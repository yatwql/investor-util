# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.3.7] - 2026-07-12

### Fixed

- **文档双向校验修正**：`how-to-config.md` 中 `degradation.t4.stale_days` 统一为 14（代码默认值），市场时段缓存 TTL 表格改为按时段描述匹配代码实现。`how-to-use-registry.md` 公共 API 补全 6 个缺失函数、消费者清单修正并补全 10 个遗漏消费者、LLM 新增模块检查清单改为实际代码模式（`_MODULE_FNS` + `_compute_module_cache_info()`）、去除历史变更叙述纯当前状态描述。
- **`technical.md` 设计约束章节**：C9 注册点修正（`skeleton.py` → `generators_orchestrator.py`）、C12 移除 testplan.md 跨文档引用、C4/C14 参考来源列格式统一为锚点链接。
- **`technical.md` cache.py 陈旧引用**：Z6 重构后 8 处 `cache.py` → `cache/` 子包、`_read_cache()` → `_read_cache_data()` 同步更新。

---

## [Unreleased]

### Fixed

- **分红 API akshare 1.18.64 签名兼容**：`stock_history_dividend()` 新版不接受参数且返回全量聚合数据（列名从"每股股利"改为"年均股息"），改为一次拉取全量后按代码过滤，移除旧版逐股并发请求逻辑。
- **Tencent API 超时/网络错误自动重试**：`fetch_price()` 对 `TimeoutException`/`RequestError` 自动重试一次后再放弃，降低备用链路的偶发超时影响。
- **日志噪音压缩**：移除 `fetcher/chain.py` 和 `report/market_value.py` 中与 `cache.py` 重复的"缓存命中"DEBUG 日志。
- **TUI 主循环标题丢失**：`_print_header()` 从主循环前移至循环内调用，确保生成报告/刷新缓存等操作返回后，软件名称和版本号仍然显示在屏幕顶部。
- **测试文档 `--lf` 错误示例**：`how-to-test-my-code.md` 中原示例 `test_runner.py -- --lf` 实际因 argparse 不支持 `--` 透传而报错。改为直接调 `pytest -m` 复现标记表达式后组合 `--lf`，并补充 `test_runner.py` 与 `--lf` 的分工说明。

### Changed

- **缓存引擎 Strangler Fig 重构完成**：667 行的单体 `cache.py` 拆分为 `cache/` 子包（9 个文件 + services 子包），职责解耦为路径/IO/存取/TTL/统计/清理/组管理/持仓跟踪。过渡文件 `_legacy.py` 已删除。对外 API 保持完全兼容，`from cache import get/set/clear` 等不变。
- **T4 stale_days 配置收紧：14→7 天**：盈利预测/分红/风格等补充数据级不再容忍 2 周旧缓存。`config.json`、`data_status.py` 默认值、`how-to-config.md`、`requirements.md` 同步更新。

---

## [0.3.6] - 2026-07-11

### Fixed

- **check-test-markers.py 标记检查脚本 3 项自检缺陷**：
  1. `EXPECTED_DIR_MARKERS` 中键 `"llm"` 重复，Python dict 后键覆盖前键 → `unit/llm/` 下 3 个文件被误要求有 `scenario` 标记。改用完整二级路径 `"unit/llm"` / `"scenario/llm"` 消除歧义
  2. `_get_relative_dir()` 取 `parts[1]` 而非完整父路径，`unit/llm` 与 `scenario/llm` 不可区分。改用 `rel.parent` 返回全路径
  3. `KNOWN_MARKERS` 缺少 `integration_*` 系 6 个子标记；`DEPRECATED_MARKERS` 包含仍在活跃使用的 `integration`。补全标记集，清空废弃集
- 修复后全量 120 项测试标记合规性检查全部通过，0 违规。

