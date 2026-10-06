# Credit Peer Comparison

A small Python tool that compares listed companies **from a lender's point of view**.
Give it a list of tickers (Korean `.KS` / `.KQ` or US) and it pulls each company's latest
annual financial statements, calculates credit metrics from the raw line items, and shows
where each company sits against its peers.

It answers the three questions a corporate / acquisition finance lender asks first:

1. **How strong are the earnings?** EBITDA, EBITDA margin, operating margin
2. **Can the company carry its debt?** Net debt / EBITDA, interest cover
3. **Where does it sit against comparable companies?** Peer median and rank, plus review flags

> Portfolio / learning project. Not investment advice. Flag thresholds are illustrative only.

## Principles

- **Numbers are calculated from source line items**, using the formulas below. A
  provider-calculated figure is used in one case only (EBITDA fallback), and it is flagged.
- **Nothing is estimated or filled in.** A missing value is shown as N/A with the reason.
- **Every number is traceable.** Each output row carries the fiscal year end, reporting
  currency, the source values, and the exact yfinance label each value came from, so it can
  be checked against the original filing (DART, SEC).
- **AI is not part of the calculation.** An AI assistant (Claude) was used to help write and
  test the code. No figure is generated, estimated or edited by an AI model.

## Metrics

| Metric | Formula | Why it matters to a lender |
|---|---|---|
| EBIT | Operating income (income statement) | Profit from the core business, before financing costs |
| D&A | Depreciation & amortisation (cash flow statement) | Non-cash expense, added back to get EBITDA |
| EBITDA | EBIT + D&A | Approximate cash earnings; the base debt is sized against |
| EBITDA margin | EBITDA / Revenue | Size-neutral earnings strength |
| Operating margin | EBIT / Revenue | Earnings strength after D&A |
| Net debt | Total debt − Cash | Debt left after using cash on hand. Negative = net cash |
| Net debt / EBITDA | Net debt / EBITDA | Years of EBITDA to repay net debt; the most common leverage covenant |
| EBIT / interest | EBIT / Interest expense | Can operating profit pay the interest bill? |
| EBITDA / interest | EBITDA / Interest expense | Looser version of the above |

**Definition choices (stated explicitly because they change the numbers):**

- **EBIT = operating income.** yfinance also has a row called "EBIT", but it is built as
  pre-tax income + interest expense, so it mixes in non-operating gains and losses. It is not used.
- **Cash** defaults to *cash & cash equivalents only* (conservative). With
  `--include-st-investments`, net debt uses *cash, cash equivalents & short-term investments*
  instead. Korean companies often hold large short-term financial instruments, so this choice
  can move net debt materially. The basis used is printed in every output.
- **Total debt** is Yahoo's "Total Debt" line, which generally includes lease liabilities.
  Under IFRS 16, lease costs sit in depreciation and interest rather than in operating
  expenses, so EBITDA is already "pre-lease"; keeping leases in debt makes the ratio
  consistent. The lease amount is shown separately for reference.
- **Interest expense** is used in absolute value because sign conventions differ between sources.
- **N/A rules:** Net debt / EBITDA is N/A when EBITDA ≤ 0 (the ratio would flip sign and
  mislead). Interest cover is N/A when interest expense is 0. Margins are N/A when revenue ≤ 0.
- **EBITDA fallback:** if operating income or D&A is missing, the provider's EBITDA is used
  and flagged `PROVIDER_EBITDA`, because its definition may differ.

## Peer comparison and flags

- **Median** of each ratio across the peers that have a value.
- **Rank** shown as `2/5` = 2nd strongest of 5 peers with data. Higher margins and cover rank
  better; lower leverage ranks better (net cash ranks best).
- **Only ratios are compared across companies.** Amounts stay in each company's own currency
  and are never added or compared, so mixed KRW/USD peer groups are safe for ratios.

| Flag | Meaning |
|---|---|
| `HIGH_LEVERAGE(>4.0x)` | Net debt / EBITDA above `--max-leverage` |
| `LOW_COVERAGE(<2.0x)` | EBIT / interest below `--min-coverage` |
| `EBITDA<=0` | EBITDA zero or negative |
| `PROVIDER_EBITDA` | EBITDA taken from the data provider, not computed |
| `INCOMPLETE_DATA` | At least one ratio is N/A (see notes) |

The default thresholds (4.0x and 2.0x) are **examples for illustration, not a credit
standard**. Real thresholds depend on the sector, the deal and the lender.

