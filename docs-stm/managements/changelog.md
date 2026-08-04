# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.1-dev] - 2026-08-04

### 数据质量仪表盘（18 章「数据源可用性矩阵」改造，分三轮落地）

- **轮1 品种覆盖诊断**：新增 `src/python/core/holding_status.py`，`build_coverage_summary()` 逐品种判定数据状态（本地信号：代码格式/名称比对；数据信号：行情/净值可用性），按优先级 代码格式 > 数据缺失 > 名称不匹配 > 有行情，输出 C19 契约 `position_status`（`available/items/abnormal_count/summary`，items 含 code/name/account/status/status_label/reason，status 取值 ok/nav_missing/possibly_delisted/bad_code_format/name_mismatch）。在报告生成 both/full 路径经 `merge_pipeline_data()` 注入 `pipeline_data`。
- **轮2 源健康 + 品种覆盖两区块**：新增 `src/python/report/data_quality_sheet.py`（`write_data_quality_sheet()` 写「数据质量仪表盘」标题 + 源健康区块 + 品种覆盖区块；异常品种行红色标注；无行情时写降级占位）。Excel 18 章页签在开关启用时改用仪表盘样式，关闭时回归旧「数据源可用性矩阵」（辅助函数 `_write_data_source_matrix_sheet` 提取保留）。HTML 18 章追加品种覆盖表。config 新增开关 `report_submodules.data_quality`（默认关），`is_enable_data_quality()` 读取；编排层 basic/both/full 三条路径统一接线。
- **C19 契约注册**：`position_status` 在 `pipeline_data_builder.py` `_PIPELINE_DATA_KNOWN_KEYS`/`_PREP_KNOWN_KEYS`/类型映射注册，`merge_pipeline_data()` 合并；契约类型/版本/写入消费模块已预定义于 technical.md 附录 H。
- **轮3 可信度摘要 + 单日跳变检测**：新增 `src/python/core/data_freshness.py`，`classify_freshness()` 逐品种分类新鲜度（fresh 当日 / cached 上交易日 T-1 / stale 过期 / degraded 无有效行情），`detect_price_jumps()` 仅对 fresh/cached 品种判定单日 |涨跌幅| ≥ ±20% 跳变（label「疑似数据错误（单日 +X.XX%）」，stale/degraded 跳过以免跨非交易日累计涨跌误报），`build_freshness_summary()` 输出 C19 契约 `data_freshness`（available/items/abnormal_count/summary）。交易日依据 `report/market_value.py::get_last_trading_day/get_prev_trading_day`（akshare 日历缓存）。18 章「数据质量仪表盘」页签新增可信度区块，HTML 报告头部新增「N 个品种数据异常」摘要行；`data_freshness` 注册进 `pipeline_data_builder.py` 4 处集合/映射，编排层 basic/both/full 三条路径统一注入。
- **测试**：新增 `src/test/unit/report/test_data_quality_sheet.py`（13 例：build_coverage_block 规范化 / 仪表盘三区块写入 / 降级占位 / 异常行标注 / 空矩阵兜底 / 跳变红色标注 / 旧样式回归）、`src/test/unit/core/test_data_freshness.py`（19 例：新鲜度分类 6 / 单日跳变检测 8 / 可信度摘要组装 5，覆盖阈值、非交易日不误报、降级跳过跳变、过期缓存分类）、`src/test/unit/config/test_config.py` 新增 `is_enable_data_quality` 5 例、`src/test/unit/report/test_holding_status.py` 品种覆盖诊断用例、`test_orchestrator.py` 断言 position_status/data_freshness 注入与开关透传。
- **向后兼容**：开关默认关，既有 18 章输出（Excel 矩阵 + HTML 源健康表）不变，由旧样式回归测试断言。

### 行动建议章（20 章，独立顶层章节，轮4 框架落地）

