"""HTTP 客户端工厂 — 统一控制 SSL 验证策略。

所有 provider 模块通过 ``make_http_client()`` 创建 httpx.Client，
确保 SSL 验证策略统一管理。

SSL 验证由环境变量 ``SSL_VERIFY`` 控制（默认 ``true``）：
  - ``true`` / ``1`` / ``yes`` → 验证证书（生产环境推荐）
  - ``false`` / ``0`` / ``no`` → 跳过验证（开发/调试环境）

用法::

    from src.python.core.http_client import make_http_client

    with make_http_client(timeout=30.0) as client:
        resp = client.get(url)

另提供传输层注入点 ``use_transport_factory``：测试基建（数据源记录-回放）
在此处替换「响应从哪来」，从而**不改动任何 provider** 即可离线回放真实响应体。
见 ``core/cassette.py``。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx


def _should_verify() -> bool:
    """读取环境变量 ``SSL_VERIFY``，返回是否验证 SSL 证书。"""
    val = os.getenv("SSL_VERIFY", "true").strip().lower()
    return val in ("true", "1", "yes")


_SSL_VERIFY = _should_verify()

# 当前生效的传输层工厂；None 表示未安装（走 httpx 默认传输）
_TRANSPORT_FACTORY: Callable[[], httpx.BaseTransport | None] | None = None


@contextmanager
def use_transport_factory(factory: Callable[[], httpx.BaseTransport | None]) -> Iterator[None]:
    """在 ``with`` 块内为 ``make_http_client()`` 安装自定义传输层工厂。

    工厂每次被调用都应返回一个**新的**传输实例：``httpx.Client`` 关闭时会连带
    关闭其传输，若多次调用复用同一实例，前一个客户端退出后后续请求会打到已关闭
    的传输上。

    未安装（或工厂返回 ``None``）时，``make_http_client()`` 的行为与没有本机制
    时完全一致（``transport`` 参数不传 → httpx 默认传输）。

    Args:
        factory: 无参可调用对象，返回 ``httpx.BaseTransport`` 或 ``None``。
    """
    global _TRANSPORT_FACTORY
    previous = _TRANSPORT_FACTORY
    _TRANSPORT_FACTORY = factory
    try:
        yield
    finally:
        _TRANSPORT_FACTORY = previous


def _installed_transport() -> httpx.BaseTransport | None:
    """取当前工厂产出的传输；未安装工厂时返回 ``None``。"""
    if _TRANSPORT_FACTORY is None:
        return None
    return _TRANSPORT_FACTORY()


def make_http_client(**kwargs) -> httpx.Client:
    """创建一个 ``httpx.Client``，自动从环境变量读取 SSL 验证策略。

    若已通过 ``use_transport_factory()`` 安装传输层工厂，则以其产物作为传输
    （显式传入 ``transport`` 时以调用方为准）。

    Args:
        **kwargs: 传递给 ``httpx.Client`` 的额外参数（如 ``timeout``、
            ``follow_redirects``、``headers`` 等）。

    Returns:
        配置好的 ``httpx.Client`` 实例。
    """
    if "verify" not in kwargs:
        kwargs["verify"] = _SSL_VERIFY
    if "transport" not in kwargs:
        transport = _installed_transport()
        if transport is not None:
            kwargs["transport"] = transport
    return httpx.Client(**kwargs)


def make_transport(**kwargs) -> httpx.HTTPTransport:
    """创建一个 ``httpx.HTTPTransport``，沿用与 ``make_http_client`` 相同的 SSL 策略。

    供传输层注入（``use_transport_factory``）复用：需要「真实请求 + 顺带录制」
    的传输在此构造。SSL 验证策略仍是本模块一处集中管理。

    Args:
        **kwargs: 传递给 ``httpx.HTTPTransport`` 的额外参数。

    Returns:
        配置好的 ``httpx.HTTPTransport`` 实例。
    """
    if "verify" not in kwargs:
        kwargs["verify"] = _SSL_VERIFY
    return httpx.HTTPTransport(**kwargs)


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
