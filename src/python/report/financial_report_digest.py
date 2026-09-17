"""持仓个股财报摘要 — 报告章节数据装配。

对持仓 + 穿透中的 A 股标的，取最新年报（无年报退半年报）的目标章节正文，
按配置截断为摘要，装配为报告层数据契约 ``financial_report_digest_data``。

数据来源：DataSinking 全文本财报（``fetcher/financial_report.py``）。
凭据缺失、无 A 股标的或全部无覆盖时返回 ``available=False`` 的降级契约，
展示层写占位，不阻断报告主链路。
"""

from __future__ import annotations

import logging
from typing import Any

from src.python.core.num_utils import ms_to_date_str
from src.python.fetcher.financial_report import (
    DEFAULT_DOC_TYPES,
    DEFAULT_MAX_CHARS,
    DEFAULT_SECTIONS,
    collect_a_share_targets,
    fetch_symbol_report_detailed,
    target_source_label,
)
from src.python.providers import datasink

logger = logging.getLogger("invest")

_DOC_TYPE_LABELS = {
    "annual": "年报",
    "semiannual": "半年报",
    "q1": "一季报",
    "q3": "三季报",
    "amendment": "修正稿",
}


def _doc_type_label(doc_type: str) -> str:
    return _DOC_TYPE_LABELS.get(str(doc_type), str(doc_type))


def _empty(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason, "rows": [], "failures": [], "entry_count": 0}


def build_financial_report_digest(
    holdings: list,
    config: dict | None = None,
    reporter: Any = None,
    penetrated_targets: list[dict[str, Any] | str] | None = None,
) -> dict[str, Any]:
    """构建「持仓个股财报摘要」数据契约。

    Args:
        holdings: 持仓对象列表
        config: 完整配置字典（读 ``datasink`` 段）
        reporter: 可选进度报告器
        penetrated_targets: 穿透标的（``{"code", "name", "sources"}``，可空）

    Returns:
        ``{available, reason, rows, failures, entry_count}``；不可用时
        ``available=False`` 且 ``reason`` 说明原因。行含 ``target_source``
        （直接持有 / 穿透：来源基金），失败行含具体原因（索引无报告 / 目标章节缺失）。
    """
    config = config or {}
    if datasink.missing_credential(datasink.SOURCE_ID) is not None:
        return _empty("未配置 DataSinking API key（详见数据源可用性矩阵）")

    section_cfg = config.get("datasink") or {}
    raw_sections = section_cfg.get("sections") or list(DEFAULT_SECTIONS)
    sections = tuple(str(s) for s in raw_sections if str(s).strip()) or DEFAULT_SECTIONS
    max_chars = section_cfg.get("max_chars", DEFAULT_MAX_CHARS)
    max_chars = int(max_chars) if isinstance(max_chars, (int, float)) and max_chars > 0 else DEFAULT_MAX_CHARS
    doc_types = tuple(section_cfg.get("doc_types") or DEFAULT_DOC_TYPES)

    targets = collect_a_share_targets(holdings, penetrated_targets)
    if not targets:
        return _empty("无 A 股持仓或穿透标的")

    if reporter is not None:
        reporter.info(f"正在获取 {len(targets)} 只 A 股的财报摘要...")

    # 并发取数：worker 数取 config 的 batch.datasink_workers（默认 2——免费档 3 请求/秒，
    # 而每标的现为「索引 + 章节清单 + 正文」三次请求，并发过高易触 429）；
    # 每秒速率仍由 provider 层限速器逐请求兜底（线程安全），并发只提高请求管道利用率
    from concurrent.futures import ThreadPoolExecutor

    from src.python.fetcher.batch import get_batch_worker_count

    workers = get_batch_worker_count("datasink_workers", 2)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="datasink_reports") as pool:
        records = list(
            pool.map(lambda t: fetch_symbol_report_detailed(t["symbol"], doc_types, sections, max_chars), targets)
        )

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for target, (record, reason) in zip(targets, records):
        label = target_source_label(target)
        if not record:
            failures.append(
                {
                    "code": target["code"],
                    "name": target["name"],
                    "kind": str(target.get("kind") or ""),
                    "target_source": label,
                    "reason": reason or "未取到财报",
                }
            )
            continue
        rows.append(
            {
                "code": target["code"],
                "name": target["name"] or str(record.get("symbol") or target["symbol"]),
                "symbol": target["symbol"],
                "kind": str(target.get("kind") or ""),
                "target_source": label,
                "report_period": str(record.get("report_period") or ""),
                "doc_type": _doc_type_label(str(record.get("doc_type") or "")),
                "title": str(record.get("title") or ""),
                "announcement_date": ms_to_date_str(record.get("announcement_time")),
                "summary": str(record.get("summary") or ""),
                "source": str(record.get("source") or ""),
                "adjunct_url": str(record.get("adjunct_url") or ""),
            }
        )

    if not rows:
        result = _empty("全部标的未取到财报")
        result["failures"] = failures
        return result

    logger.info("[financial_report_digest] 取到 %d/%d 只 A 股财报摘要", len(rows), len(targets))
    return {
        "available": True,
        "reason": "",
        "rows": rows,
        "failures": failures,
        "entry_count": len(rows),
    }
