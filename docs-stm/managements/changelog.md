# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.8.10] - 2026-07-30

### Added
- **注释历史痕迹检查脚本**：新增 `scripts/check-history-traces.py`，扫描 src/ 下所有 .py 文件中的历史变更痕迹（拆分来源叙述、版本号标记、任务编号引用等），15+ 模式分类
- **P1 门禁前置检查**：`test_runner.py verify` 模式增加 `preflight` 机制，运行测试前先执行 `check-history-traces.py --ci`，检测到历史痕迹即中断合入流程
- **rf-72: provider_registry.py 会话缓存提取**：`DataSourceRegistry` 中的会话缓存管理逻辑提取为独立模块 `_session_cache.py`（`SessionCache` 类），provider_registry.py 从 549 行降至约 400 行
- **rf-82: alignment_correction.py 费率估算提取**：组合费率估算逻辑提取为独立子模块 `analysis/_fee_estimation.py`，alignment_correction.py 从 577 行降至约 500 行
- **rf-83: news_aggregator.py 去重逻辑提取**（已在上一轮 rf-47 中完成）：`news_dedup.py` 独立管理标题去重和锚点持久化，news_aggregator.py 降至 236 行
- **rf-84: sina.py K 线函数提取**：历史 K 线获取函数提取为 `providers/sina_kline.py`，sina.py 从 507 行降至约 400 行
- **rf-87: portfolio_history.py 数据质量校验提取**：历史走势数据质量校验（异常检测与收益率诊断）提取为 `report/_history_quality.py`，portfolio_history.py 从 597 降至 513 行
- **rf-65: orchestrator.py 按职责拆分**：1031 行的 `orchestrator.py` 拆分为 3 个子模块——`_report_generation.py`（生成管线）、`_snapshot.py`（快照/历史走势）、`_llm_news.py`（LLM+新闻编排），orchestrator.py 降至 245 行纯编排入口
- **rf-74: skeleton.py 批量模式提取**：批量处理逻辑提取为 `llm/_batch_mode.py`，skeleton.py 从 705 降至 532 行
- **rf-88: html_writer.py 渲染函数提取**：14 个 HTML 子渲染函数提取到 `html_renderers.py`，保存逻辑提取到 `html_save.py`，`write_html_report()` 从 ~275 降至 ~210 行
- **rf-100: test_llm_scenarios.py 拆分**：1202 行大测试文件按 S11-S17 场景分组拆分为 7 个子文件（`test_s11_mixed_cache.py` ~ `test_s17_partial_cache.py` + `test_llm_scenarios_misc.py`），19 个测试全部通过
- **rf-96: test_llm.py 拆分**：2037 行大测试文件拆分为 test_llm_api.py/test_llm_generators.py/test_llm_session.py 3 个子文件
- **rf-97: test_scenario_penetration.py 拆分**：1592 行按场景拆分为 4 个子文件（basic/advanced/mixed/edge）
- **rf-99: test_cache.py 拆分**：1422 行拆出 test_cache_core.py/cleanup/format 3 子模块
- **rf-73: api.py 拆分**：707 行的 `api.py` 拆分为 `_api_claude.py`（Claude）/`_api_openai.py`（OpenAI）/`_api_gemini.py`（Gemini）三个子模块，api.py 降至 521 行

- **rf-131~rf-135: P2D 测试覆盖缺口补充**（5 个新测试文件，96 用例全部通过）：
  - `test_alignment_correction.py`（21 用例）：覆盖口径修正模块 cash_stripping/twr_calculation/compute_alignment_factors
  - `test_drawdown_warning.py`（16 用例）：覆盖滚动最大回撤/历史分位预警/集成等级判断
  - `test_holdings_tracker.py`（14 用例）：覆盖持仓指纹 MD5 计算/代码提取/缓存刷新
  - `test_llm_fallback.py`（17 用例）：覆盖占位文本获取/全部失败检测/降级内容构建
  - `test_rf135_coverage.py`（28 用例）：覆盖 IndicatorBreaker/原子文件 IO/_fmt_wan 格式化/管线辅助函数/B 系列写入入口

