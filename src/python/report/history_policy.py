"""历史走势获取策略解析 — ``history.fetch_mode`` 单一事实来源。

config.json 的 ``history.fetch_mode``（off / auto / prompt）决定是否获取组合
历史走势（as-if 模拟）：

- ``off``  → False
- ``auto`` → True
- ``prompt`` → 有交互能力（传入 ``ask`` 回调）时询问用户；无交互
  （CLI 未显式传 ``--history``、Web、orchestrator 回退）→ True

orchestrator 的 ``fetch_history=None`` 回退、TUI 询问（注入 ``ask``）共用本函数；
渠道层不得自行解析 fetch_mode（TUI 仅提供交互外壳）。
"""

from __future__ import annotations

from collections.abc import Callable


def resolve_fetch_history(config: dict, ask: Callable[[], bool] | None = None) -> bool:
    """按 ``config.history.fetch_mode`` 解析是否获取历史走势。

    Args:
        config: 配置字典（读取 ``history.fetch_mode``，缺失按 ``auto``）。
        ask: ``prompt`` 模式下的交互回调（TUI 注入 y/N 询问）；None 表示非交互。

    Returns:
        是否获取历史走势数据。
    """
    fetch_mode = ((config.get("history") or {}).get("fetch_mode")) or "auto"
    if fetch_mode == "off":
        return False
    if fetch_mode == "prompt":
        if ask is None:
            return True
        return bool(ask())
    return True
