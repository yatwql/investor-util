"""隐私提示模块 — 首次运行提示 + 报告脚注。

提供标准化的隐私声明文本和首次运行检测。
每次生成报告时在 HTML/Excel 中追加脚注。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("invest")

# 隐私声明文本
PRIVACY_NOTICE = (
    "本报告数据仅供本地处理，所有数据保存在当前设备。LLM 请求经由 API 发送到配置的 provider，不会用于训练。"
)

# 首次运行标记的配置键
_FIRST_RUN_KEY = "_privacy_notice_shown"


def get_privacy_notice() -> str:
    """返回标准隐私声明文本。

    Returns:
        隐私声明字符串
    """
    return PRIVACY_NOTICE


def is_first_run() -> bool:
    """检查是否为首次运行（隐私提示未显示过）。

    Returns:
        True 表示首次运行
    """
    try:
        from src.python.config import get_config

        config = get_config()
        return not config.get(_FIRST_RUN_KEY, False)
    except Exception:
        return True


def mark_privacy_notice_shown() -> None:
    """标记隐私提示已显示，避免重复提示。"""
    try:
        from src.python.config import get_config, set_config

        config = get_config()
        if not config.get(_FIRST_RUN_KEY, False):
            set_config(_FIRST_RUN_KEY, True)
            logger.info("[privacy] 首次运行隐私提示已标记为已读")
    except Exception:
        logger.debug("[privacy] 标记隐私提示失败（非关键）", exc_info=True)


def show_privacy_notice_if_needed() -> bool:
    """首次运行时显示隐私提示。已显示过则静默。

    Returns:
        True 表示本次显示了提示
    """
    if not is_first_run():
        return False

    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║           隐私声明 / Privacy Notice          ║")
    print("  ╠══════════════════════════════════════════════╣")
    print(f"  ║ {PRIVACY_NOTICE}")
    print("  ║                                              ║")
    print("  ║ 本提示仅首次运行显示一次。                   ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()

    mark_privacy_notice_shown()
    return True
