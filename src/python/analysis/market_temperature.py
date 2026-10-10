"""市场温度 — 纯计算层（估值分位 + 均线偏离 + 波动率三因子合成）。

职责：接收指数历史 K 线 bars → 提取收盘价序列 → 合成三因子温度分
      → 映射低估/合理/高估三档“温度计”。

- 无数据获取、无报告依赖，纯标准库（日志走 logging，不用 print）。
- **第一因子为估值分位**：PE/PB/ERP（股债性价比）
  各自“当前值在自身历史中的分位”等权平均；估值序列不可得时**回落点位分位**
  （复用 ``valuation_percentile.price_percentile`` 机制），降级不阻塞主链路。
- 均线偏离复用同模块；波动率分量**反向**（越波动越冷，见下方 `_vol_component`）。
- 三因子合成权重：第一因子 0.5 + 均线偏离 0.3 + 波动率 0.2，输出 0~100 温度分。
- **温度计只给刻度，不做仓位硬建议**（“建议几成仓”合规与误导风险高），
  渲染层必须展示 ``TEMPERATURE_DISCLAIMER``。
- 样本不足（< MIN_SAMPLES）或空序列 → available=False（§1.4.5 数据降级治理）。
- **波动率分量反向**（2026-10-10 方向修正）：A 股高波动多现于恐慌下跌（股灾/贸易战/急跌），
  故波动率越高分量越低（“越波动越冷”），与恐贪情绪轴一致；旧口径同向会把低估区温度
  硬推高（波动分量最高 +20 分），可能把“低估”推成“合理”。
"""

from __future__ import annotations

import logging
import math

from src.python.analysis.valuation_percentile import (
    extract_closes,
    price_percentile,
    tier_from_percentile,
)

logger = logging.getLogger("invest")

# ═══════════════════════════════════════════════════════════════
#  市场温度常量
# ═══════════════════════════════════════════════════════════════

# 默认指数代码（沪深300；编排层可覆盖）
DEFAULT_INDEX_CODE: str = "sh000300"
DEFAULT_INDEX_NAME: str = "沪深300"
# 默认回看窗口（交易日；2026-10-10 实测腾讯/东财源上限 ~2000 根 ≈ 8 年，
# 含 2018 底部以来一轮完整牛熊 + 2024 复甦段；两轮牛熊需源支持更长历史）
DEFAULT_LOOKBACK_DAYS: int = 2000
# 均线窗口（交易日）
MA_WINDOW: int = 20
# 波动率窗口（交易日）
VOL_WINDOW: int = 20
# 年化交易日数
TRADING_DAYS_PER_YEAR: int = 252

# 三因子合成权重
W_PERCENTILE: float = 0.5
W_MA_DEVIATION: float = 0.3
W_VOLATILITY: float = 0.2
# 均线偏离映射区间（±20% 线性映射到 0~100）
MA_DEVIATION_SPAN: float = 0.4
# 年化波动率映射上限（50% 对应 100）
VOLATILITY_SPAN: float = 0.5

# 免责声明（渲染层必须展示，合规）
TEMPERATURE_DISCLAIMER: str = (
    "市场温度为估值分位（不可得时回落价格分位）、均线偏离与波动率三因子合成的信号，仅供参考，不构成任何仓位建议"
)

# 三档刻度中文名（与估值分位一致，文档/UI 统一口径）
TIER_UNDERVALUED = "低估"
TIER_FAIR = "合理"
TIER_OVERVALUED = "高估"

# 估值序列（PE/PB/ERP 月频）最少样本（对齐估值分位模块的 MIN_SAMPLES 口径）
MIN_VAL_SAMPLES: int = 60


# ═══════════════════════════════════════════════════════════════
#  估值分位（PE/PB/ERP 等权；不可得回落点位分位）
# ═══════════════════════════════════════════════════════════════


