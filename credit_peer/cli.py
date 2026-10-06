"""Command-line entry point.

Examples
--------
    python -m credit_peer 097950.KS 271560.KS 004370.KS
    python -m credit_peer --file peers/kr_food.txt --chart
    python -m credit_peer --file peers/kr_food.txt --out output/kr_food.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable

from .fields import RawCompany
from .metrics import analyse_company
from .peers import Settings, add_flags, add_peer_ranks, build_table, consistency_warnings
from .report import console_report, save_chart, write_csv, write_excel


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m credit_peer",
        description="Credit peer comparison: EBITDA, leverage and interest cover vs peers.",
    )
    p.add_argument("tickers", nargs="*", help="Tickers, e.g. 097950.KS 271560.KS AAPL")
    p.add_argument("-f", "--file", help="Text file with one ticker per line ('#' starts a comment)")
    p.add_argument("-o", "--out", default="output/credit_peer_comparison.xlsx",
                   help="Output file, .xlsx or .csv (default: %(default)s)")
    p.add_argument("--chart", nargs="?", const="output/net_debt_to_ebitda.png", default=None,
                   help="Save a net debt / EBITDA bar chart (default path: %(const)s)")
    p.add_argument("--max-leverage", type=float, default=4.0,
                   help="Flag if net debt / EBITDA is above this. Illustrative default: %(default)s")
    p.add_argument("--min-coverage", type=float, default=2.0,
                   help="Flag if EBIT / interest is below this. Illustrative default: %(default)s")
    p.add_argument("--include-st-investments", action="store_true",
                   help="Net debt uses cash + short-term investments (default: cash & equivalents only)")
    return p


def read_ticker_file(path: str) -> list[str]:
    """One ticker per line; blank lines and anything after '#' are ignored."""
    tickers = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        ticker = line.split("#", 1)[0].strip()
        if ticker:
            tickers.append(ticker)
    return tickers


def collect_tickers(cli_tickers: list[str], file_path: str | None) -> list[str]:
    """Combine CLI and file tickers, upper-case them, drop duplicates, keep order."""
    tickers = list(cli_tickers) + (read_ticker_file(file_path) if file_path else [])
    unique: list[str] = []
    for t in tickers:
        t = t.strip().upper()
        if t and t not in unique:
            unique.append(t)
    return unique


def run(argv: list[str] | None = None,
        fetcher: Callable[[str], RawCompany] | None = None) -> int:
    """Fetch -> calculate -> compare -> report. `fetcher` can be replaced in tests."""
    parser = build_parser()
    args = parser.parse_args(argv)
    tickers = collect_tickers(args.tickers, args.file)
    if not tickers:
        parser.error("give at least one ticker, or --file with a list of tickers")
    if args.max_leverage <= 0 or args.min_coverage <= 0:
        parser.error("thresholds must be positive numbers")

    if fetcher is None:
        from .fetch import fetch_company as fetcher

    settings = Settings(args.max_leverage, args.min_coverage, args.include_st_investments)

    results = []
    for i, ticker in enumerate(tickers, start=1):
        print(f"[{i}/{len(tickers)}] fetching {ticker} ...", flush=True)
        results.append(analyse_company(fetcher(ticker), settings.include_st_investments))
        if i < len(tickers):
            time.sleep(0.5)  # be polite to Yahoo and reduce rate-limit errors

    table = build_table(results)
    table, stats = add_peer_ranks(table)
    table = add_flags(table, settings)
    warnings = consistency_warnings(results)

    print(console_report(table, stats, results, warnings, settings))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".csv":
        write_csv(out, table, results)
    else:
        write_excel(out, table, stats, results, warnings, settings)
    print(f"Saved table: {out}")

    if args.chart:
        chart = Path(args.chart)
        chart.parent.mkdir(parents=True, exist_ok=True)
        save_chart(chart, table, stats, settings)
        print(f"Saved chart: {chart}")
    return 0


def main() -> None:
    sys.exit(run())
