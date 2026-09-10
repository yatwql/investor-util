"""数据源标准字段契约 — 各数据域的规范化字段定义（唯一事实来源）。

与 ``providers/*`` 的关系：provider 负责「拿到上游原始响应」，本模块定义
「本项目统一字段长什么样」。字段集在此**可执行地**声明为 frozen dataclass，
而非散落在各转换函数的 ``dict`` 字面量里——新增数据源时字段名写错会在
契约自检与单元测试期报错，而不是运行期静默丢字段。

设计要点：

- 记录类即契约：``dataclass`` 的字段名就是标准字段名（由
  ``fetcher/source_adapter.py`` 反射得到，不存在第二份手抄清单）。
- 数值字段由类型注解区分：``float`` = 必有数值（缺失取 0.0），
  ``float | None`` = 可缺（缺失取 ``None``，表示「该源不提供此字段」）。
  ``str`` 字段缺失取空串。该规则与既有手写转换函数的取值语义一一对应。
- ``to_dict()`` 输出**全部**标准字段：同一域的不同源产出同键同构的 dict，
  下游无需为「某源少两个键」写分支。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ═══════════════════════════════════════════════════════════════
#  行情域（price/nav）
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class QuoteFields:
    """行情域标准字段 —— 个股/ETF 实时价与场外基金净值共用的统一格式。

    场外基金净值以「净值即价格」的换算接入（``nav → price``），使下游
    行情消费方无需区分「场内价格」与「场外净值」。

    Attributes:
        name: 证券名称（上游提供，用于代码重叠时的名称校验）
        code: 6 位证券代码
        price: 最新价（场外基金为最新单位净值）
        yesterday_close: 昨日收盘价（场外基金为昨日净值）
        price_date: 价格/净值日期（YYYY-MM-DD）
        source_api: 数据源标识（tencent/sina/eastmoney）
        source: 数据源展示名（腾讯财经/新浪财经/东方财富）
        market_cap: 总市值（单位：亿元；不提供该字段的源为 None）
        pe: 市盈率（不提供该字段的源为 None）
    """

    name: str = ""
    code: str = ""
    price: float = 0.0
    yesterday_close: float = 0.0
    price_date: str = ""
    source_api: str = ""
    source: str = ""
    market_cap: float | None = None
    pe: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为标准字段 dict（全部字段均出现，字段序与声明序一致）。"""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
#  域注册
# ═══════════════════════════════════════════════════════════════


DOMAIN_QUOTE = "quote"

# 数据域 → 标准字段记录类（新增域时在此登记，契约自检据此校验适配器）
DOMAIN_RECORDS: dict[str, type] = {
    DOMAIN_QUOTE: QuoteFields,
}
