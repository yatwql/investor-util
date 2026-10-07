"""Provider Chain 链定义与覆盖 —— `_DEFAULT_CHAINS` 优先级表、preferred/exclude 覆盖、链健康判定。

每类数据（price/index/rank/holding）对应一条 Provider Chain；用户可通过 config.json 的
``preferred_provider`` 指定首选链路，``exclude_providers`` 排除指定源。模块加载时把默认链
注入 core 注册表（``register_default_chains``）并注册交易日历兜底。

对外门面为 ``fetcher/chain.py``（本模块符号经其 re-export）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import contextmanager

from src.python.config import get_config
from src.python.core.provider_registry import get_registry


logger = logging.getLogger("invest")


# ── Provider Chain 定义 ──────────────────────────────────────

_DEFAULT_CHAINS: dict[str, list[str]] = {
    # 行情：腾讯 → 新浪 → 同花顺（需 key）
    "price_stock": ["tencent", "sina", "hithink"],
    # 场外基金净值：东财基金 API 主源 → 新浪基金接口备源（跨厂商，故障域独立）
    "price_fund_otc": ["eastmoney", "sina_fund"],
    "price": ["tencent", "eastmoney"],
    "fund_rank": ["tiantian"],
    # 基金披露持仓：天天基金为主，同花顺官方源为备（官方源需 key，未配置时链路自动跳过）
    "fund_hold": ["tiantian", "hithink"],
    # 基金申购限购状态总表（全量单键、每日 1 次）：天天基金直连为主，
    # akshare 封装为备——两者共享同一上游端点，提供的是**解析器冗余**而非源冗余，
    # 端点整体不可用时真正的可用性兜底是最外层过期缓存（载荷带 fetched_at 供陈旧阶梯判定）
    "fund_purchase": ["tiantian", "akshare_purchase"],
    # 基金申赎费率（F10 交易费率页，按代码分键、低频）：天天基金 F10 直连为主，
    # akshare fund_fee_em 封装为备（同上游页面族、解析器冗余；备链路仅覆盖赎回
    # 阶梯，申购档位由全量申购状态表单档/配置兑底承接），真正可用性兑底是过期缓存
    "fund_fee": ["tiantian_f10", "akshare_fee"],
    "industry": ["eastmoney_industry", "eastmoney_industry_rest"],
    # 全文本财报（持仓基本面章·区块②）：DataSinking 主源 + 巨潮资讯网备源。
    # 两源经财报域适配器注册（fetcher/report_adapters.py），以 ``source_hint`` 做命名空间
    # 隔离（异源候选被异源适配器立即拒服务）——因此**两个源都必须在本链的槽位里**：
    # 编排层从巨潮索引/备源列表构造的候选带 ``source_hint=cninfo``，若链上只有主源槽，
    # 它们会被主源适配器拒后无处可去 → 备源正文永远取不到（日志表现为“尝试 DataSinking
    # 财报 → datasink 返回空 → 全链路失败”且无任何 `[datasink]` 请求日志）。
    "financial_report": ["datasink", "cninfo"],
    # 结构化财务指标（akshare 主源；备用支路 datasink_indicator 从财报全文解析）
    # 财务指标：akshare 主源 → DataSinking 章节解析支路 → 同花顺官方报表派生（需 key）
    "financial_indicator": ["akshare_financial", "datasink_indicator", "hithink"],
    # 组合历史走势：历史数据 chains（复用现有 provider name，熔断器共享）
    # 历史日 K：腾讯（前复权）→ 新浪 → 同花顺官方（前复权，需 key）
    "history_stock": ["tencent", "sina", "hithink"],
    "history_fund_otc": ["tiantian", "eastmoney"],
    # 指数历史日 K：腾讯（前复权）→ 东方财富 push2his（免 key 的独立厂商备源）→
    # 新浪（``getKLineData`` 端点实测不可用，留作代码级备用）→ 同花顺官方（需 key）。
    # 新浪单靠不住，故补东方财富作为**可用**的第二源——避免整链退化为事实单源后
    # 「抖动即整链空」（历史链无链级重试，重试在各 provider 内，见 tencent/eastmoney）。
    "history_index": ["tencent", "eastmoney", "sina", "hithink"],
    # 美股指数历史日线：新浪实现 fetch_index_kline（providers/sina_kline.py，经
    # providers/sina.py 重导出），但其 getKLineData 端点对全部代码返回 404/空，
    # 故实际取数通常由腾讯完成；腾讯 K 线接口对 gb_* 代码支持有限，该链可能整链
    # 取空——空结果按正常降级记录，不视作配置错误。
    "history_index_us": ["sina", "tencent"],
    # 无风险利率：首选 akshare（bond_zh_us_rate），配置兜底
    "bond_yield": ["akshare"],
    # 市场情绪与资金热点（龙虎榜/连板梯队，同花顺官方，需 key；报告层不得直连）
    "sentiment": ["hithink"],
}


def _get_chain(data_type: str) -> list[str]:
    """获取指定数据类型的 Provider Chain（考虑用户配置与本次运行覆盖）。

    优先级（高到低）：调用级覆盖（:func:`chain_overrides`）> 配置级
    ``config.json → preferred_provider.<data_type>`` > 默认链。
    两者都只是**排序/过滤**：既不新增链上源，也不绕过熔断与凭据就绪预检。
    """
    chain = list(_DEFAULT_CHAINS.get(data_type, []))
    try:
        config = get_config()
        preferred = (config.get("preferred_provider") or {}).get(data_type)
        if preferred and preferred in chain and chain[0] != preferred:
            chain.remove(preferred)
            chain.insert(0, preferred)
            logger.info("%s Provider Chain: 根据配置首选 '%s'", data_type, preferred)
    except (KeyError, TypeError):
        logger.debug("[chain] preferred_provider 配置解析失败，使用默认链")
    return _apply_overrides(chain, data_type)


# ── 调用级源覆盖（本次运行作用域） ──────────────────────────
#
# 语义：进程内的一次报告运行 = 一个覆盖作用域（非线程局部——报告管线在取数阶段存在
# 并行，线程局部变量不会传播到工作线程，会造成「同一次运行内部分请求生效」的隐式
# 不一致）。生命周期由上下文管理器保证：退出即恢复，长驻进程（Web 模式）不留残留。
_override_preferred: str | None = None


_override_exclude: frozenset[str] = frozenset()


def known_provider_names() -> set[str]:
    """全部已登记 provider 名（由默认链并集派生，不另写清单）。"""
    names: set[str] = set()
    for chain in _DEFAULT_CHAINS.values():
        names.update(chain)
    return names


@contextmanager
def chain_overrides(
    preferred: str | None = None,
    exclude: Iterable[str] | None = None,
):
    """本次运行作用域内覆盖源链排序/过滤（可嵌套，退出即恢复）。

    Args:
        preferred: 首选源名；不在该数据类型链上或不是已知 provider 时仅告警、不生效。
        exclude: 需排除的源名集合（仅本次运行）。
    """
    global _override_preferred, _override_exclude
    previous = (_override_preferred, _override_exclude)
    _override_preferred = preferred
    _override_exclude = frozenset(exclude or ())
    try:
        yield
    finally:
        _override_preferred, _override_exclude = previous


def reset_chain_overrides() -> None:
    """清空调用级覆盖（测试隔离用；生产路径由上下文管理器负责恢复）。"""
    global _override_preferred, _override_exclude
    _override_preferred = None
    _override_exclude = frozenset()


def _apply_overrides(chain: list[str], data_type: str) -> list[str]:
    """按调用级覆盖过滤/重排链（不改变链上源的集合，除显式 exclude）。"""
    if _override_exclude:
        filtered = [p for p in chain if p not in _override_exclude]
        if filtered != chain:
            logger.info("%s Provider Chain: 本次运行排除 %s", data_type, "、".join(sorted(_override_exclude)))
        chain = filtered

    preferred = _override_preferred
    if preferred:
        if preferred not in known_provider_names():
            logger.warning("未知 provider 名 '%s'（本次运行首选不生效）", preferred)
        elif preferred not in chain:
            logger.warning("%s Provider Chain: 本次运行首选 '%s' 不在该链上，忽略", data_type, preferred)
        elif chain[0] != preferred:
            chain.remove(preferred)
            chain.insert(0, preferred)
            logger.info("%s Provider Chain: 本次运行首选 '%s'", data_type, preferred)
    return chain


def reset_provider_skip() -> None:
    """重置 Provider 熔断状态（测试用）。委托 DataSourceRegistry.reset()。"""
    get_registry().reset()


def is_provider_chain_broken(data_type: str) -> bool:
    """检查指定数据类型的全部 Provider 是否都已熔断。

    batch 入口调用一次即可预判全链不可用，避免逐条重复尝试。

    Returns:
        True — 链上所有 provider 均在熔断中，全链不可用
        False — 至少有一个 provider 可用
    """
    chain = _get_chain(data_type)
    if not chain:
        return True
    return get_registry().is_chain_broken(chain)


def _register_core_calendar_fallback() -> None:
    """官方交易日序列兜底注入 core 交易日历（core 不反向 import providers）。"""
    from src.python.providers import hithink
    from src.python.core.trading_calendar import register_trading_days_fallback

    register_trading_days_fallback(hithink.fetch_trading_days)


# 模块加载时自动注册默认 Provider Chain，使 registry.get_chain() 和策略选择器生效
# 链路定义注入 core 注册表（core 不反向 import fetcher；传参而非 registry 自取）
get_registry().register_default_chains(_DEFAULT_CHAINS)


_register_core_calendar_fallback()
