"""证券代码工具 — 资产代码类型识别唯一入口。

集中管理 A 股/基金/债券/港股等资产类型的代码前缀和名称关键词知识，
避免多个模块各自维护一套判定规则。

所有与资产类型判定相关的逻辑都应收敛于此，而非散落在各模块中。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("invest")

# ── 已知代码前缀区间 ────────────────────────────────────────
# A 股股票：
#   60xxxx（上海主板）、68xxxx（科创板）
#   00xxxx（深圳主板/中小板，002xxx/003xxx）、30xxxx（创业板）
#   8xxxxx（北交所）
_A_SHARE_PREFIXES = ("60", "68", "00", "30")

# 场内基金 / ETF 前缀（1 开头含深市 ETF/LOF/Reits/可转债，5 开头含沪市 ETF）
_EXCHANGE_FUND_PREFIXES = ("5", "1")

# ── 名称关键词 ──────────────────────────────────────────────
# 债券基金关键词（用于基金类型识别，不包含过于宽泛的 "债" 以避免
# 可转债等非纯债品种被误判为债券基金）
_BOND_KEYWORDS = ("纯债", "短债", "中短债", "利率债", "信用债", "债券")

# 指数联接关键词
_INDEX_LINK_KEYWORDS = ("ETF联接", "ETF链接", "联接", "链接")

# 债券关键词宽松版（含单字"债"，覆盖可转债等含"债"字段的品种）
_BOND_KEYWORDS_BROAD = ("债", "纯债", "短债", "中短债", "利率债", "信用债", "债券")

# 场外基金账户关键词（用于 account 维度的判断）
FUND_ACCOUNT_KEYWORDS = ("基金", "支付宝", "微信", "银行")

# 指数类关键词（用于场外被动基金判定）
INDEX_KEYWORDS = ("指数", "ETF联接", "ETF 联接", "中证", "沪深300",
                  "中证500", "中证1000", "科创50", "创业板", "上证")

# 隐式 QDII 关键词
_OVERSEA_KW = ("纳斯达克", "标普", "纳指", "道琼斯", "日经")

# 货币类关键词
MONEY_KEYWORDS = ("货币", "现金", "增利", "宝")

# ── 指数代码相关常量 ──────────────────────────────────────────

# A 股指数交易所前缀
_INDEX_EXCHANGE_PREFIXES = ("sh", "sz")
# 美股指数代码前缀
_US_INDEX_PREFIX = "gb_"
# A 股指数原始 6 位码起始数字
_A_INDEX_RAW_PREFIXES = ("000", "399", "932")


# ═══════════════════════════════════════════════════════════════
#  代码前缀型判定（6 位证券代码，可含 sh/sz/bj 前缀）
# ═══════════════════════════════════════════════════════════════


def is_a_share_code(code: str) -> bool:
    """判断 6 位证券代码是否为 A 股股票。

    港股（00700）、基金（161725 等）返回 False。

    Args:
        code: 证券代码，可含 sh/sz/bj 前缀

    Returns:
        True 为 A 股代码
    """
    raw = _strip_prefix(code)
    if not raw:
        return False
    return raw.startswith(_A_SHARE_PREFIXES) or raw.startswith("8")


def is_exchange_fund_code(code: str) -> bool:
    """判断是否为场内基金/ETF 代码（5xxxxx 或 1xxxxx 开头）。

    含沪市 ETF（51/56/58）、深市 ETF（159）、LOF、Reits（18）、
    可转债（12）等场内交易品种。

    Args:
        code: 6 位证券代码

    Returns:
        True 为场内基金/ETF 代码
    """
    raw = _strip_prefix(code)
    if not raw:
        return False
    return raw.startswith(_EXCHANGE_FUND_PREFIXES)


def is_hk_stock_code(code: str) -> bool:
    """判断是否为港股通标的（5 位纯数字代码，如 00700、03690）。

    港股通标的通过 Stock Connect 在 A 股账户中交易，
    代码格式为 5 位数字，与 A 股的 6 位代码格式不同。

    Args:
        code: 证券代码

    Returns:
        True 为港股通代码
    """
    raw = code.strip()
    return len(raw) == 5 and raw.isdigit()


# ═══════════════════════════════════════════════════════════════
#  名称关键词型判定
# ═══════════════════════════════════════════════════════════════


def is_qdii_by_name(name: str) -> bool:
    """判断基金名称是否含 QDII 标识。

    Args:
        name: 基金名称

    Returns:
        True 为 QDII 基金
    """
    return "QDII" in name.upper()


def is_bond_related_by_name(name: str) -> bool:
    """判断名称是否含债券类关键词（严格版）。

    匹配纯债/短债/中短债/利率债/信用债/债券，不含单字"债"，
    因此可转债等品种不会被误判。如需覆盖可转债请使用
    :func:`is_bond_fund_by_name`。

    Args:
        name: 持仓名称

    Returns:
        True 表示名称匹配债券特征
    """
    return any(kw in name for kw in _BOND_KEYWORDS)


def is_etf_by_name(name: str) -> bool:
    """判断名称是否含 ETF 标识。

    Args:
        name: 持仓名称

    Returns:
        True 为 ETF
    """
    return "ETF" in name.upper()


def is_index_link_by_name(name: str) -> bool:
    """判断名称是否含指数联接关键词。

    识别：ETF联接 / ETF链接 / 联接 / 链接

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配指数联接特征
    """
    clean = name.replace(" ", "").upper()
    if "ETF联接" in clean or "ETF链接" in clean:
        return True
    return any(kw in name for kw in ("联接", "链接"))


def is_etf_by_name_or_code(name: str, code: str = "") -> bool:
    """判断是否为 ETF（名称 + 代码双维度检测）。

    识别依据：
      1. 名称含 "ETF"（大小写不敏感）
      2. 代码以 5（上海 ETF）或 1（深圳 ETF/LOF）开头

    Args:
        name: 持仓名称
        code: 证券代码（可选，提升识别准确率）

    Returns:
        True 表示符合 ETF 特征
    """
    if "ETF" in name.upper():
        return True
    if code:
        raw = _strip_prefix(code)
        if raw.startswith(("5", "1")):
            return True
    return False


def is_bond_fund_by_name(name: str) -> bool:
    """判断名称是否为债券基金（宽松匹配）。

    使用 ``_BOND_KEYWORDS_BROAD``（含"债"）进行匹配，
    覆盖纯债/短债/可转债等含"债"字段的品种。

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配债券基金特征
    """
    return any(k in name for k in _BOND_KEYWORDS_BROAD)


def is_offsite_fund(account: str) -> bool:
    """判断账户是否为场外基金渠道。

    场外渠道指通过基金公司、支付宝、微信、银行购买的基金。

    Args:
        account: 账户名称

    Returns:
        True 表示为场外基金账户
    """
    return any(kw in account for kw in FUND_ACCOUNT_KEYWORDS)


def is_qdii_extended(name: str | None) -> bool:
    """判断是否为 QDII 基金（含隐式海外基金识别）。

    显式 QDII：名称含 "QDII"（大小写不敏感）。
    隐式 QDII：名称含海外指数关键词（纳斯达克、标普、纳指、道琼斯、日经）。

    Args:
        name: 基金名称

    Returns:
        True 表示 QDII 基金（含隐式海外）
    """
    if not name:
        return False
    if is_qdii_by_name(name):
        return True
    return any(kw in name for kw in _OVERSEA_KW)


def is_money_fund_by_name(name: str) -> bool:
    """判断名称是否为货币类基金。

    识别关键词：货币、现金、增利、宝。

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配货币基金特征
    """
    return any(kw in name for kw in MONEY_KEYWORDS)


def is_index_fund_by_name(name: str) -> bool:
    """判断名称是否为场外指数/被动型基金。

    通过 INDEX_KEYWORDS（指数/ETF联接/中证/沪深300/中证500/
    中证1000/科创50/创业板/上证）进行匹配，用于区分场外
    被动基金与场外主动基金。

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配指数/被动基金特征
    """
    return any(kw in name for kw in INDEX_KEYWORDS)


# 场外基金名称关键词（用于 00 代码重叠区辅助判断）
_OTC_FUND_NAME_KW = (
    "混合",      # XX灵活配置混合/偏股混合/偏债混合
    "纯债",      # 纯债债券
    "短债",      # 短债债券
    "中短债",    # 中短债债券
    "利率债",    # 利率债债券
    "信用债",    # 信用债债券
    "货币",      # 货币市场基金
    "联接",      # ETF联接
    "增利",      # 增利货币
)


def is_otc_fund_by_name(name: str, code: str) -> bool:
    """判断 00 代码是否为场外基金（名称 + 代码双维度）。

    OTC 基金代码以 00 开头，与深市主板股票代码区间重叠，
    单纯靠前缀 `is_a_share_code()` 无法区分。本函数利用
    名称中的基金特征关键词辅助判定。

    Args:
        name: 持仓名称
        code: 6 位证券代码（可为空，仅非 00 开头时提前返回）

    Returns:
        True 表示确认为场外基金
    """
    raw = _strip_prefix(code) if code else ""
    if not raw or not raw.startswith("00"):
        return False
    return any(kw in name for kw in _OTC_FUND_NAME_KW)


def is_otc_code_overlap(code: str) -> bool:
    """判断 6 位代码是否处于 A 股/OTC 基金代码重叠区（00 开头）。

    OTC 基金代码以 00 开头，与深市主板（000~004）和中小板（002/003）
    股票代码区间重叠。本函数仅检测前缀，不验证名称，
    用于降级路由中判断"是否值得尝试基金净值 API"的快速预筛。

    Args:
        code: 6 位证券代码

    Returns:
        True 表示代码处于重叠区间（00 开头）
    """
    raw = _strip_prefix(code)
    return bool(raw and raw.startswith("00"))


def is_fund_holding(name: str, code: str, account: str) -> bool:
    """判断持仓是否需要基金业绩分析。

    识别逻辑：纯 A 股/港股通（代码前缀匹配且名称不含 ETF）
    且不在场外基金账户中 → 非基金，其余全部视为基金。

    对 00 代码重叠区，优先通过 ``is_otc_fund_by_name()`` 确认。

    Args:
        name: 持仓名称
        code: 证券代码
        account: 账户名称

    Returns:
        True 表示需要基金业绩分析
    """
    if is_otc_fund_by_name(name, code):
        return True
    return not ((is_a_share_code(code) or is_hk_stock_code(code)) and "ETF" not in name.upper() and not is_offsite_fund(account))


# ═══════════════════════════════════════════════════════════════
#  交易所 / API 前缀
# ═══════════════════════════════════════════════════════════════


def get_exchange_prefix(code: str) -> str:
    """根据 6 位代码返回东方财富行情页所需的交易所前缀。

    Args:
        code: 6 位证券代码

    Returns:
        "sh" | "sz" | "bj"
    """
    raw = code.strip()
    if raw.startswith(("5", "6")):
        return "sh"
    if raw.startswith(("0", "1", "2", "3", "9")):
        return "sz"
    return "bj"


def get_push2_secid(code: str) -> str:
    """生成东方财富 push2 API 所需的 secid 参数。

    - 沪市（6/5/8/4 开头）：1.{code}
    - 深市（0/1/2/3 开头）：0.{code}

    Args:
        code: 6 位证券代码

    Returns:
        "0.xxx" 或 "1.xxx"
    """
    raw = code.strip()
    if raw.startswith(("0", "1", "2", "3")):
        return f"0.{raw}"
    return f"1.{raw}"


# ═══════════════════════════════════════════════════════════════
#  指数代码判定（基准指数比对功能）
# ═══════════════════════════════════════════════════════════════


def is_index_code(code: str) -> bool:
    """判断代码是否为指数代码（A 股/美股通用）。

    识别依据：
      - 美股指数：``gb_`` 开头（如 ``gb_inx``）
      - A 股指数：``sh``/``sz`` 前缀 + 6 位码（以 000/399/932 开头）
      - 纯 6 位 000/399/932 开头代码（无前缀时也识别）

    Args:
        code: 指数代码

    Returns:
        True 表示该代码为指数代码
    """
    raw = code.strip()
    if not raw:
        return False
    # 美股指数
    if raw.startswith(_US_INDEX_PREFIX):
        return True
    # 去除交易所前缀
    stripped = raw
    for prefix in _INDEX_EXCHANGE_PREFIXES:
        if raw.startswith(prefix):
            stripped = raw[len(prefix):]
            break
    # A 股指数：6 位数字码以特定前缀开头
    return len(stripped) == 6 and stripped.isdigit() and stripped.startswith(_A_INDEX_RAW_PREFIXES)


def is_us_index_code(code: str) -> bool:
    """判断是否为美股指数代码（``gb_`` 开头）。

    Args:
        code: 指数代码

    Returns:
        True 表示该代码为美股指数
    """
    return bool(code and code.strip().startswith(_US_INDEX_PREFIX))


def get_index_exchange_prefix(code: str) -> str:
    """获取 A 股指数代码的交易所前缀。

    如 ``"sh000300"`` → ``"sh"``，非 A 股指数（如 ``"gb_inx"``）返回空字符串。

    Args:
        code: 指数代码

    Returns:
        ``"sh"`` | ``"sz"`` | ``""``
    """
    raw = code.strip()
    for prefix in _INDEX_EXCHANGE_PREFIXES:
        if raw.startswith(prefix):
            return prefix
    return ""


# ═══════════════════════════════════════════════════════════════
#  内部工具
# ═══════════════════════════════════════════════════════════════


def _strip_prefix(code: str) -> str:
    """去除 sh/sz/bj 前缀，返回纯净 6 位数字代码。

    Args:
        code: 可带前缀的代码

    Returns:
        纯净 6 位数字代码，或空字符串（非 6 位数字时）
    """
    raw = code.strip()
    if not raw:
        return ""
    for prefix in ("sh", "sz", "bj"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    if len(raw) == 6 and raw.isdigit():
        return raw
    return ""
