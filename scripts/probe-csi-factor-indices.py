#!/usr/bin/env python3
"""CSI 风格指数可用性探测 — plan-7 因子暴露分析的前置决策闸门。

在实施 plan-7（因子暴露分析）之前，必须验证候选 CSI 风格指数代码是否
能被现有历史 K 线链路返回有效数据。本脚本对候选代码逐个请求 K 线 API，
统计有效条数，并按 plan-advanced-analysis.md §4 的判定标准输出可行性评级，
以决定 plan-7 去留。

用法：
  python scripts/probe-csi-factor-indices.py            # 默认 5 个 CSI + 附加探测
  python scripts/probe-csi-factor-indices.py --days 365 # 调整窗口（回归建议 ≥365）
  python scripts/probe-csi-factor-indices.py --threshold 60   # 调整有效条数阈值
  python scripts/probe-csi-factor-indices.py --stale 120      # 调整数据新鲜度阈值（天）

输出：
  每个候选代码的 K 线条数 / 首末日期 / 距今天数 / 最近收盘价 + 链路探测 + 综合判定

判定标准（对齐 plan-advanced-analysis.md §4.3 + 数据新鲜度维度）：
  有效 = 条数 ≥ threshold 且 最新日期距今 ≤ stale 天（排除停更指数——仅看条数
  会误判停更数据，如 300 成长曾返回 30 条 2023 年旧数据）
  - 全部 5 个代码有效 → ✅ 全量 5 因子可行
  - 至少 3 个代码有效 → ✅ MVP 3 因子可行（停更因子需找替代代理），动量/低波标实验性
  - 仅 1-2 个代码有效 → ❌ 不可行，因子暴露分析在免费数据源下不可实现

说明：
  - 纯只读探测，不写缓存文件、不写降级记录，无副作用。
  - 候选代码均带上证前缀（sh），与 _A_INDICES 中既有指数（sh000300 等）同格式。
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
from datetime import date
from typing import Any

# ── 项目路径 ──────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")

# ── 候选 CSI 风格指数 ─────────────────────────────────
# 来源：plan-advanced-analysis.md §4 因子代理指数表
# sh = 上证（中证指数统一挂上证前缀，与 _A_INDICES 既有 sh000300 一致）
_CSI_CANDIDATES: list[tuple[str, str]] = [
    ("sh000919", "300 价值"),
    ("sh000920", "300 成长"),
    ("sh000922", "500 价值"),
    ("sh000925", "500 成长"),
    ("sh000930", "中证 300 质量"),
]

# 附加探测：低波因子（文档提及，可用性未知）
_CSI_EXTRA: list[tuple[str, str]] = [
    ("sh000931", "中证低波"),
]

# 历史 K 线 provider 探测：确认哪些模块实现了 fetch_index_kline
_HISTORY_PROVIDER_MODULES = {
    "tencent": "src.python.providers.tencent",
    "sina": "src.python.providers.sina",
}


def _has_fetch_index_kline(module_path: str) -> bool:
    """探测模块是否实现 fetch_index_kline（核实文档与实现一致性）。"""
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return False
    return callable(getattr(mod, "fetch_index_kline", None))


def _days_since(date_str: str | None) -> int:
    """计算日期距今的天数；解析失败返回 -1（表示无数据/未知）。"""
    if not date_str:
        return -1
    try:
        d = date.fromisoformat(date_str)
        return (date.today() - d).days
    except (TypeError, ValueError):
        return -1


def probe_code(code: str, days: int, provider: str = "tencent") -> list[dict[str, Any]]:
    """直接调用指定 provider 的指数 K 线函数（只读，不写缓存）。

    计划文档意图是"逐个调用 sina.fetch_index_kline"。实测两 provider 均具备
    `fetch_index_kline`（Sina 经 `sina_kline` 子模块再导出）。此处直调 provider
    层，避开 chain 的缓存/降级副作用，纯粹反映数据源可用性。
    """
    if provider == "sina":
        from src.python.providers.sina import fetch_index_kline
    else:
        from src.python.providers.tencent import fetch_index_kline

    return fetch_index_kline(code, days=days)


def evaluate(
    freshness: dict[str, int],
    threshold: int,
    stale: int,
) -> dict[str, Any]:
    """按 plan-advanced-analysis.md §4.3 + 数据新鲜度判定标准评估可用性。

    Args:
        freshness: 代码 → 距今天数（最新数据距今），-1 表示无数据
        threshold: 有效数据条数阈值
        stale: 数据新鲜度阈值（天），最新日期距今超过该值视为停更/陈旧

    Returns:
        {"verdict": "5f|3f|infeasible", "available": [...], "message": str,
         "stale_codes": [...], "stale_threshold_days": int}
    """
    available = [c for c, d in freshness.items() if d >= 0 and d <= stale]
    stale_codes = [c for c, d in freshness.items() if d > stale]
    total = len(freshness)

    if len(available) == total and total == 5:
        return {
            "verdict": "5f",
            "available": available,
            "stale_codes": stale_codes,
            "stale_threshold_days": stale,
            "message": "✅ 全部 5 个因子代理指数均可用且数据新鲜 → 全量 5 因子可行",
        }
    if len(available) >= 3:
        suffix = ""
        if stale_codes:
            suffix = f"；停更指数 {stale_codes} 需在实施时找替代代理"
        return {
            "verdict": "3f",
            "available": available,
            "stale_codes": stale_codes,
            "stale_threshold_days": stale,
            "message": (
                f"✅ 至少 3 个因子代理指数可用且数据新鲜 → MVP 3 因子可行{suffix}，"
                "动量/低波标记为实验性"
            ),
        }
    return {
        "verdict": "infeasible",
        "available": available,
        "stale_codes": stale_codes,
        "stale_threshold_days": stale,
        "message": "❌ 仅 1-2 个代码可用 → 因子暴露分析在免费数据源下不可实现，建议按 plan-4 模式放弃",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CSI 风格指数可用性探测（plan-7 前置决策闸门）",
    )
    parser.add_argument("--days", type=int, default=30, help="K 线窗口天数（默认 30）")
    parser.add_argument("--threshold", type=int, default=20, help="有效数据条数阈值（默认 20）")
    parser.add_argument("--stale", type=int, default=120, help="数据新鲜度阈值（天，默认 120；最新日期距今超过即视为停更）")
    parser.add_argument("--provider", choices=["tencent", "sina"], default="tencent", help="探测数据源（默认 tencent；sina 用于对照验证）")
    parser.add_argument("--codes", nargs="*", default=None, help="覆盖候选代码（可传多个，格式 sh000919；不传则用内置候选表）")
    parser.add_argument("--no-extra", action="store_true", help="不探测附加代码（000931 低波）")
    args = parser.parse_args()

    days = min(max(args.days, 5), 2000)  # Tencent K 线实际上限约 2000 天（3650 返回空/崩溃，见 probe 说明）
    threshold = max(args.threshold, 1)
    stale = max(args.stale, 1)

    candidates = list(_CSI_CANDIDATES)
    if not args.no_extra:
        candidates.extend(_CSI_EXTRA)
    if args.codes:
        # --codes 覆盖时只探测指定代码（不自动补名称，用于对照验证）
        candidates = [(c, c) for c in args.codes]

    # ── 链路探测 ──────────────────────────────────────
    print("[..] 探测历史 K 线 provider 实现情况…")
    for name, module_path in _HISTORY_PROVIDER_MODULES.items():
        has = _has_fetch_index_kline(module_path)
        marker = "[OK]" if has else "[!]"
        print(f"  {marker} {name}: fetch_index_kline = {has}")

    # ── 逐个探测 ──────────────────────────────────────
    counts: dict[str, int] = {}
    freshness: dict[str, int] = {}
    details: dict[str, dict[str, Any]] = {}

    print(f"\n[..] 探测 {len(candidates)} 个候选代码（provider={args.provider}，窗口 {days} 天，阈值 {threshold} 条，新鲜度 {stale} 天）…")

    for code, name in candidates:
        try:
            bars = probe_code(code, days, provider=args.provider)
        except Exception as e:  # noqa: BLE001 — 单代码失败不中断整体探测
            logger = logging.getLogger("invest")
            logger.warning("代码 %s 探测异常: %s", code, e)
            bars = []

        n = len(bars)
        last_date = bars[-1]["date"] if bars else None
        last_close = bars[-1]["close"] if bars else None
        age = _days_since(last_date)

        counts[code] = n
        freshness[code] = age if n > 0 else -1
        detail: dict[str, Any] = {"name": name, "bars": n}
        if bars:
            detail["first_date"] = bars[0]["date"]
            detail["last_date"] = last_date
            detail["last_close"] = last_close
            detail["age_days"] = age
        details[code] = detail

        fresh = 0 <= age <= stale
        if n >= threshold and fresh:
            marker = "[OK]"
        elif n >= threshold and not fresh:
            marker = "[!]"  # 条数够但已停更 → 判定为不可用
        elif n > 0:
            marker = "[!]"
        else:
            marker = "[ERR]"
        print(f"  {marker} {code} {name}: {n} 条", end="")
        if bars:
            print(
                f"（{bars[0]['date']} ~ {last_date}，距今天数 {age}d，"
                f"最新收盘 {last_close}）"
            )
        else:
            print(" — 无有效数据")

    # ── 综合判定 ──────────────────────────────────────
    # 判定基于 5 个主候选（不含附加探测的 000931）
    main_freshness = {c: freshness[c] for c, _ in _CSI_CANDIDATES if c in freshness}
    result = evaluate(main_freshness, threshold, stale)

    print("\n" + "=" * 64)
    print(f"[..] 主候选（5 因子）有效代码: {result['available'] or '无'}")
    print(f"      停更代码（> {stale} 天无更新）: {result['stale_codes'] or '无'}")
    print(f"      {result['message']}")

    # 附加代码信息
    for code, name in _CSI_EXTRA:
        age = freshness.get(code, -1)
        if counts.get(code, 0) >= threshold and 0 <= age <= stale:
            print(f"  [!] 附加探测 {code} {name}: {counts[code]} 条，距今天数 {age}d → 低波因子可作为补充候选")

    print("=" * 64)
    print("\n建议（plan-7 决策）：")
    if result["verdict"] == "5f":
        print("  → 实施完整 5 因子暴露分析（3.5d）")
    elif result["verdict"] == "3f":
        print("  → 实施 MVP 3 因子（价值+成长+质量），动量/低波标记实验性（~2.5d）")
    else:
        print("  → 不可行，建议放弃 plan-7（按 plan-4 模式归档）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