- **计算层**：新增 `src/python/analysis/action_advisor.py`，`build_action_data()` 单源计算（纯计算层，不依赖 report/），输出 C19 契约 `action_data`（`available/summary/rebalance_signals/discipline_signals/rebalance_advice/attribution`）——再平衡信号（单品占比超警戒线）轮4 落地；交易纪律轮5 落地；调仓建议/收益归因空子块框架先行、后续轮次填充，报告结构保持稳定。
- **章节注册**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 新增 `action`（type=`action`、data_flag=None、number=20），`_REPORT_SHEET_NAMES` 注册「行动建议」；`data_source_status` 顺延为 21、`llm_usage` 为 22（共 22 模块）。
- **独立顶层开关**：config 新增 `enable_action`（默认关），`_config_defaults.py`/`_core.py`（`is_enable_action()`）/`__init__.py` 导出/`_validation.py`（`_validate_enable_boards`）四处接线；board 层 `html_writer._compute_section_visibility` 与 `excel_sheet_factory.create_sheets` 的 `board_flags` 均新增 `action` 条目，两层可见性模型（§4.5）同步。
- **单源计算两处呈现（C14/C19）**：`action_data` 由 `report/orchestrator.py` 组装（both 路径在 `_report_generation.py` 直接以 `build_action_data` 注入），HTML 20 章 `partials/action_section.html` + Excel `report/action_sheet.py` + 14 章智囊团深度复盘「行动摘要」子块（引用 20 章序号）共享同一对象，无模块级全局变量（C14）。
- **C19 契约注册**：`action_data` 在 `pipeline_data_builder.py` 4 处集合/映射注册，契约类型/写入/消费模块预定义于 technical.md 附录 H。
- **测试**：新增 `src/test/unit/analysis/test_action_advisor.py`（计算/降级）、`src/test/unit/report/test_action_html.py`（10 例：20 章渲染/信号表/空子块占位/不可用占位/开关关闭隐藏 + 14 章「行动摘要」子块三态 + 单源计算断言）、`src/test/unit/report/test_action_sheet.py`（7 例：Excel 四子块/信号行/占位/归因/降级）；`test_registry.py`/`test_config.py`/`test_config_validation.py`/`test_orchestrator.py`/`test_html_report_structure_edge.py`/`test_scenario_section_order.py` 同步（22 模块、7 种可见性类型、action_data 注入）。
- **向后兼容**：`enable_action` 默认关，关闭时 20 章不渲染、14 章与现状一致（无行动摘要子块）。

### 交易纪律（行动建议 20 章，轮5 落地）

- **纪律引擎**：新增 `src/python/analysis/trade_discipline.py`，`compute_discipline_signals()` 纯计算（不依赖 report/）——止盈（收益率 ≥ 止盈线，默认 +20%）、止损（收益率 ≤ 止损线，默认 -15%）、回撤（组合相对历史峰值回撤 ≥ 回撤线，默认 10%，需注入 `portfolio_peak_mv`）三类规则，输出「触发 + 距触发幅度 + 建议动作」结构化信号（`code/name/rule/value/status_label/triggered/distance_pct/action`）；缺 `profit_rate`/总市值 0/空持仓安全跳过。
- **静默期复用**：纪律信号复用 `analysis/_silence.py` 静默机制（默认 30 天可配），持久化独立文件 `data/state/discipline_silence.json`（与再平衡静默文件分离，避免信号互相抑制）；同品种触发后 N 天内不重复告警。**静默范围**：仅单品信号（止盈/止损）参与静默；组合级回撤信号 code 为空天然豁免，与再平衡对组合级信号（category/summary）的约定一致——回撤是持续状态，峰值恢复前持续提示更合理（已文档化）。
- **接入**：`action_advisor.build_action_data()` 组装时调用纪律引擎填充 `discipline_signals`（新增可选入参 `discipline_config`/`portfolio_peak_mv`）；both 路径 `_report_generation.py` 向 `build_action_data` 传递完整估值字段（含 `profit_rate/cost/profit`），其中 `profit_rate` 统一换算为**百分数**（小数 ×100，同 full 路径 orchestrator 口径），纪律引擎按百分数阈值比较——此前 both 路径传小数值导致止盈/止损纪律永不触发，已修复并补回归测试。20 章纪律子块渲染（HTML 表格 + Excel 页签）复用既有字段契约。
- **配置**：config 新增 `discipline` 段（`take_profit_pct`/`stop_loss_pct`/`drawdown_pct`/`silence_days`），`_config_defaults.py` 默认值 + 模板同步，`_validation.py` 新增 `_validate_discipline_config` 校验——含**符号语义约束**：止盈线须为正数、止损线须为负数（符号约束自动保证「止盈线 > 止损线」，杜绝同品种同时触发止盈与止损的误配）。
- **测试**：新增 `src/test/unit/analysis/test_trade_discipline.py`（20 例：止盈触发/线上边界/合规不触发/止损触发/-15% 行为断言/距触发幅度/信号结构/自定义阈值/回撤触发/无峰值跳过/回撤边界/正值回撤配置规则文本归一/静默抑制/静默过期恢复/静默禁用/多品种混合/空持仓/总市值 0/缺 profit_rate 跳过）；`test_action_advisor.py` 改为验证纪律信号经 `build_action_data` 流入；`test_config_validation.py` 新增 `TestValidateDisciplineConfig`（9 例）；`test_orchestrator.py` 新增 both 路径 `profit_rate` 百分数契约回归测试；conftest `_isolate_sensitive_paths` 新增 `trade_discipline._SILENCE_FILE` 隔离。纪律模块覆盖率 100%。
- **回撤数据接线说明**：回撤纪律为可选能力——管线侧 `portfolio_peak_mv` 需组合历史估值数据（当前 orchestrator 未计算），无峰值时安全跳过；接入点已参数化预留，历史峰值注入属后续历史增强范围。

