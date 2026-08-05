"""HTML 报告前端 JS 资产复制子模块。

自 `html_writer.py` 拆出（超限文件拆分重构），承载 Chart.js 前端静态资产
（src/static/ → 报告输出目录）的复制逻辑，报告完全离线自包含。

被 `html_writer.py`（门面）re-export，保持 `from html_writer import ...` 引用不变。
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
