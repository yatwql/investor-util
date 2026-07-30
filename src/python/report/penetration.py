"""资产穿透TOP10 模块 — 报告第 4 页。

将每只基金拆解为前 10 大持仓，合并相同底层标的，
再合并直接持有的股票，按市值降序取全仓前 10。

计算入口：:func:`compute_penetration_top10`
Excel 写入函数见 :mod:`src.python.report.penetration_sheet`。

基金类型分类规则（按优先级）：
  1. QDII            → 具体美股（季报数据）
  2. 债券基金         → 具体债券品种
  3. 场外指数联接     → 前 10 大成分股
  4. ETF             → 前 10 大成分股/黄金现货
  5. 主动权益基金     → 前 10 大持仓
  6. 直接持有股票     → 合并计算

输出列：
  排名 | 名称 | 代码 | 穿透市值 | 占比 | 板块 | 概念 | 预测EPS(当前年E) | 年均股息 | 来源明细
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from src.python.core.code_utils import (
    is_a_share_code,
    is_bond_related_by_name,
    is_convertible_bond_by_name,
    is_etf_by_name,
    is_exchange_fund_code,
    is_index_link_by_name,
    is_offsite_fund,
    is_otc_fund_by_name,
    is_qdii_extended,
)
from src.python.core.constants import PROJECT_ROOT
from src.python.fetcher.fund import fetch_fund_holdings_batch
from src.python.fetcher.fund_manager import fetch_fund_manager
from src.python.core.models import Holding
from src.python.report.market_value import DetailRow

logger = logging.getLogger("invest")

# ── 穿透分类常量 ───────────────────────────────────────────
# 公开导出的分类常量，方便测试模块引用

STOCK = "stock"  # 直接持有股票
QDII = "qdii"  # QDII 基金
ETF = "etf"  # 场内 ETF
INDEX_LINK = "index_link"  # 场外指数联接
BOND_FUND = "bond_fund"  # 债券基金
ACTIVE_EQUITY = "active_equity"  # 主动权益基金
IGNORE = "ignore"  # 忽略（现金/转债/Reits 等）

# 穿透基金类型 → 来源短标签
_FUND_TYPE_TAG: dict[str, str] = {
    QDII: "QDII",
    ETF: "ETF",
    INDEX_LINK: "联接",
    BOND_FUND: "债券",
    ACTIVE_EQUITY: "权益",
}


# ═══════════════════════════════════════════════════════════
#  分类判断
# ═══════════════════════════════════════════════════════════


def classify_penetration(h: Holding) -> str:
    """判断持仓在穿透深度分析中的角色。

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

    # 1) QDII 基金（最优先，含隐式海外基金识别）
    if is_qdii_extended(name):
        return QDII

    # 2) 债券基金
    if is_bond_related_by_name(name):
        return BOND_FUND

    # 3) 场外指数联接
    if is_index_link_by_name(name):
        return INDEX_LINK

    # 3.5) 可转债 → 忽略（转债为场内交易品种，但非基金/ETF/股票）
    if is_convertible_bond_by_name(name):
        return IGNORE

    # 4) 场内 ETF（名称含 ETF 或代码为场内基金/ETF 代码）
    if is_etf_by_name(name) or is_exchange_fund_code(code):
        return ETF

    # 5) 场外账户中的基金 → 主动权益基金（兜底）
    if is_offsite_fund(account):
        return ACTIVE_EQUITY

    # 6) 00 代码场外基金（名称匹配基金特征，与 A 股 00 前缀重叠区）
    if is_otc_fund_by_name(name, code):
        return ACTIVE_EQUITY

    # 7) A 股股票
    if is_a_share_code(code):
        return STOCK

    # 8) 其余忽略
    return IGNORE


def _fund_type_tag(ftype: str) -> str:
    """返回基金类型的短标签（用于来源明细列）。

    Args:
        ftype: 分类常量（QDII / ETF / INDEX_LINK / BOND_FUND / ACTIVE_EQUITY）

    Returns:
        短标签字符串，如 ``"QDII"`` / ``"ETF"`` / ``"联接"``
    """
    return _FUND_TYPE_TAG.get(ftype, "基金")


# ═══════════════════════════════════════════════════════════
#  板块分类
# ═══════════════════════════════════════════════════════════

# A 股板块关键词映射：按名称关键词匹配 → 板块
# ── 第 2 层：内置知识库 ────────────────────────────────

_SECTOR_KEYWORDS_FILE = os.path.join(PROJECT_ROOT, "data/knowledge/sector_keywords.json")


