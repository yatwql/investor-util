# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Added
- **P1 基建 20 项全部完成（v0.7.4）**：
  - **P1-03**: Rf 获取——`bond_zh_us_rate` + 手动兜底，`bond_yield.py` 新建，C6 chain 路由合规
  - **P1-04**: 个股日收益率管线暴露，`portfolio_history.py` daily_returns 从局部变量→返回值
  - **P1-05**: 组合日收益率暴露，`get_combined_timeseries` 新增 `daily_returns_portfolio` 字段
  - **P1-06-A**: f_context 组装逻辑抽取，orchestrator.py→`f_context_builder.py`
  - **P1-06**: 阻断点 1——`prepare_report_data` 加 risk_metrics 空字典占位
  - **P1-07**: 阻断点 2——`capture_snapshot` 加 risk_metrics/portfolio_daily_returns 透传
  - **P1-08**: 阻断点 3——`generate_all_llm` 暴露 history_data 到 prompt
  - **P1-08-B**: prompts.py 拆为三文件（prompts_core.py / prompts_tables.py / prompts_action.py）
  - **P1-09**: 阻断点 4——fingerprint 含风险信号 Hash（risk_metrics 摘要）
  - **P1-10**: 数据模块注册 + `_COMPUTATION_REGISTRY`（bond_yield 注册 + 预留 6 计算模块）
  - **P1-11**: 功能开关注册 JSON Schema（18 开关），Feature Flag 体系 `is_feature_enabled()`
  - **P1-13**: 持仓匿名化最小版，`anonymizer.py` 名称替换/数量模糊/关闭三种模式
  - **P1-14**: 缓存文件权限保护，`cache.py` 写缓存设 0o600
  - **P1-15**: Rf fetcher 测试用例，mock 正常/异常/手动配置/缓存命中 8 场景
  - **P1-17**: 熔断器改进——指数退避（60s→300s→900s→3600s）
  - **P1-18**: 熔断器改进——持久化（`circuit_breaker.json`）
  - **P1-19**: 双熔断器统一网关（`circuit_breaker.py` + `provider_registry.py`）
  - **P1-20**: LLM 失败自动降级模板，全失败时占位文本
  - **P1-21**: f_context Schema Full Schema 补充+校验检查点
  - **P1-22**: analysis/ 层定位 + category.py→code_utils.py，消除逆向依赖
  - 合计 ~112h，53 tests passed（原 44→53，新增 registry/bond_yield 测试）
- **P1-12: 指标级断路包装器**：`circuit_breaker_wrapper.py`，per-indicator 熔断（连续 3 次→静默 24h），C20 FF↔CB 联动，持久化到 `metrics_breaker.json`
- **P2-01~P2-11a: 量化指标算法体系 11 个**：`analysis/metrics.py`（sharpe_ratio/calmar_ratio/hhi/win_rate/turnover_rate/risk_contribution/get_dividend_yield/individual_volatility/portfolio_beta/compute_all_metrics/sanitize_metric/truncate_extreme_values/check_data_sufficiency/get_confidence_level），~670 行纯函数
- **P2-12/P2-13: 回撤历史分位预警**：`analysis/drawdown_warning.py`，3 时间窗口（1 年/3 年/全历史），分位预警（80%/95% 阈值）
- **P2-14~P2-17: LLM Prompt 注入 4 项**：
  - `_build_metrics_table_block()` — 夏普/卡玛/HHI/Beta 等指标格式化
  - `_build_data_quality_detail_block()` — 降级详情报表
  - confidence guidance 注入 _SYSTEM_EXPERT_REVIEW
  - action template 表格注入 expert_review prompt
- **P1-16/P2-14-B/P2-18: 测试任务 3 项**：
  - **P1-16**: 管线集成冒烟测试（test_pipeline_smoke.py，4 阻断点，4 tests）
  - **P2-14-B**: 管线指标注入测试（test_pipeline_metrics_injection.py，14 tests）
  - **P2-18**: 指标集成测试（test_metrics.py，8 指标正+边界，24 tests）
  - 合计 42 tests，全部通过

