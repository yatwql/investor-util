# 报告浏览器验证方法与实测结论（rf-113 · plan-1 Iter 7 六项）

> **关联**：`docs/managements/review-findings.md` → **rf-113**（Iter 7 全链路浏览器人工验证 6 项）；勾选清单 [`docs/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`](../archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md)（①~⑥、逐步操作与判定标准、2026-08-06 另机历史进度）。
> **目的**：把 6 项拆成「**可自动化的实测项**」与「**必须人工的项**」，留下可复现的验证方法与本次实测结论——后续报告模板 / `chart-*.js` / Chart.js 版本改动后直接复用本方法（脚本与产物在 `docs/tmp/rf113/`，git 忽略，重跑即重建）。
> **本次实测**：2026-10-09 · 本机 headless Chromium **148.0.7778.96**（`~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`，`--headless=new`）· Node **v22.23.1** 全局 WebSocket 直连 CDP · 被测报告 `reports/个人投资分析报告.html`（v0.12.7-dev，生成于 2026-10-09 07:18:43，925,814 字节单文件）。
> **红线遵守**：不真实调用 LLM、不生成报告（仅打开既有产物）；不改 `data/config/`、`data/holdings/`；按任务约束**未跑 `scripts/check-*.py` 守护、未 `git add/commit`、未改 `docs/managements/`**（rf-113 台账由维护者回填，建议文本随实测结果一并返回）。

---

## 1. 环境与前置

### 1.1 环境与复跑命令（可复现）

```bash
# ① 静态核验：报告 HTML 零外链（在仓库根执行）
R="reports/个人投资分析报告.html"
grep -oE '<script[^>]*[[:space:]]src[[:space:]]*=[[:space:]]*"[^"]*"' "$R"   # 0 处
grep -oE '<link[^>]*href[^>]*>' "$R"                                        # 0 处
grep -c '@import' "$R"                                                      # 0
grep -oE '<(script|img|iframe|source|video|audio|embed)[^>]*src[[:space:]]*=[[:space:]]*"[^"]*"' "$R" \
  | grep -E 'https?://'                                                     # 0 处
grep -oE 'url\((["'"'"']?)https?://[^)]*\)' "$R"                             # 0 处
# 完整扫描输出：docs/tmp/rf113/static-selfcontained.log（判定 PASS）

# ② CDP 自动化实测（一键跑完 ①②③⑤⑥ 六个场景，约 2~3 分钟）
node docs/tmp/rf113/run-rf113.mjs
# 输出逐场景 [PASS]/[FAIL]，落盘 results/summary.json + 分场景 JSON + screenshots/*.png
# 其中 ③ 场景会以 --host-resolver-rules=MAP * ~NOTFOUND 独立启动第二只 Chrome 做断网验证
```

本次输出摘要（`results/summary.json`，Chrome `Chrome/148.0.7778.96`）：

```text
[PASS] ①-testchart-ok-badge
[FAIL] ⑤-testchart-375px      ← 调试页自身溢出，见 §4 发现 1（报告页 PASS）
[PASS] ⑤-report-375px
[PASS] ②-report-afterprint
[FAIL] ⑥-report-no-canvas      ← 表现记录型场景（pass 恒 false，结论按实测逐条记录）
[PASS] ③-report-offline
```

### 1.2 报告生成前置（rf-113 载体）

| 前置 | 说明 | 本次状态 |
|:-----|:-----|:---------|
| 生成入口 | 菜单 **L**（HTML 单文件）或 **B**；本次**未生成**，直接使用 `reports/` 下最新报告 `个人投资分析报告.html` | ✅ |
| `enable_interactive_charts` | `src/python/config/features.py` 常规开关，默认 **True**（Chart.js 交互图；关即回退 Canvas+表格且 HTML 不再单文件自包含） | ✅ 默认开 |
| 调试页 | `src/static/test-chart.html?s=ok\|degraded\|empty\|offline`，注入列表含 `chart-common.js`（rf-159 后 chart-init.js 依赖 `window.ChartCommon`） | ✅ |
| 图表规模 | 报告共 **10 个 canvas**：核心 6 图 + 组合演进 3 图（evolution_total/hhi/top）+ 调仓回放 1 图（schedule_replay）；回撤图历史 span ≥60 交易日时渲染 | ✅ 10/10 初始化 |

