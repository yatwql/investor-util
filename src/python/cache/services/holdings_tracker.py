"""缓存引擎 — 持仓跟踪服务。

职责：持仓指纹计算、持仓变更检测、关联缓存自动刷新。
"""

from __future__ import annotations

import builtins
import hashlib
import json
import logging
import os

from .._groups import clear_by_prefix
from .._paths import _cache_path
from .._store import clear, set

logger = logging.getLogger("invest")


def compute_holdings_fingerprint(holdings: list) -> str:
    """计算持仓指纹，用于检测持仓是否发生变更。

    基于 (代码, 账户, 份额, 每份成本) 的四元组生成 MD5 指纹。
    持仓变更（新增/清仓/改仓位）会改变指纹，触发关联缓存刷新。

    Args:
        holdings: 持仓记录列表，每项需有 code/account/shares/cost_price 属性

    Returns:
        MD5 十六进制字符串
    """
    items = sorted((h.code, h.account, h.shares, h.cost_price) for h in holdings)
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def compute_holdings_codes(holdings: list) -> builtins.set[str]:
    """提取持仓中的证券代码集合。

    Args:
        holdings: 持仓记录列表，每项需有 code 属性

    Returns:
        全部代码的集合
    """
    return {h.code for h in holdings}


def _read_holdings_tracking(tracking_key: str) -> dict | None:
    """读取上次存储的持仓跟踪数据。

    Returns:
        跟踪数据字典（含 fingerprint / codes），文件不存在或损坏时返回 None
    """
    track_path = _cache_path(tracking_key)
    if not os.path.exists(track_path):
        return None
    try:
        with open(track_path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("_data")
    except (json.JSONDecodeError, OSError, KeyError):
        logger.warning("读取持仓跟踪缓存数据失败，将重新生成")
        return None


def _clear_holdings_related_caches() -> list[str]:
    """清除与持仓关联的缓存（fund_benchmarks + industry_*）。

    Returns:
        已清除的缓存项描述列表
    """
    cleared: list[str] = []
    bm_path = _cache_path("fund_benchmarks")
    if os.path.exists(bm_path):
        clear("fund_benchmarks")
        cleared.append("fund_benchmarks")
    ind_count = clear_by_prefix("industry_")
    if ind_count > 0:
        cleared.append(f"industry_({ind_count}条)")
    if cleared:
        logger.info("已清除过期缓存: %s", ", ".join(cleared))
    else:
        logger.info("关联缓存尚未生成，无需清除")
    return cleared


def check_and_refresh_caches(holdings: list) -> list[str]:
    """检查持仓是否发生变化，若有变更则自动刷新关联缓存并返回新增资产代码。

    比较当前持仓指纹与上次存储的指纹。若不同：
      - 清除 fund_benchmarks.json（触发重新获取业绩基准）
      - 更新存储的指纹和代码集合
      - 返回新增的资产代码列表（用于主流程主动取数填充单条缓存）

    注意：份额/成本变动只会改变指纹（触发关联缓存刷新），不会将已有资产
    误判为"新增"——仅当代码集合中出现了未记录的代码时才视为新增。

    Args:
        holdings: 当前持仓列表（每项需有 code/account/shares/cost_price）

    Returns:
        新持仓相比上次新增的资产代码列表；无变化时返回空列表。
    """
    tracking_key = "holdings_tracking"

    current_fp = compute_holdings_fingerprint(holdings)
    current_codes = compute_holdings_codes(holdings)

    prev_data = _read_holdings_tracking(tracking_key)

    # ── 指纹相同 → 持仓未变 ──────────────────────────────
    if prev_data is not None:
        prev_fp = prev_data.get("fingerprint")
        if prev_fp == current_fp:
            return []

    # ── 指纹不同 → 清除关联缓存，更新跟踪数据 ────────────
    logger.info("持仓已变更，自动刷新关联缓存...")
    _clear_holdings_related_caches()

    # 先提取上一轮的代码集合（用于计算新增资产），再更新存储
    prev_codes_strs: list[str] = []
    if prev_data is not None:
        prev_codes_strs = prev_data.get("codes", [])
        if not prev_codes_strs:
            logger.debug("上一轮跟踪数据缺少 codes 字段或为空，所有代码将被视为新增")

    prev_codes = builtins.set(prev_codes_strs)
    new_codes = current_codes - prev_codes

    # 存储新跟踪数据（指纹 + 代码集合）—— 必须在判断 new_codes 之前完成
    set(
        tracking_key,
        {
            "fingerprint": current_fp,
            "codes": sorted(current_codes),
        },
    )

    if new_codes:
        logger.info(
            "检测到新增资产代码%s: %s",
            f"（上一轮共 {len(prev_codes)} 个代码）" if prev_codes else "",
            ", ".join(sorted(new_codes)),
        )
        return sorted(new_codes)

    if prev_data is not None and prev_codes:
        logger.debug(
            "持仓指纹变更（份额/成本变动），代码集合无变化 (共 %d 个)",
            len(current_codes),
        )
    return []