- **缓存路径偏移导致"每次都是新增资产"**：`cache.py` 从 `src/cache.py` 重构移动到 `src/python/cache.py` 时，`_PROJECT_ROOT` 的 `dirname` 次数未同步更新（少了一层），导致缓存目录偏移到 `src/data/cache/`，`holdings_tracking.json` 每次都读不到，全部代码被误判为"新增"。修复：在 `constants.py` 用**标记文件查找法**（向上找 `pyproject.toml` / `.git`）替代 `dirname` 深度计数，`cache.py` 统一从此导入。清理了残留的 `src/data/cache/` 目录。

- **`_fetch_from_sina()` 死循环导致 xdist worker OOM crash**：新浪财经翻页后新增跨分类 URL 去重逻辑（`seen_urls`），但当全部条目均被去重命中时，`category_fetched` 永不增长且 `len(items) >= need` 永不触发 break，导致 `while` 死循环 → worker OOM kill。新增 stale-iteration guard：一轮无新增条目时 `break`。修复 2 项测试（`test_fetch_from_sina_returns_list` / `test_fetch_from_sina_dedup_by_url`），全量 2956/2956 通过。

- **新闻源翻页能力不足**：东方财富（单次上限 200）、华尔街见闻（硬编码 `min(num,100)`）、新浪财经（单页 50 条×只取第 1 页）三源实际获取数远低于 `build_news_data` 传入的 `per_source` 值，导致 `news_top_count=300` 时原始候选池不够。改为游标/多页循环翻页，各源现在可达 `per_source` 目标量。
- **修复 22 项预存测试失败**：R-178 分拆后 18 项 `html_writer` mock 路径未同步更新（`akshare_extras.*` → `html_renderers.*`，`html_writer.*` → `html_renderers.*`），修复 `test_api_status_trading` 缓存断言与 autouse fixture 冲突，修复 3 项 TUI ESC 序列 `side_effect` 不足 StopIteration 崩溃。全量 2956/2956 回归通过。
- **provider_registry.py 移除旧测试接口**：删除 `get_skip_set_copy()` / `get_skip_time_copy()` 两个标注"兼容旧测试接口"的方法，对应测试改用 `generate_status_report()` 验证熔断状态。

### Changed

- **R-206 excel_generator.py 拆分（692→98 行，-86%）**：按 7 轮迭代拆出 7 个专业模块（excel_module_loader/sheet_factory/market_data/content_sheets/news_warning/b_series/llm_usage）。excel_generator.py 从 12 函数/692 行精简为核心编排器 5 函数/98 行。`_process_b_module` 消除重合度/集中度/风格 3 模块的重复数据准备模板（~90 行→30 行）。更新 5 个测试文件的 import/mock 路径，零行为变更。全量 989 项报告单元测试通过。设计文档已归档至 `docs-stm/archive/refactor-excel-generator/`。

- **R-207 summary.py LLM 用量拆分（617→350 行，-43%）**：8 个 LLM 用量函数（`write_llm_usage_sheet`/`_init_llm_usage_sheet`/`_write_llm_summary_section`/`_write_module_table_header`/`_write_module_data_rows`/`_write_legend`/`_write_cache_stats_section`/`_set_column_widths`）迁出至 `summary_llm_usage.py`。summary.py 通过 re-export 保持向后兼容。3 个测试文件 import 路径同步更新。设计文档已归档至 `docs-stm/archive/refactor-summary-llm-usage/`。

- **akshare 依赖版本区间锁定**：`requirements.txt` 从 `==1.18.64` 改为 `>=1.16,<2.0`，允许非破坏性更新同时防止大版本兼容风险（R-199）。

