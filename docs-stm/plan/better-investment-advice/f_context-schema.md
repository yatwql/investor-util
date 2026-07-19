# f_context Pre-Schema

> **状态**：Pre-Schema（Phase 1 Full Schema 的前置工作）  
> **目的**：清晰定义当前管线中所有数据键的定义，消除通道混淆，为 Full Schema 和类型校验提供基础。  
> **通道说明**：当前架构中"管线数据"分为两个独立通道——`capture_snapshot()` 返回的 `f_context` 和 `prepare_report_data()` 返回的 `prep` 字典。两者通过不同路径到达 LLM 消费方。

---

## A 通道：f_context（`capture_snapshot()` 返回值）

写入模块：`src/python/report/orchestrator.py` L198-248  
消费模块：`src/python/llm/generators_orchestrator.py`、`src/python/llm/prompts.py`  
写入阶段：F1（快照对比）

### 顶层键

| 键名 | 类型 | 必选/可选 | 说明 |
|------|------|-----------|------|
| `diff` | `dict` | 可选 | 环比差异详情（见子键）。首次运行或无比较基准时为 `None` |

### diff 子键

| 键名 | 类型 | 必选/可选 | 说明 |
|------|------|-----------|------|
| `is_first_check` | `bool` | 必选 | 是否为首次检查（无历史快照可比较） |
| `days_since_last_report` | `int` | 必选 | 距离上次报告的天数 |
| `total_value_diff` | `float` | 必选 | 总市值变化（绝对值） |
| `total_value_diff_pct` | `float` | 必选 | 总市值变化百分比 |
| `total_pnl_diff` | `float` | 必选 | 总盈亏变化（绝对值） |
| `added` | `list[dict]` | 必选 | 新增持仓列表，每项含 `name`/`code`/`action`/`shares_diff`/`value_diff` |
| `removed` | `list[dict]` | 必选 | 清仓列表，每项同 `added` 结构 |
| `increased` | `list[dict]` | 必选 | 加仓列表，每项同 `added` 结构 |
| `decreased` | `list[dict]` | 必选 | 减仓列表，每项同 `added` 结构 |

### 历史清理

- ~~`diff_trimmed`~~（`bool`）：**已删除**（T0-01-B）。与 `diff.days_since_last_report` 完全重复，无下游消费
- ~~`days_since_last`~~（`int`）：**已删除**（T0-01-B）。无下游消费的死键

### T0-01 新增键

| 键名 | 类型 | 必选/可选 | 说明 |
|------|------|-----------|------|
| `data_degradation` | `list[dict]` | 必选 | DegradationTracker.get_log() 返回的会话内降级事件列表。空列表 = 今日无降级 |

---

## B 通道：prep（`prepare_report_data()` 返回值）

写入模块：`src/python/report/orchestrator.py` L58-132  
消费模块：`src/python/report/orchestrator.py` _generate_report_full / _generate_report_both  
写入阶段：S1（数据准备）

### 键定义

| 键名 | 类型 | 必选/可选 | 说明 |
|------|------|-----------|------|
| `details` | `list[DetailRow]` | 必选 | 行情明细（含价格/盈亏/涨幅） |
| `total_mv` | `float` | 必选 | 持仓总市值 |
| `total_cost` | `float` | 必选 | 持仓总成本 |
| `total_profit` | `float` | 必选 | 持仓总盈亏 |
| `total_today_profit` | `float` | 必选 | 今日总盈亏 |
| `categories` | `dict` | 必选 | 品种分类计数 `{type: count}` |
| `a_indices` | `dict` | 必选 | A 股指数行情 |
| `us_indices` | `dict` | 必选 | 美股指数行情 |
| `penetrated_assets` | `list[dict]` | 可选 | 穿透 TOP10 资产列表 |
| `holdings_details` | `list[dict]` | 必选 | 持仓明细字典列表 |
| `today_str` | `str` | 必选 | 当前日期 `YYYY-MM-DD` |
| `output_dir` | `str` | 必选 | 报告输出目录路径 |
| `news_top_count` | `int` | 必选 | 新闻最大返回条数 |

---

## C 通道：generate_all_llm 参数（独立传参）

`prep` 字典中的值在 `_generate_report_full()` 中以独立参数形式传入 `generate_all_llm()`。参数列表与 prep 键的对应关系：

| `generate_all_llm` 参数 | 来源 prep 键 | 最终转给 |
|-------------------------|-------------|---------|
| `a_indices` | `prep["a_indices"]` | `_build_global_macro_prompt` |
| `us_indices` | `prep["us_indices"]` | `_build_global_macro_prompt` |
| `total_mv` | `prep["total_mv"]` | `_build_expert_review_prompt`, `_build_health_check_prompt` |
| `total_cost` | `prep["total_cost"]` | `_build_expert_review_prompt`, `_build_health_check_prompt` |
| `total_profit` | `prep["total_profit"]` | `_build_expert_review_prompt`, `_build_health_check_prompt` |
| `total_today_profit` | `prep["total_today_profit"]` | `_build_expert_review_prompt`, `_build_health_check_prompt` |
| `holdings_count` | `len(holdings)` | `_build_expert_review_prompt`, `_build_health_check_prompt` |
| `categories` | `prep["categories"]` | 所有 prompt |
| `penetrated_assets` | `prep["penetrated_assets"]` | 所有 prompt（可选） |
| `holdings_details` | `prep["holdings_details"]` | 所有 prompt（可选） |
| `sector_flow` | `get_sector_fund_flow()` | `_build_global_macro_prompt`（可选） |
| `f_context` | `capture_snapshot()` 返回值 | `_build_expert_review_prompt`, `_build_health_check_prompt`（可选） |

---

## 集成断言检查点

以下 checkpoint 在生产环境作为 `logger.warning()` 输出类型不匹配日志，开发期在 `__debug__` 模式下额外触发 `assert`：

```python
# checkpoint: capture_snapshot 返回后
if f_context is not None:
    assert isinstance(f_context, dict), "f_context 类型异常"
    _diff = f_context.get("diff")
    if _diff is not None:
        assert isinstance(_diff, dict), "f_context.diff 类型异常"

# checkpoint: prepare_report_data 返回后
assert isinstance(prep, dict), "prep 类型异常"
for _k in ("total_mv", "total_cost", "total_profit", "total_today_profit"):
    assert isinstance(prep.get(_k), (int, float)), f"prep.{_k} 类型异常"
```
