# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.1-dev] - 开发中（未发布）

### 景气度框架诊断：口径修订（并集归一 + 互斥归类 + 关键词补词）与配置同步（2026-09-16）

按用户真实持仓复核，修订第①②③维的统计口径与默认词表（原口径只覆盖 34.6% 市值、且同一标的可被景气/防御重复计数）：

- **并集覆盖 + 归一**（`_sector_weight_items`）：穿透重仓各底层标的（含基金拆解，按 `codes` 与 `sources` 里的基金代码标记已覆盖）+ **未被穿透覆盖的其余直接持仓**（QDII/联接/债基等，按 `classify_sector` 板块）合并后按已覆盖市值归一；证据披露覆盖率（如「覆盖 48.47% 市值…按已覆盖部分归一」），读者可见评分分母
- **互斥归类（防御优先）**：同一标的命中多类词时只计防御类，避免景气+防御之和 >100%
- **关键词补词（配置层单一事实来源）**：景气词加「电池/光伏/高端装备/制造/能源资源/电力/石油/煤炭」，全球优势词加「电池/高端装备/制造/电力」，防御词加「债/货币/现金」；模块默认值改为**从 `config/_config_defaults` 派生**（避免两处词表漂移），`config.json` 同步重生成（校验 0 问题）
- **回归测试**：并集覆盖计入未穿透持仓、已覆盖基金不重复计入、互斥归类（重叠词只计防御）、无重叠时正常计分；`tests` 全绿

**真实持仓复核对比**（同一份报告，改前 → 改后）

| 维度 | 改前 | 改后 |
|:--|:--|:--|
| ① 景气方向/通胀属性 | 0/25（口径仅覆盖 34.6% 市值） | 0/25（并集覆盖 48.47%；景气 14.71%、防御 77.10%） |
| ③ 全球视野/比较优势 | 5/15 | **15/15**（全球优势环节 25.64% + 境外占比 78.10%） |
| ⑥ 业绩与回撤印证 | 缺失（基准结构假设错误） | 4/15（组合 -18.11% / 沪深300 -10.36% / 回撤 22.42%） |
| **总分** | 32/100（不契合） | **42/100（部分契合）** |

门禁：四个 `--ci` + `--mode verify,regression` 5001 passed / 0 failed + ruff 全绿。

### 修复：维度⑥「业绩与回撤印证」误报缺失（基准结构假设错误）（2026-09-16）

用户复核报障「业绩与回撤印证说缺失，但组合历史走势与回撤章节明明有数据」→ 定位为**结构假设错误**：`PortfolioHistoryCalculator.get_combined_timeseries()` 的 `benchmarks` 契约是 **`list[dict]`**（`[{code, name, bars, total_return_pct, max_drawdown_pct, …}]`），而实现按 `dict[str, dict]` 调 `.values()` → `AttributeError` 被维度守卫吞成「需核实」。真实数据（用户持仓）：组合区间收益 **-18.11%**、最大回撤 **-22.42%**、沪深300 **-10.36%**，数据齐全却未计分。

- **修正确性**：新增 `_benchmark_returns()` 同时兼容 `list[dict]`（生产形态）与 `dict[str, dict]`（注入形态）；非 dict 元素/缺字段/`bool`/非数值一律跳过且**不抛异常**（注意 `finite_or(None)` 内部 `float(None)` 会抛 TypeError，故先做类型判定）；证据文案带基准名（如「未跑赢最强对比基准（沪深300 -10.36%）」）
- **修降级语义**：`drawdown_available=False`（历史样本 <60 交易日）时**只降级回撤子项**（收益仍计分，标 `partial` 并列入未验证），不再整维判为缺失；`status=degraded` 也计分但标注口径可能不完整；仅 `status=unavailable`/无收益字段才 `unverified`
- **回归测试**：`TestPerformanceDimensionBenchmarkShapes` 8 例（list 形态计分且证据含基准名、未跑赢场景 4 分档、dict 形态兼容、畸形基准 5 种输入不抛异常、degraded 计分带注记、unavailable 未验证、回撤样本不足 partial、真实形态经契约端到端 scored）
- **真实管线复核**：both 路径实际块输出「总分 32/100（32%）」，六维全部可计分——景气 0/25、ROE 9/20、全球 5/15、流动性 10/10、集中度与周期拼接 4/15、业绩与回撤印证 **4/15**（组合 -18.11% / 沪深300 -10.36% / 回撤 22.42%）

门禁：四个 `--ci` + `--mode verify,regression` 4997 passed / 0 failed + ruff 全绿。

### 修复：full 路径（菜单 L）HTML 未转发景气度框架契约（2026-09-16）

用户复核报障「开关已开、运行后行动建议章后没有新增内容」→ 定位为**接缝缺口**：`_generate_full_html_report`（full 路径 HTML 包装函数）既未声明也未转发 `prosperity_framework_data`，而 both 路径已转发——`count=1` 的批量替换只覆盖了其中一条调用链。**Excel 侧不受影响**（`generate_excel_report` 自行就地构建契约），故 both/full 的 Excel 一直有块，HTML 仅在 both 路径有块。

- 修复：`_generate_full_html_report` 补参数声明与转发（→ `write_html_report`），full 路径调用点补传 `pipeline_data` 中的契约
- 守卫（防再漏）：`test_prosperity_framework_wiring.py::TestHtmlCallSiteSeam` 3 例——① 源码级断言 `_report_generation.py` 中**每处** `write_html_report(...)` 调用都带该参数（新增其它 HTML 调用链忘记转发即失败）；② 包装函数签名含该参数且函数体内转发；③ full 路径调用点从 `pipeline_data` 取契约传入
- 真实数据复核（用户真实持仓 + 真实配置，输出到 `docs-stm/tmp/` 并清理）：both 与 full 两路径的 HTML 均含「⑥ 景气度框架诊断（实验性）」块与免责句；Excel「7.行动建议」页签含块（本次实测「总分 28/85（33%）—— 评级：不契合」）

