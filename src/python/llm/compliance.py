"""LLM 合规声明注入 — 统一在各模块 system prompt 尾部叠加研究辅助定位约束。

集中管理「仅供复盘参考、不构成投资建议」的合规约束，替代散落各模板的手写
免责声明。注入点为 ``llm.api.call_llm`` 单一漏斗，覆盖全部 LLM 模块
（全球政经复盘/智囊团/健康检查/穿透深度/新闻关联判定等），新增模块无需
各自声明。

设计要点：
- **幂等**：已含合规声明的 prompt 原样返回（调用方多次套用不会叠加）；
- **不动缓存指纹**：缓存指纹由结构化数据（持仓/行情摘要）计算，不含 prompt
  文本，注入不改变缓存键；旧缓存产物仍由报告模板层的免责声明兜底；
- **角色追加项**：窄判定类角色（如新闻关联）可经 ``role`` 追加专属约束。
"""

from __future__ import annotations

COMPLIANCE_CLOSING = (
    "【合规声明】以上分析内容为 AI 辅助生成的投资复盘参考，仅供个人学习研究使用，"
    "不构成任何投资建议；市场有风险，投资需谨慎，投资决策与后果由使用者自行承担。"
)
"""各模块 system prompt 统一尾部叠加的合规声明文本。"""

_ROLE_EXTRA_ITEMS: dict[str, tuple[str, ...]] = {
    "news_correlation": ("新闻关联判定仅基于公开信息与关键词/持仓名称匹配，不得引申为确定性因果关系或交易指令。",),
}
"""角色专属追加约束：键为模块语义名（与 LLM 配置键同名），值为追加条目元组。"""


def apply_compliance_guardrails(system_prompt: str, role: str = "") -> str:
    """在 system prompt 尾部叠加合规声明（幂等）。

    Args:
        system_prompt: 原始 system prompt。
        role: 模块语义名（如 ``news_correlation``）；命中角色追加项时额外叠加
            该角色的专属约束。未知角色仅叠加通用声明。

    Returns:
        叠加合规声明后的 system prompt；已含声明时原样返回。
    """
    if not system_prompt:
        return system_prompt
    if COMPLIANCE_CLOSING in system_prompt:
        return system_prompt
    parts = [system_prompt.rstrip(), "", COMPLIANCE_CLOSING]
    extra_items = _ROLE_EXTRA_ITEMS.get(role, ())
    parts.extend(extra_items)
    return "\n".join(parts)
