"""交易纪律规则引擎 — 止盈 / 止损 / 回撤触发检测。

独立于再平衡信号的纪律层：面向持仓收益率的止盈/止损纪律，以及面向
组合级回撤的组合纪律。输出「触发 + 距触发幅度 + 建议动作」结构化信号，
供「行动建议」纪律子块（与智囊团深度复盘「行动摘要」子块）消费。

设计要点：
  - 纯计算层：仅消费调用方传入的 holdings_details 与配置，不依赖 report/ 包
  - 参数化：止盈线/止损线/回撤线/静默期均来自 discipline 配置段（可全局覆盖）
  - 与再平衡信号同构：复用 _silence.py 静默期机制（同一「触发 + 距触发幅度」结构）
  - 静默期范围：仅对**单品信号**（止盈/止损，有 code）生效；组合级回撤信号
    （code 为空）不参与单品静默——与再平衡模块对组合级信号（category/summary）
    的约定一致：回撤是持续状态而非一次性事件，在峰值恢复前持续提示风险更合理
  - 数据守卫：缺 profit_rate / 总市值 0 / 空持仓 → 安全跳过，不报错

产出信号字段（C19 `discipline_signals` 契约）：
  code / name / rule / value / status_label / triggered / distance_pct / action
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.python.analysis import _silence
from src.python.config._core import get_config
from src.python.core.constants import PROJECT_ROOT

logger = logging.getLogger("invest")

# ── 默认纪律参数（与 _config_defaults.py discipline 段保持一致）────────────

_DEFAULT_TAKE_PROFIT_PCT = 20.0  # 止盈线：收益率 ≥ +20% 触发部分止盈建议
_DEFAULT_STOP_LOSS_PCT = -15.0  # 止损线：收益率 ≤ -15% 触发止损/减仓建议
_DEFAULT_DRAWDOWN_PCT = -10.0  # 回撤线：组合回撤 ≥ 10% 触发控回撤建议
_DEFAULT_SILENCE_DAYS = 30  # 静默期：同一品种触发后 N 天内不重复告警

# 静默期持久化路径（独立于再平衡静默文件，避免信号互相抑制；
# 测试经 monkeypatch.setattr 注入临时路径）
_SILENCE_FILE = os.path.join(PROJECT_ROOT, "data/state/discipline_silence.json")


# ── 配置解析 ────────────────────────────────────────────────────


def resolve_discipline_config(discipline_config: dict[str, Any] | None) -> dict[str, Any]:
    """解析交易纪律配置，填充默认值。

    Args:
        discipline_config: 原始 discipline 配置段（可为 None）

    Returns:
        解析后的配置字典（含 take_profit_pct/stop_loss_pct/drawdown_pct/silence_days）。
    """
    if discipline_config is None:
        config = get_config()
        discipline_config = config.get("discipline", {})
    result = dict(discipline_config)
    result.setdefault("take_profit_pct", _DEFAULT_TAKE_PROFIT_PCT)
    result.setdefault("stop_loss_pct", _DEFAULT_STOP_LOSS_PCT)
    result.setdefault("drawdown_pct", _DEFAULT_DRAWDOWN_PCT)
    result.setdefault("silence_days", _DEFAULT_SILENCE_DAYS)
    return result


# ── 信号构造 ────────────────────────────────────────────────────


def _format_threshold_pct(value: float) -> str:
    """阈值百分数格式化（整数阈值不带小数位，如 20 / -15 / 10）。"""
    return f"{value:.0f}" if value == int(value) else f"{value:.1f}"


def _build_signal(
    name: str,
    code: str,
    rule: str,
    value: float,
    distance_pct: float,
    action: str,
) -> dict[str, Any]:
    """构造一条纪律信号（触发 + 距触发幅度 + 建议动作）。

    Args:
        name: 品种名称（组合纪律为「组合」）
        code: 品种代码（组合纪律为空字符串）
        rule: 规则描述（如「止盈线 +20%」）
        value: 当前值（百分数，如 -16 表示 -16%）
        distance_pct: 距触发幅度（超线百分数，正数）
        action: 建议动作（部分止盈 / 止损减仓 / 减仓控回撤）

    Returns:
        纪律信号 dict（C19 `discipline_signals` 契约字段）。
    """
    sign = "+" if value >= 0 else ""
    if distance_pct > 0:
        status_label = f"触发（超线 {distance_pct:.1f}%，建议{action}）"
    else:
        status_label = f"触发（在线上，建议{action}）"
    return {
        "code": code,
        "name": name,
        "rule": rule,
        "value": f"{sign}{value:.1f}%",
        "status_label": status_label,
        "triggered": True,
        "distance_pct": distance_pct,
        "action": action,
    }


# ── 主入口 ──────────────────────────────────────────────────────


def compute_discipline_signals(
    holdings_details: list[dict[str, Any]] | None,
    total_mv: float,
    discipline_config: dict[str, Any] | None = None,
    portfolio_peak_mv: float | None = None,
    silence_file: str | None = None,
) -> list[dict[str, Any]]:
    """计算交易纪律信号（止盈 / 止损 / 回撤三类）。

    Args:
        holdings_details: 持仓明细列表（需含 name/code/profit_rate；缺 profit_rate
            的品种安全跳过）
        total_mv: 组合总市值（≤ 0 时视为无有效数据，返回空）
        discipline_config: discipline 配置段（None 时从全局配置读取）
        portfolio_peak_mv: 组合历史峰值市值（None 时跳过回撤纪律）
        silence_file: 静默期持久化路径（None 时使用模块默认 _SILENCE_FILE）

    Returns:
        纪律信号列表；无触发或数据不充分时返回空列表。
    """
    if not holdings_details or total_mv <= 0:
        return []

    resolved = resolve_discipline_config(discipline_config)
    signals: list[dict[str, Any]] = []

    take_profit_pct = resolved["take_profit_pct"]
    stop_loss_pct = resolved["stop_loss_pct"]

    # ① 止盈纪律：收益率 ≥ 止盈线
    for h in holdings_details:
        profit_rate = h.get("profit_rate")
        if profit_rate is None:
            continue
        if profit_rate >= take_profit_pct:
            signals.append(
                _build_signal(
                    name=h.get("name", ""),
                    code=h.get("code", ""),
                    rule=f"止盈线 +{_format_threshold_pct(take_profit_pct)}%",
                    value=profit_rate,
                    distance_pct=profit_rate - take_profit_pct,
                    action="部分止盈",
                )
            )

    # ② 止损纪律：收益率 ≤ 止损线
    for h in holdings_details:
        profit_rate = h.get("profit_rate")
        if profit_rate is None:
            continue
        if profit_rate <= stop_loss_pct:
            signals.append(
                _build_signal(
                    name=h.get("name", ""),
                    code=h.get("code", ""),
                    rule=f"止损线 {_format_threshold_pct(stop_loss_pct)}%",
                    value=profit_rate,
                    distance_pct=stop_loss_pct - profit_rate,
                    action="止损/减仓",
                )
            )

    # ③ 回撤纪律：组合当前市值相对历史峰值回撤 ≥ 回撤线。
    # 回撤线以「亏损幅度」表示（如 -10 表示回撤 10%），配置正值（10）与负值
    # 等价——统一按负值展示规则文本，避免出现「回撤线 10%」的歧义。
    drawdown_pct = resolved["drawdown_pct"]
    drawdown_threshold = -abs(drawdown_pct)
    if portfolio_peak_mv is not None and portfolio_peak_mv > 0:
        drawdown = (portfolio_peak_mv - total_mv) / portfolio_peak_mv * 100
        if drawdown >= abs(drawdown_pct):
            signals.append(
                _build_signal(
                    name="组合",
                    code="",
                    rule=f"回撤线 {_format_threshold_pct(drawdown_threshold)}%",
                    value=-drawdown,
                    distance_pct=drawdown - abs(drawdown_pct),
                    action="减仓控回撤",
                )
            )

    # ④ 静默期过滤 + 更新（与再平衡信号同构，复用 _silence.py 机制）。
    # 仅单品信号（有 code）参与静默：组合级回撤信号 code 为空，天然豁免，
    # 与再平衡对组合级信号（category/summary）的约定一致，见模块 docstring。
    silence_days = resolved.get("silence_days", _DEFAULT_SILENCE_DAYS)
    if silence_days > 0:
        path = silence_file or _SILENCE_FILE
        signals = _silence._filter_silenced_signals(signals, silence_days, path)
        _silence._update_silence_state(signals, path)

    return signals
