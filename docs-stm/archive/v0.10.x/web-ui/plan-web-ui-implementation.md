# plan-8 轻量 Web UI — 设计文档（实施拆分）

> 关联：顶层设计 [`plan-web-ui.md`](./plan-web-ui.md) §1 · 计划项 `plan-8`（plan.md，P4 实验功能，缺省关闭）· 入口 `src/python/web/`（对齐 cli/、tui/ 组织方式）
>
> 本文档是 plan-8 的**详细评估与实施拆分**，用于指导后续开发。plan.md 仅保留概述行与本文档链接，不展开细节。
>
> **设计状态**：已冻结，作为 plan-8 实施依据。架构为「薄入口 + 共享管线 + 单 worker 串行 + 上传安全 + 内存进度缓冲」，约束符合性、风险缓解、MVP 边界三方面已闭合。实施阶段 1~3 按 §10 推进，回归验收按 §9 门禁集成。

---

## 1. 背景与目标

当前交互入口是 **TUI**（`python -m src.python.tui`，终端菜单）与 **CLI**（`python -m src.python.cli`，命令行参数），两者共用 `report/orchestrator.py` 报告编排层。新用户门槛高：需要记命令、传参数、看终端输出。

**plan-8 目标**：新增第三个入口 `src/python/web/`，启动一个轻量 Web 服务，浏览器内即可完成「上传持仓 Excel → 选择报告格式 → 触发生成 → 实时进度 → 预览/下载」。

**定位**：单人投资工具，局域网（或本机）使用；**MVP 明确不做**——多用户/登录、LLM 配置在线修改、实时日志流。**边界（与 plan-10 日志可视化区分）**：Web 的「实时进度」是 run 内结构化事件消息（`/api/runs/{id}/events`），不是 `logs/app.log` 文件流；完整日志查看归 plan-10（`--view-logs`），Web 不重复实现。

**可行性结论**：管线复用面极大。`generate_report(holdings, config, reporter, report_type, fetch_history, force_llm, output_dir, ...)`（`report/orchestrator.py`）是同步函数，通过可注入的 `ProgressReporter` 接口输出阶段消息，与终端完全解耦；`core/reader.read_holdings` 完成持仓解析；`config.get_config` 提供全部默认参数。**Web 层只需做「HTTP 通道 + 上传安全 + 后台任务 + 进度缓冲」，管线代码零改动**。

---

## 2. 收益分析

| 收益 | 说明 | 达成层级 |
|------|------|----------|
| **零学习成本** | 打开浏览器上传 Excel 即可，无需记命令/参数（对不会 CLI/TUI 的新手价值最大） | **MVP** |
| **本机便捷** | 本机浏览器即可操作，免终端 | **MVP** |
| **局域网分享** | `--host 0.0.0.0` 显式开启后，局域网内给 URL 即可查看报告 | 阶段 3+（默认 127.0.0.1） |
| **后台排队不阻塞** | 报告生成（full 实测 100~300s）在后台线程跑，浏览器可轮询进度；**单 worker 串行队列**，可排队多个任务（一次一个） | **MVP** |
| **复用现有管线** | `generate_report` + `ProgressReporter` + `read_holdings` + `get_config` 四组件覆盖全部需求，编排层零改动 |
| **进度通道现成** | `report/progress.py` 的 `ProgressReporter` 抽象基类（`info/ok/warn/error/add_error/timer`）即可注入 Web 缓冲实现 |
| **健康检查/历史记录现成 JSON** | `core/check_sources.run_health_checks()` 返回结构化列表；`core/perf.load_history()` 读 `perf_history.jsonl`——可直接做 `/api/health` 与「历史运行记录」接口，免再造轮子 |
| **HTML 报告自包含** | 报告 + 资产（chart.min.js 等）平铺在 `output_dir`，浏览器可直接预览，无服务端渲染依赖 |

---

## 3. 风险分析与缓解

| # | 风险 | 影响 | 缓解措施 |
|---|------|------|----------|
| R1 | **上传安全**：恶意 xlsx、路径穿越、zip-bomb、超大文件 | 高——Web 新增攻击面核心 | §6 安全设计：服务端 uuid 重命名 + 扩展名白名单 + 大小上限 + PK 魔数校验 + `mkstemp` 落盘 + 用完清理 |
| R2 | **服务生命周期**：常驻进程、端口冲突、启动/停止 | 中——偏离 CLI「跑完即退」 | 启动脚本端口检测；`Ctrl+C` 优雅退出；文档化启停 |
| R3 | **无认证暴露面** | 中——若误暴露公网 | 默认绑定 `127.0.0.1`；威胁模型文档化；公网需前置反向代理认证（MVP 不做内建认证） |
| R4 | **长任务异步**：full 100~300s 阻塞 | 中——浏览器需感知进度 | 后台线程 + 轮询（§4.3）；进程终止即任务丢失，MVP 接受并文档化 |
| R5 | **产物定位**：`ReportResult` 不含输出路径 | 低——需拼接 | 最新版文件名固定（`个人投资分析报告.html`/`.xlsx`），用 `config["output_dir"]`（已绝对化）+ 固定文件名定位 |
| R6 | **依赖新增** | 低——增量小 | 仅引入 Flask（含 werkzeug）；`pyproject.toml` + `requirements.txt` 同步；`launch.sh` 按 sha256 增量安装自动感知 |
| R7 | **并发/配置**：`get_config` 线程安全、`config.json` 不被 web 改写 | 低 | `get_config` 已有 mtime 缓存线程安全；web 只读配置不写入（改配置仍走文件/CLI） |
| R8 | **launch 脚本只启 TUI** | 低 | `launch.sh`/`launch.ps1` 扩展 `web` 参数选入口 |
| R9 | **数据源熔断/降级**：full 长时间跑可能触发 provider 熔断（指数退避），生成失败 | 中 | run 失败提示区分"数据源暂不可用，稍后重试"（复用 `DegradationTracker` 状态）；前端给重试按钮 |
| R10 | **配置一致性**：Web 运行期外部改 `config.json`，run 内读到不一致参数 | 低 | **每个 run 启动时取一次 `get_config()` 快照**，run 期间不受外部修改影响（对齐 `_handle_report` 一次性读取语义） |
| R11 | **磁盘占用**：产物归档（180 天）+ `perf_history.jsonl` + 上传文件长期增长 | 低 | 上传文件生成后即清理；产物沿用 `excel_writer` 180 天保留；`perf_history.jsonl` 增长记录为观察项（后续补清理） |
| R12 | **浏览器兼容**：前端 JS 兼容性 | 低 | 目标 Chrome/Edge 90+、Firefox 90+（对齐 plan-1 兼容基线）；进度轮询用标准 fetch/EventSource |
| R13 | **产物半写**：run 中途失败留残缺最新版产物（HTML 已写/Excel 未写，管线固定文件名覆盖写） | 中 | web 层不额外处理（管线既有行为）；run 失败后前端提示"本次未完整生成，最新版文件可能不完整，建议重新生成"；建议重跑覆盖 |

