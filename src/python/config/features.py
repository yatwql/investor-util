"""功能开关注册表 — Feature Flag 体系。

提供集中管理功能开关的能力，替代分散在各模块中的条件判断。
所有开关在注册表中统一声明默认值，支持运行时启用/禁用。

用法：
  >>> from src.python.config.features import is_feature_enabled, FEATURE_FLAGS
  >>> if is_feature_enabled("enable_interactive_charts"):
  ...     embed_chart_assets()

配置持久化：功能开关可通过 features.json 覆写默认值。
模块级 LLM 分析章节、新闻源、报告章节等**不在此登记**——它们各有归属文件，
见 ``_FEATURE_FLAGS_DEFAULT`` 上方说明。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from src.python.core.atomic_write import write_json_atomic
from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 路径常量 ────────────────────────────────────────────────

_FEATURES_FILE = os.path.join(PROJECT_ROOT, "data/config/features.json")

# ── 全部功能开关默认值 ──────────────────────────────────────
# 格式：{flag_name: default_enabled}
# False = 功能默认关闭，需要用户手动启用
# True  = 功能默认开启，可在 features.json 中关闭
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

_FEATURE_FLAGS_DEFAULT: dict[str, bool] = {
    # ── 辩论模式（实验功能，默认关闭） ──
    "llm_debate_procon": False,
    "llm_debate_conditional": False,
    "llm_debate_qa_concentration": False,
    # ── 量化指标（7 项） ──
    "metrics_sharpe": True,
    "metrics_calmar": True,
    "metrics_hhi": True,
    "metrics_winrate": True,
    "metrics_turnover": True,
    "metrics_risk_contribution": True,
    "metrics_beta": True,
    # ── 功能特性（1 项） ──
    "enable_interactive_charts": True,
    # ── 决策跨期反思闭环（实验功能，默认关闭） ──
    "decision_reflection": False,
    # ── 信号预消化（实验功能，默认关闭） ──
    "signal_pre_digest": False,
    # ── 模块级质量分级（实验功能，默认关闭） ──
    "module_quality_gate": False,
    # ── 决策头结构化（实验功能，默认关闭） ──
    "decision_header_parse": False,
    # ── 确定性数值信号沉淀（实验功能，默认关闭） ──
    "signal_ledger": False,
    # ── 系统自检（默认开启） ──
    # 只读诊断，不写任何产物、不改报告任何字节，联网检查每次显式确认（TUI 询问、
    # Web 按钮触发）。失败的默认值会让最需要它的人（环境坏掉的那批）恰好看不到
    # 它，故默认开；可在 features.json 中置 false 关闭，TUI [D] 与 Web 卡片随之隐藏。
    "doctor_check": True,
    # ── 数据源适配契约（默认开启） ──
    # 内部接缝：开关开/关下报告产物逐源等价（唯一差异是东财源多出 market_cap/pe
    # 两个 None 键，下游一律 .get() 读取、语义不变，见 test_quote_adapter_parity.py），
    # 故它对用户没有可感知收益，不该以默认关的形态占一个用户开关；而默认关的实际
    # 代价是生产路径从不执行适配器分支，新数据源/新字段的契约得不到实跑覆盖。
    # 开关保留为回退杠杆：features.json / 面板置 false 即走既有转换函数。
    "datasource_adapter": True,
    # ── 数据源凭据就绪指引（实验功能，默认关闭） ──
    "datasource_credential_ready": False,
}

# ── 实验性功能定义 ──────────────────────────────────────────
# 格式: {flag_name: ("显示名", "说明", affects_report)}
# 此处列出的功能默认关闭，用户在 features.json 中手动开启后，报告入口
# （``report/orchestrator.generate_report``）会在日志中以红色高亮提示已启用项。
# 本注册表同时是 TUI 菜单 [S] 试验功能面板与 Web 配置面板的渲染来源（渠道层
# 不得另写清单）；CLI 侧经 ``--experiment <名|all>`` 增量启用（仅当前进程、
# 不写盘，只开不关——关闭仍走 features.json / 面板）。
#
# 第三个字段是**准入自述的口径**：开启该功能后报告产物的内容是否可能不同。
#   True  —— 进入报告自述（HTML 页脚 / Excel 落点）与控制台横幅，读者据此判断
#            手上这份产物是否非默认开关下的结果。
#   False —— 只改交互入口可见性的开关（如面板/菜单项显隐）不得进入产物自述：
#            自述里列出一个不改报告任何字节的开关，读者会推断内容受其影响，
#            而事实上零影响。新增实验项时必须回答这个问题——答 False 者不进自述。
# 现状：以下各项均可能改变产物内容，故无 False 成员；该字段的作用是拦住下一个
# 「只影响入口」的实验项，使其不能凭惯性落进产物自述。
EXPERIMENTAL_FEATURES: dict[str, tuple[str, str, bool]] = {
    "llm_debate_procon": ("辩论-正反辩论", "三段式(白脸→黑脸→综合)", True),
    "llm_debate_conditional": ("辩论-条件推理", "情景化分析(涨/跌/震荡)", True),
    "llm_debate_qa_concentration": ("辩论-集中度问答", "集中度风险问答", True),
    "decision_reflection": (
        "决策跨期反思闭环",
        "登记决策 → 真实行情结算命中率 → 教训回灌专家复盘提示词",
        True,
    ),
    "signal_pre_digest": (
        "信号预消化",
        "市场温度/估值分位/尾部风险预消化为带方向标注的信号行注入复盘与体检提示词",
        True,
    ),
    "module_quality_gate": (
        "模块级质量分级",
        "按完整性/一致性给各 LLM 模块输出评 A~F 级，低评级随内容头部标注质量提示（不阻断不重试）",
        True,
    ),
    "decision_header_parse": (
        "决策头结构化",
        "提示词追加受控 JSON 决策头，抽取优先读结构化、失败回落确定性表格解析（决策词归一，防写反方向）",
        True,
    ),
    "signal_ledger": (
        "确定性信号沉淀",
        "确定性算法评级（温度/估值/尾部风险/风格/再平衡超限）沉淀为带实时-非实时标签的账本，统计默认只算实时",
        True,
    ),
    "datasource_credential_ready": (
        "数据源凭据就绪",
        "声明数据源所需凭据，缺失时链路跳过并给出可读指引；体检与健康检查报告就绪状态（当前全部数据源免费无需凭据）",
        True,
    ),
}

# ── 实验功能名解析 ──────────────────────────────────────────
# 「可开启的实验功能清单」唯一来源是 EXPERIMENTAL_FEATURES 注册表：
# TUI 菜单 S / Web 配置面板直接遍历注册表渲染，命令行入口经下方解析函数
# 校验取值，三者同源，新增实验开关无需改动任何入口代码。

EXPERIMENT_ALL = "all"


def _match_experiment(token: str) -> str | None:
    """按开关名（大小写不敏感）或显示名（精确）匹配单个实验功能。

    Returns:
        命中的开关名，未匹配到返回 None
    """
    lowered = token.lower()
    for flag, (display_name, _desc, _affects_report) in EXPERIMENTAL_FEATURES.items():
        if flag.lower() == lowered or display_name == token:
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
            resolved.update(EXPERIMENTAL_FEATURES)
            continue
        hit = _match_experiment(token)
        if hit is None:
            unknown.append(raw)
        else:
            resolved.add(hit)
    return resolved, unknown


def describe_experiment_flags() -> str:
    """返回实验功能清单的人类可读串（供 CLI 帮助与报错提示复用）。"""
    return "、".join(f"{flag}（{name}）" for flag, (name, _desc, _a) in EXPERIMENTAL_FEATURES.items())


def enabled_experimental_features() -> list[tuple[str, str]]:
    """返回当前已启用、且**可能改变报告产物**的实验功能 ``[(开关名, 显示名), ...]``。

    报告层用它在**产物自身上**标注生成条件（HTML 页脚 / Excel 落点）——报告是
    可脱离本机流转的文件，读者须能判断内容是否为非默认开关下的产物。

    只列注册表中 ``affects_report`` 为真者：只改交互入口可见性的开关不改报告
    任何字节，列进自述会让读者推断内容受其影响。清单取自
    :data:`EXPERIMENTAL_FEATURES`，注册表仍是唯一来源；TUI 试验功能面板与 Web
    配置面板渲染的是**整张注册表**（含不影响产物者），两者用途不同。

    Returns:
        已启用项的 ``(开关名, 显示名)`` 列表，按注册表顺序；无启用项时返回空列表。
    """
    return [
        (flag, name)
        for flag, (name, _desc, affects_report) in EXPERIMENTAL_FEATURES.items()
        if affects_report and is_feature_enabled(flag)
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
        logger.error("  ⚗ %s — %s", name, EXPERIMENTAL_FEATURES[flag][1])
    logger.error(sep)


__all__ = [
    "EXPERIMENTAL_FEATURES",
    "EXPERIMENT_ALL",
    "FEATURE_FLAGS",
    "describe_experiment_flags",
    "enabled_experimental_features",
    "get_feature_defaults",
    "is_feature_enabled",
    "log_experimental_features",
    "resolve_experiment_flags",
    "set_feature_enabled",
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
