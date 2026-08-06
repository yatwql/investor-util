"""Web 上传安全 — 校验/净化/落盘/清理（纯函数，可单测）。

上传链路（对齐 Web 上传安全设计 §6.1）：
  - 文件名净化：弃用 ``werkzeug.utils.secure_filename``（会剥离中文——
    中文持仓文件名是仓库常态）；改**服务端 uuid 重命名**为无冲突安全
    临时名 ``data/holdings/uploads/{uuid}.xlsx``（丢弃原始文件名，
    内容即身份，天然防路径穿越/中文问题）。
  - 扩展名校验：仅接受 ``.xlsx``（拒绝 .xls/.xlsm/宏等，openpyxl 不支持
    xls）；大小写归一化 ``.lower()`` 后校验。
  - 大小上限：10MB（读流计数，超限即拒；Flask MAX_CONTENT_LENGTH 兜底）。
  - 内容校验：读前 4 字节校验 PK zip 魔数（``PK\\x03\\x04``），防改扩展名
    伪装；zip-bomb 由大小上限兜底。
  - 落盘：``tempfile.mkstemp`` 到 ``_UPLOAD_DIR`` + ``os.replace`` 原子写。
  - 预检：立即内容预检（行数上限 5000 + 空持仓/无有效账户即拒，避免
    "上传成功、生成失败"的坏体验）；预检通过才注册 file_id。
  - file_id：``secrets.token_urlsafe(16)`` 生成（不可预测）；内存映射
    ``file_id → path``，TTL（1h）过期即失效。
  - 清理：生成任务结束立即删除（handlers 调 discard_file）；未消费文件
    在下次上传时惰性清理过期项；服务启动时清理全部残留。
"""

from __future__ import annotations

import logging
import os
import secrets
import tempfile
import threading
import time
from typing import BinaryIO, Callable

logger = logging.getLogger("invest")

# 项目根目录（绝对化拼接，不依赖 CWD，对齐路径绝对化约束）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 上传临时目录（gitignore 排除；启动清理残留）
_UPLOAD_DIR = os.path.join(_PROJECT_ROOT, "data", "holdings", "uploads")

# 扩展名白名单（.lower() 归一化后校验）
_ALLOWED_EXT = {".xlsx"}
# 大小上限 10MB
_MAX_BYTES = 10 * 1024 * 1024
# 行数上限（防超大文件解析过载）
_MAX_ROWS = 5000
# PK zip 魔数（xlsx 本质是 zip；改扩展名伪装的文件首 4 字节不是此值）
_PK_MAGIC = b"PK\x03\x04"
# 未消费文件 TTL（秒）——1h
_FILE_TTL = 3600

# ── 错误码（机器可判定短标识，前端按 code 分支动作）──
UPLOAD_BAD_FILE = "UPLOAD_BAD_FILE"  # 扩展名/魔数/解析失败
UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"  # 超过 10MB 上限
UPLOAD_TOO_MANY_ROWS = "UPLOAD_TOO_MANY_ROWS"  # 超过 5000 行上限
UPLOAD_EMPTY = "UPLOAD_EMPTY"  # 空持仓/无有效账户


class UploadError(Exception):
    """上传校验失败（携带 error_code + 中文消息，供 handler 映射 HTTP 响应）。"""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


# ── file_id 注册表（内存映射，TTL 过期失效）────────────────

_file_registry: dict[str, tuple[str, float]] = {}
_registry_lock = threading.Lock()


def _register(file_id: str, path: str) -> None:
    with _registry_lock:
        _file_registry[file_id] = (path, time.time())


def resolve_file(file_id: str) -> str | None:
    """按 file_id 解析临时文件路径；不存在/已过期返回 None。

    过期项立即注销并删除文件（惰性清理）。
    """
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if entry is None:
            return None
        path, created = entry
        if time.time() - created > _FILE_TTL:
            _file_registry.pop(file_id, None)
            _remove_quiet(path)
            return None
        return path


def discard_file(file_id: str) -> None:
    """生成任务结束立即删除上传临时文件并注销 file_id。"""
    with _registry_lock:
        entry = _file_registry.pop(file_id, None)
    if entry is not None:
        _remove_quiet(entry[0])


def cleanup_expired(now: float | None = None) -> int:
    """清理过期未消费文件（惰性触发）。返回清理数量。"""
    now = now or time.time()
    expired: list[tuple[str, str]] = []
    with _registry_lock:
        for fid, (path, created) in list(_file_registry.items()):
            if now - created > _FILE_TTL:
                expired.append((fid, path))
                _file_registry.pop(fid, None)
    for _, path in expired:
        _remove_quiet(path)
    if expired:
        logger.info("[web-upload] 清理过期上传文件 %d 个", len(expired))
    return len(expired)


def cleanup_all() -> int:
    """启动时清理全部残留上传文件。返回清理数量。"""
    count = 0
    if os.path.isdir(_UPLOAD_DIR):
        for name in os.listdir(_UPLOAD_DIR):
            path = os.path.join(_UPLOAD_DIR, name)
            if _remove_quiet(path):
                count += 1
    with _registry_lock:
        _file_registry.clear()
    if count:
        logger.info("[web-upload] 启动清理残留上传文件 %d 个", count)
    return count


