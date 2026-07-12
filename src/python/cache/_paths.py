"""缓存引擎 — 路径/常量子模块。

职责：缓存目录路径、gzip 阈值、路径构造函数。
"""

from __future__ import annotations

import os

from src.python.constants import PROJECT_ROOT

# 项目根路径从 constants.py 统一导入，避免因重构移动文件导致的路径偏移
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
