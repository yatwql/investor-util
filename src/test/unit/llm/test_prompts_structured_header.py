"""结构化决策头提示词契约单元测试（开关 decision_header_parse，默认开启）。

覆盖：开关关闭时 expert_review 提示词**逐字节不变**（缓存指纹不受扰动）、
开启时追加「决策头：」契约行与规范词枚举、契约文本与解析器口径互相锁定、
生成器指纹后缀随开关换键。全部本地字符串，零网络零 LLM。

运行：
  pytest src/test/unit/llm/test_prompts_structured_header.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import reset_feature_flags, set_feature_enabled
from src.python.core import decision_header as dh

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


@pytest.fixture(autouse=True)
def _reset_flags():
    yield
    reset_feature_flags()


def _expert_review(**kwargs) -> str:
    from src.python.llm.prompts_action import _build_expert_review_prompt

    return _build_expert_review_prompt(
        100000.0,
        90000.0,
        10000.0,
        500.0,
        2,
        {"股票": 2},
        None,
        holdings_details=[{"name": "示例", "code": "600519", "cost": 100.0}],
        **kwargs,
    )


class TestPromptUnchangedWhenOff:
    """开关关闭 → 提示词逐字节与未加此项时一致（不扰动缓存指纹）。"""

    def test_default_omits_structured_header(self):
        assert dh.STRUCTURED_HEADER_MARKER not in _expert_review()

    def test_explicit_false_matches_default(self):
        assert _expert_review(enable_structured_header=False) == _expert_review()

    def test_extra_argument_does_not_shift_content(self):
        # 关闭分支不 append 任何内容 → 与未传该参数完全同串
        assert _expert_review(enable_structured_header=False) == _expert_review(enable_conditional=False)


class TestPromptContractWhenOn:
    """开关开启 → 追加契约段，位置在行动建议表之后。"""

    def test_marker_and_enumerations_present(self):
        text = _expert_review(enable_structured_header=True)
        assert dh.STRUCTURED_HEADER_MARKER in text
        for word, _direction in dh.CANONICAL_DECISION_WORDS:
            assert word in text
        for level, _ in dh.PRIORITY_LEVELS:
            assert level in text

    def test_contract_follows_action_table(self):
        text = _expert_review(enable_structured_header=True)
        assert text.index("### 操作建议") < text.index(dh.STRUCTURED_HEADER_MARKER)

    def test_contract_keeps_holdings_block_after(self):
        # 契约段插入后，「持仓明细」仍在末尾（不得被挤到契约之前）
        text = _expert_review(enable_structured_header=True)
        assert text.index(dh.STRUCTURED_HEADER_MARKER) < text.index("【持仓明细】")

    def test_contract_example_is_parsable(self):
        # 契约示例行必须能被解析器读回（文档与实现同源）
        text = _expert_review(enable_structured_header=True)
        header_line = next(line for line in text.splitlines() if line.startswith(dh.STRUCTURED_HEADER_MARKER))
        rows = dh.parse_structured_header(header_line)
        assert rows is not None and rows[0]["code"] == "600000"


class TestGeneratorFingerprintSuffix:
    """生成器指纹后缀随开关换键（预检键 = 读写键）。"""

    def test_suffix_off_is_empty(self):
        set_feature_enabled(dh.STRUCTURED_HEADER_FLAG, False)  # 转正后默认开，基准须显式关
        assert dh.structured_header_cache_suffix() == ""

    def test_suffix_on_changes_key(self):
        set_feature_enabled(dh.STRUCTURED_HEADER_FLAG, True)
        assert dh.structured_header_cache_suffix() != ""

    def test_generator_prompt_uses_flag(self):
        # generate_expert_review 的 _prompt 闭包随开关携带契约（避免读开关两处漂移）
        set_feature_enabled(dh.STRUCTURED_HEADER_FLAG, False)  # 转正后默认开，基准须显式关
        source = _expert_review(enable_structured_header=bool(dh.structured_header_cache_suffix()))
        assert dh.STRUCTURED_HEADER_MARKER not in source
        set_feature_enabled(dh.STRUCTURED_HEADER_FLAG, True)
        source_on = _expert_review(enable_structured_header=bool(dh.structured_header_cache_suffix()))
        assert dh.STRUCTURED_HEADER_MARKER in source_on
