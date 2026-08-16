"""像素检查：检测文本是否越出卡片右缘（在副标题行区域找亮色像素）。"""

from PIL import Image
import sys

path = sys.argv[1]  # png 路径
scale = float(sys.argv[2])  # px per svg unit
card_r = float(sys.argv[3])  # 卡片右缘 x (svg units)
row_y0 = float(sys.argv[4])  # 副标题行 y 上界 (svg)
row_y1 = float(sys.argv[5])  # 副标题行 y 下界 (svg)
margin = float(sys.argv[6])  # 检测范围到卡片右缘右扩 (svg)

im = Image.open(path).convert("RGB")
W, H = im.size
px = im.load()

x_start = int(card_r * scale)
x_end = min(W, int((card_r + margin) * scale))
y0 = int(row_y0 * scale)
y1 = min(H, int(row_y1 * scale))

# 找越界亮色像素（文本色 #9fb6d0 / #e8f1fb 亮度较高，背景 #20375a 低）
found = []
for yy in range(y0, y1):
    for xx in range(x_start, x_end):
        r, g, b = px[xx, yy]
        lum = 0.3 * r + 0.6 * g + 0.1 * b
        if lum > 140:  # 文本/亮色
            found.append((xx, yy, (r, g, b)))
if found:
    print(f"  检测到 {len(found)} 个亮色像素越出卡片右缘 {card_r}!")
    # 报告最靠右的越界像素
    mx = max(f[0] for f in found)
    print(f"  最右越界像素 x={mx / scale:.1f}px (svg), 色值 {next(f[2] for f in found if f[0] == mx)}")
else:
    print(f"  卡片右缘 {card_r} 外 {margin}px 范围干净，无越界。")
