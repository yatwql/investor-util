# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.2-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### plan-48 景气度框架④维场外流动性补齐（类型默认档）（2026-09-23）

**背景**：④ 流动性此前只算场内变现天数——场外品种未配置 `redemption_limits` 时一律标「需手动确认赎回上限」不计分（用户组合 4 只场外 + 6 只数据缺失），场外为主的组合该维无区分度。

**变更**：
- `core/code_utils.py`：新增 `otc_redemption_days_default`（走类型判定中心化，满足约束「类型分级须走 code_utils」）与四档常量——货币/短债 T+1、纯债 T+2、其他场外基金（主动权益/混合/指数/联接）T+3、QDII T+7（保守上沿）；无法识别返回 None
- `analysis/liquidity.py`：场外未配置赎回上限时改落类型默认档，输出新增 `estimate_basis="type_default"` 与标签「约 T+N 日赎回（类型默认档，非实测）」；配置口径优先，类型未识别才保留「需手动确认赎回上限」降级
- `analysis/prosperity_scoring._score_liquidity`：计分池扩为「场内 + 场外配置赎回上限（用户口径）+ 场外类型默认档（非实测）」，最差天数统一分档；默认档参与时 status=partial 且证据明标非实测；配置/默认档/未计入三类计数分列证据
- 文档：`technical.md`（§4.20 ④维口径）、`requirements.md`（R-LIQ-03 按实现更新）、`how-to-config.md`（字段表 + J 节）、`faq.md`（流动性问答）

**回归测试 +13**：`test_code_utils.py::TestOtcRedemptionDaysDefault`（6 例：货币/短债先于纯债/纯债/QDII/通用场外/未识别返回 None）、`test_liquidity_otc.py`（新增 `TestLiquidityOtcTypeDefaultTier` 4 例 + 既有 3 例改按新行为断言）、`test_liquidity.py` 与 `test_liquidity_otc_edge.py` 旧行为断言更新、`test_prosperity_framework.py::TestLiquidityDimension`（+3 例：默认档计入并标非实测/配置口径计入/无天数仍不计分）。

**验证**：`pytest src/test/unit/analysis src/test/unit/core/test_code_utils*.py src/test/unit/report/test_prosperity_framework_wiring.py src/test/scenario/basic/test_scenario_prosperity_framework.py` → 1011 passed。

### plan-47 基金重仓股 ROE 加权（景气度框架②维基金层扩展，阶段一）（2026-09-23）

**背景**：② ROE 低位弹性此前只覆盖 A 股直接持仓，基金/ETF/QDII 无个股 ROE 只能标「需核实」不计分（用户组合实测仅 ~22% 权重被覆盖）。按用户确认的两阶段方案，本项交付阶段一（前十大重仓口径）；阶段二（全量持仓）待 plan-51 阶段 3 收尾后升级，契约以 `basis` 字段区分口径。

**变更**：
- 新增 `report/fund_roe_estimate.py`：`estimate_fund_roe_batch`（基金持仓批量取数复用 `fetch_fund_holdings_batch`、个股 ROE 复用 `fetch_latest_indicator` 链路含缓存/降级，不新增 HTTP 通道；报告期陈旧闸门与穿透层同口径）+ `weighted_roe` 纯计算；`known_roe` 命中免取数
- `analysis/prosperity_scoring._score_roe`：新增可选入参 `fund_roe_estimates`，无直接 ROE 的权益类基金以推演值计分；证据/持仓视角备注/契约 notes 三处标「按框架推演」（红线②）；直接 ROE 优先不被覆盖
- `analysis/prosperity_framework.build_prosperity_framework_data`：新增 `fund_roe_estimates` 关键字入参与持仓视角推演标注（`_holdings_view` 增 `estimated_codes`）
- `report/_report_aux_metrics.compute_prosperity_framework_data`：编排层按 `classify_penetration` 预筛权益类基金后估算，失败降级为 None（②维退回个股口径）
- 文档：`technical.md`（§4.20 维度表与数据流 + 附录 H 契约 + 语义命名表新增 `estimate_fund_roe_batch`/`fund_roe_estimates`）、`folders.md` 目录树

**回归测试 +14**：`unit/report/test_fund_roe_estimate.py`（11 例：加权纯计算 3 + 编排 8——正常估算/known_roe 免取数/陈旧闸门/持仓缺失/非 A 股过滤/无效占比过滤/ROE 全缺不臆造/空清单）+ `test_prosperity_framework.py::TestRoeDimension` +3 例（推演值补上基金 ROE 且三处标注推演/直接 ROE 不被覆盖/无推演值仍按缺失降级）。

**验证**：景气度相关 91 用例全过；`ruff check` + `ruff format` 干净。

### Kimi Extended Thinking 支持 + Kimi 文档全链同步（2026-09-23，rf-417 / rf-418）

**背景**（文档审计暴露）：接入 Kimi 后审计发现两层缺口——① thinking 模型名单未覆盖 Kimi：`_THINKING_SUPPORTED_PREFIXES` 无 `kimi-` 前缀，配置开启 thinking 的模块走 Kimi 时静默降级；且 Kimi K2.6 Anthropic 兼容端点**默认开思考**（实测不传参即返回 thinking 块），而「未开启时显式禁用」安全网只看 DeepSeek effort 族名单，Kimi 不在其中——关闭 thinking 的模块会白烧思考 token，极端时占满 max_tokens 无正文；② Kimi 定价/接入文档未随计价代码同步。

