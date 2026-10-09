"""报告空状态与降级呈现契约（DESIGN.md Data States 节，三档空态族 + 二元文案口径）。

验收边界：
  - 三档空态族类名即契约（章节 empty-section / 单元 empty-note / 图表 chart-empty-note），
    原 placeholder-note 同义类归并后零残留（注释中的历史说明除外，按 class/选择器形态提取）
  - 文案二元口径：合法空「暂无 + 具体对象」、降级空「数据不可用：<原因>」——
    与 data_freshness 降级原因词根同源；豁免表见 DESIGN.md Data States 节
  - 状态 → 观感映射由 data-status 组件承载，空态族保持中性
  - HTML/Excel 双端同句（summary 指数占位样例）
"""

from __future__ import annotations

import re
import pathlib

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_report]

_ROOT = pathlib.Path(__file__).resolve().parents[4]
_TMPL = _ROOT / "src/static/tmpl"
_REPORT = _TMPL / "report_template.html"
_WHATIF = _TMPL / "whatif_template.html"
_DESIGN = _ROOT / "docs" / "managements" / "DESIGN.md"
_SUMMARY_PY = _ROOT / "src/python/report/summary.py"


def _all_templates() -> list[pathlib.Path]:
    return [_REPORT, _WHATIF, *sorted((_TMPL / "partials").glob("*.html"))]


def _sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _all_templates())


class TestEmptyFamilyTiers:
    """三档空态族：类名契约 + 归并零残留。"""

    def test_three_tier_selectors_defined(self) -> None:
        """主模板三档选择器齐备；What-if 至少单元级（其域无章节/图表级用点）。"""
        css = _REPORT.read_text(encoding="utf-8")
        for sel in (".empty-section", ".empty-note", ".chart-empty-note"):
            assert f"{sel} {{" in css, f"主模板缺空态族选择器 {sel}"
        assert ".empty-note {" in _WHATIF.read_text(encoding="utf-8")

    def test_merged_class_zero_residual(self) -> None:
        """placeholder-note 归并后：class 属性与选择器定义零残留（注释历史说明豁免）。"""
        for path in _all_templates():
            text = path.read_text(encoding="utf-8")
            assert 'placeholder-note"' not in text.replace("empty-note placeholder-note", "X"), path
            assert 'class="empty-note placeholder-note"' not in text, path
        report_css = _REPORT.read_text(encoding="utf-8")
        assert ".placeholder-note {" not in report_css, "选择器定义应已归并"
        assert ".placeholder-note {" not in _WHATIF.read_text(encoding="utf-8")

    def test_empty_note_carries_placeholder_box(self) -> None:
        """单元级基底自带占位框（淡底 + 虚线），视觉一族不依赖修饰类。"""
        for path in (_REPORT, _WHATIF):
            text = path.read_text(encoding="utf-8")
            idx = text.find(".empty-note {")
            assert idx > 0, f"{path.name} 缺 .empty-note 定义"
            body = text[idx : text.find("}", idx)]
            assert "var(--empty-section-bg)" in body, f"{path.name} empty-note 缺淡底"
            assert "dashed" in body, f"{path.name} empty-note 缺虚线框"

    def test_chart_empty_tier_kept(self) -> None:
        """图表级占位保留（chart 位内居中，不渲染空白 canvas 的观感）。"""
        assert _REPORT.read_text(encoding="utf-8").count("chart-empty-note") >= 1


class TestCopyDiction:
    """二元文案口径：合法空「暂无+对象」、降级空「数据不可用：<原因>」。"""

    def test_degraded_sentences_use_colon_prefix(self) -> None:
        """已收敛的降级句（数据源状态行 ×2 + 历史图空态）采用标准前缀。"""
        sources = _sources()
        assert "数据不可用：未获取行情数据，品种覆盖无法判定" in sources
        assert "数据不可用：未获取可信度数据，新鲜度/跳变无法判定" in sources
        assert "数据不可用：未获取持仓市值数据，量化指标暂停计算" in sources

    def test_bare_generic_placeholder_absent(self) -> None:
        """对象不明的「暂无数据」在 HTML 渲染域零残留（豁免域：py 数据哨兵/原因字段）。"""
        for path in _all_templates():
            text = path.read_text(encoding="utf-8")
            # 渲染文本域：剥 HTML 注释后查整词（Jinja 注释 {# #} 同步剥）

            body = re.sub(r"<!--.*?-->|{#.*?#}", "", text, flags=re.S)
            assert "暂无数据" not in body, f"{path.name} 残留多口径占位「暂无数据」"

    def test_index_placeholder_dual_side_consistent(self) -> None:
        """HTML/Excel 双端同句（summary 指数占位样例：暂无指数数据）。"""
        html = (_TMPL / "partials/summary_section.html").read_text(encoding="utf-8")
        py = _SUMMARY_PY.read_text(encoding="utf-8")
        assert "暂无指数数据" in html, "HTML 侧缺标准句"
        assert "暂无指数数据" in py, "Excel 侧缺标准句"


class TestStatusObservation:
    """状态 → 观感映射由 data-status 承载；空态族保持中性。"""

    def test_data_status_has_status_tokens(self) -> None:
        """数据源状态区引用状态语义色（ok/warn/info 三态）。"""
        text = (_TMPL / "partials/data_source_status_section.html").read_text(encoding="utf-8")
        css = _REPORT.read_text(encoding="utf-8")
        assert "data-status" in text and "data-status" in css
        for token in ("--ok", "--warn", "--info"):
            assert f"{token}:" in css, f"主模板缺状态色 token {token}"

    def test_empty_family_stays_neutral(self) -> None:
        """空态族定义不直接染状态色（状态着色只由状态组件承载）。"""
        css = _REPORT.read_text(encoding="utf-8")
        for sel in (".empty-section", ".empty-note", ".chart-empty-note"):
            idx = css.find(f"{sel} {{")
            body = css[idx : css.find("}", idx)]
            for state in ("var(--ok)", "var(--warn)", "var(--error)", "var(--profit)"):
                assert state not in body, f"{sel} 越权使用状态色 {state}"


class TestDesignAlignment:
    """DESIGN.md Data States 节 ↔ 实现同源。"""

    def test_design_section_names_tiers_and_diction(self) -> None:
        text = _DESIGN.read_text(encoding="utf-8")
        sec = text.split("## Data States")[1].split("## Do's and Don")[0] if "## Data States" in text else ""
        assert sec, "DESIGN 缺 Data States 节"
        for tier in ("empty-section", "empty-note", "chart-empty-note"):
            assert f"`{tier}`" in sec, f"DESIGN 状态节缺三档类名 {tier}"
        assert "暂无" in sec and "数据不可用：" in sec, "DESIGN 状态节缺二元口径"
        assert "placeholder-note" in sec, "DESIGN 应记录归并历史（同义类收敛）"

    def test_design_gaps_no_stale_empty_entry(self) -> None:
        """Known Gaps 不再挂空态归并在办条目（任务已完成）。"""
        text = _DESIGN.read_text(encoding="utf-8")
        gaps = text.split("## Known Gaps")[1]
        assert "空态样式族与降级文案口径待归并" not in gaps
