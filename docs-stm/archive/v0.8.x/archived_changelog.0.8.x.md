# 变更日志归档 — v0.8.x

> 归档时间：2026-07-30
> 原始文件：`docs-stm/managements/changelog.md`
> 涵盖版本：v0.8.0 ~ v0.8.10（2026-07-21 ~ 2026-07-30）

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

---

## [0.8.9] - 2026-07-29

### Changed
- **辩论模式配置键重命名（`procon`/`conditional`/`qa_concentration`）**：`llm_settings.json` 的辩论模式配置键从 `mode_1_procon`/`mode_2_conditional`/`mode_3_qa_concentration` 重命名为 `procon`/`conditional`/`qa_concentration`，无向后兼容。代码内变量同步：`raw_m1`→`raw_procon`、`enable_mode_2`→`enable_conditional`、`enable_mode_3`→`enable_qa_concentration` 等。涉及 `_core.py`、`_llm_defaults.py`、`generators.py`、`prompts_action.py`、`prompts_core.py`、`features.py`、`handlers_config.py`、`report/html_writer.py`、`report/excel_generator.py` 及 3 个测试文件
- **需求 ID 去冗余重命名**：`requirements.md` 中 `R-LLM-DB-DEBATE-xx` 全部改为 `R-LLM-DB-PROCON-xx`，消除 DB（Debate）+ DEBATE 语义冗余。`llm-technical.md`、`how-to-config-llm.md` 同步更新
- **辩论模块内部函数提取**：`generators.py` 新增 `_build_feature_suffix()`（确定性缓存指纹后缀生成）和 `_compute_industry_concentration()`（穿透资产行业集中度计算），为集中度问答（qa_concentration）模式提供前置数据

### Fixed
- **持仓体检报告 LLM 虚构收益率**：`_build_health_check_prompt()` 缺少持仓排名约束，LLM 猜测"601939 收益率 10.0%/13.0%"虚构数据（实际 1.9%）。修复：新增 `_build_top3_block()` 显式输出按市值降序的 TOP3 排名；`_SYSTEM_HEALTH_CHECK` 顶部新增 ⚠ 数据纪律约束块（明令不得虚构百分比数字），与正反辩论/条件推理系统提示保持一致。涉及 `prompts_action.py`、`prompts_core.py`
- **辩论模块参数名对齐**：`_build_expert_review_prompt()` 参数 `enable_mode_2`/`enable_mode_3` 改为 `enable_conditional`/`enable_qa_concentration`，消除与配置键的命名差异

### Docs
- **目录结构与测试覆盖统计全量刷新**：folders.md（源码 153/40,874、测试 191/59,441、用例 3849、文档 95）、test-coverage.md 项数同步

## [0.8.8] - 2026-07-29

### Changed
- **辩论模式三位一体命名重构（M1→正反辩论，M2→条件推理，M3→集中度问答）**：TUI 菜单显示名、HTML/Excel 报告标签、代码内参数名、管理文档描述全面替换。涉及 `features.py`、`handlers_config.py`、`generators.py`、`prompts_action.py`、`_llm_defaults.py` 及 `test_debate_conditional.py` 等 15 个文件。需求 ID（R-LLM-DB-M[1-3]-xx）、配置键（`mode_1_procon`/`mode_2_conditional`/`mode_3_qa_concentration`）和 Feature Flag 名不变
- **辩论模式组合标识**：HTML 报告页脚和 LLM 用量汇总表新增当前启用的辩论模式组合标识（如"🧪 辩论模式 · 正反辩论+条件推理"），Excel 报告 LLM 用量行同步展示
- **industry.py 批量并行重构**：`batch_fetch_industry_data()` 从自定义 ThreadPoolExecutor + 手动锁 + 逐条重试迁移为统一 BatchDispatcher（`execute_with_cache_check` + `retry_failed`），移除 threading、random、time、as_completed 等 6 项手动导入，保持非 A 股过滤/熔断预检/None 重试语义不变（rf-1 迭代 7）
- **Python 最低版本锁定 ≥3.11**：3.10 已于 2026-10 EOL，CI 中反复出现 3.10 特有的兼容性问题。CI matrix 移除 3.10，pyproject.toml requires-python 同步更新，README.md 新增环境要求章节，faq.md 版本号更新
- **LLM 模块温度调低**：expert_review 0.8→0.3、health_check 0.5→0.1、penetration_deep 0.4→0.1，降低数值幻觉概率，减少事实校验 false positive。`_llm_defaults.py` 模板与 `llm_settings.json` 默认值同步更新，`how-to-config-llm.md` 说明文档同步
- **`history.analysis` 默认值改为 `"auto"`**（原 `"off"`），新用户开箱即用组合历史走势分析与回撤统计。涉及 `_config_defaults.py`、`config.json`、`handlers_report.py`、`how-to-config.md`

