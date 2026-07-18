"""资产穿透TOP10 模块 — 报告第 4 页。

将每只基金拆解为前 10 大持仓，合并相同底层标的，
再合并直接持有的股票，按市值降序取全仓前 10。

计算入口：:func:`compute_penetration_top10`
Excel 写入函数见 :mod:`src.python.report.penetration_sheet`。

基金类型分类规则（按优先级）：
  1. QDII            → 具体美股（季报数据）
  2. 债券基金         → 具体债券品种
  3. 场外指数联接     → 前 10 大成分股
  4. ETF             → 前 10 大成分股/黄金现货
  5. 主动权益基金     → 前 10 大持仓
  6. 直接持有股票     → 合并计算

输出列：
  排名 | 名称 | 代码 | 穿透市值 | 占比 | 板块 | 概念 | 预测EPS(当前年E) | 年均股息 | 来源明细
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.python.code_utils import (
    is_a_share_code,
    is_bond_related_by_name,
    is_convertible_bond_by_name,
    is_etf_by_name,
    is_exchange_fund_code,
    is_index_link_by_name,
    is_offsite_fund,
    is_otc_fund_by_name,
    is_qdii_extended,
)
from src.python.fetcher.fund import fetch_fund_holdings
from src.python.fetcher.fund_manager import fetch_fund_manager
from src.python.models import Holding
from src.python.report.market_value import DetailRow

logger = logging.getLogger("invest")

# ── 穿透分类常量 ───────────────────────────────────────────
# 公开导出的分类常量，方便测试模块引用

STOCK = "stock"  # 直接持有股票
QDII = "qdii"  # QDII 基金
ETF = "etf"  # 场内 ETF
INDEX_LINK = "index_link"  # 场外指数联接
BOND_FUND = "bond_fund"  # 债券基金
ACTIVE_EQUITY = "active_equity"  # 主动权益基金
IGNORE = "ignore"  # 忽略（现金/转债/Reits 等）

# 穿透基金类型 → 来源短标签
_FUND_TYPE_TAG: dict[str, str] = {
    QDII: "QDII",
    ETF: "ETF",
    INDEX_LINK: "联接",
    BOND_FUND: "债券",
    ACTIVE_EQUITY: "权益",
}


# ═══════════════════════════════════════════════════════════
#  分类判断
# ═══════════════════════════════════════════════════════════


def classify_penetration(h: Holding) -> str:
    """判断持仓在穿透深度分析中的角色。

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

    # 1) QDII 基金（最优先，含隐式海外基金识别）
    if is_qdii_extended(name):
        return QDII

    # 2) 债券基金
    if is_bond_related_by_name(name):
        return BOND_FUND

    # 3) 场外指数联接
    if is_index_link_by_name(name):
        return INDEX_LINK

    # 3.5) 可转债 → 忽略（转债为场内交易品种，但非基金/ETF/股票）
    if is_convertible_bond_by_name(name):
        return IGNORE

    # 4) 场内 ETF（名称含 ETF 或代码为场内基金/ETF 代码）
    if is_etf_by_name(name) or is_exchange_fund_code(code):
        return ETF

    # 5) 场外账户中的基金 → 主动权益基金（兜底）
    if is_offsite_fund(account):
        return ACTIVE_EQUITY

    # 6) 00 代码场外基金（名称匹配基金特征，与 A 股 00 前缀重叠区）
    if is_otc_fund_by_name(name, code):
        return ACTIVE_EQUITY

    # 7) A 股股票
    if is_a_share_code(code):
        return STOCK

    # 8) 其余忽略
    return IGNORE


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
    "白酒": "消费",
    "茅台": "消费",
    "五粮液": "消费",
    "酒": "消费",
    "食品": "消费",
    "饮料": "消费",
    "乳业": "消费",
    "牛奶": "消费",
    "家电": "消费",
    "美的": "消费",
    "格力": "消费",
    "海尔": "消费",
    "汽车": "消费",
    "整车": "消费",
    "汽车零部件": "消费",
    "零售": "消费",
    "超市": "消费",
    "电商": "消费",
    "服装": "消费",
    "纺织": "消费",
    "家纺": "消费",
    "医药": "医药",
    "医疗": "医药",
    "药": "医药",
    "生物": "医药",
    "健康": "医药",
    "疫苗": "医药",
    "医美": "医药",
    "CXO": "医药",
    "cro": "医药",
    "创新药": "医药",
    # 科技
    "芯片": "科技",
    "半导体": "科技",
    "集成电路": "科技",
    "电子": "科技",
    "光电": "科技",
    "激光": "科技",
    "科技": "科技",
    "软件": "科技",
    "信息": "科技",
    "计算机": "科技",
    "AI": "科技",
    "人工智能": "科技",
    "大数据": "科技",
    "云计算": "科技",
    "云": "科技",
    "通信": "科技",
    "5G": "科技",
    "6G": "科技",
    "机器人": "科技",
    "自动化": "科技",
    "消费电子": "科技",
    "面板": "科技",
    "显示": "科技",
    # 科技 - 美股权重股（QDII 穿透常见）
    "苹果": "科技",
    "微软": "科技",
    "谷歌": "科技",
    "亚马逊": "科技",
    "英伟达": "科技",
    "META": "科技",
    "特斯拉": "科技",
    "甲骨文": "科技",
    "ORACLE": "科技",
    "英特尔": "科技",
    "INTC": "科技",
    "AMD": "科技",
    "高通": "科技",
    "博通": "科技",
    "BROADCOM": "科技",
    "思科": "科技",
    "CISCO": "科技",
    "IBM": "科技",
    "SALESFORCE": "科技",
    "CRM": "科技",
    "ADOBE": "科技",
    "INTUIT": "科技",
    "SERVICENOW": "科技",
    # 科技 - 光通信/算力（常见 A 股标的）
    "新易盛": "科技",
    "天孚": "科技",
    "太辰光": "科技",
    "旭创": "科技",
    "光模块": "科技",
    "光通信": "科技",
    "算力": "科技",
    "服务器": "科技",
    "光迅": "科技",
    "浪潮": "科技",
    "曙光": "科技",
    # 科技 - 半导体（设计/设备/封测）
    "中芯": "科技",
    "北方华创": "科技",
    "韦尔": "科技",
    "兆易": "科技",
    "卓胜微": "科技",
    "圣邦": "科技",
    "士兰微": "科技",
    "华大九天": "科技",
    "紫光": "科技",
    "中科曙光": "科技",
    "景嘉微": "科技",
    "长电": "科技",
    "通富": "科技",
    "华天": "科技",
    "沪电": "科技",
    "深南电路": "科技",
    # 科技 - 软件/互联网
    "金山办公": "科技",
    "用友": "科技",
    "广联达": "科技",
    "科大讯飞": "科技",
    "恒生电子": "科技",
    "中科创达": "科技",
    "同花顺": "科技",
    "财富趋势": "科技",
    # 科技 - 安防/通信运营商
    "海康": "科技",
    "大华": "科技",
    "中国联通": "科技",
    "中国电信": "科技",
    "中国移动": "科技",
    # 科技 - 金融科技
    "东方财富": "金融",
    # 金融 - 美股权重股
    "摩根大通": "金融",
    "高盛": "金融",
    "摩根士丹利": "金融",
    "美国银行": "金融",
    "花旗": "金融",
    "富国": "金融",
    "VISA": "金融",
    "万事达": "金融",
    # 消费 - 美股权重股
    "可口可乐": "消费",
    "百事": "消费",
    "沃尔玛": "消费",
    "COSTCO": "消费",
    "好市多": "消费",
    "宝洁": "消费",
    "麦当劳": "消费",
    "星巴克": "消费",
    "耐克": "消费",
    # 医药 - 美股权重股（重复关键词会被前面医药块覆盖，但显式列出方便检查）
    "强生": "医药",
    "辉瑞": "医药",
    "默克": "医药",
    "礼来": "医药",
    "联合健康": "医药",
    "艾伯维": "医药",
    # 通信 - 美股权重股
    "DISNEY": "消费",
    "迪士尼": "消费",
    "NETFLIX": "科技",
    "奈飞": "科技",
    "COMCAST": "科技",
    # 新能源
    "新能源": "新能源",
    "光伏": "新能源",
    "锂电": "新能源",
    "电池": "新能源",
    "风电": "新能源",
    "氢能": "新能源",
    "新能源车": "新能源",
    "电车": "新能源",
    "储能": "新能源",
    "宁德时代": "新能源",
    "比亚迪": "新能源",
    "隆基": "新能源",
    "太阳": "新能源",
    "硅": "新能源",
    "晶澳": "新能源",
    "晶科": "新能源",
    "天合": "新能源",
    "阳光电源": "新能源",
    "亿纬": "新能源",
    "恩捷": "新能源",
    "天赐": "新能源",
    "赣锋": "新能源",
    "天齐锂": "新能源",
    "华友": "新能源",
    "福莱特": "新能源",
    "福斯特": "新能源",
    # 食品饮料（消费子类细化）
    "伊利": "消费",
    "海天": "消费",
    "金龙鱼": "消费",
    "双汇": "消费",
    "安井": "消费",
    "涪陵": "消费",
    "东鹏": "消费",
    "农夫山泉": "消费",
    # 金融 - A 股
    "中国人保": "金融",
    "新华保险": "金融",
    "中国银河": "金融",
    "光大证券": "金融",
    "招商证券": "金融",
    # 制造 - 材料/矿业
    "紫金": "制造",
    "洛阳钼业": "制造",
    "江西铜业": "制造",
    "中国铝业": "制造",
    "南山铝业": "制造",
    "万华": "制造",
    "宝钢": "制造",
    "鞍钢": "制造",
    "海螺": "制造",
    "华新水泥": "制造",
    "中国巨石": "制造",
    # 制造 - 机械
    "潍柴": "制造",
    "中联重科": "制造",
    "三一": "制造",
    "徐工": "制造",
    "恒立": "制造",
    "汇川": "制造",
    # 医药 - A 股补充
    "长春高新": "医药",
    "智飞": "医药",
    "沃森": "医药",
    "康泰": "医药",
    "通策": "医药",
    "凯莱英": "医药",
    "康龙化成": "医药",
    "泰格": "医药",
    "益丰": "医药",
    "同仁堂": "医药",
    "白云山": "医药",
    "片仔癀": "医药",
    "东阿": "医药",
    "云南白药": "医药",
    # 消费 - 细分赛道
    "珀莱雅": "消费",
    "贝泰妮": "消费",
    "华熙": "医药",
    "安踏": "消费",
    "李宁": "消费",
    "波司登": "消费",
    "牧原": "农业",
    "温氏": "农业",
    "圣农": "农业",
    "大北农": "农业",
    "隆平高科": "农业",
    # 金融
    "银行": "金融",
    "证券": "金融",
    "保险": "金融",
    "信托": "金融",
    "券商": "金融",
    "互联网金融": "金融",
    "金融": "金融",
    # 制造
    "机械": "制造",
    "装备": "制造",
    "制造": "制造",
    "工业": "制造",
    "化工": "制造",
    "材料": "制造",
    "钢铁": "制造",
    "有色": "制造",
    "金属": "制造",
    "建材": "制造",
    "玻璃": "制造",
    "水泥": "制造",
    "造纸": "制造",
    "包装": "制造",
    "轻工": "制造",
    "重工": "制造",
    "电气": "制造",
    "仪器": "制造",
    # 地产基建
    "地产": "地产基建",
    "房产": "地产基建",
    "万科": "地产基建",
    "建设": "地产基建",
    "基建": "地产基建",
    "建筑": "地产基建",
    "工程": "地产基建",
    "中铁": "地产基建",
    "中交": "地产基建",
    "路桥": "地产基建",
    "市政": "地产基建",
    # 军工
    "军工": "军工",
    "航天": "军工",
    "国防": "军工",
    "中航": "军工",
    "船舶": "军工",
    "中国重工": "军工",
    # 能源资源
    "能源": "能源资源",
    "煤炭": "能源资源",
    "石油": "能源资源",
    "天然气": "能源资源",
    "电力": "能源资源",
    "核电": "能源资源",
    "水电": "能源资源",
    "中国神华": "能源资源",
    "中国海油": "能源资源",
    "中石油": "能源资源",
    "中石化": "能源资源",
    # 交通物流
    "运输": "交通物流",
    "物流": "交通物流",
    "快递": "交通物流",
    "航空": "交通物流",
    "机场": "交通物流",
    "港口": "交通物流",
    "高速": "交通物流",
    "航运": "交通物流",
    "铁路": "交通物流",
    # 农业
    "农业": "农业",
    "牧": "农业",
    "农": "农业",
    "种业": "农业",
    "猪": "农业",
    "鸡": "农业",
    "饲料": "农业",
    # 公用事业
    "水务": "公用事业",
    "燃气": "公用事业",
    "环保": "公用事业",
    "环境": "公用事业",
    "垃圾": "公用事业",
}


