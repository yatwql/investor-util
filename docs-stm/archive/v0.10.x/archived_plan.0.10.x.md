# 实现计划归档 — v0.10.x

> 归档时间：2026-08-05
> 原始文件：`docs-stm/managements/plan.md`（当前迭代部分）
> 涵盖版本：v0.10.0 ~ v0.10.4（2026-08-03 ~ 2026-08-05）
> 归档内容：本迭代已实现的计划项（plan-17~plan-24）及其迭代设计文件

---

## v0.10.x 设计文档

本迭代完成项对应的中间设计文档：

- [`plan-investment-features.md`](investment-features/plan-investment-features.md) — plan-17~24 投资分析功能优化设计（需求 × 数据源可行性 × 章节归并，§4 章节归并方案 + §4.4 架构合规自查表 + §5 实施次序）
- [`plan-investment-iteration.md`](investment-features/plan-investment-iteration.md) — plan-17~24 迭代实施计划（21 轮 / 8 阶段，每轮量化验收 + 验收签字）
- [`plan-task-code-traces-gate.md`](task-code-traces-gate/plan-task-code-traces-gate.md) — rf-208 任务编号标识符/注释门禁增强设计（check-code-traces.py 扩展 IDENT 维度 + 系列代号模式）

## v0.10.x 已完成项

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| plan-17 | **数据质量仪表盘** | 「数据源可用性矩阵」章改造为「数据质量仪表盘」：品种级覆盖诊断（`read_holdings` 状态标注）+ 源级健康 + 数据可信度/异常跳变检测；开关 `report_submodules.data_quality`（默认关） | 轮1~3 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-18 | **行动建议章** | 新增「行动建议」章（`always` 类型，`enable_action` 默认关）：调仓建议（可行化层，份额取整/现金约束/费用）+ 交易纪律 + 收益归因（品种贡献占比）；「智囊团深度复盘」章「行动摘要」子块（单源计算、两处呈现） | 轮4~7 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-19 | **持仓关系矩阵合并** | 物理合并「持仓重合度矩阵」+「持仓相关性矩阵」→「持仓关系矩阵」（sheet key `position_relationship`），一章分上下矩阵区块；删除旧 sheet 注册 + 数据契约增删 + registry.number 重排 | 轮8 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-20 | **历史增强** | 物理合并「组合历史走势」+「历史回撤分析」→「组合历史走势与回撤」（`portfolio_history_drawdown`，走势表+回撤矩阵区块）+ 危机区间标注 + 尾部风险（VaR）；「组合演进」章快照差异摘要 | 轮9~11 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-21 | **风格与选基** | 物理合并「基金风格分析」+「因子暴露分析」→「风格与因子分析」（`style_factor` 一章三区块：风格表 + 因子回归 + 行业 Beta 子表，章节数 20→19）；基金业绩分析章候选基金比较增强模式（`candidate_compare` 默认关） | 轮12~13 | ✅ 已完成（v0.10.3，2026-08-05） |
| plan-22 | **成本流水** | 持仓 Excel 可选「交易流水」「分红流水」页签 + 资金加权收益（XIRR）+ 成本分档 + 分红累计；「投资分析汇总」/「市值核算明细表」/「持仓分类表」三页签渲染（`fund_flow_data` 契约，`cost_lots` 默认关）+ HTML 三处条件渲染补遗 | 轮14~16 | ✅ 已完成（v0.10.3，2026-08-05） |
| plan-23 | **估值与温度** | 「资产穿透TOP10」章估值分位（当前 PE/PB + 价格分位代理，`valuation_percentile` 默认关）+「投资分析汇总」章市场温度（价格分位+均线偏离+波动率三因子，温度计无仓位指令，`market_temperature` 默认关）；`valuation_data`/`market_temperature_data` 契约 | 轮17~18 | ✅ 已完成（v0.10.4，2026-08-05） |
| plan-24 | **导航与收尾** | HTML 报告左侧目录五组折叠导航（`<details>/<summary>` 分组 + 组徽标计数 + 窄屏扁平兜底）+ 文档快照与用户手册同步（folders/test-coverage 统计、reports-instruction 序号核对、how-to-config 开关行） | 轮19~20 | ✅ 已完成（v0.10.4，2026-08-05） |

> 发布门禁（轮 21）：v0.10.3/v0.10.4 两次发布均通过 `test_runner.py --mode verify,regression` 全量 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致 + 数据快照刷新 + registry.number 连续编号复核 + 数据契约增删复核（changelog v0.10.3/v0.10.4）。

## 归档说明

- plan-17~24 三组设计/实施文档 2026-08-05 由 `docs-stm/plan/` 移入本目录：plan-17~24 设计层 + 实施层 → `investment-features/`（`plan-investment-features.md` 设计 + `plan-investment-iteration.md` 21 轮实施，同属「投资功能优化 + 章节归并」主题，目录语义与内容相关）；rf-208 门禁增强设计 → `task-code-traces-gate/`。
- `docs-stm/plan/` 仅保留未完成项（plan-8 轻量 Web UI / plan-10 日志可视化，P4 实验功能）设计文档：`plan-web-ui.md` + `plan-web-ui-implementation.md`。
- 版本号：本归档涵盖已发布版本 v0.10.0 ~ v0.10.4（当前开发版本 v0.10.5-dev，归档时点为 2026-08-05），归档目录按版本段命名 v0.10.x。