### Fixed
- **辩论模式缓存预检导致 M1 被静默跳过**：`_compute_module_cache_info()` 为 orchestrator 预检构建的 expert_review 缓存键不包含 Feature Flag 指纹后缀（`_fp_suffix`），导致存在非辩论模式的缓存结果时 `needs["expert_review"] = False`，辩论路由（_debate_wrapper）不被应用，用户开启 M1+M2 后仅 M2 生效。修复：`generate_all_llm()` 中辩论模式启用时绕过缓存预检，强制走辩论生成路径
- **收益归因贡献占比与收益率混淆导致 LLM 事实校验告警**：`_build_profit_attribution_block()` 使用 `%` 标注贡献占比（品种利润/全品种绝对利润之和），LLM 在持仓体检报告/智囊团深度复盘中误作个股收益率引用。贡献占比改为 `pp`（百分点）后缀，与收益率 `%` 视觉区分。涉及 2 个 LLM 模块、14 条事实校验告警
- **rf-1 技术债清理（4 项）**：① `BatchDispatcher.execute_with_cache_check` 新增 `strict_none` 参数，消除 industry.py None 后检胶水代码 ② 新增 `fetch_fund_rankings_cached` 为 fund 排名添加 session_cache，消除双管线间文件 IO ③ `compute_penetration_top10()` 实现 fund 持仓与已知 A 股行业分类并行预取，重叠 ~5s IO 等待 ④ 拆出 `_apply_industry_data` 纯函数供并行预取复用
- **穿透深度分析 LLM 虚构收益率**：prompt 缺少 `total_profit_rate` 字段（总收益率），LLM 在无数据约束下虚构 ~18% 而非实际 28.6%。`prompts_action.py` prompt 补充总收益率字段
- **辩论模式白脸/黑脸观点相同**：`generate_debate_procon()` 中 pro 和 con 两次调用 `generate_llm_module(module_key="expert_review")` 均未传递 `fingerprint_fn`，导致内部缓存键均为 `llm_expert_review_`（空指纹），con 调用命中 pro 的缓存结果。修复：pro/con/synthesis 各次调用分别传入含角色后缀的 `fingerprint_fn`，确保内部缓存键隔离

### Added
- **数据源可用性矩阵降级明细展示**：矩阵下方新增"降级明细"节，分行列出每个降级的具体数据源及其失败类型。HTML 页面使用橙色边框 `.data-status-warn` 样式区分于已有的"失败明细"；Excel 页签同步输出降级列表。涉及 `data_source_matrix.py`（新增 `degraded_list` 字段）、`report_template.html`、`excel_generator.py`
- **测试覆盖补全（3 组 15 项）**：① `get_rate_limiter.cache_clear()` 单例重建（3 项） ② price.py OTC 三路路由（直通/空名称降级/纯 A 股/ETF，4 项） ③ `build_data_source_matrix()` degraded_list（8 项：纯 degraded/纯 failed/混合/全 ok/多条同类别/全 failed/空事件/格式验证）

### Docs
- **回撤分析占位提示补充配置说明**：`report_template.html` 回撤分析数据暂不可用提示增加 `history.analysis: "auto"` 脚注
- **测试覆盖统计全量刷新**：test-coverage.md 项数更新（all 3849，unit 3478，unit_fetcher 270，unit_report 1070，快照日期 2026-07-29）
- **目录结构同步**：folders.md 修复 test/handlers/ 下误入的 `handlers_check_sources.py` 重复行，补充 source tree fetcher/ 下 `batch.py`、test tree 下 `test_batch.py` 和 `test_cost_tracker.py`、`test_data_source_matrix.py`

## [0.8.7] - 2026-07-27

