#!/usr/bin/env python3
"""东方财富 push2 连通性诊断 — 区分「程序缺陷」与「网络环境拦截」。

背景：部分电脑运行报告时频繁出现 push2 "Server disconnected without
sending a response"（服务器接受 TCP 连接但未返回响应即断开），触发
熔断退避（60s→300s→900s→3600s）后降级到 eastmoney_industry_rest 备用链路。
本脚本用于在这些电脑上快速定位根因，决定是否需要调整代码。

用法：
  python scripts/probe-push2.py            # 默认探测 3 次

输出：
  每次请求的耗时与结果 + 汇总成功数。

判读：
  A. 三次全部成功 → 网络正常，之前失败为临时抖动/时段性，无需改动
  B. 三次全失败、且下述 curl 对照也失败 → 网络/防火墙/代理拦截 push2，
     属环境问题（B 方案 curl_cffi 指纹大概率无效，可考虑加速降级）
  C. 脚本失败、curl 对照成功 → httpx/TLS 指纹被 WAF 拦截，
     B 方案（curl_cffi 浏览器指纹）才有价值

curl 对照命令（在出问题电脑上执行，测 TLS 指纹是否被 WAF 拦截）：
  curl -s "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f58"

说明：
  - 纯只读探测，不写缓存文件、不写熔断/降级记录，无副作用。
"""

import time

import httpx

_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_PARAMS = {"secid": "1.000001", "fields": "f57,f58,f127,f128,f129"}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}
_TIMEOUT = 5.0
_PROBES = 3


def _probe_once(index: int) -> tuple[bool, str]:
    """执行单次 push2 请求，返回 (是否成功, 描述)。"""
    t0 = time.time()
    try:
        with httpx.Client(timeout=_TIMEOUT, verify=True) as client:
            resp = client.get(_URL, params=_PARAMS, headers=_HEADERS)
        dt = (time.time() - t0) * 1000
        content_type = resp.headers.get("content-type", "")
        data = resp.json().get("data") if content_type.startswith("application/json") else None
        if resp.status_code == 200 and data:
            return True, f"[{index}] 成功  {dt:.0f}ms  行业={data.get('f127')}"
        return False, f"[{index}] HTTP {resp.status_code}  {dt:.0f}ms  响应非预期（可能被重定向/拦截）"
    except httpx.RemoteProtocolError as e:
        dt = (time.time() - t0) * 1000
        return False, f"[{index}] 断连  {dt:.0f}ms  Server disconnected: {e}"
    except httpx.TimeoutException as e:
        dt = (time.time() - t0) * 1000
        return False, f"[{index}] 超时  {dt:.0f}ms  {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 — 诊断脚本需覆盖所有异常
        dt = (time.time() - t0) * 1000
        return False, f"[{index}] 异常  {dt:.0f}ms  {type(e).__name__}: {e}"


def main() -> None:
    """主入口：连续探测并汇总结果。"""
    print(f"探测 {_URL}")
    print(f"参数: {_PARAMS}")

    ok = 0
    for i in range(_PROBES):
        success, desc = _probe_once(i)
        print(f"  {desc}")
        if success:
            ok += 1

    print(f"\n结果: 成功 {ok}/{_PROBES}")
    print("\n对照: 用 curl 请求同一 URL（测 TLS 指纹是否被 WAF 拦截）")
    print('  curl -s "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f58"')


if __name__ == "__main__":
    main()
