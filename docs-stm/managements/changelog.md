# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.9-dev] - 开发中（未发布）

### 行动建议章节默认开启 + 菜单 P 可视化开关

- **默认值调整**：`enable_action` 由默认关闭改为**默认开启**——`_config_defaults._DEFAULT_CONFIG["enable_action"]=True`；`get_config()` 合并逻辑以默认值打底，现有用户 config.json 缺失该键时自动补为开启（显式 `false` 的用户保持关闭）。访问器 `is_enable_action()` 缺失时返回 True，日志提示「缺少 enable_action，使用默认值 true」。
- **菜单 P 新增开关**：TUI 菜单 `[P] 配置报告可选章节` 面板新增第 5 项「行动建议（再平衡信号/交易纪律/调仓建议/收益归因）」，与既有 4 个章节组一致地交互切换；LLM 分析章节提示顺延为第 6 项。菜单 P 主菜单 label 同步加入「行动建议」。
- **行为影响**：开启后 E/B/L 报告均输出行动建议章（number=17，type=action）；关闭时章节隐藏且智囊团深度复盘隐藏「行动摘要」子块，剩余章节自动连续编号。
- **文档同步**：how-to-config.md（默认值表/章节可见性表/菜单归属/章节对照 5 处）、how-to-menu.md（主菜单 label/脚注/章节说明/菜单 P 详解 4 处）、faq.md、how-to-use-registry.md、requirements.md、reports-instruction.md、technical.md 全文「默认关」→「默认开，菜单 P 可切换」。
- **测试**：`TestIsEnableAction` 新增 `test_default_config_says_enabled`（断言 `_DEFAULT_CONFIG["enable_action"]` 为 True）；`test_default_true_when_missing` 保持缺失→True；test_registry/test_action_html/test_report_chapter_consistency 注释同步。
- **门禁**：dev-verify 1846 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 事实校验两处误修正修复（rf-239）

- **缺陷 1：名称指代主体定位平局误路由**。真实报告「止盈纪律」句「建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%」中，171.23% 被误修正为 70.2%（601398 工商银行收益率）——`_locate_subject_code` 名称分支用起点距离 `abs(idx-anchor)`，建设银行(idx=0)与工商银行(idx=16)距 anchor=8 平局，先迭代者（工商银行）胜出，把 601939 的**正确** 171.23% 判错并改写。修复：名称分支改用**最近边距离** `min(abs(idx-anchor), abs(idx+len(name)-anchor))`，与代码分支一致，紧邻数值的名称唯一胜出。
- **缺陷 2：风险警戒阈值误修正**。同句「设立止损线：当前亏损-11.80%，已接近回调20%的警戒区域」中，「回调20%」是止损警戒阈值而非收益率声称（实际 -11.80% 同句另述且正确），却被误修正为 -11.8%（159222）。修复：`_is_trim_target_context` 增加警戒阈值检测——新增 `_WARNING_THRESHOLD_KEYWORDS=("警戒",)`，数值前后更宽窗口（-25/+8）内出现警戒词即判定为风控阈值，跳过收益率比较。
- **测试**：新增 `TestNameSubjectNearestEdge`（3 用例）+ `TestWarningThresholdContext`（3 用例）回归测试，修复前均失败；fact_checker 单文件 109 通过；完整合成稿+真实持仓端到端复现 corrections 由 2 处降为 0。
- **门禁**：fact_checker 单文件 109 passed（未跑全量，用户要求最小验证）。

---

## [0.10.8] - 2026-08-06

### 超限文件拆分：报告生成 / HTML 写入 / 量化指标 / 报告编排 四个 >800 行文件 facade 化

