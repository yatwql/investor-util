# 变更日志归档 — v0.5.x

> 归档时间：2026-07-15
> 原始文件：docs-stm/managements/changelog.md
> 涵盖版本：v0.5.0 ~ v0.5.10

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.5.6] - 2026-07-15

### Added

- **组合历史走势 — 基准指数对比（Iter I）**：
  - 新增 `benchmark_indices` 配置项，支持指定最多 3 个基准指数进行走势对比
  - `benchmark.py` — `fetch_benchmarks()` 并行获取指数历史日线（ThreadPoolExecutor）
  - `benchmark.py` — `normalize_benchmarks()` 归一化至 100 基点与组合走势对齐（LOCF 填充 + 起算日对齐）
  - HTML 渲染：`drawSimpleChart()` 多 dataset 版本，组合曲线 + 基准指数虚线叠加，右侧图例 + 鼠标悬停 tooltip
  - HTML 回撤图：叠加基准指数回撤序列（灰色虚线）
  - Excel `portfolio_history` 页签：每基准一列（归一化值 0.00 格式）
  - Excel `drawdown_analysis` 页签：对比指标矩阵（累计收益率/最大回撤/波动率等）
  - `PortfolioHistoryCalculator.__init__` 接受 `benchmark_indices` 参数，完整的 docstring
- **新增测试**：
  - `test_portfolio_history.py` — benchmark 集成测试（fetch_benchmarks 调用/空配置跳过/异常处理）
  - `test_benchmark.py` — normalize_benchmarks 已有 16 项单元测试
  - `test_benchmark_edge.py` — normalize_benchmarks 已有 7 项边缘场景测试

### Fixed

- **P0 配置浅层合并**：`config/_core.py` 嵌套 dict 合并使用 `merged[key] = {**merged[key], **val}`，防止 `benchmark_indices` 默认值被 `history.analysis` 配置覆盖
- **P1 normalize_benchmarks 防御**：增加 `bar.get("date")` 防御性检查，防止 KeyError；每个基准归一化完成后追加成功日志
- **P1 HTML tooltip 事件监听器泄漏**：重绘时移除旧 `mousemove`/`mouseleave` 监听器再注册，通过 `canvas._chartTooltipHandlers` 追踪；tooltip `<div>` 元素复用而非重复创建
- **移除 Chart.js CDN 外部依赖**：`drawSimpleChart()` 使用 Canvas 2D API 原生渲染，不再加载外部 CDN 脚本

### Changed

- `handlers_report.py` — `_cmd_generate_both()` 和 `_cmd_generate_full()` 传递 `history_data` 参数
- `excel_generator.py` — `generate_excel_report()` 接收 `history_data` 参数，写入历史走势/回撤分析页签
- `report_template.html` — `drawSimpleChart()` 改为多 dataset 签名 `(canvasId, datasets, opts)`，保留旧签名向后兼容
- `_defaults.py` — `_DEFAULT_CONFIG` 中添加默认 `history.benchmark_indices`（沪深300 + 标普500）

### Docs

- `technical.md` — 新增 I 迭代技术设计（基准指数对比模块），更新最后更新日期
- `testplan.md` — 新增 S34 场景（基准指数对比）
- `test-coverage.md` — 更新测试项数
- `datasource-and-folders.md` — 新增 benchmark.py 等文件说明
- 管理文档去历史痕迹：`requirements.md`、`technical.md`、`testplan.md`、`plan.md`、`review-findings.md` 移除版本号/更新日期/归档链接，内容仅反映最新状态
- 用户文档去历史痕迹：`datasource-and-folders.md` 移除末尾最后更新行
- `reports-instruction.md` — 补充基准指数叠加对比说明（§16/§17/历史走势分组表/F2 机制）
- `faq.md` — 补充基准指数对比 FAQ（走势图基准曲线来源说明）
- **归档目录重组**：`archive/` 根目录扁平文件按版本迁入 `v0.1.x/~v0.5.x/` 子目录，迭代子目录（如 `data-degradation/`）同步归入对应版本目录；`datasource-and-folders.md` 目录树同步更新；`changelog.md`/`plan.md`/`testplan.md` 归档引用路径更新

