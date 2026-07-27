"""天天基金 API — 基金持仓数据（主页面 HTML + 季报 API 回退）。

职责：
  - 从基金主页面 fund.eastmoney.com/{code}.html 解析前 10 大持仓
  - 回退到季报 API fundf10.eastmoney.com/FundArchivesDatas.aspx（QDII/联接等）
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from src.python.providers.tiantian_base import (
    _request_fund_html,
    _request_quarterly_api,
    _safe_float,
)

logger = logging.getLogger("invest")


# ── 主页面持仓解析 ─────────────────────────


def _find_holdings_table(html: str) -> str | None:
    """从基金主页 HTML 中找到持仓数据表格。

    先按特征关键词（"占净值比例"+%等）匹配，
    再按足够数据行兜底。

    注意：需排除含"近N周/月/年"等时间段标记的收益率排行表格，
    这类表格也包含"涨跌幅"和"%"但非持仓数据。
    """
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)

    for tbl in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL)
        if len(rows) >= 3:
            all_text = re.sub(r"<[^>]+>", " ", tbl)
            if re.search(r"[涨跌]|[占净值]", all_text) and re.search(r"%", all_text):
                # 排除收益率/排行表格（含"近N"时间段标记如 近1年/近3月）
                if re.search(r"近\d+(日|周|月|年|季度)", all_text):
                    continue
                return tbl

    for tbl in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL)
        data_rows = 0
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            for cell in cells:
                if re.search(r"\d+\.\d+%", cell):
                    data_rows += 1
                    break
        if data_rows >= 5:
            return tbl

    return None


def _parse_holdings_rows(table_html: str) -> list[dict[str, Any]]:
    """解析持仓表格行，提取股票名称/代码/占比。"""
    holdings: list[dict[str, Any]] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)

    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 2:
            continue
        cell0 = cells[0]
        name_match = re.search(r"<a[^>]*>(.*?)</a>", cell0)
        if not name_match:
            continue
        stock_name = re.sub(r"<[^>]+>", "", name_match.group(1)).strip()
        if not stock_name:
            continue

        stock_code = ""
        code_match = re.search(r'stockcode="stock_(\d+)"', cell0)
        if code_match:
            stock_code = code_match.group(1)
        if not stock_code:
            href_match = re.search(r'href="[^"]*?[/.](\d{6})', cell0)
            if href_match:
                stock_code = href_match.group(1)

        ratio = 0.0
        for cell in cells[1:]:
            pct_match = re.search(r"(\d+\.?\d*)%", cell)
            if pct_match:
                ratio = _safe_float(pct_match.group(1))
                break
        # ratio > 100 不可能是有效持仓占比（占净值比例不会超 100%），跳过
        if stock_name and 0 < ratio <= 100:
            holdings.append({"name": stock_name, "code": stock_code, "ratio": ratio})

    return holdings


def _extract_fund_meta(html: str) -> tuple[str, str]:
    """从基金主页 HTML 提取基金名称和报告日期。"""
    fund_name = ""
    title_match = re.search(r"<title>(.*?)[\(（]", html)
    if title_match:
        fund_name = title_match.group(1).strip()
    report_date = ""
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", html[2000:5000])
    if date_match:
        report_date = date_match.group(1)
    return fund_name, report_date


def fetch_fund_holdings(code: str) -> dict[str, Any] | None:
    """获取一只基金的前 10 大持仓（从基金主页面 HTML 解析）。

    对于 QDII/联接等主页面无持仓表格的基金，会自动回退到季报 API。

    API: fund.eastmoney.com/{code}.html

    Args:
        code: 6 位基金代码

    Returns:
        {
            "code": 基金代码,
            "name": 基金名称,
            "date": 报告期 (YYYY-MM-DD),
            "holdings": [{"name", "code", "ratio"}, ...]
        }
        None: 获取失败
    """
    html = _request_fund_html(code)
    if html is None:
        return None

    holdings_table = _find_holdings_table(html)
    holdings: list[dict[str, Any]] = []
    if holdings_table:
        holdings = _parse_holdings_rows(holdings_table)
    if not holdings:
        logger.info("基金 %s 主页面无持仓数据，尝试季报 API...", code)
        q_result = fetch_quarterly_holdings(code)
        if q_result and q_result.get("holdings"):
            return q_result  # 季报结果含名称/日期/持仓

    fund_name, report_date = _extract_fund_meta(html)

    logger.info("基金 %s（%s）: 解析到 %d 条持仓", fund_name or code, code, len(holdings))
    return {"code": code.strip(), "name": fund_name, "date": report_date, "holdings": holdings}


# ── 基金季报持仓（回退链路：QDII/联接/债券等） ─────────────


def _recent_quarters(n: int = 4) -> list[tuple[int, int]]:
    """返回最近 n 个完整季度的 (year, month) 列表，按时间降序。

    month 取季度末月（3/6/9/12），对应季报 API 参数要求。
    如当前为 2026-07（Q3），则最近完整季度为 2026-06（Q2）。
    """
    now = datetime.now()
    qe = ((now.month - 1) // 3) * 3  # 0 → 12(prev year), 3, 6, 9
    quarters: list[tuple[int, int]] = []
    y, m = now.year, qe
    for _ in range(n):
        if m == 0:
            y -= 1
            m = 12
        quarters.append((y, m))
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
    return quarters


def _parse_quarterly_holdings(html_content: str) -> list[dict[str, Any]]:
    """从季报 API 返回的 HTML 内容中解析持仓行。"""
    holdings: list[dict[str, Any]] = []

    table_match = re.search(r"<table[^>]*>(.*?)</table>", html_content, re.DOTALL | re.IGNORECASE)
    if not table_match:
        return holdings

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 4:
            continue

        code_cell = cells[1]
        code_a = re.search(r"<a[^>]*>(.*?)</a>", code_cell)
        stock_code = code_a.group(1).strip() if code_a else re.sub(r"<[^>]+>", "", code_cell).strip()

        name_cell = cells[2]
        name_a = re.search(r"<a[^>]*>(.*?)</a>", name_cell)
        stock_name = name_a.group(1).strip() if name_a else re.sub(r"<[^>]+>", "", name_cell).strip()

        if not stock_name or not stock_code:
            continue

        ratio = 0.0
        for cell in cells:
            pct_match = re.search(r"(\d+\.?\d*)%", cell)
            if pct_match:
                ratio = _safe_float(pct_match.group(1))
                break
        if 0 < ratio <= 100:
            holdings.append({"name": stock_name, "code": stock_code, "ratio": ratio})

    return holdings


def _extract_quarterly_meta(html_content: str) -> tuple[str, str]:
    """从季报 HTML 中提取基金名称和报告日期。"""
    fund_name = ""
    name_match = re.search(r'<a\s+title=[\'"]([^\'"]+)[\'"]', html_content)
    if name_match:
        fund_name = name_match.group(1).strip()
    else:
        name_match = re.search(r'<a\s+href=[\'"][^\'"]+[\'"]>([^<]+)</a>', html_content)
        if name_match:
            fund_name = name_match.group(1).strip()

    report_date = ""
    date_match = re.search(r"截止至[：:].*?(\d{4}-\d{2}-\d{2})", html_content)
    if date_match:
        report_date = date_match.group(1)

    return fund_name, report_date


def fetch_quarterly_holdings(code: str) -> dict[str, Any] | None:
    """从东方财富基金持仓 API 获取基金前 10 大持仓。

    当主页面 HTML 解析无数据时调用（QDII/联接/短期债券基金常见）。
    自动按最近完整季度→上季度 逐季尝试，最多回溯 4 个季度。
    若指定季度均无数据，回退到不指定年份的默认请求（部分基金仅有早期年报数据）。

    API: fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&year={year}&month={month}
    返回 JavaScript 变量 apidata.content，包含 HTML 持仓表格。

    Args:
        code: 6 位基金代码

    Returns:
        同 fetch_fund_holdings，或 None
    """
    # ── 优先策略：指定最近完整季度，从新到旧回溯 ──
    for year, month in _recent_quarters(4):
        result = _fetch_single_quarter(code, year, month)
        if result:
            return result

    # ── 回退策略：不指定年份，让 API 返回默认数据（部分基金仅有早期报告） ──
    logger.info("基金持仓 API %s: 最近 4 季度均无持仓，尝试默认请求...", code)
    result = _fetch_single_quarter(code)
    if result:
        logger.info("基金持仓 API %s 默认请求成功（报告期 %s）", code, result.get("date", "未知"))
        return result

    logger.info("基金持仓 API 全部无有效持仓: %s", code)
    return None


def _fetch_single_quarter(code: str, year: int | None = None, month: int | None = None) -> dict[str, Any] | None:
    """尝试获取指定季度的持仓数据，返回结构化结果或 None。"""
    all_holdings: list[dict[str, Any]] = []
    fund_name = ""
    report_date = ""

    for api_type in ("jjcc", "zqcc"):
        html_content = _request_quarterly_api(code, api_type, year=year, month=month)
        if html_content is None:
            continue

        if not fund_name:
            fund_name, report_date = _extract_quarterly_meta(html_content)
        if not report_date:
            _, report_date = _extract_quarterly_meta(html_content)

        holdings = _parse_quarterly_holdings(html_content)
        all_holdings.extend(holdings)

        if all_holdings:
            break

    if not all_holdings:
        return None

    label = f"{year}-{month:02d}" if year is not None else "默认"
    logger.info(
        "基金持仓 API %s（%s）: %d 条持仓, 报告期 %s（%s）",
        fund_name or code,
        code,
        len(all_holdings),
        report_date or "未知",
        label,
    )
    return {"code": code.strip(), "name": fund_name, "date": report_date, "holdings": all_holdings}