def classify_sector(name: str, _code: str = "") -> str:
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


def _classify_and_group(
    holdings: list[Holding],
    details: list[DetailRow],
) -> tuple[dict[str, list[Holding]], list[Holding], list[Holding], dict[str, float]]:
    """按穿透类型分类持仓，分离基金/直接持股，构建市值映射。

    Note:
        detail_map 返回 ``{code: total_market_value}``，已按代码聚合所有账户市值。
        funds / direct_stocks 已按代码去重，避免同一基金/股票因跨账户多次归属。
    """
    classified: dict[str, list[Holding]] = {
        QDII: [],
        ETF: [],
        INDEX_LINK: [],
        BOND_FUND: [],
        ACTIVE_EQUITY: [],
        STOCK: [],
        IGNORE: [],
    }
    for h in holdings:
        cat = classify_penetration(h)
        (classified[cat] if cat in classified else classified[IGNORE]).append(h)

    fund_types = [QDII, ETF, INDEX_LINK, BOND_FUND, ACTIVE_EQUITY]
    funds: list[Holding] = []
    for ft in fund_types:
        funds.extend(classified[ft])
    direct_stocks = classified[STOCK]

    # ── detail_map：按代码聚合总市值（同一代码跨账户时累加） ──
    detail_map: dict[str, float] = {}
    for d in details:
        detail_map[d.code] = detail_map.get(d.code, 0.0) + d.market_value

    # ── funds / direct_stocks 按代码去重（跨账户时只处理一次） ──
    def _dedup_by_code(items: list[Holding]) -> list[Holding]:
        seen: set[str] = set()
        result: list[Holding] = []
        for item in items:
            if item.code not in seen:
                seen.add(item.code)
                result.append(item)
        return result

    funds = _dedup_by_code(funds)
    direct_stocks = _dedup_by_code(direct_stocks)

    return classified, funds, direct_stocks, detail_map


