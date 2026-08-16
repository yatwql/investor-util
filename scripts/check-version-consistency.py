#!/usr/bin/env python3
"""版本号一致性检查脚本。

以 src/python/core/constants.py 的 APP_VERSION 为单一事实源，校验以下文件中的版本号与其一致：

  - pyproject.toml          version = "X.Y.Z"
  - README.md               > 当前版本：X.Y.Z
  - docs-stm/managements/plan.md, technical.md, requirements.md,
    testplan.md, review-findings.md, llm-technical.md,
    folders.md, test-coverage.md
                            最后更新：...（vX.Y.Z ...）
  - docs-stm/managements/developer-guide.md
                            最后更新：...（vX.Y.Z）
  - docs-stm/managements/changelog.md
                            ## [X.Y.Z]

用法：
  python scripts/check-version-consistency.py
    检查所有文件，不一致时报错退出（exit code 1）。

  python scripts/check-version-consistency.py --fix
    自动同步 pyproject.toml 的 version 字段（其他文件需手动更新）。
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── 读取事实源 ──────────────────────────────────────────────

CONSTANTS_FILE = REPO_ROOT / "src" / "python" / "core" / "constants.py"


def _get_app_version() -> str:
    """从 constants.py 读取 APP_VERSION。"""
    text = CONSTANTS_FILE.read_text(encoding="utf-8")
    m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        print(f"[ERR] 未能在 {CONSTANTS_FILE} 中找到 APP_VERSION")
        sys.exit(1)
    return m.group(1)


# ── 检查项定义 ──────────────────────────────────────────────
# 每项：(path_relative, 断言类型, 参数)
#   断言类型:
#     "exact"       → 正则匹配整个字符串
#     "contains"    → 文件内容包含某子串
#     "header"      → 「文档版本：」头部版本行精确匹配（行首锚定，
#                     防止正文偶然出现的版本号导致全文 contains 误判）

CHECKS: list[tuple[Path, str, tuple[str, ...]]] = []


def add_exact(path: Path, pattern: str):
    CHECKS.append((REPO_ROOT / path, "exact", (pattern,)))


def add_contains(path: Path, *patterns: str):
    CHECKS.append((REPO_ROOT / path, "contains", patterns))


def add_header(path: Path):
    CHECKS.append((REPO_ROOT / path, "header", ()))


# 代码文件
CHECKS.append((REPO_ROOT / "pyproject.toml", "pyproject_version", ()))
CHECKS.append((REPO_ROOT / "src" / "python" / "core" / "constants.py", "exact", (r'^APP_VERSION\s*=\s*"[^"]*"$',)))

# Markdown 管理文档
add_exact(REPO_ROOT / "README.md", r"> 当前版本：{v}")
add_header(REPO_ROOT / "docs-stm" / "managements" / "plan.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "technical.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "requirements.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "testplan.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "review-findings.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "llm-technical.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "folders.md")
add_header(REPO_ROOT / "docs-stm" / "managements" / "test-coverage.md")
# changelog 无「文档版本：」头，用 [X.Y.Z] 标题行 contains 校验
add_contains(REPO_ROOT / "docs-stm" / "managements" / "changelog.md", "[{v}]")
add_header(REPO_ROOT / "docs-stm" / "managements" / "developer-guide.md")


# ── 校验逻辑 ────────────────────────────────────────────────


def _check_exact(text: str, pattern_template: str, version: str) -> bool:
    pattern = pattern_template.replace("{v}", re.escape(version))
    return bool(re.search(pattern, text, re.MULTILINE))


def _check_contains(text: str, patterns_template: tuple[str, ...], version: str) -> bool:
    return any(p.replace("{v}", version) in text for p in patterns_template)


def _check_header(text: str, version: str) -> bool:
    """校验「文档版本：」头部版本行与目标版本精确一致（行首锚定）。

    仅匹配整行 `> 文档版本：{version}`，避免正文偶然出现的版本号
    导致全文 contains 误判。
    """
    pattern = rf"^\s*>\s*文档版本：{re.escape(version)}\s*$"
    return bool(re.search(pattern, text, re.MULTILINE))


def _auto_fix_header(path: Path, version: str) -> bool:
    """自动修正「文档版本：」头部版本行为目标版本。"""
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"^\s*>\s*文档版本：.*$",
        lambda m: f"> 文档版本：{version}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count > 0 and new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def _check_pyproject_version(text: str, version: str) -> bool:
    """pyproject.toml 特殊检查：匹配 version = "X.Y.Z" """
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        return False
    return m.group(1) == version


def _auto_fix_pyproject(path: Path, version: str) -> bool:
    """自动修正 pyproject.toml 的 version 字段。"""
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'^(version\s*=\s*)"[^"]*"',
        lambda m: f'{m.group(1)}"{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count > 0 and new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> None:
    version = _get_app_version()
    do_fix = "--fix" in sys.argv

    print(f"[..] 校验版本号一致性 — APP_VERSION = {version}\n     来源：{CONSTANTS_FILE.relative_to(REPO_ROOT)}\n")

    all_ok = True
    checked = 0
    fixed = 0

    for full_path, assert_type, args in CHECKS:
        checked += 1
        rel = full_path.relative_to(REPO_ROOT)

        if not full_path.exists():
            print(f"  [!] {rel} — 文件不存在，跳过")
            continue

        text = full_path.read_text(encoding="utf-8")

        if assert_type == "pyproject_version":
            ok = _check_pyproject_version(text, version)
            if not ok and do_fix:
                if _auto_fix_pyproject(full_path, version):
                    print(f"  [OK] {rel} — 已自动修正为 {version}")
                    fixed += 1
                    ok = True
        elif assert_type == "exact":
            pattern = args[0].replace("{v}", re.escape(version))
            ok = bool(re.search(pattern, text, re.MULTILINE))
        elif assert_type == "contains":
            ok = _check_contains(text, args, version)
        elif assert_type == "header":
            ok = _check_header(text, version)
            if not ok and do_fix:
                if _auto_fix_header(full_path, version):
                    print(f"  [OK] {rel} — 已自动修正头部版本号为 {version}")
                    fixed += 1
                    ok = True
        else:
            ok = False

        if ok:
            print(f"  [OK] {rel}")
        else:
            if assert_type == "header":
                print(f"  [ERR] {rel} — 头部版本行未同步，期望 `> 文档版本：{version}`")
            else:
                print(f"  [ERR] {rel} — 版本号未同步，期望包含 {version}")
            all_ok = False

    print()
    if all_ok:
        print(f"[OK] 全部 {checked} 项通过 — 版本号一致")
        return

    if do_fix and fixed > 0:
        print(f"[!] 已自动修正 {fixed} 项（pyproject 版本字段 / 管理文档头部版本行）。其他文件需手动更新。")
        sys.exit(0)

    print("[ERR] 版本号不一致 — 请先手动更新后重试。")
    print("      发布流程：")
    print("        1. 修改 src/python/core/constants.py APP_VERSION")
    print("        2. 运行 python scripts/check-version-consistency.py")
    print("        3. 按 [ERR] 提示逐个更新文档版本号")
    print("        4. 再次运行确认全部 [OK]")
    print("        5. 提交 + 打标签")
    sys.exit(1)


if __name__ == "__main__":
    main()
