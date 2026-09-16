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

logger = logging.getLogger("invest")

__all__ = ["build_prosperity_framework_data", "RATING_THRESHOLDS", "DEFAULT_CONFIG"]

# ── 默认配置（可经 config.json 的 `prosperity_framework` 段覆盖） ─────────
DEFAULT_CONFIG: dict[str, Any] = {
    # 景气/通胀方向关键词（匹配板块与概念字段；偏好供给端创造需求的科技通胀）
    "boom_keywords": [
        "光通信",
        "光模块",
        "算力",
        "数据中心",
        "液冷",
        "半导体",
        "存储",
        "芯片",
        "AI",
        "电力设备",
        "电网",
        "储能",
        "新能源",
        "有色",
        "铜",
        "稀土",
        "军工",
        "创新药",
        "科技",
    ],
    # 中国有全球比较优势的环节关键词（第三个维度）
    "global_edge_keywords": [
        "光通信",
        "光模块",
        "半导体设备",
        "半导体材料",
        "芯片",
        "电力设备",
        "电网",
        "锂电",
        "光伏",
        "储能",
        "消费电子",
        "新能源",
    ],
    # 防御/红利方向关键词（作为景气维度的反向扣减项）
    "defensive_keywords": ["银行", "白酒", "食品饮料", "公用事业", "红利", "地产", "房地产", "保险", "消费"],
    # 前十大重仓集中度目标（%）：框架偏好「分散但不失主线」，超过该值视为集中度偏高
    "concentration_target_pct": 50.0,
}

# 评级阈值（对齐上游评分卡口径：≥80 高度契合 / 60–79 较契合 / 40–59 部分契合 / <40 不契合）
RATING_THRESHOLDS: tuple[tuple[int, str, str], ...] = (
    (80, "high_fit", "高度契合"),
    (60, "partial_fit", "较契合"),
    (40, "weak_fit", "部分契合"),
    (0, "low_fit", "不契合"),
)

# 维度权重（满分）
_W_BOOM = 25
_W_ROE = 20
_W_GLOBAL = 15
_W_LIQUIDITY = 10
_W_CONCENTRATION = 15
_W_PERFORMANCE = 15

# 低 ROE 判定阈值（ROE < 10% 视为「低位、存在修复弹性」）
_LOW_ROE_THRESHOLD = 0.10
# 全面变现天数分档（日）
_LIQUIDITY_TIERS = ((1.0, 10), (3.0, 7), (5.0, 4))
_LIQUIDITY_FLOOR = 2
# 换手代理分档（%）
_TURNOVER_TIERS = ((15.0, 7), (8.0, 5), (3.0, 3))
_TURNOVER_FLOOR = 1

DISCLAIMER = "本评分衡量组合与景气度框架的契合度，非组合优劣判断，亦非投资建议；标注「需核实」的项请自行核实。"


def _cfg(config: dict[str, Any] | None) -> dict[str, Any]:
    """合并用户配置与默认配置（仅覆盖本模块声明的键）。"""
    merged = dict(DEFAULT_CONFIG)
    section = (config or {}).get("prosperity_framework") if isinstance(config, dict) else None
    if isinstance(section, dict):
        for key, value in section.items():
            if key in merged and isinstance(value, type(merged[key])):
                merged[key] = value
    return merged


def _matches(text: str, keywords: list[str]) -> bool:
    """关键词命中（大小写不敏感的子串匹配）。"""
    lowered = str(text or "").lower()
    return any(str(k).lower() in lowered for k in keywords)


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole > 0 else 0.0


def _rating(score_pct: int) -> tuple[str, str]:
    for threshold, key, label in RATING_THRESHOLDS:
        if score_pct >= threshold:
            return key, label
    return "low_fit", "不契合"


def _unverified_dimension(key: str, name: str, max_score: int, reason: str) -> dict[str, Any]:
    """构造「未验证」维度结果（不计分、给出可读原因）。"""
    return {
        "key": key,
        "name": name,
        "score": 0,
        "max_score": max_score,
        "status": "unverified",
        "evidence": [],
        "unverified": [reason],
    }


