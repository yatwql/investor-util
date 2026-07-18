# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

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

> v0.6.x 及更早版本变更记录已归档：
>
> - [`v0.6.x`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.8（2026-07-15 ~ 2026-07-18）
> - [`v0.5.x`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
> - [`v0.4.x`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
> - [`v0.3.x`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
> - [`v0.2.x`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
> - [`v0.1.x`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