门禁：四个 `--ci` + `--mode verify,regression` 4989 passed / 0 failed + ruff 全绿。

### 修复：景气度框架诊断拖垮整份报告 + 行情全零 Excel 崩溃（2026-09-16）

**缺陷①（P0，用户报障「运行后有数据处理异常」）**：`logs/app.log` 显示 `AttributeError: 'SnapshotData' object has no attribute 'get'` → **整份 full 报告生成失败**。根因：`analysis/prosperity_framework.py::_turnover_proxy_pct` 按 dict 取快照字段，而 `report/history_snapshot.load_all()` 返回的是 **`SnapshotData` 冻结 dataclass**（`.accounts[*].holdings[*].code`）；异常自实验功能冒泡，违反「实验功能不得影响主报告」与数据降级治理纪律。

- **修正确性**：新增 `_snapshot_holding_codes()` 同时兼容 `SnapshotData` 对象（生产形态）与 dict 形态（`accounts`/`holdings`/`details` 键），缺失字段按空集处理且**不抛异常**
- **修韧性**（三道防线）：① 单维计算经 `_guard_dimension()` 包裹 → 单维异常降级为「未验证」，不影响其余维度与契约；② 组装辅助 `compute_prosperity_framework_data` 整体 try/except → 警告 + 返回 None（等价开关关闭，块不渲染）；③ 三个调用点（`_report_generation` 的 both/full、`excel_generator` basic 兜底）各自再加一层兜底
- **回归测试**：`test_prosperity_framework_edge.py` 新增快照形态回归 5 例（dataclass 可算换手代理 66.67%、端到端契约 scored、dict 形态兼容、畸形对象降级、缺 holdings 属性）；`test_prosperity_framework_wiring.py` 新增韧性隔离 4 例（build 抛异常 → 返回 None、坏快照不崩、单维异常隔离、真实 `SnapshotData` 全链路）；新增场景测试 `test_scenario_prosperity_framework.py` 4 例（真实 dataclass 快照 + 隔离输出目录驱动 `generate_excel_report`：功能开/关、坏快照、构建抛异常四种情形**报告均须生成成功**）

**缺陷②（既有缺陷，被本轮场景测试暴露）**：行情全零（非交易时段/网络异常）时，「持仓明细与分类」页签先写**整行合并**的提示行，随后仍以该行为数据起点写入明细 → `AttributeError: 'MergedCell' object attribute 'value' is read-only`，Excel 报告生成失败。该缺陷源自合并前的 `market_value_sheet.py`（批次② 原样带入），既有单测因用 MagicMock 工作表而漏检。

- **修复**：`holdings_detail_sheet._write_market_value_block` 中提示行之后显式重置 `data_start = row`（分类区块同样显式化数据起点语义）
- **回归测试**：`test_holdings_detail_sheet.py::TestAllZeroPriceRegression` 2 例（真实 openpyxl：全零场景不崩溃 + 提示行在数据行之前）

**验证**：用户真实快照（73 期 `SnapshotData`）只读复算 → 换手代理与契约均正常；四个 `--ci` + `--mode verify,regression` 4989 passed / 0 failed + `dev-verify` 2779 passed + ruff check/format 全绿。

### plan-46 景气度框架诊断（实验性功能）实施（2026-09-16）

借鉴开源项目 **zhengxi-views**（郑希观点库，MIT；<https://github.com/lyra81604/zhengxi-views>）从公开采访蒸馏的景气度投资方法骨架，落地为本仓的**实验性功能 `prosperity_framework`**（默认关）：把「全球视野找变化 → 顺产业链找通胀环节 → 落到中国比较优势环节 → 选流动性够 + ROE 低位有弹性的标的 → 多维跟踪与周期拼接 → 组合分散 + 行业比例 + 退出纪律」转成对**本仓持仓组合**的可计算诊断。**只借鉴可计算骨架与评分口径**（不引入其语料库、基金快照、全市场检索）。

**六维评分卡（满分 100）**：景气方向/通胀属性 25 + ROE 低位弹性 20 + 全球视野/中国比较优势 15 + 流动性 10 + 集中度与周期拼接 15 + 业绩与回撤印证 15；输入全部取自既有能力（穿透重仓板块/概念、`financial_indicator_data` 的 ROE、`check_liquidity` 变现天数、历史快照换手代理、`history_data` 收益与回撤），**不新增外部数据源与 LLM 调用**。

**实现**
- 新增 `analysis/prosperity_framework.py`（纯计算；市价读取经 `finite_or` 归一）；配置新增顶层键 `prosperity_framework`（景气/全球比较优势/防御关键词 + 集中度目标，手动编辑）并重生成 `config.json`
- 实验开关 `prosperity_framework`（实验组、默认关、`affects_report=True`）；实验块由 4 项增至 5 项（追加在组末，既有编号不变）
- 契约 `prosperity_framework_data` 进数据契约台账（pipeline_data 键 + 类型映射）与附录 H（键表 + 逐键契约说明）
- 组装辅助 `report/_report_aux_metrics.py::compute_prosperity_framework_data`：开关关闭返回 None；穿透优先取 `prep.penetrated_assets`（缺失按需计算）；流动性/快照取数失败降级为该维未验证
- 接线：`_report_generation` 的 both 与 full 两路径注入契约；`excel_generator` 在 basic 路径就绪后就地兜底
- 渲染：行动建议章内嵌块——HTML `partials/action_section.html` ⑥ 块（总分/评级 + 六维明细 + 持仓视角 + 需核实清单 + 免责句）、Excel `report/action_sheet.py::_write_prosperity_block`

**降级与诚信口径（红线）**：数据缺失维度一律 `unverified`（**不计分、不臆造**）并给出可读原因；总分只按已计分维度折算（`scored_weight` / `total_score_pct`），界面同时显示未验证清单；渲染固定带免责句（衡量「组合与框架的契合度」，非组合优劣、非投资建议）；每条得分在 `evidence` 中给出可追溯口径。

