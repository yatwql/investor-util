# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.5
> **编号源**：`rf-next = 622`（新增问题取此编号，完成后更新为 +1；已用最大 rf-621，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> **派生源（2026-10-05 起，人肉快照退役）**：行数与全集以 `scripts/check-file-length.py -v` 输出为真值（该输出列出全部 >500 行主程序文件）；红线（>800 行）由 `check-file-length.py --ci` 自动拦截（豁免路径与本表挂账同步），不再依赖本表人工发现新破线者。本表仅登记需跟踪/决策的文件。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 780 | 维持现状但**临界**（中央注册表被 56 文件引用，数据表内聚；2026-10-07 实测 780，较登记 743 增 37——报告导航分组 `nav_group`/`llm_supported` 字段增补；同批已把计算注册表拆出 `core/computation_registry.py` 控住 800 红线，余量 20 行，后续注册项增补须优先下沉子模块） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 520 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-10-02 实测 520，回落至登记值附近（rf-522 重试退避原语收编后下降）） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 671 | 维持现状（仍在 500-800 区间内聚；2026-10-02 实测 671，较登记值 542 增长 129，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 621 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-10-02 实测 621，较 2026-09-10 的 544 增长 77——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 556 | 维持现状（render 函数属同一渲染域；2026-10-02 实测 556，较 2026-09-10 的 521 增长 35） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 555 | **已跨入 500-800 可选优化区间**（2026-10-02 实测 555，较 2026-09-10 的 405 增长 150——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-86** | `cache/operations.py` | 740 | 500-800 可选优化区间（2026-10-05 脚本实测 740，较 2026-10-02 的 637 增长 103，临近 800 须关注） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 585 | **已跨入 500-800 可选优化区间**（2026-10-05 脚本实测 585，较 2026-10-02 的 574 增长 11——持仓基本面合并页签等增补）；暂维持现状 | 页签编排可进一步下沉到独立 writer（后续择机） |


### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

### P2C — 测试文件膨胀（阈值：行数 >800 警告 / >1200 红线；测试项 >80 警告 / >120 红线）

> 阈值见 `developer-guide.md`「文件膨胀阈值」表；本表登记已越线或临近越线的测试文件（2026-10-05 实测；全集清单以 `scripts/check-file-length.py -v` 为准，>1200 行红线由 `--ci` 拦截）。

> **当前无挂账项**（贴线跟踪 rf-586 的拆分已完成并转入下方已解决区）。警告级全集（测试 >800 行 / >80 项）以 `scripts/check-file-length.py -v` 为派生源，不做人肉快照；逼近红线（1200 行 / 120 项）时按「被测函数 / 场景类型」拆分为同目录兄弟分片，并同步刷新 `test-coverage.md` / `folders.md` 用例计数。

### P2F — 执行流程耗时优化残留（影子双算毕业）（2026-10-07）

> 触发：2026-10-07 流程优化批（rf-606 ~ rf-615）交付后复测——结论缓存/事实缓存/快照热路径/预检均实测达宣称值，唯影子毕业路径在混合提交节奏下不可达。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-621** | 测试收集快照**影子双算无法毕业**：`shadow_ok` 仅在「共享语境未变 + 仅测试文件变更」的运行 +1，而共享语境 = `src/` 全部非测试文件 + `pyproject.toml`（业务代码同批变更即走 `inc=None` 分支，只回写 `prev_ok` 不推进计数）；2026-10-07 全天 5 次代码+测试混合提交后计数实测仍为 0，测试变更提交每次都付全量双算 ~4.1s，宣称「变更文件纯增量 ~0.87s」结构性不可达 | 共享语境变化的运行保留**旧文件计数仅作比对用途**（权威仍以全量为准、指纹范围不缩、失效方向仍偏向真收集），使混合提交也能推进毕业计数；配回归：混合提交推进计数 / 比对不一致归零且告警 / 全量权威与失败不回写语义不变 |

## 已解决问题


> **本迭代已修复记录（rf-600 ~ rf-620 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>

> **本迭代已修复记录（rf-579 ~ rf-599 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>


> **本迭代已修复记录（rf-568、rf-571 ~ rf-578 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>

> **本迭代已修复记录（rf-563 ~ rf-570 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>
> **迁移说明**：已完成批次摘要（rf-557 ~ rf-562）已于 v0.12.1 发布（2026-10-03）随档迁入 [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)，本文件只保留未完成项与归档索引；更早批次（rf-541、rf-542 ~ rf-556）见 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)。

### 归档档案

- [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md) — v0.12.1 ~ v0.12.5 批次（2026-10-03 ~ 2026-10-07）
- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — v0.11.0 ~ v0.11.11  （2026-09-18 ~ 2026-10-02）
- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.20（2026-08-04 ~ 2026-09-15）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
