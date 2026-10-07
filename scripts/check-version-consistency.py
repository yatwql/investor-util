#!/usr/bin/env python3
"""版本号一致性检查脚本。

以 src/python/core/constants.py 的 APP_VERSION 为单一事实源，校验以下文件中的版本号与其一致：

  - pyproject.toml          version = "X.Y.Z"
  - README.md               > 当前版本：X.Y.Z
  - docs/managements/plan.md, technical.md, requirements.md,
    testplan.md, review-findings.md, llm-technical.md,
    folders.md, test-coverage.md
                            最后更新：...（vX.Y.Z ...）
  - docs/managements/developer-guide.md
                            最后更新：...（vX.Y.Z）
  - docs/managements/changelog.md
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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, rel as repo_rel  # noqa: E402

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
#     "evolution_head" → 版本演进对照表「当前开发版（」列头版本号锚定匹配
#                     （folders.md 滚动读数，发版须随版本头同步刷新）
#     "release_tag"   → 版本演进对照「最近发布 tag」列（表头 + 说明行全部出现处）
#                     == changelog 头部「最近发布 [X.Y.Z]（日期）」发布指针

CHECKS: list[tuple[Path, str, tuple[str, ...]]] = []


def add_exact(path: Path, pattern: str):
    CHECKS.append((REPO_ROOT / path, "exact", (pattern,)))


def add_contains(path: Path, *patterns: str):
    CHECKS.append((REPO_ROOT / path, "contains", patterns))


def add_header(path: Path):
    CHECKS.append((REPO_ROOT / path, "header", ()))


def add_evolution_head(path: Path):
    CHECKS.append((REPO_ROOT / path, "evolution_head", ()))


# 代码文件
CHECKS.append((REPO_ROOT / "pyproject.toml", "pyproject_version", ()))
CHECKS.append((REPO_ROOT / "src" / "python" / "core" / "constants.py", "exact", (r'^APP_VERSION\s*=\s*"[^"]*"$',)))

# Markdown 管理文档
add_exact(REPO_ROOT / "README.md", r"> 当前版本：{v}")
add_header(REPO_ROOT / "docs" / "managements" / "plan.md")
add_header(REPO_ROOT / "docs" / "managements" / "technical.md")
add_header(REPO_ROOT / "docs" / "managements" / "requirements.md")
add_header(REPO_ROOT / "docs" / "managements" / "testplan.md")
add_header(REPO_ROOT / "docs" / "managements" / "review-findings.md")
add_header(REPO_ROOT / "docs" / "managements" / "llm-technical.md")
add_header(REPO_ROOT / "docs" / "managements" / "folders.md")
# folders.md 版本演进对照表「当前开发版」列头版本号（同文件第二条断言，
# 与版本头双点同步——表头是文档化读数，漏改即报错）
add_evolution_head(REPO_ROOT / "docs" / "managements" / "folders.md")
# folders.md 版本演进「最新发布」列（表头 + 说明行）↔ changelog 发布指针单源
CHECKS.append(
    (
        REPO_ROOT / "docs" / "managements" / "folders.md",
        "release_tag",
        (REPO_ROOT / "docs" / "managements" / "changelog.md",),
    )
)
add_header(REPO_ROOT / "docs" / "managements" / "test-coverage.md")
# changelog 无「文档版本：」头，用 [X.Y.Z] 标题行 contains 校验
add_contains(REPO_ROOT / "docs" / "managements" / "changelog.md", "[{v}]")
add_header(REPO_ROOT / "docs" / "managements" / "developer-guide.md")


# ── 校验逻辑 ────────────────────────────────────────────────


def _check_contains(text: str, patterns_template: tuple[str, ...], version: str) -> bool:
    return any(p.replace("{v}", version) in text for p in patterns_template)


def _check_header(text: str, version: str) -> bool:
    """校验「文档版本：」头部版本行与目标版本精确一致（行首锚定）。

    仅匹配整行 `> 文档版本：{version}`，避免正文偶然出现的版本号
    导致全文 contains 误判。
    """
    pattern = rf"^[ \t]*>[ \t]*文档版本：{re.escape(version)}[ \t]*$"
    return bool(re.search(pattern, text, re.MULTILINE))


def _auto_fix_header(path: Path, version: str) -> bool:
    """自动修正「文档版本：」头部版本行为目标版本。

    行首空白类只用同行字符（`[ \t]`）——`\s` 含换行，原 `^\s*>` 在 MULTILINE 下
    会把版本头前的空行一并吞掉（H1 与版本头之间有空行的文档会丢格式）。
    """
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"^[ \t]*>[ \t]*文档版本：.*$",
        lambda m: f"> 文档版本：{version}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count > 0 and new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def _check_evolution_head(text: str, version: str) -> bool:
    """校验版本演进对照表「当前开发版（」列头版本号与目标版本一致。

    锚定 `当前开发版（` 后的第一个版本号（单点定位，说明行用 `=` 不参与）；
    列头缺失版本号或与目标不符均判未同步——该读数随版本头同步刷新。
    """
    m = re.search(r"当前开发版（\s*`?v?(\d+\.\d+\.\d+(?:-dev)?)", text)
    return bool(m) and m.group(1) == version


def _auto_fix_evolution_head(path: Path, version: str) -> bool:
    """自动修正版本演进对照表「当前开发版（」列头版本号（无号则插入）。"""
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r"(当前开发版（\s*`?v?)\d+\.\d+\.\d+(?:-dev)?",
        lambda m: m.group(1) + version,
        text,
        count=1,
    )
    if count == 0:
        new_text, count = re.subn(
            r"(当前开发版（)",
            lambda m: m.group(1) + version + " · ",
            text,
            count=1,
        )
    if count > 0 and new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


# ── 发布指针（changelog 头部「最近发布 [X.Y.Z]（日期）」= 发布单源） ──
# 注：changelog 指针行带 `**` 加粗标记，允许 `]` 后 0..2 个星号再接全角括号
_RELEASE_PTR_RE = re.compile(r"最近发布\s*\*{0,2}\s*\[(\d+\.\d+\.\d+)\]\s*\*{0,2}\s*[（(](\d{4}-\d{2}-\d{2})[）)]")
_RELEASE_COL_RE = re.compile(
    r"最近(?:一次)?发布\s*`?tag`?\s*[（(]?\s*`?v?(\d+\.\d+\.\d+)(?:\s*·\s*|\s+)(\d{4}-\d{2}-\d{2})?"
)


def _latest_release_pointer(changelog_text: str) -> tuple[str, str] | None:
    """从 changelog 头部提取发布指针（版本, 日期）；无指针行返回 None。"""
    m = _RELEASE_PTR_RE.search(changelog_text)
    return (m.group(1), m.group(2)) if m else None


def _check_release_tag(text: str, changelog_text: str) -> bool:
    """校验版本演进「最近发布 tag」全部出现处（表头 + 说明行）== changelog 发布指针。

    changelog 头部「最近发布」行是发布记录单源；folders 表头与说明行是它的
    投影，出现处缺失或任一处版本/日期不符均判未同步（防发版后静默过期）。
    """
    ptr = _latest_release_pointer(changelog_text)
    if ptr is None:
        return False
    ver, date = ptr
    hits = _RELEASE_COL_RE.findall(text)
    if not hits:
        return False
    return all(v == ver and d == date for v, d in hits)


def _auto_fix_release_tag(path: Path, changelog_path: Path) -> bool:
    """把版本演进「最近发布 tag」所有出现处同步为 changelog 发布指针（版本 + 日期）。"""
    ptr = _latest_release_pointer(changelog_path.read_text(encoding="utf-8"))
    if ptr is None:
        return False
    ver, date = ptr
    text = path.read_text(encoding="utf-8")
    new_text = re.sub(
        r"(最近(?:一次)?发布\s*`?tag`?\s*[（(]?\s*`?v?)\d+\.\d+\.\d+",
        lambda m: m.group(1) + ver,
        text,
    )
    new_text = re.sub(
        r"(最近(?:一次)?发布[^\n]*?tag[^\n]*?)\d{4}-\d{2}-\d{2}",
        lambda m: m.group(1) + date,
        new_text,
    )
    if new_text != text:
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
    ci_mode = "--ci" in sys.argv

    if not ci_mode:
        print(f"[..] 校验版本号一致性 — APP_VERSION = {version}\n     来源：{repo_rel(CONSTANTS_FILE)}\n")

    all_ok = True
    checked = 0
    fixed = 0

    for full_path, assert_type, args in CHECKS:
        checked += 1
        rel = full_path.relative_to(REPO_ROOT)

        rel = repo_rel(full_path)
        if not full_path.exists():
            if not ci_mode:
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
        elif assert_type == "evolution_head":
            ok = _check_evolution_head(text, version)
            if not ok and do_fix:
                if _auto_fix_evolution_head(full_path, version):
                    print(f"  [OK] {rel} — 已自动修正版本演进表头版本号为 {version}")
                    fixed += 1
                    ok = True
        elif assert_type == "release_tag":
            changelog_text = args[0].read_text(encoding="utf-8")
            ok = _check_release_tag(text, changelog_text)
            if not ok and do_fix:
                if _auto_fix_release_tag(full_path, args[0]):
                    print(f"  [OK] {rel} — 已自动同步「最近发布 tag」为 changelog 发布指针")
                    fixed += 1
                    ok = True
        else:
            ok = False

        if ok:
            if not ci_mode:
                print(f"  [OK] {rel}")
        else:
            if assert_type == "header":
                print(
                    f"{rel}: 头部版本行未同步，期望 `> 文档版本：{version}`"
                    if ci_mode
                    else f"  [ERR] {rel} — 头部版本行未同步，期望 `> 文档版本：{version}`"
                )
            elif assert_type == "evolution_head":
                print(
                    f"{rel}: 版本演进对照「当前开发版」列头版本号未同步，期望 `{version}`"
                    if ci_mode
                    else f"  [ERR] {rel} — 版本演进对照「当前开发版」列头版本号未同步，期望 `{version}`"
                )
            elif assert_type == "release_tag":
                print(
                    f"{rel}: 版本演进「最近发布 tag」与 changelog 发布指针不一致（单源：changelog 头部「最近发布 [X.Y.Z]（日期）」）"
                    if ci_mode
                    else f"  [ERR] {rel} — 版本演进「最近发布 tag」与 changelog 发布指针不一致（单源：changelog 头部「最近发布 [X.Y.Z]（日期）」，可用 --fix 自动同步）"
                )
            else:
                print(
                    f"{rel}: 版本号未同步，期望包含 {version}"
                    if ci_mode
                    else f"  [ERR] {rel} — 版本号未同步，期望包含 {version}"
                )
            all_ok = False

    if not ci_mode:
        print()
    if all_ok:
        print(f"[OK] 全部 {checked} 项通过 — 版本号一致")
        return

    if do_fix and fixed > 0:
        print(f"[!] 已自动修正 {fixed} 项（pyproject 版本字段 / 管理文档头部版本行）。其他文件需手动更新。")
        sys.exit(0)

    if not ci_mode:
        print("[ERR] 版本号不一致 — 请先手动更新后重试。")
        print("      发布流程：")
        print("        1. 修改 src/python/core/constants.py APP_VERSION")
        print("        2. 运行 python scripts/check-version-consistency.py")
        print("        3. 按 [ERR] 提示逐个更新文档版本号")
        print("        4. 再次运行确认全部 [OK]")
        print("        5. 提交 + 打标签")
    sys.exit(2)  # 契约：发现 finding → 退出码 2


if __name__ == "__main__":
    main()
