"""LLM 提示词模块 — System Prompt 常量与构建函数。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.python.code_utils import is_a_share_code, is_hk_stock_code, is_qdii_extended

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════
#  组合历史走势：差异上下文格式化（R3 F1 快照对比 LLM 注入）
# ═══════════════════════════════════════════════════════════


def _build_diff_context_block(f_context: dict | None) -> str:
    """构建差异上下文文本块（紧凑格式），供 LLM 注入环比分析能力。

    当 f_context 中包含 diff 且非首次运行时，输出"相比上次报告"的差异摘要。
    首次运行（is_first_check=True）时输出首次报告标记。
    f_context 为 None 或 diff 为 None 时返回空字符串。

    注意：f_context 中的 diff 由 fetcher/history_diff.HistoryDiff.compute() 生成，
    以 dict 形式传递避免 prompts.py 对 schemas/history 的强依赖。

    Returns:
        格式化的差异文本块，首尾不含换行。为空字符串时不做任何注入。
    """
    if not f_context:
        return ""
    diff = f_context.get("diff")
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
        _a = "、".join(f"{a['name']}({a['code']})" for a in added[:3])
        lines.append(f"新增持仓: {_a}")
    if removed:
        _r = "、".join(f"{r['name']}({r['code']})" for r in removed[:3])
        lines.append(f"清仓: {_r}")
    if increased:
        _i = "、".join(f"{i['name']}+{i['shares_diff']:.0f}份" for i in increased[:3])
        lines.append(f"加仓: {_i}")
    if decreased:
        _d = "、".join(f"{d['name']}{d['shares_diff']:.0f}份" for d in decreased[:3])
        lines.append(f"减仓: {_d}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  数据质量降级上下文（T0-01：DegradationTracker→LLM 接线）
# ═══════════════════════════════════════════════════════════


def _build_data_degradation_block(f_context: dict | None) -> str:
    """构建数据质量降级上下文文本块，供 LLM 感知数据降级状态。

    从 f_context["data_degradation"] 读取由 DegradationTracker.get_log()
    汇总的会话内所有降级事件，格式化为紧凑文本。

    Returns:
        格式化的降级状态文本块。无降级记录时返回空字符串。
    """
    if not f_context:
        return ""
    events = f_context.get("data_degradation")
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


# ═══════════════════════════════════════════════════════════
#  MVP-01: 收益归因计算与注入
# ═══════════════════════════════════════════════════════════


def _build_profit_attribution_block(holdings_details: list[dict] | None) -> str:
    """构建收益归因段落（TOP 5 品种按贡献排序）。

    计算 profit_contribution = profit_i / Σ|profit_j|，
    正负贡献分别列出。Σ|profit_j| = 0 时返回空字符串。

    Args:
        holdings_details: 持仓明细列表（含 profit / name / code）

    Returns:
        格式化的收益归因文本块，数据不可用时返回空字符串。
    """
    if not holdings_details:
        return ""
    profits = [(h.get("name", ""), h.get("code", ""), h.get("profit", 0) or 0)
               for h in holdings_details]
    total_abs = sum(abs(p[2]) for p in profits)
    if total_abs == 0:
        return ""

    # 按贡献降序
    profits_sorted = sorted(profits, key=lambda x: abs(x[2]), reverse=True)

    lines = ["【收益归因】"]
    top5 = profits_sorted[:5]
    pos = [(n, c, p) for n, c, p in top5 if p > 0]
    neg = [(n, c, p) for n, c, p in top5 if p < 0]

    if pos:
        pos_parts = [f"{n}(+{p / total_abs * 100:.1f}%)" for n, c, p in pos]
        lines.append(f"主要盈利来源: {'、'.join(pos_parts)}")
    if neg:
        neg_parts = [f"{n}({p / total_abs * 100:.1f}%)" for n, c, p in neg]
        lines.append(f"主要亏损来源: {'、'.join(neg_parts)}")

    pos_total = sum(p for _, _, p in profits if p > 0)
    neg_total = sum(p for _, _, p in profits if p < 0)
    if pos_total > 0 and neg_total < 0:
        lines.append(f"盈利品种合计 +{_fmt_wan(pos_total)}，亏损品种合计 {_fmt_wan(neg_total)}（净{_fmt_wan(pos_total + neg_total)}）")
    elif pos_total > 0:
        lines.append(f"全部品种盈利，合计 +{_fmt_wan(pos_total)}")
    elif neg_total < 0:
        lines.append(f"全部品种亏损，合计 {_fmt_wan(neg_total)}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  MVP-02: 概念板块占比注入 LLM
# ═══════════════════════════════════════════════════════════


def _build_concept_sector_block(penetrated_assets: list[dict] | None) -> str:
    """构建概念板块占比段落（穿透 TOP10 的概念汇总）。

    从穿透资产的 concepts 字段按市值汇总，TOP 5 概念板块 + 集中度判断。
    概念数据不可用或全部为空时返回兜底文本。

    Args:
        penetrated_assets: 穿透 TOP10 资产列表（含 concepts / mv）

    Returns:
        格式化的概念板块文本块。
    """
    if not penetrated_assets:
        return "暂无概念板块数据（穿透数据不可用）"

    # 收集各概念板块的市值
    concept_mv: dict[str, float] = {}
    for asset in penetrated_assets:
        mv = asset.get("mv", 0) or 0
        concepts = asset.get("concepts") or []
        for c in concepts:
            if isinstance(c, str) and c.strip():
                concept_mv[c.strip()] = concept_mv.get(c.strip(), 0) + mv

    if not concept_mv:
        return "部分品种无概念分类（非 A 股穿透资产天然无概念数据）"

    total_mv = sum(concept_mv.values())
    sorted_concepts = sorted(concept_mv.items(), key=lambda x: -x[1])
    top5 = sorted_concepts[:5]

    lines = ["【概念板块分布】"]
    for name, mv in top5:
        pct = mv / total_mv * 100 if total_mv > 0 else 0
        lines.append(f"- {name}: {_fmt_wan(mv)} ({pct:.1f}%)")

    # 集中度判断
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


# ═══════════════════════════════════════════════════════════
#  MVP-03: 再平衡建议段落（委托 simple_rebalance 计算）
# ═══════════════════════════════════════════════════════════


def _build_rebalance_block(holdings_details: list[dict] | None, total_mv: float) -> str:
    """构建再平衡建议段落。

    委托 src.python.analysis.simple_rebalance.compute_rebalance_signals
    计算信号，格式化为易读文本。

    Returns:
        格式化的再平衡建议文本块，无信号时返回空字符串。
    """
    from src.python.analysis.simple_rebalance import compute_rebalance_signals

    signals = compute_rebalance_signals(holdings_details, total_mv)
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
                f"- {s['name']}({s['code']}) 持仓占比 {weight_pct:.1f}%，"
                f"超出建议上限 {threshold_pct:.0f}%，{s['action']}"
            )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  MVP-04: 竞争语境极简版 — 组合 vs 沪深300
# ═══════════════════════════════════════════════════════════


def _build_competitive_context_block(
    a_indices: dict | None,
    total_mv: float,
    total_today_profit: float,
    history_data: dict | None = None,
) -> str:
    """构建竞争语境段落（组合 vs 沪深300 收益对比）。

    今日对比使用 a_indices 中的 sh000300（沪深300）行情数据。
    上市以来对比需要 history_data（portfolio_history 输出）。
    基准数据不可用时返回兜底文本。

    Returns:
        格式化的竞争语境文本块。
    """
    lines: list[str] = []

    # ── 今日对比 ──
    if a_indices and total_mv > 0:
        csi300 = a_indices.get("sh000300")
        if csi300:
            idx_chg = csi300.get("change_pct")
            portfolio_chg = total_today_profit / total_mv * 100
            lines.append(f"【今日对比】组合 {portfolio_chg:+.2f}% vs 沪深300 {idx_chg:+.2f}%")
            if idx_chg is not None:
                diff = portfolio_chg - idx_chg
                lines.append(f"相对沪深300 {'跑赢' if diff >= 0 else '跑输'} {abs(diff):.2f}%")

    # ── 区间对比（依赖 history_data） ──
    if history_data and isinstance(history_data, dict):
        benchmark_returns = history_data.get("benchmark_returns")
        portfolio_returns = history_data.get("portfolio_returns")
        if benchmark_returns is not None and portfolio_returns is not None:
            p_return = portfolio_returns[-1] * 100 if isinstance(portfolio_returns, list) and portfolio_returns else None
            b_return = benchmark_returns[-1] * 100 if isinstance(benchmark_returns, list) and benchmark_returns else None
            if p_return is not None and b_return is not None:
                lines.append(f"【区间对比】组合累计 {p_return:+.2f}% vs 沪深300 {b_return:+.2f}%")

    if not lines:
        return "暂无足够历史数据进行竞争语境对比"

    return "\n".join(lines)


__all__ = [
    "CACHE_PREFIX_LLM",
    "FAIL_REASON_NOT_CONFIGURED",
    "FAIL_REASON_API_ERROR",
    "FAIL_REASON_NETWORK_ERROR",
    "FAIL_REASON_TIMEOUT",
    "FAIL_REASON_CIRCUIT_OPEN",
    "FAIL_REASON_DISABLED",
    "LLM_MODULE_FAILURE",
    "_SYSTEM_GLOBAL_MACRO",
    "_SYSTEM_EXPERT_REVIEW",
    "_SYSTEM_HEALTH_CHECK",
    "_SYSTEM_PENETRATION_DEEP",
    "_SYSTEM_NEWS_CORRELATION",
    "_fmt_wan",
    "_fmt_holding_line",
    "_build_global_macro_prompt",
    "_build_expert_review_prompt",
    "_build_health_check_prompt",
    "_build_penetration_deep_prompt",
    "_build_holdings_summary",
    "_build_news_correlation_summary",
    "_build_data_degradation_block",
    "_build_profit_attribution_block",
    "_build_concept_sector_block",
    "_build_rebalance_block",
    "_build_competitive_context_block",
]


# ── 缓存前缀 ─────────────────────────────────────────────────

CACHE_PREFIX_LLM = "llm_"


# ── 模块级失败原因记录（供 write_llm_sheets 读取以输出具体提示） ──

# 失败原因常量
FAIL_REASON_NOT_CONFIGURED = "not_configured"
FAIL_REASON_API_ERROR = "api_error"
FAIL_REASON_NETWORK_ERROR = "network_error"
FAIL_REASON_TIMEOUT = "timeout"
FAIL_REASON_CIRCUIT_OPEN = "circuit_open"
FAIL_REASON_DISABLED = "disabled"

LLM_MODULE_FAILURE: dict[str, str | dict] = {}
"""{module_key: reason|dict} 各 LLM 模块最近一次生成的失败原因。
key 为 "global_macro"/"expert_review"/"health_check"/"penetration_deep"，
value 为 FAIL_REASON_* 常量（旧格式），或 {"attempted": [...], "final_status": "success"|reason}（多链格式）。
每次新生成开始时清除对应 key。"""


# ═══════════════════════════════════════════════════════════
#  Prompt 模板
# ═══════════════════════════════════════════════════════════

_SYSTEM_GLOBAL_MACRO = """你是一位资深宏观经济学家。基于市场数据输出中文全球政经局势（500字内）。
分3-4段，覆盖主要经济体政策走向、地缘风险、对持仓潜在影响。纯文本，不要使用HTML标签。"""

_SYSTEM_EXPERT_REVIEW = """你是投资智囊团召集人，审计用户投资组合后按三阶段输出：

