# 数据源适配契约实施设计（借鉴 OpenBB Fetcher 三段式 TET + 标准字段 schema + alias 声明式归一）

> 来源：[`openbb-data-provider-analysis.md`](openbb-data-provider-analysis.md) §建议A/B（OpenBB Platform 数据层工程借鉴评估，2026-09-09）。
> 级别：**P4 实验级**（缺省关闭、需显式启用），开关 `datasource_adapter`。
> 状态：**已实现**（行情域三源试点，存量 provider 不回改）。

## Context

当前每个数据源的「上游原始响应 → 本项目统一字段」映射是**手写转换函数**：`fetcher/price.py` 为腾讯/新浪/东方财富各写了一个 `_price_transform_*`，历史 K 线、基金排名/持仓、行业分类各自再写一套。新增一个数据源时，作者必须：

1. 读一遍别的源的转换函数，推断「本项目统一字段」到底是哪几个（字段集从未被写成契约）；
2. 手写一个 `dict` 字面量，逐键 `raw.get(...)` + 默认值（字段改名处如东方财富 `nav → price`、`yesterday_nav → yesterday_close` 全靠人眼比对）；
3. 忘一个键不会有任何报错——下游拿到 `None` 或 `KeyError` 才发现。

OpenBB Platform 的 Fetcher 把这件事拆成 **transform_query（参数转译）→ extract_data（抓取）→ transform_data（按标准模型映射）** 三段，并以 `Data` 模型作为字段契约、以 alias 声明完成改名。本项目借鉴其**契约分层与声明式归一**，不搬其 Provider 注册元架构/覆盖矩阵/命令路由。

预期结果：新增数据源时只需实现三个小函数 + 一张 alias 表；标准字段集是**可执行**的（`QuoteFields` 数据类），字段写错在契约自检与单元测试期即报错，而不是运行期静默丢字段。

## 语义命名（先定语义名再设计）

| 语义 slug | 中文名（文档/UI） | 归入章节 | 决策链环节 | config 开关 |
|:--|:--|:--|:--|:--|
| `datasource_adapter` | 数据源适配契约 | 数据源可用性矩阵 | 监控 | `datasource_adapter`（实验，默认关） |

代码标识符：模块 `fetcher/source_adapter.py`（契约与注册表）、`fetcher/quote_adapters.py`（行情域适配器）、`schemas/datasource_fields.py`（标准字段记录）；类 `SourceAdapter`/`QuoteFields`；函数 `register_adapter`/`get_adapters`/`adapter_chain_slots`/`survey_adapters`。

## 变更范围

### 1. 标准字段契约 — 新增 `src/python/schemas/datasource_fields.py`

- `@dataclass(frozen=True) class QuoteFields`：行情域标准字段，**字段集与既有统一 dict 逐键一致**（`name/code/price/yesterday_close/price_date/source_api/source/market_cap/pe`），可空字段显式 `| None`，`to_dict()` 输出与既有转换函数**同键同值**。
- `QUOTE_STANDARD_FIELDS: tuple[str, ...]`：标准字段名有序元组（契约自检与 alias 校验的比对基准）。
- 文件风格与 `schemas/history.py` 一致（frozen dataclass + 全字段类型注解 + `# ═══` 节分隔）。

### 2. 三段式契约与注册表 — 新增 `src/python/fetcher/source_adapter.py`

- `class SourceAdapter`（抽象基类）声明类属性 `domain`/`source_id`/`display_name`/`record_cls`/`aliases`，并定义三段式：
  - `transform_query(params) -> dict`：参数转译（补默认值、拼查询参数），默认恒等；
  - `extract_data(query) -> Any`（抽象）：抓取上游原始响应——**既有源在此委托给既有 provider 函数，不复制解析逻辑**；
  - `transform_data(raw, source) -> dict | None`：上游原始响应 → 标准字段 dict；默认实现即 **alias 声明式归一**（`aliases` 改名 + `core.num_utils.safe_num` 数值归一 + 缺键取默认 + 记录类字段过滤），换算类源（如净值即价格）覆写之。
- 链路两槽适配：`fetch_raw(**kwargs)`（= `extract_data(transform_query(kwargs))`）与 `transform_record(raw, source)`（= `transform_data`），使适配器可直接充当 `fetch_with_fallback` 的 `provider_fn_map` 与 `transform` 槽（**签名与既有 `_ProviderFunc` / `transform(raw, source_label)` 一致**）。
- 注册表：`ADAPTER_REGISTRY: dict[str, dict[str, SourceAdapter]]`（域 → 源 id → 适配器）+ `register_adapter()` / `get_adapters(domain)` / `adapter_chain_slots(domain) -> tuple[provider_fn_map, transform_map]`。
- `survey_adapters() -> list[dict]`：**离线**契约自检报告（每次调用即时计算，不落盘、不联网、自身不抛异常），每项含 `domain/source_id/display_name/ok/message`。自检项：类属性齐备、alias 目标字段存在于 `record_cls`、标准字段名与 `record_cls` 字段集一致、`transform_data` 对合成样本输出键集 ⊆ 标准字段集。

