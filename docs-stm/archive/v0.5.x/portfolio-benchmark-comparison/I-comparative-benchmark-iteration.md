# 组合历史走势与基准指数比对 — 迭代计划

> ✅ **已完成**（v0.5.6）
>
> 对应 plan.md [P3] I，9 轮迭代
>
> 创建日期：2026-07-15 | 最后更新：2026-07-16 | 完成日期：2026-07-14

---

## 总体策略

- **Feature Flag**：`config.json` 的 `history.benchmark_indices` 键作为 Kill Switch，缺失时功能完全不生效，现有行为零影响
- **回退安全**：每轮独立 commit，可单独 `git revert`
- **迭代拓扑**：基础设施 → Provider → Chain → 计算 → 渲染 → 收尾
- **版本目标**：v0.6.0（新功能版本）
- **Edge 就近**：每轮 edge 测试随本轮功能一起提交，不在最后一轮集中堆积

---

## 迭代 1/9 — code_utils 判定函数 + Config 默认值

**目标**：在 code_utils.py 注册指数代码判定规则，定义 config 默认结构。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/code_utils.py` | 新增 `is_index_code(code)`、`is_us_index_code(code)`、`get_index_exchange_prefix(code)` |
| `src/python/config/_config_defaults.py` | 新增 `history.benchmark_indices` 默认值 `{"sh000300": "沪深300", "gb_inx": "标普500"}` |
| `src/python/config/_core.py` | 在 `_validate_config_structure()` 中增加 `benchmark_indices` 结构校验（key 为 6-8 字符代码字符串，value 为名称字符串） |
| `src/python/handlers_report.py` | 从 `history.benchmark_indices` 读取配置，传入 `PortfolioHistoryCalculator` 构造函数（与 `coverage_threshold` 同一模式） |
| `src/test/unit/core/test_code_utils.py` | 新增 `test_is_index_code()` 等单元测试（≥6 项） |

### 验收标准

1. `is_index_code("sh000300")` → `True`
2. `is_index_code("600900")` → `False`
3. `is_us_index_code("gb_inx")` → `True`
4. `is_us_index_code("sh000300")` → `False`
5. 配置缺失 `benchmark_indices` 时 `get_config()` 返回默认值 `{"sh000300": "沪深300", "gb_inx": "标普500"}`
6. 配置含非法 key 类型（如 `{"1234567": "测试"}` key 长度 > 8）时 `_validate_config_structure` 打印 WARNING 日志但 `get_config()` 不崩溃
7. 新增函数 `get_index_exchange_prefix("sh000300")` 返回 `"sh"`，`get_index_exchange_prefix("gb_inx")` 返回空字符串 `""`
8. `handlers_report.py` 中 `PortfolioHistoryCalculator(coverage_threshold=_coverage, benchmark_indices=_indices)` 调用不抛异常
9. `python -m pytest src/test/unit/core/test_code_utils.py -x -q` 通过（预计耗时 < 5s）

---

## 迭代 2/9 — Tencent 指数历史 K 线 Provider

**目标**：在 `tencent.py` 新增 `fetch_index_kline()`，供指数历史日线获取。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/providers/tencent.py` | 新增 `fetch_index_kline(code, days, start_from)`，跳过 `is_a_share_code` 检查，复用 `_parse_kline_response()` 解析逻辑；入口通过 `code_utils.is_index_code()` 校验 |
| `src/test/unit/providers/test_tencent.py` | 新增 `test_fetch_index_kline_normal`、`test_fetch_index_kline_empty`、`test_fetch_index_kline_timeout`（≥6 项） |
| `src/test/unit/providers/test_tencent_edge.py` | 新增 edge 场景（超时、非法格式等，≥3 项），与本轮普通测试同时提交 |

### 验收标准