---

## 4. 总体架构设计

### 4.1 分层原则

**web/ 是「薄入口层」**，与 cli/、tui/ 完全同构：只保留「HTTP 通道 + 交互外壳 + 上传/任务/进度差异化逻辑」，一切业务委托现有共享层。禁止在 web/ 内复制管线逻辑。

> **DRY 决策（三振法则）**：`handlers.py` 生成调用逻辑（读持仓→建 reporter→`generate_report`→映射 exit_code）与 `cli.py:_handle_report` 相似约 20 行，但 CLI 版含 `CliProgressReporter`/`sys.exit` 特有逻辑，抽取需动 `report/` 共享层、回归风险高。**MVP 不抽公共层**，Web 自实现薄逻辑；仅当出现第三处复用时再抽取。记技术债观察项。

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
| **Flask 3.x** | ✅ **推荐** | 依赖最小（werkzeug 自带 `send_from_directory`）；Jinja2 已有；同步模型与现有同步管线匹配；单人工具规模单文件/少文件即可组织 |
| FastAPI | ⚠️ 备选 | 需引入 starlette+pydantic+uvicorn；异步风格对同步阻塞的 `generate_report` 无增益，反增心智负担 |
| 标准库 `http.server` | ❌ 不取 | 路由/上传/静态/安全需手写，工作量大且安全边界易漏 |

依赖增量：`flask==3.1.x`，传递依赖 `werkzeug`、`itsdangerous`、`click`、`blinker` 同步 `==` 锁定进 `requirements.txt`（对齐仓库既有 `==` 锁定惯例；`launch.sh` 按 requirements sha256 增量安装自动感知）。

**服务器**：MVP 用 Flask 自带开发服务器 **`app.run(threaded=True)`**（线程池模式，对单人工具低并发足够；不引入 uvicorn/gunicorn 避免技术债）。waitress **不默认引入**——仅当出现并发请求排队明显卡顿或需 Windows 服务化时再评估（记录为已知演进路径，非 MVP 依赖）。

### 4.3 异步模型：后台线程 + WebProgressReporter + 轮询

管线本身**同步阻塞**（无内建队列/asyncio）。Web 层方案：

1. **RunManager**：维护**单 worker 串行队列**——同一时刻仅执行一个生成任务，后续任务排队等待（消除并发产物覆盖竞态）。`submit(...)` 把任务排入队列，worker 线程逐个执行，返回 `run_id`；线程名 `web_run_*`（对齐既有 `orch_llm_news` 风格）。**每个 run 在出队执行时取一次 `get_config()` 快照**，run 期间不受外部配置修改影响（R10）。**参数优先级**：前端提交的表单值**优先**，快照默认仅用于表单未填项（表单默认参数在页面加载时取一次 `get_config()`，页面刷新即重取）——避免页面参数与 run 快照时刻不一致。**run 记录保存实际 `output_dir`（出队快照）**，产物 URL/下载基于 run 记录而非实时 config（外部改 output_dir 时指向不错目录）。**跨进程产物竞态**：单 worker 队列仅防进程内；多进程（多开 web、或 web 与 TUI/CLI 并行）共享同一 `output_dir` 会互相覆盖最新版产物——文档化"同一 `output_dir` 仅一个入口运行"，server 启动时检测 `output_dir` 锁文件有占用则警告。**run 状态不持久化（权衡）**：MVP 内存态，服务重启即丢（进行中 run）；历史记录页数据源 = `load_history()` 已完成 run 的 perf 快照。**不持久化的权衡**：持久化需新增存储格式（sqlite/jsonl）+ 过期清理 + 并发写竞态处理，与 缓存原子写入 原子写约束叠加复杂度；收益却是"重启后恢复一次运行中 run"——单人工具重新上传重跑成本低，故 MVP 明确不持久化。
2. **WebProgressReporter(ProgressReporter)**：重写 `info/ok/warn/error/add_error/timer`，事件追加到进程内 `dict[run_id, deque[(seq, level, msg, phase)]]`。管线零改动（只注入 reporter）。**事件缓冲每 run 上限 500 条**（滚动丢弃最旧），防内存膨胀。
3. **轮询**：`GET /api/runs/{id}/events?after=N` 返回序号 > N 的增量事件；前端 setInterval 轮询（2s 固定，增量 `after=N` 已省流量）。
4. **完成**：worker 结束写 run 记录（`ReportResult.exit_code`、`errors`、耗时、产物路径）；`perf_history.jsonl` 由管线自动落盘，`load_history()` 供「历史记录」页。
5. **队列长度**：队列容量上限（如 ≤3，含运行中）；超出时 `POST /api/runs` 返回 429 与中文提示，避免任务无限堆积。
6. **run 记录保留**：内存 run 记录（含事件）**保留最近 20 个**，超出清理最旧（防服务长跑内存膨胀）。

