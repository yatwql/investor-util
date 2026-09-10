# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.17-dev] - 开发中（未发布）

### 开发版本切换（2026-09-10）

- 发布 v0.10.16 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.17-dev。

### LLM 模块缓存指纹读写同源（2026-09-10）

- **缺陷（自审 rf-297）**：写侧（`generators.py` 各生成器内的指纹闭包）与预检侧（`generators_orchestrator.py::_compute_module_cache_info`）**各自拼接**同一模块的缓存指纹，仅靠两侧注释声明"须同步"。实际已双向漂移：预检侧把组合风险信号摘要（`history_data` 的最大回撤/年化波动/区间收益/状态，经 `_build_competitive_context_block` 进入智囊团复盘提示词）计入指纹而写侧未计入；写侧把辩论增强开关后缀（`_c`）计入而预检侧未计入。后果是**读写键相互错开、永不相等**——写侧照常写缓存，预检侧却恒不命中，表现为「开关与参数看似生效、每次报告仍全量派发 LLM」的静默退化：专家复盘/健康体检/穿透深挖三个模块每次都重复调用（费用与耗时随报告规模线性放大），且无异常、无告警，只能靠逐模块比对键值发现。
- **改动（消除缺陷类别，而非补一处赋值）**：新增 `llm/module_fingerprint.py` 作为四个 LLM 模块缓存指纹的**唯一事实来源**——`ModuleFingerprintInputs`（冻结 dataclass，承载 11 项输入）+ 四个模块级构建函数 + `MODULE_FINGERPRINT_BUILDERS` 注册表。写侧与预检侧**只允许调用同一构建函数**，任一环节不得再自行拼接指纹片段；辩论增强后缀、决策账本经验后缀、风险信号摘要后缀、结构化表头后缀的判定全部收敛进构建函数内部，因此两侧不可能再对"某个入参/开关是否影响指纹"产生分歧。`generators.py::_build_feature_suffix` 随之删除（职责并入 `debate_feature_cache_suffix()`）。新增模块而非扩展 `fingerprint.py`：后者已被 `prompts_signals.py` 导入，在其中反向组合摘要后缀会形成导入环。
- **`history_data` 取舍**：两侧**一致计入**（而非从预检侧摘除）。它确实影响智囊团复盘提示词内容，计入属"过敏感"方向的保守选择——代价最多是多一次未命中，而漏计则会让提示词内容与缓存键脱钩。**副作用**：专家复盘/健康体检/穿透深挖三个模块的写侧键因此一次性变更，既有缓存不再命中，下次报告对这三个模块各重新生成一次（自动发生，无需人工清理）。
- **架构纪律升格**：该同源要求写入 `technical.md` 架构设计约束表（LLM 集成层），把原先只存在于散文注释里的"读写键同源"变成可评审、可追责的编号约束；`check-doc-traces.py` / `check-code-traces.py` 的约束代号识别范围同步扩展。
- **测试**：新增 `test_module_fingerprint.py` 32 例——注册表键集合与预检键集合一致（防新增模块只注册一半）、四种输入场景下「预检键 == 写侧键」（含 `history_data` 有无/变化、信号摘要开关、辩论增强开关两态，三模块 + 全局政经共 4 模块 × 6 场景参数化）、**风险信号进入写侧指纹**（缺陷直接守卫）、全局政经不受风险信号影响、辩论增强后缀两侧同步、信号摘要后缀只作用于摘要模块。既有 `test_debate_generators.py` 的开关变体用例补齐第二处读点打桩。`test_trace_check_scripts.py` 的约束代号边界用例随识别范围扩展同步（"范围外样例"改用紧邻的下一个新编号，确认新增约束自身被检出、而其后的编号仍不误伤）。
- **文档**：`llm-technical.md`（§13.1 指纹依赖表补齐 `history_data` 组合风险信号摘要项与辩论增强后缀、新增模块表行、"提示词受开关影响时的缓存键纪律"改写为"唯一事实来源"）、`technical.md`（约束表新增条目、结构化表头与信号摘要两处同源表述改为指向构建函数）、`folders.md`（目录树补两个新文件）、`CLAUDE.md`（架构遵从条目的约束条数）。

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

- **背景**：借鉴外部 augur 的健壮性实践识别出三项独立改进——① `float("nan")` / `float("±inf")` **不抛异常**，各 provider 解析器里 `try: float(x) except` 形态的兜底对它们完全无效，脏值直入市值核算/收益序列/绘图数据；② provider 链路失败只留 `failure_type` 短标识（`tencent: transport`），用户看不懂是哪个源、为什么失败；③ 缺少一次性盘点「环境/配置/目录/数据源」的诊断入口，出问题只能逐个命令试。分析见 `docs-stm/plan/augur-borrowing-analysis.md` §建议C；实现设计见 `docs-stm/plan/robustness-suite-implementation.md`。按缺口**性质**拆 A（真缺陷，无开关）/ B（实验增强，开关门控）三条独立落地路径。

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

