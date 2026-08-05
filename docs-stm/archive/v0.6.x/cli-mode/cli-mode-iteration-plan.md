# CLI 命令行模式 — 迭代计划

> 文档版本：v2.6（第 11 轮复盘修正版 — P2 优化为 8 轮）
> 状态：v0.6.1 — P2 CLI 模式已完成
> 关联设计：[cli-mode-technical-design.md](cli-mode-technical-design.md)
> 已归档。原始路径：`docs-stm/plan/` → `docs-stm/archive/v0.6.x/cli-mode/`

---

## 1. 概述

为工具增加非交互式**命令行模式（CLI）**，支持 Windows 任务计划程序 / Linux cron 定时自动驱动报告生成，无需人工操作 TUI 菜单。

### 1.1 核心架构决策

**TUI 和 CLI 共享同一套业务编排层，不在入口层重复实现编排逻辑。**

```
P1 之前（现状）:
  TUI → handlers_report.py (95% 业务编排 + 5% input/get_key) → report/llm/fetcher
        handlers_cache.py (业务逻辑 + print 格式化深度缠绕)

P1 之后:
  TUI → handlers_report.py (薄: 仅 input/print) ─┐
        handlers_cache.py (薄: 仅 print/press_any) ├→ report/orchestrator.py
                                                   │   cache/operations.py
  CLI → cli.py (argparse → 直接调共享层) ──────────┘
```

### 1.2 两阶段划分

| 阶段 | 内容 | 进度要求 |
|:-----|:------|:---------|
| **P1：共享层提取**（12 轮） | 从 handlers_*.py 逐函数提取业务逻辑到 `report/orchestrator.py` + `cache/operations.py`；TUI 变薄为仅保留交互的包装器 | **每轮 regression 全绿**，全部完成后才进入 P2 |
| **P2：CLI 实现**（8 轮） | 用共享层构建 CLI 入口；argparse + CliProgressReporter + 报告/缓存子命令 + 退出码 + 测试 + 文档 | 每轮独立验证 |

---

## 2. 20 轮迭代总览

```
P1 — 共享层提取（TUI 行为零变更，每轮 regression 全绿 + 模块测试）
  S1  ██░░░░░░░░░░░░   定义 orchestrator + 提取 _prepare_report_data + 创建测试骨架
  S2  ████░░░░░░░░░░   提取 _capture_snapshot + _compute_early_warnings
  S3  ██████░░░░░░░░   分拆 _fetch_history_data（input 留在 TUI）
  S4  ████████░░░░░░   basic 报告编排（Excel-only 路径，无数据准备）
  S5  ██████████░░░░   both 路径提取（行情明细+快照+历史+HTML+Excel）
  S6  ████████████░░   full 路径提取（完整数据+LLM+新闻线程池+预警+去池）
  S7  ██████████████   TUI handlers_report 变薄 + 菜单 EBL 验证
  S8  ██████████████   operations.py 框架 + _refresh_one_fund_cache（含池创建）
  S9  ██████████████   提取 _refresh_common_caches()  print→reporter 替换
  S10 ██████████████   提取持仓缓存 + 统计 + 清理
  S11 ██████████████   TUI handlers_cache 变薄 + 去池
  S12 ████████████████ regression 全绿 + 清理死代码 + 等值验证 + 文档同步

P2 — CLI 实现（基于共享层，不经过 handlers_*）
  C1  ██░░░░░░░░░░░░   argparse + 路径初始化 + config 覆写
  C2  ████░░░░░░░░░░   CliProgressReporter + 基类 print_timing_summary 补充
  C3  ██████░░░░░░░░   _cli_read_holdings + cache 子命令（委托 operations）
  C4  ████████░░░░░░   report --type basic
  C5  ██████████░░░░   report --type both + --type full（一次覆盖三路径）
  C6  ████████████░░   退出码硬化 + KeyboardInterrupt + 配置等值验证
  C7  ██████████████   单元测试 + 集成测试
  C8  ████████████████ 文档 + regression 最终验证
```

---

## 3. P1：共享层提取（12 轮）

---

### S1：orchestrator 模块结构 + 提取 _prepare_report_data

**目标**：创建 `report/orchestrator.py` 并定义接口约定，将 `_prepare_report_data()` 从 `handlers_report.py` 移入。

#### 设计要点

- 新增 `report/orchestrator.py`，定义共享入口
- 定义 `ReportResult`、`_read_section_flags()` 等辅助数据结构
- 先定义空壳 `generate_report()` 函数，后续迭代逐步填充
- 将 `_prepare_report_data()`（handlers_report.py:310-394）原样移入 orchestrator，仅改调用者为 `orchestrator.prepare_report_data()`。该函数**不含任何 TUI 交互**（纯数据操作），移动安全
- **无 TUI 行为变化**
- **★ 循环依赖预防**：orchestrator **不导入** handlers_report 任何符号。`prepare_report_data()` 内部原本调 `handlers_report._get_pool()`（指数并行获取），S1 直接复刻此调用——S6 时会消除此依赖

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/orchestrator.py` | **新建** — `ReportResult` + `prepare_report_data()` + `generate_report()` 空壳 |
| `src/python/handlers_report.py` | **修改** — `_cmd_*` 中调 `_prepare_report_data()` → 改调 `orchestrator.prepare_report_data()` |

#### 测试新增

- `src/test/test_orchestrator.py` **新建**（测试骨架 + `test_prepare_report_data` mock 测试）

#### 验收标准

- [ ] `prepare_report_data()` 在 orchestrator 中可被 TUI handler 调用
- [ ] 返回的数据结构与原 `_prepare_report_data()` 一致
- [ ] TUI 菜单 [E][B][L] 调用结果不变（肉眼验证报告内容一致）
- [ ] 无任何 `input()`/`get_key()`/`print()` 引入
- [ ] `test_orchestrator.py` 中 `test_prepare_report_data` mock 测试通过
- [ ] regression 全绿
- [ ] **不满足时不得进入 S2**

---

### S2：提取 _capture_snapshot + _compute_early_warnings

**目标**：将 `_capture_snapshot()`（~83 行，注：v2.3 及之前误估为 ~15 行）和 `_compute_early_warnings()` 从 handlers_report.py 移入 orchestrator。

#### 设计要点

- `_capture_snapshot()`（handlers_report.py:69-151，~83 行）**不是**简单纯计算函数——实际规模远大于早期估算。包含：SnapshotHolding 映射、holdings 回查关联、SnapshotData 创建、HistoryDiff 计算、save + prune、复杂 f_context 字典组装。提取时注意内联 import 的处理
- `_compute_early_warnings()`（handlers_report.py:409-430，~22 行）纯计算 + 调 `get_sector_fund_flow()` / `compute_early_warnings()`，无交互，安全移动
- TUI 调用点更新为 `orchestrator.capture_snapshot()` / `orchestrator.compute_early_warnings()`
- ★ `_capture_snapshot()` 中使用了 `get_config_cache()`（位于 tui_menu.py），orchestrator 版本需改为从 config 参数读取 `history` 配置

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/orchestrator.py` | **修改** — 添加 `capture_snapshot()` 和 `compute_early_warnings()` |
| `src/python/handlers_report.py` | **修改** — 调用点重定向 |

#### 测试（★ v2.5 细化）

`test_orchestrator.py` 扩展，覆盖 5 个子步骤：

| 测试用例 | 验证点 |
|:---------|:-------|
| `test_capture_snapshot_holding_mapping` | 从 details → SnapshotHolding 的 market_value/cost/profit 字段映射正确 |
| `test_capture_snapshot_holdings_lookup` | `next()` 回查 holdings 补充 shares/cost_price；无匹配项时默认值 0.0 |
| `test_capture_snapshot_data_creation` | SnapshotData.total_value = sum(d.market_value) 等聚合正确 |
| `test_capture_snapshot_diff_compute` | HistoryDiff.compute 被调用 + diff 结果含 added/removed/increased/decreased 四个子列表 |
| `test_capture_snapshot_prune_params` | prune 接收的 retention_days/max_count 来自 config 参数（**非** `get_config_cache()`）|
| `test_capture_snapshot_f_context` | f_context 字典含 diff/diff_trimmed/days_since_last 三个顶层 key |
| `test_capture_snapshot_first_run` | 首次运行（_old=None）时返回 None，不抛出异常 |
| `test_capture_snapshot_exception_safe` | 任意子步骤异常时捕获到 logger，返回 None 不阻塞 |

#### 验收标准（★ v2.5 细化）

- [ ] SnapshotHolding 映射：code/name/market_value/cost/profit 字段与 details 一致
- [ ] holdings 回查：shares/cost_price 正确填充；**无匹配 holdings 时默认 0.0**
- [ ] SnapshotData 聚合：total_value/total_cost/total_pnl 验算一致
- [ ] HistoryDiff 计算：`HistoryDiff.compute()` 被调用，结果含 added/removed/increased/decreased 四个结构完整的子列表
- [ ] prune 参数：retention_days 和 max_count 从 config 参数读取（**非** `get_config_cache()`，v2.4 已修正为 config 参数）
- [ ] f_context 结构：含 diff、diff_trimmed、days_since_last 三个 key
- [ ] 异常降级：SnapshotHolding 创建空 → 返回 None；HistoryDiff 计算异常 → 返回 None；prune 异常 → 不阻塞
- [ ] 首次运行无快照时返回 None（非空列表/空字典，与 TUI 原始行为一致）
- [ ] TUI 行为零变更（`_cmd_generate_both`/`_cmd_generate_full` 的快照输出不变）
- [ ] 全部 8 个测试用例通过
- [ ] regression 全绿
- [ ] **不满足时不得进入 S3**

