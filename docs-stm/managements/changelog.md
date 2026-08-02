# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.5-dev] - 2026-08-01

### Fix

- **chart：持仓分类饼图全"其他"（rf-136）** — 持仓分类表下方饼图（category_doughnut）仅显示"其他"占 100%。根因：`_build_category_doughnut_dataset` 从 details 按 `property` 聚合，但真实 `DetailRow` 无 `property` 字段 → 走 `_infer_property`；旧实现 `if code[:1] in ("6","0","3") and not name` 要求名称为空才判股票，而真实明细行始终有名称 → 全部落入"其他"。修复：① `_infer_property` 仅按代码前缀分类（6/0/3→股票，5/1→基金，无匹配→其他），不再依赖 name 判空；② `_build_category_doughnut_dataset` 双数据源——优先 cat_data（`_categorize_holding` 权威分类，按 `sub_mv` 聚合），回退 details；③ `write_html_report` 用本地计算的 cat_data 补齐/覆盖 category_doughnut，保证饼图与持仓分类表同源
- **chart：穿透章节误报"行业/穿透数据暂不可用"（rf-137）** — 资产穿透 TOP10 章节开头提示"行业数据暂不可用/穿透数据暂不可用"，但下方表格有穿透数据。用户场景为**部分失败**（12 只基金中仅 1 只无法获取穿透，合计市值 7,589.70 元未计入 TOP10，`penetration_sheet` 页脚已正确标注"无法获取穿透的基金"）。根因：`_build_chart_datasets_for_report` 构建 chart_datasets 时未传 penetration → industry_bar/penetration_bar 返回空 → 模板渲染占位提示。修复：`write_html_report` 用本地计算的 penetration（含 top10）补齐/覆盖 industry_bar/penetration_bar（R11 单图独立 try/except）；空值语义保持——仅全量不可用时才显示"暂不可用"，部分失败（top10 有数据）正常渲染图表
- **rf-122：config.json 路径型键落盘绝对路径导致跨机器不可移植** — `get_config()` 在内存把相对路径绝对化（`_absolutize_paths`），`set_config()` 却拿绝对化后的 dict 直接 `json.dumps` 全量写回 → 本机绝对路径（`D:\codebase\...`）落盘并随 git 提交，换机器/换目录后 `holdings_dir`/`output_dir` 等全部失效；`llm_providers_file` 等尚未绝对化的键在下次任何 `set_config()` 触发时也会被污染。修复：① `_validation.py` 新增 `_deabsolutize_paths()`（与 `_absolutize_paths` 对称）——仅将 PROJECT_ROOT 之下的绝对路径还原为相对路径，跨盘（Windows 不同盘符 relpath 抛 ValueError）与项目外路径（relpath `..` 越界）保持原样；② `set_config()` 写盘改用浅拷贝 + 先反绝对化再序列化，且不污染 `_config_cache`（原子写失败时缓存仍保持绝对路径内存值）；③ `_config_defaults._build_template_from_defaults()` 模板同样反绝对化——全新安装首次生成 config.json 也写相对路径；④ 恢复 `data/config/config.json` 中 4b403a3 提交的 4 个绝对路径键为相对路径
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

- **chart 分类饼图 + 穿透补齐回归测试** — `test_chart_data_builder.py` TestCategoryDoughnut 新增 4 用例：`test_infer_property_named_stock_classified_by_code`（真实 DetailRow 含名称按代码前缀分类，不再全"其他"——rf-136 回归）、`test_category_doughnut_prefers_cat_data`（cat_data 权威数据优先于 details）、`test_category_doughnut_from_cat_data_aggregation`（同 property 多组聚合 + _CATEGORY_ORDER 排序）、`test_category_doughnut_from_cat_data_empty`（空 cat_data 不崩溃）；`test_html_writer.py` 新增 `TestWriteHtmlReportChartMerge` 5 用例（write_html_report 补齐 category_doughnut/industry_bar/penetration_bar、部分失败仍渲染——rf-137 回归、Flag 关闭跳过补齐、chart_datasets=None 跳过）。report 套件全绿（P0 dev-verify 1181 passed）
- **rf-122 回归测试** — `test_config.py` 新增 4 用例：`test_init_template_writes_relative_paths`（全新安装模板写相对路径，可移植）、`test_set_non_path_key_preserves_relative_paths`（写非路径键如隐私提示 → 5 个路径键保持相对——生产实际触发场景）、`test_set_relative_path_value_kept_relative`（写相对值落盘仍相对 + 读取时被绝对化）、`test_set_external_absolute_path_kept`（项目外绝对路径不被误相对化，越界保护）。config 套件 182 passed
- **chart 行业分布边缘回归测试** — 新增 `test_chart_data_builder_edge.py`（C12 合规）：全部无行业归属→归入"其他"、None/空串/纯空白 sector 归一化、mv 为 None/负值不崩溃、top10 空列表占位；`test_chart_data_builder.py` 补 Iter 4/5 验收用例（行业市值总和与穿透口径一致、最多 10 个行业截断、穿透品种 <3 仍渲染）
- **chart Radar 降级与 Flag 过滤测试** — `test_chart_data_builder.py` TestRadar 新增 6 用例（metrics_sharpe 关闭→该轴 "N/A"、全关→6 个 "N/A"、全 N/A 占位保轴、risk_metrics 兜底 degraded+note、history 兜底 degraded+note、全量路径无 note）；`test_chart_data_builder_edge.py` 新增 4 用例（all_metrics 与 risk_metrics 均 None→空、all_metrics=None+history 降级、未知 flag 名不影响该轴、部分指标缺失→N/A 其余保留）；`test_html_report_structure.py` 结构测试 3 用例（radar 有 labels 渲染 canvas、无 labels"量化指标数据不足"占位、data_unavailable"持仓市值数据不可用"占位）+ 既有 2 用例 chart-box 计数更新（3→4 / 5→6）
- **rf-102/103 回归测试** — `test_tencent_edge.py` 新增 2 例（API 返回 list 非 dict 不崩、days=3650 钳位到 2000）；`test_sina_edge.py` 新增 1 例（days 钳位 2000 对齐 Tencent），防超限崩溃与钳位逻辑回退
- **rf-111 回归测试** — `test_html_report_structure.py` 新增 `TestHtmlInteractiveCharts::test_all_chart_canvases_have_a11y_attrs`：6 图全部渲染（Flag ON + 数据存在）时断言各 canvas 含 `aria-label`（含"悬停查看"）/`role="img"`/内嵌 fallback 文本非空，防 A1 属性回退
- **rf-122 回归测试** — `test_llm_api.py` `TestCallClaudeThinkingDegradation` 新增 3 例：①思考耗尽（stop_reason=max_tokens 无正文）→ 自动关闭 thinking 重试一次且恢复 temperature（断言 2 次调用、第二次 payload 无 thinking、返回第二次结果）；②flag False（非思考耗尽空内容）→ 不重试；③未注入 thinking → 即使 flag True 也不重试（短路由不误触）

### Docs

- **rf-122 归档 + review-findings.md 已修复表** — rf-122（config.json 路径型键落盘绝对路径）从待处理移至已修复表（摘要行），详细修复说明见 changelog Fix 条目；config.json 相对路径恢复后已确认磁盘相对 + 运行时绝对化双向一致
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

