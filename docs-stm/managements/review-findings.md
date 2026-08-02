# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.7-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C19）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P1 — probe 探测发现（plan-7 决策相关，2026-08-01）

（无待处理项 — rf-102/103/104/106 已全部处理，见"已修复"表）

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> 来源：`archive/v0.9.x/chartjs-upgrade/plan-chartjs-report-upgrade.md` §4.5/§4.7/§4.8/§4.10/§5 Iter 7 + `archive/v0.9.x/chartjs-upgrade/plan-chartjs-risk-analysis.md` §4 TD 表。
> plan-1 代码与自动化测试已落地（dev-verify 1181 passed），以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | ①③⑤ 可用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 已补齐载体）；②④⑥ 需真实浏览器/微信实操——**勾选清单已备**：`docs-stm/archive/v0.9.x/chartjs-upgrade/plan-1-iter7-verification-checklist.md`（含 6 项 × 具体操作步骤 + 结果汇总），按清单勾选完成后回填 changelog |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器 |
| **rf-115** | TD-L2：`history_data` 数据同时服务 Excel + HTML Chart.js，模板 `tojson` 序列化全量字段（含 Excel 不需要的字段） | plan-2/plan-3 引入 chart_data 专用裁剪 |
| **rf-116** | TD-L3：模板仍为单文件 ~2000 行（Chart.js 初始化 JS 已外部化缓解，Canvas 函数 + 条件分支仍占体积） | 独立技术债迭代做章节级 partial 拆分 |
| **rf-117** | A6 键盘可达性未做（Chart.js tooltip 为鼠标悬停驱动，键盘聚焦不触发） | 设计明确"不做 MVP 记入技术债"（upgrade.md §4.8 A6）；如需支持，给 chart-init.js 加键盘交互扩展 |
| **rf-118** | 相关性矩阵 Heatmap 仅占位文本（Chart.js Matrix 插件未引入） | 依赖 plan-2 提供 `correlation_data` 后引入 `chartjs-chart-matrix` 渲染（Iter 7 已推迟，非 YAGNI） |
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
| rf-119 | plan-1 遗留：单图导出 PNG 按钮未做（`chart.toBase64Image()` 已用于打印快照，可复用） | 新增 `src/static/chart-export.js`：提供 `window.ChartExport.register(chart, key)`，为每张 Chart.js 图表在 `.chart-box` 内注入「导出PNG」按钮（有 `.chart-title` 时进标题栏，否则绝对定位右上角），点击 `toBase64Image()` 2x 分辨率下载 PNG；`chart-init.js` `trackChart` 传入各图 key；模板/调试页加载顺序 chart-config → chart-export → chart-init，`_copy_js_assets` 同步复制新文件；打印时按钮隐藏 | `changelog.md` → Fix / Test |
| rf-150 | 集中度问答开关开启但报告无输出 + 资产穿透 TOP10 两柱状图难区分/小屏不齐（用户反馈 2026-08-02，他机运行报告）：① `_build_qa_concentration_block` 输出"（以上问题旨在引发思考，无需在本次报告中回答。）"仅引导不要求回答；② 辩论综合权衡（synthesis）阶段完全不支持集中度问答（`_build_debate_synthesis_prompt` 只接受 `enable_conditional`），而用户在辩论模式下看到的主体正是综合权衡 → 与需求 R-LLM-DB-QA-CONCENTRATION-03（要求输出量化评估/基准对比/调仓建议）矛盾；③ `_build_expert_review_prompt` 调用时 threshold=0.20 硬编码未读 llm_settings 配置（违反 R-04）。柱状图：行业分布/穿透 TOP10 均主色蓝难区分 + flex 并排小屏不齐 | ① `_build_qa_concentration_block` 改为要求回答（输出量化评估/基准对比/调仓建议，删除"无需回答"免责声明，标题改"### 集中度问答"）；② `_build_debate_synthesis_prompt` 新增 `enable_qa_concentration`/`industry_concentration`/`holdings_details`/`total_mv` 参数并追加集中度问答引导段；`_build_system_debate_synthesis` 新增 `enable_qa_concentration` 追加 `_SYSTEM_DEBATE_SYNTHESIS_QA_APPENDIX`（不重写编号结构避免与 conditional 冲突）；`generate_debate_procon` 传入 qa 参数；③ threshold 从 `get_llm_config() debate.qa_concentration.threshold` 读取（标准+辩论两路径）。柱状图：`ChartTheme.barColors`（蓝/橙）+ 模板 `--chart-bar-2` CSS 变量，穿透图背景/边框改橙、行业图蓝；`.penetration-charts` 两子 div 改 `flex:1 1 100%; max-width:720px` 分两行居中。新增 9 个回归用例（要求回答引导/合成阶段 qa 追加与禁用/配置阈值读取双向/synthesis 与 system prompt qa 附录/组合模式/expert_review 阈值两向） | `changelog.md` → Fix / Test |
| rf-151 | LLM provider `priority` 默认值显示不一致（文档核查 2026-08-02）：`_llm_providers.py`/`strategy.py` 实际默认 `priority=99`，但 TUI/CLI 状态显示文案与 `how-to-config-llm.md` 字段表/示例均写"默认 50"——用户省略 `priority` 时按 99 路由（末位兜底），显示却说 50，误导配置判断 | `cli.py` / `tui_menu.py` 显示文案 `50（默认）`→`99（默认）`；`how-to-config-llm.md` 字段表 + TUI 输出示例同步为 99 | `changelog.md` → Fix |
| rf-152 | P2 门禁偶发失败（2026-08-02）：`test_llm_content.py::TestWriteLlmSheets::test_content_none` 在 verify 并行套件（xdist 8 worker）偶发失败、单例通过。根因：`write_llm_sheets` 读取模块级全局 `LLM_MODULE_FAILURE` 判断模块禁用，某测试残留 `FAIL_REASON_DISABLED` 未清理 → 同 worker 后续用例页签被跳过不写入，A2 占位符断言失败 | `conftest.py` 新增 `_auto_reset_llm_module_failure` autouse fixture 每测试前置空 `LLM_MODULE_FAILURE`（与既有 `_auto_reset_*` 模式一致）；新增回归用例 `TestLlmModuleFailureReset::test_autouse_fixture_clears_polluted_state` 验证清理逻辑。P2 复跑 2555 passed、verify 2325 passed | `changelog.md` → Fix / Test |
| rf-149 | Excel 端 LLM 内容分段缺陷（用户报告检查 2026-08-02）：`_write_content_sheet` 按 `\n\n` 分段，但真实内容由 `markdown_to_html` 无换行拼接 `<p>` → ① 整模块坍缩一格 ② orchestrator 单 `\n` 追加摘要致 footer 排除守卫失效、footer 重复 ③ 校验摘要明细行（⚠/ℹ/已修正明细）样式坍缩丢失 | `llm_content.py` 新增 `_split_html_blocks`（按块级标签分段 + 游离 `<span>` 并入前块 + 纯文本 `\n\n` 回退）、`_write_fact_check_block`（摘要首行绿/琥珀、明细行灰色小字）、`_FACT_CHECK_DETAIL_FONT`；`_write_content_sheet` footer 去重。**技术债加固**（同日）：`_strip_html` 块级结束标签转换行+折叠连续换行、`_calc_row_height` 逐行估算、`<hr>` 分块、游离文本补 `\n` 防二次分段。16 个回归用例；dev-verify 1198 passed | `changelog.md` → Fix / Test |
| rf-145 | 辩论 synthesis 综合权衡**重复复述白脸/黑脸观点**（用户实测报告 2026-08-02）：综合权衡出现完整"四、情景分析"段落，且上涨/下跌/震荡各段反复引用"黑方指出同质化风险""白方指出防守资产缓冲"。根因：`llm_debate_conditional`（条件推理）开启时，pro/con 因 `skip_scenarios=True` 不写情景分析（`generators.py` 辩论模式强制跳过），改由 synthesis 的 `_build_debate_synthesis_prompt` 注入"按涨/跌/震荡情景给出综合建议"指令；但 `_SYSTEM_DEBATE_SYNTHESIS` 仍残留 rf-93 时代"情景分析已在白脸/黑脸观点中给出，不要在综合权衡中再次插入情景分析段落"的**过时断言**——system prompt 与 user prompt 直接矛盾，LLM 为满足情景指令只能从白脸/黑脸正文抽取内容填充 → 复述双方观点。rf-93 当年仅改 prompt 文案（软约束），conditional 功能合入后未同步更新 system prompt 造成回归 | `_SYSTEM_DEBATE_SYNTHESIS` 保留为 conditional 关闭基线（维持"禁止插入情景分析"）；新增 `_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL` + `_build_system_debate_synthesis(enable_conditional)`，conditional 开启时改用强化版——明确允许按 user prompt 输出情景分析（消除指令冲突）+ 强化引用纪律（综合评估/行动建议/情景分析三部分均"引用一句话概括、不得展开复述"）+ 要求各情景差异化且不与正文机械重复；`generators.py` synthesis 阶段按 `_enable_conditional` 动态选择 system prompt。新增 4 个回归用例（conditional False=基线 / True=允许情景+不复述+无冲突断言 / 开关切换内容变化 / generators 层 conditional 开启时 system_prompt 切换为强化版） | `changelog.md` → Fix / Test |
| rf-146 | 新闻去重 bg=2 梯度阈值**显示不一致**（校准脚本 2026-08-02 复跑）：0.9.2 将代码阈值 0.45 调低至 0.40 时未全量同步——`news_dedup.py` docstring 仍写"共享 ≥ 2 个实体 bigram 且 ratio ≥ 0.45 → 合并"，`calibrate-dedup-threshold.py` 的 `_CROSS_BG2_RATIO = 0.45` 常量、梯度规则注释及「当前阈值规则」显示均仍为 0.45，而 `_dedup_by_title` 实际执行 `ratio >= 0.40`。校准报告展示的阈值规则与实际代码不符，会误导后续调参判断 | 三处 0.45 → 0.40 全量同步：`news_dedup.py` docstring、`calibrate-dedup-threshold.py` 注释块/`_CROSS_BG2_RATIO`/显示打印。行为零变化（规则本身早已按 0.40 生效）。回归护栏：既有边界测试 `test_cross_source_bg2_high_ratio_merged`（ratio≈0.43 ≥ 0.40 合并）/ `test_cross_source_bg2_low_ratio_kept`（ratio≈0.375 < 0.40 保留）已锁定 0.40 边界 | `changelog.md` → Fix |
| rf-147 | 资产穿透 TOP10 两图风格**不统一**（用户反馈 2026-08-02）：穿透章节两图并排，行业分布图为 `indexAxis: 'y'` 水平条，穿透 TOP10 为垂直柱状图，横竖混排观感割裂 | `chart-init.js` `initIndustryBar` 移除 `indexAxis: 'y'` + scales 改为垂直配置（x 轴类别 `maxRotation: 45`、y 轴数值网格），与 `initPenetrationBar` 竖桩统一；`report_template.html` / `test-chart.html` 两图 aria-label 统一为「垂直柱状图」（穿透 TOP10 补"垂直"前缀，语义与渲染一致）；`reports-instruction.md` 描述同步。新增回归测试 `test_industry_and_penetration_bars_both_vertical`（两图 aria-label 均含"垂直柱状图"、无"水平"残留） | `changelog.md` → Fix |
| rf-148 | 事实校验自动修正明细**不可见**（用户反馈 2026-08-02，他机运行报告）：校验摘要仅显示"自动修正 N 处数值"计数，修正明细（wrong%→correct% + 句段）不落盘、不在摘要展开，用户无法得知具体修正了哪些数值 | `run_fact_check` 自动修正后 ① 修正明细写入 `invest` 日志（模块标签 + 逐条 `wrong%→correct%（句段）`）；② HTML 校验摘要追加灰色小字「已修正明细: …」行（追加在模块章节尾部，供用户直接查看）。新增回归测试 `test_corrections_detail_in_summary` / `test_corrections_logged`。不破坏既有格式（`llm_content.py` 摘要正则匹配宽松） | `changelog.md` → Fix |

> 0.9.0 ~ 0.9.5 已修复问题记录（rf-90 ~ rf-144）已迁移归档至 [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md)，本表仅跟踪当前迭代（0.9.7-dev）修复项。

---

## 归档

### 归档档案

- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.5（2026-07-30 ~ 2026-08-02）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