def _guard_dimension(build, key: str, name: str, max_score: int) -> dict[str, Any]:
    """执行单维计算；异常时降级为「未验证」维度（**不得**让单维异常拖垮整份契约）。"""
    try:
        return build()
    except Exception:
        logger.warning("[prosperity_framework] 维度「%s」计算异常，已降级为未验证", name, exc_info=True)
        return _unverified_dimension(key, name, max_score, "该维计算异常，已跳过（详见日志）")


# ── 维度① 景气方向 / 通胀属性 ─────────────────────────────────


def _boom_weights(
    penetration_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> tuple[float, float, list[str], str]:
    """返回 (景气占比, 防御占比, 证据, 口径说明)。

    口径优先穿透后重仓（含基金底层，`penetration_data.top10`）；无穿透数据时退回
    直接持仓的板块分布（`classify_sector`）。
    """
    from src.python.report.penetration import classify_sector

    items: list[tuple[str, str, float]] = []  # (名称, 板块文本, 权重%)
    top10 = (penetration_data or {}).get("top10") or []
    if top10:
        for item in top10:
            text = " ".join([item.get("name", ""), item.get("sector", ""), " ".join(item.get("concepts") or [])])
            items.append((item.get("name", ""), text, finite_or(item.get("ratio_pct"))))
        scope = "穿透后 TOP10 板块/概念分布"
    else:
        total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details) if holdings_details else 0.0
        for d in holdings_details:
            sector = classify_sector(getattr(d, "name", ""), getattr(d, "code", ""))
            weight = _pct(finite_or(getattr(d, "market_value", 0.0)), total)
            items.append((getattr(d, "name", ""), f"{sector} {getattr(d, 'name', '')}", weight))
        scope = "直接持仓板块分布（无穿透数据）"

    covered = sum(w for _, _, w in items)
    boom = sum(w for _, text, w in items if _matches(text, cfg["boom_keywords"]))
    defensive = sum(w for _, text, w in items if _matches(text, cfg["defensive_keywords"]))
    evidence = [
        f"{scope}：覆盖 {covered:.2f}% 市值",
        f"命中景气关键词的权重 {boom:.2f}%、防御/红利关键词 {defensive:.2f}%",
    ]
    return boom, defensive, evidence, scope


