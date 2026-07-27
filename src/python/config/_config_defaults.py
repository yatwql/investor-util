"""默认配置与模板 — _DEFAULT_CONFIG、模板生成、路径常量。"""

from __future__ import annotations

import json
import os

from src.python.constants import PROJECT_ROOT
from src.python.registry import get_cache_ttl_defaults

# 配置文件路径（支持 CLI --config 覆写），始终以项目根目录为基准
_CONFIG_FILE = os.path.join(PROJECT_ROOT, "data/config/config.json")
_CONFIG_PATH_OVERRIDE: str | None = None


def set_config_path_override(path: str) -> None:
    """设置配置文件路径覆写（CLI --config 使用）。"""
    global _CONFIG_PATH_OVERRIDE
    _CONFIG_PATH_OVERRIDE = path


def get_config_path() -> str:
    """返回配置文件路径（优先返回覆写路径）。"""
    return _CONFIG_PATH_OVERRIDE or _CONFIG_FILE


# 默认配置（按业务分组排列顺序，与模板 _get_default_config_template() 一致）
_PATH_KEYS = frozenset({"holdings_dir", "output_dir", "llm_settings_file", "llm_key_file", "llm_providers_file"})

_DEFAULT_CONFIG = {
    # ── A. 路径与文件 ──
    # 以下路径型键使用绝对路径，使配置不依赖 CWD；holdings_filename 是纯文件名，保持相对
    "holdings_dir": os.path.join(PROJECT_ROOT, "data/holdings"),
    "holdings_filename": "个人投资持仓信息.xlsx",
    "output_dir": os.path.join(PROJECT_ROOT, "reports"),
    "llm_settings_file": os.path.join(PROJECT_ROOT, "data/config/llm_settings.json"),
    "llm_key_file": os.path.join(PROJECT_ROOT, "data/config/llm_key.json"),
    "llm_providers_file": os.path.join(PROJECT_ROOT, "data/config/llm_providers.json"),
    # ── B. 报告章节可见性 ──
    "enable_b_series": True,  # 基金深度分析（#6~9）
    "enable_news": True,  # 市场新闻（#10）
    "enable_history": True,  # 组合历史走势+回撤（#16~17）
    # ── C. 数据源与提供商 ──
    "news_top_count": 300,
    "news_sources": {
        "sina": True,
        "eastmoney": True,
        "cls": False,
        "wallstreetcn": True,
        "akshare": True,
    },
    "preferred_provider": {},
    # ── D. 市场时段与缓存 ──
    "market_hour_aware": ["price", "index"],
    "market_hour_ttl": 30,
    "market_hours": {
        "start": "09:30",
        "end": "15:00",
        "official_source": True,
    },
    "cache_ttl": get_cache_ttl_defaults(),
    # ── E. 行为调优 ──
    "default_menu_key": "L",
    "report_section_order": {},
    "degradation": {
        "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},
        "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},
        "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14},
    },
    # ── F. 业绩基准与无风险利率 ──
    "risk_free_rate": None,  # Rf 手动配置（None=自动获取，填小数如0.0174或百分比如1.74）
    "user_fund_benchmarks": {},
    # 竞争语境对比指数池（默认沪深300+中证500+中证全债）
    "comparison_indices": {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"},
    # ── G. 持仓快照 ──
    "history": {
        "analysis": "off",
        "snapshot_retention_days": 60,
        "snapshot_max_count": 365,
        "coverage_threshold": 0.8,
        "benchmark_indices": {"sh000300": "沪深300"},
    },
    # ── H. 再平衡配置 ──
    "rebalance": {
        "threshold": 0.15,  # 单品种权重超限阈值（默认 15%）
        "deviation_threshold": 0.05,  # 大类/品种配置偏离阈值（默认 5%）
        "profile": "moderate",  # 预设阈值集: conservative / moderate / aggressive / custom
        "silence_days": 30,  # 再平衡信号静默期天数（默认 30 天）
        "target_allocation": {},  # 目标配置 Schema（空=不启用目标配置检查）
        "equity_fixed_income": {},  # 权益/固收超大类目标配置（空=不启用）
    },
    # ── I. 流动性配置 ──
    "redemption_limits": {},  # 场外基金单日赎回上限（code → 金额，空=未配置）
    # ── J. 匿名化配置 ──
    "anonymization": {"mode": "off"},  # 匿名化模式：off/code_display/full_anonymous/summary
}


def _get_default_config_template() -> str:
    """返回带分组注释的默认 config.json 模板字符串。

    与 _DEFAULT_CONFIG 保持语义一致，首次创建 config.json 时写入。
    使用 ``//`` 注释分组，由 _strip_json_comments() 剥离后解析。
    """
    ttl_json = json.dumps(get_cache_ttl_defaults(), ensure_ascii=False, indent=2)
    lines = ttl_json.split("\n")
    indented_ttl = "\n".join([lines[0]] + ["  " + line for line in lines[1:]])
    return (
        "{\n"
        "  // ── A. 路径与文件 ──\n"
        '  "holdings_dir": "data/holdings",\n'
        '  "holdings_filename": "个人投资持仓信息.xlsx",\n'
        '  "output_dir": "reports",\n'
        '  "llm_settings_file": "data/config/llm_settings.json",\n'
        '  "llm_key_file": "data/config/llm_key.json",\n'
        '  "llm_providers_file": "data/config/llm_providers.json",\n'
        "\n"
        "  // ── B. 报告可选章节（关闭后对应页签/章节完全隐藏）──\n"
        '  "enable_b_series": true,  // 基金深度分析（#6~9）\n'
        '  "enable_news": true,  // 市场新闻（#10）\n'
        '  "enable_history": true,  // 组合历史走势+回撤（#16~17）\n'
        "\n"
        "  // ── C. 数据源与提供商 ──\n"
        '  "news_top_count": 300,\n'
        '  "news_sources": {\n'
        '    "sina": true,\n'
        '    "eastmoney": true,\n'
        '    "cls": false,\n'
        '    "wallstreetcn": true,\n'
        '    "akshare": true\n'
        "  },\n"
        '  "preferred_provider": {},\n'
        "\n"
        "  // ── D. 市场时段与缓存 ──\n"
        '  "market_hour_aware": ["price", "index"],\n'
        '  "market_hour_ttl": 30,\n'
        '  "market_hours": {\n'
        '    "start": "09:30",\n'
        '    "end": "15:00",\n'
        '    "official_source": true\n'
        "  },\n"
        f'  "cache_ttl": {indented_ttl},\n'
        "\n"
        "  // ── E. 行为调优 ──\n"
        '  "default_menu_key": "L",\n'
        '  "report_section_order": {},\n'
        '  "degradation": {\n'
        '    "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},\n'
        '    "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},\n'
        '    "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14}\n'
        "  },\n"
        "\n"
        "  // ── F. 业绩基准与无风险利率 ──\n"
        '  "risk_free_rate": null,\n'
        '  "user_fund_benchmarks": {},\n'
        '  "comparison_indices": {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"},\n'
        "\n"
        "  // ── G. 组合历史走势与持仓快照 ──\n"
        '  "history": {\n'
        '    "analysis": "off",\n'
        '    "snapshot_retention_days": 60,\n'
        '    "snapshot_max_count": 365,\n'
        '    "coverage_threshold": 0.8,\n'
        '    "benchmark_indices": {"sh000300": "沪深300"}\n'
        "  },\n"
        "\n"
        "  // ── H. 再平衡配置 ──\n"
        '  "rebalance": {\n'
        '    "threshold": 0.15,\n'
        '    "deviation_threshold": 0.05,\n'
        '    "profile": "moderate",\n'
        '    "silence_days": 30,\n'
        '    "target_allocation": {},\n'
        '    "equity_fixed_income": {}\n'
        "  },\n"
        "\n"
        "  // ── I. 流动性配置 ──\n"
        '  "redemption_limits": {},\n'
        "\n"
        "  // ── J. 匿名化配置 ──\n"
        '  "anonymization": {\n'
        '    "mode": "off"\n'
        "  }\n"
        "}\n"
    )
