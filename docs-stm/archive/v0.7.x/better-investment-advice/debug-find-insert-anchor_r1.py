#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试脚本：在 discussion-better-investment-advice.md 中定位 Round 1 插入锚点。
合并自原有 debug.py / debug2.py / debug3.py / debug4.py，按策略优先级依次尝试。
"""
import sys

DOC = "D:/path/to/investor-util/docs-stm/plan/discussion-better-investment-advice.md"

def try_text_strategies():
    """文本模式打开，多策略搜索"""
    with open(DOC, "r", encoding="utf-8") as f:
        content = f.read()

    results = []

    # 策略 a: 搜索 ``` + --- 分隔区域
    idx = content.find('```\n\n---')
    results.append(("a: ```---", idx, None if idx < 0 else content[idx:idx+150]))

    # 策略 b: 搜索 \n## 3.
    idx = content.find('\n## 3.')
    results.append(("b: \\n##3.", idx, None if idx < 0 else content[idx:idx+60]))

    # 策略 c: 精确搜索 section 3 标题
    idx = content.find('## 3. 最终版综合建议')
    results.append(("c: section3标题", idx, None if idx < 0 else (content[idx:idx+50], content[idx-100:idx])))

    # 策略 d: 在 section 3 前找 --- 分隔界标
    idx_sec3 = content.find('## 3. 最终版综合建议')
    if idx_sec3 >= 0:
        idx_sep = content.rfind('---\n\n\n', 0, idx_sec3)
        results.append(("d: --- 分隔(sec3前)", idx_sep, None if idx_sep < 0 else content[idx_sep:idx_sep+50]))

    # 策略 e: 搜索双 --- 模式
    idx = content.find('---\n\n\n\n---')
    results.append(("e: 双---", idx, None if idx < 0 else content[idx:idx+60]))

    return results

def try_binary_strategies():
    """二进制模式打开，处理不同换行符"""
    with open(DOC, "rb") as f:
        data = f.read()

    results = []

    # 策略 f: 二进制搜索 b'## 3'
    idx = data.find(b'## 3')
    results.append(("f: binary ##3", idx, None if idx < 0 else (data[idx-5:idx+30].hex(" "), data[idx-5:idx+30].decode("utf-8", "replace"))))

    # 策略 g: 二进制搜索 b'## 3. '
    idx = data.find(b'## 3. ')
    results.append(("g: binary ##3.", idx, None if idx < 0 else data[idx:idx+60].decode("utf-8", "replace")))

    # 策略 h: 二进制搜索 b'```\n\n---' (LF)
    idx = data.find(b'```\n\n---')
    results.append(("h: binary ```---(LF)", idx, None if idx < 0 else data[idx:idx+60].decode("utf-8", "replace")))

    # 策略 i: 二进制搜索 b'```\r\n\r\n---' (CRLF)
    idx = data.find(b'```\r\n\r\n---')
    results.append(("i: binary ```---(CRLF)", idx, None if idx < 0 else data[idx:idx+60].decode("utf-8", "replace")))

    return results

def main():
    print(f"=== 锚点定位报告 ===")
    print(f"文档: {DOC}")
    print()

    for name, idx, ctx in try_text_strategies() + try_binary_strategies():
        status = "✅" if idx >= 0 else "❌"
        print(f"{status} [{name}] position={idx}")
        if ctx is not None:
            if isinstance(ctx, tuple):
                for item in ctx:
                    print(f"    {item[:120]}")
            else:
                print(f"    {ctx[:120]}")
        print()

    sys.exit(0 if any(r[1] >= 0 for r in try_text_strategies() + try_binary_strategies()) else 1)

if __name__ == "__main__":
    main()
