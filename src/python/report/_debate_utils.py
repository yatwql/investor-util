"""辩论模式检测工具函数。

为 HTML / Excel 报告提供统一的辩论模式标签与组合标识检测。
消除 html_writer.py 与 excel_generator.py 之间的重复逻辑。
"""

from __future__ import annotations


def detect_debate_mode(
    debate_info: dict | None = None,
) -> tuple[str | None, str | None]:
    """检测并返回辩论模式标签与组合标识。

    先尝试从 debate_info 中提取（LLM 缓存命中时优先级高），
    降级时从 feature flag 实时检测。

    Args:
        debate_info: 辩论信息 dict（含 mode_label / mode_combination 键）

    Returns:
        (mode_label, mode_combination) 二元组，均可能为 None
    """
    from src.python.features import is_feature_enabled

    mode_label: str | None = None
    mode_combination: str | None = None

    if debate_info and isinstance(debate_info, dict):
        mode_label = debate_info.get("mode_label")
        mode_combination = debate_info.get("mode_combination")

    if not mode_label:
        if is_feature_enabled("llm_debate_procon"):
            mode_label = "🧪 辩论模式"
        elif is_feature_enabled("llm_debate_conditional") or is_feature_enabled(
            "llm_debate_qa_concentration"
        ):
            mode_label = "🧪 实验模式"

    if not mode_combination:
        _comb_parts = []
        if is_feature_enabled("llm_debate_procon"):
            _comb_parts.append("正反辩论")
        if is_feature_enabled("llm_debate_conditional"):
            _comb_parts.append("条件推理")
        if is_feature_enabled("llm_debate_qa_concentration"):
            _comb_parts.append("集中度问答")
        mode_combination = "+".join(_comb_parts) if _comb_parts else None

    return mode_label, mode_combination