- **technical.md 迭代历史痕迹清理**：移除 16 处 A 类（纯迭代记录）和 B 类（版本标记）历史痕迹，恢复为永恒技术设计文档。
- **how-to-config.md 版本标记清理**：移除 2 处 v0.2.xx 版本标记。
- **用户文档全局迭代/版本标记清理**：`reports-instruction.md`、`how-to-use-registry.md`、`how-to-config-llm.md` 共 6 处版本后缀/迭代名称（`B 迭代`/`C 迭代后`/`v0.2.15+`/`v0.2.29+`/`v0.2.30+`/`v0.2.85+`）替换或删除，用户文档不再出现具体迭代引用。
- **technical.md LLM 模块计数同步**：LLM 子模块从 `9` 修正为 `12`，模块职责表新增 `api_base.py` 和 `generators_news.py`。
- **how-to-use-registry.md 消费方表校正**：`generators.py` → `generators_orchestrator.py`，`market_value.py` → `market_value_sheet.py`，新增 `fund_overlap_sheet.py` 和 `fund_concentration_sheet.py`。新增 LLM 模块步骤增加 `generators_orchestrator.py` 调度注册环节。

### Docs

- **datasource-and-folders.md 目录树描述全面润色**：移除所有历史变更痕迹（如"从 xxx.py 拆分"）、迭代标记（D-7b/D-8）和生硬的三段式堆砌，统一改为自然的功能描述语句。涉及约 40 条文件/目录描述更新，涵盖 llm/、report/、test/ 等核心子目录。

- **代码库兼容性/死代码审计**：全局扫描 `src/python/` 中 config.json/llm_settings.json/缓存/API 响应的历史兼容代码，结论：代码库干净，仅 4 处微小负担，已处理其中 1 处（`get_skip_*_copy` 旧测试接口）。
- **配置 + 代码全局一致性检查**：config.json 17 键 / llm_settings.json 53 键 / registry 21 缓存 TTL 项 / 所有 `.py` 文件导入引用 — 无死键、无死文件、无冲突。

- **technical.md 组织修复**：补充 H2 间缺失 `---` 分隔线（功能模块详解 → LLM 客户端技术要点）；移除功能模块详解内部两处多余 `---` 分组线（B 系列、报告序号可配置前），与全文其他 H2 章节格式统一。
- **how-to-test-my-code.md 组织修复**：H4 多模式组合补 `🔷` 前缀（与其他 4 个子节一致）；目录树 `scenario_extreme/` 移入场景组（紧接 `scenario/` 后）；快速开始专项验证区新增 `--mode scenario_extreme` 示例。
- **how-to-test-my-code.md / technical.md 交叉核对**：faq.md 组织正常无需调整；how-to-test-my-code.md 4 项建议中实施 3 项（dev-verify 时序复查后确认正确，撤回）。
- **test-coverage.md 核对**：all=2972/unit=2665/scenario=269/edge=335，全部吻合无需修改。

- **technical.md 报告管线/依赖树/LLM 用量引用更新**：反映 R-206（7 个 excel_* 中间模块）和 R-207（summary_llm_usage.py）拆分后的新模块结构。Excel 管线从单行描述改为分步编排架构。`build_llm_usage_sheet`/`_write_cache_stats_section` 引用路径从 `summary.py` 更新至 `excel_llm_usage.py`/`summary_llm_usage.py`。
- **test-coverage.md 报告生成模块列表更新**：补充 R-206/R-207 新增的 8 个模块（excel_module_loader/sheet_factory/market_data/content_sheets/news_warning/b_series/llm_usage/summary_llm_usage）。
- **datasource-and-folders.md 目录树同步**：新增 `summary_llm_usage.py` 文件条目 + 2 个归档目录（refactor-excel-generator、refactor-summary-llm-usage）。`summary.py` 描述修正为"不含 LLM 用量"。
- **review-findings.md 全部清空**：24 项自审问题已全部修复/归档，当前无待修复问题。R-187（TUI Windows 12 测试跳过，平台限制已标记 `skipIf`）/R-199（akshare 版本区间锁定）/R-201（HTML 打印预览 Playwright 测试，低优先级暂不修复）已处理归档。
- **R-206/R-207 设计文档归档**：plan/ 下 2 份迭代设计文件迁至 `docs-stm/archive/refactor-excel-generator/` 和 `docs-stm/archive/refactor-summary-llm-usage/`。

