# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.8.1-dev] - 未发布

### Fixed
- **P2-11b**: `analysis/metrics.py` 新增 `portfolio_beta_analysis()` — 组合 Beta 95% 置信区间、t 统计量、p 值及可靠性标记（区间宽度 > 1.5 标记不可靠）
- **P3-09b**: `analysis/alignment_correction.py` 实现三项口径修正因子 — 组合综合费率估算 (`portfolio_fee_estimation`)、现金剥离 (`cash_stripping`)、时间加权收益率 TWR (`twr_calculation`)，统一入口 `compute_alignment_factors` 已集成至报告管线

### Changed
- 版本号更新至 v0.8.1-dev
- **check-version-consistency.py**: review-findings.md、llm-technical.md 加入版本号一致性检查清单（11 项）

## [0.8.0] - 2026-07-21

### Changed
- 版本号发布 v0.8.0
- **review-findings.md**：新增 P2 段，记录 Beta 置信区间（P2-11b）和口径修正因子（P3-09b）两项技术债务，待后续迭代切入

---

## 归档

- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录

