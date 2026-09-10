# 健壮性三件套实现设计（plan-35）

> 文档版本：0.10.16-dev
> 来源：augur 借鉴评估 §建议 C（`augur-borrowing-analysis.md`，2026-09-09）
> 语义名：`robustness_suite`（数值归一防线 / 失败原因可读 / 系统自检）
> 状态：**已实现**（数值归一防线与失败原因可读为默认路径生效的真缺陷修复；`doctor_check` 系统自检为默认关闭的 P4 实验特性）
> 依赖：无（纯增量，不依赖前序实验开关）

---

## 0. 范围与 A/B 划分

本项由三件互相独立、均属「补齐既有能力短板」的增量组成。按本项目「A = 真缺陷修复（确定性，无开关）／B = 实验增强（开关门控，默认关）」纪律划分如下：

| 编号 | 内容 | 归类 | 开关 | 依据 |
|:----:|:-----|:----:|:-----|:-----|
| A1 | 数值归一全链路防线（防 NaN/±inf 污染下游） | **A 缺陷修复** | 无 | 已确认存在 `nan or 0.0` 空防线、provider 解析器泄漏 NaN/±inf 进入市值/收益/绘图链 |
| A2 | 数据源失败原因可读（「错误即 UX」） | **A 缺陷修复** | 无 | 失败原因在 `_try_provider_fetch` 内被丢弃，用户可见面只剩 `price_sh600519: unreachable` 机器串 |
| B1 | 系统自检命令（doctor） | **B 实验增强** | `doctor_check` | 新增用户可见入口（CLI 子命令 + TUI 菜单 + Web 卡片），实验期默认关、零行为变更 |

> **为什么 A1/A2 不设开关**：两者修的都是可复现的既有缺陷（NaN 传播、错误信息丢失），开关门控会让「关闭时缺陷仍在」成为可选项，违背 A/B 纪律中「A 无开关」的定义。参照 plan-34 的 `_safe_number` 先例——数值防线本就不该是可关的。

---

## 1. 语义命名（先定名，再实现）

| 语义名 | 落点 | 含义 |
|:-------|:-----|:-----|
| `safe_num` | `core/num_utils.py` | 把任意脏值归一为**有限** float；脏值返回 `default`（默认 `None`） |
| `finite_or` | `core/num_utils.py` | `safe_num(value, default=fallback)` 的语义化糖，专治 `x or 0.0` 空防线惯用法 |
| `is_finite_number` | `core/num_utils.py` | 判定「是真数值且有限」（排除 bool/None/字符串/NaN/±inf） |
| `FailureDiagnostics` | `fetcher/chain.py` | 单次链路调用的失败原因收集器（provider 名 + 可读原因） |
| `record(message=...)` | `report/data_status.py` | 降级事件的可读原因槽位 |
| `run_doctor_checks` | `core/doctor.py` | 一次性自检：路径/密钥/缓存/状态文件/连通性 |
| `doctor_check` | `config/features.py` | B1 实验开关名（显示名「系统自检」） |

禁用任务代号入代码（`plan-35`/Augur 系列代号仅存于本文与管理文档）。

---

## 2. A1 — 数值归一全链路防线

### 2.1 问题（已实测确认）

现状是**约 10 个互不一致的私有解析器 + 4 种失败口径**：

| 口径 | 代表实现 | 对 NaN/±inf 的行为 |
|:-----|:---------|:-------------------|
| `None`-on-dirty | `core/signal_ledger.py::_safe_number`、`providers/akshare_extras.py::_safe_float` | NaN/±inf → `None`（**唯一严格的**） |
| `0.0`-on-dirty | `providers/_utils.py::safe_float`、`tencent.py::_parse_float` | **NaN/±inf 原样泄漏**（`float("nan")` 不抛异常） |
| 静默钳制 | `tencent.py::_parse_float` 对负值 | 负值 → `0.0` |
| 带守卫直通 | `analysis/metrics_returns.py::sanitize_metric` | 拦 NaN/±inf，但**不拦 bool、不解析字符串** |

