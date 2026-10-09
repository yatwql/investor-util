#!/usr/bin/env python3
"""发布流程分步编排脚本 —— 把发布口径从文档散文固化为可执行子命令。

七个分步子命令（每步独立可审阅、失败即停不连锁，按序执行）：

    check      预检：分支 / 工作树干净 / 版本形态 / tag 未占用 / 版本一致性
    prepare    文档手术：版本全链（constants + README + --fix 传播）+ changelog
               发布段迁入归档、指针与归档索引改写（changelog 段由本步自动完成）；
               rf 已解决条目 / plan 已完成任务 / docs/plan 已完成任务设计文件三项归档迁移为
               人工强制项（未完成不得继续 gate/publish）
    refresh    数据刷新：bench --update-docs + collect-test-coverage + doc-drift --sync
    evolution  版本演进对照快照：git 清单 + 逐文件行数口径；默认只滚「当前开发版」列，
               `--release` 时发布列与增长比一并写入（发布期在 prepare 之后执行）
    gate       P2 门禁：`--mode regression` + 十守护 `--ci`（清单与门禁文档同源）
    publish    release 提交 + P1 verify + --no-ff 合并 dev→master + tag（默认不推送）
    devbump    切下一开发版 X.Y.(Z+1)-dev + chore 提交

典型发布序列：
    .venv/bin/python scripts/release.py check
    .venv/bin/python scripts/release.py prepare
    .venv/bin/python scripts/release.py refresh
    .venv/bin/python scripts/release.py evolution --release
    .venv/bin/python scripts/release.py gate
    .venv/bin/python scripts/release.py publish --title "<发布主题>"
    .venv/bin/python scripts/release.py devbump

退出码：0 = 通过；2 = 预检/门禁发现（与守护脚本 CLI 契约一致）；1 = 执行失败。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_FILE = REPO_ROOT / "src" / "python" / "core" / "constants.py"
README_FILE = REPO_ROOT / "README.md"
CHANGELOG_FILE = REPO_ROOT / "docs" / "managements" / "changelog.md"
FOLDERS_FILE = REPO_ROOT / "docs" / "managements" / "folders.md"
TEST_COVERAGE_FILE = REPO_ROOT / "docs" / "managements" / "test-coverage.md"

# P2 十守护清单（与 CLAUDE.md / testplan.md / developer-guide.md / ci.yml / pre-commit 钩子同源）
GUARD_SCRIPTS = [
    "scripts/check-code-traces.py",
    "scripts/check-doc-traces.py",
    "scripts/check-task-numbering.py",
    "scripts/check-semantic-index.py",
    "scripts/check-doc-drift.py",
    "scripts/check-test-redundancy.py",
    "scripts/check-requirement-trace.py",
    "scripts/check-version-consistency.py",
    "scripts/check-doc-links.py",
    "scripts/check-file-length.py",
]

_DEV_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)-dev$")
_RELEASE_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_APP_VERSION_LINE_RE = re.compile(r'^APP_VERSION = "([^"]+)"', re.M)


class ReleaseError(RuntimeError):
    """命令无法继续（预检不过 / 输入不符合契约）；消息即用户可读原因。"""


# ─────────────────────────── 基础执行与版本纯函数 ───────────────────────────


def _exec(cmd: list[str], root: Path, runner=None, capture: bool = True) -> tuple[int, str, str]:
    """执行外部命令（显式 UTF-8 解码，避免非 UTF-8 locale 下的隐式编码）。"""
    if runner is not None:
        return runner.run(cmd, root, capture=capture)
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(root),
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def read_app_version(text: str) -> str:
    m = _APP_VERSION_LINE_RE.search(text)
    if not m:
        raise ReleaseError("constants.py 中未找到 APP_VERSION 行")
    return m.group(1)


def render_app_version(text: str, version: str) -> str:
    new_text, n = _APP_VERSION_LINE_RE.subn(f'APP_VERSION = "{version}"', text, count=1)
    if n != 1:
        raise ReleaseError("constants.py 中未找到 APP_VERSION 行")
    return new_text


def release_version_of(dev_version: str) -> str:
    m = _DEV_VERSION_RE.match(dev_version)
    if not m:
        raise ReleaseError(f"当前版本 {dev_version} 不是 X.Y.Z-dev 形态（发布前应处于开发版）")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"


def next_dev_version_of(release_version: str) -> str:
    m = _RELEASE_VERSION_RE.match(release_version)
    if not m:
        raise ReleaseError(f"{release_version} 不是 X.Y.Z 发布版形态")
    return f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}-dev"


def render_readme_version(text: str, version: str) -> str:
    new_text, n = re.subn(r"^(> 当前版本：)[^\s（]+", lambda m: m.group(1) + version, text, count=1, flags=re.M)
    if n != 1:
        raise ReleaseError("README.md 中未找到「> 当前版本：」行")
    return new_text


def normalize_release_title(title: str) -> str:
    """剥离 `--title` 中多余的 `release: v… —— ` 前缀。

    commit subject 由 publish 统一加前缀；title 自带前缀时会拼出双前缀
    （发布提交实测）。剥离后为空（title 本身就是前缀）则按原样使用。
    """
    stripped = re.sub(r"^release:\s*v\S+\s*—+\s*", "", title.strip())
    return stripped or title.strip()


def archive_paths_for(release_version: str) -> tuple[Path, str]:
    """按小版本推导归档目录与文件名（小版本号 → docs/archive/vX.Y.x/… 目录）。"""
    m = _RELEASE_VERSION_RE.match(release_version)
    if not m:
        raise ReleaseError(f"{release_version} 不是 X.Y.Z 发布版形态")
    minor = f"{m.group(1)}.{m.group(2)}"
    name = f"archived_changelog.{minor}.x.md"
    return REPO_ROOT / "docs" / "archive" / f"v{minor}.x" / name, name


# ─────────────────────────── changelog 发布段迁移 ───────────────────────────

_SECTION_NOTE = "（本次发布内容见下方归档索引）"


def _find_section(text: str) -> tuple[int, int, str]:
    """定位当前开发段（含正文），返回 (起点, 终点, 段内版本号)；终点=下一 ## 行。"""
    header = re.search(r"^## \[([^\]]+)\] - 开发中（未发布）\s*$", text, re.M)
    if not header:
        raise ReleaseError("changelog 未找到「开发中（未发布）」段")
    next_header = re.search(r"^## ", text[header.end() :], re.M)
    if not next_header:
        raise ReleaseError("changelog 开发段之后没有归档章节")
    return header.start(), header.end() + next_header.start(), header.group(1)


