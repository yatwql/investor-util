"""HTML 报告前端 JS 资产复制/内嵌子模块。

承载 Chart.js 前端静态资产（src/static/）的两条产出路径：
1. `_copy_js_assets`：将资产复制到报告输出目录（松散文件，配合外链引用）；
2. `_inline_js_assets`：将资产内容内嵌进报告 HTML 的行内 <script>（单文件
   完全自包含——下载/移动/单发移动端浏览不再依赖同目录 JS 文件）。

由 `html_writer.py`（聚合门面）re-export 对外提供。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("invest")


def _copy_js_assets(output_dir: str) -> None:
    """将 src/static/ 下 Chart.js 前端 JS 资产复制到报告输出目录（本地 bundle）。

    模板以相对路径引用（chart.min.js / chart-print.js / chart-config.js /
    chart-export.js / chart-common.js / chart-init.js / toc.js / theme.js），
    报告完全离线自包含。文件缺失时仅告警，不阻断报告生成（防御性）。

    Args:
        output_dir: 报告输出目录（与 HTML 同目录）
    """
    import shutil

    from src.python.core.constants import PROJECT_ROOT

    _JS_ASSETS = (
        "chart.min.js",
        "chart-print.js",
        "chart-config.js",
        "chart-export.js",
        "chart-common.js",
        "chart-init.js",
        "toc.js",
        "theme.js",
    )
    src_dir = os.path.join(PROJECT_ROOT, "src", "static")
    os.makedirs(output_dir, exist_ok=True)
    for fname in _JS_ASSETS:
        src = os.path.join(src_dir, fname)
        if not os.path.exists(src):
            logger.warning("[chart] JS 资产缺失（跳过复制）: %s", src)
            continue
        try:
            shutil.copy2(src, os.path.join(output_dir, fname))
        except OSError as e:
            logger.warning("[chart] JS 资产复制失败: %s", e)


def _inline_js_assets(html: str) -> str:
    """将报告 HTML 的 Chart.js 外链脚本内嵌为行内 <script>（单文件自包含）。

    读取 src/static/ 下本地 bundle 各 JS 文件内容，把模板产出的
    ``<script defer src="X.js"></script>``（位于 <head>）移除，并按原顺序
    作为行内 ``<script>`` 追加到 ``</body>`` 前——复刻 defer 外链的执行
    时序（DOM 解析完后、DOMContentLoaded 事件前按序执行），保证：
    - chart-init.js 等立即执行型脚本能取到已解析的 canvas/chart-data；
    - toc.js/theme.js/whatif 初始化等内部注册 DOMContentLoaded 的脚本
      仍能正常触发（事件尚未派发）。

    使报告 HTML 完全自包含——下载/移动到其他目录/单发移动端浏览时，
    不再依赖同目录的松散 JS 文件即可渲染图表。

    防御性：文件缺失、读取失败或内容含 ``</script`` 序列时，跳过该资产
    （其外链标签保留原位，配合 ``_copy_js_assets`` 复制的松散文件仍可
    加载），不阻断报告生成。非本地 bundle 的外链脚本（其他 .js）保持原样。
    已内嵌的 HTML 再次调用时无匹配标签，幂等。

    Args:
        html: 渲染完成的报告 HTML 字符串

    Returns:
        内嵌后的 HTML 字符串（无匹配资产时原样返回）
    """
    import re

    from src.python.core.constants import PROJECT_ROOT

    _JS_ASSETS = (
        "chart.min.js",
        "chart-print.js",
        "chart-config.js",
        "chart-export.js",
        "chart-common.js",
        "chart-init.js",
        "toc.js",
        "theme.js",
    )
    src_dir = os.path.join(PROJECT_ROOT, "src", "static")
    # 资产名 → 内容（跳过缺失/读取失败/含 </script 序列者，保留其外链）
    content_by_name: dict[str, str] = {}
    for fname in _JS_ASSETS:
        src = os.path.join(src_dir, fname)
        if not os.path.exists(src):
            logger.warning("[chart] JS 资产缺失（跳过内嵌，保留外链）: %s", src)
            continue
        try:
            with open(src, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            logger.warning("[chart] JS 资产读取失败（跳过内嵌，保留外链）: %s", e)
            continue
        # 行内脚本以 </script> 为终结符，资产含该序列会截断脚本体（必须跳过）
        if "</script" in content.lower():
            logger.warning("[chart] JS 资产含 </script> 序列（跳过内嵌，保留外链）: %s", src)
            continue
        content_by_name[fname] = content

    if not content_by_name:
        return html

    # 匹配 bundle 外链标签（可含 defer 等属性；src 值取 basename 比对）
    pattern = re.compile(r'<script\b[^>]*\bsrc="([^"]+\.js)"[^>]*>\s*</script>', re.IGNORECASE)

    def _is_bundle(m: re.Match) -> bool:
        return os.path.basename(m.group(1)) in content_by_name

    # 1) 从原位置移除已内嵌资产的外链标签（非 bundle 的外链脚本保留原位）
    removed = pattern.sub(lambda m: "" if _is_bundle(m) else m.group(0), html)

    # 2) 按 bundle 资产顺序生成行内脚本块
    inline_block = "".join(
        f"<script>{content_by_name[name]}</script>" for name in _JS_ASSETS if name in content_by_name
    )

    # 3) 追加到 </body> 前（复刻 defer 时序；无 </body> 时兜底追加到末尾）
    body_close = removed.rfind("</body>")
    if body_close == -1:
        return removed + inline_block
    return removed[:body_close] + inline_block + removed[body_close:]
