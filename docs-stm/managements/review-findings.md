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

> 来源：用户运行日志复现。DeepSeek 主链路 thinking 开启模块反复触发"思考部分耗尽 max_tokens 预算"→ 切 provider。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-122** | `expert_review`/`health_check` 开启 Extended Thinking 时，DeepSeek V4 兼容端点 `max_tokens` 为 **thinking + 正文共享预算**（官方文档确认），`max_tokens=8192` 下 medium 思考即耗尽 → 响应仅 thinking block 无正文 → 空内容 → 切 provider（gemini-fallback 不支持 thinking 且链路不稳，模块内容有丢失风险）。rf-98 只抬 4096→8192，对复杂输入仍不够 | ① 抬 `max_tokens`：expert_review 8192→20000、health_check 8192→16000（对应 thinking_budget 16000/12000 + 正文余量；DeepSeek V4 输出上限 384K 无 400 风险）② 代码安全网：thinking 耗尽时自动**关闭 thinking 重试一次**（`call_claude` 层），保证有正文产出 |

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
| rf-122 | `set_config()` 写盘前未还原 `_absolutize_paths` 的内存绝对化 → 本机绝对路径（`D:\codebase\...`）直接落盘 config.json 并随 git 提交，跨机器不可移植；`llm_providers_file` 等后续也会被绝对化；另 `init_config` 模板同样写绝对路径（全新安装即不可移植） | `_validation.py` 新增 `_deabsolutize_paths()`（与 `_absolutize_paths` 对称，仅还原 PROJECT_ROOT 之下路径，跨盘/项目外绝对路径保留）；`set_config()` 写盘用浅拷贝先反绝对化再序列化（写盘失败不污染缓存）；`_build_template_from_defaults()` 模板同样反绝对化；恢复 config.json 已提交的 4 个绝对路径为相对 | `changelog.md` → Fix / Test / Docs |
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
