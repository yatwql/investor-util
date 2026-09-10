"""数据源适配契约 — 三段式「参数转译 → 抓取 → 映射到标准字段」。

一个数据源接入本项目需要做的三件事，在此被拆成三个可独立检验的小函数：

1. ``transform_query``：参数转译（补默认值、拼查询参数）；
2. ``extract_data``：抓取（返回上游原始响应，既有的源在此**委托给既有 provider
   函数**，不复制任何 HTTP 与解析逻辑）；
3. ``transform_data``：映射到标准字段（默认实现即声明式 alias 归一，见下）。

默认的 ``transform_data`` 由三样声明驱动，全部是数据而非代码：

- ``aliases``：``{上游字段名: 标准字段名}`` —— 字段改名的唯一表达处；
- ``defaults``：``{标准字段: 该源在上游未提供时的取值}``；
- 标准字段记录类（``schemas/datasource_fields.py``）的**类型注解** ——
  ``float`` 缺失取 0.0、``float | None`` 缺失取 ``None``（表示该源不提供此字段）、
  ``str`` 缺失取空串；数值一律经 ``core.num_utils.safe_num`` 归一（防 NaN/±inf 污染下游）。

输出恒为**全部标准字段**：同一域的不同源产出同键同构 dict，下游无需为
「某源少两个键」写分支。

适配器可直接充当 Provider Chain 的两槽（``fetch_raw`` 对应 provider 函数槽、
``transform_record`` 对应转换槽），因此链路顺序、缓存键、熔断、降级全部复用
``fetcher/chain.fetch_with_fallback``，不新造第二条获取路径。
"""

from __future__ import annotations

import logging
import types
import typing
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import fields as dataclass_fields
from typing import Any, ClassVar, get_type_hints

from src.python.core.num_utils import safe_num
from src.python.schemas.datasource_fields import DOMAIN_RECORDS

logger = logging.getLogger("invest")

# 上游未提供该字段的哨兵（区别于「上游明确给了 None」）
_MISSING = object()


# ═══════════════════════════════════════════════════════════════
#  字段类型驱动的归一
# ═══════════════════════════════════════════════════════════════


def _field_types(record_cls: type) -> tuple[tuple[str, Any], ...]:
    """返回记录类的 ``((字段名, 类型注解), ...)``（保持声明序）。"""
    hints = get_type_hints(record_cls)
    return tuple((f.name, hints.get(f.name)) for f in dataclass_fields(record_cls))


def _is_optional(ftype: Any) -> bool:
    """类型注解是否允许 None（``float | None`` / ``Optional[float]``）。"""
    if isinstance(ftype, types.UnionType):
        return type(None) in ftype.__args__
    if typing.get_origin(ftype) is typing.Union:
        return type(None) in typing.get_args(ftype)
    return False


def _is_numeric(ftype: Any) -> bool:
    """类型注解是否为数值（含可选数值）。"""
    if ftype in (float, int):
        return True
    args: tuple = ()
    if isinstance(ftype, types.UnionType):
        args = ftype.__args__
    elif typing.get_origin(ftype) is typing.Union:
        args = typing.get_args(ftype)
    return any(a in (float, int) for a in args)


def _normalize_value(value: Any, ftype: Any, fallback: Any = _MISSING) -> Any:
    """按字段类型把上游取值归一为契约值。

    上游**未提供**（``_MISSING``）或**提供了但不可用**（NaN/±inf/非数值串）时：
    优先取 ``fallback``（适配器声明的该源缺省值），未声明则按类型缺省——
    数值取 0.0（可选数值取 None）、文本取空串。

    注意「合法的 0.0」不会被缺省值覆盖：只有不可用的值才回落。
    """
    if _is_numeric(ftype):
        num = safe_num(value, default=None)
        if num is not None:
            return num
        if fallback is not _MISSING:
            return fallback
        return None if _is_optional(ftype) else 0.0
    if value is _MISSING or value is None:
        return "" if fallback is _MISSING else fallback
    return value if isinstance(value, str) else str(value)


def _sample_value(ftype: Any) -> Any:
    """自检合成样本的取值（数值取 1.0，文本取占位串）。"""
    return 1.0 if _is_numeric(ftype) else "sample"


# ═══════════════════════════════════════════════════════════════
#  适配器基类
# ═══════════════════════════════════════════════════════════════


