# 实施 plan-2 / plan-3 / plan-9（总体架构视角）

## Context（背景）

已完成「HTML 报告每个章节底部回到顶部链接」（上一任务）。本任务实施 `docs-stm/managements/plan.md` 中的三个待办：

- **plan-2 持仓相关性矩阵** — 新增报告模块，计算各品种间收益率相关系数热力图，识别"伪分散"
- **plan-3 最大回撤 + 净值曲线增强** — 在既有 `drawdown_analysis` 模块（type=history）内新增回撤事件/恢复耗时明细
- **plan-9 首次运行引导** — 首次运行检测缺失资源并交互式引导

实施必须从**整体技术架构**出发，遵循 `technical.md` 的 `## 架构设计约束`（C1~C19 表格）与 `## 概要设计--核心架构决策`（1.4.1~1.4.5）。**plan-7 因子暴露（factor_exposure）是本次三任务的架构模板**——它已完整走通「analysis 纯计算 → orchestrator 编排 → C7 注册 → C19 pipeline_data → HTML/Excel 双层可见性 → 降级治理」全链路，新模块按同一范式接入。

---

## 总体设计原则（先决约束，贯穿三任务）

1. **单向依赖**：`analysis/` 层纯 pandas/numpy 计算，不导入 `report/`；`report/` 可导入 `analysis/`。新计算模块一律放 `src/python/analysis/`。
2. **双层可见性**：`section_visible = board_enabled(sec.type) AND data_available(sec.data_flag)`。新模块在 `html_writer._compute_section_visibility` 与 `excel_sheet_factory.create_sheets` 两侧同步扩展。
3. **C19 pipeline_data Schema 契约**：新数据键必须在 `_PIPELINE_DATA_KNOWN_KEYS` 预定义；数据结构进 `technical.md` 附录 H。
4. **§1.4.5 数据降级治理**：数据不足（`insufficient`，<60 交易日）≠ 数据源故障（`source_failed`）。两者均渲染为 `available=False`，但 UI 文案不同，**不走 DegradationTracker**。
5. **C14 渲染期数据**：HTML 图表/矩阵数据一律经模板 `render()` context 传递，不写 `_ENV.globals`。
6. **C1/C6**：品种链路选择经 `core/code_utils.py` 判定，历史数据一律走 `fetch_with_incremental_fallback`（复用 `orchestrator._fetch_holding_bars`）。
7. **LLM mock 强制 + 单例重置 + 路径隔离**：新增测试遵循 conftest 既有隔离约定。
8. **新增模块 key 命名**：章节 key 用 `correlation_analysis`，data_flag 用 `correlation_data`，与 `factor_exposure`/`factor_exposure_data` 同构。

---

## plan-2 持仓相关性矩阵

### 2.1 纯计算层 — 新建 `src/python/analysis/correlation.py`

镜像 `factor_exposure.py` 的 `unavailable_result` + 纯计算结构。**scipy/statsmodels 均未安装**（已验证），显著性用 `_math_utils._t_cdf` / `_t_critical_95` 手算（`factor_exposure._ols_regression` 同款方式）。

常量：
- `DEFAULT_WINDOW = 60`（计算窗口，60 交易日 ≈ 3 个月）
- `MIN_SAMPLES = 60`（对齐后有效样本下限）
- `MIN_HOLDINGS = 2`（<2 只有效持仓 → insufficient）
- `FETCH_DAYS = 90`（拉取条数，预留对齐/dropna 损耗，同 factor_exposure `_days=90`）

对外函数：
- `unavailable_result(status, sample_count=0, insufficient_codes=None)` → C19 字典 `available=False`
- `compute_correlation_matrix(returns_by_code, names_by_code, window=DEFAULT_WINDOW, min_samples=MIN_SAMPLES)` → C19 字典：
  - 按日期对齐各品种日收益序列，逐对取尾部 `window` 重叠样本
  - 每对：Pearson r + 双侧 p-value（`t = r·sqrt((n-2)/(1-r²))`，`p = 2·(1-_t_cdf(|t|, n-2))`），`p<0.05` → `significant=True`
  - 重叠样本 < `min_samples` 的 pair → 矩阵格为 `None`（灰色 N/A），代码进 `insufficient_codes`
  - 输出 `matrix`（N×N 下三角，其余为 None）、`pairs`（降序）、`codes`/`names`

