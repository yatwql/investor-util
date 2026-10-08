#!/usr/bin/env python3
"""设计护栏机检（DESIGN.md「Do's and Don'ts — 护栏」样式面的机器化检查）。

规则与 DESIGN.md 护栏条目**逐条同源**（各函数 docstring 标注映射编号）：

  E1 强调色越权（护栏 3）   品牌蓝系 **hex 字面量**（小写归一）出现在非 token 定义行 / 非 JS 字符串
                             → finding；rgb/rgba 透明变体不入 E1（柔和底色实践归 W1 观察）
  E2 明暗同步（护栏 5）      ``[data-theme="dark"]`` 覆盖的变量在 ``:root`` 缺定义 → finding
  E3 双面 token 对表（Colors「同名对齐」段）
                             正向：DESIGN Colors 表两面同列具名 token，双面 ``:root`` 均须定义
                             反向：实现中「值为颜色」的两面同名变量，须在 Colors 表登记
  W1 裸色值存量（护栏 1）    非定义行出现 hex/rgb 字面量（**观察项**，统计不判 finding）
  W2 圆角档位（护栏 2）      ``border-radius`` 档外字面值（**观察项**，统计不判 finding）

**观察期口径**（样式护栏先例，2026-10-08 立）：W 级仅统计与 ``-v`` 明细供分诊，
**不判 finding**、不入 pre-commit 钩子域与 CI guards；待误报率稳定后再评估入域。
检查域：两份报告模板 + partials + Web 工作台样式表。

用法：
  python scripts/check-style-guardrails.py           # 检查全部
  python scripts/check-style-guardrails.py -v        # 详细输出（含 W 级观察清单）
  python scripts/check-style-guardrails.py --ci      # CI 模式（只输出 文件:描述）

退出码：
  0 — 全部通过（无 E 级 finding；W 级观察项不判 finding）
  2 — 发现 E 级 finding（强调色越权 / 明暗同步缺失 / 双面 token 对表不一致）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import REPO_ROOT, add_common_args, rel, report  # noqa: E402

#: 样式检查域（仓库相对路径）
STYLE_DOMAIN = (
    "src/static/tmpl/report_template.html",
    "src/static/tmpl/whatif_template.html",
    "src/static/tmpl/partials",
    "src/static/web/style.css",
)

#: 圆角档位（DESIGN.md Layout「圆角档」+ 药丸/全圆钮 999px；字面 px 值白名单）
RADIUS_TIERS = frozenset({4, 6, 8, 999})

#: DESIGN.md 文件（Colors / Layout 真值来源）
DESIGN_DOC = "DESIGN.md"

_COMMENT_PREFIXES = ("/*", "*", "//", "<!--", "#")
_TOKEN_DEF = re.compile(r"--[\w-]+\s*:")  # 行内任意位置的变量定义形态（含单行 :root {...}）
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_JS_STRING_HEX = re.compile(r"""['"]#[0-9a-fA-F]{3,8}['"]""")
_RGB = re.compile(r"\b(?:rgba?|hsla?)\(")
_RADIUS_PX = re.compile(r"border-radius:\s*(\d+(?:\.\d+)?px)")


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(_COMMENT_PREFIXES)


def _root_block(css: str) -> str:
    m = re.search(r":root\s*\{([^}]*)\}", css, re.S)
    return m.group(1) if m else ""


def _root_vars(css: str) -> dict[str, str]:
    """``:root`` 变量名 → 原始值。"""
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", _root_block(css)))


def _dark_vars(css: str) -> set[str]:
    out: set[str] = set()
    for blk in re.findall(r"""\[data-theme=['"]dark['"]\]\s*\{([^}]*)\}""", css, re.S):
        out |= set(re.findall(r"(--[\w-]+)\s*:", blk))
    return out


