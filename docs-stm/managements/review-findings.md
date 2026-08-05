# 个人投资分析报告生成小助手 - 自我审查问题记录
> 文档版本：0.10.6-dev
> **编号源**：`rf-next = 230`（新增问题取此编号，完成后更新为 +1；已用最大 rf-229，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复 |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

> 已关闭项（决策已定，archive 可查）：rf-117 A6 键盘可达性（不做 MVP）、rf-118 相关性矩阵 Heatmap（已用 HTML 表格渲染）、rf-120 S5 CSP（不做）、rf-121 报告体积（R21 接受自包含代价）

#### P2D — 调仓建议可行化层数据模型限制（待后续增强接入）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-217** | 调仓建议可行化层（审查发现）：1 前缀场外持有基金（LOF/开放式指数基金，如 `161725 招商中证白酒指数A`、`110022 易方达消费行业`）无法区分场内/场外持仓渠道，当前默认按场内基金处理（100 份取整 + 仅计佣金）；场外持有会漏计赎回费且份额取整过粗 | 需持仓明细携带场内/场外渠道上下文（属后续增强，不在当前契约内）；当前默认场内口径已在模块 docstring 与 changelog 文档化，费用为估算性质 |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）



| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 653 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 537 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 534 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 未超限（<500，维持现状） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 477 | 未超限（<500，维持现状） | Excel 编排器 |

#### P2B — 文档与实现不符（低优先级，增量改进）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-229** | §6.7 功能语义命名表目前是「记录性活索引」而非自动约束——`check-code-traces.py` 只做负面禁止（禁任务代号/魔法编号，`IDENTIFIER_PATTERNS` + CODE），**不校验正面一致性**：① 新增 `report_submodules.*` 开关键可绕过表不登记（预演审计实证：代码现有 6 键 `candidate_compare/cost_lots/data_quality/industry_beta/market_temperature/valuation_percentile`，其中 **`cost_lots` 不在表中**，表内成本流水由 `fund_flow`/`dividend_flow` 覆盖——键与表已存在漂移）；② 表中 slug 若功能已删除可残留僵尸条目；③ 合并章 sheet key（`position_relationship`/`portfolio_history_drawdown`/`style_factor`）是否真实存在于 `registry._REPORT_SECTION_DEFAULT` 无人校验 | **增强方向（待讨论定稿）**：新增 `scripts/check-semantic-index.py` 做双向校验并入门禁——正向：代码中 `report_submodules.<key>` 均须在 §6.7 表中登记（表外键报错，或先补表/列豁免）；反向：表中每个 slug 在 `src/python` 中确实存在（防僵尸条目）；合并章 key 校验须在 registry 中存在。**实施前先跑「键覆盖审计」**确定表外键清单与豁免策略（`cost_lots` 需决定补表或豁免）。待讨论：校验脚本独立 or 并入 check-code-traces.py；门禁级别（P0/P2）；表解析的稳定性 |

---

## 已修复（摘要）

> 已归档历史修复记录见 [归档档案](#归档档案)。以下仅保留近期未归档条目。

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| **rf-228** | TUI 菜单「2」更新行情缓存时进程崩溃 `[FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized()`。根因：菜单 2 的并行价格抓取（ThreadPoolExecutor 4 workers）中，每个价格的新鲜度校验 `_price_cache_fresh` → `get_last_trading_day()` → `_get_trading_calendar()` → `akshare.tool_trade_date_hist_sina()`，akshare 内部用 `py_mini_racer`(V8) 解密新浪接口且每次调用都重新初始化 V8；多线程并发首次初始化 V8 触发 partition_address_space FATAL，**直接 abort 整个进程**（try/except 无法捕获）。已在 tmp 探针脚本复现（4 线程并发 → EXIT 3 崩溃；加锁串行化 → 全成功） | `_get_trading_calendar()` 缓存未命中分支用模块级锁 `_TRADING_CALENDAR_AKSHARE_LOCK` 串行化 + 双重检查（避免锁等待后重复拉取）。V8 顺序初始化安全。新增回归测试 `TestTradingCalendarConcurrency`：4 线程并发调用 `_get_trading_calendar()` 注入 fake akshare，断言回调最大并发深度 = 1。**连带优化**：测试文件 `test_market_value.py` 多个测试类裸调用 `is_market_open`（东方财富 push2 API 真实 HTTP）与 `_is_trading_day`（akshare 交易日历）致单用例 2~6s，统一补 setUp mock 隔离网络 | changelog v0.10.5 |
| **rf-227** | `test_cli_integration.py` 三处 CLI 测试 patch 目标陈旧（41df26a 根文件归子包重构后残留包级 re-export 路径 `src.python.cli._cli_read_holdings`，拦截不到 `cli.py` 内部调用）：`test_cli_cache_config_respected` 直接读取真实持仓文件失败（`/test/holdings/test.xlsx` 不存在 → mock 被调用 0 次断言失败），另两例靠默认持仓文件恰好存在而侥幸通过 | 三处 patch 目标统一修正到 `src.python.cli.cli._cli_read_holdings(_with_flows)`；report 路径两例改用 `_cli_read_holdings_with_flows` 返回 `(mock_holdings, [], [])`（与 `_handle_report` 实际调用一致），彻底脱离真实持仓文件依赖。全量 all 5026 passed、CLI 单测 56 passed | changelog v0.10.5 |


---

## 归档

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.4（2026-08-04 ~ 2026-08-05，rf-204~rf-226）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
