"""提示词信号预消化模块 — 数值进 LLM 前预消化为带方向标注的一句话信号。

职责：把**算法已经算出、但此前只走渲染层**的确定性结论（行业资金流向方向、
市场温度档位、持仓估值分位、尾部风险幅度）在进入提示词之前，用确定性规则
写成一到多行「结论行」，让模型读到方向判断而非裸数值自行解读。

典型缺口：行业资金流向原先拼成「主力净流入-5,000,000」——label 固定但数值
带负号，方向只能靠读者自行推断符号含义；且数据源未排序，截取的前 5 行没有
任何排名语义。本模块统一以「主力净流入/主力净流出 + 非负量」表达方向。

设计约束：

- **纯计算层**：无网络、无文件、无 LLM 调用；同输入必得同输出（缓存指纹后缀
  依赖该确定性）。唯一的外部读数是 ``_signal_digest_cache_suffix`` 中的开关判定，
  它被刻意收敛为开关的**唯一**读取点以保证读写键同源。
- **词表集中**：方向词/风险词/信号前缀均为模块常量，供下游解析器复用，
  避免中文结论词散落在各 prompt 构建函数里。
- **只读既有数据契约**：算法评级取自 ``pipeline_data`` 既有键
  （``market_temperature_data`` / ``valuation_data`` / ``tail_risk_data``），
  本模块不写入 pipeline_data、不新增键（附录 H 数据契约不变）。
- **不注入即无感**：数据不可用（``available=False``）或缺档位时返回空串，
  调用方据此跳过拼接，提示词与未启用时逐字节一致。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from src.python.llm.fingerprint import compute_fingerprint
from src.python.llm.prompts_core import _fmt_wan

logger = logging.getLogger("invest")

__all__ = [
    "SIGNAL_PREFIX",
    "SIGNAL_BULLISH",
    "SIGNAL_BEARISH",
    "SIGNAL_NEUTRAL",
    "SIGNAL_RISK_HIGH",
    "SIGNAL_RISK_MEDIUM",
    "SIGNAL_RISK_LOW",
    "SECTOR_FLOW_TOP_N",
    "TAIL_RISK_VAR95_HIGH",
    "TAIL_RISK_VAR95_MEDIUM",
    "_is_number",
    "_flow_verdict",
    "_format_signal",
    "_fmt_amount",
    "_sector_flow_lines",
    "_build_sector_flow_block",
    "_build_signal_digest_block",
    "_signal_digest_cache_suffix",
]

# ═══════════════════════════════════════════════════════════════
#  信号词表与格式（下游解析器的唯一基准）
# ═══════════════════════════════════════════════════════════════

#: 信号行前缀。固定且唯一，供下游解析器按行首匹配（中英混排会引入词边界坑，
#: 故全中文，与项目其余提示词口径一致）。
SIGNAL_PREFIX = "信号："

#: 方向词（看多/看空/中性轴）：资金流向、估值分位这类有明确好淡方向的指标用。
SIGNAL_BULLISH = "看多"
SIGNAL_BEARISH = "看空"
SIGNAL_NEUTRAL = "中性"

#: 风险词（风险高/中/低轴）：尾部风险这类只有幅度、没有好淡方向的指标用——
#: 强行套「看空」会把「波动大」误述成「看跌」，方向与幅度是两个正交维度。
SIGNAL_RISK_HIGH = "风险高"
SIGNAL_RISK_MEDIUM = "风险中"
SIGNAL_RISK_LOW = "风险低"

#: 行业资金流向每个方向展示的行业数（净流入前 N / 净流出前 N）。
SECTOR_FLOW_TOP_N = 3

#: 尾部风险分档阈值（VaR95 单日损失幅度，%）。启发式标定：单日 95% 分位损失
#: 3% 对混合型组合已属显著。原始数值同行给出，模型可自行判读，阈值只决定档位词。
TAIL_RISK_VAR95_HIGH = 3.0
TAIL_RISK_VAR95_MEDIUM = 1.5

_FLOW_WORD_BY_VERDICT = {
    SIGNAL_BULLISH: "主力净流入",
    SIGNAL_BEARISH: "主力净流出",
    SIGNAL_NEUTRAL: "主力净流入",
}

_SECTOR_FLOW_HEADER = "【行业资金流向】"
_SECTOR_FLOW_INFLOW_TITLE = "净流入前列："
_SECTOR_FLOW_OUTFLOW_TITLE = "净流出前列："

_DIGEST_HEADER = "【确定性信号】"
_DIGEST_NOTE = "（算法预判，供参考，非投资建议）"


# ═══════════════════════════════════════════════════════════════
#  基础判定与格式化
# ═══════════════════════════════════════════════════════════════


def _is_number(value: Any) -> bool:
    """可用数值判定：排除 bool 与 NaN/±inf。

    bool 是 int 的子类（``True`` 会被当成 1 元）；NaN/±inf 格式化后是 ``nan``/``inf``
    这类文字，进提示词比裸数值更糟——两者都按「无此字段」处理，交由降级路径。
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _flow_verdict(net_amount: Any) -> str:
    """主力净额 → 方向词。

    Args:
        net_amount: 主力净额（元）；非可用数值（None/bool/非有限值）视为无方向。

    Returns:
        ``SIGNAL_BULLISH``（净流入）/ ``SIGNAL_BEARISH``（净流出）/ ``SIGNAL_NEUTRAL``。
    """
    if not _is_number(net_amount):
        return SIGNAL_NEUTRAL
    if net_amount > 0:
        return SIGNAL_BULLISH
    if net_amount < 0:
        return SIGNAL_BEARISH
    return SIGNAL_NEUTRAL


