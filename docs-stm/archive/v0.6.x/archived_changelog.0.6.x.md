# 变更日志归档 — v0.6.x

> 归档时间：2026-07-18
> 原始文件：docs-stm/managements/changelog.md
> 涵盖版本：v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）共 11 个版本

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.6.0] - 2026-07-15

### Fixed

- **管理文档清理**：补齐版本头（llm-technical.md、review-findings.md、test-coverage.md、folders.md），plan.md 移除字母跳跃历史注释，review-findings.md P3 重新连续编号（P3-2~P3-9→P3-1~P3-5），changelog.md 去重
- **faq.md 行号偏差**：`logger.py` 控制台级别修改行号 48→82（实际代码行）
- **how-to-test-my-code.md 历史注脚**：移除"基于 v0.5.7 版本撰写"过时说明

### Docs

- **文档版本号统一升至 v0.6.0**：constants.py、pyproject.toml、README.md、7 份管理文档、how-to-test-my-code.md

## [0.6.1] - 2026-07-16

> P1 共享层提取 S8~S11 + technical.md 全面重组

### Added
- **cache/operations.py** — 缓存操作共享层，包含：
  - 数据结构：`CacheUpdateResult`、`PositionCacheResult`、`CacheStats`
  - 内部线程池 `_get_pool()`（替代 handlers_cache._POOL）
  - `update_basic_cache()` — 基金 + 公共缓存（盈利预测/资金流向/行业/分红）并行刷新
  - `update_position_cache()` — 持仓价格 + 指数并行获取
  - `cleanup_cache()` — 过期清理
  - `get_cache_stats()` — 三目录统计（data/cache + snapshots + state）

### Changed
- **handlers_cache.py** — 246 行（原 457 行），-46%
  - 业务逻辑全部迁移至 operations.py
  - `_POOL` / `_get_pool()` 删除（operations 池唯一存在）
  - 保留 TUI 外壳：文件选择、结果格式化、`_cmd_*` 委托
- **test_handlers_cache.py** — 导入路径切至 `cache.operations`
- **test_handlers.py** — 移除已删除函数的旧测试（`_process_llm_news_futures`, `_compute_early_warnings`）
- **`_sector_flow_hint()`** — 从 handlers_cache 移除，统一使用 operations 版本
- **technical.md** — 全面重组结构，按「总体架构→概要设计→逐层详细设计→架构约束→附录」分层展开：
  - §1.4 新增概要设计章节（核心架构决策自原 §2 移入）
  - §3.6 新增缓存操作共享层设计（operations.py 数据结构/接口/线程池）
  - §4.2 新增报告编排器设计（orchestrator 三种路径/ProgressReporter）
  - §6.5/§6.6 展开代码类型判定和 HTTP 客户端统一设计
  - 附录 D/E 新增降级层级阈值定义和线程池分布
  - 清除所有历史痕迹和用户文档交叉引用

### Removed
- `handlers_cache._POOL` + `_get_pool()` — 完成去池，operations 池唯一
- `handlers_cache._refresh_industry_cache`, `_refresh_dividend_cache`, `_refresh_profit_forecast_cache`, `_refresh_sector_flow_cache`, `_refresh_common_caches`, `_fetch_prices_and_indices` — 全量迁移

## [0.6.2] - 2026-07-17

> CLI 命令行模式（P2）全部 8 轮完成

### Added
- **cli.py** — CLI 入口，argparse（report/cache 子命令） + config 覆写 + 退出码硬化的完整实现
- **report/cli_progress.py** — CliProgressReporter（常规→logging，verbose→stderr 彩色输出）
- **logger.py** — `log_app_boundary()` 记录启动/关闭事件（含版本号、运行模式、机器 IP）
- **docs-stm/manuals/how-to-schedule.md** — 定时任务配置指南（Windows schtasks / Linux cron）

