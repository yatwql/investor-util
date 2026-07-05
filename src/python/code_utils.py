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

# 无歧义基金代码前缀（凭前缀即可断定是基金而非股票）
#   16xxxx（深圳 LOF）、50xxxx（上海 LOF/ETF）
#   51xxxx~52xxxx（上海 ETF）、159xxx（深圳 ETF）
#   184xxx（传统封基）
_FUND_PREFIXES = ("16", "50", "51", "52", "184")

# 股票类代码基本范围（A 股 + B 股 + 少量特殊品种）
_STOCK_PREFIXES = ("60", "68", "00", "30", "20", "8", "9")

# 场内基金 / ETF 前缀（1 开头含深市 ETF/LOF/Reits/可转债，5 开头含沪市 ETF）
_EXCHANGE_FUND_PREFIXES = ("5", "1")

# ── 名称关键词 ──────────────────────────────────────────────
# 债券基金关键词（用于基金类型识别，不包含过于宽泛的 "债" 以避免
# 可转债等非纯债品种被误判为债券基金）
_BOND_KEYWORDS = ("纯债", "短债", "中短债", "利率债", "信用债", "债券")

# 指数联接关键词
_INDEX_LINK_KEYWORDS = ("ETF联接", "ETF链接", "联接", "链接")


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


def is_fund_code(code: str) -> bool:
    """判断 6 位代码是否属于明确的基金前缀区间。

    仅返回**无歧义**的基金代码（通过前缀即可断定是基金而非股票）。
    000xxx/001xxx 等股基重叠区间返回 False，由调用方结合名称判断。

    Args:
        code: 6 位证券代码

    Returns:
        True 为明确基金代码
    """
    raw = _strip_prefix(code)
    if not raw:
        return False
    return raw.startswith(_FUND_PREFIXES) or raw.startswith("159")


def is_stock_like_code(code: str) -> bool:
    """判断 6 位代码是否属于股票类（A 股 + B 股 + 北交所）。

    is_a_share_code 的放宽版：除 A 股外还包含 B 股（20xxxx）
    和部分特殊品种（9xxxxx），用于行情获取类场景。

    Args:
        code: 6 位证券代码

    Returns:
        True 为股票类代码
    """
    raw = _strip_prefix(code)
    if not raw:
        return False
    return raw.startswith(_STOCK_PREFIXES)


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
    """判断名称是否含债券类关键词。

    覆盖纯债/短债/中短债/利率债/信用债/债券/债，包括可转债。

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
