"""系统自检 —— 一次性把「跑不起来」的常见根因列出来。

与 ``check-sources`` 的分工：``check-sources`` 只测外部数据源联通性；
``doctor`` 还覆盖运行环境（解释器/虚拟环境）、配置（可解析、关键字段齐全、
LLM 凭据就位）、目录（持仓/缓存/输出可读写），最后复用 ``check-sources``
的网络检查（可用 ``include_network=False`` 关闭，便于离线/测试场景）。

设计原则：**自检自身永不抛异常**。任一项失败都必须转成该行结果，
否则「配置坏了」时用户看到的是 traceback，而这正是最需要诊断输出的场景。
因此本模块刻意不 import pandas / reader 等重依赖——它们恰好可能是坏掉的那一环。

用法::

    from src.python.core.doctor import run_doctor_checks
    for item in run_doctor_checks():
        print(item["group"], item["label"], item["ok"], item["message"])
"""

from __future__ import annotations

import os
import sys
from typing import Any

from src.python.core.constants import APP_NAME, APP_VERSION, PROJECT_ROOT

# 自检分组顺序（渲染时按此顺序输出，便于稳定对比两次自检结果）
GROUP_ENV = "环境"
GROUP_CONFIG = "配置"
GROUP_DIRS = "目录"
GROUP_FEATURES = "功能开关"
GROUP_NETWORK = "数据源"

GROUP_ORDER = [GROUP_ENV, GROUP_CONFIG, GROUP_DIRS, GROUP_FEATURES, GROUP_NETWORK]

# 支持的最低 Python 版本（项目依赖的语法特性下限）
MIN_PYTHON = (3, 10)

# 探测目录可写性时写入的哨兵文件名（写完立即删除，不留残留）
_WRITE_PROBE = ".doctor_write_probe"


def _item(group: str, label: str, ok: bool, message: str, *, hint: str = "") -> dict[str, Any]:
    """构造一条自检结果。

    Args:
        hint: 可选的可执行修复建议（「错误即 UX」——不只报错，还告诉用户怎么办）
    """
    return {"group": group, "label": label, "ok": ok, "message": message, "hint": hint}


def _check_python_version() -> dict[str, Any]:
    current = sys.version_info
    version = f"{current.major}.{current.minor}.{current.micro}"
    required = ".".join(str(n) for n in MIN_PYTHON)
    if current[:2] >= MIN_PYTHON:
        return _item(GROUP_ENV, "Python 版本", True, f"{version}（要求 ≥ {required}）")
    return _item(
        GROUP_ENV,
        "Python 版本",
        False,
        f"{version} 低于要求的 {required}",
        hint="升级 Python 后重建虚拟环境",
    )


def _check_venv() -> dict[str, Any]:
    """检查是否运行在项目虚拟环境中。

    裸解释器（系统 Python）通常缺 pandas 等依赖，表现为启动即报
    ``No module named 'pandas'``——提前判定可省去一轮排查。
    """
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        return _item(GROUP_ENV, "虚拟环境", True, sys.prefix)
    return _item(
        GROUP_ENV,
        "虚拟环境",
        False,
        "当前为系统解释器，可能缺少项目依赖",
        hint="改用 .venv/bin/python（Windows 为 .venv\\Scripts\\python.exe）",
    )


def _check_project_root() -> dict[str, Any]:
    marker = os.path.join(PROJECT_ROOT, "pyproject.toml")
    if os.path.isfile(marker):
        return _item(GROUP_ENV, "项目根目录", True, PROJECT_ROOT)
    return _item(GROUP_ENV, "项目根目录", False, f"{PROJECT_ROOT}（未找到 pyproject.toml）")


def _check_config() -> list[dict[str, Any]]:
    """检查配置可加载、关键路径字段齐全、LLM 凭据已配置。

    配置加载失败不抛异常——转为一条失败项，其余检查继续。
    """
    try:
        from src.python.config import get_config, init_config

        init_config()
        config = get_config()
    except Exception as exc:  # noqa: BLE001 —— 自检必须吞掉一切异常
        return [
            _item(
                GROUP_CONFIG,
                "配置加载",
                False,
                f"{type(exc).__name__}: {exc}",
                hint="检查 data/config/config.json 是否为合法 JSON，或删除后重新生成",
            )
        ]

    results = [_item(GROUP_CONFIG, "配置加载", True, "config.json 解析正常")]

    missing = [key for key in ("holdings_dir", "output_dir") if not config.get(key)]
    if missing:
        results.append(
            _item(
                GROUP_CONFIG,
                "关键路径字段",
                False,
                f"缺少: {'、'.join(missing)}",
                hint="删除 data/config/config.json 后重新运行以生成默认配置",
            )
        )
    else:
        results.append(_item(GROUP_CONFIG, "关键路径字段", True, "holdings_dir / output_dir 均已配置"))

    results.extend(_check_llm_credentials())
    return results


