# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.3]**（2026-10-05）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.4-dev] - 开发中（未发布）

### Added

- **工程/评测**：**因子动物园目录评测**完成（先决门槛即评测本体）——新增评测脚本 `scripts/factor_zoo_eval.py`（阶段 `catalog|fields|signals|timing|verdict|all`：25 因子五来源族目录冻结 → 字段可得 → 信号相关 → 耗时基线 → 判定汇总；生产代码零改动、无 report/llm 导入、字段取数仅经既有链路、相关性复用 `analysis/correlation._pearson_pvalue`、产物只落 `docs/tmp/factor-zoo/`），实测三指标全过：**A 字段可得率 23/25 = 92% ≥ 80%**（未过 2 项为 push2 扩展字段空值、源侧暂不可用挂 rf-592 可复评）、**B 低相关占比 19/23 = 82.6% ≥ 30%**（分母 23 ≥ 10，`rebalance_overflow` 族按设计降级；Δ 一阶差分 Pearson、季频阶跃按结构性不相关 ρ=0、不可评估 fail-closed）、**C 冷启动估算 12.831s ÷ 报告基线 446.255s = 2.9% ≤ 20%**（池外冷样本均延迟 × 请求数；基线 = perf 近 5 次 full 中位数）→ **判定：转正立项**，实施另起 **plan-81**（plan-next → 82）；40 项脚本单测（A/B/C 阈值恰等边界、判定三态、基线读取、相关性口径、注入探针全离线 + edge 空输入/退化/极端值 fail-closed）；设计文档归档 [`factor-zoo-catalog-design.md`](../archive/v0.12.x/factor-zoo-catalog/factor-zoo-catalog-design.md)（已评测·判定转正立项，§13 判定记录），plan.md/vibe 研究文档/folders/test-coverage 同步；评测期自审修复入 review-findings（**rf-591** 对数市值非有限值已归档已解决、rf-592 push2 扩展字段空值挂待处理复核）

- **报告/取数**：What-if **回放交易成本建模与业绩基准对比**落地（`whatif_trade_cost` 实验开关，默认关，关态与既有产出**逐字节一致**）——四迭代：① `analysis/trade_cost_model.py` 纯计算（快照事件 **FIFO 批次**重放：期初批=快照首见日**下界估计**标注、批次按**交易日**持有期阶梯选档加权、买入腿金额分档含「每笔N元」、场内腿未建模显式标注、未知 `fees_complete=False` 不冒充 0；表选档/文本解析下沉 `analysis/fee_schedule_model.py`——前者 835 行跨红线按拆分纪律拆出，`EXEMPTIONS` 不新增）；② 费率数据三级可得性：`providers/tiantian_fund_fee.py` F10 费用页直连（`FEE_SCHEMA` 载荷准入，赎回表缺失即整载荷判无效不污染旧缓存）→ `fetcher/fund_fee.py::fetch_fee_index` 持仓级索引（链注册 `fund_fee` = `tiantian_f10` → `akshare_fee` 备链 → 过期缓存，`refresh` 缓存组 + 数据源矩阵归类）→ 申购侧 F10 优惠档/申购状态全量表「手续费」列（`table_single`/`table_multi`）→ `fund_fee_fallback` 配置兜底（仅补在线不可得侧不覆盖，在线结果优先；键值校验）；先决门槛抽样 20 只经真实管线复测两费率侧均 **95% ≥ 80%**；③ `analysis/benchmark_index_resolver.py` 三阶基准映射（`whatif_benchmark_index` 合法指数码 → 目标持仓基准文本反查 `comparison_indices` → 默认 sh000300，源标注零 I/O）+ `report/whatif_cost_panel.py` 双端面板（成本汇总/逐腿 11 列 + t0 一次性扣费成本前/后差对原 100 基线 + 基准曲线 LOCF 对齐归一，分阶段降级；Excel 第 5 页签「交易成本对比」+ HTML⑧ 区与图表负载裁剪契约、说明区条件重编号⑨/⑧）；④ 回归网：关态 sha256 黄金断言（与产出前模板同数据渲染逐字节一致）+ 换手 30% × ≈19.5bp **方向翻转**回归（人工复核入网）+ Excel/HTML 双端数值一致；需求 **R-WIF-12~14** 入 §6.11、testplan 批 8 载体、TUI 菜单 12-28 号与开关 31 项（实验 5）、`reports-instruction` 条件页签与产物描述、datasource(-reliability) `fund_fee` 链与缓存行、`how-to-config` 两个配置键、technical 语义命名表 7 条、folders/test-coverage 快照同步；设计文档归档 [`whatif-cost-benchmark-design.md`](../archive/v0.12.x/whatif-cost-benchmark/whatif-cost-benchmark-design.md)（已实施，§14 门槛与验收记录）；开发期三处自审修复入 review-findings（`rf-588` 数据源矩阵缺 fund_fee 归类、`rf-589` registry 缓存组缺 fund_fee 模块、`rf-590` trade_cost_model 超行红线拆 fee_schedule_model，均归档已解决）