而 `providers/_utils.safe_float` 是**最广被依赖**的一个（`eastmoney.py`、`tiantian_base.py`／`tiantian_nav.py`／`tiantian_ranking.py` 均经它），恰恰是 NaN/±inf 防线最弱的一个：NaN 净值可一路流到 `report/market_value.py:441`。

### 2.2 两个确凿缺陷

**(a) `or 0.0` 惯用法对 NaN 完全无效。** `float('nan')` 是 **truthy**，故 `nan or 0.0` 求值为 `nan`——这行代码看起来在兜底，实际什么都没拦。已确认命中（非穷举）：

- `report/market_value.py:441,442` — `price = mkt.get("price", 0.0) or 0.0`，NaN 直入 `mv`/`profit`/`profit_rate`/`today_profit` 全链
- `report/category.py:76-78`、`report/market_value_sheet.py:81,82`、`report/chart_data_builder.py:290,338,366`
- `report/decision_record.py:56`、`report/decision_llm_capture.py:140`
- `analysis/whatif.py:59,65,66`、`analysis/portfolio_evolution.py`（14 处）、`analysis/snapshot_diff.py:136,153,154`
- `core/data_freshness.py:162,163,238,243`、`core/reader.py:295`
- `report/html_writer_display.py:40`

**(b) provider 解析器泄漏 NaN/±inf。** `providers/_utils.safe_float`、`tencent._parse_float_field`、`sina_kline._parse_sina_kline_float`、`eastmoney_industry._extract_number` 在脏值路径上返回 NaN/±inf 而非兜底值。K 线泄漏（`sina_kline.py:178`、`tencent.py:365`）尤其危险——它直接进入 `analysis/` 全部收益序列指标。

### 2.3 实现

**新增 `src/python/core/num_utils.py`（零项目内依赖，纯 stdlib）**

```python
def safe_num(value: Any, *, default=None) -> float | int | None:
    """宽容归一：数值字符串先尝试解析，再施加有限性检查；其余返回 default。"""

def strict_num(value: Any, *, default=None) -> float | int | None:
    """严格归一：仅接受 int/float（排除 bool）且有限；字符串一律非数值。"""

def finite_or(value: Any, fallback: float = 0.0) -> float:
    """`x or fallback` 的 NaN 安全替代（NaN 为真值，`or` 拦不住）。"""

def is_finite_number(value: Any) -> bool:
    """是否为有限真数值（排除 bool/None/字符串/NaN/±inf）。"""
```

**为什么是两个归一入口**：两层既有口径本就不同，强行合一反而出错。

- provider 解析器（`_parse_float` 等）面对的是**网页/JSON 字符串字段**，必须解析文本 → 用 `safe_num`。
- `signal_ledger._safe_number` 面对的是**待落盘的账本值**，字符串混入会破坏类型契约 → 用 `strict_num`（即其现有语义原样提取，行为逐字不变）。

`int` 均原样返回（不转 float），避免整数份额/ID 被改写；`bool` 均显式排除（它是 `int` 子类，混入会让 `True` 静默变 `1`）。

**落点（三处收敛，一次到位）**

1. **新建原语**：`core/num_utils.py`（上述三函数）。`safe_num` 保留 `int` 原样返回（不强行转 float），避免整数 ID/份额被改写。
2. **收敛既有私有实现**（行为对**合法输入逐字不变**，仅脏值路径改变）：
   - `core/signal_ledger.py::_safe_number` → 委托 `safe_num`（保持 `None`-on-dirty）
   - `providers/_utils.py::safe_float` → 委托 `safe_num(default=0.0)`（保持 `0.0`-on-dirty，**堵住 NaN/±inf**）
   - `providers/akshare_extras.py::_safe_float` → 委托 `safe_num()`（保持 `None`-on-dirty）
   - `providers/tencent.py::_parse_float` / `_parse_float_field`、`providers/sina_kline.py::_parse_sina_kline_float`、`providers/eastmoney_industry.py::_extract_number` → 委托 `safe_num(default=0.0/None)`（各自保持既有默认值口径）
   - `core/reader.py::_safe_float` → 追加有限性检查：Excel 返回 NaN（`=NA()`/公式错误）时按「非法值」告警并返回 `None`（当前返回 NaN，使 `shares <= 0` 校验对 NaN 恒为 False 而放行脏行）
