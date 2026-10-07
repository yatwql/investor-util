"""`scripts/` 下检查类脚本的共享设施（统一 CLI 契约 / 输出格式 / 路径 / 文档区间解析）。

**统一的检查脚本契约**（CLAUDE.md 的提交前/发布前门禁据此调用）：
  - 每个检查脚本支持 `-v/--verbose`（详细）与 `--ci`（仅输出 `文件:描述`）
  - 退出码 **0 = 通过，2 = 发现 finding**（`check-code-traces.py` 另有 LOW 级别 1，属其自身分级语义）
  - 通过时打印 `[OK] …`；失败时逐条 `[ERR] file:desc`（或 `--ci` 下仅 `file:desc`）+ `[!] 发现 N 处…`

本模块提供**无副作用的原语**（例外：结论缓存 `conclusion_cache_*`——仅在调用方
显式调用时读写，写入原子、失败静默，见文末章节）；脚本以
``sys.path.insert(0, str(Path(__file__).resolve().parent))`` 后 ``from _checklib import …`` 引用
（`pyproject.toml` 对 `scripts/*.py` 声明了 E402 豁免，理由即此）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

#: 仓库根目录（`scripts/` 的上一级）
REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def rel(path: Path) -> str:
    """仓库相对路径，**POSIX 分隔符**（非仓库内路径原样返回，便于单测传合成路径）。

    统一用 `/` 而非 OS 原生分隔符：仓库相对路径的消费方（`folders.md` 目录树、
    文档内文件引用、CI 日志）一律是 POSIX 形式，Windows 下若返回 `\\`，
    调用方的字符串比较/拼接会全部失配（`parse_tree_paths` 的 `/` 拼接
    与 `_actual_files()` 的 `\\` 比对不上，导致“目录树缺全部条目”误报）。
    """
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


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


# ── 结论缓存（输入指纹未变时复用上次结论） ──────────────────────────
# 设计边界（质量前提，本地降频不降级）：
#   - **通过与发现都缓存**——输入字节未变 ⇒ 结论必然相同，退出码同源；
#   - **失效方向永远偏向全量**：逻辑版本（调用脚本 + 本模块 + 解释器大版本）
#     或输入文件集/逐文件指纹任一失配、状态缺失损坏 → 返回 None，调用方全量重算；
#   - **只作加速不是真值**：写入原子（tmp + replace）、失败静默不抛；
#   - **加载建议限定 `--ci`**：结论按 ci 输出形态缓存，verbose 详细过程仍全量执行。

#: 结论缓存目录环境变量（测试隔离经 `_path_isolation` 重定向到 tmp）
_CONCLUSION_CACHE_ENV = "CHECK_CONCLUSION_CACHE_DIR"
_CONCLUSION_CACHE_DEFAULT = REPO_ROOT / "data" / "cache" / "guard_conclusions"


def conclusion_cache_dir() -> Path:
    """结论缓存目录（环境变量可重定向）。"""
    override = os.environ.get(_CONCLUSION_CACHE_ENV)
    return Path(override) if override else _CONCLUSION_CACHE_DEFAULT


def _logic_fingerprint(logic_files: Sequence[Path]) -> str:
    """收集逻辑版本指纹：调用脚本 + 本模块字节 + 解释器大版本。"""
    parts = [f"py{sys.version_info[0]}.{sys.version_info[1]}"]
    for p in logic_files:
        try:
            parts.append(hashlib.sha1(p.read_bytes()).hexdigest())
        except OSError:
            parts.append("?")
    parts.append(hashlib.sha1(Path(__file__).read_bytes()).hexdigest())
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _input_fingerprint(input_files: Sequence[Path]) -> dict[str, str]:
    """输入面指纹：``{仓库相对 POSIX: size:mtime_ns}``，路径排序。

    文件集增删、内容或时间戳任一变化即失配（宁可多失效不漏失效）；
    声明了但已消失的文件记 ``<absent>``（调用方下次重算会同步文件集）。
    """
    out: dict[str, str] = {}
    for p in sorted({Path(x) for x in input_files}, key=lambda q: q.as_posix()):
        try:
            st = p.stat()
        except OSError:
            out[rel(p)] = "<absent>"
            continue
        out[rel(p)] = f"{st.st_size}:{st.st_mtime_ns}"
    return out


def conclusion_cache_load(
    namespace: str,
    logic_files: Sequence[Path],
    input_files: Sequence[Path],
) -> dict | None:
    """命中 → 结论 dict（须含 ``findings`` 列表，调用方可附带其他回放字段）；否则 None。

    None（一律全量重算）：缓存缺失 / 损坏 / 非法结构 / 逻辑版本变化 /
    文件集或逐文件指纹变化 / ``findings`` 非列表。
    """
    path = conclusion_cache_dir() / f"{namespace}.json"
    logic = _logic_fingerprint(logic_files)
    inputs = _input_fingerprint(input_files)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("logic") != logic or data.get("inputs") != inputs:
        return None
    conclusion = data.get("conclusion")
    if not isinstance(conclusion, dict) or not isinstance(conclusion.get("findings"), list):
        return None
    return conclusion


def conclusion_cache_save(
    namespace: str,
    logic_files: Sequence[Path],
    input_files: Sequence[Path],
    conclusion: dict,
) -> None:
    """原子写结论（通过与发现都缓存）；任何失败静默——缓存只是加速，不是真值。"""
    payload = {
        "logic": _logic_fingerprint(logic_files),
        "inputs": _input_fingerprint(input_files),
        "conclusion": conclusion,
    }
    path = conclusion_cache_dir() / f"{namespace}.json"
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