### Fixed
- **P2B 魔数/硬编码修复（rf-90 ~ rf-95 共 6 项）**：
  - rf-90: `report/penetration.py` `_SECTOR_KEYWORDS` ~330 行硬编码 → 迁出至 `data/knowledge/sector_keywords.json`，`_load_sector_keywords()` 加载
  - rf-91: `fetcher/bond_yield.py` `df.columns[3]` → 改为列名匹配 `"中国国债收益率10年"`（随 C6 修复 rf-12 一并完成）
  - rf-92: `market_hours.py` 时区硬编码 → 提取为模块级常量 `_BJ_TZ`
  - rf-93: `providers/sina.py`/`tencent.py` K 线超时硬编码 → 提取为模块级常量 `_KLINE_TIMEOUT`
  - rf-94: `report/fund_performance.py` 超额阈值硬编码 → 改为 `config.json` 可配置（`performance_evaluation.excess_threshold_up/down`），`_config_defaults.py` 新增对应配置段
  - rf-95: `fetcher/fund.py` `_BUILTIN_BENCHMARKS` 13 条硬编码 → 迁出至 `data/knowledge/fund_benchmarks.json`，`_load_builtin_benchmarks()` 加载

- **P2F LLM 模块技术债修复（rf-119 ~ rf-130 共 12 项，不含 rf-118）**：
  - rf-119: `generators.py` 影子导入 — 移除 `generate_debate_procon()` 内部重复导入
  - rf-120: `prompts_action.py` 重复 `logger` 定义 — 删除重复行
  - rf-121: `prompts_tables.py` 未使用导入 — 移除 `is_a_share_code`、`is_hk_stock_code`
  - rf-122: `prompts_core.py` 未使用导入 — 移除 `datetime`、`timedelta`、`timezone`
  - rf-123: `prompts.py` `__all__` 缺失 — 补充 `_build_qa_concentration_block`
  - rf-124: `api.py` 空白内容重试逻辑重复 — 提取共享 `_calm_retry()` 函数
  - rf-125: `prompts_action.py` TOP3 代码重复 — 复用 `_build_top3_block()`
  - rf-126: `api.py` thinking budget 计算重复 — 提取共享 `_resolve_thinking_budget()` 函数
  - rf-127: `fact_checker.py` 贡献度关键词检查重复 — 提取 `_is_contribution_sentence()`
  - rf-128: `generators_orchestrator.py` 硬编码 HTTP 连接池参数 → 模块级常量 `_LLM_MAX_CONNECTIONS`、`_LLM_MAX_KEEPALIVE`
  - rf-129: `skeleton.py` 硬编码 `BATCH_SIZE`/`max_workers` → 模块级常量 `_BATCH_CHUNK_SIZE`、`_BATCH_MAX_WORKERS`
  - rf-130: `api.py` 硬编码默认模型名 → 模块级常量 `_DEFAULT_CLAUDE_MODEL`、`_DEFAULT_OPENAI_MODEL`、`_DEFAULT_GEMINI_MODEL`

- **P1A 架构约束违反修复（rf-17/19 — 2 项，补全前序修复）**：
  - rf-17: `fetcher/price.py/industry.py/fund_manager.py` 添加 `session_cache_get/set` 会话缓存层，消除双管线场景下同一资产重复读取文件缓存
  - rf-19: `provider_registry.py` 模块级全局变量（`_phase_timer`/`_phase_expired`/`_phase_timeout_lock`/`_phase_timer_name`）封装为 `_PhaseTimeoutState` 实例，使用 `contextvars.ContextVar` 管理

- **P1D 函数过长批量拆分（rf-36 ~ rf-50 共 15 项）**：
  - rf-36/rf-46: `orchestrator.py` `_generate_report_full`(~272→~85 行) 拆出 `_prepare_full_risk_metrics`/`_generate_full_html_report`/`_generate_full_excel_report`；`_fetch_llm_and_news`(~126→~64 行) 拆出 `_submit_llm_future`/`_submit_news_future`/`_collect_llm_future_result`/`_collect_news_future_result`
  - rf-37: `portfolio_history.py` `get_combined_timeseries`(~232→~112 行) 拆出 7 个子函数
  - rf-38: `fund_manager.py` `parse_manager_from_html`(~139→~35 行) 拆出 4 个子函数
  - rf-39/42/45: `rebalance.py` 拆出 5 个子函数
  - rf-40: `alignment_correction.py` 现金识别+剥离+费率估算拆分
  - rf-41: `scenario.py` `scenario_analysis`(~123→~61 行) 拆出 `_build_scenario_entry`
  - rf-43: `price.py` `fetch_market_data`(~97→~25 行) 拆出 3 个子函数
  - rf-44: `fund_style_classify.py` `classify_fund_style`(~116→~30 行) 拆出 3 个子函数
  - rf-48: `fact_checker.py` `check_numerical_consistency`(~142→~45 行) 拆出 `_evaluate_percent_value`
  - rf-49: `skeleton.py` `generate_llm_content`(~118→~40 行) 拆出 2 个子函数
  - rf-50: `generators_orchestrator.py` `generate_all_llm`(~166→~80 行) 拆出 3 个预检子函数

