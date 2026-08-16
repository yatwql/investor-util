#!/usr/bin/env python3
"""从 pytest-html 报告中提取失败/错误测试用例的详细信息。

用法：
  python scripts/extract-test-failures.py              # 读取 test-reports/latest/all/report.html
  python scripts/extract-test-failures.py path/to/report.html  # 指定报告路径
  python scripts/extract-test-failures.py --summary    # 仅输出汇总（不打印每条日志）
  python scripts/extract-test-failures.py --json       # 输出 JSON 格式
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any


def _find_json_blob(html: str) -> str | None:
    """在 pytest-html 报告 HTML 中找到 data-jsonblob 属性的值。

    JSON blob 是单一 HTML 属性值：属性起始引号到下一个裸引号之间即为
    完整 JSON（blob 内所有 JSON 引号都被 pytest-html 转义为 HTML 实体
    ``&#34;``，不会出现裸引号提前终止属性）。取到后统一解码实体。
    """
    idx = html.find("data-jsonblob=")
    if idx < 0:
        return None

    start = html.index('"', idx) + 1
    end = html.find('"', start)
    if end < 0:
        return None

    raw = html[start:end]
    raw = raw.replace("&#34;", '"').replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return raw


def _extract_log_text(info: dict) -> str:
    """从测试用例信息中提取日志文本。"""
    extras = info.get("extras", [])
    texts: list[str] = []
    for ext in extras:
        for content in ext.get("content", []):
            if isinstance(content.get("log"), str):
                texts.append(content["log"])
    return "\n".join(texts)


def _extract_log_from_html(html: str, test_id: str) -> str:
    """后备方案：从 HTML 中直接搜索测试用例的日志段落。

    pytest-html 的 log 有时只存在于外部 HTML 结构中。
    """
    # 尝试匹配 <div class="log">...</div> 在包含 test_id 的区域附近
    escaped = re.escape(test_id)
    m = re.search(r'<div\s+class="log"[^>]*>.*?' + escaped + r".*?</pre>\s*</div>", html, re.DOTALL)
    if m:
        # 提取 <pre> 中的内容
        pre = re.search(r"<pre[^>]*>(.*?)</pre>", m.group(0), re.DOTALL)
        if pre:
            text = pre.group(1)
            text = text.replace("&#34;", '"').replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
            text = re.sub(r"<[^>]+>", "", text)
            return text.strip()
    return ""


def parse_report(report_path: str) -> dict[str, Any]:
    """解析 pytest-html 报告，返回结构化结果。

    Returns:
        {
            "summary": {"total": int, "passed": int, "failed": int, "errors": int, "skipped": int},
            "failures": [{"test_id": str, "result": str, "log": str, "duration": str}, ...]
        }
    """
    with open(report_path, encoding="utf-8") as f:
        html = f.read()

    raw_json = _find_json_blob(html)
    if raw_json is None:
        raise ValueError("未在报告中找到 data-jsonblob，请确认是 pytest-html 生成的报告。")

    data = json.loads(raw_json)
    tests = data.get("tests", {})

    total = len(tests)
    passed = errors = failed = skipped = 0
    failures: list[dict[str, Any]] = []

    for tid in sorted(tests):
        info = tests[tid]
        if not info:
            continue
        result = info[0].get("result", "Unknown")
        duration = info[0].get("duration", "")
        if result == "Passed":
            passed += 1
        elif result == "Failed":
            failed += 1
            log = _extract_log_text(info[0])
            if not log:
                log = _extract_log_from_html(html, tid)
            failures.append({"test_id": tid, "result": result, "log": log, "duration": duration})
        elif result == "Error":
            errors += 1
            log = _extract_log_text(info[0])
            if not log:
                log = _extract_log_from_html(html, tid)
            failures.append({"test_id": tid, "result": result, "log": log, "duration": duration})
        elif result == "Skipped":
            skipped += 1
        else:
            # xfailed, xpassed etc. - count as passed for summary purposes
            if result in ("xfailed", "xpassed"):
                passed += 1
            else:
                passed += 1

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
        },
        "failures": failures,
    }


def print_report(result: dict[str, Any], detail: bool = True) -> None:
    """打印报告到 stdout。"""
    s = result["summary"]
    total = s["total"]
    ok = s["passed"]
    nf = s["failed"]
    ne = s["errors"]
    sk = s["skipped"]

    print("=== 测试报告汇总 ===")
    print(f"  总计: {total}  |  通过: {ok}  |  失败: {nf}  |  错误: {ne}  |  跳过: {sk}")
    print()

    if not result["failures"]:
        print("[OK] 无失败或错误")
        return

    for f in result["failures"]:
        symbol = "ERR" if f["result"] == "Error" else "FAIL"
        print(f"[{symbol}] {f['test_id']}")
        if detail and f["log"]:
            # 截取关键部分（最后 500 字符通常包含错误堆栈）
            log = f["log"][-500:] if len(f["log"]) > 500 else f["log"]
            # 缩进显示
            for line in log.split("\n"):
                if line.strip():
                    print(f"  {line.strip()}")
        print()


def print_json(result: dict[str, Any]) -> None:
    """输出 JSON 格式。"""
    # 限制日志长度避免过大
    for f in result["failures"]:
        if len(f["log"]) > 1000:
            f["log"] = f["log"][-1000:]
    print(json.dumps(result, ensure_ascii=False, indent=2))


def resolve_report_path(path_arg: str | None) -> str:
    """解析报告路径，支持快捷方式。"""
    if path_arg:
        return os.path.abspath(path_arg)

    candidates = [
        "test-reports/latest/all/report.html",
        "test-reports/latest/report.html",
    ]
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根
    for rel in candidates:
        full = os.path.join(base, rel)
        if os.path.exists(full):
            return full

    print("[ERR] 未找到测试报告，请指定路径", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 pytest-html 报告中提取失败/错误测试用例",
    )
    parser.add_argument("path", nargs="?", default=None, help="report.html 路径（默认自动查找 test-reports/latest/）")
    parser.add_argument("--summary", action="store_true", help="仅输出汇总统计")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    report_path = resolve_report_path(args.path)
    result = parse_report(report_path)

    if args.json:
        print_json(result)
    else:
        print_report(result, detail=not args.summary)


if __name__ == "__main__":
    main()
