"""LLM 幻觉率采样测试 — 10 组标准持仓数据集 + 正确事实表。

每组数据集包含：
  - name: 数据集名称
  - holdings_details: 持仓明细列表（含 name、code、market_value、cost、profit、profit_rate、account）
  - correct_facts: 正确事实表，供事实校验器验证 LLM 输出准确性

使用方式：
    from src.test.data.hallucination.datasets import HALLUCINATION_DATASETS
    for ds in HALLUCINATION_DATASETS:
        ds["holdings_details"]  # 持仓数据
        ds["correct_facts"]     # 正确事实

字段约定：
  - profit = market_value - cost（持仓浮盈）
  - profit_rate = profit / cost * 100（盈亏百分比）
  - account: 账户归属（测试账户/信用账户/两融账户）
"""

from __future__ import annotations

from typing import Any

# ── 数据集 1：基本 A 股组合（3 只）───────────────────────────────

DS01_BASIC_A_SHARES: dict[str, Any] = {
    "name": "基本 A 股组合",
    "description": "3 只 A 股股票，正收益为主，标准分散组合",
    "holdings_details": [
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 216400.0,
            "cost": 200000.0,
            "profit": 16400.0,
            "profit_rate": 8.2,
            "account": "测试账户",
        },
        {
            "name": "贵州茅台",
            "code": "600519",
            "market_value": 345000.0,
            "cost": 300000.0,
            "profit": 45000.0,
            "profit_rate": 15.0,
            "account": "测试账户",
        },
        {
            "name": "易方达蓝筹",
            "code": "005827",
            "market_value": 97000.0,
            "cost": 100000.0,
            "profit": -3000.0,
            "profit_rate": -3.0,
            "account": "测试账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 9.73,  # (16400+45000-3000) / (200000+300000+100000) * 100
        "top_holding_code": "600519",
        "top_holding_name": "贵州茅台",
        "stock_rates": {"600036": 8.2, "600519": 15.0, "005827": -3.0},
        "total_mv": 658400.0,
        "total_cost": 600000.0,
        "total_profit": 58400.0,
    },
}

# ── 数据集 2：混合基金组合（5 只）─────────────────────────────────

