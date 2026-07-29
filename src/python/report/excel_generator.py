"""Excel 报告生成核心函数。

通过 ProgressReporter 接口输出进度，不依赖 TUI。
"""

from __future__ import annotations

from typing import Any

from src.python.logger import setup_logger
from src.python.registry import get_report_section_order
from src.python.report.excel_b_series import write_b_series_sheets
from src.python.report.excel_content_sheets import write_content_sheets
from src.python.report.excel_llm_usage import write_llm_section_and_usage
from src.python.report.excel_market_data import resolve_indices, resolve_market_data
from src.python.report.excel_module_loader import load_report_modules
from src.python.report.excel_news_warning import write_news_sheet
from src.python.report.excel_sheet_factory import create_sheets
from src.python.report.progress import ProgressReporter, SilentProgressReporter, Timer

logger = setup_logger()


# ── 组合历史走势 + 回撤分析页签写入 ──────────────────────


def _write_portfolio_history_sheet(ws, history_data: dict) -> None:
    """写入组合历史走势页签（含基准指数归一化列）。"""
    from src.python.report.excel_writer import (
        _write_placeholder,
        auto_width,
        freeze_header,
        write_data_row,
        write_header_row,
        write_title_row,
    )
    from src.python.report.styles import FMT_MONEY, FMT_PERCENT

    if history_data is None:
        _write_placeholder(ws, "组合历史走势数据暂不可用（配置或网络原因）", max_cols=5)
        auto_width(ws)
        return

    bars = history_data.get("bars", [])
    if not bars:
        _write_placeholder(ws, "组合历史走势数据暂不可用（配置或网络原因）", max_cols=5)
        auto_width(ws)
        return

    benchmarks = history_data.get("benchmarks", [])
    first_value = bars[0]["total_value"] if bars and bars[0].get("total_value") else 0
    n_bm = len(benchmarks)
    ncols = 4 + n_bm  # 日期 + 市值 + 收益(%) + 归一化(%) + N 基准

    headers = ["日期", "组合市值", "组合收益(%)", "组合归一化(%)"]
    for bm in benchmarks:
        headers.append(bm.get("name", bm.get("code", "基准")))

    row = write_title_row(ws, 1, "组合历史走势", ncols)
    row = write_header_row(ws, row, headers)

    for i, bar in enumerate(bars):
        tv = bar.get("total_value", 0)
        cum_return = (tv - first_value) / first_value if first_value > 0 else 0
        norm_value = tv / first_value * 100 if first_value > 0 else 0

        values = [bar.get("date", ""), tv, cum_return, round(norm_value, 2)]
        for bm in benchmarks:
            bm_bars = bm.get("bars", [])
            bm_value = bm_bars[i].get("value") if i < len(bm_bars) else None
            values.append(bm_value)

        fmts: list[str | None] = [None, FMT_MONEY, FMT_PERCENT, "0.00"]
        for _ in range(n_bm):
            fmts.append("0.00")
        row = write_data_row(ws, row, values, formats=fmts)

    # ── 指标汇总区 ──
    row += 1
    row = write_title_row(ws, row, "指标汇总", ncols)

    pd = history_data
    summary_items: list[tuple[str, Any, str | None]] = [
        ("累计收益率(%)", round(pd.get("total_return_pct", 0) / 100, 4), FMT_PERCENT),
        ("累计收益(元)", pd.get("total_return", 0), FMT_MONEY),
        ("最大回撤(%)", round(pd.get("max_drawdown_pct", 0) / 100, 4), FMT_PERCENT),
        ("年化波动率", pd.get("annualized_volatility", 0), FMT_PERCENT),
        ("起算日", pd.get("data_start", ""), None),
        ("终止日", pd.get("data_end", ""), None),
    ]
    for label, val, fmt in summary_items:
        cells = [label, val] + [None] * (ncols - 2)
        fmts_line: list[str | None] = [None, fmt] + [None] * (ncols - 2)
        row = write_data_row(ws, row, cells, formats=fmts_line)

    freeze_header(ws, row=2)
    auto_width(ws, min_width=10, max_width=28)


