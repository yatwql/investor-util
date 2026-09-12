# 实现计划归档 — v0.10.x

> 归档时间：2026-08-05（设计文档 + 完成项摘要）；2026-08-05 二次合并 plan.md 已完成事项记录；2026-08-07 追加 plan-25 Web 持仓输入模式 / plan-26 Web 配置编辑 / README SVG 架构图；2026-08-08 追加 env-benchmark-doc-update（--update-docs 环境耗时对照自动更新）；2026-08-16 三次合并 plan.md 已完成事项记录（plan-8/25/26/27/28 P4 实验功能项）；2026-09-10 四次合并 plan.md 已完成事项记录（plan-29 DeepSeek 峰谷定价周末闲时）；2026-09-11 五次归档——`docs-stm/plan/` 全部 14 份外部借鉴系列设计文档（plan-30~plan-38 + 指纹提示词覆盖）按借鉴来源分四目录迁入；2026-09-12 六次合并 plan.md 已完成事项记录（plan-29 引用、plan-40 / plan-41 完成态与 P4 实验功能表 plan-30~plan-41 整体迁入）
> 原始文件：`docs-stm/managements/plan.md`（当前迭代部分）
> 涵盖版本：v0.10.0 ~ v0.10.18（2026-08-03 ~ 2026-09-12）；plan-8 于 v0.10.10 实现、plan-25/26/27/28 于 v0.10.12 实现、README SVG 于 v0.10.13 实现（2026-08-06/07）、plan-29 于 v0.10.15 实现（2026-08-28）、plan-30~plan-38 外部借鉴系列于 v0.10.16~v0.10.17 实现（2026-09-10）、plan-39~plan-41 于 v0.10.19-dev 实现（2026-09-11 ~ 2026-09-12）
> 归档内容：本迭代已实现的计划项（plan-8 + plan-17~plan-41）设计文档 + 完成项摘要 + 推荐实施顺序 + 发布门禁记录（P0/P1/P2/P3 已完成事项记录 + P4 已随发布版本实现项自 plan.md 整体迁入）。plan-30~plan-41 的完成项摘要已随六次合并并入本文件。

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
- [`plan-env-benchmark-doc-update.md`](env-benchmark-doc-update/plan-env-benchmark-doc-update.md) — 环境耗时对照文档自动更新设计（`--mode bench --update-docs` 自动回填 test-coverage.md 环境耗时表，2026-08-08 归档）

### 外部借鉴系列（plan-30~plan-38 + 指纹提示词覆盖，2026-09-11 归档）

2026-09-04 ~ 2026-09-09 对三个外部仓库做借鉴评估，识别出的可借用点全部落地后，14 份「评估分析 + 实现设计」文档按**借鉴来源**分四目录归档：

**借鉴 TradingAgents-astock → `tradingagents-borrowing/`**（LLM 输入/输出质量治理 + 决策闭环）

- [`reflection-decision-loop-analysis.md`](tradingagents-borrowing/reflection-decision-loop-analysis.md) — plan-30 决策跨期反思闭环机理分析（两阶段延迟反馈：先记 `pending`，同标的再现时用真实行情结算方向正确率与超额 alpha）
- [`decision-reflection-implementation.md`](tradingagents-borrowing/decision-reflection-implementation.md) — plan-30 实现设计（`decision_reflection` 开关，`decision_ledger` 账本 + `decision_settlement` 结算）
- [`experimental-features-ui-surfacing.md`](tradingagents-borrowing/experimental-features-ui-surfacing.md) — 实验开关上屏改为由 `features.EXPERIMENTAL_FEATURES` 注册表统一驱动（TUI 菜单 S / Web 配置面板 / CLI `--experiment` 三面同源）
- [`llm-quality-signal-analysis.md`](tradingagents-borrowing/llm-quality-signal-analysis.md) — plan-31/32/33 三层质量治理分析（输入侧预消化 → 输出侧分级 → 决策头结构化）
- [`signal-pre-digestion-implementation.md`](tradingagents-borrowing/signal-pre-digestion-implementation.md) — plan-31 信号预消化实现设计（`signal_pre_digest` 开关 + 行业资金流向默认路径缺陷修复）
- [`decision-header-parse-implementation.md`](tradingagents-borrowing/decision-header-parse-implementation.md) — plan-33 决策头结构化与决策词归一解析实现设计（`decision_header_parse` 开关 + 边界纪律解析器）

**借鉴 BruceLanLan/augur → `augur-borrowing/`**（决策结算纪律 + 健壮性）

- [`augur-borrowing-analysis.md`](augur-borrowing/augur-borrowing-analysis.md) — augur 借鉴评估（决策-结算学习闭环 / 确定性数值信号沉淀 + live/demo 标签 / 健壮性三件套）
- [`signal-ledger-implementation.md`](augur-borrowing/signal-ledger-implementation.md) — plan-34 确定性数值信号账本实现设计（`signal_ledger` 开关，五类评级沉淀 + 默认 `live_only`）
- [`robustness-suite-implementation.md`](augur-borrowing/robustness-suite-implementation.md) — plan-35 健壮性三件套实现设计（数值归一防线 / 失败原因可读 / `doctor_check` 系统自检）

**借鉴 OpenBB Platform → `openbb-borrowing/`**（数据层适配 + 测试基建 + 凭据声明）

- [`openbb-data-provider-analysis.md`](openbb-borrowing/openbb-data-provider-analysis.md) — OpenBB 数据层工程借鉴评估（Fetcher 三段式 / 响应记录-回放 / 凭据就绪矩阵）
- [`datasource-adapter-contract-design.md`](openbb-borrowing/datasource-adapter-contract-design.md) — plan-36 数据源适配契约实现设计（三段式 TET + 标准字段 schema + alias 声明式归一，行情域三源试点）
- [`datasource-cassette-replay-design.md`](openbb-borrowing/datasource-cassette-replay-design.md) — plan-37 数据源记录-回放测试实现设计（自研轻量 cassette 引擎，真实响应进仓库离线回放）
- [`datasource-credential-ready-design.md`](openbb-borrowing/datasource-credential-ready-design.md) — plan-38 数据源凭据声明与就绪指引实现设计（`datasource_credential_ready` 开关，缺凭据主动跳过并给可读指引）

**自审缺陷修复 → `llm-fingerprint-prompt-coverage/`**

- [`llm-fingerprint-prompt-coverage-design.md`](llm-fingerprint-prompt-coverage/llm-fingerprint-prompt-coverage-design.md) — LLM 模块缓存指纹的提示词覆盖设计（提示词实际承载的派生段进指纹 + 辩论综合键覆盖白脸/黑脸完整正文，无开关）