1. `tencent.fetch_index_kline("sh000300", 30)` 在 mock 数据下返回 `list[dict]`，每条记录的 key 集合等于 `{"date", "open", "close", "high", "low", "volume"}`，所有数值字段不为 `None`
2. `tencent.fetch_index_kline("gb_inx", 30)` 在 mock 数据下返回同样 schema 的列表
3. `fetch_index_kline` 函数入口通过 `code_utils.is_index_code(code)` 校验传入代码（mock spy 断言函数体调用了 `is_index_code`），而非自行硬编码前缀匹配
4. mock 远程返回 `[]` 时函数返回 `[]`
5. mock `httpx.TimeoutException` 时函数返回 `[]`
6. `_add_prefix("sh000300")` 返回 `"sh000300"`（不 double-prefix）
7. `_add_prefix("gb_inx")` 返回 `"gb_inx"`（非 6 位码原样返回）
8. 所有测试方法标注 `@pytest.mark.unit_providers`
9. edge 测试文件命名为 `test_tencent_edge.py`，且 pytest 收集期不触发 `"边缘测试不得与普通测试混搭"` validation error
10. `python -m pytest src/test/unit/providers/test_tencent.py src/test/unit/providers/test_tencent_edge.py -x -q` 通过（预计耗时 < 10s）

---

## 迭代 3/9 — Sina 指数历史 K 线 Provider + 共享解析层

**目标**：在 `sina.py` 新增 `fetch_index_kline()`，完成双链路 Provider 覆盖。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/providers/sina.py` | 新增 `fetch_index_kline(code, days, start_from)`，跳过类型检查；入口通过 `code_utils.is_index_code()` 校验 |
| `src/test/unit/providers/test_sina.py` | 新增 mock 测试（≥6 项） |
| `src/test/unit/providers/test_sina_edge.py` | 新增 edge 场景（≥3 项），与本轮普通测试同时提交 |

### 验收标准

1. `sina.fetch_index_kline("sh000300", 30)` 在 mock 数据下返回 `list[dict]`，每条记录 key 集合等于 `{"date", "open", "close", "high", "low", "volume"}`，所有数值字段 `isinstance(v, (int, float))`
2. `sina.fetch_index_kline("gb_inx", 30)` 在 mock 数据下返回同样 schema 的列表
3. `fetch_index_kline` 函数入口通过 `code_utils.is_index_code(code)` 校验传入代码（mock spy 断言），而非自行硬编码前缀匹配
4. mock Tencent 返回 `[]` 且 Sina 返回合法数据时，fetcher chain 选择 Sina 数据（验证 chain 内部先调 tencent 再 fallback 到 sina 的日志顺序）
5. edge：`sina.fetch_index_kline("invalid_code", 30)` 返回 `[]`
6. edge：mock 超时返回 `[]`
7. edge：mock 非法 JSON 响应返回 `[]`
8. 测试标注 `@pytest.mark.unit_providers`
9. `python -m pytest src/test/unit/providers/test_sina.py src/test/unit/providers/test_sina_edge.py -x -q` 通过（预计耗时 < 10s）

---

## 迭代 4/9 — history_index Chain 定义 + Registry 注册

**目标**：在 `chain.py` 注册 `history_index` 链路，在 `registry.py` 注册数据模块定义。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/fetcher/chain.py` | `_DEFAULT_CHAINS` 新增 `"history_index": ["tencent", "sina"]`；`_call_history_provider()` 新增 `history_index` dispatch 分支 → 调用 `fetch_index_kline(code, days, start_from)`。**`_HISTORY_PROVIDER_MAP` 和 `_get_chain()` 无需改动**——前者是 provider 名→模块路径映射（已有 tencent/sina 条目），后者已是通用函数 |
| `src/python/registry.py` | 新增 `DataModuleDef("指数历史日线", "history_index", ...)`，`cache_prefixes=("history_index_",)`，`cache_ttl=CACHE_MONTHLY` |
| `src/test/unit/fetcher/test_chain.py` | 新增 ≥12 项测试（含 edge：全链路异常、增量合并重叠边界、dispatch 分支正确性、`history_stock` 不受 `history_index` 影响） |

