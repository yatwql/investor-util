"""确定性数值信号账本核心 — 单元测试。

覆盖：来源标签四判据（含持仓级/组合级边界）、记录规范化（幂等键/方向缺省/数值
归一）、批量原子追加与幂等去重、容错读取、fold 统计（live_only 切换/live-demo 全量
计数/样本门槛）、摘要文本与缓存指纹后缀（开关关闭/样本不足/内容变化）。

运行：
  pytest src/test/unit/core/test_signal_ledger.py -v
"""

from __future__ import annotations

import json

import pytest

from src.python.config.features import reset_feature_flags, set_feature_enabled
from src.python.core import signal_ledger as sl

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


@pytest.fixture(autouse=True)
def _reset_flags():
    yield
    reset_feature_flags()


def _sig(signal_type, rating, *, date="2026-09-10", subject="", source=sl.DATA_SOURCE_LIVE, value=1.0):
    return sl.build_signal(
        signal_type=signal_type,
        report_date=date,
        rating=rating,
        value=value,
        subject=subject,
        data_source=source,
        source_reason="测试构造",
    )


class TestResolveDataSource:
    """来源标签四判据。"""

    def test_degraded_wins_over_fresh(self):
        assert sl.resolve_data_source(freshness="fresh", degraded=True) == (
            sl.DATA_SOURCE_DEMO,
            sl.REASON_DEGRADED,
        )

    @pytest.mark.parametrize("freshness", ["cached", "stale", "degraded"])
    def test_non_live_freshness_labels_demo(self, freshness):
        source, reason = sl.resolve_data_source(freshness=freshness)

        assert source == sl.DATA_SOURCE_DEMO
        assert reason.startswith("行情")

    def test_fresh_labels_live(self):
        assert sl.resolve_data_source(freshness="fresh") == (
            sl.DATA_SOURCE_LIVE,
            sl.REASON_LIVE_FRESH,
        )

    def test_none_freshness_labels_live_for_portfolio_and_index_scope(self):
        """组合级/指数级无逐品种条目 → 乐观缺省 live（边界见函数 docstring）。"""
        assert sl.resolve_data_source(freshness=None) == (
            sl.DATA_SOURCE_LIVE,
            sl.REASON_LIVE_NO_FRESHNESS,
        )


class TestBuildSignal:
    """记录规范化。"""

    def test_id_is_date_type_subject(self):
        record = _sig(sl.SIGNAL_VALUATION, "低估", subject="600000")

        assert record["id"] == "2026-09-10|valuation_percentile|600000"

    def test_empty_subject_falls_back_to_portfolio(self):
        record = _sig(sl.SIGNAL_TAIL_RISK, "尾部正常")

        assert record["subject"] == "portfolio"
        assert record["id"] == "2026-09-10|tail_risk|portfolio"

    def test_direction_defaults_to_flat(self):
        assert _sig(sl.SIGNAL_STYLE_FACTOR, "价值")["direction"] == 0

    def test_direction_accepted_explicitly(self):
        record = sl.build_signal(
            signal_type=sl.SIGNAL_VALUATION,
            report_date="2026-09-10",
            rating="高估",
            direction=-1,
        )

        assert record["direction"] == -1

    def test_event_and_detail_defaults(self):
        record = _sig(sl.SIGNAL_TAIL_RISK, "尾部正常")

        assert record["event"] == "signal"
        assert record["detail"] == {}

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan"), "text", None, True])
    def test_non_finite_and_non_numeric_values_normalized_to_none(self, bad):
        """±inf/NaN 若直接 json.dumps 会写出非法 JSON（Infinity/NaN）。"""
        assert _sig(sl.SIGNAL_TAIL_RISK, "尾部正常", value=bad)["value"] is None

    def test_record_is_strictly_valid_json(self):
        record = _sig(sl.SIGNAL_TAIL_RISK, "尾部偏厚", value=float("nan"))

        assert json.loads(json.dumps(record, ensure_ascii=False, sort_keys=True))


