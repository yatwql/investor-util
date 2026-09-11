"""实验性功能清单的产物落点文案。

报告是可脱离本机流转的文件：读者既看不到 ``features.json``，也看不到生成时的
控制台横幅，产物必须自述其生成条件。清单取自 ``EXPERIMENTAL_FEATURES`` 注册表
（与 TUI 面板 / Web 面板 / 日志横幅同源），注册表仍是唯一清单来源；本模块只统一
措辞，供 HTML 页脚、Excel 用量页签与 Excel 汇总页脚兜底落点共用，避免同一事实在
三处各写各的而漂移。
"""

from __future__ import annotations

NOTICE_HINT = "实验功能输出质量可能不稳定，结论请自行复核"


def enabled_notice_line() -> str | None:
    """已启用实验性功能清单语句；零开关返回 None（既有输出不变）。

    只列**显示名**，不含内部开关键——读者手上没有配置文件，键名对其无意义。
    """
    from src.python.config.features import enabled_experimental_features

    enabled = enabled_experimental_features()
    if not enabled:
        return None
    names = "、".join(name for _flag, name in enabled)
    return f"⚗ 本报告在 {len(enabled)} 项实验性功能开启下生成：{names}"
