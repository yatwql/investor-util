#!/usr/bin/env python3
"""定位「顺序依赖」失败：单跑通过、与其它测试一起跑却失败的用例，二分找出污染它的前置测试文件。

典型场景：某 fixture / 模块级 patch 泄漏（如日历注入与离线桩的装配栈序错误），
目标用例单独跑绿、排在泄漏文件之后跑红。手工二分需要 10+ 轮 pytest 往返，
本脚本把候选前缀缩到最小复现集并给出污染源文件与最小复现命令。

用法：
  .venv/bin/python scripts/find-order-dependent-test.py <目标用例节点ID>
  .venv/bin/python scripts/find-order-dependent-test.py <目标> \\
      --candidates "src/test/unit/report/test_event_impact_wiring.py"   # 只在候选内搜（大幅提速）
  .venv/bin/python scripts/find-order-dependent-test.py <目标> --collect-root src/test --max-runs 40

流程：
  1) 单跑目标 → 必须通过（否则非顺序依赖，退出 1）
  2) 收集参考顺序（pytest --collect-only -q）→ 目标之前的文件即候选前缀
  3) 全量候选复现门：candidates + 目标必须让「目标」失败（无关失败则中止，退出 2）
  4) 二分最小前缀 K，再做单文件配对确认；配对不成立则在最小集合内做预算内精简
  5) 输出污染源文件 + 最小复现命令（退出 0）

前置条件：全套除目标外全绿（否则「前置无关失败」会中止并提示）。
退出码：0 = 已定位；1 = 非顺序依赖（单跑即失败）；2 = 无法复现/前置含无关失败/用法错误。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from enum import Enum

_PYTEST_FLAGS = ["-q", "--tb=no", "-rf", "-p", "no:cacheprovider", "--no-header"]
_NODE_LINE = re.compile(r"^(\S+\.py)(?::.*)?$")


class Outcome(Enum):
    """一次 pytest 运行对目标用例的判定结果。"""

    TARGET_FAILED = "target_failed"
    TARGET_PASSED = "target_passed"
    OTHER_FAILURE = "other_failure"
    ERROR = "error"


def parse_collect_order(output: str) -> list[str]:
    """从 ``--collect-only -q`` 输出解析测试文件顺序（首次出现顺序、逐文件去重）。"""
    files: list[str] = []
    seen: set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _NODE_LINE.match(line)
        if not m:
            continue
        path = m.group(1)
        if path not in seen:
            seen.add(path)
            files.append(path)
    return files


def classify_output(returncode: int, output: str, target: str) -> Outcome:
    """按 pytest 返回码与 ``-rf`` 摘要行判定目标用例的结果。"""
    if returncode == 0:
        return Outcome.TARGET_PASSED
    if returncode not in (1,):  # 1 = 有用例失败；其余（2/3/4/5）视为执行错误
        return Outcome.ERROR
    failed_ids: list[str] = []
    for line in output.splitlines():
        m = re.match(r"^(?:FAILED|ERROR)\s+(\S+)", line.strip())
        if m:
            failed_ids.append(m.group(1))
    if not failed_ids:
        # 极旧格式兜底：逐行 `node::test FAILED [xx%]`
        m = re.findall(r"^(\S+\.py::\S+)\s+FAILED", output, re.MULTILINE)
        failed_ids = list(m)
    if any(fid == target or fid.startswith(target) for fid in failed_ids):
        return Outcome.TARGET_FAILED
    if failed_ids:
        return Outcome.OTHER_FAILURE
    return Outcome.ERROR


def run_pytest_case(
    node_ids: Sequence[str],
    target: str,
    *,
    python: str = sys.executable,
    timeout: float = 600.0,
) -> Outcome:
    """以显式文件/node-id 顺序跑一次 pytest，判定目标用例结果。"""
    cmd = [python, "-m", "pytest", *node_ids, *_PYTEST_FLAGS]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return Outcome.ERROR
    return classify_output(proc.returncode, proc.stdout + proc.stderr, target)


def smallest_failing_prefix(
    total: int,
    pred: Callable[[int], bool],
) -> int | None:
    """二分求最小前缀长度 K ∈ [1, total] 使 ``pred(K)`` 为真（假设单调：前缀越长越可能失败）。

    ``pred(total)`` 必须为真（调用方先过复现门）；不成立返回 None。内部记忆化
    ——每次判定对应一次真实 pytest 运行，重复点不重跑。
    """
    if total <= 0:
        return None
    memo: dict[int, bool] = {}

    def fails(k: int) -> bool:
        if k not in memo:
            memo[k] = pred(k)
        return memo[k]

    if not fails(total):
        return None
    lo, hi = 1, total
    while lo < hi:
        mid = (lo + hi) // 2
        if fails(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo if fails(lo) else None


def minimize_subset(
    files: Sequence[str],
    fails: Callable[[list[str]], bool],
    budget: int = 40,
) -> list[str]:
    """预算内精简集合：逐级减半滑窗剔除仍保持失败的文件，直到每个元素都必要。"""
    subset = list(files)
    runs = 0
    changed = True
    while changed and runs < budget:
        changed = False
        chunk = max(1, len(subset) // 2)
        while chunk >= 1 and runs < budget:
            i = 0
            while i < len(subset) and runs < budget:
                candidate = subset[:i] + subset[i + chunk :]
                runs += 1
                if len(candidate) < len(subset) and fails(candidate):
                    subset = candidate
                    changed = True
                else:
                    i += chunk
            chunk //= 2
    return subset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="二分定位顺序依赖（测试间状态泄漏）的污染源文件",
    )
    parser.add_argument("target", help="目标用例节点ID（path::Class::test 或 path::test）")
    parser.add_argument(
        "--collect-root",
        default="src/test",
        help="收集参考顺序的根目录（默认 src/test）",
    )
    parser.add_argument(
        "--candidates",
        default="",
        help="限定候选文件（空格/逗号分隔）；给定后跳过全量前缀，只在这些文件内搜",
    )
    parser.add_argument("--max-runs", type=int, default=40, help="pytest 运行次数上限（默认 40）")
    parser.add_argument("--run-timeout", type=float, default=600.0, help="单次 pytest 超时秒数")
    parser.add_argument("--dry-run", action="store_true", help="只做单跑确认与候选枚举，不二分")
    args = parser.parse_args(argv)

    target = args.target.strip()
    print(f"[..] 目标用例：{target}")

    # 1) 单跑目标：必须通过（否则非顺序依赖）
    out = run_pytest_case([target], target, timeout=args.run_timeout)
    if out is Outcome.TARGET_FAILED:
        print("[!] 目标单跑即失败——不是顺序依赖问题（请直接调试该用例）")
        return 1
    if out in (Outcome.OTHER_FAILURE, Outcome.ERROR):
        print("[ERR] 单跑出现无关失败或执行错误，先处理后再用本工具")
        return 2
    print("[OK] 单跑通过（具备顺序依赖特征）")

    # 2) 收集参考顺序
    collect = subprocess.run(
        [sys.executable, "-m", "pytest", args.collect_root, "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=args.run_timeout,
    )
    ordered = parse_collect_order(collect.stdout)
    if collect.returncode != 0 or not ordered:
        print("[ERR] 收集失败（--collect-only 非 0 或无结果）")
        print((collect.stdout + collect.stderr)[-500:])
        return 2

    target_file = target.split("::", 1)[0]
    if target_file not in ordered:
        print(f"[ERR] 目标文件不在收集结果中：{target_file}（--collect-root 是否正确？）")
        return 2

    if args.candidates.strip():
        wanted = {c for c in re.split(r"[,\s]+", args.candidates.strip()) if c}
        unknown = wanted - set(ordered)
        if unknown:
            print(f"[ERR] 候选文件不在收集结果中：{sorted(unknown)}")
            return 2
        candidates = [f for f in ordered if f in wanted and f != target_file]
    else:
        target_idx = ordered.index(target_file)
        candidates = ordered[:target_idx]
    print(f"[..] 候选前置文件：{len(candidates)} 个")
    if args.dry_run:
        print("[OK] dry-run 结束（未执行二分）")
        return 0

    # 3) 复现门：全量候选 + 目标必须让目标失败
    if not candidates:
        print("[!] 目标前无候选文件——顺序依赖不成立")
        return 2
    runs = 1  # 已消耗：单跑确认

    def case(files: list[str]) -> Outcome:
        nonlocal runs
        runs += 1
        return run_pytest_case([*files, target], target, timeout=args.run_timeout)

    if case(candidates) is not Outcome.TARGET_FAILED:
        print("[!] 全量候选与目标合跑时目标未失败（顺序不同或泄漏已不存在）——无法复现")
        return 2
    print("[OK] 已复现：目标在候选之后失败")

    # 4) 二分最小前缀
    def fails_prefix(k: int) -> bool:
        if runs > args.max_runs:
            return False
        return case(candidates[:k]) is Outcome.TARGET_FAILED

    if runs >= args.max_runs:
        print(f"[!] 已达运行上限 --max-runs={args.max_runs}")
        return 2
    k = smallest_failing_prefix(len(candidates), fails_prefix)
    if k is None or runs > args.max_runs:
        print("[!] 二分未收敛（可能非单调或达上限）——可尝试 --candidates 缩小范围")
        return 2
    minimal_prefix = candidates[:k]
    print(f"[OK] 最小失败前缀长度 K={k}（前一长度不失败）")

    # 5) 单文件配对确认；不成立则预算内精简
    last = minimal_prefix[-1]
    if case([last]) is Outcome.TARGET_FAILED:
        culprit = [last]
    else:
        if runs >= args.max_runs:
            print(f"[!] 已达运行上限 --max-runs={args.max_runs}，无法进一步精简")
            return 2
        remaining_budget = max(4, args.max_runs - runs)

        def fails_subset(subset: list[str]) -> bool:
            nonlocal runs
            runs += 1
            return case(subset) is Outcome.TARGET_FAILED

        culprit = minimize_subset(minimal_prefix, fails_subset, budget=remaining_budget)
        if not fails_subset(culprit):  # 精简后必须仍可复现（最终确认）
            print("[ERR] 精简集合无法复现——请用 --candidates 缩小范围重试")
            return 2

    repro_cmd = f".venv/bin/python -m pytest {' '.join(culprit)} {target} -q --tb=short"
    print("[OK] 污染源已定位：")
    for f in culprit:
        print(f"       - {f}")
    print(f"       最小复现：{repro_cmd}")
    print(f"[OK] 共执行 pytest {runs} 次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
