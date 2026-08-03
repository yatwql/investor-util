# plan-11 HTML 暗色模式

## Context（背景）

HTML 报告目前仅浅色主题，页面级颜色全部硬编码（body `#f0f2f5`、表格、卡片、行状态等），无主题切换。晚间查看报告刺眼，金融工具缺失暗色模式显过时。

**现状（已调研）**：
- `report_template.html` 的 `:root` 已定义 `--chart-*` 10 个图表色变量（注释"暗色模式预留"），由 `chart-config.js::cssVar()` 一次性读取生成 `window.ChartTheme`；但页面级颜色（body/表格/卡片/行状态/语义色）全部硬编码。
- `whatif_template.html` 完全无 `:root` 变量、无 `@media print`，颜色全硬编码。
- `@media print`（report_template.html:290-352）已有浅色强制（`:root` 覆盖 + `body #fff`），`chart-print.js` 的 `toBase64Image()` 抓当前 canvas 像素。
- `toc.js` 提供 localStorage 范式（key `investor-toc-collapsed`，值 '1'/'0'，try/catch 包裹）可复用。
- 无 `data-theme` / `prefers-color-scheme` / 主题切换 JS。

**用户决策**：① 切换按钮**浮动右上角**（fixed，两模板通用）；② 首次打开**默认浅色**（不跟随系统，用户手动切换后 localStorage 持久化）。

## 设计

### 主题机制
- 根元素 `data-theme` 属性：`document.documentElement.dataset.theme = 'dark'`（或移除）。
- 页面级颜色统一为 CSS 变量：`:root` 定义浅色默认值，`[data-theme="dark"]` 覆盖深色值。
- 图表色沿用现有 `--chart-*` 变量（`--chart-grid`/`--chart-text`/`--chart-bg`/`--chart-danger-transparent` 在 dark 块覆盖提亮；`--chart-primary` 等品牌/调色板色保持原值——饱和色暗背景可读）。

### Chart.js 重绘（关键坑）
`ChartTheme` 在脚本加载时一次性烘焙进图表配置。切换主题后需重读 CSS 变量更新 `window.ChartTheme`，并对每张已创建图表更新 `scales.*.ticks/grid/angleLines/pointLabels` 与 `legend.labels` 颜色后 `chart.update()`。
- 图表实例收集：**`Chart.getChart(canvas)`**（Chart.js v4 全局 API）+ `document.querySelectorAll('canvas')` 遍历——无需改 `chart-print.js`/`chart-common.js`，对 report（经 ChartPrint 注册）与 whatif（未加载 chart-print.js）两种页面都通用，非 Chart.js canvas（旧 drawSimpleChart 手绘）返回 undefined 自然跳过。
- `chart.update()` 在 `animation=false`（chart-config.js 已设）下**同步渲染**，切换即刻生效。

### 打印协调（关键坑）
暗色下 `@media print` 的 CSS 覆盖只影响页面非 canvas 部分，canvas 像素仍暗色。theme.js 用**捕获阶段**监听 `beforeprint`（`addEventListener('beforeprint', fn, true)`——捕获先于 chart-print.js 的冒泡阶段快照执行）：若当前暗色，先移除 `data-theme` + 重读变量 + 遍历图表 `update()`（同步渲染浅色像素）→ 随后 chart-print.js 快照抓到浅色；`afterprint` 捕获阶段恢复暗色 + 重绘。记录 `_restoreAfterPrint` 标志。

### 切换按钮
- HTML：`<button type="button" class="theme-toggle-btn" id="theme-toggle-btn" aria-label="切换深色模式" title="切换主题">🌙</button>`，放两模板 `<body>` 内（report 在 TOC 后、container 前；whatif 在 body 开头）。
- CSS：`position: fixed; right: 12px; top: 12px; z-index: 101; width: 38px; height: 38px; border-radius: 50%; background: #2E75B6; ...`；`@media print { display:none !important }`。
- icon 随主题切换：浅色显示 🌙（可切换暗色）/ 暗色显示 ☀️（切回浅色），同步 aria-label。

## 实现步骤