def _prefetch_manager_data(code: str) -> None:
    """预取基金经理数据并写入缓存（供 B2 变更监控使用）。

    与 fetch_fund_holdings 共用同一基金主页面 HTML，首次调用
    时发起 HTTP 请求，后续运行命中缓存（TTL=1天）零额外请求。
    此函数不阻塞穿透逻辑——经理数据不可用时仅打印调试日志。
    """
    try:
        manager = fetch_fund_manager(code)
        if manager is None:
            logger.debug("基金经理预取失败 [%s]（不阻塞穿透计算）", code)
    except Exception:
        logger.debug("基金经理预取异常 [%s]（不阻塞穿透计算）", code, exc_info=True)


def _merge_fund_layer(
    funds: list[Holding],
    detail_map: dict[str, float],
) -> tuple[dict[str, Any], float, int, list[dict[str, str]]]:
    """合并基金层穿透，返回 merged 字典 + 统计值。"""
    merged: dict[str, Any] = {}
    unknown_mv = 0.0
    failed_count = 0
    failed_fund_details: list[dict[str, str]] = []

    for fund in funds:
        fund_mv = detail_map.get(fund.code, 0.0)
        ftype = classify_penetration(fund)
        tag = _fund_type_tag(ftype)

        holdings_data = fetch_fund_holdings(fund.code)
        # 同页面顺带获取基金经理数据并缓存，供 B2 基金经理变更监控使用
        _prefetch_manager_data(fund.code)

        if holdings_data is None or not holdings_data.get("holdings"):
            unknown_mv += fund_mv
            failed_count += 1
            failed_fund_details.append({"name": fund.name, "code": fund.code})
            # 不把基金本身加入 merged — 穿透结果只反映可识别的底层标的
            # 基金全值计入 unknown_mv 并在页脚提示，不污染 TOP10
            continue

        # 过滤无效持仓比例（<= 0 或 > 100），一些基金（如黄金 ETF）的
        # 天天基金 API 可能返回垃圾数据（ratio 如 401%/399% 等）
        valid_items = [item for item in holdings_data["holdings"] if 0 < item.get("ratio", 0) <= 100]
        if not valid_items:
            unknown_mv += fund_mv
            failed_count += 1
            failed_fund_details.append({"name": fund.name, "code": fund.code})
            logger.info(
                "基金 %s(%s) 所有持仓比例无效（包含 %s），已排除",
                fund.name,
                fund.code,
                [h.get("ratio", 0) for h in holdings_data["holdings"]],
            )
            continue

        for item in valid_items:
            stock_name = item.get("name", "").strip()
            stock_code = item.get("code", "").strip()
            ratio = item.get("ratio", 0.0)
            if not stock_name:
                continue
            attributed_mv = fund_mv * (ratio / 100.0)
            norm_name = normalize_name(stock_name)
            sector = classify_sector(stock_name, stock_code)
            if norm_name not in merged:
                merged[norm_name] = {
                    "name": stock_name,
                    "codes": set(),
                    "mv": 0.0,
                    "funds": [],
                    "sector": sector,
                }
            if stock_code:
                merged[norm_name]["codes"].add(stock_code)
            merged[norm_name]["mv"] += attributed_mv
            merged[norm_name]["funds"].append(f"[{tag}] {fund.name}({fund.code})")

    return merged, unknown_mv, failed_count, failed_fund_details


