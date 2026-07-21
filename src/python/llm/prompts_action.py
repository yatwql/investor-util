"""LLM 提示词动作模块 — 各模块 Prompt 构建函数。

包含：
  - _build_global_macro_prompt — 全球政经局势
  - _build_expert_review_prompt — 智囊团深度复盘
  - _build_health_check_prompt — 持仓体检报告
  - _build_penetration_deep_prompt — 穿透深度分析
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.python.llm.prompts_core import (
    _build_concept_sector_block,
    _build_data_degradation_block,
    _build_difpipeline_data_block,
    _build_profit_attribution_block,
    _build_rebalance_block,
    _fmt_wan,
)
from src.python.llm.prompts_tables import (
    _calc_country_exposure,
    _build_fx_exposure_block,
    _format_holdings_block,
    _format_penetration_block,
    _build_metrics_table_block,
    _build_data_quality_detail_block,
)

logger = logging.getLogger("invest")

logger = logging.getLogger("invest")



def _build_global_macro_prompt(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
    total_cost: float,
    categories: dict,
    sector_flow: list[dict[str, Any]] | None = None,
    competitive_context: str | None = None,
) -> str:
    """构建全球政经局势的用户提示词（紧凑格式）。

    Args:
        a_indices: A 股指数行情
        us_indices: 美股指数行情
        total_mv: 持仓总市值
        total_profit: 持仓总盈亏
        total_cost: 持仓总成本
        categories: 品种分类计数
        sector_flow: 行业资金流向数据（可选），含主力净流入排名
        competitive_context: 竞争语境文本（可选），由呼叫方构建
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    idx_text = "A股:"
    for idx in (a_indices or {}).values():
        name = idx.get("name", "")
        price = idx.get("price", 0)
        chg = idx.get("change_pct", 0)
        idx_text += f" {name}{price}({chg:+.2f}%)"
    idx_text += "\n美股:"
    for idx in (us_indices or {}).values():
        name = idx.get("name", "")
        price = idx.get("price", 0)
        chg = idx.get("change_pct", 0)
        idx_text += f" {name}{price}({chg:+.2f}%)"

    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    # ── 行业资金流向 ──
    flow_text = ""
    if sector_flow:
        top_sectors = sector_flow[:5]  # 前 5 个行业
        flow_lines = []
        for s in top_sectors:
            name = s.get("name", "")
            chg = s.get("change_pct")
            inflow = s.get("main_net_inflow")
            inflow_pct = s.get("main_net_inflow_pct")
            parts = [f"{name}"]
            if chg is not None:
                parts.append(f"涨跌{chg:+.2f}%")
            if inflow is not None:
                parts.append(f"主力净流入{inflow:,.0f}")
            if inflow_pct is not None:
                parts.append(f"净占比{inflow_pct:.2f}%")
            flow_lines.append("  ".join(parts))
        flow_text = "\n【行业资金流向】\n" + "\n".join(flow_lines)

    total_rate = (total_profit / total_cost * 100) if total_cost else 0.0
    comp_text = f"\n{competitive_context}" if competitive_context else ""
    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【指数】{idx_text}\n"
        f"【持仓】总市值{total_mv:,.0f} 总盈亏{total_profit:+,.0f}（收益率{total_rate:+.2f}%）\n"
        f"【分布】{' '.join(cat_parts)}\n"
        f"{flow_text}"
        f"{comp_text}"
        f"请基于以上数据，分析当前全球政经局势对持仓的潜在影响。"
    )


# ── 集中度反问引导 ──────────────────────────────────────────


