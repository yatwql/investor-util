"""财务指标章 — 报告层数据装配。

对持仓 + 穿透中的 A 股标的取多期财务指标（``fetcher/financial_indicator.py``），
装配为报告层数据契约 ``financial_indicator_data``：

    {available, reason, rows, failures, entry_count}

每行含最新报告期指标 + **质量分档**（``analysis/financial_indicator.py`` 启发式，
四维度均值分档）+ **年度趋势**（相邻年报营收/净利）+ **当前 PE/PB**（现价 ÷
每股收益/每股净资产，亏损或净资产非正时留空）+ 近几期趋势点。

无 A 股标的、akshare 不可用或全部无覆盖时返回 ``available=False`` 的降级契约，
展示层写占位，不阻断报告主链路（§1.4.5 数据降级治理）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.analysis.financial_indicator import (
    current_valuation,
    quality_grade,
    trend_label,
    trend_points,
)
from src.python.fetcher.financial_indicator import fetch_indicator_series
from src.python.fetcher.financial_report import collect_a_share_targets

logger = logging.getLogger("invest")

_DOC_TYPE_LABELS = {
    "annual": "年报",
    "semiannual": "半年报",
    "q1": "一季报",
    "q3": "三季报",
    "amendment": "修正稿",
}

#: 趋势点展示期数
_TREND_POINTS = 4


def _doc_type_label(doc_type: str) -> str:
    return _DOC_TYPE_LABELS.get(str(doc_type or ""), str(doc_type or ""))


def _empty(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason, "rows": [], "failures": [], "entry_count": 0}


def _row(target: dict[str, str], series: list[dict[str, Any]], price: float | None) -> dict[str, Any]:
    """装配单只标的的行（缺失字段取 None，不猜、不填 0）。"""
    latest = series[0]
    grade, score = quality_grade(latest)
    pe, pb = current_valuation(latest, price)
    return {
        "code": target["code"],
        "name": target["name"],
        "report_period": latest.get("report_period") or "",
        "doc_type": latest.get("doc_type") or "",
        "doc_type_label": _doc_type_label(str(latest.get("doc_type") or "")),
        "source_api": latest.get("source_api") or "",
        "source": latest.get("source") or "",
        "revenue": latest.get("revenue"),
        "net_profit": latest.get("net_profit"),
        "revenue_yoy": latest.get("revenue_yoy"),
        "net_profit_yoy": latest.get("net_profit_yoy"),
        "gross_margin": latest.get("gross_margin"),
        "roe": latest.get("roe"),
        "debt_ratio": latest.get("debt_ratio"),
        "operating_cash_flow": latest.get("operating_cash_flow"),
        "eps": latest.get("eps"),
        "bvps": latest.get("bvps"),
        "pe": pe,
        "pb": pb,
        "quality_grade": grade,
        "quality_score": score,
        "trend": trend_label(series),
        "series": trend_points(series, limit=_TREND_POINTS),
        "period_count": len(series),
    }


def build_financial_indicator(
    holdings: list,
    config: dict | None = None,
    reporter: Any = None,
    penetrated_codes: list[str] | None = None,
    prices: dict[str, float] | None = None,
) -> dict[str, Any]:
    """构建「财务指标」数据契约。

    Args:
        holdings: 持仓对象列表
        config: 完整配置字典（当前未读取，保留与同类装配函数一致的签名）
        reporter: 可选进度报告器
        penetrated_codes: 穿透底层的证券代码（可空）
        prices: ``{代码: 现价}``（用于当前 PE/PB；缺价则该行 PE/PB 留空）

    Returns:
        ``{available, reason, rows, failures, entry_count}``；
        **DataSinking 数据底座未就绪（配置位关闭或缺凭据）时返回 None**——
        章节整体隐藏（不写占位），报告形态与引入本能力前逐字一致
    """
    from src.python.config import datasink_feature_ready

    if not datasink_feature_ready(config):
        logger.info("[financial_indicator] DataSinking 数据底座未就绪，财务指标章静默跳过")
        return None

    targets = collect_a_share_targets(holdings, penetrated_codes)
    if not targets:
        return _empty("无 A 股持仓或穿透标的")

    if reporter is not None:
        reporter.info(f"正在获取 {len(targets)} 只 A 股的财务指标...")

    # 并发取数：akshare 侧为只读 HTTP，worker 数取 config 的 batch.akshare_workers（默认 2）
    from concurrent.futures import ThreadPoolExecutor

    from src.python.fetcher.batch import get_batch_worker_count

    prices = prices or {}
    workers = get_batch_worker_count("akshare_workers", 2)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fin_indicator") as pool:
        series_list = list(pool.map(lambda t: fetch_indicator_series(t["code"]), targets))

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for target, series in zip(targets, series_list):
        if not series:
            failures.append(
                {"code": target["code"], "name": target["name"], "reason": "无指标数据（未覆盖或数据源不可用）"}
            )
            continue
        rows.append(_row(target, series, prices.get(target["code"])))

    if not rows:
        result = _empty("未取到财务指标数据（数据源不可用或标的不在覆盖范围）")
        result["failures"] = failures
        return result

    return {
        "available": True,
        "reason": f"已取到 {len(rows)} 只 A 股的财务指标",
        "rows": rows,
        "failures": failures,
        "entry_count": len(rows),
    }