def _load_sector_keywords() -> dict[str, str]:
    """从 sector_keywords.json 加载行业关键词映射表。"""
    if not os.path.exists(_SECTOR_KEYWORDS_FILE):
        logger.warning("[穿透] 行业关键词文件 %s 不存在，使用空表", _SECTOR_KEYWORDS_FILE)
        return {}
    try:
        with open(_SECTOR_KEYWORDS_FILE, encoding="utf-8") as f:
            data: dict[str, str] = json.load(f)
        logger.debug("[穿透] 已加载 %d 条行业关键词", len(data))
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[穿透] 加载行业关键词文件失败: %s，使用空表", e)
        return {}


_SECTOR_KEYWORDS: dict[str, str] = _load_sector_keywords()


def classify_sector(name: str, _code: str = "") -> str:
    """根据证券名称和代码判断所属板块。

    Args:
        name: 证券名称
        code: 证券代码（备用，当前未使用）

    Returns:
        板块名称，如 "消费" / "科技" / "医药" / "新能源"，未知返回 "--"
    """
    if not name:
        return "--"
    clean = name.replace(" ", "").upper()
    for keyword, sector in _SECTOR_KEYWORDS.items():
        if keyword.upper() in clean:
            return sector
    return "--"


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


def _classify_and_group(
    holdings: list[Holding],
    details: list[DetailRow],
) -> tuple[dict[str, list[Holding]], list[Holding], list[Holding], dict[str, float]]:
    """按穿透类型分类持仓，分离基金/直接持股，构建市值映射。

    Note:
        detail_map 返回 ``{code: total_market_value}``，已按代码聚合所有账户市值。
        funds / direct_stocks 已按代码去重，避免同一基金/股票因跨账户多次归属。
    """
    classified: dict[str, list[Holding]] = {
        QDII: [],
        ETF: [],
        INDEX_LINK: [],
        BOND_FUND: [],
        ACTIVE_EQUITY: [],
        STOCK: [],
        IGNORE: [],
    }
    for h in holdings:
        cat = classify_penetration(h)
        (classified[cat] if cat in classified else classified[IGNORE]).append(h)

    fund_types = [QDII, ETF, INDEX_LINK, BOND_FUND, ACTIVE_EQUITY]
    funds: list[Holding] = []
    for ft in fund_types:
        funds.extend(classified[ft])
    direct_stocks = classified[STOCK]

    # ── detail_map：按代码聚合总市值（同一代码跨账户时累加） ──
    detail_map: dict[str, float] = {}
    for d in details:
        detail_map[d.code] = detail_map.get(d.code, 0.0) + d.market_value

    # ── funds / direct_stocks 按代码去重（跨账户时只处理一次） ──
    def _dedup_by_code(items: list[Holding]) -> list[Holding]:
        seen: set[str] = set()
        result: list[Holding] = []
        for item in items:
            if item.code not in seen:
                seen.add(item.code)
                result.append(item)
        return result

    funds = _dedup_by_code(funds)
    direct_stocks = _dedup_by_code(direct_stocks)

    return classified, funds, direct_stocks, detail_map


def _prefetch_manager_data(code: str) -> None:
    """预取基金经理数据并写入缓存（供 B2 变更监控使用）。

    与 fetch_fund_holdings 共用同一基金主页面 HTML，首次调用
    时发起 HTTP 请求，后续运行命中缓存（TTL=1天）零额外请求。
    此函数不阻塞穿透逻辑——经理数据不可用时仅打印调试日志。
    """
    try:
        manager = fetch_fund_manager(code)
        if manager is None:
            logger.debug("基金经理预取失败 [%s]（不阻塞穿透计算）", code)
    except Exception:
        logger.debug("基金经理预取异常 [%s]（不阻塞穿透计算）", code, exc_info=True)