> 取消机制：管线无内建取消，MVP 不做（R4 文档化）。

**演进路径（触发条件驱动，避免提前建设）**：
| 演进 | 触发条件 | 路径 |
|------|----------|------|
| 轮询 → SSE | 进度延迟感知成为问题（单 worker 下事件本就低频，MVP 轮询已够） | Flask 流式响应（response 生成器推送 `/events`），前端 `EventSource`，改动集中于 progress/runs + handlers |
| 单 worker → 并发 | 排队等待成为实际痛点（full 100~300s，MVP 单 worker 可能不够） | `ThreadPoolExecutor(max_workers=2)` + **每个 run 独立 `output_dir` 子目录**（解决最新版产物覆盖竞态） |
| 历史报告页 | 用户需要回看历史版本 | 读 `output_dir/YYYYMMDD/` 归档（180 天保留），`/api/reports/history` + 前端列表 |
| LLM 在线配置 | 明确需求 + 鉴权方案 | 复用 `set_config`（单键 patch），前端表单 + 密码/token 保护（MVP 已定为不做） |

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
| `server.py` | sys.path 注入（对齐 `cli.py:13-17`）、`main()`、`setup_logger()`、`init_config(config_path)`、**参数 `--host`（默认 `127.0.0.1`）/`--port`（默认 `8000`）/`--config`（对齐 CLI）**、**端口占用检测**（占用则报错并提示换端口）、`app.run(host, port, threaded=True)`。**生成线程 `daemon=True`**：`Ctrl+C` 时进程可正常退出（任务丢弃，R4 文档化） | `core.logger.setup_logger`、`config.init_config` |
| `app.py` | `create_app(run_manager=None)` 工厂（Flask test_client 可测）：支持**注入 run_manager**（默认全局单例，测试传内存 fake 免 patch 全局）、路由蓝图注册、**统一 JSON 错误处理**：`errorhandler(500)` 返回 `{"ok": false, "error": "服务器内部错误"}` + 记录 error 日志（不泄绝对路径）；413→中文上传超限提示。**`before_request` 生成 `request_id` 注入日志**（请求可关联到 run，错误定位） | — |
| `handlers.py` | 各路由 handler；生成 handler 复刻 `cli.py:_handle_report` 模板（读持仓→建 reporter→generate_report→映射 exit_code） | `orchestrator.generate_report`、`core.reader.read_holdings`、`core.check_sources.run_health_checks`、`core.perf.load_history` |
| `upload.py` | 上传文件校验/净化/`mkstemp` 落盘/清理（纯函数） | `tempfile`、`core.reader.get_xlsx_info`（可选预览元信息） |
| `progress.py` | `WebProgressReporter` 按 run_id 缓冲事件；事件 `seq` 用**单调递增整数**（非时间戳，测试确定性） | `report.progress.ProgressReporter`（继承） |
| `runs.py` | RunManager 单 worker 队列 + run 状态/事件队列；**注册表与事件队列均用 `threading.Lock` 保护**（worker 写、HTTP 线程读；事件读取做快照避免遍历中变更）。**worker 线程 `try/except` 包裹**：异常→run failed 状态 + error 日志（不崩溃服务、不静默挂起）；上传读流/临时文件用 `with` 确保关闭（资源泄漏审计） | `threading.Thread` + `threading.Lock`（对齐既有线程池风格） |

---

## 5. 架构约束符合性（核对表）

> 约束原文见 `technical.md` §8 表格。逐条核对：**继承项** = Web 复用管线自动满足，无需额外动作；**遵守项** = Web 自身代码须遵守。

