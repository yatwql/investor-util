"""确定性信号抽取适配器 — 单元测试。

覆盖：五类信号抽取形状、`available=False` 占位不入账、持仓级 live/demo 判定
（逐 code 新鲜度 + 数据源降级）、组合级/指数级乐观缺省、聚合行与无 code 行跳过、
开关关闭无感、幂等跳过计数。

运行：
  pytest src/test/unit/report/test_signal_record.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import reset_feature_flags, set_feature_enabled
from src.python.core import signal_ledger as sl
from src.python.core.decision_ledger import DIRECTION_FLAT, DIRECTION_LONG, DIRECTION_SHORT
from src.python.report import signal_record

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

REPORT_DATE = "2026-09-10"


@pytest.fixture(autouse=True)
def _enable_signal_ledger():
    set_feature_enabled(sl.FEATURE_FLAG, True)
    yield
    reset_feature_flags()


@pytest.fixture()
def ledger_path(tmp_path):
    return str(tmp_path / "signals.jsonl")


def _pipeline_data(**overrides):
    """最小可用 pipeline_data（各信号可用、全部 live）。"""
    data = {
        "market_temperature_data": {
            "available": True,
            "index_code": "sh000300",
            "index_name": "沪深300",
            "score": 82.31,
            "tier": "高估",
            "price_percentile": 88.4,
            "ma_deviation": 0.05,
            "volatility": 0.21,
            "sample_count": 750,
        },
        "valuation_data": {
            "available": True,
            "status": "ok",
            "by_code": {
                "600000": {
                    "pe": 5.2,
                    "pb": 0.6,
                    "price_percentile": 12.0,
                    "tier": "低估",
                    "sample_count": 300,
                    "percentile_available": True,
                }
            },
        },
        "tail_risk_data": {
            "available": True,
            "sample_size": 250,
            "var95": -2.5,
            "var99": -4.1,
            "max_single_day_drop": -6.2,
            "consecutive_down_days": 3,
        },
        "style_factor_data": {
            "available": True,
            "alpha": 0.0021,
            "window": 120,
            "sample_count": 120,
            "style_allocation": {"value": 0.6, "growth": 0.3, "quality": 0.1},
            "significant": {"value": True, "growth": False, "quality": False},
        },
        "action_data": {
            "rebalance_signals": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "weight": 0.21,
                    "threshold": 0.15,
                    "action": "建议部分止盈至7-15%区间",
                }
            ]
        },
        "data_freshness": {
            "available": True,
            "items": [
                {"code": "600000", "freshness": "fresh"},
                {"code": "600519", "freshness": "fresh"},
            ],
        },
        "data_degradation": [],
    }
    data.update(overrides)
    return data


def _records_by_type(ledger_path):
    out: dict[str, list[dict]] = {}
    for record in sl.load_signals(ledger_path):
        out.setdefault(record["signal_type"], []).append(record)
    return out


class TestExtraction:
    """五类信号抽取形状。"""

    def test_registers_all_five_types(self, ledger_path):
        result = signal_record.register_deterministic_signals(
            _pipeline_data(), report_date=REPORT_DATE, path=ledger_path
        )

        assert result["registered"] == 5
        assert set(result["by_type"]) == {
            sl.SIGNAL_MARKET_TEMPERATURE,
            sl.SIGNAL_VALUATION,
            sl.SIGNAL_TAIL_RISK,
            sl.SIGNAL_STYLE_FACTOR,
            sl.SIGNAL_REBALANCE_OVERFLOW,
        }

    def test_temperature_record_shape_and_direction(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        record = _records_by_type(ledger_path)[sl.SIGNAL_MARKET_TEMPERATURE][0]
        assert record["subject"] == "sh000300"
        assert record["name"] == "沪深300"
        assert record["rating"] == "高估"
        assert record["value"] == 82.31
        assert record["direction"] == DIRECTION_SHORT

    def test_valuation_record_direction_long_on_undervalued(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        record = _records_by_type(ledger_path)[sl.SIGNAL_VALUATION][0]
        assert record["subject"] == "600000"
        assert record["rating"] == "低估"
        assert record["direction"] == DIRECTION_LONG

    def test_tail_risk_is_portfolio_scoped_and_directionless(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        record = _records_by_type(ledger_path)[sl.SIGNAL_TAIL_RISK][0]
        assert record["subject"] == "portfolio"
        assert record["value"] == -2.5
        assert record["direction"] == DIRECTION_FLAT
        assert record["rating"] == signal_record.RATING_TAIL_MODERATE

    @pytest.mark.parametrize(
        ("var95", "expected"),
        [
            (-5.0, "尾部偏厚"),
            (-3.0, "尾部偏厚"),
            (-2.5, "尾部中等"),
            (-2.0, "尾部中等"),
            (-1.0, "尾部正常"),
        ],
    )
    def test_tail_risk_rating_bands(self, var95, expected):
        assert signal_record._tail_risk_rating(var95) == expected

    def test_style_factor_uses_english_label(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        record = _records_by_type(ledger_path)[sl.SIGNAL_STYLE_FACTOR][0]
        assert record["rating"] == "价值"  # FACTOR_NAMES 归一，非原始 key
        assert record["value"] == 0.6
        assert record["direction"] == DIRECTION_FLAT

    def test_overflow_record_shape_and_direction(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        record = _records_by_type(ledger_path)[sl.SIGNAL_REBALANCE_OVERFLOW][0]
        assert record["subject"] == "600519"
        assert record["name"] == "贵州茅台"
        assert record["rating"] == "超限"
        assert record["value"] == 0.21
        assert record["direction"] == DIRECTION_SHORT


class TestUnavailableSkipped:
    """不可用占位与缺失键不入账。"""

    @pytest.mark.parametrize(
        "key",
        [
            "market_temperature_data",
            "valuation_data",
            "tail_risk_data",
            "style_factor_data",
            "action_data",
        ],
    )
    def test_missing_key_skips_that_type(self, key, ledger_path):
        data = _pipeline_data()
        data.pop(key)

        result = signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert result["registered"] == 4

    def test_unavailable_flags_skip_all(self, ledger_path):
        data = _pipeline_data(
            market_temperature_data={"available": False, "status": "insufficient"},
            valuation_data={"available": False, "status": "no_bars", "by_code": {}},
            tail_risk_data={"available": False, "sample_size": 3},
            style_factor_data={"available": False, "style_allocation": {}},
            action_data={"rebalance_signals": []},
        )

        result = signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert result["registered"] == 0
        assert sl.load_signals(ledger_path) == []

    def test_valuation_requires_percentile_available(self, ledger_path):
        data = _pipeline_data()
        data["valuation_data"]["by_code"]["600000"]["percentile_available"] = False

        result = signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert sl.SIGNAL_VALUATION not in result["by_type"]

    def test_tail_risk_below_min_sample_skipped(self, ledger_path):
        data = _pipeline_data()
        data["tail_risk_data"]["sample_size"] = signal_record.MIN_TAIL_RISK_SAMPLE - 1

        result = signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert sl.SIGNAL_TAIL_RISK not in result["by_type"]

    def test_aggregate_summary_row_skipped(self, ledger_path):
        """再平衡 >3 条时产出聚合提示行（无 code），不得入账。"""
        data = _pipeline_data()
        data["action_data"]["rebalance_signals"] = [{"summary": True, "count": 4, "message": "..."}]

        result = signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert sl.SIGNAL_REBALANCE_OVERFLOW not in result["by_type"]

    def test_rows_without_code_skipped(self, ledger_path):
        data = _pipeline_data()
        data["action_data"]["rebalance_signals"] = [
            {"name": "无代码行", "weight": 0.3, "threshold": 0.15},
            {},
        ]

        result = signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert sl.SIGNAL_REBALANCE_OVERFLOW not in result["by_type"]


class TestSourceLabeling:
    """live/demo 判定（持仓级传 freshness，组合级乐观缺省）。"""

    def test_all_fresh_marks_everything_live(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        assert all(r["data_source"] == sl.DATA_SOURCE_LIVE for r in sl.load_signals(ledger_path))

    def test_stale_holding_marks_only_that_code_demo(self, ledger_path):
        data = _pipeline_data()
        data["data_freshness"]["items"][0]["freshness"] = "stale"  # 600000 估值分位

        signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        records = _records_by_type(ledger_path)
        assert records[sl.SIGNAL_VALUATION][0]["data_source"] == sl.DATA_SOURCE_DEMO
        assert records[sl.SIGNAL_VALUATION][0]["source_reason"].startswith("行情")
        # 同批其他标的/组合级信号不受影响
        assert records[sl.SIGNAL_REBALANCE_OVERFLOW][0]["data_source"] == sl.DATA_SOURCE_LIVE
        assert records[sl.SIGNAL_TAIL_RISK][0]["data_source"] == sl.DATA_SOURCE_LIVE

    def test_missing_freshness_item_keeps_portfolio_level_live(self, ledger_path):
        """组合级/指数级无逐品种条目 → 乐观缺省 live（有明确 reason）。"""
        data = _pipeline_data()
        data["data_freshness"] = {"available": False, "items": []}

        signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        records = _records_by_type(ledger_path)
        assert records[sl.SIGNAL_MARKET_TEMPERATURE][0]["data_source"] == sl.DATA_SOURCE_LIVE
        assert records[sl.SIGNAL_STYLE_FACTOR][0]["source_reason"] == sl.REASON_LIVE_NO_FRESHNESS
        # 持仓级因无 freshness 条目同样落到乐观缺省（非降级路径）
        assert records[sl.SIGNAL_VALUATION][0]["data_source"] == sl.DATA_SOURCE_LIVE

    def test_index_degradation_marks_temperature_and_style_demo(self, ledger_path):
        data = _pipeline_data()
        data["data_degradation"] = [
            {"source_key": "index_history_tencent_sh000300", "degraded": True},
        ]

        signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        records = _records_by_type(ledger_path)
        assert records[sl.SIGNAL_MARKET_TEMPERATURE][0]["data_source"] == sl.DATA_SOURCE_DEMO
        assert records[sl.SIGNAL_STYLE_FACTOR][0]["source_reason"] == sl.REASON_DEGRADED
        assert records[sl.SIGNAL_VALUATION][0]["data_source"] == sl.DATA_SOURCE_LIVE

    def test_per_code_degradation_matches_by_suffix(self, ledger_path):
        data = _pipeline_data()
        data["data_degradation"] = [
            {"source_key": "price_stock_600000", "degraded": True},
        ]

        signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        records = _records_by_type(ledger_path)
        assert records[sl.SIGNAL_VALUATION][0]["data_source"] == sl.DATA_SOURCE_DEMO
        assert records[sl.SIGNAL_REBALANCE_OVERFLOW][0]["data_source"] == sl.DATA_SOURCE_LIVE

    def test_price_degradation_marks_tail_risk_demo(self, ledger_path):
        data = _pipeline_data()
        data["data_degradation"] = [{"source_key": "price_fund_000001", "degraded": True}]

        signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert _records_by_type(ledger_path)[sl.SIGNAL_TAIL_RISK][0]["data_source"] == sl.DATA_SOURCE_DEMO

    def test_undegraded_events_ignored(self, ledger_path):
        data = _pipeline_data()
        data["data_degradation"] = [{"source_key": "price_stock_600000", "degraded": False}]

        signal_record.register_deterministic_signals(data, report_date=REPORT_DATE, path=ledger_path)

        assert _records_by_type(ledger_path)[sl.SIGNAL_VALUATION][0]["data_source"] == sl.DATA_SOURCE_LIVE


class TestIdempotenceAndFlag:
    """幂等与开关。"""

    def test_second_run_same_date_registers_nothing(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        again = signal_record.register_deterministic_signals(
            _pipeline_data(), report_date=REPORT_DATE, path=ledger_path
        )

        assert again["registered"] == 0
        assert again["skipped"] == 5
        assert len(sl.load_signals(ledger_path)) == 5

    def test_next_date_registers_again(self, ledger_path):
        signal_record.register_deterministic_signals(_pipeline_data(), report_date=REPORT_DATE, path=ledger_path)

        nxt = signal_record.register_deterministic_signals(_pipeline_data(), report_date="2026-09-11", path=ledger_path)

        assert nxt["registered"] == 5
        assert len(sl.load_signals(ledger_path)) == 10

    def test_flag_off_is_noop(self, ledger_path):
        set_feature_enabled(sl.FEATURE_FLAG, False)

        result = signal_record.register_deterministic_signals(
            _pipeline_data(), report_date=REPORT_DATE, path=ledger_path
        )

        assert result == {"registered": 0, "skipped": 0, "by_type": {}}
        assert sl.load_signals(ledger_path) == []

    @pytest.mark.parametrize("bad", [None, [], "text", 42])
    def test_non_dict_pipeline_data_is_noop(self, bad, ledger_path):
        result = signal_record.register_deterministic_signals(bad, report_date=REPORT_DATE, path=ledger_path)

        assert result == {"registered": 0, "skipped": 0, "by_type": {}}

    def test_report_date_defaults_to_today(self, ledger_path):
        from datetime import datetime

        signal_record.register_deterministic_signals(_pipeline_data(), path=ledger_path)

        records = sl.load_signals(ledger_path)
        assert records
        assert records[0]["report_date"] == datetime.now().strftime("%Y-%m-%d")
