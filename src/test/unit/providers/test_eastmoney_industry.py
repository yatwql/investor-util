"""东方财富行业/概念 Provider 单元测试。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.python.providers.eastmoney_industry import (

    fetch_industry_and_concepts,
    fetch_industry,
    fetch_concepts,
    _secid,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_providers]


# ── 模拟数据 ──────────────────────────────────────────────────

# 新 API 字段映射:
#   f127 = 行业名称（如"电力"）  f129 = 概念名称列表（逗号分隔）
#   f198 = 行业 BK 代码（如"BK0428"）  f140 = 数值（不再含概念 ID）
#   f128 = 地域板块（如"北京板块"）

_MOCK_SUCCESS_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f127": "电力",
        "f128": "北京板块",
        "f129": "创投,参股银行,核能核电,风能,水利建设",
        "f198": "BK0428",
        "f140": 79323632.0,
    }
}

_MOCK_NO_CONCEPT_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f127": "电力",
        "f128": "北京板块",
        "f129": "",
        "f198": "BK0428",
        "f140": 79323632.0,
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
        "f127": "电力",
        "f128": "北京板块",
        "f129": 0,
        "f198": "BK0428",
        "f140": 79323632.0,
    }
}

_MOCK_CONCEPTS_IS_NONE_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f127": "电力",
        "f128": "北京板块",
        "f129": None,
        "f198": "BK0428",
        "f140": 79323632.0,
    }
}

_MOCK_CONCEPTS_IS_DASH_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f127": "电力",
        "f128": "北京板块",
        "f129": "-",
        "f198": "BK0428",
        "f140": 79323632.0,
    }
}

_MOCK_INDUSTRY_IS_DASH_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f127": "-",
        "f128": "北京板块",
        "f129": "创投,参股银行,核能核电,风能,水利建设",
        "f198": "",
        "f140": 79323632.0,
    }
}

_MOCK_INDUSTRY_IS_NUMBER_RESPONSE = {
    "data": {
        "f57": "600900",
        "f58": "长江电力",
        "f127": 0,
        "f128": "北京板块",
        "f129": "创投,参股银行,核能核电,风能,水利建设",
        "f198": 0,
        "f140": 79323632.0,
    }
}

_MOCK_ETF_NO_INDUSTRY_RESPONSE = {
    "data": {
        "f57": "518880",
        "f58": "黄金ETF华安",
        "f127": "",
        "f128": "",
        "f129": "",
        "f198": "",
        "f140": 25357952.0,
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


class TestSecid(unittest.TestCase):
    """测试 _secid 前缀规则。"""

    def test_shanghai_stock(self):
        """60xxxx → 1. 前缀。"""
        self.assertEqual(_secid("600900"), "1.600900")

    def test_shanghai_star(self):
        """68xxxx → 1. 前缀。"""
        self.assertEqual(_secid("688001"), "1.688001")

    def test_shanghai_etf(self):
        """51xxxx/56xxxx/58xxxx ETF → 1. 前缀。"""
        self.assertEqual(_secid("510050"), "1.510050")
        self.assertEqual(_secid("518880"), "1.518880")

    def test_shenzhen_main(self):
        """00xxxx → 0. 前缀。"""
        self.assertEqual(_secid("000001"), "0.000001")

    def test_shenzhen_gem(self):
        """30xxxx → 0. 前缀。"""
        self.assertEqual(_secid("300750"), "0.300750")

    def test_shenzhen_etf(self):
        """15xxxx/2xxxxx → 0. 前缀。"""
        self.assertEqual(_secid("159915"), "0.159915")


class TestFetchIndustryAndConcepts(unittest.TestCase):
    """测试 fetch_industry_and_concepts 主函数。"""

    def setUp(self):
        from src.python.provider_registry import get_registry
        get_registry().session_cache_clear("industry")
        get_registry().reset()

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_success_with_concepts(self, mock_client_cls):
        """正常返回：正确解析行业和概念。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "600900")
        self.assertEqual(result["industry"], "电力")
        self.assertEqual(result["industry_id"], "BK0428")
        self.assertEqual(result["concepts"], ["创投", "参股银行", "核能核电", "风能", "水利建设"])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_success_no_concepts(self, mock_client_cls):
        """API 返回空概念列表 → 正确返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_NO_CONCEPT_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_no_data_field(self, mock_client_cls):
        """API 返回 data 为 None → 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_NO_DATA_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_empty_response(self, mock_client_cls):
        """API 返回空对象 → 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_EMPTY_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_timeout_returns_none(self, mock_client_cls):
        """API 超时异常 → 返回 None。"""
        import httpx
        mock_client_cls.side_effect = _mock_httpx(error=httpx.TimeoutException)
        result = fetch_industry_and_concepts("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_timeout_triggers_registry_failure(self, mock_client_cls):
        """连续 3 次 API 超时 → registry 熔断打开。"""
        import httpx
        from src.python.provider_registry import get_registry
        reg = get_registry()
        reg.reset()
        mock_client_cls.side_effect = _mock_httpx(error=httpx.TimeoutException)
        # 熔断阈值 = 3 次失败；每次用不同 code 绕过会话级缓存
        for code in ("600900", "600905", "600919"):
            fetch_industry_and_concepts(code)
        self.assertTrue(reg.is_circuit_broken("eastmoney_industry"))
        # 熔断后请求直接跳过，不再调 API
        result = fetch_industry_and_concepts("600601")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_industry_with_fund_code(self, mock_client_cls):
        """基金代码也正常处理。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_industry_and_concepts("000961")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "000961")
        self.assertEqual(result["industry"], "电力")

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_field_is_number(self, mock_client_cls):
        """概念字段 API 返回数字 → 概念为空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_NUMBER_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_field_is_none(self, mock_client_cls):
        """概念字段 API 返回 None → 概念为空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_NONE_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_field_is_dash(self, mock_client_cls):
        """概念字段 API 返回 '-' → 概念为空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_DASH_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "电力")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
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
        self.assertEqual(result["concepts"], ["创投", "参股银行", "核能核电", "风能", "水利建设"])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_industry_field_is_number(self, mock_client_cls):
        """行业字段 API 返回数字 → 行业/ID 均为空字符串。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_NUMBER_RESPONSE)
        )
        result = fetch_industry_and_concepts("600900")
        self.assertIsNotNone(result)
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["industry_id"], "")
        # 概念仍正常解析
        self.assertEqual(result["concepts"], ["创投", "参股银行", "核能核电", "风能", "水利建设"])
        self.assertEqual(result["concept_ids"], [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_etf_no_industry(self, mock_client_cls):
        """ETF (518880 黄金ETF) 无行业/概念数据 → 正确返回空值。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_ETF_NO_INDUSTRY_RESPONSE)
        )
        result = fetch_industry_and_concepts("518880")
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "518880")
        self.assertEqual(result["industry"], "")
        self.assertEqual(result["industry_id"], "")
        self.assertEqual(result["concepts"], [])
        self.assertEqual(result["concept_ids"], [])


class TestFetchIndustry(unittest.TestCase):
    """测试 fetch_industry 便捷接口。"""

    def setUp(self):
        from src.python.provider_registry import get_registry
        get_registry().session_cache_clear("industry")

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_industry_found(self, mock_client_cls):
        """有行业数据时返回行业名称。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertEqual(result, "电力")

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_industry_not_found(self, mock_client_cls):
        """无行业数据时返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_EMPTY_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_industry_dash_returned(self, mock_client_cls):
        """行业字段为 '-' 时 fetch_industry 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_DASH_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertIsNone(result)

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_industry_number_returned(self, mock_client_cls):
        """行业字段为数字时 fetch_industry 返回 None。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_INDUSTRY_IS_NUMBER_RESPONSE)
        )
        result = fetch_industry("600900")
        self.assertIsNone(result)


class TestFetchConcepts(unittest.TestCase):
    """测试 fetch_concepts 便捷接口。"""

    def setUp(self):
        from src.python.provider_registry import get_registry
        get_registry().session_cache_clear("industry")

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_found(self, mock_client_cls):
        """有概念板块时返回列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_SUCCESS_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, ["创投", "参股银行", "核能核电", "风能", "水利建设"])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_empty(self, mock_client_cls):
        """无概念板块时返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_NO_CONCEPT_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_number(self, mock_client_cls):
        """概念字段为数字时 fetch_concepts 返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_NUMBER_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_dash(self, mock_client_cls):
        """概念字段为 '-' 时 fetch_concepts 返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_CONCEPTS_IS_DASH_RESPONSE)
        )
        result = fetch_concepts("600900")
        self.assertEqual(result, [])

    @patch("src.python.providers.eastmoney_industry.httpx.Client")
    def test_concepts_etf_empty(self, mock_client_cls):
        """ETF 无概念时返回空列表。"""
        mock_client_cls.side_effect = _mock_httpx(
            json.dumps(_MOCK_ETF_NO_INDUSTRY_RESPONSE)
        )
        result = fetch_concepts("518880")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
