"""数据源健康检查 — 逐个测试各数据源联通性并报告延迟。

用法:
  python -m src.python.cli check-sources

输出格式:
  ✅/⚠️/❌ 数据源名   用途   延迟   状态说明
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from src.python.http_client import make_http_client
from src.python.logger import setup_logger

logger = setup_logger()

# ── 显示符号（自动降级：非 UTF-8 终端使用 ASCII 替代） ──

import sys

_USE_ASCII = sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8")

_OK = "[V]" if _USE_ASCII else "✅"
_WARN = "[!]" if _USE_ASCII else "⚠️"
_ERR = "[X]" if _USE_ASCII else "❌"
_SKIP = "[-]" if _USE_ASCII else "⏭️"


def _colored(text: str, ok: bool, warn: bool = False) -> str:
    """简易颜色标记。终端不支持 ANSI 时自动降级纯文本。"""
    if _USE_ASCII:
        return text
    try:
        if ok:
            return f"\033[32m{text}\033[0m"
        if warn:
            return f"\033[33m{text}\033[0m"
        return f"\033[31m{text}\033[0m"
    except (UnicodeEncodeError, OSError):
        return text


def _check_http(
    name: str,
    label: str,
    url: str,
    *,
    timeout: float = 15.0,
    expect_status: int = 200,
    **kwargs,
) -> tuple[str, float, str]:
    """通用 HTTP 健康检查。

    Returns:
        (符号, 延迟(ms), 状态说明)
    """
    start = time.perf_counter()
    try:
        client = make_http_client(timeout=timeout, **kwargs)
        resp = client.get(url)
        elapsed = (time.perf_counter() - start) * 1000
        if resp.status_code == expect_status:
            return _OK, elapsed, f"{elapsed:.0f}ms 正常"
        return _WARN, elapsed, f"{elapsed:.0f}ms HTTP {resp.status_code}"
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        err_msg = str(e).split("\n")[0][:60]
        return _ERR, elapsed, f"超时" if "timeout" in str(e).lower() else err_msg


# ── 检查项定义 ──────────────────────────────────────────

_checks: list[tuple[str, str, Callable[[], tuple[str, float, str]]]] = [
    (
        "腾讯财经",
        "行情",
        lambda: _check_http("腾讯财经", "行情", "http://qt.gtimg.cn/q=sz000001", timeout=15),
    ),
    (
        "新浪财经",
        "行情",
        lambda: _check_http(
            "新浪财经",
            "行情",
            "http://hq.sinajs.cn/list=sh000001",
            timeout=15,
            headers={"Referer": "https://finance.sina.com.cn"},
        ),
    ),
    (
        "东方财富",
        "基金净值",
        lambda: _check_http(
            "东方财富",
            "基金净值",
            "http://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=000001&pageIndex=1&pageSize=1",
            timeout=15,
        ),
    ),
    (
        "天天基金",
        "持仓/排名",
        lambda: _check_http(
            "天天基金",
            "持仓/排名",
            "http://fund.eastmoney.com/pingzhongdata/000001.js",
            timeout=15,
        ),
    ),
    (
        "东方财富行业",
        "行业分类",
        lambda: _check_http(
            "东方财富行业",
            "行业分类",
            "http://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f12,f14,f137,f138",
            timeout=5,
        ),
    ),
    (
        "新浪新闻",
        "财经新闻",
        lambda: _check_http(
            "新浪新闻",
            "财经新闻",
            "http://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=1",
            timeout=15,
        ),
    ),
    (
        "东方财富新闻",
        "财经新闻",
        lambda: _check_http(
            "东方财富新闻",
            "财经新闻",
            "http://np-weblist.eastmoney.com/comm/web/getFastNewsList?pageSize=1",
            timeout=15,
        ),
    ),
    (
        "华尔街见闻",
        "财经新闻",
        lambda: _check_http(
            "华尔街见闻",
            "财经新闻",
            "http://api-one.wallstcn.com/apiv1/content/lives?limit=1",
            timeout=15,
        ),
    ),
    (
        "财联社",
        "财经新闻",
        lambda: _check_http(
            "财联社",
            "财经新闻",
            "http://www.cls.cn/v1/roll/get_roll_list?rn=1",
            timeout=15,
        ),
    ),
    (
        "腾讯K线",
        "历史行情",
        lambda: _check_http(
            "腾讯K线",
            "历史行情",
            "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,1",
            timeout=30,
        ),
    ),
]


def run_check_sources() -> None:
    """执行全量数据源健康检查并打印结果。"""
    from datetime import date

    print(f"\n数据源健康检查结果 ({date.today()})")
    print("─" * 55)
    print(f"  {'状态':<4} {'数据源':<14} {'用途':<12} {'延迟':>8}  说明")
    print("─" * 55)

    ok_count = 0
    warn_count = 0
    err_count = 0

    for name, label, check_fn in _checks:
        symbol, elapsed, msg = check_fn()
        if symbol == _OK:
            ok_count += 1
        elif symbol == _WARN:
            warn_count += 1
        else:
            err_count += 1

        color = "green" if symbol == _OK else ("yellow" if symbol == _WARN else "red")
        elapsed_str = f"{elapsed:>7.0f}ms" if elapsed >= 0 else "       -"
        print(f"  {symbol}  {name:<12} {label:<10} {elapsed_str:>8}  {msg}")

    print("─" * 55)
    status_color = "green" if err_count == 0 else ("yellow" if warn_count > 0 else "red")
    total = ok_count + warn_count + err_count
    print(f"  {total} 个数据源 — {_OK} {ok_count} / {_WARN} {warn_count} / {_ERR} {err_count}")
    print()

    # 返回退出码
    if err_count > 0:
        sys.exit(2)
    if warn_count > 0:
        sys.exit(1)
    sys.exit(0)
