# 个人投资分析报告生成小助手 - 自我审查问题记录

> 文档版本：v0.8.10-dev
> 审查范围：全代码库（src/python/ + src/test/ + scripts/）
> 审查基准：technical.md §8 架构设计约束（C1~C19）+ §1.4 核心架构决策 + 代码质量最佳实践
> 审查日期：2026-07-29

---

## 当前待处理问题

### P2 - 代码质量（低优先级，增量改进）

#### P2A — 文件过长（>500 行，建议拆分）

| # | 文件 | 行数 | 拆分建议 |
|---|------|------|----------|
| **rf-75** | `registry.py` | 617 | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责 |
| **rf-76** | `llm/fact_checker.py` | 623 | 核心校验逻辑与辅助函数分离（注：长函数已拆分，文件级别未拆） |
| **rf-77** | `handlers_config.py` | 553 | JSON 文本编辑函数提取到 `config/` 子模块 |
| **rf-78** | `fetcher/batch.py` | 549 | BatchDispatcher 本身内聚，可维持现状 |
| **rf-79** | `code_utils.py` | 541 | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出 |
| **rf-80** | `report/data_status.py` | 528 | DegradationTracker 单类偏大 |
| **rf-81** | `report/html_renderers.py` | 521 | 所有 HTML render 函数揉合一体 |
| **rf-85** | `fetcher/fund.py` | 394 | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 447 | Excel 编排器 |

---

## 归档

### 已修复问题

