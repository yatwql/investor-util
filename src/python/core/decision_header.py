"""决策头词表与确定性归一解析（语义名 decision_header / decision_word）。

把 LLM 自由文本里的决策词（减仓/加仓/持有…）归一到统一方向常量。本模块是
``llm/`` 与 ``report/`` 两层共享的**唯一词表基准**：提示词契约用它声明可选值，
抽取侧用它判方向。

为什么需要确定性解析（而非子串包含）
------------------------------------
朴素的 ``if keyword in cell`` 会在下列情形**静默写反方向**，而误判结果会直接
写入决策账本（``data/state/decision_ledger.jsonl``），日后用真实行情结算时
污染命中率统计——报告上完全看不出异常：

  ===================  ==============  ================
  输入                  子串包含         本模块
  ===================  ==============  ================
  ``不建议加仓``        加仓（+1）       未判定（None）
  ``加仓或减仓``        减仓（−1）       未判定（None）
  ``暂不减仓``          减仓（−1）       未判定（None）
  ===================  ==============  ================

判据（对齐外部 rating.py 修三轮得到的纪律）
------------------------------------------
1. **标签优先于裸词**：整格精确匹配优先，未命中才降级全文扫描。
2. **长词优先**：词表按长度降序匹配。
3. **否定守卫**：命中词紧邻前一字为「不/勿」，或同子句内出现劝阻词，判未命中。
4. **二义不猜**：全文扫描命中多个不同方向时返回 None（不做「取第一个」）。
5. **无默认值兜底**：判不出即 None。**绝不落「持有」或任何方向默认值**——
   这是对「失败→丢默认值填充」型兜底的明确拒绝（默认值会把「模型没说」与
   「模型判定中性」混为一谈）。
"""

from __future__ import annotations

import html as _html
import json
import logging
import re
from typing import Any

from src.python.core.decision_ledger import (
    DIRECTION_FLAT,
    DIRECTION_LONG,
    DIRECTION_SHORT,
)

logger = logging.getLogger("invest")

# ── 词表 ────────────────────────────────────────────────────

CANONICAL_DECISION_WORDS: tuple[tuple[str, int], ...] = (
    ("减仓", DIRECTION_SHORT),
    ("加仓", DIRECTION_LONG),
    ("持有", DIRECTION_FLAT),
)
"""规范词 —— 提示词契约固定的三值枚举（``llm/prompts_action.py`` 操作建议表）。"""

EXTENDED_DECISION_WORDS: tuple[tuple[str, int], ...] = (
    ("清仓", DIRECTION_SHORT),
    ("减持", DIRECTION_SHORT),
    ("卖出", DIRECTION_SHORT),
    ("止损", DIRECTION_SHORT),
    ("增持", DIRECTION_LONG),
    ("买入", DIRECTION_LONG),
    ("建仓", DIRECTION_LONG),
    ("观望", DIRECTION_FLAT),
)
"""扩展词 —— 模型措辞漂移容忍，**只收语义单向无歧义者**。

刻意不收 ``止盈``（可能只是落袋一部分，也可能指向清仓）与 ``调仓``（方向不明）：
宁可判不出（None，不登记），不可判错（写反方向）。
"""

DECISION_WORDS: tuple[tuple[str, int], ...] = tuple(
    sorted(CANONICAL_DECISION_WORDS + EXTENDED_DECISION_WORDS, key=lambda kv: -len(kv[0]))
)
"""匹配用词表（长词优先）。"""

# 优先级词表（提示词契约：高/中/低）
PRIORITY_LEVELS: tuple[tuple[str, str], ...] = (
    ("低", "low"),
    ("中", "mid"),
    ("高", "high"),
)
PRIORITY_DEFAULT = "mid"
MAGNITUDE_RANK: dict[str, int] = {"low": 0, "mid": 1, "high": 2}

# ── 判据用常量 ──────────────────────────────────────────────

NEGATION_PREFIXES: tuple[str, ...] = (
    "不建议",
    "不宜",
    "暂不",
    "暂缓",
    "无需",
    "不必",
    "不用",
    "不再",
    "不要",
    "不应",
    "避免",
    "防止",
    "切勿",
    "切忌",
    "切莫",
)
"""劝阻短语 —— 出现在同一子句内则其后的决策词判未命中。

覆盖「不建议加仓」（劝阻）与「不再减仓」（终止）两类：二者都会让决策词失去
方向语义，若照常判定即为写反方向。宁可判不出（None，不登记），不可判错。
"""

NEGATION_ADJACENT_CHARS = "不勿"
"""紧邻前置否定字 —— 如「不建仓」「勿减仓」。仅判紧邻，避免「不断加仓」被误杀。"""

