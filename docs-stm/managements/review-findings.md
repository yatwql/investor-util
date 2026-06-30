# 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-06-30（v0.2.40+文档清理）

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

### [R-009] tui_handlers.py God 对象 ❌（待处理）

- **类型**：架构/可维护性
- **文件**：`src/python/tui_handlers.py`（1044 行）
- **描述**：同时负责用户交互、数据获取编排、报告生成调度，职责过重，难以单元测试。6 个函数超过 50 行（`_cmd_generate_full` 196 行、`_cmd_update_basic_cache` 130 行等）。
- **建议方案**：增量拆分 — 每次改到此文件时顺手抽一个函数或一组相关功能到新模块，不安排专门重构迭代。
- **状态**：P2 — 待处理

### [R-010] cache.py 大函数拆分 ❌（待处理）

- **类型**：可维护性
- **文件**：`src/python/cache.py`
- **描述**：`cleanup_expired`（95 行）、`_is_market_open`（75 行）、`check_and_refresh_caches`（68 行）、`get`（67 行）、`set`（57 行）均超过合理长度。`set`/`get` 中包含 gzip 压缩/解压、原子写入、重试逻辑，可提取 `_read_with_decompress()` / `_write_with_compress()` 辅助函数。
- **建议方案**：下次修改 cache.py 时增量提取，每次提取一个辅助函数。
- **状态**：P3 — 待处理

### [R-011] 测试覆盖缺口 ❌（待处理）

- **类型**：测试
- **文件**：多个
- **描述**：以下模块缺少独立单元测试（部分虽被集成测试间接覆盖，但边界场景覆盖不足）：
  - `fetcher/fund.py` — 基金业绩基准 3 层回退解析逻辑
  - `fetcher/price.py` — 价格获取
  - `fetcher/industry.py` — 行业分类获取
  - `llm/api.py` — 重试/熔断/回退核心逻辑（目前靠集成测试覆盖）
  - `llm/skeleton.py` — 共享骨架函数
  - `llm/generators.py` — 生成器函数
  - `llm/session.py` — 会话用量跟踪
  - `report/progress.py` — ProgressReporter 接口
- **建议方案**：按需补充，优先覆盖核心逻辑（api.py/skeleton.py）。
- **状态**：P3 — 待处理

### [R-012] tui_handlers.py _cmd_config_llm_modules 职责混合 ❌（待处理）

- **类型**：可维护性
- **文件**：`src/python/tui_handlers.py`
- **描述**：`_cmd_config_llm_modules`（56 行）混合了配置读取、交互菜单、配置写入三个职责，可拆为 `_read_llm_settings()` → 交互 → `_write_llm_settings()`。
- **建议方案**：下次改到该函数时分步提取。
- **状态**：P3 — 待处理

### [R-013] tui_handlers.py 缓存刷新逻辑重复 ❌（待处理）

- **类型**：架构
- **文件**：`src/python/tui_handlers.py`
- **描述**：`_check_and_warm_for_new_assets`（55 行）与 `_cmd_update_position_cache` 部分逻辑重复（均获取持仓价格和指数），可提取共享的「并行获取持仓价格+指数」辅助函数。
- **建议方案**：下次改到缓存刷新相关函数时提取。
- **状态**：P3 — 待处理

### [已完成 — 2026-07-01] write_html_report 单体函数拆分

- **类型**：可维护性
- **文件**：`src/python/report/html_writer.py`
- **描述**：`write_html_report`（390 行）同时负责 11 个区块的数据准备和渲染，职责过重。
- **处理结果**：拆分为 12 个子函数，主函数降为 ~60 行，各子函数职责明确。详见 changelog.md。

### [已完成 — 2026-07-01] fetcher/fund.py 静默异常加日志

- **类型**：可观测性
- **文件**：`src/python/fetcher/fund.py`
- **描述**：`_fetch_benchmark_from_api` 的 `except: continue` 和 `_get_full_benchmark_table` 的 `except: pass` 静默忽略失败，无日志线索。
- **处理结果**：两处均补充 `logger.debug`。详见 changelog.md。

### [已完成 — 2026-07-01] fetcher/chain.py 单元测试

- **类型**：测试
- **文件**：`src/test/test_chain.py`
- **描述**：Provider Chain 是最核心的回退机制（缓存命中、Provider 遍历、验证、转换、过期缓存降级），此前完全靠集成测试覆盖。
- **处理结果**：新增 23 项单元测试覆盖全部路径。详见 changelog.md。


