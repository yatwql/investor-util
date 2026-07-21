# 自我审查问题记录归档 — v0.7.x

> 归档时间：2026-07-21
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.7.4 ~ v0.7.8

---

## v0.7.x 审查记录

### v0.7.4 — 首次扫描结果（2026-07-15）

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

### v0.7.5 — 版本头更新，Phase 4 批量交付（2026-07-18）

> 原始提交：`ae2b0e9` — chore: 发布后版本切换至 v0.7.5-dev

审查问题内容与 v0.7.4 一致（3 项 P3 问题：P3-9/P3-10/P3-11 文件过长），D16/D17 审查轮次尚未启动。
期间 Phase 4 批量交付：P4-01 敏感性分析 → P4-06 隐私安全、P4-08 幻觉采样 → P4-16 安全测试共 13 项完成，
变更已验证通过（regression 266 passed, 0 failed）。

---

### v0.7.7 ~ v0.7.8 — D16 终轮一致性扫描 + D17 Schema 合规审计 + P3 长期跟踪（2026-07-20 ~ 2026-07-21）

> 原始提交：`5e8a648` ~ `6f5be5c`
> 版本头：v0.7.8-dev → v0.7.8

#### P0（计划文档 — D16 终轮一致性扫描，已修复）

| # | 修复内容 |
|---|----------|
| D16-1 | §6/§7/§8 目录编号偏移修复，锚点与实际标题对齐 |
| D16-2 | I-09 cost_tracker.py 误引用 → 改为 `generate_debate_procon()` 内建 output token 守卫（D9 发现落地） |
| D16-3 | I-06 闭包变量捕获 → 改为 list-container 模式（D14 发现落地） |
| D16-4 | R6 第三层防线"综合阶段交叉校验"不存在 → 降为 2 层防线描述并添加注释 |
| D16-5 | R2 交叉引用错误（I-12→I-03）修复 |

#### P1（计划文档 — D16 终轮一致性扫描，已修复）

| # | 修复内容 |
|---|----------|
| D16-6 | I-03 session_cache 添加 threading.Lock 线程安全要求 |
| D16-7 | §4.4 新增/修改文件清单补全遗漏文件（html_writer.py、orchestrator.py、llm_content.py 等） |
| D16-8 | 依赖图 I-12 连接分支修正（从 I-04/I-05 块移至独立节点） |
| D16-9 | I-06 文件变更补全 orchestrator.py |
| D16-10 | 终轮一致性扫描提交补充（注释修复、格式对齐等） |

#### D17（计划文档 — pipeline_data Schema 合规审计，已修复）

| # | 修复内容 |
|---|----------|
| D17-1 | C19 pipeline_data Schema 合规确认：不新增 pipeline_data 键，debate_info 通过独立返回通道传递 |
| D17-2 | I-06 数据流描述扩展：debate_info 全链路数据流（a-f 六步），明确 `_fetch_llm_and_news()` 改 5 元组 |
| D17-3 | `_fetch_llm_and_news()` 第 630 行增加元组长度检测提取 debate_info |
| D17-4 | fingerprint 数据依赖合规确认：`generate_debate_procon()` 使用与 `expert_review` 相同的输入参数，不新增依赖 |

#### P3（低优先级 — 修复收益有限，建议长期跟踪，自 v0.7.4 持续未修复）

| # | 分类 | 文件 | 行号 | 问题 | 风险 | 整改收益 |
|---|------|------|------|------|------|---------|
| P3-9 | **文件过长** | `providers/tiantian.py` | 744 行 | 基金持仓解析、季度回退、业绩排名、评级计算、历史净值等多项独立职责揉合在一个文件。 | **低**：降低可读性和可测试性 | 将评级计算、风险分析拆出 |
| P3-10 | **文件过长** | `report/fund_style_analysis.py` | 635 行 | 快照管理、单股判定、行业 PE 计算、并发批量降级等多种职责。 | **低**：同上 | 考虑拆分子模块 |
| P3-11 | **文件过长** | `config/_core.py` | 631 行 | 15 个验证函数、配置读写、LLM 配置读取，验证函数模式高度一致。 | **低**：同上 | 验证函数提取到 `_validate.py` |

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