### 验收标准

1. `_fetch_with_incremental_fallback("history_index", "sh000300", 365)` 先调用 Tencent 成功时直接返回、不调用 Sina（mock spy 断言 sina.fetch_index_kline 未被触发）
2. mock Tencent 返回 `[]` 时自动 fallback 到 Sina，最终返回 Sina 数据（断言链式调用日志）
3. `_call_history_provider("tencent", "history_index", "sh000300", 365, None)` 正确调用 `tencent.fetch_index_kline("sh000300", days=365, start_from=None)`（mock spy 断言调用参数精确匹配）
4. `_call_history_provider("tencent", "history_stock", "600900", 30, None)` 仍调用 `tencent.fetch_kline("600900", days=30, start_from=None)`（`history_stock` 分支不受影响）
5. 双 Provider 均返回 `[]` 时返回 `[]`
6. 全链路抛出异常时返回 `[]`，不抛出任何异常
7. Registry 中 `data_modules` 列表包含一条 `DataModuleDef`，其 `display_name == "指数历史日线"` 且 `key == "history_index"`
8. cache key 实际格式为 `history_history_index_sh000300`（`chain.py:290` 固定前缀 `history_` + chain_name + `_` + code）
9. 增量合并：新数据含 3 天与旧缓存重叠时，合并后结果中重叠部分使用新数据（日期精确匹配断言）
10. 增量合并：新旧数据各贡献不同日期段，合并后日期连续无缺失（排序后相邻日期差 ≤ 5 个日历日，覆盖周末/节假日）
11. `python -m pytest src/test/unit/fetcher/test_chain.py -x -q -k "history_index or benchmark or dispatch"` 通过（预计耗时 < 15s）

---

## 迭代 5/9 — fetcher/index.py 新增 fetch_index_history()

**目标**：在 `fetcher/index.py` 中实现指数历史日线获取入口，由 `portfolio_history.py` 调用。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/fetcher/index.py` | 新增 `fetch_index_history(code, days=365)` → 调用 `chain._fetch_with_incremental_fallback("history_index", ...)`；新增 `_index_history_cache_key()` |
| `src/python/fetcher/index.py` | 缓存校验层：优先查 `DataSourceRegistry.session_cache`（C4 约束） |
| `src/test/unit/fetcher/test_fetcher_index.py` | 新增 mock 测试（≥6 项，含 edge：空代码、全失败） |

### 验收标准

1. `fetch_index_history("sh000300", 365)` 返回 `[{"date": str, "close": float, "open": float, "high": float, "low": float, "volume": int}, ...]`（mock chain 返回数据，验证条目 ≥ 1）
2. 同一会话中两次调用 `fetch_index_history("sh000300", 365)`，第二次 mock spy 断言 chain 层未被调用（命中 session_cache）
3. 不支持的代码（如 `""`）返回 `None`
4. 全链路 mock 失败时返回 `[]`，调用方不捕获到异常
5. cache key 格式为 `history_index_sh000300`
6. `python -m pytest src/test/unit/fetcher/test_fetcher_index.py -x -q` 通过（预计耗时 < 10s）

---

## 迭代 6a/9 — report/benchmark.py 提取 + 并行获取集成

**目标**：新建 `report/benchmark.py` 模块封装基准指数数据获取逻辑，集成到 `get_combined_timeseries()` 的 ThreadPoolExecutor；不引入归一化。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/report/benchmark.py` | **新建模块**，export `fetch_benchmarks(indices_config, days)` — 对每个基准代码调用 `fetch_index_history()`，返回原始数据列表 |
| `src/python/report/portfolio_history.py` | `PortfolioHistoryCalculator.__init__` 新增 `benchmark_indices` 参数（与 `coverage_threshold` 一致）；修改 `get_combined_timeseries()` 将 benchmark 获取任务提交到已有的 ThreadPoolExecutor 中（**共用同一并行池**，不增加串行延迟）；返回值新增 `benchmarks` 字段 |
| `src/python/report/benchmark.py` | 只依赖 `fetch_index_history()` 的 session_cache，`portfolio_history._session_cache` 不缓存 benchmark 数据（避免双重缓存） |
| `src/test/unit/report/test_benchmark.py` | 新增 ≥6 项测试（`test_fetch_benchmarks_normal`、`test_fetch_benchmarks_empty_config`、`test_fetch_benchmarks_partial_failure`、`test_fetch_benchmarks_all_failure`、`test_benchmarks_integrated_in_get_combined`） |
| `src/test/scenario/basic/test_integration.py` | 新增 S34 场景（≥1 项：验证 `history_data` 含原始 benchmark 数据） |