C19 契约（进入 technical.md 附录 H）：
```json
{
  "available": bool, "status": "ok"|"insufficient"|"source_failed",
  "window": 60, "sample_count": int,
  "codes": ["...", ...], "names": {"code": "name"},
  "matrix": [[r|None, ...], ...],
  "pairs": [{"code_a","name_a","code_b","name_b","pearson","p_value","significant","samples"}],
  "insufficient_codes": ["..."], "note": ""
}
```

### 2.2 编排层 — `src/python/report/orchestrator.py`

- 新增 `compute_correlation_data(holdings, config, reporter)`，**完整镜像 `compute_factor_exposure_data`（L183）**：
  1. `if not is_enable_fund_deep_analysis(config): return None`（board 门）
  2. `ThreadPoolExecutor(max_workers=min(6, n))` 并行 `_fetch_holding_bars(h.code, h.name, FETCH_DAYS)`（复用 L142，天然满足 C1/C6）
  3. 全空 → `unavailable_result("source_failed")`；有效持仓 < MIN_HOLDINGS → `unavailable_result("insufficient")`
  4. 用 `factor_exposure.klines_to_returns` 转收益序列 → 纯计算 `compute_correlation_matrix`
  5. `except Exception` → `unavailable_result("source_failed")`（C8 日志）
- `prepare_report_data`（L54）中调用，prep 字典新增 `"correlation_data"` 键。

### 2.3 注册层 — `src/python/core/registry.py`

- `_REPORT_SECTION_DEFAULT`（L499）在 `factor_exposure`（#10）**之后插入**：
  `{"key": "correlation_analysis", "name": "持仓相关性矩阵", "number": 11, "type": "b_series", "data_flag": "correlation_data"}`
  → 后续模块顺延 +1（news_correlation→12 … llm_usage→20），总模块数 **19→20**。
- `_REPORT_SHEET_NAMES`（L361）新增 `"correlation_analysis": "持仓相关性矩阵"`；**顺带修复已知缺陷**：补 `"factor_exposure": "因子暴露分析"`（当前缺失导致页签标题显示 "10. factor_exposure"）。

### 2.4 pipeline 注入 — `src/python/report/_report_generation.py` + `pipeline_data_builder.py`

- `_generate_report_full`（L588 旁）增加 `pipeline_data["correlation_data"] = prep.get("correlation_data")`
- `_generate_full_html_report` 增加 `correlation_data` 参数 → 透传 `write_html_report`
- `pipeline_data_builder.py`：`_PIPELINE_DATA_KNOWN_KEYS` 加 `"correlation_data"`；`_PIPELINE_DATA_TYPE_MAP` 加 `"correlation_data": dict`

### 2.5 HTML — `src/python/report/html_writer.py` + `tmpl/report_template.html`

- `_compute_section_visibility`（L80）加 `correlation_data` 参数，`data_flags["correlation_data"] = correlation_data is not None`
- `_render_template`（L223）/`write_html_report`（L345）加 `correlation_data` kwarg → render context（C14）
- 模板新增 section 块（仿 factor_exposure 块 L1322-1409）：
  - `{% if section_visible("correlation_analysis") %}` → `.section` + `style="order: {{ section_numbers['correlation_analysis'] }}"`
  - `available=True`：N×N **下三角热力表格**（复用 `.heatmap-matrix` 样式，见 fund_overlap L1097），配色：`r>0` 红渐变 / `r<0` 蓝渐变 / `p>=0.05` 白 / `None` 灰 N/A；附 legend + 配对明细表（降序）+ 数据不足品种名单
  - `available=False`：按 `status=="source_failed"` 与 `数据不足` 分支显示占位（§1.4.5）
  - 底部 `{{ render_back_to_top() }}`

### 2.6 Excel — 新建 `src/python/report/correlation_sheet.py`

- `write_correlation_sheet(ws, correlation_data, ...)`：标题行（`get_report_section_number` + `get_report_sheet_name`）、热力矩阵（openpyxl `PatternFill` 条件配色）、配对明细表、不可用时 `STATUS_MESSAGES["correlation_unavailable"]` 占位
- `excel_module_loader.py`（L155 旁）注册；`excel_fund_deep_analysis.write_fund_deep_analysis_sheets`（L46）加 `correlation_data` 参数并调用
- `excel_generator.py`（L268 旁）：`write_fund_deep_analysis_sheets(..., correlation_data=(pipeline_data or {}).get("correlation_data"))`
- `data_status.py` `STATUS_MESSAGES`（L71）加 `"correlation_unavailable": "持仓相关性数据暂不可用"`

