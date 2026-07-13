# HTML 报告组合历史走势/回撤图渲染修复方案（实施修订版 v2）

## Context

用户报告 HTML 报告页面中：
- **组合历史走势图**："速度很慢，显示不完整"
- **历史回测分析**："没有显示"

根因分析：Chart.js 从西方 CDN 加载在中国大陆均慢/不稳定。超时后仅显示错误文本，图表区域为空白。
此外 `history.analysis` 默认配置为 `"off"` 时 `history_data` 为 None，模版无法渲染图表内容。

**修改两个文件**：核心为 `src/python/tmpl/report_template.html`（纯前端 Chart.js/Canvas 渲染改造），辅以 `src/python/report/portfolio_history.py`（Python 后端并行加速）。

## 修改方案（实际实施）

### 改动 1：CDN 加载链路 → 新增国内 CDN + 移除失效 CDN

新增 `bootcdn.net`（国内可访问）作为首位；移除始终超时的 `cdnjs.cloudflare.com`：
```
https://cdn.bootcdn.net/ajax/libs/Chart.js/4.4.0/chart.umd.min.js  ← 首位（国内加速）
https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js
https://unpkg.com/chart.js@4.4.0/dist/chart.umd.min.js
```

### 改动 2：新增原生 Canvas 2D 即时渲染函数（核心修复）

在 head 的 `<script>` 块中定义 `drawSimpleChart(canvasId, labels, values, opts)`：
- 纯 Canvas 2D API，无外部依赖
- 使用 `canvas.clientWidth` / `canvas.clientHeight` 获取 CSS 显示尺寸（**不用 `cssText` 覆盖**）
- 支持 retina 高 DPI（`canvas.width = dispW * devicePixelRatio`）
- Y 轴刻度 + grid 线（支持 `currency` / `percent` 格式）
- X 轴日期标签（自动采样至 ~10 个）
- 折线 + 可选的 fill 面积填充

**实施演变**：

| 版本 | 策略 | 问题 |
|------|------|------|
| v1（首次） | Chart.js 超时 8s 后降级到 drawSimpleChart | 8s 白屏，用户仍觉慢 |
| v2（当前） | 立即用 drawSimpleChart 渲染，后台加载 Chart.js 后原地升级 | 唯一解决"白屏等待"的方案 |

**关键 Bug 修复**（从"翻几页都翻不完"到"一屏可见"）：

| 版本 | 问题 | 修复 |
|------|------|------|
| v1 | `canvas.style.cssText = 'width:'+width+'px'` 用 buffer 宽度覆盖 CSS 显示宽度，画布远超出视口 | 改为读取 `canvas.clientWidth`，不动 CSS |
| v2.1 | `canvas.clientWidth` 返回的是父容器计算宽度，若父容器被其他内容撑宽，canvas 仍会溢出视口；且 Chart.js `responsive:true` 接管后又可能重设宽度 | 用 `Math.min(canvas.clientWidth, window.innerWidth - 96)` 做硬钳制，然后 `canvas.style.width = dispW + 'px'` 显式锁死 CSS 宽度 + `responsive: false` 禁止 Chart.js 篡改 |

**v2.1 核心逻辑**：

1. `dispW = Math.min(canvas.clientWidth, window.innerWidth - 96)` —— 以窗口宽度为硬上限
2. `canvas.style.width = dispW + 'px'` —— 用像素值锁定 CSS 显示尺寸，防止父容器 flex/grid 溢出将其撑宽
3. Chart.js 升级时 **传 canvas 元素而非 2D 上下文**，避免上下文残留 `ctx.scale(dpr)` 导致 Chart.js 绘图错位
4. Chart.js 选项 `responsive: false` —— 使用 canvas 已有尺寸（即 drawSimpleChart 锁定的大小），Chart.js 只负责绘制交互层（tooltip），不改尺寸

### 改动 3：两个图表渲染脚本 → 即时原生渲染 + 后台 Chart.js 升级（responsive:false）

**组合走势图**（portfolioChart）和**回撤图**（drawdownChart）的内联渲染脚本：
- **同步阶段**（页面解析到此 `<script>` 时）：立即调用 `drawSimpleChart()` 渲染，毫秒级
- **异步阶段**：`setInterval` 每 300ms 轮询 `window.Chart` 是否加载完成
  - 加载完成 → 传 canvas 元素给 `new Chart(element, {responsive: false, ...})` 在同个 canvas 上叠加交互 tooltip，**不改 canvas CSS 尺寸**
  - 10s 后停止轮询，保持原生静态渲染结果
- Chart.js 加载异常（CDN 全挂）→ 原生渲染结果保持，不会回退到白屏或错误文本

### 改动 4：新增 canvas CSS

```css
canvas { max-width: 100%; }
@media print { canvas { max-width: 100%; page-break-inside: avoid; } }
```

## 修改的文件

| 文件 | 变更 |
|------|------|
| `src/python/tmpl/report_template.html` | 新增 drawSimpleChart（原生 Canvas 即时渲染）、CDN 链路改造（bootcdn 首位）、渲染脚本改为即刻渲染+后台 Chart.js 升级、canvas CSS |
| `src/python/report/portfolio_history.py` | 新增 `ThreadPoolExecutor` 并行获取每个持仓历史数据（`max_workers=8`），解决多持仓时数据获取串行慢的问题 |

## 验证步骤

1. 运行回归测试：`python scripts/test_runner.py --mode regression`
2. 浏览生成的 HTML 报告（需一份包含 history_data 的报告，菜单 L），确认：
   - 走势图一屏内可见，不超宽
   - 回撤图正常渲染
   - 页面首屏立即显示图表，不等 CDN
   - Canvas 清晰（retina 适配）
3. CDN 容错验证：在浏览器 DevTools 中 Block CDN 域名，刷新页面，确认原生渲染保留
4. 窗口缩放测试：缩小/放大浏览器窗口，确认 canvas 响应式适配宽度
