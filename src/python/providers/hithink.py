"""同花顺金融数据服务 — A 股行情 / 财务 / 基金 / 情绪面（官方 API）。

职责：只负责「拿到上游原始响应」——字段归一由 ``schemas`` + ``source_adapter``
承担，缓存 / 熔断 / 降级由 ``fetcher/chain`` 承担（与 ``providers/datasink.py``
同一分层口径）。

凭据：用户自备 API key（<https://fuyao.aicubes.cn/admin/> 免费申领），写在通用密钥文件
（默认 ``data/config/data_key.json``）以 ``hithink`` 为节的 ``api_key`` 字段；环境变量
``HITHINK_FINANCE_API_KEY`` 优先。缺凭据时链路主动跳过、不发起请求；凭据值**永不落
日志、报告与缓存**。

限流：官方口径「不限制累计调用次数」，但按实时负载动态限流（HTTP 429 或信封
``code=4001``）。文档明确要求「降低并发与频率、避免立即连续重试」，故本层：
  ① 每次请求前经 ``RateLimiter`` 取得许可（间隔 = 1/qps，默认 3.0 与保守口径对齐，
     可经 ``config.json`` 的 ``hithink.qps`` 覆盖）；
  ② 命中限流记 WARNING 并返回空，交链路降级——**不做立即重试**（与 datasink 的
     「退避后重试一次」不同，遵循各源官方指引）。

覆盖边界（官方明确不含，避免误用）：分钟 K / tick、**海外行情**、**宏观数据**、
**新闻公告原文与研报**。因此本模块**不能**替代 DataSinking 的财报全文链路（区块②），
QDII 穿透中的美股行情仍走既有美股链路。

响应信封：``{code, message, request_id, data}``；HTTP 状态码恒 200，业务错误看 ``code``
（``0`` 为成功）。错误码语义见 ``_ERROR_HINTS``。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from src.python.core.code_utils import to_fmp_symbol
from src.python.core.datasource_credential import (
    CredentialSpec,
    credential_value,
    missing_credential,
)
from src.python.core.datasource_credential import (
    register_credential_spec as _register_credential_spec,
)
from src.python.core.http_client import make_http_client

logger = logging.getLogger("invest")

SOURCE_ID = "hithink"
DISPLAY_NAME = "同花顺金融数据"

_BASE_URL = "https://fuyao.aicubes.cn"
_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; investor-util)"}

#: 通用数据源密钥文件默认相对路径（配置键 ``data_key_file`` 可覆盖为绝对路径）
DEFAULT_KEY_FILE = "data/config/data_key.json"

#: 默认每秒请求上限（官方不给固定额度，取保守值；``config.json`` 的 ``hithink.qps`` 可覆盖）
DEFAULT_QPS = 3.0

#: 业务错误码 → 语义（响应信封 ``code`` 非 0 时的日志依据）
_ERROR_HINTS: dict[int, str] = {
    1001: "缺少必填参数",
    1002: "参数格式错误",
    1003: "参数取值越界（枚举非法或窗口超限）",
    1004: "参数冲突（start/end 与 limit 混用或半开区间）",
    2001: "未认证（X-api-key 缺失或无效）",
    2003: "权限不足（API Key 无权调用该能力）",
    3001: "标的不存在",
    3002: "数据未就绪（标的暂无该业务数据）",
    3004: "标的类型不支持该能力",
    4001: "频率超限",
    5001: "服务内部错误",
    5002: "上游服务超时",
    5003: "数据源不可用",
}

_register_credential_spec(
    CredentialSpec(
        source_id=SOURCE_ID,
        display_name=DISPLAY_NAME,
        env_var="HITHINK_FINANCE_API_KEY",
        apply_url="https://fuyao.aicubes.cn/admin/",
        note="官方 A 股数据服务（同花顺）；不限累计调用次数，按负载动态限流",
        key_file=DEFAULT_KEY_FILE,
        key_file_setting="data_key_file",
        key_field="api_key",
        key_section=SOURCE_ID,
    )
)


def _get_limiter() -> Any:
    """进程级限速器（懒加载，线程安全）；间隔 = 1 / qps。"""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                from src.python.fetcher.batch import RateLimiter

                from src.python.config import get_config

                qps = DEFAULT_QPS
                try:
                    raw = (get_config().get("hithink") or {}).get("qps")
                    if isinstance(raw, (int, float)) and raw > 0:
                        qps = float(raw)
                except Exception:  # 配置不可用（如测试环境）→ 用默认值
                    pass
                _limiter = RateLimiter({SOURCE_ID: 1.0 / qps})
    return _limiter


_limiter: Any = None
_limiter_lock = threading.Lock()


def reset_hithink_limiter() -> None:
    """重置限速器单例（间隔读配置一次；测试隔离与配置热更新须重建）。"""
    global _limiter
    with _limiter_lock:
        _limiter = None


def _request(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """带凭据 / 限速 / 信封解析的 GET；失败返回 None（不抛异常、不计熔断）。

    返回 ``data`` 字段（业务数据容器）；``code != 0``、非 200、限流、网络不可达均返回 None
    并记日志，由链路按空结果降级。
    """
    if missing_credential(SOURCE_ID) is not None:
        logger.info("[hithink] 未配置凭据，跳过请求 %s", path)
        return None
    key = credential_value(SOURCE_ID)
    if not key:
        logger.info("[hithink] 凭据为空，跳过请求 %s", path)
        return None

    _get_limiter().acquire(SOURCE_ID)
    query = {k: v for k, v in params.items() if v is not None}
    headers = {**_HEADERS, "X-api-key": key}
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(f"{_BASE_URL}{path}", params=query, headers=headers)
    except Exception as e:  # 网络不可达：返回空，交链路降级
        logger.warning("[hithink] 请求失败 %s: %s", path, e)
        return None

    if resp.status_code == 429:
        logger.warning("[hithink] 触发限流（HTTP 429），按官方指引降低频率后由链路重试：%s", path)
        return None
    if resp.status_code != 200:
        logger.warning("[hithink] 请求 %s 返回 HTTP %d", path, resp.status_code)
        return None
    try:
        body = resp.json()
    except ValueError:
        logger.warning("[hithink] 响应非 JSON：%s", path)
        return None
    if not isinstance(body, dict):
        logger.warning("[hithink] 响应结构异常（非对象）：%s", path)
        return None

    code = body.get("code")
    if code != 0:
        hint = _ERROR_HINTS.get(code, "未知错误") if isinstance(code, int) else "未知错误"
        logger.warning("[hithink] 业务错误 code=%s（%s）%s：%s", code, hint, path, body.get("message"))
        return None
    data = body.get("data")
    return data if isinstance(data, dict) else None


# ── 代码映射 ────────────────────────────────────────────────


def to_thscode(code: str, *, is_fund: bool = False) -> str:
    """项目代码 → 同花顺 thscode（``.SH`` / ``.SZ`` / ``.BJ`` / ``.OF``）。

    Args:
        code: 项目内代码（6 位 A 股/场内 ETF，或场外基金代码）
        is_fund: 该标的是否为**场外基金**（组合里由持仓渠道判定后传入）。场外基金
            用 ``.OF`` 后缀——注意基金代码与深市股票在 ``00`` 前缀重叠（如 ``002943``
            既是场外基金也是深市股票），故不能只按代码猜，须由调用方给出语义。

    Returns:
        thscode；无法映射时返回空串。已带后缀的输入原样返回。
    """
    raw = (code or "").strip().upper()
    if not raw:
        return ""
    if "." in raw:
        return raw
    if is_fund:
        return f"{raw}.OF" if raw.isdigit() else ""
    fmp = to_fmp_symbol(raw)  # 与行情/财务链路同一套 A 股判定
    if fmp.endswith(".SS"):
        return f"{fmp[:-3]}.SH"
    if fmp.endswith((".SZ", ".BJ")):
        return fmp
    # 场内 ETF/LOF：沪市 5xxxxx、深市 1xxxxx（to_fmp_symbol 不覆盖这两段）
    if len(raw) == 6 and raw.isdigit():
        if raw.startswith("5"):
            return f"{raw}.SH"
        if raw.startswith("1"):
            return f"{raw}.SZ"
    return ""


# ── A 股：财务报表与指标 ─────────────────────────────────────


def fetch_financial_indicators(thscode: str, report: str) -> dict[str, Any] | None:
    """单只 A 股指定报告期的五类财务指标（成长/盈利/偿债/营运/现金流）。

    Args:
        thscode: 如 ``600519.SH``
        report: 报告期，格式 ``yyyy-1``（一季报）/ ``yyyy-2``（中报）/ ``yyyy-3``
            （三季报）/ ``yyyy-4``（年报）
    """
    return _request("/api/a-share/financials/indicators", {"thscode": thscode, "report": report})


def _statement_params(thscode: str, period: str, limit: int, start: int | None, end: int | None) -> dict[str, Any]:
    """三张报表共用的入参（``start``/``end`` 与 ``limit`` 互斥，官方约束）。"""
    params: dict[str, Any] = {"thscode": thscode, "period": period}
    if start is not None and end is not None:
        params.update({"start": start, "end": end})
    else:
        params["limit"] = limit
    return params


def fetch_income_statements(
    thscode: str,
    period: str = "annual",
    limit: int = 4,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any] | None:
    """整体合并利润表多期序列（按 ``period_end`` 降序）。"""
    return _request("/api/a-share/financials/income-statements", _statement_params(thscode, period, limit, start, end))


def fetch_balance_sheets(
    thscode: str,
    period: str = "annual",
    limit: int = 4,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any] | None:
    """整体合并资产负债表多期序列。"""
    return _request("/api/a-share/financials/balance-sheets", _statement_params(thscode, period, limit, start, end))


def fetch_cash_flow_statements(
    thscode: str,
    period: str = "annual",
    limit: int = 4,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any] | None:
    """整体合并现金流量表多期序列。"""
    return _request(
        "/api/a-share/financials/cash-flow-statements", _statement_params(thscode, period, limit, start, end)
    )


def fetch_valuation_snapshot(thscodes: list[str]) -> dict[str, Any] | None:
    """A 股最新估值快照（``pe_ttm`` / ``pe_mrq`` / ``pb_mrq`` / ``ps_ttm`` / ``pcf_ttm``）。

    官方限制：单次最多 100 个代码；**不提供历史估值**（估值分位仍需历史序列，故
    本接口只能补「现值」的稳定性，不能替代估值分位链路）。
    """
    joined = ",".join(t for t in (thscodes or []) if t)
    return _request("/api/a-share/valuations/snapshot", {"thscodes": joined}) if joined else None


# ── A 股：行情 / 日历 / 公司行动 ─────────────────────────────


def fetch_price_snapshot(
    thscodes: list[str] | None = None, limit: int | None = None, offset: int | None = None
) -> dict[str, Any] | None:
    """A 股行情快照（按 ``thscodes`` 批量，或全市场分页）。"""
    params: dict[str, Any] = {}
    joined = ",".join(t for t in (thscodes or []) if t)
    if joined:
        params["thscodes"] = joined
    else:
        params["limit"] = limit
        params["offset"] = offset
    return _request("/api/a-share/prices/snapshot", params)


def fetch_price_history(thscode: str, start_ms: int, end_ms: int, adjust: str = "forward") -> dict[str, Any] | None:
    """单只 A 股历史日 K（``adjust``：``none`` / ``forward`` 前复权 / ``backward`` 后复权）。

    官方约束：单次仅一个 thscode，窗口跨度 ≤ 10 年。
    """
    return _request(
        "/api/a-share/prices/historical",
        {"thscode": thscode, "interval": "1d", "start": start_ms, "end": end_ms, "adjust": adjust},
    )


def fetch_trading_days() -> dict[str, Any] | None:
    """A 股近一年交易日序列（固定窗口 ``[今日 - 1 年, 今日]``，无入参）。"""
    return _request("/api/a-share/calendar/trading-days", {})


def fetch_adjustment_factors(
    thscode: str, from_date: str | None = None, to_date: str | None = None
) -> dict[str, Any] | None:
    """单只 A 股复权因子事件流（现金分红 / 送股 / 配股），日期格式 ``YYYY-MM-DD``。"""
    return _request(
        "/api/a-share/corporate-actions/adjustment-factors",
        {"thscode": thscode, "from": from_date, "to": to_date},
    )


# ── 指数与板块 ──────────────────────────────────────────────


def fetch_index_constituents(thscode: str) -> dict[str, Any] | None:
    """同花顺指数 / 板块（含沪深 300 等标准指数）的成分股清单。"""
    return _request("/api/a-share-index/constituents/ths-stock-list", {"thscode": thscode})


# ── 情绪面（涨跌停 / 龙虎榜）────────────────────────────────


def fetch_limit_up_ladder() -> dict[str, Any] | None:
    """连板天梯：近 30 个交易日 × 各板位的股票梯队矩阵（无入参）。"""
    return _request("/api/a-share/special-data/limit-up-ladder", {})


def fetch_dragon_tiger_list(board_type: str = "all", date: str | None = None) -> dict[str, Any] | None:
    """龙虎榜榜单（``board_type``：``all`` 全部 / ``org`` 机构榜 / ``hot_money`` 游资榜）。"""
    return _request("/api/a-share/special-data/dragon-tiger-list", {"board_type": board_type, "date": date})


# ── 公募基金 ────────────────────────────────────────────────


def fetch_fund_portfolio_holdings(thscode: str) -> dict[str, Any] | None:
    """基金最新定期披露持仓（股票 / 债券 / 基金资产，含占比与排名）。

    注意：持仓来自**定期披露**，不代表实时持仓；与天天基金链路口径一致。
    """
    return _request("/api/fund/portfolio/holdings", {"thscode": thscode})


def fetch_fund_stock_history(thscode: str, report_type: str, end_date: str) -> dict[str, Any] | None:
    """基金指定报告期的历史股票持仓。"""
    return _request(
        "/api/fund/portfolio/stock-history",
        {"thscode": thscode, "report_type": report_type, "end_date": end_date},
    )


def fetch_fund_nav(thscode: str, range_: str | None = None, nav_type: str = "unit,adj") -> dict[str, Any] | None:
    """基金净值序列（``range_``：``week``/``month``/``tmonth``/``hyear``/``year``/``twoyear``/``tyear``/``fyear``）。"""
    return _request("/api/fund/performance/nav", {"thscode": thscode, "range": range_, "nav_type": nav_type})


__all__ = [
    "DEFAULT_KEY_FILE",
    "DEFAULT_QPS",
    "DISPLAY_NAME",
    "SOURCE_ID",
    "fetch_adjustment_factors",
    "fetch_balance_sheets",
    "fetch_cash_flow_statements",
    "fetch_dragon_tiger_list",
    "fetch_financial_indicators",
    "fetch_fund_nav",
    "fetch_fund_portfolio_holdings",
    "fetch_fund_stock_history",
    "fetch_income_statements",
    "fetch_index_constituents",
    "fetch_limit_up_ladder",
    "fetch_price_history",
    "fetch_price_snapshot",
    "fetch_trading_days",
    "fetch_valuation_snapshot",
    "reset_hithink_limiter",
    "to_thscode",
]
