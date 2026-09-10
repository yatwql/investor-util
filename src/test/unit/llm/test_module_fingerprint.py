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
  - 辩论综合键取「基础指纹 + 综合提示词全文」——pro/con 仅 200 字符之后不同、
    或仅 config 情景段/集中度阈值不同，都必须换键（历史缺陷：只哈希前 200 字符
    摘要 + 开关位字母，两种情况都静默复用陈旧综合结论）

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

# pipeline_data 中【环比变化】【数据质量降级】两段的来源（提示词正文段）
_PIPELINE_DEGRADED = {
    "data_degradation": [
        {"source_key": "tencent", "tier": "T2", "failure_type": "unreachable", "degraded": True, "count": 2}
    ]
}
_PIPELINE_DEGRADED_CHANGED = {
    "data_degradation": [
        {"source_key": "eastmoney", "tier": "T1", "failure_type": "empty", "degraded": True, "count": 1}
    ]
}
_PIPELINE_DIFF = {
    "diff": {
        "is_first_check": False,
        "total_value_diff": 1200.0,
        "total_value_diff_pct": 1.2,
        "total_pnl_diff": 300.0,
        "days_since_last_report": 3,
        "added": [{"name": "示例", "code": "600519", "action": "新增", "shares_diff": 100.0, "value_diff": 1200.0}],
        "removed": [],
        "increased": [],
        "decreased": [],
    }
}
_PIPELINE_DIFF_CHANGED = {"diff": {**_PIPELINE_DIFF["diff"], "total_value_diff": 9900.0, "total_value_diff_pct": 9.9}}

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
    actual = _precheck_info(history_data, pipeline_data, competitive_context, metrics, data_quality_text)[module_key][
        "key"
    ]

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


# ── pipeline_data 派生的【环比变化】【数据质量降级】两段 ──────────
# 复盘提示词与体检提示词都直接承载这两段（_build_expert_review_prompt /
# _build_health_check_prompt 共用 prompts_core 的两个构建器），故二者都必须进键。

_PIPELINE_BLOCK_MODULES = ("expert_review", "health_check")
_PIPELINE_BLOCK_ABSENT_MODULES = ("global_macro", "penetration_deep")


def test_degradation_block_is_in_prompt_for_covered_modules():
    """前提校验：降级块确实进了这两个模块的提示词（否则下述用例是无的放矢）。"""
    from src.python.llm.prompts import _build_data_degradation_block, _build_expert_review_prompt

    block = _build_data_degradation_block(_PIPELINE_DEGRADED)
    assert block, "降级块构建器对该输入未产出文本，用例输入需修正"
    prompt = _build_expert_review_prompt(
        _TOTAL_MV,
        _TOTAL_COST,
        _TOTAL_PROFIT,
        _TODAY_PROFIT,
        1,
        dict(_CATEGORIES),
        holdings_details=_HOLDINGS,
        pipeline_data=_PIPELINE_DEGRADED,
    )
    assert block in prompt, "降级块未进入复盘提示词——指纹覆盖就失去了前提"


@pytest.mark.parametrize("module_key", _PIPELINE_BLOCK_MODULES)
def test_degradation_block_enters_fingerprint(module_key: str):
    """降级事件集变化 ⇒ 指纹随之变化（否则复述故障的陈旧结论被复用）。

    历史缺陷：该块只进提示词、不进指纹——持仓未动而数据源故障/恢复时键不变，
    预检命中旧键，报告继续陈述「某数据源不可用」或漏报新故障，且不报错。
    """
    baseline = _write_fingerprint(module_key, pipeline_data=_PIPELINE_DEGRADED)
    changed = _write_fingerprint(module_key, pipeline_data=_PIPELINE_DEGRADED_CHANGED)
    empty = _write_fingerprint(module_key)

    assert baseline != changed, f"{module_key}：降级事件集变化未换键 → 复用陈旧降级结论"
    assert baseline != empty, f"{module_key}：降级块未进入指纹"


@pytest.mark.parametrize("module_key", _PIPELINE_BLOCK_MODULES)
def test_diff_block_enters_fingerprint(module_key: str):
    """环比差异内容变化 ⇒ 指纹随之变化（同日两份报告的环比结论不得串用）。"""
    baseline = _write_fingerprint(module_key, pipeline_data=_PIPELINE_DIFF)
    changed = _write_fingerprint(module_key, pipeline_data=_PIPELINE_DIFF_CHANGED)

    assert baseline != changed, f"{module_key}：环比差异变化未换键 → 复用陈旧环比结论"
    assert baseline != _write_fingerprint(module_key), f"{module_key}：环比块未进入指纹"


@pytest.mark.parametrize("module_key", _PIPELINE_BLOCK_ABSENT_MODULES)
def test_pipeline_blocks_ignored_without_block_in_prompt(module_key: str):
    """提示词不含这两段的模块，指纹不随其变化（并入即纯成本失效）。"""
    assert _write_fingerprint(module_key, pipeline_data=_PIPELINE_DEGRADED) == _write_fingerprint(module_key)