def apply_changelog_release(text: str, release_version: str, date: str) -> tuple[str, str]:
    """发布段迁出：改指针、改归档索引、清空开发段并生成下一开发段。

    返回 (新主文件文本, 迁出的发布段正文)。纯文本变换，不落盘。
    """
    section_start, section_end, current_dev = _find_section(text)
    if current_dev != f"{release_version}-dev":
        raise ReleaseError(f"changelog 开发段 {current_dev} 与目标发布版 {release_version} 不一致")

    body = text[section_start:section_end]
    # 迁出正文 = 段头之后到段尾注之前（尾注只属于主文件的占位说明）
    body_core = body.split("\n", 1)[1] if "\n" in body else ""
    body_core = re.sub(rf"^\s*\n*{re.escape(_SECTION_NOTE)}\s*$", "", body_core, flags=re.M)
    body_core = body_core.strip("\n")

    next_dev = next_dev_version_of(release_version)
    new_section = f"## [{next_dev}] - 开发中（未发布）\n\n\n{_SECTION_NOTE}\n\n"

    out = text[:section_start] + new_section + text[section_end:]

    out, n_ptr = re.subn(
        r"^(> \*\*最近发布 \[)[\d.]+(\]\*\*（)[\d-]+(）)",
        lambda m: m.group(1) + release_version + m.group(2) + date + m.group(3),
        out,
        count=1,
        flags=re.M,
    )
    if n_ptr != 1:
        raise ReleaseError("changelog 未找到「最近发布」指针行")

    _, archive_name = archive_paths_for(release_version)
    idx_pat = re.compile(
        rf"^(- \[`{re.escape(archive_name)}`\]\([^)]*\)\s*—\s*[^（]*?)"
        r"(v[\d.]+)( ~ v[\d.]+)?（(\d{4}-\d{2}-\d{2})( ~ \d{4}-\d{2}-\d{2})?）",
        re.M,
    )
    if archive_name not in out:
        raise ReleaseError(f"changelog 归档索引中没有 {archive_name} 行（新小版本需先手工建归档文件）")

    def _idx_repl(m: re.Match) -> str:
        head, start_v, tail_v, start_d, tail_d = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
        end_v = f" ~ v{release_version}" if tail_v else ""
        end_d = f" ~ {date}" if tail_d else ""
        return f"{head}{start_v}{end_v}（{start_d}{end_d}）"

    out, n_idx = idx_pat.subn(_idx_repl, out, count=1)
    if n_idx != 1:
        raise ReleaseError("changelog 归档索引行改写失败（格式与预期不符）")
    return out, body_core


