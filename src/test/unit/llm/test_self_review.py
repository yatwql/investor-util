"""生成后自检模块单元测试。

测试目标：
  - 开关门控：关闭时零 LLM 调用（不是「调用了但丢弃」）
  - 无有效产出时跳过并登记原因
  - 产出后写载体 + 固定尾注（非质量保证）确定性补全
  - 调用异常/空产出 → 主内容不受影响（返回 False，不抛出）
  - 注册纪律：注册表中存在，但**不**出现在编排并行模块表（防注册漂移）
  - 指纹内容寻址：产出变化 → 指纹变化；产出相同 → 指纹相同

运行：
  pytest src/test/unit/llm/test_self_review.py -v
"""

from __future__ import annotations

import pytest

from src.python.core.registry import get_llm_module_names
from src.python.llm.module_fingerprint import self_review_fingerprint
from src.python.llm.self_review import (
    NON_GUARANTEE_NOTE,
    SELF_REVIEW_MODULE_KEY,
    ensure_non_guarantee_note,
    get_self_review_block,
    reset_self_review,
    run_self_review,
    set_self_review_block,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]

_OUTPUTS = {"global_macro": "<p>宏观分析正文</p>", "expert_review": "<p>智囊团正文</p>"}


@pytest.fixture(autouse=True)
def _clean_carrier():
    reset_self_review()
    yield
    reset_self_review()


def _llm_config(enabled: bool, **extra) -> dict:
    return {"enabled_llm": {SELF_REVIEW_MODULE_KEY: enabled}, **extra}


# ── 开关门控：关闭时零调用 ─────────────────────────────────────


def test_disabled_makes_no_llm_call(monkeypatch):
    """开关关闭 → 不产生任何生成调用（以调用计数断言，而非只看返回值）。"""
    called = []

    def _boom(*a, **k):
        called.append(1)
        raise AssertionError("开关关闭时不得调用生成器")

    monkeypatch.setattr("src.python.llm.generators.generate_self_review", _boom)

    assert run_self_review(_OUTPUTS, None, None, _llm_config(False)) is False
    assert called == []
    assert get_self_review_block() is None


def test_enabled_but_no_upstream_output_skips_without_call(monkeypatch):
    """上游全失败/占位 → 无可复核内容，不调用生成器，并登记跳过原因。"""
    called = []

    def _boom(*a, **k):
        called.append(1)
        raise AssertionError("无有效内容时不得调用生成器")

    monkeypatch.setattr("src.python.llm.generators.generate_self_review", _boom)

    assert run_self_review({"global_macro": None, "expert_review": "   "}, None, None, _llm_config(True)) is False
    assert called == []


def test_enabled_with_output_produces_block(monkeypatch):
    """开关开启且上游有产出 → 调用生成器并把结果写入载体。"""
    monkeypatch.setattr(
        "src.python.llm.generators.generate_self_review",
        lambda *a, **k: ("<p>【自检清单】未发现矛盾</p>", False),
    )

    assert run_self_review(_OUTPUTS, [], [], _llm_config(True)) is True
    block = get_self_review_block()
    assert block is not None
    assert "【自检清单】" in block


# ── 固定尾注（防虚假信心）─────────────────────────────────────


def test_generated_block_always_carries_non_guarantee_note(monkeypatch):
    """模型未输出尾注时由代码确定性补上——「自检通过」不得被读作质量背书。"""
    monkeypatch.setattr(
        "src.python.llm.generators.generate_self_review",
        lambda *a, **k: ("<p>【自检清单】一切正常</p>", False),
    )
    run_self_review(_OUTPUTS, [], [], _llm_config(True))
    assert NON_GUARANTEE_NOTE in get_self_review_block()


def test_ensure_note_is_idempotent():
    once = ensure_non_guarantee_note("<p>x</p>")
    assert ensure_non_guarantee_note(once) == once
    assert once.count(NON_GUARANTEE_NOTE) == 1


def test_ensure_note_passes_through_empty():
    assert ensure_non_guarantee_note("") == ""


# ── 失败隔离 ──────────────────────────────────────────────────


def test_generator_exception_does_not_propagate(monkeypatch):
    """生成器抛异常 → 返回 False 且不抛出，主内容不受影响。"""

    def _raise(*a, **k):
        raise RuntimeError("LLM 调用失败")

    monkeypatch.setattr("src.python.llm.generators.generate_self_review", _raise)

    assert run_self_review(_OUTPUTS, [], [], _llm_config(True)) is False
    assert get_self_review_block() is None


def test_empty_result_is_not_written_to_carrier(monkeypatch):
    monkeypatch.setattr("src.python.llm.generators.generate_self_review", lambda *a, **k: (None, False))
    assert run_self_review(_OUTPUTS, [], [], _llm_config(True)) is False
    assert get_self_review_block() is None


# ── 载体语义 ──────────────────────────────────────────────────


def test_set_none_clears_carrier():
    set_self_review_block("<p>x</p>")
    set_self_review_block(None)
    assert get_self_review_block() is None


def test_set_empty_string_treated_as_no_content():
    set_self_review_block("")
    assert get_self_review_block() is None


# ── 注册纪律（LLM 模块注册）─────────────────────────────────────────────


def test_module_registered_in_registry():
    """在模块注册表中登记 → 显示名/缓存前缀/TTL/用量统计/失败载体自动获得。"""
    assert SELF_REVIEW_MODULE_KEY in get_llm_module_names()


