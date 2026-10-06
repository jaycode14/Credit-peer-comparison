"""Metric formulas, checked against hand-calculated values."""

import pytest

from credit_peer.metrics import analyse_company
from tests.mock_data import OMIT, make_raw


def metrics_of(raw, **kwargs):
    return analyse_company(raw, **kwargs).metrics


def test_default_company_by_hand():
    m = metrics_of(make_raw())
    assert m["ebitda"].value == 150.0                          # 100 + 50
    assert m["ebitda_margin"].value == pytest.approx(0.15)      # 150 / 1000
    assert m["operating_margin"].value == pytest.approx(0.10)   # 100 / 1000
    assert m["net_debt"].value == 500.0                         # 600 - 100
    assert m["net_debt_to_ebitda"].value == pytest.approx(500 / 150)
    assert m["ebit_interest_cover"].value == pytest.approx(5.0)    # 100 / 20
    assert m["ebitda_interest_cover"].value == pytest.approx(7.5)  # 150 / 20


def test_ebitda_is_computed_not_provider():
    result = analyse_company(make_raw())
    assert result.ebitda_basis == "computed"
    assert result.metrics["ebitda"].value == 150.0  # provider says 140; we ignore it


def test_negative_d_and_a_sign_is_handled():
    m = metrics_of(make_raw(cashflow={"Depreciation And Amortization": -50.0}))
    assert m["ebitda"].value == 150.0


def test_provider_ebitda_fallback_is_flagged():
    result = analyse_company(make_raw(cashflow={"Depreciation And Amortization": OMIT}))
    assert result.ebitda_basis == "provider"
    assert result.metrics["ebitda"].value == 140.0
    assert "provider EBITDA used" in result.metrics["ebitda"].note


def test_no_ebitda_at_all():
    raw = make_raw(cashflow={"Depreciation And Amortization": OMIT}, income={"EBITDA": OMIT})
    result = analyse_company(raw)
    assert result.metrics["ebitda"].value is None
    assert result.metrics["net_debt_to_ebitda"].value is None
    assert result.ebitda_basis == ""


def test_cash_excludes_short_term_investments_by_default():
    m = metrics_of(make_raw())
    assert m["net_debt"].value == 500.0  # 600 - 100


def test_cash_can_include_short_term_investments():
    m = metrics_of(make_raw(), include_st_investments=True)
    assert m["net_debt"].value == 450.0  # 600 - 150
    assert m["net_debt_to_ebitda"].value == pytest.approx(3.0)


def test_net_cash_gives_negative_leverage():
    m = metrics_of(make_raw(balance={"Total Debt": 50.0}))
    assert m["net_debt"].value == -50.0
    assert m["net_debt_to_ebitda"].value == pytest.approx(-50 / 150)


def test_leverage_not_meaningful_when_ebitda_negative():
    m = metrics_of(make_raw(income={"Operating Income": -200.0}))
    assert m["ebitda"].value == -150.0
    assert m["net_debt_to_ebitda"].value is None
    assert "EBITDA <= 0" in m["net_debt_to_ebitda"].note


def test_zero_interest_gives_na_not_infinity():
    m = metrics_of(make_raw(income={"Interest Expense": 0.0}))
    assert m["ebit_interest_cover"].value is None
    assert "interest expense is 0" in m["ebit_interest_cover"].note


def test_negative_interest_sign_is_handled():
    m = metrics_of(make_raw(income={"Interest Expense": -20.0}))
    assert m["ebit_interest_cover"].value == pytest.approx(5.0)


def test_missing_revenue_gives_na_margins():
    m = metrics_of(make_raw(income={"Total Revenue": OMIT}))
    assert m["ebitda_margin"].value is None
    assert "missing revenue" in m["ebitda_margin"].note


def test_yfinance_ebit_row_is_not_used_as_operating_income():
    raw = make_raw(income={"Operating Income": OMIT, "EBIT": 999.0})
    result = analyse_company(raw)
    assert result.items["operating_income"].value is None
