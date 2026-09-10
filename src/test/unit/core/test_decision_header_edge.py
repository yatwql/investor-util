"""决策词归一解析 — 边缘/畸形输入矩阵（语义名 decision_header）。

覆盖：裸方向词嵌长句、词表词作子串出现、emoji 与全角标点包裹、HTML 片段、超长
文本、纯标点、嵌套/重复否定、结构化决策头畸形载荷矩阵、代码形态边界。
全部纯字符串运算，零网络零 LLM。

运行：
  pytest src/test/unit/core/test_decision_header_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import reset_feature_flags
from src.python.core import decision_ledger as dl
from src.python.core import decision_header as dh

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


@pytest.fixture(autouse=True)
def _reset_flags():
    yield
    reset_feature_flags()


class TestBareWordEmbeddedInSentence:
    """裸方向词嵌在长句中（表格单元格之外的自由文本形态）。"""

    def test_word_inside_long_sentence(self):
        text = "综合考虑当前估值与行业景气度，我们对长江电力维持持有评级，等待更好的价格。"
        assert dh.parse_decision_word(text) == dl.DIRECTION_FLAT

    def test_multi_sentence_same_direction(self):
        text = "基本面走弱。建议减仓。同时可考虑清仓以规避回撤风险。"
        assert dh.parse_decision_word(text) == dl.DIRECTION_SHORT


class TestVocabularyWordAsSubstring:
    """词表词作为更长词的子串出现（子串包含时代的高危误判面）。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("加减仓位需谨慎", None),  # 复合短语「加减仓」，不表达任一方向
            ("增减持仓比例", None),  # 复合短语「增减持」
            ("不再持有该品种", None),  # 「不再」劝阻前缀
            ("调减仓位至 5%", dl.DIRECTION_SHORT),  # 「调减」是真实减仓语义，非复合歧义
            ("长期持有型基金", dl.DIRECTION_FLAT),  # 「持有」独立成词 → 合法命中
        ],
    )
    def test_substring_forms(self, text, expected):
        assert dh.parse_decision_word(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("坚持持有", dl.DIRECTION_FLAT),  # 「持」作左邻字不得误杀
            ("逢低买入", dl.DIRECTION_LONG),
            ("逢高减持", dl.DIRECTION_SHORT),
            ("立即止损", dl.DIRECTION_SHORT),
            ("可以清仓", dl.DIRECTION_SHORT),
            ("建议观望", dl.DIRECTION_FLAT),
            ("分批建仓", dl.DIRECTION_LONG),
        ],
    )
    def test_normal_phrases_not_killed_by_boundary(self, text, expected):
        # 复合词左边界只收「加减增」，不得波及正常表述（误杀面回归）
        assert dh.parse_decision_word(text) == expected


class TestDecorationAndPunctuation:
    """emoji / 全角标点 / HTML 包裹。"""  # noqa: D400

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("🔴 高：减仓", dl.DIRECTION_SHORT),
            ("【加仓】", dl.DIRECTION_LONG),
            ("（持有）", dl.DIRECTION_FLAT),
            ("－减仓－", dl.DIRECTION_SHORT),
            ("<p>减仓</p>", dl.DIRECTION_SHORT),
            ("<span>加仓&nbsp;</span>", dl.DIRECTION_LONG),
            ("**减仓**", dl.DIRECTION_SHORT),
        ],
    )
    def test_decorated_forms(self, text, expected):
        assert dh.parse_decision_word(text) == expected

    @pytest.mark.parametrize("text", ["。；、，", ".........", "？！", "|||", "   \t\n  "])
    def test_punctuation_only(self, text):
        assert dh.parse_decision_word(text) is None


class TestLongText:
    """超长文本（不因规模退化或误判）。"""

    def test_very_long_text_single_direction(self):
        text = "前置说明。" * 500 + "结论：减仓。" + "后置解释。" * 500
        assert dh.parse_decision_word(text) == dl.DIRECTION_SHORT

    def test_very_long_text_no_decision_word(self):
        text = "行业景气度分析。" * 1000
        assert dh.parse_decision_word(text) is None


class TestNestedNegation:
    """嵌套/重复否定（守卫不得被绕过）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "不建议现在加仓",
            "暂不急于减仓",
            "无需立即清仓",
            "不宜贸然增持",
            "不必急于买入",
        ],
    )
    def test_prefix_with_adverb_between(self, text):
        assert dh.parse_decision_word(text) is None

    def test_double_negation_still_guarded(self):
        # 「不建议不建仓」→ 含劝阻短语 → 判未命中（不猜双重否定的净语义）
        assert dh.parse_decision_word("不建议不建仓") is None


class TestStructuredHeaderMalformedPayloads:
    """结构化决策头畸形载荷矩阵。"""

    def _header(self, payload: str) -> str:
        return dh.STRUCTURED_HEADER_MARKER + payload

    @pytest.mark.parametrize(
        "payload",
        [
            "",
            "{}",
            "null",
            "[]",
            '{"decisions":"not-a-list"}',
            '{"decisions":null}',
            '{"other":[]}',
            '{"decisions":[1,2,3]}',
            '{"decisions":[{"action":"减仓"}]}',  # 无 code
            '{"decisions":[{"code":"561910"}]}',  # 无 action
        ],
    )
    def test_malformed_payload_returns_none(self, payload):
        assert dh.parse_structured_header(self._header(payload)) is None

    def test_header_without_json_braces(self):
        assert dh.parse_structured_header(self._header("减仓")) is None

    def test_multiple_headers_uses_first(self):
        text = self._header('{"decisions":[{"code":"561910","action":"减仓"}]}') + self._header(
            '{"decisions":[{"code":"561910","action":"加仓"}]}'
        )
        rows = dh.parse_structured_header(text)
        assert rows is not None and rows[0]["direction"] == dl.DIRECTION_SHORT

    def test_all_items_invalid_returns_none(self):
        text = self._header('{"decisions":[{"code":"x","action":"y"},{"code":"561910","action":"止盈"}]}')
        assert dh.parse_structured_header(text) is None

    @pytest.mark.parametrize("text", [None, "", "决策头：", "决策头：\n"])
    def test_empty_text_variants(self, text):
        assert dh.parse_structured_header(text) is None


class TestExtractCodeBoundaries:
    """代码形态边界。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("600000", "600000"),
            ("sh600000 浦发银行", "600000"),
            ("600000.SH", "600000"),
            ("6000001", None),  # 7 位数字串不取
            ("1600000", None),
            ("60000", None),  # 5 位
            ("abc", None),
        ],
    )
    def test_code_shapes(self, text, expected):
        assert dh.extract_code(text) == expected


class TestParsePriorityBoundaries:
    """优先级单元格边界。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("优先级：高", "high"),
            ("[中]", "mid"),
            ("（低）", "low"),
            ("HIGH", "mid"),  # 英文不识别 → 默认中
        ],
    )
    def test_priority_shapes(self, text, expected):
        assert dh.parse_priority(text) == expected
