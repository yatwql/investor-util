# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.8.10-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C19）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P1 - 代码质量（中优先级，建议近期修复）

#### P1A — 架构约束违反

| # | 分类 | 问题 | 风险点 | 修改收益 |
|---|------|------|--------|---------|
| **rf-17** | **C4 违反** - `fetcher/price.py:fetch_market_data()`、`fetcher/industry.py:fetch_industry_data()`、`fetcher/fund_manager.py:fetch_fund_manager()` 缺少 `DataSourceRegistry.session_cache` 会话缓存 | 双管线（HTML+Excel）场景下同一资产重复读取文件缓存，增加 I/O 延迟 | 添加 `registry.session_cache_get/set` 包装层，与 `fund.py` 的 `*_cached` 模式对齐 |
| **rf-19** | **C14 违反** - `provider_registry.py` 第 629-632 行四个模块级全局变量（`_phase_timer`/`_phase_expired`/`_phase_timeout_lock`/`_phase_timer_name`）通过 `global` 关键字修改 | 测试隔离困难，不支持嵌套调用（当前虽已检测嵌套并抛 RuntimeError，但全局状态设计本身就是 C14 禁止的模式） | 封装到实例级或使用 `contextvars.ContextVar` |

#### P1D — 函数过长（>100 行）

| # | 函数 | 文件 | 行数 | 风险点 |
|---|------|------|------|--------|
| **rf-36** | `_generate_report_full()` | `report/orchestrator.py` | ~272 | 混合数据准备、快照、历史走势、LLM/新闻、双管线生成，圈复杂度极高 |
| **rf-37** | `get_combined_timeseries()` | `report/portfolio_history.py` | ~228 | LOCF 合并+有效区间截断+回撤+收益率+波动率+基准对比 6 步算法揉合 |
| **rf-38** | `parse_manager_from_html()` | `fetcher/fund_manager.py` | ~138 | 3 种解析策略（infoOfFund 表格、全文搜索、移动端）+ 2 种子格式 + 任职天数计算 |
| **rf-39** | `compute_target_deviation()` | `analysis/rebalance.py` | ~147 | 目标偏离计算逻辑过多层嵌套 |
| **rf-40** | `cash_stripping()` | `analysis/alignment_correction.py` | ~124 | 现金识别+剥离+费率估算揉合 |
| **rf-41** | `scenario_analysis()` | `analysis/scenario.py` | ~123 | 情景分析多路径分支 |
| **rf-42** | `equity_fixed_income_deviation()` | `analysis/rebalance.py` | ~118 | 权益固收偏离计算 |
| **rf-43** | `fetch_market_data()` | `fetcher/price.py` | ~97 | 代码类型路由+validate 闭包+`_fetch_with_cache_refresh` 内部函数+00代码降级+跨日刷新重试 |
| **rf-44** | `classify_fund_style()` | `report/fund_style_classify.py` | ~116 | 风格分类逻辑过长 |
| **rf-45** | `compute_rebalance_signals()` | `analysis/rebalance.py` | ~112 | 再平衡信号计算 |
| **rf-46** | `_fetch_llm_and_news()` | `report/orchestrator.py` | ~126 | LLM+新闻并行编排 |
| **rf-47** | `_dedup_by_title()` | `providers/news_aggregator.py` | ~181 | 标题标准化+bigram 提取+三档阈值去重+锚点采集，6 种子逻辑混合 |
| **rf-48** | `check_numerical_consistency()` | `llm/fact_checker.py` | ~142 | 事实校验过长 |
| **rf-49** | `generate_llm_content()` | `llm/skeleton.py` | ~120 | LLM 骨架生成函数 |
| **rf-50** | `generate_all_llm()` | `llm/generators_orchestrator.py` | ~166 | LLM 编排总入口 |

#### P1F — 线程安全问题

（暂无可报告项）


### P2 - 代码质量（低优先级，增量改进）

#### P2A — 文件过长（>500 行，建议拆分）

