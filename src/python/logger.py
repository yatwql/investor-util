from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# 日志文件路径：测试期间写入独立文件，避免与运行时日志混淆
# 检测方式（按可靠性降序）：
#   1. INVEST_RUNNING_TESTS 环境变量（test_runner.py 显式设置，xdist worker 继承）
#   2. PYTEST_CURRENT_TEST 环境变量（pytest 自身设置）
#   3. sys.modules 中已加载 pytest（xdist worker 进程，pytest 先于用户代码导入）
#   4. sys.argv[:3] 包含 "pytest"（直接 python -m pytest）
_is_pytest = (
    os.environ.get("INVEST_RUNNING_TESTS") == "1"
    or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    or "pytest" in sys.modules
    or any("pytest" in arg.lower() for arg in sys.argv[:3])
)
_LOG_FILE = "logs/test.log" if _is_pytest else "logs/app.log"

# 日志格式
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

# 日志轮转配置
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 单文件最大 10 MB
_LOG_BACKUP_COUNT = 5               # 保留 5 个备份


def setup_logger(name: str = "invest") -> logging.Logger:
    """
    初始化并返回 logger。

    配置控制台输出和自动轮转文件输出两种 handler，避免重复添加。
    自动创建 logs/ 目录（如果不存在）。
    使用 RotatingFileHandler，单文件超过 10 MB 自动切割，保留 5 份备份。

    Args:
        name: logger 名称，默认 "invest"

    Returns:
        配置好的 logging.Logger 实例
    """
    logger = logging.getLogger(name)

    # 如果已经配置过 handler，直接返回
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 创建日志格式器
    formatter = logging.Formatter(_LOG_FORMAT)

    # ---- 控制台 Handler ----
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ---- 文件 Handler（自动轮转） ----
    log_dir = os.path.dirname(_LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
