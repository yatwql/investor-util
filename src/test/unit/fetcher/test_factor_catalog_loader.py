"""因子目录装载与校验 — 单元测试。

覆盖（R-FCT-01 载体）：目录完整性校验的负例集合（族名/slug/字段/条数/label）、
装载缓存与拒载降级、四类备数的注入探针形状与逐类型不可得原因（含探针抛异常
不外抛）、值键映射（fund_pb→pb / fund_size_log_cap→market_cap 等）。

运行：
  pytest src/test/unit/fetcher/test_factor_catalog_loader.py -v
"""

from __future__ import annotations

import copy

import pytest

from src.python.fetcher import factor_catalog_loader as loader
from src.python.schemas.factor_catalog import (
    CATALOG,
    CATALOG_VERSION,
    FIELD_BARS,
    FIELD_FIN,
    FIELD_INDEX,
    FIELD_VAL,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_BARS = [
    {"date": f"2026-09-{d:02d}", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.1, "volume": 1000}
    for d in range(1, 29)
]


def _fixed_probes(**overrides):
    """构造确定性注入探针（缺省：日K/估值有、指数/财务无）。"""
    probes = {
        "bars": lambda code: list(_BARS),
        "index": lambda: [],
        "valuation": lambda code: {"pb": 1.5},
        "fin": lambda code: None,
    }
    probes.update(overrides)
    return probes


class TestValidateCatalog:
    """目录完整性校验（R-FCT-01）。"""

    def test_real_catalog_passes(self):
        """冻结目录零问题（25 条五族约束内嵌于校验）。"""
        assert loader.validate_catalog(CATALOG) == []

    def test_unknown_family_rejected(self):
        """族名不在五族集合 → 报族条数问题。"""
        bad = copy.deepcopy(CATALOG)
        bad[0]["family"] = "hack_family"
        problems = loader.validate_catalog(bad)
        assert problems, "未知族名应产生问题"
        assert any("族" in p for p in problems)

    def test_duplicate_slug_rejected(self):
        """slug 重复 → 报重复问题。"""
        bad = copy.deepcopy(CATALOG)
        bad[1]["slug"] = bad[0]["slug"]
        problems = loader.validate_catalog(bad)
        assert any("slug 存在重复" in p for p in problems)

    def test_empty_fields_rejected(self):
        """fields 为空 → 报问题。"""
        bad = copy.deepcopy(CATALOG)
        bad[0]["fields"] = []
        problems = loader.validate_catalog(bad)
        assert any("fields 为空" in p for p in problems)

    def test_unknown_field_type_rejected(self):
        """未知字段类型 → 报问题。"""
        bad = copy.deepcopy(CATALOG)
        bad[0]["fields"] = ["hack_field"]
        problems = loader.validate_catalog(bad)
        assert any("未知字段类型" in p for p in problems)

    def test_missing_label_rejected(self):
        """缺 label/formula → 报问题。"""
        bad = copy.deepcopy(CATALOG)
        bad[0]["label"] = ""
        problems = loader.validate_catalog(bad)
        assert any("label" in p for p in problems)

    def test_wrong_count_rejected(self):
        """条数偏离冻结清单 → 报条数问题（截断集合后族计数同时失衡）。"""
        bad = copy.deepcopy(CATALOG)[:-1]
        problems = loader.validate_catalog(bad)
        assert any("条数" in p for p in problems)


class TestLoadCatalog:
    """装载、缓存与拒载降级（R-FCT-01）。"""

    def test_load_shape_and_cache(self, monkeypatch):
        """装载返回版本 + 条目；进程内缓存复用同一对象。"""
        monkeypatch.setattr(loader, "_CATALOG_CACHE", None)
        first = loader.load_factor_catalog()
        second = loader.load_factor_catalog()
        assert first is not None
        assert first["version"] == CATALOG_VERSION
        assert {e["slug"] for e in first["entries"]} == {e["slug"] for e in CATALOG}
        assert second is first, "第二次装载应命中缓存"

    def test_validation_failure_returns_none(self, monkeypatch):
        """校验失败 → 拒载返回 None（调用方降级，不进计算）。"""
        monkeypatch.setattr(loader, "_CATALOG_CACHE", None)
        monkeypatch.setattr(loader, "validate_catalog", lambda catalog: ["目录条数 0 != 25"])
        assert loader.load_factor_catalog() is None


class TestLoadFactorInputs:
    """四类备数与逐类型不可得原因（R-FCT-02）。"""

    def test_injected_probe_shape_and_unavailable(self):
        """注入探针：有数入结构，无数按类型记原因（指数空 → 基准指数不可得）。"""
        inputs = loader.load_factor_inputs(
            ["600000", "600001"],
            probes=_fixed_probes(valuation=lambda code: {"pb": 1.2} if code == "600000" else None),
        )
        assert set(inputs) == {"bars_by_code", "index_bars", "valuation_by_code", "fin_by_code", "unavailable"}
        assert set(inputs["bars_by_code"]) == {"600000", "600001"}
        assert inputs["index_bars"] == []
        assert inputs["unavailable"][FIELD_INDEX] == {"index": "基准指数不可得"}
        assert inputs["unavailable"][FIELD_VAL] == {"600001": "估值字段不可得"}
        assert "600000" not in inputs["unavailable"].get(FIELD_VAL, {})
        assert set(inputs["unavailable"][FIELD_FIN]) == {"600000", "600001"}

    def test_index_probe_exception_not_raised(self):
        """指数探针抛异常 → 记 unavailable，不外抛（契约要求）。"""

        def _boom():
            raise RuntimeError("网络中断")

        inputs = loader.load_factor_inputs(["600000"], probes=_fixed_probes(index=_boom))
        assert inputs["index_bars"] == []
        assert inputs["unavailable"][FIELD_INDEX] == {"index": "基准指数不可得"}

    def test_per_code_probe_exception_records_reason(self):
        """逐码探针抛异常 → 该码按类型记原因，不中断其余码。"""

        def _boom_bars(code):
            if code == "600001":
                raise ValueError("单码异常")
            return list(_BARS)

        inputs = loader.load_factor_inputs(["600000", "600001"], probes=_fixed_probes(bars=_boom_bars))
        assert set(inputs["bars_by_code"]) == {"600000"}
        assert inputs["unavailable"][FIELD_BARS]["600001"] == "日K不可得"

    def test_empty_valuation_dict_marked_unavailable(self):
        """估值返回空 dict → 视为不可得（value_present 过滤全缺失）。"""
        inputs = loader.load_factor_inputs(["600000"], probes=_fixed_probes(valuation=lambda code: {}))
        assert inputs["unavailable"][FIELD_VAL] == {"600000": "估值字段不可得"}


class TestRequiredValueKey:
    """值键映射（R-FCT-02）。"""

    @pytest.mark.parametrize(
        ("slug", "ftype", "expected"),
        [
            ("fund_pb", FIELD_VAL, "pb"),
            ("fund_size_log_cap", FIELD_VAL, "market_cap"),
            ("fund_roe", FIELD_FIN, "roe"),
            ("fund_revenue_yoy", FIELD_FIN, "revenue_yoy"),
            ("fund_gross_margin", FIELD_FIN, "gross_margin"),
        ],
    )
    def test_known_mappings(self, slug, ftype, expected):
        assert loader.required_value_key({"slug": slug}, ftype) == expected

    def test_unknown_fin_slug_defaults_roe(self):
        assert loader.required_value_key({"slug": "unknown"}, FIELD_FIN) == "roe"

    def test_non_valuation_type_returns_type(self):
        assert loader.required_value_key({"slug": "any"}, FIELD_BARS) == FIELD_BARS
