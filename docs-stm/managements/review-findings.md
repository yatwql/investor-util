# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：0.9.6-dev
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
| rf-145 | 辩论 synthesis 综合权衡**重复复述白脸/黑脸观点**（用户实测报告 2026-08-02）：综合权衡出现完整"四、情景分析"段落，且上涨/下跌/震荡各段反复引用"黑方指出同质化风险""白方指出防守资产缓冲"。根因：`llm_debate_conditional`（条件推理）开启时，pro/con 因 `skip_scenarios=True` 不写情景分析（`generators.py` 辩论模式强制跳过），改由 synthesis 的 `_build_debate_synthesis_prompt` 注入"按涨/跌/震荡情景给出综合建议"指令；但 `_SYSTEM_DEBATE_SYNTHESIS` 仍残留 rf-93 时代"情景分析已在白脸/黑脸观点中给出，不要在综合权衡中再次插入情景分析段落"的**过时断言**——system prompt 与 user prompt 直接矛盾，LLM 为满足情景指令只能从白脸/黑脸正文抽取内容填充 → 复述双方观点。rf-93 当年仅改 prompt 文案（软约束），conditional 功能合入后未同步更新 system prompt 造成回归 | `_SYSTEM_DEBATE_SYNTHESIS` 保留为 conditional 关闭基线（维持"禁止插入情景分析"）；新增 `_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL` + `_build_system_debate_synthesis(enable_conditional)`，conditional 开启时改用强化版——明确允许按 user prompt 输出情景分析（消除指令冲突）+ 强化引用纪律（综合评估/行动建议/情景分析三部分均"引用一句话概括、不得展开复述"）+ 要求各情景差异化且不与正文机械重复；`generators.py` synthesis 阶段按 `_enable_conditional` 动态选择 system prompt。新增 4 个回归用例（conditional False=基线 / True=允许情景+不复述+无冲突断言 / 开关切换内容变化 / generators 层 conditional 开启时 system_prompt 切换为强化版） | `changelog.md` → Fix / Test |

> 0.9.0 ~ 0.9.5 已修复问题记录（rf-90 ~ rf-144）已迁移归档至 [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md)，本表仅跟踪当前迭代（0.9.6-dev）修复项。

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
