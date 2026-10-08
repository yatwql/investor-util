"""主菜单页头状态行 — 五项常驻紧凑状态的组装与渲染。

每项指标全部取自本地既有单源（不新增任何外部网络调用）：

  - 上次报告时间  ← ``core/perf`` 的 ``perf_history.jsonl`` 末条记录
  - 缓存过期数    ← ``cache`` 的 ``get_cache_stats().expired``（清单预估）
  - 数据新鲜度    ← 最新价格缓存的 ``price_date``（数据日期 + 自然日龄；
    页头不引入交易日历取数——日历缓存未命中时会走 akshare 触网）
  - 降级源数      ← ``core/perf`` 的 ``datasource_health.jsonl`` 末条 ``fail_count``
  - LLM 状态点    ← ``core/system_info.llm_status``（● 已配置 / ○ 未配置）

契约：

  - 逐项独立容错——单项取数异常降级为「—」，不影响其余项；
  - 整行组装异常降级为 ``状态 │ —``，永不向调用方抛出；
  - TTL 记忆化（页头随主循环重绘，重取限频），``reset_status_memo`` 供测试。
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_STATUS_TTL = 45.0  # 页头重绘频繁，缓存/健康历史等重取限频（秒）
_memo: dict[str, Any] = {}


def _last_report_part() -> str:
    """上次报告时间（perf 历史末条时间戳）。"""
    try:
        from src.python.core.perf import load_history

        records = load_history()
        if not records:
            return "上次报告 —"
        ts = str(records[-1].get("timestamp") or "")
        return f"上次报告 {datetime.fromisoformat(ts):%m-%d %H:%M}"
    except Exception:
        logger.debug("状态行「上次报告」取数失败，降级为 —", exc_info=True)
        return "上次报告 —"


def _cache_expired_part() -> str:
    """缓存过期数（与菜单 [4] 同一统计口径）。"""
    try:
        from src.python.cache.operations import get_cache_stats
        from src.python.report.progress import SilentProgressReporter

        stats = get_cache_stats(SilentProgressReporter())
        return f"缓存过期 {stats.expired}"
    except Exception:
        logger.debug("状态行「缓存过期」取数失败，降级为 —", exc_info=True)
        return "缓存过期 —"


def _freshness_part() -> str:
    """数据新鲜度（最新一条价格缓存的数据日期与自然日龄，纯本地读数）。"""
    try:
        from src.python.cache import get, get_cache_dir

        cache_dir = get_cache_dir()
        if not os.path.isdir(cache_dir):
            return "新鲜度 —"
        newest_stem, newest_mtime = "", 0.0
        for fname in os.listdir(cache_dir):
            if not fname.startswith("price_") or not fname.endswith(".json"):
                continue
            try:
                mtime = os.path.getmtime(os.path.join(cache_dir, fname))
            except OSError:
                continue
            if mtime > newest_mtime:
                newest_mtime, newest_stem = mtime, fname[: -len(".json")]
        if not newest_stem:
            return "新鲜度 —"
        payload = get(newest_stem)
        detail = payload.get("_data") if isinstance(payload, dict) and "_data" in payload else payload
        if not isinstance(detail, dict):
            return "新鲜度 —"
        raw_date = detail.get("nav_date") or detail.get("price_date")
        if not raw_date:
            return "新鲜度 —"
        date_obj = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
        age = max((datetime.now().date() - date_obj).days, 0)
        return f"新鲜度 {date_obj:%m-%d}（{age}天）"
    except Exception:
        logger.debug("状态行「新鲜度」取数失败，降级为 —", exc_info=True)
        return "新鲜度 —"


def _degraded_part() -> str:
    """降级源数（最近一次健康历史的失败源计数，无记录显示 —）。"""
    try:
        from src.python.core.perf import summarize_health_history

        rows = summarize_health_history(limit=1)
        if not rows:
            return "降级源 —"
        return f"降级源 {int(rows[-1].get('fail_count') or 0)}"
    except Exception:
        logger.debug("状态行「降级源」取数失败，降级为 —", exc_info=True)
        return "降级源 —"


def _llm_part() -> str:
    """LLM 状态点（● 已配置 / ○ 未配置，判定与 [S] 状态同源）。"""
    try:
        from src.python.core.system_info import llm_status

        return "LLM ●" if llm_status().get("configured") else "LLM ○"
    except Exception:
        logger.debug("状态行「LLM」取数失败，降级为 —", exc_info=True)
        return "LLM —"


def build_status_line(*, now: float | None = None) -> str:
    """组装页头状态行（TTL 内复用记忆；任何异常降级为 ``状态 │ —``）。

    Args:
        now: 时间戳注入（测试用）；None 取当前时间。

    Returns:
        形如 ``状态 │ 上次报告 10-07 09:55 · 缓存过期 3 · 新鲜度 最新 ·
        降级源 0 · LLM ●〔详情 [4][H][S]〕`` 的单行文本。
    """
    ts = time.time() if now is None else float(now)
    cached = _memo.get("line")
    if cached is not None and ts - float(_memo.get("ts", 0.0)) < _STATUS_TTL:
        return str(cached)
    try:
        parts = [
            _last_report_part(),
            _cache_expired_part(),
            _freshness_part(),
            _degraded_part(),
            _llm_part(),
        ]
        line = "状态 │ " + " · ".join(parts) + "〔详情 [4][H][S]〕"
    except Exception:
        logger.debug("状态行组装失败，降级显示", exc_info=True)
        line = "状态 │ —"
    _memo["line"] = line
    _memo["ts"] = ts
    return line


def reset_status_memo() -> None:
    """清空状态行记忆（测试与手工刷新用）。"""
    _memo.clear()