- **P3 批量修复（rf-108 ~ rf-117 共 10 项）**：
  - rf-108: `providers/__init__.py` 补充 `__all__`（21 个子模块）
  - rf-109: `fetcher/industry.py` 删除冗余 `_is_a_share_code()` 包装
  - rf-111: `config/_config_defaults.py` 字符串拼接改为 `_build_template_from_defaults()` dict-driven 生成
  - rf-112: `config/_llm_defaults.py` 同上
  - rf-113: `registry.py` `enumerate + pop` 改为 `remove + append`
  - rf-114: `code_utils.py` 删除未使用的 `import logging` 和 `logger`
  - rf-115: `provider_registry.py:is_chain_broken()` 未注册 provider 视为不可用（`continue` 跳过）
  - rf-116: `eastmoney_news.py` 新增 `prev_sort_end` 游标去重守卫
  - rf-117: `tui_handlers.py` `_busy` 标志位新增 `threading.Lock()` 保护
  - rf-118: `generators_orchestrator.py` `_MODULE_FNS` 提升为模块级 `_build_module_fns()` 工厂函数

- **P1A 架构约束违反修复（rf-15 ~ rf-22 共 6 项，不含 rf-17/19 待定）**：
  - rf-15: `alignment_correction.py:_classify_fund_type()` 硬编码代码类型判定 → 改用 `code_utils.is_a_share_code()`/`is_hk_stock_code()`
  - rf-16: `news_aggregator.py` 锚点文件 `data/cache/dedup_anchors.jsonl` → 迁出到 `data/calibration/`
  - rf-18: `registry.py` 辩论模块 `DataModuleDef` 缺 `settings_suffix` → 补充 `debate_pro`/`debate_con`/`debate_synthesis`
  - rf-20: `handlers_check_sources.py:_colored()` 缺 `NO_COLOR`/`isatty` 检查 → 新增 `_use_ansi()` 统一判断（含 rf-110 移重复 `import sys`）
  - rf-21: `orchestrator.py` 直接赋值 `pipeline_data["risk_metrics"]` → 在 Schema 中注册 `risk_metrics`/`portfolio_daily_returns`
  - rf-22: `pipeline_data_builder.py` 静默注册未知键 → 未注册键先 `logger.warning` 再注册

- **P1B 裸异常修复（rf-23 ~ rf-30 共 8 项）**：
  - rf-23: `config/_core.py` `_get_llm_providers_path()`/`_get_llm_key_path()` → 缩小异常范围
  - rf-24: `reader.py:get_xlsx_info()` → 缩小为 `(FileNotFoundError, BadZipFile, InvalidFileException, OSError)`
  - rf-25: `circuit_breaker_wrapper.py:_log_ff_event()`/`record_failure()` → 添加 `logger.debug`
  - rf-26: `metrics.py:get_dividend_yield` → 提升日志级别到 `logger.warning`
  - rf-27: `llm/api.py:_resolve_first_provider_model_endpoint` → 添加 `logger.debug`
  - rf-28: `llm/skeleton.py` 两处 `except Exception: pass` → 添加 `logger.debug`
  - rf-29: `news_aggregator.py:_flush_anchors()` `except OSError: pass` → `logger.warning`
  - rf-30: `akshare_extras.py` 指纹/分红摘要 → 缩小异常范围

