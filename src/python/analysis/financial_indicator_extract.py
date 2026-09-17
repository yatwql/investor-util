"""财务指标提取 —— 全文本财报（压平正文）→ `financial_indicator` 标准字段。

**纯解析层**：不取数、不缓存、不落盘。取数编排在
``fetcher/financial_indicator_adapters.py`` 的 ``datasink_indicator`` 适配器
（先经 ``fetcher/financial_report.py`` 取回「公司简介和主要财务指标」章节正文，
再交给本模块解析）。

## 上游形态（已对真实年报实测核实）

DataSinking 转换 Markdown 时**不保留表格结构**，指标行被压平为「标签紧连数字」的
段落，例如::

    ...营业收入86,241,940,222.2084,491,870,566.522.0778,143,535,736.10利润总额41,739...

因此解析采取**锚点 + 前若干数值**策略：定位标准指标名，取其后的第一、第二个数值
（本期、上年）。为守住「不猜」纪律，配套四道护栏：

  1. **锚点取标准披露行文**（如「归属于上市公司股东的净利润」），并对
     「扣除非经常性损益后的…」等易混行加否定环视，避免误取扣非口径；
  2. **窗口限定**：数值只在锚点后的有限窗口（``_WINDOW``）内取，超窗即判为
     下一行、弃用（防止跨行取数）；
  3. **按报告期精度选数值模式**：金额两位小数、每股收益四位小数、比率两位小数，
     避免「1.41011.3281」这类**无分隔连写**被误切；
  4. **逐字段合理性校验**：任一不通过即该字段取 ``None``（宁缺勿错）。

同比由本期/上年**同口径**两个数值算术派生（只做算术，不做口径推断）；无上年或
上年为 0 时取 ``None``。报告期与文种一律**由元数据给出**，不从正文猜。

## 覆盖面（诚实边界）

本模块只解析「主要会计数据和财务指标」类章节可提供的字段；毛利率/资产负债率/
每股净资产不在该章节内（需报表正文，且正文存在附注编号与数字粘连的误读风险），
故恒取 ``None``，交由主源 akshare 提供——见 :data:`PARSED_FIELDS`。
"""

from __future__ import annotations

import dataclasses
import logging
import math
import re
from dataclasses import dataclass

from src.python.schemas.datasource_fields import FinancialIndicatorFields

logger = logging.getLogger("invest")

#: 本解析层能够填出的标准字段（其余字段恒取 None，由主源提供）
PARSED_FIELDS: tuple[str, ...] = (
    "revenue",
    "net_profit",
    "revenue_yoy",
    "net_profit_yoy",
    "operating_cash_flow",
    "eps",
    "roe",
)

#: 需要同比派生的字段 → 同比字段名
_YOY_FIELDS: dict[str, str] = {
    "revenue": "revenue_yoy",
    "net_profit": "net_profit_yoy",
}

#: 金额单位声明 → 换算到「元」的倍数
_AMOUNT_SCALES: dict[str, float] = {"元": 1.0, "千元": 1e3, "万元": 1e4, "亿元": 1e8}

#: 单位声明的识别模式（取锚点前最近一处）
_UNIT_PATTERN = re.compile(r"单位[：:]\s*(亿元|千元|万元|元)")

#: 各口径数值的取值窗口（锚点后字符数）——超出即视为跨行，弃用
_WINDOW: dict[str, int] = {"amount": 72, "percent": 48, "per_share": 48}

#: 锚点与其后首个数值之间允许的最大间隔字符数（其间只允许单位/（元）等标注）
_MAX_GAP = 8

#: 数值模式链：按报告期精度优先，取不到时退化为次选（仅当首选一个都没取到）
_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "amount": (
        re.compile(r"-?\d[\d,]*\.\d{2}"),  # 两位小数 + 千分位
        re.compile(r"-?\d[\d,]*(?:\.\d+)?"),  # 无小数（退化为整数串）
    ),
    "percent": (re.compile(r"-?\d+\.\d{2}"),),  # 比率惯例两位小数
    "per_share": (
        re.compile(r"-?\d+\.\d{4}"),  # 每股收益惯例四位小数
        re.compile(r"-?\d+\.\d{2,4}"),  # 退化为 2~4 位
    ),
}


@dataclass(frozen=True)
class _IndicatorAnchor:
    """一个标准字段在压平正文中的定位规则。"""

    field: str
    label: str
    kind: str
    take: int = 2


#: 锚点表 —— 只登记「主要会计数据和财务指标」章节的标准行文。
#: 否定环视用于排除「扣除非经常性损益后的…」等同名易混行（其标准行在本行之后，
#: 首个匹配即所需，环视只是双保险）。
_ANCHORS: tuple[_IndicatorAnchor, ...] = (
    _IndicatorAnchor("revenue", r"(?:营业总收入|营业收入)", "amount"),
    _IndicatorAnchor("net_profit", r"归属于(?:上市公司|母公司)股东的净利润", "amount"),
    _IndicatorAnchor("operating_cash_flow", r"经营活动产生的现金流量净额", "amount"),
    _IndicatorAnchor("eps", r"(?<!损益后的)(?<!损益的)基本每股收益", "per_share"),
    _IndicatorAnchor("roe", r"(?<!损益后的)(?<!损益的)加权平均净资产收益率", "percent"),
)


