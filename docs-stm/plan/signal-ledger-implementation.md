# 确定性数值信号沉淀 + live/demo 标签纪律 — 实现设计

> 文档版本：0.10.16-dev
> 语义名：`signal_ledger`（实验开关名同）
> 来源分析：[`augur-borrowing-analysis.md`](./augur-borrowing-analysis.md) §建议 B
> 对应计划项：`plan-34`（P4 实验功能）
> 结构模板：[`decision-reflection-implementation.md`](./decision-reflection-implementation.md)（`plan-30`）

---

## 1. 借鉴点与本项目落点

### 1.1 外部机制（augur）

`backtest.py:29-47,450-479` 的纪律：

- 每条记录打 `data_source="live"/"demo"` 标签；
- 排行榜 / IC 报告**默认只算 live**，合成记录绝不混入「真实战绩」；
- 附带 `safe_num` 数值归一（防 NaN/±inf 污染）→ 归 `plan-35` 建议 C，不在本项。

### 1.2 本项目现状

我方已有一批**确定性算法评级**，逐日可复算但**不留痕**——跑完即散，无法回溯「当时判了什么、后来对不对」：

| 信号 | 产出模块 | 关键字段 |
|---|---|---|
| 市场温度 | `analysis/market_temperature.py::compute_temperature` | `score`(0-100)、`tier`(低估/合理/高估) |
| 估值分位 | `analysis/valuation_percentile.py::compute_price_percentile` | `price_percentile`、`tier` |
| 尾部风险 | `analysis/tail_risk.py::compute_tail_risk` | `var95`、`var99`、`max_single_day_drop` |
| 风格因子 | `analysis/style_factor_regression.py::compute_factor_exposure` | `style_allocation`、`alpha`、`significant` |
| 再平衡超限 | `analysis/simple_rebalance.py::compute_simple_rebalance_signals` | `weight`、`threshold`、`action` |

**本项目不存在合成/demo 数据概念**（无 `example/`/`samples/` 持仓目录，全仓无 `data_source` 式标签）。因此 `demo` 的判定**不从新造旗标来**，而由**既有数据质量基础设施**推导——这正是「不引技术债」的落点：

- `core/data_freshness.py`：逐品种 `freshness` ∈ `fresh`/`cached`/`stale`/`degraded`；
- `report/data_status.py::DegradationTracker`：逐数据源 T2/T3/T4 降级事件（`data/state/.degradation_state.json`）。

### 1.3 落点

新增一套**只追加的信号账本**（`data/state/signal_ledger.jsonl`），记录确定性评级快照 + 来源标签；统计口径默认 `live_only=True`。

---

## 2. 架构合规自查（对照 `technical.md` 架构设计约束表）

| 约束 | 落点判定 |
|---|---|
| 分层依赖 | `core/signal_ledger.py` **只依赖 stdlib + 同层 `core`**（`decision_ledger` 常量、`data_freshness` 枚举、`jsonl_store` 原语、`config.features` 延迟 import）。**不 import** `report/`、`llm/`、`analysis/`——与 `decision_ledger.py` 同纪律。 |
| 单向依赖 | 抽取信号的职责落在 **report 层适配器** `report/signal_record.py`（report → core 合法）；提示词注入落在 **llm 层** `llm/skeleton.py`（llm → core 合法）。`core/` 不反向依赖。 |
| 数据契约 | 不新增 `pipeline_data` 顶层键（适配器只**读**既有契约键），无需 `data-channels-schema.md` 登记。 |
| 无单例 | 沿用 `decision_ledger` 的无状态函数集纪律，不设 `get_signal_ledger()`；避免跨测试状态泄漏。 |
| 缓存指纹同源 | 摘要注入提示词 → 写侧 `llm/generators.py::_fingerprint` 与预检侧 `llm/generators_orchestrator._compute_module_cache_info` **各补一处同调** `summary_cache_suffix()`。 |
| 语义命名 | 全部标识符用语义名（`signal_ledger`/`signal_record`/`data_source`/`resolve_data_source`），无任务编号。 |
| 实验开关三端可控 | 注册进 `EXPERIMENTAL_FEATURES` 即自动上屏 TUI 菜单 `[S]` / Web 配置面板 / CLI `--experiment`（三端由注册表驱动，无需改入口代码）。 |

---