class SourceAdapter(ABC):
    """数据源适配器基类 —— 声明三样数据 + 实现三段式。

    子类必须声明：``domain``（数据域）、``source_id``（与 provider 注册名一致）、
    ``display_name``（展示名，须与链路标签一致）、``extract_data``（抓取）。
    子类可按需声明：``aliases``、``defaults``。
    """

    domain: ClassVar[str] = ""
    source_id: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    #: 上游字段名 → 标准字段名（字段改名的唯一表达处）
    aliases: ClassVar[Mapping[str, str]] = {}
    #: 标准字段 → 该源在上游未提供时的取值（缺省按字段类型注解推导）
    defaults: ClassVar[Mapping[str, Any]] = {}
    #: 由适配器**强制提供**的标准字段（源身份信息）——上游同名取值不参与映射，
    #: 避免上游自报的 source（如东方财富回落到天天基金时自报「天天基金」）
    #: 覆盖链路标签，破坏「来源 = 实际生效链路」的可信语义
    identity_fields: ClassVar[tuple[str, ...]] = ("source_api", "source")

    # ── 标准字段契约（由数据域推导，不存在第二份手抄清单）──

    @classmethod
    def standard_record(cls) -> type | None:
        """本适配器所属数据域的标准字段记录类（域未登记返回 None）。"""
        return DOMAIN_RECORDS.get(cls.domain)

    @classmethod
    def standard_fields(cls) -> tuple[str, ...]:
        """本适配器的标准字段名（保持记录类声明序）。"""
        record = cls.standard_record()
        if record is None:
            return ()
        return tuple(name for name, _ in _field_types(record))

    @classmethod
    def _reverse_aliases(cls) -> dict[str, str]:
        """标准字段名 → 上游字段名（同一标准字段多个别名时取先声明者）。"""
        reverse: dict[str, str] = {}
        for upstream, standard in cls.aliases.items():
            reverse.setdefault(standard, upstream)
        return reverse

    # ── 三段式 ──

    def transform_query(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """参数转译：默认恒等，子类可补默认值/拼查询参数。"""
        return dict(params)

    @abstractmethod
    def extract_data(self, query: dict[str, Any]) -> Any:
        """抓取：返回上游原始响应（既有源在此委托既有 provider 函数）。"""

    def transform_data(self, raw: Any, source: str = "") -> dict[str, Any] | None:
        """映射到标准字段：默认实现为声明式 alias 归一。

        Args:
            raw: 上游原始响应
            source: 数据源展示名（链路标签），写入标准字段 ``source``

        Returns:
            全部标准字段构成的 dict；``raw`` 非映射（或子类判定为无有效数据）时 None
        """
        record = self.standard_record()
        if record is None or not isinstance(raw, Mapping):
            return None
        reverse = self._reverse_aliases()
        # 源身份字段恒由适配器提供；其余字段上游值优先（含 alias 后的键名），
        # 上游未提供或提供了不可用的值时由 defaults 兜底
        base: dict[str, Any] = {"source": source, "source_api": self.source_id, **self.defaults}
        out: dict[str, Any] = {}
        for name, ftype in _field_types(record):
            fallback = base.get(name, _MISSING)
            if name in self.identity_fields:
                out[name] = _normalize_value(fallback, ftype)
                continue
            value = raw.get(reverse.get(name, name), _MISSING)
            if value is _MISSING:
                value = raw.get(name, fallback)
            out[name] = _normalize_value(value, ftype, fallback)
        return out

    # ── Provider Chain 两槽适配 ──

    def fetch_raw(self, **kwargs: Any) -> Any:
        """链路抓取槽：``transform_query`` → ``extract_data``。"""
        return self.extract_data(self.transform_query(kwargs))

    def transform_record(self, raw: Any, source: str = "") -> dict[str, Any] | None:
        """链路转换槽：上游原始响应 → 标准字段 dict。"""
        return self.transform_data(raw, source)

    # ── 契约自检 ──

    def self_test(self) -> list[str]:
        """离线契约自检，返回问题描述列表（空 = 通过）。

        校验项：域与标识声明齐备、域已登记、alias/defaults 指向真实标准字段、
        ``transform_data`` 对合成样本输出**恰好**标准字段集（不多不少）。
        **不发起任何网络请求**，自身不抛异常（异常转为问题描述）。
        """
        problems: list[str] = []
        if not self.source_id:
            problems.append("未声明 source_id")
        if not self.display_name:
            problems.append("未声明 display_name")
        if not self.domain:
            problems.append("未声明 domain")
            return problems
        record = self.standard_record()
        if record is None:
            problems.append(f"数据域 {self.domain!r} 未在 DOMAIN_RECORDS 登记")
            return problems

        known = set(self.standard_fields())
        for upstream, standard in self.aliases.items():
            if standard not in known:
                problems.append(f"alias {upstream!r} → {standard!r} 不是标准字段")
        for name in self.defaults:
            if name not in known:
                problems.append(f"defaults 中的 {name!r} 不是标准字段")

        try:
            probe = self.transform_data(self._sample_raw(), self.display_name)
        except Exception as e:
            problems.append(f"transform_data 对合成样本抛异常：{type(e).__name__}: {e}")
            return problems
        if not isinstance(probe, dict):
            problems.append("transform_data 对合成样本未返回 dict")
            return problems
        extra = set(probe) - known
        missing = known - set(probe)
        if extra:
            problems.append(f"transform_data 输出含非标准字段：{sorted(extra)}")
        if missing:
            problems.append(f"transform_data 输出缺标准字段：{sorted(missing)}")
        return problems

    def _sample_raw(self) -> dict[str, Any]:
        """自检合成样本：按各标准字段的**上游键名**给出合法取值。"""
        record = self.standard_record()
        if record is None:
            return {}
        reverse = self._reverse_aliases()
        return {reverse.get(name, name): _sample_value(ftype) for name, ftype in _field_types(record)}


# ═══════════════════════════════════════════════════════════════
#  适配器注册表
# ═══════════════════════════════════════════════════════════════

#: 数据域 → 源 id → 适配器实例（由各适配器模块在导入时注册）
ADAPTER_REGISTRY: dict[str, dict[str, SourceAdapter]] = {}

#: 承载适配器实现的模块（新增数据域时在此追加一行；按需惰性导入，避免
#: 「为注册而 import」的隐式副作用依赖——调用方只与公开 API 打交道）
ADAPTER_MODULES: tuple[str, ...] = ("src.python.fetcher.quote_adapters",)

_ADAPTERS_LOADED = False


def _ensure_adapters_loaded() -> None:
    """惰性导入全部适配器模块，触发其注册。失败仅告警，不中断调用方。"""
    global _ADAPTERS_LOADED
    if _ADAPTERS_LOADED:
        return
    import importlib

    for module_name in ADAPTER_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as e:  # 单个适配器模块异常不得拖垮链路与体检
            logger.warning("[adapter] 适配器模块 %s 导入失败：%s", module_name, e, exc_info=True)
    _ADAPTERS_LOADED = True


def register_adapter(adapter: SourceAdapter) -> None:
    """登记一个适配器（同一 ``(域, 源 id)`` 重复登记时后注册者覆盖）。"""
    if not adapter.domain or not adapter.source_id:
        logger.warning("[adapter] 适配器 %s 缺少 domain/source_id，忽略登记", type(adapter).__name__)
        return
    ADAPTER_REGISTRY.setdefault(adapter.domain, {})[adapter.source_id] = adapter


def get_adapters(domain: str) -> dict[str, SourceAdapter]:
    """返回某数据域的适配器映射（域未登记返回空 dict，不抛异常）。"""
    _ensure_adapters_loaded()
    return dict(ADAPTER_REGISTRY.get(domain, {}))


def adapter_chain_slots(domain: str) -> tuple[dict[str, tuple[str, Callable]], dict[str, Callable]]:
    """把某数据域的适配器映射为链路两槽：``(provider_fn_map, transform_map)``。

    返回结构与 ``fetch_with_fallback`` 的两个入参一一对应，可直接替换既有
    手写 provider 映射与转换函数映射。
    """
    _ensure_adapters_loaded()
    adapters = ADAPTER_REGISTRY.get(domain, {})
    provider_map: dict[str, tuple[str, Callable]] = {
        source_id: (adapter.display_name, adapter.fetch_raw) for source_id, adapter in adapters.items()
    }
    transform_map: dict[str, Callable] = {
        source_id: adapter.transform_record for source_id, adapter in adapters.items()
    }
    return provider_map, transform_map


def survey_adapters() -> list[dict[str, Any]]:
    """全部已登记适配器的契约自检报告（离线、无副作用、自身不抛异常）。

    Returns:
        列表，每项含 ``domain`` / ``source_id`` / ``display_name`` / ``ok`` / ``message``
    """
    _ensure_adapters_loaded()
    reports: list[dict[str, Any]] = []
    for domain in sorted(ADAPTER_REGISTRY):
        for source_id, adapter in ADAPTER_REGISTRY[domain].items():
            try:
                problems = adapter.self_test()
            except Exception as e:  # 自检本身异常不得中断体检
                problems = [f"自检异常：{type(e).__name__}: {e}"]
            reports.append(
                {
                    "domain": domain,
                    "source_id": source_id,
                    "display_name": adapter.display_name,
                    "ok": not problems,
                    "message": "契约自检通过" if not problems else "；".join(problems),
                }
            )
    return reports


def snapshot_adapters() -> dict[str, dict[str, SourceAdapter]]:
    """快照当前注册表（测试隔离用，配合 :func:`restore_adapters`）。"""
    _ensure_adapters_loaded()
    return {domain: dict(adapters) for domain, adapters in ADAPTER_REGISTRY.items()}


def restore_adapters(snapshot: Mapping[str, Mapping[str, SourceAdapter]]) -> None:
    """把注册表恢复为快照内容（测试隔离用）。"""
    ADAPTER_REGISTRY.clear()
    for domain, adapters in snapshot.items():
        ADAPTER_REGISTRY[domain] = dict(adapters)
