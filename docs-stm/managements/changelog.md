# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.8.11-dev] - 2026-07-30

### 修复

- **回归测试：4 个穿透测试 mock 失效** — `compute_penetration_top10` 已重构为 Phase 1(`batch_fetch_industry_data`)/Phase 3(`_apply_industry_data`) 实时 API 流程，旧 mock `_enrich_with_industry_api` 处于死代码路径不再被调用，导致返回真实行业数据覆盖关键字分类。改为 mock `batch_fetch_industry_data` 返回空字典，让 sector 保持关键字分类结果。（`test_penetration_core.py`、`test_scenario_penetration_basic.py`）
- **回归测试：`test_llm_content_none_when_disabled` 顺序依赖失败** — `_render_llm_module_info` 在所有条件下均读取全局 `LLM_MODULE_FAILURE`，前序测试（test_llm_all_fail）设值后污染状态导致 module_disabled 出现非预期值。增加 `patch("src.python.llm.prompts.LLM_MODULE_FAILURE", {})` 隔离。（`test_llm_disabled.py`）
- **文档引用修复** — testplan.md 中 `test_scenario_penetration.py` 和 `test_cache.py` 引用已拆分的旧文件名，how-to-test-my-code.md 中示例同样引用已删除的 `test_cache.py`；technical.md 中"30 个数据模块"（实际 29）数字错误；folders.md 测试代码行数、脚本行数等统计更新，目录树补充缺失的 `check-history-traces.py`、`test_data_source_matrix.py`、`test_excel_b_series.py`、`test_pipeline_utils.py` 并修复 `batch-parallel-iteration-plan.md` 缩进错位。全部已修正。

### 重构

- **测试文件重命名 — `scenario/llm/`（7 文件）**：`test_s11_mixed_cache.py` → `test_llm_mixed_cache.py`、`test_s12_all_fail.py` → `test_llm_all_fail.py`、`test_s13_extended_thinking.py` → `test_llm_extended_thinking.py`、`test_s14_llm_disabled.py` → `test_llm_disabled.py`、`test_s15_disabled_cache.py` → `test_llm_disabled_cache.py`、`test_s16_network_error.py` → `test_llm_network_error.py`、`test_s17_partial_cache.py` → `test_llm_partial_cache.py`
- **`test_llm_scenarios_misc.py` 拆分（→ 4 文件）**：拆为 `test_llm_empty_holdings.py`（S18-S19）、`test_llm_output_consistency.py`（S20）、`test_llm_non_trading_day.py`、`test_llm_multi_account.py`，原文件删除
- **测试文件重命名 — 其余 6 文件**：`scenario/basic/test_integration.py` → `test_scenario_basic_flows.py`、`scenario/resilience/test_integration_scenarios.py` → `test_scenario_resilience_flows.py`、`unit/llm/test_prompts.py` → `test_llm_prompt_builders.py`、`unit/llm/test_session.py` → `test_llm_session_usage.py`、`unit/llm/test_cache_multi.py` → `test_llm_cache_multi.py`、`unit/analysis/test_scenario.py` → `test_scenario_analysis.py`
- **删除冗余单体测试文件（4 文件）**：删除 `test_cache.py`（1261 行，内容已迁移至 `test_cache_core.py`/`test_cache_cleanup.py`/`test_cache_format.py`/`test_cache_edge.py`）、`test_penetration_core.py`（561 行）和 `test_penetration_portfolio.py`（575 行，内容已迁移至 `test_scenario_penetration_basic.py`/`test_scenario_penetration_advanced.py`/`test_scenario_penetration_mixed.py`/`test_scenario_penetration_edge.py`）、`test_scenario_penetration.py`（30 行，空壳转发文件）

### 新增

- **`test_cache_core.py` 新增测试类**：增加 `TestGetTTL`（10 项：配置读取/未知类型/默认值/零值/负数/异常兜底）、`TestGetCacheDir`（2 项：绝对路径/cache 后缀）、`TestCacheConstants`（3 项：DAILY/WEEKLY/MONTHLY 常量值），原 `test_cache.py` 中重复内容已清理
- **`test_tui_handlers.py` 注释规范化**：将所有"新增测试 — Xxx"注释改为"Xxx 测试"描述性标题，消除遗留开发标记

### 杂项

- 同步更新 `testplan.md`、`test-coverage.md`、`how-to-test-my-code.md`、`folders.md` 中所有文件引用、统计数字和 Sxx 注释
- 更新各重命名文件的 docstring 运行命令

## 归档

- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

