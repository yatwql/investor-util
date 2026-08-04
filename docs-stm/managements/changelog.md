# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.3-dev] - 2026-08-04

### 开发中（未发布）

#### 风格与因子分析合并章 + 行业 Beta 子表（plan-21 轮12，章节数 20→19）

- **物理合并**：合并原「基金风格分析」（`fund_style_sheet.py`）+「因子暴露分析」（`factor_exposure_sheet.py`）→ 统一渲染模块 `src/python/report/style_factor_sheet.py`，章节 sheet key 统一为 `style_factor`，一章三区块渲染：区块一基金风格表（8 列）+ 区块二风格因子回归（5 列 + 基准对照）+ 区块三行业 Beta 子表（7 列，`industry_beta=None` 隐藏 / `available=False` 占位）；删除旧两个渲染模块，`core/registry.py` `_REPORT_SECTION_DEFAULT` 的 `fund_style`/`factor_exposure` 合并为 `style_factor`（number 9），registry.number 连续编号重新整理 20→19，`data_source_status`=18、`llm_usage`=19。
- **行业 Beta 子表**：新增 `src/python/analysis/industry_beta.py`，`compute_industry_beta_analysis()` 复用 `factor_exposure.py::compute_factor_exposure` 单因子 OLS（不重复实现），行业穿透分类复用 `batch_fetch_industry_data`（`industry_` 前缀缓存，C1 复用 `core/code_utils.py` 判定）；`INDUSTRY_INDEX_MAP` 映射 12 个中证行业指数（银行=sh000986、证券=sz399975、白酒/食品饮料=sz399997、半导体/电子=sz399995、有色/贵金属=sz399996、煤炭=sz399998、医药=sz399989、钢铁=sz399994、房地产=sh000980、能源=sh000928、环保=sz399973、保险=sz399983）；指数 K 线复用 `history_index` 通道（Chain + session_cache，C4/C6）；开关 `report_submodules.industry_beta` **默认关**。
- **C19 契约增删**：`pipeline_data_builder.py` 删除 `factor_exposure` 旧注册，新增 `style_factor_data` 主键（13 键：available/summary/style_table/factor_regressions/benchmark/industry_beta 等）+ 内嵌 `industry_beta` 子键（7 键：available/exposure/index_codes/betas/t_stats/significant/correlations/unmapped_industries）；`orchestrator.py` 新增 `compute_industry_beta_data()` 并在 full/both 路径注入 `style_factor_data`（含 `industry_beta` 组装）；附录 H 契约类型/版本/写入消费模块同步预定义。
- **双层可见性**：board 层 `enable_fund_deep_analysis` + data 层 `style_factor_data`；可见性 = `style_factor_data is not None or style_analysis is not None`，旧 `factor_exposure_data` 数据 flag 一并迁移。
- **HTML/Excel 同步**：`report_template.html` 合并 section 号 9（区块标题 `.block-title` CSS + 行业 Beta 区块渲染分支）、`excel_generator.py`/`excel_fund_deep_analysis.py`/`excel_module_loader.py`/`html_writer.py`/`_report_generation.py` 同步 `style_factor`/`style_factor_data` 接线。
- **测试**：新增 `src/test/unit/analysis/test_industry_beta.py`（11 例：行业暴露占比 / Beta 回归 / 显著性 / 数据不足 / 开关关隐藏 / push2 行业分类降级占位 / 固定 fixture 解析解误差 <0.01）、`src/test/unit/report/test_style_factor_sheet.py`（合并章三区块渲染 / 行业 Beta 三态 / 可见性）；旧 `fund_style`/`factor_exposure` 测试迁移适配；`test_orchestrator.py`/`test_html_report_structure*.py`/`test_registry.py`/`test_config*.py`/`test_scenario_section_order.py` 同步（键 `factor_exposure`→`style_factor_data`、19 个章节、7 种可见性类型）。新增模块覆盖率：industry_beta 94% / style_factor_sheet 97%。
- **文档同步**：technical.md（模块数 20→19、data_flag 表、§4.8 一章三区块、附录 H 契约）、requirements.md（§6.3/6.4 章节合并重编号）、全部用户手册（how-to-menu / how-to-config / how-to-use-registry / reports-instruction / faq / datasource）、test-coverage.md（模式计数 + 功能域 + unit 子分组）、folders.md 目录树。

#### 基金业绩分析章候选基金比较增强模式（plan-21 轮13，`candidate_compare` 默认关）