3. **消除 `or 0.0` 空防线**：上述 §2.2(a) 清单中的真 bug 站点改用 `finite_or(...)`。
   - 判定标准：**值可能来自外部数据**才改；纯 CLI 参数/时间戳等可证明非浮点的站点（如 `web/runs.py:214`）保持原样，避免无意义改动。

**明确不做**：不统一各层的 dirty 默认值语义（`None` vs `0.0`）。调用方各自的口径是既有契约，强行统一会波及数十处消费方，属超范围重构。本次只保证「**有限性**」这一条不变量。

---

## 3. A2 — 数据源失败原因可读（「错误即 UX」）

### 3.1 问题（已实测确认）

失败原因在源码层就被丢弃，链路如下：

```
_try_provider_fetch()          # chain.py:112-118 捕获 str(e) → 只 log 一行 → return TRANSPORT_FAILURE
  ↓  异常文本已丢失
fetch_with_fallback()          # chain.py:220 全链失败 return None（无原因槽位）
  ↓
调用方 fund.py / price.py / industry.py
  ↓  只能写通用失败类型
DegradationTracker.record(failure_type="unreachable")   # data_status.py:249 无 message 参数
  ↓
data_source_matrix.py:91,94    # f"{src_key}: {failure_type}"
  ↓
HTML 模板「失败明细」          # 用户最终看到：price_sh600519: unreachable
```

三处断点：① `_try_provider_fetch` 拿到 `str(e)` 后丢弃；② 链路出口无原因槽位；③ 降级事件无原因槽位，矩阵只能拼机器串。此外 `registry.record_failure()` 收到的也一直是通用串 `f"{data_type}:transport"`，`last_failure_context` 因此形同虚设。

### 3.2 实现

**① 链路内保留原因**（`fetcher/chain.py`，私有）

- `_try_provider_fetch` 改为返回 `(result, reason)`：成功时 `reason=None`；失败时 `reason` 为可读短句（异常路径取 `f"{type(e).__name__}: {e}"` 截断、429 单列、空结果「返回空」、验证失败「数据校验未通过」、转换失败「数据转换失败」）。私有函数，改动不外泄。
- 新增 `FailureDiagnostics`（dataclass）：`attempts: list[tuple[str, str]]`（provider 名, 原因）+ `summary() -> str`（`"腾讯财经(连接超时)；新浪财经(返回空)"` 形态）+ `has_failure`。
- `fetch_with_fallback(...)` / `fetch_with_incremental_fallback(...)` 增加**可选**出参 `diagnostics: FailureDiagnostics | None = None`；传入则逐 provider 记录。**返回类型不变**（`dict|None` / `list`），故其余调用方零改动。
- 全链失败时，`reg.record_failure(provider_name, reason)` 改传**可读原因**（替代 `f"{data_type}:transport"`），使 `DataSourceRegistry.last_failure_context` 与 `generate_status_report()` 首次具备真实内容。

**② 降级事件带原因**（`report/data_status.py`）

- `DegradationEvent` 复用既有 `detail` 字典（当前仅聚合事件用）承载 `{"message": ...}`；`record()` 增加可选 `message: str | None = None`。
- 向后兼容：不传 `message` 时行为与 `detail=None` 完全一致（既有调用方与测试不受影响）。

**③ 上屏可读**（`report/data_source_matrix.py` + 模板）

- `sample_failures` / `degraded_list` 条目改为：有 `detail.message` 时用 `f"{src_key}: {message}"`，否则回落 `f"{src_key}: {failure_type}"`（保留既有键名与回落行为，无 message 时输出逐字不变）。
- HTML `report_template.html`「降级明细」「失败明细」两处无需改动即可受益（模板原样渲染上述字符串）。

**④ 调用方补齐**（`fetcher/fund.py`、`price.py`、`industry.py`）

5 个 `fetch_with_fallback` 调用点构造 `FailureDiagnostics`，失败分支把 `diagnostics.summary()` 交给 `record(..., message=...)`。历史链路（`fetch_with_incremental_fallback`）同样支持，但**只在调用方已显式传 `diagnostics` 时**才采集——不传则零开销。

---

## 4. B1 — 系统自检命令（实验开关 `doctor_check`）