## [0.5.5] - 2026-07-14

### Added

- **覆盖阈值可配置**：`config.json` 新增 `history.coverage_threshold`（默认 0.8），控制组合历史走势有效区间起止日的持仓覆盖比例要求。由 `PortfolioHistoryCalculator` 接收，替代硬编码 80%。

### Changed

- **dev-verify / verify 测试范围修正**：`dev-verify`（开发期快速验证）原误包含了全部 unit 子模块（2407 项），远超 `verify`（合入验证，1043 项），与设计意图颠倒。已修正：
  - `dev-verify` 精简为核心单元（core/providers/fetcher）+ 基础场景 → **815 项**（原 2407）
  - `verify` 扩展为核心/配置/新闻/LLM 模块 + 全量场景 → **1775 项**（原 1043）

### Docs

- **test-coverage.md**：同步更新所有测试模式计数——全量 2990 项（-5），单元 2685 项（-5），场景 276 项（+9），report 1013 项（-5），dev-verify 815 项（-1592），verify 1775 项（+732）。其余模式保持不变。
- **datasource-and-folders.md**：`src/python/` 目录树展开至单文件粒度（~80 个文件/目录），每个文件含用途说明。新增「开发者指引」章节。

- **requirements.md**：系统性重构——由扁平 11 节结构重组为"全局→局部、功能需求→非功能需求"两大部分 12 章。新增统一需求标识体系（R-XXXX-NN），功能/非功能分离，移除原文档中混入的技术设计内容（DataSourceRegistry/Provider Chain/指纹算法等）和版本历史痕迹。
- **technical.md**：全面重构——从扁平 ~950 行扩充为层次化 ~2050 行文档，新增 12+ ASCII 架构图流程图、5 层系统架构图、核心数据流图，设计约束从平铺表重组为 6 领域分组（含设计目的/违反后果/适用范围）。移除所有用户文档引用和版本历史痕迹。
- **llm-technical.md**：全面重构——从原始 ~159 行扩充为 ~980 行完整技术设计，含 7 幅 ASCII 架构图/流程图（4 层架构、调用链、标准/批量模式流程等）。移除版本历史痕迹。
- **technical.md 附录**：附录 B/C 的交叉引用锚点同步更新（`§4`→`§5.1`、`§5.5`→`§9.2`）。
- **requirements.md §3.2/§1.2**：E 菜单描述补全历史走势/回撤分析模块（原缺失 2 模块）。
- **requirements.md §8.4**：删除与 §12 内容重复的"配置异常降级"小节。
- **technical.md**：组合历史走势算法章节补充覆盖阈值可配置说明。
- **how-to-config.md**：新增 `coverage_threshold` 配置项说明，累计收益率起算文档同步。
- **how-to-start.md**：精简——聚焦启动方式和持仓格式，菜单详解提取独立成册，改为速览表 + 链接到新文档。
- **how-to-menu.md**：新增菜单操作手册（从 how-to-start.md 提取独立成册）——完整菜单对照表、各菜单详解、键盘操作、缓存管理、生成建议顺序。
- **how-to-config-llm.md**：精简——移除总体架构图、会话统计数据结构、指纹成分表、骨架函数调用链等所有技术实现细节；保留纯配置说明。
- **how-to-config.md**：精简——移除缓存分组工作原理（registry 驱动）、自动 gzip 压缩等技术细节。
- **how-to-use-registry.md**：增强——在新增 LLM 模块检查清单中补充 4 步领域特定步骤（提示词/报告模板/缓存 TTL/用户文档）。
- **datasource-and-folders.md**：精简——目录树从 400+ 行缩减为主层级结构，移除 `__init__.py` 包标记等细节行。
- **reports-instruction.md**：增强——新增「附录：投资产品知识点」，系统解释 QDII、穿透、溢价率、场内 vs 场外、ETF、5 级评级、最大回撤、as-if 模拟、Jaccard 系数等 15+ 个概念。
- **faq.md**：补充 LLM 配置分享、投资概念文档入口指引；更新报告完整性、报告页签顺序问答链接到新菜单手册。
- **README.md**：用户指南入口表改为编号有序排列（按阅读顺序），新增 how-to-menu.md 条目。

