"""Mock financial statements shaped like yfinance output (no network needed).

Default company (easy numbers so expected results can be checked by hand):
    revenue 1,000 | operating income 100 | D&A 50  -> EBITDA 150
    total debt 600 | cash 100 | cash + ST investments 150
    interest expense 20
"""

from __future__ import annotations

import pandas as pd

from credit_peer.fields import RawCompany

FY = pd.Timestamp("2025-12-31")
PRIOR_FY = pd.Timestamp("2024-12-31")
OMIT = object()  # use as a value to remove a row entirely ("not reported")

DEFAULT_INCOME = {
    "Total Revenue": 1000.0,
    "Operating Income": 100.0,
    "Interest Expense": 20.0,
    "EBITDA": 140.0,  # provider EBITDA, deliberately different from 150
}
DEFAULT_BALANCE = {
    "Total Debt": 600.0,
    "Cash And Cash Equivalents": 100.0,
    "Cash Cash Equivalents And Short Term Investments": 150.0,
    "Capital Lease Obligations": 80.0,
}
DEFAULT_CASHFLOW = {"Depreciation And Amortization": 50.0}


def statement(values: dict, period: pd.Timestamp = FY) -> pd.DataFrame:
    """Rows = line items, columns = [latest FY, prior FY], like yfinance.

    The prior year holds different numbers (x0.5) so tests catch it if the
    wrong year is ever picked. A value of None becomes NaN ("reported but empty").
    """
    rows = {k: v for k, v in values.items() if v is not OMIT}
    latest = pd.Series(rows, dtype="float64")
    prior = latest * 0.5
    return pd.DataFrame({period: latest, PRIOR_FY: prior})


def make_raw(ticker: str = "AAA.KS", currency: str | None = "KRW", *,
             income: dict | None = None, balance: dict | None = None,
             cashflow: dict | None = None, period: pd.Timestamp = FY,
             balance_period: pd.Timestamp | None = None) -> RawCompany:
    """Build a RawCompany. Pass dicts to override or OMIT individual rows."""
    return RawCompany(
        ticker=ticker,
        name=f"{ticker} Corp",
        currency=currency,
        income=statement({**DEFAULT_INCOME, **(income or {})}, period),
        balance=statement({**DEFAULT_BALANCE, **(balance or {})}, balance_period or period),
        cashflow=statement({**DEFAULT_CASHFLOW, **(cashflow or {})}, period),
    )