### Added
- **三层性能基准体系（P3-13）**：① `perf.py` PerfCollector 在 `generate_report()` 三路径（basic/both/full）嵌入轻量计时埋点，每次运行自动记录各阶段耗时到 `data/state/perf_history.jsonl` ② `scripts/perf_report.py` 保留独立基准脚本（mock 外部源）用于精准回归检测 ③ `scripts/perf_view.py` 趋势查看工具读取历史文件输出版本间耗时对比 Markdown 表格。遵循 C3（原子写入）、C8（统一日志）、C14（局部实例非单例）、C16（路径绝对化）约束
- **数据源健康检查自动收集**：每次客户端生成报告时，后台并行运行全量数据源健康检查（HTTP 连通性+延迟），结果存入 `data/state/datasource_health.jsonl` 并注入 DegradationTracker，供数据源可用性矩阵章节（#17）实时展示。`handlers_check_sources.py` 提取 `run_health_checks()` 返回结构化数据，CLI `check-sources` 命令保持不变

### Fixed
- **excel_b_series.py `NameError: _fetch_fund_holdings_cached`**：P2-6（提交 `259e4b4`）将本地私有函数 `_fetch_fund_holdings_cached` 提取到 `fetcher/fund.py` 为公开函数 `fetch_fund_holdings_cached`，删除了本地定义并更新了导入名，但调用点（`_process_b_module` 第 36 行）仍使用旧私有名 `_fetch_fund_holdings_cached`，导致 `enable_b_series=True` 且持有基金时触发 `NameError`，持仓重合度/集中度/风格分析三个模块均回退为占位。修复：导入 `fetch_fund_holdings_cached` 并修正调用名

### Changed
- **代码/测试注释历史迭代痕迹清理（6 轮）**：全面清除源码注释、测试注释/描述、管理文档正文（changelog.md/plan.md/review-findings.md 除外）、用户文档中的所有历史变更痕迹。覆盖模式包括「不再」「向后兼容」「保留供兼容」「已废弃」「原有的」「此前」「曾」「已迁」「已拆分」「已改为」等，累计修复 50+ 处。涉及 8 个源码文件、5 个测试文件、3 份管理文档、3 份用户文档。豁免文件按约定保留历史记录
- **P3-11 问题描述修正**：`review-findings.md` P3-11 从错误描述的"async 异步化"修正为 ThreadPoolExecutor 批量并行方案，对齐 C5/C6/C2/C3/§1.4.5 架构约束
- **迭代计划文件同步**：`plan-engineering.md` 大文件拆分/性能基准段标记为已完成，异步化段重写为 TPE 并行方案并补齐架构约束分析；`plan-documentation.md` ADR 段标记为搁置并记录原因；`perf-three-layer-plan.md` 归档至 `archive/v0.8.x/perf_report/`

### Docs
- `review-findings.md` P3-11 补充架构耦合约束脚注（C5/C6/C2/C3/1.4.2/1.4.5）

## [0.8.6] - 2026-07-27

### Added
- **数据源可用性矩阵**：新增报告章节 #17（always 类型），在 Excel/HTML 报告末尾统一展示所有数据源运行状态（正常/降级/失败），聚合 DegradationTracker 会话事件按类别（行情/基金排名/行业分类/指数等）归总；Excel 页签含颜色标注和失败明细，HTML 表格含状态图标和详情列

### Fixed
- **cost_tracker 全局预算 xdist 竞态**：`_input_budget` 和 `_budget_warned` 为模块级全局变量，xdist 并行时其他测试通过 `patch("src.python.llm.session.get_session_usage")` 污染 worker，导致 `get_budget_status()` 中 `usage.get("input_tokens", 0)` 返回 MagicMock 而非 int，`max(0, input_budget - MagicMock)` 抛出 TypeError。修复：`_auto_reset_cost_tracker` autouse fixture 增加 `reset_session_usage()` 调用，每次测试前同时重置 session 用量 + budget，确保 `get_budget_status()` 读取到干净的 int 数据；修复 4 个失败用例（`test_cost_tracker.py::TestBudgetManagement`）
- **穿透测试 HTTP 请求遗漏 mock**：`_prefetch_manager_data()` 在 `compute_penetration_top10()` 中遍历基金调用 `fetch_fund_manager(code)`（每只基金一次 HTTP 请求），`mock_all_apis` 未 mock 该函数导致穿透性能测试实际发出 10 次网络请求耗时 17s — 在 `test_e2e_perf.py::mock_all_apis` 中补回 `patch("src.python.report.penetration.fetch_fund_manager", return_value=None)`