- **动机**：自审核查（review-findings rf-234/rf-235/rf-236/rf-237）发现四源文件超过 800 行硬性上限——`report/_report_generation.py`（1018）、`report/html_writer.py`（934）、`analysis/metrics.py`（880）、`report/orchestrator.py`（822）。大量测试直接 `patch` 原模块路径（如 `html_writer._ENV`、`_report_generation._spawn_health_checks`、`orchestrator._fetch_valuation_for_code`），整体搬迁会破坏 mock 接线。
- **方案**：facade 聚合门面拆分——函数体物理移动到语义子模块，原模块保留关键入口并 re-export 全部符号，所有外部引用（生产代码 + 测试）零改动。
  - `report/_report_generation.py`（686）：后台健康检查→`_report_health.py`（`_spawn_health_checks`/`_collect_health_checks`）、轻量行情/演进与快照差异注入/完整性校验/both 明细子集→`_report_helpers.py`（`_compute_details`/`_inject_evolution_data`/`_inject_snapshot_diff_data`/`_validate_prep_completeness`/`_validate_pipeline_snapshot`/`_both_action_holdings_details`）、full 路径全量量化指标装配→`_full_risk_metrics.py`（`_prepare_full_risk_metrics`）、Chart.js 数据集构建→`_chart_dataset_factory.py`（`_build_chart_datasets_for_report`）。门面保留 both/full 双路径生成编排（`_generate_report_both`/`_generate_report_full`/`_generate_full_html_report`/`_generate_full_excel_report`），确保 `patch("_report_generation._spawn_health_checks")` 等接线继续生效。
  - `report/html_writer.py`（660）：章节可见性/目录分组导航→`html_writer_nav.py`（`_compute_section_visibility`/`_build_section_nav_groups`/`_LLM_SUPPORTED_SECTIONS`）、数据契约展示映射→`html_writer_display.py`（`_build_flow_display`/`_build_temperature_display`/`_attach_valuation_to_penetration`）、Chart.js JS 资产复制→`html_writer_assets.py`（`_copy_js_assets`）。门面保留 `write_html_report`/`_render_template` 及全部顶部 import（`_ENV`/`build_*_data_status`），mock 路径不变。
  - `analysis/metrics.py`（225）：收益/清理类指标→`metrics_returns.py`（`compute_daily_returns`/`sanitize_metric`/`sharpe_ratio`/`calmar_ratio`/`max_drawdown_pct` 等 10 函数）、风险/持仓类指标→`metrics_risk.py`（`hhi`/`win_rate`/`risk_contribution`/`portfolio_beta` 等 8 函数）。门面保留 `compute_all_metrics` 聚合入口 + `__all__` + 4 常量 + `_math_utils` 符号再导出（测试引用 `_t_critical_95`/`_t_cdf`）；子模块维持 analysis 层单向依赖约束（不导入 report/）。
  - `report/orchestrator.py`（442）：风格因子/行业 Beta 计算族→`_report_factor_metrics.py`（持仓 K 线路由 `_fetch_holding_bars` + 因子回归 `compute_factor_exposure_data` + 行业 Beta `compute_industry_beta_data`）、市场温度/持仓相关性→`_report_aux_metrics.py`（`compute_market_temperature_data`/`compute_correlation_data`）。门面保留 `generate_report`/`prepare_report_data`/`compute_valuation_data`/`_fetch_valuation_for_code`——估值族因测试 `patch("orchestrator._fetch_valuation_for_code")` 依赖门面命名空间解析，留在门面（docstring 注明原因），确保 patch 接线继续生效。
  - `llm/generators_orchestrator.py`（698，rf-238）：facade 聚合门面拆分——新闻关联责任单元（模块级结果缓存 `_store_news_correlation_result`/`get_news_correlation_result`、闭包 `_make_news_correlation_closure`、安全直调 `run_news_correlation_safe`）→`_llm_news_correlation.py`（161）。门面保留缓存预检（`_compute_module_cache_info`/`_precheck_*`）、worker 分发（`_dispatch_llm_workers`/`_build_module_fns`）与主编排入口 `generate_all_llm`，re-export 子模块符号，mock patch 接线零改动。
- **语义命名**：新子模块全部语义命名（metrics_returns/metrics_risk/html_writer_nav/html_writer_display/html_writer_assets/_report_health/_report_helpers/_full_risk_metrics/_chart_dataset_factory/_report_factor_metrics/_report_aux_metrics/_llm_news_correlation），无任务代号扩散到实现层；子模块 docstring 不含任务编号。
- **文档同步**：`folders.md` 目录树登记 12 个新文件（四文件拆分 11 个 + `_llm_news_correlation.py`）+ 项目统计表刷新（主程序 222→234 文件、55,823→56,189 行）；review-findings 五条已修复项（rf-234~238）迁入「已修复（摘要）」。
- **测试**：dev-verify 1846 passed；report 全量单测 1479 + metrics 94 通过；`test_valuation_temperature_wiring.py`/`test_pipeline_style_factor_regression.py`/`test_pipeline_smoke.py`/`test_cli*.py`/`test_cli_integration.py` 97 项通过。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 15 文件已格式化。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.7（2026-08-04 ~ 2026-08-05）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
