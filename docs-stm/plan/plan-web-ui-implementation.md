# plan-8 轻量 Web UI — 设计文档（实施拆分）

> 关联：顶层设计 [`plan-web-ui.md`](./plan-web-ui.md) §1 · 计划项 `plan-8`（plan.md，P3）· 入口 `src/python/web/`（对齐 cli/、tui/ 组织方式）
>
> 本文档是 plan-8 的**详细评估与实施拆分**，用于指导后续开发。plan.md 仅保留概述行与本文档链接，不展开细节。

---

## 1. 背景与目标

当前交互入口是 **TUI**（`python -m src.python.tui`，终端菜单）与 **CLI**（`python -m src.python.cli`，命令行参数），两者共用 `report/orchestrator.py` 报告编排层。新用户门槛高：需要记命令、传参数、看终端输出。

**plan-8 目标**：新增第三个入口 `src/python/web/`，启动一个轻量 Web 服务，浏览器内即可完成「上传持仓 Excel → 选择报告格式 → 触发生成 → 实时进度 → 预览/下载」。

**定位**：单人投资工具，局域网（或本机）使用；**MVP 明确不做**——多用户/登录、LLM 配置在线修改、实时日志流（实时进度≠日志流）。

**可行性结论（调研前置）**：管线复用面极大。`generate_report(holdings, config, reporter, ...)` 是一个同步函数，通过可注入的 `ProgressReporter` 接口输出阶段消息，与终端完全解耦；`core/reader.read_holdings` 完成持仓解析；`config.get_config` 提供全部默认参数。**Web 层只需做「HTTP 通道 + 上传安全 + 后台任务 + 进度缓冲」，管线代码零改动**。

---

## 2. 收益分析

| 收益 | 说明 |
|------|------|
| **零学习成本** | 打开浏览器上传 Excel 即可，无需记命令/参数 |
| **分享简单** | 局域网内给 URL 即可查看报告 |
| **后台排队不阻塞** | 报告生成（full 实测 100~300s）在后台线程跑，浏览器可轮询进度，可同时发起多次生成 |
| **复用现有管线** | `generate_report` + `ProgressReporter` + `read_holdings` + `get_config` 四组件覆盖全部需求，编排层零改动 |
| **进度通道现成** | `report/progress.py` 的 `ProgressReporter` 抽象基类（`info/ok/warn/error/add_error/timer`）即可注入 Web 缓冲实现 |
| **健康检查/历史记录现成 JSON** | `core/check_sources.run_health_checks()` 返回结构化 dict；`core/perf.load_history()` 读 `perf_history.jsonl`——可直接做 `/api/health` 与「历史运行记录」接口，免再造轮子 |
| **HTML 报告自包含** | 报告 + 资产（chart.min.js 等）平铺在 `output_dir`，浏览器可直接预览，无服务端渲染依赖 |

---

## 3. 风险分析与缓解

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|----------|
| R1 | **上传安全**：恶意 xlsx、路径穿越、zip-bomb、超大文件 | 高——Web 新增攻击面核心 | §6 安全设计：`secure_filename` 净化 + 扩展名白名单 + 大小上限 + PK 魔数校验 + `mkstemp` 落盘 + 用完清理 |
| R2 | **服务生命周期**：常驻进程、端口冲突、启动/停止 | 中——偏离 CLI「跑完即退」 | 启动脚本端口检测；`Ctrl+C` 优雅退出；文档化启停 |
| R3 | **无认证暴露面** | 中——若误暴露公网 | 默认绑定 `127.0.0.1`；威胁模型文档化；公网需前置反向代理认证（MVP 不做内建认证） |
| R4 | **长任务异步**：full 100~300s 阻塞 | 中——浏览器需感知进度 | 后台线程 + 轮询（§4.3）；进程终止即任务丢失，MVP 接受并文档化 |
| R5 | **产物定位**：`ReportResult` 不含输出路径 | 低——需拼接 | 最新版文件名固定（`个人投资分析报告.html`/`.xlsx`），用 `config["output_dir"]`（已绝对化）+ 固定文件名定位 |
| R6 | **依赖新增** | 低——增量小 | 仅引入 Flask（含 werkzeug）；`pyproject.toml` + `requirements.txt` 同步；`launch.sh` 按 sha256 增量安装自动感知 |
| R7 | **并发/配置**：`get_config` 线程安全、`config.json` 不被 web 改写 | 低 | `get_config` 已有 mtime 缓存线程安全；web 只读配置不写入（改配置仍走文件/CLI） |
| R8 | **launch 脚本只启 TUI** | 低 | `launch.sh`/`launch.ps1` 扩展 `web` 参数选入口 |

