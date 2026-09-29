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


#: 同类排名载荷的语义版本——写入缓存时随载荷同存，读侧以 :func:`rank_payload_is_current`
#: 为准入判据：版本不符即视为未命中、丢弃重取（与 ``fetcher/fund.py`` 的 ``hold_schema`` 同习语），
#: 使「改变载荷语义的修复」不再依赖用户手动清缓存、也不被 24h TTL 遮蔽。
_RANK_SCHEMA_FIELD = "rank_schema"
_RANK_SCHEMA = 2

#: 排名日期与**同一文件内**的净值日期允许的最大偏差（天）。
#: 为何以此为准：排名由净值派生，实测 13 只基金两侧尾部日期**完全相等**（Δ=0 天），
#: 故这是一个**假阳性免疫**的陈旧判据——排名序列落后于净值序列即说明该次响应里的
#: 排名数据是陈旧的（实测 040046 曾读到 2024-02-18 那期的 253 同类池，而净值同期）。
_RANK_MAX_LAG_DAYS = 3

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


def _parse_nav_date(text: str) -> str:
    """同一 pingzhongdata 载荷内的**净值日期**（``Data_netWorthTrend`` 末位 ``x``）。

    用于给排名做陈旧闸门：排名由净值派生，两者尾部日期应当同期（实测 Δ=0 天）。
    解析不到时返回空串（调用方据此跳过闸门，不做无依据的置空）。
    """
    m = re.search(r"var Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if not m:
        return ""
    try:
        series = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(series, list) or not series:
        return ""
    last = series[-1]
    if isinstance(last, dict):
        return _sample_date(last.get("x"))
    if isinstance(last, list) and last:
        return _sample_date(last[0])
    return ""


def _days_between(later: str, earlier: str) -> int | None:
    """两个 ``YYYY-MM-DD`` 的相隔天数（later − earlier）；任一侧不可解析返回 None。"""
    from datetime import datetime

    try:
        a = datetime.strptime(later, "%Y-%m-%d")
        b = datetime.strptime(earlier, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return (a - b).days


def _parse_rank_entry(text: str) -> dict[str, Any]:
    """解析同类排名（Data_rateInSimilarType）和百分位（Data_rateInSimilarPersent）。

    排名载荷有**三个独立的上游时序**（排名数组、百分位数组、净值序列），各自可能滞后。
    各取各的末位会拼出「不同期」或「陈旧」的记录且无任何提示，报告上表现为自相矛盾/
    过时的排名（实测 040046 曾读到 2024-02-18 那期的 ``253`` 同类池，而同报告里另几只
    纳指 100 联接均是 ``362``）。故本函数做两道校验：

    1. **排名 / 百分位同期性**：两侧末位日期不一致时，以**较新者**为准，较旧项置 ``--``；
    2. **排名 / 净值陈旧闸门**：排名尾部日期相对同一文件内的净值日期偏离超过
       :data:`_RANK_MAX_LAG_DAYS` 天时，整条排名判为陈旧（全部置 ``--``）——实测两侧
       尾部日期恒相等，故该判据假阳性免疫。

    两者均只告警+置空，不抛异常（宁缺毋错：宁可显示 ``--`` 也不显示错期排名）。

    Returns:
        ``{"rank", "total", "percentile", "data_date", "rank_schema"}``；缺失项为 ``"--"``。
    """
    rank_entry: dict[str, Any] = {
        "rank": "--",
        "total": "--",
        "percentile": "--",
        "data_date": "--",
        _RANK_SCHEMA_FIELD: _RANK_SCHEMA,
    }

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

    # ── 陈旧闸门：排名尾部日期 vs 同一文件内的净值日期 ──
    # 排名由净值派生，实测两侧尾部日期恒相等（13 只基金 Δ=0 天）；偏离即说明该次响应里的
    # 排名序列陈旧（实测读到过 2024-02-18 那期的同类池）。只在**两侧日期均可解析**时判定，
    # 避免无依据地置空。
    nav_date = _parse_nav_date(text)
    if use_rank and rank_date and nav_date:
        lag = _days_between(nav_date, rank_date)
        if lag is None or abs(lag) > _RANK_MAX_LAG_DAYS:
            logger.warning(
                "同类排名数据陈旧：排名尾部 %s 与净值 %s 相差 %s 天（阈值 %d）——本条排名判为不可用",
                rank_date,
                nav_date,
                lag,
                _RANK_MAX_LAG_DAYS,
            )
            use_rank = use_pct = False
            data_date = ""

    if use_rank:
        last = rank_series[-1]
        rank_entry["rank"] = str(last.get("y", "--"))
        rank_entry["total"] = str(last.get("sc", "--"))
    if use_pct and isinstance(pct_last, list) and len(pct_last) >= 2:
        with contextlib.suppress(TypeError, ValueError):
            rank_entry["percentile"] = str(round(float(pct_last[1]), 2))

    if data_date:
        rank_entry["data_date"] = data_date
    return rank_entry


def rank_payload_is_current(payload: object) -> bool:
    """缓存载荷是否由**当前语义版本**的排名解析器写出（版本不符 → 视为未命中重取）。

    为何需要：排名载荷的语义曾变更（新增日期附注、陈旧闸门），旧缓存条目**结构未变但
    含义已变**——仅靠 24h TTL 会在过期前持续遮蔽修复（实测：旧条目里的 ``155/253``
    在 TTL 内被重复上屏，用户看到问题依旧）。以版本戳作准入判据后，旧条目**自动作废**。

    无排名数据的载荷（基金本身无同类排名）不拦——无东西可校验，拦了会无限重取。
    """
    if not isinstance(payload, dict):
        return False
    peer = (payload.get("rankings") or {}).get("同类排名")
    if not isinstance(peer, dict):
        return True
    return peer.get(_RANK_SCHEMA_FIELD) == _RANK_SCHEMA


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