### 4.1 定位

一次性盘点「为什么这次报告不对」，把当前分散在 `check-sources`（只测连通性）、菜单 `[4]`（只看缓存）、菜单 `[V]/[H]`（只看日志/健康历史）三处的诊断能力，合成**一个入口、一份可读结论**。

### 4.2 实现分层（严守既有架构分层）

**`src/python/core/doctor.py`（纯数据层，不做任何 IO 之外的渲染）**

```python
def run_doctor_checks(*, include_network: bool = True) -> list[dict]
# 返回 [{ "group": str, "name": str, "status": "ok"|"warn"|"fail",
#         "message": str, "hint": str | None }, ...]
```

检查项（分组）：

| 组 | 检查 |
|:---|:-----|
| 环境 | Python 版本、程序版本（`constants.APP_VERSION`）、关键依赖可导入性（pandas/openpyxl） |
| 路径 | 持仓目录 / 持仓文件 / 输出目录 存在性与**可写性** |
| 密钥 | `llm_key.json` 是否配置、当前 provider 是否与密钥匹配（**只报存在性，绝不回显密钥内容**） |
| 缓存 | `data/cache/` 文件数/大小/过期数；`data/state/` 状态文件数/大小 |
| 状态文件 | 各 JSONL 状态文件可读性（损坏/截断检测，复用 `core/jsonl_store.read_jsonl`） |
| 连通性 | 复用 `core/check_sources.run_health_checks()`（`include_network=False` 时跳过） |

**注意事项（防重蹈 augur 反例）**：连通性探测**不得**进入报告生成热路径——本模块只在用户显式调用 doctor 时执行，报告管线不引用它。

**三入口（由开关门控，注册表驱动）**

| 入口 | 形态 |
|:-----|:-----|
| CLI | 新增子命令 `doctor`（`--no-network` 跳过联网），并在 `--experiment` 校验通过且 `doctor_check` 启用时可用 |
| TUI | 主菜单诊断类新增 `[D] 系统自检`，开关关闭时不显示该项 |
| Web | 运行状态区（⑥）新增「系统自检」卡片；配置编辑面板（③）实验性功能组由注册表自动出现「⚗ 系统自检」开关 |

- 开关注册：`config/features.py::EXPERIMENTAL_FEATURES` 追加 `doctor_check` → TUI 菜单 `S` / Web 配置面板 / CLI `--experiment` **三处自动上屏**，无需改动任何入口代码（沿用既有注册表纪律）。
- CLI 参数：`--experiment doctor_check` 启用；未启用时 `doctor` 子命令提示「该命令为实验功能，请经 `--experiment doctor_check` 启用或在 TUI 菜单 S / Web 面板开启」。

---

## 5. 架构约束遵从

| 约束 | 遵从说明 |
|:-----|:---------|
| 分层依赖 | `core/num_utils.py` 零项目内依赖（纯 stdlib），可被 `providers/`/`analysis/`/`report/`/`fetcher/` 任一侧安全导入——这也是不放进 `analysis/_math_utils.py` 的原因（该模块是统计专用，且 `analysis` 已依赖 `core`，反向导入会成环） |
| 单一事实来源 | 数值归一只有 `core/num_utils.py` 一处实现；既有 8 个私有解析器改为委托，不再各写一份 |
| 降级治理 | A2 复用既有 `DegradationTracker` 通道与 `detail` 槽位，**不新建**第二套降级记录体系；不新增持久化文件 |
| 开关纪律 | 唯一新增开关 `doctor_check` 进 `EXPERIMENTAL_FEATURES` 注册表，默认关、默认零行为变更 |
| 渲染分层 | `core/doctor.py` 只返回结构化结果；CLI/TUI/Web 各自渲染（与 `check_sources.run_health_checks` 的既有分工一致） |
| 热路径纪律 | 连通性探测不进报告生成管线（仅 doctor 显式调用） |
| 不变量 | 合法输入下既有输出逐字不变；脏值路径由「泄漏」变为「兜底」（严格更安全） |

---

## 6. 测试设计