---

## 4. 总体架构设计

### 4.1 分层原则

**web/ 是「薄入口层」**，与 cli/、tui/ 完全同构：只保留「HTTP 通道 + 交互外壳 + 上传/任务/进度差异化逻辑」，一切业务委托现有共享层。禁止在 web/ 内复制管线逻辑。

```
浏览器
  ⇅  HTTP（JSON / 静态）
src/python/web/          ← 薄层：Flask 路由 + 上传安全 + 后台任务 + 进度缓冲
  ⇅  直接调用（绝对导入 src.python.*）
report/orchestrator.generate_report()    # 编排（TUI/CLI/Web 共用）
report/progress.ProgressReporter         # 进度接口（Web 注入子类，管线零改动）
core/reader.read_holdings()              # 持仓解析（上传后复用）
config.get_config()                      # 默认参数（只读）
core/check_sources.run_health_checks()   # /api/health
core/perf.load_history()                 # 历史运行记录
```

### 4.2 技术选型：Flask

| 候选 | 结论 | 理由 |
|------|------|------|
| **Flask 3.x** | ✅ **推荐** | 依赖最小（werkzeug 自带 `secure_filename`、`send_from_directory`）；Jinja2 已有；同步模型与现有同步管线匹配；单人工具规模单文件/少文件即可组织 |
| FastAPI | ⚠️ 备选 | 需引入 starlette+pydantic+uvicorn；异步风格对同步阻塞的 `generate_report` 无增益，反增心智负担 |
| 标准库 `http.server` | ❌ 不取 | 路由/上传/静态/安全需手写，工作量大且安全边界易漏 |

依赖增量：`flask==3.1.x`（含 `werkzeug>=3.x`、`itsdangerous`、`click`、`blinker`）。MVP 用 Flask 自带开发服务器（`app.run()`），文档注明生产可选 waitress。不引入 uvicorn/gunicorn。

### 4.3 异步模型：后台线程 + WebProgressReporter + 轮询

管线本身**同步阻塞**（无内建队列/asyncio）。Web 层方案：

1. **RunManager**：`submit(...)` 用 `threading.Thread` 包一层 `generate_report`，返回 `run_id`；线程名 `web_run_*`（对齐既有 `orch_llm_news` 风格）。
2. **WebProgressReporter(ProgressReporter)**：重写 `info/ok/warn/error/add_error/timer`，事件追加到进程内 `dict[run_id, deque[(seq, level, msg, phase)]]`。管线零改动（只注入 reporter）。
3. **轮询**：`GET /api/runs/{id}/events?after=N` 返回序号 > N 的增量事件；前端 setInterval 轮询。
4. **完成**：线程结束写 run 记录（`ReportResult.exit_code`、`errors`、耗时、产物路径）；`perf_history.jsonl` 由管线自动落盘，`load_history()` 供「历史记录」页。
5. **并发限制**：MVP 不做任务队列上限，但 RunManager 记录运行中数量，前端提示当前并行任务数（建议 ≤ 2，LLM/行情并发有内部池保护）。

> 取消机制：管线无内建取消，MVP 不做（R4 文档化）。