def write_archive_release(archive_file: Path, release_version: str, date: str, body_core: str) -> None:
    """把发布段正文追加到归档文件（`## [X.Y.Z] - 日期` 头，段间空行、无分隔线）。"""
    if not archive_file.exists():
        raise ReleaseError(f"归档文件不存在：{archive_file}")
    old = archive_file.read_text(encoding="utf-8")
    block = f"## [{release_version}] - {date}\n\n{body_core.strip()}\n\n"
    archive_file.write_text(old.rstrip("\n") + "\n\n" + block.strip("\n") + "\n", encoding="utf-8")


# ─────────────────────────── 预检 ───────────────────────────


def _current_branch(root: Path, runner=None) -> str:
    rc, out, _ = _exec(["git", "branch", "--show-current"], root, runner)
    return out.strip() if rc == 0 else ""


def _worktree_clean(root: Path, runner=None) -> bool:
    rc, out, _ = _exec(["git", "status", "--porcelain"], root, runner)
    return rc == 0 and out.strip() == ""


def _tag_absent(root: Path, tag: str, runner=None) -> bool:
    rc, _, _ = _exec(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], root, runner)
    return rc != 0


def run_preflight(
    root: Path, expect_release: bool = False, runner=None, require_clean: bool = True
) -> list[tuple[str, bool, str]]:
    """前置条件 + 版本一致性；返回 [(检查名, 是否通过, 详情)]。

    ``require_clean=False`` 供 publish 使用——彼时 prepare 手术改动尚待提交，属预期状态。
    """
    results: list[tuple[str, bool, str]] = []
    branch = _current_branch(root, runner)
    results.append(("工作分支为 dev", branch == "dev", f"当前分支：{branch or '<获取失败>'}"))
    if require_clean:
        clean = _worktree_clean(root, runner)
        results.append(("工作树干净", clean, "有未提交改动" if not clean else "无未提交改动"))

    constants_path = root / "src" / "python" / "core" / "constants.py"
    try:
        version = read_app_version(constants_path.read_text(encoding="utf-8"))
    except (OSError, ReleaseError) as exc:
        results.append(("版本形态", False, f"读取 APP_VERSION 失败：{exc}"))
        version = ""
    if version:
        if expect_release:
            ok = bool(_RELEASE_VERSION_RE.match(version))
            results.append(("版本为发布形态", ok, f"APP_VERSION = {version}"))
        else:
            ok = bool(_DEV_VERSION_RE.match(version))
            results.append(("版本为开发形态", ok, f"APP_VERSION = {version}"))
        if ok:
            rel = version if expect_release else release_version_of(version)
            results.append((f"tag v{rel} 未占用", _tag_absent(root, f"v{rel}", runner), "已存在则发布会被拒"))

    rc, out, _ = _exec([sys.executable, "scripts/check-version-consistency.py", "--ci"], root, runner)
    results.append(("版本号一致性", rc == 0, (out or "").strip().splitlines()[0] if (out or "").strip() else ""))
    return results


def _print_results(results: list[tuple[str, bool, str]]) -> bool:
    all_ok = True
    for name, ok, detail in results:
        mark = "[OK]" if ok else "[ERR]"
        all_ok = all_ok and ok
        print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return all_ok


def cmd_check(args: argparse.Namespace, runner=None) -> int:
    print("[..] 发布预检")
    ok = _print_results(run_preflight(REPO_ROOT, expect_release=False, runner=runner))
    if not ok:
        print("[ERR] 预检未通过，先处理上述项再继续")
        return 2
    print("[OK] 预检通过 — 可执行 prepare")
    return 0


# ─────────────────────────── prepare ───────────────────────────