| 约束 | 要求 | Web 符合性 |
|------|------|-----------|
| 代码类型判定中心化 | **继承项**：管线内部；Web 不自实现判定 |
| 缓存统一管理 | **遵守项**：上传临时文件非缓存；持久化缓存仍走 `cache/` 接口 |
| 缓存/配置原子写入 | **遵守项**：上传文件落盘用 `tempfile.mkstemp` + `os.replace` |
| 会话级 API 复用 | **继承项**：管线内部 |
| HTTP 客户端统一 | **遵守项**：Web 若发起出站 HTTP（未来）必须走 `core/http_client.py` |
| Provider Chain 必经 | **继承项**：管线内部 |
| 报告序号不可硬编码 | **继承项**：管线内部 |
| 日志统一（禁 print） | **遵守项**：Web 服务日志用 `logging.getLogger("invest")`；`WebProgressReporter` 事件进内存队列并写 logger，不 print。**werkzeug/Flask 自带访问日志纳入 invest logger 统一通道（级别调低或关闭），禁止双通道**。**日志隐私边界**：记录请求/生成/错误事件，**不记录上传文件名、持仓内容、绝对路径全文**（对齐既有 `_mask_api_key` 脱敏基线） |
| LLM 模块注册 | **继承项**：管线内部 |
| 新闻召回策略可配置 | **继承项**：管线内部 |
| 测试标记强制 | **遵守项**：新增 `unit_web` marker 注册到 `conftest.py`，web 测试必标注 |
| 边缘测试文件隔离 | **遵守项**：上传安全等极端用例放 `*_edge.py` |
| 测试敏感路径隔离 | **遵守项**：web 测试遵守 `_isolate_sensitive_paths`；新增持久化文件（如 run 状态）须加入该 fixture |
| 渲染期数据不可写模块级全局 | **遵守项**：`runs.py` 的 run 注册表属**运行态任务管理**（与 `get_tracker()` 同类），非渲染期数据——报告渲染数据仍经 reporter/模板 context 传递，不落入 run 注册表；该边界在 `runs.py` docstring 明确。须在 conftest 加 autouse 重置 fixture |
| 控制台日志着色 | **继承项**：logger 已处理（非 TTY 降级） |
| 路径绝对化 | **遵守项**：Web 只用 `get_config()` 绝对化路径，不依赖 CWD（对齐 cli/tui 已移除 `os.chdir`） |
| Multi-LLM Provider Chain | **继承项**：管线内部 |
| credentials_ref 凭据分离 | **遵守项**：Web 不触碰 LLM 凭据，不上传/不回显 `llm_key.json` |
| pipeline_data Schema 契约 | **继承项**：管线内部 |
| HTML 图表图下说明 | **继承项**：管线内部 |

**Web 自身新增遵守清单**（浓缩）：缓存原子写、日志统一、测试标记/边缘文件隔离/敏感路径隔离/单例重置测试规范、路径绝对化、凭据隔离 + §6 上传安全。

---

## 6. 安全设计

### 6.1 上传链路

| 环节 | 措施 |
|------|------|
| 文件名净化 | **弃用 `werkzeug.utils.secure_filename`**（会剥离中文——`个人投资.xlsx` → `xlsx`，中文持仓文件名是仓库常态）；改**服务端重命名**为无冲突安全临时名 `uploads/{uuid}.xlsx`（丢弃原始文件名，内容即身份，天然防路径穿越/中文问题） |
| 扩展名校验 | 仅接受 `.xlsx`（拒绝 `.xls`/`.xlsm`/宏等，openpyxl 不支持 xls）；**大小写归一化 `.lower()` 后校验** |
| 大小上限 | 10MB 上限（读流计数，超限即拒） |
| 内容校验 | 读前 4 字节校验 PK zip 魔数（`PK\x03\x04`），防改扩展名伪装；zip-bomb 由大小上限兜底 |
| 落盘 | `tempfile.mkstemp` 到 `data/holdings/uploads/`（基于 `PROJECT_ROOT` 绝对化拼接，不依赖 CWD，对齐路径绝对化；gitignore 排除），`os.replace` 原子写 |
| 解析 | **上传时立即内容预检**：复用 `read_holdings`（表头/数值/行级容错已有）；空持仓/无有效账户则拒绝并返回中文错误（避免"上传成功、生成失败"的坏体验）；预检通过的路径绑定 `file_id`，生成时直接复用。**行数上限**（如 5000 行，超限拒绝防超大文件解析过载）；持仓代码类型判定由管线内部 代码类型判定中心化 完成，web 不判定 |
| file_id | `secrets.token_urlsafe(16)` 生成（不可预测，防枚举推测他人/过期文件）；内存映射 `file_id→路径`，TTL 过期即失效 |
| 清理 | 生成任务结束**立即删除**上传临时文件；**未消费文件设 TTL（1h）定时清理**；启动时清理全部残留。`file_id→路径` 为内存映射，服务重启即失效，残留由启动清理兜底（R11 关联） |

### 6.2 预览/下载防穿越

- 预览/下载路由用 `flask.send_from_directory(output_dir, filename)`——**内置 `..` 净化**；
- 叠加**扩展名白名单**：仅 `html/js/map/css/png/svg/json/xlsx`，**先 `.lower()` 大小写归一化再校验**（防 `.HTML`/`.XLSX` 绕过）；
- 不挂载整个 `data/` 为静态目录（避免暴露 config/cache/llm_key）。

### 6.3 威胁模型（STRIDE）与部署

| 威胁类别 | 场景 | 缓解 |
|----------|------|------|
| **S 伪装** | 无认证、伪造来源 | 默认 `127.0.0.1`；同源校验（`Sec-Fetch-Site`/`Origin`）；LAN 部署文档化 basic auth |
| **T 篡改** | 恶意上传/数据投毒 | 上传链路 §6.1（净化/白名单/大小/魔数/原子写）；报告 HTML 由 Jinja2 autoescape 防护（既有） |
| **R 抵赖** | 操作无痕 | 请求/生成/错误经 invest logger 记录（日志统一），可追溯 |
| **I 信息泄露** | 路径/凭据/绝对路径回显 | 扩展名大小写归一化；错误不回显绝对路径；`llm_key` 不上传不回显（凭据分离）；`/api/runs` 不返回敏感字段 |
| **D 拒绝服务** | 频繁上传/轮询/健康检查 | `MAX_CONTENT_LENGTH`；单 worker 队列 + 429；**`/api/health` 结果缓存（如 60s），避免每次轮询真实跑数据源健康检查**；前端轮询节流 |
| **E 提权** | 路径穿越/任意文件读 | 服务端 uuid 重命名 + `send_from_directory` + 扩展名白名单 多层防护 |