COMPOUND_PREFIX_CHARS = "加减增"
"""复合词左边界字 —— 命中词紧邻左字符若属此集合，判为复合词的一部分而跳过。

中文无词间空格，字符级匹配无法照搬拉丁语的 ``\\b``。但「加减仓位」「增减持」
这类复合短语里嵌着的决策词**并不表达该方向**，照常判定会静默写反方向。
取「加减增」三字依据：只有它们能与其后的 仓/持 组成方向二义的复合短语；
不收 持/买/卖/清/观/止/建 —— 那会误杀「坚持持有」「逢低买入」等正常表述。
"""

_CLAUSE_SEPARATORS = "，。；、！？,.;:!?\n"

# 装饰字符剥离：保留 \w（含中文/字母/数字）与子句分隔符，去掉 emoji/括号/空白等
_KEEP_RE = re.compile(r"[^\w" + re.escape(_CLAUSE_SEPARATORS) + r"]+", re.UNICODE)
# 整格精确匹配用：去掉包括分隔符在内的一切非词字符
_COMPACT_RE = re.compile(r"[\W_]+", re.UNICODE)
_CLAUSE_SPLIT_RE = re.compile("[" + re.escape(_CLAUSE_SEPARATORS) + "]")

# 结构化决策头契约标识（提示词侧追加、抽取侧优先读取），开关名同字面量
STRUCTURED_HEADER_FLAG = "decision_header_parse"
STRUCTURED_HEADER_MARKER = "决策头："

# 6 位代码：与 decision_llm_capture 同一形态判据（前后非数字，兼容 sh600000）
_CODE_RE = re.compile(r"(?<!\d)([0-9]{6})(?!\d)")


# ── 文本规整 ────────────────────────────────────────────────


def strip_marks(text: str | None) -> str:
    """去 HTML 标签/实体与装饰字符，保留子句分隔符（否定守卫需要）。"""
    if not text:
        return ""
    value = text
    if "<" in value:
        value = re.sub(r"<[^>]+>", " ", value)
        value = _html.unescape(value)
    return _KEEP_RE.sub("", value)


def _compact(text: str | None) -> str:
    return _COMPACT_RE.sub("", text or "")


def extract_code(text: str | None) -> str | None:
    """取出文本中的 6 位数字代码（前后非数字）；无则返回 ``None``。

    用「前后非数字」而非 ``\\b`` 词界——``\\b`` 在 ``sh600000``（字母紧邻数字）
    不成立，无法抽出带交易所前缀持仓的裸 6 位别名。
    """
    if not text:
        return None
    match = _CODE_RE.search(str(text))
    return match.group(1) if match else None


# ── 决策词归一 ──────────────────────────────────────────────


def parse_priority(text: str | None) -> str:
    """优先级单元格 → magnitude（``high``/``mid``/``low``）；未识别落 ``mid``。

    优先级无「判错污染账本」风险（仅影响同日去重时保留哪一条），故保留默认值。
    """
    cell = _compact(text)
    for level, magnitude in PRIORITY_LEVELS:
        if level in cell:
            return magnitude
    return PRIORITY_DEFAULT


def _is_negated(clause_text: str, pos: int) -> bool:
    """判 ``clause_text[pos]`` 起的位置是否处于否定语境。

    Args:
        clause_text: 已规整（保留分隔符）的文本
        pos: 决策词起始下标
    """
    if pos > 0 and clause_text[pos - 1] in NEGATION_ADJACENT_CHARS:
        return True
    clause_start = 0
    for match in _CLAUSE_SPLIT_RE.finditer(clause_text, 0, pos):
        clause_start = match.end()
    return any(prefix in clause_text[clause_start:pos] for prefix in NEGATION_PREFIXES)


def is_compound_fragment(kept_text: str, pos: int) -> bool:
    """判 ``kept_text[pos]`` 起的命中词是否为复合词片段（如「加减[仓]位」）。"""
    return pos > 0 and kept_text[pos - 1] in COMPOUND_PREFIX_CHARS


def parse_decision_word(text: str | None, *, allow_scan: bool = True) -> int | None:
    """把决策文本归一为方向常量（``DIRECTION_LONG``/``SHORT``/``FLAT``）。

    Args:
        text: 待解析文本（表格单元格、结构化字段或自由文本）
        allow_scan: 整格精确匹配未命中时是否降级全文扫描。表格单元格场景传
            True（模型可能写成「加仓（价值修复）」）；需要严格「整格即词」时
            传 False。

    Returns:
        方向常量；判不出或多义时返回 ``None``（不做默认值兜底）。
    """
    if not text:
        return None
    compact = _compact(text)
    if not compact:
        return None
    # ① 标签优先：整格即词
    for word, direction in DECISION_WORDS:
        if compact == word:
            return direction
    if not allow_scan:
        return None
    # ② 全文扫描：长词优先 + 否定守卫；命中多方向则视为二义不猜
    kept = strip_marks(text)
    if not kept:
        return None
    found: set[int] = set()
    for word, direction in DECISION_WORDS:
        for match in re.finditer(re.escape(word), kept):
            if _is_negated(kept, match.start()) or is_compound_fragment(kept, match.start()):
                continue
            found.add(direction)
    if len(found) == 1:
        return found.pop()
    return None