def cmd_prepare(args: argparse.Namespace, runner=None) -> int:
    constants_text = CONSTANTS_FILE.read_text(encoding="utf-8")
    dev_version = read_app_version(constants_text)
    release_version = args.version or release_version_of(dev_version)
    if args.version and args.version != release_version_of(dev_version):
        print(f"[!] --version {args.version} 与当前 {dev_version} 推导结果 {release_version} 不一致，按推导执行")
    date = args.date or _dt.date.today().isoformat()

    print("[..] prepare 预检（发布形态前的开发态条件）")
    if not _print_results(run_preflight(REPO_ROOT, expect_release=False, runner=runner)):
        print("[ERR] 预检未通过，prepare 中止（未写入任何文件）")
        return 2

    main_text = CHANGELOG_FILE.read_text(encoding="utf-8")
    new_main, body_core = apply_changelog_release(main_text, release_version, date)
    archive_file, _ = archive_paths_for(release_version)
    write_archive_release(archive_file, release_version, date, body_core)
    CHANGELOG_FILE.write_text(new_main, encoding="utf-8")

    next_dev = next_dev_version_of(release_version)
    CONSTANTS_FILE.write_text(render_app_version(constants_text, release_version), encoding="utf-8")
    README_FILE.write_text(
        render_readme_version(README_FILE.read_text(encoding="utf-8"), release_version), encoding="utf-8"
    )
    print(f"[OK] 版本全链 → {release_version}（changelog 段迁入 {archive_file.name}，新开发段 {next_dev}）")

    rc, out, err = _exec([sys.executable, "scripts/check-version-consistency.py", "--fix"], REPO_ROOT, runner)
    print((out or err).rstrip())
    if rc != 0:
        print("[ERR] 版本一致性 --fix 未收敛，按上方 [ERR] 逐个处理后重跑 prepare")
        return rc

    rc, status_out, _ = _exec(["git", "status", "--short"], REPO_ROOT, runner)
    if rc == 0 and status_out.strip():
        print("\n[..] 本次改动清单（请审阅 diff）：")
        print(status_out.rstrip())
    print("\n[OK] prepare 完成。后续人工项：")
    print("  1. 审阅 git diff（重点：changelog 指针/归档索引、演进列头）")
    print(
        "  2. 发布归档迁移（强制）：rf 已解决条目 + plan 已完成任务 + docs/plan 已完成任务设计文件迁档（changelog 段已由本步自动完成），未完成不得继续 gate/publish"
    )
    print("  3. 按序继续：refresh → evolution --release → gate → publish → devbump")
    return 0


# ─────────────────────────── refresh ───────────────────────────


def _run_step(label: str, cmd: list[str], root: Path, runner=None) -> int:
    print(f"[..] {label}")
    rc, out, err = _exec(cmd, root, runner)
    if out.strip():
        print(out.rstrip())
    if rc != 0:
        if err.strip():
            print(err.rstrip())
        print(f"[ERR] {label} 退出码 {rc}（按输出处理后重跑本子命令）")
        return rc
    print(f"[OK] {label}")
    return 0


def cmd_refresh(args: argparse.Namespace, runner=None) -> int:
    steps = [
        ("测试量与耗时快照回填", [sys.executable, "scripts/test-runner.py", "--mode", "bench", "--update-docs"]),
        ("测试收集计数回填", [sys.executable, "scripts/collect-test-coverage.py"]),
        ("文档统计快照回写", [sys.executable, "scripts/check-doc-drift.py", "--sync"]),
    ]
    for label, cmd in steps:
        rc = _run_step(label, cmd, REPO_ROOT, runner)
        if rc != 0:
            return rc
    print("[OK] refresh 完成")
    return 0


# ─────────────────────────── evolution ───────────────────────────


def _line_count(data: bytes) -> int:
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def build_evolution_stats(root: Path, runner=None) -> dict[str, int]:
    """按 folders.md「复现方法」口径统计：git 清单 + 逐文件精确行数（工作区直读）。"""
    rc, out, err = _exec(["git", "ls-files"], root, runner)
    if rc != 0:
        raise ReleaseError(f"git ls-files 失败：{err.strip()}")
    paths = [p for p in out.splitlines() if p.strip()]

    cats: dict[str, list[str]] = {"main": [], "test": [], "scripts": [], "tmpl": [], "svg": [], "md": []}
    missing: list[str] = []
    lines: dict[str, int] = {}
    for rel in paths:
        full = root / rel
        try:
            data = full.read_bytes()
        except OSError:
            missing.append(rel)
            continue
        lines[rel] = _line_count(data)
        if rel.endswith(".py"):
            if rel.startswith("src/test/"):
                cats["test"].append(rel)
            elif rel.startswith("src/"):
                cats["main"].append(rel)
            elif rel.startswith("scripts/"):
                cats["scripts"].append(rel)
        elif rel.endswith(".html") and rel.startswith("src/static/tmpl/"):
            cats["tmpl"].append(rel)
        elif rel.endswith(".svg"):
            cats["svg"].append(rel)
        elif rel.endswith(".md"):
            cats["md"].append(rel)

    def pair(name: str) -> tuple[int, int]:
        fs = cats[name]
        return len(fs), sum(lines[p] for p in fs)

    main_f, main_l = pair("main")
    test_f, test_l = pair("test")
    scripts_f, scripts_l = pair("scripts")
    tmpl_f, tmpl_l = pair("tmpl")
    svg_f, svg_l = pair("svg")
    md_f, md_l = pair("md")

    test_bytes = [(root / p).read_bytes() for p in cats["test"]]
    def_test_lines = sum(1 for data in test_bytes for ln in data.split(b"\n") if b"def test_" in ln)
    def_test_strict = sum(1 for data in test_bytes for ln in data.split(b"\n") if ln.lstrip().startswith(b"def test_"))

    five_files = main_f + test_f + scripts_f + tmpl_f + svg_f
    five_lines = main_l + test_l + scripts_l + tmpl_l + svg_l
    return {
        "main_files": main_f,
        "main_lines": main_l,
        "test_files": test_f,
        "test_lines": test_l,
        "scripts_files": scripts_f,
        "scripts_lines": scripts_l,
        "tmpl_files": tmpl_f,
        "tmpl_lines": tmpl_l,
        "svg_files": svg_f,
        "svg_lines": svg_l,
        "md_files": md_f,
        "md_lines": md_l,
        "five_files": five_files,
        "five_lines": five_lines,
        "def_test_lines": def_test_lines,
        "def_test_strict": def_test_strict,
        "repo_files": len(paths),
        "repo_lines": sum(lines[p] for p in paths),
        "missing": len(missing),
    }


