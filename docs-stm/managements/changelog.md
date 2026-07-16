# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

### Added

### Changed

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