### Changed
- **report/progress.py** — ProgressReporter 基类新增 `print_timing_summary()` 空壳
- **plan.md** — P3-I（CLI 模式）移入已完成区
- **folders.md** — 同步新增 CLI 相关 6 个文件条目
- **conftest.py** — 注册 `unit_cli` marker
- **cli-mode-iteration-plan.md / cli-mode-technical-design.md** — 归档至 `docs-stm/archive/v0.6.x/cli-mode/`

### Removed
- **完全移除智能预警（early_warning）模块** — 经 P4-1 评估确认两个维度均不可靠：行业资金流向 0% 成功率（废弃），新闻情绪聚合因 str/dict 类型 Bug 恒空且 LLM 成本收益比不佳。删除 `report/early_warning.py`、`test_early_warning.py`、`test_early_warning_edge.py`，清理 orchestrator/html_writer/excel_generator/registry/config 中全部引用及所有测试

## [0.6.3] - 2026-07-17

> 完全移除智能预警（early_warning）模块 + 全量文档同步清理

### Added
- **新闻关联质量优化（4 项 + 1 项）**：
  - **关键词精准度** — `_extract_terms()` 去除双字滑动窗口噪声，只保留完整中文词组，大幅减少"嘉实""产业"等通用片段导致的假阳性匹配
  - **行业/概念阈值** — 行业/概念类轻量级关键词需要至少 2 个命中才计为关联，避免单个泛词（如"电力"）关联不相关新闻
  - **LLM 分析条数可配置** — 新增 `llm_settings.json` 配置项 `news_correlation_top_n`（默认 30），控制送 LLM 分析的新闻条数
  - **跨源标题去重** — `_dedup_by_title()` 基于 `difflib.SequenceMatcher` 做标准化标题模糊去重，消除同一新闻在不同源用不同 URL 导致的重复
  - **底部标注 LLM 条数** — 新闻页签 footer 改为"其中 LLM 关联分析 N 条"，不再仅显示"含 LLM 智能关联分析"

### Changed
- **news_correlation `_build_news_footer`** — 参数由 `has_llm: bool` 改为 `llm_count: int`，精确显示分析条数
- **全量文档同步** — 移除智能预警模块后，核对所有管理文档/用户文档/源码注释的模块数（18→17）、编号（LLM 12→15→11→14，历史 16→17→15→16）、引用描述（新闻与预警→新闻），清除历史痕迹

### Removed
- **完全移除智能预警（early_warning）模块** — 删除 `report/early_warning.py`、`test_early_warning.py`、`test_early_warning_edge.py`，清理 orchestrator/html_writer/excel_generator/registry/config 中全部引用及所有测试

### Fixed
- **内部路径隔离** — `_config_defaults.py`、`logger.py`、`handlers_config.py` 统一使用 `PROJECT_ROOT`（`constants.py`）作为基准路径，消除 CWD 依赖。解决从非项目根目录运行时 `src/data/`、`src/logs/` 等目录误创建的问题
- **回撤图 Y 轴截断** — `drawSimpleChart` 中 `yMin = Math.max(0, globalMin - pad)` 强制下限 ≥0，导致全部负值回撤数据不可见、指数回撤线被裁剪。移除 `Math.max(0, ...)` 修复
- **回撤区持仓名单分行** — `report_template.html` 中 Section 13 持仓列表由内联拼接改为逐行显示，与 Section 12 保持一致

## [0.6.4] - 2026-07-17

> 全量架构约束整改（P1+P2+P3 共 27 项）+ 定价模块懒加载 + 缓存共享测试覆盖

