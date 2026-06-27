"""东方财富行业/概念 Provider 单元测试。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.providers.eastmoney_industry import (
    fetch_industry_and_concepts,
    fetch_industry,
    fetch_concepts,
)

# ── 模拟数据 ──────────────────────────────────────────────────

_MOCK_SUCCESS_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": "电力设备",
        "f127": "BKxxxx",
        "f141": "CPO光模块,人工智能,新能源",
        "f140": "BK1000,BK1001,BK1002",
    }
}

_MOCK_NO_CONCEPT_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": "电力设备",
        "f127": "BKxxxx",
        "f141": "",
        "f140": "",
    }
}

_MOCK_NO_DATA_RESPONSE = {
    "data": None,
}

_MOCK_EMPTY_RESPONSE = {}

# ── Edge case 模拟数据 ──────────────────────────────────────────

_MOCK_CONCEPTS_IS_NUMBER_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": "电力设备",
        "f127": "BKxxxx",
        "f141": 0,
        "f140": 0,
    }
}

_MOCK_CONCEPTS_IS_NONE_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": "电力设备",
        "f127": "BKxxxx",
        "f141": None,
        "f140": None,
    }
}

_MOCK_CONCEPTS_IS_DASH_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": "电力设备",
        "f127": "BKxxxx",
        "f141": "-",
        "f140": "-",
    }
}

_MOCK_INDUSTRY_IS_DASH_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": "-",
        "f127": "-",
        "f141": "CPO光模块,人工智能,新能源",
        "f140": "BK1000,BK1001,BK1002",
    }
}

_MOCK_INDUSTRY_IS_NUMBER_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f128": 0,
        "f127": 0,
        "f141": "CPO光模块,人工智能,新能源",
        "f140": "BK1000,BK1001,BK1002",
    }
}


def _mock_httpx(text: str = "", error: type | None = None):
    """创建模拟 httpx.Client。

    Args:
        text: API 正常返回时的响应文本
        error: 不为 None 时，client.get() 抛出该异常
    """

    class MockResponse:
        def __init__(self):
            self.text = text
            self.status_code = 200

        def json(self):
            return json.loads(self.text)

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args, **kwargs):
            pass

        def get(self, url, *args, **kwargs):
            if error:
                raise error("mock timeout")
            return MockResponse()

    return MockClient


class TestFetchIndustryAndConcepts(unittest.TestCase):
    """测试 fetch_industry_and_concepts 主函数。"""

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_success_with_concepts(self, mock_client_cls):
        """正常返回：正确解析行业和概念。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "600900")
        self.assertEqual(result["industry"], "电力设备")
        self.assertEqual(result["industry_id"], "BKxxxx")
        self.assertEqual(result["concepts"], ["CPO光模块", "人工智能", "新能源"])
        self.assertEqual(result["concept_ids"], ["BK1000", "BK1001", "BK1002"])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_success_no_concepts(self, mock_client_cls):
        """API 返回空概念列表 → 正确返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_NO_CONCEPT_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力设备")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_no_data_field(self, mock_client_cls):
        """API 返回 data 为 None → 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_NO_DATA_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNone(result)

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_empty_response(self, mock_client_cls):
        """API 返回空对象 → 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_EMPTY_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNone(result)

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_timeout_returns_none(self, mock_client_cls):
        """API 超时异常 → 返回 None。"""
        import httpx
        mock_client_cls.side_effect = _mock_httpx(error=httpx.TimeoutException)
        result = fetch_industry_and_concepts("600900")
        self.assertIsNone(result)

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_with_fund_code(self, mock_client_cls):
        """基金代码也正常处理。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_industry_and_concepts("000961")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "000961")
        self.assertEqual(result["industry"], "电力设备")

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_field_is_number(self, mock_client_cls):
        """概念字段 API 返回数字 0 → 概念为空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_NUMBER_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力设备")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_field_is_none(self, mock_client_cls):
        """概念字段 API 返回 None → 概念为空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_NONE_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力设备")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_field_is_dash(self, mock_client_cls):
        """概念字段 API 返回 '-' → 概念为空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_DASH_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力设备")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_field_is_dash(self, mock_client_cls):
        """行业字段 API 返回 '-' → 行业/ID 均为空字符串。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_DASH_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["industry_id"], "")
        # 概念仍正常解析
        self.assertEqual(result["concepts"], ["CPO光模块", "人工智能", "新能源"])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_field_is_number(self, mock_client_cls):
        """行业字段 API 返回数字 0 → 行业/ID 均为空字符串。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_NUMBER_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["industry_id"], "")
        # 概念仍正常解析
        self.assertEqual(result["concepts"], ["CPO光模块", "人工智能", "新能源"])


class TestFetchIndustry(unittest.TestCase):
    """测试 fetch_industry 便捷接口。"""

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_found(self, mock_client_cls):
        """有行业数据时返回行业名称。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertEqual(result, "电力设备")

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_not_found(self, mock_client_cls):
        """无行业数据时返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_EMPTY_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertIsNone(result)

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_dash_returned(self, mock_client_cls):
        """行业字段为 '-' 时 fetch_industry 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_DASH_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertIsNone(result)

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_industry_number_returned(self, mock_client_cls):
        """行业字段为数字时 fetch_industry 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_NUMBER_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertIsNone(result)


class TestFetchConcepts(unittest.TestCase):
    """测试 fetch_concepts 便捷接口。"""

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_found(self, mock_client_cls):
        """有概念板块时返回列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, ["CPO光模块", "人工智能", "新能源"])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_empty(self, mock_client_cls):
        """无概念板块时返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_NO_CONCEPT_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, [])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_number(self, mock_client_cls):
        """概念字段为数字时 fetch_concepts 返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_NUMBER_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, [])

    @patch("src.providers.eastmoney_industry.httpx.Client")
    def test_concepts_dash(self, mock_client_cls):
        """概念字段为 '-' 时 fetch_concepts 返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_DASH_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
