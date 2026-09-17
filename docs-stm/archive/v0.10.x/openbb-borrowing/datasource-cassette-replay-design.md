# 数据源记录-回放测试实施设计（借鉴 OpenBB pytest-recorder / vcrpy cassette）

> 来源：[`openbb-data-provider-analysis.md`](openbb-data-provider-analysis.md) §建议C（OpenBB Platform 数据层工程借鉴评估，2026-09-09）。
> 级别：**测试基建（非运行时实验开关）**——本计划不引入 `features.json` 开关，理由见「为何不设开关」。
> 状态：**已实现**（自研轻量回放引擎，已录 6 份真实响应夹具）。

## Context

现有数据源测试全部用**手工构造的假响应**（`src/test/unit/providers/test_tencent.py` 等内联 `monkeypatch` 返回 dict/文本）。这些假响应是**人写出来的「我以为上游长什么样」**，因此测不到最要命的一类回归：**真实响应体格式与解析器假设不一致**（上游改字段名/加前后缀/换分隔符/返回 HTML 错误页/多出 BOM）。

`src/test/live/` 的真实网络套件补了「源可达 + 结构存在」这一层，但它**不入门禁**（`-m "not live"` 默认排除，conftest `_block_external_network` 阻断真实网络），且只断言结构不断言解析结果；源临时不可达时整条断言链失效，无法作为回归防线。

OpenBB 用 vcrpy/pytest-recorder 把**真实响应体**录成 cassette 进仓库，此后离线回放——既有真实数据，又不碰网络。本项目**不引第三方依赖**（当前环境无 vcrpy/responses/httpretty，见评估文档「需评估引依赖 vs 自研轻量回放」），按推荐结论**自研轻量回放**：实现收敛在单一模块，录制仅限显式 opt-in。

预期结果：`pytest src/test/` 默认离线跑通，其中包含「真实响应体 → 当前解析器 → 统一字段」的回归断言；上游格式漂移或解析器回归会**在门禁内**失败。

## 语义命名（先定语义名再设计）

| 语义 slug | 中文名（文档/UI） | 归入章节 | 决策链环节 | config 开关 |
|:--|:--|:--|:--|:--|
| `datasource_cassette` | 数据源记录-回放（真实响应体离线回归） | 数据源可用性矩阵 | 监控 | 无（测试基建 + `cassettes` 子命令） |

代码标识符：模块 `core/cassette.py`；类 `Cassette`/`CassetteTransport`；函数 `record_cassette`/`replay_cassette`/`list_cassettes`/`verify_cassettes`/`normalize_request_key`。

## 为何不设 `features.json` 开关

本计划**不产生任何运行时行为分支**：cassette 只在测试进程与维护命令中被使用。给它一个功能开关会得到一个「开/关都不改变任何运行结果」的开关——那是纯粹的登记负担与技术债，而非可实验的特性。其「缺省关闭、需显式启用」由**已有机制**如实表达：

- **录制**：需 `--run-live`（放行真实网络）**且** `--record-cassettes`（开启写入）双开关，缺一不可；录制目标目录与写盘均为显式动作。
- **回放**：默认行为，离线运行，不需要任何开关。
- **三面开关**（TUI 菜单 / Web 配置面板 / `--experiment`）因此不适用；用户可见入口是 `cassettes` 维护子命令（只读、离线）。

## 变更范围

### 1. 传输层注入点 — `src/python/core/http_client.py`（唯一生产代码改动）

- 新增模块级传输工厂注入：`use_transport_factory(factory)` 上下文管理器（`factory() -> httpx.BaseTransport | None`），`make_http_client()` 在工厂存在时以 `transport=factory()` 构造客户端。
- 动机：`make_http_client` 已是全项目 HTTP 的**唯一构造点**（架构约束：HTTP 客户端统一），在此注入即一处生效、provider 全部零改动；替代方案「逐个 patch `src.python.providers.<name>.make_http_client`」会随 provider 增减而腐化。
- 未安装工厂时行为与现状**完全一致**（`transport=None` → httpx 默认传输）。

### 2. 录制/回放引擎 — 新增 `src/python/core/cassette.py`

