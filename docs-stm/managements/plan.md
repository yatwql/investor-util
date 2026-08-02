# 个人投资分析报告生成小助手 — 实现计划

> 文档版本：0.9.9-dev

---

## 概述

本文档记录项目的实现计划。已完成的历史版本计划已归档，此处仅跟踪当前迭代中的工作。

---

## 当前迭代待办

> **P0** = 必须完成才能发布 · **P1** = 当前待办 · **P2** = 下一阶段就绪（~12.5d 预排） · **P3** = 预期实施，有空时安排 · **P4** = 实验功能（缺省关闭，需显式启用）

### P0 — 发布门禁

（待排期）

### 推荐实施顺序

> 结合架构约束、收益/风险与最新依赖状态（rf-1 批量并行已落地、plan-3 C7 注册已完成）重排的推荐实施次序。
> ①~⑨ 为推荐先后；括号内为计划项原有优先级归类（P2=下一阶段就绪 / P3=预期实施）。plan-4 已放弃，不列入实施序列。

| 次序 | 计划项 | 归类 | 工作量 | 推荐理由 |
|:--:|:--|:--:|:--:|:--|
| ① | ~~**plan-9** 首次运行引导~~ | P3 | 1d | ✅ 已完成（2026-08-03） |
| ② | ~~**plan-2 / plan-3** 分析基础~~ | P2 | 4.5d | ✅ 已完成（2026-08-03，含相关性矩阵/最大回撤/净值曲线） |
| ③ | ~~**plan-12** HTML 左侧可折叠 TOC~~ | P3 | 0.5d | ✅ 已完成（2026-08-03，用户新增需求） |
| ④ | ~~**plan-6** 多快照趋势追踪~~ | P2 | 3d | ✅ 已完成（2026-08-03，多快照聚合→总市值/HHI/TOP 变迁） |
| ⑤ | ~~**plan-5** 调仓 What-if 模拟~~ | P2 | 5d | ✅ 已完成（2026-08-03，双持仓成本口径 diff 报告） |
| ⑥ | **plan-11** HTML 暗色模式 | P3 | 0.5d | 依赖 plan-1 的 CSS 变量预留（已就绪），极低成本 |
| ⑦ | **plan-10** 日志可视化 | P3 | 1d | 独立低风险 |
| ⑧ | **plan-8** 轻量 Web UI | P3 | 5-6d | 运维+安全成本最高，单人工具需谨慎，建议最后 |

> ✅ **已完成并归档**：**plan-1**（交互式 HTML 报告，8 迭代落地）与 **plan-7**（因子暴露分析 MVP 3 因子，2026-08-02 完成）不再列入实施顺序，设计文档归档见 [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md)。
> ✅ **已完成（v0.9.7，2026-08-03）**：**plan-9** 首次运行引导、**plan-2/plan-3** 分析基础、**plan-12** HTML 左侧可折叠 TOC。
> ✅ **已完成（v0.9.9-dev，2026-08-03）**：**plan-6** 组合演进（多快照趋势追踪）、**plan-5** 调仓 What-if 模拟。

### P2 — 下一阶段就绪

> **plan-2 / plan-3 / plan-5 / plan-6 均已提前完成**（plan-4 已放弃，plan-1/plan-7 已完成归档），P2 组当前无待办。
> **前置状态**：rf-1 批量并行已落地（v0.8.x），plan-2 全品种历史获取依赖已解除；plan-3 的 `drawdown_analysis` 模块 C7 注册已完成；plan-1 交互式 HTML 图表框架已就绪（chartjs-upgrade 归档见 [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md)）。
> 组内条目按推荐实施顺序排列（见上方总览）。

#### 分析功能基础增强（[`plan-correlation-drawdown.md`](../plan/plan-correlation-drawdown.md)）— **plan-2 / plan-3（推荐②）**

| # | 项目 | 内容 | 工作量 |
|:-:|:-----|:-----|:------:|
| plan-2 | **持仓相关性矩阵** | 纯计算(`analysis/correlation.py`)+编排(`orchestrator.py` 获取全品种历史+注入)+registry 注册(C7)+pipeline_data 新键(C19)+Excel/HTML 渲染+数据不足降级(§1.4.5) | 2.5d | ✅ `rf-1` 批量并行已落地，全品种历史可并行获取，无阻塞（详 `plan-correlation-drawdown.md §1`） |
| plan-3 | **最大回撤+净值曲线** | 回撤区间标注 + 多期净值聚合 + 恢复时间明细表 + C19 schema 定义 + 数据不足降级(§1.4.5) + 图表增强(依赖 plan-1) | 2d | ✅ plan-1 已就绪，Chart.js 双轴图可直接复用（详 `plan-correlation-drawdown.md §2`） |

#### 高级分析功能（[`plan-advanced-analysis.md`](../plan/plan-advanced-analysis.md)）— **plan-4（已放弃）~ plan-6**

| # | 项目 | 内容 | 工作量 | 状态 |
|:-:|:-----|:-----|:------:|:----:|
| ~~plan-4~~ | ~~**业绩归因（Brinson 分解）**~~ | ~~单期 Brinson（配置+选股+交互）+ 多期平滑 + 基准选择~~ | ~~4d~~ | ❌ **已放弃** — 3/4 关键数据源不可突破：① 行业指数 K 线不稳定 ② 无免费基准行业权重 ③ 非 A 股品种无行业归属。详见 `archive/v0.7.x/better-investment-advice/discussion-better-investment-advice.md` §4.2 不做清单 |
| ~~plan-6~~ | ~~**多快照趋势追踪（推荐③）**~~ | ~~多期快照聚合 → 市值趋势/行业配置流/穿透变迁/HHI 趋势~~ | ~~3d~~ | ✅ **已完成（2026-08-03）** |
| ~~plan-5~~ | ~~**调仓 What-if 模拟（推荐④）**~~ | ~~双目录镜像 + 对比管线 + diff 视图（Excel/HTML）~~ | ~~5d~~ | ✅ **已完成（2026-08-03）** |

