# 交互式 HTML 报告升级

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

## 工作量估算

| 阶段 | 内容 | 天数 |
|------|------|------|
| 技术选型验证 | Chart.js vs ECharts vs ApexCharts → 选定模板集成方案 | 0.5 |
| 模板改造 | jinja2 模板引入 Chart.js、数据序列化接口、渲染函数 | 1 |
| 图表迁移 | 饼图、柱状图、净值曲线、热力图逐个替换为交互版 | 1 |
| 打印降级 | @media print + canvas-to-image fallback | 0.5 |
| **合计** | | **3 天** |

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
