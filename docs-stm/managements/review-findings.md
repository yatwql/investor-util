# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-04（v0.2.85 — B 迭代审计：PE 边界条件/excel_writer API 签名风险）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|
| 2026-06-26 ~ 2026-07-01 | 全量需求/架构/代码/测试审计（P1~P2） | ✅ 已完成 |
| 2026-07-01 | P3 代码现代化：旧式 typing / `.format()` / pyproject.toml | ✅ 已完成 |
| 2026-07-01 | 全量场景审计：网络/数据质量/并发/节假日/零成本/首次运行/LLM 等 edge case | ✅ 已完成 |
| 2026-07-01 | 第二波代码级深度审计：12 模块 18 项（P0 CRASH×7、P1 HANG/DATA×5、P2×6） | ✅ 已完成 |
| 2026-07-01 | 第三波：P0 CRASH×4 / P1 HANG×1 / P1 DATA×5 / P1 场景×3 等共 30 项 | ✅ 已完成 |
| 2026-07-01 | R-131~R-132：基金业绩评级百分位冲突 bug + _parse_rank_entry 异常防御 | ✅ 已完成 |
| 2026-07-01 | R-136~R-137：全局 Cache TTL 硬编码审计 | ✅ 已完成 |
| 2026-07-01 | R-138~R-143：P3 死代码/向后兼容代码全局清理 + 全局文档/Cache TTL 一致性审计 | ✅ 已完成 |
| 2026-07-02 | R-144：指数双链路 fallback（A股：腾讯→新浪；美股：新浪→腾讯）+ httpx h2 依赖补全 | ✅ 已完成 |
| 2026-07-02 | R-145：`_handle_truncation` 丢弃 usage 导致 per_module 无数据、HTML 页脚缺失 | ✅ 已完成 |
| 2026-07-02 | R-146：`news_correlation` 遗漏在 LLM 模块明细表（3 文件硬编码 4 模块）| ✅ 已完成 |
| 2026-07-02 | R-147：HTML 模板 `{% if _mi.total_tokens %}` 将 0 显示为 `—` | ✅ 已完成 |
| 2026-07-02 | T-001~T-003：pytest 标记层级体系（19 个分层标记）+ 目录分组搬迁（60 文件）+ 标记插入脚本修复 | ✅ 已完成 |

---

| 2026-07-04 | 全技术债务审计：版本漂移/except Exception 追踪/模板格式统一 | ✅ 已完成 |
| 2026-07-04 | 待观察/优化项（R-149~R-152）：安全隐式依赖/re-export审计/缓存展示/测试时长 | 📋 待决策 |
| 2026-07-04 | B 迭代自审：PE 阈值边界条件 / excel_writer API 签名系统性风险 | 📋 待观察 |
| 2026-07-04 | R-155：Excel 页签排序错位（1-7→13-16→8-11→12）— B 模块插入后未 reorder | 📋 待决策 |

---

## 待处理问题

### [R-149] 新闻富化关键词 `display` 字段隐式安全依赖（低风险）

**发现**：模板第 598 行 `{{ ekw.display }}` 未标记 `|safe`，autoescape 生效防止 XSS。但 display 值来自外部 API（东方财富/新浪），当前安全依赖 autoescape 默认行为，后续若有 `|safe` 添加将暴露 XSS 风险。
**状态**：📋 待观察 — 建议在 html_writer.py 的 render 调用处或模板变量注入前加 sanitize 注释标记。

### [R-150] `llm/__init__.py` re-export 符号审计（低优先级）

**发现**：`llm/__init__.py` 通过 `# noqa: F401` 批量 re-export 了多个模块的符号（`cache_get`、`cache_set` 等），部分可能已无外部调用者。
**状态**：📋 待审计 — 建议每半年或大版本发布前核查一次导出符号的实际使用情况。

### [R-151] 缓存命中率数据未在报告中展示（中低优先级）

**发现**：`cache.py` 已有完善的 `get_cache_hit_rate()` 统计接口，跟踪命中/未命中和命中率，但 HTML 和 Excel 报告均未消费此数据。
**状态**：📋 待决策 — 展示缓存命中率有助于用户判断数据新鲜度，建议在报告页脚或 LLM 用量页签追加。