---

## [0.3.5] - 2026-07-10

### Changed

- **R-200 scenario/regression/verify 三模式耗时优化**：
  - **Step 0 push2 API mock**：`conftest.py` 新增 `_mock_market_hours_api` autouse fixture，跳过东方财富 push2 网络请求，直接使用内置 fallback 判断市场时段，消除每测试类首次调用的 1-3s 网络开销
  - **B-2b 标记拆分 + 文件搬迁**：S0c（超多持仓）从 `scenario` 拆分为 `scenario_extreme`；`TestS0cLargeHoldings` + `TestScenarioExtreme` 统一迁至 `resilience/test_scenario_extreme.py`。scenario 模式从 21min 降至 321s（74% 降幅），scenario_extreme 8 项 ~56s
  - **B-2a（S0c 优化）降级为低优先级**：S0c 已移出 scenario，不再影响门禁
  - **D-4 dev-verify 新增**：`test_runner.py` 新增 `--mode dev-verify`，组合全部 unit 子模块并行 + 基础场景，约 2min 开发者快速验证
  - **C verify 子阶段（`--phased`）**：`test_runner.py` 新增 `--phased` 分阶段标志，verify 模式支持 Phase A（核心单元 unit_core/providers/fetcher ~30s）+ Phase B（场景 ~5min），前序失败跳过后续，减少合入验证的反馈等待时间

- **R-197 market_value.py 拆分**：`market_value.py` 从 711 行拆分为 `market_value.py`（计算层，~450 行）和 `market_value_sheet.py`（Excel 写入层，~230 行）。桥接导入已在 I-8 中完全移除，外部调用者（`excel_generator.py`）分别导入计算和写入模块。测试文件同步拆分为 `test_market_value.py`（128 项 compute 测试）和 `test_market_value_sheet.py`（31 项 write 测试）。

- **R-198 LLM 模块横向拆分（14 步迭代）**：`generators.py`（750 行）拆分为 `generators.py`（190 行，4 单例函数）+ `generators_orchestrator.py`（~340 行，编排/预检/线程池）+ `generators_news.py`（306 行，新闻 LLM 关联）。`api.py`（337 行，原 702 行）拆出 `api_base.py`（基础常量/重试/截断/失败追踪），移除 24 个基础设施 re-export，`__init__.py` 直链新模块。采用 Add→Re-export→Remove 三阶段过渡策略，mock 路径同步更新原则已验证。clean 增量：-949 行（拆分前 ~1452 行 → 拆分后 ~503 行跨 6 文件）。

### Docs

- **计划文档 v5 终版**：`r200_verify_mode_optimization.md` 同步迭代更新（已完成，归档至 `docs-stm/archive/test-verify-mode-optimization/`）
- **测试模式文档同步**：`how-to-test-my-code.md`、`testplan.md`、`datasource-and-folders.md` 更新 scenario_extreme 文件位置和 dev-verify 模式说明
- **review-findings.md R-200 → ✅**：已修复转归档

### Added

- **测试隔离 autouse fixture**：`conftest.py` 新增 `_isolate_sensitive_paths` autouse fixture，自动将 `_defaults._CONFIG_FILE` 和 `cache._CACHE_DIR` 重定向到 `tmp_path`，防止测试污染用户真实配置文件/缓存。配合 `_clear_config_cache()` 确保 `get_config()` 从临时路径读取后回退到默认值。
- **测试标记遗漏自动检查**：`conftest.py` 的 `pytest_collection_modifyitems` 新增标记遗漏检查，新测试文件若缺少 `pytestmark` 变量则发出 `PytestWarning` 提醒。`_KNOWN_MARKERS` 全集与 `pytest_configure` 注册的 31 个标记保持同步。

