"""决策词归一解析单元测试（语义名 decision_header / decision_word）。

覆盖：规范词/扩展词整格匹配、标签优先于裸词、长词优先、否定守卫（紧邻否定字 +
同子句劝阻短语）、二义不猜、子句边界、优先级归一、结构化决策头逐字段校验与
缓存后缀开关。全部纯字符串运算，零网络零 LLM。

运行：
  pytest src/test/unit/core/test_decision_header.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import reset_feature_flags, set_feature_enabled
from src.python.core import decision_ledger as dl
from src.python.core import decision_header as dh

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


@pytest.fixture(autouse=True)
def _reset_flags():
    yield
    reset_feature_flags()


class TestParseDecisionWordCanonical:
    """规范词三值枚举（提示词契约固定）整格精确匹配。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("减仓", dl.DIRECTION_SHORT),
            ("加仓", dl.DIRECTION_LONG),
            ("持有", dl.DIRECTION_FLAT),
        ],
    )
    def test_exact_canonical_word(self, text, expected):
        assert dh.parse_decision_word(text) == expected

    def test_whitespace_and_marks_ignored(self):
        # 整格匹配前剥离空白/emoji/符号
        assert dh.parse_decision_word(" 减仓 ") == dl.DIRECTION_SHORT
        assert dh.parse_decision_word("🔴减仓") == dl.DIRECTION_SHORT


