"""配置注册表测试 — 验证注册表完备性、派生产出一致性、前向兼容。"""

from __future__ import annotations



from src.python.constants import CACHE_DAILY, CACHE_WEEKLY, CACHE_MONTHLY
from src.python.registry import (
    DataModuleDef,
    get_registry,
    get_cache_ttl_defaults,
    get_prefix_type_map,
    get_exact_type_map,
    get_known_llm_settings_keys,
    get_registered_data_types,
)
import pytest
pytestmark = [pytest.mark.unit, pytest.mark.unit_core]



class TestRegistryCompleteness:
    """注册表完整性验证。"""

    def test_all_modules_have_data_type(self):
        """每个注册模块必须有 data_type。"""
        for m in get_registry():
            assert m.data_type, f"模块 {m.name} 缺少 data_type"

    def test_all_modules_have_name(self):
        """每个注册模块必须有可读名称。"""
        for m in get_registry():
            assert m.name, f"模块 {m.data_type} 缺少 name"

    def test_no_duplicate_data_types(self):
        """data_type 不得重复。"""
        types = [m.data_type for m in get_registry()]
        duplicates = {t for t in types if types.count(t) > 1}
        assert not duplicates, f"重复的 data_type: {duplicates}"

    def test_no_duplicate_cache_prefixes(self):
        """cache_prefixes 不得跨模块重复。"""
        seen: dict[str, str] = {}
        for m in get_registry():
            for pfx in m.cache_prefixes:
                if pfx in seen:
                    pytest.fail(f"缓存前缀 {pfx!r} 同时在 {seen[pfx]} 和 {m.data_type} 中注册")
                seen[pfx] = m.data_type

    def test_no_duplicate_exact_keys(self):
        """exact_cache_keys 不得跨模块重复。"""
        seen: dict[str, str] = {}
        for m in get_registry():
            for key in m.exact_cache_keys:
                if key in seen:
                    pytest.fail(f"精确键名 {key!r} 同时在 {seen[key]} 和 {m.data_type} 中注册")
                seen[key] = m.data_type

    def test_llm_modules_have_settings_suffix(self):
        """LLM 模块必须设置 settings_suffix。"""
        for m in get_registry():
            if m.is_llm:
                assert m.settings_suffix, f"LLM 模块 {m.data_type} 缺少 settings_suffix"

    def test_non_llm_modules_no_settings_suffix(self):
        """非 LLM 模块不应设置 settings_suffix。"""
        for m in get_registry():
            if not m.is_llm:
                assert m.settings_suffix is None, (
                    f"非 LLM 模块 {m.data_type} 不应有 settings_suffix={m.settings_suffix!r}"
                )

    def test_llm_settings_keys_count(self):
        """LLM settings 键名数量应与预期一致（5模块 × 10 - 1个例外 = 49 + 3全局 = 52）。"""
        keys = get_known_llm_settings_keys()
        # 确认已知的全局键存在
        assert "max_retries" in keys
        assert "enabled_llm" in keys
        assert "pricing" in keys
        # 确认 per-module 键生成正确
        assert "temperature_global_macro" in keys
        assert "output_brief_global_macro" in keys
        # news_correlation 不应有 output_brief
        assert "output_brief_news_correlation" not in keys
        # 确认总键数
        assert len(keys) == 52, f"预期 52 个 LLM settings 键，实际 {len(keys)}"

    def test_each_llm_module_has_model_key(self):
        """每个 LLM 模块必须有 model_{suffix} 键。"""
        keys = get_known_llm_settings_keys()
        for m in get_registry():
            if m.is_llm:
                assert f"model_{m.settings_suffix}" in keys, (
                    f"LLM 模块 {m.data_type} 缺少 model_{m.settings_suffix}"
                )


