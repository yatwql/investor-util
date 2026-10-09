# Web 模式浏览器真机验证方法与实测结论（rf-257 五类 UX 项）

> **关联**：`docs/managements/review-findings.md` → **rf-257**（plan-8 Web 模式浏览器真机人工验收）；勾选清单 [`docs/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`](../archive/v0.10.x/web-ui/web-ui-verification-checklist.md)（①~⑤ 五类、逐步操作与判定标准）；启动方式见 [`docs/manuals/how-to-use-web-mode.md`](../manuals/how-to-use-web-mode.md) §1。
> **目的**：把五类验收项拆成「**可自动化的实测项**」与「**必须人工的项**」，并留下可复现的验证方法与本次实测结论——后续 Web UI 改动复验时直接复用本方法（脚本与产物在 `docs/tmp/rf257/`，git 忽略，重跑即重建）。
> **本次实测**：2026-10-09 · 本机 headless Chromium **148.0.7778.96**（`~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`）· Node **v22.23.1** 全局 WebSocket 直连 CDP · 服务 `v0.12.7-dev`。
> **红线遵守**：全程 **0 次真实 `POST /api/runs`**（浏览器侧 CDP 捕获 0 次 + 服务端 `server.log` 中 `POST /api/runs` 出现 0 次）；不改 `data/config/`、`data/holdings/` 正式持仓；上传测试仅落到 `data/holdings/uploads/` 临时区（测后已清空还原）。本次按任务约束**未跑 `scripts/check-*.py` 守护、未 `git add/commit`、未改 `docs/managements/`**（rf-257 台账由维护者回填）。

---

## 1. 启动与前置

### 1.1 环境与启动命令（可复现）

```bash
# ① 选空闲端口并启动本地 Web 服务（手册 §1「手动启动」；--port 可换端口）
PORT=$(.venv/bin/python -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")
nohup .venv/bin/python -m src.python.web --port "$PORT" > docs/tmp/rf257/server.log 2>&1 &
SERVER_PID=$!                      # 记录 PID，验证结束必须 kill
echo "$PORT" > docs/tmp/rf257/port.txt; echo "$SERVER_PID" > docs/tmp/rf257/server.pid

# ② HTTP 层证据（Flask test_client 进程内链路，不占端口、不发外网、mock 管线）
.venv/bin/python scripts/smoke-web.py           # 预期 11/11，退出码 0

# ③ 启动无头 Chromium（独立 user-data-dir，避免污染日常浏览器）
CHROME=$HOME/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome
CDP_PORT=$(.venv/bin/python -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")
nohup "$CHROME" --headless=new --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$PWD/docs/tmp/rf257/chrome-profile" --no-sandbox --disable-gpu \
  --disable-dev-shm-usage --no-first-run --window-size=1280,900 about:blank \
  > docs/tmp/rf257/chrome.log 2>&1 &

# ④ 跑自动化实测（Node 22 全局 WebSocket 直连 CDP）
RF257_BASE="http://127.0.0.1:$PORT" RF257_CDP_HTTP="http://127.0.0.1:$CDP_PORT" \
  node docs/tmp/rf257/cdp-check.mjs            # 输出逐项 [PASS]/[FAIL]/[MANUAL] + cdp-report.json
# 可选：⑤ 真实鼠标 hover 复核（会先自动上传一次使「生成报告」按钮可用）
RF257_BASE="http://127.0.0.1:$PORT" RF257_CDP_HTTP="http://127.0.0.1:$CDP_PORT" \
  RF257_FIXTURES="$PWD/docs/tmp/rf257" node docs/tmp/rf257/cdp-hover-debug.mjs

# ⑤ 收尾（必做）：杀浏览器、杀服务、清上传临时区
kill "$SERVER_PID"  <chrome_pid>
ls data/holdings/uploads/     # 应为空；有残留则删除本次测试产生的 uuid 文件
```

本次实测参数：服务端口 `39445`（PID 3040331）、CDP 端口 `54333`（Chrome PID 3042330），验证结束均已 `kill`，`data/holdings/uploads/` 已清空还原。

### 1.2 前置断言（每次复验先看这三条）

| 前置 | 判定 | 本次结果 |
|:-----|:-----|:--------|
| `GET /`、`/static/style.css`、`/static/main.js` 均 200 | curl 三条均为 200 | ✅ |
| `scripts/smoke-web.py` 11/11 | 退出码 0 | ✅ 11/11（证据 `docs/tmp/rf257/smoke-web.log`） |
| 未触发报告生成 | 浏览器侧 `Network.requestWillBeSent` 统计 `POST /api/runs`=0；服务端日志 `grep -c "POST /api/runs" server.log`=0 | ✅ 双侧均为 0 |