- **核心模块**：新增 `src/python/report/fund_candidate.py`——`resolve_candidates()`（6 位代码校验 / 去重 / 超 10 截断 + `exceed_limit` 标记）、`build_candidate_compare_data()`（开关门控 → 无有效候选降级 → 正常）、`_build_candidate_row()`（收益近1月/3月/6月/1年 + 同类排名 + 评级 + 最大回撤 + 风格 + 与现有持仓重合度，单候选失败 `available=False` 短路不阻塞其余）。比较维度不含规模/费率（无数据源，已验证）；重合度复用 `fund_overlap.compute_overlap_matrix`（Jaccard），风格复用 `fund_style_classify.classify_fund_style`（C1 复用）；`risk_analysis` 最大回撤百分数数值 `/100.0` 归一化为小数与 `syl_*_raw` 口径一致（Excel FMT_PERCENT 直接可用）。
- **配置层**：`report_submodules.candidate_compare` **默认关**（关闭时 `build_candidate_compare_data` 返回 None，基金业绩分析章输出与改造前一致）+ 顶层 `comparison_candidates`（6 位基金代码列表 ≤10）；`_core.py` 新增访问器 `is_enable_candidate_compare` / `get_comparison_candidates`（镜像既有 data_quality 模式，非 list/str/int 数值归一化容错）；`_validation.py` 新增 `_validate_comparison_candidates`（非列表 / 非法项 / >10 告警，数值项允许）。
- **Excel 渲染**：`fund_performance.py` 末尾（数据状态脚注后、冻结/列宽前）条件渲染候选比较子表 `_write_candidate_compare_block`（11 列：候选基金/代码/评级/近1月/近3月/近6月/近1年/同类排名/最大回撤/风格/与持仓重合），可用行百分比列 FMT_PERCENT，失败行"获取失败"占位，`exceed_limit`/`invalid` 各写提示行。
- **HTML 渲染**：`html_renderers._render_fund_performance_section` 返回 `(perf_data, candidate_data)`，`html_writer` 传入模板；`report_template.html` 基金业绩分析章主业绩表后新增候选比较区块（`.block-title`「候选基金比较（候选来自 config.comparison_candidates）」+ 11 列表格 + 失败占位行 + 超限/无效脚注），`candidate_data` 不可用时整块不输出（行为断言）。
- **测试**：新增 `src/test/unit/report/test_fund_candidate.py`（23 例：候选校验/截断/开关门控/全维度行/单候选失败降级/CLI 合并/缺期间非法值/风格与重合度失败降级/现有持仓收集），`test_html_writer.py` 新增 `TestCandidateCompareTemplate`（7 例，从真实模板配平截取候选区块渲染，断言开关关无子表、开启 11 列正确、失败占位、超限/无效脚注），`test_config.py`/`test_config_validation.py` 新增候选配置访问器与校验测试。fund_candidate 覆盖率 99%。
- **文档同步**：plan.md（plan-21 轮13 已完成）、plan-investment-iteration.md（轮13 验收签字）、how-to-config.md（开关 + 候选列表说明）、reports-instruction.md（基金业绩分析比较子表说明）、folders.md 目录树补 `fund_candidate.py`/`test_fund_candidate.py`。

## [0.10.2] - 2026-08-04

### 配置家族模块化重构（config 包）

- **llm_settings 解析拆分为独立模块**：新增 `src/python/config/_llm_settings.py`（`get_llm_config()` 解析入口从 `_core.py` 迁出），`_core.py` 减 299 行回归 config.json 读写协调者角色；`__init__.py` 导出同步。
- **命名对称**：`_llm_defaults.py` 更名为 `_llm_settings_defaults.py`（与 `_llm_settings.py` 解析入口配对、与 `<配置文件名>_defaults` 命名风格统一），`_llm_providers_defaults.py` 模板 dict 化。
- **顶层键 patch 引擎迁入 `_json_patch.py`**：`_core.py` 中 6 个 JSON 文本 patch 引擎函数（顶层键扫描/替换/删除）迁入 `_json_patch.py`，`_core.py` 聚焦 config.json 读写协调，职责边界清晰。
- **llm_settings 模板坏 JSON 修复**：`_get_default_llm_settings_template()` 生成的模板剥注释后无法解析（模块块缺键名、尾逗号），按 `_config_defaults.py` 手拼风格重写，模板现可解析且与 `_DEFAULT_LLM_SETTINGS` 深度一致；`data/config/config.json` 补齐 4 个缺失默认键（`enable_portfolio_evolution`/`enable_action`/`report_submodules`/`discipline`）并清理 B 区历史章节编号注释。
- **测试隔离补齐**：features.json 持久化路径加入 `_isolate_sensitive_paths` fixture；新增 `TestLlmSettingsTemplateConsistency` 一致性测试（对照 config 模板测试）。

### 语义命名与章节引用清理

- **语义命名审计修复**：修复 3 处合并后语义残留（plural `_write_history_sheets`→`_write_portfolio_history_drawdown_sheet`、docstring「§阶段 C 轮 9」、注释「行动建议独立章 17」）。
- **源码/模板注释章节数字引用清理**：统一为章节标题语义，消除过期编号与历史变更描述。
- **文档章节引用标题化**：技术文档/用户手册（reports-instruction 等）章节引用统一改为标题语义，清理过期页签编号（22→20、21→20）。

### 文档与计划状态同步

- **管理+用户文档序号漂移修正**：requirements 页签编号 1~22→1~20、testplan 1.~21.→1.~20.、README 分六组→分七组 + 行动建议组、how-to-menu 补行动建议列、faq 1.~22.→1.~20.、folders 20 章表格→行动建议章表格共用。
- **plan.md P1 状态更新**：plan-17~20（轮 1~11）标记已完成，推荐实施顺序 ①~④ 标 ✅，待办序列自 ⑤ 起；迭代计划文档阶段 A~C 状态列标注已完成。
- **README 章节编号修正**：主报告 21 页签→20、数据源健康检查 #20→#19（与 registry 20 模块对齐）。

### 工程与门禁

- **启用 git pre-commit 任务编号校验 hook**（`.githooks/pre-commit` 补执行位），提交涉及编号文档时自动校验，与 `check-task-numbering.py` 双轨保障。

## [0.10.1] - 2026-08-04

### 数据质量仪表盘（「数据源可用性矩阵」章改造，分三轮落地）

