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
  - **覆盖以「提示词是否真的含该段」为准**：进了提示词的内容必须进指纹
    （``competitive_context`` / ``metrics`` / ``data_quality_text`` /
    ``pipeline_data`` 派生的【环比变化】【数据质量降级】两段），不进提示词的
    段落不并入（纯成本失效）。
  - **一次渲染、两侧共享同一实例**：``competitive_context`` 与
    ``data_quality_text`` 由调用方（``generate_all_llm``）渲染一次后同时交给预检侧
    与写侧，两边不得各自渲染——两次渲染会让「进键的文本」与「进提示词的文本」
    退化为靠纪律对齐。
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
    "debate_procon_fingerprint",
    "debate_synthesis_fingerprint",
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
        competitive_context: **已渲染**的竞争语境文本块，由调用方渲染一次后
            与提示词共享**同一实例**（仅提示词含该段的模块使用）
        metrics: 量化指标字典（指标表 / 情景分析 / 风格一致性的共同来源，
            仅 expert_review 使用）
        data_quality_text: **已渲染**的数据质量详细状态文本块，由调用方渲染一次后
            与提示词共享**同一实例**（仅提示词含该段的模块使用——目前仅
            health_check）
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
    competitive_context: str = ""
    metrics: dict | None = None
    data_quality_text: str = ""


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


def _pipeline_block_cache_suffix(pipeline_data: dict | None) -> str:
    """``pipeline_data`` 注入复盘类提示词的正文段（环比差异 / 数据质量降级）指纹后缀。

    复盘与辩论提示词都会带上【环比变化】【数据质量降级】两段（构建器
    ``_build_difpipeline_data_block`` / ``_build_data_degradation_block``），
    但这两段此前不参与指纹——持仓未动而降级事件集变化时键不变，预检命中旧键，
    报告继续陈述「某数据源不可用」（或漏报新故障），且不报错。

    与 ``_signal_digest_cache_suffix`` 同法：调用**提示词侧同一构建器**取文本再
    哈希，故「进键的文本」与「进提示词的文本」由同一段代码产出，不靠纪律对齐。
    两段皆空（无环比数据、无降级事件）→ ``""``，键与未注入时一致，不误伤旧缓存。

    Args:
        pipeline_data: 报告管线数据契约。
    """
    # 延迟导入：prompts_core 属提示词层，模块级导入会与 llm 包初始化形成环。
    from src.python.llm.prompts_core import (
        _build_data_degradation_block,
        _build_difpipeline_data_block,
    )

    _blocks = [
        _build_difpipeline_data_block(pipeline_data),
        _build_data_degradation_block(pipeline_data),
    ]
    _block = "\n".join(b for b in _blocks if b)
    if not _block:
        return ""
    return "_" + compute_fingerprint(_block)


def global_macro_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """全球政经局势：指数行情 / 总市值 / 盈亏 / 分类汇总 + 竞争语境块。

    竞争语境块（组合 vs 指数今日/区间对比）由其提示词直接承载，故必须进键：
    否则「组合未动、基准指数已动」时键不变，预检命中旧键后复用按旧指数算出的
    对比结论。该块为**已渲染文本**，与注入提示词的实例同一（见模块 docstring）。
    """
    return compute_fingerprint(
        inputs.a_indices,
        inputs.us_indices,
        inputs.total_mv,
        inputs.total_profit,
        inputs.categories,
        inputs.competitive_context,
    )


def expert_review_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """智囊团深度复盘：基础指纹 + 提示词内容（竞争语境块 / 量化指标）+ 五段现算后缀。

    五个后缀（决策教训 / 信号预消化 / 环比与降级块 / 确定性信号摘要 / 结构化
    决策头）各自的开关判定收敛在函数内部，关闭或样本不足时返回空串——键与未
    启用时一致，不误伤既有缓存。

    竞争语境块与 ``metrics`` 都是其提示词的正文段（【今日对比】/【区间对比】/
    【指标对比】/【量化指标】/情景分析），连同 ``pipeline_data`` 派生的【环比
    变化】【数据质量降级】两段（见 ``_pipeline_block_cache_suffix``）一并纳入哈希。
    """
    _fp = compute_fingerprint(
        build_llm_fingerprint(
            total_mv=inputs.total_mv,
            total_cost=inputs.total_cost,
            total_profit=inputs.total_profit,
            total_today_profit=inputs.total_today_profit,
            holdings_details=inputs.holdings_details,
            penetrated_assets=inputs.penetrated_assets,
            categories=inputs.categories,
            history_data=inputs.history_data,
        ),
        inputs.competitive_context,
        inputs.metrics,
    )
    _fp += debate_feature_cache_suffix()
    if decision_ledger.is_active():
        _fp += decision_ledger.lessons_cache_suffix()
    _fp += _signal_digest_cache_suffix(inputs.pipeline_data)
    _fp += _pipeline_block_cache_suffix(inputs.pipeline_data)
    _fp += signal_ledger.summary_cache_suffix()
    _fp += structured_header_cache_suffix()
    return _fp


