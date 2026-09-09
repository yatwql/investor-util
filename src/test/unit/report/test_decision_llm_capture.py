"""决策跨期反思闭环 — LLM 智囊团操作建议表解析登记单元测试。

覆盖：expert_review HTML 表行定位（块级换行剥离）、表头/分隔/校验摘要行跳过、
方向映射（减仓/加仓/持有）、未识别操作跳过、非持仓 code 剔除、同 code 取高优
先级、纯文本输入兼容、登记落账 pending（仅可结算方向且带基线）、开关关闭无感、
含交易所前缀持仓代码别名对账。全部本地字符串，防网络。

运行：
  pytest src/test/unit/report/test_decision_llm_capture.py -v
"""

from __future__ import annotations

import pytest

from src.python.config.features import set_feature_enabled, reset_feature_flags
from src.python.core import decision_ledger as dl
from src.python.report import decision_llm_capture as cap

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

# 与 fact_checker 真实用例同款持仓白名单（见 test_fact_checker.py table_holdings）
_HOLDINGS: list[dict] = [
    {"name": "华安纳斯达克100ETF联接基金A", "code": "040046", "price": 1.234, "market_value": 100000.0},
    {"name": "建信高端装备股票A", "code": "011506", "price": 0.89, "market_value": 50000.0},
    {"name": "招商中证电池主题ETF", "code": "561910", "price": 0.712, "market_value": 30000.0},
    {"name": "长江电力", "code": "600900", "price": 22.5, "market_value": 20000.0},
]

# HTML 输入：markdown_to_html 将每个表行落为 <p>| ... |</p>（竖线保留），块间无换行
_HTML_HEADER = "<h3>操作建议</h3><p>| 优先级 | 品种 | 建议操作 | 理由 |</p><p>|:------:|------|:--------:|------|</p>"

# 一段含「减仓(high)」与「持有(low)」两行的完整 expert_review HTML
_HTML_TWO_ROWS = _HTML_HEADER + (
    "<p>| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 市场占比10.6%，已是组合第三大持仓却贡献负收益 |</p>"
    "<p>| 🟢 低 | 040046 华安纳斯达克100ETF联接基金A | 持有 | 收益率+1.16%，组合第一大重仓，继续持有 |</p>"
)


@pytest.fixture(autouse=True)
def _enable_flag():
    """本组测试需要 decision_reflection 开启；结束后复位。"""
    set_feature_enabled("decision_reflection", True)
    yield
    reset_feature_flags()


def _ids_for(rows):
    return [r["code"] for r in rows]


class TestIterAndParseRows:
    """表行定位与单元格解析。"""

    def test_empty_html(self):
        assert list(cap._iter_table_rows("")) == []
        assert list(cap._iter_table_rows(None)) == []

    def test_table_rows_extracted_from_html(self):
        rows = list(cap._iter_table_rows(_HTML_TWO_ROWS))
        # 表头、分隔行、两数据行都被规整为 | 起止的行
        assert len(rows) == 4
        assert all(r.startswith("|") and r.endswith("|") for r in rows)

    def test_non_pipe_content_skipped(self):
        html = "<h3>操作建议</h3><p>| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 理由 |</p><p>✓ 校验通过，无误。</p>"
        rows = list(cap._iter_table_rows(html))
        assert len(rows) == 1
        assert "561910" in rows[0]

    def test_plain_text_table_accepted(self):
        text = "| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 理由 |"
        rows = list(cap._iter_table_rows(text))
        assert rows == [text]

    def test_header_and_separator_skipped(self):
        assert cap._parse_table_row("| 优先级 | 品种 | 建议操作 | 理由 |") is None
        assert cap._parse_table_row("|:------:|------|:--------:|------|") is None

    def test_parse_short_high_row(self):
        row = cap._parse_table_row("| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 市场占比10.6%，负收益 |")
        assert row["code"] == "561910"
        assert row["direction"] == dl.DIRECTION_SHORT
        assert row["magnitude"] == "high"
        assert row["name"] == "招商中证电池主题ETF"
        assert "10.6%" in row["detail"]

    def test_parse_long_and_mid(self):
        row = cap._parse_table_row("| 🟡 中 | 600900 长江电力 | 加仓 | 分红稳定 |")
        assert row["direction"] == dl.DIRECTION_LONG
        assert row["magnitude"] == "mid"

    def test_unrecognized_operation_skipped(self):
        assert cap._parse_table_row("| 🔴 高 | 600900 长江电力 | 观望 | 理由 |") is None

    def test_no_code_row_skipped(self):
        # 表头行有「品种」列但无 code → 跳过（已在 header 用例验证）；此处验证理由含代码不影响
        row = cap._parse_table_row("| 🟢 低 | 600900 | 减仓 | 建议关注 561910 走势 |")
        assert row is not None and row["code"] == "600900"  # code 只从品种格取

    def test_reason_with_inner_pipe_merged(self):
        # 理由格内含竖线（markdown_to_html 不转义）→ 剩余列并入 detail
        row = cap._parse_table_row("| 🔴 高 | 600900 长江电力 | 减仓 | 触发 10% | 双止损线 |")
        assert row is not None
        assert "触发 10%" in row["detail"]
        assert "双止损线" in row["detail"]


