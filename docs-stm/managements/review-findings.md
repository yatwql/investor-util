# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.11-dev
> **编号源**：`rf-next = 533`（新增问题取此编号，完成后更新为 +1；已用最大 rf-532，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

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

### P2C — 文档与实现口径（2026-10-02）

> **rf-520（已解决，2026-10-02）**：48h 自查发现的三处文档性劣化随本轮修复——实验功能治理后 `depth_profile.py`/`excel_generator.py`/`experimental_seams.py` 注释仍按旧语境引用。**同日延伸核实**：全仓 410 个测试文件按八项纪律复核，唯一实质违规为约束代号类用例名 5 处（已语义化改名；其余为业务阈值数字与启发式误报，不构成违规）。

> 无待处理项（`rf-420` 已修复，见「已解决问题」区）。

### P2D — 工程卫生（2026-09-29）

> 无待处理项（`rf-474` 已修复，见「已解决问题」区）。

### P2E — 全仓技术债务审查（2026-10-02，对照「架构设计约束」27 条与核心架构决策五项）

> 本轮全仓源码审查（src/python ~7.8 万行），逐条对照 `technical.md`「## 架构设计约束」全部编号约束与「## 概要设计—核心架构决策」§1.4.1~1.4.5 排查历史技术债务。多数关键基线已达标（HTTP 客户端工厂零绕过、控制台着色与路径绝对化合规、凭据分离合规、LLM 模块缓存指纹单一事实来源无违例、时间距离交易日口径已收敛、语义命名守卫全过、原子写主路径已统一）；以下为发现项，按优先级排列。

