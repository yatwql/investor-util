"""持仓源守卫边缘场景 —— 解析异常/缺省回退/全局配置。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - 持仓路径解析异常 → fail-closed 判非正式源（宁可少写、不误写用户历史）
  - holdings_dir/holdings_filename 为空 → 回退默认表（正式源不受误伤）
  - config=None → 经全局配置同源解析（隔离后默认值仍为正式目录）
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


class TestFormalHoldingsSourceJudgeEdge:
    """正式持仓源判定边缘。"""

    def test_resolve_failure_fails_closed(self, monkeypatch):
        """路径解析抛异常 → 按非正式源处理（不写用户历史）。"""
        import src.python.config as config_pkg

        def _boom(_cfg=None):
            raise RuntimeError("配置不可读")

        monkeypatch.setattr(config_pkg, "resolve_holdings_path", _boom)
        assert config_pkg.is_formal_holdings_source({}) is False

    def test_empty_dir_and_filename_fall_back_to_defaults(self):
        """holdings_dir/holdings_filename 为空串 → 回退默认表（正式源）。"""
        from src.python.config import is_formal_holdings_source

        assert is_formal_holdings_source({"holdings_dir": "", "holdings_filename": ""}) is True

    def test_config_none_uses_global_defaults(self):
        """config=None → 经全局配置解析，隔离环境默认值仍指向正式目录。"""
        from src.python.config import is_formal_holdings_source

        assert is_formal_holdings_source(None) is True
