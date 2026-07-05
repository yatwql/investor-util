"""持仓分类工具函数 — 统一的资产类型判定逻辑（全代码库唯一入口）。

集中管理证券类型判定函数，避免逻辑分散各处导致定义不一致。
所有模块应通过此模块进行股票/ETF/债券/QDII/场外基金等判定。
"""

from __future__ import annotations

# ── 常量 ──────────────────────────────────────────

# 场外基金账户关键词
FUND_ACCOUNT_KEYWORDS = ("基金", "支付宝", "微信", "银行")

# 固收类关键词（宽松版 — 含单字"债"，用于持仓分类广度匹配）
BOND_KEYWORDS = ("债", "纯债", "短债", "中短债", "利率债", "信用债", "债券")

# 固收类关键词（严格版 — 不含单字"债"，用于穿透分析等需排除可转债的场景）
BOND_KEYWORDS_STRICT = ("纯债", "短债", "中短债", "利率债", "信用债", "债券")

# 指数类关键词（用于场外被动基金判定）
INDEX_KEYWORDS = ("指数", "ETF联接", "ETF 联接", "中证", "沪深300",
                  "中证500", "中证1000", "科创50", "创业板", "上证")

# 隐式 QDII 关键词（名称不含"QDII"但实际投资海外市场的基金）
_OVERSEA_KW = ("纳斯达克", "标普", "纳指", "道琼斯", "日经")


# ── 判定函数 ──────────────────────────────────────


def is_stock_code(code: str) -> bool:
    """A 股股票代码特征：以 6/0/3 开头。

    Args:
        code: 证券代码

    Returns:
        True 表示符合 A 股股票代码格式
    """
    return code.startswith(("6", "0", "3"))


def is_etf(name: str, code: str = "") -> bool:
    """判断是否为场内 ETF。

    识别依据：
      1. 名称含 "ETF"（大小写不敏感）
      2. 代码以 5（上海 ETF）或 1（深圳 ETF/LOF）开头

    Args:
        name: 证券名称
        code: 证券代码（可选，提升识别准确率）

    Returns:
        True 表示符合 ETF 特征
    """
    if "ETF" in name.upper():
        return True
    if code and code.startswith(("5", "1")):
        return True
    return False


def is_bond_fund(name: str) -> bool:
    """判断名称是否为债券基金。

    识别关键词：债 / 纯债 / 短债 / 中短债 / 利率债 / 信用债 / 债券

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配债券基金特征
    """
    return any(k in name for k in BOND_KEYWORDS)


def is_index_link(name: str) -> bool:
    """判断是否为场外指数联接基金。

    识别依据：
      1. 名称含 "ETF联接" / "ETF链接"（大小写不敏感，允许空格）
      2. 名称含 "联接" / "链接"

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配指数联接特征
    """
    clean = name.replace(" ", "").upper()
    if "ETF联接" in clean or "ETF链接" in clean:
        return True
    return any(kw in name for kw in ("联接", "链接"))


def is_offsite_fund(account: str) -> bool:
    """判断账户是否为场外基金渠道。

    场外渠道指通过基金公司、支付宝、微信、银行购买的基金，
    这类账户中的品种不可能是场内股票/ETF。

    Args:
        account: 账户名称

    Returns:
        True 表示为场外基金账户
    """
    return any(kw in account for kw in FUND_ACCOUNT_KEYWORDS)


def is_qdii(name: str) -> bool:
    """判断是否为 QDII 基金（含隐式 QDII 识别）。

    显式 QDII：名称含 "QDII"（大小写不敏感）。
    隐式 QDII：名称含海外指数关键词（纳斯达克、标普、纳指、道琼斯、日经），
              这些基金不带 QDII 字样但实际投资海外市场，净值更新同样延迟一日。

    Args:
        name: 基金名称

    Returns:
        True 表示 QDII 基金
    """
    if not name:
        return False
    upper = name.upper()
    if "QDII" in upper:
        return True
    return any(kw in name for kw in _OVERSEA_KW)
