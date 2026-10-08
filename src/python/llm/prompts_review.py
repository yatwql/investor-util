"""LLM 复盘与自审提示词（语义名 prompts_review）— 自审/持仓变动复盘 system prompt 与构建器。

自 prompts_core 按职责下沉（复盘域）；prompts_core 门面 re-export，导入面不变。
"""

from __future__ import annotations

from src.python.config.anonymizer import mask_holding_code


_SYSTEM_SELF_REVIEW = """你是严格的投资复盘内容复核员。你会收到同一次报告中若干个分析模块的产出文本，
以及持仓/穿透数据摘要。你的唯一任务是**复核这些产出与数据是否自洽**，而不是重新做一遍分析。

## 必须输出的固定条目（缺一条即视为不合格输出）

【自检清单】
1. 结论与数据是否矛盾：逐条列出发现的矛盾（引用原文片段 + 说明与哪项数据冲突）；未发现时写「未发现」。
2. 未标注的推测性表述：列出把推测当作事实陈述、或未标注不确定性的表述（引用原文片段）；未发现写「未发现」。
3. 模块间结论是否互斥：指出相互冲突的结论对；未发现写「未发现」。

## 硬性禁止（违反即为无效输出）

- **禁止给出任何投资建议、买卖方向、目标价、仓位建议**——你只复核，不提供建议。
- **禁止新增数据、数值或排名**：只能引用你收到的文本与摘要中的既有信息；不确定就写「无法核实」。
- **禁止声称已"校验无误"或给出质量评分**：你只报告发现，不下结论性背书。
- 不得复述原文全文，只引用必要片段（每条不超过 40 字）。

输出为 Markdown，只输出上述清单，不要寒暄、不要总结段落。"""


def _build_self_review_prompt(
    module_outputs: dict | None,
    holdings_details: list | None = None,
    penetrated_assets: list | None = None,
    per_module_limit: int = 4000,
) -> str:
    """构造自检 user prompt：各模块产出（截断）+ 数据摘要（比对基准）。

    Args:
        module_outputs: 模块名 → HTML 产出文本（None/空串跳过）。
        holdings_details: 持仓明细。
        penetrated_assets: 穿透资产列表。
        per_module_limit: 单个模块文本的字符上限（防止 prompt 无限膨胀）。

    Returns:
        自检 user prompt。
    """
    lines: list[str] = ["以下是本次报告的各模块分析产出（已截断），请按系统提示要求复核。", ""]
    for key, text in (module_outputs or {}).items():
        if not isinstance(text, str) or not text.strip():
            continue
        plain = _strip_html_for_review(text)
        if len(plain) > per_module_limit:
            plain = plain[:per_module_limit] + "…（已截断）"
        lines.append(f"### 模块：{key}")
        lines.append(plain)
        lines.append("")

    lines.append("### 持仓数据摘要")
    lines.append(_self_review_holdings_digest(holdings_details))
    lines.append("")
    lines.append("### 穿透资产摘要")
    lines.append(_self_review_penetration_digest(penetrated_assets))
    return "\n".join(lines)


def _strip_html_for_review(text: str) -> str:
    """粗略剥离 HTML 标签与实体，供自检比对（不追求完美，够用即可）。"""
    import re

    plain = re.sub(r"<[^>]+>", " ", text)
    plain = plain.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t]+", " ", plain).strip()


def _self_review_holdings_digest(holdings_details: list | None) -> str:
    """持仓比对基准：名称/代码/市值/盈亏/占比（每行一条，截断至 40 行）。"""
    if not holdings_details:
        return "（无持仓明细）"
    rows: list[str] = []
    for d in holdings_details[:40]:
        get = d.get if isinstance(d, dict) else lambda k, _d=d: getattr(_d, k, None)
        rows.append(
            "- {name}({code}) 市值 {mv} 盈亏 {profit} 占比 {ratio}".format(
                name=get("name") or "?",
                code=mask_holding_code(get("code")) or "?",
                mv=get("market_value") if get("market_value") is not None else get("mv"),
                profit=get("profit"),
                ratio=get("weight_pct") if get("weight_pct") is not None else get("ratio_pct"),
            )
        )
    return "\n".join(rows)


def _self_review_penetration_digest(penetrated_assets: list | None) -> str:
    """穿透比对基准：资产名 + 占比（截断至 20 行）。"""
    if not penetrated_assets:
        return "（无穿透数据）"
    rows: list[str] = []
    for a in penetrated_assets[:20]:
        if not isinstance(a, dict):
            continue
        rows.append(f"- {a.get('name', '?')} 占比 {a.get('ratio_pct', '?')}%")
    return "\n".join(rows) or "（无穿透数据）"


# ── 持仓变动复盘归因（章内 LLM 归因块） ──────────────────

_SYSTEM_HOLDING_CHANGE_REVIEW = """你是投资复盘分析师，负责对「持仓变动复盘」的结构化事实做归因说明。

你会收到：快照差分得到的变动事件清单（**区间净额推断、非逐笔**）+ 指标汇总（变动频率/结构计数/区间贡献分解/意图对账）+ 窗口内历史信号清单。你的任务是解释"这段时间持仓为什么变成这样"，只做结构级归因。

## 归因框架（按序排查，命中即写明依据）

1. **账户/数据结构变更（优先排查）**：事实清单含"疑似账户结构重排"标注，或出现同日跨品种清仓 + 次日同名新增、单日过桥持仓（当日新增次日清仓）——这类形态是账户/份额数据结构变更而非真实调仓，必须单独说明，**不得当作战绩、主动调仓或择时解读**。
2. **信号/决策对应**：与意图对账的"一致/分歧"行及窗口内历史信号对照——有明确决策记录或信号指向的变动，说明其对应关系；"分歧"行要指出差异点。
3. **指数/行业被动跟随**：触及品种集中在同一指数/行业且同日同向变动——按被动跟随/资金申赎驱动解读。
4. **无法归因**：以上均不成立时明确写"无法从现有数据判定成因"，并说明缺口（如缺逐笔成交、缺决策记录）。

## 硬性禁止（违反即为无效输出）

- **禁止给出任何投资建议、买卖方向、目标价、仓位建议**。
- **禁止编造清单之外的数据**：成交日期、成交价格、费用、逐笔数量一概不得出现（区间净额推断不含这些维度）；引用数字只能来自收到的事实清单。
- **禁止输出持仓健康度评价或后市判断**——你只归因已发生的变动。
- 不得复述清单全文，只引用必要片段（每条不超过 40 字）。

输出为 Markdown：以「## 持仓变动归因」开头，3~5 个要点段（每段先给结论再给依据）；最后一段固定以「口径与局限：」开头，写明"事件为区间净额推断（非逐笔），不含成交日期/单价/费用；分红再投与份额折算混入份额变动"。不要寒暄。"""


def _build_holding_change_review_prompt(context_block: str, signal_block: str = "") -> str:
    """构造持仓变动复盘归因 user prompt：事实块 + 窗口信号对账块。

    Args:
        context_block: 契约 ``prompt_block``（报告展示与 LLM 同源渲染的事件清单）。
        signal_block: 窗口内历史信号清单（可为空——信号功能关闭时附录零贡献）。

    Returns:
        user prompt 文本。
    """
    lines = [
        "以下是本期「持仓变动复盘」的结构化事实（快照差分，区间净额推断、非逐笔），",
        "请按系统提示的归因框架输出。",
        "",
        context_block or "（变动事实块缺席）",
    ]
    if signal_block:
        lines.append("")
        lines.append(signal_block)
    return "\n".join(lines)
