"""fact_checker 子包 — 基础工具函数。

HTML 剥离、句子拆分、上下文摘要、持仓映射与组合数值计算。
"""

from __future__ import annotations

import re

from src.python.llm.fact_checker._constants import _ATTACHED_SUBJECT_MAX_DIST, _NAME_ALIAS_MAP
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


# 描述性尾名匹配最小中文核心长度：LLM 缩写省略基金公司前缀后保留的
# 「描述词+产品后缀」（如"电池主题ETF"→561910"招商中证电池主题ETF"）须含
# ≥3 个汉字才算特异，避免"混合C""股票A"等纯产品型泛词被当作主体。
_DESCRIPTIVE_TAIL_MIN_CJK = 3


def _cjk_len(s: str) -> int:
    """统计字符串中的汉字（CJK 统一表意文字）个数。"""
    return sum(1 for ch in s if "一" <= ch <= "鿿")


def _leading_token(s: str) -> str:
    """取字符串前导的连续数字串（产品代号中的数字部分）。

    如"100ETF联接基金A"→"100"、"ETF"→""、"2040三年A"→"2040"。仅取数字——
    LLM 以「核心名+数字代号」缩写持仓时只保留指数/产品代码数字（"华安纳斯达克
    100"），不含类型尾缀字母（"ETF"等）；若后缀以字母开头（"ETF""C""A"）则
    无数字代号，不生成短尾候选。
    """
    m = re.match(r"[0-9]+", s)
    return m.group(0) if m else ""


def _match_descriptive_tail(
    sentence: str,
    name_to_code: dict[str, str] | None,
    anchor: int,
) -> tuple[str, int] | None:
    """按持仓核心名的「描述性后缀 + 产品后缀」匹配句中主体。

    LLM 常省略基金公司前缀指代持仓（如"电池主题ETF"→561910"招商中证电池
    主题ETF"），全名/别名匹配均失败时会回退全局最近邻 → 误路由到同句其他
    品种。逐持仓取核心名后缀（≥3 汉字）拼接产品后缀（"ETF"/"股票A"/"混合C"
    等）为完整候选，命中句中候选则按 (距锚点距离, 候选长度) 择优；产品后缀
    将候选锚定为产品名而非泛词（"科技""指数"等），避免无谓误路由。

    Returns:
        (code, 最近边距锚点距离)；无命中返回 None。
    """
    best_code: str | None = None
    best_dist: int | None = None
    best_len = 0
    for name, code in sorted((name_to_code or {}).items(), key=lambda kv: -len(kv[0])):
        core = _extract_core_name(name)
        rest = name[len(core) :]
        if len(core) < _DESCRIPTIVE_TAIL_MIN_CJK:
            continue
        # 核心名后缀从最长（完整核心名）到最短（≥3 汉字）逐一尝试；同一持仓
        # 的嵌套后缀可能命中更近位置（如"电池主题ETF"内再命中"池主题ETF"）。
        for start in range(0, len(core) - _DESCRIPTIVE_TAIL_MIN_CJK + 1):
            tail = core[start:]
            if _cjk_len(tail) < _DESCRIPTIVE_TAIL_MIN_CJK:
                continue
            cand = tail + rest
            for m in re.finditer(re.escape(cand), sentence):
                dist = min(abs(m.start() - anchor), abs(m.end() - anchor))
                if best_dist is None or dist < best_dist or (dist == best_dist and len(cand) > best_len):
                    best_code, best_dist, best_len = code, dist, len(cand)
            # 短尾候选：核心名后缀 + 类型后缀的「数字/字母前缀」——LLM 常省略类型尾缀
            # （"ETF联接基金A""(QDII)A"等）仅保留「核心名+数字代号」指代持仓（如
            # "华安纳斯达克100"→040046"华安纳斯达克100ETF联接基金A"、"博时纳斯达克100"
            # →016055），全名/别名/完整长尾候选均不命中 → 回退全局最近邻误路由。
            # 取 rest 的前导字母/数字串（"100ETF联接基金A"→"100"）拼核心名后缀，
            # 仅当前导串是 rest 真前缀（短于 rest）时生成，避免与完整候选重复。
            _short = _leading_token(rest)
            if _short and _short != rest:
                cand_short = tail + _short
                for m in re.finditer(re.escape(cand_short), sentence):
                    dist = min(abs(m.start() - anchor), abs(m.end() - anchor))
                    if best_dist is None or dist < best_dist or (dist == best_dist and len(cand_short) > best_len):
                        best_code, best_dist, best_len = code, dist, len(cand_short)
    return (best_code, best_dist) if best_code is not None else None


