# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

### Added

- *（本次无新增功能）*

### Fixed

- **回归测试修复**：修复 P1-3f 函数重命名残留在 9 个测试文件中的 7 类共 41 个测试失败
  - `test_fund_performance.py`：`fp._is_fund()` → `fp.is_fund()`（9 处）
  - `test_tui_handlers.py`：`_timing_records` → `timing_records`（20+ 处）
  - `test_log_sanitize.py`：`_call_claude` → `call_claude`（2 处）
  - `test_news_correlation.py`：mock target `enhance_news_correlation` → `generators_orchestrator.run_news_correlation_safe`
  - `test_penetration.py`：可转债 `110059` 重分类 `IGNORE` → `ETF`（P2-3 行为变更，更新 2 个测试断言）
  - `test_html_builders_edge.py`：mock target `providers.akshare_extras.*` → `fetcher.akshare.*`
  - `test_fund_style_analysis.py`：mock target `providers.eastmoney_industry.fetch_industry` → `fetcher.industry.fetch_industry_data`，返回值由 `str` 调整为 `dict`

### Changed

- *（本次无变更）*

### Docs

- **requirements.md**：修复 R-CCH-27 编号重复（缓存分组/指纹区段全体顺移）
- **technical.md**：附录 C 自完备化——移除对需求文档的 TTL 引用，改为直接填充具体数值（price/index 24h/盘中30s、news/sector_flow 15min、LLM 2h/1h/24h 等 22 项）
- **changelog.md**／**archived_changelog.0.5.x.md**／**review-findings.md**／**archived_review-findings.0.5.x.md**：v0.5.x 变更记录与自审记录归档迁移


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.10（2026-07-14 ~ 2026-07-15）共 11 个版本。
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