def _build_qa_concentration_block(
    holdings_details: list[dict] | None,
    total_mv: float,
    threshold: float = 0.20,
    industry_concentration: dict[str, float] | None = None,
) -> str:
    """构建集中度反问段落。

    检查持仓集中度，命中任一阈值即追加反问段落。
    纯计算函数，不涉及 LLM 调用。

    Args:
        holdings_details: 持仓明细列表，每项含 name/code/mv 等字段。
        total_mv: 持仓总市值。
        threshold: 单品种占比警戒阈值（默认 20%）。
        industry_concentration: 可选行业集中度字典 {行业名: 占比}。

    Returns:
        反问段落字符串（无触发时返回空字符串）。
    """
    if not holdings_details or total_mv <= 0:
        return ""

    questions: list[str] = []

    # 触发器①：单品种占比 > threshold
    for h in holdings_details:
        mv = h.get("mv", 0) or 0
        ratio = mv / total_mv if total_mv > 0 else 0
        if ratio > threshold:
            name = h.get("name", h.get("code", "未知"))
            questions.append(
                f"1. **{name} 占比 {ratio:.1%}**，远超 {threshold:.0%} 警戒线。"
                "若该品种出现极端行情，可能对组合整体造成显著冲击。"
            )
            break  # 只需提示最突出的一个

    # 触发器②：前 3 品种合计 > 60%
    sorted_by_mv = sorted(holdings_details, key=lambda x: x.get("mv", 0) or 0, reverse=True)
    top3_ratio = sum((h.get("mv", 0) or 0) for h in sorted_by_mv[:3]) / total_mv
    if top3_ratio > 0.60:
        questions.append(
            f"2. **前 3 大品种合计 {top3_ratio:.1%}**，集中度偏高。"
            "您是否评估过前 3 品种同时回调对组合的影响？"
        )

    # 触发器③：行业穿透集中度
    if industry_concentration:
        risky_industries = {k: v for k, v in industry_concentration.items() if v > 0.40}
        for ind_name, ind_ratio in sorted(risky_industries.items(), key=lambda x: -x[1]):
            questions.append(
                f"3. **{ind_name}行业穿透后占比 {ind_ratio:.1%}**，"
                "超过 40% 行业集中度预警线。该行业若出现政策或周期风险，"
                "将对穿透层资产产生系统性影响。"
            )
            break  # 只需提示最突出的一个行业

    if not questions:
        return ""

    lines = [
        "\n\n### 思考\n",
        "您是否考虑过以下问题？\n",
    ]
    lines.extend(questions)
    lines.append("\n（以上问题旨在引发思考，无需在本次报告中回答。）")
    return "".join(lines)


# ── 条件推理 + 反问引导 ─────────────────────────────────────
# 通过 _build_expert_review_prompt 的 enable_mode_2/enable_mode_3 参数控制