**Warnings** are printed when reporting currencies are mixed, fiscal year ends differ, a
company has no statements, or fewer than 3 companies have data.

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/<your-username>/credit-peer-comparison.git
cd credit-peer-comparison
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m credit_peer --file peers/kr_food.txt --chart
```

Other examples:

```bash
python -m credit_peer 097950.KS 271560.KS 004370.KS          # tickers on the command line
python -m credit_peer --file peers/kr_food.txt --include-st-investments
python -m credit_peer --file peers/kr_food.txt --max-leverage 3.5 --min-coverage 3
python -m credit_peer --file peers/kr_food.txt --out output/kr_food.csv
```

| Option | Default | Description |
|---|---|---|
| `tickers` | | Tickers separated by spaces |
| `-f, --file` | | Text file, one ticker per line, `#` for comments |
| `-o, --out` | `output/credit_peer_comparison.xlsx` | `.xlsx` or `.csv` |
| `--chart [PATH]` | off (`output/net_debt_to_ebitda.png`) | Net debt / EBITDA bar chart |
| `--max-leverage` | 4.0 | Flag threshold, illustrative |
| `--min-coverage` | 2.0 | Flag threshold, illustrative |
| `--include-st-investments` | off | Include short-term investments in cash |

## Output

- **Console:** company list (FY end, currency, EBITDA basis), metric table with
  `value (rank)`, peer median row, flags, warnings, and the reason for every N/A.
- **Excel workbook:**
  - `Summary`: one row per company with FY end, currency, cash basis, source amounts,
    computed amounts, ratios, ranks, flags, and a peer-median row
  - `Source items`: one row per company × line item, with the value, the statement and
    yfinance label it came from, or why it is missing. Use this sheet to check against filings
  - `Peer stats`: median, min, max and number of peers with data for each ratio
  - `Notes`: run time, settings, definitions, warnings, per-company notes
- **CSV** (if `--out` ends in `.csv`): the summary plus a notes column.
- **Chart** (with `--chart`): net debt / EBITDA by company, with the example threshold and
  the peer median.

## Example output

<!-- Paste the console output of your own run here, with the run date. -->

## Data source and limitations

- **Data comes from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance)**,
  an unofficial library. Yahoo standardises statements, so figures can differ from the
  original filing. For example, Yahoo's "Operating Income" for a Korean company may not equal
  the 영업이익 reported under K-IFRS. **Check against the original filing (DART / SEC)
  before relying on any number.** The `Source items` sheet also shows "Operating income as
  reported" where Yahoo provides it, to help with that comparison.
- **Latest annual figures only.** No trailing-twelve-months (TTM) view, no trend.
- **No adjustments.** One-off items, acquisitions and disposals are not adjusted for.
  Loan agreements usually define their own "Adjusted EBITDA" and net debt, so covenant
  figures will differ.
- **Listed companies only.** Most acquisition finance targets are private; their figures
  would have to come from audited accounts.
- **Small peer groups** make medians and ranks less informative.
- yfinance can be rate-limited or change; if a fetch fails, the error is shown in the notes.

## Tests

The tests run offline on mock statements shaped like yfinance output, and check every
formula against hand-calculated values, the N/A rules, alias matching, ranks, flags,
warnings, and a full run that writes the Excel, CSV and chart.

```bash
python -m pytest
```

## Project structure

```
credit_peer/
  fetch.py    download statements with yfinance (the only module that uses the network)
  fields.py   find line items via alias lists; record source label or reason for N/A
  metrics.py  metric formulas
  peers.py    peer table, medians, ranks, flags, consistency warnings
  report.py   console table, Excel / CSV, chart
  cli.py      command-line options; runs fetch -> calculate -> compare -> report
peers/kr_food.txt   example peer group (Korean packaged food)
tests/              offline unit tests with mock data
```

## Roadmap

- **DART OpenAPI loader** for Korean companies: K-IFRS figures as filed, choice of
  consolidated or separate statements
- **Manual input (CSV)** for private companies, using the same formulas
- **TTM and multi-year trends** (quarterly data)
- **Covenant monitoring:** compare actual leverage and cover with covenant levels and show headroom
- **Optional FX conversion** for comparing amounts across currencies

## 한국어 요약

기업금융·인수금융 관점에서 상장사의 이익 체력과 상환 능력을 동종 기업과 비교하는 Python 도구입니다.
티커 목록을 넣으면 yfinance로 최근 회계연도의 손익계산서·재무상태표·현금흐름표를 불러와 EBITDA(영업이익 + 감가상각비),
EBITDA 마진, 영업이익률, 순차입금/EBITDA, 이자보상배율을 원천 항목에서 직접 계산하고, 지표별 동종 중앙값과 순위,
예시 기준(4.0x, 2.0x — 실제 신용 기준이 아님)에 따른 검토 플래그를 콘솔·Excel(CSV)·차트로 출력합니다.
값이 없으면 추정하지 않고 N/A와 사유를 남기며, 각 기업 행에 회계기간 종료일·통화·원천 항목 값과 출처 항목명을 함께 기록해
원문 공시(DART 등)와 대조할 수 있게 했습니다. AI는 코드 작성과 테스트 보조에만 사용했고, 수치를 만들거나 수정하지 않습니다.
yfinance 데이터는 원문 공시와 다를 수 있으므로 판단 전 반드시 원문을 확인해야 합니다.

## Disclaimer

For education and illustration only. Not investment, credit or legal advice.