## [0.5.4] - 2026-07-14

### Fixed

- **截断后索引偏移导致收益率/诊断取值错误**：`portfolio_history.py` 在 `sorted_dates` 截断后，后续仍使用截断前的 `valid_start_idx` 访问已截断的数组（`bars[valid_start_idx]`、`sorted_dates[valid_start_idx]`），导致取值偏移、收益率计算错误。已修复为 `bars[0]` / `sorted_dates[0]`。
- **`_validate_bars` 双重截断**：`bars[valid_start_idx:]` 在 `bars` 已截断的基础上再次偏移，跳过有效区间头部的数据校验。已修复为直接传入 `bars`。

### Changed

- **C1 合规（代码类型判定中心化）**：`portfolio_history.py` 全面改用 `code_utils` 函数进行资产代码路由：
  - OTC 基金兜底路由：`len(code)==6 and code.isdigit()` → `is_otc_fund_by_name(name, code)`
  - 债券基金路由：`self._is_bond_fund(name)` → `is_bond_fund_by_name(name)`
  - QDII 路由：新增 `is_qdii_extended(name)` 前置判定
  - 港股路由：新增 `is_hk_stock_code(code)` 跳过港股
  - 降级路径中移除 `code.startswith("00")`（`is_otc_fund_by_name` 内部已处理）
- **移除死代码**：`_BOND_FUND_KEYWORDS` 类属性和 `_is_bond_fund()` 方法（路由已通过 `code_utils.is_bond_fund_by_name()` 实现，不再使用）。

### Docs

- **plan.md**：新增 [P3] I. 组合历史走势与基准指数比对功能提议。

## [0.5.3] - 2026-07-14

### Fixed

- **最大回撤显示为正数**：`portfolio_history.py` 中 `drawdown_pct` 存储为正值（如 `+59.51%`），但回撤是亏损应显示为负值。已修复为存储负值，Jinja `change` filter 自动显示 `−59.51%`。
- **累计收益/回撤因尾端数据覆盖不全而异常放大**：历史走势起算点有 ≥80% 覆盖检查，但终止日无等效检查。部分基金数据未延伸到最新日（如 2026-07-14 仅 7/15 只有数据），导致组合市值骤降、收益虚低、回撤虚高。新增 `valid_end_idx` 尾端覆盖检查，与起算点对称处理。

### Changed

- **历史数据重叠自动全量刷新**：`_fetch_with_incremental_fallback()` 检测到新旧数据重叠（如分红除权导致的前复权回溯调整）时不再仅记录 WARNING，而是自动清除污染缓存并重新获取完整历史。用户不再需要手动执行菜单 `[2]` 来修正。
- **OTC 基金全量返回检测**：`fetch_fund_nav_history()` 不支增量、每次全量返回 200 条历史净值，导致全量刷新后新数据仍与旧缓存重叠，无线循环触发。新增判断：新数据起点 ≤ 缓存起点时视为全量返回，直接替换不合并，消除误告警。
- **重叠检测边界修正**：`_validate_continuity()` 使用 `<=` 判定重叠，但腾讯等 API 在 `start_from` 参数传入缓存末日时，返回值恰好包含该日，导致单日边界误判为修正。改为 `<`，仅当新数据首日早于旧数据末日（多天重叠）时才触发全量刷新。

### Docs

- **technical.md**：`_fetch_with_incremental_fallback` 描述同步，标注自动全量刷新行为。

## [0.5.2] - 2026-07-14

### Added