# ── 校验与落盘 ─────────────────────────────────────────


def _validate_extension(filename: str | None) -> None:
    """扩展名白名单校验（.lower() 归一化）。失败抛 UploadError。"""
    if not filename:
        raise UploadError(UPLOAD_BAD_FILE, "未提供文件名")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXT:
        raise UploadError(UPLOAD_BAD_FILE, "仅支持 .xlsx 格式的持仓文件")


def _read_and_validate_stream(stream: BinaryIO) -> bytes:
    """读流（计数 + PK 魔数校验），返回完整字节（供落盘）。

    读前 4 字节校验 zip 魔数（防改扩展名伪装）；全程计数，超 10MB 即拒。
    """
    head = stream.read(4)
    if len(head) < 4 or head != _PK_MAGIC:
        raise UploadError(UPLOAD_BAD_FILE, "文件内容不是有效的 Excel（xlsx）格式")
    total = len(head)
    buf = bytearray(head)
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_BYTES:
            raise UploadError(UPLOAD_TOO_LARGE, "文件超过 10MB 上限")
        buf.extend(chunk)
    return bytes(buf)


def _persist_atomic(data: bytes) -> str:
    """mkstemp 落盘 + os.replace 原子写为 {uuid}.xlsx。返回最终路径。"""
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_UPLOAD_DIR, prefix=".upload-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except Exception:
        _remove_quiet(tmp_path)
        raise
    final_name = f"{secrets.token_urlsafe(16)}.xlsx"
    final_path = os.path.join(_UPLOAD_DIR, final_name)
    os.replace(tmp_path, final_path)
    return final_path


def _prevalidate(
    path: str,
    *,
    get_xlsx_info: Callable | None = None,
    read_holdings: Callable | None = None,
) -> dict:
    """内容预检：行数上限 + 空持仓/无有效账户校验。

    复用核心 reader（表头/数值/行级容错已有）。返回
    ``{"sheets": [...], "rows": int, "count": int}``；超限/空持仓抛 UploadError。
    """
    from src.python.core.reader import get_xlsx_info as _real_get_info
    from src.python.core.reader import read_holdings as _real_read

    get_xlsx_info = get_xlsx_info or _real_get_info
    read_holdings = read_holdings or _real_read

    try:
        info = get_xlsx_info(path)
    except Exception as e:
        # 兜底：伪造 zip 等未预期读取异常统一转 BAD_FILE（防 500）
        logger.warning("[web-upload] 元信息读取异常: %s", e)
        raise UploadError(UPLOAD_BAD_FILE, "文件无法读取，请确认是完整的 xlsx 文件") from e
    if isinstance(info, dict) and info.get("error"):
        raise UploadError(UPLOAD_BAD_FILE, "文件无法读取，请确认是完整的 xlsx 文件")
    sheets = list(info.get("sheet_names", []))
    rows = int(info.get("total_rows", 0) or 0)
    if rows > _MAX_ROWS:
        raise UploadError(UPLOAD_TOO_MANY_ROWS, f"持仓行数超过上限（{_MAX_ROWS} 行），请拆分后重试")

    try:
        holdings = read_holdings(path)
    except Exception as e:
        logger.warning("[web-upload] 持仓预检解析失败: %s", e)
        raise UploadError(UPLOAD_BAD_FILE, "持仓文件解析失败，请确认为标准四列格式") from e
    if not holdings:
        raise UploadError(UPLOAD_EMPTY, "持仓文件为空或无有效账户，请检查文件内容")

    return {"sheets": sheets, "rows": rows, "count": len(holdings)}


def save_upload(
    stream: BinaryIO,
    original_filename: str | None,
    *,
    get_xlsx_info: Callable | None = None,
    read_holdings: Callable | None = None,
) -> dict:
    """完整上传链路：校验 → 落盘 → 预检 → 注册，返回 ``{file_id, sheets, rows, count}``。

    Args:
        stream: 可读二进制流（Flask request.files["file"].stream）
        original_filename: 原始文件名（仅用于扩展名校验；落盘丢弃改 uuid）
        get_xlsx_info / read_holdings: 内容预检注入点（测试传 fake）

    Returns:
        {"file_id": str, "sheets": [...], "rows": int, "count": int}

    Raises:
        UploadError: 任一校验环节失败（error_code + 中文消息）
    """
    _validate_extension(original_filename)
    data = _read_and_validate_stream(stream)
    # 惰性清理过期文件（避免额外后台线程）
    cleanup_expired()

    path = _persist_atomic(data)
    try:
        info = _prevalidate(path, get_xlsx_info=get_xlsx_info, read_holdings=read_holdings)
    except Exception:
        _remove_quiet(path)
        raise

    file_id = secrets.token_urlsafe(16)
    _register(file_id, path)
    return {"file_id": file_id, **info}


def _remove_quiet(path: str) -> bool:
    """尽力删除文件（不存在/权限异常静默忽略）。返回是否删除。"""
    try:
        os.remove(path)
        return True
    except OSError:
        return False
