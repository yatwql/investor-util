"""LLM 缓存指纹模块 — 指纹计算与缓存 TTL 管理。"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("invest")

__all__ = [
    "compute_fingerprint",
    "extract_stable_holdings",
    "extract_stable_penetration",
    "build_llm_fingerprint",
    "get_cache_ttl_llm",
]


def compute_fingerprint(*args: Any) -> str:
    """计算输入数据的确定性哈希值（前 12 位），用作缓存键后缀。

    当市场行情、持仓数据变化时指纹随之改变，
    自动跳过旧缓存，无需等待 TTL 过期。
    """
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def extract_stable_holdings(holdings_details: list[dict] | None) -> list[dict]:
    """从持仓明细中提取稳定的（无行情波动）字段。"""
    if not holdings_details:
        return []
    return [{"name": d.get("name", ""), "code": d.get("code", ""), "cost": d.get("cost", 0)} for d in holdings_details]


def extract_stable_penetration(penetrated_assets: list[dict] | None, full: bool = False) -> list[dict]:
    """从穿透资产中提取稳定的（无行情波动）字段。

    Args:
        penetrated_assets: 穿透 TOP10 资产列表
        full: 若为 True 则包含 mv/ratio/sector（用于穿透深度分析的额外区分）

    Returns:
        稳定字段的字典列表
    """
    result: list[dict] = []
    if penetrated_assets:
        for a in penetrated_assets:
            entry = {"name": a.get("name", ""), "codes": a.get("codes", [])}
            if full:
                entry["mv"] = a.get("mv", 0)
                entry["sector"] = a.get("sector", "")
                entry["ratio"] = a.get("ratio", 0)
            result.append(entry)
    return result


def build_llm_fingerprint(
    total_mv: float = 0,
    total_cost: float = 0,
    total_profit: float = 0,
    total_today_profit: float = 0,
    holdings_details: list[dict] | None = None,
    penetrated_assets: list[dict] | None = None,
    categories: dict | None = None,
    full_penetration: bool = False,
    history_data: dict | None = None,
) -> str:
    """构建 LLM 模块的缓存指纹，统一剔除行情波动字段。

    替代 _expert_review_fingerprint / _health_check_fingerprint / _penetration_deep_fingerprint。

    使用 _extract_stable_holdings 剔除行情波动；
    穿透资产默认仅取 (name, codes)，full_penetration=True 时额外包含
    mv/sector/ratio（穿透深度分析需要穿透数据更新触发缓存失效）。

    history_data 参数提取 key 风险信号摘要加入指纹，
    使风险指标变化时自动失效 LLM 缓存。

    Args:
        total_mv: 总市值
        total_cost: 总成本
        total_profit: 总盈亏
        total_today_profit: 本日盈亏
        holdings_details: 持仓明细（仅提取 name/code/cost）
        penetrated_assets: 穿透资产列表
        categories: 分类汇总
        full_penetration: 为 True 时穿透资产包含 mv/sector/ratio（用于穿透深度分析）
        history_data: 组合历史走势数据，仅提取 key 风险信号摘要

    Returns:
        指纹哈希值（前 12 位）
    """
    _details = extract_stable_holdings(holdings_details)
    _pen = extract_stable_penetration(penetrated_assets, full=full_penetration)

    # 从 history_data 提取 key 风险信号摘要
    _risk_signals: dict[str, float | str] = {}
    if history_data and isinstance(history_data, dict):
        for _key in ("max_drawdown_pct", "annualized_volatility", "total_return_pct", "status"):
            if _key in history_data:
                _risk_signals[_key] = history_data[_key]

    return compute_fingerprint(
        total_mv,
        total_cost,
        total_profit,
        total_today_profit,
        categories,
        _details,
        _pen,
        _risk_signals,
    )


def get_cache_ttl_llm(subtype: str = "global_macro") -> float:
    """获取 LLM 缓存 TTL。

    TTL 优先级：
      1. config.json 中的 cache_ttl.llm_global_macro / llm_expert_review / llm_news_correlation
      2. 代码默认值（全球政经局势 86400s / 智囊团深度复盘 7200s / 财经新闻热点与持仓关联分析 3600s）

    Args:
        subtype: "global_macro"（全球政经局势）、"expert_review"（智囊团深度复盘）或 "news_correlation"（财经新闻热点与持仓关联分析）

    Returns:
        过期时间（秒）
    """
    # 从 config.json cache_ttl 读取
    _key_map: dict[str, str] = {
        "global_macro": "llm_global_macro",
        "expert_review": "llm_expert_review",
        "news_correlation": "llm_news_correlation",
        "health_check": "llm_health_check",
        "penetration_deep": "llm_penetration_deep",
        "debate_pro": "llm_debate_pro",
        "debate_con": "llm_debate_con",
        "debate_synthesis": "llm_debate_synthesis",
    }
    data_type = _key_map.get(subtype, "llm_global_macro")
    try:
        from src.python.cache import get_ttl

        return get_ttl(data_type)
    except (ImportError, TypeError, AttributeError):
        logger.debug("_get_llm_ttl: 获取 TTL 失败，使用 LLM 默认值")
        defaults: dict[str, float] = {
            "global_macro": 86400,
            "expert_review": 7200,
            "news_correlation": 3600,
            "health_check": 86400,
            "penetration_deep": 86400,
            "debate_pro": 86400,
            "debate_con": 86400,
            "debate_synthesis": 86400,
        }
        return defaults.get(subtype, 3600)