### 1.3 自动化脚本覆盖的检查点

`docs/tmp/rf257/cdp-check.mjs`（**37 项断言**：33 过 / 2 不过 / 2 人工，全部中文输出）关键技术手段：

- **Console/异常**：`Runtime.consoleAPICalled(error)` + `Runtime.exceptionThrown` + `Log.entryAdded(error)`（域启用后先清缓冲再导航，避免上一页回放污染）。
- **Network**：`Network.responseReceived` 记录全部状态码；`Network.setCacheDisabled` 保证读到当前版本静态资源。
- **首屏占位态**：`Fetch.enable` 暂扣 `*api/runs/history*` 与 `*api/health`，使首屏时点能观察到「加载中…」「正在检测...」占位（本机回环过快，不暂扣会错过）。
- **上传状态文案**：页面内 `MutationObserver` 记录 `#upload-status` 全部文本变更（否则 10ms 内完成的 busy 态采不到）。
- **文件注入**：`DOM.setFileInputFiles` 塞入本地 fixture（只到上传层，不提交运行）。
- **hover**：`Input.dispatchMouseEvent` 真实鼠标移动（先 `scrollIntoView` 再取坐标，避免元素在视口外导致真实 hover 落空——首版脚本未滚动时的偶发不落地属测试工件）+ `CSS.forcePseudoState` 强制 `:hover` 兜底（确定性判据），两口径交叉验证。
- **375px**：`Emulation.setDeviceMetricsOverride {width:375, mobile:true}` 后读 `documentElement.scrollWidth/clientWidth`、卡片矩形、控件矩形。

### 1.4 测试用文件（`docs/tmp/rf257/`，git 忽略）

| 文件 | 用途 |
|:-----|:-----|
| `valid_holdings.xlsx` | 合法最小持仓（四列 + 1 行，openpyxl 构造）——上传成功路径 |
| `fake_not_excel.xlsx` | 文本改 `.xlsx` 后缀 —— 上传非法文件中文报错 |
| `empty.xlsx` | 0 字节 `.xlsx` —— 上传空文件中文报错 |
| `cdp-check.mjs` / `cdp-report.json` / `cdp-run.log` | 自动化实测脚本 / 结构化结论 / 逐项输出 |
| `cdp-hover-debug.mjs` / `hover-debug.json` | ⑤ 真实鼠标 hover 复核（4 个按钮 + 375px 复测） |
| `cdp-overflow-debug.mjs`、`cdp-mincontent-debug.mjs`、`cdp-wrap-debug.mjs`（`overflow-debug.log`、`mincontent-debug.json`、`wrap-debug.json`） | ④ 375px 溢出的根因定位探针 |
| `smoke-web.log`、`server.log`、`chrome.log` | HTTP 层冒烟 / 服务端日志（含 0 次 `POST /api/runs` 佐证）/ 浏览器日志 |

---

## 2. 逐项结论

> 每项标注 **【自动化实测结论】**（命令 + 证据路径，本次已跑）或 **【人工验证步骤】**（操作 + 判定标准，本次未跑）。

### ① 页面渲染（rf-274 回归确认）

