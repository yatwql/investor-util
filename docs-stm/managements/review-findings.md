# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.48 — R-025 ✅ 已完成，R-026~R-032 P3 待处理）

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
| 2026-07-01 | cache.py _is_market_open 拆解 + R-009 tui_handlers 完成 + R-010 cache 完成 | 代码质量修复 |
| 2026-07-01 | R-015 P3 延期，test_fund.py 已覆盖，其余后续迭代补充 | 延期决策 |
| 2026-07-01 | 全部已修复问题移出待办区，review-findings.md 待办区清空 | 文档清理 |
| 2026-07-01 | **R-015 ✅ 已完成** — test_api.py（44 项，含 HTTPStatusError 修复）+ test_excel_generator.py（15 项，重写 mock 策略）+ progress.py 基类错误存储修复 + reports-instruction.md LLM API 用量章节更新 | 测试覆盖完成 |
| 2026-07-01 | 全量检查：technical.md 测试文件数 30→34 未更新、tui_handlers.py 1147 行文件偏大、cache.py 交易时间逻辑可提取 | 优化审查 |
| 2026-07-01 | **汇总页移除【LLM 用量】区块**、**LLM API 用量页签排版优化**（增加区域标题、图例、间距） | 体验改进 |
| 2026-07-01 | **R-018 ✅ tui_handlers.py 拆分**（1147→234 行，拆出 handlers_report/handlers_cache/handlers_config） | 代码质量修复 |
| 2026-07-01 | **R-019 ✅ cache.py 交易时间逻辑提取为 market_hours.py 独立模块** | 代码质量修复 |
| 2026-07-01 | 代码审计：generate_excel_report(296行)/generate_all_llm(224行)/write_llm_usage_sheet(215行)/compute_penetration_top10(199行) 大函数识别；handlers 测试缺口审计 | 优化审查 |
| 2026-07-01 | **R-020 ✅ ～ R-024 ✅ 全部完成** — 4 个大函数拆分（均≤75行）+ handlers 测试 23 项新增，全量 1216 passed | 代码质量修复 |
| 2026-07-01 | 全量审计：AST 扫描大函数（16个>100行）、未使用 import 扫描（28处）、测试缺口分析（tiantian/skeleton 无专用测试）、硬编码名称扫描（~45处） | 综合审计 |

---

## 待处理问题

| 编号 | 问题 | 严重度 | 状态 | 发现日期 |
|:----|------|:------:|:----:|:--------:|
| R-025 | **未使用 import 清理（28 处，12 个文件）**：`cache.py` 3 处、`config.py` 1 处、`handlers_cache.py` 5 处、`handlers_report.py` 10 处、`main.py` 2 处、`market_hours.py` 1 处、`fetcher/chain.py` 1 处、`llm/generators.py` 1 处、`report/market_value.py` 1 处、`providers/` 3 处（其中 `CACHE_WEEKLY`/`CACHE_MONTHLY` 与 `_generate_llm_content` 为便利再导出而非未使用，已保留） | P2 | ✅ v0.2.48 | 2026-07-01 |
| R-026 | **`report/fund_performance.py:write_fund_performance_sheet()`（164 行）**：Excel 页签写入大函数，含表头/数据行/标色/备注四段，可拆分 | P3 | 待处理 | 2026-07-01 |
| R-027 | **`report/summary.py:write_summary_sheet()`（163 行）**：投资分析汇总页签写入，含指数行情/汇总数据/账户小计/备注四段，可拆分 | P3 | 待处理 | 2026-07-01 |
| R-028 | **`report/news_correlation.py:build_news_data()`（159 行）**：新闻获取/关键词匹配/LLM 分析/排序输出四段逻辑可拆分 | P3 | 待处理 | 2026-07-01 |
| R-029 | **`providers/tiantian.py` 三大函数（平均 143 行）**：`fetch_quarterly_holdings`（150）、`fetch_fund_holdings`（143）、`fetch_fund_rankings`（135），含复杂的 JS 变量解析/HTML 多格式处理，可拆分 | P3 | 待处理 | 2026-07-01 |
| R-030 | **`llm/skeleton.py` 两大函数**：`_generate_llm_content()`（136 行）+ `_run_batch_mode()`（112 行），骨干函数含缓存/API/截断重试/格式处理多段逻辑 | P3 | 待处理 | 2026-07-01 |
| R-031 | **`providers/tiantian.py` 缺专用测试**：481 行文件含三大复杂函数，现有 `test_fund.py` 间接覆盖不足 | P3 | 待处理 | 2026-07-01 |
| R-032 | **`llm/skeleton.py` 缺专用测试**：397 行含 2 个大函数，缓存/API/截断重试路径无独立覆盖 | P3 | 待处理 | 2026-07-01 |