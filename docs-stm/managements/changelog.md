# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.12-dev] - 开发中（未发布）

### 应用更名「投资复盘助手」（2026-08-07）

- **`core/constants.py` `APP_NAME` 值由「个人投资分析报告生成小助手」改为「投资复盘助手」**：单一来源常量，一处修改即全链生效（TUI 首页 / 启动日志 / Web 首页 / HTML 报告 / Excel 报告 / What-if 报告 / cli/server 帮助描述 / test_runner 报告页脚）。
- **程序内散落旧名全部改为引用 `APP_NAME` 常量**：`cli.py`/`server.py` argparse description、`scripts/test_runner.py` 报告页脚（补 sys.path 注入 + `from src.python.core.constants import APP_NAME`）、`test_tui_menu.py` 断言（`assertIn(APP_NAME, …)` 替代硬编码字符串）。
- **文档全局替换**：README / CLAUDE.md / plan / testplan / requirements / technical / review-findings 标题与正文（R-TUI-01、rf-265 行）中的旧名统一改为「投资复盘助手」；`pyproject.toml` description 同步更新。
- **说明**：报告输出文件名（`个人投资分析报告.xlsx/html`）是报告产品名，不属于应用名，**不随更名变动**。

---

### 应用名称单一来源 + 各入口统一强调名称/版本（rf-265）（2026-08-06）

- **`core/constants.py` 新增 `APP_NAME = "投资复盘助手"`**：应用名称单一来源常量（零依赖模块，任何模块可直接引用），替代 TUI 首页硬编码。
- **应用启动日志**（`core/logger.py` `log_app_boundary`）：日志格式由「应用启动 | 版本 vX | 模式 | 主机 IP」改为「应用启动 | 投资复盘助手 vX | 模式 | 主机 IP」，CLI/TUI/Web 三入口启动/关闭日志统一强调名称+版本。
- **TUI 首页**（`tui_menu.py` `print_header`）：标题头由硬编码字符串改为引用 `APP_NAME`（`投资复盘助手  v{APP_VERSION}` 不变）。
- **Web 首页**（`web/handlers.py` `_handle_index` 传 `app_name` + `index.html`）：顶部 `<title>`/`<h1>` 改为应用名称，副标题前缀「v{app_version} ·」，浏览器标签页与页面头同时强调名称+版本。
- **HTML 报告首页**（`report_template.html` + `whatif_template.html`）：主报告头部加副标题「由 {app_name} v{app_version} 生成」，页脚改为「由 {app_name} v{app_version} 生成 · 个人投资分析报告 | 生成时间」；调仓 What-if 报告页脚加同款生成声明。
- **Excel 首页**（`report/summary.py` `_write_basic_info`）：投资分析汇总页签「统计时间/所属交易日」后新增「生成工具」行（`投资复盘助手 v0.10.12-dev`）。
- **测试**：`test_summary.py` 新增 生成工具行 用例、`test_handlers.py` 新增 首页标题名称+版本 用例、`test_html_writer.py` 补 `app_name` 透传断言、`test_tui_menu.py` 补版本断言。
- **门禁**：相关 212 用例全绿 + dev-verify + 4 checks `--ci` 全 [OK]。

---

### Web 首页系统信息卡对齐 TUI 首页摘要（rf-264）（2026-08-06）

- **`web/handlers.py` `_build_system_info` 增补配置摘要字段**：在既有 程序版本/本机 IP/LLM 状态 基础上，对齐 TUI `show_config()` 首页摘要——持仓目录 / 持仓文件 / 输出目录 / 新闻抓取上限（`news_top_count`）/ 状态（`os.path.exists` 判定持仓文件是否就绪）/ 持仓匿名化模式（`features.anonymization.mode` 中文映射）/ 隐私声明是否已显示（`get_flag("_privacy_notice_shown")`）。配置读取异常按默认值兜底，不阻断页面渲染。
- **`web/templates/index.html` 系统信息卡片补对应行**：新增 持仓目录 / 持仓文件 / 输出目录 / 新闻抓取上限 / 状态（文件就绪绿 / 未找到红，语义色对齐 TUI `[OK]`/`[!!]`）/ 持仓匿名化 / 隐私声明 行，LLM 状态行保留原有 flat/multi/未配置 分支。
- **`web/static/style.css` 补 `.system-status-ok` / `.system-status-err`** 状态色样式。
- **`src/test/unit/web/test_handlers.py` `TestSystemInfo` 新增 6 用例**（unit_web 标记，web 目录 89 用例）：配置摘要默认兜底 / 字段齐全且文件就绪 / 文件缺失未就绪 / `get_config` 异常兜底 / 索引页渲染摘要（就绪 + 缺失两态）。
- **门禁**：web 目录 89/89 passed + smoke-web 9/9 + dev-verify + 4 checks `--ci` 全 [OK]。

---

## [0.10.11] - 2026-08-06

### README 核心亮点总览重写（2026-08-06）

- **标题区简介重写**：从一句话简介升级为有感染力的总览——「把持仓 Excel 变成决策级投资洞察」，点明本地投资分析引擎、对接中国金融数据源、穿透组合底层资产、融合量化指标/基金评级/LLM 智囊团深度复盘、产出图表丰富的 HTML 报告与专业的 Excel 报告。
- **新增「✨ 核心亮点」总览表**（5 行）：① **三种交互渠道**（TUI 全键盘菜单 / CLI 定时无人值守 / Web 浏览器即开即用，同一引擎报告一致）；② **图表丰富的 HTML 报告**（单页自包含、响应式、9 张 Chart.js 交互图、深/浅色主题）；③ **专业的 Excel 报告**（最多 19 条件页签分七组）；④ **LLM 智囊团**（多 Provider 链式分发 + 缓存省费）；⑤ **调仓 What-if 模拟**。
- **启动方式统一引导句**：「同一套引擎，三种交互渠道——按你的场景选一个即可，报告结果完全一致」。
- **folders.md 同步**：用户文档统计行数 5,843→5,855（README 191→203 行）、目录树 README 描述标注「三渠道交互 + 核心亮点总览」。

---

### 数据源健康检查整体耗时预算修复（rf-263）（2026-08-06）

- **`core/check_sources.py` `run_health_checks`（rf-263 修复）**：`max_timeout` 原为**死参数**——`ThreadPoolExecutor` + `as_completed` 主流程等待全部线程完成，慢速/挂起数据源会拖住整个健康检查（Web 健康接口需在前端 15s abort 前返回，超时则 504）。改为 daemon 线程 + 整体耗时预算：`deadline = perf_counter() + max_timeout`，逐线程 `join(timeout=剩余预算)`，预算耗尽即返回已收集的部分结果，未完成项标记「超时（预算 Ns）」；持锁原子追加 + 竞态兜底（同 name 保留真实结果弃超时占位）。
- **`src/test/unit/core/test_check_sources.py`（新增）**：回归用例覆盖——预算内完成全部返回 / 慢源超时未完成项标记超时 / 竞态兜底（迟到真实结果覆盖超时占位）。
- **门禁**：dev-verify passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

---

### 功能开关文档补全 + HTML 自包含文档强调（2026-08-06）