DS02_MIXED_FUND: dict[str, Any] = {
    "name": "混合基金组合",
    "description": "3 只股票 + 2 只基金，覆盖股债混合场景",
    "holdings_details": [
        {
            "name": "美的集团",
            "code": "000333",
            "market_value": 128000.0,
            "cost": 110000.0,
            "profit": 18000.0,
            "profit_rate": 16.36,
            "account": "测试账户",
        },
        {
            "name": "海康威视",
            "code": "002415",
            "market_value": 85000.0,
            "cost": 95000.0,
            "profit": -10000.0,
            "profit_rate": -10.53,
            "account": "测试账户",
        },
        {
            "name": "宁德时代",
            "code": "300750",
            "market_value": 256000.0,
            "cost": 220000.0,
            "profit": 36000.0,
            "profit_rate": 16.36,
            "account": "测试账户",
        },
        {
            "name": "汇添富创新医药",
            "code": "006113",
            "market_value": 82000.0,
            "cost": 80000.0,
            "profit": 2000.0,
            "profit_rate": 2.5,
            "account": "信用账户",
        },
        {
            "name": "易方达研究精选",
            "code": "008286",
            "market_value": 58000.0,
            "cost": 65000.0,
            "profit": -7000.0,
            "profit_rate": -10.77,
            "account": "信用账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 5.74,  # (18000-10000+36000+2000-7000) / (110000+95000+220000+80000+65000) * 100
        "top_holding_code": "300750",
        "top_holding_name": "宁德时代",
        "stock_rates": {"000333": 16.36, "002415": -10.53, "300750": 16.36, "006113": 2.5, "008286": -10.77},
        "total_mv": 609000.0,
        "total_cost": 570000.0,
        "total_profit": 39000.0,
    },
}

# ── 数据集 3：含较大亏损组合（4 只）───────────────────────────────

DS03_WITH_LOSSES: dict[str, Any] = {
    "name": "含较大亏损组合",
    "description": "2 只盈利 + 2 只较大亏损，测试 LLM 对亏损的描述准确性",
    "holdings_details": [
        {
            "name": "中国平安",
            "code": "601318",
            "market_value": 135000.0,
            "cost": 150000.0,
            "profit": -15000.0,
            "profit_rate": -10.0,
            "account": "测试账户",
        },
        {
            "name": "五粮液",
            "code": "000858",
            "market_value": 186000.0,
            "cost": 155000.0,
            "profit": 31000.0,
            "profit_rate": 20.0,
            "account": "测试账户",
        },
        {
            "name": "比亚迪",
            "code": "002594",
            "market_value": 82000.0,
            "cost": 100000.0,
            "profit": -18000.0,
            "profit_rate": -18.0,
            "account": "信用账户",
        },
        {
            "name": "长江电力",
            "code": "600900",
            "market_value": 92000.0,
            "cost": 85000.0,
            "profit": 7000.0,
            "profit_rate": 8.24,
            "account": "测试账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 1.02,  # (-15000+31000-18000+7000) / (150000+155000+100000+85000) * 100
        "top_holding_code": "000858",
        "top_holding_name": "五粮液",
        "stock_rates": {"601318": -10.0, "000858": 20.0, "002594": -18.0, "600900": 8.24},
        "total_mv": 495000.0,
        "total_cost": 490000.0,
        "total_profit": 5000.0,
    },
}

# ── 数据集 4：权重集中组合（3 只）─────────────────────────────────

DS04_CONCENTRATED: dict[str, Any] = {
    "name": "权重集中组合",
    "description": "一只品种占 65% 以上，测试 LLM 对集中度风险描述的准确性",
    "holdings_details": [
        {
            "name": "宁德时代",
            "code": "300750",
            "market_value": 650000.0,
            "cost": 500000.0,
            "profit": 150000.0,
            "profit_rate": 30.0,
            "account": "测试账户",
        },
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 180000.0,
            "cost": 175000.0,
            "profit": 5000.0,
            "profit_rate": 2.86,
            "account": "测试账户",
        },
        {
            "name": "易方达中小盘",
            "code": "110011",
            "market_value": 170000.0,
            "cost": 180000.0,
            "profit": -10000.0,
            "profit_rate": -5.56,
            "account": "信用账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 16.37,  # (150000+5000-10000) / (500000+175000+180000) * 100
        "top_holding_code": "300750",
        "top_holding_name": "宁德时代",
        "stock_rates": {"300750": 30.0, "600036": 2.86, "110011": -5.56},
        "total_mv": 1000000.0,
        "total_cost": 855000.0,
        "total_profit": 145000.0,
    },
}

# ── 数据集 5：分散组合（8 只）─────────────────────────────────────

DS05_DIVERSIFIED: dict[str, Any] = {
    "name": "分散组合",
    "description": "8 只品种小额分散，行业覆盖金融、消费、科技、医药",
    "holdings_details": [
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 62000.0,
            "cost": 58000.0,
            "profit": 4000.0,
            "profit_rate": 6.9,
            "account": "测试账户",
        },
        {
            "name": "贵州茅台",
            "code": "600519",
            "market_value": 110000.0,
            "cost": 100000.0,
            "profit": 10000.0,
            "profit_rate": 10.0,
            "account": "测试账户",
        },
        {
            "name": "美的集团",
            "code": "000333",
            "market_value": 48000.0,
            "cost": 45000.0,
            "profit": 3000.0,
            "profit_rate": 6.67,
            "account": "测试账户",
        },
        {
            "name": "宁德时代",
            "code": "300750",
            "market_value": 75000.0,
            "cost": 65000.0,
            "profit": 10000.0,
            "profit_rate": 15.38,
            "account": "信用账户",
        },
        {
            "name": "海康威视",
            "code": "002415",
            "market_value": 35000.0,
            "cost": 40000.0,
            "profit": -5000.0,
            "profit_rate": -12.5,
            "account": "信用账户",
        },
        {
            "name": "易方达蓝筹",
            "code": "005827",
            "market_value": 52000.0,
            "cost": 55000.0,
            "profit": -3000.0,
            "profit_rate": -5.45,
            "account": "信用账户",
        },
        {
            "name": "汇添富创新医药",
            "code": "006113",
            "market_value": 44000.0,
            "cost": 42000.0,
            "profit": 2000.0,
            "profit_rate": 4.76,
            "account": "信用账户",
        },
        {
            "name": "长江电力",
            "code": "600900",
            "market_value": 38000.0,
            "cost": 36000.0,
            "profit": 2000.0,
            "profit_rate": 5.56,
            "account": "测试账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 6.06,  # (4000+10000+3000+10000-5000-3000+2000+2000) / (58000+100000+45000+65000+40000+55000+42000+36000) * 100
        "top_holding_code": "600519",
        "top_holding_name": "贵州茅台",
        "stock_rates": {
            "600036": 6.9, "600519": 10.0, "000333": 6.67, "300750": 15.38,
            "002415": -12.5, "005827": -5.45, "006113": 4.76, "600900": 5.56,
        },
        "total_mv": 464000.0,
        "total_cost": 441000.0,
        "total_profit": 23000.0,
    },
}

# ── 数据集 6：多账户组合（6 只）───────────────────────────────────

DS06_MULTI_ACCOUNT: dict[str, Any] = {
    "name": "多账户组合",
    "description": "6 只品种分布 3 个账户，覆盖场内外混合",
    "holdings_details": [
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 150000.0,
            "cost": 140000.0,
            "profit": 10000.0,
            "profit_rate": 7.14,
            "account": "测试账户",
        },
        {
            "name": "贵州茅台",
            "code": "600519",
            "market_value": 210000.0,
            "cost": 180000.0,
            "profit": 30000.0,
            "profit_rate": 16.67,
            "account": "测试账户",
        },
        {
            "name": "易方达蓝筹",
            "code": "005827",
            "market_value": 80000.0,
            "cost": 90000.0,
            "profit": -10000.0,
            "profit_rate": -11.11,
            "account": "信用账户",
        },
        {
            "name": "华夏上证50ETF",
            "code": "510050",
            "market_value": 55000.0,
            "cost": 50000.0,
            "profit": 5000.0,
            "profit_rate": 10.0,
            "account": "信用账户",
        },
        {
            "name": "宁德时代",
            "code": "300750",
            "market_value": 120000.0,
            "cost": 110000.0,
            "profit": 10000.0,
            "profit_rate": 9.09,
            "account": "两融账户",
        },
        {
            "name": "东方财富",
            "code": "300059",
            "market_value": 65000.0,
            "cost": 70000.0,
            "profit": -5000.0,
            "profit_rate": -7.14,
            "account": "两融账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 7.14,  # (10000+30000-10000+5000+10000-5000) / (140000+180000+90000+50000+110000+70000) * 100
        "top_holding_code": "600519",
        "top_holding_name": "贵州茅台",
        "stock_rates": {
            "600036": 7.14, "600519": 16.67, "005827": -11.11,
            "510050": 10.0, "300750": 9.09, "300059": -7.14,
        },
        "total_mv": 680000.0,
        "total_cost": 640000.0,
        "total_profit": 40000.0,
    },
}

# ── 数据集 7：偏防守组合（4 只）───────────────────────────────────

DS07_DEFENSIVE: dict[str, Any] = {
    "name": "偏防守组合",
    "description": "高股息 + 债券基金 + 公用事业，偏防守型",
    "holdings_details": [
        {
            "name": "长江电力",
            "code": "600900",
            "market_value": 210000.0,
            "cost": 190000.0,
            "profit": 20000.0,
            "profit_rate": 10.53,
            "account": "测试账户",
        },
        {
            "name": "大秦铁路",
            "code": "601006",
            "market_value": 85000.0,
            "cost": 88000.0,
            "profit": -3000.0,
            "profit_rate": -3.41,
            "account": "测试账户",
        },
        {
            "name": "中国神华",
            "code": "601088",
            "market_value": 155000.0,
            "cost": 130000.0,
            "profit": 25000.0,
            "profit_rate": 19.23,
            "account": "测试账户",
        },
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 120000.0,
            "cost": 115000.0,
            "profit": 5000.0,
            "profit_rate": 4.35,
            "account": "信用账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 8.81,  # (20000-3000+25000+5000) / (190000+88000+130000+115000) * 100
        "top_holding_code": "600900",
        "top_holding_name": "长江电力",
        "stock_rates": {"600900": 10.53, "601006": -3.41, "601088": 19.23, "600036": 4.35},
        "total_mv": 570000.0,
        "total_cost": 523000.0,
        "total_profit": 47000.0,
    },
}

# ── 数据集 8：全基金组合（3 只）───────────────────────────────────

DS08_ALL_FUNDS: dict[str, Any] = {
    "name": "全基金组合",
    "description": "3 只公募基金，无直接股票持仓，测试穿透逻辑幻觉",
    "holdings_details": [
        {
            "name": "易方达蓝筹",
            "code": "005827",
            "market_value": 150000.0,
            "cost": 160000.0,
            "profit": -10000.0,
            "profit_rate": -6.25,
            "account": "测试账户",
        },
        {
            "name": "汇添富创新医药",
            "code": "006113",
            "market_value": 120000.0,
            "cost": 110000.0,
            "profit": 10000.0,
            "profit_rate": 9.09,
            "account": "信用账户",
        },
        {
            "name": "华夏沪深300指数增强",
            "code": "007207",
            "market_value": 85000.0,
            "cost": 80000.0,
            "profit": 5000.0,
            "profit_rate": 6.25,
            "account": "信用账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 1.43,  # (-10000+10000+5000) / (160000+110000+80000) * 100
        "top_holding_code": "005827",
        "top_holding_name": "易方达蓝筹",
        "stock_rates": {"005827": -6.25, "006113": 9.09, "007207": 6.25},
        "total_mv": 355000.0,
        "total_cost": 350000.0,
        "total_profit": 5000.0,
    },
}

# ── 数据集 9：零成本特殊场景（3 只）───────────────────────────────

DS09_ZERO_COST: dict[str, Any] = {
    "name": "零成本特殊场景",
    "description": "部分品种成本为 0（继承/赠予），测试 LLM 对异常成本的处理",
    "holdings_details": [
        {
            "name": "贵州茅台",
            "code": "600519",
            "market_value": 250000.0,
            "cost": 0.0,
            "profit": 250000.0,
            "profit_rate": None,
            "account": "测试账户",
        },
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 180000.0,
            "cost": 160000.0,
            "profit": 20000.0,
            "profit_rate": 12.5,
            "account": "测试账户",
        },
        {
            "name": "易方达蓝筹",
            "code": "005827",
            "market_value": 70000.0,
            "cost": 75000.0,
            "profit": -5000.0,
            "profit_rate": -6.67,
            "account": "信用账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 106.38,  # (250000+20000-5000) / (0+160000+75000) * 100 — 零成本导致总收益率极高
        "top_holding_code": "600519",
        "top_holding_name": "贵州茅台",
        "stock_rates": {"600036": 12.5, "005827": -6.67},
        "total_mv": 500000.0,
        "total_cost": 235000.0,
        "total_profit": 265000.0,
    },
}

# ── 数据集 10：极简组合（2 只）────────────────────────────────────

DS10_MINIMAL: dict[str, Any] = {
    "name": "极简组合",
    "description": "仅 2 只品种，最小规模测试",
    "holdings_details": [
        {
            "name": "招商银行",
            "code": "600036",
            "market_value": 54000.0,
            "cost": 50000.0,
            "profit": 4000.0,
            "profit_rate": 8.0,
            "account": "测试账户",
        },
        {
            "name": "易方达蓝筹",
            "code": "005827",
            "market_value": 47000.0,
            "cost": 50000.0,
            "profit": -3000.0,
            "profit_rate": -6.0,
            "account": "测试账户",
        },
    ],
    "correct_facts": {
        "portfolio_return_rate": 1.0,  # (4000-3000) / (50000+50000) * 100
        "top_holding_code": "600036",
        "top_holding_name": "招商银行",
        "stock_rates": {"600036": 8.0, "005827": -6.0},
        "total_mv": 101000.0,
        "total_cost": 100000.0,
        "total_profit": 1000.0,
    },
}

# ── 总注册表 ──────────────────────────────────────────────────────

HALLUCINATION_DATASETS: list[dict[str, Any]] = [
    DS01_BASIC_A_SHARES,
    DS02_MIXED_FUND,
    DS03_WITH_LOSSES,
    DS04_CONCENTRATED,
    DS05_DIVERSIFIED,
    DS06_MULTI_ACCOUNT,
    DS07_DEFENSIVE,
    DS08_ALL_FUNDS,
    DS09_ZERO_COST,
    DS10_MINIMAL,
]
"""10 组标准持仓数据集，用于 LLM 幻觉率采样测试。"""
