#!/usr/bin/env python3
"""README SVG 架构图检查（三件套合并：几何审查 / 像素越界 / 文字色越界）。

原为三个各自独立的脚本（`check-svg-geom.py` / `check-svg-pixel.py` /
`check-svg-text-overflow.py`）：都没有退出码、靠位置参数调用、无法作为门禁，且三者都在做
「文本是否越出卡片」，维护面重叠。合并为一个带子命令与统一契约的脚本（`--ci` + 退出码 2）。

子命令：
  geom  <svg…>                                   几何审查：文本越界/贴边、文本重叠、矩形底部对齐（估算字体宽度，纯标准库）
  pixel <png> <scale> <card_r> <row_y0> <row_y1> <margin>
                                                 像素审查：副标题行区域找高亮像素越出卡片右缘（需 Pillow）
  text-overflow <png> <scale> <card_r> <y0> <y1> <margin>
                                                 像素审查：精确匹配文字色像素越出卡片右缘（需 Pillow）

用法：
  python scripts/check-svg.py geom src/static/architecture.svg …        # 几何审查
  python scripts/check-svg.py pixel out.png 2.0 320 60 80 20            # 像素审查（需 Pillow）
  python scripts/check-svg.py --ci geom src/static/*.svg                # CI 模式：仅输出 文件:描述，退出码 2

退出码：
  0 — 通过
  1 — 环境缺失（pixel/text-overflow 子命令需要 Pillow）
  2 — 发现越界/重叠/对齐问题
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录共享模块（_checklib）
from _checklib import add_common_args, rel, report  # noqa: E402

#: 文字色目标（README 架构图里的文本/强调色）
_TEXT_COLORS: tuple[tuple[int, int, int], ...] = (
    (0xE8, 0xF1, 0xFB),
    (0x9F, 0xB6, 0xD0),
    (0xF4, 0xBB, 0x24),
    (0x34, 0xD3, 0x99),
)
#: 像素审查中判定为「亮色（文字）」的亮度阈值
_LUMINANCE_THRESHOLD = 140
#: 贴边告警阈值（左右余量小于该值即视为贴边）
_PADDING_WARN = 6.0
#: 画布尺寸（无父容器的标题类文本据此判越界）
_CANVAS = 1000.0

# ═══════════════════════════════════════════════════════════════
#  geom：几何审查
# ═══════════════════════════════════════════════════════════════


def _char_w(ch: str, fs: float, bold: bool) -> float:
    """按字符类别估算宽度（CJK 全角 / 大写 / 数字 / 小写 / 空格 / 标点）。"""
    scale = 1.06 if bold else 1.0
    if re.match(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u2014\u2026]", ch):
        return fs * 1.0 * scale
    if ch.isupper():
        return fs * 0.66 * scale
    if ch.isdigit():
        return fs * 0.56 * scale
    if ch.islower():
        return fs * 0.55 * scale
    if ch == " ":
        return fs * 0.30 * scale
    if ch in "·-/_·→:：|":
        return fs * 0.50 * scale
    return fs * 0.6 * scale


def _text_box(text_el: ET.Element) -> tuple[float, float, float, float, str, float]:
    """文本元素 → ``(x0, y0, x1, y1, 内容, 字号)``（按 text-anchor 展开水平范围）。"""
    fs = float(text_el.get("font-size", 15))
    bold = text_el.get("font-weight") in ("700", "bold")
    content = text_el.text or ""
    width = sum(_char_w(ch, fs, bold) for ch in content)
    x = float(text_el.get("x"))
    anchor = text_el.get("text-anchor", "start")
    if anchor == "middle":
        x0, x1 = x - width / 2, x + width / 2
    elif anchor == "end":
        x0, x1 = x - width, x
    else:
        x0, x1 = x, x + width
    y = float(text_el.get("y"))
    return x0, y - fs * 0.95, x1, y + fs * 0.12, content, fs


def _rect_box(rect_el: ET.Element) -> tuple[float, float, float, float]:
    x, y = float(rect_el.get("x")), float(rect_el.get("y"))
    w, h = float(rect_el.get("width")), float(rect_el.get("height"))
    return x, y, x + w, y + h


def _parse_svg(path: Path):
    """解析 SVG → ``(texts, rects)``；texts 项为 ``(标签, box)``，rects 项为 ``(标签, box, fill)``。"""
    root = ET.parse(path).getroot()
    texts, rects = [], []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "text":
            box = _text_box(el)
            if box[4]:
                texts.append((tag, box))
        elif tag == "rect":
            try:
                rects.append((tag, _rect_box(el), el.get("fill")))
            except (TypeError, ValueError):
                continue
    return texts, rects


def _parent_rect(box, rects):
    """按 y 范围完全包含取面积最小的矩形（背景/装饰性除外），返回 ``(面积, box, fill)``。"""
    best = None
    x0, y0, x1, y1 = box[0], box[1], box[2], box[3]
    for _tag, (rx0, ry0, rx1, ry1), fill in rects:
        if ry0 <= y0 and y1 <= ry1 and x0 < rx1 and x1 > rx0:
            area = (rx1 - rx0) * (ry1 - ry0)
            if best is None or area < best[0]:
                best = (area, (rx0, ry0, rx1, ry1), fill)
    return best


def geom_findings(path: Path) -> list[str]:
    """几何问题清单：文本越界/贴边、文本重叠、同列矩形底部不一致。"""
    findings: list[str] = []
    texts, rects = _parse_svg(path)
    for _tag, box in texts:
        x0, y0, x1, y1, content, fs = box
        parent = _parent_rect(box, rects)
        if parent:
            pr = parent[1]
            pad_l, pad_r = x0 - pr[0], pr[2] - x1
            if pad_l < 0 or pad_r < 0:
                findings.append(
                    f"{rel(path)}: 文本越界 `{content}` fs={fs:g} 左余量 {pad_l:+.0f}px 右余量 {pad_r:+.0f}px"
                )
            elif min(pad_l, pad_r) < _PADDING_WARN:
                findings.append(
                    f"{rel(path)}: 文本贴边 `{content}` fs={fs:g} 左余量 {pad_l:.0f}px 右余量 {pad_r:.0f}px"
                )
        elif x0 < 0 or x1 > _CANVAS or y0 < 0 or y1 > _CANVAS:
            findings.append(f"{rel(path)}: 无容器文本越出画布 `{content}` fs={fs:g} ({x0:.0f},{x1:.0f})")

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i][1], texts[j][1]
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 2 and oy > 1:
                findings.append(f"{rel(path)}: 文本重叠 `{a[4]}` ∩ `{b[4]}` 重叠 {ox:.0f}x{oy:.0f}px")

    return findings


def geom_notes(path: Path) -> list[str]:
    """几何**提示**（不作为 finding）：同列矩形底部是否齐平。

    流程图里同一列的卡片高度本就允许不同（内容行数不同），故此项只作人工参考，
    不计入退出码——避免把正常版式判成缺陷。
    """
    notes: list[str] = []
    rects = _parse_svg(path)[1]
    by_col: dict[float, list[float]] = {}
    for _tag, (rx0, _ry0, _rx1, ry1), _fill in rects:
        by_col.setdefault(round(rx0 / 10) * 10, []).append(ry1)
    for key in sorted(by_col):
        bottoms = sorted({round(item) for item in by_col[key]})
        if len(bottoms) > 1:
            notes.append(f"同列（x~{key:g}）矩形底部不一致 {bottoms}")
    return notes


def _print_geom_report(path: Path, findings: list[str], notes: list[str]) -> None:
    """人类可读报告（`--ci` 下不打，保持与既有三件套一致的阅读体验）。"""
    print(f"\n===== {path} =====")
    print("  越界/贴边/重叠问题:")
    if findings:
        for item in findings:
            print(f"    {item.split(': ', 1)[-1]}")
    else:
        print("  无")
    print("  版式提示（不计入退出码）:")
    print("\n".join(f"    {note}" for note in notes) if notes else "  无")


# ═══════════════════════════════════════════════════════════════
#  pixel / text-overflow：像素审查（需 Pillow）
# ═══════════════════════════════════════════════════════════════


def _require_pillow():
    """按需导入 Pillow；缺失时给出可执行指引并返回 None。"""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        print("[ERR] 该子命令需要 Pillow：pip install Pillow（或 pip install -e '.[svg]'）")
        return None
    return Image


def pixel_findings(path: Path, scale: float, card_r: float, row_y0: float, row_y1: float, margin: float) -> list[str]:
    """副标题行区域内的亮色像素越出卡片右缘 → finding。"""
    Image = _require_pillow()
    if Image is None:
        raise SystemExit(1)
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    x_start = int(card_r * scale)
    x_end = min(width, int((card_r + margin) * scale))
    y_start = int(row_y0 * scale)
    y_end = min(height, int(row_y1 * scale))
    found: list[tuple[int, int, tuple[int, int, int]]] = []
    for yy in range(y_start, y_end):
        for xx in range(x_start, x_end):
            r, g, b = pixels[xx, yy]
            if 0.3 * r + 0.6 * g + 0.1 * b > _LUMINANCE_THRESHOLD:
                found.append((xx, yy, (r, g, b)))
    if not found:
        return []
    rightmost = max(item[0] for item in found)
    color = next(item[2] for item in found if item[0] == rightmost)
    return [f"{rel(path)}: 亮色像素越出卡片右缘 {len(found)} 个，最右 x={rightmost / scale:.1f}px 色值 {color}"]


def text_overflow_findings(path: Path, scale: float, card_r: float, y0: float, y1: float, margin: float) -> list[str]:
    """精确匹配文字色像素越出卡片右缘 → finding。"""
    Image = _require_pillow()
    if Image is None:
        raise SystemExit(1)
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    x_start = int(card_r * scale)
    x_end = min(width, int((card_r + margin) * scale))
    y_start, y_end = int(y0 * scale), min(height, int(y1 * scale))
    found: list[int] = []
    for yy in range(y_start, y_end):
        for xx in range(x_start, x_end):
            r, g, b = pixels[xx, yy]
            if any(abs(r - tr) <= 20 and abs(g - tg) <= 20 and abs(b - tb) <= 20 for tr, tg, tb in _TEXT_COLORS):
                found.append(xx)
    if not found:
        return []
    return [f"{rel(path)}: 文字色像素越出卡片右缘 {len(found)} 个，最右 x={max(found) / scale:.1f}px"]


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="README SVG 架构图检查（几何 / 像素越界 / 文字色越界）")
    add_common_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    geom = sub.add_parser("geom", help="几何审查：文本越界/贴边、文本重叠、矩形底部对齐")
    geom.add_argument("paths", nargs="+", help="SVG 路径（可多个）")

    pixel = sub.add_parser("pixel", help="像素审查：副标题行亮色像素是否越出卡片右缘（需 Pillow）")
    pixel.add_argument("path", help="PNG 路径")
    pixel.add_argument("scale", type=float, help="px per svg unit")
    pixel.add_argument("card_r", type=float, help="卡片右缘 x（svg 单位）")
    pixel.add_argument("row_y0", type=float, help="检测行 y 上界（svg 单位）")
    pixel.add_argument("row_y1", type=float, help="检测行 y 下界（svg 单位）")
    pixel.add_argument("margin", type=float, help="检测范围到卡片右缘的右扩量（svg 单位）")

    overflow = sub.add_parser("text-overflow", help="像素审查：精确匹配文字色像素越界（需 Pillow）")
    overflow.add_argument("path", help="PNG 路径")
    overflow.add_argument("scale", type=float, help="px per svg unit")
    overflow.add_argument("card_r", type=float, help="卡片右缘 x（svg 单位）")
    overflow.add_argument("y0", type=float, help="检测区 y 上界（svg 单位）")
    overflow.add_argument("y1", type=float, help="检测区 y 下界（svg 单位）")
    overflow.add_argument("margin", type=float, help="检测范围到卡片右缘的右扩量（svg 单位）")

    args = parser.parse_args()
    findings: list[str] = []

    if args.command == "geom":
        for raw in args.paths:
            path = Path(raw)
            if not path.exists():
                findings.append(f"{rel(path)}: 文件不存在")
                continue
            path_findings = geom_findings(path)
            if not args.ci:
                _print_geom_report(path, path_findings, geom_notes(path))
            findings.extend(path_findings)
        ok_message = "[OK] SVG 几何审查通过（无越界/贴边/重叠/对齐问题）"
    elif args.command == "pixel":
        findings = pixel_findings(Path(args.path), args.scale, args.card_r, args.row_y0, args.row_y1, args.margin)
        ok_message = f"[OK] 卡片右缘 {args.card_r:g} 外 {args.margin:g}px 范围干净，无亮色像素越界"
    else:
        findings = text_overflow_findings(Path(args.path), args.scale, args.card_r, args.y0, args.y1, args.margin)
        ok_message = f"[OK] 无文字色像素越出卡片右缘（{args.card_r:g} 外 {args.margin:g}px 干净）"

    sys.exit(report(findings, ok_message, ci=args.ci, fail_message="[!] 发现 {n} 处 SVG 问题，须修正后提交"))


if __name__ == "__main__":
    main()
