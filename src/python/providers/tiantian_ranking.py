"""天天基金 API — 基金业绩排名、评级计算与风险分析。

职责：
  - 从 pingzhongdata/{code}.js 提取区间收益率与同类排名
  - 5 级评级计算（类型差异化阈值）
  - 业绩评价与风险分析解析
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Any

from src.python.providers.tiantian_base import _request_pingzhong_data, _safe_float

logger = logging.getLogger("invest")


def _parse_syl_returns(text: str) -> dict[str, dict[str, Any]]:
    """解析各区间收益率（syl_* JS 变量）。

    覆盖短中长全部周期，缺失值（`--`）自动跳过。
    """
    period_map = {
        "近1月": "syl_1y",
        "近3月": "syl_3y",
        "近6月": "syl_6y",
        "近1年": "syl_1n",
        "近2年": "syl_2n",
        "近3年": "syl_3n",
        "近5年": "syl_5n",
    }
    rankings: dict[str, dict[str, Any]] = {}
    for period, var_name in period_map.items():
        m = re.search(rf'var\s+{var_name}\s*=\s*"?(-?[\d.]+|--)', text)
        if m and m.group(1) != "--":
            rankings[period] = {"return": _safe_float(m.group(1))}
    return rankings


def _parse_rank_entry(text: str) -> dict[str, Any]:
    """解析同类排名（Data_rateInSimilarType）和百分位（Data_rateInSimilarPersent）。"""
    rank_entry: dict[str, Any] = {"rank": "--", "total": "--", "percentile": "--"}

    rank_match = re.search(r"var Data_rateInSimilarType\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if rank_match:
        try:
            rank_data = json.loads(rank_match.group(1))
            if rank_data:
                last = rank_data[-1]
                rank_entry["rank"] = str(last.get("y", "--"))
                rank_entry["total"] = str(last.get("sc", "--"))
        except (json.JSONDecodeError, IndexError, TypeError, AttributeError) as _e:
            logger.warning("解析同类排名数据失败: %s", _e)

    pct_match = re.search(r"var Data_rateInSimilarPersent\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if pct_match:
        try:
            pct_data = json.loads(pct_match.group(1))
            if pct_data:
                last_pct = pct_data[-1]
                if isinstance(last_pct, list) and len(last_pct) >= 2:
                    rank_entry["percentile"] = str(round(last_pct[1], 2))
        except (json.JSONDecodeError, IndexError, TypeError, AttributeError) as _e:
            logger.warning("解析百分位排名数据失败: %s", _e)

    return rank_entry


# ── 评级计算（5 级 + 类型差异化阈值） ────────────────

_RATING_THRESHOLDS: dict[str, list[float]] = {
    "default": [0.10, 0.30, 0.50, 0.75],
    "bond": [0.15, 0.35, 0.55, 0.80],
    "index": [0.10, 0.25, 0.45, 0.70],
    "qdii": [0.15, 0.35, 0.55, 0.80],
}

_KNOWN_RATING_TYPES = list(_RATING_THRESHOLDS.keys())


def _get_rating_thresholds(fund_type_hint: str = "") -> list[float]:
    """根据基金类型获取对应的评级阈值列表。"""
    return _RATING_THRESHOLDS.get(fund_type_hint, _RATING_THRESHOLDS["default"])


def _fund_type_hint_from_name(name: str | None) -> str:
    """根据基金名称推导评级阈值类型键（default/bond/index/qdii）。

    与穿透分类（report/penetration.classify_penetration）的判定优先级一致：
    先 QDII（含隐式海外），再债券型，再指数/ETF/联接，其余走主动权益默认阈值。

    Returns:
        阈值类型键：``"qdii"`` / ``"bond"`` / ``"index"`` / ``""``（默认）
    """
    if not name:
        return ""
    from src.python.core.code_utils import (
        is_bond_related_by_name,
        is_etf_by_name,
        is_index_fund_by_name,
        is_index_link_by_name,
        is_qdii_extended,
    )

    if is_qdii_extended(name):
        return "qdii"
    if is_bond_related_by_name(name):
        return "bond"
    if is_index_fund_by_name(name) or is_index_link_by_name(name) or is_etf_by_name(name):
        return "index"
    return ""


def _pct_to_rating(pct: float, thresholds: list[float] | None = None) -> str:
    """将 0~1 百分位值转为 5 级评级。

    5 级对齐晨星分布：
      优秀(前10%) / 良好(10~30%) / 稳定(30~50%) / 偏差(50~75%) / 较差(后25%)
    """
    if pct < 0 or pct > 1:
        return ""
    t = thresholds or _RATING_THRESHOLDS["default"]
    if pct <= t[0]:
        return "优秀"
    if pct <= t[1]:
        return "良好"
    if pct <= t[2]:
        return "稳定"
    if pct <= t[3]:
        return "偏差"
    return "较差"


def _calc_rating_from_entry(rank_entry: dict[str, Any], fund_type_hint: str = "") -> str:
    """根据排名/总数（优先）或百分位计算评级。

    支持类型差异化阈值 + 5 级输出。

    Args:
        rank_entry: 排序条目（含 rank/total/percentile）
        fund_type_hint: 基金类型（"bond"/"index"/"qdii"/默认）

    Returns:
        评级字符串（优秀/良好/稳定/偏差/较差）或空串
    """

    def _pct_to_rating_with_type(pct: float) -> str:
        return _pct_to_rating(pct, _get_rating_thresholds(fund_type_hint))

    # 路径1：百分位
    pct_rating = ""
    if rank_entry.get("percentile", "--") != "--":
        try:
            pct_val = float(rank_entry["percentile"]) / 100.0
            pct_rating = _pct_to_rating_with_type(pct_val)
        except (ValueError, TypeError):
            pass

    # 路径2：排名/总数（更可靠）
    rank_rating = ""
    if rank_entry.get("rank", "--") != "--" and rank_entry.get("total", "--") != "--":
        try:
            rank_pct = int(rank_entry["rank"]) / int(rank_entry["total"])
            rank_rating = _pct_to_rating_with_type(rank_pct)
        except (ValueError, ZeroDivisionError):
            pass

    # 两者矛盾 → 以排名/总数为准
    if pct_rating and rank_rating and pct_rating != rank_rating:
        logger.info(
            "百分位评级(%s)与排名评级(%s)不一致，以排名/总数(%s/%s)为准",
            pct_rating,
            rank_rating,
            rank_entry.get("rank", "?"),
            rank_entry.get("total", "?"),
        )

    return rank_rating or pct_rating or ""


def _parse_perf_evaluation(text: str) -> dict[str, Any] | None:
    """解析业绩评价数据（Data_performanceEvaluation JS 变量）。"""
    pe_match = re.search(r"var Data_performanceEvaluation\s*=\s*(\{[^;]+\});", text, re.DOTALL)
    if not pe_match:
        return None
    try:
        return json.loads(pe_match.group(1))
    except (json.JSONDecodeError, TypeError, ValueError) as _e:
        logger.warning("解析业绩评价数据失败: %s", _e)
        return None


# ── 风险分析 ─────────────────────────────────────────

_SHARPE_THRESHOLDS = {"excellent": 1.5, "poor": 0.3}
_MAX_DD_THRESHOLD = -40.0


def _parse_risk_analysis(text: str) -> dict[str, Any] | None:
    """解析风险分析数据（Data_riskAnalysis JS 变量）。

    支持 JSON 对象格式（categories+data）和数组格式。
    返回归一化字典 {"年化波动率": 15.2, "最大回撤": -18.5, ...}。

    Returns:
        风险指标字典 或 None
    """
    ra_match = re.search(r"var Data_riskAnalysis\s*=\s*(\[[\s\S]*?\]);", text, re.DOTALL)
    if not ra_match:
        ra_match = re.search(r"var Data_riskAnalysis\s*=\s*(\{[\s\S]*?\});", text, re.DOTALL)
    if not ra_match:
        return None

    raw = ra_match.group(1)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as _e:
        logger.warning("解析风险分析数据失败: %s", _e)
        return None

    # 格式1: {"categories": [...], "data": [...]}
    if isinstance(parsed, dict):
        cats = parsed.get("categories") or []
        data = parsed.get("data") or []
        if cats and data and len(cats) == len(data):
            return {str(c): float(d) for c, d in zip(cats, data) if c is not None and d is not None}

    # 格式2: [["名称", 值], ...]
    if isinstance(parsed, list) and parsed:
        result: dict[str, Any] = {}
        for item in parsed:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                k, v = item[0], item[1]
                if k is not None and v is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        result[str(k)] = float(v)
        if result:
            return result

    return None


def fetch_fund_rankings(code: str) -> dict[str, Any] | None:
    """获取基金同类排名和区间收益率。

    API: fund.eastmoney.com/pingzhongdata/{code}.js
    从 JS 变量 Data_rateInSimilarType（排名）和 Data_rateInSimilarPersent（百分位）提取。

    Args:
        code: 6 位基金代码

    Returns:
        {"code", "name", "type", "rankings", "rating", "perf_evaluation",
        "risk_analysis"} 或 None
        其中 ``type`` 为评级阈值类型键（``qdii``/``bond``/``index``/``""``），
        由基金名称推导，决定 ``rating`` 采用的差异化阈值。
    """
    text = _request_pingzhong_data(code)
    if text is None:
        return None

    name = ""
    name_match = re.search(r'var\s+fS_name\s*=\s*"([^"]*)"', text)
    if name_match:
        name = name_match.group(1)

    # 类型差异化阈值：按名称推导 QDII/债券/指数，接线至评级计算
    fund_type_hint = _fund_type_hint_from_name(name)

    rankings = _parse_syl_returns(text)
    rank_entry = _parse_rank_entry(text)
    if rank_entry.get("rank") != "--" or rank_entry.get("percentile") != "--":
        rankings["同类排名"] = rank_entry

    rating = _calc_rating_from_entry(rank_entry, fund_type_hint)
    perf_eval = _parse_perf_evaluation(text)
    risk_data = _parse_risk_analysis(text)

    logger.info(
        "基金 %s（%s）: 排名 %s/%s, 评级 %s",
        name,
        code,
        rank_entry.get("rank", "?"),
        rank_entry.get("total", "?"),
        rating or "未知",
    )

    return {
        "code": code.strip(),
        "name": name,
        "type": fund_type_hint,
        "rankings": rankings,
        "rating": rating,
        "perf_evaluation": perf_eval,
        "risk_analysis": risk_data,
    }
