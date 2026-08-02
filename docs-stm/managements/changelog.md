# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.6-dev] - 2026-08-02

---

## [0.9.5] - 2026-08-02

### Added

- **因子暴露分析模块序号前移（#17 → #10）** — 用户要求将 `factor_exposure`（属于基金深度分析 b_series 分组）从报告末尾（#17，位于 history 分组之后）调整至 #10，紧跟同组 B2~B5 模块（fund_manager=6/fund_overlap=7/fund_concentration=8/fund_style=9）之后。后续模块顺序顺延：news_correlation 10→11、global_macro 11→12、expert_review 12→13、health_check 13→14、penetration_deep 14→15、portfolio_history 15→16、drawdown_analysis 16→17；data_source_status=18、llm_usage=19（强制末位）不变。C7 注册表 `_REPORT_SECTION_DEFAULT` 条目重排（内部契约 `type="b_series"`/`data_flag="factor_exposure_data"`/`enable_fund_deep_analysis` 门控不变），序号由注册表驱动、渲染期连续重编号，故仅默认顺序变化。同步：registry 单测断言（17→10）、HTML 模板 MODULE 注释 1~19 连续编号、管理文档（requirements.md/plan.md/technical.md §4.8 模块数 4→5 并新增 B6 小节 + 附录 H 去归档引用）、用户文档（how-to-config.md/reports-instruction.md/how-to-use-registry.md/faq.md/README.md）序号同步。门禁 dev-verify 1198 通过。

- **plan-7：因子暴露分析（MVP 3 因子：价值/成长/质量）** — 组合风格画像：`analysis/factor_exposure.py` 纯计算层（时间序列 OLS 回归，`numpy.linalg.lstsq` + 复用 `_math_utils._t_critical_95`，statsmodels 未装故不依赖）；因子代理指数 `FACTOR_INDICES`（value=sh000919 300价值、growth=sh000925 500成长替代停更的 sh000920、quality=sh000930 300质量），**不注册 `_A_INDICES`（C1：避免污染实时行情循环 fetch_indices）**；组合 R_p 按 as-if 口径（当前份额 × 历史价格 + LOCF，与 `portfolio_history` 一致）；对齐策略（组合 ffill+dropna、因子 inner join、基准 left join、有效样本 <36 判数据不足）；停更因子剔除（`FACTOR_STALE_DAYS=120`，剔除后剩余因子 <2 判数据不足）；C19 契约 13 键（available/status/betas/t_stats/significant/style_allocation/baseline_betas/factor_correlations/correlation_note/alpha/window/sample_count/stale_factors）；§1.4.5 双重降级（数据不足 insufficient / 数据源故障 source_failed）；编排 `report/orchestrator.py::compute_factor_exposure_data` 并行拉持仓历史 → 注入 `pipeline_data["factor_exposure"]`；HTML 模块 #10 风格归属柱状图（方案 A 自绘 CSS 宽度条）+ Excel `factor_exposure_sheet.py` 页签；`excel_module_loader.py` C7 注册带 ImportError 兜底；双层可见性（board_flags `enable_fund_deep_analysis` 门控 + data_flags `factor_exposure_data` 数据可用）。测试：单元 11 例（`test_factor_exposure.py`，OLS 已知解/共线性诊断/样本下限/停更剔除/as-if 收益/LOCF）+ 场景 5 例（`test_pipeline_factor_exposure.py`，C19 契约/全因子失败 source_failed/空持仓 insufficient/管线注入）
- **`excel_b_series.py` → `excel_fund_deep_analysis.py` 文件重命名** — 文件名与对应测试文件名 `test_excel_b_series.py` → `test_excel_fund_deep_analysis.py`（`git mv` 保留历史），模块路径 import 同步（`excel_generator.py`、测试文件）；rf-125 仅保留内部模块分组类型标识（`"b_series"` dict key）原样，**文件名层面用户要求统一为 `fund_deep_analysis` 语义**（函数名/变量名的标识符重命名见下条）；活动文档同步（folders.md/test-coverage.md），archive 历史引用不追溯重命名
- **标识符重命名：函数/变量/类名 `b_series` → `fund_deep_analysis`** — 承接文件重命名，按用户要求将代码中与 B 系列/基金深度分析相关的标识符统一为 `fund_deep_analysis`：`write_b_series_sheets` → `write_fund_deep_analysis_sheets`（`excel_generator.py` 调用点同步）、`_process_b_module` → `_process_fund_deep_analysis_module`（定义 + 3 处内部调用 + docstring）、TUI 菜单局部变量 `b_series`/`b_status` → `fund_deep_analysis`/`fund_status`、测试标识同步（`TestExcelBSeries` → `TestExcelFundDeepAnalysis`、`_B_SERIES_KEYS` → `_FUND_DEEP_ANALYSIS_KEYS`、`_make_b_series_mocks` → `_make_fund_deep_analysis_mocks` 等）；**保留内部契约**——注册表 `type="b_series"`、board_flags dict key、`enable_fund_deep_analysis` 门控键不变（稳定内部模块分组标识，rf-125 决策）；全局 grep 确认 `_b_model` 片段不存在（仅 `fb_model`=fallback_model，与 B 系列无关）

### Fix

