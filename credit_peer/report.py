"""Outputs: console table, Excel workbook (or CSV) and an optional bar chart.

Every output keeps the fiscal year end, currency and source values next to the
ratios, so each number can be checked against the company's filing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .fields import LINE_ITEMS
from .metrics import METRIC_LABELS, RATIO_KEYS, CompanyResult
from .peers import Settings

PERCENT_KEYS = {"ebitda_margin", "operating_margin"}

# Column headers for the Excel / CSV summary.
SUMMARY_HEADERS = {
    "ticker": "Ticker",
    "name": "Company",
    "fy_end": "FY end",
    "currency": "Currency",
    "ebitda_basis": "EBITDA basis",
    "cash_basis": "Cash basis",
    "revenue": "Revenue",
    "operating_income": "EBIT (operating income)",
    "d_and_a": "D&A",
    "ebitda": "EBITDA",
    "interest_expense": "Interest expense",
    "total_debt": "Total debt",
    "cash_used": "Cash (per cash basis)",
    "net_debt": "Net debt",
    **{key: METRIC_LABELS[key] for key in RATIO_KEYS},
    **{f"rank_{key}": f"Rank: {METRIC_LABELS[key]}" for key in RATIO_KEYS},
    "flags": "Flags",
}

DEFINITIONS = [
    "EBIT = operating income (income statement). yfinance's own 'EBIT' row is not used.",
    "D&A = depreciation & amortisation from the cash flow statement (absolute value).",
    "EBITDA = EBIT + D&A. If either is missing, the provider's EBITDA is used and flagged PROVIDER_EBITDA.",
    "EBITDA margin = EBITDA / revenue. Operating margin = EBIT / revenue.",
    "Net debt = total debt - cash (cash definition: see 'Cash basis'). Negative = net cash.",
    "Net debt / EBITDA: N/A if EBITDA <= 0.",
    "EBIT / interest and EBITDA / interest: interest expense in absolute value; N/A if it is 0.",
    "Ranks: '1/5' = strongest of 5 peers with data (higher margins and cover, lower leverage).",
    "Amounts are in each company's reporting currency, full units, as provided by Yahoo Finance.",
]


def _text_table(frame: pd.DataFrame) -> str:
    """Plain left-aligned text table (pandas right-aligns text, which reads badly)."""
    rows = [[str(c) for c in frame.columns]]
    rows += [[str(v) for v in row] for row in frame.itertuples(index=False)]
    widths = [max(len(row[i]) for row in rows) for i in range(len(frame.columns))]
    return "\n".join("  ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip() for row in rows)


def _fmt(key: str, value: float) -> str:
    """Format a ratio for the console: 12.3% or 2.1x, or N/A."""
    if pd.isna(value):
        return "N/A"
    return f"{value * 100:.1f}%" if key in PERCENT_KEYS else f"{value:.2f}x"


# ---------------------------------------------------------------- console
def console_report(df: pd.DataFrame, stats: pd.DataFrame, results: list[CompanyResult],
                   warnings: list[str], settings: Settings) -> str:
    """Build the text printed to the terminal (ASCII only, safe on any console)."""
    companies = df[["ticker", "name", "fy_end", "currency", "ebitda_basis"]].copy()
    companies["name"] = companies["name"].astype(str).str.slice(0, 30)
    companies.columns = ["Ticker", "Company", "FY end", "Ccy", "EBITDA basis"]

    table = pd.DataFrame({"Ticker": df["ticker"]})
    for key in RATIO_KEYS:
        table[METRIC_LABELS[key]] = [
            "N/A" if rank == "N/A" else f"{_fmt(key, v)} ({rank})"
            for v, rank in zip(df[key], df[f"rank_{key}"])
        ]
    table["Flags"] = df["flags"]
    medians = stats.set_index("metric")["median"]
    median_row = {"Ticker": "MEDIAN", **{METRIC_LABELS[k]: _fmt(k, medians[k]) for k in RATIO_KEYS}, "Flags": ""}
    table = pd.concat([table, pd.DataFrame([median_row])], ignore_index=True)

    lines = [
        "",
        "CREDIT PEER COMPARISON  (latest fiscal year, data: Yahoo Finance via yfinance)",
        f"Cash basis for net debt: {settings.cash_basis}",
        "",
        _text_table(companies),
        "",
        "Value (rank among peers with data; 1 = strongest credit profile)",
        _text_table(table),
        "",
        f"Flag thresholds: net debt/EBITDA > {settings.max_leverage:.1f}x, EBIT/interest < "
        f"{settings.min_coverage:.1f}x. These are illustrative examples, NOT a credit policy.",
    ]
    if warnings:
        lines += ["", "WARNINGS"] + [f"  - {w}" for w in warnings]
    notes = [(r.ticker, n) for r in results for n in r.notes]
    if notes:
        lines += ["", "NOTES (why a value is N/A or needs checking)"]
        lines += [f"  - {ticker}: {note}" for ticker, note in notes]
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------- tables for files
def summary_frame(df: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """Summary table with readable headers and a peer-median row for the ratios."""
    out = df[list(SUMMARY_HEADERS)].copy()
    medians = stats.set_index("metric")["median"]
    median_row = {col: None for col in out.columns}
    median_row.update({"ticker": "Peer median", **{k: medians[k] for k in RATIO_KEYS}})
    # dropna(axis=1): leave the blank cells out of the new row (avoids a pandas warning)
    median_df = pd.DataFrame([median_row]).dropna(axis=1, how="all")
    out = pd.concat([out, median_df], ignore_index=True)
    return out.rename(columns=SUMMARY_HEADERS)


def source_items_frame(results: list[CompanyResult]) -> pd.DataFrame:
    """Long table: one row per company x line item, with the exact label used."""
    rows = []
    for r in results:
        for key, item in r.items.items():
            rows.append({
                "Ticker": r.ticker,
                "Company": r.name,
                "FY end": r.period.strftime("%Y-%m-%d") if r.period is not None else "N/A",
                "Currency": r.currency or "N/A",
                "Item": LINE_ITEMS[key].label,
                "Value": item.value,
                "Source (statement: yfinance label)": item.source or "N/A",
                "Note": item.note,
            })
    return pd.DataFrame(rows)


def peer_stats_frame(stats: pd.DataFrame) -> pd.DataFrame:
    out = stats.copy()
    out["metric"] = out["metric"].map(METRIC_LABELS)
    return out.rename(columns={"metric": "Metric", "median": "Median", "min": "Min", "max": "Max",
                               "n_valid": "Peers with data", "better": "Better if"})


def notes_frame(results: list[CompanyResult], warnings: list[str], settings: Settings) -> pd.DataFrame:
    rows = [
        ("Run", f"Data retrieved from Yahoo Finance via yfinance on {datetime.now():%Y-%m-%d %H:%M}."),
        ("Run", "Check figures against the original filings (e.g. DART, SEC) before any use."),
        ("Settings", f"Cash basis: {settings.cash_basis}"),
        ("Settings", f"Flag if net debt / EBITDA > {settings.max_leverage:.1f}x (illustrative, not a credit policy)"),
        ("Settings", f"Flag if EBIT / interest < {settings.min_coverage:.1f}x (illustrative, not a credit policy)"),
    ]
    rows += [("Definition", d) for d in DEFINITIONS]
    rows += [("Warning", w) for w in warnings]
    rows += [(f"Note: {r.ticker}", n) for r in results for n in r.notes]
    return pd.DataFrame(rows, columns=["Section", "Detail"])


# ------------------------------------------------------------- file writers
HEADER_TO_KEY = {header: key for key, header in SUMMARY_HEADERS.items()}
AMOUNT_HEADERS = {"Value"}  # amount column on the "Source items" sheet


def _number_format(header: str) -> str | None:
    """Excel number format for a column, chosen from its header."""
    key = HEADER_TO_KEY.get(header)
    if key in PERCENT_KEYS:
        return "0.0%;(0.0%)"
    if key in RATIO_KEYS:
        return '0.00"x";(0.00"x")'
    if key in {"revenue", "operating_income", "d_and_a", "ebitda", "interest_expense",
               "total_debt", "cash_used", "net_debt"} or header in AMOUNT_HEADERS:
        return "#,##0;(#,##0)"
    return None


def _style_sheet(ws, bold_last_row: bool = False) -> None:
    """Arial font, bold header, number formats, column widths, frozen header."""
    from openpyxl.styles import Font, PatternFill

    headers = [cell.value for cell in ws[1]]
    for cell in ws[1]:
        cell.font = Font(name="Arial", size=10, bold=True)
        cell.fill = PatternFill("solid", start_color="D9E1F2")

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial", size=10, bold=bold_last_row and cell.row == ws.max_row)
            fmt = _number_format(str(headers[cell.column - 1]))
            if fmt and isinstance(cell.value, (int, float)):
                cell.number_format = fmt

    # Column width = longest displayed value in the column (capped at 60).
    for column in ws.iter_cols():
        lengths = [_display_len(cell.value) for cell in column]
        ws.column_dimensions[column[0].column_letter].width = min(max(lengths) + 2, 60)
    ws.freeze_panes = "B2"


def _display_len(value: object) -> int:
    """Approximate width of a value as Excel will show it."""
    if value is None:
        return 0
    if isinstance(value, float):
        return len(f"{value:,.2f}")
    return len(str(value))


def write_excel(path: Path, df: pd.DataFrame, stats: pd.DataFrame, results: list[CompanyResult],
                warnings: list[str], settings: Settings) -> None:
    """Workbook with four sheets: Summary, Source items, Peer stats, Notes."""
    sheets = {
        "Summary": summary_frame(df, stats),
        "Source items": source_items_frame(results),
        "Peer stats": peer_stats_frame(stats),
        "Notes": notes_frame(results, warnings, settings),
    }
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            _style_sheet(writer.sheets[name], bold_last_row=(name == "Summary"))
        _format_peer_stats(writer.sheets["Peer stats"])


def _format_peer_stats(ws) -> None:
    """Peer stats mixes % and x metrics, so format row by row (columns B-D)."""
    percent_labels = {METRIC_LABELS[k] for k in PERCENT_KEYS}
    for row in ws.iter_rows(min_row=2):
        fmt = "0.0%;(0.0%)" if row[0].value in percent_labels else '0.00"x";(0.00"x")'
        for cell in row[1:4]:
            cell.number_format = fmt


def write_csv(path: Path, df: pd.DataFrame, results: list[CompanyResult]) -> None:
    """Single CSV: the summary plus a 'Notes' column. utf-8-sig opens cleanly in Excel."""
    out = df[list(SUMMARY_HEADERS)].rename(columns=SUMMARY_HEADERS)
    out["Notes"] = [" | ".join(r.notes) for r in results]
    out.to_csv(path, index=False, encoding="utf-8-sig")


def save_chart(path: Path, df: pd.DataFrame, stats: pd.DataFrame, settings: Settings) -> None:
    """Bar chart of net debt / EBITDA with the example threshold and peer median."""
    import matplotlib
    matplotlib.use("Agg")  # draw to file only, no window needed
    import matplotlib.pyplot as plt

    data = df[["ticker", "net_debt_to_ebitda", "fy_end"]]
    valid = data.dropna(subset=["net_debt_to_ebitda"])
    missing = data.loc[data["net_debt_to_ebitda"].isna(), "ticker"].tolist()

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#C0392B" if v > settings.max_leverage else "#2E86C1" for v in valid["net_debt_to_ebitda"]]
    bars = ax.bar(valid["ticker"], valid["net_debt_to_ebitda"], color=colors)
    for bar, value in zip(bars, valid["net_debt_to_ebitda"]):
        ax.annotate(f"{value:.2f}x", (bar.get_x() + bar.get_width() / 2, value),
                    ha="center", va="bottom" if value >= 0 else "top", fontsize=9)

    ax.axhline(0, color="black", linewidth=0.8)
    ax.axhline(settings.max_leverage, color="grey", linestyle="--",
               label=f"Example threshold {settings.max_leverage:.1f}x (not a credit policy)")
    median = stats.set_index("metric").loc["net_debt_to_ebitda", "median"]
    if pd.notna(median):
        ax.axhline(median, color="#7D3C98", linestyle=":", label=f"Peer median {median:.2f}x")

    periods = ", ".join(sorted(set(valid["fy_end"]))) or "N/A"
    ax.set_title(f"Net debt / EBITDA (FY end: {periods})")
    ax.set_ylabel("x (negative = net cash)")
    ax.legend(fontsize=8)
    if missing:
        fig.text(0.01, 0.01, f"N/A (see notes): {', '.join(missing)}", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
