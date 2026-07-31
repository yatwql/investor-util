"""LLM 智能分析包 — 公共 API 入口。

仅暴露非私有（无 `_` 前缀）的公开接口。
子模块内部的辅助函数/常量通过直接 import 子模块引用。

子模块（按职责分层）：
  prompts.py                 — System Prompt 常量与构建函数
  generators.py              — 4 个单例生成函数（global_macro/expert_review/health_check/penetration）
  generators_orchestrator.py — LLM 批量编排、缓存预检、线程池分发
  generators_news.py         — 财经新闻 LLM 关联分析
  api.py                     — Provider 路由 + Extended Thinking
  _api_claude.py             — Claude API 调用实现
  _api_openai.py             — OpenAI API 调用实现
  _api_gemini.py             — Gemini API 调用实现
  api_base.py                — API 基础设施（常量、重试、截断、失败追踪）
  fingerprint.py             — 缓存指纹计算
  pricing.py                 — Token 定价与费用估算
  session.py                 — 会话统计（Token 累计、模块级用量）
  circuit_breaker.py         — 熔断器（连续失败自动暂停）
  strategy.py                — Provider 链策略引擎（priority/weighted/cost_first）
  markdown.py                — Markdown → HTML 转换
"""

from __future__ import annotations

from src.python.llm.generators_news import (  # noqa: F401
    enhance_news_correlation,
)
from src.python.llm.generators_orchestrator import (  # noqa: F401
    generate_all_llm,
    get_news_correlation_result,
    run_news_correlation_safe,
)
from src.python.llm.prompts import (  # noqa: F401
    FAIL_REASON_API_ERROR,
    FAIL_REASON_CIRCUIT_OPEN,
    FAIL_REASON_DISABLED,
    FAIL_REASON_NETWORK_ERROR,
    FAIL_REASON_NOT_CONFIGURED,
    FAIL_REASON_TIMEOUT,
)
from src.python.llm.session import (  # noqa: F401
    format_session_usage,
    get_session_usage,
)
from src.python.llm.strategy import (  # noqa: F401
    resolve_provider_chain,
)