Phase 1（召集令）指出组合核心矛盾，挑5位流派对立专家并标明立场。指挥官画像，专家列头衔立场。

Phase 2（圆桌会）两轮辩论：第一轮立足结构提方向，第二轮互相反驳聚焦调仓优先级。

Phase 3（定音锤）指挥官融合辩论给出量化调仓方案和风险提示。禁止调仓穿透层底层资产，只调直接持有品种。

约束：数据来自输入不虚构；每个论点引用品种代码和收益率；全 Markdown 输出；引用北京时间。
标注了"净值:YYYY-MM-DD"的品种其涨跌幅数据截止该日期，并非今日涨跌幅，不得在简报和辩论中提及本日盈亏。
标注了"(QDII滞后1日)"的 QDII 基金净值天然滞后一个交易日，即使净值日期显示为今日，其底层资产定价也截止上一交易日，同样不得讨论本日盈亏。

## 情景分析

请在回复末尾增加 **"### 情景分析"** 二级标题，标题下包含两个子段落：

📈 **上涨情景：如果未来市场上涨 20%…**
- 至少 2 句具体行动建议（如：哪些品种建议止盈、哪些可继续持有、是否加仓等）
- 结合当前持仓结构和盈亏状态给出差异化建议

📉 **下跌情景：如果未来市场下跌 20%…**
- 至少 2 句具体行动建议（如：哪些品种可逢低补仓、是否需要设止损、现金管理建议等）
- 结合品种的当前回撤位置和基本面判断

