"""本地机器状态 — `data/state/local_state.json` 读写。

存放仅本机有意义、不应随 config.json 同步的状态标志（如首次运行引导/隐私提示
已读标记）。config.json 是跨机器同步的配置文件（受 git 跟踪），本地状态混入其中
会导致每台机器各自写入差异、难以同步；故独立存放于 `data/state/`（git 忽略目录）。

职责：
  - get_flag(key) — 读取布尔状态标志
  - set_flag(key, value) — 写入布尔状态标志

架构约束：
  - 写入复用 `config._core._atomic_write` 原子写
"""

from __future__ import annotations

import json
import logging
import os

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# 本地状态文件（data/state/ 被 git 忽略，仅本机可见）
_LOCAL_STATE_FILE = os.path.join(PROJECT_ROOT, "data", "state", "local_state.json")


def get_local_state() -> dict:
    """读取本地状态 dict（文件不存在或损坏 → 空 dict）。"""
    try:
        if os.path.exists(_LOCAL_STATE_FILE):
            with open(_LOCAL_STATE_FILE, encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        logger.debug("[local-state] 读取失败（非关键），按空处理", exc_info=True)
    return {}


def _write_local_state(data: dict) -> None:
    """原子写入本地状态文件（父目录不存在时创建）。"""
    from src.python.config._core import _atomic_write

    os.makedirs(os.path.dirname(_LOCAL_STATE_FILE), exist_ok=True)
    _atomic_write(_LOCAL_STATE_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def get_flag(key: str) -> bool:
    """读取布尔状态标志。"""
    data = get_local_state()
    return bool(data.get(key, False))


def set_flag(key: str, value: bool) -> None:
    """写入布尔状态标志。"""
    data = get_local_state()
    data[key] = bool(value)
    _write_local_state(data)
