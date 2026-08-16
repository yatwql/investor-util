"""fact_checker 子包 — 基础工具函数。

HTML 剥离、句子拆分、上下文摘要、持仓映射与组合数值计算。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._constants import _NAME_ALIAS_MAP
from src.python.llm.fact_checker._patterns import _CODE_PATTERN


def _strip_html(html: str) -> str:
    """去除 HTML 标签，返回纯文本。"""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _split_sentences(text: str) -> list[str]:
    """按中英文句号、感叹号、问号、换行拆分句子。"""
    sentences = re.split(r"[。！？\n!?]", text)
    return [s.strip() for s in sentences if s.strip()]


def _sentence_snippet(sentence: str, max_len: int = 50) -> str:
    """截取句子前 max_len 字作为上下文摘要。"""
    s = sentence.replace(" ", "").strip()
    return s[:max_len] + "…" if len(s) > max_len else s


def _extract_holding_map(holdings_details: list[dict] | None) -> dict[str, str]:
    """从持仓明细构建 {code: name} 映射。"""
    result: dict[str, str] = {}
    for d in holdings_details or []:
        code = d.get("code", "") or ""
        name = d.get("name", "") or ""
        if code:
            result[code] = name
    return result


def _calc_portfolio_values(holdings_details: list[dict] | None) -> dict[str, float]:
    """计算组合核心数值。

    Returns:
        {"total_mv": float, "total_cost": float, "total_profit": float, "total_profit_rate": float}
    """
    total_mv = sum(d.get("market_value", 0) or 0 for d in holdings_details or [])
    total_cost = sum(d.get("cost", 0) or 0 for d in holdings_details or [])
    total_profit = total_mv - total_cost
    total_profit_rate = 0.0
    if total_cost and abs(total_cost) > 1e-10:
        total_profit_rate = (total_profit / total_cost) * 100
    return {
        "total_mv": total_mv,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_profit_rate": total_profit_rate,
    }


def _build_stock_rate_map(holdings_details: list[dict] | None) -> dict[str, float]:
    """构建 {code: profit_rate} 映射用于个股级校验。

    每个品种的盈亏比例来自持仓明细中的 profit_rate 字段（百分单位，
    orchestrator 已统一为百分比，如 187.12 = +187.12%），
    用于在 LLM 提及个股收益时进行精准比对，而非一律回退到组合总收益。
    """
    result: dict[str, float] = {}
    for d in holdings_details or []:
        code = d.get("code", "") or ""
        rate = d.get("profit_rate")
        if code and rate is not None:
            result[code] = float(rate)
    return result


def _build_stock_change_map(holdings_details: list[dict] | None) -> dict[str, float]:
    """构建 {code: change_pct} 映射（单日涨跌幅度，百分单位）。

    用于单日涨跌语境校验（如"今日下跌-3.41%"与 601939 的 change_pct=-3.41 比对）。
    """
    result: dict[str, float] = {}
    for d in holdings_details or []:
        code = d.get("code", "") or ""
        chg = d.get("change_pct")
        if code and chg is not None:
            result[code] = float(chg)
    return result


def _extract_core_name(name: str) -> str:
    """提取持仓名称的核心名（首个 ASCII 字母/数字之前的汉字部分）。

    如"华安纳斯达克100ETF联接基金A"→"华安纳斯达克"、"建设银行"→"建设银行"、
    "华安黄金ETF"→"华安黄金"。简称匹配按核心名做前缀包含判断，
    避免被"ETF联接基金A"等类型尾缀干扰。
    """
    if not name:
        return ""
    m = re.search(r"[A-Za-z0-9（(]", name)
    if m:
        return name[: m.start()]
    return name


def _locate_subject_code(
    sentence: str,
    holding_codes: set[str],
    name_to_code: dict[str, str] | None,
    anchor: int,
) -> str | None:
    """定位句中最可能指代的持仓代码。

    优先句中出现的持仓代码（取离 anchor 最近）；无代码时按持仓名称匹配
    （名称越长越具体优先，取离 anchor 最近）。

    补充简称归一化匹配：LLM 常用「机构名+指数简称」缩略指代持仓
    （如"华安纳指"→040046"华安纳斯达克100ETF联接基金A"），全名匹配失败会
    回退全局最近邻 → 反向串位漏检（180.5 恰命中另一品种 601939 真实值）。
    """
    best: str | None = None
    best_dist: int | None = None
    for cm in _CODE_PATTERN.finditer(sentence):
        code = cm.group(0)
        if code not in holding_codes:
            continue
        dist = min(abs(cm.start() - anchor), abs(cm.end() - anchor))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = code
    if best:
        return best
    for name, code in sorted((name_to_code or {}).items(), key=lambda kv: -len(kv[0])):
        idx = sentence.find(name)
        if idx == -1:
            continue
        # 最近边距离（与上方代码分支一致）：名称与数值相邻时（如"建设银行收益率
        # +171.23%"）若只按起点距离 abs(idx-anchor)，名称起点距数值可能与其相邻
        # 另一名称（如"工商银行"）平局，先迭代者胜出导致误路由（把 601939 的
        # 171.23% 误判为 601398 的 70.2%）。改用最近边距离 min(abs(idx-anchor),
        # abs(idx+len(name)-anchor))，紧邻数值的名称唯一胜出。
        dist = min(abs(idx - anchor), abs(idx + len(name) - anchor))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = code
    # 简称归一化匹配：先将句中常用简称归一化（"纳指"→"纳斯达克"等），
    # 再与持仓名称核心名前缀匹配。仅在句中确实出现简称（norm != sentence）
    # 时执行，避免额外开销与误匹配。
    norm = sentence
    for _alias, _canon in sorted(_NAME_ALIAS_MAP.items(), key=lambda kv: -len(kv[0])):
        norm = norm.replace(_alias, _canon)
    if norm != sentence:
        for name, code in sorted((name_to_code or {}).items(), key=lambda kv: -len(kv[0])):
            core = _extract_core_name(name)
            if len(core) < 2:
                continue
            idx = norm.find(core)
            if idx == -1:
                continue
            # 归一化位置映射回原句的近似：减去 norm[:idx] 中别名替换带来的
            # 长度增量（core 内部含 canon 时略有偏差，仅影响多候选排序，
            # 不影响唯一简称的归因）。
            _extra = sum((len(_c) - len(_a)) * norm[:idx].count(_c) for _a, _c in _NAME_ALIAS_MAP.items())
            _pos = idx - _extra
            dist = min(abs(_pos - anchor), abs(_pos + len(core) - anchor))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = code
    return best
