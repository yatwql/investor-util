"""调仓 What-if 模拟报告输出。

编排双产物输出：
  - Excel 调仓模拟工作簿（调仓摘要 / 分类配置对比 / 持仓变动明细
    + 指定生效日时的「时序回测」页签 + whatif_trade_cost 开启时的「交易成本对比」页签）
  - HTML 双栏对比页（含资产配置对比环形图 + 回测折线图，复用 Chart.js 本地 bundle）

报告按主报告归档惯例输出到 output_dir（与主报告分离）：
  - 最新版固定名 `调仓模拟.xlsx` / `调仓模拟.html`（每次覆盖为最新对比）
  - 归档版 `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx` / `.html`（日期子目录）
并复制 Chart.js 前端资产到同目录（离线自包含，约束）；
超过 180 天的归档目录自动清理。

持仓匿名化（anonymization.mode，与主报告同一分层接入）：
  - 装配边：双产品物化点（Excel 写入 / HTML 渲染）经
    ``apply_report_anonymization`` 字段层匿名（off/summary 恒等原样，
    summary 拦截下沉到渲染/写入层——差异行不适配大类折叠键位）
  - 渲染点：模板代码列 ``| anon_code``（真码 → 显示掩码，full/summary 生效）
  - 产物清扫：HTML 名称自由文本清扫（只扫名称防金额误伤）+ 边界安全代码兜底；
    Excel 字符串单元格清扫 + 代码面边界安全替换
  - off 模式全链恒等零开销；匿名化只改显示面，不改模拟计算结果
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from src.python.core.constants import APP_NAME, APP_VERSION
from src.python.report.excel_writer import _cleanup_old_archives, _ensure_reports_dir
from src.python.report.html_writer import _copy_js_assets, _inline_js_assets
from src.python.report.whatif_sheet import (
    write_whatif_backtest_sheet,
    write_whatif_category_sheet,
    write_whatif_changes_sheet,
    write_whatif_cost_sheet,
    write_whatif_summary_sheet,
)

logger = logging.getLogger("invest")


# ── 持仓匿名化（双产品物化点：字段层 + 渲染/清扫映射单源） ──────────


def _whatif_identity_rows(whatif_data: dict[str, Any]) -> list[dict]:
    """身份面渲染源行：changes 主明细在前，cost legs / feasibility 派生行在后。

    顺序稳定是代号编号的单源前提：``build_report_alias_map`` 按 code 首见序
    编号，与 ``apply_report_anonymization`` 字段层同规则，保证 HTML/Excel
    双端、字段层与清扫层的「品种X」指向同一持仓。
    """
    if not whatif_data:
        return []
    cost = whatif_data.get("cost") or {}
    tc = cost.get("trade_cost") or {}
    rows = list(whatif_data.get("changes") or [])
    rows += list(tc.get("legs") or [])
    rows += list(whatif_data.get("feasibility") or [])
    return [r for r in rows if isinstance(r, dict)]


def _whatif_anonymization_maps(
    whatif_data: dict[str, Any],
    mode: str | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """身份面单源映射：(真名→代号, 真码→显示掩码)，渲染点与产物清扫共用。

    名称映射**不含代码**（自由文本清扫只换名称，金额串不误伤）；代码面统一
    由渲染点 ``| anon_code`` 与 ``mask_code_text`` 边界安全替换负责——whatif 的
    impact 说明列/箭头列是内嵌数值的字符串单元格，全分子串换码会命中金额。
    off → 两映射皆空（全链恒等零开销）。
    """
    if mode is None:
        from src.python.config.anonymizer import get_anonymization_mode

        mode = get_anonymization_mode()

    from src.python.config.anonymizer import build_code_display_map, build_report_alias_map

    rows = _whatif_identity_rows(whatif_data)
    return (
        build_report_alias_map(rows, mode, include_codes=False),
        build_code_display_map(rows, mode),
    )


def _rename_identity_rows(rows: list[dict], name_map: dict[str, str]) -> list[dict]:
    """派生容器行按同一代号映射改名（pair 语义：与主明细容器共用映射）。"""
    renamed: list[dict] = []
    for row in rows:
        name = row.get("name")
        renamed.append({**row, "name": name_map[name]} if name and name in name_map else row)
    return renamed


def _anonymize_whatif_data(whatif_data: dict[str, Any], mode: str | None = None) -> dict[str, Any]:
    """装配边字段层：whatif 契约显示面匿名（返回副本；off/summary 原样返回）。

    分层口径（对齐主报告 ``apply_report_anonymization`` 的物化点规则）：

    - code_display / full_anonymous：changes 主明细经 ``apply_report_anonymization``
      物化匿名（同一代号映射），cost legs / feasibility 派生容器共用该映射改名；
      full 分支按明细键派生的 profit/profit_rate 非 whatif 契约键，剥离后
      **数值面保持原值**——匿名化不得改变模拟计算结果（成本/回测数值），
      与主报告明细的千位模糊口径区分（此处不做模糊）。
    - summary：字段层不折叠（差异行的 base_cost/cand_cost 与大类折叠键位
      不匹配，折叠会产出缺失假行并混同变动方向），拦截下沉到渲染/写入层
      （HTML 明细区空态、Excel 明细页占位），仅保留聚合面——
      whatif 的大类汇总由分类配置对比天然承载。
    - off：恒等返回原对象（零开销）。
    """
    if mode is None:
        from src.python.config.anonymizer import get_anonymization_mode

        mode = get_anonymization_mode()

    if mode not in ("code_display", "full_anonymous"):
        return whatif_data

    rows = _whatif_identity_rows(whatif_data)
    if not rows:
        return whatif_data

    from src.python.report._report_helpers import apply_report_anonymization

    alias_map, _ = _whatif_anonymization_maps(whatif_data, mode=mode)
    anon: dict[str, Any] = dict(whatif_data)

    changes = whatif_data.get("changes")
    if isinstance(changes, list) and changes:
        anon_changes, _ = apply_report_anonymization(changes, None, mode=mode)
        # full 派生键（profit/profit_rate）非 whatif 契约键 → 剥离保持键集原样
        anon_changes = [{k: a.get(k) for k in s} for s, a in zip(changes, anon_changes)]
        zip_map = {s.get("name"): a.get("name") for s, a in zip(changes, anon_changes) if s.get("name")}
        # 字段层映射优先（pair 语义同标），派生容器仅含主明细未覆盖的名称
        name_map = {**alias_map, **zip_map}
        anon["changes"] = anon_changes
    else:
        name_map = alias_map

    feasibility = whatif_data.get("feasibility")
    if feasibility:
        anon["feasibility"] = _rename_identity_rows(feasibility, name_map)

    cost = whatif_data.get("cost")
    legs = (((cost or {}).get("trade_cost")) or {}).get("legs")
    if cost and legs:
        anon["cost"] = {
            **cost,
            "trade_cost": {**cost["trade_cost"], "legs": _rename_identity_rows(legs, name_map)},
        }
    return anon


def _mask_whatif_workbook_codes(wb: Any, code_map: dict[str, str]) -> int:
    """Excel 端代码面兜底：字符串单元格按 {真码→掩码} 边界安全替换，返回改写数。

    与 ``mask_workbook_text``（名称清扫）分工：代码是纯数字串，无条件子串
    替换会命中内嵌金额（如 1600519.00），故复用 ``mask_code_text`` 的
    边界判定；数值单元格一律不动。
    """
    if not code_map:
        return 0

    from src.python.config.anonymizer import mask_code_text

    changed = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if not isinstance(value, str) or not value:
                    continue
                masked = mask_code_text(value, code_map)
                if masked and masked != value:
                    cell.value = masked
                    changed += 1
    if changed:
        logger.info("[anonymizer] 调仓模拟 Excel 代码面掩码 %d 个单元格", changed)
    return changed


def write_whatif_excel(whatif_data: dict[str, Any], output_dir: str = "reports") -> str:
    """输出调仓模拟 Excel 工作簿（最新版固定名 + 日期目录归档版），返回最新文件路径。

    归档格式对齐主报告：`调仓模拟.xlsx`（最新版，覆盖）+ `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.xlsx`（归档版）。

    Args:
        whatif_data: 数据契约 dict
        output_dir: 输出目录

    Returns:
        最新版 Excel 绝对路径
    """
    from openpyxl import Workbook

    from src.python.config.anonymizer import get_anonymization_mode

    # 装配边（Excel 物化点）：字段层匿名 + 单源映射（清扫层用）
    _anon_mode = get_anonymization_mode()
    _alias_map, _code_map = _whatif_anonymization_maps(whatif_data, mode=_anon_mode)
    _anon_data = _anonymize_whatif_data(whatif_data, mode=_anon_mode)

    _ensure_reports_dir(output_dir)
    wb = Workbook()
    ws_sum = wb.active
    ws_sum.title = "调仓摘要"
    write_whatif_summary_sheet(ws_sum, _anon_data)
    ws_cat = wb.create_sheet("分类配置对比")
    write_whatif_category_sheet(ws_cat, _anon_data)
    ws_chg = wb.create_sheet("持仓变动明细")
    write_whatif_changes_sheet(ws_chg, _anon_data)
    ws_bt = wb.create_sheet("时序回测")
    write_whatif_backtest_sheet(ws_bt, _anon_data)
    # 条件页签：开关 whatif_trade_cost 开启且面板装配成功时追加（关闭 → 页签集不变）
    if _anon_data.get("cost"):
        ws_cost = wb.create_sheet("交易成本对比")
        write_whatif_cost_sheet(ws_cost, _anon_data)

    # 产物清扫（匿名化）：字符串单元格真名→代号 + 代码面边界安全替换；
    # 数值单元格不动（无数字子串误伤）。off → 恒等零开销跳过。
    if _anon_mode != "off":
        from src.python.report.excel_writer import mask_workbook_text

        mask_workbook_text(wb, _alias_map)
        _mask_whatif_workbook_codes(wb, _code_map)

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    latest = os.path.join(output_dir, "调仓模拟.xlsx")
    archive = os.path.join(output_dir, date_str, f"调仓模拟-{date_str}-{time_str}.xlsx")
    try:
        wb.save(latest)
    except PermissionError:
        logger.error("文件被占用: %s", latest)
        raise
    try:
        wb.save(archive)
    except (PermissionError, OSError) as e:
        logger.warning("存档 Excel 写入失败（非关键）: %s", e)
    _cleanup_old_archives(output_dir)
    logger.info("调仓模拟 Excel 已保存: %s", latest)
    return os.path.abspath(latest)


def _trim_whatif_chart_data(whatif_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """What-if 图表数据专用裁剪（避免整包 tojson，数据最小化）。

    whatif_data（数据契约）含 summary/changes/stats/base/candidate 等表格字段，
    双环图只需 categories（图表 JS 读取 whatif.categories）。保留 available 便于
    JS 侧可用性判断；数据不足（None/available=False）返回 None（模板不输出数据段）。
    """
    if not whatif_data or not whatif_data.get("available"):
        return None
    return {"available": True, "categories": whatif_data.get("categories") or []}


def _trim_whatif_backtest_chart_data(whatif_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """时序回测图表数据专用裁剪（数据最小化）。

    只透传 series 字段（labels/base/candidate/base_drawdown/candidate_drawdown），
    避免把 metrics/reason 等表格字段整包 tojson 到前端。回测缺失/不可用时返回 None。
    """
    bt = (whatif_data or {}).get("backtest") if whatif_data else None
    if not bt or not bt.get("available"):
        return None
    series = bt.get("series")
    if not series or not series.get("labels"):
        return None
    return {
        "available": True,
        "effective_date": bt.get("effective_date"),
        "series": {
            "labels": series.get("labels"),
            "base": series.get("base"),
            "candidate": series.get("candidate"),
            "base_drawdown": series.get("base_drawdown"),
            "candidate_drawdown": series.get("candidate_drawdown"),
        },
    }


def _trim_whatif_cost_chart_data(whatif_data: dict[str, Any] | None) -> dict[str, Any] | None:
    """交易成本对比图表数据专用裁剪（数据最小化，只透传三线所需字段）。"""
    cost = (whatif_data or {}).get("cost") if whatif_data else None
    if not cost or not cost.get("chart"):
        return None
    chart = cost["chart"]
    if not chart.get("labels"):
        return None
    return {
        "labels": chart.get("labels"),
        "base": chart.get("base"),
        "candidate_after": chart.get("candidate_after"),
        "candidate_before": chart.get("candidate_before"),
        "benchmark": chart.get("benchmark"),
        "benchmark_name": ((cost.get("benchmark") or {}).get("name")),
        "impact": cost.get("impact"),
    }


def render_whatif_html(whatif_data: dict[str, Any], now_str: str) -> str:
    """渲染 whatif_template.html，返回完整 HTML 字符串。

    装配边（HTML 物化点）与渲染点在此接线：匿名数据进模板，代码列经
    ``| anon_code`` 键控折叠（anon_code_map），``anon_mode`` 供模板在
    summary 模式拦截明细区（差异行不适配大类折叠，渲染层出空态不出行）。

    Args:
        whatif_data: 数据契约 dict
        now_str: 展示用时间字符串

    Returns:
        HTML 字符串
    """
    from src.python.config.anonymizer import get_anonymization_mode
    from src.python.report.html_jinja_env import _ENV

    _anon_mode = get_anonymization_mode()
    _anon_data = _anonymize_whatif_data(whatif_data, mode=_anon_mode)
    _, _code_map = _whatif_anonymization_maps(whatif_data, mode=_anon_mode)

    return _ENV.get_template("whatif_template.html").render(
        whatif_data=_anon_data,
        anon_mode=_anon_mode,
        anon_code_map=_code_map,
        now=now_str,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        whatif_chart_data=_trim_whatif_chart_data(whatif_data),
        whatif_backtest_chart_data=_trim_whatif_backtest_chart_data(whatif_data),
        whatif_cost_chart_data=_trim_whatif_cost_chart_data(whatif_data),
    )


def write_whatif_html(whatif_data: dict[str, Any], output_dir: str = "reports") -> str:
    """输出调仓模拟 HTML 页面（最新版固定名 + 日期目录归档版，含 Chart.js 资产复制），返回最新文件路径。

    归档格式对齐主报告：`调仓模拟.html`（最新版，覆盖）+ `YYYYMMDD/调仓模拟-YYYYMMDD-HHMMSS.html`（归档版）。

    Args:
        whatif_data: 数据契约 dict
        output_dir: 输出目录

    Returns:
        最新版 HTML 绝对路径
    """
    _ensure_reports_dir(output_dir)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = render_whatif_html(whatif_data, now_str)
    # 产物清扫（匿名化）：字段层未覆盖的派生面（文件名/降级原因等自由文本）
    # 在最终 HTML 统一真名→代号——**只扫名称**（金额不误伤），代码面由
    # mask_code_text 边界安全替换兜底（渲染点 | anon_code 为主）。off → 恒等跳过。
    # 时序：先清扫后内嵌，Chart.js bundle 不参与文本替换。
    from src.python.config.anonymizer import get_anonymization_mode, mask_code_text, mask_display_text

    _anon_mode = get_anonymization_mode()
    if _anon_mode != "off":
        _alias_map, _code_map = _whatif_anonymization_maps(whatif_data, mode=_anon_mode)
        html = mask_display_text(html, _alias_map)
        _masked_codes = mask_code_text(html, _code_map)
        if _masked_codes:
            html = _masked_codes
    _copy_js_assets(output_dir)
    # 内嵌 Chart.js 资产 → HTML 单文件自包含（下载/移动/单发移动端浏览）
    html = _inline_js_assets(html)

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    latest = os.path.join(output_dir, "调仓模拟.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)
    archive_dir = os.path.join(output_dir, date_str)
    os.makedirs(archive_dir, exist_ok=True)
    archive = os.path.join(archive_dir, f"调仓模拟-{date_str}-{time_str}.html")
    with open(archive, "w", encoding="utf-8") as f:
        f.write(html)
    _cleanup_old_archives(output_dir)
    logger.info("调仓模拟 HTML 已保存: %s", latest)
    return os.path.abspath(latest)


def write_whatif_report(
    whatif_data: dict[str, Any],
    output_dir: str = "reports",
    reporter=None,
) -> dict[str, str]:
    """同时输出 Excel + HTML 调仓模拟报告。

    Args:
        whatif_data: 数据契约 dict
        output_dir: 输出目录
        reporter: 进度输出（CliProgressReporter），None 时静默

    Returns:
        {"excel": 最新 Excel 绝对路径, "html": 最新 HTML 绝对路径}
    """
    if reporter is not None:
        reporter.info("正在输出调仓 What-if 模拟报告...")
    excel_path = write_whatif_excel(whatif_data, output_dir)
    html_path = write_whatif_html(whatif_data, output_dir)
    if reporter is not None:
        reporter.ok(f"调仓模拟报告生成完成: Excel {excel_path} / HTML {html_path}")
    return {"excel": excel_path, "html": html_path}