### 3. 行情域试点 — 新增 `src/python/fetcher/quote_adapters.py`

- `TencentQuoteAdapter`/`SinaQuoteAdapter`/`EastMoneyQuoteAdapter` 三个适配器，`extract_data` 委托 `providers.tencent.fetch_price` / `providers.sina.fetch_price` / `providers.eastmoney.fetch_nav`（**provider 层零改动**）。
- 东方财富适配器承载真实改名：`aliases = {"nav": "price", "yesterday_nav": "yesterday_close", "nav_date": "price_date"}` + `nav <= 0 → None` 的换算守卫，与既有 `_price_transform_eastmoney` 等价。
- 模块导入时注册到 `quote` 域。

### 4. 试点接入 — `src/python/fetcher/price.py`

- `_fetch_price_with_cache_refresh()` 增加 `providers`/`transforms` 参数（缺省取 `_PRICE_PROVIDERS`/`_PRICE_TRANSFORMS`）；`fetch_market_data()` 按开关取槽：
  ```python
  if is_feature_enabled("datasource_adapter"):
      providers, transforms = adapter_chain_slots("quote")
  else:
      providers, transforms = _PRICE_PROVIDERS, _PRICE_TRANSFORMS
  ```
- **开关关闭时取槽结果与被替换对象在构造上完全相同**（同一 dict 内容），行为逐字节不变；开关开启时链路顺序、缓存键、TTL、`validate`、熔断、降级路径全部不变——只换「原始响应 → 统一格式」的实现方式。既有手写转换函数**保留**（作为等价性基准与开关关闭路径），本计划结束时不删除（留待试点结论后再定，见「技术债规避」）。
- 既有 `_price_transform_*` 与适配器 `transform_record` 的一致性由**等价性回归测试**锁定（见测试计划）。

### 5. 自检上屏 — `src/python/core/doctor.py`

- 新增检查组 `GROUP_ADAPTER = "数据源适配"`（加入 `GROUP_ORDER`）与检查函数：调用 `survey_adapters()`，报告「已声明适配器 N 个（域：quote），契约自检通过」或列出问题项；并标注当前开关状态（未启用时描述为「契约路径未启用（实验开关关闭），适配器声明与自检仍可核验」）。
- doctor 自身沿用 plan-35 既有纪律：零重依赖、**离线**（自检不联网）、自身永不抛异常。**不新增任何 TUI/Web/CLI 界面** —— doctor 已三面上屏（TUI `[D]`、Web 运行状态区、CLI `doctor`），适配契约自检随之可见。

### 6. 实验开关注册 — `src/python/config/features.py`

- `_FEATURE_FLAGS_DEFAULT` 与 `EXPERIMENTAL_FEATURES` 各追加一项（**追加至注册表末尾**，不改动既有条目顺序）：
  - 显示名「数据源适配契约」，说明「三段式（参数转译→抓取→映射）适配器 + 声明式 alias 归一，行情域试点；关闭时走既有转换函数」。
- 上屏为**注册表驱动自动生效**，无需改任何入口代码：TUI 菜单 `[S]` 实验块、Web 配置面板「实验性功能」组、CLI `--experiment datasource_adapter`。

## 关键复用点（勿新造）

- `fetcher/chain.py::fetch_with_fallback` — 链路/缓存/熔断/降级/诊断全部复用，**不新造第二条获取路径**（架构约束：Provider Chain 必经）。
- `providers/*` 既有抓取函数 — 适配器只做映射，`extract_data` 直接委托，不复制任何 HTTP 与解析逻辑（架构约束：HTTP 客户端统一）。
- `core/num_utils.safe_num` — 数值归一唯一实现（plan-35 已收敛），适配器默认映射直接调用。
- `core/doctor.py::_item` / `GROUP_ORDER` — 自检上屏复用既有体检面，不新增界面。
- `config/features.py::EXPERIMENTAL_FEATURES` — 开关三面上屏的唯一注册表，**零入口代码改动**。
- `schemas/*` 既有 dataclass 风格 — 标准字段记录沿用，不引入 pydantic 等新依赖。

