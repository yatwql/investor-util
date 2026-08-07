# 实现计划归档 — v0.10.x

> 归档时间：2026-08-05（设计文档 + 完成项摘要）；2026-08-05 二次合并 plan.md 已完成事项记录；2026-08-07 追加 plan-25 Web 持仓输入模式 / plan-26 Web 配置编辑 / README SVG 架构图
> 原始文件：`docs-stm/managements/plan.md`（当前迭代部分）
> 涵盖版本：v0.10.0 ~ v0.10.4（2026-08-03 ~ 2026-08-05）；plan-25/26 于 0.10.12-dev 实现、README SVG 于 0.10.13-dev 实现（2026-08-07）
> 归档内容：本迭代已实现的计划项（plan-17~plan-26）设计文档 + 完成项摘要 + 推荐实施顺序 + 发布门禁记录（P0/P1/P2/P3 已完成事项记录自 plan.md 整体迁入）

---

## v0.10.x 设计文档

本迭代完成项对应的中间设计文档：

- [`plan-investment-features.md`](investment-features/plan-investment-features.md) — plan-17~24 投资分析功能优化设计（需求 × 数据源可行性 × 章节归并，§4 章节归并方案 + §4.4 架构合规自查表 + §5 实施次序）
- [`plan-investment-iteration.md`](investment-features/plan-investment-iteration.md) — plan-17~24 迭代实施计划（21 轮 / 8 阶段，每轮量化验收 + 验收签字）
- [`plan-task-code-traces-gate.md`](task-code-traces-gate/plan-task-code-traces-gate.md) — rf-208 任务编号标识符/注释门禁增强设计（check-code-traces.py 扩展 IDENT 维度 + 系列代号模式）
- [`plan-web-ui.md`](web-ui/plan-web-ui.md) — plan-8 轻量 Web UI / plan-10 日志可视化计划（2026-08-06 三阶段完成后由 `docs-stm/plan/` 归档）
- [`plan-web-ui-implementation.md`](web-ui/plan-web-ui-implementation.md) — plan-8 Web UI 实施拆分设计（评估/风险/约束符合性/模块拆分/安全/API/测试/阶段，2026-08-06 归档）
- [`plan-web-holdings-input-modes.md`](web-holdings-input-modes/plan-web-holdings-input-modes.md) — plan-25 Web 持仓输入模式（试算隔离/正式共享）实现设计（命名空间隔离 + 双模式输入，2026-08-07 完成归档）
- [`web-config-edit.md`](web-config-edit/web-config-edit.md) — plan-26 Web 配置编辑（完整镜像 TUI 可编辑配置全集）设计定稿（白名单 + 7 组控件 + 原子写备份，2026-08-07 完成归档）
- [`plan-readme-svg-layout.md`](readme-svg-layout/plan-readme-svg-layout.md) — README 嵌入 SVG 架构图 + 排版优化设计（3 张深色科技风图 + folders 同步，2026-08-07 完成归档）

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
| plan-25 | **Web 持仓输入模式** | Web「生成用途」双模式：临时试算（快照隔离 `web/` 域，不污染共享时间线）/ 正式更新（上传覆盖备份 `.bak` 或用存量直接读正式文件，快照共享）；`history_snapshot` 全公开函数 + 消费/编排层 `namespace`/`snapshot_namespace` 透传；`web/holdings_update.py` 备份+原子提升；`_handle_create_run` mode/use_existing 组合校验；前端生成用途/输入来源 UI；语义表登记 `snapshot_namespace`/`web_input_mode`/`use_existing`/`holdings_update` | 6 阶段 | ✅ 已完成（0.10.12-dev，2026-08-07） |

### P0 — 发布门禁（已完成）

> 发布门禁（轮 21）：v0.10.3/v0.10.4 两次发布均通过 `test_runner.py --mode verify,regression` 全量 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致 + 数据快照刷新 + registry.number 连续编号复核 + 数据契约增删复核（changelog v0.10.3/v0.10.4）。

- ✅ **全链回归与发布门禁**（迭代计划轮 21）：`test_runner.py --mode verify,regression` 3256 全过 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致（v0.10.4）+ 数据快照刷新（test-coverage 5038 / folders 统计）+ registry.number 连续编号复核 + 数据契约增删复核。**v0.10.4 已发布**（2026-08-05）。
- ✅ **全链回归与发布门禁**（迭代计划轮 21）：`test_runner.py --mode verify,regression` 3169 全过 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致（v0.10.3）+ 数据快照刷新（test-coverage 4916 / folders 统计）+ registry.number 连续编号复核 + 数据契约增删复核。**v0.10.3 已发布**（2026-08-05）。