- 默认绑定 `127.0.0.1`（本机）；`--host 0.0.0.0` 需显式传参，文档警告仅限可信局域网。
- MVP 无认证/CSRF（单人工具）；副作用操作（触发生成）做**轻量同源校验**（校验 `Sec-Fetch-Site`/`Origin`）。文档化：公网部署必须前置反向代理认证（basic auth）。
- 日志不泄漏：LLM key 脱敏已由 `_mask_api_key` 处理；Web 错误信息不回显文件系统绝对路径（对齐 `test_security.py` HTML 不泄路径基线）。

---

## 7. API 设计

响应统一信封：`{"ok": bool, "data": ..., "error": str|null}`（对齐仓库 API Response Format 惯例）。

> **应用级限制**：`MAX_CONTENT_LENGTH = 10MB`（超限 Flask 返回 413）；上传路由额外读流计数兜底。**超时策略**：上传读流设 60s 超时（慢速连接防长时间占用）；前端 fetch 设 `AbortSignal.timeout`（10s，轮询端点除外）；`/api/health` 缓存命中瞬时返回。

> **幂等与重试**：上传/生成**不引入服务端幂等**（MVP；重复上传由 TTL 清理 + 前端按钮禁用防连击兜底，重复生成由单 worker 队列自然排队）；`POST /api/runs` 队列满返回 429 中文提示"已有任务在跑，排队或稍后再试"。

> **错误契约（code + 中文 msg）**：错误响应统一 `{"ok": false, "error_code": str|null, "error": 中文文案}`。`error` 面向用户**全中文**（复用 R9/熔断提示等既有中文文案风格）；`error_code` 为机器可判定的短标识（`UPLOAD_TOO_LARGE`/`UPLOAD_BAD_FILE`/`RUN_QUEUE_FULL`/`FILE_EXPIRED`/`BAD_PARAM`/`SERVER_ERROR` 等），**前端按 code 分支动作（是否可重试/按钮态），不靠解析中文文案**。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 单页应用（index.html） |
| POST | `/api/upload` | 上传 xlsx，**立即内容预检**（`read_holdings` 空持仓/无有效账户即拒），校验后返回 `{file_id, sheets, rows}`（`sheets`=账户列表、`rows`=总行数；契约固定，前端据此渲染） |
| POST | `/api/runs` | 触发生成：body `{file_id, report_type, fetch_history, force_llm}` → `{run_id}`。**枚举校验**：`report_type ∈ {basic,both,full}`、`fetch_history/force_llm ∈ bool`，非法返回 400 中文错误；**校验 file_id 存在且未过期**（TTL 清理后引用→404） |
| GET | `/api/runs` | 运行中/最近 run 列表 |
| GET | `/api/runs/{id}` | run 详情：状态（running/done/failed）、阶段耗时、`exit_code`、errors、产物路径 |
| GET | `/api/runs/{id}/events?after=N` | 增量进度事件（轮询），`N` 为最后已读序号 |
| GET | `/api/runs/history` | `load_history()` 历史运行记录（perf 快照，含阶段耗时）。**结果短缓存 5s**（防频繁轮询重复读 `perf_history.jsonl`）——该 jsonl 属运行时状态记录（非缓存，不受 缓存统一管理 约束），但 Web 层加短缓存防重复读文件 |
| GET | `/api/reports/<path>` | `send_from_directory(output_dir, path)` 预览/下载（扩展名白名单） |
| GET | `/api/health` | `run_health_checks()` 数据源健康 JSON（复用现成结构化数据）；**结果仅内存缓存展示（60s），不重复落盘 `datasource_health.jsonl`**（落盘归管线健康检查，避免 web 轮询触发真实探测的副作用/重复写）；**历史趋势读 `load_health_history()`（与 plan-10 共享该数据源）** |

`report_type` 映射：`basic`→仅 Excel / `both`→HTML+Excel（无 LLM）/ `full`→HTML+Excel+LLM（对齐 CLI `--type` 语义）。

---

## 8. 前端页面

单页 `index.html` 三段式：

1. **上传区**：拖拽/选择 xlsx → 上传校验 → 显示账户/sheet 预览（`get_xlsx_info`）；
2. **生成区**：报告格式（basic/both/full）、历史走势、强制 LLM 开关 → 提交 → 进度条（阶段名 + 序号，来自 `/events` 轮询）→ 完成后显示产物按钮（预览 HTML / 下载 Excel）。**失败态**：按 `exit_code` 映射展示（0 成功 / 1 部分失败=黄色告警列 errors / 2 严重=红色），`errors` 逐条展示 + 通用建议文案（如"数据源暂不可用，稍后重试"——复用 R9 熔断提示）；提供「重新生成」按钮；
3. **状态区**：数据源健康（`/api/health`）+ 历史运行记录（`/api/runs/history`）。

样式遵循 `design-quality` 原则（不做默认模板感）；语言中文；加载态/错误态明确。**错误展示统一**：取服务端 `error` 中文文案直显；`error_code` 驱动分支动作（重试/提示/禁用按钮），中文文案不前端硬编码映射（避免服务端/前端文案漂移）。

**XSS 防护（渲染侧）**：前端**一律 `textContent`/DOM API 渲染服务端返回字符串**（errors/事件/状态，可能含数据源名等不可信内容），**禁止 `innerHTML`**（对齐既有 `test_security.py` XSS 基线；报告 HTML 自身由 Jinja2 autoescape 防护，web 前端是第二道防线）。

