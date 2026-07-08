# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Changed

- **Provider Chain 熔断架构升级**（三层熔断 + 冷却恢复 + batch 预检）：
  - 新增 `is_provider_chain_broken()` 全链熔断查询 API，batch 入口一次预检替换逐条重复判断
  - 新增熔断冷却恢复机制（`_PROVIDER_COOLDOWN_SECS=300`），冷却期满后放行试探请求，成功则恢复
  - `batch_fetch_industry_data` 入口预检：全链熔断时跳过批量获取，不调 API
  - `batch_fetch_industry_data` 重试预检：熔断未恢复时跳过 0.8s 等待+重试
  - 新增 13 项 edge 测试覆盖：`is_provider_chain_broken`（5 项）、冷却探针 4 态（4 项）、batch 预检（4 项）

### Fixed

- **R-166 mypy 严格模式升级**：启用 `no_implicit_optional`、`warn_unused_ignores`、`check_untyped_defs` 三个严格标记，修复 77 处 mypy 错误（覆盖 24 文件），包括：attr-defined（termios 平台特化）、valid-type（`Callable`/`builtins.set`）、arg-type（httpx 参数、list 不变性—改用 `Sequence`）、return-value（返回 None 路径添加 `| None`）、union-attr（Optional 属性访问保护）、misc（None 可调用检查、条件分支签名对齐）、list-item（异构 Future 列表用 `Future[Any]`）、assignment（窄化/类型收窄）、name-defined（`Any` 导入）等模式。mypy 零残留错误。
- **R-167 `_ext_memo` 会话级复用缓存推广**：`eastmoney_industry.py` 和 `eastmoney_industry_rest.py` 新增 `_ext_memo` 模块级字典缓存（C4 约束），同一证券代码在同一会话内仅首次发起 HTTP 请求，后续调用直接返回缓存结果。两个模块各新增 `_ext_memo_clear()` 测试辅助方法。
- **R-161 TOCTOU 竞态**：`fetcher/chain.py` 中 `_fetch_with_fallback` 对 `_PROVIDER_SKIP` 和 `_PROVIDER_SKIP_TIME` 的读取分别在两次独立加锁中，合并为一次临界区
- **R-162 `_TRANSPORT_FAILURE` 类型污染**：`fetcher/chain.py` 中 `dict[str, Any] | None = object()  # type: ignore` 改为 `object` 纯哨兵，移除类型擦除标记
- **R-163 废弃 build-backend**：`pyproject.toml` 中 `setuptools.backends._legacy:_Backend` 切换为 `setuptools.build_meta`
- **R-164 模板一致性防护**：`test_config.py` 新增 `TestDefaultConfigTemplateConsistency` 测试，自动校验 `_get_default_config_template()` 与 `_DEFAULT_CONFIG` 深度一致
- **R-165 Ruff 规则集升级**：从 `["E", "F", "W", "I"]` 升级至 `["E", "F", "W", "I", "SIM", "UP", "ARG", "PERF"]`，手动修复 50+ 未定义名/废弃类型/未用参数等违规，添加 `# noqa` 抑制合法 PERF203 模式（try-except 逐项隔离），新增 per-file-ignores 放宽测试/遗留代码约束
- **R-168 配置 mtime+size 双因子缓存**：`config.py` 新增 `_config_size`/`_llm_config_size`，mtime 之外增加文件大小校验，避免 Windows FAT 同秒写入漏检测
- **R-169 429 API 限速差异化提示**：`fetcher/chain.py` `_try_provider_fetch` 中区分 429/Too Many Requests/rate limit 并输出单独日志
- **R-170 新闻流水线集成测试修复**：`test_news_pipeline_edge.py` 中 4 个测试全部真实通过。
  - 修复 pre-existing `test_aggregate_deduplicate_correlate_chain` 和 `test_correlator_sorts_by_relevance` 的 mock 路径/函数名错误（`correlate_news` → `correlate_news_with_holdings`；mock 位置改为 `news_aggregator.correlate_news_with_holdings` 以绕过模块级 import 引用问题）
  - 修复新增 `test_fetch_from_all_sources_partial_failure` 和 `test_fetch_from_all_sources_deduplicates_by_url` 的 mock 位置（`news_sources._FETCH_MAP` → `news_aggregator._FETCH_MAP` 因模块级 import）
- **R-171 CI/CD 流水线配置**：新增 `.github/workflows/ci.yml` — 多 Python 版本（3.10~3.13）矩阵测试，三档门禁（dev→regression / master→verify / 标签→all），附带 mypy 类型检查 + Ruff 代码/格式检查。同步在 `pyproject.toml` 新增 `[project.optional-dependencies] test` 集中管理测试工具链依赖。
- **R-166 遗留修复（缓存测试导入路径）**：`test_cache.py` 中 4 处 `from src.python.cache import CACHE_WEEKLY/CACHE_MONTHLY` 修正为 `from src.python.constants`，与 production 代码的导入路径一致。
- **R-167 遗留修复（_ext_memo 测试隔离）**：`test_eastmoney_industry.py` 和 `test_fetcher_industry.py` 中 4 个测试类新增 `setUp` → `_ext_memo_clear()`，避免模块级缓存污染跨测试用例。
- **R-172 HTTP 异步客户端支持**：`http_client.py` 新增 `make_async_http_client()` 工厂方法返回 `httpx.AsyncClient`，同步更新 `technical.md` 中 C5 约束描述。现有同步调用路径无任何变更。
- **R-173 ThreadPoolExecutor 集中管理**：`handlers_report.py` 新增模块级共享 `_POOL`（`_get_pool()`）替代两处 `with ThreadPoolExecutor() as _:` 现场创建模式，通过 `atexit` 注册清理。避免并行任务执行期间反复创建/销毁线程池。
- **R-174 配置校验去重**：`config.py` 新增 `_section()` 辅助函数封装"get → None 检查 → isinstance → 日志"重复模式，6 个校验函数（`_validate_cache_ttl`/`_validate_news_sources`/`_validate_preferred_provider`/`_validate_user_fund_benchmarks`/`_validate_early_warning`/`_validate_report_section_order`）统一使用。`_validate_string_configs` 和 `_validate_news_top_count` 因模式不同保留原样。
- **R-175 colorama 降级为可选依赖**：`tui_menu.py` 中 `import colorama` 改为 `try/except ImportError` 保护，`just_fix_windows_console()` 仅在 colorama 可用时调用。`pyproject.toml` 中 colorama 从硬依赖移至 `[project.optional-dependencies] color`。
- **R-176 docstring 误放**：`llm/api.py` `_cache_line_model_tpl` 后跟随的独立字符串改为注释
- **R-182 TODO 残留清理**：`fund_style_analysis.py` `_get_industry_avg_pe()` 删除 TODO 注释并精简 docstring，函数签名如实反映"当前暂未实现"
- **R-183 文档引用索引表**：`plan.md` 新增 R-160~R-176 索引表（编号/标题/修复版本/changelog 位置），新场景引用时可直接定位
- **R-181 ThreadPoolExecutor 集中管理（handlers_cache）**：`handlers_cache.py` 新增模块级共享 `_POOL + _get_pool()`，替代原来 3 处 `with ThreadPoolExecutor() as _:` 现场创建模式，附带 `atexit` 清理注册
- **R-178 文件导览注释**：`html_writer.py` 顶部新增完整文件导览 TOC（L44-L78），列出所有区段（路径/过滤器/辅助函数/核心生成/子渲染/报告保存）及其行号范围，替代原拆分方案

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
