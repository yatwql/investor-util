"""数据源可用性矩阵 — 统一聚合所有数据源状态供 Excel/HTML 渲染。

从 DegradationTracker 采集各数据源最新状态，按类别聚合为
统一的矩阵结构，消除各模块独立状态碎片。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.report.data_status import get_tracker

logger = logging.getLogger("invest")

# ── 数据源类别定义 ──────────────────────────────────────
# 每条记录包含：类别键、中文名称、source_key 前缀列表

_SOURCE_CATEGORIES: list[dict[str, Any]] = [
    {"key": "price", "name": "行情数据", "prefixes": ["price_"]},
    {"key": "fund_rank", "name": "基金排名", "prefixes": ["fund_rank_", "perf_rank"]},
    {"key": "fund_hold", "name": "基金持仓", "prefixes": ["fund_hold_"]},
    {"key": "industry", "name": "行业分类", "prefixes": ["industry_", "penetration_industry"]},
    {"key": "index", "name": "指数数据", "prefixes": ["index_a", "index_us", "index_history_"]},
    {"key": "profit_forecast", "name": "盈利预测", "prefixes": ["penetration_profit_forecast"]},
    {"key": "dividend", "name": "分红数据", "prefixes": ["penetration_dividend"]},
    {"key": "fund_flow", "name": "资金流向", "prefixes": ["ff_"]},
    {"key": "financial_report", "name": "财报全文", "prefixes": ["report_datasink_"]},
    {"key": "financial_indicator", "name": "财务指标", "prefixes": ["fin_indicator_"]},
]


def _match_category(source_key: str) -> str | None:
    """返回 source_key 所属的类别 key，None 表示无匹配。"""
    for cat in _SOURCE_CATEGORIES:
        for prefix in cat["prefixes"]:
            if source_key == prefix or source_key.startswith(prefix):
                return cat["key"]
    return None


def _failure_entry(source_key: str, event: dict[str, Any]) -> str:
    """把降级事件渲染成 ``数据源: 原因`` 的可读条目。

    优先用事件携带的人类可读原因（``detail.message``，由链路诊断传入），
    无原因时回落到失败类型短标识，保证既有输出逐字不变。
    """
    detail = event.get("detail") or {}
    reason = detail.get("message") or event.get("failure_type", "unknown")
    return f"{source_key}: {reason}"


def build_data_source_matrix() -> list[dict[str, Any]]:
    """构建数据源可用性矩阵。

    从 DegradationTracker 事件日志聚合每条 source_key 的最新状态，
    按类别（行情/基金/行业等）归类后计算整体健康度。

    Returns:
        矩阵行列表，每行含：
            key / name / status / detail / total / ok / degraded / failed
        status 取值 "ok" / "degraded" / "failed"
    """
    events = get_tracker().get_log()
    if not events:
        return []

    # 1) 按 source_key 取最新事件
    latest: dict[str, dict[str, Any]] = {}
    for ev in events:
        key = ev["source_key"]
        ts = ev["timestamp"]
        if key not in latest or ts > latest[key]["timestamp"]:
            latest[key] = ev

    # 2) 初始化类别容器
    cat_data: dict[str, dict[str, Any]] = {}
    for cat in _SOURCE_CATEGORIES:
        cat_data[cat["key"]] = {
            "key": cat["key"],
            "name": cat["name"],
            "total": 0,
            "ok": 0,
            "degraded": 0,
            "failed": 0,
            "sample_failures": [],  # 失败项（source_key + 可读原因）
            "degraded_list": [],  # 降级项列表（source_key + 可读原因）
        }

    unmatched: list[str] = []

    # 3) 归入类别
    for src_key, ev in latest.items():
        cat_key = _match_category(src_key)
        if cat_key is None:
            unmatched.append(src_key)
            continue
        cd = cat_data[cat_key]
        cd["total"] += 1
        if ev["success"]:
            cd["ok"] += 1
        elif ev["degraded"]:
            cd["degraded"] += 1
            cd["degraded_list"].append(_failure_entry(src_key, ev))
        else:
            cd["failed"] += 1
            cd["sample_failures"].append(_failure_entry(src_key, ev))

    # 4) 计算综合状态并生成输出行
    matrix: list[dict[str, Any]] = []
    for cat in _SOURCE_CATEGORIES:
        cd = cat_data[cat["key"]]
        if cd["total"] == 0:
            continue
        if cd["failed"] == 0 and cd["degraded"] == 0:
            status = "ok"
        elif cd["failed"] > 0 and cd["ok"] == 0:
            status = "failed"
        else:
            status = "degraded"

        detail_parts: list[str] = []
        if cd["ok"] > 0:
            detail_parts.append(f"{cd['ok']} 正常")
        if cd["degraded"] > 0:
            detail_parts.append(f"{cd['degraded']} 降级")
        if cd["failed"] > 0:
            detail_parts.append(f"{cd['failed']} 失败")

        row: dict[str, Any] = {
            "key": cd["key"],
            "name": cd["name"],
            "status": status,
            "detail": "，".join(detail_parts) if detail_parts else "无数据",
            "total": cd["total"],
            "ok": cd["ok"],
            "degraded": cd["degraded"],
            "failed": cd["failed"],
            "sample_failures": cd["sample_failures"],
            "degraded_list": cd["degraded_list"],
        }
        matrix.append(row)

    # 5) 追加未归类项（如有）
    if unmatched:
        matrix.append(
            {
                "key": "_unmatched",
                "name": "其他数据源",
                "status": "ok",
                "detail": f"{len(unmatched)} 个未归类源（均正常）",
                "total": len(unmatched),
                "ok": len(unmatched),
                "degraded": 0,
                "failed": 0,
                "sample_failures": [],
            }
        )

    return matrix


# ═══════════════════════════════════════════════════════════
#  数据源说明表（实际使用清单：用途 / 计费 / 凭据要求）
# ═══════════════════════════════════════════════════════════

#: 类别前缀唯一来源（与 _SOURCE_CATEGORIES 同源——说明表不再各写一份 prefixes）
_CATEGORY_PREFIXES: dict[str, list[str]] = {c["key"]: list(c["prefixes"]) for c in _SOURCE_CATEGORIES}

#: 免费源的计费描述；需 key 的源由 providers.datasink.billing_description 按套餐动态给
_FREE_BILLING = "免费"

# 每行描述一个数据类别实际走的数据源链路、用途与凭据要求。
# 「本次是否使用」的前缀取自 _CATEGORY_PREFIXES；计费文案的数字同源于 provider 层套餐表。
_SOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "price",
        "category": "行情数据",
        "provider": "腾讯财经 / 新浪财经（场内）；东方财富 / 天天基金（场外净值）",
        "usage": "持仓实时价与场外基金净值",
        "auth": "无需",
    },
    {
        "id": "fund_rank",
        "category": "基金排名",
        "provider": "天天基金",
        "usage": "基金同类排名与区间收益",
        "auth": "无需",
    },
    {
        "id": "fund_hold",
        "category": "基金持仓",
        "provider": "天天基金（基金主页面 + 季报 API）",
        "usage": "基金底层持仓（含联接基金穿透目标 ETF）",
        "auth": "无需",
    },
    {
        "id": "industry",
        "category": "行业分类",
        "provider": "东方财富 push2 → 东方财富 REST",
        "usage": "个股行业分类与概念板块",
        "auth": "无需",
    },
    {
        "id": "index",
        "category": "指数数据",
        "provider": "腾讯财经 / 新浪财经（A 股）；新浪财经 / 腾讯财经（美股）",
        "usage": "A 股与美股指数行情",
        "auth": "无需",
    },
    {
        "id": "profit_forecast",
        "category": "盈利预测",
        "provider": "akshare",
        "usage": "机构盈利预测（穿透 TOP10 增强）",
        "auth": "无需",
    },
    {
        "id": "dividend",
        "category": "分红数据",
        "provider": "akshare",
        "usage": "持仓股票历史分红",
        "auth": "无需",
    },
    {
        "id": "fund_flow",
        "category": "资金流向",
        "provider": "akshare",
        "usage": "行业资金流向（LLM 分析上下文）",
        "auth": "无需",
    },
    {
        "id": "financial_report",
        "category": "财报全文",
        "provider": "DataSinking（api.datasink.ing）",
        "usage": "个股财报章节全文摘要，兼作财务指标解析的备用支路（仅 A 股）",
        "auth": "需 key",
        "credential_source_id": "datasink",
        "note": "免费 key 需自备（datasink.ing）；需开启 report_submodules.financial_report_digest 或 financial_indicator 才会取用",
    },
    {
        "id": "financial_indicator",
        "category": "财务指标",
        "provider": "akshare 结构化财务指标（主源）；DataSinking 财报章节解析（备用支路）",
        "usage": "持仓 A 股基本面（指标列 / 质量档 / 年度趋势 / 真实 PE·PB 分位）",
        "auth": "无需（主源）",
        "note": "备用支路需 DataSinking key；两者均需开启 report_submodules.financial_indicator 或 valuation_percentile",
    },
]


def _datasink_plan() -> str:
    """读 config.json 的 `datasink.plan`（缺失或异常回退 free）。"""
    try:
        from src.python.config import get_config

        plan = (get_config().get("datasink") or {}).get("plan")
        return str(plan).strip().lower() if plan else "free"
    except Exception:
        return "free"


def build_data_source_catalog() -> list[dict[str, Any]]:
    """数据源说明表：描述实际使用的数据源、用途、计费与凭据要求。

    与 :func:`build_data_source_matrix` 互补：矩阵答「本次哪类源健康度如何」，
    本表答「这类数据实际走哪些源、是否付费、是否需 key、本次有没有用」。

    Returns:
        每行含 ``id / category / provider / usage / billing / auth / used / note``。
        ``used`` 为 True 表示本次运行**取得过该类别数据**（含命中缓存）——由各类别的
        取数链路以 ``report.data_status.mark_data_used`` 标记（**只记成功、不记降级**，
        故「未使用」仅说明本次未取到该类数据，不等于该源故障）。
        需 key 的类别（如财报全文）的 ``auth`` 附加就绪状态。
    """
    from src.python.core.datasource_credential import credential_readiness, credential_ready_enabled

    observed = {ev["source_key"] for ev in get_tracker().get_log()}
    readiness: dict[str, dict[str, Any]] = {}
    if credential_ready_enabled():
        try:
            readiness = {row["source_id"]: row for row in credential_readiness()}
        except Exception:
            logger.debug("[matrix] 凭据就绪矩阵读取失败，说明表不附就绪态")
    plan = _datasink_plan()

    rows: list[dict[str, Any]] = []
    for cat in _SOURCE_CATALOG:
        prefixes = _CATEGORY_PREFIXES.get(cat["id"], [])
        used = any(any(key == p or key.startswith(p) for p in prefixes) for key in observed)
        cred_id = cat.get("credential_source_id")
        billing = _FREE_BILLING
        auth = cat["auth"]
        if cred_id:
            from src.python.providers import datasink as _datasink

            billing = _datasink.billing_description(plan)
            row = readiness.get(cred_id)
            if row is not None:
                auth = f"需 key（{'已就绪' if row.get('ready') else '未配置'}）"
        rows.append(
            {
                "id": cat["id"],
                "category": cat["category"],
                "provider": cat["provider"],
                "usage": cat["usage"],
                "billing": billing,
                "auth": auth,
                "used": used,
                "note": cat.get("note", ""),
            }
        )
    return rows
