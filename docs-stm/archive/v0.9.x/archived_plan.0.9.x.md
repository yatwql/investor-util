# 实现计划归档 — v0.9.x

> 归档时间：2026-08-02
> 原始文件：`docs-stm/managements/plan.md`（当前迭代部分）
> 涵盖版本：v0.9.0 ~ v0.9.5（2026-07-30 ~ 2026-08-02）
> 归档内容：本迭代已实现的计划项（plan-1、plan-7）及其迭代设计文件

---

## v0.9.x 设计文档

本迭代完成项对应的中间设计文档：

- [`plan-chartjs-report-upgrade.md`](chartjs-upgrade/plan-chartjs-report-upgrade.md) — plan-1 交互式 HTML 报告升级实施方案（8 迭代）
- [`plan-chartjs-risk-analysis.md`](chartjs-upgrade/plan-chartjs-risk-analysis.md) — plan-1 风险/收益/架构分析
- [`plan-1-iter7-verification-checklist.md`](chartjs-upgrade/plan-1-iter7-verification-checklist.md) — plan-1 Iter 7 浏览器人工验证清单（rf-113）
- [`plan-factor-exposure.md`](factor-exposure/plan-factor-exposure.md) — plan-7 因子暴露分析设计（原 `plan-advanced-analysis.md` §4）

> 未完成项（plan-2/3/5/6 等）设计文档仍保留在 `docs-stm/plan/`：`plan-correlation-drawdown.md`（plan-2/3）、`plan-advanced-analysis.md`（plan-4 已放弃 + plan-5/6 待办）、`plan-web-ui.md`、`plan-engineering.md`、`plan-fix-deepseek-thinking-exhaustion.md`。
> 完成但仍处开发版本（v0.9.7-dev）的修复项设计文档亦保留在 `docs-stm/plan/`（不归档）：`plan-fix-qa-concentration-and-chart-optimization.md`（rf-150，当前迭代修复项，release 后随版本归档）。

## v0.9.x 已完成项

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| plan-1 | **交互式 HTML 报告升级（Chart.js）** | Chart.js 替换 Canvas 静态图表，实现缩放/悬停/筛选/导出；6 张交互图表（净值/回撤/资产构成/行业分布/穿透 TOP10/量化指标 Radar）+ 双路径回退 + 本地 bundle | 5.25d（8 迭代） | ✅ 已完成 |
| plan-7 | **因子暴露分析（MVP 3 因子）** | 中证因子代理 + OLS 回归 + 风格归属柱状图 + 停更剔除 + C19 契约（13 键）+ HTML/Excel 渲染 + 单元 11 例/场景 5 例 | 2.5d | ✅ 已完成（2026-08-02） |

## 归档说明

- plan-1 三个设计文档（实施方案/风险分析/验证清单）2026-08-02 由 `docs-stm/plan/` 移入本目录 `chartjs-upgrade/`。
- plan-7 设计内容为原 `docs-stm/plan/plan-advanced-analysis.md` §4，2026-08-02 抽取为独立文件移入本目录 `factor-exposure/`；`plan-advanced-analysis.md` 已同步裁剪（仅保留 plan-4/5/6 内容）。
- 版本号：本归档涵盖已发布版本 v0.9.0 ~ v0.9.5（当前开发版本 v0.9.7-dev，v0.9.6 已发布，归档时点为 2026-08-02），归档目录按版本段命名 v0.9.x。
