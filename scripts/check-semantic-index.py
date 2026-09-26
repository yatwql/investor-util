#!/usr/bin/env python3
"""语义命名索引双向校验脚本 — 校验技术设计文档（technical.md）「功能语义命名表」章节与代码的一致性。

「功能语义命名表」是「代码标识符 = 文档中文描述」的唯一现状基准（活索引）。
check-code-traces.py 只做负面禁止（禁任务代号/魔法编号），本脚本做正面一致性校验，
三向检查：

  1. 正向：src/python/config/features.py 的功能开关注册表（``feature_switch_registry``）
     每个键（运行时功能开关）必须已登记在「功能语义命名表」中（表外键报错，防新增开关绕过登记）
  2. 反向：表中每个语义 slug 在 src/python/ 下至少一处非注释代码引用
     （防僵尸条目——功能已删除但表行残留）
  3. 合并章：表下「合并章代码标识符」注声明的 sheet key 必须存在于
     core/registry.py 的 _REPORT_SECTION_DEFAULT 注册表（防 sheet key 改名/删除后
     文档未同步）

表解析基于该表首尾的 HTML 注释标记（<!-- semantic-index:start/end -->），
与 check-version-consistency.py / test-runner.py 文档写入器同款标记定位习语，
不依赖脆弱的表头正则。标记缺失时报错（须先在文档中补齐标记）。

用法：
  python scripts/check-semantic-index.py       # 检查全部
  python scripts/check-semantic-index.py -v    # 详细输出（打印每项解析结果）
  python scripts/check-semantic-index.py --ci  # CI 模式：仅输出 文件名:描述，退出码 2

退出码：
  0 — 全部通过（正反向 + 合并章均一致）
  2 — 发现不一致（表外键 / 僵尸条目 / 合并章 key 缺失）
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, extract_region, rel, report  # noqa: E402

_TECHNICAL_MD = REPO_ROOT / "docs-stm" / "managements" / "technical.md"
_FEATURES_PY = REPO_ROOT / "src/python/config/features.py"
_CONFIG_DEFAULTS = REPO_ROOT / "src" / "python" / "config" / "_config_defaults.py"
_REGISTRY_PY = REPO_ROOT / "src" / "python" / "core" / "registry.py"
_CODE_ROOT = REPO_ROOT / "src" / "python"

_MARKER_START = "<!-- semantic-index:start -->"
_MARKER_END = "<!-- semantic-index:end -->"

# 表行：第一格为反引号包裹的语义 slug（`` `slug` ``），仅取第一列
_ROW_PATTERN = re.compile(r"^\|\s*`([a-z_]+)`\s*\|")
# 合并章注：`` `sheet_key`（ `` 形态（仅取合并章标识符注所在行，避免误取并入说明）
_MERGED_KEY_PATTERN = re.compile(r"`([a-z_]+)`（")
_MERGED_NOTE_MARK = "**合并章代码标识符**"

# 反向扫描时跳过的目录段
_SKIP_REL_PARTS = {"__pycache__"}


# ═══════════════════════════════════════════════════════════════
#  表解析（基于 HTML 注释标记定位）
# ═══════════════════════════════════════════════════════════════


def extract_marker_region(doc_text: str) -> str | None:
    """返回功能语义命名表标记区间内的正文；start/end 任一标记缺失返回 None。"""
    return extract_region(doc_text, _MARKER_START, _MARKER_END)


def parse_table_slugs(doc_text: str) -> list[str]:
    """解析标记区间内表格的语义 slug 列（按出现顺序，仅第一列）。"""
    region = extract_marker_region(doc_text)
    if region is None:
        return []
    slugs: list[str] = []
    for line in region.splitlines():
        m = _ROW_PATTERN.match(line)
        if m:
            slugs.append(m.group(1))
    return slugs


def parse_merged_sheet_keys(doc_text: str) -> list[str]:
    """解析标记区间内「合并章代码标识符」注声明的 sheet key。"""
    region = extract_marker_region(doc_text)
    if region is None:
        return []
    keys: list[str] = []
    for line in region.splitlines():
        if _MERGED_NOTE_MARK in line:
            keys.extend(_MERGED_KEY_PATTERN.findall(line))
    return keys


# ═══════════════════════════════════════════════════════════════
#  权威源解析（ast，不 import 运行库避免副作用）
# ═══════════════════════════════════════════════════════════════


def feature_switch_keys(source: str) -> list[str]:
    """ast 解析 features.py，返回功能开关注册表（feature_switch_registry）的全部键。

    注册表取值统一为单一事实来源（旧 ``report_submodules`` 机制已移除），
    故「表外键」校验挂在注册表上：新增开关必须同步登记「功能语义命名表」。
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id != "feature_switch_registry" or not isinstance(node.value, ast.Dict):
            continue
        return [k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    return []


def registry_section_keys(source: str) -> list[str]:
    """ast 解析 registry.py，返回 _REPORT_SECTION_DEFAULT 列表各 dict 的 key 值。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for t in targets:
            if not (isinstance(t, ast.Name) and t.id == "_REPORT_SECTION_DEFAULT"):
                continue
            if not isinstance(node.value, ast.List):
                continue
            keys: list[str] = []
            for elt in node.value.elts:
                if not isinstance(elt, ast.Dict):
                    continue
                for i, k in enumerate(elt.keys):
                    if isinstance(k, ast.Constant) and k.value == "key":
                        v = elt.values[i]
                        if isinstance(v, ast.Constant) and isinstance(v.value, str):
                            keys.append(v.value)
            return keys
    return []


# ═══════════════════════════════════════════════════════════════
#  反向存在性校验
# ═══════════════════════════════════════════════════════════════


def _code_without_comments(source: str) -> str:
    """用 tokenize 剔除注释，返回拼接的代码 token 文本（字符串字面量保留）。"""
    tokens: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (
                tokenize.COMMENT,
                tokenize.ENCODING,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENDMARKER,
            ):
                continue
            tokens.append(tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # 语法异常文件（如含模板占位）——按原始文本降级，注释剔除尽力而为
        return source
    return " ".join(tokens)


def collect_code_texts(code_root: Path) -> list[tuple[Path, str]]:
    """一次性读取 code_root 下全部 `.py` 并剔除注释，返回 ``[(路径, 代码文本), …]``。

    **性能关键**：`_code_without_comments()` 要跑一遍 tokenize，成本远高于字符串包含判断。
    若按 slug 逐个重读，规模会放大成 116 slug × ~88 文件 ≈ 10,176 次全文件 tokenize
    （约占本脚本 95% 耗时）；故每次检查只收集一次，所有 slug 复用同一份结果。
    """
    collected: list[tuple[Path, str]] = []
    if not code_root.exists():
        return collected
    for fpath in sorted(code_root.rglob("*.py")):
        if any(part in _SKIP_REL_PARTS for part in fpath.parts):
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        collected.append((fpath, _code_without_comments(text)))
    return collected


def slug_exists_in_code(
    code_root: Path,
    slug: str,
    code_texts: list[tuple[Path, str]] | None = None,
) -> bool:
    """slug 在 code_root 下任一 `.py` 的非注释代码中出现即视为存在。

    Args:
        code_root: 代码根目录（`code_texts` 缺省时按它现算）
        slug: 语义 slug
        code_texts: 预先收集的 ``[(路径, 代码文本), …]``（批量检查时传入以复用 tokenize 结果）
    """
    texts = code_texts if code_texts is not None else collect_code_texts(code_root)
    return any(slug in text for _fpath, text in texts)


# ═══════════════════════════════════════════════════════════════
#  总入口
# ═══════════════════════════════════════════════════════════════


def run_checks(
    doc_text: str,
    features_source: str,
    registry_source: str,
    code_root: Path,
) -> list[str]:
    """三向校验，返回违规描述列表（空 = 全部通过）。"""
    findings: list[str] = []

    if extract_marker_region(doc_text) is None:
        findings.append(f"{rel(_TECHNICAL_MD)}: 「功能语义命名表」缺少 semantic-index:start/end 标记")
        return findings

    table_slugs = parse_table_slugs(doc_text)
    merged_keys = parse_merged_sheet_keys(doc_text)
    switch_keys = feature_switch_keys(features_source)
    registry_keys = registry_section_keys(registry_source)
    # 代码文本只收集一次（tokenize 是热点），所有 slug 复用同一份结果
    code_texts = collect_code_texts(code_root)

    # 正向：功能开关注册表键必须在表中登记
    for key in switch_keys:
        if key not in table_slugs:
            findings.append(f"{rel(_FEATURES_PY)}: 功能开关 {key} 未在「功能语义命名表」登记")

    # 反向：表中 slug 必须在代码中存在（防僵尸条目）
    for slug in table_slugs:
        if not slug_exists_in_code(code_root, slug, code_texts):
            findings.append(
                f"{rel(_TECHNICAL_MD)}: 语义 slug `{slug}` 在 src/python/ 无代码引用（「功能语义命名表」僵尸条目）"
            )

    # 合并章：sheet key 必须在 registry 中存在
    for key in merged_keys:
        if key not in registry_keys:
            findings.append(
                f"{rel(_TECHNICAL_MD)}: 「功能语义命名表」合并章: sheet key `{key}` 不在 registry._REPORT_SECTION_DEFAULT"
            )

    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="校验「功能语义命名表」与代码的正反向一致性（正面校验，与 check-code-traces 负面禁止互补）",
    )
    add_common_args(parser)
    args = parser.parse_args()

    doc_text = _TECHNICAL_MD.read_text(encoding="utf-8")
    features_source = _FEATURES_PY.read_text(encoding="utf-8")
    registry_source = _REGISTRY_PY.read_text(encoding="utf-8")

    findings = run_checks(doc_text, features_source, registry_source, _CODE_ROOT)

    if args.verbose:
        table_slugs = parse_table_slugs(doc_text)
        merged_keys = parse_merged_sheet_keys(doc_text)
        switch_keys = feature_switch_keys(features_source)
        registry_keys = registry_section_keys(registry_source)
        print(f"  表内 slug（{len(table_slugs)}）：{', '.join(table_slugs)}")
        print(f"  功能开关（{len(switch_keys)}）：{', '.join(switch_keys)}")
        print(f"  合并章 sheet key（{len(merged_keys)}）：{', '.join(merged_keys)}")
        print(f"  registry 章节 key（{len(registry_keys)}）：{', '.join(registry_keys)}")

    sys.exit(
        report(
            findings,
            "[OK] 语义命名索引正反向校验通过（表内 slug 均存在、功能开关均登记、合并章 key 均在 registry）",
            ci=args.ci,
            fail_message="[!] 发现 {n} 处语义命名索引不一致，须修正后提交",
        )
    )


if __name__ == "__main__":
    main()
