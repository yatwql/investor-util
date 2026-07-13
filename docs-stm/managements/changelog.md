# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Fixed

- **HTML 章节 18（LLM API 用量）出现在 16/17 之前（HIGH）**：模板源顺序中 llm_usage 的 HTML 代码位于 portfolio_history 和 drawdown_analysis 之前。CSS `order` 在 `overflow-x: auto` + 条件渲染组合下浏览器渲染引擎不总是按 `order` 重排。修复为将 llm_usage 的 HTML 块物理移动到 drawdown_analysis 之后、footer 之前，源顺序与 CSS order 一致。
- **penetration.py 穿透分类中 00 代码误判为 STOCK（LOW）**：`classify_penetration()` 对 00 前缀 OTC 基金（证券账户中的混合基/货币基）从 `is_a_share_code` 路径改为 `is_otc_fund_by_name()` 优先判定，避免被误归类为直接持股。
- **excel_b_series.py 三模块重复获取基金持仓（LOW）**：引入 `_fetch_fund_holdings_cached()` 复用 `registry.session_cache_get/set("fund_hold", code)`，消除持仓重合度/集中度/风格分析三模块各自独立调用 `fetch_fund_holdings` 的冗余。
- **portfolio_history.py 无独立单元测试**：创建 `test_portfolio_history.py`，覆盖代码类型路由、00 代码降级、session_cache、as-if 市值、波动率计算、数据质量校验、债券名称识别共 28 项测试。
- **test_fetcher_price.py 缺 00 代码降级测试**：新增 3 项测试（降级成功、双链路全失败、股票链路成功不降级），覆盖 price.py 的 00 代码 `price_fund_otc` 降级路径。

### Added

- **`code_utils.is_otc_fund_by_name()` 00 代码重叠区分类辅助**：新增 `_OTC_FUND_NAME_KW` 关键词元组（混合/纯债/短债/货币/联接等），和 `is_otc_fund_by_name(name, code)` 函数，名称+代码双维度判断 00 代码是否为场外基金。
- **logger.py 控制台彩色日志**：新增 `_ColoredFormatter`，WARNING 黄色/ERROR 红色高亮，文件日志保持纯文本不受影响。

### Fixed

- **002943 等 00 代码基金无法获取行情（HIGH）**：`fetch_market_data()` 对 `00` 开头且股票链路全失败的代码自动降级到 `price_fund_otc` 链路通过东方财富获取净值。同时 `market_value.py` 和 `category.py` 在代码分类环节借用 `is_otc_fund_by_name()` 优先判定，消除 00 代码被误路由到 A 股链路的根因。
- **00 代码基金历史 K 线全空（HIGH）**：`portfolio_history.py` 对 `is_a_share_code()` 和 `is_exchange_fund_code()` 均不匹配的 00 代码，股票历史全空时自动降级尝试基金净值链路，与行情获取的降级策略保持一致。
- **`except Exception: pass` 空吞异常 2 处（MEDIUM）**：`news_correlation.py` 两处静默吞异常改为 `logger.warning()` 输出详情，避免调试困难。

### Performance

- **组合历史走势多持仓并行获取**：`portfolio_history.py` 的 `calculate_portfolio_history()` 使用 `ThreadPoolExecutor(max_workers=8)` 并行获取每只持仓的历史数据，串行→并行显著缩短大规模持仓的等待时间（用户报告"速度很慢"的数据获取层根因）。
- **指数数据去重请求**：`_render_index_section()` 接受 `pre_fetched_a`/`pre_fetched_us` 可选参数，`write_html_report()` 和 `_cmd_generate_full()` 透传 `_prepare_report_data()` 已获取的指数数据，消除同一流程中指数 HTTP 请求重复调用的浪费（降级日志曾出现同一指数数据降级两次）。

### Changed

- **CDN 链路优化 + 原生 Canvas 即时渲染**：`report_template.html` 重构图表渲染架构——新增 `drawSimpleChart()` 原生 Canvas 2D 函数（无外部依赖、即刻渲染），双图表脚本改为同步原生渲染+后台 Chart.js 升级模式，消除 CDN 白屏等待。CDN 链路首位新增 `bootcdn.net`（国内加速），移除始终超时的 `cdnjs.cloudflare.com`。
  - **v1** 修复 cssText 覆盖导致画布溢出的 Bug（`canvas.style.cssText` → `canvas.clientWidth`）
  - **v2.1** `canvas.clientWidth` 仍可能因父容器被撑宽而溢出 → 追加 `Math.min(..., window.innerWidth - 96)` 硬钳制 + `canvas.style.width = dispW + 'px'` 锁死 CSS 显示宽度 + Chart.js 升级改传 canvas 元素而非 2D 上下文（避免 `ctx.scale(dpr)` 残留）+ `responsive: false` 禁止 Chart.js 篡改尺寸
