# 组合历史走势与基准指数比对 — 技术设计

> ✅ **已完成**（v0.5.6）
>
> 迭代自 [plan.md](../managements/plan.md) [P3] I，9 轮迭代落地
>
> 创建日期：2026-07-15 | 最后更新：2026-07-16 | 完成日期：2026-07-14

---

## 1. 需求概述

组合历史走势（`portfolio_history.py`）当前仅展示 **绝对收益**（as-if 净值曲线）。用户无法判断组合相对市场的表现。本功能在走势图中叠加基准指数（沪深 300、标普 500 等）归一化曲线，使相对收益和相对回撤可量化。

### 1.1 用户故事

```
作为一名投资者，我希望在组合历史走势图上叠加基准指数线，
从而直观地判断组合是否跑赢大盘、跑赢/跑输的幅度有多大。
```

### 1.2 功能边界

| 包含 | 不包含 |
|------|--------|
| 组合走势 + 指数归一化曲线（双线叠加） | 同一图三条以上线（最多 2-3 条） |
| 回撤分析图 + 指数回撤曲线（双线叠加） | 自定义指数合成、行业指数对比 |
| 默认 A 股沪深 300、美股标普 500 | 指数定投收益计算 |
| 指数代码可配置（config.json） | 指数行情实时监控（已有） |
| 指数历史日线复用现有 Provider Chain | 多指数-组合相关性矩阵 |

### 1.3 不产生新报告模块

指数数据**不作为独立 report section** 注册，而是作为 `portfolio_history`（section 17）和 `drawdown_analysis`（section 18）的**内部增强数据**。不修改 `_REPORT_SECTION_DEFAULT`，C7 约束合规。

---

## 2. 系统架构总览

### 2.1 新增模块：`report/benchmark.py`

```
src/python/report/
├── __init__.py
├── benchmark.py               ← 新增：基准指数数据获取 + 归一化算法
├── portfolio_history.py       ← 修改：调用 benchmark.py
├── html_builders.py           ← 修改：传入 benchmark 数据到模板
├── html_writer.py             ← 修改：context 透传
├── excel_content_sheets.py    ← 修改：写入基准列
...其他模块不变
```

**`benchmark.py` 职责**：
- `fetch_benchmarks(indices_config, portfolio_days)` → 并行获取指数原始数据（调用 `fetch_index_history`，内部使用 `max(365, portfolio_days)` 确保归一化需要）
- `normalize_benchmarks(portfolio_bars, benchmark_bars_list, codes, names)` → 起算日对齐 + 100 基点归一化
- `_compute_benchmark_drawdowns(benchmarks_bars)` → 指数回撤指标

**不纳入 `portfolio_history.py` 的理由**：
- `portfolio_history.py` 已 435 行，职责为组合 LOCF 合并 + 回撤/波动率计算
- Benchmark 计算涉及独立的获取、对齐、归一化逻辑，变化原因不同
- 未来若增加更多指数类型（行业指数、债券指数），不影响组合计算器

### 2.2 数据流（优化版：同一并行池获取）

```
┌─ config.json ──────────────────────────────────────┐
│  "history": {                                       │
│    "coverage_threshold": 0.8,                       │
│    "benchmark_indices": {                           │  ← Feature Flag
│      "sh000300": "沪深300",                         │
│      "gb_inx": "标普500"                            │
│    }                                                │
│  }                                                  │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
┌─ get_combined_timeseries(holdings, indices_config) ─┐
│                                                      │
│  ThreadPoolExecutor(max_workers=8) [并行, 已有+扩展] │
│  ╔══════════════════════════════════════════════════╗ │
│  ║  持仓 A ──→ calculate_for_holding()             ║ │
│  ║  持仓 B ──→ calculate_for_holding()             ║ │
│  ║  持仓 C ──→ calculate_for_holding()             ║ │
│  ║  指数1(sh000300) ──→ fetch_index_history()      ║ │  ← 与持仓并行，零额外延迟
│  ║  指数2(gb_inx)    ──→ fetch_index_history()     ║ │
│  ╚══════════════════════════════════════════════════╝ │
│                         ↓                             │
│  ① LOCF 合并 [已有]                                   │
│  ② 有效区间双向截断 [已有]                            │
│  ③ normalize_benchmarks() [新增, 纯计算, 无 IO]      │
│  ④ 回撤/收益率/波动率 [已有]                          │
│                                                      │
│  ⑤ return {bars, max_drawdown, ..., benchmarks}     │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
┌─ html_writer.py ──────────────┬─ excel_content_sheets.py ─┐
│ 传递 benchmarks 到模板 context │ 写入基准指数列             │
└──────────────┬────────────────┴──────────────┬────────────┘
               │                                │
               ▼                                ▼
┌─ report_template.html ──────┐   ┌─ Excel 页签 ────────────┐
│ Section 17: 组合历史走势     │   │ 日期 | 组合市值 | ...    │
│  drawSimpleChart({          │   │ 指数净值 | 指数日收益 |   │
│    datasets: [              │   │ 指数回撤                 │
│      {label:"组合",...},    │   └──────────────────────────┘
│      {label:"沪深300",...}  │
│    ]                        │
│  })                         │
│ Section 18: 历史回撤分析     │
│  drawSimpleChart({          │
│    datasets: [组合回撤,指数] │
│  })                         │  ← Chart.js 已迁移至 Native Canvas
└─────────────────────────────┘
```