def _format_signal(label: str, verdict: str, detail: str = "") -> str:
    """格式化单条信号行：``信号：{指标} {结论}（{依据}）``。

    Args:
        label: 指标名（如 "市场温度（沪深300）"）。
        verdict: 词表内的方向词或风险词。
        detail: 括号内依据；为空时省略括号。
    """
    if detail:
        return f"{SIGNAL_PREFIX}{label} {verdict}（{detail}）"
    return f"{SIGNAL_PREFIX}{label} {verdict}"


def _fmt_amount(num: float) -> str:
    """金额格式化：沿用 万/亿 单位，未达万级时补「元」防止裸数字无单位。"""
    text = _fmt_wan(num)
    return text if text.endswith(("万", "亿")) else f"{text}元"


def _sector_flow_lines(rows: list[dict]) -> list[str]:
    """把同一方向的行业行格式化为展示行：方向由词承担，金额取绝对值。

    金额取绝对值 + 方向词表达符号，是「主力净流入-5,000,000」的替代方案——
    方向与数值不再互相矛盾，模型无需推断符号语义。
    净占比保留正负号：它是比率而非金额，且同行已有方向词可对照。
    """
    lines: list[str] = []
    for _s in rows:
        _net = _s.get("main_net_inflow")
        _word = _FLOW_WORD_BY_VERDICT[_flow_verdict(_net)]
        _parts = [str(_s.get("name", ""))]
        _chg = _s.get("change_pct")
        if _is_number(_chg):
            _parts.append(f"涨跌{_chg:+.2f}%")
        if _is_number(_net):
            _parts.append(f"{_word}{_fmt_amount(abs(_net))}")
        _net_pct = _s.get("main_net_inflow_pct")
        if _is_number(_net_pct):
            _parts.append(f"净占比{_net_pct:+.2f}%")
        lines.append("  ".join(_parts))
    return lines


def _build_sector_flow_block(sector_flow: list[dict] | None) -> str:
    """构建行业资金流向文本块（按主力净额分方向排名）。

    数据源返回顺序无排名语义，故先按主力净额排序再截取：净流入降序取前
    ``SECTOR_FLOW_TOP_N`` 个、净流出升序取前 ``SECTOR_FLOW_TOP_N`` 个。分方向
    展示（而非合成一张榜）是为了在全市场净流出日仍能看到最弱行业——只取净额
    降序前 N 会退化成「回撤最小的 N 个行业」，恰好丢掉风险侧信号。

    Args:
        sector_flow: ``get_sector_fund_flow()`` 输出，每项含
            name/change_pct/main_net_inflow/main_net_inflow_pct。

    Returns:
        格式化的文本块；空输入或无有效净额时退回原始顺序前 N 行。
    """
    rows = [r for r in (sector_flow or []) if isinstance(r, dict)]
    if not rows:
        return ""

    def _net(row: dict) -> float:
        _v = row.get("main_net_inflow")
        return float(_v) if _is_number(_v) else 0.0

    inflows: list[dict] = []
    outflows: list[dict] = []
    for _row in rows:
        _verdict = _flow_verdict(_row.get("main_net_inflow"))
        if _verdict == SIGNAL_BULLISH:
            inflows.append(_row)
        elif _verdict == SIGNAL_BEARISH:
            outflows.append(_row)
    inflows.sort(key=_net, reverse=True)
    outflows.sort(key=_net)

    lines: list[str] = []
    if inflows:
        lines.append(_SECTOR_FLOW_INFLOW_TITLE)
        lines.extend(_sector_flow_lines(inflows[:SECTOR_FLOW_TOP_N]))
    if outflows:
        lines.append(_SECTOR_FLOW_OUTFLOW_TITLE)
        lines.extend(_sector_flow_lines(outflows[:SECTOR_FLOW_TOP_N]))
    if not lines:
        # 全市场净额为 0 / 缺失：无方向可分，退回原始顺序前 N 行
        lines = _sector_flow_lines(rows[:SECTOR_FLOW_TOP_N])
    return "\n" + _SECTOR_FLOW_HEADER + "\n" + "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  算法评级信号（只读既有 pipeline_data 数据契约）
# ═══════════════════════════════════════════════════════════════


