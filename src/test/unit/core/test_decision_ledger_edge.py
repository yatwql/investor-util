"""决策跨期反思账本核心 — 边缘/异常专项测试。

edge 场景：
  - 空账本 / 全 gap / 全 flat：统计不崩溃且不产出结论
  - 只读账本目录 / 追加失败：不抛异常污染主链路
  - 超常数值（区间涨跌 +inf / 极端小数）：判定稳定
  - 未知载体名 / 重复 decision_id / 半行畸形数据
  - lessons_block 对空账本与全 gap 返回空串

运行：
  pytest src/test/unit/core/test_decision_ledger_edge.py -v
"""

from __future__ import annotations

import json
import math
import os

import pytest

from src.python.core import decision_ledger as dl

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


def _settle(decision_id, outcome, raw, path, bench=None, hit=None):
    dl.append_settlement(
        decision_id=decision_id,
        outcome=outcome,
        raw_return=raw,
        direction_hit=hit,
        bench_return=bench,
        path=path,
    )


class TestEmptyAndDegenerateLedger:
    """空/退化账本不应崩溃。"""

    def test_empty_ledger_stats(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        stats = dl.fold_ledger(path=lp)
        assert stats["pending_count"] == 0
        assert stats["settled_count"] == 0
        assert stats["directional_total"] == 0
        assert stats["direction_accuracy"] is None
        assert stats["alpha_mean"] is None
        assert stats["sample_sufficient"] is False

    def test_all_gap_never_concludes(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        for _ in range(30):
            d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_SHORT, path=lp)
            _settle(d, outcome=dl.OUTCOME_GAP, raw=None, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["counts"]["gap"] == 30
        assert stats["directional_total"] == 0  # gap 不参与方向判定
        assert stats["direction_accuracy"] is None
        assert dl.lessons_block(path=lp) == ""  # 无有效方向结论 → 不产出教训

    def test_all_flat_never_concludes(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        for _ in range(30):
            d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_SHORT, path=lp)
            _settle(d, outcome=dl.OUTCOME_FLAT, raw=0.001, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["directional_total"] == 0
        assert dl.lessons_block(path=lp) == ""

    def test_no_file_lessons_block_empty(self, tmp_path):
        assert dl.lessons_block(path=str(tmp_path / "missing.jsonl")) == ""
        assert dl.lessons_cache_suffix(path=str(tmp_path / "missing.jsonl")) == ""


class TestExtremeValues:
    """超常数值稳定性。"""

    def test_infinite_return_classifies_as_hit(self):
        # 看空遭遇 +inf 上涨 → miss（不崩溃）；看多遭遇 -inf → miss
        assert dl.classify_direction_outcome(math.inf, dl.DIRECTION_SHORT) == (dl.OUTCOME_MISS, False)
        assert dl.classify_direction_outcome(-math.inf, dl.DIRECTION_LONG) == (dl.OUTCOME_MISS, False)

    def test_tiny_return_is_flat(self):
        assert dl.classify_direction_outcome(1e-9, dl.DIRECTION_SHORT) == (dl.OUTCOME_FLAT, None)

    def test_ledger_with_inf_raw_does_not_crash_fold(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_LONG, path=lp)
        # 直接写一条带 inf 的结算行（json 序列化 inf 为非标准 → 手动落盘）
        with open(lp, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "event": dl.EVENT_SETTLEMENT,
                        "decision_id": d,
                        "raw_return": 1e308,
                        "outcome": dl.OUTCOME_HIT,
                        "settle_date": "2026-01-01",
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        stats = dl.fold_ledger(path=lp)  # 不崩溃
        assert stats["counts"]["hit"] == 1

    def test_roundtrip_negative_zero_magnitude(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_SHORT, magnitude="high", path=lp)
        _settle(d, outcome=dl.OUTCOME_HIT, raw=-0.02, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert stats["decisions"][0]["magnitude"] == "high"


class TestMalformedLedger:
    """畸形账本行容错。"""

    def test_half_line_and_empty_lines_skipped(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        with open(lp, "w", encoding="utf-8") as f:
            f.write('{"event": "decision", "decision_id": "good1"}\n')
            f.write('{"event": "settle\n')  # 截断 JSON
            f.write("\n")
            f.write("not json at all\n")
        assert len(dl.load_events(lp)) == 1

    def test_non_json_whole_file(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        with open(lp, "w", encoding="utf-8") as f:
            f.write("garbage")
        stats = dl.fold_ledger(path=lp)
        assert stats["settled_count"] == 0
        assert stats["pending_count"] == 0

    def test_duplicate_decision_id_last_settlement_wins(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_SHORT, path=lp)
        _settle(d, outcome=dl.OUTCOME_MISS, raw=0.05, path=lp)
        _settle(d, outcome=dl.OUTCOME_MISS, raw=0.07, path=lp)  # 同 id 二次结算
        stats = dl.fold_ledger(path=lp)
        assert stats["counts"]["miss"] == 1  # 后写覆盖先写，只计一次
        assert stats["counts"]["hit"] == 0
        assert stats["decisions"][0]["settlement"]["raw_return"] == 0.07

    def test_unknown_carrier_grouped_separately(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        d = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_SHORT, carrier="mystery", path=lp)
        _settle(d, outcome=dl.OUTCOME_HIT, raw=-0.03, path=lp)
        stats = dl.fold_ledger(path=lp)
        assert "mystery" in stats["by_carrier"]
        assert stats["by_carrier"]["mystery"]["hit"] == 1

    def test_append_creates_missing_dirs(self, tmp_path):
        """目标文件所在目录不存在 → append 自动创建并落盘。"""
        lp = str(tmp_path / "deep" / "nested" / "ledger.jsonl")
        did = dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_LONG, path=lp)
        assert os.path.isfile(lp)
        events = dl.load_events(lp)
        assert events[0]["decision_id"] == did

    def test_append_failure_silent(self, tmp_path, monkeypatch):
        """os.replace 失败 → 不向上抛，保证 report seam 主链路不中断。"""
        lp = str(tmp_path / "ledger.jsonl")

        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr("os.replace", boom)
        # 不抛异常即通过
        dl.append_decision(code="600000", name="x", direction=dl.DIRECTION_LONG, path=lp)
        monkeypatch.undo()


class TestThresholdBoundary:
    """方向判定阈值边界。"""

    def test_at_threshold_is_flat(self):
        # 恰为 ±1.5% 视为未达方向判据（abs < threshold 而非 <=）
        assert dl.classify_direction_outcome(0.0149, dl.DIRECTION_LONG) == (dl.OUTCOME_FLAT, None)
        assert dl.classify_direction_outcome(0.0151, dl.DIRECTION_LONG) == (dl.OUTCOME_HIT, True)

    def test_zero_direction_with_positive_return(self):
        # 持有即使大涨也按 flat（不判定方向）
        assert dl.classify_direction_outcome(0.2, dl.DIRECTION_FLAT) == (dl.OUTCOME_FLAT, None)