**测试**：`unit/analysis/test_prosperity_framework.py`（27 例：六维计分/缺数据降级/总分口径/持仓视角/评级边界/配置覆盖）+ `test_prosperity_framework_edge.py`（13 例：空/None/零/异常类型/全防御/未知板块/极端集中度/快照缺失/负收益深回撤）+ `unit/report/test_prosperity_framework_wiring.py`（7 例：开关门控、prep 穿透口径、Excel/HTML 双端块显隐）；TUI 面板编号断言与文档串同步。

**文档同步**：设计文档 `docs-stm/plan/prosperity-framework-design.md`（含上游归属与许可、数据映射、六维口径、契约结构、约束对照、验收标准）；`technical.md`（§4.20 叙述 + 语义表 3 行 + 附录 H + 附录 I 段号）；`requirements.md`（§5.11 R-PF-01~08 + 配置键）；`how-to-config.md`（开关表 + 配置键 + 实验组计数 4→5）；`reports-instruction.md`（行动建议章块）；`README.md`；`testplan.md`（§4 回归行）；`folders.md`（树 + 统计）；`plan.md`（plan-46 已实施）。

**实施期自查**：`rf-372` —— 新增实验开关触发三处跨接缝漂移（TUI 面板编号断言、附录 H 台账一致性用例、both 路径无 `prep` 变量），均已修正并同步测试与文档。

门禁：四个 `--ci` + `--mode verify,regression` 4980 passed / 0 failed + `dev-verify` + ruff + 版本一致性全绿。

### 管理/用户文档二次核对与整改（rf-371）（2026-09-16）

技术债整改（rf-370）后逐份复核 10 份管理文档 + 11 份用户文档的「顺序/编号、清单完整性、示例与计数、章归属表述」，整改 6 类：

- **`technical.md`**：Web 配置编辑接口表的可编辑面分组名改用 surface 实际键（`report_switches`）；白名单段落去掉已不存在的 `submodule` writer、「增强子模块开关 6」「功能开关 20」改为「报告章节与增强 8（`report_switches` 独立视图）+ 功能开关 28（实验 4 + 常规 16 + 报告 8）」并补记 43 条白名单；契约注记序号随章节合并更新（`portfolio_evolution` number=14、`action` number=7、「报告顺序完整 16 项」）；`features.json` 行改「28 项声明 / 三组（实验 4 + 常规 16 + 报告 8）」
- **`requirements.md`**：P 菜单条目删除已随 plan-44 移除的「报告增强子模块配置（8 项）」入口（改指菜单 `[S]`「报告章节与增强」块）；R-WEB-08 可编辑面清单改用 `report_switches`；features.json 章节改「28 项 / 三块（实验 4 + 常规 16 + 报告 8）」
- **`how-to-config.md`**：配置样例中「报告子模块开关」注释改为指向 `features.json`（功能开关注册表，菜单 `[S]`）；`report_section_order` 行的「默认顺序（20 项）」改 17 项
- **统计快照刷新**：`test-coverage.md` 按 `collect-test-coverage.py` 实测更新模式计数（unit 6900→6905、standard 5903→5908、report 1902→1907、all 7213→7218）、`unit_report` 与「报告生成」功能域计数；`folders.md` 更新测试代码（372 文件 / 109,295 行）、测试用例（7,218 个）、管理文档（10 / 10,085 行）与项目文档合计（52,549 行）

校验：章节表编号与注册表逐一比对（requirements §6.3 / how-to-config / reports-instruction 全 OK）、§6.4 编号 1..18 连续、README 分组合计 17、语义表 97 slug 覆盖全部 28 个开关、目录树全量比对无遗漏、陈旧表述扫描零命中。

门禁：四个 `--ci` + `--mode verify,regression` + `dev-verify` + ruff + 版本一致性全绿。

### 过去 96 小时实现技术债整改（plan-42~45，rf-370）（2026-09-16）

审计窗口内 67 次提交（plan-42~45 及发布/文档收尾）的代码、配置与测试，整改 7 类技术债：

**① 语义索引正向校验失效（最重要）**：`scripts/check-semantic-index.py` 的正向项仍在解析 `_config_defaults.py` 的 `report_submodules` 字典——该机制已随「报告增强子模块并入功能开关注册表」移除，校验恒为空集，**新增开关可绕过「功能语义命名表」登记**。
- 改为 AST 解析 `src/python/config/features.py::feature_switch_registry`，校验「每个功能开关都已在语义表登记」（表外键报错）；脚本 docstring、`-v` 输出、`--ci` 摘要与单测（`TestReportSubmodulesKeys` → `TestFeatureSwitchKeys`、run_checks 夹具改 features.py 形态）同步
- 新校验立刻暴露 **12 个开关未登记** → `technical.md` 功能语义命名表补 12 行：`llm_debate_procon`/`llm_debate_conditional`/`llm_debate_qa_concentration`、7 个 `metrics_*`（夏普/卡玛/HHI/胜率/换手率/风险贡献/Beta）、`enable_interactive_charts`、`datasource_adapter`

**② data 层可用性字典双份实现**：`excel_generator` 内联构造 + integration 一致性测试手写镜像，章节合并每批需改两处（rf-367 即此类漂移）。
- 下沉为 `report/excel_sheet_factory.build_data_availability()`（合并章契约 OR、契约 None、news/llm 口径集中一处），生成器与集成测试镜像改用同一函数；新增 5 例口径守卫（fund_deep 开/关、单契约注入、两财报契约随开关、news/llm 随 include）

**③ 死代码 / 死认知**：删除 `html_writer_nav` 的 `manager_data` data_flag（章节移除后无消费方；集成测试镜像同步删）；`registry.py` docstring 示例键 `fund_manager` → `position_structure`。