def _score_boom(
    penetration_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    boom, defensive, evidence, _scope = _boom_weights(penetration_data, holdings_details, cfg)
    base = _W_BOOM * min(1.0, boom / 60.0)
    penalty = _W_BOOM * defensive * 0.5 / 100.0
    score = max(0, min(_W_BOOM, round(base - penalty)))
    if boom >= 60:
        evidence.append("景气方向占比 ≥60% → 达满分档")
    elif boom > 0:
        evidence.append(f"景气方向占比 {boom:.2f}% → 按 60% 满分档线性折算")
    else:
        evidence.append("未命中任何景气关键词 → 该维 0 分")
    if defensive:
        evidence.append(f"防御/红利方向占比 {defensive:.2f}% 触发反向扣减")
    return {
        "key": "boom_cycle",
        "name": "景气方向/通胀属性",
        "score": score,
        "max_score": _W_BOOM,
        "status": "scored",
        "evidence": evidence,
        "unverified": [],
    }


# ── 维度② ROE 低位弹性 ────────────────────────────────────────


def _score_roe(
    holdings_details: list[dict[str, Any]],
    financial_indicator_data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, float]]:
    """返回 (维度结果, {code: roe})。契约缺失 → unverified（不给分）。"""
    rows = ((financial_indicator_data or {}).get("rows") or []) if financial_indicator_data else []
    if not rows:
        return (
            {
                "key": "roe_elasticity",
                "name": "ROE 低位弹性",
                "score": 0,
                "max_score": _W_ROE,
                "status": "unverified",
                "evidence": [],
                "unverified": ["未取到个股 ROE（功能开关 `financial_indicator` 默认关）→ 该维不计分"],
            },
            {},
        )

    roe_by_code: dict[str, float] = {}
    improving: set[str] = set()
    for row in rows:
        code = str(row.get("code") or "")
        roe = row.get("roe")
        if code and isinstance(roe, (int, float)):
            roe_by_code[code] = float(roe)
        if code and str(row.get("trend") or "").startswith("改善"):
            improving.add(code)

    total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details)
    low_roe_weight = 0.0
    high_roe_weight = 0.0
    missing: list[str] = []
    for d in holdings_details:
        code = getattr(d, "code", "")
        weight = _pct(finite_or(getattr(d, "market_value", 0.0)), total)
        roe = roe_by_code.get(code)
        if roe is None:
            missing.append(f"{getattr(d, 'name', code)}（{code}）")
        elif roe < _LOW_ROE_THRESHOLD:
            low_roe_weight += weight
            if code in improving:
                low_roe_weight += 0.0  # 改善趋势已在证据中标注，计分见下
        else:
            high_roe_weight += weight

    improving_weight = sum(
        _pct(finite_or(getattr(d, "market_value", 0.0)), total)
        for d in holdings_details
        if getattr(d, "code", "") in improving
    )
    base = _W_ROE * min(1.0, low_roe_weight / 50.0)
    bonus = min(4.0, improving_weight / 25.0 * 4.0)
    score = max(0, min(_W_ROE, round(base + bonus)))
    evidence = [
        f"低 ROE（<{_LOW_ROE_THRESHOLD:.0%}）持仓权重 {low_roe_weight:.2f}%（按 50% 满分档折算）",
        f"ROE 年度趋势改善的持仓权重 {improving_weight:.2f}%（加分项）",
    ]
    if high_roe_weight:
        evidence.append(f"已处高位 ROE 的持仓权重 {high_roe_weight:.2f}%（框架偏好低位修复，故不加分）")
    unverified = []
    if missing:
        unverified.append(
            f"未取到 ROE 的标的 {len(missing)} 只：" + "、".join(missing[:5]) + ("…" if len(missing) > 5 else "")
        )
    return (
        {
            "key": "roe_elasticity",
            "name": "ROE 低位弹性",
            "score": score,
            "max_score": _W_ROE,
            "status": "partial" if missing else "scored",
            "evidence": evidence,
            "unverified": unverified,
        },
        roe_by_code,
    )


# ── 维度③ 全球视野 / 中国比较优势 ─────────────────────────────


def _score_global_edge(
    penetration_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    from src.python.core.code_utils import is_a_share_code, is_hk_stock_code

    items: list[tuple[str, float]] = []
    top10 = (penetration_data or {}).get("top10") or []
    if top10:
        for item in top10:
            text = " ".join([item.get("name", ""), item.get("sector", ""), " ".join(item.get("concepts") or [])])
            items.append((text, finite_or(item.get("ratio_pct"))))
    else:
        from src.python.report.penetration import classify_sector

        total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details) or 0.0
        for d in holdings_details:
            sector = classify_sector(getattr(d, "name", ""), getattr(d, "code", ""))
            items.append(
                (f"{sector} {getattr(d, 'name', '')}", _pct(finite_or(getattr(d, "market_value", 0.0)), total))
            )

    edge = sum(w for text, w in items if _matches(text, cfg["global_edge_keywords"]))
    total_mv = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details)
    offshore = sum(
        finite_or(getattr(d, "market_value", 0.0))
        for d in holdings_details
        if not is_a_share_code(getattr(d, "code", "")) or is_hk_stock_code(getattr(d, "code", ""))
    )
    offshore_pct = _pct(offshore, total_mv)
    base = _W_GLOBAL * min(1.0, edge / 40.0)
    bonus = min(5.0, offshore_pct / 20.0 * 5.0)
    score = max(0, min(_W_GLOBAL, round(base + bonus)))
    return {
        "key": "global_edge",
        "name": "全球视野/中国比较优势",
        "score": score,
        "max_score": _W_GLOBAL,
        "status": "scored",
        "evidence": [
            f"命中「中国有全球比较优势」关键词的权重 {edge:.2f}%（按 40% 满分档折算）",
            f"非 A 股 / 港股等境外及港股通资产占比 {offshore_pct:.2f}%（全球暴露加分，上限 5 分）",
        ],
        "unverified": [],
    }


# ── 维度④ 流动性 ──────────────────────────────────────────────


