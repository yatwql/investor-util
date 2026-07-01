# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.50 — P1 大函数拆分全部完成 + 缓存 TTL 盘中感知缺陷修复 + HTML 报告 LLM 章节按需隐藏）

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
| 2026-07-01 | **R-026 ✅ `write_fund_performance_sheet` 拆分（164→55行）**、**R-027 ✅ `write_summary_sheet` 拆分（163→43行）** | 代码质量修复 |
| 2026-07-01 | **R-028 ✅ `build_news_data` 拆分（159→60行）**、**R-029 ✅ tiantian.py 三大函数全部分解**（fetch_fund_holdings/fetch_quarterly_holdings/fetch_fund_rankings，提取12个辅助函数） | 代码质量修复 |
| 2026-07-01 | **R-030 ✅ skeleton.py 两大函数拆分**：`_generate_llm_content`（136→43行）提取 3 个辅助函数；`_run_batch_mode`（112→57行）提取 2 个辅助函数 | 代码质量修复 |
| 2026-07-01 | **R-031 ✅ test_tiantian.py 新增 39 项**（8 个纯函数测试）、**R-032 ✅ test_skeleton.py 新增 9 项**（`_is_llm_module_enabled` + 导入验证）。全量 1264 测试通过。 | 测试覆盖 |
| 2026-07-01 | **全量文档一致性审计**：修复 5 处不一致（how-to-start.md 菜单 S 穿透深度分析状态、requirements.md/testplan.md 日期、datasource-and-folders.md/technical.md 测试数表述） | 文档审计 |
| 2026-07-01 | **datasource-and-folders.md 目录结构完善**：补全 `.gitignore` 描述、5 个 `__init__.py` 描述、修正 `data/config/` 树形符号 | 文档完善 |
| 2026-07-01 | **全量AST扫描审查**：8个剩余大函数、测试缺口分析、`llm/__init__.py` 过度导出（~60个私有符号）、静默异常清零确认 | 综合审查 |
| 2026-07-01 | **新一轮全量审查** — 8个大函数定位、测试缺口（http_client/market_hours/llm子模块）识别、P3代码治理（__init__.py导出/html_writer文件拆分） | 综合审查 |

---

## 待办区

### P0 — 基础设施测试覆盖（当前迭代）

| 编号 | 模块 | 问题 | 状态 |
|------|------|------|------|
| R-033 | `http_client.py` | 缺少专用单元测试 — HTTP 客户端工厂，所有 provider 共用 | ✅ 17项覆盖 |
| R-034 | `market_hours.py` | 缺少专用单元测试 — 交易时段判断核心，影响缓存 TTL 和报告日期 | ✅ 41项覆盖 |

### P1 — 大函数拆分

| 编号 | 文件:函数 | 行数 | 问题 | 状态 |
|------|----------|------|------|------|
| R-035 | `report/news_correlation.py:_build_keyword_lookup` | 119 | 关键词查找构建 | ✅ 提取6个辅助函数，核心降至28行 (2026-07-01) |
| R-036 | `report/category.py:write_category_sheet` | 124 | 分类汇总表写入 | ✅ 提取3个辅助函数，核心降至58行 (2026-07-01) |
| R-037 | `llm/generators.py:enhance_news_correlation` | 128 | 新闻 LLM 分析核心，含批处理逻辑，可拆分 | ✅ 提取5个辅助函数，核心降至35行 (2026-07-01) |
| R-038 | `llm/api.py:_call_llm_with_retry` | 114 | LLM 调用重试核心 | ✅ 提取2个辅助函数，核心降至75行 (2026-07-01) |
| R-039 | `report/news_correlation.py:write_news_sheet` | 113 | 新闻工作表写入 | ✅ 提取3个辅助函数，核心降至48行 (2026-07-01) |
| R-040 | `report/html_writer.py:_build_perf_data` | 107 | HTML 性能数据构建 | ✅ 提取_build_single_perf_item，核心降至27行 (2026-07-01) |
| R-041 | `providers/news_aggregator.py:aggregate_news` | 106 | 多源新闻聚合 | ✅ 提取4个辅助函数，核心降至27行 (2026-07-01) |
| R-042 | `report/penetration.py:write_penetration_sheet` | 105 | 穿透分析表写入 | ✅ 提取3个辅助函数，核心降至40行 (2026-07-01) |

### P2 — 补充模块测试

| 编号 | 模块 | 风险 | 说明 | 状态 |
|------|------|------|------|------|
| R-043 | `llm/circuit_breaker.py` | 🟡 中 | 熔断器，仅在 test_api.py 间接覆盖 | 待处理 |
| R-044 | `llm/fingerprint.py` | 🟡 中 | 缓存指纹计算 | 待处理 |
| R-045 | `llm/pricing.py` | 🟢 低 | 定价计算 | 待处理 |
| R-046 | `llm/markdown.py` | 🟢 低 | Markdown→HTML 转换 | 待处理 |
| R-047 | `providers/eastmoney_news.py` | 🟢 低 | 东方财富新闻 provider | 待处理 |
| R-048 | `providers/sina_news.py` | 🟢 低 | 新浪新闻 provider | 待处理 |
| R-049 | `providers/wallstreetcn_news.py` | 🟢 低 | 华尔街见闻 provider | 待处理 |

### P3 — 代码治理

| 编号 | 问题 | 说明 | 状态 |
|------|------|------|------|
| R-050 | `llm/__init__.py` 过度导出 | 从 6 个子模块 re-export ~60 个私有符号（`_` 前缀），既是公共 API 又暴露内部实现 | 待处理 |
| R-051 | `report/html_writer.py` 文件偏大 | 792 行，虽已拆分函数，但文件整体仍可考虑按章节拆分 | 待处理 |
| R-052 | `report/penetration.py` 文件偏大 | 715 行，穿透逻辑与 Excel 写入混合 | 待处理 |
| R-053 | `requirements.txt` 缺少锁定版本 | 仅有 5 个顶层依赖，无可复现锁定文件 | 待处理 |