**④ Web 面旧机制命名**：surface 键 `submodules` → `report_switches`（`web/config_edit.py` + `static/web/main.js` 渲染调用同步）；删除前端 `CONFIG_LABELS.submodules` 陈旧字典（漏列两个开关且与服务端 `features.labels` 同源下发设计矛盾）。

**⑤ 测试用例陈旧 / 失效断言**：`test_excel_report_structure` 夹具改用当前注册表切片（删 `fund_manager`/`position_relationship`/`fund_concentration`，序号与页签计数同步 16/9 → 14/7）；`test_config` 的「重复序号」「多问题累加」用例改用现存键（此前误走「未知键」分支，断言通过但未测目标行为）；`test_orchestrator`/`test_excel_market_data`/`test_holdings_detail_sheet` 注释去掉 `report_submodules.*` 旧表述；`test_financial_indicator` 的「旧配置不再生效」守护样本改为中性旧键名；plan-45 新增用例的**恒真断言**（先按值过滤再断言不存在）改为「占位文案存在 + 无集中度数据行」正向断言。

**⑥ 配置与模板漂移**：`data/config/config.json` 按当前模板重生成（补 plan-43 引入的 `holdings_start_date`，其余键值保持仓库现值：相对路径、显式 `cache_ttl`、显式 `report_section_order` 16 项），`validate_config()` 0 问题。

门禁：四个 `--ci`（含改造后的语义索引）+ `--mode verify,regression` + ruff check/format + 版本一致性全绿。

### plan-45 设计与实施层文档归档（docs-stm/plan → archive/v0.11.x）（2026-09-16）

plan-45（报告章节整合，注册表 21 → 17）四批全部实施完成，按「中间设计文件随完成态归档」惯例把两份文档从 `docs-stm/plan/` 归档到 `docs-stm/archive/v0.11.x/section-consolidation/`：

- `section-consolidation-design.md` — 设计层（四项合并方案 / 可见性模型扩展 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）；头部状态改为「**已实现**（2026-09-16 归档）」并补归档位置与实施记录指引
- `section-consolidation-iteration.md` — 实施层施工单（命名统一总表 / 接缝地图 / 逐批施工步骤与量化验收 / 十轮复盘记录 / 守卫清单与基线方法 / 领域层与章节层边界 / 文档同步清单）；头部状态改为「**✅ 四批全部实施完成**」并列出四批提交号，批次②③④ 小节标题标注「✅ 已实施」
- `docs-stm/archive/v0.11.x/archived_plan.0.11.x.md`：新增「P1 — 已完成（plan-45 完成态，2026-09-16 归档）」条目（动机/决定/方案/四批实施记录与提交号/十轮复盘/验收达成/实施记录指引 + 设计文档索引），头部涵盖版本与归档内容同步更新
- `plan.md`：P1 待办区移除 plan-45 条目（恢复「无待办项」），待办说明与归档清单改为 plan-44 / plan-45 并指向新设计文档目录；`plan-next` 保持 46
- `folders.md`：`plan/` 目录树改为空目录说明、统计行 2 文件/373 行 → 0；`archive/v0.11.x/` 树新增 `section-consolidation/`（含两份文档）；archive 统计 129/42,429 → 131/42,802（md 125→127），项目文档合计行同步

门禁：四个 `--ci` + `dev-verify` 全绿。

### plan-45 四批后管理/用户文档一致性与顺序整改（rf-369）（2026-09-16）

对 10 份管理文档 + 11 份用户文档逐份核对「章节表顺序/编号、清单完整性、示例与计数、章归属表述」，按注册表现状（17 条）整改：

- **requirements.md**：§6.3 补 `fundamental_snapshot` 行（16）并把 `llm_usage` 归位 17；§6.4 小节编号重排为连续 1..18（17 个报告章节 + 成本流水子模块），补 6.4.16 持仓基本面（两条区块字段表，指向 §5.9/§6.12），经理变更块降为「基金业绩分析」章内 h5 子标题
- **how-to-config.md**：表头 15→17、补 `fundamental_snapshot` 行与 `llm_usage`=17；示例 JSON 的已删键（`fund_manager`/`position_relationship`/`fund_concentration`）→ `position_structure`/`fundamental_snapshot`；「19 项默认顺序」「完整 18 项」及示例序号全部按现状改写
- **reports-instruction.md**：类型分组表编号错位（基金业绩 3→4、数据源 14→15、LLM 用量 16→17）、基金深度分析「共 4 个」→2、删除基金评价表重复的「持仓集中度」行、菜单快速索引与「19 个页签/7 组」→「17 个页签/8 组」
- **folders.md**：HTML 模板行 partial 清单换为 `fundamental_snapshot_section.html`（并修正文件数/行数）、目录树删三个已删模块行并补 `test_section_visibility.py` 与新 partial、把 `fundamental_snapshot_sheet.py` 归入财报装配组、统计快照按实测刷新（主程序 280/70,669、测试 372/109,257、用例 7,213、源代码合计 310/82,270、项目文档 138/52,459、用户文档 11/5,159、managements 10/10,040）
- **technical.md**：三处「19 个模块」→17（含注册表约束条目与模块分布行：always×5 / fund_deep×2 / fundamental_snapshot×1 等）、注册表结构示例改用 `position_structure`（含 `data_flag_any`）、基金深度块图与「基金经理变更监控」小节标题改为章内区块、TOC 条目随 §4.19 改题同步
- **test-coverage.md**：按 `scripts/collect-test-coverage.py` 实测刷新模式计数（unit 6900 / standard 5903 / verify 4696 / report 1902 / data 68 / all 7213）、unit 子标记（unit_report 1902 / unit_config 359 / unit_core 1213 / unit_analysis 811 / unit_web 212）与跨类标记（edge 931 / data 68）；报告域测试清单补三个合并章测试文件
- **testplan.md**：§4 新增 P1「报告章节合并」回归行（三个合并章的逐格等价 + OR 可见性 + type/board_flags/装配键守卫 + 两侧一致性 + 经理块门控）
- **用户文档**：README（页签 21→17、分组七→八、「全部 20 项开关」→28）、how-to-use-tui-menu（基金深度分析 3→2 章 + 经理块说明、features.json 开关计数表述）、how-to-use-web-mode（报告增强子模块清单补财务指标、菜单归属 `[S]`）、faq（示例 JSON 与 19→17 项）、datasource / datasource-reliability（数据源用途归属改「持仓基本面章·区块①/②」）、developer-guide（示例键与 17 个模块键）