def _fmt_pair(files: int, lines_n: int) -> str:
    return f"{files} 文件 / {lines_n:,} 行"


def _growth(base_value: int, cur_value: int, override: str | None = None) -> str:
    if override:
        return override
    if base_value == 0:
        return "新增"
    return f"{cur_value / base_value:.1f}×"


def _cell_number(cell: str) -> int:
    m = re.search(r"(\d[\d,]*)", cell)
    if not m:
        raise ReleaseError(f"基线单元格无数字：{cell!r}")
    return int(m.group(1).replace(",", ""))


def update_evolution_table(text: str, stats: dict[str, int], with_release: bool, date: str) -> str:
    """改写演进对照表：指标行两列 + 增长列 + 当前开发版列头日期；`with_release` 时发布列同写。"""
    rows: list[tuple[str, int, int, str | None]] = [
        # (行标签锚, 发布列值, 开发列值, 增长格式覆盖)
        ("| 主程序（", stats["main_lines"], stats["main_lines"], None),
        ("| 测试（", stats["test_lines"], stats["test_lines"], None),
        ("| 辅助脚本（", stats["scripts_lines"], stats["scripts_lines"], None),
        ("| HTML 报告模板（", stats["tmpl_lines"], stats["tmpl_lines"], f"1 → {stats['tmpl_files']}"),
        ("| 架构图示（", stats["svg_lines"], stats["svg_lines"], None),
        ("| 文档（", stats["md_lines"], stats["md_lines"], None),
        ("| **代码文件合计**", stats["five_files"], stats["five_files"], None),
        ("| **代码行合计**", stats["five_lines"], stats["five_lines"], None),
        ("| **测试用例数**", stats["def_test_lines"], stats["def_test_lines"], None),
        ("| 仓库文件总数", stats["repo_files"], stats["repo_files"], None),
        ("| 仓库总行数", stats["repo_lines"], stats["repo_lines"], None),
    ]
    out_lines: list[str] = []
    seen: set[str] = set()
    for line in text.split("\n"):
        hit = next((anchor for anchor, _, _, _ in rows if line.startswith(anchor)), None)
        if hit is None:
            out_lines.append(line)
            continue
        rel_val, dev_val, override = next((r[1], r[2], r[3]) for r in rows if r[0] == hit)
        cells = line.split("|")
        if len(cells) < 6:
            out_lines.append(line)
            continue
        base_cell = cells[2]
        bold = "**" in cells[3]
        pair_rows = hit in {"| 主程序（", "| 测试（", "| 辅助脚本（", "| HTML 报告模板（", "| 架构图示（", "| 文档（"}
        if pair_rows:
            # 行数指标行的增长比以「行数」为基准；基线以 0 开头（历史布局差异）直接判「新增」
            if re.match(r"\s*0(?!\d)", base_cell):
                base_val = 0
            else:
                ml = re.search(r"(\d[\d,]*) 文件 / (\d[\d,]*) 行", base_cell)
                base_val = int(ml.group(2).replace(",", "")) if ml else _cell_number(base_cell)
            files_key = {
                "| 主程序（": "main_files",
                "| 测试（": "test_files",
                "| 辅助脚本（": "scripts_files",
                "| HTML 报告模板（": "tmpl_files",
                "| 架构图示（": "svg_files",
                "| 文档（": "md_files",
            }[hit]
            rel_cell = _fmt_pair(stats[files_key], rel_val)
            dev_cell = _fmt_pair(stats[files_key], dev_val)
        else:
            base_val = _cell_number(base_cell)
            fmt = (lambda v: f"**{v:,}**") if bold else (lambda v: f"{v:,}")
            rel_cell = fmt(rel_val)
            dev_cell = fmt(dev_val)
        growth = _growth(base_val, dev_val, override)
        cells[3] = f" {rel_cell} " if with_release else cells[3]
        cells[4] = f" {dev_cell} "
        cells[5] = f" {growth}"
        out_lines.append("|".join(cells))
        seen.add(hit)
    missing_rows = [anchor for anchor, _, _, _ in rows if anchor not in seen]
    if missing_rows:
        raise ReleaseError(f"演进对照表缺行：{missing_rows}")
    result = "\n".join(out_lines)

    result, n_date = re.subn(
        r"(当前开发版（[^）]*?· 本次重跑时的工作区 · )\d{4}-\d{2}-\d{2}",
        lambda m: m.group(1) + date,
        result,
        count=1,
    )
    if n_date != 1:
        raise ReleaseError("演进对照表「当前开发版」列头日期模式缺失（列头格式变化时先同步本工具）")
    return result


