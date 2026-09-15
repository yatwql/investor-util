# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.20-dev] - 开发中（未发布）

### DataSinking 财报接入·数据层（plan-42 阶段①②③）（2026-09-14）

- **凭据**：`CredentialSpec` 扩展 `key_file` / `key_field` / `key_section` / `key_file_setting`，就绪判定支持「环境变量或密钥文件」（环境变量优先）；新增 `credential_value()` 取值接口，就绪矩阵增「来源类型」与密钥文件路径，**值永不回显**。密钥文件通用化：新增顶层路径键 `data_key_file`（默认 `data/config/data_key.json`），文件**以 provider（source_id）为节**（如 `{"datasink": {"api_key": "..."}}`），一个文件容纳多个数据源的 key；纳入绝对化与测试隔离。
- **provider**：新增 `providers/datasink.py` —— DataSinking 全文本财报（`/documents`、`/documents/{id}`、`/documents/{id}/sections`）；A 股 6 位代码 → FMP 符号映射；**计划感知限速**（间隔 = 1/每秒上限，免费 3 请求/秒、付费 31，由 `datasink.plan` / `requests_per_second` 派生）在**每次 HTTP 请求前** `RateLimiter.acquire`（免费档无批量端点、必然逐篇请求，限速必须落在本层）+ **日配额护栏**（`data/state/datasink_quota.json`，免费 8,191 篇/日，超限即停）；401/429/非 200/网络不可达均返回空并按代码级降级（不计传输级熔断）；凭据值不落日志。
- **契约与链路**：新增数据域 `financial_report` 与标准字段记录 `FinancialReportFields`（登记 `DOMAIN_RECORDS`）；新增 `fetcher/report_adapters.py::DataSinkReportAdapter`（上游 `id` → 标准 `doc_id`，契约自检通过），登记 `ADAPTER_MODULES`；新增默认链 `financial_report: ["datasink"]`；缓存注册 `report_datasink_index_`（两周）/ `report_datasink_doc_`（一月）；数据源可用性矩阵新增「财报全文」类别；配置校验已知类型/名称放行 `financial_report` / `datasink`。
- **测试**：新增 `test_datasink.py`（26 例：符号映射/套餐限额派生/凭据缺失跳过/请求前限速与配额护栏/401·429·非 200·非 JSON/取数原语）；`test_datasource_credential.py` 增密钥文件 8 例（就绪/环境变量覆盖/空值与损坏/配置路径覆盖/取值不回显）；适配器自检用例改为断言域覆盖而非写死总数。dev-verify 2602 passed / 0 failed。
- **章节装配（阶段④a）**：新增 `fetcher/financial_report.py`（A 股标的收集含去重与穿透合并；元数据按年报→半年报顺序取最新一篇并缓存；单篇正文经链路 + 财报域适配器归一；摘要按 `datasink.max_chars` 截断）与 `report/financial_report_digest.py`（`financial_report_digest_data` 契约：`available`/`rows`/`failures`/`entry_count`，含文种中文标签与披露日换算；缺凭据/无 A 股标的/全部无覆盖均降级不抛异常）。新增 `datasink` 配置段（plan / requests_per_second / daily_quota / sections / max_chars / doc_types）与 `batch.datasink_workers`。新增测试 14 例。
- **渲染接线（阶段④b）**：注册表新增章节 `financial_report_digest`（type=`financial_report`、data_flag=`financial_report_digest_data`、页签名「持仓个股财报摘要」）；新增开关 `report_submodules.financial_report_digest`（默认关）与 `is_enable_financial_report_digest`；pipeline_data 契台登记（`pipeline_data_builder` 三处 + technical.md 附录 H）；Excel 自动建页签与写盘（`report/financial_report_sheet.py`）、HTML 章节 partial（`partials/financial_report_section.html`）与目录分组；both/full 双路径均按开关注入契约。新增页签测试 3 例；同步更新写死章节数/类型/分组/契约的既有用例（注册表 20 项 + 新 type）。
- **配置与入口补全**：`report_submodules.financial_report_digest` 接入 TUI 菜单 P 子菜单（第 7 项）与 Web 配置面板白名单，用户无需手改 config.json 即可开启；`batch.datasink_workers` 由财报摘要装配层消费（`ThreadPoolExecutor` 并发取数，默认 3，免费档批量上限 ≤3；每秒速率仍由 provider 限速器逐请求兜底）。
- **数据源说明表**：「数据源可用性矩阵」章在健康度表后新增「数据源说明（实际使用清单）」表——逐数据类别列出实际链路（如财报全文=DataSinking）、用途、计费（免费/免费档/付费档，财报全文随 `datasink.plan` 动态展示）与凭据要求（是否需 key + 就绪状态），并标注本次运行是否实际使用（观测到 DegradationTracker 事件即为已使用）。Excel（旧样式页签与数据质量仪表盘两路）与 HTML 同步渲染，`build_data_source_catalog()` 输出契约。
- **状态**：plan-42 全部完成——数据层（①②③）+ 章节装配（④a）+ 渲染接线（④b）+ 文档同步（⑤：requirements §6.12 R-FRD-01~07、technical 附录 H 与 §4.9/§6.7、datasource 两册、how-to-config、folders）。

