"""CLI 运行收尾资源摘要行单元测试。

测试目标：
  - print_llm_cost_line — 有调用时输出成本行、无调用时静默
  - print_cache_hit_line — 有缓存读写时输出命中率行、无读写时静默

运行：
  pytest src/test/unit/report/test_cli_run_summary.py -v
"""

from __future__ import annotations

import logging

import pytest

from src.python.cache import reset_cache_stats
from src.python.cache._stats import _record_cache_hit, _record_cache_miss
from src.python.llm.session import reset_session_usage, track_session_usage
from src.python.report.cli_progress import CliProgressReporter

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _messages(caplog: pytest.LogCaptureFixture, needle: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


# ── print_llm_cost_line ───────────────────────────────────────


@pytest.fixture
def _clean_session():
    reset_session_usage()
    yield
    reset_session_usage()


@pytest.mark.usefixtures("_clean_session")
def test_llm_cost_line_silent_when_no_calls(caplog: pytest.LogCaptureFixture) -> None:
    """无 LLM 调用（无用量）→ 不输出任何日志。"""
    with caplog.at_level(logging.INFO, logger="invest"):
        CliProgressReporter(verbose=False).print_llm_cost_summary()
    assert _messages(caplog, "LLM 成本") == []


@pytest.mark.usefixtures("_clean_session")
def test_llm_cost_line_prints_after_usage_tracked(caplog: pytest.LogCaptureFixture) -> None:
    """累计一次调用后 → 输出含调用次数/token/模型名的成本行。"""
    track_session_usage("claude", {"input_tokens": 1200, "output_tokens": 300}, model_name="claude-sonnet-4")
    with caplog.at_level(logging.INFO, logger="invest"):
        CliProgressReporter(verbose=False).print_llm_cost_summary()
    lines = _messages(caplog, "LLM 成本")
    assert len(lines) == 1
    assert "1200" in lines[0]
    assert "300" in lines[0]
    assert "claude-sonnet-4" in lines[0]


# ── print_cache_hit_line ──────────────────────────────────────


@pytest.fixture
def _clean_cache_stats():
    reset_cache_stats()
    yield
    reset_cache_stats()


@pytest.mark.usefixtures("_clean_cache_stats")
def test_cache_hit_line_silent_when_no_observations(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="invest"):
        CliProgressReporter(verbose=False).print_cache_hit_summary()
    assert _messages(caplog, "缓存命中率") == []


@pytest.mark.usefixtures("_clean_cache_stats")
def test_cache_hit_line_prints_hit_rate_with_counts(caplog: pytest.LogCaptureFixture) -> None:
    """3 命中 / 1 未命中 → 输出 3/4 (75.0%)。"""
    _record_cache_hit()
    _record_cache_hit()
    _record_cache_hit()
    _record_cache_miss()
    with caplog.at_level(logging.INFO, logger="invest"):
        CliProgressReporter(verbose=False).print_cache_hit_summary()
    lines = _messages(caplog, "缓存命中率")
    assert len(lines) == 1
    assert "3/4" in lines[0]
    assert "75.0%" in lines[0]


@pytest.mark.usefixtures("_clean_cache_stats")
def test_cache_hit_line_zero_percent_still_printed(caplog: pytest.LogCaptureFixture) -> None:
    """全未命中（0%）同样是诊断信号，必须输出而非静默。"""
    _record_cache_miss()
    with caplog.at_level(logging.INFO, logger="invest"):
        CliProgressReporter(verbose=False).print_cache_hit_summary()
    lines = _messages(caplog, "缓存命中率")
    assert len(lines) == 1
    assert "0/1" in lines[0]
    assert "0.0%" in lines[0]