---

### S3：分拆 _fetch_history_data

**目标**：将 `_fetch_history_data()` 中的**业务逻辑**移至 orchestrator，`input()` 交互留在 TUI。

#### 设计要点

- `_fetch_history_data()`（handlers_report.py:154-195，~42 行，v2.3 及之前误估为 ~22 行）当前含一个 `input()` 分支（`history_mode="prompt"`）和一个自动分支（`history_mode="auto"`），还有 PortfolioHistoryCalculator 创建+调用逻辑
- **分拆方案**：
  - orchestrator 新增 `fetch_history_data(holdings, config, reporter, mode="auto")` — 纯业务逻辑，不接受 `"prompt"`
  - TUI 保留 `_fetch_history_data` 外壳：调用 `input()` + 根据结果决定调 `fetch_history_data()` 的参数
- `"auto"` 分支已存在且正常，orchestrator 版本只需对外暴露 `mode="auto"/"off"`

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/orchestrator.py` | **修改** — 新增 `fetch_history_data(holdings, config, reporter, mode="auto")` |
| `src/python/handlers_report.py` | **修改** — `_fetch_history_data()` 保留 `"prompt"` 外壳，业务走 orchestrator |

#### 验收标准

- [ ] `_fetch_history_data("prompt", ...)` TUI 交互完全不变（`input()` 弹出）
- [ ] `orchestrator.fetch_history_data("auto", ...)` 直接返回数据，无交互
- [ ] `orchestrator.fetch_history_data("off", ...)` 直接返回 None
- [ ] regression 全绿
- [ ] **不满足时不得进入 S4**

---

### S4：basic 报告编排

**目标**：将 `_cmd_generate_excel()` 的编排逻辑从 handlers_report.py 移入 orchestrator 的 `generate_report()`。

#### 设计要点

- orchestrator 新增 `generate_report(holdings, config, reporter, report_type="basic", ...)`：
  - **不调** `prepare_holdings()` 和 `finish_report()`
  - **不调用** `prepare_report_data()`／`capture_snapshot()`／`fetch_history_data()`（匹配 TUI `_cmd_generate_excel` 原始行为——仅直接生成 Excel）
  - 直接调 `excel_generator.generate_excel_report()`（**不**经过 `handlers_report._generate_excel_report()`）
  - 返回 `ReportResult`
- `_generate_excel_report()` 是 handlers_report.py 中一个极薄委托包装（~5 行），orchestrator 直接跳过
- **★ 本次发现修正（第 4 轮复盘）**：orchestrator `basic` 路径**不**包含 `prepare_report_data()` + `capture_snapshot()`，这不是架构简化遗漏，而是刻意匹配 TUI 原始三路径差异以避免引入 TUI 行为变更

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/orchestrator.py` | **修改** — `generate_report()` 支持 `basic` 路径 |
| `src/python/handlers_report.py` | **修改** — `_cmd_generate_excel()` 改调 `generate_report()` |
| `src/python/handlers_report.py` | **修改** — `_generate_excel_report()` 保留（S7 评估是否删除） |

#### 测试

- `test_orchestrator.py` 扩展：`test_generate_report_basic`（mock `excel_generator.generate_excel_report`，验证被调用）

#### 验收标准

- [ ] `_cmd_generate_excel()` TUI 行为不变（仅生成 Excel，无数据准备/快照/历史）
- [ ] `generate_report(report_type="basic")` 生成 Excel 报告（不调 `prepare_report_data`/`capture_snapshot`）
- [ ] `generate_report()` 内无 `input()`/`get_key()`/`print()`
- [ ] orchestrator 不导入 `handlers_report`（循环依赖预防验证）
- [ ] `test_generate_report_basic` 通过
- [ ] regression 全绿
- [ ] **不满足时不得进入 S5**

---

### S5：both 路径提取（行情明细 + 快照 + 历史 + HTML+Excel）

**目标**：将 `_cmd_generate_both()` 的编排逻辑移入 orchestrator 的 `_generate_report_both()`。

#### 设计要点

- `_cmd_generate_both()`（~74 行）的流程：`_generate_details()` → `check_network_available()` → `_capture_snapshot()` → `_fetch_history_data()` → `write_html_report()` → `_generate_excel_report()`
- **不调用 `_prepare_report_data()`**（无指数/穿透/分类），直接调 `_generate_details()`——标记为 `_compute_details()` 包装
- **不调用线程池**——新闻由 writer 内部处理，不同于 full 路径的显式 `build_news_data()`
- `history_mode="prompt"` 由 TUI 外壳处理（`_cmd_generate_both()` 中 if-else）
- ★ `check_network_available()` 是 TUI 专属函数（位于 `tui_handlers.py`，使用 `print()`），orchestrator **不调用**。orchestrator 调 `_generate_details()` 后直接返回，网络可用性检查由调用方（TUI 外壳）负责
- ★ `_cmd_generate_both()` 当前使用 `get_config_cache()` 读取配置。orchestrator 版本通过 `config` 参数接收

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/orchestrator.py` | **修改** — `generate_report()` 支持 `both` 路径 + `_compute_details()` 轻量级明细 |
| `src/python/handlers_report.py` | **修改** — `_cmd_generate_both()` 改调 `generate_report(report_type="both")` |

#### 测试

- `test_orchestrator.py` 扩展：`test_generate_report_both`（验证不调 `prepare_report_data`、无线程池）

#### ⚡ 验收标准

- [ ] `_cmd_generate_both()` TUI 行为不变
- [ ] `generate_report(report_type="both", history_mode="auto")` 生成 HTML + Excel，无 LLM
- [ ] `generate_report(report_type="both")` **不调用** `_fetch_llm_and_news()` / 线程池
- [ ] `generate_report(report_type="both")` **不调用** `prepare_report_data()`（仅 `_compute_details()`）
- [ ] orchestrator 不导入 `handlers_report`（循环依赖预防验证）
- [ ] 新增测试全部通过
- [ ] regression 全绿
- [ ] **不满足时不得进入 S6**

---

### S6：full 路径提取（完整数据 + LLM+新闻线程池 + 预警）

**目标**：将 `_cmd_generate_full()` 的编排逻辑移入 orchestrator 的 `_generate_report_full()`。

#### 设计要点

- `_cmd_generate_full()`（handlers_report.py:433-603，~171 行）的流程：`_prepare_report_data()` ← 内含 `check_network_available()` → `_capture_snapshot()` → `_fetch_history_data()` → `get_sector_fund_flow()` → `_prompt_force_llm()` → 线程池(LLM+新闻并行) → `_process_llm_news_futures()` → `print_llm_session_usage()` → `_compute_early_warnings()` → `write_html_report()` → `_generate_excel_report()`
- orchestrator `_generate_report_full()` 包含：
  - **`prepare_report_data()`**：完整数据准备（含指数/穿透/分类），内部创建 `ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_prep")` 获取指数
  - **`_fetch_llm_and_news()`**：内部 `ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_llm_news")`，`try/finally shutdown(wait=False, cancel_futures=True)`
  - **`compute_early_warnings()`**：智能预警
- ★ **第 4 轮复盘修正 — `_fetch_llm_and_news()` 需统一处理四个分支**：
  1. LLM+新闻均启用（当前 `_process_llm_news_futures()` 处理，~59 行，handlers_report.py:273-331）
  2. 仅 LLM（`_cmd_generate_full()`:509-541，~33 行，与 _process_llm_news_futures 有大量重复的 ok/disabled/failed 计数逻辑）
  3. 仅新闻（`:504-507`，~4 行）
  4. 均关闭（`:542-547`，~6 行）
  
  `_fetch_llm_and_news()` 内部用 if-elif 覆盖全部 4 分支，消除重复代码。返回统一的 (llm_content, news_data, news_llm_meta, news_ok) 四元组。
- ★ `_process_llm_news_futures()` 和 LLM-only 分支的 ok/disabled/failed 计数逻辑（`LLM_MODULE_FAILURE` / `FAIL_REASON_DISABLED` / `get_llm_module_name` 判定）统一归入 `_fetch_llm_and_news()`，TUI 外壳不再含此判定
- ★ `check_network_available()` 出现在 `_prepare_report_data()` 中（handlers_report.py:347），TUI 专属，orchestrator 不调用。orchestrator 的 `prepare_report_data()` 调用 `_generate_details()` 后直接返回
- ★ `print_llm_session_usage()`（handlers_report.py:549）是 TUI 专属函数（位于 `tui_handlers.py`），CLI 通过 logging 间接记录 LLM 用量。orchestrator 不调用
- `_prompt_force_llm()` 的 `input()` 留在 TUI 外壳
- `history_mode="prompt"` 由 TUI 外壳处理
- S6 完成后，`handlers_report._POOL` 和 `_get_pool()` 不再被任何代码引用（S7 清理）

```python
# orchestrator.py — S6 后 prepare_report_data 使用内部池
def prepare_report_data(holdings, reporter):
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_prep")
    try:
        a_fut = pool.submit(fetch_indices)
        us_fut = pool.submit(fetch_us_indices)
        # ...
    finally:
        pool.shutdown(wait=False)
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/orchestrator.py` | **修改** — `generate_report()` 支持 `full` 路径 + `_fetch_llm_and_news()` 线程池 + `prepare_report_data()` 内部池 |
| `src/python/handlers_report.py` | **修改** — `_cmd_generate_full()` 改调 `generate_report(report_type="full")` |