| 清单项 | 类型 | 结论与证据 |
|:------|:----|:----------|
| 1.1 样式生效 + 7 卡齐全 | 自动化 | **过**。`getComputedStyle` 抽查 `section.card`：`border-radius=8px`、`background=rgb(255,255,255)`、`box-shadow=rgba(31,35,40,.05)…`，`body` 背景 `rgb(243,245,248)`（非浏览器默认白底黑字）；`styleSheets` 含 `/static/style.css?v=0.12.7-dev` 且解析出 **171 条规则**。7 卡按 `h2` 圆圈序号齐备：`① 上传持仓｜② 生成报告｜④ 生成进度｜⑤ 生成结果｜③ 配置编辑｜⑥ 运行状态｜⑦ 日志查看`（DOM 顺序 ①②④⑤\|③\|⑥⑦，分属不同页签，属预期结构）。证据 `cdp-run.log` 1.1a/1.1b/1.1c |
| 1.2 main.js 生效（配置面板 / 健康 / 最近运行） | 自动化 | **过**。`#config-panel` 子节点 9、可交互控件 63（面板自动渲染）；`#health-list` 首屏「正在检测...」→ 12 行实际探测结果（含耗时）；`#history-list` 首屏「加载中...」→ 自动加载出最近运行记录。证据 `cdp-run.log` 1.2a/1.2b/1.2c |
| 1.3 页头应用名 + 版本 + 副标题 | 自动化 | **过**。`h1=投资复盘助手`、`subtitle=v0.12.7-dev · 上传持仓 Excel…`、`document.title=投资复盘助手 v0.12.7-dev`。证据 `cdp-run.log` 1.3 |
| 1.4 Console 无 JS 报错 | 自动化 | **过**。页面加载 + 全程交互：`console.error=0`、`exceptionThrown=0`、`Log(error)=0`（仅刻意负面上传产生 2 条「400 /api/upload」网络日志，属预期负向用例）。证据 `cdp-run.log` 1.4 |
| 1.5 Network 无 404（尤其 main.js/style.css） | 自动化 | **过**。`/static/main.js→200`、`/static/style.css→200`（另有一次 304 复用）；**非预期 4xx/5xx = 0**（仅 `POST /api/upload→400` ×2 为刻意负向用例；本机 headless 未请求 `/favicon.ico`）。证据 `cdp-run.log` 1.5a/1.5b —— **rf-274 回归确认闭合** |

**① 判定：通过**（5/5 过，全部自动化实测）。

### ② 上传表单 UX

| 清单项 | 类型 | 结论与证据 |
|:------|:----|:----------|
| 2.1 选 .xlsx 后显示文件名与结果 | 自动化 | **过**。`DOM.setFileInputFiles` 注入 `valid_holdings.xlsx` → `#upload-status` = 「上传成功：1 个账户，共 1 条持仓，可生成报告」。证据 `cdp-run.log` 2.1 |
| 2.2 只接受 `.xlsx` | 自动化 | **过**。`#file-input` 的 `accept=".xlsx"`；改后缀/空文件被服务端 400 拒绝（见 2.4）。证据 `cdp-run.log` 2.2a |
| 2.3 上传中/成功/失败文案 | 自动化 | **过**。MutationObserver 完整序列：`""` → `status-busy「正在上传并校验 valid_holdings.xlsx ...」`（约 2ms）→ `status-ok「上传成功：…」`（约 10ms）；失败态见 2.4（`status-error`）。证据 `cdp-run.log` 2.3a/2.3b |
| 2.4 非法文件中文报错 | 自动化 | **过**。文本改后缀 → `status-error`「**文件内容不是有效的 Excel（xlsx）格式**」；0 字节 `.xlsx` → 同样中文报错（非静默失败）。证据 `cdp-run.log` 2.4/2.4b |
| 2.5 拖拽视觉反馈 | 自动化（合成事件） | **过（合成事件口径）**。派发 `dragover` → `.upload-zone` 获得 `drag-over` 类，样式 `rgba(0,0,0,0)\|rgb(217,220,225)` → `rgb(232,241,251)\|rgb(31,111,178)`（背景/边框变品牌蓝）；派发 `dragleave` 类移除。**真实 OS 拖拽留人工抽验**（步骤见 §2-② 末）。证据 `cdp-run.log` 2.5 |
| 2.6 键盘可达性 | 自动化（可达性） | **过（可达性口径）**。`#file-input` 为 `tabIndex=0`、`display:block/visibility:visible`（sr-only 用 `clip` 而非 `display:none`），`focus()` 后 `document.activeElement` 即该 input。**真实 Tab 序列 + Enter 弹文件框留人工抽验**。证据 `cdp-run.log` 2.6 |

**【人工验证步骤】**（真实拖拽与键盘全流程）：① 打开首页 → 鼠标拖住任意 `.xlsx` 移入上传区 → 判定：上传区边框变蓝、底色变浅蓝、抬起后回落并触发上传；② `Tab` 依次聚焦到上传 input → 判定：出现焦点轮廓、按 `Enter` 弹出文件选择框、选中文件后状态区出现 busy → ok 文案。

**② 判定：通过**（2.1~2.4 全自动化；2.5/2.6 自动化覆盖处理器与可达性，真实交互建议人工抽验 1 次）。

### ③ 进度事件可视化

