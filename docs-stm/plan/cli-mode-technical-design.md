# CLI 命令行模式 — 技术设计

> 文档版本：v2.5（第 5~10 轮复盘修正版）
> 状态：规划中
> 关联计划：[cli-mode-iteration-plan.md](cli-mode-iteration-plan.md)

---

## 目录

- [1. 架构概览](#1-架构概览)
- [2. 模块设计细节](#2-模块设计细节)
  - [2.1 report/orchestrator.py — 报告编排共享层](#21-reportorchestratorpy--报告编排共享层)
  - [2.2 cache/operations.py — 缓存操作共享层](#22-cacheoperationspy--缓存操作共享层)
  - [2.3 cli.py — argparse 主入口](#23-clipy--argparse-主入口)
  - [2.4 report/cli_progress.py — CliProgressReporter](#24-reportcli_progresspy--cliprogressreporter)
- [3. TUI 函数修改方案](#3-tui-函数修改方案)
  - [3.1 handlers_report.py 变薄](#31-handlers_reportpy-变薄)
  - [3.2 handlers_cache.py 变薄](#32-handlers_cachepy-变薄)
  - [3.3 tui_menu.py / tui_handlers.py](#33-tui_menupy--tui_handlerspy)
- [4. 交互降级对照表](#4-交互降级对照表)
- [5. 退出码设计](#5-退出码设计)
- [6. 与 TUI 的共享/隔离策略](#6-与-tui-的共享隔离策略)
- [7. 测试策略](#7-测试策略)
- [8. 架构设计约束校验清单](#8-架构设计约束校验清单)
- [9. 文件清单与变更统计](#9-文件清单与变更统计)
- [附录 A：最终用法参考](#附录-a最终用法参考)

---

## 1. 架构概览

### 1.1 核心理念

**TUI 和 CLI 共享同一套业务编排层，不在入口层重复实现编排逻辑。**

P1 共享层提取后，handlers_report.py 和 handlers_cache.py 从"编排 + 交互"变成"仅交互"，而 orchestrator.py 和 operations.py 是纯业务。CLI 直接调用共享层，不经过 handlers_*。

```
P1 之后的分层：
                                    ┌─ tui_menu.py
                                    │  用户菜单循环
                                    │
  TUI 入口 ─────────────────────────┤
  main.py + handlers_report.py 薄    │
  handlers_cache.py 薄               ├─ report/orchestrator.py + cache/operations.py
  tui_handlers.py 薄                 │  （共享业务编排 + 纯数据）
                                     │
  CLI 入口 ──────────────────────────┤
  cli.py + CliProgressReporter        └─ report/* / cache/* / fetcher/* / llm/*
  直接调共享层，不经 handlers_*
```

### 1.2 关键架构预防

**★ 循环依赖预防（复盘审查发现）**：orchestrator **不导入** handlers_report 任何符号。orchestrator 内部的 `generate_report()` 直接调 `excel_generator.generate_excel_report()`，而非 `handlers_report._generate_excel_report()`（后者只是一个 ~5 行的委托包装）。这避免了：

```
handlers_report → orchestrator → handlers_report  ✗ 破坏
handlers_report → orchestrator → excel_generator  ✔ 清洁
```

### 1.3 数据流

**report 子命令（P2 最终）**:

```
cli.py
  → init_config(args.config)
  → config = get_config()
  → holdings = _cli_read_holdings(config)       ← CLI 专属，无交互
  → reporter = CliProgressReporter(args.verbose)
  → result = generate_report(                    ← 调 orchestrator 共享层
        holdings=holdings,
        config=config,
        reporter=reporter,
        report_type=args.type,
        history_mode=args.history,
        force_llm=args.force_llm,
        output_dir=args.output,
        warm_cache=args.warm,                    ← 可选预热
      )
  → sys.exit(result.exit_code)

generate_report() 内部（orchestrator）— 三条独立路径:

  # ── basic 路径（最小化，不含数据准备/快照/历史）──
  report_type == "basic":
    → excel_generator.generate_excel_report(
        holdings, include_news=False, ...)
    → reporter.print_timing_summary()
    → return ReportResult(excel_ok=True, report_generated=True)

  # ── both 路径（轻量级：无指数/穿透/LLM 线程池）──
  report_type == "both":
    → _read_section_flags(config)
    → _compute_details(holdings, today_str)       ← 仅行情明细，非完整 prepare_report_data
    → capture_snapshot(holdings, details, reporter)
    → fetch_history_data(holdings, mode, reporter) ← 按需
    → write_html_report(..., include_news=config)  ← 新闻由 writer 内部获取
    → excel_generator.generate_excel_report(...)
    → reporter.print_timing_summary()
    → return ReportResult(excel_ok=True, html_ok=True, ...)

  # ── full 路径（全量：指数/穿透/LLM/新闻/预警）──
  report_type == "full":
    → _read_section_flags(config)
    → prepare_report_data(holdings, reporter)     ← 完整数据准备含指数+穿透
    → capture_snapshot(holdings, prep, reporter)
    → fetch_history_data(holdings, mode, reporter)
    → _fetch_llm_and_news(...)                    ← 内部线程池 2w（仅 full 调用）
    → compute_early_warnings(...)
    → write_html_report(...)
    → excel_generator.generate_excel_report(...)
    → reporter.print_timing_summary()
    → return ReportResult(excel_ok=True, html_ok=True, llm_ok=..., ...)
```

**cache 子命令（P2 最终）**:

```
cli.py
  → init_config()
  → config = get_config()
  → reporter = CliProgressReporter(args.verbose)
  → case --update basic:
        holdings = _cli_read_holdings(config)    ← CLI 专属
        result = update_basic_cache(holdings, reporter)  ← 调 operations
        sys.exit(result.exit_code)
  → case --update position:
        holdings = _cli_read_holdings(config)
        result = update_position_cache(holdings, reporter)
        sys.exit(result.exit_code)
  → case --clean:
        n = cleanup_cache(reporter)
        sys.exit(0)
  → case --stats:
        stats = get_cache_stats(reporter)
        sys.exit(0)
```

---

## 2. 模块设计细节

### 2.1 `report/orchestrator.py` — 报告编排共享层

**文件路径**：`src/python/report/orchestrator.py`（P1-S1 新建，S1~S6 逐步填充）

#### 核心原则

- **不导入 handlers_report 任何符号**（循环依赖预防）
- **不调 `prepare_holdings()` 和 `finish_report()`**（TUI 外壳负责）
- **直接调 `excel_generator.generate_excel_report()`**，不经过 handlers_report 的委托包装
- **★ v2.4：不调 `check_network_available()`**（TUI 专属，位于 `tui_handlers.py`）
- **★ v2.4：不调 `print_llm_session_usage()`**（TUI 专属，CLI 通过 logging 间接记录）
- **★ v2.4：不调 `get_config_cache()`**（或任何 `tui_menu` 符号）；所有配置通过 `config` 参数接收

#### ReportResult

```python
@dataclass
class ReportResult:
    holdings_ok: bool = False
    excel_ok: bool = False
    html_ok: bool = False
    llm_ok: bool = True
    news_ok: bool = True
    history_ok: bool = True
    report_generated: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if not self.report_generated:
            return 2
        if self.errors:
            return 1
        return 0
```

#### generate_report()

```python
def generate_report(
    holdings: list,
    config: dict,
    reporter: ProgressReporter,
    report_type: str = "basic",
    history_mode: str = "off",       # auto / off（CLI 永不传 "prompt"）
    force_llm: bool = False,
    output_dir: str | None = None,
    warm_cache: bool = False,
) -> ReportResult:
    """生成投资分析报告（三条独立路径，对应 TUI 原始流程）。

    ★ 三条路径各自独立，不共用数据准备函数：
      - basic:  仅 Excel（无数据准备/快照/历史走势）
      - both:   轻量级（行情明细+快照+历史，无指数/穿透/LLM线程池）
      - full:   全量（完整数据准备+LLM+新闻+预警）
    """
    result = ReportResult()
    effective_output = output_dir or config.get("output_dir", "reports")
    sec_order = get_report_section_order(config)
    _enable = _read_section_flags(config, report_type)

    # 可选缓存预热（三路共用）
    if warm_cache and report_type in ("both", "full"):
        _warm_cache(holdings, reporter)

    # ── basic 路径：直接生成 Excel（无数据准备/快照/历史）──
    if report_type == "basic":
        return _generate_report_basic(holdings, config, reporter,
                                      effective_output, sec_order)

    today_str = datetime.now().strftime("%Y-%m-%d")
    news_top_count = int(config.get("news_top_count", 100))

    # ── both 路径：行情明细 + 快照 + 历史 + HTML+Excel ──
    if report_type == "both":
        return _generate_report_both(holdings, config, reporter,
                                     effective_output, today_str,
                                     news_top_count, sec_order, _enable)

    # ── full 路径：全量数据 + LLM+新闻线程池 + 预警 ──
    return _generate_report_full(holdings, config, reporter,
                                 effective_output, today_str,
                                 news_top_count, sec_order, _enable,
                                 history_mode, force_llm)


def _generate_report_basic(holdings, config, reporter,
                           output_dir, sec_order) -> ReportResult:
    """basic: 仅生成 Excel（无数据准备/快照/历史）。匹配 TUI _cmd_generate_excel。"""
    from src.python.report.excel_generator import generate_excel_report
    generate_excel_report(holdings, include_news=False,
                          output_dir=output_dir, section_order=sec_order,
                          progress=reporter)
    result = ReportResult(excel_ok=True, report_generated=True)
    reporter.print_timing_summary()
    return result


def _generate_report_both(holdings, config, reporter,
                          output_dir, today_str,
                          news_top_count, sec_order, _enable) -> ReportResult:
    """both: 轻量级生成（不含指数、穿透、LLM）。匹配 TUI _cmd_generate_both。

    注意：新闻由 writer 内部处理（不调用 build_news_data），
    与 full 路径不同。此行为继承自 TUI _cmd_generate_both。
    """
    from src.python.report.market_value import _generate_details

    result = ReportResult()

    # 仅行情明细（非完整 prepare_report_data）
    reporter.info("正在获取行情数据...")
    details = _generate_details(holdings, today_str)
    reporter.ok(f"行情数据获取完成，共 {len(details)} 条")
    result.holdings_ok = True

    # 快照对比
    f_context = capture_snapshot(holdings, details, reporter)

    # 历史走势（按需）
    history_data = None
    if _enable["history"]:
        history_mode = config.get("history", {}).get("analysis", "off")
        history_data = fetch_history_data(holdings, config, reporter,
                                          mode=history_mode if history_mode != "prompt" else "auto")

    # HTML 报告
    from src.python.report.html_writer import write_html_report
    reporter.info("正在生成 HTML 报告...")
    try:
        write_html_report(holdings, output_dir=output_dir,
                          news_top_count=news_top_count,
                          include_news=_enable["news"],
                          details=details, section_order=sec_order,
                          history_data=history_data, progress=reporter,
                          enable_b_series=_enable["b_series"],
                          enable_news=_enable["news"],
                          enable_history=_enable["history"],
                          enable_llm=False)
        result.html_ok = True
    except Exception:
        reporter.add_error("HTML 报告生成失败")
        reporter.info("继续生成 Excel 报告...")

    # Excel 报告
    from src.python.report.excel_generator import generate_excel_report
    generate_excel_report(holdings, include_news=_enable["news"],
                          output_dir=output_dir,
                          news_top_count=news_top_count,
                          details=details, section_order=sec_order,
                          history_data=history_data, progress=reporter,
                          enable_b_series=_enable["b_series"],
                          enable_news=_enable["news"],
                          enable_history=_enable["history"],
                          enable_llm=False)
    result.excel_ok = True
    result.report_generated = True

    reporter.print_timing_summary()
    return result


def _generate_report_full(holdings, config, reporter,
                          output_dir, today_str,
                          news_top_count, sec_order, _enable,
                          history_mode, force_llm) -> ReportResult:
    """full: 全量生成（含指数、穿透、LLM+新闻线程池）。匹配 TUI _cmd_generate_full。"""
    result = ReportResult()

    # 完整数据准备（含指数/穿透/分类）
    prep = prepare_report_data(holdings, reporter)
    result.holdings_ok = True

    # 快照对比
    f_context = capture_snapshot(holdings, prep["details"], reporter)

    # 历史走势（按需）
    history_data = None
    if _enable["history"]:
        history_data = fetch_history_data(holdings, config, reporter,
                                          mode=history_mode if history_mode != "prompt" else
                                               config.get("history", {}).get("analysis", "off"))

    # 行业资金流向
    reporter.info("正在获取行业资金流向...")
    sector_flow = _get_sector_fund_flow(reporter)

    # LLM + 新闻并行线程池（仅 full 路径）
    llm_content, news_data, news_llm_meta, _news_ok = \
        _fetch_llm_and_news(holdings, prep, f_context, _enable,
                            force_llm, reporter, sector_flow)
    result.llm_ok = _enable["llm"] and bool(llm_content[0])
    result.news_ok = _news_ok

    # 智能预警
    early_warnings = compute_early_warnings(
        holdings, prep["penetrated_assets"], sector_flow,
        news_data, news_llm_meta, reporter)

    # HTML 报告
    from src.python.report.html_writer import write_html_report
    reporter.info("正在生成 HTML 报告（含新闻 + LLM 分析章节）...")
    try:
        write_html_report(holdings, output_dir=output_dir,
                          news_top_count=news_top_count,
                          include_news=_news_ok,
                          llm_content=llm_content,
                          details=prep["details"],
                          a_indices=prep["a_indices"],
                          us_indices=prep["us_indices"],
                          news_data=news_data,
                          news_llm_meta=news_llm_meta,
                          early_warnings=early_warnings,
                          section_order=sec_order,
                          history_data=history_data, progress=reporter,
                          enable_b_series=_enable["b_series"],
                          enable_news=_enable["news"],
                          enable_history=_enable["history"],
                          enable_llm=_enable["llm"])
        result.html_ok = True
    except Exception:
        reporter.add_error("HTML 报告生成失败")
        reporter.info("继续生成 Excel 报告...")

    # Excel 报告
    from src.python.report.excel_generator import generate_excel_report
    generate_excel_report(holdings, include_news=_news_ok,
                          output_dir=output_dir,
                          news_top_count=news_top_count,
                          include_llm=_enable["llm"],
                          llm_content=llm_content,
                          details=prep["details"],
                          a_indices=prep["a_indices"],
                          us_indices=prep["us_indices"],
                          news_data=news_data,
                          news_llm_meta=news_llm_meta,
                          early_warnings=early_warnings,
                          section_order=sec_order,
                          history_data=history_data, progress=reporter,
                          f_context=f_context,
                          enable_b_series=_enable["b_series"],
                          enable_news=_enable["news"],
                          enable_history=_enable["history"],
                          enable_llm=_enable["llm"])
    result.excel_ok = True
    result.report_generated = True

    reporter.print_timing_summary()
    return result
```

#### `_fetch_llm_and_news()` — 线程池 4 分支统一封装（v2.4 修正）

**注意**：此函数**仅被 `_generate_report_full()` 调用**。both 路径不调用线程池——它的新闻由 writer 内部处理，不显式获取。此行为继承自 TUI `_cmd_generate_both`。

**★ v2.4 修正**：原 `_process_llm_news_futures()`（handlers_report.py:273-331，~59 行）+ `_cmd_generate_full()` 中 LLM-only 分支（:509-541，~33 行）存在大量重复的 ok/disabled/failed 判定逻辑。`_fetch_llm_and_news()` 统一封装全部 4 分支：

```python
def _fetch_llm_and_news(holdings, prep, f_context, enable, force_llm, reporter, sector_flow):
    """Orchestrator 内部管理线程池（仅 full 路径使用），覆盖 4 分支。

    Returns:
        (llm_content, news_data, news_llm_meta, news_ok)
        — llm_content: 4-tuple (global_macro, expert_review, health_check, penetration_deep)
        — news_data: list
        — news_llm_meta: dict
        — news_ok: bool
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_llm_news")
    try:
        news_fut = pool.submit(build_news_data, ...) if enable["news"] else None
        llm_fut = pool.submit(generate_all_llm, ...,
                               sector_flow=sector_flow,
                               force=force_llm) if enable["llm"] else None

        # ── 分支 1：LLM + 新闻均启用 → as_completed 双 Future ──
        if news_fut is not None and llm_fut is not None:
            return _await_both_futures(llm_fut, news_fut, reporter)
        # ── 分支 2：仅 LLM ──
        if llm_fut is not None:
            return _await_llm_only(llm_fut, reporter)
        # ── 分支 3：仅新闻 ──
        if news_fut is not None:
            news_data, news_llm_meta = news_fut.result()
            return (None, None, None, None), news_data, news_llm_meta, bool(news_data)
        # ── 分支 4：均关闭 ──
        reporter.info("[板块配置] 新闻和 LLM 均未开启，跳过内容生成")
        return (None, None, None, None), [], {}, False
    except KeyboardInterrupt:
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

def _await_both_futures(llm_fut, news_fut, reporter):
    """LLM + 新闻 双 Future as_completed 提取。原 _process_llm_news_futures() 逻辑。"""
    # ... 原 ~59 行逻辑，含 ok/disabled/failed 判定

def _await_llm_only(llm_fut, reporter):
    """仅 LLM 单 Future 提取。原 _cmd_generate_full():509-541 逻辑。"""
    # ... 原 ~33 行逻辑，消除与 _await_both_futures 的重复判定
```


#### `_compute_details()` — 共享明细计算（both/full 共用）

both 路径不需要完整 `prepare_report_data()`（无指数/穿透/分类），但需要 `_generate_details()` 计算的行情明细与分类。`_compute_details()` 仅封装 basic+tui_both 所需的最小数据集：

```python
def _compute_details(holdings: list, today_str: str) -> dict:
    """计算行情明细与分类（轻量级，无指数/穿透）。both 路径使用。"""
    from src.python.report.market_value import _generate_details, classify_holdings
    details = _generate_details(holdings, today_str)
    categories = classify_holdings(holdings)
    total_mv = sum(d.market_value for d in details)
    total_cost = sum(d.cost for d in details)
    total_profit = sum(d.profit for d in details)
    return {
        "details": details, "categories": categories,
        "total_mv": total_mv, "total_cost": total_cost, "total_profit": total_profit,
    }
```

而 `prepare_report_data()` 在 `_compute_details()` 基础上追加指数获取、资产穿透、holdings_details：

```python
def prepare_report_data(holdings: list, reporter: ProgressReporter) -> dict:
    """完整数据准备（full 路径使用）。包含指数、穿透、详细持仓信息。"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    base = _compute_details(holdings, today_str)

    reporter.info("正在获取指数行情...")
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_prep")
    a_fut = pool.submit(fetch_indices)
    us_fut = pool.submit(fetch_us_indices)
    a_indices = a_fut.result()
    us_indices = us_fut.result()
    pool.shutdown(wait=False)

    reporter.info("正在计算资产穿透 TOP10...")
    pen_result = compute_penetration_top10(holdings, base["details"])
    penetrated_assets = (pen_result or {}).get("top10", [])

    holdings_details = [
        {"name": d.name, "code": d.code, "market_value": d.market_value,
         "cost": d.cost, "profit": d.profit, "profit_rate": d.profit_rate,
         "nav_date": d.nav_date, "source_api": d.source_api}
        for d in base["details"]
    ]

    base.update({
        "a_indices": a_indices, "us_indices": us_indices,
        "penetrated_assets": penetrated_assets,
        "holdings_details": holdings_details,
        "today_str": today_str,
        # ★ v2.4 修正：不通过 reporter._output_dir（私有属性），output_dir 由 caller 传入
        # "output_dir": reporter._output_dir if hasattr(reporter, '_output_dir') else "reports",
    })
    return base
```

#### `prepare_report_data()` — 指数池（S6 清除 handlers_report 依赖）

`prepare_report_data()`（原 `handlers_report._prepare_report_data()`）内部使用 `_get_pool()` 提交指数并行获取任务。S6 时改为内部短生命周期池：

```python
def prepare_report_data(holdings, reporter):
    # S1~S5: 还使用 handlers_report._get_pool()（临时依赖）
    # S6 后:
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orch_prep")
    try:
        # 提交指数并行获取
    finally:
        pool.shutdown(wait=False)
```

#### `_warm_cache()` — 缓存预热辅助函数

```python
def _warm_cache(holdings: list, reporter: ProgressReporter) -> None:
    """预热缓存——仅在 warm_cache=True 时调用。

    ★ 此函数内部使用 reporter.* 输出进度，不接受 print()。
    保证 CLI --warm 模式下进度可追踪到日志/stderr。
    """
    for h in holdings:
        code = h.get("code", "")
        reporter.info(f"预热缓存: {code}")
        # 分批 fetch / cache.set 操作，按基金类型分 2~3 批次
    reporter.ok("缓存预热完成")
```

**★ C6 合规声明**（v2.5 补充）：`_warm_cache()` 内部的分批 fetch 操作调用已有的 fetcher 函数（经 Provider Chain 路由），不引入新的数据获取路径。C6 合规性由继承保证，无需新增审计项。

### 2.2 `cache/operations.py` — 缓存操作共享层

**文件路径**：`src/python/cache/operations.py`（P1-S8 新建，S9~S10 扩充）

#### 线程池策略（★ 复盘修正）

operations **从 S8 开始就创建自己的池**，不等 S11:

```python
# operations.py 内部
def _get_pool() -> ThreadPoolExecutor:
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cache_ops")
    # 不注册 atexit，函数内部 try/finally shutdown
    return pool
```

- S8: operations 创建池，`handlers_cache._POOL` 标记 **deprecated**
- S9~S10: operations 池被各函数使用，handlers_cache._POOL 仍有其他 TUI 函数使用
- S11: handlers_cache._POOL 删除，所有缓存操作走 operations 池

**为什么不等 S11**：
1. S9 的 `_refresh_common_caches()` 需要池做并行（4 类缓存并发刷新）
2. 不立即创建自己的池，S9 提取后仍依赖 handlers_cache._POOL → **模块间耦合未消除**
3. S8 创建池仅 4 worker（远小于 handlers_cache._POOL 的 8），资源占用可控

#### 数据结构

```python
@dataclass
class CacheUpdateResult:
    perf_ok: int = 0
    hold_ok: int = 0
    bm_ok: int = 0
    pf_ok: int = 0
    sf_ok: int = 0
    ind_ok: int = 0
    div_ok: int = 0
    total_funds: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if not self.total_funds:
            return 2
        if self.errors:
            return 1
        return 0

@dataclass
class PositionCacheResult:
    price_ok: int = 0
    total_holdings: int = 0
    a_indices: dict = field(default_factory=dict)
    us_indices: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if not self.total_holdings:
            return 2
        if self.errors:
            return 1
        return 0

@dataclass
class CacheStats:
    total_files: int = 0
    total_size_bytes: int = 0
    hit_rate: float = 0.0
    by_prefix: dict = field(default_factory=dict)
    top_by_size: list = field(default_factory=list)
    expired_count: int = 0
    snapshot_files: int = 0
    snapshot_size: int = 0
    state_files: int = 0
    state_size: int = 0
```

#### 核心函数

```python
def update_basic_cache(holdings: list, reporter: ProgressReporter) -> CacheUpdateResult:
    """更新基础类缓存。

    所有进度通过 reporter.* 输出，不含 print()。
    holdings 由调用方传入（CLI 直接传，TUI 传交互加载的结果）。
    使用 operations 内部池（非 handlers_cache._POOL）。
    ★ 内部先调用 clear_by_group("refresh") 清除旧缓存（匹配 TUI 行为）。
    """

def update_position_cache(holdings: list, reporter: ProgressReporter) -> PositionCacheResult:
    """★ 内部先调用 clear_by_group("preload") 清除旧缓存。"""

def cleanup_cache(reporter: ProgressReporter) -> int:
def get_cache_stats(reporter: ProgressReporter) -> CacheStats:
```

**关键设计原则**：
1. 所有函数接受 `ProgressReporter` 接口
2. 所有函数返回结构化数据，格式化输出由 TUI 外壳负责
3. `print()` → `reporter.*()`，颜色表格留在 handlers_cache.py
4. `press_any_key()` 不属于共享层
5. 线程池在 operations 内部管理，不依赖 handlers_cache._POOL
6. **★ v2.4 — `clear_by_group` 归属权统一**：`update_basic_cache()` / `update_position_cache()` 内部调用 `clear_by_group()`。TUI 外壳 `_read_holdings_and_clear_cache()` **不再主动清除缓存**，避免双重清除。
7. **★ v2.4 — `_refresh_common_caches()` 的 print 在 `as_completed` 循环内**，替换为 reporter.* 时需重构循环体：先收集结果→再用 reporter 输出→最后返回结构化数据。

### 2.3 `cli.py` — argparse 主入口

**文件路径**：`src/python/cli.py`（P2-C1 新建，C2~C9 逐步充实）

#### 路径初始化

```python
import os, sys
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_project_root)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
```

#### 解析器定义

```python
import argparse
from src.python.constants import APP_VERSION

_EXIT_SUCCESS = 0
_EXIT_PARTIAL = 1
_EXIT_SEVERE = 2

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="investor-util",
        description="个人投资分析报告生成工具 — 命令行模式",
        epilog="示例: python -m src.python.cli report --type full --history auto",
    )
    # ★ 全局参数
    parser.add_argument("--config", metavar="PATH",
                        help="备用配置文件路径（默认: data/config/config.json）")
    parser.add_argument("--output", metavar="DIR",
                        help="报告输出目录（覆盖 config.json 的 output_dir）")
    parser.add_argument("--verbose", action="store_true",
                        help="将进度消息同步到 stderr（默认仅写入 logs/app.log）")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s v{APP_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── report 子命令 ──
    report_p = sub.add_parser("report", help="生成投资分析报告")
    report_p.add_argument(
        "--type", choices=["basic", "both", "full"], default="basic",
        help="报告类型: basic=仅Excel(≈1min, 默认), both=HTML+Excel(不含LLM,≈2min), "
             "full=全量含LLM(≈5min, 定时任务按需开启)",
    )
    report_p.add_argument(
        "--history", choices=["auto", "off"], default="off",
        help="获取组合历史走势数据: auto=获取, off=跳过（默认; 仅 --type both/full 时有效）",
    )
    report_p.add_argument("--force-llm", action="store_true",
                          help="强制重新生成 LLM 内容（跳过缓存）")
    report_p.add_argument("--warm", action="store_true",
                          help="预热新资产缓存（冷启动时使用）")

    # ── cache 子命令 ──
    cache_p = sub.add_parser("cache", help="缓存管理")
    cache_action = cache_p.add_mutually_exclusive_group(required=True)
    cache_action.add_argument("--update", choices=["basic", "position", "all"],
                              help="更新缓存: basic=基础类, position=持仓类, all=全部")
    cache_action.add_argument("--clean", action="store_true",
                              help="清理过期缓存文件")
    cache_action.add_argument("--stats", action="store_true",
                              help="查看缓存文件统计/状态")
    cache_p.epilog = (
        "示例:\n"
        "  cache --update all             更新全部缓存\n"
        "  cache --update basic           仅更新基础类缓存\n"
        "  cache --clean                  清理过期缓存\n"
        "  cache --stats                  查看缓存统计"
    )
    return parser
```

#### argparse 设计决策

| 决策 | 理由 |
|:-----|:------|
| `--type` 默认 `basic` | 确保 cron 稳定运行不依赖 LLM API 可用性；需引用全量报告时主动加 `--type full` |
| `--history` 默认 `off` | 历史走势获取需 ~3-5 秒，定时任务用户按需开启；仅 `--type both/full` 时有意义 |
| `--history` 帮助含"仅 both/full 有效" | 避免用户 `report --type basic --history auto` 时困惑（basic 不含 HTML，无走势图） |
| `--config` help 含默认路径 | 用户需知工具查找配置的默认位置 |
| `--verbose` 明确"默认仅写日志" | cron 用户需知不传此参数时终端无输出；交互终端时 **自动开启**（`stderr.isatty()`） |
| `--version` 读取 `constants.APP_VERSION` | 与 `pyproject.toml`, `README.md` 版本号一致 |
| `epilog` 全局 + cache 子命令各含示例 | 用户无需再查独立文档 |
| 子命令 `required=True` | 无子命令时报错 exit 2，不静默 |
| cache 子命令 `--update`/`--clean`/`--stats` 互斥组 | `required=True` 确保用户明确操作意图，避免空命令 |
| **`init_config(config_path)` 修改（v2.4）** | 向后兼容：`config_path=None` 走默认路径，TUI 调用方无需改动 |

#### main() + 子命令路由

```python
def main() -> int:
    from src.python.logger import setup_logger
    setup_logger()
    parser = _build_parser()
    args = parser.parse_args()

    from src.python.config import init_config, get_config
    init_config(config_path=args.config)
    config = get_config()

    if args.command == "report":
        return _handle_report(args, config)
    elif args.command == "cache":
        return _handle_cache(args, config)
    return _EXIT_SEVERE

def _handle_report(args, config) -> int:
    from src.python.report.cli_progress import CliProgressReporter
    from src.python.report.orchestrator import generate_report

    reporter = CliProgressReporter(verbose=args.verbose)
    holdings = _cli_read_holdings(config)
    if not holdings:
        reporter.error("无法读取持仓数据，报告生成终止")
        return _EXIT_SEVERE

    result = generate_report(
        holdings=holdings, config=config, reporter=reporter,
        report_type=args.type, history_mode=args.history,
        force_llm=args.force_llm, output_dir=args.output,
        warm_cache=args.warm,
    )
    return result.exit_code

def _handle_cache(args, config) -> int:
    from src.python.report.cli_progress import CliProgressReporter
    from src.python.cache import operations as ops

    reporter = CliProgressReporter(verbose=args.verbose)

    if args.clean:
        n = ops.cleanup_cache(reporter)
        return _EXIT_SUCCESS
    if args.stats:
        stats = ops.get_cache_stats(reporter)
        return _EXIT_SUCCESS

    holdings = _cli_read_holdings(config)
    if not holdings:
        return _EXIT_SEVERE

    final_exit = _EXIT_SUCCESS   # ★ v2.5 新增：--update all 最大努力退出码

    if args.update in ("basic", "all"):
        result = ops.update_basic_cache(holdings, reporter)
        final_exit = max(final_exit, result.exit_code)    # ★ v2.5 最大努力：记录最严重退出码
    if args.update in ("position", "all"):
        result = ops.update_position_cache(holdings, reporter)
        final_exit = max(final_exit, result.exit_code)    # ★ v2.5 最大努力：position 即使 basic 失败也执行
    return final_exit


def _cli_read_holdings(config: dict) -> list | None:
    """CLI 专属持仓读取——跳过文件选择交互。"""
    import os, logging
    from src.python.reader import read_holdings

    logger = logging.getLogger("invest")
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        import logging
        logging.getLogger("invest").info("CLI 操作被用户中断")
        sys.exit(130)
    except Exception:
        import logging
        logging.getLogger("invest").exception("CLI 未处理异常")
        sys.exit(2)
```

### 2.4 `report/cli_progress.py` — CliProgressReporter

与 v2.0 设计一致，**额外架构变更**（v2.4 复盘修正）：

**★ 基类 `print_timing_summary()` 接口补充**：当前 `ProgressReporter` 基类（`report/progress.py:41`）未定义 `print_timing_summary()` 方法，但 orchestrator 的三个报告路径均调用 `reporter.print_timing_summary()`。需在基类中添加空壳方法，确保 `SilentProgressReporter` 兼容。

**★ C8 边界说明**（v2.5 复盘补充）：`_cprint()` 的 verbose stderr 输出属于**交互式进度展示**，不是日志体系的一部分——等同于 TUI 的 `print()`。C8 约束仅覆盖持久化应用日志（统一走 `logging.getLogger("invest")`），不约束终端进度展示。`_cprint()` 不违反 C8。

核心要点：

```python
# CLI 本地颜色常量（不依赖 ansi_colors 模块级 stdout.isatty()）
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"

def _should_color() -> bool:
    """stderr TTY + NO_COLOR 判断（C15）。"""
    if "NO_COLOR" in os.environ:
        return False
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
```

#### 方法行为对照

| 方法 | TuiProgressReporter | CliProgressReporter |
|:-----|:-------------------|:--------------------|
| `__init__(verbose)` | — | `verbose=None` → 自动: TTY 时 True，管道/cron 时 False |
| `info(msg)` | print + CYAN | 始终 `logger.info(msg)`；verbose 时同时 `stderr msg` |
| `ok(msg)` | print + GREEN | 始终 `logger.info(msg)` **无前缀**；verbose 时 `stderr [OK] msg` |
| `warn(msg)` | print + YELLOW | `logger.warning(msg)` **无前缀**；verbose 时 `stderr [!] msg` |
| `error(msg)` | print + RED | `logger.error(msg)` **无前缀**；verbose 时 `stderr [ERR] msg` |
| `call_sheet(label, fn)` | print 实时进度 | 始终计时；verbose 时 `stderr [..] label...` → `[OK] label X.XXs` |
| `print_timing_summary()` | print + █░ 进度条 | `logger.info` 逐行输出（见下方格式定义）|

#### 设计决策

**① 日志前缀策略（避免冗余）**
`logger.py` 的 `_ColoredFormatter` 已输出 `[%(levelname)s]`（如 `[INFO]`, `[WARNING]`, `[ERROR]`），因此 CliProgressReporter 的日志输出**不再加** `[OK]`/`[!]`/`[ERR]`/`[..]` 前缀，避免日志行出现 `[INFO] [OK] ...` 的冗余。verbose stderr 输出保留前缀，因 stderr 无日志等级信息。

```python
# 日志输出（进入日志文件）— 不加前缀
logger.info("已完成市场数据获取")       # 日志: 2026-07-16 [INFO] 已完成市场数据获取
logger.warning("部分数据不可用")        # 日志: 2026-07-16 [WARNING] 部分数据不可用

# verbose stderr 输出（终端可见）— 保留前缀
if self._verbose:
    _cprint("  [OK] 已完成市场数据获取", _GREEN)
    _cprint("  [!] 部分数据不可用", _YELLOW)
```

**② `--verbose` 自动启用规则**
- 默认行为（不传 `--verbose`）：`stderr.isatty()` 为 True 时自动 verbose，cron/管道/重定向时静默
- `--verbose` 强制开启：无论 TTY 状态都输出到 stderr
- `NO_COLOR` 环境变量：抑制颜色转义，不影响 verbose 开关

```python
class CliProgressReporter(ProgressReporter):
    def __init__(self, verbose: bool | None = None):
        super().__init__()
        self._logger = logging.getLogger("invest")
        if verbose is None:
            # 自动检测：终端时 verbose，否则静默
            self._verbose = self._auto_verbose()
        else:
            self._verbose = verbose
        self._color = _should_color()

    @staticmethod
    def _auto_verbose() -> bool:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
```

**③ `call_sheet()` verbose 执行过程**
verbose 模式时同步输出到 stderr：
```
  [..] 正在获取基金业绩数据...
  [OK] 基金业绩数据获取完成（2.35s）
```
非 verbose 模式仍计时，不输出到 stderr。

**④ `print_timing_summary()` 输出格式定义**
```
logger.info("━━━ 计时汇总 ━━━")
for label, elapsed in self._sorted_timing():
    bar = "█" * int(elapsed * 10) + "░" * (20 - int(elapsed * 10))
    logger.info("  %-24s %s %6.2fs", label, bar, elapsed)
logger.info("━━━━━━━━━━━━━━━━")
```
- 始终写入 `logs/app.log`（`logging.INFO`）
- verbose 模式同步输出到 stderr（含颜色 bar）
- 非 verbose 模式仅写入日志，stderr 无输出
- 日志中不含颜色转义字符（logger 的 `_ColoredFormatter` 自行处理等级着色）

---

## 3. TUI 函数修改方案

### 3.1 handlers_report.py 变薄

**P1 后的最终形态**（~220 行 → ~60 行）。参见迭代计划 S7 章节。

**删除的函数与循环依赖预防**：

| 函数 | 移至 | 备注 |
|:-----|:------|:------|
| `_prepare_report_data()` | `orchestrator.prepare_report_data()` | |
| `_capture_snapshot()` | `orchestrator.capture_snapshot()` | |
| `_compute_early_warnings()` | `orchestrator.compute_early_warnings()` | |
| `_fetch_history_data()` | 分拆：input 在 TUI，业务在 orchestrator | |
| `_get_pool()` + `_POOL` | 删除（orchestrator 内部管理池） | S6 后无引用 |
| `_generate_excel_report()` | **保留至 S12 评估** | 但 orchestrator 不用它（直接调 excel_generator），仅 TUI 其他引用方 |

### 3.2 handlers_cache.py 变薄

**P1 后的最终形态**（~456 行 → ~80 行）。参见迭代计划 S11 章节。

**池清理**：
- `handlers_cache._POOL` 从 S8 起标记 deprecated
- S8~S10 期间仍有 TUI 代码使用，S11 删除
- operations 内部池使用 `_get_pool()` 模式但局部 try/finally，不注册 atexit

### 3.3 tui_handlers.py / tui_menu.py

**不修改**。CLI 不调用这些模块的任何函数。

---

## 4. 交互降级对照表

审计 `src/python/` 下所有 `input()` / `get_key()` 调用。

| # | 文件 | 函数 | 交互类型 | TUI 行为 | CLI 替代方案 |
|:-:|:-----|:-----|:---------|:---------|:------------|
| 1 | `handlers_report.py` | `_prompt_force_llm()` | `input()` | 询问 y/N | `--force-llm` 标志 → bool |
| 2 | `tui_handlers.py` | `select_holdings_file()` | `get_key()` | 文件选择器 | `_cli_read_holdings()` |
| 3 | `tui_handlers.py` | `press_any_key()` | `get_key()` | 等待任意键 | CLI 不调用 |
| 4 | `tui_handlers.py` | `prepare_holdings()` | `get_key()` | 文件选择+预热 | `_cli_read_holdings()` |
| 5 | `tui_handlers.py` | `finish_report()` | `get_key()` | 耗时汇总+等待 | CLI 不调用 |
| 6 | `handlers_cache.py` | `press_any_key()` | `get_key()` | 命令末尾等待 | CLI 不调用 |

**审计命令**（同时搜索 input 和 get_key）：
```bash
grep -rn "\binput(" src/python/ --include="*.py" | grep -v test | grep -v __pycache__
grep -rn "\bget_key(" src/python/ --include="*.py" | grep -v test | grep -v __pycache__
```

**结论**：6 个交互点全部有替代方案。CLI 永不进入终端原始模式。

---

## 5. 退出码设计

### 5.1 退出码定义

```python
_EXIT_SUCCESS = 0    # 成功
_EXIT_PARTIAL = 1    # 部分失败（报告/缓存已生成/更新）
_EXIT_SEVERE = 2     # 严重错误（报告/缓存未生成/更新）
```

### 5.2 report 子命令

| 场景 | exit code | 说明 |
|:-----|:----------|:------|
| 完整报告成功生成 | 0 | |
| Excel 成功 + HTML 失败 | 1 | |
| Excel 成功 + LLM 部分失败 | 1 | |
| 行情部分获取失败 + 报告仍生成 | 1 | |
| 新闻获取失败 + 报告仍生成 | 1 | |
| 历史走势获取失败 + 报告仍生成 | 1 | |
| LLM disabled（配置关闭） | 0 | 非失败 |
| LLM key 缺失（--type full 降级） | 1 | 报告仍生成 |
| 持仓文件不存在 | 2 | |
| config.json 格式错误 | 2 | |
| 未处理异常 | 2 | |
| KeyboardInterrupt | 130 | POSIX 标准 |

### 5.3 cache 子命令

| 场景 | exit code |
|:-----|:----------|
| 所有缓存成功更新 | 0 |
| 部分缓存模块失败 | 1 |
| 缓存目录不可访问 | 2 |

退出码由数据结构（`ReportResult.exit_code` / `CacheUpdateResult.exit_code`）直接提供。C8 硬化补全 `_handle_cache()` 中的映射。

---

## 6. 与 TUI 的共享/隔离策略

| 组件 | 策略 | 说明 |
|:-----|:------|:------|
| `init_config()` | **共享** | CLI 支持 `--config` 参数 |
| `get_config()` | **共享** | CLI 直接调用 |
| `report/orchestrator.py` | **共享** | **不导入 handlers_report**（循环依赖预防） |
| `cache/operations.py` | **共享** | 内部池独立管理 |
| `ProgressReporter` | **接口共享** | 基类 + Tui/Cli 子类 |
| `CliProgressReporter` | **CLI 专属** | logging + verbose stderr |
| `TuiProgressReporter` | **TUI 专属** | print + ANSI |
| `_cli_read_holdings()` | **CLI 专属** | 跳过预热，可选 `--warm` |
| `prepare_holdings()` | **TUI 专属** | CLI 不调用 |
| `finish_report()` | **TUI 专属** | CLI 不调用 |
| `handlers_report.py` | **TUI 薄包装** | ~60 行，input + 调 orchestrator |
| `handlers_cache.py` | **TUI 薄包装** | ~80 行，交互 + 格式化 |
| orc 线程池 | **隔离** | S5 内部池：`orch_llm_news`(2w) |
| orc 指数池 | **隔离** | S6 内部池：`orch_prep`(2w) |
| ops 缓存池 | **隔离** | S8 内部池：`cache_ops`(4w) |
| handlers_report._POOL | **删除** | S6 后无引用 |
| handlers_cache._POOL | **删除** | S11 后无引用 |

**★ C4 多进程隔离验证**（v2.5 补充）：上表中的"隔离"策略依赖一个隐含前提——CLI 和 TUI 运行在**不同操作系统进程**中。`DataSourceRegistry` 是进程级单例（`provider_registry.py:110`），`timing_records` 是模块级全局变量（`progress.py:19`），共享层未使用文件/进程间通信。CLI 单次执行与 TUI 的会话状态完全隔离，无冲突风险。同理，`handlers_report._POOL` / `handlers_cache._POOL` 等 atexit 注册的线程池在 CLI 执行结束后自然释放。

### P1 消除的关键依赖

| 依赖 | P1 前 | P1 后 |
|:-----|:------|:------|
| `handlers_report._POOL` | 4w, atexit | **删除** |
| `handlers_cache._POOL` | 8w, atexit | **删除** |
| `tui_menu.get_config_cache()` | TUI handlers_report 读配置 | orchestrator 从 config 参数读 |
| `handlers_report._generate_excel_report()` | handlers 包装 | orchestrator 直接调 excel_generator |

### 6.2 config 覆写线程安全性分析（★ v2.5 新增）

**情景分析**：`set_config_path_override()` + `init_config(config_path)` 在 CLI 多线程上下文中是否安全？

| 访问模式 | 时序 | 线程安全性 |
|:---------|:------|:----------|
| `init_config()` 调 `set_config_path_override()` | 主线程顺序 | ✔ 同线程无竞争 |
| orchestrator 内部线程读 config 参数 | 初始化完成后 | ✔ **参数传递**而非全局 `get_config()` 调用 |
| orchestrator 深度调用链（fetcher/cache）读 config | 初始化完成后 | ✔ fetcher/cache 不从 orchestrator 接收 config，读自身的全局 `get_config()`——但 `_config_cache` 在 init 后无写入 |
| TUI `set_config()` 写 config | CLI 不触发 | ✔ CLI 无配置编辑菜单 |
| 两个 CLI 实例同时运行 | **不同进程** | ✔ 进程隔离 |

**结论**：CLI 的 config 覆写模式在单进程单线程初始化 + 参数传递模式下完全线程安全。无需加锁。

**★ C14 残余风险**：orchestrator 收到的 `config` 参数是 `_config_cache` 的 dict 引用。orchestrator 必须保持只读使用，不得 mutate dict。技术设计已在 C14 行标注"不写模块级 dict"，但需在 orchestrator 代码注释中补强此约束。

### C6 Provider Chain 合规审计清单

P1 提取后，orchestrator/operations 中所有 fetcher 调用均经 Provider Chain 或属已文档化例外：

| orchestrator 函数 | fetcher 调用 | Chain 合规 | 说明 |
|:-------------------|:-------------|:-----------|:------|
| `prepare_report_data()` | `fetch_market_data()` (price.py) | ✔ `fetch_with_fallback()` | 标准 Provider Chain 路由 |
| `prepare_report_data()` | `fetch_indices()` / `fetch_us_indices()` (index.py) | ✔ 已文档化例外 | technical.md §2.2：指数数据双链路 fallback 硬编码 |
| `capture_snapshot()` | `HistoryDiff` | N/A | 纯差异计算，非数据获取 |
| `compute_early_warnings()` | 纯计算 | N/A | 调用 `report.early_warning.compute_early_warnings()` |
| `fetch_history_data()` | `PortfolioHistoryCalculator` | N/A | 基于缓存的组合计算 |
| `_fetch_llm_and_news()` → `build_news_data()` | news providers | ✔ 经 Chain 路由 | news_aggregator.py 使用 Provider Chain 获取各源新闻 |
| `_fetch_llm_and_news()` → `generate_all_llm()` | LLM API | ✔ 经 `http_client.py` | LLM 调用通过统一 HTTP 客户端 |

**审计结论**：orchestrator 不引入新的数据获取路径，C6 合规性由继承保证。

---

### 6.1 P1→P2 接口冻结合约（★ v2.5 新增）

P1 完成后以下接口进入冻结状态，P2 实现不得修改其签名。参见迭代计划对应章节。

| 模块 | 函数 | 签名 | 返回 |
|:-----|:------|:------|:------|
| `orchestrator` | `generate_report` | `(holdings, config, reporter, report_type, history_mode, force_llm, output_dir, warm_cache)` | `ReportResult` |
| `orchestrator` | `prepare_report_data` | `(holdings, reporter)` | `dict` |
| `orchestrator` | `capture_snapshot` | `(holdings, details, reporter)` | `dict\|None` |
| `orchestrator` | `compute_early_warnings` | `(holdings, penetrated_assets, sector_flow, news_data, news_llm_meta, reporter)` | `list` |
| `orchestrator` | `fetch_history_data` | `(holdings, config, reporter, mode)` | `dict\|None` |
| `operations` | `update_basic_cache` | `(holdings, reporter)` | `CacheUpdateResult` |
| `operations` | `update_position_cache` | `(holdings, reporter)` | `PositionCacheResult` |
| `operations` | `cleanup_cache` | `(reporter)` | `int` |
| `operations` | `get_cache_stats` | `(reporter)` | `CacheStats` |

**冻结时点**：S12 regression/dev-verify/scenario 全绿 + config 等值验证通过 + 跨模块导入审计无残留引用。

**解冻流程**：review-findings.md 记录 → P2 暂停依赖轮次 → 回归全绿 → 同步文档 → 恢复。

---

## 7. 测试策略

### 7.1 测试文件清单

| 文件 | marker | 作用域 |
|:-----|:-------|:-------|
| `test_cli.py` | `@pytest.mark.unit` + `@pytest.mark.unit_cli` | 参数解析、mock 分发、退出码 |
| `test_cli_edge.py` | `@pytest.mark.edge` + `@pytest.mark.unit_cli` | 边界/异常场景 |
| `test_cli_integration.py` | `@pytest.mark.integration` + `@pytest.mark.unit_cli` | 日志、着色降级、配置共享 |
| `test_orchestrator.py` | `@pytest.mark.unit` | 报告编排各路径（P1-S1 建骨架） |
| `test_cache_operations.py` | `@pytest.mark.unit` | 缓存操作共享函数 |

### 7.2 Mock 策略（★ v2.5 补充 S2 测试维度）

`capture_snapshot()` 的 5 个子步骤测试需分别 mock ：

| 子步骤 | 依赖 | mock 方式 |
|:-------|:------|:----------|
| SnapshotHolding 映射 | `schemas.history.SnapshotHolding` | 验证字段映射，不 mock 构造 |
| holdings 回查 | 无外部依赖 | 纯数据遍历，无需 mock |
| SnapshotData 创建 | `schemas.history.SnapshotData` | 验证聚合计算，不 mock 构造 |
| HistoryDiff 计算 | `fetcher.history_diff.HistoryDiff` | `mocker.patch` 计算 + compute 返回值 |
| prune | `history_snapshot.save/prune` | `mocker.patch` 跳过 IO |
| f_context 组装 | 无外部依赖 | 纯字典操作，无需 mock |

| 依赖 | mock 方式 |
|:-----|:----------|
| `generate_report()` | `mocker.patch` → `ReportResult` |
| `update_basic_cache()` | `mocker.patch` → `CacheUpdateResult` |
| `_cli_read_holdings()` | `mocker.patch` → list / None |
| `init_config()` | `mocker.patch` → 跳过文件 |
| `sys.exit()` | `pytest.raises(SystemExit)` |
| `sys.stderr` | `capsys` / `capfd` |
| `logging` | `caplog` |

### 7.3 覆盖目标

| 维度 | 目标 |
|:-----|:------|
| `cli.py` 行覆盖率 | ≥ 90% |
| `orchestrator.py` 行覆盖率 | ≥ 85% |
| `operations.py` 行覆盖率 | ≥ 85% |
| `cli_progress.py` 行覆盖率 | ≥ 95% |
| 退出码场景覆盖 | 全部 ~12 种 |

---

## 8. 架构设计约束校验清单

| 约束 | 内容 | 满足情况 | 验证方式 |
|:-----|:-----|:---------|:---------|
| **C1** | 代码类型判定中心化 | ✔ 不涉及 | 无 `startswith`/`in` 判定 |
| **C2** | 缓存统一管理 | ✔ 通过 cache/ 子包接口 | cache 子命令使用 `cache.get()/set()` |
| **C3** | 缓存原子写入 | ✔ 不新增写入路径 | 无直接 `open()+write()` 到 `data/cache/` |
| **C4** | 会话级 API 复用 | ✔ CLI 单次执行不与 TUI 冲突 | 不修改 DataSourceRegistry |
| **C5** | HTTP 客户端统一 | ✔ 不新增 HTTP 调用 | 调用的 fetcher/ 已使用统一客户端 |
| **C6** | Provider Chain 必经 | ✔ 调用链不变 | P1 每轮审计确认 orchestrator 中所有 fetcher 调用仍经过 Chain |
| **C7** | 报告序号可配置 | ✔ 共享 `get_report_section_order()` | CLI 不允许硬编码序号 |
| **C8** | 日志统一 | ✔ CliProgressReporter 使用 `logging.getLogger("invest")` | 测试验证 logger name |
| **C9** | LLM 模块注册 | ✔ 不涉及新增 LLM 模块 | 仅调用现有 `generate_all_llm()` |
| **C10** | 新闻召回策略可配置 | ✔ 不修改新闻获取逻辑 | 调用 `build_news_data()` 参数不变 |
| **C11** | 测试标记强制 | ✔ 所有测试标记注册 | conftest.py 注册 + pytest 收集验证 |
| **C12** | 边缘测试文件隔离 | ✔ `test_cli_edge.py` 隔离 | `pytest_collection_modifyitems` 校验 |
| **C13** | 测试敏感路径隔离 | ✔ 自动由 conftest.py 保障 | autouse fixture 无需配置 |
| **C14** | 渲染期数据不可写全局 | ✔ CLI 不新增渲染路径 | 不写模块级 dict |
| **C15** | 控制台日志着色降级 | ✔ `_should_color()` 使用 `os.environ` + `NO_COLOR`/`isatty(stderr)` | CLI 测试 |

---

## 9. 文件清单与变更统计

### 9.1 新增文件

| 文件 | 在哪个迭代 | 预估行数 | 说明 |
|:-----|:----------|:---------|:------|
| `src/python/report/orchestrator.py` | P1-S1~S6 | ~200 | 报告编排共享层（**不导入 handlers_report**） |
| `src/python/cache/operations.py` | P1-S8~S10 | ~200 | 缓存操作共享层（**内部管理池**） |
| `src/python/cli.py` | P2-C1~C9 | ~170 | argparse + 路由 + 持仓读取 + 退出码（含 `--warm`） |
| `src/python/report/cli_progress.py` | P2-C2 | ~110 | CliProgressReporter |
| `src/test/test_cli.py` | P2-C10 | ~350 | CLI 单元测试 |
| `src/test/test_cli_edge.py` | P2-C10 | ~150 | CLI 边界测试 |
| `src/test/test_cli_integration.py` | P2-C11 | ~100 | CLI 集成测试 |
| `src/test/test_orchestrator.py` | P1-S1 | ~150 | orchestrator 单元测试（P1-S1 建骨架，P2-C10 完善） |
| `src/test/test_cache_operations.py` | P2-C10 | ~100 | operations 单元测试 |
| `docs-stm/manuals/how-to-schedule.md` | P2-C12 | ~200 | 定时任务文档 |

### 9.2 修改文件

| 文件 | 在哪个迭代 | 变更说明 |
|:-----|:----------|:---------|
| `src/python/config/_config_defaults.py` | P2-C1 | 新增 `set_config_path_override()` |
| `src/python/config/_core.py` | P2-C1 | `init_config(config_path=None)` |
| `src/python/config/__init__.py` | P2-C1 | 导出 `set_config_path_override` |
| `src/python/handlers_report.py` | P1-S7 | 变薄~60 行（删除 _POOL/_get_pool 等） |
| `src/python/handlers_cache.py` | P1-S11 | 变薄~80 行（删除 _POOL/_get_pool） |
| `src/test/conftest.py` | P2-C10 | 注册 `unit_cli` marker |

### 9.3 与 v2.0 的架构差异（复盘修正）

| 维度 | v2.0（审查前） | v2.1~v2.3（修正后） |
|:-----|:--------------|:------------------|
| 循环依赖 | orchestrator → handlers_report → excel_generator | **已修复**：orchestrator → excel_generator |
| S5+S6 both+full | 分两轮（串行→并行重写） | **合并**：一次性提取 both+full 含线程池 |
| operations 池策略 | S9 提取后仍依赖 handlers_cache._POOL，S12"评估" | S8 即创建内部池，S11 删除旧池 |
| P1 测试 | 11 轮无新增测试 | **S1 建 test_orchestrator 骨架**，每轮扩展 |
| C8 退出码硬化 | 表述模糊，代码变更不明 | **明确定义**：补 _handle_cache 退出码映射 + 全场景测试 |
| C9 交互审计 | 只搜 `input\b` | **同时搜** `input(` 和 `get_key(` |
| 冷启动风险 | 未提及 | **新增**：`--warm` 标志 + 风险矩阵条目 |
| Config 等值验证 | 未提及 | **新增**：S12 + C9 验证步骤 |
| 收益表 | S4~S6 合并为一行 | **分开**：每轮独立可见性 |

**v2.4 追加变更**（第 4 轮复盘）：

| 维度 | v2.3（审查前） | v2.4（修正后） |
|:-----|:---------------|:---------------|
| `_capture_snapshot` 规模 | 估算 ~15 行 | **修正**：实际 ~83 行，S2 按真实规模评估 |
| `_process_llm_news_futures` | 未在计划中提及 + LLM-only 分支 ~33 行重复代码 | **统一**：`_fetch_llm_and_news()` 封装全部 4 分支 |
| TUI 专属函数处理 | 未明确标注 orchestrator 禁区 | **追加**：check_network_available / print_llm_session_usage / get_config_cache 列为 TUI-only |
| `reporter._output_dir` | 伪代码中通过私有属性获取 output_dir | **修正**：output_dir 作为参数传入 |
| `clear_by_group` 归属 | TUI 外壳 + operations 双重清除 | **统一归 operations**：TUI 外壳不再主动清除 |
| `ProgressReporter.print_timing_summary()` | 基类无此方法 | **追加**：基类增加空壳方法，子类覆盖 |
| `init_config(config_path)` | 未分析波及范围 | **分析**：向后兼容，TUI 调用方无需改动 |
| `_refresh_common_caches` print→reporter | 简单替换描述 | **更正**：print 在 as_completed 循环内，需重构循环体 |

**v2.5 追加变更**（第 5~10 轮复盘修正）：

| 维度 | v2.4（审查前） | v2.5（修正后） |
|:-----|:---------------|:---------------|
| C8 _cprint() 边界 | 未讨论 C8 是否覆盖 _cprint | **界定**：交互式进度展示 ≠ 日志体系，C8 仅覆盖持久化日志 |
| C4 进程隔离 | 隐性依赖"不同进程"前提 | **显式验证**：DataSourceRegistry 进程级单例，CLI/TUI 无冲突 |
| C6 _warm_cache 路径 | 未做合规声明 | **补充**：内部 fetch 调用已有 Chain 路由，C6 继承保证 |
| S2 测试粒度 | "验证快照结果一致"泛泛一句 | **细化**：8 用例覆盖 SnapshotHolding 映射→回查→SnapshotData→HistoryDiff→prune→f_context→异常→首次运行 |
| S6 4 分支覆盖 | "均可正确返回"泛泛一句 | **细化**：6 用例（both/llm-only/news-only/disabled/llm 降级/线程池清理）|
| 接口冻结流程 | "P1-S12 回归后冻结"无具体约束 | **形式化**：冻结签名表 + 冻结时点 + 解冻流程 |
| cache --update all 失败处理 | basic 失败直接 return，position 被跳过 | **最大努力**：basic 失败后 position 仍执行，退出码聚合 |
| config 线程安全 | 未分析 | **分析**：单线程初始化 + 参数传递模式安全；C14 残余风险标注 |
| 测试时间预算 | 未估算 | **新增**：每轮 ≤5~20s，S12/C12 ≤90s |
| 价值静默期 | 未分析 | **新增**：15 轮无产出期间统计 + C4 价值拐点 + 并行化建议 |

---

## 版本记录

| 版本 | 日期 | 变更说明 |
|:-----|:-----|:---------|
| v0.1~v0.4 | - | 旧方案（参数化 + cli_handlers_* 中介模块，已废弃） |
| v2.0 | 2026-07-16 | 共享层架构版：orchestrator/operations |
| **v2.1** | 2026-07-16 | **复盘审查修正**：修复循环依赖；合并 S5+S6；S8 即建池；P1 追加测试；新增 --warm；C8 明确定义；get_key 审计；config 等值验证 |
| **v2.2** | 2026-07-16 | **第 2 轮复盘修正**：新增 C6 Provider Chain 合规审计清单；S6/S11 追加跨模块导入审计步骤；验证 S1-S7 和 S8-S11 两条链独立 |
| **v2.3** | 2026-07-16 | **第 3 轮复盘修正**（CLI 细节深挖）：① `--type` 默认改为 `basic`（cron 安全）；② `--history` 帮助标注仅与 both/full 配合；③ cache 子命令 epilog；④ argparse 设计决策表补充；⑤ CliProgressReporter 日志前缀策略（无冗余 `[OK]`）；⑥ `--verbose` 自动启用规则（TTY 检测）；⑦ `print_timing_summary()` 格式定义；⑧ `call_sheet()` verbose 执行过程定义；⑨ 错误消息文案改进（持仓文件缺列名提示）；⑩ `_warm_cache` 内使用 reporter.* 而非 print() |
| **v2.4** | 2026-07-16 | **第 4 轮复盘修正**（全量代码对比审计 12 项）：① `capture_snapshot()` 规模修正（~83 行 vs 估算 ~15 行）；② `_fetch_llm_and_news()` 4 分支统一封装（消除 `_process_llm_news_futures` + LLM-only 分支重复）；③ orchestrator 核心原则追加 TUI 专属函数黑名单（check_network_available / print_llm_session_usage / get_config_cache）；④ `prepare_report_data()` 移除 `reporter._output_dir` 私有属性访问；⑤ operations 设计原则追加 `clear_by_group` 归属权统一 + `_refresh_common_caches` 循环重塑；⑥ `ProgressReporter` 基类追加 `print_timing_summary()` 空壳接口；⑦ `init_config(config_path)` 波及分析；⑧ argparse 决策表追加兼容性行；⑨ `CacheStats` 确认已有 snapshot/state 字段（v2.3 已覆盖）；⑩ 文档全线同步 v2.4 |
| **v2.5** | 2026-07-16 | **第 5~10 轮复盘修正**：① §2.4 C8 _cprint() 边界声明（交互式进度展示≠日志）；② §6 C4 多进程隔离显式验证；③ §2.1 C6 _warm_cache 预热链路合规注释；④ §7.2 S2 capture_snapshot 5 子步骤 mock 策略表；⑤ 新增 §6.1 P1→P2 接口冻结合约（签名表+冻结时点+解冻流程）；⑥ §6.2 config 覆写线程安全性分析+C14 残余风险标注；⑦ §2.3 cache --update all 最大努力退出码模式；⑧ §9.3 追加 v2.5 差异维度表 |
