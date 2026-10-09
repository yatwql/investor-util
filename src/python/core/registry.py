"""中央注册表门面 — 统一 re-export 数据模块注册表与报告章节注册表。

按注册职责域下沉（导入面与拆分前完全一致）：
  - 数据模块 / 缓存 TTL / LLM 设置键派生 → ``core/data_registry.py``
  - 报告章节 / 导航分组 / 页签名称派生 → ``core/report_section_registry.py``
  - 计算模块 / 章节-区块矩阵 → 原有子模块（本门面继续单入口再导出）

用法：
  >>> from src.python.core.registry import get_cache_ttl_defaults
  >>> ttl_map = get_cache_ttl_defaults()
  >>> ttl_map["price"]
  86400
"""

from __future__ import annotations

import logging

from src.python.core.computation_registry import (  # noqa: F401
    ComputModuleDef,
    _COMPUTATION_REGISTRY,
    get_computation_module,
    get_computation_registry,
)
from src.python.core.data_registry import (  # noqa: F401
    DataModuleDef,
    LLM_HIDDEN_KEYS,
    LLM_MODULE_GATED_SECTIONS,
    _MODULE_REGISTRY,
    get_cache_ttl_defaults,
    get_exact_type_map,
    get_known_enabled_llm_keys,
    get_known_llm_settings_keys,
    get_llm_module_name,
    get_llm_module_names,
    get_prefix_type_map,
    get_registered_data_types,
    get_registry,
    visible_llm_module_names,
)
from src.python.core.report_section_registry import (  # noqa: F401
    NAV_GROUPS,
    _LLM_SHEET_NAME_KEYS,
    _REPORT_SECTION_DEFAULT,
    _REPORT_SHEET_NAMES,
    get_report_section_keys,
    get_report_section_number,
    get_report_section_order,
    get_report_sheet_name,
)
from src.python.core.section_block_registry import (  # noqa: F401
    SECTION_BLOCK_SPECS,
    SectionBlockSpec,
    get_section_block_spec,
)

logger = logging.getLogger("invest")

# ── 计算模块注册表（_COMPUTATION_REGISTRY） ──────────────────
# 计算模块不能反向导入 report/，此注册表确保分析模块与报表层的
# 单向依赖关系（analysis 层隔离约束）；条目与访问器持于
# core/computation_registry.py（顶部 import re-export，单入口不变）。