门禁：四个 `--ci` + `dev-verify`（2748 passed）全绿。

### plan-45 章节整合·批次④ `fundamental_snapshot` + 经理变更并入（plan-45 完成）（2026-09-16）

**目标**：把「财务指标」与「持仓个股财报摘要」两章合并为同页签两区块的新章 `fundamental_snapshot`「持仓基本面」，并把「基金经理变更监控」章并入「基金业绩分析」章末尾区块（注册表条目 19 → 17，零 alias）。**四批全部完成：21 → 17 条**。

**注册表与可见性**
- 删除 `fund_manager` 条目（其内容成为基金业绩章的块）；`financial_report_digest` + `financial_indicator` 两条 → 一条 `fundamental_snapshot`（`type=fundamental_snapshot`、`data_flag=None`、`data_flag_any=("financial_indicator_data","financial_report_digest_data")`、序号 16）；条目总数 17（序号连续 1..17）；`_REPORT_SHEET_NAMES` 同步（新增 `fundamental_snapshot: 持仓基本面`，删除 `fund_manager`/两条旧财报页签名）
- board 层参数合并：两侧 `board_flags` 删除 `"financial_report"`、`"financial_indicator"` → `"fundamental_snapshot"`（`enable_fundamental_snapshot` = 两功能开关任一开启）；`enable_financial_report_digest` 形参链全量删除（`html_writer` / `excel_generator` / `_report_generation` 包装函数与两处调用点）；`html_writer_nav._SECTION_NAV_GROUP_MAP` 同步（删 `fund_manager`，两条旧财报章键 → `fundamental_snapshot: basic`）
- `excel_generator` 的 `data_availability` 保持登记两契约 flag（`data_flag_any` 乐观/悲观口径与 HTML 侧一致）

**Excel / HTML 渲染**
- 新增 `report/fundamental_snapshot_sheet.py::write_fundamental_snapshot_sheet`（区块① 财务指标 19 列 + 区块② 财报摘要 9 列；契约 None = 该功能开关关闭 → 该块整体不写，含小节标题）；删除 `financial_indicator_sheet.py` / `financial_report_sheet.py`（`financial_indicator.py` 装配层与 `financial_report_digest.py` 保持不动）
- `report/fund_performance.py` 吸收经理变更块：`write_fund_performance_sheet(..., manager_data=None)` + `_write_manager_block`（8 列 + 预警着色 + 占位）；删除 `fund_manager_sheet.py`
- 经理数据改在内容阶段组装（`write_content_sheets` 新增 `enable_fund_deep_analysis` 参数，开启时 `detect_manager_changes` 注入），`excel_fund_deep_analysis` 不再单独写经理页签；`excel_module_loader` 装配键改 `write_fundamental_snapshot_sheet`（删除三个旧键）
- HTML：新增 `partials/fundamental_snapshot_section.html`（一章两区块，块级开关 `financial_indicator_data` / `financial_report_digest_data` 非空才渲染该块），删除两个旧 partial；`report_template.html` 删除独立经理章节、内容并入 `sec-fund_performance` 末尾（块门禁 `manager_analysis` 非空 = 基金深度分析开启）
- `data/config/config.json` 的 `report_section_order` 重生成（删除 `fund_manager`，新增 `fundamental_snapshot`=16）

**测试（新增/同步）**
- `test_financial_indicator_sheet.py` + `test_financial_report_sheet.py` → `test_fundamental_snapshot_sheet.py`（区块写入器用例 + 新增合并写入器：两区块小节标题同页签、契约 None 的块级门控两侧、两契约皆 None 仅剩章标题、**内容等价**）
- `test_fund_manager_sheet.py` → `test_fund_performance_manager_block.py`（改调 `_write_manager_block`）；`test_fund_performance.py` 新增经理块门控两例（`manager_data=None` 不渲染经理块且主表照常 / 传入时渲染）
- 章节键断言同步：条目数 19→17、HTML 容器 19→17、导航/目录 14→13、Excel 页签数 15→14（全开）；type 集合 `financial_report`/`financial_indicator` → `fundamental_snapshot`；`fund_deep_analysis` 计数 3→2；配置模板与注册表同序新增一致性用例

**文档同步**：`technical.md`（模块数 20→17、可见性旗标表、`data_flag` 表、§4.19 改为「持仓基本面」、契约叙述的注册表注册点与消费方、功能语义命名表（僵尸条目 `financial_indicator_sheet` → `fundamental_snapshot_sheet` + 新增合并章行）、合并章注）、`requirements.md`（§6.3 表与 §6.4 小节合并重排、§5.9/§6.12 章节合并说明）、`testplan.md`、用户文档 5 份、`folders.md` 目录树、`plan.md`（批次④ 已实施，plan-45 完成）

**实施期自查**：`rf-368` —— board 层参数链比施工单预估更长（实际 5 处调用点），首改即由 `--mode verify` 的 `unexpected keyword argument` 捕获并改净；`technical.md` 语义命名表僵尸条目由 `check-semantic-index` 捕获。

**门禁**：`--mode verify,regression` 4939 passed / 0 failed；`dev-verify` 2748 passed；四个 `--ci` + 版本一致性 + ruff check/format 全绿。

### plan-45 章节整合·批次③ `position_structure` 实施（2026-09-16）

**目标**：把「持仓关系矩阵」与「持仓集中度监控」两章合并为同页签三区块的新章 `position_structure`「持仓结构与集中度」（注册表条目 20 → 19，零 alias）。

