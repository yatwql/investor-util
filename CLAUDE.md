# CLAUDE.md

Guidance for Claude Code when working with this repository.

## Project

Python TUI application that reads personal investment holdings (stocks + funds) from Excel and generates analysis reports in Excel (.xlsx) and/or HTML format. Reports include market value, category summaries, asset penetration, fund performance, news correlation, and LLM-powered macro/risk commentary.

## Conventions

- **UI language**: All Chinese (menu, errors, report content)
- **Logging**: Standard `logging` → `logs/app.log` + console. Levels: INFO (normal), WARNING (API switch/skip), ERROR (non-fatal failure)
- **Tests**: Unittest alongside source (e.g. `src/test_penetration.py`)
- **Management docs**: All in `docs-stm/managements/` — plan.md, requirements.md, testplan.md, review-findings.md, changelog.md

## Holdings xlsx Format

- Each worksheet = one account (tab name = account name, e.g. "证券账户")
- Fixed 4 columns: 名称 (str), 代码 (str), 持仓份额 (float > 0), 每份成本 (float > 0)
- Column mapping is NOT configurable — columns read by fixed name
- Prices (最新价/昨日价) fetched live from APIs, not from spreadsheet

## Source Layout

See `docs-stm/README.md` for the complete directory tree and user-facing documentation.

## LLM Provider Support

`llm_client.py` supports `provider: "claude"` in `llm.json` for Anthropic Messages API (including DeepSeek Anthropic-compatible endpoint at `api.deepseek.com/anthropic/v1/messages`) and `provider: "openai"` for OpenAI Chat Completions API.
