"""HTTP 客户端工厂单元测试。

测试目标：
  - _should_verify — SSL_VERIFY 环境变量解析
  - make_http_client — 客户端创建、verify 参数合并

运行：
  pytest src/test/unit/core/test_http_client.py -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.python.core.http_client import _should_verify, make_http_client
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_core]




class TestShouldVerify(unittest.TestCase):
    """_should_verify 环境变量解析测试。"""

    @patch("src.python.core.http_client.os.getenv")
    def test_default_true(self, mock_getenv):
        """默认值：SSL_VERIFY 未设置 → True。"""
        mock_getenv.return_value = "true"
        self.assertTrue(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_explicit_true(self, mock_getenv):
        """显式设置 true → True。"""
        mock_getenv.return_value = "true"
        self.assertTrue(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_explicit_one(self, mock_getenv):
        """SSL_VERIFY=1 → True。"""
        mock_getenv.return_value = "1"
        self.assertTrue(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_explicit_yes(self, mock_getenv):
        """SSL_VERIFY=yes → True。"""
        mock_getenv.return_value = "yes"
        self.assertTrue(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_false(self, mock_getenv):
        """SSL_VERIFY=false → False。"""
        mock_getenv.return_value = "false"
        self.assertFalse(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_zero(self, mock_getenv):
        """SSL_VERIFY=0 → False。"""
        mock_getenv.return_value = "0"
        self.assertFalse(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_no(self, mock_getenv):
        """SSL_VERIFY=no → False。"""
        mock_getenv.return_value = "no"
        self.assertFalse(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_case_insensitive(self, mock_getenv):
        """大小写不敏感：True/TRUE/YES 均识别。"""
        for val in ("True", "TRUE", "YES", "Yes"):
            mock_getenv.return_value = val
            self.assertTrue(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_unknown_value_returns_false(self, mock_getenv):
        """未知值（不在 true/1/yes 中）→ False。"""
        mock_getenv.return_value = "maybe"
        self.assertFalse(_should_verify())

    @patch("src.python.core.http_client.os.getenv")
    def test_whitespace_stripped(self, mock_getenv):
        """前后空格自动去除。"""
        mock_getenv.return_value = "  true  "
        self.assertTrue(_should_verify())


class TestMakeHttpClient(unittest.TestCase):
    """make_http_client 集成测试。"""

    @patch("src.python.core.http_client.httpx.Client")
    @patch("src.python.core.http_client._SSL_VERIFY", True)
    def test_default_verify_true(self, mock_client_class):
        """未传 verify → 使用模块级 _SSL_VERIFY=True。"""
        make_http_client(timeout=30.0)
        _, kwargs = mock_client_class.call_args
        self.assertIs(kwargs["verify"], True)

    @patch("src.python.core.http_client.httpx.Client")
    @patch("src.python.core.http_client._SSL_VERIFY", False)
    def test_default_verify_false(self, mock_client_class):
        """未传 verify → 使用模块级 _SSL_VERIFY=False。"""
        make_http_client(timeout=30.0)
        _, kwargs = mock_client_class.call_args
        self.assertIs(kwargs["verify"], False)

    @patch("src.python.core.http_client.httpx.Client")
    @patch("src.python.core.http_client._SSL_VERIFY", True)
    def test_explicit_verify_overrides(self, mock_client_class):
        """显式传 verify=False 覆盖模块级 True。"""
        make_http_client(verify=False, timeout=30.0)
        _, kwargs = mock_client_class.call_args
        self.assertIs(kwargs["verify"], False)

    @patch("src.python.core.http_client.httpx.Client")
    def test_timeout_passed_through(self, mock_client_class):
        """timeout 参数透传给 httpx.Client。"""
        make_http_client(timeout=15.0)
        _, kwargs = mock_client_class.call_args
        self.assertEqual(kwargs["timeout"], 15.0)

    @patch("src.python.core.http_client.httpx.Client")
    def test_headers_passed_through(self, mock_client_class):
        """headers 参数透传。"""
        make_http_client(headers={"X-Test": "1"})
        _, kwargs = mock_client_class.call_args
        self.assertEqual(kwargs["headers"], {"X-Test": "1"})

    @patch("src.python.core.http_client.httpx.Client")
    def test_multiple_kwargs(self, mock_client_class):
        """多个参数同时传递。"""
        make_http_client(timeout=30.0, follow_redirects=True, headers={"X-T": "1"})
        _, kwargs = mock_client_class.call_args
        self.assertEqual(kwargs["timeout"], 30.0)
        self.assertTrue(kwargs["follow_redirects"])
        self.assertEqual(kwargs["headers"], {"X-T": "1"})

    def test_context_manager(self):
        """支持 with 语句（真实 httpx.Client）。"""
        with make_http_client(timeout=30.0) as client:
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)
