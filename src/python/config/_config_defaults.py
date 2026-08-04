"""默认配置与模板 — _DEFAULT_CONFIG、模板生成、路径常量。"""

from __future__ import annotations

import json
import os

from src.python.config._validation import _deabsolutize_paths
from src.python.core.constants import PROJECT_ROOT
from src.python.core.registry import get_cache_ttl_defaults

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
    "enable_fund_deep_analysis": True,  # 基金深度分析+因子暴露+相关性
    "enable_news": True,  # 市场新闻
    "enable_history": True,  # 组合历史走势+回撤
    "enable_portfolio_evolution": True,  # 组合演进
    "enable_action": False,  # 行动建议独立章（再平衡信号+交易纪律+调仓建议+收益归因，默认关）
    # 报告子模块开关（新增能力默认关闭，避免既有报告突然"变胖"）
    "report_submodules": {
        "data_quality": False,  # 「数据源可用性矩阵」→「数据质量仪表盘」（源健康+品种覆盖）
        "industry_beta": False,  # 「风格与因子分析」→ 行业 Beta 子表（穿透行业暴露占比 + 行业指数 β）
        "candidate_compare": False,  # 「基金业绩分析」→ 候选基金比较子表（候选来自 comparison_candidates）
    },
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
    "comparison_candidates": [],  # 候选基金比较子表候选（6 位基金代码列表，≤10；与 report_submodules.candidate_compare 配合）
    # ── G. 持仓快照 ──
    "history": {
        "fetch_mode": "auto",  # 历史走势获取模式: off=关闭 / prompt=报告后询问 / auto=自动获取
        # 历史走势取数窗口（K 线条数/交易日），需 ≥ drawdown MIN_SPAN(60) 才能计算回撤分析
        "lookback_days": 90,
        "snapshot_retention_days": 60,
        "snapshot_max_count": 365,
        "coverage_threshold": 0.8,
        "benchmark_indices": {"sh000300": "沪深300"},
    },
    # ── H. 业绩评价配置 ──
    "performance_evaluation": {
        "excess_threshold_up": 80,  # 超额收益 ≥ 此值 → 评级上调一级
        "excess_threshold_down": 40,  # 超额收益 < 此值 → 评级下调一级
    },
    # ── I. 再平衡配置 ──
    "rebalance": {
        "threshold": 0.15,  # 单品种权重超限阈值（默认 15%）
        "deviation_threshold": 0.05,  # 大类/品种配置偏离阈值（默认 5%）
        "profile": "moderate",  # 预设阈值集: conservative / moderate / aggressive / custom
        "silence_days": 30,  # 再平衡信号静默期天数（默认 30 天）
        "target_allocation": {},  # 目标配置 Schema（空=不启用目标配置检查）
        "equity_fixed_income": {},  # 权益/固收超大类目标配置（空=不启用）
    },
    # ── I2. 交易纪律配置 ──
    "discipline": {
        "take_profit_pct": 20.0,  # 止盈线：单品种收益率 ≥ 此值 → 建议部分止盈
        "stop_loss_pct": -15.0,  # 止损线：单品种收益率 ≤ 此值 → 建议止损/减仓
        "drawdown_pct": -10.0,  # 回撤线：组合相对历史峰值回撤 ≥ 此绝对值 → 建议控回撤
        "silence_days": 30,  # 交易纪律信号静默期天数（默认 30 天）
    },
    # ── J. 流动性配置 ──
    "redemption_limits": {},  # 场外基金单日赎回上限（code → 金额，空=未配置）
    # ── K. 匿名化配置 ──
    "anonymization": {"mode": "off"},  # 匿名化模式：off/code_display/full_anonymous/summary
    # ── L. 批量并行调度 ──
    "batch": {
        "max_total_workers": 15,  # 全局 batch 线程硬上限（已有池不计入）
        "fund_workers": 3,  # 基金排名/持仓批量并发数
        "industry_workers": 8,  # 行业分类批量并发数
    },
    "batch_rate_limit": {  # Provider 级别请求间隔（秒），0=不限速
        "tencent": 0.0,
        "sina": 0.0,
        "eastmoney": 0.1,
        "tiantian": 0.5,
        "eastmoney_industry": 0.05,
    },
}


def _get_default_config_template() -> str:
    """返回带分组注释的默认 config.json 模板字符串。

    从 _DEFAULT_CONFIG 自动生成，确保值与代码定义一致。
    首次创建 config.json 时写入。使用 ``//`` 注释分组，
    由 _strip_json_comments() 剥离后解析。
    """
    return _build_template_from_defaults()


