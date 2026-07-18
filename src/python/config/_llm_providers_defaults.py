"""LLM Provider 多链默认配置模板 — llm_providers.json 缺省模板生成。

职责：
  提供 _get_default_llm_providers_template() 函数，返回带注释的
  llm_providers.json 模板字符串。首次初始化时由 _core.py 的
  _ensure_llm_providers_file() 调用写入磁盘。
"""


def _get_default_llm_providers_template() -> str:
    """返回带注释的默认 llm_providers.json 模板字符串。

    主：DeepSeek（通过 claude 兼容端点）/ 辅：Gemini
    使用者需自行在 llm_key.json 中配置对应凭据块。
    """
    return (
        "{\n"
        "  // LLM Provider 多链配置\n"
        "  // 按优先级尝试多个 provider，直到第一个成功返回\n"
        "  // 有效 provider 类型：claude, openai, gemini\n"
        "  //\n"
        "  // 使用前请先在 llm_key.json 中配置对应的 credentials_ref 凭据块，\n"
        "  // 并按需修改 model / endpoint 为实际使用的模型与 API 端点。\n"
        "\n"
        '  "strategy": "priority",\n'
        '  "preferred_providers": {},\n'
        '  "providers": [\n'
        "    {\n"
        '      "name": "deepseek-main",\n'
        '      "provider": "claude",\n'
        '      "credentials_ref": "deepseek-main",\n'
        '      "priority": 10,\n'
        '      "timeout": 120\n'
        "    },\n"
        "    {\n"
        '      "name": "gemini-fallback",\n'
        '      "provider": "gemini",\n'
        '      "credentials_ref": "gemini-fb",\n'
        '      "priority": 20,\n'
        '      "timeout": 60\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