### 财务指标全文解析备用支路（`datasink_indicator`，plan-43 阶段②）（2026-09-15）

- **实测推翻原设计前提**：DataSinking 的 Markdown **不保留表格**（PDF 报表被压平为「标签紧连数字」的整段正文，如 `...营业收入86,241,940,222.2084,491,870,566.52...`），且不存在 `主要会计数据与财务指标` 章节（该名 404）；指标实际在**第二节「公司简介和主要财务指标」**（别名 `主要财务指标` 命中共章），季报为「主要财务数据」。据此**修订设计文档 §5**（新增 §5.0 前提修订）：解析策略由「读表格」改为「锚点 + 前若干数值」，并把解析**收窄到该章节**（报表正文存在附注编号与金额粘连的误读风险，收益低于风险）。
- **纯解析层**：新增 `analysis/financial_indicator_extract.py` —— 锚点表（营收/归母净利/经营现金流/基本每股收益/加权 ROE，含「归属于母公司股东」旧式行文）+ 否定环视排除「扣除非经常性损益后的…」同口径干扰 + 有限取值窗口（超窗判为跨行、弃用）+ 按报告期精度选数值模式（金额两位小数、每股四位、比率两位，避免 `1.41011.3281` 无分隔连写误切）+ 金额单位换算（取锚点前最近「单位：X」，**无声明即不产金额**）+ 逐字段幅度/区间校验；同比由本期/上年**同口径**两值算术派生。报告期/文种一律由元数据给出。
- **解析适配器**：`fetcher/financial_indicator_adapters.py` 新增 `DataSinkIndicatorAdapter`（`datasink_indicator`），**逐章节试取、命中即止**（避免同一章节被多个别名重复取回白耗配额）；取数经既有 `fetcher/financial_report.py` 链（复用其缓存/限速/配额/熔断，**不另建 HTTP 通道**）。
- **链路**：`financial_indicator: [akshare_financial, datasink_indicator]`（主源失败落解析支路）；配置校验放行新源名 `datasink_indicator`。
- **覆盖面（诚实边界）**：解析支路提供营收/归母净利/营收同比/净利同比/经营现金流净额/基本每股收益/ROE 共 7 项；毛利率、资产负债率、每股净资产**不在该章节**，恒为 `None`（由主源 akshare 提供）。
- **实测复核**：新增真实正文夹具 `src/test/data/fixtures/datasink_indicator_section_600900.md`（长江电力 600900.SS 2025 年报该章节全文，附 `README.md` 记来源与核对值），逐字段复现披露值——营收 86,241,940,222.20 元、归母净利 34,502,809,176.39 元、经营现金流 60,562,925,570.41 元、EPS 1.4101 元/股、ROE 15.90%、同比 2.07% / 6.17%。
- **测试**：`test_financial_indicator_extract.py`（真实夹具回归 + 行文变体/单位/精度/扣非排除/降级）+ `test_financial_indicator_extract_edge.py`（窗口边界/异常幅度/越界比率/零基数同比/截断正文，`*_edge.py` 隔离）+ `test_financial_indicator.py` 扩充（链路顺序、落解析支路且源身份为 `datasink_indicator`、逐章节试取、非 A 股不发请求、双源皆失败返回 None）。

### 结构化财务指标数据域（`financial_indicator`，plan-43 阶段①）（2026-09-15）