## 3. 改动文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/python/core/jsonl_store.py` | 新增 | 原子 JSONL 追加/读取原语（去重既有两份拷贝） |
| `src/python/core/signal_ledger.py` | 新增 | 信号账本：常量 + 追加 + 折叠统计 + 摘要/injection 后缀 |
| `src/python/core/decision_ledger.py` | 改 | `_append_event_atomic`/`load_events` 委托 `jsonl_store`（消除重复实现） |
| `src/python/core/perf.py` | 改 | `_append_jsonl_atomic` 委托 `jsonl_store`（同上） |
| `src/python/report/signal_record.py` | 新增 | report 层适配器：从 `pipeline_data` 抽确定性评级 → 账本 |
| `src/python/report/_report_generation.py` | 改 | 新增步骤 5d：登记本轮确定性信号 |
| `src/python/llm/skeleton.py` | 改 | 账本摘要注入接收模块（与决策教训同注入点） |
| `src/python/llm/generators.py` | 改 | 写侧指纹补 `summary_cache_suffix()` |
| `src/python/llm/generators_orchestrator.py` | 改 | 预检指纹补 `summary_cache_suffix()` |
| `src/python/config/features.py` | 改 | 默认旗标 + `EXPERIMENTAL_FEATURES` 注册 |
| `src/test/conftest.py` | 改 | `_isolate_sensitive_paths` 隔离 `_SIGNAL_LEDGER_FILE` |
| `src/test/unit/core/test_jsonl_store.py` | 新增 | 原语测试 |
| `src/test/unit/core/test_signal_ledger.py` | 新增 | 账本/统计/摘要测试 |
| `src/test/unit/core/test_signal_ledger_edge.py` | 新增 | 边缘（`edge` 标记，独立 `*_edge.py`） |
| `src/test/unit/report/test_signal_record.py` | 新增 | 适配器抽取测试（含 live/demo 判定） |

---

## 4. 设计

### 4.1 共享原子原语 `core/jsonl_store.py`

**动机（去债而非加债）**：`core/perf.py::_append_jsonl_atomic` 与 `core/decision_ledger.py::_append_event_atomic` 已是**同一实现的第二份拷贝**（后者注释即写「对齐 `core/perf.py`」）。第三份拷贝即技术债，故先抽取：

```python
def append_jsonl_atomic(path: str, line: str, *, prefix: str = ".jsonl_", log_tag: str = "jsonl") -> None
def read_jsonl(path: str) -> list[dict[str, Any]]   # 损坏行跳过 + 告警，不中断后续行
```

`perf.py` / `decision_ledger.py` 改为**一行委托**，`prefix`/`log_tag` 保持原值以确保行为逐字不变（临时文件名与日志文本不动）。

### 4.2 标签纪律（核心）

```python
DATA_SOURCE_LIVE = "live"   # 本次运行实时可得
DATA_SOURCE_DEMO = "demo"   # 非本次实时（缓存/过期/降级/样本不足）
DATA_SOURCE_LABELS = {"live": "实时", "demo": "非实时"}
```

判定收敛于**单一函数**（禁止各调用点自行拼字符串）：

```python
def resolve_data_source(*, freshness: str | None = None, degraded: bool = False) -> tuple[str, str]:
    """返回 (data_source, source_reason)。"""
```

判据（判定顺序即优先级）：

1. `degraded=True` → `demo`，理由「依赖数据源本次降级」；
2. `freshness` ∈ {`cached`,`stale`,`degraded`} → `demo`，理由「行情缓存（T-1）/过期/降级」；
3. `freshness` = `fresh` → `live`，理由「本次实时行情」；
4. `freshness` 为 `None` → `live`，理由「组合级/指数级信号，无逐品种新鲜度条目」。

> **第 4 条的边界纪律**：`None` 乐观缺省**仅**适用于组合级（风格因子、尾部风险）与指数级（市场温度）信号——它们没有 `data_freshness.items` 条目。**持仓级**信号（估值分位、再平衡超限）**必须**由适配器传入该 `code` 的 `freshness`，不得省参。此约束由适配器保证并在其 docstring 声明。

### 4.3 记录 schema

每行一条 JSON（`sort_keys=True, ensure_ascii=False`）：

```json
{
  "event": "signal",
  "report_date": "2026-09-10",
  "signal_type": "market_temperature",
  "subject": "sh000300",
  "name": "沪深300",
  "rating": "高估",
  "value": 82.31,
  "direction": -1,
  "data_source": "live",
  "source_reason": "组合级/指数级信号，无逐品种新鲜度条目",
  "detail": {"score": 82.31, "price_percentile": 88.4}
}
```

- `signal_type` 枚举：`market_temperature`/`valuation_percentile`/`tail_risk`/`style_factor`/`rebalance_overflow`；
- `direction` 复用 `decision_ledger` 的 `DIRECTION_LONG=+1`/`DIRECTION_SHORT=-1`/`DIRECTION_FLAT=0`（**直接 import 同层常量**，保证两账本方向语义不分叉）；
- 评级 → 方向映射表 `RATING_DIRECTIONS`：低估→+1、合理→0、高估→-1、超限→-1（再平衡超限=建议减仓）；风格因子无方向语义 → `0`。

