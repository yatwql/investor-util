# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.16
> **编号源**：`rf-next = 305`（新增问题取此编号，完成后更新为 +1；已用最大 rf-304，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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

#### P2D — LLM 缓存指纹同源偏差（2026-09-10 plan-31 实现期自审发现）

| # | 问题 | 修复方向 |
|---|------|----------|
#### P2E — DeepSeek 旧模型名定价口径待确认（2026-09-10 接入 `deepseek-flash` 时自审发现）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-303** | 接入 V4.1-Flash 正式名时核对 `MODEL_PRICING` 的 DeepSeek 条目，发现两处既有口径未经官方确认：① **`deepseek-reasoner` 无定价条目**——该模型名目前仍被 DeepSeek 端点接受，但 `estimate_cost()` 对其返回 `"-"`，费用页签显示为空；② **`deepseek-chat` 单价来源存疑**——本表按 V3（1.50/4.50/0.05）单独定价，而 DeepSeek 文档称 `deepseek-chat` 与 `deepseek-reasoner` 分别是 V4-Flash 的「非思考 / 思考模式」别名（若属实，二者应随 flash 系列走 09-10 降价后的 1.00/4.00/0.02，且 `deepseek-reasoner` 应有条目） | 以 DeepSeek 官方文档确认两个模型名的**当前语义与单价归属**后再定：若确为 v4-flash 别名，则为 `deepseek-reasoner` 增加条目并核对 `deepseek-chat` 单价（须同步 `[0.10.16]` 起 flash 系列降价口径）；若 `deepseek-chat` 已固化为独立 V3 端点则维持现值并补注释说明。**改动前须先补「模型名 → 单价」断言测试**，避免误改导致费用估算偏移。低优先级：项目配置、文档示例与测试均未使用这两个模型名 |

| **rf-297** | `generators_orchestrator._compute_module_cache_info` 对 expert_review / health_check / penetration_deep 三个模块构建指纹时传 `history_data=history_data`（`build_llm_fingerprint` 会把它抽取成 `_risk_signals` 并入哈希），而 `generators.py` 三个写侧 `_fingerprint()` 闭包**完全不传** `history_data`（`_risk_signals` 恒为 `{}`）→ 两侧哈希必然不同（实测 `41e560ba67fe` ≠ `259afccbd62e`）→ 预检 `cache_get(cache_info["key"])` 对这三个模块**永不命中**，每次报告都全量派发。**非正确性缺陷**（内层 `generate_llm_module` 用写侧键读写缓存，内容仍正确复用），属性能与日志噪声；但预检形同虚设，易误判为"缓存未命中率高" | 二选一对齐：① 预检侧不传 `history_data`；② 写侧闭包补传并核对 `history_data` 在两侧可取到同一对象（须确认 `build_llm_fingerprint` 的 `history_data` 语义对三个模块等价）。**必须先补两侧指纹一致的回归测试**（断言 `_compute_module_cache_info` 的 key 与写侧 `fingerprint_fn()` 拼接结果相等）再改，避免修复引入缓存永久 miss；另需评估 `_module_labels` 事实校验按 `cached` 跳过的分支不受影响。关联 plan-31（其信号后缀已按同源纪律两侧同调，未触碰本偏差） |
## 已解决问题

### 已解决待归档（v0.10.16-dev）

v0.10.16 已解决记录（rf-295 ~ rf-304）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.16 章节（变更详情见 changelog.md [0.10.16] 对应条目）。

### 已解决待归档（v0.10.15-dev）

v0.10.15 已解决记录（rf-288 ~ rf-294）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.15 章节（变更详情见 changelog.md [0.10.15] 对应条目）。

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.16（2026-08-04 ~ 2026-09-10，rf-204 ~ rf-304）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