def _check_llm_credentials() -> list[dict[str, Any]]:
    """检查 LLM provider 与凭据是否就位（缺失只影响 LLM 模块，不阻断报告）。"""
    try:
        from src.python.config import get_llm_config

        llm_config = get_llm_config()
    except Exception as exc:  # noqa: BLE001
        return [_item(GROUP_CONFIG, "LLM 凭据", False, f"读取失败: {type(exc).__name__}: {exc}")]

    if not llm_config:
        return [
            _item(
                GROUP_CONFIG,
                "LLM 凭据",
                False,
                "未配置（LLM 相关模块将跳过）",
                hint="在 TUI 菜单或 Web 配置面板中填写 API Key",
            )
        ]

    # 多链模式：凭据分散在各 provider 的 credentials_ref，无顶层 api_key
    provider_list = llm_config.get("_provider_list") or []
    if provider_list:
        names = "、".join(str(e.get("name", "?")) for e in provider_list)
        strategy = llm_config.get("_strategy", "priority")
        return [_item(GROUP_CONFIG, "LLM 凭据", True, f"多链模式（策略 {strategy}）：{names}")]

    provider = llm_config.get("provider", "?")
    if llm_config.get("api_key"):
        return [_item(GROUP_CONFIG, "LLM 凭据", True, f"provider={provider}，API Key 已配置")]
    return [
        _item(
            GROUP_CONFIG,
            "LLM 凭据",
            False,
            f"provider={provider}，API Key 为空",
            hint="在 TUI 菜单或 Web 配置面板中填写 API Key",
        )
    ]


def _check_writable(directory: str) -> tuple[bool, str]:
    """探测目录可写性（写哨兵文件后立即删除）。"""
    if not os.path.isdir(directory):
        return False, "目录不存在"
    probe = os.path.join(directory, _WRITE_PROBE)
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True, "可读写"
    except OSError as exc:
        return False, f"不可写: {exc.strerror or exc}"


def _check_directories() -> list[dict[str, Any]]:
    """检查持仓/输出目录与项目关键目录。"""
    results: list[dict[str, Any]] = []

    try:
        from src.python.config import get_config

        config = get_config()
    except Exception:  # noqa: BLE001 —— 配置已在上一条报错，此处静默跳过
        return results

    holdings_dir = config.get("holdings_dir") or ""
    if not holdings_dir:
        results.append(_item(GROUP_DIRS, "持仓目录", False, "未配置 holdings_dir"))
    elif not os.path.isdir(holdings_dir):
        results.append(
            _item(GROUP_DIRS, "持仓目录", False, f"{holdings_dir} 不存在", hint="创建该目录并放入持仓 Excel")
        )
    else:
        try:
            files = [f for f in os.listdir(holdings_dir) if f.lower().endswith(".xlsx") and not f.startswith("~$")]
        except OSError as exc:
            files = []
            results.append(_item(GROUP_DIRS, "持仓目录", False, f"读取失败: {exc.strerror or exc}"))
        else:
            if files:
                results.append(_item(GROUP_DIRS, "持仓文件", True, f"{len(files)} 个 .xlsx"))
            else:
                results.append(
                    _item(
                        GROUP_DIRS,
                        "持仓文件",
                        False,
                        "目录内无 .xlsx 文件",
                        hint="将持仓 Excel 放入该目录（每 worksheet = 一个账户）",
                    )
                )

    output_dir = config.get("output_dir") or ""
    if output_dir:
        ok, message = _check_writable(output_dir)
        results.append(_item(GROUP_DIRS, "输出目录", ok, f"{output_dir} — {message}"))

    cache_dir = os.path.join(PROJECT_ROOT, "data", "cache")
    ok, message = _check_writable(cache_dir)
    results.append(_item(GROUP_DIRS, "缓存目录", ok, f"{cache_dir} — {message}"))

    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    ok, message = _check_writable(logs_dir)
    results.append(_item(GROUP_DIRS, "日志目录", ok, f"{logs_dir} — {message}"))

    return results