#### 测试（★ v2.5 细化 4 分支）

- `test_orchestrator.py` 扩展：`test_generate_report_full` / `test_generate_report_thread_pool` / `test_generate_report_force_llm`

`_fetch_llm_and_news()` 独立 4 分支测试：

| 测试用例 | 分支 | 验证点 |
|:---------|:-----|:-------|
| `test_fetch_llm_news_both_enabled` | ① LLM+新闻 | `_await_both_futures` 被调用；返回的 llm_content 非空 4-tuple；news_data 非空列表；news_ok=True |
| `test_fetch_llm_news_only` | ② 仅 LLM | `_await_llm_only` 被调用；news_data=[]；news_llm_meta={}；news_ok=False |
| `test_fetch_llm_news_only_news` | ③ 仅新闻 | llm_content=(None,None,None,None)；news_data 非空；news_ok=True |
| `test_fetch_llm_news_both_disabled` | ④ 均关闭 | 返回占位四元组 + [] + {} + False；reporter.info 被调用 |
| `test_fetch_llm_news_llm_failure_graceful` | ① LLM 失败 | `_await_both_futures` 中 LLM 异常→llm_ok=False，新闻仍正常返回 |
| `test_fetch_llm_news_threadpool_cleanup` | 全部 | `pool.shutdown(cancel_futures=True)` 在 finally 中被调用；KeyboardInterrupt 时资源正常回收 |

#### ⚡ 验收标准（★ v2.5 细化 4 分支）

- [ ] `_cmd_generate_full()` TUI 行为不变
- [ ] `generate_report(report_type="full")` 生成 HTML + Excel + LLM
- [ ] `generate_report(force_llm=True)` 跳过 LLM 缓存
- [ ] `prepare_report_data()` 不调 `handlers_report._get_pool()`
- [ ] orchestrator 内部线程池创建/关闭正常（不泄漏）
- [ ] Ctrl+C 能立刻中断线程池（不阻塞 ~30 秒）
- [ ] orchestrator 不导入 `handlers_report`（循环依赖预防验证）
- [ ] **4 分支独立验收**：
   - [ ] 分支① LLM+新闻：返回 `(llm_tuple, news_list, meta_dict, True)`，llm_tuple 为 4 元素元组（global_macro/expert_review/health_check/penetration_deep），news_list 长度 > 0
   - [ ] 分支② 仅 LLM：llm_tuple 非占位，`news_list=[]`，`meta_dict={}`，`news_ok=False`
   - [ ] 分支③ 仅新闻：`llm_tuple=(None,None,None,None)`，news_list 非空，`news_ok=True`
   - [ ] 分支④ 均关闭：`reporter.info()` 打印"[板块配置] 新闻和 LLM 均未开启"；返回占位值
- [ ] **LLM 失败降级**：LLM key 缺失时 branch① 自动退化为 branch③（仅新闻继续打印），不抛异常
- [ ] LLM-only 分支的 ok/disabled/failed 判定不重复（`_process_llm_news_futures` 中与 `_cmd_generate_full()` LLM-only 间的重复计数逻辑已被消除）
- [ ] **`print_llm_session_usage()` TUI 专属确认**：orchestrator 内不调用此函数；CLI 路径通过 logging 记录 LLM 用量
- [ ] **check_network_available() 不在 orchestrator 中出现**
- [ ] **`get_config_cache()` 替换为 config 参数**：orchestrator 内所有配置读取通过 `config` 参数，不调用 `tui_menu.get_config_cache()`
- [ ] **跨模块审计**：确认 `handlers_report._POOL` 和 `_get_pool()` 无外部模块导入（`grep -rn "handlers_report.*_get_pool\|handlers_report.*_POOL" src/python/ --include="*.py"` 应返回空）
- [ ] 新增测试全部通过
- [ ] regression 全绿
- [ ] **不满足时不得进入 S7**

---

### S7：TUI handlers_report 变薄

**目标**：完成 `handlers_report.py` 的瘦身——所有编排逻辑已移入 orchestrator，`_cmd_*` 函数仅保留交互外壳。

#### handlers_report.py 最终形态（～220 行 → ～60 行）

```python
# handlers_report.py（P1 最终）
from src.python.report.orchestrator import generate_report

def _prompt_force_llm(reporter) -> bool:
    """TUI 专属：询问用户是否强制刷新 LLM 缓存。"""
    try:
        _resp = input("  [..] 是否强制重新生成 LLM 内容（跳过缓存）？(y/N): ")
        return _resp.strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False

def _cmd_generate_excel() -> None:
    """basic: 仅 Excel（无数据准备/快照/历史）。"""
    holdings = prepare_holdings()
    if not holdings:
        return
    config = get_config_cache() or {}
    reporter = TuiProgressReporter()
    generate_report(holdings, config, reporter, report_type="basic")
    finish_report(reporter)

def _cmd_generate_both() -> None:
    """both: HTML+Excel（轻量级，无 LLM）。"""
    holdings = prepare_holdings()
    if not holdings:
        return
    config = get_config_cache() or {}
    reporter = TuiProgressReporter()
    generate_report(holdings, config, reporter,
                    report_type="both", history_mode="prompt")
    finish_report(reporter)

def _cmd_generate_full() -> None:
    """full: 全量 HTML+Excel+LLM。"""
    holdings = prepare_holdings()
    if not holdings:
        return
    config = get_config_cache() or {}
    reporter = TuiProgressReporter()
    force = _prompt_force_llm(reporter)
    generate_report(holdings, config, reporter,
                    report_type="full", history_mode="prompt",
                    force_llm=force)
    finish_report(reporter)
```

#### 需要清理的旧代码

| 函数 | 状态 |
|:-----|:------|
| `_prepare_report_data()` | S1 移至 orchestrator，删除 |
| `_capture_snapshot()` | S2 移至 orchestrator，删除 |
| `_compute_early_warnings()` | S2 移至 orchestrator，删除 |
| `_fetch_history_data()` | S3 分拆，TUI 外壳已简化，确认残留代码 |
| `_process_llm_news_futures()` | S6 由 `_fetch_llm_and_news()` 统一封装，删除 |
| `_get_pool()` + `_POOL` | S6 消除，确认无引用后删除 |
| `_generate_excel_report()` | S4 由 orchestrator 直接调 excel_generator，保留至 S12 评估 |

#### 额外审计

S7 完成后执行 `get_config_cache()` 调用点全局审计（当前 handlers_report.py 有 5 处引用），确保：
- S1 提取的 `prepare_report_data()` 已通过 config 参数获取配置
- S2 提取的 `capture_snapshot()` 已通过 config 参数获取 history 配置
- S5/S6 提取的编排路径已将 `config` 作为参数传入
- 残留的 `get_config_cache()` 仅在 TUI 外壳的 `_cmd_*` 包装器中使用

```bash
grep -rn "get_config_cache\|get_config" src/python/handlers_report.py --include="*.py"
# 应仅出现在 _cmd_generate_* 函数中（TUI 外壳）
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/handlers_report.py` | **修改** — 大幅精简（从 ~220 行 → ~60 行） |
| `src/python/report/orchestrator.py` | 无需修改（接口已在 S1~S6 确立） |

#### 验收标准

- [ ] TUI 菜单 [E] 行为与 S1 之前完全一致
- [ ] TUI 菜单 [B] 行为完全一致
- [ ] TUI 菜单 [L] 行为完全一致（含 `input()` 询问 LLM 和 history）
- [ ] `handlers_report.py` 中无残留编排逻辑（含 `_process_llm_news_futures()` 已删除）
- [ ] `_prompt_force_llm()` 按 TUI 原始行为工作
- [ ] `get_config_cache()` 仅在 `_cmd_*` TUI 外壳中出现（`grep -c "get_config_cache" handlers_report.py` ≤ 3）
- [ ] `handlers_report.py` 的 `from src.python.tui_menu import GREEN, RESET, get_config_cache` 导入——`GREEN`/`RESET` 随代码删除自然消失，`get_config_cache` 应在 TUI 外壳中保留
- [ ] `check_network_available()` 和 `print_llm_session_usage()` 未出现在 orchestrator 中（审计确认）
- [ ] regression 全绿
- [ ] **不满足时不得进入 S8**

---

### S8：operations.py 框架 + _refresh_one_fund_cache

**目标**：创建 `cache/operations.py`，提取第一个纯计算函数 `_refresh_one_fund_cache()`，建立 operations 内部的线程池。

#### 设计要点

- 新增 `cache/operations.py`，定义 `CacheUpdateResult` / `PositionCacheResult` / `CacheStats`
- 定义 `update_basic_cache()` 空壳，后续逐步填充
- 提取 `_refresh_one_fund_cache()`（~10 行）— 纯计算，无 print，无交互，属安全移动
- **★ operations 内部创建并管理线程池**（`max_workers=4`），不依赖 `handlers_cache._POOL`。`try/finally shutdown(wait=False)`
- `handlers_cache._POOL` 立刻标记为 **deprecated**（不在 operations 中使用）
- **★ v2.5 — 池迁移基线记录**：运行 `grep -rn "handlers_cache.*_POOL\|handlers_cache.*_get_pool" src/python/ --include="*.py"` 记录当前引用数作为基线，后续每轮跟踪减少量
- TUI 菜单 [1] 行为不变

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cache/operations.py` | **新建** — 数据结构 + `_refresh_one_fund_cache()` + `update_basic_cache()` 空壳 + 池 |
| `src/python/handlers_cache.py` | **修改** — `_cmd_update_basic_cache()` 调 `operations.update_basic_cache()` |
| `src/python/handlers_cache.py` | **修改** — 在 `_POOL` 上方加 `# deprecated: S9 起不再使用，S11 删除` 注释 |

