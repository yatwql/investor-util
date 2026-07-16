# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

### Fixed
- **内部路径隔离** — `_config_defaults.py`、`logger.py`、`handlers_config.py` 统一使用 `PROJECT_ROOT`（`constants.py`）作为基准路径，消除 CWD 依赖。解决从非项目根目录运行时 `src/data/`、`src/logs/` 等目录误创建的问题
- **回撤图 Y 轴截断** — `drawSimpleChart` 中 `yMin = Math.max(0, globalMin - pad)` 强制下限 ≥0，导致全部负值回撤数据不可见、指数回撤线被裁剪。移除 `Math.max(0, ...)` 修复
- **回撤区持仓名单分行** — `report_template.html` 中 Section 13 持仓列表由内联拼接改为逐行显示，与 Section 12 保持一致

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

## [0.6.0] - 2026-07-15

> **v0.6.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.6.x/archived_changelog.0.6.x.md](../archive/v0.6.x/archived_changelog.0.6.x.md)。
> 涵盖 v0.6.0（2026-07-15）共 1 个版本。


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）共 13 个版本。


> **v0.4.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.4.x/archived_changelog.0.4.x.md](../archive/v0.4.x/archived_changelog.0.4.x.md)。
> 涵盖 v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）共 5 个版本。
>
> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.3.x/archived_changelog.0.3.x.md](../archive/v0.3.x/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）共 8 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.2.x/archived_changelog.0.2.x.md](../archive/v0.2.x/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/v0.1.x/archived_changelog.0.1.x.md](../archive/v0.1.x/archived_changelog.0.1.x.md)。