**变更**：
- `llm/api_base.py`：把「控制方式」（budget_tokens/effort）与「默认行为」（默认开/关思考）两个维度拆开——新增 `_THINKING_DEFAULT_ON_PREFIXES`（独立于 effort 名单显式声明）+ `_is_default_thinking_on()`；`_THINKING_SUPPORTED_PREFIXES` 加 `kimi-`
- `llm/api.py`：禁用安全网改按 default-on 判定（Kimi 开启时走 budget_tokens 路径，不进 effort 族）
- Kimi 端点三态实测验证：默认（thinking 块）/ 显式 `disabled`（HTTP 200 纯正文）/ `enabled+budget_tokens`（HTTP 200 生效）
- 文档同步五处：`llm-technical.md` 附录 B 定价表 + thinking 注入流程图（补默认开思考禁用分支与 Kimi budget 归属）、`how-to-config-llm.md` 定价表 + thinking 支持矩阵 + 新增 Kimi 接入示例（含与 Kimi Code 订阅 Key 不通用的警示）、`faq.md`/`README.md` 支持列表

**回归测试 +7**：`test_llm_utils.py`（kimi 支持判定 / kimi 非 effort / 新增 `TestIsDefaultThinkingOn` 三例）、`test_llm_api.py`（payload 级：kimi 开启注入 budget_tokens 且不发 effort / 未开启显式 disabled）、`test_llm_api_base.py`（支持名单/effort 名单 kimi 断言）。

**验证**：`pytest test_llm_utils.py test_llm_api.py test_llm_api_base.py` → 189 passed；`ruff check` + `ruff format --check` 零告警。

### LLM 用量汇总 Endpoint 主备混用标注（2026-09-23，rf-416）

**背景**（用户反馈）：切换 Kimi 为主节点后，报告「LLM API 用量」汇总的 Endpoint 仍显示 DeepSeek 端点，疑似配置未生效。排查确认配置已生效（模型列表含 kimi-k2.6），但缓存模块保留了切换前 DeepSeek 时代的调用元数据，而汇总行只显示**第一个**有值模块的端点——主备混用时无法看出谁是主。

**变更**：
- `report/llm_module_info.py`：新增 `build_llm_endpoint_display`——多端点时按 provider 链 priority 升序、主在前并标注（`https://主端点（主） / https://备端点（备）`）；端点无法映射链路时保持模块出现顺序且不标注（防误标）；`llm_config=None` 时惰性加载全局配置
- `html_renderers.py` / `excel_llm_usage.py`：两处 `next(...)` 取首端点改为复用该函数（HTML/Excel 口径一致）
- `reports-instruction.md`：用量页签 Endpoint 字段说明同步主备标注行为

**回归测试 +7**（新增 `unit/report/test_llm_module_info.py`）：空/单端点原样、主备标注、模块乱序仍主在前、未映射不标注、惰性加载不崩、重复端点去重。

**验证**：`pytest test_llm_module_info.py test_html_writer.py test_llm_session_usage.py` → 122 passed；`ruff check` + `ruff format --check` 零告警。

### 修复穿透 TOP10 占比字段名不一致导致穿透深度分析误判「占比为 0%」（2026-09-23，rf-415）

**背景**（用户报告）：报告中「资产穿透 TOP10」表格数据正常，但「穿透深度分析」章节的 LLM 文本称穿透占比为 0%。

**根因**：`report/penetration.py::_build_penetration_result` 的 top10 产出字段为 `ratio_pct`，而两处消费方误读 `ratio`（`.get("ratio", 0)` 恒为 0）：
- `llm/prompts_action.py::_build_penetration_deep_prompt`——提示词中每条穿透资产「占比0.0%」，LLM 忠实复述为穿透占比 0%（用户可见症状）
- `llm/fingerprint.py::extract_stable_penetration`——full 模式指纹的占比分量恒为 0，缓存指纹对穿透占比变化不敏感（隐性缺陷）

Excel 穿透页签与景气度评分读 `ratio_pct`，不受影响。既有测试夹具恰好也传 `ratio` 键，形成自证掩盖。

**修复**：两处改为 `a.get("ratio_pct", a.get("ratio", 0))`（契约字段优先，`ratio` 作兼容兜底）。

**回归测试 +2**（净增）：`test_llm_prompt_builders.py` 穿透明细用例夹具改为生产形状 `ratio_pct` 并断言「占比25.0%」（对修复前代码必失败）；`test_fingerprint.py` 新增 2 例——full 模式按 `ratio_pct` 提取契约 / 占比变化必须改变提取结果。

**验证**：`pytest test_llm_prompt_builders.py test_fingerprint.py` → 54 passed；`ruff check` + `ruff format --check` 零告警。

### 接入 Kimi（月之暗面）开放平台为 LLM 主节点，下架 Gemini（2026-09-23）

**背景**（部署调整）：本机部署的 LLM provider 链从「DeepSeek 主 + Gemini 辅」切换为「Kimi K2.6 主 + DeepSeek 备」，不再使用 Gemini。Kimi 走开放平台按量付费 + Anthropic 兼容端点（与 DeepSeek 主节点同一套调用路径），代码零改动即可接入；仅计价表需补充新模型费率。

**变更**：
- `core/constants.py`：`MODEL_PRICING` 新增 `kimi-k2.6`（输入 ¥6.5 / 输出 ¥27.0 / 缓存命中 ¥1.10 每百万 token）与 `kimi-k3`（¥20.0 / ¥100.0 / ¥2.00）官方费率，无峰谷子段
- `data/config/llm_providers.json`（本机部署配置）：`kimi-main`（priority 10，主）→ `deepseek-main`（priority 20，备）；移除 `gemini-fallback`
- `data/config/llm_key.json`（gitignore 不入库）：新增 `kimi-main` 凭据（endpoint `https://api.moonshot.cn/anthropic/v1/messages`），移除 `gemini-fb`
- Gemini 的 `MODEL_PRICING` 条目保留——历史报告成本渲染仍依赖其为旧调用记录估价
- 文档同步：`test-coverage.md`（unit_llm 计数与覆盖描述）、`folders.md`（统计表）

