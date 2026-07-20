# 自我审查问题记录归档 — v0.7.x

> 归档时间：2026-07-20
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.7.4 ~ v0.7.5

---

## v0.7.x 审查记录

### v0.7.4 — 初始审查结果（2026-07-15）

> 原始提交：`4fecab4` — release: v0.7.4
> 版本头：v0.7.4

审查方法：全库代码扫描（src/python/ + src/test/），按 technical.md §1.4（核心架构决策）和 §8（架构设计约束）逐条核对。

#### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：同上 | 考虑拆分子模块 |
| P3-11 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：同上 | 验证函数提取到 `_validate.py` |

---

### v0.7.5 — 版本头更新（2026-07-18）

> 原始提交：`ae2b0e9` — chore: 发布后版本切换至 v0.7.5-dev

审查问题内容与 v0.7.4 一致，仅版本头从 `v0.7.4` 更新为 `v0.7.5-dev`。3 项 P3 问题（P3-9、P3-10、P3-11）均未修复。

---

## 归档引用

- `review-findings.md`（当前）→ `docs-stm/managements/review-findings.md`
- 原始 git 提交历史 → `4fecab4` ~ `ae2b0e9`

## 历史审查记录（早期版本）

- [`archived_review-findings.0.6.x.md`](../v0.6.x/archived_review-findings.0.6.x.md) — v0.6.0 ~ v0.6.9
- [`archived_review-findings.0.5.x.md`](../v0.5.x/archived_review-findings.0.5.x.md) — v0.5.0 ~ v0.5.12
- [`archived_review-findings.0.4.x.md`](../v0.4.x/archived_review-findings.0.4.x.md) — v0.4.0 ~ v0.4.5
- [`archived_review-findings.0.3.x.md`](../v0.3.x/archived_review-findings.0.3.x.md) — v0.3.0 ~ v0.3.10
- [`archived_review-findings.0.2.x.md`](../v0.2.x/archived_review-findings.0.2.x.md) — v0.2.0 ~ v0.2.91
- [`archived_review-findings.0.1.x.md`](../v0.1.x/archived_review-findings.0.1.x.md) — 早期版本
