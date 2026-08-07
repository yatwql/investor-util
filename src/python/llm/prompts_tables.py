"""LLM 提示词表格模块 — 格式化和摘要构建函数。

包含：
  - _format_holdings_block — 持仓明细格式化
  - _format_penetration_block — 穿透 TOP10 格式化
  - _calc_country_exposure — 国别/币种暴露计算
  - _build_holdings_summary — 持仓摘要构建（新闻关联分析用）
  - _build_news_correlation_summary — 新闻摘要构建
  - _build_metrics_table_block — 量化指标表格
  - _build_scenario_block — 情景分析文本块
  - _build_alignment_block — 口径修正文本块
"""

from __future__ import annotations

import logging

from src.python.analysis.fx_exposure import fx_exposure as _fx_exposure
from src.python.core.code_utils import get_currency_by_code
from src.python.llm.prompts_core import _fmt_holding_line, _fmt_wan

logger = logging.getLogger("invest")


def _format_holdings_block(
    holdings_details: list[dict] | None, show_cost: bool = False, compact: bool = False, limit: int = 30
) -> str:
    """将持仓明细格式化为紧凑文本块（共享函数，消除 3 模块重复循环）。

    Args:
        holdings_details: 持仓明细列表
        show_cost: 是否显示成本
        compact: 是否省略今日涨跌幅（减少 token + 缓存更稳定）
        limit: 最大行数

    Returns:
        格式化的持仓明细文本块
    """
    if not holdings_details:
        return ""
    # 按市值降序排列确保与 TOP3 排名一致，消除 LLM 排名幻觉
    sorted_h = sorted(
        holdings_details,
        key=lambda h: -(h.get("market_value", 0) or 0),
    )
    return "\n".join(_fmt_holding_line(h, show_cost=show_cost, compact=compact) for h in sorted_h[:limit])


def _format_penetration_block(penetrated_assets: list[dict] | None, limit: int = 10) -> str:
    """将穿透 TOP10 格式化为紧凑文本块（共享函数）。

    Args:
        penetrated_assets: 穿透资产列表
        limit: 最大条目数

    Returns:
        格式化的穿透文本块
    """
    if not penetrated_assets:
        return ""
    assets = []
    for asset in penetrated_assets[:limit]:
        name = asset.get("name", "")
        codes = ",".join(asset.get("codes", []))
        mv = asset.get("mv", 0)
        sector = asset.get("sector", "--")
        assets.append(f"{name}({codes}){_fmt_wan(mv)}/{sector}")
    return " | 穿透:" + " ".join(assets)


def _calc_country_exposure(holdings_details: list[dict] | None) -> list[str]:
    """从持仓明细计算国别/币种分布，返回格式化行列表。

    使用 code_utils.get_currency_by_code() 统一判定逻辑，
    确保与 fx_exposure.py 的判定结果一致。
    """
    exposure: dict[str, float] = {}
    if holdings_details:
        for h in holdings_details:
            name = h.get("name", "")
            code = h.get("code", "")
            mv = h.get("market_value", 0)

            currency = get_currency_by_code(name, code)
            if currency == "CNY":
                country = "A股"
            elif currency == "HKD":
                country = "港股"
            elif currency == "USD":
                country = "美股"
            else:
                country = "其他"

            exposure[country] = exposure.get(country, 0) + mv
    return [f"{k}: {_fmt_wan(v)}" for k, v in sorted(exposure.items(), key=lambda x: -x[1])]