**回归测试 +3**（`test_llm_utils.py::TestPricing`）：Kimi k2.6/k3 单价锁定（1M 输入 + 1M 输出金额断言）/ 缓存命中价锁定（防止缺 `input_cache_hit` 字段回落为 input 价）/ 无峰谷加成（高峰钟点与闲时同价，与 DeepSeek 行为区分）。

**验证**：`pytest src/test/unit/llm/test_llm_utils.py::TestPricing` → 31 passed；`get_llm_config()` 链解析 `kimi-main → deepseek-main` 凭据全部可解析零告警；Kimi 端点实测 HTTP 200（`kimi-k2.6` 正常返回，thinking 模式可用）；费用估算冒烟（10 万输入 + 1.5 万输出 → ¥1.055）。

### 新增 Jev 新闻关联判定评测方案与接入设计草案（2026-09-22，plan-55）

**背景**（能力评估）：TypeSafe 发布 System One 评估模型 Jev——与语言模型不同，它不生成文本，而是接收 `state` + 类型化问项（是否概率 / 单选带分布 / 档位打分）并回结构化答案与校准置信度。经查证，其四条对外路由均无对话补全兼容面，故**不可作为对话模型接入**，仅适用于「窄判断」场景；本项目的新闻关联判定正是此类场景。

**预检结论**（回收 `data/cache/` 中 48 条既有判定得出）：
- `relevance` 已饱和——**77% 标「高」、0% 标「无关」**，无法区分对照方案；`sentiment` 才有区分度（利好 48% / 中性 40% / 利空 12%）
- 「无关」占比 0% → 关键词预筛已承担相关性闸门，**「先用判定预筛、再削减生成侧输入」的动机被证伪**
- 理由文本中位 **23 字**且全为「主体 + 方向」型 → 可由确定性模板渲染，无须为它保留生成调用

**变更**（仅文档与计划，无运行时行为改动）：
- 新增 `docs-stm/plan/jev-news-correlation-evaluation.md`——三方对照评测方案（关键词确定性 / 现网生成 / Jev），含语料构造（现场快照冻结；既有缓存因单向指纹无法回收原文）、盲标协议、指标（主指标取 `sentiment`，含 Brier 与期望校准误差）、预注册判定阈值、脚本落点与复现步骤
- 新增 `docs-stm/plan/jev-news-correlation-design.md`——接入设计草案：独立于对话链的类型化判定通道、问项版本参与缓存指纹、类型化通道下五个无意义配置键不读取、失败降级矩阵、模板理由渲染
- `plan.md` 登记 `plan-55`（含三条预检约束与五条红线），`plan-next` 递增至 56
- `folders.md` 同步目录树与统计表

**未决**：评测本身尚未开跑，前置为 Jev 凭据（直连为 waitlist，可经聚合网关复用既有凭据）与 40~60 条人工标注金标准。未达预注册阈值则归档为「已评估未采纳」。

**口径确认**：`docs-stm/plan/` 的在办设计文档为**扁平文件**（目录树统计以 `glob` 而非 `rglob` 口径核对），完成后才移入归档的主题子目录。

**验证**：`check-doc-drift` / `check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-test-redundancy` 六个 `--ci` 脚本全 [OK]；`ruff check` + `ruff format --check` 全绿。

### 跟进 DeepSeek 计费规则调整：法定节假日全天闲时 + V4 Pro 继续服务（2026-09-20）

**背景**（外部规则变化）：DeepSeek 官方 2026-09-10 定价页更新峰谷计价口径——高峰时段为北京时间周一至周五（**不含中国法定节假日**）9:00–12:00、14:00–18:00；其余时段（含周末与**法定节假日全天**）均为空闲时段。同批 change log 还宣布 V4 Pro 在 2026-09-14 之后**继续提供 API 服务**（此前曾计划下线）。项目原先只实现了「周末全天闲时」，且注释误记 V4 Pro 下线。

**变更**：
- `core/constants.py`：新增 `PRICING_HOLIDAY_ALWAYS_IDLE`（默认 True）；峰谷时段注释更新为「高峰日 = 周一至周五且非法定节假日」；更正 V4 Pro 注释为继续服务、计费不变
- `llm/pricing.py`：新增 `_is_holiday`（复用 `core/trading_calendar._is_trading_day` 判定工作日但非 A 股交易日）、`_is_idle_day`（周末/法定节假日，各受 `weekend_always_idle` / `holiday_always_idle` 开关控制）；`_is_peak_minute` 参数由 `weekend` 改为 `idle_day`；`reload_pricing` 增加 `holiday_always_idle` 解析
- `config/_llm_settings_defaults.py`：pricing 段新增 `holiday_always_idle: true` 及注释
- 文档同步：`llm-technical.md`（§10.4 峰谷定价 + 附录 B 定价表与说明）、`how-to-config-llm.md`（pricing 字段说明 + DeepSeek 注意事项 + 峰谷定价说明 + 费用估算示例）

**回归测试 +5**（`test_llm_utils.py::TestPricing`）：法定节假日闲时默认开 / 高峰钟点按闲时价 / 缓存命中按闲时价 / 普通工作日（交易日）仍按高峰价 / `holiday_always_idle=false` 恢复峰谷——法定节假日判定 mock `trading_calendar._is_trading_day`，不触发真实网络。