- **轮1 品种覆盖诊断**：新增 `src/python/core/holding_status.py`，`build_coverage_summary()` 逐品种判定数据状态（本地信号：代码格式/名称比对；数据信号：行情/净值可用性），按优先级 代码格式 > 数据缺失 > 名称不匹配 > 有行情，输出 C19 契约 `position_status`（`available/items/abnormal_count/summary`，items 含 code/name/account/status/status_label/reason，status 取值 ok/nav_missing/possibly_delisted/bad_code_format/name_mismatch）。在报告生成 both/full 路径经 `merge_pipeline_data()` 注入 `pipeline_data`。
- **轮2 源健康 + 品种覆盖两区块**：新增 `src/python/report/data_quality_sheet.py`（`write_data_quality_sheet()` 写「数据质量仪表盘」标题 + 源健康区块 + 品种覆盖区块；异常品种行红色标注；无行情时写降级占位）。Excel「数据源可用性矩阵」章页签在开关启用时改用仪表盘样式，关闭时回归旧「数据源可用性矩阵」（辅助函数 `_write_data_source_matrix_sheet` 提取保留）。HTML「数据源可用性矩阵」章追加品种覆盖表。config 新增开关 `report_submodules.data_quality`（默认关），`is_enable_data_quality()` 读取；编排层 basic/both/full 三条路径统一接线。
- **C19 契约注册**：`position_status` 在 `pipeline_data_builder.py` `_PIPELINE_DATA_KNOWN_KEYS`/`_PREP_KNOWN_KEYS`/类型映射注册，`merge_pipeline_data()` 合并；契约类型/版本/写入消费模块已预定义于 technical.md 附录 H。
- **轮3 可信度摘要 + 单日跳变检测**：新增 `src/python/core/data_freshness.py`，`classify_freshness()` 逐品种分类新鲜度（fresh 当日 / cached 上交易日 T-1 / stale 过期 / degraded 无有效行情），`detect_price_jumps()` 仅对 fresh/cached 品种判定单日 |涨跌幅| ≥ ±20% 跳变（label「疑似数据错误（单日 +X.XX%）」，stale/degraded 跳过以免跨非交易日累计涨跌误报），`build_freshness_summary()` 输出 C19 契约 `data_freshness`（available/items/abnormal_count/summary）。交易日依据 `report/market_value.py::get_last_trading_day/get_prev_trading_day`（akshare 日历缓存）。「数据源可用性矩阵」章「数据质量仪表盘」页签新增可信度区块，HTML 报告头部新增「N 个品种数据异常」摘要行；`data_freshness` 注册进 `pipeline_data_builder.py` 4 处集合/映射，编排层 basic/both/full 三条路径统一注入。
- **测试**：新增 `src/test/unit/report/test_data_quality_sheet.py`（13 例：build_coverage_block 规范化 / 仪表盘三区块写入 / 降级占位 / 异常行标注 / 空矩阵兜底 / 跳变红色标注 / 旧样式回归）、`src/test/unit/core/test_data_freshness.py`（19 例：新鲜度分类 6 / 单日跳变检测 8 / 可信度摘要组装 5，覆盖阈值、非交易日不误报、降级跳过跳变、过期缓存分类）、`src/test/unit/config/test_config.py` 新增 `is_enable_data_quality` 5 例、`src/test/unit/report/test_holding_status.py` 品种覆盖诊断用例、`test_orchestrator.py` 断言 position_status/data_freshness 注入与开关透传。
- **向后兼容**：开关默认关，既有「数据源可用性矩阵」章输出（Excel 矩阵 + HTML 源健康表）不变，由旧样式回归测试断言。

### 行动建议章（「行动建议」章，独立顶层章节，轮4 框架落地）

- **计算层**：新增 `src/python/analysis/action_advisor.py`，`build_action_data()` 单源计算（纯计算层，不依赖 report/），输出 C19 契约 `action_data`（`available/summary/rebalance_signals/discipline_signals/rebalance_advice/attribution`）——再平衡信号（单品占比超警戒线）轮4 落地；交易纪律轮5 落地；调仓建议/收益归因空子块框架先行、后续轮次填充，报告结构保持稳定。
- **章节注册**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 新增 `action`（type=`action`、data_flag=None、number=20），`_REPORT_SHEET_NAMES` 注册「行动建议」；`data_source_status` 顺延为 21、`llm_usage` 为 22（共 22 模块）。
- **独立顶层开关**：config 新增 `enable_action`（默认关），`_config_defaults.py`/`_core.py`（`is_enable_action()`）/`__init__.py` 导出/`_validation.py`（`_validate_enable_boards`）四处接线；board 层 `html_writer._compute_section_visibility` 与 `excel_sheet_factory.create_sheets` 的 `board_flags` 均新增 `action` 条目，两层可见性模型（§4.5）同步。
- **单源计算两处呈现（C14/C19）**：`action_data` 由 `report/orchestrator.py` 组装（both 路径在 `_report_generation.py` 直接以 `build_action_data` 注入），HTML「行动建议」章 `partials/action_section.html` + Excel `report/action_sheet.py` + 「智囊团深度复盘」章「行动摘要」子块（引用「行动建议」章序号）共享同一对象，无模块级全局变量（C14）。
- **C19 契约注册**：`action_data` 在 `pipeline_data_builder.py` 4 处集合/映射注册，契约类型/写入/消费模块预定义于 technical.md 附录 H。
- **测试**：新增 `src/test/unit/analysis/test_action_advisor.py`（计算/降级）、`src/test/unit/report/test_action_html.py`（10 例：「行动建议」章渲染/信号表/空子块占位/不可用占位/开关关闭隐藏 + 「智囊团深度复盘」章「行动摘要」子块三态 + 单源计算断言）、`src/test/unit/report/test_action_sheet.py`（7 例：Excel 四子块/信号行/占位/归因/降级）；`test_registry.py`/`test_config.py`/`test_config_validation.py`/`test_orchestrator.py`/`test_html_report_structure_edge.py`/`test_scenario_section_order.py` 同步（22 模块、7 种可见性类型、action_data 注入）。
- **向后兼容**：`enable_action` 默认关，关闭时「行动建议」章不渲染、「智囊团深度复盘」章与现状一致（无行动摘要子块）。