### [R-152] 测试运行时长的可扩展性关注（中优先级）

**发现**：`unit` 模式已达 1997 项、耗时 ~25min，`verify` 模式 ~12min。虽然 `smoke`（24 项/2s）和 `regression`（222 项/~32s）保持快速，但长期趋势不乐观。
**状态**：📋 待评审 — 设计方案（`docs-stm/plan/A5-test-runtime-optimization.md`）已完成 4 Phase 16 步详细设计，每步含 目标/验证/回滚。待决策是否进入实施。

### [R-153] `_pe_to_style` PE 阈值边界条件（低风险，已修复）

**发现**：`fund_style_analysis.py` 的 `_pe_to_style` 使用 `ratio > 1.3`（成长）和 `ratio < 0.7`（价值）判断估值倾向，边界值（恰好等于 1.3 或 0.7）落入"混合"分支。语义上 `>=` 和 `<=` 更合理——当 PE 恰好等于行业均值的 0.7 倍时应判为价值型而非混合型。该 bug 由单元测试 `test_growth_with_industry_avg` 捕获。

**修复**：`fund_style_analysis.py:109-112` `>` → `>=`，`<` → `<=`。

**状态**：✅ 已完成（随 B5 实施时修复）

### [R-154] `excel_writer.py` API 签名系统性风险（低优先级）

**发现**：B2 实施时 `fund_manager_sheet.py` 调用了错误的 `excel_writer.py` API 签名——`write_header_row(ws, _HEADERS, ncols=N)` 应改为 `write_header_row(ws, 2, _HEADERS)`；`freeze_header(ws, nrows, ncols)` 应改为 `freeze_header(ws, row=2)`；`auto_width(ws, ncols)` 应改为 `auto_width(ws)`。问题在 B2 集成测试阶段被捕获，但说明 `excel_writer.py` 的 API 签名变更（从旧式 `ncols` 参数改为无参/最小参数）已导致多个调用方出错，存在系统性风险。

**关联问题**：B 系列 4 个 sheet 模块（`fund_manager_sheet.py`、`fund_overlap_sheet.py`、`fund_concentration_sheet.py`、`fund_style_sheet.py`）的页签标题均为硬编码字符串（如 `"14. 持仓重合度矩阵"`），未通过 `get_report_sheet_name()`（非 LLM）或 `get_llm_module_name()`（B 模块标题暂无 registry 入口）获取。若未来需统一标题来源，需在 registry 中为 B 模块注册 sheet 键名，并修改硬编码调用方。

**状态**：📋 待观察 — 建议对所有调用 `excel_writer.py` 的 sheet 模块做一次 API 签名一致性审计，或在 `excel_writer.py` 增加参数类型校验和弃用警告。

### [R-155] Excel 页签排序错位 — B 模块插入导致 1-7→13-16→8-11→12（低优先级）

**发现**：B 迭代实施中，Excel 页签创建顺序为 `ws1-ws7 → ws13-ws16 → ws8-ws12`（LLM 页签由 `write_llm_sheets()` 通过 `wb.create_sheet()` 默认 append 到末尾），最终 Excel 页签排序为 **1-7, 13-16, 8-11, 12**，不满足 §8 要求的"页签编号排序（1.~16.）"。根因：`excel_generator.py` 中 B 模块预创建在 LLM 模块写入之前，而 LLM 模块作为独立写入阶段 `_write_llm_section_and_usage()` 将其页签追加到末尾。

**修复思路**：在 `_write_llm_section_and_usage()` 写入完成后，通过 `wb.move_sheet()` 将 ws8-ws12 移动到 ws7 之后、ws13 之前；或统一由 `excel_generator.py` 创建全部页签并固定顺序，传入 LLM 写入器。

**状态**：📋 待决策 — 建议 P3 或 O 迭代处理，非功能阻塞（页签编号仍有数字前缀，用户可通过菜单导航，无数据损失）。

---

**已修复问题详细变更记录见** `docs-stm/managements/changelog.md`。
**待处理问题状态将随后续审查更新。**
