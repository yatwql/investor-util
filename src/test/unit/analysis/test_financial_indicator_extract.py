"""财务指标提取（DataSinking 全文解析层）单元测试。

覆盖：真实年报章节夹具的逐字段复现、同比派生、每股收益无分隔连写切分、
百分数换算、金额单位换算、易混行（扣非）排除、缺字段取 None、无覆盖降级。

真实夹具：``src/test/data/fixtures/datasink_indicator_section_600900.md``
（长江电力 600900.SS 2025 年报「公司简介和主要财务指标」章节，核对值见该目录 README）。

运行：
  pytest src/test/unit/analysis/test_financial_indicator_extract.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.python.analysis.financial_indicator_extract import PARSED_FIELDS, extract_indicators
from src.python.schemas.datasource_fields import FinancialIndicatorFields

pytestmark = [pytest.mark.unit, pytest.mark.unit_analysis]

_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "datasink_indicator_section_600900.md"

#: 合成片段的前缀（模拟「主要会计数据」表头与单位声明）
_PREFIX = "(一) 主要会计数据单位：元币种：人民币主要会计数据2025年2024年本期比上年同期增减2023年调整后调整前"


def _fixture_text() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def _synthetic(rows: str, unit: str = "单位：元币种：人民币") -> str:
    """构造最小可解析正文（表头 + 指定指标行）。"""
    return f"(一) 主要会计数据{unit}主要会计数据2025年2024年本期比上年同期增减2023年调整后调整前{rows}"


# ═══════════════════════════════════════════════════════════════
#  真实年报章节回归（夹具锁定上游形态）
# ═══════════════════════════════════════════════════════════════


class TestRealAnnualReportFixture:
    """对真实年报章节的逐字段复现（核对值 = 年报披露值）。"""

    def _record(self) -> dict:
        return extract_indicators(
            _fixture_text(), code="600900", symbol="600900.SS", report_period="2025-12-31", doc_type="annual"
        )

    def test_amounts_match_disclosure(self):
        """营收/归母净利/经营现金流与年报一致（元）。"""
        row = self._record()
        assert row["revenue"] == pytest.approx(86_241_940_222.20)
        assert row["net_profit"] == pytest.approx(34_502_809_176.39)
        assert row["operating_cash_flow"] == pytest.approx(60_562_925_570.41)

    def test_per_share_and_ratio_match_disclosure(self):
        """每股收益与 ROE 与年报一致（ROE 已换算为小数比例）。"""
        row = self._record()
        assert row["eps"] == pytest.approx(1.4101)
        assert row["roe"] == pytest.approx(0.159)

    def test_derived_yoy_matches_disclosed_percent(self):
        """派生同比与披露的两位百分数一致（2.07% / 6.17%）。"""
        row = self._record()
        assert row["revenue_yoy"] == pytest.approx(0.0207)
        assert row["net_profit_yoy"] == pytest.approx(0.0617)

    def test_fields_outside_section_stay_none(self):
        """章节不提供的字段恒为 None（不猜、不填 0）。"""
        row = self._record()
        assert row["gross_margin"] is None
        assert row["debt_ratio"] is None
        assert row["bvps"] is None

    def test_metadata_passthrough_and_full_key_set(self):
        """元数据原样写入，键集恰为标准字段集。"""
        row = self._record()
        assert set(row) == set(FinancialIndicatorFields().to_dict())
        assert row["code"] == "600900"
        assert row["symbol"] == "600900.SS"
        assert row["report_period"] == "2025-12-31"
        assert row["doc_type"] == "annual"

    def test_source_identity_left_to_adapter(self):
        """解析层不填源身份字段（由适配器强制注入，避免自报覆盖链路标签）。"""
        row = self._record()
        assert row["source_api"] == ""
        assert row["source"] == ""


# ═══════════════════════════════════════════════════════════════
#  行文变体
# ═══════════════════════════════════════════════════════════════


class TestWordingVariants:
    def test_parent_company_wording(self):
        """旧式行文「归属于母公司股东的净利润」同样识别。"""
        row = extract_indicators(_synthetic("归属于母公司股东的净利润34,502,809,176.3932,496,172,808.65"))
        assert row["net_profit"] == pytest.approx(34_502_809_176.39)
        assert row["net_profit_yoy"] == pytest.approx(0.0617)

    def test_both_revenue_wordings_use_first_row(self):
        """「营业总收入」与「营业收入」并存时取正文首个（本期口径一致）。"""
        row = extract_indicators(_synthetic("营业收入86,241,940,222.2084,491,870,566.52"))
        assert row["revenue"] == pytest.approx(86_241_940_222.20)

    def test_amount_unit_declaration_between_anchor_and_value(self):
        """锚点与数值之间允许「（元）」等标注。"""
        row = extract_indicators(_synthetic("营业收入（元）86,241,940,222.2084,491,870,566.52"))
        assert row["revenue"] == pytest.approx(86_241_940_222.20)

    def test_first_occurrence_wins(self):
        """同一锚点重复出现（如正文与附注各一次）时取首个。"""
        text = _synthetic("营业收入86,241,940,222.2084,491,870,566.52") + "营业收入999.00999.00"
        row = extract_indicators(text)
        assert row["revenue"] == pytest.approx(86_241_940_222.20)


class TestNumberPrecision:
    def test_eps_glued_four_decimals_are_split(self):
        """无分隔连写「1.41011.3281」按四位小数正确切分。"""
        row = extract_indicators(_synthetic("基本每股收益（元／股）1.41011.32811.32816.171.1135"))
        assert row["eps"] == pytest.approx(1.4101)

    def test_percent_normalized_to_ratio(self):
        """比率字段百分数 → 小数比例。"""
        row = extract_indicators(_synthetic("加权平均净资产收益率（%）15.9015.7115.71增加0.19 个百分点13.52"))
        assert row["roe"] == pytest.approx(0.159)

    def test_negative_amounts(self):
        """负值（亏损）保留符号。"""
        row = extract_indicators(_synthetic("归属于上市公司股东的净利润-1,234,567,890.12-2,000,000,000.00"))
        assert row["net_profit"] == pytest.approx(-1_234_567_890.12)
        assert row["net_profit_yoy"] == pytest.approx(0.3827)

    def test_wan_yuan_scaling(self):
        """「单位：万元」声明下的金额换算为元。"""
        row = extract_indicators(_synthetic("营业收入86,241,940.2284,491,870.57", unit="单位：万元币种：人民币"))
        assert row["revenue"] == pytest.approx(862_419_402_200.0)

    def test_yi_yuan_scaling(self):
        """「单位：亿元」声明下的金额换算为元。"""
        row = extract_indicators(_synthetic("营业收入862.42844.92", unit="单位：亿元币种：人民币"))
        assert row["revenue"] == pytest.approx(86_242_000_000.0)


class TestExclusions:
    def test_deducted_earnings_rows_are_not_used(self):
        """仅有「扣除非经常性损益后的…」行时，对应标准字段留空。"""
        text = _synthetic(
            "归属于上市公司股东的扣除非经常性损益的净利润33,445,575,299.9432,507,551,977.06"
            "扣除非经常性损益后的基本每股收益（元／股）1.36691.3286"
            "扣除非经常性损益后的加权平均净资产收益率（%）15.4115.72"
        )
        assert extract_indicators(text) is None

    def test_amounts_skipped_without_unit_declaration(self):
        """缺「单位：」声明时金额字段留空，但比率/每股字段仍可用。"""
        text = _synthetic("营业收入86,241,940,222.2084,491,870,566.52", unit="")
        row = extract_indicators(f"{text}基本每股收益（元／股）1.41011.3281")
        assert row is not None
        assert row["revenue"] is None
        assert row["eps"] == pytest.approx(1.4101)


class TestDegradation:
    def test_empty_content_returns_none(self):
        assert extract_indicators("") is None
        assert extract_indicators(None) is None

    def test_no_anchor_returns_none(self):
        """正文无任何标准指标行 → None（上层按无覆盖处理）。"""
        assert extract_indicators("公司简介和主要财务指标\n管理层讨论与分析\n无指标数据") is None

    def test_partial_record_keeps_found_fields(self):
        """只解析到部分字段时仍返回记录，其余字段为 None。"""
        row = extract_indicators(_synthetic("营业收入86,241,940,222.2084,491,870,566.52"))
        assert row is not None
        assert row["revenue"] == pytest.approx(86_241_940_222.20)
        assert row["eps"] is None
        assert row["roe"] is None

    def test_parsed_fields_declaration_covers_fixture(self):
        """声明可解析字段集与夹具实际解析结果一致（防声明漂移）。"""
        row = extract_indicators(_fixture_text(), code="600900", report_period="2025-12-31", doc_type="annual")
        produced = {name for name in PARSED_FIELDS if row[name] is not None}
        assert produced == set(PARSED_FIELDS)