class TestDerivedMaps:
    """派生映射正确性验证。"""

    def test_cache_ttl_defaults_has_all_types(self):
        """所有数据类型在 TTL 默认值中均有定义。"""
        ttl_map = get_cache_ttl_defaults()
        for m in get_registry():
            assert m.data_type in ttl_map, (
                f"data_type {m.data_type} 未在 get_cache_ttl_defaults() 中"
            )
            assert ttl_map[m.data_type] == m.cache_ttl, (
                f"{m.data_type}: 预期 TTL={m.cache_ttl}, 实际={ttl_map[m.data_type]}"
            )

    def test_cache_ttl_defaults_known_values(self):
        """验证几个已知 TTL 默认值。"""
        ttl_map = get_cache_ttl_defaults()
        assert ttl_map["price"] == CACHE_DAILY
        assert ttl_map["hold"] == CACHE_WEEKLY
        assert ttl_map["benchmark"] == CACHE_MONTHLY
        assert ttl_map["news"] == 900
        assert ttl_map["llm_expert_review"] == 7200
        assert ttl_map["sector_flow"] == 900

    def test_prefix_type_map_covers_all_prefixes(self):
        """所有模块的缓存前缀在 prefix_type_map 中均有对应。"""
        ptm = get_prefix_type_map()
        for m in get_registry():
            for pfx in m.cache_prefixes:
                assert pfx in ptm, (
                    f"前缀 {pfx!r} ({m.data_type}) 未在 get_prefix_type_map() 中"
                )
                assert ptm[pfx] == m.data_type

    def test_prefix_type_map_known_entries(self):
        """验证几个已知前缀映射。"""
        ptm = get_prefix_type_map()
        assert ptm["price_"] == "price"
        assert ptm["fund_perf_"] == "rank"
        assert ptm["fund_hold_"] == "hold"
        assert ptm["industry_"] == "industry"
        assert ptm["news_"] == "news"
        assert ptm["llm_global_macro_"] == "llm_global_macro"
        assert ptm["llm_expert_review_"] == "llm_expert_review"
        assert ptm["llm_news_item_"] == "llm_news_correlation"
        assert ptm["llm_health_check_"] == "llm_health_check"
        assert ptm["llm_penetration_deep_"] == "llm_penetration_deep"
        assert ptm["profit_forecast_"] == "profit_forecast"
        assert ptm["sector_flow_"] == "sector_flow"
        assert ptm["dividend_"] == "dividend"

    def test_exact_type_map_known_entries(self):
        """验证精确键名映射。"""
        etm = get_exact_type_map()
        assert etm["fund_benchmarks"] == "benchmark"
        assert etm["holdings_tracking"] == "tracking"
        assert etm["trading_calendar"] == "calendar"

    def test_exact_type_map_no_extra_keys(self):
        """exact_map 不包含多余键名。"""
        etm = get_exact_type_map()
        assert len(etm) == 3, f"预期 3 个精确键名，实际 {len(etm)}"

    def test_registered_data_types(self):
        """get_registered_data_types 返回所有 data_type。"""
        types = get_registered_data_types()
        for m in get_registry():
            assert m.data_type in types

    def test_no_type_collision_with_prefix(self):
        """确保没有 data_type 和缓存前缀产生歧义。

        例如 data_type="rank" 而前缀是 "fund_perf_" 而非 "rank_",
        所以 cleanup_expired() 不会把 "rank_" 开头的文件误匹配。
        """
        types = get_registered_data_types()
        ptm = get_prefix_type_map()
        for dtype in types:
            # 如果 data_type 恰好以某个前缀开头，两者需指向同一类型
            for pfx, mapped_type in ptm.items():
                if dtype.startswith(pfx) and dtype != mapped_type:
                    pytest.fail(
                        f"data_type {dtype!r} 被前缀 {pfx!r} 匹配到 {mapped_type!r}，"
                        f"可能导致 cleanup_expired 误判"
                    )

    def test_cache_groups_known_values(self):
        """验证已知模块的组归属。"""
        reg = {m.data_type: m for m in get_registry()}
        assert "refresh" in reg["rank"].cache_groups
        assert "refresh" in reg["hold"].cache_groups
        assert "refresh" in reg["industry"].cache_groups
        assert "refresh" in reg["news"].cache_groups
        assert "preload" in reg["price"].cache_groups
        assert "preload" in reg["index"].cache_groups
        assert not reg["calendar"].cache_groups

    def test_cache_prefix_modules_have_groups(self):
        """所有有缓存前缀的模块都应有 cache_groups。"""
        for m in get_registry():
            if m.cache_prefixes:
                assert m.cache_groups, f"{m.name} 有 cache_prefixes 但无 cache_groups"


class TestDataModuleDef:
    """DataModuleDef 单元测试。"""

    def test_llm_settings_keys_non_llm(self):
        """非 LLM 模块返回空键名集合。"""
        m = DataModuleDef("测试", "test_type", cache_ttl=3600)
        assert not m.is_llm
        assert m.llm_settings_keys() == set()

    def test_llm_settings_keys_llm(self):
        """LLM 模块返回适当的键名。"""
        m = DataModuleDef("测试LLM", "test_llm", cache_ttl=3600,
                          settings_suffix="test_module")
        assert m.is_llm
        keys = m.llm_settings_keys()
        assert f"model_test_module" in keys
        assert f"temperature_test_module" in keys
        assert f"output_brief_test_module" in keys  # 非 news_correlation 应有 output_brief

    def test_llm_settings_keys_news_correlation_no_output_brief(self):
        """news_correlation 模块不应有 output_brief 键。"""
        m = DataModuleDef("测试新闻", "test_news", cache_ttl=3600,
                          settings_suffix="news_correlation")
        assert "output_brief_news_correlation" not in m.llm_settings_keys()

    def test_frozen_dataclass(self):
        """DataModuleDef 应为不可变。"""
        m = DataModuleDef("测试", "test", cache_ttl=3600)
        with pytest.raises(AttributeError):
            m.data_type = "changed"  # type: ignore[misc]