注意：两个情景必须给出方向性判断和具体品种建议，避免"视情况而定"这类模棱两可的表述。"""

_SYSTEM_HEALTH_CHECK = """你是专业投资组合体检分析师。基于用户持仓数据，从五个维度打分：

## 评分标准（每项满分100）

1. **风险分散度**：评估行业集中度、单品种集中度、穿透资产集中度
2. **流动性**：评估场内/场外比例、停牌风险、基金封闭期
3. **收益合理性**：评估盈亏是否合理、与大盘/同类对比
4. **成本结构**：评估成本分布、浮盈浮亏比
5. **数据质量**：评估输入数据的完整性和可靠性，结合输入中的【数据质量降级】段落：
   - 收盘价异常断点（停牌/零值）
   - T2/T3 降级发生频次（数据源不可用的严重程度）
   - 基金净值更新延迟（净值日期距当前日期）
   - 分红数据状态（是否可获取）
   - 个别品种数据缺失时长（连续缺失交易日数）

## 输出格式（Markdown）

## 综合评分
**总分：XX/100** | 评级：优/良/中/差

## 一、风险分散度（XX/100）
评分依据：…
扣分项：…

## 二、流动性（XX/100）
评分依据：…
风险提示：…

## 三、收益合理性（XX/100）
评分依据：…
异常说明：…