**验证**：`.venv/bin/python -m pytest src/test/unit/llm/test_llm_utils.py::TestPricing` → 28 passed / 0 failed；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-doc-drift` / `check-test-redundancy` 六个 `--ci` 脚本全 [OK]；`ruff check` + `ruff format --check` 全绿。

### 修复 LLM thinking 预算兜底方向写反（2026-09-20，rf-379）

**背景（自审待核类问题，已解决）**：`_resolve_thinking_budget` 的兜底方向存疑——旧实现把「budget 不足 `max_tokens + 1024`」视为不足并**提升到 `max_tokens + 4096`**，导致实际发送 `budget_tokens > max_tokens`。本次查证 Anthropic / Gemini 官方约束后确认方向写反。

**官方约束**：
- **Anthropic**：`budget_tokens` 须 **< `max_tokens`**（思考 token 计入 max_tokens 共享预算，须为最终回答留空间），且最小值 1024（仅 interleaved thinking 可例外，本项目不用）。
- **Gemini**：`thinkingBudget` 为软上限，但 `maxOutputTokens`（= max_tokens）是硬截止，思考 token 计入；若 `thinkingBudget ≥ maxOutputTokens`，推理时触发 `finish_reason=MAX_TOKENS` 且正文为空。
- **DeepSeek（主用）**：走 `reasoning_effort` effort 档（`deepseek-flash` / `deepseek-v4-` / `deepseek-chat` 命中 `_THINKING_EFFORT_MODEL_PREFIXES`），**不发送 budget_tokens**，故本缺陷不影响 DeepSeek 主路径。

**变更**：
- `src/python/llm/api.py::_resolve_thinking_budget`：兜底条件由 `budget < max_tokens + 1024` 改为 `budget ≥ max_tokens`（含缺失），兜底值由 `max_tokens + 4096` 改为 `max(1024, max_tokens − 2048)`（保证 ≥1024 且 ≤ max_tokens − 2048，正文留 2048 余量）
- 同步 `docs-stm/manuals/how-to-config-llm.md`（参数表 + 「thinking_budget 与 max_tokens 的关系」章节）与 `docs-stm/managements/llm-technical.md`（Claude/Gemini 两处注入流程）
- 回归测试 +5：`test_llm_api.py` Claude 3 例（兜底 1024 / ≥max_tokens 回落 / 合法值保留）+ Gemini 2 例（≥max_tokens 回落 / 合法值保留）

**验证**：`.venv/bin/python -m pytest src/test/unit/llm/test_llm_api.py` → 32 passed / 0 failed。

### 补充 rf-113 / rf-257 浏览器人工验收清单（2026-09-20）

**背景**：rf-113（Chart.js 图表浏览器验证）与 rf-257（Web 模式浏览器验收）是两项**只能真实浏览器/真机人工走查**的遗留待办（均无法用自动化脚本替代）。rf-113 已有旧清单但存在与当前实现的偏差；rf-257 长期只有模糊的「对照 plan-web-ui.md 验收标准」而无落地勾选清单。本次补齐二者载体并勘误。

**变更**：
- **rf-257 新增勾选清单**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`——从实际 `index.html` 七卡结构（①上传 ②生成 ③配置编辑 ④进度 ⑤结果 ⑥运行状态 ⑦日志）+ `how-to-use-web-mode.md` 手册 + `plan-web-ui-implementation.md` §10/§6.5/§6.6 验收标准导出 ①~⑤ 五类 UX 项（页面渲染 / 上传表单 / 进度可视化 / 375px 响应式 / 按钮态），每项含可勾选细项 + 逐步操作步骤 + 明确判定标准；`review-findings.md` rf-257 条目补指向该清单的引用，验收标准源由笼统的 `plan-web-ui.md` 修正为 `plan-web-ui-implementation.md`
- **rf-113 清单勘误**：`iter7-verification-checklist.md` 的 5 处场景参数名错误——`test-chart.html?场景=ok` / `?场景=离线` 修正为 `?s=ok` / `?s=offline`。根因：`test-chart.html` 的 `getScenario()` 只读 `?s=` 参数（合法值 ok/degraded/empty/offline），中文字参数不报错但实际无效（非法值 fallback 到 ok），其中 `?场景=离线` 会让用户验证不到离线守卫逻辑，属必须修复的误导

**其余核对**：rf-113 清单的其它断言仍与当前实现一致——`enable_interactive_charts` 默认开（`True`）、6 图清单（`portfolio_line/drawdown/category_doughnut/industry_bar/penetration_bar/radar`）、回撤图 span ≥ 60 交易日（`DRAW_DOWN_MIN_SPAN`=60）才渲染、7 JS 资产 + chart-common.js 依赖、`drawSimpleChart` + Canvas 回退路径仍在（对应 rf-114「先验 rf-113 再删旧路径」的待办）。

### 修复 full 路径 HTML 漏接市场情绪契约（2026-09-18，rf-402）

**背景**（用户反馈）：「同花顺，市场情绪没开启么？我看数据可用性矩阵没提到它」。排查确认**开关与 key 均无问题**（`features.json` 已开 `market_sentiment`、hithink key 就绪、`data/cache/sentiment_*` 本次已由同花顺接口刷新），而是 full 路径的 HTML 端接线遗漏。

**现象**：同一次运行的两份产物自相矛盾——xlsx「15.数据源可用性矩阵」有 `市场情绪 | ✅ 正常 | 同花顺金融数据 ×2`、说明表「✅ 已使用」；HTML 两者皆无（矩阵缺该行、说明表「○ 未使用」），情绪区块也不渲染。

**根因**：`report/_report_generation.py::_generate_report_full` 未取数/未注入 `market_sentiment_data`，且 `_generate_full_html_report` 无该形参、其 `write_html_report` 调用未传参；Excel 侧靠 `report/excel_generator.py` 的「就地兜底」在 **HTML 落盘之后**才触发取数（`logs/app.log`：HTML 20.126 → 情绪取数 20.419/20.799 → Excel 21.032）。矩阵只列**本次取用过的类别**，故取数前生成的 HTML 自然缺行。