- **`how-to-config.md` §M 功能开关表补全（rf-262 修复）**：原表只以通配符摘要列出分组（`llm_*`/`fund_deep_analysis_*`/`news_*`/`metrics_*`），未列具体 key，且 `fund_deep_analysis_*` 计数误写 4 项（实际 2 项）。已补全为**逐项列出全部 27 个开关**（key / 默认值 / 说明），与代码 `features.py::_FEATURE_FLAGS_DEFAULT` 一致。
- **修正错误指引**：原「完整清单以 `data/config/features.json` 文件中的注释为准」——features.json 是唯一不支持注释的配置文件，指引错误。改为明确指向代码默认值 `features.py`，并强调该文件仅存覆写子集。
- **`faq.md` 报告理解新增问答（HTML 单文件自包含强调）**：明确默认自包含（8 个 JS 资产内嵌）、关闭 `enable_interactive_charts` 后的例外（不自包含、须与 JS 同目录）、以及给用户的明确结论；同步修正故障排查中过时说法「报告不含 JavaScript，纯 CSS 渲染」。
- **门禁**：check-doc-traces / check-task-numbering `--ci` 全 [OK]。

---

### Web 状态区系统信息展示（版本 / 本机 IP / LLM 状态）（2026-08-06）

- **`web/handlers.py` `_build_system_info`（新增）**：rf-260 修复——Web 页面缺 TUI 状态面板信息面（程序版本号 / 是否开启 LLM / endpoint / 熔断 / 模型路由 / 本机 IP）。组装 `app_version`（`APP_VERSION`）+ `machine_ip`（`_get_machine_ip`）+ `llm` 结构化状态：flat 单 provider 模式展示 provider / model / endpoint（`_simplify_endpoint` 取主机名）/ 熔断（`get_circuit_status`）/ 模型路由（隐藏辩论三模块，模块级 `model_{sfx}` 覆盖展示）；credentials_ref 多链模式展示策略（priority 等）与 provider 清单（名称/后端/模型/优先级/熔断，model/endpoint 经 credentials_ref 解析到 `_llm_credentials`）及模块偏好；未配置或读取异常（try/except 兜底）→ `configured=False`，页面显示「未配置」，不阻断渲染。
- **`web/templates/index.html` / `web/static/style.css`**：状态区 grid 由两列改三列（`.status-grid-3`），新增「系统信息」卡片（程序版本 `#system-version` / 本机 IP `#system-ip` / LLM 状态 `#system-llm`），配置时展开 `#system-llm-detail`（multi 列 provider、flat 列熔断+模型路由）；补 `.system-list`/`.system-row`/`.system-llm-on/off`/`.system-llm-detail` 等样式，375px 响应式折叠为单列。
- **验证**：`TestSystemInfo` 7 用例（unit_web 标记：默认未配置 / flat 缺 api_key 兜底 / flat 详情与模块覆盖 / 多链凭据解析与偏好 / 读配置异常兜底 / 索引页渲染未配置态）全绿；`test_handlers.py` 全文件 31 用例通过。
- **门禁**：dev-verify passed（1938 passed, 0 failed）+ check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

---

### HTML 报告单文件自包含（2026-08-06）

- **`html_writer_assets.py` `_inline_js_assets`（新增）**：rf-259 修复——报告 HTML 下载/移动后图表失效。报告模板以相对路径外链 8 个 Chart.js 本地 bundle 资产（chart.min.js/chart-print.js/chart-config.js/chart-export.js/chart-common.js/chart-init.js/toc.js/theme.js），`_copy_js_assets` 仅复制到输出目录，HTML 移到其他目录（Web 下载到本地、单发移动端浏览）后 JS 找不到 → 资产穿透 TOP10 等图表空白。`_inline_js_assets` 在内嵌保存前读取资产内容，将 head 区外链标签移除并按 bundle 依赖顺序追加为行内 `<script>` 到 `</body>` 前——复刻 defer 外链时序（DOM 解析完后、DOMContentLoaded 事件前按序执行），保证 chart-init.js 能取到已解析的 canvas/chart-data、toc.js/theme.js/whatif 初始化等内部注册 DOMContentLoaded 的脚本仍触发；报告 HTML 单文件完全自包含。
- **`html_writer.py` / `whatif_writer.py`**：`enable_interactive_charts` 开启时保存前调用 `_inline_js_assets(html)`；`_copy_js_assets` 保留作兜底（资产缺失/读取失败/含 `</script` 序列时该资产外链标签保留原位，松散文件仍可加载）。
- **验证**：`TestInlineJsAssets` 6 用例（unit_report 标记：全部外链替换+追加到 body 前、defer 时序位置、bundle 依赖序 common→init、非 bundle 外链保留、缺失/含 `</script` 跳过）全绿；无头 Chrome 差分实测——内嵌版在无 JS 目录 canvas `width=1048`（Chart.js 实例化，图表渲染），外链版停默认 `500×320`（空白），修复前两者像素一致、修复后内嵌版彩色像素 347682→398536（ratio 1.15）。
- **门禁**：dev-verify passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

---

### Web 冒烟脚本沉淀（2026-08-06）

- **`scripts/smoke-web.py`（新增）**：rf-258 修复——将 Web 模式验收的临时冒烟脚本沉淀为可复跑脚本。前端零 node 工具链约束下不引入 Playwright，改为 Flask `test_client` 进程内 HTTP 全链路验证（不占端口、不发真实网络），覆盖 9/9 断言：页面渲染 / 健康检查 / 上传校验（合法 xlsx→file_id、伪装坏文件→400）/ 运行 202 / 进度事件 / 完成态 / 产物下载 / 历史记录 / 产物目录隔离。管线（fake executor）、健康探测（`run_health_checks` mock）、历史记录（`load_history` mock）全 mock；output_dir 与上传目录临时目录隔离。独立运行 `.venv/bin/python scripts/smoke-web.py`，全部通过退出码 0，失败退出码 2。
- **`src/test/unit/web/test_smoke_web.py`（新增）**：pytest 载体（`unit` + `unit_web` 标记），importlib 加载脚本调 `run_smoke()` 断言 9 项全通过；`unit_web` 标记使本用例自动纳入 test_runner `dev-verify`/`verify` 门禁（无需改 MODES 字典）。
- **门禁**：dev-verify passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

---

## [0.10.10] - 2026-08-06

### 六文档核对与 Web 模式文档补全（2026-08-06）

- **六文档核对结论**：how-to-start.md（方式四）/ README.md（功能特性）/ faq.md（Web 问答）已在 plan-8 阶段3 就绪；llm-technical.md 经核对**无需改动**——Web 复用 `report/orchestrator.py` → `llm/` 包，对 LLM 层零改动，与 CLI 一致不入该文档。
- **requirements.md**：§1.1 目标补三种入口（TUI/CLI/Web）共用同一套管线；§1.2 流程图后加入口共用说明（TUI E/B/L ↔ CLI `--type` ↔ Web 报告格式下拉）；§2 新增 R-ENV-04（`launch.sh/ps1 web` 启动 Web 模式）；§3 改「用户交互」+ 新增 3.4 Web 浏览器模式（R-WEB-01~07：启动/上传/格式与选项/进度事件/产物预览下载/单 worker 串行队列/生命周期管理）。
- **technical.md**：§1.1「双入口：TUI 与 CLI」改「三入口」，三入口对照表加 Web 行，共享模块/分层差异/关键分层原则文案同步（"消除 TUI、CLI 与 Web 间的逻辑重复"）；§1.2 报告类型表补 CLI/Web 触发说明；§1.3 模块职责总览加 Web 服务层 + Web 进度报告两行；§7 模块间依赖补 web/ 薄入口依赖块；附录 A 目录结构补 `src/python/web/` 全量条目。
- **how-to-test-my-code.md**：`unit_web` 标记补全——verify/dev-verify 的 `-m` 表达式（三处）加 `or unit_web`、「12 个子组」改「13 个子组」、dev-verify/verify 模块计数（5→6、8→9）、marker 参照表加 `unit_web` 行。
- **scripts-reference.md**：启动脚本一览表 `launch.sh/ps1` 行补 `web` 子命令说明；「启动脚本」章节新增 `launch.sh web / launch.ps1 web` 小节（默认 127.0.0.1:8000、--host/--port/--config、单 worker 串行队列说明）。
- **README.md**：启动方式新增「Web 浏览器模式」小节（`launch.sh web` / `launch.ps1 web`）。
- **技术债务登记（review-findings.md rf-256~258）**：rf-256 `output_dir` 锁文件检测未实现（设计规定 server 启动时检测输出目录占用并警告，实现仅端口探测）；rf-257 Web 浏览器真机人工验收未做（冒烟为脚本化 HTTP 验证 9/9 过，缺 Chrome/Edge 真机走查含 375px）；rf-258 Web 前端 main.js 无自动化测试、冒烟脚本未沉淀。rf-next 256→259。
- **门禁**：dev-verify 1917 passed + check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

