"""持仓关系矩阵页签·相关性区块 Excel 呈现测试。

覆盖（position_structure_sheet 的区块二 _write_correlation_block）：
  - available=True → 写入下三角矩阵 + 配对明细 + 说明区
  - 配对按 |r| 降序、显著标记、r 颜色字体
  - available=False（数据不足）→ 占位文本
  - 相关性数据 None → 相关性区块占位
  - 上三角留空、对角线=1.00、重叠样本不足格=N/A
"""

from __future__ import annotations

import unittest
from typing import Any

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]


def _correlation_data(**extra) -> dict:
    """构造持仓关系矩阵·相关性区块数据契约 mock（2 品种，强负相关）。"""
    d = {
        "available": True,
        "status": "ok",
        "window": 60,
        "sample_count": 60,
        "codes": ["a", "b"],
        "names": {"a": "资产A", "b": "资产B"},
        "matrix": [[1.0, None], [-0.87, 1.0]],
        "p_values": [[None, None], [0.0001, None]],
        "pairs": [
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": -0.87,
                "p_value": 0.0001,
                "significant": True,
                "samples": 60,
            }
        ],
        "insufficient_codes": [],
        "note": "",
    }
    d.update(extra)
    return d


class TestExcelCorrelationSheet(unittest.TestCase):
    """持仓关系矩阵页签·相关性区块 Excel 呈现测试。"""

    def _write(self, correlation_data) -> "object":
        from openpyxl import Workbook

        from src.python.report.position_structure_sheet import write_position_structure_sheet

        wb = Workbook()
        ws = wb.active
        write_position_structure_sheet(ws, overlap_result=None, correlation_data=correlation_data)
        return ws

    def _all_text(self, ws) -> list[list[str]]:
        return [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]

    def _flat(self, ws) -> list[str]:
        return [v for row in self._all_text(ws) for v in row]

    def test_matrix_pairs_and_notes_rendered(self):
        """available=True → 矩阵 + 配对明细 + 说明区齐全。"""
        ws = self._write(_correlation_data())
        titles = [r[0] for r in self._all_text(ws)]
        self.assertTrue(any("相关性矩阵" in t or "持仓相关性" in t for t in titles), f"应含相关性标题，实际: {titles}")
        self.assertTrue(any("配对明细" in t for t in titles), f"应含配对明细标题，实际: {titles}")
        self.assertTrue(any("说明" in t for t in titles), f"应含说明标题，实际: {titles}")
        # 标题顺序：矩阵 → 配对 → 说明
        corr_idx = next(i for i, t in enumerate(titles) if "相关性" in t)
        pairs_idx = next(i for i, t in enumerate(titles) if "配对明细" in t)
        notes_idx = next(i for i, t in enumerate(titles) if "说明" in t)
        self.assertLess(corr_idx, pairs_idx)
        self.assertLess(pairs_idx, notes_idx)
        # 配对数据完整
        flat = self._flat(ws)
        self.assertTrue(any("资产A" in v for v in flat))
        self.assertTrue(any("资产B" in v for v in flat))
        self.assertIn("-0.87", flat)
        self.assertIn("0.0001", flat)
        self.assertTrue(any("显著" in v for v in flat))
        # 说明区包含窗口与样本
        self.assertTrue(any("计算窗口" in v for v in flat))

    def test_matrix_lower_triangle_and_diagonal(self):
        """下三角有值、对角线 1.0、上三角留空。"""
        ws = self._write(_correlation_data())
        grid = self._all_text(ws)
        # 矩阵数据行（r[0] 非空即矩阵/标题行，标题不以此前缀开头）
        data_rows = [r for r in grid if r and r[0]]
        a_row = next(r for r in data_rows if r[0].startswith("资产A"))
        b_row = next(r for r in data_rows if r[0].startswith("资产B"))
        self.assertIn("1.0", a_row)  # 对角线（raw float，number_format 显示 1.00）
        self.assertIn("", a_row)  # 上三角留空
        self.assertIn("-0.87", b_row)  # 下三角 r

    def test_na_cell_for_insufficient_overlap(self):
        """重叠样本不足品种 → 相关性格为 N/A。"""
        data = _correlation_data()
        data["matrix"] = [[1.0, None], [None, 1.0]]
        data["insufficient_codes"] = ["a", "b"]
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertIn("N/A", flat)
        # 说明区提示数据不足品种
        self.assertTrue(any("不足" in v and "a" in v for v in flat))

    def test_unavailable_placeholder(self):
        """available=False（数据不足/源故障）→ 占位文本。"""
        data = _correlation_data(available=False, status="insufficient", codes=[], matrix=[], pairs=[])
        ws = self._write(data)
        flat = self._flat(ws)
        self.assertTrue(any("持仓相关性数据暂不可用" in v for v in flat), "available=False 应写占位")

    def test_none_placeholder(self):
        """correlation_data=None → 整页占位。"""
        ws = self._write(None)
        flat = self._flat(ws)
        self.assertTrue(any("持仓相关性数据暂不可用" in v for v in flat), "None 应写整页占位")

    def test_pairs_sorted_by_abs_r(self):
        """配对明细按 |r| 降序（与 HTML 一致）。"""
        data = _correlation_data()
        data["codes"] = ["a", "b", "c"]
        data["names"] = {"a": "资产A", "b": "资产B", "c": "资产C"}
        data["matrix"] = [
            [1.0, None, None],
            [-0.2, 1.0, None],
            [0.9, 0.1, 1.0],
        ]
        data["pairs"] = [
            {
                "code_a": "c",
                "name_a": "资产C",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": 0.9,
                "p_value": 0.001,
                "significant": True,
                "samples": 60,
            },
            {
                "code_a": "b",
                "name_a": "资产B",
                "code_b": "a",
                "name_b": "资产A",
                "pearson": -0.2,
                "p_value": 0.1,
                "significant": False,
                "samples": 60,
            },
            {
                "code_a": "c",
                "name_a": "资产C",
                "code_b": "b",
                "name_b": "资产B",
                "pearson": 0.1,
                "p_value": 0.2,
                "significant": False,
                "samples": 60,
            },
        ]
        ws = self._write(data)
        rows = self._all_text(ws)
        # 只取「配对明细」表内的 r 列（第 4 列，index 3），排除矩阵格干扰
        pairs_idx = next(i for i, r in enumerate(rows) if r and "配对明细" in r[0])
        pearson_vals: list[float] = []
        for r in rows[pairs_idx + 2 :]:  # +1 表头行，+1 跳到首条数据
            if not r or not r[0] or r[0] == "说明":
                break  # 数据行结束（空行或说明标题）
            pearson_vals.append(float(r[3]))
        self.assertEqual(pearson_vals, [0.9, -0.2, 0.1])
        self.assertEqual(pearson_vals, sorted(pearson_vals, key=abs, reverse=True), "配对应严格按 |r| 降序")
        # 显著标记出现在 0.9 那对
        flat_pairs = [v for r in rows[pairs_idx:] for v in r]
        self.assertTrue(any("显著" in v for v in flat_pairs))