def _to_float(token: str) -> float | None:
    """数值串 → float（去掉千分位逗号）；不可解析返回 None。"""
    try:
        return float(token.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _is_plausible(kind: str, value: float) -> bool:
    """取值合理性校验（金额=元、percent=百分数、ratio=小数比例、每股=元/股）。"""
    if not math.isfinite(value):
        return False
    if kind == "amount":
        return abs(value) < 1e15  # 千亿级以上的「金额」几可断定是误切
    if kind == "percent":
        return -100.0 <= value <= 100.0
    if kind == "ratio":
        return -10.0 <= value <= 10.0
    return abs(value) < 1e4


def _read_numbers(segment: str, kind: str, take: int) -> list[float]:
    """从锚点之后的正文片段读取前 ``take`` 个数值（按精度模式逐级尝试）。

    首选模式一个数值都取不到时才退化到次选模式；拿到部分即返回（不足由调用方
    判为取数失败），避免次选模式对「无分隔连写」二次误切。
    """
    for pattern in _PATTERNS[kind]:
        numbers: list[float] = []
        for match in pattern.finditer(segment):
            if not numbers and match.start() > _MAX_GAP:
                break  # 锚点后迟迟不出现数值 → 判为下一行
            value = _to_float(match.group())
            if value is None:
                continue
            numbers.append(value)
            if len(numbers) >= take:
                return numbers
        if numbers:
            return numbers
    return []


def _locate(text: str, anchor: _IndicatorAnchor) -> tuple[str, int] | None:
    """定位锚点，返回「锚点后的取值片段」与该锚点在全文中的起始位置。"""
    match = re.search(anchor.label, text)
    if match is None:
        return None
    return text[match.end() : match.end() + _WINDOW[anchor.kind]], match.start()


def _amount_scale(text: str, anchor_start: int) -> float | None:
    """取锚点前最近一处「单位：X」声明的金额换算倍数；无声明返回 None。

    **无声明即不产金额**（宁缺勿错）：缺失单位时金额口径不可知，宁可留空。
    """
    matches = list(_UNIT_PATTERN.finditer(text, 0, anchor_start))
    if not matches:
        return None
    return _AMOUNT_SCALES[matches[-1].group(1)]


def _yoy(current: float | None, prior: float | None) -> float | None:
    """同比 = (本期 - 上年) / |上年|，保留 4 位小数（对应披露的两位百分数）。"""
    if current is None or prior is None or abs(prior) < 1e-9:
        return None
    return round((current - prior) / abs(prior), 4)


def extract_indicators(
    content: str | None,
    *,
    code: str = "",
    symbol: str = "",
    report_period: str = "",
    doc_type: str = "",
) -> dict[str, object] | None:
    """从全文本财报章节正文提取标准指标记录（单报告期）。

    Args:
        content: 「主要会计数据和财务指标」类章节的压平正文
        code: 6 位证券代码
        symbol: FMP 风格符号
        report_period: 报告期（``YYYY-MM-DD``，由元数据给出）
        doc_type: 文种（``annual`` / ``semiannual`` / …，由元数据给出）

    Returns:
        全部标准字段构成的 dict（未解析到的字段取 ``None``）；
        正文为空或**一个字段都未解析到**时返回 None（调用方按无覆盖降级）
    """
    text = content or ""
    if not text.strip():
        return None

    values: dict[str, float | None] = {}
    for anchor in _ANCHORS:
        located = _locate(text, anchor)
        if located is None:
            continue
        segment, anchor_start = located
        numbers = _read_numbers(segment, anchor.kind, anchor.take)
        if not numbers or not _is_plausible(anchor.kind, numbers[0]):
            continue

        scale = 1.0
        if anchor.kind == "amount":
            scale = _amount_scale(text, anchor_start)
            if scale is None:
                logger.warning("[fin_indicator_extract] 未找到金额单位声明，金额字段留空（code=%s）", code)
                continue

        current = numbers[0] * scale
        prior = numbers[1] * scale if len(numbers) >= 2 and _is_plausible(anchor.kind, numbers[1]) else None
        if anchor.kind == "percent":
            current, prior = current / 100.0, (prior / 100.0 if prior is not None else None)
            if not _is_plausible("ratio", current) or (prior is not None and not _is_plausible("ratio", prior)):
                continue

        values[anchor.field] = round(current, 6)
        yoy_field = _YOY_FIELDS.get(anchor.field)
        if yoy_field is not None:
            values[yoy_field] = _yoy(current, prior)

    if not values:
        return None

    record = dataclasses.asdict(
        FinancialIndicatorFields(code=code, symbol=symbol, report_period=report_period, doc_type=doc_type)
    )
    record.update(values)
    return record