### 功能开关与基金取数（plan-39 / plan-40，2026-09-12 批准）

两份设计实现落地后由 `docs-stm/plan/` 按主题子目录迁入：

- [`feature-switch-registry-unification-design.md`](feature-switch-registry/feature-switch-registry-unification-design.md) — plan-39 功能开关注册表统一设计（面板可见性 / 默认值 / 产物自述三事解耦为单条开关声明 + 分组属性，TUI / Web / CLI 三渠道入口由注册表派生）
- [`feeder-penetration-and-holdings-fetch-design.md`](feeder-fund-penetration/feeder-penetration-and-holdings-fetch-design.md) — plan-40 联接基金穿透与基金持仓取数通道修正设计（取数阶梯次序修正 + 目标 ETF 代理底层暴露）

## v0.10.x 已完成项

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| plan-8 | **轻量 Web UI** | Web 浏览器模式：Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载；`src/python/web/` 全量创建（server/app/handlers/upload/progress/runs + templates/static）+ `flask==3.1.2` 依赖 + launch.sh/ps1 web 入口；上传安全（§6.1）+ 预览防穿越（§6.2）+ `unit_web` marker + 5 测试文件 54 用例；三阶段（MVP/功能补齐/体验打磨）+ 用户文档（how-to-start 方式四 + faq Web 问答 + README 提点） | 阶段1/2/3（约 5.5d） | ✅ 已完成（v0.10.10，2026-08-06） |
| plan-17 | **数据质量仪表盘** | 「数据源可用性矩阵」章改造为「数据质量仪表盘」：品种级覆盖诊断（`read_holdings` 状态标注）+ 源级健康 + 数据可信度/异常跳变检测；开关 `report_submodules.data_quality`（默认关） | 轮1~3 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-18 | **行动建议章** | 新增「行动建议」章（`always` 类型，`enable_action` 默认关）：调仓建议（可行化层，份额取整/现金约束/费用）+ 交易纪律 + 收益归因（品种贡献占比）；「智囊团深度复盘」章「行动摘要」子块（单源计算、两处呈现） | 轮4~7 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-19 | **持仓关系矩阵合并** | 物理合并「持仓重合度矩阵」+「持仓相关性矩阵」→「持仓关系矩阵」（sheet key `position_relationship`），一章分上下矩阵区块；删除旧 sheet 注册 + 数据契约增删 + registry.number 重排 | 轮8 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-20 | **历史增强** | 物理合并「组合历史走势」+「历史回撤分析」→「组合历史走势与回撤」（`portfolio_history_drawdown`，走势表+回撤矩阵区块）+ 危机区间标注 + 尾部风险（VaR）；「组合演进」章快照差异摘要 | 轮9~11 | ✅ 已完成（v0.10.1，2026-08-04） |
| plan-21 | **风格与选基** | 物理合并「基金风格分析」+「因子暴露分析」→「风格与因子分析」（`style_factor` 一章三区块：风格表 + 因子回归 + 行业 Beta 子表，章节数 20→19）；基金业绩分析章候选基金比较增强模式（`candidate_compare` 默认关） | 轮12~13 | ✅ 已完成（v0.10.3，2026-08-05） |
| plan-22 | **成本流水** | 持仓 Excel 可选「交易流水」「分红流水」页签 + 资金加权收益（XIRR）+ 成本分档 + 分红累计；「投资分析汇总」/「市值核算明细表」/「持仓分类表」三页签渲染（`fund_flow_data` 契约，`cost_lots` 默认关）+ HTML 三处条件渲染补遗 | 轮14~16 | ✅ 已完成（v0.10.3，2026-08-05） |
| plan-23 | **估值与温度** | 「资产穿透TOP10」章估值分位（当前 PE/PB + 价格分位代理，`valuation_percentile` 默认关）+「投资分析汇总」章市场温度（价格分位+均线偏离+波动率三因子，温度计无仓位指令，`market_temperature` 默认关）；`valuation_data`/`market_temperature_data` 契约 | 轮17~18 | ✅ 已完成（v0.10.4，2026-08-05） |
| plan-24 | **导航与收尾** | HTML 报告左侧目录五组折叠导航（`<details>/<summary>` 分组 + 组徽标计数 + 窄屏扁平兜底）+ 文档快照与用户手册同步（folders/test-coverage 统计、reports-instruction 序号核对、how-to-config 开关行） | 轮19~20 | ✅ 已完成（v0.10.4，2026-08-05） |
| plan-25 | **Web 持仓输入模式** | Web「生成用途」双模式：临时试算（快照隔离 `web/` 域，不污染共享时间线）/ 正式更新（上传覆盖备份 `.bak` 或用存量直接读正式文件，快照共享）；`history_snapshot` 全公开函数 + 消费/编排层 `namespace`/`snapshot_namespace` 透传；`web/holdings_update.py` 备份+原子提升；`_handle_create_run` mode/use_existing 组合校验；前端生成用途/输入来源 UI；语义表登记 `snapshot_namespace`/`web_input_mode`/`use_existing`/`holdings_update` | 6 阶段 | ✅ 已完成（v0.10.12，2026-08-07） |
| plan-26 | **Web 配置编辑** | Web 修改与 TUI 完全一致的配置全集（7 组）：`web/config_edit.py` 白名单 + `GET/POST /api/config/edit` + 同源守卫 + `.bak` 备份；`write_llm_settings` 共享原语（TUI 改委托）；匿名化读路径修正；前端配置面板即改即存；测试 35+42 用例 + smoke 11 断言 | 6 阶段 | ✅ 已完成（v0.10.12，2026-08-07） |
| plan-27 | **前端资产统一归入 src/static/** | Web UI 前端 + 报告模板归入 `src/static/`（三合一），`src/python/` 仅纯 Python；`app.py`/`html_jinja_env` 加载点改 `PROJECT_ROOT` 派生；5 个按路径读模板测试同步 | 基础设施重构 | ✅ 已完成（v0.10.12，2026-08-07） |
| plan-28 | **三模式使用指南体系** | how-to-use-web-mode/cli-mode 新建 + tui-menu 重命名；定时任务并入 CLI 指南 §11；README/CLAUDE/folders 索引统一；test-coverage 耗时刷新 | 纯文档 | ✅ 已完成（v0.10.12，2026-08-07） |
| plan-29 | **DeepSeek 峰谷定价周末闲时** | 按 DeepSeek 2026-08-23 官方方案适配周末（周六/周日）全天统一按闲时（低谷）价计费、不再区分峰谷：`core/constants.py` 新增 `PRICING_WEEKEND_ALWAYS_IDLE`（默认 True）+ `llm/pricing.py` 新增同名模块级变量与 `_is_weekend()` 判定并据以改写 `estimate_cost()` 峰谷分支；`pricing.weekend_always_idle` 配置（默认 true，设 false 恢复周末按钟点区分）同步 `config/_llm_settings_defaults.py` 默认模板与用户 `data/config/llm_settings.json`；`test_llm_utils.py::TestPricing` 周末闲时规则 4 例（默认开/周末高峰按闲时/周末缓存命中按闲时价/关闭恢复峰谷）+ how-to-config-llm.md、llm-technical.md §10.4 与附录 B 文档同步 | 定价适配 | ✅ 已完成（v0.10.15，2026-08-28） |

### P0 — 发布门禁（已完成）

> 发布门禁（轮 21）：v0.10.3/v0.10.4 两次发布均通过 `test_runner.py --mode verify,regression` 全量 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致 + 数据快照刷新 + registry.number 连续编号复核 + 数据契约增删复核（changelog v0.10.3/v0.10.4）。

- ✅ **全链回归与发布门禁**（迭代计划轮 21）：`test_runner.py --mode verify,regression` 3256 全过 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致（v0.10.4）+ 数据快照刷新（test-coverage 5038 / folders 统计）+ registry.number 连续编号复核 + 数据契约增删复核。**v0.10.4 已发布**（2026-08-05）。
- ✅ **全链回归与发布门禁**（迭代计划轮 21）：`test_runner.py --mode verify,regression` 3169 全过 + 3 check 脚本 `--ci` 全 [OK] + 版本号全链一致（v0.10.3）+ 数据快照刷新（test-coverage 4916 / folders 统计）+ registry.number 连续编号复核 + 数据契约增删复核。**v0.10.3 已发布**（2026-08-05）。

### 推荐实施顺序（①~⑧ 全部完成）

> 结合架构约束、收益/风险与最新依赖状态重排的推荐实施次序。①~⑧ 为推荐先后；括号内为计划项优先级归类。plan-4 已放弃，不列入实施序列；plan-8/plan-10 原归 P4 实验功能，不列入本迭代实施序列——plan-8 已于 v0.10.10 随 Web 模式独立完成（见本文件「P4 — 实验功能」章节），plan-10 仍留 plan.md 待办。

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

### P4 — 实验功能（已随发布版本实现）

> P4 实验功能（缺省关闭、选做无排期）中已随发布版本实现并归档的项，2026-08-16 自 plan.md 迁入本文件。仍保留在 plan.md 的 P4 实验项仅 `plan-10` 日志可视化（未实现）。

#### ✅ `plan-8` 轻量 Web UI（[`plan-web-ui.md`](web-ui/plan-web-ui.md) + [`plan-web-ui-implementation.md`](web-ui/plan-web-ui-implementation.md)）— 已完成（v0.10.10，2026-08-06）

Web 浏览器模式（Flask 服务 + 上传页面 + 触发管线 + 结果预览/下载）。**三阶段全部落地**——阶段1（MVP 核心）`src/python/web/` 全量创建（server/app/handlers/upload/progress/runs + templates/static），依赖接入 `flask==3.1.2`（pyproject + requirements.txt），`launch.sh`/`launch.ps1` 增 `web` 入口参数；上传→生成→轮询→预览/下载全链路贯通（复用 `generate_report` 管线，report/ 层零改动），上传安全（§6.1：uuid 重命名/扩展名白名单/PK 魔数/10MB/行数上限/原子落盘/TTL）与预览防穿越（§6.2）就位；`unit_web` marker 注册 + 5 个测试文件（upload/upload_edge/progress/runs/handlers，54 用例）全绿。阶段2（功能补齐）索引页按 `get_config()` 回填表单默认（历史走势跟随配置 + 强制 LLM 开关）、进度编号步骤 + 当前阶段展示、状态区（数据源健康 `/api/health` 含 `?fresh=1` 重测 + 历史运行记录 `/api/runs/history`）、错误处理完善（exit_code 映射 / 严重态产物裁剪 rf-254 / FILE_EXPIRED 重置 / 重新生成按钮）；web 目录 64 用例全绿。阶段3（体验打磨 + 用户文档）样式打磨（design-quality：拖拽高亮/渐变进度条/卡片悬浮阴影/状态区分栏/语义色）、加载态与轮询节流、375px 响应式（`prefers-reduced-motion` 减动效）、a11y（文件输入 sr-only、progressbar aria、aria-live）、用户文档（how-to-start 方式四 Web 模式 + faq 高频问题 + README 提点）；web 目录 64 用例全绿。三阶段 P0 门禁通过，设计文档归档至本目录 `web-ui/`。

#### ✅ `plan-25` Web 持仓输入模式（[`plan-web-holdings-input-modes.md`](web-holdings-input-modes/plan-web-holdings-input-modes.md)）— 已完成（v0.10.12，2026-08-07）

Web「生成用途」双模式：临时试算（快照隔离 `web/` 域）/ 正式更新（上传覆盖备份 `.bak` 或用存量直接读正式文件）。**六阶段全部落地**——① 存储层 `history_snapshot` namespace 子目录（save/load_latest/load_all/list_all/prune + 白名单校验）；② 消费层 `capture_snapshot`/`build_evolution_data`/`build_snapshot_diff` + 两个 `_inject_*` 透传 `snapshot_namespace`；③ 编排层 `generate_report` + `_report_generation` 双路径透传；④ web 入口 `holdings_update.py`（单槽 `.bak` 备份 + 原子提升）+ `_handle_create_run` mode/use_existing 解析与组合校验（正式+用存量禁止 file_id→400）+ `_web_input_mode_snapshot_domain` 模式→快照域映射；⑤ 前端生成用途/输入来源单选 + 覆盖警示 + 确认勾选（index.html/main.js/style.css），resetFlow 区分正式-用存量；⑥ 文档与门禁——语义表登记 `snapshot_namespace`/`web_input_mode`/`use_existing`/`holdings_update`，folders/三手册/changelog 同步。smoke-web.py 10 断言全通过，dev-verify 1970 + 4 checks `--ci` 全 [OK]。设计文档已归档至本目录 `web-holdings-input-modes/`。

#### ✅ `plan-26` Web 配置编辑（[`web-config-edit.md`](web-config-edit/web-config-edit.md)）— 已完成（v0.10.12，2026-08-07）

Web 模式修改与 TUI **完全一致**的配置项全集（7 组：自由文本路径 3 / 报告章节开关 5 / 增强子模块开关 6 / 匿名化枚举 4 档 / 对比指数池 / LLM 分析章节开关 5 / 辩论实验功能开关 3）。**六阶段全量完成**——① 共享层抽取 `write_llm_settings`（TUI 改委托，行为零变化）；② 后端核心 `web/config_edit.py`（白名单 + 面板读取 + 应用编辑 + `.bak` 备份）+ `handlers.py` 路由 `GET/POST /api/config/edit` 与同源守卫；③ 匿名化读路径修正（tui_menu `_show_privacy_and_security_status` + web `_build_system_info` 读顶层 `anonymization.mode`）；④ 前端配置面板（index.html「③ 配置编辑」card + main.js 即改即存 + error_code 分支）；⑤ 测试补齐（`test_config_edit.py` 35 用例 + `test_config_edit_edge.py` 42 用例 + `smoke-web.py` 扩展至 11 项断言）；⑥ 文档与门禁——changelog/how-to-config/faq/folders 同步 + 语义表登记 3 行。附带修复 smoke-web `_DEFAULT_CONFIG` 顺序污染。设计文档已归档至本目录 `web-config-edit/`。

#### ✅ `plan-27` 前端资产统一归入 `src/static/`（基础设施重构）— 已完成（v0.10.12，2026-08-07）

将分散在 Python 包内的非 Python 前端资产统一归入 `src/static/`（报告图表 bundle + Web UI 前端 + 报告模板三合一），`src/python/` 仅保留纯 Python 代码。**已完成**——Web UI 前端（index.html/main.js/style.css）自 `src/python/web/{templates,static}/` 归入 `src/static/web/`（`app.py` Flask template/static folder 改 `PROJECT_ROOT` 派生，`/static/main.js` 与 `render_template("index.html")` 契约不变）；报告 Jinja 模板（report_template.html/whatif_template.html/partials/）自 `src/python/tmpl/` 归入 `src/static/tmpl/`（`html_jinja_env.py` 单加载点）；5 个按路径读模板的测试路径同步。`smoke-web.py` 10/10 + report/web/llm 单测 2395 passed；folders 目录树/统计表同步；`src/static/README.md` 资产说明滞后登记 rf-266 已修复。

#### ✅ `plan-28` 三模式使用指南体系：TUI/CLI/Web 各一份 + 文档索引统一（用户文档）— 已完成（v0.10.12，2026-08-07）

plan-8/25/26/27 实现后用户文档从「单份菜单手册 + 定时任务手册」演进为三模式各一份分册并统一索引。**已完成**——三份模式分册（`how-to-use-web-mode.md` 新建 / `how-to-use-cli-mode.md` 新建 / `how-to-menu.md` → `how-to-use-tui-menu.md` 重命名）；定时任务并入 cli-mode.md §11（`how-to-schedule.md` 删除，活跃引用改指）；索引统一（README 启动方式三节 + 功能特性三模式条目 + 用户指南表指向各分册；CLAUDE.md 用户文档列表顺序与 README 索引一致；folders.md 目录树去重 + 统计表刷新）；test-coverage `bench --update-docs` 回填 dragonball 列耗时。P0 门禁（dev-verify 2005 + 4 checks `--ci`）全 [OK]。纯文档任务，无运行时代码变更。

### P1 — 已完成（plan-29 ~ plan-41 完成态，2026-09-12 六次合并迁入）

> 无待办项。plan-29（DeepSeek 峰谷定价适配周末全天闲时）已于 v0.10.15（2026-08-28）完成并归档，完成项摘要见 [`archived_plan.0.10.x.md`](../archive/v0.10.x/archived_plan.0.10.x.md)。
>
> **plan-40（已完成 2026-09-11）**：QDII 联接基金拿不到最新报告的修复——用户报障「QDII 类基金取不到最新报告，无法准确分析穿透资产」。**批次① 取数阶梯次序修正（缺陷修复，不加开关，默认路径生效）**：`providers/tiantian_holdings.py::fetch_fund_holdings` 由「主页面优先」改为「季报年份域（最近 4 个完整季度回溯，唯一携带真实报告期的通道）→ 主页面（前十大；报告期不从此处取）→ 季报无年份兜底（最早可得报告，通常已陈旧）」——次序本身即陈年数据隔离（兜底压到第 3 跳），**不在取数层复制时效判据**（判据唯一归属 `report/holdings_freshness.py`）。**批次② 联接基金穿透（`feeder_penetration`，常规组默认开）**：ETF 联接基金的资产即其目标 ETF、本身不持有股票，其季报股票表按构造为空（实测 `016055` 四个近季度响应体均为 59/50 字节空内容），修复前恒为「持仓不可用」；开启后由 `fetcher/fund.py::with_feeder_penetration` 以目标 ETF 的持仓与报告期代理其底层暴露（目标 ETF 由主页面锚点**动态解析**、不维护映射表，结构深度恒为 1；**幂等**后处理在单条与批量两处接缝调用——批量路径 `execute_with_cache_check` 缓存命中时任务不执行，穿透若只在网络路径做则热缓存下静默失效）。归因口径 **100%（不折算持有比例）**并在报告中显式标注该已知偏差。设计文档见 `docs-stm/archive/v0.10.x/feeder-fund-penetration/feeder-penetration-and-holdings-fetch-design.md`。
>
> **plan-41（已完成 2026-09-12）**：读侧增强类开关转正（承接 plan-39 注册表统一）——分组与默认值解耦后，「转正」只剩「改分组 + 改默认值」两个字段，本轮据此把五项**只在读侧追加内容、不新增调用次数、不写持久化状态**的开关自实验组移入常规组并默认开启：`signal_pre_digest`（信号预消化）、`module_quality_gate`（模块级质量分级）、`decision_header_parse`（结构化决策头）、`llm_debate_conditional`（辩论-条件推理）、`datasource_credential_ready`（数据源凭据就绪）。**判据**是「开启的代价只在读侧」——在既有提示词或既有产物流水线上追加一段由**已算出**数据派生的内容，无新增 LLM 调用次数、无新写持久化文件、无隐式网络与耗时，且内容有确定收益（方向性结论替代裸数值 / 结构化契约替代表格猜测 / 质量分级提示读者降级参考 / 缺凭据给可读指引）。五项 `affects_report` 照实答 `True`（确实改变产物内容），故 Web 面板保留「（影响报告）」标记，关闭杠杆保留为 `features.json` 置 false。**刻意不转正**：`decision_reflection` / `signal_ledger`（写盘积累型——默认开启等于未经用户知情选择即向 `data/state/*.jsonl` 落账；本项无功能开关，不属本轮范围）、`llm_debate_procon`（调用次数放大型——把一次 `expert_review` 换成最多三次）、`llm_debate_qa_concentration`（触发面最窄、覆盖最薄，待真实触发样本）。**一次性副作用**：改变提示词的开关其缓存后缀函数由「默认返回空」翻为「默认返回非空」（`_dh` / `_c` / 信号块摘要），升级后首次运行换键重生成一次，属预期行为并已写入变更记录。转正口径沉淀为 `developer-guide.md` 的「读侧增强类开关也应转正（第三类首例）」段 + 「刻意不转正的两类」说明。自审记录 rf-353。


### P4 — 实验功能（plan-30 ~ plan-41 全部完成，2026-09-12 六次合并迁入）

> **借用探索候选**（借鉴外部仓库 TradingAgents-astock + BruceLanLan/augur + OpenBB 的机制）：当前迭代已完整发布，以下为借鉴评估识别出的可借用点登记，均按 P4 实验级（缺省关闭、需显式启用）暂存，先设计评估后实施。TradingAgents 借鉴评估（2026-08-29）识别 4 条——**plan-30/31/32/33 均已深入分析**（**plan-30、plan-31、plan-32、plan-33 已实施完成**，见下）；augur 借鉴评估（2026-09-09）识别 3 条——**plan-30 合并评估 + plan-34、plan-35 已实施完成**；OpenBB Platform 借鉴评估（2026-09-09）识别 3 条——**plan-36、plan-37、plan-38 均已实施完成**。分析文档已随本迭代完成一并归档至 `docs-stm/archive/v0.10.x/`（按借鉴来源分目录）：`tradingagents-borrowing/`（`reflection-decision-loop-analysis.md`、`decision-reflection-implementation.md`、`llm-quality-signal-analysis.md` 及三份同源实现设计）、`augur-borrowing/augur-borrowing-analysis.md`、`openbb-borrowing/openbb-data-provider-analysis.md`。语义名为拟用名，落地前须按「先定语义名再设计」复核。已完成实验项见归档设计文档 `docs-stm/archive/v0.10.x/log-visualization/plan-log-visualization.md`（`plan-10` 日志可视化）与 `docs-stm/archive/v0.10.x/tradingagents-borrowing/decision-reflection-implementation.md`（`plan-30` 决策跨期反思闭环）。
>
> | # | 任务 | 优先级 | 状态 |
> |---|------|:------:|:----:|
> | **plan-30** | 决策跨期反思闭环（借鉴 TradingAgents-astock `agents/utils/memory.py` + `graph/reflection.py` 两阶段延迟反馈 + augur `learning.py`/`registry.py` 预测-真实结果结算）：对判断（含 LLM 看多看空与确定性再平衡/行动建议）不即时评判——当次记作 `pending` 决策；同标的再现时用真实后续行情结算（方向正确率、超额 alpha），产出教训回灌后续分析提示词。合并 augur 借鉴点 #1：结算改**确定性命中率统计**（augur：bullish 需 +2% 才算对、≥3 样本才生效、立即持久化防进程重启丢失、空 context 预测跳过），与 TradingAgents 的 LLM 反思回灌互补可合成一套。语义名（已落地）`decision_reflection`。分析见 `reflection-decision-loop-analysis.md` + `augur-borrowing-analysis.md` §建议A。 | P4 | 已完成（2026-09-10，默认关闭实验项；实现设计见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/decision-reflection-implementation.md`） |
> | **plan-31** | 信号预消化（借鉴外部数据层信号文本 `Signal: … (bullish/bearish)` 前缀）：把资金流/涨跌等数值指标在进 LLM 前预消化为带方向标注的一句话信号（净流入=看多…），降低模型读裸数值自行解读的误判率。语义名（已落地）`signal_pre_digest`。分析见 `llm-quality-signal-analysis.md`。 | P4 | 已完成（2026-09-10）：**A 缺陷修复（无开关，默认路径生效）**——行业资金流向段改「主力净流入/主力净流出 + 非负量」并按净额分方向排名（原「主力净流入-5,000,000」label 与数值自相矛盾，且数据源无序导致前 5 行无排名语义）；**B 实验增强（`signal_pre_digest` 默认关）**——市场温度/估值分位/尾部风险预消化为 `信号：…` 行注入专家复盘与持仓体检提示词。实现设计见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/signal-pre-digestion-implementation.md` |
> | **plan-32** | 模块级质量分级注入（借鉴 `agents/quality_gate.py` A~F 分级——劣级**不阻断不重试**，而是把「降级 C/D/F」说明注入下游模块）：把现有【数据质量降级】披露从数据源侧扩展到 LLM 输出侧，按完整性/一致性给单模块输出分级并透传到后续拼接。语义名（已落地）`module_quality_gate`。 | P4 | 已完成（2026-09-10）：**A 同域缺陷修复（无开关，默认路径生效）**——`rf-295` `report/_llm_news.py::_submit_llm_future` 漏传 `degradation_events`，致持仓体检第 5 维「数据质量」恒读「今日无降级记录，所有数据源正常」，与专家复盘降级摘要自相矛盾；**B 实验增强（`module_quality_gate` 默认关）**——`report/llm_quality.py` 对 4 个 LLM 模块输出按完整性/篇幅评 A~F，低评级中「内容在但存在缺陷」者（缺章节/偏短）随内容头部注入【内容质量提示】横幅，**只标注、不阻断、不重试、不写回缓存**（内容缺失型已有占位/空内容醒目提示，不叠加）。横幅复用模块 HTML 字符串作载体（与截断标记/缓存命中行同一载体，HTML+Excel 双路径生效）。分析见 `llm-quality-signal-analysis.md` §2 |
> | **plan-33** | 决策头结构化 + 确定性解析兜底（借鉴 `bind_structured` schema 输出 + `agents/utils/rating.py` 词边界确定性解析）：评级/决策头先走结构化输出，落空时用确定性规则兜底解析（防"评级静默误判/污染绩效统计"这类隐患）。语义名（已落地）`decision_header_parse`。 | P4 | 已完成（2026-09-10）：**A 缺陷修复（无开关，默认路径生效）**——决策词解析自子串包含改为带边界纪律的**归一解析器**（`core/decision_header.py`：标签优先 / 长词优先 / 否定守卫 / 复合词左边界 / 二义不猜 / 判不出返 None），`report/decision_llm_capture.py` 改走该解析器，「不建议加仓」「加仓或减仓」「暂不减仓」不再被判成相反方向写入决策账本；**B 实验增强（`decision_header_parse` 默认关）**——专家复盘提示词追加一行受控 JSON 决策头契约，抽取侧优先读结构化头（逐字段归一校验）、失败回落确定性表格解析，两路产物形状统一。缓存指纹读写两侧同调后缀函数。实现设计见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/decision-header-parse-implementation.md` |
> | **plan-34** | 确定性数值信号沉淀 + live/demo 标签纪律（借鉴 augur `backtest.py` `data_source` 标签 + 排行榜默认 `live_only`）：把我方已有确定性算法评级——市场温度低估/合理/高估、估值分位 tier、尾部风险 VaR、风格因子、再平衡超限——沉淀为可回测记录并附真/合成标签，排行榜/统计默认只算真实，防合成数据冒充真实战绩；与 plan-30 决策记录可合并成一套。语义名（已落地）`signal_ledger`。分析见 `augur-borrowing-analysis.md` §建议B。 | P4 | 已完成（2026-09-10）：**A 缺陷修复：本项无**（五类评级输出确定性可复现，无「算错」可修；不制造缺陷凑 A/B 结构）；**B 实验增强（`signal_ledger` 默认关）**——`core/jsonl_store.py` 抽出已被重复两份的原子 JSONL 原语（`perf`/`decision_ledger` 改委托，不新增第三份拷贝）、`core/signal_ledger.py` 账本（登记幂等/折叠统计/**默认 `live_only`**/摘要与缓存后缀/非有限数值归一）、`report/signal_record.py` 适配器（唯一持有语义词表映射，`core/` 不依赖 `analysis/`）、报告第 5d 步 seam、专家复盘提示词注入账本上下文。**来源标签复用既有数据质量设施**（逐品种 `data_freshness` + 降级事件）而非新造合成数据开关；仅可证明为实时才算实时，无逐品种条目时乐观取实时但显式记理由。实现设计见 `docs-stm/archive/v0.10.x/augur-borrowing/signal-ledger-implementation.md` |
> | **plan-35** | 健壮性三件套（借鉴 augur）：① `safe_num` 全链路数值归一（防 NaN/±inf 污染下游链）；② 数据源失败「错误即 UX」——provider 失败原因进可读 `data_error` 字段、主链路不中断；③ `doctor` 类自检命令（一次性盘点 key/连通性/缓存/路径，复用现有 `check_sources.py`）。语义名（拟）`robustness_suite`。分析见 `augur-borrowing-analysis.md` §建议C。 | P4 | 已完成（2026-09-10）：**A 缺陷修复（无开关，默认路径生效）**——① **数值归一防线**：`providers/_utils.safe_float` 及 tencent/sina_kline/akshare_extras/eastmoney_industry 各解析器对 `float("nan")`/`float("±inf")` 的 `try: float(x) except` 兜底完全失效（两者都不抛异常），脏值直入市值/收益序列/绘图数据；统一收敛到 `core.num_utils.safe_num` 显式拦下非有限值，合法输入行为逐字不变；② **失败原因可读**：provider 链路失败原因此前只留 `failure_type` 短标识（`transport`/`empty`），用户看不懂哪个源、为什么失败；新增 `fetcher/chain.FailureDiagnostics` 采集「展示名(原因)」序列随 `DegradationEvent.detail.message` 透传到 `data_source_matrix` 降级明细，无原因时回落原短标识保证既有输出逐字不变。**B 实验增强（`doctor_check` 默认关）**——`core/doctor.py` 一键自检（环境/配置/目录/功能开关/数据源适配/数据源凭据/数据源七组，失败项附可执行修复建议）；零重依赖（不 import pandas，因 pandas 缺失正是它要报的场景）、自身永不抛异常。三面上屏：`doctor` CLI 子命令（`--offline`/`--timeout`，**不受开关约束**——配置损坏正是它要诊断的场景，若被开关拦住即成死锁）、TUI 菜单 `[D]`（受开关约束）、Web 运行状态区自检卡片 + `GET /api/doctor`。CLI 实验开关由 `--experiment doctor_check` 统一控制。**后续转正**：`doctor_check` 移出实验注册表、默认值改 `True`（只读诊断，默认关的代价是环境出故障者恰好看不到它），TUI/Web 门控保留、`features.json` 置 false 仍可隐藏入口。实现设计见 `docs-stm/archive/v0.10.x/augur-borrowing/robustness-suite-implementation.md`；自审记录 rf-299~rf-301 |
> | **plan-36** | 数据源适配契约（借鉴 OpenBB Fetcher 三段式 TET + 标准字段 schema + alias 声明式归一）：定义「数据域标准字段」一份 + 每数据源只实现「参数转译 → 抓取 → 映射到标准字段」三小函数；字段改名/换算用 alias/校验器在解析期归一，替代各 provider 手拼 dict。**只对新增数据源/加字段试点，不回改存量 provider**；不搬 OpenBB 的 Provider 注册元架构/覆盖矩阵/命令路由。语义名（拟）`provider_adapter_contract`。分析见 `openbb-data-provider-analysis.md` §建议A/B。 | P4 | 已完成（2026-09-10）：**语义名定为 `datasource_adapter`**（开关名同此）——`fetcher/source_adapter.py` 提供三段式契约基类（`transform_query`/`extract_data`/`transform_data`）+ 域注册表 + 离线自检（`survey_adapters`），`schemas/datasource_fields.py` 定义行情域标准字段记录（类型注解即缺省语义：`float`→0.0、`float \| None`→None、`str`→空串，数值统一经 `safe_num` 拦 NaN/±inf）；默认映射由 **aliases（上游字段→标准字段）+ defaults（源缺省）+ 类型注解**三样数据驱动，输出恒为全标准字段；`adapter_chain_slots(domain)` 把适配器映射成 Provider Chain 两槽，链路顺序/缓存键/熔断/降级全部复用 `fetch_with_fallback`（**不新造第二条获取路径**）。**试点范围**：仅行情域三源（`quote_adapters.py`），与既有转换函数逐源等价——唯一有意差异是东财既有转换函数不含 `market_cap`/`pe` 而契约恒为全字段（补 `None`，下游一律 `.get()` 读取，语义不变），由 `test_quote_adapter_parity.py` 锁定；**存量 provider 不回改**。接入点 `fetcher/price.py::_price_chain_slots()`：开关关→返回既有映射对象本身（行为逐字节不变），开→改用适配器映射。三面上屏由功能开关注册表自动驱动（TUI 菜单 S / Web 配置面板 / CLI `--experiment datasource_adapter`；后随 plan-39 注册表统一转正为默认开启）；`doctor` 新增「数据源适配」组，**开关关闭时也照常核验契约声明与自检**。实现设计见 `docs-stm/archive/v0.10.x/openbb-borrowing/datasource-adapter-contract-design.md`；自审记录 rf-306（命令行实验开关对早期返回命令不可达，随本条一并修复） |
> | **plan-37** | 数据源记录-回放测试（借鉴 OpenBB pytest-recorder/vcrpy cassette）：对高价值数据源（基金净值/持仓解析）录真实响应进 git 跟踪 cassette，无 `--record` 跑即离线回放——补上「真实响应体的解析/归一路径」的回归覆盖（现有 mock 测试测不到），不违反「测试不碰真网络」隔离纪律；需评估引依赖 vs 自研轻量回放。语义名（拟）`datasource_cassette_test`。分析见 `openbb-data-provider-analysis.md` §建议C。 | P4 | 已完成（2026-09-10）：**语义名定为 `cassette`**（引擎模块名即语义名；表中另登记 `cassette_checks` 绑定表与 `use_transport_factory` 注入点）——**自研轻量引擎，不引 vcrpy/responses/httpretty 任何依赖**。`core/cassette.py` 提供请求键归一（剥离易变查询参数）、录制/回放传输、原子写盘、`verify_cassettes` 解析校验；**注入点为「HTTP 客户端统一」约束下的唯一 HTTP 构造点**（`core/http_client.py::use_transport_factory` + `make_transport`，工厂每次返回新传输实例——`httpx.Client.close()` 会连带关闭其传输），全项目 provider **零改动**即被替换为回放源。**存储口径**：存解码后的响应体文本 + 字符集（真实响应为 gzip + GBK/GB18030/utf-8 混用），回放时按录制字符集重新编码并丢弃 `content-encoding`/`content-length`/`transfer-encoding`，否则 httpx 会二次解压或按旧长度截断。**离线保证**：回放未命中抛 `CassetteMissError` 且**绝不回落真实网络**；该异常**刻意不继承 `httpx.HTTPError`**——否则 provider 会将其当作网络错误降级到别的源，把「夹具漏录」静默改写成「换个源重试」。**录制保证**：需 `--run-live` + `--record-cassettes` 双显式开关（非 live 用例的真实请求已被 conftest 阻断，机制上不可能意外录制）。**已录 6 份真实响应**（腾讯行情/K 线、新浪行情、东财基金净值、天天基金持仓与季度持仓）。**维护入口**：`cassettes` / `cassettes --verify`（早返回命令，无需 config、不受实验开关约束；解析失败退出码 2）。**不设功能开关**——cassette 只在测试进程与维护命令中被读写，报告管线不读它、不产生任何运行时行为分支（理由见设计文档「为何不设开关」）。实现设计见 `docs-stm/archive/v0.10.x/openbb-borrowing/datasource-cassette-replay-design.md`；自审记录 rf-307（CLI 进程入口丢弃退出码，随本条一并修复） |
> | **plan-38** | 数据源凭据声明与就绪指引（借鉴 OpenBB `Provider(credentials=[...])` + 缺失 `"Missing credential ... Check <website>"` 可读报错）：若接入需 API key 的数据源，能声明「此源需 key」并在缺失时给可读指引与就绪提示，而非运行时裸报错。当前免费源为主，**远期/需 key 源时再启用**，可并入 `config` 层 + `check_sources.py`。语义名（拟）`datasource_credential_ready`。分析见 `openbb-data-provider-analysis.md` §建议D。 | P4 | 已完成（2026-09-10）：**语义名定为 `datasource_credential_ready`**（开关名同此）——`core/datasource_credential.py` 提供 `CredentialSpec` 冻结声明 + `CREDENTIAL_SPECS` 注册表 + 就绪判定（**空白串视为缺失**；源未声明→不需凭据）+ 可读指引（「缺少凭据（数据源：X）——请设置环境变量 VAR；申请地址：URL」，措辞对齐既有 LLM 凭据指引）+ 就绪矩阵（**自身不抛异常**，体检与健康检查共用）。**声明即数据、当前表为空**（全部免费源是事实），机制由**注入合成声明**的单元测试证明可用——不为演示把假数据源写进生产注册表。四处落地：① `fetcher/chain.py` 链路预检——`fetch_with_fallback` 与**历史走势的 `_try_providers` 遍历循环**（设计原稿只写了前者，只堵一处等于机制半应用）在熔断检查后跳过缺凭据的 provider，**不计入熔断失败计数**（配置级问题≠源不可达），仅以可读原因进 `FailureDiagnostics` 上屏；② `check_sources.py` ——`_checks` 扩为 `(source_id, 显示名, 用途, 探测函数)`（按 provider 名对齐、新闻源带 `_news` 后缀消歧），缺凭据**不发起探测**，对称使用文件中已定义但一直未用的 `_SKIP` 符号 `⏭️`，跳过项**不影响退出码**，末尾追加就绪摘要行；③ `doctor.py` 新增 `GROUP_CREDENTIAL`「数据源凭据」组（无声明报「均无需凭据（免费源）」、缺失报失败项附变量名建议），「数据源」组过滤凭据跳过项**避免同一问题被两组重复计失败**；④ 开关由功能开关注册表自动三面上屏（TUI 菜单 S / Web 配置面板 / CLI `--experiment`），**关闭时零行为分支、输出逐字节同现状**（实测 doctor 无该组、check-sources 无就绪行）。**安全口径**：凭据只从环境变量读，**值永不落日志/报告/缓存**。新增 50 例 / 6 测试文件（含 `*_edge.py` 隔离与 conftest 单例重置 fixture）。实现设计见 `docs-stm/archive/v0.10.x/openbb-borrowing/datasource-credential-ready-design.md` |
> | **plan-39** | 功能开关注册表统一（架构自省）：实验功能开关注察表把「面板可见性 / 默认值 / 是否进产物自述」三件事拧在一个容器里，导致「转正」会连带摘掉可见性（`doctor_check` 转正后仅剩手改 `features.json` 一条关闭途径），且量化指标等常规开关从来没有任何界面入口；同时 `datasource_adapter` 作为内部接缝占着一个默认关的用户开关。设计：单条开关声明（显示名/说明/分组/默认值/产物影响）+ 分组属性（`GROUP_EXPERIMENTAL` 实验性功能默认关 / `GROUP_STANDARD` 常规开关默认开），转正 = 改一个字段、可见性自动延续；三渠道入口由注册表派生（TUI 面板 / Web 面板 / CLI `--feature NAME=VALUE` 双向）。设计文档见 `docs-stm/archive/v0.10.x/feature-switch-registry/feature-switch-registry-unification-design.md`。 | P4 | 已完成（2026-09-11）：**批次① 转正 `datasource_adapter`**——内部接缝（开关两态下报告产物逐源等价，由 `test_quote_adapter_parity.py` 锁定），不该占一个默认关的用户开关；默认关的真实代价是生产路径从不执行适配器分支。**批次② 注册表统一 + 三渠道上屏**——`config/features.py` 以 `FeatureSwitchDef`（显示名/说明/分组/默认值/产物影响五字段）+ `feature_switch_registry`（20 项）为**唯一登记点**，`_FEATURE_FLAGS_DEFAULT` 降为**派生投影**，`EXPERIMENTAL_FEATURES` 容器退场（实验清单改由 `switches_in_group(GROUP_EXPERIMENTAL)` 表达）——**「面板可见性」与「是否实验项」由此解耦**，转正只剩「改分组 + 改默认值」两个字段，面板入口自动延续。三渠道一律派生：TUI 菜单 `[S]` 分三块（标准 LLM 模块 1-5 / ⚗ 实验块 6-14 / 常规块 15-25，常规块**追加**在实验块后故既有编号不位移，行首 ⚗ 仅标实验组）；Web 配置面板同构两块并下发 `features` 面（`experimental`/`standard` 取值 + `labels` + `report_affecting`，前端不写字典，常规组中改变产物的项标签带「（影响报告）」）；CLI 新增全局 `--feature NAME=VALUE`（**全域、双向、仅本次运行、不写盘**，取值经 argparse type 回调即时校验并列出可选值）。`--feature` 在 `--experiment` **之后**应用，故 `--experiment all --feature X=off` 表示「其余全开、只关 X」；早返回命令（`doctor`/`check-sources`/`view-logs`/`cassettes`）经 `_prepare_early_exit_switches` 同样生效。架构约束「功能开关注册表唯一事实来源」同步修订——适用范围由实验开关扩至**全部**开关、登记点改指 `feature_switch_registry`，渠道层不得另写清单的禁令不变而覆盖面扩大。实现设计见 `docs-stm/archive/v0.10.x/feature-switch-registry/feature-switch-registry-unification-design.md`；自审记录 rf-346 |