- **新增数据域与契约**：`financial_indicator` 域 + `FinancialIndicatorFields`（营收/净利/同比/毛利率/ROE/负债率/经营现金流/EPS/每股净资产；金额单位元、比率为小数比例、可选数值缺失取 `None`），登记 `DOMAIN_RECORDS` 并纳入适配器契约自检。
- **主源 provider**：`providers/akshare_financial.py` —— 一次 `stock_financial_abstract` 取回宽表（指标 × 报告期），归一为每报告期一条标准记录；百分数（ROE/毛利率/负债率/同比）换算为小数比例；同名指标多分组按表格顺序首个非空为准；非 A 股/未安装/超时/空表返回空。
- **适配器与链路**：`fetcher/financial_indicator_adapters.py::AkshareFinancialAdapter`（标准字段直出，无需 alias）+ 新链 `financial_indicator: [akshare_financial]`；取数复用 `fetch_with_fallback`（缓存/熔断/降级），缓存前缀 `fin_indicator_`（一月 TTL、基础类）；配置校验放行新数据类型/源名。
- **共享原语收敛（去重）**：A 股→FMP 符号映射统一为 `core/code_utils.py::to_fmp_symbol`（原在 datasink 内，现两个数据源共用）；akshare 取数超时封装统一为 `providers/_utils.py::run_with_timeout`（由 `akshare_extras` 抽出，避免第二份副本）。
- **测试**：新增 `test_akshare_financial.py`（宽表归一/百分数换算/同名指标优先与逐期补齐/文种映射/各类降级，15 例）与 `test_financial_indicator.py`（适配器登记与自检/标准字段集/链注册/链路取回与降级，5 例）；`TestFmpSymbol` 随函数迁移至 `test_code_utils.py`（unit_core）。
- **口径**：本阶段仅数据层（无报告消费）；真实 PE/PB 估值分位、质量因子与 LLM 注入属后续阶段（见 `docs-stm/plan/financial-indicator-source-design.md` §13）。

### 测试用例审计与修复（rf-365）（2026-09-14）

- **审计口径**：333 个测试文件（`src/test/unit|scenario|integration`，`live/` 为 opt-in 排除）AST + 收集器全量扫描，按「无效（名实不符且无断言）/ 死（空体、同类重名、未收集）/ 冗余（AST 完全相同、同类同函数号）/ 目录语义（导入包 vs 目录期望）/ 命名与内容」五维盘点。
- **官方门禁**：`check-test-markers.py --ci` 通过（无漏标、无 `_edge.py` 混放、无失效标记）；无无条件 `skip`；无同类重名；`live/` 未收集属 opt-in 设计而非死用例。
- **修复（rf-365）**：6 例无效用例补真断言（`test_set_write_error_logged` 断言告警内容；`test_llm_api_base::TestLogTokenUsage` 4 例改 `assertLogs/assertNoLogs` 断言输入/输出/缓存命中并补 empty 分支；`test_handlers_cache::TestCmdCleanupCache` 2 例断言委托调用与等待按键；`test_html_report_structure_edge` 断言 2 处导航锚点模板）；删 1 例空体死用例；删 `test_llm_utils::TestLogTokenUsage` 冗余类（与 api_base 重复）；`git mv` 分类测试至 `unit/core/` 并改标 `unit_core`。新增回归守护 `test_test_quality_regression.py`（静态禁止空测试体）。
- **保留（有意）**：18 例「不抛异常/no-op」弱断言测试（如 `SilentProgressReporter` 四个 no-op、空范围 no-crash、live 录制辅助）经逐例审阅为有意边界覆盖，不强制补断言；`unit/core` 与 `unit/cache` 的缓存测试拆分、`unit/analysis/test_bond_yield*` 走 fetcher 网关两处目录语义为历史布局，已记录待后续评估。
- **统计刷新**：`folders.md`（测试代码 364/106,414、测试用例 6,991）与 `test-coverage.md`（bench 回填模式表 + 收集分组：报告生成 1828、核心基础设施 1210、unit_llm 954、unit_scripts 204、跨类 llm 750）同步。

### bench 全量计时与 integration 契约修复（rf-364）（2026-09-14）

