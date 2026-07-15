# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

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

- *（本次无文档变更）*


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


## [0.5.6] - 2026-07-15

### Added

- **组合历史走势 — 基准指数对比（Iter I）**：详见 [v0.5.x 归档](../archive/v0.5.x/archived_changelog.0.5.x.md)

### Docs

- **版本发布**：v0.5.6，完整变更记录已归档至 [archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.6（2026-07-14 ~ 2026-07-15）共 7 个版本。
>
> **v0.4.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.4.x/archived_changelog.0.4.x.md](../archive/v0.4.x/archived_changelog.0.4.x.md)。
> 涵盖 v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）共 5 个版本。
>
> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.3.x/archived_changelog.0.3.x.md](../archive/v0.3.x/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）共 8 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.2.x/archived_changelog.0.2.x.md](../archive/v0.2.x/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/v0.1.x/archived_changelog.0.1.x.md](../archive/v0.1.x/archived_changelog.0.1.x.md)。
