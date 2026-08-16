# plan-10 日志可视化 — 三端实现（CLI + TUI + Web）

## Context

plan.md 中 plan-10（P4 实验功能）「日志可视化」，设计文档 `docs-stm/archive/v0.10.x/web-ui/plan-web-ui.md §2`：
- 结构化日志查看（`--view-logs` 命令 + 报告尾部数据源状态表），预估 1d
- 收益：异常追查快（按级别筛选、时间过滤）；数据源健康可见
- 风险：日志 >100MB 解析卡顿 → 需 `tail -n 5000` 限制

**用户明确要求三端都实现**（CLI + TUI + Web），且**逻辑功能集中在核心层，渠道层只做薄展示**（架构分层原则）。

**现状盘点**：
- 「报告尾部数据源状态表」**已存在**——`data_source_matrix`（registry.py section 18）在 HTML + Excel 双端渲染，绿=ok/黄=degraded/红=failed，与设计意图吻合 → 该部分**确认覆盖，不改代码**
- 核心缺口是「结构化日志查看」——CLI/TUI/Web 三端都无日志查看功能
- `core/perf.py::load_health_history()`（读 `data/state/datasource_health.jsonl`）**定义了但零调用者**——健康检查历史无展示入口，需接线

## 架构分层原则（响应「逻辑功能不要在渠道层实现」）

**核心层（core/）承载所有逻辑**，三端只做薄展示层（调核心函数 + 渲染）：
- `core/log_reader.py`（新）：日志解析/过滤/尾部读取全部逻辑
- `core/perf.py`：新增 `summarize_health_history()` 聚合健康历史（与 `load_health_history` 同文件）
- CLI/TUI/Web **不实现任何解析/聚合逻辑**，只 import 核心函数输出/渲染

---

## 1. 核心层：`src/python/core/log_reader.py`（新，三端共享）

### 数据结构（不可变）

```python
@dataclass(frozen=True)
class LogEntry:
    time: str            # "YYYY-MM-DD HH:MM:SS,mmm"（与 _LOG_FORMAT 一致）
    level: str           # DEBUG/INFO/WARNING/ERROR/CRITICAL
    message: str         # 首行消息
    body: str            # 完整记录 = message + 续行（traceback），供展开
    is_decorative: bool  # 横幅/装饰性记录（如「⚗ 实验性功能已开启」整块、纯 ==== 行）

    def to_dict(self) -> dict: ...  # 供 Web JSON
```

### 关键点

- 日志路径来自 `logger.py::_LOG_FILE`（惰性引用，pytest 下自动为 test.log），**不硬编码**
- 续行归并：`_TIMESTAMP_RE`（`^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[[A-Z]+\]`）分割记录，非时间戳起始行归并到上一条（traceback 多行）；孤儿行丢弃（tail 边界不完整记录）
- `is_decorative`：消息仅由 `=/-/*/—` 重复字符构成或含 `_DECORATIVE_HINTS`（如「⚗ 实验性功能已开启」）→ 置灰显示，**不作为级别过滤依据**
- `tail_log(path, limit)`：从文件尾部反向分块读取（chunk 64KB），收集到 >limit 换行即停，防 >100MB 卡顿

### 函数签名

```python
def default_log_path() -> str                     # 惰性引用 logger._LOG_FILE
def parse_log(text: str) -> list[LogEntry]        # 纯函数：续行归并 + 孤儿行丢弃
def tail_log(path: str, limit: int = 5000) -> str # 尾部反向分块读
def read_log(path=None, *, limit=5000, level=None, since=None, until=None) -> list[LogEntry]
    # level: 最小级别阈值（ERROR 含 ERROR+CRITICAL，标准 logging 语义）
    # since/until: 时间前缀过滤（entry.time[:len(x)] >= x 词典序）
    # 无效 level → ValueError；文件缺失/空 → []
```

---

## 2. 核心层：`core/perf.py` 健康历史聚合

新增（与 `load_health_history` 同文件，L243 附近）：

```python
def summarize_health_history(limit: int = 10) -> list[dict]:
    """读 datasource_health.jsonl，返回最近 limit 次运行摘要。

    每条：{timestamp, report_type, holdings_count, total, ok_count, fail_count, failed_sources:[str]}
    failed_sources = [name for name, s in sources.items() if not s["ok"]][:5]
    """
```

