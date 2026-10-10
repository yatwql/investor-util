"""LLM 数据块提示词（语义名 prompts_data_blocks）— `_build_*_block` 数据块与格式化辅助。

自 prompts_core 按职责下沉（数据块域）；prompts_core 门面 re-export，
消费方（prompts / prompts_action / prompts_tables / module_fingerprint）导入面不变。
"""

from __future__ import annotations

from src.python.config.anonymizer import mask_holding_code
from src.python.core.code_utils import is_qdii_extended


# ── 上下文构建块 ──────────────────────────────────────────


def _build_difpipeline_data_block(pipeline_data: dict | None) -> str:
    """构建差异上下文文本块（紧凑格式），供 LLM 注入环比分析能力。

    Returns:
        格式化的差异文本块，为空时不做任何注入。
    """
    if not pipeline_data:
        return ""
    diff = pipeline_data.get("diff")
    if diff is None or not isinstance(diff, dict):
        return ""
    if diff.get("is_first_check"):
        return "【对比基准】这是首次生成的报告，暂无历史对比数据。"

    lines: list[str] = []
    days = diff.get("days_since_last_report", 0)
    lines.append(f"【环比对比】距上次报告 {days} 天")

    tv_diff = diff.get("total_value_diff", 0)
    tv_pct = diff.get("total_value_diff_pct", 0)
    lines.append(f"总市值变化: {tv_diff:+,.0f} ({tv_pct:+.2f}%)")

    tp_diff = diff.get("total_pnl_diff", 0)
    lines.append(f"总盈亏变化: {tp_diff:+,.0f}")

    added = diff.get("added", [])
    removed = diff.get("removed", [])
    increased = diff.get("increased", [])
    decreased = diff.get("decreased", [])

    if added:
        _a = "、".join(f"{a['name']}({mask_holding_code(a['code'])})" for a in added[:3])
        lines.append(f"新增持仓: {_a}")
    if removed:
        _r = "、".join(f"{r['name']}({mask_holding_code(r['code'])})" for r in removed[:3])
        lines.append(f"清仓: {_r}")
    if increased:
        _i = "、".join(f"{i['name']}+{i['shares_diff']:.0f}份" for i in increased[:3])
        lines.append(f"加仓: {_i}")
    if decreased:
        _d = "、".join(f"{d['name']}{d['shares_diff']:.0f}份" for d in decreased[:3])
        lines.append(f"减仓: {_d}")

    return "\n".join(lines)


def _build_data_degradation_block(pipeline_data: dict | None) -> str:
    """构建数据质量降级上下文文本块。

    Returns:
        格式化的降级状态文本块。无降级记录时返回空字符串。
    """
    if not pipeline_data:
        return ""
    events = pipeline_data.get("data_degradation")
    if not events or not isinstance(events, list):
        return ""

    degraded = [e for e in events if e.get("degraded")]
    if not degraded:
        return ""

    lines = ["【数据质量降级】"]
    for e in degraded:
        _sk = e.get("source_key", "?")
        _tier = e.get("tier", "?")
        _ft = e.get("failure_type", "?")
        _cnt = e.get("count", 0)
        lines.append(f"- {_sk}: {_tier} 降级 ({_ft}, 累计{_cnt}次)")
    lines.append("（以上数据源部分或完全不可用，分析建议时请考虑数据缺失的影响）")
    return "\n".join(lines)


def _build_profit_attribution_block(holdings_details: list[dict] | None) -> str:
    """构建收益归因段落（TOP 5 品种按贡献排序）。

    复用 `analysis.return_attribution.compute_return_attribution` 的单一计算实现
    （与行动建议归因子块表格共享，避免重复实现），此处仅做提示词段落格式化。
    """
    from src.python.analysis.return_attribution import compute_return_attribution

    data = compute_return_attribution(holdings_details)
    if not data:
        return ""

    lines = ["【收益归因】（贡献占比 pp = 盈亏 ÷ Σ|盈亏|，按持仓成本口径；非个股收益率，两者不可混用）"]
    asset_parts = [f"{i['asset_class']}({i['contribution_pp']:+.1f}pp)" for i in data["大类贡献"]]
    if asset_parts:
        lines.append(f"大类贡献: {'、'.join(asset_parts)}")
    pos = data["盈利来源"]
    neg = data["亏损来源"]
    if pos:
        pos_parts = [f"{i['name']}(+{i['contribution_pp']:.1f}pp)" for i in pos]
        lines.append(f"主要盈利来源: {'、'.join(pos_parts)}")
    if neg:
        neg_parts = [f"{i['name']}({i['contribution_pp']:.1f}pp)" for i in neg]
        lines.append(f"主要亏损来源: {'、'.join(neg_parts)}")

    pos_total = data["pos_total"]
    neg_total = data["neg_total"]
    if pos_total > 0 and neg_total < 0:
        lines.append(
            f"盈利品种合计 +{_fmt_wan(pos_total)}，亏损品种合计 {_fmt_wan(neg_total)}（净{_fmt_wan(pos_total + neg_total)}）"
        )
    elif pos_total > 0:
        lines.append(f"全部品种盈利，合计 +{_fmt_wan(pos_total)}")
    elif neg_total < 0:
        lines.append(f"全部品种亏损，合计 {_fmt_wan(neg_total)}")

    return "\n".join(lines)


