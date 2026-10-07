"""计算模块注册表 — 纯计算/分析模块（无缓存）的元信息注册。

计算模块不能反向导入 report/，本注册表确保分析模块与报表层的
单向依赖关系（analysis 层隔离约束）得以维持。由 `core/registry.py`
顶部 import re-export 对外提供，调用方入口保持 `from ...registry import ...` 不变。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComputModuleDef:
    """计算模块注册表条目。

    记录所有计算/分析模块的元信息，
    用于运行时发现、依赖管理和指标级断路的注册基础。

    Attributes:
        name: 模块中文名称。
        module_key: 模块键名，如 "analytics_metrics"、"analytics_liquidity"。
        label: 短标签（用于日志/提示）。
        dependencies: 前置数据模块键名列表（如 "bond_yield"、"history"）。
        description: 模块功能说明，用于文档生成。
        status: 实现状态（planned / implemented）。
    """

    name: str
    module_key: str
    label: str = ""
    dependencies: tuple[str, ...] = ()
    description: str = ""
    status: str = "planned"


_COMPUTATION_REGISTRY: tuple[ComputModuleDef, ...] = (
    ComputModuleDef(
        name="量化指标计算",
        module_key="analytics_metrics",
        label="指标",
        dependencies=("bond_yield", "history"),
        description="夏普比率、卡玛比率、HHI 集中度、组合 Beta、持仓胜率、换手率、波动率、最大回撤等指标",
        status="implemented",
    ),
    ComputModuleDef(
        name="流动性分析",
        module_key="analytics_liquidity",
        label="流动性",
        dependencies=(),
        description="场内/场外比例、停牌风险、基金封闭期分析",
        status="implemented",
    ),
    ComputModuleDef(
        name="外汇敞口分析",
        module_key="analytics_fx_exposure",
        label="外汇",
        dependencies=(),
        description="A股/港股/美股 国别分布与外汇风险敞口判断",
        status="implemented",
    ),
    ComputModuleDef(
        name="情景分析",
        module_key="analytics_scenario",
        label="情景",
        dependencies=("history",),
        description="市场上涨/下跌的情景模拟与影响评估（±10%/±20%/±30% 六情景，含置信区间传播）",
        status="implemented",
    ),
    ComputModuleDef(
        name="组合校准分析",
        module_key="analytics_alignment",
        label="校准",
        dependencies=(),
        description="组合校准修正因子：费率估算、现金剥离、时间加权收益率（TWR）",
        status="implemented",
    ),
    ComputModuleDef(
        name="用户画像推断",
        module_key="analytics_inferrer",
        label="画像",
        dependencies=(),
        description="从持仓结构推断用户风险偏好与投资风格",
        status="planned",
    ),
    ComputModuleDef(
        name="事实锚定校验器",
        module_key="analytics_fact_checker",
        label="事实校验",
        dependencies=(),
        description="LLM 输出的事实锚定校验：数值一致性、品种存在性、排名正确性（纯算法层）",
        status="implemented",
    ),
)


def get_computation_registry() -> tuple[ComputModuleDef, ...]:
    """返回完整的计算模块注册表副本。"""
    return _COMPUTATION_REGISTRY


def get_computation_module(module_key: str) -> ComputModuleDef | None:
    """根据 module_key 查找计算模块定义。

    Args:
        module_key: 模块键名，如 "analytics_metrics"

    Returns:
        ComputModuleDef 或 None（未找到）
    """
    for m in _COMPUTATION_REGISTRY:
        if m.module_key == module_key:
            return m
    return None