### 调仓建议可行化层（行动建议 20 章，轮6 落地）

- **可行化层**：新增 `src/python/analysis/rebalance_advisor.py`，`build_rebalance_advice()` 纯计算（不依赖 report/）——把再平衡/纪律触发信号转成可执行调仓订单，每条含 code/name/operation/shares/amount/fee/cash_after。
- **份额取整（C1 合规）**：复用 `core/code_utils.py`（is_a_share_code / is_exchange_fund_code / is_otc_fund_by_name）判定证券类型——A 股一手 100 股向下取整、场内基金/ETF 一手 100 份、场外基金整数份；不足一手（取整为 0）不生成建议。场外基金判定优先于 A 股（00 代码区间重叠，先经名称关键词排除）。
- **审查修复（rf-214~216）**：`core/code_utils.py` 的 `_OTC_FUND_NAME_KW` 补「债券/指数/股票」关键词（修复 00 前缀债券型基金如 `000311` 误判为 A 股导致漏计赎回费）；`estimate_fee()` 增加卖出方向守卫（未知操作抛 ValueError）；`_round_to_lot`/`estimate_fee` 名称缺失（None）归一化为空串防御。残留建模限制见 rf-217（1 前缀场外持有基金需持仓渠道上下文，当前默认场内口径）。
- **费用估算**：本地静态费率表（佣金万 2.5 最低 5 元 / 印花税 0.05% 仅 A 股卖出 / 赎回费 0.5% 仅场外基金卖出），`estimate_fee()` 导出，费率表可经 `fee_table` 覆盖（测试固定 fixture 断言精度 <0.01 元）。
- **现金缓冲**：从 available_cash 起按执行顺序累计卖出净额（金额 - 费用），任一条执行后现金为负则剔除（现金负值防护）；同品种触发多条（再平衡 + 纪律）时去重保留优先级最高（止损 > 部分止盈 > 卖出减仓）。
- **接入**：`action_advisor.build_action_data()` 在信号计算后调用可行化层填充 `rebalance_advice`；full 路径 orchestrator 的 holdings_details 补充 shares/price（供计算卖出份额，both 路径本就具备）；HTML 20 章调仓建议表格与 Excel 子块补 金额/调仓后现金 两列；附录 H 契约更新。
- **测试**：新增 `src/test/unit/analysis/test_rebalance_advisor.py`（27 例：份额取整一手 5 / 操作生成 3 / 费用估算 7 / 现金缓冲 3 / 优先级去重 2 / 多品种与守卫 7，含债券基金赎回费、港股整数份、名称缺失、未知操作守卫回归）；`test_action_advisor.py` 新增 shares/price 字段与调仓建议流经、摘要计数；`test_action_html.py`/`test_action_sheet.py` 补调仓建议表格行渲染；`test_code_utils.py` 补 `is_otc_fund_by_name` 债券/指数/股票关键词与股票负例。可行化层覆盖率 ≥85%。
### 任务编号冲突消解（rf-205~213 重编号为 rf-209~217）

- **背景**：行动建议 20 章（轮4~6）开发期间，上游分支（任务编号保障机制）同时合并了已修复条目 rf-204~208（含 fact_checker 数值校验/门禁补强/版本一致性回归）。rebase 落盘后「已提交侧已用 rf-205~208」与「本侧开发用的 rf-205~213」重叠，编号源与已修复表交叉冲突。
- **处理**：本侧 9 条按冲突消解规则整体重编号——轮5 五条（profit_rate 修正、组合回撤峰值、纪律符号校验、注释清理、回撤线归一）由 rf-205~209 → **rf-209~213**；轮6 四条（债券基金关键词、卖出方向守卫、名称缺失防御、1 前缀场外持有建模限制）由 rf-210~213 → **rf-214~217**。已提交侧 rf-204~208 保持原名不动，`rf-next` 由 214 递增为 **218**。changelog 轮6 审查修复引用同步为 rf-214~216、建模限制引用为 rf-217。
- **验证**：`check-task-numbering.py --ci` 全局扫描（当前文档 + 全部归档）通过——已用最大 rf-217，`rf-next = 218` 严格递增、无冲突。

