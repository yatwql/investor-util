"""收益归因计算与适配层单元测试（「行动建议」章归因子块 + 「智囊团深度复盘」章提示词段落共用计算）。

测试目标（「行动建议」章收益归因子块验收口径）：
  - 共享纯计算 `compute_return_attribution`：TOP5 按 |profit| 排序、正负分列、
    贡献占比精度（固定 fixture <0.01%）、空/零盈亏保护、pos/neg 合计覆盖全部持仓
  - 渲染适配层 `build_return_attribution`：C19 `attribution` 契约、净额合计摘要
    （混合/全盈/全亏三类文案）、不可归因时透传 None
  - 复用断言：`llm/prompts_core._build_profit_attribution_block` 与共享计算
    输出逐字节一致（段落与表格同一数据的两处格式化，避免重复实现）

运行：
  python -m pytest src/test/unit/analysis/test_return_attribution.py -v
"""

from __future__ import annotations

import pytest

from src.python.analysis.return_attribution import (
    build_return_attribution,
    compute_return_attribution,
)
from src.python.llm.prompts_core import _build_profit_attribution_block, _fmt_wan

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]


# ── 固定 fixture：3 盈 3 亏，Σ|profit|=34000 ──────────────────


def _mixed_holdings() -> list[dict]:
    """6 个品种：3 盈 3 亏，盈亏金额互不相同便于验证排序与精度。"""
    profits = [
        ("品种甲", "600900", 10000.0),
        ("品种乙", "000001", 6000.0),
        ("品种丙", "000002", 3000.0),
        ("品种丁", "600905", -8000.0),
        ("品种戊", "600906", -5000.0),
        ("品种己", "600907", -2000.0),
    ]
    return [{"name": n, "code": c, "profit": p} for n, c, p in profits]


def _all_profit_holdings() -> list[dict]:
    return [
        {"name": "品种甲", "code": "600900", "profit": 5000.0},
        {"name": "品种乙", "code": "000001", "profit": 3000.0},
    ]


def _all_loss_holdings() -> list[dict]:
    return [
        {"name": "品种甲", "code": "600900", "profit": -4000.0},
        {"name": "品种乙", "code": "000001", "profit": -2000.0},
    ]


# ── 共享纯计算：compute_return_attribution ────────────────────


class TestComputeReturnAttribution:
    """共享纯计算：TOP5 排序 / 精度 / 保护 / 合计覆盖。"""

    def test_top5_ordering_and_positive_negative_split(self):
        """6 品种 3 盈 3 亏 → TOP5 按 |profit| 降序，正负分列，第 6 名被剔除。"""
        data = compute_return_attribution(_mixed_holdings())
        assert data is not None
        assert data["available"] is True
        assert [i["code"] for i in data["盈利来源"]] == ["600900", "000001", "000002"]
        assert [i["code"] for i in data["亏损来源"]] == ["600905", "600906"]
        # TOP5 总额不含第 6 名（品种己）
        top5_codes = [i["code"] for i in data["盈利来源"]] + [i["code"] for i in data["亏损来源"]]
        assert "600907" not in top5_codes

    def test_contribution_pp_precision_within_threshold(self):
        """固定 fixture 贡献占比精度 <0.01%（占比=盈亏/Σ|profit|*100）。"""
        data = compute_return_attribution(_mixed_holdings())
        assert data is not None
        expected = {"600900": 10000 / 34000 * 100, "600905": -8000 / 34000 * 100}
        got = {i["code"]: i["contribution_pp"] for i in data["盈利来源"] + data["亏损来源"]}
        for code, exp in expected.items():
            assert abs(got[code] - exp) < 0.01

    def test_pos_neg_total_cover_all_holdings(self):
        """pos_total/neg_total 为全部持仓正负合计（非仅 TOP5）。"""
        data = compute_return_attribution(_mixed_holdings())
        assert data is not None
        assert data["pos_total"] == pytest.approx(19000.0)  # 10000+6000+3000（含剔除的丙）
        assert data["neg_total"] == pytest.approx(-15000.0)  # -8000-5000-2000（含剔除的己）
        assert data["total_abs"] == pytest.approx(34000.0)

    def test_none_on_empty_holdings(self):
        """空持仓 → None（无盈亏可归因）。"""
        assert compute_return_attribution([]) is None
        assert compute_return_attribution(None) is None

    def test_none_on_zero_total_pnl(self):
        """Σ|profit|==0（全部平盘）→ None（渲染层写「待生成」占位）。"""
        flat = [
            {"name": "品种甲", "code": "600900", "profit": 0.0},
            {"name": "品种乙", "code": "000001", "profit": 0.0},
        ]
        assert compute_return_attribution(flat) is None

    def test_default_profit_when_missing(self):
        """profit 缺省按 0 处理（不崩溃），全缺省时视为零盈亏。"""
        no_profit = [{"name": "品种甲", "code": "600900"}, {"name": "品种乙", "code": "000001"}]
        assert compute_return_attribution(no_profit) is None


