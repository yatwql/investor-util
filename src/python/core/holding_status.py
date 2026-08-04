"""品种级数据状态标注 — 数据质量仪表盘「品种覆盖」区块的数据源。

对 `read_holdings` 解析出的每个品种标注数据状态，让「数据缺失」
从静默容错变成显式诊断。状态由两类信号合成：
  1. 本地信号（无需网络）：代码格式校验、名称比对
  2. 数据信号（复用行情/净值接口返回状态）：行情/净值是否取到

状态枚举（语义名，禁用任务代号）：
  ok                  有行情（正常）
  nav_missing         净值缺失（基金无净值）
  possibly_delisted   可能退市（股票无有效行情/长期停牌）
  bad_code_format     代码格式可疑
  name_mismatch       名称不匹配

判定优先级（取最先命中的单一状态）：
  代码格式可疑 > 数据缺失（净值缺失/可能退市）> 名称不匹配 > 有行情

消费方：
  `report/orchestrator.prepare_report_data()` 组装为 `position_status`
  数据契约注入 pipeline_data，供「数据质量仪表盘」品种覆盖区块渲染。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.code_utils import is_fund_holding

logger = logging.getLogger("invest")

# ── 状态常量 ────────────────────────────────────────────────

STATUS_OK = "ok"
STATUS_NAV_MISSING = "nav_missing"
STATUS_POSSIBLY_DELISTED = "possibly_delisted"
STATUS_BAD_CODE_FORMAT = "bad_code_format"
STATUS_NAME_MISMATCH = "name_mismatch"

# 展示文案（语义名即状态名，避免任务代号扩散到 UI）
STATUS_LABELS: dict[str, str] = {
    STATUS_OK: "有行情",
    STATUS_NAV_MISSING: "净值缺失",
    STATUS_POSSIBLY_DELISTED: "可能退市",
    STATUS_BAD_CODE_FORMAT: "代码格式可疑",
    STATUS_NAME_MISMATCH: "名称不匹配",
}

STATUS_REASONS: dict[str, str] = {
    STATUS_OK: "行情/净值数据正常",
    STATUS_NAV_MISSING: "基金未取到有效净值，收益/市值可能为空",
    STATUS_POSSIBLY_DELISTED: "未取到有效行情（可能退市/长期停牌），请人工核对",
    STATUS_BAD_CODE_FORMAT: "代码格式异常，无法路由到数据源",
    STATUS_NAME_MISMATCH: "持仓名称与数据源名称不一致，请确认代码是否正确",
}

# 需要报告提示的异常状态集合（有行情不计入）
_ABNORMAL_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_NAV_MISSING,
        STATUS_POSSIBLY_DELISTED,
        STATUS_BAD_CODE_FORMAT,
        STATUS_NAME_MISMATCH,
    }
)


# ── 本地信号：代码格式校验 ──────────────────────────────────


def classify_code_format(code: str | None) -> str:
    """校验证券代码格式，返回 ``STATUS_OK`` 或 ``STATUS_BAD_CODE_FORMAT``。

    合法格式（去除 sh/sz/bj 交易所前缀后）：
      - 6 位纯数字（A 股 / 场内基金 / 场外基金 / 其他 6 位证券）
      - 5 位纯数字（港股通，如 ``00700``）

    兼容 Excel 浮点假象：``"600900.0"`` 归一为 ``"600900"`` 判合法，
    避免用户在 Excel 中把代码单元格格式化为数值导致的误报。

    Args:
        code: 证券代码（可含 sh/sz/bj 前缀；可为 None/空串）

    Returns:
        ``STATUS_OK`` 或 ``STATUS_BAD_CODE_FORMAT``
    """
    raw = (code or "").strip()
    lower = raw.lower()
    if lower.startswith(("sh", "sz", "bj")):
        raw = raw[2:]
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if raw.isdigit() and len(raw) in (5, 6):
        return STATUS_OK
    return STATUS_BAD_CODE_FORMAT


# ── 本地信号：名称比对 ──────────────────────────────────────


def normalize_name(name: str | None) -> str:
    """规范化证券名称用于比对：去所有空白并转小写。

    Args:
        name: 证券名称

    Returns:
        规范化后的名称（空输入返回空串）
    """
    return "".join((name or "").split()).lower()


def names_match(holding_name: str | None, market_name: str | None) -> bool:
    """判断持仓名称与数据源名称是否匹配（容忍简称/后缀差异）。

    匹配规则（任一侧为空视为不可比，不判不匹配）：
      1. 规范化后完全相同；
      2. 短名（≥2 字符）为长名的子串——容忍「茅台 ⊆ 贵州茅台」等两字简称，
         以及「易方达蓝筹精选 ⊆ 易方达蓝筹精选混合」等后缀差异。

    说明：子串匹配 ≥2 字符是有意放宽，优先避免对合法简称误报；
    真实「代码填错导致名称不符」通常是名称完全不同（无公共子串），
    仍会被准确标出。

    Args:
        holding_name: 持仓文件中的名称
        market_name: 数据源返回的该代码实际名称

    Returns:
        True 表示匹配（或不可比）；False 表示名称不匹配
    """
    a = normalize_name(holding_name)
    b = normalize_name(market_name)
    if not a or not b:
        return True
    if a == b:
        return True
    if len(a) >= 2 and a in b:
        return True
    if len(b) >= 2 and b in a:
        return True
    return False


# ── 数据信号：行情明细读取 ──────────────────────────────────


def _detail_value(detail: Any, field: str, default: Any = None) -> Any:
    """从行情明细读取字段（兼容 dict 或含属性对象，如 DetailRow）。

    Args:
        detail: 单条行情明细；None 时返回 default
        field: 字段名（如 "code"/"name"/"price"/"price_type"）
        default: 缺失时的默认值

    Returns:
        字段值
    """
    if detail is None:
        return default
    if isinstance(detail, dict):
        return detail.get(field, default)
    return getattr(detail, field, default)


def _has_effective_quote(detail: Any) -> bool:
    """判断该品种是否取到有效行情。

    行情明细缺失、price 缺失/≤0、或 price_type 明确「暂无行情」，
    均视为未取到有效行情。

    Args:
        detail: 单条行情明细（可为 None）

    Returns:
        True 表示有有效行情
    """
    if detail is None:
        return False
    price = _detail_value(detail, "price", 0.0)
    if price is None or price <= 0:
        return False
    price_type = _detail_value(detail, "price_type", "") or ""
    if price_type == "暂无行情":
        return False
    return True


# ── 单品种状态判定 ─────────────────────────────────────────


def _status_for_holding(holding: Any, detail: Any) -> str:
    """判定单品种数据状态（优先级见模块 docstring）。

    Args:
        holding: Holding 对象（含 name/code/account）
        detail: 该代码的行情明细（可为 None）

    Returns:
        状态常量之一
    """
    code = (holding.code or "").strip()
    if classify_code_format(code) != STATUS_OK:
        return STATUS_BAD_CODE_FORMAT

    if not _has_effective_quote(detail):
        if is_fund_holding(holding.name, code, holding.account):
            return STATUS_NAV_MISSING
        return STATUS_POSSIBLY_DELISTED

    market_name = _detail_value(detail, "name", "") or ""
    if not names_match(holding.name, market_name):
        return STATUS_NAME_MISMATCH
    return STATUS_OK


# ── 对外主入口 ──────────────────────────────────────────────


def annotate_position_status(holdings: list, details: list | None = None) -> list[dict]:
    """逐品种标注数据状态，产出品种状态清单。

    Args:
        holdings: Holding 列表
        details: 行情明细列表（DetailRow 或同结构对象）；可为 None

    Returns:
        品种状态清单，每项：:
            {"code", "name", "account", "status", "status_label", "reason"}
    """
    detail_map: dict[str, Any] = {}
    for d in details or []:
        code = _detail_value(d, "code", "") or ""
        if code:
            detail_map.setdefault(code, d)

    items: list[dict] = []
    for h in holdings:
        st = _status_for_holding(h, detail_map.get((h.code or "").strip()))
        items.append(
            {
                "code": h.code,
                "name": h.name,
                "account": h.account,
                "status": st,
                "status_label": STATUS_LABELS.get(st, st),
                "reason": STATUS_REASONS.get(st, ""),
            }
        )
    return items


def build_coverage_summary(holdings: list, details: list | None = None) -> dict:
    """构建品种覆盖诊断数据契约（`position_status` 键结构）。

    Args:
        holdings: Holding 列表
        details: 行情明细列表（可为 None）

    Returns:
        契约 dict：::
            {"available": bool, "items": list[dict], "abnormal_count": int,
             "summary": str}
    """
    items = annotate_position_status(holdings, details)
    abnormal = [i for i in items if i["status"] in _ABNORMAL_STATUSES]
    if items:
        summary = f"{len(items)} 个品种，{len(abnormal)} 个数据异常"
    else:
        summary = "无持仓品种"
    return {
        "available": bool(holdings),
        "items": items,
        "abnormal_count": len(abnormal),
        "summary": summary,
    }