- **`_validate_enable_llm()` 新增**：在 `config/_core.py` 新增 LLM 板块配置校验函数，启动时检查 `llm_settings.json` 中 `enabled_llm` 字典的子键拼写错误。与 `_validate_enable_boards()` 互补，后者仅处理 `config.json` 的三个板块字段。调用链：`validate_config()` → `_validate_enable_llm()`。
- **`get_known_enabled_llm_keys()` 新增**：在 `registry.py` 新增启用 LLM 子键查询函数，返回 `enabled_llm` 字典的所有合法子键。

### Docs

- **technical.md**：`_validate_enable_boards()` 验证描述更新为分两路说明（config.json 三字段 + llm_settings.json 子键拼写）。
- **how-to-use-registry.md**：新增 `enabled_llm` 子键查询章节。

## [0.5.1] - 2026-07-14

### Fixed

- **HTML 报告导航栏序号不连续**：导航栏使用 `sec["number"]`（注册表中的原始编号）而非重新编号后的 `section_numbers`，导致关闭 B 系列/历史走势后导航栏显示原始序号（1,2,3,4,5,10,11...）而章节标题已正确连续编号（1,2,3,4,5,6,7...）。已修复：导航栏改为使用 `section_numbers[sec["key"]]`，与章节标题统一。

- **HTML 报告缺失 LLM 页面**：`write_html_report()` 的 `enable_llm` 参数默认值为 `False`，而 `_cmd_generate_full()`（L 菜单）调用时未传入，导致 HTML 报告中所有 LLM 板块被隐藏且无连续编号。已修复为传递 `is_enable_llm()` 配置值，并同步新增该函数作为统一读取入口。

- **误导日志"实增 N 个"**：`news_correlation.py` 中行业/概念关键词扩展日志使用了"实增"（暗示随时间增长），但实际是持仓关键词（股票名）与行业/概念关键词（行业名、板块名）两个不重叠集合的差值，每次结果相同。已改为"行业/概念 N 个"。

### Changed

- **`is_enable_llm()` 新增**：在 `config/_core.py` 新增 LLM 板块可见性判断函数，读取 `llm_settings.json` 的 `enabled_llm`，仅检测 4 个 LLM 报告模块（global_macro / expert_review / health_check / penetration_deep），不包含 `news_correlation`。缺失时默认启用（向后兼容）。
- **L 菜单 LLM 生成条件化**：`_cmd_generate_full()` 在 `is_enable_llm()` 返回 False 时不再提交 LLM 线程任务。新闻/LLM 组合的 4 种开关状态（双启/仅新闻/仅 LLM/双关）均正确处理。
- **B 菜单显式同步**：`_cmd_generate_both()` 的 Excel 和 HTML 调用均显式传入 `enable_llm=False`，与 B 菜单"不含 LLM"的语义对齐。
- **Provider 熔断器阈值可配置化**：`ProviderState.failure_threshold` 和 `cooldown_secs` 改为 per-instance。`eastmoney_industry` 使用 `failure_threshold=6, cooldown_secs=120`，避免 3 线程并发调用时一次网络抖动即熔断。单股票 API 保持默认 3/300s。

### Docs

- **technical.md**：`is_enable_llm()` 加入 board 层对照表，llm 配置来源说明更新。
- **how-to-config.md**：H 节新增 LLM 可见性配置行，内容只描述当前状态。
- **how-to-config-llm.md**：新增板块可见性与 `enabled_llm` 的关联提示。
- **faq.md**：板块可见性配置项补充 `enabled_llm`，菜单生成范围说明同步。
- **how-to-start.md**：报告内容对照表 B/L 菜单改用 ☆ 标注配置驱动型可见性，新增脚注 ⁵ 说明。
- **reports-instruction.md**：可见性规则表重构为两层模型（board+data），LLM 模块触发条件补充 `enabled_llm` 配置控制。
- **requirements.md**：熔断器/push2/基金风格加速阈值文字同步。
- **testplan.md**：熔断器覆盖要求补充 per-instance 阈值说明。