def update_ratio_note(text: str, stats: dict[str, int], with_release: bool) -> str:
    """测试/主程序行数比注释：`--release` 时最新发布点一并改写，否则只滚当前工作区。

    两种目标模式任一缺失即抛 `ReleaseError`——宁可硬失败也不产出半新半旧的注释。
    """
    ratio = stats["test_lines"] / stats["main_lines"] if stats["main_lines"] else 0.0
    pair = f"{stats['test_lines']:,} / {stats['main_lines']:,}"
    if with_release:
        text, n_release = re.subn(
            r"升至 \*\*[\d.]+:\d\*\*（[\d,]+ / [\d,]+，最新发布点）",
            f"升至 **{ratio:.2f}:1**（{pair}，最新发布点）",
            text,
            count=1,
        )
        if n_release != 1:
            raise ReleaseError("比值注释「最新发布点」模式缺失（注释格式变化时先同步本工具）")
    text, n_ws = re.subn(
        r"当前工作区为 \*\*[\d.]+:\d\*\*（[\d,]+ / [\d,]+）",
        f"当前工作区为 **{ratio:.2f}:1**（{pair}）",
        text,
        count=1,
    )
    if n_ws != 1:
        raise ReleaseError("比值注释「当前工作区为」模式缺失（注释格式变化时先同步本工具）")
    return text


def update_case_note(text: str, stats: dict[str, int]) -> str:
    """用例口径注释中的 grep / 严格定义行数；pytest 收集口径留人工核对提示。

    目标短语在真实文档中位于行中（非行首），不做行首锚定；模式缺失即抛
    `ReleaseError`（不静默漏更、不留滞留计数）。
    """
    text, n_grep = re.subn(
        r"(最初 \d+ → 当前 )[\d,]+",
        lambda m: m.group(1) + f"{stats['def_test_lines']:,}",
        text,
        count=1,
    )
    if n_grep != 1:
        raise ReleaseError("用例口径注释「最初 → 当前」模式缺失（注释格式变化时先同步本工具）")
    text, n_strict = re.subn(
        r"口径为 [\d,]+；",
        f"口径为 {stats['def_test_strict']:,}；",
        text,
        count=1,
    )
    if n_strict != 1:
        raise ReleaseError("用例口径注释「口径为」模式缺失（注释格式变化时先同步本工具）")
    return text


def cmd_evolution(args: argparse.Namespace, runner=None) -> int:
    print("[..] 版本演进快照（git 清单 + 逐文件行数）")
    stats = build_evolution_stats(REPO_ROOT, runner)
    if stats["missing"]:
        print(f"[!] {stats['missing']} 个跟踪文件在工作区缺失（已跳过计数）")
    text = FOLDERS_FILE.read_text(encoding="utf-8")
    date = _dt.date.today().isoformat()
    try:
        text = update_evolution_table(text, stats, with_release=args.release, date=date)
        text = update_ratio_note(text, stats, with_release=args.release)
        text = update_case_note(text, stats)
    except ReleaseError as exc:
        print(f"[ERR] {exc}")
        return 2
    FOLDERS_FILE.write_text(text, encoding="utf-8")
    scope = "发布列 + 当前开发版列" if args.release else "当前开发版列（发布列不动）"
    print(f"[OK] 演进对照已更新：{scope}（{date}）")
    print(
        "     摘要："
        + ", ".join(
            [
                f"主程序 {_fmt_pair(stats['main_files'], stats['main_lines'])}",
                f"测试 {_fmt_pair(stats['test_files'], stats['test_lines'])}",
                f"用例 {stats['def_test_lines']:,}（严格 {stats['def_test_strict']:,}）",
            ]
        )
    )
    print("[..] 需人工核对的注释行（脚本不代写）：")
    print("  - 用例口径注释中的 pytest 实际收集数与 opt-in live 项数（见 test-coverage.md）")
    print("  - 「文档」注释行的目录分解数（根/管理/手册/计划/归档）")
    return 0


