"""天天基金 API — 基金业绩排名、区间收益和底层持仓数据。

API 来源：
  - 基金持仓（主页面）: fund.eastmoney.com/{code}.html（HTML 表格解析）
  - 基金持仓（季度回退）: fundf10.eastmoney.com/FundArchivesDatas.aspx（JS 变量 apidata.content）
  - 基金业绩排名: fund.eastmoney.com/pingzhongdata/{code}.js（JS 变量提取）
  - 同类排名: fund.eastmoney.com/pingzhongdata/{code}.js → Data_rateInSimilarType
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime
from typing import Any

import httpx

from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_TIMEOUT = 15.0


def _safe_float(s: Any) -> float:
    try:
        return float(s) if s is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


# ── 基金底层持仓（前 10 大重仓股） ─────────────────────────


def _request_fund_html(code: str) -> str | None:
    """请求基金主页面 HTML。"""
    url = f"https://fund.eastmoney.com/{code.strip()}.html"
    logger.debug("请求基金持仓页面: %s", url)
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            return resp.text
    except httpx.TimeoutException:
        logger.warning("基金持仓页面超时: %s", code)
        return None
    except httpx.RequestError as e:
        logger.warning("基金持仓页面请求失败 %s: %s", code, e)
        return None


def _find_holdings_table(html: str) -> str | None:
    """从基金主页 HTML 中找到持仓数据表格。

    先按特征关键词（"占净值比例"+%等）匹配，
    再按足够数据行兜底。
    """
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)

    for tbl in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL)
        if len(rows) >= 3:
            all_text = re.sub(r"<[^>]+>", " ", tbl)
            if re.search(r"[涨跌]|[占净值]", all_text) and re.search(r"%", all_text):
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
        name_match = re.search(r'<a[^>]*>(.*?)</a>', cell0)
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
        if stock_name and ratio > 0:
            holdings.append({"name": stock_name, "code": stock_code, "ratio": ratio})

    return holdings


def _extract_fund_meta(html: str) -> tuple[str, str]:
    """从基金主页 HTML 提取基金名称和报告日期。"""
    fund_name = ""
    title_match = re.search(r"<title>(.*?)\(|（", html)
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


def _request_quarterly_api(code: str, api_type: str) -> str | None:
    """请求季报 API 并解析 JS 字符串内容。"""
    url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://fundf10.eastmoney.com/",
    }
    params = {
        "type": api_type,
        "code": code.strip(),
        "topline": 10,
        "year": "",
        "month": "",
        "rt": str(random.random()),
    }
    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.encoding = "utf-8"
            text = resp.text
    except httpx.RequestError as e:
        logger.warning("基金持仓 API (%s) 请求失败 %s: %s", api_type, code, e)
        return None

    m = re.search(r'content\s*:\s*"(.+?)"\s*,\s*arryear', text, re.DOTALL)
    if not m:
        logger.debug("基金持仓 API (%s) 未找到 content 字段: %s", api_type, code)
        return None

    raw_content = m.group(1)
    if not raw_content or raw_content.isspace():
        logger.debug("基金持仓 API (%s) 内容为空: %s", api_type, code)
        return None

    try:
        return json.loads('"' + raw_content + '"')
    except json.JSONDecodeError:
        logger.warning("基金持仓 API (%s) JS 字符串解析失败: %s", api_type, code)
        return None


def _parse_quarterly_holdings(html_content: str) -> list[dict[str, Any]]:
    """从季报 API 返回的 HTML 内容中解析持仓行。"""
    holdings: list[dict[str, Any]] = []

    table_match = re.search(
        r"<table[^>]*>(.*?)</table>", html_content, re.DOTALL | re.IGNORECASE
    )
    if not table_match:
        return holdings

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 4:
            continue

        code_cell = cells[1]
        code_a = re.search(r"<a[^>]*>(.*?)</a>", code_cell)
        stock_code = (
            code_a.group(1).strip()
            if code_a else re.sub(r"<[^>]+>", "", code_cell).strip()
        )

        name_cell = cells[2]
        name_a = re.search(r"<a[^>]*>(.*?)</a>", name_cell)
        stock_name = (
            name_a.group(1).strip()
            if name_a else re.sub(r"<[^>]+>", "", name_cell).strip()
        )

        if not stock_name or not stock_code:
            continue

        ratio = 0.0
        for cell in cells:
            pct_match = re.search(r"(\d+\.?\d*)%", cell)
            if pct_match:
                ratio = _safe_float(pct_match.group(1))
                break
        if ratio > 0:
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
    自动尝试股票持仓（jjcc）和债券持仓（zqcc）两种类型并合并结果。

    API: fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}
    返回 JavaScript 变量 apidata.content，包含 HTML 持仓表格。

    Args:
        code: 6 位基金代码

    Returns:
        同 fetch_fund_holdings，或 None
    """
    all_holdings: list[dict[str, Any]] = []
    fund_name = ""
    report_date = ""

    for api_type in ("jjcc", "zqcc"):
        html_content = _request_quarterly_api(code, api_type)
        if html_content is None:
            continue

        if not fund_name:
            fund_name, report_date = _extract_quarterly_meta(html_content)
        if not report_date:
            _, report_date = _extract_quarterly_meta(html_content)

        holdings = _parse_quarterly_holdings(html_content)
        all_holdings.extend(holdings)

        if all_holdings:
            break  # 已有持仓数据，无需尝试其它类型

    if not all_holdings:
        logger.info("基金持仓 API 全部类型无有效持仓: %s", code)
        return None

    logger.info("基金持仓 API %s（%s）: %d 条持仓, 报告期 %s",
                fund_name or code, code, len(all_holdings), report_date or "未知")
    return {"code": code.strip(), "name": fund_name, "date": report_date, "holdings": all_holdings}


