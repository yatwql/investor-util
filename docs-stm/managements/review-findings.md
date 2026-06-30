# 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-06-30

---

## 典型发现的问题

### [R-003] 多处死代码残留（已清理）

- **发现日期**：2026-06-27
- **类型**：死代码
- **描述**：多模块存在已废弃但未清理的函数和 import：cache.exists()、tiantian.fetch_fund_type()、sina_news 3 个死函数、llm_content.write_llm_sheets 12 个冗余参数及 ~60 行死分支、main.py portfolio_items 字典及未使用 import
- **修复**：全部清理（详见 changelog v0.2.8 Removed）

### [R-004] html_writer.py a_indices/us_indices 类型不匹配（已修复）

- **发现日期**：2026-06-27
- **类型**：类型不匹配
- **描述**：`fetch_indices()` 返回 `dict[str, dict]`，但 html_writer.py 将其转为 `list[dict]` 传入 `generate_all_llm()`，该函数签名声明为 `dict` 并调用 `.values()`，列表无此方法将引发 `AttributeError`
- **修复**：保留 dict 原始类型传 LLM，模板渲染使用独立 list 变量

### [R-005] fund_performance.py 对 API JSON null 值缺少防护（已修复）

- **发现日期**：2026-06-27
- **类型**：空安全缺陷
- **描述**：`perf_eval.get("categories", [])` 在 JSON 中存在显式 `null`（如 `{"categories": null}`）时返回 `None` 而非 `[]`，随后 `enumerate(categories)` 引发 `TypeError`
- **修复**：`.get()` 后使用 `or []` 兜底

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
| 2026-06-30 | 代码审查 — 非 LLM 页签名注册化、指纹函数合并、news_correlation 批量模式纳入共享骨架、TUI 摘要标题统一、`_CONTENT_FILTER_RECOVERY` 导出清理 | 代码审查 |

---

## 迭代结束审查清单

- [x] Iter 1 全部功能已实现（项目骨架、TUI、数据源、Excel 输出）
- [x] Iter 2 全部功能已实现（分类汇总、穿透 TOP10、基金业绩）
- [x] Iter 3.1 已实现（HTML 报告引擎）
- [x] Iter 3.2 已实现（财经新闻热点与持仓关联分析模块）
- [x] Iter 3.3 已实现（模板占位 + 缓存管理 + 异常处理增强）
- [x] Iter 3.4 已完成（HTML + Excel LLM 模块）
- [x] Iter 3.5 已完成（LLM 全局优化）
- [x] Iter 3.6 已完成（全面性能优化与代码清理）
- [x] 配置管理含 output_dir 字段，支持菜单 R 配置
- [x] 所有单元测试通过（1019 项）
- [x] API Key 不丢失（config.json 不存明文 key，使用外部文件 llm_key.json）
- [x] Excel/HTML 输出文件格式正确
- [x] TUI 菜单功能正常（含 B/L/R 新菜单）
- [x] API 联通性已验证
- [x] 缓存逻辑正确
- [x] v0.2.18 盈利预测/行业资金流向/分红历史集成完成
- [x] 进程级内存缓存层 + 指数数据内存缓存
- [x] Batch 新闻 LLM 分析优化
- [x] 配置同步（config.json cache_ttl 补全 + llm_settings.json cache_ttl_macro 修正）
- [x] v0.2.29 持仓体检报告集成完成
- [x] v0.2.30 穿透深度分析集成完成
- [x] 综合审计：配置/缓存前缀/管理文档核对完成
- [x] v0.2.32 Token 定价可配置、多币种、缓存命中计费、全量管理文档审计
- [x] v0.2.33 Import/Sheet 写入隔离 + 名称统一 + 常量重命名 + 智囊团 NAV/QDII 标注 + 全量自测 814 passed