#### 验收标准

- [ ] `_refresh_one_fund_cache()` 在 operations 中可独立调用
- [ ] operations 内部池创建/关闭正常
- [ ] `handlers_cache._POOL` 标记为 deprecated（仍有调用者，不删除）
- [ ] **基线记录**：`grep -rn "handlers_cache.*_POOL\|handlers_cache.*_get_pool" src/python/ --include="*.py"` 结果记录到 S8 变更日志（S8→S11 期间跟踪减量）
- [ ] TUI 菜单 [1] 行为不变
- [ ] regression 全绿
- [ ] **不满足时不得进入 S9**

---

### S9：提取 _refresh_common_caches() print→reporter 替换

**目标**：将 `_refresh_common_caches()`（~38 行，~8 处 print）及其子函数移入 operations，完成 print→reporter 替换。

#### 提取范围

| 函数 | 行数 | 说明 |
|:-----|:-----|:------|
| `_refresh_common_caches()` | ~38 | **核心难点**：盈利预测+资金流向+行业+分红并行，~8 处 print 位于 `as_completed` 循环内部（非顺序执行）→ reporter.* 替换需重构循环体结构 |
| `_refresh_industry_cache()` | ~15 | 纯计算，无 print |
| `_refresh_dividend_cache()` | ~15 | 纯计算，无 print |
| `_refresh_profit_forecast_cache()` | ~10 | 纯计算，无 print |
| `_refresh_sector_flow_cache()` | ~10 | 纯计算，无 print |
| `_print_cache_refresh_report()` | ~30 | **留在 TUI**（纯格式化 + 颜色转义） |

#### print→reporter 映射

| 原代码 | 替换后 | 说明 |
|:-------|:-------|:------|
| `print(f"  [..] 正在获取: ...")` | `reporter.info(f"正在获取: ...")` | TUI 显示 CYAN，CLI 写日志 |
| `print(f"  [OK] ... 完成")` | `reporter.ok(f"... 完成")` | TUI 显示 GREEN |
| `print(f"  [!] ... 失败")` | `reporter.warn(f"... 失败")` | TUI 显示 YELLOW |
| `print(f"  [ERR] ...")` | `reporter.error(f"...")` | TUI 显示 RED |

#### TUI 格式化保留

operations 返回 `CacheUpdateResult`（结构化数据），TUI 外壳调用 `_print_cache_refresh_report(result)` 输出彩色表格。

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cache/operations.py` | **修改** — 添加 `update_basic_cache()` 完整实现（含各 `_refresh_*`） |
| `src/python/handlers_cache.py` | **修改** — `_cmd_update_basic_cache()` 调 `operations.update_basic_cache()` |

#### 验收标准

- [x] `update_basic_cache()` 使用 `reporter.*` 替代所有 `print()`
- [x] `update_basic_cache()` 无 `press_any_key()`/`input()`
- [x] TUI 菜单 [1] 行为不变（格式化输出通过 `_print_cache_refresh_report` 保留）
- [x] operations 内部池独立管理，不依赖 `handlers_cache._POOL`
- [x] regression 全绿
- [x] **不满足时不得进入 S10**

---

### S10：提取持仓类缓存刷新 + 统计 + 清理

**目标**：将 `_fetch_prices_and_indices()`、`_cmd_show_cache_stats()` 的统计逻辑、`_cmd_cleanup_cache()` 移入 `cache/operations.py`。

#### 提取范围

| 函数 | 行数 | 说明 |
|:-----|:------|:------|
| `_fetch_prices_and_indices()` | ~48 | 并行价格+指数获取，~12 处 print→reporter.* |
| `_cmd_show_cache_stats()` 统计逻辑 | ~71 | 缓存扫描+过期检查+snapshots 目录扫描+state 目录扫描，返回结构化 `CacheStats`。**实际规模大于早期估算**（~50 行 → ~71 行）|
| `_cmd_cleanup_cache()` 清理逻辑 | ~10 | 委托给 `cleanup_expired()` |

#### operations.py 新增接口

```python
def update_position_cache(holdings: list, reporter: ProgressReporter) -> PositionCacheResult:
    """更新持仓类缓存（价格+指数）。使用 operations 内部池。"""

def cleanup_cache(reporter: ProgressReporter) -> int:
    """清理过期缓存，返回清理数量。"""

def get_cache_stats(reporter: ProgressReporter) -> CacheStats:
    """返回缓存统计，不含 print 格式化。

    ★ 第 4 轮复盘修正：同时扫描 data/cache/、data/history/snapshots/、data/state/ 三个目录，
    匹配 TUI `_cmd_show_cache_stats()` 的实际行为。原计划遗漏了快照和 state 目录。
    """
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cache/operations.py` | **修改** — 添加 `update_position_cache()` / `cleanup_cache()` / `get_cache_stats()` |
| `src/python/handlers_cache.py` | **修改** — `_cmd_update_position_cache()` / `_cmd_cleanup_cache()` / `_cmd_show_cache_stats()` 改调 operations |

#### 验收标准

- [x] `update_position_cache()` 使用 `reporter.*` 替代 `print()`
- [x] `get_cache_stats()` 返回结构化 `CacheStats`，不含 print
- [x] `cleanup_cache()` 返回清理数量，不含 print
- [x] TUI 菜单 [2][3][4] 行为不变（打印格式通过 TUI 外壳保留）
- [x] regression 全绿
- [x] **不满足时不得进入 S11**

---

### S11：TUI handlers_cache 变薄 + 去池

**目标**：完成 `handlers_cache.py` 的瘦身——所有业务逻辑已移入 operations，`_cmd_*` 仅保留交互/格式化外壳。删除 `_POOL` + `_get_pool()`。

#### handlers_cache.py 最终形态（～456 行 → ～80 行）

```python
# handlers_cache.py（P1 最终）

# 删除 _POOL / _get_pool()

def _read_holdings_and_clear_cache(group_name: str) -> list | None:
    """TUI 专属：交互选择持仓文件 → 读取 → 清缓存。"""
    refresh_config()
    filepath = select_holdings_file()
    if not filepath:
        return None
    holdings = read_holdings(filepath)
    if not holdings:
        print("  [ERR] 未读取到有效的持仓数据"); press_any_key(); return None
    print(f"  [OK] 共 {len(holdings)} 条持仓记录")
    # ... 清缓存
    return holdings

def _print_cache_refresh_report(result: CacheUpdateResult) -> None:
    """TUI 专属：彩色格式化输出缓存更新结果。"""
    # 保留原格式化代码（ANSI 颜色表格）

def _cmd_update_basic_cache() -> None:
    holdings = _read_holdings_and_clear_cache("refresh")
    if not holdings:
        return
    reporter = TuiProgressReporter()
    result = update_basic_cache(holdings, reporter)    # operations 共享层
    _print_cache_refresh_report(result)
    press_any_key()

def _cmd_update_position_cache() -> None:
    holdings = _read_holdings_and_clear_cache("preload")
    if not holdings:
        return
    reporter = TuiProgressReporter()
    result = update_position_cache(holdings, reporter) # operations 共享层
    # TUI 格式化输出...
    press_any_key()

def _cmd_cleanup_cache() -> None:
    reporter = TuiProgressReporter()
    n = cleanup_cache(reporter)
    print(f"  [OK] 已清理 {n} 个过期缓存文件")
    press_any_key()