def _temperature_signal(pipeline_data: dict) -> str | None:
    """市场温度档位 → 信号行（低估=看多 / 合理=中性 / 高估=看空）。"""
    from src.python.analysis.market_temperature import (
        TIER_OVERVALUED,
        TIER_UNDERVALUED,
    )

    data = pipeline_data.get("market_temperature_data")
    if not isinstance(data, dict) or not data.get("available"):
        return None
    tier = data.get("tier")
    if not tier:
        return None
    verdict = {
        TIER_UNDERVALUED: SIGNAL_BULLISH,
        TIER_OVERVALUED: SIGNAL_BEARISH,
    }.get(tier, SIGNAL_NEUTRAL)
    score = data.get("score")
    detail = f"{tier}，温度分 {score:.1f}" if _is_number(score) else tier
    index_name = data.get("index_name") or "基准指数"
    return _format_signal(f"市场温度（{index_name}）", verdict, detail)


def _valuation_signal(pipeline_data: dict) -> str | None:
    """持仓估值分位档位分布 → 信号行（低估多于高估=看多，反之看空）。

    逐只持仓的档位对模型是噪声，聚合成「几只低估 / 几只合理 / 几只高估」
    的分布更有信息量；档位数并列时判为中性，不硬造方向。
    """
    from src.python.analysis.valuation_percentile import (
        TIER_FAIR,
        TIER_OVERVALUED,
        TIER_UNDERVALUED,
    )

    data = pipeline_data.get("valuation_data")
    if not isinstance(data, dict) or not data.get("available"):
        return None
    by_code = data.get("by_code")
    if not isinstance(by_code, dict) or not by_code:
        return None

    counts = {TIER_UNDERVALUED: 0, TIER_FAIR: 0, TIER_OVERVALUED: 0}
    for _entry in by_code.values():
        if not isinstance(_entry, dict):
            continue
        _tier = _entry.get("tier")
        if _tier in counts:
            counts[_tier] += 1
    if sum(counts.values()) <= 0:
        return None

    low, high = counts[TIER_UNDERVALUED], counts[TIER_OVERVALUED]
    if low > high:
        verdict = SIGNAL_BULLISH
    elif high > low:
        verdict = SIGNAL_BEARISH
    else:
        verdict = SIGNAL_NEUTRAL
    detail = "、".join(f"{t}{n}只" for t, n in counts.items() if n > 0)
    return _format_signal("持仓估值分位", verdict, detail)


def _tail_risk_signal(pipeline_data: dict) -> str | None:
    """尾部风险幅度 → 信号行（风险高/中/低，非看多看空）。"""
    data = pipeline_data.get("tail_risk_data")
    if not isinstance(data, dict) or not data.get("available"):
        return None
    var95 = data.get("var95")
    if not _is_number(var95):
        return None
    if var95 >= TAIL_RISK_VAR95_HIGH:
        verdict = SIGNAL_RISK_HIGH
    elif var95 >= TAIL_RISK_VAR95_MEDIUM:
        verdict = SIGNAL_RISK_MEDIUM
    else:
        verdict = SIGNAL_RISK_LOW

    parts = [f"VaR95 {var95:.2f}%"]
    drop = data.get("max_single_day_drop")
    if _is_number(drop):
        parts.append(f"最大单日跌幅 {drop:.2f}%")
    days = data.get("consecutive_down_days")
    if _is_number(days) and days > 0:
        parts.append(f"最长连跌 {int(days)} 日")
    return _format_signal("尾部风险", verdict, "，".join(parts))


def _build_signal_digest_block(pipeline_data: dict | None) -> str:
    """构建【确定性信号】文本块（算法评级预消化）。

    三路信号各自独立取用：缺键、``available`` 为假、档位缺失都只是跳过该项，
    不阻断其余信号，也不报错（数据降级已在数据源侧披露，此处不重复告警）。

    Args:
        pipeline_data: 报告管线数据契约。

    Returns:
        文本块；无任一可用信号时返回空串（调用方据此跳过注入）。
    """
    if not isinstance(pipeline_data, dict):
        return ""
    lines = [
        _line
        for _line in (
            _temperature_signal(pipeline_data),
            _valuation_signal(pipeline_data),
            _tail_risk_signal(pipeline_data),
        )
        if _line
    ]
    if not lines:
        logger.debug("信号预消化：pipeline_data 中无可用算法评级信号，跳过注入")
        return ""
    return "\n".join([_DIGEST_HEADER + _DIGEST_NOTE, *lines])


def _signal_digest_cache_suffix(pipeline_data: dict | None) -> str:
    """信号块的缓存指纹后缀（保障读写键同源）。

    开关关闭或块为空 → ``""``，缓存键与未注入信号时逐字节一致（不误伤旧缓存、
    不因开关切换而强制全量重生成）；注入时取块内容指纹——信号数值变化即换键，
    避免「提示词已带新信号、缓存内容还是旧信号」的错配。

    开关判定**收敛在此处**：写侧指纹闭包与 orchestrator 预检闭包都无条件调用本
    函数（对齐 ``decision_ledger.lessons_cache_suffix()`` 的同源纪律），避免两侧
    各自读开关时漂移。

    Args:
        pipeline_data: 报告管线数据契约。
    """
    from src.python.config.features import is_feature_enabled

    if not is_feature_enabled("signal_pre_digest"):
        return ""
    block = _build_signal_digest_block(pipeline_data)
    if not block:
        return ""
    return "_" + compute_fingerprint(block)
