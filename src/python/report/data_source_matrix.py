"""数据源可用性矩阵 — 统一聚合所有数据源状态供 Excel/HTML 渲染。

从 DegradationTracker 采集各数据源最新状态，按类别聚合为
统一的矩阵结构，消除各模块独立状态碎片；并叠加 provider 级
命中归属（``data_status.mark_provider_used``），使矩阵既答
「这类数据健康吗」、也答「本次这类数据走的是哪个源」。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.report.data_status import get_provider_usage, get_tracker

logger = logging.getLogger("invest")

#: 矩阵表格列头（Excel 两处渲染共用；HTML 模板同序硬编码）
#: 「命中源」= 本次该类别实际由哪个 provider 服务（命中缓存时无归属，显示「—」）
MATRIX_HEADERS: list[str] = ["数据源", "状态", "命中源", "详情", "成功", "失败/降级"]

#: 有意不进矩阵的链路数据类型：其消费方不属矩阵任何类别（如无风险利率仅供市场温度合成），
#: provider 归属对其无展示落点。新增此类须在此登记，使「未归属」成为显式决策而非遗漏
#: （由 test_data_source_matrix.py 的不变式用例强制）。
UNMAPPED_CHAIN_DATA_TYPES: frozenset[str] = frozenset({"bond_yield"})

# ── 数据源类别定义 ──────────────────────────────────────
# 每条记录包含：类别键、中文名称、source_key 前缀列表、该类别对应的**链路数据类型**
#
#   prefixes  —— 类别级事件（降级 tracker 的 source_key）归属，决定「本次使用 / 健康度」
#   data_types —— provider 级归属（`data_status.mark_provider_used`）的归属，决定
#                「命中源」列（如 ``price_stock`` 类数据由腾讯还是同花顺服务）
#
# 两套归属分开声明：类别级事件来自各域取数函数（键里只有代码，无 provider），
# provider 级归属来自链路成功回调（键是链路 data_type）。二者的键形态不同，
# 且存在只有一方的情形——历史日 K 无类别级 tracker 事件（只登记缓存键），
# 故其行由 provider 归属单独成立。

_SOURCE_CATEGORIES: list[dict[str, Any]] = [
    {
        "key": "price",
        "name": "行情数据",
        "prefixes": ["price_"],
        "data_types": ["price_stock", "price_fund_otc", "price"],
    },
    {"key": "fund_rank", "name": "基金排名", "prefixes": ["fund_rank_", "perf_rank"], "data_types": ["fund_rank"]},
    {"key": "fund_hold", "name": "基金持仓", "prefixes": ["fund_hold_"], "data_types": ["fund_hold"]},
    {
        "key": "industry",
        "name": "行业分类",
        "prefixes": ["industry_", "penetration_industry"],
        "data_types": ["industry"],
    },
    # 指数类别含指数历史日 K（其类别键为 ``index_history_history_index_*``）
    {
        "key": "index",
        "name": "指数数据",
        "prefixes": ["index_a", "index_us", "index_history_"],
        "data_types": ["index", "history_index", "history_index_us"],
    },
    {
        "key": "history",
        "name": "历史走势",
        "prefixes": ["history_"],
        "data_types": ["history_stock", "history_fund_otc"],
    },
    {
        "key": "profit_forecast",
        "name": "盈利预测",
        "prefixes": ["penetration_profit_forecast"],
        "data_types": ["profit_forecast"],
    },
    {"key": "dividend", "name": "分红数据", "prefixes": ["penetration_dividend"], "data_types": ["dividend"]},
    {"key": "fund_flow", "name": "资金流向", "prefixes": ["ff_"], "data_types": ["fund_flow"]},
    {
        "key": "financial_report",
        "name": "财报全文",
        "prefixes": ["report_datasink_"],
        "data_types": ["financial_report"],
    },
    {
        "key": "financial_indicator",
        "name": "财务指标",
        "prefixes": ["fin_indicator_"],
        "data_types": ["financial_indicator"],
    },
    {
        "key": "sentiment",
        "name": "市场情绪",
        "prefixes": ["sentiment"],
        "data_types": ["sentiment"],
    },
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


def _category_provider_hits(
    cat: dict[str, Any], usage: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, dict[str, Any]]:
    """归集该类别下各 provider 的本次命中次数（按 ``data_types`` 映射；无归属返回空 dict）。"""
    hits: dict[str, dict[str, Any]] = {}
    for data_type in cat.get("data_types") or [cat["key"]]:
        for provider_id, entry in (usage.get(data_type) or {}).items():
            slot = hits.setdefault(provider_id, {"count": 0, "label": entry.get("label") or provider_id})
            slot["count"] += int(entry.get("count") or 0)
    return hits


def _providers_text(hits: dict[str, dict[str, Any]]) -> str:
    """命中源展示文本（按命中次数降序；无 provider 归属时返回「—」）。

    无归属的典型场景：本次数据全部命中缓存（无 provider 参与网络取数）——此时
    「本次使用」列仍为已使用，两列并读即知「用了这份数据，但本次未走源」。
    """
    if not hits:
        return "—"
    ordered = sorted(hits.values(), key=lambda h: (-int(h["count"]), str(h["label"])))
    return "、".join(f"{h['label']} ×{h['count']}" for h in ordered)


def build_data_source_matrix() -> list[dict[str, Any]]:
    """构建数据源可用性矩阵。

    从 DegradationTracker 事件日志聚合每条 source_key 的最新状态，
    按类别（行情/基金/行业等）归类后计算整体健康度；同时附上 provider 级
    命中归属（``providers`` / ``providers_text``），令矩阵能回答「本次这类
    数据到底走的是腾讯还是同花顺」。

    Returns:
        矩阵行列表，每行含：
            key / name / status / detail / providers / providers_text /
            total / ok / degraded / failed
        status 取值 "ok" / "degraded" / "failed"；``providers`` 为 ``{provider_id:
        {count, label}}``，``providers_text`` 为其展示文本（无归属时为「—」）。
    """
    events = get_tracker().get_log()
    provider_usage = get_provider_usage()
    if not events and not provider_usage:
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
    # 行由两个信号建立：类别级事件（健康度）与 provider 级归属（命中源）。历史日 K 等
    # 只有后者（无降级事件记录），此类行只要本次确实取过数即成立，健康度无事件可判。
    matrix: list[dict[str, Any]] = []
    for cat in _SOURCE_CATEGORIES:
        cd = cat_data[cat["key"]]
        providers = _category_provider_hits(cat, provider_usage)
        if cd["total"] == 0 and not providers:
            continue
        if cd["total"] == 0:
            status = "ok"
            detail = f"取数 {sum(int(p['count']) for p in providers.values())} 次（无降级事件）"
        elif cd["failed"] == 0 and cd["degraded"] == 0:
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
        if cd["total"] > 0:
            detail = "，".join(detail_parts) if detail_parts else "无数据"

        row: dict[str, Any] = {
            "key": cd["key"],
            "name": cd["name"],
            "status": status,
            "detail": detail,
            "providers": providers,
            "providers_text": _providers_text(providers),
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

#: 类别定义索引（说明表行与矩阵类别同 ``id``；用于按 id 取 ``data_types`` 做 provider 归属联查）
_CATEGORY_DEFS: dict[str, dict[str, Any]] = {c["key"]: c for c in _SOURCE_CATEGORIES}

#: 免费源计费描述。需 key 的源由行内 ``billing`` 或 provider 层套餐表给出；
#: 「主源免费、兜底槽需 key」的类别仍记「免费」——key 要求写在 provider/note 文案里
_FREE_BILLING = "免费"

# 每行描述一个数据类别实际走的数据源链路、用途与凭据要求。
# 「本次是否使用」的前缀取自 _CATEGORY_PREFIXES；计费文案的数字同源于 provider 层套餐表。
_SOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "price",
        "category": "行情数据",
        "provider": (
            "腾讯财经 / 新浪财经（场内）；东方财富 / 天天基金（场外净值）→ 同花顺金融数据（官方快照兜底，需 key）"
        ),
        "usage": "持仓实时价与场外基金净值",
        "auth": "无需（主源）",
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
        "provider": "天天基金（基金主页面 + 季报 API）→ 同花顺金融数据（官方披露持仓兜底，需 key）",
        "usage": "基金底层持仓（含联接基金穿透目标 ETF）",
        "auth": "无需（主源）",
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
        "id": "history",
        "category": "历史走势",
        "provider": (
            "腾讯财经 / 新浪财经（A 股与场内基金前复权日 K）→ 同花顺金融数据（官方日 K 兜底，需 key）；"
            "天天基金 / 东方财富（场外基金净值序列）"
        ),
        "usage": "组合历史走势、回撤与流动性分析所需的日线序列",
        "auth": "无需（主源）",
        "note": "本类别只登记缓存键、不记降级事件，故「本次使用」以链路 provider 归属为正面证据（全部命中缓存时显示未使用）",
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
        "billing_provider": "datasink",
        "note": (
            "免费 key 需自备（datasink.ing）；需开启 功能开关 `financial_report_digest` 或 financial_indicator 才会取用；"
            "同花顺官方源不含公告原文，故本类别无兜底源"
        ),
    },
    {
        "id": "financial_indicator",
        "category": "财务指标",
        "provider": (
            "akshare 结构化财务指标（主源）；DataSinking 财报章节解析（备用支路）→ 同花顺官方合并报表派生（需 key）"
        ),
        "usage": "持仓 A 股基本面（指标列 / 质量档 / 年度趋势 / 真实 PE·PB 分位）",
        "auth": "无需（主源）",
        "note": (
            "备用支路需 DataSinking key、兜底槽位需 hithink key；"
            "两者均需开启 功能开关 `financial_indicator` 或 valuation_percentile"
        ),
    },
    {
        "id": "sentiment",
        "category": "市场情绪",
        "provider": "同花顺金融数据（龙虎榜 + 连板梯队；本类别唯一源）",
        "usage": "持仓/穿透标的当日上榜与连板事件行（行动建议章内嵌区块）",
        "auth": "需 key",
        "credential_source_id": "hithink",
        "billing": "免费（key 免费申领，官方不限累计调用次数）",
        "note": "需开启 功能开关 `market_sentiment`；只保留命中持仓/穿透标的代码的事件行，无命中时该区块不显示",
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


def _catalog_billing(cat: dict[str, Any], plan: str) -> str:
    """该行的计费文案：行内显式声明 → provider 层套餐文案（按套餐变化）→ 免费。

    「主源免费、兜底槽需 key」的类别仍记「免费」——本次主链路不花钱，key 要求
    写在 provider/note 文案里。需凭据的源不因此自动算付费（如同花顺 key 免费申领、
    官方不限累计调用次数）。
    """
    declared = cat.get("billing")
    if declared:
        return str(declared)
    if cat.get("billing_provider") == "datasink":
        from src.python.providers import datasink as _datasink

        return _datasink.billing_description(plan)
    return _FREE_BILLING


def build_data_source_catalog() -> list[dict[str, Any]]:
    """数据源说明表：描述实际使用的数据源、用途、计费与凭据要求。

    与 :func:`build_data_source_matrix` 互补：矩阵答「本次哪类源健康度如何」，
    本表答「这类数据实际走哪些源、是否付费、是否需 key、本次有没有用」。

    Returns:
        每行含 ``id / category / provider / usage / billing / auth / used / note``。
        ``used`` 为 True 表示本次运行**取得过该类别数据**（含命中缓存）——由各类别的
        取数链路以 ``report.data_status.mark_data_used`` 标记（**只记成功、不记降级**，
        故「未使用」仅说明本次未取到该类数据，不等于该源故障）；未登记类别级标记的
        类别（如历史走势只登记缓存键）以 provider 级归属为补充正面证据。
        需 key 的类别（如财报全文）的 ``auth`` 附加就绪状态。
    """
    from src.python.core.datasource_credential import credential_readiness, credential_ready_enabled

    observed = {ev["source_key"] for ev in get_tracker().get_log()}
    provider_usage = get_provider_usage()
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
        if not used:
            cat_def = _CATEGORY_DEFS.get(cat["id"])
            used = bool(cat_def) and bool(_category_provider_hits(cat_def, provider_usage))
        cred_id = cat.get("credential_source_id")
        billing = _catalog_billing(cat, plan)
        auth = cat["auth"]
        if cred_id:
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