def _write_drawdown_analysis_sheet(ws, history_data: dict) -> None:
    """写入历史回撤分析页签（组合 vs 基准对比矩阵）。"""
    from src.python.report.excel_writer import (
        _write_placeholder,
        auto_width,
        freeze_header,
        write_data_row,
        write_header_row,
        write_title_row,
    )
    from src.python.report.styles import FMT_PERCENT

    if history_data is None:
        _write_placeholder(ws, "历史回撤分析数据暂不可用（配置或网络原因）", max_cols=5)
        auto_width(ws)
        return

    benchmarks = history_data.get("benchmarks", [])
    n_bm = len(benchmarks)
    ncols = 2 + n_bm

    headers = ["指标", "组合"]
    for bm in benchmarks:
        headers.append(bm.get("name", bm.get("code", "基准")))

    row = write_title_row(ws, 1, "历史回撤分析", ncols)
    row = write_header_row(ws, row, headers)

    pd = history_data
    pct_fmt = FMT_PERCENT
    none_fmt: str | None = None

    metrics: list[tuple[str, Any, str | None, str, str | None]] = [
        ("累计收益率(%)", round(pd.get("total_return_pct", 0) / 100, 4), pct_fmt, "total_return_pct", pct_fmt),
        ("最大回撤(%)", round(pd.get("max_drawdown_pct", 0) / 100, 4), pct_fmt, "max_drawdown_pct", pct_fmt),
        ("年化波动率", pd.get("annualized_volatility", 0), pct_fmt, None, None),
        ("起算日", pd.get("data_start", ""), none_fmt, "data_start", none_fmt),
        ("终止日", pd.get("data_end", ""), none_fmt, "data_end", none_fmt),
    ]

    for metric_name, portfolio_val, portfolio_fmt, bm_key, bm_fmt in metrics:
        values = [metric_name, portfolio_val]
        for bm in benchmarks:
            if bm_key and bm.get(bm_key) is not None:
                raw = bm[bm_key]
                bm_val = round(raw / 100, 4) if bm_fmt == pct_fmt else raw
            else:
                bm_val = None
            values.append(bm_val)

        flist: list[str | None] = [none_fmt, portfolio_fmt]
        for _ in range(n_bm):
            flist.append(bm_fmt if bm_key else none_fmt)
        row = write_data_row(ws, row, values, formats=flist)

    freeze_header(ws, row=2)
    auto_width(ws, min_width=10, max_width=28)


def _write_history_sheets(
    sheets: dict[str, Any],
    history_data: dict | None,
) -> None:
    """写入组合历史走势和回撤分析页签（含基准指数列）。"""
    ws_ph = sheets.get("portfolio_history")
    ws_dd = sheets.get("drawdown_analysis")

    data_ok = history_data and history_data.get("status") != "unavailable" and history_data.get("bars")
    effective = history_data if data_ok else None

    if ws_ph is not None:
        _write_portfolio_history_sheet(ws_ph, effective)
    if ws_dd is not None:
        _write_drawdown_analysis_sheet(ws_dd, effective)