class TestAppendSignals:
    """批量原子追加与幂等。"""

    def test_appends_and_loads(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")

        appended = sl.append_signals([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")], path=path)

        assert len(appended) == 1
        assert len(sl.load_signals(path)) == 1

    def test_idempotent_on_same_id(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        sl.append_signals([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")], path=path)

        again = sl.append_signals([_sig(sl.SIGNAL_TAIL_RISK, "尾部偏厚")], path=path)

        assert again == []
        assert len(sl.load_signals(path)) == 1  # 保留首次登记，不覆盖

    def test_dedupes_within_same_batch(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        batch = [
            _sig(sl.SIGNAL_VALUATION, "低估", subject="600000"),
            _sig(sl.SIGNAL_VALUATION, "高估", subject="600000"),
        ]

        appended = sl.append_signals(batch, path=path)

        assert len(appended) == 1
        assert appended[0]["rating"] == "低估"

    def test_same_subject_different_type_not_deduped(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        batch = [
            _sig(sl.SIGNAL_VALUATION, "低估", subject="600000"),
            _sig(sl.SIGNAL_REBALANCE_OVERFLOW, "超限", subject="600000"),
        ]

        assert len(sl.append_signals(batch, path=path)) == 2

    def test_empty_input_does_not_touch_file(self, tmp_path):
        path = tmp_path / "signals.jsonl"

        assert sl.append_signals([], path=path) == []
        assert sl.append_signals([None, {}, {"id": ""}], path=path) == []
        assert not path.exists()

    def test_all_duplicates_does_not_rewrite_file(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        sl.append_signals([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")], path=path)
        before = (tmp_path / "signals.jsonl").read_text(encoding="utf-8")

        sl.append_signals([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")], path=path)

        assert (tmp_path / "signals.jsonl").read_text(encoding="utf-8") == before

    def test_append_signal_single_returns_record_then_none(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        kwargs = dict(
            signal_type=sl.SIGNAL_TAIL_RISK,
            report_date="2026-09-10",
            rating="尾部正常",
            value=-1.2,
        )

        assert sl.append_signal(path=path, **kwargs) is not None
        assert sl.append_signal(path=path, **kwargs) is None

    def test_corrupt_line_tolerated_on_load(self, tmp_path):
        path = tmp_path / "signals.jsonl"
        path.write_text('{broken\n{"id": "x", "signal_type": "tail_risk"}\n', encoding="utf-8")

        assert len(sl.load_signals(str(path))) == 1


class TestFoldSignals:
    """折叠统计。"""

    def _mixed(self):
        return [
            _sig(sl.SIGNAL_VALUATION, "低估", date="2026-09-08", subject="600000"),
            _sig(sl.SIGNAL_VALUATION, "高估", date="2026-09-09", subject="600000"),
            _sig(sl.SIGNAL_VALUATION, "合理", date="2026-09-10", subject="600000"),
            _sig(sl.SIGNAL_TAIL_RISK, "尾部正常", date="2026-09-10", source=sl.DATA_SOURCE_DEMO),
        ]

    def test_live_only_default_excludes_demo(self):
        folded = sl.fold_signals(self._mixed())

        assert folded["live_only"] is True
        assert folded["records"] == 3
        assert folded["live_count"] == 3
        assert folded["demo_count"] == 1

    def test_live_only_false_counts_all(self):
        folded = sl.fold_signals(self._mixed(), live_only=False)

        assert folded["records"] == 4
        assert folded["live_count"] == 3
        assert folded["demo_count"] == 1

    def test_demo_only_type_absent_when_live_only(self):
        folded = sl.fold_signals(self._mixed())

        assert sl.SIGNAL_TAIL_RISK not in folded["by_type"]

    def test_by_type_latest_is_last_written(self):
        folded = sl.fold_signals(self._mixed())

        info = folded["by_type"][sl.SIGNAL_VALUATION]
        assert info["records"] == 3
        assert info["latest_date"] == "2026-09-10"
        assert info["latest_rating"] == "合理"
        assert info["label"] == "估值分位"

    def test_dates_span_counted_records(self):
        folded = sl.fold_signals(self._mixed())

        assert folded["first_date"] == "2026-09-08"
        assert folded["last_date"] == "2026-09-10"
        assert folded["dates"] == ["2026-09-08", "2026-09-09", "2026-09-10"]

    def test_sample_threshold(self):
        assert sl.fold_signals(self._mixed())["sample_sufficient"] is True
        assert sl.fold_signals(self._mixed()[:2])["sample_sufficient"] is False

    def test_empty_ledger_shape(self, tmp_path):
        folded = sl.fold_signals(path=str(tmp_path / "absent.jsonl"))

        assert folded["records"] == 0
        assert folded["by_type"] == {}
        assert folded["first_date"] == ""
        assert folded["sample_sufficient"] is False

    def test_reads_ledger_when_signals_not_given(self, tmp_path):
        path = str(tmp_path / "signals.jsonl")
        sl.append_signals(self._mixed(), path=path)

        assert sl.fold_signals(path=path)["records"] == 3


class TestSummaryBlock:
    """注入摘要文本。"""

    def test_inactive_flag_returns_empty(self):
        assert sl.summary_block([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")] * 3) == ""

    def test_insufficient_sample_returns_empty(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)

        assert sl.summary_block([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")]) == ""

    def test_contains_type_label_and_rating(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [_sig(sl.SIGNAL_VALUATION, "低估", subject="600000")] * 3

        block = sl.summary_block(records)

        assert "确定性信号沉淀" in block
        assert "估值分位" in block
        assert "低估" in block

    def test_demo_note_only_when_demo_records_exist(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")] * 3

        assert "非实时" not in sl.summary_block(records)

        records = records + [_sig(sl.SIGNAL_TAIL_RISK, "尾部正常", date="2026-09-11", source=sl.DATA_SOURCE_DEMO)]
        assert "已剔除" in sl.summary_block(records)

    def test_demo_only_records_yield_empty_summary(self):
        """全非实时 → live 样本 0 → 样本不足 → 不注入（防非实时记录冒充战绩）。"""
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [
            _sig(sl.SIGNAL_TAIL_RISK, "尾部正常", date=f"2026-09-1{i}", source=sl.DATA_SOURCE_DEMO) for i in range(4)
        ]

        assert sl.summary_block(records) == ""


class TestSummaryCacheSuffix:
    """缓存指纹后缀（读写两侧同源）。"""

    def test_inactive_flag_returns_empty(self):
        assert sl.summary_cache_suffix([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")] * 3) == ""

    def test_insufficient_sample_returns_empty(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)

        assert sl.summary_cache_suffix([_sig(sl.SIGNAL_TAIL_RISK, "尾部正常")]) == ""

    def test_prefix_and_stability(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        records = [_sig(sl.SIGNAL_VALUATION, "低估", subject="600000")] * 3

        first = sl.summary_cache_suffix(records)

        assert first.startswith("_sg")
        assert sl.summary_cache_suffix(records) == first  # 同内容 → 同后缀

    def test_changes_when_rating_changes(self):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        base = [_sig(sl.SIGNAL_VALUATION, "低估", subject="600000")] * 3
        changed = base[:-1] + [_sig(sl.SIGNAL_VALUATION, "高估", subject="600000")]

        assert sl.summary_cache_suffix(base) != sl.summary_cache_suffix(changed)

    def test_changes_when_source_label_flips(self):
        """live→demo 翻转会改变摘要正文 → 后缀必须同变（否则缓存键漏判）。"""
        set_feature_enabled(sl.FEATURE_FLAG, True)
        live = [_sig(sl.SIGNAL_TAIL_RISK, "尾部正常", date=f"2026-09-1{i}") for i in range(3)]
        flipped = [
            _sig(sl.SIGNAL_TAIL_RISK, "尾部正常", date=f"2026-09-1{i}", source=sl.DATA_SOURCE_DEMO) for i in range(3)
        ]

        # flipped 全非实时 → 摘要为空；live 有样本 → 摘要非空 → 后缀必不同
        assert sl.summary_cache_suffix(live) != sl.summary_cache_suffix(flipped)

    def test_reads_ledger_when_signals_not_given(self, tmp_path):
        set_feature_enabled(sl.FEATURE_FLAG, True)
        path = str(tmp_path / "signals.jsonl")
        sl.append_signals(
            [_sig(sl.SIGNAL_TAIL_RISK, "尾部正常", date=f"2026-09-1{i}") for i in range(3)],
            path=path,
        )

        assert sl.summary_cache_suffix(path=path).startswith("_sg")