- **降级日志增强**：`chain.py` 全部 degrade/fallback 日志附加 `_code_tag`（代码+名称），降级时明确标识受影响资产。`price.py` 新增 00 代码降级/成功两阶段日志。
- **`max_tokens_global_macro` 1024→2048**：`_core.py` 提高 LLM 全局宏观提示词的最大 token 数，允许生成更长的宏观分析内容。
- **`progress.py` / `tui_menu.py`**：联动适配，`ProgressReporter` 输出格式微调，`tui_menu` 颜色常量提升为模块级别供 logger.py 引用。

### Docs

- **review-findings.md**：P0(CRITICAL) E1 → 已完成，P1 E2/E3/E4 → 已完成，P2 E5/E6/E7 → 已完成。新增 P3 待处理项（test_fetcher_price 00 degrade 测试、portfolio_history 单元测试、penetration.py 00 分类、excel_b_series session_cache）。
- **technical.md**：同步设计约束 C1 引用（`code_utils.py` 代码类型分类中心化），补充降级链路描述（00 代码降级流程）。
- **requirements.md**：同步 00 代码分类需求、并行获取需求、指数去重需求。
- **datasource-and-folders.md**：目录树补充 `schemas/` 节点。

## [0.4.1] - 2026-07-13

### Added

- **F1 快照对比**：每次报告生成时自动创建持仓快照，与上一次快照对比输出环比差异摘要（总市值/盈亏变化、新增/清仓/增持/减持 TOP5），写入 Excel summary 页签底部（`history_snapshot.py` + `history_diff.py`）。
- **F2 历史走势**：as-if 模拟（当前持仓 × 历史价格/净值），Chart.js 折线图显示组合市值走势 + 回撤面积图，附累计收益率、最大回撤、年化波动率等指标（`portfolio_history.py`、HTML template 模块 17/18）。
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
- **config.json**：同步新增配置项（`cache_ttl.history_stock`、`cache_ttl.history_fund_otc`、`history.analysis`）。
- **requirements.md**：页签对照表扩展至 18 项（新增 #17 组合历史走势、#18 回撤分析），配置表新增 `history.analysis`，计数更新（16→18）。同步修正 cache_ttl 计数（21→23）、独立缓存列表补 history_stock/fund_otc、TTL 子表增加历史走势类、数据源表补历史数据行、历史走势页签脚注、历史走势降级场景、default_menu_key 描述、历史走势 Excel 占位说明共 8 项。
- **technical.md**：报告管线增加历史走势数据流，fetcher 表增加 `portoflio_history.py`，缓存设计更新（21→23 类型 + 独立缓存说明），注册表增加 `history` 可见性类型，C7 约束更新为 18 模块。修正页签引用编号 6 处（16→18）。
- **how-to-config.md**：Config JSON 样本增加 `history` 节 + `history.analysis` 字段，报告模块表扩展至 18 项，新增历史走势配置章节，无分组模块增加 history 缓存类型。Cache TTL 子表增加历史走势类（history_stock/history_fund_otc）。
- **reports-instruction.md**：页签对照表补充 #16 组合历史走势、#17 回撤分析；LLM API 用量章节编号修正 6 处（16→18）、页签名（16→18）、最多模块数（16→18）。
- **how-to-use-registry.md**：模块计数修正（16→18）；键名对照表补齐全部 18 个模块；分组注册表增加历史走势类条目；补充历史走势描述段；编号修正（第 16 号→第 18 号）。
- **faq.md**：编号修正 3 处：默认顺序（16 项→18 项）、页签范围（1~16→1~18）、全量（1~16→1~18）。
- **历史走势设计文件归档**：`plan/F-portfolio-history-comparison.md` → `archive/`。
- **plan.md**：历史走势从待实现方向移除，加入已完成列表。
- **how-to-start.md**：菜单 B/L 描述补充 F1 快照对比和 F2 历史走势（视 history.analysis 配置）信息。
- **how-to-config-llm.md**：LLM API 用量页码编号修正（16→18），与注册表最新编号保持一致。
- **docs 迭代标签清理（全局）**：所有活跃管理文档和用户文档正文中的历史迭代名称（"B 迭代""C 迭代""D 迭代""F 迭代"）及版本号标记移除或替换为功能描述。源代码注释 18 处"F 迭代"/"组合历史对比分析"统一为"组合历史走势"。
- **用词统一**：全库 "组合历史对比分析" → "组合历史走势"（how-to-config.md、datasource-and-folders.md 及源代码注释同步）。
- **归档文件迁移**：`archive/F-portfolio-history-comparison.md` → `archive/portfolio-history-comparison/` 子目录，文件名保持不变。

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