**不可用信号不入账**（`available=False` 的占位）——占位无评级、非真实观测，入账只会污染统计；可用性叙事已由既有降级披露（`plan-32`）承担。此为 v1 显式边界。

### 4.4 去重

同一 `(report_date, signal_type, subject)` 当日重复运行不重复入账（幂等，对齐 `decision_ledger.same_day_pending_exists()` 纪律）。

### 4.5 折叠统计

```python
def fold_signals(signals=None, *, live_only=True) -> dict
```

返回：`{records, live_count, demo_count, by_type, latest, dates, live_only, sample_sufficient}`。

- `live_only=True`（**默认**）时 `records` 只计 `data_source=="live"` 的条数；`live_count`/`demo_count` 恒为全量计数，供对比展示；
- `by_type[t]` → `{records, live, demo, latest_rating, latest_value, latest_date}`；
- `sample_sufficient`：live 样本数 ≥ `MIN_SUMMARY_SAMPLE`。

### 4.6 提示词注入与缓存指纹同源

```python
def summary_block(signals=None, *, live_only=True) -> str      # 样本不足返回 ""
def summary_cache_suffix(signals=None, *, live_only=True) -> str  # 块为空返回 ""，否则 "_sg{md5[:8]}"
```

- 注入点：`llm/skeleton.py` 与决策教训**同一接收模块集合、同一位置**，各自独立开关守卫；
- 缓存键同源：`llm/generators.py::_fingerprint` 与 `llm/generators_orchestrator._compute_module_cache_info` **各补一处** `+= signal_ledger.summary_cache_suffix()`；开关读**收敛在后缀函数内部**（`is_active()` 判空），防两侧漂移。

### 4.7 报告 seam

`_report_generation.py` 新增步骤 **5d**（在 5c 之后）：

```python
# ── 5d. 确定性数值信号沉淀（实验开关，默认关闭）──
# 置于 LLM 生成之后：尾部风险/危机标注等 A 通道键在 LLM 生成阶段才注入
# pipeline_data，过早登记会漏采。适配器对缺失键逐项跳过，故不构成硬依赖。
```

守卫 `signal_ledger.is_active()` + `try/except` + `reporter.warn`，与 3.6/5b 同纪律（实验功能异常不阻断报告主链路）。

---

## 5. 测试计划

| 文件 | 标记 | 覆盖 |
|---|---|---|
| `unit/core/test_jsonl_store.py` | `unit_core` | 原子追加/读取/损坏行跳过/目录缺失自建 |
| `unit/core/test_signal_ledger.py` | `unit_core` | `resolve_data_source` 四判据、`append_signal` 形状、去重幂等、`fold_signals` live_only 切换、`summary_block` 样本门槛、`summary_cache_suffix` 空/非空 |
| `unit/core/test_signal_ledger_edge.py` | `edge` | 账本文件不存在/损坏行/全 demo 记录/`value=None`/超长 detail |
| `unit/report/test_signal_record.py` | `unit_report` | 五类信号抽取、`available=False` 跳过、持仓级 live/demo 判定（freshness 注入）、缺键跳过 |

既有测试回归：`unit/core/test_decision_ledger.py`（验证原语抽取未改变行为）、`unit/core/test_perf*`、`unit/llm/test_prompts_structured_header.py`、`unit/web/test_config_edit.py`。

---

## 6. A / B 分解（对齐 `plan-31`/`plan-32`/`plan-33` 纪律）

- **A 缺陷修复（无开关，默认路径生效）**：**本项无**。经排查，五类确定性评级均无可复现的输出错误（`plan-33` 已修掉决策词解析这一类）。**不制造缺陷以凑 A/B 结构**——参照 `plan-31`/`plan-32` 的同一纪律，宁缺毋滥。
- **B 实验增强（`signal_ledger` 默认关）**：账本沉淀 + live/demo 标签 + `live_only` 统计默认 + 摘要注入。

---

## 7. 文档同步清单

管理文档：`requirements.md`、`technical.md`（含功能语义命名与实现节）、`llm-technical.md`、`folders.md`、`test-coverage.md`、`developer-guide.md`、`changelog.md`、`plan.md`。

用户文档：`README.md`、`manuals/how-to-config.md`、`how-to-config-llm.md`、`how-to-use-tui-menu.md`、`how-to-use-web-mode.md`、`how-to-use-cli-mode.md`。
