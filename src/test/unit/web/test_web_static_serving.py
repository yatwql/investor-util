"""Web 静态资产服务回归测试（app.py 静态路由固定 /static/*）。

背景缺陷：Flask 未显式指定 static_url_path 时，按 static_folder 的 basename
推导（src/static/web/ → /web/*），导致 index.html 引用的 /static/main.js、
/static/style.css 全部 404 —— JS/CSS 未加载，前端整页失效（配置面板空白、
健康区卡静态"正在检测"、生成按钮灰色）。修复：app.py 显式
static_url_path="/static"。

回归断言：index.html 引用的全部 /static/* 资产都必须可访问（200），
任一路径漂移即失败。
"""

from __future__ import annotations

import re

import pytest

from src.python.config import _config_defaults
from src.python.config._core import invalidate_config_cache
from src.python.web.app import create_app
from src.python.web.runs import RunManager

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """构造 Flask test_client（仅静态资源读取，不触碰真实数据）。"""
    monkeypatch.setitem(_config_defaults._DEFAULT_CONFIG, "output_dir", str(tmp_path))
    invalidate_config_cache()
    rm = RunManager(executor=lambda state, params: 0)
    app = create_app(rm)
    app.config["TESTING"] = True
    return app.test_client()


def _static_asset_paths(index_html: str) -> list[str]:
    """提取 index.html 中全部 /static/* 资源路径（含查询串前缀）。"""
    return re.findall(r'(?:src|href)="(/static/[^"?#]+)', index_html)


class TestStaticServing:
    """前端静态资产可访问性（/static/* 路径固定）。"""

    def test_static_url_path_pinned_to_slash_static(self, app_client):
        """静态路由显式固定为 /static（不随 static_folder 目录名推导）。"""
        app = app_client.application
        assert app.static_url_path == "/static"

    def test_index_assets_all_served(self, app_client):
        """index.html 引用的全部 /static/* 资产均返回 200（核心回归断言）。"""
        client = app_client
        index_resp = client.get("/")
        assert index_resp.status_code == 200
        index_html = index_resp.get_data(as_text=True)

        assets = _static_asset_paths(index_html)
        assert assets, "index.html 未引用任何 /static/* 资产，断言前提失效"
        # 必须包含 JS 与 CSS 入口（前端功能依赖）
        assert any(a.endswith("/main.js") for a in assets)
        assert any(a.endswith("/style.css") for a in assets)

        for asset in assets:
            resp = client.get(asset)
            assert resp.status_code == 200, f"前端资产 404：{asset}"
            assert resp.get_data(), f"前端资产为空：{asset}"

    def test_main_js_reachable_and_contains_init(self, app_client):
        """main.js 可访问且含 DOMContentLoaded 初始化注册（防空壳文件）。"""
        resp = app_client.get("/static/main.js")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "DOMContentLoaded" in body and "init" in body