def _merge_stock_layer(
    direct_stocks: list[Holding],
    detail_map: dict[str, float],
    merged: dict[str, Any],
) -> None:
    """将直接持股合并入 merged 字典（原地修改）。"""
    for stock in direct_stocks:
        stock_mv = detail_map.get(stock.code, 0.0)
        norm_name = normalize_name(stock.name)
        sector = classify_sector(stock.name, stock.code)
        if norm_name not in merged:
            merged[norm_name] = {
                "name": stock.name,
                "codes": {stock.code},
                "mv": 0.0,
                "funds": [],
                "sector": sector,
            }
        else:
            merged[norm_name]["codes"].add(stock.code)
        merged[norm_name]["mv"] += stock_mv
        merged[norm_name]["funds"].append("直接持有")


def _enrich_with_industry_api(merged: dict[str, Any]) -> tuple[bool, str]:
    """用 API 行业数据补充板块分类和概念（原地修改）。

    Returns:
        (success, failure_type)
        - success=True 表示 API 获取成功（可能有部分数据）
        - success=False 时 failure_type 为 ``"unreachable"``（连接失败）或 ``"empty"``（无可用代码/空响应）
    """
    try:
        all_codes: list[str] = []
        for info in merged.values():
            all_codes.extend(info.get("codes") or [])
        if not all_codes:
            return False, "empty"
        from src.python.fetcher.industry import batch_fetch_industry_data as batch_ind

        ind_data = batch_ind(list(set(all_codes)))
        if ind_data:
            for info in merged.values():
                for code in info.get("codes") or []:
                    if code in ind_data:
                        id_rec = ind_data[code]
                        if id_rec.get("industry"):
                            info["sector_api"] = id_rec["industry"]
                            info["sector"] = id_rec["industry"]
                        if id_rec.get("concepts"):
                            info["concepts"] = id_rec["concepts"]
                        break
            return True, ""
        logger.warning("[penetration] 行业分类 API 返回空数据（非关键）")
        return False, "empty"
    except Exception:
        logger.warning("[penetration] 行业分类 API 获取失败（非关键）", exc_info=True)
        return False, "unreachable"