**可访问性（a11y）**：
- 键盘可达：上传区（`<label for=file>` + 按钮）、表单、进度条全部可 Tab 聚焦 + Enter 操作；
- 进度条 `role="progressbar"` + `aria-valuenow`（阶段序号）——阶段 1 就建立语义，避免后期返工；
- 对比度达标、`prefers-reduced-motion` 时降级动画；
- 错误/成功状态 `aria-live="polite"` 播报。

**轮询节流**：`setInterval` 2s 固定轮询（增量 `after=N` 已省流量）；页面不可见时 `visibilitychange` 暂停，恢复可见立即同步一次。

**状态恢复（刷新/重连）**：前端 `localStorage` 存最近 `run_id`，页面刷新后自动重连 `/api/runs/{id}` 恢复进度/结果（避免 full 报告结果刷新即丢）；`file_id` 失效（TTL/服务重启）时提示重新上传。

**静态资源与缓存**：web 静态（`main.js`/`style.css`）带版本查询串 `?v={APP_VERSION}`（防浏览器缓存旧 JS 导致功能异常）；web 只服务自己的 `web/static/`，报告资产（`chart.min.js` 等）经 `/api/reports` 从 `output_dir` 提供——两处静态分离，不混同。

**前端工具链权衡**：前端用**原生 JS（ES6）+ 单 index.html + 单 CSS**，**不引入 npm/webpack/vite/React 等构建链**——仓库至今零 node 工具链，引入需新增 node 依赖 + 构建产物版本管理，对单文件前端是净技术债；当前复杂度（上传/表单/轮询/进度渲染）原生实现完全可控，仅当出现多视图路由/组件化需求时再评估。

---

## 9. 测试设计

### 9.1 marker 与隔离

- `conftest.py` `pytest_configure` 注册 **`unit_web`** marker（对齐 `unit_ui`/`unit_cli` 描述风格）。
- `src/test/unit/conftest.py` `_DIR_TO_MARKER` 登记 `unit_web`（新增目录强制子标记）。
- **autouse 单例重置**：`runs.py` RunManager 注册表属模块级单例（对齐 `get_tracker()` 模式），新增 `_auto_reset_run_manager` fixture。
- **持久化隔离**：上传临时目录 `data/holdings/uploads/` 若引入，加入 `_isolate_sensitive_paths` 重定向。
- **管线 mock 强制**：任何触发 `generate_report` 的测试 mock 之（`@patch("src.python.report.orchestrator.generate_report")`），LLM 一律 mock（CLAUDE.md 强制）。
- **output_dir 重定向**：涉及真实生成路径的测试把 `output_dir` 指向 `tmp_path`。

### 9.2 门禁集成

- `unit_web` marker **必须纳入 `scripts/test_runner.py` MODES**：dev-verify（提交前）、verify（合入前）、regression（发布前）的 unit 集合均加 `unit_web`，否则 web 测试写了但门禁不跑（形同虚设）。
- **CI 集成**：`unit_web` 在 MODES 配置里**单点定义**（一处改，三模式自动继承，杜绝矩阵漏配）；CI/干净环境用 `test_runner.py --mode dev-verify` 覆盖 web 核心测试，并验证 `launch.sh` 增量安装 Flask 在干净环境可完成。
- `edge` 测试被 dev-verify 排除：上传/预览安全边缘用例在 **verify / regression** 模式覆盖（对齐既有 `test_security_edge.py` 的归属）。
- 新增 web 测试后刷新 `docs-stm/managements/test-coverage.md` 数据快照（发布前 `collect-test-coverage.py` 强制，见 §11）。
- **发布前验证**：`launch.sh` 增量安装 Flask 在干净环境可离线完成（依赖从 PyPI 拉取，发布回归清单确认有网环境可安装）。

### 9.3 用例清单

| 模块 | 用例 |
|------|------|
| `upload.py`（unit_web） | 正常 xlsx 通过；非 xlsx 拒绝；超 10MB 拒绝；`..`/绝对路径文件名净化；非 PK 魔数拒绝；落盘后清理 |
| `progress.py`（unit_web） | 事件按 run_id 隔离；seq 单调；level/phase 正确 |
| `runs.py`（unit_web） | submit→running→done 状态机；exit_code 映射；并发两次 submit 各自隔离；`_auto_reset_run_manager` 生效 |
| `handlers.py`（unit_web，Flask test_client） | 上传→生成→轮询→产物 URL 全链路（mock 管线）；`send_from_directory` 路径穿越拒绝；错误信封格式 |
| 安全边缘（unit_web + edge，放 `*_edge.py`） | zip-bomb/伪装扩展名/超大文件/路径穿越/空持仓（对齐 `test_security_edge.py` 风格） |

---

## 10. 实施拆分

