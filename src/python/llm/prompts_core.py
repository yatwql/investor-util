"""LLM 提示词核心模块 — System Prompt 常量与基础设施。

从 prompts.py 拆分，包含：
  - System Prompt 常量（_SYSTEM_*）
  - 失败原因常量（FAIL_REASON_*）
  - 缓存前缀（CACHE_PREFIX_LLM）
  - 模块级失败原因记录（LLM_MODULE_FAILURE）
  - 共用格式化函数（_fmt_wan, _fmt_holding_line）
  - 上下文构建块（diff / data_degradation / 收益归因 / 概念板块 / 再平衡 / 竞争语境）
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.python.code_utils import is_qdii_extended

logger = logging.getLogger("invest")

# ── 缓存前缀 ─────────────────────────────────────────────────

CACHE_PREFIX_LLM = "llm_"

# ── 模块级失败原因记录（供 write_llm_sheets 读取以输出具体提示） ──

FAIL_REASON_NOT_CONFIGURED = "not_configured"
FAIL_REASON_API_ERROR = "api_error"
FAIL_REASON_NETWORK_ERROR = "network_error"
FAIL_REASON_TIMEOUT = "timeout"
FAIL_REASON_CIRCUIT_OPEN = "circuit_open"
FAIL_REASON_DISABLED = "disabled"

LLM_MODULE_FAILURE: dict[str, str | dict] = {}
"""{module_key: reason|dict} 各 LLM 模块最近一次生成的失败原因。"""

# ── System Prompt 常量 ───────────────────────────────────────

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

注意：两个情景必须给出方向性判断和具体品种建议，避免"视情况而定"这类模棱两可的表述。

置信度指引：
- 所有调仓建议应附带置信度（高/中/低）
- 偏离阈值越远（如持仓占比 25% 远超警戒线 15%），置信度越高
- 数据源降级期间的信号置信度自动降一级
- 样本量不足（如不足 20 个交易日）的信号标注"数据有限"
"""

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

# ── 上下文构建块 ──────────────────────────────────────────


def _build_diff_context_block(f_context: dict | None) -> str:
    """构建差异上下文文本块（紧凑格式），供 LLM 注入环比分析能力。

    Returns:
        格式化的差异文本块，为空时不做任何注入。
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


def _build_data_degradation_block(f_context: dict | None) -> str:
    """构建数据质量降级上下文文本块。

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


def _build_profit_attribution_block(holdings_details: list[dict] | None) -> str:
    """构建收益归因段落（TOP 5 品种按贡献排序）。"""
    if not holdings_details:
        return ""
    profits = [(h.get("name", ""), h.get("code", ""), h.get("profit", 0) or 0)
               for h in holdings_details]
    total_abs = sum(abs(p[2]) for p in profits)
    if total_abs == 0:
        return ""

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
    """构建再平衡建议段落。"""
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
            p_return = portfolio_returns[-1] * 100 if isinstance(portfolio_returns, list) and portfolio_returns else None
            b_return = benchmark_returns[-1] * 100 if isinstance(benchmark_returns, list) and benchmark_returns else None
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
    code = h.get("code", "")
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
    "_build_diff_context_block",
    "_build_data_degradation_block",
    "_build_profit_attribution_block",
    "_build_concept_sector_block",
    "_build_rebalance_block",
    "_build_competitive_context_block",
]