def _build_template_from_defaults() -> str:
    """从 _DEFAULT_CONFIG 生成带注释的 JSON 模板。

    模板中路径型键写相对路径（可移植，跨机器友好）；运行时由
    _absolutize_paths() 绝对化。_DEFAULT_CONFIG 内存值保持绝对路径。
    """
    # 浅拷贝后反绝对化：仅改顶层路径键，不污染 _DEFAULT_CONFIG
    d = dict(_DEFAULT_CONFIG)
    _deabsolutize_paths(d)
    parts = [
        "{",
        # ── A ──
        "  // ── A. 路径与文件 ──",
        f'  "holdings_dir": {json.dumps(d["holdings_dir"])},',
        f'  "holdings_filename": {json.dumps(d["holdings_filename"], ensure_ascii=False)},',
        f'  "output_dir": {json.dumps(d["output_dir"])},',
        f'  "llm_settings_file": {json.dumps(d["llm_settings_file"])},',
        f'  "llm_key_file": {json.dumps(d["llm_key_file"])},',
        f'  "llm_providers_file": {json.dumps(d["llm_providers_file"])},',
        "",
        # ── B ──
        "  // ── B. 报告可选章节（关闭后对应页签/章节完全隐藏）──",
        f'  "enable_fund_deep_analysis": {json.dumps(d["enable_fund_deep_analysis"])},  // 基金深度分析+因子暴露+相关性',
        f'  "enable_news": {json.dumps(d["enable_news"])},  // 市场新闻',
        f'  "enable_history": {json.dumps(d["enable_history"])},  // 组合历史走势+回撤',
        f'  "enable_portfolio_evolution": {json.dumps(d["enable_portfolio_evolution"])},  // 组合演进',
        f'  "enable_action": {json.dumps(d["enable_action"])},  // 行动建议独立章（决策行动，默认关）',
        '  // 报告子模块开关（新增能力默认关闭，避免既有报告突然"变胖"）',
        f'  "report_submodules": {json.dumps(d["report_submodules"], ensure_ascii=False)},  // 数据质量仪表盘默认关',
        "",
        # ── C ──
        "  // ── C. 数据源与提供商 ──",
        f'  "news_top_count": {json.dumps(d["news_top_count"])},',
        f'  "news_sources": {json.dumps(d["news_sources"], ensure_ascii=False)},',
        f'  "preferred_provider": {json.dumps(d["preferred_provider"])},',
        "",
        # ── D ──
        "  // ── D. 市场时段与缓存 ──",
        f'  "market_hour_aware": {json.dumps(d["market_hour_aware"])},',
        f'  "market_hour_ttl": {json.dumps(d["market_hour_ttl"])},',
        f'  "market_hours": {json.dumps(d["market_hours"], indent=2).replace(chr(10), chr(10) + "  ")},',
        f'  "cache_ttl": {json.dumps(d["cache_ttl"], ensure_ascii=False, indent=2).replace(chr(10), chr(10) + "  ")},',
        "",
        # ── E ──
        "  // ── E. 行为调优 ──",
        f'  "default_menu_key": {json.dumps(d["default_menu_key"])},',
        f'  "report_section_order": {json.dumps(d["report_section_order"])},',
        f'  "degradation": {json.dumps(d["degradation"], indent=2).replace(chr(10), chr(10) + "  ")},',
        "",
        # ── F ──
        "  // ── F. 业绩基准与无风险利率 ──",
        f'  "risk_free_rate": {json.dumps(d["risk_free_rate"])},  // Rf 手动配置（None=自动获取，填小数如0.0174或百分比如1.74）',
        f'  "user_fund_benchmarks": {json.dumps(d["user_fund_benchmarks"])},',
        "  // 竞争语境对比指数池（默认沪深300+中证500+中证全债）",
        f'  "comparison_indices": {json.dumps(d["comparison_indices"], ensure_ascii=False)},',
        "  // 候选基金比较子表候选（6 位基金代码列表，≤10；与 report_submodules.candidate_compare 配合）",
        f'  "comparison_candidates": {json.dumps(d["comparison_candidates"])},',
        "",
        # ── G ──
        "  // ── G. 组合历史走势与持仓快照 ──",
        '  "history": {',
        f'    "fetch_mode": {json.dumps(d["history"]["fetch_mode"])},  // 历史走势获取模式: off=关闭 / prompt=报告后询问 / auto=自动获取',
        f'    "lookback_days": {d["history"]["lookback_days"]},  // 历史走势取数窗口（K 线条数/交易日），需≥60（回撤分析最少交易日）才计算回撤分析，上限 365',
        f'    "snapshot_retention_days": {d["history"]["snapshot_retention_days"]},',
        f'    "snapshot_max_count": {d["history"]["snapshot_max_count"]},',
        f'    "coverage_threshold": {d["history"]["coverage_threshold"]},',
        f'    "benchmark_indices": {json.dumps(d["history"]["benchmark_indices"], ensure_ascii=False, indent=2).replace(chr(10), chr(10) + "    ")}',
        "  },",
        "",
        # ── H ──
        "  // ── H. 业绩评价配置 ──",
        '  "performance_evaluation": {',
        f'    "excess_threshold_up": {d["performance_evaluation"]["excess_threshold_up"]},  // 超额收益 ≥ 此值 → 评级上调一级',
        f'    "excess_threshold_down": {d["performance_evaluation"]["excess_threshold_down"]}  // 超额收益 < 此值 → 评级下调一级',
        "  },",
        "",
        # ── I ──
        "  // ── I. 再平衡配置 ──",
        '  "rebalance": {',
        f'    "threshold": {d["rebalance"]["threshold"]},  // 单品种权重超限阈值（默认 15%）',
        f'    "deviation_threshold": {d["rebalance"]["deviation_threshold"]},  // 大类/品种配置偏离阈值（默认 5%）',
        f'    "profile": {json.dumps(d["rebalance"]["profile"])},  // 预设阈值集: conservative / moderate / aggressive / custom',
        f'    "silence_days": {d["rebalance"]["silence_days"]},  // 再平衡信号静默期天数（默认 30 天）',
        f'    "target_allocation": {json.dumps(d["rebalance"]["target_allocation"])},  // 目标配置 Schema（空=不启用目标配置检查）',
        f'    "equity_fixed_income": {json.dumps(d["rebalance"]["equity_fixed_income"])}  // 权益/固收超大类目标配置（空=不启用）',
        "  },",
        "",
        # ── I2 ──
        "  // ── I2. 交易纪律配置 ──",
        '  "discipline": {',
        f'    "take_profit_pct": {d["discipline"]["take_profit_pct"]},  // 止盈线：单品种收益率 ≥ 此值 → 建议部分止盈',
        f'    "stop_loss_pct": {d["discipline"]["stop_loss_pct"]},  // 止损线：单品种收益率 ≤ 此值 → 建议止损/减仓',
        f'    "drawdown_pct": {d["discipline"]["drawdown_pct"]},  // 回撤线：组合相对历史峰值回撤 ≥ 此绝对值 → 建议控回撤',
        f'    "silence_days": {d["discipline"]["silence_days"]}  // 交易纪律信号静默期天数（默认 30 天）',
        "  },",
        "",
        # ── J ──
        "  // ── J. 流动性配置 ──",
        f'  "redemption_limits": {json.dumps(d["redemption_limits"])},  // 场外基金单日赎回上限（code → 金额，空=未配置）',
        "",
        # ── K ──
        "  // ── K. 匿名化配置 ──",
        '  "anonymization": {',
        f'    "mode": {json.dumps(d["anonymization"]["mode"])}  // 匿名化模式：off/code_display/full_anonymous/summary',
        "  },",
        "",
        # ── L ──
        # batch/batch_rate_limit 手动构建（json.dumps 会丢 _DEFAULT_CONFIG 行尾注释）：
        # 注释文本对齐 _DEFAULT_CONFIG（batch 子项）与历史 config.json（batch_rate_limit 子项）
        "  // ── L. 批量并行调度 ──",
        '  "batch": {',
        f'    "max_total_workers": {d["batch"]["max_total_workers"]},  // 全局 batch 线程硬上限（已有池不计入）',
        f'    "fund_workers": {d["batch"]["fund_workers"]},  // 基金排名/持仓批量并发数',
        f'    "industry_workers": {d["batch"]["industry_workers"]}  // 行业分类批量并发数',
        "  },",
        '  "batch_rate_limit": {  // Provider 级别请求间隔（秒），0=不限速',
        f'    "tencent": {d["batch_rate_limit"]["tencent"]},  // 腾讯行情（不限速）',
        f'    "sina": {d["batch_rate_limit"]["sina"]},  // 新浪行情（不限速）',
        f'    "eastmoney": {d["batch_rate_limit"]["eastmoney"]},  // 东方财富行情（100ms）',
        f'    "tiantian": {d["batch_rate_limit"]["tiantian"]},  // 天天基金（500ms）',
        f'    "eastmoney_industry": {d["batch_rate_limit"]["eastmoney_industry"]}  // 东方财富行业（50ms）',
        "  }",
        "}",
    ]
    return "\n".join(parts) + "\n"
