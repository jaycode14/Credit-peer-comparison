"""fetch_company with a fake yfinance module (no network)."""

import sys
import types

from credit_peer.fetch import fetch_company
from tests.mock_data import DEFAULT_INCOME, statement


class FakeTicker:
    def __init__(self, ticker):
        self.ticker = ticker
        self.income_stmt = statement(DEFAULT_INCOME)
        self.cashflow = statement({"Depreciation And Amortization": 50.0})
        self.fast_info = {"currency": "KRW"}

    @property
    def balance_sheet(self):
        raise ConnectionError("rate limited")

    @property
    def info(self):
        return {"longName": "Fake Foods Co.", "currency": "KRW"}  # no financialCurrency


def test_fetch_records_errors_and_currency_source(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=FakeTicker))
    raw = fetch_company("000000.KS")
    assert raw.name == "Fake Foods Co."
    assert raw.income is not None and raw.balance is None
    assert raw.currency == "KRW"
    assert any("balance sheet failed: ConnectionError" in e for e in raw.fetch_errors)
    assert any("using trading currency KRW" in e for e in raw.fetch_errors)
