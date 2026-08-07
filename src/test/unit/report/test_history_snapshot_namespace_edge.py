"""持仓快照命名空间（namespace）非法值安全测试 — 路径穿越防护。

必须使用 @pytest.mark.edge 标记，存放于 *_edge.py 文件。

覆盖：
  - `../` / `/` / `\\` / `..` 等路径穿越字符 → ValueError
  - 空串 namespace → ValueError
  - 大写/中文字符等非白名单字符 → ValueError
  - 非法值不越界写盘（save 抛错，无文件产生）
"""

from __future__ import annotations

import os

import pytest

from src.python.report import history_snapshot as hs
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

pytestmark = [pytest.mark.unit, pytest.mark.unit_report, pytest.mark.edge]


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


def _sd() -> SnapshotData:
    h = _holding("a", "A", 100, 90)
    return SnapshotData(
        accounts=(AccountSnapshot(account_name="全部", holdings=(h,)),),
        total_value=100.0,
        total_cost=90.0,
        total_pnl=0.0,
        timestamp="20260801T090000",
    )


@pytest.mark.parametrize(
    "bad_namespace",
    [
        "../evil",
        "a/b",
        "a\\b",
        "..",
        "web/../evil",
        "web\\..",
    ],
)
def test_path_traversal_namespace_rejected(bad_namespace: str):
    """路径穿越类 namespace → _namespace_dir / save / load 抛 ValueError。"""
    with pytest.raises(ValueError):
        hs._namespace_dir(bad_namespace)
    with pytest.raises(ValueError):
        hs.save(_sd(), bad_namespace)
    with pytest.raises(ValueError):
        hs.load_latest(bad_namespace)
    with pytest.raises(ValueError):
        hs.load_all(bad_namespace)
    with pytest.raises(ValueError):
        hs.list_all(bad_namespace)


@pytest.mark.parametrize(
    "bad_namespace",
    ["", "Web", "WEB", "web域", "web space"],
)
def test_non_whitelist_namespace_rejected(bad_namespace: str):
    """空串 / 大写 / 中文 / 空格等非白名单字符 → ValueError。"""
    with pytest.raises(ValueError):
        hs._namespace_dir(bad_namespace)


def test_invalid_namespace_does_not_write_disk():
    """非法 namespace → save 抛错，目录中无文件产生（不越界写盘）。"""
    before = set(os.listdir(hs.HISTORY_SNAPSHOT_DIR)) if os.path.isdir(hs.HISTORY_SNAPSHOT_DIR) else set()
    with pytest.raises(ValueError):
        hs.save(_sd(), "../evil")
    after = set(os.listdir(hs.HISTORY_SNAPSHOT_DIR)) if os.path.isdir(hs.HISTORY_SNAPSHOT_DIR) else set()
    assert after == before