class TestExtract:
    """抽取 → 决策行（白名单 + 持有剔除 + 去重）。"""

    def test_empty_html_no_rows(self):
        assert cap.extract_llm_decisions(None, _HOLDINGS) == []
        assert cap.extract_llm_decisions("", _HOLDINGS) == []

    def test_hold_neutral_excluded(self):
        rows = cap.extract_llm_decisions(_HTML_TWO_ROWS, _HOLDINGS)
        # 仅 561910 减仓(short) 入；040046 持有(flat) 剔除
        assert _ids_for(rows) == ["561910"]
        assert rows[0]["direction"] == dl.DIRECTION_SHORT

    def test_add_long_included(self):
        html = _HTML_HEADER + "<p>| 🟡 中 | 600900 长江电力 | 加仓 | 分红稳定 |</p>"
        rows = cap.extract_llm_decisions(html, _HOLDINGS)
        assert _ids_for(rows) == ["600900"]
        assert rows[0]["direction"] == dl.DIRECTION_LONG
        assert rows[0]["magnitude"] == "mid"
        assert rows[0]["baseline_close"] == 22.5

    def test_code_not_in_holdings_excluded(self):
        # 600519 贵州茅台不在白名单 → 剔除
        html = _HTML_HEADER + "<p>| 🔴 高 | 600519 贵州茅台 | 减仓 | 权重过高 |</p>"
        assert cap.extract_llm_decisions(html, _HOLDINGS) == []

    def test_name_fallback_and_baseline(self):
        # 品种格无名称 → 回填持仓名；price 即为 baseline
        html = _HTML_HEADER + "<p>| 🔴 高 | 561910 | 减仓 | 负收益 |</p>"
        rows = cap.extract_llm_decisions(html, _HOLDINGS)
        assert rows[0]["name"] == "招商中证电池主题ETF"
        assert rows[0]["baseline_close"] == 0.712

    def test_same_code_keeps_higher_priority(self):
        # 同 code 两行：先 low 后 high → 取 high
        html = _HTML_HEADER + (
            "<p>| 🟢 低 | 600900 长江电力 | 减仓 | 保守 |</p><p>| 🔴 高 | 600900 长江电力 | 减仓 | 触及双止盈线 |</p>"
        )
        rows = cap.extract_llm_decisions(html, _HOLDINGS)
        assert len(rows) == 1
        assert rows[0]["magnitude"] == "high"
        assert rows[0]["detail"] == "触及双止盈线"

    def test_holdings_prefix_code_alias(self):
        # 持仓 code 带 sh 前缀（场内），表内裸 6 位 → 别名命中
        holdings = [{"name": "浦发银行", "code": "sh600000", "price": 10.0}]
        html = _HTML_HEADER + "<p>| 🟡 中 | 600000 浦发银行 | 减仓 | 破位 |</p>"
        rows = cap.extract_llm_decisions(html, holdings)
        assert len(rows) == 1
        assert rows[0]["code"] == "600000"
        assert rows[0]["name"] == "浦发银行"

    def test_fact_check_summary_appended_not_parsed(self):
        # 事实校验摘要为 <p>✓ ...</p> 尾注，不以 | 起止 → 不影响抽取
        html = _HTML_HEADER + (
            "<p>| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 负收益 |</p><p>✓ 校验通过：持仓与价格表述一致。</p>"
        )
        rows = cap.extract_llm_decisions(html, _HOLDINGS)
        assert _ids_for(rows) == ["561910"]


class TestRegister:
    """登记落账（仅可结算方向且带基线）。"""

    def test_register_appends_pending(self, tmp_path):
        lp = str(tmp_path / "ledger.jsonl")
        out = cap.register_llm_decisions(_HTML_TWO_ROWS, _HOLDINGS, report_date="2026-09-01", path=lp)
        assert out["registered"] == 1
        assert len(out["ids"]) == 1
        stats = dl.fold_ledger(path=lp)
        assert stats["pending_count"] == 1
        d = stats["decisions"][0]
        assert d["carrier"] == dl.CARRIER_EXPERT_REVIEW
        assert d["direction"] == dl.DIRECTION_SHORT
        assert d["baseline_close"] == 0.712
        assert d["status"] == "pending"

    def test_register_no_baseline_skipped(self, tmp_path):
        # price 缺失（0）→ 无结算基线，登记跳过（保证入账必可结算）
        holdings = [{"name": "招商中证电池主题ETF", "code": "561910", "price": 0}]
        lp = str(tmp_path / "ledger.jsonl")
        out = cap.register_llm_decisions(_HTML_TWO_ROWS, holdings, path=lp)
        assert out == {"registered": 0, "ids": []}
        assert dl.fold_ledger(path=lp)["settled_count"] == 0

    def test_flag_off_no_register(self, tmp_path):
        reset_feature_flags()  # decision_reflection 默认 False
        lp = str(tmp_path / "ledger.jsonl")
        out = cap.register_llm_decisions(_HTML_TWO_ROWS, _HOLDINGS, path=lp)
        assert out == {"registered": 0, "ids": []}
        assert dl.fold_ledger(path=lp)["settled_count"] == 0

    def test_only_directional_registered_with_baseline(self, tmp_path):
        # 同表含加仓(600900)与减仓(561910) → 两笔都登记；持有不登记
        html = _HTML_HEADER + (
            "<p>| 🟡 中 | 600900 长江电力 | 加仓 | 分红稳定 |</p>"
            "<p>| 🔴 高 | 561910 招商中证电池主题ETF | 减仓 | 负收益 |</p>"
        )
        lp = str(tmp_path / "ledger.jsonl")
        out = cap.register_llm_decisions(html, _HOLDINGS, path=lp)
        assert out["registered"] == 2
        stats = dl.fold_ledger(path=lp)
        assert stats["pending_count"] == 2