def _score_liquidity(liquidity_signals: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not liquidity_signals:
        return {
            "key": "liquidity",
            "name": "流动性",
            "score": 0,
            "max_score": _W_LIQUIDITY,
            "status": "unverified",
            "evidence": [],
            "unverified": ["未取得流动性信号（场内变现天数需行情 K 线缓存；场外品种无赎回上限）→ 该维不计分"],
        }

    measurable = [s for s in liquidity_signals if s.get("type") == "stock" and s.get("liquidation_days") is not None]
    otc = [s for s in liquidity_signals if s.get("type") == "otc"]
    assumed = [s for s in liquidity_signals if s.get("type") == "assumed_liquid"]
    if not measurable:
        return {
            "key": "liquidity",
            "name": "流动性",
            "score": 0,
            "max_score": _W_LIQUIDITY,
            "status": "unverified",
            "evidence": [],
            "unverified": [
                f"无可计算的场内变现天数（场外 {len(otc)} 只 / 数据缺失按充足处理 {len(assumed)} 只）→ 该维不计分"
            ],
        }

    worst_days = max(finite_or(s.get("liquidation_days")) for s in measurable)
    score = _LIQUIDITY_FLOOR
    for limit, tier_score in _LIQUIDITY_TIERS:
        if worst_days < limit:
            score = tier_score
            break
    unverified = []
    if otc:
        unverified.append(f"场外品种 {len(otc)} 只（无赎回上限，场内变现天数口径不适用）")
    if assumed:
        unverified.append(f"成交额数据缺失、按「流动性充足」假设计算的品种 {len(assumed)} 只")
    return {
        "key": "liquidity",
        "name": "流动性",
        "score": score,
        "max_score": _W_LIQUIDITY,
        "status": "partial" if (otc or assumed) else "scored",
        "evidence": [
            f"最差场内品种全额变现天数 {worst_days:.1f} 日（<1 日 → 10 分，<3 日 → 7 分，<5 日 → 4 分，否则 2 分）",
            f"可计算场内品种 {len(measurable)} 只",
        ],
        "unverified": unverified,
    }


# ── 维度⑤ 集中度与周期拼接 ───────────────────────────────────


def _top10_concentration_pct(holdings_details: list[dict[str, Any]]) -> float | None:
    total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details)
    if total <= 0:
        return None
    values = sorted((finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details), reverse=True)
    return _pct(sum(values[:10]), total)


def _snapshot_holding_codes(snap: Any) -> set[str]:
    """从一期快照中提取持仓代码集合。

    兼容两种形态（快照来源经 `history_snapshot.load_all()`，返回**冻结 dataclass**）：

      - `SnapshotData` 对象：`snap.accounts[*].holdings[*].code`（生产形态）
      - dict 形态：`{"accounts": [{"holdings": [{"code": ...}]}]}` 或
        `{"holdings"/"details": [{"code": ...}]}`（测试/外部注入形态）

    任何字段缺失/类型异常一律按「无该字段」处理（返回值可能为空集），
    由调用方判定该期不可用 —— 本函数**不得抛异常**（诊断功能不拖垮主报告）。
    """
    codes: set[str] = set()

    def _harvest(items: Any) -> None:
        for item in items or []:
            if isinstance(item, dict):
                code = item.get("code")
            else:
                code = getattr(item, "code", None)
            if code:
                codes.add(str(code))

    accounts = getattr(snap, "accounts", None)
    if accounts is None and isinstance(snap, dict):
        accounts = snap.get("accounts")
    for account in accounts or []:
        holdings = getattr(account, "holdings", None)
        if holdings is None and isinstance(account, dict):
            holdings = account.get("holdings")
        _harvest(holdings)

    if not codes and isinstance(snap, dict):
        _harvest(snap.get("holdings") or snap.get("details"))
    return codes


