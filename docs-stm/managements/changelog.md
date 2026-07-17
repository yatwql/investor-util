# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [0.6.7] - 2026-07-18

> 31 项测试修复 + extract-test-failures 脚本

### Added

- **脚本**: `scripts/extract-test-failures.py` — 从 pytest-html 报告中快速提取失败/错误测试用例，支持 `--summary` / `--json` 输出
- **调试工具**: `plan.md` 多 LLM Provider 链式服务标记为 **P1-T01**，优先级 P1

### Fixed

- **测试修复（31 项）**:
  - 8 个 LLM Error：移除 `TestEnhanceNewsCorrelation` / `TestEnhanceNewsCorrelationGranularCache` 对 `skeleton.httpx.Client` 的 mock（`httpx` 在 TYPE_CHECKING 下导入，运行时属性不存在）
  - 3 个 `test_fund_style_analysis`：修正 `_push2_extended` mock 字段名（`market_cap` → `f20`）和 Tencent 市值单位（亿→元换算）
  - 2 个 `test_handlers_cache`：mock 路径从旧 `providers.akshare_extras` 更新为 `fetcher.akshare`
  - 2 个 `test_handlers`：同上，mock 路径同步更新
  - 5 个 `test_news_correlation`：`aggregate_news` mock 路径从 `providers.news_aggregator` 更新为 `fetcher.news`
  - 7 个 `TestPrintTimingSummary`：`print_timing_summary()` 注入模块级 `_timing_records` 后清空
  - 4 个页签/导航数量断言：同步 `_REPORT_SECTION_DEFAULT` 新增的 `portfolio_history`/`drawdown_analysis` 模块
  - 1 个 `test_no_prefix_code_is_other`：测试代码从 `600900` 改为 `900900`（`60` 开头被 `is_a_share_code` 识别为 A 股）
  - 1 个 `test_fund_style_analysis` 中 `delete_by_prefix` → `clear_by_prefix`（前者不存在）
- **路径绝对化后遗症修复**: `test_config.py` / `test_config_atomic_edge.py` / `test_config_firstrun_edge.py` / `test_security_edge.py` 中 9 处路径断言适配绝对路径
- **`_extract_model_from_cached` 恢复**: Gemini 编辑期间被误删的函数定义已恢复

### Changed

- **`tui_handlers.py`**: `print_timing_summary()` 在调用 reporter 后清空 `_timing_records`，避免测试间污染

> **v0.6.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.6.x/archived_changelog.0.6.x.md](../archive/v0.6.x/archived_changelog.0.6.x.md)。
> 涵盖 v0.6.0 ~ v0.6.6（2026-07-15 ~ 2026-07-17）共 7 个版本。

> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）共 13 个版本。

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
