"""持仓快照命名空间（namespace）隔离存储测试。

覆盖：
  - save(namespace="web") → 文件落在 {HISTORY_SNAPSHOT_DIR}/web/
  - 默认 namespace（None）读写共享主目录（向后兼容）
  - load_latest / load_all 按 namespace 隔离，不串读其他域
  - prune(namespace="web") 只清理 web/ 域
  - 同 namespace 两次保存 → load_latest 取本域最新

测试隔离：conftest `_isolate_sensitive_paths` 已将 HISTORY_SNAPSHOT_DIR
重定向到 tmp_path，web/ 是其下子目录，天然隔离。
"""

from __future__ import annotations

import os

import pytest

from src.python.report import history_snapshot as hs
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _holding(code: str, name: str, mv: float, cost: float) -> SnapshotHolding:
    return SnapshotHolding(
        code=code,
        name=name,
        shares=0.0,
        cost_price=0.0,
        market_value=mv,
        daily_pnl=0.0,
        total_pnl=0.0,
        cost_total=cost,
    )


def _save(ts: str, holdings: list[SnapshotHolding], namespace: str | None = None) -> str:
    sd = SnapshotData(
        accounts=(AccountSnapshot(account_name="全部", holdings=tuple(holdings)),),
        total_value=sum(h.market_value for h in holdings),
        total_cost=sum(h.cost_total for h in holdings),
        total_pnl=0.0,
        timestamp=ts,
    )
    return hs.save(sd, namespace)


# ── namespace 存储隔离 ─────────────────────────────────────


def test_save_web_namespace_writes_subdir():
    """save(namespace="web") → 文件落在 {HISTORY_SNAPSHOT_DIR}/web/。"""
    path = _save("20260801T090000", [_holding("a", "A", 100, 90)], "web")
    assert os.path.dirname(path) == os.path.join(hs.HISTORY_SNAPSHOT_DIR, "web")
    assert os.path.isfile(path)
    # 主目录无此文件
    main_dir_files = [
        f
        for f in os.listdir(hs.HISTORY_SNAPSHOT_DIR)
        if f.startswith("snapshot_") and f.endswith(".json")
    ]
    assert main_dir_files == []


def test_default_namespace_reads_main_dir():
    """默认 namespace=None → 读写共享主目录（向后兼容）。"""
    path = _save("20260801T090000", [_holding("a", "A", 100, 90)])
    assert os.path.dirname(path) == hs.HISTORY_SNAPSHOT_DIR
    latest = hs.load_latest()
    assert latest is not None
    assert latest.total_value == 100.0


def test_load_latest_namespace_isolated_from_main():
    """load_latest(namespace="web") 不含主目录文件（反污染）。"""
    _save("20260701T090000", [_holding("a", "A", 100, 90)])  # 主目录
    _save("20260702T090000", [_holding("b", "B", 200, 150)], "web")  # web 域
    # 主目录 latest 是本域快照
    main_latest = hs.load_latest()
    assert main_latest is not None
    assert main_latest.total_value == 100.0
    # web 域 latest 是 web 域快照
    web_latest = hs.load_latest("web")
    assert web_latest is not None
    assert web_latest.total_value == 200.0
    # 跨域不串读
    assert [a.code for acc in web_latest.accounts for a in acc.holdings] == ["b"]


def test_load_all_namespace_only_web():
    """load_all(namespace="web") 只聚合 web/ 域快照。"""
    _save("20260701T090000", [_holding("a", "A", 100, 90)])
    _save("20260701T090000", [_holding("w1", "W1", 10, 9)], "web")
    _save("20260702T090000", [_holding("w2", "W2", 20, 15)], "web")
    web_all = hs.load_all("web")
    assert len(web_all) == 2
    main_all = hs.load_all()
    assert len(main_all) == 1


def test_prune_namespace_only_web():
    """prune(namespace="web") 只清理 web/ 域，主目录不受影响。"""
    for i in range(5):
        _save(f"2026070{i + 1}T090000", [_holding("m", "M", 100, 90)])
    for i in range(5):
        _save(f"2026070{i + 1}T090000", [_holding("w", "W", 100, 90)], "web")
    # web 域 max_count=3 → 清理 2 个
    deleted = hs.prune(max_count=3, namespace="web")
    assert deleted == 2
    assert len(hs.load_all("web")) == 3
    # 主目录仍 5 个（prune 未动）
    assert len(hs.load_all()) == 5


def test_same_namespace_latest_is_last_saved():
    """同 namespace 两次保存 → load_latest 取本域最新（环比闭环基础）。"""
    _save("20260801T090000", [_holding("a", "A", 100, 90)], "web")
    _save("20260802T090000", [_holding("a", "A", 120, 90)], "web")
    latest = hs.load_latest("web")
    assert latest is not None
    assert latest.total_value == 120.0


def test_list_all_namespace():
    """list_all(namespace="web") 只列 web/ 域快照元信息。"""
    _save("20260801T090000", [_holding("a", "A", 100, 90)])
    _save("20260801T090000", [_holding("w", "W", 100, 90)], "web")
    web_entries = hs.list_all("web")
    assert len(web_entries) == 1
    assert "web" in web_entries[0]["path"]


def test_cache_stats_ignores_web_subdir(tmp_path, monkeypatch):
    """get_cache_stats.snapshot_files 不含 web/ 子目录内 JSON（isfile 过滤天然排除）。"""
    from unittest.mock import MagicMock

    from src.python.cache.operations import get_cache_stats

    # 主目录 1 份 + web/ 域 2 份
    _save("20260801T090000", [_holding("a", "A", 100, 90)])
    _save("20260801T090000", [_holding("w", "W", 100, 90)], "web")
    _save("20260802T090000", [_holding("w", "W", 120, 90)], "web")
    assert os.path.isdir(os.path.join(hs.HISTORY_SNAPSHOT_DIR, "web"))

    # operations.get_cache_stats 用 PROJECT_ROOT 推导快照目录 → 对齐隔离路径
    monkeypatch.setattr("src.python.core.constants.PROJECT_ROOT", str(tmp_path))
    stats = get_cache_stats(MagicMock())
    # web/ 是子目录（非文件），isfile 过滤排除 → snapshot_files 只数主目录 1 份
    assert stats.snapshot_files == 1
    # 主目录确实有 1 份（防止"全被忽略"的假阳性）
    assert len(hs.load_all()) == 1
