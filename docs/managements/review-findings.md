# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.4-dev
> **编号源**：`rf-next = 588`（新增问题取此编号，完成后更新为 +1；已用最大 rf-587，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
| **rf-75** | `core/registry.py` | 743 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-10-05 脚本实测 743，较 2026-10-02 的 716 增长 27——plan-50 财报域槽位/plan-57 等注册项增补） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
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

| # | 文件 | 现状 | 状态 / 修复方向 |
|---|------|------|----------|
| **rf-587** | `docs/plan/` 八份文档（除 jev 两份）十轮复盘新增内容曾同时违两道机检：① 架构约束对照等新增节使用约束代号（CIPHER 规则：代号仅技术设计约束定义处可用，须语义描述替代）共 321 处；② 4 份文件「外部数据/风险」两节误插文档中段致序号跳变 | 已修复 2026-10-06（C 代号全量语义化为约束语义描述、4 份节序调整至文末，`check-doc-traces --ci`/`check-doc-links --ci` 全绿；十轮复盘记录落各文档终检节） |
| **rf-586** | **警告级（未越红线）跟踪——红线 8 个已随 rf-583 拆分清零，2026-10-05 `check-file-length.py -v` 派生**：行数最贴红线的 `unit/llm/test_llm_api_base.py`（1190 行，距 1200 仅 10 行）、`unit/report/test_penetration.py`（1141）、`unit/config/test_config.py`（1112）；用例数最贴 120 项红线的 `unit/scripts/test_check_doc_drift.py`（94 项）、`unit/config/test_config.py`（89 项）；`test_html_report_structure.py` 拆分后回落至 31 项，原 110 项警告解除 | 无门禁动作（800~1200 行 / 80~120 项仅 `-v` 清单）；再增内容前先跑 `check-file-length.py -v`，逼近红线时按「被测函数 / 场景类型」拆分并同步刷新 `test-coverage.md` / `folders.md` 用例计数 |

## 已解决问题

