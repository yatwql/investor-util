"""HTTP 客户端工厂 — 统一控制 SSL 验证策略。

所有 provider 模块通过 ``make_http_client()`` 创建 httpx.Client，
确保 SSL 验证策略统一管理。

SSL 验证由环境变量 ``SSL_VERIFY`` 控制（默认 ``true``）：
  - ``true`` / ``1`` / ``yes`` → 验证证书（生产环境推荐）
  - ``false`` / ``0`` / ``no`` → 跳过验证（开发/调试环境）

用法::

    from src.python.http_client import make_http_client

    with make_http_client(timeout=30.0) as client:
        resp = client.get(url)
"""

from __future__ import annotations

import os

import httpx


def _should_verify() -> bool:
    """读取环境变量 ``SSL_VERIFY``，返回是否验证 SSL 证书。"""
    val = os.getenv("SSL_VERIFY", "true").strip().lower()
    return val in ("true", "1", "yes")


_SSL_VERIFY = _should_verify()


def make_http_client(**kwargs) -> httpx.Client:
    """创建一个 ``httpx.Client``，自动从环境变量读取 SSL 验证策略。

    Args:
        **kwargs: 传递给 ``httpx.Client`` 的额外参数（如 ``timeout``、
            ``follow_redirects``、``headers`` 等）。

    Returns:
        配置好的 ``httpx.Client`` 实例。
    """
    if "verify" not in kwargs:
        kwargs["verify"] = _SSL_VERIFY
    return httpx.Client(**kwargs)


def make_async_http_client(**kwargs) -> httpx.AsyncClient:
    """创建一个 ``httpx.AsyncClient``，自动从环境变量读取 SSL 验证策略。

    当调用者需要异步 HTTP 请求时使用此工厂方法（如配合 ``asyncio``）。
    用法与 ``make_http_client()`` 一致，返回 AsyncClient 以支持 ``async with`` 上下文。

    Args:
        **kwargs: 传递给 ``httpx.AsyncClient`` 的额外参数。

    Returns:
        配置好的 ``httpx.AsyncClient`` 实例。
    """
    if "verify" not in kwargs:
        kwargs["verify"] = _SSL_VERIFY
    return httpx.AsyncClient(**kwargs)