| 阶段 | 内容 | 工作量 | 验收标准 |
|------|------|:--:|------|
| **阶段 1 MVP 核心** | 依赖接入（pyproject/requirements/launch 脚本 `web` 参数）；`web/` 骨架（server/app/handlers/upload/progress/runs）；上传→生成→轮询→预览/下载全链路；上传安全（§6.1）；`unit_web` marker 注册 + 核心测试 | 3d | 浏览器完成一次 basic 报告生成并预览；上传安全用例绿；P0 门禁过 |
| **阶段 2 功能补齐** | 配置显示（`get_config()` 默认参数回填表单）；进度步骤展示（阶段名+序号）；历史运行记录页；`/api/health` 数据源状态；错误处理完善 | 1.5d | full 报告进度可观察；历史记录/健康页可用；错误路径有中文反馈 |
| **阶段 3 体验打磨** | 样式落地（design-quality）；加载态/按钮禁用/轮询节流；响应式（375px 移动端可用）；文档（how-to-start 新增 web 入口说明 + faq.md 补端口冲突/无法访问/进度卡住常见问题 + README 功能提点）；folders.md/数据快照刷新；**实施完成后本文档与 `plan-web-ui.md` 归档至 `archive/v0.x.x/web-ui/`** | 1d | 视觉达标；移动端不溢出；用户文档齐全 |

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
- `requirements.txt`：同步 `flask==3.1.x` 及传递依赖 `werkzeug==x.y.z`/`itsdangerous==x.y.z`/`click==x.y.z`/`blinker==x.y.z` **全链 `==` 锁定**（`launch.sh` 按 requirements sha256 增量安装：requirements 变更→`.deps_installed` 标记失效→自动重装）
- `scripts/launch.sh` / `launch.ps1`：支持 `web` 入口参数（默认仍 TUI）；`launch.sh web [--host 127.0.0.1] [--port 8000]`
- `scripts/test_runner.py`：MODES 的 dev-verify / verify 模式 unit 集合加 `unit_web`（门禁集成，见 §9.2）
- `src/test/conftest.py`：注册 `unit_web` marker + run 管理器重置 fixture（+ uploads 目录隔离）
- `src/test/unit/conftest.py`：`_DIR_TO_MARKER` 登记 `unit_web`
- `docs-stm/managements/folders.md`：目录树登记 `src/python/web/`、`src/test/unit/web/`、`docs-stm/plan/plan-web-ui-implementation.md`；项目统计表更新（web 模块代码行数/文件数/测试用例数，发布前 `collect-test-coverage.py` 刷新数据快照）
- `docs-stm/plan/plan-web-ui-implementation.md`（本文档）：实施完成后随 `archive/v0.x.x/web-ui/` 归档；归档版本头部同步发布版本号标记（设计文档不在 check-version-consistency 清单内，但归档需可追溯）
- **发布门禁全链核对**：P2 发布前依 CLAUDE.md 发布门禁逐项过——`test_runner.py --mode verify,regression`（含 `unit_web`）+ 3 个 `check-*.py --ci` + 版本号一致（`check-version-consistency.py` 全 [OK]）+ `collect-test-coverage.py` 数据快照刷新（folders.md 统计/test-coverage.md/datasource 文档），缺一不可
- `docs-stm/managements/plan.md`：plan-8 条目加本文档链接（不展开细节）
- `docs-stm/manuals/how-to-start.md`：新增 Web 入口启动说明（阶段 3）
- `docs-stm/managements/test-coverage.md`：新增 web 测试计数数据快照（发布前 `collect-test-coverage.py` 刷新）
- **发布前安全审计（步骤）**：`bandit` 静态扫描 `src/python/web/`（上传/下载/输入边界为重点）+ `security-reviewer` agent 专项审计，对齐既有 `test_security.py` 基线；CRITICAL/HIGH 修复后方可过 P2 发布门禁

### 明确不动
- `report/orchestrator.py`、`report/progress.py`、`core/reader.py`、`config/*`：全部复用，**零改动**

---

## 12. 与 plan.md 衔接

- plan.md 当前 `plan-8 轻量 Web UI`（P4 实验功能，缺省关闭，选做无排期）条目**仅补一行链接**指向本文档，不展开细节。
- plan-8 实施编号沿用 `plan-8`（不新占编号）；`plan-next` 不变（未新增任务）。
- 实施时按 §10 阶段推进，每阶段完成回填 changelog、自审 review-findings。
- **实施前遗留动作**：① 阶段 1 编码时先注册 `unit_web` marker 再写测试（防测试写了不跑）；② 安全审计步骤在阶段 1 上传链路完成后即执行一次，不拖到发布前。

---

## 13. 附录：调研关键结论速查（当前设计依据）

- 管线复用点：`generate_report`（`report/orchestrator.py:336`）、`ProgressReporter`（`report/progress.py:47`）、`read_holdings`（`core/reader.py:86`）、`get_config`（`config/_core.py:83`）、`run_health_checks`（`core/check_sources.py:191`）、`load_history`（`core/perf.py:263`）。
- 现有入口组织：`cli.py:13-17` / `tui.py:11-15` 的 sys.path 注入模式；`cli.py:_handle_report:300` 为 Web handler 模板。
- 产物定位：`output_dir`（`get_config()` 绝对化）+ 固定文件名 `个人投资分析报告.html`/`.xlsx`（`html_save.py:31`、`excel_writer.py:59`）。
- 既有安全基线：`src/test/scenario/security/test_security.py`、`src/test/unit/report/test_security_edge.py`（路径遍历/XSS/密钥脱敏已有防线，上传侧为新增缺口）。
- 数据源健康：`perf.py` 已落 `datasource_health.jsonl`。

---

## 14. 文件变更清单总表（供审查）

> 本表汇总 plan-8 实施涉及的全部**新增/修改**文件，供评审逐项核对。类别分组：**A** 新增—Web 应用代码 · **B** 新增—测试 · **C** 新增—文档 · **D** 修改—配置与脚本 · **E** 修改—测试基建 · **F** 修改—管理/用户文档 · **G** 明确不动（复用现有，零改动）。

