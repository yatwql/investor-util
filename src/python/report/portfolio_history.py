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

        # 路由：按代码类型确定数据源
        if is_a_share_code(code) or is_exchange_fund_code(code):
            bars = self._get_stock_history(code)
        elif is_hk_stock_code(code):
            logger.debug("[history] 港股通暂不支持历史走势: %s", code)
            return None
        elif self._is_bond_fund(name):
            bars = self._get_fund_history(code)
        elif len(code) == 6 and code.isdigit():
            bars = self._get_fund_history(code)
        else:
            logger.debug("[history] 不支持的类型: %s (%s)", code, name)
            return None

        if not bars:
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
        # 收集每只持仓的走势
        all_series: list[list[dict]] = []
        total_holdings = len(holdings)
        success_count = 0
        warnings: list[str] = []

        for code, name, shares in holdings:
            series = self.calculate_for_holding(code, name, shares)
            if series:
                all_series.append(series)
                success_count += 1

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
            }

        status = "ok"
        if success_count < total_holdings:
            warnings.append(f"部分持仓历史走势不可用（{success_count}/{total_holdings}）")
            status = "degraded"

        # 合并为统一时间线
        date_map: dict[str, float] = {}
        for series in all_series:
            for bar in series:
                d = bar["date"]
                date_map[d] = date_map.get(d, 0) + bar["value"]

        sorted_dates = sorted(date_map.keys())
        if not sorted_dates:
            return {"bars": [], "max_drawdown": 0, "max_drawdown_pct": 0,
                    "annualized_volatility": 0, "total_return": 0,
                    "total_return_pct": 0, "status": "unavailable", "warnings": warnings}

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
                current_dd_start = ""
            drawdown = peak - tv
            drawdown_pct = drawdown / peak * 100 if peak > 0 else 0

            if drawdown > max_drawdown_val:
                max_drawdown_val = drawdown
                max_drawdown_pct = drawdown_pct
                drawdown_end = date
                drawdown_start = current_dd_start or date

            bars.append({
                "date": date,
                "total_value": round(tv, 2),
                "drawdown": round(drawdown, 2),
                "drawdown_pct": round(drawdown_pct, 4),
            })

        # 计算年化波动率
        daily_returns = []
        for i in range(1, len(bars)):
            prev = bars[i - 1]["total_value"]
            curr = bars[i]["total_value"]
            if prev > 0:
                daily_returns.append((curr - prev) / prev)

        annualized_vol = self._compute_annualized_volatility(daily_returns)

        # 计算总收益率
        first_val = bars[0]["total_value"]
        last_val = bars[-1]["total_value"]
        total_return = last_val - first_val
        total_return_pct = (total_return / first_val * 100) if first_val > 0 else 0

        # 质量校验
        warnings.extend(_validate_bars(bars))

        return {
            "bars": bars,
            "max_drawdown": round(max_drawdown_val, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "drawdown_start": drawdown_start,
            "drawdown_end": drawdown_end,
            "annualized_volatility": round(annualized_vol, 4),
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "status": status,
            "warnings": warnings,
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
