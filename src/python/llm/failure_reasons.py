"""LLM 模块失败原因常量（语义名 failure_reasons）— 门面 prompts_core / prompts 共享再导出。"""

from __future__ import annotations

# ── 模块级失败原因记录（供 write_llm_sheets 读取以输出具体提示） ──

FAIL_REASON_NOT_CONFIGURED = "not_configured"
FAIL_REASON_API_ERROR = "api_error"
FAIL_REASON_NETWORK_ERROR = "network_error"
FAIL_REASON_TIMEOUT = "timeout"
FAIL_REASON_CIRCUIT_OPEN = "circuit_open"
# 端点配额/风控类拒绝（如订阅制端点的 5 小时窗口、并发上限）——重试无益且会加剧风控画像
FAIL_REASON_QUOTA_EXCEEDED = "quota_exceeded"
FAIL_REASON_DISABLED = "disabled"

LLM_MODULE_FAILURE: dict[str, str | dict] = {}
"""{module_key: reason|dict} 各 LLM 模块最近一次生成的失败原因。"""
