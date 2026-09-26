"""`scripts/` 下检查类脚本的共享设施（统一 CLI 契约 / 输出格式 / 路径 / 文档区间解析）。

**统一的检查脚本契约**（CLAUDE.md 的提交前/发布前门禁据此调用）：
  - 每个检查脚本支持 `-v/--verbose`（详细）与 `--ci`（仅输出 `文件:描述`）
  - 退出码 **0 = 通过，2 = 发现 finding**（`check-code-traces.py` 另有 LOW 级别 1，属其自身分级语义）
  - 通过时打印 `[OK] …`；失败时逐条 `[ERR] file:desc`（或 `--ci` 下仅 `file:desc`）+ `[!] 发现 N 处…`

本模块只提供**无副作用的原语**，不替脚本决定检查内容；脚本以
``sys.path.insert(0, str(Path(__file__).resolve().parent))`` 后 ``from _checklib import …`` 引用
（`pyproject.toml` 对 `scripts/*.py` 声明了 E402 豁免，理由即此）。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

#: 仓库根目录（`scripts/` 的上一级）
REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def rel(path: Path) -> str:
    """仓库相对路径（非仓库内路径原样返回，便于单测传合成路径）。"""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """为检查脚本补上统一的两个公共开关（`-v/--verbose`、`--ci`）。"""
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出（打印解析结果与统计）")
    parser.add_argument("--ci", action="store_true", help="CI 模式：仅输出 文件:描述，退出码 2")


def report(
    findings: list[str],
    ok_message: str,
    *,
    ci: bool = False,
    fail_message: str | None = None,
) -> int:
    """按统一契约打印结论并返回退出码（0 = 通过，2 = 有 finding）。

    Args:
        findings: 违规描述列表（空表示通过）
        ok_message: 通过时的 `[OK]` 文案
        ci: CI 模式（只输出裸描述行，不加 `[ERR]` 前缀、不打汇总行）
        fail_message: 失败时的汇总行文案（可用 `{n}` 占位 finding 数）；缺省用「发现 N 处问题，须修正后提交」

    Returns:
        退出码（0 或 2），调用方 `sys.exit(...)` 即可。
    """
    if not findings:
        print(ok_message)
        return 0
    for finding in findings:
        print(finding if ci else f"[ERR] {finding}")
    if not ci:
        template = fail_message or "[!] 发现 {n} 处问题，须修正后提交"
        print(template.format(n=len(findings)))
    return 2


# ── 文档区间解析（HTML 注释标记 / 表区域） ──────────────────────


def extract_region(text: str, start_marker: str, end_marker: str) -> str | None:
    """返回 `start_marker … end_marker` 之间的正文；任一标记缺失返回 None。"""
    start = text.find(start_marker)
    if start == -1:
        return None
    body = text[start + len(start_marker) :]
    end = body.find(end_marker)
    if end == -1:
        return None
    return body[:end]


def replace_region(text: str, start_marker: str, end_marker: str, block: str) -> str | None:
    """用 `block` 替换 `start_marker … end_marker` 之间的内容；标记缺失返回 None。"""
    start = text.find(start_marker)
    if start == -1:
        return None
    body_start = start + len(start_marker)
    end = text.find(end_marker, body_start)
    if end == -1:
        return None
    return text[:body_start] + block + text[end:]


def _table_region_pattern(markers: tuple[str, str]) -> re.Pattern[str]:
    """表区域正则（起始标记 → 表格 → 结束标记，跨行）。"""
    start_marker, end_marker = markers
    return re.compile(re.escape(start_marker) + r"\n(.*?)\n" + re.escape(end_marker), re.DOTALL)


def extract_table_region(doc_text: str, markers: tuple[str, str]) -> list[str]:
    """抽取两 marker 之间的表格行（不含 marker 行与空行）。

    Raises:
        ValueError: marker 缺失 / 区域内不是表格 / 夹有非表格行 / 缺分隔行
    """
    match = _table_region_pattern(markers).search(doc_text)
    if not match:
        raise ValueError(f"文档缺少成对的表区域标记 {markers[0]} … {markers[1]}")
    lines = [ln for ln in match.group(1).splitlines() if ln.strip()]
    if not lines or not lines[0].lstrip().startswith("|"):
        raise ValueError(f"标记 {markers[0]} 与 {markers[1]} 之间未找到表格")
    # 全行校验：任一非表格行（如夹入说明文字）或分隔行缺失都判结构异常，
    # 防止后续 token 网格编辑把数据行误当分隔行而静默破坏表格。
    if any(not ln.lstrip().startswith("|") for ln in lines):
        raise ValueError(f"标记 {markers[0]} 与 {markers[1]} 之间夹有非表格行")
    if len(lines) < 2 or "---" not in lines[1]:
        raise ValueError(f"标记 {markers[0]} 与 {markers[1]} 之间的表格缺少分隔行")
    return lines


def replace_table_region(doc_text: str, markers: tuple[str, str], updated_lines: list[str]) -> str:
    """以更新后的表格行替换 marker 之间的表区域。

    Raises:
        ValueError: marker 未配对匹配（防御性，正常不会触发）
    """
    block = markers[0] + "\n" + "\n".join(updated_lines) + "\n" + markers[1]
    # 用可调用替换避免 re 把块内容当模板解析（单元格含反斜杠会触发 re.error）。
    new_text, count = _table_region_pattern(markers).subn(lambda _match: block, doc_text, count=1)
    if count != 1:
        raise ValueError(f"表区域标记 {markers[0]} 与 {markers[1]} 未匹配")
    return new_text