**并行优化说明**：
- 基准指数获取与持仓走势获取**提交到同一个 ThreadPoolExecutor**
- 指数返回后由 `normalize_benchmarks()` 处理，该函数**纯计算无 IO**
- 因此，基准指数的网络延迟完全被持仓获取覆盖，`get_combined_timeseries()` 总耗时 ≈ 持仓获取耗时 + 归一化运算耗时（< 50ms）

### 2.3 9 轮迭代依赖拓扑

```
Iter 1: code_utils + config         ──────────┐
Iter 2: tencent fetch_index_kline() ──┐ ──────┤
Iter 3: sina fetch_index_kline()   ──┐ │ ────┤
Iter 4: history_index chain         ┐ │ │ ──┤ │
Iter 5: fetcher/index.py            ┐│ │ │ ─┤ │   ← 获取层完备
Iter 6a: report/benchmark.py        ┐│ │ │ │ ─┤ │ ← 获取+集成
Iter 6b: normalize_benchmarks()     ┐│ │ │ │ │ ─┤ │ ← 纯算法
Iter 7: 走势+回撤+CDN移除+图例      ┐│ │ │ │ │ │ ─┤ │ ← 合并里程碑
Iter 8: Excel columns               ││ │ │ │ │ │ │ │
Iter 9: regression + docs           ││ │ │ │ │ │ │ │
                                     ▼ ▼ ▼ ▼ ▼ ▼ ▼
Iter 可独立 revert:
  - 6a (数据获取) 和 6b (归一化) 互不影响
  - 7 (走势图+回撤图+CDN) 一次完成，无过渡断裂风险
  - 8 (Excel) 完全独立于 HTML 渲染路径
```

**关键点**：
- **Iter 7 合并了原 Iter 7（drawSimpleChart 多 dataset + 走势图双线 + 图例/tooltip）和原 Iter 8（回撤图调优 + Chart.js CDN 移除）**。这是唯一安全的做法：`drawSimpleChart` 签名从 `(canvasId, labels, values, opts)` 变为 `(canvasId, datasets, opts)` 后，两个调用点（走势图和回撤图）必须在同一轮更新，否则过渡期的回撤图调用老签名导致参数错位。Iter 8（Chart.js 迁移）本质上是同一变化的收尾，移除 CDN 不产生新功能变更，合并在 Iter 7 消除过渡期断裂风险。
- **Iter 4 关键注意点**：需要修改 `_DEFAULT_CHAINS` 新增 `"history_index": ["tencent", "sina"]`（line 33），`_call_history_provider()`（line 379-390）新增 `history_index` dispatch 分支。**不需要修改**：`_HISTORY_PROVIDER_MAP`（line 337-342）映射的是 provider 名→模块路径（已有 tencent/sina），`history_index` 不在此注册；`_get_chain()`（line 38）已是通用函数，无需新增路由。`history_stock` 和 `history_fund_otc` 现有分支不被修改。

---

## 3. Config 入口改动

`handlers_report.py` 中 `PortfolioHistoryCalculator` 的实例化方式从：

```python
_calc = PortfolioHistoryCalculator(coverage_threshold=_coverage)
history_data = _calc.get_combined_timeseries(_holdings_tuples)
```

改为：

```python
_calc = PortfolioHistoryCalculator(
    coverage_threshold=_coverage,
    benchmark_indices=_history_cfg.get("benchmark_indices", {}),
)
history_data = _calc.get_combined_timeseries(_holdings_tuples)
```

`PortfolioHistoryCalculator.__init__` 新增 `benchmark_indices` 参数（与 `coverage_threshold` 同模式），`get_combined_timeseries()` 签名不变。

### Kill-Switch 语义

```
config.json `history` 段中 benchmark_indices 键的状态    → 行为
──────────────────────────────────────────────────────────
键不存在（键缺失）                                         → 使用默认值（沪深300 + 标普500，自动启用）
键存在且值为 {}                                            → 禁用，无基准线（Kill Switch）
键存在且值为 {"sh000300": "沪深300"}                       → 仅显示配置的基准
"history": {} 或整个 history 段缺失                         → get_config() 返回默认值 → 启用
```

注意：**键缺失 ≠ 禁用**。默认值会启用沪深 300 和标普 500。用户若不想看到任何基准线，必须显式设 `"benchmark_indices": {}`。

### days 参数传递