### 1.3 自动化取证的三个环境前提（脚本已内置，人工复验同样适用）

1. **报告章节默认折叠**：正文大块在 `<details class="section-fold>` 内（16 个，加载时 10 个折叠）。折叠态下 canvas **不渲染、不可命中**（`checkVisibility()=false`、`elementFromPoint` 穿透到祖先），因此脚本先 `details.open = true` 展开全部章节再取证；折叠态本身不影响 `chart-print.js` 的 `toBase64Image` 快照（位图在初始化时已绘制）。
2. **headless 下 `html { scroll-behavior: smooth }` 不推进**（实测 `scrollIntoView` 后 2.8s `scrollY` 仍为 0）：脚本先临时置 `scrollBehavior='auto'` 再 `scrollTo`，并轮询目标元素入视口。
3. **截图口径**：`Page.captureScreenshot` 必须带 `captureBeyondViewport: false`，否则默认从页面顶部截取，拿不到滚动位置的图表区。

### 1.4 测试用文件（`docs/tmp/rf113/`，git 忽略，重跑即重建）

| 文件/目录 | 内容 |
|:----------|:-----|
| `run-rf113.mjs` | 主脚本：启动 headless Chrome（+离线第二实例），6 个场景逐一断言 |
| `static-selfcontained.log` | ③ 静态零外链扫描全输出（判定 PASS） |
| `results/*.json` | `summary.json` + 6 个分场景结果（断言值、console 错误、网络请求清单） |
| `screenshots/*.png` | 01/02/03/04/05/06/07 系列截图（见各节证据路径） |
| `probe-*.mjs`、`probe-*.log` | 排障探针（canvas display 归属、滚动行为、hover 坐标、折叠态可见性）；固化 §1.3 三条前提后可删除 |
| `profile-*` | Chrome 临时 user-data-dir（每场景独立，避免缓存串扰） |

---

## 2. 逐项结论

### ① 6 图渲染回归（`?s=ok` 6/6 badge）— 自动化实测结论

- **命令**：`node docs/tmp/rf113/run-rf113.mjs`（场景 `①-testchart-ok-badge`，打开 `src/static/test-chart.html?s=ok`）
- **断言与结果**：
  - 自检横幅 `className=ok`，文案「场景 [ok]：**6/6 图已初始化**」→ 过
  - 6 个 badge（`bd_portfolio_line/drawdown/category_doughnut/industry_bar/penetration_bar/radar`）全部 `badge ok` → 过（6/6）
  - `Chart.getChart()` 命中 6/6 canvas，引擎已加载 → 过
  - console error / 未捕获异常 **0 条**（含清单 1.7「页面无 JS 报错」口径）→ 过
- **证据**：`docs/tmp/rf113/results/①-testchart-ok-badge.json`、`docs/tmp/rf113/screenshots/01-testchart-ok-badge.png`
- **历史（已过项）**：2026-08-06 Windows 另机人工——ok/degraded 6/6 渲染 + tooltip、empty 4/6 + 2 占位、offline 守卫生效（Chrome + Firefox；期间修复 rf-248/249/251），见归档清单 §①。
- **残留（人工范围）**：本机仅 Chromium；Firefox 抽验历史已过、Edge 同 Chromium 内核可视为覆盖，**Safari 14+ 抽验仍属人工**（不阻塞）。

### ② 打印降级 2.4 afterprint — 自动化实测结论

- **方法**：打开真实报告 → 展开全部章节 → `window.dispatchEvent(new Event('beforeprint'))` / `afterprint`（`chart-print.js` 通过 `window.addEventListener('beforeprint'/'afterprint')` 监听），前后各取 10 个 canvas 的状态快照；再用 **CDP 真实鼠标事件**打到净值图数据点验证 tooltip。
- **断言与结果**：

