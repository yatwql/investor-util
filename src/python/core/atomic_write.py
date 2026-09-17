"""原子整文件写入原语 — 同目录临时文件 + os.replace（core 层共享）。

问题（缓存原子写入约束）：`open(path, "w") + json.dump()` 直接覆盖落盘，
进程在写入途中被中断（Ctrl-C / 断电 / OOM）时目标文件停留在半写状态——
下次读取拿到的是截断内容，JSON 解析失败即整份持久化状态丢失。原子写入的
语义是「要么旧内容、要么新内容，不存在中间态」：先把新内容写进**同目录**的
临时文件（同目录保证同文件系统，`os.replace` 才是原子 rename 而非跨设备拷贝），
再 `os.replace` 顶替目标。

本模块抽出原先散落各处的逐字重复 mkstemp + os.replace 实现，避免第 N 份拷贝。

两处**有意不合并**（契约相反，非疏漏）：
  - `cache/_io.py` + `cache/_store.py`：需 gzip 分支与文件锁，另有读写一致性约束。
  - `config/_core.py::_atomic_write`：契约是「失败即抛且**保留异常类型**」——
    `init_config()` 的 `except PermissionError` Windows 并发容忍分支、TUI 把
    `PermissionError` 映射为「权限不足」提示，都依赖传得出异常类型；而本原语刻意
    吞掉异常、只返回布尔。原子写入要求的 mkstemp + os.replace 语义两者一致。

设计约束遵从（对齐 `core/jsonl_store.py` 先例）：
    分层约束  — 本模块属 core 层，只依赖 stdlib，禁止 import report/llm/analysis
    无单例    — 纯函数集，不驻留模块全局状态
    日志统一  — logging.getLogger("invest")；log_tag/noun 由调用方注入

调用方（各自保持原有 prefix / log_tag / noun）：
    core/jsonl_store.py                  → prefix=".jsonl_"     tag="jsonl"
                                            （news_dedup 经 append_jsonl_atomic_many 走此入口）
    core/provider_registry.py            → 熔断状态
    report/history_snapshot.py           → 持仓快照
    config/features.py                   → 功能开关覆写
    analysis/_silence.py                 → 静默期状态
    analysis/circuit_breaker_wrapper.py  → 指标断路状态
    report/data_status.py                → 数据源降级状态
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger("invest")


def write_text_atomic(
    path: str,
    content: str,
    *,
    prefix: str = ".atomic_",
    log_tag: str = "atomic",
    noun: str = "文件",
) -> bool:
    """原子写入文本文件（父目录不存在时自动创建）。

    Args:
        path: 目标文件路径
        content: 完整的目标内容（覆盖式写入，非追加）
        prefix: 临时文件名前缀（各调用点保留原值，便于故障定位）
        log_tag: 日志标签（如 "breaker"）
        noun: 日志中对该文件的称谓（如 "静默期状态"）

    Returns:
        是否落盘成功。写盘异常已在内部记日志并**不向上抛出**（本原语只负责尽力
        持久化，不承担中断调用链的职责）；但必须把成败**如实返回**——调用方若
        依赖「已持久化」这一前提做后续动作（如迁移成功后删除旧文件），就得据此
        判定，否则会在写入失败时误删唯一的数据源。
    """
    parent = os.path.dirname(path)
    try:
        # 建目录也纳入守护：父路径被占（同名文件）等场景下 makedirs 会抛
        # FileExistsError/PermissionError，若逸出则违背「本原语不抛出」的契约，
        # 而调用方（如 news_dedup 锚点写入）正是靠返回值而非异常判定成败。
        if parent:
            os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=parent or ".", prefix=prefix, suffix=".tmp")
    except OSError:
        logger.exception("[%s] 准备写入失败（创建目录或临时文件）: %s", log_tag, path)
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        _replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        logger.exception("[%s] 写入%s失败: %s", log_tag, noun, path)
        return False
    return True


def write_json_atomic(
    path: str,
    data: Any,
    *,
    indent: int | None = 2,
    prefix: str = ".atomic_",
    log_tag: str = "atomic",
    noun: str = "状态文件",
) -> bool:
    """原子写入 JSON 文件（序列化 → :func:`write_text_atomic`）。

    Args:
        path: 目标文件路径
        data: 待序列化对象（须可由 json.dumps 处理）
        indent: 缩进（None → 紧凑单行）；默认 2 空格，保持各调用点原有落盘形态
        其余参数同 :func:`write_text_atomic`

    Returns:
        是否落盘成功（语义同 :func:`write_text_atomic`）。
    """
    try:
        content = json.dumps(data, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError):
        logger.exception("[%s] %s序列化失败: %s", log_tag, noun, path)
        return False
    return write_text_atomic(path, content, prefix=prefix, log_tag=log_tag, noun=noun)


def _replace(tmp_path: str, path: str) -> None:
    """临时文件 → 目标文件（os.replace；Windows 文件被占用时降级重试）。

    Windows 上 os.replace 目标若被其它进程持有句柄会抛 PermissionError；
    与 `cache/_io.py::_write_atomic` 同一处置——先删目标再 rename。该回退路径
    失去原子性（存在短暂的无文件窗口），仅作为 Windows 占用的兜底，
    POSIX 下始终走 os.replace 的原子路径。
    """
    try:
        os.replace(tmp_path, path)
    except PermissionError:
        if os.path.exists(path):
            os.remove(path)
        os.rename(tmp_path, path)