def _overlap_result(**extra) -> dict:
    """构造持仓关系矩阵·重合度区块结构（2 只基金，部分重合 50%）。"""
    d = {
        "fund_names": {"a": "基金A", "b": "基金B"},
        "funds": ["a", "b"],
        "matrix": [
            [1.0, 0.5],
            [0.5, 1.0],
        ],
        "pairs": [
            {
                "fund_a": "a",
                "fund_b": "b",
                "name_a": "基金A",
                "name_b": "基金B",
                "code_a": "a",
                "code_b": "b",
                "common_count": 2,
                "jaccard": 0.5,
                "common_stocks": [
                    {"name": "贵州茅台", "code": "600519"},
                    {"name": "五粮液", "code": "000858"},
                ],
            }
        ],
    }
    d.update(extra)
    return d


class TestExcelMergedPositionStructureSheet(unittest.TestCase):
    """持仓关系矩阵页签·一章两区块（重合度 + 相关性）Excel 呈现测试。"""

    def _write(self, overlap_result, correlation_data, stale_fund_notes=None) -> "object":
        from openpyxl import Workbook

        from src.python.report.position_structure_sheet import write_position_structure_sheet

        wb = Workbook()
        ws = wb.active
        write_position_structure_sheet(
            ws,
            overlap_result=overlap_result,
            correlation_data=correlation_data,
            stale_fund_notes=stale_fund_notes,
        )
        return ws

    def _flat(self, ws) -> list[str]:
        return [str(c.value) if c.value is not None else "" for row in ws.iter_rows() for c in row]

    def test_both_blocks_render_in_one_sheet(self):
        """重合度 + 相关性同时提供 → 一章两区块同页呈现（正文标题纯中文名，序号仅在页签栏）。"""
        ws = self._write(_overlap_result(), _correlation_data())
        flat = self._flat(ws)
        self.assertTrue(any("持仓结构与集中度" in v for v in flat), f"应含章节标题，实际: {flat[:3]}")
        self.assertTrue(any("一、持仓重合度矩阵" in v for v in flat), "应含重合度区块标题")
        self.assertTrue(any("二、持仓相关性矩阵" in v for v in flat), "应含相关性区块标题")
        self.assertTrue(any("基金A" in v for v in flat), "重合度区块应含基金名")
        self.assertTrue(any("资产A" in v for v in flat), "相关性区块应含资产名")
        # 区块顺序：重合度在上、相关性在下
        overlap_idx = next(i for i, v in enumerate(flat) if "一、持仓重合度矩阵" in v)
        corr_idx = next(i for i, v in enumerate(flat) if "二、持仓相关性矩阵" in v)
        self.assertLess(overlap_idx, corr_idx, "重合度区块应位于相关性区块之前")

    def test_overlap_placeholder_when_correlation_only(self):
        """仅提供相关性数据 → 重合度区块写占位（相关度矩阵照常呈现）。"""
        ws = self._write(None, _correlation_data())
        flat = self._flat(ws)
        self.assertTrue(any("无法计算重合度" in v for v in flat), "重合度区块应写占位")
        self.assertTrue(any("资产B" in v for v in flat), "相关性矩阵应正常呈现")

    def test_correlation_placeholder_when_overlap_only(self):
        """仅提供重合度数据 → 相关性区块写占位（重合度矩阵照常呈现）。"""
        ws = self._write(_overlap_result(), None)
        flat = self._flat(ws)
        self.assertTrue(any("基金A" in v for v in flat), "重合度矩阵应正常呈现")
        self.assertTrue(any("持仓相关性数据暂不可用" in v for v in flat), "相关性区块应写占位")

    def test_overlap_jaccard_value_rendered(self):
        """重合度区块 Jaccard 系数值以百分比呈现。"""
        ws = self._write(_overlap_result(), _correlation_data())
        flat = self._flat(ws)
        self.assertTrue(any("50.00%" in v for v in flat), "重合度 Jaccard 0.5 应呈现为 50.00%")
        self.assertTrue(any("100.00%" in v for v in flat), "对角线 1.0 应呈现为 100.00%")

    def test_stale_fund_exclusion_noted(self):
        """被剔除的陈旧基金须在矩阵上方留痕（否则读者以为矩阵算错了）。"""
        ws = self._write(
            _overlap_result(),
            _correlation_data(),
            stale_fund_notes=["陈年基金（报告期 2020-03-31，已过 20 个完整季度）"],
        )
        flat = self._flat(ws)
        self.assertTrue(any("已从矩阵剔除" in v for v in flat), "应写剔除说明行")
        self.assertTrue(any("陈年基金" in v and "2020-03-31" in v for v in flat), "应含被剔除基金名与报告期")

    def test_no_stale_note_when_none_excluded(self):
        """无陈旧基金 → 不出现剔除说明行（零噪声）。"""
        ws = self._write(_overlap_result(), _correlation_data())
        flat = self._flat(ws)
        self.assertFalse(any("已从矩阵剔除" in v for v in flat), "无剔除时不应出现说明行")


