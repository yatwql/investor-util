# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.5-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C19）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P1 — probe 探测发现（plan-7 决策相关，2026-08-01）

（无待处理项 — rf-102/103/104/106 已全部处理，见"已修复"表）

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> 来源：`plan-chartjs-report-upgrade.md` §4.5/§4.7/§4.8/§4.10/§5 Iter 7 + `plan-chartjs-risk-analysis.md` §4 TD 表。
> plan-1 代码与自动化测试已落地（dev-verify 1181 passed），以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | ①③⑤ 可用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 已补齐载体）；②④⑥ 需真实浏览器/微信实操——**勾选清单已备**：`docs-stm/plan/plan-1-iter7-verification-checklist.md`（含 6 项 × 具体操作步骤 + 结果汇总），按清单勾选完成后回填 changelog |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器 |
| **rf-115** | TD-L2：`history_data` 数据同时服务 Excel + HTML Chart.js，模板 `tojson` 序列化全量字段（含 Excel 不需要的字段） | plan-2/plan-3 引入 chart_data 专用裁剪 |
| **rf-116** | TD-L3：模板仍为单文件 ~2000 行（Chart.js 初始化 JS 已外部化缓解，Canvas 函数 + 条件分支仍占体积） | 独立技术债迭代做章节级 partial 拆分 |
| **rf-117** | A6 键盘可达性未做（Chart.js tooltip 为鼠标悬停驱动，键盘聚焦不触发） | 设计明确"不做 MVP 记入技术债"（upgrade.md §4.8 A6）；如需支持，给 chart-init.js 加键盘交互扩展 |
| **rf-118** | 相关性矩阵 Heatmap 仅占位文本（Chart.js Matrix 插件未引入） | 依赖 plan-2 提供 `correlation_data` 后引入 `chartjs-chart-matrix` 渲染（Iter 7 已推迟，非 YAGNI） |
| **rf-119** | 单图导出 PNG 按钮未做（`chart.toBase64Image()` 已用于打印快照，可复用） | P2 可选增强非 MVP（upgrade.md §4.5）；用户分享整份 HTML 报告时各图仍完整 |
| **rf-120** | S5 CSP 未配置（报告为离线静态 HTML，无外部域名） | 可选不做 MVP（upgrade.md §4.10 S5）；未来若加 CSP 仅需 `script-src 'self'` |
| **rf-121** | TD2：报告体积增大 ~200KB（chart.min.js 随每份报告复制） | R21 决策接受的"报告自包含"代价；如未来对体积敏感可改 CDN 优先 + 本地兜底 |

### P1 — LLM thinking 预算耗尽（2026-08-02）

（无待处理项 — rf-122 已处理，见"已修复"表；竞态根因 + 配置缓解详见 changelog Fix 条目）

### P2 - 代码质量（低优先级，增量改进）

#### P2A — 文件过长（>500 行，建议拆分）

| # | 文件 | 行数 | 拆分建议 |
|---|------|------|----------|
| **rf-75** | `core/registry.py` | 617 | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责 |
| **rf-76** | `llm/fact_checker.py` | 623 | 核心校验逻辑与辅助函数分离（注：长函数已拆分，文件级别未拆） |
| **rf-77** | `tui/handlers_config.py` | 553 | JSON 文本编辑函数提取到 `config/` 子模块 |
| **rf-78** | `fetcher/batch.py` | 549 | BatchDispatcher 本身内聚，可维持现状 |
| **rf-79** | `core/code_utils.py` | 541 | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出 |
| **rf-80** | `report/data_status.py` | 528 | DegradationTracker 单类偏大 |
| **rf-81** | `report/html_renderers.py` | 521 | 所有 HTML render 函数揉合一体 |
| **rf-85** | `fetcher/fund.py` | 394 | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 447 | Excel 编排器 |

#### P2B — 文档与实现不符（低优先级，增量改进）

| # | 问题 | 修复方向 |
|---|------|----------|

### P3 — 测试覆盖缺口（建议补齐）

| # | 位置 | 问题 |
|---|------|------|

---

