# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.7.8-dev

---

## 当前待处理问题

> 审查方法：全库代码扫描（src/python/ + src/test/），按 technical.md §1.4（核心架构决策）和 §8（架构设计约束）逐条核对。
>
> 已修复清单见 changelog.md。

### P0（计划文档 — task91-enhanced-llm-strategy.md D16 扫描，已修复）

| # | 分类 | 状态 | 摘要 |
|---|------|:----:|:------|
| D16-1 | TOC 编号偏移 | ✅ 已修复 | 目录 §6/§7/§8 锚点与实际标题对齐 |
| D16-2 | cost_tracker 误引用 | ✅ 已修复 | I-09 改为 `generate_debate_procon()` 内建 output token 守卫 |
| D16-3 | 闭包变量陷阱 | ✅ 已修复 | I-06 改为 list-container 模式 |
| D16-4 | R6 第三层防线缺失 | ✅ 已修复 | 降为 2 层防线，删除"综合阶段交叉校验" |
| D16-5 | I-03 session_cache 缺锁 | ✅ 已修复 | 添加 `threading.Lock` 线程安全要求 |

### P1（计划文档 — task91-enhanced-llm-strategy.md D16 扫描，已修复）

| # | 分类 | 状态 | 摘要 |
|---|------|:----:|:------|
| D16-6 | R2 交叉引用错误 | ✅ 已修复 | I-12→I-03 |
| D16-7 | §4.4 文件清单不完整 | ✅ 已修复 | 补全 html_writer.py、orchestrator.py、llm_content.py 等 |
| D16-8 | 依赖图 I-12 连接错误 | ✅ 已修复 | 从 I-04/I-05 块移至独立节点 |
| D16-9 | I-06 文件变更缺 orchestrator.py | ✅ 已修复 | 已补全 |
| D16-10 | §4.4 api_base.py 变更描述不准 | ✅ 已修复 | 调整为"无变更必要" |

### D17（计划文档 — pipeline_data Schema 合规审计，已修复）

| # | 分类 | 状态 | 摘要 |
|---|------|:----:|:------|
| D17-1 | C19 pipeline_data Schema | ✅ 合规 | 不新增 pipeline_data 键，debate_info 通过独立返回通道传递 |
| D17-2 | I-06 数据流描述模糊 | ✅ 已修复 | 扩展了 debate_info 全链路数据流（a-f 六步），明确 `_fetch_llm_and_news()` 改 5 元组 |
| D17-3 | `_fetch_llm_and_news()` 第 630 行静默丢弃 | ✅ 已解决 | 增加 `len(_result) > 8` 元组长度检测提取 debate_info |
| D17-4 | fingerprint 数据依赖 | ✅ 合规 | generate_debate_procon() 使用与 expert_review 相同的输入参数，不新增依赖 |

### P3（低优先级 — 修复收益有限，建议长期跟踪）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：同上 | 考虑拆分子模块 |
| P3-11 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：同上 | 验证函数提取到 `_validate.py` |

---

## 归档

- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md)
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)