| 断言 | 结果 |
|:-----|:----|
| beforeprint 后 `img[data-chart-print]` 插入 | ✅ **10 张**（`src` 前缀 `data:image/png;base64`，2x 快照） |
| beforeprint 后 canvas 隐藏 | ✅ 10/10 `style.display='none'` |
| afterprint 后快照 img 移除 | ✅ **0 张残留** |
| afterprint 后 canvas 可见 | ✅ 10/10 computed `display ≠ none`，**文档坐标几何偏差 0px**（位置/尺寸完全还原） |
| afterprint 后交互恢复 | ✅ CDP `mouseMoved` 命中数据点 → `tooltip.getActiveElements()`：**打印前 2**（组合+沪深300）、**afterprint 后 2**，tooltip 恢复可用（截图可见 tooltip 浮层） |
| console error | ✅ 0 条 |
| 观察项（非断言） | ⚠ canvas 内联 `display` 打印前 `block`（Chart.js v4.4.3 初始化写入）→ afterprint 后 `''`（computed `inline`）；几何零偏差、tooltip 正常，详见 §4 发现 2 |

- **证据**：`docs/tmp/rf113/results/②-report-afterprint.json`、`docs/tmp/rf113/screenshots/04-report-beforeprint.png`（快照态）、`05-report-afterprint-hover.png`（恢复后 hover tooltip）
- **历史（已过项）**：2026-08-06 Windows 另机人工——2.1 2x DPI 清晰、2.2 浅色主题、2.3 单图不跨页（`break-inside: avoid`），见归档清单 §②。
- **人工范围**：真实 `Ctrl+P` 打印预览的分页/着色效果 headless 无法出 UI，2.1~2.3 仍以人工预览为准（已有历史结论）；本自动化覆盖 2.4「派发打印事件 → 快照插入/移除 → 交互恢复」全链路。

### ③ 离线验证 3.1 — 自动化实测结论

**(a) 静态核验（零外链）**

- **命令**：§1.1 ①（5 条 grep）
- **结果**：`<script src>` **0 处**、`<link href>` **0 处**、`@import` **0 处**、任何资源属性 `http(s)` 外链 **0 处**、CSS `url(http…)` **0 处** → **PASS，单文件自包含**（10 个 `<script>` 全内联，其中含完整 `chart.umd.js` 引擎，`sourceMappingURL=chart.umd.js.map` 内联可见）
- **证据**：`docs/tmp/rf113/static-selfcontained.log`

**(b) 断网打开照常渲染**

- **方法**：`chrome --headless=new --host-resolver-rules="MAP * ~NOTFOUND"`（全域名 DNS 失效）独立实例打开 `file://reports/个人投资分析报告.html`，CDP 采集全部网络请求 + console。
- **断言与结果**：
  - 图表渲染：**10/10 canvas 有 Chart 实例**，且 10/10 画布中部色带读到非透明像素（真实绘制）→ 过
  - 网络：仅 **1 条请求**（报告本身 `file://`），**外域请求 0 条** → 过
  - console error **0 条** → 过
  - 视觉证据：环形图（资产构成）完整渲染，含图例与「导出PNG」按钮
- **证据**：`docs/tmp/rf113/results/③-report-offline.json`、`docs/tmp/rf113/screenshots/07-report-offline.png`、`07b-report-offline-chart.png`
- **历史（已过项）**：3.2~3.4（删除/改名 `chart.min.js` → `typeof Chart` 双守卫静默跳过、无 JS 报错、真实报告回退明细表格）2026-08-06 另机已过（含 rf-249 口径修正），见归档清单 §③。

### ④ 微信内置浏览器实测 — 人工验证步骤（不可自动化）

- **不可自动化原因**：需要微信 App 真机 + 其内置 X5/系统 WebView 内核与「文件传输助手」分享链路，本机 headless Chromium 无法代跑；`file://` 沙箱行为也与微信内核版本强相关。
- **操作步骤与判定标准**（载体：真实报告，不用调试页——微信验证的是用户实际收到的报告）：

| # | 操作 | 判定标准 |
|:-:|:-----|:---------|
| 4.0 前置 | 菜单 **L/B** 生成一份完整报告，拿到 `reports/` 下 `.html` | 文件在手；`enable_interactive_charts` 默认开 |
| 4.1 链接访问 | 报告目录起静态服务：`.venv/bin/python -m http.server 8000`（或部署到 http/https）→ 电脑端微信发链接 / 手机与电脑同网直接访问 → 微信内点开 | **6 图渲染正常 + 悬停/点按有 tooltip** → 4.1 过 |
| 4.2 file:// 访问 | 报告 `.html` 经**文件传输助手**发到手机 → 微信内点开 | 图表渲染 → 4.2 过 |
| 4.3 file:// 兜底 | 若 X5 沙箱拦 `file://` 导致图表不渲染 | **页面无 JS 报错 + 明细表格兜底可读**（数据可读即可）→ 4.3 过 |
| 4.4 横竖屏 | 竖屏 ↔ 横屏切换，滚动浏览图表章节 | 图表自适应、**不横向溢出**（A4：`responsive + maintainAspectRatio`）→ 4.4 过 |
| **判定** | 4.1 过；且 4.2 / 4.3 **任一**过 → **④ 通过**；4.4 单独勾选 | 微信内触屏无 hover，图表退化为可读静态呈现属合理预期，不构成功能缺失（upgrade.md §4.14） |