### 交易纪律（「行动建议」章，轮5 落地）

- **纪律引擎**：新增 `src/python/analysis/trade_discipline.py`，`compute_discipline_signals()` 纯计算（不依赖 report/）——止盈（收益率 ≥ 止盈线，默认 +20%）、止损（收益率 ≤ 止损线，默认 -15%）、回撤（组合相对历史峰值回撤 ≥ 回撤线，默认 10%，需注入 `portfolio_peak_mv`）三类规则，输出「触发 + 距触发幅度 + 建议动作」结构化信号（`code/name/rule/value/status_label/triggered/distance_pct/action`）；缺 `profit_rate`/总市值 0/空持仓安全跳过。
- **静默期复用**：纪律信号复用 `analysis/_silence.py` 静默机制（默认 30 天可配），持久化独立文件 `data/state/discipline_silence.json`（与再平衡静默文件分离，避免信号互相抑制）；同品种触发后 N 天内不重复告警。**静默范围**：仅单品信号（止盈/止损）参与静默；组合级回撤信号 code 为空天然豁免，与再平衡对组合级信号（category/summary）的约定一致——回撤是持续状态，峰值恢复前持续提示更合理（已文档化）。
- **接入**：`action_advisor.build_action_data()` 组装时调用纪律引擎填充 `discipline_signals`（新增可选入参 `discipline_config`/`portfolio_peak_mv`）；both 路径 `_report_generation.py` 向 `build_action_data` 传递完整估值字段（含 `profit_rate/cost/profit`），其中 `profit_rate` 统一换算为**百分数**（小数 ×100，同 full 路径 orchestrator 口径），纪律引擎按百分数阈值比较——此前 both 路径传小数值导致止盈/止损纪律永不触发，已修复并补回归测试。「行动建议」章纪律子块渲染（HTML 表格 + Excel 页签）复用既有字段契约。
- **配置**：config 新增 `discipline` 段（`take_profit_pct`/`stop_loss_pct`/`drawdown_pct`/`silence_days`），`_config_defaults.py` 默认值 + 模板同步，`_validation.py` 新增 `_validate_discipline_config` 校验——含**符号语义约束**：止盈线须为正数、止损线须为负数（符号约束自动保证「止盈线 > 止损线」，杜绝同品种同时触发止盈与止损的误配）。
- **测试**：新增 `src/test/unit/analysis/test_trade_discipline.py`（20 例：止盈触发/线上边界/合规不触发/止损触发/-15% 行为断言/距触发幅度/信号结构/自定义阈值/回撤触发/无峰值跳过/回撤边界/正值回撤配置规则文本归一/静默抑制/静默过期恢复/静默禁用/多品种混合/空持仓/总市值 0/缺 profit_rate 跳过）；`test_action_advisor.py` 改为验证纪律信号经 `build_action_data` 流入；`test_config_validation.py` 新增 `TestValidateDisciplineConfig`（9 例）；`test_orchestrator.py` 新增 both 路径 `profit_rate` 百分数契约回归测试；conftest `_isolate_sensitive_paths` 新增 `trade_discipline._SILENCE_FILE` 隔离。纪律模块覆盖率 100%。
- **回撤数据接线说明**：回撤纪律为可选能力——管线侧 `portfolio_peak_mv` 需组合历史估值数据（当前 orchestrator 未计算），无峰值时安全跳过；接入点已参数化预留，历史峰值注入属后续历史增强范围。

### 调仓建议可行化层（「行动建议」章，轮6 落地）

