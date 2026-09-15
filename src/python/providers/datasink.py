"""DataSinking API — 全文本财报（中国 A 股）。

职责：
  - 列表取得单只股票的财报元数据（`/documents`）
  - 取单篇全文或单章节正文（`/documents/{id}`）
  - 取单篇的章节标题清单（`/documents/{id}/sections`）

凭据：用户自备 API key，写在通用密钥文件（默认
``data/config/data_key.json``）以 provider 名为节的 ``api_key`` 字段：
``{"datasink": {"api_key": "..."}}``；环境变量 ``DATASINK_API_KEY`` 可覆盖
（便于 CI / 临时切换）。缺凭据时链路主动跳过，不发起请求。凭据值**永不落
日志、报告与缓存**。

限速与配额（免费档：3 请求/秒、8,191 篇/日）：
  - 每次 HTTP 请求前经 :class:`RateLimiter` 取得许可，间隔 = 1 / 每秒上限；
    免费档无批量端点、必然逐篇请求，故限速必须落在本层（批量调度器层挡不住
    单条调用）
  - 请求前经日配额护栏计数（``data/state/datasink_quota.json``），超限即停并
    告警；配额与速率均由 :data:`_PLAN_LIMITS` 按套餐派生，可经 ``config.json``
    的 ``datasink`` 段覆盖

本模块只做「拿到上游原始响应」，字段归一由 ``schemas`` + ``source_adapter``
承担；缓存/熔断/降级由 ``fetcher/chain`` 承担。
"""

from __future__ import annotations

import json
import logging
import time
import os
import threading
from datetime import date
from typing import Any

from src.python.core.atomic_write import write_json_atomic
from src.python.core.constants import PROJECT_ROOT
from src.python.core.datasource_credential import CredentialSpec, credential_value, missing_credential
from src.python.core.datasource_credential import register_credential_spec as _register_credential_spec
from src.python.core.http_client import make_http_client

logger = logging.getLogger("invest")

_BASE_URL = "https://api.datasink.ing"
#: 429 限速后的退避秒数（重试一次；免费档 3 请求/秒）
_RATE_LIMIT_BACKOFF = 1.0
_TIMEOUT = 20.0
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; investor-util)"}

SOURCE_ID = "datasink"
DISPLAY_NAME = "DataSinking 财报"

#: 通用数据源密钥文件默认相对路径（配置键 ``data_key_file`` 可覆盖为绝对路径；
#: 文件以 provider 名为节，本源的节名为 ``datasink``）
DEFAULT_KEY_FILE = "data/config/data_key.json"

#: 计划 → (每秒请求上限, 每日文档配额)。官方定价页口径。
_PLAN_LIMITS: dict[str, tuple[int, int]] = {
    "free": (3, 8191),
    "yearly": (31, 131071),
}

#: 日配额计数状态文件（机器本地；测试经 conftest 重定向）
_QUOTA_FILE = os.path.join(PROJECT_ROOT, "data/state/datasink_quota.json")

_register_credential_spec(
    CredentialSpec(
        source_id=SOURCE_ID,
        display_name=DISPLAY_NAME,
        env_var="DATASINK_API_KEY",
        apply_url="https://datasink.ing",
        note="免费额度 3 请求/秒、8191 篇/日；付费 31 请求/秒、131071 篇/日",
        key_file=DEFAULT_KEY_FILE,
        key_file_setting="data_key_file",
        key_field="api_key",
    )
)


# 符号映射 ``to_fmp_symbol`` 统一存放于 ``core/code_utils.py``（多个数据源共用同一
# A 股→FMP 符号口径），本模块不再自留一份。

# ═══════════════════════════════════════════════════════════════
#  限速（计划感知）与日配额护栏
# ═══════════════════════════════════════════════════════════════


def _datasink_config() -> dict[str, Any]:
    try:
        from src.python.config import get_config

        section = get_config().get("datasink")
        return section if isinstance(section, dict) else {}
    except Exception:
        logger.debug("[datasink] 读取 datasink 配置失败，使用套餐默认")
        return {}


def resolve_plan(cfg: dict[str, Any] | None = None) -> str:
    """当前套餐（``free`` / ``yearly``）。"""
    plan = str((cfg or _datasink_config()).get("plan", "free")).strip().lower()
    return plan if plan in _PLAN_LIMITS else "free"


def resolve_requests_per_second(cfg: dict[str, Any] | None = None) -> float:
    """每秒请求上限：显式配置优先，否则按套餐派生。"""
    section = cfg or _datasink_config()
    configured = section.get("requests_per_second", 0)
    if isinstance(configured, (int, float)) and configured > 0:
        return float(configured)
    return float(_PLAN_LIMITS[resolve_plan(section)][0])


def resolve_daily_quota(cfg: dict[str, Any] | None = None) -> int:
    """每日文档配额：显式配置优先，否则按套餐派生；返回值恒为正（不限用 0 表达则回退套餐）。"""
    section = cfg or _datasink_config()
    configured = section.get("daily_quota", 0)
    if isinstance(configured, (int, float)) and configured > 0:
        return int(configured)
    return int(_PLAN_LIMITS[resolve_plan(section)][1])


_PLAN_TIER_LABELS: dict[str, str] = {"free": "免费档", "yearly": "付费档"}


def billing_description(plan: str | None = None) -> str:
    """套餐的计费与额度描述（报告「数据源说明表」消费）。

    数字同源于 :data:`_PLAN_LIMITS`，不在别处重复硬编码。
    """
    resolved = plan if plan in _PLAN_LIMITS else "free"
    rps, quota = _PLAN_LIMITS[resolved]
    return f"{_PLAN_TIER_LABELS.get(resolved, '免费档')}（{rps} 请求/秒、{quota:,} 篇/日）"