- **本次状态**：⏳ 未执行（等真机人工）；完成后把结果回填归档清单 §④ 并更新 §3 总表。

### ⑤ 移动端 375px 适配 — 自动化实测结论

**（a）真实报告 → ✅ 通过**

- **方法**：CDP `Emulation.setDeviceMetricsOverride {width:375, height:900, deviceScaleFactor:2, mobile:true}` → 打开报告 → 展开全部 16 个章节 → 测 `documentElement.scrollWidth` vs 视口宽 + 溢出元素诊断 + 图表区截图。
- **断言与结果**：
  - 5.1 无横向滚动：`scrollWidth **375** == clientWidth **375**`（`body.scrollWidth=375`、`horizontalScroll=false`）→ **过**；10/10 图在 375px 下初始化成功、console error 0
  - 5.2 轴标签不重叠：折线图日期标签 45° 自动抽稀（12 档）、柱状图类目标签 45°（银行/电力/…/光伏设备）互不重叠 → **过**（`03c`/`03d` 截图）
  - 5.3 流式排列：图表容器随视口收缩；明细表格在自身 `overflow-x:auto` 容器内横向滚动（截图 `03b` 可见容器滚动条），**页面不被撑破** → **过**
  - 溢出诊断里的 3203 个「超视口元素」全部是滚动容器内的宽表格节点，属容器内滚动，不产生文档级横向滚动条（以 `scrollWidth<=clientWidth` 为判据）
- **证据**：`docs/tmp/rf113/results/⑤-report-375px.json`、`screenshots/03-report-375.png`、`03b-report-375-chart.png`、`03c-report-375-line.png`、`03d-report-375-bar.png`

**（b）调试页 `test-chart.html?s=ok` → ❌ 5.1 不过（调试页自身溢出，见 §4 发现 1）**

- **结果**：375px 下 `documentElement.scrollWidth **436** > clientWidth **375**`（`body.scrollWidth=420`），出现文档级横向滚动；6 图本身渲染正常（6/6 ok badge）、console error 0。
- **根因**：调试页 `.grid { grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)) }` → 图卡最小 420px + 左右 16px 边距 = 436px，放不进 375px 视口。
- **影响面**：仅调试页布局，**不涉及报告产物**；rf-113 ⑤ 的验证对象是报告 → ⑤ 按报告判过，调试页问题单列（待父级编号）。
- **证据**：`docs/tmp/rf113/results/⑤-testchart-375px.json`、`screenshots/02-testchart-375.png`、`02b-testchart-375-chart.png`（截图可见卡片右侧被裁）

### ⑥ 禁用 Canvas 后 fallback — 自动化实测（表现记录型）+ 人工步骤

- **方法（自动化模拟）**：`Page.addScriptToEvaluateOnNewDocument` 注入 `HTMLCanvasElement.prototype.getContext = () => null`（现代浏览器无「禁用 Canvas」开关时的标准模拟），打开真实报告并展开全部章节，逐条记录实际表现。
- **实际表现（按实测写，rf-249 口径复核成立）**：

| 观察点 | 实测结果 |
|:-------|:---------|
| 引擎加载 | ✅ `typeof Chart !== 'undefined'`（引擎照常加载，只是拿不到 2D 上下文） |
| 图表初始化 | ❌ **0/10**（`Chart` 创建失败） |
| console | ⚠ **10 条** `Failed to create chart: can't acquire context from the given item`（Chart.js `console.error`；系模拟破坏 `getContext` 所致，非新增缺陷） |
| canvas 内 fallback 文本 | DOM 中 **10/10 存在**（如「图表无法显示，数据见持仓分类表」），但 `Range.getClientRects()` = **0 → 文本不渲染**，**图表区域空白**（截图 `06b`：原环形图位置空白、上方明细表完整） |
| 明细表格兜底 | ✅ **41 张**可见表格，浅色下文字可读（截图 `06b`） |
| 页面其余交互 | ✅ 折叠 `details` 正常开合、主题切换/TOC 结构在位——图表失败**不拖垮整页** |