# ── 基金业绩排名（同类排名 + 区间收益） ──────────────────


def _request_pingzhong_data(code: str) -> str | None:
    """请求基金业绩数据 JS 文件。"""
    url = f"https://fund.eastmoney.com/pingzhongdata/{code.strip()}.js"
    logger.debug("请求基金业绩数据: %s", url)
    try:
        with make_http_client(timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            return resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("基金业绩 API 请求失败 %s: %s", code, e)
        return None


def _parse_syl_returns(text: str) -> dict[str, dict[str, Any]]:
    """解析各区间收益率（syl_* JS 变量）。"""
    period_map = {
        "近1月": "syl_1y", "近3月": "syl_3y",
        "近6月": "syl_6y", "近1年": "syl_1n",
    }
    rankings: dict[str, dict[str, Any]] = {}
    for period, var_name in period_map.items():
        m = re.search(rf"var\s+{var_name}\s*=\s*\"?(-?[\d.]+)", text)
        if m:
            rankings[period] = {"return": _safe_float(m.group(1))}
    return rankings


def _parse_rank_entry(text: str) -> dict[str, Any]:
    """解析同类排名（Data_rateInSimilarType）和百分位（Data_rateInSimilarPersent）。"""
    rank_entry: dict[str, Any] = {"rank": "--", "total": "--", "percentile": "--"}

    rank_match = re.search(r"var Data_rateInSimilarType\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if rank_match:
        try:
            rank_data = json.loads(rank_match.group(1))
            if rank_data:
                last = rank_data[-1]
                rank_entry["rank"] = str(last.get("y", "--"))
                rank_entry["total"] = str(last.get("sc", "--"))
        except (json.JSONDecodeError, IndexError, TypeError) as _e:
            logger.warning("解析同类排名数据失败: %s", _e)

    pct_match = re.search(r"var Data_rateInSimilarPersent\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if pct_match:
        try:
            pct_data = json.loads(pct_match.group(1))
            if pct_data:
                last_pct = pct_data[-1]
                if isinstance(last_pct, list) and len(last_pct) >= 2:
                    rank_entry["percentile"] = str(round(last_pct[1], 2))
        except (json.JSONDecodeError, IndexError, TypeError) as _e:
            logger.warning("解析百分位排名数据失败: %s", _e)

    return rank_entry


def _calc_rating_from_entry(rank_entry: dict[str, Any]) -> str:
    """根据排名百分位或排名/总数计算评级。"""
    if rank_entry.get("percentile", "--") != "--":
        try:
            pct_val = float(rank_entry["percentile"]) / 100.0
        except (ValueError, TypeError):
            return ""

        if pct_val <= 0.20:
            return "优秀"
        elif pct_val <= 0.30:
            return "良好"
        elif pct_val <= 0.50:
            return "稳定"
        else:
            return "偏差"

    if rank_entry.get("rank", "--") != "--" and rank_entry.get("total", "--") != "--":
        try:
            pct_val = int(rank_entry["rank"]) / int(rank_entry["total"])
        except (ValueError, ZeroDivisionError):
            return ""

        if pct_val <= 0.20:
            return "优秀"
        elif pct_val <= 0.30:
            return "良好"
        elif pct_val <= 0.50:
            return "稳定"
        else:
            return "偏差"

    return ""


def _parse_perf_evaluation(text: str) -> dict[str, Any] | None:
    """解析业绩评价数据（Data_performanceEvaluation JS 变量）。"""
    pe_match = re.search(
        r'var Data_performanceEvaluation\s*=\s*(\{[^;]+\});', text, re.DOTALL
    )
    if not pe_match:
        return None
    try:
        return json.loads(pe_match.group(1))
    except (json.JSONDecodeError, TypeError, ValueError) as _e:
        logger.warning("解析业绩评价数据失败: %s", _e)
        return None


def fetch_fund_rankings(code: str) -> dict[str, Any] | None:
    """获取基金同类排名和区间收益率。

    API: fund.eastmoney.com/pingzhongdata/{code}.js
    从 JS 变量 Data_rateInSimilarType（排名）和 Data_rateInSimilarPersent（百分位）提取。

    Args:
        code: 6 位基金代码

    Returns:
        {"code", "name", "rankings", "rating", "perf_evaluation"} 或 None
    """
    text = _request_pingzhong_data(code)
    if text is None:
        return None

    name = ""
    name_match = re.search(r'var\s+fS_name\s*=\s*"([^"]*)"', text)
    if name_match:
        name = name_match.group(1)

    rankings = _parse_syl_returns(text)
    rank_entry = _parse_rank_entry(text)
    if rank_entry.get("rank") != "--" or rank_entry.get("percentile") != "--":
        rankings["同类排名"] = rank_entry

    rating = _calc_rating_from_entry(rank_entry)
    perf_eval = _parse_perf_evaluation(text)

    logger.info("基金 %s（%s）: 排名 %s/%s, 评级 %s",
                name, code, rank_entry.get("rank", "?"), rank_entry.get("total", "?"),
                rating or "未知")

    return {
        "code": code.strip(),
        "name": name,
        "type": "",
        "rankings": rankings,
        "rating": rating,
        "perf_evaluation": perf_eval,
    }


