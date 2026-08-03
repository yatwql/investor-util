# 实现计划归档 — v0.9.x

> 归档时间：2026-08-03
> 原始文件：`docs-stm/managements/plan.md`（当前迭代部分）
> 涵盖版本：v0.9.0 ~ v0.9.8（2026-07-30 ~ 2026-08-03）
> 归档内容：本迭代已实现的计划项（plan-1/2/3/5/6/7/9/12）及其迭代设计文件

---

## v0.9.x 设计文档

本迭代完成项对应的中间设计文档：

- [`plan-chartjs-report-upgrade.md`](chartjs-upgrade/plan-chartjs-report-upgrade.md) — plan-1 交互式 HTML 报告升级实施方案（8 迭代）
- [`plan-chartjs-risk-analysis.md`](chartjs-upgrade/plan-chartjs-risk-analysis.md) — plan-1 风险/收益/架构分析
- [`plan-1-iter7-verification-checklist.md`](chartjs-upgrade/plan-1-iter7-verification-checklist.md) — plan-1 Iter 7 浏览器人工验证清单（rf-113）
- [`plan-factor-exposure.md`](factor-exposure/plan-factor-exposure.md) — plan-7 因子暴露分析设计（原 `plan-advanced-analysis.md` §4）

> 已完成项（plan-2/3/5/6/9/12）设计文档仍保留在 `docs-stm/plan/`（本批仅迁移 plan.md 记录，设计文档待后续统一归档）：`plan-correlation-drawdown.md`（plan-2/3）、`plan-advanced-analysis.md`（plan-4 已放弃 + plan-5/6）、`plan-web-ui.md`（plan-8/9/10/11）。
> 未完成项（plan-8/10/11）设计文档亦保留在 `docs-stm/plan/`：`plan-web-ui.md`、`plan-engineering.md`、`plan-fix-deepseek-thinking-exhaustion.md`。
> 完成但仍处开发版本（v0.9.9-dev）的修复项设计文档亦保留在 `docs-stm/plan/`（不归档）：`plan-fix-qa-concentration-and-chart-optimization.md`（rf-150，当前迭代修复项，release 后随版本归档）。

## v0.9.x 已完成项

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| plan-1 | **交互式 HTML 报告升级（Chart.js）** | Chart.js 替换 Canvas 静态图表，实现缩放/悬停/筛选/导出；6 张交互图表（净值/回撤/资产构成/行业分布/穿透 TOP10/量化指标 Radar）+ 双路径回退 + 本地 bundle | 5.25d（8 迭代） | ✅ 已完成 |
| plan-7 | **因子暴露分析（MVP 3 因子）** | 中证因子代理 + OLS 回归 + 风格归属柱状图 + 停更剔除 + C19 契约（13 键）+ HTML/Excel 渲染 + 单元 11 例/场景 5 例 | 2.5d | ✅ 已完成（2026-08-02） |
| plan-2 | **持仓相关性矩阵** | 纯计算(`analysis/correlation.py`)+编排(`orchestrator.py` 获取全品种历史+注入)+registry 注册(C7)+pipeline_data 新键(C19)+Excel/HTML 渲染+数据不足降级(§1.4.5) | 2.5d | ✅ 已完成（v0.9.7，2026-08-03） |
| plan-3 | **最大回撤+净值曲线** | 回撤区间标注 + 多期净值聚合 + 恢复时间明细表 + C19 schema 定义 + 数据不足降级(§1.4.5) + 图表增强(依赖 plan-1) | 2d | ✅ 已完成（v0.9.7，2026-08-03） |
| plan-9 | **首次运行引导** | 检测 config.json/llm_key/holdings 首次缺失 → 交互式引导创建（`startup_wizard.py` 三态检测 + TUI/CLI 接线） | 1d | ✅ 已完成（v0.9.7，2026-08-03） |
| plan-12 | **HTML 报告左侧可折叠 TOC** | 左侧固定目录栏（列出全部可见章节，点击平滑定位）+ 一键收起/展开（localStorage 持久化）+ 滚动高亮当前章节 + 窄屏隐藏 + 打印隐藏 | 0.5d | ✅ 已完成（v0.9.7，2026-08-03） |
| plan-6 | **多快照趋势追踪（组合演进）** | 多期快照聚合 → 总市值/HHI/TOP 变迁趋势 + 账户配置流（`analysis/portfolio_evolution.py` + Excel/HTML 3 图渲染） | 3d | ✅ 已完成（v0.9.8，2026-08-03） |
| plan-5 | **调仓 What-if 模拟** | 双持仓成本口径 diff 报告（`whatif` CLI + Excel 3 页签 + HTML 双栏双环图独立页） | 5d | ✅ 已完成（v0.9.8，2026-08-03） |

## 归档说明

- plan-1 三个设计文档（实施方案/风险分析/验证清单）2026-08-02 由 `docs-stm/plan/` 移入本目录 `chartjs-upgrade/`。
- plan-7 设计内容为原 `docs-stm/plan/plan-advanced-analysis.md` §4，2026-08-02 抽取为独立文件移入本目录 `factor-exposure/`；`plan-advanced-analysis.md` 已同步裁剪（保留 plan-4/5/6 内容）。
- 2026-08-03 追加归档已完成项记录（迁移自 `plan.md`）：plan-2/3/9/12（v0.9.7 发布）、plan-5/6（v0.9.8 发布）；对应设计文档仍保留在 `docs-stm/plan/`。
- 版本号：本归档涵盖已发布版本 v0.9.0 ~ v0.9.8（当前开发版本 v0.9.9-dev，归档时点为 2026-08-03），归档目录按版本段命名 v0.9.x。
