# 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.41 fix: God对象/大函数拆分/补充测试/文档审计）

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

---

## 待办事项

### [R-009] tui_handlers.py God 对象 ◐（部分完成）

- **类型**：架构/可维护性
- **文件**：`src/python/tui_handlers.py`（~1050 行）
- **描述**：同时负责用户交互、数据获取编排、报告生成调度，职责过重。已提取 `_prepare_holdings()`、`_finish_report()`、`_fetch_prices_and_indices()`、`_read_llm_settings()`、`_write_llm_settings()` 共享函数，减少重复。仍有 `_cmd_generate_full`（~175 行）、`_cmd_update_basic_cache`（~130 行）等大函数待增量拆分。
- **状态**：P2 — 部分完成（R-012/013 子项已修复，主项待继续）

### [R-010] cache.py 大函数拆分 ◐（部分完成）

- **类型**：可维护性
- **文件**：`src/python/cache.py`
- **描述**：已提取 `_read_cache_data()` 统一处理 gzip/非 gzip 读取，`get()` 从 67 行缩减至 33 行，`cleanup_expired` 复用同一辅助函数。`_is_market_open`（75 行）、`check_and_refresh_caches`（91 行）、`set`（57 行）仍可进一步提取。
- **状态**：P3 — 部分完成（get/cleanup_expired 已简化，其余待增量处理）

### [R-011] 测试覆盖缺口 ✅（已完成）

- **类型**：测试
- **文件**：多个
- **描述**：新增 `test_progress.py`（33 tests）和 `test_session.py`（32 tests）。`fetcher/fund.py`、`fetcher/price.py`、`fetcher/industry.py`、`llm/api.py`、`llm/skeleton.py`、`llm/generators.py` 仍靠集成测试覆盖，边界场景可后续补充。
- **状态**：P3 — ✅ 已修复（2026-07-01）

### [R-012] _cmd_config_llm_modules 职责拆分 ✅（已完成）

- **类型**：可维护性
- **文件**：`src/python/tui_handlers.py`
- **描述**：提取 `_read_llm_settings()` 和 `_write_llm_settings()`，将配置读取/写入与交互菜单分离。
- **状态**：P3 — ✅ 已修复（2026-07-01）

### [R-013] 缓存刷新逻辑重复 ✅（已完成）

- **类型**：架构
- **文件**：`src/python/tui_handlers.py`
- **描述**：提取 `_fetch_prices_and_indices()` 并行获取持仓价格+指数，`_cmd_update_position_cache` 调用之。
- **状态**：P3 — ✅ 已修复（2026-07-01）

<!-- 已完成：v0.2.41（2026-07-01）= write_html_report 拆分 + fund.py 日志 + chain.py 测试 + R-011~R-013 修复 + R-009/R-010 部分完成 -->