# ── 渲染适配层：build_return_attribution ──────────────────────


class TestBuildReturnAttribution:
    """「行动建议」章适配层：C19 契约 + 净额合计摘要文案。"""

    def test_contract_c19_compliant(self):
        """输出 C19 `attribution` 契约键（available/盈利来源/亏损来源/summary）。"""
        data = build_return_attribution(_mixed_holdings())
        assert data is not None
        assert set(data.keys()) == {"available", "盈利来源", "亏损来源", "summary"}
        assert data["available"] is True

    def test_float_values_kept_for_render(self):
        """contribution_pp/profit 保持全精度浮点（渲染层格式化，非预字符串化）。"""
        data = build_return_attribution(_mixed_holdings())
        assert data is not None
        for item in data["盈利来源"] + data["亏损来源"]:
            assert isinstance(item["contribution_pp"], float)
            assert isinstance(item["profit"], float)

    def test_summary_mixed_net_total(self):
        """混合盈亏 → 摘要含正负合计与净额（3 盈 2 亏口径）。"""
        data = build_return_attribution(_mixed_holdings())
        assert data is not None
        assert "盈利品种合计 +19,000.00" in data["summary"]
        assert "亏损品种合计 -15,000.00" in data["summary"]
        assert "净+4,000.00" in data["summary"]

    def test_summary_all_profit(self):
        """全部品种盈利 → 「全部品种盈利，合计 +…」。"""
        data = build_return_attribution(_all_profit_holdings())
        assert data is not None
        assert data["summary"] == "全部品种盈利，合计 +8,000.00"
        assert data["亏损来源"] == []

    def test_summary_all_loss(self):
        """全部品种亏损 → 「全部品种亏损，合计 …」。"""
        data = build_return_attribution(_all_loss_holdings())
        assert data is not None
        assert data["summary"] == "全部品种亏损，合计 -6,000.00"
        assert data["盈利来源"] == []

    def test_none_when_not_attributable(self):
        """无持仓 / 零盈亏 → 透传 None（渲染层写「待生成」占位）。"""
        assert build_return_attribution([]) is None
        flat = [{"name": "品种甲", "code": "600900", "profit": 0.0}]
        assert build_return_attribution(flat) is None


# ── 复用断言：提示词段落与共享计算逐字节一致 ───────────────────


class TestPromptReuse:
    """`llm/prompts_core._build_profit_attribution_block` 复用共享计算（段落 = 表格同一数据）。"""

    def test_prompt_block_byte_identical_to_shared_computation(self):
        """同一 fixture 下，提示词段落输出与 compute_return_attribution 手工格式化逐字节一致。"""
        holdings = _mixed_holdings()
        data = compute_return_attribution(holdings)
        assert data is not None

        lines = ["【收益归因】（以下数值为贡献占比 pp，非个股收益率，两者不可混用）"]
        pos_parts = [f"{i['name']}(+{i['contribution_pp']:.1f}pp)" for i in data["盈利来源"]]
        lines.append(f"主要盈利来源: {'、'.join(pos_parts)}")
        neg_parts = [f"{i['name']}({i['contribution_pp']:.1f}pp)" for i in data["亏损来源"]]
        lines.append(f"主要亏损来源: {'、'.join(neg_parts)}")
        pos_total = data["pos_total"]
        neg_total = data["neg_total"]
        lines.append(
            f"盈利品种合计 +{_fmt_wan(pos_total)}，亏损品种合计 {_fmt_wan(neg_total)}"
            f"（净{_fmt_wan(pos_total + neg_total)}）"
        )
        expected = "\n".join(lines)

        assert _build_profit_attribution_block(holdings) == expected

    def test_prompt_block_empty_when_not_attributable(self):
        """无可归因数据 → 提示词段落为空字符串（与渲染层「待生成」降级一致）。"""
        assert _build_profit_attribution_block([]) == ""
        flat = [{"name": "品种甲", "code": "600900", "profit": 0.0}]
        assert _build_profit_attribution_block(flat) == ""