### Changed
- **`_extract_entity_bigrams()` 英数专名 `_tk:` 加权**：长度 ≥4 的英文专名（Anthropic/Meta/Helios 等）在实体 bigram 中额外插入 `_tk:` 前缀虚拟 bigram，使 `Anthropic+Meta` 等英数专名重叠的跨源标题即使 ratio<0.40 也能通过 bg≥3 候选区合并，无需降低 ratio 阈值

### Docs
- **内部文档序号/组织校对**：全量审核 6 份文档并修复不一致
- **统计数据全量刷新**：folders.md、test-coverage.md

## [0.8.5] - 2026-07-24

### Fixed
- **CI 超时 & 退出码混乱**：增加默认超时到 1200s，CI 全部加 `--no-timeout` 禁用超时，超时退出码改为标准 124

### Changed
- **P0 提交门禁优化**：`regression`（~6min 全场景）改 `dev-verify`（~1min 核心单元+基础场景）
- **verify 模式瘦身**：移除 Phase B 场景测试，仅保留单元测试
- **P2 发布门禁优化**：`all`（3741 测试，~6.5min）改 `verify,regression`（单元+场景，1306 测试，~3min）
- **`src/test/` 目录结构全面重组**：9 个分析计算测试文件从根目录移入 `unit/analysis/` 等

### Docs
- **门禁文档同步**：CLAUDE.md、how-to-test-my-code.md 等
- **目录树全量同步**：folders.md

---

## [0.8.4] - 2026-07-22

### Fixed
- **`metrics.py` 零方差浮点精度（Linux CI）**：改为 `< 1e-15` epsilon 容差
- **`test_fund.py` threading.Lock 类型检查兼容**：改用 `type(threading.Lock())` 动态获取实际类型
- **`fallback.py` 占位文本缺字**：补回"成"字
- **`handlers_config.py` 辩论模式说明缺字**：补全"深度"二字

### Changed
- **`generators_orchestrator.py` 消除硬编码模块标签**：改为调用 `get_llm_module_names()`

### Chore
- **ruff format 全量对齐**：33 个源码文件

## [0.8.3] - 2026-07-22

### Fixed
- **P3-12 CI 测试持续失败**：修复依赖版本锁死、Ruff 格式检查和超时截断
- **辩论模式 HTML 报告编码错误**：Jinja2 模板变量补充 `| safe` 过滤器
- **新闻去重算法优化**：扩展 STOP 集，增加前缀/数字模式过滤

### Changed
- **辩论模式防幻觉增强**：pro/con 系统提示词新增严格约束
- **事实校验器防误报**：新增 `_PROPORTION_KEYWORDS` 策略
- **历史走势基准指数移除标普500(gb_inx)**：Sina/Tencent K-line 均不可用

## [0.8.2] - 2026-07-22

### Fixed
- **新闻去重算法优化**：`_extract_entity_bigrams()` 加入英数 token 提取
- **校准工具错误建议修正**：`calibrate-dedup-threshold.py` 分档分析

### Changed
- **术语统一**：全项目范围将内部架构术语替换为用户友好术语
- **测试隔离增强**：conftest.py 新增 `_auto_reset_feature_flags` fixture

## [0.8.1] - 2026-07-22

### Fixed
- **P3-13**: `llm/generators.py` `_filter_hallucinated_codes` — 英文词误杀修复
- **P2-11b**: `analysis/metrics.py` 新增 `portfolio_beta_analysis()`
- **P3-09b**: `analysis/alignment_correction.py` 实现三项口径修正因子
- **P2-12**: `config/_core.py` 验证函数提取至 `config/_validation.py`

### Changed
- 版本号更新至 v0.8.1
- `check-version-consistency.py` 加入 review-findings.md、llm-technical.md

## [0.8.0] - 2026-07-21

### Changed
- 版本号发布 v0.8.0
- **review-findings.md**：新增 P2 段，记录 Beta 置信区间（P2-11b）和口径修正因子（P3-09b）两项技术债务
