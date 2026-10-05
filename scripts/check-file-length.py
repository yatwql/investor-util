#!/usr/bin/env python3
"""单文件行数红线守护脚本。

阈值口径（developer-guide「文件膨胀阈值」表 + review-findings P2A 硬上限）：
  - 主程序（``src/python/**.py``） > 800 行 → finding（硬上限，必须拆分）
  - 测试（``src/test/**.py``）      > 1200 行 → finding（测试文件红线）
  - 主程序 500-800 / 测试 800-1200 为可选优化区间，不判 finding，仅 ``-v`` 输出清单，
    供 review-findings「文件过长」登记表派生刷新（人肉快照退役，脚本输出即真值）。

豁免登记：既有破线项须同时在 review-findings 挂账限期处理，二者同步存在——
  - 豁免文件超限 → 不报 finding，``-v`` 列为「豁免」状态；
  - 非豁免文件超限 → finding，退出 2；
  - 豁免文件回落至阈值内 → ``-v`` 提示「可移除豁免」（不判 finding）。

豁免语义名登记（相对路径 → 挂账位置与处理要求；豁免必须与 review-findings
待处理区条目同步存在）：
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402

# ── 阈值与检查域 ──────────────────────────────────────────────

MAIN_SOURCE_LIMIT = 800
"""主程序单文件硬上限（行数）。"""

TEST_SOURCE_LIMIT = 1200
"""测试单文件红线（行数）。"""

MAIN_SOURCE_ROOT = "src/python"
TEST_SOURCE_ROOT = "src/test"

#: 既有破线豁免：相对路径 → 挂账说明（review-findings 待处理区须有对应条目）。
#: 空 = 当前无挂账破线项；新破线须先拆分，无法立即拆分时在此登记并同步挂账。
EXEMPTIONS: dict[str, str] = {}


def collect_line_counts(root: Path) -> list[tuple[str, str, int]]:
    """遍历检查域，返回 (类别, 相对路径, 行数) 记录列表（类别：主程序/测试）。"""
    records: list[tuple[str, str, int]] = []
    for sub, kind in ((MAIN_SOURCE_ROOT, "主程序"), (TEST_SOURCE_ROOT, "测试")):
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                lines = len(path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                continue
            records.append((kind, rel(path), lines))
    return records


def split_findings(
    records: list[tuple[str, str, int]],
    exemptions: dict[str, str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """把测量记录分成 (违规 finding, 豁免在列, 可移除豁免) 三组。"""
    exemptions = EXEMPTIONS if exemptions is None else exemptions
    violations: list[str] = []
    exempted: list[str] = []
    removable: list[str] = []
    for kind, path, lines in records:
        limit = MAIN_SOURCE_LIMIT if kind == "主程序" else TEST_SOURCE_LIMIT
        over = lines > limit
        if path in exemptions:
            if over:
                exempted.append(f"{path}（{kind} {lines} 行 > {limit}，豁免在列：{exemptions[path]}）")
            else:
                removable.append(f"{path}（已回落至 {limit} 行内，可移除豁免登记）")
        elif over:
            hint = "硬上限必须拆分" if kind == "主程序" else "测试文件红线须拆分"
            violations.append(f"{path}: {kind} {lines} 行 > {limit} 行（{hint}），须拆分或在豁免登记挂账")
    return violations, exempted, removable


def over_limit_inventory(records: list[tuple[str, str, int]]) -> list[str]:
    """可选优化区间清单：主程序 >500 行、测试 >800 行（P2A/P2C 登记表派生源）。"""
    rows = []
    for kind, path, lines in records:
        warn_at = 500 if kind == "主程序" else 800
        if lines > warn_at:
            rows.append(f"  [{kind}] {lines:>5} 行  {path}")
    rows.sort(key=lambda s: -int(s.split("]")[1].split("行")[0].strip()))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="单文件行数红线守护（主程序 >800 / 测试 >1200）")
    add_common_args(parser)
    args = parser.parse_args()

    records = collect_line_counts(REPO_ROOT)
    violations, exempted, removable = split_findings(records)

    if args.verbose:
        print(
            f"检查域：{MAIN_SOURCE_ROOT}/（≤{MAIN_SOURCE_LIMIT} 行）+ {TEST_SOURCE_ROOT}/（≤{TEST_SOURCE_LIMIT} 行）"
            f"，共 {len(records)} 个 py 文件"
        )
        for line in over_limit_inventory(records):
            print(line)
        for line in exempted:
            print(f"[豁免] {line}")
        for line in removable:
            print(f"[可移除豁免] {line}")

    ok_message = (
        f"[OK] 行数红线通过（主程序 ≤{MAIN_SOURCE_LIMIT} 行 / 测试 ≤{TEST_SOURCE_LIMIT} 行；"
        f"豁免在列 {len(exempted)} 项，违规 {len(violations)} 项）"
    )
    return report(
        violations,
        ok_message,
        ci=args.ci,
        fail_message="[!] 发现 {n} 个文件超行数红线，须拆分（或同步挂账豁免并登记 review-findings）",
    )


if __name__ == "__main__":
    sys.exit(main())
