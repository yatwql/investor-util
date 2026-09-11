"""基金持仓报告期的时效判定。

基金持仓是定期报告的静态快照：接口返回的报告期是数据所属的报告期末，
与调用时点天然相隔一段披露延迟。当接口回退到「不指定年份」的默认请求时
（部分基金仅有早期报告），报告期可能已在数年前——此时持仓比例反映的是
当时的配置，与当期实际配置可能严重脱节。

报告期此前只被记入日志，没有任何消费者读取。本模块提供统一口径：
以「报告期之后已走完的完整季度数」度量陈旧程度，达到阈值即判定为不可采信，
由调用方按既有「持仓不可用」路径处理，并在报告中标注原因与原始报告期。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

STALE_QUARTERS = 2
"""判定陈旧的完整季度数阈值。

取舍：定期报告本身存在披露滞后（法定不晚于报告期结束后 15 个工作日，
QDII 因境外市场休市与结算安排常更晚）。阈值取 1 会把仍在正常披露节奏内的
持仓误判为陈旧；取 4（约一年）又放过了与当期配置明显脱节的快照。
2 个完整季度（约 6~9 个月）既容纳披露延迟，又拦得住跨年的陈年报告。
"""

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y年%m月%d日")
_QUARTER_END_DAYS = ((3, 31), (6, 30), (9, 30), (12, 31))


def parse_report_date(raw: object) -> date | None:
    """解析持仓接口返回的报告期。

    接口报告期不保证格式统一（基金主页面与季报接口各有解析规则），
    无法解析时返回 None——宁可放弃时效判定，也不因格式差异误判为陈旧。
    """
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _quarter_index(day: date) -> int:
    """day 所在季度在日历上的序号（每季度 +1）。

    以序号相减代替逐季度遍历，跨年、跨十年都无需特判。
    """
    return day.year * 4 + (day.month - 1) // 3


def _last_completed_quarter_index(today: date) -> int:
    """截至 today 已走完的最后一个季度序号。

    当天恰为季末（3/31、6/30、9/30、12/31）时当季即算走完，
    否则当季尚未结束、不计入。
    """
    index = _quarter_index(today)
    if (today.month, today.day) != _QUARTER_END_DAYS[index % 4]:
        index -= 1
    return index


def complete_quarters_since(report: date, today: date) -> int:
    """报告期之后、截至 today 已走完的完整季度数。"""
    return max(0, _last_completed_quarter_index(today) - _quarter_index(report))


def is_stale_report(report: date | None, today: date | None = None) -> bool:
    """报告期是否陈旧到不可采信。

    报告期缺失或无法解析时不判陈旧：那属于「数据缺失」，由既有的获取失败
    降级路径处理，与本闸门不是一回事，混在一起会掩盖真正的失败原因。
    """
    if report is None:
        return False
    return complete_quarters_since(report, today or date.today()) >= STALE_QUARTERS


def format_report_period(raw: object) -> str:
    """规范化为展示用报告期文本；无法解析时原样返回，空值显示「未知」。"""
    parsed = parse_report_date(raw)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d")
    text = str(raw or "").strip()
    return text or "未知"


@dataclass(frozen=True)
class ReportPeriodInfo:
    """一次报告期判定的完整结果（展示文本 + 时效度量）。

    各报告层消费者（穿透 / 重合度 / 集中度 / 风格 / 候选比较）共用同一判定，
    避免「展示用文本」与「陈旧判定」两处口径各自演化——判据复制即漂移温床。
    """

    period: str
    """展示用报告期文本（无法解析时原样返回，空值「未知」）。"""

    quarters: int
    """报告期之后已走完的完整季度数（无法解析时为 0）。"""

    stale: bool
    """是否陈旧到不可采信（口径见 :func:`is_stale_report`）。"""


def evaluate_report_period(raw: object, today: date | None = None) -> ReportPeriodInfo:
    """一次调用得出报告期的展示文本与时效判定。

    Args:
        raw: 持仓接口返回的报告期原文（``fetch_fund_holdings`` 的 ``date`` 字段）。
        today: 判定基准日，默认当天（测试可注入固定日期）。

    Returns:
        判定结果；报告期缺失或无法解析时 ``stale`` 为 False、``quarters`` 为 0。
    """
    day = today or date.today()
    parsed = parse_report_date(raw)
    return ReportPeriodInfo(
        period=format_report_period(raw),
        quarters=complete_quarters_since(parsed, day) if parsed is not None else 0,
        stale=is_stale_report(parsed, day),
    )


def fund_period_label(name: str, info: ReportPeriodInfo) -> str:
    """基金持仓在报告中的标准报告期标注（名称 + 报告期 + 已过季度数）。

    各消费者的标注措辞须一致——同一只基金在重合度、集中度、风格、候选比较
    中若各写各的报告期文字，读者会以为是不同口径下的两件事。
    """
    return f"{name}（报告期 {info.period}，已过 {info.quarters} 个完整季度）"
