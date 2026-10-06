"""Peer comparison: one table for all companies, medians, ranks, flags, warnings.

Only RATIOS are compared across peers. Ratios have no currency, so a KRW and a
USD company can be compared on them. Amounts (revenue, debt, ...) are shown per
company for verification but are never added up or compared across companies.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .fields import LINE_ITEMS
from .metrics import RATIO_KEYS, CompanyResult

# For ranking: True if a higher value is the stronger credit profile.
HIGHER_IS_BETTER = {
    "ebitda_margin": True,
    "operating_margin": True,
    "net_debt_to_ebitda": False,   # less leverage ranks better (net cash ranks best)
    "ebit_interest_cover": True,
    "ebitda_interest_cover": True,
}

# Amount columns shown per company (same currency as that company's statements).
AMOUNT_KEYS = [
    "revenue", "operating_income", "d_and_a", "ebitda",
    "interest_expense", "total_debt", "cash_used", "net_debt",
]


@dataclass(frozen=True)
class Settings:
    """User-adjustable settings. Default thresholds are EXAMPLES, not credit policy."""

    max_leverage: float = 4.0    # flag if net debt / EBITDA is above this
    min_coverage: float = 2.0    # flag if EBIT / interest is below this
    include_st_investments: bool = False

    @property
    def cash_basis(self) -> str:
        key = "cash_and_st_investments" if self.include_st_investments else "cash"
        return LINE_ITEMS[key].label


def build_table(results: list[CompanyResult]) -> pd.DataFrame:
    """One row per company: period, currency, source amounts and ratios."""
    rows = []
    for r in results:
        row = {
            "ticker": r.ticker,
            "name": r.name,
            "fy_end": r.period.strftime("%Y-%m-%d") if r.period is not None else "N/A",
            "currency": r.currency or "N/A",
            "ebitda_basis": r.ebitda_basis or "N/A",
            "cash_basis": LINE_ITEMS[r.cash_key].label,
            "revenue": r.items["revenue"].value,
            "operating_income": r.items["operating_income"].value,
            "d_and_a": r.items["d_and_a"].value,
            "ebitda": r.metrics["ebitda"].value,
            "interest_expense": r.items["interest_expense"].value,
            "total_debt": r.items["total_debt"].value,
            "cash_used": r.items[r.cash_key].value,
            "net_debt": r.metrics["net_debt"].value,
        }
        for key in RATIO_KEYS:
            row[key] = r.metrics[key].value
        rows.append(row)

    df = pd.DataFrame(rows)
    # None -> NaN, so medians and ranks skip missing values cleanly.
    for key in AMOUNT_KEYS + RATIO_KEYS:
        df[key] = df[key].astype(float)
    return df


def add_peer_ranks(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add 'rank_<metric>' columns and return peer statistics for each ratio.

    Rank is written as "2/5": 2nd strongest of the 5 peers that have a value.
    Ties share the better rank. Companies with N/A are left out of the count.
    """
    df = df.copy()
    stats = []
    for key, higher_is_better in HIGHER_IS_BETTER.items():
        values = df[key]
        n_valid = int(values.notna().sum())
        ranks = values.rank(ascending=not higher_is_better, method="min")
        df[f"rank_{key}"] = [f"{int(r)}/{n_valid}" if pd.notna(r) else "N/A" for r in ranks]
        stats.append({
            "metric": key,
            "median": values.median(),
            "min": values.min(),
            "max": values.max(),
            "n_valid": n_valid,
            "better": "higher" if higher_is_better else "lower",
        })
    return df, pd.DataFrame(stats)


def add_flags(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Add a 'flags' column with rule-based review flags.

    Flags point to companies that need a closer look. They are not a credit
    decision, and the default thresholds are illustrative only.
    """
    df = df.copy()
    flags = []
    for _, row in df.iterrows():
        f = []
        lev, cover = row["net_debt_to_ebitda"], row["ebit_interest_cover"]
        if pd.notna(lev) and lev > settings.max_leverage:
            f.append(f"HIGH_LEVERAGE(>{settings.max_leverage:.1f}x)")
        if pd.notna(cover) and cover < settings.min_coverage:
            f.append(f"LOW_COVERAGE(<{settings.min_coverage:.1f}x)")
        if pd.notna(row["ebitda"]) and row["ebitda"] <= 0:
            f.append("EBITDA<=0")
        if row["ebitda_basis"] == "provider":
            f.append("PROVIDER_EBITDA")
        if row[RATIO_KEYS].isna().any():
            f.append("INCOMPLETE_DATA")
        flags.append(", ".join(f))
    df["flags"] = flags
    return df


def consistency_warnings(results: list[CompanyResult]) -> list[str]:
    """Warnings about things that make a peer comparison less like-for-like."""
    warnings = []

    no_data = [r.ticker for r in results if r.period is None]
    if no_data:
        warnings.append(f"No financial statements found for: {', '.join(no_data)} (check the ticker and your internet connection).")

    unknown_ccy = [r.ticker for r in results if not r.currency]
    if unknown_ccy:
        warnings.append(f"Reporting currency unknown for: {', '.join(unknown_ccy)}.")

    currencies = sorted({r.currency for r in results if r.currency})
    if len(currencies) > 1:
        warnings.append(
            f"Mixed reporting currencies ({', '.join(currencies)}). Ratios are comparable; "
            "amounts are NOT - do not add or compare them across companies."
        )

    periods = sorted({r.period.strftime("%Y-%m-%d") for r in results if r.period is not None})
    if len(periods) > 1:
        warnings.append(
            f"Fiscal year ends differ ({', '.join(periods)}). Each company is shown on its "
            "latest fiscal year, so the periods are not identical."
        )

    with_data = sum(r.period is not None for r in results)
    if 0 < with_data < 3:
        warnings.append("Fewer than 3 companies with data: medians and ranks say little.")
    return warnings
