"""精确检测文字色像素是否越出卡片右缘。"""

from PIL import Image
import sys

path = sys.argv[1]
scale = float(sys.argv[2])
card_r = float(sys.argv[3])
y0 = float(sys.argv[4])
y1 = float(sys.argv[5])
margin = float(sys.argv[6])
targets = [(0xE8, 0xF1, 0xFB), (0x9F, 0xB6, 0xD0), (0xF4, 0xBB, 0x24), (0x34, 0xD3, 0x99)]

im = Image.open(path).convert("RGB")
px = im.load()
W, H = im.size
x_start = int(card_r * scale)
x_end = min(W, int((card_r + margin) * scale))
y0p, y1p = int(y0 * scale), min(H, int(y1 * scale))

found = []
for yy in range(y0p, y1p):
    for xx in range(x_start, x_end):
        r, g, b = px[xx, yy]
        for tr, tg, tb in targets:
            if abs(r - tr) <= 20 and abs(g - tg) <= 20 and abs(b - tb) <= 20:
                found.append((xx, yy, (r, g, b)))
                break
if found:
    mx = max(f[0] for f in found)
    print(f"  ✗ 文字越界! 最右 x={mx / scale:.1f}px, 共{len(found)}像素")
else:
    print(f"  ✓ 无文字越出 (右缘 {card_r} 外 {margin}px 干净)")
