#!/usr/bin/env python3
"""版本号一致性检查脚本。

以 src/python/constants.py 的 APP_VERSION 为单一事实源，校验以下文件中的版本号与其一致：

  - pyproject.toml          version = "X.Y.Z"
  - README.md               > 当前版本：X.Y.Z
  - docs-stm/managements/plan.md, technical.md, requirements.md,
    testplan.md, review-findings.md, llm-technical.md
                            最后更新：...（vX.Y.Z ...）
  - docs-stm/manuals/how-to-test-my-code.md
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

CONSTANTS_FILE = REPO_ROOT / "src" / "python" / "constants.py"


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

CHECKS: list[tuple[Path, str, tuple[str, ...]]] = []


def add_exact(path: Path, pattern: str):
    CHECKS.append((REPO_ROOT / path, "exact", (pattern,)))


def add_contains(path: Path, *patterns: str):
    CHECKS.append((REPO_ROOT / path, "contains", patterns))


# 代码文件
CHECKS.append((REPO_ROOT / "pyproject.toml", "pyproject_version", ()))
CHECKS.append((REPO_ROOT / "src" / "python" / "constants.py", "exact", (r'^APP_VERSION\s*=\s*"[^"]*"$',)))

# Markdown 管理文档
add_exact(REPO_ROOT / "README.md", r"> 当前版本：{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "plan.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "technical.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "requirements.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "testplan.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "review-findings.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "llm-technical.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "folders.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "test-coverage.md", "v{v}")
add_contains(REPO_ROOT / "docs-stm" / "managements" / "changelog.md", "[{v}]")
add_contains(REPO_ROOT / "docs-stm" / "manuals" / "how-to-test-my-code.md", "v{v}")


# ── 校验逻辑 ────────────────────────────────────────────────


def _check_exact(text: str, pattern_template: str, version: str) -> bool:
    pattern = pattern_template.replace("{v}", re.escape(version))
    return bool(re.search(pattern, text, re.MULTILINE))


def _check_contains(text: str, patterns_template: tuple[str, ...], version: str) -> bool:
    return any(p.replace("{v}", version) in text for p in patterns_template)


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
        else:
            ok = False

        if ok:
            print(f"  [OK] {rel}")
        else:
            print(f"  [ERR] {rel} — 版本号未同步，期望包含 {version}")
            all_ok = False

    print()
    if all_ok:
        print(f"[OK] 全部 {checked} 项通过 — 版本号一致")
        return

    if do_fix and fixed > 0:
        print(f"[!] 已自动修正 {fixed} 项（pyproject.toml）。其他文件需手动更新。")
        sys.exit(0)

    print("[ERR] 版本号不一致 — 请先手动更新后重试。")
    print("      发布流程：")
    print("        1. 修改 src/python/constants.py APP_VERSION")
    print("        2. 运行 python scripts/check-version-consistency.py")
    print("        3. 按 [ERR] 提示逐个更新文档版本号")
    print("        4. 再次运行确认全部 [OK]")
    print("        5. 提交 + 打标签")
    sys.exit(1)


if __name__ == "__main__":
    main()
