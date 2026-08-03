# 调仓 What-if 指定生效日时序回测

> **📦 已归档**：调仓 What-if 指定生效日时序回测已于 2026-08-03 实施完成（v0.9.10 发布）并归档至本目录。
> 前置功能：调仓 What-if 模拟（plan-5，v0.9.8，纯截面比较）见 [`../whatif-simulation/plan-whatif-simulation.md`](../whatif-simulation/plan-whatif-simulation.md)。

## Context（背景）

调仓 What-if 模拟目前是**成本口径截面比较**（份额 × 每份成本），文档标注"零网络请求、不可回测"。用户希望扩展：指定一个**调仓生效日**，取生效日之后的行情历史，用基准（调仓前）/目标（调仓后）两份持仓的 as-if 市值（份额 × 每日价格）各算一条归一化净值曲线，对比**区间收益 / 年化收益 / 年化波动率 / 夏普 / 最大回撤**。

**硬性约束（用户明确要求）**：回测计算逻辑必须全部放**共享层**（analysis + report），CLI/TUI 只做入口差异（参数解析 / 交互提示 / 传参），不得在 CLI/TUI 里写任何回测业务代码。

**既有设计边界**：不指定生效日 → 维持现状（纯截面，零网络请求）。指定生效日 → opt-in 联网取历史，回测是假设推演、不构成收益承诺；回测失败/数据不足 → 降级不阻塞主报告（主 whatif 契约仍可用，仅回测区隐藏/占位）。

## 复用组件

- `src/python/report/portfolio_history.py::PortfolioHistoryCalculator` — `get_combined_timeseries(holdings, days)` 现成 as-if 时序引擎（close×shares、LOCF 合并、回撤/波动率/总收益）。**缺口**：days 只作用于基准指数，需透传到持仓历史链路。
- `src/python/fetcher/chain.py::fetch_with_incremental_fallback(chain, code, days=30)` — 已支持 days；股票/ETF K 线上限 365 天，场外基金全量。TTL 缓存开箱即用。
- `src/python/analysis/metrics.py` — `sharpe_ratio()`；`annualized_return` / `max_drawdown_pct` 需从 `calmar_ratio` 内联代码抽取为独立纯函数。
- `src/python/analysis/whatif.py::_arrow` — 指标方向箭头（analysis→analysis 允许）。
- `src/python/report/excel_writer.py`（`write_title_row`/`write_header_row`/`write_data_row`/`_write_placeholder`/`freeze_header`/`auto_width`）、`src/python/report/data_status.py::STATUS_MESSAGES`。
- HTML 图表：`src/static/chart-common.js::ChartCommon.lineOptions(yLabel)`；线图数据形状参考 `src/python/report/chart_data_builder.py::_build_portfolio_line_dataset`；降采样 `src/python/report/downsample.py::downsample_bars`（≤500 点日频原样）。

## 实现步骤

### Step 1 — `days` 透传（portfolio_history.py）
给 5 个方法加 `days: int = 30` 默认值（向后兼容，主报告 `_snapshot.py` 路径零变化）：
`get_combined_timeseries` → `_fetch_all_histories(holdings, days)` → `calculate_for_holding(code, name, shares, days)` → `_get_stock_history(code, days)` / `_get_fund_history(code, days)`，末两者把 days 传给 `fetch_with_incremental_fallback`。更新第 156-158 行 docstring（删"仅作用于基准指数"）。

### Step 2 — metrics.py 抽取纯函数
新增 `annualized_return(daily_returns, trading_days=252)` 与 `max_drawdown_pct(daily_returns)`（返回**正数**幅度），guard 与 `sharpe_ratio` 一致（`check_data_sufficiency==0 → None`）。refactor `calmar_ratio` 复用两者。加入 `__all__`。

### Step 3 — 新建 `src/python/analysis/whatif_backtest.py`（纯计算）
模块 docstring 声明"纯计算、不联网、不 import report/"（遵守 analysis 层单向依赖纪律）。函数：
- `compute_backtest_days(effective_date, today=None) -> int | None` — 格式无效或 `eff >= today` 返回 None；否则自然日→交易日（×5/7）+ 热身 20，钳位 `[30, 365]`。
- `_align_series(base_bars, cand_bars, effective_date)` — 并集日期 + 各自 pairwise LOCF + 首个双方有值锚点（锚点前丢弃，锚点值 >0）；无共同锚点返回 None。
- `_normalize` / `_returns_from_values` / `_drawdown_series`（负百分比）/ `_build_metrics`。
- `compute_backtest_metrics(base_bars, cand_bars, effective_date, base_status="ok", cand_status="ok") -> dict` — 数据不足（`len(labels)-1 < _MIN_SAMPLE_DAYS=20`）或无可对齐数据 → `available:False`；正常 → `available:True`，status 传播 degraded。