def _design_table_shared(design_text: str) -> set[str]:
    """DESIGN.md Colors 表中「报告侧」与「工作台侧」两列**同现**的具名 token。

    支持组合书写：``--primary``(-hover) 展开为附加名；反引号单 token 直取；
    通配（``--warn-*``）与破折号占位不参与对表。
    """
    try:
        sec = design_text.split("## Colors — 语义角色表")[1].split("## Typography")[0]
    except IndexError:
        return set()

    def toks(cell: str) -> set[str]:
        out = set(re.findall(r"`(--[\w-]+)`", cell))
        out |= {base + suf for base, suf in re.findall(r"`(--[\w-]+)`\((-\w+)\)", cell)}
        return out

    rep, web = set(), set()
    for line in sec.splitlines():
        if line.startswith("|") and "---" not in line and "角色族" not in line:
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 4:
                rep |= toks(cols[2])
                web |= toks(cols[3])
    return rep & web


def _table_all_tokens(design_text: str) -> set[str]:
    """Colors 表两列出现过的全部具名 token（正反向对表的登记集）。"""
    try:
        sec = design_text.split("## Colors — 语义角色表")[1].split("## Typography")[0]
    except IndexError:
        return set()
    out: set[str] = set()
    for line in sec.splitlines():
        if line.startswith("|") and "---" not in line and "角色族" not in line:
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 4:
                out |= set(re.findall(r"`(--[\w-]+)`", cols[2] + " " + cols[3]))
                out |= {a + b for a, b in re.findall(r"`(--[\w-]+)`\((-\w+)\)", cols[2] + " " + cols[3])}
    return out


def _brand_hexes(paths: list[Path]) -> set[str]:
    """品牌蓝系 hex 集合——从检查域各 ``:root`` 的强调系 token 动态提取（真值=实现定义）。"""
    brand: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        css = path.read_text(encoding="utf-8")
        for name, val in _root_vars(css).items():
            if name in ("--primary", "--primary-hover", "--focus", "--accent"):
                brand |= {h.lower() for h in _HEX.findall(val)}
    return brand


def check_emphasis_color(path: Path, brand: set[str]) -> list[str]:
    """E1 强调色越权（护栏 3）：品牌蓝字面量只许出现在 token 定义行与 JS fallback 串。"""
    findings: list[str] = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if _is_comment(line) or _TOKEN_DEF.search(line):
            continue
        if _JS_STRING_HEX.search(line):
            continue
        for hit in {h.lower() for h in _HEX.findall(line)} & brand:
            findings.append(f"{rel(path)}:{i}: 强调色越权：品牌蓝 {hit} 应改用 var(--primary) 系 token")
    return findings


def check_dark_sync(path: Path) -> list[str]:
    """E2 明暗同步（护栏 5）：dark 覆盖变量必须在 ``:root`` 有定义（亮色为源）。"""
    text = path.read_text(encoding="utf-8")
    root = set(_root_vars(text))
    return [
        f"{rel(path)}: dark 覆盖变量 {name} 在 :root 缺定义（明暗不同步）" for name in sorted(_dark_vars(text) - root)
    ]


def check_token_alignment(report_css: str, web_css: str, design_text: str) -> list[str]:
    """E3 双面 token 对表（Colors「同名对齐」段）：表 ↔ 实现双向。"""
    findings: list[str] = []
    rep, web = _root_vars(report_css), _root_vars(web_css)
    shared_in_table = _design_table_shared(design_text)
    for name in sorted(shared_in_table):
        if name not in rep or name not in web:
            findings.append(
                f"{DESIGN_DOC}: Colors 表共名 token {name} 双面定义缺失"
                f"（报告 {'有' if name in rep else '无'} / 工作台 {'有' if name in web else '无'}）"
            )
    registered = _table_all_tokens(design_text)
    shared_colors = {
        n
        for n in set(rep) & set(web)
        if n in rep and ("#" in rep[n] or "rgb" in rep[n]) and ("#" in web[n] or "rgb" in web[n])
    }
    for name in sorted(shared_colors - registered):
        findings.append(f"{DESIGN_DOC}: 两面同名颜色变量 {name} 未在 Colors 表登记（实现先于契约）")
    return findings