- **bench 全量跑**：`test-runner.py --mode bench --update-docs` 依次跑 14 个模式并回填 `test-coverage.md`（模式对应测试量 + 采集环境属性 + 各模式耗时对照，dragonball 采集日期 2026-09-14）。本机各模式耗时（worker=8）：unit ~17s / standard ~18s / scenario ~20s / dev-verify ~27s / verify ~15s / integration ~19s / edge ~14s / all ~26s。
- **暴露并修复真实回归（rf-364）**：bench 的 `all` / `all_no_unit` 报 2 例失败——`test_report_chapter_consistency.py` 的「全开」镜像未带新章节 `financial_report_digest` 的 board/data 参数（Excel 少一页签、HTML 该章节不可见）。该套件为 `integration` 标记、不在 dev-verify 门禁内，故此前未暴露。修复：为 `_excel_visible` / `_html_visible_keys` 与两个 all-enabled 用例补 `financial_report` 开关与 `financial_report_digest_data` 参数，并在「全开」场景显式启用。
- **复跑**：`--mode all` **6982 passed / 0 failed**（含 12 skipped）；`test-coverage.md` 散文字面日期（两处采集说明与示例耗时）同步为 2026-09-14。

### 数据源与统计快照刷新（datasource.md / folders.md / test-coverage.md）（2026-09-14）

- **datasource.md**：DataSinking 行补两级缓存前缀（`report_datasink_index_` 两周 / `report_datasink_doc_` 一月）；新增「财报全文（DataSinking）」路由小节（鉴权/取数/限速配额/仅 A 股符号映射）；数据质量说明与常见问题各增一行。
- **folders.md**：统计表按实测刷新（主程序 276 文件/68,852 行、HTML 模板 5/3,999、测试代码 363/106,356、测试用例 6,994、用户文档 11/5,114、项目文档 133/51,292、代码合计 305/80,340），主程序说明补 5 个新模块；目录树经校已含全部新文件。
- **test-coverage.md**：收集快照同步（功能域与单元分组：数据源 Provider 303 / 数据获取调度 371 / 报告生成 1861 / 核心基础设施 1178 / unit 父标记 6681 / unit_scripts 203；报告测试文件 89），源模块清单补 `datasink` / `financial_report` / `report_adapters` / `financial_report_digest` / `financial_report_sheet`。计数以 `scripts/collect-test-coverage.py` 实时输出为准。

### 过去 96 小时实现审计整改（技术债 + 文档漂移，rf-358~rf-362）（2026-09-14）

- **代码债**：删除 `providers/datasink.py` 的两个新增即死函数（`fetch_report_sections` / `quota_remaining`，仅定义+单测、无生产消费者）；`datasink.sections` 由「列表只取首项」改为**多章节顺序拼接**（逐章节取正文、每节独立缓存、空行分隔）；数据源说明表的前缀改从 `_SOURCE_CATEGORIES` 派生（`_CATEGORY_PREFIXES`）、计费文案改由 provider 新增 `billing_description(plan)` 生成（数字同源 `_PLAN_LIMITS`），消除前缀/套餐数字两处重复。
- **文档漂移**：DataSinking 接入后「全部数据源免费、声明表为空」描述已过时——同步修正 `core/datasource_credential.py` 模块 docstring 与注释、`config/features.py` 开关注释/描述、`core/doctor.py` 与 `core/check_sources.py` 回退文案、`technical.md` §2.7（标题由「实验：默认关」改「常规开关默认开」+ 正文补密钥文件/节名）、`requirements.md` §5.8（R-CRD-01/02/03/06/07 补 `key_file`/`key_field`/`key_section` 与解析顺序）、`how-to-config.md` 两处；对应 3 个测试断言文案同步。
- **用户文档与覆盖**：`README.md`「最多 19 个条件页签」→ 20 并补「财报摘要（可选）」与 DataSinking key 说明；`testplan.md` §4 增财报取数 P1 回归行；`technical.md` 增 §4.19「持仓个股财报摘要」叙述章节。
- **门禁**：dev-verify 全绿；四个 `--ci` 检查 exit 0；ruff check + format 零告警。自审记录 rf-358~rf-362（`rf-next` 363）。
- **任务编号纪律收紧（rf-363）**：`check-code-traces.py` 原先在 `src/test/` 对「回归…」整行与「rf-N 修复」两条予以豁免，使测试注释/docstring 可残留任务编号（共 7 处）。现改为 **任务编号硬禁止且先于整行豁免判定**（`scan_file` 用 `_TASK_ID_RE` 检出 rf-/plan-/R- 编号即报 CODE），删除 `TEST_META_EXCLUDE` 的 `rf-…修复` 条；7 处测试注释/docstring 清理为纯回归语义措辞；检查器测试同步（+2 例硬检出、改写 1 例豁免断言）；CLAUDE.md 补注「测试元描述豁免不适用于任务编号」。