- **rf-142：辩论幻觉过滤误伤穿透资产代码** — 持有 QDII 基金（博时纳指100 016055/工银标普500 096001/博时纳指100联接 040046/嘉实全球产业机遇 017730）穿透 TOP10 底层资产含 AAPL/MSFT，辩论 con 中 LLM 合理引用时被 `_filter_hallucinated_codes` 误判为虚构整句删除（实测日志 `[debate-hallu] 检测到 2 个虚构品种代码: {'AAPL', 'MSFT'}`，过滤 4202→4032 字符）。根因：`generate_debate_procon` 构建 `_valid_codes` 仅收集直接持仓代码、不含穿透资产 codes；而新闻关键词构建 `_extract_keywords_from_penetrated` 正确包含穿透 codes（实测新闻关键词含 `'AAPL', 'MSFT', '苹果', '微软'`），两处逻辑不一致。修复：`_valid_codes` 增加 `penetrated_assets[].codes`，与新闻关键词构建对齐——LLM 合理引用穿透代码不再被删，真正的虚构代码（不在持仓也不在穿透）仍被过滤
- **rf-143：DeepSeek 未开 thinking 也思考耗尽，安全网失效** — DeepSeek 等强制推理模型在 `thinking_enabled=false`（payload 无 thinking 参数）时，Anthropic 兼容端点落入默认思考模式（effort=high），思考占满 max_tokens 导致无正文（实测 2026-08-02 12:18:30 global_macro max_tokens=2048 / 12:20:08 penetration_deep max_tokens=8192 均耗尽）。旧安全网要求 `thinking_was_enabled=True` 才重试 → 该场景**静默失效** → `api_error` 切 gemini-fallback（gemini 国内不可达连续超时，模块最终失败降级占位）。修复双层：① **治本**——`configure_extended_thinking`（api.py）对 effort 模型未开 thinking 时显式注入 `thinking:{"type":"disabled"}`（DeepSeek 思考默认开启，仅移除参数无效，必须显式 disabled）；② **兜底**——`_api_claude.py` 安全网触发条件放宽到 `_is_effort_model(model)`，重试 payload 显式 disabled + 移除互斥的 `output_config`/`reasoning_effort`（thinking:disabled 与 effort 并存报 HTTP 400），禁用后恢复 temperature
- **fact-check：缓存命中模块误报"最大持仓"排名翻转（rf-138）** — [智囊团深度复盘]/[持仓体检报告] 反复出现"声称 X 为最大持仓，但实际最大持仓为 040046"误报（600900/011506/561910 被反复标记）。根因：`generators_orchestrator.py` fact_check 循环已提取缓存标志（`gm_c/er_c/hc_c/pd_c`）但**未使用**——对**缓存命中**的 LLM 内容仍用**当前**持仓市值校验排名。缓存内容基于生成时的价格快照（011506/040046 市值仅差 ~1,800 元约 5%），价格变动即排名翻转 → 用当前排名校验旧快照内容必然误报。修复：`run_fact_check` 新增 `skip_ranking_check` 参数；orchestrator fact_check 循环改为带 cached 标志的列表，缓存命中模块传 `skip_ranking_check=True` 跳过排名校验（数值/品种校验保留，缓存内容的数值自动修正仍生效），与注释"仅检查非缓存且非空的模块"意图一致
- **fact-check：`_RANK_MAX_PATTERN` 过宽误判非排名语境（rf-139）** — "561910 是组合最大单项亏损品种""601939 贡献了主要利润""600900 最大特点是…"等非持仓排名语境被误判为"声称 X 为最大持仓"。根因：正则 `最大\|最重\|首要\|主要` 单独匹配即触发。修复：正则收紧为排名词（第X大/第一/最大/最重/首要/主要/前X大/头X大）须与持仓名词（持仓/重仓/仓位/持股/权重）紧邻（允许中间一个"的"）才算排名声称；"最大单项亏损品种/主要利润/最大亏损来源/最大特点"不再匹配
- **chart：持仓分类饼图全"其他"（rf-136）** — 持仓分类表下方饼图（category_doughnut）仅显示"其他"占 100%。根因：`_build_category_doughnut_dataset` 从 details 按 `property` 聚合，但真实 `DetailRow` 无 `property` 字段 → 走 `_infer_property`；旧实现 `if code[:1] in ("6","0","3") and not name` 要求名称为空才判股票，而真实明细行始终有名称 → 全部落入"其他"。修复：① `_infer_property` 仅按代码前缀分类（6/0/3→股票，5/1→基金，无匹配→其他），不再依赖 name 判空；② `_build_category_doughnut_dataset` 双数据源——优先 cat_data（`_categorize_holding` 权威分类，按 `sub_mv` 聚合），回退 details；③ `write_html_report` 用本地计算的 cat_data 补齐/覆盖 category_doughnut，保证饼图与持仓分类表同源
- **chart：穿透章节误报"行业/穿透数据暂不可用"（rf-137）** — 资产穿透 TOP10 章节开头提示"行业数据暂不可用/穿透数据暂不可用"，但下方表格有穿透数据。用户场景为**部分失败**（12 只基金中仅 1 只无法获取穿透，合计市值 7,589.70 元未计入 TOP10，`penetration_sheet` 页脚已正确标注"无法获取穿透的基金"）。根因：`_build_chart_datasets_for_report` 构建 chart_datasets 时未传 penetration → industry_bar/penetration_bar 返回空 → 模板渲染占位提示。修复：`write_html_report` 用本地计算的 penetration（含 top10）补齐/覆盖 industry_bar/penetration_bar（R11 单图独立 try/except）；空值语义保持——仅全量不可用时才显示"暂不可用"，部分失败（top10 有数据）正常渲染图表
- **rf-122：LLM thinking 思考耗尽安全网竞态修复 + 配置缓解** — 实测复现（2026-08-02 运行日志）：`expert_review` debate con 方开启 Extended Thinking（effort=medium）时 DeepSeek V4 思考吃满 `max_tokens=20000` 全部预算 → 响应仅 thinking block 无正文 → `_extract_content` 置位 `_last_thinking_exhausted` 返回 None；但 `call_claude` 思考耗尽安全网（关闭 thinking 同 provider 重试一次，代码已存在）**未触发**——`_last_thinking_exhausted` 为 `api_base` **模块级全局布尔量**，`_extract_content` 每次提取开头**无条件复位为 False**，而 LLM 生成在 `ThreadPoolExecutor(llm_max_concurrency=3)` 下并发执行（`generators_orchestrator.py`），其他并发模块线程的提取把本线程刚置位的标志踩踏复位 → 安全网静默失效 → provider 误标 `api_error` 切 gemini-fallback（弱模型），synthesis 因字符预算超限被跳过 → 模块降级为 pro+con 拼接。修复：① **竞态修复**——`_last_thinking_exhausted` 改**线程局部**（`threading.local()`，`api_base.py` `_thinking_exhausted_local`，复位/置位/检查同线程隔离），安全网可靠触发；② **配置缓解**——`reasoning_effort_expert_review` medium→low + `max_tokens_expert_review` 20000→24000（同步 `data/config/llm_settings.json` + `_llm_defaults.py` 默认），降低思考占满概率
- **rf-123：config.json 路径型键落盘绝对路径导致跨机器不可移植** — `get_config()` 在内存把相对路径绝对化（`_absolutize_paths`），`set_config()` 却拿绝对化后的 dict 直接 `json.dumps` 全量写回 → 本机绝对路径（`D:\codebase\...`）落盘并随 git 提交，换机器/换目录后 `holdings_dir`/`output_dir` 等全部失效；`llm_providers_file` 等尚未绝对化的键在下次任何 `set_config()` 触发时也会被污染。修复：① `_validation.py` 新增 `_deabsolutize_paths()`（与 `_absolutize_paths` 对称）——仅将 PROJECT_ROOT 之下的绝对路径还原为相对路径，跨盘（Windows 不同盘符 relpath 抛 ValueError）与项目外路径（relpath `..` 越界）保持原样；② `set_config()` 写盘改用浅拷贝 + 先反绝对化再序列化，且不污染 `_config_cache`（原子写失败时缓存仍保持绝对路径内存值）；③ `_config_defaults._build_template_from_defaults()` 模板同样反绝对化——全新安装首次生成 config.json 也写相对路径；④ 恢复 `data/config/config.json` 中 4b403a3 提交的 4 个绝对路径键为相对路径
- **rf-124：set_config 全量 json.dumps 重写剥掉 config.json 注释分组** — set_config 写盘用 `json.dumps(payload)` 全量重写 → 模板的 `// ── A~L ──` 12 个分组注释与行尾注释被剥掉（实测磁盘 config.json 仅剩 1 个 K 分组且编号与模板错位），`history` 缺 `performance_evaluation` 键；配置文件带 `//` 注释是项目惯例（llm_settings.json、config 模板均如此，内部统一 `_strip_json_comments` 解析），全量重写是长期注释剥离缺陷。修复：① `set_config` 改**基于磁盘原始文本做单键 patch**（`_core.py` 新增 `_patch_config_key` + 状态机 tokenizer `_find_top_level_value_span`/`_find_value_end`/`_find_top_level_close_brace`/`_skip_ws_and_comments`，正确处理字符串/`//`/`/* */` 注释与嵌套深度，仅替换目标键 value 区间，键不存在追加对象末尾；文件不存在/空白用默认模板打底——首次创建也带注释；原文件损坏中止写（保持 _strict 语义）；patch 结果校验合法再原子写；目标路径键经 `_patch_value_for_write` 反绝对化，rf-123 相对路径能力保留）；② `_build_template_from_defaults` 模板补注释——`holdings_filename`/`history` 加 `ensure_ascii=False`（原中文转义 `个...` 可读性差），`batch`/`batch_rate_limit` 手动构建恢复 `_DEFAULT_CONFIG` 与历史 config.json 的行尾注释（原 json.dumps 序列化丢失嵌套行尾注释）；③ 重建 `data/config/config.json`：恢复 A~L 12 分组注释 + batch/batch_rate_limit 行尾注释 + 补回 `performance_evaluation` + 保留 `_privacy_notice_shown`
- **rf-125：`enable_b_series` 配置项改名 `enable_fund_deep_analysis`** — 原配置项名 `enable_b_series`（基金深度分析 #6~9）对用户不可读——"B 系列"是内部模块分组编号，用户无法从其推断该开关控制什么。改名：① 配置键 `enable_b_series` → `enable_fund_deep_analysis`（`data/config/config.json`、`_DEFAULT_CONFIG`、模板、`_validate_enable_boards` 校验列表同步）；② 读取函数 `is_enable_b_series` → `is_enable_fund_deep_analysis`（`_core.py`/`__init__.py` 导出、TUI 菜单 `P`、report 层 `_report_generation.py`/`_pipeline.py`/`orchestrator.py` 调用）；③ report 层参数与局部变量 `enable_b_series`/`_enable_b_series` → `enable_fund_deep_analysis`/`_enable_fund_deep_analysis`（html_writer/html_renderers/excel_generator/excel_b_series/excel_sheet_factory）；④ 活跃文档同步（how-to-config/how-to-menu/reports-instruction/faq/requirements/technical/plan-1 设计文档）；**内部模块类型标识 `"b_series"`（dict key、`write_b_series_sheets`、`excel_b_series.py` 文件名）保持原名**——它是模块分组类型，非用户配置；archive 历史文档不追溯重命名
- **chart：行业分布空白 sector 未归一化** — `_build_industry_bar_dataset` 仅做 `entry.get("sector") or "其他"`，纯空白字符串 `"  "` 被当作有效行业分类（生成空白标签）。修复：`(sector or "").strip() or "其他"`，None/空串/纯空白统一归入"其他"。回归测试见 `test_chart_data_builder_edge.py`（plan-1 Iter 4 验收标准 5）
- **chart：量化指标 Radar 图表（Iter 6）** — 第 6 张图迁移为 Chart.js v4 radar：① 数据三级降级（R12）——`all_metrics` 全量 6 轴（夏普/卡玛/胜率/换手率/组合 Beta/集中度 HHI）→ `risk_metrics` 3 基本字段 → `history_data` 3 基本轴，`risk_metrics`/`history_data` 兜底时 `datasets[0]["note"]="仅限基础指标"` + `degraded=True`；② §6.6 F1 子开关——6 个 `metrics_*` 雷达子开关收集传入预处理器，对应轴关闭时输出 `"N/A"`（非 0）；③ 胜率 `win_rate()` 返回 dict，`_extract_rate` 提取 0~1 数值；④ 模板 3 路占位——`data_unavailable` → "持仓市值数据不可用，量化指标暂停计算"、radar 无 labels → "量化指标数据不足"、全量/降级 → canvas + 降级 note 文本；⑤ `chart-init.js` 新增 `initRadarChart`（radar 极坐标 scale，O1 独立 try/catch，降级虚线描边）
- **chart：Iter 8 代码审查 4 项 LOW 修复** — ① rf-107：`metrics_risk_contribution` 从雷达 flag 收集移除（该 flag 是指标级熔断开关，`circuit_breaker_wrapper` 消费，非雷达轴；设计文档 F1 同步修正"6 项雷达子开关 + 1 项熔断开关"）；② rf-108：`chart_data_builder.py` 404 行→397 行，合并 risk_metrics/history_data 两降级分支 + 提取 `_BASIC_RADAR_AXES` 常量（§4.11 O4 预算 ≤400）；③ rf-109：`initRadarChart` 增加 `borderDash: degraded ? [5,5] : undefined`，对齐 line/drawdown"降级→虚线"统一契约；④ rf-110：模板降级 note `<div>` 移出固定高度 `.chart-box` 容器，避免溢出压到下方数据块
- **chart：Flag OFF 回归测试补全（Iter 7 集成验证）** — 新增 `test_flag_off_legacy_canvas_regression`：`enable_interactive_charts=False` 时 6 个新 Chart.js canvas 均不输出（无空 div/canvas 残留）、旧 `portfolioChart`/`drawdownChart` Canvas 保留、`drawSimpleChart` 定义保留——保证 Flag OFF 报告与未升级版渲染一致（Iter 7 验收标准 5）；热力图框架按 §5.0.2 推迟到 plan-2（`correlation_data` 未到，不提前引入 Matrix 插件，MODULE 14 占位已具备）；R21 本地 bundle `typeof Chart` 守卫、`chart-print.js` 打印快照已实现，浏览器人工验证项（Chrome/微信/打印/375px）在设计文档标注 ⏳ 待实测
- **rf-102：Tencent 指数 K 线超限崩溃修复** — `fetch_index_kline` 文档声称上限 3650 天，实测 `days=3650` 时 API 返回 `[]`（list），`_parse_kline_response` 以 `data.get(...)` 处理 dict 而崩溃 `AttributeError: 'list' object has no attribute 'get'`；实际上限约 2000 天。修复：`_parse_kline_response` 加非 dict 类型守卫（异常响应 → 空列表不崩）；`fetch_index_kline` 钳位上限 3650→2000 + docstring 同步
- **rf-103：Sina 指数 K 线备用链路降级处理** — Sina `getKLineData` 端点当前环境对**所有**代码返回 404/空（数据源故障，非代码 bug），`sina_kline.fetch_index_kline` 备用链路失效。处理：`sina_kline.fetch_index_kline` 钳位上限对齐 2000（rf-102 同类防）；`_parse_kline_json` 已有非 list 容错；接受 Tencent 单链路降级，Sina 保留为代码级备用（环境恢复后自动生效），设计文档表述如实修正（原"🟢 生产验证"→ 降级接受）
- **rf-106：`get_combined_timeseries` days 参数语义澄清** — `portfolio_history.py` 该方法 `days` 仅作用于基准指数（`_fetch_benchmarks`），不控制持仓历史长度（`_fetch_all_histories` 走 chain 默认 30）；docstring"历史天数"有误导，澄清并标注 rf-106，提示后续需透传 days 时改 `_fetch_all_histories`
- **rf-111：模板 6 个 chart canvas 补 A1 可访问性属性** — 设计文档 §4.8 A1 声称每个 `<canvas>` 含 aria-label/role + fallback 文本（Iter 1 验收 ✅），实际 `grep -c aria-label` = 0 处（文档与实现不符）。修复：`report_template.html` 6 处 canvas（净值趋势/最大回撤/资产构成/行业分布/穿透 TOP10/量化雷达）补 `aria-label`（"悬停查看…"描述图义）+ `role="img"` + 内嵌 fallback 文本（降级环境指引用户看明细表格），写法对齐 `test-chart.html` 示范；旧 Canvas 兜底 `portfolioChart`/`drawdownChart` 不受影响
- **rf-112：TD8 JS 调试设施空白补全** — 设计文档多处声称已建"独立 test HTML 调试页"，仓库实际无此文件（仅 `report_template.html`），升级 Chart.js（S2 流程）无独立验证载体。新增 `src/static/test-chart.html` 独立调试页：6 图渲染/交互 + 4 场景（正常/降级/空数据/离线）自检横幅（`canvas._chart` 统计初始化数 + `typeof Chart` 引擎守卫验证），ES5 语法（R17/R22），数据契约对齐 §4.12；动态注入引擎 script（离线场景移除 chart.min.js 模拟引擎缺失）
- **rf-122：DeepSeek Extended Thinking 思考耗尽 max_tokens 预算修复** — DeepSeek V4（deepseek-v4-flash）Anthropic 兼容端点 `max_tokens` 为 **thinking + 正文共享预算**（官方文档确认），expert_review/health_check 在 8192 下 medium 思考即耗尽 → 响应仅 thinking block 无正文 → 空内容 → 直接切 provider（gemini 不支持 thinking 且链路不稳，模块内容丢失风险）。修复双层：① 抬 `max_tokens_expert_review` 8192→20000、`max_tokens_health_check` 8192→16000（对齐 thinking_budget 16000/12000 + 正文余量；DeepSeek V4 输出上限 384K 无 400 风险），同步 `data/config/llm_settings.json` + `_llm_defaults.py` 默认模板；② `call_claude` 思考耗尽安全网——`_extract_content` 新增 `_last_thinking_exhausted` 标志（stop_reason=max_tokens 且无 text 置 True），首次调用返回 None 且标志为 True 时自动**关闭 thinking 同 provider 重试一次**（构建全新 retry_payload + 恢复 temperature），保证有正文产出，不再因思考耗尽直接切 provider

