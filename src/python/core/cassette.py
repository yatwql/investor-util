"""数据源记录-回放 — 真实响应体的离线回归引擎（语义名 datasource_cassette）。

测试基建，**不产生任何运行时行为分支**：cassette 只在测试进程与维护命令
（``cassettes``）中被读写，报告管线不读取它，因此本模块不进实验开关注册表
（详见 docs-stm/plan/datasource-cassette-replay-design.md「为何不设开关」）。

解决的问题：既有数据源测试全部用**手工构造的假响应**，那是「我以为上游长什么
样」；真实响应体格式与解析器假设不一致（字段改名、加前后缀、换分隔符、返回
HTML 错误页）这类回归测不出来。本引擎把**真实响应体**录进仓库，此后离线回放：
既有真实数据，又不碰网络，且随默认套件入门禁。

分层约束  — 本模块属 core 层，只依赖 stdlib + httpx + ``core.http_client``，
            禁止 import providers/fetcher/report/llm
注入点    — 经 ``core.http_client.use_transport_factory`` 替换「响应从哪来」，
            全项目 provider 零改动（HTTP 客户端统一约束下的唯一构造点）
离线保证  — 回放未命中抛 ``CassetteMissError``，**绝不回落真实网络**，
            避免「以为在回放、实则在联网」的隐性依赖
录制保证  — 需 ``--run-live`` 与 ``--record-cassettes`` 双开关；非 live 用例的
            真实请求已被 conftest 阻断，机制上不可能产出录制内容
原子写入  — 会话结束时一次写盘（``tempfile.mkstemp`` + ``os.replace``）
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from src.python.core.constants import PROJECT_ROOT
from src.python.core.http_client import make_transport, use_transport_factory

logger = logging.getLogger("invest")

# ── 存取格式 ────────────────────────────────────────────
_CASSETTE_VERSION = 1

# 录制目标目录（module-level，测试可 monkeypatch 重定向到 tmp）
CASSETTE_DIR = os.path.join(PROJECT_ROOT, "src", "test", "data", "cassettes")

# 易变查询参数：每次请求都可能不同、与响应内容无关。归一请求键时剥离，否则同一
# 响应每录一次就是一条新交互，回放也匹配不上。取值来自本仓库实际用法：
#   rt        — tiantian_base 的 random.random() 防缓存参数
#   req_trace — eastmoney_news 的毫秒时间戳
#   _/callback/reqid — JSONP 与防缓存惯用名（上游换命名不影响匹配）
VOLATILE_QUERY_PARAMS = frozenset({"_", "callback", "reqid", "req_trace", "rt"})

# 回放时须丢弃的响应头：录制存的是**已解压**的响应体文本，若把这些传输层头原样
# 带回，httpx 会按 content-encoding 再解一次（zlib.error）或按旧的 content-length
# 截断。存储仍保真保留，仅在构造回放响应时丢弃（归一规则集中于此，便于核对）。
_REPLAY_DROPPED_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})


# ── 异常 ────────────────────────────────────────────────


class CassetteError(RuntimeError):
    """cassette 缺失 / 无法读取 / 版本不符 / 结构非法。"""


class CassetteMissError(CassetteError):
    """回放未命中：请求键在已加载 cassette 中无对应交互。

    刻意不继承 ``httpx.HTTPError``：provider 的异常处理会捕获 httpx 错误并
    降级到下一个源，那会让「回放漏录」静默变成「换个源重试」，进而掩盖问题。
    """

    def __init__(self, key: str, recorded_keys: Sequence[str]) -> None:
        self.key = key
        self.recorded_keys = tuple(recorded_keys)
        listed = "\n".join(f"    - {k}" for k in self.recorded_keys) or "    （空：cassette 未录制任何交互）"
        super().__init__(
            f"回放未命中：请求 {key} 不在已加载 cassette 中。\n"
            f"  已录制请求键：\n{listed}\n"
            f"  若上游确实新增了请求，请重新录制该 cassette"
            f"（pytest -m live --run-live --record-cassettes）；"
            f"本引擎不回落真实网络。"
        )


# ── 请求键归一 ──────────────────────────────────────────


def normalize_request_key(method: str, url: str) -> str:
    """把 (方法, URL) 归一为 cassette 匹配键。

    剥离易变查询参数（``VOLATILE_QUERY_PARAMS``）、丢弃 fragment、查询参数排序，
    使「同一响应的不同次请求」归一到同一键。
    """
    parts = urlsplit(url)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in VOLATILE_QUERY_PARAMS)
    normalized = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    return f"{method.upper()} {normalized}"


# ── 数据模型 ────────────────────────────────────────────


@dataclass(frozen=True)
class Interaction:
    """一次「请求 → 响应」的录制。"""

    method: str
    url: str
    status: int
    headers: dict[str, str]
    body: str
    encoding: str

    @property
    def key(self) -> str:
        return normalize_request_key(self.method, self.url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": {"method": self.method, "url": self.url},
            "response": {
                "status": self.status,
                "headers": self.headers,
                "body": self.body,
                "encoding": self.encoding,
            },
        }

    @classmethod
    def from_dict(cls, data: Any, *, origin: str) -> Interaction:
        if not isinstance(data, dict):
            raise CassetteError(f"cassette 交互项不是对象: {origin}")
        request = data.get("request")
        response = data.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise CassetteError(f"cassette 交互项缺少 request/response: {origin}")
        method = request.get("method")
        url = request.get("url")
        status = response.get("status")
        if not isinstance(method, str) or not isinstance(url, str) or not isinstance(status, int):
            raise CassetteError(f"cassette 交互项缺少 method/url/status: {origin}")
        headers = response.get("headers")
        return cls(
            method=method,
            url=url,
            status=status,
            headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else {},
            body=response.get("body") if isinstance(response.get("body"), str) else "",
            encoding=response.get("encoding") if isinstance(response.get("encoding"), str) else "utf-8",
        )


@dataclass
class Cassette:
    """一份 cassette：同一数据源的一组录制交互。

    重复请求键按**后写覆盖先写**处理（录制时原地替换，读取时取最后一条）：
    同一 URL 在一次会话中被请求两次，只保留最后一次的真实响应。
    """

    name: str
    source: str = ""
    recorded_at: str = ""
    interactions: list[Interaction] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return [interaction.key for interaction in self.interactions]

    def lookup(self, key: str) -> Interaction | None:
        """按键取交互；重复键取最后一条（后写覆盖先写）。"""
        found: Interaction | None = None
        for interaction in self.interactions:
            if interaction.key == key:
                found = interaction
        return found

    def record(self, interaction: Interaction) -> None:
        """写入交互；同键已存在则原地替换（避免重复录制堆积同一条）。"""
        key = interaction.key
        for index, existing in enumerate(self.interactions):
            if existing.key == key:
                self.interactions[index] = interaction
                return
        self.interactions.append(interaction)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": _CASSETTE_VERSION,
            "name": self.name,
            "source": self.source,
            "recorded_at": self.recorded_at,
            "interactions": [interaction.to_dict() for interaction in self.interactions],
        }

    @classmethod
    def from_dict(cls, data: Any, *, origin: str) -> Cassette:
        if not isinstance(data, dict):
            raise CassetteError(f"cassette 顶层不是对象: {origin}")
        version = data.get("version")
        # 版本号是格式标记，须严格为整数：JSON 里写成 1.0 / true 都会被 Python
        # 判为「等于 1」，放行即等于把畸形文件的解析权交给巧合的类型相等。
        if isinstance(version, bool) or not isinstance(version, int) or version != _CASSETTE_VERSION:
            raise CassetteError(
                f"cassette 版本不受支持: {origin}（文件 version={version!r}，当前支持 {_CASSETTE_VERSION}）"
            )
        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise CassetteError(f"cassette 缺少 name: {origin}")
        raw_items = data.get("interactions")
        if not isinstance(raw_items, list):
            raise CassetteError(f"cassette 缺少 interactions 列表: {origin}")
        return cls(
            name=name,
            source=data.get("source") if isinstance(data.get("source"), str) else "",
            recorded_at=data.get("recorded_at") if isinstance(data.get("recorded_at"), str) else "",
            interactions=[Interaction.from_dict(item, origin=origin) for item in raw_items],
        )


# ── 读写 ────────────────────────────────────────────────


def cassette_path(name: str, directory: str | None = None) -> str:
    """cassette 文件绝对路径（目录以 ``PROJECT_ROOT`` 为基准解析）。"""
    return os.path.join(directory or CASSETTE_DIR, f"{name}.json")


def load_cassette(name: str, directory: str | None = None) -> Cassette:
    """读取 cassette；缺失或损坏抛 ``CassetteError``（含可读原因）。"""
    path = cassette_path(name, directory)
    if not os.path.isfile(path):
        raise CassetteError(f"cassette 不存在: {path}")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as err:
        raise CassetteError(f"cassette 无法读取: {path}（{err}）") from err
    except json.JSONDecodeError as err:
        raise CassetteError(f"cassette 不是合法 JSON: {path}（{err}）") from err
    return Cassette.from_dict(data, origin=path)


def save_cassette(cassette: Cassette, directory: str | None = None) -> str:
    """原子写盘（``tempfile.mkstemp`` + ``os.replace``），返回写入路径。"""
    target_dir = directory or CASSETTE_DIR
    os.makedirs(target_dir, exist_ok=True)
    path = cassette_path(cassette.name, target_dir)
    handle_fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".cassette-", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(cassette.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        # mkstemp 建的是 0600；cassette 是入库夹具，按仓库常规权限落盘
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    logger.info("[cassette] 已写盘 %s（%d 条交互）", path, len(cassette.interactions))
    return path


def list_cassettes(directory: str | None = None) -> list[dict[str, Any]]:
    """索引已录制 cassette；无法读取者以 ``error`` 字段如实呈现，不静默跳过。"""
    target_dir = directory or CASSETTE_DIR
    if not os.path.isdir(target_dir):
        return []
    entries: list[dict[str, Any]] = []
    for filename in sorted(os.listdir(target_dir)):
        if not filename.endswith(".json"):
            continue
        name = filename[: -len(".json")]
        path = os.path.join(target_dir, filename)
        entry: dict[str, Any] = {"name": name, "path": path, "size_bytes": os.path.getsize(path)}
        try:
            cassette = load_cassette(name, target_dir)
        except CassetteError as err:
            entry["error"] = str(err)
        else:
            entry["source"] = cassette.source
            entry["recorded_at"] = cassette.recorded_at
            entry["interactions"] = len(cassette.interactions)
        entries.append(entry)
    return entries


# ── 传输层 ──────────────────────────────────────────────


def _build_response(interaction: Interaction) -> httpx.Response:
    """把录制交互还原为 ``httpx.Response``（按录制时的字符集还原字节）。"""
    headers = {k: v for k, v in interaction.headers.items() if k.lower() not in _REPLAY_DROPPED_HEADERS}
    return httpx.Response(
        interaction.status,
        headers=headers,
        content=interaction.body.encode(interaction.encoding),
    )


class _ReplayTransport(httpx.BaseTransport):
    """离线回放传输：只从 cassette 取响应，未命中即抛错（不联网）。"""

    def __init__(self, cassettes: Sequence[Cassette]) -> None:
        self._cassettes = list(cassettes)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = normalize_request_key(request.method, str(request.url))
        for cassette in self._cassettes:
            interaction = cassette.lookup(key)
            if interaction is not None:
                logger.debug("[cassette] 回放命中 %s ← %s", key, cassette.name)
                return _build_response(interaction)
        raise CassetteMissError(key, [f"{c.name}: {k}" for c in self._cassettes for k in c.keys])


class _RecordTransport(httpx.BaseTransport):
    """录制传输：真实请求照常发出，响应体顺带录进会话。"""

    def __init__(self, session: RecordingSession) -> None:
        self._session = session
        self._inner = make_transport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        # 消费流：既解掉 content-encoding 得到可读文本，又把内容缓存进 response，
        # 使上层客户端随后仍能正常读取（httpx 读取后走 _content 缓存）。
        response.read()
        self._session.observe(request, response)
        return response

    def close(self) -> None:
        self._inner.close()


class RecordingSession:
    """录制会话：收集交互，会话结束时**一次**原子写盘。

    逐次落盘会让「录到一半失败」留下半份 cassette；一次写盘配合 ``os.replace``
    保证磁盘上不会出现写了一半的文件。
    """

    def __init__(self, name: str, *, source: str = "", directory: str | None = None) -> None:
        self.cassette = Cassette(
            name=name,
            source=source,
            recorded_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        self._directory = directory
        self._dirty = False

    def observe(self, request: httpx.Request, response: httpx.Response) -> None:
        """把一次真实请求/响应收进会话（同键后写覆盖先写）。"""
        encoding = response.encoding or "utf-8"
        body = response.content or b""
        self.cassette.record(
            Interaction(
                method=request.method,
                url=str(request.url),
                status=response.status_code,
                headers=dict(response.headers.items()),
                body=body.decode(encoding, errors="replace"),
                encoding=encoding,
            )
        )
        self._dirty = True

    def flush(self) -> bool:
        """写盘；本次会话无新增录制内容时不动磁盘（返回 False）。

        幂等：重复调用（如用例内先自行写盘核验、退出时再兜底）不会重复写盘，
        也不会让「无录制内容」凭空产出一个空 cassette 文件。
        """
        if not self._dirty:
            return False
        save_cassette(self.cassette, self._directory)
        self._dirty = False
        return True


# ── 对外上下文管理器 ────────────────────────────────────


@contextmanager
def cassette_replay(names: Sequence[str], *, directory: str | None = None) -> Iterator[None]:
    """在该块内把 ``make_http_client()`` 的响应来源换成已录制 cassette。"""
    cassettes = [load_cassette(name, directory) for name in names]
    with use_transport_factory(lambda: _ReplayTransport(cassettes)):
        yield


@contextmanager
def cassette_record(name: str, *, source: str = "", directory: str | None = None) -> Iterator[RecordingSession]:
    """在该块内真实请求并把响应录进 ``name`` cassette（退出时一次原子写盘）。"""
    session = RecordingSession(name, source=source, directory=directory)
    with use_transport_factory(lambda: _RecordTransport(session)):
        yield session


# ── 解析校验 ────────────────────────────────────────────


def verify_cassettes(
    checks: Mapping[str, Callable[[], Any]] | None = None,
    *,
    directory: str | None = None,
    names: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """逐条离线回放并把响应交给**当前解析器**，报告可解析/解析失败。

    这是「真实响应体的解析路径」回归的人工可核验入口：解析器调用（``checks``
    的值）内部照常走 ``make_http_client``，其响应被替换为录制内容，因此校验的是
    「解析器能否吃下真实响应体」，而非引擎自身。

    Args:
        checks: cassette 名 → 无参解析器调用（返回解析结果，空结果视为失败）。
            未登记的 cassette 报 ``skipped``（不伪造通过）。
        directory: cassette 目录；缺省用仓库内 ``CASSETTE_DIR``。
        names: 只校验这些 cassette；缺省校验目录内全部。录制用例录完即刻自检时
            用它可以避免「顺带校验别的 cassette」的连带失败。

    Returns:
        每项含 ``name`` / ``status``（``ok`` / ``fail`` / ``skipped``）/ ``detail``。

    自身永不抛异常：本函数服务于诊断命令，异常转为 ``fail`` 详情上报。
    """
    registry = checks or {}
    wanted = set(names) if names is not None else None
    results: list[dict[str, Any]] = []
    for entry in list_cassettes(directory):
        name = entry["name"]
        if wanted is not None and name not in wanted:
            continue
        if "error" in entry:
            results.append({"name": name, "status": "fail", "detail": entry["error"]})
            continue
        check = registry.get(name)
        if check is None:
            results.append({"name": name, "status": "skipped", "detail": "未登记解析器，仅校验文件可读"})
            continue
        try:
            with cassette_replay([name], directory=directory):
                parsed = check()
        except Exception as err:  # 诊断入口：任何异常都如实上报，不向上抛
            results.append({"name": name, "status": "fail", "detail": f"{type(err).__name__}: {err}"})
            continue
        parseable = parsed not in (None, [], {}, "")
        results.append(
            {
                "name": name,
                "status": "ok" if parseable else "fail",
                "detail": "" if parseable else "当前解析器返回空结果（上游格式可能已变）",
                "interactions": entry.get("interactions", 0),
            }
        )
    return results


__all__ = [
    "CASSETTE_DIR",
    "VOLATILE_QUERY_PARAMS",
    "Cassette",
    "CassetteError",
    "CassetteMissError",
    "Interaction",
    "RecordingSession",
    "cassette_path",
    "cassette_record",
    "cassette_replay",
    "list_cassettes",
    "load_cassette",
    "normalize_request_key",
    "save_cassette",
    "verify_cassettes",
]
