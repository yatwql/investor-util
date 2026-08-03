"""组合历史走势计算器 — PortfolioHistoryCalculator。

职责：
  1. 遍历持仓 → 按代码类型路由（A 股/ETF → history_stock，OTC 基金 → history_fund_otc）
  2. 调用 fetch_with_incremental_fallback() 获取历史数据
  3. 合并为统一的时间序列（as-if 市值）
  4. 计算回撤、波动率、收益率
  5. 数据质量校验（_validate_bars）— 见 _history_quality.py

C1 约束：代码类型判定使用 code_utils 组合逻辑。
C4 约束：会话内重复请求先查 session_cache。
C5 约束：HTTP 请求通过 make_http_client()（由 provider 层保证）。
C6 约束：走 fetch_with_incremental_fallback，不绕过 chain 层。
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from src.python.core.code_utils import (
    is_a_share_code,
    is_bond_fund_by_name,
    is_exchange_fund_code,
    is_hk_stock_code,
    is_otc_code_overlap,
    is_otc_fund_by_name,
    is_qdii_extended,
)
from src.python.analysis.drawdown_events import (
    MIN_SPAN,
    compute_recovery_times,
    extract_drawdown_events,
)
from src.python.fetcher.chain import fetch_with_incremental_fallback
from src.python.report._history_quality import _diagnose_return, _validate_bars
from src.python.report.benchmark import fetch_benchmarks, normalize_benchmarks

logger = logging.getLogger("invest")


# ═══════════════════════════════════════════════════════════════
#  主计算器
# ═══════════════════════════════════════════════════════════════


class PortfolioHistoryCalculator:
    """组合历史走势计算器（无状态，每次独立计算）。"""

    def __init__(
        self,
        session_cache: dict[str, Any] | None = None,
        coverage_threshold: float | None = None,
        benchmark_indices: dict[str, str] | None = None,
    ) -> None:
        """初始化组合历史走势计算器。

        Args:
            session_cache: 会话级请求缓存（C4 约束），同一次会话内相同请求免 HTTP。
            coverage_threshold: 有效区间覆盖比例阈值。
                起止日要求 ≥此比例×总持仓有数据，否则截断。
                默认 0.8（80%），取值范围 (0, 1]。
            benchmark_indices: 基准指数配置。
                {指数代码: 指数名称} 映射，如 {"sh000300": "沪深300", "gb_inx": "标普500"}。
                空 dict 表示禁用基准指数对比。None 等同于空 dict。
        """
        self._session_cache = session_cache or {}
        # 覆盖比例阈值：有效区间起止日要求 ≥此比例×总持仓 有数据
        self._coverage_threshold = coverage_threshold if coverage_threshold is not None else 0.8
        # 基准指数配置：{代码: 名称}，空 dict 表示禁用
        self._benchmark_indices = benchmark_indices if benchmark_indices is not None else {}

    def calculate_for_holding(
        self,
        holding_code: str,
        holding_name: str,
        shares: float,
        days: int = 30,
    ) -> list[dict] | None:
        """计算单只持仓的 as-if 历史市值序列。

        as-if 语义：假设当前持仓份额在过去 N 天不变，用历史价格 × 当前份额。

        Args:
            holding_code: 证券代码
            holding_name: 证券名称
            shares: 当前持有份额
            days: 历史天数（透传给 chain 层取数）

        Returns:
            list[dict]: [{date, value, close}, ...] 按日期升序排列。
            每项 value = close × shares（as-if 市值）。
            不支持的类型或获取失败返回 None。
        """
        code = holding_code.strip()
        name = (holding_name or "").strip()
        _tag = f"  [{code} {name}]" if name else f"  [{code}]"

        # 路由：按代码类型确定数据源（使用 code_utils 统一入口）
        if is_exchange_fund_code(code) or is_a_share_code(code):
            bars = self._get_stock_history(code, days)
            # 降级：A 股/OTC 基金代码重叠区（00 开头），股票历史全空时尝试基金历史
            if not bars and is_otc_code_overlap(code):
                logger.info("[history]%s K 线链路全部失败（该代码为场外基金），降级尝试基金净值链路", _tag)
                bars = self._get_fund_history(code, days)
                if bars:
                    logger.info("[history]%s 降级成功——通过基金净值链路获取到历史数据", _tag)
                else:
                    logger.warning("[history]%s 降级也失败——基金净值链路亦无数据", _tag)
            elif not bars:
                logger.warning("[history]%s K 线链路无数据", _tag)
        elif is_hk_stock_code(code):
            logger.info("[history]%s 港股通暂不支持历史走势，跳过", _tag)
            return None
        elif is_qdii_extended(name):
            logger.info("[history]%s QDII 基金→基金净值链路", _tag)
            bars = self._get_fund_history(code, days)
        elif is_bond_fund_by_name(name):
            logger.info("[history]%s 债券基金→基金净值链路", _tag)
            bars = self._get_fund_history(code, days)
        elif is_otc_fund_by_name(name, code):
            logger.info("[history]%s OTC 基金→基金净值链路", _tag)
            bars = self._get_fund_history(code, days)
        elif len(code) == 6 and code.isdigit():
            # 兜底：非 00 前缀的 6 位基金代码（如 011506、161725 等）
            logger.info("[history]%s 基金→基金净值链路", _tag)
            bars = self._get_fund_history(code, days)
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
            result.append(
                {
                    "date": bar["date"],
                    "close": close,
                    "value": round(close * shares, 2),
                }
            )

        return result if result else None

    def get_combined_timeseries(
        self,
        holdings: list[tuple[str, str, float]],
        days: int = 30,
    ) -> dict[str, Any]:
        """计算组合全部持仓的综合走势。

        Args:
            holdings: [(code, name, shares), ...] 持仓列表
            days: 历史天数，同时决定持仓历史长度（_fetch_all_histories 透传）
                  与基准指数历史长度（_fetch_benchmarks）。

        Returns:
            {
                "bars": [{date, total_value, daily_return, drawdown}, ...],
                "max_drawdown": float,
                "max_drawdown_pct": float,
                "drawdown_events": [{peak_date, trough_date, recovery_date,
                                     drawdown_pct, duration_days, recovery_days,
                                     recovered}, ...],  # 独立回撤事件
                "recovery_times": [{start_date, end_date, days}, ...],  # 恢复耗时明细
                "drawdown_available": bool,  # len(bars) >= MIN_SPAN，§1.4.5
                "annualized_volatility": float,
                "total_return": float,
                "total_return_pct": float,
                "daily_returns": [float, ...],  # 日收益率序列（百分比）
                "status": "ok" | "degraded" | "unavailable",
                "warnings": [str, ...],
                "benchmarks": [{code, name, bars, total_return_pct,
                                max_drawdown_pct, data_start, data_end, status}, ...],
            }
        """
        # 1) 收集每只持仓的走势（并行获取，显著提速）
        all_series, success_count, failed_holdings, successful_holdings = self._fetch_all_histories(holdings, days)
        warnings: list[str] = []

        if not all_series:
            return {
                "bars": [],
                "max_drawdown": 0,
                "max_drawdown_pct": 0,
                "annualized_volatility": 0,
                "total_return": 0,
                "total_return_pct": 0,
                "daily_returns": [],
                "daily_returns_portfolio": [],
                "status": "unavailable",
                "warnings": ["所有持仓均无法获取历史走势数据"],
                "failed_holdings": failed_holdings,
                "successful_holdings": [],
            }

        total_holdings = len(holdings)
        status = "ok"
        if success_count < total_holdings:
            warnings.append(f"部分持仓历史走势不可用（{success_count}/{total_holdings}）")
            status = "degraded"

        # 2) 合并为统一时间线（含 LOCF）
        sorted_dates, date_map, fund_count_on_date = self._merge_locf(all_series)

        if not sorted_dates:
            return {
                "bars": [],
                "max_drawdown": 0,
                "max_drawdown_pct": 0,
                "annualized_volatility": 0,
                "total_return": 0,
                "total_return_pct": 0,
                "daily_returns": [],
                "daily_returns_portfolio": [],
                "status": "unavailable",
                "warnings": warnings,
            }

        # 3) 有效区间截断：去除首尾覆盖不足的日期
        sorted_dates = self._trim_effective_range(sorted_dates, fund_count_on_date, len(all_series))

        # 4) 构建完整时间线 + 计算回撤
        bars, max_drawdown_val, max_drawdown_pct, drawdown_start, drawdown_end = self._compute_drawdown(
            sorted_dates, date_map
        )

        # 5) 计算日收益率序列 + 年化波动率
        daily_returns = self._compute_daily_returns(bars)
        annualized_vol = self._compute_annualized_volatility(daily_returns)

        # 6) 计算总收益率（从截断后的起算点开始）
        total_return, total_return_pct = self._compute_total_return(bars)

        # 7) 诊断 + 质量校验
        _diagnose_return(bars, sorted_dates, 0, fund_count_on_date, total_return_pct, len(all_series))
        warnings.extend(_validate_bars(bars))

        # 8) 基准指数历史走势
        benchmarks = self._fetch_benchmarks(bars, days)

        # 9) 独立回撤事件 + 恢复耗时（span < MIN_SPAN 标记数据不足，§1.4.5）
        drawdown_events = extract_drawdown_events(bars)
        recovery_times = compute_recovery_times(drawdown_events)
        drawdown_available = len(bars) >= MIN_SPAN

        return {
            "bars": bars,
            "max_drawdown": round(-max_drawdown_val, 2),
            "max_drawdown_pct": round(-max_drawdown_pct, 2),
            "drawdown_start": drawdown_start,
            "drawdown_end": drawdown_end,
            "drawdown_events": drawdown_events,
            "recovery_times": recovery_times,
            "drawdown_available": drawdown_available,
            "annualized_volatility": round(annualized_vol, 4),
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "daily_returns": daily_returns,
            "daily_returns_portfolio": daily_returns,
            "data_start": sorted_dates[0],
            "data_end": sorted_dates[-1],
            "status": status,
            "warnings": warnings,
            "failed_holdings": failed_holdings,
            "successful_holdings": successful_holdings,
            "benchmarks": benchmarks,
        }

    # ── 子函数 ──────────────────────────────────────────

    def _fetch_all_histories(
        self,
        holdings: list[tuple[str, str, float]],
        days: int = 30,
    ) -> tuple[list[list[dict]], int, list[str], list[str]]:
        """并行收集每只持仓的历史走势。

        Args:
            holdings: [(code, name, shares), ...] 持仓列表
            days: 历史天数（透传给 calculate_for_holding）

        Returns:
            (all_series, success_count, failed_holdings, successful_holdings)
        """
        all_series: list[list[dict]] = []
        total_holdings = len(holdings)
        success_count = 0
        failed_holdings: list[str] = []
        successful_holdings: list[str] = []

        _max_workers = min(8, total_holdings) if total_holdings > 1 else 1
        with ThreadPoolExecutor(max_workers=_max_workers) as _pool:
            _futures = {
                _pool.submit(self.calculate_for_holding, code, name, shares, days): (code, name)
                for code, name, shares in holdings
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

        return all_series, success_count, failed_holdings, successful_holdings

    @staticmethod
    def _merge_locf(
        all_series: list[list[dict]],
    ) -> tuple[list[str], dict[str, float], dict[str, int]]:
        """合并为统一时间线（含 LOCF）。

        LOCF（Last Observation Carried Forward）：净值未更新的标的沿用上次已知值，
        避免因 QDII 净值 T-1 滞后、场外基金净值晚更新等导致组合市值偏低。

        Returns:
            (sorted_dates, date_map, fund_count_on_date)
        """
        all_dates = sorted({d for series in all_series for b in series for d in [b["date"]]})
        date_map: dict[str, float] = {d: 0.0 for d in all_dates}
        fund_count_on_date: dict[str, int] = {d: 0 for d in all_dates}

        for series in all_series:
            last_val = 0.0
            series_by_date = {b["date"]: b["value"] for b in series}
            for d in all_dates:
                if d in series_by_date:
                    last_val = series_by_date[d]
                if last_val > 0:
                    date_map[d] += last_val
                    fund_count_on_date[d] += 1

        return all_dates, date_map, fund_count_on_date

    def _trim_effective_range(
        self,
        sorted_dates: list[str],
        fund_count_on_date: dict[str, int],
        total_funds: int,
    ) -> list[str]:
        """有效区间截断：去除首尾覆盖不足的日期。

        不同基金数据起止日期不同（如有的从2025-09、有的从2026-03），
        过早的起算点会因基金不全导致组合市值偏低、收益率虚高；
        过晚的终止点同样会因部分基金数据未刷新导致市值骤降。

        Args:
            sorted_dates: 排序后的完整日期列表
            fund_count_on_date: 每日期有数据的标的数
            total_funds: 总标的数

        Returns:
            截断后的日期列表
        """
        min_coverage = max(1, int(total_funds * self._coverage_threshold))
        valid_start_idx = 0
        for i, d in enumerate(sorted_dates):
            funds_with_data = fund_count_on_date.get(d, 0)
            if funds_with_data >= min_coverage:
                valid_start_idx = i
                break
        valid_end_idx = len(sorted_dates) - 1
        for i in range(len(sorted_dates) - 1, -1, -1):
            if fund_count_on_date.get(sorted_dates[i], 0) >= min_coverage:
                valid_end_idx = i
                break
        if valid_end_idx < valid_start_idx:
            valid_end_idx = valid_start_idx
        if valid_start_idx > 0 or valid_end_idx < len(sorted_dates) - 1:
            logger.info(
                "[history] 有效区间截取: %s ~ %s（首尾覆盖不足日期已排除）",
                sorted_dates[valid_start_idx],
                sorted_dates[valid_end_idx],
            )
        return sorted_dates[valid_start_idx : valid_end_idx + 1]

    @staticmethod
    def _compute_drawdown(
        sorted_dates: list[str],
        date_map: dict[str, float],
    ) -> tuple[list[dict], float, float, str, str]:
        """构建完整时间线，计算回撤指标。

        Returns:
            (bars, max_drawdown_val, max_drawdown_pct, drawdown_start, drawdown_end)
        """
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
                current_dd_start = date
            drawdown = peak - tv
            drawdown_pct = drawdown / peak * 100 if peak > 0 else 0

            if drawdown > max_drawdown_val:
                max_drawdown_val = drawdown
                max_drawdown_pct = drawdown_pct
                drawdown_end = date
                if current_dd_start:
                    drawdown_start = current_dd_start
                else:
                    drawdown_start = date

            bars.append(
                {
                    "date": date,
                    "total_value": round(tv, 2),
                    "drawdown": round(-drawdown, 2),
                    "drawdown_pct": round(-drawdown_pct, 4),
                }
            )

        return bars, max_drawdown_val, max_drawdown_pct, drawdown_start, drawdown_end

    @staticmethod
    def _compute_daily_returns(bars: list[dict]) -> list[float]:
        """计算日收益率序列。

        Args:
            bars: 走势数据列表（含 total_value）

        Returns:
            日收益率列表（小数形式，非百分比）
        """
        daily_returns: list[float] = []
        for i in range(1, len(bars)):
            prev = bars[i - 1]["total_value"]
            curr = bars[i]["total_value"]
            if prev > 0:
                daily_returns.append((curr - prev) / prev)
        return daily_returns

    @staticmethod
    def _compute_total_return(bars: list[dict]) -> tuple[float, float]:
        """计算总收益率。

        bars 基于截断后的日期列表构建，索引 0 即有效起算点。

        Returns:
            (total_return, total_return_pct) 绝对收益和百分比收益
        """
        first_val = bars[0]["total_value"]
        last_val = bars[-1]["total_value"]
        total_return = last_val - first_val
        total_return_pct = (total_return / first_val * 100) if first_val > 0 else 0
        return total_return, total_return_pct

    def _fetch_benchmarks(self, bars: list[dict], days: int) -> list[dict[str, Any]]:
        """获取基准指数历史走势并归一化对齐。

        Args:
            bars: 组合走势数据（用于归一化对齐）
            days: 历史天数

        Returns:
            基准指数走势列表，空列表表示无基准或获取失败
        """
        benchmarks: list[dict[str, Any]] = []
        if not self._benchmark_indices:
            return benchmarks

        logger.info("[history] 开始获取 %d 个基准指数历史走势", len(self._benchmark_indices))
        try:
            raw_benchmarks = fetch_benchmarks(self._benchmark_indices, days=days)
            if raw_benchmarks:
                ok_count = len(raw_benchmarks)
                logger.info("[history] 基准指数获取完成: %d/%d", ok_count, len(self._benchmark_indices))
                benchmarks = normalize_benchmarks(bars, raw_benchmarks)
                if benchmarks:
                    logger.info("[history] 基准指数归一化完成: %d 条", len(benchmarks))
                else:
                    logger.warning("[history] 基准指数归一化全部失败")
            else:
                logger.warning("[history] 基准指数全部获取失败")
        except Exception:
            logger.warning("[history] 基准指数获取异常", exc_info=True)

        return benchmarks

    # ── 内部路由 ──────────────────────────────────────────

    def _get_stock_history(self, code: str, days: int = 30) -> list[dict]:
        """获取股票/ETF 历史 K 线数据。"""
        # C4 约束：会话内重复请求免 HTTP
        cache_key = f"history_stock_{code}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        bars = fetch_with_incremental_fallback("history_stock", code, days)
        if bars:
            self._session_cache[cache_key] = bars
        return bars

    def _get_fund_history(self, code: str, days: int = 30) -> list[dict]:
        """获取 OTC 基金历史净值数据。"""
        cache_key = f"history_fund_otc_{code}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        bars = fetch_with_incremental_fallback("history_fund_otc", code, days)
        if bars:
            self._session_cache[cache_key] = bars
        return bars

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
