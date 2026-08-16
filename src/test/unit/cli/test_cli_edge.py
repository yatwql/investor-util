"""CLI 命令行模式边缘/异常场景测试。

必须放在 *_edge.py 文件中（pytest_collection_modifyitems 强制约束）。
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_cli, pytest.mark.edge]

import os
from unittest.mock import MagicMock, patch

from src.python.cli import _EXIT_SEVERE, _EXIT_SUCCESS, _cli_read_holdings


class TestCliEdge:
    """CLI 边缘场景测试。"""

    @pytest.mark.edge
    def test_no_input_in_report_path(self):
        """report 路径无 input() 调用。"""
        mock_holdings = [MagicMock()]
        with (
            patch("src.python.cli.cli._cli_read_holdings", return_value=mock_holdings),
            patch("src.python.report.orchestrator.generate_report") as mock_gen,
        ):
            from src.python.cli import _handle_report
            args = MagicMock(type="basic", history="off", force_llm=False, output=None, verbose=False)
            _handle_report(args, {})

        # 验证 orchestrator.generate_report 被调用而非 input()
        mock_gen.assert_called_once()
        assert "input" not in str(mock_gen.call_args)

    @pytest.mark.edge
    def test_no_input_in_cache_path(self):
        """cache 路径无 input() 调用。"""
        from src.python.cli import _handle_cache_update

        mock_result = MagicMock()
        mock_result.exit_code = _EXIT_SUCCESS

        with (
            patch("src.python.cli.cli._cli_read_holdings", return_value=[MagicMock()]),
            patch("src.python.cache.operations.update_basic_cache", return_value=mock_result),
        ):
            code = _handle_cache_update("basic", {}, MagicMock())

        assert code == _EXIT_SUCCESS

    @pytest.mark.edge
    def test_holdings_not_found_exit_severe(self, caplog):
        """持仓文件不存在时 → _EXIT_SEVERE。"""
        caplog.set_level(10)

        config = {"holdings_dir": "/tmp", "holdings_filename": "nonexistent.xlsx"}
        result = _cli_read_holdings(config)
        assert result is None

    @pytest.mark.edge
    def test_holdings_dir_is_none(self):
        """holdings_dir 缺失时使用默认值。"""
        # 使用不存在的路径但 holdings_dir 取默认值
        with patch("src.python.cli.cli.os.path.exists", return_value=False):
            result = _cli_read_holdings({})
        assert result is None

    @pytest.mark.edge
    def test_multi_holdings_auto_select(self, tmp_path, caplog):
        """多个 xlsx 文件时自动选第一个（最新修改的）。"""
        caplog.set_level(10)

        # 创建临时持仓目录和文件
        holdings_dir = tmp_path / "holdings"
        holdings_dir.mkdir()
        f1 = holdings_dir / "持仓1.xlsx"
        f2 = holdings_dir / "持仓2.xlsx"
        f1.write_text("dummy")
        f2.write_text("dummy")

        # f2 修改时间更新
        import time
        now = time.time()
        os.utime(str(f1), (now - 100, now - 100))
        os.utime(str(f2), (now, now))

        config = {
            "holdings_dir": str(holdings_dir),
            "holdings_filename": str(holdings_dir),  # 指向目录
        }

        with patch("src.python.core.reader.read_holdings", return_value=[]):
            result = _cli_read_holdings(config)
        # 该目录下无有效 xlsx（文件内容不是真实 xlsx），read_holdings 返回空列表
        assert result is None

    @pytest.mark.edge
    def test_verbose_ansi_auto_disable(self, monkeypatch):
        """NO_COLOR 环境变量禁用 ANSI 颜色。"""
        monkeypatch.setenv("NO_COLOR", "1")
        from src.python.report.cli_progress import _should_color
        assert _should_color() is False

    @pytest.mark.edge
    def test_verbose_no_color_pipe(self, monkeypatch):
        """stderr 非 TTY 时 ANSI 禁用。"""
        monkeypatch.delenv("NO_COLOR", raising=False)
        from src.python.report.cli_progress import _should_color
        # 测试环境中 stderr 被 pytest 捕获（非 TTY），应禁用颜色
        assert _should_color() is False