- **可行化层**：新增 `src/python/analysis/rebalance_advisor.py`，`build_rebalance_advice()` 纯计算（不依赖 report/）——把再平衡/纪律触发信号转成可执行调仓订单，每条含 code/name/operation/shares/amount/fee/cash_after。
- **份额取整（C1 合规）**：复用 `core/code_utils.py`（is_a_share_code / is_exchange_fund_code / is_otc_fund_by_name）判定证券类型——A 股一手 100 股向下取整、场内基金/ETF 一手 100 份、场外基金整数份；不足一手（取整为 0）不生成建议。场外基金判定优先于 A 股（00 代码区间重叠，先经名称关键词排除）。
- **审查修复（rf-214~216）**：`core/code_utils.py` 的 `_OTC_FUND_NAME_KW` 补「债券/指数/股票」关键词（修复 00 前缀债券型基金如 `000311` 误判为 A 股导致漏计赎回费）；`estimate_fee()` 增加卖出方向守卫（未知操作抛 ValueError）；`_round_to_lot`/`estimate_fee` 名称缺失（None）归一化为空串防御。残留建模限制见 rf-217（1 前缀场外持有基金需持仓渠道上下文，当前默认场内口径）。
- **费用估算**：本地静态费率表（佣金万 2.5 最低 5 元 / 印花税 0.05% 仅 A 股卖出 / 赎回费 0.5% 仅场外基金卖出），`estimate_fee()` 导出，费率表可经 `fee_table` 覆盖（测试固定 fixture 断言精度 <0.01 元）。
- **现金缓冲**：从 available_cash 起按执行顺序累计卖出净额（金额 - 费用），任一条执行后现金为负则剔除（现金负值防护）；同品种触发多条（再平衡 + 纪律）时去重保留优先级最高（止损 > 部分止盈 > 卖出减仓）。
- **接入**：`action_advisor.build_action_data()` 在信号计算后调用可行化层填充 `rebalance_advice`；full 路径 orchestrator 的 holdings_details 补充 shares/price（供计算卖出份额，both 路径本就具备）；HTML「行动建议」章调仓建议表格与 Excel 子块补 金额/调仓后现金 两列；附录 H 契约更新。
- **测试**：新增 `src/test/unit/analysis/test_rebalance_advisor.py`（27 例：份额取整一手 5 / 操作生成 3 / 费用估算 7 / 现金缓冲 3 / 优先级去重 2 / 多品种与守卫 7，含债券基金赎回费、港股整数份、名称缺失、未知操作守卫回归）；`test_action_advisor.py` 新增 shares/price 字段与调仓建议流经、摘要计数；`test_action_html.py`/`test_action_sheet.py` 补调仓建议表格行渲染；`test_code_utils.py` 补 `is_otc_fund_by_name` 债券/指数/股票关键词与股票负例。可行化层覆盖率 ≥85%。

### 收益归因（「行动建议」章，轮7 落地）

- **共享纯计算**：新增 `src/python/analysis/return_attribution.py`，`compute_return_attribution()` 单一计算实现（纯本地、零新增外部依赖）——组合收益按品种贡献排序，TOP 5 盈利/亏损来源（贡献占比 pp，非收益率，两者不可混用）、正负分列，每项含 name/code/profit/contribution_pp（全精度浮点，正数盈利 / 负数亏损）；pos_total/neg_total 为全部持仓（非仅 TOP5）正负盈亏合计。无持仓或 Σ|profit|==0 返回 None（渲染层写「待生成」占位）。
- **提示词段落复用（架构遵从，llm → analysis 单向依赖）**：`llm/prompts_core.py::_build_profit_attribution_block` 改为惰性 import `compute_return_attribution` 复用同一计算（与 `_build_rebalance_block` 复用 simple_rebalance 同构），段落输出逐字节一致——「智囊团深度复盘」章 LLM 段落与「行动建议」章表格为同一数据的两处格式化，无重复实现；`prompts_action.py` 既有引用（模块级 import）自动继承。
- **渲染适配层**：`build_return_attribution()` 把共享计算结果塑形为「行动建议」章表格契约（C19 `attribution`：`available/盈利来源/亏损来源/summary`），summary 净额合计摘要分三类文案（混合盈亏「盈利品种合计 +…，亏损品种合计 …（净…）」/ 全部盈利 / 全部亏损）。「行动建议」章 Excel（`report/action_sheet.py` 子块 4）与 HTML（`partials/action_section.html` ④ 区块）渲染适配：贡献占比 `+X.Xpp`、盈亏金额 `+,.2f` 格式化 + 净额合计摘要行（HTML 用 str.format 风格 `{:+.1f}`/`{:+,.2f}`，% 风格不支持千分位逗号）。
- **契约更新**：`action_advisor.build_action_data()` 在持仓可用且总市值 >0 时调用适配层填充 `attribution`（Σ|profit|=0 时 None）；C19 契约 docstring 同步；technical.md 附录 H `action_data` 契约更新 attribution 字段描述（含 return_attribution 实现与降级）。
- **测试**：新增 `src/test/unit/analysis/test_return_attribution.py`（14 例：TOP5 排序/正负分列 3 / 固定 fixture 精度 <0.01% / pos_neg_total 覆盖全部持仓 / 空/零盈亏保护 / 缺省 profit / C19 契约 / 浮点值保留 / 摘要三态 / 不可归因透传 / 提示词段落逐字节一致复用断言 ×2）；`test_action_advisor.py` 更新归因零盈亏保护断言 + 新增有盈有亏填充断言；`test_action_sheet.py`/`test_action_html.py` 归因 fixture 改浮点契约 + 渲染格式/净额摘要断言。`return_attribution.py` 覆盖率 97%（≥85%）。测试用例总数 4,623 → 4,639。
- **向后兼容**：`enable_action` 默认关；开关开启且有盈亏时「行动建议」章归因子块由「待生成」占位升级为真实表格 + 净额摘要，报告结构不变。

### 持仓关系矩阵合并（「持仓关系矩阵」章，轮8「一章两区块」物理合并）