def _build_expert_review_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    pipeline_data: dict | None = None,
    competitive_context: str | None = None,
    metrics: dict | None = None,
    *,  # 以下为实验模式参数
    enable_mode_2: bool = False,
    enable_mode_3: bool = False,
    industry_concentration: dict[str, float] | None = None,
) -> str:
    """构建智囊团深度复盘的用户提示词（紧凑格式）。

    必须包含实际持仓明细（名称、代码、市值、成本、盈亏），
    防止 LLM 虚构持仓代码。同时包含穿透 TOP10 供参考。

    Args:
        pipeline_data: 组合历史走势时间维度上下文（含 diff 差异摘要）。
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），
            可选，由呼叫方构建并传入。
        metrics: 量化指标字典，compute_all_metrics() 的输出。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details, compact=True)
    pen_text = _format_penetration_block(penetrated_assets)
    diff_text = _build_difpipeline_data_block(pipeline_data)
    degradation_text = _build_data_degradation_block(pipeline_data)
    attribution_text = _build_profit_attribution_block(holdings_details)
    concept_text = _build_concept_sector_block(penetrated_assets)
    rebalance_text = _build_rebalance_block(holdings_details, total_mv)
    fx_text = _build_fx_exposure_block(holdings_details)
    total_rate = (total_profit / total_cost * 100) if total_cost else 0.0

    parts = [
        f"【当前时间】{now_bj}（北京时间）",
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f}（收益率{total_rate:+.2f}%）今日{total_today_profit:+,.0f}",
        f"【分布】{' '.join(cat_parts)}{pen_text}",
    ]
    if diff_text:
        parts.append(diff_text)
    if degradation_text:
        parts.append(degradation_text)
    if attribution_text:
        parts.append(attribution_text)
    if concept_text:
        parts.append(concept_text)
    if rebalance_text:
        parts.append(rebalance_text)
    if fx_text:
        parts.append(fx_text)
    if competitive_context:
        parts.append(competitive_context)
    # 量化指标表格
    metrics_text = _build_metrics_table_block(metrics)
    if metrics_text:
        parts.append(metrics_text)
    # 行动建议模板
    parts.append(
        "\n【行动建议】\n"
        "请在回复末尾增加 **'### 操作建议'** 表格，按优先级排列：\n\n"
        "| 优先级 | 品种 | 建议操作 | 理由 |\n"
        "|:------:|------|:--------:|------|\n"
        "| 🔴 高 | XXX | 减仓/加仓/持有 | 简述理由 |\n"
        "| 🟡 中 | XXX | 减仓/加仓/持有 | 简述理由 |\n"
        "| 🟢 低 | XXX | 减仓/加仓/持有 | 简述理由 |\n"
    )
    parts += [
        "",
        "【持仓明细】",
        holdings_text,
        "",
        "请严格基于以上【持仓明细】中的品种进行深度复盘，"
        "只引用我实际持有的品种代码（上面列出的），"
        "不要虚构任何持仓代码。每个建议必须引用具体品种的名称和代码。\n"
        "【数值精度约束】\n"
        "1. 持仓明细中每只品种已经标注了盈亏比例（如 +6.00% 或 -3.50%），"
        "请直接引用这些数据，不要自行计算或虚构收益率、涨幅等百分比数值。\n"
        "2. 如果需要引用收益归因数据，请参考【收益归因】段落中的占比数据，"
        '并明确标注为「贡献占比」而非收益率。\n'
        "3. 如果对某个数值不确定，请使用定性描述（如「表现较好」、「有盈利」、「亏损」等）"
        "而非虚构具体百分比。\n"
        "4. 提及指数基准时（如沪深300涨跌幅），请保持数值大致合理，"
        "避免与基准指数的实际表现严重偏离。\n"
        "给出优化建议和风险预警。",
    ]

    # ── 条件推理情景追加 ────────────────────────────────
    if enable_mode_2:
        try:
            from src.python.config._core import get_llm_config
            _cfg = get_llm_config()
            _scenarios = (_cfg or {}).get("debate", {}).get("mode_2_conditional", {}).get("scenarios", [])
            if _scenarios:
                scenario_lines = ["\n\n### 情景分析"]
                for _s in _scenarios:
                    _name = _s.get("name", "未知")
                    _desc = _s.get("desc", "")
                    _change = _s.get("change", 0)
                    scenario_lines.append(
                        f"📈 **{_name}情景（{_desc}）**：至少 2 句具体行动建议，"
                        f"分析在 {_desc} 情境下应如何调整持仓。"
                    )
                parts.append("\n".join(scenario_lines))
        except Exception:
            logger.warning("[debate] 条件推理情景追加失败，已跳过")

    # ── 集中度反问引导 ──────────────────────────────────
    if enable_mode_3:
        _qa_block = _build_qa_concentration_block(
            holdings_details, total_mv,
            threshold=0.20,  # 默认值，可由调用方传入
            industry_concentration=industry_concentration,
        )
        if _qa_block:
            parts.append(_qa_block)

    return "\n".join(parts)


def _build_health_check_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    pipeline_data: dict | None = None,
    degradation_events: list[dict] | None = None,
) -> str:
    """构建持仓体检报告的用户提示词。

    要求 LLM 从风险分散度/流动性/收益合理性/成本结构四维度打分。

    Args:
        pipeline_data: 组合历史走势时间维度上下文（含 diff 差异摘要）。
        degradation_events: DegradationTracker.get_log() 输出。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details, show_cost=True)
    pen_text = _format_penetration_block(penetrated_assets)
    diff_text = _build_difpipeline_data_block(pipeline_data)
    degradation_text = _build_data_degradation_block(pipeline_data)
    # 数据质量详情
    dq_detail = _build_data_quality_detail_block(degradation_events)
    attribution_text = _build_profit_attribution_block(holdings_details)
    total_rate = (total_profit / total_cost * 100) if total_cost else 0.0

    parts = [
        f"【当前时间】{now_bj}（北京时间）",
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f}（收益率{total_rate:+.2f}%）今日{total_today_profit:+,.0f}",
        f"【分布】{' '.join(cat_parts)}{pen_text}",
    ]
    if diff_text:
        parts.append(diff_text)
    if degradation_text:
        parts.append(degradation_text)
    if dq_detail:
        parts.append(dq_detail)
    if attribution_text:
        parts.append(attribution_text)
    parts += [
        "",
        "【持仓明细】（含成本）",
        holdings_text,
        "",
        "请从以下五个维度对以上投资组合进行全面体检并打分：",
        "1. 风险分散度 — 行业/品种集中度，结合环比变化趋势评估",
        "2. 流动性 — 场内场外/停牌/封闭期",
        "3. 收益合理性 — 盈亏是否与市场匹配，对比上次报告变化",
        "4. 成本结构 — 成本分布与浮盈浮亏比",
        "5. 数据质量 — 结合【数据质量降级】段落评估数据完整性",
        "按要求的输出格式给出评分和改进建议。",
    ]
    return "\n".join(parts)