- **R-177 核心模块单元测试覆盖**：为 `llm/generators.py`、`llm/prompts.py`、`handlers_cache.py`、`handlers_report.py` 四个模块编写 97 个单元测试，覆盖 JSON 解析、提示词构建、缓存预检、报告编排等关键逻辑。测试 mock 路径修正、`_press_any_key` 阻塞问题修复等实战经验已沉淀。

- **DataSourceRegistry 数据源注册中心（Step A）**：`provider_registry.py` 新增 `DataSourceRegistry` 单例，统一管理熔断器（3 次失败 / 300s 冷却）、会话级缓存（OrderedDict O(1) 淘汰、2000 条阈值）、获取策略选择（`LIVE_FETCH`/`CACHE_ONLY`/`PLACEHOLDER`）及审计报告生成。双锁设计（`_provider_lock` + `_cache_lock`）保证并发安全。新增 45 项单元测试（`test_provider_registry.py` 37 + `test_phase_timeout.py` 8）。

- **`all_no_unit` 快捷测试模式**：`scripts/test_runner.py` 新增 `all_no_unit` 模式（`-m "not unit"`），排除单元测试运行其余全部场景/集成/边缘测试（306 项），方便快速验证非单元逻辑。

### Changed

- **`config.py` → `config/` 子包拆分（R-179）**：原单文件 817 行/30+ 模块导入的 `config.py` 拆分为 `_defaults.py`（默认配置 & 模板）、`_comments.py`（JSON 注释剥离）、`_core.py`（配置读写/校验/LLM 配置）三个独立子模块。`__init__.py` 统一导出，保持外部导入兼容。

- **Provider Chain 熔断架构升级**（三层熔断 + 冷却恢复 + batch 预检）：
  - 新增 `is_provider_chain_broken()` 全链熔断查询 API，batch 入口一次预检替换逐条重复判断
  - 新增熔断冷却恢复机制（`_PROVIDER_COOLDOWN_SECS=300`），冷却期满后放行试探请求，成功则恢复
  - `batch_fetch_industry_data` 入口预检：全链熔断时跳过批量获取，不调 API
  - `batch_fetch_industry_data` 重试预检：熔断未恢复时跳过 0.8s 等待+重试
  - 新增 13 项 edge 测试覆盖：`is_provider_chain_broken`（5 项）、冷却探针 4 态（4 项）、batch 预检（4 项）

- **数据降级策略选择器（Step B）**：`market_value.py` 使用 `DataSourceRegistry.get_effective_strategy()` 区分 CACHE_ONLY（非交易时段 / 链熔断）和 LIVE_FETCH（交易时段），通过 `classify_holdings()` 拆分为两组并发获取。新增 8 项 edge 测试（`test_market_value_strategy_edge.py`）。

- **Provider Chain 全局变量迁移至注册表（Step C）**：`chain.py` 移除 4 个旧全局熔断变量（`_PROVIDER_SKIP`、`_PROVIDER_SKIP_TIME`、`_PROVIDER_CONSECUTIVE_FAILURES`、`_PROVIDER_LOCK`），全面改用 `DataSourceRegistry` 熔断 API。`chain.py` 末尾新增 `get_registry().register_default_chains()` 模块级自动注册，确保 `get_chain()` 在生产环境返回有效 Provider 列表。旧测试模块全部同步更新。

- **_ext_memo 模块级缓存迁移至注册表（Step D）**：`eastmoney_industry.py`、`eastmoney_industry_rest.py`、`fund_style_analysis.py` 三模块的 `_ext_memo` 模块级字典替换为 `DataSourceRegistry.session_cache`，使用独立域名（`"industry"` / `"industry_rest"` / `"extended"`）。`_ext_memo_clear()` 保留为兼容包装。

