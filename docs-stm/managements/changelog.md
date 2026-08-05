# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.6-dev] - 2026-08-05

### 开发中（未发布）

### 测试模式耗时标注更新（换机实测 + 机型依赖说明）

- **动机**：测试环境从旧慢笔记本换到当前开发机（Linux x86_64，Intel i5-13500H，12 核 16 线程，46GiB 内存；pytest-xdist worker=8 = medium 50% 核数）后，各测试模式实际耗时大幅下降（如 `all` ~10min → ~21s、`scenario` ~6min → ~18s、`scenario_extreme` ~1min 45s → ~2s），test-coverage.md「典型耗时」列与 test_runner.py 模式描述中的时间标注已严重过时。
- **实测**：2026-08-05 顺序运行除 `live`（opt-in 运维套件，不入门禁）外全部 14 个模式记录 pytest 总耗时——unit ~15s / standard ~16s / scenario ~18s / regression ~17s / dev-verify ~20s / verify ~10s / integration ~14s / edge ~13s / data ~2s / all ~21s / all_no_unit ~10s / smoke ~2s / report ~11s / scenario_extreme ~2s。
- **更新**：`scripts/test_runner.py` MODES 描述 4 处时间估算（dev-verify ~2.5min→~20s、scenario_basic 阶段 ~100s→~10s、smoke ~15s→~2s 且项数 24→26、scenario_extreme ~1min→~2s）并标注「12 核 16 线程并行实测」；`test-coverage.md` 模式表「典型耗时」列全部刷新为实测值，并加注说明**耗时与硬件/并行度强相关**（早期标注源自慢笔记本环境，仅作相对量级参考）；同步刷新 `scripts-reference.md`「--mode 对照」表与 `how-to-test-my-code.md` 门禁/流水线/模式说明中的全部耗时标注，并在 test-coverage.md / scripts-reference.md / how-to-test-my-code.md 三份文档补充统计所用硬件配置（i5-13500H 12 核 16 线程 / 46GiB 内存 / worker=8）。
- **门禁**：各模式实测全部通过；改动仅涉及描述字符串与文档，不影响测试逻辑。

## [0.10.5] - 2026-08-05

### plan.md 已完成事项整体归档至 archived_plan.0.10.x.md

- **动机**：`plan.md` 承载当前迭代待办 + 已完成项详细记录，v0.10.x 已发布事项（plan-17~24）详细段落随迭代推进持续累积，活跃文档过重。按「已完成历史版本计划已归档，此处仅跟踪当前迭代中的工作」原则，将已发布（v0.10.1/v0.10.3/v0.10.4）的已完成事项记录整体迁入归档索引，`plan.md` 回归轻量「未完成项 + 归档引用」结构。
- **迁移内容**（`plan.md` → `docs-stm/archive/v0.10.x/archived_plan.0.10.x.md`）：P0 发布门禁两条（v0.10.3/v0.10.4）、推荐实施顺序 ①~⑧ 表格、P1~P3 已完成项详细段落（plan-17~24 每项轮次/验收/门禁记录）。
- **归档文档结构**：设计文档索引（investment-features + task-code-traces-gate）+ v0.10.x 已完成项摘要表 + P0 发布门禁 + 推荐实施顺序 + P1~P3 详细段落（原相对链接改指本目录内 `investment-features/` 兄弟路径）。
- **plan.md 精简**：概述改为指向归档（含设计文档索引 + 完成项摘要表 + 推荐实施顺序 + 发布门禁记录）；当前迭代待办仅保留 P4 实验功能（plan-8/plan-10，未完成）；归档列表保持。
- **状态变更**：`plan.md` 中已完成项状态由「当前迭代待办」转为「已归档」；`plan-next` 编号源不变（已用最大 plan-24，归档不回收）。

### 新增 opt-in live 真实网络验证套件（不入门禁）