- **章节合并**：原「持仓重合度矩阵」章与「持仓相关性矩阵」章物理合并为「持仓关系矩阵」章——同一章节内**上区块 持仓重合度矩阵**（Jaccard 系数/共同持仓明细）+ **下区块 持仓相关性矩阵**（Pearson r/显著性/下三角热力格），章节可见性 = 重合度或相关性任一区块有数据。
- **统一渲染模块**：新增 `src/python/report/position_relationship_sheet.py`（`write_position_relationship_sheet(ws, overlap_result=None, correlation_data=None)`，内部分 `_write_overlap_block`/`_write_correlation_block` 两区块，任一区块缺失写降级占位）；删除 `fund_overlap_sheet.py`、`correlation_sheet.py` 两个旧页签模块。`fund_overlap.py::compute_overlap_matrix` 重合度计算引擎保留（缓存前缀 `fund_overlap_` 不变）。
- **章节编号重排（22 → 21 模块）**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 收敛为 21 项，`position_relationship`（number=7、data_flag=`position_relationship_data`）替换原 `fund_overlap`/`correlation_analysis` 两个条目，其后各章序号整体 -1（`expert_review` 14→13、`action` 20→19、`data_source_status` 21→20、`llm_usage` 22→21）。章节序号引用全量同步（trade_discipline/return_attribution/action_advisor/data_freshness/holding_status/prompts_core/data_quality_sheet/action_sheet/pipeline_data_builder/orchestrator/excel_generator/html_writer/_report_generation/report_template.html/action_section.html）。
- **C19 契约收敛**：`position_relationship_data`（`available/status/window/sample_count/codes/names/matrix/p_values/pairs/insufficient_codes/note`，11 键）替代 `correlation_data` 在 `pipeline_data_builder.py` 注册/合并，编排层 both/full 路径统一注入；技术文档 data_flag 表、缓存表、C19 契约表同步。
- **模板合并**：`report_template.html` MODULE 7 一章两区块——区块一读 `overlap_matrix`（`_fund_names/_funds/_matrix/_pairs`），区块二读 `position_relationship_data`（None 守卫 `{% set _corr_data = position_relationship_data or {} %}`）；Excel `create_sheets` 经 `board_flags` 同一可见性口径自动产出「持仓关系矩阵」章页签。
- **测试**：`test_registry.py` 新增 `test_old_relationship_sections_removed`（断言旧键移除、position_relationship 注册、21 模块）；`test_correlation_sheet.py` 新增 `TestExcelMergedRelationshipSheet`（4 例：一章两区块同页/仅相关度占位/仅重合度占位/Jaccard 百分比）；`test_correlation_html.py` 新增 `TestHtmlMergedRelationshipSection`（2 例：合并章节双区块/仅重合度时相关性区块占位）；`test_excel_report_structure.py`/`test_html_report_structure_edge.py`/`test_orchestrator.py`/`test_html_writer.py` 页签数/契约键同步。

### 任务编号冲突消解（rf-205~213 重编号为 rf-209~217）

- **背景**：「行动建议」章（轮4~6）开发期间，上游分支（任务编号保障机制）同时合并了已修复条目 rf-204~208（含 fact_checker 数值校验/门禁补强/版本一致性回归）。rebase 落盘后「已提交侧已用 rf-205~208」与「本侧开发用的 rf-205~213」重叠，编号源与已修复表交叉冲突。
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

### 组合历史走势与回撤合并 + 危机区间标注（「组合历史走势与回撤」章，轮9 物理合并）