# ─────────────────────────── gate ───────────────────────────


def cmd_gate(args: argparse.Namespace, runner=None) -> int:
    print("[..] P2 门禁：场景回归")
    rc, out, err = _exec([sys.executable, "scripts/test-runner.py", "--mode", "regression"], REPO_ROOT, runner)
    if out.strip():
        print(out.rstrip())
    if rc != 0:
        if err.strip():
            print(err.rstrip())
        print("[ERR] 场景回归未通过，P2 中止")
        return rc if rc != 0 else 1
    print("[OK] 场景回归通过\n")

    print("[..] P2 门禁：十守护 --ci")
    worst = 0
    for script in GUARD_SCRIPTS:
        rc, out, err = _exec([sys.executable, script, "--ci"], REPO_ROOT, runner)
        if rc == 0:
            print(f"  [OK] {Path(script).name}")
        else:
            print(f"  [ERR] {Path(script).name}（退出码 {rc}）")
            if out.strip():
                print("    " + out.strip().replace("\n", "\n    "))
            if err.strip():
                print("    " + err.strip().replace("\n", "\n    "))
            worst = max(worst, rc) if rc in (1, 2, 3) else 1
    if worst:
        print("[ERR] P2 守护存在 finding，先修复再发布")
        return worst
    print("[OK] P2 门禁全绿（regression + 十守护）")
    return 0


# ─────────────────────────── publish / devbump ───────────────────────────


def _git_ok(args: list[str], root: Path, runner=None, capture: bool = True) -> tuple[int, str, str]:
    return _exec(["git", *args], root, runner, capture=capture)


def cmd_publish(args: argparse.Namespace, runner=None) -> int:
    print("[..] publish 预检（发布形态；工作树此时允许带 prepare 待提交改动）")
    if not _print_results(run_preflight(REPO_ROOT, expect_release=True, runner=runner, require_clean=False)):
        print("[ERR] 预检未通过，publish 中止")
        return 2
    release_version = read_app_version(CONSTANTS_FILE.read_text(encoding="utf-8"))

    rc, staged, _ = _git_ok(["status", "--porcelain"], REPO_ROOT, runner)
    if rc != 0:
        return 1
    if staged.strip():
        _git_ok(["add", "-A"], REPO_ROOT, runner)
        rc, out, err = _git_ok(
            ["commit", "-m", f"release: v{release_version} —— {normalize_release_title(args.title)}"],
            REPO_ROOT,
            runner,
        )
        if rc != 0:
            print(f"[ERR] release 提交失败：{(err or out).strip()}")
            return rc
        print(f"[OK] release 提交完成（v{release_version}）")
    else:
        print("[OK] release 提交已存在，跳过")

    print("[..] P1 合入门禁：--mode verify")
    rc, out, err = _exec([sys.executable, "scripts/test-runner.py", "--mode", "verify"], REPO_ROOT, runner)
    if out.strip():
        print(out.rstrip())
    if rc != 0:
        if err.strip():
            print(err.rstrip())
        print("[ERR] P1 verify 未通过 —— 已停在 release 提交，修复后重跑 publish（提交步骤会自动跳过）")
        return rc
    counts = re.findall(r"(\d[\d,]*) 通过", out)
    passed = counts[-1].replace(",", "") if counts else ""
    print(f"[OK] P1 verify 通过（{passed or '见报告'} 项）")

    rc, out, err = _git_ok(["checkout", "master"], REPO_ROOT, runner)
    if rc != 0:
        print(f"[ERR] 切换 master 失败：{(err or out).strip()}")
        return rc
    merge_msg = (
        f"merge: dev → master，发布 v{release_version}（P1 verify {passed} 项已全绿）"
        if passed
        else f"merge: dev → master，发布 v{release_version}（P1 verify 全绿）"
    )
    rc, out, err = _git_ok(["merge", "--no-ff", "dev", "-m", merge_msg], REPO_ROOT, runner)
    if rc != 0:
        print(f"[ERR] 合并失败：{(err or out).strip()}")
        _git_ok(["checkout", "dev"], REPO_ROOT, runner)
        return rc
    print("[OK] dev → master 已合并（--no-ff）")

    rc, out, err = _git_ok(["tag", f"v{release_version}"], REPO_ROOT, runner)
    if rc != 0:
        print(f"[ERR] 打 tag 失败：{(err or out).strip()}")
        _git_ok(["checkout", "dev"], REPO_ROOT, runner)
        return rc
    print(f"[OK] tag v{release_version} 已打在 master 合并提交")

    _git_ok(["checkout", "dev"], REPO_ROOT, runner)
    if args.push:
        for push_args in (["push", "origin", "dev"], ["push", "origin", "master"], ["push", "origin", "--tags"]):
            rc, out, err = _git_ok(push_args, REPO_ROOT, runner, capture=True)
            if rc != 0:
                print(f"[ERR] git {' '.join(push_args)} 失败：{(err or out).strip()}")
                return rc
        print("[OK] dev / master / tags 已推送")
    else:
        print("[..] 未推送（默认）。确认后执行：")
        print("      git push origin dev && git push origin master && git push origin --tags")
    print("[OK] publish 完成 —— 最后执行 devbump 切开发版")
    return 0


