# Iter 8: Excel 基准指数列

> ✅ **已完成**（I 迭代的一部分，v0.5.6 完成）
>
> 创建日期：2026-07-14 | 完成日期：2026-07-14

## Context

组合历史走势和回撤分析的 Excel 页签目前已创建但完全空白——`portfolio_history` 和 `drawdown_analysis` 两个 sheet 只有标题行，无任何数据写入。而 `history_data["benchmarks"]` 在 `portfolio_history.py` 中已完整计算好（归一化至 100 基点的指数走势 + 累计收益率/最大回撤等指标），且已成功注入 HTML 报告的 Canvas 图表。Iter 8 的目标是将这些基准数据写入 Excel 页签。

## Implementation Plan

### 1. `excel_generator.py` — 新增 `history_data` 参数

**函数签名** (`generate_excel_report`): 在 `f_context` 参数后添加 `history_data: dict | None = None`。

**docstring** 新增：`history_data: 组合历史走势数据（含基准指数），来自 PortfolioHistoryCalculator。未提供或 status=unavailable 时页签显示占位文本。`

### 2. `excel_generator.py` — 新增 `_write_history_sheets()` 函数

在 `generate_excel_report()` 之前添加模块级私有函数（`_write_history_sheets` → `_write_portfolio_history_sheet` + `_write_drawdown_analysis_sheet`）。

#### `_write_portfolio_history_sheet(ws, history_data)` — 两张表的核心

**数据缺失时**：调用 `_write_placeholder(ws, "组合历史走势数据暂不可用（配置或网络原因）", max_cols=5)`

**表头结构**：`[日期, 组合市值, 组合收益(%), 组合归一化(%), 基准1名, 基准2名, ...]`

**数据行**（每行一个 bar）：
- 日期 → 文本
- 组合市值 → `FMT_MONEY`（`#,##0.00`）
- 组合收益(%) → `(bar.total_value / first_value - 1)` 存储为小数 → `FMT_PERCENT`（`0.00%`）
- 组合归一化(%) → `bar.total_value / first_value * 100` → `'0.00'`
- 各基准值 → `bm.bars[i].value`（已归一化到 100）→ `'0.00'`

**指标汇总区**（数据行下方，空一行后写入）：
- 累计收益率(%) → `total_return_pct / 100` → `FMT_PERCENT`
- 累计收益(元) → `total_return` → `FMT_MONEY`
- 最大回撤(%) → `max_drawdown_pct / 100` → `FMT_PERCENT`
- 年化波动率 → `annualized_volatility` → `FMT_PERCENT`（注意：已是小数，不需 ÷100）
- 起算日 / 终止日 → 文本

#### `_write_drawdown_analysis_sheet(ws, history_data)` — 对比矩阵

**数据缺失时**：`_write_placeholder(ws, "历史回撤分析数据暂不可用（配置或网络原因）", max_cols=5)`

**表头**：`[指标, 组合, 基准1名, 基准2名, ...]`

**指标行**：累计收益率(%)、最大回撤(%)、年化波动率、起算日、终止日
- 组合列：取 `history_data` 的对应字段
- 基准列：取 `benchmark` 各条目的对应字段
- 百分比字段 ÷100 后使用 `FMT_PERCENT`

### 3. `excel_generator.py` — 在 `generate_excel_report()` 中插入调用

在 `write_llm_section_and_usage(...)`（第 102 行）之后、`f_context` 块（第 104 行）之前插入：

```python
# ── 组合历史走势 + 回撤分析页签（F2 数据） ──
if enable_history:
    ws_ph = sheets.get("portfolio_history")
    ws_dd = sheets.get("drawdown_analysis")
    if ws_ph is not None or ws_dd is not None:
        prog.info("正在写入组合历史走势页签...")
        try:
            _write_history_sheets(sheets, history_data)
        except Exception:
            logger.debug("[excel] 组合历史走势页签写入失败（非关键）", exc_info=True)
```

### 4. `handlers_report.py` — 传递 `history_data`

两个调用点：

**`_cmd_generate_both()`**（~第 257 行）：在 `f_context=f_context` 后加 `history_data=history_data`（`history_data` 已在该作用域第 230 行获取）

**`_cmd_generate_full()`**（~第 582 行）：在 `f_context=f_context` 后加 `history_data=history_data`（`history_data` 已在该作用域第 458 行获取）

### 5. 关键格式注意事项

| 字段 | 存储值示例 | 写入值 | 格式 |
|------|-----------|--------|------|
| `total_return_pct` | 5.0 (5%) | 0.05 | `0.00%` |
| `max_drawdown_pct` | -20.0 (-20%) | -0.20 | `0.00%` |
| `annualized_volatility` | 0.1534 | 0.1534 | `0.00%` |
| `benchmark.total_return_pct` | 3.0 (3%) | 0.03 | `0.00%` |
| `benchmark.max_drawdown_pct` | -5.0 (-5%) | -0.05 | `0.00%` |

## Files to Modify

1. `D:\path\to\investor-util\src\python\report\excel_generator.py`
2. `D:\path\to\investor-util\src\python\handlers_report.py`

No new files needed. No new external dependencies.

## Verification

- `python scripts/test_runner.py --mode regression` — 确认不会破坏现有测试
- 检查生成的 Excel 文件：
  - `portfolio_history` sheet 应有日期 + 组合数据 + 每基准一列
  - `drawdown_analysis` sheet 应有对比指标矩阵
  - 无基准时 sheet 依然正常显示（仅组合列）
  - `history_data=None` 时 sheet 显示占位文本
