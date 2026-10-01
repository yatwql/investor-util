"""调用级数据源覆盖（preferred / exclude）单元测试。

测试目标：
  - 覆盖生效：preferred 排到链首、exclude 过滤（**只排序/过滤，不新增链上源**）
  - 作用域：嵌套可恢复、退出即恢复（长驻进程不留残留）
  - 边界：未知源名忽略并告警、首选不在该链上忽略并告警、全排除 → 空链
  - 优先级：调用级 > 配置级 preferred_provider（两者都只是排序）
  - CLI：未知源名报错退出、参数透传到覆盖作用域

运行：
  pytest src/test/unit/fetcher/test_chain_overrides.py -v
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from src.python.fetcher.chain import (
    _DEFAULT_CHAINS,
    _get_chain,
    chain_overrides,
    known_provider_names,
    reset_chain_overrides,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_fetcher]

_DATA_TYPE = "price_stock"  # 默认链：tencent → sina → hithink


def _no_config_preferred():
    """隔离配置层 preferred_provider（本用例只测调用级）。"""
    return patch("src.python.fetcher.chain.get_config", return_value={})


# ── known_provider_names ──────────────────────────────────────


def test_known_provider_names_derives_from_default_chains():
    """取值域由默认链并集派生（不另写清单）——新增 provider 自动可被 --prefer-source 使用。"""
    expected: set[str] = set()
    for chain in _DEFAULT_CHAINS.values():
        expected.update(chain)
    assert known_provider_names() == expected


# ── preferred ─────────────────────────────────────────────────


def test_preferred_moves_source_to_front():
    with _no_config_preferred(), chain_overrides(preferred="sina"):
        assert _get_chain(_DATA_TYPE)[0] == "sina"


def test_preferred_does_not_add_new_source():
    """首选只能重排链上已有源：链上无该源时忽略（不把外部源塞进链）。"""
    with chain_overrides(preferred="datasink"):
        chain = _get_chain(_DATA_TYPE)
    assert chain == list(_DEFAULT_CHAINS[_DATA_TYPE])


def test_unknown_preferred_is_ignored_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="invest"), chain_overrides(preferred="no_such_source"):
        chain = _get_chain(_DATA_TYPE)
    assert chain == list(_DEFAULT_CHAINS[_DATA_TYPE])
    assert any("未知 provider 名" in r.getMessage() for r in caplog.records)


# ── exclude ───────────────────────────────────────────────────


def test_exclude_removes_source_from_chain():
    with _no_config_preferred(), chain_overrides(exclude={"sina"}):
        assert "sina" not in _get_chain(_DATA_TYPE)


def test_exclude_all_candidates_yields_empty_chain():
    """全排除 → 空链（与「链上全部失败」同语义，由调用方按既有降级路径处理）。"""
    with _no_config_preferred(), chain_overrides(exclude=set(_DEFAULT_CHAINS[_DATA_TYPE])):
        assert _get_chain(_DATA_TYPE) == []


def test_exclude_unknown_name_is_noop():
    with _no_config_preferred(), chain_overrides(exclude={"no_such_source"}):
        assert _get_chain(_DATA_TYPE) == list(_DEFAULT_CHAINS[_DATA_TYPE])


def test_exclude_wins_over_preferred():
    """被排除的源即使被指定为首选也不出现（排除优先于排序）。"""
    with chain_overrides(preferred="sina", exclude={"sina"}):
        assert "sina" not in _get_chain(_DATA_TYPE)


# ── 作用域 ────────────────────────────────────────────────────


def test_overrides_restored_after_context_exit():
    before = _get_chain(_DATA_TYPE)
    with chain_overrides(preferred="sina", exclude={"tencent"}):
        assert _get_chain(_DATA_TYPE) != before
    assert _get_chain(_DATA_TYPE) == before


def test_nested_contexts_restore_previous_layer():
    with chain_overrides(preferred="sina"):
        assert _get_chain(_DATA_TYPE)[0] == "sina"
        with chain_overrides(preferred="hithink"):
            assert _get_chain(_DATA_TYPE)[0] == "hithink"
        assert _get_chain(_DATA_TYPE)[0] == "sina"
    assert _get_chain(_DATA_TYPE) == list(_DEFAULT_CHAINS[_DATA_TYPE])


def test_reset_clears_overrides():
    """显式重置（测试隔离兜底）后不再有任何覆盖生效。"""
    with chain_overrides(preferred="sina"):
        pass
    reset_chain_overrides()
    assert _get_chain(_DATA_TYPE) == list(_DEFAULT_CHAINS[_DATA_TYPE])


# ── 与配置级优先的关系 ────────────────────────────────────────


def test_call_level_overrides_config_level():
    """两层同时存在时调用级优先；两者都只是排序，不改变链上源集合。"""
    with patch(
        "src.python.fetcher.chain.get_config",
        return_value={"preferred_provider": {_DATA_TYPE: "hithink"}},
    ):
        assert _get_chain(_DATA_TYPE)[0] == "hithink"
        with chain_overrides(preferred="sina"):
            chain = _get_chain(_DATA_TYPE)
            assert chain[0] == "sina"
            assert set(chain) == set(_DEFAULT_CHAINS[_DATA_TYPE])
        assert _get_chain(_DATA_TYPE)[0] == "hithink"


# ── CLI 接入 ──────────────────────────────────────────────────


def _report_args(**overrides):
    from argparse import Namespace

    base = {
        "type": "basic",
        "history": "auto",
        "force_llm": False,
        "output": None,
        "verbose": False,
        "prefer_source": None,
        "exclude_source": None,
    }
    base.update(overrides)
    return Namespace(**base)


def test_cli_resolver_returns_empty_when_no_flags():
    from src.python.cli.cli import _resolve_source_overrides

    assert _resolve_source_overrides(_report_args()) == (None, ())


def test_cli_resolver_parses_flags():
    from src.python.cli.cli import _resolve_source_overrides

    preferred, exclude = _resolve_source_overrides(
        _report_args(prefer_source=["sina"], exclude_source=["tencent", "hithink"])
    )
    assert preferred == "sina"
    assert exclude == ("tencent", "hithink")


def test_cli_resolver_rejects_unknown_source():
    """未知源名必须报错退出（否则用户会误以为生效）。"""
    from src.python.cli.cli import _resolve_source_overrides

    with pytest.raises(SystemExit) as exc:
        _resolve_source_overrides(_report_args(prefer_source=["no_such_source"]))
    message = str(exc.value)
    assert "未知数据源" in message
    assert "tencent" in message  # 报错须列出可用源名


def test_cli_handle_report_applies_overrides(monkeypatch):
    """_handle_report 把解析结果落到覆盖作用域，退出后即恢复。"""
    from types import SimpleNamespace

    from src.python.cli import cli as cli_module
    from src.python.cli.cli import _handle_report

    captured: dict[str, object] = {}

    def _fake_generate_report(**kwargs):
        captured["chain"] = _get_chain(_DATA_TYPE)
        return SimpleNamespace(exit_code=0)

    monkeypatch.setattr("src.python.report.orchestrator.generate_report", _fake_generate_report)
    monkeypatch.setattr(
        cli_module,
        "_cli_read_holdings_with_flows",
        lambda config: ([], [], []),
    )

    code = _handle_report(_report_args(prefer_source=["sina"], exclude_source=["tencent"]), {})

    assert code == 0
    assert captured["chain"] == ["sina", "hithink"]
    # 报告生成结束后覆盖已恢复（长驻进程不留残留）
    assert _get_chain(_DATA_TYPE) == list(_DEFAULT_CHAINS[_DATA_TYPE])