### 4.4 模块拆分 `src/python/web/`

对齐 cli/（`cli.py` + `__main__.py`）、tui/（`tui.py` + `handlers_*.py`）的组织方式：

```
src/python/web/
├── __init__.py          # re-export 公共接口（main、create_app）
├── __main__.py          # python -m src.python.web 入口（对齐 cli/tui）
├── server.py            # 主入口：sys.path 注入、main()、端口检测、app.run()
├── app.py               # create_app() 应用工厂：路由注册、静态目录、错误处理（可测试）
├── handlers.py          # 路由 handler：页面/上传/生成/轮询/预览/下载/历史/健康
├── upload.py            # 上传安全：校验/净化/落盘/清理（纯函数，可单测）
├── progress.py          # WebProgressReporter(ProgressReporter) 事件缓冲
├── runs.py              # RunManager：后台线程任务注册表 + run 状态/事件
├── templates/
│   └── index.html       # 单页应用骨架
└── static/
    ├── main.js          # 上传/表单/轮询/进度渲染
    └── style.css        # 样式
```

各模块职责与复用的现有符号：

| 模块 | 职责 | 复用点 |
|------|------|--------|
| `server.py` | sys.path 注入（对齐 `cli.py:13-17`）、`main()`、`setup_logger()`、`init_config()`、端口检测、`app.run()` | `core.logger.setup_logger`、`config.init_config` |
| `app.py` | `create_app()` 工厂（Flask test_client 可测）、路由蓝图注册、JSON 错误处理 | — |
| `handlers.py` | 各路由 handler；生成 handler 复刻 `cli.py:_handle_report` 模板（读持仓→建 reporter→generate_report→映射 exit_code） | `orchestrator.generate_report`、`core.reader.read_holdings`、`core.check_sources.run_health_checks`、`core.perf.load_history` |
| `upload.py` | 上传文件校验/净化/`mkstemp` 落盘/清理（纯函数） | `tempfile`、`core.reader.get_xlsx_info`（可选预览元信息） |
| `progress.py` | `WebProgressReporter` 按 run_id 缓冲事件 | `report.progress.ProgressReporter`（继承） |
| `runs.py` | RunManager 后台线程 + run 状态/事件队列 | `threading.Thread`（对齐既有线程池风格） |

---

## 5. 架构约束符合性（C1~C20 核对表）

> 约束原文见 `technical.md` §8 表格（行 2443-2489）。逐条核对：**继承项** = Web 复用管线自动满足，无需额外动作；**遵守项** = Web 自身代码须遵守。

| 约束 | 要求 | Web 符合性 |
|------|------|-----------|
| C1 | 代码类型判定中心化 | **继承项**：管线内部；Web 不自实现判定 |
| C2 | 缓存统一管理 | **遵守项**：上传临时文件非缓存；持久化缓存仍走 `cache/` 接口 |
| C3 | 缓存/配置原子写入 | **遵守项**：上传文件落盘用 `tempfile.mkstemp` + `os.replace` |
| C4 | 会话级 API 复用 | **继承项**：管线内部 |
| C5 | HTTP 客户端统一 | **遵守项**：Web 若发起出站 HTTP（未来）必须走 `core/http_client.py` |
| C6 | Provider Chain 必经 | **继承项**：管线内部 |
| C7 | 报告序号不可硬编码 | **继承项**：管线内部 |
| C8 | 日志统一（禁 print） | **遵守项**：Web 服务日志用 `logging.getLogger("invest")`；`WebProgressReporter` 事件进内存队列并写 logger，不 print |
| C9 | LLM 模块注册 | **继承项**：管线内部 |
| C10 | 新闻召回策略可配置 | **继承项**：管线内部 |
| C11 | 测试标记强制 | **遵守项**：新增 `unit_web` marker 注册到 `conftest.py`，web 测试必标注 |
| C12 | 边缘测试文件隔离 | **遵守项**：上传安全等极端用例放 `*_edge.py` |
| C13 | 测试敏感路径隔离 | **遵守项**：web 测试遵守 `_isolate_sensitive_paths`；新增持久化文件（如 run 状态）须加入该 fixture |
| C14 | 渲染期数据不可写模块级全局 | **遵守项**：`runs.py` 的 run 注册表属运行态单例（与 `get_tracker()` 同类），须在 conftest 加 autouse 重置 fixture |
| C15 | 控制台日志着色 | **继承项**：logger 已处理（非 TTY 降级） |
| C16 | 路径绝对化 | **遵守项**：Web 只用 `get_config()` 绝对化路径，不依赖 CWD（对齐 cli/tui 已移除 `os.chdir`） |
| C17 | Multi-LLM Provider Chain | **继承项**：管线内部 |
| C18 | credentials_ref 凭据分离 | **遵守项**：Web 不触碰 LLM 凭据，不上传/不回显 `llm_key.json` |
| C19 | pipeline_data Schema 契约 | **继承项**：管线内部 |
| C20 | HTML 图表图下说明 | **继承项**：管线内部 |