| 清单项 | 类型 | 结论与证据 |
|:------|:----|:----------|
| 3.1a 初始隐藏 | 自动化 | **过**。首屏 `#progress-section`、`#result-section` 均带 `hidden`（未提交前不出现）。证据 `cdp-run.log` 3.1a |
| 3.1b 静态初始态 | 自动化 | **过**。`#progress-bar`：`role=progressbar`、`aria-valuenow=0`、`aria-valuemin/max=0/100`；`#progress-phase` =「准备中...」；`#progress-events` 空 `<ol>`。证据 `cdp-run.log` 3.1b |
| 3.3a 显隐逻辑 | 自动化 | **过（DOM 口径）**。脚本移除 `hidden` 后卡片真实可见（高度 139.9px、进度轨宽 = 容器宽、可渲染进度条），恢复 `hidden` 后回到隐藏。证据 `cdp-run.log` 3.3a |
| 3.1c/3.2/3.3 提交后进度推进与事件追加 | **人工** | 需真实 `POST /api/runs`（本次红线禁止）。**已有证据**：`scripts/smoke-web.py` 第 4/5/6 项断言 `202 → GET events 非空且 status 可达 done → GET run 完成态 exit_code=0`（`docs/tmp/rf257/smoke-web.log`）。**完整进度观察需人工跑一次 basic** |
| 3.4 full 全程可观察 | **人工** | 同上，需人工跑一次 full（约 5 分钟） |
| 3.5 生成期间按钮禁用 | **人工** | 与 5.3 同一代码路径（`onSubmit` 同步置 `disabled + aria-busy`），本次不实际提交 |

**【人工验证步骤】**：① 首页上传合法 `.xlsx` → 报告格式选「仅 Excel（约 1 分钟）」→ 点「生成报告」；② 判定：**进度卡自动出现**（不再 hidden）、进度条从 0% 起步、阶段文案实时变化（「当前阶段（第 N 步）：…」）、事件流 `<ol>` 逐条追加且可滚动、`aria-valuenow` 递增；③ 判定：生成期间「生成报告」按钮灰显禁用（文案「正在提交…/生成中...」），完成后恢复、结果卡出现「报告生成成功」+ 预览/下载按钮；④ 抽验 full：进度持续可观察、非「转圈后直接跳结果」。

**③ 判定：部分自动化**（静态初始态 + 显隐逻辑自动化过；真实生成过程以 smoke-web 事件流断言为已有证据，完整视觉观察待人工跑一次 basic/full）。

### ④ 375px 响应式

| 清单项 | 类型 | 结论与证据 |
|:------|:----|:----------|
| 4.1 无横向滚动 | 自动化 | **不过**。375px 设备模拟下 `documentElement.clientWidth=375`、`scrollWidth=421`、`body.scrollWidth=404` → **存在横向滚动**（`hScroll=true`）。证据 `cdp-run.log` 4.1、`overflow-debug.log` |
| 4.2 卡片单列不超容器 | 自动化 | **过**。生成页签可见卡片各 343px 宽、`left=16/right=359`、自上而下单列堆叠、均不超 375。证据 `cdp-run.log` 4.2 |
| 4.3 表单控件不溢出 | 自动化 | **不过**。`select#report-type` 矩形 `left=41 → right=404`（**超出视口 29px**）；同列的 `check-label`/`radio-label` 一并被撑到 `right=404`。证据 `cdp-run.log` 4.3、`mincontent-debug.json`、`wrap-debug.json` |
| 4.4 ⑥ 状态网格降单列 | 自动化 | **过**。⑥ 页签 `status-grid-3` 在 375px 下 `grid-template-columns="293px"`（**1 列**），`scrollWidth=375 ≤ clientWidth=375` 无溢出。证据 `cdp-run.log` 4.4 |
| 4.5 结果区预览/下载按钮 | **人工** | 结果卡需真实生成产物才渲染按钮（本次禁 `POST /api/runs`） |

**根因（自动化探针定位，见 §4 缺陷 1）**：`min-content` 探针显示生成页签表单最小内容宽 **363px**，全部来自「正式更新」radio 的文案 —— 其中绝对持仓路径 `/lzcapp/.../data/holdings/个人投资持仓信息.xlsx` 无断词机会（`min-content=369px`；`overflow-wrap:break-word` 无效 369px，`overflow-wrap:anywhere`/`word-break:break-all` 可降到 16~32px）。

