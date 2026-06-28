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
            "holdings": [
                {"name": "贵州茅台", "code": "600519", "ratio": 9.50},
                ...
            ]
        }
        None: 获取失败
    """
    url = f"https://fund.eastmoney.com/{code.strip()}.html"
    logger.debug("请求基金持仓页面: %s", url)

    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, verify=False) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            html = resp.text
    except httpx.TimeoutException:
        logger.warning("基金持仓页面超时: %s", code)
        return None
    except httpx.RequestError as e:
        logger.warning("基金持仓页面请求失败 %s: %s", code, e)
        return None

    # 找到持仓数据表格（Table 5，约第 5-7 个表格为持仓表）
    # 特征：包含"占净值比例"或股票名称列表
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)

    holdings_table = None
    for tbl in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL)
        if len(rows) >= 3:  # 至少表头 + 数据行
            all_text = re.sub(r"<[^>]+>", " ", tbl)
            # 检查是否包含典型持仓表的关键词
            if re.search(r"[涨跌]|[占净值]", all_text) and re.search(r"%", all_text):
                holdings_table = tbl
                break

    if not holdings_table:
        # 备用：检查有足够数据行且包含百分比的行
        for tbl in tables:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.DOTALL)
            data_rows = 0
            for row in rows:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
                for cell in cells:
                    if re.search(r"\d+\.\d+%", cell):
                        data_rows += 1
                        break
            if data_rows >= 5:  # 至少 5 行有百分比数据
                holdings_table = tbl
                break

    holdings: list[dict[str, Any]] = []

    if not holdings_table:
        logger.info("基金 %s（%s）未找到持仓表格，尝试季报...", code, code)
    else:
        # 解析持仓行
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", holdings_table, re.DOTALL)

        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(cells) < 2:
                continue
            # 提取股票名称（取第一个 <a> 标签的文本）
            cell0 = cells[0]
            name_match = re.search(r'<a[^>]*>(.*?)</a>', cell0)
            if not name_match:
                continue
            stock_name = re.sub(r"<[^>]+>", "", name_match.group(1)).strip()
            if not stock_name:
                continue
            # 提取股票代码（从 stockcode 属性或 href 中）
            stock_code = ""
            code_match = re.search(r'stockcode="stock_(\d+)"', cell0)
            if code_match:
                stock_code = code_match.group(1)
            if not stock_code:
                # 尝试从 href 提取（格式: //quote.eastmoney.com/unify/r/0.300604 或 1.600660）
                href_match = re.search(r'href="[^"]*?[/.](\d{6})', cell0)
                if href_match:
                    stock_code = href_match.group(1)
            # 提取占比（第二个字段或最后一个含 % 的 td）
            ratio = 0.0
            for cell in cells[1:]:
                pct_match = re.search(r"(\d+\.?\d*)%", cell)
                if pct_match:
                    ratio = _safe_float(pct_match.group(1))
                    break
            if stock_name and ratio > 0:
                holdings.append({
                    "name": stock_name,
                    "code": stock_code,
                    "ratio": ratio,
                })

    if not holdings:
        logger.info("基金 %s（%s）持仓表格解析后无有效数据", code, code)

    # 提取基金名称（从页面标题）
    fund_name = ""
    title_match = re.search(r"<title>(.*?)\(|（", html)
    if title_match:
        fund_name = title_match.group(1).strip()

    # 提取报告期（页面中可能有"最新持仓"提示）
    report_date = ""
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", html[2000:5000])  # 从页面中部查找
    if date_match:
        report_date = date_match.group(1)

    if not holdings:
        # 主页面无持仓表格 → 尝试季报 API（QDII/联接/债券基金常见情况）
        logger.info("基金 %s（%s）主页面无持仓数据，尝试季报 API...", code, code)
        q_result = fetch_quarterly_holdings(code)
        if q_result and q_result.get("holdings"):
            holdings = q_result["holdings"]
            if q_result.get("date"):
                report_date = q_result["date"]
            if q_result.get("name"):
                fund_name = q_result["name"]

    logger.info("基金 %s（%s）: 解析到 %d 条持仓", fund_name or code, code, len(holdings))
    return {
        "code": code.strip(),
        "name": fund_name,
        "date": report_date,
        "holdings": holdings,
    }


# ── 基金季报持仓（回退链路：QDII/联接/债券等） ─────────────


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
    url = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://fundf10.eastmoney.com/",
    }

    all_holdings: list[dict[str, Any]] = []
    fund_name = ""
    report_date = ""

    for api_type in ("jjcc", "zqcc"):
        params = {
            "type": api_type,
            "code": code.strip(),
            "topline": 10,
            "year": "",
            "month": "",
            "rt": str(random.random()),
        }
        try:
            with httpx.Client(timeout=_TIMEOUT, verify=False) as client:
                resp = client.get(url, params=params, headers=headers)
                resp.encoding = "utf-8"
                text = resp.text
        except httpx.RequestError as e:
            logger.warning("基金持仓 API (%s) 请求失败 %s: %s", api_type, code, e)
            continue

        # 解析 JavaScript 响应：
        #   var apidata={ content:"...HTML...", arryear:["2026"], curyear:"2026" };
        m = re.search(r'content\s*:\s*"(.+?)"\s*,\s*arryear', text, re.DOTALL)
        if not m:
            logger.debug("基金持仓 API (%s) 未找到 content 字段: %s", api_type, code)
            continue

        raw_content = m.group(1)
        if not raw_content or raw_content.isspace():
            logger.debug("基金持仓 API (%s) 内容为空: %s", api_type, code)
            continue

        # json.loads 正确解析 JS 字符串转义（\uXXXX, \" 等）
        try:
            html_content = json.loads('"' + raw_content + '"')
        except json.JSONDecodeError:
            logger.warning("基金持仓 API (%s) JS 字符串解析失败: %s", api_type, code)
            continue

        # 提取基金名称
        if not fund_name:
            # 优先从 title 属性取（完整名称），否则从 <a> 标签文本取
            name_match = re.search(r'<a\s+title=[\'"]([^\'"]+)[\'"]', html_content)
            if name_match:
                fund_name = name_match.group(1).strip()
            else:
                name_match = re.search(r'<a\s+href=[\'"][^\'"]+[\'"]>([^<]+)</a>', html_content)
                if name_match:
                    fund_name = name_match.group(1).strip()

        # 提取报告日期
        if not report_date:
            date_match = re.search(r"截止至[：:].*?(\d{4}-\d{2}-\d{2})", html_content)
            if date_match:
                report_date = date_match.group(1)

        # 找到第一个表格（最新一个季度的持仓）
        table_match = re.search(
            r"<table[^>]*>(.*?)</table>", html_content, re.DOTALL | re.IGNORECASE
        )
        if not table_match:
            continue

        table_html = table_match.group(1)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)

        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(cells) < 4:
                continue

            # td[1] = 股票/债券代码
            code_cell = cells[1]
            code_a = re.search(r"<a[^>]*>(.*?)</a>", code_cell)
            stock_code = (
                code_a.group(1).strip()
                if code_a
                else re.sub(r"<[^>]+>", "", code_cell).strip()
            )

            # td[2] = 股票/债券名称
            name_cell = cells[2]
            name_a = re.search(r"<a[^>]*>(.*?)</a>", name_cell)
            stock_name = (
                name_a.group(1).strip()
                if name_a
                else re.sub(r"<[^>]+>", "", name_cell).strip()
            )

            if not stock_name or not stock_code:
                continue

            # 搜索含 % 的单元格（占净值比例）
            ratio = 0.0
            for cell in cells:
                pct_match = re.search(r"(\d+\.?\d*)%", cell)
                if pct_match:
                    ratio = _safe_float(pct_match.group(1))
                    break

            if ratio > 0:
                all_holdings.append({
                    "name": stock_name,
                    "code": stock_code,
                    "ratio": ratio,
                })

        if all_holdings:
            break  # 已有持仓数据，无需尝试其它类型

    if not all_holdings:
        logger.info("基金持仓 API 全部类型无有效持仓: %s", code)
        return None

    logger.info(
        "基金持仓 API %s（%s）: %d 条持仓, 报告期 %s",
        fund_name or code,
        code,
        len(all_holdings),
        report_date or "未知",
    )
    return {
        "code": code.strip(),
        "name": fund_name,
        "date": report_date,
        "holdings": all_holdings,
    }


# ── 基金业绩排名（同类排名 + 区间收益） ──────────────────


def fetch_fund_rankings(code: str) -> dict[str, Any] | None:
    """获取基金同类排名和区间收益率。

    API: fund.eastmoney.com/pingzhongdata/{code}.js
    从 JS 变量 Data_rateInSimilarType（排名）和 Data_rateInSimilarPersent（百分位）提取。

    Args:
        code: 6 位基金代码

    Returns:
        {
            "code": 基金代码,
            "name": 基金名称,
            "type": 基金类型,
            "rankings": {
                "同类排名": {"rank": "231", "total": "1075", "percentile": "78.51"},
            },
            "rating": "优秀|良好|稳定|偏差"
        }
        None: 获取失败
    """
    url = f"https://fund.eastmoney.com/pingzhongdata/{code.strip()}.js"
    logger.debug("请求基金业绩数据: %s", url)

    try:
        with httpx.Client(timeout=_TIMEOUT, verify=False) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            text = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("基金业绩 API 请求失败 %s: %s", code, e)
        return None

    # 解析基金名称
    name = ""
    name_match = re.search(r'var\s+fS_name\s*=\s*"([^"]*)"', text)
    if name_match:
        name = name_match.group(1)

    # 解析各区间收益率（从 syl_* 变量）
    # syl_1y = 近1月, syl_3y = 近3月, syl_6y = 近6月, syl_1n = 近1年
    period_map = {
        "近1月": "syl_1y",
        "近3月": "syl_3y",
        "近6月": "syl_6y",
        "近1年": "syl_1n",
    }
    rankings: dict[str, dict[str, Any]] = {}
    for period, var_name in period_map.items():
        m = re.search(rf"var\s+{var_name}\s*=\s*\"?(-?[\d.]+)", text)
        if m:
            val = _safe_float(m.group(1))
            rankings[period] = {"return": val}

    # 解析同类排名（Data_rateInSimilarType）
    rank_entry: dict[str, Any] = {"rank": "--", "total": "--", "percentile": "--"}
    rank_match = re.search(r"var Data_rateInSimilarType\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if rank_match:
        try:
            rank_data = json.loads(rank_match.group(1))
            if rank_data:
                last = rank_data[-1]
                rank_entry["rank"] = str(last.get("y", "--"))
                rank_entry["total"] = str(last.get("sc", "--"))
        except (json.JSONDecodeError, IndexError, TypeError):
            pass

    # 解析排名百分位（Data_rateInSimilarPersent）
    pct_match = re.search(r"var Data_rateInSimilarPersent\s*=\s*(\[.*?\]);", text, re.DOTALL)
    if pct_match:
        try:
            pct_data = json.loads(pct_match.group(1))
            if pct_data:
                last_pct = pct_data[-1]
                if isinstance(last_pct, list) and len(last_pct) >= 2:
                    rank_entry["percentile"] = str(round(last_pct[1], 2))
        except (json.JSONDecodeError, IndexError, TypeError):
            pass

    if rank_entry.get("rank") != "--" or rank_entry.get("percentile") != "--":
        rankings["同类排名"] = rank_entry

    # 计算评级
    rating = ""
    if rank_entry.get("percentile", "--") != "--":
        try:
            pct_val = float(rank_entry["percentile"]) / 100.0
            if pct_val <= 0.20:
                rating = "优秀"
            elif pct_val <= 0.30:
                rating = "良好"
            elif pct_val <= 0.50:
                rating = "稳定"
            else:
                rating = "偏差"
        except (ValueError, TypeError):
            pass
    elif rank_entry.get("rank", "--") != "--" and rank_entry.get("total", "--") != "--":
        try:
            pct_val = int(rank_entry["rank"]) / int(rank_entry["total"])
            if pct_val <= 0.20:
                rating = "优秀"
            elif pct_val <= 0.30:
                rating = "良好"
            elif pct_val <= 0.50:
                rating = "稳定"
            else:
                rating = "偏差"
        except (ValueError, ZeroDivisionError):
            pass

    # 解析业绩评价数据（Data_performanceEvaluation）
    perf_eval: dict[str, Any] | None = None
    pe_match = re.search(
        r'var Data_performanceEvaluation\s*=\s*(\{[^;]+\});', text, re.DOTALL
    )
    if pe_match:
        try:
            raw = pe_match.group(1)
            perf_eval = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

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


