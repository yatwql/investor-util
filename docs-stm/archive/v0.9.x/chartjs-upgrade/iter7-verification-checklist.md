# plan-1 Iter 7 全链路浏览器人工验证清单（rf-113）

> **归档说明**：随 plan-1 设计文档一并归档（2026-08-02），清单仍在 review-findings.md P1 跟踪（rf-113 浏览器人工验证项）。关联方案文档见同目录 [`plan-chartjs-report-upgrade.md`](./plan-chartjs-report-upgrade.md) 与 [`plan-chartjs-risk-analysis.md`](./plan-chartjs-risk-analysis.md)。
>
> 关联：`plan-chartjs-report-upgrade.md` §5 Iter 7 验收标准 2/3/4/6 + §4.8（A1/A4）+ §4.14（R17 浏览器矩阵）+ §4.15（R22 微信场景）
> 状态：⏳ 待实测（rf-113，review-findings.md P1）
> 目的：plan-1 代码与自动化测试已落地（dev-verify 1181 passed），以下为**只能真实浏览器/微信执行的验证项**——本清单提供可勾选的操作步骤，勾选完成后回填 `changelog.md` 并将 rf-113 从 review-findings.md 待处理移至已修复表。
>
> 文档版本：0.9.9-dev（rf-159 后更新资产清单：7 JS + chart-common.js 依赖说明）

---

## 前置准备

| # | 操作 | 说明 |
|:-:|:-----|:-----|
| 0.1 | 生成一份完整报告（菜单 L 或 B） | 报告输出目录含 6 个 Chart.js canvas + 7 个 JS 资产（`chart.min.js`/`chart-print.js`/`chart-config.js`/`chart-export.js`/`chart-common.js`/`chart-init.js`/`toc.js`），确认 `src/static/` 七文件已复制 |
| 0.2 | 打开 `src/static/test-chart.html` 调试页（可独立于真实报告先行） | 6 图渲染/交互 + 4 场景自检；S2 升级验证载体。⚠ 注入列表必须含 `chart-common.js`（rf-159 后 chart-init.js 依赖 `window.ChartCommon`，缺失会 0/6 全跳过） |
| 0.3 | 调试页场景栏切换：正常 / 降级（虚线）/ 空数据（占位）/ 离线（无引擎） | 场景自检横幅显示 `N/6 图已初始化` |

> ⚠ 浏览器最低版本：Chrome / Edge 90+（主验）、Firefox 90+ / Safari 14+（抽验）、国产 Chromium 内核 90+（R17 矩阵）。

---

## ① 6 图渲染 + 交互（Iter 7 验收标准 2）

> 对应 rf-113 ①。可用 `test-chart.html` 调试页在真实浏览器执行。
> ⚠ ① 的 6 图 = 核心 6 图（净值/回撤/资产构成/行业/穿透/雷达）。真实报告（菜单 L/B）另含 **3 张组合演进图**（evolution_total/hhi/top，plan-5/6 新增）——非 rf-113 验证对象，正常渲染即可。
> ⚠ 回撤图（chart_drawdown）在报告里**仅当历史数据 span ≥ 60 交易日才渲染**（§1.4.5，`drawdown_available`）；span 不足时该 canvas 按设计隐藏。要完整验证 6 图交互请用 `test-chart.html`（合成数据全量渲染）。

| # | 检查项 | Chrome | Edge | Firefox* | Safari* |
|:-:|:-------|:------:|:----:|:-------:|:-------:|
| 1.1 | 净值趋势 Line 渲染，悬停显示精确 tooltip（组合 + 基准线） | ☐ | ☐ | ☐ | ☐ |
| 1.2 | 最大回撤 Line 渲染，回撤填充 + tooltip | ☐ | ☐ | ☐ | ☐ |
| 1.3 | 资产构成 Doughnut 渲染，悬停显示占比 + 金额 | ☐ | ☐ | ☐ | ☐ |
| 1.4 | 行业分布 Horizontal Bar 渲染，悬停显示市值 | ☐ | ☐ | ☐ | ☐ |
| 1.5 | 穿透 TOP10 Bar 渲染，悬停显示穿透明细 | ☐ | ☐ | ☐ | ☐ |
| 1.6 | 量化指标 Radar 渲染，悬停显示指标值 | ☐ | ☐ | ☐ | ☐ |
| 1.7 | 页面无 JS 报错（打开 DevTools Console 检查） | ☐ | ☐ | ☐ | ☐ |

> *Firefox / Safari 为抽验（R17 矩阵最低支持版本），不通过不阻塞，记录差异即可。
> **判定**：Chrome + Edge 6 图全部渲染且无 JS 报错 → ① 通过。

## ② 打印降级（Iter 7 验收标准 3）

> 对应 rf-113 ②。`chart-print.js` beforeprint 快照 + `@media print` 浅色强制已实现。

| # | 检查项 | Chrome | Edge |
|:-:|:-------|:------:|:----:|
| 2.1 | `Ctrl+P` 打印预览，6 张图以高分辨率静态图显示（2x DPI） | ☐ | ☐ |
| 2.2 | 打印预览中图表为浅色主题（不浪费墨水，对比度正常） | ☐ | ☐ |
| 2.3 | 图表不在分页处被切断（`break-inside: avoid`） | ☐ | ☐ |
| 2.4 | 打印后关闭预览，页面交互图恢复正常（afterprint 恢复 canvas） | ☐ | ☐ |

> **判定**：2.1~2.4 全过 → ② 通过。

## ③ 离线验证（Iter 7 验收标准 4，R21）