def _build_metrics_table_block(metrics: dict | None) -> str:
    """构建量化指标表格文本块，供 expert_review prompt 使用。

    Args:
        metrics: compute_all_metrics() 的输出字典

    Returns:
        格式化的指标表格文本块。metrics 为空或全 None 时返回空字符串。
    """
    if not metrics:
        return ""

    lines = ["【量化指标】"]

    # 夏普比率
    sharpe = metrics.get("sharpe_ratio")
    if sharpe is not None:
        sharpe_conf = metrics.get("sharpe_confidence", "low")
        lines.append(f"夏普比率: {sharpe:.2f}（置信度: {sharpe_conf}）")
    else:
        lines.append("夏普比率: --（数据不足）")

    # 卡玛比率
    calmar = metrics.get("calmar_ratio")
    if calmar is not None:
        lines.append(f"卡玛比率: {calmar:.2f}")
    else:
        lines.append("卡玛比率: --")

    # HHI
    hhi_val = metrics.get("hhi")
    hhi_eq = metrics.get("hhi_equivalent")
    if hhi_val is not None and hhi_val > 0:
        conc_level = "低" if hhi_val < 0.1 else "中" if hhi_val < 0.2 else "高"
        if hhi_eq:
            lines.append(f"集中度(HHI): {hhi_val:.4f}（等效{hhi_eq:.0f}只品种, {conc_level}）")
        else:
            lines.append(f"集中度(HHI): {hhi_val:.4f}（{conc_level}）")
    else:
        lines.append("集中度(HHI): --")

    # 胜率
    wr = metrics.get("win_rate", {})
    if isinstance(wr, dict):
        wr_val = wr.get("win_rate", 0)
        winning = wr.get("winning", [])
        losing = wr.get("losing", [])
        lines.append(f"持仓胜率: {wr_val * 100:.1f}%（盈利{len(winning)}只, 亏损{len(losing)}只）")

    # 换手率
    turnover = metrics.get("turnover_rate")
    if turnover is not None:
        lines.append(f"区间换手率: {turnover * 100:.1f}%")

    # Beta
    beta = metrics.get("portfolio_beta")
    beta_conf = metrics.get("beta_confidence", "insufficient")
    if beta is not None:
        beta_desc = "偏高" if beta > 1.2 else "偏低" if beta < 0.8 else "适中"
        lines.append(f"组合Beta: {beta:.2f}（{beta_desc}, 置信度: {beta_conf}）")
    else:
        lines.append("组合Beta: --（数据不足）")

    return "\n".join(lines)


def _build_scenario_block(scenario: dict | None) -> str:
    """构建情景分析文本块。

    基于 scenario_analysis() 的 6 种市场情景输出 Beta CI 传播结果。

    Args:
        scenario: scenario_analysis() 的输出字典

    Returns:
        格式化的情景分析文本块。无数据时返回空字符串。
    """
    if not scenario or not scenario.get("has_data"):
        return ""

    lines = ["【情景分析（Beta 置信区间传播）】"]
    beta = scenario.get("beta")
    if beta is not None:
        lines.append(f"组合 Beta: {beta:.2f}")
    else:
        lines.append("组合 Beta: --")

    scenarios = scenario.get("scenarios", [])
    for s in scenarios:
        mkt = s.get("market_change")
        exp_pct = s.get("expected_change_pct")
        if mkt is None:
            continue
        if exp_pct is not None:
            lines.append(f"  市场 {mkt * 100:+.0f}% → 组合预期 {exp_pct * 100:+.2f}%")
        else:
            lines.append(f"  市场 {mkt * 100:+.0f}% → 组合预期: --")

    return "\n".join(lines)


def _build_alignment_block(alignment_summary: str | None) -> str:
    """构建口径修正文本块。

    Args:
        alignment_summary: compute_alignment_factors() 输出的 summary_text

    Returns:
        口径修正文本块。无数据时返回空字符串。
    """
    if not alignment_summary:
        return ""
    return "\n" + alignment_summary


