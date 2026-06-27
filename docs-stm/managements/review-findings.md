# 自我审查问题记录

创建日期：2026-06-26

---

## 审查记录

| 日期 | 审查对象 | 审查类型 | 审查人 | 状态 |
|---|---|---|---|---|
| 2026-06-26 | 需求文档 `requirements.md` | 完整性审查 | 自审 | ✅ 已通过 |
| 2026-06-26 | 实现计划 `plan.md` | 可行性/一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-26 | 测试计划 `testplan.md` | 覆盖度审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | HTML 报告引擎 (Iter 3.1) | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 财经新闻关联模块 (Iter 3.2) | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 五文档全量审计 | 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | output_dir + 菜单重构 | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | `news_top_count` 可配置 + TOP 50→100 | 配置一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 基金业绩评价标色（Excel+HTML）+ 汇总页美股指数键名修复 | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 六文档全量第二次审计 | 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 模块 7/8 模板占位 + 缓存管理增强 + 异常处理增强 | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 七文档全量第三次审计 + plan.md Iter 3.3/3.4 文件结构修正 | 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 穿透模块板块分类 + 失败基金明细 + 8 文档全量第四次审计 | 实现正确性 + 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 文档冗余精简：CLAUDE.md 精简目录树/去重、5 文档一致性修复 | 一致性审查 + 去冗余 | 自审 | ✅ 已通过 |
| 2026-06-27 | 全量问题修复 + 文档最终核对 | 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 全面性能审计与并行化改造（菜单[1][2]/新闻/LLM 多线程） | 性能审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 死代码审计与清理（exists/fetch_fund_type/3 新浪死函数/llm_content else 分支） | 代码审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | LLM 优化：Prompt 压缩 230 字/Token 追踪/并行缓存预检/万亿单位压缩 | 优化审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 缓存策略增强：新闻 15min 缓存/mtime 配置缓存/HTML 直存 | 优化审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 多文档全量第五次审计 + v0.2.8 文档同步 | 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 全量代码类型与安全审计（html_writer list→dict + fund_performance JSON null） | 代码审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | 全量代码二次类型审计（summary.py write_summary_sheet list→dict + fund_performance _adjust_rating_with_benchmark None） | 代码审查 | 自审 | ✅ 已通过 |
| 2026-06-27 | v0.2.8 全量文档与代码一致性确认（5 文档审计 + 类型/空安全修正验证） | 一致性审查 | 自审 | ✅ 已通过 |
| 2026-06-28 | v0.2.9 LLM 新闻关联分析 + 缓存清理补全 + HTML 模板更新 | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-28 | v0.2.10 关键词富化（持仓/穿透/行业三种类型）+ Excel 格式优化 + HTML 模板同步 | 实现正确性审查 | 自审 | ✅ 已通过 |
| 2026-06-28 | 六文档全量第六次审计（requirements.md/README.md/changelog.md/testplan.md/review-findings.md/CLAUDE.md） | 一致性审查 + 去冗余 | 自审 | ✅ 已通过 |

---

## 发现问题

### [R-001] 备用 API 链路端点需明确具体 URL 路径

- **发现日期**：2026-06-26
- **审查对象**：`plan.md` / Iter 1.3
- **类型**：信息不完整
- **描述**：计划中提及"备用链路自动切换"，但未明确各链路的 API 端点格式和响应格式，实施者需自行调研
- **状态**：✅ 已修复（已补充具体端点到 plan.md 的 API 路由表）
- **修复日期**：2026-06-26

### [R-002] 持仓 xlsx 输入列名未定义

- **发现日期**：2026-06-26
- **审查对象**：`plan.md` / Iter 1.2
- **类型**：信息缺失
- **描述**：未定义持仓 xlsx 的预期列名和数据类型，用户无法准备兼容的输入文件
- **状态**：✅ 已修复（已添加 xlsx 列名映射表到 plan.md）
- **修复日期**：2026-06-26

### [R-003] 多处死代码残留（已清理）

- **发现日期**：2026-06-27
- **审查对象**：`src/` 全量代码审计
- **类型**：死代码
- **描述**：多模块存在已废弃但未清理的函数和 import：cache.exists()、tiantian.fetch_fund_type()、sina_news 3 个死函数、llm_content.write_llm_sheets 12 个冗余参数及 ~60 行死分支、main.py portfolio_items 字典及未使用 import
- **状态**：✅ 已修复（详见 changelog v0.2.8 Removed 章节）
- **修复日期**：2026-06-27

### [R-004] html_writer.py a_indices/us_indices 类型不匹配（潜在运行时崩溃）