- **报告/LLM**：**持仓变动复盘**落地（快照事件级，`holding_change_review` 实验开关，默认关）——四迭代：① `analysis/holding_change_events.py` 快照序列按日去重 + 逐对差分出 `change_event` 事件表（份额净变动分类，缺字段降级不虚构）+ 快照保留 **60 → 180 天**（`core/constants.py`/`_config_defaults.py`/`_snapshot.py`/`config.json` 四处同步）；② `analysis/holding_change_metrics.py` 纯计算（变动频率/加减清仓结构/意图对账/交易日模式 + `detect_account_reorder` **账户重排双形态识别**：清仓→新增优先、≥5 代码阈值）；③ `report/holding_change_panel.py` Excel/HTML 双端单源面板（默认序在数据源可用性矩阵/基本面快照/LLM 用量面板之前——该三项随之顺延，事件表+「区间净额推断、非逐笔」局限标注两端同源常驻，关态逐字节不变）；④ LLM 归因**双轨**——附录**第 5 段** `holding_change_block` 随四模块+辩论 pro/con/synthesis+自检携带（指纹按段条件并入，空块逐字节不变）+ 注册表串行模块 `holding_change_review`（镜像 `self_review`：准入闸门/信号窗 top10/结果写 `holding_change_data.llm_review`/失败登记不外抛），`enabled_llm.holding_change` 默认开（章由实验开关门控）；需求 **R-HCR-01~06** 入 §6.13、`reports-instruction` 18 个报告页签与 9 组分组导航、TUI 菜单 8-11 号、测试 88 项（events 9+edge 7 / metrics 15 / injection 23 / panel 26+edge 8）；先决门槛三段全过（28 期/71 事件/人工认可），结构级结论与「账户结构变更」边界记入设计文档 §15 验收记录

- **工程门禁**：新增单文件行数红线守护 `scripts/check-file-length.py --ci`（复用 `_checklib`：主程序 >800 行 / 测试 >1200 行即 finding 退出 2；既有超限项豁免登记与 `review-findings` 挂账同步、拆分后自动提示移除；`-v` 输出 >500/>800 警告区全集清单作登记表派生源，人肉快照退役），入 CI `guards` job + pre-commit 十守护 + CLAUDE.md/developer-guide/testplan 门禁清单（`check-doc-drift` 第 16 项五处同源校验）；15 项回归用例入 `test_check_file_length.py`；首跑全仓查出 `cli/cli.py` 910 行与 5 个未登记测试文件超 1200 行红线，已分别挂账 rf-585/rf-583（rf-584 归档已解决）

- **HTML**：正文大块折叠新增「持仓结构与集中度」「风格与因子分析」「数据源可用性矩阵」三个章节——与既有折叠章同构（章标题与「回到顶部」常显于折叠块外、内容包 `details.section-fold`、`summary` 提示条带该章关键摘要：基金数与组合对数 / 基金风格数 / 数据源数，文案自带展开/收起指引，原生键盘可达），缺省一律收起且打开报告（含带 `#锚点`）不自动展开；结构回归用例 `_FOLD_KEYS` 扩展至六个折叠章节（包裹/默认收起/summary 首元素/标题回顶在外/摘要五类断言逐章遍历，`unit_report` 域 2135 项全绿）；`reports-instruction` ④节折叠章清单同步

### Changed