```python
# benchmark.py 内部
def fetch_benchmarks(indices_config: dict[str, str], portfolio_days: int = 30) -> list[dict]:
    """并行获取基准指数历史数据。

    Args:
        indices_config: 基准配置
        portfolio_days: 组合请求的天数。指数实际获取天数为 max(365, portfolio_days)，
                       因为归一化需要足够的回溯数据来对齐起算日。
    """
    fetch_days = max(365, portfolio_days)
    # 每个指数调用 fetch_index_history(code, fetch_days)
```

---

## 4. 数据模型设计

### 4.1 `get_combined_timeseries()` 返回值扩展

```python
# 原字段全部保留，新增 benchmarks
{
    "bars": [...],                                 # 组合走势（不变）
    "max_drawdown": ...,                           # 不变
    "max_drawdown_pct": ...,                       # 不变
    "benchmarks": [                                # 新增
        {
            "code": "sh000300",                    # 指数代码
            "name": "沪深300",                      # 指数名称
            "bars": [                              # 归一化后的走势
                {"date": "2026-06-01", "value": 100.0},
                {"date": "2026-06-02", "value": 101.5},
                ...
            ],
            "total_return_pct": 5.2,               # 区间累计收益率
            "max_drawdown_pct": -3.1,              # 区间最大回撤
            "data_start": "2026-06-01",            # 指数数据起始日
            "data_end": "2026-07-14",              # 指数数据结束日
            "status": "ok",                        # "ok" | "degraded"
        }
    ],
}
```

### 4.2 `report/benchmark.py` 接口

```python
def fetch_benchmarks(
    indices_config: dict[str, str],
    days: int = 365,
) -> list[dict]:
    """并行获取所有配置基准指数的历史日线数据。

    调用 fetch_index_history() 获取每个指数的原始 bars，
    通过 ThreadPoolExecutor 并行执行（被 PortfolioHistoryCalculator 复用）。

    Args:
        indices_config: {"sh000300": "沪深300", "gb_inx": "标普500"}
        days: 获取天数

    Returns:
        [{"code": str, "name": str, "bars": list[dict],
          "status": "ok"}, ...]
        失败的指数不出现在列表中。全失败返回 []。

    注意: 不缓存到 portfolio_history._session_cache，
          依赖 fetch_index_history 内部的 DataSourceRegistry.session_cache（C4）。
    """

def normalize_benchmarks(
    portfolio_bars: list[dict],
    benchmark_bars_list: list[list[dict]],
    benchmark_codes: list[str],
    benchmark_names: list[str],
) -> list[dict]:
    """归一化基准指数到 100 基点，与组合对齐。

    纯计算函数，无 IO 依赖，可单独单元测试。

    Args:
        portfolio_bars: 组合走势（已截断的 bars）
        benchmark_bars_list: 各指数的原始 bars
        benchmark_codes: 指数代码列表
        benchmark_names: 指数名称列表

    Returns:
        [{"code": str, "name": str, "bars": [{"date", "value"}, ...],
          "total_return_pct": float, "max_drawdown_pct": float,
          "data_start": str, "data_end": str, "status": str}, ...]
    """
```

### 4.3 `fetch_index_history()` 接口

```python
def fetch_index_history(code: str, days: int = 365) -> list[dict] | None:
    """获取指数历史日线。

    通过 history_index chain 路由，复用 tencent/sina 的 K 线能力，
    跳过 is_a_share_code 类型检查。

    Args:
        code: 指数代码，如 "sh000300" / "gb_inx"
        days: 获取天数（默认 365，最大 3650）

    Returns:
        [{"date": "...", "close": float, "open": float,
          "high": float, "low": float, "volume": int}, ...]
        按日期升序。全链路失败返回 [].

    C4 约束: 同次会话同一代码命中 DataSourceRegistry.session_cache
    C6 约束: 走 _fetch_with_incremental_fallback，不绕过 chain
    """
```

### 4.4 Provider 新增函数签名

```python
# tencent.py
def fetch_index_kline(code: str, days: int = 30,
                      start_from: str | None = None) -> list[dict]:
    """获取指数历史 K 线数据（腾讯财经）。

    与 fetch_kline() 的区别：
      - 不检查 is_a_share_code/is_exchange_fund_code
      - _add_prefix 对含前缀代码（sh000300）原样返回
      - 复用 _parse_kline_response() 解析逻辑

    Args:
        code: 指数代码，如 "sh000300" / "gb_inx"
        days: 获取天数（默认 30，最大 365 与指数盘一致）
        start_from: 增量起始日期 YYYY-MM-DD

    Returns:
        list[dict]: 同 fetch_kline，[{date, open, close, high, low, volume}]
    """

# sina.py — 同上，Tencent 的备用链路
def fetch_index_kline(code: str, days: int = 30,
                      start_from: str | None = None) -> list[dict]:
    """获取指数历史 K 线数据（新浪备用链路）。

    与 fetch_kline() 的区别：不检查类型，复用 _parse_kline_response。
    """
```

