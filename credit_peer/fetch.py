"""Download annual financial statements from Yahoo Finance via yfinance.

This is the ONLY module that uses the network. Everything downstream works on
the returned RawCompany, which is why all calculations can be tested offline
with mock data (see tests/).
"""

from __future__ import annotations

from typing import Any, Callable

from .fields import RawCompany


def _try(label: str, func: Callable[[], Any], errors: list[str]) -> Any:
    """Call func(); on any error, record a short message and return None.

    yfinance can fail in many ways (unknown ticker, rate limit, changed page
    layout), so one failed request should not stop the whole peer group.
    """
    try:
        return func()
    except Exception as exc:  # noqa: BLE001 - we report every failure as a note
        errors.append(f"{label} failed: {type(exc).__name__}: {str(exc)[:200]}")
        return None


def fetch_company(ticker: str) -> RawCompany:
    """Fetch the annual income statement, balance sheet and cash flow for one ticker."""
    import yfinance as yf  # imported here so the unit tests do not need yfinance

    errors: list[str] = []
    t = yf.Ticker(ticker)

    # Annual statements: rows = line items, columns = fiscal year-end dates.
    income = _try("income statement", lambda: t.income_stmt, errors)
    balance = _try("balance sheet", lambda: t.balance_sheet, errors)
    cashflow = _try("cash flow statement", lambda: t.cashflow, errors)

    info = _try("company info", lambda: t.info, errors) or {}
    name = info.get("longName") or info.get("shortName") or ticker
    # 'financialCurrency' = currency of the statements.
    # 'currency' = currency the share trades in (can differ, e.g. for ADRs).
    currency = info.get("financialCurrency")
    if not currency:
        currency = info.get("currency") or _try("quote currency", lambda: t.fast_info["currency"], errors)
        if currency:
            errors.append(f"reporting currency not available; using trading currency {currency} - please verify")

    return RawCompany(ticker, name, currency, income, balance, cashflow, errors)
