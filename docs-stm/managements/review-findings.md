# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.4-dev
> **编号源**：`rf-next = 431`（新增问题取此编号，完成后更新为 +1；已用最大 rf-430，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
| **rf-75** | `core/registry.py` | 666 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-09-10 实测 666，较登记值 665 增长 1） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 542 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 544 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-09-10 实测 544，较登记值 536 增长 8，数值归一防线纳入后仍处 500-800 区间） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限；2026-09-10 实测 521，较登记值 526 下降 5） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 405 | 未超限（<500，维持现状；2026-09-10 实测 405，较登记值 401 增长 4） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 633 | 500-800 可选优化区间（2026-08-05 实测 635，较登记值 472 增长 163，跨过 500 线；2026-09-10 实测 633，较上次下降 2，关注后续增长） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 427 | 未超限（<500，维持现状；2026-08-05 实测 423，较登记值 477 下降，重构后缩减；2026-09-10 实测 427，较上次增长 4，决策登记载体纳入后仍处 500 线以下） | Excel 编排器 |

#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

#### P2C — 文档与配置口径（2026-09-24）

> 无待处理项（`rf-420` 已修复，见「已解决问题」区）。

## 已解决问题

### 已解决待归档（v0.11.4-dev）

| # | 问题（违反的约束用语义描述） | 处置 |
|---|------|------|
| **rf-428** | **数据源健康检查探针误报「连接失败」**（用户报「`price_price_fund_otc` / `report_datasink` 高频连接失败」）：`core/check_sources.py` 的 9 个探针**全部用 `http://` 端点且不跟随重定向**，上游迁 https 后回 301/302 → 3xx 被计为告警（`ok=false`），健康历史里天天基金/腾讯K线/财联社长期 ok=0/fail=10；东方财富行业探针缺 headers 且指向本环境不可达的 push2 ——**4 个源被误报，而生产取数路径（https + `follow_redirects`）一直正常**（实测行业分类 3/3 命中、场外净值正常） | ① 9 个探针 URL 全部改 https；② `_check_http` 默认 `follow_redirects=True` 且 **3xx 计「可达（带备注）」**；③ 新增 `_check_any()` 多端点探针，行业分类改「push2 主源 → 行情页备源」，任一可达即判可用并标注「主源不可达，由备源接管」；④ 回归 +9 例（3xx 可达 / follow_redirects 透传 / 4xx-5xx 仍告警 / 备源接管与全失败标注 / 静态守卫「探针不得出现 `http://`」 / 行业探针双端点）。**实测健康检查 10/10 可用（此前 6/10）** |


| **rf-429** | **过去 24 小时改动的技术债 5 项**（用户要求「过去24小时的修改有技术债务么，有就修复它们」）：① `scripts/check-doc-drift.py` 因新增 3 项检查由 732 → **985 行**（越过 800 行上限，违反项由 rf-390/rf-399 先例确立）；② `analysis/prosperity_scoring.py` 731 → **813 行**同越限；③ **重复实现**：`_price_transform_sina_fund` 与 `_price_transform_eastmoney` 逐键相同、`SinaFundQuoteAdapter` 与 `EastMoneyQuoteAdapter` 映射与有效性判据全同（两处重复维护点）；④ **文档未同步**：`requirements.md` 数据源表与 `technical.md` 链路表仍写场外净值单源，`developer-guide.md` 的检查项清单滞后（写「十一项」而实为 14 项），入口 docstring 同样滞后；⑤ **冗余形参**：`_check_http(expect_status=...)` 无任何调用方传参（连同签名内二次分支） | ① `check-doc-drift.py` 拆为 `scripts/_doc_drift/` 包（`_shared` / `_format` / `_tree` / `_ledger`，入口 198 行仅留 CLI + 编排 + **原面 re-export**，镜像 `_test_runner/` 先例）；② 抽出 `analysis/prosperity_signals.py`（127 行，本地信号提取原语；评分内核 711 行），迁移名在 `prosperity_scoring` 原面 re-export；③ 收敛为 `_otc_nav_to_standard()` 单一转换实现 + `_OtcNavQuoteAdapter` 共用基类（两源仅余 `source_api`/`source_id` 差异）；④ 四处文档同步（含 `developer-guide` 补齐第 12~14 项 + 「十四项」计数）；⑤ 删除冗余形参，3xx 判定合并为单分支。**回归**：`test_check_doc_drift.py` 补丁目标改为指向持有子模块（`drift_parts` fixture）；新增 `test_sina_fund_*`/`_otc_nav` 等价与端到端断言；**全量 90 + 75 + 83 例通过**，folders.md 目录树与统计已补 |


| **rf-430** | **Provider Chain 降级路径表长期缺链**（48h 技术债审计发现）：`datasource-reliability.md` §4.2 表声称枚举全部链路，实际仅 5 行（13 条链缺 8 条）——其中 `financial_report` 是**本轮窗口内**（plan-50 接入巨潮备源）新增双源行为却未入表；`price`/`fund_rank`/`fund_hold`/`financial_indicator`/`history_fund_otc`/`history_index`/`bond_yield` 亦从未登记。表与代码无任何断言绑定 → 漂移无人发现 | ① 表补齐为 **13 条链**（主/备/回退条件，与 `_DEFAULT_CHAINS` 逐链对应）；② **新增第 15 项断言** `check_chain_table()`：解析该表链名并与 `_DEFAULT_CHAINS` **双向**比对（漏链 → 「缺少链路」；幽灵行 → 「无此链」），表缺失亦报错；③ 项数枚举同步「十四项 → 十五项」（入口 docstring + CLI 用法 + developer-guide 项单）；④ 回归 +4 例（真实仓库一致 / 漏链 / 幽灵行 / 表缺失）。**附**：核实 `cninfo` 端点 https 不可达（超时）而 http 可达 → 保留 http + `follow_redirects`，非债务 |

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)  — rf-380 ~ rf-427（v0.11.0 ~ v0.11.1 批次，2026-09-18 并入）；rf-379、rf-402 ~ rf-422（v0.11.2 批次，2026-09-24 并入）
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
