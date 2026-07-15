# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

---

## [Unreleased]

### Added

- **组合历史走势 — 基准指数对比（Iter I）**：
  - 新增 `benchmark_indices` 配置项，支持指定最多 3 个基准指数进行走势对比
  - `benchmark.py` — `fetch_benchmarks()` 并行获取指数历史日线（ThreadPoolExecutor）
  - `benchmark.py` — `normalize_benchmarks()` 归一化至 100 基点与组合走势对齐（LOCF 填充 + 起算日对齐）
  - HTML 渲染：`drawSimpleChart()` 多 dataset 版本，组合曲线 + 基准指数虚线叠加，右侧图例 + 鼠标悬停 tooltip
  - HTML 回撤图：叠加基准指数回撤序列（灰色虚线）
  - Excel `portfolio_history` 页签：每基准一列（归一化值 0.00 格式）
  - Excel `drawdown_analysis` 页签：对比指标矩阵（累计收益率/最大回撤/波动率等）
  - `PortfolioHistoryCalculator.__init__` 接受 `benchmark_indices` 参数，完整的 docstring
- **新增测试**：
  - `test_portfolio_history.py` — benchmark 集成测试（fetch_benchmarks 调用/空配置跳过/异常处理）
  - `test_benchmark.py` — normalize_benchmarks 已有 16 项单元测试
  - `test_benchmark_edge.py` — normalize_benchmarks 已有 7 项边缘场景测试

### Fixed

- **P0 配置浅层合并**：`config/_core.py` 嵌套 dict 合并使用 `merged[key] = {**merged[key], **val}`，防止 `benchmark_indices` 默认值被 `history.analysis` 配置覆盖
- **P1 normalize_benchmarks 防御**：增加 `bar.get("date")` 防御性检查，防止 KeyError；每个基准归一化完成后追加成功日志
- **P1 HTML tooltip 事件监听器泄漏**：重绘时移除旧 `mousemove`/`mouseleave` 监听器再注册，通过 `canvas._chartTooltipHandlers` 追踪；tooltip `<div>` 元素复用而非重复创建
- **移除 Chart.js CDN 外部依赖**：`drawSimpleChart()` 使用 Canvas 2D API 原生渲染，不再加载外部 CDN 脚本

### Changed

- `handlers_report.py` — `_cmd_generate_both()` 和 `_cmd_generate_full()` 传递 `history_data` 参数
- `excel_generator.py` — `generate_excel_report()` 接收 `history_data` 参数，写入历史走势/回撤分析页签
- `report_template.html` — `drawSimpleChart()` 改为多 dataset 签名 `(canvasId, datasets, opts)`，保留旧签名向后兼容
- `_defaults.py` — `_DEFAULT_CONFIG` 中添加默认 `history.benchmark_indices`（沪深300 + 标普500）

### Docs

- `technical.md` — 新增 I 迭代技术设计（基准指数对比模块），更新最后更新日期
- `testplan.md` — 新增 S34 场景（基准指数对比）
- `test-coverage.md` — 更新测试项数
- `datasource-and-folders.md` — 新增 benchmark.py 等文件说明
- 管理文档去历史痕迹：`requirements.md`、`technical.md`、`testplan.md`、`plan.md`、`review-findings.md` 移除版本号/更新日期/归档链接，内容仅反映最新状态
- 用户文档去历史痕迹：`datasource-and-folders.md` 移除末尾最后更新行
- `reports-instruction.md` — 补充基准指数叠加对比说明（§16/§17/历史走势分组表/F2 机制）
- `faq.md` — 补充基准指数对比 FAQ（走势图基准曲线来源说明）


> **v0.5.x 版本变更记录已归档**：详见 [docs-stm/archive/v0.5.x/archived_changelog.0.5.x.md](../archive/v0.5.x/archived_changelog.0.5.x.md)。
> 涵盖 v0.5.0 ~ v0.5.5（2026-07-14）共 6 个版本。
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
