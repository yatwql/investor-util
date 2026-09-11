"""功能开关注册表 — Feature Flag 体系。

提供集中管理功能开关的能力，替代分散在各模块中的条件判断。
所有开关在注册表中统一声明默认值，支持运行时启用/禁用。

用法：
  >>> from src.python.config.features import is_feature_enabled, FEATURE_FLAGS
  >>> if is_feature_enabled("enable_interactive_charts"):
  ...     embed_chart_assets()

配置持久化：功能开关可通过 features.json 覆写默认值。
全部开关在 :data:`feature_switch_registry` 一处登记（显示名/说明/分组/默认值/
产物影响），TUI 面板、Web 配置面板、CLI 取值域与文档清单一律由它派生——渠道层
不得另写开关清单。分组（实验组 / 常规组）决定面板可见性，「转正」即改分组与
默认值两个字段，可见性随之延续。
模块级 LLM 分析章节、新闻源、报告章节等**不在此登记**——它们各有归属文件，
见 ``feature_switch_registry`` 上方说明。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from src.python.core.atomic_write import write_json_atomic
from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 路径常量 ────────────────────────────────────────────────

_FEATURES_FILE = os.path.join(PROJECT_ROOT, "data/config/features.json")

# ── 分组常量 ────────────────────────────────────────────────
# 分组表达的是**生命周期的当前状态**，不是优先级、不是新旧：
#   GROUP_EXPERIMENTAL —— 会改变产物、需真实数据验证后择机转正，出厂默认关
#   GROUP_STANDARD     —— 常驻能力，出厂默认开、用户可关
# 「转正」= 把一条声明从实验组改到常规组并把 default 改 True。此前「默认值」与
# 「是否实验项」是同一件事的两个名字：转正会连带摘掉面板入口（doctor_check 转正
# 后只剩手改 features.json 一条关闭途径），而从未被标为实验项的 metrics_* 则从来
# 没有过任何界面入口。分组把这两件事拆开——可见性由分组决定、取值由 default 决定。

GROUP_EXPERIMENTAL = "experimental"
GROUP_STANDARD = "standard"

# 分组标题（TUI 菜单 [S] 与 Web 配置面板共用同一措辞，渠道层不另写文字）
GROUP_LABELS: dict[str, str] = {
    GROUP_EXPERIMENTAL: "⚗ 实验性功能（默认关闭）",
    GROUP_STANDARD: "常规开关（默认开启）",
}
# 面板分块顺序（顺序即渲染顺序）
GROUP_ORDER: tuple[str, ...] = (GROUP_EXPERIMENTAL, GROUP_STANDARD)


@dataclass(frozen=True)
class FeatureSwitchDef:
    """单条功能开关声明。

    Attributes:
        label: 显示名（TUI 面板行名 / Web 配置面板标签，服务端同源下发）
        desc: 一句话说明（CLI 报错提示、控制台横幅、文档）
        group: 分组（``GROUP_EXPERIMENTAL`` / ``GROUP_STANDARD``）
        default: 出厂默认值（``features.json`` 未覆写时的取值）
        affects_report: 开启后报告产物内容是否可能不同——决定它是否进入产物自述
    """

    label: str
    desc: str
    group: str
    default: bool
    affects_report: bool


# ── 功能开关注册表（唯一登记点） ────────────────────────────
# 渠道层（TUI 面板、Web 配置面板、CLI 取值域与提示）与各文档清单一律由此派生，
# **不得另写清单**——一处登记即三面上屏，改一处即三面同步。声明顺序即面板顺序。
#
# 本注册表只登记**有消费者的开关**（全仓必有一处 is_feature_enabled 读取其取值）。
# 其余开关各有归属文件，不在此登记、也不要再往这里搬：
#   - LLM 模块启停 / 基金深度分析模块 → llm_settings.json 的 enabled_llm（TUI 菜单 S
#     标准模块区、Web 配置面板「LLM 分析章节」组）
#   - 新闻源启停 → config.json 的 news_sources
#   - 历史走势与回撤 → config.json 的 enable_history
#   - 各报告章节与增强子模块 → config.json 的 enable_* 键
#   - 匿名化模式 → config.json 的 anonymization.mode
# 声明了却无人读取的开关会让用户照文档配置后毫无效果（本注册表曾含 16 项此类
# 陈旧开关，已全部移除）。新增开关必须同时接线到消费点，回归测试见
# test_features.py::TestRegistryLiveness。
#
# ``affects_report`` 是**产物自述的准入口径**：开启该开关后报告产物的内容是否可能
# 不同。True 者（实验组）进入报告自述（HTML 页脚 / Excel 落点）与控制台横幅，读者
# 据此判断手上这份产物是否非默认开关下的结果；只改入口可见性的开关答 False，不得
# 凭惯性落进自述——列出一个不改报告任何字节的开关，读者会推断内容受其影响。
feature_switch_registry: dict[str, FeatureSwitchDef] = {
    # ── 实验性功能：辩论三式 ──
    "llm_debate_procon": FeatureSwitchDef("辩论-正反辩论", "三段式(白脸→黑脸→综合)", GROUP_EXPERIMENTAL, False, True),
    "llm_debate_conditional": FeatureSwitchDef(
        "辩论-条件推理", "情景化分析(涨/跌/震荡)", GROUP_EXPERIMENTAL, False, True
    ),
    "llm_debate_qa_concentration": FeatureSwitchDef(
        "辩论-集中度问答", "集中度风险问答", GROUP_EXPERIMENTAL, False, True
    ),
    # ── 实验性功能：LLM 输出增强 ──
    "decision_reflection": FeatureSwitchDef(
        "决策跨期反思闭环",
        "登记决策 → 真实行情结算命中率 → 教训回灌专家复盘提示词",
        GROUP_EXPERIMENTAL,
        False,
        True,
    ),
    "signal_pre_digest": FeatureSwitchDef(
        "信号预消化",
        "市场温度/估值分位/尾部风险预消化为带方向标注的信号行注入复盘与体检提示词",
        GROUP_EXPERIMENTAL,
        False,
        True,
    ),
    "module_quality_gate": FeatureSwitchDef(
        "模块级质量分级",
        "按完整性/一致性给各 LLM 模块输出评 A~F 级，低评级随内容头部标注质量提示（不阻断不重试）",
        GROUP_EXPERIMENTAL,
        False,
        True,
    ),
    "decision_header_parse": FeatureSwitchDef(
        "决策头结构化",
        "提示词追加受控 JSON 决策头，抽取优先读结构化、失败回落确定性表格解析（决策词归一，防写反方向）",
        GROUP_EXPERIMENTAL,
        False,
        True,
    ),
    "signal_ledger": FeatureSwitchDef(
        "确定性信号沉淀",
        "确定性算法评级（温度/估值/尾部风险/风格/再平衡超限）沉淀为带实时-非实时标签的账本，统计默认只算实时",
        GROUP_EXPERIMENTAL,
        False,
        True,
    ),
    # ── 实验性功能：数据层 ──
    "datasource_credential_ready": FeatureSwitchDef(
        "数据源凭据就绪",
        "声明数据源所需凭据，缺失时链路跳过并给出可读指引；体检与健康检查报告就绪状态（当前全部数据源免费无需凭据）",
        GROUP_EXPERIMENTAL,
        False,
        True,
    ),
    # ── 常规开关：量化指标（关闭即报告少一项指标） ──
    "metrics_sharpe": FeatureSwitchDef("量化指标-夏普比率", "报告输出夏普比率", GROUP_STANDARD, True, True),
    "metrics_calmar": FeatureSwitchDef("量化指标-卡玛比率", "报告输出卡玛比率", GROUP_STANDARD, True, True),
    "metrics_hhi": FeatureSwitchDef("量化指标-HHI 集中度", "报告输出 HHI 集中度", GROUP_STANDARD, True, True),
    "metrics_winrate": FeatureSwitchDef("量化指标-胜率", "报告输出胜率", GROUP_STANDARD, True, True),
    "metrics_turnover": FeatureSwitchDef("量化指标-换手率", "报告输出换手率", GROUP_STANDARD, True, True),
    "metrics_risk_contribution": FeatureSwitchDef(
        "量化指标-风险贡献", "报告输出各持仓风险贡献", GROUP_STANDARD, True, True
    ),
    "metrics_beta": FeatureSwitchDef("量化指标-Beta", "报告输出组合 Beta", GROUP_STANDARD, True, True),
    # ── 常规开关：功能特性 ──
    "enable_interactive_charts": FeatureSwitchDef(
        "报告图表交互",
        "Chart.js 交互图（缩放/悬停）；关闭即回退 Canvas+表格静态渲染，且 HTML 不再单文件自包含",
        GROUP_STANDARD,
        True,
        True,
    ),
    # ── 常规开关：只读诊断（不改产物、不写文件，默认关的代价是环境出故障者看不到它） ──
    "doctor_check": FeatureSwitchDef(
        "系统自检上屏",
        "TUI 菜单 [D] 与 Web「系统自检」卡片可见性；CLI doctor 子命令不受本开关约束",
        GROUP_STANDARD,
        True,
        False,
    ),
    # ── 常规开关：内部接缝（开关两态下报告产物逐源等价，保留为回退杠杆） ──
    "datasource_adapter": FeatureSwitchDef(
        "数据源适配契约",
        "行情域三源走三段式适配器（参数转译→抓取→映射到标准字段）；置 false 回退既有转换函数",
        GROUP_STANDARD,
        True,
        False,
    ),
}

# 出厂默认值投影：``get_feature_defaults()`` 与兼容既有引用的取值表
_FEATURE_FLAGS_DEFAULT: dict[str, bool] = {flag: d.default for flag, d in feature_switch_registry.items()}

# ── 注册表查询 ──────────────────────────────────────────────


def switches_in_group(group: str) -> list[tuple[str, FeatureSwitchDef]]:
    """返回某分组下的开关声明 ``[(开关名, 声明), ...]``（顺序 = 注册表顺序）。

    面板渲染与实验清单的唯一取数入口——渠道层据此分块，不自行筛选。
    """
    return [(flag, d) for flag, d in feature_switch_registry.items() if d.group == group]


def is_experimental_switch(flag: str) -> bool:
    """判定开关是否属实验组（``--experiment`` 的取值域即此集合）。"""
    d = feature_switch_registry.get(flag)
    return d is not None and d.group == GROUP_EXPERIMENTAL


# ── 开关名解析（``--experiment`` / ``--feature``） ──────────

EXPERIMENT_ALL = "all"

# ``--feature NAME=VALUE`` 的取值词表（大小写不敏感）
_SWITCH_TRUE_TOKENS = frozenset({"on", "true", "1", "yes", "enable", "enabled"})
_SWITCH_FALSE_TOKENS = frozenset({"off", "false", "0", "no", "disable", "disabled"})


def _match_experiment(token: str) -> str | None:
    """按开关名（大小写不敏感）或显示名（精确）匹配单个实验功能。

    Returns:
        命中的开关名，未匹配到返回 None
    """
    lowered = token.lower()
    for flag, d in switches_in_group(GROUP_EXPERIMENTAL):
        if flag.lower() == lowered or d.label == token:
            return flag
    return None


def resolve_experiment_flags(names: list[str]) -> tuple[set[str], list[str]]:
    """将用户输入的实验功能名解析为开关名集合（注册表驱动）。

    接受三种写法（忽略首尾空白；开关名大小写不敏感）：
      - 开关名：``signal_pre_digest``
      - 显示名：``信号预消化``
      - ``all``：全部实验功能

    Args:
        names: 用户输入的名称列表（空白项自动跳过）

    Returns:
        ``(命中的开关名集合, 未识别的原始名称列表)``；调用方据此决定
        是全部启用还是报错提示可用清单。
    """
    resolved: set[str] = set()
    unknown: list[str] = []
    for raw in names:
        token = (raw or "").strip()
        if not token:
            continue
        if token.lower() == EXPERIMENT_ALL:
            resolved.update(flag for flag, _d in switches_in_group(GROUP_EXPERIMENTAL))
            continue
        hit = _match_experiment(token)
        if hit is None:
            unknown.append(raw)
        else:
            resolved.add(hit)
    return resolved, unknown


def describe_experiment_flags() -> str:
    """返回实验功能清单的人类可读串（供 CLI 帮助与报错提示复用）。"""
    return "、".join(f"{flag}（{d.label}）" for flag, d in switches_in_group(GROUP_EXPERIMENTAL))


def describe_switches() -> str:
    """返回全部功能开关清单的人类可读串（``--feature`` 报错提示复用）。"""
    return "、".join(f"{flag}（{d.label}）" for flag, d in feature_switch_registry.items())


def resolve_switch_values(pairs: list[tuple[str, bool]] | None) -> list[tuple[str, bool]]:
    """把 ``--feature NAME=VALUE`` 解析结果收敛为待应用的覆写列表。

    Args:
        pairs: argparse 收集的 ``(开关名, 取值)`` 列表（可为 None）

    Returns:
        去重后的 ``(开关名, 取值)`` 列表，后者覆盖前者（同名重复时以最后一次为准）；
        输入为空时返回空列表。
    """
    merged: dict[str, bool] = {}
    for flag, value in pairs or []:
        merged[flag] = value
    return list(merged.items())


def parse_switch_override(token: str) -> tuple[str, bool]:
    """解析 ``--feature`` 的单个取值 ``NAME=VALUE``。

    取值在 argparse ``type`` 回调中即时校验——错误的开关名或取值当场报错并列出
    可选项，而不是等到运行中途静默无效。

    Args:
        token: 形如 ``module_quality_gate=on`` / ``doctor_check=off`` 的字符串

    Returns:
        ``(开关名, 取值)``

    Raises:
        ValueError: 缺少 ``=``、开关名未知、或取值不在词表内
    """
    name, sep, raw_value = token.partition("=")
    name = name.strip()
    if not sep or not name:
        raise ValueError("应为 NAME=VALUE 形式（如 module_quality_gate=on）")
    if name not in feature_switch_registry:
        raise ValueError(f"未知功能开关 '{name}'；可选: {describe_switches()}")

    value = raw_value.strip().lower()
    if value in _SWITCH_TRUE_TOKENS:
        return name, True
    if value in _SWITCH_FALSE_TOKENS:
        return name, False
    raise ValueError(f"开关 '{name}' 的取值 '{raw_value}' 不可识别；可选: on / off")


def enabled_experimental_features() -> list[tuple[str, str]]:
    """返回当前已启用、且**可能改变报告产物**的实验功能 ``[(开关名, 显示名), ...]``。

    报告层用它在**产物自身上**标注生成条件（HTML 页脚 / Excel 落点）——报告是
    可脱离本机流转的文件，读者须能判断内容是否为非默认开关下的产物。

    只列注册表中 ``affects_report`` 为真者：只改交互入口可见性的开关不改报告
    任何字节，列进自述会让读者推断内容受其影响。清单取自
    :data:`feature_switch_registry` 的实验组，注册表仍是唯一来源；TUI 菜单 [S] 与
    Web 配置面板渲染的是**全部开关**（含不影响产物者与常规组），两者用途不同。

    Returns:
        已启用项的 ``(开关名, 显示名)`` 列表，按注册表顺序；无启用项时返回空列表。
    """
    return [
        (flag, d.label)
        for flag, d in switches_in_group(GROUP_EXPERIMENTAL)
        if d.affects_report and is_feature_enabled(flag)
    ]


def log_experimental_features() -> None:
    """如果已启用实验性功能，在日志中以红色高亮显示具体开启了什么功能。

    唯一调用点为报告入口 ``report/orchestrator.generate_report``（在配置初始化
    之后），故 TUI / CLI / Web 三条入口在生成报告时均会提示——「本次报告受哪些
    实验功能影响」正是需要看到这条信息的时刻。
    通过 ``logger.error()`` 输出以触发 ``_ColoredFormatter`` 的红色着色。
    """
    enabled = enabled_experimental_features()
    if not enabled:
        return

    import logging

    logger = logging.getLogger("invest")
    sep = "=" * 48

    logger.error(sep)
    logger.error("  ⚗ 实验性功能已开启！")
    logger.error(sep)
    for flag, name in enabled:
        logger.error("  ⚗ %s — %s", name, feature_switch_registry[flag].desc)
    logger.error(sep)


__all__ = [
    "EXPERIMENT_ALL",
    "FEATURE_FLAGS",
    "GROUP_EXPERIMENTAL",
    "GROUP_LABELS",
    "GROUP_ORDER",
    "GROUP_STANDARD",
    "FeatureSwitchDef",
    "describe_experiment_flags",
    "describe_switches",
    "enabled_experimental_features",
    "feature_switch_registry",
    "get_feature_defaults",
    "is_experimental_switch",
    "is_feature_enabled",
    "log_experimental_features",
    "parse_switch_override",
    "resolve_experiment_flags",
    "resolve_switch_values",
    "set_feature_enabled",
    "switches_in_group",
    "load_feature_overrides",
    "save_feature_overrides",
    "reset_feature_flags",
]

# ── 运行时状态 ──────────────────────────────────────────────
# 合并默认值 + 外部覆写后的最终生效值

FEATURE_FLAGS: dict[str, bool] = dict(_FEATURE_FLAGS_DEFAULT)
_FEATURES_LOCK = threading.Lock()


def get_feature_defaults() -> dict[str, bool]:
    """返回功能开关的出厂默认值（不受运行时覆写影响）。"""
    return dict(_FEATURE_FLAGS_DEFAULT)


def is_feature_enabled(flag_name: str) -> bool:
    """检查指定功能开关是否启用。

    Args:
        flag_name: 功能开关名称（如 "llm_global_macro"）

    Returns:
        True 表示功能启用，False 表示功能禁用
    """
    if flag_name not in FEATURE_FLAGS:
        logger.debug("[features] 未知功能开关 '%s'，视为关闭", flag_name)
        return False
    return FEATURE_FLAGS[flag_name]


def set_feature_enabled(flag_name: str, enabled: bool) -> None:
    """运行时切换功能开关状态（不持久化）。

    持久化覆写请调用 save_feature_overrides()。

    Args:
        flag_name: 功能开关名称
        enabled: True 启用 / False 禁用
    """
    if flag_name not in FEATURE_FLAGS:
        logger.warning("[features] 试图设置未知功能开关 '%s'，忽略", flag_name)
        return
    old = FEATURE_FLAGS[flag_name]
    FEATURE_FLAGS[flag_name] = enabled
    if old != enabled:
        logger.info("[features] 功能开关 '%s': %s → %s", flag_name, old, enabled)


def load_feature_overrides() -> None:
    """从 features.json 加载覆写配置，合并到 FEATURE_FLAGS。

    文件中仅需列出需要覆写的开关键值对，未列出的保持默认值。

    JSON 格式：
      {
        "enable_interactive_charts": false,
        "metrics_hhi": true
      }
    """
    if not os.path.exists(_FEATURES_FILE):
        return
    try:
        with open(_FEATURES_FILE, encoding="utf-8") as f:
            overrides = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[features] 加载覆写文件失败: %s", e)
        return

    if not isinstance(overrides, dict):
        logger.warning("[features] 覆写文件格式异常（应为 JSON object），忽略")
        return

    valid_count = 0
    changed = 0
    unknown: list[str] = []
    with _FEATURES_LOCK:
        for flag_name, value in overrides.items():
            if isinstance(value, bool) and flag_name in FEATURE_FLAGS:
                changed += FEATURE_FLAGS[flag_name] != value
                FEATURE_FLAGS[flag_name] = value
                valid_count += 1
            elif isinstance(value, bool):
                unknown.append(flag_name)
                FEATURE_FLAGS[flag_name] = value
                valid_count += 1
                changed += 1
            else:
                logger.warning("[features] 覆写 '%s' 值应为 bool，忽略", flag_name)

    # 无消费者开关一次告警（多为陈旧开关或拼写错误）：这类键在本版本不驱动任何
    # 行为，用户照文档配置后会毫无效果，必须让其可见。收集后合并成一条——逐键
    # 打印会在每次启动刷屏，而 features.json 在模块导入时就会加载一次。
    if unknown:
        logger.warning(
            "[features] features.json 含 %d 项无消费者的开关，配置后不产生任何效果"
            "（请核对拼写，或查阅 how-to-config 的功能开关键表）: %s",
            len(unknown),
            "、".join(sorted(unknown)),
        )

    if not valid_count:
        return
    # 只有确实改变了取值才报 INFO：本模块在导入时自动加载一次，调用方（如 CLI
    # 早返回命令的应用开关入口）可能再显式加载一次，重复打印同一条日志是噪声。
    if changed:
        logger.info("[features] 已加载 %d 项功能开关覆写", valid_count)
    else:
        logger.debug("[features] 覆写已生效（%d 项，取值无变化）", valid_count)


def save_feature_overrides(overrides: dict[str, bool], merge: bool = True) -> None:
    """保存功能开关覆写到 features.json。

    Args:
        overrides: {flag_name: enabled} 字典
        merge: True = 合并到现有覆写（覆盖同名键），False = 完全替换
    """
    existing: dict[str, Any] = {}
    if merge and os.path.exists(_FEATURES_FILE):
        try:
            with open(_FEATURES_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing.update(overrides)

    # 只保留值为 bool 的条目
    cleaned = {k: v for k, v in existing.items() if isinstance(v, bool)}

    # 落盘委托 core/atomic_write（唯一原语，mkstemp + os.replace）。失败由原语记日志
    # 并返回 False——开关覆写属尽力持久化：写不进盘不影响本次运行（内存态随后同步），
    # 也不应因此中断调用链。
    if write_json_atomic(
        _FEATURES_FILE,
        cleaned,
        prefix=".features_",
        log_tag="features",
        noun="功能开关覆写",
    ):
        logger.info("[features] 已保存 %d 项功能开关覆写", len(cleaned))

    # 同步运行时状态
    for flag_name, enabled in cleaned.items():
        FEATURE_FLAGS[flag_name] = enabled


def reset_feature_flags() -> None:
    """重置所有功能开关为默认值（运行时状态，不影响持久化文件）。"""
    with _FEATURES_LOCK:
        FEATURE_FLAGS.clear()
        FEATURE_FLAGS.update(_FEATURE_FLAGS_DEFAULT)
    logger.debug("[features] 功能开关已重置为默认值")


# 模块导入时自动加载覆写
load_feature_overrides()
