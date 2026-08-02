"""辩论模式边缘场景测试 — C12 合规，必须与普通测试文件分离。

运行：
  cd D:/codebase/zoo/investor-util
  pytest src/test/unit/llm/test_debate_edge.py -v
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.edge]

# 最小持仓数据
_MIN_HOLDINGS = [
    {
        "name": "测试A",
        "code": "000001",
        "market_value": 100000,
        "cost": 80000,
        "profit": 20000,
        "profit_rate": 0.25,
        "change_pct": 1.5,
        "nav_date": "2026-07-20",
        "source_api": "mock",
    },
]

_BOND_HOLDINGS = [
    {
        "name": "国债ETF",
        "code": "511010",
        "market_value": 100000,
        "cost": 95000,
        "profit": 5000,
        "profit_rate": 0.0526,
        "change_pct": 0.1,
        "nav_date": "2026-07-20",
        "source_api": "mock",
    },
]

_HK_HOLDINGS = [
    {
        "name": "腾讯控股",
        "code": "00700",
        "market_value": 100000,
        "cost": 80000,
        "profit": 20000,
        "profit_rate": 0.25,
        "change_pct": 2.0,
        "nav_date": "2026-07-20",
        "source_api": "mock",
    },
    {
        "name": "Apple",
        "code": "AAPL",
        "market_value": 50000,
        "cost": 45000,
        "profit": 5000,
        "profit_rate": 0.1111,
        "change_pct": 0.5,
        "nav_date": "2026-07-20",
        "source_api": "mock",
    },
]

_CONTEXT = {
    "holdings_details": _MIN_HOLDINGS,
    "total_mv": 100000,
    "total_cost": 80000,
    "total_profit": 20000,
    "total_today_profit": 1000,
    "categories": {"股票": 1, "基金": 0, "债券": 0},
    "penetrated_assets": [],
    "holdings_count": 1,
}


def _mock_llm_result(text: str = "mock分析结果") -> tuple[str | None, bool]:
    """模拟 generate_llm_module 返回 (text, cached)。"""
    return (text, False)


def _mock_no_result() -> tuple[None, bool]:
    """模拟 generate_llm_module 返回 (None, False)。"""
    return (None, False)


@pytest.mark.edge
class TestDebateEdgeAllProvidersUnavailable(unittest.TestCase):
    """所有 LLM Provider 全不可用 → 降级普通模式。"""

    @patch("src.python.llm.generators.generate_llm_module", return_value=(None, False))
    def test_pro_failure_returns_none(self, mock_gen):
        """pro 失败（模拟 Provider 不可用）→ 返回 (None, None, None)。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertIsNone(result[2])


@pytest.mark.edge
class TestDebateEdgeSingleHolding(unittest.TestCase):
    """仅有 1 个持仓品种 → 正反辩论/集中度问答正常。"""

    @patch(
        "src.python.llm.generators.generate_llm_module",
        side_effect=[
            _mock_llm_result("pro分析正面持有理由充足"),
            _mock_llm_result("con分析注意集中度风险"),
            _mock_llm_result("综合分析"),
        ],
    )
    def test_single_holding_pro_con_synthesis(self, mock_gen):
        """单个品种辩论正常生成。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertIsNotNone(result[2])
        self.assertIn("pro", result[0])


@pytest.mark.edge
class TestDebateEdgeBonds(unittest.TestCase):
    """持仓全部为债券 → 黑脸诚实说明无负面理由。"""

    @patch(
        "src.python.llm.generators.generate_llm_module",
        side_effect=[
            _mock_llm_result("债券配置合理持有"),
            _mock_llm_result("债券风险较低无负面理由"),
            _mock_llm_result("综合：维持债券配置"),
        ],
    )
    def test_all_bonds(self, mock_gen):
        """全债券持仓辩论正常。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            95000,
            5000,
            100,
            1,
            {"债券": 1},
            [],
            holdings_details=_BOND_HOLDINGS,
        )
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertIsNotNone(result[2])


@pytest.mark.edge
class TestDebateEdgePenetrateEmpty(unittest.TestCase):
    """penetrate_data 为空 → 正反辩论/条件推理/集中度问答均正常。"""

    @patch(
        "src.python.llm.generators.generate_llm_module",
        side_effect=[
            _mock_llm_result("pro正面分析"),
            _mock_llm_result("con负面分析"),
            _mock_llm_result("综合分析"),
        ],
    )
    def test_penetrate_empty(self, mock_gen):
        """穿透数据为空时辩论正常。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertIsNotNone(result[2])


@pytest.mark.edge
class TestDebateEdgeProSuccessConFailure(unittest.TestCase):
    """正反辩论 pro 成功但 con 失败 → 回退普通模式。"""

    @patch(
        "src.python.llm.generators.generate_llm_module",
        side_effect=[
            _mock_llm_result("pro正面分析"),
            (None, False),  # con 失败
        ],
    )
    def test_pro_success_con_failure(self, mock_gen):
        """pro 成功 con 失败 → (None, None, None)。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        self.assertIsNone(result[0])
        self.assertIsNone(result[1])
        self.assertIsNone(result[2])