| # | 优先级 | 问题 | 风险点 | 修改后收益 |
|---|--------|------|--------|------------|
| **rf-521** | **高** | **报告层直连 providers（Provider Chain 必经约束）**。`report/financial_report_digest.py:25`（datasink）、`report/market_sentiment.py:21`（hithink）、`report/data_source_matrix.py:420`（datasink）、`report/news_correlation.py:492`（news_aggregator 状态查询）、`report/category.py:147`（akshare_extras 私有常量 `_DIVIDEND_FAILURE`）绕过 fetcher 网关直接 import `providers` 模块；`core/check_sources.py`（datasink/cninfo 探针）与 `core/trading_calendar.py:85`（hithink）亦直连 | 这些调用不激活熔断器、不产生 fallback 递补、不进链路审计日志——正是「Provider Chain 必经」约束列举的三重失效。其中 `financial_report_digest`/`market_sentiment` 是真实取数路径（非只读查询），在源抖动时会拖垮报告生成且熔断器无感知，用户看到的可用性矩阵与实际失败原因脱节；同源双路径（report 直连 + fetcher 走链路）还会让 cassette 回放覆盖出现缺口 | 报告层取数与探针全部收敛到 fetcher 网关函数（真实取数走 `fetch_with_fallback`，只读状态查询在 fetcher 内提供薄透传函数），熔断/fallback/审计/回放四套机制对全部路径一致生效；后续新增数据源只需改网关，不再出现报告层直连第二套口径 |
| **rf-522** | 已修复（2026-10-02） | **两处手写「重试 + 退避」残留（重试退避唯一原语约束）**：`batch.py::retry_failed` 与 `index.py::fetch_us_indices` 迁移到 `retry_transient` + `RetryPolicy`，内联退避算式删除；详见 changelog 0.11.11-dev 条目。 |
| **rf-523** | 已修复（2026-10-02） | **手写间隔节流散落（间隔节流唯一原语约束）**：eastmoney 分页 sleep 与 cninfo/datasink 429 退避等待分别收敛到 RateLimiter 与 interval_delay 唯一算式；详见 changelog 0.11.11-dev 条目。 |
| **rf-524** | 已修复（2026-10-02） | **剩余自持原子写拷贝（缓存原子写唯一原语约束）**：`write_text_atomic/write_bytes_atomic` 补 `mode` 参数，新增 `write_bytes_atomic`/`copy_file_atomic` 原语，cassette/upload/holdings_update/config_edit 四处旁路全部委托；详见 changelog 0.11.11-dev 条目。 |
| **rf-525** | 已修复（2026-10-02） | **场内前缀判定漏中心化（代码类型判定中心化约束）**：`code_utils` 补 `to_exchange_symbol`/`get_exchange_category`，hithink 两处与 cninfo 栏目映射改薄委托；详见 changelog 0.11.11-dev 条目。 |
| **rf-526** | 已修复（2026-10-02） | **core 层反向依赖（分层纪律缺口）**：circuit_breaker/provider_registry/doctor/trading_calendar 四处改注册钩子（上游模块导入时自注册），core 删除对 llm/analysis/fetcher/providers 的延迟 import；并新增 check-code-traces 分层守卫（core→上层 import 即 HIGH，豁免白名单现空）；详见 changelog 0.11.11-dev 条目。 |
| **rf-527** | **中** | **自然日差离散判定残留（时间距离按交易日计约束；收益类/历史事件场景）**。`analysis/drawdown_events.py:116/121`（回撤持续/恢复天数）、`analysis/crisis_annotation.py:250`（恢复耗时）、`analysis/cost_flow.py:154`（XIRR 年化 `t=days/365`，设计上即自然日口径，合规）与 `fetcher/fund_manager.py:121/303`、`report/fund_manager_analysis.py:129/148`（基金经理任职/变更距今天数）均直接自然日差 `days` | 与「时间距离按交易日计」一致的判定需求（距今多久）在「报告新鲜度/停更/观察期」主链路上已收敛到交易日历，但回撤事件与基金经理任职时长仍用自然日——长假期段回撤事件 duration/recovery_days 被充分拉长、跨年对比口径与交易日维度指标（年化波动等）不可同屏比较。cost_flow XIRR 属「本身以自然日定义的量」豁免，合规 | 回撤事件/危机标注/基金经理任职的时长改用 `trading_calendar.count_trading_days_elapsed`（UI 标注「按交易日计」），历史对比与风险指标口径统一；保留 XIRR 自然日年化（设计如旧） |
| **rf-528** | 低 | **渲染期模块级可变状态边界复查**。`web/handlers.py` 的 `_history_cache`/`_health_cache` 模块级 dict（进程内 5s/60s 性能缓存）静态单线程 Flask worker 语义下安全，但属「模块级可变状态」，与「渲染期数据不写入模块级全局变量」约束精神存在张力；`report/html_jinja_env.py:128` 已合规（fail-closed + context 覆盖） | Flask 单 worker（RunManager 串行队列）前提下当前无并发污染，但将来 worker 多开/线程化时静默串数据；健康检查/历史缓存与业务缓存双体系并行，清理心智开销 | 收敛到统一进程内缓存助手（带线程锁 + TTL 注释标注线程模型前提），或注释锁死「仅限单 worker」约束测试钉桩 |
| **rf-529** | 低 | **双治理并行体系内的重复工具**。`analysis/whatif.py::_compute_hhi`（L88，成本口径）与 `analysis/portfolio_evolution.py::_compute_hhi`（L60，市值/成本兜底口径）各算 Σ权重²，`analysis/_silence.py`、`core/perf.py`、`core/decision_ledger.py` 对同一 `jsonl_store` 抽取逻辑保持 3 份薄包装（后两者为转发 OK，但静默其仍保留对`mkstemp` 语义的独立文档化） | 同一逻辑两张表达（whatif 与 portfolio_evolution 权重基数口径略有差异：成本合一 vs 市值优先），未来若加入 HHI 权重口径（如启用市值优先）两处需同步改，易漏 | whatif 复用 portfolio_evolution 的口径函数（或共享纯计算 `analysis/_hhi.py` 按口径参数化），差异仅体现在调用参数 |
| **rf-530** | 低 | **print 输出规范边界确认（日志统一约束）**。`report/progress.py::TuiProgressReporter`（交互式进度，属合法「交互式 print」豁免）与 `core/check_sources.py::run_check_sources`（CLI 报告打印，属交互输出）合规；但 `core/doctor.py:16` 的 print 走的是自检 CLI 快路径，与同文件 `print(item["group"]...)` 复合、违背「若 doctor 需要嵌入 Web 报告」（`web/handlers.py` 已走结构化数据路径），该 print 仅命令行入口——它没走 `[..]`/`[OK]`/`[ERR]` 样式前缀规范，有各別字符流风险 | 无功能风险，仅一致性观察（`check-code-traces.py` 不阻止交互式 print） | 体检 CLI 输出亦可走统一带前缀/着色的 console helper（复用 `core/ansi_colors.py`），或显式标注「CLI-only，不进产物」注释声明豁免依据 |
| **rf-531** | 低 | **过期缓存降级处置无统一入口（§1.4.5 尾部难覆盖区）**。`fetcher/index.py::fetch_us_indices` 手写「可正常缓存 → 主链路 → 备用腾讯 → 过期缓存 + `cache_set` 回写 + `_source=stale_cache`」四段流程，与 §1.4.5 的统一链路状态在语义上等价，但独立实现且 `cache_set` 回写过期数据时未盖语义版本，与「缓存载荷语义版本」词条的判据接入无关 | 该函数是「Provider Chain 必经」约束的唯一声明例外（技术原因），但例外声明只覆盖「不走 Chain」，未覆盖「手写降级回写」这一段；语义版本机制上线后此处（自动类别 restart）易成为版本缺失的缓存回写点 | 将「过期缓存回写」收敛为 `fetcher/chain.py` 提供的通用降级助手（常见语义版本盖戳），index.py 调用之；例外注释同步声明为「仅本次手写降级路径」 |

**rf-532** | 已修复（2026-10-02） | **CI 统计快照漂移高频红源（流程性）**：日常提交高频改变 managements/ 文档行数与测试用例数，`folders.md` 统计表静态数字必漂移，人工同步被连续推送踩踏（当日 6 次红全同源）。已按 A 方案落地：`check-doc-drift.py --sync` 自动回写实测数字（幂等，保留格式），`git pre-commit` 钩子在提交涉及 managements/ 或 src/test/ 时自动同步；详见 changelog 0.11.11-dev 条目。

## 已解决问题

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — v0.11.0 ~ v0.11.10  （2026-09-18 ~ 2026-10-01）
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
