# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Added

- **F 迭代：F1 快照对比**：每次报告生成时自动创建持仓快照，与上一次快照对比输出环比差异摘要（总市值/盈亏变化、新增/清仓/增持/减持 TOP5），写入 Excel summary 页签底部（`history_snapshot.py` + `history_diff.py`）。
- **F 迭代：F2 历史走势**：as-if 模拟（当前持仓 × 历史价格/净值），Chart.js 折线图显示组合市值走势 + 回撤面积图，附累计收益率、最大回撤、年化波动率等指标（`portfolio_history.py`、HTML template 模块 17/18）。
- **新的报告章节 #17 组合历史走势**（`type="history"`，始终可见，数据不可用时占位）。
- **新的报告章节 #18 回撤分析**（`type="history"`，始终可见，数据不可用时占位）。
- **`history.analysis` 配置项**：三种模式 `"off"`（默认）/ `"prompt"` / `"auto"`，控制 F2 走势获取行为。
- **Charts.js CDN 加载**：jsDelivr + unpkg 双 CDN fallback，折线图 + 面积图展示。
- **5 条数据状态消息**：`history_price_unavailable`、`history_nav_unavailable`、`history_degraded`、`history_correction`、`history_zero_value`。
- **注册表扩展**：`portfolio_history`（17, type=history）和 `drawdown_analysis`（18, type=history）注册到 `_REPORT_SECTION_DEFAULT` 和 `_REPORT_SHEET_NAMES`；`history_stock`（CACHE_WEEKLY）和 `history_fund_otc`（CACHE_MONTHLY）注册到 `_MODULE_REGISTRY`。

### Fixed

- **`_cmd_generate_both()` 缺少 F1+F2 数据获取**（HIGH）：菜单 B 全系列报告中完全缺少快照对比和历史走势数据的获取与传递逻辑，导致生成的 Excel/HTML 报告无环比摘要和历史走势章节。已补充 ~80 行 F1 快照创建/对比/保存 + F2 走势获取/注入逻辑。
- **`_BOND_FUND_KEYWORDS` 过宽**（HIGH）：原关键词含"易方达""广发""招商""博时"等基金公司名称，导致非债券基金被错误路由到 OTC 净值链路。已将关键词限定为债券品种：纯债、短债、中短债、利率债、信用债、债券。
- **`id(series)` 作为字典键**（HIGH）：`id()` 返回的内存地址可被回收重用，用作 dict key 会导致数据错乱。已移除整段未使用的 `date_close_map` 死代码。
- **`_cmd_generate_full()` 不可达代码**（MEDIUM）：`if _diff.is_first_check:` 分支位于外层 `if not _diff.is_first_check:` 块内，条件恒为 False。已移除。
- **CACHE_ONLY 盘后无缓存时全量丢失行情**（CRITICAL）：非交易时段 `_generate_details()` 对非 QDII 资产使用 CACHE_ONLY 策略，`fetch_cached_only()` 找不到缓存文件直接返回 None，11/15 个资产显示"暂无行情"。已增加缓存未命中检测，自动降级到 LIVE_FETCH 实时获取。

### Docs

- **how-to-test-my-code.md / test-coverage.md**：同步各模式实际运行时间（regression ~6min / verify ~8min / all ~10min），修正多处不一致的耗时描述。scenario 项数修正为 269 项。
- **config.json**：同步 F 迭代新增配置项（`cache_ttl.history_stock`、`cache_ttl.history_fund_otc`、`history.analysis`）。
- **requirements.md**：页签对照表扩展至 18 项（新增 #17 组合历史走势、#18 回撤分析），配置表新增 `history.analysis`，计数更新（16→18）。同步修正 cache_ttl 计数（21→23）、独立缓存列表补 history_stock/fund_otc、TTL 子表增加历史走势类、数据源表补历史数据行、F 系列页签脚注、F 迭代降级场景、default_menu_key 描述、F 系列 Excel 占位说明共 8 项。
- **technical.md**：报告管线增加 F 迭代数据流，fetcher 表增加 `portoflio_history.py`，缓存设计更新（21→23 类型 + 独立缓存说明），注册表增加 `history` 可见性类型，C7 约束更新为 18 模块。修正页签引用编号 6 处（16→18）。
- **how-to-config.md**：Config JSON 样本增加 F 节 + `history.analysis` 字段，报告模块表扩展至 18 项，新增 §F 历史走势配置章节，无分组模块增加 history 缓存类型。Cache TTL 子表增加历史走势类（history_stock/history_fund_otc）。
- **reports-instruction.md**：页签对照表补充 #16 组合历史走势、#17 回撤分析；LLM API 用量章节编号修正 6 处（16→18）、页签名（16→18）、最多模块数（16→18）。
- **how-to-use-registry.md**：模块计数修正（16→18）；键名对照表补齐全部 18 个模块；分组注册表增加历史走势类条目；补充 F 迭代描述段；编号修正（第 16 号→第 18 号）。
- **faq.md**：编号修正 3 处：默认顺序（16 项→18 项）、页签范围（1~16→1~18）、全量（1~16→1~18）。
- **F 迭代设计文件归档**：`plan/F-portfolio-history-comparison.md` → `archive/`。
- **plan.md**：F 迭代从待实现方向移除，加入已完成迭代列表。
- **how-to-start.md**：菜单 B/L 描述补充 F1 快照对比和 F2 历史走势（视 history.analysis 配置）信息。
- **how-to-config-llm.md**：LLM API 用量页码编号修正（16→18），与注册表最新编号保持一致。

## [0.4.0] - 2026-07-12

### Fixed

- **price_stock 测试 mock 未同步 v0.3.8 链路拆分（延续）**：本迭代进一步发现同类问题，修复 `test_api_edge.py`（3 项 fallback 链测试 + 1 项异常降级测试）和 `test_fetcher.py`（1 项名称不匹配测试）仍 mock `eastmoney` 为 fallback provider，但 v0.3.8 已将 `price_stock` 链改为 `tencent→sina`。统一替换为 `sina` mock，返回字段同步适配 `_price_transform_sina`（`nav`/`nav_date` → `price`/`price_date`）。

### Docs

- **datasource-and-folders.md 目录树核对**：补充 `unit/llm/test_prompts.py`（45 项提示词测试）、`unit/report/test_market_value_strategy_edge.py`（8 项策略退化验证）。
- **test-coverage.md 文件计数同步**：`unit/report/` 41→40 文件、`unit/llm/` 20→19 文件。

> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.3.x.md](../archive/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）共 8 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.2.x.md](../archive/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