逻辑集中在核心层，TUI/Web 只调 `load_health_history` + `summarize_health_history`。

---

## 3. CLI 渠道（`src/python/cli/cli.py`，薄展示）

1. `_build_parser()` 新增子命令：
   ```python
   logs_p = sub.add_parser("view-logs", help="查看结构化运行日志")
   logs_p.add_argument("--level", choices=["DEBUG","INFO","WARNING","ERROR","CRITICAL"], default=None)
   logs_p.add_argument("--lines", type=int, default=5000, help="读取末尾行数上限")
   logs_p.add_argument("--since", metavar="YYYY-MM-DD[ HH:MM:SS]")
   logs_p.add_argument("--until", metavar="YYYY-MM-DD[ HH:MM:SS]")
   ```
2. `_handle_view_logs(args) -> int`：调 `read_log(...)`，`print` 输出每条 `time [LEVEL] message`（多行 body 缩进）。无匹配 → 提示 + 返回 0；ValueError/OSError → logger.error + 返回 `_EXIT_SEVERE`
3. `main()` 在 `init_config` **之前**（`check-sources` 分支旁）加分派——view-logs 无需 config，配置损坏时也能查日志（诊断场景）：
   ```python
   if args.command == "view-logs":
       return _handle_view_logs(args)
   ```

---

## 4. TUI 渠道（薄展示）

### 新模块 `src/python/tui/handlers_log.py`

复用现有「print 输出 + `press_any_key()`」扁平循环模式（`_cmd_show_cache_stats` 先例）：

- `_cmd_view_logs()`：`input()` 提示级别筛选（空回车=全部）→ `read_log(limit=_DISPLAY_LINES=200, level=...)` → 打印头部统计 + 逐条彩色首行（ERROR 红/WARNING 黄，`ansi_colors`）+ traceback 折叠为 `⤷ 堆栈详情 +N 行` → `press_any_key()`
- `_cmd_view_health_history()`：`summarize_health_history(limit=10)` → 打印最近运行时间线（timestamp | ok/total | 失败源）→ `press_any_key()`；空 → 「暂无数据源健康历史记录」

### 菜单改动

- `tui_menu.py` MENU_ITEMS（L24-42）在 `("X","退出")` 前插入两项：
  - `("V", "查看最近运行日志（可按级别筛选）", None, False)`
  - `("H", "查看数据源健康历史（近期检查记录）", None, False)`
- `tui.py` `_bind_callbacks()`（L78-122）import handlers_log 两个函数，callbacks 增加 `"V"`/`"H"`；修正 L157 default_menu_key 注释

---

## 5. Web 渠道（薄展示）

### 后端 `src/python/web/handlers.py`

- 新增 `_handle_logs()`：`?level=` 校验（不在 `_LOG_LEVELS` → 400 BAD_PARAM）、`?lines=` int 解析并 clamp `[1,5000]`、`?since/until` 透传 → `read_log(...)`；ValueError/OSError → 500 LOG_READ_FAILED；成功 `_ok([e.to_dict() for e in entries])`
- `create_handlers()` 注册 `GET /api/logs`
- 可选：`GET /api/health/history` 返回 `summarize_health_history()`（与现有 `/api/health` 探测解耦）

### 前端 `src/static/web/index.html` + `main.js` + `style.css`

- ⑥ 状态卡后新增「⑦ 日志查看」卡：级别 `<select id="log-level">` + 「加载日志」按钮 `#log-load` + `#log-status` + `#log-list`。**手动加载不自动轮询**（响应设计文档「自动刷新高 IO → 需手动刷新」）
- `main.js`：`init()` 绑定按钮事件；`loadLogs()`/`renderLogs()` fetch `/api/logs`，全 `textContent`/DOM API（对齐 XSS 纪律）；每条 `<details class="log-entry log-{level}">` + `<summary>` + `<pre class="log-body">`（原生折叠）；`is_decorative` 置灰
- `style.css`：`.log-list/.log-entry/.log-body/.log-controls` + 级别配色 + 移动端适配

---

## 6. 测试计划（测试标记强制，测试隔离）

