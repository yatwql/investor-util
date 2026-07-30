# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.0] - 2026-07-30

### Chore

- **ruff 版本锁定 + 全量格式修正** — `pyproject.toml` 锁定 `ruff==0.15.20`（精确版本，避免版本升级导致格式噪音）；全量运行 `ruff format src/python/ scripts/`，修复 CI ruff 格式检查报错
- **版本格式统一** — 管理文档版本头统一去除 `v` 前缀（如 `v0.8.12-dev` → `0.8.12-dev`），`check-version-consistency.py` 模板同步（`v{v}` → `{v}`），涉及 9 份文档

### Docs

- **review-findings.md 归档整理** — 0.8.* 已发布版本的已修复记录（rf-1~rf-64、rf-66~rf-135、rf-106~rf-107）迁移至 `archived_review-findings.0.8.x.md`，归档链接路径修复（`archive/0.8.x/` → `archive/v0.8.x/`）
- **plan.md 归档整理** — 0.8.* 已完成项（plan-12 数据源可用性矩阵、plan-13 数据源可靠性文档、plan-14 ADR）迁移至 `archived_plan.0.8.x.md`
- **changelog.md 归档整理** — v0.8.11 变更记录迁移至 `archived_changelog.0.8.x.md`

## 归档

## 归档

- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

