from __future__ import annotations

import logging
import os

# 日志文件路径
_LOG_FILE = "logs/app.log"

# 日志格式
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def setup_logger(name: str = "invest") -> logging.Logger:
    """
    初始化并返回 logger。

    配置控制台输出和文件输出两种 handler，避免重复添加。
    自动创建 logs/ 目录（如果不存在）。

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

    # ---- 文件 Handler ----
    log_dir = os.path.dirname(_LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