### Test

- **rf-142 回归测试** — `test_debate_generators.py` TestDebateProconFlow 新增 2 例：`test_penetrated_assets_codes_not_filtered`（穿透 AAPL/MSFT 被 LLM 合理引用不被过滤——捕获 con 步骤 raw_filter_fn 验证文本原样保留）、`test_penetrated_assets_real_hallucination_still_filtered`（加入穿透代码后真虚构 X1234 仍被过滤，不过度豁免）
- **rf-143 回归测试** — `test_llm_api.py` TestCallClaudeThinkingDegradation：更新 `test_thinking_exhausted_retries_without_thinking`（DeepSeek 重试 payload 断言 `thinking:{"type":"disabled"}` + 移除 output_config/reasoning_effort）、`test_no_thinking_enabled_no_retry`（改 claude-sonnet 非 effort 模型验证"未注入 thinking 不误触"）；新增 `test_deepseek_no_thinking_enabled_exhausted_retries_with_disabled`（未开 thinking 耗尽 → 安全网重试 disabled + 温度恢复）、`test_deepseek_thinking_disabled_injected_when_not_enabled`（治本：未开 thinking 的 DeepSeek 首次 payload 即显式 disabled）。LLM 套件 668 passed + P0 dev-verify 1181 passed
- **test_llm_hallucination 3 值解包修复（rf-140）** — `src/test/scenario/llm/test_llm_hallucination.py` 10 处以 3 值解包 `check_numerical_consistency`，但该函数在 rf-91 v3 升级时已返回 4 元组（含 corrections）→ `ValueError: too many values to unpack`，LLM 数值/归因幻觉检测场景（10 项）全部无法运行（`scenario_llm` marker 不在门禁内故未被捕获）。修复：10 处解包补 `_`；3 个偏离用例（组合收益率/个股收益率/混合）额外断言 `len(corrections) >= 1` 验证数值修正生成。LLM 场景套件 49 用例全绿（此前 10 失败）
- **fact-check 排名误报回归测试** — `test_fact_checker.py` TestCheckRankingCorrectness 新增 5 例（rf-139 回归：`最大单项亏损品种`/`主要利润`/`最大亏损来源`/`最大特点`均不再误判为排名声称、`前三大持仓`合法排名声称仍被检测且正确通过）；TestRunFactCheck 新增 3 例（rf-138 回归：`skip_ranking_check=True` 跳过过期排名声称且品种存在性校验通过 → 全部通过摘要、`skip_ranking_check=True` 数值自动修正仍生效（5.0%→30.3%）、默认不传参时过期排名声称仍被检出）
- **chart 分类饼图 + 穿透补齐回归测试** — `test_chart_data_builder.py` TestCategoryDoughnut 新增 4 用例：`test_infer_property_named_stock_classified_by_code`（真实 DetailRow 含名称按代码前缀分类，不再全"其他"——rf-136 回归）、`test_category_doughnut_prefers_cat_data`（cat_data 权威数据优先于 details）、`test_category_doughnut_from_cat_data_aggregation`（同 property 多组聚合 + _CATEGORY_ORDER 排序）、`test_category_doughnut_from_cat_data_empty`（空 cat_data 不崩溃）；`test_html_writer.py` 新增 `TestWriteHtmlReportChartMerge` 5 用例（write_html_report 补齐 category_doughnut/industry_bar/penetration_bar、部分失败仍渲染——rf-137 回归、Flag 关闭跳过补齐、chart_datasets=None 跳过）。report 套件全绿（P0 dev-verify 1181 passed）
- **rf-122 回归测试（竞态隔离）** — `test_llm_api.py` `TestCallClaudeThinkingDegradation` 新增 `test_thinking_exhausted_flag_thread_local_isolation`：主线程 `_extract_content` 思考耗尽置位后，并发线程提取普通响应不清除主线程标志（thread-local 隔离），本线程内后续提取仍正常复位（保留原语义）；旧模块级全局实现下该断言失败（回归守卫）。LLM 套件 656 passed
- **rf-123 回归测试** — `test_config.py` 新增 4 用例：`test_init_template_writes_relative_paths`（全新安装模板写相对路径，可移植）、`test_set_non_path_key_preserves_relative_paths`（写非路径键如隐私提示 → 5 个路径键保持相对——生产实际触发场景）、`test_set_relative_path_value_kept_relative`（写相对值落盘仍相对 + 读取时被绝对化）、`test_set_external_absolute_path_kept`（项目外绝对路径不被误相对化，越界保护）。config 套件 182 passed
- **rf-124 回归测试（单键 patch 保留注释）** — `test_config.py` 新增 `TestSetConfigSingleKeyPatch` 5 例：分组+行尾注释保留且目标值更新、仅改目标键其余注释/键不动、新键追加末尾且可解析、嵌套 dict 替换不破坏相邻键、文件不存在模板打底带注释；既有 4 处测试 `json.load` 直接解析适配为 `_strip_json_comments`（config.json 落盘带 `//` 注释是项目惯例，原直接 `json.load` 是 set_config 全量重写时期的过时假设）。config 套件 187 passed
- **rf-125 重命名回归** — `test_config_validation.py` 校验列表断言、`test_config.py` 默认配置键、`test_orchestrator.py` 12 处 `patch("src.python.config.is_enable_fund_deep_analysis")`、`test_excel_*`/`test_html_writer_edge.py` 参数名全部同步为新名，内部模块类型 key `b_series` 不受影响；config 套件 + report 相关 231 passed
- **chart 行业分布边缘回归测试** — 新增 `test_chart_data_builder_edge.py`（C12 合规）：全部无行业归属→归入"其他"、None/空串/纯空白 sector 归一化、mv 为 None/负值不崩溃、top10 空列表占位；`test_chart_data_builder.py` 补 Iter 4/5 验收用例（行业市值总和与穿透口径一致、最多 10 个行业截断、穿透品种 <3 仍渲染）
- **chart Radar 降级与 Flag 过滤测试** — `test_chart_data_builder.py` TestRadar 新增 6 用例（metrics_sharpe 关闭→该轴 "N/A"、全关→6 个 "N/A"、全 N/A 占位保轴、risk_metrics 兜底 degraded+note、history 兜底 degraded+note、全量路径无 note）；`test_chart_data_builder_edge.py` 新增 4 用例（all_metrics 与 risk_metrics 均 None→空、all_metrics=None+history 降级、未知 flag 名不影响该轴、部分指标缺失→N/A 其余保留）；`test_html_report_structure.py` 结构测试 3 用例（radar 有 labels 渲染 canvas、无 labels"量化指标数据不足"占位、data_unavailable"持仓市值数据不可用"占位）+ 既有 2 用例 chart-box 计数更新（3→4 / 5→6）
- **rf-102/103 回归测试** — `test_tencent_edge.py` 新增 2 例（API 返回 list 非 dict 不崩、days=3650 钳位到 2000）；`test_sina_edge.py` 新增 1 例（days 钳位 2000 对齐 Tencent），防超限崩溃与钳位逻辑回退
- **rf-111 回归测试** — `test_html_report_structure.py` 新增 `TestHtmlInteractiveCharts::test_all_chart_canvases_have_a11y_attrs`：6 图全部渲染（Flag ON + 数据存在）时断言各 canvas 含 `aria-label`（含"悬停查看"）/`role="img"`/内嵌 fallback 文本非空，防 A1 属性回退
- **rf-122 回归测试** — `test_llm_api.py` `TestCallClaudeThinkingDegradation` 新增 3 例：①思考耗尽（stop_reason=max_tokens 无正文）→ 自动关闭 thinking 重试一次且恢复 temperature（断言 2 次调用、第二次 payload 无 thinking、返回第二次结果）；②flag False（非思考耗尽空内容）→ 不重试；③未注入 thinking → 即使 flag True 也不重试（短路由不误触）

