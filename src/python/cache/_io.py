"""缓存引擎 — 文件 IO 子模块。

职责：原子文件读写、gzip 透明压缩/解压、损坏文件自动恢复。
"""

from __future__ import annotations

import contextlib
import gzip
import json
import logging
import os

from ._paths import _GZIP_SUFFIX

logger = logging.getLogger("invest")


def _read_cache_data(fpath: str, key: str, dry_run: bool = False) -> dict | None:
    """读取并解析单个缓存文件，返回载荷字典（含 _ts 和 _data 键）。

    自动识别 .json.gz（gzip 压缩）和 .json（纯文本）格式。
    文件损坏时自动删除并返回 None。

    Args:
        fpath: 缓存文件路径
        key: 缓存键名（仅用于日志）
        dry_run: True 时仅记录不删除损坏文件（用于 cleanup_expired 预览）

    Returns:
        解析后的字典载荷，文件不存在/损坏返回 None
    """
    if not os.path.exists(fpath):
        return None
    is_gz = fpath.endswith(_GZIP_SUFFIX)
    try:
        if is_gz:
            with open(fpath, "rb") as f:
                return json.loads(gzip.decompress(f.read()).decode("utf-8"))
        with open(fpath, encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        if dry_run:
            logger.info("缓存清理(预览): 损坏文件 %s", os.path.basename(fpath))
        else:
            logger.warning("缓存文件 %s 损坏，自动删除: %s", key, e)
            try:
                os.remove(fpath)
                logger.info("已删除损坏的缓存文件: %s", key)
            except OSError:
                pass
        return None


def _write_atomic(
    fd: int,
    tmp_path: str,
    final_path: str,
    path: str,
    json_str: str,
    raw_bytes: bytes,
    use_gzip: bool,
) -> None:
    """原子写入：写临时文件 → os.replace 替换 → 清理旧格式。

    Args:
        fd: tempfile.mkstemp 返回的文件描述符
        tmp_path: 临时文件路径
        final_path: 最终目标文件路径（含 .json 或 .json.gz）
        path: 原始缓存路径（用于清理另一格式文件）
        json_str: JSON 序列化字符串
        raw_bytes: UTF-8 编码字节
        use_gzip: 是否 gzip 压缩

    Raises:
        OSError: IO 写入或替换失败
        FileNotFoundError: 临时文件所在目录被删除
    """
    if use_gzip:
        compressed = gzip.compress(raw_bytes)
        with os.fdopen(fd, "wb") as f:
            f.write(compressed)
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json_str)
    try:
        os.replace(tmp_path, final_path)
    except PermissionError:
        # Windows: replace 目标文件可能被锁，先删除再 rename
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(tmp_path, final_path)

    # 设置文件权限为 0o600（仅所有者可读写，保护敏感数据）
    try:
        os.chmod(final_path, 0o600)
    except OSError:
        pass  # Windows 可能不支持完整 chmod，忽略

    # 清理旧格式文件（防止 .json 和 .json.gz 同时存在）
    other_path = path if use_gzip else (path + _GZIP_SUFFIX)
    if os.path.exists(other_path):
        with contextlib.suppress(OSError):
            os.remove(other_path)
