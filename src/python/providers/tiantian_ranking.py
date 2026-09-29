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


#: 同类池规模（``sc``）相对上期**显著回落**的判定阈值：下降超过此比例即告警。
#: 同类池（全市场同类型基金只数）只会缓慢增长，**大幅回落几乎必是上游数据版本问题**
#: （实测：某次报告的 040046 读到 253，而同类池当时实为 362——253 其实是 2024-02-18
#: 那期的值），故这是一个高价值的上游数据滞后信号。
_PEER_POOL_SHRINK_RATIO = 0.10

#: 毫秒时间戳的合理性下限（2000-01-01 UTC）——小于此值视为「不是日期」（见 _sample_date）。
_MIN_PLAUSIBLE_MS = 946_684_800_000


def _sample_date(value: Any) -> str:
    """位图日期（毫秒 Unix 或 ``YYYY-MM-DD``）→ ``YYYY-MM-DD``；无法解析返回空串。

    合理性下限：只接受**毫秒时间戳**（2000-01-01 起）或显式日期字符串。
    为何要设下限：旧格式/精简载荷里该字段可能是**序号**（实测存量测试夹具的
    ``[[1, 6.25]]``——1 毫秒会解成 1970-01-01），当成日期会把附注写错。
    """
    if isinstance(value, str):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
        return m.group(0) if m and int(m.group(1)) >= 2000 else ""
    if isinstance(value, (int, float)) and float(value) >= _MIN_PLAUSIBLE_MS:
        from datetime import datetime

        from src.python.core.constants import BEIJING_TZ

        try:
            return datetime.fromtimestamp(float(value) / 1000.0, tz=BEIJING_TZ).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            return ""
    return ""


def _parse_rank_entry(text: str) -> dict[str, Any]:
    """解析同类排名（Data_rateInSimilarType）和百分位（Data_rateInSimilarPersent）。

    两条数据在 pingzhongdata 中是**独立数组、各自带日期字段**（``x``）。上游在某次响应里
    可能一条已更新、另一条仍是旧期（实测：某次报告读到 rank/total 落后而 percentile 同期，
    或反）——若各取各的末位就拼出「不同期」的一条记录且无任何提示，报告上表现为
    自相矛盾/过时的排名。故本函数：

    1. **同期性校验**：两个数组的末位日期不一致时，以**较新者**为准，并把较旧的字段
       置 ``--``（宁缺毋错） + 记 ``data_date`` 与告警；
    2. **同类池跳变防护**：``sc`` 相对上一期大幅回落（> 10%）时告警（同类池只会缓慢增长，
       突降基本是上游数据版本问题）。

    Returns:
        ``{"rank", "total", "percentile", "data_date"}``；缺失项为 ``"--"``。
    """
    rank_entry: dict[str, Any] = {"rank": "--", "total": "--", "percentile": "--", "data_date": "--"}

    # ── 排名数组（y=rank, sc=同类池规模, x=日期）──
    rank_series: list[dict[str, Any]] = []
    rank_match = re.search(r"var Data_rateInSimilarType\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if rank_match:
        try:
            parsed = json.loads(rank_match.group(1))
            if isinstance(parsed, list):
                rank_series = [e for e in parsed if isinstance(e, dict)]
        except (json.JSONDecodeError, IndexError, TypeError, AttributeError) as _e:
            logger.warning("解析同类排名数据失败: %s", _e)

    # ── 百分位数组（[日期, 百分位]）──
    pct_series: list[Any] = []
    pct_match = re.search(r"var Data_rateInSimilarPersent\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if pct_match:
        try:
            parsed_pct = json.loads(pct_match.group(1))
            if isinstance(parsed_pct, list):
                pct_series = parsed_pct
        except (json.JSONDecodeError, IndexError, TypeError, AttributeError) as _e:
            logger.warning("解析百分位排名数据失败: %s", _e)

    rank_date = _sample_date(rank_series[-1].get("x")) if rank_series else ""
    pct_last = pct_series[-1] if pct_series else None
    pct_date = _sample_date(pct_last[0]) if isinstance(pct_last, list) and pct_last else ""

    # ── 同期性校验：两侧**均有日期且确实不同**时才取新置旧 ──
    # 为何要求「均有日期」：无日期只是「未知期次」（旧格式/精简载荷），不是
    # 「期次不同」——把未知当不同会白丢掉可用数据（回归风险）。
    use_rank, use_pct = bool(rank_series), isinstance(pct_last, list) and len(pct_last) >= 2
    if rank_date and pct_date and rank_date != pct_date:
        newer = max(rank_date, pct_date)
        use_rank = rank_date == newer
        use_pct = pct_date == newer
        logger.warning(
            "同类排名数据不同期（排名 %s / 百分位 %s）——以较新者 %s 为准，较旧项置空",
            rank_date,
            pct_date,
            newer,
        )
    data_date = (rank_date if use_rank else "") or (pct_date if use_pct else "")

    if use_rank:
        last = rank_series[-1]
        rank_entry["rank"] = str(last.get("y", "--"))
        rank_entry["total"] = str(last.get("sc", "--"))
        _warn_on_peer_pool_shrink(rank_series)
    if use_pct and isinstance(pct_last, list) and len(pct_last) >= 2:
        with contextlib.suppress(TypeError, ValueError):
            rank_entry["percentile"] = str(round(float(pct_last[1]), 2))

    if data_date:
        rank_entry["data_date"] = data_date
    return rank_entry


def _warn_on_peer_pool_shrink(rank_series: list[dict[str, Any]]) -> None:
    """同类池规模（``sc``）相对上一期大幅回落时告警（上游数据版本异常信号）。

    同类池是全市场同类型基金只数，只会缓慢增长；突降（> 10%）基本可判定为该次
    响应的数据版本落后或结构异常，值得在日志里点名（报告侧不会因此报错——只告警）。
    """
    if len(rank_series) < 2:
        return
    try:
        cur = int(rank_series[-1].get("sc"))
        prev = int(rank_series[-2].get("sc"))
    except (TypeError, ValueError):
        return
    if prev > 0 and cur < prev * (1 - _PEER_POOL_SHRINK_RATIO):
        logger.warning(
            "同类池规模异常回落：%d → %d（日期 %s → %s）——同类池只会缓慢增长，疑为上游客端数据版本滞后",
            prev,
            cur,
            _sample_date(rank_series[-2].get("x")),
            _sample_date(rank_series[-1].get("x")),
        )


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
