"""LLM 模块指纹读写同源回归测试 — 唯一事实来源（module_fingerprint）的结构性保证。

覆盖：
  - 注册表覆盖全部 LLM 模块（与预检侧键集合一致，新增模块不得绕过注册）
  - 预检键 == 写侧键（四模块 × 多场景：无/有风险信号、信号预消化、辩论增强、
    竞争语境块、量化指标）
  - 风险信号（history_data）确实进入**写侧**指纹 —— 历史缺陷回归（写侧漏传
    history_data 而预检侧传了 → 两侧键永不同源、预检 read 永远落空）
  - 辩论增强后缀（conditional / qa_concentration）两侧同时生效
  - 不承接信号块的模块（穿透深度）不受 pipeline_data 影响
  - **提示词覆盖**：竞争语境块 / 量化指标 / 数据质量详细状态块进了提示词就必须
    进指纹（否则键不变、恒命中按旧数据算出的陈旧结论——数据质量块尤其严重：
    源恢复后仍复述故障）；且只进「提示词确实包含该段」的模块——卫生检查/穿透
    深度的提示词不含对比块与指标，并入只是纯成本
  - 辩论三键的基础指纹同样覆盖其提示词内容，但不并入辩论提示词没有的段落

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

# 竞争语境块（组合 vs 指数对比）：由指数 / 区间收益 / 指标渲染而成的**已渲染文本**
_COMPETITIVE_BLOCK = "【今日对比】组合 +0.50% vs 沪深300 +1.05%\n相对沪深300 跑输 0.55%"
_COMPETITIVE_BLOCK_CHANGED = "【今日对比】组合 +0.50% vs 沪深300 +1.42%\n相对沪深300 跑输 0.92%"
_METRICS = {"sharpe_ratio": 1.2, "calmar_ratio": 0.8, "annualized_volatility": 0.15, "max_drawdown": -0.10}
_METRICS_CHANGED = {"sharpe_ratio": 2.4, "calmar_ratio": 1.6, "annualized_volatility": 0.31, "max_drawdown": -0.24}

# 数据质量详细状态块（health_check 提示词第五维度）：**已渲染文本**
_DQ_BLOCK = "【数据质量详细状态】\n连接失败: tencent(2次)\n触发降级: 2 次"
_DQ_BLOCK_CHANGED = "【数据质量详细状态】\n数据为空: eastmoney(1次)"

_TOTAL_MV = 100000.0
_TOTAL_COST = 90000.0
_TOTAL_PROFIT = 10000.0
_TODAY_PROFIT = 500.0

# 场景：history_data / pipeline_data / 竞争语境块 / 量化指标 / 需开启的功能开关
_SCENARIOS: dict[str, dict] = {
    "no_history": {},
    "with_history": {"history_data": _HISTORY},
    "history_changed": {"history_data": _HISTORY_CHANGED},
    "signal_digest_on": {"history_data": _HISTORY, "pipeline_data": _PIPELINE_RISK, "flags": ("signal_pre_digest",)},
    "debate_enhance_on": {"history_data": _HISTORY, "flags": ("llm_debate_conditional",)},
    "debate_enhance_off": {"history_data": _HISTORY},
    "competitive_block": {"competitive_context": _COMPETITIVE_BLOCK},
    "competitive_block_changed": {"competitive_context": _COMPETITIVE_BLOCK_CHANGED},
    "competitive_block_with_history": {"competitive_context": _COMPETITIVE_BLOCK, "history_data": _HISTORY},
    "metrics": {"metrics": _METRICS},
    "metrics_changed": {"metrics": _METRICS_CHANGED},
    "data_quality_block": {"data_quality_text": _DQ_BLOCK},
    "data_quality_block_changed": {"data_quality_text": _DQ_BLOCK_CHANGED},
}


# ═══════════════════════════════════════════════════════════════
#  两侧取键辅助：预检键 / 写侧指纹
# ═══════════════════════════════════════════════════════════════


def _precheck_info(
    history_data=None,
    pipeline_data=None,
    competitive_context: str = "",
    metrics=None,
    data_quality_text: str = "",
) -> dict[str, dict]:
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
        competitive_context=competitive_context,
        metrics=metrics,
        data_quality_text=data_quality_text,
    )


def _write_kwargs(
    module_key: str,
    history_data=None,
    pipeline_data=None,
    competitive_context: str = "",
    metrics=None,
    data_quality_text: str = "",
) -> dict:
    """按模块签名构造写侧生成函数的实参。

    竞争语境块只传给提示词确实包含它的模块（全球政经局势 / 智囊团复盘），
    量化指标只给智囊团复盘，数据质量块只给持仓体检；其余模块的生成函数没有
    这些形参——它们不进提示词，也就不该进指纹。
    """
    if module_key == "global_macro":
        kwargs = {
            "a_indices": {},
            "us_indices": {},
            "total_mv": _TOTAL_MV,
            "total_profit": _TOTAL_PROFIT,
            "total_cost": _TOTAL_COST,
            "categories": dict(_CATEGORIES),
            "holdings_details": _HOLDINGS,
        }
    else:
        kwargs = {
            "total_mv": _TOTAL_MV,
            "total_cost": _TOTAL_COST,
            "total_profit": _TOTAL_PROFIT,
            "total_today_profit": _TODAY_PROFIT,
            "holdings_count": 1,
            "categories": dict(_CATEGORIES),
            "penetrated_assets": None,
            "holdings_details": _HOLDINGS,
            "history_data": history_data,
        }
        if module_key in ("expert_review", "health_check"):
            kwargs["pipeline_data"] = pipeline_data
    if module_key in ("global_macro", "expert_review"):
        kwargs["competitive_context"] = competitive_context
    if module_key == "expert_review":
        kwargs["metrics"] = metrics
    if module_key == "health_check":
        kwargs["data_quality_text"] = data_quality_text
    return kwargs


def _write_fingerprint(
    module_key: str,
    history_data=None,
    pipeline_data=None,
    competitive_context: str = "",
    metrics=None,
    data_quality_text: str = "",
) -> str:
    """调用写侧生成函数并取回其指纹闭包输出（skeleton 入口被 mock，不触网）。"""
    generator_fn = {
        "global_macro": generators.generate_global_macro,
        "expert_review": generators.generate_expert_review,
        "health_check": generators.generate_health_check,
        "penetration_deep": generators.generate_penetration_deep_analysis,
    }[module_key]
    with patch.object(generators, "generate_llm_module") as mock_gen:
        mock_gen.return_value = ("内容", False)
        generator_fn(
            **_write_kwargs(module_key, history_data, pipeline_data, competitive_context, metrics, data_quality_text)
        )
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
    competitive_context = spec.get("competitive_context", "")
    metrics = spec.get("metrics")
    data_quality_text = spec.get("data_quality_text", "")

    expected = CACHE_PREFIX_LLM + (
        f"{module_key}_"
        f"{_write_fingerprint(module_key, history_data, pipeline_data, competitive_context, metrics, data_quality_text)}"
    )
    actual = _precheck_info(history_data, pipeline_data, competitive_context, metrics, data_quality_text)[module_key]["key"]

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


# ═══════════════════════════════════════════════════════════════
#  提示词覆盖：进了提示词的内容必须进指纹（且只进真的进了提示词的模块）
# ═══════════════════════════════════════════════════════════════


_BLOCK_MODULES = ("global_macro", "expert_review")
_NO_BLOCK_MODULES = ("health_check", "penetration_deep")


@pytest.mark.parametrize("module_key", _BLOCK_MODULES)
def test_competitive_block_enters_fingerprint(module_key: str):
    """竞争语境块内容变化 ⇒ 指纹随之变化。

    否则「持仓未动、基准指数已动」时键不变，预检命中旧键、直接复用按旧指数
    算出的对比结论——提示词与缓存键脱钩，且不报错。
    """
    baseline = _write_fingerprint(module_key, competitive_context=_COMPETITIVE_BLOCK)
    changed = _write_fingerprint(module_key, competitive_context=_COMPETITIVE_BLOCK_CHANGED)
    empty = _write_fingerprint(module_key)

    assert baseline != changed, "竞争语境块变化未换键 → 会复用陈旧对比内容"
    assert baseline != empty, "竞争语境块未进入指纹"


@pytest.mark.parametrize("module_key", _NO_BLOCK_MODULES)
def test_competitive_block_ignored_without_block_in_prompt(module_key: str):
    """提示词不含竞争语境块的模块，指纹不随其变化（并入即纯成本失效）。"""
    assert _write_fingerprint(module_key, competitive_context=_COMPETITIVE_BLOCK) == _write_fingerprint(module_key)


def test_metrics_enter_expert_review_fingerprint():
    """量化指标内容变化 ⇒ 智囊团指纹随之变化（指标表 / 情景分析 / 风格一致性同源）。"""
    baseline = _write_fingerprint("expert_review", metrics=_METRICS)
    changed = _write_fingerprint("expert_review", metrics=_METRICS_CHANGED)

    assert baseline != changed, "量化指标变化未换键 → 会复用按旧指标算出的分析"
    assert baseline != _write_fingerprint("expert_review"), "量化指标未进入指纹"


@pytest.mark.parametrize("module_key", ("global_macro", "health_check", "penetration_deep"))
def test_metrics_ignored_without_metrics_block_in_prompt(module_key: str):
    """提示词不含量化指标段的模块，指纹不随 metrics 变化。"""
    assert _write_fingerprint(module_key, metrics=_METRICS) == _write_fingerprint(module_key)


def test_competitive_block_enters_precheck_key_not_only_write_side():
    """预检侧同样随竞争语境块换键——只改写侧会让预检恒命中旧键。"""
    baseline = _precheck_info(competitive_context=_COMPETITIVE_BLOCK)["expert_review"]["key"]
    changed = _precheck_info(competitive_context=_COMPETITIVE_BLOCK_CHANGED)["expert_review"]["key"]

    assert baseline != changed, "预检侧未随竞争语境块换键"


def test_data_quality_block_enters_health_check_fingerprint():
    """数据质量块内容变化 ⇒ 持仓体检指纹随之变化。

    否则「源故障期间生成并缓存、随后恢复」时持仓未变故键不变，预检命中旧键、
    复用陈述与此刻事实相反的故障结论——报告出错却不报错。
    """
    baseline = _write_fingerprint("health_check", data_quality_text=_DQ_BLOCK)
    changed = _write_fingerprint("health_check", data_quality_text=_DQ_BLOCK_CHANGED)
    empty = _write_fingerprint("health_check")

    assert baseline != changed, "数据质量块变化未换键 → 会复用陈述故障的陈旧体检结论"
    assert baseline != empty, "数据质量块未进入指纹"


@pytest.mark.parametrize("module_key", ("global_macro", "expert_review", "penetration_deep"))
def test_data_quality_block_ignored_without_block_in_prompt(module_key: str):
    """提示词不含数据质量块的模块，指纹不随其变化（并入即纯成本失效）。

    数据质量块是**每次运行**的数据源画像，且 ``record()`` 在真实取数路径上无条件
    触发，故恒非空；把它并入不含该段的模块只会让这些模块每份报告必 miss。
    """
    assert _write_fingerprint(module_key, data_quality_text=_DQ_BLOCK) == _write_fingerprint(module_key)


def test_data_quality_block_enters_precheck_key_not_only_write_side():
    """预检侧同样随数据质量块换键——只改写侧会让预检恒命中旧键。"""
    baseline = _precheck_info(data_quality_text=_DQ_BLOCK)["health_check"]["key"]
    changed = _precheck_info(data_quality_text=_DQ_BLOCK_CHANGED)["health_check"]["key"]

    assert baseline != changed, "预检侧未随数据质量块换键"


# ═══════════════════════════════════════════════════════════════
#  辩论三键：写侧独有（辩论模式绕过标准预检），同样覆盖其提示词内容
# ═══════════════════════════════════════════════════════════════


def _debate_inputs(competitive_context: str = "", metrics=None, pipeline_data=None) -> ModuleFingerprintInputs:
    return ModuleFingerprintInputs(
        total_mv=_TOTAL_MV,
        total_cost=_TOTAL_COST,
        total_profit=_TOTAL_PROFIT,
        total_today_profit=_TODAY_PROFIT,
        holdings_details=_HOLDINGS,
        categories=dict(_CATEGORIES),
        competitive_context=competitive_context,
        metrics=metrics,
        pipeline_data=pipeline_data,
    )


def test_debate_fingerprint_covers_its_prompt_content():
    """辩论提示词含竞争语境块与量化指标 ⇒ 基础指纹须覆盖二者。"""
    from src.python.llm.module_fingerprint import debate_procon_fingerprint

    baseline = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK, _METRICS))
    assert baseline != debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK_CHANGED, _METRICS))
    assert baseline != debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK, _METRICS_CHANGED))
    assert baseline != debate_procon_fingerprint(_debate_inputs())


def test_debate_fingerprint_ignores_segments_absent_from_its_prompt():
    """辩论提示词不含信号预消化段 ⇒ 指纹不得随 pipeline_data 变化。

    否则每次报告的 pipeline_data 摘要都不同，辩论三键（白脸/黑脸/综合各一次
    昂贵调用）将每份报告必 miss。
    """
    from src.python.llm.module_fingerprint import debate_procon_fingerprint

    without = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK))
    with_signal = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK, pipeline_data=_PIPELINE_RISK))

    assert without == with_signal, "辩论指纹被并入其提示词没有的段落 → 三键每次必 miss"


def test_debate_fingerprint_carries_debate_feature_suffix():
    """辩论增强开关组合仍须换键（后缀语义不因收敛构造器而丢）。"""
    from src.python.config.features import FEATURE_FLAGS
    from src.python.llm.module_fingerprint import debate_procon_fingerprint

    off = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK))
    FEATURE_FLAGS["llm_debate_conditional"] = True
    on = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK))

    assert off != on, "辩论增强后缀未进入辩论指纹"
