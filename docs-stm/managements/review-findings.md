# 个人投资分析报告生成小助手 - 自我审查问题记录
> 文档版本：0.10.10-dev
> **编号源**：`rf-next = 252`（新增问题取此编号，完成后更新为 +1；已用最大 rf-251，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：③ 的 3.2~3.4 已过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；③ 的 3.1（断网渲染）待补验 |
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

---

## 已修复（摘要）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-248 | test-chart.html 调试页动态注入 chart 脚本未设 `s.async=false`（注释「非 async 动态注入按序执行」实为错误认知），动态 script 默认 async=true 无序执行，chart-init.js 先于 chart.min.js/chart-common.js 执行触发守卫静默 return，全场景 0/6 图未初始化、无 tooltip（用户 2026-08-06 实测 ok/degraded/empty 三场景复现） | 注入循环补 `s.async=false` 对齐报告模板 defer 语义；生产模板（report_template/whatif_template）用静态 defer 不受影响 | `changelog.md` [0.10.10-dev] |
| rf-249 | 折线图（净值趋势/最大回撤/演进图 + whatif 回测线图）`pointRadius:0` 且默认 `interaction.intersect:true` → 数据点命中区域≈0，悬停无法触发 tooltip；雷达图 `pointRadius:3` 命中区域小同样难触发（用户 2026-08-06 ok 场景实测：环形图+两柱状图有 tooltip、折线+雷达无）。另：test-chart.html 自检 800ms 早于脚本加载完成误报 0/6；offline 文案「canvas 保留 fallback 文本」为误解（现代浏览器不渲染 `<canvas>` fallback 文本，引擎缺失时图表区域空白，真实报告回退明细表格） | ① chart-common.js `lineOptions` 补 `interaction:{mode:'index',intersect:false}`（悬停任意处显示最近 x 点全数据集值）；② chart-init.js radar 补 `interaction:{mode:'nearest',intersect:false}`；③ test-chart.html 自检改 chart-init.js onload 触发 + 3s 兜底；④ offline 文案与 iter7 清单/review-findings 断言修正为实测行为 | `changelog.md` [0.10.10-dev] |
| rf-250 | test-chart.html 自检用 `canvas._chart` 判定图是否被 Chart.js 接管——v4 该内部句柄不存在（canvas 上挂 `_chartjs` 管理事件监听，`_chart` 是数据集/元素内部引用），判定恒为假；rf-249 修复后图真实渲染、tooltip 可用，但自检仍误报「0/6 图已初始化」（用户 2026-08-06 ok/degraded 场景实测） | 自检判定改官方 API `Chart.getChart(canvas)`（v4 构造内部亦用 `Chart.getChart(canvas)` 查已有图表，与 chart-print/chart-export 用同一 API） | `changelog.md` [0.10.10-dev] |
| rf-251 | chart-init.js 6 个核心图 init 守卫 `!ds.labels`/`!ds.datasets` 不拦截空数组（空数组 truthy），empty 场景（`labels:[]`+`datasets:[]`）下 `ds.datasets[0]` 为 undefined、抛 TypeError，依赖外层 try/catch 降级（图不渲染、console warn 噪声），而非显式空数据跳过 | 6 处守卫统一补 `!ds.labels.length` + `!ds.datasets.length`，空数据优雅 return（对齐生产模板 `{% if labels %}` 空值语义 §4.12，不再依赖异常降级） | `changelog.md` [0.10.10-dev] |

> v0.10.8/v0.10.9 发布时已修复项（rf-234~rf-247）已整体迁入 [归档档案](#归档档案) 的 `archived_review-findings.0.10.x.md`。

## 归档

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.8（2026-08-04 ~ 2026-08-06，rf-204~rf-247）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