def build_erp_series(
    pe_rows: list[dict],
    rf_rows: list[dict],
) -> list[float]:
    """按日期对齐构建股债性价比序列：ERP = 1/PE − Rf（asof join）。

    PE 为月频（2005 起 259 点）、Rf 为日频（数千点），不能按序号
    尾部 zip 配对（会把历史 PE 与近期 Rf 错位拼接）——每个 PE 日期
    取“当日可得的最近一个 ≤ 该日”的 Rf。

    Args:
        pe_rows: [{"date": "YYYY-MM-DD", "pe": float|None}, ...] 升序（指数 PE 历史）。
        rf_rows: [{"date": "YYYY-MM-DD", "rate": float|None}, ...] 升序（10Y 国债收益率，小数）。

    Returns:
        ERP 序列（升序，与可用 PE 点对应）；不可得返回 []。
    """
    if not pe_rows or not rf_rows:
        return []
    valid_rf: list[tuple[str, float]] = []
    for r in rf_rows:
        rate = r.get("rate")
        if isinstance(rate, (int, float)) and math.isfinite(float(rate)) and 0 < float(rate) < 1:
            date = str(r.get("date") or "")
            if date:
                valid_rf.append((date, float(rate)))
    if not valid_rf:
        return []

    out: list[float] = []
    j = 0
    last_rate: float | None = None
    for row in pe_rows:
        date = str(row.get("date") or "")
        while j < len(valid_rf) and valid_rf[j][0] <= date:
            last_rate = valid_rf[j][1]
            j += 1
        pe = row.get("pe")
        if pe is None or last_rate is None:
            continue
        try:
            pe_f = float(pe)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(pe_f) or pe_f <= 0:
            continue
        out.append(1.0 / pe_f - last_rate)
    return out


def valuation_percentile(
    pe_series: list[float] | None,
    pb_series: list[float] | None,
    erp_values: list[float] | None,
) -> dict | None:
    """估值分位：PE/PB/ERP 各自“当前值（末值）在自身历史中的分位”等权平均。

    对标主流估值派（有知有行/且慢）：多估值指标等权 + 历史分位，而非点位分位。
    单项序列样本不足（< MIN_VAL_SAMPLES）或非正 → 该项缺席；全部缺席 → None
    （消费方回落点位分位，降级不阻塞）。

    Returns:
        {"percentile": float, "components": {"pe": ..., "pb": ..., "erp": ...}}；
        components 中缺席项为 None（仅保留可用项的分位）。
    """
    comps: dict[str, float | None] = {}
    for name, series in (("pe", pe_series), ("pb", pb_series), ("erp", erp_values)):
        if not series:
            comps[name] = None
            continue
        vals = [float(v) for v in series if isinstance(v, (int, float)) and math.isfinite(float(v))]
        if name in ("pe", "pb"):
            vals = [v for v in vals if v > 0]  # 非正 PE/PB（亏损期/异常）不参与
        if len(vals) < MIN_VAL_SAMPLES:
            comps[name] = None
            continue
        comps[name] = price_percentile(vals)

    available = [p for p in comps.values() if p is not None]
    if not available:
        return None
    percentile = round(sum(available) / len(available), 2)
    return {"percentile": percentile, "components": comps}


# ═══════════════════════════════════════════════════════════════
#  单因子计算
# ═══════════════════════════════════════════════════════════════


def moving_average(closes: list[float], window: int = MA_WINDOW) -> float | None:
    """最近 window 期简单移动平均。样本不足返回 None。"""
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def ma_deviation(closes: list[float], current: float | None = None, window: int = MA_WINDOW) -> float | None:
    """均线偏离：(当前价 - MA) / MA。样本不足或 MA 为 0 返回 None。"""
    ma = moving_average(closes, window)
    if ma is None or abs(ma) <= 1e-12:
        return None
    cur = closes[-1] if current is None else current
    if not math.isfinite(float(cur)):
        return None
    return (float(cur) - ma) / ma


def returns_volatility(closes: list[float], window: int = VOL_WINDOW) -> float | None:
    """年化波动率：最近 window 期日收益率的样本标准差 × √252。

    样本不足（<2 个收益率）或序列非有限值返回 None。
    """
    if len(closes) < 2:
        return None
    returns: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        cur = closes[i]
        if prev > 0 and math.isfinite(prev) and math.isfinite(cur):
            returns.append((cur - prev) / prev)
    if len(returns) < 2:
        return None
    tail = returns[-window:]
    mean = sum(tail) / len(tail)
    var = sum((r - mean) ** 2 for r in tail) / (len(tail) - 1)
    return math.sqrt(var * TRADING_DAYS_PER_YEAR)


# ═══════════════════════════════════════════════════════════════
#  三因子合成
# ═══════════════════════════════════════════════════════════════


def _ma_component(ma_dev: float) -> float:
    """均线偏离 → 0~100 分量（±20% 线性映射，越正越"热"）。"""
    return max(0.0, min(100.0, (ma_dev + MA_DEVIATION_SPAN / 2) / MA_DEVIATION_SPAN * 100.0))


def _vol_component(vol: float) -> float:
    """年化波动率 → 0~100 分量（0~50% 线性映射，**越高越"冷"**）。

    A 股高波动多现于恐慌下跌而非狂热顶部，故分量反向（vs 价格分位/均线偏离）：
    波动 0% → 100（平静=偏热），波动 ≥50% → 0（恐慌=偏冷）。负值（异常输入）按
    100 处理（clamp 上界）。
    """
    return max(0.0, min(100.0, (1.0 - vol / VOLATILITY_SPAN) * 100.0))