- **判定（按 rf-249 修正后的口径）**：
  - 6.1 原文断言「6 图区域显示内嵌 fallback 文本」在现代 Chrome **不成立**（不渲染 canvas 内文本）；**实际兜底 = 图表区空白 + 明细表格可读** → 兜底机制成立，6.1 按修正口径记录为「实测完成，原文断言已修正」。
  - 6.2「fallback 文本对比度 ≥4.5:1」因文本不渲染 **不适用**；替代口径「浅色模式下兜底数据可读」→ 明细表格可读（`06b`），✅。
- **证据**：`docs/tmp/rf113/results/⑥-report-no-canvas.json`、`screenshots/06-report-no-canvas.png`、`06b-report-no-canvas-chart.png`
- **人工复核步骤（可选，保留原清单口径）**：
  1. 若所用 Chrome 版本 DevTools 设置里存在 **Disable canvas** 复选项 → 勾选后刷新报告 → 对照上表逐条核对（图表区空白 + 表格兜底 + 页面可用）→ 测完取消勾选。
  2. 若设置项不存在（新版本 DevTools 可能已移除）→ 直接复跑本脚本场景 ⑥：`node docs/tmp/rf113/run-rf113.mjs`，或把覆写 script 注入本地副本 html 后人工打开，判定标准同上表。
- **历史（已过项）**：3.4「现代浏览器不渲染 `<canvas>` fallback 文本、真实报告回退明细表格」2026-08-06 已按实测修正（rf-249），本次自动化复核与之一致。

---

## 3. 六项状态总表（含历史已过项与日期）

| 项 | 标题 | 结果 | 说明与证据 |
|:--:|:-----|:----:|:----------|
| ① | 6 图渲染 + 交互（验收 2） | ✅ **通过** | 2026-08-06 Windows Chrome+Firefox 人工全过（tooltip/降级/空数据/离线守卫）；**2026-10-09 headless Chromium 148 自动化回归**：`?s=ok` **6/6 badge ok**、横幅 ok、console 0 error。`results/①-testchart-ok-badge.json`。Safari 抽验仍属人工（不阻塞） |
| ② | 打印降级（验收 3） | ✅ **通过** | 2.1~2.3 2026-08-06 人工过（2x DPI / 浅色 / 不跨页）；**2.4 2026-10-09 自动化过**：beforeprint 插入 10 张 2x 快照 + 10/10 canvas 隐藏 → afterprint 移除 0 残留、几何 0px 偏差、真实 hover tooltip 恢复（active 2→2）、console 0。附观察：内联 `display block→''`（§4 发现 2）。真实 `Ctrl+P` 分页效果仍以人工预览为准（历史已过）。`results/②-report-afterprint.json` |
| ③ | 离线验证（验收 4 / R21） | ✅ **通过** | 3.2~3.4 2026-08-06 人工过（引擎缺失守卫）；**3.1 2026-10-09 自动化过**：静态 5 类外链全 0（PASS）+ `--host-resolver-rules=MAP * ~NOTFOUND` 断 DNS 打开 → 10/10 图渲染且有绘制像素、外域请求 0、console 0 error。`static-selfcontained.log` + `results/③-report-offline.json` |
| ④ | 微信内置浏览器（验收 6 / R22） | ⏳ **待人工（不可自动化）** | 需微信真机 X5/内核 + 文件传输助手链路。步骤与判定见 §2④（4.1 链接访问必过；4.2 file:// 或 4.3 兜底任一过即 ④ 通过；4.4 横竖屏不溢出） |
| ⑤ | 移动端 375px 不溢出（A4） | ✅ **通过（报告产物）** | **2026-10-09 自动化**：报告 375px `scrollWidth==clientWidth==375` 无横向滚动、10/10 图初始化、轴标签 45° 不重叠、表格容器内滚动不撑破页面。**附带发现**：调试页 `test-chart.html` 375px 自身溢出 61px（`minmax(420px,1fr)`，§4 发现 1，仅调试页）。`results/⑤-report-375px.json` / `⑤-testchart-375px.json` |
| ⑥ | 禁用 Canvas 后 fallback（A1） | ⚠️ **实测完成（断言口径已修正）** | **2026-10-09 自动化**：原断言「canvas 显示 fallback 文本」**不成立**（文本在 DOM 但不渲染，rf-249 复核）；实际表现 = 0/10 图初始化 + 图表区空白 + **41 张明细表格兜底可读** + 页面其余交互正常 + console 10 条（模拟所致）。6.2 因文本不渲染不适用，浅色兜底可读 ✅。可选人工 DevTools 复核步骤见 §2⑥。`results/⑥-report-no-canvas.json` |

