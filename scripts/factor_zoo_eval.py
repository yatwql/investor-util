"""因子动物园目录评测工具（非生产代码，只住 scripts/；评测产物落 docs/tmp/factor-zoo/）。

先评测后立项：五个来源族各抽 5 个代表因子（共 25），三项指标——
A 字段可得率 ≥80%（≥20/25 因子可完整计算）、B 与既有信号族增量
（|ρ|<0.5 的因子占比 ≥30%、分母 ≥10）、C 全量计算耗时 ÷ 基线报告耗时 ≤20%。
A/B/C 全过 → 转正立项（另起实现计划）；任一不过 → 归档「已评估未采纳」。

纪律（设计文档约定）：
  - 取数只经既有 Provider Chain / 网关（fetch_with_incremental_fallback、
    fetch_index_history、fetch_valuation_fields、fetch_latest_indicator），禁裸调 provider；
  - 不 import report/llm，不向生产模块注入任何代码，生产侧零改动；
  - 穿透持仓股票池只读复用（不重算穿透逻辑），评测报告只落 docs/tmp/（git 忽略）；
  - 相关性复用 analysis.correlation 的共享 Pearson 原语（防评测口径与生产口径漂移）。

阶段（子命令，可单独重跑）：
  catalog  25 因子清单冻结（五族×5，字段需求与口径入 JSON）
  fields   穿透股票池冻结 + 逐因子字段可得性探测 → 指标 A
  signals  可计算因子近 1 年横截面信号 vs 既有信号族日频序列 → 指标 B
  timing   取数/计算耗时与缓存命中统计 + 真实报告耗时基线 → 指标 C
  verdict  三项指标汇总判定（阈值与口径预注册于判定书）
  all      依序执行全部阶段
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

# ── 项目路径（脚本独立运行，需先把仓库根加入 sys.path） ──────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 晚导入：sys.path 就绪后再引用项目模块（纯计算层，无网络）
from src.python.analysis.correlation import _pearson_pvalue  # noqa: E402  共享 Pearson + p 值

# ── 常量（门槛与口径在判定书中预注册，改这里等于改门槛） ──────────────
OUT_DIR_DEFAULT = _PROJECT_ROOT / "docs" / "tmp" / "factor-zoo"
THRESH_A = 0.80  # 字段可得率 ≥80%（≥20/25）
THRESH_B = 0.30  # 低相关（增量）因子占比 ≥30%
THRESH_C = 0.20  # 耗时增量 ≤20%
CORR_LOW = 0.5  # |ρ| < 0.5 计「低相关」
B_MIN_DENOM = 10  # 指标 B 分母下限（样本不足判不通过）
TYPE_COVERAGE = 0.80  # 字段类型可得 = 池内 ≥80% 代码有效
MIN_PAIRS = 30  # 相关性评估最少对齐样本（Δ 后）
MIN_CODES_PER_DAY = 3  # 横截面日均值最少成分数
STEP_NONZERO_FRACTION = 0.05  # Δ 非零占比低于此 = 步进/常量型信号（结构性不相关）
LOOKBACK_DAYS = 365  # 回看窗口（自然日，K 线链路按此折算交易日）
DAYS_PER_YEAR_TD = 250  # 「N 年」标签的交易日折算（保守口径，与成本模型同源）

FIELD_BARS = "bars"
FIELD_INDEX = "index"
FIELD_VAL = "valuation"
FIELD_FIN = "fin_indicator"
FIELD_TYPES = (FIELD_BARS, FIELD_INDEX, FIELD_VAL, FIELD_FIN)

FAMILY_MARKET_TEMPERATURE = "market_temperature"
FAMILY_VALUATION_PERCENTILE = "valuation_percentile"
FAMILY_TAIL_VAR = "tail_risk_var95"
FAMILY_STYLE_BETA = "style_beta"
FAMILY_REBALANCE = "rebalance_overflow"  # 快照域信号族（非日频）→ 降级不参与
FAMILY_DEGRADED = {
    FAMILY_REBALANCE: "再平衡超限为持仓快照域（非日频）信号族，无法构造日频序列，按设计降级不参与相关性评估"
}

BETA_WINDOW = 60  # 风格族滚动 Beta 窗口（交易日）
TEMPERATURE_SLICE = 120  # 温度族滚动窗口切片（覆盖 MIN_SAMPLES=60 + 缓冲）

FAMILY_NAMES = {
    FAMILY_MARKET_TEMPERATURE: "市场温度",
    FAMILY_VALUATION_PERCENTILE: "估值/价格分位（代理）",
    FAMILY_TAIL_VAR: "尾部风险 VaR95",
    FAMILY_STYLE_BETA: "风格 Beta",
    FAMILY_REBALANCE: "再平衡超限",
}

# ── 因子目录：五族 × 5（评测简化口径，族内可追溯到出处；不移植算子代码） ──
# fields ⊆ FIELD_TYPES；min_bars = 因子所需最少日 K 线条数（交易日）
CATALOG: list[dict[str, Any]] = [
    # qlib158 族：经典技术因子
    {
        "slug": "qlib_ma_cross",
        "family": "qlib158",
        "label": "均线交叉（close vs MA20）",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "(close-MA20)/MA20",
    },
    {
        "slug": "qlib_macd_hist",
        "family": "qlib158",
        "label": "MACD 柱（EMA12/26 与信号 9）",
        "fields": [FIELD_BARS],
        "min_bars": 45,
        "window": 26,
        "formula": "(EMA12-EMA26)-EMA9(差值)",
    },
    {
        "slug": "qlib_rsi_14",
        "family": "qlib158",
        "label": "RSI 14",
        "fields": [FIELD_BARS],
        "min_bars": 20,
        "window": 14,
        "formula": "14 日涨跌幅强度比",
    },
    {
        "slug": "qlib_beta_60",
        "family": "qlib158",
        "label": "60 日 Beta vs 沪深300",
        "fields": [FIELD_BARS, FIELD_INDEX],
        "min_bars": 65,
        "window": 60,
        "formula": "Cov(r,rm)/Var(rm)，复用 portfolio_beta 口径",
    },
    {
        "slug": "qlib_aroon_25",
        "family": "qlib158",
        "label": "Aroon 25（高低点回望）",
        "fields": [FIELD_BARS],
        "min_bars": 30,
        "window": 25,
        "formula": "(aroon_up-aroon_down)/100",
    },
    # alpha101 族：量价关系
    {
        "slug": "alpha_corr_cv_10",
        "family": "alpha101",
        "label": "10 日收盘-成交量相关（反向）",
        "fields": [FIELD_BARS],
        "min_bars": 15,
        "window": 10,
        "formula": "-corr(close, volume, 10)",
    },
    {
        "slug": "alpha_rev_open_10",
        "family": "alpha101",
        "label": "10 日开盘-成交量相关（延迟反转代理）",
        "fields": [FIELD_BARS],
        "min_bars": 15,
        "window": 10,
        "formula": "-corr(open, volume, 10)",
    },
    {
        "slug": "alpha_pvt_10",
        "family": "alpha101",
        "label": "10 日价量趋势 PVT",
        "fields": [FIELD_BARS],
        "min_bars": 15,
        "window": 10,
        "formula": "Σ(Δclose×volume)/Σvolume（10 日）",
    },
    {
        "slug": "alpha_corr_cv_20",
        "family": "alpha101",
        "label": "20 日收盘-成交量相关（反向）",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "-corr(close, volume, 20)",
    },
    {
        "slug": "alpha_vwma_dev_20",
        "family": "alpha101",
        "label": "收盘价对 20 日成交量加权均价偏离",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "(close-VWMA20)/VWMA20",
    },
    # gtja191 族：量价形态（评测简化口径）
    {
        "slug": "gtja_mom_20",
        "family": "gtja191",
        "label": "20 日动量",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "close/close[-20]-1",
    },
    {
        "slug": "gtja_rsv_9",
        "family": "gtja191",
        "label": "KD-J RSV 9",
        "fields": [FIELD_BARS],
        "min_bars": 12,
        "window": 9,
        "formula": "(close-low9)/(high9-low9)",
    },
    {
        "slug": "gtja_bias_60",
        "family": "gtja191",
        "label": "60 日乖离率",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "(close-MA60)/MA60",
    },
    {
        "slug": "gtja_atr_14",
        "family": "gtja191",
        "label": "ATR14 波动归一",
        "fields": [FIELD_BARS],
        "min_bars": 20,
        "window": 14,
        "formula": "TR14 均值/close",
    },
    {
        "slug": "gtja_pv_divergence",
        "family": "gtja191",
        "label": "量价背离（动量 × 量能趋势符号）",
        "fields": [FIELD_BARS],
        "min_bars": 25,
        "window": 20,
        "formula": "-sign(mom20)×sign(volume10 斜率)",
    },
    # academic 族：经典学术效应（日线代理口径）
    {
        "slug": "acad_max_60",
        "family": "academic",
        "label": "MAX 效应（60 日日内最大涨幅代理）",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "max(high/open-1, 60 日)（分钟口径的日线代理）",
    },
    {
        "slug": "acad_idio_vol_60",
        "family": "academic",
        "label": "特质波动率 60 日",
        "fields": [FIELD_BARS, FIELD_INDEX],
        "min_bars": 65,
        "window": 60,
        "formula": "std(r-rm, 60)",
    },
    {
        "slug": "acad_amihud_proxy_60",
        "family": "academic",
        "label": "非流动性 60 日（成交量代理）",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "mean(|r|/volume, 60)（无成交额字段，用量代理）",
    },
    {
        "slug": "acad_low_vol_60",
        "family": "academic",
        "label": "低波动率 60 日",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "std(日收益, 60)",
    },
    {
        "slug": "acad_skew_60",
        "family": "academic",
        "label": "收益偏度 60 日",
        "fields": [FIELD_BARS],
        "min_bars": 65,
        "window": 60,
        "formula": "skewness(日收益, 60)",
    },
    # fundamental 族：基本面（当前报告期截面值，步进信号）
    {
        "slug": "fund_roe",
        "family": "fundamental",
        "label": "净资产收益率 ROE",
        "fields": [FIELD_FIN],
        "min_bars": 0,
        "window": 0,
        "formula": "最新报告期 roe",
    },
    {
        "slug": "fund_revenue_yoy",
        "family": "fundamental",
        "label": "营业总收入同比增长率",
        "fields": [FIELD_FIN],
        "min_bars": 0,
        "window": 0,
        "formula": "最新报告期 revenue_yoy",
    },
    {
        "slug": "fund_gross_margin",
        "family": "fundamental",
        "label": "毛利率",
        "fields": [FIELD_FIN],
        "min_bars": 0,
        "window": 0,
        "formula": "最新报告期 gross_margin",
    },
    {
        "slug": "fund_pb",
        "family": "fundamental",
        "label": "市净率 PB",
        "fields": [FIELD_VAL],
        "min_bars": 0,
        "window": 0,
        "formula": "push2 f23 当前 PB",
    },
    {
        "slug": "fund_size_log_cap",
        "family": "fundamental",
        "label": "市值规模（对数）",
        "fields": [FIELD_VAL],
        "min_bars": 0,
        "window": 0,
        "formula": "ln(market_cap)（push2 透传）",
    },
]

FAMILIES = ["qlib158", "alpha101", "gtja191", "academic", "fundamental"]
FAMILY_LABELS = {
    "qlib158": "qlib158 技术因子族",
    "alpha101": "alpha101 量价族",
    "gtja191": "gtja191 量价形态族",
    "academic": "academic 学术效应族",
    "fundamental": "fundamental 基本面族",
}

BENCHMARK_INDEX = "sh000300"  # 市场相对族与因子统一基准

# 冷启动延迟样本（池外大盘股，仅测冷请求延迟，不入池；有缓存命中则标记）
COLD_SAMPLE_CODES = ["600519", "000858", "300750"]


# ═══════════════════════════════════════════════════════════════
#  阶段 1：目录构建与校验（纯逻辑，无 I/O 副作用）
# ═══════════════════════════════════════════════════════════════


def build_catalog() -> list[dict[str, Any]]:
    """返回冻结因子目录（五族 × 5，确定性：同输入同输出）。"""
    return [dict(item) for item in CATALOG]


def validate_catalog(catalog: list[dict[str, Any]]) -> list[str]:
    """目录完整性校验：25 条、五族各 5、slug 唯一、字段类型合法、族名合法。"""
    problems: list[str] = []
    if len(catalog) != 25:
        problems.append(f"目录条数 {len(catalog)} != 25")
    slugs = [item.get("slug") for item in catalog]
    if len(set(slugs)) != len(slugs):
        problems.append("slug 存在重复")
    for family in FAMILIES:
        n = sum(1 for item in catalog if item.get("family") == family)
        if n != 5:
            problems.append(f"族 {family} 条数 {n} != 5")
    for item in catalog:
        fields = item.get("fields") or []
        if not fields:
            problems.append(f"{item.get('slug')}: fields 为空")
        for field in fields:
            if field not in FIELD_TYPES:
                problems.append(f"{item.get('slug')}: 未知字段类型 {field}")
        if not item.get("label") or not item.get("formula"):
            problems.append(f"{item.get('slug')}: 缺 label/formula")
    return problems


# ═══════════════════════════════════════════════════════════════
#  阶段 2：股票池与字段可得性（经既有链路取数；网络层可注入替换）
# ═══════════════════════════════════════════════════════════════


def build_stock_pool(holdings_path: str) -> dict[str, Any]:
    """穿透持仓股票池（只读复用穿透模块输出 + 直接持仓 A 股）。

    返回 {"codes": [...升序唯一...], "holdings_file", "direct_stocks",
          "penetration_stocks", "built_at"}；穿透失败时回退直接持仓并记录原因。
    """
    from src.python.core.code_utils import is_a_share_stock
    from src.python.core.reader import read_holdings
    from src.python.report.market_value import DetailRow
    from src.python.report.penetration import compute_penetration_top10

    holdings = read_holdings(holdings_path)
    # 名称 + 代码双维判定（排除 00 前缀重叠区场外基金，如 002943）
    direct = sorted({h.code for h in holdings if is_a_share_stock(h.name, h.code)})
    details = [
        DetailRow(
            name=h.name,
            code=h.code,
            market_value=h.shares * h.cost_price,
            cost=h.shares * h.cost_price,
            profit=0.0,
            account=h.account,
        )
        for h in holdings
    ]
    penetration: list[str] = []
    note = ""
    try:
        result = compute_penetration_top10(holdings, details)
        penetration = _extract_share_codes(result.get("top10") or [])
    except Exception as exc:  # 穿透失败回退直接持仓（池缩小会在判定书如实记录）
        note = f"穿透失败回退直接持仓: {type(exc).__name__}: {exc}"
    codes = sorted(set(direct) | set(penetration))
    return {
        "codes": codes,
        "holdings_file": str(holdings_path),
        "direct_stocks": direct,
        "penetration_stocks": sorted(set(penetration)),
        "penetration_note": note,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _extract_share_codes(nodes: Any) -> list[str]:
    """从穿透 top10 结构中递归收集 A 股代码（code 标量 / codes 列表两种形状）。"""
    from src.python.core.code_utils import is_a_share_code

    found: set[str] = set()
    if isinstance(nodes, dict):
        code = nodes.get("code")
        if isinstance(code, str) and is_a_share_code(code):
            found.add(code)
        codes = nodes.get("codes")
        if isinstance(codes, (list, tuple)):
            for item in codes:
                if isinstance(item, str) and is_a_share_code(item):
                    found.add(item)
        for value in nodes.values():
            found.update(_extract_share_codes(value))
    elif isinstance(nodes, (list, tuple)):
        for item in nodes:
            found.update(_extract_share_codes(item))
    return sorted(found)


def probe_bars(code: str) -> list[dict]:
    """日 K 线（history_stock 链，增量合并缓存）。"""
    from src.python.fetcher.chain_incremental import fetch_with_incremental_fallback

    try:
        return fetch_with_incremental_fallback("history_stock", code, LOOKBACK_DAYS) or []
    except Exception as exc:
        print(f"    [!] {code} 日K失败: {type(exc).__name__}: {exc}")
        return []


def probe_index() -> list[dict]:
    """基准指数历史（history_index 链）。"""
    from src.python.fetcher.index import fetch_index_history

    try:
        return fetch_index_history(BENCHMARK_INDEX, LOOKBACK_DAYS) or []
    except Exception as exc:
        print(f"    [!] 指数历史失败: {type(exc).__name__}: {exc}")
        return []


def probe_valuation(code: str) -> dict | None:
    """当前 PE/PB/市值（push2 扩展字段，经行业数据入口）。"""
    from src.python.fetcher.industry import fetch_valuation_fields

    try:
        return fetch_valuation_fields(code)
    except Exception as exc:
        print(f"    [!] {code} 估值失败: {type(exc).__name__}: {exc}")
        return None


def probe_fin_indicator(code: str) -> dict | None:
    """最新报告期财务指标（financial_indicator 链）。"""
    from src.python.fetcher.financial_indicator import fetch_latest_indicator

    try:
        return fetch_latest_indicator(code)
    except Exception as exc:
        print(f"    [!] {code} 财务指标失败: {type(exc).__name__}: {exc}")
        return None


def _value_present(value: Any) -> bool:
    return value is not None and not (isinstance(value, float) and value != value)


def probe_fields(
    catalog: list[dict[str, Any]], pool: dict[str, Any], probes: dict[str, Callable[..., Any]] | None = None
) -> dict[str, Any]:
    """逐字段类型探测池内可得性（每类型记录耗时；因子可得性在 metric_a 判定）。

    probes: 可注入替身（测试用）；默认走真实链路。
    返回 {"field_results": {type: {"per_code": {...}, "index_ok": bool},
          "timings": {type: seconds}, "pool_size": N, "cache_warm_bars": K}}
    """
    probes = probes or {
        FIELD_BARS: probe_bars,
        FIELD_INDEX: lambda *_: probe_index(),
        FIELD_VAL: probe_valuation,
        FIELD_FIN: probe_fin_indicator,
    }
    codes: list[str] = list(pool.get("codes") or [])
    field_results: dict[str, Any] = {"per_code": {}, "index_ok": False}
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    bars_by_code: dict[str, list[dict]] = {}
    for code in codes:
        bars = probes[FIELD_BARS](code)
        bars_by_code[code] = bars
    timings[FIELD_BARS] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    index_bars = probes[FIELD_INDEX]()
    timings[FIELD_INDEX] = round(time.perf_counter() - t0, 3)
    field_results["index_ok"] = bool(index_bars)

    for ftype in (FIELD_VAL, FIELD_FIN):
        t0 = time.perf_counter()
        per_code: dict[str, Any] = {}
        for code in codes:
            per_code[code] = probes[ftype](code)
        timings[ftype] = round(time.perf_counter() - t0, 3)
        field_results["per_code"][ftype] = per_code

    field_results["bars_by_code"] = bars_by_code
    field_results["index_bars"] = index_bars
    return {
        "field_results": field_results,
        "timings": timings,
        "pool_size": len(codes),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ═══════════════════════════════════════════════════════════════
#  指标 A：字段可得率（纯计算，测试可注入）
# ═══════════════════════════════════════════════════════════════


def _required_value_key(catalog_item: dict[str, Any], ftype: str) -> str:
    """字段类型在具体因子上要求的值键（覆盖率与信号提取同源）。"""
    if ftype == FIELD_VAL:
        return "market_cap" if catalog_item["slug"] == "fund_size_log_cap" else "pb"
    if ftype == FIELD_FIN:
        return {"fund_roe": "roe", "fund_revenue_yoy": "revenue_yoy", "fund_gross_margin": "gross_margin"}.get(
            catalog_item["slug"], "roe"
        )
    return ""


def _field_coverage(catalog_item: dict[str, Any], field_results: dict[str, Any]) -> dict[str, Any]:
    """单因子的逐字段覆盖率：bars 按 min_bars 条数、其余按值有效性。"""
    codes = list(field_results.get("codes") or [])
    total = len(codes)
    detail: dict[str, Any] = {}
    for ftype in catalog_item.get("fields", []):
        if ftype == FIELD_BARS:
            bars_by_code = field_results.get("bars_by_code") or {}
            min_bars = int(catalog_item.get("min_bars") or 0)
            ok_codes = [c for c in codes if len(bars_by_code.get(c) or []) >= min_bars]
        elif ftype == FIELD_INDEX:
            ok_codes = codes if field_results.get("index_ok") else []
        else:
            per_code = (field_results.get("per_code") or {}).get(ftype) or {}
            key = _required_value_key(catalog_item, ftype)
            ok_codes = []
            for c in codes:
                value = per_code.get(c)
                if isinstance(value, dict):
                    ok_codes += [c] if _value_present(value.get(key)) else []
                else:
                    ok_codes += [c] if _value_present(value) else []
        coverage = (len(ok_codes) / total) if total else 0.0
        detail[ftype] = {
            "ok": coverage >= TYPE_COVERAGE,
            "coverage": round(coverage, 4),
            "ok_codes": len(ok_codes),
            "total": total,
        }
    return detail


def metric_a(catalog: list[dict[str, Any]], field_results: dict[str, Any]) -> dict[str, Any]:
    """指标 A：可完整计算因子数 ÷ 25 ≥ 80%（每字段类型覆盖 ≥80% 池）。"""
    per_factor: dict[str, Any] = {}
    computable: list[str] = []
    for item in catalog:
        detail = _field_coverage(item, field_results)
        missing = [ftype for ftype, info in detail.items() if not info["ok"]]
        ok = not missing
        per_factor[item["slug"]] = {"ok": ok, "fields": detail, "missing": missing}
        if ok:
            computable.append(item["slug"])
    n = len(catalog) or 1
    ratio = len(computable) / n
    return {
        "metric": "A",
        "name": "字段可得率",
        "total": len(catalog),
        "computable": computable,
        "n_computable": len(computable),
        "ratio": round(ratio, 4),
        "threshold": THRESH_A,
        "pass": ratio >= THRESH_A,
        "per_factor": per_factor,
        "rule": f"每字段类型池内覆盖 ≥{TYPE_COVERAGE:.0%}；恰等算过；A 不过 → 提前终态不进 B/C",
    }


# ═══════════════════════════════════════════════════════════════
#  因子值计算（纯函数：bars + 指数 → 逐日值，None = 数据不足）
# ═══════════════════════════════════════════════════════════════


def _closes(bars: list[dict]) -> list[float]:
    out = []
    for bar in bars:
        try:
            out.append(float(bar["close"]))
        except (KeyError, TypeError, ValueError):
            out.append(float("nan"))
    return out


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v == v]
    return sum(vals) / len(vals) if vals else None


def _std(values: list[float]) -> float | None:
    vals = [v for v in values if v == v]
    n = len(vals)
    if n < 2:
        return None
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return var**0.5


def _pearson(values_x: list[float], values_y: list[float]) -> float | None:
    """共享 Pearson（复用 correlation 原语，退化返回 0.0）。"""
    pairs = [(x, y) for x, y in zip(values_x, values_y) if x == x and y == y]
    if len(pairs) < 3:
        return None
    r, _p = _pearson_pvalue([p[0] for p in pairs], [p[1] for p in pairs])
    return r


def _ema(values: list[float], span: int) -> list[float | None]:
    alpha = 2.0 / (span + 1)
    out: list[float | None] = []
    prev: float | None = None
    for i, value in enumerate(values):
        if i == 0:
            prev = value
        elif prev is None:
            prev = value
        else:
            prev = alpha * value + (1 - alpha) * prev
        out.append(prev if i >= span - 1 else None)
    return out


def _rolling_beta(rets: list[float], mkt: list[float], window: int) -> list[float | None]:
    """滚动 Beta（协方差法，与 metrics_risk.portfolio_beta 同口径）。"""
    out: list[float | None] = [None] * len(rets)
    for i in range(window, len(rets) + 1):
        pr = rets[i - window : i]
        br = mkt[i - window : i]
        mp, mb = sum(pr) / window, sum(br) / window
        cov = sum((a - mp) * (b - mb) for a, b in zip(pr, br)) / (window - 1)
        var = sum((b - mb) ** 2 for b in br) / (window - 1)
        out[i - 1] = cov / var if var > 0 else None
    return out


def _daily_returns(closes: list[float]) -> list[float]:
    rets = [float("nan")]
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        rets.append((closes[i] / prev - 1) if prev == prev and prev else float("nan"))
    return rets


def _aligned_index_returns(bars: list[dict], index_bars: list[dict]) -> list[float]:
    """按 bars 日期对齐的指数日收益（缺日为 NaN，相关性成对剔除）。"""
    closes = _closes(index_bars)
    dates = [b.get("date") for b in index_bars]
    date_pos = {d: i for i, d in enumerate(dates)}
    out: list[float] = []
    for bar in bars:
        pos = date_pos.get(bar.get("date"))
        value = float("nan")
        if pos is not None and pos > 0 and closes[pos - 1]:
            value = closes[pos] / closes[pos - 1] - 1
        out.append(value)
    return out


def compute_factor_values(
    slug: str, bars: list[dict], index_bars: list[dict], scalar: float | None = None
) -> list[float | None]:
    """单因子逐日值（对齐 bars 日期；步进型基本面传入 scalar 铺满）。"""
    closes = _closes(bars)
    n = len(bars)
    if n == 0:
        return []
    if scalar is not None:
        return [scalar if _value_present(scalar) else None] * n
    rets = _daily_returns(closes)
    idx_rets = _aligned_index_returns(bars, index_bars)
    item = next((c for c in CATALOG if c["slug"] == slug), None)
    window = int(item["window"]) if item else 20
    out: list[float | None] = [None] * n

    if slug == "qlib_ma_cross":
        for i in range(window, n):
            ma = _mean(closes[i - window : i])
            out[i] = (closes[i] - ma) / ma if ma else None
    elif slug == "qlib_macd_hist":
        ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
        diff = [a - b if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
        signal = _ema([d if d is not None else 0.0 for d in diff], 9)
        for i in range(n):
            if diff[i] is not None and signal[i] is not None:
                out[i] = diff[i] - signal[i]
    elif slug == "qlib_rsi_14":
        for i in range(window, n):
            seg = rets[i - window : i + 1][1:]
            gains = sum(r for r in seg if r == r and r > 0)
            losses = -sum(r for r in seg if r == r and r < 0)
            if gains + losses == 0:
                out[i] = 50.0
            else:
                out[i] = 100.0 * gains / (gains + losses)
    elif slug == "qlib_beta_60":
        for i, beta in enumerate(
            _rolling_beta(
                [r if r == r else 0.0 for r in rets],
                [r if r == r else 0.0 for r in idx_rets],
                window,
            )
        ):
            out[i] = beta
    elif slug == "qlib_aroon_25":
        for i in range(window, n):
            seg_h = [float(bars[j]["high"]) for j in range(i - window + 1, i + 1)]
            seg_l = [float(bars[j]["low"]) for j in range(i - window + 1, i + 1)]
            high_at = max(range(len(seg_h)), key=lambda k: seg_h[k])
            low_at = max(range(len(seg_l)), key=lambda k: -seg_l[k])
            up = 100.0 * (window - 1 - high_at) / (window - 1)
            down = 100.0 * (window - 1 - low_at) / (window - 1)
            out[i] = (up - down) / 100.0
    elif slug in ("alpha_corr_cv_10", "alpha_corr_cv_20", "alpha_rev_open_10"):
        open_prices = [float(b["open"]) for b in bars]
        for i in range(window, n):
            seg_c = closes[i - window : i + 1]
            seg_o = open_prices[i - window : i + 1]
            seg_v = [float(b["volume"]) for b in bars[i - window : i + 1]]
            xs = seg_o if slug == "alpha_rev_open_10" else seg_c
            r = _pearson(xs, seg_v)
            out[i] = -r if r is not None else None
    elif slug == "alpha_pvt_10":
        for i in range(window, n):
            acc, vol_sum = 0.0, 0.0
            for j in range(i - window + 1, i + 1):
                vol = float(bars[j]["volume"])
                acc += (closes[j] - closes[j - 1]) * vol
                vol_sum += vol
            out[i] = acc / vol_sum if vol_sum else None
    elif slug == "alpha_vwma_dev_20":
        for i in range(window, n):
            seg_c = closes[i - window : i + 1]
            seg_v = [float(b["volume"]) for b in bars[i - window : i + 1]]
            vol_sum = sum(seg_v)
            vwma = sum(c * v for c, v in zip(seg_c, seg_v)) / vol_sum if vol_sum else None
            out[i] = (closes[i] - vwma) / vwma if vwma else None
    elif slug == "gtja_mom_20":
        for i in range(window, n):
            prev = closes[i - window]
            out[i] = closes[i] / prev - 1 if prev else None
    elif slug == "gtja_rsv_9":
        for i in range(window, n):
            seg_h = [float(bars[j]["high"]) for j in range(i - window + 1, i + 1)]
            seg_l = [float(bars[j]["low"]) for j in range(i - window + 1, i + 1)]
            hi, lo = max(seg_h), min(seg_l)
            out[i] = (closes[i] - lo) / (hi - lo) if hi > lo else None
    elif slug == "gtja_bias_60":
        for i in range(window, n):
            ma = _mean(closes[i - window : i])
            out[i] = (closes[i] - ma) / ma if ma else None
    elif slug == "gtja_atr_14":
        trs: list[float] = []
        for i in range(1, n):
            high, low = float(bars[i]["high"]), float(bars[i]["low"])
            prev_close = closes[i - 1]
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        for i in range(window, n):
            atr = _mean(trs[i - window : i])
            out[i] = atr / closes[i] if atr and closes[i] else None
    elif slug == "gtja_pv_divergence":
        for i in range(window, n):
            mom = closes[i] / closes[i - window] - 1 if closes[i - window] else None
            seg_v = [float(bars[j]["volume"]) for j in range(i - 9, i + 1)]
            slope = _pearson(list(range(len(seg_v))), seg_v)
            if mom is None or slope is None or mom == 0 or slope == 0:
                out[i] = None
            else:
                out[i] = -1.0 if (mom > 0) == (slope > 0) else 1.0
    elif slug == "acad_max_60":
        for i in range(window, n):
            intraday = []
            for j in range(i - window + 1, i + 1):
                op = float(bars[j]["open"])
                intraday.append(float(bars[j]["high"]) / op - 1 if op else float("nan"))
            out[i] = max(v for v in intraday if v == v) if any(v == v for v in intraday) else None
    elif slug == "acad_idio_vol_60":
        resid = [(r - m) if r == r and m == m else float("nan") for r, m in zip(rets, idx_rets)]
        for i in range(window, n):
            out[i] = _std(resid[i - window + 1 : i + 1])
    elif slug == "acad_amihud_proxy_60":
        for i in range(window, n):
            accs = []
            for j in range(i - window + 1, i + 1):
                r, vol = rets[j], float(bars[j]["volume"])
                if r == r and vol > 0:
                    accs.append(abs(r) / vol * 1e9)  # 量纲归一（口径差异入判定书）
            out[i] = _mean(accs)
    elif slug == "acad_low_vol_60":
        for i in range(window, n):
            out[i] = _std(rets[i - window + 1 : i + 1])
    elif slug == "acad_skew_60":
        for i in range(window, n):
            seg = [r for r in rets[i - window + 1 : i + 1] if r == r]
            m, sd = _mean(seg), _std(seg)
            if m is None or not sd or len(seg) < 3:
                continue
            skew = sum(((v - m) / sd) ** 3 for v in seg) * len(seg) / ((len(seg) - 1) * (len(seg) - 2))
            out[i] = skew
    return out


# ═══════════════════════════════════════════════════════════════
#  阶段 3：信号相关性（横截面日均值 vs 既有信号族日频序列）
# ═══════════════════════════════════════════════════════════════


def cross_sectional_series(
    factor_values_by_code: dict[str, list[tuple[str, float | None]]],
) -> dict[str, float]:
    """横截面日均值：{date: mean(当日有效因子值)}（成分数 < MIN_CODES_PER_DAY 的日期剔除）。"""
    buckets: dict[str, list[float]] = {}
    for _code, pairs in factor_values_by_code.items():
        for date, value in pairs:
            if value is None or value != value:
                continue
            buckets.setdefault(date, []).append(value)
    series: dict[str, float] = {}
    for date in sorted(buckets):
        values = buckets[date]
        if len(values) >= MIN_CODES_PER_DAY:
            series[date] = sum(values) / len(values)
    return series


def build_family_series(
    family: str, index_bars: list[dict], pool_mean_rets: dict[str, float] | None = None
) -> dict[str, float]:
    """既有信号族日频序列（复用 analysis 原语，快照域族抛 ValueError 表示降级）。"""
    if family == FAMILY_REBALANCE:
        raise ValueError(FAMILY_DEGRADED[FAMILY_REBALANCE])
    closes = _closes(index_bars)
    dates = [b.get("date") for b in index_bars]
    series: dict[str, float] = {}

    if family == FAMILY_MARKET_TEMPERATURE:
        from src.python.analysis.market_temperature import compute_temperature

        for i in range(TEMPERATURE_SLICE - 1, len(index_bars)):
            result = compute_temperature(index_bars[max(0, i - TEMPERATURE_SLICE + 1) : i + 1])
            if result.get("available") and _value_present(result.get("score")):
                series[dates[i]] = float(result["score"])
    elif family == FAMILY_VALUATION_PERCENTILE:
        from src.python.analysis.valuation_percentile import price_percentile

        for i in range(59, len(index_bars)):
            pct = price_percentile(closes[: i + 1])
            if pct is not None:
                series[dates[i]] = float(pct)
    elif family == FAMILY_TAIL_VAR:
        from src.python.analysis.tail_risk import compute_tail_risk

        for i in range(29, len(index_bars)):
            window_bars = [{"date": dates[j], "total_value": closes[j]} for j in range(max(0, i - 59), i + 1)]
            result = compute_tail_risk(window_bars)
            if result.get("available") and _value_present(result.get("var95")):
                series[dates[i]] = float(result["var95"])
    elif family == FAMILY_STYLE_BETA:
        from src.python.analysis.metrics_risk import portfolio_beta

        if not pool_mean_rets:
            raise ValueError("风格族需要池均值收益序列")
        idx_rets = _daily_returns(closes)
        for i in range(BETA_WINDOW, len(index_bars)):
            pr = [pool_mean_rets.get(d, 0.0) for d in dates[i - BETA_WINDOW : i]]
            br = [r if r == r else 0.0 for r in idx_rets[i - BETA_WINDOW : i]]
            beta = portfolio_beta(pr, br)
            if beta is not None:
                series[dates[i]] = float(beta)
    else:
        raise ValueError(f"未知信号族: {family}")
    return series


def _delta(series: dict[str, float]) -> dict[str, float]:
    """一阶差分（去趋势口径，预注册于判定书）。"""
    dates = sorted(series)
    return {dates[i]: series[dates[i]] - series[dates[i - 1]] for i in range(1, len(dates))}


def _is_step_signal(delta_values: list[float]) -> bool:
    """步进/常量型信号：Δ 非零占比 < STEP_NONZERO_FRACTION（季频基本面等）。"""
    if not delta_values:
        return True
    nonzero = sum(1 for v in delta_values if abs(v) > 1e-12)
    return nonzero / len(delta_values) < STEP_NONZERO_FRACTION


def evaluate_factor_correlation(
    factor_series: dict[str, float],
    family_series: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """单因子 vs 各信号族：Δ Pearson（共享原语），返回 max|ρ| 与逐族明细。"""
    factor_delta = _delta(factor_series)
    f_dates = sorted(factor_delta)
    f_vals = [factor_delta[d] for d in f_dates]
    step_signal = _is_step_signal(f_vals)
    per_family: dict[str, Any] = {}
    max_abs: float | None = None
    closest: str | None = None
    for family, series in family_series.items():
        if not series:
            per_family[family] = {"rho": None, "note": "信号族序列为空"}
            continue
        fam_delta = _delta(series)
        shared = [d for d in f_dates if d in fam_delta]
        if len(shared) < MIN_PAIRS:
            per_family[family] = {"rho": None, "note": f"对齐样本 {len(shared)} < {MIN_PAIRS}"}
            continue
        if step_signal:
            rho = 0.0
            note = "步进/常量型信号（季频值），日频 Δ 结构性不相关，按预注册口径 ρ=0"
        else:
            rho, _p = _pearson_pvalue(
                [factor_delta[d] for d in shared],
                [fam_delta[d] for d in shared],
            )
            note = ""
        per_family[family] = {"rho": round(rho, 4), "note": note}
        abs_rho = abs(rho)
        if max_abs is None or abs_rho > max_abs:
            max_abs, closest = abs_rho, family
    low_corr = max_abs is not None and max_abs < CORR_LOW
    return {
        "max_abs_rho": round(max_abs, 4) if max_abs is not None else None,
        "closest_family": closest,
        "low_corr": bool(low_corr),
        "step_signal": step_signal,
        "per_family": per_family,
        "note": "无可评估信号族时按不通过计（fail-closed）" if max_abs is None else "",
    }


def metric_b(catalog: list[dict[str, Any]], computable: list[str], corr_results: dict[str, Any]) -> dict[str, Any]:
    """指标 B：低相关（增量）因子 ÷ 可计算因子 ≥30%，分母 <10 判样本不足不通过。"""
    denom = len(computable)
    low = [slug for slug in computable if (corr_results.get(slug) or {}).get("low_corr")]
    ratio = (len(low) / denom) if denom else 0.0
    sample_ok = denom >= B_MIN_DENOM
    return {
        "metric": "B",
        "name": "信号增量（低相关占比）",
        "denom": denom,
        "n_low_corr": len(low),
        "low_corr_factors": low,
        "ratio": round(ratio, 4),
        "threshold": THRESH_B,
        "sample_ok": sample_ok,
        "pass": sample_ok and ratio >= THRESH_B,
        "per_factor": {slug: corr_results.get(slug) for slug in computable},
        "rule": (
            f"可计算因子中 max|ρ|<{CORR_LOW}（跨四个日频信号族，Δ Pearson，"
            f"共享原语）占比 ≥{THRESH_B:.0%}；分母 <{B_MIN_DENOM} 判样本不足；恰等算过"
        ),
        "catalog_labels": {c["slug"]: c["label"] for c in catalog},
    }


# ═══════════════════════════════════════════════════════════════
#  指标 C：耗时与基线
# ═══════════════════════════════════════════════════════════════


def read_report_baseline(perf_path: Path | None = None) -> dict[str, Any]:
    """真实报告耗时基线：perf_history 近 5 次 full 报告 total_seconds 中位数。"""
    path = perf_path or (_PROJECT_ROOT / "data" / "state" / "perf_history.jsonl")
    totals: list[float] = []
    compute_totals: list[float] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"available": False, "reason": f"基线文件不可读: {path}", "n": 0}
    for line in lines[-10:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("report_type") != "full":
            continue
        if _value_present(entry.get("total_seconds")):
            totals.append(float(entry["total_seconds"]))
        phases = entry.get("phases") or {}
        non_llm = sum(float(v) for k, v in phases.items() if k != "LLM+新闻" and _value_present(v))
        compute_totals.append(non_llm)
    if not totals:
        return {"available": False, "reason": "近 10 行无 full 报告记录", "n": 0}
    recent = totals[-5:]
    recent_compute = compute_totals[-5:]
    median = sorted(recent)[len(recent) // 2]
    return {
        "available": True,
        "n": len(recent),
        "samples": recent,
        "median_seconds": round(median, 3),
        "compute_only_median_seconds": round(sorted(recent_compute)[len(recent_compute) // 2], 3),
        "source": str(path),
        "rule": "基线 = 近 5 次 full 报告 total_seconds 中位数（含 LLM，真实整机实测）；"
        "非 LLM 计算阶段中位数作保守副口径一并记录",
    }


def metric_c(cold_seconds: float | None, warm_seconds: float, baseline: dict[str, Any]) -> dict[str, Any]:
    """指标 C：冷启动全量计算耗时 ÷ 基线报告耗时 ≤20%（恰等算过；冷/基线缺失判不通过）。"""
    if cold_seconds is None:
        return {
            "metric": "C",
            "name": "耗时预算",
            "pass": False,
            "threshold": THRESH_C,
            "warm_seconds": warm_seconds,
            "reason": "冷启动延迟不可实测（冷样本无有效冷请求或全部异常）",
            "rule": "冷启动不可测 → 不可判定 → 按不通过计（fail-closed，可复评）",
        }
    if not baseline.get("available") or not baseline.get("median_seconds"):
        return {
            "metric": "C",
            "name": "耗时预算",
            "pass": False,
            "threshold": THRESH_C,
            "cold_seconds": cold_seconds,
            "warm_seconds": warm_seconds,
            "reason": baseline.get("reason", "基线不可用"),
            "rule": "基线缺失 → 不可判定 → 按不通过计（fail-closed，可复评）",
        }
    baseline_s = float(baseline["median_seconds"])
    ratio = cold_seconds / baseline_s if baseline_s else float("inf")
    return {
        "metric": "C",
        "name": "耗时预算",
        "cold_seconds": round(cold_seconds, 3),
        "warm_seconds": round(warm_seconds, 3),
        "baseline_seconds": baseline_s,
        "ratio": round(ratio, 4),
        "threshold": THRESH_C,
        "pass": ratio <= THRESH_C,
        "baseline": baseline,
        "rule": "冷启动（冷样本均延迟 × 全量请求数 + 指数探测）÷ 基线中位数 ≤20%；恰等算过；"
        "冷/基线不可测按不通过计（可复评）",
    }


def judge(
    metric_a_res: dict[str, Any] | None, metric_b_res: dict[str, Any] | None, metric_c_res: dict[str, Any] | None
) -> dict[str, Any]:
    """终态判定：A/B/C 全过 → 立项；任一不过/缺失 → 归档未采纳（A 不过则 B/C 终态跳过）。"""
    results = {"A": metric_a_res, "B": metric_b_res, "C": metric_c_res}
    failed: list[str] = []
    for key in ("A", "B", "C"):
        res = results[key]
        if res is None:
            failed.append(f"{key}未评估")
        elif not res.get("pass"):
            failed.append(f"{key}未过")
    approved = not failed
    return {
        "verdict": "转正立项" if approved else "已评估未采纳",
        "approved": approved,
        "failed": failed,
        "metrics": {k: (v or {}).get("pass") for k, v in results.items()},
    }


# ═══════════════════════════════════════════════════════════════
#  阶段执行与产物落盘
# ═══════════════════════════════════════════════════════════════


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def stage_catalog(out_dir: Path) -> list[dict[str, Any]]:
    print("[..] 阶段1：因子目录冻结（五族 × 5）")
    catalog = build_catalog()
    problems = validate_catalog(catalog)
    if problems:
        for problem in problems:
            print(f"    [!] {problem}")
        raise SystemExit("[ERR] 因子目录校验未过")
    _write_json(
        out_dir / "factor_catalog.json",
        {
            "catalog": catalog,
            "families": FAMILIES,
            "family_labels": FAMILY_LABELS,
            "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "评测简化口径（族内可追溯出处）；不移植源族算子代码，转正实施需按源族口径复核",
        },
    )
    lines = ["# 因子目录（25，五族 × 5）", ""]
    for family in FAMILIES:
        lines.append(f"## {FAMILY_LABELS[family]}（{family}）")
        lines.append("")
        lines.append("| slug | 因子 | 所需字段 | 最少 bars | 口径 |")
        lines.append("|---|---|---|---:|---|")
        for item in catalog:
            if item["family"] == family:
                lines.append(
                    f"| `{item['slug']}` | {item['label']} | "
                    f"{'+'.join(item['fields'])} | {item['min_bars']} | {item['formula']} |"
                )
        lines.append("")
    (out_dir / "_catalog.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"    [OK] 25 因子冻结 → {out_dir / 'factor_catalog.json'}")
    return catalog


def stage_fields(out_dir: Path, refresh_pool: bool = False) -> dict[str, Any]:
    print("[..] 阶段2：股票池冻结 + 字段可得性探测（经既有链路）")
    catalog = _read_json(out_dir / "factor_catalog.json")
    if not catalog:
        raise SystemExit("[ERR] 未找到目录，请先运行 catalog 阶段")
    catalog = catalog["catalog"]

    pool_path = out_dir / "stock_pool.json"
    pool = _read_json(pool_path) if not refresh_pool else None
    if not pool:
        from src.python.config import resolve_holdings_path

        holdings_path = resolve_holdings_path()
        print(f"    [..] 持仓: {holdings_path}")
        pool = build_stock_pool(holdings_path)
        _write_json(pool_path, pool)
    print(
        f"    [OK] 股票池 {len(pool['codes'])} 只"
        f"（直接 {len(pool.get('direct_stocks') or [])} + 穿透 "
        f"{len(pool.get('penetration_stocks') or [])}）"
        + (f" [{pool.get('penetration_note')}]" if pool.get("penetration_note") else "")
    )

    started = time.perf_counter()
    probe_out = probe_fields(catalog, pool)
    total_seconds = round(time.perf_counter() - started, 3)
    field_results = probe_out["field_results"]
    field_results["codes"] = pool["codes"]

    report = metric_a(catalog, field_results)
    report["timings"] = probe_out["timings"]
    report["probe_total_seconds"] = total_seconds
    report["pool_size"] = probe_out["pool_size"]
    report["captured_at"] = probe_out["built_at"]
    _write_json(out_dir / "fields_report.json", report)

    # 探测原始数据（bars/指数）落盘供 signals 阶段复用（避免重复打源）
    _write_json(
        out_dir / "probe_cache.json",
        {
            "bars_by_code": field_results.get("bars_by_code"),
            "index_bars": field_results.get("index_bars"),
            "valuation": field_results.get("per_code", {}).get(FIELD_VAL),
            "fin_indicator": field_results.get("per_code", {}).get(FIELD_FIN),
        },
    )
    status = "[OK]" if report["pass"] else "[!]"
    print(
        f"    {status} 指标 A：{report['n_computable']}/{report['total']} = "
        f"{report['ratio']:.1%}（阈值 {THRESH_A:.0%}）→ {'过' if report['pass'] else '不过'}"
    )
    if not report["pass"]:
        for slug, info in report["per_factor"].items():
            if not info["ok"]:
                print(f"      [!] {slug} 缺: {'+'.join(info['missing'])}")
    return report


def stage_signals(out_dir: Path) -> dict[str, Any]:
    print("[..] 阶段3：可计算因子信号 vs 既有信号族相关性")
    fields_report = _read_json(out_dir / "fields_report.json")
    if not fields_report:
        raise SystemExit("[ERR] 未找到 fields_report.json，请先运行 fields 阶段")
    if not fields_report.get("pass"):
        print("    [!] 指标 A 未过 → 按设计提前终态，不进阶段 3/4")
        _write_json(
            out_dir / "signals_report.json",
            {
                "metric": "B",
                "skipped": True,
                "reason": "指标 A 未过，提前终态",
                "pass": False,
                "denom": 0,
                "ratio": 0.0,
                "threshold": THRESH_B,
            },
        )
        return {"skipped": True, "pass": False}

    probe = _read_json(out_dir / "probe_cache.json")
    if not probe:
        raise SystemExit("[ERR] 未找到 probe_cache.json，请先运行 fields 阶段")
    bars_by_code = probe.get("bars_by_code") or {}
    index_bars = probe.get("index_bars") or []
    valuation = probe.get("valuation") or {}
    fin_indicator = probe.get("fin_indicator") or {}
    started = time.perf_counter()

    computable = fields_report["computable"]
    catalog = _read_json(out_dir / "factor_catalog.json")["catalog"]
    label_by_slug = {c["slug"]: c for c in catalog}

    # ── 因子横截面日均值序列 ──
    factor_series: dict[str, dict[str, float]] = {}
    for slug in computable:
        item = label_by_slug[slug]
        values_by_code: dict[str, list[tuple[str, float | None]]] = {}
        for code, bars in bars_by_code.items():
            if not bars:
                continue
            scalar: float | None = None
            if FIELD_FIN in item["fields"]:
                record = fin_indicator.get(code) or {}
                scalar = (
                    record.get("roe")
                    if slug == "fund_roe"
                    else (record.get("revenue_yoy") if slug == "fund_revenue_yoy" else record.get("gross_margin"))
                )
                if isinstance(scalar, str):
                    try:
                        scalar = float(scalar)
                    except ValueError:
                        scalar = None
            elif FIELD_VAL in item["fields"]:
                record = valuation.get(code) or {}
                if slug == "fund_pb":
                    scalar = record.get("pb")
                elif slug == "fund_size_log_cap":
                    scalar = json_cap_log(record.get("market_cap"))
            values = compute_factor_values(slug, bars, index_bars, scalar=scalar)
            dates = [b.get("date") for b in bars]
            values_by_code[code] = list(zip(dates, values))
        series = cross_sectional_series(values_by_code)
        if series:
            factor_series[slug] = series

    # ── 池均值日收益（风格族输入）与信号族序列 ──
    pool_mean = _pool_mean_returns(bars_by_code, index_bars)
    family_series: dict[str, dict[str, float]] = {}
    degraded: dict[str, str] = {}
    for family in (
        FAMILY_MARKET_TEMPERATURE,
        FAMILY_VALUATION_PERCENTILE,
        FAMILY_TAIL_VAR,
        FAMILY_STYLE_BETA,
        FAMILY_REBALANCE,
    ):
        try:
            series = build_family_series(family, index_bars, pool_mean)
            if series:
                family_series[family] = series
            else:
                degraded[family] = "序列为空（数据不足）"
        except ValueError as exc:
            degraded[family] = str(exc)

    corr_results = {slug: evaluate_factor_correlation(series, family_series) for slug, series in factor_series.items()}
    # 无可评估序列的可计算因子：fail-closed 记不可评估
    for slug in computable:
        corr_results.setdefault(
            slug,
            {
                "max_abs_rho": None,
                "closest_family": None,
                "low_corr": False,
                "step_signal": False,
                "per_family": {},
                "note": "因子序列为空，不可评估（fail-closed 按不通过计）",
            },
        )

    report = metric_b(catalog, computable, corr_results)
    report["skipped"] = False
    report["family_series_sizes"] = {k: len(v) for k, v in family_series.items()}
    report["family_degraded"] = degraded
    report["factor_series_sizes"] = {k: len(v) for k, v in factor_series.items()}
    report["compute_seconds"] = round(time.perf_counter() - started, 3)
    report["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(out_dir / "signals_report.json", report)
    status = "[OK]" if report["pass"] else "[!]"
    print(
        f"    {status} 指标 B：{report['n_low_corr']}/{report['denom']} = "
        f"{report['ratio']:.1%}（阈值 {THRESH_B:.0%}）→ {'过' if report['pass'] else '不过'}"
    )
    for family, reason in degraded.items():
        print(f"    [!] 信号族 {FAMILY_NAMES.get(family, family)} 降级: {reason}")
    return report


def json_cap_log(cap: Any) -> float | None:
    """log10(market_cap)×100（对数市值），非法/非有限值返回 None。"""
    import math

    if not _value_present(cap):
        return None
    try:
        value = float(cap)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return round(math.log10(value) * 100, 2)


def _pool_mean_returns(bars_by_code: dict[str, list[dict]], index_bars: list[dict]) -> dict[str, float]:
    """池内等权日收益（风格族滚动 Beta 的组合腿）。"""
    per_code: dict[str, dict[str, float]] = {}
    for code, bars in bars_by_code.items():
        closes = _closes(bars)
        rets = _daily_returns(closes)
        per_code[code] = {bars[i].get("date"): rets[i] for i in range(len(bars)) if rets[i] == rets[i]}
    dates = sorted({d for series in per_code.values() for d in series})
    mean: dict[str, float] = {}
    for date in dates:
        values = [series[date] for series in per_code.values() if date in series]
        if len(values) >= MIN_CODES_PER_DAY:
            mean[date] = sum(values) / len(values)
    return mean


def measure_cold_sample() -> dict[str, Any]:
    """池外样本测冷请求延迟（bars/估值/财务 + 指数）→ 冷启动估算均值。

    样本码若已缓存则如实标记（暖值不计入冷均值；全部暖 → 均值不可得）。
    """
    cache_dir = _PROJECT_ROOT / "data" / "cache"
    samples: list[dict[str, Any]] = []
    cold_durations: list[float] = []

    def _cached(prefix: str, code: str) -> bool:
        return any(cache_dir.glob(f"{prefix}{code}*"))

    for code in COLD_SAMPLE_CODES:
        entry: dict[str, Any] = {"code": code}
        for ftype, prefix, fn in (
            (FIELD_BARS, "history_stock_", probe_bars),
            (FIELD_VAL, "price_stock_", probe_valuation),
            (FIELD_FIN, "fin_indicator_", probe_fin_indicator),
        ):
            cached = _cached(prefix, code)
            t0 = time.perf_counter()
            try:
                value = fn(code)
                ok = bool(value)
            except Exception as exc:  # 样本失败仅记录（冷均值按成功冷样本）
                value, ok = None, False
                entry[f"{ftype}_error"] = f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - t0
            entry[ftype] = {"cached": cached, "ok": ok, "seconds": round(elapsed, 3)}
            if ok and not cached:
                cold_durations.append(elapsed)
        samples.append(entry)

    t0 = time.perf_counter()
    try:
        index_ok = bool(probe_index())
    except Exception:
        index_ok = False
    index_seconds = time.perf_counter() - t0
    mean_cold = (sum(cold_durations) / len(cold_durations)) if cold_durations else None
    return {
        "samples": samples,
        "cold_request_count": len(cold_durations),
        "mean_cold_request_seconds": round(mean_cold, 4) if mean_cold else None,
        "index_probe_seconds": round(index_seconds, 3),
        "index_ok": index_ok,
    }


def stage_timing(out_dir: Path) -> dict[str, Any]:
    print("[..] 阶段4：耗时与基线（指标 C）")
    fields_report = _read_json(out_dir / "fields_report.json")
    signals_report = _read_json(out_dir / "signals_report.json")
    if not fields_report:
        raise SystemExit("[ERR] 未找到 fields_report.json，请先运行 fields 阶段")
    if signals_report is None:
        raise SystemExit("[ERR] 未找到 signals_report.json，请先运行 signals 阶段")

    warm = 0.0 if signals_report.get("skipped") else float(signals_report.get("compute_seconds") or 0.0)
    baseline = read_report_baseline()

    # 冷启动估算：池外冷样本均延迟 × 全量请求数（池码 × 三字段类型 + 指数一次）
    try:
        cold_info = measure_cold_sample()
    except Exception as exc:
        cold_info = {"samples": [], "error": f"{type(exc).__name__}: {exc}", "mean_cold_request_seconds": None}
    pool_size = int(fields_report.get("pool_size") or 0)
    requests = pool_size * 3 + 1
    mean_cold = cold_info.get("mean_cold_request_seconds")
    cold_estimate: float | None = None
    if mean_cold:
        cold_estimate = mean_cold * requests + float(cold_info.get("index_probe_seconds") or 0.0)

    report = metric_c(cold_estimate, warm, baseline)
    report["cold_basis"] = (
        f"池外冷样本均延迟 {mean_cold}s × {pool_size} 码 × 3 字段类型 + 指数探测"
        if mean_cold
        else "冷样本无有效冷请求（全部缓存命中或失败）"
    )
    report["cold_sample"] = cold_info
    report["estimated_requests"] = requests
    report["warm_probe_total_seconds"] = fields_report.get("probe_total_seconds")
    report["timings_by_field"] = fields_report.get("timings") or {}
    report["skipped_signals"] = bool(signals_report.get("skipped"))
    report["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(out_dir / "timing_report.json", report)
    status = "[OK]" if report.get("pass") else "[!]"
    if "ratio" in report:
        print(
            f"    {status} 指标 C：冷启动估算 {report.get('cold_seconds')}s ÷ "
            f"基线 {report.get('baseline_seconds')}s = {report.get('ratio'):.1%}"
            f"（阈值 {THRESH_C:.0%}）；温态在跑 {report.get('warm_seconds')}s"
        )
    else:
        print(f"    [!] 指标 C 不可判定: {report.get('reason')}")
    return report


def stage_verdict(out_dir: Path) -> dict[str, Any]:
    print("[..] 阶段5：判定汇总（阈值与口径预注册）")
    fields_report = _read_json(out_dir / "fields_report.json")
    signals_report = _read_json(out_dir / "signals_report.json")
    timing_report = _read_json(out_dir / "timing_report.json")
    if fields_report is None or signals_report is None or timing_report is None:
        raise SystemExit("[ERR] 指标报告不齐，请先运行 fields/signals/timing 阶段")
    verdict = judge(
        fields_report if not fields_report.get("skipped") else fields_report,
        signals_report if not signals_report.get("skipped") else signals_report,
        timing_report,
    )
    verdict["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(out_dir / "verdict.json", verdict)
    _write_verdict_md(out_dir, verdict, fields_report, signals_report, timing_report)
    status = "[OK]" if verdict["approved"] else "[!]"
    print(
        f"    {status} 判定：{verdict['verdict']}"
        f"（A={verdict['metrics']['A']} B={verdict['metrics']['B']} "
        f"C={verdict['metrics']['C']}；未过: {'、'.join(verdict['failed']) or '无'}）"
    )
    return verdict


def _write_verdict_md(
    out_dir: Path, verdict: dict[str, Any], a: dict[str, Any], b: dict[str, Any], c: dict[str, Any]
) -> None:
    """判定书（结论入库用；数值与分子分母逐项落盘可复算）。"""
    lines = [
        "# 因子动物园目录评测判定书",
        "",
        f"- 判定：**{verdict['verdict']}**（A={verdict['metrics']['A']} / "
        f"B={verdict['metrics']['B']} / C={verdict['metrics']['C']}）",
        f"- 判定时间：{verdict['captured_at']}",
        f"- 未过项：{'、'.join(verdict['failed']) or '无'}",
        "",
        "## 预注册口径（判定前固定，复算须逐字段一致）",
        "",
        f"- **A 字段可得率** = 可完整计算因子数 ÷ 25 ≥ {THRESH_A:.0%}；每字段类型需池内 "
        f"≥{TYPE_COVERAGE:.0%} 代码有效（bars 按因子 min_bars 条数）；恰等算过；A 不过提前终态。",
        f"- **B 信号增量** = 可计算因子中 max|ρ|<{CORR_LOW}（四个日频信号族，一阶差分 Pearson，"
        f"共享 correlation 原语）占比 ≥{THRESH_B:.0%}；分母 <{B_MIN_DENOM} 判样本不足不通过；"
        f"对齐样本 <{MIN_PAIRS} 或序列为空按不通过计（fail-closed）；步进/常量型季频信号"
        f"（Δ 非零占比 <{STEP_NONZERO_FRACTION:.0%}）按结构性不相关 ρ=0（增量体现在横截面排序）。",
        f"- **C 耗时预算** = 冷启动全量计算 ÷ 基线报告耗时 ≤{THRESH_C:.0%}；基线 = perf_history "
        "近 5 次 full 报告 total_seconds 中位数（真实整机实测，含 LLM）；非 LLM 计算阶段中位数作"
        "保守副口径一并记录；基线缺失按不通过计（可复评）。",
        "- 快照域信号族（再平衡超限）无日频序列，按设计降级不参与（B 的信号族数如实记录）。",
        "",
        "## 指标 A：字段可得率",
        "",
        f"- {a.get('n_computable', 0)}/{a.get('total', 0)} = {a.get('ratio', 0):.1%}"
        f"（阈值 {THRESH_A:.0%}）→ {'过' if a.get('pass') else '不过'}",
        f"- 股票池 {a.get('pool_size', '?')} 只；字段类型耗时(s)：{json.dumps(a.get('timings') or {}, ensure_ascii=False)}",
        "",
        "| slug | 可计算 | 缺失字段 | 逐字段覆盖 |",
        "|---|---|---|---|",
    ]
    for slug, info in (a.get("per_factor") or {}).items():
        coverage = " / ".join(f"{ftype}:{meta['coverage']:.0%}" for ftype, meta in info["fields"].items())
        lines.append(f"| `{slug}` | {'✅' if info['ok'] else '❌'} | {'+'.join(info['missing']) or '—'} | {coverage} |")
    lines += ["", "## 指标 B：信号增量", ""]
    if b.get("skipped"):
        lines.append("- 未评估（指标 A 未过 → 提前终态）")
    else:
        lines += [
            f"- {b.get('n_low_corr', 0)}/{b.get('denom', 0)} = {b.get('ratio', 0):.1%}"
            f"（阈值 {THRESH_B:.0%}）→ {'过' if b.get('pass') else '不过'}"
            f"（样本门槛 ≥{B_MIN_DENOM}: {'满足' if b.get('sample_ok') else '不满足'}）",
            f"- 信号族序列长度：{json.dumps(b.get('family_series_sizes') or {}, ensure_ascii=False)}",
            f"- 降级信号族：{json.dumps(b.get('family_degraded') or {}, ensure_ascii=False)}",
            "",
            "| slug | max\\|ρ\\| | 最近族 | 低相关 | 步进型 |",
            "|---|---:|---|:---:|:---:|",
        ]
        for slug, info in (b.get("per_factor") or {}).items():
            if not info:
                continue
            lines.append(
                f"| `{slug}` | {info.get('max_abs_rho')} | "
                f"{FAMILY_NAMES.get(info.get('closest_family') or '', '—')} | "
                f"{'✅' if info.get('low_corr') else '❌'} | "
                f"{'是' if info.get('step_signal') else '否'} |"
            )
    lines += [
        "",
        "## 指标 C：耗时预算",
        "",
        f"- 冷启动 {c.get('cold_seconds', '?')}s / 温态计算 {c.get('warm_seconds', '?')}s ÷ "
        f"基线 {c.get('baseline_seconds', '—')}s = {c.get('ratio', '—')}"
        f"（阈值 {THRESH_C:.0%}）→ {'过' if c.get('pass') else '不过'}",
        f"- 冷启动口径：{c.get('cold_basis', '—')}；估算请求数 {c.get('estimated_requests', '—')}"
        f"（字段在跑耗时 {c.get('warm_probe_total_seconds', '—')}s 为暖态，不作冷判据）",
        f"- 逐字段阶段耗时(s)：{json.dumps(c.get('timings_by_field') or {}, ensure_ascii=False)}",
        f"- 基线样本：{json.dumps((c.get('baseline') or {}).get('samples') or [], ensure_ascii=False)}"
        f"，非 LLM 计算阶段中位数 {((c.get('baseline') or {}).get('compute_only_median_seconds'))}s（副口径，仅记录）",
        "",
        "## 复算说明",
        "",
        "判定输入（目录/股票池/字段快照/信号报告/耗时报告）冻结于本目录；"
        "`factor_zoo_eval.py all` 重跑后 A/B 的分子分母与判定须逐字段一致；"
        "C 的秒数为实测快照（网络波动允许漂移），复算以判定结论一致为准。",
    ]
    (out_dir / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"    [OK] 判定书 → {out_dir / 'verdict.md'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="因子动物园目录评测（先评测后立项）")
    parser.add_argument("stage", choices=["catalog", "fields", "signals", "timing", "verdict", "all"])
    parser.add_argument(
        "--out-dir", default=str(OUT_DIR_DEFAULT), help="评测产物目录（默认 docs/tmp/factor-zoo，git 忽略）"
    )
    parser.add_argument("--refresh-pool", action="store_true", help="忽略冻结股票池重新构建（持仓变动后重评）")
    args = parser.parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stages = ["catalog", "fields", "signals", "timing", "verdict"] if args.stage == "all" else [args.stage]
    for stage in stages:
        if stage == "catalog":
            stage_catalog(out_dir)
        elif stage == "fields":
            stage_fields(out_dir, refresh_pool=args.refresh_pool)
        elif stage == "signals":
            stage_signals(out_dir)
        elif stage == "timing":
            stage_timing(out_dir)
        elif stage == "verdict":
            stage_verdict(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
