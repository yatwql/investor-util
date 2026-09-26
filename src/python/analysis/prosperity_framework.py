"""景气度框架诊断 — 组合与「景气度投资」框架的契合度评估（实验性功能）。

方法骨架借鉴自上游开源项目 **zhengxi-views**（郑希观点库，MIT License，
<https://github.com/lyra81604/zhengxi-views>）的 `references/method.md` 与
`references/scorecard.md`：把一位主动权益基金经理的公开方法蒸馏为「可操作流程 + 六维评分卡」。
**本项目只借鉴其可计算骨架与评分口径**（不引入其语料、基金快照、检索能力），并按本仓
「可计算、可降级、可复核」原则重写为纯计算模块。

方法一句话：全球视野找技术/需求变化 → 顺产业链找「正在涨价（通胀）」的环节（偏好供给端创造
需求的科技通胀）→ 落到中国有比较优势的环节 → 在该环节选「流动性够 + ROE 低位有修复弹性 +
偏中小市值」的标的 → 多维跟踪、逐步拟合、周期拼接 → 组合分散 + 行业比例调整 + 预先想好退出 →
以「客观」为最高准绳，底层逻辑变坏就卖。

六维评分卡（满分 100，权重与口径见设计文档 `docs-stm/plan/prosperity-framework-design.md`）：

  ① 景气方向 / 通胀属性 25   ② ROE 低位弹性 20   ③ 全球视野 / 中国比较优势 15
  ④ 流动性 10               ⑤ 集中度与周期拼接 15   ⑥ 业绩与回撤印证 15

**红线**（写入本模块文档串与渲染文案）：
  1. 数据缺失的维度一律标 ``unverified``：**不给分、不臆造**（开关关闭的契约、场外品种流动性、
     无历史快照的换手代理、无历史数据的回撤印证）；
  2. 本评分衡量「组合与该框架的**契合度**」，**不是**组合优劣判断，更**不是投资建议**；
  3. 每条得分都须在 ``evidence`` 中可追溯到具体输入（口径写清楚）。

数据来源（全部取自本仓既有能力，不新增外部数据源与网络调用）：
  ``holdings_details``（市值明细）/ ``penetration_data``（穿透重仓的板块与占比）/
  ``financial_indicator_data``（A 股 ROE 与质量档）/ ``liquidity_signals``（场内变现天数）/
  ``snapshots``（历史快照 → 换手代理）/ ``history_data``（组合区间收益与最大回撤）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.num_utils import finite_or
from src.python.analysis.prosperity_scoring import (  # noqa: F401
    # 全部迁移名逐一再导出：既有测试与报告层的 import 面保持不变（含私有常量/打分器）
    DEFAULT_CONFIG,
    RATING_THRESHOLDS,
    estimated_fund_codes,
    roe_by_code_from_rows,
    _FALLBACK_CONFIG,
    _LIQUIDITY_FLOOR,
    _LIQUIDITY_TIERS,
    _LOW_ROE_THRESHOLD,
    _TURNOVER_FLOOR,
    _TURNOVER_TIERS,
    _W_BOOM,
    _W_CONCENTRATION,
    _W_GLOBAL,
    _W_LIQUIDITY,
    _W_PERFORMANCE,
    _W_ROE,
    _benchmark_returns,
    _boom_weights,
    _cfg,
    _config_defaults_for_module,
    _fund_type_fallback_label,
    _guard_dimension,
    _matches,
    _pct,
    _rating,
    _score_boom,
    _score_concentration,
    _score_global_edge,
    _score_liquidity,
    _score_performance,
    _score_roe,
    _sector_weight_items,
    _snapshot_holding_codes,
    _top10_concentration_pct,
    _turnover_proxy_pct,
    _unverified_dimension,
)

logger = logging.getLogger("invest")

__all__ = ["build_prosperity_framework_data", "RATING_THRESHOLDS", "DEFAULT_CONFIG"]


DISCLAIMER = "本评分衡量组合与景气度框架的契合度，非组合优劣判断，亦非投资建议；标注「需核实」的项请自行核实。"


# ── 维度② ROE 低位弹性 ────────────────────────────────────────


# ── 维度③ 全球视野 / 中国比较优势 ─────────────────────────────


# ── 维度④ 流动性 ──────────────────────────────────────────────


# ── 维度⑤ 集中度与周期拼接 ───────────────────────────────────


# ── 维度⑥ 业绩与回撤印证 ─────────────────────────────────────


# ── 持仓视角（可核对清单） ────────────────────────────────────


def _holdings_view(
    holdings_details: list[dict[str, Any]],
    roe_by_code: dict[str, float],
    cfg: dict[str, Any],
    limit: int = 20,
    estimated_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    from src.python.report.penetration import classify_sector

    total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details)
    ordered = sorted(holdings_details, key=lambda d: finite_or(getattr(d, "market_value", 0.0)), reverse=True)
    view: list[dict[str, Any]] = []
    for d in ordered[:limit]:
        code = getattr(d, "code", "")
        name = getattr(d, "name", "")
        sector = classify_sector(name, code)
        notes: list[str] = []
        if _matches(f"{sector} {name}", cfg["boom_keywords"]):
            notes.append("命中景气方向关键词")
        if _matches(f"{sector} {name}", cfg["defensive_keywords"]):
            notes.append("命中防御/红利关键词（反向扣减项）")
        roe = roe_by_code.get(code)
        if roe is None:
            pass  # ROE 缺失由渲染层在 ROE 列标「需核实」，此处不再重复成备注
        elif estimated_codes and code in estimated_codes:
            notes.append(f"ROE {roe:.1%} 为基金重仓股加权推演值（按框架推演）")
            if roe < _LOW_ROE_THRESHOLD:
                notes.append("低 ROE → 存在修复弹性")
        elif roe < _LOW_ROE_THRESHOLD:
            notes.append(f"低 ROE（{roe:.1%}）→ 存在修复弹性")
        view.append(
            {
                "code": code,
                "name": name,
                "weight_pct": _pct(finite_or(getattr(d, "market_value", 0.0)), total),
                "sector": sector,
                "roe": roe,
                "notes": notes,
            }
        )
    return view


def _safe_holdings_view(
    holdings_details: list[dict[str, Any]],
    roe_by_code: dict[str, float],
    cfg: dict[str, Any],
    estimated_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    """持仓视角清单（异常时返回空清单，不影响契约其余部分）。"""
    try:
        return _holdings_view(holdings_details, roe_by_code, cfg, estimated_codes=estimated_codes)
    except Exception:
        logger.warning("[prosperity_framework] 持仓视角清单构建异常，已置空", exc_info=True)
        return []


# ── 入口 ──────────────────────────────────────────────────────


def build_prosperity_framework_data(
    holdings_details: list[dict[str, Any]] | None,
    *,
    penetration_data: dict[str, Any] | None = None,
    financial_indicator_data: dict[str, Any] | None = None,
    fund_roe_estimates: dict[str, dict[str, Any]] | None = None,
    liquidity_signals: list[dict[str, Any]] | None = None,
    snapshots: list[Any] | None = None,
    history_data: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 `prosperity_framework_data` 契约（六维评分卡 + 持仓视角）。

    Args:
        holdings_details: 市值明细行（`DetailRow`，含 code/name/market_value）。
        penetration_data: `compute_penetration_top10()` 结果（提供穿透后板块与占比；可为 None）。
        financial_indicator_data: `financial_indicator_data` 契约（提供个股 ROE 与年度趋势）。
        fund_roe_estimates: 基金重仓股 ROE 加权推演值（`estimate_fund_roe_batch` 产出；
            仅对无直接 ROE 的基金持仓生效，证据与持仓视角均标注「按框架推演」）。
        liquidity_signals: `check_liquidity()` 结果（提供场内变现天数）。
        snapshots: 历史快照序列（`SnapshotData` 对象或 dict；最近两期用于换手代理）。
        history_data: 组合历史走势数据（提供区间收益与最大回撤）。
        config: 完整配置字典（读取 `prosperity_framework` 段）。

    Returns:
        契约 dict；`holdings_details` 为空时 `available=False`。
    """
    details = list(holdings_details or [])
    cfg = _cfg(config)
    notes = [DISCLAIMER]
    if not details:
        return {
            "available": False,
            "reason": "无持仓数据，无法评估景气度框架契合度",
            "notes": notes,
        }

    boom = _guard_dimension(
        lambda: _score_boom(penetration_data, details, cfg), "boom_cycle", "景气方向/通胀属性", _W_BOOM
    )
    global_dim = _guard_dimension(
        lambda: _score_global_edge(penetration_data, details, cfg), "global_edge", "全球视野/中国比较优势", _W_GLOBAL
    )
    liquidity_dim = _guard_dimension(lambda: _score_liquidity(liquidity_signals), "liquidity", "流动性", _W_LIQUIDITY)
    performance_dim = _guard_dimension(
        lambda: _score_performance(history_data), "performance", "业绩与回撤印证", _W_PERFORMANCE
    )

    roe_dim: dict[str, Any]
    roe_by_code: dict[str, float] = {}
    try:
        roe_dim, roe_by_code = _score_roe(details, financial_indicator_data, fund_roe_estimates)
    except Exception:
        logger.warning("[prosperity_framework] 维度「ROE 低位弹性」计算异常，已降级为未验证", exc_info=True)
        roe_dim = _unverified_dimension("roe_elasticity", "ROE 低位弹性", _W_ROE, "该维计算异常，已跳过（详见日志）")

    concentration: float | None = None
    turnover: float | None = None
    try:
        concentration_dim, concentration, turnover = _score_concentration(details, snapshots, cfg)
    except Exception:
        logger.warning("[prosperity_framework] 维度「集中度与周期拼接」计算异常，已降级为未验证", exc_info=True)
        concentration_dim = _unverified_dimension(
            "concentration_cycle", "集中度与周期拼接", _W_CONCENTRATION, "该维计算异常，已跳过（详见日志）"
        )

    # 持仓视角标注所需的推演集合：直接 ROE 缺失、由基金重仓加权推演补上的品种
    # （与 _score_roe 共用同一判定原语，两侧不得各自实现规则）
    direct_roe_codes = set(roe_by_code_from_rows((financial_indicator_data or {}).get("rows")))
    estimated_codes = estimated_fund_codes(fund_roe_estimates, direct_roe_codes)
    if estimated_codes:
        notes.append("② 维基金 ROE 为重仓股加权推演值（阶段一：前十大重仓口径），非基金披露口径。")

    dimensions = [boom, roe_dim, global_dim, liquidity_dim, concentration_dim, performance_dim]
    scored = [d for d in dimensions if d["status"] != "unverified"]
    scored_weight = sum(d["max_score"] for d in scored)
    total_score = sum(d["score"] for d in scored)
    total_pct = round(total_score / scored_weight * 100) if scored_weight else 0
    rating, rating_label = _rating(total_pct)

    unverified = [
        f"{d['name']}：{d['unverified'][0]}" for d in dimensions if d["status"] == "unverified" and d["unverified"]
    ]
    partial_notes = [f"{d['name']}：{u}" for d in dimensions if d["status"] == "partial" for u in d["unverified"]]

    logger.info(
        "[prosperity_framework] 诊断完成：%d/%d（%d%%）评级=%s，未验证维度 %d 个",
        total_score,
        scored_weight,
        total_pct,
        rating_label,
        len(unverified),
    )
    return {
        "available": True,
        "reason": "",
        "total_score": total_score,
        "scored_weight": scored_weight,
        "max_score": _W_BOOM + _W_ROE + _W_GLOBAL + _W_LIQUIDITY + _W_CONCENTRATION + _W_PERFORMANCE,
        "total_score_pct": total_pct,
        "rating": rating,
        "rating_label": rating_label,
        "dimensions": dimensions,
        "holdings_view": _safe_holdings_view(details, roe_by_code, cfg, estimated_codes=estimated_codes),
        "concentration_pct": concentration,
        "turnover_proxy_pct": turnover,
        "unverified": unverified,
        "partial_notes": partial_notes,
        "notes": notes,
    }
