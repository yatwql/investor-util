# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python TUI application that reads personal investment holdings (stocks + funds) from Excel and generates analysis reports in Excel (.xlsx) and/or HTML format. Reports include market value breakdowns, category summaries, asset penetration analysis, fund performance ranking, news correlation, and macro/risk commentary.

## Directory Structure

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── main.py              # TUI entry point
│   ├── config.py             # Config management
│   ├── models.py             # Data models (Holding dataclass)
│   ├── reader.py             # Holdings xlsx parser
│   ├── test_penetration.py   # Asset penetration unit tests
│   ├── cache.py              # API response cache
│   ├── fetcher.py            # Data fetch router
│   ├── logger.py             # Logging setup
│   ├── tui.py               # Keyboard input wrapper
│   ├── providers/            # Financial API providers
│   │   ├── __init__.py
│   │   ├── tencent.py        # Tencent Finance API
│   │   ├── eastmoney.py      # East Money API
│   │   ├── tiantian.py       # Tian Tian Fund API
│   │   └── sina.py           # Sina Finance API
│   └── report/               # Report generation modules
│       ├── __init__.py
│       ├── excel_writer.py
│       ├── styles.py
│       ├── summary.py
│       ├── market_value.py
│       ├── category.py
│       ├── penetration.py
│       └── fund_performance.py
├── data/
│   ├── holdings/             # .xlsx holdings files
│   ├── cache/                # API response cache (JSON)
│   └── config/               # Config files (config.json)
├── logs/                     # Application logs (app.log)
├── reports/                  # Generated reports
│   └── <YYYYMMDD>/           # Archived reports
├── docs-stm/
│   ├── README.md
│   ├── managements/          # Project management docs
│   ├── plan/                 # Plan files
│   └── tmp/                  # Process files & temp files
├── scripts/
│   ├── launch.ps1            # Windows launcher
│   └── launch.sh             # Linux launcher
├── requirements.txt
└── CLAUDE.md
```

## Development Setup

```bash
# Use launcher scripts — they handle venv + deps automatically
.\scripts\launch.ps1    # Windows PowerShell
./scripts/launch.sh     # Linux

# Or manually:
python -m venv .venv
.venv\Scripts\Activate.ps1  # or: source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

## Key Conventions

- **UI language**: All Chinese (menu prompts, error messages, report content)
- **Logging**: Standard `logging` module, output to `logs/app.log` + console
- **Log levels**: INFO (normal flow), WARNING (API switch/data skip), ERROR (non-fatal failure)
- **Tests**: Unittest, test files alongside source modules (e.g. src/test_penetration.py)
- **Management docs**: All in `docs-stm/managements/` — plan.md, requirements.md, testplan.md, review-findings.md, changelog.md

## Holdings xlsx Format

- Each worksheet tab = one account (tab name = account name, e.g. "证券账户")
- Fixed 4 columns: 名称 (str), 代码 (str), 持仓份额 (float > 0), 每份成本 (float > 0)
- Column mapping is NOT configurable — program reads by fixed column name
- Prices (最新价/昨日价) are fetched live from APIs, not from the spreadsheet