def _build_data_quality_detail_block(degradation_events: list[dict] | None) -> str:
    """构建数据质量详细信息块，供 health_check prompt 使用。

    从 DegradationTracker 的 events 日志中提取结构化数据质量信息，
    比 _build_data_degradation_block 更详细，包含降级频次和时间。

    Args:
        degradation_events: DegradationTracker.get_log() 的输出

    Returns:
        格式化的数据质量详细文本块
    """
    if not degradation_events:
        return "【数据质量】今日无降级记录，所有数据源正常。"

    lines = ["【数据质量详细状态】"]
    unreachable: dict[str, int] = {}
    empty: dict[str, int] = {}
    degraded_events: list[dict] = []

    for e in degradation_events:
        sk = e.get("source_key", "?")
        ft = e.get("failure_type", "?")
        degraded = e.get("degraded", False)
        if degraded:
            degraded_events.append(e)
        if ft == "unreachable":
            unreachable[sk] = unreachable.get(sk, 0) + 1
        elif ft == "empty":
            empty[sk] = empty.get(sk, 0) + 1

    if unreachable:
        parts = [f"{k}({v}次)" for k, v in sorted(unreachable.items(), key=lambda x: -x[1])]
        lines.append(f"连接失败: {'、'.join(parts)}")
    if empty:
        parts = [f"{k}({v}次)" for k, v in sorted(empty.items(), key=lambda x: -x[1])]
        lines.append(f"数据为空: {'、'.join(parts)}")
    if degraded_events:
        lines.append(f"触发降级: {len(degraded_events)} 次")

    if not unreachable and not empty and not degraded_events:
        lines.append("今日无降级事件")

    return "\n".join(lines)


def _build_fx_exposure_block(holdings_details: list[dict] | None) -> str:
    """构建汇率敞口文本块，供 expert_review prompt 注入。

    调用 fx_exposure() 计算币种分布后格式化为易读文本，
    包含人民币/港币/美元占比摘要。
    """
    result = _fx_exposure(holdings_details)
    if not result or not result.get("exposures"):
        return ""

    lines = ["【币种敞口分布】"]
    for e in result["exposures"]:
        mv_str = _fmt_wan(e["total_mv"])
        lines.append(f"{e['label']}: {e['pct']:.1f}%（市值{mv_str}）")

    if result["hkd_suffix"]:
        lines.append(f"*{result['hkd_suffix']}")

    # 非人民币资产占比
    foreign_pct = sum(e["pct"] for e in result["exposures"] if e["currency"] != "CNY")
    if foreign_pct > 0:
        lines.append(f"非人民币资产合计占比 {foreign_pct:.1f}%，存在汇率波动风险。")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  新闻关联分析
# ═══════════════════════════════════════════════════════════


def _build_holdings_summary(
    holdings: list,
    penetrated_assets: list | None = None,
    industry_data: dict[str, dict] | None = None,
) -> str:
    """构建持仓摘要文本（紧凑格式），供财经新闻热点与持仓关联分析 Prompt 使用。

    可选注入行业分类和概念板块信息（industry_data），
    使 LLM 能更准确判断新闻对持仓的利好/利空影响。

    Args:
        holdings: 持仓列表
        penetrated_assets: 穿透 TOP10 资产（可选）
        industry_data: 行业/概念数据 {code: {industry, concepts, ...}}（可选）

    Returns:
        紧凑格式的持仓摘要文本
    """
    lines: list[str] = []
    for i, h in enumerate(holdings[:20]):
        code = (h.code or "").strip()
        line = f"{i + 1}. {h.name} ({code})"
        if industry_data and code in industry_data:
            idata = industry_data[code]
            tags = []
            if idata.get("industry"):
                tags.append(idata["industry"])
            if idata.get("concepts"):
                tags.extend(idata["concepts"][:3])
            if tags:
                line += f" [{'·'.join(tags)}]"
        lines.append(line)
    if penetrated_assets:
        for a in penetrated_assets[:10]:
            name = a.get("name", "")
            codes = ",".join(a.get("codes", []))
            line = f"    [穿透] {name} ({codes})"
            if industry_data:
                tags = []
                for ac in a.get("codes") or []:
                    ac = ac.strip()
                    if ac in industry_data:
                        idata = industry_data[ac]
                        if idata.get("industry"):
                            tags.append(idata["industry"])
                        if idata.get("concepts"):
                            tags.extend(idata["concepts"][:2])
                if tags:
                    line += f" [{'·'.join(tags)}]"
            lines.append(line)
    return "\n".join(lines)