### Docs

- **文档全量一致性审计（模块序号/分组/归档引用）** — 按用户要求对全部管理文档+用户文档做最新状态核验：① 修正 README 过期计数——"最多 18 个条件页签"→"最多 19 个条件页签"、"基金深度分析（4 个）"→"（5 个）"补因子暴露分析；② 补 README 基金评价功能清单 + reports-instruction §10 因子暴露分析 功能↔报告位置对照行（此前缺失该模块）；③ testplan.md 场景文件表补 3 个管线测试文件（`test_pipeline_smoke.py`/`test_pipeline_metrics_injection.py`/`test_pipeline_factor_exposure.py`，C19 契约/全失败 source_failed/空持仓 insufficient）；④ folders.md 清理 plan-advanced-analysis.md 目录注释中的历史痕迹（"plan-7 已归档"→"模拟/趋势"）；⑤ 确认非豁免文档正文（technical/requirements/llm-technical/testplan/test-coverage/manuals/README）已无 archive 文件引用与历史变更描述，最新状态自包含。门禁 dev-verify 1198 通过 + check-history-traces --ci 通过 + check-version-consistency 13 项 [OK]
- **'B 系列' → '基金深度分析' 术语统一（代码/测试注释 + 文档正文）+ 报告模块序号修正（18→19）** — 确认"B 系列"即基金深度分析模块组后，按用户要求全局替换：① 代码与测试注释/文档字符串中的人性化描述"B 系列"全部改为"基金深度分析"（`test_excel_generator_edge.py`/`test_html_writer_edge.py`/`test_fund_deep_analysis_sheet_edge.py`/`test_excel_fund_deep_analysis.py`/`test_scenario_section_order.py`/`test_registry.py`/`test_html_report_structure.py`/`test_excel_report_structure.py` + 用户文档 8 份 + 管理文档 + `plan-chartjs-risk-analysis.md` 设计文档）；② 报告模块总数 18→19 全链修正——`factor_exposure` #17、`data_source_status` 17→18、`llm_usage` 18→19（history #15~16 不变），涉及 how-to-config/how-to-use-registry/faq/technical/requirements/testplan/reports-instruction/how-to-menu；③ 测试文件 `test_fund_bseries_sheet_edge.py` → `test_fund_deep_analysis_sheet_edge.py`（`git mv` 保留历史）；④ **内部契约保留**——注册表 `type="b_series"`、board_flags dict key、`enable_fund_deep_analysis` 门控键稳定不变（rf-125 决策）
- **check-history-traces.py 覆盖强化 + 全库历史痕迹清零（Python/JS/HTML/脚本）** — 按用户要求对 `.py/.js/.mjs/.html` + `.sh/.ps1/.bat/.cmd` 全类型扫描并打磨脚本：新增 shell 注释提取（`.sh` `#`、`.ps1` `#`+`<# #>`、`.bat/.cmd` `REM`/`::`，BOM 头处理，shebang 跳过）；HIGH 新正则（`历史上|历次迭代`、`曾(?:经)?(?:用[于]?|作为|属于|采用|以)`、`(?:后来|之后|随后)\s*(?:改[为成]|换[为成]|引入|移除)`）；VERSION `(?:原先|最初|早期)(?:是|为|使用|采用|属于)`；ORIGIN 扩展非 `.py` 后缀（`原\s*[`\w./_-]+\.(?:py|js|mjs|html|ts|vue)`）。手动清扫暴露旧版漏检 3 类痕迹并修复：`test_market_value.py` "从原 test_market_value_edge.py 合并"、`test_config.py` "曾用 json.dumps 全量重写"、`registry.py` 4 处 "对应原 constants.py/cache.py/config.py 的功能"（源归属 docstring）。全库扫描 exit 0（`scripts-reference.md` 同步 8 种支持扩展名）
- **rf-122 归档 + rf-123 编号更正** — rf-122（LLM thinking 思考耗尽安全网竞态）从待处理移至已修复表（摘要行），详细修复说明见 changelog Fix 条目；同时更正上一笔提交的编号冲突——config.json 路径修复由误用的 rf-122 改为 **rf-123**（rf-122 已被 LLM thinking 问题占用，原编号违反"单调递增不回收"规则），changelog Fix/Test/Docs 与 review-findings 已修复表同步
- **rf-123 归档 + review-findings.md 已修复表** — rf-123（config.json 路径型键落盘绝对路径）从待处理移至已修复表（摘要行），详细修复说明见 changelog Fix 条目；config.json 相对路径恢复后已确认磁盘相对 + 运行时绝对化双向一致
- **rf-124 归档 + review-findings.md 已修复表** — rf-124（set_config 全量 json.dumps 重写剥注释分组）从待处理移至已修复表（摘要行），详细修复说明见 changelog Fix 条目；config.json 重建后已确认 A~L 12 分组注释 + batch/batch_rate_limit 行尾注释齐全、`performance_evaluation` 补回、`_privacy_notice_shown` 保留
- **rf-125 归档 + review-findings.md 已修复表** — rf-125（`enable_b_series` 配置项名不可读）从待处理移至已修复表（摘要行），详细修复说明见 changelog Fix 条目；活跃文档已全部同步新名，内部 `b_series` 模块标识与 archive 历史保持原名
- **plan.md 与迭代设计文档依赖状态同步** — 核实 rf-1 批量并行已落地（`BatchDispatcher` 应用于行情/基金排名/行业链路）后：① plan.md plan-2 依赖标注 ⚠️→✅（原"串行获取全品种历史 15-30s"顾虑已消除），P2 头部补充前置状态注记，合计预排 ~18d→~21d；② plan-1 预估 4d→5.25d，对齐 `plan-chartjs-report-upgrade.md` 8 迭代方案，移除 plan.md 中过时的 4d 分阶段表；③ `plan-correlation-drawdown.md` §1 "对 rf-1 的依赖"改写为"已解除"，数据获取编排行注明复用 `BatchDispatcher` 并行链路；④ `plan-engineering.md` 补充 rf-1 完成状态注记（v0.8.x 已回归验证）
- **plan.md 按推荐实施顺序重排** — 新增"推荐实施顺序"总览小节（①~⑨ 跨 P2/P3 归类），标注推荐理由与工作量；P2 区块内部重排（plan-2/3 → plan-1 → plan-6/5/7，plan-4 已放弃保留），P3 区块内部重排（plan-9 → plan-11 → plan-10 → plan-8）；各计划项标题/表格行补充推荐序号标注；plan-7 状态列明确"实施前先做 0.5d probe 决策闸门（≥3 个 CSI 指数有效 → MVP 3 因子，否则放弃）"；同步 P2 定义行预排数 ~22d→~21d 消除不一致
- **plan-7 probe 决策闸门完成 → MVP 3 因子** — 新增 `scripts/probe-csi-factor-indices.py`（只读探测，支持 `--provider tencent|sina`/`--days`/`--threshold`/`--stale`/`--codes`/`--no-extra`），对 5 个 CSI 风格指数 + 低波补充逐个调用 `fetch_index_kline`，按 plan-advanced-analysis.md §4.3 + 数据新鲜度维度（条数 ≥ threshold 且 距今 ≤ stale 天）输出 5f/3f/infeasible 判定。实测（365 天窗口，新鲜度 120 天）：**Tencent 4/5 有效且新鲜**（300价值/500价值/500成长/300质量），**300成长（sh000920）自 2023-02-17 停更**需替换代理，低波（sh000931）有效可作补充 → **MVP 3 因子可行（3f）**。同步 plan.md plan-7 行（3.5d→2.5d、状态 ✅ probe 完成、P2 预排 ~21d→~20d）与 `plan-advanced-analysis.md` §4.3（可行性评级、风险表、probe 结论）
- **plan-7 实现设计补齐：架构约束遵从表 + 技术债预置** — `plan-advanced-analysis.md` §4 新增三小节：① 架构约束遵从表（C1/C6/C7/C14/C19/§1.4.5/C2，对齐 plan-2/plan-3 文档规范，补设计缺口）；② 技术债与技术预置——既有技术债 rf-102（Tencent 3650 上限崩溃）/rf-103（Sina 备用链路 404）/rf-104（sh000920 停更）对 plan-7 的影响与处理建议，C7 注册条目（`factor_exposure` number=17，data_source_status/llm_usage 顺延 18/19）与 C19 schema（`factor_exposure` dict 键结构）预置，计算方案（R_p 复用 `get_combined_timeseries().daily_returns` + `numpy.linalg.lstsq` 手写 OLS 复用 `_math_utils`，不新增 statsmodels 依赖；饼图降级为柱状图不阻塞 plan-1）；③ 工作量估算 3.5d→2.5d 对齐 plan.md。同步 technical.md 附录 H 追加 `factor_exposure` 计划中条目；plan.md plan-7 行"饼图"改"柱状图"
- **plan-7 迭代设计 10 轮复盘（质量收敛）** — `plan-advanced-analysis.md` §4 多轮自我进化（2026-08-01）：① **R_p 来源重要修正**——`get_combined_timeseries` 的 `days` 参数只传基准、持仓历史固定走 chain 默认 30 期（新增 rf-106），改编排层独立拉取持仓历史 `days=60` 按 as-if 语义算组合收益；② 共线性 MVP 处置明确（不做正交化/岭回归，仅相关矩阵诊断展示 + 高相关文案提示）；③ 风险清单深化 4 项（仅单点数据源/as-if 失真/手写 OLS 正确性/因子停更静默污染，按数据重要性排优先级，降级原则"绝不输出误导性数字"显式化）；④ 新增"与其它计划项交互"表（plan-2 对齐复用 / plan-3 as-if 口径一致约束 + 共享提取技术债预留 / plan-6 快照预留 / LLM 不注入）；⑤ MVP 范围收敛（固定 3 因子集合 `FACTOR_INDICES` + 明确不做清单 + 保留项，修正"少 1 个因子代理"与"低波作补充"两处矛盾）；⑥ 新增测试策略章节（OLS 已知答案小数据集/降级路径/口径一致用例 + marker 分配 + 门禁映射）。同步 review-findings.md 记录 rf-106
- **rf-102/103/104/106 技术债处理落地** — review-findings.md 四条目从待处理移至已修复表（含修复方案与变更记录）；`plan-advanced-analysis.md` §4 技术债表更新为 ✅ 已处理（C6 行、风险清单"仅单点数据源"同步降级接受表述）；plan.md plan-7 行标注"实施前技术债已全部处理"；rf-104（sh000920 停更）MVP 因子替代方案确认（500成长 sh000925 单因子，probe 脚本保留 sh000920 作探测候选）
- **rf-112 文档同步** — review-findings.md rf-112 已修复表 + rf-111（模板 canvas 缺 A1 aria-label/fallback，文档与实际不符，待处理）P2B 小节；`src/static/README.md` 文件清单补 `test-chart.html` + S2 升级指引改为"先调试页验证再真实报告验证"；`folders.md` src/static/ 子树补 `test-chart.html` 条目
- **rf-111 修复归档 + plan-1 遗留技术债 P1 记录** — review-findings.md：rf-111 从 P2B 移至已修复表（含修复方案与变更记录）；新增 P1 小节「plan-1 交互图表遗留技术债（2026-08-02）」记录 rf-113~121——rf-113（Iter 7 浏览器人工验证 6 项未实测，test-chart.html 已备载体）、rf-114（TD3 双渲染路径，稳定 2 版本后移除 Canvas）、rf-115（TD-L2 history_data 数据裁剪）、rf-116（TD-L3 模板单文件拆分）、rf-117（A6 键盘可达性）、rf-118（Heatmap 依赖 plan-2 correlation_data）、rf-119（单图导出 PNG 可选增强）、rf-120（S5 CSP 可选）、rf-121（TD2 报告体积 ~200KB）
- **`src/js/` 更名 `src/static/`（前端静态资产目录）** — 目录实际承载 Chart.js 引擎 + 自有 JS + 独立 HTML 调试页 + README，`js/` 名不副实，更名反映"前端静态资产"语义（为未来承接 HTML/CSS/图片预留，行业惯例 static/）。同步：`html_writer.py` `_copy_js_assets` 复制源路径 `src/js` → `src/static`（运行时唯一代码引用）；4 份管理/设计文档 `src/js` 引用全量替换；`src/static/README.md` 标题 + 职责描述更新；`folders.md` 目录树 `js/` → `static/`。模板与调试页走相对路径，运行时不受影响。report 套件 1153 passed + dev-verify 1181 passed 确认复制逻辑正常
- **rf-113 验证清单备妥** — 新增 `docs-stm/plan/plan-1-iter7-verification-checklist.md`（plan-1 Iter 7 浏览器人工验证勾选清单，rf-113）：对照 upgrade.md §5 Iter 7 验收标准 2/3/4/6 + §4.8 A1/A4，6 项 × 具体操作步骤（Chrome/Edge 主验、Firefox/Safari 抽验）+ 结果汇总 + 通过后回填 changelog/review-findings 处理流程；`review-findings.md` rf-113 修复方向引用清单；`folders.md` plan/ 子树补条目
- **plan-1/plan-7 完成项设计文档归档至 `archive/v0.9.x/`** — 按用户要求将已实现任务的设计文档从 `docs-stm/plan/` 归档：① 新增 `archive/v0.9.x/archived_plan.0.9.x.md`（已完成项索引表 + 设计文档清单）；② plan-1 三个设计文档（`plan-chartjs-report-upgrade.md`/`plan-chartjs-risk-analysis.md`/`plan-1-iter7-verification-checklist.md`）`git mv` 至 `archive/v0.9.x/chartjs-upgrade/`（rf-113 清单随文档归档，review-findings/technical 引用路径同步）；③ plan-7 设计内容（原 `plan-advanced-analysis.md` §4 因子暴露分析）抽取为独立文件 `archive/v0.9.x/factor-exposure/plan-factor-exposure.md` 归档，`plan-advanced-analysis.md` 同步裁剪（仅保留 plan-4 已放弃/plan-5/plan-6 待办），目录与标题更新；④ 内部交叉引用修正（factor-exposure↔chartjs-upgrade 相对路径、`plan-chartjs-risk-analysis.md` 指向 `plan.md` 的路径、`technical.md` C7 注册引用）；⑤ plan.md 更新——已完成项移出"推荐实施顺序"，剩余项重新编号（①plan-9 ②plan-2/3 ③plan-6 ④plan-5 ⑤plan-11 ⑥plan-10 ⑦plan-8），P2 预排 ~20d→~12.5d，归档区补 v0.9.x 索引；⑥ folders.md 目录树同步（plan/ 移除 3 文件、archive/v0.9.x 子树补 5 条目、统计数 69/8→78/5）

### Test

- **`test_write_settings` 测试隔离补全** — mock 了 `open`/`json.dump` 但 `_write_llm_settings` 还调用真实 `os.makedirs('/fake/path')` + `tempfile.mkstemp` + `os.replace`，非 root 环境下 `/fake` 不可建 → `PermissionError` 使 P0 dev-verify 门禁失败（rf-105）。修复：补全 fs 写路径 4 个 mock（`os.makedirs`/`tempfile.mkstemp`/`os.fdopen`/`os.replace`）+ `assert_called_once()` 断言，测试隔离完备且不依赖根目录可写权限

---

## [0.9.4] - 2026-08-01

### Fix

- **test_runner.py GBK 控制台打印崩溃** — 子进程捕获输出经 `errors="replace"` 处理后含 U+FFFD 替换字符，直接 `print` 到 GBK 控制台抛 `UnicodeEncodeError`，Phase A 后 runner 崩溃导致 Phase B 不执行。修复：模块顶部 `sys.stdout.reconfigure(errors="replace")` 兜底（异常时静默跳过）
- **`test_tencent_success` mock 目标笔误导致静默真调 API** — `fetch_indices` 主链路实际调用 `tencent.fetch_index_price`，测试却 mock 了 `tencent.fetch_price`：有外网时真调成功侥幸通过，无外网环境暴露（返回空 → 断言失败）。修复：mock 目标对齐 `fetch_index_price` + 新增 `mock_fetch_price.assert_called()` 回归守卫，杜绝 mock 目标漂移
- **TUI [S] 菜单泄漏旧设计遗留辩论三模块（僵尸开关）** — 辩论白脸/黑脸/综合（`debate_pro`/`debate_con`/`debate_synthesis`）注册表条目保留，但作为 LLM 模块泄漏进 [S] 面板显示为 6/7/8 开关（写入 `enabled_llm` 后无任何生成路径消费，切换无效）。修复：菜单层过滤——`tui_menu.py` 新增 `LLM_MENU_HIDDEN_KEYS` 常量与 `filter_menu_llm_modules()` 辅助函数，`handlers_config.py` [S] 面板与 TUI 模型路由显示同步过滤；注册表条目原样保留（缓存 TTL/前缀清理仍依赖）。修复后 [S] 面板恢复文档描述的标准 5 模块 + 实验 6-8（正反辩论/条件推理/集中度问答）
- **LLM 空内容误判"内容被过滤"→ 根因区分 + 修复无效安抚重试** — DeepSeek V4 兼容端点为强制推理模型，`thinking` 与 `text` 共享 `max_tokens` 预算；思考部分耗尽预算时响应仅含 `thinking` block 无 `text`（复现：effort=high + max_tokens=4096 稳定触发）。`_extract_content` 对无 text block 的响应区分根因：`stop_reason=max_tokens` 记录"思考耗尽预算"日志（建议增大 max_tokens/降低 effort），其他仍记录"可能被内容过滤"；统一返回 `None` 走 provider 切换，替代对空内容追加安抚指令的无效重试
- **health_check `max_tokens` 4096→8192 + effort high→medium** — 实测（mt=8192 + effort=high 输出 5172 tokens 正常）验证增大预算可消除空 text；expert_review effort high→medium 缩短 thinking 预留文本预算。同步生产 `llm_settings.json`、默认模板 `_llm_defaults.py`

### Test

- **`test_tencent_success` mock 目标回归守卫** — 断言腾讯主链路 mock 实际被调用，防止 mock 目标与代码调用漂移后静默真调 API
- **辩论模块菜单过滤回归测试** — 新增 `TestFilterMenuLlmModules` 2 用例：过滤后仅剩 5 个标准模块（不含 `debate_pro`/`debate_con`/`debate_synthesis`）、注册表仍保留辩论三模块条目
- **`_extract_content` 空 text 回归测试** — edge 新增 `TestExtractContentEdge` 3 用例：仅 thinking + max_tokens → None 且记录预算耗尽日志（不误报过滤）、仅 thinking + end_turn → None 且记录过滤日志、thinking+text 并存正常返回；同步 4 处既有断言（空列表/仅 thinking → None）

### Docs

- **how-to-menu.md [S] 章节补充三段式说明** — 新增"6/7/8 与白脸/黑脸/综合的关系"注解：正反辩论（编号 6）内部即为白脸→黑脸→综合三段式，非独立开关；旧设计遗留的独立模块开关已从菜单隐藏（注册表保留仅用于缓存）
- **4 份用户手册同步 [S] 面板布局与辩论三模块说明** — how-to-config.md（features 章节补充 [S] 面板分组注解）、how-to-config-llm.md（模块启停补充菜单分组与三段式说明）、reports-instruction.md（§12 智囊团复盘补充辩论模式增强说明 + 对照表新增辩论式复盘行）、how-to-use-registry.md（辩论三模块标注"仅缓存管理用途、菜单已隐藏"，LLM 名称/键名查询与消费方清单同步）
- **review-findings.md rf-99 标记已修复** — 详细说明移至 changelog，摘要行保留于已修复表
- **how-to-config-llm.md 调优参数同步** — 参数表新增 `reasoning_effort` 列；health_check max_tokens 4096→8192；expert_review / health_check effort 标为 medium（非统一 high）；失败降级表区分"返回空内容（None）→ 切换 Provider"与"空字符串 → 安抚重试"；Extended Thinking 章节补充 DeepSeek V4 强制推理说明（thinking+text 共享 max_tokens 预算）与空内容调参建议（增大 max_tokens / 降低 effort）
- **llm-technical.md 空内容处理与参数同步** — 参数表 health_check 4096→8192；调用链/§5.1/§6.1 四层容错更新空内容处理（`_extract_content` 无 text block → None → 直接切换 provider；仅真正空字符串 `""` 安抚重试）；effort 兜底说明（模板默认 expert_review / health_check 为 medium）；附录 A `reasoning_effort` 枚举补 `low`/`max`
- **technical.md LLM 章节空内容处理同步** — §5.2 调用链、§5.5 关键机制表"内容过滤安抚"改为"空内容处理"（None 切 provider / "" 安抚重试）
- **review-findings.md rf-98 标记已修复** — 详细说明移至 changelog，摘要行保留于已修复表

## [0.9.3] - 2026-07-31

### Fix

- **`set_config` 并发读-改-写竞态导致丢失已有配置项** — `_core.py`：`_config_lock` 改 `threading.RLock`；`set_config` 整个读-改-写纳入锁内串行化（并发线程不再基于旧快照覆盖写）；`get_config(_strict=True)` 文件存在但读取失败时抛异常中止写而非静默回退默认配置覆盖（P2 verify 门禁在 xdist 4-worker 下暴露：并发测试 `final.get("base")` 为 None）；新增损坏文件不覆盖回归测试
- **辩论虚构过滤按"行"删除导致整段误删** — `_hallucination_filter.py` 过滤粒度从"整行"改为"行内句段"（先按行、行内再按句末标点切分），markdown_to_html 输出的单行 HTML 不再因一个误判 token 被整段清空（6412 字符→0 字符→白脸失败回退普通模式）
- **虚构过滤时机下移** — `skeleton.py` 新增 `raw_filter_fn` 钩子，在 markdown_to_html 之前对 LLM 原始输出过滤（作用于带换行的 Markdown）；`generators.py` 辩论 pro/con/synthesis 三处手动过滤收敛到骨架一处，synthesis 顺带获得过滤保护
- **虚构代码误报降低** — `_is_safe_word` 豁免 `TOP\d+`（提示词附录 TOP3 块回声），白名单新增 `smart`/`money`（Smart Beta/Money 等金融术语）
- **`max_tokens_penetration_deep` 4096→8192** — 同步生产配置 `llm_settings.json`、默认模板 `_llm_defaults.py`、`how-to-config-llm.md`，避免穿透深度分析输出撞 max_tokens 上限触发 1.5× 重试
- **test_runner.py subprocess UnicodeDecodeError** — 两处 `subprocess.run` 添加 `errors="replace"`，防止 Windows 子进程输出非 UTF-8 字节时崩溃
- **回撤数值误判窗口收窄** — `_is_drawdown_context` 近邻守卫窗口 30→15 字符，避免跨分句误判"累计"为收益率关键词
- **辩论模式 synthesis 条件推理注入补全** — `_build_debate_synthesis_prompt` 新增 `enable_conditional` 参数，辩论+条件推理同时开启时 synthesis 阶段追加配置化情景分析，弥补 pro/con 跳过情景分析的空缺
- **缓存测试 patch 路径修复** — `test_handlers_cache.py` 的 `@patch` 目标从 `providers.akshare_extras` 修正为 `fetcher.akshare`（模块加载本地绑定导致 xdist 并行下间歇性失败）
- **新闻去重测试用例同步** — `test_cross_source_english_token_only_overlap` 预期合并 1 条；`test_cross_source_bg2_low_ratio_kept` 替换测试数据

### Test

- **set_config 并发竞态回归测试** — 新增 `test_set_config_raises_on_corrupt_file`（edge）：配置文件损坏时 `set_config` 抛异常且不覆盖原文件，杜绝静默回退默认配置覆盖写丢数据；原并发测试 `test_concurrent_set_config_thread_safe` 修复后 5 连跑稳定通过
- **虚构过滤回归测试** — 新增 4 用例：`test_sentence_level_removal_same_line`（行内句段删除）、`test_top_rank_suffix_not_filtered`（TOP2/TOP3 豁免）、`test_smart_term_not_filtered`（Smart 豁免）、`test_filter_single_line_html_keeps_other_sentences`（单行 HTML 不整段清空，edge）
- **测试用例数据更新** — 同步 bg=2 梯度阈值 0.40 更新后的去重预期行为

### Docs

- **llm-technical.md 骨架流程同步** — 骨架执行 ASCII 图新增 `③' 原始输出过滤（可选）` 步骤（`raw_filter_fn` 钩子，位于截断处理之后、markdown_to_html 之前）；模块表更新 `skeleton.py` 描述与 `generators.py` 辩论生成说明；`max_tokens_penetration_deep` 参数表 4096→8192
- **technical.md 虚构过滤架构表行更新** — 描述改为"句子级删除 + `raw_filter_fn` 钩子时机下移"，同步 C 约束表对应行的设计说明
- **test-coverage.md 统计快照更新** — all 3806 / unit 3494 / standard 2957 / verify 2248 / edge 474 / unit_llm 650 / LLM 功能域 683（2026-07-31 实时收集）
- **folders.md 目录树与统计项更新** — 主程序 182/43422、脚本 10/3460、源码合计 193/48744、测试代码 217/59014、测试用例 3806；目录树含 `src/test/data/hallucination/` 两个 gitignore 测试数据集文件
- **how-to-config-llm.md `max_tokens_penetration_deep` 8192** — JSON 示例与参数表行同步
- **review-findings.md rf-96 标记已修复** — 详细说明移至 changelog，摘要行保留于已修复表

