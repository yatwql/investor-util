"""组合历史走势 — 数据模型与差异摘要。

4 个 dataclass 构成完整的时间维度数据模型：

- SnapshotHolding：单条持仓在快照时刻的状态
- SnapshotData： 全量快照（所有持仓 + 计算指标 + LLM 摘要）
- DiffSummary：  新旧快照的差异摘要（组合级 + 持仓级）
- HistoryBar：   单日价格/净值数据点（F2 走势曲线基础单元）

遵循 C3 约束：快照文件使用 tempfile.mkstemp + os.replace 写入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ═══════════════════════════════════════════════════════════════
#  F1：快照模型（R0+R1 基础设施）
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SnapshotHolding:
    """单条持仓在快照时刻的状态。

    与 models.Holding 的区别：
      - 去除了 account 字段（快照按账户组织，在 SnapshotData.accounts 中体现）
      - 增加了 market_value / daily_pnl / total_pnl 等计算值
      - 用于 F1 快照对比和 F2 as-if 走势计算
    """

    code: str
    name: str
    shares: float
    cost_price: float
    market_value: float          # 当前市值
    daily_pnl: float = 0.0      # 当日盈亏
    total_pnl: float = 0.0      # 总盈亏（累计）
    cost_total: float = 0.0     # 总成本


@dataclass(frozen=True)
class AccountSnapshot:
    """单个账户在快照时刻的状态。"""

    account_name: str
    holdings: tuple[SnapshotHolding, ...] = ()


@dataclass(frozen=True)
class SnapshotData:
    """一次完整的快照数据。

    包含所有账户的持仓数据 + 组合级汇总 + 可选 LLM 摘要。
    Fingerprint 用于 R3 指纹去重——无实际变化时跳过差异段落生成。

    Attributes:
        accounts:     所有账户的快照列表
        total_value:  组合总市值
        total_cost:   组合总成本
        total_pnl:    组合总盈亏
        total_pnl_pct:组合总盈亏率
        timestamp:    快照时间（ISO 格式字符串，如 "2026-07-12T14:30:00"）
        fingerprint:  内容指纹（SHA256），用于去重
        llm_summary:  LLM 生成的快照评语（可选，由 R3 LLM 流程写入）
    """

    accounts: tuple[AccountSnapshot, ...]
    total_value: float = 0.0
    total_cost: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    timestamp: str = ""
    fingerprint: str = ""
    llm_summary: str = ""


# ═══════════════════════════════════════════════════════════════
#  F1：差异模型（R2 差异计算引擎）
# ═══════════════════════════════════════════════════════════════

# 持仓变动类型
_DiffAction = Literal["新增", "清仓", "加仓", "减仓", "不变"]


@dataclass(frozen=True)
class HoldingDiff:
    """单条持仓的差异。

    用于报告每个持仓的变化明细。

    Attributes:
        code:         证券代码
        name:         证券名称
        action:       变动类型（新增/清仓/加仓/减仓/不变）
        shares_diff:  份额变化量（正=加仓，负=减仓）
        value_diff:   市值变化量
        pnl_diff:     盈亏变化量
        pnl_rate_diff:盈亏率变化（百分点）
    """

    code: str
    name: str
    action: _DiffAction
    shares_diff: float = 0.0
    value_diff: float = 0.0
    pnl_diff: float = 0.0
    pnl_rate_diff: float = 0.0


@dataclass(frozen=True)
class DiffSummary:
    """新旧快照的差异摘要。

    包含：
      - 组合级 Δ 值
      - 持仓级明细（新增/清仓/加仓/减仓）
      - 分类迁移（A 股/基金/债券 之间的仓位变化）
      - 距上次报告天数（用于单位时间 Δ% 计算）

    trim(top_n=5) 方法返回裁剪版本，减少 LLM token 占用约 60%。
    """

    # ── 组合级 ──
    total_value_diff: float = 0.0          # 总市值变化
    total_value_diff_pct: float = 0.0      # 总市值变化率
    total_pnl_diff: float = 0.0            # 总盈亏变化
    days_since_last_report: int = 0        # 距上次报告天数

    # ── 持仓级 ──
    added: tuple[HoldingDiff, ...] = ()        # 新增持仓
    removed: tuple[HoldingDiff, ...] = ()      # 清仓持仓
    increased: tuple[HoldingDiff, ...] = ()    # 加仓
    decreased: tuple[HoldingDiff, ...] = ()    # 减仓

    # ── 元数据 ──
    is_first_check: bool = False               # 首次运行（无对比基准）
    trimmed: bool = False                      # 是否已被裁剪

    def trim(self, top_n: int = 5) -> DiffSummary:
        """返回裁剪后的差异摘要（仅保留前 top_n 条变化）。

        减小 LLM token 占用约 60%。
        裁剪后 trimmed=True。
        """
        return DiffSummary(
            total_value_diff=self.total_value_diff,
            total_value_diff_pct=self.total_value_diff_pct,
            total_pnl_diff=self.total_pnl_diff,
            days_since_last_report=self.days_since_last_report,
            added=self.added[:top_n],
            removed=self.removed[:top_n],
            increased=self.increased[:top_n],
            decreased=self.decreased[:top_n],
            is_first_check=self.is_first_check,
            trimmed=len(self.added) > top_n
            or len(self.removed) > top_n
            or len(self.increased) > top_n
            or len(self.decreased) > top_n,
        )


# ═══════════════════════════════════════════════════════════════
#  F2：走势数据模型
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class HistoryBar:
    """单日价格/净值数据点。

    F2 as-if 语义：假设当前持仓在过去 N 天份额不变，
    用此价格 × 当前份额计算历史每日市值。

    Attributes:
        date:   日期（YYYY-MM-DD）
        open:   开盘价
        close:  收盘价（用于市值计算）
        high:   最高价
        low:    最低价
        volume: 成交量
    """

    date: str
    open: float = 0.0
    close: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
