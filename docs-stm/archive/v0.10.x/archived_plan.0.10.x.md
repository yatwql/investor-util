# 实现计划归档 — v0.10.x

> 归档时间：2026-08-05（设计文档 + 完成项摘要）；2026-08-05 二次合并 plan.md 已完成事项记录；2026-08-07 追加 plan-25 Web 持仓输入模式 / plan-26 Web 配置编辑 / README SVG 架构图；2026-08-08 追加 env-benchmark-doc-update（--update-docs 环境耗时对照自动更新）；2026-08-16 三次合并 plan.md 已完成事项记录（plan-8/25/26/27/28 P4 实验功能项）
> 原始文件：`docs-stm/managements/plan.md`（当前迭代部分）
> 涵盖版本：v0.10.0 ~ v0.10.13（2026-08-03 ~ 2026-08-14）；plan-8 于 v0.10.10 实现、plan-25/26/27/28 于 v0.10.12 实现、README SVG 于 v0.10.13 实现（2026-08-06/07）
> 归档内容：本迭代已实现的计划项（plan-8 + plan-17~plan-28）设计文档 + 完成项摘要 + 推荐实施顺序 + 发布门禁记录（P0/P1/P2/P3 已完成事项记录 + P4 已随发布版本实现项自 plan.md 整体迁入）

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

## 归档说明

- plan-17~24 三组设计/实施文档 2026-08-05 由 `docs-stm/plan/` 移入本目录：plan-17~24 设计层 + 实施层 → `investment-features/`（`plan-investment-features.md` 设计 + `plan-investment-iteration.md` 21 轮实施，同属「投资功能优化 + 章节归并」主题，目录语义与内容相关）；rf-208 门禁增强设计 → `task-code-traces-gate/`。
- **二次合并**：`docs-stm/managements/plan.md` 中 v0.10.x 已完成事项记录（P0 发布门禁两条、推荐实施顺序 ①~⑧ 表格、P1~P3 已完成项详细段落）整体迁入本文件「v0.10.x 已完成项」章节，原相对链接改指本目录内 `investment-features/` 兄弟路径。plan.md 仅保留未完成项与归档引用。
- `docs-stm/plan/` 原保留未完成项（plan-8 轻量 Web UI / plan-10 日志可视化，P4 实验功能）设计文档：`plan-web-ui.md` + `plan-web-ui-implementation.md`。**plan-8 已于 2026-08-06 三阶段全部实施完成**，两份设计文档归档至 `docs-stm/archive/v0.10.x/web-ui/`（见本文件「v0.10.x 设计文档」索引）；plan.md 引用同步改指归档路径，`docs-stm/plan/` 当前为空目录。
- **三次合并（2026-08-16）**：`docs-stm/managements/plan.md` 中 v0.10.x 已随发布版本实现的 **P4 实验功能项**（plan-8/25/26/27/28）详细段落整体迁入本文件「P4 — 实验功能（已随发布版本实现）」章节。plan.md 的 P4 区仅保留未实现项 plan-10（日志可视化，未完成）与归档引用。对应 rf-248~275 已解决项同步迁入 `archived_review-findings.0.10.x.md`、changelog [0.10.9]~[0.10.13] 同步迁入 `archived_changelog.0.10.x.md`。
- 版本号：本归档涵盖已发布版本 v0.10.0 ~ v0.10.4（当前开发版本 v0.10.5-dev，归档时点为 2026-08-05），归档目录按版本段命名 v0.10.x。三次合并后归档范围扩展为已发布 v0.10.0 ~ v0.10.13（2026-08-03 ~ 2026-08-14）。