**契约 `whatif_data["backtest"]`**：
```python
{available, status("ok"/"degraded"/"unavailable"), reason, effective_date,
 metrics: [{key,label,unit("pct"/"ratio"),base,candidate,delta,arrow}, ...],  # 5 行
 series: {labels, base, candidate, base_drawdown, candidate_drawdown}}  # 归一化到 100 / 回撤负%
```

### Step 4 — 共享层整合（whatif_operations.py）
- 新增 `build_whatif_backtest(base, candidate, effective_date=None, session_cache=None) -> dict | None`：无生效日返回 None；`compute_backtest_days` 无效返回 unavailable dict；合并多账户 → `PortfolioHistoryCalculator(session_cache=cache, benchmark_indices={})`（禁用基准，免多余网络）对 base/candidate 各跑一次 `get_combined_timeseries(..., days=days)` → 调 `compute_backtest_metrics`。
- `run_whatif_simulation` 加 `effective_date: str | None = None`；`effective_date=None` 时**不调用、不加 backtest 键**（报告自然隐藏/占位）；调用时包 try/except，异常→`available:False` + reason，**不阻塞主报告**。
- 从 `analysis/whatif.py` import `_merge_holdings`。

### Step 5 — CLI 入口（只传参）
`src/python/cli/cli.py`：whatif 子命令加 `--effective-date YYYY-MM-DD`（可选，help 说明 opt-in 联网回测）；`_handle_whatif` 调 `run_whatif_simulation(..., effective_date=args.effective_date)`。epilog 补示例行。无业务逻辑。

### Step 6 — TUI 入口（交互提示，只传参）
`src/python/tui/handlers_whatif.py`：新增 `_prompt_effective_date() -> str`（input 提示，回车=空，EOF/KeyboardInterrupt→空）。`_cmd_whatif` 在读取两份持仓成功后、调用 `run_whatif_simulation` 前调用并传 `effective_date=eff or None`。**不校验格式**（格式错误由共享层 `compute_backtest_days` 降级）。**必须**：现有 `TestCmdWhatif` 测试补 `@patch("..._prompt_effective_date", return_value="")`，否则新增 input() 会让它们卡住。

### Step 7 — Excel 第 4 页签「时序回测」
- `data_status.py` `STATUS_MESSAGES` 加 `whatif_backtest_unavailable`。
- `whatif_sheet.py` 新增 `write_whatif_backtest_sheet(ws, whatif_data)`：标题行 + 生效日信息行 + 指标对比表（5 行，unit 映射 `{"pct":"0.00","ratio":"0.00"}`，变化列拼 arrow）+ 净值曲线数据表（日期×基准/目标净值×基准/目标回撤）+ 说明（口径/局限）。`available=False`/None → `_write_placeholder`。
- `whatif_writer.py::write_whatif_excel` 加 `wb.create_sheet("时序回测")` + 调用新函数。
- `whatif_sheet.py` 摘要页 notes 三条文案更新（截面零网络 / 回测 opt-in / 不构成承诺）。

### Step 8 — HTML 呈现
- `whatif_writer.py` 新增 `_trim_whatif_backtest_chart_data(whatif_data)`（R9 数据最小化，只传 series 字段）；`render_whatif_html` render 时加 `whatif_backtest_chart_data=...` context 变量。
- `src/python/tmpl/whatif_template.html`：
  - 顶部加 `{% set _bt = whatif_data.get("backtest") if whatif_data else None %}`。
  - 章节重排：③ 资产配置双环图之后插新 **④ 时序回测** section（`{% if _bt and _bt.available %}` 包裹）；原 ④⑤⑥ 顺延为 ⑤⑥⑦。③ 的 `{% if _cats %}` 闭合块需拆分（现与 ④ 分类表共用一个 if）。
  - 新 ④ section：指标对比卡（复用 ② 的 `.summary-card` + arrow class；unit=="pct" 值后拼 `%`）+ 2 张线图（归一化净值曲线 + 回撤曲线），各带 `.chart-caption`（C20），canvas 带 aria-label/role="img"。数据经 `<script type="application/json" id="whatif-backtest-chart-data">{{ whatif_backtest_chart_data | tojson }}</script>` 注入；JS 复用 `window.ChartCommon.trackChart(new Chart(cv, {type:'line', data:{labels,datasets}, options:ChartCommon.lineOptions(yLabel)}), cid)`，ES5，DOMContentLoaded + try/catch。
  - ⑦ 说明区更新三条文案 + 加"启用时序回测（指定生效日）时联网取历史"。