| # | 文件 | 行数 | 拆分建议 |
|---|------|------|----------|
| **rf-65** | `report/orchestrator.py` | 1031 | 数据准备 / 快照 / 历史走势 / LLM新闻 / 管线生成 5 职责 |
| **rf-66** | `analysis/metrics.py` | 990 | 辅助数学函数（Beta/t-分布）拆出到 `_math_utils.py` |
| **rf-67** | `report/penetration.py` | 895 | `_SECTOR_KEYWORDS` ~330 行迁入 JSON 配置 |
| **rf-68** | `analysis/rebalance.py` | 875 | 静默期管理拆出到 `_silence.py` |
| **rf-69** | `llm/generators.py` | 754 | 幻觉过滤逻辑拆出到 `_hallucination_filter.py` |
| **rf-70** | `llm/generators_orchestrator.py` | 743 | `_MODULE_FNS` 提升为模块级常量；fact-check 集成逻辑提取为独立函数 |
| **rf-71** | `config/_core.py` | 738 | LLM 配置解析逻辑拆分到 `_llm_providers.py` 子模块 |
| **rf-72** | `provider_registry.py` | 708 | 熔断状态序列化/Chain 管理/phase_timeout 提取独立模块 |
| **rf-73** | `llm/api.py` | 707 | call_claude/call_openai/call_gemini 可提取到子模块 |
| **rf-74** | `llm/skeleton.py` | 685 | 批量模式代码拆出到 `_batch_mode.py` |
| **rf-75** | `registry.py` | 617 | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责 |
| **rf-76** | `llm/fact_checker.py` | 620 | 核心校验逻辑与辅助函数分离 |
| **rf-77** | `handlers_config.py` | 553 | JSON 文本编辑函数提取到 `config/` 子模块 |
| **rf-78** | `fetcher/batch.py` | 549 | BatchDispatcher 本身内聚，可维持现状 |
| **rf-79** | `code_utils.py` | 541 | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出 |
| **rf-80** | `report/data_status.py` | 528 | DegradationTracker 单类偏大 |
| **rf-81** | `report/html_renderers.py` | 521 | 所有 HTML render 函数揉合一体 |
| **rf-82** | `analysis/alignment_correction.py` | 518 | `cash_stripping` 中的现金识别逻辑可拆出 |
| **rf-83** | `providers/news_aggregator.py` | 524 | 去重逻辑提取为 `news_dedup.py` |
| **rf-84** | `providers/sina.py` | 516 | K 线相关函数提取为 `sina_kline.py` |
| **rf-85** | `fetcher/fund.py` | 394 | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-87** | `report/portfolio_history.py` | 497 | `get_combined_timeseries()` ~228 行函数可拆分 |
| **rf-88** | `report/html_writer.py` | 480 | `write_html_report()` ~275 行单函数可拆分 |
| **rf-89** | `report/excel_generator.py` | 447 | Excel 编排器 |

#### P2C — 测试文件过大

| # | 文件 | 行数 | 建议 |
|---|------|------|------|
| **rf-96** | `test_llm.py` | 2037 | 按模块拆分为多个文件 |
| **rf-97** | `test_scenario_penetration.py` | 1592 | 按场景分组拆分 |
| **rf-98** | `test_datetime_scenarios.py` | 1471 | 参数化 `TestClassifyHoldings` 和 `TestGetTtlMarketAware` 可减少 ~50% 代码 |
| **rf-99** | `test_cache.py` | 1422 | 按缓存子模块拆分 |
| **rf-100** | `test_llm_scenarios.py` | 1203 | 按 S11-S17 分组拆分 |

#### P2D — 测试质量问题

| # | 分类 | 文件 | 说明 |
|---|------|------|------|
| **rf-106** | 测试覆盖缺口 | 10+ 模块无对应测试 | `analysis/alignment_correction.py`、`circuit_breaker_wrapper.py`、`drawdown_warning.py`、`llm/fallback.py`、`llm/prompts_core.py`、`cache/_io.py`、`cache/services/holdings_tracker.py`、`report/excel_b_series.py` 等 |

#### P2F — LLM 模块特定问题

| # | 分类 | 文件 | 说明 |
|---|------|------|------|
| **rf-118** | 设计问题 | `llm/generators_orchestrator.py` | `_MODULE_FNS` 是 `_dispatch_llm_workers()` 的局部变量而非模块级常量，新增 LLM 模块需潜入 239 行函数内部注册，降低可发现性。建议提升为模块级常量 |

### P3 - 低优先级（可逐步跟进）