def _cmd_show_cache_stats() -> None:
    reporter = TuiProgressReporter()
    stats = get_cache_stats(reporter)
    # TUI 格式化输出（彩色表格）...
    press_any_key()
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/handlers_cache.py` | **修改** — 大幅精简（从 ~456 行 → ~80 行），删除 `_POOL` + `_get_pool()` |
| `src/python/cache/operations.py` | 接口已在前两轮确立 |

#### 验收标准

- [x] TUI 菜单 [1][2][3][4] 行为与提取前完全一致（格式化输出相同）
- [x] `_read_holdings_and_clear_cache()` 的 TUI 交互选择不变
- [x] `press_any_key()` 在每条命令末尾正常工作
- [x] `handlers_cache.py` 中无残留业务逻辑
- [x] `handlers_cache._POOL` 和 `_get_pool()` 被删除，无残留引用
- [x] **★ v2.5 — 池迁移完成验证**：`grep -rn "handlers_cache.*_POOL\|handlers_cache.*_get_pool" src/python/ --include="*.py"` 应仅返回 main.py 的 `from src.python.handlers_cache import _POOL, _get_pool` 两行（供需要保留引用的外部模块）。与 S8 基线对比，引用数已归零（除 main.py）
- [x] **跨模块审计**：确认 `handlers_cache._POOL` 和 `_get_pool()` 无外部模块导入（`grep -rn "handlers_cache.*_get_pool\|handlers_cache.*_POOL" src/python/ --include="*.py"` 仅返回 main.py 的正常导入）
- [x] regression 全绿
- [x] **不满足时不得进入 S12**

---

### S12：回归验证 + 等值验证 + 清理死代码 + 文档同步

**目标**：全量门禁确保 P1 提取无回归，清理废弃代码，验证 TUI 与 CLI 配置语义一致。

#### 等值验证（新增）

```python
# S12 验证脚本
# 验证 get_config_cache() 和 get_config() 解析同一 config.json 的结果一致
_config = get_config()
_cache_config = get_config_cache()  # 需在 TUI 菜单初始化后调用
assert _config == _cache_config, "配置语义不一致"
```

#### 清理清单

| 清理项 | 状态 |
|:-------|:------|
| `handlers_report._POOL` + `_get_pool()` | S6 已消除，确认无引用后删除 |
| `handlers_report._prepare_report_data()` | S1 移至 orchestrator，删除 |
| `handlers_report._capture_snapshot()` | S2 移至 orchestrator，删除 |
| `handlers_report._compute_early_warnings()` | S2 移至 orchestrator，删除 |
| `handlers_report._fetch_history_data()` | S3 分拆，确认无残留调用 |
| `handlers_report._generate_excel_report()` | 评估是否删除（orchestrator 直接调 excel_generator） |
| `handlers_cache._POOL` + `_get_pool()` | S11 删除，确认无引用 |

#### 门禁

| 模式 | 预期 |
|:-----|:------|
| `dev-verify` | 全绿 |
| `regression` | 全绿 |
| `scenario` | 全绿 |

#### 文档同步

- `docs-stm/managements/folders.md` — 新增 `orchestrator.py`、`operations.py`
- `docs-stm/managements/review-findings.md` — P1 变更记录
- `plan.md` — P3-I 状态标注"P1 共享层提取已完成"

#### 验收标准

- [x] `regression` 全绿
- [x] `dev-verify` 全绿
- [x] `scenario` 全绿
- [x] TUI 菜单 [E][B][L][1][2][3][4] 冒烟验证通过
- [x] `get_config_cache()` 与 `get_config()` 解析同一 config.json 的结果一致
- [x] `handlers_report.py` 中无 TUI 编排逻辑残留
- [x] `handlers_cache.py` 中无业务逻辑残留
- [x] `folders.md` 已同步
- [x] **★ v2.5 — P1→P2 接口冻结合约已锁定**（见下方"接口冻结合约"章节）
- [x] **不满足时不得进入 P2**

---

### ★ v2.5 新增：P1→P2 接口冻结合约

#### 冻结范围

P1 完成后以下接口进入冻结状态，P2 实现**不得修改其签名**：

**`report/orchestrator.py`**：
| 函数 | 签名 | 返回 |
|:-----|:------|:------|
| `generate_report()` | `(holdings, config, reporter, report_type="basic", history_mode="off", force_llm=False, output_dir=None, warm_cache=False)` | `ReportResult` |
| `prepare_report_data()` | `(holdings, reporter)` | `dict` |
| `capture_snapshot()` | `(holdings, details, reporter)` | `dict \| None` |
| `compute_early_warnings()` | `(holdings, penetrated_assets, sector_flow, news_data, news_llm_meta, reporter)` | `list` |
| `fetch_history_data()` | `(holdings, config, reporter, mode="auto")` | `dict \| None` |

**`cache/operations.py`**：
| 函数 | 签名 | 返回 |
|:-----|:------|:------|
| `update_basic_cache()` | `(holdings, reporter)` | `CacheUpdateResult` |
| `update_position_cache()` | `(holdings, reporter)` | `PositionCacheResult` |
| `cleanup_cache()` | `(reporter)` | `int` |
| `get_cache_stats()` | `(reporter)` | `CacheStats` |

#### 冻结时点

在以下条件**全部满足**后生效：
1. S12 regression/dev-verify/scenario 全绿
2. `get_config_cache() == get_config()` 等值验证通过
3. 跨模块导入审计确认 `handlers_report._POOL`/`handlers_cache._POOL` 无外部引用

#### 解冻流程

P2 实现时若发现冻结接口需要变更，**不得直接修改**，需按以下流程处理：
1. **记录**：在 `review-findings.md` 中记录变更需求（签名变更点、原因、修改内容）
2. **阻断**：P2 实现暂停依赖该接口的轮次，等待解冻裁决
3. **回归**：变更 P1 接口后，必须通过 `--mode verify`（P1 门禁）全绿
4. **同步**：更新两步文档（迭代计划 + 技术设计）中的签名表
5. **恢复**：P2 继续

---

## 4. P2：CLI 实现（8 轮）

---

### C1：argparse 骨架 + 路径初始化 + config 覆写

**目标**：创建 `cli.py`，实现 argparse 解析、子命令注册、--help 输出。此时所有子命令仅输出占位消息。

#### 设计要点

- `cli.py` 顶部 `os.chdir()` + `sys.path.insert(0, ...)`，与 `main.py` 一致
- 子命令 `report` 和 `cache`
- `report` 参数：`--type {basic,both,full}`（默认 `basic`）/ `--history {auto,off}` / `--force-llm`
- `cache` 互斥操作：`--update {basic,position,all}` / `--clean` / `--stats`
- 全局参数：`--config`（帮助含默认路径 `data/config/config.json`）/ `--output` / `--verbose`（自动 TTY 检测）/ `--version`
- **配置路径覆写**：`config/_config_defaults.py` 增 `set_config_path_override()`；`config/_core.py` 的 `init_config()` 增 `config_path` 可选参数
- **日志初始化**：CLI 入口显式调用 `setup_logger()`
- `main()` 返回 `int`，`sys.exit(main())`
- 子命令 body 仅 `print() 占位`

#### ★ 波及分析：`init_config(config_path)` 修改（第 4 轮复盘新增）

`_core.py` 的 `init_config()` 当前签名 `def init_config() -> None` 无参数（`_core.py:125`）。
改为 `def init_config(config_path: str | None = None) -> None` 后波及以下调用方：

| 调用方 | 位置 | 当前调用 | 修改后 |
|:-------|:------|:---------|:-------|
| `tui_menu.py` 菜单初始化 | `from src.python.config import init_config; init_config()` | 无参数 | 向后兼容：`config_path=None` → 走默认路径 `_config_defaults.get_config_path()` |
| `handlers_config.py` 配置页签 | 同上 | 无参数 | 同上 |
| `cli.py` | `init_config(config_path=args.config)` | 新建 | 显式传 `--config` |

**结论**：TUI 调用方均可不传参（兼容），仅 CLI 使用 `--config` 参数时传路径。修改安全，无需改 TUI 调用点。

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cli.py` | **新建** — argparse 骨架 + 路径初始化 |
| `src/python/config/_config_defaults.py` | **修改** — `set_config_path_override()` |
| `src/python/config/_core.py` | **修改** — `init_config(config_path=None)` |
| `src/python/config/__init__.py` | **修改** — 导出 `set_config_path_override`（若已包含则只验证）|

#### 验收标准

- [ ] `python -m src.python.cli --help` 输出含 report 和 cache 子命令
- [ ] `python -m src.python.cli report --help` 输出含 `--type`/`--history`/`--force-llm`
- [ ] `python -m src.python.cli cache --help` 输出含 `--update`/`--clean`/`--stats`
- [ ] `python -m src.python.cli unknown` → exit 2（argparse 自动行为）
- [ ] `--config` 参数解析正确
- [ ] `logs/app.log` 中存在 CLI 执行的 INFO 日志
- [ ] `os.chdir()` 在 `init_config()` 之前执行
- [ ] 非法参数路径验证（`pytest.raises(SystemExit)`）
- [ ] **不满足时不得进入 C2**

---

### C2：CliProgressReporter

**目标**：实现 CLI 专属进度报告器，继承 `ProgressReporter` 基类。

#### 设计要点

- 文件位置：`src/python/report/cli_progress.py`
- 常规模式：输出到 `logging.getLogger("invest")`（**无 `[OK]`/`[!]` 前缀**——`logger.py` 的 `_ColoredFormatter` 已输出 `[%(levelname)s]`）
- `--verbose` 模式：带前缀的 `[..]`/`[OK]`/`[!]`/`[ERR]` 同步到 stderr；**默认 TTY 自动开启**（`stderr.isatty()`）
- 着色降级：本地颜色常量（不导入 `ansi_colors` 模块级常量），`_should_color()` 基于 `stderr.isatty()` + `NO_COLOR` 环境变量
- `call_sheet()`：始终计时，verbose 模式同步输出执行过程到 stderr
- `print_timing_summary()`：`logging.INFO` 逐行输出（含 █░ 柱状条），verbose 模式同步到 stderr

#### ★ 基类接口补充

当前 `ProgressReporter` 基类（`report/progress.py:41`）**未定义** `print_timing_summary()` 方法。
但 orchestrator 的三个报告路径均调用 `reporter.print_timing_summary()`。

需在 `ProgressReporter` 基类中添加空壳方法：
```python
# progress.py ProgressReporter 基类
def print_timing_summary(self) -> None:
    """输出耗时汇总。默认空实现，子类可覆盖。"""
    pass  # CLI 子类覆盖为 logging 输出；Silent 继承空实现
```