def _turnover_proxy_pct(snapshots: list[Any] | None) -> float | None:
    """换手代理（周期拼接）：最近两期快照持仓集合的变动率（1 - Jaccard）。

    Args:
        snapshots: 按时间升序的快照序列（`SnapshotData` 对象或 dict 形态）。

    Returns:
        变动率百分比；不足两期 / 任一期无持仓 / 形态不可解析时返回 None
        （该子项标记未验证，不计分）。
    """
    if not snapshots or len(snapshots) < 2:
        return None
    try:
        prev, cur = _snapshot_holding_codes(snapshots[-2]), _snapshot_holding_codes(snapshots[-1])
    except Exception:  # 形态异常 → 该子项未验证（不得冒泡）
        logger.warning("[prosperity_framework] 快照形态不可解析，换手代理标记未验证", exc_info=True)
        return None
    if not prev or not cur:
        return None
    union = prev | cur
    if not union:
        return None
    return round((1 - len(prev & cur) / len(union)) * 100, 2)


def _score_concentration(
    holdings_details: list[dict[str, Any]],
    snapshots: list[Any] | None,
    cfg: dict[str, Any],
) -> tuple[dict[str, Any], float | None, float | None]:
    concentration = _top10_concentration_pct(holdings_details)
    turnover = _turnover_proxy_pct(snapshots)
    target = float(cfg["concentration_target_pct"])

    if concentration is None:
        conc_score = None
    elif concentration <= 0:
        conc_score = None
    elif concentration <= target:
        conc_score = 8.0
    elif concentration <= target * 1.4:
        conc_score = 5.0
    else:
        conc_score = 3.0

    if turnover is None:
        turn_score = None
    else:
        turn_score = _TURNOVER_FLOOR
        for limit, tier_score in _TURNOVER_TIERS:
            if turnover >= limit:
                turn_score = tier_score
                break

    evidence: list[str] = []
    unverified: list[str] = []
    if concentration is not None:
        evidence.append(
            f"前十大集中度 {concentration:.2f}%（框架目标 ≤{target:.0f}%：达标 8 分 / 1.4 倍内 5 分 / 更高 3 分）"
        )
    else:
        unverified.append("无可计算的前十大集中度（无正市值持仓）")
    if turnover is not None:
        evidence.append(
            f"换手代理（最近两期快照持仓集合变动率）{turnover:.2f}% → {'高换手加分' if turnover >= 8 else '换手偏低'}"
        )
    else:
        unverified.append("无历史快照（<2 期）→ 换手代理不可算（周期拼接子项不计分）")

    if conc_score is None and turn_score is None:
        status, score = "unverified", 0
    elif conc_score is None or turn_score is None:
        status = "partial"
        score = round((conc_score or 0.0) + (turn_score or 0.0))
    else:
        status, score = "scored", round(conc_score + turn_score)
    score = max(0, min(_W_CONCENTRATION, score))
    return (
        {
            "key": "concentration_cycle",
            "name": "集中度与周期拼接",
            "score": score,
            "max_score": _W_CONCENTRATION,
            "status": status,
            "evidence": evidence,
            "unverified": unverified,
        },
        concentration,
        turnover,
    )


