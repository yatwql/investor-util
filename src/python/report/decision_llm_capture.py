"""决策跨期反思闭环 — LLM 智囊团操作建议表解析登记（语义名 decision_reflection）。

从 expert_review 内容（llm_content[1]，含「操作建议」表）逆向解析逐 code 的方向
判断，登记为 pending 决策，供日后用真实行情结算。本模块属 report 层（仅 report
消费），单向依赖 ``core``（账本 ``decision_ledger`` + 词表/解析 ``decision_header``），
对 LLM 表结构的 knowledge 全部由本层承载。

数据源与表结构（见 ``llm/prompts_action.py`` 尾部固定表 + ``llm/markdown.py``）：
  - ``markdown_to_html`` 无真实表格处理 → 每个表行落为独立 ``<p>`` 块，如
    ``<p>| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 理由 |</p>``（竖线保留）。
  - 表头行（品种列无 6 位 code）、分隔行（``|:---|``）、事实校验摘要（不以 ``|``
    起止）均自然跳过。
  - 方向与优先级的归一判据（词表、否定守卫、二义不猜）统一定义在
    ``core.decision_header``，本模块只做「取行 → 归一 → 按纪律登记」。

抽取顺序：结构化决策头优先（开关 ``decision_header_parse``），
不可用时回落确定性表格解析；两路都不落默认值。

登记纪律（承接设计文档 §4.2，防技术债务）：
  - **持有（0）不落账**：结算仅处理 ±1 方向决策，持有若落账将永远滞留 pending、
    持续污染 pending_count 与「历史决策复盘」区块 → 解析识别为中性但登记剔除。
  - **code 白名单**：须在持仓明细（holdings_details）内；空上下文/幻觉不入账。
  - **可结算不变量**：baseline_close 取持仓明细 ``price``（登记日最新已知价，即
    结算基线）。无可用基线的不登记——保证「入账必可结算」，不留永久 pending 债务。
  - 开关关闭全链路无感（不解析不落账）。
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Any, Iterable

from src.python.config.features import is_feature_enabled
from src.python.core import decision_ledger as dl
from src.python.core.num_utils import finite_or
from src.python.core.decision_header import (
    MAGNITUDE_RANK,
    STRUCTURED_HEADER_FLAG,
    extract_code,
    parse_decision_word,
    parse_priority,
    parse_structured_header,
)

logger = logging.getLogger("invest")

# 块级结束/自闭合标签 → 换行（对齐 report/llm_content.py 剥离风格，保留行结构）
_BLOCK_END_NEWLINE_RE = re.compile(
    r"(</p>|</li>|</h[1-6]>|</div>|</ul>|</ol>|<br\s*/?>|<hr\s*/?>)",
    re.IGNORECASE,
)


def is_active() -> bool:
    return dl.is_active()


# ── 表行定位与解析 ──────────────────────────────────────


def _normalized_text(content: str | None) -> str:
    """expert_review 内容 → 保留行结构的纯文本（HTML 与纯文本同口径）。

    HTML（真实 seam 输入）先做块级换行 + 去标签，再解实体；纯文本原样返回。
    结构化决策头抽取与表行切分共用本规整，避免两路各自处理 HTML。
    """
    if not content:
        return ""
    text = content
    if "<" in text:  # HTML：块级结束标签 → 换行保留行结构，再去除内联标签
        text = _BLOCK_END_NEWLINE_RE.sub("\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = _html.unescape(text)
    return text


def _iter_table_rows(expert_review_html: str | None) -> Iterable[str]:
    """将 expert_review 内容规整为「以 | 起止」的表行文本。

    表头/分隔/校验摘要/结构化决策头行（以「决策头：」起）等非数据行保留原样，
    由调用方按列解析自然跳过。
    """
    for raw in _normalized_text(expert_review_html).splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            yield line


def _split_cells(line: str) -> list[str]:
    """按竖线切分表行为单元格（保留空位以固定列位置）。"""
    return [c.strip() for c in line.strip("|").split("|")]


def _parse_table_row(line: str) -> dict[str, Any] | None:
    """解析单行表 → 决策行雏形；非数据行（表头/分隔/无操作值）返回 None。

    Returns:
        {code, name, direction, magnitude, detail}；detail 合并理由格（理由可能
        内含竖线，故按剩余列拼接，而非仅取第 4 列）。
    """
    cells = _split_cells(line)
    if len(cells) < 4:
        return None
    _prio, stock_cell, op_cell, *_rest = cells
    code = extract_code(stock_cell)
    if code is None:
        return None
    direction = parse_decision_word(op_cell)
    if direction is None:
        return None
    name = _strip_code(stock_cell)
    reason = " ".join(c for c in _rest if c.strip()) or ""
    return {
        "code": code,
        "name": name,
        "direction": direction,
        "magnitude": parse_priority(_prio),
        "detail": reason,
    }


def _strip_code(stock_cell: str) -> str:
    """从品种单元格去掉 6 位代码与分隔符，留下名称。"""
    return re.sub(r"(?<!\d)[0-9]{6}(?!\d)", "", stock_cell or "").strip(" -")


def _build_holdings_index(holdings_details: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """持仓明细 → {code: {name, price}}（价格用于结算基线；无价格记 0）。

    兼容带交易所前缀的持仓代码（如 sh600000）——补挂末 6 位数字别名，
    便于与表内裸 6 位 code 对账。
    """
    index: dict[str, dict[str, Any]] = {}
    for holding in holdings_details or []:
        code = str(holding.get("code") or "").strip()
        if not code:
            continue
        try:
            price = finite_or(holding.get("price"))
        except (TypeError, ValueError):
            price = 0.0
        entry = {"name": str(holding.get("name") or "").strip(), "price": price}
        index.setdefault(code, entry)
        # 非裸 6 位持仓代码（sh600000 / 600000.SH 等交易所前缀）→ 补挂裸 6 位别名，
        # 便于与表内 code 对账。
        bare = extract_code(code)
        if bare and bare != code:
            index.setdefault(bare, entry)
    return index


def extract_llm_decisions(
    expert_review_html: str | None,
    holdings_details: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """从 expert_review 内容抽取可登记的方向决策行（按 code 去重）。

    两路抽取，**结构化优先、确定性表格兜底**：
      ① 结构化决策头（开关 ``decision_header_parse``）——提示词追加的受控
         JSON 行，解析失败/缺失即回落；
      ② 操作建议表行（默认路径，始终可用）。
    两路都不做默认值填充：判不出方向即不登记。

    Returns:
        [{code, name, direction, magnitude, carrier, detail, baseline_close}, ...]
        - 仅保留减仓/加仓方向行（持有剔除）；
        - code 须在持仓白名单内；
        - 同 code 多条保留优先级（magnitude 强度）最高一条；
        - name 缺失时回填持仓名；baseline_close 取持仓 price（无 price 为 None）。
    """
    if not expert_review_html:
        return []
    holdings = _build_holdings_index(holdings_details)
    best: dict[str, dict[str, Any]] = {}
    structured = None
    if is_feature_enabled(STRUCTURED_HEADER_FLAG):
        structured = parse_structured_header(_normalized_text(expert_review_html))
    if structured is not None:
        for item in structured:
            _collect_decision(best, item, holdings)
        return list(best.values())
    for line in _iter_table_rows(expert_review_html):
        row = _parse_table_row(line)
        if row:
            _collect_decision(best, row, holdings)
    return list(best.values())


def _collect_decision(
    best: dict[str, dict[str, Any]],
    row: dict[str, Any],
    holdings: dict[str, dict[str, Any]],
) -> None:
    """把一条候选决策并入结果集（登记纪律在此统一执行）。

    纪律：持有/中性剔除；非持仓 code（空上下文/幻觉）不入账；同 code 保留
    优先级强度最高一条；name 缺失回填持仓名；baseline 取持仓 price，无价则 None。
    """
    if row["direction"] not in (dl.DIRECTION_LONG, dl.DIRECTION_SHORT):
        return  # 持有/中性剔除（结算无方向语义，落账即成永久 pending）
    holding = holdings.get(row["code"])
    if holding is None:
        return  # 非持仓 code（空上下文/幻觉）不入账
    if not row.get("name"):
        row["name"] = holding["name"]
    rank = MAGNITUDE_RANK.get(row["magnitude"], 0)
    prev = best.get(row["code"])
    if prev is None or rank > MAGNITUDE_RANK.get(prev["magnitude"], 0):
        row.update(
            {
                "carrier": dl.CARRIER_EXPERT_REVIEW,
                "baseline_close": holding["price"] if holding["price"] > 0 else None,
            }
        )
        best[row["code"]] = row


def register_llm_decisions(
    expert_review_html: str | None,
    holdings_details: list[dict[str, Any]] | None,
    *,
    report_date: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """登记 expert_review 操作建议表中的方向决策为 pending（开关关闭时无感）。

    Returns:
        {"registered": int, "ids": [decision_id, ...]}
    """
    if not is_active():
        return {"registered": 0, "ids": []}
    rows = extract_llm_decisions(expert_review_html, holdings_details)
    ids: list[str] = []
    skipped_dup = 0
    for row in rows:
        baseline = row.get("baseline_close")
        if baseline is None or baseline <= 0:
            logger.info(
                "[decision_llm_capture] 无可用基线跳过 LLM 决策登记: %s %s",
                row["code"],
                row.get("name") or "",
            )
            continue
        # 同日重复登记防重：expert_review 常命中 LLM 缓存，重生成报告时内容不变
        # → 同(报告日, code, carrier) pending 已在账本 → 不再重复入账。
        if dl.same_day_pending_exists(
            code=row["code"],
            carrier=dl.CARRIER_EXPERT_REVIEW,
            report_date=report_date,
            path=path,
        ):
            skipped_dup += 1
            continue
        did = dl.append_decision(
            code=row["code"],
            name=row["name"],
            direction=row["direction"],
            carrier=dl.CARRIER_EXPERT_REVIEW,
            magnitude=row["magnitude"],
            detail=row["detail"],
            report_date=report_date,
            baseline_close=baseline,
            path=path,
        )
        ids.append(did)
    if skipped_dup:
        logger.info("[decision_llm_capture] 同日重复 LLM 决策跳过: %d 条", skipped_dup)
    return {"registered": len(ids), "ids": ids}