### Step 1 — 新增 `src/static/theme.js`（~120 行，ES5 保守语法）
职责：初始化主题、切换按钮、更新 ChartTheme、遍历图表重绘、打印协调。
- `var STORAGE_KEY = 'investor-theme-dark';`，值 `'1'`/`'0'`，读写均 try/catch（file:// 隐私模式降级，复用 toc.js 范式）。
- 初始化：读 localStorage，`'1'` → 设 `data-theme="dark"` + 按钮 icon 同步。IIFE，`document.readyState === 'loading'` 时挂 DOMContentLoaded。
- `setTheme(dark)`: 设/移除 `data-theme` → `refreshChartTheme()` → `applyThemeToCharts()` → 更新按钮 icon/aria-label → localStorage 写。
- `refreshChartTheme()`: in-place 更新 `window.ChartTheme` 的 `primary/secondary/danger/dangerTransparent/success/warning/grid/text`（用自带的 `cssVar(name, fallback)`，与 chart-config.js 同款），并同步 `commonOptions` 内 text/grid 引用。
- `applyThemeToCharts()`: `querySelectorAll('canvas')` → `Chart.getChart(cv)` 收集 → 逐图更新 `options.plugins.legend.labels.color`、所有 `options.scales.*` 的 `ticks.color`/`grid.color`/`angleLines.color`/`pointLabels.color` = 新 theme → `chart.update()`。
- beforeprint/afterprint 捕获阶段协调（见设计-打印协调），守卫 `window.Chart` 存在。
- 暴露 `window.ThemeSwitcher = { setTheme: setTheme, isDark: function(){ return isDark; } }` 供测试/调试。

### Step 2 — 修改 `src/python/tmpl/report_template.html`
1. `:root`（行 8-20）新增页面级变量：`--bg/--surface/--text/--text-secondary/--border/--border-strong/--table-th-bg/--table-even/--table-hover/--subtotal-bg/--grand-total-bg/--row-danger-bg/--row-warning-bg/--notice-bg/--card-bg/--profit/--loss/--toc-bg/--toc-border/--debate-pro-bg/--debate-con-bg/--debate-synthesis-bg/--box-bg`（浅色值 = 现有硬编码色）。
2. `:root` 后新增 `[data-theme="dark"] { ... }` 覆盖块：背景深灰（`--bg:#121212; --surface:#1e1e1e`）、文字浅（`--text:#e0e0e0`）、边框（`--border:#333`）、表格/卡片深色系、语义色提亮（`--profit:#ff6b6b; --loss:#4caf50`）、`--chart-grid:rgba(255,255,255,0.12); --chart-text:#e0e0e0; --chart-bg:#1e1e1e; --chart-danger-transparent:rgba(255,107,107,0.15)`。
3. 把 style 块内硬编码颜色逐处替换为 `var(--xxx)`（body/section/表格/行状态/语义色/卡片/notice/debate 块/toc 栏/.chart-box 等约 30+ 处）；品牌蓝（`.report-header`/`.section-title`/`.toc-header` 背景 `#2E75B6`）保持原值不变量化（暗色下蓝底白字清晰）。
4. 内联 `style="color: #CC0000"` / `#009900` 等（如 summary 表格）改为 `style="color: var(--profit)"` / `var(--loss)`。
5. body 内加切换按钮 HTML（TOC 后）；`@media print` 加 `.theme-toggle-btn { display:none !important }`。
6. head 脚本区（行 652-660 后）加 `<script defer src="theme.js"></script>`。

### Step 3 — 修改 `src/python/tmpl/whatif_template.html`
1. `<style>` 内补 `:root` 变量（图表色 + 页面色，与 report 同套浅色值）+ `[data-theme="dark"]` 覆盖块 + `.theme-toggle-btn` 样式 + `@media print` 隐藏按钮。
2. 硬编码颜色替换为 var()（body/section/表格/行状态 badge 色/内联 style 等）。
3. body 加切换按钮；head 脚本区加 `<script defer src="theme.js"></script>`。
4. 图表 canvas 若暗色下需要底色，用 `--box-bg` 覆盖 `.chart-box`。

### Step 4 — 修改 `src/python/report/html_writer.py`
`_copy_js_assets` 的 `_JS_ASSETS` 元组（行 649-657）加 `"theme.js"`。whatif 复用同一函数（whatif_writer.py:151），自动包含。

