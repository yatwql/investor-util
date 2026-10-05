# 变更日志归档 — v0.12.x

> 归档时间：2026-10-03（v0.12.1 发布当日并入，0.12 系列首份）
> 原始文件：`docs/managements/changelog.md`
> 涵盖版本：v0.12.1（2026-10-03）
> 归档内容：v0.12.1 已发布版本变更记录（报告目录动态分组与「附录」组、LLM 章级开关整章隐藏、历史章默认折叠、版本演进对照双断言 evolution_head / release_tag、仓库目录更名、rf-557 ~ rf-562 修复与过期残留整改）

---

## [0.12.1] - 2026-10-03

### Added
- **报告章级 LLM 开关**：`llm_settings.json → enabled_llm` 禁用的分析模块（全球政经局势/智囊团深度复盘/持仓体检/穿透深度）在 HTML 章节与 Excel 页签**整章隐藏**（原仅跳过生成、章节仍保留「待生成」占位），后续章号连续递进；判定集合 `LLM_MODULE_GATED_SECTIONS` 单一来源，两端同调 `get_llm_chapter_disabled()` 同配置同逻辑推导；新闻关联（LLM 仅二次增强）与 API 用量章不受章级影响；用户手册「章节可见性规则总览」与需求 R-LLM-02 同步补章级隐藏语义（章号连续递进不跳号）
- **报告正文大块默认折叠**：「组合历史走势与回撤」章内容默认收起，提示条显示累计收益/最大回撤/年化波动摘要；原生 `<details>` 键盘可达，新增 `fold.js`（锚点定位与打印自动展开、打印后恢复，beforeprint 以捕获阶段先于图表快照展开并同步 resize），打印稿不显示提示条
- **版本演进对照可标注发布 tag**：`check-doc-traces` 豁免上下文锚定的「最近（一次）发布 tag + 版本号」行（与日期同为随发布重跑刷新的滚动读数，属当前状态），行中版本号叙述（如"该功能在 vX.Y.Z 引入"）仍检出
- **版本演进对照「当前开发版」列标注版本号**：表头列头补版本号 + 更新时间（与「最新发布」列的 tag + 时间对称）；`check-version-consistency` 新增 `evolution_head` 断言，锚定列头版本号与 `APP_VERSION` 同步（与文档版本头双点校验，发版漏改即报错，`--fix` 可自动同步）；`doc-traces` 同步上下文锚定豁免，行中版本号叙述仍检出。同表「最近发布 tag」列（表头 + 说明行全部出现处）新增 `release_tag` 断言，与 changelog 头部「最近发布 [X.Y.Z]（日期）」**发布指针**比对（changelog 为发布记录单源，`--fix` 自动同步，发版后发布列静默过期即报错）

### Changed
- **仓库目录更名**：`docs-stm/` → `docs/`，全部引用同步更新（管理/用户/归档文档、守护与测试脚本、pyproject ruff 排除、.gitignore、CLAUDE.md、githooks 钩子）——目录树、守护路径断言、文档链接校验与版本一致性检查全部跟随新路径

### Fixed
- **报告目录展开序与正文线性序不一致**：目录分组由固定组序改为「按报告号线性序扫描、同组连续段聚块」（跨组插号时组在号序断点拆块、同组可多块，如实反映线性序），分组映射按注册号段归组（数据源可用性矩阵/持仓基本面/LLM API 用量归入新增「附录」组），展开后严格 1..N 与正文（flex order = 报告号）逐位一致，消除「3→15→4」跳号回跳；`report_section_order` 自定义（含跨组交错场景）全程自适应（兼容报告序号可配置机制）
- **实现与文档过期残留整改**：导航分组「五组」注释四处（实际六组含「附录」）、技术设计文档 JS 资产段旧名与旧计数（`_JS_ASSETS`/8 个 → `JS_ASSETS`/9 个含 `fold.js`）、test-coverage 计数六处未随新增用例刷新——注释与描述改齐、`collect-test-coverage` 全量回填对齐
- **测试质量**：JS 资产清单由两函数局部元组收敛为模块级 `JS_ASSETS` 单一来源（测试同源派生）；打印隐藏断言改为跨全部 `@media print` 块查找（不依赖块出现顺序）；章号/分组断言补「展开严格连续 1..N」结构不变式

## [0.12.2] - 2026-10-04

### Added