### Fixed
- **全量架构约束整改** — 完成 review-findings.md 中 P1(7项)+P2(11项)+P3(7+2项) 共 27 项修复：
  - **C6 Provider Chain 必经**（P1-1~P1-3, P2-1~P2-2）：编排器/基金风格分析/新闻关联/缓存层 5 处直调 provider 改为通过 fetcher 层转发，消除绕过熔断器和 fallback 的入口
  - **C7 报告序号不可硬编码**（P1-4~P1-7）：B 系列 4 个 sheet（基金经理/重合度/集中度/风格）标题序号从硬编码 13-16 改为 `get_report_section_number()` 动态获取
  - **C3 缓存原子写入**（P2-3~P2-4）：`init_config()` 和 `_ensure_llm_settings_file()` 首次写入改用 `tempfile.mkstemp + os.replace` 原子写入模式
  - **C8 日志统一**（P2-5~P2-9）：LLM 模块 3 处 + report 2 处 `print()` 替换为 `logger`
  - **C14 渲染期全局变量**（P2-10）：`timing_records` 从模块级可变列表改为 ProgressReporter 实例级属性
  - **C1 代码类型判定中心化**（P2-11+P3-7）：`llm/prompts.py` 硬编码国家映射改为 `code_utils` 函数；`news_keywords.py` 手动 ETF/联接判定改为 `is_etf_by_name()`/`is_index_link_by_name()`
  - **死代码/命名清理**（P3-1~P3-5）：重命名 `write_news_and_early_warning`→`write_news_sheet`；删除 `_reset_news_correlation_result`、2 处 `_ext_memo_clear`；`ws13/14/15/16`→`ws_mgr/ws_overlap/ws_conc/ws_style`
  - **C5 HTTP 客户端统一**（P3-6）：4 个 LLM 模块的 `import httpx` 移至 `TYPE_CHECKING` 块
  - **P3-8 定价懒加载**：`pricing.py` 模块级 `reload_pricing()` 调用改为首次 `estimate_cost()` 时惰性加载，消除启动阶段非必要文件 IO
  - **P3-12 缓存共享测试**：`test_fund_style_analysis.py` 新增 `TestExtendedCacheSharing`，验证 `_push2_extended` 与 `_tencent_extended` 共享 `extended_{code}` 缓存 key
- **C14 修复补丁**：`TuiProgressReporter.__init__` 遗漏 `super().__init__()` 调用，导致 `_timing_records` 未初始化，`print_timing_summary()` 运行时抛出 AttributeError

## [0.6.5] - 2026-07-17

> LLM 关联分析情绪着色 — [利好]红色 / [利空]绿色

### Added
- **LLM 关联分析情绪着色** — Excel 和 HTML 报告对 `[利好]` 标记设为红色（#CC0000）、`[利空]` 标记设为绿色（#009900），中性/无标记保持默认黑色。新增 `_colorize_llm_cell`（Excel）和 `sentiment_colorize` Jinja2 过滤器（HTML）

## [0.6.6] - 2026-07-17

> 新闻去重增强 — 子串包含匹配跨源适用

### Fixed
- **新闻去重增强** — `_dedup_by_title` 新增子串包含规则：标准化后较短标题（≥10 字）完全包含于另一条即判定重复。覆盖两条场景：同源快讯版 vs 全文版（苹果 iPad mini）、跨源同一事件（中际旭创成交额跨东方财富/华尔街见闻）

### Changed
- **folders.md 同步** — 补充版本迭代中遗漏的文件：`src/python/__init__.py`、`src/python/report/orchestrator.py`、`src/test/test_orchestrator.py`；`docs-stm/plan/` 目录已空，移除已归档文件条目；`docs-stm/archive/v0.6.x/` 新增 `cli-mode/` 子目录条目

---

## [0.6.7] - 2026-07-18

> 31 项测试修复 + extract-test-failures 脚本 + 文档审计 + 多 Provider 初版 + 设计文件归档

### Added

- **脚本**: `scripts/extract-test-failures.py` — 从 pytest-html 报告中快速提取失败/错误测试用例，支持 `--summary` / `--json` 输出
- **调试工具**: `plan.md` 多 LLM Provider 链式服务标记为 **P1-T01**，优先级 P1

### Fixed