## 四、成本结构（XX/100）
评分依据：…
优化建议：…

## 五、数据质量（XX/100）
评分依据（引用【数据质量降级】中的具体降级事件）：
影响说明：…

## 改进建议
按优先级列出3-5条具体可操作建议。

约束：只引用数据中实际存在的品种，不虚构任何数据。每个判断必须有数据支撑。"""

_SYSTEM_PENETRATION_DEEP = """你是穿透深度分析专家。基于用户穿透 TOP10 数据和持仓行业分类，分析以下维度：

## 输出格式（Markdown）

## 行业集中度分析
- 前 N 大行业及占比
- 集中度风险判断（>30%标注风险）
- 行业分散度评分

## 品种集中度分析
- TOP 10 底层资产及占比（占总市值百分比）
- 单品种风险判断（>15%标注风险）

## 国别/币种暴露
- A股/港股/美股 各占比
- 外汇风险敞口判断

## 综合建议
- 2-3条调整建议

约束：只引用数据中实际存在的品种，不虚构任何数据。
每个结论须有具体数据支撑（占比百分比）。"""

_SYSTEM_NEWS_CORRELATION = """你是一位资深金融分析师。以下会给你多批财经新闻（每批最多5条），请逐批分析每条新闻与用户投资组合持仓的关联性。

关联度标准：
- 高：新闻内容直接涉及持仓品种、所属行业或相关重大政策
- 中：新闻内容与持仓品种有间接关联（产业链、相关行业）
- 低：新闻内容与持仓品种关联较弱
- 无关：新闻内容与持仓品种无明显关联

每批输出一个JSON数组，为本批【每条新闻】分别输出关联分析结果，格式：
[{"idx": 0, "relevance": "高|中|低|无关", "sentiment": "利好|利空|中性", "analysis": "不超过30字的原因分析"}, ...]

