"""报告深度档位单元测试。

测试目标：
  - 档位表结构（三档、模块集合从注册表派生、brief ⊊ standard）
  - normalize_depth / resolve_depth_profile — 合法、非法回落、缺失默认
  - depth_gate — 档位只收窄不放大（不得打开已关闭模块）
  - effective_news_limit — 下界修正与缺省原样
  - non_default_depth_line — 默认档零噪声、非默认档给自述

运行：
  pytest src/test/unit/llm/test_depth_profile.py -v
"""

from __future__ import annotations

import logging

import pytest

from src.python.core.registry import get_llm_module_names
from src.python.llm.depth_profile import (
    DEPTH_PROFILES,
    REPORT_DEPTH_DEFAULT,
    REPORT_DEPTH_LEVELS,
    depth_gate,
    effective_news_limit,
    non_default_depth_line,
    normalize_depth,
    resolve_depth_profile,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_llm, pytest.mark.llm]


# ── 档位表结构 ────────────────────────────────────────────────


def test_profile_keys_match_declared_levels():
    """档位表键集合与声明的档位枚举双向一致（新增档位必须同步声明）。"""
    assert set(DEPTH_PROFILES) == set(REPORT_DEPTH_LEVELS)


def test_default_level_exists_and_is_declared():
    assert REPORT_DEPTH_DEFAULT in DEPTH_PROFILES


def test_all_module_set_derives_from_registry():
    """standard 档模块集合 == 注册表的 LLM 模块集合（不另写模块清单，防注册漂移）。"""
    registry_keys = set(get_llm_module_names())
    assert DEPTH_PROFILES["standard"].max_modules == registry_keys

    for profile in DEPTH_PROFILES.values():
        assert profile.max_modules <= registry_keys


def test_brief_is_strict_subset_of_standard():
    """简版是标准的真子集——档位只能收窄，不能引入 standard 之外的模块。"""
    brief = DEPTH_PROFILES["brief"].max_modules
    standard = DEPTH_PROFILES["standard"].max_modules
    assert brief < standard


def test_only_deep_raises_news_floor():
    """仅深度档设新闻采集下界；简版与标准不改用户配置（缺省零影响）。"""
    assert DEPTH_PROFILES["brief"].news_limit_floor is None
    assert DEPTH_PROFILES["standard"].news_limit_floor is None
    assert DEPTH_PROFILES["deep"].news_limit_floor is not None


# ── normalize_depth ───────────────────────────────────────────


@pytest.mark.parametrize("level", REPORT_DEPTH_LEVELS)
def test_normalize_accepts_合法档位(level):
    assert normalize_depth(level) == level


def test_normalize_is_case_and_space_insensitive():
    assert normalize_depth("  DEEP  ") == "deep"


def test_normalize_invalid_falls_back_with_warning(caplog):
    """非法取值回落默认档且**必须告警**（不静默吃掉用户配置错误）。"""
    with caplog.at_level(logging.WARNING, logger="invest"):
        assert normalize_depth("deepest") == REPORT_DEPTH_DEFAULT
    assert any("llm_report_depth" in r.getMessage() for r in caplog.records)


def test_normalize_missing_value_is_silent(caplog):
    """缺省取值（None）不告警——缺失是正常情况，非法才是问题。"""
    with caplog.at_level(logging.WARNING, logger="invest"):
        assert normalize_depth(None) == REPORT_DEPTH_DEFAULT
    assert not caplog.records


# ── resolve_depth_profile ─────────────────────────────────────


def test_resolve_reads_config_value():
    assert resolve_depth_profile({"llm_report_depth": "brief"}).key == "brief"
    assert resolve_depth_profile({"llm_report_depth": "deep"}).key == "deep"


def test_resolve_missing_key_returns_default():
    assert resolve_depth_profile({}).key == REPORT_DEPTH_DEFAULT
    assert resolve_depth_profile({"news_top_count": 300}).key == REPORT_DEPTH_DEFAULT


def test_resolve_invalid_returns_default_profile():
    assert resolve_depth_profile({"llm_report_depth": 42}).key == REPORT_DEPTH_DEFAULT


# ── depth_gate：只收窄不放大 ───────────────────────────────────


def test_depth_gate_cannot_open_disabled_module():
    """开关关闭时任何档位都不得让模块参与（档位是上界，不是开关）。"""
    brief = DEPTH_PROFILES["brief"]
    assert depth_gate(False, "global_macro", brief) is False
    assert depth_gate(False, "expert_review", brief) is False


def test_depth_gate_narrows_enabled_module_outside_profile():
    """开关打开但模块在档位上界之外（简版下的体检模块）→ 不参与。"""
    brief = DEPTH_PROFILES["brief"]
    assert depth_gate(True, "health_check", brief) is False
    assert depth_gate(True, "expert_review", brief) is False


def test_depth_gate_allows_enabled_module_inside_profile():
    brief = DEPTH_PROFILES["brief"]
    standard = DEPTH_PROFILES["standard"]
    assert depth_gate(True, "global_macro", brief) is True
    assert depth_gate(True, "health_check", standard) is True


def test_standard_depth_preserves_all_enabled_modules():
    """缺省档位下，开关打开的模块逐个原样通过（缺省零影响的直接断言）。"""
    standard = DEPTH_PROFILES["standard"]
    for key in get_llm_module_names():
        assert depth_gate(True, key, standard) is True


# ── effective_news_limit ──────────────────────────────────────


def test_news_limit_unchanged_for_profiles_without_floor():
    assert effective_news_limit(300, DEPTH_PROFILES["standard"]) == 300
    assert effective_news_limit(123, DEPTH_PROFILES["brief"]) == 123


def test_news_limit_raised_to_floor_only_when_below():
    deep = DEPTH_PROFILES["deep"]
    floor = deep.news_limit_floor
    assert effective_news_limit(100, deep) == floor
    assert effective_news_limit(floor + 50, deep) == floor + 50


# ── non_default_depth_line ────────────────────────────────────


def test_default_depth_produces_no_line():
    assert non_default_depth_line(DEPTH_PROFILES[REPORT_DEPTH_DEFAULT]) is None


@pytest.mark.parametrize("level", [lv for lv in REPORT_DEPTH_LEVELS if lv != REPORT_DEPTH_DEFAULT])
def test_non_default_depth_line_names_the_label(level):
    line = non_default_depth_line(DEPTH_PROFILES[level])
    assert line is not None
    assert DEPTH_PROFILES[level].label in line