def test_module_not_in_parallel_dispatch_table():
    """**不得**出现在编排并行模块表：其输入是其余模块产出，必须串行在它们之后。

    该断言是「防注册漂移」的锁：若后续维护者按「注册即编排」把它加进
    ``_build_module_fns``，本用例即变红（模块注册纪律要求移除无独立调度语义的注册分支）。
    """
    from src.python.llm._llm_dispatch import _build_module_fns

    fns = _build_module_fns(
        a_indices={},
        us_indices={},
        total_mv=0.0,
        total_cost=0.0,
        total_profit=0.0,
        total_today_profit=0.0,
        holdings_count=0,
        categories={},
        penetrated_assets=None,
        holdings_details=None,
        sector_flow=None,
        force=False,
    )
    assert SELF_REVIEW_MODULE_KEY not in fns


# ── 指纹内容寻址 ──────────────────────────────────────────────


def test_fingerprint_changes_when_output_changes():
    base = self_review_fingerprint(_OUTPUTS, [], [])
    changed = self_review_fingerprint({**_OUTPUTS, "global_macro": "<p>改写过的宏观正文</p>"}, [], [])
    assert base != changed


def test_fingerprint_stable_for_same_output():
    assert self_review_fingerprint(_OUTPUTS, [], []) == self_review_fingerprint(dict(_OUTPUTS), [], [])


def test_fingerprint_ignores_empty_outputs():
    """缺失/空产出不参与哈希（None 与空串等价）。"""
    a = self_review_fingerprint({"global_macro": "x"}, [], [])
    b = self_review_fingerprint({"global_macro": "x", "expert_review": None, "health_check": "  "}, [], [])
    assert a == b


# ── 真实构建路径（此前仅被 monkeypatch 覆盖，缺口补齐）────────


def test_prompt_builder_includes_module_texts_and_digests():
    """真实提示词构建：含各模块正文、持仓摘要与穿透摘要，且按上限截断。"""
    from src.python.llm.prompts import _build_self_review_prompt

    long_text = "长" * 50
    prompt = _build_self_review_prompt(
        {"global_macro": f"<p>{long_text}</p>", "expert_review": "<p>智囊团正文</p>"},
        holdings_details=[{"name": "测试基金", "code": "000001", "market_value": 1000.0, "profit": 12.0}],
        penetrated_assets=[{"name": "宁德时代", "ratio_pct": 3.5}],
        per_module_limit=10,
    )

    assert "global_macro" in prompt
    assert "智囊团正文" in prompt
    assert "已截断" in prompt, "超过 per_module_limit 的模块正文必须标注截断"
    assert "测试基金" in prompt and "000001" in prompt
    assert "宁德时代" in prompt


def test_prompt_builder_skips_empty_outputs():
    """空/None 产出不进入提示词（不给模型无意义空段）。"""
    from src.python.llm.prompts import _build_self_review_prompt

    prompt = _build_self_review_prompt({"global_macro": None, "expert_review": "   "}, None, None)
    assert "### 模块：global_macro" not in prompt
    assert "### 模块：expert_review" not in prompt
    assert "（无持仓明细）" in prompt
    assert "（无穿透数据）" in prompt


def test_real_generator_reaches_provider_with_compliance_and_caches(monkeypatch):
    """真实生成路径（generate_self_review → generate_llm_module → api.call_llm → provider）。

    mock 打在 **provider 层**（而非 skeleton 的 call_llm）：合规声明注入在
    ``api.call_llm`` 这个漏斗内，若 mock 在 skeleton 层，就绕过了被测的注入点，
    断言会假绿/假红（本用例初版即踩此坑）。

    断言三件事：① 自检模块的 system prompt 经漏斗后含合规声明；② user prompt 含上游
    产出；③ 同产出第二次命中缓存（call_claude 只被调用一次），锁定指纹内容寻址。
    """
    from unittest.mock import patch

    from src.python.llm.compliance import COMPLIANCE_CLOSING
    from src.python.llm.generators import generate_self_review

    calls: list[tuple] = []

    def _fake_call_claude(system_prompt, user_prompt, *args, **kwargs):
        calls.append((system_prompt, user_prompt))
        return ("<p>【自检清单】未发现矛盾</p>", {"input_tokens": 10, "output_tokens": 5})

    llm_config = {
        "provider": "claude",
        "api_key": "sk-test",
        "enabled_llm": {SELF_REVIEW_MODULE_KEY: True},
        "cache_enabled_self_review": True,
        "max_tokens_self_review": 2048,
    }

    with patch("src.python.llm.api.call_claude", _fake_call_claude):
        first, cached_first = generate_self_review(_OUTPUTS, [], [], force=False, llm_config=llm_config)
        second, cached_second = generate_self_review(_OUTPUTS, [], [], force=False, llm_config=llm_config)

    assert first and "【自检清单】" in first
    assert cached_first is False
    assert cached_second is True, "同产出第二次应命中缓存"
    assert second.startswith(first), "缓存返回的内容主体应与首次一致（仅追加缓存页脚）"
    assert len(calls) == 1, "命中缓存后不得再次调用 provider"
    assert COMPLIANCE_CLOSING in calls[0][0], "自检模块的 system prompt 须经漏斗叠加合规声明"
    assert "宏观分析正文" in calls[0][1], "user prompt 须含上游模块产出"