### 推荐实施顺序（①~⑧ 全部完成）

> 结合架构约束、收益/风险与最新依赖状态重排的推荐实施次序。①~⑧ 为推荐先后；括号内为计划项优先级归类。plan-4 已放弃，不列入实施序列；plan-8/plan-10 归 P4 实验功能（仍在 plan.md），不列入本迭代实施序列。

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

#### ✅ `plan-17` 数据质量仪表盘（[`plan-investment-iteration.md` 阶段A](investment-features/plan-investment-iteration.md)）— **推荐① · 已完成**

改造「数据源可用性矩阵」章为「数据质量仪表盘」：品种级覆盖诊断（`read_holdings` 状态标注）+ 源级健康 + 数据可信度/异常跳变检测。开关 `report_submodules.data_quality`（默认关）。**对应轮 1~3**，每轮量化验收（已通过）。

#### ✅ `plan-18` 行动建议章（[`plan-investment-iteration.md` 阶段B](investment-features/plan-investment-iteration.md)）— **推荐② · 已完成**

新增「行动建议」章（`always` 类型，`enable_action` 默认关）：调仓建议（可行化层，份额取整/现金约束/费用）+ 交易纪律 + 收益归因（品种贡献占比，复用 `_build_profit_attribution_block`）；「智囊团深度复盘」章加「行动摘要」子块（单源计算、两处呈现）。**对应轮 4~7**（已通过）。

#### ✅ `plan-19` 持仓关系矩阵合并（[`plan-investment-iteration.md` 阶段B′](investment-features/plan-investment-iteration.md)）— **推荐③ · 已完成**

物理合并「持仓重合度矩阵」+「持仓相关性矩阵」→「持仓关系矩阵」（sheet key `position_relationship`），一章分上下矩阵区块；删除旧 sheet 注册 + 数据契约增删 + registry.number 重排。**对应轮 8**（已通过）。

#### ✅ `plan-20` 历史增强（[`plan-investment-iteration.md` 阶段C](investment-features/plan-investment-iteration.md)）— **推荐④ · 已完成**

物理合并「组合历史走势」+「历史回撤分析」→「组合历史走势与回撤」（`portfolio_history_drawdown`，走势表+回撤矩阵区块）+ 危机区间标注 + 尾部风险（VaR）；「组合演进」章快照差异摘要。**对应轮 9~11**（已通过）。

### P2 — 已完成（轮 12~16）

#### ✅ `plan-21` 风格与选基（[`plan-investment-iteration.md` 阶段D](investment-features/plan-investment-iteration.md)）— **推荐⑤ · 已完成**

物理合并「基金风格分析」+「因子暴露分析」→「风格与因子分析」（`style_factor`，一章三区块：风格表 + 因子回归 + 行业 Beta 子表）——**轮 12 已完成**（章节数 20→19，registry.number 重新编号，数据契约 `style_factor_data` 删旧建新，dev-verify 1568 passed + 3 check 全 [OK]）；基金业绩分析章候选基金比较增强模式（`candidate_compare` 默认关）——**轮 13 已完成**（核心模块 `report/fund_candidate.py`，Excel/HTML 双渲染，新增测试 23 个，覆盖率 99%，dev-verify 1568 passed）。

#### ✅ `plan-22` 成本流水（[`plan-investment-iteration.md` 阶段E](investment-features/plan-investment-iteration.md)）— **推荐⑥ · 已完成**

持仓 Excel 新增**可选**「交易流水」「分红流水」页签（不破坏既有 4 列）+ 资金加权收益（XIRR）+ 成本分档；「投资分析汇总」/「市值核算明细表」/「持仓分类表」章渲染（Excel + HTML）。**对应轮 14~16，已完成**——轮 14 持仓文件格式扩展（`TradeRecord`/`DividendRecord` + `read_flow_sheets()`/`read_holdings_with_flows()`，20 例解析测试、覆盖率 93%）；轮 15 XIRR 资金加权收益 + 成本分档（`analysis/cost_flow.py` 纯计算层，24 例、覆盖率 94%）；轮 16 三页签渲染（`report_submodules.cost_lots` 默认关 + `fund_flow_data` 数据契约 + CLI/TUI 接线，新增测试 32 个、受影响套件 267 passed，dev-verify 1638 passed）；**HTML 渲染补齐**（轮16 补遗：`html_writer._build_flow_display` 复用加权成本/分档标签组装展示映射 + 模板三处条件渲染，新增测试 12 个）。