### plan-8 阶段1：轻量 Web UI 骨架 + 上传→生成→预览全链路（2026-08-06）

- **依赖接入**：`flask==3.1.2`（pyproject.toml + requirements.txt，锁 werkzeug 3.1.8 / itsdangerous 2.2.0 / click 8.4.2 / blinker 1.9.0）；`scripts/launch.sh` / `launch.ps1`（BOM 保留）增 `web` 入口参数，`launch.sh web` / `launch.ps1 web` 启动 Web 服务，其余参数透传。
- **`src/python/web/` 骨架**：`server.py`（sys.path 注入 + 端口占用检测 + app.run）、`app.py`（Flask 工厂：统一 JSON 错误处理 / request_id 访问日志 / 注入 run_manager）、`handlers.py`（页面/上传/生成/轮询/预览/下载/历史/健康路由）、`upload.py`（上传安全）、`progress.py`（WebProgressReporter 事件缓冲）、`runs.py`（RunManager 单 worker 串行队列 + run 状态/事件注册表）、`templates/index.html` + `static/main.js`/`style.css`（单页 UI，原生 ES6 无 innerHTML）。
- **全链路贯通**：上传持仓 Excel（`POST /api/upload`）→ 提交生成任务（`POST /api/runs`，单 worker 串行防产物覆盖）→ 轮询进度（`GET /api/runs/{id}/events` 增量）→ 预览/下载产物（`GET /api/reports/<file>`）。管线复用 `generate_report` 零改动（reporter 注入 WebProgressReporter，output_dir 快照在出队时取）。
- **上传安全（§6.1）**：uuid 重命名丢弃原始文件名（防路径穿越/中文）、`.xlsx` 扩展名白名单 `.lower()`、10MB 上限（Flask MAX_CONTENT_LENGTH 兜底）、PK zip 魔数校验、行数上限 5000、mkstemp + os.replace 原子落盘、TTL 1h + 启动清理；伪装 zip 预检兜底转 UPLOAD_BAD_FILE（新增测试暴露的真实缺陷）。
- **预览防穿越（§6.2）**：扩展名白名单 + `send_from_directory` 内置 `..` 净化。
- **`unit_web` marker + 测试**：conftest 注册 marker / 隔离 `_UPLOAD_DIR`+`_file_registry` / autouse 重置 RunManager 单例，unit/conftest `_DIR_TO_MARKER` 映射，test_runner dev-verify/verify 纳入；5 个测试文件 54 用例（upload/upload_edge/progress/runs/handlers，含 zip-bomb/伪装/路径穿越变体 edge 场景）。
- **验证**：web 目录 54 用例全绿；dev-verify 1905 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 通过。阶段2（功能补齐）/阶段3（体验打磨）待做。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### plan-8 阶段2：配置回填 + 进度步骤 + 状态区（2026-08-06）

- **配置显示回填表单**：索引页加载时取一次 `get_config()`，历史走势复选框默认跟随配置 `history.fetch_mode`（off→关闭，auto/prompt→开启，`enable_history` 一并计入）；新增「强制重新生成 LLM 内容」开关。表单显式提交 `fetch_history`/`force_llm` 布尔值。
- **进度步骤展示**：事件按步序号（seq）编号渲染，进度条上方显示「当前阶段（第 N 步）：消息」，完成置 100%。
- **历史运行记录页**：状态区新增历史记录卡片（`/api/runs/history`，5s 短缓存），展示最近 10 条运行（时间/报告类型/持仓数/耗时/异常标记）。
- **数据源健康状态**：状态区新增健康卡片（`/api/health`，60s 缓存），逐源展示正常/异常 + 延迟；「重新检测」按钮用 `?fresh=1` 绕过缓存强制重测。
- **错误处理完善**：结果按 `exit_code` 映射展示（0 成功 / 1 部分失败黄色告警 + 通用建议 / 2 严重红色 + 提示看日志）；严重/执行失败时隐藏无效产物按钮（见 rf-254）；失败提供「重新生成」按钮（上传文件已消费，引导重新上传）；提交时 `FILE_EXPIRED` 自动重置流程提示重新上传。
- **验证**：web 目录 64 用例全绿（新增索引回填/健康缓存 fresh/产物裁剪/布尔参数 10 用例）；dev-verify 1915 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 通过。阶段3（体验打磨 + 文档）待做。

### plan-8 阶段3：样式打磨 + 加载态/轮询节流 + 响应式 + 用户文档（2026-08-06）

- **样式打磨（design-quality）**：上传区拖拽高亮（drag-over 抬起 + 聚焦态）、进度条渐变（主色→强调色）、卡片悬浮阴影层级、状态区双栏网格（数据源健康/历史记录，≤480px 单栏）、结果徽章语义着色（成功绿/部分黄/失败红）、`prefers-reduced-motion` 减动效适配。
- **加载态与轮询节流**：提交后生成按钮禁用 + 文案切换（正在提交...→生成中...）；上传/轮询/结果请求全部 `AbortSignal.timeout` 兜底；`visibilitychange` 页面不可见时暂停轮询、恢复可见立即同步（省请求）。
- **响应式（375px 移动端）**：表单纵向堆叠、按钮全宽、状态区单列、健康行 meta 截断不溢出。
- **a11y**：文件输入从 `hidden` 改为 `sr-only` 视觉隐藏但保留可聚焦（键盘可达）；进度条 `role="progressbar"` + aria-valuenow；aria-live 播报。
- **用户文档**：how-to-start.md 新增「方式四：Web 浏览器模式」（启动命令 / --host --port --config 参数 / 局域网访问无内建认证警示 / 使用要点）；faq.md 故障排查补 Web 模式 5 问（端口冲突/无法访问/进度卡住/文件过期/产物 404）；README.md 功能特性补 Web 模式提点。
- **归档**：`plan-web-ui.md` + `plan-web-ui-implementation.md` 归档至 `docs-stm/archive/v0.10.x/web-ui/`（三阶段全部完成），plan.md / folders.md 引用同步更新。
- **工具修复（rf-255）**：`check-doc-traces.py` 裸版本号模式把 Web 文档正文 IP 地址误判为版本号（`127.0.0.1:8000`→子串 `0.0.1`、`0.0.0.0`→`0.0.0`，5 处误报）——`_line_exempt()` 增加 IPv4（含端口）整行豁免，双用例回归。
- **验证**：web 目录 64 用例全绿；dev-verify 1917 passed（新增 2 个工具回归用例）；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 通过。plan-8 三阶段全部完成。

