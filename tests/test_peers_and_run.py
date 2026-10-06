"""Peer medians, ranks, flags, warnings and a full offline run."""

import pandas as pd
import pytest

from credit_peer.cli import collect_tickers, run
from credit_peer.metrics import analyse_company
from credit_peer.peers import Settings, add_flags, add_peer_ranks, build_table, consistency_warnings
from tests.mock_data import OMIT, make_raw

# Five peers with known operating income -> known EBITDA and leverage.
# Debt 600, cash 100 -> net debt 500 for all; D&A 50.
#   A: OI 100 -> EBITDA 150 -> 3.33x | B: OI 200 -> 250 -> 2.00x
#   C: OI  50 -> EBITDA 100 -> 5.00x | D: OI 150 -> 200 -> 2.50x
#   E: OI 300 -> EBITDA 350 -> 1.43x
OPERATING_INCOME = {"A": 100.0, "B": 200.0, "C": 50.0, "D": 150.0, "E": 300.0}


def five_peers():
    return [analyse_company(make_raw(t, income={"Operating Income": oi}))
            for t, oi in OPERATING_INCOME.items()]


def peer_table(results, settings=Settings()):
    table, stats = add_peer_ranks(build_table(results))
    return add_flags(table, settings), stats


def test_median_and_rank():
    table, stats = peer_table(five_peers())
    lev = table.set_index("ticker")["rank_net_debt_to_ebitda"]
    assert lev["E"] == "1/5"   # lowest leverage = strongest
    assert lev["C"] == "5/5"
    margin_rank = table.set_index("ticker")["rank_ebitda_margin"]
    assert margin_rank["E"] == "1/5"
    median = stats.set_index("metric").loc["net_debt_to_ebitda", "median"]
    assert median == pytest.approx(2.5)  # middle of 1.43, 2.0, 2.5, 3.33, 5.0


def test_na_companies_are_excluded_from_rank_count():
    results = five_peers() + [analyse_company(make_raw("F", income={"Total Revenue": OMIT}))]
    table, _ = peer_table(results)
    ranks = table.set_index("ticker")["rank_ebitda_margin"]
    assert ranks["F"] == "N/A"
    assert ranks["E"] == "1/5"


def test_flags_with_default_thresholds():
    table, _ = peer_table(five_peers())
    flags = table.set_index("ticker")["flags"]
    assert "HIGH_LEVERAGE(>4.0x)" in flags["C"]      # 5.0x > 4.0x
    assert "LOW_COVERAGE(<2.0x)" not in flags["C"]   # 50 / 20 = 2.5x
    assert flags["B"] == ""


def test_flags_with_custom_thresholds():
    table, _ = peer_table(five_peers(), Settings(max_leverage=3.0, min_coverage=3.0))
    flags = table.set_index("ticker")["flags"]
    assert "HIGH_LEVERAGE(>3.0x)" in flags["A"]   # 3.33x
    assert "LOW_COVERAGE(<3.0x)" in flags["C"]    # 2.5x


def test_provider_ebitda_and_incomplete_flags():
    results = [analyse_company(make_raw("P", cashflow={"Depreciation And Amortization": OMIT})),
               analyse_company(make_raw("Z", income={"Interest Expense": 0.0}))]
    table, _ = peer_table(results)
    flags = table.set_index("ticker")["flags"]
    assert "PROVIDER_EBITDA" in flags["P"]
    assert "INCOMPLETE_DATA" in flags["Z"]


def test_mixed_currency_and_period_warnings():
    results = [analyse_company(make_raw("A")),
               analyse_company(make_raw("B", currency="USD", period=pd.Timestamp("2025-06-30"))),
               analyse_company(make_raw("C"))]
    text = " ".join(consistency_warnings(results))
    assert "Mixed reporting currencies (KRW, USD)" in text
    assert "Fiscal year ends differ" in text


def test_ticker_file_parsing(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# comment\n097950.ks  # CJ\n\n271560.KS\n097950.KS\n", encoding="utf-8")
    assert collect_tickers(["aapl"], str(f)) == ["AAPL", "097950.KS", "271560.KS"]


def fake_fetcher(ticker):
    if ticker == "BAD":
        from credit_peer.fields import RawCompany
        return RawCompany("BAD", "BAD", None, None, None, None, ["income statement failed: 404"])
    return make_raw(ticker, income={"Operating Income": OPERATING_INCOME.get(ticker, 100.0)})


def test_full_run_writes_excel_and_chart(tmp_path, capsys):
    out, chart = tmp_path / "result.xlsx", tmp_path / "chart.png"
    code = run(["A", "B", "C", "D", "E", "BAD", "--out", str(out), "--chart", str(chart)],
               fetcher=fake_fetcher)
    assert code == 0
    assert out.exists() and chart.exists()

    sheets = pd.read_excel(out, sheet_name=None)
    assert list(sheets) == ["Summary", "Source items", "Peer stats", "Notes"]
    summary = sheets["Summary"].set_index("Ticker")
    assert summary.loc["C", "Net debt / EBITDA"] == pytest.approx(5.0)
    assert summary.loc["Peer median", "Net debt / EBITDA"] == pytest.approx(2.5)
    assert summary.loc["A", "FY end"] == "2025-12-31"

    printed = capsys.readouterr().out
    assert "MEDIAN" in printed
    assert "No financial statements found for: BAD" in printed


def test_full_run_csv(tmp_path):
    out = tmp_path / "result.csv"
    assert run(["A", "B", "--out", str(out)], fetcher=fake_fetcher) == 0
    df = pd.read_csv(out, encoding="utf-8-sig")
    assert "Notes" in df.columns and len(df) == 2