## [0.5.0] - 2026-07-14

### Changed

- **归档目录重组**：`archive/g-board-visibility-iteration-plan.md` 迁入 `archive/report-board-visibility-configable/` 子目录，保持与其它多文件归档一致的目录结构。
- **`should_create_sheet()` 重构（Option A）**：去掉硬编码 type_map 和 board/data 混层参数，改为直接查询注册表中每个 section 的 `data_flag` 字段。`should_create_sheet(section, data_availability)` 成为纯 data 层函数，新增模块只需在 registry 填对 `data_flag` 即可零改动。
- **`create_sheets()` 签名简化**：移除 `news_data_available`/`llm_data_available` 两个 data 层参数，统一为 `data_availability: dict[str, bool]` 字典传入。
- **`set_sheet_title()` 移除**：生产代码中已无消费者（`create_sheets` 改用内联连续重新编号），删除 ~25 行死代码。
- **TUI 菜单 B/L 描述更新**：不再硬写`[含基金深度分析]`，改为`[按板块配置]`；L 菜单突出`[含LLM]`为核心差异。

### Docs

- **datasource-and-folders.md**：目录树中 `g-board-visibility-iteration-plan.md` 单文件引用更新为 `report-board-visibility-configable/` 目录+子文件层级。

## [0.5.7] - 2026-07-15

### Fixed

- **P1-1: generators_orchestrator.py/skeleton.py 直接 httpx.Client()** — 两处直接绕过 `make_http_client()` 导致 LLM 模块 HTTP 请求缺少统一 SSL 验证策略，已全部改为 `make_http_client(timeout=LLM_TIMEOUT, **_LLM_CLIENT_SETTINGS)`
- **P1-2: fund_style_analysis.py 直接调用 Provider 私有函数** — 直接调用 `eastmoney_industry._make_push2_request`、`tencent.fetch_price`、`eastmoney_industry.fetch_industry` 绕过 Provider Chain，已全部移除直接调用
- **P1-3e: tui_handlers.py/tui_menu.py 私有符号跨包导入** — 完成 5 个消费者文件的内部调用点同步（handlers_cache.py、handlers_config.py、handlers_report.py、main.py、tui_handlers.py），修复因 import 已改但调用点未更新导致的潜在 NameError
- **P1-3f: LLM 模块私有符号跨包导入** — 全局重命名 pricing.py（`_CURRENCY_SYMBOLS`→`CURRENCY_SYMBOLS`、`_PRICING_CURRENCY`→`PRICING_CURRENCY`、`_reload_pricing`→`reload_pricing`、`_estimate_cost`→`estimate_cost`）、prompts.py（`_LLM_MODULE_FAILURE`→`LLM_MODULE_FAILURE`、`_CACHE_PREFIX_LLM`→`CACHE_PREFIX_LLM`）、skeleton.py（4 函数去 `_` 前缀）、fingerprint.py（5 函数去 `_` 前缀）、session.py（`_track_session_usage`→`track_session_usage`、`_record_per_module`→`record_per_module`）、api_base.py（`clear_last_llm_failure`、`LLM_TIMEOUT`、`CACHE_LINE_HTML`、`call_llm_with_retry`）、api.py（5 函数去 `_` 前缀）、markdown.py（`_markdown_to_html`→`markdown_to_html`），同步 8 个消费模块的导入与调用点
- **P1-3f 补漏：api_base.py 定义名未同步** — `_call_llm_with_retry`→`call_llm_with_retry`、`_AUTO_INCREASE_FACTOR`→`AUTO_INCREASE_FACTOR`、`_TRUNCATION_MARKER`→`TRUNCATION_MARKER`，三项定义仍带下划线但消费者已按公开名导入，修复 `__all__` 与内部引用
- **P1-3 测试文件未同步** — 7 个测试文件仍导入旧的私有名（`_NOT_FOUND`、`_LLM_MODULE_FAILURE`、`_Timer`、`_timing_records`），运行时引发 `ImportError`。已全部更新为公开名
- **technical.md 残留 `_NOT_FOUND`** — 缓存架构图中仍使用私有名，同步为公开名 `NOT_FOUND`
- **requirements.md 重复 TTL 条目** — R-CCH-25/R-CCH-26 存在两份内容完全相同的条目，删除重复区块
- **Excel 报告组合历史走势页签运行时崩溃** — `excel_generator.py` 在 P1-3d 重命名后遗漏 `write_data_row` 导入导致 `NameError`，已在两个局域 import 块中补充
- **P3-3: provider_registry.py 模块级副作用** — 模块加载时执行 `get_registry().register_default_chains()` 调用已移除（原第 467 行）
- **P3-8: api_base.py 遗留 print 语句** — `print(msg)` 改为 `logger.info("%s", msg)`，对齐项目日志标准
- **P3-10: is_chain_broken 冷却恢复测试缺口** — 补充 `test_is_chain_broken_cooldown` 测试用例，覆盖全链熔断→冷却期满→自动恢复路径
- **P3-11: _validate_user_fund_benchmarks 配置验证缺失** — 增强逐项验证逻辑：对 code/benchmark 校验类型和非空，非 dict 类型时告警并计数
- **P3-12: _core.py 多空白行** — 删除 config/_core.py 中连续三空白行（PEP8 违规）

