"""`check-doc-drift` 共享设施 —— 文档路径常量、扫描面与通用解析原语。

被检文档清单、生成物排除规则、表格与区间解析、项目统计口径的公共辅助。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from _checklib import REPO_ROOT, rel


_README = REPO_ROOT / "README.md"


_MANUALS = REPO_ROOT / "docs-stm" / "manuals"


_MANAGEMENTS = REPO_ROOT / "docs-stm" / "managements"


_FOLDERS_MD = _MANAGEMENTS / "folders.md"


_HOW_TO_CONFIG_MD = _MANUALS / "how-to-config.md"


_REPORTS_MD = _MANUALS / "reports-instruction.md"


_TUI_MENU_MD = _MANUALS / "how-to-use-tui-menu.md"


_LLM_TECHNICAL_MD = _MANAGEMENTS / "llm-technical.md"
_RELIABILITY_MD = _MANUALS / "datasource-reliability.md"


_TEST_COVERAGE_MD = _MANAGEMENTS / "test-coverage.md"


_PLAN_MD = _MANAGEMENTS / "plan.md"


_CHANGELOG_MD = _MANAGEMENTS / "changelog.md"


_REVIEW_FINDINGS_MD = _MANAGEMENTS / "review-findings.md"


_HISTORY_DOCS = {_MANAGEMENTS / "changelog.md", _MANAGEMENTS / "review-findings.md"}


_TREE_ROOTS = ("src", "scripts", "docs-stm/managements", "docs-stm/manuals", "docs-stm/plan")


_GENERATED_DIRS = {
    "__pycache__",
    ".eggs",
    "build",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov",
}


_GENERATED_SUFFIXES = (".egg-info", ".dist-info")


_GENERATED_FILES = {".coverage"}


_GENERATED_PREFIXES = ("docs-stm/tmp/",)


def _is_generated(rel: str) -> bool:
    """相对路径是否属构建/缓存产物（`pip install -e` 的 egg-info、构建目录、缓存等）。

    这些由工具链生成、不该出现在目录树里也不该计入统计——CI 上 `pip install -e ".[test]"`
    会在 `src/` 下留下 `*.egg-info/`，若不排除会被误报为「目录树缺条目」。

    **例外**：`test-reports/` 的规范位置是仓库根（不在受检根内），故**不**豁免——受检目录
    （`src/`、`scripts/`、`docs-stm/{managements,manuals,plan}`）下出现 `test-reports/`
    属误落（如入口把项目根算到了 `scripts/`），须由目录树检查报出。
    """
    if rel in _GENERATED_FILES or rel.startswith(_GENERATED_PREFIXES):
        return True
    return any(p in _GENERATED_DIRS or p.endswith(_GENERATED_SUFFIXES) for p in Path(rel).parts)


def _scan_docs() -> dict[Path, str]:
    """返回参与断言扫描的文档集合（README + 手册 + 管理文档，排除历史记录类）。"""
    docs: list[Path] = [_README]
    docs += sorted(_MANUALS.glob("*.md"))
    docs += sorted(_MANAGEMENTS.glob("*.md"))
    return {p: p.read_text(encoding="utf-8") for p in docs if p not in _HISTORY_DOCS}


def _doc_section(text: str, start: str, end: str | None) -> str:
    """取 ``start`` 起、到 ``end``（不含）的区段；起点缺失返回空串。"""
    idx = text.find(start)
    if idx < 0:
        return ""
    if end is None:
        return text[idx:]
    stop = text.find(end, idx + len(start))
    return text[idx:] if stop < 0 else text[idx:stop]


def _split_table_row(line: str) -> list[str] | None:
    """拆分 markdown 表格行 → 去除粗体标记的单元格列表（非表格行返回 None）。"""
    if not line.startswith("|"):
        return None
    cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
    return cells if len(cells) >= 4 else None


def _first_number(cell: str) -> str | None:
    """取单元格中的首个数字（去千分位），无数字时返回 None（`-` / 空占位）。"""
    m = re.search(r"[\d][\d,]*", cell)
    return m.group(0).replace(",", "") if m else None


def _count(files: list[Path]) -> tuple[int, int]:
    kept = [p for p in files if not _is_generated(rel(p))]
    return len(kept), sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in kept)


def _values_equal(doc_value: str, code_value: object) -> bool:
    """文档字符串 ↔ 代码默认值的等价判定（bool/None/数字/路径/字符串）。"""
    shown = doc_value.strip()
    if isinstance(code_value, bool):
        return shown.lower() in (("true", "开") if code_value else ("false", "关"))
    if code_value is None:
        return shown.lower() in ("null", "none", "无")
    if isinstance(code_value, (int, float)):
        try:
            return float(shown.replace(",", "")) == float(code_value)
        except ValueError:
            return False
    text = str(code_value)
    if shown == text or shown.strip("\"'") == text.strip("\"'"):
        return True
    # 路径类默认值在代码内可能已被解析为绝对路径，文档写相对形式
    return bool(shown) and (text.endswith(shown) or Path(text).name == Path(shown).name)


def _collect_test_count() -> int | None:
    """已收集用例数（与 folders.md 说明同源），见 `_collect_test_snapshot`。"""
    snapshot = _collect_test_snapshot()
    return snapshot.get("_总收集")


def _collect_test_snapshot() -> dict[str, int]:
    """`scripts/collect-test-coverage.py` 快照 → ``{标记/名称: 数量}``（含 ``_总收集``）。

    与 `test-coverage.md` / `folders.md` 同一来源（慢：内部跑 pytest 收集，仅 `--with-test-count` 时调用）。
    """
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "collect-test-coverage.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    snapshot: dict[str, int] = {}
    total = re.search(r"总收集:\s*(\d+)\s*项", proc.stdout)
    if total:
        snapshot["_总收集"] = int(total.group(1))
    for line in proc.stdout.splitlines():
        m = re.match(r"^([\w\u4e00-\u9fff][^:]*?):\s*(\d+)$", line.strip())
        if m:
            snapshot[m.group(1).strip()] = int(m.group(2))
    return snapshot
