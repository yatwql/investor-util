"""智能预警模块 — 行业资金流向联动 + 新闻情绪聚合。

从已有数据（穿透 TOP10、行业资金流向、新闻 LLM 关联分析）中
自动发现风险信号和关注焦点，输出到报告「智能预警」章节。

包含：
  - compute_early_warnings() — 核心计算逻辑
  - write_early_warning_sheet() — Excel 页签写入
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.python.config import get_config
from src.python.registry import get_llm_module_name, get_report_sheet_name, set_sheet_title
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)

logger = logging.getLogger("invest")


def _get_sector_alert_thresholds() -> tuple[float, float]:
    """从 config.json 读取行业预警阈值，不存在时返回默认值。"""
    cfg = get_config()
    ew = cfg.get("early_warning", {}) if isinstance(cfg, dict) else {}
    return (
        float(ew.get("sector_alert_threshold_warning", -50_000_000)),
        float(ew.get("sector_alert_threshold_danger", -200_000_000)),
    )


def _get_sentiment_top_n() -> int:
    """从 config.json 读取新闻情绪聚合 TOP N，不存在时返回默认值。"""
    cfg = get_config()
    ew = cfg.get("early_warning", {}) if isinstance(cfg, dict) else {}
    return int(ew.get("sentiment_top_n", 10))

# ── Excel 列数 ──────────────────────────────────────────────
_SECTOR_COLS = 6
_SENTIMENT_COLS = 7


# ═══════════════════════════════════════════════════════════
#  核心计算逻辑
# ═══════════════════════════════════════════════════════════


def compute_early_warnings(
    holdings: list,
    penetration_top10: list[dict] | None = None,
    sector_flow: list[dict] | None = None,
    news_data: list[dict] | None = None,
    news_llm_meta: dict | None = None,
) -> dict:
    """计算智能预警数据。

    两个独立维度：
      1. 行业资金流向联动 — 穿透资产的行业概念与今日资金流向匹配
      2. 新闻情绪聚合 — 财经新闻热点与持仓关联分析按持仓品种汇总

    Args:
        holdings: 持仓列表（Holding objects），用于获取名称/代码
        penetration_top10: 穿透 TOP10 列表，每项含 name/codes/concepts/mv/ratio_pct
        sector_flow: 行业资金流向列表，每项含 name/main_net_inflow/change_pct/top_stock
        news_data: build_news_data() 返回的新闻列表
        news_llm_meta: news_data 伴随的元数据（含 llm_enabled 等）

    Returns:
        {
            "sector_alerts": [..],
            "sentiment_alerts": [..],
            "has_warnings": bool,
            "has_sector_data": bool,
            "has_llm_news": bool,
        }
    """
    sector_alerts = _compute_sector_alerts(penetration_top10, sector_flow)
    sentiment_alerts = _compute_sentiment_alerts(holdings, news_data, news_llm_meta)

    has_warnings = bool(sector_alerts or sentiment_alerts)
    has_sector_data = bool(sector_flow)
    has_llm_news = bool(
        news_llm_meta
        and news_llm_meta.get("llm_enabled")
        and any(
            isinstance(item, dict) and item.get("llm_analysis")
            for item in (news_data or [])
        )
    )

    return {
        "sector_alerts": sector_alerts,
        "sentiment_alerts": sentiment_alerts,
        "has_warnings": has_warnings,
        "has_sector_data": has_sector_data,
        "has_llm_news": has_llm_news,
    }


def _compute_sector_alerts(
    penetration_top10: list[dict] | None,
    sector_flow: list[dict] | None,
) -> list[dict]:
    """行业资金流向联动预警。

    匹配逻辑：取穿透资产的 concepts（概念板块标签），
    与行业资金流向的行业名做交集。如果持有的行业出现大额净流出，标记预警。

    Returns:
        [{sector_name, main_net_inflow, main_net_inflow_pct, change_pct,
          matched_assets, alert_level}, ...]
    """
    if not penetration_top10 or not sector_flow:
        return []

    # 构建概念 → 穿透资产的倒排索引
    concept_to_assets: dict[str, list[dict]] = {}
    for asset in penetration_top10:
        for concept in (asset.get("concepts") or []):
            concept = concept.strip()
            if not concept:
                continue
            if concept not in concept_to_assets:
                concept_to_assets[concept] = []
            concept_to_assets[concept].append({
                "name": asset.get("name", ""),
                "codes": asset.get("codes", []),
                "mv": asset.get("mv", 0),
                "ratio_pct": asset.get("ratio_pct", 0),
            })

    if not concept_to_assets:
        return []

    alerts: list[dict] = []
    for flow in sector_flow:
        sname = (flow.get("name") or "").strip()
        if not sname:
            continue
        main_inflow = flow.get("main_net_inflow") or 0
        if main_inflow >= 0:
            continue  # 净流入不计预警

        matched = concept_to_assets.get(sname)
        if not matched:
            continue

        # 判定预警等级（从 config 读取阈值）
        _threshold_warn, _threshold_danger = _get_sector_alert_thresholds()
        if main_inflow <= _threshold_danger:
            level = "danger"
        elif main_inflow <= _threshold_warn:
            level = "warning"
        else:
            level = "info"

        alerts.append({
            "sector_name": sname,
            "main_net_inflow": main_inflow,
            "main_net_inflow_pct": flow.get("main_net_inflow_pct") or 0,
            "change_pct": flow.get("change_pct") or 0,
            "top_stock": flow.get("top_stock") or "",
            "matched_assets": matched,
            "alert_level": level,
        })

    # 按净流出金额排序（最危险的排最前）
    alerts.sort(key=lambda a: a["main_net_inflow"])
    return alerts


def _collect_relevant_news(
    news_data: list[dict],
    news_llm_meta: dict,
) -> list[dict]:
    """从新闻列表中筛选出有 LLM 分析且关联度 >= 中 的条目。"""
    if not news_llm_meta.get("llm_enabled", False):
        return []

    result: list[dict] = []
    for item in news_data:
        analysis = item.get("llm_analysis")
        if not isinstance(analysis, dict):
            continue
        relevance = analysis.get("relevance", "")
        if relevance not in ("高", "中"):
            continue
        result.append(item)
    return result


def _build_code_to_name_map(holdings: list) -> dict[str, str]:
    """构建持仓代码 → 名称查找表。"""
    code_to_name: dict[str, str] = {}
    for h in holdings:
        code = h.code.strip() if hasattr(h, "code") else ""
        name = h.name.strip() if hasattr(h, "name") else ""
        if code:
            code_to_name[code] = name or code
    return code_to_name


def _aggregate_and_score_sentiments(
    relevant_news: list[dict],
    code_to_name: dict[str, str],
) -> list[dict]:
    """按持仓代码聚合新闻情绪，计算得分并排序。"""
    holding_sentiments: dict[str, dict] = {}
    for item in relevant_news:
        analysis = item.get("llm_analysis", {})
        sentiment = analysis.get("sentiment", "中性")
        matched_keywords = item.get("matched_keywords") or []
        title = item.get("title", "")

        # 从 matched_keywords 中提取持仓代码
        codes_in_news: set[str] = set()
        for kw in matched_keywords:
            m = re.search(r"(\d{6})", kw)
            if m:
                codes_in_news.add(m.group(1))

        for code in codes_in_news:
            name = code_to_name.get(code, code)
            if code not in holding_sentiments:
                holding_sentiments[code] = {
                    "code": code,
                    "name": name,
                    "total_mentions": 0,
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0,
                    "top_stories": [],
                }
            entry = holding_sentiments[code]
            entry["total_mentions"] += 1
            if sentiment == "利好":
                entry["positive"] += 1
            elif sentiment == "利空":
                entry["negative"] += 1
            else:
                entry["neutral"] += 1
            if len(entry["top_stories"]) < 3 and title not in entry["top_stories"]:
                entry["top_stories"].append(title)

    if not holding_sentiments:
        return []

    result: list[dict] = list(holding_sentiments.values())
    for entry in result:
        total = entry["total_mentions"]
        score = (entry["positive"] - entry["negative"]) / total if total > 0 else 0
        entry["sentiment_score"] = round(score, 2)
        if score >= 0.3:
            entry["sentiment_label"] = "偏利好"
        elif score <= -0.3:
            entry["sentiment_label"] = "偏利空"
        else:
            entry["sentiment_label"] = "中性"

    result.sort(key=lambda a: a["total_mentions"], reverse=True)
    return result[:_get_sentiment_top_n()]


def _compute_sentiment_alerts(
    holdings: list,
    news_data: list[dict] | None,
    news_llm_meta: dict | None,
) -> list[dict]:
    """新闻情绪聚合预警。

    从每条新闻的 llm_analysis.sentiment 字段聚合，按持仓品种汇总。
    仅当财经新闻热点与持仓关联分析启用时生效。

    Returns:
        [{code, name, total_mentions, positive, negative, neutral,
          sentiment_score, sentiment_label, top_stories}, ...]
    """
    if not news_data or not news_llm_meta:
        return []

    relevant_news = _collect_relevant_news(news_data, news_llm_meta)
    if not relevant_news:
        return []

    code_to_name = _build_code_to_name_map(holdings)
    return _aggregate_and_score_sentiments(relevant_news, code_to_name)


# ═══════════════════════════════════════════════════════════
#  Excel 页签写入
# ═══════════════════════════════════════════════════════════


def write_early_warning_sheet(ws, early_warnings: dict) -> None:
    """写入智能预警页签。

    Args:
        ws: 目标工作表
        early_warnings: compute_early_warnings() 返回的字典
    """
    row = write_title_row(ws, 1, get_report_sheet_name('early_warning'), max(_SECTOR_COLS, _SENTIMENT_COLS))

    # ── 第一段：行业资金流向联动预警 ────────────────────────
    row += 1
    ws.cell(row=row, column=1, value="行业资金流向联动预警").font = _bold_font()
    row += 1

    sector_alerts = early_warnings.get("sector_alerts", [])
    has_sector_data = early_warnings.get("has_sector_data", False)

    if not has_sector_data:
        row = _write_empty_row(ws, row, "当前行业资金流向数据不可用，无法生成预警。")
    elif not sector_alerts:
        row = _write_empty_row(ws, row, "当前暂无行业资金流向预警。所有关联行业资金面正常。")
    else:
        headers = ["行业", "主力净流入(元)", "净流入占比", "涨跌幅", "关联持仓", "预警等级"]
        row = write_header_row(ws, row, headers)

        for alert in sector_alerts:
            inflow_val = alert.get("main_net_inflow", 0)
            assets = alert.get("matched_assets", [])
            asset_names = ", ".join(a.get("name", "") for a in assets)
            alert_level = alert.get("alert_level", "info")
            level_label = {"danger": "⚠ 危险", "warning": "▲ 关注", "info": "● 注意"}.get(alert_level, alert_level)

            row = write_data_row(ws, row, [
                alert.get("sector_name", ""),
                _fmt_money(inflow_val),
                f"{alert.get('main_net_inflow_pct', 0):.2f}%",
                f"{alert.get('change_pct', 0):.2f}%",
                asset_names,
                level_label,
            ])

    # ── 第二段：新闻情绪聚合 ────────────────────────────────
    row += 1
    ws.cell(row=row, column=1, value="新闻情绪聚合").font = _bold_font()
    row += 1

    sentiment_alerts = early_warnings.get("sentiment_alerts", [])
    has_llm_news = early_warnings.get("has_llm_news", False)

    if not has_llm_news:
        row = _write_empty_row(ws, row, f"开启{get_llm_module_name('news_correlation')}后可显示新闻情绪聚合。")
    elif not sentiment_alerts:
        row = _write_empty_row(ws, row, "暂无新闻情绪聚合数据。")
    else:
        s_headers = ["持仓品种", "代码", "提及次数", "利好", "利空", "中性", "情绪"]
        row = write_header_row(ws, row, s_headers)

        for entry in sentiment_alerts:
            row = write_data_row(ws, row, [
                entry.get("name", ""),
                entry.get("code", ""),
                entry.get("total_mentions", 0),
                entry.get("positive", 0),
                entry.get("negative", 0),
                entry.get("neutral", 0),
                entry.get("sentiment_label", ""),
            ])

    freeze_header(ws, 1)
    auto_width(ws, min_width=10, max_width=50)


def _write_empty_row(ws, row: int, text: str) -> int:
    """写入一行提示文本并返回下一行号。"""
    write_data_row(ws, row, [text])
    return row + 2


def _fmt_money(val: float | int) -> str:
    """格式化金额，以亿元/万元为单位。"""
    if abs(val) >= 1_0000_0000:
        return f"{val / 1_0000_0000:.2f}亿"
    if abs(val) >= 1_0000:
        return f"{val / 1_0000:.2f}万"
    return str(int(val))


def _bold_font():
    """返回粗体字体对象。"""
    from openpyxl.styles import Font  # noqa: PLC0415
    return Font(bold=True, size=11)
