# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.14-dev
> **编号源**：`rf-next = 281`（新增问题取此编号，完成后更新为 +1；已用最大 rf-280，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）



| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 665 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 542 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 536 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 526 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 635 | 500-800 可选优化区间（2026-08-05 实测 635，较登记值 472 增长 163，跨过 500 线，关注后续增长） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 423 | 未超限（<500，维持现状；2026-08-05 实测 423，较登记值 477 下降，重构后缩减） | Excel 编排器 |

#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui.md` 验收标准），完成后回填 changelog、本表移至已修复。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

## 已解决问题（变更详情见 changelog.md 对应条目）

> 2026-08-07 全面核对：以下各项均已修复并在 changelog.md 相应版本段登记（rf-261 为 plan-25 实现、rf-272 为 ARG001 死参数全数处置，完成时均处于待处理段，本次核对后移入本区）。
> **2026-08-16 归档**：v0.10.10 ~ v0.10.13 已发布版本修复项（rf-248 ~ rf-275）已整体迁入 [归档档案](#归档档案) 的 `archived_review-findings.0.10.x.md` 对应版本章节。本区仅保留仍处 dev 版本（v0.10.14-dev）的已解决项。

| # | 摘要 | 变更记录 |
|---|------|----------|
| rf-276 | v0.10.1+ 改动文档一致性全量审计（203 提交）→ A 类事实错误 / B 类用户文档缺口 / C 类管理文档三档修复 | `changelog.md` [0.10.14-dev] |
| rf-277 | fact_checker 条件阈值误修正：穿透深度分析「收益率超过 200% 后可考虑部分止盈」的 200% 是止盈目标阈值，被误判为 600900 实际收益率修正为 59.2%（把正确文本改错）。修复：新增 `_CONDITION_TRIGGER_KEYWORDS` 触发词 + 后置调仓动作词双条件联合判定 | `changelog.md` [0.10.14-dev] |
| rf-278 | fact_checker 简称匹配漏检：「华安纳指+180.5%」（040046 实际 130.61%）因简称无法匹配全名、回退最近邻 180.5 恰命中 601939 真实值而漏检。修复：`_NAME_ALIAS_MAP` 简称归一化 + `_extract_core_name` 核心名前缀匹配 | `changelog.md` [0.10.14-dev] |
| rf-279 | dedup 校准脚本读取路径与写入路径不一致：`calibrate-dedup-threshold.py` 默认读 `data/cache/dedup_anchors.jsonl`（7-29 旧文件），而 `news_dedup.py` 自 commit `4e95d595`（2026-07-30）起写入 `data/calibration/dedup_anchors.jsonl`，脚本从未同步 → 校准建议基于过时快照。修复：脚本默认路径改为 `data/calibration/`；基于最新 109018 条数据重校准结论——bg=2 ratio≥0.35 候选 523 条真实重复率仅约 25%，维持现阈值 | `changelog.md` [0.10.14-dev] |
| rf-280 | dedup 锚点文件重复计数：`dedup_anchors.jsonl` append-only，同一对 (source,title) 多轮运行重复追加（实测 61.6% 为重复），使校准数字失真（cross_skip bg=0 279→13800 虚增）。修复：① `_flush_anchors` 写入层去重——新增 `_WRITTEN_ANCHOR_KEYS` 进程级集合 + `_load_written_keys` 惰性加载，跨轮只写新 key；② 校准脚本 `load_anchors` 统计层按 (source,title) 对去重，处理存量污染；③ conftest 隔离锚点路径 + 重置锚点单例。去重后校准锚点 109018→41761 | `changelog.md` [0.10.14-dev] |

> **独立项（rf-272 处置衍生，单列跟踪）**：`html_renderers._render_llm_content_section` 13 参渲染器上下文（删除需重构 html_writer.py 调用点，单列「签名瘦身」）；`report/_pipeline.py` 遗留重复文件（已标注不承载活代码，单列清理项）；`orchestrator.generate_report.warm_cache`（CLI `--warm` 标志去留待决策，已无实际消费路径）。

> v0.10.8 ~ v0.10.13 发布时已修复项（rf-234 ~ rf-275）已整体迁入 [归档档案](#归档档案) 的 `archived_review-findings.0.10.x.md`。

## 归档

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.13（2026-08-04 ~ 2026-08-14，rf-204 ~ rf-275）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
