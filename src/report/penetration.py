"""资产穿透 TOP10 模块 — 报告第 4 页。

将每只基金拆解为前 10 大持仓，合并相同底层标的，
再合并直接持有的股票，按市值降序取全仓前 10。

基金类型分类规则（按优先级）：
  1. QDII            → 具体美股（季报数据）
  2. 债券基金         → 具体债券品种
  3. 场外指数联接     → 前 10 大成分股
  4. ETF             → 前 10 大成分股/黄金现货
  5. 主动权益基金     → 前 10 大持仓
  6. 直接持有股票     → 合并计算

输出列：
  排名 | 名称 | 代码 | 穿透市值 | 占比 | 来源明细
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from openpyxl.worksheet.worksheet import Worksheet

from src.fetcher import fetch_fund_holdings
from src.models import Holding
from src.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.report.market_value import DetailRow
from src.report.styles import FMT_MONEY, FMT_PERCENT

logger = logging.getLogger("invest")

_NCOLS = 6
_HEADERS = [
    "排名", "名称", "代码", "穿透市值", "占比", "来源明细",
]

# ── 穿透分类常量 ───────────────────────────────────────────
# 公开导出的分类常量，方便测试模块引用

STOCK = "stock"                # 直接持有股票
QDII = "qdii"                  # QDII 基金
ETF = "etf"                    # 场内 ETF
INDEX_LINK = "index_link"      # 场外指数联接
BOND_FUND = "bond_fund"        # 债券基金
ACTIVE_EQUITY = "active_equity"  # 主动权益基金
IGNORE = "ignore"              # 忽略（现金/转债/Reits 等）

# 穿透基金类型 → 来源短标签
_FUND_TYPE_TAG: dict[str, str] = {
    QDII: "QDII",
    ETF: "ETF",
    INDEX_LINK: "联接",
    BOND_FUND: "债券",
    ACTIVE_EQUITY: "权益",
}

# 场外账户关键词
_FUND_ACCOUNT_KW = ("基金", "支付宝", "微信", "银行")


# ═══════════════════════════════════════════════════════════
#  分类判断
# ═══════════════════════════════════════════════════════════


def classify_penetration(h: Holding) -> str:
    """判断持仓在穿透分析中的角色。

    优先级（高 → 低）：
      1. QDII            — 名称含 ``QDII``
      2. 债券基金         — 名称含债类关键词（纯债/短债/债券等）
      3. 场外指数联接     — 名称含联接 / ETF联接 / 链接
      4. ETF             — 名称含 ``ETF`` 或代码以 ``5`` 开头
      5. 主动权益基金     — 场外账户（基金/支付宝/微信/银行）中的基金
      6. 直接持有股票     — 代码以 ``6`` / ``0`` / ``3`` 开头
      7. ``"ignore"``    — 其余（现金/转债/Reits 等）

    Args:
        h: 持仓记录

    Returns:
        分类常量之一（``STOCK`` / ``QDII`` / ``ETF`` / ``INDEX_LINK`` /
        ``BOND_FUND`` / ``ACTIVE_EQUITY`` / ``IGNORE``）
    """
    name = h.name.strip()
    code = h.code.strip()
    account = h.account.strip()

    # 1) QDII 基金（最优先，名称明确）
    if "QDII" in name.upper():
        return QDII

    # 2) 债券基金
    if _is_bond_fund(name):
        return BOND_FUND

    # 3) 场外指数联接
    if _is_index_link(name):
        return INDEX_LINK

    # 4) 场内 ETF（名称含 ETF 或代码 5 开头）
    if "ETF" in name.upper() or code.startswith("5"):
        return ETF

    # 5) 场外账户中的基金 → 主动权益基金（兜底）
    if any(kw in account for kw in _FUND_ACCOUNT_KW):
        return ACTIVE_EQUITY

    # 6) A 股股票
    if code.startswith(("6", "0", "3")):
        return STOCK

    # 7) 其余忽略
    return IGNORE


def _is_bond_fund(name: str) -> bool:
    """判断名称是否为债券基金。

    识别关键词：纯债 / 短债 / 中短债 / 利率债 / 信用债 / 债券

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配债券基金特征
    """
    kw = ("纯债", "短债", "中短债", "利率债", "信用债", "债券")
    return any(k in name for k in kw)


def _is_index_link(name: str) -> bool:
    """判断是否为场外指数联接基金。

    识别关键词：ETF联接 / ETF链接 / 联接 / 链接（单独出现时也视为联接基金）。

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配指数联接特征
    """
    clean = name.replace(" ", "").upper()
    if "ETF联接" in clean or "ETF链接" in clean:
        return True
    return any(kw in name for kw in ("联接", "链接"))


def _fund_type_tag(ftype: str) -> str:
    """返回基金类型的短标签（用于来源明细列）。

    Args:
        ftype: 分类常量（QDII / ETF / INDEX_LINK / BOND_FUND / ACTIVE_EQUITY）

    Returns:
        短标签字符串，如 ``"QDII"`` / ``"ETF"`` / ``"联接"``
    """
    return _FUND_TYPE_TAG.get(ftype, "基金")


# ═══════════════════════════════════════════════════════════
#  名称归一化
# ═══════════════════════════════════════════════════════════


def normalize_name(name: str) -> str:
    """归一化证券名称，用于合并相同底层标的。

    处理：去除首尾空格、全角空格、\xa0 不间断空格。

    Args:
        name: 原始名称

    Returns:
        归一化后的名称
    """
    s = name.strip()
    s = s.replace("　", " ").replace("\xa0", " ")
    return s


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════


def compute_penetration_top10(
    holdings: List[Holding],
    details: List[DetailRow],
) -> dict[str, Any]:
    """计算资产穿透 TOP10，返回结构化数据（不写 Excel）。

    与 :func:`write_penetration_sheet` 共用同一套合并/排序逻辑，
    但返回可序列化的 Python 字典，适合缓存为 JSON。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        {
            "update_time": "2026-06-27 14:30:00",
            "summary": {
                "total_funds": 5,
                "total_stocks": 3,
                "fund_breakdown": "QDII1 + ETF2 + 联接1 + 债券1 + 主动0",
                "merged_count": 12,
                "total_mv": 123456.78,
                "top10_coverage_pct": 85.3,
                "unknown_mv": 5000.0,
                "failed_funds": 1,
            },
            "top10": [
                {
                    "rank": 1, "name": "贵州茅台",
                    "codes": ["600519"], "mv": 50000.0,
                    "ratio_pct": 15.2, "sources": ["[ETF] 电池ETF(561910)"]
                },
                ...
            ],
        }
    """
    # ── 1) 精细化分类 ──────────────────────────────────────
    classified: dict[str, list[Holding]] = {
        QDII: [], ETF: [], INDEX_LINK: [],
        BOND_FUND: [], ACTIVE_EQUITY: [], STOCK: [], IGNORE: [],
    }
    for h in holdings:
        cat = classify_penetration(h)
        if cat in classified:
            classified[cat].append(h)
        else:
            classified[IGNORE].append(h)

    fund_types = [QDII, ETF, INDEX_LINK, BOND_FUND, ACTIVE_EQUITY]
    funds: list[Holding] = []
    for ft in fund_types:
        funds.extend(classified[ft])
    direct_stocks = classified[STOCK]

    detail_map: dict[str, DetailRow] = {d.code: d for d in details}

    # ── 2) 合并底层标的 ──────────────────────────────────────
    merged: dict[str, dict[str, Any]] = {}
    unknown_mv = 0.0
    failed_count = 0

    for fund in funds:
        detail = detail_map.get(fund.code)
        fund_mv = detail.market_value if detail else 0.0
        ftype = classify_penetration(fund)
        tag = _fund_type_tag(ftype)

        holdings_data = fetch_fund_holdings(fund.code)
        if holdings_data is None or not holdings_data.get("holdings"):
            unknown_mv += fund_mv
            failed_count += 1
            continue

        for item in holdings_data["holdings"]:
            stock_name = item.get("name", "").strip()
            stock_code = item.get("code", "").strip()
            ratio = item.get("ratio", 0.0)
            if not stock_name:
                continue

            attributed_mv = fund_mv * (ratio / 100.0) if ratio > 0 else 0.0
            norm_name = normalize_name(stock_name)

            if norm_name not in merged:
                merged[norm_name] = {
                    "name": stock_name, "codes": set(),
                    "mv": 0.0, "funds": [],
                }
            if stock_code:
                merged[norm_name]["codes"].add(stock_code)
            merged[norm_name]["mv"] += attributed_mv
            merged[norm_name]["funds"].append(f"[{tag}] {fund.name}({fund.code})")

    # ── 3) 合并直接持股 ──────────────────────────────────────
    for stock in direct_stocks:
        detail = detail_map.get(stock.code)
        stock_mv = detail.market_value if detail else 0.0
        norm_name = normalize_name(stock.name)

        if norm_name not in merged:
            merged[norm_name] = {
                "name": stock.name, "codes": {stock.code},
                "mv": 0.0, "funds": [],
            }
        else:
            merged[norm_name]["codes"].add(stock.code)
        merged[norm_name]["mv"] += stock_mv
        merged[norm_name]["funds"].append("直接持有")

    # ── 4) 生成返回数据 ──────────────────────────────────
    total_mv = sum(v["mv"] for v in merged.values())
    sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)

    fund_breakdown = " + ".join(
        f"{cat_label}{len(classified[c])}"
        for c, cat_label in [
            (QDII, "QDII"), (ETF, "ETF"), (INDEX_LINK, "联接"),
            (BOND_FUND, "债券"), (ACTIVE_EQUITY, "主动"),
        ]
        if classified[c]
    )

    top10_list = []
    for rank, (norm_name, info) in enumerate(sorted_items[:10], 1):
        ratio = info["mv"] / total_mv * 100 if total_mv > 0 else 0.0
        top10_list.append({
            "rank": rank,
            "name": info["name"],
            "codes": sorted(info["codes"]) if info["codes"] else [],
            "mv": round(info["mv"], 2),
            "ratio_pct": round(ratio, 2),
            "sources": sorted(set(info["funds"])),
        })

    top10_coverage = (
        sum(v["mv"] for _, v in sorted_items[:10]) / total_mv * 100
        if total_mv > 0 else 0.0
    )

    now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "update_time": now,
        "summary": {
            "total_funds": len(funds),
            "total_stocks": len(direct_stocks),
            "fund_breakdown": fund_breakdown,
            "merged_count": len(merged),
            "total_mv": round(total_mv, 2),
            "top10_coverage_pct": round(top10_coverage, 1),
            "unknown_mv": round(unknown_mv, 2),
            "failed_funds": failed_count,
        },
        "top10": top10_list,
    }


# ═══════════════════════════════════════════════════════════
#  Excel 写入（复用 compute_penetration_top10）
# ═══════════════════════════════════════════════════════════


def write_penetration_sheet(
    ws: Worksheet,
    holdings: List[Holding],
    details: List[DetailRow],
) -> None:
    """写入资产穿透 TOP10 页签。

    用 :func:`compute_penetration_top10` 计算数据后写入 Excel 行。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
    """
    ws.title = "资产穿透TOP10"
    row = write_title_row(ws, 1, "资产穿透 TOP 10", _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    result = compute_penetration_top10(holdings, details)

    if not result["top10"]:
        write_data_row(ws, row, ["暂无穿透数据"])
        freeze_header(ws, 2)
        auto_width(ws)
        logger.warning("穿透分析无数据")
        return

    summary = result["summary"]

    for entry in result["top10"]:
        vals = [
            entry["rank"],
            entry["name"],
            ", ".join(entry["codes"]) if entry["codes"] else "--",
            entry["mv"],
            entry["ratio_pct"] / 100.0,
            "; ".join(entry["sources"]),
        ]
        write_data_row(ws, row, vals, _num_formats())
        row += 1

    # 备注 & 统计信息
    row += 1
    if summary["unknown_mv"] > 0:
        write_data_row(ws, row,
                       [f"* {summary['total_funds']} 只基金中，有 "
                        f"{summary['failed_funds']} 只无法获取穿透数据，"
                        f"合计市值 {summary['unknown_mv']:,.2f} 元未计入穿透 TOP10"],
                       [])
        row += 1

    info_line = (
        f"基金 {summary['total_funds']} 只（{summary['fund_breakdown']}）"
        f" + 直接持股 {summary['total_stocks']} 只 → "
        f"穿透合并 {summary['merged_count']} 个标的，"
        f"TOP10 覆盖 {summary['top10_coverage_pct']:.1f}%"
    )
    write_data_row(ws, row, [info_line], [])

    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=40)

    logger.info("资产穿透 TOP10 页签写入完成，合并 %d 个标的",
                summary["merged_count"])


# ═══════════════════════════════════════════════════════════
#  内部辅助
# ═══════════════════════════════════════════════════════════


def _num_formats() -> list[str]:
    """每列的 Excel 数字格式。"""
    return [
        "",           # 1  排名
        "",           # 2  名称
        "",           # 3  代码
        FMT_MONEY,    # 4  穿透市值
        FMT_PERCENT,  # 5  占比
        "",           # 6  来源明细
    ]
