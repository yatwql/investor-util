"""校准工具（scripts/calibrate-dedup-threshold.py）单元测试。

覆盖：
  - 分支重判 classify_pair 与 news_dedup 常量同源（阈值变化不产生漂移）
  - 锚点压缩：每个标题对保留最新一条、幂等、dry-run 不写盘
  - 加载去重保留最早一条
  - 报告输出口径取自当前常量、不再出现「剥离年份」这类已实现的过时建议
  - 锚点文件超告警线时给出压缩指引
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src.python.providers.news_dedup import (
    ANCHOR_RULES_FIELD,
    _ANCHOR_RULES_VERSION,
    _CROSS_BG2_RATIO,
    _CROSS_BIGRAM_MIN,
    _CROSS_CANDIDATE_RATIO,
    _CROSS_DIRECT_RATIO,
    _CROSS_SAFE_RATIO,
    _SAME_SRC_BIGRAM_MIN,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts]

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _load_script():
    """按文件名加载 scripts/ 下的工具脚本（规避 import 路径限制）。"""
    fpath = _SCRIPTS_DIR / "calibrate-dedup-threshold.py"
    spec = importlib.util.spec_from_file_location("calibrate_dedup_threshold", fpath)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def tool():
    return _load_script()


def _record(
    title_a: str, title_b: str, ratio: float, overlap: int, rule: str, *, source_a="东方财富", source_b="新浪财经"
):
    return {
        "ts": "",
        "title_a": title_a,
        "title_b": title_b,
        "source_a": source_a,
        "source_b": source_b,
        "ratio": ratio,
        "bigram_overlap": overlap,
        "merged": rule in ("cross_merge", "cross_merge_bg2", "cross_safe"),
        "rule": rule,
    }


def _write(tmp_path: Path, records: list[dict], name: str = "anchors.jsonl") -> str:
    path = tmp_path / name
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return str(path)


class TestClassifyPair:
    """按当前阈值重判分支（阈值全部来自 news_dedup 常量）。"""

    def test_same_source_branches(self, tool):
        assert tool.classify_pair(0.0, _SAME_SRC_BIGRAM_MIN, True, "A", "B") == "same_src_merged"
        assert tool.classify_pair(0.0, _SAME_SRC_BIGRAM_MIN - 1, True, "A", "B") == "same_src_kept"

    def test_cross_safe_branches(self, tool):
        assert tool.classify_pair(_CROSS_DIRECT_RATIO, 1, False, "A", "B") == "cross_safe_merged"
        assert tool.classify_pair(_CROSS_SAFE_RATIO, 2, False, "A", "B") == "cross_safe_merged"
        assert tool.classify_pair(_CROSS_SAFE_RATIO, 1, False, "A", "B") == "cross_safe_kept"

    def test_cross_candidate_branches(self, tool):
        assert tool.classify_pair(_CROSS_CANDIDATE_RATIO, _CROSS_BIGRAM_MIN, False, "A", "B") == "cross_merge"
        assert (
            tool.classify_pair(_CROSS_BG2_RATIO, 2, False, "CPI同比增长2.5%PPI同比下降0.8%", "CPI涨2.5%PPI降0.8%")
            == "cross_merge_bg2"
        )
        # 纯数字共享不算专名证据 → 不合并
        assert (
            tool.classify_pair(_CROSS_BG2_RATIO, 2, False, "纳斯达克100指数期货", "巴基斯坦KSE100指数") == "cross_skip"
        )
        assert (
            tool.classify_pair(
                0.419,
                3,
                False,
                "兆易创新：5月6日至6月12日朱一明合计减持约44亿元公司股份",
                "兆易创新拟回购最高20亿元股份，董事长朱一明拟增持不低于10亿元",
            )
            == "cross_opposite"
        )

    def test_below_candidate(self, tool):
        assert tool.classify_pair(_CROSS_CANDIDATE_RATIO - 0.01, 9, False, "A", "B") == "below_candidate"


class TestCompactAnchors:
    """锚点压缩：每个标题对保留最新一条。"""

    def test_keeps_newest_and_reports_counts(self, tmp_path, tool):
        old = _record("新闻A", "新闻B", 0.31, 1, "cross_skip")
        new = _record("新闻A", "新闻B", 0.40, 2, "cross_skip")
        other = _record("新闻C", "新闻D", 0.36, 3, "cross_merge")
        path = _write(tmp_path, [old, other, new])
        result = tool.compact_anchors(path)
        assert result["before_lines"] == 3
        assert result["after_lines"] == 2
        assert result["unique_keys"] == 2
        lines = [json.loads(line) for line in open(path, encoding="utf-8")]
        kept = [r for r in lines if r["title_a"] == "新闻A"][0]
        assert kept["ratio"] == 0.40, "应保留最新一条（后者覆盖前者）"

    def test_idempotent_second_run_drops_nothing(self, tmp_path, tool):
        path = _write(tmp_path, [_record("A", "B", 0.4, 2, "cross_skip"), _record("A", "B", 0.4, 2, "cross_skip")])
        first = tool.compact_anchors(path)
        second = tool.compact_anchors(path)
        assert first["before_lines"] == 2 and first["after_lines"] == 1
        assert second["before_lines"] == 1 and second["after_lines"] == 1
        assert second["legacy_era"] == 0

    def test_dry_run_does_not_write(self, tmp_path, tool):
        path = _write(tmp_path, [_record("A", "B", 0.4, 2, "cross_skip")] * 3)
        before = Path(path).read_bytes()
        tool.compact_anchors(path, dry_run=True)
        assert Path(path).read_bytes() == before

    def test_counts_legacy_era_rows(self, tmp_path, tool):
        """丢弃的重复行中，规则指纹与当前不同的计入 legacy_era。"""
        legacy = _record("A", "B", 0.4, 2, "cross_skip")
        legacy[ANCHOR_RULES_FIELD] = "oldfingerprint"
        current = dict(legacy, ratio=0.41)
        current[ANCHOR_RULES_FIELD] = _ANCHOR_RULES_VERSION
        path = _write(tmp_path, [legacy, current])
        result = tool.compact_anchors(path)
        assert result["after_lines"] == 1
        assert result["legacy_era"] == 1

    def test_missing_file_returns_zero_counts(self, tmp_path, tool):
        result = tool.compact_anchors(str(tmp_path / "none.jsonl"))
        assert result["before_lines"] == 0 and result["unique_keys"] == 0


class TestLoadAnchors:
    def test_keeps_earliest_per_pair(self, tmp_path, tool):
        path = _write(
            tmp_path,
            [_record("A", "B", 0.31, 1, "cross_skip"), _record("A", "B", 0.40, 2, "cross_skip")],
        )
        records = tool.load_anchors(path)
        assert len(records) == 1
        assert records[0]["ratio"] == 0.31

    def test_missing_file_returns_empty(self, tmp_path, tool):
        assert tool.load_anchors(str(tmp_path / "none.jsonl")) == []


class TestReportOutput:
    """报告口径：阈值取自常量，不残留已实现的过时建议。"""

    def test_reports_current_thresholds(self, tmp_path, tool, capsys, monkeypatch):
        path = _write(tmp_path, [_record("光伏行业景气度持续超预期", "通信行业5G建设持续推进", 0.36, 0, "cross_skip")])
        monkeypatch.setattr(tool, "_ACTIVE_FILE", path)
        records = tool.load_anchors(path)
        tool.report(records, summary_only=True)
        out = capsys.readouterr().out
        assert f"跨源候选区入口: ratio ≥ {_CROSS_CANDIDATE_RATIO}" in out
        assert "_CROSS_BG2_RATIO" not in out  # 不应把内部常量名当文案
        assert "剥离孤立年份" not in out, "年份剥离早已实现，不应再作为建议输出"
        assert "0.30 当前合适" not in out

    def test_advice_flags_oversized_file(self, tmp_path, tool, capsys, monkeypatch):
        path = _write(tmp_path, [_record("A", "B", 0.4, 2, "cross_skip")])
        monkeypatch.setattr(tool, "_ACTIVE_FILE", path)
        monkeypatch.setattr(tool, "_ANCHOR_SIZE_WARN_BYTES", 1)
        tool.report(tool.load_anchors(path), summary_only=True)
        assert "--compact" in capsys.readouterr().out

    def test_empty_records_message(self, tool, capsys):
        tool.report([])
        assert "尚无数据可用于校准" in capsys.readouterr().out

    def test_digit_only_evidence_not_counted_as_missed(self, tmp_path, tool, capsys, monkeypatch):
        """无专名的 bg=2 边界样本不得被报成「漏判候选」。"""
        path = _write(
            tmp_path,
            [
                _record(
                    "联创电子：控股股东拟变更为寿县新桥 股票复牌",
                    "兆日科技：筹划控制权变更事项 股票停牌",
                    0.359,
                    2,
                    "cross_skip",
                )
            ],
        )
        monkeypatch.setattr(tool, "_ACTIVE_FILE", path)
        tool.report(tool.load_anchors(path), summary_only=True)
        out = capsys.readouterr().out
        assert "其中含真专名证据: 0 条" in out
        assert "bg=2 梯度无漏判" in out

    def test_proper_noun_edge_flagged_for_review(self, tmp_path, tool, capsys, monkeypatch):
        """含真专名的 bg=2 边界样本计入「降阈值会新增合并」的待审查清单。"""
        path = _write(
            tmp_path,
            [_record("摩根士丹利上调Paypal目标价", "Paypal致股东：“请相信我们”", 0.357, 2, "cross_skip")],
        )
        monkeypatch.setattr(tool, "_ACTIVE_FILE", path)
        tool.report(tool.load_anchors(path), summary_only=True)
        out = capsys.readouterr().out
        assert "其中含真专名证据: 1 条" in out
        assert "会新增合并 1 条" in out