- **tencent_style 显式注册（M-004）**：`fund_style_analysis.py` 模块级新增 `get_registry().register_provider("tencent_style", tier=4, timeout=15.0)`，消除 `record_failure` 隐式最低优先级注册行为。`_tencent_extended()` 在成功/异常时调用 `record_success`/`record_failure` 通知注册表。

- **集成审计报告（Step E）**：`report/data_status.py` 的 `DegradationTracker` 集成 `DataSourceRegistry.generate_status_report()`，在报告中输出数据源注册与熔断状态。TUI 的 `[!]` 降级提示信息包含策略来源（CACHE_ONLY / PLACEHOLDER）。

### Fixed

- **R-166 mypy 严格模式升级**：启用 `no_implicit_optional`、`warn_unused_ignores`、`check_untyped_defs` 三个严格标记，修复 77 处 mypy 错误（覆盖 24 文件）。mypy 零残留错误。
- **R-167 `_ext_memo` 会话级复用缓存推广**：`eastmoney_industry.py` 和 `eastmoney_industry_rest.py` 新增 `_ext_memo` 模块级字典缓存（C4 约束）。
- **R-161 TOCTOU 竞态**：`fetcher/chain.py` `_fetch_with_fallback` 锁合并为一次临界区
- **R-162 `_TRANSPORT_FAILURE` 类型污染**：`fetcher/chain.py` 哨兵改为纯 `object`
- **R-163 废弃 build-backend**：`pyproject.toml` 切换为 `setuptools.build_meta`
- **R-164 模板一致性防护**：`test_config.py` 新增 `TestDefaultConfigTemplateConsistency` 测试
- **R-165 Ruff 规则集升级**：`["E", "F", "W", "I"]` → `["E", "F", "W", "I", "SIM", "UP", "ARG", "PERF"]`
- **R-168 配置 mtime+size 双因子缓存**：`config.py` 新增文件大小校验
- **R-169 429 API 限速差异化提示**：`chain.py` 区分 429/rate limit 单独日志
- **R-170 新闻流水线集成测试修复**：4 个测试 mock 路径修正
- **R-171 CI/CD 流水线配置**：`.github/workflows/ci.yml`，三档门禁 + 多版本矩阵 + mypy/Ruff
- **R-172 HTTP 异步客户端支持**：`http_client.py` 新增 `make_async_http_client()`
- **R-173 ThreadPoolExecutor 集中管理（handlers_report）**：模块级共享 `_POOL`
- **R-174 配置校验去重**：`config.py` 新增 `_section()` 辅助函数
- **R-175 colorama 降级为可选依赖**：`try/except ImportError` 保护
- **R-176 docstring 误放**：`llm/api.py` 独立字符串改为注释
- **R-178 文件导览注释**：`html_writer.py` 顶部 TOC
- **R-181 ThreadPoolExecutor 集中管理（handlers_cache）**：模块级共享 `_POOL`
- **R-182 TODO 残留清理**：`fund_style_analysis.py` 删除 TODO
- **R-183 文档引用索引表**：`plan.md` 新增 R-160~R-176 索引表
- **R-184 `_get_industry_avg_pe()` 空实现 → 完整实现**：接入 push2 API 三级降级，10 项测试覆盖
- **R-185 预测年份硬编码 → 动态计算**：穿透表列名跨年自动更新
- **R-186 定价双源消除 — constants.py 为单一来源**
- **R-188 eastmoney_industry 局部熔断器迁移至 DataSourceRegistry**：6 个全局变量 + 2 个辅助函数删除
- **R-189 `_fetch_cached_only()` → 公开 `fetch_cached_only()`**
- **R-190 `_TRANSPORT_FAILURE` 哨兵去重**：chain.py 删除局部定义，统一 import
- **R-191 test_eviction_order 修复 + fetch_or_cached/fetch_cached_only 测试覆盖**
- **R-192 verify 测试 3 项 price_type 断言同步**：`"--"` → `"暂无行情"`
- **R-193 unit 测试 3 项 _check_network_available 断言同步**：文案对齐当前实现

