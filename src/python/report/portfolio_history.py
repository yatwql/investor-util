"""F2 组合历史走势计算器 — PortfolioHistoryCalculator。

职责：
  1. 遍历持仓 → 按代码类型路由（A 股/ETF → history_stock，OTC 基金 → history_fund_otc）
  2. 调用 _fetch_with_incremental_fallback() 获取历史数据
  3. 合并为统一的时间序列（as-if 市值）
  4. 计算回撤、波动率、收益率
  5. 数据质量校验（_validate_bars）

C1 约束：代码类型判定使用 code_utils 组合逻辑。
C4 约束：会话内重复请求先查 session_cache。
C5 约束：HTTP 请求通过 make_http_client()（由 provider 层保证）。
C6 约束：走 _fetch_with_incremental_fallback，不绕过 chain 层。
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from src.python.code_utils import (
    is_a_share_code,
    is_exchange_fund_code,
    is_hk_stock_code,
)
from src.python.fetcher.chain import _fetch_with_incremental_fallback

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════════
#  主计算器
# ═══════════════════════════════════════════════════════════════


class PortfolioHistoryCalculator:
    """组合历史走势计算器（无状态，每次独立计算）。"""

    # 债券基金名称关键词（用于排除路由到 OTC 净值链路）
    # 注意：只放真正的债券品种关键词，不放基金公司名——公司名会误伤股票型基金
    _BOND_FUND_KEYWORDS = (
        "纯债", "短债", "中短债", "利率债", "信用债", "债券",
    )

    def __init__(self, session_cache: dict[str, Any] | None = None) -> None:
        self._session_cache = session_cache or {}

    def calculate_for_holding(self, holding_code: str, holding_name: str,
                              shares: float) -> list[dict] | None:
        """计算单只持仓的 as-if 历史市值序列。

        as-if 语义：假设当前持仓份额在过去 N 天不变，用历史价格 × 当前份额。

        Args:
            holding_code: 证券代码
            holding_name: 证券名称
            shares: 当前持有份额

        Returns:
            list[dict]: [{date, value, close}, ...] 按日期升序排列。
            每项 value = close × shares（as-if 市值）。
            不支持的类型或获取失败返回 None。
        """
        code = holding_code.strip()
        name = (holding_name or "").strip()
        _tag = f"  [{code} {name}]" if name else f"  [{code}]"

        # 路由：按代码类型确定数据源
        if is_a_share_code(code) or is_exchange_fund_code(code):
            bars = self._get_stock_history(code)
            # 降级：00 开头 A 股/OTC 基金重叠区，股票历史全空时尝试基金历史
            if not bars and code.startswith("00") and not is_exchange_fund_code(code):
                logger.info("[history]%s K 线链路全部失败（该代码可能为场外基金），降级尝试基金净值链路", _tag)
                bars = self._get_fund_history(code)
                if bars:
                    logger.info("[history]%s 降级成功——通过基金净值链路获取到历史数据", _tag)
                else:
                    logger.warning("[history]%s 降级也失败——基金净值链路亦无数据", _tag)
            elif not bars:
                logger.warning("[history]%s K 线链路无数据", _tag)
        elif is_hk_stock_code(code):
            logger.info("[history]%s 港股通暂不支持历史走势，跳过", _tag)
            return None
        elif self._is_bond_fund(name):
            logger.info("[history]%s 债券基金→基金净值链路", _tag)
            bars = self._get_fund_history(code)
        elif len(code) == 6 and code.isdigit():
            logger.info("[history]%s OTC 基金→基金净值链路", _tag)
            bars = self._get_fund_history(code)
        else:
            logger.info("[history]%s 不支持的类型，跳过", _tag)
            return None

        if not bars:
            logger.warning("[history]%s 基金净值链路也无数据", _tag)
            return None

        # 转换为 as-if 市值序列
        result = []
        for bar in bars:
            close = bar.get("close") or bar.get("nav", 0)
            if close <= 0:
                continue
            result.append({
                "date": bar["date"],
                "close": close,
                "value": round(close * shares, 2),
            })

        return result if result else None

    def get_combined_timeseries(
        self, holdings: list[tuple[str, str, float]], days: int = 30,
    ) -> dict[str, Any]:
        """计算组合全部持仓的综合走势。

        Args:
            holdings: [(code, name, shares), ...] 持仓列表
            days: 历史天数

        Returns:
            {
                "bars": [{date, total_value, daily_return, drawdown}, ...],
                "max_drawdown": float,
                "max_drawdown_pct": float,
                "annualized_volatility": float,
                "total_return": float,
                "total_return_pct": float,
                "status": "ok" | "degraded" | "unavailable",
                "warnings": [str, ...],
            }
        """
        # 收集每只持仓的走势（并行获取，显著提速）
        all_series: list[list[dict]] = []
        total_holdings = len(holdings)
        success_count = 0
        warnings: list[str] = []
        failed_holdings: list[str] = []
        successful_holdings: list[str] = []

        _max_workers = min(8, total_holdings) if total_holdings > 1 else 1
        with ThreadPoolExecutor(max_workers=_max_workers) as _pool:
            _futures = {
                _pool.submit(self.calculate_for_holding, code, name, shares):
                (code, name) for code, name, shares in holdings
            }
            for _fut in as_completed(_futures):
                _code, _name = _futures[_fut]
                try:
                    series = _fut.result()
                except Exception:
                    logger.warning("[history] %s 历史数据获取异常", _code, exc_info=True)
                    series = None
                if series:
                    all_series.append(series)
                    success_count += 1
                    successful_holdings.append(f"{_name}({_code})")
                else:
                    failed_holdings.append(f"{_name}({_code})")

        if not all_series:
            return {
                "bars": [],
                "max_drawdown": 0,
                "max_drawdown_pct": 0,
                "annualized_volatility": 0,
                "total_return": 0,
                "total_return_pct": 0,
                "status": "unavailable",
                "warnings": ["所有持仓均无法获取历史走势数据"],
                "failed_holdings": failed_holdings,
                "successful_holdings": [],
            }

        status = "ok"
        if success_count < total_holdings:
            warnings.append(f"部分持仓历史走势不可用（{success_count}/{total_holdings}）")
            status = "degraded"

        # 合并为统一时间线
        date_map: dict[str, float] = {}
        fund_count_on_date: dict[str, int] = {}
        for series in all_series:
            for bar in series:
                d = bar["date"]
                date_map[d] = date_map.get(d, 0) + bar["value"]
                fund_count_on_date[d] = fund_count_on_date.get(d, 0) + 1

        sorted_dates = sorted(date_map.keys())
        if not sorted_dates:
            return {"bars": [], "max_drawdown": 0, "max_drawdown_pct": 0,
                    "annualized_volatility": 0, "total_return": 0,
                    "total_return_pct": 0, "status": "unavailable", "warnings": warnings}

        # 找到可用的收益率起算日期：要求该日 ≥80% 的持仓有数据
        # 不同基金数据起止日期不同（如有的从2025-09、有的从2026-03），
        # 过早的起算点会因基金不全导致组合市值偏低、收益率虚高
        total_funds = len(all_series)
        min_coverage = max(1, int(total_funds * 0.8))
        valid_start_idx = 0
        for i, d in enumerate(sorted_dates):
            funds_with_data = fund_count_on_date.get(d, 0)
            if funds_with_data >= min_coverage:
                valid_start_idx = i
                break
        if valid_start_idx > 0:
            logger.info("[history] 收益率起算点调整: %s → %s（此前日期仅覆盖部分持仓）",
                        sorted_dates[0], sorted_dates[valid_start_idx])

        # 构建完整时间线 + 计算指标
        bars: list[dict] = []
        peak = 0.0
        max_drawdown_val = 0.0
        max_drawdown_pct = 0.0
        drawdown_start = ""
        drawdown_end = ""
        current_dd_start = ""

        for date in sorted_dates:
            tv = date_map[date]
            if tv > peak:
                peak = tv
                current_dd_start = date  # 新高日=潜在回撤起算日
            drawdown = peak - tv
            drawdown_pct = drawdown / peak * 100 if peak > 0 else 0

            if drawdown > max_drawdown_val:
                max_drawdown_val = drawdown
                max_drawdown_pct = drawdown_pct
                drawdown_end = date
                if current_dd_start:
                    drawdown_start = current_dd_start  # 峰值日
                else:
                    drawdown_start = date

            bars.append({
                "date": date,
                "total_value": round(tv, 2),
                "drawdown": round(-drawdown, 2),
                "drawdown_pct": round(-drawdown_pct, 4),
            })

        # 计算年化波动率
        daily_returns = []
        for i in range(1, len(bars)):
            prev = bars[i - 1]["total_value"]
            curr = bars[i]["total_value"]
            if prev > 0:
                daily_returns.append((curr - prev) / prev)

        annualized_vol = self._compute_annualized_volatility(daily_returns)

        # 计算总收益率（从 valid_start_idx 起算，避免早期数据覆盖不全导致虚高）
        first_val = bars[valid_start_idx]["total_value"]
        last_val = bars[-1]["total_value"]
        total_return = last_val - first_val
        total_return_pct = (total_return / first_val * 100) if first_val > 0 else 0

        # 诊断：输出起止值明细（用于排查收益率异常）
        _diagnose_return(bars, sorted_dates, valid_start_idx, fund_count_on_date,
                         total_return_pct, len(all_series))

        # 质量校验（只校验收益率起算点之后的数据，避免新基金加入导致的跳变误报）
        warnings.extend(_validate_bars(bars[valid_start_idx:]))

        return {
            "bars": bars,
            "max_drawdown": round(-max_drawdown_val, 2),
            "max_drawdown_pct": round(-max_drawdown_pct, 2),
            "drawdown_start": drawdown_start,
            "drawdown_end": drawdown_end,
            "annualized_volatility": round(annualized_vol, 4),
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "data_start": sorted_dates[valid_start_idx],
            "data_end": sorted_dates[-1],
            "status": status,
            "warnings": warnings,
            "failed_holdings": failed_holdings,
            "successful_holdings": successful_holdings,
        }

    # ── 内部路由 ──────────────────────────────────────────

    def _get_stock_history(self, code: str) -> list[dict]:
        """获取股票/ETF 历史 K 线数据。"""
        # C4 约束：会话内重复请求免 HTTP
        cache_key = f"history_stock_{code}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        bars = _fetch_with_incremental_fallback("history_stock", code)
        if bars:
            self._session_cache[cache_key] = bars
        return bars

    def _get_fund_history(self, code: str) -> list[dict]:
        """获取 OTC 基金历史净值数据。"""
        cache_key = f"history_fund_otc_{code}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        bars = _fetch_with_incremental_fallback("history_fund_otc", code)
        if bars:
            self._session_cache[cache_key] = bars
        return bars

    @classmethod
    def _is_bond_fund(cls, name: str) -> bool:
        """根据名称判断是否为债券基金。"""
        return any(kw in name for kw in cls._BOND_FUND_KEYWORDS)

    @staticmethod
    def _compute_annualized_volatility(daily_returns: list[float]) -> float:
        """计算年化波动率（基于日收益率序列）。

        年化波动率 = 日收益率标准差 × sqrt(252)
        不足 2 个数据点时返回 0。
        """
        if len(daily_returns) < 2:
            return 0.0
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_dev = math.sqrt(variance)
        return std_dev * math.sqrt(252)


# ═══════════════════════════════════════════════════════════════
#  数据质量校验
# ═══════════════════════════════════════════════════════════════


def _validate_bars(bars: list[dict]) -> list[str]:
    """检查走势数据质量，返回警告列表。

    检查项：
      - 收盘价为 0
      - 未来日期
      - 明显的异常跳变（单日涨跌 > 50%）

    Args:
        bars: 走势数据列表

    Returns:
        警告消息列表，无问题时为空列表
    """
    warnings: list[str] = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    for i, b in enumerate(bars):
        close = b.get("close") or b.get("total_value", 0)
        if close == 0:
            warnings.append(f"{b['date']}: 收盘价为 0（可能停牌或数据异常）")
        if b.get("date", "") > today_str:
            warnings.append(f"{b['date']}: 日期为未来")

        # 检查异常跳变
        if i > 0:
            prev = bars[i - 1].get("close") or bars[i - 1].get("total_value", 0)
            if prev > 0 and close > 0:
                change_pct = abs(close - prev) / prev
                if change_pct > 0.5:
                    warnings.append(f"{b['date']}: 单日变化 {change_pct*100:.1f}%（可能异常）")

    return warnings


def _diagnose_return(
    bars: list[dict],
    sorted_dates: list[str],
    valid_start_idx: int,
    fund_count_on_date: dict[str, int],
    total_return_pct: float,
    total_series: int,
) -> None:
    """诊断收益率异常：输出起止日市值、覆盖标的数、每日明细快照。"""
    if not bars:
        return

    first_bar = bars[valid_start_idx]
    last_bar = bars[-1]

    # 取起止日 + 中间等间隔抽 3 个样本
    step = max(1, (len(bars) - 1) // 4)
    sample_idxs = [valid_start_idx] + [valid_start_idx + step * i for i in range(1, 4)] + [len(bars) - 1]
    sample_idxs = sorted(set(i for i in sample_idxs if i < len(bars)))

    lines = [
        f"[history] ═══ 累计收益率诊断 ═══",
        f"[history]  起算日: {first_bar['date']}  total_value={first_bar['total_value']:.2f}  "
        f"覆盖 {fund_count_on_date.get(first_bar['date'], 0)}/{total_series} 只",
        f"[history]  终止日: {last_bar['date']}  total_value={last_bar['total_value']:.2f}  "
        f"覆盖 {fund_count_on_date.get(last_bar['date'], 0)}/{total_series} 只",
        f"[history]  收益率: {total_return_pct:.2f}%",
        f"[history]  期间: {first_bar['date']} → {last_bar['date']} 共 {len(bars) - valid_start_idx} 个交易日",
    ]

    # 每日明细快照
    lines.append(f"[history]  中轴抽样（{len(sample_idxs)} 点）:")
    for idx in sample_idxs:
        b = bars[idx]
        coverage = fund_count_on_date.get(b["date"], 0)
        lines.append(
            f"[history]    {b['date']}  tv={b['total_value']:.2f}  "
            f"dd={b['drawdown']:.2f}  dd%={b['drawdown_pct']:.2f}%  "
            f"覆盖={coverage}/{total_series}"
        )

    for line in lines:
        logger.info(line)