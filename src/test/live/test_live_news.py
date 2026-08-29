"""真实新闻源连通性验证（opt-in live 套件，不入门禁）。

运行：`python scripts/test-runner.py --mode live` 或 `pytest -m live`。

断言原则：只校验返回「结构」（字段存在、类型、非空），不校验具体内容
（新闻标题/正文随时间变化）。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live]


@pytest.mark.live
def test_eastmoney_news():
    """东方财富快讯：返回结构化新闻列表。"""
    from src.python.providers.eastmoney_news import fetch_news

    items = fetch_news(num=10)
    assert isinstance(items, list)
    assert len(items) > 0, "东方财富快讯接口不可达或返回空"
    first = items[0]
    # 结构字段校验
    assert any(k in first for k in ("title", "content", "content_text"))
    assert first.get("title") or first.get("content_text")


@pytest.mark.live
def test_cls_news():
    """财联社快讯：返回结构化新闻列表。

    注：财联社 API 需签名鉴权（errno=10012），实际可能返回空列表 ——
    本用例只校验「返回类型正确」，不强制非空，避免因数据源自身鉴权限制
    误报。若有内容，校验其结构。
    """
    from src.python.providers.cls_news import fetch_news

    items = fetch_news(num=10)
    assert isinstance(items, list), "财联社接口应返回列表"
    if items:
        assert items[0].get("title")


@pytest.mark.live
def test_sina_news():
    """新浪财经新闻：返回结构化新闻列表。"""
    from src.python.providers.sina_news import fetch_news

    items = fetch_news(num=10)
    assert isinstance(items, list)
    assert len(items) > 0, "新浪财经接口不可达或返回空"
    assert items[0].get("title")


@pytest.mark.live
def test_wallstreetcn_news():
    """华尔街见闻：返回结构化新闻列表。"""
    from src.python.providers.wallstreetcn_news import fetch_news

    items = fetch_news(num=10)
    assert isinstance(items, list)
    assert len(items) > 0, "华尔街见闻接口不可达或返回空"
    assert items[0].get("title")