**变更**：
- 编排层在写 HTML 之前取数并注入 `pipeline_data`（位置与 both 路径一致：`record_prosperity_diagnosis` 之后、`# ── 6. HTML 报告 ──` 之前），并透传 `prep` 以带出穿透标的（与该路径 Excel 的穿透口径一致）
- `_generate_full_html_report` 新增 `market_sentiment_data` 形参并透传 `write_html_report`（HTML 与 Excel 从此同源同序）
- Excel 就地兜底保留（basic 路径不经编排层；注释「full/both 由编排层注入」自此属实）
- 回归用例 2 例（`test_market_sentiment_wiring.py::TestFullPathInjection`：编排注入 / HTML 生成器透传），已实测对修复前代码两者均失败

**验证**：修复前后各跑一次两例（修复前 `assert None is {...}` / `TypeError: unexpected keyword argument` 失败，修复后通过）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 四个 `--ci` 脚本全 [OK]。

### 文案与实现对齐：市场情绪块的描述口径 + 报告组开关计数（2026-09-19，rf-403、rf-404）

**触发**：用户追问「情绪价值会出现在报告的哪个部分？我没看到」。实测确认区块已正常出现（HTML 行动建议章 ⑦ 号内嵌块 / Excel「7.行动建议」页签），只是当日 0 命中——而两份手册恰好把这种情况写反了，所以先修文档。

**两类文案与实现不符**：
- **位置**：`features.py` 的 `market_sentiment` 开关描述写「**新增独立章**」（初稿形态），实际是行动建议章内嵌块——该偏离在设计文档归档里已记录，只是开关描述未随之更新；它恰是功能开关面板/菜单里展示给用户的文字
- **零命中行为**：`data_source_matrix.py` 说明表、`how-to-config.md`、`datasource.md` 三处写「**无命中时该区块不显示/不渲染**」，而实现是**零命中仍渲染**（标题 + 市场概览 + 「（当日无持仓/穿透标的命中龙虎榜或连板梯队）」+ 口径脚注）——两句话叠加，正好把“功能正常、只是无事件”误读成“没开启”
- **报告组开关计数**（rf-400 同类漏改）：`how-to-use-tui-menu.md`（共 29 项 / 报告组 8 项 + 两处清单漏 `market_sentiment`）、`how-to-config.md`（子模块枚举漏）、`folders.md`（28 项 / 8 项）——实况 **30 项（⚗5 / 常规 16 / 报告组 9）**

**变更**：四处描述口径按实现改正（并把“怎么排查是否已取到数”写进手册：矩阵「市场情绪」行 + 说明表「本次使用」+ `logs/app.log` 的 `[market_sentiment] 命中 N 条`）；四处计数/清单按 `feature_switch_registry` 实况更正并补 `market_sentiment`。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 文档与实现全量核对：4 类共 28 处不一致修订（2026-09-19，rf-405~rf-408）

**触发**：用户要求「核对管理文档和用户文档，比对程序和配置文件，查看有没有不一致的地方，要修订」。

**核对口径**：以注册表（`feature_switch_registry` / 章节注册表 `_REPORT_SECTION_DEFAULT` / 数据模块缓存注册表）、`data/config/config.json` + `_DEFAULT_CONFIG`、文件系统、`pytest --collect-only`（`scripts/collect-test-coverage.py`）为事实源，逐条比对 11 份用户文档（README + manuals 10）+ 10 份管理文档。审计脚本（`docs-stm/tmp/audit_phase{1..7}.py`，gitignore）按「提取代码侧事实 → 反向扫文档断言」两面跑。

**修订四类**：
- **统计快照过期（rf-405，12 处）**：`test-coverage.md` 的 unit/standard/all/report/unit 父标记/unit_report/功能域「报告生成」与实测差 2（rf-402 新增的回归用例未回填）；`folders.md` 的主程序与测试代码行数、测试用例数、managements/项目文档行数未随代码与文档变动刷新（含「源代码合计」联动）
- **目录树漏登 9 个文件（rf-406）**：`folders.md` 未随新增文件同步（`fetcher/financial_indicator.py` + 8 个测试文件）→ 按所属子包位置补条目并附职责说明（取自各文件 docstring）；补后重核「实际有而树内缺 0 / 树内有而磁盘无 0」
- **TUI `[S]` 面板编号表与分组实况脱节（rf-407）**：实验块只列 4 项（缺 ⚗ 景气度框架诊断）、常规块 10-25 未随实验组扩容后移、报告块未编号、三处「第 23 项」位置引用失准、`how-to-use-web-mode.md` 实验清单缺项——而编号本是 `handlers_config.py` 从分组与注册表顺序**派生**（设计上非硬编码）→ 按实况重编（实验 6-10 / 常规 11-26 / 报告 27-35）
- **零星数值/表述（rf-408，3 处）**：`requirements.md` 页签编号 1~19 与默认顺序 19 项（实况 17 个报告章节）；`technical.md` 功能语义命名表中 `market_temperature` 标为默认关（实况默认开）；`testplan.md` 「白名单 7 组」→「7 个可编辑面（功能开关面拆两块）」

**核对为一致（未改）**：30 项开关分组计数与清单、报告章节表（17 项）与 Excel sheet 名、13 份版本头（`check-version-consistency`）、`how-to-config.md` 标量默认值表与 `_DEFAULT_CONFIG`、缓存 TTL 表与 LLM 默认 `max_tokens`/`timeout`、CLI 7 个子命令、`providers/` 与数据源清单路由、测试标记与 conftest；另有 2 类扫描报警经核实为误报（`market_temperature_data` 契约名被前缀匹配、`how-to-config.md` 中非开关表被当成开关表），未改。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 新增文档与实现一致性检查脚本（check-doc-drift.py）并纳入门禁（2026-09-19，rf-409）