def _build_concept_sector_block(penetrated_assets: list[dict] | None) -> str:
    """构建概念板块占比段落（穿透 TOP10 的概念汇总）。"""
    if not penetrated_assets:
        return "暂无概念板块数据"

    concept_mv: dict[str, float] = {}
    for asset in penetrated_assets:
        mv = asset.get("mv", 0) or 0
        concepts = asset.get("concepts") or []
        for c in concepts:
            if isinstance(c, str) and c.strip():
                concept_mv[c.strip()] = concept_mv.get(c.strip(), 0) + mv

    if not concept_mv:
        return "部分品种无概念分类"

    total_mv = sum(concept_mv.values())
    sorted_concepts = sorted(concept_mv.items(), key=lambda x: -x[1])
    top5 = sorted_concepts[:5]

    lines = ["【概念板块分布】"]
    for name, mv in top5:
        pct = mv / total_mv * 100 if total_mv > 0 else 0
        lines.append(f"- {name}: {_fmt_wan(mv)} ({pct:.1f}%)")

    if top5:
        top1_pct = top5[0][1] / total_mv * 100 if total_mv > 0 else 0
        top3_pct = sum(v for _, v in top5[:3]) / total_mv * 100 if total_mv > 0 else 0
        if top1_pct > 40 or top3_pct > 70:
            lines.append("集中度判断: 高")
        elif top1_pct > 20 or top3_pct > 50:
            lines.append("集中度判断: 中")
        else:
            lines.append("集中度判断: 低")

    return "\n".join(lines)


def _build_rebalance_block(holdings_details: list[dict] | None, total_mv: float) -> str:
    """构建再平衡建议段落。

    静默期不适用：LLM 智囊团深度复盘为一次性分析提示，需看到当前全部
    超限信号；且不得读写共享静默期文件（避免与「行动建议」章节相互抑制，
    造成同一报告内再平衡信号不一致）。静默期是用户侧重复建议的 UX 护栏。
    """
    from src.python.analysis.simple_rebalance import compute_simple_rebalance_signals

    signals = compute_simple_rebalance_signals(holdings_details, total_mv, silence_days=0)
    if not signals:
        return ""

    lines = ["【再平衡建议】"]
    for s in signals:
        if s.get("summary"):
            lines.append(f"⚠ {s['message']}")
        else:
            weight_pct = s["weight"] * 100
            threshold_pct = s["threshold"] * 100
            lines.append(
                f"- {s['name']}({mask_holding_code(s['code'])}) 持仓占比 {weight_pct:.1f}%，"
                f"超出建议上限 {threshold_pct:.0f}%，{s['action']}"
            )

    return "\n".join(lines)