def _item(**extra: Any) -> dict:
    """构造 compute_concentration() 的单行结果。"""
    base: dict[str, Any] = {
        "name": "易方达中小盘混合",
        "code": "110011",
        "report_period": "2026-06-30",
        "report_stale": False,
        "top3_pct": 24.5,
        "top5_pct": 35.5,
        "top10_pct": 35.5,
        "prev_top10_pct": None,
        "change_pct": None,
        "alert_level": "正常",
        "is_first_check": False,
        "period_unchanged": False,
    }
    base.update(extra)
    return base


# ═══════════════════════════════════════════════════════════
#  区块三：持仓集中度（由 test_fund_concentration_sheet.py 迁入）
# ═══════════════════════════════════════════════════════════


class TestConcentrationBlock(unittest.TestCase):
    """write_concentration_sheet：报告期与环比语义的呈现。"""

    def _write(self, data: list[dict]) -> "object":
        from openpyxl import Workbook

        from src.python.report.position_structure_sheet import _write_concentration_block

        wb = Workbook()
        ws = wb.active
        _write_concentration_block(ws, 1, data)
        return ws

    def _rows(self, ws) -> list[list[str]]:
        return [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]

    def _flat(self, ws) -> list[str]:
        return [v for row in self._rows(ws) for v in row]

    def test_header_includes_report_period(self):
        """表头含「报告期」列（否则读者无从判断占比是哪一期的持仓）。"""
        ws = self._write([_item()])
        header = self._rows(ws)[1]
        self.assertIn("报告期", header)
        self.assertLess(header.index("基金代码"), header.index("报告期"))
        self.assertLess(header.index("报告期"), header.index("前3占比%"))

    def test_report_period_rendered(self):
        """报告期逐行呈现，与数据同列。"""
        ws = self._write([_item(report_period="2025-12-31")])
        header = self._rows(ws)[1]
        data_row = next(r for r in self._rows(ws) if r and r[0] == "易方达中小盘混合")
        self.assertEqual(data_row[header.index("报告期")], "2025-12-31")

    def test_stale_report_period_suffixed(self):
        """报告期陈旧 → 期次后缀「（陈旧）」，一眼可辨。"""
        ws = self._write([_item(report_period="2020-03-31", report_stale=True)])
        flat = self._flat(ws)
        self.assertTrue(any("2020-03-31（陈旧）" in v for v in flat), f"应标注陈旧，实际: {flat}")

    def test_period_unchanged_no_comparison_meaning(self):
        """报告期未推进 → 环比「无对比意义」、标识「报告期未推进」（不报 0 冒充无变化）。"""
        ws = self._write([_item(period_unchanged=True, prev_top10_pct=35.5, change_pct=None)])
        flat = self._flat(ws)
        self.assertIn("无对比意义", flat)
        self.assertTrue(any("报告期未推进" in v for v in flat), f"标识列应说明原因，实际: {flat}")
        self.assertFalse(any("基线已记录" in v for v in flat), "报告期未推进不应显示为基线已记录")
        self.assertFalse(any("→ 0.00%" in v or "+0.00%" in v for v in flat), "不应把环比呈现为 0")

    def test_advanced_period_renders_change(self):
        """报告期推进 → 照常呈现环比箭头与预警标识（闸门不可误伤正常对比）。"""
        ws = self._write([_item(report_period="2026-06-30", prev_top10_pct=30.0, change_pct=5.5, alert_level="正常")])
        flat = self._flat(ws)
        self.assertTrue(any("↑ +5.50%" in v for v in flat), f"应呈现环比，实际: {flat}")
        self.assertFalse(any("无对比意义" in v for v in flat), "报告期已推进不应标为无对比意义")
        self.assertTrue(any("✅ 正常" in v for v in flat))

    def test_first_check_keeps_baseline_label(self):
        """首检 → 环比「基线已记录」，不受报告期语义影响。"""
        ws = self._write([_item(is_first_check=True, prev_top10_pct=None, change_pct=None)])
        flat = self._flat(ws)
        self.assertIn("基线已记录", flat)
        self.assertFalse(any("无对比意义" in v for v in flat))