- **基金申购限购信息接入（`plan-72` 迭代 1~3）**：天天基金申购状态总表全量取数（直连解析 + akshare 备链 + `purchase_schema` 载荷准入 + 会话复用单次经链），持仓明细市值明细末列「申购状态」条件列（限大额日限额/暂停申购下一开放日，Excel 与 HTML 单源文案）+ 双端口径脚注（天天基金渠道口径）与按交易日历的 ≤3 / 4~7 / >7 交易日三档时效标注；功能开关 `fund_purchase_limit`（默认开，注册表报告组），数据全链失败 `available=False` 时静默隐列、四层降级不阻断报告生成（设计文档 `docs/archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-design.md`）
- **申购限购约束块接入全部 LLM 分析章（`plan-73` 四迭代）**：单源渲染器 `build_purchase_constraint_block`（契约条件字段 `constraint_block`，准入四条任一不过 → 空串，行序 = 持仓序、字段值与单元格同源）→ `generate_all_llm` 提取同一实例交标准模式四模块统一 prompt 附录第 4 段（`_build_prompt_appendix` 组装守卫「任一段非空即返回」，缺省与空块逐字节一致）+ 指纹输入字段 `purchase_block` 条件并入（进提示词必进指纹，接线前录制四模块基线防分隔符换哈希）+ 辩论 pro/con/synthesis、生成后自检、新闻批量 hooks（批量提示词拼块 + `holdings_fp` 指纹并入逐级影响逐条缓存键）同源接线，6 函数透传链单测覆盖；both/basic/What-if 取契约路径块恒空零开销，降级态提示词与缓存键双不变（设计文档 `docs/archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-llm-context-design.md`）
- **What-if 目标持仓申购受限提示（`plan-74` 四迭代）**：受限标的预格式化索引 `restricted_index`（契约条件字段，与单元格同源格式化，编排层注入 + What-if 路径单点挂载）+ 申购可行性判定 `evaluate_purchase_feasibility`（限大额 `ceil(金额÷日限额)` 交易日估算、超 60 交易日判不可行、暂停引用下一开放日、金额/限额未知不给天数）+ 目标持仓新增/加仓腿提示注入 `build_whatif_data(restricted_index=…)`（卖出腿不判定；条件键 `feasibility`，Excel 持仓变动明细尾部 + HTML⑦申购受限提示节）；降级态（开关关/不可用/时效超限/取契约异常）契约与输出逐字节回退现网行为，调仓建议与行动摘要零改动（设计文档 `docs/archive/v0.12.x/fund-purchase-limit/fund-purchase-limit-advice-design.md`）

- **持仓分类汇总（两端）追加「申购状态」列（plan-75）**：Excel「持仓明细与分类」区块②（持仓分类汇总）末列 + HTML 报告持仓分类表条件列——明细行经 `format_purchase_status_cell` 单源渲染（与区块①同一套判据/文案/时效原语），小计与总计行留空（非可聚合指标），与 `cost_lots` 可选列组合时保持末列次序；开关复用 `fund_purchase_limit`（`purchase_column_visible` 单源判据，不新增开关），降级（关/`available=False`）列缺席逐字节回退；口径脚注复用区块①②之间既有那一行（位置天然覆盖两块）；HTML 侧表头/明细行/小计/总计四处条件块复用同一 `purchase_status_display` 上下文（cells 取自同一文案函数，与 Excel 逐字一致，两端一致）

### Changed