**背景**：前一条全量核对用的是临时脚本（`docs-stm/tmp/audit_phase*.py`），用户问「是否有价值留存」。结论：值得——这类「文档里写死的事实」属**易漂移断言**，人工穷举写法必定漏检（本次就把「返回 result（N 项）」与「`market_temperature_data` 同行内的开关默认值」漏掉了，见 rf-409），而每次漂移都直接误导读者。故常驻化为门禁脚本。

**新增 `scripts/check-doc-drift.py`（十一项检查，权威源 → 受检文档）**：
- 章节：报告章节表（`reports-instruction.md` ↔ 章节注册表，行数/序号/名称）+ 章节数量断言（`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`）
- 开关：功能开关表（`how-to-config.md` 三组区段 ↔ 注册表，含表外键与缺项）+ 分组计数断言（三组连写/单组/合计三种写法）+ 默认值断言（`` `flag` `` 后紧随「默认开/关」，不跨到相邻开关、不误匹配 `xxx_data` 形态）
- 默认值：配置标量默认值表（↔ `_DEFAULT_CONFIG`，含 bool/None/数字/路径/引号归一）+ LLM 默认参数表（↔ `_DEFAULT_LLM_SETTINGS` 与缓存 TTL 注册表）
- 结构：TUI `[S]` 面板编号连续性与分组边界（↔ `handlers_config.py` 的派生规则）+ 目录树双向比对（↔ 文件系统）+ 项目统计表（↔ 实测文件数/行数，`--with-test-count` 时再核「测试用例」行）+ 测试覆盖计数表（`test-coverage.md` ↔ collect-test-coverage 快照，同一开关）

**集成**：纳入 P0 提交前门禁与 P2 发布门禁（`CLAUDE.md` / `developer-guide.md` / `testplan.md` §6.3 同步）、`test-runner.py` 的 dev-verify preflight（与编号校验并列，约 1s）；`pyproject.toml` 补 E402 豁免（先注入项目根到 `sys.path`）；`technical.md` 的「约束外参照」新增「文档与实现一致性纪律」条；`folders.md` 目录树与统计表同步。

**测试**：`src/test/unit/scripts/test_check_doc_drift.py`（55 例，`unit_scripts`）——逐项纯函数单测（含误报守卫：相邻开关不串号、`xxx_data` 不误匹配、历史记录类文档豁免）+ 真实仓库冒烟（`run_checks()` 为空）。

**豁免面（设计声明）**：`changelog.md` / `review-findings.md`（如实引用旧数字作为变更记录）与 `docs-stm/archive/**`（版本快照）不参与计数与默认值扫描；结构型默认值（dict/list）与菜单类位置引用（「第 N 项」）不比对（前者文档以「见下节」描述，后者随分组变动属预期）。

**修正**：rf-409 两处（`technical.md` 19→17 项、`market_temperature` 默认关→默认开）；`folders.md` 新增脚本与测试文件树条目与统计刷新。

**验证**：`.venv/bin/python scripts/check-doc-drift.py --ci` → [OK]（`--with-test-count` 连 test-coverage.md 计数一并核对）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 3026 passed / 0 failed（较上次 +55，即本脚本的用例数）；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 全 [OK]。

### 修复一致性检查在 CI 上误报构建产物（2026-09-19，rf-410）

**背景**：提交 `122694d3` 推送后 GitHub Actions 的 `test` job 在 3.11/3.12/3.13 三版本全红（`format` job 通过），失败步骤为新纳入的 P0 门禁（dev-verify）。

**根因**：CI 的 P0 步骤在 `pip install -e ".[test]"` 之后运行，而 editable 安装会在 `src/` 下生成 `*.egg-info/`（该目录本就在 `.gitignore` 中）。一致性检查的目录树/统计比对把工作区所有文件都视为「应被 `folders.md` 登记的源文件」，于是把生成物报成「目录树缺条目」→ preflight 失败。本地未做 editable 安装，故「干净克隆 + 现有 venv」验证无法暴露该差异。

**变更**：新增产物判定 `_is_generated()`——按目录名（`__pycache__` / `.eggs` / `build` / `dist` / `.pytest_cache` / `.ruff_cache` / `.mypy_cache` / `htmlcov` / `test-reports`）、后缀（`*.egg-info` / `*.dist-info`）、文件名（`.coverage`）与路径前缀（`docs-stm/tmp/`）识别构建/缓存产物；目录树比对与项目统计两条路径统一排除。

**回归用例（+11）**：产物判定表（egg-info / pycache / build / dist-info / .coverage / tmp / test-reports 为产物；`core/atomic_write.py`、测试文件不是）+ 含产物的合成仓库用例（构造成员被忽略、真实文件缺条目仍报）。定位于 `TestGeneratedArtifacts`。

**本地复现方式**（供后续同类排查）：在仓库根执行 `mkdir -p src/investor_util.egg-info && echo x > src/investor_util.egg-info/PKG-INFO`，即可复现「目录树缺条目」误报；修复后同一状态下检查通过。

**验证**：`check-doc-drift --ci` → [OK]（`--with-test-count` 连 test-coverage.md 计数一并核对）；`dev-verify` → 3037 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；五个 `--ci` 脚本全 [OK]；统计快照同步刷新（folders.md / test-coverage.md）。

### 测试用例冗余与有效性整备 + 新增 check-test-redundancy.py（2026-09-19，rf-411）

