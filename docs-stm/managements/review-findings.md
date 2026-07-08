# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-08（D-8c 审查：v0.3.0 代码健康度检查 — 7 项识别，4 项处理中）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|:------|:------|:----:|
| 2026-07-08 | D-8b 全面审查：代码质量/并发安全/工程化 | 已完成（全部修复） |
| 2026-07-08 | D-8c 审查：v0.3.0 代码健康度检查（R-177~R-183） | 修复中（R-181/182/183 已修复，4 项处理中） |

> **v0.1.x ~ v0.2.52 早期审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.1.x.md](../archive/archived_review-findings.0.1.x.md)。
> 涵盖：初始全量审计、P3 现代化、场景审计、第二/三波深度审计、R-131~R-147、T-001~T-003 等 13 条。
>
> **v0.2.52 ~ v0.2.91 审计记录已归档**：详见 [docs-stm/archive/archived_review-findings.0.2.x.md](../archive/archived_review-findings.0.2.x.md)。
> 涵盖：R-149~R-159、C 迭代文档审核、D-7a/D-8 实施复盘、D-8 设计复盘 等 8 条。

---

## 待修复问题

### 🔴 高优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-177 | **核心模块缺少单元测试**：`llm/generators.py`（750行 LLM 并发调度）、`llm/prompts.py`（提示词构建）、`handlers_cache.py`（缓存刷新决策树）、`handlers_report.py`（报告编排）等关键业务逻辑无独立测试，修改后缺快速回归手段 | `test/` | 按 `handlers_cache` → `handlers_report` → `generators` → `prompts` 顺序推进 |
| R-178 | **`html_writer.py` 958 行严重超重**：导入 20+ 模块，混合 HTML 构建/数据准备/模板渲染/文件写入 | `report/html_writer.py` | 已添加文件导览 TOC（L44-L78），拆分暂缓，待某区段需大改时顺手拆出 |
| R-179 | **`config.py` 817 行**：混合配置加载/校验/LLM 配置/JSON 注释剥离，30+ 模块导入 | `config.py` | 拆为 config/ 子包（loader/validator/models/入口），建议配合大改版 |

### 🟡 中优先级

| # | 问题 | 模块 | 备注 |
|:-:|:-----|:----|:----:|
| R-180 | **`type: ignore` 累计 ~23 处**：10+ 文件含 arg-type/misc/return-value/attr-defined 等忽略标记 | 多文件 | 随改随清，不单独安排改动 |
