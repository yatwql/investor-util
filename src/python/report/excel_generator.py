"""Excel 报告生成核心函数。

通过 ProgressReporter 接口输出进度，不依赖 TUI。
"""

from __future__ import annotations

from typing import Any

from src.python.logger import setup_logger
from src.python.registry import get_report_section_order
from src.python.report.excel_module_loader import load_report_modules
from src.python.report.excel_b_series import write_b_series_sheets
from src.python.report.excel_content_sheets import write_content_sheets
from src.python.report.excel_llm_usage import write_llm_section_and_usage
from src.python.report.excel_market_data import resolve_market_data, resolve_indices
from src.python.report.excel_news_warning import write_news_and_early_warning
from src.python.report.excel_sheet_factory import create_sheets
from src.python.report.progress import ProgressReporter, SilentProgressReporter, _Timer

logger = setup_logger()


def generate_excel_report(
    holdings: list, include_news: bool = False, output_dir: str = "reports",
    news_top_count: int = 100, include_llm: bool = False,
    llm_content: tuple[str | None, str | None, str | None, str | None] | None = None,
    details: list | None = None, a_indices: dict[str, dict[str, Any]] | None = None,
    us_indices: dict[str, dict[str, Any]] | None = None,
    news_data: list | None = None,
    news_llm_meta: dict | None = None,
    early_warnings: dict | None = None,
    include_b_series: bool | None = None,  # renamed from include_fund_deep
    progress: ProgressReporter | None = None,
    section_order: list[dict] | None = None,
    f_context: dict | None = None,  # 组合历史走势：环比对比数据（drives delta columns）
) -> None:
    """生成 Excel 报告的核心逻辑。

    Args:
        holdings: 持仓列表
        include_news: 是否包含新闻页签
        output_dir: 输出目录
        news_top_count: 新闻条数上限
        include_llm: 是否包含 LLM 分析章节
        llm_content: 预生成的 LLM 内容元组
        details: 预获取的市值核算明细
        a_indices: A 股指数数据
        us_indices: 美股指数数据
        news_data: 预获取的新闻数据
        news_llm_meta: 新闻 LLM 元数据
        early_warnings: 智能预警数据
        include_b_series: 是否包含 B 系列页签（基金深度分析）。
            None 时跟随 include_news（B/L 含，E/H 不含）。已从 include_fund_deep 重命名。
        progress: 进度报告接口（默认 SilentProgressReporter，不输出）
        section_order: 可选的自定义报告模块顺序，来自 get_report_section_order(config)
        f_context: 组合历史走势环比对比数据（含 diff 等），注入 summary 页签生成 δ 列对比摘要
    """
    prog = progress if progress is not None else SilentProgressReporter()

    # B 系列跟随 include_news（B/L 菜单含新闻 = 含 B 系列）
    enable_b_series = include_news if include_b_series is None else include_b_series

    modules = load_report_modules(prog)
    if not modules:
        return  # excel_writer 缺失，无法继续

    create_workbook = modules["create_workbook"]
    save_workbook = modules["save_workbook"]

    # ── 创建工作簿，按需创建全部页签 ──
    wb = create_workbook()
    wb.remove(wb.active)
    order = section_order or get_report_section_order()  # 内部名 order，避免影子覆盖参数
    sheets = create_sheets(wb, order,
                            enable_b_series=enable_b_series,
                            include_news=include_news,
                            include_llm=include_llm)

    # ── 行情市值 + 指数 ──
    data = resolve_market_data(holdings, details, modules, sheets["market_value"], prog)
    a_idx, us_idx = resolve_indices(a_indices, us_indices, modules, prog)

    # ── 各页签写入 ──
    pen_result = write_content_sheets(sheets, holdings, data, a_idx, us_idx, modules, prog)
    write_news_and_early_warning(sheets, holdings, pen_result, include_news,
                                  news_data, news_llm_meta, news_top_count,
                                  early_warnings, prog)
    write_b_series_sheets(sheets, holdings, enable_b_series, data, modules, prog)
    write_llm_section_and_usage(sheets, include_llm, llm_content, prog, section_order=order)

    # ── 组合历史走势：环比对比摘要（写入 summary 页签底部） ──
    if f_context and f_context.get("diff") and "summary" in sheets:
        prog.info("正在写入环比对比摘要...")
        try:
            _diff = f_context["diff"]
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
                _cell.number_format = '#,##0.00'
                _cell.font = Font(color="CC0000" if _diff["total_value_diff"] >= 0 else "009900")
                _last_row += 1
            if _diff.get("total_value_diff_pct") is not None:
                _ws_sum.cell(row=_last_row, column=1, value="总市值变化率")
                _cell = _ws_sum.cell(row=_last_row, column=2, value=round(_diff["total_value_diff_pct"] / 100, 4))
                _cell.number_format = '0.00%'
                _last_row += 1
            if _diff.get("total_pnl_diff") is not None:
                _ws_sum.cell(row=_last_row, column=1, value="总盈亏变化").font = _bold_font
                _cell = _ws_sum.cell(row=_last_row, column=2, value=_diff["total_pnl_diff"])
                _cell.number_format = '#,##0.00'
                _cell.font = Font(color="CC0000" if _diff["total_pnl_diff"] >= 0 else "009900")
                _last_row += 1
            # 持仓变动概要
            for _label, _key in [("新增持仓", "added"), ("清仓标的", "removed"),
                                  ("增持标的", "increased"), ("减持标的", "decreased")]:
                _items = _diff.get(_key, [])
                if _items:
                    _ws_sum.cell(row=_last_row, column=1, value=_label).font = _bold_font
                    _names = ", ".join(f"{i.get('name','')}({i.get('code','')})" for i in _items[:5])
                    if len(_items) > 5:
                        _names += f" 等{len(_items)}只"
                    _ws_sum.cell(row=_last_row, column=2, value=_names)
                    _last_row += 1
            logger.info("环比对比摘要已写入 summary 页签")
        except Exception:
            logger.debug("[F delta] Excel 环比对比摘要写入失败（非关键）", exc_info=True)

    # ── 保存 ──
    with _Timer("保存 Excel/HTML 文件"):
        prog.info("正在保存 Excel 报告...")
        path = save_workbook(wb, output_dir=output_dir)
        logger.info("Excel 报告已生成: %s", path)
        logger.info("总市值: %.2f元, 总成本: %.2f元, 总盈亏: %.2f元, 本日盈亏: %.2f元",
                    data["total_mv"], data["total_cost"],
                    data["total_profit"], data["today_profit"])
        prog.ok(f"Excel 报告已保存: {path}")
