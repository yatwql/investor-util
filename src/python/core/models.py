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
        data_status: 本地可判定的品种数据状态（如 "bad_code_format"），
            空字符串表示格式正常、待行情数据进一步标注（品种级覆盖诊断）。
    """

    account: str
    name: str
    code: str
    shares: float
    cost_price: float
    data_status: str = ""