def _benchmark_returns(benchmarks: Any) -> list[tuple[str, float]]:
    """提取对比基准的区间收益率，返回 [(名称, 收益率%), ...]。

    兼容两种形态（**生产为 list**，见 `PortfolioHistoryCalculator.get_combined_timeseries`
    的 `benchmarks` 契约：`[{code, name, bars, total_return_pct, ...}, ...]`）：

      - list/tuple[dict]：生产形态
      - dict[str, dict]：测试/外部注入形态

    非 dict 元素、缺 `total_return_pct`、非有限数值一律跳过（**不得抛异常**）。
    """
    if isinstance(benchmarks, dict):
        items: list[Any] = list(benchmarks.values())
    elif isinstance(benchmarks, (list, tuple)):
        items = list(benchmarks)
    else:
        return []

    out: list[tuple[str, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = item.get("total_return_pct")
        # bool 是 int 子类但语义上不是收益率；仅接受 int/float（字符串一律跳过，
        # 且不可用 finite_or(None) —— 其内部 float(None) 会抛 TypeError）
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        value = finite_or(raw, None)
        if value is None:
            continue
        name = str(item.get("name") or item.get("code") or "基准")
        out.append((name, float(value)))
    return out


# ── 维度⑥ 业绩与回撤印证 ─────────────────────────────────────


def _score_performance(history_data: dict[str, Any] | None) -> dict[str, Any]:
    data = history_data or {}
    status = data.get("status")
    # status: ok（正常）/ degraded（部分持仓缺失，收益口径可用但需标注）/ unavailable（不可用）
    if not data or data.get("total_return_pct") is None or status not in (None, "ok", "degraded"):
        return {
            "key": "performance",
            "name": "业绩与回撤印证",
            "score": 0,
            "max_score": _W_PERFORMANCE,
            "status": "unverified",
            "evidence": [],
            "unverified": ["无可用组合历史走势数据（`history` 配置关闭 / status=unavailable / 样本不足）→ 该维不计分"],
        }

    total_return_pct = finite_or(data.get("total_return_pct"))
    max_drawdown_pct = abs(finite_or(data.get("max_drawdown_pct")))
    bench_pairs = _benchmark_returns(data.get("benchmarks"))
    bench_best_name, bench_best = max(bench_pairs, key=lambda x: x[1]) if bench_pairs else (None, None)

    score = 8 if total_return_pct > 0 else 3
    evidence = [f"组合区间累计收益 {total_return_pct:+.2f}%"]
    if bench_best is not None:
        label = f"{bench_best_name} {bench_best:+.2f}%" if bench_best_name else f"{bench_best:+.2f}%"
        if total_return_pct >= bench_best:
            score += 4
            evidence.append(f"跑赢最强对比基准（{label}）→ 加分")
        else:
            evidence.append(f"未跑赢最强对比基准（{label}）")
    elif data.get("benchmarks"):
        evidence.append("对比基准数据不可解析，仅按组合自身收益/回撤计分")
    drawdown_available = bool(data.get("drawdown_available", True))
    if drawdown_available:
        if max_drawdown_pct <= 15:
            score += 3
            evidence.append(f"最大回撤 {max_drawdown_pct:.2f}%（≤15% → 加分；框架视回撤为进攻性资产的自然结果）")
        elif max_drawdown_pct <= 25:
            score += 1
            evidence.append(f"最大回撤 {max_drawdown_pct:.2f}%（≤25% → 小幅加分）")
        else:
            evidence.append(f"最大回撤 {max_drawdown_pct:.2f}%（>25%）")
    else:
        evidence.append("历史样本不足（<60 交易日）→ 回撤子项未计分（收益部分仍计入）")

    unverified = []
    if status == "degraded":
        unverified.append("组合历史数据 status=degraded（部分持仓缺历史），收益/回撤口径可能不完整")
    if not drawdown_available:
        unverified.append("历史样本不足（<60 交易日）→ 回撤子项不计分")
    return {
        "key": "performance",
        "name": "业绩与回撤印证",
        "score": max(0, min(_W_PERFORMANCE, score)),
        "max_score": _W_PERFORMANCE,
        "status": "partial" if unverified else "scored",
        "evidence": evidence,
        "unverified": unverified,
    }


# ── 持仓视角（可核对清单） ────────────────────────────────────


def _holdings_view(
    holdings_details: list[dict[str, Any]],
    roe_by_code: dict[str, float],
    cfg: dict[str, Any],
    limit: int = 20,
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
            notes.append("ROE 需核实（未取到基本面）")
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
) -> list[dict[str, Any]]:
    """持仓视角清单（异常时返回空清单，不影响契约其余部分）。"""
    try:
        return _holdings_view(holdings_details, roe_by_code, cfg)
    except Exception:
        logger.warning("[prosperity_framework] 持仓视角清单构建异常，已置空", exc_info=True)
        return []


# ── 入口 ──────────────────────────────────────────────────────


def build_prosperity_framework_data(
    holdings_details: list[dict[str, Any]] | None,
    *,
    penetration_data: dict[str, Any] | None = None,
    financial_indicator_data: dict[str, Any] | None = None,
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
        roe_dim, roe_by_code = _score_roe(details, financial_indicator_data)
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
        "holdings_view": _safe_holdings_view(details, roe_by_code, cfg),
        "concentration_pct": concentration,
        "turnover_proxy_pct": turnover,
        "unverified": unverified,
        "partial_notes": partial_notes,
        "notes": notes,
    }
