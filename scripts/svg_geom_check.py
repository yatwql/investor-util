"""SVG 几何审查：文本越界 / 文本重叠 / 矩形对齐检查（估算字体宽度）。"""

import xml.etree.ElementTree as ET
import sys, re


def char_w(ch, fs, bold):
    m = 1.06 if bold else 1.0
    if re.match(r"[一-鿿　-〿＀-￯—…]", ch):
        return fs * 1.0 * m  # CJK 全角
    if ch.isupper():
        return fs * 0.66 * m  # 大写拉丁
    if ch.isdigit():
        return fs * 0.56 * m  # 数字
    if ch.islower():
        return fs * 0.55 * m  # 小写拉丁
    if ch == " ":
        return fs * 0.30 * m  # 空格
    if ch in "·-/_·→:：|":
        return fs * 0.50 * m  # 标点
    return fs * 0.6 * m


def text_box(t):
    fs = float(t.get("font-size", 15))
    bold = t.get("font-weight") in ("700", "bold")
    s = t.text or ""
    w = sum(char_w(c, fs, bold) for c in s)
    x = float(t.get("x"))
    anchor = t.get("text-anchor", "start")
    if anchor == "middle":
        x0, x1 = x - w / 2, x + w / 2
    elif anchor == "end":
        x0, x1 = x - w, x
    else:
        x0, x1 = x, x + w
    y = float(t.get("y"))
    y0, y1 = y - fs * 0.95, y + fs * 0.12
    return x0, y0, x1, y1, s, fs


def rect_box(r):
    x, y = float(r.get("x")), float(r.get("y"))
    w, h = float(r.get("width")), float(r.get("height"))
    return x, y, x + w, y + h


def parse(path):
    root = ET.parse(path).getroot()
    texts, rects = [], []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "text":
            tb = text_box(el)
            if tb[4]:  # non-empty
                texts.append((tag, tb))
        elif tag == "rect":
            try:
                rects.append((tag, rect_box(el), el.get("fill")))
            except (TypeError, ValueError):
                pass
    return texts, rects


def parent_rect(tb, rects):
    """按 y 范围取最小的包含矩形（背景/装饰性除外）。"""
    best = None
    for tag, (rx0, ry0, rx1, ry1), fill in rects:
        tx0, ty0, tx1, ty1 = tb[0], tb[1], tb[2], tb[3]
        # 要求矩形 y 范围完全包含文本 y 范围，且 x 有交集
        if ry0 <= ty0 and ty1 <= ry1 and tx0 < rx1 and tx1 > rx0:
            area = (rx1 - rx0) * (ry1 - ry0)
            if best is None or area < best[0]:
                best = (area, (rx0, ry0, rx1, ry1), fill)
    return best


def main(paths):
    for path in paths:
        texts, rects = parse(path)
        issues = []
        print(f"\n===== {path} =====")
        for tag, tb in texts:
            x0, y0, x1, y1, s, fs = tb
            p = parent_rect(tb, rects)
            if p:
                pr = p[1]
                pad_l = x0 - pr[0]
                pad_r = pr[2] - x1
                flag = ""
                if pad_l < 0 or pad_r < 0:
                    flag = f"  <-- 越界! 左余量 {pad_l:+.0f}px 右余量 {pad_r:+.0f}px"
                elif min(pad_l, pad_r) < 6:
                    flag = f"  <-- 贴边! 左余量 {pad_l:.0f}px 右余量 {pad_r:.0f}px"
                if flag:
                    issues.append(f"  [{s}] fs={fs} 容器({pr[0]:.0f},{pr[2]:.0f}) 文本({x0:.0f},{x1:.0f}){flag}")
            else:
                # 无父容器（标题等）只报越出画布
                if x0 < 0 or x1 > 1000 or y0 < 0 or y1 > 1000:
                    issues.append(f"  [{s}] fs={fs} 无容器但越出画布 ({x0:.0f},{x1:.0f})")
        # 文本互相重叠（同区域且非父子文本行）
        overlap = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                a, b = texts[i][1], texts[j][1]
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox > 1 and oy > 1:
                    # 排除同一行的紧凑排版（emoji+标题 间距>2 正常）
                    if ox > 2:
                        overlap.append(f"  [{a[4]}] ∩ [{b[4]}] 重叠 {ox:.0f}x{oy:.0f}px")
        # 矩形底部对齐：x 范围重叠的矩形，底部应一致
        cols = {}
        for tag, (rx0, ry0, rx1, ry1), fill in rects:
            for k in range(len(rects)):
                pass
        print("  越界/贴边问题:")
        print("\n".join(issues) if issues else "  无")
        print("  文本重叠:")
        print("\n".join(overlap) if overlap else "  无")
        # 矩形底部对齐检查
        print("  矩形底部分布(同 x 列):")
        bycol = {}
        for tag, (rx0, ry0, rx1, ry1), fill in rects:
            key = round(rx0 / 10) * 10
            bycol.setdefault(key, []).append((round(ry1), round(ry0), round(rx0), round(rx1), fill))
        for k in sorted(bycol):
            bottoms = sorted(set(b[0] for b in bycol[k]))
            if len(bottoms) > 1:
                print(f"    x~{k}: 底部 {bottoms}  <- 不一致!")


if __name__ == "__main__":
    main(sys.argv[1:])