### Changed

- *（本次无变更）*

### Docs

- **technical.md 函数名引用同步** — `_fetch_with_fallback()`→`fetch_with_fallback()`（6 处）、`_fetch_with_incremental_fallback()`→`fetch_with_incremental_fallback()`（4 处）、`_generate_llm_module`→`generate_llm_module`、`_call_llm()`→`call_llm()`、`_select_holdings_file()`→`select_holdings_file()`
- **拆分 datasource-and-folders.md** — 原文件分解为两个独立文档：`docs-stm/manuals/datasource.md`（用户文档，数据源一览表）和 `docs-stm/managements/folders.md`（管理文档，目录结构树）。同步更新 CLAUDE.md 文档列表和目录树同步指、README.md 链接、testplan.md 引用

## [0.5.8] - 2026-07-15

### Added

- *（本次无新增功能）*

### Fixed

- **P2-1：fund_style_analysis.py 硬编码代码前缀判定** — 在 `code_utils.py` 新增 `estimate_market_cap_by_prefix(code)` 统一规模估算函数，`fund_style_analysis.py` 的 `_estimate_style_by_code()` 改为此函数委派调用
- **P2-2：price.py 硬编码 code.startswith("00")** — 替换为 `code_utils.is_otc_code_overlap(code)`
- **P2-3：penetration.py 硬编码 code.startswith("5")** — 替换为 `code_utils.is_exchange_fund_code(code)`，覆盖 1 开头深市 ETF
- **P2-4：DegradationTracker 状态文件路径** — 从 `data/cache/.degradation_state.json` 移至 `data/state/.degradation_state.json`，避免 cache.cleanup_expired() 误清理
- **P2-5：news_correlation 注册到 _MODULE_FNS** — `generators_orchestrator.py` 新增 `run_news_correlation_safe()` 安全调用封装，统一缓存/失败处理/日志模式；`_dispatch_llm_workers` 支持可选集成 news_correlation 线程池执行；`news_correlation.py` 改用安全封装
- **P2-6：重复 _fetch_fund_holdings_cached 函数** — 提取到 `fetcher/fund.py` 的 `fetch_fund_holdings_cached()`，`html_renderers.py` 和 `excel_b_series.py` 改用共享函数
- **P2-7：重复 LLM 模块信息构建** — 新建 `report/llm_module_info.py`，提供共享 `build_llm_module_info()` 函数，`html_renderers.py` 和 `excel_llm_usage.py` 改用共享函数
- **P2-8：清理 7 处死导入** — `handlers_config.py`（sys）、`cache/_io.py`（Any）、`cache/_ttl.py`（Any）、`html_renderers.py`（datetime）、`akshare_extras.py`（as_completed）、`schemas/history.py`（field）
- **P2-9：移除 FetchStrategy.PLACEHOLDER** — 枚举值从未被返回，移除减少概念死分支
- **P2-10：创建 fetcher/akshare.py 封装层** — 统一封装 `providers/akshare_extras` 的 4 个公开函数，report 层 9 处导入改为 `fetcher.akshare`
- **P3-1：fund_style_analysis.py 模块级副作用** — 移除模块加载时 `get_registry().register_provider("tencent_style")` 调用，改为 `_ensure_tencent_provider_registered()` 惰性函数，首次调用 `classify_fund_style` 时注册