- **P1C 死代码清理（rf-31 ~ rf-35 共 5 项）**：
  - rf-31: 删除 `tui_handlers.py:check_network_available()`
  - rf-32: 删除 `_config_defaults.py:_PATH_KEYS`
  - rf-33: 删除 `html_jinja_env.py:_jinja_section_visible()`
  - rf-34: 删除 `akshare_extras.py:_SECTOR_FLOW_FAILURE` 及相关赋值
  - rf-35: 删除 `akshare_news.py:_MAX_CCTV`

- **P1E 重复代码修复（rf-51 ~ rf-60 共 10 项）**：
  - rf-51: 辩论模式检测逻辑 → 提取到 `data_status.py` 共享函数
  - rf-52: 原子写入模式 → 提取 `_atomic_write()` 工具函数
  - rf-53: `_ts_to_str()` 三模块重复 → 统一到 `providers/_utils.py`
  - rf-54: `_safe_float()` 两处实现 → 统一到 `providers/_utils.py`
  - rf-55~57: handlers 三个模块命令模式 → 提取通用辅助函数
  - rf-58: 截断重试逻辑 → `_execute_and_merge_batch` 复用 `_handle_truncation`
  - rf-59: 缓存命中处理 → 统一处理逻辑
  - rf-60: `sina.py` 三处 `_pf()` → 提取为模块级私有函数

- **P1F 线程安全问题修复（rf-61 ~ rf-64 共 4 项）**：
  - rf-61: `news_aggregator.py:_last_src_results` → 新增 `_src_results_lock` 保护
  - rf-62: `news_aggregator.py:_ANCHOR_RECORDS` → 新增 `_ANCHOR_LOCK` + `_record_anchor()` 线程安全追加
  - rf-63: `provider_registry.py:fetch_cached_only()` → `data = dict(data)` 复制再修改
  - rf-64: `features.py:FEATURE_FLAGS` → 新增 `_FEATURES_LOCK` 保护所有写操作

- **P2D 测试质量修复（rf-101 ~ rf-105 共 5 项）**：
  - rf-101: `test_integration.py` S4 死测试 — 修正 `fetch_market_data` mock 路径 + 补充 `is_market_open` mock，移除 `@unittest.skip`，清除重复 setUp 代码
  - rf-102: `conftest.py` `_isolate_sensitive_paths` 补充 LLM 配置文件路径隔离（`llm_key.json`、`llm_providers.json`、`llm_settings.json`）
  - rf-103: `test_config.py` 硬编码路径 → 改用 `get_llm_settings_path()`
  - rf-104: `test_integration.py` 硬编码 `cache_dir = 'data/cache'` → 改用 `get_cache_dir()`
  - rf-105: `test_datetime_scenarios.py` 测试重复 — `TestGetTtlMarketAware`（12 个测试）和 `TestClassifyHoldings`（12 个测试）参数化重构，代码减少 ~60%，覆盖不变（41 pt ✅）

- **P0 技术债批量修复（rf-6 ~ rf-14 共 9 项）**：
  - C3 原子写入（3 项）：`provider_registry._save_state()`、`features.save_feature_overrides()`、`handlers_config._write_llm_settings()` 全部改用 `tempfile.mkstemp + os.replace` 模式
  - C18 凭据分离（2 项）：`_parse_providers_list()` 内联 api_key 改为强制 credentials_ref 并输出 WARNING，移除 `get_llm_config()` 中 `llm_settings.json` api_key 回退路径
  - C16 路径安全（1 项）：`_PATH_CONFIG_KEYS` 补上 `llm_providers_file`
  - C6 Chain 约束（1 项）：`bond_yield.py` 集成 akshare 熔断检查，`df.columns[3]` 改为列名匹配
  - 封装破坏（1 项）：新增 `config._core.invalidate_config_cache()` / `invalidate_llm_config_cache()` 公共 API
  - 死测试（1 项）：删除 4 个 `@pytest.mark.skip` 骨架占位文件

- **rf-107 排查关闭**：确认 `simple_rebalance.compute_simple_rebalance_signals` 与 `rebalance.compute_rebalance_signals` 函数名已区分，无命名冲突；`simple_rebalance` 仍被 `prompts_core.py` 用于无配置依赖的轻量再平衡场景，非废弃代码，保持现状

—

## 归档

- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.9（2026-07-21 ~ 2026-07-29）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