---

## 5. 归一化算法

### 5.1 三段式对齐

```
组合有效起算日: 2026-01-15（通过覆盖阈值确定）
指数数据首日:   2026-03-01（指数只返回了 180 天）

对齐起算日 = max(组合有效起算日, 指数数据首日) = 2026-03-01

        2026-01-15 ─── 2026-03-01 ─── 2026-07-14
组合线:  ████████████████████████████████████████
                  ↑ 指数从此处开始，与组合在 2026-03-01 同时归一化到 100
指数线:           ████████████████████████████████
```

```python
def normalize_benchmarks(
    portfolio_bars: list[dict],         # 组合走势（已截断）
    benchmark_bars_list: list[list[dict]],  # 各指数原始数据
    benchmark_codes: list[str],
    benchmark_names: list[str],
) -> list[dict]:
    """归一化基准指数到 100 基点，与组合对齐。

    步骤:
      1. 确定对齐起算日 = max(组合 bars[0]["date"], 指数首条数据日期)
      2. 从对齐起算日开始，将组合和指数分别归一化：
         normalized[t] = raw[t] / raw[align_start] × 100
      3. 对齐前的组合数据保持原始值（指数线不绘制到对齐前）
      4. NaN 过滤：指数 bars 中 close 为 NaN 或 0 的行不参与归一化
      5. 日期集合对齐：以组合的日期列表为基准，指数在缺失日期上做 LOCF（前值填充），
         确保最终组合和指数的 values 数组长度一致、索引一一对应。例如：
         组合 [1/1, 1/2, 1/3, 1/4]，指数 [1/1=100, 1/4=102]
         → LOCF 后 [1/1=100, 1/2=100, 1/3=100, 1/4=102]
      6. 从对齐起算日截取最终 bars

    Returns:
        [{"code": str, "name": str, "bars": [...], ...}, ...]
    """
```

### 5.2 回撤对齐

指数回撤计算与组合回撤共用同一 Peak-to-Trough 算法（`_compute_drawdowns`），归一化后的指数 bars 输入即可：

```python
# 对每个基准，在归一化后的 bars 上计算单独的回撤指标
for bm in benchmarks:
    bm["max_drawdown_pct"] = _compute_drawdowns(bm["bars"])["max_pct"]
```

---

## 6. HTML 渲染方案

### 6.1 走势主图（Section 17）+ 回撤分析图（Section 18）— Native Canvas

**改造范围（一次完成，Iter 7）**：
- 修改 `drawSimpleChart` 签名
- 更新走势图和回撤图两个调用点
- 移除 Chart.js CDN 依赖
- 添加图例和 tooltip

**改造理由**：
- `drawSimpleChart` 签名从 `(canvasId, labels, values, opts)` 变为 `(canvasId, datasets, opts)`。两个调用点（走势图 line 1444、回撤图 line 1551）必须在同一轮更新，否则过渡期的回撒图调用老签名导致参数错位。
- Chart.js CDN 移除是签名变更的自然收尾——回撤图已用 Native Canvas 绘制后 CDN 无引用。
- 合并为一次变更消除了过渡期断裂风险（原 10 轮方案中被评估为 M 级风险）。

#### 新签名

```javascript
// 改造后签名（Iter 7）
window.drawSimpleChart = function(canvasId, datasets, opts) {
    // datasets: [{label, values, color, fill, width?, dash?}, ...]
    // 兼容旧调用：当 arguments.length >= 3 且第二个参数非数组的数组时自动转换
    // 多 dataset：依次绘制，颜色不同，右上角图例
}

// 走势图调用
drawSimpleChart("historyChart", [
    {
        label: '组合净值',
        values: [100, 101.5, 102.3, ...],
        color: '#2563EB',
        fill: true
    },
    {
        label: '沪深300',
        values: [100, 100.8, 101.1, ...],
        color: '#DC2626',
        fill: false,
        dash: [4, 2]   // 虚线，与组合实线区分
    }
]);

// 回撤图调用（数据格式一致，仅 values 来源不同）
drawSimpleChart("drawdownChart", [
    {
        label: '组合回撤',
        values: [0, -1.2, -2.5, ...],
        color: '#2563EB',
        fill: true
    },
    {
        label: '沪深300 回撤',
        values: [0, -0.8, -1.5, ...],
        color: '#9CA3AF',
        fill: false,
        dash: [4, 2]   // 灰色虚线，与走势图指数线色系统一
    }
]);
```

**改造原则**：
- 向后兼容：单 dataset 旧式调用通过函数入口参数类型检测自动转换
- 无 benchmark 时不构造第二个 dataset，`drawSimpleChart` 仅绘单线
- 图例仅在 `datasets.length > 1` 时渲染
- **色板**：多基准时色板循环为 `["#DC2626"（红）, "#F59E0B"（橙）, "#10B981"（绿）]`，组合线固定 `"#2563EB"（蓝）`，色板不污染组合线颜色。第 4+ 条从色板开头重新循环。
- **回撤线样式**：指数回撒线固定灰色 `#9CA3AF`，虚线 `dash: [4, 2]`，与走势图的红色/橙色/绿色色板区分，避免走势图和回撤图中同一指数颜色不同造成混淆