def cmd_devbump(args: argparse.Namespace, runner=None) -> int:
    branch = _current_branch(REPO_ROOT, runner)
    if branch != "dev":
        print(f"[ERR] 当前分支 {branch or '<获取失败>'}，devbump 仅在 dev 上执行")
        return 2
    constants_text = CONSTANTS_FILE.read_text(encoding="utf-8")
    current = read_app_version(constants_text)
    if not _RELEASE_VERSION_RE.match(current):
        print(f"[ERR] 当前版本 {current} 不是发布形态 X.Y.Z（devbump 应在发布提交之后执行）")
        return 2
    release_version = current
    next_dev = next_dev_version_of(release_version)
    CONSTANTS_FILE.write_text(render_app_version(constants_text, next_dev), encoding="utf-8")
    README_FILE.write_text(render_readme_version(README_FILE.read_text(encoding="utf-8"), next_dev), encoding="utf-8")
    rc, out, err = _exec([sys.executable, "scripts/check-version-consistency.py", "--fix"], REPO_ROOT, runner)
    if rc != 0:
        print((out or err).rstrip())
        print("[ERR] 切版后版本一致性未收敛")
        return rc
    print(f"[OK] 版本全链 → {next_dev}")

    _, staged, _ = _git_ok(["status", "--porcelain"], REPO_ROOT, runner)
    if staged.strip():
        _git_ok(["add", "-A"], REPO_ROOT, runner)
        rc, out, err = _git_ok(
            ["commit", "-m", f"chore: 切 {next_dev} 开发版本（v{release_version} 发布后）"],
            REPO_ROOT,
            runner,
        )
        if rc != 0:
            print(f"[ERR] 切版提交失败：{(err or out).strip()}")
            return rc
        print("[OK] 切版提交完成")
    if args.push:
        rc, out, err = _git_ok(["push", "origin", "dev"], REPO_ROOT, runner)
        if rc != 0:
            print(f"[ERR] push 失败：{(err or out).strip()}")
            return rc
        print("[OK] dev 已推送")
    else:
        print("[..] 未推送（默认）。确认后执行：git push origin dev")
    return 0


# ─────────────────────────── CLI ───────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="release.py",
        description="发布流程分步编排（每步独立可审阅、失败即停；详见模块文档字符串与 developer-guide）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="预检：分支/工作树/版本形态/tag/版本一致性")

    p_prepare = sub.add_parser("prepare", help="版本全链 + changelog 发布段归档 + 一致性 --fix")
    p_prepare.add_argument("--version", help="目标发布版（默认按 APP_VERSION 推导）")
    p_prepare.add_argument("--date", help="发布日期 YYYY-MM-DD（默认今天）")

    sub.add_parser("refresh", help="数据刷新：bench --update-docs + collect + doc-drift --sync")

    p_evolution = sub.add_parser("evolution", help="版本演进对照快照（默认只滚当前开发版列）")
    p_evolution.add_argument("--release", action="store_true", help="发布期使用：发布列与增长比一并写入")

    sub.add_parser("gate", help="P2 门禁：regression + 十守护 --ci")

    p_publish = sub.add_parser("publish", help="release 提交 + P1 verify + --no-ff 合并 + tag")
    p_publish.add_argument("--title", required=True, help="release 提交主题（changelog 摘要式短描述）")
    p_publish.add_argument("--push", action="store_true", help="完成后推送 dev/master/tags（默认只打印命令）")

    p_devbump = sub.add_parser("devbump", help="切下一开发版并提交")
    p_devbump.add_argument("--push", action="store_true", help="完成后推送 dev（默认只打印命令）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "check": cmd_check,
        "prepare": cmd_prepare,
        "refresh": cmd_refresh,
        "evolution": cmd_evolution,
        "gate": cmd_gate,
        "publish": cmd_publish,
        "devbump": cmd_devbump,
    }
    try:
        return handlers[args.command](args)
    except ReleaseError as exc:
        print(f"[ERR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
