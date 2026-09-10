"""LLM 模块缓存指纹的唯一事实来源 — 预检侧与写侧同源。

模块缓存键统一为 ``CACHE_PREFIX_LLM + f"{模块}_{指纹}"``，两侧各自拼接：

  - **预检侧**：``generators_orchestrator._compute_module_cache_info()``（判断能否跳过生成）
  - **写侧**：``generators.py`` 各生成函数的 ``_fingerprint`` 闭包（经 ``skeleton.py``
    的 ``_run_standard_mode`` 组装同一形态的键）

历史教训：两侧原先靠「注释声明同调」维护，每逢新增影响提示词或内容的输入
（风险信号摘要、信号预消化后缀、决策教训后缀、辩论增强后缀…），都要在两处手工
各改一遍。任一侧漏改即产生**读写键永不同源**——预检 read 落空、每次报告全量派发，
且不报错、只表现为静默的性能与日志噪声（如 ``history_data`` 与辩论增强后缀两处
历史偏差）。本模块把每个模块的指纹构造收敛为**唯一函数**，两侧都调用它：
新增输入只需改一处，同源由结构保证，而非靠纪律与复查维持。

约定：
  - 四个 LLM 模块（global_macro / expert_review / health_check / penetration_deep）
    的指纹均由 ``MODULE_FINGERPRINT_BUILDERS`` 提供；两侧不得再自行拼接模块指纹。
  - ``ModuleFingerprintInputs`` 是两侧都持有的输入闭包；``history_data`` 的风险
    信号摘要对三模块统一参与哈希（口径一致优先于逐模块精简——多算只带来无害的
    过度失效，漏算则导致内容与键脱钩的陈旧缓存）。
  - 返回值为**指纹本体**（不含 ``CACHE_PREFIX_LLM + 模块名`` 前缀），缓存键由两侧
    按同一形态自行拼装。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.python.config.features import is_feature_enabled
from src.python.core import decision_ledger
from src.python.core import signal_ledger
from src.python.core.decision_header import structured_header_cache_suffix
from src.python.llm.fingerprint import build_llm_fingerprint, compute_fingerprint
from src.python.llm.prompts_signals import _signal_digest_cache_suffix

__all__ = [
    "ModuleFingerprintInputs",
    "debate_feature_cache_suffix",
    "global_macro_fingerprint",
    "expert_review_fingerprint",
    "health_check_fingerprint",
    "penetration_deep_fingerprint",
    "MODULE_FINGERPRINT_BUILDERS",
]


@dataclass(frozen=True)
class ModuleFingerprintInputs:
    """LLM 模块指纹的输入闭包 — 预检侧与写侧共同持有的要素。

    两侧调用点都持有同一组数据（同一次报告生成的参数），故以同一对象喂入同一
    构造器即可保证逐字节相同的哈希输入。

    Attributes:
        total_mv: 持仓总市值
        total_cost: 持仓总成本
        total_profit: 累计盈亏
        total_today_profit: 本日盈亏
        holdings_details: 持仓明细（指纹仅取 name/code/cost 稳定字段）
        penetrated_assets: 穿透 TOP10 资产列表
        categories: 分类汇总
        history_data: 组合历史走势数据（仅取 key 风险信号摘要入哈希）
        pipeline_data: 管线上下文（供信号预消化后缀计算）
        a_indices: A 股指数行情（仅 global_macro 使用）
        us_indices: 美股指数行情（仅 global_macro 使用）
    """

    total_mv: float = 0.0
    total_cost: float = 0.0
    total_profit: float = 0.0
    total_today_profit: float = 0.0
    holdings_details: list[dict] | None = None
    penetrated_assets: list[dict] | None = None
    categories: dict | None = None
    history_data: dict | None = None
    pipeline_data: dict | None = None
    a_indices: dict | None = None
    us_indices: dict | None = None


def debate_feature_cache_suffix() -> str:
    """辩论增强组合（条件推理 / 集中度问答）的缓存指纹后缀。

    取各启用模式的代号字母排序后拼接（conditional=c，qa_concentration=q），
    保证相同组合产生相同后缀、不同组合不串扰。非辩论模式下这些增强会改写
    expert_review 的提示词（追加情景分析 / 反问引导段），故后缀必须参与
    expert_review 指纹——否则同一持仓在开关切换前后会命中同一份缓存。

    Returns:
        空字符串（无增强启用）或 "_c"、"_cq" 等后缀。
    """
    _parts: list[str] = []
    if is_feature_enabled("llm_debate_conditional"):
        _parts.append("c")  # conditional
    if is_feature_enabled("llm_debate_qa_concentration"):
        _parts.append("q")  # qa_concentration
    return "_" + "".join(sorted(_parts)) if _parts else ""


def global_macro_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """全球政经局势：指数行情 / 总市值 / 盈亏 / 分类汇总。"""
    return compute_fingerprint(
        inputs.a_indices,
        inputs.us_indices,
        inputs.total_mv,
        inputs.total_profit,
        inputs.categories,
    )


def expert_review_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """智囊团深度复盘：基础指纹 + 辩论增强 + 四段按开关现算的后缀。

    四个后缀（决策教训 / 信号预消化 / 确定性信号摘要 / 结构化决策头）各自的
    开关判定收敛在函数内部，关闭或样本不足时返回空串——键与未启用时一致，
    不误伤既有缓存。
    """
    _fp = build_llm_fingerprint(
        total_mv=inputs.total_mv,
        total_cost=inputs.total_cost,
        total_profit=inputs.total_profit,
        total_today_profit=inputs.total_today_profit,
        holdings_details=inputs.holdings_details,
        penetrated_assets=inputs.penetrated_assets,
        categories=inputs.categories,
        history_data=inputs.history_data,
    )
    _fp += debate_feature_cache_suffix()
    if decision_ledger.is_active():
        _fp += decision_ledger.lessons_cache_suffix()
    _fp += _signal_digest_cache_suffix(inputs.pipeline_data)
    _fp += signal_ledger.summary_cache_suffix()
    _fp += structured_header_cache_suffix()
    return _fp


def health_check_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """持仓体检报告：基础指纹 + 信号预消化后缀。"""
    _fp = build_llm_fingerprint(
        total_mv=inputs.total_mv,
        total_cost=inputs.total_cost,
        total_profit=inputs.total_profit,
        total_today_profit=inputs.total_today_profit,
        holdings_details=inputs.holdings_details,
        penetrated_assets=inputs.penetrated_assets,
        categories=inputs.categories,
        history_data=inputs.history_data,
    )
    _fp += _signal_digest_cache_suffix(inputs.pipeline_data)
    return _fp


def penetration_deep_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """穿透深度分析：基础指纹（穿透资产含 mv/sector/ratio 全字段）。"""
    return build_llm_fingerprint(
        total_mv=inputs.total_mv,
        total_cost=inputs.total_cost,
        total_profit=inputs.total_profit,
        total_today_profit=inputs.total_today_profit,
        holdings_details=inputs.holdings_details,
        penetrated_assets=inputs.penetrated_assets,
        categories=inputs.categories,
        full_penetration=True,
        history_data=inputs.history_data,
    )


# 模块标识 → 指纹构造器。预检侧按键取指纹建缓存键，写侧闭包按同一函数现算，
# 新增 LLM 模块时在此登记即可（模块键与 llm 模块注册表一致）。
MODULE_FINGERPRINT_BUILDERS: dict[str, Callable[[ModuleFingerprintInputs], str]] = {
    "global_macro": global_macro_fingerprint,
    "expert_review": expert_review_fingerprint,
    "health_check": health_check_fingerprint,
    "penetration_deep": penetration_deep_fingerprint,
}