def _build_penetration_result(
    merged: dict[str, Any],
    classified: dict[str, list[Holding]],
    funds: list[Holding],
    direct_stocks: list[Holding],
    unknown_mv: float,
    failed_count: int,
    failed_fund_details: list[dict[str, str]],
) -> dict[str, Any]:
    """从合并数据生成穿透 TOP10 返回字典。"""
    total_mv = sum(v["mv"] for v in merged.values())
    sorted_items = sorted(merged.items(), key=lambda x: x[1]["mv"], reverse=True)

    fund_breakdown = " + ".join(
        f"{cl}{len(classified[c])}"
        for c, cl in [
            (QDII, "QDII"),
            (ETF, "ETF"),
            (INDEX_LINK, "联接"),
            (BOND_FUND, "债券"),
            (ACTIVE_EQUITY, "主动"),
        ]
        if classified[c]
    )

    top10_list = []
    for rank, (_, info) in enumerate(sorted_items[:10], 1):
        ratio = info["mv"] / total_mv * 100 if total_mv > 0 else 0.0
        top10_list.append(
            {
                "rank": rank,
                "name": info["name"],
                "codes": sorted(info["codes"]) if info["codes"] else [],
                "mv": round(info["mv"], 2),
                "ratio_pct": round(ratio, 2),
                "sector": info.get("sector", "--"),
                "concepts": (info.get("concepts") or [])[:3],
                "sources": sorted(set(info["funds"])),
            }
        )

    if not top10_list:
        logger.warning("[penetration] 天天基金持仓解析结果为空，穿透表不可用")

    top10_coverage = sum(v["mv"] for _, v in sorted_items[:10]) / total_mv * 100 if total_mv > 0 else 0.0

    return {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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


def compute_penetration_top10(
    holdings: list[Holding],
    details: list[DetailRow],
) -> dict[str, Any]:
    """计算资产穿透TOP10，返回结构化数据。

    Excel 写入见 :func:`src.python.report.penetration_sheet.write_penetration_sheet`。

    Args:
        holdings: 原始持仓列表
        details: 市值核算明细行列表

    Returns:
        {
            "update_time": "...",
            "summary": {...},
            "top10": [...],
        }
    """
    classified, funds, direct_stocks, detail_map = _classify_and_group(holdings, details)
    merged, unknown_mv, failed_count, failed_fund_details = _merge_fund_layer(funds, detail_map)
    _merge_stock_layer(direct_stocks, detail_map, merged)
    industry_success, industry_failure_type = _enrich_with_industry_api(merged)
    result = _build_penetration_result(
        merged,
        classified,
        funds,
        direct_stocks,
        unknown_mv,
        failed_count,
        failed_fund_details,
    )
    result["industry_success"] = industry_success
    if not industry_success:
        result["industry_failure_type"] = industry_failure_type
    return result