- **背景**：市场温度、估值分位、尾部风险、风格因子、再平衡超限这五类评级由**确定性算法**算出，但只活在一次报告生成的内存里与当页展示中——报告落盘即散失，跨期无法回答「上期判高估，事后对不对」。同时，这些评级里既有当日实时行情算出的、也有**降级/缓存行情**算出的，二者混在一起消费时，非实时数据算出的评级会冒充真实战绩。借鉴外部 augur `backtest.py` 的 `data_source` 标签与「排行榜默认 `live_only`」纪律。分析见 `docs-stm/plan/augur-borrowing-analysis.md` §建议B。
- **实现设计**：`docs-stm/plan/signal-ledger-implementation.md`。

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

- **背景**：决策词（减仓/加仓/持有）在全仓库**只走展示、无人解析**——「操作建议」表仅存在于提示词契约中，`markdown_to_html` 又把表格降级为逐个 `<p>` 行；唯一消费方（决策账本抽取）用**子串包含**判方向。`不建议加仓` 会被判成 `+1`、`加仓或减仓` 会取靠前词判成 `-1`、`暂不减仓` 会被判成 `-1`。误判后果不是显示错一行，而是**按错误方向写入 `data/state/decision_ledger.jsonl`**，日后结算时污染命中率统计与教训回灌。分析见 `docs-stm/plan/llm-quality-signal-analysis.md` §3。
- **实现设计**：`docs-stm/plan/decision-header-parse-implementation.md`。按缺口**性质**拆两条独立落地路径：

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

- **背景**：现有【数据质量降级】披露只覆盖**输入侧**（数据源可达性），**输出侧**（LLM 各模块内容本身的完整性/一致性）无任何口径——内容缺章节、被占位符顶替、篇幅显著偏薄这类"内容在但不可信"的情形，下游读者拿到的是与正常输出无异的排版。借鉴外部 `agents/quality_gate.py` 的 A~F 分级机制（**劣级不阻断、不重试**，只把「降级 C/D/F」说明注入下游）。分析见 `docs-stm/plan/llm-quality-signal-analysis.md` §2。
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

- **背景**：算法层算出的确定性结论有相当一部分只走渲染层、进不了提示词；进了的那部分又存在**裸值歧义**——行业资金流向段原先把净流出拼成「主力净流入-5,000,000」（label 固定「净流入」、数值带负号），模型读到的是自相矛盾的文本，只能靠推断符号含义；且数据源返回顺序无排名语义，截取前 5 行不构成任何「前列」含义。分析见 `docs-stm/plan/llm-quality-signal-analysis.md`。
- **实现设计**：`docs-stm/plan/signal-pre-digestion-implementation.md`。按缺口的**性质**拆两条独立落地路径：

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

- **背景**：原「对判断当次即评、事后无对账」——LLM 看多看空与确定性再平衡/行动建议无法用真实后续行情验证，判断质量无从沉淀、教训无法回灌后续分析。借鉴 TradingAgents-astock 两阶段延迟反馈 + augur「预测-真实结果结算、确定性命中率统计、立即持久化」合成一套闭环（分析见 `docs-stm/plan/reflection-decision-loop-analysis.md` + `augur-borrowing-analysis.md` §建议A）。
- **实现设计**：`docs-stm/plan/decision-reflection-implementation.md`（分层依赖：`core/` 账本零 report/llm 依赖；`report/` 登记/结算/复盘消费 core；`llm/` 经 core 读教训回灌）。
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

- **借鉴评估**：外部仓库 TradingAgents-astock 与 BruceLanLan/augur 的机制借鉴评估，识别 7 条可借用点登记为 P4 实验级候选（缺省关闭、需显式启用），见 `docs-stm/plan/` 三份深入分析文档 + plan.md P4「借用探索候选」表：
  - TradingAgents-astock（2026-08-29 评估）：决策跨期反思闭环、信号预消化、模块级质量分级注入、决策头结构化+确定性解析兜底 → **plan-30/31/32/33**
  - augur（2026-09-09 评估）：确定性结算学习、live/demo 标签纪律、健壮性三件套 → **plan-30 合并评估 + plan-34/35**
- **待办登记**：借鉴分析同步发现 2 条 LLM 输出侧质量缺陷，登记 `review-findings.md` P2C（详见该文件）——
  - **rf-295**：`_submit_llm_future` 漏传 `degradation_events` → health_check「数据质量」维度恒报全正常，与 expert_review 降级摘要口径可能矛盾（关联 plan-32 可作最小起步验证）
  - **rf-296**：品种代码笔误（如实盘 561910→161910 易位一位）无自动纠正通道，fact_checker 仅告警不修正，唯一近邻 + 权重吻合也被放过 → **已随「品种代码笔误自动纠正（rf-296）」修复条目解决**（见本版本上方条目）
- **配套**：folders.md 目录树/统计新增 `docs-stm/plan/` 3 份分析文档（project 文档 116→118 / 46,372→46,773）。

### 开发版本切换（2026-08-29）

- 发布 v0.10.15 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.16-dev。

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

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.13（2026-08-04 ~ 2026-08-14）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
