#!/usr/bin/env python3
"""需求 ID ↔ 验证载体追溯校验脚本 — 校验 requirements.md 的需求 ID 在 testplan.md 均有确定测试载体。

`requirements.md` 是需求 ID 的**唯一事实来源**；`testplan.md` §2.1 的
「需求 ID ↔ 验证载体映射」表承载「每条需求由哪些测试文件/用例验证」。两面互为镜像，
本脚本按四个断言校验（**分批推进**：`_COVERED_DOMAINS` 记录已补全的需求域）：

  1. 映射表格式：`<!-- requirement-trace:start/end -->` 标记与表头齐备（防整表被误删）
  2. ID 合法性：映射表中的每个 ID 均存在于 `requirements.md`（防臆造/拼错 ID）
  3. ID 唯一性：同一 ID 在映射表中不得重复登记（防两行互相矛盾）
  4. 域覆盖完备性：`_COVERED_DOMAINS` 中每个已补全域在 `requirements.md` 中的全部 ID
     均已在映射表中（防「补了 37 条漏 1 条」）
  5. 载体真实性：映射表载体列中出现的 `src/test/**/*.py` 路径必须真实存在于磁盘
     （防测试文件改名/删除后文档留悬空引用）

**分批推进方式**：每完成一批需求域（见 testplan.md §2.1 的「补全批次」列），
把该域前缀追加进 `_COVERED_DOMAINS`——脚本随即开始断言该域全覆盖。全部域补完后该
常量即为 `_ALL_DOMAINS`，脚本转为全量断言。

用法：
  python scripts/check-requirement-trace.py       # 检查全部已补域
  python scripts/check-requirement-trace.py -v    # 详细输出（打印每项解析结果）
  python scripts/check-requirement-trace.py --ci  # CI 模式：仅输出 文件名:描述，退出码 2

退出码：
  0 — 全部通过  2 — 发现 finding
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, extract_region, rel, report  # noqa: E402

_REQUIREMENTS_MD = REPO_ROOT / "docs-stm" / "managements" / "requirements.md"
_TESTPLAN_MD = REPO_ROOT / "docs-stm" / "managements" / "testplan.md"

_TRACE_START = "<!-- requirement-trace:start -->"
_TRACE_END = "<!-- requirement-trace:end -->"

#: 需求 ID 形如 `R-CCH-01`（域前缀 + 两位序号）
_ID_RE = re.compile(r"^\|\s*(R-[A-Z]+-\d+)\s*\|")
#: 载体列中的测试文件路径（反引号内以 src/test/ 开头、.py 结尾）
_CARRIER_PATH_RE = re.compile(r"`(src/test/[\w/\-]+\.py)(?:::[\w\[\]:\- ,]+)?`")

#: 已完成「需求 ID → 验证载体」映射的域前缀（每补完一批在此追加一项）
_COVERED_DOMAINS: tuple[str, ...] = ("R-CCH",)

#: requirements.md 中全部需求域前缀（用于全量断言；与 _COVERED_DOMAINS 比对即得进度）
_ALL_DOMAINS: tuple[str, ...] = (
    "R-CCH",
    "R-ERR",
    "R-DIAG",
    "R-BRK",
    "R-CRD",
    "R-FIN",
    "R-FRD",
    "R-NWS",
    "R-DATA",
    "R-IDX",
    "R-OUT",
    "R-PERF",
    "R-WIF",
    "R-ACT",
    "R-RBL",
    "R-VAL",
    "R-TAIL",
    "R-EVO",
    "R-SNP",
    "R-CFL",
    "R-DIFF",
    "R-PEN",
    "R-LLM",
    "R-PF",
    "R-CTX",
    "R-WEB",
    "R-TUI",
    "R-ENV",
    "R-HLD",
    "R-DIS",
    "R-LIQ",
    "R-FX",
    "R-CON",
    "R-ADP",
    "R-HST",
)


def requirement_ids(text: str) -> dict[str, int]:
    """从 requirements.md 提取 `{需求 ID: 首次出现行号}`。"""
    ids: dict[str, int] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        match = _ID_RE.match(line)
        if match and match.group(1) not in ids:
            ids[match.group(1)] = lineno
    return ids


def trace_rows(text: str) -> list[tuple[str, str, int]]:
    """解析测试计划映射表，返回 `[(需求 ID, 载体原文, 行号)]`（标记缺失时返回空表）。"""
    region = extract_region(text, _TRACE_START, _TRACE_END)
    if region is None:
        return []
    rows: list[tuple[str, str, int]] = []
    offset = text[: text.find(_TRACE_START)].count("\n") + 1
    for index, line in enumerate(region.splitlines(), offset):
        match = _ID_RE.match(line)
        if match:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append((match.group(1), cells[1] if len(cells) > 1 else "", index))
    return rows


def carrier_paths(carrier_cell: str) -> list[str]:
    """提取载体单元格中的测试文件路径（去重、保序）。"""
    seen: list[str] = []
    for path in _CARRIER_PATH_RE.findall(carrier_cell):
        if path not in seen:
            seen.append(path)
    return seen


def check_requirement_trace(
    requirements_text: str | None = None,
    testplan_text: str | None = None,
    *,
    covered_domains: tuple[str, ...] | None = None,
) -> list[str]:
    """校验需求 ID 与验证载体的双向追溯（返回 finding 描述列表）。

    Args:
        requirements_text: requirements.md 正文（None 时读磁盘）
        testplan_text: testplan.md 正文（None 时读磁盘）
        covered_domains: 视为「已补全」的域前缀（None 时用模块级 `_COVERED_DOMAINS`）
    """
    req_text = requirements_text
    if req_text is None:
        req_text = _REQUIREMENTS_MD.read_text(encoding="utf-8") if _REQUIREMENTS_MD.exists() else ""
    plan_text = testplan_text
    if plan_text is None:
        plan_text = _TESTPLAN_MD.read_text(encoding="utf-8") if _TESTPLAN_MD.exists() else ""
    if not req_text or not plan_text:
        return []

    findings: list[str] = []
    domains = _COVERED_DOMAINS if covered_domains is None else covered_domains

    rows = trace_rows(plan_text)
    if not rows:
        findings.append(
            f"{rel(_TESTPLAN_MD)}: 未找到需求追溯映射表（`{_TRACE_START}` … `{_TRACE_END}` 标记或表行缺失）"
        )
        return findings

    known_ids = requirement_ids(req_text)
    mapped: dict[str, str] = {}
    for req_id, carrier, lineno in rows:
        if req_id in mapped:
            findings.append(f"{rel(_TESTPLAN_MD)}:{lineno}: 需求 ID `{req_id}` 重复登记（已在映射表中出现）")
            continue
        mapped[req_id] = carrier
        if req_id not in known_ids:
            findings.append(
                f"{rel(_TESTPLAN_MD)}:{lineno}: 需求 ID `{req_id}` 不存在于 requirements.md（臆造或拼写错误）"
            )
        for path in carrier_paths(carrier):
            if not (REPO_ROOT / path).exists():
                findings.append(f"{rel(_TESTPLAN_MD)}:{lineno}: 需求 `{req_id}` 的载体文件 `{path}` 不存在于磁盘")
        if not carrier:
            findings.append(f"{rel(_TESTPLAN_MD)}:{lineno}: 需求 `{req_id}` 的验证载体列缺失")

    for domain in domains:
        expected = [rid for rid in known_ids if rid.startswith(f"{domain}-")]
        if not expected:
            findings.append(
                f"{rel(_REQUIREMENTS_MD)}: 已声明补全的域 `{domain}` 在 requirements.md 中无任何 ID（域名拼写错误？）"
            )
            continue
        missing = sorted(rid for rid in expected if rid not in mapped)
        if missing:
            preview = ", ".join(missing[:6]) + (" …" if len(missing) > 6 else "")
            findings.append(
                f"{rel(_TESTPLAN_MD)}: 已补全域 `{domain}` 有 {len(missing)} 条需求未映射验证载体：{preview}"
            )
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="需求 ID ↔ 验证载体追溯校验（requirements.md ↔ testplan.md §2.1）")
    add_common_args(parser)
    args = parser.parse_args()

    findings = check_requirement_trace()
    if args.verbose:
        plan_text = _TESTPLAN_MD.read_text(encoding="utf-8")
        rows = trace_rows(plan_text)
        known_ids = requirement_ids(_REQUIREMENTS_MD.read_text(encoding="utf-8"))
        print(f"  已补全域（{len(_COVERED_DOMAINS)}/{len(_ALL_DOMAINS)}）：{', '.join(_COVERED_DOMAINS)}")
        print(f"  映射表行数：{len(rows)}（requirements.md 共 {len(known_ids)} 条需求 ID）")
        for domain in _COVERED_DOMAINS:
            covered = sum(1 for rid in known_ids if rid.startswith(f"{domain}-"))
            print(f"    {domain}: {covered}/{covered} 已映射")
    sys.exit(
        report(
            findings,
            f"[OK] 需求追溯校验通过（已补全域 {len(_COVERED_DOMAINS)}/{len(_ALL_DOMAINS)}：{', '.join(_COVERED_DOMAINS)}）",
            ci=args.ci,
            fail_message="[!] 发现 {n} 处需求追溯不一致，须修正 testplan.md §2.1 后提交",
        )
    )


if __name__ == "__main__":
    main()
