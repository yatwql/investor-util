"""数据源凭据声明与就绪指引 —— 「声明 → 就绪判定 → 可读指引」。

本项目当前的数据源**全部免费、无需凭据**（腾讯/新浪/东方财富/天天基金/
华尔街见闻/财联社），故 ``CREDENTIAL_SPECS`` 声明表为空。机制的价值不在当下
而在接入任何**需要 key 的源**时：把「此源需什么凭据」声明在源的定义旁，
使调用方无需发出请求即可判定是否就绪——

  - 链路（``fetcher/chain.py``）**主动跳过**未就绪的源并给出「你缺什么、去哪
    申请」，而不是把它当作「源不可达」反复重试、甚至计入熔断（配置级问题
    混入可用性统计会污染数据源可用性矩阵的语义）；
  - 健康检查（``core/check_sources.py``）与体检（``core/doctor.py``）直接报告
    就绪状态，用户不必等到某个报告段落缺数据才发现 key 没配。

措辞与判定习语对齐 ``doctor.py::_check_llm_credentials``（「错误即 UX」：
不只报错，还告诉用户怎么办），不另创一套文案范式。

安全纪律：**凭据值永不落日志、永不写入报告/缓存**——本模块只读环境变量、
只对外报告「变量名 + 是否就绪」。

用法::

    from src.python.core.datasource_credential import (
        CredentialSpec, register_credential_spec, missing_credential, credential_hint,
    )
    register_credential_spec(CredentialSpec("example", "示例财经", "EXAMPLE_API_KEY"))
    spec = missing_credential("example")
    if spec is not None:
        logger.info("跳过：%s", credential_hint(spec))
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = [
    "CREDENTIAL_SPECS",
    "CredentialSpec",
    "credential_hint",
    "credential_readiness",
    "credential_ready_enabled",
    "missing_credential",
    "register_credential_spec",
    "reset_credential_specs",
]

# 实验开关名：本模块的全部判定受它约束，开关名只此一处出现
_FEATURE_FLAG = "datasource_credential_ready"


@dataclass(frozen=True)
class CredentialSpec:
    """一个数据源的凭据声明。

    Attributes:
        source_id: 数据源标识，与 ``fetcher/chain.py`` 的 provider 名 /
            ``core/provider_registry.py`` 登记名一致（如 ``tencent``）
        display_name: 用户可见的数据源名（如「腾讯财经」）
        env_var: 承载凭据的环境变量名
        apply_url: 申请地址（可空）
        note: 备注（可空，如免费额度说明）
    """

    source_id: str
    display_name: str
    env_var: str
    apply_url: str = ""
    note: str = ""


# 声明即数据：当前为空（全部免费源）。接入需 key 的源时在源模块内导入即注册，
# 与 ``source_adapter.ADAPTER_REGISTRY`` 同习语。
CREDENTIAL_SPECS: dict[str, CredentialSpec] = {}


def register_credential_spec(spec: CredentialSpec) -> None:
    """登记一条凭据声明（同 source_id 重复登记以最后一次为准）。"""
    CREDENTIAL_SPECS[spec.source_id] = spec


def reset_credential_specs() -> None:
    """清空声明表（测试隔离用；生产代码不得调用）。"""
    CREDENTIAL_SPECS.clear()


def credential_ready_enabled() -> bool:
    """本机制是否启用（常规开关 ``datasource_credential_ready``，默认开启）。

    开关名收敛在此处——各调用点用本函数判定，不各自硬编码开关字符串；
    开关关闭时全部调用点的行为与未引入本机制时逐字一致。
    """
    from src.python.config.features import is_feature_enabled

    return is_feature_enabled(_FEATURE_FLAG)


def _is_blank(value: str | None) -> bool:
    """空白串视为缺失 —— 防止「设了空值以为配好了」。"""
    return not (value or "").strip()


def missing_credential(source_id: str) -> CredentialSpec | None:
    """该源是否「已声明需凭据但当前缺失」。

    Args:
        source_id: 数据源标识

    Returns:
        缺失时返回其 ``CredentialSpec``；源**未声明**凭据需求时返回 ``None``
        （即无需凭据，调用方照常尝试）。空白的环境变量视为缺失。
    """
    spec = CREDENTIAL_SPECS.get(source_id)
    if spec is None:
        return None
    if _is_blank(os.environ.get(spec.env_var)):
        return spec
    return None


def credential_hint(spec: CredentialSpec) -> str:
    """缺失凭据的可读指引（含数据源名、变量名与申请地址）。"""
    parts = [f"缺少凭据（数据源：{spec.display_name}）——请设置环境变量 {spec.env_var}"]
    if spec.apply_url:
        parts.append(f"申请地址：{spec.apply_url}")
    if spec.note:
        parts.append(spec.note)
    return "；".join(parts)


def credential_readiness() -> list[dict]:
    """全部已声明数据源的就绪矩阵（供体检与健康检查复用）。

    Returns:
        每项 ``{source_id, display_name, required, ready, env_var, message}``，
        按 ``source_id`` 排序保证输出稳定。**不抛异常**——只有环境变量读取与
        数据类字段拼装，异常路径不存在（调用方仍可将其视作纯数据）。

    只报告「变量名 + 是否就绪」，**不含凭据值**。
    """
    rows: list[dict] = []
    for source_id in sorted(CREDENTIAL_SPECS):
        spec = CREDENTIAL_SPECS[source_id]
        ready = not _is_blank(os.environ.get(spec.env_var))
        rows.append(
            {
                "source_id": source_id,
                "display_name": spec.display_name,
                "required": True,
                "ready": ready,
                "env_var": spec.env_var,
                "message": f"已就绪（环境变量 {spec.env_var} 已设置）" if ready else credential_hint(spec),
            }
        )
    return rows