### 2.7 依赖 scipy 检查
已确认 `.venv` **无 scipy/statsmodels** → 一律用 `_math_utils` 手算，不新增依赖。

---

## plan-3 最大回撤 + 净值曲线增强

### 3.1 纯计算层 — 新建 `src/python/analysis/drawdown_events.py`

纯函数（不依赖 report/）：
- `extract_drawdown_events(bars, min_depth_pct=5.0, max_events=5)` → `list[dict]`：
  - 输入：`bars`（`[{date, total_value, drawdown_pct, ...}]`，来自 `get_combined_timeseries`）
  - 扫描峰值→谷底→恢复：跟踪 running peak；跌破峰值进入回撤，至回到前峰恢复；**合并连续未恢复区间**
  - 每事件输出 `{peak_date, trough_date, recovery_date, drawdown_pct, duration_days, recovered}`
- `compute_recovery_times(events)` → `list[dict]`：`{start_date, end_date, days}`（trough→recovery）
- `MIN_SPAN = 60` 常量（<60 交易日 → `data_sufficient=False`）

### 3.2 数据加工 — `src/python/report/portfolio_history.py`

- `get_combined_timeseries`（L142）返回字典**新增键**（设计文档 plan-3 §C19）：
  - `"drawdown_events"`：调 `extract_drawdown_events(bars)`
  - `"recovery_times"`：调 `compute_recovery_times(drawdown_events)`
  - `"drawdown_available"`：`len(bars) >= MIN_SPAN`（§1.4.5 数据不足标记）
- **无需改注册表**（drawdown_analysis 已注册 type=history，#17）。history_data 已直达 HTML/Excel 两侧，无需新参数线程。

### 3.3 HTML 增强 — `report_template.html` drawdown_analysis 块（L1817-1929）

- 新增**回撤明细表格**：`{% if history_data.drawdown_events %}` → 表头 序号/起峰日/最深日/恢复日/最大回撤/持续天数/恢复耗时/是否已恢复；`recovery_date` 为空显示 "未恢复"
- summary-grid 增补「当前是否已恢复」卡片 + 最近一次恢复耗时
- **数据不足占位**：`{% elif history_data and not history_data.get("drawdown_available") %}` → §1.4.5 占位文案（与现有 `status=="unavailable"` 占位区分）
- 底部 `{{ render_back_to_top() }}` 保持

> 图表阴影标注：**已确认（用户采纳建议）**——plan-1（Chart.js 双轴图迁移）不在本任务范围。按设计文档回退条款，本任务**以明细表格为交付主体**，不修改 `drawSimpleChart` 渲染逻辑（它是多图共享的 Canvas 绘图函数，改动回归风险高；阴影/水印留待 plan-1 用 Chart.js annotation 插件原生实现）。

### 3.4 Excel 增强 — `src/python/report/excel_generator.py`

- `_write_drawdown_analysis_sheet`（L100）在指标矩阵下方追加**回撤明细表**：列 = 序号/起峰日/最深日/恢复日/幅度/持续天数/恢复耗时(天)/当前状态；`drawdown_events` 为空时写占位行

---

## plan-9 首次运行引导

### 4.1 新建 `src/python/startup_wizard.py`（镜像 `report/privacy_notice.py` 范式）

- 配置标记键 `_startup_wizard_shown`（同 `_privacy_notice_shown`），`is_first_run()` / `mark_wizard_shown()` / `show_startup_wizard_if_needed()`
- 检测函数 `_detect_startup_state(config)` → dict：`holdings_ok`（`holdings_dir` 下存在 xlsx，经 `reader.list_xlsx_files`）、`llm_key_ok`（`llm_key.json` 存在 **或** `llm_providers.json` 有 providers，读取复用 `_load_llm_providers`/`get_llm_config`）、`llm_degraded`（provider=claude 但无 key）
- 交互式引导流程（TUI 内执行，仿隐私提示边框）：
  ```
  config.json → init_config 已自动创建，无需处理（打印提示即可）
  ├── llm_key.json 缺失 → 提示 跳过/输入 Key（输入则经 _atomic_write 原子写 flat llm_key.json：provider/api_key/model/endpoint，C3）
  ├── holdings/ 为空 → 提示放置持仓文件（引导到 how-to-start.md 持仓格式章节）
  ├── LLM=claude 无 key → 降级提示（报告对应页签将显示占位）
  └── 全部就绪 → 打印 "一切就绪，开始生成报告！"
  ```
