"""确定性数值信号账本 — 边缘/畸形输入矩阵（语义名 signal_ledger）。

覆盖：未识别新鲜度取值的保守缺省、账本路径为目录/不可写、超长与 Unicode 字段、
缺字段记录、显式集合夹带非对象、非有限数值、序列化不可表示的 detail、空报告日、
越界方向值、超大记录量。全部纯文件/内存运算，零网络零 LLM。

运行：
  pytest src/test/unit/core/test_signal_ledger_edge.py -v
"""

from __future__ import annotations

import json
import os

import pytest

from src.python.config.features import reset_feature_flags, set_feature_enabled
from src.python.core import signal_ledger as sl

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


@pytest.fixture(autouse=True)
def _reset_flags():
    yield
    reset_feature_flags()


def _minimal(signal_type=sl.SIGNAL_TAIL_RISK, rating="尾部正常", **overrides):
    kwargs = dict(
        signal_type=signal_type,
        report_date="2026-09-10",
        rating=rating,
        value=-1.0,
    )
    kwargs.update(overrides)
    return sl.build_signal(**kwargs)


class TestUnrecognizedFreshness:
    """未识别的新鲜度取值 → 保守判 demo（只有可证明实时才算 live）。"""

    @pytest.mark.parametrize("freshness", ["unknown", "FRESH", "", "partially_stale"])
    def test_unrecognized_value_defaults_to_demo(self, freshness):
        source, reason = sl.resolve_data_source(freshness=freshness)

        assert source == sl.DATA_SOURCE_DEMO
        assert reason.startswith("行情")

    def test_unrecognized_value_reason_echoes_raw_value(self):
        _, reason = sl.resolve_data_source(freshness="unknown")

        assert "unknown" in reason

    def test_known_non_live_labels_use_canonical_wording(self):
        """标签取自 core.data_freshness.FRESHNESS_LABELS，不另写一份文案。"""
        from src.python.core.data_freshness import FRESHNESS_LABELS

        _, reason = sl.resolve_data_source(freshness="cached")

        assert FRESHNESS_LABELS["cached"] in reason


class TestLedgerPathHostility:
    """账本路径不可用时不崩、不误报。"""

    def test_path_is_directory_returns_empty(self, tmp_path):
        assert sl.load_signals(str(tmp_path)) == []

    def test_append_to_directory_path_does_not_raise(self, tmp_path):
        """目标路径是已存在目录 → os.replace 失败，原子原语须吞掉并清理临时文件。"""
        target = tmp_path / "ledger_dir"
        target.mkdir()

        sl.append_signals([_minimal()], path=str(target))  # 不应抛出

        assert [p for p in os.listdir(tmp_path) if p.startswith(".signal_ledger_")] == []

    def test_unreadable_ledger_treated_as_absent(self, tmp_path, monkeypatch):
        target = tmp_path / "signals.jsonl"
        target.write_text('{"id": "x"}\n', encoding="utf-8")
        monkeypatch.setattr(os.path, "isfile", lambda _p: False)

        assert sl.load_signals(str(target)) == []


class TestDegenerateRecords:
    """字段缺失/畸形记录的折叠容错。"""

    def test_fold_ignores_non_dict_entries(self, tmp_path):
        mixed = [None, "text", 42, _minimal()]

        folded = sl.fold_signals(mixed)

        assert folded["records"] == 1

    def test_fold_survives_records_missing_all_fields(self):
        folded = sl.fold_signals([{}, {}, {}], live_only=False)

        assert folded["records"] == 3
        assert folded["by_type"] == {}
        assert folded["dates"] == []

    def test_records_without_source_label_never_count_as_live(self):
        """缺 data_source 的记录既非 live 也非 demo：live_only 下不计入。"""
        folded = sl.fold_signals([{}, {}, {}])

        assert folded["records"] == 0
        assert folded["live_count"] == 0

    def test_fold_ignores_unknown_signal_type(self):
        """未注册类型不进 by_type（保持 SIGNAL_TYPE_ORDER 的稳定输出）。"""
        folded = sl.fold_signals([_minimal(signal_type="brand_new_type")], live_only=False)

        assert folded["by_type"] == {}

    def test_fold_dates_skip_blank_report_date(self):
        folded = sl.fold_signals([_minimal(report_date="")], live_only=False)

        assert folded["dates"] == []
        assert folded["first_date"] == ""

    def test_summary_omits_value_text_when_value_absent(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [_minimal(value=None) for _ in range(3)]

        block = sl.summary_block(records)

        assert "尾部正常" in block
        assert "None" not in block


class TestFieldExtremes:
    """超长/Unicode/越界字段。"""

    def test_long_unicode_rating_roundtrips(self):
        rating = "极" * 2000 + " 📉"

        record = _minimal(rating=rating)

        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True))["rating"] == rating

    def test_deeply_nested_detail_roundtrips(self):
        detail = {"level": {"a": [1, 2, {"b": "深" * 500}]}}

        record = sl.build_signal(
            signal_type=sl.SIGNAL_STYLE_FACTOR,
            report_date="2026-09-10",
            rating="价值",
            detail=detail,
        )

        assert json.loads(json.dumps(record, ensure_ascii=False))["detail"] == detail

    def test_non_serializable_detail_raises_before_write(self, tmp_path):
        """detail 不可序列化是编程错误：须显式失败而非静默丢记录（seam 侧兜底）。"""
        record = sl.build_signal(
            signal_type=sl.SIGNAL_STYLE_FACTOR,
            report_date="2026-09-10",
            rating="价值",
            detail={"bad": object()},
        )

        with pytest.raises(TypeError):
            sl.append_signals([record], path=str(tmp_path / "signals.jsonl"))

    def test_out_of_range_direction_passes_through_unvalidated(self):
        """方向值不做范围校验（core 保持通用形状，语义由 report 层保证）。"""
        assert _minimal(direction=99)["direction"] == 99

    def test_blank_report_date_still_produces_id(self):
        assert _minimal(report_date="")["id"] == "|tail_risk|portfolio"

    def test_large_batch_single_atomic_write(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        batch = [_minimal(subject=f"{600000 + i:06d}", signal_type=sl.SIGNAL_VALUATION) for i in range(500)]

        appended = sl.append_signals(batch, path=path)

        assert len(appended) == 500
        assert len(sl.load_signals(path)) == 500
        assert [p for p in os.listdir(tmp_path) if p.startswith(".signal_ledger_")] == []


class TestSummaryBoundary:
    """摘要/后缀的边界态。"""

    def test_inactive_flag_beats_explicit_signals(self):
        records = [_minimal() for _ in range(5)]

        assert sl.summary_block(records) == ""
        assert sl.summary_cache_suffix(records) == ""

    def test_exactly_at_sample_threshold_emits_block(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [_minimal(report_date=f"2026-09-{10 + i}", subject=f"60000{i}") for i in range(sl.MIN_SUMMARY_SAMPLE)]

        assert sl.summary_block(records) != ""

    def test_one_below_threshold_is_silent(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [
            _minimal(report_date=f"2026-09-{10 + i}", subject=f"60000{i}") for i in range(sl.MIN_SUMMARY_SAMPLE - 1)
        ]

        assert sl.summary_block(records) == ""

    def test_suffix_is_empty_when_block_empty(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)

        assert sl.summary_cache_suffix([_minimal()]) == ""
