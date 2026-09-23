"""景气度框架诊断 —— 评分内核（配置默认值 + 权重常量 + 六维打分器）。

职责边界：本模块只做**确定性打分**（入参是已就绪契约数据，出参是六维得分与依据）；
视图装配与对外入口在 ``analysis/prosperity_framework.py``（该模块 re-export 本模块的
私有名，保持既有测试与报告层 import 面不变）。

与 ``prosperity_framework.py`` 的拆分轴是「评分 vs 装配」，两侧单向依赖（装配 → 评分），无循环。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.num_utils import finite_or

logger = logging.getLogger("invest")


# ── 默认配置（可经 config.json 的 `prosperity_framework` 段覆盖） ─────────
def _config_defaults_for_module() -> dict[str, Any]:
    """从配置层单一事实来源读取默认关键词与阈值（`config/_config_defaults._DEFAULT_CONFIG`）。

    词表只维护一处（配置层），本模块不再另存一份 —— 否则两处漂移会导致
    「config.json 加了词、模块默认值里没有」这类假命中（真实持仓复核踩到）。
    配置层不可用时退回内置最小词表（保持功能可用）。
    """
    try:
        from src.python.config import _config_defaults as _cd

        section = _cd._DEFAULT_CONFIG.get("prosperity_framework") or {}
        if section:
            return {key: value for key, value in section.items() if key in _FALLBACK_CONFIG}
    except Exception:  # 配置层不可用（如极简运行环境）→ 退回内置
        logger.debug("[prosperity_framework] 配置层默认值不可读，使用内置回退词表", exc_info=True)
    return dict(_FALLBACK_CONFIG)


_FALLBACK_CONFIG: dict[str, Any] = {
    # 内置最小词表（仅当配置层不可读时使用；正常路径以配置层为准）
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
        "电池",
        "光伏",
        "有色",
        "铜",
        "稀土",
        "军工",
        "创新药",
        "科技",
        "高端装备",
        "制造",
        "能源资源",
        "电力",
    ],
    "global_edge_keywords": [
        "光通信",
        "光模块",
        "半导体设备",
        "半导体材料",
        "芯片",
        "电力设备",
        "电网",
        "锂电",
        "电池",
        "光伏",
        "储能",
        "消费电子",
        "新能源",
        "高端装备",
        "制造",
        "电力",
    ],
    "defensive_keywords": [
        "银行",
        "白酒",
        "食品饮料",
        "公用事业",
        "红利",
        "地产",
        "房地产",
        "保险",
        "消费",
        "债",
        "货币",
        "现金",
    ],
    "concentration_target_pct": 50.0,
}
# 默认配置：单一事实来源为配置层（`config/_config_defaults`），本模块只做读取
DEFAULT_CONFIG: dict[str, Any] = _config_defaults_for_module()
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


def _fund_type_fallback_label(name: str, code: str) -> str:
    """板块识别失败时的**基金类型兜底标签**（返回可被关键词匹配消费的文本）。

    背景（真实持仓复核）：`classify_sector` 依赖品种名称关键词表，QDII/联接/债基/
    宽基 ETF 等常返回 `--`，导致并集口径下大批权重"无板块信息"（实测约 51% 权重）。
    本函数按**基金类型**给出保守标签，标签文本只命中「防御」侧词或不命中任何侧
    （**绝不**把固收/宽基塞进景气侧）：

      - 债券/货币/超短债等固收 → ``债券现金``（命中 `defensive_keywords` 的「债」「货币」）
      - QDII/海外标的 → ``境外资产``（中性；境外暴露已由维度③的境外占比单独加分）
      - 宽基/指数/ETF 联接 → ``宽基指数``（中性）
      - 其余（主动权益等） → ``未分类资产``（中性）

    优先级说明：**ETF/指数判定先于货币基金判定** —— `code_utils.is_money_fund_by_name`
    对含「现金」字样的非货基（如「国证自由现金流 ETF」）也会返回 True，若先判货币会把
    场内权益 ETF 误标为固收/现金，故此处以 ETF/指数为最高优先级。
    """
    from src.python.core.code_utils import (
        is_bond_fund_by_name,
        is_convertible_bond_by_name,
        is_etf_by_name_or_code,
        is_index_fund_by_name,
        is_index_link_by_name,
        is_money_fund_by_name,
        is_qdii_extended,
    )

    if is_etf_by_name_or_code(name, code) or is_index_fund_by_name(name) or is_index_link_by_name(name):
        return "宽基指数"
    if is_qdii_extended(name):
        return "境外资产"
    if is_bond_fund_by_name(name) or is_convertible_bond_by_name(name) or is_money_fund_by_name(name):
        return "债券现金"
    return "未分类资产"


def _sector_weight_items(
    penetration_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]],
) -> tuple[list[tuple[str, float]], float, float, float, int]:
    """构造「板块/概念 → 权重」清单（**并集口径 + 类型兜底 + 归一化**）。

    口径（含两轮真实持仓修订）：

      - **视角一（穿透底层）**：穿透 top10 每项按其 `ratio_pct` 计入；
      - **视角二（持仓自身）**：每个直接持仓按自身组合权重计入 —— 板块优先取
        `classify_sector`，识别失败（`--`，QDII/联接/债基/宽基 ETF 常见）时用
        `_fund_type_fallback_label` 的**基金类型标签**兜底（固收→防御侧、
        境外/宽基/主动权益→中性，绝不进景气侧）；**直接持有的证券**（其代码在
        top10 的 `codes` 中）已在视角一计入，视角二跳过以避免重复；
      - 两视角叠加后按合计**归一**为 100（阈值口径 = 「占合计的占比」；穿透项与
        持仓自身对同一基金会有部分重合，属口径设计，非重复计数错误）。

    Returns:
        (items, covered_pct, penetration_pct, fallback_pct, fallback_count)
    """
    from src.python.report.penetration import classify_sector

    raw: list[tuple[str, float]] = []
    top10 = (penetration_data or {}).get("top10") or []
    covered_codes: set[str] = set()
    pen_pct = 0.0
    for item in top10:
        if not isinstance(item, dict):
            continue
        text = " ".join([str(item.get("name", "")), str(item.get("sector", "")), " ".join(item.get("concepts") or [])])
        weight = finite_or(item.get("ratio_pct"))
        raw.append((text, weight))
        pen_pct += weight
        for code in item.get("codes") or []:
            covered_codes.add(str(code))
        # 注：`sources`（贡献该底层的基金）**不**加入去重集合 —— 基金持仓按其自身
        # 板块/类型标签单独计入（两视角叠加），否则基金权重只能由 top10 底层代表，
        # 实测覆盖率仅 48%（其余 52% 权重无信息）。

    total = sum(finite_or(getattr(d, "market_value", 0.0)) for d in holdings_details)
    fallback_pct = 0.0
    fallback_count = 0
    for d in holdings_details:
        code = str(getattr(d, "code", ""))
        if code and code in covered_codes:
            continue  # 已由穿透项计入，避免重复计数
        name = str(getattr(d, "name", ""))
        weight = _pct(finite_or(getattr(d, "market_value", 0.0)), total)
        sector = classify_sector(name, code)
        if sector in ("--", "", None):
            # 兜底项**只用类型标签参与关键词判定**（不带名称）：类型兜底本就是保守降级，
            # 若把名称一并带入，「自由现金流 ETF」会被防御词「现金」误命中为固收/现金。
            label = _fund_type_fallback_label(name, code)
            raw.append((label, weight))
            fallback_pct += weight
            fallback_count += 1
        else:
            raw.append((f"{sector} {name}", weight))

    covered = sum(w for _, w in raw)
    if covered <= 0:
        return [], 0.0, round(pen_pct, 2), 0.0, 0
    items = [(text, round(w / covered * 100, 2)) for text, w in raw]
    return items, round(covered, 2), round(pen_pct, 2), round(fallback_pct, 2), fallback_count


def _boom_weights(
    penetration_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> tuple[float, float, list[str], str]:
    """返回 (景气占比, 防御占比, 证据, 口径说明)。

    口径：**并集** —— 穿透 top10 各底层标的（含基金持仓拆解）+ 未被穿透覆盖的直接持仓，
    合计覆盖≈100% 市值（见 `_sector_weight_items`）。
    """
    items, covered, pen_pct, fallback_pct, fallback_count = _sector_weight_items(penetration_data, holdings_details)
    # 互斥归类（防御优先）：同一标的可能既命中景气词又命中防御词（如「电力」与「公用事业」
    # 类文本、「债」「现金」类策略名），若各计一次会使两者之和 >100%，故按防御优先归类。
    defensive = sum(w for text, w in items if _matches(text, cfg["defensive_keywords"]))
    boom = sum(
        w for text, w in items if _matches(text, cfg["boom_keywords"]) and not _matches(text, cfg["defensive_keywords"])
    )
    scope = f"口径：穿透底层（{pen_pct:.2f}%）+ 持仓自身板块/类型，两视角叠加（合计 {covered:.2f}%）后归一"
    evidence = [
        f"{scope}",
        f"命中景气关键词的权重 {boom:.2f}%、防御/红利关键词 {defensive:.2f}%（同一标的按防御优先归类，互斥不重复计）",
        f"基金类型兜底 {fallback_count} 只（{fallback_pct:.2f}% 权重，按固收/境外/宽基等类型标签，不计入景气侧）",
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


def _score_roe(
    holdings_details: list[dict[str, Any]],
    financial_indicator_data: dict[str, Any] | None,
    fund_roe_estimates: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, float]]:
    """返回 (维度结果, {code: roe})。契约缺失 → unverified（不给分）。

    fund_roe_estimates：基金重仓股 ROE 加权推演值（`estimate_fund_roe_batch` 产出），
    仅对无直接 ROE 的基金持仓生效；推演值计入评分但在证据中标注「按框架推演」，
    并合并进返回的 roe_by_code 供持仓视角展示（渲染侧据 estimated 集合标注）。
    """
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
    estimates = fund_roe_estimates or {}
    estimated: list[tuple[str, str, float]] = []  # (name, code, covered_pct)
    low_roe_weight = 0.0
    high_roe_weight = 0.0
    missing: list[str] = []
    for d in holdings_details:
        code = getattr(d, "code", "")
        name = getattr(d, "name", code)
        weight = _pct(finite_or(getattr(d, "market_value", 0.0)), total)
        roe = roe_by_code.get(code)
        if roe is None:
            est = estimates.get(code)
            est_roe = (est or {}).get("roe")
            if isinstance(est_roe, (int, float)):
                # 基金重仓股加权推演值：计入评分，证据标注推演属性
                roe = float(est_roe)
                roe_by_code[code] = roe
                estimated.append((name, code, float((est or {}).get("covered_pct") or 0.0)))
            else:
                missing.append(f"{name}（{code}）")
                continue
        if roe < _LOW_ROE_THRESHOLD:
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
    if estimated:
        est_weight = sum(
            _pct(finite_or(getattr(d, "market_value", 0.0)), total)
            for d in holdings_details
            if getattr(d, "code", "") in {c for _, c, _ in estimated}
        )
        basis = estimates.get(estimated[0][1], {}).get("basis", "")
        basis_label = "前十大重仓" if basis == "top10_holdings" else basis
        evidence.append(
            f"基金 ROE 按重仓股加权推演：{len(estimated)} 只基金（组合权重 {est_weight:.2f}%，{basis_label}口径）——按框架推演，非基金披露口径"
        )
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


def _score_global_edge(
    penetration_data: dict[str, Any] | None,
    holdings_details: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    from src.python.core.code_utils import is_a_share_code, is_hk_stock_code

    items, covered, pen_pct, fallback_pct, fallback_count = _sector_weight_items(penetration_data, holdings_details)
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
            f"命中「中国有全球比较优势」关键词的权重 {edge:.2f}%（按 40% 满分档折算；"
            f"口径同维度①（穿透底层 + 持仓自身板块叠加归一，穿透项 {pen_pct:.2f}%）",
            f"非 A 股 / 港股等境外及港股通资产占比 {offshore_pct:.2f}%（全球暴露加分，上限 5 分）",
        ],
        "unverified": [],
    }


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
    otc_all = [s for s in liquidity_signals if s.get("type") == "otc"]
    # 场外计入两档：配置赎回上限（用户实测口径）与类型默认档（推演口径，标非实测）
    otc_configured = [s for s in otc_all if s.get("daily_redemption_limit") and s.get("liquidation_days") is not None]
    otc_default_tier = [
        s for s in otc_all if s.get("estimate_basis") == "type_default" and s.get("liquidation_days") is not None
    ]
    otc_unscored = [
        s
        for s in otc_all
        if s.get("liquidation_days") is None
        or (not s.get("daily_redemption_limit") and s.get("estimate_basis") != "type_default")
    ]
    assumed = [s for s in liquidity_signals if s.get("type") == "assumed_liquid"]
    scored_pool = measurable + otc_configured + otc_default_tier
    if not scored_pool:
        return {
            "key": "liquidity",
            "name": "流动性",
            "score": 0,
            "max_score": _W_LIQUIDITY,
            "status": "unverified",
            "evidence": [],
            "unverified": [
                f"无可计算的变现/赎回天数（场外 {len(otc_all)} 只 / 数据缺失按充足处理 {len(assumed)} 只）→ 该维不计分"
            ],
        }

    worst_days = max(finite_or(s.get("liquidation_days")) for s in scored_pool)
    score = _LIQUIDITY_FLOOR
    for limit, tier_score in _LIQUIDITY_TIERS:
        if worst_days < limit:
            score = tier_score
            break
    unverified = []
    if otc_unscored:
        unverified.append(f"场外品种 {len(otc_unscored)} 只（无赎回上限且类型未识别，未计入）")
    if assumed:
        unverified.append(f"成交额数据缺失、按「流动性充足」假设计算的品种 {len(assumed)} 只")
    evidence = [
        f"最差品种全额变现/赎回天数 {worst_days:.1f} 日（<1 日 → 10 分，<3 日 → 7 分，<5 日 → 4 分，否则 2 分）",
        f"可计算场内品种 {len(measurable)} 只",
    ]
    if otc_configured or otc_default_tier:
        evidence.append(
            f"场外品种计入 {len(otc_configured) + len(otc_default_tier)} 只"
            f"（配置赎回上限 {len(otc_configured)} 只 / 类型默认档 {len(otc_default_tier)} 只——类型默认档为非实测口径）"
        )
    return {
        "key": "liquidity",
        "name": "流动性",
        "score": score,
        "max_score": _W_LIQUIDITY,
        "status": "partial" if (otc_unscored or assumed or otc_default_tier) else "scored",
        "evidence": evidence,
        "unverified": unverified,
    }


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