def _locate_subject_code(
    sentence: str,
    holding_codes: set[str],
    name_to_code: dict[str, str] | None,
    anchor: int,
) -> str | None:
    """定位句中最可能指代的持仓代码。

    主体来源分四级：句中持仓代码 → 持仓全名 → 简称归一化 → 描述性尾名。
    采用「紧邻优先 + 可靠主体兜底」：
      - 任一来源的主体若紧贴该数值（主体边缘距数值 ≤ _ATTACHED_SUBJECT_MAX_DIST），
        取其中最近者为其主体——同句含代码与多个名称主体时（"040046 收益率
        +130.61%、建设银行收益率 +181.37%"）181.37 紧邻建设银行 → 归 601939，
        不再被句内唯一代码 040046 钉扎误修正；
      - 无紧邻主体时，若句中已有代码/全名则取其中最近者（代码钉扎优先，防远距
        别名/尾名误覆盖；如"040046 ... +130% ... 与博时纳斯达克
        100合计17.4%"，+130% 归最近的代码 040046 而非 17 字符外的尾名 016055）；
      - 仅当句中既无代码也无全名时才以最近的简称/尾名候选作为主体（历史兜底）。

    最近边距离（min(abs(idx-anchor), abs(idx+len(subject)-anchor))）：名称与数值
    相邻时（如"建设银行收益率+171.23%"）若只按起点距离 abs(idx-anchor)，名称
    起点距数值可能与其相邻另一名称（如"工商银行"）平局，先迭代者胜出导致误路由。
    """
    best: str | None = None
    best_dist: int | None = None
    attached: str | None = None
    attached_dist: int | None = None
    has_reliable = False  # 句中是否存在代码或全名（可靠主体）

    def _offer(code: str, dist: int, into_best: bool = True) -> None:
        nonlocal best, best_dist, attached, attached_dist
        if dist <= _ATTACHED_SUBJECT_MAX_DIST:
            if attached_dist is None or dist < attached_dist:
                attached, attached_dist = code, dist
        if into_best and (best_dist is None or dist < best_dist):
            best, best_dist = code, dist

    for cm in _CODE_PATTERN.finditer(sentence):
        code = cm.group(0)
        if code not in holding_codes:
            continue
        has_reliable = True
        _offer(code, min(abs(cm.start() - anchor), abs(cm.end() - anchor)))

    for name, code in sorted((name_to_code or {}).items(), key=lambda kv: -len(kv[0])):
        idx = sentence.find(name)
        if idx == -1:
            continue
        has_reliable = True
        _offer(code, min(abs(idx - anchor), abs(idx + len(name) - anchor)))

    # 简称归一化匹配：先将句中常用简称归一化（"纳指"→"纳斯达克"等），
    # 再与持仓名称核心名前缀匹配。仅在句中确实出现简称（norm != sentence）
    # 时执行，避免额外开销与误匹配。句中已有代码/全名时简称仅以「紧邻」覆盖
    # （不参与全局最近竞争），防止远距简称误路由。
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
            _offer(code, min(abs(_pos - anchor), abs(_pos + len(core) - anchor)), into_best=not has_reliable)

    # 描述性尾名匹配（兜底）：按持仓核心名的「描述性后缀 + 产品后缀」匹配
    # （LLM 省略基金公司前缀，如"电池主题ETF"→561910、"华安纳斯达克100"
    # →040046）。与简称一致：句中已有代码/全名时尾名仅以「紧邻」覆盖。
    _tail = _match_descriptive_tail(sentence, name_to_code, anchor)
    if _tail is not None:
        _code, _dist = _tail
        _offer(_code, _dist, into_best=not has_reliable)

    if attached is not None:
        return attached
    return best