## [0.9.2] - 2026-07-31

### Feat

- **事实校验 v3：自动修正机制** — `fact_checker.py`：`check_numerical_consistency` 返回 `(issue, correction)` 二元组、`run_fact_check` 返回 `(corrected_html, summary_html)`、`apply_numerical_corrections` 支持正则级联替换；新增 `tolerance_pct` + `tolerance_overrides` 逐模块容差、pp 混淆语境跳过策略
- **Prompt 防御统一注入架构** — `prompts_tables.py` 新增 `_build_prompt_appendix`（TOP3 排名 + 数据速查表 + 代码白名单），在 `skeleton.py:_run_standard_mode()` 自动注入到所有模块的 user prompt 末尾，各模块无需手动调用；`prompts_action.py` 移除各模块的手动防御调用
- **跨源 bg=2 梯度阈值调低至 0.40** — `news_dedup.py` 的 `cross_merge_bg2` 规则从 `ratio≥0.45` 降至 `ratio≥0.40`，基于校准报告（119654 条锚点）发现 bg≥2+ratio≥0.35 区间有 580 条含实体重叠被跳过，0.40 可额外捕获约 300-400 条真实重复，bg=2 已提供实体重叠安全垫
- **辩论模式 synthesis 条件推理注入** — `prompts_action.py:_build_debate_synthesis_prompt` 新增 `enable_conditional` 参数，辩论+条件推理同时开启时在综合阶段追加配置化情景分析（涨/跌/震荡三情景），弥补 pro/con 因 `skip_scenarios=True` 跳过情景分析的空缺