> 对应 rf-113 ③。本地 bundle 离线自包含，`typeof Chart` 守卫跳过初始化。
> ⚠ 删除 `chart.min.js` 时**保留 `chart-common.js`**：它不依赖引擎，加载无副作用；chart-init.js 靠 `typeof Chart` 守卫静默跳过（双守卫 `typeof Chart === 'undefined' || !window.ChartCommon`，rf-159 后）。

| # | 检查项 | 结果 |
|:-:|:-------|:----:|
| 3.1 | 断网（或 DevTools Network → Offline）打开报告，6 图正常渲染 + 交互 | ☐ |
| 3.2 | **模拟引擎缺失**：复制报告目录 → 删除/改名 `chart.min.js` → 打开复制版 → 页面无 JS 报错 | ✅（另机 2026-08-06） |
| 3.3 | 引擎缺失时页面回退 Canvas / 表格（Canvas 兜底路径生效） | ✅（另机 2026-08-06，chart-config/chart-init 静默跳过） |
| 3.4 | 引擎缺失且 Canvas 失败时显示 `<canvas>` fallback 文本（A1，指引用户看表格） | ✅（另机 2026-08-06，canvas 保留 fallback 文本） |

> **判定**：3.1 通过（离线自包含成立）；3.2~3.4 通过（防御性守卫成立）→ ③ 通过。
> 💡 也可用 `test-chart.html?场景=离线` 先行验证守卫逻辑（`typeof Chart` 检测 → 静默跳过 → banner 显示 err）。
> **验证进度（2026-08-06 另机）**：3.2~3.4 已实测通过——删除 chart.min.js 后 `typeof Chart === undefined` → chart-config/chart-init 静默跳过，页面无 JS 报错，canvas 保留 fallback 文本，守卫逻辑符合预期（R21）。**3.1（断网 6 图正常渲染）待补验**。

## ④ 微信内置浏览器实测（Iter 7 验收标准 6，R22）

> 对应 rf-113 ④。唯一不确定点：file:// 沙箱对相对 JS 加载的限制。

| # | 检查项 | 结果 |
|:-:|:-------|:----:|
| 4.1 | **链接访问**：报告部署到 http/https（或本地起静态服务），微信内点链接打开 → 6 图渲染正常 | ☐ |
| 4.2 | **file:// 访问**：从文件传输助手/收藏点开 .html 附件 → 图表渲染 | ☐ |
| 4.3 | file:// 若图表不渲染（X5 沙箱拦截）→ 页面无 JS 报错、Canvas/表格兜底可见、数据可读 | ☐ |
| 4.4 | 移动端横屏/竖屏下图表自适应不溢出（A4，responsive + maintainAspectRatio） | ☐ |

> **判定**：4.1 通过（链接访问正常）；4.2 或 4.3 任一通过（file:// 或兜底成立）→ ④ 通过。
> ⚠ 微信内展示本质是"看一张静态报告"，移动端触屏 hover 不友好，图表退化为可读静态呈现是**合理预期**，不构成功能缺失（upgrade.md §4.14）。

## ⑤ 移动端 375px 适配（Iter 7 验收标准，A4）

> 对应 rf-113 ⑤。

| # | 检查项 | 结果 |
|:-:|:-------|:----:|
| 5.1 | DevTools 设备模拟 375px 宽度，6 图自适应不溢出容器 | ☐ |
| 5.2 | 图表横轴标签不重叠（柱状/折线） | ☐ |
| 5.3 | 图表容器与明细表格流式排列正常 | ☐ |

> **判定**：5.1~5.3 全过 → ⑤ 通过。

## ⑥ 禁用 Canvas 后 fallback 文本（Iter 7 验收标准补充，A1）

> 对应 rf-113 ⑥。页面禁用 Canvas 后，6 图区域应显示 fallback 文本而非空白。

| # | 检查项 | 结果 |
|:-:|:-------|:----:|
| 6.1 | DevTools 禁用 Canvas（或渲染无 canvas 环境）后，6 图区域显示内嵌 fallback 文本（如"图表无法显示，数据见报告明细表格"） | ☐ |
| 6.2 | 浅色模式下图表文本可读（对比度 ≥ 4.5:1 目测） | ☐ |

> **判定**：6.1 通过（A1 fallback 生效）；6.2 通过（A2 对比度目测可接受）→ ⑥ 通过。

---

## 结果汇总

| 项 | 标题 | 结果 | 备注 |
|:--:|:-----|:----:|:-----|
| ① | 6 图渲染 + 交互 | ☐ 通过 / ☐ 不通过 | |
| ② | 打印降级 | ☐ 通过 / ☐ 不通过 | |
| ③ | 离线验证 | ☐ 通过 / ☐ 不通过 | 3.2~3.4 已过（另机 2026-08-06）；3.1 断网渲染待补验 |
| ④ | 微信打开 | ☐ 通过 / ☐ 不通过 | |
| ⑤ | 375px 移动端 | ☐ 通过 / ☐ 不通过 | |
| ⑥ | fallback 文本 | ☐ 通过 / ☐ 不通过 | |

**全部通过后处理**：
1. `changelog.md` 0.9.5-dev 段补 Fix/Docs 条目（记录实测结果 + 环境）
2. `review-findings.md` rf-113 从 P1 待处理移至已修复表（含验证摘要）
3. 本文件状态行改 ✅ 已完成，保留作 S2 升级 Chart.js 时的复验清单

> **复验复用**：本清单在升级 Chart.js（S2 流程）后可直接复用——`test-chart.html` 场景自检 + ①③⑤ 项即可覆盖，②④⑥ 抽验。