def _build_penetration_deep_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
) -> str:
    """构建穿透深度分析的用户提示词。

    要求 LLM 基于穿透 TOP10 和持仓行业分类，
    分析行业集中度、品种集中度、国别/币种暴露。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details)

    # 穿透 TOP10 明细（包含行业/板块）
    pen_list = ""
    if penetrated_assets:
        items = []
        for a in penetrated_assets[:10]:
            name = a.get("name", "")
            codes = ",".join(a.get("codes", []))
            mv = a.get("mv", 0)
            ratio = a.get("ratio", 0)
            sector = a.get("sector", "--")
            items.append(f"{name}({codes}) 市值{_fmt_wan(mv)} 占比{ratio:.1f}% 行业:{sector}")
        pen_list = "\n".join(items)

    # 根据代码前缀推断国别/币种
    country_lines = _calc_country_exposure(holdings_details)

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} 成本{total_cost:,.0f} 盈亏{total_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}\n"
        f"\n"
        f"【持仓明细】\n"
        f"{holdings_text}\n"
        f"\n"
        f"【穿透TOP10底层资产】\n"
        f"{pen_list}\n"
        f"\n"
        f"【国别/币种分布】\n"
        f"{chr(10).join(country_lines)}\n"
        f"\n"
        f"请基于以上数据，从以下维度进行穿透深度分析：\n"
        f"1. 行业集中度评估 — TOP 10 行业及占比，>30%时标注风险\n"
        f"2. 品种集中度评估 — TOP 10 底层资产及占比\n"
        f"3. 国别/币种暴露 — 外汇风险敞口判断\n"
        f"按要求的输出格式给出分析结论和建议。"
    )


# ── 辩论模式：综合 prompt 构建 ──────────────────────────────


def _build_debate_synthesis_prompt(pro_text: str, con_text: str) -> str:
    """构建综合阶段的用户 prompt，包含白脸和黑脸的原始分析全文。

    Args:
        pro_text: 白脸分析的完整文本。
        con_text: 黑脸分析的完整文本。

    Returns:
        格式化的综合 prompt 字符串。
    """
    return (
        f"白脸原始分析：\n\n```markdown\n{pro_text}\n```\n\n"
        f"黑脸原始分析：\n\n```markdown\n{con_text}\n```"
    )


__all__ = [
    "_build_global_macro_prompt",
    "_build_expert_review_prompt",
    "_build_health_check_prompt",
    "_build_penetration_deep_prompt",
    "_build_debate_synthesis_prompt",
    "_build_qa_concentration_block",
]
