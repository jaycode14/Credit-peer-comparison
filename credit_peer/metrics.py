"""Credit metric formulas.

Every function takes Items (raw line items) or Metrics (already calculated
values) and returns a Metric. If an input is missing, or the result would be
meaningless (e.g. dividing by a negative EBITDA), the Metric's value is None
and its note explains why. Nothing is ever estimated.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .fields import Item, RawCompany, extract_items


@dataclass(frozen=True)
class Metric:
    """A calculated value, or None plus the reason it could not be calculated."""

    value: float | None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None


# Display names, shared by the console, Excel and CSV outputs.
METRIC_LABELS = {
    "ebitda": "EBITDA",
    "net_debt": "Net debt",
    "ebitda_margin": "EBITDA margin",
    "operating_margin": "Operating margin",
    "net_debt_to_ebitda": "Net debt / EBITDA",
    "ebit_interest_cover": "EBIT / interest",
    "ebitda_interest_cover": "EBITDA / interest",
}

# The ratios that are compared across peers (amounts are not, see peers.py).
RATIO_KEYS = [
    "ebitda_margin",
    "operating_margin",
    "net_debt_to_ebitda",
    "ebit_interest_cover",
    "ebitda_interest_cover",
]


def _missing(*inputs: tuple[str, Item | Metric]) -> str | None:
    """Return 'missing X, Y' for any input without a value, or None if all present."""
    names = [name for name, x in inputs if not x.ok]
    return "missing " + ", ".join(names) if names else None


def ebitda(operating_income: Item, d_and_a: Item, provider_ebitda: Item) -> tuple[Metric, str]:
    """EBITDA = EBIT (operating income) + D&A (from the cash flow statement).

    What: operating profit before the non-cash charge for depreciation and
    amortisation.
    Why: it approximates the cash earnings available to service debt, and is the
    base lenders size debt against (e.g. "net debt no more than 4x EBITDA").

    Fallback: if EBIT or D&A is missing, the data provider's EBITDA is used and
    the basis is marked "provider" so it gets flagged. Its definition may differ
    from ours (yfinance builds it from pre-tax income + interest + D&A).

    Returns (metric, basis) where basis is "computed", "provider" or "".
    """
    if operating_income.ok and d_and_a.ok:
        # D&A is an expense; whether the cash flow statement shows it as + or -
        # is a presentation choice, so we add back its absolute size.
        return Metric(operating_income.value + abs(d_and_a.value)), "computed"

    reason = _missing(("operating income", operating_income), ("D&A", d_and_a))
    if provider_ebitda.ok:
        return Metric(provider_ebitda.value, note=f"provider EBITDA used ({reason})"), "provider"
    return Metric(None, note=f"{reason}; no provider EBITDA either"), ""


def margin(profit: Item | Metric, revenue: Item, profit_name: str) -> Metric:
    """Margin = profit / revenue.

    What: the share of each unit of sales that is kept as profit.
    Why: a size-neutral measure of earnings strength, so a small and a large
    company can be compared, and a thin margin means less room to absorb shocks.
    """
    reason = _missing((profit_name, profit), ("revenue", revenue))
    if reason:
        return Metric(None, reason)
    if revenue.value <= 0:
        return Metric(None, "revenue <= 0")
    return Metric(profit.value / revenue.value)


def net_debt(total_debt: Item, cash: Item) -> Metric:
    """Net debt = total debt - cash.

    What: borrowings left after using the cash on hand to repay them.
    Why: cash could repay debt today, so lenders look at debt net of cash.
    A negative value means a net cash position. Which cash definition is used
    (with or without short-term investments) is chosen by the caller and shown
    in every output.
    """
    reason = _missing(("total debt", total_debt), ("cash", cash))
    if reason:
        return Metric(None, reason)
    return Metric(total_debt.value - cash.value)


def net_debt_to_ebitda(net_debt_metric: Metric, ebitda_metric: Metric) -> Metric:
    """Leverage = net debt / EBITDA.

    What: roughly how many years of EBITDA it would take to repay net debt.
    Why: the core leverage measure in acquisition and leveraged finance, and
    the most common financial covenant.
    If EBITDA <= 0 the ratio is meaningless (the sign flips), so it is N/A.
    """
    reason = _missing(("net debt", net_debt_metric), ("EBITDA", ebitda_metric))
    if reason:
        return Metric(None, reason)
    if ebitda_metric.value <= 0:
        return Metric(None, "EBITDA <= 0: ratio not meaningful")
    return Metric(net_debt_metric.value / ebitda_metric.value)


def interest_cover(earnings: Item | Metric, interest_expense: Item, earnings_name: str) -> Metric:
    """Interest cover = earnings / interest expense.

    What: how many times operating earnings cover the annual interest bill.
    Why: shows whether the company can pay interest out of operations; below
    1x it cannot. EBIT is the stricter version (after D&A), EBITDA the looser one.
    Interest expense signs differ between sources, so its absolute size is used.
    Zero interest gives N/A (division by zero; usually little or no debt).
    """
    reason = _missing((earnings_name, earnings), ("interest expense", interest_expense))
    if reason:
        return Metric(None, reason)
    interest = abs(interest_expense.value)
    if interest == 0:
        return Metric(None, "interest expense is 0")
    return Metric(earnings.value / interest)


@dataclass
class CompanyResult:
    """All inputs and outputs for one company, kept together for traceability."""

    ticker: str
    name: str
    currency: str | None
    period: pd.Timestamp | None
    cash_key: str                 # which cash line item was used for net debt
    items: dict[str, Item]
    metrics: dict[str, Metric]
    ebitda_basis: str             # "computed", "provider" or ""
    notes: list[str]


def analyse_company(raw: RawCompany, include_st_investments: bool = False) -> CompanyResult:
    """Run every formula for one company."""
    period, items = extract_items(raw)
    cash_key = "cash_and_st_investments" if include_st_investments else "cash"

    ebitda_m, basis = ebitda(items["operating_income"], items["d_and_a"], items["provider_ebitda"])
    net_debt_m = net_debt(items["total_debt"], items[cash_key])

    metrics = {
        "ebitda": ebitda_m,
        "net_debt": net_debt_m,
        "ebitda_margin": margin(ebitda_m, items["revenue"], "EBITDA"),
        "operating_margin": margin(items["operating_income"], items["revenue"], "operating income"),
        "net_debt_to_ebitda": net_debt_to_ebitda(net_debt_m, ebitda_m),
        "ebit_interest_cover": interest_cover(items["operating_income"], items["interest_expense"], "EBIT"),
        "ebitda_interest_cover": interest_cover(ebitda_m, items["interest_expense"], "EBITDA"),
    }

    notes = list(raw.fetch_errors)
    if period is None:
        notes.append("no financial statements found: all metrics N/A")
    else:
        for key, metric in metrics.items():
            if metric.note:
                notes.append(f"{METRIC_LABELS[key]}: {metric.note}")

    return CompanyResult(
        ticker=raw.ticker,
        name=raw.name,
        currency=raw.currency,
        period=period,
        cash_key=cash_key,
        items=items,
        metrics=metrics,
        ebitda_basis=basis,
        notes=notes,
    )
