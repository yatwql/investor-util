"""决策跨期反思账本核心 — 单元测试。

覆盖：事件追加/读取/损坏行容错、fold 统计（命中率/样本门槛/方向符号 alpha/
按载体聚合）、方向结算纯判定、教训文本与指纹后缀（空态/稳定态/随结算变化）。

运行：
  pytest src/test/unit/core/test_decision_ledger.py -v
"""

from __future__ import annotations

import json
import pytest

from src.python.core import decision_ledger as dl

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


def _w(ledger_path, events):
    """直接以显式路径写入一组事件行（绕过原子追加，便于构造畸形数据）。"""
    import os

    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    with open(ledger_path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")


def _settle(decision_id, outcome, raw, bench=None, path=None, hit=None, horizon=10):
    dl.append_settlement(
        decision_id=decision_id,
        raw_return=raw,
        outcome=outcome,
        direction_hit=hit,
        bench_return=bench,
        horizon_bars=horizon,
        path=path,
    )


class TestAppendAndLoad:
    """事件追加与读取。"""

    def test_append_decision_persists_pending(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        did = dl.append_decision(
            code="040046",
            name="华夏回报",
            direction=dl.DIRECTION_SHORT,
            carrier=dl.CARRIER_EXPERT_REVIEW,
            detail="止盈",
            magnitude="high",
            baseline_close=1.5,
            path=lp,
        )
        assert isinstance(did, str) and len(did) == 12
        events = dl.load_events(lp)
        assert len(events) == 1
        ev = events[0]
        assert ev["event"] == dl.EVENT_DECISION
        assert ev["decision_id"] == did
        assert ev["status"] == "pending"
        assert ev["direction"] == dl.DIRECTION_SHORT
        assert ev["baseline_close"] == 1.5

    def test_append_settlement_roundtrip(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        did = dl.append_decision(code="600519", name="贵州茅台", direction=dl.DIRECTION_LONG, path=lp)
        _settle(did, raw=-0.02, outcome=dl.OUTCOME_MISS, hit=False, path=lp)
        events = dl.load_events(lp)
        assert [e["event"] for e in events] == [dl.EVENT_DECISION, dl.EVENT_SETTLEMENT]
        s = events[1]
        assert s["decision_id"] == did
        assert s["direction_hit"] is False
        assert s["outcome"] == dl.OUTCOME_MISS

    def test_load_missing_file_returns_empty(self, tmp_path):
        assert dl.load_events(str(tmp_path / "nope.jsonl")) == []

    def test_load_skips_corrupt_lines(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        _w(lp, [{"event": dl.EVENT_DECISION, "decision_id": "abc123", "junk": True}])
        with open(lp, "a", encoding="utf-8") as f:
            f.write("{ not json }\n")
            f.write("\n")
        did = dl.append_decision(code="000001", name="平安银行", direction=dl.DIRECTION_LONG, path=lp)
        events = dl.load_events(lp)
        # 两条有效行（含刚追加的）+ 一条损坏行被跳过
        assert len(events) == 2
        assert events[-1]["decision_id"] == did

    def test_default_path_isolated_by_conftest(self):
        """默认路径被 _isolate_sensitive_paths 重定向到临时目录（非真实 data/state）。"""
        dl.append_decision(code="159915", name="创业板ETF", direction=dl.DIRECTION_LONG, carrier=dl.CARRIER_REBALANCE)
        events = dl.load_events()
        assert len(events) == 1
        # 确认不落到仓库真实 data/state 下
        from src.python.core import decision_ledger as mod

        assert "decision_ledger.jsonl" in mod._DECISION_LEDGER_FILE
        assert mod._DECISION_LEDGER_FILE.startswith("/tmp") or "tmp" in mod._DECISION_LEDGER_FILE


class TestSameDayPending:
    """同日(报告日, code, carrier) pending 防重判定（报告重生成防重复登记）。"""

    def test_true_when_same_day_same_carrier_pending(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        dl.append_decision(
            code="040046",
            name="华夏回报",
            direction=dl.DIRECTION_SHORT,
            carrier=dl.CARRIER_EXPERT_REVIEW,
            report_date="2026-09-01",
            path=lp,
        )
        assert dl.same_day_pending_exists(
            code="040046", carrier=dl.CARRIER_EXPERT_REVIEW, report_date="2026-09-01", path=lp
        )

    def test_false_when_settled(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        did = dl.append_decision(
            code="040046",
            name="华夏回报",
            direction=dl.DIRECTION_SHORT,
            carrier=dl.CARRIER_EXPERT_REVIEW,
            report_date="2026-09-01",
            path=lp,
        )
        dl.append_settlement(decision_id=did, raw_return=-0.02, outcome=dl.OUTCOME_MISS, path=lp)
        assert not dl.same_day_pending_exists(
            code="040046", carrier=dl.CARRIER_EXPERT_REVIEW, report_date="2026-09-01", path=lp
        )

    def test_false_different_report_date(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        dl.append_decision(
            code="040046",
            name="华夏回报",
            direction=dl.DIRECTION_SHORT,
            carrier=dl.CARRIER_EXPERT_REVIEW,
            report_date="2026-09-01",
            path=lp,
        )
        # 跨日重跑（新 report_date）→ 不误伤：视为新一轮判断
        assert not dl.same_day_pending_exists(
            code="040046", carrier=dl.CARRIER_EXPERT_REVIEW, report_date="2026-09-02", path=lp
        )

    def test_false_different_carrier_or_code(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        dl.append_decision(
            code="040046",
            name="华夏回报",
            direction=dl.DIRECTION_SHORT,
            carrier=dl.CARRIER_REBALANCE,
            report_date="2026-09-01",
            path=lp,
        )
        assert not dl.same_day_pending_exists(
            code="040046", carrier=dl.CARRIER_EXPERT_REVIEW, report_date="2026-09-01", path=lp
        )
        assert not dl.same_day_pending_exists(
            code="600519", carrier=dl.CARRIER_REBALANCE, report_date="2026-09-01", path=lp
        )

    def test_false_without_report_date(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        dl.append_decision(
            code="040046", name="华夏回报", direction=dl.DIRECTION_SHORT, carrier=dl.CARRIER_REBALANCE, path=lp
        )
        assert not dl.same_day_pending_exists(code="040046", carrier=dl.CARRIER_REBALANCE, report_date=None, path=lp)


class TestClassifyOutcome:
    """方向结算纯判定。"""

    def test_short_hit_when_falling(self):
        assert dl.classify_direction_outcome(-0.05, dl.DIRECTION_SHORT) == (dl.OUTCOME_HIT, True)

    def test_short_miss_when_rising(self):
        assert dl.classify_direction_outcome(0.05, dl.DIRECTION_SHORT) == (dl.OUTCOME_MISS, False)

    def test_long_hit_when_rising(self):
        assert dl.classify_direction_outcome(0.05, dl.DIRECTION_LONG) == (dl.OUTCOME_HIT, True)

    def test_long_miss_when_falling(self):
        assert dl.classify_direction_outcome(-0.05, dl.DIRECTION_LONG) == (dl.OUTCOME_MISS, False)

    def test_flat_below_threshold(self):
        assert dl.classify_direction_outcome(0.005, dl.DIRECTION_SHORT) == (dl.OUTCOME_FLAT, None)

    def test_gap_when_no_return(self):
        assert dl.classify_direction_outcome(None, dl.DIRECTION_SHORT) == (dl.OUTCOME_GAP, None)

    def test_flat_direction_never_hits(self):
        assert dl.classify_direction_outcome(-0.05, dl.DIRECTION_FLAT) == (dl.OUTCOME_FLAT, None)


class TestFoldStats:
    """fold 统计正确性。"""

    def test_hit_miss_accuracy(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        for i, (code, direction, raw, outcome) in enumerate(
            [
                ("600519", dl.DIRECTION_LONG, 0.03, dl.OUTCOME_HIT),
                ("000858", dl.DIRECTION_LONG, -0.02, dl.OUTCOME_MISS),
                ("040046", dl.DIRECTION_SHORT, -0.04, dl.OUTCOME_HIT),
                ("159915", dl.DIRECTION_SHORT, 0.02, dl.OUTCOME_MISS),
            ]
        ):
            did = dl.append_decision(code=code, name=code, direction=direction, path=lp)
            _settle(did, outcome=outcome, raw=raw, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["settled_count"] == 4
        assert stats["pending_count"] == 0
        assert stats["counts"] == {"hit": 2, "miss": 2, "flat": 0, "gap": 0}
        assert stats["directional_total"] == 4
        assert stats["direction_accuracy"] == 0.5
        assert stats["sample_sufficient"] is False  # 4 < 20

    def test_flat_and_gap_excluded_from_accuracy(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        # 2 hit + 1 miss + 2 flat + 1 gap → accuracy 只按 3 个方向样本算
        cases = [
            (dl.DIRECTION_LONG, 0.05, dl.OUTCOME_HIT),
            (dl.DIRECTION_SHORT, -0.06, dl.OUTCOME_HIT),
            (dl.DIRECTION_LONG, -0.03, dl.OUTCOME_MISS),
            (dl.DIRECTION_LONG, 0.002, dl.OUTCOME_FLAT),
            (dl.DIRECTION_SHORT, -0.001, dl.OUTCOME_FLAT),
            (dl.DIRECTION_SHORT, None, dl.OUTCOME_GAP),
        ]
        for direction, raw, outcome in cases:
            did = dl.append_decision(code="600000", name="x", direction=direction, path=lp)
            _settle(did, outcome=outcome, raw=raw, path=lp, hit=(True if outcome == dl.OUTCOME_HIT else False))
        stats = dl.fold_ledger(path=lp)
        assert stats["counts"] == {"hit": 2, "miss": 1, "flat": 2, "gap": 1}
        assert stats["directional_total"] == 3
        assert stats["direction_accuracy"] == pytest.approx(2 / 3)

    def test_hold_neutral_excluded(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        did = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_FLAT, path=lp)
        _settle(did, outcome=dl.OUTCOME_HIT, raw=-0.05, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["settled_count"] == 1
        assert stats["directional_total"] == 0
        assert stats["direction_accuracy"] is None

    def test_pending_not_settled_kept_pending(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_LONG, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["pending_count"] == 1
        assert stats["settled_count"] == 0
        assert stats["decisions"][0]["status"] == "pending"
        assert "settlement" not in stats["decisions"][0]

    def test_alpha_direction_signed(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        # 看空 -5%，基准 -3% → 跑赢基准 → (raw-bench)*sign = (-0.05-(-0.03))*(-1) = +0.02
        d1 = dl.append_decision(code="A", name="a", direction=dl.DIRECTION_SHORT, path=lp)
        _settle(d1, outcome=dl.OUTCOME_HIT, raw=-0.05, bench=-0.03, path=lp)
        # 看空 -5%，基准 -8% → 跑输基准 → (-0.05-(-0.08))*(-1) = -0.03
        d2 = dl.append_decision(code="B", name="b", direction=dl.DIRECTION_SHORT, path=lp)
        _settle(d2, outcome=dl.OUTCOME_HIT, raw=-0.05, bench=-0.08, path=lp)
        # 看多 +4%，基准 +1% → (+0.04-0.01)*(+1) = +0.03
        d3 = dl.append_decision(code="C", name="c", direction=dl.DIRECTION_LONG, path=lp)
        _settle(d3, outcome=dl.OUTCOME_HIT, raw=0.04, bench=0.01, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["alpha_mean"] == pytest.approx((0.02 - 0.03 + 0.03) / 3)

    def test_flat_outcome_not_counted_in_alpha(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        d1 = dl.append_decision(code="A", name="a", direction=dl.DIRECTION_SHORT, path=lp)
        _settle(d1, outcome=dl.OUTCOME_FLAT, raw=0.001, bench=0.0, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["alpha_mean"] is None

    def test_by_carrier_aggregation(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        for carrier in (dl.CARRIER_EXPERT_REVIEW, dl.CARRIER_REBALANCE):
            for direction, raw, outcome in [
                (dl.DIRECTION_LONG, 0.03, dl.OUTCOME_HIT),
                (dl.DIRECTION_SHORT, 0.02, dl.OUTCOME_MISS),
            ]:
                did = dl.append_decision(code="600000", name="x", direction=direction, carrier=carrier, path=lp)
                _settle(did, outcome=outcome, raw=raw, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert set(stats["by_carrier"]) == {dl.CARRIER_EXPERT_REVIEW, dl.CARRIER_REBALANCE}
        for c in stats["by_carrier"].values():
            assert c["hit"] == 1 and c["miss"] == 1
            assert c["directional"] == 2
            assert c["accuracy"] == 0.5


class TestSampleSufficiency:
    """有效样本门槛（MEANINGFUL_SAMPLE=20）。"""

    def test_exactly_20_is_sufficient(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        for i in range(20):
            d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_LONG, path=lp)
            if i % 2:
                _settle(d, outcome=dl.OUTCOME_HIT, raw=0.03, hit=True, path=lp)
            else:
                _settle(d, outcome=dl.OUTCOME_MISS, raw=-0.03, hit=False, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["directional_total"] == 20
        assert stats["sample_sufficient"] is True
        assert stats["direction_accuracy"] == 0.5


class TestLessons:
    """教训文本与指纹后缀。"""

    def _seed_hits(self, lp, n=3):
        for i in range(n):
            d = dl.append_decision(code=f"60000{i}", name=f"股{i}", direction=dl.DIRECTION_SHORT, path=lp)
            _settle(d, outcome=dl.OUTCOME_HIT, raw=-0.03 - i * 0.01, path=lp, horizon=10)

    def test_no_lessons_below_min_sample(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_SHORT, path=lp)
        _settle(d, outcome=dl.OUTCOME_HIT, raw=-0.03, path=lp)
        assert dl.lessons_block(path=lp) == ""

    def test_lessons_block_emitted_above_min(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        self._seed_hits(lp)
        block = dl.lessons_block(path=lp)
        assert block
        assert "历史决策复盘" in block
        assert "非回测" in block
        # 3 样本 < 20 → 给出 hit/total 而非百分比结论
        assert "3/3" in block
        assert "600002" in block  # 案例含 code

    def test_suffix_empty_when_no_block(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        assert dl.lessons_cache_suffix(path=lp) == ""

    def test_suffix_stable_and_changes_with_settlement(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        self._seed_hits(lp)
        suffix1 = dl.lessons_cache_suffix(path=lp)
        assert suffix1.startswith("_lr")
        assert len(suffix1) == 3 + 12
        # 相同账本 → 后缀稳定
        assert dl.lessons_cache_suffix(path=lp) == suffix1
        # 新增一条相反结果结算 → 教训文本变 → 后缀变
        d = dl.append_decision(code="510300", name="沪深300ETF", direction=dl.DIRECTION_LONG, path=lp)
        _settle(d, outcome=dl.OUTCOME_MISS, raw=-0.05, path=lp, horizon=10)
        suffix2 = dl.lessons_cache_suffix(path=lp)
        assert suffix2 != suffix1
        assert suffix2.startswith("_lr")

    def test_suffix_covers_debate_procon_suffix(self, tmp_path):
        """教训指纹后缀以 _lr 开头，与既有辩论 _cq 后缀风格一致、可拼接。"""
        lp = str(tmp_path / "ledger.jsonl")
        self._seed_hits(lp)
        combined = "base_cq" + dl.lessons_cache_suffix(path=lp)
        assert combined.startswith("base_cq_lr")