### Step 9 — 文档同步
- `analysis/whatif.py` docstring（第 5-15 行）"零网络请求/不可回测" → 截面零网络、回测 opt-in。
- `technical.md` §4.13 设计边界 + C19 契约加 backtest 键 + 分层说明。
- `how-to-menu.md` [W] 段 / `how-to-start.md` / `reports-instruction.md` 补 `--effective-date` 与 TUI 生效日提示用法。
- `testplan.md` §6.4 手动验证项（有/无生效日、未来生效日、离线降级、Excel 4 页签、HTML 回测区隐藏）。
- `folders.md`：analysis 区加 `whatif_backtest.py`，测试区加 `test_whatif_backtest.py`。
- `changelog.md` 0.9.10-dev 加 Feat 条目。

## 测试计划

| 文件 | 内容 |
|---|---|
| `src/test/unit/analysis/test_whatif_backtest.py`（新增）`[unit, unit_analysis]` | compute_backtest_days 折算/钳位/坏格式；_align_series 并集+LOCF+锚点/无锚点/0 值；归一化/returns/drawdown/_build_metrics 数值断言；compute_backtest_metrics 正常/数据不足/两侧空 bars/status 降级。`pytest.approx` |
| `test_whatif_backtest_edge.py`（新增）`@pytest.mark.edge` | 未来日期、单 bar、首值 0、None 注入、极端涨跌 |
| `test_whatif_operations.py`（扩展） | `@patch("...build_whatif_backtest")`：None 不调用且无 backtest 键；指定生效日合并进 data；异常→ok=True 且 available=False；返回 None→不加键 |
| `test_portfolio_history.py`（扩展） | 现有断言补 days：`assert_called_once_with("history_stock","600900")`→`("history_stock","600900",30)`；新增 days=365 透传断言 |
| `test_whatif_sheet.py` / `test_whatif_writer.py`（扩展） | `write_whatif_backtest_sheet` full/占位/None 占位；`write_whatif_excel` 4 页签 |
| `test_whatif_html.py`（扩展） | ①~⑥→①~⑦；backtest available→④ 出现 + 2 个 line canvas + 2 条 caption（C20）+ `#whatif-backtest-chart-data` 可解析且无冗余字段（R9）；缺失/不可用→④ 隐藏 |
| `test_cli.py`（扩展） | `--effective-date` 解析 + 透传到 run_whatif_simulation kwargs |
| `test_handlers_whatif.py`（扩展） | `TestCmdWhatif` 补 `@patch("..._prompt_effective_date", return_value="")`；新增生效日输入透传 / 回车空→None |

## 风险点

- **chain 缓存键不含 days**（`history_{chain}_{code}`）：主报告 days=30 跑过后的短缓存，回测请求更长 days 可能只返回缓存短历史 → 生效日较远时回测 unavailable。缓解：文档/提示回测前可 `cache --update all`；首次运行无缓存全量拉取正常。列为后续 chain 增强项。
- **TUI 测试卡输入**：新增 input() 必须给 `TestCmdWhatif` 补 mock。
- **analysis 层单向依赖纪律**：联网编排放 `report/whatif_operations.py::build_whatif_backtest`，纯计算放 analysis——不破坏 `metrics.py` "不 import report" 约束。

## 验证

1. 单测：`pytest src/test/unit/analysis/test_whatif_backtest.py src/test/unit/analysis/test_whatif_backtest_edge.py src/test/unit/report/ src/test/unit/handlers/test_handlers_whatif.py src/test/unit/cli/test_cli.py -q`
2. P0 门禁：`python scripts/test_runner.py --mode dev-verify` + `python scripts/check-code-traces.py --ci` + `python scripts/check-doc-traces.py --ci`
3. `ruff format --check` 受影响文件
4. 手动：CLI `--effective-date 2026-07-01` 生成含 4 页签 Excel + 含回测区 HTML；不指定生效日 → 维持现状
5. 提交；计划文件迁移至 `docs-stm/plan/`