def generate_excel_report(
    holdings: list,
    include_news: bool = False,
    output_dir: str = "reports",
    news_top_count: int = 100,
    include_llm: bool = False,
    llm_content: tuple[str | None, str | None, str | None, str | None] | None = None,
    details: list | None = None,
    a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
    news_data: list | None = None,
    news_llm_meta: dict | None = None,
    enable_b_series: bool = False,  # board 层：基金深度分析是否开启
    enable_news: bool = True,  # board 层：市场新闻是否开启（配置值）
    enable_llm: bool = True,  # board 层：LLM 分析章节是否开启
    enable_history: bool = True,  # board 层：历史走势章节是否开启
    progress: ProgressReporter | None = None,
    section_order: list[dict] | None = None,
    pipeline_data: dict | None = None,  # 组合历史走势：环比对比数据（drives delta columns）
    history_data: dict | None = None,  # 组合历史走势数据（含基准指数）
    debate_info: dict | None = None,
) -> None:
    """生成 Excel 报告的核心逻辑。

    Args:
        holdings: 持仓列表
        include_news: 是否包含新闻页签（data 层：菜单类型决定）
        output_dir: 输出目录
        news_top_count: 新闻条数上限
        include_llm: 是否包含 LLM 分析章节
        llm_content: 预生成的 LLM 内容元组
        details: 预获取的市值核算明细
        a_indices: A 股指数数据
        us_indices: 美股指数数据
        news_data: 预获取的新闻数据
        news_llm_meta: 新闻 LLM 元数据
        enable_b_series: board 层 — 基金深度分析是否开启
        enable_news: board 层 — 市场新闻是否开启（配置值）
        enable_llm: board 层 — LLM 分析章节是否开启
        enable_history: board 层 — 历史走势章节是否开启
        progress: 进度报告接口（默认 SilentProgressReporter，不输出）
        section_order: 可选的自定义报告模块顺序，来自 get_report_section_order(config)
        pipeline_data: 组合历史走势环比对比数据（含 diff 等），注入 summary 页签生成 δ 列对比摘要
        history_data: 组合历史走势数据（含基准指数），来自 PortfolioHistoryCalculator。
                      未提供或 status=unavailable 时页签显示占位文本。
    """
    prog = progress if progress is not None else SilentProgressReporter()

    modules = load_report_modules(prog)
    if not modules:
        return  # excel_writer 缺失，无法继续

    create_workbook = modules["create_workbook"]
    save_workbook = modules["save_workbook"]

    # ── 创建工作簿，按需创建全部页签 ──
    wb = create_workbook()
    wb.remove(wb.active)
    order = section_order or get_report_section_order()  # 内部名 order，避免影子覆盖参数

    # 构造 data 层可用性字典
    data_availability: dict[str, bool] = {}
    if include_news:
        data_availability["news_data_available"] = True
    if include_llm:
        data_availability["llm_data_available"] = True

    sheets = create_sheets(
        wb,
        order,
        enable_b_series=enable_b_series,
        enable_news=enable_news,
        enable_history=enable_history,
        enable_llm=enable_llm,
        data_availability=data_availability,
    )

    # ── 行情市值 + 指数 ──
    data = resolve_market_data(holdings, details, modules, sheets["market_value"], prog)
    a_idx, us_idx = resolve_indices(a_indices, us_indices, modules, prog)

    # ── 各页签写入 ──
    pen_result = write_content_sheets(sheets, holdings, data, a_idx, us_idx, modules, prog)
    write_news_sheet(sheets, holdings, pen_result, include_news, news_data, news_llm_meta, news_top_count, prog)
    write_b_series_sheets(sheets, holdings, enable_b_series, data, modules, prog)
    # 辩论模式标签（从 debate_info 提取或从 feature flag 检测）
    _debate_mode_label: str | None = None
    _debate_mode_combination: str | None = None
    if debate_info and isinstance(debate_info, dict):
        _debate_mode_label = debate_info.get("mode_label")
        _debate_mode_combination = debate_info.get("mode_combination")
    if not _debate_mode_label:
        from src.python.features import is_feature_enabled

        if is_feature_enabled("llm_debate_procon"):
            _debate_mode_label = "🧪 辩论模式"
        elif is_feature_enabled("llm_debate_conditional") or is_feature_enabled("llm_debate_qa_concentration"):
            _debate_mode_label = "🧪 实验模式"

    # 构建组合标识（debate_info 不存在时从 feature flag 检测）
    if not _debate_mode_combination:
        _comb_parts = []
        if is_feature_enabled("llm_debate_procon"):
            _comb_parts.append("正反辩论")
        if is_feature_enabled("llm_debate_conditional"):
            _comb_parts.append("条件推理")
        if is_feature_enabled("llm_debate_qa_concentration"):
            _comb_parts.append("集中度问答")
        _debate_mode_combination = "+".join(_comb_parts) if _comb_parts else None

    if _debate_mode_label and _debate_mode_combination:
        _debate_mode_label = f"{_debate_mode_label} · {_debate_mode_combination}"
    write_llm_section_and_usage(
        sheets, include_llm, llm_content, prog, section_order=order, debate_mode_label=_debate_mode_label
    )

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

    # ── 数据源可用性矩阵页签 ──
    ws_ds = sheets.get("data_source_status")
    if ws_ds is not None:
        prog.info("正在写入数据源可用性矩阵...")
        try:
            from src.python.report.data_source_matrix import build_data_source_matrix
            from src.python.report.excel_writer import (
                auto_width,
                write_data_row,
                write_header_row,
                write_title_row,
            )
            from openpyxl.styles import Font

            _FONT_RED = Font(color="CC0000")
            _FONT_GREEN = Font(color="009900")
            _FONT_ORANGE = Font(color="E67E22")

            matrix = build_data_source_matrix()
            if matrix:
                ncols = 5
                row = write_title_row(ws_ds, 1, "数据源可用性矩阵", ncols)
                row = write_header_row(
                    ws_ds, row,
                    ["数据源", "状态", "详情", "成功", "失败/降级"],
                )
                for m in matrix:
                    if m["status"] == "ok":
                        status_label = "✅ 正常"
                        _font = _FONT_GREEN
                    elif m["status"] == "degraded":
                        status_label = "⚠️ 降级"
                        _font = _FONT_ORANGE
                    else:
                        status_label = "❌ 失败"
                        _font = _FONT_RED
                    row = write_data_row(
                        ws_ds, row,
                        [m["name"], status_label, m["detail"],
                         m["ok"], f"{m['degraded']}/{m['failed']}"],
                    )
                    if m["status"] != "ok":
                        for col in range(1, 6):
                            ws_ds.cell(row=row - 1, column=col).font = _font

                has_degraded = any(m["degraded_list"] for m in matrix)
                if has_degraded:
                    row += 1
                    row = write_title_row(ws_ds, row, "降级明细", ncols)
                    for m in matrix:
                        for dg in m.get("degraded_list", []):
                            row = write_data_row(ws_ds, row, [m["name"], dg, "", "", ""])

                has_failures = any(m["sample_failures"] for m in matrix)
                if has_failures:
                    row += 1
                    row = write_title_row(ws_ds, row, "失败明细", ncols)
                    for m in matrix:
                        for sf in m.get("sample_failures", []):
                            row = write_data_row(ws_ds, row, [m["name"], sf, "", "", ""])
                auto_width(ws_ds)
                logger.info("数据源可用性矩阵页签已写入")
            else:
                logger.debug("[excel] 数据源矩阵为空，跳过页签写入")
        except Exception:
            logger.debug("[excel] 数据源可用性矩阵页签写入失败（非关键）", exc_info=True)

    # ── 组合历史走势：环比对比摘要（写入 summary 页签底部） ──
    if pipeline_data and pipeline_data.get("diff") and "summary" in sheets:
        prog.info("正在写入环比对比摘要...")
        try:
            _diff = pipeline_data["diff"]
            _ws_sum = sheets["summary"]
            # 找到最后一行的行号
            _last_row = _ws_sum.max_row + 2
            from openpyxl.styles import Font

            _section_font = Font(size=12, bold=True, color="2E75B6")
            _bold_font = Font(bold=True)
            # 标题行
            _ws_sum.cell(row=_last_row, column=1, value="【环比对比】").font = _section_font
            _last_row += 1
            # 对比数据
            if _diff.get("days_since_last_report") is not None:
                _ws_sum.cell(row=_last_row, column=1, value="距上次报告")
                _ws_sum.cell(row=_last_row, column=2, value=f"{_diff['days_since_last_report']} 天")
                _last_row += 1
            if _diff.get("total_value_diff") is not None:
                _ws_sum.cell(row=_last_row, column=1, value="总市值变化").font = _bold_font
                _cell = _ws_sum.cell(row=_last_row, column=2, value=_diff["total_value_diff"])
                _cell.number_format = "#,##0.00"
                _cell.font = Font(color="CC0000" if _diff["total_value_diff"] >= 0 else "009900")
                _last_row += 1
            if _diff.get("total_value_diff_pct") is not None:
                _ws_sum.cell(row=_last_row, column=1, value="总市值变化率")
                _cell = _ws_sum.cell(row=_last_row, column=2, value=round(_diff["total_value_diff_pct"] / 100, 4))
                _cell.number_format = "0.00%"
                _last_row += 1
            if _diff.get("total_pnl_diff") is not None:
                _ws_sum.cell(row=_last_row, column=1, value="总盈亏变化").font = _bold_font
                _cell = _ws_sum.cell(row=_last_row, column=2, value=_diff["total_pnl_diff"])
                _cell.number_format = "#,##0.00"
                _cell.font = Font(color="CC0000" if _diff["total_pnl_diff"] >= 0 else "009900")
                _last_row += 1
            # 持仓变动概要
            for _label, _key in [
                ("新增持仓", "added"),
                ("清仓标的", "removed"),
                ("增持标的", "increased"),
                ("减持标的", "decreased"),
            ]:
                _items = _diff.get(_key, [])
                if _items:
                    _ws_sum.cell(row=_last_row, column=1, value=_label).font = _bold_font
                    _names = ", ".join(f"{i.get('name', '')}({i.get('code', '')})" for i in _items[:5])
                    if len(_items) > 5:
                        _names += f" 等{len(_items)}只"
                    _ws_sum.cell(row=_last_row, column=2, value=_names)
                    _last_row += 1
            logger.info("环比对比摘要已写入 summary 页签")
        except Exception:
            logger.debug("[F delta] Excel 环比对比摘要写入失败（非关键）", exc_info=True)

    # ── 保存 ──
    with Timer("保存 Excel/HTML 文件"):
        # 在每个页签底部写入隐私声明脚注
        for _ws_name, _ws in sheets.items():
            if _ws is not None:
                try:
                    from src.python.report.excel_writer import write_privacy_footer

                    write_privacy_footer(_ws, ncols=5)
                except Exception:
                    logger.debug("[privacy] 页签 %s 写入隐私脚注失败（非关键）", _ws_name, exc_info=True)
        prog.info("正在保存 Excel 报告...")
        path = save_workbook(wb, output_dir=output_dir)
        logger.info("Excel 报告已生成: %s", path)
        logger.info(
            "总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
            data["total_mv"],
            data["total_cost"],
            data["total_profit"],
            data["today_profit"],
        )
        prog.ok(f"Excel 报告已保存: {path}")
