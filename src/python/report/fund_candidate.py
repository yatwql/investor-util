"""候选基金比较增强模块 —「基金业绩分析」章候选比较子表。

候选基金横向比较（收益 / 同类排名 / 评级 / 最大回撤 / 风格 / 与现有持仓重合度）。
开关 `report_submodules.candidate_compare`（**默认关**，未开启时维持既有输出），
候选基金代码来自 config `comparison_candidates`（6 位基金代码列表，≤10 只）。

数据降级：
  - 单候选获取失败 → 该行 `available=False` + `reason`，不阻塞其余行；
  - 候选无有效代码 / 开关关闭 → `build_candidate_compare_data` 返回 None 或
    `available=False`，渲染层不输出比较子表；
  - 候选超过 10 只 → 截断前 10，`exceed_limit=True`，渲染层提示；
  - 持仓报告期陈旧（候选自身或作为重合度基准的现有基金）→ 保留候选行并标注
    其报告期；基准侧的陈旧基金则剔除出重合度计算并如实列出，理由同「持仓
    重合度矩阵」——该列只是矩阵的一格，口径须一致。

与现有持仓重合度复用 `position_overlap.compute_overlap_matrix`（Jaccard 系数，
不重复实现）；风格判定复用 `fund_style_classify.classify_fund_style`（复用中心化分类）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.python.config import get_comparison_candidates, is_enable_candidate_compare
from src.python.core.code_utils import is_fund_holding
from src.python.fetcher.fund import fetch_fund_holdings_cached, fetch_fund_rankings_cached
from src.python.report.holdings_freshness import evaluate_report_period, fund_period_label
from src.python.report.position_overlap import compute_overlap_matrix
from src.python.report.fund_style_classify import classify_fund_style

logger = logging.getLogger("invest")

CANDIDATE_LIMIT = 10
_CODE_RE = re.compile(r"^\d{6}$")
_PERIOD_KEYS = ("近1月", "近3月", "近6月", "近1年")
_RISK_DRAWDOWN_KEY = "最大回撤"


def resolve_candidates(
    codes: list[str],
    limit: int = CANDIDATE_LIMIT,
) -> tuple[list[str], list[str], bool]:
    """校验并归一化候选基金代码列表。

    规则：仅保留 6 位数字代码；去重（保持首次出现顺序）；超过 limit 只时截断。

    Args:
        codes: 候选基金代码原始列表
        limit: 候选上限（默认 10）

    Returns:
        (valid, invalid, exceeded)：
          - valid: 合法且未超上限的 6 位代码列表
          - invalid: 被剔除的非法项（保持原样，供渲染提示）
          - exceeded: 是否因超上限被截断
    """
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        code = str(raw).strip()
        if not _CODE_RE.match(code):
            invalid.append(str(raw))
            continue
        if code in seen:
            continue
        seen.add(code)
        valid.append(code)
    exceeded = len(valid) > limit
    if exceeded:
        valid = valid[:limit]
        logger.warning("候选基金超过 %d 只上限，仅比较前 %d 只", limit, limit)
    if invalid:
        logger.warning("候选基金存在非法代码（忽略）: %s", ", ".join(invalid))
    return valid, invalid, exceeded


def _collect_existing_fund_baseline(
    holdings: list[Any] | None,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """收集现有持仓基金的持仓明细（候选重合度基准），并剔除报告期陈旧者。

    仅收集可成功获取的基金；获取失败/非基金持仓安全跳过（降级，不阻塞候选比较）。
    复用 `fetch_fund_holdings_cached` 会话缓存，与深度分析共享请求。

    陈旧者剔除与「持仓重合度矩阵」同口径——候选行这一列本就是重合度矩阵的一格，
    留着会让数年前的持仓结构以「与当前持仓的重合度」的名义呈现。

    Args:
        holdings: 原始持仓列表（Holding 模型或含 name/code/account 的对象）

    Returns:
        ({fund_code: [{name, code, ratio}, ...], ...}, [陈旧基金标注文本, ...])
    """
    result: dict[str, list[dict[str, Any]]] = {}
    stale_notes: list[str] = []
    if not holdings:
        return result, stale_notes
    for h in holdings:
        try:
            if not is_fund_holding(h.name, h.code, h.account):
                continue
        except AttributeError:
            continue
        try:
            fh = fetch_fund_holdings_cached(h.code)
        except Exception as e:  # 单基金获取失败降级
            logger.debug("候选重合度：现有基金 %s 持仓获取失败，跳过: %s", h.code, e)
            continue
        if not fh or not fh.get("holdings"):
            continue
        period_info = evaluate_report_period(fh.get("date"))
        if period_info.stale:
            stale_notes.append(fund_period_label(fh.get("name") or h.code, period_info))
            logger.warning(
                "候选重合度：剔除 %s —— 报告期 %s 已过 %d 个完整季度",
                fh.get("name") or h.code,
                period_info.period,
                period_info.quarters,
            )
            continue
        result[h.code] = fh["holdings"]
    return result, stale_notes


def _pct_str(val: float | None) -> str:
    """百分数显示（0.1523 → '15.23%'），None → '--'。"""
    if val is None:
        return "--"
    try:
        return f"{float(val) * 100:.2f}%"
    except (TypeError, ValueError):
        return "--"


def _build_candidate_row(
    code: str,
    existing_holdings: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """构建单个候选基金比较行。

    数据结构（Excel/HTML 共用）：
      {code, name, rating, syl_{1m,3m,6m,1y}, syl_{...}_raw, rank_text,
       max_drawdown, max_drawdown_raw, style, overlap_name, overlap_jaccard,
       overlap_jaccard_raw, report_period, report_stale, report_quarters,
       report_label, available, reason}

    单候选数据获取失败 → `available=False` + `reason`，其余行不受影响。

    Args:
        code: 6 位基金代码
        existing_holdings: 现有持仓基金持仓明细映射（用于重合度）

    Returns:
        候选比较行字典
    """
    row: dict[str, Any] = {
        "code": code,
        "name": code,
        "rating": "--",
        "rank_text": "--",
        "max_drawdown": "--",
        "max_drawdown_raw": None,
        "style": "--",
        "overlap_name": None,
        "overlap_jaccard": "--",
        "overlap_jaccard_raw": None,
        "report_period": "未知",
        "report_stale": False,
        "report_quarters": 0,
        "report_label": "",
        "available": False,
        "reason": "",
    }
    for p in _PERIOD_KEYS:
        row[f"syl_{p}"] = "--"
        row[f"syl_{p}_raw"] = None

    rank = fetch_fund_rankings_cached(code)
    if rank is None:
        row["reason"] = "rank_unavailable"
        return row
    row["name"] = rank.get("name") or code
    row["rating"] = rank.get("rating") or "--"

    ratings = rank.get("rankings") or {}
    for p in _PERIOD_KEYS:
        entry = ratings.get(p)
        raw = entry.get("return") if isinstance(entry, dict) else None
        if raw is None:
            continue
        try:
            fval = float(raw)
            row[f"syl_{p}_raw"] = fval
            row[f"syl_{p}"] = _pct_str(fval)
        except (TypeError, ValueError):
            continue

    rank_entry = ratings.get("同类排名") or {}
    rk = rank_entry.get("rank")
    tot = rank_entry.get("total")
    if rk not in (None, "--") and tot not in (None, "--"):
        row["rank_text"] = f"{rk}/{tot}"

    risk = rank.get("risk_analysis") or {}
    drawdown_raw = risk.get(_RISK_DRAWDOWN_KEY)
    if drawdown_raw is not None:
        try:
            # risk_analysis 为百分数数值（如 -18.5 表示 -18.5%），
            # 归一化为小数（-0.185）与 syl_*_raw 口径一致（Excel FMT_PERCENT 直接可用）
            dd = float(drawdown_raw) / 100.0
            row["max_drawdown_raw"] = dd
            row["max_drawdown"] = _pct_str(dd)
        except (TypeError, ValueError):
            pass

    # 风格 + 与现有持仓重合度。
    # 注意：fetch_fund_holdings_cached 返回 {"name", "holdings", "date"} 字典，
    # 下游风格判定与重合度计算要的是持仓**列表**，须先取 ["holdings"]。
    cand_fh = fetch_fund_holdings_cached(code) or {}
    cand_holdings = cand_fh.get("holdings") or []
    period_info = evaluate_report_period(cand_fh.get("date"))
    row["report_period"] = period_info.period
    row["report_stale"] = period_info.stale
    row["report_quarters"] = period_info.quarters
    row["report_label"] = fund_period_label(row["name"], period_info)
    if cand_holdings:
        try:
            style = classify_fund_style(code, cand_holdings)
            row["style"] = style.get("style") or "--"
        except Exception as e:  # 风格判定失败降级
            logger.debug("候选基金 %s 风格判定失败，跳过: %s", code, e)
        _fill_overlap(row, code, cand_holdings, existing_holdings)

    row["available"] = True
    return row


def _fill_overlap(
    row: dict[str, Any],
    code: str,
    cand_holdings: list[dict[str, Any]],
    existing_holdings: dict[str, list[dict[str, Any]]],
) -> None:
    """计算候选基金与现有持仓基金的最大重合度（复用 compute_overlap_matrix）。"""
    if not existing_holdings:
        return
    combined: dict[str, list[dict[str, Any]]] = dict(existing_holdings)
    combined[code] = cand_holdings
    if len(combined) < 2:
        return
    try:
        om = compute_overlap_matrix(combined)
    except Exception as e:
        logger.debug("候选基金 %s 重合度矩阵计算失败，跳过: %s", code, e)
        return
    names = om.get("fund_names") or {}
    for pr in om.get("pairs") or []:
        if code not in (pr.get("fund_a"), pr.get("fund_b")):
            continue
        other = pr["fund_b"] if pr["fund_a"] == code else pr["fund_a"]
        row["overlap_name"] = names.get(other) or other
        jaccard = pr.get("jaccard")
        if jaccard is not None:
            row["overlap_jaccard_raw"] = float(jaccard)
            row["overlap_jaccard"] = _pct_str(float(jaccard))
        break  # pairs 已按重合度降序，首个即最大重合


def build_candidate_compare_data(
    holdings: list[Any] | None,
    config: dict | None = None,
    cli_codes: list[str] | None = None,
) -> dict[str, Any] | None:
    """构建候选基金比较数据（「基金业绩分析」章比较子表渲染源）。

    Returns:
        None — 开关 `report_submodules.candidate_compare` 关闭（不渲染比较子表）；
        {"available": False, "reason": ..., "rows": []} — 开关开但无有效候选；
        {"available": True, "exceed_limit", "invalid", "rows", "stale_baseline_notes"} — 正常。
        `stale_baseline_notes` 列出因报告期陈旧而未进入重合度基准的现有持仓基金。
    """
    if not is_enable_candidate_compare(config):
        return None
    codes = list(get_comparison_candidates(config) or [])
    if cli_codes:
        codes.extend(cli_codes)
    valid, invalid, exceeded = resolve_candidates(codes)
    if not valid:
        return {
            "available": False,
            "reason": "no_valid_candidate",
            "exceed_limit": False,
            "invalid": invalid,
            "rows": [],
        }
    existing_holdings, stale_baseline_notes = _collect_existing_fund_baseline(holdings)
    rows = [_build_candidate_row(code, existing_holdings) for code in valid]
    return {
        "available": True,
        "exceed_limit": exceeded,
        "invalid": invalid,
        "rows": rows,
        "stale_baseline_notes": stale_baseline_notes,
    }
