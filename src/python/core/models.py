from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass
class TradeRecord:
    """单笔交易流水记录（持仓 Excel「交易流水」页签）。

    Attributes:
        date:    成交日期（YYYY-MM-DD）
        code:    证券代码
        action:  操作方向（buy=买入 / sell=卖出，解析时归一化）
        shares:  成交份额 / 股数
        price:   成交价格（每份/每股）
        fee:     交易费用（可选，默认 0；页签缺省费用列时不解析）
        account: 账户名（页签名，可选）
    """

    date: str
    code: str
    action: str
    shares: float
    price: float
    fee: float = 0.0
    account: str = ""


@dataclass
class DividendRecord:
    """单笔分红流水记录（持仓 Excel「分红流水」页签）。

    Attributes:
        date:    除权 / 到账日期（YYYY-MM-DD）
        code:    证券代码
        amount:  每份现金分红金额
        shares:  登记日持有份额（可选，0 表示未知——计算总额时回退当前持仓份额）
        account: 账户名（页签名，可选）
    """

    date: str
    code: str
    amount: float
    shares: float = 0.0
    account: str = ""


@dataclass
class HoldingsFile:
    """持仓文件完整解析结果（主表 + 可选流水页签）。

    Attributes:
        holdings:     主表持仓记录（与 read_holdings 返回一致）
        transactions: 交易流水记录（「交易流水」页签，无则空列表）
        dividends:    分红流水记录（「分红流水」页签，无则空列表）
    """

    holdings: list[Holding]
    transactions: list[TradeRecord] = field(default_factory=list)
    dividends: list[DividendRecord] = field(default_factory=list)
