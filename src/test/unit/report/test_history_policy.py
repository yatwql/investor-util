"""历史走势获取策略解析 report.history_policy：off/auto/prompt 单一事实来源。

三渠道（TUI 询问 / CLI·Web·orchestrator 非交互回退）共用本解析；
渠道层不得自行分支 fetch_mode。
"""

from __future__ import annotations

import pytest

from src.python.report.history_policy import resolve_fetch_history

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


class TestResolveFetchHistory:
    def test_off_wins_even_with_ask(self):
        config = {"history": {"fetch_mode": "off"}}
        assert resolve_fetch_history(config, ask=lambda: True) is False

    def test_auto_enables_without_asking(self):
        config = {"history": {"fetch_mode": "auto"}}
        assert resolve_fetch_history(config, ask=lambda: False) is True

    def test_prompt_without_ask_falls_back_enabled(self):
        # CLI / Web / orchestrator 回退：非交互 → auto 语义
        config = {"history": {"fetch_mode": "prompt"}}
        assert resolve_fetch_history(config) is True

    @pytest.mark.parametrize("answer", [True, False])
    def test_prompt_with_ask_uses_callback(self, answer):
        config = {"history": {"fetch_mode": "prompt"}}
        assert resolve_fetch_history(config, ask=lambda: answer) is answer

    @pytest.mark.parametrize(
        "config",
        [
            {},  # 缺 history 段
            {"history": {}},  # 缺 fetch_mode
            {"history": {"fetch_mode": None}},  # 显式空值
            {"history": {"fetch_mode": "bogus"}},  # 未知值按 auto
        ],
    )
    def test_missing_or_unknown_mode_defaults_enabled(self, config):
        assert resolve_fetch_history(config) is True

    def test_history_none_value(self):
        assert resolve_fetch_history({"history": None}) is True