### 验收标准

1. `fetch_benchmarks({"sh000300": "沪深300"}, 365)` 返回 `[{"code": "sh000300", "name": "沪深300", "bars": [...], "status": "ok"}]`
2. `benchmark_indices` 为 `{}` 时 `fetch_benchmarks({}, ...)` 返回 `[]`
3. 部分指数失败时返回结果数 = 成功代码数，失败的代码不出现在返回值中
4. `get_combined_timeseries()` 返回值 `keys()` 包含 `"benchmarks"`，且 benchmark 获取与持仓获取在同一个 ThreadPoolExecutor 中完成（日志校验并行性）
5. 加入 benchmark 获取后，`get_combined_timeseries()` 总耗时 < 无 benchmark 时耗时 + 100ms（并行不串行）
6. `fetch_benchmarks({"sh000300": "沪深300"}, 30)` 内部调用 `fetch_index_history("sh000300", max(365, 30))`（最少获取 365 天以确保归一化需要；mock spy 断言实际调用参数）
7. `get_combined_timeseries(holdings, days=30)` 有基准时，`benchmarks[0]["bars"]` 长度 ≥ 指数 365 天的数据量（非 30 天）
8. `python -m pytest src/test/unit/report/test_benchmark.py -x -q` 通过（预计耗时 < 10s）

---

## 迭代 6b/9 — 归一化算法 + Edge 测试

