"""LLM 模块指纹读写同源回归测试 — 唯一事实来源（module_fingerprint）的结构性保证。

覆盖：
  - 注册表覆盖全部 LLM 模块（与预检侧键集合一致，新增模块不得绕过注册）
  - 预检键 == 写侧键（四模块 × 多场景：无/有风险信号、信号预消化、辩论增强）
  - 风险信号（history_data）确实进入**写侧**指纹 —— 历史缺陷回归（写侧漏传
    history_data 而预检侧传了 → 两侧键永不同源、预检 read 永远落空）
  - 辩论增强后缀（conditional / qa_concentration）两侧同时生效
  - 不承接信号块的模块（穿透深度）不受 pipeline_data 影响

运行：
  pytest src/test/unit/llm/test_module_fingerprint.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.python.llm import generators
from src.python.llm.generators_orchestrator import _compute_module_cache_info
from src.python.llm.module_fingerprint import (
    MODULE_FINGERPRINT_BUILDERS,
    ModuleFingerprintInputs,
)
from src.python.llm.prompts import CACHE_PREFIX_LLM

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]

_MODULE_KEYS = ("global_macro", "expert_review", "health_check", "penetration_deep")

_HISTORY = {"annualized_volatility": 0.15, "max_drawdown_pct": -0.10, "status": "ok"}
_HISTORY_CHANGED = {"annualized_volatility": 0.31, "max_drawdown_pct": -0.24, "status": "ok"}
_HOLDINGS = [{"name": "示例", "code": "600519", "cost": 100.0}]
_CATEGORIES = {"股票": 1}
_PIPELINE_RISK = {"tail_risk_data": {"available": True, "var95": 0.5}}

_TOTAL_MV = 100000.0
_TOTAL_COST = 90000.0
_TOTAL_PROFIT = 10000.0
_TODAY_PROFIT = 500.0

# 场景：history_data / pipeline_data / 需开启的功能开关
_SCENARIOS: dict[str, dict] = {
    "no_history": {},
    "with_history": {"history_data": _HISTORY},
    "history_changed": {"history_data": _HISTORY_CHANGED},
    "signal_digest_on": {"history_data": _HISTORY, "pipeline_data": _PIPELINE_RISK, "flags": ("signal_pre_digest",)},
    "debate_enhance_on": {"history_data": _HISTORY, "flags": ("llm_debate_conditional",)},
    "debate_enhance_off": {"history_data": _HISTORY},
}


# ═══════════════════════════════════════════════════════════════
#  两侧取键辅助：预检键 / 写侧指纹
# ═══════════════════════════════════════════════════════════════


def _precheck_info(history_data=None, pipeline_data=None) -> dict[str, dict]:
    """调用预检侧拿到各模块缓存信息（与生产同一入口）。"""
    return _compute_module_cache_info(
        {},
        {},
        {},
        _TOTAL_MV,
        _TOTAL_COST,
        _TOTAL_PROFIT,
        _TODAY_PROFIT,
        1,
        dict(_CATEGORIES),
        None,
        _HOLDINGS,
        False,
        history_data=history_data,
        pipeline_data=pipeline_data,
    )


def _write_kwargs(module_key: str, history_data=None, pipeline_data=None) -> dict:
    """按模块签名构造写侧生成函数的实参。"""
    if module_key == "global_macro":
        return {
            "a_indices": {},
            "us_indices": {},
            "total_mv": _TOTAL_MV,
            "total_profit": _TOTAL_PROFIT,
            "total_cost": _TOTAL_COST,
            "categories": dict(_CATEGORIES),
            "holdings_details": _HOLDINGS,
        }
    kwargs = {
        "total_mv": _TOTAL_MV,
        "total_cost": _TOTAL_COST,
        "total_profit": _TOTAL_PROFIT,
        "total_today_profit": _TODAY_PROFIT,
        "holdings_count": 1,
        "categories": dict(_CATEGORIES),
        "penetrated_assets": None,
        "holdings_details": _HOLDINGS,
    }
    if module_key != "global_macro":
        kwargs["history_data"] = history_data
    if module_key in ("expert_review", "health_check"):
        kwargs["pipeline_data"] = pipeline_data
    return kwargs


def _write_fingerprint(module_key: str, history_data=None, pipeline_data=None) -> str:
    """调用写侧生成函数并取回其指纹闭包输出（skeleton 入口被 mock，不触网）。"""
    generator_fn = {
        "global_macro": generators.generate_global_macro,
        "expert_review": generators.generate_expert_review,
        "health_check": generators.generate_health_check,
        "penetration_deep": generators.generate_penetration_deep_analysis,
    }[module_key]
    with patch.object(generators, "generate_llm_module") as mock_gen:
        mock_gen.return_value = ("内容", False)
        generator_fn(**_write_kwargs(module_key, history_data, pipeline_data))
    return mock_gen.call_args.kwargs["fingerprint_fn"]()


# ═══════════════════════════════════════════════════════════════
#  注册表：唯一事实来源的覆盖面
# ═══════════════════════════════════════════════════════════════


class TestModuleFingerprintRegistry:
    """注册表覆盖全部 LLM 模块，且与预检侧产出的模块集合一致。"""

    def test_registry_covers_all_llm_modules(self):
        """注册表键集合 == 预检侧 cache_info 键集合 == 四个分析模块。"""
        assert set(MODULE_FINGERPRINT_BUILDERS) == set(_MODULE_KEYS)
        assert set(_precheck_info()) == set(_MODULE_KEYS)

    def test_builders_are_deterministic(self):
        """同一输入 → 同一指纹（四模块均确定性）。"""
        inputs = ModuleFingerprintInputs(
            total_mv=_TOTAL_MV,
            total_cost=_TOTAL_COST,
            total_profit=_TOTAL_PROFIT,
            total_today_profit=_TODAY_PROFIT,
            holdings_details=_HOLDINGS,
            categories=dict(_CATEGORIES),
            history_data=_HISTORY,
        )
        for module_key, builder in MODULE_FINGERPRINT_BUILDERS.items():
            assert builder(inputs) == builder(inputs), f"{module_key} 指纹不确定"


# ═══════════════════════════════════════════════════════════════
#  读写同源：预检键 == 写侧键
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("module_key", _MODULE_KEYS)
@pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
def test_precheck_key_equals_write_key(module_key: str, scenario: str):
    """任一模块、任一场景下，预检键与写侧键逐字符相同（预检不得形同虚设）。"""
    from src.python.config.features import FEATURE_FLAGS

    spec = _SCENARIOS[scenario]
    for flag in spec.get("flags", ()):
        FEATURE_FLAGS[flag] = True

    history_data = spec.get("history_data")
    pipeline_data = spec.get("pipeline_data")

    expected = CACHE_PREFIX_LLM + f"{module_key}_{_write_fingerprint(module_key, history_data, pipeline_data)}"
    actual = _precheck_info(history_data, pipeline_data)[module_key]["key"]

    assert actual == expected, f"{module_key} / {scenario}：预检键与写侧键不同源 → 预检永不命中"


# ═══════════════════════════════════════════════════════════════
#  敏感性：影响内容的输入必须进入两侧指纹
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("module_key", ("expert_review", "health_check", "penetration_deep"))
def test_risk_signals_enter_write_side_fingerprint(module_key: str):
    """写侧指纹必须随 history_data 风险信号变化（历史缺陷：写侧漏传 → 键脱钩）。"""
    without_history = _write_fingerprint(module_key)
    with_history = _write_fingerprint(module_key, history_data=_HISTORY)
    changed_history = _write_fingerprint(module_key, history_data=_HISTORY_CHANGED)

    assert without_history != with_history, "风险信号未进入写侧指纹"
    assert with_history != changed_history, "风险信号变化未换键"


def test_global_macro_fingerprint_ignores_risk_signals():
    """全球政经局势不承接风险信号 → 指纹不随其变化（避免无谓的缓存失效）。"""
    assert _write_fingerprint("global_macro", history_data=_HISTORY) == _write_fingerprint("global_macro")


def test_debate_enhance_suffix_enters_both_sides():
    """辩论增强开启 → 两侧同时换键（只改提示词的开关不得让预检命中旧键）。"""
    from src.python.config.features import FEATURE_FLAGS

    off_key = _precheck_info(history_data=_HISTORY)["expert_review"]["key"]
    off_fp = _write_fingerprint("expert_review", history_data=_HISTORY)

    FEATURE_FLAGS["llm_debate_conditional"] = True
    on_key = _precheck_info(history_data=_HISTORY)["expert_review"]["key"]
    on_fp = _write_fingerprint("expert_review", history_data=_HISTORY)

    assert on_key != off_key, "预检侧未随辩论增强换键"
    assert on_fp != off_fp, "写侧未随辩论增强换键"
    assert on_key == CACHE_PREFIX_LLM + f"expert_review_{on_fp}", "开启后两侧键仍须同源"


def test_signal_suffix_only_affects_digest_modules():
    """信号预消化只进 expert_review / health_check 的键，穿透深度不受影响。"""
    from src.python.config.features import FEATURE_FLAGS

    FEATURE_FLAGS["signal_pre_digest"] = True
    without_signal = _precheck_info(history_data=_HISTORY)
    with_signal = _precheck_info(history_data=_HISTORY, pipeline_data=_PIPELINE_RISK)

    assert without_signal["expert_review"]["key"] != with_signal["expert_review"]["key"]
    assert without_signal["health_check"]["key"] != with_signal["health_check"]["key"]
    assert without_signal["penetration_deep"]["key"] == with_signal["penetration_deep"]["key"]