### Changed

- **P3-7：颜色常量独立为共享模块** — 创建 `ansi_colors.py`，`report/progress.py` 改为从此导入而非 `tui_menu`，消除 report 层对 UI 层的依赖

### Docs

- **technical.md 残留 `_` 前缀引用同步** — `_TRUNCATION_MARKER`→`TRUNCATION_MARKER`、`_session_usage`→`session_usage`、degradation 状态文件路径更新、附录 B 数据源标注更新、目录树同步
- **folders.md 目录树同步** — 新增 `fetcher/akshare.py`、`report/llm_module_info.py`、`report/benchmark.py`、`ansi_colors.py` 及 `data/state/`

## [0.5.9] - 2026-07-15

### Docs

- **changelog 归档**：v0.5.6/0.5.7/0.5.8 详细记录迁移至 `archived_changelog.0.5.x.md`，changelog.md 仅保留归档引用链接
- **review-findings 归档**：已修复 P3 问题（P3-1/P3-3/P3-7/P3-8/P3-10/P3-11/P3-12）剥离至 `archived_review-findings.0.5.x.md`

## [0.5.10] - 2026-07-15

### Fixed

- **handlers_cache 缺失 import os**：`_cmd_show_cache_stats` 中使用 `os.path.join` 但模块未导入 `os`（P2-7 拆分解耦遗留）
- **skeleton.py `_generate_llm_content` 内部调用残留**：`_run_standard_mode` 仍调用旧私有名，导致 penetration_deep 模块 RuntimeError
- **handlers_config.py 函数名错写**：`_cmdrefresh_config` → `_cmd_refresh_config`（少一个 `_`，保持 `_cmd_` 命名一致）
- **`_call_llm` → `call_llm` 引用残留**：test_api.py 8 处 + test_log_sanitize.py import/调用
- **`_call_llm_with_retry` → `call_llm_with_retry` 引用残留**：test_log_sanitize.py import-as
- **`history_index` 缺少 cache_groups 豁免**：test_registry.py `known_ungrouped` 未包含 `history_index`
- **P1-3f 重命名残留全量清理**（17 测试文件 + 2 源码文件，共 100+ 处）：
  - `_build_module_info_list` → `build_llm_module_info`（位置迁移至 `llm_module_info.py`）：测试 import/调用 10+ 处
  - `_generate_llm_content` → `generate_llm_content`：mock 目标 7 处 + `_run_standard_mode` 内部调用 1 处
  - `_fetch_with_fallback` → `fetch_with_fallback`（`chain.py` 公开函数）：mock 目标 9 处
  - `_fetch_with_incremental_fallback` → `fetch_with_incremental_fallback`（`chain.py`）：mock 目标 19 处
  - `_call_openai` → `call_openai`、`_call_single_provider` → `call_single_provider`：mock 目标 13 处
  - `_call_llm_with_retry` → `call_llm_with_retry`（移入 `api_base.py`）：mock 目标 1 处
  - `_press_any_key` / `_refresh_config`（import 自 `tui_menu.py`）：mock 目标 10 处

### Changed

- *（本次无变更）*

### Docs

- **test-coverage.md**：同步更新测试计数（all 2990→3073, verify 1775→1832 等）
- **changelog.md**：记录本次全部修复明细