**Web 自身新增遵守清单**（浓缩）：C3 原子写、C8 日志统一、C11/C12/C13/C14 测试规范、C16 路径绝对化、C18 凭据隔离 + §6 上传安全。

---

## 6. 安全设计

### 6.1 上传链路

| 环节 | 措施 |
|------|------|
| 文件名净化 | `werkzeug.utils.secure_filename` 剥离路径/非法字符（补 `.xlsx` 扩展名强制白名单） |
| 扩展名校验 | 仅接受 `.xlsx`（拒绝 `.xls`/`.xlsm`/宏等，openpyxl 不支持 xls） |
| 大小上限 | 10MB 上限（读流计数，超限即拒） |
| 内容校验 | 读前 4 字节校验 PK zip 魔数（`PK\x03\x04`），防改扩展名伪装；zip-bomb 由大小上限兜底 |
| 落盘 | `tempfile.mkstemp` 到 `data/holdings/uploads/`（受控目录，gitignore 排除），`os.replace` 原子写 |
| 解析 | 复用 `read_holdings`（表头/数值/行级容错已有）；空持仓/无有效账户则拒绝并返回中文错误 |
| 清理 | 生成任务结束后删除上传临时文件；启动时清理残留 |

### 6.2 预览/下载防穿越

- 预览/下载路由用 `flask.send_from_directory(output_dir, filename)`——**内置 `..` 净化**；
- 叠加**扩展名白名单**：仅 `html/js/map/css/png/svg/json/xlsx`；
- 不挂载整个 `data/` 为静态目录（避免暴露 config/cache/llm_key）。

### 6.3 威胁模型与部署

- 默认绑定 `127.0.0.1`（本机）；`--host 0.0.0.0` 需显式传参，文档警告仅限可信局域网。
- MVP 无认证/CSRF（单人工具）；副作用操作（触发生成）做**轻量同源校验**（校验 `Sec-Fetch-Site`/`Origin`，或未来加 token）。文档化：公网部署必须前置反向代理认证（basic auth）。
- 日志不泄漏：LLM key 脱敏已由 `_mask_api_key` 处理；Web 错误信息不回显文件系统绝对路径（对齐 `test_security.py` HTML 不泄路径基线）。

---

## 7. API 设计

