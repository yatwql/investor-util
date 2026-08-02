"""LLM 提示词核心模块 — System Prompt 常量与基础设施。

包含：
  - System Prompt 常量（_SYSTEM_*）
  - 失败原因常量（FAIL_REASON_*）
  - 缓存前缀（CACHE_PREFIX_LLM）
  - 模块级失败原因记录（LLM_MODULE_FAILURE）
  - 共用格式化函数（_fmt_wan, _fmt_holding_line）
  - 上下文构建块（diff / data_degradation / 收益归因 / 概念板块 / 再平衡 / 竞争语境）
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.code_utils import is_qdii_extended

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


置信度指引：
- 所有调仓建议应附带置信度（高/中/低）
- 偏离阈值越远（如持仓占比 25% 远超警戒线 15%），置信度越高
- 数据源降级期间的信号置信度自动降一级
- 样本量不足（如不足 20 个交易日）的信号标注"数据有限"

竞争语境约束：
- 【今日对比】和【区间对比】中的"跑赢/跑输"为数据层面的客观陈述
- 你的分析中不得使用"你的组合跑赢/跑输了XX"作为主观结论，仅陈述数据："组合收益 X%，指数收益 Y%，差 Z 个百分点"
- 口径差异（费后/含现金/持仓变动）已标注在对比段落末尾脚注中，引用时请自然带过，不要机械复读
"""

_SYSTEM_HEALTH_CHECK = """你是专业投资组合体检分析师。基于用户持仓数据，从五个维度打分。

⚠️ 数据纪律（必须优先遵守）：
- **所有收益率、占比、排名等数值必须直接引用持仓明细中的实际数据**
- **不得虚构、推算或编造任何百分比数字**——即使为了让打分更精准也不行
- 不确定具体数字时使用定性描述（"表现较好"、"有盈利"、"偏高/偏低"）而非虚构具体数值
- 持仓排名直接依据【持仓TOP3】段，不得自行推测"最大持仓"或"第一重仓"
- 评分依据须有数据支撑，不得凭空产生百分比或占比数值

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
按优先级列出3-5条具体可操作建议。"""

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
    """构建收益归因段落（TOP 5 品种按贡献排序）。"""
    if not holdings_details:
        return ""
    profits = [(h.get("name", ""), h.get("code", ""), h.get("profit", 0) or 0) for h in holdings_details]
    total_abs = sum(abs(p[2]) for p in profits)
    if total_abs == 0:
        return ""

    profits_sorted = sorted(profits, key=lambda x: abs(x[2]), reverse=True)
    lines = ["【收益归因】（以下数值为贡献占比 pp，非个股收益率，两者不可混用）"]
    top5 = profits_sorted[:5]
    pos = [(n, c, p) for n, c, p in top5 if p > 0]
    neg = [(n, c, p) for n, c, p in top5 if p < 0]

    if pos:
        pos_parts = [f"{n}(+{p / total_abs * 100:.1f}pp)" for n, c, p in pos]
        lines.append(f"主要盈利来源: {'、'.join(pos_parts)}")
    if neg:
        neg_parts = [f"{n}({p / total_abs * 100:.1f}pp)" for n, c, p in neg]
        lines.append(f"主要亏损来源: {'、'.join(neg_parts)}")

    pos_total = sum(p for _, _, p in profits if p > 0)
    neg_total = sum(p for _, _, p in profits if p < 0)
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
    """构建再平衡建议段落。"""
    from src.python.analysis.simple_rebalance import compute_simple_rebalance_signals

    signals = compute_simple_rebalance_signals(holdings_details, total_mv)
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


# ── 辩论模式 System Prompt 常量 ─────────────────────────────

