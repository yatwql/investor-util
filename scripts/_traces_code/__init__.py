"""check-code-traces 实现包（check-code-traces.py 薄 CLI 的持有者）。

模块划分：
  - config     扫描域配置（REPO_ROOT/SCAN_DIRS/SKIP_FILES/_is_tool_self）
  - patterns   模式表（PATTERNS/IDENTIFIER_PATTERNS/EXCLUDE_LINE）+ 行级豁免
  - exemptions 章节/轮次计数豁免（与 check-doc-traces 共用，原 _traces_common）
  - extract    注释抽取（per-language）与标识符提取
  - scan       scan_file 调度（三支路汇聚）
  - layers     core 反向依赖 AST 守卫
"""

from __future__ import annotations

from _traces_code.config import (  # noqa: F401
    REPO_ROOT,
    SCAN_DIRS,
    SKIP_FILES,
    _is_tool_self,
)
from _traces_code.exemptions import (  # noqa: F401
    _COMPILED_CHAPTER_EXCLUDE,
    _COMPILED_ROUND_EXCLUDE,
    _chapter_excludes,
    _is_chapter_excluded,
    _is_round_excluded,
    _round_excludes,
)
from _traces_code.extract import (  # noqa: F401
    _html_comment_lines,
    _iter_comment_lines,
    _iter_identifiers,
    _js_comment_lines,
    _js_identifier_names,
    _py_comment_lines,
    _py_identifier_names,
    _shell_comment_lines,
)
from _traces_code.layers import (  # noqa: F401
    _CORE_LAYERING_EXEMPT_FILES,
    _UPPER_PACKAGES,
    _scan_core_layering,
)
from _traces_code.patterns import (  # noqa: F401
    _COMPILED_DASH_EXCLUDE,
    _COMPILED_EXCLUDE,
    _COMPILED_IDENTIFIER_PATTERNS,
    _COMPILED_MAGIC_EXCLUDE,
    _COMPILED_PATTERNS,
    _COMPILED_UNDER_EXCLUDE,
    _PATTERNS_PREFILTER,
    _TASK_ID_RE,
    _TEST_META_COMPILED,
    _dash_excludes,
    _is_dash_excluded,
    _is_excluded,
    _is_magic_match_excluded,
    _is_under_excluded,
    _magic_excludes,
    _under_excludes,
    EXCLUDE_LINE,
    IDENTIFIER_PATTERNS,
    PATTERNS,
    TEST_META_EXCLUDE,
)
from _traces_code.scan import (  # noqa: F401
    _scan_identifiers,
    scan_file,
)