- **动机**：既有测试体系全 mock（网络依赖由运行时回退/熔断治理，非门禁），无法直接排查「数据源是否真的可达 / API 是否漂移」。新增 `live` 套件作为独立运维验证通道，与门禁严格隔离。
- **基建**：`src/test/live/` 14 项真实联网测试（行情：A 股/ETF/场外基金/中美指数；新闻：东方财富/财联社/新浪/华尔街见闻；基金：历史净值/排名/基准；akshare 交易日历）。三层机制保证**平时完全不运行**：① `pytest.ini` `addopts = -m "not live"` 收集期排除；② conftest `_skip_live_unless_requested` autouse fixture 默认 skip；③ test_runner 门禁模式不引用。验证：全量收集 4981/4995（14 deselected，即 live 被排除）。
- **断言原则**：只校验返回「结构」（字段存在、类型、非空），不校验具体数值，容忍真实行情波动；不含 LLM 真实调用（防费用）。`_block_external_network` 阻断 fixture 放行 live 项（显式 `--run-live`/`-m live` 时）。
- **触发方式**：`python scripts/test_runner.py --mode live`（新增 MODES 条目，order 14）或 `pytest --run-live -m live`。
- **文档同步**：how-to-test-my-code.md（②专项验证代码块 + 新增 live 小节 + 报告目录树）、testplan.md（测试环境网络行标注 live opt-in）。
- **门禁**：dev-verify 1706 passed + 3 check 全 [OK]。

### 功能语义命名表抽取为活索引（technical.md §6.7）

- **动机**：CLAUDE.md「语义化命名」条目原引用归档文档（`docs-stm/archive/v0.10.x/investment-features/plan-investment-features.md` §2.0）作功能语义命名表，归档后引用路径不稳定、可追溯性差。共性语义命名表应入管理文档作为**活索引**，各轮设计文档中的原始表降级为历史快照。
- **抽取**：`technical.md` 新增 `### 6.7 功能语义命名表`——纪律说明（代码标识符=文档中文描述、先定语义名再设计、任务代号不入实现层）+ 14 行核心功能语义命名表（candidate_compare/valuation_percentile/market_temperature/rebalance_advice/trade_discipline/return_attribution/fund_flow/dividend_flow/industry_beta/crisis_annotation/tail_risk/snapshot_diff/data_quality/holding_diagnosis）+ 合并章 key 说明（position_relationship/portfolio_history_drawdown/style_factor）+ registry.number 重排说明（1~19）；同时更新技术文档目录 TOC 添加 6.7。
- **引用改向**：CLAUDE.md「语义化命名」条目引用改指 `docs-stm/managements/technical.md` §6.7（活索引）；归档 `plan-investment-features.md` §2.0 原始表保留为历史快照不追溯修改。
- **门禁**：check-code-traces.py 不引用归档表格（抽取无冲突），3 check 脚本 `--ci` 待最终全量验证。

### 消除测试用例运行时外部网络依赖（全局 socket 阻断防线）

- **审计方法**：临时 socket 阻断插件全局替换建连入口（socket.socket 用类替换保留 ssl 继承、socket.create_connection / getaddrinfo 函数替换），扫描全部测试套件——凡触发真实网络连接的用例立即失败暴露。unit 套件 + scenario/integration 共扫描出 **5 处**未 mock 的真实网络依赖。
- **修复 5 处未 mock 网络调用**：
  - `test_fetcher.py::TestFetchFundBenchmark`（2 例）：`fetch_fund_benchmark` 三层策略（API 解析→内置知识库→配置覆盖）先走 API 解析层联网；mock `_fetch_benchmark_from_api` → None 改走内置基准库，用例改用内置库真实代码 561910。
  - `test_data_integrity.py::test_a_index_value_ranges` / `test_cache_consistency.py::test_index_cache_shared_across_modules`：mock 指数数据只覆盖 5/1 个，而 `_A_INDICES` 共 7 个 → 缺失项触发新浪备用链路联网；补 patch `_fetch_indices_from_sina` → {} 阻断 fallback。
  - `test_orchestrator.py::test_generate_report_skeleton`：骨架 basic 路径真实生成 Excel，依赖交易日历（akshare 联网）+ A 股/美股指数 + 后台数据源健康检查（全量 HTTP 连通性探测）；补 mock `_get_trading_calendar` / `fetch_indices` / `fetch_us_indices` / `_spawn_health_checks` / `_collect_health_checks`。