- **第二轮全量文档核对（2026-10-03）两处更新 + rf-570 处置**：`faq.md` 报告理解节补「LLM 分析×限购约束上下文」问答（约束块注入面、开关回退行为、self_review 为下游独立复核不影响分析章约束——源自用户真实疑问）；`developer-guide.md` P0 门禁节补 `--sync` 统计快照口径警示（工作区 vs committed 分叉坑，rf-570 纪律条款处置）；核对结论：其余管理/用户文档与实现一致（config-llm 联动句已在模块启停节、上轮九处未回退、testplan 计数外置）
- **管理/用户文档补齐 plan-73 限购约束块消费方（rf-569，全量核对）**：`llm-technical.md` 补注入链四处（§3.2 附录图第 4 段、§4.1 提示词覆盖表 `purchase_constraint_block` 行、§4.4 `extract_purchase_constraint_block` 唯一提取点、§8.2 统一附录四段与组装守卫）；`how-to-config.md` `fund_purchase_limit` 消费方补 What-if 提示与 LLM 约束上下文（关＝三者同时失效）；`datasource-reliability` §3.11 用途句补 LLM 消费方；`how-to-config-llm.md` 模块启停节补约束上下文联动；`reports-instruction` ④节与 `README` 智囊团行补可执行性约束说明；核对结论：其余管理/用户文档与实现一致（`datasource.md` 路由表无消费方列、testplan 计数外置 test-coverage、developer-guide 现状描述准确，均无须改）
- **P0/P1 门禁并入 `unit_report` 域（rf-564 / rf-565）**：报告生成域（98 文件 / 2,120 用例）此前不在 `dev-verify`、`verify`、`verify,regression` 任何档（modes.py `report` 专用模式零调用方），What-if 页面级测试「⑦/⑧ 说明」编号漂移因此带病提交——`dev-verify`（3,638→5,454）与 `verify`（5,796→7,917）marker 并入 `unit_report`，`test-runner modes.py` 与 `collect-test-coverage.py` 双处 marker 定义同步并互注防漂移；`test_whatif_html.py` 断言与 `whatif_template.html` 编号同步（「⑦ 说明」→「⑧ 说明」+ ⑦受限节缺席断言）
- **`constraint_block` 提取收敛单源 helper（rf-567）**：编排层与新闻链两处相同的字典路径表达式收敛为 `llm.extract_purchase_constraint_block(pipeline_data)`（唯一提取点，契约键/嵌套调整只改此处，防漏改一处致块静默缺席），两侧调用同一实现并补三态单测
- 限购总表缓存显式注册进数据模块注册表（data_type `fund_purchase` + 精确键 `fund_purchase_status_table`，TTL 与官方净值同源 `CACHE_DAILY` 24h）：此前未注册、靠 `get_ttl` 回退巧合与净值同档，回退逻辑或常量一变即无声漂移；仍不入菜单刷新组（大表不随菜单强抓），`datasource.md` 脚注同步
- **限购线文档一致性核对修正**：`reports-instruction.md` 持仓市值明细 15→16 列（申购状态条件列 + 脚注/时效/降级说明）与 What-if 申购受限提示块（页签表/产物/设计边界/功能对照表 4 处）；`requirements.md` R-WIF-05 输出描述与 R-WIF-06 网络语义（what-if 默认本地计算，提示经缓存链读限购总表：命中零联网/未命中现场取一次/失败静默兜底）；TUI/CLI 手册 What-if 段同源修正；FAQ 新增「申购状态」列问答；`datasource-reliability.md` 3.11 用途行补 What-if 消费方；README What-if 特性行补受限提示

## [0.12.3] - 2026-10-05

### Added

- **HTML**：正文大块默认折叠从「组合历史走势与回撤」扩展到「财经新闻热点与持仓关联分析」「组合演进」「持仓基本面」——章标题常显、内容默认收起，提示条带该章关键摘要（新闻条数 / 快照数与观察日数 / 财务指标与财报摘标的数），点击展开/收起；原生 `<details>` 键盘可达，锚点定位与打印展开复用 `fold.js`（对全部 `details.section-fold` 生效），「回到顶部」留在折叠块外（收起态仍可点）；新增结构回归用例（默认收起 / summary 首子元素 / 标题与回顶在折叠块外 / 提示条带摘要）

### Changed