### 修复：QDII 联接穿透被旧缓存遮蔽 — 持仓缓存载荷语义版本（rf-357）（2026-09-14）

- **背景（用户报障）**：另一台机器运行报告仍报 `016055` / `040046` 持仓报告期陈旧（`2023-09-30` / `2022-12-08`）、已按持仓不可用处理、未计入穿透 TOP10。定位于 v0.10.18 的 QDII 联接穿透修复（`d02e32e0`）**只改代码、未让旧缓存失效**：修复前写下的 `fund_hold_*` 条目无 `feeder_target_code`，新代码读到时无法穿透，旧载荷「有持仓 + 早期报告期」直接撞上时效闸门——`hold` TTL 为 7 天，旧条目过期前修复被全程遮蔽（提交当时已注明「需立即见效时 `--clear-cache`」，但该依赖用户手动，属真实缺口）。
- **修复（语义版本 + 读侧准入）**：provider 产出经 `fetcher/fund.py::_stamp_hold_schema` 盖 `hold_schema` 版本字段；读取侧以 `_is_current_hold_payload` 为准入判据，版本不符视为未命中。判据接在**两处**读缓存接缝：① `fetcher/chain.py::fetch_with_fallback` 新增 `cache_validate` 参数（覆盖新鲜命中与过期降级条目，不符即清缓存重取）；② 批量预检回调 `_hold_cache_check`（`execute_with_cache_check` 命中会跳过任务，判据若只挂在链路内则热缓存下失效）。顺带移除 `fetch_fund_holdings_batch` 内冗余的局部 `cache_get`/`get_ttl` 导入（模块顶部已有，局部导入使与 `fetch_with_fallback` 的 `cache_validate` 无法在测试中一致打桩）。
- **效果**：此类「改变载荷含义、不变键结构」的修复从此自失效，不再依赖用户手动清缓存；另一台机器 `git pull` 后首次运行即自动丢弃旧条目并重取。
- **回归测试**：`test_chain.py` 增 3 例（准入判据放行/拒收旧载荷并清缓存重取/拒收旧语义过期降级条目）；`test_fund.py` 增 `TestHoldPayloadSchema` 5 例（盖章、判据准入、旧载荷重取并盖章、当前载荷命中不重取、批量预检拒收旧载荷）。fetcher 两文件 89 passed / 0 failed。
- **文档**：`technical.md` §4.9 补「持仓缓存载荷语义版本」机制、§6.7 语义命名表增 `hold_schema` / `cache_validate` 两行、§8.2 补「缓存载荷语义版本」词条外设计规则；本 changelog 与 `review-findings.md` rf-357。

### 项目级 pi 配置入库（`.pi/settings.json`）（2026-09-14）

- 新增 `.pi/settings.json` 并纳入版本控制，压掉更新日志面板的启动期闪屏：`collapseChangelog: true`（What's New 面板折叠为一行）、`quietStartup: true`（隐藏启动 header）、`tuiMode: "fullscreen"`（viewport 由 pi 自持，避免终端 scrollback 大段重排）、`terminal.clearOnShrink: false`（保留默认；文档标注其可致闪屏）。
- **生效前提**：`.pi/` 属「需信任的项目资源」——首次启动会要求信任该项目，未信任时整份项目设置被忽略（回退全局）；`/settings` 面板切换写的是全局设置，仅本文件为项目级。`--tui-mode` 启动参数优先级最高，会盖掉本设置。
- `folders.md` 目录树同步新增 `.pi/settings.json` 条目。

### 发布后自查整改：多币种换算口径校正 + 脚本约定守护（rf-354 ~ rf-356）（2026-09-13）