### rf-208 门禁补强：任务编号标识符/注释纪律（check-code-traces.py / check-doc-traces.py）

- **缺陷**：语义命名纪律要求代码标识符与注释一律语义名、禁任务代号（`plan-N`/`rf-N`/B 系列/F 系列等），但 `check-code-traces.py` 只扫注释且 CODE 模式仅 `(?:rf|plan|R)-\d+`——抓不住 `b_series`/`G系列`/`F4`/`B6` 系列代号，也完全不扫代码标识符（变量/函数/类名）。
- **修复**：
  - **注释侧**（`check-code-traces.py` + `check-doc-traces.py` 的 CODE 模式）：新增 `[A-Za-z]系列`、单字母`_series` 两条零误报系列代号模式（负向 lookbehind 排除 `drawdown_series` 等合法多字母词）。
  - **标识符侧**（`check-code-traces.py` 新增扫描维度）：`.py` 用 `ast` 精确提取函数/类/参数/赋值目标/导入别名，`.js/.mjs` 用正则提取声明名；`IDENTIFIER_PATTERNS` 捕获大写裸字母+数字（`F4`/`B6`）、单字母`_series`/`系列`、嵌入 `rf/plan`+数字（`rf_205_fix`/`plan18_hack`）；`IDENT` 类等同 CODE 退出码 2。
  - **明确不捕获**（避免误伤，注释侧含原因）：小写短局部名（`h1/t1/f1`——Future/测试脚手架）、注释中裸"族字母+数字"（与 Excel 单元格 `A1/B2` 结构性冲突）、`C20`/`P1`/`S-P1`/`A3`/`R17` 等合法约束/优先级/场景/需求交叉引用。
- **测试**：`src/test/unit/scripts/test_trace_check_scripts.py` 新增 9 例——注释系列代号正/负用例（`b_series`/`G系列` 命中；`drawdown_series`/`全系列`/`C20`/`A1:B1` 不命中）、标识符违规命中与合法短局部不命中、`_iter_identifiers` AST/JS 提取断言。
- **验证**：`check-code-traces.py --ci`/`check-doc-traces.py --ci` 对现有代码仓 0 命中（新增模式零误报）。

### rf-207 数值校验策略 1 忽略句中明确品种代码（漏检）（fact_checker 数值一致性）

- **缺陷**：`_evaluate_percent_value` 策略 1 做全局最近邻匹配，句中已含明确品种代码/名称时仍与全部参考收益率比较——数值只要接近任一无关品种（容差内）即判定一致，不按句中主体校验。例：601939 实际 1.87%、240012 实际 2.24%，「建设银行收益率 3.2%」→ 3.2 与 240012 差 0.96≤容差被误判通过，漏检与主体 601939 的 1.33 超差。与 rf-205（过修）方向相反，属漏检。
- **修复**：主体解析提前到策略 1 前——句中有明确持仓主体（句中单个持仓代码 / 名称指代）时按该主体实际收益率校验（容差内通过、超差报错到该主体），无主体或主体无收益率数据（`stock_rates_abs` 缺失）时回退全局最近邻（历史语义）；主体解析块上移后去除底部重复逻辑。
- **测试**：`src/test/unit/llm/test_fact_checker.py` 新增 `TestRegressionExplicitSubjectBeatsGlobalNearest` 5 例——名称/代码指代主体超差被修正到该主体、主体容差内通过、无主体回退全局最近邻、主体无收益率数据回退不崩溃。
- **验证**：全仓 `check-code-traces.py --ci` 仍 0 命中（新注释无任务编号）；llm 目录 738 例全过。

### rf-206 版本一致性回归测试 Windows 路径分隔符失效（test_check_version_consistency）

- **缺陷**：`TestDocHeaderRegistration::test_doc_header_docs_registered_as_header` 硬编码正斜杠路径（`docs-stm/managements/plan.md`），而 `check-version-consistency.py` 的 `CHECKS` 用 `Path` 拼接、`relative_to` 在 Windows 返回反斜杠分隔 → `types.get(rel)` 恒为 None，dev-verify 必失败。随 rf-204 引入，从未在 Windows 通过。
- **修复**：构造 CHECKS 类型字典时把 `relative_to` 结果分隔符规范化为 `/`（`.replace("\\", "/")`），Linux/macOS 无副作用。
- **测试**：修复即回归——同一用例在 Windows 通过，dev-verify 全绿。

### rf-205 事实校验误修正非收益率数值 + 亏损符号丢失（fact_checker 数值一致性）

