"""因子目录计算编排 — 单元测试。

覆盖（R-FCT-02/R-FCT-05 载体）：池构造（直接持仓 ∪ 穿透 A 股、双维过滤、
dict/attr 两种明细形状）、逐因子横截面（可算/不可算原因/中性相对/评级）、
编排入口的目录拒载/空池/备数异常三类降级。

运行：
  pytest src/test/unit/analysis/test_factor_evaluator.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis import factor_evaluator as fe
from src.python.schemas.factor_catalog import CATALOG, NEUTRAL_POINTS, value_present

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


def _rising_bars(n: int = 70, base: float = 10.0) -> list[dict]:
    return [
        {
            "date": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": base,
            "high": base + 0.5,
            "low": base - 0.2,
            "close": base + i * 0.1,
            "volume": 1000,
        }
        for i in range(n)
    ]


def _inputs(**overrides) -> dict:
    inputs = {
        "bars_by_code": {code: _rising_bars() for code in ("600000", "600001", "600002", "600003")},
        "index_bars": _rising_bars(70, 3000.0),
        "valuation_by_code": {},
        "fin_by_code": {},
        "unavailable": {},
    }
    inputs.update(overrides)
    return inputs


def _entry(slug: str, **overrides) -> dict:
    base = dict(next(e for e in CATALOG if e["slug"] == slug))
    base.update(overrides)
    return base


class TestDeriveFactorPool:
    """池构造（R-FCT-05）。"""

    def test_direct_and_penetration_union(self):
        """直接持仓（名称+代码双维）∪ 穿透 code/codes 两种形状，去重升序。"""
        details = [
            {"name": "贵州茅台", "code": "600519"},
            {"name": "易方达蓝筹精选混合", "code": "005827"},  # 基金 → 双维过滤排除
            {"name": "苹果", "code": "AAPL"},  # 非 A 股代码 → 排除
        ]
        penetration = [
            {"name": "五粮液", "code": "000858", "weight": 0.12},
            {"name": "平安银行", "codes": ["000001", "600519"], "weight": 0.10},
        ]
        pool = fe.derive_factor_pool(details, penetration)
        assert pool["direct_stocks"] == ["600519"]
        assert pool["penetration_stocks"] == ["000001", "000858", "600519"]
        assert pool["codes"] == ["000001", "000858", "600519"], "并集应去重升序"

    def test_attr_row_shape_supported(self):
        """明细为属性对象形状（DetailRow）同样可提取。"""

        class Row:
            name = "万华化学"
            code = "600309"

        pool = fe.derive_factor_pool([Row()], None)
        assert pool["codes"] == ["600309"]

    def test_empty_inputs_yield_empty_pool(self):
        pool = fe.derive_factor_pool(None, None)
        assert pool == {"codes": [], "direct_stocks": [], "penetration_stocks": []}


class TestEvaluateFactorCatalog:
    """逐因子横截面评估（R-FCT-02）。"""

    def test_technical_factor_computable_above_neutral(self):
        """上行序列 RSI=100 ≥ 中性 50 → 可算且中性上方。"""
        out = fe.evaluate_factor_catalog(_inputs(), entries=[_entry("qlib_rsi_14")])
        factor = out["factors"][0]
        assert out["available"] is True
        assert factor["computable"] is True
        assert factor["value"] == pytest.approx(100.0)
        assert factor["above"] is True
        assert factor["codes_ok"] == 4
        assert out["rating"] == "1/1 中性上方"

    def test_insufficient_codes_reason(self):
        """有效码数 < MIN_CODES_PER_DAY → 不出值并给原因。"""
        inputs = _inputs(bars_by_code={"600000": _rising_bars(), "600001": _rising_bars()})
        out = fe.evaluate_factor_catalog(inputs, entries=[_entry("qlib_rsi_14")])
        factor = out["factors"][0]
        assert factor["computable"] is False
        assert "有效码数不足" in factor["reason"]
        assert out["available"] is False
        assert out["reason"] == "池内无可算因子"

    def test_valuation_scalar_cross_section(self):
        """基本面族按码级标量取均值（fund_pb 中性 1.0 → 上方）。"""
        inputs = _inputs(
            bars_by_code={},
            index_bars=[],
            valuation_by_code={"600000": {"pb": 1.0}, "600001": {"pb": 2.0}, "600002": {"pb": 3.0}},
        )
        out = fe.evaluate_factor_catalog(inputs, entries=[_entry("fund_pb")])
        factor = out["factors"][0]
        assert factor["value"] == pytest.approx(2.0)
        assert factor["above"] is True
        assert factor["codes_ok"] == 3
        assert out["pool_size"] == 3

    def test_fin_scalar_field_mapping(self):
        """财务族按值键映射取数（fund_roe → roe）。"""
        inputs = _inputs(
            bars_by_code={},
            index_bars=[],
            fin_by_code={
                "600000": {"roe": 0.12},
                "600001": {"roe": 0.15},
                "600002": {"roe": 0.18},
            },
        )
        out = fe.evaluate_factor_catalog(inputs, entries=[_entry("fund_roe")])
        factor = out["factors"][0]
        assert factor["value"] == pytest.approx(0.15)
        assert factor["computable"] is True

    def test_missing_index_reason(self):
        """需基准指数的因子在指数缺失时先判「基准指数不可得」。"""
        out = fe.evaluate_factor_catalog(_inputs(index_bars=[]), entries=[_entry("qlib_beta_60")])
        factor = out["factors"][0]
        assert factor["computable"] is False
        assert factor["reason"] == "基准指数不可得"

    def test_neutral_less_factor_excluded_from_digest(self):
        """无中性语义因子 above=None，不进评级分母（结构关系断言）。"""
        out = fe.evaluate_factor_catalog(_inputs(), entries=[_entry("acad_amihud_proxy_60"), _entry("qlib_rsi_14")])
        by_slug = {f["slug"]: f for f in out["factors"]}
        assert by_slug["acad_amihud_proxy_60"]["neutral"] is None
        assert by_slug["acad_amihud_proxy_60"]["above"] is None
        expected_total = sum(1 for f in out["factors"] if f["computable"] and f["neutral"] is not None)
        assert out["neutral_total"] == expected_total
        assert out["neutral_above"] <= out["neutral_total"]

    def test_rating_fallback_without_neutral_points(self):
        """全部可算因子无中性点 → 评级回退 N/M 可算。"""
        out = fe.evaluate_factor_catalog(_inputs(), entries=[_entry("acad_amihud_proxy_60")])
        assert out["computed"] == 1
        assert out["rating"] == "1/1 可算"

    def test_empty_inputs_placeholder(self):
        """空输入 → 占位不抛。"""
        out = fe.evaluate_factor_catalog({})
        assert out["available"] is False
        assert out["reason"] == "输入为空"
        assert out["factors"] == []


class TestBuildFactorCatalogData:
    """编排入口三类降级（R-FCT-01/R-FCT-02）。"""

    def test_happy_path_with_patched_loaders(self, monkeypatch):
        monkeypatch.setattr(fe, "load_factor_catalog", lambda: {"version": "V1", "entries": [_entry("fund_pb")]})
        monkeypatch.setattr(
            fe,
            "load_factor_inputs",
            lambda codes: {
                "bars_by_code": {},
                "index_bars": [],
                "valuation_by_code": {c: {"pb": 1.0} for c in codes},
                "fin_by_code": {},
                "unavailable": {},
            },
        )
        out = fe.build_factor_catalog_data(["600000", "600001", "600002"])
        assert out["available"] is True
        assert out["version"] == "V1"
        assert out["pool_size"] == 3

    def test_catalog_rejected_placeholder(self, monkeypatch):
        monkeypatch.setattr(fe, "load_factor_catalog", lambda: None)
        out = fe.build_factor_catalog_data(["600000"])
        assert out["available"] is False
        assert out["reason"] == "目录校验失败"

    def test_empty_pool_skips_fetch(self, monkeypatch):
        monkeypatch.setattr(fe, "load_factor_catalog", lambda: {"version": "V1", "entries": [_entry("fund_pb")]})
        monkeypatch.setattr(fe, "load_factor_inputs", lambda codes: pytest.fail("空池不应备数"))
        out = fe.build_factor_catalog_data([])
        assert out["available"] is False
        assert out["reason"] == "股票池为空"

    def test_fetch_exception_placeholder(self, monkeypatch):
        def _boom(codes):
            raise RuntimeError("链路全断")

        monkeypatch.setattr(fe, "load_factor_catalog", lambda: {"version": "V1", "entries": [_entry("fund_pb")]})
        monkeypatch.setattr(fe, "load_factor_inputs", _boom)
        out = fe.build_factor_catalog_data(["600000"])
        assert out["available"] is False
        assert "备数异常" in out["reason"]


class TestCatalogContractAlignment:
    """评估器与冻结目录的口径一致性（R-FCT-01）。"""

    def test_neutral_points_cover_all_slugs(self):
        """中性点字典键集 == 目录 slug 集（双向，结构关系）。"""
        assert set(NEUTRAL_POINTS) == {e["slug"] for e in CATALOG}

    def test_value_present_filters_none_and_nan(self):
        assert value_present(1.0) is True
        assert value_present(None) is False
        assert value_present(float("nan")) is False

    def test_all_catalog_slugs_dispatch_without_raise(self):
        """全量 25 slug 在空数据下逐个分发且不抛（字段路由全覆盖）。"""
        out = fe.evaluate_factor_catalog(_inputs(bars_by_code={}, index_bars=[]), entries=list(CATALOG))
        assert len(out["factors"]) == len(CATALOG)
        for factor in out["factors"]:
            assert factor["computable"] is False
            assert factor["reason"], f"{factor['slug']} 应给出不可算原因"
