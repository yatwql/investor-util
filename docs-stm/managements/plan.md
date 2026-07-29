# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：v0.8.11-dev

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪（~22d 预排） · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P0 — 发布门禁

（待排期）

### P2 — 下一阶段就绪

> **plan-1**～**plan-7**（plan-4 已放弃）合计 ~18d 预排。

#### `plan-1` 交互式 HTML 报告升级（[`plan-chartjs-report-upgrade.md`](../plan/plan-chartjs-report-upgrade.md)）

Chart.js 替换 Canvas 静态图表，实现缩放、悬停提示、筛选、导出。**预估：4d**

| 阶段 | 内容 | 工作量 |
|------|------|:------:|
| 技术选型验证 | Chart.js vs ECharts vs ApexCharts → 选定模板集成方案；CDN ↔ 本地 bundle 策略 | 0.5d |
| 数据接口定义 | 每类图表 template context 数据结构（C14 约束：走 `render()` context）；C19 Schema 定义（如需新增 pipeline_data 键） | 0.5d |
| 模板改造 | jinja2 模板引入 Chart.js、数据序列化接口、渲染函数 | 1d |
| 图表迁移 | 饼图、柱状图、净值曲线、热力图逐个替换为交互版 | 1d |
| 打印降级 | @media print + canvas-to-image fallback | 0.5d |
| Feature Flag | `enable_interactive_charts` 控制迁移回退（§1.4.4 配置驱动） | 0.5d |

覆盖 6 张交互图表：资产构成(Doughnut)、行业分布(Horizontal Bar)、穿透 TOP10(Bar)、净值趋势(Line)、相关性矩阵(Heatmap)、量化指标(Gauge/Radar)。（⬆ plan-3/plan-6 图表增强依赖本项）

#### 分析功能基础增强（[`plan-correlation-drawdown.md`](../plan/plan-correlation-drawdown.md)）— **plan-2 / plan-3**

| # | 项目 | 内容 | 工作量 |
|:-:|:-----|:-----|:------:|
| plan-2 | **持仓相关性矩阵** | 纯计算(`analysis/correlation.py`)+编排(`orchestrator.py` 获取全品种历史+注入)+registry 注册(C7)+pipeline_data 新键(C19)+Excel/HTML 渲染+数据不足降级(§1.4.5) | 2.5d | ⚠️ 对 `rf-1` 有间接依赖（串行获取全品种历史 ~15-30s，详 `plan-correlation-drawdown.md §1`） |
| plan-3 | **最大回撤+净值曲线** | 回撤区间标注 + 多期净值聚合 + 恢复时间明细表 + C19 schema 定义 + 数据不足降级(§1.4.5) + 图表增强(依赖 plan-1) | 2d | ⚠️ Chart.js 双轴图依赖 plan-1（详 `plan-correlation-drawdown.md §2`） |

#### 高级分析功能（[`plan-advanced-analysis.md`](../plan/plan-advanced-analysis.md)）— **plan-4（已放弃）~ plan-7**

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| ~~plan-4~~ | ~~**业绩归因（Brinson 分解）**~~ | ~~单期 Brinson（配置+选股+交互）+ 多期平滑 + 基准选择~~ | ~~4d~~ | ❌ **已放弃** — 3/4 关键数据源不可突破：① 行业指数 K 线不稳定 ② 无免费基准行业权重 ③ 非 A 股品种无行业归属。详见 `archive/v0.7.x/better-investment-advice/discussion-better-investment-advice.md` §4.2 不做清单 |
| plan-5 | **调仓 What-if 模拟** | 双目录镜像 + 对比管线 + diff 视图（Excel/HTML） | 5d | ⏳ 数据源 ✅ 无新依赖 |
| plan-6 | **多快照趋势追踪** | 多期快照聚合 → 市值趋势/行业配置流/穿透变迁/HHI 趋势 | 3d | ⏳ 数据源 ✅ 无新依赖 |
| plan-7 | **因子暴露分析** | 中证因子代理 + OLS 回归 + 风格归属饼图 | 3.5d | ⏳ 数据源 ⚠️ 需 CSI 风格指数 probe 验证 |

### P3 — 用户体验改进

> **P3** = 预期实施，有空时安排。部分子项已完成，剩余待排期。

#### `plan-8` 轻量 Web UI（[`plan-web-ui.md §1`](../plan/plan-web-ui.md#1-轻量-web-ui)）

Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载。MVP 不做多用户/LLM 在线修改/实时日志流。

| 阶段 | 工作量 |
|------|:------:|
| MVP 核心 | 3d |
| 功能补齐 | 1.5d |
| 体验打磨 | 1d |

#### `plan-9` 首次运行引导（[`plan-web-ui.md §2`](../plan/plan-web-ui.md#2-首次运行引导)）

检测 config.json/llm_key/holdings 首次缺失 → 交互式引导创建。**预估：1d**

#### `plan-10` 日志可视化（[`plan-web-ui.md §3`](../plan/plan-web-ui.md#3-日志可视化)）

结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表）。**预估：1d**

#### `plan-11` HTML 暗色模式（[`plan-web-ui.md §5`](../plan/plan-web-ui.md#5-html-暗色模式)）

CSS 变量 + localStorage 切换按钮。**预估：0.5d**

#### 已完成项

- **✅ plan-12 错误友好提示/数据源可用性矩阵**（`plan-web-ui.md §4`）— 已在 `data_source_matrix.py` 实现，作为报告章节 #17（always 类型页签）输出

#### 文档体系完善（[`datasource-reliability-documentation.md`](../archive/v0.8.x/datasource-reliability-documentation/datasource-reliability-documentation.md)）— **plan-13 / plan-14（已归档）**

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| plan-13 | **数据源可靠性文档** | 8 类数据源可靠性详表 + 降级路径 + 限流规则 + 历史故障 | 1-1.5d | ✅ 已完成 (`datasource-reliability.md` + `cli check-sources`) |
| plan-14 | **架构决策记录（ADR）** | ADR 目录/模板 + 补写 5-8 个关键决策 + 流程固化 | 2.5d | ⏸ 已搁置（`technical.md` 架构约束表 + `review-findings.md` rf-1 脚注已覆盖关键决策记录，当前优先级不足投入 2.5d） |

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。

（待排期）

---

## 归档

- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.9（含设计文档索引）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