def _check_experimental_features() -> list[dict[str, Any]]:
    """列出当前启用的实验功能（信息性，不影响自检结论）。

    这些功能未经充分验证，是排查「行为与预期不符」时的第一嫌疑对象，
    故主动上屏而非等用户去翻日志。
    """
    try:
        from src.python.config.features import EXPERIMENTAL_FEATURES, is_feature_enabled

        enabled = [(name, desc) for flag, (name, desc) in EXPERIMENTAL_FEATURES.items() if is_feature_enabled(flag)]
    except Exception as exc:  # noqa: BLE001
        return [_item(GROUP_FEATURES, "实验功能", False, f"读取失败: {type(exc).__name__}: {exc}")]

    if not enabled:
        return [_item(GROUP_FEATURES, "实验功能", True, "未启用任何实验功能")]
    detail = "；".join(f"{name}（{desc}）" for name, desc in enabled)
    return [_item(GROUP_FEATURES, "实验功能", True, f"已启用 {len(enabled)} 项 — {detail}")]


def _check_network(max_timeout: float) -> list[dict[str, Any]]:
    """复用数据源健康检查（网络不可用时不应让整次自检失败，故结果照实上报）。"""
    try:
        from src.python.core.check_sources import run_health_checks

        raw = run_health_checks(max_timeout=max_timeout)
    except Exception as exc:  # noqa: BLE001
        return [_item(GROUP_NETWORK, "数据源检查", False, f"执行失败: {type(exc).__name__}: {exc}")]

    results: list[dict[str, Any]] = []
    for r in raw:
        results.append(
            _item(
                GROUP_NETWORK,
                r.get("label") or r.get("name", "未知数据源"),
                bool(r.get("ok")),
                r.get("message", ""),
                hint=r.get("message", "") if r.get("hint") else "",
            )
        )
    return results


def run_doctor_checks(*, include_network: bool = True, max_timeout: float = 8.0) -> list[dict[str, Any]]:
    """执行系统自检，返回结构化结果列表。

    Args:
        include_network: 是否包含数据源网络检查。Web/TUI 快速自检可传 False
            以即时返回；命令行 ``doctor`` 默认 True。
        max_timeout: 网络检查的整体耗时预算（秒），透传给 ``run_health_checks``。

    Returns:
        列表，每项含 ``group`` / ``label`` / ``ok`` / ``message`` / ``hint``。
        按 ``GROUP_ORDER`` 分组顺序排列，组内保持检查定义顺序。

    本函数不抛异常：任何单项故障都转为该行的失败结果。
    """
    results: list[dict[str, Any]] = []
    results.append(_check_python_version())
    results.append(_check_venv())
    results.append(_check_project_root())
    results.extend(_check_config())
    results.extend(_check_directories())
    results.extend(_check_experimental_features())
    if include_network:
        results.extend(_check_network(max_timeout))

    order = {group: i for i, group in enumerate(GROUP_ORDER)}
    return sorted(results, key=lambda r: order.get(r["group"], len(order)))


def summarize_doctor_results(results: list[dict[str, Any]]) -> tuple[int, int]:
    """统计自检结果 ``(通过数, 失败数)``。"""
    ok_count = sum(1 for r in results if r.get("ok"))
    return ok_count, len(results) - ok_count


def format_doctor_report(results: list[dict[str, Any]], *, use_color: bool = False) -> str:
    """把自检结果渲染成可读文本（CLI 与 TUI 共用）。

    失败项附 ``hint`` 修复建议——自检的价值一半在「告诉用户下一步做什么」。
    """
    ok_count, bad_count = summarize_doctor_results(results)
    lines = [
        f"{APP_NAME} 系统自检 (v{APP_VERSION})",
        "实验功能（doctor_check）：只读诊断，结论仅供参考",
        "─" * 55,
    ]
    ok_mark = "\033[32m[OK]\033[0m" if use_color else "[OK]"
    bad_mark = "\033[31m[ERR]\033[0m" if use_color else "[ERR]"

    current_group = None
    for item in results:
        if item["group"] != current_group:
            current_group = item["group"]
            lines.append(f"\n[{current_group}]")
        mark = ok_mark if item["ok"] else bad_mark
        lines.append(f"  {mark} {item['label']} — {item['message']}")
        if not item["ok"] and item.get("hint"):
            lines.append(f"        → {item['hint']}")

    lines.append("─" * 55)
    lines.append(f"  共 {len(results)} 项 — [OK] {ok_count} / [ERR] {bad_count}")
    return "\n".join(lines)