| # | 分类 | 问题 | 文件 | 说明 |
|---|------|------|------|------|
| **rf-108** | 包入口无 `__all__` | `providers/__init__.py` | 仅 4 行 docstring，无 `__all__` 导出声明 |
| **rf-109** | 冗余委托函数 | `fetcher/industry.py:80-82` | `_is_a_share_code()` 仅封装 `code_utils.is_a_share_code`，多余间接层 |
| **rf-111** | 字符串拼接默认值 | `config/_config_defaults.py:112-212` | 纯字符串拼接构建 JSON（~100 行），默认值与 `_DEFAULT_CONFIG` 可能不一致（如 `analysis: "off"` vs `"auto"`） |
| **rf-112** | 字符串拼接默认值 | `config/_llm_defaults.py:10-143` | 同上，纯字符串拼接 LLM 默认值（134 行） |
| **rf-113** | `enumerate + pop` 迭代删除 | `registry.py:609-613` | `get_report_section_order()` 在循环中 `enumerate` 后 `pop` 删除元素 |
| **rf-114** | 模块级 `logger` 未使用 | `code_utils.py:13` | `logger` 变量初始化后全文件无日志调用 |
| **rf-115** | `is_chain_broken()` 对未注册 Provider 返回 False | `provider_registry.py:370-397` | 未注册的 Provider 被认为"链可用"，实际不可用 |
| **rf-116** | 翻页游标潜在无限循环 | `providers/eastmoney_news.py:77-129` | `sort_end` 依赖最后一条 `showTime` 作为游标，可能导致重复请求相同数据 |
| **rf-117** | `_busy` 标志位无锁 | `tui_handlers.py:24,254-267` | 当前单线程 OK，但设计上标志位无锁保护 |

---

## 归档

### 已修复问题

