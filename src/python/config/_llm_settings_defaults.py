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
    "llm_max_thinking_concurrency": 1,
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
    "max_tokens_expert_review": 24000,
    "timeout_expert_review": 120,
    "cache_enabled_expert_review": True,
    "output_brief_expert_review": False,
    "thinking_enabled_expert_review": True,
    "thinking_budget_expert_review": 16000,
    "reasoning_effort_expert_review": "low",
    "system_prompt_health_check": None,
    "model_health_check": None,
    "temperature_health_check": 0.1,
    "max_tokens_health_check": 16000,
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
        "max_total_tokens_per_report": 48000,
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
        # 峰谷定价时段（DeepSeek 官方方案，北京时间）——模型价格仍以
        # constants.py MODEL_PRICING 为唯一默认源，此处仅配置峰谷时段/时区：
        #   timezone      — 峰谷判定时区（IANA 名称，默认 Asia/Shanghai）
        #   peak_periods  — 高峰时段（"HH:MM-HH:MM" 列表，闭区间）
        #   idle_periods  — 闲时时段（空列表 = 高峰之外的其余时间均按闲时价）
        # 含 "peak" 高峰价子段的模型（如 deepseek-v4-*）在高峰时段按 peak 价计费，
        # 其余时段按 base 价计费；无 "peak" 的模型始终按 base 价计费。模型价格
        # 覆盖示例（含 peak 子段）："deepseek-v4-flash": {"input": 1.5, "output": 4.5,
        # "input_cache_hit": 0.05, "peak": {"input": 3.0, "output": 9.0, "input_cache_hit": 0.10}}
        "timezone": "Asia/Shanghai",
        "peak_periods": ["09:00-12:00", "14:00-18:00"],
        "idle_periods": [],
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

    与 _config_defaults._build_template_from_defaults() 同构：逐行手拼
    带键名，保证生成的 JSON 可被 _strip_json_comments + json.loads 解析。
    """
    d = _DEFAULT_LLM_SETTINGS
    lines = ["{"]

    def _section(title: str) -> None:
        """生成区块分隔注释。"""
        lines.append("")
        lines.append("  // ═══════════════════════════════════════════")
        lines.append(f"  // {title}")
        lines.append("  // ═══════════════════════════════════════════")

    def _kv(key: str, comment: str = "", indent: int = 2) -> str:
        """生成 '  "key": value,  // comment' 形式的单行键值对。

        嵌套 dict 由调用方手拼，本函数仅处理标量/数组值。
        """
        val = d[key]
        pad = " " * indent
        return f'{pad}"{key}": {json.dumps(val, ensure_ascii=False)},  {comment}'.rstrip()

    def _module_block(module: str) -> None:
        """生成单个模块的配置块（注释标题 + 该模块全部 *_<module> 键）。"""
        prefix = module.replace("-", "_")
        label = _MODULE_LABELS.get(module, module)
        _section(f"{label} — {module}")
        for key in d:
            if key.endswith(f"_{prefix}"):
                lines.append(_kv(key))

    # ── 全局设置 ──
    _section("全局设置")
    lines.append(f'  "max_retries": {d["max_retries"]},')
    lines.append(f'  "llm_max_concurrency": {d["llm_max_concurrency"]},')
    lines.append(f'  "llm_max_thinking_concurrency": {d["llm_max_thinking_concurrency"]},')

    # ── 模块开关 ──
    _section("模块开关 — 控制各 LLM 分析功能的启用/停用")
    lines.append(f'  "enabled_llm": {json.dumps(d["enabled_llm"], indent=2, ensure_ascii=False)},')

    _module_block("global_macro")
    _module_block("expert_review")
    _module_block("health_check")
    _module_block("penetration_deep")

    # ── news_correlation ──
    _section("财经新闻热点与持仓关联分析 — news_correlation")
    lines.append("  // （注：news_correlation 不支持 output_brief 模式）")
    for key in d:
        if key.endswith("_news_correlation"):
            lines.append(_kv(key))
    lines.append(f'  "news_correlation_top_n": {d["news_correlation_top_n"]},')

    # ── 辩论模式 ──
    _section("辩论模式（实验功能，缺省关闭）")
    lines.append("  // 通过 Feature Flag 控制启停，菜单 [S] 可交互开关")
    debate = d["debate"]
    lines.append('  "debate": {')
    lines.append("    // 正反辩论 — 三段式(白脸→黑脸→综合)")
    lines.append(f'    "procon": {json.dumps(debate["procon"], indent=4, ensure_ascii=False)},')
    lines.append("    // 条件推理 — 情景化分析")
    lines.append('    "conditional": {')
    lines.append("      // 情景列表：每条含 name(情景名)/change(涨跌幅)/desc(描述)")
    lines.append('      "scenarios": [')
    scenarios = debate["conditional"]["scenarios"]
    for i, s in enumerate(scenarios):
        comma = "," if i < len(scenarios) - 1 else ""
        lines.append(f"        {json.dumps(s, ensure_ascii=False)}{comma}")
    lines.append("      ]")
    lines.append("    },")
    lines.append("    // 集中度问答 — 集中度风险问答块")
    lines.append(f'    "qa_concentration": {json.dumps(debate["qa_concentration"])},')
    lines.append("    // 单次报告辩论模式总 token 预算上限（超出后回退标准模式）")
    lines.append(f'    "max_total_tokens_per_report": {debate["max_total_tokens_per_report"]},')
    lines.append("    // 辩论模式单次 API 调用超时覆盖（秒）")
    lines.append(f'    "per_call_timeout_override": {debate["per_call_timeout_override"]}')
    lines.append("  },")

    # ── 事实校验 ──
    _section("事实校验（fact_check）— LLM 输出数值一致性检测")
    fc = d["fact_check"]
    lines.append('  "fact_check": {')
    lines.append("    // 全局数值偏差容差（百分点），默认 1.0 — LLM 声称的收益率/占比等")
    lines.append("    // 与真实值偏差在 ±tolerance 百分点内即视为通过校验")
    lines.append(f'    "tolerance": {fc["tolerance"]},')
    lines.append("    // 按模块覆盖容差（模块名 → 百分点）— 覆盖全局 tolerance")
    lines.append("    // 对于需要更大容差的分析模块（如 expert_review 综合判断多）,")
    lines.append("    // 可单独设置较宽松的阈值，避免过度告警")
    lines.append('    "tolerance_overrides": {')
    overrides = fc["tolerance_overrides"]
    for i, (mod, val) in enumerate(overrides.items()):
        comma = "," if i < len(overrides) - 1 else ""
        lines.append(f'      "{mod}": {val}{comma}')
    lines.append("    }")
    lines.append("  },")

    # ── 计价配置 ──
    _section("计价配置（默认使用 constants.py MODEL_PRICING，此处可覆盖）")
    lines.append(f'  "pricing": {json.dumps(d["pricing"], indent=2, ensure_ascii=False)}')

    lines.append("}")
    lines.append("")
    return "\n".join(lines)
