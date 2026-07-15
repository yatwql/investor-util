# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

### Added

- *（本次无新增功能）*

### Fixed

- **handlers_cache 缺失 import os**：`_cmd_show_cache_stats` 中使用 `os.path.join` 但模块未导入 `os`（P2-7 拆分解耦遗留）
- **skeleton.py `_generate_llm_content` 内部调用残留**：`_run_standard_mode` 仍调用旧私有名，导致 penetration_deep 模块 RuntimeError
- **handlers_config.py 函数名错写**：`_cmdrefresh_config` → `_cmd_refresh_config`（少一个 `_`，保持 `_cmd_` 命名一致）
- **`_call_llm` → `call_llm` 引用残留**：test_api.py 8 处 + test_log_sanitize.py import/调用
- **`_call_llm_with_retry` → `call_llm_with_retry` 引用残留**：test_log_sanitize.py import-as
- **`history_index` 缺少 cache_groups 豁免**：test_registry.py `known_ungrouped` 未包含 `history_index`
- **P1-3f 重命名残留全量清理**（17 测试文件 + 2 源码文件，共 100+ 处）：
  - `_build_module_info_list` → `build_llm_module_info`（位置迁移至 `llm_module_info.py`）：测试 import/调用 10+ 处
  - `_generate_llm_content` → `generate_llm_content`：mock 目标 7 处 + `_run_standard_mode` 内部调用 1 处
  - `_fetch_with_fallback` → `fetch_with_fallback`（`chain.py` 公开函数）：mock 目标 9 处
  - `_fetch_with_incremental_fallback` → `fetch_with_incremental_fallback`（`chain.py`）：mock 目标 19 处
  - `_call_openai` → `call_openai`、`_call_single_provider` → `call_single_provider`：mock 目标 13 处
  - `_call_llm_with_retry` → `call_llm_with_retry`（移入 `api_base.py`）：mock 目标 1 处
  - `_press_any_key` / `_refresh_config`（import 自 `tui_menu.py`）：mock 目标 10 处

### Changed

- *（本次无变更）*

### Docs

- **test-coverage.md**：同步更新测试计数（all 2990→3073, verify 1775→1832 等）
- **changelog.md**：记录本次全部修复明细


## [0.5.9] - 2026-07-15

### Docs

- **changelog 归档**：v0.5.6/0.5.7/0.5.8 详细记录迁移至 `archived_changelog.0.5.x.md`，changelog.md 仅保留归档引用链接
- **review-findings 归档**：已修复 P3 问题（P3-1/P3-3/P3-7/P3-8/P3-10/P3-11/P3-12）剥离至 `archived_review-findings.0.5.x.md`


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.9（2026-07-14 ~ 2026-07-15）共 10 个版本。


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.8（2026-07-14 ~ 2026-07-15）共 9 个版本。
>
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