**触发**：用户问询「有没有冗余的测试用例，无效的测试用例」。对 381 个测试文件 / 7,245 个用例做 AST 静态审计（并与 `pytest --collect-only` 节点比对），结论与处置：

**四类问题**：
- **完全重复 20 组**：14 组为同一被测对象同一断言（跨文件或同文件），6 组是不同 provider 解析器（`_safe_float` vs `_parse_float` 等）的**并行覆盖，保留**
- **自证用例 6 个**：`test_cache_edge.py` 的 `get_ttl` 系列把被测函数本身 patch 掉，再断言自己设的 `return_value`——断言恒真、等于没测
- **名实不符 7 例**：`test_default_true`（实际设了 `SSL_VERIFY=true`，默认分支从未被测）、`test_none_content`（传 `""`）、`test_none_returns_low`（传 `[]`）、`test_midday_145959_still_midday`（时间由 patch 决定，与 11:30 用例完全同分支）、`test_afternoon_closed_uses_long_ttl`（与午休同义）、`test_capture_snapshot_first_run`/`holding_mapping`（两者同体同断言，且后者名字声称验字段映射却只断言返回 `None`）
- **无断言 16 个**：仅「调用不抛异常」，未断言任何可观测结果

**负面结论（同样是有效信息）**：**无死用例**（无同名覆盖 / 无非 `Test` 类的 `test_*` / 无 `Test` 类 `__init__`）、**无空测试体**（既有守护生效）、**parametrize 无重复参数集**、20 个 `test/live/*` 是 `pytest.ini` 刻意排除的 opt-in 套件（非死用例）。

**处置**：跨文件重复删其一；同文件重复合并（`test_html_builders_edge` 价格变体 4→1 用 `subTest`、`test_cache_edge` 午休/收盘合并、`test_market_hours` 09:30 重复删一、`test_news_sources` 字母 token 重复删一）；6 个自证用例改为真实断言（patch 依赖、断言真 `get_ttl`）；7 例名实不符改为真跑其声称场景（含 `capture_snapshot` 映射用例改为断言传给 `save()` 的快照字段）；16 处补可观测断言（stdout 静默、错误列表、删除尝试次数、`assert_not_called`、产出文件存在等）。

**新增 `scripts/check-test-redundancy.py`（四类检查 + 误报守卫）**：死用例（不可收集/被覆盖）／无断言（含「断言落在同类辅助方法」的解析）／完全重复（去 docstring 后函数体+参数+装饰器 AST 归一化；**无法解析的 `self.<attr>` 间接调用跳过比对**，避免把并行覆盖误判为重复）／自证用例（patch 被测函数 + `return_value` 断言回原值）。纳入 P0/P2 门禁与 `test-runner.py` 的 dev-verify preflight；`developer-guide.md`（工具表 + 专门章节）、`testplan.md` §6.3、`technical.md`「约束外参照（测试有效性纪律）」、`CLAUDE.md`（P0/P2 + 独立性条目）同步；`folders.md` 目录树与统计刷新。

**验证**：`check-test-redundancy --ci` → [OK]（0 死用例 / 0 无断言 / 0 完全重复 / 0 自证）；`dev-verify` 全绿；`ruff check` + `ruff format --check` 全绿；`check-doc-drift --with-test-count` 连计数一并核对通过。

### scripts/ 优化：性能修复 + 共享模块抽取 + test-runner 拆包（2026-09-19，rf-412 / rf-413）

**触发**：用户问询「scripts 目录下的脚本有没有可优化的空间」。审计 23 个脚本（AST 克隆检测 + 真实计时 + cProfile + 调用方引用统计）。

**① 性能（P0 门禁合计 15.7s → 4.0s）**
- `check-semantic-index.py` **7.15s → 0.25s（≈29×）**：`slug_exists_in_code()` 曾对**每个 slug** 遍历全部 `.py` 并 tokenize 一次（116 slug × ~88 文件 ≈ 10,176 次全文件 tokenize；cProfile 显示 `tokenize` 占其 95% 耗时）。改为 `collect_code_texts()` 每次检查只收集一次、所有 slug 复用
- `check-code-traces.py` **4.53s → 3.32s（−27%）**：89 个模式逐行逐一匹配（3.8 万注释行 × 89 ≈ 345 万次 regex）→ 加模式编译缓存 + **并集预筛**（单次扫描判定该行是否可能命中，未命中即跳过逐一匹配；命中后仍走精确分支，判定结果不变）；标识符模式同样改为预编译

**② 共享模块（消除重复与漂移面）**
- 新增 **`scripts/_checklib.py`**：统一 CLI 契约（`add_common_args()` 的 `-v/--verbose` + `--ci`）、统一输出与退出码（`report()`：通过 0 / 发现 finding 2，`--ci` 仅输出裸描述）、`REPO_ROOT`/`rel()`、文档标记区间与表区域解析（`extract_region`/`replace_region`/`extract_table_region`/`replace_table_region`）
- 新增 **`scripts/_traces_common.py`**：两个历史痕迹检查脚本 4 个逐字节相同的函数（章节计数豁免 / 迭代轮次豁免）收拢一处；两脚本以原面 re-export + `__all__` 暴露同名符号，既有测试与调用方无需改动
- 语义命名索引、文档一致性、测试冗余、版本一致性、编号一致性、测试标记等脚本改为复用 `_checklib`

**③ 契约统一**：`check-version-consistency.py` 补 `--ci`（仅报失败、退出 2）；`check-task-numbering.py` / `check-test-markers.py` 发现违规退出 2（原为 1）；`check-svg-geom/pixel/text-overflow` 三件套合并为 **`check-svg.py`**（子命令 `geom` / `pixel` / `text-overflow`，带 `--ci` 与退出码 0/1/2）