def observe_raw_colors(path: Path) -> list[str]:
    """W1 裸色值存量（护栏 1，观察）：非注释/非定义/非 JS 串行的 hex 或 rgb 字面。"""
    details: list[str] = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        if _is_comment(line) or _TOKEN_DEF.search(line):
            continue
        stripped = _JS_STRING_HEX.sub("", line)
        if _HEX.search(stripped) or _RGB.search(stripped):
            details.append(f"{rel(path)}:{i}: {line.strip()[:96]}")
    return details


def observe_radius(path: Path) -> list[str]:
    """W2 圆角档位（护栏 2，观察）：字面 px 圆角不在档位集内。"""
    details: list[str] = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        for raw in _RADIUS_PX.findall(line):
            if int(float(raw[:-2])) not in RADIUS_TIERS:
                details.append(f"{rel(path)}:{i}: border-radius {raw} 档外（档位 {sorted(RADIUS_TIERS)}）")
    return details


def _collect_files(paths: tuple[str, ...] | None) -> list[Path]:
    files: list[Path] = []
    for rel_path in paths or STYLE_DOMAIN:
        base = REPO_ROOT / rel_path
        if base.is_dir():
            files.extend(sorted(base.glob("*.html")))
        elif base.is_file():
            files.append(base)
    return files


def run_checks(
    paths: tuple[str, ...] | None = None,
    design_text: str | None = None,
    files: list[Path] | None = None,
) -> tuple[list[str], dict[str, list[str]]]:
    """执行全部规则。

    Args:
        paths: 检查域相对路径（缺省 ``STYLE_DOMAIN``）。
        design_text: DESIGN.md 正文（缺省读仓库真值）。
        files: 显式文件列表（测试注入合成文件，优先于 ``paths``）。

    Returns:
        ``(findings, observations)`` —— findings 为 E 级（退出 2）；
        observations 为 W 级明细列表（统计用，不判 finding）。
    """
    targets = files if files is not None else _collect_files(paths)
    if design_text is None:
        design_path = REPO_ROOT / DESIGN_DOC
        design_text = design_path.read_text(encoding="utf-8") if design_path.is_file() else ""

    brand = _brand_hexes(targets)
    findings: list[str] = []
    observations: dict[str, list[str]] = {"raw_colors": [], "radius": []}

    report_css = ""
    web_css = ""
    for path in targets:
        text = path.read_text(encoding="utf-8")
        if path.name == "report_template.html":
            report_css = text
        if path.name == "style.css":
            web_css = text
        findings += check_emphasis_color(path, brand)
        if ":root" in text or "[data-theme" in text:
            findings += check_dark_sync(path)
        observations["raw_colors"] += observe_raw_colors(path)
        observations["radius"] += observe_radius(path)

    if design_text and report_css and web_css:
        findings += check_token_alignment(report_css, web_css, design_text)
    return findings, observations


def main() -> int:
    parser = argparse.ArgumentParser(description="设计护栏机检（DESIGN.md 护栏样式面）")
    add_common_args(parser)
    args = parser.parse_args()

    findings, observations = run_checks()
    w1, w2 = len(observations["raw_colors"]), len(observations["radius"])

    if args.verbose:
        for line in observations["raw_colors"]:
            print(f"  [观察] {line}")
        for line in observations["radius"]:
            print(f"  [观察] {line}")
    if not args.ci and (w1 or w2):
        hint = "（-v 看明细）" if not args.verbose else ""
        print(f"[!] 观察项（不判 finding，观察期）：裸色值 {w1} 处、圆角档外 {w2} 处{hint}")

    return report(
        findings,
        f"[OK] 设计护栏 E 级通过（观察期统计：裸色值 {w1}、圆角档外 {w2}）",
        ci=args.ci,
    )


if __name__ == "__main__":
    sys.exit(main())
