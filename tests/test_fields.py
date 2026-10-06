"""Line-item lookup: aliases, missing values, period selection."""

import pandas as pd

from credit_peer.fields import RawCompany, extract_items, latest_period
from tests.mock_data import FY, OMIT, make_raw


def test_latest_fiscal_year_is_used():
    period, items = extract_items(make_raw())
    assert period == FY
    assert items["revenue"].value == 1000.0  # not the prior-year 500


def test_source_label_is_recorded():
    _, items = extract_items(make_raw())
    assert items["operating_income"].source == "income_stmt: Operating Income"
    assert items["d_and_a"].source == "cash_flow: Depreciation And Amortization"


def test_compact_labels_from_older_yfinance_are_matched():
    raw = make_raw(income={"Total Revenue": OMIT, "TotalRevenue": 900.0})
    _, items = extract_items(raw)
    assert items["revenue"].value == 900.0


def test_next_alias_is_used_when_first_is_absent():
    raw = make_raw(income={"Total Revenue": OMIT, "Operating Revenue": 800.0})
    _, items = extract_items(raw)
    assert items["revenue"].value == 800.0
    assert items["revenue"].source.endswith("Operating Revenue")


def test_empty_row_falls_through_to_next_alias():
    raw = make_raw(income={"Total Revenue": None, "Operating Revenue": 800.0})
    _, items = extract_items(raw)
    assert items["revenue"].value == 800.0


def test_missing_item_is_none_with_reason_never_filled():
    raw = make_raw(balance={"Total Debt": OMIT})
    _, items = extract_items(raw)
    assert items["total_debt"].value is None
    assert "not reported" in items["total_debt"].note


def test_empty_item_reason():
    raw = make_raw(balance={"Total Debt": None})
    _, items = extract_items(raw)
    assert items["total_debt"].value is None
    assert "empty" in items["total_debt"].note


def test_balance_sheet_from_another_date_is_not_used():
    raw = make_raw(balance_period=pd.Timestamp("2025-06-30"))
    _, items = extract_items(raw)
    assert items["total_debt"].value is None
    assert "no column for 2025-12-31" in items["total_debt"].note


def test_no_statements_at_all():
    raw = RawCompany("BAD", "BAD", None, None, None, None)
    period, items = extract_items(raw)
    assert period is None
    assert all(item.value is None for item in items.values())


def test_latest_period_skips_all_empty_columns():
    df = pd.DataFrame({pd.Timestamp("2025-12-31"): [None], pd.Timestamp("2024-12-31"): [1.0]},
                      index=["Total Revenue"])
    assert latest_period(df) == pd.Timestamp("2024-12-31")