| # | 分类 | 问题 | 修复内容 | 修复版本 |
|---|------|------|---------|---------|
| rf-1 | **批量数据获取串行瓶颈** | `providers/` + `fetcher/` 核心批量数据获取（行情/基金排名/行业分类）在批次内逐资产串行请求，full 路径 ~85s 中 ~50s 串行 IO | 引入 BatchDispatcher（ThreadPoolExecutor）统一管理并行生命周期：链级并行 + 熔断器感知 + 限速控制 + 降级聚合。覆盖 fund.py（排名+持仓）、penetration.py、fund_performance.py、html_builders.py、industry.py 共 7 处批量调用，配置文件驱动线程池上限（max_total_workers=15）。dev-verify 1114 ✅, edge 478 ✅ | v0.8.8-dev |
| rf-6 | **C3 违反 - 非原子写入** | `provider_registry.py:_save_state()` 使用 `open(path, "w")` 直接覆写熔断状态文件 | 改用 `tempfile.mkstemp + os.replace` 原子写入模式 | v0.8.10-dev |
| rf-7 | **C3 违反 - 非原子写入** | `features.py:save_feature_overrides()` 使用 `open(_FEATURES_FILE, "w")` 直接覆写 `features.json` | 改用 `tempfile.mkstemp + os.replace` 原子写入 | v0.8.10-dev |
| rf-8 | **C3 违反 - 非原子写入** | `handlers_config.py:_write_llm_settings()` 使用 `open(path, "w")` 直接写入 `llm_settings.json` | 改用 `tempfile.mkstemp + os.replace` 原子写入 | v0.8.10-dev |
| rf-9 | **C18 违反 - 凭据内联** | `config/_core.py:_parse_providers_list()` 无 `credentials_ref` 时内联存储 `api_key` | 强制使用 `credentials_ref`，内联 api_key 时 WARNING + 自动迁入凭据字典 | v0.8.10-dev |
| rf-10 | **C18 违反 - 回退路径** | `get_llm_config()` 从 `llm_settings.json` 回退读取 `api_key` | 移除该回退路径，强制使用 `llm_key.json` 或 `credentials_ref` | v0.8.10-dev |
| rf-11 | **C16 违反 - 路径未绝对化** | `_PATH_CONFIG_KEYS` 缺少 `llm_providers_file` | 在 `_PATH_CONFIG_KEYS` 和 `_STRING_CONFIG_KEYS` 中补上 | v0.8.10-dev |
| rf-12 | **C6 违反 - 绕过 Provider Chain** | `fetcher/bond_yield.py` 直接调用 `ak.bond_zh_us_rate()`，无熔断检查 | 集成 akshare 熔断检查 + 列名匹配替换硬编码 `df.columns[3]` | v0.8.10-dev |
| rf-13 | **封装破坏** | `handlers_config.py:_cmd_refresh_config()` 直接修改 `config._core` 私有属性 | 新增 `invalidate_config_cache()`/`invalidate_llm_config_cache()` 公共 API | v0.8.10-dev |
| rf-14 | **死测试** | 4 个 `@pytest.mark.skip` 骨架占位测试文件 | 确认功能已由其它测试覆盖，删除 4 个空占位文件 | v0.8.10-dev |
| rf-2 | 文件过长 | `providers/tiantian.py`（768 行）持仓解析、季报回退、排名评级、历史净值揉合一体 | 拆分为 4 子模块：`tiantian_base.py`（HTTP 基底）、`tiantian_holdings.py`（持仓/季报）、`tiantian_ranking.py`（排名/评级/风险分析）、`tiantian_nav.py`（历史净值）；原文件删除；外部调用方直接引用子模块 | v0.8.7-dev |
| rf-3 | 文件过长 | `report/fund_style_analysis.py`（652 行）快照管理、单股分类、行业 PE、批量降级、漂移检测揉合一体 | 拆分为 3 子模块：`fund_style_base.py`（常量/快照/工具函数）、`fund_style_classify.py`（单股分类/行业 PE/入口函数）、`fund_style_report.py`（漂移检测/全基金分析）；原文件删除 | v0.8.7-dev |
| rf-4 | 缺乏性能基准 | `scripts/` — 无端到端性能基准，无法量化进度、检测回归 | 三层性能基准体系：① `perf.py` PerfCollector 每次报告生成自动计时 + 持久化到 `perf_history.jsonl` ② `perf_report.py` 独立基准脚本（mock 外部源）用于精准回归检测 ③ `perf_view.py` 历史趋势可视化工具 | v0.8.7-dev |
| rf-5 | CI 测试失败 | `pyproject.toml` 中 `required_plugins` 将 `pytest-mock` 死锁在 `==3.15.1`，但 deps 声明 `>=3.15`，导致 pip 安装的版本（如 `3.15.2`）不满足 `==3.15.1` 硬校验，pytest 拒绝启动；`format` job 的 Ruff 检查无 `continue-on-error`，阻塞 CI；`all` 模式无 `--no-timeout` 易超时截断 | ① `required_plugins` 改为 `pytest-mock>=3.15` 与 deps 一致 ② `format` job 添加 `continue-on-error: true` ③ `all` 模式添加 `--no-timeout` | v0.8.6-dev |
| rf-92 | **P2B 魔数 - 时区硬编码** | `market_hours.py` 5 个函数中重复 `timezone(timedelta(hours=8))` | 提取为模块级常量 `_BJ_TZ` | v0.8.10-dev |
| rf-93 | **P2B 魔数 - K 线超时硬编码** | `providers/sina.py`/`tencent.py` 中 K 线超时 `30.0` 硬编码 | 提取为模块级常量 `_KLINE_TIMEOUT` | v0.8.10-dev |
| rf-94 | **P2B 魔数 - 超额阈值硬编码** | `report/fund_performance.py` `_EXCESS_THRESHOLD_UP/DOWN` 硬编码 | 改为 `config.json` 可配置（`performance_evaluation.excess_threshold_up/down`） | v0.8.10-dev |
| rf-102 | **P2D C13 隔离不完整** | `test/conftest.py:_isolate_sensitive_paths` 未重定向 LLM 配置文件 | 补充 `llm_key.json`、`llm_providers.json`、`llm_settings.json` 路径隔离 | v0.8.10-dev |
| rf-103 | **P2D C13 违反** | `test_config.py:382` 直接 `open(...)` 读取真实 LLM 配置文件 | 改用 `get_llm_settings_path()` | v0.8.10-dev |
| rf-104 | **P2D C13 违反** | `test_integration.py:403-408` 硬编码 `cache_dir = 'data/cache'` | 改用 `get_cache_dir()` | v0.8.10-dev |
| rf-119 | **P2F 影子导入** | `llm/generators.py` `generate_debate_procon()` 内部重复导入 | 移除内部重复导入，使用模块级导入 | v0.8.10-dev |
| rf-120 | **P2F 重复 logger** | `llm/prompts_action.py` 连续两行 `logger = logging.getLogger("invest")` | 删除重复行 | v0.8.10-dev |
| rf-121 | **P2F 未使用导入** | `llm/prompts_tables.py:20` 从 `code_utils` 导入 `is_a_share_code`、`is_hk_stock_code` 但无调用 | 移除未使用导入 | v0.8.10-dev |
| rf-122 | **P2F 未使用导入** | `llm/prompts_core.py:15` 从 `datetime` 导入 `datetime`、`timedelta`、`timezone` 但无调用 | 移除未使用导入 | v0.8.10-dev |
| rf-123 | **P2F `__all__` 缺失** | `llm/prompts.py` 导入 `_build_qa_concentration_block` 但 `__all__` 未列出 | 补充 `__all__` 条目 | v0.8.10-dev |
| rf-124 | **P2F 重复逻辑** | `llm/api.py` 空白内容重试逻辑在 `_call_provider_entry` 和 `_call_llm_legacy` 中重复 | 提取共享 `_calm_retry()` 函数 | v0.8.10-dev |
| rf-125 | **P2F 重复逻辑** | `llm/prompts_action.py` `_build_global_macro_prompt()` 内联完整 TOP3 排序与 `_build_top3_block()` 重复 | 复用 `_build_top3_block()` | v0.8.10-dev |
| rf-126 | **P2F 重复逻辑** | `llm/api.py` `call_gemini()` 重新实现 `configure_extended_thinking()` 的 budget-floor 逻辑 | 提取共享 `_resolve_thinking_budget()` 函数 | v0.8.10-dev |
| rf-127 | **P2F 重复逻辑** | `llm/fact_checker.py` 内联关键词检查与 `_is_contribution_sentence()` 重复 | 统一使用 `_is_contribution_sentence()` | v0.8.10-dev |
| rf-128 | **P2F 硬编码值** | `llm/generators_orchestrator.py` HTTP 连接池 `max_connections=20`、`max_keepalive_connections=10` 硬编码 | 提取为模块级常量 `_LLM_MAX_CONNECTIONS`、`_LLM_MAX_KEEPALIVE` | v0.8.10-dev |
| rf-129 | **P2F 硬编码值** | `llm/skeleton.py` `BATCH_SIZE=10`、`max_workers=min(...)` 硬编码 | 提取为模块级常量 `_BATCH_CHUNK_SIZE`、`_BATCH_MAX_WORKERS` | v0.8.10-dev |
| rf-130 | **P2F 硬编码值** | `llm/api.py` 默认模型名 `"claude-sonnet-4-20250514"` 等硬编码 | 提取为模块级常量 `_DEFAULT_CLAUDE_MODEL` 等 | v0.8.10-dev |
| rf-15 | **P1A C1 违反** | `analysis/alignment_correction.py:_classify_fund_type()` 硬编码代码类型判定 | 改用 `code_utils.is_a_share_code()`、`is_hk_stock_code()` 中心化函数 | v0.8.10-dev |
| rf-16 | **P1A C2 违反** | `news_aggregator.py` 锚点文件写 `data/cache/dedup_anchors.jsonl` 未通过缓存接口 | 迁出到 `data/calibration/` 非缓存目录 | v0.8.10-dev |
| rf-18 | **P1A C9 违反** | `registry.py` 辩论模块 `DataModuleDef` 缺 `settings_suffix` | 添加 `settings_suffix="debate_pro"/"debate_con"/"debate_synthesis"` | v0.8.10-dev |
| rf-20 | **P1A C15 违反** | `handlers_check_sources.py:_colored()` 缺少 `NO_COLOR`/`isatty` 检查 | 新增 `_use_ansi()` 函数统一检查 `NO_COLOR`+`isatty()`+encoding | v0.8.10-dev |
| rf-21 | **P1A C19 违反** | `orchestrator.py` 直接赋值 `pipeline_data["risk_metrics"]` 绕过 Schema 校验 | 在 `_PIPELINE_DATA_KNOWN_KEYS`/`_PREP_KNOWN_KEYS`/类型映射中注册所有键 | v0.8.10-dev |
| rf-22 | **P1A C19 违反** | `pipeline_data_builder.py` `build()` 静默注册未知键 | 改为未注册键先 `logger.warning` 再注册 | v0.8.10-dev |
| rf-23 | **P1B 裸异常过宽** | `config/_core.py:_get_llm_providers_path()`/`_get_llm_key_path()` `except Exception` 过宽 | 缩小为 `(KeyError, TypeError, AttributeError)` | v0.8.10-dev |
| rf-24 | **P1B 裸异常过宽** | `reader.py:get_xlsx_info()` `except Exception` 掩盖编程错误 | 缩小为 `(FileNotFoundError, zipfile.BadZipFile, InvalidFileException, OSError)` | v0.8.10-dev |
| rf-25 | **P1B 静默吞异常** | `circuit_breaker_wrapper.py:_log_ff_event()`/`record_failure()` `except Exception: pass` | 改为 `logger.debug(..., exc_info=True)` | v0.8.10-dev |
| rf-26 | **P1B 裸异常过宽** | `metrics.py:get_dividend_yield` `except Exception` 仅 debug 日志 | 提升为 `logger.warning(..., exc_info=True)` | v0.8.10-dev |
| rf-27 | **P1B 静默吞异常** | `llm/api.py:_resolve_first_provider_model_endpoint` `except Exception: pass` | 添加 `logger.debug(..., exc_info=True)` | v0.8.10-dev |
| rf-28 | **P1B 静默吞异常** | `llm/skeleton.py` `_build_provider_cache_key`/`generate_llm_content` `except Exception: pass` | 添加 `logger.debug(..., exc_info=True)` | v0.8.10-dev |
| rf-29 | **P1B 静默吞异常** | `news_aggregator.py:_flush_anchors()` `except OSError: pass` | 改为 `logger.warning("锚点文件写入失败: %s", e)` | v0.8.10-dev |
| rf-30 | **P1B 裸异常过宽** | `akshare_extras.py` 指纹/分红摘要 `except Exception` 过宽 | 缩小为 `(TypeError, ValueError)`/`(TypeError, ValueError, IndexError, KeyError)` | v0.8.10-dev |
| rf-31 | **P1C 死代码** | `tui_handlers.py:check_network_available()` 全局无调用方 | 删除该函数 | v0.8.10-dev |
| rf-32 | **P1C 死代码** | `config/_config_defaults.py` `_PATH_KEYS` 全局无引用 | 删除 | v0.8.10-dev |
| rf-33 | **P1C 死代码** | `report/html_jinja_env.py:_jinja_section_visible()` 未注册为 Jinja2 过滤器或全局变量 | 删除 | v0.8.10-dev |
| rf-34 | **P1C 死代码** | `akshare_extras.py:_SECTOR_FLOW_FAILURE` 仅写入无读取 | 删除变量及相关赋值 | v0.8.10-dev |
| rf-35 | **P1C 死代码** | `akshare_news.py:_MAX_CCTV` 定义为 17 但从未引用 | 删除 | v0.8.10-dev |
| rf-51 | **P1E 重复代码** | `html_writer.py`/`excel_generator.py` 辩论模式检测逻辑重复 | 提取到 `data_status.py` 共享函数 `_has_debate_data()` | v0.8.10-dev |
| rf-52 | **P1E 重复代码** | `config/_core.py` 4 处原子写入重复 | 提取为 `_atomic_write()` 工具函数 | v0.8.10-dev |
| rf-53 | **P1E 重复代码** | 3 个新闻模块各自实现 `_ts_to_str()` | 统一到 `providers/_utils.py` | v0.8.10-dev |
| rf-54 | **P1E 重复代码** | `tiantian_base.py`/`eastmoney.py` 各自实现 `_safe_float()` | 统一到 `providers/_utils.py` 的 `safe_float()` | v0.8.10-dev |
| rf-55 | **P1E 重复代码** | `handlers_report.py` 三个生成命令 85% 重复 | 提取通用辅助函数 | v0.8.10-dev |
| rf-56 | **P1E 重复代码** | `handlers_config.py` 三个配置命令 95% 重复 | 提取 `_edit_single_config()` | v0.8.10-dev |
| rf-57 | **P1E 重复代码** | `handlers_cache.py` 两个更新命令 90% 重复 | 提取差分化参数 | v0.8.10-dev |
| rf-58 | **P1E 重复代码** | `skeleton.py` 截断重试逻辑重复 | `_execute_and_merge_batch` 复用 `_handle_truncation` | v0.8.10-dev |
| rf-59 | **P1E 重复代码** | `skeleton.py`/`generators_orchestrator.py` 缓存命中处理重复 | 统一缓存命中处理逻辑 | v0.8.10-dev |
| rf-60 | **P1E 重复代码** | `sina.py` 三处 `_pf()` 局部函数重复定义 | 提取为模块级私有函数 | v0.8.10-dev |
| rf-61 | **P1F 线程安全** | `news_aggregator.py:_last_src_results` 模块级 dict 无锁 | 新增 `_src_results_lock` 保护写入 | v0.8.10-dev |
| rf-62 | **P1F 线程安全** | `news_aggregator.py:_ANCHOR_RECORDS` 模块级 list 无锁 | 新增 `_ANCHOR_LOCK` + `_record_anchor()` 线程安全追加 | v0.8.10-dev |
| rf-63 | **P1F 线程安全** | `provider_registry.py:fetch_cached_only()` 就地修改缓存 dict | `data = dict(data)` 复制后再修改 | v0.8.10-dev |
| rf-64 | **P1F 线程安全** | `features.py:FEATURE_FLAGS` `clear()+update()` 非原子 | 新增 `_FEATURES_LOCK` 保护所有写操作 | v0.8.10-dev |
| rf-90 | **P2B 魔数 — 行业关键词硬编码** | `report/penetration.py` `_SECTOR_KEYWORDS` ~330 行硬编码字典 | 迁出至 `data/knowledge/sector_keywords.json`，`_load_sector_keywords()` 加载 | v0.8.10-dev |
| rf-91 | **P2B 魔数 — 列索引硬编码** | `fetcher/bond_yield.py:107` `df.columns[3]` 硬编码列索引 | 改为列名匹配 `"中国国债收益率10年"`（随 C6 修复 rf-12 一并完成） | v0.8.10-dev |
| rf-95 | **P2B 魔数 — 基准映射硬编码** | `fetcher/fund.py` `_BUILTIN_BENCHMARKS` 13 条硬编码基准映射 | 迁出至 `data/knowledge/fund_benchmarks.json`，`_load_builtin_benchmarks()` 加载 | v0.8.10-dev |
| rf-110 | **P3 重复导入** | `handlers_check_sources.py:12,23` 同一文件重复 `import sys` | 随 P1A rf-20 修复移除重复行 | v0.8.10-dev |
| rf-107 | 排查关闭 — 设计冲突（误报） | `review-findings.md` 原记载 `simple_rebalance.py` 与 `rebalance.py` 存在同名函数 `compute_rebalance_signals`。排查确认：`simple_rebalance.py` 实际函数名为 `compute_simple_rebalance_signals`，与 `rebalance.py` 的 `compute_rebalance_signals` 已区分，无命名冲突。`simple_rebalance` 仍被 `prompts_core.py` 用于轻量无配置依赖场景，非废弃代码 | 保持现状，无需修改 | v0.8.10-dev |
| rf-101 | **P2D 测试死代码** | `test_integration.py:426` `test_api_called_when_no_cache` 长期 `@unittest.skip` | 修正 `fetch_market_data` mock 路径 + 补充 `is_market_open` mock，移除 `@unittest.skip`，清除重复 setUp 代码 | v0.8.10-dev |
| rf-105 | **P2D 测试重复** | `test_datetime_scenarios.py` `TestClassifyHoldings`（12 个测试）和 `TestGetTtlMarketAware`（12 个测试）重复模式 | 参数化重构：`TestGetTtlMarketAware` 10 个场景 + 2 个回退场景 → `@pytest.mark.parametrize`，`TestClassifyHoldings` 13 个单品测试 → `@pytest.mark.parametrize`，保留混合/边界用例为独立方法。代码行数减少 ~60%，测试覆盖不变（41 pt ✅） | v0.8.10-dev |

### 归档档案

- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
