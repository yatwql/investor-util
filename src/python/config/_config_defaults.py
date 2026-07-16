"""默认配置与模板 — _DEFAULT_CONFIG、模板生成、路径常量。"""
from __future__ import annotations

import json

from src.python.registry import get_cache_ttl_defaults

# 配置文件路径
_CONFIG_FILE = "data/config/config.json"

# 默认配置（按业务分组排列顺序，与模板 _get_default_config_template() 一致）
_DEFAULT_CONFIG = {
    # ── A. 路径与文件 ──
    "holdings_dir": "data/holdings",
    "holdings_filename": "个人投资持仓信息.xlsx",
    "output_dir": "reports",
    "llm_key_file": "data/config/llm_key.json",
    "llm_settings_file": "data/config/llm_settings.json",
    # ── B. 板块可见性（关闭后对应页签/章节完全隐藏） ──
    "enable_b_series": True,    # B 系列基金深度分析（#6~9）
    "enable_news": True,        # 新闻与预警（#10~11）
    "enable_history": True,     # 历史走势+回撤分析（#16~17）
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
    "early_warning": {
        "sector_alert_threshold_warning": -50_000_000,
        "sector_alert_threshold_danger": -200_000_000,
        "sentiment_top_n": 10,
    },
    "degradation": {
        "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},
        "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},
        "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14},
    },
    # ── F. 业绩基准 ──
    "user_fund_benchmarks": {},
    # ── G. 持仓快照 ──
    "history": {
        "analysis": "off",
        "snapshot_retention_days": 60,
        "snapshot_max_count": 365,
        "coverage_threshold": 0.8,
        "benchmark_indices": {"sh000300": "沪深300", "gb_inx": "标普500"},
    },
}


def get_config_path() -> str:
    """返回配置文件路径。"""
    return _CONFIG_FILE


def _get_default_config_template() -> str:
    """返回带分组注释的默认 config.json 模板字符串。

    与 _DEFAULT_CONFIG 保持语义一致，首次创建 config.json 时写入。
    使用 ``//`` 注释分组，由 _strip_json_comments() 剥离后解析。
    """
    ttl_json = json.dumps(get_cache_ttl_defaults(), ensure_ascii=False, indent=2)
    lines = ttl_json.split("\n")
    indented_ttl = "\n".join([lines[0]] + ["  " + line for line in lines[1:]])
    return (
        '{\n'
        '  // ── A. 路径与文件 ──\n'
        '  "holdings_dir": "data/holdings",\n'
        '  "holdings_filename": "个人投资持仓信息.xlsx",\n'
        '  "output_dir": "reports",\n'
        '  "llm_key_file": "data/config/llm_key.json",\n'
        '  "llm_settings_file": "data/config/llm_settings.json",\n'
        '\n'
        '  // ── B. 板块可见性（关闭后对应页签/章节完全隐藏）──\n'
        '  "enable_b_series": true,\n'
        '  "enable_news": true,\n'
        '  "enable_history": true,\n'
        '\n'
        '  // ── C. 数据源与提供商 ──\n'
        '  "news_top_count": 300,\n'
        '  "news_sources": {\n'
        '    "sina": true,\n'
        '    "eastmoney": true,\n'
        '    "cls": false,\n'
        '    "wallstreetcn": true,\n'
        '    "akshare": true\n'
        '  },\n'
        '  "preferred_provider": {},\n'
        '\n'
        '  // ── D. 市场时段与缓存 ──\n'
        '  "market_hour_aware": ["price", "index"],\n'
        '  "market_hour_ttl": 30,\n'
        '  "market_hours": {\n'
        '    "start": "09:30",\n'
        '    "end": "15:00",\n'
        '    "official_source": true\n'
        '  },\n'
        f'  "cache_ttl": {indented_ttl},\n'
        '\n'
        '  // ── E. 行为调优 ──\n'
        '  "default_menu_key": "L",\n'
        '  "report_section_order": {},\n'
        '  "early_warning": {\n'
        '    "sector_alert_threshold_warning": -50000000,\n'
        '    "sector_alert_threshold_danger": -200000000,\n'
        '    "sentiment_top_n": 10\n'
        '  },\n'
        '  "degradation": {\n'
        '    "t2": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 3},\n'
        '    "t3": {"unreachable_threshold": 2, "empty_data_threshold": 3, "stale_days": 14},\n'
        '    "t4": {"unreachable_threshold": 1, "empty_data_threshold": 1, "stale_days": 14}\n'
        '  },\n'
        '\n'
        '  // ── F. 业绩基准 ──\n'
        '  "user_fund_benchmarks": {},\n'
        '\n'
        '  // ── G. 组合历史走势与持仓快照 ──\n'
        '  "history": {\n'
        '    "analysis": "off",\n'
        '    "snapshot_retention_days": 60,\n'
        '    "snapshot_max_count": 365,\n'
        '    "coverage_threshold": 0.8,\n'
        '    "benchmark_indices": {"sh000300": "沪深300", "gb_inx": "标普500"}\n'
        '  }\n'
        '}\n'
    )
