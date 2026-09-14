"""数据源凭据声明与就绪指引 —— 「声明 → 就绪判定 → 可读指引」。

多数数据源免费（腾讯/新浪/东方财富/天天基金/华尔街见闻/财联社等）；
需凭据的源（如 DataSinking 全文本财报）在其 provider 模块导入时登记一条
``CredentialSpec``，把「此源需什么凭据」声明在源的定义旁，使调用方无需
发出请求即可判定是否就绪——

  - 链路（``fetcher/chain.py``）**主动跳过**未就绪的源并给出「你缺什么、去哪
    申请」，而不是把它当作「源不可达」反复重试、甚至计入熔断（配置级问题
    混入可用性统计会污染数据源可用性矩阵的语义）；
  - 健康检查（``core/check_sources.py``）与体检（``core/doctor.py``）直接报告
    就绪状态，用户不必等到某个报告段落缺数据才发现 key 没配。

措辞与判定习语对齐 ``doctor.py::_check_llm_credentials``（「错误即 UX」：
不只报错，还告诉用户怎么办），不另创一套文案范式。

安全纪律：**凭据值永不落日志、永不写入报告/缓存**——本模块只读环境变量与
声明的密钥文件，只对外报告「来源类型 + 是否就绪」。

凭据文件通用化：多个数据源的 key 共用一个 ``data/config/data_key.json``，
**以 provider（``source_id``）为节**（节内字段由 ``key_field`` 指定，默认
``api_key``）——文件内容自述「哪个 key 属于哪个数据源」：

    {
      "datasink": {"api_key": "ds_xxx"},
      "another_source": {"api_key": "yyy"}
    }

用法::

    from src.python.core.datasource_credential import (
        CredentialSpec, register_credential_spec, missing_credential, credential_hint,
    )
    register_credential_spec(CredentialSpec("example", "示例财经", "EXAMPLE_API_KEY"))
    spec = missing_credential("example")
    if spec is not None:
        logger.info("跳过：%s", credential_hint(spec))

需要密钥文件的源额外声明 ``key_file``（默认路径，可为相对路径）与
``key_field``（节内字段名，默认 ``api_key``）；节名默认取 ``source_id``，
可用 ``key_section`` 覆盖（便于一个数据源用多个 key 或节名与注册名不同）。
环境变量优先于密钥文件（便于 CI / 临时切换）。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

__all__ = [
    "CREDENTIAL_SPECS",
    "CredentialSpec",
    "credential_hint",
    "credential_readiness",
    "credential_ready_enabled",
    "credential_value",
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
    #: 承载凭据的本地密钥文件路径（可空；相对路径按 PROJECT_ROOT 解析）。
    #: 多个源共用 ``data/config/data_key.json``；环境变量优先于本文件。
    key_file: str = ""
    #: 密钥文件内的字段名（默认 ``api_key``）。
    key_field: str = "api_key"
    #: 密钥文件内的节名（默认取 ``source_id``）——文件以 provider 为节，
    #: 自述「哪个 key 属于哪个数据源」。
    key_section: str = ""
    #: 可选的配置键名，用于覆盖 ``key_file``（配置层路径型键，运行时为绝对路径）。
    key_file_setting: str = ""


# 声明即数据：由各源模块导入即注册（如 providers/datasink.py 的 DataSinking 财报）；
# 未声明的源视为免凭据，与 ``source_adapter.ADAPTER_REGISTRY`` 同习语。
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


def _key_file_path(spec: CredentialSpec) -> str:
    """解析声明的密钥文件路径（配置覆盖优先；相对路径按项目根目录解析）。"""
    path = spec.key_file
    if spec.key_file_setting:
        try:
            from src.python.config import get_config

            override = get_config().get(spec.key_file_setting)
            if isinstance(override, str) and override.strip():
                path = override
        except Exception:  # 配置不可用时回退声明路径，就绪判定不应因配置层异常而崩溃
            logger.debug("[credential] 读取 %s 配置失败，回退声明路径", spec.key_file_setting)
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)


def _read_key_file(path: str, field: str, section: str = "") -> str:
    """从 JSON 密钥文件读取字段值（文件缺失/不可解析/字段空白时返回空串）。

    通用结构以 provider 为节（``{"datasink": {"api_key": "..."}}``）：
    给了 ``section`` 且该节为对象时取节内字段；否则回退到顶层平铺字段
    （兼容单源文件 ``{"api_key": "..."}``）。
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    section_data = data.get(section) if section else None
    value = section_data.get(field) if isinstance(section_data, dict) else data.get(field)
    return value.strip() if isinstance(value, str) and not _is_blank(value) else ""


def resolve_credential(spec: CredentialSpec) -> tuple[str, str]:
    """解析凭据值与来源——返回 ``(值, 来源)``，来源为「环境变量」/「密钥文件」/空串。

    解析顺序：环境变量优先（便于 CI / 临时切换），否则读声明的密钥文件。
    **值仅供取数使用**，调用方不得写入日志/报告/缓存。
    """
    env_val = os.environ.get(spec.env_var)
    if not _is_blank(env_val):
        return env_val.strip(), "环境变量"
    path = _key_file_path(spec)
    if path:
        value = _read_key_file(path, spec.key_field, spec.key_section or spec.source_id)
        if value:
            return value, "密钥文件"
    return "", ""


def credential_value(source_id: str) -> str:
    """返回指定源的凭据值（供取数使用）；未声明或缺失时为空串。

    **安全纪律**：调用方不得把返回值写入日志、报告或缓存。
    """
    spec = CREDENTIAL_SPECS.get(source_id)
    if spec is None:
        return ""
    return resolve_credential(spec)[0]


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
    if resolve_credential(spec)[0]:
        return None
    return spec


def credential_hint(spec: CredentialSpec) -> str:
    """缺失凭据的可读指引（含数据源名、密钥文件/变量名与申请地址）。"""
    parts = [f"缺少凭据（数据源：{spec.display_name}）"]
    if spec.key_file:
        path = _key_file_path(spec) or spec.key_file
        parts.append(f"请填写密钥文件 {path} 的 {spec.key_field} 字段")
    parts.append(f"或设置环境变量 {spec.env_var}")
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
        value, source = resolve_credential(spec)
        ready = bool(value)
        rows.append(
            {
                "source_id": source_id,
                "display_name": spec.display_name,
                "required": True,
                "ready": ready,
                "env_var": spec.env_var,
                "key_file": _key_file_path(spec),
                "source": source,
                "message": f"已就绪（来源：{source}）" if ready else credential_hint(spec),
            }
        )
    return rows