## 架构约束自检（技术设计文档「架构设计约束」逐条对照）

| 约束（语义名） | 是否受影响 | 说明 |
|:--|:--|:--|
| 代码类型判定中心化 | 否 | 适配器不做类型判定；路由仍走 `_route_price_request` → `core/code_utils` |
| HTTP 客户端统一 | 否 | 适配器不新建 HTTP 会话，`extract_data` 委托 provider，provider 内部 `make_http_client` |
| Provider Chain 必经 | **是（正向遵从）** | 试点路径仍在 `fetch_with_fallback` 内，未新增旁路获取 |
| 日志统一 | 是 | 新增日志一律 `logging.getLogger("invest")`，前缀 `[adapter]` |
| 测试标记强制 / edge 文件隔离 | 是 | 新增测试全部带 `unit` + `unit_fetcher` 标记；边界用例置 `*_edge.py` 并带 `edge` 标记 |
| 敏感路径隔离 | 否 | 无新增持久化状态文件；`survey_adapters` 为纯计算 |
| pipeline_data 数据契约 | 否 | 标准字段 dict 与既有统一 dict 同键同值，下游数据结构不变 |
| LLM 缓存指纹同源 | 否 | 不涉及 LLM |
| 其余各条 | 否 | 不新增缓存/写入/渲染/路径逻辑 |

## 测试计划

- `src/test/unit/fetcher/test_source_adapter.py`（`unit` + `unit_fetcher`，mock LLM 不涉及、不碰网络）：
  - `survey_adapters()` 对已注册适配器全部通过；
  - **别名合法性与僵尸字段防御**：注入一个 alias 指向不存在标准字段的临时适配器 → 自检检出（防「改名写错」静默丢字段）；
  - `transform_query` 默认恒等、`fetch_raw` 串接两段（用桩 `extract_data` 断言收到转译后的 query）；
  - 未知域取槽返回空映射（不抛异常）。
- `src/test/unit/fetcher/test_quote_adapter_parity.py`（`unit` + `unit_fetcher`）：
  - **逐源等价性**：对腾讯/新浪/东方财富的代表性原始响应，断言 `adapter.transform_record(raw, source) == _price_transform_*(raw, source)`（东方财富含 `nav<=0 → None` 守卫分支）；
  - **端到端等价性**：monkeypatch 三个 provider 函数返回固定响应，分别在开关开/关下调用 `fetch_market_data`（缓存重定向到 tmp，见 conftest），断言两次返回**完全相等**；
  - 标准字段键集与 `QuoteFields` 字段集一致（防新增标准字段时漏同步）。
- 边界用例（`src/test/unit/fetcher/test_source_adapter_edge.py`，`unit` + `unit_fetcher` + `edge`）：空响应/全 `None` 字段/上游多出未知键 → 归一出标准键集且不抛异常。

> 说明：本计划的登记开关为 `datasource_adapter`。按仓库测试隔离纪律，涉及管线的测试一律重定向缓存/输出目录、不读真实持仓、不发起真实网络（conftest `_block_external_network` 兜底）。

## 技术债规避（明确不做的事）

- **不改 provider 层任何代码**——适配器委托既有抓取函数，避免「同一解析逻辑两份实现」的复制式技术债。
- **不删除既有 `_price_transform_*`**——它们是等价性基准，且开关关闭路径必须逐字节不变；删除与否留待试点结论。
- **不引入 pydantic/OpenBB 依赖**——标准字段用标准库 dataclass 表达。
- **不搬 OpenBB 的 Provider 注册元架构/覆盖矩阵/命令路由**——本项目已有 `provider_registry` + `chain`，再造一套即重复。
- **只试点行情域**——单一域打通契约即验证了机制；其余域在真正新增源/加字段时按契约接入，不做投机性改造（YAGNI）。

## 验证

1. 单元：`.venv/bin/python -m pytest src/test/unit/fetcher/ -v --tb=short`
2. 等价性抽查：`.venv/bin/python -c` 手动脚本比对开关开/关下同一标的的行情 dict（离线固定响应）。
3. 自检可见：`.venv/bin/python -m src.python.cli doctor`（含「数据源适配」组）。
4. 三面开关核对：TUI 菜单 `[S]` 实验块末项、「Web 配置面板 → 实验性功能」组、`--experiment datasource_adapter`（`--help` 列出）。
5. 格式：`.venv/bin/ruff format --check`。
6. P0 提交门禁：`test-runner.py --mode dev-verify` + `check-code-traces.py --ci` + `check-doc-traces.py --ci` + `check-task-numbering.py --ci` + `check-semantic-index.py --ci`。
