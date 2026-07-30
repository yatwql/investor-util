from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Holding:
    """单条持仓记录。

    Attributes:
        account:    账户名称（Excel 工作表名）
        name:       证券名称（股票名称 / 基金名称）
        code:       证券代码（字符串，保持原始格式，如 "600900"）
        shares:     持有份额 / 股数
        cost_price: 每份成本价
    """

    account: str
    name: str
    code: str
    shares: float
    cost_price: float
