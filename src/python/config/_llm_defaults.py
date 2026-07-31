"""LLM 设置默认模板 — llm_settings.json 缺省模板生成。

职责：
  提供 _get_default_llm_settings_template() 函数，返回带中文分组注释的
  llm_settings.json 模板字符串。首次初始化时由 _core.py 的
  _ensure_llm_settings_file() 调用写入磁盘。
"""

from __future__ import annotations

import json
from typing import Any

# LLM 默认设置（与模板一一对应，确保一致性）
_DEFAULT_LLM_SETTINGS: dict[str, Any] = {
    "max_retries": 2,
    "llm_max_concurrency": 3,
    "enabled_llm": {
        "global_macro": True,
        "expert_review": True,
        "health_check": True,
        "penetration_deep": True,
        "news_correlation": False,
    },
    "system_prompt_global_macro": None,
    "model_global_macro": None,
    "temperature_global_macro": 0.3,
    "max_tokens_global_macro": 2048,
    "timeout_global_macro": 60,
    "cache_enabled_global_macro": True,
    "output_brief_global_macro": False,
    "thinking_enabled_global_macro": False,
    "thinking_budget_global_macro": 4000,
    "reasoning_effort_global_macro": "high",
    "system_prompt_expert_review": None,
    "model_expert_review": None,
    "temperature_expert_review": 0.3,
    "max_tokens_expert_review": 8192,
    "timeout_expert_review": 120,
    "cache_enabled_expert_review": True,
    "output_brief_expert_review": False,
    "thinking_enabled_expert_review": True,
    "thinking_budget_expert_review": 16000,
    "reasoning_effort_expert_review": "medium",
    "system_prompt_health_check": None,
    "model_health_check": None,
    "temperature_health_check": 0.1,
    "max_tokens_health_check": 8192,
    "timeout_health_check": 120,
    "cache_enabled_health_check": True,
    "output_brief_health_check": False,
    "thinking_enabled_health_check": True,
    "thinking_budget_health_check": 12000,
    "reasoning_effort_health_check": "medium",
    "system_prompt_penetration_deep": None,
    "model_penetration_deep": None,
    "temperature_penetration_deep": 0.1,
    "max_tokens_penetration_deep": 8192,
    "timeout_penetration_deep": 90,
    "cache_enabled_penetration_deep": True,
    "output_brief_penetration_deep": False,
    "thinking_enabled_penetration_deep": False,
    "thinking_budget_penetration_deep": 8000,
    "reasoning_effort_penetration_deep": "high",
    "system_prompt_news_correlation": None,
    "model_news_correlation": None,
    "temperature_news_correlation": 0.1,
    "max_tokens_news_correlation": 2000,
    "timeout_news_correlation": 60,
    "cache_enabled_news_correlation": True,
    "thinking_enabled_news_correlation": False,
    "thinking_budget_news_correlation": 4000,
    "reasoning_effort_news_correlation": "high",
    "news_correlation_top_n": 30,
    "debate": {
        "procon": {"per_call_max_tokens": None, "synthesis_model": None, "synthesis_temperature": 0.5},
        "conditional": {
            "scenarios": [
                {"name": "上涨", "change": 0.20, "desc": "如果未来市场上涨 20%"},
                {"name": "下跌", "change": -0.20, "desc": "如果未来市场下跌 20%"},
                {"name": "震荡", "change": 0.05, "desc": "如果未来市场窄幅震荡±5%"},
            ]
        },
        "qa_concentration": {"threshold": 0.20},
        "max_total_tokens_per_report": 16000,
        "per_call_timeout_override": 90,
    },
    "fact_check": {
        "tolerance": 1.0,
        "tolerance_overrides": {
            "expert_review": 2.0,
            "health_check": 1.0,
            "global_macro": 1.0,
            "penetration_deep": 1.0,
        },
    },
    "pricing": {
        "currency": "CNY",
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "input_cache_hit": 0.3},
    },
}

# 模块显示名映射（与 _DEFAULT_LLM_SETTINGS["enabled_llm"] 的键名对齐）
_MODULE_LABELS = {
    "global_macro": "全球政经局势",
    "expert_review": "智囊团深度复盘",
    "health_check": "持仓体检报告",
    "penetration_deep": "穿透深度分析",
    "news_correlation": "财经新闻热点与持仓关联分析",
}


