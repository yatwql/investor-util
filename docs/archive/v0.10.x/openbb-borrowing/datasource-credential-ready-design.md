# 数据源凭据声明与就绪指引实施设计（借鉴 OpenBB `Provider(credentials=[...])`）

> 来源：[`openbb-data-provider-analysis.md`](openbb-data-provider-analysis.md) §建议D（OpenBB Platform 数据层工程借鉴评估，2026-09-09）。
> 级别：**P4 实验级**（缺省关闭、需显式启用），开关 `datasource_credential_ready`。
> 状态：**已实现**（当前生产注册表为空表——全部数据源免费无需凭据是事实；机制由注入合成声明的单元测试证明）。

## Context

本项目当前的数据源**全部免费、无需凭据**（腾讯/新浪/东方财富/天天基金/华尔街见闻/财联社）。但 LLM 侧已经暴露过同一个问题模式：缺 key 时若在调用点裸报错，用户看到的是传输层异常而非「你缺什么、去哪申请」——plan-35 之前的 `doctor._check_llm_credentials` 就是为此而写。

OpenBB 的做法是把「此源需什么凭据」**声明在 Provider 定义里**（`Provider(credentials=[...])`），缺失时给出 `Missing credential ... Check <website>` 这类可读指引，而不是等运行期 HTTP 401。

本计划把这套「**声明 → 就绪判定 → 可读指引**」机制补到数据源侧，使将来接入任何需 key 的源时：链路能**主动跳过**该源并给出指引（而非把它当作「不可达」反复重试、甚至计入熔断），体检与健康检查能直接报告就绪状态。

**现状如实呈现**：由于当前无源需要凭据，开关开启后的可观察行为就是就绪矩阵报告「N 个数据源均无需凭据（免费源）」。机制本身通过**注入合成凭据声明**的单元测试证明可用——不为了演示而编造一个假数据源进仓库。

## 语义命名（先定语义名再设计）

| 语义 slug | 中文名（文档/UI） | 归入章节 | 决策链环节 | config 开关 |
|:--|:--|:--|:--|:--|
| `datasource_credential_ready` | 数据源凭据就绪指引 | 数据源可用性矩阵 | 监控 | `datasource_credential_ready`（实验，默认关） |

代码标识符：模块 `core/datasource_credential.py`；类 `CredentialSpec`；函数 `register_credential_spec`/`missing_credential`/`credential_hint`/`credential_readiness`。

## 变更范围

### 1. 凭据声明与就绪判定 — 新增 `src/python/core/datasource_credential.py`

- `@dataclass(frozen=True) class CredentialSpec`：`source_id`（与 `provider_registry`/`chain` 的 provider 名一致）、`display_name`、`env_var`（环境变量名）、`apply_url`（申请地址，可空）、`note`（可空备注）。
- `CREDENTIAL_SPECS: dict[str, CredentialSpec] = {}` —— **声明即数据，当前为空**（全部免费源）；`register_credential_spec(spec)` 供接入需 key 的源时登记（模块导入即注册，与 `ADAPTER_REGISTRY` 同习语）。
- `missing_credential(source_id) -> CredentialSpec | None`：该源是否「已声明需凭据但当前缺失」。判定读环境变量，**空白串视为缺失**；源未声明 → `None`（即不需凭据）。
- `credential_hint(spec) -> str`：可读缺失指引，措辞对齐 `doctor._check_llm_credentials` 既有风格，例如
  `缺少凭据（数据源：XX财经）——请设置环境变量 XX_API_KEY；申请地址：https://...`。
- `credential_readiness() -> list[dict]`：就绪矩阵，每项 `{source_id, display_name, required, ready, env_var, message}`。**自身不抛异常**（供体检复用）。
- **凭据值永不落日志、永不写入报告**——只报告「变量名 + 是否就绪」。

### 2. 链路预检跳过 — `src/python/fetcher/chain.py`

- 在 `fetch_with_fallback` 的 provider 循环内、熔断检查之后，插入凭据就绪预检（**受开关约束**）：
  ```python
  spec = missing_credential(provider_name)
  if spec is not None:
      logger.info("[%s]%s %s 缺少凭据，跳过（%s）", data_type, _code_tag, label, spec.env_var)
      if diagnostics is not None:
          diagnostics.add(label, credential_hint(spec))   # 进「错误即 UX」的可读原因
      continue
  ```
- 语义与既有「已被熔断跳过」「未知 Provider」两处 `continue` 完全同例：**不计入熔断计数器**（这是配置级问题，不是源不可达），仅以可读原因进入 `FailureDiagnostics`，随降级事件上屏到「数据源可用性矩阵」。
- 开关关闭 / 无声明凭据 → 该分支恒不触发，行为与现状逐字一致。