- **tui_menu.py `_YELLOW` 缺失导致 ImportError**：`else` 分支补定义 `_YELLOW`
- **TUI 全颜色统一**：`handlers_cache/handlers_config/handlers_report` 统一 ANSI 颜色常量
- **`llm_settings.json` JSON 注释清理**：移除 `//` 和 `/* */` 注释
- **集成测试 mock 返回值修复**：`test_html_generation_ok_llm_crash` 从 `{}` 修正为 `([], False)`
- **R-203 `register_default_chains()` 未在生产环境调用（P0）**：`chain.py` 末尾添加自动注册
- **Provider Chain 日志增加代码上下文**：日志输出末尾追加 `[{code}]` 标签
- **test_runner.py verify 模式描述时间修正**：`"并行~1min"` → `"并行~5min"`

- **R-204 html_renderers.py fund_hold 三函数会话缓存**：`_render_overlap_matrix`/`_render_concentration`/`_render_style_analysis` 通过 `DataSourceRegistry.session_cache`（域名 `"fund_hold"`）消除同报告生成内对 `fetch_fund_holdings` 的重复文件缓存读取，~20 只基金从 3×disk 降为 1×disk
- **R-205 cache.py `_CACHE_DIR` cwd 依赖消除**：`_CACHE_DIR` 从相对路径 `"data/cache"` 改为 `os.path.join(_PROJECT_ROOT, "data/cache")`，以 `cache.py` 文件位置（`src/python/cache.py`）推导项目根目录绝对路径。消除 cwd 依赖后，`DegradationTracker` 的 `.degradation_state.json` 持久化文件始终写入正确目录，跨会话降级记忆恢复生效。同时 `os.path.abspath(_CACHE_DIR)` 对已绝对路径无影响
- **R-197/R-198 审计修复（5 项技术债）**：代码复盘发现并修复 5 项低/中优先级代码质量问题。MEDIUM：`market_value_sheet.py` 移除重复的 `_FUND_PREMIUM_PLACEHOLDER` 常量定义（已由 `market_value.py` 提供），更新过期注释。LOW：`market_value.py` + `market_value_sheet.py` 新增 `__all__`，明确公共 API 边界。LOW：`generators_news.py` 移除未使用的 `_is_llm_module_enabled` 导入。LOW：`generators_orchestrator.py` 惰性导入（Phase 1+2 临时措施）改为模块级导入，同步修正 3 处 mock 路径。

### Docs

- **文档引用层级规范化**：requirements.md 自包含 + technical.md 仅引 requirements.md
- **用户文档交叉优化**：how-to-config/how-to-use-registry/faq/README 修正同步
- **目录归档与同步**：数据降级文档归档至 `archive/data-degradation/`，datasource-and-folders.md 同步
- **`test_security_edge.py` mock 路径修正**：`patch("src.python.config._defaults._CONFIG_FILE")`
- **文档版本号统一更新**：constants.py、README.md、how-to-test-my-code.md、plan.md、changelog.md 同步至 v0.3.3

---

## [0.3.4] - 2026-07-09

### Added

- **溢价率真实计算**：`market_value.py` 新增 `_compute_premium()` 函数，QDII 基金（含隐式海外基金如标普500ETF/纳指ETF）的溢价率从固定占位符 `"--"` 改为 `(现价-参考净值)/参考净值` 实时计算，输出格式 `"+X.XX%"`。非 QDII 或无参考净值时保持 `"--"`。新增 4 项 `@pytest.mark.data` 测试覆盖正/负/非QDII/零净值场景。
- **版本号一致性检查脚本**：`scripts/check-version-consistency.py` 以 `constants.py` 的 `APP_VERSION` 为单一事实源，自动校验 `pyproject.toml` + 7 份管理/用户文档的版本号一致性。已同步修复 `pyproject.toml` 从 `0.3.0` → `0.3.4` 的过期问题。`CLAUDE.md` 发布流程引用该脚本。