响应统一信封：`{"ok": bool, "data": ..., "error": str|null}`（对齐仓库 API Response Format 惯例）。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 单页应用（index.html） |
| POST | `/api/upload` | 上传 xlsx，校验后返回 `{file_id, sheets, rows}`（`get_xlsx_info` 预览元信息） |
| POST | `/api/runs` | 触发生成：body `{file_id, report_type, fetch_history, force_llm}` → `{run_id}`（默认参数来自 `get_config()`） |
| GET | `/api/runs` | 运行中/最近 run 列表 |
| GET | `/api/runs/{id}` | run 详情：状态（running/done/failed）、阶段耗时、`exit_code`、errors、产物路径 |
| GET | `/api/runs/{id}/events?after=N` | 增量进度事件（轮询），`N` 为最后已读序号 |
| GET | `/api/runs/history` | `load_history()` 历史运行记录（perf 快照，含阶段耗时） |
| GET | `/api/reports/<path>` | `send_from_directory(output_dir, path)` 预览/下载（扩展名白名单） |
| GET | `/api/health` | `run_health_checks()` 数据源健康 JSON（复用现成结构化数据） |

`report_type` 映射：`basic`→仅 Excel / `both`→HTML+Excel（无 LLM）/ `full`→HTML+Excel+LLM（对齐 CLI `--type` 语义）。

---

## 8. 前端页面

单页 `index.html` 三段式：

1. **上传区**：拖拽/选择 xlsx → 上传校验 → 显示账户/sheet 预览（`get_xlsx_info`）；
2. **生成区**：报告格式（basic/both/full）、历史走势、强制 LLM 开关 → 提交 → 进度条（阶段名 + 序号，来自 `/events` 轮询）→ 完成后显示产物按钮（预览 HTML / 下载 Excel）；
3. **状态区**：数据源健康（`/api/health`）+ 历史运行记录（`/api/runs/history`）。

样式遵循 `design-quality` 原则（不做默认模板感）；语言中文；加载态/错误态明确。

---

## 9. 测试设计

### 9.1 marker 与隔离

- `conftest.py` `pytest_configure` 注册 **`unit_web`** marker（对齐 `unit_ui`/`unit_cli` 描述风格）。
- `src/test/unit/conftest.py` `_DIR_TO_MARKER` 登记 `unit_web`（新增目录强制子标记）。
- **autouse 单例重置**：`runs.py` RunManager 注册表属模块级单例（对齐 `get_tracker()` 模式），新增 `_auto_reset_run_manager` fixture。
- **持久化隔离**：上传临时目录 `data/holdings/uploads/` 若引入，加入 `_isolate_sensitive_paths` 重定向。
- **管线 mock 强制**：任何触发 `generate_report` 的测试 mock 之（`@patch("src.python.report.orchestrator.generate_report")`），LLM 一律 mock（CLAUDE.md 强制）。
- **output_dir 重定向**：涉及真实生成路径的测试把 `output_dir` 指向 `tmp_path`。

### 9.2 用例清单（示例）

| 模块 | 用例 |
|------|------|
| `upload.py`（unit_web） | 正常 xlsx 通过；非 xlsx 拒绝；超 10MB 拒绝；`..`/绝对路径文件名净化；非 PK 魔数拒绝；落盘后清理 |
| `progress.py`（unit_web） | 事件按 run_id 隔离；seq 单调；level/phase 正确 |
| `runs.py`（unit_web） | submit→running→done 状态机；exit_code 映射；并发两次 submit 各自隔离；`_auto_reset_run_manager` 生效 |
| `handlers.py`（unit_web，Flask test_client） | 上传→生成→轮询→产物 URL 全链路（mock 管线）；`send_from_directory` 路径穿越拒绝；错误信封格式 |
| 安全边缘（unit_web + edge，放 `*_edge.py`） | zip-bomb/伪装扩展名/超大文件/路径穿越/空持仓（对齐 `test_security_edge.py` 风格） |

---

## 10. 实施拆分（对应 plan.md 阶段工作量）