### Fix

- **辩论模式 synthesis 重复白脸/黑脸观点 + 情景分析** — `prompts_core.py:_SYSTEM_DEBATE_SYNTHESIS` 重写：明确禁止 synthesis 重述双方论点（"读者已阅读过原文"）、禁止插入情景分析段落；输出结构从"关键分歧点→分歧定论"改为"共识与分歧摘要→综合评估"，压缩 LLM 重复论述空间
- **`_build_debate_synthesis_prompt` 错误标记 HTML 为 markdown 代码块** — `prompts_action.py:463` 中 ` ```markdown ` → ` ``` `（pro_text/con_text 已是 HTML，标记为 markdown 误导 LLM）
- **LLM 持仓排名幻觉** — `_build_code_whitelist_block` 声明 #1 品种身份，阻止 LLM 将非排名 #1 的代码断言为"最大持仓"
- **LLM 数值混淆（pp 贡献占比 ↔ 收益率）** — `_build_data_slot_block` 提供精确逐品种收益率，`fact_checker` 增强 pp 语境检测
- **`_SYSTEM_EXPERT_REVIEW` 情景分析双重指令** — 从 system prompt 移除"### 情景分析"段（第54-66行），移至 user prompt builder 作为单一注入点；`_build_expert_review_prompt` 新增 `skip_scenarios` 参数，辩论 pro/con 跳过情景分析避免双重输出
- **回撤数值误判为收益率** — `fact_checker.py`：新增 `_DRAWDOWN_KEYWORDS` 和 `_is_drawdown_context`（全句扫描回撤关键词+ match 前 15 字收益关键词近邻守卫，避免跨分句干扰），回撤语境数值改与实际 `max_drawdown_pct` 比较而非与组合累计收益率比较；告警消息增加句段截图（`句段：...`）辅助定位
- **已修正值不重复告警** — `run_fact_check` 中已自动修正的数值不再在 ⚠ 告警明细中重复列出（仅保留"自动修正 N 处"摘要），用户看到的内容中已不存在该值即不警告