- **背景**：发布 v0.10.19 后复盘近 96 小时的实现，发现三处遗留债——一处是 rf-350 明确标记「待用户确认」的能力口径失配，两处是脚本约定只写在文档、无任何校验环节。
- **rf-354 多币种换算口径校正（按实现改写文档与测试，不新增汇率功能）**：`faq.md` 原称「港股通和非 A 股品种的汇率换算由数据源接口自动处理」；`testplan.md` 的 T8 场景列「美元份额币种转换」、T19 场景为「汇率中间价故障」、数据正确性验证表列「多币种转换正确：美元份额 × 汇率中间价 = 人民币市值 ✅」；测试侧 `test_data_integrity.py` 第 4 项与 `TestMultiCurrencyConversion`、`test_market_value.py::TestCurrencyConversion` 亦按汇率换算命名。核对实现：**全仓无任何汇率取数或换算**——`get_currency_by_code` 只做币种分类（5 位纯数字→HKD、QDII/海外基金/美股指数→USD、其余→CNY），`fx_exposure.py` 只按币种汇总市值与占比，`market_value.py` 无汇率分支，QDII/场外基金的净值本身即以人民币计值（相关断言为 100 份 × 2.5 = 250.0），情景分析的「汇率情景」是假设 ±5% 对非人民币占比的估算。处置：四处口径按实现改写（`faq.md` 明确「程序不做汇率换算」并补币种分类规则与港股通换汇成本提示；`testplan.md` T8 删跨境币种换算、T19 改为真实且已覆盖的「场外品种净值日期非 T 日」场景、数据正确性表该行改为「非人民币计价品种市值核算（价格 × 份额，不做汇率折算）」并补 `test_market_value.py` 载体；两个测试类更名为 `TestForeignDenominatedMarketValue`，docstring 改述实现，**断言不变**）。需求 §6.10 只承诺「币种判定 + 市值占比 + 标注 + 注入」，与实现一致，未改。
- **rf-355 `scripts/*.ps1` 行尾归一 + 回归守护**：`cli.ps1`、`launch.ps1` 为 UTF-8 with BOM 但**通体 LF**，与 `.editorconfig` 的 `[*.ps1] end_of_line = crlf` 及 CLAUDE.md 的「BOM + CRLF」约定不符（新写的 `llm.ps1` 反而合规）——两文件行尾归一为 CRLF（BOM 保留）。
- **rf-356 `scripts/*.sh` 可执行位入索引 + 回归守护**：仓库 `core.fileMode = false`，工作区权限不被跟踪，`cli.sh` / `launch.sh` / `llm.sh` 在索引中均为 `100644`——新克隆的仓库里 `./scripts/llm.sh` 报 permission denied，而 CLI 手册 / 开发者指南 / 变更记录均按可执行方式调用（且声称「llm.sh 置可执行位」）。处置：`git update-index --chmod=+x` 将三个 `.sh` 的索引权限置为 `100755`，`llm.sh` 工作区权限由 777 归为 755。
- **回归测试**：新增 `src/test/unit/scripts/test_script_encoding.py`（`unit_scripts` 标记，4 例）——`scripts/*.ps1` 逐文件断言以 BOM 开头且不含裸 LF（无 BOM 时 Windows PowerShell 5.1 按 GBK 误读中文注释而解析崩溃）；`scripts/*.sh` 断言 git 索引权限为 `100755` 且工作区可执行（非 git 工作区 / Windows 自动跳过）。

### 开发版本切换（2026-09-13）

- 发布 v0.10.19 后，按既定流程将 `APP_VERSION` 与全部管理文档版本头切换至 v0.10.20-dev，`check-version-consistency.py` 全链 [OK]。

### 已发布版本变更记录归档（v0.10.19 → archived_changelog）（2026-09-13）

- **归档**：发布 v0.10.19 后，按「已完成即归档」口径将本文件 [0.10.19] 已发布版本变更记录整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（接于 [0.10.18] 之后，保持版本升序）；本文件自此仅保留在开发版本 [0.10.20-dev] 的章节与归档引用。
- **同步**：归档文件头部「涵盖版本」扩至 v0.10.1 ~ v0.10.19、「归档内容」改指开发版本 [0.10.20-dev]；`folders.md` 项目文档/归档统计按实测刷新。
- **口径**：发布版本与开发版本分开存放——已发布版本的完整变更记录只在归档文件，本文件只描述尚未发布的工作。

## 归档

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
