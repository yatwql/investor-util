# 变更日志归档 — v0.10.x

> 归档时间：2026-08-06；2026-08-16 二次合并 changelog.md [0.10.9] ~ [0.10.13] 已发布版本变更记录
> 原始文件：`docs-stm/managements/changelog.md`
> 涵盖版本：v0.10.1 ~ v0.10.13（2026-08-04 ~ 2026-08-14；v0.10.0 无独立 changelog 段）
> 归档内容：v0.10.x 已发布版本变更记录（仍处开发版本 [0.10.14-dev] 保留在原文件 changelog.md）

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