- 存取格式：`src/test/data/cassettes/<name>.json`（git 跟踪）——
  ```json
  {"version": 1, "name": "tencent_quote", "source": "tencent",
   "recorded_at": "2026-09-10T12:00:00+08:00",
   "interactions": [{"request": {"method": "GET", "url": "..."},
                     "response": {"status": 200, "headers": {...}, "body": "..."}}]}
  ```
- `CassetteTransport(httpx.BaseTransport)`：按 **`normalize_request_key(method, url)`** 匹配交互并返回录制响应；响应体以文本存（本项目数据源返回 GBK/UTF-8 文本与 JSONP，文本存法保真且可直接人读比对）。
- 请求键归一：剥离易变查询参数（`_` 时间戳、`callback`/`reqid` 回调名）后匹配，避免每次录制都产生新条目；归一规则显式集中在一处并有单元测试。
- **回放未命中 = 显式失败**：抛 `CassetteMissError` 并在消息中给出「已录制键清单 + 提示需重新录制」。绝不静默回落真实网络（防「以为在回放、实则在联网」的隐性依赖）。
- **录制模式未命中 = 追加**：真实请求发出→响应写入 cassette；整个 cassette 在会话结束时**一次原子写盘**（`tempfile.mkstemp` + `os.replace`，与 `save_feature_overrides` 同款习语；架构约束：原子写入）。
- `list_cassettes()` → 索引列表（name/source/recorded_at/交互数/文件大小）；`verify_cassettes()` → 逐条回放并把响应体交给**当前解析器**解析，报告「可解析 / 解析失败」，实现「真实响应体的解析路径」回归的**人工可核验入口**。

### 3. 测试接入 — `src/test/conftest.py`

- 新增 `--record-cassettes` 选项（默认关，与既有 `--run-live` 并列注册）。
- 新增 autouse fixture `_install_cassette_replay`：为每个测试用例安装「该用例声明要用的 cassette」的回放传输；未声明 cassette 的用例不受影响（不安装工厂 → 行为同现状）。
- 用例通过 `pytest.mark.cassette("tencent_quote")` 声明所需 cassette；marker 注册进 `_KNOWN_MARKERS` 与 `pytest_configure` 的 `markers` 列表（架构约束：测试标记强制）。
- 录制路径仅在 `--run-live` **且** `--record-cassettes` 时生效，且只在 `live` 套件内，机制上不入门禁。

### 4. 回放回归用例

- `src/test/unit/providers/test_cassette_replay.py`（`unit` + `unit_providers`）：对已录制的行情/基金净值/持仓/排名真实响应，断言「当前解析器 → 统一字段」的完整结果（字段值逐项断言，而非仅结构），锁定真实响应体的解析路径。
- `src/test/unit/core/test_cassette.py`（`unit` + `unit_core`）：引擎自身单测——请求键归一（含时间戳/回调参数剥离）、回放命中、**未命中抛错**、录制追加与原子写盘、cassette 文件损坏时的可读报错、版本号不匹配报错。
- `src/test/unit/core/test_cassette_edge.py`（`unit` + `unit_core` + `edge`）：空 `interactions`、非 JSON、缺字段、未知 `version`、重复键等边界。
- `src/test/live/test_live_cassette_record.py`（`live`）：录制入口，默认跳过；用例内显式断言「录制写入文件存在且 `verify_cassettes` 可通过」。

### 5. 维护入口 — `src/python/cli/cli.py`

- 新增 `cassettes` 子命令（**不受任何开关约束**，与 `doctor` 同例：这是只读维护命令）：
  - `cassettes`：列出已录制 cassette 与录制时间/交互数；
  - `cassettes --verify`：逐条离线回放 + 交给当前解析器解析，退出码 0/2（有解析失败即 2）。

### 6. 文档