def _merge_fund_layer(
    funds: list[Holding],
    detail_map: dict[str, float],
) -> tuple[dict[str, Any], float, int, list[dict[str, str]]]:
    """合并基金层穿透，返回 merged 字典 + 统计值。

    批量并行获取所有基金持仓。
    """
    merged: dict[str, Any] = {}
    unknown_mv = 0.0
    failed_count = 0
    failed_fund_details: list[dict[str, str]] = []

    # ── 批量并行获取所有基金持仓（替换原串行循环内 fetch_fund_holdings） ──
    fund_codes = [f.code for f in funds]
    holdings_batch = fetch_fund_holdings_batch(fund_codes)

    for fund in funds:
        fund_mv = detail_map.get(fund.code, 0.0)
        ftype = classify_penetration(fund)
        tag = _fund_type_tag(ftype)

        holdings_data = holdings_batch.get(fund.code)
        # 同页面顺带获取基金经理数据并缓存，供 B2 基金经理变更监控使用
        _prefetch_manager_data(fund.code)

        if holdings_data is None or not holdings_data.get("holdings"):
            unknown_mv += fund_mv
            failed_count += 1
            failed_fund_details.append({"name": fund.name, "code": fund.code})
            # 不把基金本身加入 merged — 穿透结果只反映可识别的底层标的
            # 基金全值计入 unknown_mv 并在页脚提示，不污染 TOP10
            continue

        # 过滤无效持仓比例（<= 0 或 > 100），一些基金（如黄金 ETF）的
        # 天天基金 API 可能返回垃圾数据（ratio 如 401%/399% 等）
        valid_items = [item for item in holdings_data["holdings"] if 0 < item.get("ratio", 0) <= 100]
        if not valid_items:
            unknown_mv += fund_mv
            failed_count += 1
            failed_fund_details.append({"name": fund.name, "code": fund.code})
            logger.info(
                "基金 %s(%s) 所有持仓比例无效（包含 %s），已排除",
                fund.name,
                fund.code,
                [h.get("ratio", 0) for h in holdings_data["holdings"]],
            )
            continue

        for item in valid_items:
            stock_name = item.get("name", "").strip()
            stock_code = item.get("code", "").strip()
            ratio = item.get("ratio", 0.0)
            if not stock_name:
                continue
            attributed_mv = fund_mv * (ratio / 100.0)
            norm_name = normalize_name(stock_name)
            sector = classify_sector(stock_name, stock_code)
            if norm_name not in merged:
                merged[norm_name] = {
                    "name": stock_name,
                    "codes": set(),
                    "mv": 0.0,
                    "funds": [],
                    "sector": sector,
                }
            if stock_code:
                merged[norm_name]["codes"].add(stock_code)
            merged[norm_name]["mv"] += attributed_mv
            merged[norm_name]["funds"].append(f"[{tag}] {fund.name}({fund.code})")

    return merged, unknown_mv, failed_count, failed_fund_details


def _merge_stock_layer(
    direct_stocks: list[Holding],
    detail_map: dict[str, float],
    merged: dict[str, Any],
) -> None:
    """将直接持股合并入 merged 字典（原地修改）。"""
    for stock in direct_stocks:
        stock_mv = detail_map.get(stock.code, 0.0)
        norm_name = normalize_name(stock.name)
        sector = classify_sector(stock.name, stock.code)
        if norm_name not in merged:
            merged[norm_name] = {
                "name": stock.name,
                "codes": {stock.code},
                "mv": 0.0,
                "funds": [],
                "sector": sector,
            }
        else:
            merged[norm_name]["codes"].add(stock.code)
        merged[norm_name]["mv"] += stock_mv
        merged[norm_name]["funds"].append("直接持有")


def _enrich_with_industry_api(merged: dict[str, Any]) -> tuple[bool, str]:
    """用 API 行业数据补充板块分类和概念（原地修改）。

    Returns:
        (success, failure_type)
        - success=True 表示 API 获取成功（可能有部分数据），或无需调用 API（全为非 A 股）
        - success=False 时 failure_type 为 ``"unreachable"``（连接失败）、
          ``"empty"``（A 股代码存在但 API 返回空数据）
    """
    try:
        all_codes: list[str] = []
        for info in merged.values():
            all_codes.extend(info.get("codes") or [])
        if not all_codes:
            return True, "no_a_share"
        a_share_codes = [c for c in set(all_codes) if is_a_share_code(c)]
        if not a_share_codes:
            return True, "no_a_share"
        from src.python.fetcher.industry import batch_fetch_industry_data as batch_ind

        ind_data = batch_ind(a_share_codes)
        if ind_data:
            return True, _apply_industry_data(merged, ind_data)
        logger.warning("[penetration] 行业分类 API 返回空数据（非关键）")
        return False, "empty"
    except Exception:
        logger.warning("[penetration] 行业分类 API 获取失败（非关键）", exc_info=True)
        return False, "unreachable"


def _apply_industry_data(merged: dict[str, Any], ind_data: dict[str, dict]) -> str:
    """将行业分类数据应用到 merged 字典（原地修改）。

    Returns:
        空字符串表示成功，否则返回失败原因。
    """
    for info in merged.values():
        for code in info.get("codes") or []:
            if code in ind_data:
                id_rec = ind_data[code]
                if id_rec.get("industry"):
                    info["sector_api"] = id_rec["industry"]
                    info["sector"] = id_rec["industry"]
                if id_rec.get("concepts"):
                    info["concepts"] = id_rec["concepts"]
                break
    return ""


