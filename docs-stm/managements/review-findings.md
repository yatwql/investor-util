# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.10-dev
> **编号源**：`rf-next = 520`（新增问题取此编号，完成后更新为 +1；已用最大 rf-519，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> `src/test/conftest.py` 曾达 872 行（超硬上限），已于 2026-09-26 拆分至 672 行 + 新模块 225 行（详见「已解决问题」rf-448）。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 704 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-09-26 实测 704，较 2026-09-10 的 666 增长 38——plan-50 财报域槽位/plan-57 等注册项增补） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 578 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-09-26 实测 578，较登记值 564 增长 14） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 605 | 维持现状（仍在 500-800 区间内聚；2026-09-26 实测 605，较登记值 542 增长 63，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 621 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-09-26 实测 621，较 2026-09-10 的 544 增长 77——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 556 | 维持现状（render 函数属同一渲染域；2026-09-26 实测 556，较 2026-09-10 的 521 增长 35） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 551 | **已跨入 500-800 可选优化区间**（2026-09-26 实测 551，较 2026-09-10 的 405 增长 146——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-86** | `cache/operations.py` | 633 | 500-800 可选优化区间（2026-09-26 实测 633，与 2026-09-10 持平） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 574 | **已跨入 500-800 可选优化区间**（2026-09-26 实测 574，较 2026-09-10 的 427 增长 147——持仓基本面合并页签等增补）；暂维持现状 | 页签编排可进一步下沉到独立 writer（后续择机） |


### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

### P2C — 文档与配置口径（2026-09-24）

> 无待处理项（`rf-420` 已修复，见「已解决问题」区）。

### P2D — 工程卫生（2026-09-29）

> 无待处理项（`rf-474` 已修复，见「已解决问题」区）。

## 已解决问题

### 已解决待归档（v0.11.10-dev）

> **rf-512**（2026-10-01，既有缺陷）：`test_cassette_replay.py` 的季报回放用例受**日期时移**影响而变红（窗口按当前日期回溯、录制内容固定在录制当日，跨季度即先请求未录制季度报 miss），阻断 P0 门禁。已修复：`quarter_walk_anchor` 时间锚点把窗口固定到 cassette 的 `recorded_at`（pytest fixture 与 CLI 校验两条路径均施加），并补日期时移回归用例（去掉锚定即变红）；请求形状漂移信号未弱化。
>
> **rf-519**（2026-10-01，`folders.md`「版本演进对照」两处数据与自述口径不符）：按该节自述的复现方法重跑，发现①最初版本「仓库总行数」记 15,357，而同口径复算为 **15,600**（同口径下最新发布列的 280,397 完全吻合，说明该格为历史上用另一工具写入的错值）；②最新发布列「测试用例数」记 7,682，按该节步骤③（`git grep -c "def test_"`）复算为 **7,678**。已修正，并新增「当前开发版」滚动列 + 口径说明（grep 行数口径 7,757 / 严格行首定义 7,730 / pytest 收集 8,119）。
>
> **rf-518**（2026-10-01，bench 文档回填把「未测到」写成 0）：`test-runner --mode bench --update-docs` 的计数表写入器把「0 项执行」也当实测值回填——分阶段模式（`dev-verify`）预检未通过时会跳过测试阶段并返回 0，该 0 被写进 `test-coverage.md`（实测把 `dev-verify` 的 3392 覆盖成 0）。已修：写入器对「0 项执行」保留原值（与「未实测/超时保留原值」同口径）并补回归用例；文档已按修复后实测回填。
>
> **rf-515 ~ rf-517**（2026-10-01，本批实现的自查债务）：① 生成后自检的成本明细行缺失（用量总计含它而明细不含 → 行合计与总计对不上），已改为条件追加行；② 自检端到端用例 mock 打在 `skeleton.call_llm`，绕过了 `api.call_llm` 的合规注入点导致断言失真，已下移到 provider 层；③ 私有跨模块导入（`_strip_html`）与 akshare 降级日志措辞不准，已分别改为公开别名与中性 debug 描述。详见 changelog「修复（实现自查发现的债务）」条。
>
> **rf-513**（2026-10-01，TUI 菜单测试写死逐条模块清单）：`test_filter_hides_legacy_debate_modules` 以字面量集合断言菜单模块清单，注册表新增一个 LLM 模块（生成后自检）即变红——属「测试真值不是单一来源」的同类问题。已改为结构导出断言（注册表全集 ⊖ 菜单隐藏集）并补结构约束，新增模块不再触发该用例。
>
> **rf-514**（2026-10-01，模板结构用例的既有写法）：`test_section_count` 把模板 `.section` 容器数写死为常量。本次为生成后自检加区块时触发；处置上**刻意不改该常量**——自检区块改为「附录区块」形态（不占 `section-title` 编号、不参与目录导航），既符合「自检是附录而非独立分析章」的语义，也避免把可增长的模板结构计数固化进断言。
>
> **rf-510**（2026-10-01，TradingAgents-CN 借鉴项落地）：外部仓库借鉴项立项时**未先核对本仓库现状**，导致 `plan-59`/`plan-60`/`plan-62` 声称的能力（LLM token/成本记账、缓存命中率统计、跨源与源内接口降级链）在本仓库已有成熟实现——已按「先做缺口分析、再补真实缺口 + 测试锁定」修正实施路径，三项均补齐各自剩余缺口并新增回归用例（详细变更见 [`changelog.md`](changelog.md)「新增」段）。教训：借鉴类计划项在立项前先做本仓库现状比对，避免重复造轮子。
>
> **rf-511**（2026-10-01）：CLI 收尾摘要初版实现为模块级函数并访问 `reporter._verbose`（外部访问私有属性；被测报告器为 `MagicMock` 时该属性为真值 → 测试中误触发 stderr 输出）——已改为 `CliProgressReporter` 公开方法 + `verbose` 只读属性（与 `print_timing_summary` 同形）。
>
> **rf-479 ~ rf-509**（2026-09-30，31 项）管理/用户文档一致性核对批次：章节序号与层级、交叉引用指错、内容数字口径、目录树/格式卫生——均已修复，详细变更见 [`changelog.md`](changelog.md)「文档一致性核对」条目。
>
> v0.11.9 批次 rf-471 ~ rf-478 已随发布归档至 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)）

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — rf-380 ~ rf-478（v0.11.0 ~ v0.11.9 批次：v0.11.1~v0.11.3 于 2026-09-18 / 2026-09-24 并入，v0.11.4~v0.11.6 批次（rf-428 ~ rf-456）于 2026-09-26 并入，v0.11.7 批次（rf-457 ~ rf-460）于 2026-09-27 并入，v0.11.8 批次（rf-461 ~ rf-470）于 2026-09-29 并入，v0.11.9 批次（rf-471 ~ rf-478）于 2026-09-30 并入）
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
