"""`check-doc-drift` 守护清单族 —— P0/P2 门禁清单与 CI guards / CLAUDE.md / testplan.md 的同源校验。

「守护脚本清单」被四处引用且各处都声称同源/全量：

- `developer-guide.md` 的 **P0 提交前门禁** / **P2 发布门禁** 代码块
- `.github/workflows/ci.yml` 的 `guards` job steps
- `CLAUDE.md` 的「提交前门禁（P0）」/「发布门禁（P2）」条款
- `testplan.md` 的「P0 全通」/「P2 已执行」清单行

新增/移除守护脚本时任何一处漏改都会静默失真（该清单此前无校验）。
本模块从四处各自截取清单区域，统一提取 ``scripts/check-*.py --ci`` 脚本名，
断言七个区域（4 份文档 × P0/P2 视角）提取到的脚本集合两两一致。
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 门禁命令行中的守护脚本引用形如 ``scripts/check-xxx.py --ci``
_SCRIPT_CI = re.compile(r"scripts/(check-[\w-]+\.py) --ci")

_GUIDE_MD = _REPO_ROOT / "docs-stm" / "managements" / "developer-guide.md"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_TESTPLAN_MD = _REPO_ROOT / "docs-stm" / "managements" / "testplan.md"
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _region(text: str, start: str, end: str | None) -> str | None:
    """截取清单区域：`start` 命中行起、到 `end` 命中行为止；`end=None` 表示单行源（返回起始行本身）。

    `end` 自起始行**之后**开始搜索，避免 ci.yml 的 ``^  guards:`` 起始行被通用行模式自匹配。
    任一锚点未命中返回 ``None``（由调用方转为「区域未匹配」finding，防静默失效）。
    """
    m = re.search(start, text, re.M)
    if not m:
        return None
    if end is None:
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.start())
        return text[line_start : line_end if line_end != -1 else len(text)]
    tail = text[m.end() :]
    m2 = re.search(end, tail, re.M)
    if not m2:
        return None
    return text[m.start() : m.end() + m2.start()]


def find_guard_parity(sources: dict[str, str | None]) -> list[str]:
    """断言各来源截取区域提取的守护脚本集合一致。

    ``sources``：来源标签 → 清单区域文本（``None`` = 区域截取失败）。
    以第一个成功提取的来源为基准逐一比对；任一来源缺失/多出脚本均报 finding。
    """
    findings: list[str] = []
    sets: dict[str, set[str]] = {}
    for name, region in sources.items():
        if region is None:
            findings.append(f"{name}: 未匹配到守护清单区域（标题/结构可能已变更，请同步本检查的锚点）")
            continue
        found = set(_SCRIPT_CI.findall(region))
        if not found:
            findings.append(f"{name}: 清单区域内未提取到任何 `scripts/check-*.py --ci` 引用")
            continue
        sets[name] = found
    if len(sets) < 2:
        return findings
    base_name = next(iter(sets))
    base = sets[base_name]
    for name, found in sets.items():
        if name == base_name:
            continue
        missing = base - found
        extra = found - base
        if missing:
            findings.append(f"{name}: 守护清单缺少 {', '.join(sorted(missing))}（与 {base_name} 不同源）")
        if extra:
            findings.append(f"{name}: 守护清单多出 {', '.join(sorted(extra))}（与 {base_name} 不同源）")
    return findings


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def check_guard_parity() -> list[str]:
    """读取四份权威源文件，执行守护清单同源校验。"""
    try:
        texts = {
            _GUIDE_MD: _GUIDE_MD.read_text(encoding="utf-8"),
            _CLAUDE_MD: _CLAUDE_MD.read_text(encoding="utf-8"),
            _TESTPLAN_MD: _TESTPLAN_MD.read_text(encoding="utf-8"),
            _CI_YML: _CI_YML.read_text(encoding="utf-8"),
        }
    except OSError as exc:  # 源文件缺失不应让检查崩溃
        return [f"守护清单校验无法读取源文件: {exc}"]
    guide, claude, testplan, ci = (texts[p] for p in (_GUIDE_MD, _CLAUDE_MD, _TESTPLAN_MD, _CI_YML))
    sources = {
        f"{_rel(_GUIDE_MD)} P0 门禁块": _region(guide, r"^\*\*P0 提交前门禁\*\*", r"^\*\*P1 合入门禁\*\*"),
        f"{_rel(_GUIDE_MD)} P2 门禁块": _region(guide, r"^\*\*P2 发布门禁\*\*", r"^\*\*辅助（非阻塞）\*\*"),
        f"{_rel(_CI_YML)} guards job": _region(ci, r"^  guards:", r"^  [a-z][a-z_]*:$"),
        f"{_rel(_CLAUDE_MD)} P0 条款": _region(
            claude, r"^ *- \*\*提交前门禁（P0）\*\*", r"^ *- \*\*合入门禁（P1）\*\*"
        ),
        f"{_rel(_CLAUDE_MD)} P2 条款": _region(claude, r"^ *- \*\*发布门禁（P2）\*\*", r"^- \*\*CI\*\*"),
        f"{_rel(_TESTPLAN_MD)} P0 行": _region(testplan, r"^9\. \*\*P0 全通\*\*", None),
        f"{_rel(_TESTPLAN_MD)} P2 行": _region(testplan, r"^11\. \*\*P2 已执行\*\*", None),
    }
    return find_guard_parity(sources)