def debate_procon_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """辩论白脸 / 黑脸两键共用的基础指纹 + 辩论增强后缀 + 环比与降级块后缀。

    **仅写侧使用**：辩论模式绕过标准预检（其缓存键族 ``llm_debate_*`` 与标准
    ``llm_expert_review_*`` 不同），故不进 ``MODULE_FINGERPRINT_BUILDERS``。

    输入口径以其提示词实际包含的段落为准——基础持仓 + 竞争语境块 + 量化指标 +
    辩论增强后缀 + ``pipeline_data`` 派生的【环比变化】【数据质量降级】两段
    （白脸/黑脸复用 ``_build_expert_review_prompt``，这两段随之进入其提示词）。

    **刻意不并入** ``history_data`` 与决策教训、信号摘要、结构化决策头后缀：
    辩论提示词不含这些段落（不传 ``history_data``、不开信号预消化与结构化决策头），
    并入只会让每次运行都换键 —— 白脸/黑脸两次昂贵调用每份报告必 miss。
    """
    return (
        compute_fingerprint(
            build_llm_fingerprint(
                total_mv=inputs.total_mv,
                total_cost=inputs.total_cost,
                total_profit=inputs.total_profit,
                total_today_profit=inputs.total_today_profit,
                holdings_details=inputs.holdings_details,
                penetrated_assets=inputs.penetrated_assets,
                categories=inputs.categories,
            ),
            inputs.competitive_context,
            inputs.metrics,
        )
        + debate_feature_cache_suffix()
        + _pipeline_block_cache_suffix(inputs.pipeline_data)
    )


def debate_synthesis_fingerprint(inputs: ModuleFingerprintInputs, synthesis_prompt: str) -> str:
    """辩论综合（第三段）：辩论基础指纹 + **综合提示词全文**。

    **仅写侧使用**（同 ``debate_procon_fingerprint``）。

    综合提示词 = 白脸/黑脸**全文** + 条件推理情景段（``debate.conditional.scenarios``
    驱动）+ 集中度问答段（``debate.qa_concentration.threshold`` 驱动），由
    ``_build_debate_synthesis_prompt`` 一次性渲染。既然提示词就是这三者的函数，
    键直接取该渲染结果——无需逐项枚举入哈希的来源，也就不会漏项。

    此前本键另起一套：截取 pro/con **前 200 字符**摘要再拼接。两处后果——
    正文差异落在 200 字符之后时键不动（命中按旧正文生成的综合结论），仅改
    config（情景名/描述、集中度阈值）而开关位不变时键同样不动。

    Args:
        inputs: 与白脸/黑脸同一份输入闭包（除 ``pipeline_data`` 外，其效果已由
            基础指纹承载）。
        synthesis_prompt: 已渲染的综合阶段 user prompt。
    """
    return compute_fingerprint(debate_procon_fingerprint(inputs), synthesis_prompt)


def health_check_fingerprint(inputs: ModuleFingerprintInputs) -> str:
    """持仓体检报告：基础指纹 + 数据质量详细状态块 + 信号预消化后缀。

    数据质量块（【数据质量详细状态】）由其提示词直接承载，故必须进键：否则
    「数据源故障期间生成并缓存、随后源恢复」时持仓未变故键不变，预检命中旧键、
    复用陈述与此刻事实相反的故障结论。该块为**已渲染文本**，与注入提示词的实例
    同一（见模块 docstring）。

    成本口径：该块是**本次运行**的数据源画像（事件集只在进程内累积，不含时间戳
    等易变字段），且本模块指纹本就含 ``total_today_profit``——交易日内持仓一有
    盈亏变化即换键，故纳入本块带来的边际额外失效接近零。

    同理由纳入 ``pipeline_data`` 派生的【环比变化】【数据质量降级】两段（体检
    提示词同样承载它们，见 ``_pipeline_block_cache_suffix``）。
    """
    _fp = compute_fingerprint(
        build_llm_fingerprint(
            total_mv=inputs.total_mv,
            total_cost=inputs.total_cost,
            total_profit=inputs.total_profit,
            total_today_profit=inputs.total_today_profit,
            holdings_details=inputs.holdings_details,
            penetrated_assets=inputs.penetrated_assets,
            categories=inputs.categories,
            history_data=inputs.history_data,
        ),
        inputs.data_quality_text,
    )
    _fp += _signal_digest_cache_suffix(inputs.pipeline_data)
    _fp += _pipeline_block_cache_suffix(inputs.pipeline_data)
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