### 3. 健康检查跳过与就绪行 — `src/python/core/check_sources.py`

- `_checks` 项由 `(显示名, 用途, 探测函数)` 扩展为带 `source_id` 的四元组（声明式数据，便于把探测项与 provider 名对齐）。
- 探测前凭据预检（受开关约束）：缺失则**不发起探测**，直接产出跳过项（对称使用文件中**已定义但至今未使用**的 `_SKIP` 符号 `⏭️`），消息为 `credential_hint(...)`；跳过项计入 `skipped` 计数，**不使退出码变为失败**（`err`/`warn` 判定不含跳过）。
- 开关开启时，输出末尾追加一行就绪摘要（如 `凭据就绪：10 个数据源均无需凭据`）。

### 4. 体检项 — `src/python/core/doctor.py`

- 新增检查组 `GROUP_CREDENTIAL = "数据源凭据"`（加入 `GROUP_ORDER`）与检查函数（受开关约束）：调用 `credential_readiness()`——全部就绪 → OK，消息为「N 个数据源均无需凭据（免费源）」；存在缺失 → 失败项 + `hint`（可执行修复建议，复用 plan-35 的 `_item(..., hint=...)`）。
- 开关关闭 → 不产出该组（体检输出与现状一致）。

### 5. 实验开关注册 — `src/python/config/features.py`

- `_FEATURE_FLAGS_DEFAULT` 与 `EXPERIMENTAL_FEATURES` 各追加一项（**追加至注册表末尾**）：
  - 显示名「数据源凭据就绪」，说明「声明数据源所需凭据，缺失时链路跳过并给出可读指引；体检与健康检查报告就绪状态（当前全部数据源免费无需凭据）」。
- 三面上屏为注册表驱动**自动生效**：TUI 菜单 `[S]` 实验块、Web 配置面板「实验性功能」组、CLI `--experiment datasource_credential_ready`。

## 关键复用点（勿新造）

- `core/doctor.py` 既有 `_item(..., hint=...)` 与 `GROUP_ORDER` — 体检上屏复用，不新增界面。
- `core/doctor.py::_check_llm_credentials` 的**可读缺失指引措辞与判定习语** — 数据源侧对齐同一风格，不另创一套文案范式。
- `check_sources.py` 既有 `_SKIP` 符号与结果结构（`name/label/ok/latency_ms/message`）— 只增 `skipped` 标记与 `source_id`，Web `/api/health` 与 TUI 消费方结构不变。
- `fetcher/chain.py::FailureDiagnostics` — 缺失凭据以可读原因复用既有「错误即 UX」通道上屏，不新增上报机制。
- `config/features.py::EXPERIMENTAL_FEATURES` — 开关三面上屏唯一注册表，零入口代码改动。

## 架构约束自检（技术设计文档「架构设计约束」逐条对照）

| 约束 | 是否受影响 | 说明 |
|:--|:--|:--|
| HTTP 客户端统一 | 否 | 预检在 HTTP 之前，不新建客户端 |
| Provider Chain 必经 | **是（正向遵从）** | 跳过发生在 chain 循环内部，未新增旁路 |
| 日志统一 | 是 | 日志 `logging.getLogger("invest")`，前缀 `[credential]`；**只记变量名不记值** |
| 测试标记强制与 edge 文件隔离 | 是 | 新增测试带标记；边界（空串/未声明/多源混合）置 `*_edge.py` |
| 敏感路径隔离 | 否 | 无新增持久化状态文件 |
| 安全（密钥管理） | 是（正向遵从） | 凭据只从环境变量读，绝不硬编码、绝不写入报告/日志/缓存 |
| 其余各条 | 否 | 不涉及类型判定/缓存/LLM/渲染/指纹 |

## 测试计划

- `src/test/unit/core/test_datasource_credential.py`（`unit` + `unit_core`，`monkeypatch.setenv` 隔离环境变量）：
  - 未声明源 → `missing_credential` 返回 `None`（不需凭据）；空串环境变量 → **视为缺失**（防「设了空值以为配好了」）；
  - `credential_hint` 含显示名、变量名、申请地址；
  - `credential_readiness()` 对当前实现返回全就绪，且**不抛异常**（空注册表、未知源、异常环境变量均覆盖）。
