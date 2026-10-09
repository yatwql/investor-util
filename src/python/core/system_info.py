"""系统状态信息组装与展示原语 — Web 状态卡片 / TUI 首页摘要共用数据源。

- ``build_system_info()``：版本 / 机器 IP / 持仓与输出摘要 / 匿名化与隐私 /
  自检开关 / LLM 配置状态（flat 单 provider 与 credentials_ref 多链两种模式）。
  渠道层只做渲染，不自行组装状态数据。
- ``llm_status()``：LLM 配置状态单源（三渠道状态展示共用判定树，渠道不复刻分支）。
- 展示原语（``simplify_endpoint`` / ``circuit_display`` / ``strategy_label`` /
  ``priority_display`` / ``anon_mode_label`` / ``resolve_provider_credentials`` /
  ``model_route_labels``）：熔断规则、主机名简化、策略标签、凭据回填等
  曾在渠道各持一份的展示规则，收敛于此单点实现。

配置读取失败按默认值兜底，不阻断页面渲染。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("invest")


def simplify_endpoint(endpoint: str) -> str:
    """简化 endpoint 显示（取 URL 主机名），非 URL 原样返回。"""
    if not endpoint or endpoint == "默认":
        return endpoint or "默认"
    if "//" in endpoint:
        parts = endpoint.split("/")
        if len(parts) > 2:
            return parts[2]
    return endpoint


def circuit_display(endpoint: str, *, default_as_none: bool = False) -> str:
    """熔断状态展示规则（渠道无关的唯一判定）。

    Args:
        endpoint: provider endpoint。
        default_as_none: True 时字面 ``默认`` 视为无端点（flat 单 provider 模式）；
            多链模式（False）仅空端点视为无端点。

    Returns:
        熔断状态字符串；无端点返回 ``—``。
    """
    if not endpoint or (default_as_none and endpoint == "默认"):
        return "—"
    # 熔断文案判定经 core 网关注册获取（上游模块导入时注册），本模块不反向 import 上层
    from src.python.core.circuit_breaker import circuit_text

    return circuit_text(endpoint)


def strategy_label(strategy_raw: str) -> str:
    """多链策略原始值 → 中文展示标签。"""
    labels = {
        "priority": "优先级排序",
        "weighted": "加权随机",
        "cost_first": "价格最低优先",
        "fallback_only": "仅 Fallback",
    }
    return labels.get(strategy_raw, strategy_raw)


def priority_display(priority) -> str:
    """provider 优先级展示（缺失 → 默认档说明）。"""
    return str(priority) if priority is not None else "99（默认）"


def anon_mode_label(mode: str) -> str:
    """持仓匿名化模式 → 中文展示标签。"""
    labels = {"off": "关闭", "code_display": "代码显示", "full_anonymous": "完全匿名", "summary": "汇总"}
    return labels.get(mode, mode)


def resolve_provider_credentials(entry: dict, all_creds: dict) -> tuple[str, str]:
    """credentials_ref 回填：entry 缺失 model/endpoint 时查凭据表。

    Returns:
        (model, endpoint) 元组。
    """
    model = entry.get("model", "")
    endpoint = entry.get("endpoint") or ""
    creds_ref = entry.get("credentials_ref")
    if creds_ref and (not model or not endpoint):
        ref_creds = all_creds.get(creds_ref, {}) if isinstance(all_creds, dict) else {}
        if isinstance(ref_creds, dict):
            if not model:
                model = ref_creds.get("model", "")
            if not endpoint:
                endpoint = ref_creds.get("endpoint", "") or ""
    return model, endpoint


def model_route_labels(llm_config: dict) -> list[str]:
    """flat 模式模型路由行：``模块显示名=生效模型``（面板隐藏模块已剔除）。"""
    from src.python.core.registry import visible_llm_module_names

    model = llm_config.get("model") or "默认"
    return [f"{name}={llm_config.get(f'model_{sfx}') or model}" for sfx, name in visible_llm_module_names().items()]


def build_system_info() -> dict:
    """组装系统状态信息（版本 / IP / 持仓与输出摘要 / LLM 配置状态）。

    - 持仓目录 / 持仓文件 / 输出目录 / 新闻抓取上限 / 状态（文件是否就绪）；
    - 持仓匿名化模式（中文映射）/ 隐私声明是否已显示；
    - flat 单 provider：provider / model / endpoint（简化主机名）/ 熔断 / 模型路由；
    - credentials_ref 多链：策略 / 各 provider（名称/后端/模型/优先级/熔断）/ 模块偏好；
    - 未配置：configured=False（消费方按未配置展示）。

    Returns:
        dict，含 app_version / machine_ip / holdings 摘要字段 / llm（结构化状态）。
    """
    from src.python.config import get_config, get_default, get_local_flag, resolve_holdings_path
    from src.python.config.anonymizer import get_anonymization_mode
    from src.python.core.constants import APP_VERSION
    from src.python.core.logger import get_machine_ip

    info = {
        "app_version": APP_VERSION,
        "machine_ip": get_machine_ip(),
        "llm": {"configured": False},
    }

    # ── 持仓 / 输出 / 新闻 / 匿名化 / 隐私 ──
    config_readable = True
    try:
        config = get_config()
    except Exception:
        logger.warning("读取配置失败，系统信息按默认值展示", exc_info=True)
        config = {}
        # 配置读取失败时无法信任路径解析：摘要按默认展示，就绪按未就绪保守呈现
        config_readable = False
    if not isinstance(config, dict):
        config = {}
    holdings_dir = config.get("holdings_dir") or ""
    holdings_filename = config.get("holdings_filename") or ""
    info["holdings_dir"] = holdings_dir or "未设置"
    info["holdings_filename"] = holdings_filename or "未设置"
    info["output_dir"] = config.get("output_dir") or get_default("output_dir")
    info["news_top_count"] = config.get("news_top_count") or get_default("news_top_count")
    holdings_path = ""
    if config_readable:
        try:
            holdings_path = resolve_holdings_path(config)
        except Exception:
            holdings_path = ""
    holdings_ready = bool(holdings_path and os.path.exists(holdings_path))
    info["holdings_ready"] = holdings_ready
    # 正式文件 mtime（「读取当前正式持仓」提示用；未就绪为 None）
    info["holdings_mtime"] = os.path.getmtime(holdings_path) if holdings_ready else None
    try:
        anon_mode = get_anonymization_mode()
    except Exception:
        logger.warning("读取匿名化模式失败，按关闭展示", exc_info=True)
        anon_mode = "off"
    info["anonymization"] = anon_mode_label(anon_mode)
    info["privacy_shown"] = bool(get_local_flag("_privacy_notice_shown"))

    # 系统自检卡片可见性（doctor_check 开关，与 TUI 菜单 D 同一开关；默认开启）
    try:
        from src.python.config.features import is_feature_enabled

        info["doctor_enabled"] = is_feature_enabled("doctor_check")
    except Exception:
        logger.warning("读取功能开关失败，系统自检卡片按隐藏处理", exc_info=True)
        info["doctor_enabled"] = False

    info["llm"] = llm_status()
    return info


def llm_status() -> dict:
    """LLM 配置状态（三渠道状态展示共用的单一分支事实来源）。

    configured 判定 / 多链与 flat 分流 / credentials 凭据回填 / 优先级与熔断
    展示一律经本函数：TUI、CLI、Web 的 LLM 状态行消费同一份结果，渠道层
    只做传输渲染（print/logger/JSON），不得复刻判定树。

    Returns:
        dict：未配置 ``{"configured": False}``；多链含 ``mode="multi"`` /
        strategy / providers / preferred；flat 含 ``mode="flat"`` / provider /
        model / endpoint / endpoint_display / circuit / route。
    """
    from src.python.config import get_llm_config
    from src.python.core.registry import get_llm_module_names

    try:
        llm_config = get_llm_config()
    except Exception:
        logger.warning("读取 LLM 配置失败，按未配置展示", exc_info=True)
        llm_config = None
    if llm_config is None:
        return {"configured": False}

    provider_list = llm_config.get("_provider_list") or []

    # ── credentials_ref 多链模式 ──
    if provider_list and not llm_config.get("api_key"):
        all_creds = llm_config.get("_llm_credentials", {}) or {}
        providers = []
        for entry in provider_list:
            model, endpoint = resolve_provider_credentials(entry, all_creds)
            providers.append(
                {
                    "name": entry.get("name", "?"),
                    "backend": entry.get("provider", "?"),
                    "model": model or "默认",
                    "endpoint": endpoint,
                    "endpoint_display": simplify_endpoint(endpoint),
                    "priority": priority_display(entry.get("priority")),
                    "circuit": circuit_display(endpoint),
                }
            )
        preferred = [
            f"{get_llm_module_names().get(mk, mk)} → {pname}"
            for mk, pname in (llm_config.get("_preferred_providers", {}) or {}).items()
        ]
        return {
            "configured": True,
            "mode": "multi",
            "strategy": strategy_label(llm_config.get("_strategy", "priority")),
            "providers": providers,
            "preferred": preferred,
        }

    # ── 传统 flat 模式：单 provider ──
    if not llm_config.get("api_key") or not llm_config.get("provider"):
        return {"configured": False}

    model = llm_config.get("model") or "默认"
    endpoint = llm_config.get("endpoint") or "默认"
    return {
        "configured": True,
        "mode": "flat",
        "provider": llm_config["provider"],
        "model": model,
        "endpoint": endpoint,
        "endpoint_display": simplify_endpoint(endpoint),
        "circuit": circuit_display(endpoint, default_as_none=True),
        "route": model_route_labels(llm_config),
    }