- **工程/兼容清理（全兼容清理复检）**：移除两处旧结构兼容——① `config/features.py` 私有别名 `_FEATURES_FILE` 删除（15 处引用全部改用公开名 `FEATURES_FILE` 单源，含 `_path_isolation`/CLI/开关/配置编辑测试）；② `analysis/circuit_breaker_wrapper.py` 旧路径迁移 `_migrate_legacy_file`/`_LEGACY_METRICS_BREAKER_FILE` 删除（`data/cache/metrics_breaker.json` 旧路径自动迁移逻辑与 2 项迁移用例移除，`_path_isolation` 同步摘除旧路径 patch；本机旧文件不存在、新文件已在 `data/state/`）；全仓 `data/cache` 369 个缓存文件前缀逐一比对**无孤儿文件**（全部有在产代码生产者），`deepseek-chat/reasoner` 定价条目/whatif `_copy_js_assets`/自检 `_drop_legacy_cached_payload`/单链路 `_call_llm_legacy`/fund_manager 源格式回退经复检属在产能力（历史成本渲染/失效器/降级路径）予以保留；唯一可删文件 `data/config/features.json.bak`（开关覆写旧备份）已提报用户手动删除

- **plan/工程**：plan-76 路线改为**快照事件级**（持仓变动复盘，`holding_change_review`）——原「手工交易日志 xlsx」路线经可行性评估废弃：持仓快照历史与差异引擎已内建（`data/history/snapshots/` + `fetcher/history_diff`，2026-10 实测本机 87 期），连续快照差分即得变动事件，零手工；设计文档更名 `trade-journal-review-design.md` → `holding-change-review-design.md` 并按新路线全量修订（语义命名 `change_event`/`holding_change_events`/`_metrics`/`_panel`/`_llm_review`；先决门槛改「去重后有效快照 ≥12 期且变动事件 ≥10 个 / 事件口径唯一且局限显式标注 / 结构级结论人工认可」；五迭代改四迭代；预估成本中 → 低-中；能力边界诚实声明——结构级精度，不承诺逐笔胜率与精确持有期，沿用 `snapshot_diff` 不虚构边界）；plan.md 概述与 plan-70/76 条目、vibe 研究文档 7 处、decision 设计数据来源节、folders 目录树与统计同步

- **文档/计划**：`docs/plan/` 除 jev 两份外 8 份设计/研究文档完成十轮复盘增强——每份补齐：架构定位与依赖方向、架构约束逐条对照（语义化表述，不使用代号）、共享能力复用清单（防双实现）、技术债防线、迭代表格化（迭代/范围/前置依赖/产出物）、按迭代测试策略（marker/edge/隔离/patch 纪律）、迭代级量化验收（每迭代可量化阈值与门禁命令）、外部数据依赖与稳定性考察（数据项/监测指标/降级防护/判定动作）、风险回滚与文档同步义务；终检修正约束代号 321 处全量语义化与 4 份节序跳变（**rf-587** 归档已解决），`check-doc-traces`/`check-doc-links` 全绿；复盘过程记录不入库，文档仅保留最新状态的迭代设计与计划内容

- **CLI/工程**：`cli/cli.py` 910 行按职责拆分（**rf-585** 归档已解决）——按挂账建议拆为 `cli/_parser.py`（argparse 解析器构建与 type 回调，226 行）与 `cli/_handlers.py`（`_handle_*` 子命令处理器 + 持仓读入辅助 + `_EXIT_*` 退出码契约，521 行），`cli.py` 保留 `main()`/`run_cli()` 主流程与命令行功能开关应用并 re-export 全部对外符号（`__all__` 显式声明，`src.python.cli` 包导入与测试 patch 点 `cli.cli._handle_*` 零改动），910 → 243 行；测试 patch 目标随消费方迁移 4 文件（读者辅助 `_cli_read_holdings*`/`_cli_resolve_holdings_file`/`os.path.exists` → `src.python.cli._handlers.*`，含 `test_chain_overrides` 的 `monkeypatch.setattr` 改作用 `_handlers` 模块对象），156 项 CLI/源覆盖测试全绿；`check-file-length.py` EXEMPTIONS 移除 `cli.py`（豁免清空、违规 0 项）；`technical.md` §1.7 与 whatif 模块树、`folders.md` 目录树+统计、`testplan.md`/`test-coverage.md` 载体同步

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