## 归档说明

- plan-17~24 三组设计/实施文档 2026-08-05 由 `docs-stm/plan/` 移入本目录：plan-17~24 设计层 + 实施层 → `investment-features/`（`plan-investment-features.md` 设计 + `plan-investment-iteration.md` 21 轮实施，同属「投资功能优化 + 章节归并」主题，目录语义与内容相关）；rf-208 门禁增强设计 → `task-code-traces-gate/`。
- **二次合并**：`docs-stm/managements/plan.md` 中 v0.10.x 已完成事项记录（P0 发布门禁两条、推荐实施顺序 ①~⑧ 表格、P1~P3 已完成项详细段落）整体迁入本文件「v0.10.x 已完成项」章节，原相对链接改指本目录内 `investment-features/` 兄弟路径。plan.md 仅保留未完成项与归档引用。
- `docs-stm/plan/` 原保留未完成项（plan-8 轻量 Web UI / plan-10 日志可视化，P4 实验功能）设计文档：`plan-web-ui.md` + `plan-web-ui-implementation.md`。**plan-8 已于 2026-08-06 三阶段全部实施完成**，两份设计文档归档至 `docs-stm/archive/v0.10.x/web-ui/`（见本文件「v0.10.x 设计文档」索引）；plan.md 引用同步改指归档路径，`docs-stm/plan/` 当前为空目录。
- **三次合并（2026-08-16）**：`docs-stm/managements/plan.md` 中 v0.10.x 已随发布版本实现的 **P4 实验功能项**（plan-8/25/26/27/28）详细段落整体迁入本文件「P4 — 实验功能（已随发布版本实现）」章节。plan.md 的 P4 区仅保留未实现项 plan-10（日志可视化，未完成）与归档引用。对应 rf-248~275 已解决项同步迁入 `archived_review-findings.0.10.x.md`、changelog [0.10.9]~[0.10.13] 同步迁入 `archived_changelog.0.10.x.md`。
- **五次归档（2026-09-11）**：`docs-stm/plan/` 中外部借鉴系列全部 14 份文档按**借鉴来源**分四目录迁入本目录——`tradingagents-borrowing/`（决策跨期反思闭环 + LLM 输入/输出质量治理三层 + 实验开关上屏）、`augur-borrowing/`（决策结算纪律 + 确定性信号账本 + 健壮性三件套）、`openbb-borrowing/`（数据源适配契约 + 记录-回放测试 + 凭据就绪指引）、`llm-fingerprint-prompt-coverage/`（自审发现的缓存指纹提示词覆盖缺口）。目录语义 = 借鉴来源，与各文档头部「来源」行一致；文档间交叉引用按新相对路径改写。各文档头部状态行同步由「未立项实施 / 设计定稿待实施 / 实现中」更新为已实现态。`plan.md` 的「实现设计见」引用同步改指归档路径，`docs-stm/plan/` 再次成为空目录（等待新立项的中间计划）。
- **六次合并（2026-09-12）**：`docs-stm/managements/plan.md` 中留存的 v0.10.x 完成项整体迁入本文件——P1 区 plan-29 归档引用行与 plan-40 / plan-41 完成态段落、P4 区「借用探索候选」引言与 plan-30~plan-41 实验功能表（新增 `### P1 — 已完成（plan-29 ~ plan-41 完成态）` 与 `### P4 — 实验功能（plan-30 ~ plan-41 全部完成）` 两节）。plan.md 的 P1 / P4 两区自此均为「无待办项」。同批：rf-322 ~ rf-353 已解决项迁入 `archived_review-findings.0.10.x.md`、changelog [0.10.14]~[0.10.18] 迁入 `archived_changelog.0.10.x.md`、`docs-stm/plan/` 两份已实现设计文档迁入 `feature-switch-registry/` 与 `feeder-fund-penetration/`。
- 版本号：本归档涵盖已发布版本 v0.10.0 ~ v0.10.4（当前开发版本 v0.10.5-dev，归档时点为 2026-08-05），归档目录按版本段命名 v0.10.x。三次合并后归档范围扩展为已发布 v0.10.0 ~ v0.10.13（2026-08-03 ~ 2026-08-14）；五次归档后扩展为已发布 v0.10.0 ~ v0.10.17（2026-08-03 ~ 2026-09-10）；六次合并后扩展为已发布 v0.10.0 ~ v0.10.18（2026-08-03 ~ 2026-09-12）。
