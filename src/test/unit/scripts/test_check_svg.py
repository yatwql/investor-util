"""check-svg.py 几何审查测试（字符宽度估算 / 元素包围盒 / 容器归属 / 越界·贴边·重叠判定）。

覆盖 `geom` 子命令的纯标准库路径：坏元素跳过不中断、越界/贴边/无容器越画布/文本重叠
四类 finding、同列底部提示不计入退出码，以及 `geom` 子命令的退出码契约。
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.unit_scripts, pytest.mark.usefixtures("offline_external_sources")]

SVG_NS = 'xmlns="http://www.w3.org/2000/svg" width="1000" height="600"'


@pytest.fixture(name="mod")
def fixture_mod():
    """加载 `scripts/check-svg.py` 为可测模块。"""
    from src.test._script_loader import load_script

    return load_script("check-svg.py")


def _svg(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(f"<svg {SVG_NS}>{body}</svg>", encoding="utf-8")
    return path


# ── 字符宽度估算 ──


class TestCharWidth:
    """按字符类别的宽度档位（CJK / 大写 / 数字 / 小写 / 空格 / 连接符 / 兜底）。"""

    @pytest.mark.parametrize(
        ("ch", "expected"),
        [
            ("中", 10.0),  # CJK 全角
            ("A", 6.6),  # 大写
            ("1", 5.6),  # 数字
            ("a", 5.5),  # 小写
            (" ", 3.0),  # 空格
            ("-", 5.0),  # 连接符族
            ("!", 6.0),  # 兜底标点
        ],
    )
    def test_width_by_char_class(self, mod, ch, expected):
        assert mod._char_w(ch, 10.0, False) == pytest.approx(expected)

    def test_bold_scales_every_class(self, mod):
        assert mod._char_w("A", 10.0, True) == pytest.approx(6.6 * 1.06)


# ── 元素包围盒 ──


class TestElementBoxes:
    """`_text_box` / `_rect_box` 的几何展开。"""

    @pytest.mark.parametrize(
        ("extra", "expected_x0"),
        [
            ('x="100"', 100.0),
            ('x="100" text-anchor="middle"', 94.5),
            ('x="100" text-anchor="end"', 89.0),
        ],
    )
    def test_text_box_expands_by_anchor(self, mod, extra, expected_x0):
        el = ET.fromstring(f'<text {extra} y="50" font-size="10">ab</text>')
        x0, y0, x1, y1, content, fs = mod._text_box(el)
        assert (x0, x1) == pytest.approx((expected_x0, expected_x0 + 11.0))
        assert (y0, y1) == pytest.approx((40.5, 51.2))
        assert (content, fs) == ("ab", 10.0)

    def test_text_box_defaults_font_size(self, mod):
        el = ET.fromstring('<text x="0" y="0">hi</text>')
        _x0, y0, _x1, y1, _content, fs = mod._text_box(el)
        assert fs == 15.0
        assert y0 == pytest.approx(-15.0 * 0.95)

    def test_rect_box(self, mod):
        el = ET.fromstring('<rect x="10" y="20" width="30" height="40"/>')
        assert mod._rect_box(el) == (10.0, 20.0, 40.0, 60.0)


# ── 解析与容器归属 ──


class TestParseAndParent:
    """`_parse_svg` 的坏元素跳过，`_parent_rect` 的最小面积容器归属。"""

    @pytest.mark.parametrize(
        "text_el",
        [
            '<text y="50" font-size="12">缺 x</text>',
            '<text x="10" font-size="12">缺 y</text>',
            '<text x="abc" y="10" font-size="12">x 非数值</text>',
        ],
        ids=["no-x", "no-y", "bad-x"],
    )
    def test_malformed_text_is_skipped_not_crash(self, mod, tmp_path, text_el):
        """缺数值属性的 <text> 与 rect 同口径跳过，单个坏元素不中断整轮审查。"""
        path = _svg(tmp_path, "malformed.svg", text_el + '<rect x="0" y="0" width="10" height="10"/>')
        texts, rects = mod._parse_svg(path)
        assert texts == []
        assert len(rects) == 1

    def test_empty_text_content_not_collected(self, mod, tmp_path):
        path = _svg(tmp_path, "empty.svg", '<text x="10" y="10" font-size="12"></text>')
        texts, _rects = mod._parse_svg(path)
        assert texts == []

    def test_parent_rect_prefers_smallest_containing(self, mod):
        rects = [
            ("rect", (0.0, 0.0, 1000.0, 600.0), "#fff"),
            ("rect", (0.0, 0.0, 200.0, 100.0), "#eee"),
        ]
        box = (10.0, 10.0, 110.0, 30.0, "x", 10.0)
        area, picked, fill = mod._parent_rect(box, rects)
        assert area == pytest.approx(200.0 * 100.0)
        assert picked == (0.0, 0.0, 200.0, 100.0)
        assert fill == "#eee"

    def test_parent_rect_requires_horizontal_overlap(self, mod):
        rects = [("rect", (0.0, 0.0, 200.0, 100.0), "#eee")]
        box = (500.0, 10.0, 600.0, 30.0, "x", 10.0)
        assert mod._parent_rect(box, rects) is None

    def test_parent_rect_none_when_nothing_contains(self, mod):
        rects = [("rect", (0.0, 0.0, 100.0, 100.0), "#eee")]
        box = (500.0, 500.0, 600.0, 560.0, "x", 10.0)
        assert mod._parent_rect(box, rects) is None


# ── 几何 findings ──


class TestGeomFindings:
    """四类几何 finding 与干净路径。"""

    def test_text_overflow_reported(self, mod, tmp_path):
        path = _svg(
            tmp_path,
            "overflow.svg",
            '<rect x="0" y="0" width="100" height="100" fill="#eee"/><text x="95" y="50" font-size="20">AAAAAA</text>',
        )
        findings = mod.geom_findings(path)
        assert len(findings) == 1
        assert "文本越界" in findings[0]

    def test_text_padding_warn_reported(self, mod, tmp_path):
        path = _svg(
            tmp_path,
            "padding.svg",
            '<rect x="0" y="0" width="200" height="100" fill="#eee"/><text x="3" y="50" font-size="10">hi</text>',
        )
        findings = mod.geom_findings(path)
        assert len(findings) == 1
        assert "文本贴边" in findings[0]

    def test_clean_layout_has_no_findings(self, mod, tmp_path):
        path = _svg(
            tmp_path,
            "clean.svg",
            '<rect x="0" y="0" width="1000" height="200" fill="#eee"/><text x="100" y="100" font-size="14">OK</text>',
        )
        assert mod.geom_findings(path) == []

    def test_overlapping_texts_reported_once(self, mod, tmp_path):
        path = _svg(
            tmp_path,
            "overlap.svg",
            '<rect x="0" y="0" width="1000" height="200" fill="#eee"/>'
            '<text x="50" y="50" font-size="12">AAAAAAAA</text>'
            '<text x="60" y="56" font-size="12">AAAAAAAA</text>',
        )
        findings = mod.geom_findings(path)
        assert len(findings) == 1
        assert "文本重叠" in findings[0]

    def test_containerless_text_outside_canvas_reported(self, mod, tmp_path):
        path = _svg(tmp_path, "canvas.svg", '<text x="990" y="30" font-size="20">AAAA</text>')
        findings = mod.geom_findings(path)
        assert len(findings) == 1
        assert "无容器文本越出画布" in findings[0]


class TestGeomNotes:
    """同列底部齐平只作提示，不进入退出码。"""

    def test_misaligned_bottoms_noted(self, mod, tmp_path):
        path = _svg(
            tmp_path,
            "misaligned.svg",
            '<rect x="100" y="0" width="50" height="50" fill="#a"/>'
            '<rect x="104" y="0" width="60" height="80" fill="#b"/>',
        )
        notes = mod.geom_notes(path)
        assert len(notes) == 1
        assert "同列" in notes[0]

    def test_aligned_bottoms_produce_no_note(self, mod, tmp_path):
        path = _svg(
            tmp_path,
            "aligned.svg",
            '<rect x="100" y="0" width="50" height="50" fill="#a"/>'
            '<rect x="104" y="0" width="60" height="50" fill="#b"/>',
        )
        assert mod.geom_notes(path) == []


# ── geom 子命令退出码契约 ──


class TestGeomExitCode:
    """`check-svg.py geom` 通过 0 / 发现 2。"""

    def test_exit_0_when_clean(self, mod, monkeypatch, tmp_path):
        path = _svg(
            tmp_path,
            "ok.svg",
            '<rect x="0" y="0" width="1000" height="200" fill="#eee"/><text x="100" y="100" font-size="14">OK</text>',
        )
        monkeypatch.setattr(sys, "argv", ["check-svg.py", "--ci", "geom", str(path)])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert int(exc.value.code) == 0

    def test_exit_2_when_finding(self, mod, monkeypatch, tmp_path):
        path = _svg(tmp_path, "bad.svg", '<text x="990" y="30" font-size="20">AAAA</text>')
        monkeypatch.setattr(sys, "argv", ["check-svg.py", "--ci", "geom", str(path)])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert int(exc.value.code) == 2

    def test_exit_2_when_file_missing(self, mod, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv", ["check-svg.py", "--ci", "geom", str(tmp_path / "absent.svg")])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert int(exc.value.code) == 2