每条新闻必须分析，不允许跳过任何一条。idx 对应当前批新闻列表中的序号（0 开始）。
sentiment 字段判断该新闻对持仓的利好/利空影响（结合行业和概念判断）。
只输出JSON，不要其他内容。"""


# ═══════════════════════════════════════════════════════════
#  共享持仓明细格式化（智囊团深度复盘 / 持仓体检报告 / 穿透深度分析共用）
# ═══════════════════════════════════════════════════════════


def _fmt_wan(num: float) -> str:
    """将数值格式化为中文单位（万/亿），减少 token 消耗。"""
    if abs(num) >= 100_000_000:
        return f"{num / 100_000_000:.2f}亿"
    if abs(num) >= 10_000:
        return f"{num / 10_000:.1f}万"
    return f"{num:,.0f}"


def _fmt_holding_line(h: dict, show_cost: bool = False, compact: bool = False) -> str:
    """格式化单条持仓明细行，含净值日期 / QDII 标注。

    Args:
        h: 持仓明细字典（code, market_value, profit, profit_rate,
           nav_date, source_api, name, change_pct, 可选 cost）
        show_cost: 是否显示成本（持仓体检报告用）

    Returns:
        格式化的文本行
    """
    code = h.get("code", "")
    mv = h.get("market_value", 0)
    profit = h.get("profit", 0)
    rate = h.get("profit_rate")  # 可能为 None（成本为 0 时）
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


# ═══════════════════════════════════════════════════════════
#  构建 Prompts
# ═══════════════════════════════════════════════════════════


def _build_global_macro_prompt(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
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

    comp_text = f"\n{competitive_context}" if competitive_context else ""
    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【指数】{idx_text}\n"
        f"【持仓】总市值{total_mv:,.0f} 总盈亏{total_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}\n"
        f"{flow_text}"
        f"{comp_text}"
        f"请基于以上数据，分析当前全球政经局势对持仓的潜在影响。"
    )


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
    return "\n".join(_fmt_holding_line(h, show_cost=show_cost, compact=compact) for h in holdings_details[:limit])


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


def _build_expert_review_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    f_context: dict | None = None,
    competitive_context: str | None = None,
) -> str:
    """构建智囊团深度复盘的用户提示词（紧凑格式）。

    必须包含实际持仓明细（名称、代码、市值、成本、盈亏），
    防止 LLM 虚构持仓代码。同时包含穿透 TOP10 供参考。

    Args:
        f_context: 组合历史走势时间维度上下文（含 diff 差异摘要）。
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），
            可选，由呼叫方构建并传入。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details, compact=True)
    pen_text = _format_penetration_block(penetrated_assets)
    diff_text = _build_diff_context_block(f_context)
    degradation_text = _build_data_degradation_block(f_context)
    attribution_text = _build_profit_attribution_block(holdings_details)
    concept_text = _build_concept_sector_block(penetrated_assets)
    rebalance_text = _build_rebalance_block(holdings_details, total_mv)

    parts = [
        f"【当前时间】{now_bj}（北京时间）",
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f} 今日{total_today_profit:+,.0f}",
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
    if competitive_context:
        parts.append(competitive_context)
    parts += [
        "",
        "【持仓明细】",
        holdings_text,
        "",
        "请严格基于以上【持仓明细】中的品种进行深度复盘，"
        "只引用我实际持有的品种代码（上面列出的），"
        "不要虚构任何持仓代码。每个建议必须引用具体品种的名称和代码。"
        "给出优化建议和风险预警。",
    ]
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
    f_context: dict | None = None,
) -> str:
    """构建持仓体检报告的用户提示词。

    要求 LLM 从风险分散度/流动性/收益合理性/成本结构四维度打分。

    Args:
        f_context: 组合历史走势时间维度上下文（含 diff 差异摘要）。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details, show_cost=True)
    pen_text = _format_penetration_block(penetrated_assets)
    diff_text = _build_diff_context_block(f_context)
    degradation_text = _build_data_degradation_block(f_context)
    attribution_text = _build_profit_attribution_block(holdings_details)

    parts = [
        f"【当前时间】{now_bj}（北京时间）",
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f} 今日{total_today_profit:+,.0f}",
        f"【分布】{' '.join(cat_parts)}{pen_text}",
    ]
    if diff_text:
        parts.append(diff_text)
    if degradation_text:
        parts.append(degradation_text)
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


def _calc_country_exposure(holdings_details: list[dict] | None) -> list[str]:
    """从持仓明细计算国别/币种分布，返回格式化行列表。"""
    exposure: dict[str, float] = {}
    if holdings_details:
        for h in holdings_details:
            code = h.get("code", "")
            mv = h.get("market_value", 0)

            if is_a_share_code(code):
                country = "A股"
            elif is_hk_stock_code(code):
                country = "港股"
            elif code.upper().endswith(".US"):
                country = "美股"
            else:
                country = "其他"

            exposure[country] = exposure.get(country, 0) + mv
    return [f"{k}: {_fmt_wan(v)}" for k, v in sorted(exposure.items(), key=lambda x: -x[1])]


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


# ═══════════════════════════════════════════════════════════
#  新闻关联分析（LLM 增强）
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