### rf-113 Iter 7 浏览器人工验证进度更新（2026-08-06 另机 Windows）

- **① 6 图渲染 + 交互 — ✅ 通过**：ok/degraded 场景 6/6 图渲染 + 全部图 tooltip 可用（含净值/回撤折线、雷达——rf-249 修复后悬停任意处即显示）；empty 场景 4/6 渲染 + tooltip（资产构成/雷达空数据占位，符合 §4.12 空值语义）；offline 场景引擎缺失守卫生效（R21）。Chrome + Firefox 实测，Edge 未测（同 Chromium 内核，S2 升级时补验）。
- **② 打印降级 — ✅ 2.1~2.3 通过**：打印预览图表 2x DPI 清晰（文字/刻度/数据线锐利）、浅色主题强制（文字黑/背景白，不浪费墨水）、单图不跨页（`break-inside: avoid`）。2.4（afterprint 恢复交互）待补验。
- **③ 离线验证 — 3.2~3.4 通过**：删除 chart.min.js → `typeof Chart` 守卫静默跳过、无 JS 报错；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格（rf-249 修正断言）。3.1（断网 6 图正常渲染）待补验。
- **待补验**：② 2.4 afterprint、③ 3.1 断网渲染、④ 微信内置浏览器、⑤ 375px 移动端、⑥ 禁用 Canvas fallback。
- **验证期间修复**：rf-248（动态脚本顺序）、rf-249（折线/雷达 tooltip 触发）、rf-250（自检 `Chart.getChart` 判定）、rf-251（空数据图显式守卫）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### Web 服务启动 output_dir 写锁检测（rf-256）

- **缺陷**：`web/server.py` 仅做端口占用检测（bind 探测），未做设计文档（`docs-stm/archive/v0.10.x/web-ui/plan-web-ui-implementation.md` 单 worker 串行队列一节）规定的 `output_dir` 锁文件检测——多进程共享同一输出目录（多开 web、或 web 与 TUI/CLI 并行）会互相覆盖最新版产物，启动时不提示，用户难以察觉产物被其他入口覆盖。
- **修复**：`web/server.py` 启动时对 `output_dir` 做写锁检测——原子抢占锁文件 `.investor_output.lock`（`os.open` `O_CREAT|O_EXCL` 防多进程抢占竞态；内容记录 entry/pid 便于排查），锁已被其他入口持有则记录警告「该输出目录可能正被其他入口占用，产物可能互相覆盖」，抢占成功则持有至进程退出时 finally 释放。锁文件为点文件，不参与 `YYYYMMDD` 归档扫描与历史枚举（`_cleanup_old_archives` 仅处理 8 位数字目录）。占用仅告警、不阻塞启动（产物竞态交由用户决策）。
- **验证**：新增 `src/test/unit/web/test_server.py` 11 用例（锁路径定位 / 存在性判断 / O_EXCL 原子排他 / 释放与缺失 noop / 目录不可写兜底 / 被占用告警且不阻塞启动）全绿；web 目录 75 用例全绿；dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### technical.md 三渠道体系梳理 + 渠道详细设计（TUI / CLI / Web）

- **背景**：plan-8 三阶段后系统已具备 TUI/CLI/Web 三个交互渠道，technical.md 仅以「三入口」表格平铺各渠道入口/交互层/进度报告器对照，缺体系化视角（渠道定位、统一架构模式、差异维度、并发与产物治理），且各渠道实现（TUI 主循环/菜单/键盘、CLI argparse/退出码、Web 启动流程/上传安全/单 worker 队列/事件缓冲）分散在 §1.1/§1.3/§4/§7 而无集中详述。
- **§1.5 交互渠道体系（CLI / TUI / Web）**：新增体系化章节——① 渠道定位（交互范式/典型场景/进程模型三渠道对照）；② 统一架构模式（薄入口 + 共享管线 + 进度抽象 + 配置快照）；③ 渠道差异对照（参数传递/进度传输/并发模型/产物输出/启动防护/生命周期六维度）；④ 并发与产物治理三层（进程内单 worker 队列 / 进程间 output_dir 写锁 / 存储层原子写 + 归档分目录，警告优先不阻塞）。
- **§1.6 TUI 渠道详细设计（主要渠道）**：聚拢既有丰富材料重新组织为独立章节（TUI 是主要渠道，篇幅最深，位于渠道序位首位）——模块划分（tui.py / tui_menu / tui_keys / handlers_report / handlers_config / handlers_cache / handlers_whatif / TuiProgressReporter）/ 主循环与键盘导航（重绘循环 + 方向键/快捷键/Ctrl+C 路由，跨平台键盘封装）/ 菜单体系（17 项四分组表 + 状态面板）/ 报告生成流程（_run_generate 骨架 + _prompt_history/_prompt_force_llm 交互询问 + 委托 orchestrator）/ TuiProgressReporter（四态前缀 + call_sheet + 耗时排行框）/ 启动流程（init_config → _bind_callbacks → 清理/隐私提示/首次引导 → default_menu_key 默认「L」→ 退出 LLM 会话统计）。
- **§1.7 CLI 渠道详细设计**：新增——退出码约定（0/1/2）/ argparse 结构（全局参数 + report/cache/whatif/check-sources 子命令）/ 主流程（check-sources 前置免 config、持仓 config 定位差异）/ 子命令处理器（report 委托 generate_report、cache 三分支含 --update all 最大努力模式、whatif 委托 run_whatif_simulation）/ CliProgressReporter（默认日志、--verbose 同步 stderr）。
- **§1.8 Web 渠道详细设计**（原 §1.6 重编号）：模块划分 / 启动流程与启动防护（端口检测 + output_dir 写锁检测）/ Flask 工厂与统一错误信封 / 路由全景表 / RunManager 单 worker 串行队列（快照语义、状态机、内存上限、线程安全）/ 上传安全链路 / WebProgressReporter 事件缓冲 / 前端单页与进度可视化 / 安全防护矩阵 / 与 TUI/CLI 差异要点。
- **同步修订**：目录 TOC 补 §1.5/§1.6/§1.7/§1.8 锚点；§1.1 分层差异段落交叉引用 §1.6（TUI 主要渠道）/§1.7/§1.8；§1.5 内引用随重编号更新（§1.6.5→§1.8.5、§1.6.2→§1.8.2）；§7 web 依赖块 server.py 行补写锁检测；附录 A server.py 条目补启动防护说明。
- **门禁**：check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致。

### 技术设计文档自完备修正（technical.md / llm-technical.md）

- **technical.md 数据降级体系**：删除对用户文档（datasource-reliability.md §4.1）的引用，改为自包含「三级熔断体系」完整说明——技术设计文档不引用用户文档、整体自行完备（约束原文要求）。
- **technical.md 数据可用性措辞**：去实测日期痕迹与「历史快照」措辞，改为「365 天窗口探测，Tencent 主链路」等反映最新状态的中性描述。
- **technical.md 附录 H**：去「已实现全量」标题与「已实现」状态列、清理悬空 Schema 文档引用；架构设计约束表中 pipeline_data Schema 定义条目改指向附录 H。
- **llm-technical.md**：提示词示例时间「2026-07-14 14:30」改为占位符「YYYY-MM-DD HH:MM」——示例反映模板而非快照时间。
- **门禁**：check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### chart-init.js 空数据图显式守卫（rf-251）