# ═══════════════════════════════════════════════════════════
#  合并章节：一次调用承载三区块 + OR 可见性
# ═══════════════════════════════════════════════════════════


class TestWritePositionStructureSheet(unittest.TestCase):
    """合并章节写入器：单页签承载三个区块，缺失区块独立降级。"""

    def _ws(self):
        import openpyxl

        wb = openpyxl.Workbook()
        return wb.active

    def _overlap(self):
        return {
            "funds": ["161725", "110022"],
            "fund_names": {"161725": "招商中证白酒", "110022": "易方达消费行业"},
            "matrix": [[1.0, 0.35], [0.35, 1.0]],
            "pairs": [
                {
                    "fund_a": "161725",
                    "fund_b": "110022",
                    "jaccard": 0.35,
                    "overlap_ratio": 0.5,
                    "common_count": 3,
                    "common_stocks": [{"code": "600519", "name": "贵州茅台"}],
                }
            ],
        }

    def _correlation(self):
        return {
            "available": True,
            "codes": ["600519", "000858"],
            "names": {"600519": "贵州茅台", "000858": "五粮液"},
            "matrix": [[1.0, None], [0.62, 1.0]],
            "p_values": [[0.0, None], [0.01, 0.0]],
            "pairs": [
                {
                    "code_a": "000858",
                    "code_b": "600519",
                    "name_a": "五粮液",
                    "name_b": "贵州茅台",
                    "pearson": 0.62,
                    "p_value": 0.01,
                    "samples": 60,
                    "significant": True,
                }
            ],
            "window": 60,
            "sample_count": 60,
            "insufficient_codes": [],
        }

    def _concentration(self):
        return [
            {
                "name": "招商中证白酒",
                "code": "161725",
                "report_period": "2026-06-30",
                "top3_pct": 55.0,
                "top5_pct": 70.0,
                "top10_pct": 85.0,
                "prev_top10_pct": 80.0,
                "change_pct": 5.0,
                "alert_level": "关注",
                "is_first_check": False,
                "period_unchanged": False,
            }
        ]

    def test_title_and_three_blocks(self):
        """首行为合并章节显示名，三个区块小节标题同页签。"""
        from src.python.core.registry import get_report_sheet_name
        from src.python.report.position_structure_sheet import write_position_structure_sheet

        ws = self._ws()
        write_position_structure_sheet(
            ws,
            self._overlap(),
            fund_names={"161725": "招商中证白酒", "110022": "易方达消费行业"},
            correlation_data=self._correlation(),
            concentration_data=self._concentration(),
        )
        col_a = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        self.assertEqual(ws["A1"].value, get_report_sheet_name("position_structure"))
        self.assertEqual(ws["A1"].value, "持仓结构与集中度")
        self.assertIn("一、持仓重合度矩阵", col_a)
        self.assertIn("二、持仓相关性矩阵", col_a)
        self.assertIn("三、持仓集中度监控", col_a)

    def test_blocks_equal_standalone_rendering(self):
        """内容等价：区块一/二/三的数据行与各自独立调用（起始行=1）逐格相等。"""
        import openpyxl

        from src.python.report.position_structure_sheet import (
            _write_concentration_block,
            _write_correlation_block,
            _write_overlap_block,
            write_position_structure_sheet,
        )

        ws = self._ws()
        write_position_structure_sheet(
            ws,
            self._overlap(),
            fund_names=None,
            correlation_data=self._correlation(),
            concentration_data=self._concentration(),
        )

        wb2 = openpyxl.Workbook()
        ws_ref = wb2.active
        _write_overlap_block(ws_ref, 1, self._overlap(), None, 16, None)
        ws_cat = wb2.create_sheet()
        _write_correlation_block(ws_cat, 1, self._correlation(), 16)
        ws_conc = wb2.create_sheet()
        _write_concentration_block(ws_conc, 1, self._concentration())

        def dump(sheet, marker, ncols=12):
            rows = []
            started = False
            for r in range(1, sheet.max_row + 1):
                first = sheet.cell(row=r, column=1).value
                if first == marker:
                    started = True
                if started:
                    rows.append([sheet.cell(row=r, column=c).value for c in range(1, ncols)])
            return rows

        # 区块一：合并页签中自「配对明细（按重合度降序）」起与独立一致
        for marker in ("配对明细（按重合度降序）",):
            merged = dump(ws, marker)
            ref = dump(ws_ref, marker)
            self.assertTrue(merged, f"合并页签缺少 {marker}")
            self.assertEqual(merged[: len(ref)], ref, f"{marker} 行内容与独立写入不一致")

        # 区块三：集中度表头与数据行一致
        merged_conc = dump(ws, "三、持仓集中度监控", 11)
        ref_conc = dump(ws_conc, "三、持仓集中度监控", 11)
        self.assertEqual(merged_conc, ref_conc, "集中度区块行内容与独立写入不一致")

    def test_missing_concentration_writes_placeholder_only(self):
        """仅有关系数据（OR 场景）→ 集中度区块写占位，其余区块正常。"""
        from src.python.report.position_structure_sheet import write_position_structure_sheet

        ws = self._ws()
        write_position_structure_sheet(ws, self._overlap(), correlation_data=self._correlation())
        col_a = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        self.assertIn("三、持仓集中度监控", col_a)
        # 占位文案出现在集中度区块之后
        idx = col_a.index("三、持仓集中度监控")
        tail = " ".join(str(v) for v in col_a[idx:] if v)
        self.assertIn("集中度", tail)
        self.assertNotIn("161725", [v for v in col_a[idx:] if isinstance(v, str) and v == "161725"])

    def test_only_concentration_data_renders_other_blocks_as_placeholder(self):
        """仅有集中度数据 → 重合度/相关性区块写占位，集中度正常（OR 可见性另一侧）。"""
        from src.python.report.position_structure_sheet import write_position_structure_sheet

        ws = self._ws()
        write_position_structure_sheet(ws, None, correlation_data=None, concentration_data=self._concentration())
        col_a = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        self.assertIn("一、持仓重合度矩阵", col_a)
        self.assertIn("二、持仓相关性矩阵", col_a)
        self.assertIn("三、持仓集中度监控", col_a)
        self.assertIn("招商中证白酒", col_a)
