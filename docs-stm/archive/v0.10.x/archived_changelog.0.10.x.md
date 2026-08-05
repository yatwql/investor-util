# 变更日志归档 — v0.10.x

> 归档时间：2026-08-05
> 原始文件：`docs-stm/managements/changelog.md`
> 涵盖版本：v0.10.1 ~ v0.10.6（2026-08-04 ~ 2026-08-05；v0.10.0 无独立 changelog 段）
> 归档内容：v0.10.x 已发布版本变更记录（v0.10.7 保留在原文件，不随版本归档）

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
