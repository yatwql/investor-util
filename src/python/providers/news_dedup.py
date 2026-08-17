"""新闻去重模块 — 标题模糊去重 + 实体 bigram 辅助判定 + 锚点采集。

包含 _dedup_by_title 去重核心逻辑及其依赖的所有常量和辅助函数。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 锚点采集（阈值校准用） ──────────────────────────────────────
# 每次 _dedup_by_title 运行后，边界案例收集到此列表，
# aggregate_news() 结束时追写至 data/calibration/dedup_anchors.jsonl。
# 一条记录为一个 JSON 行，append-only。格式：
#   {"ts","title_a","title_b","source_a","source_b",
#    "ratio","bigram_overlap","decision","rule"}
_ANCHOR_RECORDS: list[dict[str, Any]] = []
_ANCHOR_LOCK = threading.Lock()
_ANCHOR_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "calibration",
    "dedup_anchors.jsonl",
)

# 进程级"已写锚点 key"集合 — 防止同一对 (source,title) 在多轮运行中重复追加。
# 背景：锚点文件 append-only，同一对新闻在每次真实抓取进入候选区时都会重新记录，
# 多轮后同一对重复数十次（实测 calibration 文件 61.6% 为重复记录），使校准报告
# 绝对数字严重失真（如 cross_skip bg=0 从 279 虚增至 13800）。
# 方案：首次 flush 时惰性加载现有文件 key 到内存集合，之后每次 flush 只写
# 不在集合中的新 key、写后加入。跨会话、跨轮次均拦截重复，避免每次读全文件。
_WRITTEN_ANCHOR_KEYS: set[str] = set()
_WRITTEN_KEYS_LOADED = False
_WRITTEN_KEYS_LOCK = threading.Lock()


def _anchor_key(record: dict[str, Any]) -> str:
    """锚点去重键：source 对 + 标题对（顺序无关）。"""
    a = (record.get("source_a", "") or "", record.get("title_a", "") or "")
    b = (record.get("source_b", "") or "", record.get("title_b", "") or "")
    # 排序使 (A,B) 与 (B,A) 视为同一对，避免来源顺序不同产生重复
    sa, ta = (a, b) if a <= b else (b, a)
    return f"{sa[0]}|{sa[1]}|{ta[0]}|{ta[1]}"


def _load_written_keys() -> None:
    """惰性加载锚点文件已有 key 到 _WRITTEN_ANCHOR_KEYS（进程生命周期内一次）。

    首次 flush 前调用，读一次现有文件（~110k 行/35MB，一次性成本），
    之后所有 flush 仅内存比对。文件不存在或为空时静默返回空集合。
    """
    global _WRITTEN_KEYS_LOADED
    with _WRITTEN_KEYS_LOCK:
        if _WRITTEN_KEYS_LOADED:
            return
        _WRITTEN_KEYS_LOADED = True
        if not os.path.exists(_ANCHOR_PATH):
            return
        try:
            with open(_ANCHOR_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    _WRITTEN_ANCHOR_KEYS.add(_anchor_key(rec))
        except OSError:
            logger.warning("锚点 key 加载失败: %s", _ANCHOR_PATH)


def _record_anchor(record: dict[str, Any]) -> None:
    """线程安全地追加一条锚点记录。"""
    with _ANCHOR_LOCK:
        _ANCHOR_RECORDS.append(record)


def _normalize_title(title: str) -> str:
    """标准化标题：去标点、去空格、去常见前缀，过滤通用数字模式降虚高。

    数字模式（百分比、金额、年份、排名标记）在不同新闻中可能无意共享，导致
    SequenceMatcher 比率虚高和实体 bigram 中数字 token 的虚假重叠。
    过滤后同时降低 bigram 提取噪声和比率比较的误判。

    用于跨源标题去重，消除"快讯：""收评"等差异。
    """
    for prefix in (
        "快讯",
        "收评",
        "收盘",
        "早评",
        "午评",
        "盘中",
        "盘后",
        "数据图解",
        "CCI快报",
        "市场动态",
        "市场洞察",
        "行业深度",
        "周刊提前读",
        "公司观察",
        "量化观察",
        "刷屏",
        "尾盘",
        "华尔街见闻早餐",
    ):
        if title.startswith(prefix):
            title = title[len(prefix) :]
            break
    # 过滤通用数字模式，避免跨源去重时不同新闻因共享
    # "20%""25亿"等数字模式而获得虚高 SequenceMatcher 比率。
    # 日期模式（2026年/7月/8日）已在 _dedup_by_title 的 _RATIO_CLEAN 中处理，
    # 但前导日期（如 "7月18日美股成交额前20"）在 bigram 提取前剥离。
    title = re.sub(r"\d+(?:\.?\d+)?%", "", title)  # 20%、2.5%
    title = re.sub(r"\d+(?:\.?\d+)?[万亿]", "", title)  # 25亿、1.2万亿
    # 孤立 4 位年份数字（如 "WAIC 2026" → "WAIC"），避免不同年报道因共享英文
    # 事件名 + 不同年份标识导致 SequenceMatcher 比率虚高。
    title = re.sub(r"(?<=[a-zA-Z])\s*\d{4}\b", "", title)
    # 排名/列表标记（"前20""前10"），可安全移除的修饰语
    title = re.sub(r"前\d+", "", title)
    # 孤立 4 位年份数字（1900-2099），避免不同新闻因共享"2026"等年份数字
    # 在实体 bigram 提取和 SequenceMatcher 中产生虚假重叠。
    title = re.sub(r"\b(?:19|20)\d{2}\b", "", title)
    # 地震等量级模式（"3.5级""4.4级"），剥离后避免"级地震"模板虚高
    title = re.sub(r"\d+(?:\.?\d+)?级", "", title)
    # ⚠ 保留空格：剥离标点但保留单词间空格，避免英文 token 粘连
    # （"Blackwell AI" → blackwellai 无法切分，导致同事件两标题英文 token 不重叠）。
    title = re.sub(r"[^\w一-鿿 ]", "", title)
    return title.strip().lower()


def _make_anchor(
    item_a: dict[str, Any],
    item_b: dict[str, Any],
    ratio: float,
    bigram_overlap: int,
    merged: bool,
    rule: str,
) -> dict[str, Any]:
    """构建一条锚点记录（边界案例），用于后续阈值校准。"""
    return {
        "ts": item_a.get("ctime", "") or item_b.get("ctime", ""),
        "title_a": item_a.get("title", ""),
        "title_b": item_b.get("title", ""),
        "source_a": item_a.get("_source", ""),
        "source_b": item_b.get("_source", ""),
        "ratio": round(ratio, 3),
        "bigram_overlap": bigram_overlap,
        "merged": merged,
        "rule": rule,
    }


def _flush_anchors() -> None:
    """将内存中的锚点记录追写到 JSONL 文件，然后清空列表。

    一次运行产生数十条记录（~200 字节/条），文件写入发生在去重完成后，
    不影响新闻获取和报告生成的主流程。

    写入前按 (source,title) 对去重：只写本次尚未写入文件的记录（查
    _WRITTEN_ANCHOR_KEYS），写后加入集合。防止同一对新闻多轮运行重复
    追加导致校准数字失真（见 _WRITTEN_ANCHOR_KEYS 注释）。
    """
    global _ANCHOR_RECORDS
    if not _ANCHOR_RECORDS:
        return
    with _ANCHOR_LOCK:
        records = _ANCHOR_RECORDS
        _ANCHOR_RECORDS = []  # 先清空再写，防止递归写入
    _load_written_keys()
    new_records: list[dict[str, Any]] = []
    with _WRITTEN_KEYS_LOCK:
        for r in records:
            key = _anchor_key(r)
            if key in _WRITTEN_ANCHOR_KEYS:
                continue
            _WRITTEN_ANCHOR_KEYS.add(key)
            new_records.append(r)
    if not new_records:
        return
    try:
        os.makedirs(os.path.dirname(_ANCHOR_PATH), exist_ok=True)
        with open(_ANCHOR_PATH, "a", encoding="utf-8") as f:
            for r in new_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("锚点文件写入失败: %s", e)


# ── 高频财经常见动词/形容词/副词 — 不作为实体判定依据 ──────
# ⚠ 2026-08-17 校准扩充：财报/回购/指数/预警/地震/目标价等模板词
# 此前未覆盖，导致任何两条同类新闻（不同公司业绩快报、回购公告、指数行情、
# 天气预警）天然共享 3-6 个 bigram，跨源 bg≥3 形同虚设（实测误合并 ~70-80%）。
# 提取 bigram 前先整体掩码替换为占位符（见 _mask_stop），彻底消除模板词贡献，
# 也杜绝"累计|回购"跨词边界 bigram（计回）泄漏。
_STOP_BIGRAMS: set[str] = {
    # 原有高频动词/形容词
    "上调",
    "下跌",
    "上涨",
    "超越",
    "低于",
    "高于",
    "首次",
    "今日",
    "昨日",
    "本周",
    "上周",
    "本月",
    "上月",
    "盘中",
    "盘后",
    "早盘",
    "午盘",
    "收盘",
    "开盘",
    "不会",
    "将会",
    "成为",
    "宣布",
    "公布",
    "发布",
    "推动",
    "发力",
    "实现",
    "加大",
    "降低",
    "回升",
    "有望",
    "再度",
    "时隔",
    # 高频数理/报道用词
    "同比",
    "环比",
    "预计",
    "累计",
    "显示",
    "预期",
    "影响",
    "明显",
    "相关",
    "报告",
    "数据",
    "来源",
    "表示",
    "认为",
    "其中",
    "分别",
    "总额",
    "规定",
    # ── 财报/业绩模板词 ──
    "增长",
    "下降",
    "上升",
    "下滑",
    "扭亏",
    "为盈",
    "大增",
    "大降",
    "翻倍",
    "净利",
    "利润",
    "归母",
    "营收",
    "收入",
    "业绩",
    "预增",
    "预减",
    "超出",
    "不及",
    "符合",
    "超过",
    "达到",
    "接近",
    "突破",
    "创下",
    "创出",
    "创新",
    "同期",
    "季度",
    "半年",
    "年度",
    "第一",
    "第二",
    "第三",
    "第四",
    "发生",
    "截至",
    "补充",
    "暂缓",
    "目前",
    "此前",
    "近日",
    "今天",
    "明天",
    # ── 资本运作模板词 ──
    "回购",
    "增持",
    "减持",
    "股份",
    "注销",
    "股权",
    "持股",
    "股东",
    "市值",
    "股价",
    "股本",
    "流通",
    "重组",
    "并购",
    "收购",
    "出售",
    "转让",
    "质押",
    "解禁",
    "分红",
    "派息",
    "定增",
    "配股",
    "控股",
    "全资",
    "旗下",
    "子公司",
    "母公司",
    "融资",
    "募资",
    "投资",
    "入股",
    "参股",
    # ── 行情/指数模板词 ──
    "指数",
    "涨幅",
    "跌幅",
    "走强",
    "走弱",
    "收涨",
    "收跌",
    "低开",
    "高开",
    "翻红",
    "翻绿",
    "涨停",
    "跌停",
    "大涨",
    "大跌",
    "暴涨",
    "暴跌",
    "反弹",
    "回落",
    "成交",
    "成交量",
    "成交额",
    "板块",
    "主力",
    "资金",
    "净买",
    "净卖",
    "流入",
    "流出",
    "美股",
    "港股",
    "a股",
    "期指",
    "期货",
    "合约",
    "基准",
    "点位",
    "关口",
    "大关",
    "涨超",
    "跌超",
    "盘初",
    "新高",
    "新低",
    "扩大",
    "收窄",
    # ── 预警/天气模板词 ──
    "预警",
    "暴雨",
    "台风",
    "高温",
    "橙色",
    "红色",
    "黄色",
    "蓝色",
    "地震",
    "震源",
    "深度",
    "洪水",
    "干旱",
    "寒潮",
    "霜冻",
    "雷电",
    "大风",
    "冰雹",
    "信号",
    "海啸",
    # ── 评级/观点模板词 ──
    "评级",
    "目标价",
    "目标",
    "买入",
    "卖出",
    "持有",
    "下调",
    "重申",
    "给予",
    "维持",
    "看多",
    "看空",
    "中性",
    "超配",
    "低配",
    "展望",
    "判断",
    "加息",
    "降息",
    # ── 新闻格式模板词 ──
    "报道",
    "消息",
    "回应",
    "澄清",
    "声明",
    "公告",
    "通知",
    "提醒",
    "提示",
    "出炉",
    "落地",
    "进展",
    "更新",
    "详情",
    "汇总",
    "速览",
    "快讯",
    "披露",
    "获悉",
    "透露",
    "据悉",
    "知情",
    # ── 连接/修饰词 ──
    "拟将",
    "或将",
    "已获",
    "共计",
    "合计",
    "凌晨",
    "上午",
    "下午",
    "晚间",
    "深夜",
    "同时",
    "此外",
    "本次",
    "可能",
    "或许",
    "仍然",
    "依然",
    "已经",
    "正在",
    "即将",
    "日前",
    "年内",
    "至今",
    "计划",
    "方案",
    "主席",
    "会议",
    # ── 数量/货币/单位 ──
    "金额",
    "规模",
    "价值",
    "合同",
    "订单",
    "签约",
    "中标",
    "招标",
    "额度",
    "数量",
    "港元",
    "美元",
    "欧元",
    "日元",
    "英镑",
    "韩元",
    "澳元",
    "加元",
    "人民币",
    "泰铢",
    "卢布",
    "台币",
    "万股",
    "亿股",
    # ── 通用业务/技术名词 ──
    "公司",
    "集团",
    "业务",
    "产品",
    "项目",
    "政策",
    "措施",
    "机制",
    "体系",
    "结构",
    "升级",
    "转型",
    "布局",
    "推进",
    "深化",
    "优化",
    "完善",
    "健全",
    "加强",
    "强化",
    "模式",
    "场景",
    "平台",
    "生态",
    "赛道",
    "行业",
    "科技",
    "芯片",
    "算力",
    "服务",
    "签订",
    "恢复",
    "设备",
    "检查",
    "工厂",
    "工作",
    "需要",
    "时间",
    "性能",
    "采用",
    # ── 地区修饰词 ──
    "全国",
    "全球",
    "国际",
    "国内",
    "海外",
    "境内",
    "境外",
}

# 停用词掩码正则（长词优先，防重叠替换）：
# "累计回购" → "□□"，杜绝跨词边界 bigram（计回/购股）泄漏；
# 中文 bigram 提取时跳过含占位符的滑窗，使模板词彻底不贡献实体重叠。
_STOP_MASK_RE = re.compile(
    "|".join(re.escape(w) for w in sorted(_STOP_BIGRAMS, key=len, reverse=True))
)


def _mask_stop(text: str) -> str:
    """将停用模板词整体替换为占位符，供 bigram 提取前掩码。"""
    return _STOP_MASK_RE.sub("□", text)


def _extract_entity_bigrams(text: str) -> set[str]:
    """提取标题中的实体特征：中文 bigram + 英数 token + 长英文专名加权。

    中文实体判定依赖 2-gram 重叠；英数 token 补全"AI""AMD"等被中文
    正则过滤的专名；长度 ≥ 4 的英文专名（Anthropic/Meta/Helios 等）
    额外插入 _tk: 前缀虚拟 bigram，使共享专名在 bigram 计数中获得
    权重加成，避免因英文专名占比高但 token 条数少而漏过候选区。

    模板词（见 _STOP_BIGRAMS）在提取前被整体掩码替换为占位符，
    不产生任何中文 bigram——财报/回购/指数/预警等通用财经词汇不再
    虚增实体重叠（此前不同公司同类新闻天然共享 3-6 bigram）。
    孤立 4 位年份数字（2026 等）不作为专名 token。
    """
    # 英数 token：长度 ≥ 2 避免单字符噪声；孤立年份数字（19xx/20xx）
    # 为通用时间标识，不作专名。
    tokens = re.findall(r"[a-zA-Z]+|[0-9]+", text)
    result: set[str] = set()
    for t in tokens:
        t_lower = t.lower()
        if len(t_lower) >= 2 and not re.fullmatch(r"(?:19|20)\d{2}", t_lower):
            result.add(t_lower)
            # 长英文专名（≥4 字符）额外插入虚拟 bigram 占用位，
            # 提升共享专名在实体重叠计数中的权重（如 Anthropic+Meta
            # 在 bg 计数中额外贡献 2 点，使 bg=2+2=4 进入合并区）。
            if t_lower.isalpha() and len(t_lower) >= 4:
                result.add(f"_tk:{t_lower}")
    # 中文 bigram：先掩码模板词，再滑窗提取，跳过含占位符的窗口
    chinese_only = re.sub(r"[^一-鿿]", "", text)
    masked = _mask_stop(chinese_only)
    for i in range(len(masked) - 1):
        bg = masked[i : i + 2]
        if "□" in bg:
            continue
        result.add(bg)
    return result


# 用于 SequenceMatcher 的归一化——剥离通用日期模式，避免
# "2026年7月票房破25亿" 与 "2026年7月经营质量因子" 等完全不同的
# 新闻因共享日期格式而获得虚高 ratio，进入不必要的候选区。
# ⚠ 仅用于 ratio 计算，不影响 kept_norms（后者用于 bigram 提取）。
_RATIO_CLEAN = re.compile(r"\d{4}年|\d+月|\d+日")
# 英文词占位化：用于 ratio 比较时降权共享英文专名（Anthropic/Meta 等），
# 避免 SequenceMatcher 比率虚高。英文专名在 _extract_entity_bigrams
# 中已有独立处理，不影响 bigram 提取。
# ⚠ 按长度分桶占位（_tk2_/_tk4_/_tk6_）：统一 _tk_ 会让任意英文 token
# （msci/vn、ETF/CPI…）都共享同一占位符，人为抬高 ratio 0.1+；
# 分桶后仅同长度段英文词共享，恢复真实相似度。
_ENG_PLACEHOLDER = re.compile(r"[a-z]+")


def _eng_len_placeholder(match: re.Match) -> str:
    """按英文 token 长度分桶的占位符：2-3 字符 → _tk2_，4-5 → _tk4_，6+ → _tk6_。"""
    n = len(match.group())
    if n <= 2:
        return "_tk2_"
    if n <= 5:
        return "_tk4_"
    return "_tk6_"


# ── 跨源阈值常量（2026-08-17 校准定值） ──────────────────────────────
# 42560 锚点分层采样验证：旧规则（候选区 0.30 + bg≥3 任意 ratio、
# 安全区 0.50 直接合并、bg=2 梯度 0.40）误合并率 ~70-80%。新规则收紧：
#   - 安全区：ratio ≥ 0.65 直接合并（改写型重复）；0.50~0.65 需专名 bg ≥ 2
#     （防"算力服务合同""指数上涨 N%"等模板骨架把 ratio 推到 0.5+ 的误合并）
#   - 候选区：ratio ≥ 0.35 进区；bg ≥ 3 合并；bg=2 需 ratio ≥ 0.38
#     且共享 bigram 含英数/数字 token（纯中文公司名共享如"英伟达/伟达"
#     不代表同一事件，不再触发）
_CROSS_DIRECT_RATIO = 0.65
_CROSS_SAFE_RATIO = 0.50
_CROSS_BG2_RATIO = 0.375

# 跨源方向对立词对：共享实体 + 相反方向词分属两标题 → 不合并。
# 跨源会同时出现"暂缓加息"vs"将加息"这类方向对立报道，
# 而同源规则假设同源不出现对立报道——跨源必须显式防护。
_OPPOSITE_PAIRS: tuple[tuple[str, str], ...] = (
    ("上涨", "下跌"),
    ("加息", "降息"),
    ("增持", "减持"),
    ("上调", "下调"),
    ("买入", "卖出"),
    ("走强", "走弱"),
    ("收涨", "收跌"),
    ("扩大", "收窄"),
    ("大涨", "大跌"),
    ("涨停", "跌停"),
    ("新高", "新低"),
    ("看多", "看空"),
)

# 共享 bigram 中的英数/数字 token 或 _tk 虚拟专名（专名证据判定）
_TOKEN_LIKE = re.compile(r"^[a-z0-9]+$|^_tk:[a-z]+$")


def _has_opposite_direction(title_a: str, title_b: str) -> bool:
    """两标题是否含相反方向的词对（一正一反分属两标题）。"""
    return any(
        (w1 in title_a and w2 in title_b) or (w2 in title_a and w1 in title_b)
        for w1, w2 in _OPPOSITE_PAIRS
    )


def _dedup_by_title(
    items: list[dict[str, Any]],
    cross_threshold: float = 0.35,
) -> list[dict[str, Any]]:
    """基于标准化标题模糊去重 + 中文实体 bigram 辅助判定。

    五档阈值策略（2026-08-17 基于 42560 条锚点分层采样校准）：
      - 同源：共享实体 bigram ≥ 4 即合并。
        同源不会同时出现方向对立报道（如"突破3万亿"vs"跌破3万亿"），
        所以不依赖 SequenceMatcher 阈值，只检查实体重叠。
      - 跨源安全区：
        ① ratio ≥ 0.65 直接合并（高相似改写重复，如"英国央行如期维持利率不变"
           vs"英国央行以6比3票数维持利率不变"）
        ② 0.50 ≤ ratio < 0.65 需专名 bg ≥ 2 才合并——旧规则直接合并导致
           40-50% 误合并（"行云科技签算力合同"vs"亿田智能签算力合同"共享模板骨架）
      - 跨源候选区：cross_threshold(0.35) ≤ ratio < 0.50，阶梯判定：
        ③ 共享 ≥ 3 个实体 bigram → 合并（高实体重叠，低 ratio 门槛）
        ④ 共享 ≥ 2 个实体 bigram 且 ratio ≥ 0.38 且含英数/数字 token → 合并
           （CPI/PPI、荣耀IPO 类共享专名 token 的真重复；纯中文公司名共享
           如"英伟达/伟达"不代表同一事件，不触发）
        ⑤ 方向对立（上涨vs下跌/加息vs降息分属两标题）且共享实体 → 不合并
        ⑥ 否则跳过（实体重叠不足或 ratio 太低）

    模板词治理：_STOP_BIGRAMS 扩充财报/回购/指数/预警/地震/目标价等模板词，
    提取 bigram 前整体掩码替换（_mask_stop），消除同类新闻共享模板骨架的虚高
    重叠。英文专名占位按长度分桶（_tk2_/_tk4_/_tk6_），不同长度英文词不再
    共享相似度。_normalize_title 保留空格防英文 token 粘连。
    """
    from difflib import SequenceMatcher

    if not items:
        return items

    kept: list[dict[str, Any]] = []
    kept_norms: list[str] = []
    kept_sources: list[str] = []
    for item in items:
        norm = _normalize_title(item.get("title", ""))
        if not norm:
            kept.append(item)
            continue
        is_dup = False
        source = item.get("_source", "") or ""
        for idx, existing in enumerate(kept_norms):
            existing_src = kept_sources[idx]
            existing_item = kept[idx]
            same_source = bool(source) and bool(existing_src) and source == existing_src

            # ① 同源：共享实体 bigram ≥ 4 即合并
            if same_source:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                overlap = len(bg1 & bg2)
                if overlap >= 4:
                    is_dup = True
                    break
                # 锚点：同源 bigram 接近阈值
                if 2 <= overlap <= 5:
                    _record_anchor(_make_anchor(item, existing_item, 0.0, overlap, False, "same_src"))

            # ② 跨源安全区：ratio ≥ 0.65 直接合并；0.50~0.65 需专名 bg ≥ 2
            #    剥离通用日期模式后比较，避免不同新闻因共享"2026年7月"等虚高；
            #    英文专名按长度分桶占位，避免共享专名（Anthropic/Meta/AMD）导致
            #    SequenceMatcher 比率虚高（英文专名在 _extract_entity_bigrams
            #    中已有独立处理，ratio 中可降权）。
            _norm_clean = _RATIO_CLEAN.sub("", norm)
            _exist_clean = _RATIO_CLEAN.sub("", existing)
            _norm_clean = _ENG_PLACEHOLDER.sub(_eng_len_placeholder, _norm_clean)
            _exist_clean = _ENG_PLACEHOLDER.sub(_eng_len_placeholder, _exist_clean)
            # SequenceMatcher 贪心匹配方向不对称（含多个英文占位块的串上
            # ratio(a,b)≠ratio(b,a)，实测差异可达 0.18），取双向 max 消除
            # 方向偏差，保证同一对标题相似度判定与比较顺序无关。
            ratio = max(
                SequenceMatcher(None, _norm_clean, _exist_clean).ratio(),
                SequenceMatcher(None, _exist_clean, _norm_clean).ratio(),
            )
            if ratio >= _CROSS_SAFE_RATIO:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                overlap = len(bg1 & bg2)
                # ratio ≥ 0.65 直接合并也要求专名 bg ≥ 1：不同公司同模板
                # （"XX：2026年半年度净利润同比增长N%"）ratio 可高达 0.7+，
                # 但掩码后 bg=0（公司名不同），不能当作改写型重复。
                if ratio >= _CROSS_DIRECT_RATIO and overlap >= 1:
                    is_dup = True
                    break
                if overlap >= 2:
                    is_dup = True
                    # 锚点：跨源安全区合并样本（含擦边 0.50~0.65）
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_safe"))
                    break
                # 安全区但实体不足：跳过（记录锚点供校准，继续子串包含判定）
                _record_anchor(_make_anchor(item, existing_item, ratio, overlap, False, "cross_safe"))

            # ③ 跨源候选区：0.35 ≤ ratio < 0.50，需共享 ≥ 3 实体 bigram
            if not same_source and ratio >= cross_threshold:
                bg1 = _extract_entity_bigrams(norm)
                bg2 = _extract_entity_bigrams(existing)
                overlap = len(bg1 & bg2)
                # ④ 方向对立检测：共享实体 + 相反方向词分属两标题 → 不合并
                #    （"美联储或暂缓加息"vs"城堡证券预计美联储将加息"）
                if overlap >= 1 and _has_opposite_direction(norm, existing):
                    _record_anchor(
                        _make_anchor(item, existing_item, ratio, overlap, False, "cross_opposite")
                    )
                elif overlap >= 3:
                    is_dup = True
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge"))
                    break
                # ⑤ bg=2 梯度：中高 ratio + 共享英数/数字 token（专名）→ 合并
                #    纯中文实体共享（如"英伟达"2 bigram）不代表同一事件，不触发；
                #    CPI/PPI、荣耀IPO 等共享专名 token 的真重复靠此规则捕获。
                elif (
                    overlap >= 2
                    and ratio >= _CROSS_BG2_RATIO
                    and any(_TOKEN_LIKE.match(s) for s in (bg1 & bg2))
                ):
                    is_dup = True
                    _record_anchor(_make_anchor(item, existing_item, ratio, overlap, True, "cross_merge_bg2"))
                    break
                # 锚点：跨源候选区但 bigram 不足
                _record_anchor(_make_anchor(item, existing_item, ratio, overlap, False, "cross_skip"))

            # ⑥ 子串包含
            if not is_dup:
                short, long = (norm, existing) if len(norm) <= len(existing) else (existing, norm)
                if len(short) >= 6 and short in long:
                    is_dup = True
                    break

        if not is_dup:
            kept_norms.append(norm)
            kept_sources.append(source)
            kept.append(item)
    return kept
