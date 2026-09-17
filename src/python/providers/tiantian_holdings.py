"""天天基金 API — 基金持仓数据。

职责：
  - 季报 API 取当期持仓（fundf10.eastmoney.com/FundArchivesDatas.aspx）
  - 基金主页面解析前 10 大持仓（fund.eastmoney.com/{code}.html）
  - ETF 联接基金的目标 ETF 解析

取数阶梯（次序即「陈年数据隔离」——判据仍唯一留在报告层时效闸门）：

  第 1 跳  季报接口（年份域，最近完整季度回溯）→ 当期持仓 + 真实报告期
  第 2 跳  基金主页面 → 前十大；报告期不从此处取（页面无可靠来源，
           盲扫会误抓导航/日历控件里的「当天」）。联接基金在此带回目标 ETF
  第 3 跳  季报接口（无年份兜底）→ 最早可得报告，通常已陈旧

把无年份兜底压到第 3 跳、且仅在「第 2 跳找不到目标 ETF 锚点」时到达，
使其无法遮蔽联接基金；同时避免在取数层复制报告期时效判据。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from src.python.core.code_utils import is_exchange_fund_code, is_index_link_by_name
from src.python.providers.tiantian_base import (
    _request_fund_html,
    _request_quarterly_api,
    _safe_float,
)

logger = logging.getLogger("invest")

_QUARTER_LOOKBACK = 4
"""季报年份域回溯的完整季度数。

取值 4（约一年）：定期报告法定披露不晚于报告期结束后 15 个工作日，QDII 因
境外市场休市与结算安排常更晚；回溯 4 个季度足以越过披露延迟，覆盖仅按年
披露的品种（年报落在最近 4 个完整季度内），又不至于把陈年报告当作「当期」。
超过一年的历史报告由第 3 跳的兜底请求承担，并交由报告层时效闸门裁决。
"""

_FEEDER_TARGET_PATTERN = re.compile(
    r"""href=["']https?://fund\.eastmoney\.com/(\d{6})\.html["'][^>]*>\s*查看相关ETF(?!联)""",
)
"""联接基金主页面中指向目标 ETF 的锚点。

实测两个方向（`2026-09-11`）：

===========  ==================================================  ==============
页面类型      锚点                                                指向
===========  ==================================================  ==============
联接基金       ``…>查看相关ETF></a>``（标签止于 ETF）             目标 ETF，场内代码
常规 ETF       ``…>查看相关ETF联接></a>``（标签多「联接」二字）    该 ETF 的联接基金，场外代码
===========  ==================================================  ==============

两个方向**互为反向**，只看「有没有这个链接」必然误判。故做两重区分：

1. 标签必须**止于「ETF」**（``(?!联)``）——「查看相关ETF联接」是常规 ETF 回指其
   联接基金的反向链接，且 ``查看相关ETF`` 是它的前缀，不加否定前瞻会一并命中；
2. 目标须为**场内**代码（:func:`is_exchange_fund_code`）——目标 ETF 按定义场内交易，
   而反向链接指向的场外联接基金代码前缀不为 5/1。

实测：``561910``（电池ETF招商）的锚点标签为「查看相关ETF联接」且指向 ``016019``，
两重区分各自都能挡下；``016055`` 的锚点标签止于「ETF」且指向 ``513390``，正常命中。

调用方仍须先经 :func:`is_index_link_by_name` 过滤名称——本函数只回答「页面上写着
哪个 ETF」，不回答「本基金是不是联接基金」。
"""


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


def _extract_fund_name(html: str) -> str:
    """从基金主页 HTML 提取基金名称。

    报告期**不在此处提取**：主页没有带语义标注的报告期字段，此前按字节窗口
    盲扫（``html[2000:5000]``）既几乎不命中（实测 10 只基金 0 命中），又可能
    命中导航/日历控件里的当天日期——比空值更危险。报告期只从季报接口取。
    """
    title_match = re.search(r"<title>(.*?)[\(（]", html)
    return title_match.group(1).strip() if title_match else ""


def parse_feeder_target_etf(html: str, self_code: str) -> str | None:
    """从联接基金主页面解析其目标 ETF 代码。

    联接基金的资产就是目标 ETF、本身不持有股票，故其季报股票表为空；其底层
    暴露取自目标 ETF 的持仓。目标 ETF 代码由页面锚点**动态解析**，不维护
    「联接基金 → 目标 ETF」映射表——基金公司更换标的 ETF 时映射表会静默失效，
    而锚点随页面同步更新。

    两类页面的「相关」链接互为反向（见 :data:`_FEEDER_TARGET_PATTERN`），故本函数
    需先以标签形态与场内代码两重区分，再由调用方以 :func:`is_index_link_by_name`
    过滤名称——本函数只回答「页面上写着哪个目标 ETF」，不回答「本基金是不是联接基金」。

    Args:
        html: 基金主页面 HTML
        self_code: 本基金代码（用于排除锚点指向自身的情形）

    Returns:
        目标 ETF 代码；反向链接、非场内代码、指向自身或未找到时返回 None
    """
    match = _FEEDER_TARGET_PATTERN.search(html)
    if not match:
        return None
    target = match.group(1)
    if target == self_code.strip() or not is_exchange_fund_code(target):
        return None
    return target


