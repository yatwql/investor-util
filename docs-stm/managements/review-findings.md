# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.8.3-dev

---

## 当前待处理问题

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 768 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件（较记录时增长 24 行）。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 652 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责（较记录时增长 17 行）。 | **低**：同上 | 考虑拆分子模块 |
| P3-12 | **CI 测试失败** | GitHub Actions | — | GitHub CI 测试持续失败，需排查流水线配置或测试环境差异问题。 | **中**：阻塞 CI 门禁，影响合并/发布流程可靠性 | 修复 CI 配置或测试用例，确保流水线通过 |

---

## 归档

- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)

