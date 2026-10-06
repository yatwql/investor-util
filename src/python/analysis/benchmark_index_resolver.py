"""基准指数映射（benchmark_index_resolver）— 目标持仓 → 业绩基准指数（纯映射，零 I/O）。

三阶优先级（唯一口径，Excel/HTML/LLM 引用同源；先决门槛与红线见设计文档）：

  1. **配置覆盖**：``config.json whatif_benchmark_index``（显式指数代码，必须通过
     ``core.code_utils.is_index_code`` 判定；非法值告警忽略、回落后续级）
  2. **持仓基准文本**：按目标持仓成本降序逐只取其业绩基准文本（注入 getter，源自
     ``fund_benchmarks`` 内置表/用户扩展/接口），与宽基指数池
     （``comparison_indices`` 反查 文本→代码）做包含匹配，首个命中即用
  3. **宽基默认**：``sh000300``（沪深300）

代码类型判定一律复用 ``core/code_utils``（``is_index_code``），禁自建前缀表；
基准文本查询与指数行情由调用方注入——分析层零网络零磁盘（单向依赖纪律）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from src.python.core.code_utils import is_index_code

logger = logging.getLogger("invest")

#: 宽基默认指数（第 3 阶兜底；显示名缺省与之配套）
DEFAULT_BENCHMARK_INDEX = "sh000300"
DEFAULT_BENCHMARK_NAME = "沪深300"

#: ``source`` 取值（面板展示「映射来源」的唯一枚举）
SOURCE_CONFIG = "config"
SOURCE_HOLDINGS = "holdings"
SOURCE_DEFAULT = "default"


def resolve_benchmark_index(
    holdings: Iterable[Mapping[str, Any]] | None,
    *,
    override: str | None = None,
    comparison_indices: Mapping[str, str] | None = None,
    benchmark_text_getter: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """目标持仓 → 业绩基准指数（配置覆盖 → 持仓基准文本 → 宽基默认）。

    Args:
        holdings: 目标持仓条目（``{code, name, cost}``；``cost`` 用于按权重降序
            优先匹配，缺省按 0——空清单直接落默认级）
        override: 配置覆盖值（``whatif_benchmark_index``；``None``/空白/非法代码
            → 忽略并回落，非法值另记 warning）
        comparison_indices: 宽基指数池 ``{指数代码: 显示名}``（反查 显示名→代码；
            池内非法指数代码不参与匹配）
        benchmark_text_getter: 单只基金业绩基准文本查询（注入，零 I/O）；
            抛异常/返回非字符串视为该代码无文本，继续下一只

    Returns:
        ``{"code", "name", "source"}``——``source`` ∈ ``config`` / ``holdings`` /
        ``default``（映射来源随面板展示，供读者判断是配置还是推断）
    """
    pool = dict(comparison_indices or {})

    # ── 第 1 阶：配置覆盖（显式意图，最高优先；须为合法指数代码）──
    if override and str(override).strip():
        candidate = str(override).strip()
        if is_index_code(candidate):
            return {"code": candidate, "name": pool.get(candidate, candidate), "source": SOURCE_CONFIG}
        logger.warning("[基准映射] 配置覆盖 %r 不是合法指数代码，忽略并按持仓/默认回落", override)

    # ── 第 2 阶：持仓业绩基准文本 → 宽基池反查（成本降序 = 权重优先）──
    if benchmark_text_getter is not None and pool:
        ordered = sorted(holdings or [], key=lambda h: float(h.get("cost") or 0.0), reverse=True)
        for item in ordered:
            code = str((item or {}).get("code") or "").strip()
            if not code:
                continue
            try:
                text = benchmark_text_getter(code)
            except Exception:  # noqa: BLE001 — 文本查询失败只回落，不中断映射（仅兜 Exception）
                logger.debug("[基准映射] %s 基准文本查询失败，跳过", code, exc_info=True)
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            for idx_code, idx_name in pool.items():
                if not is_index_code(idx_code):
                    continue
                name = str(idx_name or "")
                if name and name in text:
                    return {"code": idx_code, "name": name, "source": SOURCE_HOLDINGS}

    # ── 第 3 阶：宽基默认 ──
    return {
        "code": DEFAULT_BENCHMARK_INDEX,
        "name": pool.get(DEFAULT_BENCHMARK_INDEX, DEFAULT_BENCHMARK_NAME),
        "source": SOURCE_DEFAULT,
    }


__all__ = [
    "DEFAULT_BENCHMARK_INDEX",
    "DEFAULT_BENCHMARK_NAME",
    "SOURCE_CONFIG",
    "SOURCE_DEFAULT",
    "SOURCE_HOLDINGS",
    "resolve_benchmark_index",
]
