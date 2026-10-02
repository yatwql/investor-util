#!/usr/bin/env python3
"""连通性/可用性探测统一入口（按 target 分发到 probes/ 子模块）。

背景：数据源报错时需要区分「程序缺陷」与「网络环境/数据源侧停更」——
每个 target 是一个只读探测子模块（probes/<target>.py），**不写缓存文件、
不写熔断/降级记录，无副作用**。

用法（无参数 → 列出全部 target）：
  python scripts/probe.py                    # 列出可用 target
  python scripts/probe.py push2              # 东方财富 push2 连通性
  python scripts/probe.py csi --days 365     # CSI 风格指数可用性（因子分析复核）

新增 target：在 probes/ 下新增模块，实现 `PROBE_TARGET`（名称）、
`build_parser()`（返回 argparse.ArgumentParser，公共开关与选项按需声明）、
`run(args)`（执行探测并返回退出码），在 `__init__.py` 的 `register_targets()`
登记即可——入口无需改动。
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))  # 同目录共享包（probes）

from probes import available_targets, get  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    targets = available_targets()

    if not argv or argv[0] in ("-h", "--help"):
        print("探测统一入口 — 用法: python scripts/probe.py <target> [options…]")
        print(f"可用 target: {', '.join(sorted(targets))}")
        print("各 target 的选项: python scripts/probe.py <target> --help")
        return 0

    name = argv.pop(0)
    if name not in targets:
        print(f"[ERR] 未知 target: {name}（可用: {', '.join(sorted(targets))}）")
        return 2

    module = get(name)
    parser = module.build_parser()
    parser.prog = f"scripts/probe.py {name}"
    args = parser.parse_args(argv)
    rc = module.run(args) or 0
    return rc


if __name__ == "__main__":
    sys.exit(main())
