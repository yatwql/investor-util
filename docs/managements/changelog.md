# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.3]**（2026-10-05）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.4-dev] - 开发中（未发布）

### Added

- **工程门禁**：新增单文件行数红线守护 `scripts/check-file-length.py --ci`（复用 `_checklib`：主程序 >800 行 / 测试 >1200 行即 finding 退出 2；既有超限项豁免登记与 `review-findings` 挂账同步、拆分后自动提示移除；`-v` 输出 >500/>800 警告区全集清单作登记表派生源，人肉快照退役），入 CI `guards` job + pre-commit 十守护 + CLAUDE.md/developer-guide/testplan 门禁清单（`check-doc-drift` 第 16 项五处同源校验）；15 项回归用例入 `test_check_file_length.py`；首跑全仓查出 `cli/cli.py` 910 行与 5 个未登记测试文件超 1200 行红线，已分别挂账 rf-585/rf-583（rf-584 归档已解决）

- **HTML**：正文大块折叠新增「持仓结构与集中度」「风格与因子分析」「数据源可用性矩阵」三个章节——与既有折叠章同构（章标题与「回到顶部」常显于折叠块外、内容包 `details.section-fold`、`summary` 提示条带该章关键摘要：基金数与组合对数 / 基金风格数 / 数据源数，文案自带展开/收起指引，原生键盘可达），缺省一律收起且打开报告（含带 `#锚点`）不自动展开；结构回归用例 `_FOLD_KEYS` 扩展至六个折叠章节（包裹/默认收起/summary 首元素/标题回顶在外/摘要五类断言逐章遍历，`unit_report` 域 2135 项全绿）；`reports-instruction` ④节折叠章清单同步

### Changed

- **LLM/报告/工程**：两个 800 行临界文件按职责拆分（**rf-582** 归档已解决）——① `llm/generators_orchestrator.py`（798，距硬上限仅 2 行）下沉**并发调度/进度回调** → 新增 `llm/_llm_dispatch.py`（`_build_module_fns` 模块→生成函数映射 `_MODULE_FNS` + `_dispatch_llm_workers` 线程池分发/进度回调/thinking 串行上限/辩论 `_debate_wrapper` 路由 + `_LLM_CLIENT_SETTINGS`），门面 re-export `_dispatch_llm_workers`（消费方 `generate_all_llm` 在门面 → 既有 patch 点不变），798 → 480 行；② `report/_report_generation.py`（786）下沉**产物落盘** → `_generate_full_html_report` 并入既有 `report/_report_output.py`（与 `_generate_full_excel_report` 同居，89 → 232 行），门面 import 保留 patch 点，786 → 649 行；测试 patch/import 目标随消费方迁移 6 个测试文件（`patch("…X")` / 属性链 `…X.Client` / `patch.object(orch, X)` 三种形式逐一迁到 `_llm_dispatch`，漏迁即 AttributeError 响亮失败、零静默 no-op），全仓 8590 项全绿；llm-technical 模块清单、technical「LLM 模块注册」架构约束与辩论路由、developer-guide ④注册步骤、folders 目录树/统计指针同步

- **取数/工程**：`fetcher/chain.py` 按三职责拆分子模块（**rf-581** 归档已解决）——822 行跨 800 硬上限；**拆前先跑 P1 门禁**（`test-runner.py --mode verify` → 7970 通过、0 失败）。拆为 `chain_config.py`（`_DEFAULT_CHAINS` 优先链定义 + preferred/exclude 覆盖 + 链健康判定 + 加载时注册默认链/交易日历兜底）、`chain_diagnostics.py`（`FailureDiagnostics` 失败载荷 + 原因短句截断 + 命中归属登记）、`chain_incremental.py`（历史序列增量合并：payload 语义版本闸门 / 按日合并 / 交易日连续性校验 / provider 递补），`chain.py` 只保留 `fetch_with_fallback` 路由执行并对子模块符号 re-export——对外 API 与既有 `from ...fetcher.chain import X` 调用方零改动，822 → 305 行；测试侧跨模块 patch 目标随消费方迁移 11 处（`chain.get_config` → `chain_config`、增量路径 `chain.cache_*`/`_try_providers`/`_call_history_provider` → `chain_incremental`），静态审计「patch `chain.X` 但 `chain.py` 已不消费」= 0，全仓 8590 项测试全绿；`check-file-length.py` EXEMPTIONS 移除 `chain.py`（仅剩 `cli.py`，违规 0 项）；`folders.md` 目录树 3 条 + 统计快照、`technical.md` 模块树/加载注册/凭据预检/历史链路 4 处、`datasource-reliability.md` 2 处、`developer-guide.md` 1 处指针同步