- **缺陷**：`_evaluate_percent_value` 的 closest-ref 最近邻匹配假设报告每个百分比都是持仓收益率，把非收益率语境数值误修正并污染 2026-08-04 报告 HTML：胜率 `80%→8.9%`、评分权重 `20%/25%→16.6%/26.0%`、相对基准跑输差 `1.10%→2.2%`；且 `stock_rates_abs` 取绝对值使亏损品种（518880 实际 -8.86%）修正输出 `+8.9%`，亏损写成盈利。
- **修复**：补「胜率/权重/相对基准跑输跑赢」三种近邻语境跳过（数值紧邻语境词才判定，避免同句真实收益率被连带跳过）；修正输出改用带符号收益率（`stock_rates`/`profit_rate_signed`）保留盈亏方向。
- **测试**：`src/test/unit/llm/test_fact_checker.py` 新增 `TestRegressionFalseCorrectionContexts` 5 例（胜率/权重/相对基准不被修正、亏损符号保留、run_fact_check 整链路摘要无修正明细）。
- **关联**：方向相反的同源弱点（句中含明确代码时策略 1 仍全局最近邻 → 漏检）见 rf-207（已修复）。

### rf-204 版本一致性检查缺陷修复（check-version-consistency.py）

- **缺陷**：`_check_contains` 仅判断全文是否包含目标版本串，正文偶然出现的版本号（如 v0.10.0）会掩盖头部 `文档版本：` 行未同步，导致漏检误判 [OK]。
- **修复**：管理文档改用新增的 `header` 断言——按 `> 文档版本：{v}` 头部行首精确匹配；`--fix` 模式自动修正头部版本行；changelog（`[X.Y.Z]` 标题行）保留 contains、README（`当前版本：`）保留 exact。
- **测试**：新增 `src/test/unit/scripts/test_check_version_consistency.py`（9 例，覆盖 rf-204 回归场景/头部精确匹配/--fix 修正/CHECKS 注册防止退回 contains）。

### 历史任务编号冲突清理（check-task-numbering.py 全局校验）

- **背景**：v0.8 归档（2026-07-30 创建）已占用 plan-12/13/14 与 rf-90~135；v0.9 开发（07-31 起）重新从 plan-12、rf-90 起编号，造成两代归档编号交叉冲突。
- **plan 编号修复**：v0.9 归档中的组合演进项 plan-12 → **plan-15**；HTML 左侧 TOC 项（新需求）→ **plan-16**（不得占用 v0.8 已用 plan-12）。`plan-next` 更新为 **17**。
- **rf 编号修复**：v0.9 归档中与 v0.8 冲突的 30 个编号（90-112、115、116、119、122-125）按升序整体重命名为 **rf-174 ~ rf-203**（定义行 + changelog/plan 归档内交叉引用同步替换；`archived_changelog.0.9.x.md` L424 为 v0.8 迁移参考行，保留原编号）。`rf-next` 更新为 **204**。
- **约束遵守**：跨文档引用带前缀、历史已归档编号不回收、编号源标记单调递增不回退；`scripts/check-task-numbering.py --ci` 验证 plan（17 > 16）与 rf（204 > 203）全局无冲突。

### 任务编号自动保障机制（三层 + P0 门禁）

- **校验脚本**：新增 `scripts/check-task-numbering.py`（`--kind plan/rf` 单序列、`--ci` 静默模式），扫描当前管理文档 + 全部历史归档，断言 `plan-next`/`rf-next` 严格大于已用最大编号，防止新增编号撞历史。
- **Claude Code hook**：新增 `scripts/check-task-numbering-hook.py`（PostToolUse，编辑 `plan.md`/`review-findings.md` 后自动校验、失败中断编辑）+ `scripts/install-claude-hook.py`（跨机器接线，`.claude/settings.json` 被 gitignore 排除，clone 后运行一次激活）。
- **git pre-commit**：新增 `.githooks/pre-commit`（提交涉及编号文档时自动校验）+ `.githooks/install-hooks.sh`（`core.hooksPath` 为本地配置，clone 后运行一次激活，`--off` 停用）。
- **dev-verify 门禁**：`test_runner.py` dev-verify 模式新增 `preflight` 机制，运行测试前自动执行 `check-task-numbering.py --ci`，失败即中止并提示修正。
- **P0/P2 门禁描述**：CLAUDE.md 提交前（P0）/发布前（P2）门禁追加 `check-task-numbering.py --ci`，与 `check-code-traces.py` 同构。
- **测试**：新增 `src/test/unit/scripts/test_task_numbering_hook_scripts.py`（14 例，hook 目标判定/放行/拦截/OSError 兜底/双注入方式 + 安装脚本幂等/合并/卸载；全部用 tmp_path 假文件隔离，不触碰真实编号文档）。

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