- **LLM/日志**：「要求调整配置值」的提示一律回显当前值（**rf-577**）——思考耗尽提示回显 `<config_field>=<值>`（配置上下文由 `_process_success_response` 经线程局部注入，未注入时给通用建议、不编造数值）、Thinking 安全网日志回显 `max_tokens` 与思考配置现值、截断重试耗尽回显「当前 X → 已试 Y」与配置项名；429 并发/间隔、截断检测、worker 钳位、阈值超限等既有提示本已合规，密钥类仍只给文件名/条目名（不回显本体）；排查口径与覆盖点固化到 developer-guide「日志回显纪律」节
- **LLM**：429 诊断回显补 `pacing.min_interval` 现值——「当前配置」行同时列出 `pacing.max_concurrency` 与 `pacing.min_interval`（未声明标「未配置」），凡建议「加大 pacing.min_interval」处均带当前值，读者不必翻配置即可知道要从多少调到多少
- **LLM**：429 限速日志回显**当前实际并发配置**（全局 `llm_max_concurrency=…` + `provider[条目] pacing.max_concurrency=…`），并按「还有没有下降空间」给建议——端点已配到最低 1（如 kimi-main）时不再叫用户「调低端点并发」，改为提示调低全局值或加大 `min_interval`；两级并发均到底时明确「再调低并发已无益，429 更可能来自配额（RPM/TPM）或风控」（`api_base._concurrency_hint`，新增 3 个用例覆盖三种分支）
- **LLM**：429 限速日志提示增强——除「调低 `llm_max_concurrency`」外补「或为该 provider 条目配置 `pacing.max_concurrency` 按端点限流」，把用户引到正确的并发旋钮（新增用例断言两提示同时出现）
- **文档**：`llm-technical.md` §4.2.1 补「429 诊断回显」（含 `min_interval` 与「未配置」口径）与「策略惰性装载兜底」两行；`how-to-config-llm.md` 端点级节流补 429 回显性质、思考耗尽调参建议注明「日志直接回显字段名与当前值」；`faq.md` 429 问答改按日志诊断 + 三类旋钮作答（并点明单纯增大 `timeout_{模块}` 对 429 无效）；`testplan.md` R-LLM-10 载体补 `test_llm_api_multi.py`（endpoint_key 逐层下传）与惰性装载；数据快照同步——`test-coverage.md` 经 `--mode bench --update-docs` 回填（模式对应测试量 + 环境耗时对照表 + 采集日期 2026-10-04），`folders.md` 版本演进对照「当前开发版」列按**工作区**重跑（主程序 307/80,564、测试 430/128,389、代码行合计 224,759、测试用例 8,191、仓库 1,015 文件/296,973 行，口径说明同步为工作区读数）

### Fixed

- **安全**：密钥权限基线补漏（**rf-578**、**rf-574**）——`_SECRET_FILES` 只列 `llm_key.json`，漏掉同样持密钥本体的 `data_key.json`（datasink/hithink 内联明文 `api_key`、未跟踪且实测 644 world-readable），已补入清单；两密钥文件均 `chmod 600`（`llm_key.json` 即 rf-574 待执行项，执行后基线用例转绿）；该基线在本机 bench 汇总中报失败（文件不存在时仍跳过，CI 干净检出不受影响）
- **LLM**：修复端点节流（pacing）**从未生效**（**rf-575**）——多链调用 `_call_provider_entry` 漏传 `endpoint_key`，下游 `PacingGate("")` 恒空转，`llm_providers.json` 里 provider 条目声明的 `pacing.max_concurrency`（kimi-main/kimi-code/opencode-go）全部未落到调用路径，429 提示也回显不出端点配置（只见「全局 llm_max_concurrency=3」+泛化建议）；补传条目名后，同一端点的 429 提示改推「全局/间隔旋钮」而非叫用户配一个已经配好的参数；新增 api 层下传 + 重试骨架到达两级回归用例（去掉透传即红）
- **LLM**：修复 pacing 惰性装载静默失效（**rf-576**）——`_ensure_loaded()` 引用不存在的 `src.python.config.get_llm_providers`（必然 ImportError 被 debug 吞掉、按无约束处理），改读与生产装载同源的 `get_llm_config()._provider_list`；未经配置加载的入口（单测/脚本/doctor 概览）此前一律拿不到策略
- **测试**：条件推理死测试整改（**rf-568**）——原 `test_system_debate_conditional_scenario_exists` 瞄准一个全仓不存在的预留常量 `_SYSTEM_DEBATE_CONDITIONAL_SCENARIO`，十余轮条件 skip 全绿零覆盖；经确认该预留非计划功能后，改为 `TestConditionalScenarioInjection` 4 例断言真实行为（情景 name/desc 渲染进综合/标准两条 user prompt、scenarios 为空回退基线、开关门控、`skip_scenarios` 跳过），模块 docstring 同步更正；两处注入点变异实测均拦截
- **测试**：测试有效性自查修复（**rf-571** ~ **rf-573**）——① rf-571 补 429 并发回显的 `endpoint_key` 透传接线用例（原缺口：去掉透传后 7 个 429 用例全过）；② rf-572 `test_capture_snapshot_holdings_lookup` 断言落到 `save()` 快照对象，验「无匹配时 `shares/cost_price == 0.0`」；③ rf-573 `test_capture_snapshot_data_creation` 验 `total_value/total_cost/total_pnl` 多明细求和与账户持仓清单（原均只 `assert compute.called`，与 docstring 目标不符）——三者均经变异实测确认能拦截对应回归
