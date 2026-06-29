"""资产穿透 TOP10 模块 — 报告第 4 页。

将每只基金拆解为前 10 大持仓，合并相同底层标的，
再合并直接持有的股票，按市值降序取全仓前 10。

基金类型分类规则（按优先级）：
  1. QDII            → 具体美股（季报数据）
  2. 债券基金         → 具体债券品种
  3. 场外指数联接     → 前 10 大成分股
  4. ETF             → 前 10 大成分股/黄金现货
  5. 主动权益基金     → 前 10 大持仓
  6. 直接持有股票     → 合并计算

输出列：
  排名 | 名称 | 代码 | 穿透市值 | 占比 | 板块 | 概念 | 预测EPS(2025E) | 年均股息率 | 来源明细
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List

from openpyxl.worksheet.worksheet import Worksheet

from src.python.fetcher import fetch_fund_holdings
from src.python.models import Holding
from src.python.report.excel_writer import (
    auto_width,
    freeze_header,
    write_data_row,
    write_header_row,
    write_title_row,
)
from src.python.report.market_value import DetailRow
from src.python.report.styles import FMT_MONEY, FMT_PERCENT


def _get_eps_text(forecast: dict, codes: list[str]) -> str:
    """根据盈利预测数据和代码列表，查找匹配的预测 EPS 文本。"""
    if not forecast:
        return "--"
    for code in codes:
        info = forecast.get(code)
        if info:
            eps = info.get("eps_2025e")
            if eps is not None:
                return f"¥{eps:.2f}"
    return "--"


def _get_dividend_text(dividend_data: dict, codes: list[str]) -> str:
    """根据分红数据和代码列表，查找匹配的年均股息率文本。"""
    if not dividend_data:
        return "--"
    for code in codes:
        info = dividend_data.get(code)
        if info and info.get("avg_dividend"):
            return f"{info['avg_dividend']:.4f}元/年"
    return "--"

logger = logging.getLogger("invest")

_NCOLS = 10
_HEADERS = [
    "排名", "名称", "代码", "穿透市值", "占比", "板块", "概念",
    "预测EPS(2025E)", "年均股息率", "来源明细",
]

# ── 穿透分类常量 ───────────────────────────────────────────
# 公开导出的分类常量，方便测试模块引用

STOCK = "stock"                # 直接持有股票
QDII = "qdii"                  # QDII 基金
ETF = "etf"                    # 场内 ETF
INDEX_LINK = "index_link"      # 场外指数联接
BOND_FUND = "bond_fund"        # 债券基金
ACTIVE_EQUITY = "active_equity"  # 主动权益基金
IGNORE = "ignore"              # 忽略（现金/转债/Reits 等）

# 穿透基金类型 → 来源短标签
_FUND_TYPE_TAG: dict[str, str] = {
    QDII: "QDII",
    ETF: "ETF",
    INDEX_LINK: "联接",
    BOND_FUND: "债券",
    ACTIVE_EQUITY: "权益",
}

# 场外账户关键词
_FUND_ACCOUNT_KW = ("基金", "支付宝", "微信", "银行")


# ═══════════════════════════════════════════════════════════
#  分类判断
# ═══════════════════════════════════════════════════════════


def classify_penetration(h: Holding) -> str:
    """判断持仓在穿透分析中的角色。

    优先级（高 → 低）：
      1. QDII            — 名称含 ``QDII``
      2. 债券基金         — 名称含债类关键词（纯债/短债/债券等）
      3. 场外指数联接     — 名称含联接 / ETF联接 / 链接
      4. ETF             — 名称含 ``ETF`` 或代码以 ``5`` 开头
      5. 主动权益基金     — 场外账户（基金/支付宝/微信/银行）中的基金
      6. 直接持有股票     — 代码以 ``6`` / ``0`` / ``3`` 开头
      7. ``"ignore"``    — 其余（现金/转债/Reits 等）

    Args:
        h: 持仓记录

    Returns:
        分类常量之一（``STOCK`` / ``QDII`` / ``ETF`` / ``INDEX_LINK`` /
        ``BOND_FUND`` / ``ACTIVE_EQUITY`` / ``IGNORE``）
    """
    name = h.name.strip()
    code = h.code.strip()
    account = h.account.strip()

    # 1) QDII 基金（最优先，名称明确）
    if "QDII" in name.upper():
        return QDII

    # 2) 债券基金
    if _is_bond_fund(name):
        return BOND_FUND

    # 3) 场外指数联接
    if _is_index_link(name):
        return INDEX_LINK

    # 4) 场内 ETF（名称含 ETF 或代码 5 开头）
    if "ETF" in name.upper() or code.startswith("5"):
        return ETF

    # 5) 场外账户中的基金 → 主动权益基金（兜底）
    if any(kw in account for kw in _FUND_ACCOUNT_KW):
        return ACTIVE_EQUITY

    # 6) A 股股票
    if code.startswith(("6", "0", "3")):
        return STOCK

    # 7) 其余忽略
    return IGNORE


def _is_bond_fund(name: str) -> bool:
    """判断名称是否为债券基金。

    识别关键词：纯债 / 短债 / 中短债 / 利率债 / 信用债 / 债券

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配债券基金特征
    """
    kw = ("纯债", "短债", "中短债", "利率债", "信用债", "债券")
    return any(k in name for k in kw)


def _is_index_link(name: str) -> bool:
    """判断是否为场外指数联接基金。

    识别关键词：ETF联接 / ETF链接 / 联接 / 链接（单独出现时也视为联接基金）。

    Args:
        name: 基金名称

    Returns:
        True 表示名称匹配指数联接特征
    """
    clean = name.replace(" ", "").upper()
    if "ETF联接" in clean or "ETF链接" in clean:
        return True
    return any(kw in name for kw in ("联接", "链接"))


def _fund_type_tag(ftype: str) -> str:
    """返回基金类型的短标签（用于来源明细列）。

    Args:
        ftype: 分类常量（QDII / ETF / INDEX_LINK / BOND_FUND / ACTIVE_EQUITY）

    Returns:
        短标签字符串，如 ``"QDII"`` / ``"ETF"`` / ``"联接"``
    """
    return _FUND_TYPE_TAG.get(ftype, "基金")


# ═══════════════════════════════════════════════════════════
#  板块分类
# ═══════════════════════════════════════════════════════════

# A 股板块关键词映射：按名称关键词匹配 → 板块
_SECTOR_KEYWORDS: dict[str, str] = {
    # 消费
    "白酒": "消费", "茅台": "消费", "五粮液": "消费", "酒": "消费",
    "食品": "消费", "饮料": "消费", "乳业": "消费", "牛奶": "消费",
    "家电": "消费", "美的": "消费", "格力": "消费", "海尔": "消费",
    "汽车": "消费", "整车": "消费", "汽车零部件": "消费",
    "零售": "消费", "超市": "消费", "电商": "消费",
    "服装": "消费", "纺织": "消费", "家纺": "消费",
    "医药": "医药", "医疗": "医药", "药": "医药", "生物": "医药",
    "健康": "医药", "疫苗": "医药", "医美": "医药", "CXO": "医药",
    "cro": "医药", "创新药": "医药",
    # 科技
    "芯片": "科技", "半导体": "科技", "集成电路": "科技",
    "电子": "科技", "光电": "科技", "激光": "科技",
    "科技": "科技", "软件": "科技", "信息": "科技",
    "计算机": "科技", "AI": "科技", "人工智能": "科技",
    "大数据": "科技", "云计算": "科技", "云": "科技",
    "通信": "科技", "5G": "科技", "6G": "科技",
    "机器人": "科技", "自动化": "科技",
    "消费电子": "科技", "面板": "科技", "显示": "科技",
    # 科技 - 美股权重股（QDII 穿透常见）
    "苹果": "科技", "微软": "科技", "谷歌": "科技",
    "亚马逊": "科技", "英伟达": "科技", "META": "科技",
    "特斯拉": "科技", "甲骨文": "科技", "ORACLE": "科技",
    "英特尔": "科技", "INTC": "科技", "AMD": "科技",
    "高通": "科技", "博通": "科技", "BROADCOM": "科技",
    "思科": "科技", "CISCO": "科技", "IBM": "科技",
    "SALESFORCE": "科技", "CRM": "科技", "ADOBE": "科技",
    "INTUIT": "科技", "SERVICENOW": "科技",
    # 科技 - 光通信/算力（常见 A 股标的）
    "新易盛": "科技", "天孚": "科技", "太辰光": "科技",
    "旭创": "科技", "光模块": "科技", "光通信": "科技",
    "算力": "科技", "服务器": "科技", "光迅": "科技",
    "浪潮": "科技", "曙光": "科技",
    # 科技 - 半导体（设计/设备/封测）
    "中芯": "科技", "北方华创": "科技", "韦尔": "科技",
    "兆易": "科技", "卓胜微": "科技", "圣邦": "科技",
    "士兰微": "科技", "华大九天": "科技", "紫光": "科技",
    "中科曙光": "科技", "景嘉微": "科技",
    "长电": "科技", "通富": "科技", "华天": "科技",
    "沪电": "科技", "深南电路": "科技",
    # 科技 - 软件/互联网
    "金山办公": "科技", "用友": "科技", "广联达": "科技",
    "科大讯飞": "科技", "恒生电子": "科技",
    "中科创达": "科技", "同花顺": "科技", "财富趋势": "科技",
    # 科技 - 安防/通信运营商
    "海康": "科技", "大华": "科技",
    "中国联通": "科技", "中国电信": "科技", "中国移动": "科技",
    # 科技 - 金融科技
    "东方财富": "金融",
    # 金融 - 美股权重股
    "摩根大通": "金融", "高盛": "金融",
    "摩根士丹利": "金融", "美国银行": "金融", "花旗": "金融",
    "富国": "金融", "VISA": "金融", "万事达": "金融",
    # 消费 - 美股权重股
    "可口可乐": "消费", "百事": "消费", "沃尔玛": "消费",
    "COSTCO": "消费", "好市多": "消费", "宝洁": "消费",
    "麦当劳": "消费", "星巴克": "消费", "耐克": "消费",
    # 医药 - 美股权重股（重复关键词会被前面医药块覆盖，但显式列出方便检查）
    "强生": "医药", "辉瑞": "医药", "默克": "医药",
    "礼来": "医药", "联合健康": "医药", "艾伯维": "医药",
    # 通信 - 美股权重股
    "DISNEY": "消费", "迪士尼": "消费", "NETFLIX": "科技",
    "奈飞": "科技", "COMCAST": "科技",
    # 新能源
    "新能源": "新能源", "光伏": "新能源", "锂电": "新能源",
    "电池": "新能源", "风电": "新能源", "氢能": "新能源",
    "新能源车": "新能源", "电车": "新能源", "储能": "新能源",
    "宁德时代": "新能源", "比亚迪": "新能源", "隆基": "新能源",
    "太阳": "新能源", "硅": "新能源", "晶澳": "新能源",
    "晶科": "新能源", "天合": "新能源", "阳光电源": "新能源",
    "亿纬": "新能源", "恩捷": "新能源", "天赐": "新能源",
    "赣锋": "新能源", "天齐锂": "新能源", "华友": "新能源",
    "福莱特": "新能源", "福斯特": "新能源",
    # 食品饮料（消费子类细化）
    "伊利": "消费", "海天": "消费", "金龙鱼": "消费",
    "双汇": "消费", "安井": "消费", "涪陵": "消费",
    "东鹏": "消费", "农夫山泉": "消费",
    # 金融 - A 股
    "中国人保": "金融", "新华保险": "金融",
    "中国银河": "金融", "光大证券": "金融", "招商证券": "金融",
    # 制造 - 材料/矿业
    "紫金": "制造", "洛阳钼业": "制造", "江西铜业": "制造",
    "中国铝业": "制造", "南山铝业": "制造",
    "万华": "制造", "宝钢": "制造", "鞍钢": "制造",
    "海螺": "制造", "华新水泥": "制造", "中国巨石": "制造",
    # 制造 - 机械
    "潍柴": "制造", "中联重科": "制造", "三一": "制造",
    "徐工": "制造", "恒立": "制造", "汇川": "制造",
    # 医药 - A 股补充
    "长春高新": "医药", "智飞": "医药", "沃森": "医药",
    "康泰": "医药", "通策": "医药", "凯莱英": "医药",
    "康龙化成": "医药", "泰格": "医药", "益丰": "医药",
    "同仁堂": "医药", "白云山": "医药", "片仔癀": "医药",
    "东阿": "医药", "云南白药": "医药",
    # 消费 - 细分赛道
    "珀莱雅": "消费", "贝泰妮": "消费", "华熙": "医药",
    "安踏": "消费", "李宁": "消费", "波司登": "消费",
    "牧原": "农业", "温氏": "农业", "圣农": "农业",
    "大北农": "农业", "隆平高科": "农业",
    # 金融
    "银行": "金融", "证券": "金融", "保险": "金融", "信托": "金融",
    "券商": "金融", "互联网金融": "金融", "金融": "金融",
    # 制造
    "机械": "制造", "装备": "制造", "制造": "制造",
    "工业": "制造", "化工": "制造", "材料": "制造",
    "钢铁": "制造", "有色": "制造", "金属": "制造",
    "建材": "制造", "玻璃": "制造", "水泥": "制造",
    "造纸": "制造", "包装": "制造", "轻工": "制造",
    "重工": "制造", "电气": "制造", "仪器": "制造",
    # 地产基建
    "地产": "地产基建", "房产": "地产基建", "万科": "地产基建",
    "建设": "地产基建", "基建": "地产基建", "建筑": "地产基建",
    "工程": "地产基建", "中铁": "地产基建", "中交": "地产基建",
    "路桥": "地产基建", "市政": "地产基建",
    # 军工
    "军工": "军工", "航天": "军工", "航空": "军工", "国防": "军工",
    "中航": "军工", "船舶": "军工", "中国重工": "军工",
    # 能源资源
    "能源": "能源资源", "煤炭": "能源资源", "石油": "能源资源",
    "天然气": "能源资源", "电力": "能源资源", "核电": "能源资源",
    "水电": "能源资源", "中国神华": "能源资源", "中国海油": "能源资源",
    "中石油": "能源资源", "中石化": "能源资源",
    # 交通物流
    "运输": "交通物流", "物流": "交通物流", "快递": "交通物流",
    "航空": "交通物流", "机场": "交通物流", "港口": "交通物流",
    "高速": "交通物流", "航运": "交通物流", "铁路": "交通物流",
    # 农业
    "农业": "农业", "牧": "农业", "农": "农业", "种业": "农业",
    "猪": "农业", "鸡": "农业", "饲料": "农业",
    # 公用事业
    "水务": "公用事业", "燃气": "公用事业", "环保": "公用事业",
    "环境": "公用事业", "垃圾": "公用事业",
}


def classify_sector(name: str, code: str = "") -> str:
    """根据证券名称和代码判断所属板块。

    Args:
        name: 证券名称
        code: 证券代码（备用，当前未使用）

    Returns:
        板块名称，如 "消费" / "科技" / "医药" / "新能源"，未知返回 "--"
    """
    if not name:
        return "--"
    clean = name.replace(" ", "").upper()
    for keyword, sector in _SECTOR_KEYWORDS.items():
        if keyword.upper() in clean:
            return sector
    return "--"


def normalize_name(name: str) -> str:
    """归一化证券名称，用于合并相同底层标的。

    处理：去除首尾空格、全角空格、\xa0 不间断空格。

    Args:
        name: 原始名称

    Returns:
        归一化后的名称
    """
    s = name.strip()
    s = s.replace("　", " ").replace("\xa0", " ")
    return s


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════


def compute_penetration_top10(
    holdings: List[Holding],
    details: List[DetailRow],
) -> dict[str, Any]:
    """计算资产穿透 TOP10，返回结构化数据（不写 Excel）。

    与 :func:`write_penetration_sheet` 共用同一套合并/排序逻辑，
    但返回可序列化的 Python 字典，适合缓存为 JSON。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        {
            "update_time": "2026-06-27 14:30:00",
            "summary": {
                "total_funds": 5,
                "total_stocks": 3,
                "fund_breakdown": "QDII1 + ETF2 + 联接1 + 债券1 + 主动0",
                "merged_count": 12,
                "total_mv": 123456.78,
                "top10_coverage_pct": 85.3,
                "unknown_mv": 5000.0,
                "failed_funds": 1,
            },
            "top10": [
                {
                    "rank": 1, "name": "贵州茅台",
                    "codes": ["600519"], "mv": 50000.0,
                    "ratio_pct": 15.2, "sources": ["[ETF] 电池ETF(561910)"]
                },
                ...
            ],
        }
    """
    # ── 1) 精细化分类 ──────────────────────────────────────
    classified: dict[str, list[Holding]] = {
        QDII: [], ETF: [], INDEX_LINK: [],
        BOND_FUND: [], ACTIVE_EQUITY: [], STOCK: [], IGNORE: [],
    }
    for h in holdings:
        cat = classify_penetration(h)
        if cat in classified:
            classified[cat].append(h)
        else:
            classified[IGNORE].append(h)

    fund_types = [QDII, ETF, INDEX_LINK, BOND_FUND, ACTIVE_EQUITY]
    funds: list[Holding] = []
    for ft in fund_types:
        funds.extend(classified[ft])
    direct_stocks = classified[STOCK]

    detail_map: dict[str, DetailRow] = {d.code: d for d in details}

    # ── 2) 合并底层标的 ──────────────────────────────────────
    merged: dict[str, dict[str, Any]] = {}
    unknown_mv = 0.0
    failed_count = 0
    failed_fund_details: list[dict[str, str]] = []  # 记录无法获取穿透的基金

    for fund in funds:
        detail = detail_map.get(fund.code)
        fund_mv = detail.market_value if detail else 0.0
        ftype = classify_penetration(fund)
        tag = _fund_type_tag(ftype)

        holdings_data = fetch_fund_holdings(fund.code)
        if holdings_data is None or not holdings_data.get("holdings"):
            # 无法获取底层持仓时，将基金本身作为穿透节点加入，
            # 避免该基金市值完全脱离穿透 TOP10 覆盖
            unknown_mv += fund_mv
            failed_count += 1
            failed_fund_details.append({"name": fund.name, "code": fund.code})
            # 将基金本身作为一个穿透标的加入合并列表
            fund_node = normalize_name(fund.name)
            if fund_node not in merged:
                sector = classify_sector(fund.name, fund.code)
                merged[fund_node] = {
                    "name": fund.name, "codes": {fund.code},
                    "mv": 0.0, "funds": [], "sector": sector or "--",
                }
            merged[fund_node]["mv"] += fund_mv
            merged[fund_node]["codes"].add(fund.code)
            merged[fund_node]["funds"].append(f"[{tag}] {fund.name}({fund.code})")
            continue

        for item in holdings_data["holdings"]:
            stock_name = item.get("name", "").strip()
            stock_code = item.get("code", "").strip()
            ratio = item.get("ratio", 0.0)
            if not stock_name:
                continue

            attributed_mv = fund_mv * (ratio / 100.0) if ratio > 0 else 0.0
            norm_name = normalize_name(stock_name)

            sector = classify_sector(stock_name, stock_code)
            if norm_name not in merged:
                merged[norm_name] = {
                    "name": stock_name, "codes": set(),
                    "mv": 0.0, "funds": [], "sector": sector,
                }
            if stock_code:
                merged[norm_name]["codes"].add(stock_code)
            merged[norm_name]["mv"] += attributed_mv
            merged[norm_name]["funds"].append(f"[{tag}] {fund.name}({fund.code})")

    # ── 3) 合并直接持股 ──────────────────────────────────────
    for stock in direct_stocks:
        detail = detail_map.get(stock.code)
        stock_mv = detail.market_value if detail else 0.0
        norm_name = normalize_name(stock.name)
        sector = classify_sector(stock.name, stock.code)

        if norm_name not in merged:
            merged[norm_name] = {
                "name": stock.name, "codes": {stock.code},
                "mv": 0.0, "funds": [], "sector": sector,
            }
        else:
            merged[norm_name]["codes"].add(stock.code)
        merged[norm_name]["mv"] += stock_mv
        merged[norm_name]["funds"].append("直接持有")

    # ── 3.5) 用 API 行业数据补充板块分类和概念 ──────────────
    try:
        _all_pen_codes: list[str] = []
        for _info in merged.values():
            _all_pen_codes.extend(_info.get("codes") or [])
        if _all_pen_codes:
            from src.python.fetcher import batch_fetch_industry_data as _batch_ind
            _ind_data = _batch_ind(list(set(_all_pen_codes)))
            if _ind_data:
                for _info in merged.values():
                    for _code in _info.get("codes") or []:
                        if _code in _ind_data:
                            _id = _ind_data[_code]
                            if _id.get("industry"):
                                _info["sector_api"] = _id["industry"]
                                _info["sector"] = _id["industry"]
                            if _id.get("concepts"):
                                _info["concepts"] = _id["concepts"]
                            break
    except Exception as _e:
        logger.debug("穿透板块 API 补充失败（非关键）: %s", _e)

    # ── 4) 生成返回数据 ──────────────────────────────────
    total_mv = sum(v["mv"] for v in merged.values())
    sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)

    fund_breakdown = " + ".join(
        f"{cat_label}{len(classified[c])}"
        for c, cat_label in [
            (QDII, "QDII"), (ETF, "ETF"), (INDEX_LINK, "联接"),
            (BOND_FUND, "债券"), (ACTIVE_EQUITY, "主动"),
        ]
        if classified[c]
    )

    top10_list = []
    for rank, (norm_name, info) in enumerate(sorted_items[:10], 1):
        ratio = info["mv"] / total_mv * 100 if total_mv > 0 else 0.0
        # 概念列表最多取前 3 个
        concepts = (info.get("concepts") or [])[:3]
        top10_list.append({
            "rank": rank,
            "name": info["name"],
            "codes": sorted(info["codes"]) if info["codes"] else [],
            "mv": round(info["mv"], 2),
            "ratio_pct": round(ratio, 2),
            "sector": info.get("sector", "--"),
            "concepts": concepts,
            "sources": sorted(set(info["funds"])),
        })

    top10_coverage = (
        sum(v["mv"] for _, v in sorted_items[:10]) / total_mv * 100
        if total_mv > 0 else 0.0
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "update_time": now,
        "summary": {
            "total_funds": len(funds),
            "total_stocks": len(direct_stocks),
            "fund_breakdown": fund_breakdown,
            "merged_count": len(merged),
            "total_mv": round(total_mv, 2),
            "top10_coverage_pct": round(top10_coverage, 1),
            "unknown_mv": round(unknown_mv, 2),
            "failed_funds": failed_count,
            "failed_fund_details": failed_fund_details,
        },
        "top10": top10_list,
    }


# ═══════════════════════════════════════════════════════════
#  Excel 写入（复用 compute_penetration_top10）
# ═══════════════════════════════════════════════════════════


def write_penetration_sheet(
    ws: Worksheet,
    holdings: List[Holding],
    details: List[DetailRow],
    penetration_data: dict | None = None,
) -> None:
    """写入资产穿透TOP10。

    用 :func:`compute_penetration_top10` 计算数据后写入 Excel 行。

    Args:
        ws: 目标工作表
        holdings: 原始持仓列表
        details: 市值核算明细行列表
        penetration_data: 预计算穿透数据。为 None 时自动计算，提供时跳过
                          内部重复计算，用于调用方已算过一轮的场景
    """
    ws.title = "4.资产穿透TOP10"
    row = write_title_row(ws, 1, "资产穿透TOP10", _NCOLS)
    row = write_header_row(ws, row, _HEADERS)

    if penetration_data is not None:
        result = penetration_data
    else:
        result = compute_penetration_top10(holdings, details)

    if not result["top10"]:
        write_data_row(ws, row, ["暂无穿透数据"])
        freeze_header(ws, 2)
        auto_width(ws)
        logger.warning("穿透分析无数据")
        return

    summary = result["summary"]

    # ── 加载盈利预测数据（降级：API 不可用时全列 "--"） ──
    try:
        from src.python.providers.akshare_extras import get_profit_forecast
        profit_forecast = get_profit_forecast()
    except Exception:
        logger.debug("盈利预测加载失败（非关键），EPS 列显示 --")
        profit_forecast = {}

    # ── 加载分红数据（降级：API 不可用时全列 "--"） ──
    try:
        from src.python.providers.akshare_extras import get_dividend_data
        _all_top10_codes = list(set().union(*(entry.get("codes", []) for entry in result["top10"])))
        _a_stock_codes = [c for c in _all_top10_codes if c.startswith(("6", "0", "3"))]
        dividend_data = get_dividend_data(_a_stock_codes) if _a_stock_codes else {}
    except Exception:
        logger.debug("分红数据加载失败（非关键），年均股息率列显示 --")
        dividend_data = {}

    for entry in result["top10"]:
        concepts = entry.get("concepts", [])
        concepts_str = " / ".join(concepts) if concepts else "--"
        codes = entry.get("codes", [])
        eps_text = _get_eps_text(profit_forecast, codes)
        div_text = _get_dividend_text(dividend_data, codes)
        vals = [
            entry["rank"],
            entry["name"],
            ", ".join(codes) if codes else "--",
            entry["mv"],
            entry["ratio_pct"] / 100.0,
            entry.get("sector", "--"),
            concepts_str,
            eps_text,
            div_text,
            "; ".join(entry["sources"]),
        ]
        write_data_row(ws, row, vals, _num_formats())
        row += 1

    # 备注 & 统计信息
    row += 1
    if summary["unknown_mv"] > 0:
        write_data_row(ws, row,
                       [f"* {summary['total_funds']} 只基金中，有 "
                        f"{summary['failed_funds']} 只无法获取穿透数据，"
                        f"合计市值 {summary['unknown_mv']:,.2f} 元未计入穿透 TOP10"],
                       [])
        row += 1
        # 列出无法获取穿透的基金明细
        failed_details = summary.get("failed_fund_details", [])
        if failed_details:
            failed_names = "；".join(
                f"{f['name']}({f['code']})" for f in failed_details
            )
            write_data_row(ws, row, [f"  无法获取穿透的基金：{failed_names}"], [])
            row += 1

    info_line = (
        f"基金 {summary['total_funds']} 只（{summary['fund_breakdown']}）"
        f" + 直接持股 {summary['total_stocks']} 只 → "
        f"穿透合并 {summary['merged_count']} 个标的，"
        f"TOP10 覆盖 {summary['top10_coverage_pct']:.1f}%"
    )
    write_data_row(ws, row, [info_line], [])

    freeze_header(ws, 2)
    auto_width(ws, min_width=10, max_width=40)

    logger.info("资产穿透TOP10写入完成，合并 %d 个标的",
                summary["merged_count"])


# ═══════════════════════════════════════════════════════════
#  内部辅助
# ═══════════════════════════════════════════════════════════


def _num_formats() -> list[str]:
    """每列的 Excel 数字格式。"""
    return [
        "",           # 1  排名
        "",           # 2  名称
        "",           # 3  代码
        FMT_MONEY,    # 4  穿透市值
        FMT_PERCENT,  # 5  占比
        "",           # 6  板块
        "",           # 7  概念
        "",           # 8  预测EPS(2025E)
        "",           # 9  年均股息率
        "",           # 10 来源明细
    ]