| 测试文件 | 覆盖 |
|:---------|:-----|
| `src/test/unit/core/test_num_utils.py` | `safe_num` 全脏值矩阵（None/bool/str/NaN/±inf/嵌套）、`finite_or` 对 NaN 的正确兜底（对照裸 `or`）、`is_finite_number` 判定 |
| `src/test/unit/core/test_num_utils_edge.py` | 极端值：`float("inf")`/`-inf`/`-0.0`/超大值/`Decimal`/`numpy` 标量 |
| `src/test/unit/core/test_doctor.py` | 各检查组返回结构、`include_network=False` 不联网、密钥检查**不回显内容** |
| `src/test/unit/fetcher/test_chain_diagnostics.py` | 诊断收集：逐 provider 原因、全链失败 `summary()` 可读、未传 `diagnostics` 时零采集、`record_failure` 收到可读原因 |
| `src/test/unit/report/test_data_status_message.py` | `record(message=...)` 进 `detail`、不传时 `detail=None`（向后兼容）、矩阵条目渲染可读原因 / 无 message 时回落机器串 |
| `src/test/unit/report/test_numeric_guard_regression.py` | **缺陷回归**：NaN 价格不再污染 `market_value` 的 `mv`/`profit`；NaN 份额行被 `reader` 拒绝；provider NaN 净值被兜底 |
| `src/test/unit/report/test_numeric_guard_regression_edge.py` | `±inf` 价格、全 NaN 组合、NaN 与真实值混合列的聚合输出 |
| `src/test/unit/llm/…`（若无则并入 cli/ui） | CLI `doctor` 子命令开关门控：关闭时提示、开启时执行；TUI 菜单项显隐 |

所有新增测试携带 marker（`unit_core` / `unit_report` / `unit_fetcher` / `edge`），edge 用例置于 `*_edge.py`。

既有测试需同步的预期变更：断言矩阵/detail 机器串的用例（如有）随可读原因调整；`signal_ledger` 与 `providers` 既有用例在合法输入下应**全部原样通过**（验证「逐字不变」不变量）。

---

## 7. 不变量与风险

**不变量**

1. 合法（有限数值）输入下，全链路输出与改动前逐字一致。
2. `fetch_with_fallback` / `fetch_with_incremental_fallback` 的**返回类型与取值语义不变**（新增能力只在可选出参上）。
3. `DegradationTracker.record()` 不传 `message` 时行为完全不变。
4. `doctor_check` 关闭时，CLI/TUI/Web 行为与改动前一致（无新菜单项、无新命令、无新卡片）。
5. doctor 绝不回显密钥明文。

**风险与缓解**

| 风险 | 缓解 |
|:-----|:-----|
| provider 解析器改委托后，某调用方依赖「NaN 透传」 | 全量跑 provider 既有测试；NaN 透传不构成任何合法契约（下游全是数值聚合） |
| `reader._safe_float` 追加有限性检查后，含 NaN 的历史持仓文件由「静默接受」变「告警拒绝」 | 属预期修复；补充回归测试固化；告警文案明确指向具体 sheet/行 |
| 改动面广（跨 providers/analysis/report/core） | 分批实施：先落原语与委托（可独立验证），再落 `or 0.0` 站点，最后 A2/B1；每批跑 `dev-verify` |
| doctor 联网检查被误用于热路径 | 模块 docstring 显式声明「仅显式调用」；报告管线不引用该模块（由架构约束表与 code review 把关） |

---

## 8. 实施批次

| 批次 | 内容 | 验证 |
|:----:|:-----|:-----|
| 1 | `core/num_utils.py` + 既有私有解析器收敛（含 `signal_ledger._safe_number`） | 既有 core/providers 测试全绿 + 新原语测试 |
| 2 | `or 0.0` 空防线站点替换 + `reader._safe_float` 有限性检查 | 回归测试 + `dev-verify` |
| 3 | A2 链路诊断（chain → record(message) → 矩阵/模板） | 诊断与矩阵测试 + `dev-verify` |
| 4 | B1 doctor 模块 + 三入口 + 开关注册 | doctor 测试 + 三入口冒烟 + 门禁 |

每批一次提交（遵守批次提交纪律：文档与代码同步）。

---

[↑ 回到顶部](#健壮性三件套实现设计plan-35)