- **测试修复（31 项）**:
  - 8 个 LLM Error：移除 `TestEnhanceNewsCorrelation` / `TestEnhanceNewsCorrelationGranularCache` 对 `skeleton.httpx.Client` 的 mock（`httpx` 在 TYPE_CHECKING 下导入，运行时属性不存在）
  - 3 个 `test_fund_style_analysis`：修正 `_push2_extended` mock 字段名（`market_cap` → `f20`）和 Tencent 市值单位（亿→元换算）
  - 2 个 `test_handlers_cache`：mock 路径从旧 `providers.akshare_extras` 更新为 `fetcher.akshare`
  - 2 个 `test_handlers`：同上，mock 路径同步更新
  - 5 个 `test_news_correlation`：`aggregate_news` mock 路径从 `providers.news_aggregator` 更新为 `fetcher.news`
  - 7 个 `TestPrintTimingSummary`：`print_timing_summary()` 注入模块级 `_timing_records` 后清空
  - 4 个页签/导航数量断言：同步 `_REPORT_SECTION_DEFAULT` 新增的 `portfolio_history`/`drawdown_analysis` 模块
  - 1 个 `test_no_prefix_code_is_other`：测试代码从 `600900` 改为 `900900`（`60` 开头被 `is_a_share_code` 识别为 A 股）
  - 1 个 `test_fund_style_analysis` 中 `delete_by_prefix` → `clear_by_prefix`（前者不存在）
- **路径绝对化后遗症修复**: `test_config.py` / `test_config_atomic_edge.py` / `test_config_firstrun_edge.py` / `test_security_edge.py` 中 9 处路径断言适配绝对路径
- **`_extract_model_from_cached` 恢复**: Gemini 编辑期间被误删的函数定义已恢复

### Changed

- **`tui_handlers.py`**: `print_timing_summary()` 在调用 reporter 后清空 `_timing_records`，避免测试间污染
- **管理文档审计**: `folders.md`、`technical.md`、`llm-technical.md`、`requirements.md` 同步最新架构状态（proxy_preferred 后处理修正、模块列表对齐）
- **用户文档修正**:
  - `how-to-config.md` / `faq.md`: `report_section_order` 默认模块数 18→17，页签编号 `(1~18)`→`(1~17)`
  - `how-to-use-registry.md`: `config/_defaults.py`→`_config_defaults.py`
  - `how-to-config-llm.md`: 新增 Gemini provider 配置示例
  - `faq.md`: 补充多 Provider 链式服务问答，替换过时"不支持多 Key"内容
  - `how-to-config.md` / `faq.md`: 补充 `llm_providers.json` 多 Provider 配置说明
- **设计文件归档**: `docs-stm/plan/` → `docs-stm/archive/v0.6.x/llm-multi-provider/` — 已完成的多 LLM Provider 链式服务设计文件更新状态后归档
- **版本计划/审查记录归档**: `plan.md` 和 `review-findings.md` 的 v0.6.x 内容迁移合并至归档文件，重置为 v0.7.0-dev

---

## [0.6.8] - 2026-07-18

> 多 LLM Provider 链式服务（Phase 0 — 数据模型），R1 完成

### Added

- **配置**: `data/config/llm_providers.json` — LLM 多 Provider 配置文件模板
- **配置解析**: `_load_llm_providers()` / `_parse_providers_list()` / `_validate_provider_entry()` — llm_providers.json 解析与校验（`_core.py`）
- **测试**: `test_config_llm_multi.py`（20 用例） + `test_config_llm_multi_edge.py`（7 用例）

### Changed

- **`_config_defaults.py`**: 从 `_PATH_KEYS` 和 `_DEFAULT_CONFIG` 中移除 `llm_key_file`
- **`config.json` 模板**: 不再包含 `llm_key_file` 字段
- **`_core.py`**: `_load_llm_providers()` 增加根元素类型校验（非 dict 返回 None）
- **`conftest.py`**: 注册 `unit_config_edge` 标记
- **`test_config.py`**: 同步清理 `_PATH_KEYS_IN_TEMPLATE` 中的 `llm_key_file`
- **`folders.md`**: 同步新文件列表和标记描述

### Docs

