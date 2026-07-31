"""缓存引擎 — 路径/常量子模块。

职责：缓存目录路径、gzip 阈值、路径构造函数、目录权限校验。
"""

from __future__ import annotations

import logging
import os
import stat

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# 项目根路径从 constants.py 统一导入，确保路径来源唯一
_CACHE_DIR = os.path.join(PROJECT_ROOT, "data/cache")
_GZIP_THRESHOLD = 100 * 1024  # 100KB 以上的缓存自动 gzip
_GZIP_SUFFIX = ".gz"


def _cache_path(key: str) -> str:
    """返回缓存文件完整路径（始终带 .json 后缀，由 get/set 决定是否追加 .gz）。"""
    # 防止目录穿越
    safe_name = key.replace("/", "_").replace("\\", "_").replace("..", "_")
    return os.path.join(_CACHE_DIR, f"{safe_name}.json")


def get_cache_dir() -> str:
    """返回缓存目录绝对路径。"""
    return os.path.abspath(_CACHE_DIR)


def check_cache_dir_permissions() -> None:
    """检查缓存目录权限，确保目录存在且权限正确。

    目录不存在时自动创建。权限异常时仅记录警告，不影响运行。
    """
    path = get_cache_dir()
    try:
        os.makedirs(path, exist_ok=True)
        # 尝试设置目录权限为 0o700（仅所有者可读写执行）
        try:
            current_mode = stat.S_IMODE(os.stat(path).st_mode)
            if current_mode & 0o077:  # 组/其他有任何权限
                os.chmod(path, current_mode & ~0o077 | 0o700)
        except OSError:
            pass  # Windows 可能不支持完整 chmod
    except OSError as e:
        logger.warning("缓存目录权限检查失败: %s", e)