- **缺陷**：6 个核心图 init 守卫 `!ds.labels` / `!ds.datasets` 不拦截空数组（空数组 truthy）。empty 场景（`labels:[]` + `datasets:[]`）下 `ds.datasets[0]` 为 undefined，访问 `.data` 抛 TypeError，**依赖外层 try/catch 降级**（图不渲染、console 出现 `[chart] 初始化失败` warn 噪声），而非显式空数据跳过。
- **修复**：6 处守卫统一补 `!ds.labels.length` + `!ds.datasets.length`，空数据优雅 return，对齐生产模板 `{% if labels %}` 空值语义（§4.12），不再依赖异常降级。
- **验证**：JS 语法校验通过；empty 场景资产构成/雷达空数据图不初始化、badge 占位行为不变。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### test-chart.html 自检图接管判定修正（rf-250）

- **缺陷**：调试页自检用 `canvas._chart` 判定图是否被 Chart.js 接管——Chart.js v4 该内部句柄已不存在（canvas 上挂的是 `_chartjs`，用于管理事件监听器；`_chart` 是数据集/图表元素内部引用），判定恒为假。rf-249 修复后 ok/degraded 场景图真实渲染、tooltip 可用（用户 2026-08-06 实测），但自检仍误报「0/6 图已初始化」。
- **修复**：自检判定改用官方 API `Chart.getChart(canvas)`——v4 构造内部亦用 `Chart.getChart(canvas)` 查询已有图表（`constructor` 中 `o = Dn(n)`），与 chart-print.js / chart-export.js 收集图表用同一 API，口径一致。
- **验证**：待用户重测四场景 banner 应正确显示实际初始化数（ok/degraded=6/6，empty=4/6，offline=引擎缺失文本）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 折线图/雷达图 tooltip 触发修复 + 调试页自检时序与文案修正（rf-249）

- **tooltip 缺陷**：6 图交互验证（rf-113 ①，用户 2026-08-06 另机）发现——净值趋势/最大回撤折线图 `pointRadius:0` 且 Chart.js 默认 `interaction.intersect:true`，数据点命中区域≈0，鼠标悬停无法触发 tooltip；雷达图 `pointRadius:3` 命中区域小同样难触发。环形图（切片命中区域大）与两个柱状图（整柱命中）正常。该缺陷同时影响生产报告（净值/回撤/组合演进 3 图）与 whatif 回测线图（共用 `ChartCommon.lineOptions`）。
- **修复**：
  - `chart-common.js` `lineOptions` 补 `interaction:{mode:'index',intersect:false}`——折线图悬停图表任意处即显示最近 x 点全数据集值（金融时序标准交互）。
  - `chart-init.js` radar 补 `interaction:{mode:'nearest',intersect:false}`——雷达无 x 索引轴，用最近点模式。
- **调试页自检时序**：test-chart.html banner 自检原用固定 800ms 定时器，早于脚本加载完成（chart.min.js 约 200KB）误报「0/6 图已初始化」；改为 chart-init.js（最后一个注入脚本）onload 触发 + 3s 兜底，保证自检在全部图表初始化完成后执行。
- **offline 文案修正**：banner 原断言「canvas 保留 fallback 文本」为误解——现代浏览器（Firefox/Chrome）不渲染 `<canvas>` 内部 fallback 文本（仅不支持 Canvas 的浏览器显示），引擎缺失时图表区域实际为空白，真实报告回退到明细表格。banner 文案与 iter7 验证清单 3.4/进度注记、review-findings rf-113 注记同步修正为实测行为。
- **验证**：待用户另机硬刷新（Ctrl+F5 清缓存）重测四场景——ok/degraded 应 6/6 初始化、全部图悬停有 tooltip；empty 应 4/6 初始化 + 资产构成/雷达占位；offline 引擎缺失文本为预期（R21）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### test-chart.html 动态注入脚本顺序修复（rf-248）

- **缺陷**：TD8 调试页 `src/static/test-chart.html` 引导脚本用动态 `createElement('script')` 注入 6 个 chart 资产，但未设 `s.async=false`。动态 script 默认 async=true **无序执行**，chart-init.js（约 13KB）可能先于 chart.min.js（约 200KB）执行，触发 chart-init.js 顶部守卫（`typeof Chart === 'undefined' || !window.ChartCommon`）静默 return，图表永不初始化——ok/degraded/empty 全场景实测均「0/6 图已初始化」、无 tooltip（用户 2026-08-06 另机复现；empty 场景仅 radar badge 走「占位」分支，其余图空白；偶发 800ms 自检时 Chart 尚未加载完成还会误报「引擎缺失」banner）。
- **修复**：注入循环补 `s.async=false`，保证脚本按注入顺序执行（chart.min.js → … → chart-init.js 最后），对齐报告模板 `defer` 语义。
- **影响范围**：仅调试页受影响；生产报告模板（report_template.html）/ whatif 模板（whatif_template.html）均用静态 `<script defer>`，执行顺序有保证，无此缺陷。
- **验证**：修复后待用户另机重测三场景（ok/degraded/empty 应 6/6 图初始化、tooltip 可用；offline 场景保留引擎缺失文本，属 R21 预期）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

---

## [0.10.9] - 2026-08-06

### LLM 空响应安全网扩展（关闭 thinking 重试 + thinking 并发信号量）

- **空内容诊断增强**：`llm/api_base.py::_extract_content` 空 content 诊断日志补充响应细节（stop_reason / block 结构 / HTTP 状态），出现 HTTP 200 + 空正文时可快速定位是 thinking 耗尽还是端点偶发异常。
- **安全网覆盖范围扩展**：DeepSeek 等强制推理模型在 `payload` 未显式携带 thinking 参数时也会落入默认思考模式（effort=high）占满 `max_tokens`，导致 `stop_reason=max_tokens` 无正文。`_api_claude.py` 安全网触发条件由「显式 thinking + 思考耗尽」放宽到「强制推理模型（`_is_effort_model`）或思考耗尽」；重试 payload 显式 `thinking.type=disabled` 并移除互斥参数（output_config / reasoning_effort），避免重试再次触发思考。
- **thinking 并发信号量**：`generators_orchestrator.py` 新增 `llm_max_thinking_concurrency`（默认 1）BoundedSemaphore，约束开启 Extended Thinking 的模块（health_check / expert_review 等 `thinking_enabled_{suffix}=true`）同时最多 N 个在跑，从源头降低多 thinking 模块并发涌向 DeepSeek 时偶发空 content（HTTP 200 空响应）的概率；非 thinking 模块不受此限，总并发仍受 `llm_max_concurrency` 约束。新键登记至 registry `get_known_llm_settings_keys()`，默认模板 `_llm_settings_defaults.py` 同步生成。
- **配置同步**：`data/config/llm_settings.json` 全局设置区补 `llm_max_thinking_concurrency: 1`；how-to-config-llm.md（全局配置 8 项说明 + 完整范例）、requirements.md（全局配置参数表）、llm-technical.md（全局键名清单 + 4.2 并发控制段落）、testplan.md（llm/ 包覆盖描述补 thinking 并发信号量）同步。
- **测试**：test_llm_api.py 新增强制推理模型空 content 关闭 thinking 重试用例；test_generate_all_llm.py 新增 `TestThinkingConcurrencyLimit`（thinking 模块串行/非 thinking 不受限/总并发不超限）；test_llm_api_base_edge.py 空 content 诊断断言；test_registry.py `test_llm_settings_keys_count` 断言由 86 更新为 87（新增全局键）。LLM 测试全部 mock `call_llm` / `call_llm_with_retry` / `make_http_client`，无真实 API 调用。
- **门禁**：dev-verify 1862 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 报告子模块无候选/无数据时页面提示 + data_quality 缺省开启（rf-247）

