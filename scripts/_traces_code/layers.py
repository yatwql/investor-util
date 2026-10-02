"""core 层反向依赖守卫（check-code-traces 的 AST 级 HIGH 扫描支路）。"""

from __future__ import annotations

import ast
from pathlib import Path

#: core 禁止反向 import 的上层包（order: 上游层任意演化会静默改 core 诊断口径）
_UPPER_PACKAGES = frozenset({"fetcher", "analysis", "report", "llm", "providers", "web", "tui", "cli"})
#: 声明豁免（technical.md「架构设计约束」例外登记）：探针网关薄透传（惰性 import fetcher）
_CORE_LAYERING_EXEMPT_FILES = frozenset({"check_sources.py"})


def _scan_core_layering(fpath: Path) -> list[tuple[int, str, str, str]]:
    """扫描 core 层 .py 的反向 import（``src.python.<上层包>``）。

    以 AST Import/ImportFrom 节点判定（含函数内延迟 import），命中即 HIGH
    「core 反向 import 上层」。豁免文件集中在 `_CORE_LAYERING_EXEMPT_FILES`
    （每项须在 technical.md 声明；新增豁免属预审行为，不允许就地扩散）。
    """
    if fpath.suffix.lower() != ".py" or fpath.name in _CORE_LAYERING_EXEMPT_FILES:
        return []
    # 仅约束生产层（src/python/core/**）——测试对上层的 import 属被测对象，不在纪律内
    parts = fpath.parts
    if not any(tuple(parts[i : i + 3]) == ("src", "python", "core") for i in range(len(parts) - 3)):
        return []
    hits: list[tuple[int, str, str, str]] = []
    try:
        tree = ast.parse(fpath.read_text(encoding="utf-8-sig"), filename=str(fpath))
    except (SyntaxError, UnicodeDecodeError, OSError, ValueError):
        return hits
    for node in ast.walk(tree):
        module = getattr(node, "module", "") or ""
        names = [a.name for a in getattr(node, "names", [])] if isinstance(node, ast.Import) else []
        candidates = [module] if module else names
        for cand in candidates:
            seg = cand.split(".")
            if len(seg) >= 3 and seg[0] == "src" and seg[1] == "python" and seg[2] in _UPPER_PACKAGES:
                hits.append(
                    (
                        node.lineno,
                        "HIGH",
                        "core 反向 import 上层（分层倒置，改注册钩子/网关）",
                        cand,
                    )
                )
                break
    return hits
