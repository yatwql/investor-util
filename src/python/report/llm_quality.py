"""LLM 模块输出质量分级 —— 按完整性/一致性给每个模块输出评级并随内容标注。

设计要点：

- **只标注，不阻断**：评级结果不改变生成流程、不触发重试、不影响缓存读写。
  「内容在但存在缺陷」的低评级（C/D/F）在模块内容头部追加一条「内容质量
  提示」横幅，让下游读者（人读 HTML/Excel、后续章节装配）知道该段输出需
  降级参考；内容缺失型（空内容、降级占位）已有各自醒目提示，不叠加横幅。
- **载体复用**：横幅直接拼接在模块 HTML 字符串头部，与既有的截断标记、
  缓存命中行、事实校验摘要同一套载体 —— 无需新增 pipeline_data 键、
  无需扩展现有报告生成函数的参数表，HTML 与 Excel 两条输出路径同时生效。
- **只读分级**：判定依据全部来自内容本身（正文长度、必需章节标记、降级
  占位签名），不引入额外数据依赖，也不写回缓存（缓存内容保持原样）。
- **开关**：由 ``features.module_quality_gate`` 控制（常规开关，默认开启）。

分级口径（A~F，自上而下首个命中者胜出）：

  ======  ==================================================
  评级    触发条件
  ======  ==================================================
  F       剥离标签后正文为空
  D       命中降级占位 / 截断标记，或正文短于该模块下限
  C       缺失该模块提示词要求的必需章节标记
  B       结构与必需章节齐备，但正文短于该模块参考篇幅
  A       结构与篇幅均达标
  ======  ==================================================

阈值与必需章节标记均为按模块配置的常量，见下方常量表；判定口径刻意保持
「一个条件对应一个评级」，避免制造无法解释的精度。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.python.core.registry import get_llm_module_name
from src.python.llm.api_base import TRUNCATION_MARKER
from src.python.llm.fallback import is_placeholder_content
from src.python.report.llm_content import _strip_html

logger = logging.getLogger("invest")

# 开关名（注册于 src/python/config/features.py）
_FEATURE_FLAG = "module_quality_gate"

# 承载评级的模块顺序，与 llm_content 四元组位置一一对应
_MODULE_KEYS = ("global_macro", "expert_review", "health_check", "penetration_deep")

# ── 评级常量 ────────────────────────────────────────────────

GRADE_A = "A"
GRADE_B = "B"
GRADE_C = "C"
GRADE_D = "D"
GRADE_F = "F"

# 需要上屏提示的评级：A/B 视为健康输出，不打扰读者
_ADVISORY_GRADES = frozenset({GRADE_C, GRADE_D, GRADE_F})

# ── 触发原因 ────────────────────────────────────────────────
# 同一评级可由不同原因触发，展示策略据此区分（见 _SELF_EVIDENT_TRIGGERS）。

TRIGGER_EMPTY = "empty"  # 正文为空
TRIGGER_PLACEHOLDER = "placeholder"  # 降级占位 / 截断标记
TRIGGER_TOO_SHORT = "too_short"  # 正文短于该模块下限
TRIGGER_MISSING_SECTIONS = "missing_sections"  # 缺必需章节标记
TRIGGER_THIN = "thin"  # 章节齐备但篇幅偏短
TRIGGER_OK = "ok"  # 章节齐备、篇幅达标

# 内容缺失型触发：失败本身已有醒目提示（占位文本写明「当前无法生成」、
# 空内容由报告模板兜底），再叠一条质量横幅只是把同一件事说两遍。
_SELF_EVIDENT_TRIGGERS = frozenset({TRIGGER_EMPTY, TRIGGER_PLACEHOLDER})

# ── 模块阈值 ────────────────────────────────────────────────
# 每模块的正文长度双阈值 (降级下限, 参考篇幅)，单位为剥离 HTML 标签后的字符数。
# 标定依据：data/cache/ 下真实健康输出的实测正文长度 ——
#   global_macro ≈1170 / health_check ≈2430 / penetration_deep ≈2150 字符。
# 降级下限取实测值的约 25%~40%，参考篇幅取约 60%~65%，为正常的篇幅波动留足余量，
# 只拦截「明显残缺」而非「写得比其他模块短」。
_LENGTH_THRESHOLDS: dict[str, tuple[int, int]] = {
    "global_macro": (300, 700),
    "expert_review": (400, 1000),
    "health_check": (500, 1200),
    "penetration_deep": (500, 1200),
}
_DEFAULT_LENGTH_THRESHOLDS = (300, 800)

# ── 必需章节标记 ────────────────────────────────────────────
# 取自各模块 System Prompt 中逐条枚举的固定章节小标题（见 llm/prompts_core.py）。
# 只收录「提示词明文规定了固定章节清单」的模块：
#   - health_check      —— ## 综合评分 / 一~五 五个维度 / ## 改进建议
#   - penetration_deep  —— ## 行业集中度分析 / ## 品种集中度分析 / ## 国别·币种暴露 / ## 综合建议
# 未收录的模块只做长度分级，原因是其输出结构不固定：
#   - global_macro      —— 纯散文，提示词明确要求分段、不使用 HTML 标签
#   - expert_review     —— 标准模式要求「### 操作建议」表，辩论模式用编号式
#                          综合行动建议，两种模式章节不同，硬编标记会误判
# 标记随对应 System Prompt 的章节规定变化，二者需同步维护 —— 由测试
# test_module_markers_match_prompts 直接比对提示词常量，二者不同步即会报错。
_REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "health_check": (
        "综合评分",
        "风险分散度",
        "流动性",
        "收益合理性",
        "成本结构",
        "数据质量",
        "改进建议",
    ),
    "penetration_deep": (
        "行业集中度",
        "品种集中度",
        "国别",
        "币种",
        "综合建议",
    ),
}


@dataclass(frozen=True)
class ModuleQuality:
    """单个 LLM 模块的输出质量评级结果。"""

    module_key: str
    name: str
    grade: str
    trigger: str
    reason: str

    @property
    def is_advisory(self) -> bool:
        """是否需要随内容上屏质量提示。

        低评级（C/D/F）中，内容缺失型（空内容 / 降级占位）已有各自的醒目
        提示，不再叠加横幅；其余低评级说明「内容在，但存在缺陷」，需要标注。
        """
        return self.grade in _ADVISORY_GRADES and self.trigger not in _SELF_EVIDENT_TRIGGERS


def grade_module(module_key: str, html: str | None) -> ModuleQuality:
    """对单个模块的 LLM 输出评级。

    Args:
        module_key: 模块键（global_macro / expert_review / health_check / penetration_deep）
        html: 模块输出 HTML；None 或空串评 F

    Returns:
        评级结果（模块显示名取自 registry，未注册时回退为模块键）
    """
    name = get_llm_module_name(module_key)
    raw = html or ""
    text = _strip_html(raw)
    min_chars, comfort_chars = _LENGTH_THRESHOLDS.get(module_key, _DEFAULT_LENGTH_THRESHOLDS)

    if not text:
        return ModuleQuality(module_key, name, GRADE_F, TRIGGER_EMPTY, "正文为空")
    if is_placeholder_content(raw) or TRUNCATION_MARKER in text:
        return ModuleQuality(module_key, name, GRADE_D, TRIGGER_PLACEHOLDER, "命中降级占位或截断标记")
    if len(text) < min_chars:
        return ModuleQuality(
            module_key,
            name,
            GRADE_D,
            TRIGGER_TOO_SHORT,
            f"正文过短（{len(text)} 字，低于下限 {min_chars} 字）",
        )

    missing = [m for m in _REQUIRED_MARKERS.get(module_key, ()) if m not in text]
    if missing:
        return ModuleQuality(
            module_key,
            name,
            GRADE_C,
            TRIGGER_MISSING_SECTIONS,
            "缺失必需章节：" + "、".join(missing),
        )
    if len(text) < comfort_chars:
        return ModuleQuality(
            module_key,
            name,
            GRADE_B,
            TRIGGER_THIN,
            f"正文偏短（{len(text)} 字，低于参考篇幅 {comfort_chars} 字）",
        )
    return ModuleQuality(module_key, name, GRADE_A, TRIGGER_OK, "章节齐备、篇幅达标")


def build_quality_banner(quality: ModuleQuality) -> str:
    """构建并入模块内容头部的质量提示横幅（仅低评级模块调用）。

    横幅以【内容质量提示】起首而非 ⚠ 起首 —— Excel 侧按行首 `⚠ ` 识别事实
    校验告警块，换用方括号前缀避免被误判为校验告警。

    Args:
        quality: 评级结果

    Returns:
        内联样式 HTML 段落
    """
    return (
        '<p style="color:#b45309;background:#fffbeb;border-left:3px solid #f59e0b;'
        'padding:6px 10px;margin:0 0 10px 0;font-size:13px">'
        f"【内容质量提示】本模块输出评级 {quality.grade}：{quality.reason}。"
        "该内容仅供降级参考，请结合原始数据谨慎使用。</p>"
    )


def grade_modules(llm_content: tuple) -> list[ModuleQuality]:
    """对 llm_content 四元组逐模块评级（未生成或非文本的模块跳过）。

    Args:
        llm_content: (global_macro, expert_review, health_check, penetration_deep)

    Returns:
        评级结果列表，仅含「内容为非空字符串」的模块。非字符串内容按「不可
        评级」跳过 —— 分级是只读旁路，不为上游数据形状异常阻断报告生成。
    """
    results: list[ModuleQuality] = []
    for idx, module_key in enumerate(_MODULE_KEYS):
        if idx >= len(llm_content or ()):
            break
        html = llm_content[idx]
        if not isinstance(html, str) or not html:
            continue
        results.append(grade_module(module_key, html))
    return results


def apply_quality_banners(llm_content: tuple, reporter=None) -> tuple:
    """按开关给低评级模块的内容头部追加质量提示横幅。

    开关关闭时原样返回（同一对象），调用方无需分叉判断。横幅注入发生在
    缓存读取之后，不写回缓存 —— 缓存内容始终保持 LLM 原始输出。

    Args:
        llm_content: LLM 内容四元组
        reporter: 可选的进度报告器，用于汇总提示低评级模块

    Returns:
        处理后的内容元组（无低评级模块时与入参等值）
    """
    from src.python.config.features import is_feature_enabled

    if not is_feature_enabled(_FEATURE_FLAG) or not llm_content:
        return llm_content

    content = list(llm_content)
    advisory: list[str] = []
    for quality in grade_modules(llm_content):
        idx = _MODULE_KEYS.index(quality.module_key)
        logger.info("[llm_quality] %s 评级 %s（%s）", quality.name, quality.grade, quality.reason)
        if not quality.is_advisory:
            continue
        content[idx] = build_quality_banner(quality) + str(content[idx])
        advisory.append(f"{quality.name}（{quality.grade}）")

    if advisory and reporter is not None:
        reporter.warn("内容质量提示：" + "、".join(advisory) + " 评级偏低，已在内容中标注")
    return tuple(content)