**自动化断言合计**：5 场景 PASS / 1 场景 FAIL（调试页 ⑤，另列缺陷）/ 1 场景表现记录（⑥）；**人工余项**：④ 微信真机（+ ① Safari 抽验、② 真实 `Ctrl+P` 分页抽验，均不阻塞）。

---

## 4. 本次实测发现（描述，未编号）

**发现 1（影响 ⑤ 调试页，不影响报告）：`test-chart.html` 在 375px 视口横向溢出 61px。**

- 现象：375px 设备模拟下 `documentElement.scrollWidth=436 > clientWidth=375`（`body.scrollWidth=420`），整页出现横向滚动条；6 图渲染本身正常。
- 根因：调试页 `.grid { grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)) }` —— 图卡最小宽 420px + `body` 左右 16px 边距 = 436px，列宽无法收缩到 375px。
- 影响面：仅 TD8/S2 调试页布局，报告产物在 375px 下实测无溢出（见 §2⑤a）。清单 5.1 若按调试页走查会误判为报告缺陷，建议后续把 5.1 的执行载体明确为报告 HTML（或顺手把调试页 `minmax` 降到 ≤343px，如 `minmax(min(420px, 100%), 1fr)`）。
- 处置：**未自行修复/编号**，交由维护者登记。

**发现 2（轻微，影响 ② 观察项）：`chart-print.js` 的 afterprint 恢复把 canvas 内联 `display` 置空而非还原原值。**

- 现象：Chart.js v4.4.3 初始化时给 canvas 写入内联 `display:block; box-sizing:border-box`（实测打印前 10/10 为 `block`）；`afterprint` 走 `restoreFromPrint()` 的 `canvas.style.display = ''` → 内联值变 `''`，computed `display` 由 `block` 变为 `inline`。
- 实测影响：canvas **可见**（≠ none）、**文档坐标几何偏差 0px**、tooltip 交互正常恢复——当前无可见布局位移；但内联样式与打印前不一致（inline 替换元素依赖基线排版，主题/容器样式变化时可能出现细微行高间隙），属「恢复不精确」而非功能失效。
- 可选修复方向（未实施）：`beforeprint` 时记录原 `display` 值、`afterprint` 按记录还原（`canvas.style.display = saved`），或统一恢复为 `'block'`。
- 处置：**未自行修复/编号**，交由维护者登记。

**记录 3（非缺陷，供口径对齐）：⑥ 场景 console 的 10 条 `Failed to create chart` 属模拟产物。** 真实环境无法「禁用 Canvas」（无该开关），此错误只在注入 `getContext→null` 时出现；⑥ 的判定只看「兜底数据可读 + 页面不垮」，不以 console 零错误为口径。

---

## 5. 复验清单（报告模板 / chart-*.js / Chart.js 升级后）

1. 静态零外链：§1.1 ①（5 条 grep，全 0 即过）。
2. `node docs/tmp/rf113/run-rf113.mjs` → 对照 §1.1 输出摘要：①/⑤-report/②/③ 必须 PASS；⑤-testchart 仅在发现 1 修复后才会 PASS；⑥ 看 §2⑥ 表逐条。
3. 手工抽验（headless 覆盖不到的）：真实 `Ctrl+P` 预览（2.1~2.3 口径）、微信真机（④ 全套）、Safari 抽验。
4. 结论回填：归档清单勾选 → `changelog.md` 记录 → `review-findings.md` rf-113 状态更新（由维护者执行，回填依据为本文件的总表与实测记录）。