- **候选基金无配置提示**：`candidate_compare` 子模块开启但 `config.comparison_candidates` 未配置（或全部代码非法）时，原先 HTML 端静默跳过候选基金比较区块、Excel 端静默不写，用户无从判断原因。现在 HTML 模板（report_template.html）外层守卫改为 `{% if candidate_data %}` + 内部 `available` 分支，无候选时渲染「📭 未配置候选基金（config.comparison_candidates 为空），无法输出候选基金比较…」占位（含被忽略的非法代码列表）；Excel 端新增 `_write_candidate_unavailable_block`（标题 + `_write_placeholder` 占位）；`html_renderers.py` 同步 `prog.warn` 提示。
- **成本流水无数据提示**：`cost_lots` 子模块开启但持仓 Excel 未录入交易/分红流水时，HTML 端盈亏汇总区补「成本流水子模块已开启，但持仓 Excel 未录入交易/分红流水，资金加权收益率 (XIRR)、成本分档、分红累计无法计算」提示（Excel 端 summary.py 已有占位，本次对齐 HTML 端）。
- **data_quality 缺省开启**：`report_submodules.data_quality` 默认值由 `false` 改为 `true`（数据质量仪表盘 = 品种覆盖 + 可信度，属长期可信核心，开箱即得）；访问器 `is_enable_data_quality` 兜底逻辑（report_submodules 缺失/非 dict/data_quality 键缺失）同步改为缺省 `true`，与 `enable_action` 缺省开启口径一致；配置生成模板注释同步。
- **文档同步**：how-to-config.md（示例配置 + 参数表默认值）、how-to-menu.md（子模块默认说明）、requirements.md（`report_submodules` 默认值）、technical.md（功能语义命名表 data_quality 行默认开）、reports-instruction.md（候选基金比较子表补充「无候选时占位提示」行为说明）、test-coverage.md + folders.md（测试计数快照刷新：`all` 5,146→5,196、dev-verify 1,846→1,864）。
- **测试**：test_fund_performance.py 新增 `TestWriteCandidateUnavailableBlock` 2 用例（无候选写占位 / 占位列出非法代码）；test_html_writer.py 候选基金无候选渲染拆 3 例（None 不渲染 / available=False 显示未配置提示 / invalid 列表显示）+ 成本流水空数据提示 2 例；test_config.py `TestIsEnableDataQuality` 重写为默认 true + 新增 `_DEFAULT_CONFIG` 断言；test_handlers_config.py 数据质量默认开（toggle 测试改关）。
- **门禁**：定向 250 passed；dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 历史走势默认自动获取 + 关闭时醒目警示（rf-245）

- **警示修复**：`fetch_history=False`（历史走势关闭/跳过）时原先静默返回 `None`，下游只剩误导性的「尾部风险：无历史 bars」占位警告，用户无法判断是配置关闭所致。现在 `report/_snapshot.py::fetch_history_data` 在 fetch 关闭时通过 `reporter.warn`（[!] 黄色）+ `logger.warning` 醒目提示「组合历史走势获取已跳过（history off）」及占位后果（历史走势/回撤章节、尾部风险指标、累计收益率等显示"数据不可用"），并提示开启方式（CLI `--history auto`）。
- **默认值调整**：CLI `--history` 默认值由 `off`（跳过）改为跟随配置层——未显式传参时 `generate_report` 按 `config.history.fetch_mode`（`off`/`auto`/`prompt`，默认 `auto`）决定是否获取。`auto`/`prompt` 均视为获取（prompt 为 TUI 交互询问，CLI 非交互场景按获取处理），仅 `off` 跳过。config.json 默认 `fetch_mode="auto"` 不变，新用户开箱即获取组合历史走势。
- **影响**：`both`/`full` 报告默认包含组合历史走势/回撤、尾部风险、累计收益率等数据（原来默认占位）；`--history off` 可显式跳过。包装脚本（`cli.sh`/`cli.ps1`）无参数默认 both 同样受益。
- **文档同步**：how-to-start.md（`--history` 参数表默认说明 + 报告类型段落）、cli.sh/cli.ps1 头部注释（历史走势默认 auto 获取）。
- **测试**：`test_orchestrator.py` 新增 `test_generate_report_both_fetch_history_follows_config`（配置驱动解析 off/auto/缺失三态）+ `test_fetch_history_data_fetch_false` 增加警示断言；`test_cli.py` 默认断言更新（`--history` 未传 → None）。
- **门禁**：dev-verify passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### Excel 序号收敛到导航层（页签栏 + HTML 标题）（rf-244）

- **设计调整**：序号只在 Excel 页签栏 tab 名与 HTML 章节标题出现，Excel 正文标题统一为纯中文名（与投资组合概要/市值/分类/穿透/基金业绩/数据源可用性矩阵一致）。撤除 rf-243 引入的正文标题序号同步机制（`get_report_section_number_from_order`、create_sheets 的 `visible_number` 标记、7 个页签写入函数的 `section_order` 透传），回归更简设计——正文不依赖序号，调整配置/隐藏章节不会错位。
- **效果**：Excel 页签栏保留连续序号（行动建议=10、组合演进=13、数据源可用性矩阵=14），正文标题为「行动建议」「组合演进」「数据源可用性矩阵」纯中文名；HTML 章节标题保留序号。
- **测试**：test_correlation_sheet 正文标题断言更新为纯中文名；191 受影响单测 + dev-verify 1864 passed；4 项 trace `--ci` 全 [OK]。

### cli.ps1 补 UTF-8 BOM，修复 Windows PowerShell 中文解析崩溃（rf-246）

- **缺陷**：`scripts/cli.ps1` 文件头注释声称 "Encoding: UTF-8 with BOM"，实际文件**无 BOM**。Windows PowerShell 5.1 对无 BOM 的 UTF-8 中文按 ANSI/GBK 误读，导致中文注释解析崩溃（"字符串缺少终止符" / "语句块或类型定义中缺少右}"），跨机器复现（另一台电脑运行同样报错）。
- **修复**：补回 BOM（`EF BB BF`，UTF-8 + CRLF），PowerShell Parser 验证通过（`[System.Management.Automation.Language.Parser]::ParseFile` 无 errors）。
- **编码纪律落盘**：CLAUDE.md 技术要点新增「编码/BOM（Windows 脚本）」条目——`*.ps1` 必须 UTF-8 BOM + CRLF，否则 PS 5.1 按 GBK 误读崩溃；新增 `.editorconfig`（`[*.ps1] charset = utf-8-bom, end_of_line = crlf`），支持 EditorConfig 的编辑器**跨机器自动遵守**，避免此问题在其他电脑复发。
- **文档同步**：folders.md 目录树登记 `.editorconfig`。
- **验证**：BOM 字节（`ef bb bf`）+ PowerShell 解析器双重确认；CLI 包装脚本功能不受影响。

### Excel 正文标题序号跟随报告章节顺序配置（rf-243）

- **缺陷**：`report_section_order` 配置生效后，Excel 页签栏 tab 名按 create_sheets 可见连续序号重编号（行动建议=10、组合演进=13、数据源可用性矩阵=14），但 7 个深度分析页签（行动建议/组合演进/基金经理变更/持仓集中度/持仓关系矩阵/风格与因子/组合历史走势回撤）正文标题仍用注册表默认序号（行动建议=17、组合演进=16），与页签栏不一致。
- **修复**：create_sheets 创建页签时就地标记 `visible_number`（与 tab 名同源）；registry 新增 `get_report_section_number_from_order`，正文标题按「可见连续序号 → 配置序号 → 注册表默认」取值；7 个页签写入函数新增 `section_order` 参数，excel_generator / excel_fund_deep_analysis 透传配置后 order。正文标题与页签栏序号现完全一致。
- **说明**：该方案随后被 rf-244 设计调整取代——正文标题统一为纯中文名，序号仅收敛到导航层，本条目保留作过程记录。

