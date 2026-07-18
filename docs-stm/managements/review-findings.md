# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.6.8

---

## 当前待处理问题

> 审查方法：全库代码扫描（src/python/ + src/test/），按 technical.md §1.4（核心架构决策）和 §8（架构设计约束）逐条核对。
>
> 已修复清单见 changelog.md。
>
> v0.6.x 历史审查记录 → [`docs-stm/archive/v0.6.x/archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：同上 | 考虑拆分子模块 |
| P3-11 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：同上 | 验证函数提取到 `_validate.py` |

---

## 历史归档

- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