@pytest.mark.edge
class TestDebateEdgeSynthesisTimeout(unittest.TestCase):
    """正反辩论全部成功但 synthesis 超时 → 返回 pro+con 拼接。"""

    @patch(
        "src.python.llm.generators.generate_llm_module",
        side_effect=[
            _mock_llm_result("pro正面持有理由分析结果"),
            _mock_llm_result("con负面卖出理由分析结果"),
            (None, False),  # synthesis 超时/失败
        ],
    )
    def test_synthesis_timeout_returns_pro_con(self, mock_gen):
        """synthesis 失败 → (pro, con, None)。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertIsNone(result[2])


@pytest.mark.edge
class TestDebateEdgeFilterHallucinatedCodes(unittest.TestCase):
    """_filter_hallucinated_codes 过滤虚构代码且不误伤合法品种。"""

    def test_filter_removes_hallucinated(self):
        """含字母的虚构代码所在行被移除，合法代码所在行保留。"""
        from src.python.llm.generators import _filter_hallucinated_codes

        # 虚构代码和合法代码在不同行（过滤器移除整行）
        text = "建议关注000001和00700\n虚构品种ZZZZZ需警惕"
        valid_codes = {"000001", "00700"}
        result = _filter_hallucinated_codes(text, valid_codes)
        self.assertIn("000001", result)
        self.assertNotIn("ZZZZZ", result)

    def test_filter_keeps_legit_codes(self):
        """港股 5 位代码和美股字母代码不被误伤。"""
        from src.python.llm.generators import _filter_hallucinated_codes

        text = "腾讯控股00700和AAPL表现良好"
        valid_codes = {"00700", "AAPL"}
        result = _filter_hallucinated_codes(text, valid_codes)
        self.assertIn("00700", result)
        self.assertIn("AAPL", result)

    def test_filter_all_hallucinated_returns_empty(self):
        """全部虚构行被移除 → 返回空字符串。"""
        from src.python.llm.generators import _filter_hallucinated_codes

        # 使用含字母的虚构代码（纯数字会被忽略不过滤）
        text = "建议关注虚构品种ZZZZZ\n还有XXXXX"
        valid_codes = {"000001"}
        result = _filter_hallucinated_codes(text, valid_codes)
        # 所有行都有虚构代码，返回空字符串
        self.assertEqual(result, "")

    def test_filter_single_line_html_keeps_other_sentences(self):
        """单行 HTML（markdown_to_html 后无换行）中仅删除含虚构代码的句子。

        单行拼接字符串须按句切分后删除——仅删除含虚构代码的句子，
        不得因单个虚构 token 清空整段内容。
        """
        from src.python.llm.generators import _filter_hallucinated_codes

        text = (
            "【白脸观点】组合整体风险可控，600519 贵州茅台表现良好。虚构品种X1234需警惕，建议减持。其余品种现金流稳健。"
        )
        result = _filter_hallucinated_codes(text, {"600519"})
        self.assertIn("600519", result)
        self.assertIn("组合整体", result)
        self.assertIn("现金流", result)
        self.assertNotIn("X1234", result)
        self.assertNotEqual(result, "", "单行文本含虚构代码时不应整段清空")


@pytest.mark.edge
class TestDebateEdgeConfigMissingSection(unittest.TestCase):
    """features.json flag=true 但配置段缺失 → 使用全缺省配置。"""

    @patch("src.python.config._core.get_llm_config")
    @patch(
        "src.python.llm.generators.generate_llm_module",
        side_effect=[
            _mock_llm_result("pro分析"),
            _mock_llm_result("con分析"),
            _mock_llm_result("综合分析"),
        ],
    )
    def test_missing_config_section(self, mock_gen, mock_config):
        """配置段缺失时使用缺省值。"""
        mock_config.return_value = {}  # 空配置，无 debate 段

        from src.python.llm.generators import generate_debate_procon

        # 不应抛出 KeyError
        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        # 缺省配置下 defense 应正常生成
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])


@pytest.mark.edge
class TestDebateEdgeProviderChainFailure(unittest.TestCase):
    """Provider 全链不可用 → debate 模式跳过。"""

    @patch("src.python.llm.generators.generate_llm_module", return_value=(None, False))
    def test_provider_failure_all_none(self, mock_gen):
        """Provider 全不可用时 debate 返回 None。"""
        from src.python.llm.generators import generate_debate_procon

        result = generate_debate_procon(
            100000,
            80000,
            20000,
            1000,
            1,
            {"股票": 1},
            [],
            holdings_details=_MIN_HOLDINGS,
        )
        self.assertEqual(result, (None, None, None))