# ── 结构化决策头 ────────────────────────────────────────────


def build_structured_header_instruction() -> str:
    """结构化决策头的提示词契约文本（仅在开关开启时追加）。

    与 ``parse_structured_header`` 的解析口径严格对应：``action`` 三值枚举、
    ``priority`` 三值枚举。二者由测试互相锁定。
    """
    actions = "/".join(word for word, _ in CANONICAL_DECISION_WORDS)
    priorities = "/".join(level for level, _ in PRIORITY_LEVELS)
    return (
        "\n【结构化决策头】\n"
        "在「### 操作建议」表格之后追加**一行**机器可读 JSON（仅一行，无需代码块）：\n"
        f'{STRUCTURED_HEADER_MARKER}{{"decisions":[{{"code":"600000","action":"减仓","priority":"高"}}]}}\n'
        f"action 仅可取值 {actions}；priority 仅可取值 {priorities}。\n"
        "code 必须是【持仓明细】中的 6 位数字代码。\n"
    )


def structured_header_cache_suffix() -> str:
    """结构化决策头的缓存指纹后缀（保障读写键同源）。

    开关关闭 → ``""``，缓存键与未追加决策头时逐字节一致（不误伤旧缓存、不因
    开关切换而强制全量重生成）；开启 → 固定后缀（提示词多了契约段，必须换键，
    否则会读到「提示词已改、缓存内容还是旧格式」的错配内容）。

    开关判定**收敛在此处**：写侧指纹闭包与 orchestrator 预检闭包都无条件调用
    本函数（对齐 ``prompts_signals._signal_digest_cache_suffix`` 的同源纪律），
    避免两侧各自读开关时漂移。
    """
    from src.python.config.features import is_feature_enabled

    return "_dh" if is_feature_enabled(STRUCTURED_HEADER_FLAG) else ""


def _extract_header_payload(text: str | None) -> str | None:
    """从文本中取出 ``决策头：`` 之后的 JSON 载荷。

    按**括号配对**截取（而非「首个 ``{`` 到末个 ``}``」）：模型偶尔在同一行写出
    多段内容，末个 ``}` 会跨段拼接成非法 JSON。配对扫描带字符串状态跟踪，引号内的
    花括号不计入深度。
    """
    if not text or STRUCTURED_HEADER_MARKER not in text:
        return None
    tail = text.split(STRUCTURED_HEADER_MARKER, 1)[1]
    line = (tail.splitlines() or [""])[0]
    start = line.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(line)):
        char = line[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return line[start : index + 1]
    return None


def parse_structured_header(text: str | None) -> list[dict[str, Any]] | None:
    """解析结构化决策头；不可用返回 ``None`` 交由确定性表格解析兜底。

    **逐字段归一校验**：``action`` 必须能经 :func:`parse_decision_word` 归一为
    方向（不做原样透传）、``code`` 必须 6 位数字形态。单条畸形只丢该条，不丢整批；
    整体不可解析（缺标记/非法 JSON/无有效条目）返回 None。

    Returns:
        ``[{code, direction, magnitude}, ...]``（与表格解析同形状，``magnitude``
        即优先级强度 high/mid/low）；不可用时 None。
    """
    payload = _extract_header_payload(text)
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        logger.info("[decision_header] 结构化决策头 JSON 解析失败，回落确定性表格解析")
        return None
    if not isinstance(data, dict):
        return None
    raw_items = data.get("decisions")
    if not isinstance(raw_items, list):
        return None
    rows: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = extract_code(item.get("code"))
        if code is None:
            continue
        direction = parse_decision_word(str(item.get("action") or ""), allow_scan=False)
        if direction is None:
            continue
        rows.append(
            {
                "code": code,
                "direction": direction,
                "magnitude": parse_priority(str(item.get("priority") or "")),
            }
        )
    return rows or None


__all__ = [
    "CANONICAL_DECISION_WORDS",
    "COMPOUND_PREFIX_CHARS",
    "DECISION_WORDS",
    "EXTENDED_DECISION_WORDS",
    "MAGNITUDE_RANK",
    "NEGATION_ADJACENT_CHARS",
    "NEGATION_PREFIXES",
    "PRIORITY_DEFAULT",
    "PRIORITY_LEVELS",
    "STRUCTURED_HEADER_FLAG",
    "STRUCTURED_HEADER_MARKER",
    "build_structured_header_instruction",
    "extract_code",
    "is_compound_fragment",
    "parse_decision_word",
    "parse_priority",
    "parse_structured_header",
    "strip_marks",
    "structured_header_cache_suffix",
]
