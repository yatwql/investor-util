"""数据源健康检查 — 逐个测试各数据源联通性并报告延迟。

用法:
  python -m src.python.cli check-sources

输出格式:
  ✅/⚠️/❌ 数据源名   用途   延迟   状态说明
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable

from src.python.core.http_client import make_http_client
from src.python.core.logger import setup_logger

logger = setup_logger()

# ── 显示符号（自动降级：非 UTF-8 终端使用 ASCII 替代） ──

_USE_ASCII = sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8")

_OK = "[V]" if _USE_ASCII else "✅"
_WARN = "[!]" if _USE_ASCII else "⚠️"
_ERR = "[X]" if _USE_ASCII else "❌"
_SKIP = "[-]" if _USE_ASCII else "⏭️"


def _use_ansi() -> bool:
    """判断是否支持 ANSI 颜色输出。

    同时满足以下条件时返回 True：
    - 未设置 NO_COLOR 环境变量
    - stdout 是终端（非管道重定向）
    - 编码支持 Unicode/ANSI
    """
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return bool(sys.stdout.encoding and sys.stdout.encoding.upper() in ("UTF-8", "UTF8"))


def _colored(text: str, ok: bool, warn: bool = False) -> str:
    """简易颜色标记。终端不支持 ANSI 时自动降级纯文本。"""
    if not _use_ansi():
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
        lambda: _check_http("http://qt.gtimg.cn/q=sz000001", timeout=15),
    ),
    (
        "新浪财经",
        "行情",
        lambda: _check_http(
            "http://hq.sinajs.cn/list=sh000001",
            timeout=15,
            headers={"Referer": "https://finance.sina.com.cn"},
        ),
    ),
    (
        "东方财富",
        "基金净值",
        lambda: _check_http(
            "http://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=000001&pageIndex=1&pageSize=1",
            timeout=15,
        ),
    ),
    (
        "天天基金",
        "持仓/排名",
        lambda: _check_http(
            "http://fund.eastmoney.com/pingzhongdata/000001.js",
            timeout=15,
        ),
    ),
    (
        "东方财富行业",
        "行业分类",
        lambda: _check_http(
            "http://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f12,f14,f137,f138",
            timeout=5,
        ),
    ),
    (
        "新浪新闻",
        "财经新闻",
        lambda: _check_http(
            "http://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=1",
            timeout=15,
        ),
    ),
    (
        "东方财富新闻",
        "财经新闻",
        lambda: _check_http(
            "http://np-weblist.eastmoney.com/comm/web/getFastNewsList?pageSize=1",
            timeout=15,
        ),
    ),
    (
        "华尔街见闻",
        "财经新闻",
        lambda: _check_http(
            "http://api-one.wallstcn.com/apiv1/content/lives?limit=1",
            timeout=15,
        ),
    ),
    (
        "财联社",
        "财经新闻",
        lambda: _check_http(
            "http://www.cls.cn/v1/roll/get_roll_list?rn=1",
            timeout=15,
        ),
    ),
    (
        "腾讯K线",
        "历史行情",
        lambda: _check_http(
            "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,1",
            timeout=30,
        ),
    ),
]


# 代理诊断：当全部数据源同时失败且多数为「连接被拒」时，提示检查本机代理。
# 连接被拒（TCP RST，Windows WinError 10061 / POSIX Errno 111）且 0 成功，
# 几乎总是本机系统代理 / HTTP(S)_PROXY 指向的端口无监听（代理软件未启动）——
# 所有请求被统一路由到死代理。该提示能自愈大多数「全部源异常」的误报。
_PROXY_HINT_NAME = "__proxy_hint__"


def _refused_error(msg: str) -> bool:
    """判断错误消息是否属「连接被拒」类。"""
    m = (msg or "").lower()
    return "10061" in m or "refused" in m


def _with_proxy_hint(results: list[dict]) -> list[dict]:
    """全部失败且多数为连接被拒时，追加代理诊断提示项（返回新列表，不修改入参）。"""
    if not results:
        return results
    if any(r.get("ok") for r in results):
        return results
    refused = sum(1 for r in results if _refused_error(r.get("message", "")))
    if refused < max(1, len(results) // 2):
        return results
    return results + [
        {
            "name": _PROXY_HINT_NAME,
            "label": "网络代理",
            "ok": False,
            "latency_ms": 0.0,
            "message": (
                "多个数据源同时连接被拒：疑似本机系统代理或 HTTP_PROXY/HTTPS_PROXY/"
                "ALL_PROXY 指向的代理未运行。请检查系统代理设置或清除相关环境变量后重试"
            ),
            "hint": True,
        }
    ]


def run_health_checks(max_timeout: float = 15.0) -> list[dict]:
    """执行全量数据源健康检查，返回结构化结果列表。

    Args:
        max_timeout: 整体耗时预算秒数。超过预算即返回已收集的部分结果，
            未完成项标记为"超时"——防止自动检查被慢速/挂起的数据源拖住
            （如 Web 健康接口需在前端 15s abort 前返回，传较短预算 8~12s）。

    Returns:
        列表，每项含：name / label / ok / latency_ms / message
    """
    import threading

    results: list[dict] = []
    results_lock = threading.Lock()

    def _run_check(name: str, label: str, check_fn: Callable) -> None:
        try:
            symbol, elapsed, msg = check_fn()
            item = {
                "name": name,
                "label": label,
                "ok": symbol == _OK,
                "latency_ms": round(elapsed, 1),
                "message": msg,
            }
        except Exception as e:
            item = {
                "name": name,
                "label": label,
                "ok": False,
                "latency_ms": 0.0,
                "message": str(e)[:60],
            }
        with results_lock:
            results.append(item)

    threads = []
    for name, label, fn in _checks:
        # daemon=True：预算超时后主流程可立即返回，挂起线程在后台收尾不阻塞进程退出
        t = threading.Thread(target=_run_check, args=(name, label, fn), daemon=True)
        t.start()
        threads.append(t)

    # 等待全部完成，但受 max_timeout 整体预算约束（预算耗尽即返回部分结果）
    deadline = time.perf_counter() + max_timeout
    for t in threads:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        t.join(timeout=max(0.0, remaining))

    # 预算内未完成的检查项标记为超时（持锁原子判空，避免与迟到的真实结果重复）
    with results_lock:
        done = {r["name"] for r in results}
        for name, label, _fn in _checks:
            if name not in done:
                results.append(
                    {
                        "name": name,
                        "label": label,
                        "ok": False,
                        "latency_ms": 0.0,
                        "message": f"超时（预算 {max_timeout:g}s）",
                    }
                )

    # 预算边界竞态兜底：同 name 保留真实结果，弃"超时"占位
    by_name: dict[str, dict] = {}
    for r in results:
        cur = by_name.get(r["name"])
        if cur is None or (cur["message"].startswith("超时") and not r["message"].startswith("超时")):
            by_name[r["name"]] = r

    # 按 name 排序保证输出稳定
    results = sorted(by_name.values(), key=lambda r: r["name"])
    return _with_proxy_hint(results)


def run_check_sources() -> None:
    """执行全量数据源健康检查并打印结果（CLI 入口）。"""
    from datetime import date

    results = run_health_checks(max_timeout=15.0)
    hint_items = [r for r in results if r.get("hint")]
    results = [r for r in results if not r.get("hint")]

    print(f"\n数据源健康检查结果 ({date.today()})")
    print("─" * 55)
    print(f"  {'状态':<4} {'数据源':<14} {'用途':<12} {'延迟':>8}  说明")
    print("─" * 55)

    ok_count = 0
    warn_count = 0
    err_count = 0

    for r in results:
        if r["ok"]:
            ok_count += 1
        elif "timeout" in r["message"].lower() or "超时" in r["message"]:
            warn_count += 1
        else:
            err_count += 1

        symbol = _OK if r["ok"] else (_WARN if "timeout" in r["message"].lower() else _ERR)
        elapsed_str = f"{r['latency_ms']:>7.0f}ms" if r["latency_ms"] >= 0 else "       -"
        print(f"  {symbol}  {r['name']:<12} {r['label']:<10} {elapsed_str:>8}  {r['message']}")

    print("─" * 55)
    total = ok_count + warn_count + err_count
    print(f"  {total} 个数据源 — {_OK} {ok_count} / {_WARN} {warn_count} / {_ERR} {err_count}")
    if hint_items:
        print(f"  {_WARN} {hint_items[0]['message']}")
    print()

    if err_count > 0:
        sys.exit(2)
    if warn_count > 0:
        sys.exit(1)
    sys.exit(0)