| 阶段 | 内容 | 工作量 | 验收标准 |
|------|------|:--:|------|
| **阶段 1 MVP 核心** | 依赖接入（pyproject/requirements/launch 脚本 `web` 参数）；`web/` 骨架（server/app/handlers/upload/progress/runs）；上传→生成→轮询→预览/下载全链路；上传安全（§6.1）；`unit_web` marker 注册 + 核心测试 | 3d | 浏览器完成一次 basic 报告生成并预览；上传安全用例绿；P0 门禁过 |
| **阶段 2 功能补齐** | 配置显示（`get_config()` 默认参数回填表单）；进度步骤展示（阶段名+序号）；历史运行记录页；`/api/health` 数据源状态；错误处理完善 | 1.5d | full 报告进度可观察；历史记录/健康页可用；错误路径有中文反馈 |
| **阶段 3 体验打磨** | 样式落地（design-quality）；加载态/按钮禁用/轮询节流；响应式（375px 移动端可用）；文档（how-to-start 新增 web 入口说明）；folders.md/数据快照刷新 | 1d | 视觉达标；移动端不溢出；用户文档齐全 |

**依赖次序**：阶段 1 不依赖阶段 2/3；每阶段独立可交付。全程遵守 §5 约束与 §9 测试规范。

---

## 11. 文件变更清单

### 新增
- `src/python/web/__init__.py` / `__main__.py` / `server.py` / `app.py` / `handlers.py` / `upload.py` / `progress.py` / `runs.py`
- `src/python/web/templates/index.html`、`src/python/web/static/main.js`、`src/python/web/static/style.css`
- `src/test/unit/web/test_upload.py`、`test_progress.py`、`test_runs.py`、`test_handlers.py`、`test_upload_edge.py`（edge）
- 本文档：`docs-stm/plan/plan-web-ui-implementation.md`

### 修改
- `pyproject.toml`：dependencies 增 `flask==3.1.x`
- `requirements.txt`：同步
- `scripts/launch.sh` / `launch.ps1`：支持 `web` 入口参数（默认仍 TUI）
- `src/test/conftest.py`：注册 `unit_web` marker + run 管理器重置 fixture（+ uploads 目录隔离）
- `src/test/unit/conftest.py`：`_DIR_TO_MARKER` 登记 `unit_web`
- `docs-stm/managements/folders.md`：目录树登记 `src/python/web/`、`src/test/unit/web/`、`docs-stm/plan/plan-web-ui-implementation.md`；项目统计表更新
- `docs-stm/managements/plan.md`：plan-8 条目加本文档链接（不展开细节）
- `docs-stm/manuals/how-to-start.md`：新增 Web 入口启动说明（阶段 3）

### 明确不动
- `report/orchestrator.py`、`report/progress.py`、`core/reader.py`、`config/*`：全部复用，**零改动**

---

## 12. 与 plan.md 衔接

- plan.md 当前 `plan-8 轻量 Web UI`（P3，推荐②）条目**仅补一行链接**指向本文档，不展开细节。
- plan-8 实施编号沿用 `plan-8`（不新占编号）；`plan-next` 不变（未新增任务）。
- 实施时按 §10 阶段推进，每阶段完成回填 changelog、自审 review-findings。

---

## 附录：调研关键结论速查（本次设计依据）

- 管线复用点：`generate_report`（`report/orchestrator.py:393`）、`ProgressReporter`（`report/progress.py:47`）、`read_holdings`（`core/reader.py:68`）、`get_config`（`config/_core.py:93`）、`run_health_checks`（`core/check_sources.py:191`）、`load_history`（`core/perf.py:263`）。
- 现有入口组织：`cli.py:13-17` / `tui.py:11-15` 的 sys.path 注入模式；`cli.py:_handle_report:239` 为 Web handler 模板。
- 产物定位：`output_dir`（`get_config()` 绝对化）+ 固定文件名 `个人投资分析报告.html`/`.xlsx`（`html_save.py:15`、`excel_writer.py:57`）。
- 既有安全基线：`src/test/scenario/security/test_security.py`、`src/test/unit/report/test_security_edge.py`（路径遍历/XSS/密钥脱敏已有防线，上传侧为新增缺口）。
- 数据源健康：`perf.py` 已落 `datasource_health.jsonl`。