| # | 摘要 | 状态 |
|---|------|------|
| **rf-585** | `cli/cli.py` 910 行跨 800 硬上限且长期未登记 P2A 表（2026-10-05 `check-file-length.py` 首跑全仓查出，豁免挂账待拆） | 已修复 2026-10-06（按挂账建议拆分：新增 `cli/_parser.py` 承载 argparse 解析器构建与 type 回调（226 行）、`cli/_handlers.py` 承载子命令处理器/持仓读入辅助/`_EXIT_*` 退出码契约（521 行），`cli.py` 保留 `main()`/`run_cli()` 主流程与命令行功能开关应用并 re-export 全部对外符号（`__all__` 显式声明，`src.python.cli` 包导入与测试 patch 点 `cli.cli._handle_*` 零改动），910 → 243 行；测试 patch 目标随消费方迁移 4 文件（`_cli_read_holdings*`/`_cli_resolve_holdings_file`/`os.path.exists` → `src.python.cli._handlers.*`，含 `test_chain_overrides` 的 `monkeypatch.setattr` 改作用 `_handlers` 模块对象），156 项 CLI/源覆盖测试全绿；`check-file-length.py` EXEMPTIONS 移除 `cli.py`（豁免清空、违规 0 项）；`technical.md` §1.7 与 whatif 模块树、`folders.md` 目录树+统计、`testplan.md`/`test-coverage.md` 载体同步） |
| **rf-584** | >800 主程序 / >1200 测试文件行数红线无任何 `--ci` 脚本强制，且 P2A 登记表为人肉快照（api_base.py 699→831、chain.py 破线均未登记即放行） | 已修复 2026-10-05（新增 `scripts/check-file-length.py --ci`：复用 `_checklib`，主程序 >800 / 测试 >1200 即 finding 退出 2；豁免登记与本表挂账同步、拆分后自动提示移除；`-v` 输出警告区全集清单作 P2A/P2C 派生源；入 CI guards + pre-commit 十守护 + CLAUDE.md/developer-guide/testplan 五处清单同源校验（check-doc-drift 第 16 项）；15 项回归用例入 `test_check_file_length.py`；首跑全仓查出 cli.py 910 与 5 个未登记测试文件超限，已分别挂账 rf-585/rf-583；P2A/P2C 行数刷新为脚本派生） |
| **rf-583** | 超 1200 行红线测试文件 8 个（`test_html_report_structure.py` 2313 行 / 110 项、`test_orchestrator.py` 1963、`test_fact_checker.py` 1846、`test_market_value.py` 1746、`test_html_writer.py` 1661、`test_holdings_detail_sheet.py` 1485、`test_cli.py` 1410、`test_summary.py` 1344），且长期以人肉快照登记 | 已修复 2026-10-05（按「被测函数 / 场景类型」拆为同目录兄弟文件：structure → +`_toc`/`_content`、fact_checker → +`_context`、orchestrator → +`_generate_report`、market_value → +`_premium`、html_writer → +`_contents`、holdings_detail_sheet → +`_categories`、cli → +`_subcommands`、summary → +`_module_rows`；原文件全部保留为分片，testplan 载体路径有效；拆分前后 8 文件用例数逐份求和不变、17 份全绿，最长回落至 1056 行；脚本 EXEMPTIONS 8 条测试豁免移除、`check-file-length --ci` 违规 0 项，`test_check_file_length.py` 「两域均有挂账」断言改为「豁免不得过期」；`folders.md` 目录树 9 条 + 统计、`testplan.md` 8 处载体同步；警告级清单转挂 **rf-586**） |
| **rf-581** | `fetcher/chain.py` 822 行跨 800 硬上限且长期未登记 P2A 表 | 已修复 2026-10-05（**拆前先跑 P1 门禁** `test-runner.py --mode verify` → 7970 通过、0 失败；按三职责拆为 `chain_config.py` 链定义与覆盖 + `chain_diagnostics.py` 失败诊断与命中归属 + `chain_incremental.py` 历史增量合并，`chain.py` 只保留 `fetch_with_fallback` 路由执行并对子模块符号 re-export——对外 API 与既有 `from ...fetcher.chain import X` 调用方零改动，822 → 305 行；跨模块 patch 目标随消费方迁移 11 处（`test_chain`/`test_chain_overrides`/`test_fetcher`/`test_credential_gate`），静态审计「patch `chain.X` 但 `chain.py` 已不消费」= 0，8590 项全绿；`check-file-length.py` EXEMPTIONS 移除 `chain.py`（仅剩 `cli.py` 挂账，违规 0 项）；`folders.md` 目录树 3 条 + 统计、`technical.md` 模块树/加载注册/凭据预检/历史链路 4 处、`datasource-reliability.md` 2 处、`developer-guide.md` 1 处指针同步） |
| **rf-582** | `llm/generators_orchestrator.py`（798）与 `report/_report_generation.py`（786）距 800 硬上限仅 2 / 14 行 | 已修复 2026-10-05（按 finding 建议两条轴各拆一刀：① orchestrator 下沉并发调度/进度回调 → 新增 `llm/_llm_dispatch.py`（`_build_module_fns` 模块→生成函数映射 `_MODULE_FNS` + `_dispatch_llm_workers` 线程池分发/进度回调/thinking 串行上限/辩论 `_debate_wrapper` 路由 + `_LLM_CLIENT_SETTINGS`），门面 re-export `_dispatch_llm_workers`（消费方 `generate_all_llm` 在门面 → 既有 patch 点不变）且 `__all__` 移除仅新模块消费的两个符号，798 → 480 行；② _report_generation 下沉产物落盘 → `_generate_full_html_report` 并入既有 `report/_report_output.py`（与 `_generate_full_excel_report` 同居，89 → 232 行），门面 import 保留 patch 点，786 → 649 行；测试 patch/import 目标随消费方迁移（6 个测试文件，`patch("…X")` / 属性链 `…X.Client` / `patch.object(orch, X)` 三种形式逐一迁到 `_llm_dispatch`，漏迁一律 AttributeError 响亮失败、零静默），全仓 8590 项全绿；llm-technical 模块清单、technical「LLM 模块注册」架构约束与辩论路由、developer-guide ④注册步骤、folders 目录树/统计同步） |
| **rf-580** | `llm/api_base.py` 在 36 小时实现窗口内从 699 → 831 行，跨过本文件 P2A「>800 行硬上限必须拆分」（增长主要为 429 诊断建议函数与 pacing 整改回显），且未登记 P2A 表、无门禁拦截 | 已修复 2026-10-05（`_concurrency_hint` 整体移入其功能文档本就归属的 `llm/pacing.py` §4.2.1，api_base 回落 737 行；归属一致性 + 800 行上限回归用例入 `test_llm_pacing.py`；`llm-technical` / `developer-guide` 两处符号指针同步） |
| **rf-579** | 429 诊断「端点已=1 而全局 >1 → 建议调低全局」是恒无效建议：生效并发 = min(全局, 端点)，端点已钳到 1 时调低全局（3→2→1）从不减少该端点在途并发；「端点>1」分支并列建议调低非绑定项（如全局 5 > 端点 2 时叫调低全局）同样绕路；「两级均到底」建议含无效的「减少同时发起的生成任务」 | 已修复 2026-10-05（按生效并发绑定项给建议：>1 只列绑定项、=1 不给任何并发类建议改推 min_interval + 配额/风控；4 条用例变异实测改前全红，三处文档同步） |

> **本迭代已修复记录（rf-568、rf-571 ~ rf-578 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>

> **本迭代已修复记录（rf-563 ~ rf-570 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>
> **迁移说明**：已完成批次摘要（rf-557 ~ rf-562）已于 v0.12.1 发布（2026-10-03）随档迁入 [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)，本文件只保留未完成项与归档索引；更早批次（rf-541、rf-542 ~ rf-556）见 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)。

### 归档档案

- [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md) — v0.12.1 ~ v0.12.3 批次（2026-10-03 ~ 2026-10-05）
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
