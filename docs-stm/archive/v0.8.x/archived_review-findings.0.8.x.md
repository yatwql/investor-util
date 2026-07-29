# 自我审查问题记录归档 — v0.8.x

> 归档时间：2026-07-30
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.8.0 ~ v0.8.9（2026-07-21 ~ 2026-07-29）

---

## 已修复问题

### v0.8.0（2026-07-21）

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

### v0.8.1 ~ v0.8.9（2026-07-22 ~ 2026-07-29）

| # | 分类 | 摘要 |
|---|------|------|
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