@pytest.mark.parametrize("module_key", _PIPELINE_BLOCK_MODULES)
def test_pipeline_block_enters_precheck_key_not_only_write_side(module_key: str):
    """预检侧同样随降级块换键，且与写侧逐字符同源。"""
    baseline = _precheck_info(pipeline_data=_PIPELINE_DEGRADED)[module_key]["key"]
    changed = _precheck_info(pipeline_data=_PIPELINE_DEGRADED_CHANGED)[module_key]["key"]
    write_fp = _write_fingerprint(module_key, pipeline_data=_PIPELINE_DEGRADED)

    assert baseline != changed, f"{module_key}：预检侧未随降级块换键"
    assert baseline == CACHE_PREFIX_LLM + f"{module_key}_{write_fp}", f"{module_key}：两侧键不同源"


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


def test_debate_fingerprint_covers_pipeline_blocks_in_its_prompt():
    """辩论提示词（复用复盘提示词构建器）含环比与降级两段 ⇒ 基础指纹须覆盖。"""
    from src.python.llm.module_fingerprint import debate_procon_fingerprint

    baseline = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK, pipeline_data=_PIPELINE_DEGRADED))
    changed = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK, pipeline_data=_PIPELINE_DEGRADED_CHANGED))

    assert baseline != changed, "辩论指纹未覆盖其提示词中的降级段 → 复用陈旧降级结论"


def test_debate_fingerprint_ignores_segments_absent_from_its_prompt():
    """辩论提示词不含信号预消化段 ⇒ 指纹不得随该段变化。

    否则每次报告的信号摘要都不同，辩论三键（白脸/黑脸/综合各一次昂贵调用）
    将每份报告必 miss。注意区分：``pipeline_data`` 中的环比/降级两段确实在其
    提示词内（上一个用例），只有信号预消化这类**未开启**的段落才应被排除。
    """
    from src.python.llm.module_fingerprint import debate_procon_fingerprint

    without = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK))
    with_signal = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK, pipeline_data=_PIPELINE_RISK))

    assert without == with_signal, "辩论指纹被并入其提示词没有的段落 → 三键每次必 miss"


def test_debate_synthesis_fingerprint_covers_full_procon_text():
    """综合指纹覆盖 pro/con **全文**：仅 200 字符之后不同也必须换键。

    历史缺陷：综合键另起一套拼接，只取 pro/con 前 200 字符摘要——正文差异落在
    200 字符之后时键不动，直接复用按旧正文生成的综合结论（且不报错）。
    """
    from src.python.llm.module_fingerprint import debate_synthesis_fingerprint
    from src.python.llm.prompts import _build_debate_synthesis_prompt

    _prefix = "开头相同。" * 60  # 300 字符 > 200，差异因此落在摘要窗口之外
    pro_a = _prefix + "尾部：建议持有。"
    pro_b = _prefix + "尾部：建议减仓。"
    con = "黑脸观点：估值偏高。"

    fp_a = debate_synthesis_fingerprint(_debate_inputs(), _build_debate_synthesis_prompt(pro_a, con))
    fp_b = debate_synthesis_fingerprint(_debate_inputs(), _build_debate_synthesis_prompt(pro_b, con))

    assert pro_a[:200] == pro_b[:200], "用例前提：两段正文前 200 字符须完全相同"
    assert fp_a != fp_b, "综合指纹仍只看前 200 字符 → 会复用按旧正文生成的综合结论"


def test_debate_synthesis_fingerprint_covers_config_driven_prompt_text():
    """综合指纹覆盖 config 驱动的情景段/集中度段：仅改配置也必须换键。

    历史缺陷：综合键只编码开关位（c/q 字母后缀），提示词里的情景名/描述与
    集中度阈值来自 config——改配置不动开关时键不变，命中按旧配置生成的综合结论。
    """
    from unittest.mock import patch

    from src.python.llm.module_fingerprint import debate_synthesis_fingerprint
    from src.python.llm.prompts import _build_debate_synthesis_prompt

    _base_cfg = {
        "debate": {
            "conditional": {"scenarios": [{"name": "上涨", "desc": "上证站上 3500"}]},
            "qa_concentration": {"threshold": 0.20},
        }
    }
    _changed_cfg = {
        "debate": {
            "conditional": {"scenarios": [{"name": "上涨", "desc": "上证站上 4000"}]},
            "qa_concentration": {"threshold": 0.20},
        }
    }

    def _fp(cfg: dict) -> str:
        with patch("src.python.config._llm_settings.get_llm_config", return_value=cfg):
            prompt = _build_debate_synthesis_prompt(
                "白脸观点。", "黑脸观点。", enable_conditional=True, total_mv=_TOTAL_MV
            )
        return debate_synthesis_fingerprint(_debate_inputs(), prompt)

    _base_prompt_fp = _fp(_base_cfg)
    _changed_prompt_fp = _fp(_changed_cfg)

    assert _base_prompt_fp != _changed_prompt_fp, "综合指纹未覆盖 config 驱动的情景段 → 复用旧配置结论"


def test_debate_fingerprint_carries_debate_feature_suffix():
    """辩论增强开关组合仍须换键（后缀语义不因收敛构造器而丢）。"""
    from src.python.config.features import FEATURE_FLAGS
    from src.python.llm.module_fingerprint import debate_procon_fingerprint

    off = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK))
    FEATURE_FLAGS["llm_debate_conditional"] = True
    on = debate_procon_fingerprint(_debate_inputs(_COMPETITIVE_BLOCK))

    assert off != on, "辩论增强后缀未进入辩论指纹"
