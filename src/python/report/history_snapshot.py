"""F1 快照持久化：保存/加载/列表/清理。

C3 约束：所有文件写入使用 tempfile.mkstemp + os.replace 确保原子性。
竞争条件防护：快照文件名使用时间戳（snapshot_{timestamp}.json）。

用法：
  >>> from src.python.schemas.history import SnapshotData, AccountSnapshot
  >>> sd = SnapshotData(...)
  >>> path = save(sd)
  >>> latest = load_latest()
  >>> all_snapshots = list_all()
  >>> prune(max_count=12)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Any

from src.python.core.constants import (
    HISTORY_SNAPSHOT_DIR,
    HISTORY_SNAPSHOT_MAX_COUNT,
    HISTORY_SNAPSHOT_RETENTION_DAYS,
)
from src.python.schemas.history import AccountSnapshot, SnapshotData, SnapshotHolding

logger = logging.getLogger("invest")

# ── JSON 编解码辅助 ──────────────────────────────────────────


def _holding_to_dict(h: SnapshotHolding) -> dict[str, Any]:
    return {
        "code": h.code,
        "name": h.name,
        "shares": h.shares,
        "cost_price": h.cost_price,
        "market_value": h.market_value,
        "daily_pnl": h.daily_pnl,
        "total_pnl": h.total_pnl,
        "cost_total": h.cost_total,
    }


def _holding_from_dict(d: dict[str, Any]) -> SnapshotHolding:
    return SnapshotHolding(
        code=d["code"],
        name=d.get("name", ""),
        shares=d.get("shares", 0.0),
        cost_price=d.get("cost_price", 0.0),
        market_value=d.get("market_value", 0.0),
        daily_pnl=d.get("daily_pnl", 0.0),
        total_pnl=d.get("total_pnl", 0.0),
        cost_total=d.get("cost_total", 0.0),
    )


def _account_to_dict(a: AccountSnapshot) -> dict[str, Any]:
    return {
        "account_name": a.account_name,
        "holdings": [_holding_to_dict(h) for h in a.holdings],
    }


def _account_from_dict(d: dict[str, Any]) -> AccountSnapshot:
    return AccountSnapshot(
        account_name=d["account_name"],
        holdings=tuple(_holding_from_dict(h) for h in d.get("holdings", [])),
    )


def _snapshot_to_dict(sd: SnapshotData) -> dict[str, Any]:
    return {
        "accounts": [_account_to_dict(a) for a in sd.accounts],
        "total_value": sd.total_value,
        "total_cost": sd.total_cost,
        "total_pnl": sd.total_pnl,
        "total_pnl_pct": sd.total_pnl_pct,
        "timestamp": sd.timestamp,
        "fingerprint": sd.fingerprint,
        "llm_summary": sd.llm_summary,
    }


def _snapshot_from_dict(d: dict[str, Any]) -> SnapshotData:
    return SnapshotData(
        accounts=tuple(_account_from_dict(a) for a in d.get("accounts", [])),
        total_value=d.get("total_value", 0.0),
        total_cost=d.get("total_cost", 0.0),
        total_pnl=d.get("total_pnl", 0.0),
        total_pnl_pct=d.get("total_pnl_pct", 0.0),
        timestamp=d.get("timestamp", ""),
        fingerprint=d.get("fingerprint", ""),
        llm_summary=d.get("llm_summary", ""),
    )


# ── 公开 API ────────────────────────────────────────────────


def save(snapshot: SnapshotData) -> str:
    """将 SnapshotData 保存为快照 JSON 文件。

    使用 tempfile.mkstemp + os.replace 确保原子写入（C3 约束）。
    文件名格式：snapshot_{timestamp}.json（timestamp = ISO 格式）。

    Args:
        snapshot: 要保存的快照数据

    Returns:
        已写入文件的绝对路径

    Raises:
        OSError: 目录创建或文件写入失败
    """
    os.makedirs(HISTORY_SNAPSHOT_DIR, exist_ok=True)

    ts = snapshot.timestamp or datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"snapshot_{ts}.json"
    final_path = os.path.join(HISTORY_SNAPSHOT_DIR, filename)

    data = _snapshot_to_dict(snapshot)
    content = json.dumps(data, ensure_ascii=False, indent=2)

    # C3 约束：tempfile.mkstemp + os.replace
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".snapshot_tmp_",
        dir=HISTORY_SNAPSHOT_DIR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, final_path)
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    logger.info("[history_snapshot] 快照已保存: %s (%d KB)", filename, len(content) // 1024)
    return final_path


def load_latest() -> SnapshotData | None:
    """加载最新的快照文件（按 mtime）。

    从 HISTORY_SNAPSHOT_DIR 中查找所有 snapshot_*.json 文件，
    返回 mtime 最大的那个的解析结果。

    Returns:
        SnapshotData 或 None（无快照文件时）
    """
    snapshots = _list_snapshot_files()
    if not snapshots:
        return None

    latest = max(snapshots, key=lambda p: os.path.getmtime(p))
    return _load_file(latest)


def list_all() -> list[dict[str, Any]]:
    """列出所有快照文件的元信息（按 mtime 降序）。

    Returns:
        每个元素包含 filename、mtime、timestamp（从文件名解析）、size 的 dict 列表。
        空列表表示无快照文件。
    """
    files = _list_snapshot_files()
    entries = []
    for path in sorted(files, key=lambda p: os.path.getmtime(p), reverse=True):
        mtime = os.path.getmtime(path)
        basename = os.path.basename(path)
        size = os.path.getsize(path)
        # 从文件名解析时间戳：snapshot_{ts}.json
        ts = basename.replace("snapshot_", "").replace(".json", "")
        entries.append(
            {
                "filename": basename,
                "path": path,
                "mtime": mtime,
                "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": ts,
                "size": size,
            }
        )
    return entries


def prune(
    retention_days: int = HISTORY_SNAPSHOT_RETENTION_DAYS,
    max_count: int = HISTORY_SNAPSHOT_MAX_COUNT,
) -> int:
    """删除超出保留天数和最大数量的旧快照文件。

    两阶段清理：
      1. 删除 mtime 早于 retention_days 天的文件（时间优先）
      2. 若剩余文件仍超过 max_count，再删除最旧的超出部分（数量兜底）

    多进程安全：删除基于逐个文件操作，不会因文件数突变而出错。

    Args:
        retention_days: 保留天数，默认 HISTORY_SNAPSHOT_RETENTION_DAYS (60)
        max_count: 最大保留数，默认 HISTORY_SNAPSHOT_MAX_COUNT (12)

    Returns:
        实际删除的文件数量
    """
    from datetime import datetime

    files = _list_snapshot_files()
    if not files:
        return 0

    now = datetime.now().astimezone()
    deleted = 0
    kept: list[str] = []

    # 阶段 1：按保留天数删除
    for path in sorted(files, key=os.path.getmtime):
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
        age_days = (now - mtime).total_seconds() / 86400
        if age_days > retention_days:
            try:
                os.unlink(path)
                deleted += 1
            except OSError as e:
                logger.warning("[history_snapshot] 删除失败 %s: %s", os.path.basename(path), e)
        else:
            kept.append(path)

    # 阶段 2：按最大数量兜底（仅对阶段 1 幸存文件再限制）
    if max_count > 0 and len(kept) > max_count:
        # 按 mtime 升序排列，删除最旧的超出部分
        kept_sorted = sorted(kept, key=os.path.getmtime)
        to_delete = kept_sorted[: len(kept_sorted) - max_count]
        for path in to_delete:
            try:
                os.unlink(path)
                deleted += 1
            except OSError as e:
                logger.warning("[history_snapshot] 删除失败 %s: %s", os.path.basename(path), e)

    if deleted:
        logger.info(
            "[history_snapshot] 清理了 %d 个旧快照（保留 %d 天内，最多 %d 个）", deleted, retention_days, max_count
        )
    return deleted


# ── 内部辅助 ────────────────────────────────────────────────


def _list_snapshot_files() -> list[str]:
    """列出快照目录中所有 snapshot_*.json 文件。

    Returns:
        文件绝对路径列表，按文件名排序
    """
    if not os.path.isdir(HISTORY_SNAPSHOT_DIR):
        return []
    try:
        return [
            os.path.join(HISTORY_SNAPSHOT_DIR, f)
            for f in os.listdir(HISTORY_SNAPSHOT_DIR)
            if f.startswith("snapshot_") and f.endswith(".json")
        ]
    except OSError:
        return []


def _load_file(path: str) -> SnapshotData | None:
    """从指定路径加载并解析快照 JSON 文件。

    Args:
        path: 快照文件绝对路径

    Returns:
        SnapshotData 或 None（文件不存在/损坏）
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return _snapshot_from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.warning("[history_snapshot] 文件损坏 %s: %s", os.path.basename(path), e)
        return None