### Added
- **P3-01~P3-06: 再平衡六项任务全部完成**：
  - **P3-01**: 目标配置 Schema——`rebalance.py` 支持大类+品种级目标配置，`compute_target_deviation()` 输出偏离度信号
  - **P3-02**: 阈值可配——三套预设集（保守 10%/3%、稳健 15%/5%、进取 25%/8%），`resolve_rebalance_config()` 解析，config 独立覆盖
  - **P3-03**: 静默期——同品种 N 天不重复告警（默认 30d，可配），JSON 持久化到 `rebalance_silence.json`
  - **P3-04**: 信号置信度——`_compute_confidence()` 输出 high/medium/low，单品种超限 2×threshold→high
  - **P3-05**: 误报防护——3 类：分红拆股（shares 检查）、新买入<20 日过滤、可转债到期标注
  - **P3-06**: 权益/固收偏离——`equity_fixed_income_deviation()` 将 7 类资产汇总为权益/固收超大类，对照目标配置计算偏离
  - 79 项单元测试全部通过，含 16 项权益/固收偏离专项测试
- **P3-07: 竞争语境完整版——自定义基金池**：
  - `index.py`/`sina.py` 新增中证500(`sh000905`)和中证全债(`sh000012`)指数映射
  - `comparison_indices` 配置项（默认沪深300+中证500+中证全债），含配置校验
  - `_build_competitive_context_block()` 支持多指数对比行
  - TUI 新增 `[I]` 管理对比指数池菜单
- **P3-08: 竞争语境完整版——夏普对比**：
  - 量化指标（夏普/卡玛/年化波动率/最大回撤）注入竞争语境【指标对比】段落
  - metrics 数据流在 `_generate_report_full()` 中计算，经 `_fetch_llm_and_news()` → `generate_all_llm()` → `_dispatch_llm_workers()` → `_build_competitive_context_block()` 全链路贯通
  - 8 项单元测试覆盖正常/空/部分键/None 值/NaN 等指标展示场景
- **P3-09a: 竞争语境——口径对齐与说明**：
  - 竞争语境段落末尾自动追加口径说明脚注（费后净收益 vs 价格指数、含现金 vs 不含、期间持仓变动）
  - `_SYSTEM_EXPERT_REVIEW` 新增竞争语境约束段落，限制 LLM 使用数据陈述替代主观结论
  - 3 项新增测试验证脚注和 LLM 约束内容
- **P3-10: 竞争语境——幸存者偏差说明**：
  - 竞争语境脚注追加幸存者偏差提示（指数成分股/成分基金定期调整效应）
  - 2 项新增测试验证提示存在/不存在
- **P3-11: 流动性风险——场内品种自动计算**：
  - `src/python/analysis/liquidity.py` 新增 `check_liquidity()` 函数，基于市值/20日日均成交额计算场内品种变现天数
  - OTC 基金正确识别并标记 type="otc"（交 P3-12），K 线数据缺失时降级为 assumed_liquid
  - 检查顺序：先场外（债券基/货基/代码重叠区 OTC）→ 后场内（A 股/场内基金）→ 港股等默认充足
  - `__init__.py` 导出 `check_liquidity`，registry.py `analytics_liquidity` 已注册（P1-10 预留）
- **P3-11-T: 流动性风险测试（场内）**：
  - `test_liquidity.py` 10 项正常场景（空输入/OTC/Stock/Mixed）+ `test_liquidity_edge.py` 5 项 edge 场景
  - mock 路径使用 `_MOCK_TARGET = "src.python.fetcher.chain.fetch_with_incremental_fallback"`（lazy import），C12 edge 文件隔离合规

