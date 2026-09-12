# 变更日志归档 — v0.10.x

> 归档时间：2026-08-06；2026-08-16 二次合并 changelog.md [0.10.9] ~ [0.10.13] 已发布版本变更记录；2026-09-12 三次合并 changelog.md [0.10.14] ~ [0.10.18] 已发布版本变更记录
> 原始文件：`docs-stm/managements/changelog.md`
> 涵盖版本：v0.10.1 ~ v0.10.18（2026-08-04 ~ 2026-09-12；v0.10.0 无独立 changelog 段）
> 归档内容：v0.10.x 已发布版本变更记录（仍处开发版本 [0.10.19-dev] 保留在原文件 changelog.md）

---

## [0.10.4] - 2026-08-05

### 技术债收尾（LLM 死代码删除 + fact_checker 组合级收益误配 + 匿名化模块补测试）

- **LLM 死代码删除**：删除 `llm/_call_claude.py`/`_call_gemini.py`/`_call_openai.py`/`_thinking.py` 四个孤儿模块（外部零引用，LLM 调用统一走 `_api_claude`/`_api_openai`/`_api_gemini` 活动路径），净删 378 行，`llm/__init__.py` 导出同步清理。
- **fact_checker 组合级收益误配修复**：`_evaluate_percent_value` 对「组合累计收益10%，招商银行上涨8%，贵州茅台上涨15%」同句段，组合收益数值被整句主体定位误路由到数值最近的个股（招商银行 8.2%），报假阳性。新增组合级语境检测 `_is_portfolio_level_context`（`_PORTFOLIO_KEYWORDS` 词表，match 前 15 字符窗口），在主体定位前判定组合级收益并归到组合总收益率。新增 2 例专项回归（`test_portfolio_level_plus_stock_level_same_sentence` 组合级路由通过 / `test_portfolio_level_mismatch_attributed_to_portfolio` 组合级错误归因到组合总收益率而非个股）；`test_fact_checker.py` 95 例、`test_llm_hallucination.py` 17 例全过。
- **匿名化模块补测试**：`config/anonymizer.py` 原 0% 覆盖 → 新增 `src/test/unit/config/test_anonymizer.py` 33 例、覆盖率 99%。覆盖 4 种模式（off/code_display/full_anonymous/summary）× 持仓列表与明细字典、未知模式回退 off、`get/set_anonymization_mode` 配置读写（含无效模式抛 ValueError）、`_num_to_label`/`_blur_value`/`_categorize_*` 辅助函数、`code_utils` 导入失败前缀回退。唯一未覆盖为 `_blur_shares` 中不可达的 `<100` 防御分支（`round(x/100)*100` 值域仅 {0} ∪ [100,∞)，无法命中）。
- **门禁**：P0 dev-verify 1694 passed + 3 check（code-traces/doc-traces/task-numbering）全 [OK]。

### 重构期历史兼容负担清理（移除旧配置键迁移 / import 再导出 / LLM 内嵌凭据自动改写）

- **配置键迁移移除**：`_core.get_config()` 不再做 `history.analysis`→`history.fetch_mode` 惰性迁移（旧键直接忽略，回落到默认 `fetch_mode=auto`）；`config/_local_state.py` 移除 `_migrate_legacy_keys` 旧键搬移（`_startup_wizard_shown`/`_privacy_notice_shown` 只在本机 `local_state.json` 读写，不做 config.json 迁移）；`anonymizer.py` 移除匿名化模式废弃别名映射（未知模式回退 `off`）。
- **import 再导出移除**：`config/_core.py` 不再再导出 `_llm_providers`/`_llm_settings` 符号；`report/orchestrator.py` 移除对 `_snapshot`/`_llm_news`/`_report_generation` 的 bridge 转发 import——消费方改从源模块直接导入。
- **LLM 内嵌 api_key 行为修正**：`_parse_providers_list` 不再把 `_inline_api_key`/`_inline_model`/`_inline_credentials_ref` 自动注入 `_llm_credentials`；内嵌 `api_key`/`model` 直接保留在 entry 中，由 `api.py:_resolve_entry_credentials` 运行时内联回退读取（宽容行为保留，仅移除自动改写）。
- **缓存 schema 版本递增**：`cache/_paths.py` `_CACHE_KEY_VERSION` v2→v3，旧缓存文件自然失效重建。
- **向后兼容措辞清理**：`report/` 多模块（data_quality_sheet / fund_candidate / category / market_value_sheet / excel_generator）与 `_config_defaults` 中"向后兼容"措辞改为描述当前行为；`tui/handlers_config.py`、`llm/generators.py`、`llm/prompts_action.py` 同步清理旧名注释。
- **文档同步**：technical.md（local_state 迁移描述移除、config.json 解析职责三处去迁移、主矩阵写入方去 `_local_state`）、requirements.md（跨机器同步段去迁移）、folders.md（`_local_state.py`/`test_local_state.py` 描述去旧键迁移）、how-to-config.md（机器本地状态段去兼容迁移说明）；llm-technical.md 内联凭据运行时回退描述保持不变（合法行为）；data/config/config.json 由模板程序重新生成（同步 `enable_fund_deep_analysis` 新注释 + 补齐 `report_submodules` 5 个子键与 `comparison_candidates`）。
- **测试**：`test_config.py` 迁移用例改断言忽略旧键回落默认；`test_local_state.py` 删 TestLegacyMigration 类；`test_config_llm_multi*.py`/`test_integration_multi.py`/`test_debate_*.py`/`test_config_validation.py` patch 目标改到 `_llm_settings`/`_llm_providers` 源模块；`test_orchestrator.py`/`test_pipeline_smoke.py` 导入改源模块；`test_cache_core.py`/`test_cache_cleanup.py` 断言 v3 缓存文件名。

### HTML 报告目录分组导航折叠 + 文档快照同步（plan-24 轮19/轮20，导航收尾）

- **分组导航（轮19）**：HTML 报告左侧目录按「基础/基金深度/风险/历史/LLM」五组折叠导航，原生 `<details>/<summary>`（键盘可达、无需 JS）。`html_writer.py` 新增 `_NAV_GROUP_LABELS`（五组顺序）/`_SECTION_NAV_GROUP_MAP`（19 章节→组归属）/`_build_section_nav_groups()`（仅收录可见章节、组序固定、组内按报告序号升序、空组保留由模板跳过）；`_render_template` 计算并注入 `section_groups` 到模板。`report_template.html` 目录改为分组结构（`.toc-group` details + 组标题徽标计数 `.toc-group-count`），空组不渲染；窄屏扁平 `section-nav` 保留作移动端兜底，两种导航均不依赖 JS。
- **测试**：`test_html_report_structure.py` 新增 `TestHtmlTocGroupedNav`（11 例：五组分组渲染/组内章节正确/标题+徽标数/空组跳过/真实 registry 映射含 action·evolution·data_source_status/折叠原生交互/键盘可达/窄屏不溢出），`_render_template` helper 同步注入 `section_groups`（与生产一致）；原 TOC 顺序测试改为分组序断言。dev-verify 1694 passed + 3 check 全 [OK]。
- **文档快照（轮20）**：folders.md 统计表（主程序 225/55,697、HTML 4/3,756、脚本 16/5,581、源代码合计 245/65,034、测试代码 275/78,856、测试用例 5,009）；test-coverage.md 模式/功能域/unit 子分组按 `collect-test-coverage.py` 实时值刷新（all 5009、unit 4691、report 1475、unit_report 1475、unit_analysis 580、unit_providers 199、edge 566 等）；how-to-config.md 补 `report_submodules.valuation_percentile`/`market_temperature` 开关行 + `report_section_order` 19 项核对（示例键 `fund_style`→`style_factor`）；reports-instruction.md HTML 目录五组折叠说明 + 「页面/章节分组」序号全面核对（19 个页签；数据源可用性矩阵 18、llm_usage 19、风格与因子 9 等）；registry.py docstring「20 项」→「19 项」；faq.md / how-to-config.md「20 项默认顺序」→「19 项」。datasource*.md 已覆盖 push2 PE/PB 扩展字段与指数 K 线通道，无需变更。

### 估值分位 + 市场温度（plan-23 轮17/轮18，`valuation_data`/`market_temperature_data` 契约）

- **估值分位（轮17）**：新增 `src/python/analysis/valuation_percentile.py`（纯计算层）——`extract_closes()` 收盘价提取（股票 `close` 优先、场外基金回退 `nav`，过滤 None/NaN）、`price_percentile()` 价格分位（0~100，`MIN_SAMPLES=60` 样本下限）、`compute_price_percentile()` 分位+三档刻度（低估/合理/高估）契约、`DISCLAIMER`（"价格分位代理，非真实历史估值分位"）；`providers/eastmoney_industry.py` push2 扩展字段 `fetch_valuation_fields()`（PE/PB，复用既有 push2 请求通道 + 会话缓存）。「资产穿透TOP10」章追加「估值分位」列（Excel `penetration_sheet` ncols 10→11 + 表尾免责声明；HTML `report_template.html` 条件列），开关 `report_submodules.valuation_percentile` **默认关**（关闭时列隐藏、输出与改造前一致）。
- **市场温度（轮18）**：新增 `src/python/analysis/market_temperature.py`（纯计算层）——`ma_deviation()` 均线偏离（小数比例）、`returns_volatility()` 年化波动率（√252 年化）、`temperature_score()` 三因子合成（0.5×分位 + 0.3×均线偏离分量 + 0.2×波动率分量，各分量 clamp 0~100）、`compute_temperature()` 温度契约（`MA_DEVIATION_SPAN=±20%`、`VOLATILITY_SPAN=50%` 映射区间）；**温度计只给刻度、无仓位指令**（`TEMPERATURE_DISCLAIMER` 渲染层必须展示）。「投资分析汇总」章「市场指数」后追加「市场温度」刻度行（Excel `summary._write_market_temperature`；HTML kv-table），三因子行展示转百分数（`dev/vol ×100`，分位已为 0~100）。开关 `report_submodules.market_temperature` **默认关**（与 `cost_lots` 同章不同行、开关独立互不影响）。
- **编排与契约**：`orchestrator.py` 新增 `compute_valuation_data()`（A 股去重 → ThreadPoolExecutor 并行 `_fetch_valuation_for_code`：push2 PE/PB + 历史 K 线价格分位，PE/PB 与分位任一可得即计入）、`compute_market_temperature_data()`（`fetch_index_history` 沪深300 → `compute_temperature`，指数 K 线不足 `insufficient` 占位）；`prepare_report_data` 注入 `valuation_data`/`market_temperature_data` 键；`pipeline_data_builder.py` 注册两键（已知键 + 类型映射，None 允许）；`_report_generation.py` both/full 路径透传；`excel_generator`/`excel_content_sheets`/`html_writer` 同步接线（`_build_temperature_display`/`_attach_valuation_to_penetration` 不可变展示映射）。
- **测试**：新增 `src/test/unit/analysis/test_valuation_percentile.py`（16 例：收盘价提取/分位解析解/三档刻度/数据不足/局限标注）、`test_valuation_percentile_edge.py`（边缘）、`src/test/unit/analysis/test_market_temperature.py`（17 例：均线偏离/波动率/三因子合成/刻度映射/免责声明/数据不足）、`test_market_temperature_edge.py`（边缘）；报告层接线 `src/test/unit/report/test_valuation_temperature_wiring.py`（24 例：HTML 展示构建器/穿透估值列文本/汇总温度行/编排开关降级与契约）；`test_orchestrator.py` 期望键补 `valuation_data`/`market_temperature_data`；修复温度展示小数比例转百分数 bug（`dev/vol ×100`）。dev-verify 1694 passed + 3 check 全 [OK]。
- **文档同步**：plan.md（plan-23 轮17~18 已完成）、plan-investment-iteration.md（轮17/轮18 验收）、technical.md（附录 H 两契约行 + 数据契约键记录）、folders.md 目录树（analysis 两模块 + 5 个新测试文件）。

## [0.10.3] - 2026-08-05

### 风格与因子分析合并章 + 行业 Beta 子表（plan-21 轮12，章节数 20→19）

- **物理合并**：合并原「基金风格分析」（`fund_style_sheet.py`）+「因子暴露分析」（`factor_exposure_sheet.py`）→ 统一渲染模块 `src/python/report/style_factor_sheet.py`，章节 sheet key 统一为 `style_factor`，一章三区块渲染：区块一基金风格表（8 列）+ 区块二风格因子回归（5 列 + 基准对照）+ 区块三行业 Beta 子表（7 列，`industry_beta=None` 隐藏 / `available=False` 占位）；删除旧两个渲染模块，`core/registry.py` `_REPORT_SECTION_DEFAULT` 的 `fund_style`/`factor_exposure` 合并为 `style_factor`（number 9），registry.number 连续编号重新整理 20→19，`data_source_status`=18、`llm_usage`=19。
- **行业 Beta 子表**：新增 `src/python/analysis/industry_beta.py`，`compute_industry_beta_analysis()` 复用 `factor_exposure.py::compute_factor_exposure` 单因子 OLS（不重复实现），行业穿透分类复用 `batch_fetch_industry_data`（`industry_` 前缀缓存，代码类型判定中心化 复用 `core/code_utils.py` 判定）；`INDUSTRY_INDEX_MAP` 映射 12 个中证行业指数（银行=sh000986、证券=sz399975、白酒/食品饮料=sz399997、半导体/电子=sz399995、有色/贵金属=sz399996、煤炭=sz399998、医药=sz399989、钢铁=sz399994、房地产=sh000980、能源=sh000928、环保=sz399973、保险=sz399983）；指数 K 线复用 `history_index` 通道（Chain + session_cache，会话级API复用/Provider Chain 必经）；开关 `report_submodules.industry_beta` **默认关**。
- **数据契约增删**：`pipeline_data_builder.py` 删除 `factor_exposure` 旧注册，新增 `style_factor_data` 主键（13 键：available/summary/style_table/factor_regressions/benchmark/industry_beta 等）+ 内嵌 `industry_beta` 子键（7 键：available/exposure/index_codes/betas/t_stats/significant/correlations/unmapped_industries）；`orchestrator.py` 新增 `compute_industry_beta_data()` 并在 full/both 路径注入 `style_factor_data`（含 `industry_beta` 组装）；附录 H 契约类型/版本/写入消费模块同步预定义。
- **双层可见性**：board 层 `enable_fund_deep_analysis` + data 层 `style_factor_data`；可见性 = `style_factor_data is not None or style_analysis is not None`，旧 `factor_exposure_data` 数据 flag 一并迁移。
- **HTML/Excel 同步**：`report_template.html` 合并 section 号 9（区块标题 `.block-title` CSS + 行业 Beta 区块渲染分支）、`excel_generator.py`/`excel_fund_deep_analysis.py`/`excel_module_loader.py`/`html_writer.py`/`_report_generation.py` 同步 `style_factor`/`style_factor_data` 接线。
- **测试**：新增 `src/test/unit/analysis/test_industry_beta.py`（11 例：行业暴露占比 / Beta 回归 / 显著性 / 数据不足 / 开关关隐藏 / push2 行业分类降级占位 / 固定 fixture 解析解误差 <0.01）、`src/test/unit/report/test_style_factor_sheet.py`（合并章三区块渲染 / 行业 Beta 三态 / 可见性）；旧 `fund_style`/`factor_exposure` 测试迁移适配；`test_orchestrator.py`/`test_html_report_structure*.py`/`test_registry.py`/`test_config*.py`/`test_scenario_section_order.py` 同步（键 `factor_exposure`→`style_factor_data`、19 个章节、7 种可见性类型）。新增模块覆盖率：industry_beta 94% / style_factor_sheet 97%。
- **文档同步**：technical.md（模块数 20→19、data_flag 表、§4.8 一章三区块、附录 H 契约）、requirements.md（§6.3/6.4 章节合并重编号）、全部用户手册（how-to-menu / how-to-config / how-to-use-registry / reports-instruction / faq / datasource）、test-coverage.md（模式计数 + 功能域 + unit 子分组）、folders.md 目录树。

### 基金业绩分析章候选基金比较增强模式（plan-21 轮13，`candidate_compare` 默认关）

- **核心模块**：新增 `src/python/report/fund_candidate.py`——`resolve_candidates()`（6 位代码校验 / 去重 / 超 10 截断 + `exceed_limit` 标记）、`build_candidate_compare_data()`（开关门控 → 无有效候选降级 → 正常）、`_build_candidate_row()`（收益近1月/3月/6月/1年 + 同类排名 + 评级 + 最大回撤 + 风格 + 与现有持仓重合度，单候选失败 `available=False` 短路不阻塞其余）。比较维度不含规模/费率（无数据源，已验证）；重合度复用 `fund_overlap.compute_overlap_matrix`（Jaccard），风格复用 `fund_style_classify.classify_fund_style`（复用中心化分类）；`risk_analysis` 最大回撤百分数数值 `/100.0` 归一化为小数与 `syl_*_raw` 口径一致（Excel FMT_PERCENT 直接可用）。
- **配置层**：`report_submodules.candidate_compare` **默认关**（关闭时 `build_candidate_compare_data` 返回 None，基金业绩分析章输出与改造前一致）+ 顶层 `comparison_candidates`（6 位基金代码列表 ≤10）；`_core.py` 新增访问器 `is_enable_candidate_compare` / `get_comparison_candidates`（镜像既有 data_quality 模式，非 list/str/int 数值归一化容错）；`_validation.py` 新增 `_validate_comparison_candidates`（非列表 / 非法项 / >10 告警，数值项允许）。
- **Excel 渲染**：`fund_performance.py` 末尾（数据状态脚注后、冻结/列宽前）条件渲染候选比较子表 `_write_candidate_compare_block`（11 列：候选基金/代码/评级/近1月/近3月/近6月/近1年/同类排名/最大回撤/风格/与持仓重合），可用行百分比列 FMT_PERCENT，失败行"获取失败"占位，`exceed_limit`/`invalid` 各写提示行。
- **HTML 渲染**：`html_renderers._render_fund_performance_section` 返回 `(perf_data, candidate_data)`，`html_writer` 传入模板；`report_template.html` 基金业绩分析章主业绩表后新增候选比较区块（`.block-title`「候选基金比较（候选来自 config.comparison_candidates）」+ 11 列表格 + 失败占位行 + 超限/无效脚注），`candidate_data` 不可用时整块不输出（行为断言）。
- **测试**：新增 `src/test/unit/report/test_fund_candidate.py`（23 例：候选校验/截断/开关门控/全维度行/单候选失败降级/CLI 合并/缺期间非法值/风格与重合度失败降级/现有持仓收集），`test_html_writer.py` 新增 `TestCandidateCompareTemplate`（7 例，从真实模板配平截取候选区块渲染，断言开关关无子表、开启 11 列正确、失败占位、超限/无效脚注），`test_config.py`/`test_config_validation.py` 新增候选配置访问器与校验测试。fund_candidate 覆盖率 99%。
- **文档同步**：plan.md（plan-21 轮13 已完成）、plan-investment-iteration.md（轮13 验收签字）、how-to-config.md（开关 + 候选列表说明）、reports-instruction.md（基金业绩分析比较子表说明）、folders.md 目录树补 `fund_candidate.py`/`test_fund_candidate.py`。

### 成本流水：持仓文件格式扩展 + 资金加权收益与成本分档 + 三页签渲染（plan-22 轮14/轮15/轮16，`fund_flow_data` 契约）

- **持仓文件格式扩展（轮14）**：持仓 Excel 可选新增「交易流水」「分红流水」页签，不破坏既有固定 4 列格式（名称/代码/持仓份额/每份成本）。`core/models.py` 新增 `TradeRecord`（日期/代码/操作/份额/价格/费用，费用可选缺省 0）与 `DividendRecord`（日期/代码/每份分红）；`core/reader.py` 新增 `read_flow_sheets()` / `read_holdings_with_flows()` 与 `_parse_trade_sheet()` / `_parse_dividend_sheet()`（表头不匹配整体跳过 + 行级无效容忍：日期/操作/数值无效仅跳过该行并告警；`parse_workbook` 主体零改动，向后兼容）。`test_reader.py` 新增 `TestParseFlowSheets`（20 例：交易/分红解析、表头不匹配、无效行容忍、费用可选、操作归一化、多账户、向后兼容字段相等），共 80 例、覆盖率 93%。
- **资金加权收益（XIRR，轮15）**：新增 `src/python/analysis/cost_flow.py`（纯计算层，禁止导入 report/）——`solve_xirr()`（Newton-Raphson + 二分兜底，自然日年化 `t=days/365`，扫描区间 -99.99%~+1600%）、`build_xirr_cashflows()`（投资者视角现金流：买入为负 / 卖出与分红到账为正 / 期末市值为正，分红按登记日份额纳入时点效应，份额未知回退当前持仓）；固定 fixture 解析解年化误差 0.0000%（定投与整笔两类 10% 年化案例）。
- **成本分档 + 分红累计（轮15）**：`build_cost_lots()`（交易流水按代码 FIFO 合并成本批次，批次成本 = 价格 + 费用均摊）、`compute_cost_tiers()`（相对当前市价分低成本/高成本档 + 无市价品种单列，`high_cost_ratio` 支持「是否追高加仓」判断）、`compute_dividend_totals()`（按代码汇总分红金额）。
- **数据契约预定义（轮15）**：`build_fund_flow_data()` 输出 `fund_flow_data` 契约（available/xirr/cost_tiers/dividends）。
- **三页签渲染（轮16）**：开关 `report_submodules.cost_lots`（默认关，`is_enable_cost_lots()` 访问器，镜像 candidate_compare 模式）贯穿 CLI/TUI → `generate_report(transactions=…, dividends=…)` → `excel_market_data.resolve_market_data` 组装 `fund_flow_data` 注入 data dict（`pipeline_data_builder.py` 注册 + technical.md 附录 H）——「持仓分类表」加「成本分档」「分红累计」子列（category.py）、「市值核算明细表」加可选「资金加权成本」列（market_value_sheet.py）、「投资分析汇总」加「资金加权收益率 (XIRR)」汇总行（summary.py，无流水写「未录入流水」占位）；CLI `_cli_read_holdings_with_flows()` / TUI `prepare_holdings()` 接线透传；新增测试 32 个（summary 3 + category 6 + market_value_sheet 8 + config 5 + cli 5 + excel_market_data 5，远超 ≥8），受影响套件 267 passed。
- **测试**：新增 `src/test/unit/analysis/test_cost_flow.py`（24 例：XIRR 精度 / guess 无关性 / 空值与同日退化、FIFO 批次、成本分档边界、分红累计，pytestmark unit/unit_analysis），覆盖率 94%。

### 成本流水 HTML 渲染补齐（plan-22 轮16 补遗，`fund_flow_data` 三处 HTML 渲染）

- **HTML 接线**：`html_writer.py` 的 `write_html_report()` / `_render_template()` 新增 `fund_flow_data` 参数，并新增 `_build_flow_display()` 将成本流水数据转为模板友好展示映射（复用 `market_value_sheet._weighted_avg_cost` 资金加权成本 + `category._tier_label` 分档标签计算逻辑，避免双实现）；`_report_generation.py` 两条路径（`_generate_report_both` / `_generate_report_full`）复用 `excel_market_data._build_flow_data` 组装成本流水数据并透传 HTML 渲染（Excel 侧仍按原路径内部组装，无重复计算）。
- **模板三处渲染**（`report_template.html`，`flow_display` 不可用时整体不输出，与开关关闭行为一致）：
  - 「投资分析汇总」盈亏汇总卡组新增「资金加权收益率 (XIRR)」卡（`xirr_rate` 经 pct 过滤器 ×100 加 %，profit_color 着色；无可用现金流不渲染）
  - 「市值核算明细表」追加可选「资金加权成本」列（批次加权成本价按 price 过滤器，缺码 `--`，小计/总计列留空）
  - 「持仓分类表」追加可选「成本分档」「分红累计」子列（分档标签复用 `_tier_label`、分红累计按 `money` 金额渲染，缺码 `--`/0.00）
- **测试**：`test_html_writer.py` 新增 `TestFundFlowTemplate`（9 例，从真实模板配平截取三处条件区块渲染，断言开关关不渲染 / 开启正确输出 / 缺码占位）+ `TestBuildFlowDisplay`（3 例，展示映射组装 / 契约键缺失降级）；修复 `test_orchestrator.py::test_generate_report_basic` 断言的 `enable_cost_lots`/`transactions`/`dividends` 参数透传（轮16 遗漏同步）。受影响套件 test_html_writer 74 passed、test_orchestrator 45 passed。

### 语义命名与章节/轮次引用清理（语义命名审计，2026-08-04）

- **章节编号暗号全面清理**（rf-218/rf-219）：源码与测试注释、docstring、fixture 中 `N 章`/`第 N 章`/`报告第 N 页` 一律改为纯语义章节名；`test_excel_report_structure.py`/`test_action_html.py` fixture 编号对齐当前 registry（style_factor=9、action=17、expert_review=12、global_macro=11、data_source_status=18、llm_usage=19），页签计数断言同步（全部启用 17 个、always+基金深度 10 个）。
- **check-code-traces 增强——章节编号检测（CHAPTER）**：镜像 check-doc-traces 的 CHAPTER 模式（`N 章`/`第 N 章` 指代报告章节须改用语义名）+ 计数/序数豁免（共 N 章、减至 N 章、N→M 章、「N 章」、出现第 N 章），退出码归入任务编号类（exit 2）。
- **check-code-traces 增强——迭代轮次检测（ROUND）**（rf-220）：新增 ROUND 模式检出 `第 N 轮`/`N 轮`/`轮N` 迭代轮次痕迹，计数/运行时表述豁免（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/轮换、第 N 轮循环）；测试层残留轮次引用（`test_html_writer.py` 候选比较 docstring）改为语义描述；退出码归入任务编号类（exit 2）。
- **check-doc-traces 增强——迭代轮次检测（ROUND，空格分隔形式）**（rf-221）：check-doc-traces 镜像 ROUND 模式（`第 N 轮`/`经 N 轮`/`N 轮`/`轮 N`，含空格分隔）+ 计数/运行时豁免（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/轮换/轮番/轮涨/轮跌、第 N 轮循环），ROUND 不进 trace-exempt 文档扫描（changelog/plan/review-findings + docs-stm/plan/ 仅章节编号检查，`轮 N` 是其正式记录载体）；check-code-traces ROUND 放宽 `轮N` → `轮\s*N`（空格分隔）；清理 4 处空格分隔旧注释（industry_beta / excel_fund_deep_analysis / orchestrator / test_return_attribution）改为语义描述；`test_trace_check_scripts.py` 新增 `TestDocRoundDetection` 4 例。
- **契约改名叙述清理 + 两脚本补「原 X 迁移」模式**（rf-222）：注释残留「原 factor_exposure 契约迁移为主键」等历史契约改名叙述（7 处 src 注释 + 1 处 scenario 测试）——现有模式只覆盖「原+固定名词 / 迁移自 / 迁移到新X」，漏检「原+标识符+迁移为/为主键」形状；8 处全部改为纯语义描述（style_factor_data 主键）；check-code-traces 与 check-doc-traces 同步新增 HIGH 模式「原 X…迁移/改称/并入」（ASCII 标识符 + 契约/dict/数据契约 限定词，「原始数据迁移」等中文后续不误伤）；`test_trace_check_scripts.py` 新增代码/文档各 1 例契约改名叙述检出测试；全仓两检查脚本 `--ci` 干净。
- **check-code-traces / check-doc-traces 增强——中文数字章节/轮次 + 物理合并痕迹**：两脚本 CHAPTER 新增中文数字检测——「第 X 章」式（X 为中文数字 1~20）与裸「X 章」式（X 为中文数字二~十，唯「一」为计数语义如"一章三区块"不纳入裸模式）；ROUND 新增中文数字检测——「第 X 轮」式（X 为中文数字三~十，唯「一/二」为 LLM 圆桌会两轮辩论等运行时序数不纳入）与「轮 X」式；同步补齐 `_chapter_excludes()`/`_round_excludes()` 中文数字计数豁免（共 X 章/减至 X 章/共 X 轮/计划分 X 轮等）；CHANGE/HIGH 新增「物理合并」痕迹检测（模块/章节合并历史，类似迁移）；两脚本自豁免 `_is_tool_self()`（`check-*.traces.py` 整文件跳过自身，防止新增强模式特征字面量检出自身体）；清理 6 处源码注释 + 2 处 requirements.md 物理合并叙述 + changelog 残留的中文数字章节字样为语义描述（registry / style_factor_sheet / portfolio_history_drawdown_sheet / test_registry / test_excel_generator）；`test_trace_check_scripts.py` 新增中文数字章节/轮次检出与豁免、物理合并检出、工具自身文件豁免测试，77 例全过；全仓两检查脚本 `--ci` 干净。
- **测试**：`test_trace_check_scripts.py` 新增 `TestCodeChapterDetection`（镜像 doc 版本）、`TestCodeRoundDetection`（轮次暗号检出 / 计数豁免 / 运行时豁免 / 合法表述不误伤）与契约改名叙述检出（代码/文档各 1 例），66 例全过；全仓 check-code-traces / check-doc-traces `--ci` 干净。

### 架构约束暗号清理收尾 + check-code-traces 增强 3 类暗号匹配（task #110/#111，2026-08-04）

- **check-code-traces 增强——3 类暗号模式**：新增/强化三类「字母+数字/字母-数字/字母_数字」暗号匹配（用户中断指令）：
  - **MAGIC（字母+数字/连续字母+数字，如 D8/HH6）**：注释中裸「大写字母(+小写)+数字」魔法编号须用语义名替代；`_magic_excludes()` 行豁免覆盖合法领域值——conftest 官方活分类法（S1~S33/T1~T21/Y1~Y6/Z1）、穿透场景标签（S-P1~S-P10）、TOP\d+、linter 码（F401 等）、VaR/MD5/SHA/AES、季度 Q1~Q4、DeepSeek V\d、Excel 单元格/范围（A1:B1）、微信 X5、ETF/主动/基金 基金标签；`_is_magic_match_excluded()` 逐 token 豁免（同一行合法场景标记与暗号并存时只豁免合法 token，暗号仍检出）。
  - **DASHTASK（字母-数字/连续字母-数字，如 F-1/G-1/TASK-22）**：疑似任务编号；`_dash_excludes()` 豁免交易日（T-1）、小写下标/编码/模型名（i-1/utf-8/sonnet-4）、N-2 计数、需求 ID 交叉引用（`R-LLM-DB-QA-CONCENTRATION-03/04`，requirements.md 定义）。
  - **UNDERSCORE（字母_数字/连续字母_数字，如 F_1/H_1/MINE_22）**：疑似无意义代码；`_under_excludes()` 豁免小写语义短名（changed_1m/syl_1y）。
- **注释提取重写——tokenize+AST**：`_py_comment_lines()` 从行级三引号启发式改为 tokenize 提取 `#` 注释 token + AST 定位真实 docstring（Module/ClassDef/FunctionDef body[0] Expr→Constant str），彻底修复两处 docstring 状态泄漏（字符串字面量结尾 `"""` 误判、裸 `"""` 关闭行卡死 in_docstring 状态导致后续代码行被当注释扫描）。MAGIC 检出由 479 → 130（真暗号净剩）。
- **真暗号清理**：全仓 20 处测试描述真暗号（R11/R21/R9/TD8/D-6/D-7a/D-7b/D-8/C-P2/A1/A6）替换为语义描述；契约键集常量改语义名 `_CONTRACT_KEYS` 修复双下划线名称混淆（rf-225）；架构约束代号注释全面改语义描述（延续 task #110，~108 文件）。
- **批量替换脚本缺陷修复（rf-223/rf-224）**：会话内一次性脚本（/tmp/clean_ciphers.py）折叠整行空白破坏 9 个 Python 文件前导缩进、截断需求 ID、删段头序号——已按 HEAD 逐行映射恢复缩进（全仓 compile 通过），需求 ID 恢复并纳入豁免，`I2.`/`── ──` 改语义。
- **测试**：`test_trace_check_scripts.py` 新增 `test_magic_number_letter_digit_flagged`（8 例：P1/C21/AB14/MC19/D8/HH6 等魔法编号与约束代号检出）、`test_dashtask_letter_digit_flagged`（6 例）+ `test_dashtask_legit_not_flagged`（5 例：T-1/i-1/utf-8/N-2 项/R-LLM-DB-QA 需求 ID 豁免）、`test_underscore_letter_digit_flagged`（3 例）+ `test_underscore_legit_not_flagged`（2 例）；`_code_hit` helper 补齐 DASHTASK/UNDERSCORE/MAGIC 豁免逻辑与 scan_file 一致；删除已废弃的 `_is_triple_quote_line` 测试；88 例全过。
- **门禁验证**：P0 门禁 `dev-verify` 1649 全过（Phase A 单元 1501 + Phase B 场景 146，含全部 analysis/report/config 相关）；`check-code-traces.py --ci`、`check-doc-traces.py --ci`、`check-task-numbering.py --ci` 三脚本全部 [OK]（exit 0）。

### 设计文档微调（plan-investment-iteration.md，task #109，2026-08-05）

- **轮17 补复用说明**：估值分位模块实施内容与验收标准补「复用既有 push2 请求通道」（`providers/eastmoney_industry.py::make_push2_request`，行业分类在用，不重复实现），并补「复用既有 push2 请求通道断言」测试项。
- **轮18 补双开关叠加说明**：市场温度模块实施内容补「双开关叠加说明」——「投资分析汇总」章成本流水资金加权收益（XIRR）汇总行（`cost_lots` 开关）与本温度刻度行（`market_temperature` 开关）同章不同行、开关独立互不影响，开启其一不改变另一行渲染，测试须断言两开关各自独立生效。
- **轮21 措辞与格式修正**：约束正文复核措辞改「19 模块」（registry.number 连续编号 1~19）；修复「附录 H数据契约」缺空格（→「附录 H 数据契约」）。
- **§4.1 依赖表补链**：新增「轮 19 → 轮 20 → 轮 21」（结构→快照→发布）依赖行（分组导航结构稳定是文档快照/手册前置，数据快照与版本一致是发布门禁前置）。

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

- **轮1 品种覆盖诊断**：新增 `src/python/core/holding_status.py`，`build_coverage_summary()` 逐品种判定数据状态（本地信号：代码格式/名称比对；数据信号：行情/净值可用性），按优先级 代码格式 > 数据缺失 > 名称不匹配 > 有行情，输出数据契约 `position_status`（`available/items/abnormal_count/summary`，items 含 code/name/account/status/status_label/reason，status 取值 ok/nav_missing/possibly_delisted/bad_code_format/name_mismatch）。在报告生成 both/full 路径经 `merge_pipeline_data()` 注入 `pipeline_data`。
- **轮2 源健康 + 品种覆盖两区块**：新增 `src/python/report/data_quality_sheet.py`（`write_data_quality_sheet()` 写「数据质量仪表盘」标题 + 源健康区块 + 品种覆盖区块；异常品种行红色标注；无行情时写降级占位）。Excel「数据源可用性矩阵」章页签在开关启用时改用仪表盘样式，关闭时回归旧「数据源可用性矩阵」（辅助函数 `_write_data_source_matrix_sheet` 提取保留）。HTML「数据源可用性矩阵」章追加品种覆盖表。config 新增开关 `report_submodules.data_quality`（默认关），`is_enable_data_quality()` 读取；编排层 basic/both/full 三条路径统一接线。
- **数据契约注册**：`position_status` 在 `pipeline_data_builder.py` `_PIPELINE_DATA_KNOWN_KEYS`/`_PREP_KNOWN_KEYS`/类型映射注册，`merge_pipeline_data()` 合并；契约类型/版本/写入消费模块已预定义于 technical.md 附录 H。
- **轮3 可信度摘要 + 单日跳变检测**：新增 `src/python/core/data_freshness.py`，`classify_freshness()` 逐品种分类新鲜度（fresh 当日 / cached 上交易日 T-1 / stale 过期 / degraded 无有效行情），`detect_price_jumps()` 仅对 fresh/cached 品种判定单日 |涨跌幅| ≥ ±20% 跳变（label「疑似数据错误（单日 +X.XX%）」，stale/degraded 跳过以免跨非交易日累计涨跌误报），`build_freshness_summary()` 输出数据契约 `data_freshness`（available/items/abnormal_count/summary）。交易日依据 `report/market_value.py::get_last_trading_day/get_prev_trading_day`（akshare 日历缓存）。「数据源可用性矩阵」章「数据质量仪表盘」页签新增可信度区块，HTML 报告头部新增「N 个品种数据异常」摘要行；`data_freshness` 注册进 `pipeline_data_builder.py` 4 处集合/映射，编排层 basic/both/full 三条路径统一注入。
- **测试**：新增 `src/test/unit/report/test_data_quality_sheet.py`（13 例：build_coverage_block 规范化 / 仪表盘三区块写入 / 降级占位 / 异常行标注 / 空矩阵兜底 / 跳变红色标注 / 旧样式回归）、`src/test/unit/core/test_data_freshness.py`（19 例：新鲜度分类 6 / 单日跳变检测 8 / 可信度摘要组装 5，覆盖阈值、非交易日不误报、降级跳过跳变、过期缓存分类）、`src/test/unit/config/test_config.py` 新增 `is_enable_data_quality` 5 例、`src/test/unit/report/test_holding_status.py` 品种覆盖诊断用例、`test_orchestrator.py` 断言 position_status/data_freshness 注入与开关透传。
- **向后兼容**：开关默认关，既有「数据源可用性矩阵」章输出（Excel 矩阵 + HTML 源健康表）不变，由旧样式回归测试断言。

### 行动建议章（「行动建议」章，独立顶层章节，轮4 框架落地）

- **计算层**：新增 `src/python/analysis/action_advisor.py`，`build_action_data()` 单源计算（纯计算层，不依赖 report/），输出数据契约 `action_data`（`available/summary/rebalance_signals/discipline_signals/rebalance_advice/attribution`）——再平衡信号（单品占比超警戒线）轮4 落地；交易纪律轮5 落地；调仓建议/收益归因空子块框架先行、后续轮次填充，报告结构保持稳定。
- **章节注册**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 新增 `action`（type=`action`、data_flag=None、number=20），`_REPORT_SHEET_NAMES` 注册「行动建议」；`data_source_status` 顺延为 21、`llm_usage` 为 22（共 22 模块）。
- **独立顶层开关**：config 新增 `enable_action`（默认关），`_config_defaults.py`/`_core.py`（`is_enable_action()`）/`__init__.py` 导出/`_validation.py`（`_validate_enable_boards`）四处接线；board 层 `html_writer._compute_section_visibility` 与 `excel_sheet_factory.create_sheets` 的 `board_flags` 均新增 `action` 条目，两层可见性模型（§4.5）同步。
- **单源计算两处呈现**：`action_data` 由 `report/orchestrator.py` 组装（both 路径在 `_report_generation.py` 直接以 `build_action_data` 注入），HTML「行动建议」章 `partials/action_section.html` + Excel `report/action_sheet.py` + 「智囊团深度复盘」章「行动摘要」子块（引用「行动建议」章序号）共享同一对象，无模块级全局变量（渲染数据经context传递）。
- **数据契约注册**：`action_data` 在 `pipeline_data_builder.py` 4 处集合/映射注册，契约类型/写入/消费模块预定义于 technical.md 附录 H。
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
- **份额取整（代码类型判定合规）**：复用 `core/code_utils.py`（is_a_share_code / is_exchange_fund_code / is_otc_fund_by_name）判定证券类型——A 股一手 100 股向下取整、场内基金/ETF 一手 100 份、场外基金整数份；不足一手（取整为 0）不生成建议。场外基金判定优先于 A 股（00 代码区间重叠，先经名称关键词排除）。
- **审查修复（rf-214~216）**：`core/code_utils.py` 的 `_OTC_FUND_NAME_KW` 补「债券/指数/股票」关键词（修复 00 前缀债券型基金如 `000311` 误判为 A 股导致漏计赎回费）；`estimate_fee()` 增加卖出方向守卫（未知操作抛 ValueError）；`_round_to_lot`/`estimate_fee` 名称缺失（None）归一化为空串防御。残留建模限制见 rf-217（1 前缀场外持有基金需持仓渠道上下文，当前默认场内口径）。
- **费用估算**：本地静态费率表（佣金万 2.5 最低 5 元 / 印花税 0.05% 仅 A 股卖出 / 赎回费 0.5% 仅场外基金卖出），`estimate_fee()` 导出，费率表可经 `fee_table` 覆盖（测试固定 fixture 断言精度 <0.01 元）。
- **现金缓冲**：从 available_cash 起按执行顺序累计卖出净额（金额 - 费用），任一条执行后现金为负则剔除（现金负值防护）；同品种触发多条（再平衡 + 纪律）时去重保留优先级最高（止损 > 部分止盈 > 卖出减仓）。
- **接入**：`action_advisor.build_action_data()` 在信号计算后调用可行化层填充 `rebalance_advice`；full 路径 orchestrator 的 holdings_details 补充 shares/price（供计算卖出份额，both 路径本就具备）；HTML「行动建议」章调仓建议表格与 Excel 子块补 金额/调仓后现金 两列；附录 H 契约更新。
- **测试**：新增 `src/test/unit/analysis/test_rebalance_advisor.py`（27 例：份额取整一手 5 / 操作生成 3 / 费用估算 7 / 现金缓冲 3 / 优先级去重 2 / 多品种与守卫 7，含债券基金赎回费、港股整数份、名称缺失、未知操作守卫回归）；`test_action_advisor.py` 新增 shares/price 字段与调仓建议流经、摘要计数；`test_action_html.py`/`test_action_sheet.py` 补调仓建议表格行渲染；`test_code_utils.py` 补 `is_otc_fund_by_name` 债券/指数/股票关键词与股票负例。可行化层覆盖率 ≥85%。

### 收益归因（「行动建议」章，轮7 落地）

- **共享纯计算**：新增 `src/python/analysis/return_attribution.py`，`compute_return_attribution()` 单一计算实现（纯本地、零新增外部依赖）——组合收益按品种贡献排序，TOP 5 盈利/亏损来源（贡献占比 pp，非收益率，两者不可混用）、正负分列，每项含 name/code/profit/contribution_pp（全精度浮点，正数盈利 / 负数亏损）；pos_total/neg_total 为全部持仓（非仅 TOP5）正负盈亏合计。无持仓或 Σ|profit|==0 返回 None（渲染层写「待生成」占位）。
- **提示词段落复用（架构遵从，llm → analysis 单向依赖）**：`llm/prompts_core.py::_build_profit_attribution_block` 改为惰性 import `compute_return_attribution` 复用同一计算（与 `_build_rebalance_block` 复用 simple_rebalance 同构），段落输出逐字节一致——「智囊团深度复盘」章 LLM 段落与「行动建议」章表格为同一数据的两处格式化，无重复实现；`prompts_action.py` 既有引用（模块级 import）自动继承。
- **渲染适配层**：`build_return_attribution()` 把共享计算结果塑形为「行动建议」章表格契约（`attribution`：`available/盈利来源/亏损来源/summary`），summary 净额合计摘要分三类文案（混合盈亏「盈利品种合计 +…，亏损品种合计 …（净…）」/ 全部盈利 / 全部亏损）。「行动建议」章 Excel（`report/action_sheet.py` 子块 4）与 HTML（`partials/action_section.html` ④ 区块）渲染适配：贡献占比 `+X.Xpp`、盈亏金额 `+,.2f` 格式化 + 净额合计摘要行（HTML 用 str.format 风格 `{:+.1f}`/`{:+,.2f}`，% 风格不支持千分位逗号）。
- **契约更新**：`action_advisor.build_action_data()` 在持仓可用且总市值 >0 时调用适配层填充 `attribution`（Σ|profit|=0 时 None）；数据契约 docstring 同步；technical.md 附录 H `action_data` 契约更新 attribution 字段描述（含 return_attribution 实现与降级）。
- **测试**：新增 `src/test/unit/analysis/test_return_attribution.py`（14 例：TOP5 排序/正负分列 3 / 固定 fixture 精度 <0.01% / pos_neg_total 覆盖全部持仓 / 空/零盈亏保护 / 缺省 profit / 数据契约 / 浮点值保留 / 摘要三态 / 不可归因透传 / 提示词段落逐字节一致复用断言 ×2）；`test_action_advisor.py` 更新归因零盈亏保护断言 + 新增有盈有亏填充断言；`test_action_sheet.py`/`test_action_html.py` 归因 fixture 改浮点契约 + 渲染格式/净额摘要断言。`return_attribution.py` 覆盖率 97%（≥85%）。测试用例总数 4,623 → 4,639。
- **向后兼容**：`enable_action` 默认关；开关开启且有盈亏时「行动建议」章归因子块由「待生成」占位升级为真实表格 + 净额摘要，报告结构不变。

### 持仓关系矩阵合并（「持仓关系矩阵」章，轮8「一章两区块」物理合并）

- **章节合并**：原「持仓重合度矩阵」章与「持仓相关性矩阵」章物理合并为「持仓关系矩阵」章——同一章节内**上区块 持仓重合度矩阵**（Jaccard 系数/共同持仓明细）+ **下区块 持仓相关性矩阵**（Pearson r/显著性/下三角热力格），章节可见性 = 重合度或相关性任一区块有数据。
- **统一渲染模块**：新增 `src/python/report/position_relationship_sheet.py`（`write_position_relationship_sheet(ws, overlap_result=None, correlation_data=None)`，内部分 `_write_overlap_block`/`_write_correlation_block` 两区块，任一区块缺失写降级占位）；删除 `fund_overlap_sheet.py`、`correlation_sheet.py` 两个旧页签模块。`fund_overlap.py::compute_overlap_matrix` 重合度计算引擎保留（缓存前缀 `fund_overlap_` 不变）。
- **章节编号重排（22 → 21 模块）**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 收敛为 21 项，`position_relationship`（number=7、data_flag=`position_relationship_data`）替换原 `fund_overlap`/`correlation_analysis` 两个条目，其后各章序号整体 -1（`expert_review` 14→13、`action` 20→19、`data_source_status` 21→20、`llm_usage` 22→21）。章节序号引用全量同步（trade_discipline/return_attribution/action_advisor/data_freshness/holding_status/prompts_core/data_quality_sheet/action_sheet/pipeline_data_builder/orchestrator/excel_generator/html_writer/_report_generation/report_template.html/action_section.html）。
- **数据契约收敛**：`position_relationship_data`（`available/status/window/sample_count/codes/names/matrix/p_values/pairs/insufficient_codes/note`，11 键）替代 `correlation_data` 在 `pipeline_data_builder.py` 注册/合并，编排层 both/full 路径统一注入；技术文档 data_flag 表、缓存表、数据契约表同步。
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
  - **明确不捕获**（避免误伤，注释侧含原因）：小写短局部名（`h1/t1/f1`——Future/测试脚手架）、注释中裸"族字母+数字"（与 Excel 单元格 `A1/B2` 结构性冲突）、`图下说明`/`P1`/`S-P1`/`A3`/`R17` 等合法约束/优先级/场景/需求交叉引用。
- **测试**：`src/test/unit/scripts/test_trace_check_scripts.py` 新增 9 例——注释系列代号正/负用例（`b_series`/`G系列` 命中；`drawdown_series`/`全系列`/`图下说明`/`A1:B1` 不命中）、标识符违规命中与合法短局部不命中、`_iter_identifiers` AST/JS 提取断言。
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
- **危机区间标注（新区块）**：新增 `src/python/analysis/crisis_annotation.py`（`build_crisis_annotation(history_data)`，纯标准库、analysis 层隔离），基于 `history_data.bars` 对预设历史危机区间（2015 股灾 / 2018 贸易摩擦 / 2020 疫情 / 2022 调整，`CRISIS_INTERVALS` 静态历史事实表，不随持仓变化、不拉长 lookback、零新增网络请求）做窗口重叠裁剪与区间统计——`in_range`（是否与报告数据窗口重叠）/`interval_drawdown_pct`（区间最大回撤，正数 %）/`trough_date`（最深日）/`recovery_days`（恢复耗时，未恢复 None）/`recovered`；无重叠时显式写「报告数据窗口内无历史危机区间」占位。输出数据契约 `crisis_annotation_data`，both 路径在 `report/_report_generation.py` 以 `build_crisis_annotation(history_data)` 注入 pipeline_data。
- **统一渲染模块**：新增 `src/python/report/portfolio_history_drawdown_sheet.py`（`write_portfolio_history_drawdown_sheet(ws, history_data=None, crisis_annotation=None)`，内部分 `_write_trend_block`/`_write_drawdown_block`/`_write_crisis_block` 三区块，任一区块缺数据写降级占位）；删除 `excel_generator.py` 旧 `_write_portfolio_history_sheet`/`_write_drawdown_analysis_sheet` 两个独立写入函数，合并为 `_write_history_sheets` 统一写入。`portfolio_history.py` 计算引擎与 `test_portfolio_history.py` 保留（轮8 持仓关系合并先例）。
- **HTML 合并 + 危机着色（图下说明）**：`report_template.html` 原 16/17 两模块物理合并为 `sec-portfolio_history_drawdown` 单章节；净值折线图新增危机区间阴影带（Chart.js 侧 `chart_data_builder.py::_compute_crisis_bands` 计算起止索引 → `chart-init.js::buildCrisisBandPlugin` beforeDatasetsDraw 半透明红色带；Canvas 降级路径 `drawSimpleChart` 同款 `crisisBands` 支持）；危机标注净值图**必须 图下说明**（`.chart-caption` 跟随是否有 in_range 区间数据——有→「阴影区间为 2015/2018/2020/2022 主要危机时段」，无→普通文案）。
- **章节编号重排（21 → 20 模块）**：`core/registry.py` `_REPORT_SECTION_DEFAULT` 收敛为 20 项，`portfolio_history_drawdown`（number=16、data_flag=None、type=`history`）替换原 `portfolio_history`/`drawdown_analysis` 两个条目，其后各章序号整体 -1（`portfolio_evolution` 18→17、`action` 19→18、`data_source_status` 20→19、`llm_usage` 21→20）。`_REPORT_SHEET_NAMES` 中文名注册「组合历史走势与回撤」；章节序号引用全量同步（html_writer/excel_generator/orchestrator/_report_generation/chart_data_builder/report_template.html 等）。
- **数据契约增删**：附录 H 删除旧 `portfolio_history`/`drawdown_analysis` 独立契约（`history_data` 契约保留供合并章复用，消费方更新为合并章），新建 `crisis_annotation_data` 契约（8 键，见 technical.md 附录 H）。
- **测试**：新增 `src/test/unit/analysis/test_crisis_annotation.py`（19 例：数据不可用占位 3 / 2018+2020 区间行为断言 4 / 未恢复 2 / data_end 覆盖与恢复扫描 2 / 无 bar/非正值/非法日期防御 3 / 静态表 1 / 窗口解析与重叠 4，`crisis_annotation.py` 覆盖率 94%）；新增/迁移 `src/test/unit/report/test_drawdown_html_excel.py`（16 例：合并章两区块渲染 / 回撤明细表 / 未恢复占位 / 数据不足占位 / 危机表渲染 / 无重叠占位 / 图下说明跟随 / Excel 合并章三区块 + 危机表，`portfolio_history_drawdown_sheet.py` 覆盖率 87%，均 ≥85%）；迁移 `test_excel_report_structure.py`（18 页签）/`test_html_report_structure.py`（16 链接）/`test_excel_generator.py`（8 页签默认顺序 + 旧独立 sheet 不再生成回归断言）/`test_registry.py`（20 模块）/`test_scenario_section_order.py`（history 类型计数 2→1）。轮9 验收「新增测试 ≥8 个、合并断言、行为断言、图下说明 合规」全部满足。
- **向后兼容**：章节物理合并后，`history_data` 契约与 `enable_history` 开关语义不变（board 层可见性不变）；危机标注仅在 `crisis_annotation_data.available` 且存在 in_range 区间时渲染，数据不可用/无重叠时落占位，既有历史报告结构稳定。

### 尾部风险统计（「组合历史走势与回撤」章，轮10 新区块）

- **计算模块**：新增 `src/python/analysis/tail_risk.py`（`compute_tail_risk(bars)`，纯标准库、analysis 层隔离，无 report/llm 依赖，日志走 logging）。复用 `history_data.bars` 历史日收益序列（与 `report/portfolio_history._compute_daily_returns` 同口径 (curr-prev)/prev，小数单位，不额外拉长 lookback、零新增网络请求），输出数据契约 `tail_risk_data`（12 键：`available/sample_size/var95/var99/max_single_day_drop/max_single_day_drop_date/consecutive_down_days/consecutive_down_start/consecutive_down_end/recovery_days_after_drop/recovery_state/warnings`）——VaR(95/99) 历史模拟法（日收益升序取 (1-置信度) 分位损失，正数 %）、最大单日跌幅（% + 日期，无下跌日取 0.0 判状态 none）、最长连续下跌天数（含区间起止日期）、最大单日跌幅后恢复天数（`recovery_state` 分 `recovered`/`unrecovered`/`none`）。样本下限 `MIN_SAMPLE=20`，不足时 available=false 各指标置 None 落 §1.4.5 降级。
- **数据容错**：bars 中 `total_value` 为 0/负/NaN/缺失时相邻收益不成对自动跳过（prev>0 且 curr>0 才构成有效收益），避免伪 -100% 单日；缺失/非法 date 字段日期返回 None 不崩溃；极大（1e12）/极小（1e-4 级）量级计算不溢出不丢精度。
- **全接线**：both 路径 `report/_report_generation.py` 在危机标注注入旁以 `compute_tail_risk((history_data or {}).get("bars"))` 注入 pipeline_data（full 路径 `_prepare_full_risk_metrics` 同步），经 `_generate_full_html_report` → `html_writer.write_html_report` → `_render_html_template` 传入模板；Excel 经 `excel_generator._write_history_sheets` → `portfolio_history_drawdown_sheet.write_portfolio_history_drawdown_sheet` → 新增 `_write_tail_risk_rows`（五行：VaR(95)/VaR(99)/最大单日跌幅/最长连续下跌/最大单日跌幅后恢复，百分比按 FMT_PERCENT 存小数；未恢复写「未恢复」、不可用写「样本不足」占位）。
- **HTML 尾部风险卡（图下说明）**：`report_template.html` 合并章新增 summary-grid 尾部风险卡组（VaR95/VaR99/最大单日跌幅/最长连续下跌/最大跌幅后恢复，`| change` 格式化百分比），不可用时单卡「样本不足」占位；卡组下方附 图下说明「尾部风险基于历史日收益序列（历史模拟法 VaR）；恢复天数指自最大单日跌幅日收复跌幅前水平所需交易日」。
- **数据契约注册**：`tail_risk_data` 在 technical.md 附录 H 注册（12 键契约 + 计算/注入/消费/降级说明）。
- **测试**：新增 `src/test/unit/analysis/test_tail_risk.py`（15 例，`@pytest.mark.unit`+`unit_analysis`：VaR95/99 固定 fixture 精度 <0.01% / 置信度排序 / 无损失日 VaR=0 / 最大单日跌幅值+日期 / 并列最深取首 / 连续下跌天数+区间 / 更长区间优先 / 无下跌 0 天 / 恢复已恢复/未恢复/none 三态 / 样本不足/None/空占位 / 契约字段完整）、`src/test/unit/analysis/test_tail_risk_edge.py`（10 例，`@pytest.mark.edge` 放 `*_edge.py`：0/负/NaN/缺失 total_value 跳过 / 缺失日期容错 / 1e12 量级不溢出 / 1e-4 精度 / 恰 20 available / 19 unavailable / 单点 / 持平序列）、`src/test/unit/report/test_tail_risk_wiring.py`（10 例，`@pytest.mark.unit`+`unit_report`：pipeline 注入充足/不足/None 跳过 / Excel 五行+未恢复+占位 / HTML 卡渲染+未恢复+样本不足占位+图下说明）。`tail_risk.py` 覆盖率 96%，全部 ≥85%。轮10 验收「新增测试 ≥8 个、固定 fixture 精度 <0.01%、行为断言、边缘测试文件隔离 边缘合规」全部满足。
- **向后兼容**：`tail_risk_data` 为新增键、`write_portfolio_history_drawdown_sheet`/`write_html_report`/`_render_html_template` 新增参数均带默认值，既有调用与测试不受影响；样本不足时落「样本不足」占位，既有报告结构稳定。

### 自上次快照变化摘要（「组合演进」章顶部，轮11 新区块）

- **计算模块**：新增 `src/python/analysis/snapshot_diff.py`（`build_snapshot_diff(threshold_pct=15.0, min_snapshots=2)`，纯标准库、analysis 层隔离，无 report/llm 依赖，日志走 logging）。复用 `data/history/snapshots/` 多期快照本地数据（零新增网络请求），按日去重（复用 `portfolio_evolution._dedup_by_date`）后取最近两次对比，输出数据契约 `snapshot_diff_data`（12 键：`available/snapshot_count/previous_date/current_date/added/removed/hhi_previous/hhi_current/hhi_change/over_limit/summary/reason`）——新增/移除品种按 code 跨账户合并比对（复用 `fetcher/history_diff.HistoryDiff` 引擎），集中度 HHI 变化（本期-上期，市值口径优先、市值为 0 回退成本，与演进同口径，复用 `_compute_hhi`/`_holding_weight`），超 15% 警戒线品种（阈值复用 `analysis/simple_rebalance._THRESHOLD`，按权重降序）。去重后有效快照 < 2 期（无上次快照可对比）时 available=false、reason 说明，落 §1.4.5 降级。
- **全接线**：both/full 路径 `report/_report_generation.py` 新增 `_inject_snapshot_diff_data`，在组合演进注入旁同步注入 pipeline_data（与 `evolution_data` 同开关 `enable_portfolio_evolution`），经 `_generate_full_html_report` → `html_writer.write_html_report` → `_render_html_template` 传入模板；Excel 经 `excel_generator` → `evolution_sheet.write_evolution_sheet` 新增 `snapshot_diff_data` 参数，写入页签顶部「自上次快照变化摘要」区块（新增/移除品种、HHI 变化、超限项逐行）。
- **HTML 摘要卡**：`partials/evolution_section.html` 组合演进章顶部新增「⑤ 自上次快照变化摘要」notice-banner 摘要卡（summary 全文 + 对比区间 previous_date → current_date），数据不足时显示 reason 占位文本。
- **数据契约注册**：`snapshot_diff_data` 在 technical.md 附录 H 注册（12 键契约 + 计算/注入/消费/降级说明）。
- **测试**：新增 `src/test/unit/analysis/test_snapshot_diff.py`（8 例，`@pytest.mark.unit`+`unit_analysis`：无上次快照占位 / 新增移除检测 / HHI 变化 / 超限项降序 / 相同快照持平 / summary 覆盖全部变化点 / 市值 0 成本回退 / 同日去重保留最后）、`src/test/unit/analysis/test_snapshot_diff_edge.py`（6 例，`@pytest.mark.edge` 放 `*_edge.py`：空目录 / 空持仓 / 全 0 权重防除零 / 阈值 0 全超限 / 损坏文件跳过 / 多账户聚合）。`snapshot_diff.py` 覆盖率 100%，全部 ≥85%。轮11 验收「新增测试 ≥6 个、行为断言、无上次快照占位、边缘测试文件隔离 边缘合规」全部满足。
- **向后兼容**：`snapshot_diff_data` 为新增键、`write_html_report`/`_render_html_template`/`write_evolution_sheet`/`_generate_full_html_report` 新增参数均带默认值，既有调用与测试不受影响；无上次快照时落占位，既有报告结构稳定。

---

## [0.10.5] - 2026-08-05

### plan.md 已完成事项整体归档至 archived_plan.0.10.x.md

- **动机**：`plan.md` 承载当前迭代待办 + 已完成项详细记录，v0.10.x 已发布事项（plan-17~24）详细段落随迭代推进持续累积，活跃文档过重。按「已完成历史版本计划已归档，此处仅跟踪当前迭代中的工作」原则，将已发布（v0.10.1/v0.10.3/v0.10.4）的已完成事项记录整体迁入归档索引，`plan.md` 回归轻量「未完成项 + 归档引用」结构。
- **迁移内容**（`plan.md` → `docs-stm/archive/v0.10.x/archived_plan.0.10.x.md`）：P0 发布门禁两条（v0.10.3/v0.10.4）、推荐实施顺序 ①~⑧ 表格、P1~P3 已完成项详细段落（plan-17~24 每项轮次/验收/门禁记录）。
- **归档文档结构**：设计文档索引（investment-features + task-code-traces-gate）+ v0.10.x 已完成项摘要表 + P0 发布门禁 + 推荐实施顺序 + P1~P3 详细段落（原相对链接改指本目录内 `investment-features/` 兄弟路径）。
- **plan.md 精简**：概述改为指向归档（含设计文档索引 + 完成项摘要表 + 推荐实施顺序 + 发布门禁记录）；当前迭代待办仅保留 P4 实验功能（plan-8/plan-10，未完成）；归档列表保持。
- **状态变更**：`plan.md` 中已完成项状态由「当前迭代待办」转为「已归档」；`plan-next` 编号源不变（已用最大 plan-24，归档不回收）。

### 新增 opt-in live 真实网络验证套件（不入门禁）

- **动机**：既有测试体系全 mock（网络依赖由运行时回退/熔断治理，非门禁），无法直接排查「数据源是否真的可达 / API 是否漂移」。新增 `live` 套件作为独立运维验证通道，与门禁严格隔离。
- **基建**：`src/test/live/` 14 项真实联网测试（行情：A 股/ETF/场外基金/中美指数；新闻：东方财富/财联社/新浪/华尔街见闻；基金：历史净值/排名/基准；akshare 交易日历）。三层机制保证**平时完全不运行**：① `pytest.ini` `addopts = -m "not live"` 收集期排除；② conftest `_skip_live_unless_requested` autouse fixture 默认 skip；③ test_runner 门禁模式不引用。验证：全量收集 4981/4995（14 deselected，即 live 被排除）。
- **断言原则**：只校验返回「结构」（字段存在、类型、非空），不校验具体数值，容忍真实行情波动；不含 LLM 真实调用（防费用）。`_block_external_network` 阻断 fixture 放行 live 项（显式 `--run-live`/`-m live` 时）。
- **触发方式**：`python scripts/test_runner.py --mode live`（新增 MODES 条目，order 14）或 `pytest --run-live -m live`。
- **文档同步**：how-to-test-my-code.md（②专项验证代码块 + 新增 live 小节 + 报告目录树）、testplan.md（测试环境网络行标注 live opt-in）。
- **门禁**：dev-verify 1706 passed + 3 check 全 [OK]。

### 功能语义命名表抽取为活索引（technical.md §6.7）

- **动机**：CLAUDE.md「语义化命名」条目原引用归档文档（`docs-stm/archive/v0.10.x/investment-features/plan-investment-features.md` §2.0）作功能语义命名表，归档后引用路径不稳定、可追溯性差。共性语义命名表应入管理文档作为**活索引**，各轮设计文档中的原始表降级为历史快照。
- **抽取**：`technical.md` 新增 `### 6.7 功能语义命名表`——纪律说明（代码标识符=文档中文描述、先定语义名再设计、任务代号不入实现层）+ 14 行核心功能语义命名表（candidate_compare/valuation_percentile/market_temperature/rebalance_advice/trade_discipline/return_attribution/fund_flow/dividend_flow/industry_beta/crisis_annotation/tail_risk/snapshot_diff/data_quality/holding_diagnosis）+ 合并章 key 说明（position_relationship/portfolio_history_drawdown/style_factor）+ registry.number 重排说明（1~19）；同时更新技术文档目录 TOC 添加 6.7。
- **引用改向**：CLAUDE.md「语义化命名」条目引用改指 `docs-stm/managements/technical.md` §6.7（活索引）；归档 `plan-investment-features.md` §2.0 原始表保留为历史快照不追溯修改。
- **门禁**：check-code-traces.py 不引用归档表格（抽取无冲突），3 check 脚本 `--ci` 待最终全量验证。

### 消除测试用例运行时外部网络依赖（全局 socket 阻断防线）

- **审计方法**：临时 socket 阻断插件全局替换建连入口（socket.socket 用类替换保留 ssl 继承、socket.create_connection / getaddrinfo 函数替换），扫描全部测试套件——凡触发真实网络连接的用例立即失败暴露。unit 套件 + scenario/integration 共扫描出 **5 处**未 mock 的真实网络依赖。
- **修复 5 处未 mock 网络调用**：
  - `test_fetcher.py::TestFetchFundBenchmark`（2 例）：`fetch_fund_benchmark` 三层策略（API 解析→内置知识库→配置覆盖）先走 API 解析层联网；mock `_fetch_benchmark_from_api` → None 改走内置基准库，用例改用内置库真实代码 561910。
  - `test_data_integrity.py::test_a_index_value_ranges` / `test_cache_consistency.py::test_index_cache_shared_across_modules`：mock 指数数据只覆盖 5/1 个，而 `_A_INDICES` 共 7 个 → 缺失项触发新浪备用链路联网；补 patch `_fetch_indices_from_sina` → {} 阻断 fallback。
  - `test_orchestrator.py::test_generate_report_skeleton`：骨架 basic 路径真实生成 Excel，依赖交易日历（akshare 联网）+ A 股/美股指数 + 后台数据源健康检查（全量 HTTP 连通性探测）；补 mock `_get_trading_calendar` / `fetch_indices` / `fetch_us_indices` / `_spawn_health_checks` / `_collect_health_checks`。
- **全局防线**：`conftest.py` 新增 `_block_external_network` autouse fixture——测试运行时全局阻断 socket 建连，任何未 mock 的网络调用（数据源 API / LLM API / akshare / 健康检查）立即抛 RuntimeError 使测试失败，从机制上杜绝测试运行时外部网络依赖。已 mock HTTP 层（httpx.Client / requests / provider / `_fetch_*`）的测试不创建真实 socket，不受影响；真实建连仅发生在「应 mock 却未 mock」时。
- **验证**：unit 4660 passed + 12 skipped、scenario+integration 309 passed + 76 subtests、dev-verify 1706 passed / 0 failed，均无外部网络依赖。

### 文档全面核对与修复（folders.md 统计刷新 + 用户/管理文档一致性审计）

- **folders.md 统计与目录树核对**：项目统计表核对至当前实时状态（主程序 222 文件/55,247 行、HTML 4 文件/3,761 行、辅助脚本 16 文件/5,581 行、源代码合计 242 文件/64,589 行、测试代码 276 文件/78,332 行、测试用例 4,980 个）；目录树层级符号对齐（`├──`/`└──` 一致性）与文件补录；报告章节图表初始化描述「6 张」→「9 张（6 核心 + 3 演进；单图异常隔离 + degraded 虚线）」。
- **管理文档一致性核对**：technical.md 12 处修复——缓存层线程池唯一宿主表述、线程池表由 2 池补全为 9 池（orch_prep/orch_factor/orch_factor_idx/orch_ind/orch_ind_idx/orch_val/orch_corr/orch_llm_news/orch_health，含用途与 max_workers）、基金深度分析模块数 5→4、相关性区块数据契约引用改指附录 H 且架构约束注册引用改指 §8.3、STATUS_MESSAGES「23 条」→「24 条」、llm/ 子模块「36 个」→「32 个」、`module_{标识}`→`{参数}_{标识}` 命名约定、portfolio_evolution number=16、action number=17；requirements.md 8 处——降级引用统一「technical.md §1.4.5」、调仓建议/收益归因由「框架子块」更新为「已实现（无数据写『待生成』）」；testplan.md——场景规格表头补齐 D1-D3、无人工门禁表述更新、unit_config_edge 预留说明；llm-technical.md——批处理并行度「最多 3 批并行」表述、附录 B 定价表补 claude-sonnet-4-8/claude-opus-4-6 具名模型 + 6 个前缀回退键脚注；test-coverage.md——分组标题层级统一、场景覆盖项数/文件数/基准指数覆盖表述刷新；README.md——Chart.js 图表数 6→9。
- **用户手册一致性核对**：how-to-test-my-code.md 场景编号 S1-S34→S1-S33（S34 基准指数对比为合法规格项、由单元测试覆盖，testplan.md 规格表保留 S34）；reports-instruction.md / faq.md / how-to-config.md / datasource*.md / how-to-menu.md 等章节序号、目录锚点、模型名、数据源清单核对至最新状态。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]，dev-verify 1706 passed / 0 failed。

### 修复 akshare 交易日历并发 V8 崩溃（rf-228）

- **问题**：TUI 菜单「2」更新行情缓存时进程崩溃，`[FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized()`（abort 整个进程，try/except 无法捕获）。根因链：菜单 2 并行价格抓取（ThreadPoolExecutor 4 workers）→ 每价格新鲜度校验 `_price_cache_fresh` → `get_last_trading_day()` → `_get_trading_calendar()` → `akshare.tool_trade_date_hist_sina()`（新浪交易日历）。akshare 该函数内部用 `py_mini_racer`(V8) 解密、**每次调用都新建 V8 实例**；多线程并发首次初始化 V8 触发 `partition_address_space` FATAL。已在 tmp 探针脚本复现（4 线程并发 → EXIT 3 崩溃；加锁串行化 → 全成功）。
- **修复**：`market_value.py::_get_trading_calendar()` 缓存未命中分支用模块级锁 `_TRADING_CALENDAR_AKSHARE_LOCK` 串行化 + **双重检查**（锁等待后重新读缓存，避免重复拉取）。V8 顺序初始化安全。不影响单线程正常路径。
- **回归测试**：`test_market_value.py` 新增 `TestTradingCalendarConcurrency`——4 线程并发调 `_get_trading_calendar()`，注入 fake akshare（`patch.dict(sys.modules)`）统计回调最大并发深度，断言**串行化不变量 max_active == 1**。全 mock 无真实 V8/网络调用。
- **连带优化**：审计发现 `test_market_value.py` 多个测试类裸调用 `is_market_open`（东方财富 push2 API 真实 HTTP，timeout 5s）与 `_is_trading_day`（akshare 交易日历网络）导致单用例 2~6s。为 `TestPriceUpdateStatus`/`TestDeterminePriceType`/`TestGenerateDetails`/`TestPremiumPlaceholder`/`TestTodayProfitEastMoneyNonTDay`/`TestTodayProfitTencentAlways`/`TestTodayProfitEdgeCases`/`TestPremiumInWriteSheet`/`TestCurrencyConversion`/`TestTodayProfitOffMarket` 统一补 setUp mock（`is_market_open`/`is_midday_break`/`_is_trading_day`），消除用例内网络依赖。用例 call 时间从 2~6s 降至 0.01~0.08s（剩余启动开销为环境 Python 解释器慢，与测试无关）。

### HTML 报告目录 LLM 章节标记（橙色加粗 + 🧠 图标）

- **功能**：HTML 报告两处导航（左侧目录 `.toc-sidebar` + 窄屏顶部横向 `.section-nav`）中，由 LLM 生成/支持的章节标题改为**橙色加粗**并在标题旁显示 **🧠 图标**。dark mode 下橙色复用双定义变量 `--orange-text`（浅色 `#E65100` / 深色 `#ff8a50`），天然适配。
- **标记范围**：与「LLM」导航组同源派生——`html_writer.py` 新增常量 `_LLM_SUPPORTED_SECTIONS`，从 `_SECTION_NAV_GROUP_MAP` 的 `"llm"` 组推导（单一数据源防漂移，覆盖新闻关联 + LLM 文本分析系列 + API 用量），经 render() context 传入模板（渲染期数据经 context 传递约束）。
- **实现**：模板目录/横向导航链接按章节 LLM 支持位加 `toc-llm` class 与 `span.toc-llm-icon`（`aria-hidden="true"`）；CSS 新增 `.toc-list a.toc-llm` / `.section-nav a.toc-llm`（橙色加粗）与 `.toc-list a.toc-llm.active`（active 态保持橙色，特异性高于既有 active 规则）；打印样式已隐藏两导航，无需处理。
- **测试**：`test_html_report_structure.py` 新增 7 例（常量与「LLM」组一致性、目录/横向导航标记与未标记断言、分组 dict 携带 `llm_supported`、CSS 规则存在、颜色变量双定义复用），并更新 2 例既有测试（剔除 🧠 图标后比对导航文字一致性 / LLM 目录文案前缀+图标断言）。report 套件单测全绿（1482 passed）。

### 迭代计划归档（plan-17~24 收官，2026-08-05）

- **归档**：`plan-investment-features.md`（设计层）+ `plan-investment-iteration.md`（实施层，21 轮）由 `docs-stm/plan/` 移入 `docs-stm/archive/v0.10.x/investment-features/`；`plan-task-code-traces-gate.md`（rf-208 门禁增强设计）移入 `docs-stm/archive/v0.10.x/task-code-traces-gate/`。新增 `docs-stm/archive/v0.10.x/archived_plan.0.10.x.md` 归档索引（已完成项表 plan-17~24 + 设计文档索引 + 归档说明），沿用 v0.9.x `archived_plan.*.md` 格式。
- **引用同步**：plan.md 概述/推荐实施顺序/已完成章节链接改指归档索引与归档路径，归档区新增 `archived_plan.0.10.x.md` 条目；folders.md 目录树 `plan/` 仅保留未完成项（plan-web-ui*/plan-web-ui-implementation*），新增 `archive/v0.10.x/` 子树；CLAUDE.md 语义化命名条目中功能语义命名表示例路径改指归档文档。`docs-stm/plan/` 现仅存 plan-8/plan-10（P4 实验功能）设计文档。
- **门禁**：3 check 脚本 `--ci` 全 [OK]（check-task-numbering exit 0，归档编号与历史归档无冲突）。

### changelog 主题标题层级统一（v0.10.3 起 `####` → `###`）

- 修正 v0.10.3/v0.10.4/v0.10.5-dev 各版本主题标题层级漂移：开发节引入 `### 开发中（未发布）` 占位后主题误用四级 `####`，转正式节时未同步升回。现统一为三级 `###`，与 v0.10.0~0.10.2 及 v0.9 分类层级（`###`）对齐。v0.9.x 归档保持原格式不追溯。

### CLI 集成测试 patch 目标修正（rf-227）

- **问题**：`test_cli_integration.py` 三处 CLI 测试 patch 目标陈旧——41df26a「根文件归子包」重构后残留包级 re-export 路径 `src.python.cli._cli_read_holdings`，拦截不到 `cli.py` 模块内部同名引用。`test_cli_cache_config_respected` 因此走到真实持仓读取（`/test/holdings/test.xlsx` 不存在）→ mock 调用 0 次断言失败；另两例（`test_cli_report_config_respected`/`test_handle_report_return_exit_code`）靠 `data/holdings/` 默认持仓文件恰好存在而侥幸通过。
- **修复**：三处 patch 目标统一修正到 `src.python.cli.cli._cli_read_holdings(_with_flows)`；report 路径两例改用 `_cli_read_holdings_with_flows` 返回 `(mock_holdings, [], [])`（与 `_handle_report` 实际调用路径一致），彻底脱离真实持仓文件依赖，测试隔离达标。
- **验证**：全量 `test_runner.py --mode all` 5026 passed / 0 failed / 12 skipped；CLI 单测 `test_cli.py`+`test_cli_edge.py` 56 passed 无回归。

### 历史记录归档（review-findings + changelog，v0.10.x 已发布记录迁入归档）

- **review-findings 归档**：`docs-stm/managements/review-findings.md` 已修复表中 v0.10.1/v0.10.3/v0.10.4 的已修复条目（rf-204~rf-226，dev 版 rf-227/rf-228 除外）整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md`，按版本分组（v0.10.1：rf-204~216；v0.10.3：rf-218~225；v0.10.4：rf-226）保留「问题 / 修复方案 / 变更记录」完整记录；`review-findings.md` 已修复表仅保留 dev 版未归档条目（rf-227/rf-228），归档档案段新增 v0.10.x 链接；P3 段末尾 rf-226 补齐注释随迁移删除（信息在归档中）。
- **changelog 归档**：`docs-stm/managements/changelog.md` 中 v0.10.1~v0.10.4 四个已发布版本段整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（v0.10.0 无独立 changelog 段，不单独归档）；`changelog.md` 保留 v0.10.5-dev 开发段 + 归档列表（新增 v0.10.x 链接）。
- **目录同步**：`folders.md` 目录树 `archive/v0.10.x/` 补 `archived_changelog.0.10.x.md` / `archived_review-findings.0.10.x.md` 两行（与 v0.9.x 段三文件并列结构对齐）。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]；全量测试 `test_runner.py --mode all` 4969 passed / 0 failed / 12 skipped；版本号全链一致 v0.10.5。

---

## [0.10.6] - 2026-08-05

### 测试模式耗时标注更新（换机实测 + 机型依赖说明）

- **动机**：测试环境从旧慢笔记本换到当前开发机（Linux x86_64，Intel i5-13500H，12 核 16 线程，46GiB 内存；pytest-xdist worker=8 = medium 50% 核数）后，各测试模式实际耗时大幅下降（如 `all` ~10min → ~21s、`scenario` ~6min → ~18s、`scenario_extreme` ~1min 45s → ~2s），test-coverage.md「典型耗时」列与 test_runner.py 模式描述中的时间标注已严重过时。
- **实测**：2026-08-05 顺序运行除 `live`（opt-in 运维套件，不入门禁）外全部 14 个模式记录 pytest 总耗时——unit ~15s / standard ~16s / scenario ~18s / regression ~17s / dev-verify ~20s / verify ~10s / integration ~14s / edge ~13s / data ~2s / all ~21s / all_no_unit ~10s / smoke ~2s / report ~11s / scenario_extreme ~2s。
- **更新**：`scripts/test_runner.py` MODES 描述 4 处时间估算（dev-verify ~2.5min→~20s、scenario_basic 阶段 ~100s→~10s、smoke ~15s→~2s 且项数 24→26、scenario_extreme ~1min→~2s）并标注「12 核 16 线程并行实测」；`test-coverage.md` 模式表「典型耗时」列全部刷新为实测值，并加注说明**耗时与硬件/操作系统/并行度强相关**（早期标注源自慢笔记本环境，仅作相对量级参考）；同步刷新 `scripts-reference.md`「--mode 对照」表与 `how-to-test-my-code.md` 门禁/流水线/模式说明中的全部耗时标注，并在 test-coverage.md / scripts-reference.md / how-to-test-my-code.md 三份文档补充统计所用硬件配置（i5-13500H 12 核 16 线程 / 46GiB 内存 / worker=8）。
- **门禁**：各模式实测全部通过；改动仅涉及描述字符串与文档，不影响测试逻辑。

### test_runner 机器信息采集与耗时对照表（跨机器采集工具链）

- **动机**：耗时受硬件/操作系统/并行度三因素影响，既有文档已注明「强相关」但需换机采集时才能填表；为在不同电脑（如旧笔记本）上复现采集并回填对照表，需要脚本自动收集环境属性与各模式耗时并输出可直接粘贴的 Markdown 表格。
- **新增 `--mode bench` 聚合别名**：一键顺序运行 14 个对照表模式（`_MODE_TABLE_ORDER` 除 `live` 外的全部模式，`live` 为 opt-in 运维套件不入门禁），结果去重保序；非 bench 模式原样透传。`--machine-info` 输出环境属性表 + 各模式耗时对照表。
- **新增机器信息采集（跨平台容错）**：`_collect_machine_info` 采集 14 项属性——操作系统/系统版本/架构/主机名/CPU 型号/物理核数/逻辑线程/内存/磁盘类型/文件系统/Python 版本/并行级别/worker 数/采集日期。Linux 读 `/proc/cpuinfo`（按 physical id+core id 去重统计物理核）、`/proc/meminfo`、`/proc/mounts` + `/sys/block/*/queue/rotational`（区分 NVMe/SSD/HDD）；macOS 走 `sysctl`；Windows 走 `ctypes.GlobalMemoryStatusEx`。全部读取均 try/except 容错回退 `未知`，不影响 bench 运行；bench 中途 Ctrl+C 先打印已采集部分再退出（`KeyboardInterrupt` 保护，慢机器不丢数据）。
- **耗时表格渲染**：`_render_duration_table` 按对照表固定顺序输出 `--mode | 覆盖项数 | 耗时` 三列，`verify,regression` 合并一行，耗时取整至秒（下限 1s），超时与不在对照表内的模式跳过。`_render_env_table` 输出 14 行环境属性表。输出即为文档表格格式，可直接粘贴进 test-coverage.md。
- **文档同步**：test-coverage.md 新增「采集环境属性」表（当前开发机实测值 + 旧笔记本待补）+「各模式耗时对照」表（实测 vs 早期标注）+ 跨机器采集说明（`--mode bench --machine-info`）；scripts-reference.md 补充 bench/machine-info 用法；folders.md 目录树与项目统计同步（测试代码 283 文件 / 79,122 行、测试用例 4,998 个）。
- **测试**：新增 `src/test/unit/scripts/test_test_runner_machine_info.py` 17 项（机器信息字段完整性/并行级别映射/Linux 回退不崩溃/bench 展开去重排除 live/耗时表格排序与组合行/环境表未知占位），pytestmark `unit` + `unit_scripts`。
- **门禁**：dev-verify 1723 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 修复：事实校验误将止盈/减仓目标比例修正为收益率（rf-230）

- **缺陷**：智囊团深度复盘等 LLM 调仓建议写「建议止盈约30-40%持仓」「止盈约20-30%」，其中 30%/40% 是止盈/减仓**目标比例**（相对当前持仓），非收益率。事实校验因句子含「利润/盈利」触发收益语境，且 `_REBALANCE_TARGET_KEYWORDS` 只覆盖「降至/减仓至」等"至"字式、漏掉「止盈约/减仓约」等"约"字式 → 比例值走全局最近邻被误修正为 601398 实际收益率 70.2%，报告被篡改为「止盈约30-70.2%」「止盈约20-70.2%」，建议语义失真（真实报告复现 + 单测逐字复现修正明细）。
- **根因**：① 语境识别缺失——止盈/减仓目标比例无词表、无邻近窗口检测；② `apply_numerical_corrections` 用 `re.sub` 全局替换（无 `count`），一处修正连带替换 HTML 中所有同值数字。
- **修复**：① `llm/fact_checker/_constants.py` 新增 `_TRIM_TARGET_KEYWORDS`、`_context.py` 新增 `_is_trim_target_context`（match 前 15 字符窗口）、`_numerical.py` `_evaluate_percent_value` 开头拦截；② `llm/fact_checker/_corrections.py` 的 `re.sub` 加 `count=1`。
- **测试**：`test_fact_checker.py` 新增 `TestTrimTargetContext`（真实复现句 30-40%/20-30% 不误修正、单句「止盈约30%」「减仓约20%」、加仓/止损/清仓同义表达、run_fact_check 整链路内容不被篡改、真实收益率 5.0% 仍被校验）+ `TestApplyCorrectionSingleReplace`（同值异义只替换一处）。test_fact_checker 103 passed。

### 修复：What-if 测试断言硬编码 POSIX 路径致 Windows 失败（rf-231）

- **缺陷**：`test_handlers_whatif.py::TestSelectCandidateFile` 三处断言硬编码 POSIX 风格路径，在 Windows 上失败：① `test_only_base_choose_copy_template` / `test_only_base_invalid_choice_then_copy_template` 期望 `dummy_dir/base-调仓后模板.xlsx`（正斜杠），而 `_copy_base_as_template` 用 `os.path.join` 拼接在 Windows 下为 `dummy_dir\base-调仓后模板.xlsx`；② `test_only_base_manual_input_valid` 期望返回 `/tmp/after.xlsx`，但 `_manual_input_path` 对输入做 `os.path.abspath` 后 Windows 下为 `D:\tmp\after.xlsx`。dev-verify 1559 passed / 3 failed，均落此三例。
- **根因**：测试断言直接使用硬编码路径字符串，未随平台路径分隔符/归一化规则自适应。
- **修复**：期望值改用平台无关构造——复制模板路径用 `os.path.join("dummy_dir", "base-调仓后模板.xlsx")`，手动输入返回用 `os.path.abspath("/tmp/after.xlsx")`（与被测代码归一化口径一致）；测试文件补充 `import os`。
- **测试**：test_handlers_whatif.py 16 passed（含原失败三例）。

### 修复：test_runner --update-docs 写入器跨盘符 relpath 崩溃（rf-232）

- **缺陷**：`test_runner.py::_update_test_coverage_doc_file` 打印路径用 `os.path.relpath(_DOC_COVERAGE_PATH, _PROJECT_ROOT)`，Windows 下两路径跨盘符时 relpath 抛 `ValueError: path is on mount 'C:', start on mount 'D:'` 致进程崩溃。`unit` 模式 1 failed（`test_test_runner_doc_writer.py::TestDocFileAndArgs::test_update_doc_file_writes_only_when_changed`，traceback 落 929 行 print）——该测试将 `_DOC_COVERAGE_PATH` monkeypatch 到 C: 临时目录而项目在 D:。
- **根因**：仅用于展示的相对路径换算未处理 Windows 跨盘符（不同驱动器间不存在相对路径），relpath 抛 ValueError。
- **修复**：新增 `_display_path(path, start)` 辅助函数——relpath 抛 ValueError 时降级返回绝对路径；`_update_test_coverage_doc_file` 两处打印（925/929 行）改用该函数。
- **测试**：新增回归测试 `TestDocFileAndArgs::test_display_path_cross_drive_fallback`（Windows 构造跨盘符路径断言返回绝对路径不崩溃，POSIX 断言正常相对路径，平台无关）。test_test_runner_doc_writer.py 23 passed（原失败用例通过）。

### test_runner 环境耗时对照文档自动更新（`--update-docs`）

- **动机**：上一轮 `--mode bench --machine-info` 输出的环境属性表 + 耗时对照表需**手工粘贴**进 test-coverage.md，且脚本 stdout 表格与文档表格列结构不一致（脚本环境表 13 行/OS 与系统版本合并，文档 14 行分列）。用户希望跑完自动更新文档，无需手工编辑。
- **方向（用户已定）**：① 并排表格·按主机名增列——新机器自动追加一列（表头 `{hostname}（{采集日期} 实测）`），同机再次运行原地覆盖刷新日期；历史参考列（旧慢笔记本）永不被触碰；② 显式 `--update-docs` 标志（隐含 `--machine-info`），默认永不写文档。
- **文档标记锚点**：test-coverage.md 两张表各包一对 HTML 注释标记（`<!-- env-table:start/end -->`、`<!-- duration-table:start/end -->`），写入器按标记定位替换区域，标记区外文本逐字节不变；表头预改为 `dragonball（2026-08-05 实测）`（主机名子串匹配列，同机首跑即命中原地刷新，不产生孤儿列）。
- **写入器（纯函数 + IO 封装）**：`_update_test_coverage_doc(doc_text, machine_info, results) -> str` 无副作用解析→替换；`_update_test_coverage_doc_file` 仅内容变化才写盘（缺标记/异常打印 `[ERR]` 返回，绝不破坏既有文档）。表编辑用「token 网格」按 `|` 切分逐格增/改，未改动列字节原样保留；新列分隔标记由最后数据列推断（环境表左对齐 `:---` / 耗时表居中 `:---:`）。
- **环境表统一 14 行**：新增 `_ENV_ATTR_LABELS` + `_env_value(label, info)` 作为 stdout 渲染与文档写入的单一事实源（操作系统/系统版本分列），修复脚本与文档列结构不一致。
- **耗时单元格**：`_duration_mode_cells` 按 `_MODE_TABLE_ORDER` 聚合 `~{N}s`（≥60s 显示 `~{M}min`，对齐文档旧列风格），组合行 `verify,regression` = 顺序耗时之和；超时/未测模式单元格留空（None 保留原值不清空）；Ctrl+C 中断时已跑完模式照常回填。
- **测试**：新增 `src/test/unit/scripts/test_test_runner_doc_writer.py` 22 项（环境表同名列刷新/新列追加/未知行保留、耗时表同列更新/新列留空/组合行格式、标记缺失抛 ValueError、round-trip 幂等、区外文本不变、结构异常防护（标记间夹非表格行/缺分隔行抛错）、替换块反斜杠不触发 re 模板解析、仅内容变化才写盘、非 ValueError 异常降级 [ERR]、`--update-docs` 隐含 `--machine-info`），pytestmark `unit` + `unit_scripts`；既有 `test_test_runner_machine_info.py` 环境表 14 行断言同步。
- **文档**：how-to-test-my-code.md 新增「跨机器耗时采集与环境耗时对照」（`bench` + `--machine-info` / `--update-docs`）小节；folders.md 文档统计行随 changelog/manuals 增补刷新（用户文档 5,689 / 项目文档 41,957 / managements 7,102）。
- **门禁**：dev-verify + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全通过。

### test-coverage 耗时对照表新增「数据更新时间」行（按设备列回填采集日期）

- **动机**：环境耗时对照表此前只有逐模式耗时单元格，表头括号里的实测日期（如 `dragonball（2026-08-05 实测）`）无法在表体一行内直观看清**每列数据的更新时间**；多台设备各自回填后难以一眼确认某列时效。
- **更新**：`test_runner.py` `--update-docs` 写入器在耗时对照表末尾追加「数据更新时间」行——本机匹配列按采集日期回填，其余列保留原值不清空（旧慢笔记本列保持 `—`）；test-coverage.md 耗时对照表补入该行（dragonball / stallman-NB1 为 2026-08-05 实测，旧慢笔记本为早期标注 `—`），与「采集环境属性」表「采集日期」行口径一致。
- **测试**：`test_test_runner_doc_writer.py` 新增 `test_duration_update_time_row_matches_machine_date`（换机采集日期不同 → 数据更新时间行随本机列更新），并在既有同列更新/新列追加两例断言数据更新时间行回填；test-coverage.md 计数同步刷新（unit 4721 / standard 4114 / verify 3065 / dev-verify 1747 / all 5030 / unit_scripts 162 / unit_llm 736）。
- **门禁**：dev-verify 1747 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### test-coverage 环境耗时对照表移除「旧慢笔记本」列

- **变更**：test-coverage.md 两张表（采集环境属性 / 各模式耗时对照）删除「旧慢笔记本（早期标注）」列，仅保留 dragonball 与 stallman-NB1 两台已实测机器列（均 2026-08-05 采集）；正文随列删除同步修正——对照说明改为「两台已实测机器」、跨机器采集注去除「旧机器标注列不受影响」、两机差距注按 dragonball vs stallman-NB1 重述（多数模式约 10~20 倍）并补充 stallman-NB1 worker=4。
- **验证**：`--update-docs` 写入器对 2 列表格 round-trip 正常（不重写历史列、不引入列宽异常）；check-doc-traces / check-task-numbering / check-code-traces `--ci` 全 [OK]，doc_writer + machine_info 测试 41 passed。

### README 开发者参考补充跨机器测试耗时采集说明

- **更新**：README.md「如何测试我的代码」行描述补「跨机器耗时采集与环境耗时对照」，开发者参考表后新增注——`python scripts/test_runner.py --mode bench --update-docs`（隐含 `--machine-info`）一键采集本机 14 项环境属性并自动回填 test-coverage.md 环境耗时对照表（按主机名匹配/新增列，显式传入才写文档），与 how-to-test-my-code.md / scripts-reference.md 口径一致。
- **门禁**：check-version-consistency 13 项 [OK] + 3 check 脚本 `--ci` 全通过。

### 历史记录归档（review-findings + changelog，v0.10.5 已发布记录迁入归档）

- **changelog 归档**：`docs-stm/managements/changelog.md` 中 v0.10.5 已发布版本段整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（涵盖版本更新为 v0.10.1 ~ v0.10.5）；`changelog.md` 保留 v0.10.6 发布段 + 归档列表（v0.10.x 链接更新）。
- **review-findings 归档**：`docs-stm/managements/review-findings.md` 已修复摘要中 v0.10.5/v0.10.6 已修复 rf 记录迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md`。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]；版本号全链一致 v0.10.6。

---

## [0.10.7] - 2026-08-05

### 测试可移植性修复：指标熔断持久化路径断言兼容 Windows 路径分隔符

- **动机**：`test_circuit_breaker_wrapper.py` 的 `test_default_path_under_state_dir` 用硬编码正斜杠子串 `data/state/metrics_breaker.json` 对实际路径做 `in` 匹配——Linux 下 `tmp_path` 为正斜杠路径恰好命中，Windows 下为反斜杠路径断言落空，导致 Windows 平台 dev-verify 单点失败。
- **修复**：断言前将实际路径分隔符统一规范化为 `/`（`path.replace(os.sep, "/")`）再匹配，正向/负向两条断言同时修正；源码（`os.path.join`）与 conftest 隔离（`tmp_path / ...`）本就 OS 感知，无需改动。
- **测试**：`test_circuit_breaker_wrapper.py` 10 项全通过；额外以 Windows 反斜杠路径字面量模拟验证规范化逻辑通过。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 语义命名索引双向校验（check-semantic-index.py + 功能语义命名表存量修正 + 架构约束参照）

- **动机**：「功能语义命名表」（技术设计文档中「代码标识符 = 文档中文描述」的唯一现状基准）此前是「记录性活索引」而非自动约束——`check-code-traces.py` 只做负面禁止（禁任务代号/魔法编号），**不校验正面一致性**：新增 `report_submodules.*` 开关键可绕过登记、功能删除后表行可残留僵尸条目、合并章 sheet key 无人核实。预演审计实证漂移：`cost_lots` 未登记（表内成本流水此前由 `fund_flow`/`dividend_flow` 覆盖）、`dividend_flow`/`holding_diagnosis` 为僵尸条目。
- **存量修正（技术设计文档）**：表与代码对齐——`cost_lots` 补登记（`report_submodules.cost_lots`，默认关）、移除僵尸条目 `dividend_flow`/`holding_diagnosis`（并入说明注明其并入归属）、合并章 sheet key 三枚（`position_relationship`/`portfolio_history_drawdown`/`style_factor`）核实均存在于 `registry._REPORT_SECTION_DEFAULT`；表体包裹 `<!-- semantic-index:start/end -->` HTML 标记供脚本定位（与 check-version-consistency / test_runner 文档写入器同款标记习语）。
- **新增 `check-semantic-index.py`**（独立脚本，正面校验，与 check-code-traces 负面禁止互补）：正向——`_config_defaults.py` 中 `report_submodules` 各键须在「功能语义命名表」中登记（表外键报错）；反向——表中每个语义 slug 在 `src/python` 至少一处非注释代码引用（防僵尸条目，tokenize 剔除注释）；合并章——注声明 sheet key 须在 registry 中存在。退出码 0/2，`--ci` 只输出违规。
- **纪律升级为架构约束参照**：技术设计文档「架构设计约束」章节开头新增「约束外参照（语义命名纪律）」——除该章节编号约束外，语义命名纪律以「功能语义命名表」为唯一现状基准、由双脚本强制；表所在章节的纪律行同步指向该参照。**不新增约束编号**：语义命名纪律以「约束外参照」形式并入，避免扩充约束编号集合，从而无需波及 check-code-traces 的约束代号边界匹配与其边界测试。
- **门禁接入**：CLAUDE.md 提交前（P0）/发布前（P2）门禁、testplan.md 回归门禁清单增补 `check-semantic-index.py --ci`；scripts-reference.md 一览表 + 详细章节、folders.md 目录树与统计同步。
- **测试**：`test_check_semantic_index.py` 24 项（标记区间提取/表行解析/合并章 key 解析/权威源 ast/注释剔除/反向存在性/run_checks 三向/真实仓库冒烟），全部通过；新增脚本自身通过 check-code-traces --ci 自检。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 文档内容修正（菜单 P 章节组 / enable_action 配置入口 / 场内场外识别描述 / 注册表使用说明）

- **菜单 P 章节组修正**：`faq.md` 菜单 P 可配置章节组由「三个」修正为「四个」（基金深度分析/市场新闻/历史走势/组合演进），并补充「组合演进」对应 `enable_portfolio_evolution` 开关；`how-to-config.md` 同步修正——`enable_action` 无菜单入口（需手动编辑 `config.json`），菜单 P 仅配置其余 4 个章节组可见性。
- **场内/场外识别描述修正**：`reports-instruction.md` 移除「F 开头标记场外基金」的错误描述，改为程序自动识别规则（账户渠道/名称关键词/代码前缀三要素联合判定，QDII 单独分类，识别结果以取价方式列颜色区分），与实际 `market_value.py` 分类逻辑一致。
- **注册表使用说明修正（`how-to-use-registry.md`）**：① 注册表结构表移除已并入「持仓关系矩阵」的缓存模块 `fund_overlap`（`_MODULE_REGISTRY` 中已删除），TTL 由「24h~7d」修正为「24h」；②「无需手动维护的派生产出」误称报表页签标题/Excel 标签随 `_MODULE_REGISTRY` 自动派生——实际由独立 `_REPORT_SECTION_DEFAULT` 注册表驱动，改为说明注释；③「计算模块注册表」交叉引用去掉裸 `§` 符号，改文字指引；④ 计算模块表 `量化指标` 名称对齐代码 `量化指标计算`。**同步清理**：`how-to-config.md` 缓存 TTL 表移除同源失效行 `fund_overlap`（模块已删除）。
- **测试**：纯文档修正，无代码变更。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 调仓建议可行化层区分场内/场外渠道

- **动机**：调仓建议可行化层（`analysis/rebalance_advisor`）此前仅凭代码前缀 + 名称关键词判定证券类型，场外持有基金（LOF/开放式指数基金，如 `161725 招商中证白酒指数A`、`110022 易方达消费行业`）的 16/11 开头代码命中场内基金前缀，被误当场内处理（100 份取整 + 仅计佣金），漏计赎回费且份额取整过粗。
- **持仓明细携带渠道上下文**：`holdings_details` 契约（`orchestrator.prepare_report_data` 与 `_report_generation` both 路径 `_both_action_holdings_details`）新增 `channel` 字段，按账户关键词 `is_offsite_fund(account)` 判定填充（`"场外"`/`"场内"`）；`getattr` 兼容缺 `account` 的 detail 对象（测试 fixture 简化版）。
- **可行化层按渠道消费**：`_round_to_lot`/`estimate_fee` 新增 `channel` 参数——`channel="场外"` 强制整数份取整 + 计收赎回费；非场外回退既有证券类型判定（A 股印花税 / 场内基金仅佣金 / 100 份取整），避免用单一渠道覆盖 A 股印花税等差异化费率。显式 `channel` 优先，其次按 `account` 关键词判定，两者皆无保持向后兼容。候选构造（再平衡/纪律）携带渠道到可行化层。
- **测试**：`test_rebalance_advisor.py` 新增渠道感知 10 项（场外 LOF/开放式基金整数份 + 赎回费、场内 ETF 100 份 + 仅佣金、A 股渠道仍计印花税、显式 channel 优先于 account、账户关键词回退、无渠道回退代码判定）；`test_orchestrator.py` 新增契约 channel 字段 2 项（场内/场外账户各一）+ both 路径 channel 接线 1 项。
- **门禁**：dev-verify 1820 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 再平衡信号配置化阈值 + 静默期 + 回撤纪律峰值注入 + 日收益口径统一（第四批）

- **再平衡信号配置化阈值 + 静默期**：`analysis/simple_rebalance` 的再平衡阈值与静默期由硬编码改为配置化参数（`threshold`/`silence_days`/`silence_file`），与纪律层共用 `_silence.py` 静默机制；智囊团深度复盘「行动摘要」的 LLM 段**豁免静默期**（`prompts_core` 以 `silence_days=0` 调用），保证每次复盘完整呈现超限信号、不被静默窗口抑制；新增回归验证 LLM 段不写共享静默文件。
- **回撤纪律管线注入组合历史峰值市值**：组合级回撤纪律此前在生产路径**从未激活**——`build_action_data` 的两处调用（`orchestrator.prepare_report_data`、`_report_generation` both 路径）均未传 `portfolio_peak_mv`，而峰值只能从 `history_data.bars` 计算且晚于 action_data 构建。修复：新增 `metrics.compute_portfolio_peak_mv(bars)` 计算历史峰值；both 路径将 action_data 构建移至「3. 历史走势」之后并注入峰值；full 路径在 `_prepare_full_risk_metrics` 后重建 action_data 并覆盖 prep/pipeline_data；新增 `persist_silence` 参数使 `prepare_report_data` 的中间占位构建不读写纪律静默文件，保证峰值就绪后的最终构建为管线中纪律静默的唯一写入方（单品信号不被占位构建抢占静默而误抑制）。
- **日收益口径统一**：`metrics.compute_daily_returns` 成为 tail_risk 与组合走势表共用的单一口径源（prev 与 curr 市值均 >0 才计入，跳过缺失/占位/清仓的伪 -100% 单日）；`tail_risk` 与 `portfolio_history` 均委托之，VaR/最大单日跌幅/年化波动率与走势表日收益完全一致。
- **测试**：新增组合峰值市值计算 4 项、`persist_silence=False` 不读写静默文件 1 项、both/full 路径峰值注入接线 3 项（含历史走势关闭时峰值取 None 的降级路径）。
- **门禁**：dev-verify 1810 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 统一熔断网关 + 指标熔断状态文件落盘位置修正 + 菜单 [1] 基础缓存刷新补齐

- **统一熔断网关（三路聚合）**：`CircuitBreakerGateway` 将数据源熔断（DataSourceRegistry）、LLM 端点熔断、指标熔断（IndicatorBreaker）三路状态聚合到统一查询入口——`gateway.get("data_source"/"indicator"/"llm")`、`gateway.summary()`，并新增模块级 `get_indicator_breaker_status()`/`get_all_breaker_status()` 包装函数。`technical.md` §2.2「统一熔断网关」段落同步更新为三路聚合描述。
- **指标熔断状态文件落盘位置修正**：指标熔断器持久化文件从 `data/cache/metrics_breaker.json` 调整至 `data/state/metrics_breaker.json`（运行时状态目录），旧路径文件在首次加载时自动改写至新位置并删除旧文件，避免被缓存清理误扫。`technical.md` §2.2 持久化列与 `datasource-reliability.md` §4.1 同步更新。
- **菜单 [1] 更新基础类缓存补齐**：新增三项刷新——财经新闻（持仓关键词聚合预热 `news_` 缓存）、基金经理（逐基金刷新 `fund_manager_` 缓存）、基金风格扩展（A 股扩展数据预取到 registry 会话缓存）；同时补齐有基金路径此前缺失的行业分类、分红刷新。纯股票组合路径同样刷新新闻与风格扩展。`how-to-menu.md` 菜单 [1] 说明同步更新。
- **测试**：新增统一熔断网关 12 项、指标熔断持久化路径 3 项、菜单 [1] 扩展缓存刷新 19 项（新闻/基金经理/风格扩展 helper + 并行编排 + update_basic_cache 两分支接线 + 显示三行输出）。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 基金业绩评级类型差异化阈值接线

- **动机**：`tiantian_ranking` 已定义四组类型差异化评级阈值（默认/债券/指数/QDII）与类型提示参数，但 `fetch_fund_rankings` 调用评级计算时未传类型，导致债券型/QDII 的宽松阈值与指数型的严格阈值**从未生效**，所有基金均按主动权益默认阈值评级。
- **接线**：新增 `_fund_type_hint_from_name(name)`——按基金名称推导阈值类型键（优先级：QDII/隐式海外 → 债券型 → 指数/ETF/联接 → 默认，与穿透分类 `classify_penetration` 一致）；`fetch_fund_rankings` 从 JS `fS_name` 提取名称后推导类型，透传至 `_calc_rating_from_entry`，并在返回结构 `type` 字段回填类型键（此前恒为 `""`）。调用链（fetcher 包装、报告、缓存刷新、候选比较）零签名变更。
- **行为影响**：债券型/QDII 在 10~15% 百分位区间由「良好」升至「优秀」，指数型在 25~30% 区间由「良好」降为「稳定」，评级与「类型」列展示的基金分类口径一致。
- **文档**：`requirements.md` §6.4.5 基金业绩分析补充类型差异化评级阈值表。
- **测试**：`test_tiantian.py` 新增类型推导 9 项 + `fetch_fund_rankings` 接线 6 项（mock `_request_pingzhong_data`，覆盖债券/指数/QDII/主动权益四类阈值生效与无排名数据回退）。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

---

## [0.10.8] - 2026-08-06

### 超限文件拆分：报告生成 / HTML 写入 / 量化指标 / 报告编排 四个 >800 行文件 facade 化

- **动机**：自审核查（review-findings rf-234/rf-235/rf-236/rf-237）发现四源文件超过 800 行硬性上限——`report/_report_generation.py`（1018）、`report/html_writer.py`（934）、`analysis/metrics.py`（880）、`report/orchestrator.py`（822）。大量测试直接 `patch` 原模块路径（如 `html_writer._ENV`、`_report_generation._spawn_health_checks`、`orchestrator._fetch_valuation_for_code`），整体搬迁会破坏 mock 接线。
- **方案**：facade 聚合门面拆分——函数体物理移动到语义子模块，原模块保留关键入口并 re-export 全部符号，所有外部引用（生产代码 + 测试）零改动。
  - `report/_report_generation.py`（686）：后台健康检查→`_report_health.py`（`_spawn_health_checks`/`_collect_health_checks`）、轻量行情/演进与快照差异注入/完整性校验/both 明细子集→`_report_helpers.py`（`_compute_details`/`_inject_evolution_data`/`_inject_snapshot_diff_data`/`_validate_prep_completeness`/`_validate_pipeline_snapshot`/`_both_action_holdings_details`）、full 路径全量量化指标装配→`_full_risk_metrics.py`（`_prepare_full_risk_metrics`）、Chart.js 数据集构建→`_chart_dataset_factory.py`（`_build_chart_datasets_for_report`）。门面保留 both/full 双路径生成编排（`_generate_report_both`/`_generate_report_full`/`_generate_full_html_report`/`_generate_full_excel_report`），确保 `patch("_report_generation._spawn_health_checks")` 等接线继续生效。
  - `report/html_writer.py`（660）：章节可见性/目录分组导航→`html_writer_nav.py`（`_compute_section_visibility`/`_build_section_nav_groups`/`_LLM_SUPPORTED_SECTIONS`）、数据契约展示映射→`html_writer_display.py`（`_build_flow_display`/`_build_temperature_display`/`_attach_valuation_to_penetration`）、Chart.js JS 资产复制→`html_writer_assets.py`（`_copy_js_assets`）。门面保留 `write_html_report`/`_render_template` 及全部顶部 import（`_ENV`/`build_*_data_status`），mock 路径不变。
  - `analysis/metrics.py`（225）：收益/清理类指标→`metrics_returns.py`（`compute_daily_returns`/`sanitize_metric`/`sharpe_ratio`/`calmar_ratio`/`max_drawdown_pct` 等 10 函数）、风险/持仓类指标→`metrics_risk.py`（`hhi`/`win_rate`/`risk_contribution`/`portfolio_beta` 等 8 函数）。门面保留 `compute_all_metrics` 聚合入口 + `__all__` + 4 常量 + `_math_utils` 符号再导出（测试引用 `_t_critical_95`/`_t_cdf`）；子模块维持 analysis 层单向依赖约束（不导入 report/）。
  - `report/orchestrator.py`（442）：风格因子/行业 Beta 计算族→`_report_factor_metrics.py`（持仓 K 线路由 `_fetch_holding_bars` + 因子回归 `compute_factor_exposure_data` + 行业 Beta `compute_industry_beta_data`）、市场温度/持仓相关性→`_report_aux_metrics.py`（`compute_market_temperature_data`/`compute_correlation_data`）。门面保留 `generate_report`/`prepare_report_data`/`compute_valuation_data`/`_fetch_valuation_for_code`——估值族因测试 `patch("orchestrator._fetch_valuation_for_code")` 依赖门面命名空间解析，留在门面（docstring 注明原因），确保 patch 接线继续生效。
  - `llm/generators_orchestrator.py`（698，rf-238）：facade 聚合门面拆分——新闻关联责任单元（模块级结果缓存 `_store_news_correlation_result`/`get_news_correlation_result`、闭包 `_make_news_correlation_closure`、安全直调 `run_news_correlation_safe`）→`_llm_news_correlation.py`（161）。门面保留缓存预检（`_compute_module_cache_info`/`_precheck_*`）、worker 分发（`_dispatch_llm_workers`/`_build_module_fns`）与主编排入口 `generate_all_llm`，re-export 子模块符号，mock patch 接线零改动。
- **语义命名**：新子模块全部语义命名（metrics_returns/metrics_risk/html_writer_nav/html_writer_display/html_writer_assets/_report_health/_report_helpers/_full_risk_metrics/_chart_dataset_factory/_report_factor_metrics/_report_aux_metrics/_llm_news_correlation），无任务代号扩散到实现层；子模块 docstring 不含任务编号。
- **文档同步**：`folders.md` 目录树登记 12 个新文件（四文件拆分 11 个 + `_llm_news_correlation.py`）+ 项目统计表刷新（主程序 222→234 文件、55,823→56,189 行）；review-findings 五条已修复项（rf-234~238）迁入「已修复（摘要）」。
- **测试**：dev-verify 1846 passed；report 全量单测 1479 + metrics 94 通过；`test_valuation_temperature_wiring.py`/`test_pipeline_style_factor_regression.py`/`test_pipeline_smoke.py`/`test_cli*.py`/`test_cli_integration.py` 97 项通过。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 15 文件已格式化。

---

---

## [0.10.9] - 2026-08-06

### LLM 空响应安全网扩展（关闭 thinking 重试 + thinking 并发信号量）

- **空内容诊断增强**：`llm/api_base.py::_extract_content` 空 content 诊断日志补充响应细节（stop_reason / block 结构 / HTTP 状态），出现 HTTP 200 + 空正文时可快速定位是 thinking 耗尽还是端点偶发异常。
- **安全网覆盖范围扩展**：DeepSeek 等强制推理模型在 `payload` 未显式携带 thinking 参数时也会落入默认思考模式（effort=high）占满 `max_tokens`，导致 `stop_reason=max_tokens` 无正文。`_api_claude.py` 安全网触发条件由「显式 thinking + 思考耗尽」放宽到「强制推理模型（`_is_effort_model`）或思考耗尽」；重试 payload 显式 `thinking.type=disabled` 并移除互斥参数（output_config / reasoning_effort），避免重试再次触发思考。
- **thinking 并发信号量**：`generators_orchestrator.py` 新增 `llm_max_thinking_concurrency`（默认 1）BoundedSemaphore，约束开启 Extended Thinking 的模块（health_check / expert_review 等 `thinking_enabled_{suffix}=true`）同时最多 N 个在跑，从源头降低多 thinking 模块并发涌向 DeepSeek 时偶发空 content（HTTP 200 空响应）的概率；非 thinking 模块不受此限，总并发仍受 `llm_max_concurrency` 约束。新键登记至 registry `get_known_llm_settings_keys()`，默认模板 `_llm_settings_defaults.py` 同步生成。
- **配置同步**：`data/config/llm_settings.json` 全局设置区补 `llm_max_thinking_concurrency: 1`；how-to-config-llm.md（全局配置 8 项说明 + 完整范例）、requirements.md（全局配置参数表）、llm-technical.md（全局键名清单 + 4.2 并发控制段落）、testplan.md（llm/ 包覆盖描述补 thinking 并发信号量）同步。
- **测试**：test_llm_api.py 新增强制推理模型空 content 关闭 thinking 重试用例；test_generate_all_llm.py 新增 `TestThinkingConcurrencyLimit`（thinking 模块串行/非 thinking 不受限/总并发不超限）；test_llm_api_base_edge.py 空 content 诊断断言；test_registry.py `test_llm_settings_keys_count` 断言由 86 更新为 87（新增全局键）。LLM 测试全部 mock `call_llm` / `call_llm_with_retry` / `make_http_client`，无真实 API 调用。
- **门禁**：dev-verify 1862 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 报告子模块无候选/无数据时页面提示 + data_quality 缺省开启（rf-247）

- **候选基金无配置提示**：`candidate_compare` 子模块开启但 `config.comparison_candidates` 未配置（或全部代码非法）时，原先 HTML 端静默跳过候选基金比较区块、Excel 端静默不写，用户无从判断原因。现在 HTML 模板（report_template.html）外层守卫改为 `{% if candidate_data %}` + 内部 `available` 分支，无候选时渲染「📭 未配置候选基金（config.comparison_candidates 为空），无法输出候选基金比较…」占位（含被忽略的非法代码列表）；Excel 端新增 `_write_candidate_unavailable_block`（标题 + `_write_placeholder` 占位）；`html_renderers.py` 同步 `prog.warn` 提示。
- **成本流水无数据提示**：`cost_lots` 子模块开启但持仓 Excel 未录入交易/分红流水时，HTML 端盈亏汇总区补「成本流水子模块已开启，但持仓 Excel 未录入交易/分红流水，资金加权收益率 (XIRR)、成本分档、分红累计无法计算」提示（Excel 端 summary.py 已有占位，本次对齐 HTML 端）。
- **data_quality 缺省开启**：`report_submodules.data_quality` 默认值由 `false` 改为 `true`（数据质量仪表盘 = 品种覆盖 + 可信度，属长期可信核心，开箱即得）；访问器 `is_enable_data_quality` 兜底逻辑（report_submodules 缺失/非 dict/data_quality 键缺失）同步改为缺省 `true`，与 `enable_action` 缺省开启口径一致；配置生成模板注释同步。
- **文档同步**：how-to-config.md（示例配置 + 参数表默认值）、how-to-menu.md（子模块默认说明）、requirements.md（`report_submodules` 默认值）、technical.md（功能语义命名表 data_quality 行默认开）、reports-instruction.md（候选基金比较子表补充「无候选时占位提示」行为说明）、test-coverage.md + folders.md（测试计数快照刷新：`all` 5,146→5,196、dev-verify 1,846→1,864）。
- **测试**：test_fund_performance.py 新增 `TestWriteCandidateUnavailableBlock` 2 用例（无候选写占位 / 占位列出非法代码）；test_html_writer.py 候选基金无候选渲染拆 3 例（None 不渲染 / available=False 显示未配置提示 / invalid 列表显示）+ 成本流水空数据提示 2 例；test_config.py `TestIsEnableDataQuality` 重写为默认 true + 新增 `_DEFAULT_CONFIG` 断言；test_handlers_config.py 数据质量默认开（toggle 测试改关）。
- **门禁**：定向 250 passed；dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 历史走势默认自动获取 + 关闭时醒目警示（rf-245）

- **警示修复**：`fetch_history=False`（历史走势关闭/跳过）时原先静默返回 `None`，下游只剩误导性的「尾部风险：无历史 bars」占位警告，用户无法判断是配置关闭所致。现在 `report/_snapshot.py::fetch_history_data` 在 fetch 关闭时通过 `reporter.warn`（[!] 黄色）+ `logger.warning` 醒目提示「组合历史走势获取已跳过（history off）」及占位后果（历史走势/回撤章节、尾部风险指标、累计收益率等显示"数据不可用"），并提示开启方式（CLI `--history auto`）。
- **默认值调整**：CLI `--history` 默认值由 `off`（跳过）改为跟随配置层——未显式传参时 `generate_report` 按 `config.history.fetch_mode`（`off`/`auto`/`prompt`，默认 `auto`）决定是否获取。`auto`/`prompt` 均视为获取（prompt 为 TUI 交互询问，CLI 非交互场景按获取处理），仅 `off` 跳过。config.json 默认 `fetch_mode="auto"` 不变，新用户开箱即获取组合历史走势。
- **影响**：`both`/`full` 报告默认包含组合历史走势/回撤、尾部风险、累计收益率等数据（原来默认占位）；`--history off` 可显式跳过。包装脚本（`cli.sh`/`cli.ps1`）无参数默认 both 同样受益。
- **文档同步**：how-to-start.md（`--history` 参数表默认说明 + 报告类型段落）、cli.sh/cli.ps1 头部注释（历史走势默认 auto 获取）。
- **测试**：`test_orchestrator.py` 新增 `test_generate_report_both_fetch_history_follows_config`（配置驱动解析 off/auto/缺失三态）+ `test_fetch_history_data_fetch_false` 增加警示断言；`test_cli.py` 默认断言更新（`--history` 未传 → None）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### Excel 序号收敛到导航层（页签栏 + HTML 标题）（rf-244）

- **设计调整**：序号只在 Excel 页签栏 tab 名与 HTML 章节标题出现，Excel 正文标题统一为纯中文名（与投资组合概要/市值/分类/穿透/基金业绩/数据源可用性矩阵一致）。撤除 rf-243 引入的正文标题序号同步机制（`get_report_section_number_from_order`、create_sheets 的 `visible_number` 标记、7 个页签写入函数的 `section_order` 透传），回归更简设计——正文不依赖序号，调整配置/隐藏章节不会错位。
- **效果**：Excel 页签栏保留连续序号（行动建议=10、组合演进=13、数据源可用性矩阵=14），正文标题为「行动建议」「组合演进」「数据源可用性矩阵」纯中文名；HTML 章节标题保留序号。
- **测试**：test_correlation_sheet 正文标题断言更新为纯中文名；191 受影响单测 + dev-verify 1864 passed；4 项 trace `--ci` 全 [OK]。

### cli.ps1 补 UTF-8 BOM，修复 Windows PowerShell 中文解析崩溃（rf-246）

- **缺陷**：`scripts/cli.ps1` 文件头注释声称 "Encoding: UTF-8 with BOM"，实际文件**无 BOM**。Windows PowerShell 5.1 对无 BOM 的 UTF-8 中文按 ANSI/GBK 误读，导致中文注释解析崩溃（"字符串缺少终止符" / "语句块或类型定义中缺少右}"），跨机器复现（另一台电脑运行同样报错）。
- **修复**：补回 BOM（`EF BB BF`，UTF-8 + CRLF），PowerShell Parser 验证通过（`[System.Management.Automation.Language.Parser]::ParseFile` 无 errors）。
- **编码纪律落盘**：CLAUDE.md 技术要点新增「编码/BOM（Windows 脚本）」条目——`*.ps1` 必须 UTF-8 BOM + CRLF，否则 PS 5.1 按 GBK 误读崩溃；新增 `.editorconfig`（`[*.ps1] charset = utf-8-bom, end_of_line = crlf`），支持 EditorConfig 的编辑器**跨机器自动遵守**，避免此问题在其他电脑复发。
- **文档同步**：folders.md 目录树登记 `.editorconfig`。
- **验证**：BOM 字节（`ef bb bf`）+ PowerShell 解析器双重确认；CLI 包装脚本功能不受影响。

### Excel 正文标题序号跟随报告章节顺序配置（rf-243）

- **缺陷**：`report_section_order` 配置生效后，Excel 页签栏 tab 名按 create_sheets 可见连续序号重编号（行动建议=10、组合演进=13、数据源可用性矩阵=14），但 7 个深度分析页签（行动建议/组合演进/基金经理变更/持仓集中度/持仓关系矩阵/风格与因子/组合历史走势回撤）正文标题仍用注册表默认序号（行动建议=17、组合演进=16），与页签栏不一致。
- **修复**：create_sheets 创建页签时就地标记 `visible_number`（与 tab 名同源）；registry 新增 `get_report_section_number_from_order`，正文标题按「可见连续序号 → 配置序号 → 注册表默认」取值；7 个页签写入函数新增 `section_order` 参数，excel_generator / excel_fund_deep_analysis 透传配置后 order。正文标题与页签栏序号现完全一致。
- **说明**：该方案随后被 rf-244 设计调整取代——正文标题统一为纯中文名，序号仅收敛到导航层，本条目保留作过程记录。

### 报告页签显示顺序配置（行动建议提前至第 10 位）

- **配置**：`config.json` 的 `report_section_order` 由 `{}`（使用注册表默认）改为**完整配置 18 项**——`action`（行动建议）置于序号 10，原 10-16 依次顺延（`news_correlation`=11、`global_macro`=12、`expert_review`=13、`health_check`=14、`penetration_deep`=15、`portfolio_history_drawdown`=16、`portfolio_evolution`=17），`data_source_status`=18，`llm_usage` 强制末位。注册表默认值（行动建议=17）未改，清空该字段即恢复默认。
- **效果**：Excel 页签与 HTML 章节顺序/标题编号同步变化——行动建议提前至第 10 位，财经新闻/全球政经/智囊团/持仓体检/穿透深度/组合历史走势/组合演进依次顺延；数据源可用性矩阵编号不变（both 模式 14、full 模式 18）。
- **文档同步**：reports-instruction.md（主表 + 分组表重排）、requirements.md（§6.3 表 + §6.4.x 小节物理重排与重编号）、how-to-config.md（默认序号表后补本仓库配置说明）、technical.md（注册表 number 描述两处补配置说明）、faq.md（§13 智囊团引用）。
- **门禁**：dev-verify 1864 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。注册表默认值未改，test_registry 等断言不受影响。

### 行动建议章节默认开启 + 菜单 P 可视化开关

- **默认值调整**：`enable_action` 由默认关闭改为**默认开启**——`_config_defaults._DEFAULT_CONFIG["enable_action"]=True`；`get_config()` 合并逻辑以默认值打底，现有用户 config.json 缺失该键时自动补为开启（显式 `false` 的用户保持关闭）。访问器 `is_enable_action()` 缺失时返回 True，日志提示「缺少 enable_action，使用默认值 true」。
- **菜单 P 新增开关**：TUI 菜单 `[P] 配置报告可选章节` 面板新增第 5 项「行动建议（再平衡信号/交易纪律/调仓建议/收益归因）」，与既有 4 个章节组一致地交互切换；LLM 分析章节提示顺延为第 6 项。菜单 P 主菜单 label 同步加入「行动建议」。
- **行为影响**：开启后 E/B/L 报告均输出行动建议章（number=17，type=action）；关闭时章节隐藏且智囊团深度复盘隐藏「行动摘要」子块，剩余章节自动连续编号。
- **文档同步**：how-to-config.md（默认值表/章节可见性表/菜单归属/章节对照 5 处）、how-to-menu.md（主菜单 label/脚注/章节说明/菜单 P 详解 4 处）、faq.md、how-to-use-registry.md、requirements.md、reports-instruction.md、technical.md 全文「默认关」→「默认开，菜单 P 可切换」。
- **测试**：`TestIsEnableAction` 新增 `test_default_config_says_enabled`（断言 `_DEFAULT_CONFIG["enable_action"]` 为 True）；`test_default_true_when_missing` 保持缺失→True；test_registry/test_action_html/test_report_chapter_consistency 注释同步。
- **门禁**：dev-verify 1846 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 事实校验两处误修正修复（rf-239）

- **缺陷 1：名称指代主体定位平局误路由**。真实报告「止盈纪律」句「建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%」中，171.23% 被误修正为 70.2%（601398 工商银行收益率）——`_locate_subject_code` 名称分支用起点距离 `abs(idx-anchor)`，建设银行(idx=0)与工商银行(idx=16)距 anchor=8 平局，先迭代者（工商银行）胜出，把 601939 的**正确** 171.23% 判错并改写。修复：名称分支改用**最近边距离** `min(abs(idx-anchor), abs(idx+len(name)-anchor))`，与代码分支一致，紧邻数值的名称唯一胜出。
- **缺陷 2：风险警戒阈值误修正**。同句「设立止损线：当前亏损-11.80%，已接近回调20%的警戒区域」中，「回调20%」是止损警戒阈值而非收益率声称（实际 -11.80% 同句另述且正确），却被误修正为 -11.8%（159222）。修复：`_is_trim_target_context` 增加警戒阈值检测——新增 `_WARNING_THRESHOLD_KEYWORDS=("警戒",)`，数值前后更宽窗口（-25/+8）内出现警戒词即判定为风控阈值，跳过收益率比较。
- **测试**：新增 `TestNameSubjectNearestEdge`（3 用例）+ `TestWarningThresholdContext`（3 用例）回归测试，修复前均失败；fact_checker 单文件 109 通过；完整合成稿+真实持仓端到端复现 corrections 由 2 处降为 0。
- **门禁**：fact_checker 单文件 109 passed（未跑全量，用户要求最小验证）。

### 菜单 P 新增报告增强子模块配置（6 项区块级开关）

- **新增访问器**：`config.is_enable_industry_beta()` 读取 `report_submodules.industry_beta`——与 data_quality / candidate_compare / cost_lots / valuation_percentile / market_temperature 五个既有访问器一致，导出至 `src.python.config`。
- **菜单 P 子菜单**：TUI 菜单 `[P] 配置报告可选章节` 新增第 6 项「报告增强子模块」，进入子菜单逐项切换 6 项区块级开关（数据质量仪表盘 / 行业Beta子表 / 候选基金比较子表 / 成本流水 / 估值分位 / 市场温度，默认全关），实时保存到 `report_submodules`；LLM 分析章节提示顺延为第 7 项。菜单 P 主菜单 label 同步加入「报告增强子模块」。
- **文档同步**：how-to-menu.md（主菜单 label / 菜单 P 详解）、how-to-config.md（6 行 report_submodules 配置方式 手动编辑 → 菜单 P → 6）。
- **测试**：`TestIsEnableIndustryBeta`（5 用例）+ `TestConfigReportSubmodules`（4 用例，mock 输入/配置读写），定向 13 passed（本机慢，全套在另一台电脑运行）。

### 测试污染真实快照目录修复（rf-240）

- **缺陷**：`test_corrupt_snapshot_file_skipped` 用 `from src.python.core.constants import HISTORY_SNAPSHOT_DIR` 在 import 时把快照目录**旧值**拷贝进测试模块，绕过 conftest `_isolate_sensitive_paths` 的 monkeypatch 隔离，把测试用损坏文件 `snapshot_corrupt.json` 写入**真实** `data/history/snapshots/`。后果：每次生成报告时 `[WARNING] 文件损坏 snapshot_corrupt.json`（程序自动跳过，不阻塞报告，但持续刷日志），且跨机器残留（另一台电脑运行过测试即同样产生）。
- **修复**：测试文件改用 `import src.python.core.constants as core_constants` 模块属性访问 `core_constants.HISTORY_SNAPSHOT_DIR`，使 conftest 隔离生效——损坏文件写入 `tmp_path` 而非真实目录。生产代码 `snapshot_diff.py` 经 `history_snapshot.load_all` 读取（模块属性引用）本就不受影响。
- **清理**：已删除本机残留的 `data/history/snapshots/snapshot_corrupt.json`（未跟踪的测试垃圾，非用户数据）。其他机器同样删除该文件即可。
- **回归验证**：edge 测试 6 passed，运行前后真实快照目录 diff 无新增残留。

### 数据质量仪表盘区块渲染崩溃修复（rf-241）

- **缺陷**：`report_template.html` 数据质量仪表盘「品种覆盖/可信度」区块中 `position_status.items` / `data_freshness.items` 在 Jinja2 命中 dict 内置 `items` 方法（bound method）而非契约键 `"items"`——`data_quality` 子模块开启且契约有数据时，guard 恒真，`{% for item in ... %}` 迭代 bound method → `TypeError: 'builtin_function_or_method' object is not iterable`，HTML 报告生成失败（另一台电脑菜单 L 实测崩溃）。该缺陷自数据质量仪表盘引入（87a137a4）即存在，因 `data_quality` 默认关、既有测试未开启该子模块渲染模板而漏测。
- **修复**：guard 与循环改用 `.get("items")`（与生产代码 `data_freshness.get("items")` 一致）；空 items 时正确走降级占位「未获取行情数据，品种覆盖无法判定」而非进入空表。
- **回归**：新增 `TestHtmlDataQualityBlocks` 4 用例（品种覆盖渲染/可信度渲染/空 items 占位/data_quality 关闭跳过），修复前 `_render_template` 抛 TypeError。
- **门禁**：dev-verify 全量通过 + 4 个 trace 检查全 [OK]。

### 数据质量仪表盘测试覆盖补强

- **可信度（`test_data_freshness.py`）**：新增 dict 形式明细分类（`_detail_value` dict 分支）、跳变检测跳过无 code/None 明细、摘要未显式传交易日自动推断、昨收为 0 时 `change_pct` 记 0.0 不除零；新增 `_infer_latest_nav_date` 直接测试（取最新净值日期 / 忽略无效日期 / 无净值回退当天日期）。
- **品种覆盖（`test_holding_status.py`）**：新增大写 SH/SZ/BJ 交易所前缀归一、单字符简称不子串匹配、dict 形式明细标注、股票「暂无行情」判可能退市、同代码多条明细取首条（`setdefault` 语义）。
- **页签写入（`test_data_quality_sheet.py`）**：新增 `build_coverage_block` 全部正常 abnormal_count=0、契约 available=True 但缺 items 键容错。
- **HTML 渲染（`test_html_report_structure.py`）**：新增报告头部数据异常摘要告警行（异常时显示 summary + 章节号引用、正常时隐藏）与异常行 `src-matrix-failed`/正常行 `src-matrix-ok` 高亮断言。
- **门禁**：四文件 162 passed；dev-verify 1864 passed + 4 个 trace 检查全 [OK]；ruff format 已一致。

### 报告生成骨架测试污染真实 reports 目录修复（rf-242）

- **缺陷**：`src/test/unit/report/test_orchestrator.py::test_generate_report_skeleton` 用 `config={}` 真实调用 `generate_report(holdings=[], ...)`——report_type 默认 basic（仅生成 Excel 不写 HTML），且未 patch `generate_excel_report` 写盘函数。`output = output_dir or config.get("output_dir", "reports")` 在 `config={}` 时 fallback 到相对路径 `"reports"`，解析为真实 `reports/` 目录；空持仓每次生成一个空页签 Excel 归档（`reports/{YYYYMMDD}/个人投资分析报告-*.xlsx`）+ 覆盖根目录最新版，跨整天累积 37 个残留文件。该缺陷被 `result.excel_ok=True`/`report_generated=True` 断言掩盖（basic 路径正常返回成功），既有测试未校验输出目录隔离而漏测。
- **修复**：传入 `output_dir=tempfile.TemporaryDirectory()` 隔离输出到临时目录，保留真实生成流程（骨架返回 ReportResult 断言不变）。
- **清理**：删除 reports 目录下全部 37 个空页签归档 + 根目录空最新版（均已验证不含真实持仓数据，抽样 + 全量扫描 0 命中）。
- **回归验证**：重跑 `test_orchestrator.py`（50 passed）+ `--mode report` 全量（1488 passed）后 reports 目录零新增。

### 报告输出目录兜底防线（rf-242 加固）

- **新增 conftest autouse fixture**：`_isolate_report_output_dir` 统一安装，把两个真实落盘入口——`excel_writer.save_workbook`（`excel_module_loader` 运行时 `from ... import save_workbook` 取到被 patch 后的模块属性，报告链路天然覆盖）与 `html_save._save_html_report`/`html_writer._save_html_report`（模块级拷贝引用，两处一起 patch）——收到的输出目录解析后等于项目真实 `reports/` 时透明重定向到 `tmp_path/reports`。测试漏传输出目录（如 `generate_report` 在 config 缺 output_dir 时 fallback 到相对路径 `"reports"`）不再污染真实 reports 目录。判定基于绝对路径相等，显式指向临时目录的测试不受影响；测试自身 mock 写盘函数会覆盖本包装。
- **回归守护**：`test_generate_report_skeleton` 恢复为 `config={}` 不传 output_dir 的真实调用（复现缺陷场景），用运行前后 `reports/` 文件快照断言无新增，作永久回归守护——防线失效即测试失败。
- **验证**：test_orchestrator 50 passed；report 模式全量 1488 passed；dev-verify 1864 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致；全程 reports 目录零新增。

### CLI 命令行包装脚本（cli.sh / cli.ps1）

- **新增**：`scripts/cli.sh`（Linux/macOS）与 `scripts/cli.ps1`（Windows PowerShell）——CLI 命令行模式的便捷入口。**无参数调用时默认生成报告**；传入参数时原样透传给 CLI，与直调 `python -m src.python.cli <args>` 完全等效。
- **无参数默认类型**：`report --type both`（Excel+HTML 双格式、不含 LLM、全部页签有数据）——响应实测反馈：初始默认 basic（约 1 分钟仅 Excel）只生成核心 5 页签 + 数据源矩阵，新闻/历史/LLM 相关页签为降级占位，不符合"无参数=完整报告"预期，故改为 both。注意：这仅改变**包装脚本**的无参数默认；CLI 本身 `--type` 默认仍为 basic（直调 `python -m src.python.cli report` 不带 `--type` 仍是轻量模式）。
- **实现**：自动切换到项目根目录并定位虚拟环境解释器（`.venv/bin/python` / `.venv\Scripts\python.exe`），缺失时提示先运行 launch.sh / launch.ps1 初始化；创建基础数据目录（data/holdings、data/cache、data/config、docs-stm/tmp、logs）；退出码透传 CLI 结果（0=成功/1=部分失败/2=严重错误）。
- **文档同步**：folders.md 目录树登记两文件 + 统计表说明补充；scripts-reference.md 一览表与启动脚本章节新增两条（同时给出直调 python 与包装脚本两种调用方式，并说明包装脚本默认 both 与 CLI 默认 basic 的差异）；how-to-start.md CLI 模式一节补充「便捷入口」用法 + 三种报告类型差异说明。
- **验证**：both 模式实测 14 页签中 13 个有实质数据（仅组合历史走势因 `--history` 默认 off 为占位，加 `--history auto` 可得）；`--help`/`report --help`/`cache --help` 参数透传正常；bash -x 确认无参数 `set -- report --type both`；dev-verify 1864 passed + 4 个 trace 检查全 [OK]；运行期间 reports 目录零新增。

---

## [0.10.10] - 2026-08-06

### 六文档核对与 Web 模式文档补全（2026-08-06）

- **六文档核对结论**：how-to-start.md（方式四）/ README.md（功能特性）/ faq.md（Web 问答）已在 plan-8 阶段3 就绪；llm-technical.md 经核对**无需改动**——Web 复用 `report/orchestrator.py` → `llm/` 包，对 LLM 层零改动，与 CLI 一致不入该文档。
- **requirements.md**：§1.1 目标补三种入口（TUI/CLI/Web）共用同一套管线；§1.2 流程图后加入口共用说明（TUI E/B/L ↔ CLI `--type` ↔ Web 报告格式下拉）；§2 新增 R-ENV-04（`launch.sh/ps1 web` 启动 Web 模式）；§3 改「用户交互」+ 新增 3.4 Web 浏览器模式（R-WEB-01~07：启动/上传/格式与选项/进度事件/产物预览下载/单 worker 串行队列/生命周期管理）。
- **technical.md**：§1.1「双入口：TUI 与 CLI」改「三入口」，三入口对照表加 Web 行，共享模块/分层差异/关键分层原则文案同步（"消除 TUI、CLI 与 Web 间的逻辑重复"）；§1.2 报告类型表补 CLI/Web 触发说明；§1.3 模块职责总览加 Web 服务层 + Web 进度报告两行；§7 模块间依赖补 web/ 薄入口依赖块；附录 A 目录结构补 `src/python/web/` 全量条目。
- **how-to-test-my-code.md**：`unit_web` 标记补全——verify/dev-verify 的 `-m` 表达式（三处）加 `or unit_web`、「12 个子组」改「13 个子组」、dev-verify/verify 模块计数（5→6、8→9）、marker 参照表加 `unit_web` 行。
- **scripts-reference.md**：启动脚本一览表 `launch.sh/ps1` 行补 `web` 子命令说明；「启动脚本」章节新增 `launch.sh web / launch.ps1 web` 小节（默认 127.0.0.1:8000、--host/--port/--config、单 worker 串行队列说明）。
- **README.md**：启动方式新增「Web 浏览器模式」小节（`launch.sh web` / `launch.ps1 web`）。
- **技术债务登记（review-findings.md rf-256~258）**：rf-256 `output_dir` 锁文件检测未实现（设计规定 server 启动时检测输出目录占用并警告，实现仅端口探测）；rf-257 Web 浏览器真机人工验收未做（冒烟为脚本化 HTTP 验证 9/9 过，缺 Chrome/Edge 真机走查含 375px）；rf-258 Web 前端 main.js 无自动化测试、冒烟脚本未沉淀。rf-next 256→259。
- **门禁**：dev-verify 1917 passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

### plan-8 阶段1：轻量 Web UI 骨架 + 上传→生成→预览全链路（2026-08-06）

- **依赖接入**：`flask==3.1.2`（pyproject.toml + requirements.txt，锁 werkzeug 3.1.8 / itsdangerous 2.2.0 / click 8.4.2 / blinker 1.9.0）；`scripts/launch.sh` / `launch.ps1`（BOM 保留）增 `web` 入口参数，`launch.sh web` / `launch.ps1 web` 启动 Web 服务，其余参数透传。
- **`src/python/web/` 骨架**：`server.py`（sys.path 注入 + 端口占用检测 + app.run）、`app.py`（Flask 工厂：统一 JSON 错误处理 / request_id 访问日志 / 注入 run_manager）、`handlers.py`（页面/上传/生成/轮询/预览/下载/历史/健康路由）、`upload.py`（上传安全）、`progress.py`（WebProgressReporter 事件缓冲）、`runs.py`（RunManager 单 worker 串行队列 + run 状态/事件注册表）、`templates/index.html` + `static/main.js`/`style.css`（单页 UI，原生 ES6 无 innerHTML）。
- **全链路贯通**：上传持仓 Excel（`POST /api/upload`）→ 提交生成任务（`POST /api/runs`，单 worker 串行防产物覆盖）→ 轮询进度（`GET /api/runs/{id}/events` 增量）→ 预览/下载产物（`GET /api/reports/<file>`）。管线复用 `generate_report` 零改动（reporter 注入 WebProgressReporter，output_dir 快照在出队时取）。
- **上传安全（§6.1）**：uuid 重命名丢弃原始文件名（防路径穿越/中文）、`.xlsx` 扩展名白名单 `.lower()`、10MB 上限（Flask MAX_CONTENT_LENGTH 兜底）、PK zip 魔数校验、行数上限 5000、mkstemp + os.replace 原子落盘、TTL 1h + 启动清理；伪装 zip 预检兜底转 UPLOAD_BAD_FILE（新增测试暴露的真实缺陷）。
- **预览防穿越（§6.2）**：扩展名白名单 + `send_from_directory` 内置 `..` 净化。
- **`unit_web` marker + 测试**：conftest 注册 marker / 隔离 `_UPLOAD_DIR`+`_file_registry` / autouse 重置 RunManager 单例，unit/conftest `_DIR_TO_MARKER` 映射，test_runner dev-verify/verify 纳入；5 个测试文件 54 用例（upload/upload_edge/progress/runs/handlers，含 zip-bomb/伪装/路径穿越变体 edge 场景）。
- **验证**：web 目录 54 用例全绿；dev-verify 1905 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 通过。阶段2（功能补齐）/阶段3（体验打磨）待做。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### plan-8 阶段2：配置回填 + 进度步骤 + 状态区（2026-08-06）

- **配置显示回填表单**：索引页加载时取一次 `get_config()`，历史走势复选框默认跟随配置 `history.fetch_mode`（off→关闭，auto/prompt→开启，`enable_history` 一并计入）；新增「强制重新生成 LLM 内容」开关。表单显式提交 `fetch_history`/`force_llm` 布尔值。
- **进度步骤展示**：事件按步序号（seq）编号渲染，进度条上方显示「当前阶段（第 N 步）：消息」，完成置 100%。
- **历史运行记录页**：状态区新增历史记录卡片（`/api/runs/history`，5s 短缓存），展示最近 10 条运行（时间/报告类型/持仓数/耗时/异常标记）。
- **run 保留上限清理（rf-253）**：`_trim_runs` 原仅在 `submit` 时调用——run 由 worker 线程逐条变为 done，批量提交时多数 run 尚未完成，submit 循环结束时 trim 无法清理后续完成的 run → run 注册表超出 `_RUN_KEEP`（测试实测 25 > 20）。修复：worker `_work_loop` 的 finally 分支补 `_trim_runs()`（持锁），run 完成即触发保留上限清理；`test_retention_trim_oldest` 调整等待语义回归。
- **数据源健康状态**：状态区新增健康卡片（`/api/health`，60s 缓存），逐源展示正常/异常 + 延迟；「重新检测」按钮用 `?fresh=1` 绕过缓存强制重测。
- **错误处理完善**：结果按 `exit_code` 映射展示（0 成功 / 1 部分失败黄色告警 + 通用建议 / 2 严重红色 + 提示看日志）；严重/执行失败时隐藏无效产物按钮（见 rf-254）；失败提供「重新生成」按钮（上传文件已消费，引导重新上传）；提交时 `FILE_EXPIRED` 自动重置流程提示重新上传。
- **验证**：web 目录 64 用例全绿（新增索引回填/健康缓存 fresh/产物裁剪/布尔参数 10 用例）；dev-verify 1915 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 通过。阶段3（体验打磨 + 文档）待做。

### plan-8 阶段3：样式打磨 + 加载态/轮询节流 + 响应式 + 用户文档（2026-08-06）

- **样式打磨（design-quality）**：上传区拖拽高亮（drag-over 抬起 + 聚焦态）、进度条渐变（主色→强调色）、卡片悬浮阴影层级、状态区双栏网格（数据源健康/历史记录，≤480px 单栏）、结果徽章语义着色（成功绿/部分黄/失败红）、`prefers-reduced-motion` 减动效适配。
- **加载态与轮询节流**：提交后生成按钮禁用 + 文案切换（正在提交...→生成中...）；上传/轮询/结果请求全部 `AbortSignal.timeout` 兜底；`visibilitychange` 页面不可见时暂停轮询、恢复可见立即同步（省请求）。
- **响应式（375px 移动端）**：表单纵向堆叠、按钮全宽、状态区单列、健康行 meta 截断不溢出。
- **a11y**：文件输入从 `hidden` 改为 `sr-only` 视觉隐藏但保留可聚焦（键盘可达）；进度条 `role="progressbar"` + aria-valuenow；aria-live 播报。
- **用户文档**：how-to-start.md 新增「方式四：Web 浏览器模式」（启动命令 / --host --port --config 参数 / 局域网访问无内建认证警示 / 使用要点）；faq.md 故障排查补 Web 模式 5 问（端口冲突/无法访问/进度卡住/文件过期/产物 404）；README.md 功能特性补 Web 模式提点。
- **归档**：`plan-web-ui.md` + `plan-web-ui-implementation.md` 归档至 `docs-stm/archive/v0.10.x/web-ui/`（三阶段全部完成），plan.md / folders.md 引用同步更新。
- **工具修复（rf-255）**：`check-doc-traces.py` 裸版本号模式把 Web 文档正文 IP 地址误判为版本号（`127.0.0.1:8000`→子串 `0.0.1`、`0.0.0.0`→`0.0.0`，5 处误报）——`_line_exempt()` 增加 IPv4（含端口）整行豁免，双用例回归。
- **验证**：web 目录 64 用例全绿；dev-verify 1917 passed（新增 2 个工具回归用例）；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 通过。plan-8 三阶段全部完成。

### rf-113 Iter 7 浏览器人工验证进度更新（2026-08-06 另机 Windows）

- **① 6 图渲染 + 交互 — ✅ 通过**：ok/degraded 场景 6/6 图渲染 + 全部图 tooltip 可用（含净值/回撤折线、雷达——rf-249 修复后悬停任意处即显示）；empty 场景 4/6 渲染 + tooltip（资产构成/雷达空数据占位，符合 §4.12 空值语义）；offline 场景引擎缺失守卫生效（R21）。Chrome + Firefox 实测，Edge 未测（同 Chromium 内核，S2 升级时补验）。
- **② 打印降级 — ✅ 2.1~2.3 通过**：打印预览图表 2x DPI 清晰（文字/刻度/数据线锐利）、浅色主题强制（文字黑/背景白，不浪费墨水）、单图不跨页（`break-inside: avoid`）。2.4（afterprint 恢复交互）待补验。
- **③ 离线验证 — 3.2~3.4 通过**：删除 chart.min.js → `typeof Chart` 守卫静默跳过、无 JS 报错；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格（rf-249 修正断言）。3.1（断网 6 图正常渲染）待补验。
- **待补验**：② 2.4 afterprint、③ 3.1 断网渲染、④ 微信内置浏览器、⑤ 375px 移动端、⑥ 禁用 Canvas fallback。
- **验证期间修复**：rf-248（动态脚本顺序）、rf-249（折线/雷达 tooltip 触发）、rf-250（自检 `Chart.getChart` 判定）、rf-251（空数据图显式守卫）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### Web 服务启动 output_dir 写锁检测（rf-256）

- **缺陷**：`web/server.py` 仅做端口占用检测（bind 探测），未做设计文档（`docs-stm/archive/v0.10.x/web-ui/plan-web-ui-implementation.md` 单 worker 串行队列一节）规定的 `output_dir` 锁文件检测——多进程共享同一输出目录（多开 web、或 web 与 TUI/CLI 并行）会互相覆盖最新版产物，启动时不提示，用户难以察觉产物被其他入口覆盖。
- **修复**：`web/server.py` 启动时对 `output_dir` 做写锁检测——原子抢占锁文件 `.investor_output.lock`（`os.open` `O_CREAT|O_EXCL` 防多进程抢占竞态；内容记录 entry/pid 便于排查），锁已被其他入口持有则记录警告「该输出目录可能正被其他入口占用，产物可能互相覆盖」，抢占成功则持有至进程退出时 finally 释放。锁文件为点文件，不参与 `YYYYMMDD` 归档扫描与历史枚举（`_cleanup_old_archives` 仅处理 8 位数字目录）。占用仅告警、不阻塞启动（产物竞态交由用户决策）。
- **验证**：新增 `src/test/unit/web/test_server.py` 11 用例（锁路径定位 / 存在性判断 / O_EXCL 原子排他 / 释放与缺失 noop / 目录不可写兜底 / 被占用告警且不阻塞启动）全绿；web 目录 75 用例全绿；dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### technical.md 三渠道体系梳理 + 渠道详细设计（TUI / CLI / Web）

- **背景**：plan-8 三阶段后系统已具备 TUI/CLI/Web 三个交互渠道，technical.md 仅以「三入口」表格平铺各渠道入口/交互层/进度报告器对照，缺体系化视角（渠道定位、统一架构模式、差异维度、并发与产物治理），且各渠道实现（TUI 主循环/菜单/键盘、CLI argparse/退出码、Web 启动流程/上传安全/单 worker 队列/事件缓冲）分散在 §1.1/§1.3/§4/§7 而无集中详述。
- **§1.5 交互渠道体系（CLI / TUI / Web）**：新增体系化章节——① 渠道定位（交互范式/典型场景/进程模型三渠道对照）；② 统一架构模式（薄入口 + 共享管线 + 进度抽象 + 配置快照）；③ 渠道差异对照（参数传递/进度传输/并发模型/产物输出/启动防护/生命周期六维度）；④ 并发与产物治理三层（进程内单 worker 队列 / 进程间 output_dir 写锁 / 存储层原子写 + 归档分目录，警告优先不阻塞）。
- **§1.6 TUI 渠道详细设计（主要渠道）**：聚拢既有丰富材料重新组织为独立章节（TUI 是主要渠道，篇幅最深，位于渠道序位首位）——模块划分（tui.py / tui_menu / tui_keys / handlers_report / handlers_config / handlers_cache / handlers_whatif / TuiProgressReporter）/ 主循环与键盘导航（重绘循环 + 方向键/快捷键/Ctrl+C 路由，跨平台键盘封装）/ 菜单体系（17 项四分组表 + 状态面板）/ 报告生成流程（_run_generate 骨架 + _prompt_history/_prompt_force_llm 交互询问 + 委托 orchestrator）/ TuiProgressReporter（四态前缀 + call_sheet + 耗时排行框）/ 启动流程（init_config → _bind_callbacks → 清理/隐私提示/首次引导 → default_menu_key 默认「L」→ 退出 LLM 会话统计）。
- **§1.7 CLI 渠道详细设计**：新增——退出码约定（0/1/2）/ argparse 结构（全局参数 + report/cache/whatif/check-sources 子命令）/ 主流程（check-sources 前置免 config、持仓 config 定位差异）/ 子命令处理器（report 委托 generate_report、cache 三分支含 --update all 最大努力模式、whatif 委托 run_whatif_simulation）/ CliProgressReporter（默认日志、--verbose 同步 stderr）。
- **§1.8 Web 渠道详细设计**（原 §1.6 重编号）：模块划分 / 启动流程与启动防护（端口检测 + output_dir 写锁检测）/ Flask 工厂与统一错误信封 / 路由全景表 / RunManager 单 worker 串行队列（快照语义、状态机、内存上限、线程安全）/ 上传安全链路 / WebProgressReporter 事件缓冲 / 前端单页与进度可视化 / 安全防护矩阵 / 与 TUI/CLI 差异要点。
- **同步修订**：目录 TOC 补 §1.5/§1.6/§1.7/§1.8 锚点；§1.1 分层差异段落交叉引用 §1.6（TUI 主要渠道）/§1.7/§1.8；§1.5 内引用随重编号更新（§1.6.5→§1.8.5、§1.6.2→§1.8.2）；§7 web 依赖块 server.py 行补写锁检测；附录 A server.py 条目补启动防护说明。
- **门禁**：check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

### 技术设计文档自完备修正（technical.md / llm-technical.md）

- **technical.md 数据降级体系**：删除对用户文档（datasource-reliability.md §4.1）的引用，改为自包含「三级熔断体系」完整说明——技术设计文档不引用用户文档、整体自行完备（约束原文要求）。
- **technical.md 数据可用性措辞**：去实测日期痕迹与「历史快照」措辞，改为「365 天窗口探测，Tencent 主链路」等反映最新状态的中性描述。
- **technical.md 附录 H**：去「已实现全量」标题与「已实现」状态列、清理悬空 Schema 文档引用；架构设计约束表中 pipeline_data Schema 定义条目改指向附录 H。
- **llm-technical.md**：提示词示例时间「2026-07-14 14:30」改为占位符「YYYY-MM-DD HH:MM」——示例反映模板而非快照时间。
- **门禁**：check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### chart-init.js 空数据图显式守卫（rf-251）

- **缺陷**：6 个核心图 init 守卫 `!ds.labels` / `!ds.datasets` 不拦截空数组（空数组 truthy）。empty 场景（`labels:[]` + `datasets:[]`）下 `ds.datasets[0]` 为 undefined，访问 `.data` 抛 TypeError，**依赖外层 try/catch 降级**（图不渲染、console 出现 `[chart] 初始化失败` warn 噪声），而非显式空数据跳过。
- **修复**：6 处守卫统一补 `!ds.labels.length` + `!ds.datasets.length`，空数据优雅 return，对齐生产模板 `{% if labels %}` 空值语义（§4.12），不再依赖异常降级。
- **验证**：JS 语法校验通过；empty 场景资产构成/雷达空数据图不初始化、badge 占位行为不变。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### test-chart.html 自检图接管判定修正（rf-250）

- **缺陷**：调试页自检用 `canvas._chart` 判定图是否被 Chart.js 接管——Chart.js v4 该内部句柄已不存在（canvas 上挂的是 `_chartjs`，用于管理事件监听器；`_chart` 是数据集/图表元素内部引用），判定恒为假。rf-249 修复后 ok/degraded 场景图真实渲染、tooltip 可用（用户 2026-08-06 实测），但自检仍误报「0/6 图已初始化」。
- **修复**：自检判定改用官方 API `Chart.getChart(canvas)`——v4 构造内部亦用 `Chart.getChart(canvas)` 查询已有图表（`constructor` 中 `o = Dn(n)`），与 chart-print.js / chart-export.js 收集图表用同一 API，口径一致。
- **验证**：待用户重测四场景 banner 应正确显示实际初始化数（ok/degraded=6/6，empty=4/6，offline=引擎缺失文本）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 折线图/雷达图 tooltip 触发修复 + 调试页自检时序与文案修正（rf-249）

- **tooltip 缺陷**：6 图交互验证（rf-113 ①，用户 2026-08-06 另机）发现——净值趋势/最大回撤折线图 `pointRadius:0` 且 Chart.js 默认 `interaction.intersect:true`，数据点命中区域≈0，鼠标悬停无法触发 tooltip；雷达图 `pointRadius:3` 命中区域小同样难触发。环形图（切片命中区域大）与两个柱状图（整柱命中）正常。该缺陷同时影响生产报告（净值/回撤/组合演进 3 图）与 whatif 回测线图（共用 `ChartCommon.lineOptions`）。
- **修复**：
  - `chart-common.js` `lineOptions` 补 `interaction:{mode:'index',intersect:false}`——折线图悬停图表任意处即显示最近 x 点全数据集值（金融时序标准交互）。
  - `chart-init.js` radar 补 `interaction:{mode:'nearest',intersect:false}`——雷达无 x 索引轴，用最近点模式。
- **调试页自检时序**：test-chart.html banner 自检原用固定 800ms 定时器，早于脚本加载完成（chart.min.js 约 200KB）误报「0/6 图已初始化」；改为 chart-init.js（最后一个注入脚本）onload 触发 + 3s 兜底，保证自检在全部图表初始化完成后执行。
- **offline 文案修正**：banner 原断言「canvas 保留 fallback 文本」为误解——现代浏览器（Firefox/Chrome）不渲染 `<canvas>` 内部 fallback 文本（仅不支持 Canvas 的浏览器显示），引擎缺失时图表区域实际为空白，真实报告回退到明细表格。banner 文案与 iter7 验证清单 3.4/进度注记、review-findings rf-113 注记同步修正为实测行为。
- **验证**：待用户另机硬刷新（Ctrl+F5 清缓存）重测四场景——ok/degraded 应 6/6 初始化、全部图悬停有 tooltip；empty 应 4/6 初始化 + 资产构成/雷达占位；offline 引擎缺失文本为预期（R21）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### test-chart.html 动态注入脚本顺序修复（rf-248）

- **缺陷**：TD8 调试页 `src/static/test-chart.html` 引导脚本用动态 `createElement('script')` 注入 6 个 chart 资产，但未设 `s.async=false`。动态 script 默认 async=true **无序执行**，chart-init.js（约 13KB）可能先于 chart.min.js（约 200KB）执行，触发 chart-init.js 顶部守卫（`typeof Chart === 'undefined' || !window.ChartCommon`）静默 return，图表永不初始化——ok/degraded/empty 全场景实测均「0/6 图已初始化」、无 tooltip（用户 2026-08-06 另机复现；empty 场景仅 radar badge 走「占位」分支，其余图空白；偶发 800ms 自检时 Chart 尚未加载完成还会误报「引擎缺失」banner）。
- **修复**：注入循环补 `s.async=false`，保证脚本按注入顺序执行（chart.min.js → … → chart-init.js 最后），对齐报告模板 `defer` 语义。
- **影响范围**：仅调试页受影响；生产报告模板（report_template.html）/ whatif 模板（whatif_template.html）均用静态 `<script defer>`，执行顺序有保证，无此缺陷。
- **验证**：修复后待用户另机重测三场景（ok/degraded/empty 应 6/6 图初始化、tooltip 可用；offline 场景保留引擎缺失文本，属 R21 预期）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

---

## [0.10.11] - 2026-08-06

### README 核心亮点总览重写（2026-08-06）

- **标题区简介重写**：从一句话简介升级为有感染力的总览——「把持仓 Excel 变成决策级投资洞察」，点明本地投资分析引擎、对接中国金融数据源、穿透组合底层资产、融合量化指标/基金评级/LLM 智囊团深度复盘、产出图表丰富的 HTML 报告与专业的 Excel 报告。
- **新增「✨ 核心亮点」总览表**（5 行）：① **三种交互渠道**（TUI 全键盘菜单 / CLI 定时无人值守 / Web 浏览器即开即用，同一引擎报告一致）；② **图表丰富的 HTML 报告**（单页自包含、响应式、9 张 Chart.js 交互图、深/浅色主题）；③ **专业的 Excel 报告**（最多 19 条件页签分七组）；④ **LLM 智囊团**（多 Provider 链式分发 + 缓存省费）；⑤ **调仓 What-if 模拟**。
- **启动方式统一引导句**：「同一套引擎，三种交互渠道——按你的场景选一个即可，报告结果完全一致」。
- **folders.md 同步**：用户文档统计行数 5,843→5,855（README 191→203 行）、目录树 README 描述标注「三渠道交互 + 核心亮点总览」。

---

### 数据源健康检查整体耗时预算修复（rf-263）（2026-08-06）

- **`core/check_sources.py` `run_health_checks`（rf-263 修复）**：`max_timeout` 原为**死参数**——`ThreadPoolExecutor` + `as_completed` 主流程等待全部线程完成，慢速/挂起数据源会拖住整个健康检查（Web 健康接口需在前端 15s abort 前返回，超时则 504）。改为 daemon 线程 + 整体耗时预算：`deadline = perf_counter() + max_timeout`，逐线程 `join(timeout=剩余预算)`，预算耗尽即返回已收集的部分结果，未完成项标记「超时（预算 Ns）」；持锁原子追加 + 竞态兜底（同 name 保留真实结果弃超时占位）。
- **`src/test/unit/core/test_check_sources.py`（新增）**：回归用例覆盖——预算内完成全部返回 / 慢源超时未完成项标记超时 / 竞态兜底（迟到真实结果覆盖超时占位）。
- **门禁**：dev-verify passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

---

### 功能开关文档补全 + HTML 自包含文档强调（2026-08-06）

- **`how-to-config.md` §M 功能开关表补全（rf-262 修复）**：原表只以通配符摘要列出分组（`llm_*`/`fund_deep_analysis_*`/`news_*`/`metrics_*`），未列具体 key，且 `fund_deep_analysis_*` 计数误写 4 项（实际 2 项）。已补全为**逐项列出全部 27 个开关**（key / 默认值 / 说明），与代码 `features.py::_FEATURE_FLAGS_DEFAULT` 一致。
- **修正错误指引**：原「完整清单以 `data/config/features.json` 文件中的注释为准」——features.json 是唯一不支持注释的配置文件，指引错误。改为明确指向代码默认值 `features.py`，并强调该文件仅存覆写子集。
- **`faq.md` 报告理解新增问答（HTML 单文件自包含强调）**：明确默认自包含（8 个 JS 资产内嵌）、关闭 `enable_interactive_charts` 后的例外（不自包含、须与 JS 同目录）、以及给用户的明确结论；同步修正故障排查中过时说法「报告不含 JavaScript，纯 CSS 渲染」。
- **门禁**：check-doc-traces / check-task-numbering `--ci` 全 [OK]。

---

### Web 状态区系统信息展示（版本 / 本机 IP / LLM 状态）（2026-08-06）

- **`web/handlers.py` `_build_system_info`（新增）**：rf-260 修复——Web 页面缺 TUI 状态面板信息面（程序版本号 / 是否开启 LLM / endpoint / 熔断 / 模型路由 / 本机 IP）。组装 `app_version`（`APP_VERSION`）+ `machine_ip`（`_get_machine_ip`）+ `llm` 结构化状态：flat 单 provider 模式展示 provider / model / endpoint（`_simplify_endpoint` 取主机名）/ 熔断（`get_circuit_status`）/ 模型路由（隐藏辩论三模块，模块级 `model_{sfx}` 覆盖展示）；credentials_ref 多链模式展示策略（priority 等）与 provider 清单（名称/后端/模型/优先级/熔断，model/endpoint 经 credentials_ref 解析到 `_llm_credentials`）及模块偏好；未配置或读取异常（try/except 兜底）→ `configured=False`，页面显示「未配置」，不阻断渲染。
- **`web/templates/index.html` / `web/static/style.css`**：状态区 grid 由两列改三列（`.status-grid-3`），新增「系统信息」卡片（程序版本 `#system-version` / 本机 IP `#system-ip` / LLM 状态 `#system-llm`），配置时展开 `#system-llm-detail`（multi 列 provider、flat 列熔断+模型路由）；补 `.system-list`/`.system-row`/`.system-llm-on/off`/`.system-llm-detail` 等样式，375px 响应式折叠为单列。
- **验证**：`TestSystemInfo` 7 用例（unit_web 标记：默认未配置 / flat 缺 api_key 兜底 / flat 详情与模块覆盖 / 多链凭据解析与偏好 / 读配置异常兜底 / 索引页渲染未配置态）全绿；`test_handlers.py` 全文件 31 用例通过。
- **门禁**：dev-verify passed（1938 passed, 0 failed）+ check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

---

### HTML 报告单文件自包含（2026-08-06）

- **`html_writer_assets.py` `_inline_js_assets`（新增）**：rf-259 修复——报告 HTML 下载/移动后图表失效。报告模板以相对路径外链 8 个 Chart.js 本地 bundle 资产（chart.min.js/chart-print.js/chart-config.js/chart-export.js/chart-common.js/chart-init.js/toc.js/theme.js），`_copy_js_assets` 仅复制到输出目录，HTML 移到其他目录（Web 下载到本地、单发移动端浏览）后 JS 找不到 → 资产穿透 TOP10 等图表空白。`_inline_js_assets` 在内嵌保存前读取资产内容，将 head 区外链标签移除并按 bundle 依赖顺序追加为行内 `<script>` 到 `</body>` 前——复刻 defer 外链时序（DOM 解析完后、DOMContentLoaded 事件前按序执行），保证 chart-init.js 能取到已解析的 canvas/chart-data、toc.js/theme.js/whatif 初始化等内部注册 DOMContentLoaded 的脚本仍触发；报告 HTML 单文件完全自包含。
- **`html_writer.py` / `whatif_writer.py`**：`enable_interactive_charts` 开启时保存前调用 `_inline_js_assets(html)`；`_copy_js_assets` 保留作兜底（资产缺失/读取失败/含 `</script` 序列时该资产外链标签保留原位，松散文件仍可加载）。
- **验证**：`TestInlineJsAssets` 6 用例（unit_report 标记：全部外链替换+追加到 body 前、defer 时序位置、bundle 依赖序 common→init、非 bundle 外链保留、缺失/含 `</script` 跳过）全绿；无头 Chrome 差分实测——内嵌版在无 JS 目录 canvas `width=1048`（Chart.js 实例化，图表渲染），外链版停默认 `500×320`（空白），修复前两者像素一致、修复后内嵌版彩色像素 347682→398536（ratio 1.15）。
- **门禁**：dev-verify passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

---

### Web 冒烟脚本沉淀（2026-08-06）

- **`scripts/smoke-web.py`（新增）**：rf-258 修复——将 Web 模式验收的临时冒烟脚本沉淀为可复跑脚本。前端零 node 工具链约束下不引入 Playwright，改为 Flask `test_client` 进程内 HTTP 全链路验证（不占端口、不发真实网络），覆盖 9/9 断言：页面渲染 / 健康检查 / 上传校验（合法 xlsx→file_id、伪装坏文件→400）/ 运行 202 / 进度事件 / 完成态 / 产物下载 / 历史记录 / 产物目录隔离。管线（fake executor）、健康探测（`run_health_checks` mock）、历史记录（`load_history` mock）全 mock；output_dir 与上传目录临时目录隔离。独立运行 `.venv/bin/python scripts/smoke-web.py`，全部通过退出码 0，失败退出码 2。
- **`src/test/unit/web/test_smoke_web.py`（新增）**：pytest 载体（`unit` + `unit_web` 标记），importlib 加载脚本调 `run_smoke()` 断言 9 项全通过；`unit_web` 标记使本用例自动纳入 test_runner `dev-verify`/`verify` 门禁（无需改 MODES 字典）。
- **门禁**：dev-verify passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

---

## [0.10.12] - 2026-08-07

### 测试覆盖统计：dragonball 列耗时刷新（--update-docs 回填）（2026-08-07）

- **重新采集 dragonball 列运行时长**：`test_runner.py --mode bench --update-docs` 顺序采集全部模式实测耗时并回填 `test-coverage.md` 环境耗时对照表（env 表采集日期 2026-08-05 → 08-07；duration 表 dragonball 列按新实测刷新，如 `unit` ~14s → ~15s、`all` ~22s → ~23s、`report` ~11s → ~14s）。
- **统计计数核对**：`collect-test-coverage.py` 实时收集快照与文档一致——`all` 5445、`unit` 5136、unit 子标记（unit_report 1541 / unit_analysis 699 / unit_config 299 / unit_web 184 等）均无变化（近期无测试新增/删除）。
- **说明文字同步**：顶部「典型耗时」注、两机采集日期表述、对比段落示例值（`unit`/`all`/`edge`/`smoke`）按 dragonball 新实测更新。
- **门禁**：check-doc-traces `--ci` [OK]。

---

### README/CLAUDE.md：三模式文档索引与列表统一（2026-08-07）

- **README 启动方式三节统一指向各自分册**：TUI 节补「TUI 菜单操作手册」链接（原只有命令、无入口）；Web 节改链「Web 浏览器模式使用指南」（原链快速开始方式四，不直达分册）；CLI 节补完整命令参考入口 + 保留 §11「定时任务」引用。
- **README 功能特性**：TUI / CLI / Web 三模式条目统一追加对应指南链接。
- **README 用户指南表**：CLI 行说明补「定时任务」。
- **CLAUDE.md 用户文档列表顺序统一**：调整为与 README 索引一致（how-to-start → web-mode → tui-menu → cli-mode → config → llm-config → reports-instruction → datasource → datasource-reliability → faq → registry → test-my-code → scripts-reference）。
- **`folders.md` 统计表同步**：README 204→206 行，用户文档 14/6,204。
- **门禁**：check-doc-traces `--ci` [OK]。

---

### 用户文档：三模式使用指南体系（TUI/CLI/Web 各一份）（2026-08-07）

- **Web 浏览器模式使用指南**（`how-to-use-web-mode.md` 新建）：从用户视角完整讲述 Web 使用——启动访问、首页 6 分区布局、上传→生成→预览/下载全流程、配置编辑面板（7 组即改即存）、运行状态区、与其他模式关系、安全注意（无内建认证）。
- **CLI 命令行模式使用指南**（`how-to-use-cli-mode.md` 新建）：命令结构、全局参数、`report`/`cache`/`whatif`/`check-sources` 子命令、使用示例、常用命令速查、退出码、最佳实践（缓存预热/输出路径/网络退避/性能历史/日志轮转）。
- **定时任务内容并入 CLI 指南**：`how-to-schedule.md` 内容合并至 `how-to-use-cli-mode.md` §11「定时任务」（Windows schtasks + PowerShell 包装 + 防重入 / Linux crontab + flock / 排障），原独立文档删除；`README`/`how-to-start`/`faq` 等引用统一改指 CLI 指南 §11。
- **TUI 菜单文档重命名**：`how-to-menu.md` → `how-to-use-tui-menu.md`（标题改「TUI 菜单操作手册」，内容不变）；归档目录保留历史文件名（不追溯重命名）。
- **`how-to-start.md`**：方式四（Web）新增「③ 配置编辑」要点并链接 Web 指南 §4；原「CLI 命令参考」小节替换为指向 CLI 指南的精简引用；菜单操作速览引用改指 TUI 菜单手册。
- **`README.md`**：用户指南表改为三模式文档各占一行（Web/TUI/CLI），删除 schedule 行，CLI 启动方式补「定时任务见 CLI 指南 §11」。
- **`technical.md` §1.8**：模块表新增 `web/config_edit.py`、路由表新增 `GET/POST /api/config/edit`、§1.8.9 安全矩阵新增「跨站写请求（配置编辑）」行、§1.8.11 新增 Web 配置编辑小节、差异表补配置编辑行——与 plan-26 实现对齐。
- **`folders.md`**：manuals 目录树同步三模式文档（新增 web-mode/cli-mode，tui-menu 重命名，schedule 移除），统计表刷新（用户文档 14/6,202，manuals 13/5,998），并修正重复条目。
- **门禁**：dev-verify + 4 checks `--ci` 全 [OK]。

---

### Web 配置编辑：完整镜像 TUI 可编辑配置全集（plan-26 实现）（2026-08-07）

- **新模块 `web/config_edit.py`**：`config_edit_whitelist` 白名单（点分键→类型/枚举→目标文件→写入原语，唯一事实来源）+ `apply_config_edit`/`get_config_edit_surface` + `config_backup_file` 写前单槽 `.bak` 备份（mkstemp + `os.replace` 原子写，复用 `holdings_update._atomic_copy`）。
- **路由**：`GET/POST /api/config/edit`——GET 返回面板全量 7 组可编辑面；POST 复用 `_is_same_origin()` 同源守卫（失败 403），校验失败 400 BAD_PARAM，写共享配置异常 500 CONFIG_WRITE_FAILED。
- **7 组可编辑全集（与 TUI 完全一致）**：自由文本路径 3（holdings_dir / holdings_filename / output_dir）、报告章节开关 5、增强子模块开关 6、匿名化枚举 4 档、对比指数池（增/删/重置默认）、LLM 分析章节开关 5（enabled_llm，隐藏辩论三模块不展示）、辩论实验功能开关 3（features.json）。
- **写入分派逐条等价 TUI**：config.json 顶层标量→`set_config`；嵌套 dict（report_submodules/comparison_indices）读合并整块写；anonymization.mode→`set_anonymization_mode`；enabled_llm.*→共享 `write_llm_settings`（自 `tui/handlers_config.py` 抽取，TUI 改委托，行为零变化）；llm_debate_*→`save_feature_overrides`。
- **一致性修正**：两个状态面板（TUI 隐私安全状态 + Web 系统信息）匿名化读路径由不存在的 `features.anonymization.mode` 修正为顶层 `anonymization.mode`（此前恒显示「关闭」）。
- **前端**：`index.html` 新增「③ 配置编辑」card（7 组控件，选项与 TUI 完全一致）+ `main.js` 即改即存（改即写、失败回滚、error_code 驱动提示）+ `style.css` 配置面板样式。
- **测试**：`test_config_edit.py` 35 用例（白名单完备/隐藏 LLM 键拒绝/面板读取/标量写/嵌套 dict 写/llm_settings 写/features 写/校验守卫/备份）+ `test_config_edit_edge.py` 42 用例（极端输入 edge 隔离）+ `smoke-web.py` 扩展至 11 项断言（配置面板加载 + 保存成功 + 非法键 400）。
- **顺带修复**：`smoke-web.py` `_build_client` 污染 `_DEFAULT_CONFIG`（holdings_dir/holdings_filename/output_dir）导致 config 测试顺序失败——`run_smoke` finally 统一还原 `_DEFAULT_CONFIG`/`_CONFIG_FILE`，web+config 同进程 282 测试全绿。
- **验证**：web+config+handlers 同进程 282 passed；语义表登记 `config_edit`/`config_edit_whitelist`/`config_backup`（反向校验通过）。

### 前端资产统一归入 src/static/：Web UI 与报告模板（plan-27）（2026-08-07）

- **Web UI 前端**（`index.html`/`main.js`/`style.css`）自 `src/python/web/{templates,static}/` 归入 `src/static/web/`；`app.py` 的 Flask `template_folder`/`static_folder` 改为 `PROJECT_ROOT` 派生指向新目录，`/static/main.js` URL 与 `render_template("index.html")` 契约不变。
- **报告 Jinja 模板**（`report_template.html`/`whatif_template.html`/`partials/`）自 `src/python/tmpl/` 归入 `src/static/tmpl/`；`html_jinja_env.py` 的 `_TEMPLATE_DIR` 改用 `PROJECT_ROOT` 派生（单加载点，whatif 走同一 `_ENV` 零改动）。
- **净效果**：`src/static/` 成为非 Python 前端资产唯一归属（报告图表 bundle + Web UI 前端 + 报告模板三合一）；`src/python/` 仅保留纯 Python 代码。
- **测试同步**：5 个按路径读模板的测试（test_html_writer / test_html_template / test_html_report_structure / test_html_report_structure_edge / test_llm_placeholder_distinction_edge）路径改为 `src/static/tmpl/`。
- **验证**：`smoke-web.py` 10/10（Flask 新位置服务模板 + `/static/main.js`）；report/web/llm 全量单测 2395 passed。
- **配套**：`folders.md` 目录树与统计表同步（web/ 目录树移除 templates/static，src/static/ 新增 web/tmpl 子树）；plan-26 配置编辑设计文档改动清单已按新路径更新（前端位置无关、契约不变）；`src/static/README.md` 资产说明滞后登记 rf-266。

---

### Web 配置编辑：完整镜像 TUI 可编辑配置全集（设计定稿）（2026-08-07）

- **本条目为设计文档登记**（`docs-stm/archive/v0.10.x/web-config-edit/web-config-edit.md`，plan-26），实现前不产生运行时代码变更（已实现，设计文档已归档）。
- **范围**：Web 模式支持修改与 TUI **完全一致**的配置项全集——7 组：自由文本路径 3（holdings_dir / holdings_filename / output_dir）、报告章节开关 5、增强子模块开关 6、匿名化枚举 4 档（off/code_display/full_anonymous/summary）、对比指数池（增/删/重置默认）、LLM 分析章节开关 5（enabled_llm，隐藏辩论三模块不展示）、辩论实验功能开关 3（features.json）。
- **关键决策**：新模块 `web/config_edit.py`——`config_edit_whitelist` 白名单（点分键→类型/枚举→目标文件→写入原语）+ `GET/POST /api/config/edit`（POST 复用 `_is_same_origin()` 同源守卫）；写共享配置前 `config_backup_file` 单槽 `.bak` 备份（mkstemp + `os.replace` 原子写）；写入分派逐条等价 TUI（config.json→`set_config`，嵌套 dict 读合并整块写，匿名化走 `set_anonymization_mode`；llm_settings.json→自 tui 抽取共享 `write_llm_settings`；features.json→`save_feature_overrides`）。
- **一致性修正（随功能实现）**：状态面板匿名化读路径由不存在的 `features.anonymization.mode` 修正为顶层 `anonymization.mode`（tui_menu 状态面板 + web `_build_system_info`），此前面板恒显示「关闭」。
- **前端**：index.html 新增「配置编辑」card（7 组控件）+ main.js 即改即存 + error_code 分支，选项与 TUI 完全一致。
- **状态**：设计定稿待实现；预估 2d；语义表 `config_edit`/`config_edit_whitelist`/`config_backup` 于实现完成时登记（check-semantic-index 反向校验约束）。

---

### Web 生成用途双模式：临时试算隔离 / 正式更新共享（2026-08-07）

- **Web 新增「生成用途」选择**：提交前可选「临时试算」（默认）或「正式更新」。
  - **临时试算**：读上传临时文件生成，不落正式持仓；历史快照写入**试算隔离域**（`data/history/snapshots/web/`），与 TUI / CLI 的正式共享时间线互不污染。
  - **正式更新**：两个输入来源——「上传新文件覆盖」先将旧正式持仓备份为 `.bak` 再提升为正式文件；「直接用当前正式文件」无需上传，直接读取配置路径下的正式文件。两种来源快照均写入共享时间线。
- **后端契约**：`POST /api/runs` 新增 `mode`（`trial`/`formal`，默认试算）与 `use_existing` 参数；正式+用存量组合禁止携带 `file_id`（否则 400 BAD_PARAM）。正式模式提升发生在 run 出队后、生成前——报告后续失败（LLM/网络）不影响已提交的正式文件。
- **快照隔离命名空间**：`history_snapshot` 全部公开函数（save/load_latest/load_all/list_all/prune）与 `capture_snapshot`/`build_evolution_data`/`build_snapshot_diff`/`generate_report` 新增 `namespace`/`snapshot_namespace` 参数（默认共享主目录，`"web"` 为试算隔离域）；各域按 `history.snapshot_retention_days`/`snapshot_max_count` 独立清理。
- **正式持仓更新模块**：新增 `web/holdings_update.py`（`backup_holdings_file` 单槽 `.bak` 备份 + `promote_upload_to_holdings` 原子提升，mkstemp + `os.replace`）。
- **前端**：`index.html`/`main.js` 新增模式单选、输入来源单选、覆盖警示条与确认勾选；`resetFlow` 区分正式-用存量（直接重新生成）与其余模式（重新上传）；警示条 `role="alert"` 单一 live-region 语义。
- **冒烟**：`smoke-web.py` 扩展到 10 项断言（含正式-用存量 202 全链路 + 参数组合 400 校验）。
- **测试**：新增 namespace 存储隔离、消费层透传、输入模式分派（含正式-用存量缺文件严重退出、参数组合校验）；conftest 新增 `holdings_path_isolated` 可选隔离 fixture（正式覆盖不污染真实持仓）。
- **门禁**：dev-verify + 4 checks `--ci` 全 [OK]。

---

### 数据质量仪表盘缺省开启：config.json 落盘同步（2026-08-07）

- **`data/config/config.json` `report_submodules.data_quality` 由 `false` 改为 `true`**：此前默认值改 `true` 时（见下方案例 `data_quality 缺省开启` 条目）仅同步了生成模板/访问器/文档，仓库内**实际配置文件残留 `false`**——生成器新建配置虽默认开，但沿用旧配置的用户仍是关。本次将落盘配置对齐默认，并修正过期注释「数据质量仪表盘默认关」→「数据质量仪表盘默认开，其余默认关」。
- **一致性核对**：生成模板 `_config_defaults.py`（`data_quality: True`，已正确）、访问器 `is_enable_data_quality` 兜底（缺失键默认 `true`，已正确）、`how-to-config.md`（示例 + 参数表默认 `true`，已正确）、`requirements.md`/`technical.md`/`how-to-menu.md`（均默认开，已正确）——本次仅配置落盘为唯一残留，已修复。
- **验证**：`get_config()` 解析后 `is_enable_data_quality(cfg)` 为 `True`；dev-verify 1956 + 4 checks `--ci` 全 [OK]。

---

### 用户文档：说明报告 as-if 与独立 What-if 的区别（2026-08-07）

- **`faq.md`**：新增 Q&A「报告里的 as-if 和单独做的 What-if 有什么不同？」——两者定位（as-if 是组合历史走势的计算口径 / What-if 是两份持仓对比的独立功能）、唯一联系（What-if 时序回测复用 as-if 口径）、一句话总结，交叉链接 `reports-instruction.md` 对应章节。
- **`reports-instruction.md`**：`组合历史走势与回撤 → as-if 模拟` 小节末尾补「与调仓 What-if 的关系」说明——as-if 非独立功能，被 What-if 时序回测复用为底层算法，不指定生效日时 What-if 不涉及 as-if；并链接到 FAQ 新条目。
- **门禁**：dev-verify + 4 checks `--ci` 全 [OK]。

---

### 行业名剥离申万层级后缀：银行Ⅱ → 银行（2026-08-07）

- **`fetcher/industry.py` 新增 `strip_hierarchy_suffix`**：剥离行业名末尾的申万层级后缀（Ⅰ/Ⅱ/Ⅲ/Ⅳ，如「银行Ⅱ」「白酒Ⅱ」）。两类 provider（push2 f127 / 行情页 bk_name）均返回带后缀的申万原始名，统一在网关剥离，所有消费方（资产穿透TOP10 板块列 / 风格与因子分析 行业Beta / 基金风格分类 / LLM 关联标签 / TUI 单票查询）一致性受益；provider 层保持原始值（上游契约不变）。
- **三处归一化兜底**：`_industry_transform`（统一格式契约，缓存写入即干净）+ `fetch_industry_data` 出口（覆盖单查热缓存旧值）+ `batch_fetch_industry_data` 组装（覆盖批量热缓存旧值，缓存命中路径绕过 transform）。
- **测试**：`test_fetcher_industry.py` 新增 transform 剥离（银行Ⅱ/白酒Ⅱ/国有大型银行Ⅱ）、`strip_hierarchy_suffix` 纯函数、单查热缓存出口剥离、批量组装剥离共 7 例；`test_llm_prompts.py` 夹具与断言 `白酒Ⅱ → 白酒`（生产链路经网关已归一化）。provider 层 `test_eastmoney_industry_rest.py` 保持原始断言不动。
- **门禁**：dev-verify + 4 checks `--ci` 全 [OK]。

---

### 成本流水快照近似 + 文案重定位：零流水也能出价值（2026-08-07）

定位：用户维持最少量的输入，其余由应用来做——持仓 Excel 只维护 4 列快照即可，成本流水从「可选进阶增强」而非「必备手工输入」。

- **`analysis/cost_flow.py` 新增 `build_approximate_fund_flow_data`**：无交易/分红流水时，将持仓快照合成为「建仓日一次性买入」（日期取可选建仓日期，未配置则当日，XIRR 同日流水不可解 → 返回 None），复用 `build_fund_flow_data` 走单档成本分档（每份成本 vs 市价）。输出契约新增 `"approximate": true` 键（真实流水模式无此键，消费方 `.get("approximate")` → falsy 即 False），`__all__` 同步导出。
- **新增可选配置 `holdings_start_date`**（顶层，YYYY-MM-DD，默认空）：组合建仓日期，用于近似年化基准。`config/_config_defaults.py` 模板 + 注释、`config/_validation.py` 新增 `_validate_holdings_start_date`（空/缺失合法，非法格式告警不阻断）。
- **`report/excel_market_data.py` `_build_flow_data` 重写**：开关开启且既无交易也无分红 → 调用 `build_approximate_fund_flow_data`（新增 `_resolve_holdings_start_date` 读配置解析建仓日期，非法/缺失返回 None）；有流水仍走原 `build_fund_flow_data` 精确路径。
- **文案重定位（Excel + HTML 对齐）**：快照近似模式在「投资分析汇总」页签与 HTML 报告标注「资金加权收益率 (XIRR，近似)」，并写说明——「成本流水为可选进阶增强：当前未录入交易/分红流水，已用持仓快照近似计算成本分档（每份成本 vs 市价）」，未配置建仓日期时追加「请配置 config.json → holdings_start_date」提示；「已开启但无流水」旧占位文案降级为近似模式下的兜底分支。
- **测试**：`test_cost_flow.py` 新增 3 例（有建仓日期 → 近似 IRR ≈ 市值/成本−1 + 分档桶 + 分红不可用；无建仓日期 → XIRR None；空持仓 → available=False 但 approximate=True）；`test_excel_market_data.py` 重写无流水契约用例（断言近似入参 `(holdings, {}, start_date=None)`）+ 新增 `TestResolveHoldingsStartDate` 3 例；`test_summary.py`/`test_html_writer.py` 新增近似标签/说明/占位文案用例。
- **门禁**：dev-verify + 4 checks `--ci` 全 [OK]。

---

### 成本流水「已开启但无流水」说明补齐（Excel 对齐 HTML）（2026-08-07）

- **`report/summary.py` `_write_profit_summary`**：当成本流水子模块开启（`fund_flow_data` 非 None）但无可流水数据（`available=False`）时，在「资金加权收益率 (XIRR)」行下追加合并警告说明行——「成本流水子模块已开启，但持仓 Excel 未录入交易/分红流水，资金加权收益率 (XIRR)、成本分档、分红累计无法计算。如需启用，请在持仓 Excel 中补充「交易流水」「分红流水」页签后重新生成」，复用既有「行情不可用」警告样式（黄底红字），解释原因 + 修复指引。
- **`report_template.html`**：既有空态说明末尾追加同款修复指引，HTML/Excel 措辞对齐。
- **测试**：`test_summary.py` 新增 `test_flow_unavailable_note_written`（经 `ws.cell` value 参数断言说明文案）。
- **门禁**：dev-verify 1947 + 4 checks `--ci` 全 [OK]。

---

### 应用更名补漏：启动横幅 + 模块 docstring 统一应用名（2026-08-07）

- **启动脚本横幅**：`launch.sh` / `launch.ps1` 的「正在启动投资分析系统 …」改为「正在启动投资复盘助手 …」。shell 无法直接 import `constants.py`，按允许硬编码 + 注释注明与 `APP_NAME` 同步维护；`launch.ps1` 保持 UTF-8 with BOM + LF（git 历史即 BOM+LF，非本变更引入）。
- **模块 docstring**：`tui/tui.py` 模块 docstring「投资分析系统 — TUI 主入口」改为「投资复盘助手 — TUI 主入口」。
- **全量排查**：src/ 与 scripts/ 中「投资分析系统 / 小助手 / 投资分析报告生成工具」等近似应用名硬编码均已清除；剩余「个人投资」均为持仓文件名（`个人投资持仓信息.xlsx`）或「个人投资者」通用表述，非应用名。
- **门禁**：dev-verify 1947 + 4 checks `--ci` 全 [OK]。

---

### 应用更名「投资复盘助手」（2026-08-07）

- **`core/constants.py` `APP_NAME` 值由「个人投资分析报告生成小助手」改为「投资复盘助手」**：单一来源常量，一处修改即全链生效（TUI 首页 / 启动日志 / Web 首页 / HTML 报告 / Excel 报告 / What-if 报告 / cli/server 帮助描述 / test_runner 报告页脚）。
- **程序内散落旧名全部改为引用 `APP_NAME` 常量**：`cli.py`/`server.py` argparse description、`scripts/test_runner.py` 报告页脚（补 sys.path 注入 + `from src.python.core.constants import APP_NAME`）、`test_tui_menu.py` 断言（`assertIn(APP_NAME, …)` 替代硬编码字符串）。
- **文档全局替换**：README / CLAUDE.md / plan / testplan / requirements / technical / review-findings 标题与正文（R-TUI-01、rf-265 行）中的旧名统一改为「投资复盘助手」；`pyproject.toml` description 同步更新。
- **说明**：报告输出文件名（`个人投资分析报告.xlsx/html`）是报告产品名，不属于应用名，**不随更名变动**。

---

### 应用名称单一来源 + 各入口统一强调名称/版本（rf-265）（2026-08-06）

- **`core/constants.py` 新增 `APP_NAME = "投资复盘助手"`**：应用名称单一来源常量（零依赖模块，任何模块可直接引用），替代 TUI 首页硬编码。
- **应用启动日志**（`core/logger.py` `log_app_boundary`）：日志格式由「应用启动 | 版本 vX | 模式 | 主机 IP」改为「应用启动 | 投资复盘助手 vX | 模式 | 主机 IP」，CLI/TUI/Web 三入口启动/关闭日志统一强调名称+版本。
- **TUI 首页**（`tui_menu.py` `print_header`）：标题头由硬编码字符串改为引用 `APP_NAME`（`投资复盘助手  v{APP_VERSION}` 不变）。
- **Web 首页**（`web/handlers.py` `_handle_index` 传 `app_name` + `index.html`）：顶部 `<title>`/`<h1>` 改为应用名称，副标题前缀「v{app_version} ·」，浏览器标签页与页面头同时强调名称+版本。
- **HTML 报告首页**（`report_template.html` + `whatif_template.html`）：主报告头部加副标题「由 {app_name} v{app_version} 生成」，页脚改为「由 {app_name} v{app_version} 生成 · 个人投资分析报告 | 生成时间」；调仓 What-if 报告页脚加同款生成声明。
- **Excel 首页**（`report/summary.py` `_write_basic_info`）：投资分析汇总页签「统计时间/所属交易日」后新增「生成工具」行（`投资复盘助手 v0.10.12`）。
- **测试**：`test_summary.py` 新增 生成工具行 用例、`test_handlers.py` 新增 首页标题名称+版本 用例、`test_html_writer.py` 补 `app_name` 透传断言、`test_tui_menu.py` 补版本断言。
- **门禁**：相关 212 用例全绿 + dev-verify + 4 checks `--ci` 全 [OK]。

---

### Web 首页系统信息卡对齐 TUI 首页摘要（rf-264）（2026-08-06）

- **`web/handlers.py` `_build_system_info` 增补配置摘要字段**：在既有 程序版本/本机 IP/LLM 状态 基础上，对齐 TUI `show_config()` 首页摘要——持仓目录 / 持仓文件 / 输出目录 / 新闻抓取上限（`news_top_count`）/ 状态（`os.path.exists` 判定持仓文件是否就绪）/ 持仓匿名化模式（`features.anonymization.mode` 中文映射）/ 隐私声明是否已显示（`get_flag("_privacy_notice_shown")`）。配置读取异常按默认值兜底，不阻断页面渲染。
- **`web/templates/index.html` 系统信息卡片补对应行**：新增 持仓目录 / 持仓文件 / 输出目录 / 新闻抓取上限 / 状态（文件就绪绿 / 未找到红，语义色对齐 TUI `[OK]`/`[!!]`）/ 持仓匿名化 / 隐私声明 行，LLM 状态行保留原有 flat/multi/未配置 分支。
- **`web/static/style.css` 补 `.system-status-ok` / `.system-status-err`** 状态色样式。
- **`src/test/unit/web/test_handlers.py` `TestSystemInfo` 新增 6 用例**（unit_web 标记，web 目录 89 用例）：配置摘要默认兜底 / 字段齐全且文件就绪 / 文件缺失未就绪 / `get_config` 异常兜底 / 索引页渲染摘要（就绪 + 缺失两态）。
- **门禁**：web 目录 89/89 passed + smoke-web 9/9 + dev-verify + 4 checks `--ci` 全 [OK]。

---

## [0.10.13] - 2026-08-14

### perf_view 性能历史趋势查看并入 developer-guide.md（2026-08-08）

- **README「开发者参考」区 perf_view 独立入口删除**——`scripts/perf_view.py` 用法早已完整收录于 developer-guide「诊断类脚本」章节（读取 `data/state/perf_history.jsonl`、按版本+报告类型分组、`--report-type`/`--last`/`--save` 参数、输出列说明、数据来源），删除 README 重复表格行后该区仅剩 developer-guide 单一入口。
- **开发者指南入口描述补全**：新增「（含性能历史趋势查看 perf_view）」——入口行覆盖范围与 developer-guide 章节一致。
- **保留**：README 功能特性区「⚙️ 性能追踪与运维」下的「趋势查看工具」产品能力条目（与自动阶段计时/数据源健康检查并列，属产品总览非开发者参考）；`how-to-use-cli-mode.md` / `faq.md` 中用户视角的 perf_view 用法（用户手册，非开发者参考）。
- **folders.md 统计同步**：README 195→194 行，用户文档合计 4,759→4,758 行。

### 架构图布局修复（用户反馈「对齐不好的图有反作用」）（2026-08-08）

- **`architecture.svg` 右列报告卡底部对齐**——Excel/HTML 报告卡高度 150→154、y 修正，底部 428 与左列 Web 渠道卡、引擎底部对齐，消除 8px 错位。
- **`capabilities.svg`「HTML 报告」文字溢出容器**——修复「报告」两字跨出卡片右缘，文本重新排布并镜像复核（全部元素终点 < 容器右缘 980）。
- **`llm-chain.svg` 全量审计通过**，无需修改。
- **验证**：几何边界/对齐/重叠脚本 + cairosvg 渲染像素级文字溢出检测（docs-stm/tmp/svg-review/），确认三图无越界文字、无文本重叠。

### Web 数据源健康检查：全部被拒时追加代理诊断提示（2026-08-08）

- **回归背景**：另一台电脑 Web 模式全数据源 `[WinError 10061] 目标计算机积极拒绝连接` + 超时——`make_http_client` 经 `trust_env` 默认读取系统代理/HTTP(S)_PROXY，代理软件未运行即所有请求被路由到死代理。
- **后端**：`check_sources.run_health_checks` 全部失败且多数为「连接被拒」（WinError 10061 / Errno 111）时追加 `hint` 项（`_PROXY_HINT_NAME`），提示检查系统代理或清除代理环境变量；CLI `run_check_sources` 在汇总行后单独打印该提示。
- **前端**：`renderHealth` 渲染 `item.hint` 为整卡警示条（`.health-hint`，琥珀色描边）；健康检测按钮/接口不变。
- **回归测试**：`test_check_sources.py` 新增 `TestProxyHint` 3 用例（全拒追加 / 有源正常不追加 / 仅超时不追加）。

### Web 首页「历史运行记录」弱化为单行状态摘要（2026-08-08）

- **卡片标题**「历史运行记录」→「最近运行」；`renderHistory` 由多行列表（类型/条数/每条明细）重写为**单行摘要**——时间 + 状态（成功/有异常，`.`history-status-ok/err）+ 耗时（`.history-meta` 右对齐）。
- **取舍**：历史记录对单用户自用的真正价值是错误痕迹与耗时，类型/条数属装饰字段；状态区因此更紧凑，首页信息密度更聚焦。
- **样式**：移除 `.history-row/.history-type/.history-err` 旧列表样式，新增 `.history-summary/.history-status/.history-status-ok/err`；新增 `formatDur(sec)` 秒/分/时中文耗时格式化。
- **回归**：`/api/runs/history` 响应字段（timestamp/total_seconds/errors）与前端消费一致，web 单元测试 194 passed。

### 开发者指南整合：README 零碎 + 两份手册并入 developer-guide.md（2026-08-08）

- **新增管理文档 `docs-stm/managements/developer-guide.md`**（管理文档 9→10 份，纳入版本一致性受检）——整合四来源为开发者一站式指南，7 个部分：开发环境与工作流 / 三级门禁 / 任务编号规范与自动保障 / 测试指南 / 辅助脚本速查 / 版本发布流程 / 关键纪律来源。四来源 = README「开发者参考」区零碎内容（辅助脚本速查 / 性能历史趋势查看 / 跨机器耗时采集 / 任务编号自动保障）+ `how-to-test-my-code.md`（测试指南）+ `scripts-reference.md`（脚本参考）+ CLAUDE.md 开发纪律（门禁命令 / 编号规则 / 发布四步的人话版）。
- **锚点兼容**：保留 `#测试模式详解`、`#新增测试指南`、`#llm-幻觉率采样测试` 三锚点，testplan.md / faq.md 原有锚点引用不失效。
- **删除两份旧手册**：`docs-stm/manuals/how-to-test-my-code.md`、`docs-stm/manuals/scripts-reference.md`（内容并入 developer-guide，旧引用点全量迁移）。
- **引用点迁移**：README 开发者参考区精简（保留 developer-guide / registry / perf_view 三入口，删跨机器耗时 blockquote 与任务编号小节）；CLAUDE.md 管理文档清单补 developer-guide、用户文档清单删两手册；testplan.md（测试模式详解 / 新增测试指南）、faq.md（幻觉率采样）、how-to-start.md（辅助脚本参考链接）改指 developer-guide；`check-version-consistency.py` 受检登记 + `test_check_version_consistency.py` HEADER_DOCS 同步；folders.md 统计表（用户文档 14→12 文件 6,210→5,093 行、managements 9→10 文件 7,904→9,184 行）与目录树同步。

### 注册表使用说明并入 developer-guide.md（2026-08-08）

- **`docs-stm/manuals/how-to-use-registry.md` 内容并入 developer-guide** 新增「注册表使用（registry）」章节——核心数据结构（`DataModuleDef` / `ComputModuleDef`）、公共 API 速查（遍历 / 缓存 / LLM 名称 / settings 键 / enabled_llm 子键 / 报表排序 / 计算模块）、新增数据模块（非 LLM / LLM + 8 步检查清单 / 精确键名缓存）、计算模块注册表、无需手动维护的派生产出、测试。压缩易过时快照（注册表模块清单大表、19 键全表、消费方清单），架构背景与模块清单指向 `technical.md`「功能语义命名表」、report_section_order 键名对照指向 `how-to-config.md`。
- **删除旧手册** `docs-stm/manuals/how-to-use-registry.md`。
- **引用点迁移**：README 开发者参考区 registry 独立入口删除（并入 developer-guide，该区仅剩 developer-guide / perf_view 两入口）；CLAUDE.md 用户文档清单删 how-to-use-registry；folders.md 统计表（用户文档 12→11 文件 5,093→4,759 行、manuals 11→10 文件 4,897→4,564 行、managements 9,184→9,390 行）与目录树同步。

### Web 前端静态资产 404 修复 + 旧浏览器兼容兜底（rf-274 / rf-275）（2026-08-08）

- **阻断级修复：Web 前端整页失效（rf-274）**——Flask 未显式指定 `static_url_path` 时按 `static_folder` basename 推导（`src/static/web/` → `/web/*`），index.html 引用的 `/static/main.js`、`/static/style.css` 全部 404，JS/CSS 未加载 → 配置面板空白、健康区卡静态"正在检测"、生成报告按钮灰色。plan-27 前端资产移入 `src/static/` 时引入，移动后未在真实浏览器验证。
  - **修复**：`src/python/web/app.py` 显式 `static_url_path="/static"`（静态路由固定，不随目录名推导）。
  - **回归**：新增 `src/test/unit/web/test_web_static_serving.py` 3 用例（静态路由固定 /static + index.html 全部资产 200 + main.js 含初始化注册），修复前 `/static/*` 404 必然失败；连带补强 `scripts/smoke-web.py` 页面渲染检查——由仅查引用串存在升级为实际请求全部 `/static/*` 资产断言 200（原盲区：资产 404 时整页失效、冒烟仍误报通过）。
- **main.js 旧浏览器兼容兜底（rf-275）**——排查 rf-274 时发现：`AbortSignal.timeout`（Chrome 103+/Safari 16+ 起才有）缺失时 `fetch` 参数构造同步抛 TypeError，init 后续加载器全部静默不执行。修复：顶部补 `AbortSignal.timeout` 兼容兜底（AbortController+setTimeout，超旧环境退化 undefined 信号）+ init 三加载器 `safeRun` 隔离（任一初始化异常只渲染对应面板错误，不连带中断其余）。
- **验证**：node 模拟旧浏览器（无 AbortSignal.timeout）加载真实 main.js 完整走通 init；test_client 全链路 `/static/*` 200；web 单元测试 187+3 全绿。

### README 嵌入 SVG 架构图 + 排版优化（2026-08-07）

- **新增 3 张深色科技风架构图**（`src/static/`，手写 SVG，README 相对路径引用）：
  - `architecture.svg` — 首屏主图：TUI/CLI/Web 三渠道 → 分析引擎 → Excel/HTML 双报告，底部「同一套引擎 · 三种渠道 · 结果一致」。
  - `llm-chain.svg` — LLM 智囊团技术图：触发源 → 缓存指纹判定 → Provider Chain 链式分发（Claude/OpenAI/DeepSeek/Gemini）→ 四种分发策略 → 四类深度分析输出。
  - `capabilities.svg` — 八大功能域总览图：基础报告/新闻增强/LLM 智囊团/分析与风控/调仓 What-if/运维追踪/基金评价/隐私安全 2×4 网格 + 双报告输出条。
- **README 排版优化**：副标题精炼为一句话价值主张；3 张 SVG 分别嵌入首屏（架构图）、功能特性章节首（能力总览）、LLM 分析章节（Provider 链）；功能特性 8 个分组标题统一 emoji（🔍📰🤖📈🔄⚙️🏆🔒）。
- **`folders.md` 同步**：项目统计表新增「架构图示 SVG 3/315」行；目录树 `src/static/` 分支登记 3 个 SVG；README 行数 206→212、用户文档合计 6,204→6,210。
- **门禁**：XML 解析校验 3 个 SVG 合法 + 几何越界检查通过；P0 dev-verify 2005 passed；4 个 check 脚本 `--ci` [OK]。

### folders.md 目录树历史痕迹修正（rf-270）（2026-08-07）

- **过时计数修正**：① `smoke-web.py` 描述「test_client 9 项全链路验证」→ **11 项**（脚本自述「覆盖 11 项断言」+ 11 个 `_check_*` 函数，与 test_smoke_web.py 描述一致）；② `archived_plan.0.10.x.md` 描述「plan-17~25」→ **plan-17~26**（归档文件头 + plan.md 引用均为 plan-17~26）。
- **树形符号修正**：③ `tui/` 目录由 `└──` → `├──`（其后仍有 `web/` 兄弟节点）；④ `web-ui/` 目录由 `└──` → `├──`（其后仍有 `web-holdings-input-modes/`、`web-config-edit/`、`readme-svg-layout/` 兄弟节点）。保持「`├──` 后接兄弟、`└──` 为最后一项」的目录树层级符号规则。
- **门禁**：4 个 check 脚本 `--ci` [OK]（check-doc-traces / check-task-numbering 等）。

### 死代码清理：死配置 + 未用 import/变量/参数 + re-export 防护（2026-08-07）

- **死配置**：`cache_ttl.fund_overlap`（`config.json`）为唯一死配置——`get_ttl()` 先查 config `cache_ttl[data_type]`，差集无对应注册表 data_type，已移除。
- **A/B 类死代码（ruff --fix + 手动）**：清除 49+ 处未用 import/局部变量/重定义——覆盖 31 个文件（`_math_utils.py`/`alignment_correction.py`/`industry_beta.py`/`liquidity.py`/`metrics.py`/`rebalance.py`/`scenario.py`/`cache/operations.py`/`config/__init__.py`/`provider_registry.py`/`fetcher/batch.py`/`fetcher/bond_yield.py`/`llm/cost_tracker.py`/`llm/fact_checker/_numerical.py`/`llm/fallback.py`/`llm/generators.py`/`llm/prompts_core.py`/`llm/prompts_tables.py`/`llm/skeleton.py`/`providers/akshare_extras.py`/`providers/news_aggregator.py`/`providers/sina.py`/`providers/tiantian_base.py`/`report/_llm_news.py`/`report/_pipeline.py`/`report/_report_generation.py`/`report/_snapshot.py`/`report/data_quality_sheet.py`/`tui/tui_handlers.py` 等）。含 5 处被本地重定义覆盖的冗余 import（`metrics.py` 4 常量 + `provider_registry.py` 本地 sentinel/类）。
- **D 类 re-export 防护**：`cache/__init__.py` 补 `__all__`（11 个内部符号：`_read_cache_data`/`_write_atomic`/`_CACHE_DIR`/`_cache_path` 等）；`config/__init__.py` 补 `__all__`（`get_llm_config`/`_CONFIG_PATH_OVERRIDE`）——保证 re-export API 不被静态扫描误删。
- **re-export 误删修复（ruff --fix 连带，恢复 + `# noqa: F401`）**：`providers/tiantian_base.py` 恢复 `_safe_float`（`tiantian_nav`/`tiantian_ranking` 引用）；`analysis/rebalance.py` 恢复 `_SILENCE_FILE`/`_load_silence_state`/`_save_silence_state`（conftest monkeypatch + 测试引用）；`core/provider_registry.py` 恢复 `phase_timeout`（test_phase_timeout 引用）；`providers/sina.py` 恢复 `is_index_code`（`sina_kline` lazy import + 测试 patch）；`analysis/metrics.py` 恢复 `_t_cdf`/`_t_critical_95`（test_metrics_edge 引用）。
- **scenario 死参数（rf-271，方案 A）**：`scenario_analysis.portfolio_volatility`/`sharpe_ci_propagation.annual_volatility` 加 `# noqa: ARG001` 标注预留意图，不破坏测试签名。
- **遗留文件确认**：`report/_pipeline.py` 为文档标注「不再承载活代码」的遗留重复文件（编排实现在 `_report_generation.py` 聚合门面），仅删其未用 `Future` import，未做进一步改动。
- **门禁**：P0 dev-verify **2005 passed**；4 个 check 脚本 `--ci` [OK]；ruff format 本轮改动文件全绿。登记 rf-271/rf-272 待跟进（scenario 死参数补齐评估 + 43 处 ARG001 死参数评估）。

### 死代码清理（二）：ARG001 死参数全数处置（rf-272 完成）（2026-08-07）

- **删参 21 处**（生产 18 函数 + 连带 40+ 调用点/测试）：`metrics_risk.portfolio_beta.trading_days`、`fetcher/industry.batch_fetch_industry_data.max_workers`、`fetcher/chain.fetch_with_incremental_fallback.param_fn`、`cost_flow.compute_cost_tiers.holdings`、`liquidity._is_exchange_traded.name`、`_history_quality._diagnose_return.sorted_dates`、`excel_fund_deep_analysis._process_fund_deep_analysis_module.process_fn/prog`、`chart_data_builder.build_chart_datasets.perf_data`、`orchestrator.compute_valuation_data.holdings`、`_report_health._spawn_health_checks.holdings`、`handlers_config._add/_remove_comparison_index.config`、`handlers_report._prompt_history.reporter`、`check_sources._check_http.name/label`（连带 `_checks` 10 个 lambda 简化）、`prompts_action._build_global_macro_prompt.holdings_details`、`market_value_sheet.write_market_value_sheet.holdings/today_str`（连带 `excel_market_data` 别名调用 2 处）、`config/_llm_providers._validate_provider_entry.index`、`_report_helpers._compute_details.config`。
- **契约保留 7 处加 `# noqa: ARG001`**（注明保留理由）：`providers/sina_kline.py` 2×`start_from`（chain 层经 `getattr` 无条件传参契约）、`config/_llm_settings.is_enable_llm.config`（`is_enable_*` 家族统一签名 12 成员同构）、`style_factor_sheet._compute_ncols` 3×（参数声明计算覆盖的三区块，设计契约）、`liquidity.check_liquidity.total_mv`（公开 API 契约，22 处调用点传参）。
- **独立项不纳入本轮**：`html_renderers._render_llm_content_section` 13 参渲染器上下文（删除需重构 html_writer.py 调用点，单列「签名瘦身」项）；`_pipeline.py` 遗留重复文件清理（单列重构项，现有测试引用其辅助函数）；`orchestrator.generate_report.warm_cache`（CLI `--warm` 标志已无实际消费路径，去留待决策）。
- **新增 F841 连带清理**：`handlers_report._cmd_generate_both` 未用局部 `reporter`、`test_market_value_sheet` 未用局部 `result`、`test_handlers_report` 7 处未用 `reporter`。
- **门禁**：P0 dev-verify **2005 passed**；4 个 check 脚本 `--ci` [OK]；ruff format 本轮改动 7 文件全绿。rf-272 完成（43 处全数处置），rf-next 保持 273。

### scenario 死参数删除：portfolio_volatility / annual_volatility（rf-271 完成）（2026-08-07）

- **背景**：rf-271 登记时按「死参数预留」处置（保留 + `# noqa: ARG001`）。本次深入评估发现三层问题——① 两参数确实从未消费（`scenario_analysis().portfolio_volatility` docstring 承诺 ±1σ/±2σ 波动率区间但函数体不引用，2 处调用点已传 `annualized_volatility` 被吞；`sharpe_ci_propagation().annual_volatility` 被 Lo(2002) 常数近似公式绕过）；② 死的不止参数——`_build_scenario_entry` 计算的 `vol_1sigma/vol_2sigma` 4 字段与 `ci_lower/ci_upper` 4 字段**全仓零消费**，`scenario_analysis` 输出唯一消费方 `prompts_tables._build_scenario_block` 只读点估计 `expected_change_pct`；③ `sharpe_ci_propagation` 无生产调用（仅测试 + `analysis/__init__.py` 导出）。
- **设计意图核对**：归档 P4-03 承诺「在 LLM prompt 表述 *若市场下跌 20%，组合预计回撤 -16% 至 -24%（95% 置信区间）*」——该 CI 区间从未进入任何 prompt/报告输出，属**半实现**；波动率区间功能连计算都未落地（参数被吞）。用户从未见过 CI/波动率区间输出。
- **处置（方向 2：删除）**：`scenario_analysis` 删 `portfolio_volatility`（同步 `_full_risk_metrics.py`/`_pipeline.py` 2 调用点）；`sharpe_ci_propagation` 删 `annual_volatility`（签名变 `(sharpe_ratio, years_of_data, n_observations)`，同步 test_scenario_analysis.py 7 处位置传参 + test_e2e_perf.py 关键字传参）；docstring 与模块 docstring 诚实化（「年化波动率 CI → 夏普 CI」修正为「Lo 常数近似，不消费年化波动率」）。
- **保留**：`_build_scenario_entry` 的 `vol_*`/CI 结构化输出字段（由 `beta_se`/`beta_ci` 驱动，语义为「Beta 估计不确定性传播」，与已删的 `portfolio_volatility` 是不同概念；未来渲染层可直接消费）。
- **验证**：test_scenario_analysis.py + test_e2e_perf.py 共 32 用例全绿；无 `portfolio_volatility`/`annual_volatility` 残留引用；ruff format 干净。rf-271 完成，rf-next 保持 273。

### 关闭日志流竞态修复：`_ClosedStreamSilentHandler`（rf-273 完成）（2026-08-07）

- **背景**：全量测试（mode all，5433 用例）进程退出阶段出现 `--- Logging error ---` 噪声。根因——`tui.py` 模块级 `atexit.register(log_app_boundary, "关闭", "TUI模式")` 在任何导入 tui 模块的测试进程退出时触发，此时 pytest 已关闭 sys.stderr，console `StreamHandler`（默认绑 stderr）emit 抛 `ValueError: I/O operation on closed file`，logging 默认 `handleError` 打印 `--- Logging error ---` + traceback。无害（测试全绿）但污染每次全量测试输出。
- **修复**：`core/logger.py` 新增 `_ClosedStreamSilentHandler`（`logging.StreamHandler` 子类，覆盖 `handleError`——仅当异常为 `ValueError/OSError` 且含 "closed file"（退出竞态）时静默降级，其余日志错误照常由父类报告）；`setup_logger` 控制台 handler 换用该类。
- **回归测试**：新增 `src/test/unit/core/test_logger.py` 4 用例（unit_core 标记）——关闭流 emit 不打印 error / handleError 对 closed file 静默不委托父类 / 对其他错误照常委托 / setup_logger 控制台 handler 类型断言。
- **验证**：全量 mode all **5437 passed, 0 failed**（新增 4 用例），`--- Logging error ---` 消失；dev-verify 2009 passed；ruff format/lint 干净；4 check 脚本 `--ci` [OK]。rf-273 完成，rf-next 递增为 274。

---

## [0.10.14] - 2026-08-17

### 版本发布 v0.10.14（2026-08-17）

- **发布流程**：P2 发布门禁通过（`test-runner --mode verify,regression` 3710 通过 0 失败 + code/doc/task-numbering/semantic-index 四检查全绿 + 发布手动验证 `--mode perf,security` 14 通过）；版本号全链一致化至 v0.10.14（constants.py / pyproject.toml / README / 10 份管理文档）；发布数据文档刷新（test-coverage.md / folders.md / datasource 文档核对）。
- **test-coverage.md `all_no_unit` 修正（rf-288 登记）**：发布前刷新发现模式对应测试量表 `all_no_unit` 被 bench 回填为 323（含 opt-in live 套件），而 `all`(5533) = `unit`(5224) + `all_no_unit`(309) 数学自洽证明 309 为正确口径——`test-runner.py` MODES `all_no_unit: "not unit"` 覆盖 pytest.ini `addopts = -m "not live"`，使 14 项 live 真实网络套件卷入。已按 collect-test-coverage.py 口径将表值修正为 309，并登记 rf-288 待修复（marker 补 `and not live`）。

### docs-stm/tmp 有价值脚本迁移至 scripts/ + 归档（2026-08-17）

- **有复用价值脚本迁入 `scripts/`**（此前在 git 忽略的临时区，无法留存/共享）：`reproduce_factcheck_corrections.py`（事实校验自动修正复现脚本）+ `check-svg-geom.py`/`check-svg-pixel.py`/`check-svg-text-overflow.py`（README SVG 架构图检查三件套，未来改架构图可复用）。4 脚本语法验证通过，`reproduce_factcheck_corrections.py` 的 `sys.path`（`../..`）在 scripts/ 下仍正确解析项目根。**后续（v0.10.15-dev）重新评估后判定其一次性排查属性，已删除**（见 changelog 当前版本「scripts/ 命名统一与清理」条目）。
- **dedup 校准分析报告迁入归档区**：`cross_merge_bg2_review.md`/`dedup-calibration-report.md`/`dedup-review.md` → `docs-stm/archive/v0.10.x/dedup-calibration/`（rf-279/280 校准结论的依据与逐条样本，原 tmp 位置 git 忽略无法追溯）。
- **清理低价值临时产物**：一次性迁移/清理脚本（migrate_*/clean_*）、被正式工具取代的 _extract_fails/_parse_report、覆盖历史快照（coverage-*.txt）、可再生产物（rf113 报告副本 + svg 渲染 png/jpg）、`__pycache__` 全数删除；docs-stm/tmp 现为空目录（git 忽略）。
- **文档同步**：folders.md 目录树 scripts/ 补 4 脚本 + archive/ 补 dedup-calibration/，统计刷新（辅助脚本 19→23 / 7,106→7,394；archive 106→109 / 37,373→37,689；项目文档 45,933→46,249）。

### 自审记录四次合并：已解决项迁入归档（2026-08-17）

- **review-findings.md 已解决区清空**：v0.10.14 已解决项（rf-282 ~ rf-287）随四次合并整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md` v0.10.14 章节（延续 dev 批次提前归档惯例，三次合并 rf-276~281 先例）。原文件仅保留归档引用 + 待办区（rf-75~89 文件过长、rf-113/114 交互图表技术债、rf-257 Web 真机验收）。
- **对应迭代计划状态**：rf-282~287 均为维护性修复（rf-272 衍生死参/遗留清理 + smoke-web CI 竞态 + bench 菜单键集 + 测试标记体系漂移），非 plan-* 迭代项，plan.md 无变更。
- **变更记录**：各 rf 修复详情已在 [0.10.14] 各条目（死参数/遗留清理、Web 冒烟竞态、bench 回写、perf/security 定向 mode）；归档文件「归档说明」补四次合并记录。

### 补 perf/security 定向 mode + 测试标记体系清理（2026-08-17）

- **新增 `--mode perf` / `--mode security`**：`scenario_perf`（端到端性能基准，5 项）与 `scenario_security`（安全基线，9 项）此前仅有 `collect-test-coverage.py` 能计数、`test-runner.py` 无对应定向 mode（只能靠裸 `-m` 或 `all` 触发）。现补齐定向 mode（`--help` 可见、可进标准 HTML 报告管线），并同步 `collect-test-coverage.py` 模式对应测试量枚举。二者仍为「独立标记、不入门禁、不进 bench」，按既定设计保留手动/发布前运行；testplan.md §6.3 P2 门禁追加**发布手动验证**项：`--mode perf,security`。
- **清理死注册 `unit_config_edge`**：conftest 的 `_KNOWN_MARKERS` + `pytest_configure` 注册了它但全仓 0 用例（config 的 edge 测试已归入 `unit_config`+`edge`）。移除两处注册，无行为影响。
- **顺带修复 rf-287**：`check-test-markers.py` 标记合规检查的 `KNOWN_MARKERS` 与 conftest 漂移——缺 `unit_web`/`integration_cli`/`live` 三个实际在用的标记，误报 17 处「未注册标记」、退出码 1（非门禁脚本，日常门禁未暴露）。按 conftest 对齐后 277 文件 0 违规恢复通过。
- **验证**：check-test-markers 0 违规；collect-test-coverage 输出 perf:5 / security:9；`--mode perf,security` 实跑通过（见下节）。

### bench --update-docs 同步回写模式对应测试量 + 顺带修复菜单键集缺陷（2026-08-16）

- **功能**：`--mode bench --update-docs` 在更新环境耗时对照两表（采集环境属性 + 各模式耗时）之外，同步回写「模式对应测试量」表——覆盖项数 = pytest 实测执行计数（passed+failed+skipped+errors，含参数化展开），典型耗时 = 本机实测约值；未实测/超时模式保留原值。此前该表为 `collect-test-coverage.py` 静态快照，需人工回填易过期（实测由静态 5218/5527 刷新至 5224/5533）。
- **实现**：`test-runner.py` 新增 `_DOC_MODE_COUNT_MARKERS` 标记对 + `_update_mode_count_table()` 纯函数，接入 `_update_test_coverage_doc`；test-coverage.md「模式对应测试量」表套标记并修正注释（原「不含参数化展开」表述与实际 collect 口径不符——collect 计数含参数化展开）。行覆盖率仍走独立 `--coverage` 参数，不并入 bench（插桩会拖慢实测且分段覆盖会重复计数）。
- **顺带修复 rf-286**：bench 全量跑暴露 `test_menu_key_coverage` 菜单键集断言未同步日志可视化新增键——`MENU_ITEMS` 自加 `[V]`/`[H]` 后 19 键，断言仍为旧 17 键，`integration`/`all_no_unit`/`all` 模式必失败（integration 不在 P0 门禁内，全量跑才暴露）。修复：期望集补 `V`/`H`，集成/全量模式复跑通过。
- **验证**：dev-verify 2056 通过；bench 全量 5533 项仅 rf-286 1 例失败（修复前），修复后 integration 281 / all_no_unit 323 / all 5533 全绿；doc_writer 单测新增 3 例模式计数表覆盖，44 例通过。

### Web 冒烟脚本竞态修复 + CI 格式门禁修复（2026-08-16）

GitHub Actions 上报两项失败，均已修复：

- **smoke-web.py 竞态（TemporaryDirectory `Directory not empty`）**：`test_smoke_web_run_smoke_all_pass` 偶发失败——`_check_formal_use_existing` 提交第二个 run（正式-用存量，202）后不轮询终态，`run_smoke()` 立即退出临时目录上下文；run 由后台 worker 线程（`web_run`，daemon）异步执行，退出时仍在写 `output/个人投资分析报告.xlsx`，`TemporaryDirectory` 清理撞上并发写（`OSError: Directory not empty`）。CI 并行调度（worker=2）放大竞态窗口，本地偶发、CI 高频。
  **修复**：抽 `_poll_run_finished(client, run_id)` 轮询 helper，正式-用存量 run 提交后同样轮询至终态（done/failed），`_check_progress_events` 复用；断言语义不变（仍验证 202 + run_id），仅消除竞态窗口。回归测试新增 3 例（轮询至 done / failed / 永不到终态返回最后 status），本地 8 次连跑稳定。
- **ruff format 11 文件格式不一致**：CI `ruff format --check src/python/ scripts/` 报 11 个历史文件需格式化——`scripts/` 6 个（calibrate-dedup-threshold / check-code-traces / check-semantic-index / check-version-consistency / install-claude-hook / probe-push2）+ `src/python/` 5 个（llm/fact_checker/_constants、_utils、llm/strategy、report/category、schemas/history）。均为纯格式调整（frozenset 折叠、多行参数合并等），无逻辑变更；修复后 `ruff format --check src/python/ scripts/` 全 263 文件通过。
- **验证**：dev-verify 2053 通过（含 smoke-web 回归新增 3 例），0 失败。

### 日志可视化三端实现：CLI + TUI + Web（2026-08-16）

实现 plan-10「日志可视化」（P4 实验功能）：三端均提供结构化日志查看，数据源健康历史接线展示。核心解析/聚合逻辑全部集中在核心层，CLI/TUI/Web 仅做薄展示。

- **核心层 `core/log_reader.py`（新）**：三端共享的日志读取模块——`parse_log`（按时间戳切分记录，续行/traceback 归并，装饰性横幅识别 `is_decorative`）、`tail_log`（从文件尾部反向分块读取，64KB chunk，>100MB 大日志不卡顿）、`read_log`（级别阈值过滤 / since-until 时间前缀过滤，无效级别抛 ValueError）。日志路径惰性引用 `logger._LOG_FILE`，不硬编码。`LogEntry` 不可变 dataclass，`to_dict()` 供 Web JSON 序列化。
- **核心层 `core/perf.py`**：新增 `summarize_health_history(limit=10)`——聚合 `data/state/datasource_health.jsonl` 为最近 N 次运行摘要（含 ok/total、失败源清单），接线此前零调用者的 `load_health_history`。
- **CLI**：新增 `view-logs` 子命令（`--level`/`--lines`/`--since`/`--until`），在 `init_config` 之前分派——配置损坏时仍可查日志诊断；输出每条 `time [LEVEL] message`，多行 body 缩进展示。
- **TUI**：菜单新增「V 查看最近运行日志（可按级别筛选）」「H 查看数据源健康历史（近期检查记录）」两项（17→19 项）；`handlers_log.py` 按级别筛选、ERROR 红/WARNING 黄着色（NO_COLOR/TTY 检测自动降级为无着色）、traceback 折叠为「⤷ 堆栈详情 +N 行」。
- **Web**：后端新增 `GET /api/logs`（级别校验→400 / lines clamp [1,5000] / since-until 透传 / 读取失败→500）与 `GET /api/health/history`；前端「⑦ 日志查看」卡手动加载（不自动轮询，对齐设计文档「自动刷新高 IO → 手动刷新」），`<details>` 原生折叠 + 级别配色，全程 `textContent`（XSS 纪律）。
- **回归测试**：新增 `test_log_reader.py` 21 例 + `test_handlers_log.py` 10 例 + `test_tui_menu.py` 更新（V/H 项）+ `test_cli.py` 扩展 10 例 + `test_handlers.py` 扩展 10 例，全部标注 pytest marker、隔离不触真实数据路径。
- **文档同步**：
  - technical.md §6.7 语义命名表新增 `log_reader`/`view_logs`/`health_history` 3 行；§1.7/1.8 三端结构（CLI 子命令 4→5、TUI 菜单 17→19、Web 路由 + `/api/logs` + `/api/health/history`）与 §6.3/6.4 已同步。
  - requirements.md 新增 §3.5「日志可视化（诊断）」R-DIAG-01~03（CLI view-logs / TUI V+H / Web ⑦ 日志卡 + API）；§3.2 菜单表新增「诊断」组（[V]/[H]）；R-TUI-02 菜单数 17→19。
  - 三渠道用户手册：CLI 手册新增 §7 `view-logs` 子命令章节（参数表+示例）并重编号 7-13、§9 速查表加行；TUI 手册主菜单总览加 [V]/[H] + 新增「诊断类」详解；Web 手册首页 6→7 卡片区 + 新增 §6 日志查看区；how-to-start/faq/README 子命令清单加 view-logs、定时任务引用 §11→§12。
  - folders.md 目录树 + 统计刷新；plan.md plan-10 归档至 `archive/v0.10.x/log-visualization/`。
  - **顺带修复 rf-284 文档同步缺口**：CLI 手册残留的 `--warm` 标志说明（参数表/示例/缓存预热章节）已删除——rf-284 删除代码后用户文档未跟上，现与 `cli.py` 一致。
- **已确认覆盖不改代码**：「报告尾部数据源状态表」已由 `data_source_matrix`（registry.py section 18）在 HTML+Excel 双端渲染，与设计意图吻合。

### 死参数/遗留文件清理：html 渲染签名瘦身 + 遗留重复文件删除 + warm_cache 移除（2026-08-16）

三项自审独立跟踪项（rf-282/283/284，源自 rf-272 全仓 ARG001 死参数处置后遗留）一并收尾：

- **rf-282 渲染器签名瘦身**：`html_renderers._render_llm_content_section` 上下文参数从 15 个删至 2 个（`enable_llm`/`llm_content`）。函数职责仅为解包预生成的 4 元组 + 开关判定；其余 13 参（force_llm/a_indices/us_indices/总额/持仓/穿透/板块资金流等）均由编排层预置或由下游直接读取，属死参数。同步重构 `html_writer.py` 调用点。
- **rf-283 遗留重复文件删除**：`report/_pipeline.py`（25KB，标注「遗留重复文件」）确认为死代码副本——零生产引用，活代码在 `report/_llm_news.py`。删除文件（`git rm`），`test_pipeline_utils.py` 测试迁移至活模块 `_llm_news.py`（`_collect_llm_future_result`/`_collect_news_future_result`/`_report_llm_module_results`），防双份漂移。
- **rf-284 warm_cache 移除**：`orchestrator.generate_report.warm_cache` 参数声明但函数体内从未使用，唯一传入方是 CLI `--warm` 标志（web/TUI 不消费；TUI 新资产预热走独立 `check_and_warm_for_new_assets` 机制）。删除 `--warm` 标志 + `warm_cache` 参数 + 测试中 6 处引用同步清理。
- **验证**：`test_pipeline_utils.py` 6 例通过；report+cli 全量单元测试 1596 例通过。
- **自审登记**：review-findings.md 三项（rf-282/283/284）由 P3 待办区转「已解决」区。

### extract-test-failures.py 修复：pytest-html 报告解析崩溃（2026-08-16）

- **缺陷（rf-281）**：`_find_json_blob` 用手工花括号扫描器提取 `data-jsonblob`，假设 JSON 引号以反斜杠转义；但 pytest-html 将 JSON 内引号编码为 HTML 实体 `&#34;`，扫描器从不进入字符串态，日志内嵌 HTML 的 `}` 在 depth==0 时提前截断 → `json.loads` 报 `JSONDecodeError: Extra data`，**全绿报告也崩溃**，导致依赖此工具的失败用例提取流程不可用。
- **修复**：改为按属性值整体截取——`data-jsonblob=` 起始引号到下一个裸引号之间即为完整 JSON（blob 内引号均为实体编码，不会出现裸引号提前终止属性），取回后统一解码 `&#34;/&gt;/&lt;/&amp;`。
- **回归测试**：新增 `src/test/unit/scripts/test_extract_test_failures.py` 4 例——实体引号 blob 完整提取且 JSON 可解析 / 日志内嵌花括号不干扰 / 无 data-jsonblob 返回 None / 属性无结束引号返回 None 不崩溃。已验证全绿报告 `--summary` 汇总正常、失败报告与 `--json` 输出均正常。
- **测试统计同步**：按 `scripts/collect-test-coverage.py` 实时收集快照（总 5474）同步 `test-coverage.md`（模式总计 `all` 5461→5474、`unit`→5165、`verify`→3433、`dev-verify`→2019、`standard`→4487；unit 子标记 `unit_llm` 754→760、`unit_news` 188→191、`unit_scripts` 190→194；跨类 `llm` 609→615，其中 llm/news 增量来自 e777ca5f/4c4e156b 新增用例）与 `folders.md`（测试代码 306→307 文件、86,228→86,536 行；测试用例 5,461→5,474 个）。
- **自审登记**：review-findings.md 新增 rf-281 已解决条目。

### dedup 校准脚本路径修复 + 基于最新数据重校准（2026-08-16）

- **路径不一致（rf-279）**：`scripts/calibrate-dedup-threshold.py` 默认读取 `data/cache/dedup_anchors.jsonl`，而 `src/python/providers/news_dedup.py` 自 commit `4e95d595`（2026-07-30）起将锚点写入 `data/calibration/dedup_anchors.jsonl`，脚本从未同步 → 校准报告基于 7-29 旧快照（119654 条），与当前去重行为脱节。修复：脚本默认 `--file` 路径改为 `data/calibration/dedup_anchors.jsonl`，与代码写入路径一致。
- **重校准结论（基于最新 109018 条锚点）**：
  - cross_skip 总量 20785 条，但 87% 为 bg=0/1（无实体重叠的安全跳过）；真实漏判候选 bg≥2 有 2239 条，与旧数据（2154）持平，未恶化。
  - **维持现阈值**：bg=2 ratio≥0.35 的 523 条候选抽样人工审查，真实重复率仅约 25%（多为"关税退款""A股白酒领涨""原油上涨"等，其余为不同公司回购/财报/目标价误判候选）。降到 0.35 会误合并约 390 条不同事件，不值得。当前 bg=2 ratio≥0.40 梯度补偿已捕获 196 条高置信重复。
  - 跨源 bigram≥4（4753 条）与同源 bigram≥4 阈值安全；跨源 bigram=3 边界 2418 条中仅 354 条 ratio≥0.40，降阈值需求不大。
  - 可选优化（非本次必改）：bg≤1 ratio≥0.40 虚高噪声从 82→1468 条（+18x），是共享日期/事件名/财经关键词导致的 SequenceMatcher 比率虚高，可进一步改进归一化。
- **自审登记**：review-findings.md 新增 rf-279 已解决条目。

### dedup 锚点重复计数修复：写入层 + 统计层双重去重（2026-08-16）

重校准中发现锚点文件同一对 (source,title) 多轮运行重复追加（实测 61.6% 为重复记录，同一对最多重复 63 次），导致校准报告绝对数字严重失真（cross_skip bg=0 从真实 279 虚增至 13800）。修复为写入层 + 统计层双重去重：

- **写入层去重（`news_dedup.py`）**：新增进程级 `_WRITTEN_ANCHOR_KEYS` 已写 key 集合 + `_load_written_keys()` 惰性加载（首次 flush 前读一次现有文件，~110k 行/35MB 一次性成本），`_flush_anchors` 写入前按 `_anchor_key`（source 对 + 标题对，顺序无关）比对，只写新 key、写后入集合 → 跨会话、跨轮次拦截重复，无需每次读全文件。
- **统计层去重（`calibrate-dedup-threshold.py`）**：`load_anchors` 按 (source_a, source_b, title_a, title_b) 顺序无关 key 去重，处理存量污染文件 → 校准锚点 109018→41761 条。
- **测试隔离**：conftest 增加 `_ANCHOR_PATH` 路径重定向（`_isolate_sensitive_paths`）+ `_auto_reset_anchor_state` autouse fixture 重置锚点单例；`test_news_sources.py` 新增 `TestFlushAnchorsDedup` 3 例（同对跨轮只写一次 / 不同对正常追加 / key 集合缓存生效）。
- **自审登记**：review-findings.md 新增 rf-280 已解决条目。

### fact_checker 校验层修复：条件阈值误修正 + 持仓简称匹配漏检（2026-08-16）

排查 601939「130.61%」/600900「200%」两处报告数值时定位到 fact_checker 两处缺陷，均已修复并配回归测试：

- **条件阈值误修正（rf-277）**：穿透深度分析原文「收益率超过 200% 后可考虑部分止盈」中的 200% 是**止盈目标阈值**（非对 600900 当前收益率的陈述），旧逻辑因"止盈"位于数值之后较远处（超出 `_TRIM_TARGET_KEYWORDS` 的 [-15,+5] 邻近窗口）未命中止盈语境，误将 200% 归因到最近名称"长江电力(600900)"并修正为 59.2%——把正确文本改错。修复：`_constants.py` 新增 `_CONDITION_TRIGGER_KEYWORDS`（超过/达到/突破/接近/降至等），`_context._is_trim_target_context` 增加「触发词（前 12 字符）+ 后置调仓动作词（后 25 字符）」双条件联合判定；仅有触发词无动作词（如"收益率超过200%，风险很大"）仍按收益率校验，不过度跳过。
- **持仓简称匹配漏检（rf-278）**：辩论综合原文「华安纳指+180.5%、建设银行+180.55%」——华安纳指（040046）实际收益率 130.61%，LLM 反向串位写成 180.5%；旧逻辑 `_locate_subject_code` 仅按持仓全名匹配，"华安纳指"匹配不到"华安纳斯达克100ETF联接基金A" → 主体定位失败回退全局最近邻，180.5 恰命中 601939 真实值 180.55 → 误判通过、反向串位漏检。修复：`_constants.py` 新增 `_NAME_ALIAS_MAP` 简称归一化表（纳指→纳斯达克、建行→建设银行等），`_utils._locate_subject_code` 增加归一化后按持仓名称核心名（`_extract_core_name`，首个 ASCII 字母/数字前汉字部分）前缀匹配，归因到实际品种。
- **回归测试**：`test_fact_checker.py` 新增 `TestTrimTargetContext` 2 例（条件阈值不误修正 + 无动作词仍校验）+ 新增 `TestNameAliasNormalized` 4 例（华安纳指错误值修正/正确值通过/建行简称不误伤/run_fact_check 整链路）；全量 115 例通过。
- **自审登记**：review-findings.md 新增 rf-277 / rf-278 已解决条目。

### LLM 定价支持 DeepSeek 峰谷定价 + 时段可配置（2026-08-15）

- **定价更新**：`MODEL_PRICING` 中 `deepseek-v4-flash` / `deepseek-v4-pro` / `deepseek-chat` 三模型按 DeepSeek 官方 2026-08-17 峰谷定价更新——base（闲时）价 + 新增 `peak` 高峰价子段（闲时价 ×2）。如 flash：输入 ¥1.5/输出 ¥4.5/缓存命中 ¥0.05，高峰 ¥3/¥9/¥0.10。
- **峰谷时段**：新增 `PRICING_PEAK_PERIODS` / `PRICING_IDLE_PERIODS` / `PRICING_TIMEZONE` 常量（默认高峰北京时间 09:00–12:00、14:00–18:00，闲时为其外全部时间），`estimate_cost()` 新增 `at_time` 参数按时段计费（缺省当前时间、按定价时区换算，naive 视为已在定价时区便于测试）。
- **配置可覆盖**：`llm_settings.json → pricing` 段新增 `timezone` / `peak_periods` / `idle_periods` 三个非模型键，时段与时区可自定义；模型条目可携带 `peak` 子段覆盖高峰价。`reload_pricing()` 就地更新时段列表，保持对象身份稳定。
- **回归测试**：`TestPricing` 新增 6 例峰谷用例（高峰/闲时价差、边界闭区间、无 peak 模型不受时段影响、缓存命中按 peak 费率、默认时段、自定义时段+模型价格覆盖）。
- **文档同步**：`how-to-config-llm.md` 定价表与 Token 消耗参考按新价更新 + 峰谷说明；`llm-technical.md` §10 新增峰谷定价小节、附录 B 定价表更新。

### v0.10.1+ 改动文档一致性审计修复（2026-08-15）

- **A 类事实错误**：README `enable_action` 默认值修正（默认开、菜单 P 可切换，原误述为默认关）；folders.md 统计与目录树同步 6 个新测试文件（`test_llm_settings`、`test_history_snapshot_namespace{,_edge}`、`test_snapshot_namespace_consumers`、`test_holdings_update{,_edge}`）；reports-instruction 浮盈/已实现盈亏文案修正。
- **B 类用户文档缺口**：reports-instruction 补完整「成本流水分析」章节（开关 `report_submodules.cost_lots`、交易/分红流水表头、XIRR/成本分档/分红累计输出、快照近似模式文案）+ HTML TOC 加 LLM 标记说明；how-to-use-web-mode 补数据源健康代理诊断提示与产物写锁检测说明；datasource 补行业名归一化说明（剥离申万 Ⅰ~Ⅳ 后缀）；how-to-config `history.fetch_mode=off` 行补警告行为说明；how-to-start 持仓文件格式补可选流水页签块引用；faq 已实现盈亏答案引用 XIRR/cost_lots。
- **C 类管理文档**：requirements 新增 R-ENV-05（CLI 包装脚本 cli.sh/cli.ps1）、R-WEB-09（Web 试算隔离）、§6.4.20 成本流水（R-CFL-01~04）、增强 R-OUT-07（report_section_order 细节）；technical 新增 §1.7.6 便捷入口包装脚本、语义命名表补 `report_section_order`/`generators_news` 行；test-coverage 测试计数快照刷新至实时值（`all` 5,455→5,461）。
- **自审登记**：review-findings.md 新增 rf-276 已解决条目。

---


## [0.10.15] - 2026-08-29

### 版本发布 v0.10.15（2026-08-29）

- **发布流程**：P2 发布门禁通过（`test-runner --mode verify,regression` 3737 通过 0 失败 + code/doc/task-numbering/semantic-index 四检查全绿 + 发布手动验证 `--mode perf,security` 14 通过）；版本号全链一致化至 v0.10.15（constants.py / pyproject.toml / README / 10 份管理文档）；发布数据文档刷新（test-coverage.md / folders.md / datasource 文档核对）。
- **版本标签**：`git tag v0.10.15` 已打并推送，发布可追溯。
- **已解决项归档**：v0.10.15-dev 已解决项（rf-288 ~ rf-294）整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md` v0.10.15 章节，原文件保留待办区与归档引用。

### dedup 跨源收盘术语同义归一修复（rf-294）（2026-08-28）

- **问题**：跨源港股每日收评簇漏判——新浪用“收评”、东方财富用“收盘”，二者同义但仅标题开头时被前缀剥离，标题中段（如“港股收评”“港股午评”）保留差异，导致同为当日收盘汇总的两条新闻只共享“恒指涨”2 个 bigram（bg<3）被 `cross_skip` 漏判。校准工具 11847 条 skip 中发现 ~40 条此类真重复（比率 0.44~0.49）。
- **修复**（`src/python/providers/news_dedup.py` `_normalize_title`）：收盘术语同义归一 `收盘→收评`、`午评→收评`（只增不减，不破坏既有合并）。归一后收评簇 overlap 2→4、ratio≈0.54≥安全区 0.50，进入合并。
- **方向否决**：曾拟把 `收评/收盘/午评` 加入 `_STOP_BIGRAMS` 掩码，经 830 对锚点模拟证实会导致 7 对现有合并（午评类 cross_merge）bigram 重叠下降而回归（既破坏合并又不解决漏判），否决。
- **测试**：`test_news_sources.py::TestDedupByTitle` 新增 `test_cross_source_roundup_closing_terminology_synonym_merged` + `_v2` 2 例（收评/收盘同日簇应合并）；news 全单测 205 通过、误合并防护 9 例仍通过。
- **校验**：`check-code-traces.py`/`check-doc-traces.py`/`check-semantic-index.py`/`check-task-numbering.py` 均 [OK]；dev-verify 除 1 例预存在的 Windows 文件锁非确定性用例（`os.replace` PermissionError，无关本变更）外全绿。

### DeepSeek 峰谷定价适配周末全天闲时规则（plan-29）（2026-08-28）

- **变更**：DeepSeek 官方 2026-08-23 起周末（周六/周日）全天不再区分峰谷，统一按闲时（低谷）价计费。适配后含 `"peak"` 高峰价子段的模型（`deepseek-v4-flash` / `deepseek-v4-pro` / `deepseek-chat`）在工作日高峰时段（北京时间 09:00–12:00、14:00–18:00）按 peak 价计费，其余时间（含周末全天）按 base 闲时价。
- **代码**：`core/constants.py` 新增 `PRICING_WEEKEND_ALWAYS_IDLE`（默认 True）；`llm/pricing.py` 新增 `PRICING_WEEKEND_ALWAYS_IDLE` 模块级变量与 `_is_weekend()` 判定，`estimate_cost()` 峰谷判定按「工作日 + 钟点」双条件，周末恒闲时；`_is_peak_minute()` 增周末参数。
- **配置**：`pricing` 段新增 `weekend_always_idle`（bool，默认 `true`，可设 `false` 恢复周末按钟点区分峰谷），`config/_llm_settings_defaults.py` 默认模板与用户 `data/config/llm_settings.json` 同步。
- **测试**：`test_llm_utils.py::TestPricing` 周末闲时规则 4 例（默认开/周末高峰按闲时/周末缓存命中按闲时价/关闭开关恢复周末高峰），原以周六为工作日的用例改用周五（2026-08-21）固定时刻。
- **文档**：how-to-config-llm.md（配置示例/完整模板/峰谷定价说明/参数表）、llm-technical.md §10.4 与附录 B、plan.md 新增 plan-29。

### 开发版本切换（2026-08-17）

- 发布 v0.10.14 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.15-dev。

### all_no_unit live 卷入修复 + bench 重跑（rf-288）（2026-08-17）

- **修复**：`test-runner.py` MODES `all_no_unit` marker 由 `not unit` 改为 `not unit and not live`——命令行 `-m` 覆盖 pytest.ini `addopts = -m "not live"`，使 14 项 opt-in live 真实网络套件卷入 `--mode all_no_unit` / bench（323 vs 正确口径 309）。补 `and not live` 后 `--mode all_no_unit` 收集 309，与 collect-test-coverage 口径一致。
- **验证**：`--mode all_no_unit` collect 309（不再卷 live）；bench 全量重跑（含 all 5550 全 mock 零网络访问）回填 test-coverage.md 模式对应测试量表，all_no_unit 保持 309 稳定不反复。
- **变更记录**：rf-288 已修复归档（见 review-findings.md 已解决区）。

### scripts/ 命名统一与清理（2026-08-17）

- **脚本重命名 kebab-case**：7 个 snake_case 脚本统一为 kebab-case（`git mv` 保留历史）——`test_runner.py`→`test-runner.py`、`perf_report.py`→`perf-report.py`、`perf_view.py`→`perf-view.py`、`llm_hallucination_sampler.py`→`llm-hallucination-sampler.py`、`svg_geom_check.py`→`check-svg-geom.py`、`svg_pixel_check.py`→`check-svg-pixel.py`、`svg_text_overflow_check.py`→`check-svg-text-overflow.py`。同步更新脚本自引用、`src/` 注释、live/unit 测试、CI、CLAUDE.md/README/用户手册/管理文档全部引用；测试文件 `test_test_runner_*.py` 按约定不重命名。
- **developer-guide 补 `probe-push2.py`**：速查表 + 诊断类章节补齐东方财富 push2 连通性探测条目（含 curl 对照判读）。
- **删除低价值脚本**：`diagnose_gemini_proxy.py`（硬编码代理 IP `10.22.207.29:10037` 的单机排查临时产物）+ `reproduce_factcheck_corrections.py`（一次性事实校验修正复现，docstring 自认"不属于仓库交付物"，功能已被 rf-289 回归测试 `TestDescriptiveTailMatch` 正式覆盖）。同步移除 developer-guide 速查表行 + 章节、folders.md 目录树行，辅助脚本统计 23→21 / 7,394→7,165。

### dedup 跨源误合并率修复（rf-290）（2026-08-17）

- **问题**：42560 条锚点分层随机采样人工判定，跨源合并区（cross_merge bg3/bg≥4/cross_merge_bg2/cross_safe 共 4180 条）约 70-80% 为误合并，每条误合并即报告丢失一条独立新闻：① `_STOP_BIGRAMS` 未覆盖财报/回购/指数/预警/地震等模板词，不同公司同类新闻天然共享 3-6 bigram（"美的集团累计回购A股股份" vs "中远海控累计回购A股股份" bg=5 误合并）；② 英文占位符统一 `_tk_` 使任意英文 token（msci/vn）共享相似度虚高 ratio；③ 候选区门槛 0.30 过低，跨源方向对立报道（"暂缓加息" vs "将加息"）也被合并；④ bg=2 梯度（ratio≥0.40）误合并率 ~85%（英伟达 Vera Rubin vs 英伟达投资）；⑤ 安全区 0.50 直接合并在 0.50-0.60 段误合并 ~40-50%（行云科技 vs 亿田智能 共享"算力服务合同"骨架 ratio 0.542）。
- **修复**（`src/python/providers/news_dedup.py`）：
  - `_STOP_BIGRAMS` 扩至 ~280 个模板词（财报/回购/指数/预警/地震/评级/货币单位/通用业务词），提取中文 bigram 前整体掩码替换为占位符（`_mask_stop`），消除模板词贡献并杜绝"累计|回购"跨词边界 bigram（计回）泄漏
  - 英文占位符按长度分桶（`_tk2_`/`_tk4_`/`_tk6_`），不同长度英文词不再共享相似度
  - 跨源候选区门槛 0.30→0.35；bg=2 梯度改为 ratio≥0.375 且共享 bigram 含英数/数字 token（CPI/PPI、荣耀IPO、SpaceX 类专名真重复），纯中文公司名共享不触发
  - 安全区分级：ratio≥0.65 且专名 bg≥1 直接合并；0.50~0.65 需专名 bg≥2（防不同公司同模板 ratio 0.7+ 误合并）
  - 新增跨源方向对立词对检测（上涨/下跌、加息/降息等分属两标题且共享实体 → 不合并，记录 cross_opposite）
  - `_normalize_title` 保留空格防英文 token 粘连（"Blackwell AI"→blackwellai）+ 剥离"N级"（地震级数）+ 孤立年份数字不作专名 token
  - ratio 双向取 max 消除 SequenceMatcher 贪心匹配方向不对称（含多英文占位块时 ratio(a,b)≠ratio(b,a) 差异可达 0.18）
- **回归测试**：`test_news_sources.py` 新增 `TestDedupFalseMergeGuard` 9 例（同名不同事件/不同公司回购/不同地震/不同公司业绩快报/目标价骨架/算力合同骨架/不同指数/方向对立/同源不同公司）+ `TestDedupTokenGradientMerge` 3 例；锚点采样 13/13 误合并案例全部修复为保留，真重复 7/11 保持合并（4 条表述差异大按宁漏勿错原则接受漏判，如段永平减持澄清、欧元区CPI、南向资金、野村财报）。`unit/news` 44 用例全绿。
- **校准脚本同步**：`scripts/calibrate-dedup-threshold.py` 阈值常量（0.35/0.375/0.65/0.50）与"当前阈值规则"摘要更新。
- **提交**：`1aebd5ff`（dev 分支，已推送 origin/dev）——含 5 文件 +636/-63，pre-commit 任务编号一致性校验通过。

### 文档同步：rf-289/rf-290 配套管理文档刷新（2026-08-17）

- **technical.md「新闻去重算法」章节重写**：与 rf-290 新实现（五档阈值策略）对齐——cross_threshold 0.30→0.35、新增直接合并区 ratio≥0.65+bg≥1、安全区分级 0.50~0.65 需 bg≥2、候选区 bg=2 梯度 0.375+英数 token、方向对立防护、STOP 集 44→334 词 + 整体掩码机制、英文分桶 `_tk2_`/`_tk4_`/`_tk6_`、ratio 双向取 max；锚点体系补 `cross_merge_bg2`/`cross_opposite`。
- **test-coverage.md 计数刷新**（collect-test-coverage.py 实时口径）：模式对应测试量 `unit` 5224→5241 / `standard` 4546→4563 / `verify` 3470→3487 / `all` 5533→5550；功能域新闻处理 191→203、LLM 智能分析 760→765；单元分组 `unit_llm` 760→765 / `unit_news` 191→203、父标记 5224→5241；跨类 `llm` 615→620。
- **developer-guide.md**：calibrate-dedup-threshold 章节描述同步（"两档阈值"→当前五档体系）。

### 事实校验描述性尾名匹配修复（rf-289）（2026-08-17）

- **问题**：2026-08-17 报告「事实校验自动修正 3.92%→36.3%（022365实际收益率36.3%）」——LLM 正确写出的"电池主题ETF（收益率-3.92%）"（561910 招商中证电池主题ETF 实际 -3.92%）被自动修正为 **-36.3%**。根因：`_locate_subject_code` 无法解析省略基金公司前缀的描述性缩写（"电池主题ETF"→561910），回退同句最近邻把 3.92 误路由到 022365（永赢科技智选混合C，实际 +36.29%），修正逻辑保留负号 → 报告出现 -36.3%，正确数据被改错。
- **修复**：`src/python/llm/fact_checker/_utils.py` 新增 `_match_descriptive_tail` 描述性尾名匹配——逐持仓取核心名后缀（≥3 汉字）+ 产品后缀（ETF/股票A/混合C 等）拼完整候选，命中句中候选按 (距锚点距离, 候选长度) 择优，接入 `_locate_subject_code` 兜底（产品后缀将候选锚定为产品名，避免"科技""指数"等泛词误路由）。修复后"电池主题ETF（收益率-3.92%）"归因 561910 且 3.92 在容差内通过、不再误修正。
- **回归测试**：`test_fact_checker.py` 新增 `TestDescriptiveTailMatch` 5 项（报告场景不误修正 / 错误值经尾名匹配修正且保留盈亏方向 / `_locate_subject_code` 直测 / 泛词不误路由 / `run_fact_check` 整链路）；全 LLM 单测 764 通过 + code/doc/task-numbering/semantic-index 四检查全绿。

### 事实校验主体归因误修正三处修复（rf-291/rf-292/rf-293）（2026-08-17）

- **问题**：2026-08-17 报告自动修正把三处**正确数据改错**——① [持仓体检报告] 15/16 通过、自动修正 1 处 `181.37%→130.6%（040046）`，但 181.37% 是建设银行（601939）正确收益率；② 智囊团深度复盘 `130.61%→181.4%（601939）`，但 130.61% 是华安纳斯达克100（040046）正确收益率；③ `0.21%→-2.3%（561910）`，但 0.21% 是"今日组合 +0.21%"的组合本日收益。
- **根因**（三处独立）：
  1. **rf-293 单代码钉扎**：`_evaluate_percent_value` 句中恰含 1 个持仓代码（040046）时把所有百分比钉扎到该代码，"040046 收益率 +130.61%、建设银行收益率 +181.37%"中 181.37% 被误归 040046 → 误修正为 130.6%
  2. **rf-291 短尾缺数字代号**：`_match_descriptive_tail` 未覆盖「核心名+数字代号」缩略（"华安纳斯达克100"→040046"华安纳斯达克100ETF联接基金A"），130.61% 回退同句最近邻 601939 → 误修正为 181.4%
  3. **rf-292 组合当日收益无保护**："今日组合 +0.21%"组合本日收益无基准数据可校验，回退全局最近邻把 0.21% 误修正为数值最接近的品种收益率 561910 -2.3%
- **修复**（`src/python/llm/fact_checker/`）：
  - `_utils.py` `_locate_subject_code` 重构为「紧邻优先 + 代码/全名最近兜底」统一主体归因（代码/全名/简称/尾名四级来源；主体边缘距 ≤ `_ATTACHED_SUBJECT_MAX_DIST`=6 为紧邻，紧邻主体优先；无紧邻时句内代码/全名最近兜底，远距别名/尾名不得覆盖可靠主体）——替换原单代码钉扎分支，同句多主体各数值各自就近归因
  - `_utils.py` `_leading_token` 改为仅取前导数字串（"100ETF联接基金A"→"100"，排除"ETF"等字母），`_match_descriptive_tail` 据此生成「核心名+数字代号」短尾候选（"华安纳斯达克100"）
  - `_context.py` 新增 `_is_portfolio_daily_change_context`（前 18 字符时间词 + 数值紧邻"组合"标记），`_numerical.py` 在组合级累计收益语境之后、主体定位之前跳过——组合本日收益不再回退全局最近邻
- **回归测试**：`test_fact_checker.py` 新增 `TestSubjectAttributionMulti` 4 项（体检单代码不钉扎全句 / 智囊团短尾简称不误路由 / 组合本日收益不误修正 / 同句远距尾名不覆盖可靠主体）；`test_fact_checker.py` 全 124 用例通过。
- **P1 合入门禁**：`--mode verify` 通过（另机执行，0 失败）。
- **文档同步**：test-coverage.md 模式表 bench 回填（unit 5245 / standard 4567 / verify 3491 / all 5554）、功能域 LLM 智能分析 765→769、单元分组 `unit_llm` 765→769、跨类 `llm` 620→624；folders.md 统计重计（源码 70,732 / 测试 87,638 / 用例 5,554）。
- **变更记录**：rf-291/rf-292/rf-293 已修复归档（见 review-findings.md 已解决区）。


## [0.10.16] - 2026-09-10

### 版本发布 v0.10.16（2026-09-10）

- **发布流程**：P2 发布门禁通过（`test-runner --mode verify,regression` 4219 通过 0 失败 + code/doc/task-numbering/semantic-index 四检查全绿 + 发布手动验证 `--mode perf,security` 14 通过）；版本号全链一致化至 v0.10.16（constants.py / pyproject.toml / README / 10 份管理文档）；发布数据文档刷新（`--mode bench --update-docs` 回填模式对应测试量与 dragonball 环境耗时对照；folders.md 测试代码 336 文件 94,305 行、测试用例 6,263；datasource-reliability.md 补记链路失败原因可读与 `doctor` 自检的分工）。
- **版本标签**：`git tag v0.10.16` 已打并推送，发布可追溯。
- **已解决项归档**：v0.10.16-dev 已解决项（rf-295 ~ rf-304；rf-297 与 rf-303 仍待办）整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md` v0.10.16 章节，原文件保留待办区与归档引用。

### DeepSeek V4.1-Flash 正式模型名接入（`deepseek-flash`）（2026-09-10）

- **背景**：DeepSeek 于 2026-09-10 发布 V4.1 Flash，**正式模型名为 `deepseek-flash`**；同日 12:00（北京时间）起 flash 系列降价（数字见下一条 2026-09-09 条目，已落库）。配套变化：① 别名 `deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` 端点仍被接受，但底层模型由 V4.1-Flash 接管、**按同一单价计费**；② `deepseek-v4-pro` 于 **2026-09-14 12:00 下线**，该时刻至 V4.1 Pro 上线前请求自动路由到 V4.1-Flash 并按 **V4.1-Flash 单价**计费。
- **缺陷（本次修复的两个真实缺口）**：`deepseek-flash` 既不在 `MODEL_PRICING`、也不匹配任何既有前缀键（`deepseek-v4-flash` 属 `deepseek-v4-` 族，与 `deepseek-flash` 互不为前缀），`estimate_cost()` 对其**返回 `"-"`**——费用页签与终端用量行显示为空。同一模型名还不在 `llm/api_base.py` 的思考模型白名单内，连带触发第二个缺口：该模型**既无法开启 Extended Thinking，也失去「未开启 thinking 时显式注入 `disabled`」的安全网**——请求会落入 DeepSeek 默认思考模式（effort=high）占满 `max_tokens` 而无正文，正是此前 `fix-deepseek-thinking` 修复过的那类失效。
- **改动**：`core/constants.py` 新增 `deepseek-flash` 定价条目（闲时 输入 1.0/输出 4.0/缓存命中 0.02，高峰翻倍 2.0/8.0/0.04，与 flash 系列同价）并重写 DeepSeek 块注释（别名路由、v4-pro 下线时点与路由期计费口径）；`llm/api_base.py` 的 `_THINKING_SUPPORTED_PREFIXES` 与 `_THINKING_EFFORT_MODEL_PREFIXES` 双双纳入 `deepseek-flash`（后者附注漏登记的后果）；`config/_llm_settings_defaults.py` 计价注释示例改用正式模型名。
- **影响面**：**不改动任何已配置的模型名与默认值**——现有 `deepseek-v4-flash` 配置继续可用且计费不变；`deepseek-flash` 仅作为可选入口新增。`deepseek-v4-pro` 的静态单价保持 4.50/13.50/0.15（在 09-14 下线前仍准确），路由期实际费用低于本表估算值，该口径差异在代码注释与 `llm-technical.md`/`how-to-config-llm.md` 中显式说明。
- **测试**：新增 6 例 —— `test_llm_utils.py` 5 例（新名闲时 `¥5.000`/高峰 `¥10.000` 定价、与两个别名同价、缓存命中走峰谷价 0.02/0.04、`PRICING_MERGED` 含新键、`_supports_extended_thinking` 与 `_is_effort_model` 对新名（含大小写变体）判定为真）、`test_llm_api.py` 1 例（新名在未开 thinking 时命中 `thinking:disabled` 注入安全网）。
- **文档**：`llm-technical.md`（§10.3 前缀匹配示例改用新名、§10.4 peak 模型清单补齐、定价快照表新增行并把 `deepseek-v4-flash` 标注为已接管的别名、`deepseek-v4-pro` 标注下线时点）、`how-to-config-llm.md`（Extended Thinking 的 DeepSeek 适用模型名单、DeepSeek Anthropic 接入的模型清单与路由说明）、`test-coverage.md`（`unit` 5948→5954、`unit_llm` 847→853、`llm` 跨类 650→656 及覆盖项描述）、`folders.md`（统计表随本轮改动重算）。
- **来源**：DeepSeek 开放平台 2026-09-10 公告与 API 文档（`deepseek-flash` 正式模型名、别名路由、消费级计费口径以官方公告为准；本表为项目侧估算快照，可经 `llm_settings.json → pricing` 覆盖）。

### 健壮性三件套：数值归一 / 失败原因可读 / 系统自检（plan-35）（2026-09-10）

- **背景**：借鉴外部 augur 的健壮性实践识别出三项独立改进——① `float("nan")` / `float("±inf")` **不抛异常**，各 provider 解析器里 `try: float(x) except` 形态的兜底对它们完全无效，脏值直入市值核算/收益序列/绘图数据；② provider 链路失败只留 `failure_type` 短标识（`tencent: transport`），用户看不懂是哪个源、为什么失败；③ 缺少一次性盘点「环境/配置/目录/数据源」的诊断入口，出问题只能逐个命令试。分析见 `docs-stm/archive/v0.10.x/augur-borrowing/augur-borrowing-analysis.md` §建议C；实现设计见 `docs-stm/archive/v0.10.x/augur-borrowing/robustness-suite-implementation.md`。按缺口**性质**拆 A（真缺陷，无开关）/ B（实验增强，开关门控）三条独立落地路径。

  **A1｜数值归一防线（无开关，默认路径生效）**——判为真缺陷，就近修。改动前是**约 10 个互不一致的私有解析器 + 4 种失败口径**，其中被依赖最广的 `providers/_utils.safe_float` 恰是 NaN/±inf 防线最弱的一个：

  - `core/num_utils.py`（新增，零项目内依赖、纯 stdlib）：把散落的归一实现收敛为一处，只保证一条不变量——**返回的数值一定有限**。对外四个原语：`safe_num(value, default=...)`（宽容归一：数值字符串先尝试解析再施加有限性检查）、`strict_num(...)`（严格归一：仅接受 int/float 且有限，字符串一律非数值）、`finite_or(value, fallback=0.0)`（专治 `x or 0.0` 空防线惯用法）、`is_finite_number(...)`。`int` 一律原样返回（不强行转 float，避免整数份额/ID 被改写），`bool` 一律显式排除（它是 `int` 子类，混入会让 `True` 静默变 `1`）。
  - **保留两个归一入口而非强行合一**：provider 解析器面对网页/JSON 字符串字段，用 `safe_num`；`signal_ledger._safe_number` 面对待落盘的账本值（字符串混入会破坏类型契约），用 `strict_num`——两层既有口径本就不同，合一反而出错。
  - **四个确凿缺陷站点**：① `or 0.0` 惯用法对 NaN **完全无效**（`float("nan")` 是 truthy，`nan or 0.0` 求值为 `nan`）——`report/market_value.py` 的 `price = mkt.get("price", 0.0) or 0.0` 让 NaN 直入市值/盈亏/溢价全链，昨收为 NaN 时更会把「全天涨幅」算成 `price × shares` 凭空造出当日盈亏；同类站点见 `report/category.py` / `market_value_sheet.py` / `chart_data_builder.py` / `decision_record.py` / `decision_llm_capture.py`、`analysis/whatif.py` / `portfolio_evolution.py` / `snapshot_diff.py`、`core/data_freshness.py`、`report/html_writer_display.py`，均改用 `finite_or(...)`；② provider 解析器（`_utils.safe_float` / `tencent._parse_float` / `_parse_float_field` / `sina_kline._parse_sina_kline_float` / `eastmoney_industry._extract_number` / `akshare_extras._safe_float`）脏值路径返回 NaN/±inf 而非兜底值——K 线泄漏尤其危险，它直接进入 `analysis/` 全部收益序列指标；现各自委托 `safe_num` 并保持原有默认值口径（`0.0` 或 `None`）；③ `core/reader.py::_safe_float` 追加有限性检查——Excel 返回 NaN（`=NA()`/公式错误）时按「非法值」告警并返回 `None`，此前返回 NaN 使 `shares <= 0` 校验对 NaN 恒为 False 而**放行脏行**；④ `core/signal_ledger._safe_number` 收敛为委托 `strict_num`（语义原样提取，行为逐字不变）。
  - **合法输入行为逐字不变**：改动只影响非有限值与非数值入参，正数/字符串数字/`None`/空串的返回与改动前完全一致；**不统一各层的 dirty 默认值语义**（`None` vs `0.0` 是既有契约，强行统一会波及数十处消费方，属超范围重构）——本次只保证「有限性」这一条不变量。纯 CLI 参数/时间戳等可证明非浮点的 `or` 站点保持原样，不做无意义改动。

  **A2｜失败原因可读（无开关，默认路径生效）**——判为真缺陷，就近修：

  - `fetcher/chain.py` 新增 `FailureDiagnostics`：采集「展示名(原因)」条目，`summary()` 渲染为 `腾讯财经(连接超时)；新浪财经(返回空)`（单条原因按 `_REASON_MAX_LEN` 截断、空白折叠）。
  - `fetcher/{price,fund,industry,index}.py` 在调用 provider 链路时构造诊断器并随失败 `_t.record(...)` 的 `message=` 参数透传。
  - `report/data_status.py`：`record()` / `_record_unsafe()` 新增 `message: str | None = None`，写入 `DegradationEvent.detail = {"message": message}`（复用既有 `detail` 字典，与聚合路径 `record_aggregated()` 形状一致，`get_log()` 无需改动）。
  - `report/data_source_matrix._failure_entry()`：渲染降级明细时**优先取该人类可读原因**，无原因时回落原 `failure_type` 短标识——**`message=None` 时矩阵输出与改动前逐字相同**（显式测试锁定）。
  - **展示名一致性修复**（自审 rf-299）：熔断跳过与未注册两条分支原先写原始 provider id（`p1(已被熔断跳过)`），与同一循环内其余分支的展示名不一致；现把 `entry = provider_fn_map.get(provider_name)` 提到熔断检查之前，统一取 `label = entry[0] if entry else provider_name`。

  **B｜系统自检（实验功能 `doctor_check`，默认关）**：

  - `core/doctor.py`（新增）：一键自检运行环境，五组输出（环境 / 配置 / 目录 / 功能开关 / 数据源），**失败项附可执行修复建议**（`hint`）。对外三个函数：`run_doctor_checks(include_network, max_timeout)` / `summarize_doctor_results()` / `format_doctor_report(results, use_color)`。
  - **两条不可让步的设计约束**：① **自检自身永不抛异常**——任何检查项异常都转成该组的失败结果行（配置损坏正是它最需要诊断的场景，此处抛 traceback 等于在最需要用它的时刻失效）；② **零重依赖**——不 import `core/reader.py`（pandas），持仓文件检查用 `os.listdir`，因为 pandas 缺失/损坏本身就是它要报告的一类失败。
  - 检查项：Python 版本 `>= (3, 10)`、虚拟环境（`sys.prefix != sys.base_prefix`）、项目根与配置加载（惰性 `init_config()` / `get_config()`）、LLM 凭据（`get_llm_config()`，兼容多链 `_provider_list` 与扁平 `provider`/`api_key`）、目录存在性与可写性（写探测哨兵文件后**立即删除**，不留残留）、功能开关清单（信息性，不改结论）、数据源连通性（复用既有 `core/check_sources.run_health_checks`，可按 `include_network=False` 跳过）。
  - **三面上屏**（与所有实验项同源，均由 `features.EXPERIMENTAL_FEATURES` 注册表驱动）：**CLI** = `doctor` 子命令（`--offline` 跳过联网、`--timeout SECONDS` 默认 8.0）；**TUI** = 菜单 `[D]` 系统自检（`tui/handlers_log.py::_cmd_run_doctor`，交互动线与其他诊断项一致）；**Web** = 运行状态区「系统自检」卡片（带 `⚗ 实验性` 标签）+ `GET /api/doctor`（`?network=0` / `?timeout=` clamp 上限 15s，非法值回落 12s 默认）。
  - **显式启用入口**：CLI `--experiment doctor_check`（与所有实验项一致，无需另开门路）、TUI 菜单 `[S]`、Web 配置面板「实验性功能」区。
  - **`doctor` 子命令不受开关约束**（有意为之）：它与 `check-sources` / `view-logs` 同样在 `init_config` **之前**分派——配置损坏正是它要诊断的场景，若因开关未开而拒绝执行，用户就陷入「开开关要先读配置、读配置失败又要开开关」的死锁。开关只约束 TUI `[D]` 与 Web 卡片这两个「日常会看见」的入口。
  - **TUI 菜单项门控机制**：`tui/tui_menu.py` 新增 `FEATURE_GATED_ITEMS` 表 + `_apply_feature_gates()`，在 `tui.main()` 的 `init_config()` 之后、`_bind_callbacks()` 之前**就地**裁剪 `MENU_ITEMS`（切片赋值保持列表对象不变，调用方视图同步）；`_bind_callbacks()` 前调用保证裁剪后索引与渲染一致。
  - **退出码语义**（自审 rf-300）：`_handle_doctor` 返回 `_EXIT_SUCCESS`（全通过）/ `_EXIT_PARTIAL`（命令跑完但有失败项）——**不是** `_EXIT_SEVERE`，命令本身没失败、只是结论不佳。`_use_ansi_color()` 遵循 `NO_COLOR` + `isatty` + UTF-8 三项判据，终端不支持颜色时自动降级纯文本。
- **测试**：新增 8 文件 —— `test_num_utils.py`（A1：四个原语的合法输入/脏值/`bool` 排除/`int` 原样返回契约）、`test_num_utils_edge.py`（A1 边缘：非字符串非数值对象/超长字符串/嵌套容器/大小极端值）、`test_numeric_guard_regression.py`（A1 provider 层：各解析器「非有限值被拦下」+「合法输入行为不变」双向不变量）、`report/test_numeric_guard_regression.py` + `report/test_numeric_guard_regression_edge.py`（A1 报告层：`or 0.0` 站点不再泄漏 NaN 至市值/盈亏/涨幅、单个 NaN 不污染整列合计与档位判定）、`test_chain_diagnostics.py` 35 例（A2：原因渲染与截断、诊断器采集序、链路各失败分支的条目文案、熔断分支展示名一致性、无诊断器时既有行为不变、注册表失败上下文可读）、`test_data_status_message.py` ~20 例（A2：`message` → `detail` 透传、不影响降级判定、矩阵渲染优先取原因、无原因回落逐字不变）、`test_doctor.py` 27 例（B：结果结构契约、**三处「永不抛异常」**——配置坏/注册表坏/网络坏均出失败行、环境与目录检查含只读与残留断言、开关清单上屏、统计与渲染）。既有文件扩展：`test_tui_menu.py`（菜单 19→20 项 + `[D]` 项 + `TestFeatureGatedMenuItems` 6 例含开关开/关两态与幂等性，带 autouse 快照还原防污染）、`test_tui_routing.py`（键覆盖集补 `[D]`）、`test_cli.py`（`doctor` 子命令解析/处理/分派三组 8 例，含 `--offline` 与 `--timeout` 透传、`_EXIT_PARTIAL` 语义、config 之前分派）、`test_handlers.py`（`/api/doctor` 契约 6 例 + 自检卡片可见性 5 例）、`test_fetcher_index.py`（`diagnostics=ANY`）、`test_config_edit.py`（白名单与面板标签纳入 `doctor_check`）。
- **文档**：`requirements.md`（features.json 32→33 项 + 开关表行）、`technical.md`（新增 §4.17 健壮性三件套 + 白名单/features.json 计数 + CLI 子命令/TUI 菜单/Web 路由/`is_feature_enabled` 消费者）、`folders.md`（目录树 + 统计重算）、`test-coverage.md`（模式/子标记/功能域计数）、`how-to-config.md`（§M 开关表行 + 三入口说明）/ `how-to-config-llm.md` / `how-to-use-tui-menu.md`（编号 14）/ `how-to-use-web-mode.md` / `how-to-use-cli-mode.md`（`doctor` 子命令 + `--experiment doctor_check` 示例）/ `faq.md`（新增两条答疑：「想快速确认环境到底哪里不对，有没有一键体检」+「TUI 主菜单里找不到 `[D]` 系统自检项」）、`developer-guide.md`（补「新增实验开关检查清单」五步表 + 「菜单项/卡片可见性由开关门控」纪律；「诊断类命令不得依赖 config 初始化」与「新增数值解析一律委托 `core/num_utils.py`」两条通用纪律）。
- **记账**：plan-35 标记完成（见 plan.md P4 表）；自审记录 rf-299（熔断分支展示名不一致）、rf-300（退出码魔法数字）、rf-301（历史实现叙述注释与魔法编号 `F9` 违反代码痕迹纪律）、rf-302（技术设计文档正文出现任务编号括注，违反文档痕迹纪律）移入已解决待归档区。
- **不变量**：A1 合法输入行为逐字不变；A2 无 `message` 时数据源矩阵输出与改动前**逐字相同**；B 关闭 `doctor_check` 时 TUI 无 `[D]` 项、Web 不渲染自检卡片，而 `doctor` CLI 子命令始终可用。

### 确定性数值信号沉淀与实时/非实时标签纪律（plan-34）（2026-09-10）

- **背景**：市场温度、估值分位、尾部风险、风格因子、再平衡超限这五类评级由**确定性算法**算出，但只活在一次报告生成的内存里与当页展示中——报告落盘即散失，跨期无法回答「上期判高估，事后对不对」。同时，这些评级里既有当日实时行情算出的、也有**降级/缓存行情**算出的，二者混在一起消费时，非实时数据算出的评级会冒充真实战绩。借鉴外部 augur `backtest.py` 的 `data_source` 标签与「排行榜默认 `live_only`」纪律。分析见 `docs-stm/archive/v0.10.x/augur-borrowing/augur-borrowing-analysis.md` §建议B。
- **实现设计**：`docs-stm/archive/v0.10.x/augur-borrowing/signal-ledger-implementation.md`。

  **A｜缺陷修复：本项无**——五类评级当前的**输出**均为确定性且可复现，没有「算错」可修；仅有的处置隐患是**尚未发生的污染风险**（非实时数据混入统计），而消除该风险本身就属新增能力。**不制造一个缺陷来凑 A/B 结构**，避免把「新增功能」伪装成「修 bug」而掩盖真实变更面。

  **B｜确定性信号沉淀（实验功能 `signal_ledger`，默认关）**：

  - `core/jsonl_store.py`（新增）：把 `perf._append_jsonl_atomic` 与 `decision_ledger._append_event_atomic` 中**已经重复两份**的「读全文 → 拼接 → 写临时文件 → `os.replace`」逻辑抽为共享原语 `append_jsonl_atomic()` / `read_jsonl()`，两个既有调用点改为委托——**不新增第三份拷贝**。各自保留原有 `prefix`（临时文件名）与日志标签，输出逐字节不变，由 `test_jsonl_store.py::TestDelegationPreservesBehaviour` 锁定（含 `decision_ledger` 的 `sort_keys=True` + `ensure_ascii=False` 序列化口径）。
  - `core/signal_ledger.py`（新增）：账本核心，**零 `analysis/` 依赖**（分层约束 C）——`build_signal()` 记录形状 + `append_signals()` 批量幂等入账（读一次 → 按 `id = {report_date}|{signal_type}|{subject}` 去重含批内 → 一次原子写 → 同日重跑 `registered` 归零而 `skipped` 计数）、`fold_signals()` 折叠统计（**默认 `live_only=True`**）、`summary_block()` 提示词摘要（开关关闭或实时样本不足阈值 → 返回 `""`，判定**无条件执行**，保证「开关关闭 → 全链路无感」在注入路径同样成立）、`summary_cache_suffix()` 缓存后缀（无块 → `""`；有块 → `_sg` + 摘要 md5 前 12 位）。`_safe_number()` 把 `NaN`/`±inf`/bool/非数值归一为 `None` 后才落盘，防写出非法 JSON。
  - **来源标签不引入新的合成数据开关**：`resolve_data_source()` 的「非实时」判定复用**既有数据质量设施**——持仓级按该 code 的 `data_freshness`（非 `fresh` → 非实时，文案取自 `core.data_freshness.FRESHNESS_LABELS` 不另写一份）、指数级/组合级按 `DegradationTracker` 事件 `source_key` 前缀（`index_history_` 对应温度/风格，`price_`/`fund_` 对应尾部风险）。**仅可证明为实时才算实时**——未识别的新鲜度取值一律保守判非实时；确无逐品种条目可证伪时（组合级/指数级）乐观取实时但**显式写入理由字段**，不静默。全程未新增 `pipeline_data` 键，故无需登记数据渠道契约。
  - `report/signal_record.py`（新增）：五类评级 → 记录的**适配器**，也是唯一持有语义词表映射的一侧（`core/` 不得依赖 `analysis/`，故 `低估/便宜 → +1`、`高估/超限 → -1` 与尾部风险分档阈值下沉到 `report/` 层，账本只存通用整数方向，复用 `decision_ledger` 的 `DIRECTION_*` 常量）。跳过项：不可用占位（`available=False`）、无分位（`percentile_available=False`）、尾部风险样本不足 `MIN_TAIL_RISK_SAMPLE`、再平衡聚合提示行（`{"summary": True}`）、无 `code` 行。
  - `report/_report_generation.py` **第 5d 步 seam**：置于决策头结构化（5c）之后、`perf.stop()` 之前——尾部风险等键在 LLM 生成阶段才注入 `pipeline_data`，过早登记会漏采（适配器对缺失键逐项跳过，故不构成硬依赖）；整体 `try/except` + `reporter` 告警，实验特性故障绝不打断报告主链路。
  - `llm/skeleton.py`：`_LESSON_RECEIVER_MODULES` 更名 `_LEDGER_CONTEXT_MODULES`（该模块集现在承接**两类**账本上下文），标准模式 `expert_review` 首轮 user prompt 追加决策教训 + 确定性信号摘要，两者各自判开关与样本门槛。
  - **缓存键同源**：开关影响提示词 → **写侧指纹**（`generators.py::_fingerprint`）与 **orchestrator 预检指纹**（`_compute_module_cache_info`）无条件同调 `signal_ledger.summary_cache_suffix()`，开关判定收敛在函数内部；关闭返回 `""`（键不变、不误伤旧缓存），开启两侧同步换键。
- **测试**：新增 4 文件 118 例——`test_jsonl_store.py` 12 例（原子追加/容错读取/目录自动创建/临时文件不残留/两处委托行为不变）、`test_signal_ledger.py` 45 例（记录形状/批量幂等含批内去重/折叠统计/摘要与后缀/来源判定）、`test_signal_ledger_edge.py` 25 例（**未识别新鲜度取值的保守缺省**/账本路径是目录或不可读/超长与 Unicode 字段/畸形与缺字段记录/非有限数值/500 条批量单次原子写）、`test_signal_record.py` 36 例（五类抽取形状/不可用与聚合行跳过/持仓级与指数级与组合级 live-demo 判定矩阵/幂等与开关无感）。既有文件扩展：`conftest.py`（账本路径隔离重定向到 `tmp_path`）、`test_config_edit.py`（白名单与面板标签纳入 `signal_ledger`）。
- **文档**：`requirements.md`（features.json 31→32 项 + 开关表行）、`technical.md`（新增 §4.16 确定性数值信号沉淀与实时/非实时标签纪律 + 白名单/features.json 计数 + `is_feature_enabled` 消费者）、`llm-technical.md`（§13.1 缓存指纹后缀列 + 账本上下文注入说明）、`folders.md`（目录树 + 统计重算）、`test-coverage.md`（模式/子标记/功能域计数）、`how-to-config.md`（§M 开关表行 + 三入口说明）/ `how-to-config-llm.md` / `how-to-use-tui-menu.md`（编号 13）/ `how-to-use-web-mode.md` / `how-to-use-cli-mode.md`（`--experiment signal_ledger` 示例）、`developer-guide.md`（补「追加型状态文件一律走共享原语」+「统计类输出默认只算实时记录」两条通用纪律，并在缓存指纹纪律中纳入 `signal_ledger`）、`README.md`（LLM 分析特性行）。
- **记账**：plan-34 标记完成（见 plan.md P4 表）。
- **不变量**：开关关闭时**提示词逐字节不变、账本不写盘、摘要返回空**；五类评级中任何一类缺失或不可用都只是**少登记一条**，不影响其余登记与报告生成。

### 决策头结构化与决策词归一解析（plan-33）（2026-09-10）

- **背景**：决策词（减仓/加仓/持有）在全仓库**只走展示、无人解析**——「操作建议」表仅存在于提示词契约中，`markdown_to_html` 又把表格降级为逐个 `<p>` 行；唯一消费方（决策账本抽取）用**子串包含**判方向。`不建议加仓` 会被判成 `+1`、`加仓或减仓` 会取靠前词判成 `-1`、`暂不减仓` 会被判成 `-1`。误判后果不是显示错一行，而是**按错误方向写入 `data/state/decision_ledger.jsonl`**，日后结算时污染命中率统计与教训回灌。分析见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/llm-quality-signal-analysis.md` §3。
- **实现设计**：`docs-stm/archive/v0.10.x/tradingagents-borrowing/decision-header-parse-implementation.md`。按缺口**性质**拆两条独立落地路径：

  **A｜决策词归一解析器（无开关，默认路径生效）**——判为真缺陷，就近修：

  - `core/decision_header.py`（新增）：词表 + 归一解析的共享层——**零项目内业务依赖**（仅取 `core.decision_ledger` 的方向常量作单一事实来源），消费方横跨 `llm/`（提示词词表）与 `report/`（抽取），放 `core/` 两个方向都无环。
  - 判据六条：**标签优先于裸词**（整格精确匹配先行，未命中才降级全文扫描）、**长词优先**（词表按长度降序，防短词劫持）、**否定前缀守卫**（命中词左侧同子句内出现否定词或单字 `不/勿` 判未命中；**仅看左侧**——右侧限定语如 `建议加仓不必追高` 不构成否定）、**复合词左边界**（命中词紧邻左字符属 `加减增` 时跳过，`加减仓位`/`增减持` 不再被当成方向）、**二义不猜**（命中多方向返回 None，不做「取第一个」的静默选择）、**判不出返 None**（不落「持有」或任何方向默认值）。
  - **复合词左边界取窄字符集**：中文无词间空格，字符级匹配无法照搬 `\b`；只收「加减增」三字——唯有它们能与其后的 `仓/持` 组成方向二义的复合短语；不收 `持/买/卖/清/观/止/建`，否则误杀「坚持持有」「逢低买入」等正常表述（已编码为回归矩阵）。
  - **词表只收语义单向词**：规范词（减仓/加仓/持有）+ 扩展词（清仓·减持·卖出·止损 / 增持·买入·建仓 / 观望）；`止盈`（可能部分落袋也可能清仓）、`调仓`（方向不明）**不入词表**——宁可判不出，不可判错。
  - `report/decision_llm_capture.py`：`_operation_direction`（子串包含）删除，改调 `parse_decision_word`；表格行解析、持仓白名单、baseline、同日去重等既有纪律原样保留——**删掉一处脆弱实现，而非叠加第二套解析器**。

  **B｜结构化决策头（实验功能 `decision_header_parse`，默认关）**：

  - `llm/prompts_action.py`：`enable_structured_header=True` 时在「### 操作建议」表后追加一行 `决策头：{"decisions":[{"code","action","priority"}]}` 契约（由 `build_structured_header_instruction()` 生成，与解析器同源、由测试锁定互读）；关闭时 append 空串，提示词**逐字节不变**。
  - `core/decision_header.parse_structured_header()`：**花括号配平扫描**（字符串/转义感知）提取载荷，而非 `find("{")`/`rfind("}")`——后者在同一行出现两个 JSON 对象时会把跨度拉通成非法 JSON；`决策头：` 后为空行时以空串兜底，不抛 `IndexError`。逐字段**归一校验**（`action` 必须能归一为方向，否则丢弃该条而非原样透传；`code` 必须 6 位数字），全批不可用 → 回落确定性表格解析。
  - **两路产物形状统一**为 `{code, name, direction, magnitude, detail, carrier, baseline_close}`（结构化头的 `priority` 在解析侧即归一为 `magnitude`），`_collect_decision` 对两路走同一段登记纪律（持有剔除 / code 白名单 / 名称回填 / 同码取高）。
  - **缓存键同源**：开关影响提示词 → **写侧指纹**（`generators.py::_fingerprint`）与 **orchestrator 预检指纹**（`_compute_module_cache_info`）无条件同调 `structured_header_cache_suffix()`，开关判定收敛在函数内部。关闭返回 `""`（键不变、不误伤旧缓存）；开启两侧同步换键——只改一侧会让预检命中旧键而跳过重生成，开关形同虚设。辩论模式路径不追加该契约。
- **顺带修一处前端漂移**（plan-32 遗留）：Web 配置面板的实验开关显示名由前端手写字典维护，`module_quality_gate` 加入注册表后未同步，面板上显示裸 flag 名。现改为服务端按注册表下发 `experiment_labels`、前端渲染时回填，手写字典清空——**新增实验项无需再改前端**。
- **测试**：新增 3 文件 —— `test_decision_header.py`（核心：词表/标签优先/长词优先/否定守卫全表/二义不猜/子句边界/右侧限定语不否定/优先级/代码提取/结构化头/缓存后缀/契约与解析器互锁）、`test_decision_header_edge.py`（边缘：复合词左边界、**正常表述不被边界误杀**、嵌套否定、畸形载荷矩阵、边界值）、`test_prompts_structured_header.py`（提示词契约：开关关闭逐字节不变、契约位置、契约示例可解析、指纹换键）。既有文件扩展：`test_decision_llm_capture.py`（误导性操作格回归 4 例 + 结构化头优先/回落矩阵 5 例）、`test_config_edit.py`（白名单与面板标签）。
- **文档**：`requirements.md`（features.json 30→31 项 + 开关表行）、`technical.md`（新增 §4.15 决策头结构化与决策词归一解析 + 白名单/features.json 计数 + `is_feature_enabled` 消费者）、`llm-technical.md`（§13.1 缓存指纹后缀纪律 + 提示词侧结构化头说明）、`folders.md`（目录树 + 统计重算）、`test-coverage.md`（计数同步）、`how-to-config.md`（§M 开关表行 + 面板说明）/ `how-to-config-llm.md` / `how-to-use-tui-menu.md`（编号 12）/ `how-to-use-web-mode.md` / `how-to-use-cli-mode.md`（`--experiment decision_header_parse` 示例）、`developer-guide.md`（「新增 LLM 模块检查清单」补「实验开关改变提示词 → 缓存指纹读写两侧同源」通用纪律）、`README.md`（LLM 分析特性行）。
- **记账**：plan-33 标记完成（见 plan.md P4 表）。
- **依赖方向**：解析器置于 `core/` 而非 `report/`——`llm/` 不得依赖 `report/`，而提示词层需要词表；共享层放 `core/` 使两个消费方向都无环。

### 模块级质量分级注入（plan-32）（2026-09-10）

- **背景**：现有【数据质量降级】披露只覆盖**输入侧**（数据源可达性），**输出侧**（LLM 各模块内容本身的完整性/一致性）无任何口径——内容缺章节、被占位符顶替、篇幅显著偏薄这类"内容在但不可信"的情形，下游读者拿到的是与正常输出无异的排版。借鉴外部 `agents/quality_gate.py` 的 A~F 分级机制（**劣级不阻断、不重试**，只把「降级 C/D/F」说明注入下游）。分析见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/llm-quality-signal-analysis.md` §2。
- **实现设计**：按缺口**性质**拆两条独立落地路径：

  **A｜同域缺陷修复（无开关，默认路径生效）**——`rf-295` 判为真缺陷，就近修：

  - `report/_llm_news.py::_submit_llm_future` 向 `generate_all_llm` 补传 `degradation_events`（该参数早已存在，仅调用点漏传）→ 持仓体检第 5 维「数据质量」此前恒读「今日无降级记录，所有数据源正常。」（`prompts_tables._build_data_quality_detail_block(None)`），与同批专家复盘的降级摘要自相矛盾；现两侧同源。
  - **主线程取快照**：`DegradationTracker.get_log()` 在提交线程池**之前**由主线程读一次随参传入，避免与工作线程的并发写入交错。

  **B｜LLM 输出侧质量分级（实验功能 `module_quality_gate`，默认关）**：

  - `report/llm_quality.py`（新增）：`grade_module()` 对 4 个 LLM 模块（`global_macro` / `expert_review` / `health_check` / `penetration_deep`）按**触发器**评 A~F——`TRIGGER_EMPTY`/`PLACEHOLDER`（内容缺失）→ F、`TOO_SHORT`/`MISSING_SECTIONS`（结构缺陷）→ D、`THIN`（篇幅偏薄）→ C、`OK` → A~B。阈值按模块分档（`_LENGTH_THRESHOLDS` + `_DEFAULT_LENGTH_THRESHOLDS` 兜底），`_REQUIRED_MARKERS` 校验章节标记。**模块与阈值的对应由提示词章节标记一致性测试锁定**（标记漂移即测试失败）。
  - **只标注、不阻断、不重试、不写回缓存**：`_ADVISORY_GRADES = {C, D, F}` 中**内容缺失型**（`TRIGGER_EMPTY`/`PLACEHOLDER`）**不再叠加横幅**——占位符/空内容本身已是醒目提示（`llm/fallback.py::is_placeholder_content()`），叠加只会重复噪声；横幅只服务「内容在但存在缺陷」的情形。
  - **横幅以【内容质量提示】开头**，而非 `⚠ `——`_FACT_CHECK_FAIL_RE` 用 `^⚠ ` 且无 `MULTILINE`，若以该前缀开头会被 Excel 事实校验误判为失败行。
  - **载体复用模块 HTML 字符串**：横幅与既有截断标记/缓存命中行/占位符/事实校验摘要走同一拼接载体，**HTML 与 Excel 双路径自动生效**，无新增下游透传管道（低技术债的关键取舍）。
  - `report/_report_generation.py` 第 5c 步 seam（决策账本块之后、`perf.stop()` 之前），全程 `try/except` + `reporter` 告警——实验特性故障绝不打断报告主链路。
  - **依赖方向**：模块置于 `report/` 而非 `llm/`——`report/llm_content.py` 依赖 `llm/`，反向依赖构成循环，故质量分级归 `report/` 侧。
- **测试**：新增 2 文件 46 例——`test_llm_quality.py` 31 例（分级口径各触发器边界、横幅构造与文案、缺失型不叠加、载体契约、模块阈值与章节标记一致性锁）；`test_llm_quality_edge.py` 15 例（非 str 输入/空白内容/超长/畸形 HTML/未知模块键/关开关无感）。既有文件扩展：`test_llm_fallback.py`（占位符识别）、`test_orchestrator.py`（`degradation_events` 透传）、`test_config_edit.py`（白名单与 surface 纳入 `module_quality_gate`）、`test_handlers_config.py`（菜单编号连续性）。
- **文档**：`requirements.md`（features.json 29→30 项 + 开关表行）、`technical.md`（新增 §4.11 输出侧质量分级 + 白名单/features.json 计数 + `report/llm_quality.py` 消费者）、`llm-technical.md`（§4.4 degradation_events 暴露 + fallback 模块行）、`folders.md`（目录树 + 统计重算）、`test-coverage.md`（模式/子标记/功能域计数 + `unit/report` 文件数）、`how-to-config.md`（§M 开关表行 + 三入口说明）/ `how-to-config-llm.md` / `how-to-use-tui-menu.md` / `how-to-use-web-mode.md`（实验开关清单与编号）、**`reports-instruction.md`**（§④ 新增「内容质量提示」横幅口径：评级触发表、A/B 不上屏、缺失型不叠加、只标注不阻断不写缓存）、**`faq.md`**（§LLM 相关新增「【内容质量提示】是什么意思」答疑）、**`developer-guide.md`**（「新增 LLM 模块检查清单」补「纳入质量分级」步骤——`_MODULE_KEYS`/`_LENGTH_THRESHOLDS`/`_REQUIRED_MARKERS` 三处登记点及一致性测试）、**`README.md`**（LLM 分析特性行）。
- **记账**：plan-32 标记完成（见 plan.md P4 表）；`rf-295` 移入已解决待归档区。

### 实验功能开关 CLI 参数（`--experiment`）（2026-09-10）

- **背景**：实验性功能开关此前只有 TUI 菜单 **[S]** 与 Web 配置面板两个入口（均由 `features.EXPERIMENTAL_FEATURES` 注册表驱动）；CLI 定时任务/脚本场景只能改用例化 `features.json`，无法「单次运行试用而不污染用户配置」。
- **改动**：`cli/cli.py` 新增全局参数 `--experiment NAME`（`action="append"`，可重复），取值接受**开关名**（如 `signal_pre_digest`）/ **显示名**（如 `信号预消化`）/ **`all`**（全部启用）；`features.py` 新增 resolver 三件套 `EXPERIMENT_ALL` / `resolve_experiment_flags()` / `describe_experiment_flags()`；argparse `type` 回调 `_experiment_name` 在解析期即校验，写错**立即报错并列出全部可选值**（不静默忽略）。`_apply_cli_experiments(groups)` 在 `main()` 拿到配置后调用，**只走运行期 `set_feature_enabled`、绝不 `save_feature_overrides`**——单次运行生效、不写盘；反之用户已开启的开关也不会被本参数关闭。
- **效果**：`TUI 菜单 S` / `Web 面板` / `CLI --experiment` 三入口同源同一注册表，新增实验项自动三处可用。
- **测试**：新增 `test_features.py`（8 例）+ `test_features_edge.py`（7 例）——按开关名/显示名/大小写/`all`/混用去重解析、全注册表条目可解析、未知值上报但保留已命中项、空输入/空白 token/前后空白/无模糊匹配/显示名大小写敏感/重复未知值保留；`test_cli.py` 与 `test_cli_edge.py` 新增参数接线与报错路径用例。
- **文档**：`how-to-use-cli-mode.md`（§2 全局参数表 + 用法示例）、`technical.md`（§1.7.2 参数 + §1.7.3 步骤）、`how-to-config.md`（§M 三入口说明）/ `how-to-config-llm.md`（实验开关 CLI 开启说明）、`README.md`（CLI 示例 + `--experiment` 取值说明）。

### 信号预消化（plan-31）（2026-09-10）

- **背景**：算法层算出的确定性结论有相当一部分只走渲染层、进不了提示词；进了的那部分又存在**裸值歧义**——行业资金流向段原先把净流出拼成「主力净流入-5,000,000」（label 固定「净流入」、数值带负号），模型读到的是自相矛盾的文本，只能靠推断符号含义；且数据源返回顺序无排名语义，截取前 5 行不构成任何「前列」含义。分析见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/llm-quality-signal-analysis.md`。
- **实现设计**：`docs-stm/archive/v0.10.x/tradingagents-borrowing/signal-pre-digestion-implementation.md`。按缺口的**性质**拆两条独立落地路径：

  **A｜资金流方向标注与排名（无开关，默认路径修复）**——判定为真缺陷，就近修：

  - `llm/prompts_signals.py`（新增）：`_build_sector_flow_block` 以「方向词 + 非负量」表达方向（`主力净流出1.20亿` 取代 `主力净流入-120000000`），净占比保留符号（比率非金额，同行有方向词可对照）；**按净额分方向排名**（净流入降序前 3 / 净流出升序前 3）而非合成单榜——只取降序前 N 会在全市场净流出日退化成「回撤最小的 N 个行业」，丢掉风险侧信号；无方向数据回退数据源原始顺序前 N 行。
  - 非有限值不入提示词：`_is_number` 统一排除 `bool`（`True` 会被当 1 元）与 `NaN`/`±inf`（格式化后是 `nan`/`inf` 文字，比裸数值更糟）。
  - `prompts_action._build_global_macro_prompt` 删除内联拼接改调该函数；`_fmt_amount` 万/亿 沿用、未达万级补「元」防裸数字无单位。

  **B｜算法评级信号块（实验功能 `signal_pre_digest`，默认关）**：

  - `_build_signal_digest_block`：市场温度档位（低估→看多 / 高估→看空）、持仓估值分位分布（低估多于高估→看多，并列→中性）、尾部风险幅度（VaR95 ≥3.0→风险高 / ≥1.5→风险中 / 其余→风险低）预消化为 `信号：{指标} {结论}（依据）` 行。**方向轴与风险轴分离**——尾部风险只有幅度没有好淡方向，套「看空」会把「波动大」误述成「看跌」。三路独立取用、缺一律跳过、全不可用返回空串（提示词与未启用时逐字节一致）。
  - 注入专家复盘与持仓体检提示词（仅关键字参数 `enable_signal_digest=False`，位置在【分布】行后、【持仓明细】前——先结论后明细）；辩论模式各阶段不传该参数，属已文档化的 v1 边界。默认路径不传 → 提示词不变、辩论缓存键不受影响。
  - **缓存指纹后缀同源**：开关判定收敛在 `_signal_digest_cache_suffix()` 内部，写侧指纹闭包与 orchestrator 预检闭包无条件同调同一函数（比照 `decision_ledger.lessons_cache_suffix()`）；开关关或块为空 → `""`（不误伤旧缓存），注入时取块内容指纹（信号数值变化即换键）。穿透深度分析不承接信号块故不追加。
  - 只读既有 `pipeline_data` 键，**不新增数据契约键** → 附录 H 无需变更。
- **测试**：新增 2 文件 52 例——`test_prompts_signals.py` 31 例（资金流方向词/非负量/排名/截断/双方向可见/空输入 + `_fmt_amount` 单位边界 + 三路信号方向映射与降级跳过 + 尾部风险档位边界 + 缓存后缀门控与确定性 + 两个提示词构建函数的注入开关 + 两个生成函数指纹接线与预检后缀）；`test_prompts_signals_edge.py` 21 例（畸形行/全非 dict/bool 净额/NaN 净额/字符串涨跌幅/极端净额/缺键回退 + `pipeline_data` 结构畸形/未知档位/非数值分位与 VaR95/缺可选字段 + 开关关闭时畸形数据无感）。`test_config_edit.py` 白名单与 surface 断言纳入 `signal_pre_digest` + 新增写生效用例；`test_handlers_config.py` 新增菜单第 10 项回归 + 第 6 项编号连续性保持。
- **文档**：`requirements.md`（features.json 28→29 项 + 开关表行）、`folders.md`、`how-to-config.md` / `how-to-config-llm.md` / `how-to-use-tui-menu.md` / `how-to-use-web-mode.md`（实验开关清单与编号 6~10）、`technical.md`（features.json 行开关数与注册表项数）。
- **记账**：plan-31 标记完成（见 plan.md P4 表）。实现期自审发现缓存指纹同源偏差（预检侧传 `history_data`、写侧不传 → 三模块预检永不命中，属性能/日志噪声非正确性缺陷），另案登记 rf-297，**不在本项范围内修复**。

### 实验性功能开关上屏（TUI 菜单 S + Web 配置面板）（2026-09-10）

- **背景**：决策跨期反思闭环（`decision_reflection`）此前只能手工编辑 `features.json` 开关，TUI/Web 均无入口——两处 UI 各硬编码了一份**只含辩论**的开关列表（TUI `DEBATE_FLAGS`、Web `_DEBATE_FLAG_KEYS`），非辩论类实验开关无处安放。
- **改动**：两处 UI 统一改由 `features.EXPERIMENTAL_FEATURES` 注册表（唯一事实来源，含显示名 + 说明 + 顺序）驱动——TUI 菜单 S 实验块与 Web 配置面板新增实验开关自动上屏，不再需要逐处手抄列表。Web 面板第 7 组由「辩论实验功能 / `debate`」泛化为「实验性功能 / `experiments`」，`config_edit_whitelist` 第 7 组由注册表生成。
- **效果**：TUI 菜单 S 实验块由 3 项（6-8）扩展为 4 项（6-9），新增第 9 项「⚗ 决策跨期反思闭环」；Web 配置编辑面板「实验性功能（⚗ 实验性，默认关闭）」组新增同名开关；两处与 `features.json` 即改即存。
- **测试**：`test_config_edit.py` 白名单/surface 断言更新 + 新增 decision_reflection 写生效用例；`test_handlers_config.py` 新增菜单第 9 项切换回归 + 第 6 项编号连续性用例。
- **文档**：`how-to-use-tui-menu.md`（§S）、`how-to-config.md`（§M/§P）、`how-to-use-web-mode.md`、`how-to-config-llm.md`、`technical.md`（白名单组描述 + features.json 行）。

### 决策跨期反思闭环（plan-30）（2026-09-10）

- **背景**：原「对判断当次即评、事后无对账」——LLM 看多看空与确定性再平衡/行动建议无法用真实后续行情验证，判断质量无从沉淀、教训无法回灌后续分析。借鉴 TradingAgents-astock 两阶段延迟反馈 + augur「预测-真实结果结算、确定性命中率统计、立即持久化」合成一套闭环（分析见 `docs-stm/archive/v0.10.x/tradingagents-borrowing/reflection-decision-loop-analysis.md` + `augur-borrowing-analysis.md` §建议A）。
- **实现设计**：`docs-stm/archive/v0.10.x/tradingagents-borrowing/decision-reflection-implementation.md`（分层依赖：`core/` 账本零 report/llm 依赖；`report/` 登记/结算/复盘消费 core；`llm/` 经 core 读教训回灌）。
- **代码**（实验功能 `decision_reflection`，默认关，`features.json` 注册）：
  - `core/decision_ledger.py`：决策账本核心——事件 JSONL 原子追加（`data/state/decision_ledger.jsonl`，无模块单例）、结算作独立追加事件（决策事件恒 `pending`）、`fold_ledger` 按 decision_id 折叠；教训区块 `lessons_block`/`lessons_cache_suffix`（md5 → 缓存指纹版本化）；`is_active()` 单源开关。
  - `report/decision_record.py`：确定性载体登记（再平衡/调仓卖出建议，仅带基线价入账保证「入账必可结算」，同日 pending 去重）。
  - `report/decision_llm_capture.py`：LLM 操作建议表结构化解析（表头识别 → 逐代码方向登记，同日去重）。
  - `report/decision_settlement.py`：到期 pending 结算（真实后续行情对账，方向命中/超额 alpha，需样本数守门）。
  - `report/decision_review_block.py` + `action_sheet.py`/`html_writer.py`/`action_section.html`：行动章内嵌「历史决策复盘」区块（HTML+Excel，5 列，命中小样本不报命中率结论）。
  - `_report_generation.py` 两个 seam（确定性结算/登记在 LLM 拉取前；LLM 登记/复盘装配在回退后），`llm/skeleton.py` 教训注入 + `llm/generators*.py` 缓存指纹版本化——实验特性全程 try/except，故障绝不打断报告主链路。
- **测试**：新增 6 文件 109 例（决策账本核心 30 + 边缘 16 + 记录 12 + LLM 捕获 22 + 结算 14 + 复盘区块 7）+ 既有行动双端 8 例（HTML 3 + Excel 5）扩展；决策复盘全套件含 render/excel 均通过。
- **配套**：folders.md 目录树/统计（主程序 245→250 / 测试 309→315 / 测试用例 5,560→5,677 / 项目文档 119→120）+ test-coverage.md 计数同步。
- **记账**：plan-30 标记完成（见 plan.md P4 表）。

### DeepSeek v4-flash 定价更新（2026-09-10 官方降价）（2026-09-09）

- **背景**：DeepSeek 官方自 2026-09-10 12:00（北京时间）起对 v4-flash 系列降价（最高 60%），闲时 输入 ¥1.0/输出 ¥4.0/缓存命中 ¥0.02，高峰价翻倍 ¥2.0/¥8.0/¥0.04（元/百万 token）。本次降价**仅影响 flash 系列**，`deepseek-v4-pro` 与 `deepseek-chat` 价格不变。
- **改动**：`core/constants.py` `MODEL_PRICING` 中 `deepseek-v4-flash` 更新为新价（含注释说明降价生效时点与范围）；`config/_llm_settings_defaults.py` 计价注释示例同步刷新。
- **文档**：`llm-technical.md` 附录定价表 flash 行与 `how-to-config-llm.md` 定价参考同步为 2026-09-10 降价后数值。
- **测试**：`test_llm_utils.py` 费用断言按新价更新（闲时 ¥0.011/¥5.000、高峰 ¥10.000、缓存命中、周末闲时各场景）。
- **记账**：本变更不涉 plan-/rf- 编号（例行数据/文档刷新）。

### 事实校验品种代码笔误自动纠正（rf-296）（2026-09-09）

- **问题**：LLM 把持仓代码易位一位数字的笔误（实盘穿透深度模块 561910→161910）只有品种存在性**告警**、无自动纠正通道——用户需手工核错。唯一候选（编辑距离=1 唯一近邻）与其真实组合权重 10.2%（35516/347197）吻合也被放过。
- **代码**：`src/python/llm/fact_checker/` 新增代码笔误自动纠正通道——`_corrections.py` `detect_code_corrections`/`apply_code_corrections`，辅助 `_utils.py` `_build_stock_weight_map`/`_edit_distance_le_one`。三个条件**全满足**才纠正：错码非 直接持仓/穿透 extra/常见指数 有效集且非建议语境、恰好**唯一**直接持仓代码与其编辑距离≤1、错码 token 后 ~24 字符内权重声称（占比/规模达/权重达，窗口常量 `_CODE_WEIGHT_SCAN_WINDOW`）与候选真实组合权重在默认容差 1.0pt 内吻合。`_runner.py` 在品种告警基础上接入，镜像数值修正纳入「已修正明细」摘要与日志并从 ⚠ 剔除；代码纠正全文替换（错码是单一所指，不做 count=1）。
- **测试**：`test_fact_checker.py` 新增 `TestCodeTypoAutoCorrection` 8 例（实盘 161910/561910 检出+纠正+reason 带候选权重、全文替换、权重不吻合/多近邻歧义/建议语境/穿透 extra 排除/指数碰撞不误改、run_fact_check 整链路自动修正并入明细）；fact_checker 全 132 用例通过。
- **边界说明**：数值检查器仅认 `占比/仓位/集中度` 权重语境，"规模达"仅代码纠正通道本地窗口认——建议语境引用非持仓代码（合法推荐）、歧义多近邻、指数/穿透代码一律不自动纠正。
- **记账**：rf-296 修复归档（见 review-findings.md 已解决区 v0.10.16-dev）。

### LLM 输出侧借鉴评估 + 待办登记（2026-09-09）

- **借鉴评估**：外部仓库 TradingAgents-astock 与 BruceLanLan/augur 的机制借鉴评估，识别 7 条可借用点登记为 P4 实验级候选（缺省关闭、需显式启用），见借鉴评估分析文档（现归档于 `docs-stm/archive/v0.10.x/tradingagents-borrowing/` 与 `augur-borrowing/`）+ plan.md P4「借用探索候选」表：
  - TradingAgents-astock（2026-08-29 评估）：决策跨期反思闭环、信号预消化、模块级质量分级注入、决策头结构化+确定性解析兜底 → **plan-30/31/32/33**
  - augur（2026-09-09 评估）：确定性结算学习、live/demo 标签纪律、健壮性三件套 → **plan-30 合并评估 + plan-34/35**
- **待办登记**：借鉴分析同步发现 2 条 LLM 输出侧质量缺陷，登记 `review-findings.md` P2C（详见该文件）——
  - **rf-295**：`_submit_llm_future` 漏传 `degradation_events` → health_check「数据质量」维度恒报全正常，与 expert_review 降级摘要口径可能矛盾（关联 plan-32 可作最小起步验证）
  - **rf-296**：品种代码笔误（如实盘 561910→161910 易位一位）无自动纠正通道，fact_checker 仅告警不修正，唯一近邻 + 权重吻合也被放过 → **已随「品种代码笔误自动纠正（rf-296）」修复条目解决**（见本版本上方条目）
- **配套**：folders.md 目录树/统计新增 `docs-stm/plan/` 3 份分析文档（project 文档 116→118 / 46,372→46,773）。

### 开发版本切换（2026-08-29）

- 发布 v0.10.15 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.16-dev。


## [0.10.17] - 2026-09-10

### 版本发布 v0.10.17（2026-09-10）

- **发布流程**：P2 发布门禁通过（`test-runner --mode verify,regression` 4513 通过 0 失败 + code/doc/task-numbering/semantic-index 四检查全绿 + 发布手动验证 `--mode perf,security` 14 通过）；版本号全链一致化至 v0.10.17（`constants.py` / `pyproject.toml` / `README.md` / 10 份管理文档）；发布数据文档刷新（`collect-test-coverage.py` 实时收集 6,595 项与 `test-coverage.md` 模式表、功能域/子标记/跨类各表逐项核对一致，`folders.md` 统计表六项与实测一致：主程序 266 文件 66,110 行 / 模板 4 文件 3,826 行 / 脚本 21 文件 7,174 行 / 测试代码 351 文件 98,343 行 / 测试用例 6,595 个；模式对应测试量与环境耗时对照已是本机 2026-09-10 实测快照）。
- **版本标签**：`git tag v0.10.17` 已打并推送，发布可追溯。
- **已解决项归档**：v0.10.17-dev 已解决项（rf-297、rf-303、rf-305 ~ rf-321，共 19 条）整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md` v0.10.17 章节，原文件保留待办区与归档引用。
- **本版内容概览**：数据源适配契约（实验功能 `datasource_adapter`，默认关）与凭据声明/就绪指引（实验功能 `datasource_credential_ready`，默认关）、数据源记录-回放（测试基建，无开关）与模块缓存指纹治理（读写同源 + 提示词内容覆盖 + 数据质量详细状态块纳入），另含 19 项自审修复与文档漂移校正。

### 数据源文档归因校正（自审 rf-321）（2026-09-10）

- **缺陷（自审 rf-321）**：`fetcher/chain.py` 的两处注释与五份文档（`datasource.md`、`datasource-reliability.md`、`faq.md`、`requirements.md` R-HST-07、`technical.md` 链路图）均称美股指数历史链路「新浪未实现 `fetch_index_kline`、探测到即跳过，实际发请求的只有腾讯」。**与代码不符**：`providers/sina_kline.py` 实现了 `fetch_index_kline`（`days = min(max(days, 5), 2000)`）并经 `providers/sina.py` 重导出，`chain.py` 的 `getattr(mod, "fetch_index_kline", None)` 对新浪命中非 `None`，链上会**真实向新浪发出请求**；「跳过」的真实原因是该源 `getKLineData` 端点对所有代码返回 404/空（该模块自述「保留此实现作为代码级备用」），不是缺实现。归因写错会把「端点取空」误导向「未实现」的排查方向。
- **改动**：注释与五份文档统一为「新浪侧实现存在，但其 `getKLineData` 端点对全部代码返回 404/空，实际取数通常由腾讯承担」；同批修正 rf-317 变更日志条目内的同一处归因（该条目与本条同版发布，未对外成为历史记录）。链路分派逻辑本身无需改动，`test_chain.py` 断言不受影响。
- **同批校正**：核对数据源清单时另发现两处实现描述失真——`datasource.md` 基金持仓行主链路主机写成 `fundf10.eastmoney.com`（实为 `fund.eastmoney.com/{code}.html`，`fundf10` 是该链路的季报 API 回退）且漏登回退链路；`datasource-reliability.md` §3.8 称指数 K 线 `datalen` 上限 3650（provider 侧实为 2000，3650 是取数层钳位）。另按实现校正三处口径：失败路径「重试（最多 3 次）」（链路逐 provider 单次调用、无请求级重试，3 是熔断阈值）、K 线字段「含涨跌幅/换手率」（实为开高低收 + 成交量，涨跌幅由相邻收盘价推得、换手率另由两期持仓计算）、`price_fund_otc` 回退条件「JSONP 解析失败」（实含超时 / 请求错误 / 无净值记录）。

### 管理文档悬挂项清理与统计快照校正（2026-09-10）

- **`plan.md` 悬挂完成项**：`plan-29`（DeepSeek 峰谷定价适配周末全天闲时）状态已是「完成（2026-08-28）」却仍留在「当前迭代待办 → P1 — 当前待办」表内，与该文档文首「仅收录未完成计划项」的口径相悖，且该编号未见任何归档。已自待办表移出（P1 小节改为「无待办项」+ 归档指引）。
- **归档补登**：`docs-stm/archive/v0.10.x/archived_plan.0.10.x.md` 的「v0.10.x 已完成项」表补 `plan-29` 行（代码/配置/测试/文档四处改动摘要 + 已完成版本 v0.10.15），归档头「涵盖版本」扩展至 v0.10.15、「归档内容」计入 plan-29，并记录第四次合并 plan.md 已完成事项。
- **P2A 行数快照刷新**：`review-findings.md`「文件过长」表 8 行按 2026-09-10 实测更新——`core/registry.py` 666（较登记 +1）、`report/data_status.py` 544（+8，数值归一防线纳入）、`report/html_renderers.py` 521（−5，渲染重构后缩减）、`fetcher/fund.py` 405（+4）、`cache/operations.py` 633（−2）、`report/excel_generator.py` 427（+4，决策登记载体纳入）；`fetcher/batch.py` 564、`core/code_utils.py` 542 维持不变。8 项均无 **>800 行硬上限**违规，各行既有结论（维持现状 / 未超限 / 500-800 可选优化）不变。
- **`folders.md` 统计校正**：管理文档行 10,195 → **10,202**、项目文档合计 49,726 → **49,761**、版本归档 37,722 → **37,750**（105 md 累计 37,292 行）。数值以发布前终态实测为准——上一轮记录值 10,195 较上一轮快照提交时实际 10,203 少 8 行；本轮中途曾按当时状态记 10,208 / 49,740 / 37,723（md 37,265），随后同版新增 rf-321 归档行与变更条目、`review-findings.md` 已解决区清空（−27 行）使该批数值失效，故整体改为发布前终值（含本条变更日志自身所占行）。用户文档 11 文件 / 5,005 行与 manuals 10 文件 / 4,804 行复核一致，未改动。

### 开发版本切换（2026-09-10）

- 发布 v0.10.16 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.17-dev。

### 测试覆盖与目录统计快照刷新（2026-09-10）

- **`test-coverage.md`**：模式对应测试量与环境耗时对照由 `.venv/bin/python scripts/test-runner.py --mode bench --update-docs` **自动回填本机实测**（dragonball，2026-09-10）——`unit` ~13s、`all` ~22s、`verify,regression` ~28s 等；覆盖项数与 `scripts/collect-test-coverage.py` 实时收集结果一致（总收集 6595）。修正正文两处与表格脱节的旧值：「环境耗时对照」引言仍写 dragonball 为 08-07 采集（表格已是 09-10），差距说明引用的 `unit ~15s` / `all ~23s` 未随表格刷新。
- **`folders.md`**：项目统计表按本机实测刷新——主程序 66,110 行、测试代码 98,343 行、测试用例 6,595 个、用户文档 5,005 行（README 201 + manuals 4,804）、项目文档 49,720 行（CLAUDE.md 74 + managements + plan + archive 105 md）、目录树补 `src/test/unit/report/test_experimental_seams.py` 条目。
- **说明**：本轮仅刷新数据快照（非版本号），与 rf-320 的文档漂移校正同批落地。

### JSONL 原子写入与信号账本落盘结果如实上报（自审 rf-315 / rf-316）（2026-09-10）

- **缺陷（自审 rf-315）**：`core/jsonl_store.py::append_jsonl_atomic` 把 `tempfile.mkstemp()` 与随后的写入 / `os.replace()` 包在**同一个 `try`** 里，而 `except` 分支要引用的 `tmp_path` 正是 `mkstemp` 的返回值——**`mkstemp` 自身抛 `OSError` 时该名字尚未绑定**，清理分支会再抛 `UnboundLocalError`，把真实错误（目录不可写等）掩盖成一条自指异常。同一函数的签名返回 `None`、失败仅记日志，**成功与失败对调用方不可区分**。
- **缺陷（自审 rf-316）**：`core/signal_ledger.py::append_signals` 因此**在落盘失败时仍返回去重后的 `fresh`**——调用方据此统计「本次入账 N 条」并渲染绿色成功行，而账本零新增（磁盘满 / 无写权限时静默失效）。确定性信号账本是报告结论的事实来源，账本内容与统计口径不一致会让「统计只算实时记录」的纪律失真。
- **改动**：`mkstemp` 拆为独立 `try` 并返回 `False`；写入 / 替换段保留原清理逻辑（删临时文件 + 记异常日志 + 返回 `False`）；函数签名 `-> None` 改为 `-> bool` 并在 docstring 增加 `Returns:` 说明「失败只记日志不抛出，但**成功 / 失败必须如实上报**」。`append_signals` 收下该布尔结果，**失败时返回空列表**（docstring 写明），使调用方计数与账本实际内容同源。
- **测试**：`test_jsonl_store.py` 新增 3 例（成功返回 `True`；替换失败返回 `False` 且**原文件内容不变**；创建临时文件失败返回 `False` 而非抛 `UnboundLocalError`——已验证还原旧实现后此例转红）；`test_signal_ledger.py` 新增 2 例（写盘失败时入账数为 0、单条登记失败时返回 `None`）。

### 美股指数历史链路分派补齐（自审 rf-317）（2026-09-10）

- **缺陷（自审 rf-317）**：`fetcher/chain.py::_call_history_provider` 只按 `chain_name` 分派「A 股指数 / 基金净值 / 股票行情」三类取数函数，`history_index_us` **落入 `else` 分支**——该分支从不调用任何 provider，按无实现者处理并落到末尾「未知函数」告警。后果是 `fetch_index_kline('gb_*')` **恒返回空**，用户看到「美股指数历史数据缺失」而没有任何配置错误；告警文案指向内部符号名而非真实原因（该链路根本没接函数），排查方向被带偏。
- **改动**：补 `history_index_us` 分派（与 `history_index` 共用 `fetch_index_kline`），仅在命中 provider 确实实现该函数时才发起请求，无实现者落到统一的「函数名未实现」可读原因；`fn_name` 映射表同步补齐。链路注释写明现实约束：**实际取数通常由腾讯承担**（新浪侧虽有 `fetch_index_kline` 实现，但其 `getKLineData` 端点对全部代码返回 404/空；归因详见本版 rf-321 条），且腾讯 K 线接口对 `gb_*` 代码支持有限——**该链可能整链取空，空结果按正常降级记录、不视作配置错误**，避免把「该源本就不提供」误报成故障。
- **测试**：`test_chain.py` 新增 `test_call_history_provider_dispatches_us_index`（断言确实调到腾讯 `fetch_index_kline`、且不再产出「未知函数」告警），已验证还原分派前该用例转红。
- **文档**：`datasource.md` / `datasource-reliability.md` / `requirements.md`（R-HST-07）/ `technical.md` 链路图的既有描述同步改写为「美股指数历史链路实际取数通常由腾讯承担，可能整链取空」（其中归因措辞的最终校正见本版 rf-321 条）。

### 数据质量详情「未提供」判据两侧归一（自审 rf-318）（2026-09-10）

- **缺陷（自审 rf-318）**：`llm/prompts_action.py` 判断数据质量详情「未提供」用 `is None`，而模块指纹侧（`ModuleFingerprintInputs.data_quality_text` 的 `data_quality_text or ""`）把空串一并折叠成「无」——**同一实例在两个消费点被判成不同状态**：传空串时指纹侧按「无数据质量段」哈希，提示词侧却认为「已提供」并渲染出一个空段。当前调用方（`generate_all_llm()` 一次渲染、两侧共享同一实例）恰好只传非空串或 `None`，缺陷不显现；但该函数是公开入口，判据分叉属结构性隐患（rf-308 建立「一次渲染两侧共享」纪律时遗留的口径不一致）。
- **改动**：提示词侧判据改为 `not data_quality_text`，与指纹侧折叠口径一致；docstring 写明「未提供」含 `None` 与**空串**两种，并说明为何必须用 `not` 而非 `is None`——若只认 `None`，空串会渲染成空段却与 `None` 共用同一指纹，即「提示词变而键不变」。
- **测试**：`test_pipeline_metrics_injection.py` 新增参数化用例（`None` 与 `""` 渲染出**逐字相同**的提示词）与「数据质量文本与模块指纹同源」断言。

### 实验挂载点导入契约与注释校正（自审 rf-319）（2026-09-10）

- **缺陷（自审 rf-319）**：`report/_experimental_seams.py` 的模块 docstring 只说明「被调子模块在挂载点内按需导入」，未记录真正的分界契约——`core` 账本模块（`decision_ledger` / `signal_ledger`）是**顶层导入**（`is_active()` 开关判定本身要落在它们上，且二者只依赖 stdlib + 同层 core，不构成启动负担），report 子模块才是按需导入。读者按唯一口径理解，会把新增顶层导入当成无害、或把既有顶层导入当成违规。
- **改动**：docstring 改为显式区分**两类导入**，按「开关关闭时是否值得付出成本」给出判据；该分界由 `test_experimental_seams` 的接线守卫逐项锁定（顶层 `src.python.*` 导入集合必须恰为两个 core 模块 + `report.progress` 接口），使文字描述与可执行断言同源。
- **同批注释校正**：`core/doctor.py` 的目录探针注释把持久化路径误写为 `data/state`（实为 `data/cache`、`logs/`），并改写输出目录缺省值的说明为「仅当配置该键取空值（空串）时才用到」，去掉无法核实的措辞。

### 管理文档与用户文档第二批漂移校正（自审 rf-320）（2026-09-10）

- **缺陷（自审 rf-320）**：plan-36~38 三条数据层实验机制落地后，管理文档与用户文档仍有成片内容未随代码复核——
  - **自检分组枚数**：`doctor` 在四处仍写作「五组 / 六组」（`technical.md` 概览表与 §4.17.3、`requirements.md` §3.6、`plan.md` 的 plan-35 完成态），实际已是**七组**（环境 / 配置 / 目录 / 功能开关 / 数据源适配 / 数据源凭据 / 数据源）。同一特性在计划表与设计文档给出相反的分组数，读者无法判断哪份为准。
  - **LLM 子模块计数**：`technical.md` §5.1 称 `llm/` 包「共 34 个子模块」，实测 **35**（26 个顶层模块 + `fact_checker/` 子包 9 模块）；`llm-technical.md` §2.1 模块表**漏登** `_hallucination_filter.py`（该模块自辩论虚构过滤改造起就在，且被 `generators.py` 实际引用）。
  - **测试驱动脚本口径**：`developer-guide.md` 脚本一览写「支持 14 种 `--mode`」，`scripts/test-runner.py::MODES` 实为 **17** 个键；模式对照表把 `all_no_unit` 的等效表达式写成 `not unit`（实为 `not unit and not live`，会连带把 opt-in 联网套件纳入），并漏掉 `perf` / `security` / `live` 三个定向模式。
  - **测试统计快照**：`test-coverage.md` 的模式计数、单元子标记、功能域、跨类四张子表停在旧快照（`unit` 6274→6283、`all` 6583→6595、`unit_web` 213→215、`unit_core` 1126→1131、`unit_llm` 933→935、`llm` 跨类 736→738 等），且 `unit_web` 一处 213 与另一处 215 自相矛盾。
  - **目录与统计**：`folders.md` 目录树缺 `src/test/unit/report/test_experimental_seams.py` 条目，统计表「主程序 / 辅助脚本 / 测试代码 / 测试用例 / 用户文档 / 项目文档」六项数据过期。
  - **用户文档**：`how-to-start.md` 指向**并不存在**的 `scripts-reference.md`（死链）；`how-to-config.md` 的 TUI 菜单键列表漏 `D`/`P`/`I`/`A`/`S`/`R`/`V`/`H`/`F`/`X` 等且未标注门控；`how-to-use-cli-mode.md` 把 `doctor --timeout` 描述成单次请求超时（实为**整轮网络检查**的耗时预算）；`faq.md` 的日志行号引用整体偏移、美股指数基准问答与实现不符；`datasource.md` / `datasource-reliability.md` / `requirements.md` R-HST-07 仍称美股指数历史由新浪承担（新浪无 `fetch_index_kline` 实现）。
- **改动**：逐项对照代码与实时收集结果更新上述文档。统计类数据以 `scripts/collect-test-coverage.py`（测试计数，6595）与本机实测（主程序 66,112 行 / 测试代码 98,348 行 / 项目文档 49,677 行）为准回填，避免再出现同一数字两处不一致的情况。

### 报告管线实验挂载点抽取公共守护（自审 rf-310）（2026-09-10）

- **缺陷（自审 rf-310）**：实验性功能接入报告管线时，四个挂载点（决策跨期反思闭环的确定性结算/登记、决策的 LLM 注入、模块级质量分级横幅、确定性数值信号沉淀）**各自内联一份** `try/except Exception` + 告警 + 异常日志。守护判据复制即漂移——告警文案与日志标签逐处重写，改一处必漏三处（与缓存指纹「读写两份拼接」同一病根）；`report/_report_generation.py` 因这四个内联块**越过 800 行硬上限**（实测 817 行）；挂载点本身**零直接测试覆盖**——内联在管线函数中只能靠驱动整条报告管线覆盖，开关判定与数据注入此前无任何直接断言。
- **抽取**：新增 `src/python/report/_experimental_seams.py`，四个挂载点收敛为四个函数，共用一份 `_guarded()`（异常 → 一条告警 + 一条异常日志 + 兜底值，绝不外抛）。被调子模块在挂载点内**按需导入**——开关关闭时不付导入成本，导入期异常也落入同一守护（与下游逻辑异常一视同仁）。`_report_generation.py` 降至 736 行回到上限内，且只按序调用挂载点。
- **顺序契约**写入模块 docstring（由调用方保证，不得调换）：① 结算先于 LLM 拉取（否则当次教训含本批结算结果在注入前未落档，提示词读不到新结算）；② 质量横幅晚于决策登记（横幅改写模块内容文本，须避开操作建议表解析）；③ 信号沉淀晚于 LLM 生成（尾部风险等键在 LLM 生成阶段才注入 `pipeline_data`，过早登记会漏采）。
- **测试**：新增 `src/test/unit/report/test_experimental_seams.py` 16 例（开关关 → 无副作用、管线数据不被触碰；开关开 → 按契约向 `pipeline_data` 注入；下游异常 → 只告警不外抛且返回输入原对象；缺下游符号 → 安全降级返回输入；被调子模块确为按需导入），含 AST 断言「四个挂载点的调用顺序与文档一致」与「除进度上报器外无 report 子模块被提前导入」（该断言把顺序契约从口头约定变为可执行守卫）。已验证四个方向变异各自转红：去掉开关判定 / 收窄守护范围 / 改横幅兜底值 / 交换调用顺序。
- **架构约束**：该机制登记为架构设计约束表新增的「报告管线实验挂载点集中」约束行（约束表相应扩展，双检查脚本的约束代号匹配范围同步放开）。

### 体检目录探针测试隔离（自审 rf-311）（2026-09-10）

- **缺陷（自审 rf-311）**：体检（`doctor`）以「写入再删除 `.doctor_write_probe`」验证输出目录/缓存目录/日志目录「存在且可写」，但探针目标在函数内直接取自配置，**无任何可替换的注入点**——测试运行体检时探针作用于用户的真实 `reports/`/`data/cache/`/`logs/`（实测真实报告目录出现 `.doctor_write_probe` 残留），违反「测试不得修改用户数据」的敏感路径隔离纪律。
- **修复**：把探针目标提为**单一可替换来源** `_probe_targets()`（其返回值即探针实际作用的目录列表），`src/test/conftest.py` 增加 session 级 fixture 将其重定向到临时目录，隔离不依赖测试自行清理。
- **验证**：端到端确认探针解析到 pytest 临时目录，真实 `reports/`/`data/cache/`/`logs/` 无 `.doctor_write_probe` 残留。

### 注释漂移修正与文档同步（自审 rf-312 / rf-313）（2026-09-10）

- **注释漂移（自审 rf-312）**：① 实验功能注册表注释把 CLI 侧描述为可用 `--experiment` / `--no-experiment` 双向覆写，而 `--no-experiment` 参数**并不存在**（CLI 只有只开不关的 `--experiment`）；② 实验功能提示函数的 docstring 称「在 main() 中调用（TUI/CLI 均在配置初始化之后调用）」，实际唯一调用点是报告入口——TUI/CLI/Web 三入口均经该点统一触发；③ TUI 缺省菜单键的合法键注释列表漏掉系统自检项（受实验开关门控），据此配置的用户无法判断其是否可用。三处均按代码现状改写，并在键列表处注明门控与裁剪后的回落行为。
- **文档同步（自审 rf-313）**：核对全部管理文档与用户文档相对代码现状，修正成片漂移——实验开关计数（33 → 35）、TUI 试验功能面板编号（6-14 → 6-16，补登两条数据源相关实验开关）、`features.json` 键表、unit 子标记清单（`testplan.md` 与 `developer-guide.md` 两处均删除并不存在的 `unit_config_edge` 并补 `unit_web`，子组数相应由 13 改为 12）、`test-runner.py` 的模式表达式（`dev-verify`/`verify` 补回漏写的 `unit_web`，与脚本 `MODES` 定义逐字对齐）、十余处 shell 示例改回项目虚拟环境解释器、`developer-guide.md` 补登 `doctor`/`view-logs`/`cassettes` 子命令、`folders.md` 与 `test-coverage.md` 的统计快照按实时收集结果刷新。**架构设计约束表新增三条约束行**（报告管线实验挂载点集中 / 实验功能开关注册表唯一事实来源 / 凭据值不落日志与产物），双检查脚本的约束代号匹配范围与 `CLAUDE.md` 的条数说明同步放开，避免新约束代号成为检测盲区。

### DeepSeek 已停用别名定价与文档口径校正（自审 rf-303 / rf-314）（2026-09-10）

- **背景**：接入 V4.1-Flash 正式名（`deepseek-flash`）时只补新名、未审旧名语义，遗留两处未经官方确认的定价口径（rf-303）与一处用户可见误导（rf-314）。
- **核实结论**：`deepseek-chat` / `deepseek-reasoner` **不是**独立模型，而是 flash 系列**非思考 / 思考模式的兼容别名**，已于 **2026-07-24 23:59（北京时间）停用**，端点不再接受新请求。
- **代码**：`core/constants.py` 两个别名条目由 V3 口径（输入 1.50 / 输出 4.50 / 缓存命中 0.05，高峰翻倍）改为与 flash 系列一致（1.00 / 4.00 / 0.02，高峰 2.00 / 8.00 / 0.04），并补齐此前缺失的 `deepseek-reasoner` 条目——`estimate_cost()` 对该名曾返回 `"-"`、费用页签显示为空。条目**保留而非删除**：报告与性能页签要用本表估算停用前历史调用的费用，删条目会让那段记录一律显示为 `"-"`。`llm/api_base.py` 的推理族名单继续保留 `deepseek-chat` 并写明保留理由（存量配置与第三方兼容端点仍可能发出该名，命中名单才能照旧施加「未开思考时显式禁用」的安全网，删掉反而让这类请求落入默认思考模式占满 `max_tokens`）。
- **测试**：`test_llm_utils.py` 新增 3 例锁定「模型名 → 单价」断言——两个别名在闲时 / 高峰两段均与 `deepseek-flash` 同价且不为 `"-"`、缓存命中价走 0.02 而不回落为输入价、两条目均在 `PRICING_MERGED`；先补断言再改单价，避免误改造成费用估算偏移。
- **文档**：`how-to-config-llm.md` 单价表以 `deepseek-flash` 取代原先的 `deepseek-chat` 行，另起一行合并说明两个已停用别名的语义、下线日期与「条目仅保留供历史计费」；`llm-technical.md` 附录 B 补 `deepseek-reasoner` 行、两条别名行标注为已停用别名、峰谷定价的模型清单同步补齐。

### check-sources 超时行符号与统计口径归一（自审 rf-309）（2026-09-10）

- **缺陷（自审 rf-309）**：`check_sources.run_check_sources` 的结果行**符号与统计口径不一致**——统计分支判 `"timeout" in message or "超时" in message` 两种措辞，符号分支只判 `"timeout"`。而本文件自身产生的预算超时行消息恰是 `超时（预算 15s）`（不含 `"timeout"` 子串），于是该行**被计入 `warn_count` 却渲染成 `❌`（红色错误）**：汇总行说「⚠️ 1」、行首说「❌」，同一行自相矛盾。计数是对的（退出码仍为告警级 1），**渲染是错的**，用户据此以为源故障要去排查，而实际只是本次探测超出耗时预算。在 plan-38 改造该分支（新增凭据跳过态）时发现。
- **改动**：把措辞判定提为单一变量 `timed_out = "timeout" in msg.lower() or "超时" in msg`，统计与本轮改写的符号分支**共用同一判据**，口径归一——这类「判据复制两份」正是漂移的温床，与 rf-297（缓存指纹读写两份拼接）同属一个病根。
- **测试**：新增 2 例——预算超时行渲染为 `_WARN`、汇总计入告警、退出码 1；真实失败（非超时措辞）仍渲染 `_ERR` 且退出码 2（防修复过度放宽）。已验证把符号分支退回旧判据后首例转红（实测行首为 ❌）。

### 数据源凭据声明与就绪指引（plan-38，实验功能 `datasource_credential_ready` 默认关）（2026-09-10）

- **背景**：当前数据源**全部免费无需凭据**，但 LLM 侧早已暴露同一问题模式——缺 key 时若在调用点裸报错，用户看到的是传输层异常而非「你缺什么、去哪申请」（plan-35 的 `doctor._check_llm_credentials` 即为此而写）。借鉴 OpenBB 把「此源需什么凭据」**声明在 Provider 定义里**的做法，把这套「声明 → 就绪判定 → 可读指引」补到数据源侧，使将来接入任何需 key 的源时链路能**主动跳过**它并给出指引（而非当作「不可达」反复重试、甚至计入熔断）。分析见 `docs-stm/archive/v0.10.x/openbb-borrowing/openbb-data-provider-analysis.md` §建议D；实现设计见 `docs-stm/archive/v0.10.x/openbb-borrowing/datasource-credential-ready-design.md`。
- **声明即数据（不为演示编造假数据源）**：新增 `core/datasource_credential.py`——`CredentialSpec` 冻结 dataclass（`source_id` / `display_name` / `env_var` / `apply_url` / `note`）+ `CREDENTIAL_SPECS` 注册表 + `register_credential_spec` / `missing_credential` / `credential_hint` / `credential_readiness`。**生产注册表为空**（全部免费源是事实），机制由**注入合成声明**的单元测试证明可用。就绪判定读环境变量，**空白串（含纯空白/换行）视为缺失**——防「设了空值以为配好了」；源未声明 → 不需凭据。就绪矩阵**自身不抛异常**（体检与健康检查共用，不能因声明写错而崩）。
- **链路主动跳过（两处，非一处）**：`fetcher/chain.py` 的 `fetch_with_fallback` 在熔断检查之后做凭据预检，缺失则 `continue` 到下一链路；**历史走势的 `_try_providers` 遍历循环同样受控**（设计原稿只写了前者——只堵主链路等于机制半应用，缺凭据的源仍会在历史链路里被反复调用并计入熔断）。语义与既有「已被熔断跳过」「未知 Provider」两处 `continue` 完全同例：**不计入熔断失败计数**（配置级问题≠源不可达），仅以可读原因进入 `FailureDiagnostics`，随降级事件上屏到数据源可用性矩阵。
- **健康检查跳过态与就绪行**：`core/check_sources.py` 的 `_checks` 由三元组扩为 `(source_id, 显示名, 用途, 探测函数)`，`source_id` 与 provider 名对齐（新闻源带 `_news` 后缀消歧——「东方财富（净值）」与「东方财富新闻」显示名相近而 provider 名不同，按短名对齐会让凭据声明挂错源）。缺失凭据**不发起探测**，直接产出跳过项并对称使用文件中**已定义但至今未使用**的 `_SKIP` 符号 `⏭️`，消息为可读指引；跳过项计入 `skipped` 而非 `err`/`warn`，**不改变退出码**；开关开启时输出末尾追加就绪摘要行。
- **体检分组**：`core/doctor.py` 新增 `GROUP_CREDENTIAL`「数据源凭据」组（插在「数据源适配」与「数据源」之间）——无声明报「N 个数据源均无需凭据（免费源）」，存在缺失则报失败项并附变量名修复建议（复用 plan-35 的 `_item(..., hint=...)`）。「数据源」组据此**过滤掉凭据跳过项**：凭据未探测的源已由新组专门报告，若网络组照旧渲染成 `[ERR]`，同一配置问题会被计成两次失败并误导用户去查连通性。
- **安全口径**：凭据只从环境变量读取，**值永不落日志、永不写入报告与缓存**——日志与就绪矩阵只出现「变量名 + 是否就绪」以及申请地址。
- **开关关闭时零行为分支**：开关关闭 / 无声明凭据时上述分支恒不触发，链路照常尝试、无跳过项、无就绪行、无凭据组，输出与未引入本机制时逐字节一致（实测 `doctor` 与 `check-sources` 分别不再输出凭据组与就绪行）。
- **测试**：新增 50 例 / 6 文件——`test_datasource_credential.py`（声明表/空白串视为缺失/指引措辞/就绪矩阵）、`test_datasource_credential_edge.py`（`unit_core`+`edge`：空表、声明缺 `env_var`、各类空白字符、重复注册、清空回落）、`test_credential_gate.py`（`unit_fetcher`：缺凭据跳过并落到下一链路、可读原因进诊断、**断言 `record_failure` 未被调用**、补凭据后正常参与、开关关闭不预检、未声明源不跳过；历史遍历循环同上）、`test_check_sources_credential.py`（缺凭据不探测、跳过态不影响退出码、就绪摘要随声明变化）、`test_doctor_credential.py`（开关关闭不产出该组、无声明报免费源、缺失给变量名建议、就绪报通过、**就绪矩阵读取失败转失败项而非抛出**、网络组过滤跳过项）、`test_health_credential.py`（`unit_web`：`/api/health` 的 `skipped` 标记透传到前端）。既有 `test_check_sources.py` 的全部 `_checks` 桩同步改为四元组；新增 `conftest.py` autouse fixture `_auto_reset_credential_specs` 保证声明表在用例间不串味。
- **文档**：`technical.md`（新增 §2.7 + TOC + 语义命名表三行）、`requirements.md`（新增 §5.8 需求 R-CRD-01~08 + 配置开关表行）、`how-to-config.md`（开关总数 34→35、新增开关说明行、实验功能面板段落补一条、代码分派表补键名）、`how-to-config-llm.md` / `how-to-use-cli-mode.md` / `how-to-use-tui-menu.md` / `how-to-use-web-mode.md` / `faq.md` / `test-coverage.md`（`doctor` 分组枚举由「五组」更正为「七组」——plan-36 新增适配组后这五处描述已滞后，本轮一并校正）、`folders.md`（目录树补 1 个源码文件 + 6 个测试文件）、`plan.md`（本条完成态）。

### LLM 模块缓存指纹读写同源（2026-09-10）

- **缺陷（自审 rf-297）**：写侧（`generators.py` 各生成器内的指纹闭包）与预检侧（`generators_orchestrator.py::_compute_module_cache_info`）**各自拼接**同一模块的缓存指纹，仅靠两侧注释声明"须同步"。实际已双向漂移：预检侧把组合风险信号摘要（`history_data` 的最大回撤/年化波动/区间收益/状态，经 `_build_competitive_context_block` 进入智囊团复盘提示词）计入指纹而写侧未计入；写侧把辩论增强开关后缀（`_c`）计入而预检侧未计入。后果是**读写键相互错开、永不相等**——写侧照常写缓存，预检侧却恒不命中，表现为「开关与参数看似生效、每次报告仍全量派发 LLM」的静默退化：专家复盘/健康体检/穿透深挖三个模块每次都重复调用（费用与耗时随报告规模线性放大），且无异常、无告警，只能靠逐模块比对键值发现。
- **改动（消除缺陷类别，而非补一处赋值）**：新增 `llm/module_fingerprint.py` 作为四个 LLM 模块缓存指纹的**唯一事实来源**——`ModuleFingerprintInputs`（冻结 dataclass，承载 11 项输入）+ 四个模块级构建函数 + `MODULE_FINGERPRINT_BUILDERS` 注册表。写侧与预检侧**只允许调用同一构建函数**，任一环节不得再自行拼接指纹片段；辩论增强后缀、决策账本经验后缀、风险信号摘要后缀、结构化表头后缀的判定全部收敛进构建函数内部，因此两侧不可能再对"某个入参/开关是否影响指纹"产生分歧。`generators.py::_build_feature_suffix` 随之删除（职责并入 `debate_feature_cache_suffix()`）。新增模块而非扩展 `fingerprint.py`：后者已被 `prompts_signals.py` 导入，在其中反向组合摘要后缀会形成导入环。
- **`history_data` 取舍**：两侧**一致计入**（而非从预检侧摘除）。它确实影响智囊团复盘提示词内容，计入属"过敏感"方向的保守选择——代价最多是多一次未命中，而漏计则会让提示词内容与缓存键脱钩。**副作用**：专家复盘/健康体检/穿透深挖三个模块的写侧键因此一次性变更，既有缓存不再命中，下次报告对这三个模块各重新生成一次（自动发生，无需人工清理）。
- **架构纪律升格**：该同源要求写入 `technical.md` 架构设计约束表（LLM 集成层），把原先只存在于散文注释里的"读写键同源"变成可评审、可追责的编号约束；`check-doc-traces.py` / `check-code-traces.py` 的约束代号识别范围同步扩展。
- **测试**：新增 `test_module_fingerprint.py` 32 例——注册表键集合与预检键集合一致（防新增模块只注册一半）、四种输入场景下「预检键 == 写侧键」（含 `history_data` 有无/变化、信号摘要开关、辩论增强开关两态，三模块 + 全局政经共 4 模块 × 6 场景参数化）、**风险信号进入写侧指纹**（缺陷直接守卫）、全局政经不受风险信号影响、辩论增强后缀两侧同步、信号摘要后缀只作用于摘要模块。既有 `test_debate_generators.py` 的开关变体用例补齐第二处读点打桩。`test_trace_check_scripts.py` 的约束代号边界用例随识别范围扩展同步（"范围外样例"改用紧邻的下一个新编号，确认新增约束自身被检出、而其后的编号仍不误伤）。
- **文档**：`llm-technical.md`（§13.1 指纹依赖表补齐 `history_data` 组合风险信号摘要项与辩论增强后缀、新增模块表行、"提示词受开关影响时的缓存键纪律"改写为"唯一事实来源"）、`technical.md`（约束表新增条目、结构化表头与信号摘要两处同源表述改为指向构建函数）、`folders.md`（目录树补两个新文件）、`CLAUDE.md`（架构遵从条目的约束条数）。

### LLM 模块缓存指纹提示词内容覆盖（自审 rf-305）（2026-09-10）

- **缺陷（自审 rf-305）**：与上一条「读写不同源」是**反方向的同类缺陷**——那边是两侧键不一致（恒 miss），这边是**两侧一致地漏**（恒命中）。竞争语境块（`_build_competitive_context_block` 渲染的【今日对比】/【区间对比】，来源为 A 股/美股指数、对比指数配置、区间收益与量化指标）与量化指标（`metrics`）**参与提示词构造，却不进入任何模块指纹**。持仓未变而基准指数走出一段行情时，提示词内容已变、缓存键却不变 → 预检命中旧键 → 运行期直接复用按**旧指数**算出的对比结论。两侧同缺故不产生恒 miss，而是**恒命中过期内容**：不报错、不告警，用户看到的是一段与当日行情不符的复盘。
- **量化后再决定纳入**：全体对市场敏感的模块本已按 `total_mv`/`total_profit`/`total_today_profit` 换键，而对比块正是由这些**已被键控的量**派生 ⇒ 纳入后的边际额外失效≈0；真正新增的失效维度恰是本缺陷的目标（指数动而持仓未动、`comparison_indices` 配置变更、指标重算），且 TTL（智囊团复盘 2h / 全球政经 24h）封顶额外成本。与模块自身既定原则一致：**多算只带来无害的过度失效，漏算则导致内容与键脱钩的陈旧缓存**。
- **两条结构性保证（本次的核心，而非补两处赋值）**：
  1. **覆盖以「提示词是否真的含该段」为准**——`competitive_context` / `metrics` 只进提示词确实包含它们的模块（全球政经局势 / 智囊团复盘，以及辩论三键）；持仓体检与穿透深挖的提示词不含这两段，其指纹**刻意不并入**，免去纯成本失效。反向的 `history_data` / 信号后缀沿用同一判据。
  2. **一次渲染、两侧共享同一实例**——`competitive_context` 由 `generate_all_llm()` 渲染**一次**后，同一字符串实例同时交给预检侧（`_compute_module_cache_info`）与写侧（各生成函数）。指纹哈希的是**已渲染文本**而非其输入 dict：这样「提示词内容变 ⇒ 键必变」由构造保证，将来改动渲染函数（增删字段、调整格式）**不可能悄悄让键与提示词脱钩**——这是把纪律降级为结构的唯一可靠办法。`_dispatch_llm_workers` 内原先的第二处渲染随之删除，消除「两份渲染各自漂移」的可能。
- **辩论三键口径收敛**：白脸/黑脸/综合三键此前在 `generate_debate_procon` 内本地自拼 `build_llm_fingerprint`，现收敛为 `module_fingerprint.debate_procon_fingerprint()`（仍在写侧唯一构造点，**不进** `MODULE_FINGERPRINT_BUILDERS`——辩论模式绕过标准预检，其键族 `llm_debate_*` 与标准键不同）。其口径同样以辩论提示词实际包含的段落为准：含基础持仓 + 竞争语境块 + 量化指标 + 辩论增强后缀，**刻意不含** `history_data` / `pipeline_data` 与教训/信号摘要/结构化决策头后缀——辩论提示词没有这些段落，并入只会让三次昂贵调用**每份报告必 miss**。同时去掉三键缓存键字符串里重复拼接的指纹后缀（收敛后由构造器统一承载）。
- **测试**：`test_module_fingerprint.py` 新增覆盖性断言（进提示词必须进键 / 未进提示词的模块不得被并入 / 预检侧随对比块换键而非只改写侧 / 辩论指纹覆盖其提示词段落且不含无关段落 / 辩论增强后缀不丢），场景表扩至 11 组（含对比块、对比块变化、对比块 + 历史、指标、指标变化）；`test_generate_all_llm.py` 新增「一次渲染」用例——用哨兵块断言渲染仅发生一次，并用 `assertIs` 断言预检侧与两个写侧模块**收到的是同一对象**。已验证两处变异转红：摘掉智囊团指纹中的对比块/指标 → 3 例失败；预检侧改传空块 → 实例断言失败。
- **影响**：全球政经局势 / 智囊团复盘（及辩论三键）的既有缓存键一次性变更，下次报告各重新生成一次（自动发生，无需人工清理）。
- **文档**：`llm-technical.md`（§7.1 新增「提示词内容覆盖」小节：覆盖判据、两个结构性保证、辩论三键口径；模块指纹依赖表与附录 C 补对比块/指标列；「唯一事实来源」段补「同函数 + 同输入」两重含义与覆盖判据）。
- **同源登记**：`health_check` 的【数据质量详细状态】段（降级事件渲染）同样「进提示词而未进指纹」，属同一缺陷类别，本次仅登记；其处理见下方 rf-308 条目。

### LLM 模块缓存指纹纳入数据质量详细状态块（自审 rf-308）（2026-09-10）

- **缺陷（自审 rf-308）**：与上一条同属「覆盖不足（欠敏感）」——`health_check` 提示词里的【数据质量详细状态】段（`degradation_events` 经 `_build_data_quality_detail_block()` 渲染成「连接失败: 源(N次)」「数据为空: …」「触发降级: N 次」）**进提示词却不进指纹**。后果比 rf-305 更重：不是复用一段偏旧的行情分析，而是**报告陈述与此刻事实相反的数据健康结论**——源故障期间生成并缓存「连接失败: xxx(3次)」，源恢复后重出报告、持仓未变故键未变 → 预检命中旧键 → 报告仍称该源连接失败，不报错、用户无从察觉。
- **量化后纳入（挂起理由的成本前提不成立）**：该缺陷最初按「纳入后数据源抖动期间事件集持续变化会让该模块反复未命中（TTL 24h 下的重算成本）」挂起，核查显示三条前提均不成立：① 事件集是**本进程内**的降级日志（`DegradationTracker._events` 只存内存、从不落盘，持久化的只有 `_last_success` 时间戳），该块因而是**本次运行的数据源画像**而非「一日累计计数器」；② 该块已是聚合结果（仅失败源与计数，无时间戳/消息/`detail` 字段）；③ 本模块指纹本就含 `total_today_profit`，交易日内持仓一有盈亏变化即换键 ⇒ 24h TTL 从不是真实驻留期。边际额外失效因此接近零；且 `record()` 在取价路径上**无条件**触发，块恒非空，不存在「时有时无」的抖动。
- **与 rf-305 同法（结构保证而非补一处赋值）**：`generate_all_llm()` 把事件集渲染成块**一次**，同一字符串实例同时交给预检侧（`_compute_module_cache_info` → `ModuleFingerprintInputs.data_quality_text`）与写侧（`generate_health_check(data_quality_text=...)` → `_build_health_check_prompt`）；`_dispatch_llm_workers` 不再自行渲染。提示词构建函数**不再接收** `degradation_events` 原始事件（改为接收已渲染文本，传 `None` 时按「无降级事件」渲染，兼容旁路调用）。指纹哈希的是**已渲染文本**，故将来改渲染格式不可能悄悄让键与提示词脱钩。按「只进真的含该段的模块」判据，该块**只进 `health_check` 指纹**——全球政经/智囊团复盘/穿透深挖的提示词不含该段，不并入。
- **测试**：`test_module_fingerprint.py` 新增 3 组覆盖性断言（数据质量块内容变化 ⇒ 体检指纹变化 / 不含该段的三个模块不随其变化 / 预检侧同样换键），场景表扩至 13 组；`test_generate_all_llm.py` 新增 `TestDataQualityBlockRenderedOnce`——哨兵块断言渲染仅发生一次，并以 `assertIs` 断言预检侧与 `health_check` **收到的是同一对象**。已验证两处变异转红：指纹构造里把该块置空 → 2 例失败；写侧改回自行渲染 → 「渲染次数 == 1」断言失败（实测 `2 != 1`）。既有 `test_pipeline_metrics_injection.py` 的数据质量注入用例改为经 `_build_data_quality_detail_block()` 渲染后传入，与生产路径一致。
- **影响**：`health_check` 的既有缓存键一次性变更，下次报告重新生成一次体检章（自动发生，无需人工清理）。
- **文档**：`llm-technical.md`（§7.1 覆盖表新增 `data_quality_text` 行、两个结构性保证与覆盖判据补该段、「已知例外」改写为「数据质量段的成本口径」说明其前提不成立；§13.1 指纹依赖表与附录 C 补该段、「一次渲染」的测试落点补新用例；§6 的 `degradation_events` 暴露段同步改写为「渲染一次、两侧共享」口径）。

### 数据源记录-回放（plan-37，无开关）（2026-09-10）

- **背景**：既有数据源测试全部喂**手工构造的假响应**——那是「我以为上游长什么样」。上游字段改名、值加前后缀、换分隔符、错误页返回 HTML 这类回归在结构上测不出。借鉴 OpenBB 的 pytest-recorder/vcrpy cassette 思路，把**真实响应体**录进仓库、此后离线回放，补上「真实响应体的解析/归一路径」的回归覆盖，同时不破坏「测试不碰真网络」的隔离纪律。分析见 `docs-stm/archive/v0.10.x/openbb-borrowing/openbb-data-provider-analysis.md` §建议C；实现设计见 `docs-stm/archive/v0.10.x/openbb-borrowing/datasource-cassette-replay-design.md`。
- **自研轻量引擎（不引依赖）**：不引 vcrpy / responses / httpretty——本仓库只有 httpx 一种客户端、注入点唯一，自研约 430 行的引擎比适配第三方库的传输层钩子更可控。语义名定为 **`cassette`**（引擎模块名即语义名）。
- **注入点即「HTTP 客户端统一」约束下的唯一构造点**：`core/http_client.py` 新增 `use_transport_factory()` / `make_transport()`——`make_http_client()` 在未显式传 `transport` 时取当前工厂产出的传输，因此全项目 provider **零改动**即被替换为回放源（这是本次唯一的生产代码改动）。工厂每次调用必须返回**新**传输实例：`httpx.Client.close()` 会连带关闭其传输，复用同一实例会让后续请求打到已关闭的传输上。未安装工厂时行为与没有本机制时逐字节相同（既有 `test_http_client.py` 用例锁定）。
- **离线保证与「失败即错」**：回放未命中抛 `CassetteMissError`，**绝不回落真实网络**；该异常**刻意不继承 `httpx.HTTPError`**——provider 的异常处理会捕获 httpx 错误并降级到下一个源，若继承之，「夹具漏录」会被静默改写成「换个源重试」，掩盖真实问题。**录制保证**：需 `--run-live` 与 `--record-cassettes` 双显式开关；非 live 用例的真实请求已被 conftest 的 `_block_external_network` 拦死，**机制上不可能意外产生录制**。
- **存储口径（实测确定，非设计臆断）**：存**解码后的响应体文本 + 字符集**（上游真实响应为 gzip + GBK/GB18030/utf-8 混用），回放时按录制字符集重新编码，并丢弃 `content-encoding`/`content-length`/`transfer-encoding`——否则 httpx 会按已解压内容再解一次（`zlib.error`）或按旧长度截断。请求键归一剥离易变查询参数（`VOLATILE_QUERY_PARAMS`：防缓存参数与 JSONP 惯用名，取值来自本仓库实际用法），只对查询参数生效、不动路径。
- **分层**：`core/cassette.py` 只依赖 stdlib + httpx + `core.http_client`，禁止 import providers/fetcher/report/llm；「cassette 名 → 当前解析器」的绑定表放在 `fetcher/cassette_checks.py`，使 `core/` 不反向依赖 providers。
- **已录 6 份真实响应**（`src/test/data/cassettes/`，git 跟踪，合计约 170 KB）：腾讯行情、新浪行情、腾讯 K 线、东方财富基金净值、天天基金持仓明细、天天基金季度持仓——均为**对真实端点实际录制**所得，非手工编造。
- **维护入口**：新增 `cassettes`（列出已录制响应：来源/录制时间/交互数/大小）与 `cassettes --verify`（逐条离线回放并交给**当前解析器**解析；`[OK]`/`[!]` 未登记解析器/`[ERR]` 解析失败，有失败则退出码 2）两个子命令，与 `doctor` 同例——**无需 config、不受任何实验开关约束、不发起网络请求**。
- **不设功能开关**：cassette 只在测试进程与维护命令中被读写，报告管线不读它，**不产生任何运行时行为分支**——一个不控制任何功能的开关纯属注册负担（理由记入设计文档与 `technical.md` §2.6）。
- **测试**：新增 103 例——`test_cassette.py` 50 例（请求键归一/数据模型/存取/回放传输/录制会话/列出与校验，含「工厂每次返回新传输」「flush 幂等」「无流量不产空文件」「未命中在触碰网络之前失败」「未命中不是 httpx 错误」）、`test_cassette_edge.py` 45 例（畸形 URL、**版本号严格整数校验**（`1.0`/`true` 会被 Python 判为等于 1，只做等值比较会把畸形文件放行）、顶层/交互结构破坏、可选字段回退、重复键后写胜出、多 cassette 回退、非 JSON 文件忽略）、`test_cassette_replay.py` 7 例（对已录制真实响应体做**精确值断言**：价格/市值/市盈率、K 线根数与日期、基金净值与净值日期、持仓条数与前三名）、`test_http_client.py` 新增 9 例（传输工厂的安装/卸载/嵌套/异常恢复/显式 transport 优先/`make_transport` 沿用 SSL 策略）。**变异性验证**：把已录制的价格数字变异后重跑，回放用例转红；把响应体改成 HTML 错误页后 `cassettes --verify` 报 `[ERR]` 并退出码 2——确认断言测的是真实内容而非空跑。
- **文档**：`technical.md`（新增 §2.6 数据源记录-回放 + TOC + 语义命名表三行 + 「HTTP 客户端统一」约束补充「该工厂同时是 cassette 唯一注入点，绕过工厂的请求使回放静默失效」）、`testplan.md`（§4 新增 P1 回归项「数据源真实响应体解析路径」+ §5.2 补「真实响应体回归优先用 cassette 回放」）、`developer-guide.md`（测试模式详解新增「数据源真实响应录制与回放（cassette）」小节：用例写法/录制命令/三处同步清单/离线保证/与「HTTP 客户端统一」约束的关系；CLI 子命令新增 `cassettes` 条目含输出标记与退出码）、`how-to-use-cli-mode.md`（子命令清单补 `cassettes` 并标注为开发维护命令；顺带修正文首「§12 定时任务」的过期交叉引用为 §13）、`folders.md`（目录树补 3 个源码文件 + 4 个测试文件 + `test/data/cassettes/` 6 份夹具）、`README.md`（命令参考补 `cassettes` 指引）、`plan.md`（本条完成态）。
- **自审（rf-307）**：实现期自测 `cassettes --verify` 时发现——损坏的 cassette 已打印 `[ERR]`，进程退出码却是 0；根因是 `cli/__main__.py` 只调 `main()` 而丢弃返回值（只有 `cli.py` 作为脚本直跑时才 `sys.exit(main())`），而 `scripts/cli.sh` / `cli.ps1` / cron / CI **全部经 `python -m src.python.cli` 调用**，故本项目的退出码契约（`doctor` 的 1/2、`cassettes --verify` 的 2、`report`/`cache`/`whatif` 同理）对外一律失效。已抽出 `run_cli()` 供两条入口共用并补 6 例回归测试（详见下方 rf-307 条目）。

### CLI 进程入口退出码传递修复（自审 rf-307）（2026-09-10）

- **缺陷**：`python -m src.python.cli` 的退出码**恒为 0**——`cli/__main__.py` 只调 `main()` 而丢弃其返回值；`cli.py` 自身作为脚本直跑时才有 `sys.exit(main())`（含边界日志与 KeyboardInterrupt/异常处理），两条入口行为不一致。退出码是本项目命令对外契约的一部分，而 `scripts/cli.sh`、`scripts/cli.ps1`、cron、CI 全部经 `python -m src.python.cli` 调用，因此失败对外一律表现为成功：`doctor` 的「部分失败=1 / 严重=2」、`cassettes --verify` 的「解析失败=2」、`report`/`cache`/`whatif` 的非零码**都无法被脚本感知**。在 plan-37 自测中实证：损坏的 cassette 已打印 `[ERR]`，进程仍返回 0。
- **改动**：把入口逻辑抽为 `cli.py::run_cli()`（执行 `main()` → 退出码/`KeyboardInterrupt`/异常 → `SystemExit`，并写应用边界日志），`cli.py` 直跑分支与 `__main__.py` 共用，两条入口行为归一。
- **测试**：新增 6 例——`run_cli` 的返回码传递（含 `_EXIT_SEVERE`）、`KeyboardInterrupt`→130、未处理异常→2、退出时写边界日志，以及**以 `runpy` 把 `__main__.py` 当真实入口执行**并断言进程退出码（`TestModuleEntryPoint`）。已验证还原旧 `__main__.py` 后该用例转红（实测退出码 0 ≠ 7）。另在既有 `TestMainEarlyExitExperiments` 的参数化列表中加入 `cassettes`，锁定「早返回命令同样应用命令行实验开关」。

### 数据源适配契约（plan-36，实验功能 `datasource_adapter` 默认关）（2026-09-10）

- **背景**：借鉴 OpenBB Platform 的 Fetcher 设计识别出的接入形态问题——**本项目的每个数据源都要手拼一份解析后的 dict**，「字段从哪来、缺失时取什么、这个源有没有这个字段」全散在各 provider 的解析代码里；同一个行情域，腾讯源给了市值/市盈率、新浪源没给、东方财富源连键都不产出，下游只能靠 `if key in data` / `.get()` 逐个试探。字段改名（净值源的 `nav` → 统一的 `price`）也靠手写赋值表达。分析见 `docs-stm/archive/v0.10.x/openbb-borrowing/openbb-data-provider-analysis.md` §建议A/B；实现设计见 `docs-stm/archive/v0.10.x/openbb-borrowing/datasource-adapter-contract-design.md`。
- **三段式契约**：接入一个数据源要做的事被拆成三个可独立检验的小函数——`transform_query`（参数转译，默认恒等）/ `extract_data`（抓取，**既有源在此委托既有 provider 函数**，不复制任何 HTTP 与解析逻辑）/ `transform_data`（映射到标准字段）。三者由 `fetcher/source_adapter.py::SourceAdapter` 统一约束，`fetch_raw` / `transform_record` 把两段直接暴露成 Provider Chain 的槽位。
- **标准字段一份 + 声明式归一**：`schemas/datasource_fields.py` 按**数据域**登记标准字段记录（行情域为首个域），字段名与类型注解即缺省语义——`float` 缺失取 `0.0`、`float | None` 取 `None`（表示该源不提供此字段）、`str` 取空串；数值一律经 `core.num_utils.safe_num` 归一，NaN/±inf 不会经此路径进下游。默认映射由三样**数据**驱动：`aliases`（上游字段名 → 标准字段名，字段改名的唯一表达处）、`defaults`（该源的缺省取值）、记录类的类型注解。**输出恒为全部标准字段**，下游不必再为「某源少两个键」写分支。
  - **「未提供」与「不可用」同待遇**：上游缺键、NaN/±inf、不可解析的字符串，都回落到该源声明的 `defaults`（未声明则按类型注解推导）；而**合法的 `0.0` 不会被缺省值覆盖**——这是实现期发现的真语义分界，两种情形分别有测试锁定（同一不可用取值在腾讯源得 `0.0`（声明"不提供按 0 计"）、在新浪源得 `None`（声明"不提供该字段"））。
  - **源身份字段由适配器强制提供**（`source` / `source_api` 不参与上游映射）：东方财富净值回落到天天基金时上游自报 `source: "天天基金"`，若直接透传会让报告显示「来源：天天基金」而实际生效链路是东方财富，破坏「来源 = 实际生效链路」的可信语义。
- **接入链路不新造路径**：`adapter_chain_slots(domain)` 把某域的适配器映射成 Provider Chain 的两个入参（`provider_fn_map` / `transform`），因此链路顺序、缓存键、熔断、降级、过期缓存兜底**全部复用既有 `fetch_with_fallback`**。行情域接入点为 `fetcher/price.py::_price_chain_slots()`：开关关闭时**返回既有手写映射对象本身**（`is` 断言锁定，行为逐字节不变），开启时改用适配器映射。
- **试点范围与等价性（本试点唯一有意差异）**：仅行情域三源（`fetcher/quote_adapters.py`：腾讯/新浪/东方财富），与既有转换函数**逐源等价**——腾讯/新浪逐键逐值相等；东方财富既有转换函数不含 `market_cap`/`pe` 两个键而契约恒为全字段（补 `None`）。已逐个消费方复核：全部用 `.get()` 读取，且无消费方遍历该 dict 的键，「键缺失」与「值为 None」对下游完全同义。差异由 `test_quote_adapter_parity.py` 显式断言（`set(适配器输出) - set(既有输出) == {"market_cap", "pe"}`），防止差异扩大成「悄悄多跑一个源出来」。**存量 provider 不回改**——新数据源/新字段先走契约，既有源维持现状。
- **离线契约自检 + 体检**：`survey_adapters()` 核验域登记齐备、`aliases`/`defaults` 指向真实标准字段、`transform_data` 对合成样本输出**恰好**标准字段集（不多不少），自身不抛异常（异常转为该适配器的失败报告）、不发起任何网络请求。`core/doctor.py` 新增「数据源适配」组（`doctor` 子命令 `--offline` 可用），报告适配器数量/各域/自检结论，并标注契约路径是否已由开关启用——**开关关闭时声明与自检仍照常核验**，这正是接入新数据源前要看的。适配器模块按 `ADAPTER_MODULES` 惰性导入，单个模块导入失败仅告警不拖垮链路与体检。
- **实验开关与三面上屏**：开关名 `datasource_adapter`（默认关）。无需任何渠道层改动——登记进 `features.EXPERIMENTAL_FEATURES` 后，TUI 菜单 `[S]`、Web 配置面板、CLI `--experiment` 三处由注册表自动驱动（`check-semantic-index` / 既有 CLI 用例断言 `--experiment` 取值集合 == 注册表键集合，新增开关即被覆盖）。
- **测试**：新增 40 例——`test_source_adapter.py`（注册表/三段式/声明式归一/自检对坏 alias、缺标准字段、未登记域、自检抛异常四类问题的检出）、`test_source_adapter_edge.py`（非映射响应/空响应/全 None/上游多出未知键/NaN 与非有限值/合法零不被覆盖/别名冲突与键名撞车/缺身份声明，全部 `@edge` 且独立成文件）、`test_quote_adapter_parity.py`（逐源等价 + 链两槽选择（含开关关闭时返回既有映射对象本身）+ 端到端开关开/关结果一致）。另新增 `conftest.py` 的 `_auto_reset_adapter_registry` autouse fixture，适配器注册表在测试间自动还原。
- **自审（rf-306）**：实现期发现 `--experiment` 对 `doctor` / `check-sources` **完全无效**——这三个命令在 `init_config()` 之前就返回（配置损坏时它们仍须可用，属有意设计），而应用命令行实验开关的调用在其后才执行，导致 `--experiment datasource_adapter doctor --offline` 仍报告「开关关闭」，用户据此判断实验功能状态会得到相反答案。已在早返回分支内改为「先读 features.json 覆写、再叠加命令行增量」（与配置初始化的顺序一致，避免被覆写值回冲），并补 4 例回归测试（含「不传开关时保持默认」对照组与「覆写先于命令行」顺序守卫），已验证去掉修复后 3 例转红。
- **文档**：`technical.md`（新增 §2.5 数据源适配契约 + 目录 + 语义命名表三行）、`requirements.md`（新增 §5.7 契约需求 R-ADP-01~08 + 配置开关表行）、`how-to-config.md`（开关总数 33→34、新增开关说明行、实验功能面板段落补一条、配置项对照表补 `[S]` 归属）、`folders.md`（目录树补 3 个源码文件 + 3 个测试文件）、`plan.md`（本条完成态）、`review-findings.md`（rf-306 登记与解决）。


## [0.10.18] - 2026-09-12

### 管理文档与用户文档一致性核对（自审 rf-350）（2026-09-12）

- **背景**：用户要求「核对所有的管理文档和用户文档，查看顺序或内容有需要调整的地方」。对 `docs-stm/managements/`（10 份）、`docs-stm/manuals/`（10 份）与 `README.md` 逐份与代码/文件系统实况比对，确认约 **57 处失配**，修正落在 **14 份文件**，零处代码改动——本批全部是文档追平实现。
- **根因**：历次功能迭代的文档同步只覆盖「本轮改动的落点」，而**计数口径与清单类表述散布在多份文档中**，且没有任何校验环节比对全文。功能开关从 19 增至 20 时只同步了改动点附近的几处，余者（README、要求、计划、配置手册、目录树、测试计划）静默过期；同理，`[D]` 系统自检、`cassettes` 子命令、`scenario_perf`/`scenario_security` 两类测试加入时，清单类文档只在部分位置补齐。
- **失配的六类形态**：① **计数口径过期**——开关 19→20、`[S]` 常规块 15-24→15-25、TUI 菜单项并存 19/17/20 三种写法、`--mode scenario` 子组写 6 而实为 4；② **清单缺项**——`requirements.md` §3.2 菜单表漏 `[D]` 整行、`P` 项只写 4 章节（实为 5 章节 + 6 子模块）、`technical.md` 子命令只写 5（实为 7）、TOC 缺 §4.15–4.18、「影响报告」清单漏 `feeder_penetration`；③ **失效引用**——`report/correlation_sheet.py`、`cache/cache.py`、`src/python/tmpl/report_template.html` 三个路径在仓库中**不存在**，已移除的 `--warm` 仍被描述，`_JS_ASSETS` 与 `_compute_section_visibility` 归属文件写错；④ **事实错误**——README 再平衡阈值三档预设与 `analysis/rebalance.py` 的 profiles **完全错位**、币种敞口章节号沿用改序号前的 §12/§14、faq 的港股通取价口径（声称走腾讯实时价并自动换算汇率，实际 5 位码不在场内行情链路内、实为「暂无行情」）、持仓集中度列数 10（实为 11）、同一文档内组合历史走势区块数「两区块」与「三区块」自相矛盾、LLM 用量模块明细列序与写入层相反、`plan/` 记为「0 份空目录」而实有 2 份；⑤ **快照失配**——`test-coverage.md` 中同一指标在文档内两处并存（edge 862/852、CLI 110/129）且 5 项过期；⑥ **表格结构**——引用块截断字段表致渲染错乱、`review-findings.md` 两个空行把表切成三段且 rf-345 排在 rf-344 之前。
- **处置原则：核不实者一律不改并报备**。`faq.md` 末句「港股通和非 A 股品种的汇率换算由数据源接口自动处理」在代码中找不到支撑（汇率相关模块只做币种分类与占比，无取数或换算），但无法确证应改为哪种口径，**保留待用户确认**；`how-to-use-tui-menu.md`、`how-to-use-cli-mode.md`、`how-to-start.md`、`llm-technical.md` 逐项核对后确认无矛盾，未作改动。
- **计数统一口径**：开关 **20 项**（实验组 9 + 常规组 11）、TUI 菜单 **20 项**、报告章节 **19 项**；`test-coverage.md` 全部计数改以 `scripts/collect-test-coverage.py` 实时收集为准（总收集 **6881**），并消除文档内两处冲突口径。`technical.md` 另对全文的「`X.py`」引用与「`X.py::sym`」符号做了存在性交叉验证——除已修三处外全部命中。
- **测试文档订正**：`developer-guide.md` 的 `--mode scenario` 子组说明由「6 个子组」订正为「4 个子组」（`scenario_extreme`/`scenario_perf`/`scenario_security` 不携带裸 `scenario` 标记），并补 `scenario_perf`（性能基准）与 `scenario_security`（安全基线）两类说明，使「按职责分为 7 大类」名副其实。
- **遗留**：`folders.md` 的行数/文件数总计属发布数据快照，按「发布数据文档刷新」流程在本版发布时统一刷新（本批只改结构性的文件计数：`docs-stm/plan/` 0→2 份、项目文档数 130→132）。

### basic 路径接通「行动建议」（2026-09-12）

- **问题**：多份契约一致声明「行动建议为纯算法，basic/both/full 均可见」（`requirements.md` R-ACT-01、`technical.md` 章节契约、`reports-instruction.md` 页签表与分组说明、`how-to-config.md`、TUI 手册），但 **basic 路径实际拿不到**——`orchestrator.generate_report` 的 basic 分支既未下传 `enable_action`（页签根本不创建），也无 `pipeline_data` 注入（即便创建也只会写「无持仓数据，行动建议无法生成」占位）。
- **判定为「实现漏」而非「文档错」的三条独立证据**：① `core/registry.py` 中 `action` 条目自身的注释写明「纯算法，basic/both/full 均可见」且 `data_flag=None`（无数据可用性判定）；② `git log -S enable_action -- src/python/report/orchestrator.py` **零结果**——从未接线，而非被移除，且 basic 分支**确实**下传了同级的 `is_enable_data_quality` / `is_enable_cost_lots`，属不对称省略；③ 全部文档仅一处异说（`reports-instruction.md` 的「按菜单快速索引」B 行），与其余文档相左。
- **改动（两处接线）**：① `report/orchestrator.py` basic 分支下传 `enable_action=is_enable_action(config)`；② `report/excel_generator.py::generate_excel_report` 在行情明细落成后，若 `enable_action` 开启且 `pipeline_data` 未携带 `action_data`，则由该明细就地构建。both/full 由编排层在历史走势就绪后注入，**已注入时原样透传、不重复构建**，编排层仍是唯一事实来源。
- **降级口径**：basic 不含历史走势，故 `portfolio_peak_mv` 缺省——组合级回撤纪律按「峰值未知」处理（不激活），止盈/止损/再平衡等其余纪律不受影响；无持仓数据时仍写原降级占位。
- **命名订正**：持仓明细 → 行动建议的投影函数原名 `_both_action_holdings_details`（both 专用语义），现由 basic 共用，更名为 `report/_report_helpers.py::_action_holdings_details`，模块内两处引用同步。
- **测试**：`unit/report/test_excel_generator.py` 新增三例——未注入时就地构建且页签拿到可用数据（**回归用例：停用注入逻辑即失败，已实测红-绿**）、已注入时原样透传且不重复构建、开关关闭时既不建页签也不构建；`unit/report/test_orchestrator.py` 的 basic 精确 kwargs 断言补 `enable_action=True`，作为「开关必须显式下传」的接线守卫。
- **文档同步**：`reports-instruction.md`（「按菜单快速索引」中行动建议由 B 行移至 E 行——E 已含该页签，B 为「E 全部 + 其余」，原写法会把 E 的页签漏报）；`technical.md`（补 `action_data` 三路径组装口径；附录 H 台账来源列补 basic 就地构建）。

### 报告章节默认顺序对齐仓库配置（§6.3 口径统一）（2026-09-12）

- **问题**：「行动建议」的默认序号在文档中并存两种说法——`requirements.md` §6.3、`how-to-config.md` 章节排序表、`reports-instruction.md` 页签表已按 10 写，而 `technical.md` 两处契约行与 `reports-instruction.md` 的旁注仍写「注册表默认顺序为行动建议=17」。根因不是笔误，而是**同时存在两份顺序**：注册表出厂默认（`action`=17）与仓库 `config.json` 的 `report_section_order`（`action`=10）。两份顺序并存，任一处改动都会让另一处悄悄过期。
- **处置（用户决策：改注册表默认值）**：`core/registry.py::_REPORT_SECTION_DEFAULT` 的 `action` 条目由第 17 位前移至第 10 位（紧随 `style_factor`），其后 `news_correlation` / `global_macro` / `expert_review` / `health_check` / `penetration_deep` / `portfolio_history_drawdown` / `portfolio_evolution` 依次顺延为 11…17，`data_source_status`=18、`llm_usage`=19 不变。出厂默认与仓库现值由此**同序**，清空 `report_section_order` 与保留它效果相同，双源分叉消除。
- **影响面**：仅改变**出厂默认**（配置为 `{}` 的用户与全新 clone）；本仓库已显式配置同一顺序，报告产物**逐字节不变**。
- **测试**：`unit/core/test_registry.py` 两处序号断言随之前移（`portfolio_evolution` 16→17、`action` 17→10，并订正 `action` 用例的 docstring）。另订正 `unit/report/test_excel_report_structure.py` 表头注释——该表原自称「与 registry.py 对齐」，实为 `create_sheets` 的**输入数据**、序号只在本表内自洽（且刻意省略 `action`/`portfolio_evolution`），照原注释会在下次改注册表时被误当作镜像同步；现改为如实说明并指向 `test_registry.py`。
- **文档同步**：`how-to-config.md`（章节排序表 `action` 移至第 10 行、其余顺延；「本仓库配置」旁注由「仅差异在行动建议提前至第 10 位」改为「与默认顺序完全一致」）；`reports-instruction.md`（页签序号旁注同步为「与注册表默认顺序完全一致」）；`technical.md`（§4 章节契约 `action` 条 `number=17`→`10`；「报告序号可配置」约束行 `portfolio_evolution` `number=16`→`17`，两处旁注一并改写）；`data/config/config.json`（`report_section_order` 上方注释原写「清空为 {} 即恢复注册表默认顺序（行动建议=17）」，该前提已不成立，改为说明两者同序）。

### 执行效率约定入库 CLAUDE.md（2026-09-12）

- **背景**：用户反馈某一轮「文档同步 + 门禁 + 提交」耗时 27 分钟，要求定位。核查该轮 transcript 后确认瓶颈不在工具——门禁（含两次 `dev-verify`，各约 24s）在 140 次 Bash 调用中合计仅约 2.4 分钟，时间主要花在 243 次「生成 → 调用 → 观察」往返上。故可压缩项是**往返次数**，而非任何单个慢工具。
- **改动**：`CLAUDE.md` 的「Conventions」新增「**执行效率（合并往返）**」一条——需要读多份文件时一次并行读完；同类修改合并（一次多行替换或脚本批量应用），不做逐条 Edit；门禁分层跑，便宜检查（`.venv/bin/ruff`、四个 `--ci` 脚本）随改随跑，`dev-verify` 等完整门禁仅在收尾跑一次（与既有「调试失败用例流程」一致，不在小修小改后重复整套重跑）。
- **落点选择**：该约定入 `CLAUDE.md` 而非 Claude 的 memory——memory 位于本机 `~/.claude/projects/<项目>/memory/`，**随机器不随仓库**，换台机器即失效；`CLAUDE.md` 入库，clone 即带。跨项目生效则需改全局规则源仓库（`~/.claude/rules/ecc/`），不在本次范围。
- **取舍：正文只留定性理由，不落单次实测数值**。初稿曾把「工具执行占 18% / 243 次往返」作为依据写入正文，复核时判定不妥并移除——该数据出自**一轮**测量（n=1），负载构成一变即失配；且 `CLAUDE.md` 是长期指令，数字写进去即开始过期，而换台机器上的读者无法复核。定论「单轮墙钟由往返次数主导」本身可独立成立，无需实测背书。历史数据留在本日志即可。

### QDII 联接基金底层暴露修复（plan-40）（2026-09-11）

- **问题（用户报障）**：运行程序时 QDII 类基金拿不到最新报告，无法准确分析穿透资产。定位为两个叠加的根因——**根因 A**：ETF 联接基金的资产就是目标 ETF、**本身不持有股票**，东财季报接口对其每个近期季度都返回空内容（实测 `016055` 博时纳斯达克100ETF发起式联接四个近季度均为 59/50 字节空响应），于是取数落到「无年份兜底」分支，拿到的是**最早可得**的报告（`2023-09-30`），经报告层时效闸门判定陈旧后记为「持仓不可用」——用户看到的即是「拿不到最新报告」；**根因 B**：主页面 HTML 路径不产出任何报告期（原按字节窗口盲扫日期实测 10 只基金 0 命中，且可能误抓导航/日历控件里的「当天」，比空值更危险），报告期缺失时时效闸门**不判陈旧**，无报告期的结果会静默放行。
- **批次① 取数阶梯次序修正（缺陷修复，不加开关，默认路径生效）**：`providers/tiantian_holdings.py::fetch_fund_holdings` 由「主页面优先」改为三跳阶梯——**第 1 跳**季报接口（**年份域**，最近 4 个完整季度回溯）取当期持仓 + **真实报告期**（唯一携带报告期的通道）；**第 2 跳**基金主页面取前十大（报告期**不从此处取**，`_extract_fund_name` 只返回名称）；**第 3 跳**季报接口无年份兜底（最早可得报告，通常已陈旧）。**次序本身即陈年数据隔离**——兜底被压到第 3 跳，不再与年份域并列，故无法遮蔽当期数据。**取数层不做时效判定**：判据唯一归属 `report/holdings_freshness.py` 的 `is_stale_report` / `STALE_QUARTERS`，复制到取数层即「判据复制」（项目已有同型教训：缓存指纹的读写两侧各拼一份），两者日后必然漂移；第 3 跳的陈年报告照常上送，由报告层闸门裁决并标注「报告期 X，距今 N 个完整季度」。
- **批次② 联接基金穿透（新开关 `feeder_penetration`，常规组，默认开）**：`providers/tiantian_holdings.py::parse_feeder_target_etf` 从联接基金主页面解析**目标 ETF** 代码（动态解析、**不维护「联接基金 → 目标 ETF」映射表**——基金公司更换标的 ETF 时映射表会静默失效，锚点随页面同步更新），`fetcher/fund.py::with_feeder_penetration` 以目标 ETF 的持仓与报告期代理该基金的底层暴露，结果中记 `feeder_penetration = {target_code, target_name}` 供报告层登记来源。两个设计要点：① **幂等**——该后处理在**单条取数与批量两处接缝**都调用，因为批量路径的 `execute_with_cache_check` 缓存命中时会跳过任务，穿透若只在网络路径做则**热缓存下静默失效**（此为本条最隐蔽的坑：默认 7 天缓存内第二次运行就复现不了）；② **结构深度恒为 1**——只有名称含「联接」的基金才产出 `feeder_target_code`，而 ETF 名称不含「联接」，故目标基金永不产出新的目标，无需运行时深度计数。判定复用既有 `core/code_utils.py::is_index_link_by_name`（不新增第二份「是否联接」关键词表，避免同义关键词表并行漂移）。
- **锚点识别的两重区分（实测修正）**：落地前实测发现两类页面的「相关」链接**互为反向**——联接基金页标签止于「ETF」、指向**场内**目标 ETF（`016055` → `513390`）；常规 ETF 页标签为「查看相关ETF**联接**」、指向该 ETF 的**场外**联接基金（`561910` 电池ETF招商 → `016019`）。且 `查看相关ETF` 是 `查看相关ETF联接` 的**前缀**，只用子串匹配会一并命中反向链接、把常规 ETF 的底层暴露错认成其联接基金的持仓。故做两重**独立**区分：① 标签须止于「ETF」（负向先行断言 `(?!联)`）；② 目标须为场内代码（`is_exchange_fund_code`，前缀 5/1）。实测 `561910` 的锚点两重各自都能挡下。
- **归因口径（100%，不折算）**：联接基金约 95% 投向目标 ETF，未折算会**轻微高估**底层权重。折算需解析联接基金自身的「基金投资明细」，而 `jjcc` 是股票表、`zqcc` 是债券表，基金持仓不在其中、当前无对应取数通道。故阶段一按 100% 归因并在报告中**显式标注**「穿透自目标 ETF `XXXXXX`（未折算持有比例）」——把该已知偏差公开，读者才不会把穿透结果当作精确值。
- **cassette 改录**：`fund_holdings` 的请求次序变更使原录制（`110022` 的主页面路径）在回放中 `CassetteMissError`；改录**联接基金** `016055`——普通基金的年份域季报通常直接命中（第 1 跳）、不会请求主页面，录下来与 `fund_quarterly_holdings` 重复；只有联接基金才会走完阶梯并落到「主页面 → 目标 ETF 锚点」这一步。新录制 9 次交互（4 季度 × `jjcc`/`zqcc` 空响应 + 主页面约 100 KB）。**维护提示**：`year`/`month` 不在 `VOLATILE_QUERY_PARAMS` 中，故 cassette 与「今天属于哪个季度」绑定，跨季度后需重录。
- **缓存时效（用户须知）**：`fund_hold_*` 缓存 TTL 为 7 天，改动前生成的条目（无 `feeder_target_code`、主页面路径的旧结果）**在过期前不会体现本次修复**。处置：不清前缀、不升 TTL——旧条目是「现状」而非「损坏数据」，且 `fund_hold_` 前缀被 5 个模块引用（含用户可见的 `--clear-cache`），升前缀会孤立旧条目、放大改动面。需立即见效时执行 `--clear-cache` 或等待过期。
- **测试**：新增 `unit/providers/test_tiantian_holdings_edge.py`（15 例）与 `unit/fetcher/test_fund_edge.py`（8 例）两个边缘文件；`test_tiantian.py` 增补 `TestExtractFundName`（2）/ `TestParseFeederTargetEtf`（7，含反向链接拒绝）/ `TestFetchFundHoldingsLadder`（7，含次序不变量）；`test_fund.py` 增补 `TestWithFeederPenetration`（8）与批量接缝缓存命中回归 1 例；`test_cassette_replay.py` 的 `fund_holdings` 回放改为断言联接基金解析；`test_penetration.py` / `test_penetration_sheet.py` 增补穿透来源登记与标注 3 例；`test_config_edit.py` 两处开关全集断言补 `feeder_penetration`。
- **文档同步**：`technical.md`（§4.9 补「基金持仓取数阶梯」表 + 联接基金穿透段、§6.7 语义命名表 5 行、features.json 矩阵行、Web 白名单计数 19→20）；`requirements.md`（§6.4.4 补取数阶梯与 R-PEN-01、§11.5 开关计数 19/9/10→20/9/11 + 开关表行）；`how-to-config.md`（开关表新增 `feeder_penetration` 行、`[S]` 面板编号 15-24→15-25、Web 白名单行）；`how-to-use-tui-menu.md`（常规块编号与 25 号开关行、开关总数 19→20）；`how-to-use-web-mode.md`（常规开关行）；`folders.md`（两处新测试文件）；`plan.md`（plan-40 完成态 + `plan-next` 40→41）。

### 文档一致性核对（注册表统一后的口径补齐）（2026-09-11）

- **背景**：注册表统一（本版上一条）落地后，功能开关的口径从「实验项／非实验项」变为「实验组／常规组两块」，Web 配置面板的可编辑面由一个「实验性功能」组变为「功能开关」组再拆成两块渲染。管理文档与用户文档中若干沿旧口径书写的处所未被上一轮同步覆盖，本次逐一核对补正。
- **组数口径统一（Web 配置面板）**：面板的分组数此前在文档中并存「7 组」与「8 组」两种写法，实为两个不同层次的计数——白名单/surface 是 **7 组**（路径/章节/子模块/匿名化/对比指数池/LLM 开关/功能开关），前端把第 7 组渲染成「实验性功能」「常规开关」**两块**，故界面共 **8 块**。修订：`technical.md` 路由表由「返回 8 组」改「返回 7 组 + 顶层 `features` 面」并注明前端分块；前端渲染段落由「按 7 组分块渲染」改「按 8 块渲染」；白名单全集段由「全集 8 组：…（仅列 7 项）」改「全集 7 组（前端分两块渲染，故界面共 8 块）：…」。用户侧一律用界面口径 **8 组**：`how-to-config.md` §P 由「共 7 组」改「共 8 组」（该表本就列 8 行，计数与正文自相矛盾）、`how-to-use-web-mode.md` §1 由「7 组」改「8 组」（§4 已是 8 组）、`testplan.md` 回归清单改为「配置面板 8 块可编辑项（白名单 7 组，功能开关组分两块）」。
- **需求条目补正**：`requirements.md` R-WEB-08 的覆盖清单原为「…/LLM 开关/辩论实验」——「辩论实验」是注册表统一前的旧提法，改为「…/LLM 开关/功能开关——后者界面上分「实验性功能」与「常规开关」两块」。
- **CLI 新参数补入入口处**：`README.md` 全局参数说明原只提 `--experiment`，补 `--feature NAME=VALUE`（全域、双向、仅本次运行、在其之后应用故可覆盖其隐式置开、同样作用于早返回命令）；手册索引行同步。
- **目录树描述对齐实现**：`folders.md` 中 `features.py` 描述由「Feature Flag 注册中心（开关集中管理…）」改为「功能开关注册表（唯一登记点：19 项声明的显示名/说明/分组/默认值/产物影响；默认值字典为其派生投影）」；`test_features.py` / `test_features_edge.py` 描述同步为注册表不变量与开关解析覆盖（原描述只提「实验功能名解析」）。
- **测试覆盖描述补入新增覆盖**：`test-coverage.md` 中 `unit_config` 行补「功能开关注册表统一（五字段齐备 / 分组覆盖全集不重不漏 / 默认值遵循分组 / 默认值字典为派生投影 / `--experiment` 取值域仍为实验组 / `--feature` 全域双向解析与归并）」、`unit_cli` 行改「功能开关命令行通道（`--experiment` 实验组简写 + `--feature NAME=VALUE` 全域双向…）」、`unit_web` 行补「功能开关白名单键集恒等于注册表键集 + `features` 面 + 常规开关经面板关闭后落盘生效」、功能域表配置管理行同步。
- **计数快照刷新**：跑 `scripts/collect-test-coverage.py` + `test-runner.py --mode bench --update-docs` 回填——配置管理 337→**365**、核心基础设施 1154→**1156**、CLI 命令行 110→**129**、Web 服务 216→**219**、`unit` 子组合计 6463→**6515**、`folders.md` 测试用例 6,776→**6,828**；模式对应测试量与两张环境耗时对照表由 bench 自动回填（dragonball 采集日期 2026-09-10→2026-09-11），随之失配的散文数字（`unit` ~13s→~15s、`all` ~22s→~24s）与日期同步。**其余行数/文件数快照仍在发布版本时按「发布数据文档刷新」统一刷新**。
- **示例文件名纠错**：`developer-guide.md` 新增测试指南的示例表原引 `test_cache_core.py`（该文件不存在，实际为 `test_cache_io.py`），已改正——依示例操作者此前会找不到落点。
- **核对方式**：`EXPERIMENTAL_FEATURES` 在活跃文档中的残留、开关计数（19/9/10）、TUI 菜单编号（6-14 / 15-24）、`--experiment` 提法的补集覆盖、文档引用的测试类与测试文件名是否真实存在（逐项反查 `src/test/`，无失效引用）逐项扫描后修正。

### 功能开关注册表统一与三渠道可控（plan-39 批次②）（2026-09-11）

- **问题**：功能开关注册表把三件互不相干的事拧在一个容器里——决定**面板可见性**、决定**默认关**、决定**是否进产物自述**。于是「转正」（默认值改 `True` 并移出实验注册表）会**连带摘掉可见性**：系统自检转正后，TUI 菜单 `[S]`、Web 配置面板、CLI 三处入口一并消失，关闭途径只剩手改 `features.json`；反方向同样成立——7 项量化指标与交互图表从来不在任何界面通道内，用户想关掉某项指标只能手写 JSON。用户看到的是 19 项同质开关，其中一半能在界面改、一半不能，而「能不能改」取决于它是否被标为实验项，两者本无逻辑关系。
- **单条声明为唯一登记点**（`config/features.py`）：新增冻结 dataclass `FeatureSwitchDef`（显示名 / 说明 / **分组** / 默认值 / **产物影响**五字段）与 `feature_switch_registry`（19 项，声明顺序即面板顺序）；`_FEATURE_FLAGS_DEFAULT` 由逐项手写降为**派生投影**（`{flag: d.default}`），`EXPERIMENTAL_FEATURES` 容器退场——实验清单改由 `switches_in_group(GROUP_EXPERIMENTAL)` 表达。**「面板可见性」由此与「是否实验项」解耦**：可见性由分组属性决定，取值由 `default` 决定，转正只剩「改分组 + 改默认值」两个字段，面板入口自动延续。
- **两个分组按生命周期划分**：`GROUP_EXPERIMENTAL`（⚗ 实验性功能（默认关闭），9 项）＝改变产物、待真实数据验证；`GROUP_STANDARD`（常规开关（默认开启），10 项）＝常驻能力、默认开而用户可关。分组是**当前状态**而非优先级或新旧。
- **TUI 菜单 `[S]`**（`tui/handlers_config.py`）：面板改三块——标准 LLM 模块（1-5）→ 实验块（6-14）→ 常规块（15-24）。**常规块一律追加在实验块之后**，故既有编号锚点（6/9/10）不位移（由既有用例守住），新增两条用例锁定 15＝`metrics_sharpe`、23＝`doctor_check`；行首 ⚗ 标记只给实验组（常规组靠分组标题区分）；列宽取注册表全部显示名与标准模块名的最大值，仍走 `pad_right` 矩形对齐；两块走同一落盘路径（`set_feature_enabled` + `save_feature_overrides`）。
- **Web 配置面板**（`web/config_edit.py` + `src/static/web/main.js`）：白名单实验组改为对**全注册表**推导（键集等于注册表键集，由用例断言）；surface 新增顶层 `features` 面——`{experimental, standard, labels, report_affecting}`，标签由服务端同源下发，前端不再持有任何开关字典（原 `experiments` / `experiment_labels` 键移除）。常规块中**关闭会改变报告产物内容**的项（量化指标、交互图表）标签带「（影响报告）」后缀，与只影响入口显隐的项（系统自检、数据源适配契约）相区分——这条差异正是用户改动前需要知道的。
- **CLI 新增全局 `--feature NAME=VALUE`**（`cli/cli.py`）：**全域、双向、可重复、仅本次运行、不写盘**；`VALUE` 取 `on/off/true/false/1/0`（大小写不敏感），取值经 argparse `type` 回调即时校验——形态不合法、未知开关名、不可识别取值均即报错并列出可选值（可选值来自 `describe_switches()`）。同名后者覆盖前者（`resolve_switch_values` 归并去重）。**与 `--experiment` 的关系**：后者保留为实验组简写（只开、支持 `all`），`--feature` 在其**之后**应用，故 `--experiment all --feature module_quality_gate=off` 表示「其余实验功能全开、只关质量分级」。早返回命令（`doctor` / `check-sources` / `view-logs` / `cassettes`）经 `_prepare_early_exit_switches(groups, pairs)` 同样生效（先加载 `features.json` 覆写、再叠加命令行增量）。
- **架构约束同步修订**（`technical.md` 架构设计约束表「功能开关注册表唯一事实来源」条）：条文由「实验功能开关注册表唯一事实来源」改为「**功能开关注册表唯一事实来源**」——枚举/显示名/说明/**分组**/默认值/产物影响一律来自 `feature_switch_registry`，适用范围由「实验开关」扩到「全部可切换开关」；渠道层不得另写清单的禁令不变而覆盖面扩大。违反后果补记本次实测的失效形态：可见性若与「是否实验项」绑定，转正即失去界面入口。
- **文档同步**：`technical.md`（「功能开关注册表唯一事实来源」条文、§6.7 语义命名表新增 `feature_switch_registry` / `switches_in_group` / `is_experimental_switch` / `parse_switch_override` / `resolve_switch_values` / `describe_switches` 六行、CLI 全局参数、`main()` 流程、Web 路由与白名单 7 组→8 组、TUI 菜单表、features.json 矩阵行与消费模式）；`developer-guide.md`（检查清单改为「分组归属」两栏 + 五字段声明，两条转正判据的步骤改为「改分组+改默认值」，并补列常规组也可三面切换）；`requirements.md`（§11.5 注册表口径与分组、R-DIAG-05/07 与 `doctor_check` 表行改为常规组表述）；`how-to-config.md` §M（三入口改述、开关表按实验组/常规组拆两表且顺序对齐注册表、`[S]` 面板三块布局）；`how-to-use-tui-menu.md`（`[S]` 章节改「三块 + 常规块 15-24 对照表」、`[D]` 两处改为「可在 `[S]` 常规块切换」）；`how-to-use-cli-mode.md`（`--feature` 参数行 + 用法示例 + 与 `--experiment` 的关系）；`how-to-use-web-mode.md`（7 组→8 组、新增「常规开关」行、「影响报告」标记说明、自检卡片改述）；`how-to-start.md`（7 组→8 组）；`how-to-config-llm.md`（面板两组→三块、`--feature`）；`faq.md`（`[D]` 恢复方式改为「在常规块切回」）。
- **回归测试**（覆盖项 +30 余，净增文件 6 处）：
  - `unit/config/test_features.py`：新增 `TestFeatureSwitchRegistryInvariants`（默认值是派生投影、顺序即声明顺序、每条声明五字段齐备、分组划分覆盖全集不重不漏、**分组默认值遵循生命周期**——实验组全 `False` / 常规组全 `True`、`GROUP_LABELS` 覆盖 `GROUP_ORDER`）与 `TestSwitchOverrideParsing`（`on`/`off`、取值大小写不敏感、`1/0/yes/no`、空白容忍、未知名列出可选值、缺 `=`、取值不可识别、**19 项开关名全部可解析**、同名后者覆盖、`None`/空列表→空、`describe_switches` 覆盖全注册表）。
  - `unit/config/test_features_edge.py`：`TestParseSwitchOverrideEdge`（空取值、`=on` 无开关名、空串、多余 `=` 保留为取值一部分、开关名大小写敏感）。
  - `unit/cli/test_cli.py`：`TestArgparseFeatureOverrides`（默认 `None`、常规开关可关、实验开关可开、可重复、未知名 `SystemExit(2)`、取值非法 `SystemExit(2)`）与 `TestApplyCliSwitches`（应用、不写盘、`--feature` 覆盖 `--experiment` 的隐式置开、早返回命令 `doctor` / `cassettes` 同样生效）。
  - `unit/cli/test_cli_edge.py`：空取值、缺 `=`、开关名大写被拒、重复对幂等、`None`/空列表无副作用。
  - `unit/handlers/test_handlers_config.py`：常规块编号锚点两条（15→`metrics_sharpe`、23→`doctor_check`）。
  - `unit/web/test_config_edit.py`：白名单键集等于注册表键集、surface 新 `features` 键（取值/标签/产物影响三部分）、常规开关写入落 `features.json` 生效、`doctor_check` 可从面板关闭。

### 数据源适配契约转正为默认开启（plan-39 批次①）（2026-09-11）

- **转正理由**：它是**内部接缝而非用户功能**——开关开/关下报告产物逐源等价（唯一差异是东财源多出 `market_cap`/`pe` 两个 `None` 键，下游一律 `.get()` 读取、取值语义不变，由 `test_quote_adapter_parity.py` 端到端锁定），用户打开它没有任何可感知收益，摆在面板上只会让人误以为「开了有好处」；而默认关的实际代价是**生产路径从不执行适配器分支**——适配器只在测试里被显式打开，接入新数据源/新字段时契约能否真的跑通没有实跑证据。
- **改动**：`config/features.py` —— 从 `EXPERIMENTAL_FEATURES` 移出（不再上实验面板、不再进产物自述），`_FEATURE_FLAGS_DEFAULT` 保留同名键并改默认 `True`。**开关保留为回退杠杆**：`features.json` 置 `false` 即回退既有手写转换函数（行为逐字节不变，`_price_chain_slots()` 返回既有映射对象本身）。消费点口径复核：`fetcher/price.py::_price_chain_slots()` 的判定逻辑不变（仅默认值变）、`core/doctor.py` 的「数据源适配」组措辞由「实验开关…关闭」改为「开关…已关闭」、`report/excel_generator.py` 兜底清单的示例开关名换为非 LLM 实验项。
- **取舍需知**：该开关自此不在 TUI 菜单 `[S]`、Web 配置面板与 CLI `--experiment` 的可选集内（三者由实验注册表驱动），关闭入口改经 `features.json`——此缺口由 plan-39 批次②（功能开关注册表统一）补上：注册表合并后常规开关将获得与实验开关同等的三渠道入口（TUI 面板「常规开关」块 / Web 配置面板同组 / CLI `--feature NAME=VALUE` 双向）。
- **文档同步**：`requirements.md`（§5.7 标题、R-ADP-06/08、features.json 表行默认值与说明）；`technical.md`（目录 §2.5 标题、§2.5 接入方式段落、功能语义命名表 `source_adapter`/`quote_adapters`/`adapter_chain_slots` 三行开关口径由「实验开关（默认关）」改为「开关（默认开，非实验项）」）；`developer-guide.md`（转正判据增「内部接缝类开关也应转正」一段，`datasource_adapter` 为该模式首例）；`folders.md`（`quote_adapters.py` 说明）；`how-to-config.md` §M 开关表默认值 `false`→`true` 与实验面板说明、`how-to-use-tui-menu.md`（实验面板编号 6~15→6~14 与对照表）、`how-to-use-web-mode.md`、`how-to-config-llm.md`。
- **回归测试**（覆盖项 +5）：新增 `unit/config/test_features.py::TestDatasourceAdapterPromotion`——默认开启、不在实验注册表、置 `false` 仍生效（回退杠杆）、**默认配置下链路即走适配器分支**（`_price_chain_slots()` 返回的不是既有映射对象，此条即「转正的实际效果」，默认值若改回关闭立即失败）、开启状态下不进产物自述。既有用例口径同步：`unit_web::test_config_edit.py` 的白名单全集与实验面板载荷中移除该键，`unit_cli::test_cli.py` 中原以该开关为实验开关样本的早返回用例改用 `module_quality_gate`。

### 产物自述假阳性开关与系统自检转正（自审 rf-345）（2026-09-11）

- **问题一：报告自述出现假阳性开关**。`enabled_experimental_features()` 遍历整个 `EXPERIMENTAL_FEATURES` 注册表，凡启用即列入 HTML 页脚与 Excel 清单——而系统自检（`doctor_check`）只门控 TUI 菜单 `[D]` 与 Web 卡片两个入口的可见性，**不改报告任何字节**。一个只影响入口显隐的开关出现在「本报告在哪些实验功能下生成」的清单里，读者会推断内容受其影响。引入该自述时（rf-342）注册表里尚无「只影响入口」类成员，故当时口径无懈可击——缺陷随注册表成员变化而出现。
- **问题二：归类口径与「新不新」绑定**。系统自检沿用「新增能力默认关」的发布惯例被归为实验项默认关，而它是只读诊断（不改产物、不写文件、联网检查每次由调用方显式确认，本地检查毫秒级返回）。默认关的实际代价是让**环境出故障的那批用户恰好看不到它**，而开启对默认输出零代价。
- **自述准入口径显式化**（`config/features.py`）：注册表条目类型由 `(显示名, 说明)` 二元组扩为 `(显示名, 说明, 是否改变报告产物)` 三元组，`enabled_experimental_features()` 按第三位过滤——**新增实验项时必须书面回答「能否改变报告产物」**，答否者不进自述。这是准入判据的可执行形态：当前注册表十项均可能改变产物内容，故无 `False` 成员，该字段的作用是拦住下一个「只影响入口」的实验项（由一个合成项的单元用例守住）。三处解包点同步（`_match_experiment` / `describe_experiment_flags` / TUI 面板与 Web 面板清单生成）与 `core/doctor.py` 的解包。
- **系统自检转正为默认开启**：移出 `EXPERIMENTAL_FEATURES`（不再上实验面板、不再进产物自述），`_FEATURE_FLAGS_DEFAULT` 保留同名键并改默认 `True`。**门控保留**——转正不等于不可关，TUI `FEATURE_GATED_ITEMS` 与 Web `system_info["doctor_enabled"]` 照旧读取该开关，`features.json` 置 `false` 仍隐藏两个入口；CLI `doctor` 子命令本就先于 `init_config` 分派、始终不受开关约束。**取舍需知**：该开关自此不在 TUI 菜单 `[S]`、Web 配置面板与 CLI `--experiment` 的可选集内（这三者由实验注册表驱动），关闭入口改经 `features.json`。
- **失效资产清理**：随转正移除 Web 卡片标题的 `⚗ 实验性` 标签与其 CSS 规则 `.tag-experiment`（已无任何使用者），`core/doctor.py` 的报告首行由「实验功能（doctor_check）：只读诊断」改为「只读诊断，不改动任何文件，结论仅供参考」。
- **文档同步**：`requirements.md`（§3.6 标题、R-DIAG-05/06 措辞、新增 R-DIAG-07、features.json 表行默认值与说明）；`technical.md`（分层表 / TUI 菜单 / Web 路由 / §4.17 拆分口径与 §4.17.3 三面上屏表 / 实验面板计数 11→10 / features.json 注册表条目三元组）；`developer-guide.md`（新增实验开关检查清单增列「回答产物影响」一步、更正注册表条目结构、新增「实验性」准入与转正判据、`doctor` 子命令不再称「不受实验开关约束」）；`folders.md`（`doctor.py` 说明 + 统计快照）；`test-coverage.md`（模式/功能域/分组/跨类计数）；`how-to-config.md` §M 开关表默认值 `false`→`true` 与实验面板说明、`how-to-config-llm.md`、`how-to-use-tui-menu.md`（实验面板编号 6~16→6~15 + `[D]` 章节）、`how-to-use-web-mode.md`、`how-to-use-cli-mode.md`（移除 `--experiment doctor_check` 示例）、`faq.md`（「找不到 `[D]`」改为「默认出现，被显式置 false 才消失」）。
- **回归测试**（覆盖项 +8）：`unit_config` 新增 `TestReportAffectingClassification`（3 条：每项须显式声明、只影响入口的合成项不进自述、系统自检开启时自述仍为空）与 `TestDoctorCheckPromotion`（3 条：默认开启、不在实验注册表、置 false 仍生效）；`unit_ui::test_tui_menu.py::test_doctor_item_visible_under_defaults`（1 条：不 patch 取值，直接断言默认配置下 `[D]` 在菜单里）与 `unit_web::test_handlers.py::test_card_present_under_defaults`（1 条：默认配置下卡片即渲染且不再带实验性标签）——原有门控用例均以 `patch` 覆盖取值，测不出默认值本身（默认值若改回关闭它们仍全绿，而用户打开的菜单里会少一项）。`unit_core::test_doctor.py` 与 `unit_cli::test_cli.py` 中原以 `doctor_check` 为实验开关样本的用例改用 `signal_ledger`，`unit_web::test_config_edit.py` 中该键自白名单与实验面板载荷中移除。

### Excel 实验功能清单兜底落点（自审 rf-343）（2026-09-11）

- **问题**：实验功能清单在 Excel 侧只落在「LLM API 用量」页签上，而该页签只在 LLM 章节开启时生成。LLM 分析整章关闭时，Excel 产物上不出现清单，而 `signal_ledger`（确定性信号沉淀）/ `datasource_adapter`（数据源适配契约）/ `decision_reflection`（决策跨期反思闭环，结算与确定性登记部分）等**非 LLM 实验开关**此刻仍可能开启——这批开关不依赖 LLM 章节，在 Excel 产物上遂完全无痕。HTML 页脚不受影响（页脚始终存在，清单照常上屏）。
- **兜底落点**（`report/excel_generator.py`）：汇总页签（`1.投资分析汇总`，始终生成）页脚写入同一清单与复核提示。**触发条件不止「页签不存在」**——核查中发现用量数据的取数链路上有多个早退点（无会话用量、无模块明细、页签缺失），任一命中都会得到一个存在但为空的用量页签，清单同样无痕，故判据取「用量页签缺席**或为空**」。已落在用量页签时不重复写：同一事实说两遍，读者会以为有两处不同来源。
- **措辞单源**（新增 `report/experimental_notice.py`）：清单语句与复核提示收敛为 `enabled_notice_line()` / `NOTICE_HINT`，HTML 页脚、Excel 用量页签、Excel 汇总页脚三处共用同一函数取数，各落点只负责自身排版（字体、空行、合并列宽）。此前 HTML 侧在模板里拼句、Excel 侧在写入函数里拼句，两处措辞各写各的必然漂移。
- **文档同步**：`how-to-config.md` §M 的「报告会自述生成条件」提示补明 LLM 章节关闭时清单改落汇总页脚，故 Excel 产物上无论 LLM 章节开关与否都能看到清单；「实验开关全关时两处均不出现」随之改为「各处均不出现」。
- **回归测试**（覆盖项 +12）：`unit/report/test_excel_report_structure.py::TestExcelSummaryFallbackNotice`（5 条：页签缺席时落汇总页脚、页签为空时仍落、页签已载清单时不重复、开关全关时一字不提、无汇总页签时静默跳过）；`unit/report/test_excel_generator.py::test_summary_fallback_notice_wired`（1 条：生成流程确已调用兜底写入——漏调则该落点在真实产物上永不出现）；`unit/report/test_html_report_structure.py::test_wording_matches_excel_landing`（1 条：HTML 页脚句式与 Excel 落点逐字一致，防两份措辞漂移）；`scenario/basic/test_scenario_basic_flows.py::test_experimental_notice_lands_without_llm_chapter`（1 条：真实产出 xlsx 后重新打开断言——LLM 章节关闭时无用量页签、清单恰落在汇总页脚一处）。

### 候选比较两列恒空（自审 rf-344）（2026-09-11）

- **问题**：候选基金比较子表的**「风格」与「与持仓重合度」两列在取数成功时恒为空**。`fetch_fund_holdings_cached()` 返回 `{"name", "holdings", "date"}` 字典，而 `fund_candidate.py` 把它**整体**当作持仓列表传给下游——`classify_fund_style` 与 `compute_overlap_matrix` 都期望 `[{name, code, ratio}, ...]`，在字典上迭代得到键名字符串，随即抛 `AttributeError`；两处各被自身的 `try/except Exception` 吞成 `logger.debug`，于是两列恒显示 `--`。既有基金持仓基准侧同样传的是字典，两侧口径全错。既有单测全部 `mock` 掉 `compute_overlap_matrix`，真实入参形状从未被校验过，缺陷因此长期潜伏（本轮回溯报告期时效时撞见）。
- **修复**：取 `fh["holdings"]` 后再传下游，候选持仓与既有基金持仓基准两侧口径统一为持仓列表；既有基金侧同时按报告期时效剔除陈旧者（其持仓与候选的「与持仓重合」计算同样按市值/比例口径失真）。
- **回归测试**：`unit/report/test_fund_candidate.py::TestCandidateRowRealShapes` **不 mock 计算引擎**——喂真实形状的字典入参，断言风格列被填出、重合度按 Jaccard 精确取值（去掉修复即失败）。另有 `TestCollectExistingFundBaseline` 守住基准收集的返回形状。

### 其余持仓消费者的报告期时效处置（自审 rf-341）（2026-09-11）

- **问题**：穿透表已上屏报告期并对陈旧快照设闸门（rf-339），但其余持仓消费者仍只取 `["holdings"]`，同样会把数年前的快照按现行持仓呈现——`fund_concentration.py`（持仓集中度）、`excel_fund_deep_analysis.py` / `html_renderers.py`（基金深度分析）、`position_overlap.py`（重合度矩阵）、`fund_candidate.py`（候选比较）。集中度模块还会拿它与上一次快照算环比，得出与当期配置无关的「变化」。
- **分层口径**（按模块语义，而非一刀切）：**重合度矩阵**按市值加权，陈旧权重失真最重，故剔除陈旧基金并在 Excel 与 HTML 两侧标注剔除清单（读者若发现某只基金缺席矩阵而无说明，只会以为矩阵算错了）；**集中度 / 风格 / 候选比较**以比例与分类为主，保留并标注报告期。
- **统一标注**（`report/holdings_freshness.py::fund_period_label()`）：`{名称}（报告期 {期次}，已过 {N} 个完整季度）`。同一只基金在各章节若各写各的报告期文字，读者会以为是不同口径下的两件事。报告期判定经 `evaluate_report_period()` 一次取回展示文本与陈旧结论，显示与闸门不会各算各的漂移。
- **集中度环比语义修正**（`fund_concentration.py` + `fund_concentration_sheet.py`）：快照增记 `period`。报告期与上期相同时，本次与上期读的是同一份报告，环比恒为 0——报 0 会被读成「持仓结构没变化」，实为「没有新数据可比」，故改标「无对比意义」并注明原因，快照条目**原样沿用**（含 `check_date`），不刷新成一次新观察。旧快照无 `period` 字段时维持原对比行为，不制造行为悬崖。页签新增「报告期」列（陈旧者带「（陈旧）」后缀）。
- **风格与候选比较**：风格分析的报告期并入 `remark`（分析层统一生成，Excel 与 HTML 同源），候选比较标注风格与重合度所依据的报告期、并注明陈旧基准未计入重合度分母。原 `style_factor_sheet._style_remark()` 与其余两处标注实现重复，一并删除。
- **产物留痕**：陈旧基金被剔除或保留之处，均同时落 WARNING 日志与产物内标注。共用脚注字体收敛为 `report/styles.py::NOTE_FONT`（原计划在三个文件各加一份）。
- **回归测试**（覆盖项 +37）：`unit/report/test_fund_concentration.py::TestReportPeriodSemantics`（7 条：同报告期不报环比、报告期推进照常对比、旧快照维持原行为、陈旧标记透出、快照记录报告期、未推进条目原样沿用、推进条目刷新）与新增 `test_fund_concentration_sheet.py`（6 条：报告期列、陈旧后缀、「无对比意义」与「报告期未推进」标识、推进时照常呈现环比、首检不受影响）；`test_excel_fund_deep_analysis.py` +3、新增 `test_html_fund_deep_renderers.py`（9 条，HTML 侧同口径）、`test_correlation_sheet.py` +2（矩阵剔除留痕）、`test_fund_style.py` +3（备注含报告期与陈旧标记）、`test_fund_candidate.py`（真实入参形状 + 基准收集时序）；`test_html_report_structure.py::TestHtmlReportPeriodAnnotations`（8 条：HTML 产物须与 Excel 同口径——剔除横幅、报告期列、「无对比意义」、候选比较报告期注记，且无陈旧项时零噪声）。

### 报告自述生成条件：实验功能清单上屏（自审 rf-342）（2026-09-11）

- **问题**：**实验性功能的开启状态在报告产物上不可见**。11 项实验开关（`features.json` 持久化 / CLI `--experiment` 仅当次进程）会改变报告内容——辩论三项改变 expert_review 形态、决策跨期反思闭环新增行动章「历史决策复盘」区块、模块级质量分级追加内容质量横幅，而信号预消化 / 决策头结构化 / 确定性信号沉淀只改内部路径、在产物上完全不留痕——但报告本身不说明自己是在哪些非默认开关下生成的。唯一的全局提示是 `log_experimental_features()` 打印的日志横幅，而它只活在控制台：报告一旦导出流转（HTML 外发、Excel 存档），读者既看不到 `features.json` 也看不到生成时的控制台，无从判断「历史决策复盘」区块是常驻功能还是本机实验开关的产物，也无从判断某处内容质量提示究竟是内容问题还是开关所致。现有痕迹还零散不成体系——辩论三项共用同一个「🧪 实验模式」标签（看不出是哪一种）、质量横幅不标来源开关。缺的正是可复现性的前提：**产物须自述其生成条件**。
- **统一取数口**（`config/features.py`）：新增 `enabled_experimental_features()`，按注册表顺序返回已启用项的 `(开关名, 显示名)`；`log_experimental_features()` 一并改走该函数，控制台横幅与报告标注自此同源，注册表仍是唯一清单来源。
- **HTML 页脚**：紧邻既有「🧪 辩论模式已启用」行新增一行 `⚗ 本报告在 N 项实验性功能开启下生成：<显示名顿号相连>` 及一行「实验功能输出质量可能不稳定，结论请自行复核」。上下文变量由 `html_writer._render_template` 注入，只列显示名——说明文字属配置期信息，报告读者需要的是「这不是默认配置下的产物」这一事实。
- **Excel 用量页签**：顶部说明行之后写入同一清单（两行：清单 + 一致性提示）。位置选在会话用量汇总区**之前**，故不受 `_write_llm_summary_section` 的「无用量即早退」影响——清单与用量无关，无用量时同样须出现。
- **零开关不出行**：两处均判空，实验开关全关时报告一字不变，既有输出与既有测试不受影响。
- **回归测试**（覆盖项 +11）：`unit_config` +4（`TestEnabledExperimentalFeatures`：默认全空、显示名取自注册表而非另写一份、多项启用按注册表顺序而非启用先后、默认开启的非实验开关不入列）；`unit_report` +7（`test_excel_report_structure.py::TestExcelExperimentalNotice` 三条：零开关页签不提实验功能、启用项按显示名逐项列出并给出总项数、无会话用量时该行仍在；`test_html_report_structure.py::TestFooterExperimentalNotice` 四条：页脚按显示名顿号相连列出、零开关不出现、上下文未注入时不出现空壳行、渲染上下文确已注入该变量）。
- **未覆盖范围**：Excel 侧清单挂在「LLM API 用量」页签上，而该页签仅在 `include_llm` 为真时生成——LLM 分析整章关闭时，Excel 产物上仍不出现清单，而 `signal_ledger` / `datasource_adapter` 等非 LLM 实验开关此刻仍可能开启（HTML 页脚不受影响）。该缺口随后由「Excel 实验功能清单兜底落点（自审 rf-343）」补上，措辞一并收敛为单源（`report/experimental_notice.py`）。

### 基金持仓报告期上屏与陈旧闸门（自审 rf-339）（2026-09-11）

- **问题**：基金持仓的**报告期取回后无人校验、无人上屏**。`fetch_fund_holdings` / `fetch_quarterly_holdings` 返回的 `date`（报告期）在全仓没有任何消费者——`penetration.py`、`position_overlap.py`、`fund_concentration.py`、`excel_fund_deep_analysis.py`、`html_renderers.py` 一律只取 `["holdings"]`，只有 provider 内部两行日志读过它。而 `fetch_quarterly_holdings` 在最近 4 个完整季度均无数据时会回退到**不带年份的默认请求**（该分支本意是「部分基金仅有早期报告」），返回的报告期可能是数年前——用户在实际运行日志中看到 040046（华安纳斯达克100ETF联接(QDII)A）取回的持仓报告期为 **2022-12-08**。这份四年前的快照随后被 `penetration.py` 与当期报告期的持仓**同权合并**进穿透 TOP10（持仓比例直接乘以该基金**当前**市值分摊），报告读者无从分辨某一格权重来自四年前的仓位。
- **新增时效判定模块**（`report/holdings_freshness.py`）：口径为「报告期之后已走完的完整季度数」，阈值为 **2 个完整季度**。季度序号用整数相减计算（无逐季度遍历，跨年跨十年无需特判），当天恰为季末时当季计为走完。阈值取 2 的理由：定期报告本身有披露滞后（法定不晚于报告期结束后 15 个工作日，QDII 因境外市场休市与结算更晚），取 1 会把正常披露节奏内的持仓误判为陈旧，取 4（约一年）又放过了与当期配置明显脱节的快照。报告期缺失或无法解析时**不判陈旧**——那属于数据缺失，仍走既有的获取失败路径，混在一起会掩盖真正的失败原因。
- **穿透层闸门**：判定陈旧的基金按既有「持仓不可用」路径处理——全值计入未穿透（`unknown_mv`）并**不折进 TOP10**，同时以 WARNING 记录基金、报告期与已过季度数。`_merge_fund_layer` 的返回值从 4 元组改为 `_FundLayerMerge` 数据类（合并结果 + 获取失败 / 报告期陈旧 / 实际采用报告期三类明细），避免继续堆叠位置返回值。
- **报告期上屏**：`summary` 增补 `stale_funds` / `stale_fund_details` / `report_periods`。Excel 穿透页签与 HTML 报告同步输出——剔除原因由「无法获取」细分为「N 只无法获取穿透数据」「M 只因持仓报告期陈旧被剔除」，并逐只列出被剔除基金的报告期与距今季度数；正文下方另起一行列出**各基金持仓报告期**，使穿透权重的时点可被核对。
- **测试夹具时效化**：多处测试夹具把持仓报告期写死为绝对日期（`"2026-03-31"` 等）。此类字面量会随时间推移跨过阈值而使测试失败——新增 `src/test/helpers.py::recent_holdings_period()` 按当天返回最近一个完整季末，替换穿透相关测试夹具中的写死日期（7 个文件），消除这一时间炸弹。
- **回归测试**（覆盖项 +29）：新增 `unit/report/test_holdings_freshness.py`（20 条：四种报告期写法与非法值、季度数在季末/当季/未来日期/跨年边界的取值、阈值边界恰好等于阈值即判陈旧、缺失报告期不判陈旧、展示文本规范化）；`unit/report/test_penetration.py::TestStaleHoldingsReportPeriod`（4 条：实测场景 2022-12-08 的基金被剔除出 `merged`、新鲜报告期正常并入并登记报告期、缺失报告期不设闸门、`summary` 三字段端到端贯通）；`unit/report/test_penetration_sheet.py`（5 条：备注中的剔除原因与明细、报告期行、仅获取失败时措辞不变）。去掉闸门后前两组中的两条定点用例立即失败，确认其对缺陷场景有效。
- **未覆盖范围**：`fund_concentration.py`（集中度）、基金深度分析章节、重合度矩阵、候选基金比较仍只取 `["holdings"]`，同样会把陈旧快照按现行持仓呈现。该缺口随后由「其余持仓消费者的报告期时效处置（自审 rf-341）」按模块语义分层补齐（重合度剔除、其余保留并标注报告期），过程中另撞见候选比较两列恒空（自审 rf-344）。

### TUI 配置面板盒线边框按显示宽度对齐（自审 rf-340）（2026-09-11）

- **问题**：五个配置面板（LLM 分析章节 / 对比指数池 / 报告可选章节 / 报告增强子模块 / 持仓匿名化）的盒线行以 `len()`（码点数）手写空格补白——中文/全角字符在等宽终端占 2 列却只算 1，故含中文的行比含英文的行短；同一面板的上下边框、分隔线与内容行又各写各的补白数（`' ' * 22` / `' ' * 27` / `{name:<14s}` 对 `'─' * 42`），口径互不相同。实测单个面板的盒线行出现 **7 种行宽**（47~67 列），右边框参差不齐；中文名一长即撑破边框（报告可选章节面板的运行示意图行 65 列，边框仅 44 列）。
- **新增排版助手**（`tui/text_layout.py`）：`display_width()` 按东亚宽度（`east_asian_width` 的 W/F 计 2 列）计算显示列数，先剥离 ANSI 颜色序列（着色开启时 `len()` 会把 `\033[92m` 等转义字符也算作可见字符，非 TTY 下这些常量为空串、问题被掩盖）；`pad_right()` 按显示宽度补齐表格列；`render_panel()` 接收标题与内容行列表（`None` 表示分隔线），按「标题所需」与「最长内容行」的较大者统一定宽，**四边对齐由构造保证**——调用方不必预估列宽，也不会因某行超宽而撑破右边框。
- **面板改建**：上述五个面板全部改走 `render_panel()`，名称列宽取自各自清单内最长显示名（超宽名不截断，仅该行右移），状态方括号因此纵向对齐；原散落的空格魔法数与硬编码边框长度字面量全部移除。
- **回归测试**（覆盖项 +21）：新增 `unit/ui/test_text_layout.py`（16 条：中英混排宽度、ANSI 剥离、组合字符、按显示宽度补白、一个面板内所有行等宽、超宽行不截断、分隔线/空白行/无内容行）与 `unit/handlers/test_handlers_config.py::TestConfigPanelsAreRectangular`（5 条：逐个面板驱动渲染，断言捕获到的盒线行显示宽度全等）。后者对改建前的实现实测**五条全数失败**（单面板 7 种行宽），确认其对缺陷场景有效。
- **同形态待办**：报告层 `report/progress.py` 的模块耗时排行面板同属此形态（含条目行按码点补白），因该面板另带中缀分隔线与条形图，与本次的 TUI 面板不同构，另行处理。

### 功能开关注册表收敛：移除声明即死的陈旧开关（自审 rf-338）（2026-09-11）

- **问题**：实验功能三通道（TUI / Web / CLI）核查时顺带发现，`features.json` 宣传的 35 项功能开关中有 **16 项声明即死**——全仓无任何代码读取其取值，用户照 `how-to-config.md` §M 配置后不产生任何效果：5 项 `llm_*`（`llm_global_macro` / `_expert_review` / `_health_check` / `_penetration_deep` / `_news_correlation`，模块启停实际由 `llm_settings.json` 的 `enabled_llm` 同键控制）、5 项 `news_*`（实际由 `config.json` 的 `news_sources` 控制）、`history_portfolio` / `history_benchmark`（实际由 `enable_history` 单键控制）、`fund_deep_analysis_fund_manager` / `_fund_concentration`（实际由 `enable_fund_deep_analysis` 控制）、`anonymizer`（实际由 `config.json` 的 `anonymization.mode` 控制）；`cache_daily_cleanup` 声称的「启动时自动清理过期缓存」与既有的启动敏感缓存清理（`cache/__init__.py`，无条件、90 天）无关，取值同样无人读。`git log -S` 逐项证实这 16 项从未被任何提交消费过（唯一的 `llm_global_macro` 命中是 `features.py` 模块文档串示例）。
- **处置——移除而非接线**：这些能力已各自归属 `config.json` / `llm_settings.json`，且在 TUI 菜单 S（标准模块区、匿名化 A、板层开关）与 Web 配置面板上均有对应项，接线会造出第二份同义清单（违反「开关注册表唯一事实来源」的单源纪律），故按能力归属移除开关，无能力损失。
- **注册表加注纪律**（`config/features.py`）：`_FEATURE_FLAGS_DEFAULT` 现为 **19 项**，就地写明「只登记有消费者的开关」并逐条指路各能力现归属文件，防止同义开关再被搬回；模块文档串与 `load_feature_overrides` 文档串中已失效的示例开关（`llm_global_macro` / `news_cls` / `anonymizer`）改用现存开关。
- **无消费者键不再静默**：`load_feature_overrides()` 对 `features.json` 中出现的无消费者键，由逐键 `debug` 改为**合并为一条 WARNING** 列出键名——这类配置不驱动任何行为，静默忽略会让用户以为已生效，而逐键打印会在每次启动刷屏（该文件在模块导入时即加载）。
- **文档同步**（三处口径由 35 项收敛至 19 项）：`how-to-config.md` §M（删 16 行开关表、JSON 示例改用现存开关、新增「本表只收录有消费者的开关」提示并指明各能力归属文件）、`how-to-use-tui-menu.md`（菜单说明改为 19 项 + 新增「不在 features.json 的开关」归属说明）、`requirements.md` §11.5、`technical.md` 配置矩阵行（补「只登记有消费者的开关」与无消费者键告警行为）。
- **回归测试**（`test/unit/config/test_features.py`，`unit_config` +5）：新增 `TestRegistryLiveness` 三条——默认值表中每个开关名都必须在注册表之外的 `src/python` 源码里被引用（按字符串字面量判定，覆盖元组/映射间接传入，杜绝再次「声明即死」）、已移除的 16 项不得回归、实验注册表各项都须在默认值表登记；新增 `TestUnknownOverrideWarning` 两条——无消费者键合并为一条 WARNING 且逐键列名、已登记开关不误报且覆写照常生效。全量计数 6651 → **6656**（unit 6339 → 6344、standard 5420 → 5425、verify 4320 → 4325、all 6651 → 6656；report 1753 不变）。
- **数据文档同步**：`test-coverage.md`（模式表 + 功能域「配置管理」行 + `unit_config` 子标记 + 单元组合计）、`folders.md` 项目统计表按本轮变更后的行数口径刷新。

### ruff lint 基线收敛（全仓零告警）（2026-09-11）

- **基线声明**（`pyproject.toml`）：`[tool.ruff.lint]` 显式声明 `select`（等价 ruff 默认集），不再依赖会随版本升级静默漂移的隐式默认；`extend-exclude` 增加 `docs-stm`——归档目录内的历史脚本副本自此冻结，不参与 lint / format；新增 `per-file-ignores` 记录两类**刻意豁免**（各附就地说明）：可执行入口先注入项目根到 `sys.path` 再导入项目模块、子模块 re-export 块置于模块级代码之后，二者重排都会破坏原有加载顺序（E402）；函数内延迟导入 + 引号注解规避循环依赖造成的未定义名静态误报（F821）。
- **E402 走「改代码」而非「加豁免」**：28 个测试文件把 `pytestmark` 放在第三方导入与项目导入之间触发 E402。`pytestmark` 是模块级变量、pytest 在模块导入完成后读取，位置不影响语义，故统一移至全部导入之后——测试树因此保留 E402 全量保护，无需按目录豁免；仅 5 个入口/脚本文件按上述刻意豁免登记。
- **自动修复**（`ruff check --fix`）：216 项——未使用导入、无占位符 f-string、单行多导入、重复定义。未使用局部变量逐项核对后清理：`test-runner` 的 `elapsed` / `timed_out` 与 `test_market_hours` 的 `actual_weekday` 属彻底死码，连同其数据来源一并移除，不留无副作用空表达式。
- **手工收敛**：歧义变量名 `l`（E741 ×3）、`lambda` 赋值改 `def`（E731 ×2，保留默认参数绑定语义）、单行多语句（E701）、`type()` 比较改 `is`（E721）；`calibrate-dedup-threshold.py` 中 f-string 内的正则转义序列（反斜杠 d）改 raw f-string，消除 `SyntaxWarning`，输出不变。
- **格式化**（`ruff format`）：176 个文件；归档目录 `docs-stm/` 保持冻结，不随本次改动。
- **顺带发现的测试完整性缺陷**（`review-findings.md` rf-337）：`test_market_value` 的 `TestIsQdii` 内两条用例同名 `test_empty_string`，后者覆盖前者，致其中一条**从未执行**——重命名后用例恢复执行，全量计数 6650 → **6651**；`test_config_atomic` 的 `_config_cache = None` 只是本地重绑定、未清模块级缓存，改用 `_clear_config_cache()`；`_report_generation` 重复导入的 `build_action_data` 与 `test_generate_all_llm` 无使用的模块级 generators 导入块按死码移除。
- **数据文档同步**：`test-coverage.md`（unit 6339 / standard 5420 / report 1753 / all 6651，其余不变）、`folders.md` 项目统计表按 ruff format 后的行数口径刷新（主程序 66,195 / 脚本 7,165 / 测试代码 102,162 / 源代码合计 77,501；项目文档 49,993 / managements 10,396；测试用例 6,651）。

### 测试覆盖统计刷新 + 中间计划文档归档（2026-09-11）

- **测试覆盖统计刷新**（`test-coverage.md`）：模式覆盖项数与开发机实测耗时经 `--mode bench --update-docs` 回填（unit 6338 / standard 5419 / dev-verify 2494 / verify 4320 / edge 852 / report 1752 / all 6650），功能域、单元分组、跨类三张子表按 `collect-test-coverage.py` 实时结果手更（单元组合计 6338、跨类 `llm` 753、`edge` 852），并补本轮新增的覆盖语义——提示词承载段与辩论综合键进指纹、文件写入原子原语、Provider 凭据分离校验、估值字段网关、管线数据契约键台账校验。上一节的「留待发布刷新」项至此完成。
- **中间计划文档归档**（`docs-stm/plan/` → `docs-stm/archive/v0.10.x/`）：外部借鉴系列的 14 份文档（三个外部仓库的评估分析 + plan-30~plan-38 实现设计 + 缓存指纹提示词覆盖设计）随其迭代完成整体迁出 `docs-stm/plan/`，该目录回到空目录（等待新立项的中间计划）。
  - 归档目录按**借鉴来源**划分，与各文档头部「来源」行一致：`tradingagents-borrowing/`（决策跨期反思闭环 + LLM 输入/输出质量治理三层 + 实验开关上屏，6 份）、`augur-borrowing/`（决策结算纪律 + 确定性信号账本 + 健壮性三件套，3 份）、`openbb-borrowing/`（数据源适配契约 + 记录-回放测试 + 凭据就绪指引，4 份）、`llm-fingerprint-prompt-coverage/`（自审发现的缓存指纹提示词覆盖缺口，1 份）。
  - 各文档头部状态行由「未立项实施 / 设计定稿待实施 / 实现中」更新为已实现态；文档间交叉引用按新相对路径改写。
  - 引用同步：`plan.md`（P4 表的「实现设计见」与借用探索候选段的「分析文档见」改指归档路径）、`changelog.md` 本版本各条目、三个 core 模块文档字符串（`core/decision_ledger.py`、`core/signal_ledger.py`、`core/cassette.py` 的设计约束指路）。
  - `technical.md` 正文两处设计文档指路改为按名称引用（面向读者文档正文不得指向归档内容）；`archived_plan.0.10.x.md` 补四目录索引与五次归档说明；`folders.md` 目录树与项目统计同步。

### 管理文档与用户文档同步（架构约束判据回填 + 台账刷新）（2026-09-10）

- **架构设计约束表判据回填**（`technical.md` §架构设计约束，5 行）：本次自审暴露的共性是「规则只有口号、没有可操作判据」，逐条补判据与适用范围：
  - 代码类型判定中心化 —— 适用范围覆盖「按代码前缀分类资产类型」与「判定代码是否合法」两类判定，点名 `config/`、`report/` 同在范围内（本次违规正落在这两处）。
  - Provider Chain 必经 —— 适用范围补「report/ 与 analysis/ 层取估值/行业等外部数据必须经 fetcher 网关入口（`fetcher/industry.py::fetch_valuation_fields`），不得 import `providers.*` 直连」。
  - 报告序号与显示名不可硬编码 —— 规则拆为两张注册表各自点名（章节顺序/可见性取 `_REPORT_SECTION_DEFAULT`，页签显示名取 `_REPORT_SHEET_NAMES`，页签名一律经 `get_report_sheet_name()` 取用）；违反后果补「配置里一个名、页签上另一个名」的漂移形态；适用范围补 `fund_style_classify.py` 等写入层。
  - LLM 模块注册 —— 补「注册项必须有真实调用方」「模块配置项与显示名同样由中央注册表提供，不在别处建副本」；违反后果补「无人调用的注册分支误导后续维护者按『已被编排』推断调度与并发行为」与「统计口径把未编排项计入」。
  - LLM 模块缓存指纹唯一事实来源 —— 补覆盖判据「提示词正文里出现哪一段，对应入参就必须进指纹」，并说明辩论三键仅写侧使用、不进 `MODULE_FINGERPRINT_BUILDERS`，但构造同样由该模块提供、综合键须覆盖白脸/黑脸两段完整正文。
- **自我审查台账**（`review-findings.md`）：新增「已解决待归档（v0.10.18）」表登记 rf-322 ~ rf-335（一行一问题，处置详情指向本文件对应条目），编号源 `rf-next` 由 322 更新为 336。
- **需求文档**（`requirements.md`）：`llm_providers.json` 的 Provider 条目字段表与 R-LLM-07 按凭据分离的现行实现校正——`credentials_ref` 为凭据唯一合法来源（必填，缺失/空白即跳过该条目）、`api_key` 禁止出现在该文件（非空即拒并给出迁移指引）、`model`/`endpoint` 为非敏感路由字段可按条目覆盖凭据块同名值。原表把内联 `api_key` 记为与 `credentials_ref` 二选一的合法形态，与实现不符。
- **测试计划**（`testplan.md`）：「原子写入恢复」回归行补 `core/test_atomic_write.py` 的原语级用例清单（新建/覆盖/父目录创建/临时文件不残留/失败返回 False 且不抛并保留原内容/Windows 占用回退 rename）。
- **开发者指南**（`developer-guide.md`）：「新增 LLM 模块检查清单」第 ④ 步现为「注册调度入口」并指名 `llm/generators_orchestrator.py` + `llm/module_fingerprint.py`，明确指纹不进 orchestrator、预检侧与写侧只允许调用同一构建函数；指纹说明段拆成两条——「提示词内容必须进指纹（唯一事实来源 `llm/module_fingerprint.py`，含竞争格局/数据质量文本/指标/`pipeline_data` 派生两段，且只进提示词实际含该段的模块）」与「实验开关改变提示词 → 同一后缀函数供两侧调用」。
- **目录结构**（`folders.md`）：补 `src/test/unit/core/test_atomic_write.py` 行（原子写入原语用例），使目录树与仓库文件一致。
- **留待发布刷新**：`test-coverage.md` 的模式/子标记计数是发布前由 `--mode bench --update-docs` 与 `collect-test-coverage.py` 回填的数据快照，本次未手改，避免与自动回填的模式表口径不一致（发布门禁统一刷新）。

### 指纹补齐提示词承载段与综合键全文口径（自审 rf-331）（2026-09-10）

- **缺陷（自审 rf-331）**：指纹覆盖纪律要求「一次渲染、两侧共享；进了提示词的必须进指纹」。核查发现两处**键与提示词内容脱钩**，且都不报错、只表现为静默的陈旧结论：
  - **提示词承载段缺席指纹**：`pipeline_data` 派生的【环比变化】（`_build_difpipeline_data_block`）与【数据质量降级】（`_build_data_degradation_block`）两段**直接进入** `expert_review` / `health_check` / 辩论白脸红脸的提示词正文，却完全不参与指纹——持仓未动而数据源故障或恢复（降级事件集变化）、当日两份报告的环比基数不同（`diff` 内容变化）时键不变，预检命中旧键，报告继续陈述「某数据源不可用」或复用按旧环比算出的结论。
  - **辩论综合键的摘要口径**：综合步的 `fingerprint_fn` 只把白脸/黑脸正文**前 200 字符**的 sha256 摘要拼进键（`f"{_fingerprint}_{_pro_digest}_{_con_digest}"`）——正文差异落在 200 字符之后时键不动；且键里只有开关位字母后缀，提示词中的条件推理**情景名/描述**与集中度问答**阈值**均来自 `config`，仅改配置而不动开关时键同样不动。两种情况都命中按旧正文/旧配置生成的综合结论。
- **改动**：
  - `module_fingerprint.py` 新增 `_pipeline_block_cache_suffix(pipeline_data)`——与既有的 `_signal_digest_cache_suffix` 同法，调用**提示词侧同一构建器**取文本再哈希，故「进键的文本」与「进提示词的文本」由同一段代码产出、不靠纪律对齐；两段皆空时返回 `""`（键与未注入时一致，不误伤既有缓存）。`expert_review_fingerprint` / `health_check_fingerprint` / `debate_procon_fingerprint` 三个构造器各拼接该后缀（辩论白脸红脸复用 `_build_expert_review_prompt`，两段随其进入提示词）。
  - 新增 `debate_synthesis_fingerprint(inputs, synthesis_prompt)` = `compute_fingerprint(debate_procon_fingerprint(inputs), synthesis_prompt)`：综合提示词本就是白脸/黑脸全文 + 情景段 + 集中度段的函数，键直接取该渲染结果，无需逐项枚举入哈希来源、也就不会漏项。
  - `generators.py` 的 `generate_debate_procon` 改为构造**一次** `_fp_inputs` 供三段复用（并把 `pipeline_data` 注入该输入闭包），综合键改用新构造器；删除 `hashlib` 依赖与前 200 字符摘要拼接。
- **行为变更**：键形态变化，升级后首份报告的三处相关缓存（`expert_review` / `health_check` / 辩论三键）为一次性未命中重算，其后恢复正常命中。正常路径的报告内容无变化；变化只发生在「此前会命中陈旧结论」的场景。
- **测试**：`test_module_fingerprint.py` 新增 7 例——`test_degradation_block_is_in_prompt_for_covered_modules`（前提校验：该块确实进了提示词，否则下述用例无的放矢）、`test_degradation_block_enters_fingerprint` / `test_diff_block_enters_fingerprint`（两模块参数化：事件集或环比内容变化必须换键，且与「无 pipeline_data」的基线不同）、`test_pipeline_blocks_ignored_without_block_in_prompt`（`global_macro` / `penetration_deep` 提示词不含该两段，指纹不得随之变化——反向防纯成本失效）、`test_pipeline_block_enters_precheck_key_not_only_write_side`（预检侧同样换键且与写侧逐字符同源）、`test_debate_fingerprint_covers_pipeline_blocks_in_its_prompt`、`test_debate_synthesis_fingerprint_covers_full_procon_text`（用例前提显式断言两段正文前 200 字符完全相同）、`test_debate_synthesis_fingerprint_covers_config_driven_prompt_text`（仅改情景描述、开关位不变也必须换键）；`test_debate_generators.py` 新增 `test_synthesis_fingerprint_covers_full_procon_text`——走**生产路径**（`generate_debate_procon` 三段 mock 后取第三段的 `fingerprint_fn`）而非直接调用指纹函数。共 10 例已用 `git stash` 还原旧实现验证转红。

### pipeline_data 键台账回归三方一致（自审 rf-328）（2026-09-10）

- **缺陷（自审 rf-328）**：数据契约登记纪律要求 pipeline_data 的键必须先在附录 H（`technical.md` 的 Schema 台账）登记类型与写入/消费模块后才能使用。实际存在**三方漂移**——代码 `_PIPELINE_DATA_KNOWN_KEYS`、类型断言表 `_PIPELINE_DATA_TYPE_MAP`、附录 H 台账各说各话：
  - `diff`（环比对比差异，9 键）**在两个代码清单里长期存在且被汇总 Excel δ 列、行动章环比上下文、LLM 环比提示词三处消费，却从未登记进附录 H**——台账漏登在用键，该纪律的「先登记后使用」对它是空文；且因无台账可对照，其 9 键结构在文档里无处可查。
  - `decision_review_data`（决策复盘区块）**反向漏登**：`report/_experimental_seams.py::record_llm_decisions_and_review_block` 往 pipeline_data 里写它，行动章（HTML 模板 + `action_sheet.py`）读它，但代码两份清单与附录 H **三处都没有**——写路径每次命中「包含未知键」告警，类型断言表也无从校验。
  - `portfolio_daily_returns`（组合日收益率）是**死键**：登记在代码两份清单里，但全仓无任何消费者（`history_data.daily_returns_portfolio` 由 `_full_risk_metrics` 直接读取，无需再投射为顶层键），且同样不在附录 H。
  - 附带：`pipeline_data_builder.py` 模块 docstring 与 `_validate_keys` 的告警文案都把登记处指向 `data-channels-schema.md`——该文件**只存在于 `docs-stm/archive/v0.7.x/`**，照着提示去登记的开发者找不到文件。
- **改动**：`portfolio_daily_returns` 从 `_PIPELINE_DATA_KNOWN_KEYS`、`_PIPELINE_DATA_TYPE_MAP` 及写入侧 `_full_risk_metrics` 的注入语句中删除（死键清理，`history_data` 的消费路径不变）；`decision_review_data`（`dict | None`）补登进两份代码清单；附录 H 补 `diff`、`decision_review_data` 两行（含 9 键结构、写入/消费模块、降级语义），使「代码用键 ⊆ 台账登记键」成立；两处 `data-channels-schema.md` 指针改为 `technical.md` 附录 H。
- **行为变更**：① 实验功能「决策跨期反思闭环」开启时，写 `decision_review_data` 不再产生「未知键」WARNING（此前每轮报告固定刷一条噪音告警）；② `pipeline_data` 中不再出现永无消费者的 `portfolio_daily_returns`（`_snapshot.py`/`_full_risk_metrics.py` 的 `extra` 透传机制本身保留，其 docstring 由「如 risk_metrics」改为中性的「调用方 kwargs」以免继续暗示该键的存在）。报告输出无变化。
- **测试**：`test_pipeline_data_builder.py` 新增 `TestSchemaRegisteredInAppendixH` 四例——`test_known_keys_documented_in_appendix_h` 与 `test_type_map_keys_documented_in_appendix_h` 从 `technical.md` 现场解析附录 H 表格键名，锁定「代码用键 ⊆ 台账登记键」（解析结果为空即视为台账标题/格式变更而失败，防台账被改格式后校验静默失效）；`test_decision_review_data_registered`（类型登记 + `build()` 注入无告警，用 `assertNoLogs`）与 `test_portfolio_daily_returns_is_not_a_pipeline_key`（死键不得复活）。四例均已验证还原旧实现后转红。

### 凭据分离校验收紧为硬拒绝（自审 rf-327）（2026-09-10）

- **缺陷（自审 rf-327）**：`config/_llm_providers.py::_validate_provider_entry` 对「条目内联 `api_key`」的处理是**先校验必填、再告警放行**——无 `credentials_ref` 时把内联 `api_key`/`model` 当合法配置接受，仅在 `_parse_providers_list` 里记一条「建议迁移」的 WARNING 后照常进入运行期 provider 链。这与凭据分离约束的字面要求不符：`llm_providers.json` **是版本控制内文件**（`.gitignore` 白名单放行，`git ls-files` 可证），内联 `api_key` 即「凭据随配置入库」，WARNING 级提示既拦不住误提交，也不改变已经发生的泄露。附带发现同一段逻辑的另一处**文档与实现不符**：`_llm_providers_defaults.py` 生成的模板注释邀请用户「按需修改 model / endpoint」，但 `_parse_providers_list` 在 `credentials_ref` 分支下**只透传 `credentials_ref`、丢弃 entry 级 `model`**——照模板改的 `model` 覆盖被静默忽略（`_resolve_entry_credentials` 里 entry 级优先的分支因此永收不到值），用户看到的是「改了没反应」。
- **改动**：
  - 校验层：内联 `api_key` **非空即拒**（不再是必填校验 + 放行），WARNING 文案直接给出迁移指引（移入 `llm_key.json` 凭据块 + 用 `credentials_ref` 引用）；`credentials_ref` 升为**必填**（唯一合法凭据来源）；`model` 由「无 ref 时必填」改为**始终可选**（凭据块可提供），仅校验类型不为非法；纯空白视同未设置，不因可选字段的空白拒收整条。
  - 解析层：`entry_dict` 恒写 `credentials_ref`；`model` 恢复透传（非空才写，空串会让 `_resolve_entry_credentials` 的 falsy 判断跳过凭据块同名值）——模板注释承诺的「按需修改 model」至此真正生效。
  - `llm/api.py::_resolve_entry_credentials` docstring 补「凭据来源边界」说明：`entry["api_key"]` 分支只服务运行期直接构造的内存条目，配置来源的条目永不带该键；llm_key.json 的单键 flat 格式也不走此分支（由 `get_llm_config()` 合并为顶层键走单 Provider 模式）。
- **行为变更（需注意）**：① 内联 `api_key` 的条目由「告警后照常使用」变为**整条跳过**——若链中只剩该条，则该模块回落占位文本；② `credentials_ref` 缺失的条目同样被跳过；③ entry 级 `model` 覆盖**开始生效**（此前对 `credentials_ref` 条目无效）。已验证本仓 `data/config/llm_providers.json` 的实际条目均为 `credentials_ref` 形态、无内联 `api_key`，默认模板 `_llm_providers_defaults.py` 亦本就合规，故现有配置不受影响；旧内联配置的迁移路径见 `how-to-config-llm.md`。
- **文档**：`llm-technical.md` §5.3 重写为「凭据分离的边界是 `api_key`，不是全部字段」——`model`/`endpoint` 属非敏感路由字段，可留在路由配置按条目覆盖，并列出「硬拒绝 + 必填 + entry 覆盖」三条规则与迁移步骤；调用链示意同步。`how-to-config-llm.md` 的「Provider 条目字段」表补 `model`/`endpoint` 两行（原表漏列 `model`，而旧实现下它还是条件必填），并加「不得内联 `api_key`」警示块。`technical.md` 凭据分离约束行改为「`credentials_ref` 必填、内联 `api_key` 硬校验拒绝」，适用范围补 `config/_llm_providers.py`、`llm/api.py`。
- **测试**：`test_config_llm_multi.py` 相关用例整体迁移到 `credentials_ref` 形态，并把原 `test_api_key_stripped`（断言内联字段被保留供运行期读取）替换为三例：`test_inline_api_key_rejected`（内联条目不出现在运行期列表）、`test_model_carried_as_routing_override`（entry 级 model 覆盖被透传）、`test_blank_model_not_carried`（空串不写键）；`TestValidateProviderEntry` 的「缺 api_key / 缺 model 告警」两例替换为 `test_inline_api_key_rejected` / `test_missing_credentials_ref_errors` / `test_model_optional` / `test_empty_inline_api_key_no_warning`。已验证还原旧实现后其中 5 例转红。

### LLM 模块显示名回归中央注册表（模块注册一致性，自审 rf-330）（2026-09-10）

- **缺陷（自审 rf-330）**：`config/_llm_settings_defaults.py` 自留一份模块显示名映射 `_MODULE_LABELS`（5 条：global_macro / expert_review / health_check / penetration_deep / news_correlation），与 `core/registry.py::get_llm_module_names()`（8 条，多出 debate_pro / debate_con / debate_synthesis）**并存**，违反「LLM 模块元信息以中央注册表为单一事实来源」。这份副本的两处实际后果：
  - `_module_block()` 对未登记的模块走 `_MODULE_LABELS.get(module, module)` 回退，即**新增模块在配置模板里显示为裸键名**（如 `// debate_pro — debate_pro`）而非中文名——不报错、不告警，只是注释变成英文键。
  - 同文件内 `news_correlation` 的显示名**写了两遍**：`_MODULE_LABELS` 里一条，模板 `_section(f"财经新闻热点与持仓关联分析 — news_correlation")` 又硬编码一次。两处相邻但无约束，改一处忘另一处即静默不一致（该模块因不支持 `output_brief` 而单独拼接，正是漏走 `_module_block()` 统一取值路径的那一个）。
- **改动**：`_MODULE_LABELS = get_llm_module_names()`（模块级导入中央注册表），副本删除；`news_correlation` 区块标题改取 `_MODULE_LABELS.get("news_correlation", "news_correlation")`，与其他模块同一取值路径，并补注释说明该模块为何不走 `_module_block`（无 `output_brief` 键）。
- **行为变更**：无——已验证改前改后 `_get_default_llm_settings_template()` 的**输出逐字相同**（diff 为空）：既有 5 个模块的显示名与注册表本就一致，本次仅消除副本与重复。
- **测试**：`test_config.py::TestLlmSettingsTemplateConsistency` 新增两例：`test_module_labels_derived_from_registry`（映射须与 `get_llm_module_names()` 深度相等 + `enabled_llm` 每个子键都能查到显示名，已验证还原旧实现后转红——旧副本少 3 个 debate 模块）、`test_template_module_titles_match_registry`（从渲染出的模板里正则抽出各「显示名 — 模块」区块标题，逐个比对注册表取值，属渲染结果层锁定）。配置单元测试 100 例全绿。

### 移除新闻关联的误导性编排注册（模块注册一致性，自审 rf-329）（2026-09-10）

- **缺陷（自审 rf-329）**：编排层 `_dispatch_llm_workers` 内有一条 news_correlation 注册分支——仅当调用方传入 `news_data` 且 `holdings_data` 时，把 `_make_news_correlation_closure(...)` 写进 `_MODULE_FNS`。但这两个参数在**任何调用方都未传入**（`generate_all_llm` 是唯一调用方，其签名与实参均无此项），分支永不执行。连带整条「预计算」链同样是死代码：模块级变量 `_news_correlation_result`、公开读取接口 `get_news_correlation_result()`、结果回写函数 `_store_news_correlation_result()`、闭包工厂 `_make_news_correlation_closure()`，以及 `run_news_correlation_safe()` 里「若已有 orchestrator 预计算结果则直接返回」的短路——四处没有一处可达。危害不在性能而在**语义**：注册表与文档呈现出「新闻关联由编排层统一调度、结果经模块级变量复用」的图景，与真实路径（`report/news_correlation.py` 直调 `run_news_correlation_safe`）不符，正是「注册须与真实运行路径一致」所防的漂移；后来者若照此图景扩展（例如给 `generate_all_llm` 加新闻参数以「启用」预计算），会同时把 `(list, bool, dict)` 的三元返回塞进期望 `(str|None, bool)` 二元返回的线程池，异常只在运行期暴露。
- **改动**：删除上述四处死代码与 `run_news_correlation_safe` 的预计算短路；`_dispatch_llm_workers` 去掉三个永不使用的参数（`news_data` / `holdings_data` / `penetrated_assets_for_news`）及注册分支；`llm/__init__.py` 与编排门面的 re-export 同步移除 `get_news_correlation_result`。`_llm_news_correlation.py` 模块 docstring 改写为说明**为何不经编排层**（返回类型二元/三元不兼容 + 实际由报告侧直调），并注明已被移除的误导路径，避免该分支再被「复原」。模块显示名/设置键不受影响，仍由 `core/registry.py::get_llm_module_name` 单一登记。
- **行为变更**：无——被删的路径在删除前即不可达；`report/news_correlation.py` 走的 `run_news_correlation_safe` 直调入口行为不变（其内部分支减少一条恒假判断）。
- **测试**：`test_generate_all_llm.py` 新增 `TestNewsCorrelationNotOrchestrated` 三例：`test_dispatch_has_no_news_correlation_params`（签名不得再含三个死参数，已验证还原旧实现后转红）、`test_dispatch_never_returns_news_correlation`（实跑分发，结果键即为传入模块键，无注入）、`test_precompute_result_api_removed`（`src.python.llm` 不再暴露预计算结果读取接口，已验证还原旧实现后转红）。LLM 单元测试 996 例全绿。

### 报表页签显示名注册表驱动（自审 rf-326）（2026-09-10）

- **缺陷（自审 rf-326）**：`report/excel_generator.py::_write_data_source_matrix_sheet` 把「数据源可用性矩阵」页签的**表内标题写成字面量**，绕开显示名注册表，违反「报表页签标题由注册表驱动、禁止硬编码显示名」。同一显示名因此存在于两处——`core/registry.py::_REPORT_SECTION_DEFAULT`（页签名，经 `excel_sheet_factory` 生成 `ws.title`）与写入层字面量——改一处不会同步另一处，且无任何测试拦截漂移。同批核对发现「数据源可用性矩阵」「LLM API 用量」两个页签**未登记**在 `_REPORT_SHEET_NAMES`（该表按表头注释只排除「已由 `get_llm_module_name()` 注册」的 LLM 模块章，此二键不属此列，属遗漏）；未登记时 `get_report_sheet_name()` 走「回退为键名」兜底返回英文键，故仅改写入层调用而不补登记，会把 `data_source_status` 这个英文键当标题写进报告——补登记是该修复成立的前提。
- **改动**：`_REPORT_SHEET_NAMES` 补登 `data_source_status` / `llm_usage` 中文显示名；`_write_data_source_matrix_sheet` 改取 `get_report_sheet_name("data_source_status")`。`developer-guide.md` 的注册表说明同步校正——原文称「页签标题与顺序由**独立的 `_REPORT_SECTION_DEFAULT`** 注册表驱动，`get_report_sheet_name()` / `get_report_section_order()` 均读该注册表」，与实际不符（`get_report_sheet_name` 读的是 `_REPORT_SHEET_NAMES`）；改为说明两张注册表的职责分工：「页签叫什么」由 `_REPORT_SHEET_NAMES` 管、「章按什么顺序排」由 `_REPORT_SECTION_DEFAULT` 管，新增页签的登记路径一并写明。
- **行为变更**：无——该页签表内标题此前即与注册表登记值一致，本次仅把取值收敛到注册表（`llm_usage` 表内标题取自 `ws.title`，不受影响）。
- **测试**：`test_registry.py` 新增 `TestReportSheetNames` 三例：`test_sheet_names_match_section_names`（遍历 `_REPORT_SHEET_NAMES`，断言每个键都在 `_REPORT_SECTION_DEFAULT` 中且显示名逐字相同——把「两张注册表漂移」变成红灯）、`test_data_source_status_name_registered`（回归：标题取注册表值而非字面量，已验证还原旧实现后转红）、`test_unknown_key_falls_back_to_key`（锁定未登记键回退为键名的既有语义）。另清理该文件三处多余的 f-string 前缀（ruff F541）。

### 估值取数回归 Provider Chain 与会话复用（自审 rf-324 / rf-325 / rf-334）（2026-09-10）

- **缺陷（自审 rf-324，绕开 Provider Chain）**：`report/fund_style_classify.py::_push2_extended` 直接 import `fetcher.industry.make_push2_request` 发起 push2 请求——该入口是 provider 函数的**薄透传**，不经 Provider Chain，因而没有备用源递补（`eastmoney_industry_rest`）、不经 `industry_` 文件缓存、不登记 `FailureDiagnostics` 数据源状态（provider 模块内部的熔断计数仍在，故问题被掩盖得更深），也不参与会话复用；provider 侧失败时报告层只看到一条「扩展数据获取失败」告警，数据源可用性矩阵里毫无痕迹。同批发现 `fetcher/industry.py::make_push2_request` 在本轮修复后**已无任何生产调用方**，作为「绕开 Chain 的现成入口」继续留在网关层，正是同类违规的温床——一并删除。
- **缺陷（自审 rf-325，绕开 Provider Chain）**：`report/orchestrator.py::_fetch_valuation_for_code` 直接 `from src.python.providers.eastmoney_industry import fetch_valuation_fields`，**报告层直连 provider 模块**，同样绕开 Chain 与文件缓存，且与「Provider Chain 必经」的网关约束直接冲突。
- **缺陷（自审 rf-334，重复取数）**：`_get_industry_avg_pe` 对每个代码**发两次同参数 push2 请求**——先 `fetch_industry_data` 取行业归属，再 `_push2_extended` 取 PE；而 PE（f9）本就是同一次 push2 响应里的字段（provider `_FIELDS` 已含 f9/f20/f23），第一次请求的响应里就有。会话级 API 复用要求同一会话同一 API 只取一次，此处是纯浪费（每只持仓多一次请求，直接放大限频风险）。
- **改动**：
  - `providers/eastmoney_industry.py::fetch_industry_and_concepts` 的返回值补 `market_cap`（f20，与既有 pe/pb 同源同请求），`fetch_valuation_fields` 从 provider 移除（避免 provider 层再提供一个「非 Chain」取值口）。
  - `fetcher/industry.py::_industry_transform` **透传** pe/pb/market_cap（原实现在网关转换层丢弃这三个字段，迫使消费方另想办法取数）；新增 `fetch_valuation_fields(code)` 作为 PE/PB 的**网关入口**（经 `fetch_industry_data_cached` → Chain + 文件/会话缓存），`_push2_extended` 与 `_get_industry_avg_pe` 改从行业结果直接取 PE，`report/orchestrator.py` 改 import 网关入口；`fetcher/industry.py::make_push2_request` 删除。
  - **旧缓存载荷迁移**：行业缓存 TTL 为两周，而旧载荷不含扩展行情字段，`fetch_with_fallback` 命中即返回——不处理的话旧载荷会在存活期内被当作有效命中，PE 取用静默退化为「不可得」（无异常、无告警）。新增 `_drop_legacy_cached_payload`：判据取「键是否存在」（新载荷无论 provider 是否给出都会带键，值为 None 表该源不提供），缺键即清除并回落重取；单代码至多迁移一次，旧载荷全部过期后成为无害空转。
  - `analysis/valuation_percentile.py` 模块 docstring 的取数路径同步为网关入口（原文写「复用 providers…make_push2_request 通道」，已失真）。
- **行为变更**：`_push2_extended` 的取数来源由「独立 push2 请求」变为「行业数据结果」，其 `extended_{code}` 全天缓存与腾讯侧降级链（`_tencent_extended`）保持不变；PE/PB 现在享受 Chain 的熔断/降级/诊断与 7 天行业文件缓存，同一代码同一轮**只请求一次**。
- **测试**：`test_fund_style.py` 各用例改自行业结果提供 PE，`test_single_fetch_per_code` 替换原「session_cache 填充」用例——以「每个代码恰好调用一次行业入口、未二次请求」锁定会话复用回归（旧实现下即两次取数）；`test_fetcher_industry.py` 新增 `TestFetchValuationFields`（网关入口契约：投影/不可得/字段缺失/经入口取数）与 `TestLegacyIndustryCacheMigration`（旧载荷清除、新载荷不误删、转换层透传字段）；`test_eastmoney_industry.py` 原 `TestFetchValuationFields` 改为 `TestIndustryExtendedFields`（锁定一次请求带出 pe/pb/market_cap）。

### 原子写入收敛到唯一原语（自审 rf-322）（2026-09-10）

- **缺陷（自审 rf-322）**：全局架构审计发现缓存原子写入约束在实现层**逐字重复了 4 份 mkstemp + os.replace 拷贝**（`core/jsonl_store.py`、`core/provider_registry.py`、`report/history_snapshot.py`、`config/features.py`），另有 **5 处写入完全无原子性**（违反原子写入的字面要求）：
  - `analysis/_silence.py::_save_silence_state`、`analysis/circuit_breaker_wrapper.py::_save_state` 与 `_migrate_legacy`、`report/data_status.py::_persist`：`open(path, "w")` 直接覆盖——中断即留截断 JSON，下次读取解析失败，静默期状态/断路状态/降级记忆**整份丢失**（断路器「失忆」后已熔断的源被立即重试）。其中 `data_status` 的降级状态文件被高频改写，并发读取方还可能读到半写内容。
  - `providers/news_dedup.py::_flush_anchors`：`open(..., "a")` 逐行追加——中途中断留下**半行** JSONL，而读取方按行解析，该行及其后记录一并作废。
  - 多份拷贝的实质风险与原子写入约束的补充说明一致：改一处必漏其余，且各调用点拿不到成败（无法据此决定后续动作）。
- **改动**：新增 `core/atomic_write.py`（`write_text_atomic` / `write_json_atomic`，mkstemp + 同目录 os.replace；Windows 下 os.replace 遭占用时回退「删目标 + rename」，与 `cache/_io.py::_write_atomic` 同一处置），上述 8 处全部迁移到该原语，`jsonl_store` 另抽出批量入口 `append_jsonl_atomic_many`（锚点文件已达数万行，逐行调用等价于每行整文件重写，O(n²)）。原语契约：**失败记日志并如实返回布尔、不向上抛**，调用方按需还原异常类型（`history_snapshot.save` 即据返回值重新抛 `OSError`，保持其「失败即抛」的对外契约）。`cache/` 子包（需 gzip 分支与文件锁）与 `config/_core.py::_atomic_write`（契约是「失败即抛且保留异常类型」，被 `init_config()` 的 Windows 并发容忍分支与 TUI 的权限提示依赖）两处**有意不合并**，理由写在原语 docstring 与原子写入约束行内。
- **行为变更（均为修正方向）**：① 上述 5 处由「非原子覆盖」变为原子替换，写失败时旧文件原样保留；② `news_dedup` 落盘失败时**撤回**本轮登记的 `(source,title)` 已写 key（旧实现 key 留在集合里，该对新闻此后每轮都被判「已写」而永不重试，锚点**永久丢失**却只记一条 warning）；③ `circuit_breaker_wrapper._migrate_legacy` 显式以写入成败决定是否删除旧文件，删旧失败由静默的 debug 改为 warning；④ `jsonl_store`/`history_snapshot` 的 os.replace 在 Windows 占用场景获得回退路径。
- **测试**：新增 `src/test/unit/core/test_atomic_write.py`（12 例：正常写入/目录创建/覆盖/无临时残骸、mkstemp 失败与替换失败均返回 False 且旧内容原样保留、序列化失败、Windows 占用回退）；`test_news_sources.py::TestFlushAnchorsDedup` 新增写失败回滚用例（以「锚点目录被同名文件占位」构造真实 IO 故障，已验证还原旧实现后转红——旧实现 key 未撤回）；`test_features_edge.py` 新增功能开关写失败不抛出且内存态仍同步用例。原子写入相关单元测试 4080 例全绿。

### 持仓跟踪缓存读取回归 cache API（自审 rf-323）（2026-09-10）

- **缺陷（自审 rf-323）**：`cache/services/holdings_tracker.py::_read_holdings_tracking` **绕过 cache API 直接读缓存文件**（`_cache_path()` + `open` + `json.load` + 手取 `payload["_data"]`），违反「所有持久化缓存必须通过 `cache/` 子包的 `get()`/`set()` 接口读写，禁止直接操作 `data/cache/` 文件系统」的约束。逐项后果：
  - **TTL 声明失效**：注册表为 `holdings_tracking` 声明 `CACHE_MONTHLY`，旁路读取使该声明完全不起作用（即该约束表头所列「TTL 失效」后果的实例）。
  - **gzip 变体读不到**：缓存层读路径优先 `.json.gz`（超 100KB 自动转储），旁路读取只看 `.json`——一旦转储，跟踪记录被静默当作不存在，全部代码误判为新增（方向上属过度刷新，非漏刷）。
  - **BOM/编码容错缺失**：缓存层用 `utf-8-sig` 读取并捕获 `UnicodeDecodeError`，旁路读取用 `utf-8` 且异常元组不含 `UnicodeDecodeError`——带 BOM 的跟踪文件会**直接抛出**打断主流程而非降级。
  - **损坏文件不清理、命中率不统计**：缓存层读失败会自动删除损坏文件并记录 hit/miss，旁路读取两者皆无。
- **改动**：改经 `cache.get(tracking_key, get_ttl("tracking", tracking_key))` 读取，TTL 取自注册表声明；返回值非 dict 时视为无记录返回 None（「不存在/损坏」的处置统一交回缓存层）。函数 docstring 补充「必须走 cache API」的理由与过期语义。
- **行为变更**：跟踪记录超过 `CACHE_MONTHLY` 后读取返回 None，调用方按「无上轮记录」处理——即全部代码视为新增并触发关联缓存刷新（**修复**方向：宁多刷不漏刷）；TTL 内行为不变。
- **测试**：`test_holdings_tracker.py` 新增 `TestReadHoldingsTrackingUsesCacheApi` 三例（经 `cache.set` 写入后读到内层数据 / TTL 置负 → None / 无记录 → None），并补强首次运行用例断言「无上轮记录 → 全部代码视为新增」。TTL 用例为判别点——已验证还原旧实现后转红（旧实现无视 TTL，会返回过期指纹并跳过刷新）。

### 代码类型判定回归中心化（自审 rf-333）（2026-09-10）

- **缺陷（自审 rf-333）**：全局架构审计（架构设计约束表逐条对照）发现两处**绕过 `core/code_utils.py` 自建代码前缀判定**，违反「所有资产代码类型判定必须使用 `core/code_utils.py`，禁止任何模块自行实现判定逻辑」的约束：
  - `report/chart_data_builder.py::_infer_property`——按 `code[:1] in ("6","0","3")` 判股票、`("5","1")` 判基金。**实际影响**：北交所（8 开头）股票全部落入「其他」资产属性，饼图与持仓分类表口径不一致（68xxxx 科创板仅因首字符恰为 6 而蒙对，语义上仍是巧合而非判定）。
  - `config/anonymizer.py::_categorize_holding` / `_categorize_detail`——中心判定之外**并存**一张「0/3/6 开头即股票」回退表（外加 `except ImportError: pass` 兜底）。两套判定并存即会漂移，且把错误前缀知识散落到匿名化层；`except ImportError` 兜底在当前包结构下永不可达，属防御性死代码。
  - 违规后果与约束表头描述一致：代码前缀知识散落多处，新增资产类型时需全局搜索替换、极易遗漏。
- **改动**：`_infer_property` 改委托 `is_a_share_code()` / `is_exchange_fund_code()`（模块级导入，与同文件其他 `core.*` 导入一致）；`anonymizer` 两处改为模块级导入 `is_fund_holding` 并无条件委托，删除内联前缀表与 `except ImportError` 分支。判定语义单一来源化后，两处随 `code_utils` 演进自动跟进。
- **行为变更**：`_infer_property` 对北交所代码（如 830799）由「其他」变为「股票」——属**修正**而非回归（与持仓分类表口径对齐）；其余代码分类结果不变。
- **测试**：`test_anonymizer.py` 把失效的 `test_import_error_falls_back_to_prefix`（在原实现下已因模块级导入提前绑定而形同虚设）替换为 `test_delegates_to_central_judgment`（mock 中心函数返回值双向验证无条件委托）+ 新增 `test_beijing_exchange_stock_not_misclassified_as_fund`；`test_chart_data_builder.py` 新增 `test_infer_property_star_and_bse_boards_classified` 锁定科创板/北交所归「股票」、5 开头场内基金归「基金」。两用例均已验证还原旧实现后转红。另清理该测试文件历史遗留的未使用 `import logging`（ruff F401）。

### 死代码清理：未接线的股息率取值（自审 rf-332）（2026-09-10）

- **缺陷（自审 rf-332）**：`analysis/metrics_risk.py::get_dividend_yield` 在全仓（`src/`、测试、模板、文档）**零调用点**——自早期量化指标体系引入后未接入任何报告章节、LLM 提示词或纪律判定，仅由 `analysis/metrics.py` 与 `analysis/__init__.py` 两层 `__all__` 转出，形成「看起来是公共能力、实则从不执行」的假接口。更实际的问题是它**按早期缓存键契约取数**（`dividend_{code}` / `price_{code}` + `item.get("year"/"dividend"/"cash_dividend")` 多形态猜测），保留即保留一份与现行情链路无关的取数路径——将来误接时不会报错，只会静默拿到空值。
- **改动**：删除 `get_dividend_yield` 函数体与其在 `metrics_risk.__all__`、`metrics.py`（导入 + `__all__` + 模块 docstring 清单）、`analysis/__init__.py`（导入 + `__all__`）三处导出。报告中的股息信息另由持仓/流水链路（`compute_dividend_totals`）承担，不受影响。
- **测试**：全量单元/场景测试无一处引用该名（删除后 `src/test/unit/analysis` 全绿），不新增用例——死代码的验收标准即「删除后无回归」。

### 开发版本切换（2026-09-10）

- 发布 v0.10.17 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.18。

### 汇率敞口「其他币种」行未定义名崩溃（自审 rf-335）（2026-09-10）

- **缺陷（自审 rf-335）**：`analysis/fx_exposure.py` 汇总非 CNY/HKD/USD 币种时，行内标签写作 `_CURRENCY_OTHER`——**该名字全仓未定义**（常量与标签表键均为 `CURRENCY_OTHER`，无下划线前缀），该分支一执行即抛 `NameError: name '_CURRENCY_OTHER' is not defined`，整段外汇敞口分析中断。当前 `core/code_utils.get_currency_by_code()` 只返回 CNY/HKD/USD，故**今日走不到**（潜藏缺陷）——但同文件已知币种行取的是 `_CURRENCY_LABELS.get(currency, currency)`，两行取法不一致本身就是隐患：将来（或用户自持的）代码一旦识别出新币种（JPY/SGD…），不是渲染成「其他」而是直接把报告打崩。该名由 ruff 的 F821（未定义名）静态检查暴露。
- **改动**：`"label": _CURRENCY_OTHER` → `"label": _CURRENCY_LABELS.get(CURRENCY_OTHER, CURRENCY_OTHER)`，与已知币种行同一取法，标签表里既有的 `CURRENCY_OTHER: "其他币种"` 条目随之真正生效。
- **测试**：`test_fx_exposure.py` 新增 `TestFxExposureOtherCurrency::test_other_currency_row_labeled`——patch `get_currency_by_code` 使一只持仓解析为 JPY（模拟新增币种），断言未知币种汇总为一行「其他」、标签为「其他币种」、占比正确、`has_foreign` 为真。已验证还原旧实现后该用例转红（实测 `NameError: name '_CURRENCY_OTHER' is not defined`）。