### Step 5 — 测试
- `src/test/unit/feature/test_feature_interactive.py::TestCopyJsAssets.test_copies_all_js_files`：断言列表加 `theme.js`（硬编码文件清单处）。
- `src/test/unit/report/test_html_report_structure.py`（渲染后 BeautifulSoup 断言）新增：
  - `test_theme_toggle_button_present`：`soup.select_one("button.theme-toggle-btn")` + aria-label。
  - `test_theme_js_loaded`：`theme.js` script src 存在。
  - `test_root_css_variables`：style 文本含 `--bg:`/`--surface:`/`--text:` 页面变量。
  - `test_dark_theme_override_block`：style 文本含 `[data-theme="dark"]`。
  - `test_theme_button_hidden_in_print`：`@media print` 内含 `.theme-toggle-btn`。
  - 检查现有 `test_chart_scripts_loaded_in_order`（只过滤 `chart-` 前缀，theme.js 不影响）。
- `src/test/unit/report/test_html_report_structure_edge.py`（原始模板文本正则）新增：`theme.js` script 标签、`[data-theme="dark"]`、`.theme-toggle-btn` 定位 CSS。
- `src/test/unit/report/test_whatif_html.py` 或对应 whatif 结构测试：whatif 模板含 theme.js + 按钮 + `:root` 变量。
- 新增 `src/test/unit/report/test_theme_js.py`（或并入 structure 测试）：读 `src/static/theme.js` 静态断言 `investor-theme-dark` key、`beforeprint` 捕获 `true`、`Chart.getChart` 收集逻辑存在。所有用例标 `@pytest.mark.unit` + `@pytest.mark.unit_report`。

### Step 6 — 文档同步
- `technical.md`：§4.13 或新增小节记录暗色模式设计（CSS 变量体系 / ChartTheme 重读 / 打印协调 / whatif 与主报告一致）。
- `requirements.md`：报告暗色模式需求条目（若 §6 模块清单涉及报告呈现，补字段）。
- `folders.md`：`src/static/` 目录树加 `theme.js`（描述"主题切换（深/浅色 + localStorage 持久化 + Chart.js 重绘 + 打印浅色协调）"），同步项目统计文件数。
- `reports-instruction.md`：报告查看说明补暗色模式切换用法。
- `changelog.md` 0.9.11-dev 加 Feat 条目（plan-11 暗色模式）。
- `plan.md`：plan-11 标记完成（迁移至已归档区或标注 ✅）。
- 运行 `collect-test-coverage.py` 刷新 test-coverage.md / folders.md 统计（新增测试用例数变化）。

## 验证

1. 单测：`pytest src/test/unit/report/ src/test/unit/feature/ -q`（新增 + 既有全部通过）。
2. P0 门禁：`.venv/bin/python scripts/test_runner.py --mode dev-verify` + `check-code-traces.py --ci` + `check-doc-traces.py --ci`。
3. `ruff format --check` 受影响 .py 文件。
4. 手动：`src/static/test-chart.html` 与一份生成的完整报告（菜单 L/B）：
   - 右上角按钮点击切换深/浅色，刷新后主题持久化（localStorage）。
   - 暗色下 6 图网格线/文字/图例颜色随主题变化（`Chart.getChart` 重绘生效）。
   - 暗色下 Ctrl+P 打印：图表快照为浅色、按钮隐藏、非 canvas 内容浅色。
   - whatif 报告（菜单 W）同样支持切换。
5. 提交；计划文件迁移至 `docs-stm/plan/`（覆写 plan-web-ui.md §4 或归档至 archive 后标注 plan-11 完成）。

## 风险点
- **模板 CSS 替换量大**（~30+ 处硬编码色）——机械替换需逐处核对，避免漏改导致暗色下局部对比度不足。语义色（profit/loss/行状态）务必提亮，纯黑背景上旧 `#CC0000` 红可读性差。
- **Chart.getChart 兼容性**——Chart.js v4.4.3 提供该 API；ES5 环境（微信 X5）也支持 `querySelectorAll`/`Object.keys`/`forEach`。
- **打印顺序依赖捕获阶段监听**——`beforeprint` capture 先于 chart-print.js 冒泡快照，属浏览器标准行为；需测试确认。
- **FOUC**——theme.js 用 defer 在 DOMContentLoaded 前执行，body 未绘制时设 data-theme，无闪烁。
