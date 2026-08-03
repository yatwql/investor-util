# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.11-dev] - 2026-08-03

### Feat

- HTML 报告暗色模式（plan-11）：主报告与调仓 What-if 报告均可切换深/浅色，右上角浮动按钮，主题偏好 localStorage 持久化（首次默认浅色）；页面级颜色统一为 CSS 变量，Chart.js 图表随主题重绘，打印自动切浅色

### Refactor

- **首次运行引导/隐私声明已读标志迁移至机器本地状态（config.json 去个性化）** — `_startup_wizard_shown`、`_privacy_notice_shown` 自 `data/config/config.json` 迁移至 `data/state/local_state.json`（git 忽略的机器本地目录），避免 config.json 跨机同步时各机器个性化差异。新增 `config/_local_state.py`（`get_flag`/`set_flag`/`_migrate_legacy_keys` 惰性迁移）与 `del_config()` 删键能力（磁盘文本 span 定位删除键行 + 末位成员尾随逗号清理，保留注释）；startup_wizard/privacy_notice/tui_menu 三处调用点改读 local_state

### Test

- 新增 `test_local_state.py`（标志读写 + 旧键惰性迁移 9 例）、`test_config.py` 增 `TestDelConfig`（删键 5 例，含末位键尾随逗号清理）；conftest `_isolate_sensitive_paths` 隔离 `local_state.json` 路径；修正 `test_menu_key_coverage` 期望键集合补 `W`（调仓 What-if 菜单）

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.10（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
