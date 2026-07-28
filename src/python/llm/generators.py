"""LLM 生成模块 — 全局政经/智囊团/体检/穿透四大单例函数 + 辩论模式生成。

职责：
  - 4 个单例生成函数（generate_global_macro 等）
  - 辩论模式白脸/黑脸/综合生成（generate_debate_procon）
  - 批量编排 → generators_orchestrator.py
  - 新闻关联 → generators_news.py
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from src.python.cache import get as cache_get
from src.python.cache import set as cache_set
from src.python.llm.fingerprint import (
    build_llm_fingerprint,
    compute_fingerprint,
    get_cache_ttl_llm,
)
from src.python.llm.prompts import (
    _SYSTEM_DEBATE_CON,
    _SYSTEM_DEBATE_PRO,
    _SYSTEM_DEBATE_SYNTHESIS,
    _SYSTEM_EXPERT_REVIEW,
    _SYSTEM_GLOBAL_MACRO,
    _SYSTEM_HEALTH_CHECK,
    _SYSTEM_PENETRATION_DEEP,
    _build_competitive_context_block,
    _build_debate_synthesis_prompt,
    _build_expert_review_prompt,
    _build_global_macro_prompt,
    _build_health_check_prompt,
    _build_penetration_deep_prompt,
)
from src.python.llm.skeleton import generate_llm_module

logger = logging.getLogger("invest")

__all__ = [
    "generate_global_macro",
    "generate_expert_review",
    "generate_health_check",
    "generate_penetration_deep_analysis",
    "generate_debate_procon",
    "_filter_hallucinated_codes",
]


def generate_global_macro(
    a_indices: dict[str, dict[str, Any]],
    us_indices: dict[str, dict[str, Any]],
    total_mv: float,
    total_profit: float,
    total_cost: float,
    categories: dict,
    sector_flow: list[dict[str, Any]] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    competitive_context: str | None = None,
    holdings_details: list[dict] | None = None,
) -> tuple[str | None, bool]:
    """生成全球政经局势。

    Args:
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），可选。
        holdings_details: 持仓明细（可选），用于提供 TOP3 排名，防止 LLM 虚构最大持仓。
    """

    def _fingerprint():
        return compute_fingerprint(a_indices, us_indices, total_mv, total_profit, categories)

    def _prompt():
        return _build_global_macro_prompt(
            a_indices,
            us_indices,
            total_mv,
            total_profit,
            total_cost,
            categories,
            sector_flow,
            competitive_context=competitive_context,
            holdings_details=holdings_details,
        )

    return generate_llm_module(
        llm_config,
        "global_macro",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_GLOBAL_MACRO,
        prompt_builder=_prompt,
        max_tokens_default=800,
        timeout_default=60.0,
        output_brief_limit=200,
    )


def generate_expert_review(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    pipeline_data: dict | None = None,
    competitive_context: str | None = None,
    metrics: dict | None = None,
) -> tuple[str | None, bool]:
    """生成智囊团深度复盘。

    Args:
        competitive_context: 竞争语境文本块（组合 vs 沪深300 收益对比），可选。
        metrics: 量化指标字典，compute_all_metrics() 的输出。
    """

    def _fingerprint():
        return build_llm_fingerprint(
            total_mv=total_mv,
            total_cost=total_cost,
            total_profit=total_profit,
            total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
        )

    def _prompt():
        return _build_expert_review_prompt(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            pipeline_data=pipeline_data,
            competitive_context=competitive_context,
            metrics=metrics,
        )

    return generate_llm_module(
        llm_config,
        "expert_review",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_EXPERT_REVIEW,
        prompt_builder=_prompt,
        max_tokens_default=8192,
        timeout_default=120.0,
        output_brief_limit=300,
    )


def generate_health_check(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    pipeline_data: dict | None = None,
    degradation_events: list[dict] | None = None,
) -> tuple[str | None, bool]:
    """生成持仓体检报告。"""

    def _fingerprint():
        return build_llm_fingerprint(
            total_mv=total_mv,
            total_cost=total_cost,
            total_profit=total_profit,
            total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
        )

    def _prompt():
        return _build_health_check_prompt(
            total_mv,
            total_cost,
            total_profit,
            total_today_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
            pipeline_data=pipeline_data,
            degradation_events=degradation_events,
        )

    return generate_llm_module(
        llm_config,
        "health_check",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_HEALTH_CHECK,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=120.0,
        output_brief_limit=300,
    )


def generate_penetration_deep_analysis(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
) -> tuple[str | None, bool]:
    """生成穿透深度分析。"""

    def _fingerprint():
        return build_llm_fingerprint(
            total_mv=total_mv,
            total_cost=total_cost,
            total_profit=total_profit,
            total_today_profit=total_today_profit,
            holdings_details=holdings_details,
            penetrated_assets=penetrated_assets,
            categories=categories,
            full_penetration=True,
        )

    def _prompt():
        return _build_penetration_deep_prompt(
            total_mv,
            total_cost,
            total_profit,
            holdings_count,
            categories,
            penetrated_assets,
            holdings_details=holdings_details,
        )

    return generate_llm_module(
        llm_config,
        "penetration_deep",
        force=force,
        http_client=http_client,
        fingerprint_fn=_fingerprint,
        system_prompt_default=_SYSTEM_PENETRATION_DEEP,
        prompt_builder=_prompt,
        max_tokens_default=4096,
        timeout_default=90.0,
        output_brief_limit=300,
    )


# ── 辩论模式：白脸/黑脸/综合生成 ───────────────────────────


# 已知安全英文词白名单——不应被当作虚构股票代码（大小写不敏感）
# 出现场景：LLM 在分析报告中插入 HTML/CSS 标签、金融术语、英文词汇
_HALLU_SAFE_WORDS: set[str] = {
    # 已报告误杀（HTML/CSS 标签、英文词汇）
    "style",
    "flash",
    "strong",
    "font",
    "size",
    "color",
    "token",
    "qdii",
    "12px",
    "100etf",
    # HTML/CSS 常见属性
    "width",
    "height",
    "align",
    "border",
    "margin",
    "padding",
    "inline",
    "solid",
    "dashed",
    "dotted",
    "double",
    "groove",
    "ridge",
    "inset",
    "outset",
    "hidden",
    "visible",
    "scroll",
    # 金融/经济分析高频词汇
    "value",
    "price",
    "yield",
    "total",
    "index",
    "month",
    "year",
    "daily",
    "weekly",
    "growth",
    "level",
    "range",
    "trend",
    "large",
    "small",
    "short",
    "long",
    "cover",
    "limit",
    "order",
    "trade",
    "share",
    "stock",
    "bond",
    "fund",
    "cash",
    "risk",
    "rate",
    "asset",
    "debt",
    "equity",
    "fixed",
    "float",
    "clear",
    "cycle",
    "light",
    "dark",
    "block",
    "track",
    "focus",
    "upper",
    "lower",
    "major",
    "minor",
    "prime",
    "core",
    "delta",
    "gamma",
    "theta",
    "alpha",
    "beta",
    "sigma",
    "rally",
    "crash",
    "bulls",
    "bears",
    "spike",
    "split",
    # 报告写作常见词
    "title",
    "table",
    "label",
    "point",
    "issue",
    "topic",
    "chart",
    "graph",
    "phase",
    "stage",
    "state",
    "event",
    "cause",
    "effect",
    "basis",
    "shift",
    "swing",
}


def _is_safe_word(code: str) -> bool:
    """判断一个由正则捕获的字母数字组合是否为安全英文词汇而非虚构代码。

    两条规则满足其一即安全：
      1. **全小写字母**：实盘交易所代码不会全小写，低风险豁免。
      2. **白名单命中**：大小写不敏感匹配 ``_HALLU_SAFE_WORDS``。

    Args:
        code: 正则捕获的 4-6 位字母数字串。

    Returns:
        该词为安全英文词汇时返回 True，否则返回 False。
    """
    # 全小写字母 → 绝非实盘代码
    if code.islower():
        return True
    # 大小写不敏感匹配白名单
    return code.lower() in _HALLU_SAFE_WORDS


def _filter_hallucinated_codes(
    text: str,
    valid_codes: set[str],
) -> str:
    """从 LLM 输出中过滤虚构代码。

    正则提取所有 6 位数字代码（A 股）及字母数字代码（港股/美股），
    与 valid_codes 交叉校验，移除虚构代码及其所在整句。

    Args:
        text: LLM 原始输出文本。
        valid_codes: 合法持仓代码集合。

    Returns:
        过滤后的文本（无虚构代码的句子），如全部移除则返回空字符串。
    """
    if not text:
        return text

    # 使用左边界(^|[^A-Za-z0-9])和右边界([^A-Za-z0-9]|$)替代\b
    # 避免中文环境下\b失效（Python re 视中文字符为\w）
    found_codes = set(re.findall(r"(?:^|[^A-Za-z0-9])([A-Za-z0-9]{4,6})(?=[^A-Za-z0-9]|$)", text))
    invalid = {c for c in found_codes if c not in valid_codes and not c.isdigit() and not _is_safe_word(c)}

    if not invalid:
        return text

    logger.warning("[debate-hallu] 检测到 %d 个虚构品种代码: %s", len(invalid), invalid)
    lines = text.split("\n")
    filtered = []
    removed_count = 0
    for line in lines:
        line_codes = set(re.findall(r"(?:^|[^A-Za-z0-9])([A-Za-z0-9]{4,6})(?=[^A-Za-z0-9]|$)", line))
        if line_codes & invalid:
            removed_count += 1
            continue
        filtered.append(line)

    logger.info(
        "[debate-hallu] 过滤前 %d 字符，过滤后 %d 字符，移除了 %d 个虚构品种所在行",
        len(text),
        len("\n".join(filtered)),
        removed_count,
    )
    return "\n".join(filtered)


def generate_debate_procon(
    total_mv: float,
    total_cost: float,
    total_profit: float,
    total_today_profit: float,
    holdings_count: int,
    categories: dict,
    penetrated_assets: list[dict] | None = None,
    holdings_details: list[dict] | None = None,
    force: bool = False,
    http_client: httpx.Client | None = None,
    llm_config: dict | None = None,
    pipeline_data: dict | None = None,
    competitive_context: str | None = None,
    metrics: dict | None = None,
    *,  # 以下为关键字参数
    session_cache: dict | None = None,
) -> tuple[str | None, str | None, str | None]:
    """生成白脸/黑脸辩论 + 综合结果。

    pro 或 con 失败时返回 (None, None, None) — 由调用方决定是否回退普通模式。
    synthesis 失败时返回 (pro_text, con_text, None) — 调用方可使用拼接结果。

    Returns:
        (pro_text, con_text, synthesis_text) 三元组，均为 None 表示完全失败。
    """
    import threading as _threading
    from src.python.config._core import get_llm_config
    from src.python.llm.fingerprint import build_llm_fingerprint
    from src.python.llm.prompts_action import _build_debate_synthesis_prompt, _build_expert_review_prompt

    # ── 构建基础 user prompt（复用普通 expert_review 的数据块） ──
    _user = _build_expert_review_prompt(
        total_mv,
        total_cost,
        total_profit,
        total_today_profit,
        holdings_count,
        categories,
        penetrated_assets,
        holdings_details=holdings_details,
        pipeline_data=pipeline_data,
        competitive_context=competitive_context,
        metrics=metrics,
    )

    # ── 指纹计算 ────────────────────────────────────────
    _fingerprint = build_llm_fingerprint(
        total_mv=total_mv,
        total_cost=total_cost,
        total_profit=total_profit,
        total_today_profit=total_today_profit,
        holdings_details=holdings_details,
        penetrated_assets=penetrated_assets,
        categories=categories,
    )

    # ── Session 级缓存（线程安全） ──────────────────────
    _cache_lock = _threading.Lock()

    def _check_session_cache(key: str) -> str | None:
        if session_cache is not None:
            with _cache_lock:
                return session_cache.get(key)
        return None

    def _set_session_cache(key: str, value: str) -> None:
        if session_cache is not None:
            with _cache_lock:
                session_cache[key] = value

    # ── 获取 debate 配置 ────────────────────────────────
    _lc = llm_config or get_llm_config()
    debate_cfg = (_lc or {}).get("debate", {})
    m1_cfg = debate_cfg.get("mode_1_procon", {})
    _per_call_max_tokens = m1_cfg.get("per_call_max_tokens")
    _synthesis_temperature = m1_cfg.get("synthesis_temperature", 0.5)

    _max_tokens = _per_call_max_tokens if _per_call_max_tokens is not None else 8192
    _timeout = debate_cfg.get("per_call_timeout_override", 90)

    # ── Token 预算守卫 ─────────────────────────────────
    _max_total_tokens_budget = debate_cfg.get("max_total_tokens_per_report", 16000)
    # 按 1 中文字符 ≈ 1.5 token 估算，转为字符级阈值（保守偏宽松）
    _budget_char_threshold = int(_max_total_tokens_budget * 0.65)
    _cumulative_chars: int = 0

    # ── 构建有效持仓代码集合（幻觉过滤用） ────────────
    _valid_codes: set[str] = set()
    if holdings_details:
        for _h in holdings_details:
            _code = _h.get("code", "")
            if _code:
                _valid_codes.add(str(_code))

    # ── Step 1: 白脸（Pro） ────────────────────────────
    _pro_cache_key = f"llm_debate_pro_{_fingerprint}"
    _session_pro_key = f"debate_pro_{_fingerprint}"
    pro_text = _check_session_cache(_session_pro_key)

    if pro_text is None and not force:
        pro_text = cache_get(_pro_cache_key, get_cache_ttl_llm("debate_pro"))

    if pro_text is None:
        pro_result = generate_llm_module(
            _lc,
            "expert_review",
            force=force,
            http_client=http_client,
            fingerprint_fn=lambda: f"{_fingerprint}_debate_pro",
            system_prompt_default=_SYSTEM_DEBATE_PRO,
            prompt_builder=lambda: _user,
            max_tokens_default=_max_tokens,
            timeout_default=_timeout,
            output_brief_limit=300,
            system_prompt=_SYSTEM_DEBATE_PRO,
            user_prompt=_user,
        )
        pro_text = pro_result[0] if pro_result and isinstance(pro_result, tuple) else None
        if pro_text:
            pro_text = _filter_hallucinated_codes(pro_text, _valid_codes)
            cache_set(_pro_cache_key, pro_text)
            _set_session_cache(_session_pro_key, pro_text)

    if not pro_text:
        logger.warning("[debate] 白脸生成失败，回退普通模式")
        return (None, None, None)

    # 追踪白脸 token 消耗
    _cumulative_chars += len(pro_text)
    logger.info("[debate] Token budget: 已用 %d chars（阈值 %d）", _cumulative_chars, _budget_char_threshold)

    # 超过 2× 预算：跳过所有 debate 调用，回退普通模式
    if _cumulative_chars > _budget_char_threshold * 2:
        logger.warning(
            "[debate] 超过 2× Token 预算（%d chars > %d），跳过所有 debate 调用",
            _cumulative_chars,
            _budget_char_threshold * 2,
        )
        return (None, None, None)

    # ── Step 2: 黑脸（Con） ────────────────────────────
    _con_cache_key = f"llm_debate_con_{_fingerprint}"
    _session_con_key = f"debate_con_{_fingerprint}"
    con_text = _check_session_cache(_session_con_key)

    if con_text is None and not force:
        con_text = cache_get(_con_cache_key, get_cache_ttl_llm("debate_con"))

    if con_text is None:
        con_result = generate_llm_module(
            _lc,
            "expert_review",
            force=force,
            http_client=http_client,
            fingerprint_fn=lambda: f"{_fingerprint}_debate_con",
            system_prompt_default=_SYSTEM_DEBATE_CON,
            prompt_builder=lambda: _user,
            max_tokens_default=_max_tokens,
            timeout_default=_timeout,
            output_brief_limit=300,
            system_prompt=_SYSTEM_DEBATE_CON,
            user_prompt=_user,
        )
        con_text = con_result[0] if con_result and isinstance(con_result, tuple) else None
        if con_text:
            con_text = _filter_hallucinated_codes(con_text, _valid_codes)
            cache_set(_con_cache_key, con_text)
            _set_session_cache(_session_con_key, con_text)

    if not con_text:
        logger.warning("[debate] 黑脸生成失败，回退普通模式")
        return (None, None, None)

    # 追踪黑脸 token 消耗
    _cumulative_chars += len(con_text)
    logger.info("[debate] Token budget: 已用 %d chars（阈值 %d）", _cumulative_chars, _budget_char_threshold)

    # 超过预算：跳过 synthesis，返回 pro+con 拼接
    if _cumulative_chars > _budget_char_threshold:
        logger.warning(
            "[debate] 超过 Token 预算（%d chars > %d），跳过 synthesis，返回 pro+con 拼接",
            _cumulative_chars,
            _budget_char_threshold,
        )
        return (pro_text, con_text, None)

    # ── Step 3: 综合（Synthesis） ──────────────────────
    _synthesis_user = _build_debate_synthesis_prompt(pro_text, con_text)
    _pro_digest = hashlib.sha256(pro_text[:200].encode()).hexdigest()[:8]
    _con_digest = hashlib.sha256(con_text[:200].encode()).hexdigest()[:8]
    _syn_fingerprint = f"{_fingerprint}_{_pro_digest}_{_con_digest}"
    _syn_cache_key = f"llm_debate_synthesis_{_syn_fingerprint}"
    _session_syn_key = f"debate_syn_{_syn_fingerprint}"
    synthesis_text = _check_session_cache(_session_syn_key)

    if synthesis_text is None and not force:
        synthesis_text = cache_get(_syn_cache_key, get_cache_ttl_llm("debate_synthesis"))

    if synthesis_text is None:
        synthesis_result = generate_llm_module(
            _lc,
            "expert_review",
            force=force,
            http_client=http_client,
            fingerprint_fn=lambda: f"{_fingerprint}_debate_syn_{_pro_digest}_{_con_digest}",
            system_prompt_default=_SYSTEM_DEBATE_SYNTHESIS,
            prompt_builder=lambda: _synthesis_user,
            max_tokens_default=_max_tokens,
            timeout_default=_timeout,
            output_brief_limit=300,
            system_prompt=_SYSTEM_DEBATE_SYNTHESIS,
            user_prompt=_synthesis_user,
        )
        synthesis_text = synthesis_result[0] if synthesis_result and isinstance(synthesis_result, tuple) else None
        if synthesis_text:
            synthesis_text = _filter_hallucinated_codes(synthesis_text, _valid_codes)
            cache_set(_syn_cache_key, synthesis_text)
            _set_session_cache(_session_syn_key, synthesis_text)

    if not synthesis_text:
        logger.warning("[debate] 综合生成失败，返回 pro+con 拼接")
        return (pro_text, con_text, None)

    return (pro_text, con_text, synthesis_text)
