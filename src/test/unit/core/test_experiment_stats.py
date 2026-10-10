"""experiment_stats：实验功能使用统计（启用计数 / 最近启用日期）单元测试。

覆盖：累计计数、跨日日期刷新、同批去重幂等、文件损坏容错、形状异常容错、
原子写不留临时文件、未知开关名同样如实记录（统计不校验注册表——账本是
历史事实的记录，注册表以后取值时自行过滤）。
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from src.python.core import experiment_stats

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]


@pytest.fixture
def stats_path(tmp_path, monkeypatch):
    """统计文件重定向到临时目录（避免触碰真实 data/state/）。"""
    target = str(tmp_path / "data" / "state" / "experiment_stats.json")
    monkeypatch.setattr(experiment_stats, "EXPERIMENT_STATS_FILE", target)
    return target


class TestRecordExperimentUsage:
    """record_experiment_usage：累计计数与最近启用日期。"""

    def test_first_record_creates_entry(self, stats_path):
        experiment_stats.record_experiment_usage(["decision_reflection"])
        stats = experiment_stats.load_experiment_usage()
        assert stats["decision_reflection"]["enabled_count"] == 1
        assert stats["decision_reflection"]["last_enabled_date"]

    def test_repeated_records_accumulate(self, stats_path):
        experiment_stats.record_experiment_usage(["decision_reflection"])
        experiment_stats.record_experiment_usage(["decision_reflection", "prosperity_framework"])

        stats = experiment_stats.load_experiment_usage()
        assert stats["decision_reflection"]["enabled_count"] == 2
        assert stats["prosperity_framework"]["enabled_count"] == 1

    def test_duplicates_within_one_batch_deduped(self, stats_path):
        """同一次报告的重复开关名只计一次（一次报告 = 一次使用）。"""
        experiment_stats.record_experiment_usage(["decision_reflection", "decision_reflection"])
        stats = experiment_stats.load_experiment_usage()
        assert stats["decision_reflection"]["enabled_count"] == 1

    def test_empty_batch_writes_nothing(self, stats_path):
        experiment_stats.record_experiment_usage([])
        assert os.path.exists(stats_path) is False


class TestLoadExperimentUsage:
    """load_experiment_usage：容错口径。"""

    def test_missing_file_returns_empty(self, tmp_path):
        assert experiment_stats.load_experiment_usage(str(tmp_path / "absent.json")) == {}

    def test_corrupted_json_tolerated(self, stats_path, tmp_path):
        os.makedirs(os.path.dirname(stats_path), exist_ok=True)
        with open(stats_path, "w", encoding="utf-8") as f:
            f.write("{not json")
        assert experiment_stats.load_experiment_usage() == {}

    def test_wrong_shape_entries_filtered(self, stats_path):
        os.makedirs(os.path.dirname(stats_path), exist_ok=True)
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "decision_reflection": {"enabled_count": 3, "last_enabled_date": "2026-10-01"},
                    "bad_entry": {"enabled_count": "no"},
                    "junk": 7,
                },
                f,
            )
        stats = experiment_stats.load_experiment_usage()
        assert list(stats) == ["decision_reflection"]
        assert stats["decision_reflection"]["enabled_count"] == 3

    def test_atomic_write_leaves_no_temp_files(self, stats_path, tmp_path):
        experiment_stats.record_experiment_usage(["decision_reflection"])
        leftovers = [n for n in os.listdir(os.path.dirname(stats_path)) if n.startswith(".experiment_stats_")]
        assert leftovers == []


class TestDoctorIntegration:
    """doctor 只读视图中的使用统计行。"""

    def test_usage_item_lists_flag_counts(self, stats_path):
        from src.python.core import doctor

        experiment_stats.record_experiment_usage(["decision_reflection"])
        items = doctor._check_review_ledger_overview()
        usage_items = [i for i in items if i["label"] == "实验功能使用统计"]
        assert len(usage_items) == 1
        assert usage_items[0]["ok"] is True
        assert "decision_reflection" in usage_items[0]["message"]

    def test_usage_item_reports_empty_when_no_stats(self, stats_path):
        from src.python.core import doctor

        items = doctor._check_review_ledger_overview()
        usage_items = [i for i in items if i["label"] == "实验功能使用统计"]
        assert len(usage_items) == 1
        assert "暂无统计" in usage_items[0]["message"]


class TestReportEntrypointWiring:
    """报告入口 log_experimental_features 会写使用统计（尽力而为，失败不外抛）。"""

    def test_log_records_usage(self, stats_path, caplog):
        from src.python.config.features import set_feature_enabled

        set_feature_enabled("decision_reflection", True)
        try:
            experiment_stats.record_experiment_usage([])  # 清底盘上残留（如有）
            with caplog.at_level("WARNING", logger="invest"):
                from src.python.config.features import log_experimental_features

                log_experimental_features()

            stats = experiment_stats.load_experiment_usage()
            assert stats["decision_reflection"]["enabled_count"] == 1
        finally:
            set_feature_enabled("decision_reflection", False)

    def test_record_failure_swallowed(self, caplog):
        from src.python.config.features import set_feature_enabled

        set_feature_enabled("factor_catalog", True)
        try:
            with (
                patch(
                    "src.python.core.experiment_stats.write_json_atomic",
                    side_effect=OSError("disk full"),
                ),
                caplog.at_level("WARNING", logger="invest"),
            ):
                from src.python.config.features import log_experimental_features

                log_experimental_features()  # 写盘失败不外抛、落盘失败告警已记录
        finally:
            set_feature_enabled("factor_catalog", False)

        assert "实验功能使用统计记录失败" in caplog.text and "不影响报告生成" in caplog.text