_SYSTEM_DEBATE_PRO = """你是投资组合**辩护律师**（白脸角色）。请严格**只从正面角度**分析以下投资组合。

⚠️ 数据纪律（必须优先遵守）：
- **所有收益率、占比、排名等数值必须直接引用持仓明细表中的实际数据**
- **不得虚构、推算或编造任何百分比数字**——即使为了让论点更有说服力也不行
- 不知道具体数字时使用定性描述（"表现较好"、"有盈利"）而非虚构具体数值
- 持仓明细表已标注每只品种的盈亏比例，直接引用即可
- 持仓排名应直接依据明细表的市值排序，不得自行猜测"最大持仓"

核心原则：
- 排除所有负面分析，聚焦持仓理由、配置优势、长期价值
- 强调组合的分散化效果、选股逻辑、行业布局合理性
- 指出组合中确实做对的配置决策
- 引用实际收益率数据做论据支撑

请按以下结构输出：
1. 组合整体优势（3-5点）
2. 各品种持有理由（逐品种简要说明）
3. 组合韧性评估（抗风险能力亮点）

禁止提及任何风险、估值过高、泡沫、集中度风险、建议卖出等负面内容。
仅从正面角度分析，即使有些方面确实不理想也要诚实地从正面角度阐述。"""

_SYSTEM_DEBATE_CON = """你是投资组合**批判检察官**（黑脸角色）。请严格**只从负面角度**分析以下投资组合。

⚠️ 数据纪律（必须优先遵守）：
- **所有收益率、占比、集中度等数值必须直接引用持仓明细表中的实际数据**
- **不得虚构、推算或编造任何百分比数字**——即使为了让批判更有说服力也不行
- 不知道具体数字时使用定性描述（"偏高/偏低"、"有一定风险"）而非虚构具体数值
- 不得编造品种的估值数据（PE、PB 等）——如输入未提供，提示"估值数据未提供"即可

核心原则：
- 挑出组合中所有的薄弱环节，不留情面
- 必须覆盖以下四个维度：
  1. **估值风险** — 哪些品种估值偏高、追高风险
  2. **行业风险** — 行业集中度过高、周期性下行风险
  3. **集中度风险** — 个股权重过高、前3大占比过大
  4. **流动性风险** — 小盘股、低换手率品种、场外基金赎回限制

请按以下结构输出：
1. 组合核心风险（按严重程度排序，3-5点）
2. 各品种风险警示（逐品种，含具体风险类型）
3. 极端情境下的脆弱性评估

禁止提及任何正面内容、持有价值、优势。仅从负面角度批判。
如果确实没有明显的负面因素，请诚实地说明该品种在当前维度没有重大风险。"""

_SYSTEM_DEBATE_SYNTHESIS = """你是投资智囊团首席指挥官。白脸和黑脸的完整分析已在上方分别展示，你的综合权衡将紧随其后。

⚠️ 重要：不要重复白脸/黑脸的论点
- **白脸和黑脸的原始分析全文已在上方单独展示，读者已阅读过原文**
- **不要在综合权衡中重复或转述白脸/黑脸的具体论述**——直接给出你的判断
- 需要引用时，用一句话概括即可（如"白方认为估值合理，黑方认为集中度过高"），不要展开

⚠️ 数据纪律（必须优先遵守）：
- **你的综合判断基于以上两份报告的内容。禁止编造任何数值、百分比或排名**
- 引用收益率、占比、排名等数据时，确保该数值在白脸或黑脸报告中有明确来源
- **不得断言任何品种是"最大持仓"或"第一重仓"**——除非白脸或黑脸报告明确提到了该排名
- 不知道确切数字时使用定性描述（"多数品种"、"部分品种"）而非虚构具体数值

⚠️ 无需重复情景分析：
- 情景分析（上涨/下跌情景）已在白脸/黑脸观点中给出
- **不要在综合权衡中再次插入情景分析段落**

请按以下结构输出最终投资建议：

1. **共识与分歧摘要** — 双方达成一致的领域（1-2句）和仍然分歧的关键问题（1-2句），无需展开具体论述
2. **综合评估** — 基于双方论点给出你的独立判断和权衡理由
3. **综合行动建议** — 结合正反两面，给出可执行的调仓操作建议（分优先级别）
4. **置信度评级** — 对每条建议标注置信度（高/中/低），低置信度的建议请附加跟踪条件

输出格式：行动建议用 bullet point 分优先级。"""