- `src/test/unit/core/test_datasource_credential_edge.py`（`unit` + `unit_core` + `edge`）：注册表为空 / 声明缺 `env_var` / 环境变量含空白 / 同一源重复注册。
- `src/test/unit/fetcher/test_credential_gate.py`（`unit` + `unit_fetcher`）：
  - 注入合成 `CredentialSpec`（monkeypatch 注册 + 清空环境变量）+ 开关开启 → `fetch_with_fallback` **跳过该 provider、落到下一链路**、`FailureDiagnostics` 含可读指引、且**未计入熔断失败计数**（断言 `record_failure` 未被调用）；
  - 补上环境变量 → 该 provider 正常参与；
  - 开关关闭 → 预检不发生（行为与现状一致）。
- `src/test/unit/core/test_check_sources_credential.py`（`unit` + `unit_core`）：注入合成凭据声明 → 对应项产出跳过态（`_SKIP` 符号）、退出码判定不受影响；无声明时输出与现状逐字一致。
- `src/test/unit/web/test_health_credential.py`（`unit` + `unit_web`）：`/api/health` 结果结构中跳过项的 `skipped` 标记透传（不影响既有断言）。

## 技术债规避（明确不做的事）

- **不为演示编造假数据源**——注册表为空是事实；机制由合成声明注入的单元测试证明，不把假源写进生产注册表。
- **不预造「凭据交互式配置向导」**——无源需要凭据时该 UI 无法验证也无法使用（YAGNI）。
- **不改 `_checks` 的探测语义**——只加声明式 `source_id` 与预检跳过分支，探测函数与超时预算逻辑不动。
- **不新增界面**——开关三面由注册表自动上屏，效果复用 `check-sources`/`doctor`/`/api/health` 既有面。
- **不把凭据缺失计入熔断**——配置级问题混入可用性统计会污染数据源可用性矩阵的语义。

## 实施记录（落地时的取舍，2026-09-10）

设计定稿后实现期做了四处增补，均属「把机制补完整」而非扩大范围：

1. **预检同时覆盖历史走势链路**（设计原稿只写了 `fetch_with_fallback`）。`_try_providers` 是历史
   走势的 provider 遍历循环，同样「能取数」；只堵主链路等于机制半应用——缺凭据的源仍会在历史
   链路里被反复调用并计入熔断。现两处同判定，测试 `TestHistoryChainCredentialGate` 锁定。
2. **`_checks` 的 `source_id` 用 `_news` 后缀消歧**（`sina_news` / `eastmoney_news`）。探测项里
   存在「同一家的行情源与新闻源」以及「东方财富（净值）与东方财富新闻」，显示名相近而 provider
   名不同；若按显示名或去掉后缀的短名对齐，凭据声明会挂到错误的源上。
3. **`doctor._check_network` 过滤 `skipped` 行**。凭据未探测的源由新增的「数据源凭据」组专门
   报告；若网络组照旧把它们渲染成 `[ERR]`，同一个配置问题会在体检里被计成两次失败，且误导用户
   去查连通性。
4. **测试文件比原计划多一个**：`test_doctor_credential.py`（原测试计划只列了 5 个文件，体检组被
   并入 `test_doctor.py` 的隐含预期）。体检组是本次唯一新增界面，独立成文件更便于定位失败。

**CLI 实测**（v0.10.17-dev）：`--experiment datasource_credential_ready check-sources` 末尾出现
`凭据就绪：10 个数据源均无需凭据（免费源）` 且退出码 0；`doctor` 出现 `[数据源凭据]` 组并报
`[OK] 凭据就绪 — 全部数据源均无需凭据（免费源）`；两条命令在去掉 `--experiment` 后分别不再输出
就绪行与凭据组——开关关闭时行为与未引入本机制时一致。

## 验证

1. 单元：`.venv/bin/python -m pytest src/test/unit/core/test_datasource_credential.py src/test/unit/core/test_datasource_credential_edge.py src/test/unit/fetcher/test_credential_gate.py -v --tb=short`
2. 就绪可见（开关开启）：`.venv/bin/python -m src.python.cli --experiment datasource_credential_ready check-sources`（末尾就绪摘要，退出码 0）与 `.venv/bin/python -m src.python.cli doctor`（含「数据源凭据」组）。
3. 开关关闭对照：同两条命令输出与现状一致（无就绪行、无凭据组）。
4. 三面开关核对：TUI 菜单 `[S]` 实验块末项、「Web 配置面板 → 实验性功能」组、`--experiment datasource_credential_ready`（`--help` 列出）。
5. 格式：`.venv/bin/ruff format --check`。
6. P0 提交门禁：`test-runner.py --mode dev-verify` + `check-code-traces.py --ci` + `check-doc-traces.py --ci` + `check-task-numbering.py --ci` + `check-semantic-index.py --ci`。
