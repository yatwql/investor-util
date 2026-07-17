# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.6.4

---

## 当前待处理问题

> 审查方法：全库代码扫描（src/python/ + src/test/），按 technical.md §1.4（核心架构决策）和 §8（架构设计约束）逐条核对。
> 审查范围：架构约束遵从、死代码、C2/C3 缓存原子写入、C8 日志统一、C14 模块级全局变量等。
>
> 已修复清单见 changelog.md [0.6.3-dev] 条目。

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：同上 | 考虑拆分子模块 |
| P3-11 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：同上 | 验证函数提取到 `_validate.py` |

---

## 按约束分类汇总

| 约束 | 问题数 | P1 | P2 | P3 | 要点 |
|:-----|:------:|:--:|:--:|:--:|:------|
| **C1** 代码类型判定中心化 | 0 | - | - | - | 全部已修复 |
| **C2** 缓存统一管理 | 0 | - | - | - | 全部通过 |
| **C3** 缓存原子写入 | 0 | - | - | - | 已修复 |
| **C5** HTTP 客户端统一 | 0 | - | - | - | 已修复 |
| **C6** Provider Chain 必经 | 0 | - | - | - | 已修复 |
| **C7** 报告序号不可硬编码 | 0 | - | - | - | 已修复 |
| **C8** 日志统一 | 0 | - | - | - | 已修复 |
| **C9** LLM 模块注册 | 0 | - | - | - | 全部通过 |
| **C14** 渲染期全局变量 | 0 | - | - | - | 已修复 |
| **C11/C12/C13** 测试约束 | 0 | - | - | - | 全部通过 |
| 死代码/命名残留 | 0 | - | - | - | 已修复 |
| 文件过长 | 3 | - | - | 3 | tiantian.py/fund_style_analysis.py/_core.py 超长 |

> 当前剩余 **3 项问题**，均为 P3 低优先级，长期跟踪。

---

历史自审记录已归档：

- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