**注册表与可见性（多契约 OR）**
- 删除 `position_relationship`/`fund_concentration` 两条，新增 `position_structure`（`type=fund_deep_analysis`、`data_flag=None`、`data_flag_any=("position_relationship_data","concentration_data")`、序号 6），其后序号整体 −1（19 条连续 1..19）；`_REPORT_SHEET_NAMES` 同步；docstring 计数 20 → 19
- `html_writer_nav._SECTION_NAV_GROUP_MAP` → `position_structure: fund_deep`（可见性 OR 复用批次①的 `data_flag_any` 模型）
- **Excel 侧契约 flag 同步登记**（rf-367）：`excel_generator` 按与 HTML 同口径写入 `position_relationship_data`/`concentration_data`——否则 `data_flag_any` 的悲观口径会使页签恒不创建

**Excel / HTML 渲染**
- 新增 `report/position_structure_sheet.py::write_position_structure_sheet`（区块① 持仓重合度矩阵 + 配对明细；区块② 持仓相关性矩阵（下三角 + 配对 + 说明）；区块③ 持仓集中度监控（11 列 + 预警着色）），供数入参 `concentration_data` 新增；删除 `report/position_relationship_sheet.py` 与 `report/fund_concentration_sheet.py`（领域计算 `position_overlap.py`/`fund_concentration.py` 保持不动）
- `excel_fund_deep_analysis` 两处分派合并为 `sheets.get("position_structure")` 一次调用（两契约数据独立组装、各自异常隔离、区块级降级），`excel_module_loader` 装配键改 `write_position_structure_sheet`
- `report_template.html`：两个 `div.section` 合并为 `sec-position_structure`，区块小节标题改 `.block-title`（一、持仓重合度矩阵 / 二、持仓相关性矩阵 / 三、持仓集中度监控）；进入章节先归一 `overlap_matrix`（`or {}`），集中度数据在缺失时按空列表降级
- `data/config/config.json` 的 `report_section_order` 重生成（`position_structure`=6，其余 −1，共 16 项显式列出 + llm_usage 末位）

**测试（新增/同步）**
- `test_correlation_sheet.py` → `test_position_structure_sheet.py`（区块二用例改调 orchestrator；集中度区块用例自 `test_fund_concentration_sheet.py` 迁入并改调 `_write_concentration_block`）；新增 `TestWritePositionStructureSheet`：首行章名 + 三区块小节标题同页签、**内容等价**（各区块行值与独立写入逐一相等）、仅有关系数据/仅有集中度数据两侧的 OR 降级
- `test_section_visibility.py` 增合并章 OR 三例（仅 `position_relationship_data` 就绪可见 / 仅 `concentration_data` 就绪可见 / 两者皆无隐藏）；`test_registry` 放宽「非 always 类型须有 data_flag」为「data_flag 或 data_flag_any」（多契约模型）
- 章节键断言同步：条目数 20→19、HTML 容器/导航/目录 15→14、Excel 页签数 16→15；集成一致性测试镜像补两契约 flag

**文档同步**：`technical.md`（可见性旗标表改三区块 + `data_flag_any` 行、§4.x 章节叙述、缓存表注、合并章注同步为四个合并章、功能语义命名表新增 2 行、基金深度块图）、`requirements.md`（§6.3 表与 §6.4 章节定义合并 + 小节序号 −1）、`testplan.md`、用户文档 5 份（章节表与计数）、`folders.md`（目录树）、`plan.md`（批次③ 已实施）

**实施期自查**：`rf-367` —— 合并章 `data_flag_any` 与 Excel 侧 `data_availability` 未登记的组合会使页签被悲观判定隐藏（integration 两侧一致性测试捕获），已修并补守卫。

**门禁**：`--mode verify,regression` 全绿；四个 `--ci` + 版本一致性 + ruff check/format 全绿。

### plan-45 章节整合·批次② `holdings_detail` 实施（2026-09-16）

**目标**：把「市值核算明细表」与「持仓分类表」两章合并为同页签两区块的新章 `holdings_detail`「持仓明细与分类」（注册表条目 21 → 20，零 alias）。

**注册表与可见性**
- `_REPORT_SECTION_DEFAULT`：删除 `market_value`/`category` 两条，新增 `holdings_detail`（`type=always`、`data_flag=None`、序号 2），其后条目序号整体 −1（20 条连续 1..20）；`_REPORT_SHEET_NAMES` 同步；docstring 计数 21 → 20
- 两侧导航/分组映射同步（`html_writer_nav._SECTION_NAV_GROUP_MAP` → `holdings_detail: basic`）；无需改前端标签字典与 TUI 面板（均按注册表派生）

**Excel / HTML 渲染**
- 新增 `report/holdings_detail_sheet.py::write_holdings_detail_sheet`（区块① 市值明细 15/16 列 + 账户小计 + 总计；区块② 分类汇总 10/12 列 + 分类小计 + 总计），`_weighted_avg_cost` 随之迁移；删除纯章节写入器 `report/market_value_sheet.py`，`report/category.py` 仅保留分类领域函数（`_categorize_holding`/`_tier_label`/`build_category_data_status`/`calc_yield_text`/`_load_dividend_data`）——**领域层不改名不删除**
- `resolve_market_data` 退化为纯数据解析（不再写页签），页签由 `write_content_sheets` 一次调用写入；`excel_module_loader` 装配键 `write_holdings_detail_sheet`（删除 `write_market_value_sheet`/`write_category_sheet`）；`html_writer_display` 反向依赖改指新模块
- `report_template.html`：两个 `div.section` 合并为 `sec-holdings_detail`（含「一、市值核算明细」「二、持仓分类汇总」两个 `.block-title` 区块小节标题，分类区块的资产构成环形图与数据状态脚随区块保留）
- `data/config/config.json` 的 `report_section_order` 重生成（`holdings_detail`=2，其余 −1，共 17 项显式列出 + llm_usage 末位）

