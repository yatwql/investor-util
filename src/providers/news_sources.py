"""财经新闻源获取模块。

管理各新闻源（新浪/东方财富/财联社/华尔街见闻/akshare）的获取函数和注册表。

各新闻源的启用在 config.json 中配置（news_sources 字段），
代码不硬编码开关状态。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("invest")

# ── 新闻来源注册（静态元数据，不含开关状态） ─────────────────

_SOURCE_LABELS: dict[str, str] = {
    "sina": "新浪财经",
    "eastmoney": "东方财富",
    "cls": "财联社",
    "wallstreetcn": "华尔街见闻",
    "akshare": "财新网 / CCTV",
}

# 代码内默认开关（config.json 中 news_sources 未配置时使用的后备值）
_FALLBACK_ENABLED: dict[str, bool] = {
    "sina": True,
    "eastmoney": True,    # 快讯接口（np-weblist）稳定可用
    "cls": False,          # API 已要求签名鉴权（errno=10012），匿名请求不可用
    "wallstreetcn": True,  # 华尔街见闻 API 稳定可用，无需鉴权
    "akshare": True,       # akshare 封装财新网/CCTV，开源稳定
}


def get_source_label(name: str) -> str:
    """返回新闻源的中文标签。"""
    return _SOURCE_LABELS.get(name, name)


def _fetch_from_sina(num: int) -> list[dict[str, Any]]:
    """从新浪财经获取新闻，均匀覆盖多个分类。"""
    try:
        from src.providers.sina_news import fetch_news as sina_fetch
    except ImportError:
        logger.warning("新浪财经模块不可用")
        return []

    lids = ["2516", "2509", "2510"]  # 财经要闻, 国内财经, 国际财经
    per_category = max(1, num // len(lids))

    all_items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for lid in lids:
        items = sina_fetch(lid=lid, num=per_category, page=1)
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_items.append(item)

    logger.info("新浪财经: 获取 %d 条 (去重后)", len(all_items))
    return all_items


def _fetch_from_eastmoney(num: int) -> list[dict[str, Any]]:
    """从东方财富获取新闻。"""
    try:
        from src.providers.eastmoney_news import fetch_news as em_fetch
    except ImportError:
        logger.warning("东方财富模块不可用")
        return []

    items = em_fetch(num=num)
    logger.info("东方财富: 获取 %d 条", len(items))
    return items


def _fetch_from_cls(num: int) -> list[dict[str, Any]]:
    """从财联社获取新闻。"""
    try:
        from src.providers.cls_news import fetch_news as cls_fetch
    except ImportError:
        logger.warning("财联社模块不可用")
        return []

    items = cls_fetch(num=num)
    logger.info("财联社: 获取 %d 条", len(items))
    return items


def _fetch_from_wallstreetcn(num: int) -> list[dict[str, Any]]:
    """从华尔街见闻获取新闻。"""
    try:
        from src.providers.wallstreetcn_news import fetch_news as wsc_fetch
    except ImportError:
        logger.warning("华尔街见闻模块不可用")
        return []

    items = wsc_fetch(num=num)
    logger.info("华尔街见闻: 获取 %d 条", len(items))
    return items


def _fetch_from_akshare(num: int) -> list[dict[str, Any]]:
    """通过 akshare 获取财新网 + CCTV 财经新闻。"""
    try:
        from src.providers.akshare_news import fetch_news as ak_fetch
    except ImportError:
        logger.warning("akshare 模块不可用")
        return []

    items = ak_fetch(num=num)
    logger.info("akshare 新闻: 获取 %d 条", len(items))
    return items


_FETCH_MAP: dict[str, Callable] = {
    "sina": _fetch_from_sina,
    "eastmoney": _fetch_from_eastmoney,
    "cls": _fetch_from_cls,
    "wallstreetcn": _fetch_from_wallstreetcn,
    "akshare": _fetch_from_akshare,
}