def _build_news_correlation_summary(news_data: list[dict]) -> str:
    """构建新闻摘要文本（紧凑格式），供财经新闻热点与持仓关联分析 Prompt 使用。

    Args:
        news_data: 关键词匹配后的新闻列表，取前 30 条

    Returns:
        紧凑格式的新闻摘要文本
    """
    parts: list[str] = []
    for i, item in enumerate(news_data[:30]):
        title = (item.get("title") or "")[:120]
        intro = (item.get("intro") or "")[:150]
        keywords = ", ".join(item.get("matched_keywords", []))
        parts.append(f"[{i}] 标题: {title}\n    摘要: {intro}\n    关键词: {keywords or '--'}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
#  统一 prompt 附录（自动注入，所有模块共享）
# ═══════════════════════════════════════════════════════════
# 以下三个块由 generate_llm_module 统一注入到每个模块的
# user prompt 末尾，各模块无需手动调用。
# 新模块自动获得防御，无需逐个追加。


def _build_top3_block(
    holdings_details: list[dict] | None,
    total_mv: float,
) -> str:
    """构建持仓排名文本块（按市值降序 TOP3），供 LLM 直接引用排名信息。

    Args:
        holdings_details: 持仓明细列表。
        total_mv: 持仓总市值。

    Returns:
        TOP3 排名文本块，无数据时返回空字符串。
    """
    if not holdings_details or total_mv <= 0:
        return ""
    sorted_h = sorted(
        [d for d in holdings_details if (d.get("market_value", 0) or 0) > 0],
        key=lambda d: d.get("market_value", 0) or 0,
        reverse=True,
    )
    top_lines = []
    for i, h in enumerate(sorted_h[:3], 1):
        code = h.get("code", "")
        name = h.get("name", "")
        mv = h.get("market_value", 0) or 0
        weight = (mv / total_mv * 100) if total_mv else 0
        rate = h.get("profit_rate")
        rate_str = f"{rate:+.2f}%" if rate is not None else "--"
        top_lines.append(f"  {i}. {name}（{code}）市值{mv:,.0f} 占比{weight:.1f}% 收益率{rate_str}")
    return "\n【持仓TOP3】\n" + "\n".join(top_lines) if top_lines else ""


def _build_data_slot_block(
    holdings_details: list[dict] | None,
    total_mv: float,
    total_cost: float,
    total_profit: float,
) -> str:
    """构建数据速查表——LLM 必须直接使用的精确数值清单。

    放置在 prompt 末尾，降低 LLM 编造收益率的概率。

    Args:
        holdings_details: 持仓明细列表。
        total_mv: 持仓总市值。
        total_cost: 持仓总成本。
        total_profit: 持仓总盈亏。

    Returns:
        数据速查表文本块，无数据时返回空字符串。
    """
    if not holdings_details or total_mv <= 0:
        return ""

    total_rate = (total_profit / total_cost * 100) if total_cost else 0.0

    lines = ["\n【你必须直接使用的数据】"]
    lines.append(f"- 组合累计收益率: {total_rate:+.2f}%")

    # 最大持仓（按市值降序）
    sorted_h = sorted(
        [d for d in holdings_details if (d.get("market_value", 0) or 0) > 0],
        key=lambda d: d.get("market_value", 0) or 0,
        reverse=True,
    )
    if sorted_h:
        top1 = sorted_h[0]
        top1_name = top1.get("name", "")
        top1_code = top1.get("code", "")
        top1_mv = top1.get("market_value", 0) or 0
        top1_weight = (top1_mv / total_mv * 100) if total_mv else 0
        lines.append(f"- 最大持仓: {top1_name}（{top1_code}）占比 {top1_weight:.1f}%")

    # 各品种收益率 TOP10
    rate_lines = []
    for h in sorted_h[:10]:
        code = h.get("code", "")
        name = h.get("name", "")
        rate = h.get("profit_rate")
        if rate is not None:
            rate_lines.append(f"  {name}（{code}）: 收益率 {rate:+.2f}%")
    if rate_lines:
        lines.append("- 各品种盈亏比例:")
        lines.extend(rate_lines)

    lines.append("（以上为精确数据，请直接引用，不得编造或推算替代数值）")
    return "\n".join(lines)


def _build_code_whitelist_block(
    holdings_details: list[dict] | None,
    total_mv: float,
) -> str:
    """构建持仓代码白名单 + 排名断言，防止 LLM 虚构代码和最大持仓声称。

    列出用户持仓中所有合法品种代码，并明确标注按市值排名第 1 的品种，
    让 LLM 无法将不属于该名单的代码声称"最大持仓"。

    Args:
        holdings_details: 持仓明细列表。
        total_mv: 持仓总市值。

    Returns:
        白名单文本块，无数据时返回空字符串。
    """
    if not holdings_details or total_mv <= 0:
        return ""

    sorted_h = sorted(
        [d for d in holdings_details if (d.get("market_value", 0) or 0) > 0],
        key=lambda d: d.get("market_value", 0) or 0,
        reverse=True,
    )
    if not sorted_h:
        return ""

    # 所有合法代码
    all_codes = [h.get("code", "") for h in sorted_h if h.get("code")]
    codes_str = "、".join(all_codes)

    # 排名第 1 的品种
    top1 = sorted_h[0]
    top1_name = top1.get("name", "")
    top1_code = top1.get("code", "")

    return (
        "【持仓代码白名单】\n"
        f"你的持仓中仅包含以下品种代码（共 {len(all_codes)} 个）：{codes_str}\n"
        f"按市值排名第 1 的品种是 {top1_name}（{top1_code}），"
        f"这是唯一可以被称作「最大持仓」「第一重仓」「首要持仓」的品种。\n"
        "严禁在报告中引用上述白名单之外的任何 6 位数字代码作为持仓品种。"
        "任何时候都不应在你的输出中出现白名单之外的 6 位数字代码。"
    )


def _build_prompt_appendix(
    holdings_details: list[dict] | None,
    total_mv: float,
    total_cost: float,
    total_profit: float,
) -> str:
    """构建统一 prompt 附录（TOP3 + 数据速查表 + 代码白名单）。

    由 generate_llm_module 统一注入到每个模块的 user prompt 末尾，
    各模块无需手动调用。确保新模块自动获得三样防御。

    Args:
        holdings_details: 持仓明细列表。
        total_mv: 持仓总市值。
        total_cost: 持仓总成本。
        total_profit: 持仓总盈亏。

    Returns:
        格式化的附录文本块，无数据时返回空字符串。
    """
    parts = []
    top3 = _build_top3_block(holdings_details, total_mv)
    if top3:
        parts.append(top3)
    data_slot = _build_data_slot_block(holdings_details, total_mv, total_cost, total_profit)
    if data_slot:
        parts.append(data_slot)
    whitelist = _build_code_whitelist_block(holdings_details, total_mv)
    if whitelist:
        parts.append(whitelist)
    return "\n\n" + "\n\n".join(parts) if parts else ""


__all__ = [
    "_format_holdings_block",
    "_format_penetration_block",
    "_calc_country_exposure",
    "_build_fx_exposure_block",
    "_build_holdings_summary",
    "_build_news_correlation_summary",
    "_build_metrics_table_block",
    "_build_data_quality_detail_block",
    "_build_top3_block",
    "_build_data_slot_block",
    "_build_code_whitelist_block",
    "_build_prompt_appendix",
]