def fetch_fund_holdings(code: str) -> dict[str, Any] | None:
    """获取一只基金的底层持仓（取数阶梯见模块文档）。

    Args:
        code: 6 位基金代码

    Returns:
        {
            "code": 基金代码,
            "name": 基金名称,
            "date": 报告期 (YYYY-MM-DD)；第 2 跳结果为空字符串，
            "holdings": [{"name", "code", "ratio"}, ...],
            "feeder_target_code": 目标 ETF 代码（仅联接基金在第 2 跳返回）
        }
        None: 请求失败
    """
    # ── 第 1 跳：季报接口（年份域）—— 唯一携带真实报告期的通道 ──
    dated = _fetch_dated_quarterly(code)
    if dated is not None:
        return dated

    # ── 第 2 跳：基金主页面（前十大） ──
    html = _request_fund_html(code)
    if html is None:
        return None
    fund_name = _extract_fund_name(html)

    # 联接基金：本页面不产出持仓（其资产即目标 ETF），带回目标 ETF 标识，
    # 由 fetcher 层作为一次独立取数去抓目标 ETF 的持仓
    if is_index_link_by_name(fund_name):
        target_code = parse_feeder_target_etf(html, code)
        if target_code:
            logger.info("基金 %s（%s）为联接基金，底层资产在目标 ETF %s", fund_name, code, target_code)
            return {
                "code": code.strip(),
                "name": fund_name,
                "date": "",
                "holdings": [],
                "feeder_target_code": target_code,
            }

    holdings_table = _find_holdings_table(html)
    holdings = _parse_holdings_rows(holdings_table) if holdings_table else []
    if holdings:
        logger.info("基金 %s（%s）: 主页面解析到 %d 条持仓", fund_name or code, code, len(holdings))
        return {"code": code.strip(), "name": fund_name, "date": "", "holdings": holdings}

    # ── 第 3 跳：季报接口（无年份兜底）—— 最早可得报告，通常已陈旧 ──
    legacy = _fetch_legacy_quarterly(code)
    if legacy is not None:
        return legacy

    logger.info("基金 %s（%s）: 三跳均无持仓数据", fund_name or code, code)
    return {"code": code.strip(), "name": fund_name, "date": "", "holdings": []}


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


def _fetch_dated_quarterly(code: str) -> dict[str, Any] | None:
    """第 1 跳：按最近完整季度从新到旧回溯（年份域），取当期报告。

    API: fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}&year={year}&month={month}
    返回 JavaScript 变量 apidata.content，内含按报告期分区的 HTML 持仓表格；
    首表即最新分区，其「截止至」标注紧随该表，故取首表 + 取首个截止至是自洽的。
    """
    for year, month in _recent_quarters(_QUARTER_LOOKBACK):
        result = _fetch_single_quarter(code, year, month)
        if result is not None:
            return result
    return None


def _fetch_legacy_quarterly(code: str) -> dict[str, Any] | None:
    """第 3 跳：不指定年份的默认请求。

    返回的是**最早可得**报告而非最新，故通常已陈旧；本函数不做时效判定
    （判据唯一归属报告层时效闸门），仅作为「当期与前一期均无数据」时的
    诊断性兜底，供报告层标注「报告期 X，距今 N 个完整季度」。
    """
    logger.info("基金持仓 API %s: 年份域回溯无持仓，尝试默认请求...", code)
    result = _fetch_single_quarter(code)
    if result is not None:
        logger.info("基金持仓 API %s 默认请求成功（报告期 %s）", code, result.get("date", "未知"))
    return result


def fetch_quarterly_holdings(code: str) -> dict[str, Any] | None:
    """从东方财富基金持仓 API 获取基金持仓（年份域回溯 → 无年份兜底）。

    保留「回溯 + 兜底」的完整语义：调用方（录制回放校验、离线用例）依赖
    该公开契约。取数阶梯内部则分别调用两个单跳函数，以便把兜底降到第 3 跳。

    Args:
        code: 6 位基金代码

    Returns:
        同 fetch_fund_holdings，或 None
    """
    dated = _fetch_dated_quarterly(code)
    if dated is not None:
        return dated
    legacy = _fetch_legacy_quarterly(code)
    if legacy is None:
        logger.info("基金持仓 API 全部无有效持仓: %s", code)
    return legacy


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