## 已修复（摘要）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-140 | `src/test/scenario/llm/test_llm_hallucination.py` 10 处（64/72/80/89/96/103/112/119/126/196）以 **3 值**解包 `check_numerical_consistency`，但该函数在 rf-91 v3 升级时已返回 **4 元组**（含 corrections）→ `ValueError: too many values to unpack`，LLM 数值/归因幻觉检测场景（10 项）全部无法运行；`scenario_llm` marker 不在门禁内故未被捕获 | 10 处解包补 `_`；3 个偏离用例（组合收益率/个股收益率/混合）额外断言 `len(corrections) >= 1` 验证数值修正生成；LLM 场景套件 17 用例全绿（此前 10 失败） | `changelog.md` → Test |
| rf-138 | fact_check 循环（`generators_orchestrator.py`）已提取缓存标志（`gm_c/er_c/hc_c/pd_c`）但未使用——对**缓存命中**的 LLM 内容仍用**当前**持仓市值校验排名；缓存内容基于生成时价格快照，011506/040046 市值仅差 ~1,800 元（5%），价格变动即排名翻转 → 反复误报"声称 X 为最大持仓，但实际最大持仓为 040046" | `run_fact_check` 新增 `skip_ranking_check` 参数；orchestrator fact_check 循环改为带 cached 标志的列表，缓存命中模块传 `skip_ranking_check=True` 跳过排名校验（数值/品种校验保留，缓存内容数值修正仍生效），与注释"仅检查非缓存且非空的模块"意图一致 | `changelog.md` → Fix / Test |
| rf-139 | `_RANK_MAX_PATTERN` 过宽（`最大\|最重\|首要\|主要` 单独匹配即触发）——"561910 是最大单项亏损品种""601939 贡献了主要利润""600900 最大特点是…"等非持仓排名语境被误判为"声称 X 为最大持仓" | 正则收紧：排名词（第X大/第一/最大/最重/首要/主要/前X大/头X大）须与持仓名词（持仓/重仓/仓位/持股/权重）紧邻（允许中间一个"的"）才算排名声称；"最大单项亏损品种/主要利润/最大亏损来源/最大特点"不再匹配 | `changelog.md` → Fix / Test |
| rf-136 | 持仓分类表下方饼图（category_doughnut）仅显示"其他"占 100%——`_build_category_doughnut_dataset` 从 details 按 `property` 聚合，但真实 `DetailRow` 无 `property` 字段 → 走 `_infer_property`；旧实现 `if code[:1] in ("6","0","3") and not name` 要求名称为空才判股票，而真实明细行始终有名称 → 全部落入"其他" | ① `_infer_property` 仅按代码前缀分类（6/0/3→股票，5/1→基金，无匹配→其他）；② `_build_category_doughnut_dataset` 双数据源——优先 cat_data（`_categorize_holding` 权威分类，按 `sub_mv` 聚合），回退 details；③ `write_html_report` 用本地计算的 cat_data 补齐/覆盖 category_doughnut，图表与持仓分类表同源 | `changelog.md` → Fix / Test |
| rf-137 | 资产穿透 TOP10 章节开头提示"行业数据暂不可用/穿透数据暂不可用"，但下方表格有穿透数据——12 只基金中仅 1 只无法获取穿透（合计市值 7,589.70 元未计入 TOP10），属**部分失败**；根因：`_build_chart_datasets_for_report` 构建 chart_datasets 时未传 penetration → industry_bar/penetration_bar 返回空 → 模板渲染占位提示 | `write_html_report` 用本地计算的 penetration（含 top10）补齐/覆盖 industry_bar/penetration_bar；空值语义保持——仅全量不可用才显示占位，部分失败（top10 有数据）正常渲染图表 | `changelog.md` → Fix / Test |
| rf-122 | `expert_review`/`health_check` Extended Thinking 思考部分耗尽 max_tokens 预算 → 响应仅 thinking block 无正文 → 空内容 → 切 provider（gemini 不支持 thinking，模块内容有丢失风险）；且 `call_claude` 思考耗尽安全网（关闭 thinking 同 provider 重试一次）因 `_last_thinking_exhausted` 为 `api_base` **模块级全局**在 `ThreadPoolExecutor(llm_max_concurrency=3)` 并发下被其他线程 `_extract_content` 开头的无条件复位踩踏而**静默失效** → provider 误标 `api_error`（实测 2026-08-02 日志：con 方思考吃满 20000 max_tokens、安全网未触发、切 gemini） | ① **竞态修复**：`_last_thinking_exhausted` 改**线程局部**（`threading.local()`），`_extract_content` 复位/置位与 `call_claude` 检查同线程隔离，安全网可靠触发 ② **配置缓解**：`reasoning_effort_expert_review` medium→low + `max_tokens_expert_review` 20000→24000（同步 `data/config/llm_settings.json` + `_llm_defaults.py`），降低思考占满概率；既有 8192→20000/16000 抬升保留 | `changelog.md` → Fix / Test / Docs |
| rf-123 | `set_config()` 写盘前未还原 `_absolutize_paths` 的内存绝对化 → 本机绝对路径（`D:\codebase\...`）直接落盘 config.json 并随 git 提交，跨机器不可移植；`llm_providers_file` 等后续也会被绝对化；另 `init_config` 模板同样写绝对路径（全新安装即不可移植） | `_validation.py` 新增 `_deabsolutize_paths()`（与 `_absolutize_paths` 对称，仅还原 PROJECT_ROOT 之下路径，跨盘/项目外绝对路径保留）；`set_config()` 写盘用浅拷贝先反绝对化再序列化（写盘失败不污染缓存）；`_build_template_from_defaults()` 模板同样反绝对化；恢复 config.json 已提交的 4 个绝对路径为相对 | `changelog.md` → Fix / Test / Docs |
| rf-124 | `set_config()` 写盘用 `json.dumps(payload)` 全量重写 → 剥掉 config.json 模板的 `// ── A~L ──` 12 个分组注释与行尾注释（实测磁盘仅剩 1 个 K 分组且编号与模板错位），`history` 缺 `performance_evaluation`；配置文件带 `//` 注释是项目惯例，全量重写是长期注释剥离缺陷 | ① `set_config` 改**基于磁盘原始文本做单键 patch**：`_core.py` 新增 `_patch_config_key` + 状态机 tokenizer（`_find_top_level_value_span`/`_find_value_end`/`_find_top_level_close_brace`/`_skip_ws_and_comments`），正确处理字符串/`//`/`/* */` 注释与嵌套深度，仅替换目标键 value、不存在追加末尾；文件不存在/空白用模板打底（首次创建带注释）；损坏文件中止写；patch 结果校验后原子写；目标路径键 `_patch_value_for_write` 反绝对化（rf-123 保留）② 模板补注释：`holdings_filename`/`history` 加 `ensure_ascii=False`，`batch`/`batch_rate_limit` 手动构建恢复行尾注释 ③ 重建 config.json：恢复 A~L 分组注释 + batch 行尾注释 + 补 `performance_evaluation` + 保留 `_privacy_notice_shown` | `changelog.md` → Fix / Test / Docs |
| rf-125 | 配置项名 `enable_b_series`（基金深度分析 #6~9）不可读——"B 系列"是内部模块分组编号，用户无法从开关名推断其控制什么 | 改名 `enable_fund_deep_analysis`：配置键/`_DEFAULT_CONFIG`/模板/`_validate_enable_boards` 校验列表；读取函数 `is_enable_b_series`→`is_enable_fund_deep_analysis`（含导出、TUI 菜单 P、report 层调用）；report 层参数与局部变量同步改名；活跃文档全部同步。**内部模块类型标识 `"b_series"`（dict key、`write_b_series_sheets`、文件名）保持原名**，archive 历史不追溯 | `changelog.md` → Fix / Test / Docs |
| rf-111 | 模板 6 个 chart canvas 无 `aria-label`/`role="img"`/fallback 文本（设计文档 §4.8 A1 声称已实现，实际 `grep -c aria-label` = 0 处） | 模板 6 处 canvas 补 A1 属性 + 内嵌 fallback 文本（对齐 `test-chart.html` 示范写法）；新增 `test_all_chart_canvases_have_a11y_attrs` 回归用例（6 图 canvas 断言 aria-label 含"悬停查看"/role=img/fallback 文本非空）；report 套件 161 passed | `changelog.md` → Fix / Test |
| rf-112 | **TD8 JS 调试设施空白** — 设计文档多处声称已建"独立 test HTML 调试页"，仓库实际无此文件（仅 `report_template.html`），升级 Chart.js（S2 流程）无独立验证载体 | 新增 `src/static/test-chart.html` 独立调试页：6 图渲染/交互 + 4 场景（正常/降级/空数据/离线）自检横幅（`canvas._chart` 统计初始化数 + `typeof Chart` 守卫验证），ES5 语法（R17/R22），数据契约对齐 §4.12；`src/static/README.md` 文件清单 + S2 升级指引同步 | `changelog.md` → Fix / Docs |
| rf-107 | `_report_generation.py` 收集 7 个 `metrics_*` flag 传入 builder，但 `metrics_risk_contribution` 无雷达轴消费（`risk_contributions` 为 `list[dict]` 非单标量）；设计文档 F1/§6.6 称"7 项全是雷达子开关"与实际不符 | 收集列表移除 `metrics_risk_contribution`（保留 6 个雷达子开关）；设计文档 F1 修正为"6 项雷达子开关 + 1 项指标级熔断开关"（`circuit_breaker_wrapper` 消费） | `changelog.md` → Fix / Docs |
| rf-108 | `chart_data_builder.py` 404 行，超出 §4.11 O4 预算 ≤400 行 | 合并 risk_metrics 与 history_data 两个降级分支为单一分支 + 提取 `_BASIC_RADAR_AXES` 模块常量（397 行） | `changelog.md` → Fix |
| rf-109 | `chart-init.js` `initRadarChart` 未渲染 `degraded` 虚线，与 line/drawdown 图"degraded→虚线"统一契约不一致（降级雷达视觉实线，仅靠模板 note 文本提示） | `initRadarChart` dataset 增加 `borderDash: d.degraded ? [5,5] : undefined` | `changelog.md` → Fix |
| rf-110 | 模板雷达降级 note `<div>` 位于固定高度 `height:320px` 的 `.chart-box` 内、canvas（height:100%）之后，flow 中溢出容器边界，可能压到下方 `.data-status` 块 | note 移至 `.chart-box` 闭合标签之外（独立条件渲染），容器高度不再溢出 | `changelog.md` → Fix |
| rf-102 | `providers/tencent.py::fetch_index_kline` 文档声称上限 3650 天，实测 `days=3650` 时 API 返回 `[]`（list），`_parse_kline_response` 以 `data.get("data", ...)` 处理 dict 而崩溃 `AttributeError: 'list' object has no attribute 'get'`；实际上限约 2000 天 | `_parse_kline_response` 加非 dict 类型守卫（API 异常时返回 list → 判空不崩）；`fetch_index_kline` 钳位上限 3650→2000（实测）；docstring 同步；边缘回归测试 2 例（非 dict 响应、钳位 2000） | `changelog.md` → Fix / Test |
| rf-103 | Sina `getKLineData` 端点对**所有**代码（含 sh600000 股票、sh000300/sh000919 指数）返回 404/空 → `sina_kline.fetch_index_kline` 备用链路当前失效；设计文档原"🟢 生产验证"与实测不符 | 代码无结构 bug（`_parse_kline_json` 已对非 list 容错）；`sina_kline.fetch_index_kline` 钳位上限 3650→2000 与 Tencent 对齐（rf-102 同类防）；当前环境 404 为数据源故障，接受 Tencent 单链路降级，Sina 保留为代码级备用（环境恢复后自动生效），设计文档表述已如实修正 | `changelog.md` → Fix / Docs |
| rf-104 | CSI 风格指数 `sh000920`（300 成长）自 **2023-02-17** 起在 Tencent 停更（截至 2026-08-01 距今 1261 天），probe 判定该因子代理不可用 | plan-7 MVP 用 500成长（sh000925）单因子覆盖成长（见 `plan-advanced-analysis.md` §4 MVP 范围定义）；probe 脚本保留 sh000920 作探测候选（探测停更状态即其目的）；无代码改动 | `changelog.md` → Docs |
| rf-105 | `test_handlers_config.py::test_write_settings` 测试隔离缺陷：mock 了 `open`/`json.dump` 但 `_write_llm_settings` 还调用真实 `os.makedirs('/fake/path')` + `tempfile.mkstemp` + `os.replace`，非 root 环境下 `/fake` 不可建 → `PermissionError`（P0 dev-verify 门禁失败，与本次改动无关） | 测试补全 fs 写路径 4 个 mock（`os.makedirs`/`tempfile.mkstemp`/`os.fdopen`/`os.replace`）+ 对应断言，测试隔离完备 | `changelog.md` → Test |
| rf-106 | `report/portfolio_history.py::get_combined_timeseries` 的 `days` 参数**仅控制基准指数**（`_fetch_benchmarks`），**不控制持仓历史长度**（`_fetch_all_histories` 走 chain 默认 `days=30`）；docstring"历史天数"语义有误导。plan-7 曾误以为 `days≥60` 可获 60 期组合收益 | docstring 澄清 `days` 仅作用于基准指数，持仓历史由 chain 默认 30 决定（标注 rf-106）；plan-7 设计已改独立拉取持仓历史 days=60 方案规避（`plan-advanced-analysis.md` §4 计算方案） | `changelog.md` → Fix / Docs |
| rf-101 | `test_runner.py` 打印子进程捕获输出时，GBK 控制台遇 U+FFFD 替换字符抛 UnicodeEncodeError，Phase A 后 runner 崩溃致 Phase B 不执行（dev-verify 门禁跑不全） | `sys.stdout.reconfigure(errors="replace")` 模块级兜底，异常时静默跳过 | `changelog.md` → Fix |
| rf-100 | `test_fetcher_index.py::test_tencent_success` mock 目标笔误：mock `tencent.fetch_price`，实际调用 `fetch_index_price`——有外网时真调成功侥幸通过，无外网环境失败 | mock 目标对齐 `fetch_index_price` + 新增 `assert_called()` 回归守卫 | `changelog.md` → Fix / Test |
| rf-99 | TUI [S] 菜单泄漏旧设计遗留辩论三模块：`debate_pro`/`debate_con`/`debate_synthesis` 显示为 6/7/8 开关，切换仅写入 `enabled_llm` 但无生成路径消费（僵尸开关） | 菜单层过滤：`tui_menu.py` 新增 `LLM_MENU_HIDDEN_KEYS` + `filter_menu_llm_modules()`，[S] 面板与模型路由显示同步过滤；注册表条目保留（缓存 TTL/前缀清理依赖） | `changelog.md` → Fix |
| rf-96 | 辩论虚构过滤按"行"删除，HTML 单行输出被一个误判 token 整段清空（TOP2/TOP3/Smart 误判 → 白脸 6412 字符过滤后 0 字符 → 回退普通模式） | 过滤粒度改"行内句段"级；`raw_filter_fn` 钩子使过滤在 markdown_to_html 前作用于原始 Markdown；`TOP\d` 与 `smart`/`money` 白名单降低误报 | `changelog.md` → 辩论虚构过滤修复 |
| rf-97 | `set_config` 读-改-写无锁，并发下 get_config 读失败静默回退默认配置覆盖写，丢失已有配置项（P2 verify 门禁暴露：并发测试 final.get("base")=None） | `_config_lock` 改 RLock；`set_config` 整个 RMW 纳入锁内串行化；`get_config(_strict=True)` 文件存在但读失败时抛异常中止写而非静默覆盖；新增损坏文件回归测试 | `changelog.md` → Fix |
| rf-98 | LLM 空内容误报"内容被过滤"（DeepSeek V4 兼容端点为强制推理模型，thinking 耗尽 max_tokens 预算时响应仅含 thinking block 无 text；安抚重试无效） | `_extract_content` 无 text block 时区分根因：`stop_reason=max_tokens` 记录"思考耗尽预算"日志，其他记录"可能被过滤"；统一返回 `None` 走 provider 切换；health_check max_tokens 4096→8192 + expert_review/health_check effort high→medium（实测 mt=8192 正常产出） | `changelog.md` → Fix |
| rf-90 | `_build_prompt_appendix` 无专用测试 | 新增 `TestBuildPromptAppendix` 4 用例（空持仓/单品种/多品种排序/零市值）+ `TestBuildExpertReviewPromptSkipScenarios` 3 用例 | `changelog.md` → Test |
| rf-91 | `fact_checker` 数值混淆（601939 11.0%→2.0%） | 自动修正 v3：返回 correction 二元组 + apply_numerical_corrections + tolerance_overrides | `changelog.md` → 事实校验 v3 |
| rf-92 | LLM 持仓排名幻觉（040046/561910 声称"最大持仓"）| 统一注入架构：`_build_prompt_appendix` 在 `_run_standard_mode` 自动注入 TOP3/速查表/白名单 | `changelog.md` → Prompt 防御统一注入 |
| rf-93 | 辩论 synthesis 重复白脸/黑脸观点 + 情景分析 | `_SYSTEM_DEBATE_SYNTHESIS` 重写：禁止重述论点、禁止插入情景分析 | `changelog.md` → 辩论模式 synthesis 修复 |
| rf-94 | `_build_debate_synthesis_prompt` HTML误标为markdown | ` ```markdown` → ` ```` | `changelog.md` → 同上 |
| rf-95 | `_SYSTEM_EXPERT_REVIEW` 情景分析双重指令 + 辩论 pro/con 情景重复 | 从 system prompt 移除情景段移至 user prompt 单一注入；`skip_scenarios` 参数使辩论模式跳过情景分析 | `changelog.md` → Fix |

---

## 归档

### 归档档案

- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
