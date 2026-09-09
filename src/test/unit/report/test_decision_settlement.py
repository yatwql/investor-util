"""决策跨期反思闭环 — 结算服务单元测试。

覆盖：到期判定（bar 数门槛）、hit/miss/flat/gap、基准涨跌计算、幂等（已结不
重结）、开关关闭无感、行情注入失败降级。全部 mock 行情，防真网络。

运行：
  pytest src/test/unit/report/test_decision_settlement.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import set_feature_enabled, reset_feature_flags
from src.python.core import decision_ledger as dl
from src.python.report import decision_settlement as ds

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

# 决策日与固定交易日窗口：决策日 08-20，其后 08-21/22/25/26/27 恰好 5 个交易日
_REP = "2026-08-20"
_DATES = ["2026-08-18", "2026-08-21", "2026-08-22", "2026-08-25", "2026-08-26", "2026-08-27"]


@pytest.fixture(autouse=True)
def _enable_flag():
    set_feature_enabled("decision_reflection", True)
    yield
    reset_feature_flags()


def _bars(dates, closes):
    """构造 {date, close} 升序序列。"""
    return [{"date": d, "close": c} for d, c in zip(dates, closes)]


def _mature(closes):
    """固定成熟窗口序列：含 08-20 决策日之后恰好 5 个交易日的价格。"""
    assert len(closes) == len(_DATES)
    return _bars(_DATES, closes)


class _FakePrices:
    def __init__(self, series):
        self._series = series

    def __call__(self, code, name, days):
        return self._series


class _FakeIndex:
    def __init__(self, series):
        self._series = series

    def __call__(self, code, days):
        return self._series


def _seed_decision(lp, *, code="600000", direction=dl.DIRECTION_SHORT, rep=_REP, baseline=10.0):
    return dl.append_decision(
        code=code,
        name="test",
        direction=direction,
        carrier=dl.CARRIER_DISCIPLINE,
        report_date=rep,
        baseline_close=baseline,
        path=lp,
    )


class TestSettleOneHelpers:
    """内部序列取值 helper。"""

    def test_latest_close(self):
        assert ds._latest_close(_bars(["2026-01-01", "2026-01-02"], [1.0, 1.1])) == 1.1
        assert ds._latest_close([]) is None
        assert ds._latest_close([{"date": "x", "close": 0}]) is None  # 无效 close 跳过

    def test_series_at_date_locf(self):
        s = _bars(["2026-01-01", "2026-01-02", "2026-01-05"], [1.0, 1.1, 1.2])
        assert ds._series_at_date(s, "2026-01-02") == 1.1
        assert ds._series_at_date(s, "2026-01-03") == 1.1  # last-close 对齐
        assert ds._series_at_date(s, "2025-12-31") is None  # 早于首日


class TestSettleMaturity:
    """成熟度：决策日后 bar 数 < horizon 则不结算。"""

    def test_not_mature_deferred(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-09-01", baseline=10.0)  # direction short
        # 决策日 09-01 之后仅 3 个 bar（09-02/03/04 < 5）→ 未到期
        series = _bars(["2026-08-25", "2026-09-02", "2026-09-03", "2026-09-04"], [10.0, 9.8, 9.7, 9.6])
        out = ds.settle_pending_decisions(
            report_date="2026-09-09",
            ledger_path=lp,
            price_series_fn=_FakePrices(series),
            index_series_fn=_FakeIndex([]),
        )
        assert out["settled"] == 0
        assert out["deferred"] == 1
        assert dl.fold_ledger(path=lp)["settled_count"] == 0

    def test_mature_hit(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0)  # short
        out = ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices(_mature([10.0, 9.9, 9.8, 9.7, 9.6, 9.5])),
            index_series_fn=_FakeIndex([]),
        )
        assert out["settled"] == 1
        assert out["summary"][0]["outcome"] == dl.OUTCOME_HIT
        assert out["summary"][0]["raw_return"] == pytest.approx(9.5 / 10.0 - 1)
        # 已结 → 幂等：再次调用不重结
        out2 = ds.settle_pending_decisions(
            report_date="2026-08-29",
            ledger_path=lp,
            price_series_fn=_FakePrices(_mature([10.0, 9.9, 9.8, 9.7, 9.6, 9.5])),
            index_series_fn=_FakeIndex([]),
        )
        assert out2["settled"] == 0


class TestSettleOutcomes:
    """hit/miss/flat 判定。"""

    def _one(self, tmp_path, closes, direction=dl.DIRECTION_SHORT):
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, direction=direction, baseline=10.0)
        return ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices(_mature(closes)),
            index_series_fn=_FakeIndex([]),
        )

    def test_short_hit_on_decline(self, tmp_path):
        out = self._one(tmp_path, [10.0, 9.9, 9.8, 9.7, 9.6, 9.5])
        assert out["settled"] == 1
        assert out["summary"][0]["outcome"] == dl.OUTCOME_HIT

    def test_short_miss_on_rise(self, tmp_path):
        out = self._one(tmp_path, [10.0, 10.2, 10.4, 10.6, 10.8, 11.0])
        assert out["summary"][0]["outcome"] == dl.OUTCOME_MISS

    def test_flat_below_threshold(self, tmp_path):
        out = self._one(tmp_path, [10.0, 10.0, 10.01, 10.0, 10.01, 10.0])
        assert out["summary"][0]["outcome"] == dl.OUTCOME_FLAT

    def test_long_hit_on_rise(self, tmp_path):
        out = self._one(tmp_path, [10.0, 10.2, 10.4, 10.6, 10.8, 11.0], direction=dl.DIRECTION_LONG)
        assert out["summary"][0]["outcome"] == dl.OUTCOME_HIT

    def test_gap_when_no_price(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0)
        out = ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices([]),  # 全链路无行情
            index_series_fn=_FakeIndex([]),
        )
        assert out["settled"] == 0
        assert out["deferred"] == 1

    def test_hold_neutral_skipped(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        dl.append_decision(
            code="600000",
            name="x",
            direction=dl.DIRECTION_FLAT,
            carrier=dl.CARRIER_EXPERT_REVIEW,
            report_date="2026-08-20",
            baseline_close=10.0,
            path=lp,
        )
        out = ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices(_mature([10.0, 10.2, 10.4, 10.6, 10.8, 11.0])),
            index_series_fn=_FakeIndex([]),
        )
        assert out["settled"] == 0
        assert out["skipped"] == 1


class TestSettleBenchmark:
    """基准（沪深300）区间涨跌。"""

    def test_benchmark_computed(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0)  # short
        # 基准：决策日(LOCF 08-18) close=4000，末 08-27 close=3800 → -5%
        idx = _bars(["2026-08-18", "2026-08-25", "2026-08-27"], [4000.0, 3900.0, 3800.0])
        out = ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices(_mature([10.0, 9.9, 9.8, 9.7, 9.6, 9.5])),
            index_series_fn=_FakeIndex(idx),
        )
        assert out["settled"] == 1
        s = out["summary"][0]
        assert s["bench_return"] == pytest.approx(3800.0 / 4000.0 - 1)
        assert s["outcome"] == dl.OUTCOME_HIT

    def test_benchmark_missing_is_none(self, tmp_path):
        # 基准拉取失败 → bench_return None，方向判定不受影响
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0)
        out = ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices(_mature([10.0, 9.9, 9.8, 9.7, 9.6, 9.5])),
            index_series_fn=_FakeIndex([]),
        )
        assert out["settled"] == 1
        assert out["summary"][0]["bench_return"] is None
        assert out["summary"][0]["outcome"] == dl.OUTCOME_HIT


class TestSettleGating:
    """开关与幂等。"""

    def test_flag_off_noop(self, tmp_path):
        reset_feature_flags()
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0)
        out = ds.settle_pending_decisions(report_date="2026-08-28", ledger_path=lp)
        assert out == {"settled": 0, "ids": [], "deferred": 0, "skipped": 0, "summary": []}

    def test_already_settled_idempotent(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0, code="600001")
        _seed_decision(lp, rep="2026-08-20", baseline=10.0, code="600002")
        price = _mature([10.0, 9.9, 9.8, 9.7, 9.6, 9.5])
        out1 = ds.settle_pending_decisions(
            report_date="2026-08-28",
            ledger_path=lp,
            price_series_fn=_FakePrices(price),
            index_series_fn=_FakeIndex([]),
        )
        assert out1["settled"] == 2
        # 两个已结 → 再次调用 settled=0
        out2 = ds.settle_pending_decisions(
            report_date="2026-08-29",
            ledger_path=lp,
            price_series_fn=_FakePrices(price),
            index_series_fn=_FakeIndex([]),
        )
        assert out2["settled"] == 0
        assert dl.fold_ledger(path=lp)["settled_count"] == 2
