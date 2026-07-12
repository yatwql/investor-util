# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

## [0.4.0] - 2026-07-12

### Fixed

- **price_stock 测试 mock 未同步 v0.3.8 链路拆分（延续）**：本迭代进一步发现同类问题，修复 `test_api_edge.py`（3 项 fallback 链测试 + 1 项异常降级测试）和 `test_fetcher.py`（1 项名称不匹配测试）仍 mock `eastmoney` 为 fallback provider，但 v0.3.8 已将 `price_stock` 链改为 `tencent→sina`。统一替换为 `sina` mock，返回字段同步适配 `_price_transform_sina`（`nav`/`nav_date` → `price`/`price_date`）。

### Docs

- **datasource-and-folders.md 目录树核对**：补充 `unit/llm/test_prompts.py`（45 项提示词测试）、`unit/report/test_market_value_strategy_edge.py`（8 项策略退化验证）。
- **test-coverage.md 文件计数同步**：`unit/report/` 41→40 文件、`unit/llm/` 20→19 文件。

> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.3.x.md](../archive/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）共 8 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.2.x.md](../archive/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