影响文件：`src/python/report/progress.py` 修改基类。不影响现有 TuiProgressReporter（已有实现）。

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/report/cli_progress.py` | **新建** — `CliProgressReporter` |
| `src/python/report/progress.py` | **修改** — `ProgressReporter` 基类增加 `print_timing_summary()` 空壳 |

#### 验收标准

- [ ] `CliProgressReporter` 输出到 `logging.getLogger("invest")`（caplog 验证）
- [ ] `--verbose` 模式 stderr 输出 `[..]`/`[OK]`/`[!]`
- [ ] `--verbose` + `NO_COLOR` 无转义字符
- [ ] `--verbose` + stderr 管道重定向无转义字符
- [ ] `call_sheet()` 正确返回 boolean
- [ ] `print_timing_summary()` 日志输出不含转义序列
- [ ] **不满足时不得进入 C3**

---

### C3：_cli_read_holdings + cache 子命令（委托 operations）

**目标**：实现 CLI 专属持仓读取函数，以及 cache 子命令的完整路由委托。

> ★ C3 合并原 C3（`_cli_read_holdings`）和原 C7（cache 子命令）。两者均基于 P1 已冻结的共享层接口，互无依赖，可在同一轮独立验证。

#### 设计要点

```python
# cli.py 内部函数
def _cli_read_holdings(config: dict) -> list | None:
    """CLI 模式读取持仓——跳过文件选择交互。

    通过 config.json 的 holdings_dir + holdings_filename 定位文件。
    多文件时选第一个 + LOG WARNING。
    """
    filepath = os.path.join(
        config.get("holdings_dir", "data/holdings"),
        config.get("holdings_filename", "个人投资持仓信息.xlsx"),
    )
    if not os.path.exists(filepath):
        logger.error("持仓文件不存在（路径: %s）—— 请检查 config.json 中 "
                      "holdings_dir + holdings_filename 配置", filepath)
        return None
    holdings = read_holdings(filepath)
    if not holdings:
        logger.error("持仓文件为空或格式异常: %s —— "
                      "请确保持仓文件包含「名称, 代码, 持仓份额, 每份成本」四列", filepath)
        return None
    return holdings
```

**cache 子命令调用链**：

```
cli.py _handle_cache()
  → init_config()
  → config = get_config()
  → case "--update basic":
        holdings = _cli_read_holdings(config)
        result = update_basic_cache(holdings, reporter)    ← operations 共享层
        → exit result.exit_code
  → case "--update position":
        holdings = _cli_read_holdings(config)
        result = update_position_cache(holdings, reporter) ← operations 共享层
        → exit result.exit_code
  → case "--update all":                                    ← ★ 最大努力模式
        holdings = _cli_read_holdings(config)
        final_exit = _EXIT_SUCCESS
        result = update_basic_cache(holdings, reporter)
        final_exit = max(final_exit, result.exit_code)     ← basic 失败→记录继续
        result = update_position_cache(holdings, reporter)
        final_exit = max(final_exit, result.exit_code)     ← position 总被执行
        → exit final_exit
  → case "--clean":
        n = cleanup_cache(reporter)                        ← operations 共享层
        → exit 0
  → case "--stats":
        stats = get_cache_stats(reporter)                  ← operations 共享层
        → exit 0
```

**注意事项**：
- `update_basic_cache()` / `update_position_cache()` 内部已包含 `clear_by_group()` 调用（匹配 TUI 先清再刷语义），CLI 无需额外清除
- CLI 不经过 `handle_cache.py`，直接调 `operations.*`
- **不需要 `cli_handlers_cache.py` 中介模块**

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cli.py` | **修改** — 新增 `_cli_read_holdings()` + `_handle_cache()` 委托 |

#### 验收标准

- [ ] `_cli_read_holdings()` 通过 config 路径读取持仓文件
- [ ] 文件不存在时返回 None + 日志 ERROR
- [ ] 多文件时自动选第一个 + 日志 WARNING
- [ ] `cache --stats` 调用 `operations.get_cache_stats()`
- [ ] `cache --clean` 调用 `operations.cleanup_cache()`
- [ ] `cache --update basic` 调用 `operations.update_basic_cache()`
- [ ] `cache --update position` 调用 `operations.update_position_cache()`
- [ ] `cache --update all` 依次调 basic → position，退出码取 `max()`
- [ ] `cache` 不带操作参数 → exit 2（argparse 互斥组自动行为）
- [ ] TUI 菜单 [1][2][3][4] 行为不变（regression 验证）
- [ ] 日志中无 `input()` 调用痕迹
- [ ] **不满足时不得进入 C4**

---

### C4：report --type basic

**目标**：CLI `report --type basic` 调用 orchestrator 生成 Excel 报告。

#### 调用链

```
cli.py _handle_report()
  → init_config(args.config)
  → config = get_config()
  → holdings = _cli_read_holdings(config)
  → result = generate_report(
        holdings=holdings,
        config=config,
        reporter=CliProgressReporter(args.verbose),
        report_type="basic",
        output_dir=args.output,
      )
  → sys.exit(result.exit_code)
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cli.py` | **修改** — report 子命令路由到 `generate_report()` |

#### 验收标准

- [ ] `report --type basic` 生成 Excel 报告
- [ ] `--output` 目录覆盖有效
- [ ] 无持仓文件时 exit 2
- [ ] `logs/app.log` 记录步骤
- [ ] 日志中无 `input()` 调用痕迹
- [ ] TUI [E] 菜单行为不变（回归验证）
- [ ] **不满足时不得进入 C5**

---

### C5：report --type both + --type full

**目标**：CLI `report --type both` 和 `report --type full` 调用 orchestrator 生成完整报告（含 LLM）。

> ★ C5 合并原 C5（both）和原 C6（full）。CLI 端的差异仅在于 `report_type=args.type` 的透传，orchestrator 已在 P1 通过 `report_type` 三路分支完整区分。不需要在 CLI 侧编排。

#### 设计要点

- `report --type both`：生成 HTML + Excel（含新闻，不含 LLM），走 orchestrator `_generate_report_both()`
- `--history auto` 自动获取历史走势；`--history off`（默认）跳过
- `report --type full`：生成全量报告（含指数/穿透/LLM+新闻线程池/预警），走 orchestrator `_generate_report_full()`
- `--force-llm` 传 `force_llm=True` 跳过 LLM 缓存
- `--warm` 传 `warm_cache=True` 触发缓存预热（`_warm_cache()` 使用 reporter.* 输出）
- LLM 模块 disabled → exit 0（正常降级）
- LLM key 缺失 → exit 1（降级生成，报告仍生成）
- 线程池由 orchestrator 内部管理（P1 已完成）

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cli.py` | **修改** — `_handle_report()` 中 `report_type=args.type` 改为变量，透传 `history_mode`/`force_llm`/`warm_cache` |

#### 验收标准

- [ ] `report --type both` 生成 HTML + Excel（含新闻板块）
- [ ] `report --type both --history auto` 传 `history_mode="auto"`
- [ ] `report --type both` 无 LLM 相关调用
- [ ] `report --type full` 生成 HTML + Excel + LLM 分析章节
- [ ] `report --type full --force-llm` 传 `force_llm=True`
- [ ] `report --type full --warm` 传 `warm_cache=True`
- [ ] LLM key 缺失时 exit 1，报告降级生成
- [ ] LLM disabled 时 exit 0
- [ ] 日志中无 `input()` 调用痕迹
- [ ] TUI 菜单 [B][L] 行为不变（回归验证）
- [ ] **不满足时不得进入 C6**

---

### C6：退出码硬化 + KeyboardInterrupt + 配置等值验证

**目标**：补齐所有退出码场景映射，实现 Ctrl+C 安全处理，验证 CLI 与 TUI 配置语义一致。

> ★ C6 合并原 C8（退出码全场景硬化）和原 C9（交互审计 + KBI + config 等值验证）。退出码的策略已在 P1 层由 `ReportResult.exit_code` 和 `CacheUpdateResult.exit_code` 实现，CLI 端仅需补全 `_handle_cache()` 的退出码映射。

#### 实装变更

| 变更点 | 当前 | 目标 |
|:-------|:------|:------|
| `_handle_cache()` 退出码 | 总是 `_EXIT_SUCCESS`（C3 暂定） | 使用 `CacheUpdateResult.exit_code` |
| LLM disabled + --type full | exit 0（正确但无测试） | 新增测试 |
| config.json 格式错误 | exit 2（`__main__` 兜底） | 新增测试 |
| KeyboardInterrupt | exit 130 | 实现 |
| 持仓文件不存在 | exit 2 | 已在 C4 覆盖 |

#### KeyboardInterrupt 处理

```python
if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        logger.info("CLI 操作被用户中断")
        # orchestrator 的线程池已经在内部 shutdown(cancel_futures=True)
        sys.exit(130)
    except Exception:
        logger.exception("CLI 未处理异常")
        sys.exit(2)
```

#### 配置等值验证

```python
# 验证 CLI 和 TUI 解析同一 config.json 的结果一致
_config = get_config()
# 在相同 config.json 下，CLI 解析的配置应与 TUI get_config_cache() 一致
```

#### 交互审计

执行以下命令确认 CLI 路径无交互遗漏：
```bash
grep -rn "\binput(" src/python/ --include="*.py" | grep -v test | grep -v __pycache__
grep -rn "\bget_key(" src/python/ --include="*.py" | grep -v test | grep -v __pycache__
```

交互点对照表（所有点已有 CLI 替代方案）：

| # | 文件 | 函数 | 交互类型 | CLI 替代 |
|:-:|:-----|:-----|:---------|:---------|
| 1 | `handlers_report.py` | `_prompt_force_llm()` | `input()` | `--force-llm` 标志 |
| 2 | `tui_handlers.py` | `select_holdings_file()` | `get_key()` | `_cli_read_holdings()` |
| 3 | `tui_handlers.py` | `press_any_key()` / `prepare_holdings()` / `finish_report()` | `get_key()` | CLI 不调用 |

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/cli.py` | **修改** — 顶层异常兜底 + KeyboardInterrupt 处理 + `_handle_cache()` 退出码映射 |

#### 验收标准