**④ `test-runner.py` 拆包（1,600 → 246 行入口 + 7 模块）**：`scripts/_test_runner/` 按职责拆分 `paths` / `modes` / `pytest_env` / `machine_info` / `doc_writer` / `report_html` / `runner`（最大 345 行）；入口保留 CLI 与主流程并 **原面 re-export 49 个符号**，既有测试与调用方零改动（受影响测试的 monkeypatch 改指向持有状态的子模块，如 `_test_runner.report_html._LATEST_DIR`）

**⑤ 清理**：2 处死代码（`_ratio_band`、`_check_exact`）；新增 `src/test/unit/scripts/test_checklib.py`（38 例）覆盖共享设施与共享排除模式

**⑥ 顺带修正 rf-413**：`check-svg` 的像素子命令依赖 Pillow 但依赖清单未声明（干净环境必 `ModuleNotFoundError`）→ 改为按需导入 + 可读指引 + `[svg]` 可选依赖组（`pyproject.toml` / `requirements.txt` 同步）

**验证**：`check-semantic-index --ci` / `check-code-traces --ci` / `check-doc-drift --ci`（含 `--with-test-count`）/ `check-test-redundancy --ci` 全 [OK]；`dev-verify` 3098 passed / 0 failed；`ruff check` + `format --check` 全绿；统计快照（folders.md / test-coverage.md）同步刷新。

### README 架构图卡片加宽：消除 4 处文本贴边（2026-09-19，rf-412 收尾，commit `32b3766c`）

**触发**：`check-svg.py` 三合一后首次具备退出码（0/1/2），随即暴露 4 处「文本贴边」——卡片内文本右余量仅 1~4px（`_PADDING_WARN = 6px` 阈值，按字符宽度估算模型）。此前三个 svg 脚本各自无退出码、恒为"通过"，这类版式风险不会出现在任何门禁输出里。

**变更（只加宽卡片，不位移任何元素）**：
- `src/static/architecture.svg`：左侧渠道列三卡 210 → **220**（+10px）——`全键盘菜单 · 方向键+字母` 右余量 1.9 → 11.9px；中间双列六卡统一 172 → **180**（+8px）——`实时行情 · 多源回退` 3.5 → 11.5px、`风险 · 情景 · 再平衡` 2.0 → 10.0px（两列保持等宽，列间距 16 → 8px；右列右缘 686 仍在引擎面板 700 内）
- `src/static/llm-chain.svg`：顶部四个 Provider 卡片统一 200 → **210**（+10px）——`Anthropic · Opus/Sonnet` 右余量 1.4 → 11.4px（右缘 934 距容器 960 仍余 26px）
- **安全性核对**：卡片右缘（240/490/678/276）**零引用**（无连接线/箭头锚定其上），卡内文本均为左锚定或 middle 锚定在卡片外的坐标 → 仅变宽、不移动任何元素
- 矩形底部不齐降为**提示项**（流程图同列卡片高度本就允许不同，原判定会误报），已在 `developer-guide.md` 记明

**结果**：三张 SVG 均通过 `geom`，卡片内文本右余量 ≥10px（`capabilities.svg` ≥19px）。

**验证**：`check-svg.py --ci geom src/static/*.svg` → [OK]；`dev-verify` 3098 passed / 0 failed；`ruff check` + `format --check` 全绿；八个 `--ci` 检查脚本 + `check-doc-drift --with-test-count` 全 [OK]；folders.md 统计同步刷新。

### 修复 test-runner 拆包期的报告误落位置 + 检查器漏检（2026-09-19，rf-414）

**触发**：用户发现「scripts 目录下有 test-reports 目录」。

**成因**：`test-runner.py` 拆包时，迁移把入口的项目根算式 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 原样搬进 `_test_runner/paths.py`——但该文件比入口深一级，于是 `_PROJECT_ROOT` 算成 `scripts/`，22:51 的两次 `dev-verify` 校验把归档与汇总页落到 `scripts/test-reports/`（内含 `archives/20260919/225126`、`225129`）。同一根因也让 preflight 路径拼成 `scripts/scripts/check-task-numbering.py` 而报错，因此在修复前已暴露；修好 `_PROJECT_ROOT` 后（22:51:35）随后几次运行（`225139` 起）即落回仓库根 `test-reports/`。

**为何此前没被拦住**：产物本身在 `.gitignore` 内、从未入库；但**检查器漏检**——`check-doc-drift._is_generated()` 把任意层级的 `test-reports` 一律豁免，受检目录下的误落不会被报出。

**变更**：
- 删除误落目录（仓库根 `test-reports/` 为规范位置，未受影响）
- `check-doc-drift._is_generated()` 不再豁免 `test-reports`：其规范位置在仓库根、本不在受检范围内，故受检目录（`src/`、`scripts/`、`docs-stm/{managements,manuals,plan}`）下出现必属误落；文档串写明该例外与成因
- 回归用例：`check-doc-drift` 补「`scripts/test-reports/index.html` 须报目录树缺少」；`test-runner` 补 `TestProjectRoot`（`_PROJECT_ROOT` 必须等于仓库根、`_LATEST_DIR`/`_ARCHIVES_DIR` 不得含 `scripts` 段）
- `CLAUDE.md`（目录结构同步条）与 `folders.md`（目录树条目）注明「`test-reports/` 只应在仓库根」

**验证**：`check-doc-drift --with-test-count` → [OK]（含误落检测用例）；`dev-verify` 3098+ passed / 0 failed；`ruff check` + `format --check` 全绿；八个 `--ci` 检查脚本全 [OK]；复跑 `test-runner` 确认不再于 `scripts/` 下生成 test-reports。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.1（2026-09-15 ~ 2026-09-18）
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