### Fixed

- **R-178 html_writer.py 5 步分拆完成**：`html_writer.py` 从 996 行/5 重职责精简为专注编排。Step 1：`_save_html_report` → `html_save.py`；Step 2：Jinja2 环境 → `html_jinja_env.py`；Step 3：14 个 `_render_*` 函数 → `html_renderers.py`；Step PF：修复 `_ENV.globals` 运行时变异；Step 4：编排器精简。设计文档归档至 `docs-stm/archive/refactor-html_writer/`。
- **R-211 测试隔离补完**：`test_excel_generator_edge.py` 调用 `generate_excel_report` 补传 `output_dir=tmp_path`，消除测试报告对 `reports/` 目录的污染。`logger.py` 新增 `INVEST_RUNNING_TESTS` 环境变量检测 + `"pytest" in sys.modules` 回退，修复 xdist worker 子进程日志误写入 `app.log`。`test_runner.py` 子进程显式设置 `INVEST_RUNNING_TESTS=1` 确保全链路继承。

- **technical.md C12 约束老化引用**：`testplan.md §1.9` → `§1.8`（随 testplan.md 编号修复同步）。

### Docs

- **R-194 technical.md push2 熔断标记同步**：`technical.md` 三层熔断对比表的 push2 实现位置从"模块级全局变量（待迁移）"修正为"已迁移，见 R-188"，与代码实况保持一致。
- **test-coverage-map.md 归档**：`test-coverage-map.md` + `validate_coverage_map.py` 迁移至 `docs-stm/archive/test-coverage-map/`，缩略条目对应更新。
- **testplan.md 组织清理**：已归档的旧 §1.8（场景-测试文件覆盖率映射）移除，后续 §1.9→§1.8 重编号；§6.2.8、§8.3.1 老化引用同步更新。
- **plan.md R-188~R-191 引用更新**：blockquote 标记为已完成，移除"剩余待修复问题"描述。
- **多批计划文件/设计文档归档**：B1-fund-deep-analysis / C-P1b / A5-test-runtime-optimization / 数据降级复盘文档迁入 `archive/` 子目录归类。

---

## [0.3.0] - 2026-07-08

### Changed

- **版本号统一更新**：0.2.91 → 0.3.0（constants.py / README.md / pyproject.toml / 管理文档 / 用户手册共 10 处同步）。
- **管理文档归档**：changelog.md / plan.md / review-findings.md 的 v0.2.x 详细记录迁移至 `docs-stm/archive/` 对应 `archived_*.0.2.x.md` 文件，主文件保留简洁归档引用。
- **datasource-and-folders.md**：目录树补入 3 个新存档文件描述。

### Added

- **testplan.md 8 个 gap 全量覆盖补齐（共 52 项新增测试）：**
  - **HTML 打印样式**（9 项）：`@media print` 规则完整性检测 — 黑白友好/隐藏导航/展开折叠/热力图覆盖
  - **首次运行引导**（4 项 edge）：配置缺失自动初始化/目录创建/损坏降级/菜单可用
  - **Excel 数字格式**（7 项 edge）：styles.py 常量验证 — 金额/百分比/份额千分位
  - **LLM 三态占位区分**（6 项 edge）：NOT_CONFIGURED/MODULE_DISABLED/API_ERROR 互斥 + 内容引导
  - **日志分级输出**（5 项）：INFO/WARNING/ERROR 均落盘 + 级别前缀
  - **错误隔离业务语义**（1 项）：sheet 失败后穿透/市值模块仍被调用
  - **新闻流水线全链路**（2 项 edge+integration）：聚合→去重→关联端到端 + 关联度排序
  - **TUI 错误友好提示**（18 项 edge）：_print_error_with_hint 7 种异常分类 + 菜单调度异常捕获，不暴露原始异常类型名

---

> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.2.x.md](../archive/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