- [ ] `report --type full` LLM disabled 返回 exit 0
- [ ] `report --type full` LLM key 缺失返回 exit 1
- [ ] `cache --update basic` 部分失败返回 exit 1
- [ ] `cache --update all` basic 失败(exit=1) position 仍执行，最终退出码 = max(1, position_exit)
- [ ] Ctrl+C → exit 130，日志记录中断信息
- [ ] 未处理异常 → exit 2，日志记录栈
- [ ] `grep` 审计确认 CLI 路径无 `input()`/`get_key()` 交互遗漏
- [ ] 审计确认 `prepare_report_data()` 的 `get_config_cache()` 回退分支已被删除，CLI 路径无 tui_menu 隐式导入
- [ ] CLI 与 TUI 解析同一 config.json 结果一致（等值断言）
- [ ] TUI 行为不变（回归验证）
- [ ] **不满足时不得进入 C7**

---

### C7：单元测试 + 集成测试

**目标**：为 CLI 模块建立完整的单元测试和集成测试套件。

> ★ C7 合并原 C10（单元测试）和原 C11（集成测试）。测试文件结构和用例数不变，仅合并为同一轮。

#### 测试标记注册

```python
# conftest.py
config.addinivalue_line("markers", "unit_cli: CLI 命令行模式单元测试")
```

#### 测试文件

**`test_cli.py`**（`@pytest.mark.unit` + `@pytest.mark.unit_cli`，~30 用例）：

```
参数解析:
  test_argparse_basic / report_type / cache_subcommands / global_config / output / verbose
  test_argparse_invalid_command → SystemExit(2)

CliProgressReporter:
  test_cli_progress_info / ok / warn / error / add_error
  test_cli_progress_call_sheet_success / call_sheet_failure
  test_cli_progress_verbose_output / no_verbose_silent
  test_cli_progress_timing_summary
  test_cli_progress_color_disabled / color_enabled

报告:
  test_cli_report_basic → mock orchestrator
  test_cli_report_both → 验证参数传递
  test_cli_report_full → 验证 force_llm 参数

缓存:
  test_cli_cache_update_basic / position / all / clean / stats
  → mock operations

退出码:
  test_cli_exit_code_success / _partial / _severe / _llm_disabled / _llm_key_missing
  test_cli_exit_code_unhandled_exception
  test_cli_exit_code_keyboard_interrupt
```

**`test_cli_edge.py`**（`@pytest.mark.edge` + `@pytest.mark.unit_cli`，~6 用例）：

```
test_cli_no_input_in_any_path
test_cli_holdings_not_found → exit 2
test_cli_config_not_found → exit 2
test_cli_report_with_empty_holdings → exit 2
test_cli_multi_holdings_auto_select
test_cli_verbose_ansi_auto_disable
```

**`test_cli_integration.py`**（`@pytest.mark.integration` + `@pytest.mark.unit_cli`，~8 用例）：

| 测试 | 验证点 |
|:-----|:-------|
| `test_cli_progress_logger` | CLI 输出全部写入 `logging.getLogger("invest")` |
| `test_cli_verbose_color_disable` | NO_COLOR / 管道降级 |
| `test_cli_verbose_auto_enable` | `--verbose` 默认 TTY 自动启用 |
| `test_cli_report_config_respected` | `--config` 后配置加载正确 |
| `test_cli_exit_code_all_scenarios` | ~12 种退出码场景全覆盖 |
| `test_cli_init_config_error_handling` | config.json 格式错误 → exit 2 |
| `test_cli_parallel_pool_isolation` | CLI 线程池与 TUI 隔离 |

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/test/test_cli.py` | **新建** |
| `src/test/test_cli_edge.py` | **新建** |
| `src/test/test_cli_integration.py` | **新建** |
| `src/test/conftest.py` | **修改** — 注册 `unit_cli` marker |

#### 验收标准

- [ ] `pytest src/test/test_cli.py -m unit_cli -v` 全通过
- [ ] `pytest src/test/test_cli_edge.py -m edge -v` 全通过
- [ ] `pytest src/test/test_cli_integration.py -m integration -v` 全通过
- [ ] 单轮测试 < 60s（纯 mock，无网络）
- [ ] CLI 代码行覆盖率 ≥ 85%
- [ ] 测试标记符合 conftest.py 注册要求
- [ ] **不满足时不得进入 C8**

---

### C8：文档 + regression 最终验证

**目标**：新增定时任务文档，运行全量回归通过，同步管理文档。

#### 新增文档

`docs-stm/manuals/how-to-schedule.md`：
1. 概述（CLI 入口、常用命令速查表）
2. Windows 任务计划程序配置（schtasks + PowerShell 包装 + 防重入）
3. Linux crontab 配置（crontab + flock 防重入）
4. 最佳实践（日志轮转、缓存预热、网络退避、退出码速查表）
5. 故障排查

#### 最终门禁

| 模式 | 预期 |
|:-----|:------|
| `regression` | 全绿 |
| `dev-verify` | 全绿 |
| `edge` | 全绿 |

#### 额外检查

- `docs-stm/managements/folders.md` — 同步 P1+P2 新增文件
- `docs-stm/managements/review-findings.md` — P2 修复已记录
- `plan.md` — P3-I 状态标记"已完成"

#### 最终用户使用场景

```bash
# 每日盘后自动生成全量报告（Windows）
schtasks /CREATE /SC DAILY /TN "InvestReport" /TR "python D:\path\to\investor-util\src\python\cli.py report --type full --history auto" /ST 16:00

# 每周一更新缓存（Linux cron）
0 9 * * 1 cd /home/user/investor-util && python -m src.python.cli cache --update all >> logs/cron.log 2>&1

# 手动快速生成基础报告
python -m src.python.cli report --type basic --output ./weekly

# 查看缓存状态
python -m src.python.cli cache --stats