**目标**：在 `benchmark.py` 中实现起算日对齐 + 100 基点归一化算法（纯计算，无 IO）。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/report/benchmark.py` | 新增 `normalize_benchmarks(bars, benchmark_bars_list, benchmark_codes, benchmark_names)` — 三段式对齐 + 归一化；新增 `_compute_benchmark_drawdowns()` 指标计算 |
| `src/test/unit/report/test_benchmark.py` | 新增 ≥8 项测试（`test_normalize_same_start`、`test_normalize_index_later`、`test_normalize_empty_bars`、`test_normalize_multi_index`、`test_normalize_all_nan_filter`、`test_benchmark_drawdown`） |
| `src/test/unit/report/test_benchmark_edge.py` | 新增 edge 场景（≥5 项：指数数据短于组合 → 从指数首日对齐、仅配置不存在代码 → 空数组、指数全是 NaN → 过滤后仅有效段、5 个基准并行不超限、组合无交易日与指数周末对齐）|

### 验收标准

1. 同起算日时 `normalize_benchmarks(组合bars, [指数bars], ["sh000300"], ["沪深300"])` 结果中 `bars[0]["value"] == 100.0`
2. 首条指数日期晚于组合起算日时，`bars[0]["date"]` 等于指数首条日期，`value == 100.0`
3. 空输入：`normalize_benchmarks(...)` 任一参数为空列表时返回 `[]`
4. 节假日 gap 填充：组合日期集合中基准指数缺席的日期，使用前值填充（LOCF），最终两个 `values` 数组长度相等，索引一一对应
5. 多指数：输入 2 个指数，返回 2 个 benchmark 条目，互不污染
6. 指数 bars 中混有 `NaN` close 值时自动跳过该日（不传参到归一化）
7. 指数数据短于组合时（仅 60 天 vs 组合 365 天），指数线从指数首日起绘制，组合线不变
8. `python -m pytest src/test/unit/report/test_benchmark.py src/test/unit/report/test_benchmark_edge.py -x -q` 通过（预计耗时 < 15s）

---

## 迭代 7/9 — HTML 全量迁移：drawSimpleChart 多 dataset + Chart.js 移除

**目标**：一次完成走势图和回撤图的所有 HTML 渲染改造：
- 重写 `drawSimpleChart()` 支持多 dataset
- 走势图和回撤图两个调用点全部使用新签名
- 去除 Chart.js CDN 依赖
- 添加图例和 tooltip 多值显示

**设计依据**：`drawSimpleChart` 签名从 `(canvasId, labels, values, opts)` 变为 `(canvasId, datasets, opts)` 后，**两个调用点必须在同一轮更新**，否则回撤图在过渡期调用老签名导致参数错位。Iter 8（Chart.js 迁移）本质上是同一变化的收尾——移除 CDN = 签名变更完成后自然清理。合并在 Iter 7 消除过渡期断裂风险。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/tmpl/report_template.html` | 重写 `drawSimpleChart()` 为 `(canvasId, datasets, opts)`；兼容旧 `(canvasId, labels, values, opts)` 单 dataset 调用（参数类型检测 → 自动转换）；定义色板 `["#DC2626", "#F59E0B", "#10B981"]`；新增图例（右上角色块+名称）和 tooltip 多值显示 |
| `src/python/tmpl/report_template.html` | **走势图调用点**（line 1444）：`drawSimpleChart('portfolioChart', labels, values, {...})` → `drawSimpleChart('portfolioChart', datasets=[{label, values, color, fill}, ...])` |
| `src/python/tmpl/report_template.html` | **回撤图调用点**（line 1551）：`drawSimpleChart('drawdownChart', labels, drawdowns, {...})` → `drawSimpleChart('drawdownChart', datasets=[组合回撤dataset, 指数回撤dataset])` |
| `src/python/tmpl/report_template.html` | 移除 Chart.js CDN `<script src="...">` 行及其轮询加载逻辑（`_p_poll`、`_d_poll`） |
| `src/python/report/html_writer.py` | 已有 `history_data` 包含 `benchmarks`（来自 Iter 6a），通过 context 透传到模板 |
| `src/test/unit/report/test_html_report_structure.py` | 新增 ≥8 项测试（走势图 canvas 多 dataset、回撤图 canvas 多 dataset、CDN 不再加载、打印样式、无基准回退） |
| `src/test/unit/report/test_html_template.py` | 新增 `TestDrawSimpleChartMultiDataset` ≥15 项（旧签名兼容、图例渲染、tooltip 双值、色板循环、回撤虚线、离线可用、CDN 已移除） |

### 验收标准

1. 调用 `drawSimpleChart('c', [{label, values, color, fill}])` 与新签名等价于旧 `drawSimpleChart('c', labels, values, {lineColor, fillColor})`（宽度/高度/数据长度一致，参数类型自动检测）
2. 有基准时渲染后的 HTML `#historyChart` canvas `data-datasets` JSON 解析后 `length >= 2`
3. 无基准数据时 `data-datasets` 解析后 `length == 1`
4. 配置 3 个基准时，三条指数线的 `color` 依次为 `"#DC2626"`、`"#F59E0B"`、`"#10B981"`（第 4+ 条循环），组合线固定 `"#2563EB"`
5. 图例 `.chart-legend` 元素存在，`innerText` 含配置中指定的基准名称（如"沪深300"）
6. tooltip 容器 `.chart-tooltip` 渲染 N 条 `<div>`，走势图组合线显示绝对数值、指数线显示归一化值（格式 `#,##0.00`），回撤图均显示百分比
7. `#drawdownChart` canvas 有基准时 `data-datasets[1].dash == [4, 2]` 且 `color == "#9CA3AF"`
8. 渲染后 HTML 中 `grep "<script.*chart.js"` 返回空（Chart.js CDN 不再加载）
9. 离线打开生成的 HTML 报告，走势图和回撤图均渲染正常（`data-datasets` 非空，JS 无报错）
10. 打印媒体中 `#historyChart` 和 `#drawdownChart` 的 `display != "none"`
11. `python -m pytest src/test/unit/report/test_html_template.py src/test/unit/report/test_html_report_structure.py -x -q -k "MultiDataset or legend or tooltip or benchmark or drawdown or cdn or offline or single"` 通过（预计耗时 < 15s）

