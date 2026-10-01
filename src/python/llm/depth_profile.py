"""报告深度档位 — 「一次选择即约束模块集合与新闻采集规模」的成本调节面。

档位是**上界收窄**而非替代开关：``llm_settings.json → enabled_llm`` 的逐模块开关
仍决定该模块是否启用，档位只在其之上收窄可参与集合（``brief`` ⊂ ``standard``），
因此档位**永远无法打开用户显式关闭的模块**。

关键设计取舍（详见 ``docs-stm/plan/llm-depth-selfreview-source-override-design.md`` §3.3）：
档位**不写入提示词正文**——只作用于「哪些模块参与」与「新闻采集条数」。如此既有
四个模块的提示词承载入参不变，``llm/module_fingerprint.py`` 的指纹构造无需并入档位
（若档位进入提示词正文，两侧键必须同步并入该值，否则预检永不命中或档位形同虚设）。

缺省档位 ``standard`` 的模块集合与新闻条数**与未引入档位时逐字节一致**。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.python.core.registry import get_llm_module_names

logger = logging.getLogger("invest")

REPORT_DEPTH_LEVELS: tuple[str, ...] = ("brief", "standard", "deep")
"""全部合法档位（顺序即由省到全）。"""

REPORT_DEPTH_DEFAULT: str = "standard"
"""出厂默认档位；缺省时行为与既有版本逐字节一致。"""

_BRIEF_MODULES: frozenset[str] = frozenset({"global_macro"})
"""简版档仅保留的模块——全球政经局势（组合层面的宏观视角，单次调用）。"""


@dataclass(frozen=True)
class DepthProfile:
    """单档语义定义。

    Attributes:
        key: 档位标识（config 取值）。
        label: 显示名（报告自述与 CLI 提示共用，渠道层不另写文字）。
        desc: 一句话说明。
        max_modules: 参与模块的**上界**；实际参与集合 = 该上界 ∩（用户开关打开的模块）。
        news_limit_floor: 新闻采集条数的**下界**；``None`` 表示不改用户配置。
    """

    key: str
    label: str
    desc: str
    max_modules: frozenset[str]
    news_limit_floor: int | None


def _build_profiles() -> dict[str, DepthProfile]:
    """构造档位表（唯一事实来源）。

    模块集合从 ``core/registry.py`` 的 LLM 模块注册表派生——不另写模块清单，
    避免新增/改名模块时档位表与注册表漂移（模块注册表漂移的同类问题）。
    """
    all_modules = frozenset(get_llm_module_names().keys())
    return {
        "brief": DepthProfile(
            key="brief",
            label="简版",
            desc="仅全球政经局势，采集与调用最少、最快",
            max_modules=_BRIEF_MODULES,
            news_limit_floor=None,
        ),
        "standard": DepthProfile(
            key="standard",
            label="标准",
            desc="按各模块开关参与，新闻条数按用户配置",
            max_modules=all_modules,
            news_limit_floor=None,
        ),
        "deep": DepthProfile(
            key="deep",
            label="深度",
            desc="全部模块参与，新闻采集不少于 500 条",
            max_modules=all_modules,
            news_limit_floor=500,
        ),
    }


DEPTH_PROFILES: dict[str, DepthProfile] = _build_profiles()
"""档位表：0 / 1 档定义（键为 config 取值）。"""


def normalize_depth(value: object) -> str:
    """把任意取值规范为合法档位名；非法或缺失回落默认档。

    Args:
        value: config 中 ``llm_report_depth`` 的原始取值。

    Returns:
        合法档位名（``REPORT_DEPTH_LEVELS`` 之一）。
    """
    if isinstance(value, str):
        key = value.strip().lower()
        if key in DEPTH_PROFILES:
            return key
        logger.warning(
            "config.json llm_report_depth = %r 不是合法档位（可选 %s），按 %s 档处理",
            value,
            " / ".join(REPORT_DEPTH_LEVELS),
            REPORT_DEPTH_DEFAULT,
        )
    return REPORT_DEPTH_DEFAULT


def resolve_depth_profile(config: dict | None = None) -> DepthProfile:
    """解析当前生效档位。

    Args:
        config: 配置字典；``None`` 时自动读取 ``get_config()``（读取失败按默认档）。

    Returns:
        生效档位的 :class:`DepthProfile`。
    """
    if config is None:
        try:
            from src.python.config import get_config

            config = get_config()
        except Exception:  # noqa: BLE001 — 配置不可读属非致命降级，按默认档继续
            logger.debug("[depth_profile] 配置读取失败，按 %s 档处理", REPORT_DEPTH_DEFAULT)
            config = {}
    return DEPTH_PROFILES[normalize_depth((config or {}).get("llm_report_depth", REPORT_DEPTH_DEFAULT))]


def depth_gate(enabled: bool, module_key: str, profile: DepthProfile) -> bool:
    """档位与逐模块开关的交集判定。

    档位只做**收窄**：开关为关时一律不参与（档位不得打开用户显式关闭的模块）；
    开关为开时，仅且仅当模块在该档位上界内才参与。

    Args:
        enabled: ``llm_settings.json → enabled_llm.<module_key>`` 的取值。
        module_key: 模块语义名。
        profile: 生效档位。

    Returns:
        该模块本次是否参与。
    """
    return bool(enabled) and module_key in profile.max_modules


def effective_news_limit(configured: int, profile: DepthProfile) -> int:
    """按档位下界修正新闻采集条数（不改动用户配置本身）。

    Args:
        configured: 用户配置的 ``news_top_count``。
        profile: 生效档位。

    Returns:
        实际使用的新闻条数：档位有下界时取 ``max(configured, floor)``，否则原样返回。
    """
    if profile.news_limit_floor is None:
        return int(configured)
    return max(int(configured), int(profile.news_limit_floor))


def non_default_depth_line(profile: DepthProfile) -> str | None:
    """非默认档位的一句话自述（默认档返回 ``None``，保持零噪声）。

    报告是可脱离本机流转的文件，读者须能判断内容是否为非默认档位下的产物。
    """
    if profile.key == REPORT_DEPTH_DEFAULT:
        return None
    return f"本次报告深度档位：{profile.label}（{profile.desc}）"


__all__ = [
    "DEPTH_PROFILES",
    "REPORT_DEPTH_DEFAULT",
    "REPORT_DEPTH_LEVELS",
    "DepthProfile",
    "depth_gate",
    "effective_news_limit",
    "non_default_depth_line",
    "normalize_depth",
    "resolve_depth_profile",
]