_limiter: Any = None
_limiter_lock = threading.Lock()


def _get_limiter() -> Any:
    """模块级限速器（惰性构建；配置热重载经 :func:`reset_datasink_limiter`）。"""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                from src.python.fetcher.batch import RateLimiter

                interval = 1.0 / resolve_requests_per_second()
                _limiter = RateLimiter({SOURCE_ID: interval})
    return _limiter


def reset_datasink_limiter() -> None:
    """丢弃限速器单例（配置刷新 / 测试隔离用）。"""
    global _limiter
    with _limiter_lock:
        _limiter = None


_quota_lock = threading.Lock()


def _read_quota() -> tuple[str, int]:
    """读取当日配额计数；文件缺失/损坏视为「当日零次」。"""
    try:
        with open(_QUOTA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("date", "")), int(data.get("count", 0) or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "", 0


def _consume_quota() -> bool:
    """请求前计数：返回 True 表示允许且已计数，False 表示当日配额耗尽。"""
    quota = resolve_daily_quota()
    if quota <= 0:
        return True
    with _quota_lock:
        today = date.today().isoformat()
        day, count = _read_quota()
        if day != today:
            day, count = today, 0
        if count >= quota:
            logger.warning("[datasink] 当日配额已用尽（%d/%d），跳过后续请求", count, quota)
            return False
        write_json_atomic(_QUOTA_FILE, {"date": day, "count": count + 1}, log_tag="datasink", noun="配额计数")
        return True


# ═══════════════════════════════════════════════════════════════
#  HTTP 取数
# ═══════════════════════════════════════════════════════════════


def _request(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """带凭据 / 限速 / 配额护栏的 GET；失败返回 None（不抛异常，不计熔断）。

    401/403（凭据无效）、429（限速）、其他非 200 一律记日志并返回 None——
    这些均属「源不可用」的代码级结果，交由链路按空结果降级，不计入传输级熔断。
    """
    if missing_credential(SOURCE_ID) is not None:
        logger.info("[datasink] 未配置凭据，跳过请求 %s", path)
        return None
    key = credential_value(SOURCE_ID)
    if not key:
        logger.info("[datasink] 凭据为空，跳过请求 %s", path)
        return None
    if not _consume_quota():
        return None
    _get_limiter().acquire(SOURCE_ID)

    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["apikey"] = key
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(f"{_BASE_URL}{path}", params=query, headers=_HEADERS)
    except Exception as e:  # 网络不可达：返回空，交由链路降级
        logger.warning("[datasink] 请求失败 %s: %s", path, e)
        return None

    if resp.status_code in (401, 403):
        logger.warning("[datasink] 凭据无效（HTTP %d），请检查 API key", resp.status_code)
        return None
    if resp.status_code == 429:
        # 限速：等待一个限速窗口后**重试一次**（免费档 3 请求/秒，并发路径下仍可能触顶）
        logger.warning("[datasink] 触发限速（HTTP 429），%.1fs 后重试一次", _RATE_LIMIT_BACKOFF)
        time.sleep(_RATE_LIMIT_BACKOFF)
        _get_limiter().acquire(SOURCE_ID)
        try:
            with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(f"{_BASE_URL}{path}", params=query, headers=_HEADERS)
        except Exception as e:
            logger.warning("[datasink] 重试失败 %s: %s", path, e)
            return None
        if resp.status_code != 200:
            logger.warning("[datasink] 重试仍失败（HTTP %d），跳过 %s", resp.status_code, path)
            return None
    if resp.status_code != 200:
        logger.warning("[datasink] 请求 %s 返回 HTTP %d", path, resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        logger.warning("[datasink] 响应非 JSON（%s）", path)
        return None
    return data if isinstance(data, dict) else None


def fetch_report_documents(
    symbol: str,
    doc_type: str | None = None,
    order: str = "desc",
    size: int = 1,
    page: int = 1,
) -> list[dict[str, Any]] | None:
    """取得一只股票的报告元数据列表（按披露期倒序）。

    Args:
        symbol: FMP 风格符号（如 ``600519.SS``）
        doc_type: 文种过滤（``annual`` / ``semiannual`` / ``q1`` / ``q3`` / ``amendment``）
        order: ``desc`` = 最新在前
        size: 返回条数（1~200）
        page: 页码

    Returns:
        文档元数据列表；无命中或被护栏拦下时返回空列表/None
    """
    data = _request("/documents", {"symbol": symbol, "doc_type": doc_type, "order": order, "size": size, "page": page})
    if data is None:
        return None
    items = data.get("items")
    return items if isinstance(items, list) else None


def fetch_report_document(doc_id: int | str, section: str | None = None) -> dict[str, Any] | None:
    """取单篇文档（默认全文，含 ``content``）；给了 ``section`` 则只取该章节正文。"""
    data = _request(f"/documents/{doc_id}", {"section": section})
    return data


def fetch_report_sections(doc_id: int | str) -> list[str] | None:
    """取单篇文档的**章节名清单**（用于按实际章节名精确取正文）。

    章节名各公司/文种不同（如「第三节管理层讨论与分析」「五、主要会计数据和财务指标」），
    硬编码裸章节名会因服务端匹配规则不一致而 404。先取清单再按子串匹配选择，
    即可避免「章节名猜错 → 整只标的被判未取到财报」。
    """
    data = _request(f"/documents/{doc_id}/sections", {})
    if data is None:
        return None
    sections = data.get("sections")
    if not isinstance(sections, list):
        return None
    return [str(s) for s in sections if str(s).strip()]
