# 个人投资分析报告生成小助手 — 实现计划
> 文档版本：0.10.5-dev
> **编号源**：`plan-next = 25`（新增计划项取此编号，完成后更新为 +1；已用最大 plan-24，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

**当前迭代**：投资功能优化 + 章节归并（目标 19 章）。**P1 阶段（轮 1~11）已完成**：行动建议独立章（轮 4 新增）、持仓关系矩阵合并（轮 8）、组合历史与回撤合并（轮 9）。**阶段 D 轮 12~13 已完成**：合并「基金风格分析」+「因子暴露分析」→「风格与因子分析」（`style_factor` 一章三区块，章节数 20→19）；基金业绩分析章候选基金比较增强（`candidate_compare` 默认关）。**阶段 E 轮 14~16 已完成（plan-22 成本流水）**：持仓 Excel 可选「交易流水」「分红流水」页签 + XIRR 资金加权收益 + 成本分档，渲染到「投资分析汇总」/「市值核算明细表」/「持仓分类表」三页签（`fund_flow_data` 契约，`cost_lots` 默认关）。详细设计与实施轮次见 [`plan-investment-features.md`](../plan/plan-investment-features.md)（设计层，含 §4 章节归并方案与 §4.4 架构合规自查表）与 [`plan-investment-iteration.md`](../plan/plan-investment-iteration.md)（实施层，21 轮每轮量化验收）。本文档仅收录**任务摘要**，按优先级分类。

> **命名纪律（强制）**：重构/新增的变量名、函数名、注释与文档表述必须与新章节语义相关（如 `position_relationship`/`portfolio_history_drawdown`/`style_factor`/`action`），**绝对禁止用任务编号命名**（F 系列、plan-N、rf-N 等）。任务编号仅在本表作链接锚点，不进入实现层。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪 · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P0 — 发布门禁

- ✅ **全链回归与发布门禁**（迭代计划轮 21）：`test_runner.py --mode verify,regression` 3256 全过 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致（v0.10.4）+ 数据快照刷新（test-coverage 5038 / folders 统计）+ registry.number 连续编号复核 + 数据契约增删复核。**v0.10.4 已发布**（2026-08-05）。
- ✅ **全链回归与发布门禁**（迭代计划轮 21）：`test_runner.py --mode verify,regression` 3169 全过 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致（v0.10.3）+ 数据快照刷新（test-coverage 4916 / folders 统计）+ registry.number 连续编号复核 + 数据契约增删复核。**v0.10.3 已发布**（2026-08-05）。

### 推荐实施顺序

> 结合架构约束、收益/风险与最新依赖状态重排的推荐实施次序。①~⑧ 为推荐先后；括号内为计划项优先级归类。详细设计与每轮验收见 [`plan-investment-features.md`](../plan/plan-investment-features.md) §5 与 [`plan-investment-iteration.md`](../plan/plan-investment-iteration.md) 阶段地图。plan-4 已放弃，不列入实施序列；plan-8/plan-10 已归 P4 实验功能，不列入当前实施序列。**标记 ✅ 的为已完成项**（P1 轮 1~11 + 阶段 D 轮 12~13 + 阶段 E 轮 14~16 + 阶段 F 轮 17~18，changelog v0.10.1/v0.10.3/v0.10.4），保留在表中供追溯；待办序列自 ⑧ 起。

| 次序 | 计划项 | 归类 | 工作量 | 推荐理由 |
|:--:|:--|:--:|:--:|:--|
| ① | ✅ **plan-17** 数据质量仪表盘 | P1 | 轮1~3 | 地基先行，「数据源可用性矩阵」章改造为后续可信度基础 |
| ② | ✅ **plan-18** 行动建议章 | P1 | 轮4~7 | 决策价值最高，纯算法 always 类型全报告可见 |
| ③ | ✅ **plan-19** 持仓关系矩阵合并 | P1 | 轮8 | 物理合并流程模板，确立数据契约增删范式 |
| ④ | ✅ **plan-20** 历史增强 | P1 | 轮9~11 | 合并组合历史+回撤 + 危机标注 + 尾部风险 |
| ⑤ | ✅ **plan-21** 风格与选基 | P2 | 轮12~13 | 风格与因子合并 + 行业 Beta（20→19 章）+ 候选基金比较增强（`candidate_compare` 默认关），changelog v0.10.3 |
| ⑥ | ✅ **plan-22** 成本流水 | P2 | 轮14~16 | 依赖持仓文件格式扩展，输入→计算→渲染 |
| ⑦ | ✅ **plan-23** 估值与温度 | P3 | 轮17~18 | 免费代理信号，合规敏感，放最后 |
| ⑧ | ✅ **plan-24** 导航与收尾 | P3 | 轮19~20 | 分组导航 + 文档快照，收尾性质 |