- `docs-stm/managements/folders.md`：新增 `core/cassette.py`、`src/test/cassette` 相关文件与 `src/test/data/cassettes/` 目录树条目。
- `docs-stm/managements/technical.md`：语义命名表新增 `datasource_cassette` 行；架构约束表补充说明（见下）。
- `docs-stm/managements/testplan.md`：§4 回归清单登记 cassette 回放套件；说明其不属 live 套件、入门禁。
- `docs-stm/manuals/faq.md`（或 `developer-guide.md`）：开发者视角「如何录制/刷新 cassette」指引。

## 关键复用点（勿新造）

- `core/http_client.make_http_client` — 全项目 HTTP 唯一构造点（架构约束：HTTP 客户端统一），注入点选在此处，provider 零改动。
- `src/test/live/` 与 `--run-live` 既有 opt-in 机制 — 录制复用其网络放行语义，不新造「允许联网」开关。
- conftest `_block_external_network` — 回放与它天然协同：回放在 socket 之前拦截，网络阻断仍是兜底防线。
- `features.json` 写入的原子习语（`tempfile.mkstemp` + `os.replace`）— cassette 写盘沿用（架构约束：原子写入）。
- `scripts/test-runner.py` 的 live 模式 — 录制经 `--mode live` 运行，不新增模式。

## 架构约束自检（技术设计文档「架构设计约束」逐条对照）

| 约束 | 是否受影响 | 说明 |
|:--|:--|:--|
| 原子写入 | 是（正向遵从） | cassette 写盘用 mkstemp + os.replace |
| HTTP 客户端统一 | 是（正向遵从） | 传输注入点设在唯一构造点，未新增 HTTP 路径 |
| Provider Chain 必经 | 否 | 回放不改变获取路径，只在传输层替换响应来源 |
| 日志统一 | 是 | 引擎日志用 `logging.getLogger("invest")`，前缀 `[cassette]` |
| 测试标记强制 | 是 | 新增 `cassette` marker 并注册进 conftest；所有新用例带标记 |
| edge 文件隔离 | 是 | 边界用例置 `test_cassette_edge.py` 并用 `edge` 标记 |
| 敏感路径隔离 | 是 | 录制目标目录与回放读取路径在 conftest 中可重定向到 tmp（防测试污染仓库内 cassette；仅在显式录制时写仓库路径） |
| 路径绝对化 | 是 | cassette 目录以 `PROJECT_ROOT` 绝对路径解析 |
| 其余各条 | 否 | 不涉及类型判定/缓存/LLM/渲染 |

## 测试计划

见 §4。核心断言原则：**回放用例断言真实响应体的解析结果值**（这是本计划相对既有假响应测试的全部增量价值），而不仅是「不抛异常」。

## 技术债规避（明确不做的事）

- **不引第三方依赖**（vcrpy/responses/httpretty）——自研引擎约 200 行且完全可控；避免为测试基建增加供应链与版本维护面。
- **不做「录制即自动写库」**——录制必须显式双开关，防止 CI/日常运行意外改写仓库夹具或静默联网。
- **不让回放静默回落网络**——未命中即失败，避免「假离线」的隐性网络依赖。
- **不设无实际分支的功能开关**——见「为何不设开关」。
- **不把 cassette 引入运行时路径**——引擎虽在 `core/`（供 CLI 维护命令复用），但运行时管线不读取 cassette，测试数据不成为运行时依赖。

## 验证

1. 引擎单测：`.venv/bin/python -m pytest src/test/unit/core/test_cassette.py src/test/unit/core/test_cassette_edge.py -v --tb=short`
2. 回放回归：`.venv/bin/python -m pytest src/test/unit/providers/test_cassette_replay.py -v --tb=short`（断网环境应全过）
3. 维护命令：`.venv/bin/python -m src.python.cli cassettes --verify`（退出码 0）
4. 录制（可选，需网络）：`.venv/bin/python scripts/test-runner.py --mode live --record-cassettes`（或 `-m live --run-live --record-cassettes`），确认 cassette 文件被刷新且 `cassettes --verify` 仍通过。
5. 格式：`.venv/bin/ruff format --check`。
6. P0 提交门禁：`test-runner.py --mode dev-verify` + `check-code-traces.py --ci` + `check-doc-traces.py --ci` + `check-task-numbering.py --ci` + `check-semantic-index.py --ci`。