- **全局防线**：`conftest.py` 新增 `_block_external_network` autouse fixture——测试运行时全局阻断 socket 建连，任何未 mock 的网络调用（数据源 API / LLM API / akshare / 健康检查）立即抛 RuntimeError 使测试失败，从机制上杜绝测试运行时外部网络依赖。已 mock HTTP 层（httpx.Client / requests / provider / `_fetch_*`）的测试不创建真实 socket，不受影响；真实建连仅发生在「应 mock 却未 mock」时。
- **验证**：unit 4660 passed + 12 skipped、scenario+integration 309 passed + 76 subtests、dev-verify 1706 passed / 0 failed，均无外部网络依赖。

### 文档全面核对与修复（folders.md 统计刷新 + 用户/管理文档一致性审计）

- **folders.md 统计与目录树核对**：项目统计表核对至当前实时状态（主程序 222 文件/55,247 行、HTML 4 文件/3,761 行、辅助脚本 16 文件/5,581 行、源代码合计 242 文件/64,589 行、测试代码 276 文件/78,332 行、测试用例 4,980 个）；目录树层级符号对齐（`├──`/`└──` 一致性）与文件补录；报告章节图表初始化描述「6 张」→「9 张（6 核心 + 3 演进；单图异常隔离 + degraded 虚线）」。
- **管理文档一致性核对**：technical.md 12 处修复——缓存层线程池唯一宿主表述、线程池表由 2 池补全为 9 池（orch_prep/orch_factor/orch_factor_idx/orch_ind/orch_ind_idx/orch_val/orch_corr/orch_llm_news/orch_health，含用途与 max_workers）、基金深度分析模块数 5→4、相关性区块数据契约引用改指附录 H 且架构约束注册引用改指 §8.3、STATUS_MESSAGES「23 条」→「24 条」、llm/ 子模块「36 个」→「32 个」、`module_{标识}`→`{参数}_{标识}` 命名约定、portfolio_evolution number=16、action number=17；requirements.md 8 处——降级引用统一「technical.md §1.4.5」、调仓建议/收益归因由「框架子块」更新为「已实现（无数据写『待生成』）」；testplan.md——场景规格表头补齐 D1-D3、无人工门禁表述更新、unit_config_edge 预留说明；llm-technical.md——批处理并行度「最多 3 批并行」表述、附录 B 定价表补 claude-sonnet-4-8/claude-opus-4-6 具名模型 + 6 个前缀回退键脚注；test-coverage.md——分组标题层级统一、场景覆盖项数/文件数/基准指数覆盖表述刷新；README.md——Chart.js 图表数 6→9。
- **用户手册一致性核对**：how-to-test-my-code.md 场景编号 S1-S34→S1-S33（S34 基准指数对比为合法规格项、由单元测试覆盖，testplan.md 规格表保留 S34）；reports-instruction.md / faq.md / how-to-config.md / datasource*.md / how-to-menu.md 等章节序号、目录锚点、模型名、数据源清单核对至最新状态。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]，dev-verify 1706 passed / 0 failed。

### 修复 akshare 交易日历并发 V8 崩溃（rf-228）