| # | 分类 | 摘要 |
|---|------|------|
| rf-1 | **批量数据获取串行瓶颈** | `providers/` + `fetcher/` 核心批量数据获取（行情/基金排名/行业分类）在批次内逐资产串行请求，full 路径 ~85s 中 ~5… |
| rf-2 | 文件过长 | `providers/tiantian.py`（768 行）持仓解析、季报回退、排名评级、历史净值揉合一体 |
| rf-3 | 文件过长 | `report/fund_style_analysis.py`（652 行）快照管理、单股分类、行业 PE、批量降级、漂移检测揉合一体 |
| rf-4 | 缺乏性能基准 | `scripts/` — 无端到端性能基准，无法量化进度、检测回归 |
| rf-5 | CI 测试失败 | `pyproject.toml` 中 `required_plugins` 将 `pytest-mock` 死锁在 `==3.15.1`，但 deps 声… |
| rf-6 | **C3 违反 - 非原子写入** | `provider_registry.py:_save_state()` 使用 `open(path, "w")` 直接覆写熔断状态文件 |
| rf-7 | **C3 违反 - 非原子写入** | `features.py:save_feature_overrides()` 使用 `open(_FEATURES_FILE, "w")` 直接覆写 `f… |
| rf-8 | **C3 违反 - 非原子写入** | `handlers_config.py:_write_llm_settings()` 使用 `open(path, "w")` 直接写入 `llm_set… |
| rf-9 | **C18 违反 - 凭据内联** | `config/_core.py:_parse_providers_list()` 无 `credentials_ref` 时内联存储 `api_key` |
| rf-10 | **C18 违反 - 回退路径** | `get_llm_config()` 从 `llm_settings.json` 回退读取 `api_key` |
| rf-11 | **C16 违反 - 路径未绝对化** | `_PATH_CONFIG_KEYS` 缺少 `llm_providers_file` |
| rf-12 | **C6 违反 - 绕过 Provider Chain** | `fetcher/bond_yield.py` 直接调用 `ak.bond_zh_us_rate()`，无熔断检查 |
| rf-13 | **封装破坏** | `handlers_config.py:_cmd_refresh_config()` 直接修改 `config._core` 私有属性 |
| rf-14 | **死测试** | 4 个 `@pytest.mark.skip` 骨架占位测试文件 |
| rf-15 | **P1A C1 违反** | `analysis/alignment_correction.py:_classify_fund_type()` 硬编码代码类型判定 |
| rf-16 | **P1A C2 违反** | `news_aggregator.py` 锚点文件写 `data/cache/dedup_anchors.jsonl` 未通过缓存接口 |
| rf-17 | **P1A C4 违反** | `fetcher/price.py/industry.py/fund_manager.py` 缺少 `DataSourceRegistry.session… |
| rf-18 | **P1A C9 违反** | `registry.py` 辩论模块 `DataModuleDef` 缺 `settings_suffix` |
| rf-19 | **P1A C14 违反** | `provider_registry.py` 四个模块级全局变量（`_phase_timer`/`_phase_expired`/`_phase_time… |
| rf-20 | **P1A C15 违反** | `handlers_check_sources.py:_colored()` 缺少 `NO_COLOR`/`isatty` 检查 |
| rf-21 | **P1A C19 违反** | `orchestrator.py` 直接赋值 `pipeline_data["risk_metrics"]` 绕过 Schema 校验 |
| rf-22 | **P1A C19 违反** | `pipeline_data_builder.py` `build()` 静默注册未知键 |
| rf-23 | **P1B 裸异常过宽** | `config/_core.py:_get_llm_providers_path()`/`_get_llm_key_path()` `except Exc… |
| rf-24 | **P1B 裸异常过宽** | `reader.py:get_xlsx_info()` `except Exception` 掩盖编程错误 |
| rf-25 | **P1B 静默吞异常** | `circuit_breaker_wrapper.py:_log_ff_event()`/`record_failure()` `except Excep… |
| rf-26 | **P1B 裸异常过宽** | `metrics.py:get_dividend_yield` `except Exception` 仅 debug 日志 |
| rf-27 | **P1B 静默吞异常** | `llm/api.py:_resolve_first_provider_model_endpoint` `except Exception: pass` |
| rf-28 | **P1B 静默吞异常** | `llm/skeleton.py` `_build_provider_cache_key`/`generate_llm_content` `except … |
| rf-29 | **P1B 静默吞异常** | `news_aggregator.py:_flush_anchors()` `except OSError: pass` |
| rf-30 | **P1B 裸异常过宽** | `akshare_extras.py` 指纹/分红摘要 `except Exception` 过宽 |
| rf-31 | **P1C 死代码** | `tui_handlers.py:check_network_available()` 全局无调用方 |
| rf-32 | **P1C 死代码** | `config/_config_defaults.py` `_PATH_KEYS` 全局无引用 |
| rf-33 | **P1C 死代码** | `report/html_jinja_env.py:_jinja_section_visible()` 未注册为 Jinja2 过滤器或全局变量 |
| rf-34 | **P1C 死代码** | `akshare_extras.py:_SECTOR_FLOW_FAILURE` 仅写入无读取 |
| rf-35 | **P1C 死代码** | `akshare_news.py:_MAX_CCTV` 定义为 17 但从未引用 |
| rf-36~50 | **P1D 函数过长** | 15 个 >100 行函数 |
| rf-51 | **P1E 重复代码** | `html_writer.py`/`excel_generator.py` 辩论模式检测逻辑重复 |
| rf-52 | **P1E 重复代码** | `config/_core.py` 4 处原子写入重复 |
| rf-53 | **P1E 重复代码** | 3 个新闻模块各自实现 `_ts_to_str()` |
| rf-54 | **P1E 重复代码** | `tiantian_base.py`/`eastmoney.py` 各自实现 `_safe_float()` |
| rf-55 | **P1E 重复代码** | `handlers_report.py` 三个生成命令 85% 重复 |
| rf-56 | **P1E 重复代码** | `handlers_config.py` 三个配置命令 95% 重复 |
| rf-57 | **P1E 重复代码** | `handlers_cache.py` 两个更新命令 90% 重复 |
| rf-58 | **P1E 重复代码** | `skeleton.py` 截断重试逻辑重复 |
| rf-59 | **P1E 重复代码** | `skeleton.py`/`generators_orchestrator.py` 缓存命中处理重复 |
| rf-60 | **P1E 重复代码** | `sina.py` 三处 `_pf()` 局部函数重复定义 |
| rf-61 | **P1F 线程安全** | `news_aggregator.py:_last_src_results` 模块级 dict 无锁 |
| rf-62 | **P1F 线程安全** | `news_aggregator.py:_ANCHOR_RECORDS` 模块级 list 无锁 |
| rf-63 | **P1F 线程安全** | `provider_registry.py:fetch_cached_only()` 就地修改缓存 dict |
| rf-64 | **P1F 线程安全** | `features.py:FEATURE_FLAGS` `clear()+update()` 非原子 |
| rf-66 | **P2A 文件过大** | `analysis/metrics.py` 990 行，辅助数学函数揉合 |
| rf-67 | **P2A 文件过大** | `report/penetration.py` 895 行，`_SECTOR_KEYWORDS` ~330 行硬编码 |
| rf-68 | **P2A 文件过大** | `analysis/rebalance.py` 875 行，静默期管理揉合 |
| rf-69 | **P2A 文件过大** | `llm/generators.py` 754 行，幻觉过滤逻辑揉合 |
| rf-70 | **P2A 文件过大** | `llm/generators_orchestrator.py` 743 行，`_MODULE_FNS` 局部变量 |
| rf-71 | **P2A 文件过大** | `config/_core.py` 738 行，LLM 配置解析逻辑揉合 |
| rf-72 | **P2A 文件过大** | `provider_registry.py` 708 行，熔断/超时/缓存揉合 |
| rf-73 | **P2A 文件过大** | `llm/api.py` 707 行，call_claude/call_openai/call_gemini 揉合 |
| rf-82 | **P2A 文件过大** | `analysis/alignment_correction.py` 577 行 |
| rf-83 | **P2A 文件过大** | `providers/news_aggregator.py` 524 行 |
| rf-84 | **P2A 文件过大** | `providers/sina.py` 516 行 |
| rf-65 | **P2A 文件过大** | `report/orchestrator.py` 1031 行 |
| rf-74 | **P2A 文件过大** | `llm/skeleton.py` 705 行 |
| rf-88 | **P2A 文件过大** | `report/html_writer.py` 480 行 |
| rf-87 | **P2A 文件过大** | `report/portfolio_history.py` 597 行 |
| rf-90 | **P2B 魔数 — 行业关键词硬编码** | `report/penetration.py` `_SECTOR_KEYWORDS` ~330 行硬编码字典 |
| rf-91 | **P2B 魔数 — 列索引硬编码** | `fetcher/bond_yield.py:107` `df.columns[3]` 硬编码列索引 |
| rf-92 | **P2B 魔数 - 时区硬编码** | `market_hours.py` 5 个函数中重复 `timezone(timedelta(hours=8))` |
| rf-93 | **P2B 魔数 - K 线超时硬编码** | `providers/sina.py`/`tencent.py` 中 K 线超时 `30.0` 硬编码 |
| rf-94 | **P2B 魔数 - 超额阈值硬编码** | `report/fund_performance.py` `_EXCESS_THRESHOLD_UP/DOWN` 硬编码 |
| rf-95 | **P2B 魔数 — 基准映射硬编码** | `fetcher/fund.py` `_BUILTIN_BENCHMARKS` 13 条硬编码基准映射 |
| rf-96 | **P2C 测试文件过大** | `test_llm.py` 2037 行 |
| rf-97 | **P2C 测试文件过大** | `test_scenario_penetration.py` 1592 行 |
| rf-98 | **P2C 测试文件过大** | `test_datetime_scenarios.py` 1471 行 |
| rf-99 | **P2C 测试文件过大** | `test_cache.py` 1422 行 |
| rf-100 | **P2C 测试文件过大** | `test_llm_scenarios.py` 1203 行 |
| rf-101 | **P2D 测试死代码** | `test_integration.py:426` `test_api_called_when_no_cache` 长期 `@unittest.skip` |
| rf-102 | **P2D C13 隔离不完整** | `test/conftest.py:_isolate_sensitive_paths` 未重定向 LLM 配置文件 |
| rf-103 | **P2D C13 违反** | `test_config.py:382` 直接 `open(...)` 读取真实 LLM 配置文件 |
| rf-104 | **P2D C13 违反** | `test_integration.py:403-408` 硬编码 `cache_dir = 'data/cache'` |
| rf-105 | **P2D 测试重复** | `test_datetime_scenarios.py` 重复模式 |
| rf-107 | 排查关闭 — 设计冲突（误报） | `simple_rebalance.py` 与 `rebalance.py` 存在同名函数 `compute_rebalance_signals`。排查确… |
| rf-108 | **P3 包入口无 `__all__`** | `providers/__init__.py` 仅 4 行 docstring，无 `__all__` 导出声明 |
| rf-109 | **P3 冗余委托函数** | `fetcher/industry.py:80-82` `_is_a_share_code()` 仅封装 `code_utils.is_a_share_c… |
| rf-110 | **P3 重复导入** | `handlers_check_sources.py:12,23` 同一文件重复 `import sys` |
| rf-111 | **P3 字符串拼接默认值** | `config/_config_defaults.py:112-212` 纯字符串拼接构建 JSON（~100 行） |
| rf-112 | **P3 字符串拼接默认值** | `config/_llm_defaults.py:10-143` 纯字符串拼接 LLM 默认值（134 行） |
| rf-113 | **P3 `enumerate + pop` 迭代删除** | `registry.py:609-613` `get_report_section_order()` 在循环中 `enumerate` 后 `pop` 删除元素 |
| rf-114 | **P3 模块级 `logger` 未使用** | `code_utils.py:13` `logger` 变量初始化后全文件无日志调用 |
| rf-115 | **P3 `is_chain_broken()` 对未注册 Provider 返回 False** | `provider_registry.py:370-397` 未注册的 Provider 被认为"链可用" |
| rf-116 | **P3 翻页游标潜在无限循环** | `providers/eastmoney_news.py:77-129` `sort_end` 依赖最后一条 `showTime` 作游标 |
| rf-117 | **P3 `_busy` 标志位无锁** | `tui_handlers.py:24,254-267` 标志位无锁保护 |
| rf-118 | **P2F `_MODULE_FNS` 局部变量** | `llm/generators_orchestrator.py` `_MODULE_FNS` 是局部变量，新增 LLM 模块需潜入 239 行函数内部注册 |
| rf-119 | **P2F 影子导入** | `llm/generators.py` `generate_debate_procon()` 内部重复导入 |
| rf-120 | **P2F 重复 logger** | `llm/prompts_action.py` 连续两行 `logger = logging.getLogger("invest")` |
| rf-121 | **P2F 未使用导入** | `llm/prompts_tables.py:20` 导入 `is_a_share_code`、`is_hk_stock_code` 但无调用 |
| rf-122 | **P2F 未使用导入** | `llm/prompts_core.py:15` 从 `datetime` 导入 `datetime`、`timedelta`、`timezone` 但无调用 |
| rf-123 | **P2F `__all__` 缺失** | `llm/prompts.py` 导入 `_build_qa_concentration_block` 但 `__all__` 未列出 |
| rf-124 | **P2F 重复逻辑** | `llm/api.py` 空白内容重试逻辑在 `_call_provider_entry` 和 `_call_llm_legacy` 中重复 |
| rf-125 | **P2F 重复逻辑** | `llm/prompts_action.py` `_build_global_macro_prompt()` 内联完整 TOP3 排序与 `_build_… |
| rf-126 | **P2F 重复逻辑** | `llm/api.py` `call_gemini()` 重新实现 `configure_extended_thinking()` 的 budget-fl… |
| rf-127 | **P2F 重复逻辑** | `llm/fact_checker.py` 内联关键词检查与 `_is_contribution_sentence()` 重复 |
| rf-128 | **P2F 硬编码值** | `llm/generators_orchestrator.py` HTTP 连接池参数硬编码 |
| rf-129 | **P2F 硬编码值** | `llm/skeleton.py` `BATCH_SIZE=10`、`max_workers=min(...)` 硬编码 |
| rf-130 | **P2F 硬编码值** | `llm/api.py` 默认模型名 `"claude-sonnet-4-20250514"` 等硬编码 |
| rf-131 | **P2D 测试覆盖缺口** | `analysis/alignment_correction.py` 无独立单元测试 |
| rf-132 | **P2D 测试覆盖缺口** | `analysis/drawdown_warning.py` 无独立单元测试 |
| rf-133 | **P2D 测试覆盖缺口** | `cache/services/holdings_tracker.py` 无独立单元测试 |
| rf-134 | **P2D 测试覆盖缺口** | `llm/fallback.py` 无独立单元测试 |
| rf-135 | **P2D 测试覆盖缺口（批量低风险）** | `circuit_breaker_wrapper.py`, `cache/_io.py`, `llm/prompts_core.py`, `report/… |
| rf-106 | **P2D 已废弃** | 10+ 模块无对应测试 |

### 归档档案

- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