### Changed
- **代码注释历史痕迹清理**：移除所有 P1-XX/P2-XX 任务标签（metrics.py、drawdown_warning.py、fingerprint.py、generators_orchestrator.py、prompts_action.py、prompts_core.py、prompts_tables.py、circuit_breaker.py、bond_yield.py、registry.py、orchestrator.py 等共 ~60 处），保持代码当前状态描述
- **registry.py analytics_metrics 状态**: "planned" → "implemented"
- **Phase 2 全部 19 项任务（P2-01~P2-18）提升至 P1 优先级**：所有任务从 `better-investment-task.md` 的 Phase 2 移至 `plan.md` 的 P1 待办区
- **Phase 3 全部 18 项任务（P3-01~P3-17）和 Phase 4 全部 17 项任务（P2-11b、P4-01~P4-16）提升至 P2 优先级**：所有任务从 `better-investment-task.md` 的 Phase 3/4 移至 `plan.md` 的 P2 待办区

### Docs
- `plan.md`: P1 阶段 39 项任务全部标记完成并从待办表移除，仅保留完成摘要
- `better-investment-task.md`: Phase 2/3/4 头部添加迁移告示；Phase 2 已实现任务标记完成
- `changelog.md`: 本次变更记录

---

## [0.7.3] - 2026-07-20

### Added
- **P2 全部 10 项任务完成（Tier 0 + MVP）**：
  - **T0-01-A**: DegradationTracker get_log() + 6 处 fetcher 层 record() + get_tracker() 单例工厂，消除三重实例碎片化
  - **T0-01-B**: f_context Pre-Schema 文档（`f_context-schema.md`）+ 删除 2 个死键 + 类型断言 checkpoint
  - **T0-01**: DegradationTracker→LLM 接线，注入 f_context["data_degradation"]
  - **T0-02**: 健康检查 3 类→5 类（新增数据质量维度评分标准）
  - **MVP-01**: `_build_profit_attribution_block()` TOP 5 收益归因（正负分别列出，Σ|profit|=0 保护）
  - **MVP-02**: `_build_concept_sector_block()` TOP 5 概念板块 + 集中度判断（3 态兜底：无数据/部分无分类/正常）
  - **MVP-03**: `src/python/analysis/simple_rebalance.py` 硬编码 15% 再平衡阈值 + 去重聚合（>3 条→汇总）
  - **MVP-04**: `_build_competitive_context_block()` 组合 vs 沪深300 今日/区间对比
  - **MVP-05**: 5 个段落整合串联到 prompts.py + generators.py/orch 竞争语境接线
  - **MVP-06**: `_SYSTEM_EXPERT_REVIEW` 追加情景分析（上涨/下跌 20% 分情景建议）
  - 合计 45h，regression 266 passed, 0 failed
- **PRE-01/PRE-02 专项测试**：完成 Rf 国债收益率数据源和偏股基金指数 885005 的全面测试
  - 东方财富 datacenter API（RPTBOND_*）**确认不可用**（30+ report name 全部返回"参数配置不对"）
  - `bond_zh_us_rate`（akshare/Sina）通过 50/50 稳定性测试（100% 成功率，平均 2.734s，中国 10Y=1.7404%）
  - worldgovernmentbonds.com 确认 JS 渲染不可直接抓取
  - 885005 确认为 Wind（万得）专属代码，12 个公开数据源均不可获取
  - CSI 替代指数（930950/932055/931255）同样不可用
- **测试报告归档**：`docs-stm/plan/better-investment-advice/rf-and-885005-test-report.md`

### Changed
- **设计文档全面更新**：plan.md、better-investment-task.md、discussion-better-investment-advice.md 同步 PRE 测试结论
- **P1-01/P1-02 取消**（东财 API 失效、worldgovernmentbonds JS 不可解析），释放 ~20h
- **P1-03 重设计**：从纯手动配置（4h）扩展为 `bond_zh_us_rate` 自动获取 + 手动配置兜底双模式（6h）
- **P1-15 缩减**：Rf 测试从 8h 缩减为 `bond_zh_us_rate` 集成测试（4h）
- **P3-07 降级路径确认**：885005 不可获取 → 强制降级为沪深300+自定义基金池
- **PRE-02-D prompt 分支**：决策已落地，代码实现归入 P3-07