- **章节合并**：原「组合历史走势」章与「历史回撤分析」章物理合并为「组合历史走势与回撤」章（`portfolio_history_drawdown`）——同一章节分**走势表**（as-if 净值曲线 + 指标汇总矩阵：累计收益/最大回撤/年化波动率/起止日，仅一份，组合 vs 基准对比）+ **回撤矩阵**（独立水下事件明细：起峰日/最深日/恢复日/最大回撤/持续天数/恢复耗时/当前状态）两区块。
- **危机区间标注（新区块）**：新增 `src/python/analysis/crisis_annotation.py`（`build_crisis_annotation(history_data)`，纯标准库、analysis 层隔离），基于 `history_data.bars` 对预设历史危机区间（2015 股灾 / 2018 贸易摩擦 / 2020 疫情 / 2022 调整，`CRISIS_INTERVALS` 静态历史事实表，不随持仓变化、不拉长 lookback、零新增网络请求）做窗口重叠裁剪与区间统计——`in_range`（是否与报告数据窗口重叠）/`interval_drawdown_pct`（区间最大回撤，正数 %）/`trough_date`（最深日）/`recovery_days`（恢复耗时，未恢复 None）/`recovered`；无重叠时显式写「报告数据窗口内无历史危机区间」占位。输出 C19 契约 `crisis_annotation_data`，both 路径在 `report/_report_generation.py` 以 `build_crisis_annotation(history_data)` 注入 pipeline_data。
- **统一渲染模块**：新增 `src/python/report/portfolio_history_drawdown_sheet.py`（`write_portfolio_history_drawdown_sheet(ws, history_data=None, crisis_annotation=None)`，内部分 `_write_trend_block`/`_write_drawdown_block`/`_write_crisis_block` 三区块，任一区块缺数据写降级占位）；删除 `excel_generator.py` 旧 `_write_portfolio_history_sheet`/`_write_drawdown_analysis_sheet` 两个独立写入函数，合并为 `_write_history_sheets` 统一写入。`portfolio_history.py` 计算引擎与 `test_portfolio_history.py` 保留（轮8 持仓关系合并先例）。
- **HTML 合并 + 危机着色（C20）**：`report_template.html` 原 16/17 两模块物理合并为 `sec-portfolio_history_drawdown` 单章节；净值折线图新增危机区间阴影带（Chart.js 侧 `chart_data_builder.py::_compute_crisis_bands` 计算起止索引 → `chart-init.js::buildCrisisBandPlugin` beforeDatasetsDraw 半透明红色带；Canvas 降级路径 `drawSimpleChart` 同款 `crisisBands` 支持）；危机标注净值图**必须 C20 图下说明**（`.chart-caption` 跟随是否有 in_range 区间数据——有→「阴影区间为 2015/2018/2020/2022 主要危机时段」，无→普通文案）。
- **章节编号重排（21 → 20 模块）**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 收敛为 20 项，`portfolio_history_drawdown`（number=16、data_flag=None、type=`history`）替换原 `portfolio_history`/`drawdown_analysis` 两个条目，其后各章序号整体 -1（`portfolio_evolution` 18→17、`action` 19→18、`data_source_status` 20→19、`llm_usage` 21→20）。`_REPORT_SHEET_NAMES` 中文名注册「组合历史走势与回撤」；章节序号引用全量同步（html_writer/excel_generator/orchestrator/_report_generation/chart_data_builder/report_template.html 等）。
- **C19 契约增删**：附录 H 删除旧 `portfolio_history`/`drawdown_analysis` 独立契约（`history_data` 契约保留供合并章复用，消费方更新为合并章），新建 `crisis_annotation_data` 契约（8 键，见 technical.md 附录 H）。
- **测试**：新增 `src/test/unit/analysis/test_crisis_annotation.py`（19 例：数据不可用占位 3 / 2018+2020 区间行为断言 4 / 未恢复 2 / data_end 覆盖与恢复扫描 2 / 无 bar/非正值/非法日期防御 3 / 静态表 1 / 窗口解析与重叠 4，`crisis_annotation.py` 覆盖率 94%）；新增/迁移 `src/test/unit/report/test_drawdown_html_excel.py`（16 例：合并章两区块渲染 / 回撤明细表 / 未恢复占位 / 数据不足占位 / 危机表渲染 / 无重叠占位 / C20 图下说明跟随 / Excel 合并章三区块 + 危机表，`portfolio_history_drawdown_sheet.py` 覆盖率 87%，均 ≥85%）；迁移 `test_excel_report_structure.py`（18 页签）/`test_html_report_structure.py`（16 链接）/`test_excel_generator.py`（8 页签默认顺序 + 旧独立 sheet 不再生成回归断言）/`test_registry.py`（20 模块）/`test_scenario_section_order.py`（history 类型计数 2→1）。轮9 验收「新增测试 ≥8 个、合并断言、行为断言、C20 合规」全部满足。
- **向后兼容**：章节物理合并后，`history_data` 契约与 `enable_history` 开关语义不变（board 层可见性不变）；危机标注仅在 `crisis_annotation_data.available` 且存在 in_range 区间时渲染，数据不可用/无重叠时落占位，既有历史报告结构稳定。

### 尾部风险统计（「组合历史走势与回撤」章，轮10 新区块）

- **计算模块**：新增 `src/python/analysis/tail_risk.py`（`compute_tail_risk(bars)`，纯标准库、analysis 层隔离，无 report/llm 依赖，日志走 logging）。复用 `history_data.bars` 历史日收益序列（与 `report/portfolio_history._compute_daily_returns` 同口径 (curr-prev)/prev，小数单位，不额外拉长 lookback、零新增网络请求），输出 C19 契约 `tail_risk_data`（12 键：`available/sample_size/var95/var99/max_single_day_drop/max_single_day_drop_date/consecutive_down_days/consecutive_down_start/consecutive_down_end/recovery_days_after_drop/recovery_state/warnings`）——VaR(95/99) 历史模拟法（日收益升序取 (1-置信度) 分位损失，正数 %）、最大单日跌幅（% + 日期，无下跌日取 0.0 判状态 none）、最长连续下跌天数（含区间起止日期）、最大单日跌幅后恢复天数（`recovery_state` 分 `recovered`/`unrecovered`/`none`）。样本下限 `MIN_SAMPLE=20`，不足时 available=false 各指标置 None 落 §1.4.5 降级。
- **数据容错**：bars 中 `total_value` 为 0/负/NaN/缺失时相邻收益不成对自动跳过（prev>0 且 curr>0 才构成有效收益），避免伪 -100% 单日；缺失/非法 date 字段日期返回 None 不崩溃；极大（1e12）/极小（1e-4 级）量级计算不溢出不丢精度。
- **全接线**：both 路径 `report/_report_generation.py` 在危机标注注入旁以 `compute_tail_risk((history_data or {}).get("bars"))` 注入 pipeline_data（full 路径 `_prepare_full_risk_metrics` 同步），经 `_generate_full_html_report` → `html_writer.write_html_report` → `_render_html_template` 传入模板；Excel 经 `excel_generator._write_history_sheets` → `portfolio_history_drawdown_sheet.write_portfolio_history_drawdown_sheet` → 新增 `_write_tail_risk_rows`（五行：VaR(95)/VaR(99)/最大单日跌幅/最长连续下跌/最大单日跌幅后恢复，百分比按 FMT_PERCENT 存小数；未恢复写「未恢复」、不可用写「样本不足」占位）。
- **HTML 尾部风险卡（C20）**：`report_template.html` 合并章新增 summary-grid 尾部风险卡组（VaR95/VaR99/最大单日跌幅/最长连续下跌/最大跌幅后恢复，`| change` 格式化百分比），不可用时单卡「样本不足」占位；卡组下方附 C20 说明「尾部风险基于历史日收益序列（历史模拟法 VaR）；恢复天数指自最大单日跌幅日收复跌幅前水平所需交易日」。
- **C19 契约注册**：`tail_risk_data` 在 technical.md 附录 H 注册（12 键契约 + 计算/注入/消费/降级说明）。
- **测试**：新增 `src/test/unit/analysis/test_tail_risk.py`（15 例，`@pytest.mark.unit`+`unit_analysis`：VaR95/99 固定 fixture 精度 <0.01% / 置信度排序 / 无损失日 VaR=0 / 最大单日跌幅值+日期 / 并列最深取首 / 连续下跌天数+区间 / 更长区间优先 / 无下跌 0 天 / 恢复已恢复/未恢复/none 三态 / 样本不足/None/空占位 / 契约字段完整）、`src/test/unit/analysis/test_tail_risk_edge.py`（10 例，`@pytest.mark.edge` 放 `*_edge.py`：0/负/NaN/缺失 total_value 跳过 / 缺失日期容错 / 1e12 量级不溢出 / 1e-4 精度 / 恰 20 available / 19 unavailable / 单点 / 持平序列）、`src/test/unit/report/test_tail_risk_wiring.py`（10 例，`@pytest.mark.unit`+`unit_report`：pipeline 注入充足/不足/None 跳过 / Excel 五行+未恢复+占位 / HTML 卡渲染+未恢复+样本不足占位+C20 说明）。`tail_risk.py` 覆盖率 96%，全部 ≥85%。轮10 验收「新增测试 ≥8 个、固定 fixture 精度 <0.01%、行为断言、C12 边缘合规」全部满足。
- **向后兼容**：`tail_risk_data` 为新增键、`write_portfolio_history_drawdown_sheet`/`write_html_report`/`_render_html_template` 新增参数均带默认值，既有调用与测试不受影响；样本不足时落「样本不足」占位，既有报告结构稳定。