class TestParseDecisionWordExtended:
    """扩展词（模型措辞漂移容忍，语义单向无歧义）。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("清仓", dl.DIRECTION_SHORT),
            ("减持", dl.DIRECTION_SHORT),
            ("卖出", dl.DIRECTION_SHORT),
            ("止损", dl.DIRECTION_SHORT),
            ("增持", dl.DIRECTION_LONG),
            ("买入", dl.DIRECTION_LONG),
            ("建仓", dl.DIRECTION_LONG),
            ("观望", dl.DIRECTION_FLAT),
        ],
    )
    def test_exact_extended_word(self, text, expected):
        assert dh.parse_decision_word(text) == expected

    @pytest.mark.parametrize("text", ["止盈", "调仓", "保持关注", "再平衡"])
    def test_ambiguous_word_not_in_vocabulary(self, text):
        # 方向二义词刻意不收：宁可判不出（None），不可判错
        assert dh.parse_decision_word(text) is None


class TestLabelFirstOverBareWord:
    """标签优先于裸词：整格即词优先，未命中才降级全文扫描。"""

    def test_whole_cell_exact_wins(self):
        assert dh.parse_decision_word("持有") == dl.DIRECTION_FLAT

    def test_embedded_word_scanned(self):
        # 模型写成「加仓（价值修复）」→ 整格未命中 → 扫描命中加仓
        assert dh.parse_decision_word("加仓（价值修复）") == dl.DIRECTION_LONG

    def test_allow_scan_false_rejects_embedded(self):
        # 严格「整格即词」场景（结构化头字段）不允许扫描
        assert dh.parse_decision_word("加仓（价值修复）", allow_scan=False) is None
        assert dh.parse_decision_word("加仓", allow_scan=False) == dl.DIRECTION_LONG

    def test_longest_word_first(self):
        # 长词优先：清仓/减持 不被更短的 仓/持 劫持
        assert dh.parse_decision_word("清仓") == dl.DIRECTION_SHORT
        assert dh.parse_decision_word("减持") == dl.DIRECTION_SHORT


class TestNegationGuard:
    """否定守卫：紧邻否定字或同子句劝阻短语 → 判未命中。"""

    @pytest.mark.parametrize(
        "text",
        [
            "不建议加仓",
            "不宜增持",
            "暂不买入",
            "暂缓加仓",
            "无需减仓",
            "不必买入",
            "不用清仓",
            "勿减仓",
            "不建仓",
        ],
    )
    def test_negated_phrases_return_none(self, text):
        assert dh.parse_decision_word(text) is None

    def test_clause_boundary_limits_guard(self):
        # 劝阻短语只在本子句内生效：前句「不建议加仓」不影响后句「减仓」
        assert dh.parse_decision_word("不建议加仓，建议减仓") == dl.DIRECTION_SHORT

    def test_non_negation_word_not_killed(self):
        # 「不断加仓」的「不」不构成否定 → 仍判加仓
        assert dh.parse_decision_word("不断加仓") == dl.DIRECTION_LONG

    def test_trailing_qualifier_does_not_negate(self):
        # 守卫只作用于决策词**左侧**：后置限定语修饰的是别的动作，不改方向
        assert dh.parse_decision_word("建议加仓不必追高") == dl.DIRECTION_LONG


class TestAmbiguityNotGuessed:
    """二义不猜：全文扫描命中多个不同方向 → None（不做「取第一个」）。"""

    def test_two_directions_return_none(self):
        assert dh.parse_decision_word("加仓或减仓") is None

    def test_two_directions_across_clauses_return_none(self):
        assert dh.parse_decision_word("先减仓，后加仓") is None

    def test_same_direction_twice_is_unambiguous(self):
        assert dh.parse_decision_word("减仓，同时清仓") == dl.DIRECTION_SHORT


class TestEmptyAndNonDecisionInput:
    """空串/None/纯符号 → None（无默认值兜底）。"""

    @pytest.mark.parametrize("text", [None, "", "   ", "🔴🟡🟢", "——", "|"])
    def test_no_default_fallback(self, text):
        assert dh.parse_decision_word(text) is None


class TestParsePriority:
    """优先级归一（LLM 侧 magnitude 即优先级强度）。"""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("高", "high"), ("🔴 高", "high"), ("中", "mid"), ("🟡 中", "mid"), ("低", "low"), ("🟢 低", "low")],
    )
    def test_recognized_levels(self, text, expected):
        assert dh.parse_priority(text) == expected

    @pytest.mark.parametrize("text", [None, "", "未知等级", "--"])
    def test_unrecognized_falls_back_to_mid(self, text):
        # 优先级无「判错污染账本」风险，保留默认值
        assert dh.parse_priority(text) == dh.PRIORITY_DEFAULT


class TestExtractCode:
    """6 位代码抽取（前后非数字，兼容交易所前缀）。"""

    def test_plain_code(self):
        assert dh.extract_code("561910 招商中证电池主题ETF") == "561910"

    def test_exchange_prefixed_code(self):
        assert dh.extract_code("sh600000") == "600000"

    def test_no_code_returns_none(self):
        assert dh.extract_code("招商中证电池主题ETF") is None
        assert dh.extract_code(None) is None

    def test_longer_digit_run_not_matched(self):
        assert dh.extract_code("1234567") is None


class TestParseStructuredHeader:
    """结构化决策头解析（逐字段归一校验）。"""

    def _header(self, payload: str) -> str:
        return dh.STRUCTURED_HEADER_MARKER + payload

    def test_valid_header_parsed(self):
        text = self._header('{"decisions":[{"code":"561910","action":"减仓","priority":"高"}]}')
        rows = dh.parse_structured_header(text)
        assert rows == [{"code": "561910", "direction": dl.DIRECTION_SHORT, "magnitude": "high"}]

    def test_missing_marker_returns_none(self):
        assert dh.parse_structured_header("没有任何标记的内容") is None

    def test_invalid_json_returns_none(self):
        assert dh.parse_structured_header(self._header("{不是合法 JSON")) is None

    def test_empty_decisions_returns_none(self):
        assert dh.parse_structured_header(self._header('{"decisions":[]}')) is None

    def test_invalid_action_dropped(self):
        # action 不能归一为方向 → 丢弃该条（不做原样透传）
        text = self._header('{"decisions":[{"code":"561910","action":"可能减仓","priority":"高"}]}')
        assert dh.parse_structured_header(text) is None

    def test_malformed_item_dropped_others_kept(self):
        # 单条畸形只丢该条，不丢整批
        text = self._header(
            '{"decisions":[{"code":"bad","action":"减仓"},{"code":"600900","action":"加仓","priority":"中"}]}'
        )
        rows = dh.parse_structured_header(text)
        assert rows == [{"code": "600900", "direction": dl.DIRECTION_LONG, "magnitude": "mid"}]

    def test_html_wrapped_header_parsed(self):
        html = '<p>决策头：{"decisions":[{"code":"600900","action":"加仓","priority":"低"}]}</p>'
        rows = dh.parse_structured_header(html)
        assert rows is not None and rows[0]["code"] == "600900"


class TestStructuredHeaderCacheSuffix:
    """缓存指纹后缀：开关关 → 空（不误伤旧缓存）；开 → 固定后缀换键。"""

    def test_flag_off_returns_empty(self):
        set_feature_enabled(dh.STRUCTURED_HEADER_FLAG, False)  # 转正后默认开，基准须显式关
        assert dh.structured_header_cache_suffix() == ""

    def test_flag_on_returns_suffix(self):
        set_feature_enabled(dh.STRUCTURED_HEADER_FLAG, True)
        assert dh.structured_header_cache_suffix() == "_dh"


class TestInstructionContractLocksParser:
    """提示词契约与解析器互相锁定（口径漂移即失败）。"""

    def test_instruction_mentions_all_canonical_words(self):
        text = dh.build_structured_header_instruction()
        for word, _direction in dh.CANONICAL_DECISION_WORDS:
            assert word in text

    def test_instruction_round_trip(self):
        # 契约示例行必须能被解析器读回（同一条决策头往返）
        body = ",".join(
            f'{{"code":"600000","action":"{word}","priority":"高"}}' for word, _ in dh.CANONICAL_DECISION_WORDS
        )
        rows = dh.parse_structured_header(dh.STRUCTURED_HEADER_MARKER + f'{{"decisions":[{body}]}}')
        assert rows is not None
        assert {r["direction"] for r in rows} == {dl.DIRECTION_SHORT, dl.DIRECTION_LONG, dl.DIRECTION_FLAT}


class TestStripMarks:
    """文本规整（去 HTML/装饰，保留子句分隔符）。"""

    def test_html_and_entity_stripped(self):
        assert dh.strip_marks("<p>加仓&amp;持有</p>") == "加仓持有"

    def test_clause_separators_kept(self):
        assert "，" in dh.strip_marks("减仓，观望")

    def test_none_and_empty(self):
        assert dh.strip_marks(None) == ""
        assert dh.strip_marks("") == ""