### 6.2 Chart.js CDN 移除

**现状**：回撒图使用 Chart.js（CDN 加载 `cdn.jsdelivr.net/npm/chart.js`）。

**问题**：Chart.js CDN 在离线/内网环境下不可用，回撒图完全空白。走势主图（Native Canvas）无此问题。

**Iter 7 操作**：
- 移除 `<script src="...chart.js">` 行
- 移除 CDN 轮询加载逻辑（`_p_poll`、`_d_poll` 相关代码）
- 回撒图调用 `drawSimpleChart("drawdownChart", [组合回撤线, 指数回撤线])`

**离线行为对比**：

| 场景 | 当前 v0.5.5 | 改造后 |
|:-----|:-----------|:-------|
| 在线访问 | 走势图 ✓，回撒图 ✓（Chart.js CDN） | 走势图 ✓，回撒图 ✓ |
| 离线访问 | 走势图 ✓，回撒图 ✗（空白） | 走势图 ✓，回撒图 ✓ |

### 6.3 图例与 Tooltip 渲染

```javascript
// 图例（右上角色块 + 名称，仅在 datasets.length > 1 时渲染）
var legendEl = document.createElement('div');
legendEl.className = 'chart-legend';
legendEl.style.cssText = 'position:absolute;top:0;right:0;padding:8px;...';
datasets.forEach(function(ds) {
    var item = document.createElement('div');
    // <span style="background: color; width:12px; height:12px; ..."></span>
    // <span>label</span>
    legendEl.appendChild(item);
});

// Tooltip（鼠标悬停显示多值，格式 #,##0.00）
var tooltipEl = document.createElement('div');
tooltipEl.className = 'chart-tooltip';
tooltipEl.style.cssText = 'position:absolute;display:none;background:#fff;...';
// mousemove: 计算最近数据点索引 → 遍历所有 dataset 构造 N 条 <div>
// 走势图组合线显示绝对数值、指数线显示归一化值
// 回撤图组合线和指数线均显示百分比（已为 % 值）
// 格式: label: #,##0.00
```

### 6.4 Jinja2→JavaScript 模板桥接

benchmarks 数据需从 Python dict 经 Jinja2 渲染为 `drawSimpleChart` 的 `datasets` JavaScript 数组。Iter 7 的模板逻辑如下：

```javascript
// 模板渲染后的 JavaScript（Jinja2 负责展开数据）
drawSimpleChart("historyChart", [
    {
        label: '组合净值',
        values: [{% for bar in history_data.bars %}{{ bar.total_value }}{% if not loop.last %},{% endif %}{% endfor %}],
        color: '#2563EB',
        fill: true
    },
    {% for bm in history_data.benchmarks %}
    {
        label: '{{ bm.name }}',
        values: [{% for bar in bm.bars %}{{ bar.value }}{% if not loop.last %},{% endif %}{% endfor %}],
        color: ['#DC2626', '#F59E0B', '#10B981'][{{ loop.index0 }} % 3],
        fill: false,
        dash: [4, 2]
    }{% if not loop.last %},{% endif %}
    {% endfor %}
]);
```

**注意**：
- 无基准数据时 `history_data.benchmarks` 为空列表，`for` 循环不产生额外 dataset，`drawSimpleChart` 渲染单线
- 回撤图的 `datasets` 构造方式相同，仅 `values` 来源变为 `bar.drawdown_pct`，指数回撤线颜色固定 `#9CA3AF`
- 此处不新增独立模板文件，直接修改 `report_template.html` 的现有 `<script>` 块

### 6.5 data_status 集成

`report/data_status.py` 已注册消息（line 46）：

```python
"benchmark_unavailable": "业绩基准数据不可用",
```

所有基准全部获取失败时，`html_writer.py` 应当：

```python
if not benchmarks:
    data_status_history["benchmark"] = DataStatusItem(
        available=False, tier="T3",
        message=STATUS_MESSAGES["benchmark_unavailable"],
    )
```

基准部分可用时（部分成功部分失败）保持 `available=True`，`tier="T2"`，消息注明"部分基准数据不可用"。

### 6.6 Iter 7 过渡兼容性说明

