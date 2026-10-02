"""探测子模块统一接入点（scripts/probe.py 的分发登记处）。

target 生命周期：
  - `register_targets()` 在模块导入时被调用（本子包导入即登记全量 target）
  - 新 target：新增 `probes/<语义名>.py`，模块级声明 `PROBE_TARGET: str`、
    `build_parser() -> argparse.ArgumentParser`、`run(args) -> int`，
    并加入下方 `_TARGET_MODULES`

各行探测均为**纯只读**（不发写请求/不写缓存/不触碰降级状态文件）。
"""

from __future__ import annotations

import importlib

_MODULES = ("probes.csi", "probes.push2")

_REGISTRY: dict[str, object] = {}


def register_targets() -> None:
    """全量登记 target（幂等：重复调用以最后注册为准）。"""
    _REGISTRY.clear()
    for mod_name in _MODULES:
        module = importlib.import_module(mod_name)
        _REGISTRY[module.PROBE_TARGET] = module


register_targets()


def available_targets() -> set[str]:
    """已登记的 target 名称集合。"""
    return set(_REGISTRY)


def get(name: str):
    """按名称取 target 子模块（probe.py 已做存在性校验）。"""
    return _REGISTRY[name]