- **发现日期**：2026-06-27
- **审查对象**：`src/report/html_writer.py`
- **类型**：类型不匹配
- **描述**：`fetch_indices()` 返回 `dict[str, dict[str, Any]]`，但 html_writer.py 在 write_html_report() 中将结果转为 `list[dict]` 传入 `generate_all_llm()`。该函数签名声明参数为 `dict` 并调用 `.values()`，列表无此方法将引发 `AttributeError`。当前路径仅在 `enable_llm=True` 且 `llm_content=None` 时触发（main.py 调用时传入 `llm_content` 走另一分支），属于潜在缺陷。
- **状态**：✅ 已修复（保留 dict 原始类型传 LLM，模板渲染使用独立 list 变量）
- **修复日期**：2026-06-27

### [R-005] fund_performance.py 对 API JSON null 值缺少防护

- **发现日期**：2026-06-27
- **审查对象**：`src/report/fund_performance.py`
- **类型**：空安全缺陷
- **描述**：`perf_eval.get("categories", [])` 在 JSON 中存在显式 `null`（如 `{"categories": null}`）时返回 `None` 而非 `[]`，随后 `enumerate(categories)` 引发 `TypeError`。同理 `scores` 在 `len(scores)` 处崩溃。涉及 _calc_rating_comment 和 _adjust_rating_with_benchmark 两处。
- **状态**：✅ 已修复（`.get()` 后使用 `or []` 兜底确保始终为可迭代对象）
- **修复日期**：2026-06-27

### [R-006] summary.py write_summary_sheet 接收 list 而非 dict 导致崩溃

- **发现日期**：2026-06-27
- **审查对象**：`src/report/summary.py` + 调用方
- **类型**：类型不匹配
- **描述**：`fetch_indices()` 返回 `dict[str, dict[str, Any]]`，但调用方在传入 `write_summary_sheet()` 前错误将 dict 转为 list（如 `list(fetch_indices())`），导致函数内 `a_indices.get(code)` 引发 `AttributeError`。与 R-004 同属一类类型不匹配问题，但涉及不同模块（summary.py 而非 html_writer.py）。
- **状态**：✅ 已修复（保留 dict 原始类型传递）
- **修复日期**：2026-06-27

### [R-007] fund_performance.py _adjust_rating_with_benchmark 对 API JSON null 缺少防护

- **发现日期**：2026-06-27
- **审查对象**：`src/report/fund_performance.py`
- **类型**：空安全缺陷
- **描述**：`_adjust_rating_with_benchmark` 中 `perf_eval.get("categories")` 在 JSON 中存在显式 `null`（如 `{"categories": null}`）时返回 `None` 而非 `[]`，随后 `enumerate(categories)` 引发 `TypeError`。与 R-005 属同类 API null 问题，但影响函数为 `_adjust_rating_with_benchmark`（评级修正专用），且循环中 `if cat and ("超额" in cat ...)` 在 cat 为 None 时同样会因 `in` 操作于 NoneType 上崩溃。
- **状态**：✅ 已修复（`.get()` 后使用 `or []` 兜底确保始终为可迭代对象）
- **修复日期**：2026-06-27

---

## 待处理问题

当前无待处理问题。

---

## 迭代结束审查清单

每迭代完成后，对照以下清单进行审查：

- [x] Iter 1 全部功能已实现（项目骨架、TUI、数据源、Excel 输出）
- [x] Iter 2 全部功能已实现（分类汇总、穿透 TOP10、基金业绩）
- [x] Iter 3.1 已实现（HTML 报告引擎）
- [x] Iter 3.2 已实现（财经新闻关联模块）
- [x] Iter 3.3 已实现（模块 7-8 模板占位 + 缓存管理 [3][4] + 异常处理增强）
- [x] Iter 3.4 已完成（HTML + Excel LLM 模块均已实现）
- [x] Iter 3.5 已完成（LLM 全局优化：并行调用/连接复用/System Prompt 外部可配置/提示词紧凑化）
- [x] Iter 3.6 已完成（全面性能优化与代码清理：并行化/死代码移除/LLM 优化/缓存增强）
- [x] 配置管理含 output_dir 字段，支持菜单 R 配置
- [x] 所有单元测试通过（489 项，覆盖 reader/cache/summary/market_value/fund_performance/penetration/llm_client/config/fetcher/excel_writer/category/news_correlation/models）
- [x] 异常场景测试待完善（已有 test_config/test_fetcher/test_excel_writer/test_category/test_news_correlation/test_models，覆盖度可继续补强）
- [x] API Key 不丢失（config.json 不存明文 key，使用外部文件 data/config/llm.json）
- [x] Excel/HTML 输出文件格式正确
- [x] TUI 菜单功能正常（含 B/L/R 新菜单）
- [x] API 联通性已验证
- [x] 缓存逻辑正确
- [x] 本次迭代发现的问题已记录并分类