### 自上次快照变化摘要（「组合演进」章顶部，轮11 新区块）

- **计算模块**：新增 `src/python/analysis/snapshot_diff.py`（`build_snapshot_diff(threshold_pct=15.0, min_snapshots=2)`，纯标准库、analysis 层隔离，无 report/llm 依赖，日志走 logging）。复用 `data/history/snapshots/` 多期快照本地数据（零新增网络请求），按日去重（复用 `portfolio_evolution._dedup_by_date`）后取最近两次对比，输出 C19 契约 `snapshot_diff_data`（12 键：`available/snapshot_count/previous_date/current_date/added/removed/hhi_previous/hhi_current/hhi_change/over_limit/summary/reason`）——新增/移除品种按 code 跨账户合并比对（复用 `fetcher/history_diff.HistoryDiff` 引擎），集中度 HHI 变化（本期-上期，市值口径优先、市值为 0 回退成本，与演进同口径，复用 `_compute_hhi`/`_holding_weight`），超 15% 警戒线品种（阈值复用 `analysis/simple_rebalance._THRESHOLD`，按权重降序）。去重后有效快照 < 2 期（无上次快照可对比）时 available=false、reason 说明，落 §1.4.5 降级。
- **全接线**：both/full 路径 `report/_report_generation.py` 新增 `_inject_snapshot_diff_data`，在组合演进注入旁同步注入 pipeline_data（与 `evolution_data` 同开关 `enable_portfolio_evolution`），经 `_generate_full_html_report` → `html_writer.write_html_report` → `_render_html_template` 传入模板；Excel 经 `excel_generator` → `evolution_sheet.write_evolution_sheet` 新增 `snapshot_diff_data` 参数，写入页签顶部「自上次快照变化摘要」区块（新增/移除品种、HHI 变化、超限项逐行）。
- **HTML 摘要卡**：`partials/evolution_section.html` 组合演进章顶部新增「⑤ 自上次快照变化摘要」notice-banner 摘要卡（summary 全文 + 对比区间 previous_date → current_date），数据不足时显示 reason 占位文本。
- **C19 契约注册**：`snapshot_diff_data` 在 technical.md 附录 H 注册（12 键契约 + 计算/注入/消费/降级说明）。
- **测试**：新增 `src/test/unit/analysis/test_snapshot_diff.py`（8 例，`@pytest.mark.unit`+`unit_analysis`：无上次快照占位 / 新增移除检测 / HHI 变化 / 超限项降序 / 相同快照持平 / summary 覆盖全部变化点 / 市值 0 成本回退 / 同日去重保留最后）、`src/test/unit/analysis/test_snapshot_diff_edge.py`（6 例，`@pytest.mark.edge` 放 `*_edge.py`：空目录 / 空持仓 / 全 0 权重防除零 / 阈值 0 全超限 / 损坏文件跳过 / 多账户聚合）。`snapshot_diff.py` 覆盖率 100%，全部 ≥85%。轮11 验收「新增测试 ≥6 个、行为断言、无上次快照占位、C12 边缘合规」全部满足。
- **向后兼容**：`snapshot_diff_data` 为新增键、`write_html_report`/`_render_html_template`/`write_evolution_sheet`/`_generate_full_html_report` 新增参数均带默认值，既有调用与测试不受影响；无上次快照时落占位，既有报告结构稳定。

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