**【人工验证步骤】**：`F12` → `Ctrl+Shift+M` → 选 iPhone SE（375×667）→ 判定：**4.1** 页面无横向滚动条；**4.3** 报告格式下拉、复选/单选、按钮均可点选不溢出；**4.5** 跑一次 basic 后 ⑤ 结果区「预览/下载」按钮可点击、不重叠；**4.4** 切「运行状态」页签确认网格单列 → 退出设备模式。

**④ 判定：不过（部分自动化）** —— 4.2/4.4 过，**4.1/4.3 不过（真实响应式缺陷，见 §4）**，4.5 待人工。

### ⑤ 按钮态

| 清单项 | 类型 | 结论与证据 |
|:------|:----|:----------|
| 5.1 初始 disabled | 自动化 | **过**。DOMContentLoaded 时点 `#generate-btn.disabled=true`；disabled 视觉 `opacity=0.5`、`cursor=not-allowed`。证据 `cdp-run.log` 5.1/5.1b |
| 5.2 上传 + 选格式后可点 | 自动化 | **过**。合法上传成功后 `disabled=false`（格式默认已选 basic）。证据 `cdp-run.log` 5.2 |
| 5.3 点击生成后转禁用 | **人工** | 需真实提交（本次红线禁止，不实际提交生成）。代码路径：`onSubmit` 先 `disabled=true` + `aria-busy=true` + 文案「正在提交...」 |
| 5.4 次级按钮 hover + 点击动作 | 自动化 | **过**。**真实鼠标**（`cdp-hover-debug.mjs`：`Input.dispatchMouseEvent` + 先 `scrollIntoView` 保证元素在视口内）4/4 按钮命中且移出后还原：`#generate-btn` 背景 `rgb(31,111,178) → rgb(24,90,146)`（`--primary → --primary-hover`，按钮已处于可用态）、`#config-reload`/`#health-refresh`/`#log-load` 边框 `rgb(217,220,225) → rgb(31,111,178)`，`:hover` 链逐级命中目标按钮；**375px 下** `#health-refresh` 真实 hover 同样命中。另以 `CSS.forcePseudoState` 强制 `:hover` 作为确定性兑底口径亦全部命中。**点击动作**：「刷新」→ 缓存统计回填（`306 个`）、**「加载日志」→ 日志列表真实加载**（只读 `GET`）。证据 `cdp-run.log` 5.4a/5.4b/5.4c/5.4d + `hover-debug.json`。注：「清理过期」会写 `data/cache/`，本次不点，留人工 |
| 5.5 加载态占位非空白 | 自动化 | **过**。首屏时点（Fetch 暂扣响应保证可观察）`#health-list`「正在检测...」、`#history-list`「加载中...」。证据 `cdp-run.log` 5.5 |
| 5.6 正式更新未确认被拦 | 自动化 | **过**。切到「正式更新」→ `#formal-options` 展开、未勾选「我已知晓」时 `disabled=true`（提交被拦）；勾选后 `disabled=false`；切回试算 → 展开区收起、确认勾选自动清除。证据 `cdp-run.log` 5.6 |

**【人工验证步骤】**：① 未上传时确认「生成报告」灰显不可点；② 上传后变可点、hover 变深蓝；③ 选「正式更新」不勾确认 → 按钮灰显、点击无反应；④ 点一次「生成报告」→ 立即转禁用 +「正在提交...」，完成恢复（此项会真实生成，请按需选择 basic）；⑤ 「重新检测/刷新/加载日志」hover 有反馈且点击有响应。

**⑤ 判定：通过（5.3 留人工）** —— 5.1/5.2/5.4/5.5/5.6 全自动化过。

---

## 3. 五类状态总表

| 项 | 标题 | 结果 | 说明与证据 |
|:--:|:-----|:----:|:----------|
| ① | 页面渲染（JS/CSS 加载） | ✅ **通过（全自动化）** | 5/5；`/static/main.js`、`/static/style.css` 均 200、171 条规则、Console 0 error → **rf-274 回归闭合**。`docs/tmp/rf257/cdp-run.log` 1.1a~1.5b |
| ② | 上传表单 UX | ✅ **通过（2.1~2.4 全自动化；2.5/2.6 合成事件+可达性口径）** | accept 断言 + 合法/非法/空文件三路径状态文案；真实拖拽、真实 Tab/Enter 留人工抽验。`cdp-run.log` 2.1~2.6 |
| ③ | 进度事件可视化 | 🟡 **部分自动化** | 静态初始态 + 显隐逻辑过（3.1a/3.1b/3.3a）；真实进度以 smoke-web 第 4/5/6 项为已有证据，**完整进度观察需人工跑一次 basic**（full 抽验）。`cdp-run.log` 3.1a~3.3a + `smoke-web.log` |
| ④ | 375px 响应式 | ❌ **不过（部分自动化）** | 4.2/4.4 过；**4.1、4.3 不过**：375px 下横向滚动（`scrollWidth 421 > 375`）、报告格式 select `right=404` 溢出 29px，根因见 §4 缺陷 1；4.5 结果区按钮待人工。`cdp-run.log` 4.1~4.4 + `overflow-debug.log` |
| ⑤ | 按钮态 | ✅ **通过（5.3 留人工）** | 5.1/5.2/5.4/5.5/5.6 自动化过（真实鼠标 hover 4/4 按钮命中 + `forcePseudoState` 双口径，含 375px 复测）；5.3 提交即禁用需人工跑一次生成。`cdp-run.log` 5.1~5.6 + `hover-debug.json` |