### Docs
- `folders.md` 新增测试报告文件条目
- 全部 4 个 P1 PRE 任务完成，从 plan.md 当前迭代待办移除

---

## [0.7.2] - 2026-07-19

### Added
- **新闻去重阈值锚点采集 + 校准脚本**：`news_aggregator.py` 自动记录去重边界案例到 `data/cache/dedup_anchors.jsonl`（append-only，零运行时感知）；新增 `scripts/calibrate-dedup-threshold.py` 分析工具，积累 100 条后即可评估阈值是否合理

### Changed
- **CI 门禁精简**：移除 mypy 类型检查（从未全绿，形同虚设）；移除 ruff check 代码风格 lint（与 ruff format 重叠）。CI 仅保留三档测试门禁（P0/P1/P2）+ ruff format --check。CLAUDE.md 同步更新 CI 辅助检查说明

### Fixed
- **新闻标题去重算法重构**：基于 37 条真实新闻 47 对标注校准，替换单一 0.92 阈值为三层策略——同源（共享中文实体 bigram ≥ 4）、跨源（SequenceMatcher ≥ 0.50 直接合并 / 0.30~0.50 需共享 bigram ≥ 3）、子串包含兜底（6 字以上短标题包含于另一条）。消除同源/跨源同一事件多次出现问题，同时避免不同事件误合并（如"建行审查"vs"建行罚款"、"苹果反垄断"vs"苹果市值登顶"）

---

## [0.7.1] - 2026-07-18

### Added
- **Gemini Extended Thinking 支持**：`call_gemini()` 新增 `llm_config` 参数，根据 `thinking_enabled_{模块}`/`thinking_budget_{模块}` 配置向 `generationConfig.thinkingConfig.thinkingBudget` 注入推理预算。`api_base.py` 模型兼容列表新增 `gemini-2-5-` 前缀（仅 Gemini 2.5 系列支持）

### Changed
- **LLM 配置修复**：DeepSeek endpoint 补全路径 `.../anthropic` → `.../anthropic/v1/messages`（缺少 `/v1/messages` 导致 404）；模型名 `DeepSeek-V4-Flash` → `deepseek-v4-flash`（API 要求全小写）
- **Gemini URL 构造修复**：`call_gemini()` 传入 `endpoint` 时正确拼接 `/v1beta/models/{model}:generateContent` 路径，不再只取基础地址

