"""LLM 事实锚定校验器 — 纯算法层。

对 LLM 生成的报告内容做确定性事实校验，无需额外 LLM API 调用。

对外提供三个检查器与统一入口：
  - check_numerical_consistency — 数值一致性校验
  - check_symbol_existence      — 品种存在性校验
  - check_ranking_correctness   — 排名正确性校验
  - run_fact_check              — 统一入口（全量校验 + 自动修正）

用法:
    >>> from src.python.llm.fact_checker import run_fact_check
    >>> summary_html = run_fact_check(html_content, holdings_details, "全球政经局势")
    >>> html_content += summary_html

内部实现按职责拆分（均为私有模块，不对外暴露）：
  _constants.py  — 关键词词表 / 指数代码集 / 默认容差
  _patterns.py   — 正则模式
  _utils.py      — HTML 剥离、句子拆分、持仓映射、组合数值计算
  _context.py    — 语境检测（回撤/变化率/贡献度/仓位/假设/建议）
  _numerical.py  — 检查器 1：数值一致性（带语境感知）
  _symbols.py    — 检查器 2：品种存在性
  _ranking.py    — 检查器 3：排名正确性
  _corrections.py — 数值自动修正
  _runner.py     — run_fact_check 统一入口
"""

from __future__ import annotations

from src.python.llm.fact_checker._numerical import (  # noqa: F401
    check_numerical_consistency,
)
from src.python.llm.fact_checker._ranking import (  # noqa: F401
    check_ranking_correctness,
)
from src.python.llm.fact_checker._runner import (  # noqa: F401
    run_fact_check,
)
from src.python.llm.fact_checker._symbols import (  # noqa: F401
    check_symbol_existence,
)

__all__ = [
    "run_fact_check",
    "check_numerical_consistency",
    "check_symbol_existence",
    "check_ranking_correctness",
]