自动化断言合计：**33 过 / 2 不过 / 2 人工**（`cdp-run.log` 末尾 `{"pass":33,"manual":2,"fail":2}`）。

---

## 4. 本次实测发现（描述，未编号）

**发现 1（阻断 ④）：375px 下页面横向滚动，根因是「正式更新」radio 文案中的绝对持仓路径不可断行。**

- 现象：375px 设备模拟下 `documentElement.scrollWidth=421 > clientWidth=375`（`body.scrollWidth=404`；裸加载状态的 `overflow-debug.log` 为 `scrollWidth=404`，差异来自交互后 DOM 状态，两种口径均 > 375），生成页签整列表单控件被撑到 `right=404`，`select#report-type` 超出视口 29px → 出现横向滚动条（清单 4.1、4.3 不通过）。
- 根因探针（`mincontent-debug.json` / `wrap-debug.json`）：
  - `#generate-form` 的 `min-content=363px`，其中 `DIV.field-block > LABEL.radio-label > SPAN`（文本「正式更新 —— 覆盖 `/lzcapp/document/working/codebase/investor-util/data/holdings/个人投资持仓信息.xlsx`，快照共享生效」）`min-content=369px`；
  - 断词规则对照：默认 `369px`、`overflow-wrap:break-word` **369px（无效）**、`overflow-wrap:anywhere` 16px、`word-break:break-all` 32px；
  - 溢出随**安装路径长度**变化：路径越长越容易溢出（本机路径较长），换一台路径短的机器可能暂时不复现——结构性风险仍存在。
  - 连带：调仓模拟页签 `用当前正式持仓文件（<路径>）` 的 `min-content=385px`，且原生 file input `#whatif-cand-input` 内在宽 **347px > 可用 293px**（与路径无关，任何机器 375px 打开该页签都会溢出）。
- 可选修复方向（未实施，供决策）：给长路径文案加 `overflow-wrap: anywhere`（或 `word-break: break-all`）、给 `select`/`input[type=file]` 加 `max-width: 100%`（本次已在页面内临时验证 `max-width:100%` 对 select 无效——因为 select 是被上层撑宽的，须断在文案处）。

**发现 2（低，观察项）：浏览器对 `/favicon.ico` 的默认探测。** 本机 headless Chromium 本次未发起 favicon 请求（`favicon 404×0`），但用 `curl` 直接访问返回 404；若某些浏览器/标签页请求 favicon，Network 会出现一条 404。是否补一个 favicon 由维护者决定（不影响清单判定，本清单只看应用资源）。

**发现 3（低，观察项）：`data/holdings/uploads/` 为上传临时区。** 测试上传会在此生成 uuid 文件（1h TTL 自动清理）；复验脚本结束时应清空，避免残留干扰「不改 `data/holdings`」约束。

---

## 5. 复验清单（Web UI 改动后）

1. 跑 §1.1 启动 → `scripts/smoke-web.py` 11/11 → `node docs/tmp/rf257/cdp-check.mjs`。
2. 对照 §3 总表：①②⑤ 应保持全过；③ 静态项应过（真实进度人工抽验 basic）；④ 应在修复后转为全过（重点看 4.1/4.3 的 `scrollWidth` 与控件 `right` 值）。
3. 结论回填 `review-findings.md` rf-257 行与归档清单状态行；本文件仅维护方法与实测数据，不承载台账状态。
4. 收尾必做：`kill` 服务与浏览器 PID、清空 `data/holdings/uploads/`、确认 `server.log` 无 `POST /api/runs`。