- **问题**：TUI 菜单「2」更新行情缓存时进程崩溃，`[FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized()`（abort 整个进程，try/except 无法捕获）。根因链：菜单 2 并行价格抓取（ThreadPoolExecutor 4 workers）→ 每价格新鲜度校验 `_price_cache_fresh` → `get_last_trading_day()` → `_get_trading_calendar()` → `akshare.tool_trade_date_hist_sina()`（新浪交易日历）。akshare 该函数内部用 `py_mini_racer`(V8) 解密、**每次调用都新建 V8 实例**；多线程并发首次初始化 V8 触发 `partition_address_space` FATAL。已在 tmp 探针脚本复现（4 线程并发 → EXIT 3 崩溃；加锁串行化 → 全成功）。
- **修复**：`market_value.py::_get_trading_calendar()` 缓存未命中分支用模块级锁 `_TRADING_CALENDAR_AKSHARE_LOCK` 串行化 + **双重检查**（锁等待后重新读缓存，避免重复拉取）。V8 顺序初始化安全。不影响单线程正常路径。
- **回归测试**：`test_market_value.py` 新增 `TestTradingCalendarConcurrency`——4 线程并发调 `_get_trading_calendar()`，注入 fake akshare（`patch.dict(sys.modules)`）统计回调最大并发深度，断言**串行化不变量 max_active == 1**。全 mock 无真实 V8/网络调用。
- **连带优化**：审计发现 `test_market_value.py` 多个测试类裸调用 `is_market_open`（东方财富 push2 API 真实 HTTP，timeout 5s）与 `_is_trading_day`（akshare 交易日历网络）导致单用例 2~6s。为 `TestPriceUpdateStatus`/`TestDeterminePriceType`/`TestGenerateDetails`/`TestPremiumPlaceholder`/`TestTodayProfitEastMoneyNonTDay`/`TestTodayProfitTencentAlways`/`TestTodayProfitEdgeCases`/`TestPremiumInWriteSheet`/`TestCurrencyConversion`/`TestTodayProfitOffMarket` 统一补 setUp mock（`is_market_open`/`is_midday_break`/`_is_trading_day`），消除用例内网络依赖。用例 call 时间从 2~6s 降至 0.01~0.08s（剩余启动开销为环境 Python 解释器慢，与测试无关）。

### HTML 报告目录 LLM 章节标记（橙色加粗 + 🧠 图标）

- **功能**：HTML 报告两处导航（左侧目录 `.toc-sidebar` + 窄屏顶部横向 `.section-nav`）中，由 LLM 生成/支持的章节标题改为**橙色加粗**并在标题旁显示 **🧠 图标**。dark mode 下橙色复用双定义变量 `--orange-text`（浅色 `#E65100` / 深色 `#ff8a50`），天然适配。
- **标记范围**：与「LLM」导航组同源派生——`html_writer.py` 新增常量 `_LLM_SUPPORTED_SECTIONS`，从 `_SECTION_NAV_GROUP_MAP` 的 `"llm"` 组推导（单一数据源防漂移，覆盖新闻关联 + LLM 文本分析系列 + API 用量），经 render() context 传入模板（渲染期数据经 context 传递约束）。
- **实现**：模板目录/横向导航链接按章节 LLM 支持位加 `toc-llm` class 与 `span.toc-llm-icon`（`aria-hidden="true"`）；CSS 新增 `.toc-list a.toc-llm` / `.section-nav a.toc-llm`（橙色加粗）与 `.toc-list a.toc-llm.active`（active 态保持橙色，特异性高于既有 active 规则）；打印样式已隐藏两导航，无需处理。
- **测试**：`test_html_report_structure.py` 新增 7 例（常量与「LLM」组一致性、目录/横向导航标记与未标记断言、分组 dict 携带 `llm_supported`、CSS 规则存在、颜色变量双定义复用），并更新 2 例既有测试（剔除 🧠 图标后比对导航文字一致性 / LLM 目录文案前缀+图标断言）。report 套件单测全绿（1482 passed）。

### 迭代计划归档（plan-17~24 收官，2026-08-05）