```python
"""
Iter 7 是唯一涉及 HTML 模板重构的迭代，其过渡安全性依赖于以下设计：

1. drawSimpleChart 向后兼容检测：
   - 旧调用方式 drawSimpleChart(id, labels, values, opts) 传入 4 个参数，
     且第二个参数为普通数组（非数组的数组）
   - 新代码在函数入口处检查 arguments.length 和参数类型：
     if (arguments.length >= 3 && !Array.isArray(arguments[1][0])) {
         // 旧式单 dataset 调用 → 自动转换为 [{values, color, fill}]
     }
   - 因此即使过渡期存在未及时更新的调用点，drawSimpleChart 仍能正确渲染

2. 回撤图调用点在同一个 commit 内更新完毕：
   - 走势图调用（line ~1444）和回撒图调用（line ~1551）在同一轮修改中
   - 不存在"走势图已更新、回撤图等待下一轮"的过渡窗口期

3. Chart.js CDN 移除与回撤图改造在同一 commit：
   - 移除 CDN 的行和回撤图新的 drawSimpleChart 调用在同一个 commit 内
   - 不存在"CDN 已移除但回撒图仍依赖 Chart.js API"的断裂窗口

4. 回退安全性：
   - Kill-Switch（benchmark_indices={}）使走势图和回撒图回到单线状态
   - 单线状态与旧版视觉一致
   - 整体 git revert 回退全部 HTML 改动，回到 v0.5.5 完全一致
"""
```

---

## 7. Excel 输出方案

在 `excel_content_sheets.py` 的 `_write_history_sheet()` 中，在现有列之后追加基准列：

```
A 列: 日期（不变）
B 列: 组合市值（不变）
C 列: 日收益率（不变）
D 列: 回撤（不变）
--- 以下为每基准叠加 3 列 ---
E 列: 沪深300 净值（归一化）
F 列: 沪深300 日收益率
G 列: 沪深300 回撤
H 列: 标普500 净值（归一化）
I 列: 标普500 日收益率
J 列: 标普500 回撤
```

- 无基准指数时，不追加 E-J 列，向后兼容
- 百分号格式与现有 C/D 列一致
- 冻结窗格自动扩展到 J 列

---

## 8. session_cache 策略

**问题**：存在两重缓存——`fetch_index_history()` 内部的 `DataSourceRegistry.session_cache` + `portfolio_history._session_cache`。

**决策**：
- 基准指数数据**仅在** `fetch_index_history()` 层做 session_cache（C4 约束）
- `portfolio_history._session_cache` **不缓存** benchmark 数据
- 理由：
  - 同一会话中同一指数代码不会被不同持有者重复请求（指数是全组合共享的，不像每个持仓分别获取）
  - 减少内存占用（每个指数约 2-4KB，2 个指数节省可忽略，但原则是避免双重缓存）

---

## 9. 双 Provider 数据一致性

**规则**：
- **Tencent 为数据主链路**：`history_index` chain 先调 Tencent，返回非空时以此为准
- **Sina 仅做备用**：Tencent 返回空时 Fallback 到 Sina
- **数据精度一致性**：两个 provider 均返回 `{"date", "open", "close", "high", "low", "volume"}` 同构数据，归一化仅依赖 `close` 字段，精度差异不影响归一化结果

这个策略天然由 `_fetch_with_incremental_fallback()` 的优先级顺序保证，无需额外逻辑。

---

## 10. 设计约束合规矩阵

| 约束 | 内容 | 合规方案 | 违规风险 |
|:-----|:-----|:---------|:---------|
| **C1** | 代码类型判定中心化 | `code_utils` 新增 `is_index_code()` / `is_us_index_code()`。**Iter 2/3 的 `fetch_index_kline()` 内部禁止自行编写前缀判定逻辑**，必须调用 `code_utils.is_index_code()` 做入口校验。`_call_history_provider` 按 `chain_name` 字符串 dispatch（非代码类型判定），不涉及 C1 | **中**（需审查 provider 函数是否用了 `is_index_code`） |
| **C2** | 缓存统一管理 | `history_index_*` 前缀的缓存通过 `cache.set/get` 读写。注意：`_fetch_with_incremental_fallback`（`chain.py:291`）的 cache 读取硬编码 `CACHE_WEEKLY`，registry 中注册的 `cache_ttl=CACHE_MONTHLY` 仅用于元数据展示（菜单/统计），不影响缓存实际刷新频率 | 低 |
| **C3** | 缓存原子写入 | 继承 `_io.py` 的 `tempfile.mkstemp` + `os.replace` | 低 |
| **C4** | 会话级 API 复用 | `fetch_index_history` 中先查 `DataSourceRegistry.session_cache`；`report/benchmark.py` 不额外缓存 | 低 |
| **C5** | HTTP 客户端统一 | Provider 函数使用 `make_http_client()`（已有） | 无 |
| **C6** | Provider Chain 必经 | 指数历史走 `_fetch_with_incremental_fallback("history_index", ...)`，不绕过 | 低 |
| **C7** | 报告序号不可硬编码 | 指数不作为独立 section 注册，走内部数据增强 | 无 |
| **C8** | 日志统一 | 使用 `logger = logging.getLogger("invest")` | 无 |
| **C9** | LLM 模块注册 | 不涉及 LLM 模块 | 无 |
| **C14** | 渲染期数据不写模块级全局变量 | benchmark 数据通过模板 context 传递（`html_writer.py` 已通过 `render()` 传参） | 低 |
| **C11** | 测试标记强制 | 新增测试标注 `unit_providers` / `unit_fetcher` / `unit_core` / `unit_report` / `scenario_basic` | 低 |
| **C12** | 边缘测试文件隔离 | Edge 场景放 `*_edge.py`，随所属迭代提交，不堆积到最后 | 低 |
| **C13** | 测试敏感路径隔离 | 项目已有 `_isolate_sensitive_paths` fixture | 无 |

