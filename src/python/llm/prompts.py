"""LLM 提示词模块 — System Prompt 常量与构建函数。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from src.python.report.classification_utils import is_qdii

logger = logging.getLogger("invest")

__all__ = [
    "_CACHE_PREFIX_LLM",
    "FAIL_REASON_NOT_CONFIGURED", "FAIL_REASON_API_ERROR", "FAIL_REASON_NETWORK_ERROR",
    "FAIL_REASON_TIMEOUT", "FAIL_REASON_CIRCUIT_OPEN", "FAIL_REASON_DISABLED",
    "_LLM_MODULE_FAILURE",
    "_SYSTEM_GLOBAL_MACRO", "_SYSTEM_EXPERT_REVIEW", "_SYSTEM_HEALTH_CHECK",
    "_SYSTEM_PENETRATION_DEEP", "_SYSTEM_NEWS_CORRELATION",
    "_is_qdii", "_fmt_wan", "_fmt_holding_line",
    "_build_global_macro_prompt", "_build_expert_review_prompt", "_build_health_check_prompt",
    "_build_penetration_deep_prompt", "_build_holdings_summary", "_build_news_correlation_summary",
]


# ── 缓存前缀 ─────────────────────────────────────────────────

_CACHE_PREFIX_LLM = "llm_"


# ── 模块级失败原因记录（供 write_llm_sheets 读取以输出具体提示） ──

# 失败原因常量
FAIL_REASON_NOT_CONFIGURED = "not_configured"
FAIL_REASON_API_ERROR = "api_error"
FAIL_REASON_NETWORK_ERROR = "network_error"
FAIL_REASON_TIMEOUT = "timeout"
FAIL_REASON_CIRCUIT_OPEN = "circuit_open"
FAIL_REASON_DISABLED = "disabled"

_LLM_MODULE_FAILURE: dict[str, str] = {}
"""{module_key: reason} 各 LLM 模块最近一次生成的失败原因。
key 为 "global_macro"/"expert_review"/"health_check"/"penetration_deep"，
value 为 FAIL_REASON_* 常量。每次新生成开始时清除对应 key。"""


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
标注了"(QDII滞后1日)"的 QDII 基金净值天然滞后一个交易日，即使净值日期显示为今日，其底层资产定价也截止上一交易日，同样不得讨论本日盈亏。"""

_SYSTEM_HEALTH_CHECK = """你是专业投资组合体检分析师。基于用户持仓数据，从四个维度打分：

## 评分标准（每项满分100）

1. **风险分散度**：评估行业集中度、单品种集中度、穿透资产集中度
2. **流动性**：评估场内/场外比例、停牌风险、基金封闭期
3. **收益合理性**：评估盈亏是否合理、与大盘/同类对比
4. **成本结构**：评估成本分布、浮盈浮亏比

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
        return f"{num/100_000_000:.2f}亿"
    if abs(num) >= 10_000:
        return f"{num/10_000:.1f}万"
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
    rate = h.get("profit_rate", 0)
    nav_date = h.get("nav_date", "")
    source_api = h.get("source_api", "")
    name = h.get("name", "")
    qdii_suffix = "(QDII滞后1日)" if is_qdii(name) else ""

    if show_cost:
        cost = h.get("cost", 0)
        base = f"{code} 成本{_fmt_wan(cost)} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate:+.2f}%)"
    else:
        base = f"{code} 市值{_fmt_wan(mv)} 盈亏{_fmt_wan(profit)}({rate:+.2f}%)"

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
) -> str:
    """构建全球政经局势的用户提示词（紧凑格式）。

    Args:
        a_indices: A 股指数行情
        us_indices: 美股指数行情
        total_mv: 持仓总市值
        total_profit: 持仓总盈亏
        categories: 品种分类计数
        sector_flow: 行业资金流向数据（可选），含主力净流入排名
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

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【指数】{idx_text}\n"
        f"【持仓】总市值{total_mv:,.0f} 总盈亏{total_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}\n"
        f"{flow_text}"
        f"请基于以上数据，分析当前全球政经局势对持仓的潜在影响。"
    )


def _format_holdings_block(holdings_details: list[dict] | None, show_cost: bool = False, compact: bool = False, limit: int = 30) -> str:
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
    lines = []
    for h in holdings_details[:limit]:
        lines.append(_fmt_holding_line(h, show_cost=show_cost, compact=compact))
    return "\n".join(lines)


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
) -> str:
    """构建智囊团深度复盘的用户提示词（紧凑格式）。

    必须包含实际持仓明细（名称、代码、市值、成本、盈亏），
    防止 LLM 虚构持仓代码。同时包含穿透 TOP10 供参考。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details, compact=True)
    pen_text = _format_penetration_block(penetrated_assets)

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f} 今日{total_today_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}{pen_text}\n"
        f"\n"
        f"【持仓明细】\n"
        f"{holdings_text}\n"
        f"\n"
        f"请严格基于以上【持仓明细】中的品种进行深度复盘，"
        f"只引用我实际持有的品种代码（上面列出的），"
        f"不要虚构任何持仓代码。每个建议必须引用具体品种的名称和代码。"
        f"给出优化建议和风险预警。"
    )


def _build_health_check_prompt(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
) -> str:
    """构建持仓体检报告的用户提示词。

    要求 LLM 从风险分散度/流动性/收益合理性/成本结构四维度打分。
    """
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    cat_parts = [f"{k}{v}只" for k, v in (categories or {}).items()]

    holdings_text = _format_holdings_block(holdings_details, show_cost=True)
    pen_text = _format_penetration_block(penetrated_assets)

    return (
        f"【当前时间】{now_bj}（北京时间）\n"
        f"【持仓概况】{holdings_count}只 市值{total_mv:,.0f} "
        f"成本{total_cost:,.0f} 盈亏{total_profit:+,.0f} 今日{total_today_profit:+,.0f}\n"
        f"【分布】{' '.join(cat_parts)}{pen_text}\n"
        f"\n"
        f"【持仓明细】\n"
        f"{holdings_text}\n"
        f"\n"
        f"请从以下四个维度对以上投资组合进行全面体检并打分：\n"
        f"1. 风险分散度 — 行业/品种集中度\n"
        f"2. 流动性 — 场内场外/停牌/封闭期\n"
        f"3. 收益合理性 — 盈亏是否与市场匹配\n"
        f"4. 成本结构 — 成本分布与浮盈浮亏比\n"
        f"按要求的输出格式给出评分和改进建议。"
    )


def _calc_country_exposure(holdings_details: list[dict] | None) -> list[str]:
    """从持仓明细计算国别/币种分布，返回格式化行列表。"""
    _country_map: dict[str, str] = {"hk": "港股", "us": "美股", "sh": "A股", "sz": "A股", "bj": "A股"}
    exposure: dict[str, float] = {}
    if holdings_details:
        for h in holdings_details:
            code = h.get("code", "")
            mv = h.get("market_value", 0)
            prefix = code.split(".")[0].split("_")[0].split("-")[0].lower() if "." in code else code[:2].lower()
            country = _country_map.get(prefix, "其他")
            if prefix.startswith("sh") or prefix.startswith("sz") or prefix.startswith("bj"):
                country = "A股"
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
                for ac in (a.get("codes") or []):
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
        parts.append(
            f"[{i}] 标题: {title}\n"
            f"    摘要: {intro}\n"
            f"    关键词: {keywords or '--'}"
        )
    return "\n".join(parts)