### Test

- **事实校验测试扩展** — 新增 `test_pp_vs_rate_confusion_detected`、`test_contribution_sentence_skips_pp_values`、`test_tolerance_override_looser` 三个测试用例
- **回撤语境检测回归测试** — 新增 6 用例：`test_drawdown_value_within_tolerance`（19.0%≈18.97%→通过）、`test_drawdown_value_out_of_tolerance`、`test_drawdown_value_no_data_skips`、`test_drawdown_mixed_with_profit_in_sentence`（分句感知）、`test_issue_message_contains_sentence_snippet`（句段截图验证）、`test_run_fact_check_corrected_values_not_in_warnings`（已修正不重复告警）
- **辩论 synthesis 测试同步** — `test_system_debate_synthesis_contains_placeholders` → `test_system_debate_synthesis_contains_instruction_keywords`（验证"不要重复"指令）；`test_output_contains_markdown_code_block` → `test_output_contains_code_block`
- **场景分析指令迁移测试** — 新增 `TestBuildExpertReviewPromptSkipScenarios` 3 用例（`skip_scenarios=True` 剔除场景、默认保留场景、不影响其他内容块）
- **统一注入防御专用测试** — 新增 `TestBuildPromptAppendix` 4 用例（空持仓、单品种含三块、多品种排序验证、零市值防除零）
- **测试适配** — `test_mode2_disabled` 改为断言标准场景存在（场景指令已从 system prompt 移入 user prompt）；`test_system_expert_review_constant` 改用"置信度指引"代替已移除的"情景分析"断言
- **新闻去重测试用例同步** — `test_cross_source_english_token_only_overlap` 从预期保留 2 条改为预期合并 1 条（匹配 bg=2+ratio≥0.40 新规则）；`test_cross_source_bg2_low_ratio_kept` 替换测试数据（改用 ratio≈0.375 的"科技板块持续走强"vs"国际油价持续走弱"验证 <0.40 不合并）
- **缓存测试 patch 路径修复** — `test_handlers_cache.py:TestRefreshDividendCache` 中 `test_with_valid_codes` 和 `test_empty_holdings` 的 `@patch` 目标从 `src.python.providers.akshare_extras.get_dividend_data` 修正为 `src.python.fetcher.akshare.get_dividend_data`（模块加载时本地绑定导致 xdist 并行下间歇性失败）