- **归档**：`plan-investment-features.md`（设计层）+ `plan-investment-iteration.md`（实施层，21 轮）由 `docs-stm/plan/` 移入 `docs-stm/archive/v0.10.x/investment-features/`；`plan-task-code-traces-gate.md`（rf-208 门禁增强设计）移入 `docs-stm/archive/v0.10.x/task-code-traces-gate/`。新增 `docs-stm/archive/v0.10.x/archived_plan.0.10.x.md` 归档索引（已完成项表 plan-17~24 + 设计文档索引 + 归档说明），沿用 v0.9.x `archived_plan.*.md` 格式。
- **引用同步**：plan.md 概述/推荐实施顺序/已完成章节链接改指归档索引与归档路径，归档区新增 `archived_plan.0.10.x.md` 条目；folders.md 目录树 `plan/` 仅保留未完成项（plan-web-ui*/plan-web-ui-implementation*），新增 `archive/v0.10.x/` 子树；CLAUDE.md 语义化命名条目中功能语义命名表示例路径改指归档文档。`docs-stm/plan/` 现仅存 plan-8/plan-10（P4 实验功能）设计文档。
- **门禁**：3 check 脚本 `--ci` 全 [OK]（check-task-numbering exit 0，归档编号与历史归档无冲突）。

### changelog 主题标题层级统一（v0.10.3 起 `####` → `###`）

- 修正 v0.10.3/v0.10.4/v0.10.5-dev 各版本主题标题层级漂移：开发节引入 `### 开发中（未发布）` 占位后主题误用四级 `####`，转正式节时未同步升回。现统一为三级 `###`，与 v0.10.0~0.10.2 及 v0.9 分类层级（`###`）对齐。v0.9.x 归档保持原格式不追溯。

### CLI 集成测试 patch 目标修正（rf-227）

- **问题**：`test_cli_integration.py` 三处 CLI 测试 patch 目标陈旧——41df26a「根文件归子包」重构后残留包级 re-export 路径 `src.python.cli._cli_read_holdings`，拦截不到 `cli.py` 模块内部同名引用。`test_cli_cache_config_respected` 因此走到真实持仓读取（`/test/holdings/test.xlsx` 不存在）→ mock 调用 0 次断言失败；另两例（`test_cli_report_config_respected`/`test_handle_report_return_exit_code`）靠 `data/holdings/` 默认持仓文件恰好存在而侥幸通过。
- **修复**：三处 patch 目标统一修正到 `src.python.cli.cli._cli_read_holdings(_with_flows)`；report 路径两例改用 `_cli_read_holdings_with_flows` 返回 `(mock_holdings, [], [])`（与 `_handle_report` 实际调用路径一致），彻底脱离真实持仓文件依赖，测试隔离达标。
- **验证**：全量 `test_runner.py --mode all` 5026 passed / 0 failed / 12 skipped；CLI 单测 `test_cli.py`+`test_cli_edge.py` 56 passed 无回归。

### 历史记录归档（review-findings + changelog，v0.10.x 已发布记录迁入归档）

- **review-findings 归档**：`docs-stm/managements/review-findings.md` 已修复表中 v0.10.1/v0.10.3/v0.10.4 的已修复条目（rf-204~rf-226，dev 版 rf-227/rf-228 除外）整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md`，按版本分组（v0.10.1：rf-204~216；v0.10.3：rf-218~225；v0.10.4：rf-226）保留「问题 / 修复方案 / 变更记录」完整记录；`review-findings.md` 已修复表仅保留 dev 版未归档条目（rf-227/rf-228），归档档案段新增 v0.10.x 链接；P3 段末尾 rf-226 补齐注释随迁移删除（信息在归档中）。
- **changelog 归档**：`docs-stm/managements/changelog.md` 中 v0.10.1~v0.10.4 四个已发布版本段整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（v0.10.0 无独立 changelog 段，不单独归档）；`changelog.md` 保留 v0.10.5-dev 开发段 + 归档列表（新增 v0.10.x 链接）。
- **目录同步**：`folders.md` 目录树 `archive/v0.10.x/` 补 `archived_changelog.0.10.x.md` / `archived_review-findings.0.10.x.md` 两行（与 v0.9.x 段三文件并列结构对齐）。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]；全量测试 `test_runner.py --mode all` 4969 passed / 0 failed / 12 skipped；版本号全链一致 v0.10.5。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.4（2026-08-04 ~ 2026-08-05）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