### 报告页签显示顺序配置（行动建议提前至第 10 位）

- **配置**：`config.json` 的 `report_section_order` 由 `{}`（使用注册表默认）改为**完整配置 18 项**——`action`（行动建议）置于序号 10，原 10-16 依次顺延（`news_correlation`=11、`global_macro`=12、`expert_review`=13、`health_check`=14、`penetration_deep`=15、`portfolio_history_drawdown`=16、`portfolio_evolution`=17），`data_source_status`=18，`llm_usage` 强制末位。注册表默认值（行动建议=17）未改，清空该字段即恢复默认。
- **效果**：Excel 页签与 HTML 章节顺序/标题编号同步变化——行动建议提前至第 10 位，财经新闻/全球政经/智囊团/持仓体检/穿透深度/组合历史走势/组合演进依次顺延；数据源可用性矩阵编号不变（both 模式 14、full 模式 18）。
- **文档同步**：reports-instruction.md（主表 + 分组表重排）、requirements.md（§6.3 表 + §6.4.x 小节物理重排与重编号）、how-to-config.md（默认序号表后补本仓库配置说明）、technical.md（注册表 number 描述两处补配置说明）、faq.md（§13 智囊团引用）。
- **门禁**：dev-verify 1864 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。注册表默认值未改，test_registry 等断言不受影响。

### 行动建议章节默认开启 + 菜单 P 可视化开关

- **默认值调整**：`enable_action` 由默认关闭改为**默认开启**——`_config_defaults._DEFAULT_CONFIG["enable_action"]=True`；`get_config()` 合并逻辑以默认值打底，现有用户 config.json 缺失该键时自动补为开启（显式 `false` 的用户保持关闭）。访问器 `is_enable_action()` 缺失时返回 True，日志提示「缺少 enable_action，使用默认值 true」。
- **菜单 P 新增开关**：TUI 菜单 `[P] 配置报告可选章节` 面板新增第 5 项「行动建议（再平衡信号/交易纪律/调仓建议/收益归因）」，与既有 4 个章节组一致地交互切换；LLM 分析章节提示顺延为第 6 项。菜单 P 主菜单 label 同步加入「行动建议」。
- **行为影响**：开启后 E/B/L 报告均输出行动建议章（number=17，type=action）；关闭时章节隐藏且智囊团深度复盘隐藏「行动摘要」子块，剩余章节自动连续编号。
- **文档同步**：how-to-config.md（默认值表/章节可见性表/菜单归属/章节对照 5 处）、how-to-menu.md（主菜单 label/脚注/章节说明/菜单 P 详解 4 处）、faq.md、how-to-use-registry.md、requirements.md、reports-instruction.md、technical.md 全文「默认关」→「默认开，菜单 P 可切换」。
- **测试**：`TestIsEnableAction` 新增 `test_default_config_says_enabled`（断言 `_DEFAULT_CONFIG["enable_action"]` 为 True）；`test_default_true_when_missing` 保持缺失→True；test_registry/test_action_html/test_report_chapter_consistency 注释同步。
- **门禁**：dev-verify 1846 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]。

### 事实校验两处误修正修复（rf-239）

- **缺陷 1：名称指代主体定位平局误路由**。真实报告「止盈纪律」句「建设银行收益率+171.23%、工商银行+70.18%、长江电力+56.83%」中，171.23% 被误修正为 70.2%（601398 工商银行收益率）——`_locate_subject_code` 名称分支用起点距离 `abs(idx-anchor)`，建设银行(idx=0)与工商银行(idx=16)距 anchor=8 平局，先迭代者（工商银行）胜出，把 601939 的**正确** 171.23% 判错并改写。修复：名称分支改用**最近边距离** `min(abs(idx-anchor), abs(idx+len(name)-anchor))`，与代码分支一致，紧邻数值的名称唯一胜出。
- **缺陷 2：风险警戒阈值误修正**。同句「设立止损线：当前亏损-11.80%，已接近回调20%的警戒区域」中，「回调20%」是止损警戒阈值而非收益率声称（实际 -11.80% 同句另述且正确），却被误修正为 -11.8%（159222）。修复：`_is_trim_target_context` 增加警戒阈值检测——新增 `_WARNING_THRESHOLD_KEYWORDS=("警戒",)`，数值前后更宽窗口（-25/+8）内出现警戒词即判定为风控阈值，跳过收益率比较。
- **测试**：新增 `TestNameSubjectNearestEdge`（3 用例）+ `TestWarningThresholdContext`（3 用例）回归测试，修复前均失败；fact_checker 单文件 109 通过；完整合成稿+真实持仓端到端复现 corrections 由 2 处降为 0。
- **门禁**：fact_checker 单文件 109 passed（未跑全量，用户要求最小验证）。

### 菜单 P 新增报告增强子模块配置（6 项区块级开关）

- **新增访问器**：`config.is_enable_industry_beta()` 读取 `report_submodules.industry_beta`——与 data_quality / candidate_compare / cost_lots / valuation_percentile / market_temperature 五个既有访问器一致，导出至 `src.python.config`。
- **菜单 P 子菜单**：TUI 菜单 `[P] 配置报告可选章节` 新增第 6 项「报告增强子模块」，进入子菜单逐项切换 6 项区块级开关（数据质量仪表盘 / 行业Beta子表 / 候选基金比较子表 / 成本流水 / 估值分位 / 市场温度，默认全关），实时保存到 `report_submodules`；LLM 分析章节提示顺延为第 7 项。菜单 P 主菜单 label 同步加入「报告增强子模块」。
- **文档同步**：how-to-menu.md（主菜单 label / 菜单 P 详解）、how-to-config.md（6 行 report_submodules 配置方式 手动编辑 → 菜单 P → 6）。
- **测试**：`TestIsEnableIndustryBeta`（5 用例）+ `TestConfigReportSubmodules`（4 用例，mock 输入/配置读写），定向 13 passed（本机慢，全套在另一台电脑运行）。

### 测试污染真实快照目录修复（rf-240）

- **缺陷**：`test_corrupt_snapshot_file_skipped` 用 `from src.python.core.constants import HISTORY_SNAPSHOT_DIR` 在 import 时把快照目录**旧值**拷贝进测试模块，绕过 conftest `_isolate_sensitive_paths` 的 monkeypatch 隔离，把测试用损坏文件 `snapshot_corrupt.json` 写入**真实** `data/history/snapshots/`。后果：每次生成报告时 `[WARNING] 文件损坏 snapshot_corrupt.json`（程序自动跳过，不阻塞报告，但持续刷日志），且跨机器残留（另一台电脑运行过测试即同样产生）。
- **修复**：测试文件改用 `import src.python.core.constants as core_constants` 模块属性访问 `core_constants.HISTORY_SNAPSHOT_DIR`，使 conftest 隔离生效——损坏文件写入 `tmp_path` 而非真实目录。生产代码 `snapshot_diff.py` 经 `history_snapshot.load_all` 读取（模块属性引用）本就不受影响。
- **清理**：已删除本机残留的 `data/history/snapshots/snapshot_corrupt.json`（未跟踪的测试垃圾，非用户数据）。其他机器同样删除该文件即可。
- **回归验证**：edge 测试 6 passed，运行前后真实快照目录 diff 无新增残留。