def _build_penetration_result(
    merged: dict[str, Any],
    classified: dict[str, list[Holding]],
    funds: list[Holding],
    direct_stocks: list[Holding],
    unknown_mv: float,
    failed_count: int,
    failed_fund_details: list[dict[str, str]],
) -> dict[str, Any]:
    """从合并数据生成穿透 TOP10 返回字典。"""
    total_mv = sum(v["mv"] for v in merged.values())
    sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)

    fund_breakdown = " + ".join(
        f"{cl}{len(classified[c])}"
        for c, cl in [
            (QDII, "QDII"),
            (ETF, "ETF"),
            (INDEX_LINK, "联接"),
            (BOND_FUND, "债券"),
            (ACTIVE_EQUITY, "主动"),
        ]
        if classified[c]
    )

    top10_list = []
    for rank, (_, info) in enumerate(sorted_items[:10], 1):
        ratio = info["mv"] / total_mv * 100 if total_mv > 0 else 0.0
        top10_list.append(
            {
                "rank": rank,
                "name": info["name"],
                "codes": sorted(info["codes"]) if info["codes"] else [],
                "mv": round(info["mv"], 2),
                "ratio_pct": round(ratio, 2),
                "sector": info.get("sector", "--"),
                "concepts": (info.get("concepts") or [])[:3],
                "sources": sorted(set(info["funds"])),
            }
        )

    if not top10_list:
        logger.warning("[penetration] 天天基金持仓解析结果为空，穿透表不可用")

    top10_coverage = sum(v["mv"] for _, v in sorted_items[:10]) / total_mv * 100 if total_mv > 0 else 0.0

    return {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_funds": len(funds),
            "total_stocks": len(direct_stocks),
            "fund_breakdown": fund_breakdown,
            "merged_count": len(merged),
            "total_mv": round(total_mv, 2),
            "top10_coverage_pct": round(top10_coverage, 1),
            "unknown_mv": round(unknown_mv, 2),
            "failed_funds": failed_count,
            "failed_fund_details": failed_fund_details,
        },
        "top10": top10_list,
    }


def compute_penetration_top10(
    holdings: list[Holding],
    details: list[DetailRow],
) -> dict[str, Any]:
    """计算资产穿透TOP10，返回结构化数据。

    Excel 写入见 :func:`src.python.report.penetration_sheet.write_penetration_sheet`。

    性能优化：基金持仓批量获取与已知 A 股行业分类数据并行预取，
    将串行 IO 链（3s + 8s）重叠为并行 ~8s，节约 ~3-5s。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        {
            "update_time": "...",
            "summary": {...},
            "top10": [...],
        }
    """
    classified, funds, direct_stocks, detail_map = _classify_and_group(holdings, details)

    # ── Phase 1: 并行预取 ──
    # 已知 A 股代码的行业分类与基金持仓批量获取同时进行
    from concurrent.futures import ThreadPoolExecutor

    known_a_codes: set[str] = set()
    for s in direct_stocks:
        if is_a_share_code(s.code):
            known_a_codes.add(s.code)
    for code in detail_map:
        if is_a_share_code(code):
            known_a_codes.add(code)

    pen_exec = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pen_parallel")
    try:
        fund_future = pen_exec.submit(_merge_fund_layer, funds, detail_map)
        ind_future: Any = None
        if known_a_codes:
            from src.python.fetcher.industry import batch_fetch_industry_data as batch_ind

            ind_future = pen_exec.submit(batch_ind, list(known_a_codes))

        # 等待基金持仓获取完成
        merged, unknown_mv, failed_count, failed_fund_details = fund_future.result()
    finally:
        pen_exec.shutdown(wait=False)

    # ── Phase 2: 合并直接持股 ──
    _merge_stock_layer(direct_stocks, detail_map, merged)

    # ── Phase 3: 行业分类（合并预取 + 补充剩余） ──
    industry_success = True
    industry_failure_type = ""

    all_codes: set[str] = set()
    for info in merged.values():
        all_codes.update(info.get("codes") or [])
    a_share_codes = {c for c in all_codes if is_a_share_code(c)}

    if not a_share_codes:
        industry_failure_type = "no_a_share"
    else:
        prefetched: dict[str, dict] = {}
        if ind_future is not None:
            try:
                prefetched = ind_future.result() or {}
            except Exception:
                logger.debug("[penetration] 行业预取异常，回退按需获取", exc_info=True)

        if prefetched:
            _apply_industry_data(merged, prefetched)

        # 补取基金持仓中出现的、预取未覆盖的新代码
        remaining = a_share_codes - set(prefetched.keys())
        if remaining:
            from src.python.fetcher.industry import batch_fetch_industry_data as batch_ind

            remaining_data = batch_ind(list(remaining))
            if remaining_data:
                _apply_industry_data(merged, remaining_data)

        # 没有任何行业数据被获取
        if not prefetched and not remaining and a_share_codes:
            logger.warning("[penetration] 行业分类数据为空（非关键）")
            industry_success = False
            industry_failure_type = "empty"

    result = _build_penetration_result(
        merged,
        classified,
        funds,
        direct_stocks,
        unknown_mv,
        failed_count,
        failed_fund_details,
    )
    result["industry_success"] = industry_success
    if not industry_success:
        result["industry_failure_type"] = industry_failure_type
    return result
