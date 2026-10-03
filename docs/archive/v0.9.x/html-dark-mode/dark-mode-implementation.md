# plan-11 HTML 暗色模式 — 实施记录

> 归档日期：2026-08-03 · 版本：v0.9.11-dev · 设计：`../../plan/plan-web-ui.md §4` · 对应 plan：`plan-11`
>
> 状态：✅ 已完成并归档

## 背景

HTML 报告（主报告 + 调仓 What-if）原先仅浅色主题，页面级颜色全部硬编码，无主题切换。晚间查看刺眼，金融工具缺失暗色模式显过时。

**用户决策**：① 切换按钮**浮动右上角**（fixed，两模板通用）；② 首次打开**默认浅色**（不跟随系统，用户手动切换后 localStorage 持久化）。

## 主题机制

- 根元素 `data-theme` 属性：`document.documentElement.dataset.theme = 'dark'`（或移除）。
- 页面级颜色统一为 CSS 变量：`:root` 定义浅色默认值，`[data-theme="dark"]` 覆盖深色值。
- 语义色提亮：浅色 `--profit:#CC0000 / --loss:#009900`；深色 `--profit:#ff6b6b / --loss:#4caf50`（红涨绿跌惯例保持）。
- 品牌蓝 `#2E75B6` 保留硬编码（暗色下蓝底白字清晰）；相关性热力图图例色、drawSimpleChart JS 调色板为数据色，不随主题变化。

## Chart.js 重绘

`window.ChartTheme` 在脚本加载时一次性烘焙进图表配置。切换主题后 `theme.js::refreshChartTheme()` 重读 CSS 变量原位更新 `ChartTheme`，`applyThemeToCharts()` 用 **`Chart.getChart(canvas)`**（Chart.js v4 全局 API）+ `querySelectorAll('canvas')` 遍历收集图表，更新 `legend.labels.color` 与各 `scales.*` 的 `ticks/grid/angleLines/pointLabels` 后 `chart.update()`。

- 对 report（经 ChartPrint 注册）与 whatif（未加载 chart-print.js）两种页面通用；
- 非 Chart.js canvas（旧 drawSimpleChart 手绘）返回 undefined 自然跳过；
- `chart.update()` 在 `animation=false`（chart-config.js 已设）下同步渲染，切换即刻生效。

## 打印协调

暗色下 `@media print` 的 CSS 覆盖只影响非 canvas 部分，canvas 像素仍暗色。`theme.js` 用**捕获阶段**监听 `beforeprint`（`addEventListener('beforeprint', fn, true)`——捕获先于 chart-print.js 的冒泡阶段快照执行）：若当前暗色，先移除 `data-theme` + 重读变量 + 遍历图表 `update()`（同步渲染浅色像素）→ chart-print.js 快照抓到浅色；`afterprint` 捕获阶段恢复暗色 + 重绘。`restoreAfterPrint` 标志记录状态。

## 切换按钮

- HTML：`<button type="button" class="theme-toggle-btn" id="theme-toggle-btn" aria-label="切换深色模式" title="切换深色模式">🌙</button>`，放两模板 `<body>` 内。
- CSS：`position: fixed; right: 12px; top: 12px; z-index: 101; width: 38px; height: 38px; border-radius: 50%; background: #2E75B6;`；`@media print { display: none !important; }`。
- icon 随主题切换：浅色显示 🌙（可切暗色）/ 暗色显示 ☀️（切回浅色），同步 aria-label。

## 实现文件

| 文件 | 变更 |
|------|------|
| `src/static/theme.js`（新增） | ES5 IIFE，存储键 `investor-theme-dark`（'1'/'0'，try/catch 包裹）；`refreshChartTheme()` / `applyThemeToCharts()` / `setTheme()` / 捕获阶段 beforeprint/afterprint；暴露 `window.ThemeSwitcher` |
| `src/python/tmpl/report_template.html` | `:root` 增页面级变量（约 50 个）+ `[data-theme="dark"]` 覆盖块；硬编码色批量替换为 var()；`--rating-deviation` 新增；内联语义色（评级标签/集中度惩罚）改 var；按钮 HTML + theme.js script + `@media print` 隐藏按钮 |
| `src/python/tmpl/whatif_template.html` | 同套变量 + 深色块 + 按钮 + theme.js script |
| `src/python/tmpl/partials/evolution_section.html` | 2 处占位文本颜色 → `var(--text-muted)/var(--text-faint)` |
| `src/python/report/html_jinja_env.py` | `_jinja_price_type_color` → `var(--rating-stable)`；`_jinja_profit_color` → `var(--profit)/var(--loss)`；`_jinja_sentiment_colorize` 内联 span 用 var() |
| `src/python/report/html_writer.py` | `_JS_ASSETS` 加 `theme.js`（whatif 复用同一函数） |

## 测试

- `src/test/unit/report/test_html_report_structure.py::TestHtmlTheme`：按钮存在/aria-label、theme.js 加载顺序（toc 后）、`:root` 变量、`[data-theme="dark"]` 块、打印隐藏按钮、语义色无硬编码。
- `src/test/unit/report/test_html_report_structure_edge.py::TestHtmlThemeStatic`：原始模板正则（theme.js script 标签、按钮 fixed 定位、aria-label、深色块、打印隐藏、无 `color: #CC0000/#009900`）。
- `src/test/unit/report/test_theme_js.py::TestThemeJsStatic`：theme.js 静态断言（存储键、beforeprint 捕获 `}, true);`、`Chart.getChart` 收集、`window.ThemeSwitcher`、ES5 无箭头函数/const/let、`window.Chart` 缺失守卫）。
- `src/test/unit/report/test_whatif_html.py`：whatif 页含按钮 + theme.js + `:root` 变量 + 打印隐藏。
- `src/test/unit/report/test_feature_interactive.py::TestCopyJsAssets`：断言列表加 `theme.js`。
- 更新：`test_security_edge.py`（profit_color 新契约）、`test_html_writer.py::TestJinjaFilters`（price_type_color → var）、`test_html_template.py`（打印隐藏清单含 `.theme-toggle-btn`）。

## 风险与兜底

- 模板 CSS 替换量大（~30+ 处硬编码色）——逐处核对，语义色提亮防对比度不足；JS 调色板/品牌蓝/热力图图例色有意保留。
- `Chart.getChart` 依赖 Chart.js v4.4.3；ES5 环境（微信 X5）支持 `querySelectorAll`/`forEach`。
- 打印顺序依赖捕获阶段监听先于 chart-print.js 冒泡快照，属浏览器标准行为。
- FOUC：theme.js 用 defer，DOMContentLoaded 前设 `data-theme`，无闪烁。
