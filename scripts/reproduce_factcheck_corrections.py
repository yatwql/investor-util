"""临时复现脚本：对 7/30 penetration_deep 缓存重跑数值校验，提取自动修正明细。

用途：回答"事实校验通过 21/24（自动修正 3 处数值）到底修正了哪些"。
用 data/holdings 持仓 + data/cache 历史行情快照重建当时 holdings_details，
对 3 份 llm_penetration_deep 缓存内容调用 check_numerical_consistency，
打印每份的检查计数与修正三元组 (wrong_value, correct_value, sentence)。

运行时临时产物，放 docs-stm/tmp/，不属于仓库交付物。
"""

import gzip
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.python.core.reader import read_holdings  # noqa: E402
from src.python.llm.fact_checker import check_numerical_consistency  # noqa: E402

_HOLDINGS = "data/holdings/个人投资持仓信息.xlsx"
_CACHE_DIR = "data/cache"


def _last_price(code: str) -> float | None:
    """从历史行情缓存取该代码最后一条 bar 的价格（stock→close / fund→nav）。"""
    pats = glob.glob(os.path.join(_CACHE_DIR, f"history_history_*_{code}*.json*"))
    if not pats:
        return None
    fn = pats[0]
    data = json.loads(
        gzip.open(fn, "rt", encoding="utf-8").read() if fn.endswith(".gz") else open(fn, encoding="utf-8").read()
    )
    bars = data.get("_data") or []
    if not bars:
        return None
    last = bars[-1]
    return last.get("close") or last.get("nav")


def _build_details() -> list[dict]:
    holdings = read_holdings(_HOLDINGS)
    details = []
    for h in holdings:
        px = _last_price(h.code)
        mv = (px or 0) * h.shares
        cost = h.cost_price * h.shares
        details.append(
            {
                "code": h.code,
                "name": h.name,
                "market_value": mv,
                "cost": cost,
                "profit_rate": (mv - cost) / cost * 100 if cost else 0.0,
            }
        )
    return details


def main() -> None:
    details = _build_details()
    total_mv = sum(d["market_value"] for d in details)
    total_cost = sum(d["cost"] for d in details)
    print(f"重建 holdings_details: {len(details)} 条, 总市值 {total_mv:.2f}, 总成本 {total_cost:.2f}\n")

    for stem in (
        "llm_penetration_deep_058c6a25c5b9",
        "llm_penetration_deep_2d8e917d2198",
        "llm_penetration_deep_811257e5d810",
    ):
        path = os.path.join(_CACHE_DIR, f"{stem}_deepseek-main.json")
        if not os.path.exists(path):
            print(f"[!] 缺失 {path}")
            continue
        raw = json.load(open(path, encoding="utf-8"))
        html = raw["_data"]
        issues, checked, passed, corrections = check_numerical_consistency(html, details)
        print("=" * 70)
        print(f"{stem}")
        print(f"  检查 {checked} 项 / 通过 {passed} 项 / 不一致 {len(issues)} 条 / 修正 {len(corrections)} 处")
        if not corrections:
            print("  （无数值修正）")
        for i, (wrong, correct, sentence) in enumerate(corrections, 1):
            snip = sentence if len(sentence) <= 160 else sentence[:160] + "…"
            print(f"  [{i}] {wrong}% → {correct}%")
            print(f"      句段: {snip}")
        if issues and not corrections:
            for iss in issues:
                print(f"  ⚠ {iss}")


if __name__ == "__main__":
    main()