# 自定义配置文件 + 强制 LLM 刷新 + 预热缓存
python -m src.python.cli --config /path/to/custom_config.json report --type full --force-llm --warm
```

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `docs-stm/manuals/how-to-schedule.md` | **新建** |
| `docs-stm/managements/folders.md` | **修改** |

#### 验收标准

- [ ] `regression` 全绿
- [ ] `dev-verify` 全绿
- [ ] `edge` 全绿
- [ ] `how-to-schedule.md` 含 Windows 和 Linux 配置
- [ ] `folders.md` 已同步 CLI + P1 文件
- [ ] `review-findings.md` 已更新
- [ ] 全部 20 轮迭代验收标准均已通过


---

## 5. 版次记录

| 版本 | 日期 | 变更说明 |
|:-----|:-----|:---------|
| v0.1~v0.4 | - | 旧 12 轮方案（已废弃） |
| v1.0 | 2026-07-16 | 两阶段 9 轮快速方案 |
| v2.0 | 2026-07-16 | 两阶段 24 轮扩展方案 |
| **v2.1** | 2026-07-16 | **复盘审查修正**：修复循环依赖；合并 S5+S6 为 both+full 一次性提取；S8 即创建 operations 池；P1 各轮追加模块测试；C8 明确定义；新增 --warm、get_key 审计、config 等值验证 |
| **v2.2** | 2026-07-16 | **第 2 轮复盘修正**：S6/S11 追加跨模块导入审计步骤；C6 Provider Chain 合规审计通过（所有 fetcher 调用合规）；验证 S1-S7 和 S8-S11 两条链独立无共享依赖 |
| **v2.3** | 2026-07-16 | **第 3 轮复盘修正**（CLI 细节深挖）：C1 `--type` 默认改为 `basic`，新增 `--version`；C2 CliProgressReporter 日志前缀策略（无冗余 `[OK]`）、`--verbose` 自动 TTY 检测、`print_timing_summary()` 格式定义、`call_sheet()` verbose 行文；C3 错误消息含列名提示；C8 错误消息含操作指引 |
| **v2.4** | 2026-07-16 | **第 4 轮复盘修正**（代码对比审计 12 项）：S2 `_capture_snapshot` 规模修正（~15 行 → ~83 行）；S6 新增 `_fetch_llm_and_news()` 统一 LLM 三分支；S5/S6 追加 `check_network_available` TUI 专属说明；C1 追加 `init_config(config_path)` 波及分析；C7 明确 `clear_by_group` 归 operations 统一管理；C2/C10 追加 `print_timing_summary` 基类接口；S9 追加循环内 print→reporter 重构说明；S10 `CacheStats` 扩展覆盖快照/state 目录；S7 追加 `get_config_cache` 审计；基准函数签名使用参数而非 `reporter._output_dir`；新增风险条目（4 项）|
| **v2.5** | 2026-07-16 | **第 5~10 轮复盘修正**：① S2 测试范围细化（8 用例覆盖 5 子步骤+get_config_cache→config 参数验证）；② S6 4 分支测试覆盖（6 用例：both/llm-only/news-only/disabled/llm 失败降级/线程池清理）；③ S12 后新增 P1→P2 接口冻结合约（签名表+冻结时点+解冻流程）；④ S8 基线+S11 完成双池迁移验证机制；⑤ C7 cache --update all 最大努力退出码模式；⑥ 测试覆盖矩阵新增时间预算（每轮 ≤5~20s，S12 ≤90s）；⑦ 风险矩阵新增 2 项+更新 2 项严重度；⑧ 新增价值静默期分析章节（C4 为价值拐点，建议 S7 后评估 C1 并行化）|
| **v2.6** | 2026-07-16 | **第 11 轮复盘修正（P2 优化为 8 轮）**：① P2 从 12 轮压缩为 8 轮（C3+C7、C5+C6、C8+C9、C10+C11 合并）；② 价值拐点仍为 C4（第 16 轮），但 P2 总轮数减少 33%；③ 风险矩阵更新为 8 轮引用号；④ 测试覆盖矩阵同步为 C1~C8；⑤ 增量收益表同步为 8 轮；⑥ 静默期分析更新为 20 轮占比；⑦ 技术设计 §9 文件清单同步 8 轮变更 |

---

## 6. 总风险矩阵

| 风险 | 可能性 | 影响 | 出现于 | 缓解措施 |
|:-----|:-------|:-----|:-------|:---------|
| P1 提取时遗漏了业务逻辑 | 低 | TUI 菜单行为变化 | S1~S11 | 每轮 regression 验证；S12 全量回归 + 等值验证 |
| **循环依赖**（orchestrator ↔ handlers_report） | **已修复** | 模块加载崩溃 | S4~S7 | orchestrator 直接调 excel_generator，不导入 handlers_report |
| Print→reporter.* 替换改变了缓存格式化输出 | 低 | 缓存菜单显示异常 | S9~S10 | TUI 外壳保留格式化，共享层仅传结构化数据 |
| Orchestrator 线程池管理引入竞态 | 低 | LLM+新闻并发异常 | S5 | `try/finally + shutdown(wait=False)` 模式 |
| **operations 池 + handlers_cache._POOL 双池共存** | **已降低**（v2.5 追加基线记录+S11 完成验证） | ~16 线程浪费 | S8~S11 | S8 创建 operations 池即标记 handlers_cache._POOL deprecated，S11 删除；**v2.5 新增 S8 基线 grep + S11 对比验证** |
| **双池迁移期间旧池调用者遗留风险** | 低（v2.5 新增） | S11 删除 _POOL 后仍有未迁移调用者→运行时崩溃 | S8~S11 | S8 记录引用基线；S9/S10 incremental grep 跟踪减少量；S11 最终 grep 清零确认 |
| CLI 独立持仓读取与 TUI 的文件选择行为不一致 | 低 | CLI 读取了错误的文件 | C3 | CLI 使用 config.json 路径直接读取 |
| **CLI 冷启动**（不预热缓存） | 中 | 报告生成慢 2-3 倍 | C5 | `--warm` 标志可选预热 |
| **TUI/CLI 配置语义差异**（get_config_cache vs get_config） | 低 | 配置解析结果不一致 | C6 | S12 等值验证 + C6 追加验证步骤 |
| 共享层接口在 P2 实现时发现缺陷需要回改 P1 | **已降低**（v2.5 接口冻结合约已形式化） | 回退多轮 | C4 起 | P1-S12 后接口冻结（v2.5 新增正式冻结合约：签名表+冻结时点+解冻流程）；冻结合约同步至迭代计划 + 技术设计 |
| `cache --update all` 执行 ~25 个模块耗时过长被 cron 杀掉 | 中 | 缓存未完全更新 | C3 | 文档建议 cache 与 report 分开调度 |
| **`_capture_snapshot()` 提取规模低估**（实际 ~83 行 vs 估算 ~15 行） | 中 | S2 提取复杂度和测试范围超预期 | S2 | 扩大 S2 测试用例覆盖 SnapshotHolding/HistoryDiff/save/prune/字典组装 |
| **`_process_llm_news_futures()` + LLM-only 分支重复代码**未统一封装 | 中 | 维护两份重复的 ok/disabled/failed 判定逻辑 | S6 | S6 的 `_fetch_llm_and_news()` 统一封装全部 4 分支，消除重复 |
| **TUI `get_config_cache()` 与 orchestrator `config` 参数混用**导致读取不一致 | 低 | orchestrator 读取了过期配置 | S1~S7 | 全局审计 `get_config_cache()` 调用点；orchestrator 统一通过 config 参数读取 |
| **`init_config(config_path)` 修改波及 TUI 调用方** | 低 | TUI 菜单初始化兼容性 | C1 | 向后兼容：config_path=None 走默认路径，TUI 调用方无需改动 |
| **`prepare_report_data()` 残留 `get_config_cache()` 死代码** | **已修复（v2.6）** | orchestrator 意外导入 tui_menu | C1~C6 | P2-C1 清理 TD1：删除 3 行死代码；C6 增加审计确认 CLI 路径不触发该回退分支 |

---

## 7. 测试覆盖矩阵

```
迭代  测试范围                              门禁要求          预估耗时(★ v2.5)
────  ───────────────────────────────────  ──────────        ──────────────
S1    regression + test_orchestrator 骨架    regression        ≤ 15s（mock 无网络）
S2    regression + test_orchestrator 扩展    regression        ≤ 20s（8 个新用例）
S3    regression                            regression        ≤ 10s（纯回归）
S4    regression + mock basic 测试           regression        ≤ 15s
S5    regression + mock both 测试           regression        ≤ 15s
S6    regression + mock full 测试            regression        ≤ 20s（含 4 分支 6 用例）
S7    regression + handlers 变薄验证         regression        ≤ 15s
S8    regression + operations 基本           regression        ≤ 15s
S9    regression + operations 完整           regression        ≤ 15s
S10   regression + operations 全量           regression        ≤ 20s
S11   regression + 去池验证                  regression        ≤ 15s（含 grep 审计）
S12   regression + dev-verify + scenario    🔒 全绿           ≤ 90s（3 种模式合计）
C1    argparse 测试                          ⚡ 非法参数路径   ≤ 5s（纯 argparse）
C2    CliProgressReporter 测试               ⚡ caplog+capsys  ≤ 5s（纯 mock）
C3    _cli_read_holdings + cache mock 测试   ⚡ 全绿           ≤ 10s（委托验证）
C4    report basic mock 测试                 无               ≤ 5s
C5    report both + full mock 测试           无               ≤ 8s（两个 type 分支验证）
C6    退出码全场景 + KBI 测试                ⚡ ~12 场景全绿  ≤ 10s
C7    test_cli + edge + integration 全量      ⚡ 全绿           ≤ 30s（~40 用例 mock）
C8    regression + dev-verify + edge        🔒 全绿           ≤ 90s（3 种模式合计）
```

## 8. 增量收益检查

| 迭代 | 可交付物 | 用户感知 | 价值类型 |
|:-----|:---------|:---------|:---------|
| S1 | orchestrator.py + _prepare_report_data 提取 | ✗ | 架构改善 |
| S2 | 提取 _capture_snapshot + _compute_early_warnings | ✗ | 架构改善 |
| S3 | 分拆 _fetch_history_data | ✗ | 架构改善 |
| S4 | basic 编排移入 orchestrator | ✗ | 架构改善 |
| S5 | both+full 编排 + 线程池统一管理 | ✗ | 架构改善 |
| S6 | 消除 handlers_report._POOL 依赖 | ✗ | 架构改善 |
| S7 | handlers_report 变薄 | ✗ | 架构改善 |
| S8 | operations.py 框架 + 基础缓存池 | ✗ | 架构改善 |
| S9 | 缓存 print→reporter 替换 | ✗ | 架构改善 |
| S10 | 持仓缓存/统计/清理提取 | ✗ | 架构改善 |
| S11 | handlers_cache 变薄 + 去池 | ✗ | 架构改善 |
| S12 | 回归安全垫 + 等值验证 | ✗ | **风险控制** |
| C1 | CLI --help 骨架 | ✔ 帮助信息 | 基础设施 |
| C2 | CliProgressReporter | ✗ | 基础设施 |
| C3 | `_cli_read_holdings` + `cache` 子命令 | ✔ 缓存管理 | **功能交付** |
| C4 | `report --type basic` | ✔ 命令行报告 | **功能交付** |
| C5 | `report --type both + full` | ✔ HTML+新闻+LLM | **功能交付** |
| C6 | 退出码硬化 + 中断安全 + 等值验证 | ✔ 定时任务可靠 | **品质提升** |
| C7 | 单元测试 + 集成测试 | ✗ | 技术债务 |
| C8 | 文档 + regression | ✔ 可部署 | **交付** |

### ★ v2.6 更新：P2 优化为 8 轮后的价值静默期分析

P2 从 12 轮优化为 8 轮后，**价值拐点仍为 C4**（在第 16 轮），但 P2 整体缩短了 4 轮，总耗时减少 ~30%。

#### 静默期统计

| 阶段 | 轮次 | 用户可见产出 | 累计占比 |
|:-----|:----|:------------|:---------|
| P1 架构改善 | S1~S12（12 轮） | ✗ 无 | 60%（12/20） |
| P2 基础设施 | C1~C2（2 轮） | ✔ --help（C1） | 70%（14/20） |
| **价值拐点** | **C4** | **首次执行 report --type basic 生成报告** | — |
| P2 功能交付 | C3~C6（4 轮） | ✔ 全部可见（cache/report/退出码） | 90%（18/20） |
| P2 质量加固 | C7~C8（2 轮） | ✔ C8 可部署 | 100%（20/20） |

**结论**：C4 仍为价值拐点（第 16 轮），但 P2 总轮数从 12 降为 8，功能交付阶段（C3~C6）更紧凑。全部 20 轮完成即可达到可部署状态。

#### 并行化建议（可选）

考虑在 **S7 完成后**（handlers_report 变薄）并行启动 C1（argparse 骨架），原因：
- C1 不依赖 S8~S11（cache 操作），也不依赖 orchestrator 内部逻辑
- C1 仅定义 argparse 参数 + --help 输出 + main() 空壳
- 并行后可将 CLI --help 的可感知时间从 P2-C1 提前约 5 轮

**注意**：并行化会增加上下文切换成本，当前计划不强制实施。此建议供 P1 接近 S7 时评估。