---

## 迭代 8/9 — Excel 基准指数列

**目标**：Excel 历史走势页签新增基准指数列。

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/report/excel_content_sheets.py` | 在写入 history sheet 的循环中，每行新增基准指数列（指数归一化值、指数日收益、指数回撤）|
| `src/test/unit/report/test_excel_report_structure.py` | 验证新增列存在性 + 列顺序 + 空值处理（≥6 项，含 edge：配置空、大量基准超列宽、格式一致性）|

### 验收标准

1. 配置 2 个基准时，`wb["历史走势"].max_column` 较无基准时多出 `2 × 3 = 6` 列
2. 新列标题依次为 `["沪深300 净值", "沪深300 日收益率", "沪深300 回撤", "标普500 净值", "标普500 日收益率", "标普500 回撤"]`
3. `benchmark_indices` 为 `{}` 时 sheet 列数与 v0.5.5 一致（无新增列）
4. 日收益率列的 `number_format` 包含 `%`（如 `"0.00%"`），指数净值列的 `number_format` 为 `"#,##0.000"`
5. `ws.freeze_panes` 从 `"D2"` 变为 `f"{openpyxl.utils.get_column_letter(4+3*N)}2"`（N=基准数量）
6. `python -m pytest src/test/unit/report/test_excel_report_structure.py -x -q -k "benchmark"` 通过（预计耗时 < 10s）

---

## 迭代 9/9 — 全量门禁 + 文档 + 版本发布

**目标**：全量回归+verify 门禁通过，版本号更新至 v0.5.6，文档同步。

> ✅ **已完成**（v0.5.6 发布，实际版本号因历史归档节奏使用 v0.5.6 而非原计划的 v0.6.0）

### 改动清单

| 文件 | 改动 |
|:-----|:-----|
| `src/python/constants.py` | `APP_VERSION = "0.5.5"` → `"0.5.6"`；运行 `python scripts/check-version-consistency.py` 并按 [ERR] 同步其余文件 |
| `docs-stm/managements/changelog.md` | [Unreleased] 记录功能条目 |
| `docs-stm/managements/plan.md` | [P3] I 标记为"已完成 ✅" |
| `docs-stm/manuals/how-to-config.md` | 新增 `history.benchmark_indices` 配置说明（key-value 格式、默认值、建议不超过 3 个）|
| `README.md` 等 | 版本号同步（check-version-consistency.py 自动覆盖） |

### 验收标准（全部 ✅ 已完成）

1. ✅ `python scripts/test_runner.py --mode regression` 266 passed
2. ✅ `python scripts/test_runner.py --mode all` 全部通过
3. ✅ 人工验证：HTML 走势图/回撤图双线渲染正常，含图例 + tooltip
4. ✅ 人工验证：Excel 基准列存在且格式正确
5. ✅ 版本号一致：`check-version-consistency.py` 全部 [OK]
6. ✅ `git tag v0.5.6` 打标签并推送
7. ✅ `how-to-config.md` 包含 `history.benchmark_indices` 配置说明
8. ✅ `changelog.md` [Unreleased] 已记录本功能