**测试（新增/同步）**
- `test_market_value_sheet.py` → `test_holdings_detail_sheet.py`（区块①用例改调 `_write_market_value_block`，分类写入器用例自 `test_category.py` 迁入并改调 `_write_category_block`）；新增 `TestWriteHoldingsDetailSheet`：首行章名/两区块小节标题同页签/**内容等价**（两区块行值与独立写入逐一相等）/返回值契约/流水子列两区块各生效
- 新增正面守卫 `unit/report/test_section_type_flag_consistency.py`：注册表 `type` ↔ 两侧 `board_flags` 键一致、两侧键集合一致、无残留废弃 type、分派层写入器模块键均已装配
- 章节键断言同步：条目数 21→20、HTML 容器/导航/目录 16→15、Excel 页签数 8→7，配置样本与自定义顺序夹具改 `holdings_detail`；`total_value` 等领域字段（100+ 处）**不批量替换**

**文档同步**：`technical.md`（模块数 19→20 两处、架构图与 always 类型清单、成本流水消费方章名、`holdings_detail_sheet` 契约路径、功能语义命名表新增 2 行）、`requirements.md`（§6.3 表与 §6.4 章节定义合并 + 后续小节序号 −1）、`testplan.md`（测试文件名）、`reports-instruction.md`/`how-to-config.md`/`how-to-use-tui-menu.md`/`faq.md`/`README.md`（章节表与计数）、`folders.md`（目录树 + 统计）、`plan.md`（批次② 已实施）

**实施期自查**：`rf-366` —— 施工单 §3.2 把 `config/_validation.py::_KNOWN_PROVIDER_TYPES`（数据源类别 id）误判为注册表章节 `type` 的允许集合，已更正该行并补正面守卫（注册表 type ↔ 两侧 board_flags 一致）。

**门禁**：`--mode dev-verify` 2748 passed / 0 failed；四个 `--ci` + 版本一致性 + ruff 全绿。

### plan-45 设计文档十轮复盘（第 9~10 轮：跨文档同步与自洽终检）—— 十轮完成（2026-09-15）

- **第 9 轮（跨文档同步面）**：审计发现同步面远大于计划所列——`technical.md`（章节名 + **两处陈旧的「报告 19 个模块」** + 「功能语义命名表」需新增三行）、`requirements.md`、`testplan.md`（§4 回归清单）、`folders.md`（**26 处 `financial_indicator` 命中需甄别**：fetcher/analysis 保留 vs report 章节模块改名/删除）、`test-coverage.md`，以及 4 份用户文档（`README.md`/`reports-instruction.md`/`how-to-config.md`/`faq.md`）。**处置**：新增 §6.8「文档同步清单」（管理文档 / 用户文档 / 门禁脚本与索引 / 纪律四类）。
- **第 10 轮（文档自洽与命名索引）**：新增 §6.9「文档自洽终检」——两文档命名表逐字一致、条目数在施工单/守卫表/验收三处一致（21→20→19→17）、「共 N 项」表述三处一致、分层面术语无矛盾、确认十轮整改**未触碰任何生产代码**；并明确 `check-semantic-index.py` 正反向校验要求「先改表再改码」。

### plan-45 设计文档十轮复盘（第 7~8 轮：批次依赖与计数硬伤）（2026-09-15）

- **第 7 轮（批次依赖与可回退性）**：②③④ 共改 7 个文件（注册表 / 两侧可见性 / Excel 三处分派 / 模板 / 配置模板），**无法任意顺序单独回退**；新增 §6.4b「批次依赖与回退矩阵」——依赖链 ①→②→③→④（③④ 均改 `_compute_section_visibility` 与 fund 深度分组，④ 建立在 ③ 之后）、共享文件表、**逆序回退纪律**（④→③→②，每批一次提交）、版本身份（四批同属 0.11.1-dev）。
- **第 8 轮（计数一致性与非目标边界）——修正硬伤**：批次④ 实际含**两处合并**（财报两章合一 + `fund_manager` 并入 `fund_performance`），但 ④-1 未声明删除 `fund_manager` 条目、④-7/验收/§6.6b 仍写「条目数 18」。已修正为 **17**（21→20→19→17），④-1 显式删除 `fund_manager` 条目、④-2 补删除其页签名映射。非目标边界（LLM 条目不合并）经与注册表现状核对一致，予以保留。

### plan-45 设计文档十轮复盘（第 5~6 轮：接缝完整性与守卫）（2026-09-15）

- **第 5 轮（接缝完整性）**：新增 4 处漏登接缝——`excel_module_loader.py` 的模块表键与错误文案、`html_writer_display.py` 对 `market_value_sheet._weighted_avg_cost` 的**反向依赖**（删模块将 ImportError，须迁移保位）、partial 实况（全仓仅 4 个 partial，**只有 M3 需合并 partial**）、`chart_data_builder` 六图键不变但图归属章节变化；`features.py` 两个 `FeatureSwitchDef` 开关名保留。**处置**：接缝地图补 6 行、批次② 补 ②-4b/②-4c、批次④ 修正 partial 步骤、新增 §7.5 风险补充 3 条。
- **第 6 轮（守卫与可验证性）**：7 项既有守卫均在位但**无守卫清单**、**缺合并前基线方法**、「注册表 type 三处严格一致」缺正面自动化守卫。**处置**：新增 §6.6b「守卫清单与基线方法」——既有守卫表（标注每批变化处 21→20→19→18）、每批新增守卫（`test_section_type_flag_consistency`、模块加载器一致性、区块门禁、内容等价）、基线方法（批次② 前存 `docs-stm/tmp/` 快照，不入库；比对落成单测）。

### plan-45 设计文档十轮复盘（第 3~4 轮：测试面与配置面）（2026-09-15）

- **第 3 轮（测试与守卫）**：发现**同名混淆风险**——`market_value`/`category` 在 100+ 测试中属**领域层**（`DetailRow.market_value` 字段、`report/market_value.py` 市值计算、`report/category.py` 分类函数），而施工单原写「删除 `report/category.py`」会破坏领域层。修正：只迁移**纯章节写入器**，领域模块保留；新增 §6.7「领域层 vs 章节层边界」（含缓存类型域 `get_exact_type_map()` 的 `fund_manager_snapshot`/`fund_concentration_snapshot` 不改）；测试同步清单改为区分「章节键断言（逐文件行）」与「领域词（不在范围）」。
- **第 4 轮（配置与校验面）**：`_validation.py` 允许类型集合与 `config_edit.py` 硬编码处已列入 §3.2 下游清单；发现注册表 docstring「共 21 项」与架构约束表「报告 19 个模块」表述陈旧 → 收尾步骤新增「条目数表述同步」；确认 `_config_defaults.py` 的 `report_section_order` 模板随注册表自动派生（无需手改）。

### plan-45 设计文档十轮复盘（第 1~2 轮：命名链与架构约束）（2026-09-15）

- **第 1 轮（命名统一性）**：设计层新增 §3.2「命名统一的下游影响清单」——把注册表 `type` 的语义化、两侧 `board_flags` 映射键、`enable_*` 形参链、`config/_validation.py` 允许类型集合、Web 硬编码面列入同一张表，明确「三处严格一致」纪律；施工单补 ④-1b 步骤。
- **第 2 轮（架构约束符合性）**：核实代码侧接缝——两侧 `board_flags` 与 `_validation.py` 允许集合仍含旧 `type`，Web 面有硬编码；前端标签字典与 TUI 面板已按注册表派生（无需改）。**关键补充**：`enable_financial_report_digest` 形参在章节合并后必须删除（该章不再存在），涉及 `html_writer`/`excel_generator`/`_report_generation` 三处调用链。
- 施工单新增「允许保留的旧名白名单」（契约键 / 功能开关名 / 缓存前缀 / 数据源类别 / 历史记录）与「复盘记录」表。

### plan-45 实施层文档（迭代施工单）落地（2026-09-15）

- 新增 `docs-stm/plan/section-consolidation-iteration.md`（实施层，与设计层 `section-consolidation-design.md` 配套）：**命名统一总表**（旧名→新语义名，旧名全部删除留零 alias；契约层不改名）、**接缝地图**（注册表/页签名表/两侧可见性判定/Excel 分派点行号/HTML 锚点行号/页签写入器/契约写入点）、**批次②③④ 逐条施工步骤**（含命名 grep 检查、测试与文档同步清单）、收尾与门禁、风险与回退。
- `plan.md` 的 plan-45 条目补实施层文档引用并标注批次①已实施。

### 立项：报告章节整合（plan-45，重生成配置模板）（2026-09-15）

- 注册表条目 21 → 17 的四项合并（市值核算明细+持仓分类 / 持仓关系矩阵+持仓集中度 / 财报摘要并入持仓基本面 / 基金经理变更并入基金业绩），**保留吸收方主键**以免迁移 `report_section_order` pin 与开关名；按用户决定**重生成 `config.json` 与配置模板**（不做兼容）。
- **统一语义命名**（用户要求）：合并后一律用新语义名——新条目键 `holdings_detail` / `position_structure` / `fundamental_snapshot`（`fund_performance` 语义未变），页签名、页签写入器模块与函数、HTML 锚点与 partial 文件名同步改名；旧键/旧页签名/旧写入器/旧 partial **全部删除不留 alias**，配置模板与 `config.json` 重生成。**契约层保留各区块自己的契约键**（不造伪契约键）。
- 架构要点：可见性模型最小扩展——注册表可选字段 `data_flag_any`（多契约 OR，未声明时行为不变）；序号/显示名/页签名一律经注册表驱动；区块级门禁沿用「基金业绩分析章内候选比较子表」既有先例。
- 批次①（可见性模型扩展）已完成并提交：注册表字段契约注释 + Excel（`should_create_sheet`）与 HTML（`_compute_section_visibility`）两侧 OR 支持（悲观判定）+ 新增 `test_section_visibility.py` 12 例守卫；既有条目零变更、行为零变化。
- 设计文档 `docs-stm/plan/section-consolidation-design.md`（现状核实 / 四项合并方案 / 架构约束对照 / 测试与文档同步清单 / 四批次验收标准）；`plan-next` 45 → 46。

### 发布 v0.11.0 及已发布记录归档（2026-09-15）

- **发布**：`0.10.20-dev` → **v0.11.0**（本次跨越未发布的 0.10.20 编号，直接进入 0.11 系列）：`APP_VERSION`/`pyproject.toml`/README/9 份管理文档版本头/新版 changelog 段头全链同步（`check-version-consistency` [OK]）；发布数据文档按 `collect-test-coverage` 实时快照刷新（`test-coverage.md` 子表、`folders.md` 项目统计、`datasource.md` + `datasource-reliability.md` 逐类核对）；发布门禁（P2）`--mode verify,regression` 4,939 通过 / 0 失败 + 四个 `--ci` + ruff 全绿；打标签 `v0.11.0` 并推送。
- **归档（0.11 系列首份）**：`[0.11.0]` 已发布变更记录整体迁入新建的 `docs-stm/archive/v0.11.x/archived_changelog.0.11.x.md`；`plan.md` 的 plan-44 完成态迁入 `docs-stm/archive/v0.11.x/archived_plan.0.11.x.md`（P1 区自此仅保留「无待办项」与归档引用，概述补 v0.11.x 已完成项指向）；`folders.md` 目录树新增 `archive/v0.11.x/` 并刷新归档/项目文档统计；changelog 与 plan 的「归档」段各补一条链接。
- **开发版本**：打 tag 后即切换至 **0.11.1-dev**（`APP_VERSION` 与全部文档版本头），changelog 新增本轮开发段。

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。


## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0（2026-09-15，0.11 系列首份）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