def _build_competitive_context_block(
    a_indices: dict | None,
    total_mv: float,
    total_today_profit: float,
    history_data: dict | None = None,
    comparison_indices: dict[str, str] | None = None,
    metrics: dict | None = None,
) -> str:
    """构建竞争语境段落（组合 vs 多指数收益对比，含指标对比）。

    Args:
        a_indices: A 股指数行情字典（由 fetch_indices() 返回）。
        total_mv: 组合总市值。
        total_today_profit: 组合当日盈亏。
        history_data: 历史数据（含 benchmark_returns, portfolio_returns）。
        comparison_indices: {代码: 名称} 对比指数池配置，
            默认 {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"}。
        metrics: 量化指标字典（含 sharpe_ratio、annualized_volatility 等）。
    """
    lines: list[str] = []

    if comparison_indices is None:
        comparison_indices = {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"}

    # ── 今日对比：组合 vs 各指数 ──
    if a_indices and total_mv > 0:
        portfolio_chg = total_today_profit / total_mv * 100
        today_lines: list[str] = []
        for code, name in comparison_indices.items():
            idx_data = a_indices.get(code)
            if not idx_data:
                continue
            idx_chg = idx_data.get("change_pct")
            if idx_chg is None:
                continue
            today_lines.append(f"组合 {portfolio_chg:+.2f}% vs {name} {idx_chg:+.2f}%")

        if today_lines:
            lines.append("【今日对比】" + " | ".join(today_lines))

        # 相对沪深300 跑赢/跑输（沪深300 始终作为主要对比基准）
        csi300 = a_indices.get("sh000300")
        if csi300 and csi300.get("change_pct") is not None:
            diff = portfolio_chg - csi300["change_pct"]
            lines.append(f"相对沪深300 {'跑赢' if diff >= 0 else '跑输'} {abs(diff):.2f}%")

    # ── 区间对比 ──
    if history_data and isinstance(history_data, dict):
        benchmark_returns = history_data.get("benchmark_returns")
        portfolio_returns = history_data.get("portfolio_returns")
        if benchmark_returns is not None and portfolio_returns is not None:
            p_return = (
                portfolio_returns[-1] * 100 if isinstance(portfolio_returns, list) and portfolio_returns else None
            )
            b_return = (
                benchmark_returns[-1] * 100 if isinstance(benchmark_returns, list) and benchmark_returns else None
            )
            if p_return is not None and b_return is not None:
                lines.append(f"【区间对比】组合累计 {p_return:+.2f}% vs 沪深300 {b_return:+.2f}%")

    # ── 指标对比（组合级） ──
    if metrics and isinstance(metrics, dict):
        metric_parts: list[str] = []
        sharpe = metrics.get("sharpe_ratio")
        if sharpe is not None and _is_valid_number(sharpe):
            metric_parts.append(f"夏普 {sharpe:.2f}")
        vol = metrics.get("annualized_volatility")
        if vol is not None and _is_valid_number(vol):
            metric_parts.append(f"年化波动率 {vol:.1%}" if abs(vol) < 1 else f"年化波动率 {vol:.2f}%")
        mdd = metrics.get("max_drawdown")
        if mdd is not None and _is_valid_number(mdd):
            metric_parts.append(f"最大回撤 {mdd:.1%}" if abs(mdd) < 1 else f"最大回撤 {mdd:.2f}%")
        calmar = metrics.get("calmar_ratio")
        if calmar is not None and _is_valid_number(calmar):
            metric_parts.append(f"卡玛 {calmar:.2f}")
        if metric_parts:
            lines.append("【指标对比】" + " | ".join(metric_parts))

    if not lines:
        return "暂无足够历史数据进行竞争语境对比"

    # ── 口径说明（脚注） ──
    lines.append("")
    lines.append(
        "⚠ 口径说明：组合收益为费后净收益，指数为价格指数（非全收益）；"
        "组合含现金管理品种，指数不含；对比期间可能存在持仓变动（非静态组合）。"
        "以上差异可能导致对比结果偏移，仅供大致参考。"
    )

    # ── 幸存者偏差提示 ──
    lines.append(
        "⚠ 幸存者偏差提示：对比指数的成分股/成分基金会定期调整，"
        "表现差的成分可能被剔除，因此指数本身存在幸存者偏差。"
        "你的组合对比结果可能略显保守。"
    )

    return "\n".join(lines)


def _is_valid_number(val: object) -> bool:
    """检查值是否为有效有限数值（排除 None/NaN/Inf）。"""
    import math

    if val is None:
        return False
    if isinstance(val, (int, float)):
        return math.isfinite(val)
    return False


# ── 共用格式化函数 ──────────────────────────────────────────


def _fmt_wan(num: float) -> str:
    """将数值格式化为中文单位（万/亿），减少 token 消耗。"""
    if abs(num) >= 100_000_000:
        return f"{num / 100_000_000:.2f}亿"
    if abs(num) >= 10_000:
        return f"{num / 10_000:.1f}万"
    return f"{num:,.0f}"


def _fmt_holding_line(h: dict, show_cost: bool = False, compact: bool = False) -> str:
    """格式化单条持仓明细行，含净值日期 / QDII 标注。"""
    code = mask_holding_code(h.get("code", ""))
    mv = h.get("market_value", 0)
    profit = h.get("profit", 0)
    rate = h.get("profit_rate")
    rate_str = f"{rate:+.2f}%" if rate is not None else "--"
    nav_date = h.get("nav_date", "")
    source_api = h.get("source_api", "")
    name = h.get("name", "")
    qdii_suffix = "(QDII滞后1日)" if is_qdii_extended(name) else ""

    if show_cost:
        cost = h.get("cost", 0)
        base = f"{code} 成本{_fmt_wan(cost)} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate_str})"
    else:
        base = f"{code} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate_str})"

    if source_api != "tencent" and nav_date:
        return f"{base} 净值:{nav_date}{qdii_suffix}"
    chg = h.get("change_pct", 0)
    if compact:
        return f"{base}{qdii_suffix}"
    return f"{base} 今{chg:+.2f}%{qdii_suffix}"