### P1 — 已完成（轮 1~11）

> 本迭代核心：章节归并 + 决策闭环功能。每阶段一个计划项，对应迭代计划轮次区间；**变量/函数/注释/文档一律用新章节语义名，禁用任务编号**。以下 P1 计划项**全部完成**（验收记录见 changelog v0.10.1 对应轮次）。

#### ✅ `plan-17` 数据质量仪表盘（[`plan-investment-iteration.md` 阶段A](./plan-investment-iteration.md)）— **推荐① · 已完成**

改造「数据源可用性矩阵」章为「数据质量仪表盘」：品种级覆盖诊断（`read_holdings` 状态标注）+ 源级健康 + 数据可信度/异常跳变检测。开关 `report_submodules.data_quality`（默认关）。**对应轮 1~3**，每轮量化验收（已通过）。

#### ✅ `plan-18` 行动建议章（[`plan-investment-iteration.md` 阶段B](./plan-investment-iteration.md)）— **推荐② · 已完成**

新增「行动建议」章（`always` 类型，`enable_action` 默认关）：调仓建议（可行化层，份额取整/现金约束/费用）+ 交易纪律 + 收益归因（品种贡献占比，复用 `_build_profit_attribution_block`）；「智囊团深度复盘」章加「行动摘要」子块（单源计算、两处呈现）。**对应轮 4~7**（已通过）。

#### ✅ `plan-19` 持仓关系矩阵合并（[`plan-investment-iteration.md` 阶段B′](./plan-investment-iteration.md)）— **推荐③ · 已完成**

物理合并「持仓重合度矩阵」+「持仓相关性矩阵」→「持仓关系矩阵」（sheet key `position_relationship`），一章分上下矩阵区块；删除旧 sheet 注册 + 数据契约增删 + registry.number 重排。**对应轮 8**（已通过）。

#### ✅ `plan-20` 历史增强（[`plan-investment-iteration.md` 阶段C](./plan-investment-iteration.md)）— **推荐④ · 已完成**

物理合并「组合历史走势」+「历史回撤分析」→「组合历史走势与回撤」（`portfolio_history_drawdown`，走势表+回撤矩阵区块）+ 危机区间标注 + 尾部风险（VaR）；「组合演进」章快照差异摘要。**对应轮 9~11**（已通过）。

### P2 — 已完成（轮 12~16）

#### ✅ `plan-21` 风格与选基（[`plan-investment-iteration.md` 阶段D](./plan-investment-iteration.md)）— **推荐⑤ · 已完成**

物理合并「基金风格分析」+「因子暴露分析」→「风格与因子分析」（`style_factor`，一章三区块：风格表 + 因子回归 + 行业 Beta 子表）——**轮 12 已完成**（章节数 20→19，registry.number 重新编号，数据契约 `style_factor_data` 删旧建新，dev-verify 1568 passed + 3 check 全 [OK]）；基金业绩分析章候选基金比较增强模式（`candidate_compare` 默认关）——**轮 13 已完成**（核心模块 `report/fund_candidate.py`，Excel/HTML 双渲染，新增测试 23 个，覆盖率 99%，dev-verify 1568 passed）。

#### ✅ `plan-22` 成本流水（[`plan-investment-iteration.md` 阶段E](./plan-investment-iteration.md)）— **推荐⑥ · 已完成**

