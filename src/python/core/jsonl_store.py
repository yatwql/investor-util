"""JSONL 事件存储原语 — 原子追加 + 容错读取（core 层共享）。

本模块抽出 `core/perf.py` 与 `core/decision_ledger.py` 中**逐字重复**的
原子追加实现，避免第三份拷贝（`core/signal_ledger.py` 亦需要同一原语）。

设计约束遵从（对齐 `core/perf.py` / `core/decision_ledger.py` 先例）：
    分层约束  — 本模块属 core 层，只依赖 stdlib，禁止 import report/llm/analysis
    原子写入  — 读全部现有内容 → 追加新行 → tempfile.mkstemp + os.replace 写回，
                防断电/崩溃产生半写损坏档
    无单例    — 纯函数集，不驻留模块全局状态
    日志统一  — logging.getLogger("invest")；log_tag/noun 由调用方注入，
                保证迁移后各调用点日志文本逐字不变

调用方（各自保持原有 prefix / log_tag / noun）：
    core/perf.py            → prefix=".perf_history_"      tag="perf"
    core/decision_ledger.py → prefix=".decision_ledger_"   tag="decision_ledger"
    core/signal_ledger.py   → prefix=".signal_ledger_"     tag="signal_ledger"
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

logger = logging.getLogger("invest")


def append_jsonl_atomic(
    path: str,
    line: str,
    *,
    prefix: str = ".jsonl_",
    log_tag: str = "jsonl",
    noun: str = "JSONL 文件",
) -> bool:
    """向 JSONL 文件原子追加一行（`line` 需自带结尾换行）。

    Args:
        path: 目标 JSONL 文件路径（父目录不存在时自动创建）
        line: 已序列化的单行内容（含 "\\n"）
        prefix: 临时文件名前缀（各调用点保留原值，便于故障定位）
        log_tag: 日志标签（如 "perf"）
        noun: 日志中对该文件的称谓（如 "历史文件" / "账本"）

    Returns:
        是否落盘成功。写盘异常已在内部记日志并**不向上抛出**（本原语只负责尽力
        持久化，不承担中断调用链的职责）；但必须把成败**如实返回**——调用方若对
        外承诺「已写入 N 条」，就得据此判定，否则写盘失败会被报成成功。
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    existing = ""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        except OSError:
            logger.warning("[%s] %s不可读，将重新创建: %s", log_tag, noun, path)

    content = existing + line
    try:
        fd, tmp_path = tempfile.mkstemp(dir=parent or ".", prefix=prefix, suffix=".tmp")
    except OSError:
        logger.exception("[%s] 创建临时文件失败: %s", log_tag, path)
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        logger.exception("[%s] 写入%s失败: %s", log_tag, noun, path)
        return False
    return True


def read_jsonl(
    path: str,
    *,
    log_tag: str = "jsonl",
    noun: str = "JSONL 文件",
) -> list[dict[str, Any]]:
    """读取全量记录（按写入顺序）。

    损坏行（JSON 解析失败）跳过并告警，不中断后续行；文件不存在返回空列表。
    非 dict 的合法 JSON 行（如裸数组/标量）同样跳过——账本契约只认对象。
    """
    if not os.path.isfile(path):
        return []
    records: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("[%s] 忽略损坏行: %s", log_tag, line[:80])
                    continue
                if isinstance(parsed, dict):
                    records.append(parsed)
                else:
                    logger.warning("[%s] 忽略非对象行: %s", log_tag, line[:80])
    except OSError:
        logger.warning("[%s] %s读取失败: %s", log_tag, noun, path)
    return records