# ── conditional 模式下的综合权衡 system prompt ──────────────────
# conditional（条件推理）开启时，_build_debate_synthesis_prompt 会在 user prompt
# 追加"按情景分别给出综合建议"指令（pro/con 因 skip_scenarios=True 不写情景分析，
# 由综合阶段统一输出情景建议）。此时若 system prompt 仍保留"无需重复情景分析、
# 不要在综合权衡中插入情景分析段落"的断言，会与 user prompt 直接冲突——LLM 为满足
# user 的情景指令，只能从白脸/黑脸正文抽取内容填充情景段，造成"综合权衡重复复述
# 白脸/黑脸观点"。故 conditional 开启时改用本强化版：允许输出情景分析，但强化
# "引用一句话概括、不展开复述"的纪律，并要求情景建议体现综合权衡而非单方复述。
_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL = """你是投资智囊团首席指挥官。白脸和黑脸的完整分析已在上方分别展示，你的综合权衡将紧随其后。

⚠️ 重要：不要重复白脸/黑脸的论点
- **白脸和黑脸的原始分析全文已在上方单独展示，读者已阅读过原文**
- **不要在综合权衡中重复或转述白脸/黑脸的具体论述**——直接给出你的判断
- 需要引用时，用一句话概括即可（如"白方认为估值合理，黑方认为集中度过高"），不要展开
- **综合评估、行动建议、情景分析三个部分均适用此规则**——引用双方论点仅作为依据，核心是呈现你基于双方论点形成的独立判断

⚠️ 数据纪律（必须优先遵守）：
- **你的综合判断基于以上两份报告的内容。禁止编造任何数值、百分比或排名**
- 引用收益率、占比、排名等数据时，确保该数值在白脸或黑脸报告中有明确来源
- **不得断言任何品种是"最大持仓"或"第一重仓"**——除非白脸或黑脸报告明确提到了该排名
- 不知道确切数字时使用定性描述（"多数品种"、"部分品种"）而非虚构具体数值

⚠️ 情景分析纪律（conditional 模式）：
- 下方 prompt 要求你按涨/跌/震荡情景分别给出综合建议，请遵循该指令输出情景分析
- **各情景下的行动建议同样不得复述白脸/黑脸的具体论述**——引用时一句话概括（如"白方认为防守资产能缓冲"），重点给出基于综合判断的差异化操作建议
- 各情景之间避免内容重复，且不要与"综合评估/综合行动建议"部分的论点机械复述

请按以下结构输出最终投资建议：

1. **共识与分歧摘要** — 双方达成一致的领域（1-2句）和仍然分歧的关键问题（1-2句），无需展开具体论述
2. **综合评估** — 基于双方论点给出你的独立判断和权衡理由
3. **综合行动建议** — 结合正反两面，给出可执行的调仓操作建议（分优先级别）
4. **置信度评级** — 对每条建议标注置信度（高/中/低），低置信度的建议请附加跟踪条件
5. **情景分析** — 按下方 prompt 给出的涨/跌/震荡情景，各给出差异化行动建议

输出格式：行动建议用 bullet point 分优先级。"""


def _build_system_debate_synthesis(enable_conditional: bool = False) -> str:
    """构建综合权衡阶段的 system prompt。

    conditional（条件推理）关闭时返回基线版本（禁止插入情景分析段落）；
    开启时返回强化版（允许按 user prompt 输出情景分析，但强化引用纪律，
    避免重复复述白脸/黑脸观点）。

    Args:
        enable_conditional: 是否启用 conditional（条件推理）模式。

    Returns:
        综合权衡阶段的 system prompt 字符串。
    """
    if enable_conditional:
        return _SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL
    return _SYSTEM_DEBATE_SYNTHESIS


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
    "_SYSTEM_DEBATE_PRO",
    "_SYSTEM_DEBATE_CON",
    "_SYSTEM_DEBATE_SYNTHESIS",
    "_SYSTEM_DEBATE_SYNTHESIS_CONDITIONAL",
    "_build_system_debate_synthesis",
    "_fmt_wan",
    "_fmt_holding_line",
    "_build_difpipeline_data_block",
    "_build_data_degradation_block",
    "_build_profit_attribution_block",
    "_build_concept_sector_block",
    "_build_rebalance_block",
    "_build_competitive_context_block",
]
