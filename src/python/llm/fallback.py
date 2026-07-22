"""LLM 失败自动降级模板 — 全失败时提供占位文本。

当所有 LLM 模块均生成失败时，full 报告路径自动降级为使用占位文本，
避免报告页签完全空白。

设计原则：
  - 降级是静默的：用户看到的是"数据暂不可用"而非错误堆栈
  - 降级是完整的：所有 LLM 页签都获得同质的占位内容
  - 降级是可配置的：通过 features.llm_* 开关可独立关闭各模块
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("invest")

# ── 占位文本模板 ───────────────────────────────────────────

_PLACEHOLDER_TEXT: dict[str, str] = {
    "global_macro": (
        "<h3>🌍 全球政经局势</h3>"
        "<p>⚠️ 当前无法获取全球政经局势分析。</p>"
        "<p>可能原因：LLM API 服务暂时不可用、网络连接异常或 API Key 配置错误。</p>"
        "<p>建议稍后重试，或检查 <code>data/config/llm_settings.json</code> 中 API 配置是否正确。</p>"
        "<hr/><p><em>数据获取时间：{timestamp}</em></p>"
    ),
    "expert_review": (
        "<h3>🧠 智囊团深度复盘</h3>"
        "<p>⚠️ 当前无法生成智囊团深度复盘内容。</p>"
        "<p>可能原因：LLM API 服务暂时不可用、网络连接异常或 API Key 配置错误。</p>"
        "<p>建议稍后重试，或检查 <code>data/config/llm_settings.json</code> 中 API 配置是否正确。</p>"
        "<hr/><p><em>数据获取时间：{timestamp}</em></p>"
    ),
    "health_check": (
        "<h3>🏥 持仓体检报告</h3>"
        "<p>⚠️ 当前无法生成持仓体检报告。</p>"
        "<p>可能原因：LLM API 服务暂时不可用、网络连接异常或 API Key 配置错误。</p>"
        "<p>建议稍后重试，或检查 <code>data/config/llm_settings.json</code> 中 API 配置是否正确。</p>"
        "<hr/><p><em>数据获取时间：{timestamp}</em></p>"
    ),
    "penetration_deep": (
        "<h3>🔍 穿透深度分析</h3>"
        "<p>⚠️ 当前无法生成穿透深度分析。</p>"
        "<p>可能原因：LLM API 服务暂时不可用、网络连接异常或 API Key 配置错误。</p>"
        "<p>建议稍后重试，或检查 <code>data/config/llm_settings.json</code> 中 API 配置是否正确。</p>"
        "<hr/><p><em>数据获取时间：{timestamp}</em></p>"
    ),
}

_MODULE_KEYS = ("global_macro", "expert_review", "health_check", "penetration_deep")

__all__ = [
    "build_fallback_llm_content",
    "is_all_llm_failed",
    "get_placeholder_text",
]


def get_placeholder_text(module_key: str, timestamp: str | None = None) -> str:
    """获取指定模块的占位文本。

    Args:
        module_key: 模块键名（global_macro / expert_review 等）
        timestamp: 可选时间戳，不传则自动生成

    Returns:
        占位 HTML 文本
    """
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
    template = _PLACEHOLDER_TEXT.get(module_key, "")
    if not template:
        return f"<p>⚠️ {module_key} 内容暂不可用（数据获取时间：{ts}）</p>"
    return template.format(timestamp=ts)


def is_all_llm_failed(llm_content: tuple) -> bool:
    """判断所有 LLM 模块是否全部失败。

    Args:
        llm_content: (global_macro_html, expert_review_html, health_check_html, penetration_deep_html)
                     其中每个元素为 str 或 None

    Returns:
        True = 全部为 None（全部失败）
    """
    if not llm_content or len(llm_content) < 4:
        return True
    return all(c is None for c in llm_content[:4])


def build_fallback_llm_content(
    llm_content: tuple,
    force: bool = False,
) -> tuple:
    """构建 LLM 降级内容。

    当所有 LLM 模块均失败时，使用占位文本替换全部内容。

    Args:
        llm_content: 原始 LLM 内容元组 (global_macro, expert_review, health_check, penetration_deep)
        force: 设为 True 时强制使用占位文本（用于测试/预览）

    Returns:
        处理后的 LLM 内容元组
    """
    if not force and not is_all_llm_failed(llm_content):
        # 部分成功 → 仅替换失败项
        result = list(llm_content[:4])
        for i, module_key in enumerate(_MODULE_KEYS):
            if result[i] is None:
                result[i] = get_placeholder_text(module_key)
        return tuple(result)

    if force or is_all_llm_failed(llm_content):
        # 全部失败 → 全部使用占位文本
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        return tuple(get_placeholder_text(key, timestamp=ts) for key in _MODULE_KEYS)

    return llm_content
