"""轻量 Web 入口 — 浏览器内完成「上传持仓 Excel → 选择报告格式 → 生成 → 预览/下载」。

薄入口层（对齐 cli/、tui/ 组织方式）：只保留 HTTP 通道 + 交互外壳 +
上传/任务/进度差异化逻辑，一切业务委托现有共享层（report/orchestrator、
report/progress、core/reader、config/get_config）。MVP 范围外：多用户/登录、
LLM 配置在线修改、实时日志流（完整日志查看留待产品演进阶段）。
"""

from src.python.web.app import create_app
from src.python.web.server import main

__all__ = ["main", "create_app"]
