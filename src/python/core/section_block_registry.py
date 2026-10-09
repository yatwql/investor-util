"""章节区块注册表 — 双端（HTML/Excel）章内区块清单的单一真值。

矩阵口径（`technical.md` §4.22 与 `check-doc-drift` 第 17 项同源）：每个报告
章节的区块级清单以本注册表为准，`report/section_block_extraction.py` 按同一
归一化口径从 HTML partial 源与 Excel 写入器提取实际区块，三向对账（文档矩阵
↔ 注册表 ↔ 实现），任一端增删/改名在提交前暴露。

命名约定：
- 清单内为**归一化区块名**（去 HTML 标签、去序号头 `一、`/`①`、去括号段、
  去【】外框），与两端展示文案解耦；`html`/`excel` 为 ``None`` 表示该端无区块
  （HTML 流式章 / Excel 单表章），两端都为 ``None`` 的章节仍登记条目以保证
  键集与章节注册表双向一致。
- ``partials`` / ``modules`` 为区块提取载体（HTML partial 文件名、Excel 写入
  器模块文件名，多载体按矩阵「载体」列同序登记）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionBlockSpec:
    """单章节双端区块契约。

    Attributes:
        html: HTML 端归一化区块名清单（None = 该端无区块）。
        excel: Excel 端归一化区块名清单（None = 该端无区块）。
        partials: HTML 载体 partial 文件名（顺序随矩阵载体列）。
        modules: Excel 载体写入器模块文件名（顺序随矩阵载体列）。
    """

    html: tuple[str, ...] | None = None
    excel: tuple[str, ...] | None = None
    partials: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()

    @classmethod
    def both(
        cls,
        names: tuple[str, ...],
        *,
        partials: tuple[str, ...],
        modules: tuple[str, ...],
    ) -> SectionBlockSpec:
        """双端同名区块清单（区块对等章节）。"""
        return cls(html=names, excel=names, partials=partials, modules=modules)

    @classmethod
    def excel_only(
        cls,
        names: tuple[str, ...],
        *,
        partials: tuple[str, ...],
        modules: tuple[str, ...],
    ) -> SectionBlockSpec:
        """HTML 端无区块（流式/直排）而 Excel 端有子块的章节。"""
        return cls(html=None, excel=names, partials=partials, modules=modules)

    @classmethod
    def none(
        cls,
        *,
        partials: tuple[str, ...],
        modules: tuple[str, ...],
    ) -> SectionBlockSpec:
        """双端皆无区块（单表章 / 流式且无条件块）。"""
        return cls(partials=partials, modules=modules)


SECTION_BLOCK_SPECS: dict[str, SectionBlockSpec] = {
    "summary": SectionBlockSpec.excel_only(
        ("持仓概况", "盈亏汇总", "市场温度", "市场指数"),
        partials=("summary_section.html",),
        modules=("summary.py",),
    ),
    "holdings_detail": SectionBlockSpec.both(
        ("市值核算明细", "持仓分类汇总"),
        partials=("holdings_detail_section.html",),
        modules=("holdings_detail_sheet.py",),
    ),
    "penetration": SectionBlockSpec.none(
        partials=("penetration_section.html",),
        modules=("penetration_sheet.py",),
    ),
    "fund_performance": SectionBlockSpec.both(
        ("候选基金比较", "基金经理变更监控"),
        partials=("fund_performance_section.html",),
        modules=("fund_performance.py",),
    ),
    "position_structure": SectionBlockSpec.both(
        ("持仓重合度矩阵", "持仓相关性矩阵", "持仓集中度监控"),
        partials=("position_structure_section.html",),
        modules=("position_structure_sheet.py",),
    ),
    "style_factor": SectionBlockSpec.both(
        ("基金风格表", "风格因子回归", "行业 Beta", "因子目录"),
        partials=("style_factor_section.html",),
        modules=("style_factor_sheet.py",),
    ),
    "action": SectionBlockSpec.both(
        (
            "再平衡信号",
            "交易纪律",
            "调仓建议清单",
            "收益归因",
            "历史决策复盘",
            "景气度框架诊断",
            "市场情绪与持仓热点",
        ),
        partials=("action_section.html",),
        modules=("action_sheet.py",),
    ),
    "news_correlation": SectionBlockSpec.both(
        ("事件窗量化对照", "事件窗对照表"),
        partials=("news_correlation_section.html", "event_impact_section.html"),
        modules=("news_correlation.py", "event_impact_panel.py"),
    ),
    # LLM 流式章：事实校验块为内容内嵌（无标题行），双端皆无区块契约
    "global_macro": SectionBlockSpec.none(
        partials=("global_macro_section.html",),
        modules=("llm_content.py",),
    ),
    "expert_review": SectionBlockSpec.none(
        partials=("expert_review_section.html",),
        modules=("llm_content.py",),
    ),
    "health_check": SectionBlockSpec.none(
        partials=("health_check_section.html",),
        modules=("llm_content.py",),
    ),
    "penetration_deep": SectionBlockSpec.none(
        partials=("penetration_deep_section.html",),
        modules=("llm_content.py",),
    ),
    "portfolio_history_drawdown": SectionBlockSpec.both(
        ("走势表", "回撤矩阵", "危机区间标注", "月度收益日历"),
        partials=("portfolio_history_drawdown_section.html",),
        modules=("portfolio_history_drawdown_sheet.py",),
    ),
    "portfolio_evolution": SectionBlockSpec.both(
        ("自上次快照变化摘要", "总市值与总盈亏趋势", "持仓集中度趋势", "TOP 持仓占比变迁", "账户配置流"),
        partials=("evolution_section.html",),
        modules=("evolution_sheet.py",),
    ),
    "holding_change": SectionBlockSpec.both(
        ("变动事件清单", "频率与结构演变", "意图对账", "变动动因 LLM 归因"),
        partials=("holding_change_section.html",),
        modules=("holding_change_panel.py",),
    ),
    "schedule_replay": SectionBlockSpec.both(
        ("纪律回放 vs 买入持有", "规则 A 逐期调仓与成本"),
        partials=("schedule_replay_section.html",),
        modules=("schedule_replay_panel.py",),
    ),
    "data_source_status": SectionBlockSpec.excel_only(
        ("源健康", "数据源说明", "品种覆盖", "可信度"),
        partials=("data_source_status_section.html",),
        modules=("data_quality_sheet.py",),
    ),
    "fundamental_snapshot": SectionBlockSpec.both(
        ("财务指标", "持仓个股财报摘要"),
        partials=("fundamental_snapshot_section.html",),
        modules=("fundamental_snapshot_sheet.py",),
    ),
    "llm_usage": SectionBlockSpec.none(
        partials=("llm_usage_section.html",),
        modules=("excel_llm_usage.py",),
    ),
}


def get_section_block_spec(key: str) -> SectionBlockSpec:
    """按章节 key 取双端区块契约；未登记章节抛 KeyError。"""
    return SECTION_BLOCK_SPECS[key]
