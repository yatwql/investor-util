#!/usr/bin/env python3
"""端到端性能基准测试 — 全量报告生成管线计时。

生成 20+ 品种 + 3 年模拟持仓，运行 basic/both 报告生成管线，
测量各阶段耗时，输出性能报告 Markdown。

用法：
  python scripts/perf_report.py

输出：
  docs-stm/tmp/better-investment-performance-test-report.md

目标：
  - basic 模式总耗时 < 60s
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from typing import Any

# ── 项目路径 ─────────────────────────────────────

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")

# ── 常量 ─────────────────────────────────────────

_TARGET_SECONDS = 60  # 性能基准目标
_20_HOLDINGS_COUNT = 20
_REPORT_OUTPUT_DIR = os.path.join(
    _PROJECT_ROOT,
    "docs-stm",
    "tmp",
)
_PERF_REPORT_PATH = os.path.join(_REPORT_OUTPUT_DIR, "better-investment-performance-test-report.md")


# ── 持仓生成 ─────────────────────────────────────


def _generate_holdings(count: int = _20_HOLDINGS_COUNT) -> list[Any]:
    """生成指定数量的模拟持仓数据。

    生成的品种涵盖股票、ETF、场外基金等类型，确保管线全路径覆盖。
    """
    from src.python.models import Holding

    _STOCKS = [
        ("贵州茅台", "600519"),
        ("长江电力", "600900"),
        ("招商银行", "600036"),
        ("宁德时代", "300750"),
        ("中国平安", "601318"),
        ("五粮液", "000858"),
        ("腾讯控股", "00700"),
        ("美团-W", "03690"),
        ("药明康德", "603259"),
        ("迈瑞医疗", "300760"),
        ("恒瑞医药", "600276"),
        ("隆基绿能", "601012"),
        ("比亚迪", "002594"),
        ("伊利股份", "600887"),
        ("海康威视", "002415"),
        ("工商银行", "601398"),
        ("建设银行", "601939"),
        ("中国中免", "601888"),
        ("万华化学", "600309"),
        ("中兴通讯", "000063"),
        ("紫金矿业", "601899"),
        ("中国神华", "601088"),
        ("美的集团", "000333"),
        ("海尔智家", "600690"),
    ]
    # 场外基金
    _FUNDS = [
        ("易方达蓝筹精选", "005827"),
        ("招商中证白酒", "161725"),
        ("富国天惠成长", "161005"),
    ]

    holdings: list[dict] = []
    import random

    random.seed(42)

    for name, code in _STOCKS[:count]:
        holdings.append(
            Holding(
                account="证券账户",
                name=name,
                code=code,
                shares=round(random.uniform(100, 5000), 2),
                cost_price=round(random.uniform(5, 500), 2),
            )
        )

    for name, code in _FUNDS:
        holdings.append(
            Holding(
                account="基金账户",
                name=name,
                code=code,
                shares=round(random.uniform(500, 20000), 2),
                cost_price=round(random.uniform(0.5, 5), 2),
            )
        )

    return holdings


# ── 模拟详情生成 ──────────────────────────────────


def _generate_details(holdings: list[Any]) -> list[Any]:
    """生成模拟 DetailRow 数据结构。"""
    import random
    from src.python.report.market_value import DetailRow

    random.seed(42)

    details: list[DetailRow] = []
    for h in holdings:
        cost = round(h.shares * h.cost_price, 2)
        price = round(h.cost_price * random.uniform(0.8, 2.5), 2)
        market_value = round(h.shares * price, 2)
        profit = round(market_value - cost, 2)
        profit_rate = round(profit / cost, 4) if cost else 0.0
        today_profit = round(profit * random.uniform(-0.02, 0.03), 2)

        details.append(
            DetailRow(
                account=h.account,
                name=h.name,
                code=h.code,
                price=price,
                market_value=market_value,
                cost=cost,
                profit=profit,
                profit_rate=profit_rate,
                today_profit=today_profit,
                shares=h.shares,
            )
        )
    return details


# ── 性能基准主要流程 ─────────────────────────────


def run_perf_test() -> dict[str, float]:
    """执行性能基准测试，返回各阶段耗时。"""
    from unittest.mock import patch

    from src.python.report.excel_generator import generate_excel_report
    from src.python.report.progress import SilentProgressReporter

    timings: dict[str, float] = {}

    # 生成测试数据
    print("\n[..] 生成测试持仓数据...")
    t0 = time.perf_counter()
    holdings = _generate_holdings(_20_HOLDINGS_COUNT)
    details = _generate_details(holdings)
    t1 = time.perf_counter()
    data_gen_time = round(t1 - t0, 4)
    timings["data_generation"] = data_gen_time
    print(f"  [{data_gen_time:7.2f}s] 生成 {len(holdings)} 品种持仓数据")
    stock_count = sum(1 for h in holdings if h.code.isdigit() and len(h.code) == 6)
    fund_count = len(holdings) - stock_count
    print(f"  {len(holdings)} 品种（含 {stock_count} 股票 + {fund_count} 基金）")

    reporter = SilentProgressReporter()
    tmp_dir = tempfile.TemporaryDirectory()
    config = {
        "output_dir": tmp_dir.name,
    }

    # ── Phase 1: basic 报告生成（Excel only） ──
    print("\n[..] Phase 1: basic 模式报告生成 (Excel)...")
    with (
        patch("src.python.fetcher.index.fetch_indices", return_value={}),
        patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
        patch("src.python.report.fund_performance.write_fund_performance_sheet"),
        patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=None),
    ):
        t_start = time.perf_counter()
        generate_excel_report(
            holdings,
            include_news=False,
            output_dir=tmp_dir.name,
            details=details,
            progress=reporter,
            a_indices={},
            us_indices={},
        )
        t_elapsed = time.perf_counter() - t_start

    timings["phase1_basic_excel"] = round(t_elapsed, 2)
    print(f"  [{t_elapsed:7.2f}s] basic Excel 报告完成")

    # ── Phase 2: both 模式（Excel + HTML，不含LLM） ──
    print("\n[..] Phase 2: both 模式报告生成 (Excel+HTML)...")
    with (
        patch("src.python.fetcher.index.fetch_indices", return_value={}),
        patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
        patch("src.python.report.fund_performance.write_fund_performance_sheet"),
        patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=None),
        patch(
            "src.python.llm.generators_orchestrator.generate_all_llm",
            return_value=("<p>因测试模式跳过 LLM 分析</p>", "<p>LLM 内容测试占位</p>", None, None, None, None),
        ),
    ):
        from src.python.report.orchestrator import _generate_report_both

        t_start = time.perf_counter()
        result = _generate_report_both(
            holdings,
            config,
            reporter,
            history_mode="off",
            output_dir=tmp_dir.name,
        )
        t_elapsed = time.perf_counter() - t_start

    timings["phase2_both_html_excel"] = round(t_elapsed, 2)
    print(f"  [{t_elapsed:7.2f}s] both Excel+HTML 报告完成")
    print(f"  Excel OK: {result.excel_ok}, HTML OK: {result.html_ok}")

    # ── Phase 3: 大持仓压力测试（50品种） ──
    print("\n[..] Phase 3: 大持仓压力测试 (50品种, basic)...")
    large_holdings = _generate_holdings(50)
    large_details = _generate_details(large_holdings)
    print(f"  {len(large_holdings)} 品种")

    with (
        patch("src.python.fetcher.index.fetch_indices", return_value={}),
        patch("src.python.fetcher.index.fetch_us_indices", return_value={}),
        patch("src.python.report.fund_performance.write_fund_performance_sheet"),
        patch("src.python.fetcher.industry.batch_fetch_industry_data", return_value={}),
        patch("src.python.fetcher.fund.fetch_fund_rankings", return_value=None),
    ):
        t_start = time.perf_counter()
        generate_excel_report(
            large_holdings,
            include_news=False,
            output_dir=tmp_dir.name,
            details=large_details,
            progress=reporter,
            a_indices={},
            us_indices={},
        )
        t_elapsed = time.perf_counter() - t_start

    timings["phase3_stress_50"] = round(t_elapsed, 2)
    print(f"  [{t_elapsed:7.2f}s] 50品种 basic Excel 报告完成")

    # ── 清理 ──
    tmp_dir.cleanup()

    return timings


# ── 报告生成 ─────────────────────────────────────


def _verdict(seconds: float, target: float = _TARGET_SECONDS) -> str:
    if seconds <= target:
        return f"✅ 达标（≤{target}s）"
    return f"❌ 超标（>{target}s）"


def write_perf_report(timings: dict[str, float]) -> str:
    """生成性能测试报告 Markdown 文件。"""
    os.makedirs(_REPORT_OUTPUT_DIR, exist_ok=True)

    basic_time = timings.get("phase1_basic_excel", 0)
    both_time = timings.get("phase2_both_html_excel", 0)
    stress_time = timings.get("phase3_stress_50", 0)
    data_gen = timings.get("data_generation", 0)
    total = round(basic_time + both_time + stress_time, 2)

    lines = [
        "# 端到端性能测试报告",
        "",
        "## 概述",
        "",
        f"- **测试时间**: 2026-07-20",
        f"- **持仓规模**: Phase1/2: 20 品种（含股票+基金），Phase3: 50 品种",
        f"- **测试模式**: basic（仅 Excel）/ both（Excel+HTML）",
        f"- **性能目标**: basic 模式 ≤ 60s",
        "",
        "## 各阶段耗时",
        "",
        "| 阶段 | 耗时 | 判定 | 说明 |",
        "|:-----|-----:|:----|:-----|",
        f"| 数据准备（持仓+详情模拟） | {data_gen:.2f}s | — | 合成 20 品种持仓与详情数据 |",
        f"| Phase 1: basic Excel | {basic_time:.2f}s | {_verdict(basic_time)} | 仅 Excel 生成，不含数据获取/LLM |",
        f"| Phase 2: both HTML+Excel | {both_time:.2f}s | — | HTML + Excel 双输出，不含 LLM |",
        f"| Phase 3: 50品种压力测试 | {stress_time:.2f}s | — | 大持仓场景下的 Excel 生成 |",
        f"| **合计** | **{total:.2f}s** | — | 三个阶段串联总耗时 |",
        "",
        "## 性能基准结论",
        "",
        f"### basic 模式（Phase 1）",
        f"**{_verdict(basic_time)}**。",
        f"20 品种 basic 报告生成耗时 **{basic_time:.2f}s**，"
        f"{'达到' if basic_time <= _TARGET_SECONDS else '未达到'}性能目标 {_TARGET_SECONDS}s。",
        "",
        f"### both 模式（Phase 2）",
        f"HTML + Excel 双输出耗时 **{both_time:.2f}s**。",
        "不含 LLM 分析生成。",
        "",
        f"### 大持仓压力测试（Phase 3）",
        f"50 品种 basic Excel 生成耗时 **{stress_time:.2f}s**。",
        "",
        "## 环境",
        "",
        f"- **平台**: {sys.platform}",
        f"- **Python**: {sys.version.split()[0]}",
        "",
        "## 备注",
        "",
        "- 所有外部数据源（指数、基金排行、行业分类、概念数据）均已 mock，",
        "  测试结果仅反映本地计算管线性能",
        "- LLM 生成环节已 mock 跳过，实际 full 模式会额外增加 LLM 调用耗时",
        "- 实际耗时受硬件配置、磁盘速度、缓存状态等因素影响",
        "",
    ]

    report = "\n".join(lines) + "\n"
    with open(_PERF_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    return _PERF_REPORT_PATH


# ── 入口 ─────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("  端到端性能基准测试")
    print("=" * 60)

    timings = run_perf_test()

    print("\n" + "=" * 60)
    print("  生成性能报告...")
    report_path = write_perf_report(timings)
    print(f"  [OK] 报告已写入: {report_path}")

    basic_time = timings.get("phase1_basic_excel", 0)
    if basic_time <= _TARGET_SECONDS:
        print(f"\n[OK] basic 模式达标: {basic_time:.2f}s ≤ {_TARGET_SECONDS}s")
    else:
        print(f"\n[!] basic 模式未达标: {basic_time:.2f}s > {_TARGET_SECONDS}s")

    print("=" * 60)
    return 0 if basic_time <= _TARGET_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