> ✅ **plan-7 因子暴露分析（MVP 3 因子）已完成（2026-08-02）并归档**：`analysis/factor_exposure.py`（OLS 回归/样本下限/停更剔除/LOCF）+ `report/orchestrator.py` 编排注入 + C19 13 键契约 + HTML 模块 #10 柱状图 + Excel 页签 + 单元 11 例/场景 5 例。设计文档归档见 [`plan-factor-exposure.md`](../archive/v0.9.x/factor-exposure/plan-factor-exposure.md)；实施前技术债 rf-102/103/104/106 已全部处理（Tencent 钳位 2000 + 解析容错、Sina 降级接受、因子替代、days 语义澄清）。

> ✅ **plan-6 / plan-5 已完成（v0.9.9-dev，2026-08-03）**：
> - **plan-6 组合演进**：`analysis/portfolio_evolution.py`（多快照聚合 → C19 `evolution_data`）+ Excel「组合演进」页签 + HTML「组合演进」章节（3 张 Chart.js 图各带 `.chart-caption`，C20）+ 快照 <3 降级占位（§1.4.5）。
> - **plan-5 调仓 What-if**：`analysis/whatif.py`（双持仓成本口径 diff，复用 `classify_holding`）+ `whatif` CLI 子命令（`--candidate` 必填）+ 独立报告 `调仓模拟_{ts}.xlsx/.html`（Excel 3 页签 + HTML 双环图双栏页）。

### P3 — 用户体验改进

> **P3** = 预期实施，有空时安排。部分子项已完成，剩余待排期。
> 组内条目按推荐实施顺序排列（见上方总览）；其中 plan-9（推荐①）性价比最高，建议从 P3 提前实施。

#### `plan-9` 首次运行引导（[`plan-web-ui.md §2`](../plan/plan-web-ui.md#2-首次运行引导)）— **推荐①**

检测 config.json/llm_key/holdings 首次缺失 → 交互式引导创建。**预估：1d** → ✅ **已完成（2026-08-03）**：`src/python/startup_wizard.py`（首次标记 + 三态检测 + 交互引导 + llm_key 原子写入）+ TUI/CLI 接线（`--non-interactive`）。回归 18 例见 `test_startup_wizard.py`

#### `plan-12` HTML 报告左侧可折叠 TOC 目录 — **新增（P3，用户需求）**

HTML 报告左侧固定目录栏（列出全部可见章节），点击平滑定位到对应章节；TOC 可一键收起/展开（偏好持久化 localStorage），滚动高亮当前章节；窄屏隐藏保留顶部横向导航；打印隐藏。**已完成（2026-08-03）**：`report_template.html` 增 `.toc-sidebar`/`.toc-toggle-btn` + `toc.js`（折叠/展开 + IntersectionObserver 滚动高亮，离线自包含 R21）+ `html_writer._JS_ASSETS` 复制。回归 21 例（`TestHtmlTocSidebar`/`TestHtmlTocVisibility`/`TestHtmlTocStatic` + 打印/JS 资产）

#### `plan-11` HTML 暗色模式（[`plan-web-ui.md §5`](../plan/plan-web-ui.md#5-html-暗色模式)）— **推荐⑤**

CSS 变量 + localStorage 切换按钮。**预估：0.5d**（依赖 plan-1 的 chart-config.js CSS 变量预留）

#### `plan-10` 日志可视化（[`plan-web-ui.md §3`](../plan/plan-web-ui.md#3-日志可视化)）— **推荐⑥**

结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表）。**预估：1d**

#### `plan-8` 轻量 Web UI（[`plan-web-ui.md §1`](../plan/plan-web-ui.md#1-轻量-web-ui)）— **推荐⑦**

Flask/FastAPI + 上传页面 + 触发管线 + 结果预览/下载。MVP 不做多用户/LLM 在线修改/实时日志流。**运维与安全成本最高，单人工具需谨慎，建议作为 P3 最后项。**

| 阶段 | 工作量 |
|------|:------:|
| MVP 核心 | 3d |
| 功能补齐 | 1.5d |
| 体验打磨 | 1d |

### P4 — 实验功能

> 实验性功能，缺省关闭，需通过配置项或 features.json 显式启用。启用不影响现有功能稳定性。

（待排期）

---

## 归档

- [`archived_plan.0.9.x.md`](../archive/v0.9.x/archived_plan.0.9.x.md) — v0.9.x 已完成项（plan-1 / plan-7，含设计文档索引）
- [`archived_plan.0.8.x.md`](../archive/v0.8.x/archived_plan.0.8.x.md) — v0.8.0 ~ v0.8.10（含设计文档索引 + 已完成项）
- [`archived_plan.0.7.x.md`](../archive/v0.7.x/archived_plan.0.7.x.md)
- [`archived_plan.0.6.x.md`](../archive/v0.6.x/archived_plan.0.6.x.md)
- [`archived_plan.0.5.x.md`](../archive/v0.5.x/archived_plan.0.5.x.md)
- [`archived_plan.0.4.x.md`](../archive/v0.4.x/archived_plan.0.4.x.md)
- [`archived_plan.0.3.x.md`](../archive/v0.3.x/archived_plan.0.3.x.md)
- [`archived_plan.0.2.x.md`](../archive/v0.2.x/archived_plan.0.2.x.md)
- [`archived_plan.0.1.x.md`](../archive/v0.1.x/archived_plan.0.1.x.md)