持仓 Excel 新增**可选**「交易流水」「分红流水」页签（不破坏既有 4 列）+ 资金加权收益（XIRR）+ 成本分档；「投资分析汇总」/「市值核算明细表」/「持仓分类表」章渲染（Excel + HTML）。**对应轮 14~16，已完成**——轮 14 持仓文件格式扩展（`TradeRecord`/`DividendRecord` + `read_flow_sheets()`/`read_holdings_with_flows()`，20 例解析测试、覆盖率 93%）；轮 15 XIRR 资金加权收益 + 成本分档（`analysis/cost_flow.py` 纯计算层，24 例、覆盖率 94%）；轮 16 三页签渲染（`report_submodules.cost_lots` 默认关 + `fund_flow_data` 数据契约 + CLI/TUI 接线，新增测试 32 个、受影响套件 267 passed，dev-verify 1638 passed）；**HTML 渲染补齐**（轮16 补遗：`html_writer._build_flow_display` 复用加权成本/分档标签组装展示映射 + 模板三处条件渲染，新增测试 12 个）。

### P3 — 已完成（轮 17~20）

#### ✅ `plan-23` 估值与温度（[`plan-investment-iteration.md` 阶段F](./plan-investment-iteration.md)）— **推荐⑦ · 已完成**

「资产穿透TOP10」章估值分位（当前 PE/PB + 价格分位代理，显式标注局限）+「投资分析汇总」章市场温度（价格分位+均线偏离+波动率三因子，温度计无仓位指令）。**对应轮 17~18，已完成**——轮 17 估值分位（`analysis/valuation_percentile.py` 纯计算层 + `providers/eastmoney_industry.py` push2 扩展 PE/PB + 编排层 `compute_valuation_data`，穿透 TOP10 追加「估值分位」列，开关 `report_submodules.valuation_percentile` 默认关）；轮 18 市场温度（`analysis/market_temperature.py` 纯计算层，复用价格分位机制，编排层 `compute_market_temperature_data`，汇总章追加「市场温度」刻度行，开关 `report_submodules.market_temperature` 默认关）；双开关独立、同章不同行互不影响，`valuation_data`/`market_temperature_data` 数据契约注册，dev-verify 1694 passed + 3 check 全 [OK]。

#### ✅ `plan-24` 导航与收尾（[`plan-investment-iteration.md` 阶段G](./plan-investment-iteration.md)）— **推荐⑧ · 已完成**

HTML 报告左侧目录按「基础/基金深度/风险/历史/LLM」五组折叠导航。**对应轮 19~20，已完成**——轮 19 分组导航（`html_writer.py` 新增 `_NAV_GROUP_LABELS`/`_SECTION_NAV_GROUP_MAP`/`_build_section_nav_groups()`：五组固定顺序、仅收录可见章节、组内按报告序号升序；`report_template.html` 目录改 `<details>/<summary>` 折叠分组 + 组标题徽标计数；窄屏扁平 `section-nav` 兜底；`TestHtmlTocGroupedNav` 11 例全通过）；轮 20 文档快照与用户手册同步（folders.md 统计表、test-coverage.md 实时计数、how-to-config.md 新开关行 + `report_section_order` 19 项核对、reports-instruction.md 目录五组说明 + 「页面/章节分组」序号全面核对、registry.py docstring 20→19、faq.md 19 项修正），dev-verify 1694 passed + 3 check 全 [OK]。

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。**当前实验项**：日志可视化、轻量 Web UI（独立于本迭代，选做，无排期）。

#### `plan-10` 日志可视化（[`plan-web-ui.md §3`](../plan/plan-web-ui.md#3-日志可视化)）

结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表）。**预估：1d**

#### `plan-8` 轻量 Web UI（[`plan-web-ui.md §1`](../plan/plan-web-ui.md#1-轻量-web-ui)）

Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载。MVP 不做多用户/LLM 在线修改/实时日志流。**运维与安全成本最高，单人工具需谨慎，选做。**

> 详细评估与实施拆分见 [`plan-web-ui-implementation.md`](../plan/plan-web-ui-implementation.md)（收益/风险/架构约束符合性/`src/python/web/` 模块拆分/安全设计/API/测试/实施阶段）。

| 阶段 | 工作量 |
|------|:------:|
| MVP 核心 | 3d |
| 功能补齐 | 1.5d |
| 体验打磨 | 1d |

---

## 归档

- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