### Docs

- **全文档路径引用同步** — 子包重构后（`core/`、`tui/`、`cli/`、`config/`）过期路径集中清理：`technical.md`（~20 处）、`llm-technical.md`（5 处）、`test-coverage.md`（6 处）、`testplan.md`（6 处）、`review-findings.md`（3 处）、`how-to-schedule.md`（2 处）、`plan-correlation-drawdown.md`（4 处）、`plan-chartjs-report-upgrade.md`（2 处）、`plan-chartjs-risk-analysis.md`（11 处）
- **校准报告归档** — `calibrate-dedup-threshold.py` 输出保存至 `docs-stm/tmp/dedup-calibration-report.md`，含 `cross_merge_bg2` 新规则基线数据（119654 条锚点）
- **requirements.md §11.4 `proxy_preferred` 措辞修正** — "proxy_preferred 策略使用" → "per-provider 后处理标记，有代理环境时自动前置"，与 §7.1 R-LLM-06 定义保持一致
- **testplan.md 菜单选项数同步** — §1.1 tui/tui_menu.py 和 §3 TUI 菜单行中 "15 选项" → "16 选项"（同步菜单已新增 [I] 管理对比指数池的当前状态）

## [0.9.1] - 2026-07-30

### Refactor

- **src/python/ 根文件归入子包** — 将 17 个根目录文件分别迁入 `core/`（基础设施）、`tui/`（TUI 入口）、`cli/`（CLI 入口）、`config/`（配置模块）四个子包；`handlers_check_sources.py` 因 CLI/报告共享迁入 `core/check_sources.py`；新增 `__init__.py` re-export 保持导入兼容；新增 `__main__.py` 支持 `python -m`；移除死代码 `_breaker_state.py`

### Docs

- **folders.md 目录树同步** — 根文件迁移后目录树更新至子包结构（core/cli/tui/config）
- **文档路径引用同步** — `faq.md`、`how-to-config.md`、`how-to-start.md`、`how-to-use-registry.md`、`scripts-reference.md`、`requirements.md`、`technical.md` 中过期路径全部更新为子包路径（`src/python/constants.py` → `src/python/core/constants.py` 等）
- **technical.md 附录 A 目录树更新** — 替换为最新子包结构

### Fix

- **CLI 测试 patch 路径修复** — `__init__.py` re-export 导致 mock 路径需加 `.cli` 层级，`test_cli.py` 和 `test_cli_edge.py` 共 6 处 patch 路径修正
- **technical.md 附录 B 标题重复** — 附录替换脚本导致的重复标题修复

## [0.9.0] - 2026-07-30

### Chore

- **ruff 版本锁定 + 全量格式修正** — `pyproject.toml` 锁定 `ruff==0.15.20`（精确版本，避免版本升级导致格式噪音）；全量运行 `ruff format src/python/ scripts/`，修复 CI ruff 格式检查报错
- **版本格式统一** — 管理文档版本头统一去除 `v` 前缀（如 `v0.8.12-dev` → `0.8.12-dev`），`check-version-consistency.py` 模板同步（`v{v}` → `{v}`），涉及 9 份文档

### Docs

- **review-findings.md 归档整理** — 0.8.* 已发布版本的已修复记录（rf-1~rf-64、rf-66~rf-135、rf-106~rf-107）迁移至 `archived_review-findings.0.8.x.md`，归档链接路径修复（`archive/0.8.x/` → `archive/v0.8.x/`）
- **plan.md 归档整理** — 0.8.* 已完成项（plan-12 数据源可用性矩阵、plan-13 数据源可靠性文档、plan-14 ADR）迁移至 `archived_plan.0.8.x.md`
- **changelog.md 归档整理** — v0.8.11 变更记录迁移至 `archived_changelog.0.8.x.md`

## 归档

- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