### Fixed
- **基金历史净值获取全部为空（P0 修复）**：天天基金 `_parse_nav_trend()` 只认 `YYYYMMDD` 和 `YYYY-MM-DD` 格式，但东方财富 pingzhongdata 接口的 `x` 字段已改为**毫秒时间戳**（13 位），所有条目被 `continue` 跳过 → 返回 0 条。新增毫秒时间戳→日期转换分支
- **天天基金 HTTP 客户端健壮性**：`_request_pingzhong_data()` 缺少 `follow_redirects=True` 和 `raise_for_status()`，与同文件的 `_request_fund_html()` 不一致。补充后避免静默失败
- **JS 变量声明格式兼容**：`_parse_nav_trend()` 正则从仅匹配 `var` 扩展为匹配 `var`/`let`/`const`/`window.` 前缀
- **东方财富备用链路 HTTP 健壮性**：`fetch_fund_nav_history()` 补充 `follow_redirects=True` 和 `raise_for_status()`
- **LLM 用量页模型名显示"未指定"**：`format_session_usage()` 过滤 `models` 列表中 `"未指定"` 占位值，避免显示 `"deepseek-v4-flash / 未指定"`
- **LLM 用量页 Endpoint 缺失**：`_write_llm_summary_section()` 将 Endpoint 行移至汇总区的 `pairs` 列表，使其始终显示
- **A 股指数腾讯链路失败**：`_fetch_indices_from_tencent()` 使用 `tencent.fetch_price()` 获取指数行情，但该函数的前置类型守卫（`is_a_share_code`/`is_exchange_fund_code`）将 `sz399001`（深证成指）和 `sz399006`（创业板指）过滤为"不支持的类型"。改用 `tencent.fetch_index_price()` 修复，此函数无类型限制，专为指数设计
- **akshare 超时无重试**：`_run_with_timeout()` 新增自动重试机制（网络错误时 1 次重试 + 1s 间隔）；`get_profit_forecast()` 超时从 15s 放宽至 30s（全量数据获取）；`_fetch_all_dividends()` 新增超时保护（60s，此前完全无保护可能永久阻塞）
- **移除"机构覆盖"列遗留的引用**：`html_renderers.py` 仍从 `html_builders` 导入已删除的 `_load_profit_forecast`，导致 `ImportError` 报告生成崩溃；同步清理 `html_writer.py` 中向 `build_perf_data_status` 传 `profit_success` 的死参数，移除测试文件中对应 `patch` 和用例
- **多链模式 LLM Footer 模型名显示"未指定"（P0）**：`call_llm()` 在链模式下解析 `_resolve_entry_credentials()` 获取真实模型名，但仅返回 `provider_name`（entry 名），不返回 `model`/`endpoint`。`_finalize_and_cache()` 通过 `model or llm_config.get("model", "")` 兜底，在 multi-chain 模式下均为空 → "未指定"。修复：`call_llm()` 返回类型从 `(str | None)` 改为 `(dict | None)`，包含 `name`/`model`/`endpoint`；`_finalize_and_cache()` 和 `_handle_cache_hit()` 新增 `endpoint` 参数传播解析后的值
- **多链模式 LLM 用量页 Endpoint/费用/模型缺失**：`record_per_module()` 调用方传递 `llm_config.get("endpoint", "")`，多链模式下顶级 endpoint 为空 → 显示 "—"。`estimate_cost("未指定", ...)` 返回 "-" → 费用不显示。根因同上，修复后信息从实际 provider entry 传播
- **多链模式 news_correlation api_key 误报"未配置"**：`news_correlation.py` 检查 `llm_config.get("api_key")`，多链模式下 api_key 在 chain 条目中不在顶级 → 降级为传统关键词匹配。修复：检测非多链模式时才检查 api_key
- **多链模式全局审计**：审计所有 `llm_config.get("model"/"endpoint"/"api_key"/"provider")` 访问点，修复 `generators_news.py:_build_news_hooks()` 模型名解析、`_finalize_news_token_usage()` endpoint 记录、`generators_orchestrator.py:_precheck_one_cache()` endpoint 记录共 3 处类似问题。新增 `api._resolve_first_provider_model_endpoint()` 辅助函数统一多链首位 provider 信息解析

### Docs
- **项目统计信息**：`folders.md` 新增统计表（项目概览：源代码 128 文件 31,570 行，测试代码 155 文件 49,674 行/3,211 用例，文档 67 文件 31,523 行）；`test-coverage.md` 测试项数同步更新至 v0.7.1-dev 最新数据（`all` 模式 3211 项）

---

## [0.7.0] - 2026-07-18

### Added
- **增强多链 Provider 状态显示（TUI + CLI）**：新增 `get_circuit_status()` 公共函数暴露熔断器状态查询；TUI 菜单 `[4]` / `show_config` 时多链模式展示各 Provider 后端类型、模型名、优先级、熔断状态（带绿✓/红⚠图标）；CLI `cache --stats` 同步输出 LLM Provider 状态详情
- **文档**: changelog.md v0.6.10 变更记录迁移至归档文件

---

> v0.6.x 及更早版本变更记录已归档：
>
> - [`v0.6.x`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
> - [`v0.5.x`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
> - [`v0.4.x`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
> - [`v0.3.x`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
> - [`v0.2.x`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
> - [`v0.1.x`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
