# 交互式 HTML 报告升级（Chart.js 实施方案）

> **关系**：本文档 = 实施方案；关联的风险/收益/架构分析见 [`plan-chartjs-risk-analysis.md`](./plan-chartjs-risk-analysis.md)。
>
> 二者共同组成 plan-1 的完整设计方案：实施方案聚焦"怎么做"，风险分析聚焦"为什么这么做"。

## 概述

当前 HTML 报告使用 Canvas 渲染静态图表，用户无法交互。升级到 Chart.js（或同等库）实现缩放、悬停提示、筛选、导出，将 HTML 报告从"可打印的网页"升级为"可交互的仪表盘"。

---

## 收益

- **数据探索能力**：鼠标悬停看到精确数值、点击图例切换品类显示、框选放大时间区间
- **专业感提升**：交互式仪表盘比静态截图级别的报告质变，可分享给同行/顾问
- **定位问题快**：净值曲线上悬停一眼看到当日涨跌，不需要回 Excel 翻
- **技术门槛低**：jinja2 模板管道已有，Chart.js 通过 CDN 引入只需改模板 + 加序列化数据端点
- **免费且轻量**：Chart.js ~80KB（gzip），无后端依赖，完全客户端渲染

## 风险

- 嵌入大量原始数据会膨胀 HTML 文件体积（当前 ~280KB，可能涨到 ~1MB）
- 国产浏览器兼容性：微信内置浏览器对 ES6 支持不一
- 部分用户打印 HTML 报告：交互式图表打印时需要 fallback 静态图
- Chart.js 特定版本安全风险（需锁定版本号，不 auto-load latest）

## 架构约束遵从

| 约束 | 适配方式 |
|:-----|:---------|
| **C14** (渲染期数据不可写入模块级全局变量) | 所有图表数据（chart_data、chart_config 等）必须通过 `render()` context 参数传递，**严禁**注入 `_ENV.globals`。当前 `section_visible` 为唯一 globals 条目（fail-closed 默认值 + 渲染期 context 覆盖），Chart.js 数据不得增加第二个 globals 条目 |
| **C19** (pipeline_data Schema 契约) | 若新增管线级图表数据结构（如预处理的 Chart.js dataset 格式），必须在 pipeline_data Schema 定义集中预定义类型/版本号/写入模块。若仅对现有 template context 数据（`history_data.bars` 等）做 `tojson` 序列化后直接 Chart.js 消费，则不需要新 Schema 条目 |
| **§1.4.4** (报告配置化) | Chart.js 交互功能应通过 Feature Flag `enable_interactive_charts`（默认开启）控制，用户可在 `config.json` 或 `features.json` 关闭后回退到现有 Canvas 2D 渲染。渲染期通过模板 context 传递标志量，不硬编码行为 |
| **§1.4.5** (数据降级治理) | 数据量不足的图表（如相关性矩阵品种 < 3 只不生成）Chart.js 应渲染空状态提示而非白屏，与现有降级占位逻辑一致 |

**对 plan-3/plan-6 的依赖（反向）**：plan-1 是 plan-3（净值曲线/回撤图）和 plan-6（多快照趋势图）的 Chart.js 升级前提。若 plan-1 推迟，plan-3/plan-6 的图表增强需在现有 Canvas 2D 框架内实现（有限功能，不阻塞）。

## 工作量估算（含架构约束适配）

| 阶段 | 内容 | 天数 |
|------|------|:----:|
| 技术选型验证 | Chart.js vs ECharts vs ApexCharts → 选定模板集成方案；明确 CDN ↔ 本地 bundle 策略 | 0.5 |
| 数据接口定义 | 定义每类图表所需的 template context 数据结构（C14 约束：走 `render()` context，非 `_ENV.globals`）；若新增 pipeline_data 键则完成 C19 Schema 定义 | 0.5 |
| 模板改造 | jinja2 模板引入 Chart.js CDN ↔ 本地 bundle 切换、数据序列化接口、`tojson` 管道、渲染函数（C14 约束） | 1 |
| 图表迁移 | 饼图、柱状图、净值曲线、热力图逐个替换为交互版 | 1 |
| 打印降级 | `@media print` + `chart.toBase64Image()` fallback | 0.5 |
| Feature Flag 适配 | `features.json` 新增 `enable_interactive_charts`（默认开启），渲染器根据 flag 切换 Chart.js ↔ Canvas 2D | 0.5 |
| **合计** | | **4 天** |

## 实现的 6 张交互图表

| 图表 | 类型 | 交互功能 |
|------|------|----------|
| 资产构成 | Doughnut/Pie | 点击图例展开明细、悬停占比+金额 |
| 行业分布 | Horizontal Bar | 排序切换（市值/数量）、悬停详细值 |
| 穿透 TOP10 | Bar | 点击跳转品种详情、悬停穿透明细 |
| 净值趋势 | Line | 框选缩放、悬停日期+净值、基准对比 |
| 相关性矩阵 | Heatmap(Matrix plugin) | 悬停相关系数+p-value |
| 量化指标 | Gauge/Radar | 与基准对比的雷达图、指标说明 tooltip |

## 技术方案对比

| 方案 | 体积 | 热力图 | 缩放 | 打印兼容 | 评价 |
|------|------|--------|------|----------|------|
| **Chart.js** | ~80KB | 需插件 | 内置 | medium | ✅ 推荐：最轻量 |
| ECharts | ~300KB | 内置 | 内置 | hard | 太重，超过项目规模 |
| ApexCharts | ~130KB | 无原生 | 内置 | medium | 无热力图 |

## 实现路径

1. `requirements.txt` 加入 `chart.js`（可选，通过 CDN 加载可不加）
2. `html_jinja_env.py` 增加 `chart_data` 序列化 inject
3. `html_renderers.py` 新增 `render_interactive_charts()`
4. `template.html` 引入 `<script src="cdn.chart.js/4.x">` + `<canvas>` 容器
5. 打印降级：`window.print()` 前调用 `chart.toBase64Image()` 注入 `<img>` 标签
