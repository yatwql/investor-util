"""配置注册表测试 — 验证注册表完备性、派生产出一致性、前向兼容。"""

from __future__ import annotations



from src.python.constants import CACHE_DAILY, CACHE_WEEKLY, CACHE_MONTHLY
from src.python.registry import (
    ComputModuleDef,
    DataModuleDef,
    get_computation_module,
    get_computation_registry,
    get_registry,
    get_cache_ttl_defaults,
    get_prefix_type_map,
    get_exact_type_map,
    get_known_llm_settings_keys,
    get_registered_data_types,
    get_report_section_keys,
    get_report_section_order,
    _REPORT_SECTION_DEFAULT,
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
        """LLM settings 键名数量应与预期一致（5模块 × 10 - 1个例外 = 49 + 5全局 = 54）。"""
        keys = get_known_llm_settings_keys()
        # 确认已知的全局键存在
        assert "max_retries" in keys
        assert "enabled_llm" in keys
        assert "pricing" in keys
        assert "news_correlation_top_n" in keys
        # 确认 per-module 键生成正确
        assert "temperature_global_macro" in keys
        assert "output_brief_global_macro" in keys
        # news_correlation 不应有 output_brief
        assert "output_brief_news_correlation" not in keys
        # 确认总键数
        assert len(keys) == 54, f"预期 54 个 LLM settings 键，实际 {len(keys)}"

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
        assert etm["fund_manager_snapshot"] == "fund_manager"
        assert etm["fund_concentration_snapshot"] == "fund_concentration"
        assert etm["fund_style_snapshot"] == "fund_style_snapshot"
        assert etm["bond_yield_rf"] == "bond_yield"

    def test_exact_type_map_no_extra_keys(self):
        """exact_map 不包含多余键名。"""
        etm = get_exact_type_map()
        # 3 个已有（benchmark/tracking/calendar）+ 3 个 B 系列（manager/concentration/style）+ 1 bond_yield_rf
        assert len(etm) == 7, f"预期 7 个精确键名，实际 {len(etm)}"

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
        """有缓存前缀的模块——有 cache_groups 或有设计注释说明无分组原因。"""
        known_ungrouped = {"history_stock", "history_fund_otc", "history_index"}
        for m in get_registry():
            if m.cache_prefixes:
                if m.data_type in known_ungrouped:
                    continue  # 有意无分组：per-code 缓存，仅按 TTL 过期
                assert m.cache_groups, f"{m.name} 有 cache_prefixes 但无 cache_groups（如需豁免请加入 known_ungrouped）"


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


# ═══════════════════════════════════════════════════════════════
#  Test Report Section Order (C-P1a)
# ═══════════════════════════════════════════════════════════════


class TestReportSectionDefault:
    """_REPORT_SECTION_DEFAULT 完整性验证。"""

    def test_total_17_sections(self):
        """应有 17 个报告模块（early_warning 已移除）。"""
        assert len(_REPORT_SECTION_DEFAULT) == 17

    def test_every_entry_has_required_fields(self):
        """每个条目必须有 key/name/number/type/data_flag。"""
        for sec in _REPORT_SECTION_DEFAULT:
            assert "key" in sec, f"缺少 key: {sec}"
            assert "name" in sec, f"缺少 name: {sec}"
            assert "number" in sec, f"缺少 number: {sec}"
            assert "type" in sec, f"缺少 type: {sec}"
            assert "data_flag" in sec, f"缺少 data_flag: {sec}"

    def test_type_values_are_valid(self):
        """type 只能是 always/history/b_series/news/llm 之一。"""
        valid_types = {"always", "history", "b_series", "news", "llm"}
        for sec in _REPORT_SECTION_DEFAULT:
            assert sec["type"] in valid_types, (
                f"{sec['key']}: type={sec['type']!r} 不在 {valid_types}"
            )

    def test_always_type_has_no_data_flag(self):
        """always 类型的 data_flag 应为 None。"""
        for sec in _REPORT_SECTION_DEFAULT:
            if sec["type"] == "always":
                assert sec["data_flag"] is None, (
                    f"{sec['key']}: always 类型不应有 data_flag"
                )

    def test_non_always_type_has_data_flag(self):
        """非 always/history 类型必须有 data_flag。"""
        for sec in _REPORT_SECTION_DEFAULT:
            if sec["type"] not in ("always", "history"):
                assert sec["data_flag"] is not None, (
                    f"{sec['key']}: {sec['type']} 类型缺少 data_flag"
                )

    def test_default_numbers_are_1_to_17(self):
        """默认序号应为 1 到 17。"""
        numbers = [sec["number"] for sec in _REPORT_SECTION_DEFAULT]
        assert numbers == list(range(1, 18)), f"序号不连续: {numbers}"

    def test_llm_usage_is_last(self):
        """llm_usage 应在默认列表最后。"""
        assert _REPORT_SECTION_DEFAULT[-1]["key"] == "llm_usage"

    def test_no_duplicate_keys(self):
        """key 不得重复。"""
        keys = [sec["key"] for sec in _REPORT_SECTION_DEFAULT]
        duplicates = {k for k in keys if keys.count(k) > 1}
        assert not duplicates, f"重复的 key: {duplicates}"


class TestGetReportSectionKeys:
    """get_report_section_keys() 单元测试。"""

    def test_returns_all_17_keys(self):
        """应返回 17 个有效 key。"""
        keys = get_report_section_keys()
        assert len(keys) == 17

    def test_contains_known_keys(self):
        """应包含已知的几个关键 key。"""
        keys = get_report_section_keys()
        for k in ("summary", "fund_performance", "fund_manager", "llm_usage"):
            assert k in keys, f"缺少 {k}"


class TestGetReportSectionOrder:
    """get_report_section_order() 单元测试。"""

    def test_no_config_returns_defaults(self):
        """config 为 None → 返回 18 项默认值。"""
        order = get_report_section_order()
        assert len(order) == 17
        assert order[-1]["key"] == "llm_usage"
        # 验证每个条目的 number 与原默认一致
        for sec, default in zip(order, _REPORT_SECTION_DEFAULT):
            assert sec["key"] == default["key"]
            assert sec["number"] == default["number"]

    def test_config_none_returns_deep_copy(self):
        """返回的列表应为深拷贝，修改不影响原数据。"""
        order = get_report_section_order()
        order[0]["number"] = 999
        assert _REPORT_SECTION_DEFAULT[0]["number"] == 1

    def test_empty_config_returns_defaults(self):
        """report_section_order 为空字典 → 返回默认。"""
        order = get_report_section_order({"report_section_order": {}})
        assert len(order) == 17
        assert order[0]["key"] == "summary"

    def test_non_dict_config_returns_defaults(self):
        """report_section_order 不是 dict → 返回默认。"""
        order = get_report_section_order({"report_section_order": "invalid"})
        assert len(order) == 17
        assert order[0]["key"] == "summary"

    def test_partial_config_items_first(self):
        """已配置项排在最前，按序号升序。"""
        order = get_report_section_order({
            "report_section_order": {"fund_manager": 1, "summary": 2}
        })
        assert order[0]["key"] == "fund_manager"
        assert order[0]["number"] == 1
        assert order[1]["key"] == "summary"
        assert order[1]["number"] == 2
        # 前两项之外应有 16 项（含 llm_usage 在最后）
        assert len(order) == 17

    def test_partial_config_unconfigured_after_configured(self):
        """未配置项排在已配置项之后。"""
        order = get_report_section_order({
            "report_section_order": {"fund_manager": 1, "summary": 2}
        })
        # 检查前两项之后第一项是未配置的 market_value（默认顺序第 2 位）
        # 但注意 market_value 默认序号是 2，与 summary 重复
        keys_after = [s["key"] for s in order[2:]]
        assert "market_value" in keys_after
        assert "fund_overlap" in keys_after

    def test_llm_usage_always_last(self):
        """llm_usage 即使被配置也强制最后。"""
        order = get_report_section_order({
            "report_section_order": {"llm_usage": 1}
        })
        assert order[-1]["key"] == "llm_usage"

    def test_llm_usage_config_in_middle(self):
        """llm_usage 配了居中序号 → 仍强制最后。"""
        order = get_report_section_order({
            "report_section_order": {"summary": 5, "llm_usage": 3}
        })
        assert order[-1]["key"] == "llm_usage"
        # summary 应该在前面（已配置）
        assert order[0]["key"] == "summary"

    def test_invalid_number_uses_default(self):
        """无效序号回退默认值。"""
        order = get_report_section_order({
            "report_section_order": {"summary": "abc"}
        })
        summary_entry = [s for s in order if s["key"] == "summary"][0]
        # summary 默认序号是 1，配置值 "abc" 无效应回退
        assert summary_entry["number"] == 1

    def test_negative_number_uses_user_value(self):
        """注意：负数也作为用户配置值保留（校验由 config.py 负责）。"""
        # 这里 get_report_section_order 不校验正负，只负责 int() 转换
        order = get_report_section_order({
            "report_section_order": {"summary": -5}
        })
        summary_entry = [s for s in order if s["key"] == "summary"][0]
        assert summary_entry["number"] == -5

    def test_full_config_reverse_order(self):
        """全部 18 项都配了 → 按配置序号排序，llm_usage 最后。"""
        all_keys = [s["key"] for s in _REPORT_SECTION_DEFAULT if s["key"] != "llm_usage"]
        # 反序配置
        full_config = {k: i + 1 for i, k in enumerate(reversed(all_keys))}
        order = get_report_section_order({"report_section_order": full_config})
        assert len(order) == 17
        assert order[-1]["key"] == "llm_usage"
        # 第一个应为反序后的最后一个（即 fund_manager 的反序... 等等）
        reversed_last = list(reversed(all_keys))[0]
        assert order[0]["key"] == reversed_last


# ═══════════════════════════════════════════════════════════════
#  Test Computation Registry
# ═══════════════════════════════════════════════════════════════


class TestComputationRegistry:
    """计算模块注册表测试。"""

    def test_registry_has_7_modules(self):
        """_COMPUTATION_REGISTRY 当前有 7 个注册模块。"""
        reg = get_computation_registry()
        assert len(reg) == 7

    def test_all_modules_have_module_key(self):
        """每个模块必须有 module_key。"""
        for m in get_computation_registry():
            assert m.module_key, f"模块 {m.name} 缺少 module_key"
            assert m.module_key.startswith("analytics_"), f"module_key {m.module_key} 应以 analytics_ 开头"

    def test_all_modules_have_name(self):
        """每个模块必须有中文名称。"""
        for m in get_computation_registry():
            assert m.name, f"模块 {m.module_key} 缺少 name"

    def test_no_duplicate_module_keys(self):
        """module_key 不得重复。"""
        keys = [m.module_key for m in get_computation_registry()]
        duplicates = {k for k in keys if keys.count(k) > 1}
        assert not duplicates, f"重复的 module_key: {duplicates}"

    def test_get_computation_module_found(self):
        """按 module_key 查找已注册模块。"""
        m = get_computation_module("analytics_metrics")
        assert m is not None
        assert m.name == "量化指标计算"

    def test_get_computation_module_not_found(self):
        """查找不存在的 module_key 返回 None。"""
        m = get_computation_module("analytics_nonexistent")
        assert m is None

    def test_metrics_module_dependencies(self):
        """量化指标模块依赖 bond_yield 和 history。"""
        m = get_computation_module("analytics_metrics")
        assert m is not None
        assert "bond_yield" in m.dependencies
        assert "history" in m.dependencies

    def test_all_modules_status_valid(self):
        """所有模块状态为 planned 或 implemented。"""
        for m in get_computation_registry():
            assert m.status in ("planned", "implemented"), f"{m.module_key} 状态 {m.status} 不合法"

    def test_comput_module_def_is_frozen(self):
        """ComputModuleDef 应为不可变。"""
        m = ComputModuleDef(name="测试", module_key="analytics_test", label="test")
        with pytest.raises(AttributeError):
            m.module_key = "changed"  # type: ignore[misc]