- **非交互检测**：`sys.stdin.isatty()` 为 False、环境变量 `CI`/`NON_INTERACTIVE` 存在、或 CLI 传 `--non-interactive` → **跳过交互**，仅日志记录，不阻塞（设计文档风险项）

### 4.2 接线

- `tui/tui.py` `main()`（L143 隐私提示旁）：`show_startup_wizard_if_needed()` 包 try/except
- `cli/cli.py`：`_build_parser`（L31）新增 `--non-interactive` 参数；`main()`（L326）`init_config` 后按 `args.non_interactive` 调 `show_startup_wizard_if_needed()`
- 现有 `tui_menu.print_header()`（L85）"首次使用指引" 保留（非阻塞提示），两者不冲突

---

## 测试计划

> 全部新测试**必须标注 marker**（conftest 已注册）；edge 用例放 `*_edge.py`；LLM/网络调用全 mock；pipeline 测试重定向 output_dir 到 tmp。

### 新增
| 文件 | marker | 覆盖 |
|---|---|---|
| `src/test/unit/analysis/test_correlation.py` | `[unit, unit_analysis]` | 纯计算：对齐/Pearson/p-value/显著性/insufficient/矩阵 None 格 |
| `src/test/unit/analysis/test_correlation_edge.py` | `[unit, unit_analysis, edge]` | 全空、单品种、常数序列、窗口边界 |
| `src/test/unit/report/test_correlation_sheet.py` | `[unit, unit_report]` | Excel 热力页签、占位、N/A 灰格 |
| `src/test/unit/report/test_correlation_html.py` | `[unit, unit_report]` | 模板热力表格、降级分支、section 可见性 |
| `src/test/scenario/basic/test_pipeline_correlation.py` | `[scenario, scenario_basic]` | prep/pipeline_data 注入、章节可见（mock fetch） |
| `src/test/unit/analysis/test_drawdown_events.py` | `[unit, unit_analysis]` | 峰谷恢复提取、区间合并、恢复耗时 |
| `src/test/unit/analysis/test_drawdown_events_edge.py` | `[unit, unit_analysis, edge]` | 全程无恢复、<60 日、平缓序列 |
| `src/test/unit/report/test_drawdown_html_excel.py` | `[unit, unit_report]` | 回撤明细表 HTML/Excel 渲染、数据不足占位 |
| `src/test/unit/startup/test_startup_wizard.py` | `[unit, unit_ui]` | 状态检测、首次标记、交互 mock、非交互跳过 |

### 更新既有断言
- `test_registry.py` L250 `len==19` → **20**；新增 correlation 注册测试
- `test_scenario_section_order.py`：L79 `fund_deep_analysis==5` → **6**；L122 `b_series==5` → **6**
- `test_html_report_structure_edge.py` `test_section_count` 19 → **20**
- 若 factor_exposure 页签标题断言依赖回退路径，同步校验（`_REPORT_SHEET_NAMES` 修复后应为 "因子暴露分析"）

---

## 文档维护（CLAUDE.md 强制项）

- `docs-stm/managements/plan.md`：plan-2/3/9 标记完成
- `technical.md`：附录 H 补 `correlation_data` C19 契约 + history_data 嵌套字段（drawdown_events/recovery_times/drawdown_available）；新增 §4.x 相关性矩阵章节
- `folders.md`：目录树新增 `analysis/correlation.py`、`analysis/drawdown_events.py`、`report/correlation_sheet.py`、`startup_wizard.py` 及 9 个测试文件
- `testplan.md` / `test-coverage.md`：登记新测试项
- `changelog.md`：`[0.9.7-dev]` 下 3 条 `### Feat` 条目（相关性矩阵 / 回撤明细 / 首次运行引导）
- 新测试 marker 无需新增（沿用 unit_analysis/unit_report/unit_ui/scenario_basic/edge）

---

## 验证（P0 门禁）

1. 逐模块单测：`python -m pytest <新测试文件> -v --tb=short`（先单文件，不跑全量）
2. 失败用例提取：`python scripts/extract-test-failures.py`
3. 提交前门禁：`python scripts/test_runner.py --mode dev-verify` + `python scripts/check-history-traces.py --ci`
4. 手动烟测：真实持仓生成一次 HTML+Excel，检查相关性页签热力图配色/配对表/降级占位、回撤明细表、首次运行引导展示与 `--non-interactive` 跳过
5. `ruff format --check`（非阻塞，可 `ruff format` 自动修复）

## 实施顺序
plan-2 → plan-3 → plan-9（每完成一个跑一次相关单测）→ 全量文档 → P0 门禁