- **测试/工程**：8 个超 1200 行红线测试文件按「被测函数 / 场景类型」拆分为同目录兄弟文件（**rf-583** 归档已解决）——`test_html_report_structure.py`（2313 行/110 项）→ +`_toc` +`_content`、`test_orchestrator.py`（1963）→ +`_generate_report`、`test_fact_checker.py`（1846）→ +`_context`、`test_market_value.py`（1746）→ +`_premium`、`test_html_writer.py`（1661）→ +`_contents`、`test_holdings_detail_sheet.py`（1485）→ +`_categories`、`test_cli.py`（1410）→ +`_subcommands`、`test_summary.py`（1344）→ +`_module_rows`；原文件一律保留为分片（共享常量/助手仍从原模块导入，6 个外部文件既有导入不受影响），拆分前后 8 文件用例数逐份求和不变（749 项）且 17 份全绿、最长回落 1056 行、`test_html_report_structure.py` 回落至 31 项；`check-file-length.py` EXEMPTIONS 的 8 条测试豁免移除（违规 0 项，`cli.py`/`chain.py` 两条主程序豁免仍在），`test_check_file_length.py`「两域均有挂账」断言改为「豁免不得过期」；`folders.md` 目录树 +9 条与统计快照、`testplan.md` 8 处载体行补登新分片，警告级清单转挂 **rf-586**（rf-next → 587）

- **HTML**：正文大块折叠「打开报告缺省一律收起」——原 `fold.js` 初始 load 无条件执行锚点展开，浏览器恢复会话/地址带 `#sec-…` 打开报告会把目标章折叠块自动展开；改为初始 load 不执行锚点展开（模板本就无 `open` 属性，缺省收起不依赖 JS），会话内点击目录原生锚点链接（hashchange）仍自动展开目标章保证跳转可见，打印展开/恢复与手动展开 resize 不变；新增结构回归用例（初始 load 不得执行锚点展开），`reports-instruction` ④节同步
- **文档**：折叠覆盖章节在管理文档表述——`technical.md` 新增 §4.21（覆盖章节清单表、缺省收起/锚点/打印/resize 语义与模板测试载体）、`requirements.md` 新增 `R-OUT-12` + `testplan.md` 同步载体行（`test_html_report_structure.py`，需求追溯双向一致）

### Fixed

- **LLM/结构**：`api_base.py` 跨 800 行硬上限拆分（**rf-580**）——429 诊断建议函数与 pacing 整改回显使其 699 → 831 行，跨过「>800 行必须拆分」红线且期间无门禁拦截；`_concurrency_hint` 整体移入其功能文档本就归属的 `llm/pacing.py`（`llm-technical` §4.2.1 本就按 pacing 描述该行为），`api_base` 顶层导入复用、回落 737 行，行为逐字节不变（既有 429 诊断用例全绿）；新增归属一致性 + 800 行上限回归用例（`test_llm_pacing.py`，2 项）；`llm-technical` §4.2.1 / `developer-guide` 日志回显两处符号指针同步；同批自审登记 **rf-581 ~ rf-584**（`chain.py` 822 超限未登记、`generators_orchestrator.py` 798 临界、测试文件三项超 1200 行红线、行数红线无 `--ci` 门禁）

- **LLM/日志**：429 诊断无效并发建议根治（**rf-579**）——原「端点已=1 而全局 >1 → 建议调低全局」是恒无效建议：**生效并发 = min(全局, 端点)**，端点已钳到 1 时把全局从 3 调到 1 也从不减少该端点在途并发（实测场景：kimi-main `pacing.max_concurrency=1` + 全局 3 仍 429，日志却叫调低全局）；改为按**绑定项**判定：生效并发 ≥2 只建议等于生效并发的那一级（端点<全局只调端点、全局<端点只调全局、相等则两列，非绑定项注明「须低于对方现值才生效」），生效并发 =1 时明确「调低任何并发旋钮均不再减少该端点在途并发」，改推 `pacing.min_interval`（带当前值）+ 请求速率/配额（RPM/TPM）/风控/切换 provider；原「两级均到底」建议中的「减少同时发起的生成任务」属同类无效（在途已串行=1 时任务数不改变请求速率）一并移除；4 条用例（用户场景 + 三种绑定形态）变异实测改前全红；`llm-technical` §4.2.1、`how-to-config-llm` 429 回显、`faq` 429 问答三处行为描述同步

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.3（2026-10-03 ~ 2026-10-05）
- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12 + v0.12.0（2026-09-15 ~ 2026-10-03）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12)
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
