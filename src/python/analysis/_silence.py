"""再平衡静默期管理模块。

管理再平衡信号的静默期持久化状态：
  - 记录每品种触发日期
  - 过滤静默期内重复信号
  - 过期条目自动清理
"""

from __future__ import annotations

import json
import logging
import os
import datetime
from typing import Any

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 静默期管理 ──────────────────────────────────────────

# 静默期持久化路径（可通过 monkeypatch.setattr 注入测试路径）
_SILENCE_FILE = os.path.join(PROJECT_ROOT, "data/state/rebalance_silence.json")


def _load_silence_state(silence_file: str | None = None) -> dict[str, str]:
    """从持久化文件加载静默期状态。

    Args:
        silence_file: 静默期文件路径。为 None 时使用 _SILENCE_FILE。

    Returns:
        {品种代码: 触发日期 (YYYY-MM-DD)}
    """
    path = silence_file or _SILENCE_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("再平衡静默期文件格式异常，将重置: %s", path)
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("再平衡静默期文件读取失败，将重置: %s", e)
        return {}


def _save_silence_state(state: dict[str, str], silence_file: str | None = None) -> None:
    """持久化静默期状态到文件。

    Args:
        state: {品种代码: 触发日期 (YYYY-MM-DD)}
        silence_file: 静默期文件路径。为 None 时使用 _SILENCE_FILE。
    """
    path = silence_file or _SILENCE_FILE
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("再平衡静默期文件写入失败: %s", e)


def _filter_silenced_signals(
    signals: list[dict[str, Any]],
    silence_days: int,
    silence_file: str | None = None,
) -> list[dict[str, Any]]:
    """过滤静默期内的再平衡信号。

    对于有 code 的信号（单品超限、品种级偏离），检查是否在静默期内。
    大类偏离信号（category）不参与静默期检查。
    静默期到期的条目自动从持久化状态中清理。

    Args:
        signals: 再平衡信号列表
        silence_days: 静默期天数
        silence_file: 静默期文件路径

    Returns:
        过滤后的信号列表（附静默信息）
    """
    if not signals or silence_days <= 0:
        return signals

    state = _load_silence_state(silence_file)
    today = datetime.date.today()
    expired_codes: set[str] = set()

    result = []
    for sig in signals:
        code = sig.get("code", "")
        if code and sig.get("type") not in ("category", "summary"):
            trigger_str = state.get(code)
            if trigger_str:
                try:
                    trigger_date = datetime.datetime.strptime(trigger_str, "%Y-%m-%d").date()
                    days_passed = (today - trigger_date).days
                except (ValueError, TypeError):
                    # 日期格式异常，视为过期
                    expired_codes.add(code)
                    result.append(sig)
                    continue

                if days_passed < silence_days:
                    # 静默期内：跳过（不加入结果）
                    continue
                else:
                    # 静默期已过，清理
                    expired_codes.add(code)

        result.append(sig)

    # 清理过期条目
    if expired_codes:
        for c in expired_codes:
            state.pop(c, None)
        _save_silence_state(state, silence_file)

    return result


def _update_silence_state(
    signals: list[dict[str, Any]],
    silence_file: str | None = None,
) -> None:
    """将新触发的信号更新到静默期持久化状态。

    Args:
        signals: 再平衡信号列表
        silence_file: 静默期文件路径
    """
    state = _load_silence_state(silence_file)
    today_str = datetime.date.today().isoformat()
    updated = False

    for sig in signals:
        code = sig.get("code", "")
        if code and sig.get("type") not in ("category", "summary"):
            if code not in state:
                state[code] = today_str
                updated = True

    if updated:
        _save_silence_state(state, silence_file)
