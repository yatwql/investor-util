# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

### Added

- *（本次无新增功能）*

### Fixed

- **P1-3e: tui_handlers.py/tui_menu.py 私有符号跨包导入** — 完成 5 个消费者文件的内部调用点同步（handlers_cache.py、handlers_config.py、handlers_report.py、main.py、tui_handlers.py），修复因 import 已改但调用点未更新导致的潜在 NameError
- **P1-3f: LLM 模块私有符号跨包导入** — 全局重命名 pricing.py（`_CURRENCY_SYMBOLS`→`CURRENCY_SYMBOLS`、`_PRICING_CURRENCY`→`PRICING_CURRENCY`、`_reload_pricing`→`reload_pricing`、`_estimate_cost`→`estimate_cost`）、prompts.py（`_LLM_MODULE_FAILURE`→`LLM_MODULE_FAILURE`、`_CACHE_PREFIX_LLM`→`CACHE_PREFIX_LLM`）、skeleton.py（4 函数去 `_` 前缀）、fingerprint.py（5 函数去 `_` 前缀）、session.py（`_track_session_usage`→`track_session_usage`、`_record_per_module`→`record_per_module`）、api_base.py（`clear_last_llm_failure`、`LLM_TIMEOUT`、`CACHE_LINE_HTML`、`call_llm_with_retry`）、api.py（5 函数去 `_` 前缀）、markdown.py（`_markdown_to_html`→`markdown_to_html`），同步 8 个消费模块的导入与调用点
- **P1-3f 补漏：api_base.py 定义名未同步** — `_call_llm_with_retry`→`call_llm_with_retry`、`_AUTO_INCREASE_FACTOR`→`AUTO_INCREASE_FACTOR`、`_TRUNCATION_MARKER`→`TRUNCATION_MARKER`，三项定义仍带下划线但消费者已按公开名导入，修复 `__all__` 与内部引用
- **requirements.md 重复 TTL 条目** — R-CCH-25/R-CCH-26 存在两份内容完全相同的条目，删除重复区块
- **Excel 报告组合历史走势页签运行时崩溃** — `excel_generator.py` 在 P1-3d 重命名后遗漏 `write_data_row` 导入导致 `NameError`，已在两个局域 import 块中补充

### Changed

- *（本次无变更）*

### Docs

- **technical.md 函数名引用同步** — `_fetch_with_fallback()`→`fetch_with_fallback()`（6 处）、`_fetch_with_incremental_fallback()`→`fetch_with_incremental_fallback()`（4 处）、`_generate_llm_module`→`generate_llm_module`、`_call_llm()`→`call_llm()`、`_select_holdings_file()`→`select_holdings_file()`
- **拆分 datasource-and-folders.md** — 原文件分解为两个独立文档：`docs-stm/manuals/datasource.md`（用户文档，数据源一览表）和 `docs-stm/managements/folders.md`（管理文档，目录结构树）。同步更新 CLAUDE.md 文档列表和目录树同步指、README.md 链接、testplan.md 引用


## [0.5.6] - 2026-07-15

### Added

- **组合历史走势 — 基准指数对比（Iter I）**：详见 [v0.5.x 归档](../archive/v0.5.x/archived_changelog.0.5.x.md)

### Docs

- **版本发布**：v0.5.6，完整变更记录已归档至 [archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.6（2026-07-14 ~ 2026-07-15）共 7 个版本。
>
> **v0.4.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.4.x/archived_changelog.0.4.x.md](../archive/v0.4.x/archived_changelog.0.4.x.md)。
> 涵盖 v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）共 5 个版本。
>
> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.3.x/archived_changelog.0.3.x.md](../archive/v0.3.x/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）共 8 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.2.x/archived_changelog.0.2.x.md](../archive/v0.2.x/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/v0.1.x/archived_changelog.0.1.x.md](../archive/v0.1.x/archived_changelog.0.1.x.md)。