### A. 新增 — Web 应用代码

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `src/python/web/` | `__init__.py` | 新增 | 子包标记；re-export 公共接口（`main`、`create_app`） |
| `src/python/web/` | `__main__.py` | 新增 | `python -m src.python.web` 入口（对齐 `cli`/`tui` 组织方式） |
| `src/python/web/` | `server.py` | 新增 | 主入口：`sys.path` 注入、`main()`、端口占用检测、`app.run(threaded=True)` |
| `src/python/web/` | `app.py` | 新增 | `create_app()` 应用工厂：路由注册、静态目录、统一 JSON 错误处理、`request_id` 日志注入（可测试） |
| `src/python/web/` | `handlers.py` | 新增 | 路由 handler：页面/上传/生成/轮询/预览/下载/历史/健康（复刻 `cli.py:_handle_report` 模板） |
| `src/python/web/` | `upload.py` | 新增 | 上传安全：扩展名校验/PK 魔数/行数上限/uuid 重命名落盘/清理（纯函数，可单测） |
| `src/python/web/` | `progress.py` | 新增 | `WebProgressReporter(ProgressReporter)`：run 事件缓冲（seq 单调、500 条上限） |
| `src/python/web/` | `runs.py` | 新增 | `RunManager`：单 worker 队列 + run 状态/事件注册表（Lock 保护、异常兜底） |
| `src/python/web/templates/` | `index.html` | 新增 | 单页应用骨架（上传/生成/进度/状态三段式，中文，`textContent` 渲染） |
| `src/python/web/static/` | `main.js` | 新增 | 前端逻辑：上传/表单/轮询/进度渲染/状态恢复（原生 ES6，无构建链） |
| `src/python/web/static/` | `style.css` | 新增 | 样式（design-quality 原则，响应式/可访问性） |

### B. 新增 — 测试

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `src/test/unit/web/` | `test_upload.py` | 新增 | 上传安全单测（unit_web）：非 xlsx/超限/净化/PK 魔数/清理 |
| `src/test/unit/web/` | `test_progress.py` | 新增 | 事件缓冲单测：run 隔离/seq 单调/level 正确 |
| `src/test/unit/web/` | `test_runs.py` | 新增 | RunManager 状态机：submit→running→done、并发隔离、单例重置 |
| `src/test/unit/web/` | `test_handlers.py` | 新增 | Flask test_client 全链路（mock 管线）：上传→生成→轮询→产物 URL；错误信封 |
| `src/test/unit/web/` | `test_upload_edge.py` | 新增 | 安全边缘用例（unit_web + edge）：zip-bomb/伪装扩展名/路径穿越/空持仓 |

### C. 新增 — 文档

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `docs-stm/plan/` | `plan-web-ui-implementation.md` | 新增 | 本文档：plan-8 详细评估与实施拆分（实施后归档 `archive/v0.x.x/web-ui/`） |

### D. 修改 — 配置与脚本

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `(仓库根)` | `pyproject.toml` | 修改 | dependencies 增 `flask==3.1.x` |
| `(仓库根)` | `requirements.txt` | 修改 | 同步 `flask` 及传递依赖 `werkzeug/itsdangerous/click/blinker` 全链 `==` 锁定（`launch.sh` 增量安装感知） |
| `scripts/` | `launch.sh` | 修改 | 支持 `web` 入口参数（默认仍 TUI）：`launch.sh web [--host] [--port]` |
| `scripts/` | `launch.ps1` | 修改 | Windows 侧支持 `web` 入口参数（对齐 `launch.sh`） |
| `scripts/` | `test_runner.py` | 修改 | MODES 的 unit 集合加 `unit_web`（dev-verify/verify/regression 三模式单点继承） |

### E. 修改 — 测试基建

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `src/test/` | `conftest.py` | 修改 | 注册 `unit_web` marker + `_auto_reset_run_manager` 单例重置 fixture + uploads 目录隔离 |
| `src/test/unit/` | `conftest.py` | 修改 | `_DIR_TO_MARKER` 登记 `unit_web`（新增目录强制子标记） |

### F. 修改 — 管理/用户文档

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `docs-stm/managements/` | `folders.md` | 修改 | 目录树登记 `src/python/web/`、`src/test/unit/web/`、本文档；项目统计表更新（发布前刷新数据快照） |
| `docs-stm/managements/` | `plan.md` | 修改 | plan-8 条目补本文档链接（不展开细节）；编号/阶段不变 |
| `docs-stm/managements/` | `test-coverage.md` | 修改 | 新增 web 测试计数数据快照（发布前 `collect-test-coverage.py` 刷新） |
| `docs-stm/manuals/` | `how-to-start.md` | 修改 | 新增 Web 入口启动说明（阶段 3）+ faq 补端口冲突/无法访问/进度卡住常见问题 |

### G. 明确不动（复用，零改动）

| 目录 | 文件名 | 类型 | 目的 |
|------|--------|:--:|------|
| `src/python/report/` | `orchestrator.py` | 不动 | `generate_report` 编排层，Web 直接复用 |
| `src/python/report/` | `progress.py` | 不动 | `ProgressReporter` 接口，Web 注入子类 |
| `src/python/core/` | `reader.py` | 不动 | `read_holdings` 持仓解析，上传预检复用 |
| `src/python/config/` | `*` | 不动 | `get_config`/`init_config`，Web 只读默认参数 |

> **待评审关注点**：① 是否所有新增文件都有独立职责（高内聚、可单测）；② `report/` 共享层零改动是否成立（§11「明确不动」）；③ 依赖 `==` 全链锁定与既有 `launch.sh` 增量安装机制是否自洽；④ 文档修改项是否覆盖发布门禁（folders 统计 / 版本头 / 数据快照）；⑤ 是否需要为 web 增加 `docs-stm/manuals/` 分册（当前并入 how-to-start + faq，不新增分册）。