| 测试文件 | marker | 覆盖 |
|:--|:--|:--|
| `src/test/unit/core/test_log_reader.py`（新） | `unit, unit_core` | parse_log（基础/续行归并/装饰横幅/孤儿行/空）、read_log（注入路径/级别阈值/limit 截尾/since-until/无效级别/缺失文件）、tail_log（末 N/小于 N/空/缺失/边界记录头）、default_log_path 与 logger._LOG_FILE 一致 |
| `src/test/unit/cli/test_cli.py`（扩） | `unit, unit_cli` | TestArgparse view-logs（默认/参数/非法 level/lines）/ TestHandleViewLogs（输出/空/ValueError/OSError → 退出码）/ TestMain pre-config 透传（init_config 未调用） |
| `src/test/unit/ui/test_tui_menu.py`（改） | `unit, unit_ui` | 菜单数 17→19、V/H 索引、唯一性 |
| `src/test/unit/ui/test_handlers_log.py`（新） | `unit, unit_ui` | _cmd_view_logs（输出/级别提示透传/异常兜底）、_cmd_view_health_history（快照输出/空/异常）。**mock load_health_history/summarize**（data/state 被测试隔离重定向） |
| `src/test/unit/web/test_handlers.py`（扩） | `unit, unit_web` | /api/logs 成功/参数校验/clamp/500、index 渲染 log 卡 |

无新增 marker（复用 unit_core/unit_cli/unit_ui/unit_web），**conftest 无需改**。日志测试注入 tmp 路径或 mock，不触真实 logs/。

---

## 7. 实现顺序

1. **核心层**：`core/log_reader.py` + `perf.py::summarize_health_history` + `test_log_reader.py` → 跑 `unit_core`
2. **CLI**：parser + `_handle_view_logs` + main 分派 + `test_cli.py` 扩展 → 跑 `unit_cli`
3. **TUI**：`handlers_log.py` + MENU_ITEMS + `_bind_callbacks` + `test_tui_menu.py` 更新 + `test_handlers_log.py` → 跑 `unit_ui`
4. **Web**：`handlers.py` 路由 + 前端三件套 + `test_handlers.py` 扩展 → 跑 `unit_web`

依赖：1 → 2/3/4 可并行。

---

## 8. 文档同步项

- `technical.md` §6.7 语义命名表新增 3 行（**slug 必须在代码中出现**，check-semantic-index 反向校验）：
  - `| log_reader | 日志读取（read_log/tail_log/parse_log） | 日志可视化 | 诊断 | 无（模块级） |`
  - `| view_logs | 查看日志（CLI view-logs 子命令） | 日志可视化 | 诊断 | 无（子命令） |`
  - `| health_history | 数据源健康历史（load_health_history/summarize_health_history） | 日志可视化 | 监控 | data/state/datasource_health.jsonl |`
- `folders.md`：目录树补 `core/log_reader.py`、`tui/handlers_log.py` + 新增/扩展测试文件
- `changelog.md`：日志可视化条目（三端入口 + /api/logs + 健康历史接线）
- `plan.md`：plan-10 完成后从 P4 待办移至归档
- `test-coverage.md`：`.venv/bin/python scripts/collect-test-coverage.py` 刷新

---

## 9. 门禁（提交前）

```
.venv/bin/python scripts/test_runner.py --mode dev-verify
.venv/bin/python scripts/check-code-traces.py --ci
.venv/bin/python scripts/check-doc-traces.py --ci
.venv/bin/python scripts/check-task-numbering.py --ci
.venv/bin/python scripts/check-semantic-index.py --ci
.venv/bin/ruff format --check（非阻塞）
```

## 10. 边界与约束

- **日志统一**：`_handle_view_logs` 输出用 print 属**命令输出**（对齐 `run_check_sources` 先例，交互式命令输出不受统一日志约束限）；诊断走 logging
- **敏感路径隔离**：log_reader 只读；测试注入 tmp/mock，不触真实 `logs/` 与 `data/state/`
- **着色**：TUI 用 ansi_colors 按 NO_COLOR/TTY 自动降级
- **语义命名**：代码/注释/文档只用语义名（log_reader/view_logs/health_history），禁止 plan-10/rf-N
- **装饰性 ERROR 横幅**：is_decorative 置灰不过滤；级别过滤只按 levelname 阈值
