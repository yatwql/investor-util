# 个人投资分析报告生成小助手 - 自我审查问题记录
> 文档版本：0.10.9-dev
> **编号源**：`rf-next = 240`（新增问题取此编号，完成后更新为 +1；已用最大 rf-239，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复 |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）



| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 665 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 542 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 536 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 526 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 635 | 500-800 可选优化区间（2026-08-05 实测 635，较登记值 472 增长 163，跨过 500 线，关注后续增长） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 423 | 未超限（<500，维持现状；2026-08-05 实测 423，较登记值 477 下降，重构后缩减） | Excel 编排器 |

---

## 已修复（摘要）

> v0.10.7 发布时已修复项（rf-217/rf-229/rf-233）已整体迁入 [归档档案](#归档档案) 的 `archived_review-findings.0.10.x.md`。

| # | 文件 | 修复摘要 |
|---|------|----------|
| **rf-234** | `report/_report_generation.py`（1018→686） | facade 聚合门面拆分：后台健康检查→`_report_health.py`、轻量行情/注入/校验→`_report_helpers.py`、全量指标装配→`_full_risk_metrics.py`、图表数据集→`_chart_dataset_factory.py`；门面保留 both/full 双路径编排并 re-export 全部符号 |
| **rf-235** | `report/html_writer.py`（934→660） | facade 聚合门面拆分：章节可见性/目录导航→`html_writer_nav.py`、数据契约展示映射→`html_writer_display.py`、JS 资产复制→`html_writer_assets.py`；门面保留 `write_html_report`/`_render_template` 并 re-export 符号 |
| **rf-236** | `analysis/metrics.py`（880→225） | facade 聚合门面拆分：收益类指标→`metrics_returns.py`、风险类指标→`metrics_risk.py`；门面保留 `compute_all_metrics` 聚合入口 + `__all__` + 常量并 re-export 符号 |
| **rf-237** | `report/orchestrator.py`（822→442） | facade 聚合门面拆分：风格因子/行业 Beta 计算族→`_report_factor_metrics.py`（持仓K线路由 + 因子回归 + 行业Beta）、市场温度/持仓相关性→`_report_aux_metrics.py`；门面保留 `generate_report`/`prepare_report_data`/`compute_valuation_data`（patch 依赖门面命名空间）并 re-export 符号 |
| **rf-238** | `llm/generators_orchestrator.py`（808→698） | facade 聚合门面拆分：新闻关联责任单元（模块级结果缓存/闭包/安全直调）→`_llm_news_correlation.py`；门面保留缓存预检（`_compute_module_cache_info`/`_precheck_*`）/worker 分发（`_dispatch_llm_workers`/`_build_module_fns`）/主编排入口（`generate_all_llm`），re-export 子模块符号，mock patch 接线零改动 |
| **rf-239** | `llm/fact_checker/_utils.py` + `_context.py` + `_constants.py` | 事实校验两处误修正：① `_locate_subject_code` 名称分支起点距离平局（建设银行/工商银行距 171.23% anchor 均 8）误路由，把 601939 正确 171.23% 改写为 601398 的 70.2% → 改最近边距离与代码分支一致；② 止损警戒阈值「回调20%的警戒区域」被当收益率误修正为 -11.8% → `_is_trim_target_context` 增警戒词宽窗口检测。新增 6 个回归测试，修复前均失败，修复后 fact_checker 单文件 109 通过 |

## 归档

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.7（2026-08-04 ~ 2026-08-05，rf-204~rf-233）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