def temperature_score(pct: float, ma_dev: float, vol: float) -> float:
    """三因子合成温度分（0~100）。

    score = 0.5×分位 + 0.3×均线偏离分量 + 0.2×波动率分量（**反向**，越高越冷）。
    各分量经 clamp 映射，保证结果在 [0, 100]。
    """
    score = (
        W_PERCENTILE * float(pct)
        + W_MA_DEVIATION * _ma_component(float(ma_dev))
        + W_VOLATILITY * _vol_component(float(vol))
    )
    return round(max(0.0, min(100.0, score)), 2)


def compute_temperature(
    bars: list[dict],
    current: float | None = None,
    pe_series: list[float] | None = None,
    pb_series: list[float] | None = None,
    erp_values: list[float] | None = None,
) -> dict:
    """计算市场温度（数据子契约）。

    第一因子口径（估值分位升级）：PE/PB/ERP 等权分位可用时优先；
    估值序列不可得时回落点位分位（price_proxy），降级不阻塞。

    Args:
        bars: 指数历史 K 线 bars（date + close）。
        current: 当前点位；None 时取序列末值。
        pe_series: PE 历史序列（升序，含当前值；月频亦可）；None = 缺席。
        pb_series: PB 历史序列；None = 缺席。
        erp_values: 股债性价比序列（由 build_erp_series 按日期对齐构建）；None = 缺席。

    Returns:
        数据子契约 dict：
        {"available", "price_percentile", "valuation_percentile",
         "valuation_components", "first_factor", "ma_deviation", "volatility",
         "score", "tier", "sample_count", "components", "reason"}
        first_factor: "valuation"（估值分位）| "price_proxy"（点位分位回落）；
        available=False 时 reason 区分 "no_bars" / "insufficient_samples"。
    """
    closes = extract_closes(bars)
    if not closes:
        return _unavailable("no_bars", 0)

    pct = price_percentile(closes, current)
    if pct is None:
        return _unavailable("insufficient_samples", len(closes))

    cur = closes[-1] if current is None else float(current)
    dev = ma_deviation(closes, cur, MA_WINDOW)
    vol = returns_volatility(closes, VOL_WINDOW)
    if dev is None or vol is None:
        return _unavailable("insufficient_samples", len(closes))

    # 第一因子：估值分位优先，点位分位回落
    val = valuation_percentile(pe_series, pb_series, erp_values)
    if val is not None:
        first_factor, first_value = "valuation", val["percentile"]
        val_pct, val_comps = val["percentile"], val["components"]
    else:
        first_factor, first_value = "price_proxy", pct
        val_pct, val_comps = None, None

    score = temperature_score(first_value, dev, vol)
    return {
        "available": True,
        "price_percentile": pct,
        "valuation_percentile": val_pct,
        "valuation_components": val_comps,
        "first_factor": first_factor,
        "ma_deviation": round(dev, 6),
        "volatility": round(vol, 6),
        "score": score,
        "tier": tier_from_percentile(score),
        "sample_count": len(closes),
        "components": {
            "percentile_weight": W_PERCENTILE,
            "ma_deviation_weight": W_MA_DEVIATION,
            "volatility_weight": W_VOLATILITY,
        },
        "reason": None,
    }


def _unavailable(reason: str, sample_count: int) -> dict:
    """返回不可用温度结果（数据子契约）。"""
    return {
        "available": False,
        "price_percentile": None,
        "valuation_percentile": None,
        "valuation_components": None,
        "first_factor": None,
        "ma_deviation": None,
        "volatility": None,
        "score": None,
        "tier": None,
        "sample_count": sample_count,
        "components": None,
        "reason": reason,
    }


def unavailable_temperature(status: str) -> dict:
    """返回不可用结果（数据子契约，available=False）。

    Args:
        status: "insufficient"（数据不足）或 "source_failed"（数据源故障）。
    """
    return {
        "available": False,
        "status": status,
        "index_code": DEFAULT_INDEX_CODE,
        "index_name": DEFAULT_INDEX_NAME,
        "price_percentile": None,
        "valuation_percentile": None,
        "valuation_components": None,
        "first_factor": None,
        "ma_deviation": None,
        "volatility": None,
        "score": None,
        "tier": None,
        "sample_count": 0,
        "components": None,
        "reason": None,
        "disclaimer": TEMPERATURE_DISCLAIMER,
    }
