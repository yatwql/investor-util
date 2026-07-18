# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.6.9-dev] - 未发布

> 待定

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

> v0.6.x 及更早版本变更记录已归档：
>
> - [`v0.6.x`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.7（2026-07-15 ~ 2026-07-18），v0.6.8（2026-07-18）
> - [`v0.5.x`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
> - [`v0.4.x`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
> - [`v0.3.x`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
> - [`v0.2.x`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
> - [`v0.1.x`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
