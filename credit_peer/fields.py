"""Find the raw line items we need inside yfinance-style financial statements.

Why this module exists
----------------------
yfinance returns each statement as a table: rows are line items
("Total Revenue", "Operating Income", ...) and columns are fiscal year-end
dates. The row label for the same concept can differ between companies and
yfinance versions ("Total Revenue" vs "TotalRevenue"), so every item has a
list of accepted labels (aliases) that we try in order.

Rules
-----
* We only READ values that exist. Nothing is estimated, interpolated or filled.
* If an item cannot be found, it stays missing (None) and we record why.
* We record which statement and label each value came from, so every number
  can be traced back and checked against the original filing.

This module never touches the network, so it can be unit-tested offline.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class Item:
    """One raw line item: its value and where it came from, or why it is missing."""

    value: float | None
    source: str = ""  # e.g. "income_stmt: Operating Income"
    note: str = ""    # reason, filled only when value is None

    @property
    def ok(self) -> bool:
        return self.value is not None


@dataclass
class RawCompany:
    """Everything fetched for one ticker, before any calculation."""

    ticker: str
    name: str
    currency: str | None          # reporting currency of the statements
    income: pd.DataFrame | None    # income statement (rows = items, columns = dates)
    balance: pd.DataFrame | None   # balance sheet
    cashflow: pd.DataFrame | None  # cash flow statement
    fetch_errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LineItemSpec:
    """Where to look for an item and which labels to accept, in priority order."""

    statement: str              # "income", "balance" or "cashflow"
    aliases: tuple[str, ...]
    label: str                  # human-readable name used in the outputs


LINE_ITEMS: dict[str, LineItemSpec] = {
    # --- Income statement -------------------------------------------------
    "revenue": LineItemSpec(
        "income", ("Total Revenue", "Operating Revenue"), "Revenue"),
    # EBIT in this tool = OPERATING income. We deliberately do NOT use the
    # yfinance row called "EBIT", which is built as pre-tax income + interest
    # expense and therefore mixes in non-operating gains and losses.
    "operating_income": LineItemSpec(
        "income", ("Operating Income", "Total Operating Income As Reported"),
        "Operating income (EBIT)"),
    "interest_expense": LineItemSpec(
        "income", ("Interest Expense", "Interest Expense Non Operating"),
        "Interest expense"),
    # The data provider's own EBITDA. Used ONLY as a flagged fallback.
    "provider_ebitda": LineItemSpec(
        "income", ("EBITDA", "Normalized EBITDA"), "Provider EBITDA (fallback only)"),
    # Reference only, not used in any formula: lets you compare the
    # standardised operating income with the "as reported" figure.
    "operating_income_as_reported": LineItemSpec(
        "income", ("Total Operating Income As Reported",),
        "Operating income as reported (reference only)"),
    # --- Cash flow statement ----------------------------------------------
    "d_and_a": LineItemSpec(
        "cashflow",
        ("Depreciation And Amortization", "Depreciation Amortization Depletion"),
        "D&A (cash flow statement)"),
    # --- Balance sheet ----------------------------------------------------
    "total_debt": LineItemSpec("balance", ("Total Debt",), "Total debt"),
    "cash": LineItemSpec(
        "balance", ("Cash And Cash Equivalents",), "Cash & cash equivalents"),
    "cash_and_st_investments": LineItemSpec(
        "balance", ("Cash Cash Equivalents And Short Term Investments",),
        "Cash, equivalents & short-term investments"),
    # Reference only: how much of total debt is lease liabilities.
    "lease_liabilities": LineItemSpec(
        "balance", ("Capital Lease Obligations",),
        "Lease liabilities (reference only)"),
}

# Names used in the "Source" column, so a reader knows which statement to open.
STATEMENT_NAMES = {"income": "income_stmt", "balance": "balance_sheet", "cashflow": "cash_flow"}


def _normalise(label: object) -> str:
    """Make labels comparable: 'Total Revenue' and 'TotalRevenue' -> 'totalrevenue'."""
    return re.sub(r"[^a-z0-9]", "", str(label).lower())


def _is_missing(value: object) -> bool:
    """True for None, NaN or anything that is not a number."""
    if value is None:
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def latest_period(income: pd.DataFrame | None) -> pd.Timestamp | None:
    """Most recent fiscal year end that has at least one value in the income statement.

    The income statement anchors the period. Balance sheet and cash flow values
    must come from the SAME date; otherwise they are treated as missing.
    """
    if income is None or income.empty:
        return None
    filled = income.dropna(axis=1, how="all")
    if filled.empty:
        return None
    return max(pd.Timestamp(col) for col in filled.columns)


def _column_for(statement: pd.DataFrame, period: pd.Timestamp) -> object | None:
    """Return the column of `statement` whose date equals `period`, if any."""
    for col in statement.columns:
        try:
            if pd.Timestamp(col).normalize() == period.normalize():
                return col
        except (TypeError, ValueError):
            continue
    return None


def find_item(raw: RawCompany, key: str, period: pd.Timestamp | None) -> Item:
    """Look up one line item for one period, trying each alias in order."""
    spec = LINE_ITEMS[key]
    statement = {"income": raw.income, "balance": raw.balance, "cashflow": raw.cashflow}[spec.statement]
    stmt_name = STATEMENT_NAMES[spec.statement]

    if statement is None or statement.empty:
        return Item(None, note=f"{stmt_name} not available")
    if period is None:
        return Item(None, note="no fiscal period found")
    col = _column_for(statement, period)
    if col is None:
        return Item(None, note=f"{stmt_name} has no column for {period:%Y-%m-%d}")

    # Map normalised label -> actual label (first occurrence wins).
    labels: dict[str, object] = {}
    for label in statement.index:
        labels.setdefault(_normalise(label), label)

    empty: list[str] = []
    for alias in spec.aliases:
        label = labels.get(_normalise(alias))
        if label is None:
            continue
        value = statement.loc[label, col]
        if isinstance(value, pd.Series):  # duplicated row label: take the first
            value = value.iloc[0]
        if _is_missing(value):
            empty.append(alias)  # row exists but is blank: try the next alias
            continue
        return Item(float(value), source=f"{stmt_name}: {label}")

    if empty:
        return Item(None, note=f"'{', '.join(empty)}' present but empty for {period:%Y-%m-%d}")
    return Item(None, note=f"not reported (looked for: {', '.join(spec.aliases)})")


def extract_items(raw: RawCompany) -> tuple[pd.Timestamp | None, dict[str, Item]]:
    """Find the reporting period, then every line item for that period."""
    period = latest_period(raw.income)
    items = {key: find_item(raw, key, period) for key in LINE_ITEMS}
    return period, items