### P3 — 已完成（轮 17~20）

#### ✅ `plan-23` 估值与温度（[`plan-investment-iteration.md` 阶段F](investment-features/plan-investment-iteration.md)）— **推荐⑦ · 已完成**

「资产穿透TOP10」章估值分位（当前 PE/PB + 价格分位代理，显式标注局限）+「投资分析汇总」章市场温度（价格分位+均线偏离+波动率三因子，温度计无仓位指令）。**对应轮 17~18，已完成**——轮 17 估值分位（`analysis/valuation_percentile.py` 纯计算层 + `providers/eastmoney_industry.py` push2 扩展 PE/PB + 编排层 `compute_valuation_data`，穿透 TOP10 追加「估值分位」列，开关 `report_submodules.valuation_percentile` 默认关）；轮 18 市场温度（`analysis/market_temperature.py` 纯计算层，复用价格分位机制，编排层 `compute_market_temperature_data`，汇总章追加「市场温度」刻度行，开关 `report_submodules.market_temperature` 默认关）；双开关独立、同章不同行互不影响，`valuation_data`/`market_temperature_data` 数据契约注册，dev-verify 1694 passed + 3 check 全 [OK]。

#### ✅ `plan-24` 导航与收尾（[`plan-investment-iteration.md` 阶段G](investment-features/plan-investment-iteration.md)）— **推荐⑧ · 已完成**

HTML 报告左侧目录按「基础/基金深度/风险/历史/LLM」五组折叠导航。**对应轮 19~20，已完成**——轮 19 分组导航（`html_writer.py` 新增 `_NAV_GROUP_LABELS`/`_SECTION_NAV_GROUP_MAP`/`_build_section_nav_groups()`：五组固定顺序、仅收录可见章节、组内按报告序号升序；`report_template.html` 目录改 `<details>/<summary>` 折叠分组 + 组标题徽标计数；窄屏扁平 `section-nav` 兜底；`TestHtmlTocGroupedNav` 11 例全通过）；轮 20 文档快照与用户手册同步（folders.md 统计表、test-coverage.md 实时计数、how-to-config.md 新开关行 + `report_section_order` 19 项核对、reports-instruction.md 目录五组说明 + 「页面/章节分组」序号全面核对、registry.py docstring 20→19、faq.md 19 项修正），dev-verify 1694 passed + 3 check 全 [OK]。

## 归档说明

- plan-17~24 三组设计/实施文档 2026-08-05 由 `docs-stm/plan/` 移入本目录：plan-17~24 设计层 + 实施层 → `investment-features/`（`plan-investment-features.md` 设计 + `plan-investment-iteration.md` 21 轮实施，同属「投资功能优化 + 章节归并」主题，目录语义与内容相关）；rf-208 门禁增强设计 → `task-code-traces-gate/`。
- **二次合并**：`docs-stm/managements/plan.md` 中 v0.10.x 已完成事项记录（P0 发布门禁两条、推荐实施顺序 ①~⑧ 表格、P1~P3 已完成项详细段落）整体迁入本文件「v0.10.x 已完成项」章节，原相对链接改指本目录内 `investment-features/` 兄弟路径。plan.md 仅保留未完成项与归档引用。
- `docs-stm/plan/` 原保留未完成项（plan-8 轻量 Web UI / plan-10 日志可视化，P4 实验功能）设计文档：`plan-web-ui.md` + `plan-web-ui-implementation.md`。**plan-8 已于 2026-08-06 三阶段全部实施完成**，两份设计文档归档至 `docs-stm/archive/v0.10.x/web-ui/`（见本文件「v0.10.x 设计文档」索引）；plan.md 引用同步改指归档路径，`docs-stm/plan/` 当前为空目录。
- 版本号：本归档涵盖已发布版本 v0.10.0 ~ v0.10.4（当前开发版本 v0.10.5-dev，归档时点为 2026-08-05），归档目录按版本段命名 v0.10.x。
