"""LLM 智能分析包 — 公共 API 入口。

仅暴露非私有（无 `_` 前缀）的公开接口。
子模块内部的辅助函数/常量通过直接 import 子模块引用。

子模块（按职责分层）：
  prompts.py          — System Prompt 常量与构建函数
  generators.py       — LLM 调用编排与批量生成
  api.py              — Claude / OpenAI 双通道底层调用
  fingerprint.py      — 缓存指纹计算
  pricing.py          — Token 定价与费用估算
  session.py          — 会话统计（Token 累计、模块级用量）
  circuit_breaker.py  — 熔断器（连续失败自动暂停）
  markdown.py         — Markdown → HTML 转换
"""

from __future__ import annotations

from src.python.llm.prompts import (  # noqa: F401
    FAIL_REASON_NOT_CONFIGURED, FAIL_REASON_API_ERROR, FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_TIMEOUT, FAIL_REASON_CIRCUIT_OPEN, FAIL_REASON_DISABLED,
)
from src.python.llm.generators import (  # noqa: F401
    generate_global_macro, generate_expert_review, generate_health_check,
    generate_penetration_deep_analysis, enhance_news_correlation, generate_all_llm,
)
from src.python.llm.session import (  # noqa: F401
    reset_session_usage, get_session_usage, format_session_usage,
)