### 数据质量仪表盘区块渲染崩溃修复（rf-241）

- **缺陷**：`report_template.html` 数据质量仪表盘「品种覆盖/可信度」区块中 `position_status.items` / `data_freshness.items` 在 Jinja2 命中 dict 内置 `items` 方法（bound method）而非契约键 `"items"`——`data_quality` 子模块开启且契约有数据时，guard 恒真，`{% for item in ... %}` 迭代 bound method → `TypeError: 'builtin_function_or_method' object is not iterable`，HTML 报告生成失败（另一台电脑菜单 L 实测崩溃）。该缺陷自数据质量仪表盘引入（87a137a4）即存在，因 `data_quality` 默认关、既有测试未开启该子模块渲染模板而漏测。
- **修复**：guard 与循环改用 `.get("items")`（与生产代码 `data_freshness.get("items")` 一致）；空 items 时正确走降级占位「未获取行情数据，品种覆盖无法判定」而非进入空表。
- **回归**：新增 `TestHtmlDataQualityBlocks` 4 用例（品种覆盖渲染/可信度渲染/空 items 占位/data_quality 关闭跳过），修复前 `_render_template` 抛 TypeError。
- **门禁**：dev-verify 全量通过 + 4 个 trace 检查全 [OK]。

### 数据质量仪表盘测试覆盖补强

- **可信度（`test_data_freshness.py`）**：新增 dict 形式明细分类（`_detail_value` dict 分支）、跳变检测跳过无 code/None 明细、摘要未显式传交易日自动推断、昨收为 0 时 `change_pct` 记 0.0 不除零；新增 `_infer_latest_nav_date` 直接测试（取最新净值日期 / 忽略无效日期 / 无净值回退当天日期）。
- **品种覆盖（`test_holding_status.py`）**：新增大写 SH/SZ/BJ 交易所前缀归一、单字符简称不子串匹配、dict 形式明细标注、股票「暂无行情」判可能退市、同代码多条明细取首条（`setdefault` 语义）。
- **页签写入（`test_data_quality_sheet.py`）**：新增 `build_coverage_block` 全部正常 abnormal_count=0、契约 available=True 但缺 items 键容错。
- **HTML 渲染（`test_html_report_structure.py`）**：新增报告头部数据异常摘要告警行（异常时显示 summary + 章节号引用、正常时隐藏）与异常行 `src-matrix-failed`/正常行 `src-matrix-ok` 高亮断言。
- **门禁**：四文件 162 passed；dev-verify 1864 passed + 4 个 trace 检查全 [OK]；ruff format 已一致。

### 报告生成骨架测试污染真实 reports 目录修复（rf-242）

- **缺陷**：`src/test/unit/report/test_orchestrator.py::test_generate_report_skeleton` 用 `config={}` 真实调用 `generate_report(holdings=[], ...)`——report_type 默认 basic（仅生成 Excel 不写 HTML），且未 patch `generate_excel_report` 写盘函数。`output = output_dir or config.get("output_dir", "reports")` 在 `config={}` 时 fallback 到相对路径 `"reports"`，解析为真实 `reports/` 目录；空持仓每次生成一个空页签 Excel 归档（`reports/{YYYYMMDD}/个人投资分析报告-*.xlsx`）+ 覆盖根目录最新版，跨整天累积 37 个残留文件。该缺陷被 `result.excel_ok=True`/`report_generated=True` 断言掩盖（basic 路径正常返回成功），既有测试未校验输出目录隔离而漏测。
- **修复**：传入 `output_dir=tempfile.TemporaryDirectory()` 隔离输出到临时目录，保留真实生成流程（骨架返回 ReportResult 断言不变）。
- **清理**：删除 reports 目录下全部 37 个空页签归档 + 根目录空最新版（均已验证不含真实持仓数据，抽样 + 全量扫描 0 命中）。
- **回归验证**：重跑 `test_orchestrator.py`（50 passed）+ `--mode report` 全量（1488 passed）后 reports 目录零新增。

### 报告输出目录兜底防线（rf-242 加固）

- **新增 conftest autouse fixture**：`_isolate_report_output_dir` 统一安装，把两个真实落盘入口——`excel_writer.save_workbook`（`excel_module_loader` 运行时 `from ... import save_workbook` 取到被 patch 后的模块属性，报告链路天然覆盖）与 `html_save._save_html_report`/`html_writer._save_html_report`（模块级拷贝引用，两处一起 patch）——收到的输出目录解析后等于项目真实 `reports/` 时透明重定向到 `tmp_path/reports`。测试漏传输出目录（如 `generate_report` 在 config 缺 output_dir 时 fallback 到相对路径 `"reports"`）不再污染真实 reports 目录。判定基于绝对路径相等，显式指向临时目录的测试不受影响；测试自身 mock 写盘函数会覆盖本包装。
- **回归守护**：`test_generate_report_skeleton` 恢复为 `config={}` 不传 output_dir 的真实调用（复现缺陷场景），用运行前后 `reports/` 文件快照断言无新增，作永久回归守护——防线失效即测试失败。
- **验证**：test_orchestrator 50 passed；report 模式全量 1488 passed；dev-verify 1864 passed；check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；ruff format 一致；全程 reports 目录零新增。

### CLI 命令行包装脚本（cli.sh / cli.ps1）

- **新增**：`scripts/cli.sh`（Linux/macOS）与 `scripts/cli.ps1`（Windows PowerShell）——CLI 命令行模式的便捷入口。**无参数调用时默认生成报告**；传入参数时原样透传给 CLI，与直调 `python -m src.python.cli <args>` 完全等效。
- **无参数默认类型**：`report --type both`（Excel+HTML 双格式、不含 LLM、全部页签有数据）——响应实测反馈：初始默认 basic（约 1 分钟仅 Excel）只生成核心 5 页签 + 数据源矩阵，新闻/历史/LLM 相关页签为降级占位，不符合"无参数=完整报告"预期，故改为 both。注意：这仅改变**包装脚本**的无参数默认；CLI 本身 `--type` 默认仍为 basic（直调 `python -m src.python.cli report` 不带 `--type` 仍是轻量模式）。
- **实现**：自动切换到项目根目录并定位虚拟环境解释器（`.venv/bin/python` / `.venv\Scripts\python.exe`），缺失时提示先运行 launch.sh / launch.ps1 初始化；创建基础数据目录（data/holdings、data/cache、data/config、docs-stm/tmp、logs）；退出码透传 CLI 结果（0=成功/1=部分失败/2=严重错误）。
- **文档同步**：folders.md 目录树登记两文件 + 统计表说明补充；scripts-reference.md 一览表与启动脚本章节新增两条（同时给出直调 python 与包装脚本两种调用方式，并说明包装脚本默认 both 与 CLI 默认 basic 的差异）；how-to-start.md CLI 模式一节补充「便捷入口」用法 + 三种报告类型差异说明。
- **验证**：both 模式实测 14 页签中 13 个有实质数据（仅组合历史走势因 `--history` 默认 off 为占位，加 `--history auto` 可得）；`--help`/`report --help`/`cache --help` 参数透传正常；bash -x 确认无参数 `set -- report --type both`；dev-verify 1864 passed + 4 个 trace 检查全 [OK]；运行期间 reports 目录零新增。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.8（2026-08-04 ~ 2026-08-06）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