def _get_default_llm_settings_template() -> str:
    """返回带分组注释的默认 llm_settings.json 模板字符串。

    从 _DEFAULT_LLM_SETTINGS 自动生成，确保值与代码定义一致。
    支持 // 注释风格，由 _strip_json_comments() 剥离后解析。
    """
    d = _DEFAULT_LLM_SETTINGS
    lines = ["{"]

    def _kv(key: str, indent: int = 2) -> str:
        val = d[key]
        if isinstance(val, dict):
            dumped = json.dumps(val, indent=2, ensure_ascii=False)
            prefix = " " * indent
            return prefix + dumped.replace("\n", "\n" + prefix)
        return " " * indent + json.dumps(val, ensure_ascii=False)

    def _module_block(module: str):
        """生成单个模块的配置块（包含注释标题和所有键值）。"""
        prefix = module.replace("-", "_")
        label = _MODULE_LABELS.get(module, module)
        lines.append("")
        lines.append(f"  // ═══════════════════════════════════════════")
        lines.append(f"  // {label} — {module}")
        lines.append(f"  // ═══════════════════════════════════════════")
        for key in d:
            if key.endswith(f"_{prefix}"):
                lines.append(f"  {_kv(key)},")

    def _scalar(key: str, comment: str = ""):
        lines.append(f"  {_kv(key)}{',' if comment else ''}  {comment}")

    # ── 全局设置 ──
    lines.append("  // ═══════════════════════════════════════════")
    lines.append("  // 全局设置")
    lines.append("  // ═══════════════════════════════════════════")
    _scalar("max_retries")
    _scalar("llm_max_concurrency")
    lines.append("")

    # ── 模块开关 ──
    lines.append("  // ═══════════════════════════════════════════")
    lines.append("  // 模块开关 — 控制各 LLM 分析功能的启用/停用")
    lines.append("  // ═══════════════════════════════════════════")
    lines.append(f'  "enabled_llm": {json.dumps(d["enabled_llm"], indent=4, ensure_ascii=False)}')

    _module_block("global_macro")
    _module_block("expert_review")
    _module_block("health_check")
    _module_block("penetration_deep")

    # ── news_correlation ──
    lines.append("")
    lines.append("  // ═══════════════════════════════════════════")
    lines.append("  // 财经新闻热点与持仓关联分析 — news_correlation")
    lines.append("  // （注：news_correlation 不支持 output_brief 模式）")
    lines.append("  // ═══════════════════════════════════════════")
    for key in d:
        if key.endswith("_news_correlation"):
            lines.append(f"  {_kv(key)},")
    lines.append(f'  "news_correlation_top_n": {d["news_correlation_top_n"]},')

    # ── 辩论模式 ──
    lines.append("")
    lines.append("  // ═══════════════════════════════════════════")
    lines.append("  // 辩论模式（实验功能，缺省关闭）")
    lines.append("  // 通过 Feature Flag 控制启停，菜单 [S] 可交互开关")
    lines.append("  // ═══════════════════════════════════════════")
    debate = d["debate"]
    lines.append(f'  "debate": {{')
    lines.append(f"    // 正反辩论 — 三段式(白脸→黑脸→综合)")
    lines.append(f'    "procon": {json.dumps(debate["procon"], indent=4, ensure_ascii=False)},')
    lines.append(f"    // 条件推理 — 情景化分析")
    lines.append(f'    "conditional": {{')
    lines.append(f"      // 情景列表：每条含 name(情景名)/change(涨跌幅)/desc(描述)")
    lines.append(f'      "scenarios": [')
    for s in debate["conditional"]["scenarios"]:
        lines.append(f"        {json.dumps(s, ensure_ascii=False)},")
    lines.append(f"      ]")
    lines.append(f"    }},")
    lines.append(f"    // 集中度问答 — 集中度风险问答块")
    lines.append(f'    "qa_concentration": {json.dumps(debate["qa_concentration"])},')
    lines.append(f"    // 单次报告辩论模式总 token 预算上限（超出后回退标准模式）")
    lines.append(f'    "max_total_tokens_per_report": {debate["max_total_tokens_per_report"]},')
    lines.append(f"    // 辩论模式单次 API 调用超时覆盖（秒）")
    lines.append(f'    "per_call_timeout_override": {debate["per_call_timeout_override"]}')
    lines.append(f"  }},")

    # ── 事实校验 ──
    lines.append("")
    lines.append("  // ═══════════════════════════════════════════")
    lines.append("  // 事实校验（fact_check）— LLM 输出数值一致性检测")
    lines.append("  // ═══════════════════════════════════════════")
    fc = d["fact_check"]
    lines.append(f'  "fact_check": {{')
    lines.append(f"    // 全局数值偏差容差（百分点），默认 1.0 — LLM 声称的收益率/占比等")
    lines.append(f"    // 与真实值偏差在 ±tolerance 百分点内即视为通过校验")
    lines.append(f'    "tolerance": {fc["tolerance"]},')
    lines.append(f"    // 按模块覆盖容差（模块名 → 百分点）— 覆盖全局 tolerance")
    lines.append(f"    // 对于需要更大容差的分析模块（如 expert_review 综合判断多）,")
    lines.append(f"    // 可单独设置较宽松的阈值，避免过度告警")
    lines.append(f'    "tolerance_overrides": {{')
    for mod, val in fc["tolerance_overrides"].items():
        lines.append(f'      "{mod}": {val},')
    lines.append(f"    }}")
    lines.append(f"  }},")

    # ── 计价配置 ──
    lines.append("")
    lines.append("  // ═══════════════════════════════════════════")
    lines.append("  // 计价配置（默认使用 constants.py MODEL_PRICING，此处可覆盖）")
    lines.append("  // ═══════════════════════════════════════════")
    lines.append(f'  "pricing": {json.dumps(d["pricing"], indent=2, ensure_ascii=False)}')

    lines.append("}")
    lines.append("")
    return "\n".join(lines)
