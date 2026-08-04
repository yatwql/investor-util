"""LLM Provider 多链默认配置模板 — llm_providers.json 缺省模板生成。

职责：
  提供 _DEFAULT_LLM_PROVIDERS 缺省值 dict 与 _get_default_llm_providers_template()
  模板函数（手工拼注释）。首次初始化时由 _core.py 的
  _ensure_llm_providers_file() 调用写入磁盘。

与 _llm_settings_defaults.py 同构：dict 存值 + 模板函数逐行拼注释，
保证缺省值与模板内容一致，新增/修改 provider 条目只动 dict。
"""

from __future__ import annotations

import json
from typing import Any

# LLM Provider 多链缺省配置（与模板一一对应，确保一致性）
_DEFAULT_LLM_PROVIDERS: dict[str, Any] = {
    "strategy": "priority",
    "preferred_providers": {},
    "providers": [
        {
            "name": "deepseek-main",
            "provider": "claude",
            "credentials_ref": "deepseek-main",
            "priority": 10,
            "timeout": 120,
        },
        {
            "name": "gemini-fallback",
            "provider": "gemini",
            "credentials_ref": "gemini-fb",
            "priority": 20,
            "timeout": 60,
        },
    ],
}


def _get_default_llm_providers_template() -> str:
    """返回带注释的默认 llm_providers.json 模板字符串。

    主：DeepSeek（通过 claude 兼容端点）/ 辅：Gemini
    使用者需自行在 llm_key.json 中配置对应凭据块。
    """
    d = _DEFAULT_LLM_PROVIDERS
    lines = ["{"]

    def _kv(key: str, indent: int = 2) -> str:
        val = d[key]
        if isinstance(val, dict):
            dumped = json.dumps(val, indent=2, ensure_ascii=False)
            prefix = " " * indent
            return prefix + dumped.replace("\n", "\n" + prefix)
        return " " * indent + json.dumps(val, ensure_ascii=False)

    # ── 头部注释 ──
    lines.append("  // LLM Provider 多链配置")
    lines.append("  // 按优先级尝试多个 provider，直到第一个成功返回")
    lines.append("  // 有效 provider 类型：claude, openai, gemini")
    lines.append("  //")
    lines.append("  // 使用前请先在 llm_key.json 中配置对应的 credentials_ref 凭据块，")
    lines.append("  // 并按需修改 model / endpoint 为实际使用的模型与 API 端点。")
    lines.append("")

    # ── strategy / preferred_providers ──
    lines.append(f'  "strategy": {json.dumps(d["strategy"])},')
    lines.append(f'  "preferred_providers": {json.dumps(d["preferred_providers"])},')
    lines.append(f'  "providers": [')

    # ── providers 列表 ──
    for idx, entry in enumerate(d["providers"]):
        lines.append("    {")
        items = list(entry.items())
        for i, (key, val) in enumerate(items):
            comma = "," if i < len(items) - 1 else ""
            lines.append(f'      "{key}": {json.dumps(val, ensure_ascii=False)}{comma}')
        closing = "    }," if idx < len(d["providers"]) - 1 else "    }"
        lines.append(closing)

    lines.append("  ]")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)
