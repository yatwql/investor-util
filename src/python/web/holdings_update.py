"""正式持仓更新 — 备份 + 提升（纯函数，可单测）。

正式模式（formal）下把上传临时文件提升为正式持仓文件：
  - ``backup_holdings_file``：现有正式文件备份为 ``{path}.bak``（单槽轮转）。
  - ``promote_upload_to_holdings``：备份后把临时文件 copy 到正式路径。

原子性（架构约束 缓存原子写入）：一律 mkstemp + ``os.replace``，
``.bak`` 与正式文件均不会出现半写态。
失败语义：``backup`` 失败不继续 promote（旧文件与 .bak 均完好）；
``promote``（copy）失败时旧正式文件未动，``.bak`` 保留原文件可恢复。
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile

logger = logging.getLogger("invest")


def _atomic_copy(src: str, dst: str) -> None:
    """原子复制：mkstemp 到 dst 同目录 → os.replace 到 dst。

    无论 src/dst 在哪个目录，临时文件都落在 dst 同目录（同文件系统，
    os.replace 保证原子），避免跨文件系统 copy 出现半写态。
    """
    dst_dir = os.path.dirname(os.path.abspath(dst)) or "."
    os.makedirs(dst_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dst_dir, prefix=".holdings-", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copy2(src, tmp_path)
        os.replace(tmp_path, dst)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def backup_holdings_file(holdings_path: str) -> str | None:
    """把现有正式持仓文件备份为 ``{holdings_path}.bak``（单槽轮转）。

    - 文件不存在 → 返回 None（首次正式更新，无需备份）。
    - 原子写：copy → mkstemp 到同目录 → os.replace 到 .bak。
    - 返回 .bak 绝对路径。

    Args:
        holdings_path: 正式持仓文件路径

    Returns:
        .bak 绝对路径；正式文件不存在时返回 None

    Raises:
        OSError: 目标目录不可写等备份失败（调用方中止 promote）
    """
    holdings_path = os.fspath(holdings_path)
    if not os.path.isfile(holdings_path):
        return None
    bak_path = holdings_path + ".bak"
    _atomic_copy(holdings_path, bak_path)
    logger.info("[holdings] 已备份正式持仓文件: %s", bak_path)
    return bak_path


def promote_upload_to_holdings(temp_path: str, holdings_path: str) -> str:
    """把上传临时文件提升为正式持仓文件（先备份旧文件）。

    顺序：① ``backup_holdings_file(holdings_path)`` ② copy temp→holdings_path（原子写）。
    失败语义：② 失败时旧正式文件未被破坏，.bak 保留原文件，可恢复。
    调用方（handler）负责在 finally 中清理上传临时文件（copy 保持临时文件
    生命周期不变，语义清晰）。

    Args:
        temp_path: 上传临时文件路径
        holdings_path: 正式持仓文件目标路径

    Returns:
        holdings_path（提升成功）

    Raises:
        OSError: backup / promote 任一环节失败（调用方报 run 失败）
    """
    temp_path = os.fspath(temp_path)
    holdings_path = os.fspath(holdings_path)
    backup_holdings_file(holdings_path)
    _atomic_copy(temp_path, holdings_path)
    logger.info("[holdings] 正式持仓文件已更新: %s", holdings_path)
    return holdings_path
