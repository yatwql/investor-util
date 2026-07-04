"""基金经理数据获取模块。

数据来源：fund.eastmoney.com/{code}.html（HTML 解析）
         优先与穿透模块合并请求（同一个页面可同时提取经理+持仓）
缓存前缀：fund_manager_
TTL：CACHE_DAILY（86400s）

设计原则：
  - parse_manager_from_html 为纯解析函数，供穿透模块在已获取的 HTML 上顺带调用
  - fetch_fund_manager 为完整获取函数（含缓存+回退），供基金经理分析模块独立使用
  - 历史快照使用独立键 fund_manager_snapshot（不受持仓指纹影响），见 fund_manager_analysis.py
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from src.python.cache import get as cache_get, set as cache_set
from src.python.fetcher.fund import _FUND_HOLD_CACHE_PREFIX  # 复用基金持仓的 HTTP 响应
from src.python.http_client import make_http_client

logger = logging.getLogger("invest")

_CACHE_PREFIX = "fund_manager_"
_MANAGER_TTL = 86400  # CACHE_DAILY

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com/",
}
_TIMEOUT = 15.0

# ── HTML 解析 ────────────────────────────────────────────────────


def parse_manager_from_html(html: str) -> dict[str, Any] | None:
    """从基金主页 HTML 纯解析基金经理信息。

    该函数与穿透模块共用同一 HTML 源，不发起新的 HTTP 请求。
    解析 fund.eastmoney.com/{code}.html 中的基金经理信息。

    解析策略：
      1. 优先从基金概要表格 (infoOfFund) 提取当前经理
      2. 回退从页面任意位置匹配基金经理文本

    Args:
        html: fund.eastmoney.com/{code}.html 的完整 HTML 文本

    Returns:
        dict 包含:
          - manager_name: str      当前基金经理姓名（多个经理用"/"分隔）
          - start_date: str        任职起始日（YYYY-MM-DD）或空字符串
          - tenure_days: int       任职天数（0 表示无法计算）
          - history: list[dict]    历任基金经理列表（仅当前页面可提取的信息）
       解析失败返回 None
    """
    if not html or not isinstance(html, str):
        return None

    manager_name = ""
    start_date = ""

    # ── 策略 1：从 infoOfFund 表格提取 ──
    # 表格结构：<div class="infoOfFund">...<td>基金经理</td><td>...<a>经理名</a>...</td>...
    info_match = re.search(
        r'<div[^>]*class="infoOfFund"[^>]*>(.*?)</div>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if info_match:
        info_html = info_match.group(1)
        # 旧格式：基金经理 独立 td → 下一个 td 含名字
        manager_row = re.search(
            r'基金经理\s*</td>\s*<td[^>]*>(.*?)</td>',
            info_html, re.DOTALL | re.IGNORECASE,
        )
        if manager_row:
            cell_html = manager_row.group(1)
            # 提取所有 <a> 标签内的名字（多位经理以链接形式并列）
            names = re.findall(r'<a[^>]*>(.*?)</a>', cell_html)
            if names:
                manager_name = "/".join(n.strip() for n in names if n.strip())
            else:
                # 回退：提取纯文本
                text = re.sub(r'<[^>]+>', '', cell_html).strip()
                if text:
                    manager_name = text.split("（")[0].split("(")[0].strip()

            # 提取任职起始日（旧格式中在与经理名同一 cell）
            date_match = re.search(
                r'任职起始日[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
                cell_html,
            )
            if not date_match:
                date_match = re.search(
                    r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s*至今',
                    cell_html,
                )
            if date_match:
                start_date = date_match.group(1).replace("/", "-")
        else:
            # 新格式：同一 td 内 "基金经理：<a>name</a>"
            new_match = re.search(
                r'基金经理[：:]\s*<a[^>]*>(.*?)</a>',
                info_html,
            )
            if new_match:
                manager_name = new_match.group(1).strip()
            # 新格式 infoOfFund 不含任职起始日，留空由档案页回退补充

    # ── 策略 2：页面文本回退搜索 ──
    if not manager_name:
        # 在全文搜索 "基金经理：" 或 "基金经理 "</td>
        full_match = re.search(
            r'基金经理[：:]\s*([^<>\n]{2,20})',
            html,
        )
        if full_match:
            manager_name = full_match.group(1).strip()

        if not manager_name:
            # 搜索 "基金经理</span>" 模式（移动端或简化版页面）
            mobile_match = re.search(
                r'基金经理</span>\s*<span[^>]*>\s*<a[^>]*>(.*?)</a>',
                html, re.DOTALL,
            )
            if mobile_match:
                manager_name = mobile_match.group(1).strip()

    if not manager_name:
        logger.debug("基金经理解析失败：页面中未找到经理信息")
        return None

    # ── 计算任职天数 ──
    tenure_days = 0
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            tenure_days = (datetime.now() - start).days
        except (ValueError, TypeError):
            tenure_days = 0

    # ── 提取历任经理简要列表（页面中可能含"历任基金经理"） ──
    history: list[dict] = []
    history_section = re.search(
        r'历任基金经理\s*</td>\s*<td[^>]*>(.*?)</td>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if history_section:
        history_html = history_section.group(1)
        # 每个经理可能是 <a> 或纯文本
        hist_items = re.findall(
            r'<a[^>]*>(.*?)</a>\s*[（(](\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            history_html,
        )
        for name, date in hist_items:
            history.append({
                "name": name.strip(),
                "start_date": date.replace("/", "-"),
            })

    result: dict[str, Any] = {
        "manager_name": manager_name,
        "start_date": start_date,
        "tenure_days": tenure_days,
        "history": history,
    }
    logger.debug("基金经理解析完成: %s（任职起始 %s, %d 天）",
                 manager_name, start_date or "未知", tenure_days)
    return result


# ── 独立 HTTP 请求（穿透模块未预先获取 HTML 时使用） ─────────────


def _request_fund_html(code: str) -> str | None:
    """请求基金主页面 HTML（复用 tiantian 的同名函数逻辑）。"""
    url = f"https://fund.eastmoney.com/{code.strip()}.html"
    logger.debug("请求基金经理页面: %s", url)
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            return resp.text
    except httpx.TimeoutException:
        logger.warning("基金经理页面超时: %s", code)
        return None
    except httpx.RequestError as e:
        logger.warning("基金经理页面请求失败 %s: %s", code, e)
        return None


# ── 回退：从档案页解析（当主页解析失败时） ─────────────────────


def _parse_manager_from_archive_page(code: str) -> dict[str, Any] | None:
    """从基金档案页 fundf10.eastmoney.com/jjjl_{code}.html 解析经理信息。

    基金经理明细页包含完整的历任信息，作为主页解析失败时的回退方案。
    实际表格结构（天天基金）：
      <table class="w782 comm jloff">
        <thead><tr><th>起始期</th><th>截止期</th><th>基金经理</th><th>任职期间</th><th>任职回报</th></tr></thead>
        <tbody><tr><td>date</td><td>至今/date</td><td><a>name</a></td><td>tenure</td><td>return</td></tr></tbody>
      </table>
    """
    url = f"https://fundf10.eastmoney.com/jjjl_{code.strip()}.html"
    logger.debug("请求基金经理档案页(回退): %s", url)
    try:
        with make_http_client(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.encoding = "utf-8"
            html = resp.text
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("基金经理档案页请求失败 %s: %s", code, e)
        return None

    # 找到经理信息表格
    # 新格式（天天基金当前）：<table class="w782 comm jloff">
    #   <thead><th>起始期</th>...<th>基金经理</th>...
    #   <tbody><tr><td>date</td><td>至今</td><td><a>name</a></td>...
    table_match = re.search(
        r'<table[^>]*>(.*?起始期.*?基金经理.*?</thead>.*?<tbody>(.*?)</tbody>)',
        html, re.DOTALL | re.IGNORECASE,
    )

    if table_match:
        tbody_html = table_match.group(2)
        # 解析 tbody 中的行
        row_htmls = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_html, re.DOTALL)
    else:
        # 旧格式（回退）：<tr><td><a>name</a></td><td>date</td></tr>
        logger.debug("基金经理档案页未匹配新格式，尝试旧格式行解析: %s", code)
        all_cells = re.findall(
            r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>',
            html, re.DOTALL,
        )
        row_htmls = []
        for name_html, date_html in all_cells:
            name_text = re.sub(r'<[^>]+>', '', name_html).strip()
            date_text = re.sub(r'<[^>]+>', '', date_html).strip()
            # 经理行特征：第二列是日期（不含中文导航文字），第一列是人名
            if re.search(r'\d{4}', date_text) and not re.search(r'[一-鿿]{4,}', date_text):
                row_htmls.append(f"<td>{date_text}</td><td></td><td>{name_html}</td>")

    if not row_htmls:
        logger.debug("基金经理档案页未找到经理行: %s", code)
        return None

    # 取每行的 td
    def _parse_row(row_html: str) -> tuple[str, str]:
        """从经理行提取（起始日期, 经理名）。"""
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
        if len(tds) < 3:
            return ("", "")
        start_td = re.sub(r'<[^>]+>', '', tds[0]).strip()
        name_td = re.sub(r'<[^>]+>', '', tds[2]).strip()
        return (start_td, name_td)

    # 第一行 = 当前经理
    first_start, first_name = _parse_row(row_htmls[0])

    # 提取日期
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', first_start)
    start_date = date_match.group(1).replace("/", "-") if date_match else ""

    tenure_days = 0
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            tenure_days = (datetime.now() - start).days
        except (ValueError, TypeError):
            pass

    # 历任经理（从第二行起）
    history: list[dict] = []
    for row in row_htmls[1:]:
        h_start, h_name = _parse_row(row)
        h_date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', h_start)
        if h_name and h_date_match:
            history.append({
                "name": h_name,
                "start_date": h_date_match.group(1).replace("/", "-"),
            })

    result: dict[str, Any] = {
        "manager_name": first_name,
        "start_date": start_date,
        "tenure_days": tenure_days,
        "history": history,
    }
    logger.debug("基金经理档案页解析完成: %s", first_name)
    return result


# ── 公开接口 ─────────────────────────────────────────────────────


def fetch_fund_manager(code: str) -> dict[str, Any] | None:
    """获取基金经理信息（含缓存+回退）。

    先查缓存（fund_manager_{code}.json），命中直接返回；
    未命中则请求 fund.eastmoney.com/{code}.html 并解析；
    主页解析失败时回退到档案页。

    注意：穿透模块在调用 fetch_fund_holdings 后已获取同一 HTML，
    应优先调用 parse_manager_from_html(html) 而非本函数，
    避免重复 HTTP 请求。

    Args:
        code: 6 位基金代码

    Returns:
        dict 包含:
          - manager_name: str      当前基金经理姓名
          - start_date: str        任职起始日（YYYY-MM-DD）
          - tenure_days: int       任职天数
          - history: list[dict]    历任基金经理列表
        解析失败返回 None
    """
    code = code.strip()
    cache_key = _CACHE_PREFIX + code

    # 读缓存
    cached = cache_get(cache_key, _MANAGER_TTL)
    if cached is not None:
        return cached

    # 主页面解析
    html = _request_fund_html(code)
    if html:
        result = parse_manager_from_html(html)
        if result:
            cache_set(cache_key, result)
            return result
        logger.debug("基金经理主页解析失败 [%s]，尝试档案页回退", code)
    else:
        logger.debug("基金经理主页请求失败 [%s]，尝试档案页回退", code)

    # 档案页回退
    result = _parse_manager_from_archive_page(code)
    if result:
        cache_set(cache_key, result)
        return result

    logger.warning("基金经理全部解析失败 [%s]", code)
    return None