- **管理/用户文档审计**: `folders.md`、`technical.md`、`llm-technical.md`、`requirements.md`、`how-to-config.md`、`faq.md`、`how-to-config-llm.md`、`how-to-use-registry.md` 同步最新架构状态（proxy_preferred 后处理修正、模块列表对齐、Gemini 示例、多 Provider 配置说明等）
- **审查记录清理**: `review-findings.md` 移除已清零的约束汇总表，重置为 v0.6.8-dev
- **计划文档清理**: `plan.md` 移除已完成的 P1-T01，重置为 v0.6.8-dev
- **版本归档**: `plan.md`、`review-findings.md`、`changelog.md` 的 v0.6.x 内容迁移至 `archive/v0.6.x/` 对应归档文件；已完成的设计文件从 `docs-stm/plan/` 移入 `archive/v0.6.x/llm-multi-provider/`

---

## [0.6.9] - 2026-07-18

> 修复全量测试 7 项失败 + TUI 多 LLM Provider 链式服务状态检测 + Windows 并发竞态

### Fixed

- **测试修复（7 项）**:
  - `test_template_equals_default_config`: `_PATH_KEYS_IN_TEMPLATE` 补全 `llm_key_file`/`llm_providers_file`
  - `TestMalformedJson` ×4: mock 目标 `_LLM_PROVIDERS_FILE` → `_get_llm_providers_path`（模块级常量已改为函数）
  - `test_config_api_key_not_in_log`: mock 目标 `_LLM_KEY_FILE` → `_get_llm_key_path`（同上）
  - `test_concurrent_init_config_no_crash`: Windows 上 `os.replace` 并发 PermissionError 未处理，导致双线程 `init_config()` 竞态崩溃
- **`_core.py` 生产代码**: `init_config()` 增加 `PermissionError` 捕获 + 双检查回退（文件已存在则正常返回），避免 Windows 并发场景下的崩溃

### Changed

- **TUI LLM 状态检测**（`tui_menu.py`）: `_show_llm_config_status()` 和首次运行引导兼容 `credentials_ref` 多链模式（`_provider_list`），不再仅检测 `api_key`。多链模式下显示 "多链服务: deepseek-main + gemini-fallback (2 provider)"
- **提示文字更新**:
  - `handlers_config.py`: LLM 未配置提示改为提及 `llm_key.json` 或 `llm_providers.json`
  - `report/llm_content.py`: 占位文字同步更新


---

## [0.6.10] - 2026-07-18

> 用户文档系统梳理 + 归档排序统一 + 技术设计文档重构 + 多链 dict 崩溃修复

### Changed
- **文档**: technical.md §5 LLM 集成层从 73 行简述重构为完整概要设计（5 子节），llm-technical.md 重组章节结构（§5 拆分为 3 子节、§14 内容归并、新增附录 A-C）
- **文档**: technical.md + llm-technical.md 技术债清理（删除 P1/旧格式等历史痕迹）
- **文档**: datasource.md 从 24 行极简表格扩展为完整参考手册（缓存前缀、数据质量说明、路由说明、常见问题）
- **文档**: how-to-start.md 新增 CLI 命令参考（全局参数 + report/cache 子命令完整参数表）
- **文档**: how-to-config-llm.md 新增 HTTP 代理配置章节
- **文档**: how-to-schedule.md 新增 "报告输出路径" 章节、完善 CLI 引用标注
- **文档**: faq.md 新增数据源代理配置问答
- **文档**: how-to-use-registry.md / how-to-test-my-code.md 补充指向 technical.md/requirements.md 的架构背景引用
- **文档**: plan.md / review-findings.md 归档版本列表统一为降序排列（从新到旧）
- **文档**: how-to-schedule.md 常用命令表补充 `cache --update position` 行
- **文档**: testplan.md 单元子组计数 8→9，对齐实际注册数
- **代码**: 提取 `get_llm_module_failure_reason()` 统一函数，消除 3 处重复的 dict 格式兼容判断；修复 `build_llm_module_info()` 对多链 dict 格式的 `TypeError: unhashable type: 'dict'` 崩溃

### Fixed
- **测试**: conftest.py `_KNOWN_MARKERS` 补入 `unit_cli`（已在 pytest_configure 注册但缺少校验项）