---

## 11. 风险矩阵

| 风险 | 概率 | 影响 | 等级 | 缓解 |
|:-----|:----:|:----:|:----:|:-----|
| 归一化算法起算日计算 Bug | 中 | 高 | **H** | Iter 6b 独立 revert；纯算法可 mock 测试（≥8 项正常 + 5 项 edge）；不影响指数数据获取 |
| Iter 7（drawSimpleChart + CDN 移除）单轮改动量大 | 中 | 中 | **M** | 6.6 的过渡兼容性设计（老签名自动检测）保障即使有遗漏调用点也不会断裂；Kill-Switch 可回到单线状态；测试覆盖≥18 项 |
| Tencent 指数 K 线 API 不返回数据 | 中 | 高 | **H** | Sina 为备用链路；全链路失败指数降级为空，组合走势不受影响 |
| Sina 美股指数历史 K 线格式未知 | 中 | 低 | **L** | `gb_inx` 非 6 位码通过 `_add_prefix` 不添加前缀；失败时由 Tencent 链路兜底 |
| Excel 列数超过冻结窗格范围 | 低 | 低 | **L** | 冻结窗格列号从 `D` 扩展为 `D+3N`（N=基准数），2 个基准=J 列。`openpyxl` 支持 |
| 归一化起算日极端差异（指数晚于组合 1 年以上） | 低 | 低 | **L** | 日志记录差异范围，超过 365 天 WARNING。走势图组合线正常显示，指数线从可用位置开始 |
| 用户配置大量指数（>5）导致性能问题 | 极低 | 中 | **L** | ThreadPoolExecutor 限制 `max_workers=8`（与持仓共享），指数获取不会单独耗尽线程池；config 文档建议不超过 3 个 |
| **_call_history_provider 缺少 history_index dispatch 分支** | 低 | 极高 | **H** | `chain.py:379-390` 的 if/elif 硬编码了 `history_stock` 和 `history_fund_otc`，不新增 `history_index` 分支则链式调用永远返回 `[]`。缓解：Iter 4 验收标准明确要求 dispatch 分支 mock spy 断言 |
| **days 参数错配（组合 30 天但指数只取 30 天）** | 低 | 高 | **M** | 组合默认 30 天走势，指数只取 30 天则回溯数据不足，归一化起算日无法对齐。缓解：`fetch_benchmarks` 内部用 `max(365, portfolio_days)` |
| **LLM 模块误将 benchmarks 数据用于分析** | 低 | 中 | **L** | `html_writer.py` 将 `history_data` 全量传入 context，LLM 可能将指数走势当作组合数据。缓解：告知开发者注意 `benchmarks` 字段隔离 |
| **Jinja2 模板桥接复杂（handlers_report → template → drawSimpleChart 数据管道）** | 中 | 中 | **M** | benchmarks 列表需经 Jinja2 展开为 JS 数组，若模板循环中格式错误（空值/逗号缺失），渲染完全失败。缓解：Iter 7 验收标准要求 rendered HTML 的 `data-datasets` 属性 JSON 解析成功 |
| **CACHE_WEEKLY 硬编码覆盖 CACHE_MONTHLY** | 低 | 低 | **L** | `chain.py:291` 硬编码 `CACHE_WEEKLY` 作为 cache 新鲜度阈值，registry 注册的 `CACHE_MONTHLY` 仅用于元数据展示。指数数据被按周而非按月刷新，不影响正确性，仅增少量 HTTP 请求 |

---

## 12. 技术债务

