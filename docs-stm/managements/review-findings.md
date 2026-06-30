# 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.44 fix: _cmd_update_basic_cache 拆解 + test_fund.py 新增 + docs 审计）

---

## 审查记录（摘要）

| 日期 | 审查范围 | 类型 |
|------|---------|------|
| 2026-06-26 | 需求/实现计划/测试计划 | 完整性/可行性/覆盖度审查 |
| 2026-06-27 | HTML 报告引擎、新闻模块、全量文档 | 三次全量审计 + 修正 |
| 2026-06-27 | 性能审计、死代码清理、LLM 优化、缓存增强 | 优化审查 |
| 2026-06-27 | 类型安全审计、空安全审计 | 代码审查 |
| 2026-06-28 | LLM 财经新闻热点与持仓关联分析、关键词富化、行业分类增强 | 实现审查 |
| 2026-06-28 | 全量文档第七次审计（五文档一致性） | 一致性审查 |
| 2026-06-28 | akshare 盈利预测 + 行业资金流向 + 分红历史集成；内存缓存层；batch 新闻 LLM 分析 | 实现审查 |
| 2026-06-29 | 持仓体检报告（持仓体检报告）— generate_health_check、4 维度评分逻辑、2h 缓存策略、排除行情指纹 | 实现审查 |
| 2026-06-29 | 穿透深度分析（穿透深度分析）— generate_penetration_deep_analysis、行业集中度/国别暴露、24h 缓存策略、排除行情指纹 | 实现审查 |
| 2026-06-29 | 全配置审计 — config.json / llm_settings.json / llm_key.json 冗余、冲突、缺失检查；README / requirements / plan / changelog 四文档同步 | 综合审计 |
| 2026-06-30 | 智能预警（行业资金流向联动 + 新闻情绪聚合）— early_warning.py、P1 代码优化（cache/fetcher/prompts） | 实现审查 |
| 2026-06-30 | 全量文档审计 — 冗余内容清理、冲突修复（plan.md D 标记/README 12 页签/requirements 新章节/technical 目录同步） | 综合审计 |
| 2026-06-30 | 代码审查 — A~F 硬编码名 registry 替换、P 生成器共享骨架、未使用 import 清理 | 代码审查 |
| 2026-06-30 | 代码审查 — 非 LLM 分析章节名注册化、指纹函数合并、news_correlation 批量模式纳入共享骨架、TUI 摘要标题统一、`_CONTENT_FILTER_RECOVERY` 导出清理 | 代码审查 |
| 2026-06-30 | generators.py 拆分 skeleton.py、价格缓存 market-hours 感知 TTL、JSON 注释支持、llm_settings 分组、market_hour 官方 API 获取、TUI LLM 跳过/失败区分 | 实现审查 |
| 2026-07-01 | _read_llm_settings JSON 注释回归修复、_cmd_generate_full 提取 _process_llm_news_futures、菜单 S 文档同步 | 缺陷修复 |
| 2026-07-01 | 全量审查：测试缺口审计、_cmd_update_basic_cache 大函数识别、plan.md 迭代计划缺失、docs 一致性 | 综合审查 |
| 2026-07-01 | R-014 _cmd_update_basic_cache 提取 + R-015 test_fund.py 新增 + plan.md 代码质量方向 + docs 同步 | 缺陷修复/测试新增 |

---

## 待办事项

### [R-014] _cmd_update_basic_cache 大函数拆分 ✅

- **类型**：可维护性
- **文件**：`src/python/tui_handlers.py`（~1080 行）
- **描述**：提取 `_refresh_one_fund_cache()`、`_refresh_profit_forecast_cache()`、`_refresh_sector_flow_cache()`、`_print_cache_refresh_report()` 四个模块级函数。`_refresh_common_caches()` 复用提取函数并返回 `(pf_ok, sf_ok)`。`_cmd_update_basic_cache` 从 130 行降至 67 行（-48%）。
- **状态**：P2 — ✅ 已修复（2026-07-01）

### [R-015] 测试覆盖缺口 ◐（部分完成）

- **类型**：测试
- **文件**：`fetcher/fund.py`（已覆盖）、`llm/api.py`、`report/excel_generator.py` 等
- **描述**：新增 `src/test/test_fund.py`（19 项测试，覆盖基准三层策略、HTML 解析、per-code 锁、config 合并）。`llm/api.py`（熔断/重试/回退/截断）、`report/excel_generator.py`（18 个页签写入）仍缺乏独立单元测试。
- **状态**：P3 — 部分完成（test_fund.py 已新增，其余待后续增补）

### [R-016] plan.md 迭代计划未包含当前代码质量方向 ✅

- **类型**：文档
- **文件**：`docs-stm/managements/plan.md`
- **描述**：plan.md 的"下一步迭代计划"只有 B/C/F 三个远期业务方向，未包含当前的代码质量优化（大函数拆分、测试补全、文档审计等）迭代规划。已新增「A. 代码质量持续优化」方向。
- **状态**：P3 — ✅ 已修复（2026-07-01）

### [R-009] tui_handlers.py God 对象 ◐（部分完成）

- **类型**：架构/可维护性
- **文件**：`src/python/tui_handlers.py`（~1080 行）
- **描述**：已提取 `_prepare_holdings()`、`_finish_report()`、`_fetch_prices_and_indices()`、`_read_llm_settings()`、`_write_llm_settings()`、`_process_llm_news_futures()`、`_refresh_one_fund_cache()`、`_refresh_profit_forecast_cache()`、`_refresh_sector_flow_cache()`、`_print_cache_refresh_report()` 共享函数，`_cmd_generate_full` 136 行、`_cmd_update_basic_cache` 67 行。仍有 `_cmd_generate_full`（136 行）可继续拆分。
- **状态**：P3 — 部分完成（_cmd_generate_full 待继续）

### [R-010] cache.py 大函数拆分 ◐（部分完成）

- **类型**：可维护性
- **文件**：`src/python/cache.py`
- **描述**：已提取 `_read_cache_data()` 统一处理 gzip/非 gzip 读取，`get()` 从 67 行缩减至 33 行，`cleanup_expired` 复用同一辅助函数。`_is_market_open`（75 行）、`check_and_refresh_caches`（68 行）、`set`（57 行）仍可进一步提取。
- **状态**：P3 — 部分完成（get/cleanup_expired 已简化，其余待增量处理）

<!-- 已完成：v0.2.43 = R-012(_read_llm_settings JSON 注释) 回归修复 + _cmd_generate_full 提取 _process_llm_news_futures + 管理文档同步 -- 此前 R-011~R-013 已在 v0.2.42 完成 -->