| 债务项 | 类型 | 影响面 | 处理策略 |
|:-------|:----:|:-------|:---------|
| `fetch_index_kline()` 与 `fetch_kline()` ~60% 代码重复 | **欠债** | 2 个 provider 文件 | 差异仅在类型检查一行（`is_a_share_code`），解析完全复用。长远应提取共享 kline fetch 基类，但不在此迭代范围做 |
| `report/benchmark.py` 新模块 | **零净增债务** | 1 个文件 | 职责清晰的模块拆分，比堆在 `portfolio_history.py` 更优 |
| `drawSimpleChart` 签名变更（兼容旧单参） | **零净增债务** | 1 个模板文件 | 向后兼容设计，旧单 dataset 调用无需修改 |
| Chart.js CDN 移除 | **偿还债务** | 1 个模板文件 | Iter 7 消除了离线回撤图空白的历史债务，与 drawSimpleChart 改造在同一轮完成 |
| `history_index` 是第 4 个 chain 定义 | **零净增债务** | `_DEFAULT_CHAINS` 一行 | `_DEFAULT_CHAINS` 是字典，加一个 key 天然扩展。`_HISTORY_PROVIDER_MAP` 无需变更（provider 名→模块路径映射已涵盖 tencent/sina）|
| **CACHE_WEEKLY 硬编码在 chain.py:291** | **既有债务** | 所有 chain（`history_stock`/`history_fund_otc`/`history_index`） | registry 中 `cache_ttl` 仅用于元数据展示，`_fetch_with_incremental_fallback` 的 cache 读取硬编码 `CACHE_WEEKLY`。不影响指数功能正确性，但 `CACHE_MONTHLY` 注册值无效。不在本迭代范围修复 |
| 双 provider 数据精度差异 | **零净增债务** | 无 | 归一化仅依赖 `close`，数据源切换不会影响归一化曲线（差异在 0.01 级别） |

---

## 13. 回退策略

| 场景 | 回退操作 | 影响范围 |
|:-----|:---------|:---------|
| 指数线显示错乱 | `config.json` 中 `benchmark_indices` 设为 `{}` | 走势图回到 v0.5.5 状态（单线、无图例） |
| 归一化算法 Bug（6b） | `git revert` Iter 6b 的 commit | 指数数据仍能从 6a 返回原始 bars（仅 HTML/Excel 不叠加归一化线） |
| Iter 7（drawSimpleChart+CDN）渲染 Bug | `git revert` Iter 7 的 commit；或临时 `benchmark_indices={}` Kill-Switch | Kill-Switch 使走势图和回撤图回到单线状态但不丢失数据；revert 完全回到 v0.5.5 模板 |
| Provider API 不稳定 | `git revert` Iter 2/3/4/5 | 指数获取代码回退，不影响任何持仓走势 |
| 并行获取引入异常 | `git revert` Iter 6a | 基准获取回退，组合走势不受任何影响 |
| Excel 列注入 Bug | `git revert` Iter 8 | HTML 走势图不受影响（Excel 与 HTML 渲染路径独立） |
| 全量测试失败 | 不合并 master，在 dev 修复 | 无发布风险 |

---

## 14. 测试策略

### 14.1 单元测试（88+ 项，按迭代归属）

| 迭代 | 文件 | 测试项数 | 范围 |
|:----:|:-----|:--------:|:-----|
| 1 | `test_code_utils.py` | 6+ | `is_index_code()`、`is_us_index_code()`、config 校验 |
| 2 | `test_tencent.py` + `test_tencent_edge.py` | 6+3 | Tencent 指数 K 线正常/空/超时/格式错误 |
| 3 | `test_sina.py` + `test_sina_edge.py` | 6+3 | Sina 指数 K 线正常/空/超时/格式错误 |
| 4 | `test_chain.py` | 12+ | 双链路/全失败/增量合并/重叠刷新/dispatch 分支正确性/`history_stock` 不受影响/cache key 格式（含 edge） |
| 5 | `test_fetcher_index.py` | 6+ | session_cache/失败/不支持代码（含 edge） |
| 6a | `test_benchmark.py` | 6+ | 并行获取/部分失败/全失败/config 空/集成验证 |
| 6b | `test_benchmark.py` + `test_benchmark_edge.py` | 8+5 | 同起算日/指数晚于组合/NaN 过滤/LOCF gap 填充/极短指数/大量基准 |
| 7 | `test_html_template.py` + `test_html_report_structure.py` | 18+ | 多 dataset 渲染/色板循环/图例/tooltip/回撤虚线/打印/回退/旧签名兼容/CDN 已移除/离线可用（原 Iter 7+8 测试项合并） |
| 8 | `test_excel_report_structure.py` | 6+ | 列数/列标题/格式/冻结窗格/空 config（含 edge） |

### 14.2 场景测试（3+ 项，Iter 6a 提交）

| 场景 | 文件 | 说明 |
|:-----|:-----|:-----|
| S34a: 基准有数据 | `test_integration.py`（1 项）| 完整的持仓 + 指数数据，验证 HTML context 含 benchmarks |
| S34b: 基准 config 空 | `test_integration.py`（1 项）| 验证 benchmarks 为空数组 |
| S34c: 基准全部失败 | `test_integration.py`（1 项）| 验证 benchmarks 为空数组 + 组合走势不变 |

### 14.3 人工验证（Iter 9 提 PR 前）

- 打开 HTML 报告，确认走势图双线 + 图例 + tooltip 正常
- 断开网络，打开同一 HTML 报告，确认走势图和回撤图均正常显示（不再依赖 CDN）
- 打开 Excel，确认基准列存在且格式正确
- 删除 `benchmark_indices` 配置，确认报告回到 v0.5.5 状态
