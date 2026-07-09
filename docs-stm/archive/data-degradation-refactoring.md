# 数据降级系统重构 — 精细化 8 步子迭代方案

> 基于 D-8c ~ D-8e 全量代码审计和用户反馈，按"小步交付、风险分层、可逆可测"原则，
> 将整体重构拆分为 **8 个独立可提交/可回滚的子迭代**。
>
> 比对 D 迭代设计文档的详细程度，本方案每一轮都包含：
> - 精确文件（含预估行号、函数签名）
> - 关键代码片段
> - 测试用例规格（mock 策略 + 断言）
> - 验收标准（checkbox）
> - 风险分析 + 回退方案
> - 技术债务登记

---

## 总体架构目标

```
┌─────────────────────────────────────────────────────┐
│                 DataSourceRegistry                   │
│               src/python/provider_registry.py        │
├─────────────────────────────────────────────────────┤
│  register_provider(name, tier, fallback, timeout)   │
│  record_success/failure(provider, context)          │
│  is_circuit_broken(provider) → bool                 │
│  get_effective_strategy(code_type, market_hours)    │
│  session_cache_get/set(domain, code) → Any          │
│  generate_status_report() → dict                    │
│  reset()  ← 测试用                                  │
├─────────────────────────────────────────────────────┤
│  取代：chain.py._PROVIDER_SKIP (4 个全局变量)       │
│        fund_style_analysis._ext_memo (1 份)         │
│        eastmoney_industry._ext_memo (1份)           │
│        eastmoney_industry_rest._ext_memo (1份)      │
│        fund_style_analysis._tencent_failures (1)    │
│  关联：market_hours.py 交易时段感知                  │
│        cache.py 文件缓存                             │
└─────────────────────────────────────────────────────┘
```

### 策略枚举

```python
class FetchStrategy(Enum):
    LIVE_FETCH = "live"             # 盘中实时获取（走 Provider Chain + HTTP）
    CACHE_ONLY = "cache"            # 盘后只读缓存（不发起 HTTP）
    PLACEHOLDER = "placeholder"     # 所有路径都不可用 → 占位
```

### 核心数据流

```
handlers_report.py / excel_generator.py
       │
       ▼
  DataSourceRegistry.get_effective_strategy(code_type, market_hours)
       │
       ├── LIVE_FETCH ──▶ API 调用（chain.py / direct）
       │                          │
       │                     success/failure
       │                          │
       │                    registry.record_success/failure
       │
       ├── CACHE_ONLY ──▶ cache.get()（零 HTTP）
       │
       └── PLACEHOLDER ──▶ DetailRow(price=0, source="暂无行情")
                                  │
                                  ▼
                          registry.generate_status_report()
                                  │
                                  ▼
                          Excel data_status foot / HTML 状态摘要
```

---

## 第 1 轮：DataSourceRegistry 基础结构 — 纯新增（零改动）

### 做什么

纯新增 `src/python/provider_registry.py` 及其测试文件。
不修改任何现有生产代码。

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 新建 | `src/python/provider_registry.py` | ~250 | DataSourceRegistry 单例 |
| 新建 | `src/test/unit/core/test_provider_registry.py` | ~250 | 18 个测试用例 |

### 关键代码

```python
# src/python/provider_registry.py

from __future__ import annotations
import logging, threading, time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("invest")

_PROVIDER_SKIP_THRESHOLD = 3
_PROVIDER_COOLDOWN_SECS = 300
_SESSION_CACHE_MAX_ENTRIES = 2000

class FetchStrategy(Enum):
    LIVE_FETCH = "live"
    CACHE_ONLY = "cache"
    PLACEHOLDER = "placeholder"

@dataclass
class ProviderState:
    name: str; tier: int; fallback: str | None; timeout: float
    consecutive_failures: int = 0; last_failure_time: float = 0.0
    last_failure_context: str = ""; is_skipped: bool = False
    total_failures: int = 0; total_successes: int = 0

@dataclass
class SessionCacheEntry:
    value: Any; fetched_at: float; source: str

class DataSourceRegistry:
    """数据源注册中心（单例，线程安全）。"""

    _instance: DataSourceRegistry | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> DataSourceRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False): return
        self._initialized = True
        self._providers: dict[str, ProviderState] = {}
        self._session_cache: dict[str, dict[str, SessionCacheEntry]] = {}
        self._registry_lock = threading.Lock()

    # ── Provider 注册 ──
    def register_provider(self, name: str, tier: int = 4,
                          fallback: str | None = None, timeout: float = 10.0) -> None:
        with self._registry_lock:
            if name in self._providers:
                old = self._providers[name]
                old.tier = tier; old.fallback = fallback; old.timeout = timeout
            else:
                self._providers[name] = ProviderState(
                    name=name, tier=tier, fallback=fallback, timeout=timeout)

    # ── 熔断器 ──
    def record_success(self, provider: str) -> None:
        with self._registry_lock:
            state = self._providers.get(provider)
            if state is None: return
            state.consecutive_failures = 0; state.is_skipped = False
            state.total_successes += 1

    def record_failure(self, provider: str, context: str = "") -> None:
        with self._registry_lock:
            state = self._providers.get(provider)
            if state is None: return
            now = time.time()
            state.consecutive_failures += 1
            state.last_failure_time = now
            state.last_failure_context = context
            state.total_failures += 1
            if state.consecutive_failures >= _PROVIDER_SKIP_THRESHOLD:
                state.is_skipped = True
                logger.warning("[registry] %s 连续 %d 次失败（最新: %s），熔断 %ds",
                              provider, state.consecutive_failures, context,
                              _PROVIDER_COOLDOWN_SECS)

    def is_circuit_broken(self, provider: str) -> bool:
        with self._registry_lock:
            state = self._providers.get(provider)
            if state is None or not state.is_skipped: return False
            elapsed = time.time() - state.last_failure_time
            if elapsed >= _PROVIDER_COOLDOWN_SECS:
                state.is_skipped = False
                logger.info("[registry] %s 冷却期满（%.0fs），解除熔断", provider, elapsed)
                return False
            return True

    def is_chain_broken(self, chain: list[str]) -> bool:
        with self._registry_lock:
            now = time.time()
            for p in chain:
                state = self._providers.get(p)
                if state is None or not state.is_skipped: return False
            for p in chain:
                state = self._providers[p]
                if now - state.last_failure_time >= _PROVIDER_COOLDOWN_SECS:
                    state.is_skipped = False
                    return False
            return True

    def get_available_providers(self, chain: list[str]) -> list[str]:
        return [p for p in chain if not self.is_circuit_broken(p)]

    # ── 会话级缓存 ──
    def session_cache_get(self, domain: str, code: str) -> Any | None:
        with self._registry_lock:
            entry = self._session_cache.get(domain, {}).get(code)
            return entry.value if entry is not None else None

    def session_cache_set(self, domain: str, code: str, value: Any,
                          source: str = "api") -> None:
        with self._registry_lock:
            if domain not in self._session_cache:
                self._session_cache[domain] = {}
            dc = self._session_cache[domain]
            if len(dc) >= _SESSION_CACHE_MAX_ENTRIES:
                self._evict_oldest(dc)
            dc[code] = SessionCacheEntry(value=value, fetched_at=time.time(), source=source)

    def session_cache_clear(self, domain: str | None = None) -> None:
        with self._registry_lock:
            if domain is not None: self._session_cache.pop(domain, None)
            else: self._session_cache.clear()

    @staticmethod
    def _evict_oldest(dc: dict[str, SessionCacheEntry]) -> None:
        if len(dc) < 10: dc.clear(); return
        sorted_items = sorted(dc.items(), key=lambda x: x[1].fetched_at)
        for key, _ in sorted_items[:max(1, len(sorted_items) // 10)]:
            dc.pop(key, None)

    # ── 策略选择 ──
    def get_effective_strategy(self, code_type: str,
                               market_open: bool | None = None) -> FetchStrategy:
        if code_type in ("qdii", "hk_stock"):
            return FetchStrategy.LIVE_FETCH
        if market_open is None:
            from src.python.market_hours import is_market_open
            try: market_open = is_market_open()
            except Exception: market_open = False
        return FetchStrategy.LIVE_FETCH if market_open else FetchStrategy.CACHE_ONLY

    # ── 审计报告 ──
    def generate_status_report(self) -> dict[str, dict[str, Any]]:
        with self._registry_lock:
            now = time.time()
            report = {}
            for name, state in self._providers.items():
                cooldown = max(0.0, _PROVIDER_COOLDOWN_SECS - (now - state.last_failure_time)) \
                    if state.is_skipped else 0.0
                report[name] = {
                    "available": not state.is_skipped, "tier": state.tier,
                    "consecutive_failures": state.consecutive_failures,
                    "circuit_broken": state.is_skipped,
                    "cooldown_remaining": round(cooldown, 1),
                    "total_failures": state.total_failures,
                    "total_successes": state.total_successes,
                    "last_failure_context": state.last_failure_context,
                }
            return report

    def reset(self) -> None:
        with self._registry_lock: self._providers.clear(); self._session_cache.clear()

    # ── 兼容旧测试接口 ──
    def get_skip_set_copy(self) -> set[str]:
        with self._registry_lock: return {n for n, s in self._providers.items() if s.is_skipped}
    def get_skip_time_copy(self) -> dict[str, float]:
        with self._registry_lock:
            return {n: s.last_failure_time for n, s in self._providers.items() if s.is_skipped}


def get_registry() -> DataSourceRegistry:
    return DataSourceRegistry()
```

### 测试用例规格（18 个）

新建 `src/test/unit/core/test_provider_registry.py`。

| # | 测试函数 | 准备 | 验证断言 |
|:-:|:---------|:------|:---------|
| 1 | `test_register_provider_idempotent` | 注册 "t1" 两次，第二次改 timeout=20 | `_providers["t1"].timeout == 20`，熔断状态重置不受影响 |
| 2 | `test_record_success_resets` | "t1" 连续失败 2 次 → record_success | `consecutive_failures == 0`, `is_skipped == False` |
| 3 | `test_record_failure_under` | record_failure("t1") 连续 2 次 | `is_circuit_broken("t1") == False` |
| 4 | `test_record_failure_meets` | record_failure("t1") 连续 3 次 | `is_circuit_broken("t1") == True` |
| 5 | `test_cooldown_auto_recovery` | 3 次失败后 mock time.time 快进 301s | `is_circuit_broken("t1") == False` |
| 6 | `test_cooldown_not_expired` | 3 次失败后快进 299s | `is_circuit_broken("t1") == True` |
| 7 | `test_is_chain_broken_all` | "p1""p2" 各失败 3 次 | `is_chain_broken(["p1","p2"]) == True` |
| 8 | `test_is_chain_broken_one` | "p1" 失败 3 次,"p2" 正常 | `is_chain_broken(["p1","p2"]) == False` |
| 9 | `test_is_chain_broken_cooldown` | "p1" 熔断后快进 301s | `is_chain_broken(["p1"]) == False` |
| 10 | `test_get_available` | "p1" 熔断, "p2" 正常 | `get_available_providers(["p1","p2","p3"]) == ["p2","p3"]` |
| 11 | `test_session_cache_set_get` | set("price","600519",{...}) | get("price","600519") == {...} |
| 12 | `test_session_cache_miss` | 未写入的 code | get("price","000001") is None |
| 13 | `test_session_cache_clear` | 写入 2 个域 → clear() | 两域均为空 |
| 14 | `test_generate_status_report` | "t1" 正常, "t2" 熔断 | report["t2"]["circuit_broken"] == True |
| 15 | `test_thread_safety` | 10 线程各 100 次 record_failure/success | 无异常，最终计数正确 |
| 16 | `test_strategy_qdii` | code_type="qdii" | → LIVE_FETCH |
| 17 | `test_strategy_open` | code_type="a_share", market_open=True | → LIVE_FETCH |
| 18 | `test_strategy_closed` | code_type="a_share", market_open=False | → CACHE_ONLY |

### 质量门禁

- `git diff` 仅显示 2 个新文件（零改动现有代码）
- `pytest src/test/unit/core/test_provider_registry.py -v` 18/18 通过
- `python scripts/test_runner.py --mode regression` 通过
- 每项测试包含正向 + 边界 + 异常三种场景至少其一

### 风险与回退

**风险**：单例多线程 init 竞态（`__new__` + double-check lock 缓解）、会话缓存 OOM（2000 上限 + 淘汰机制缓解）。
**回退**：删除 2 个新文件即可，零影响。

---

## 第 2 轮：DataSourceRegistry 对接 chain.py

### 做什么

用 DataSourceRegistry 替换 chain.py 的 4 个全局变量（`_PROVIDER_SKIP` `_PROVIDER_SKIP_TIME` `_PROVIDER_CONSECUTIVE_FAILURES` `_PROVIDER_LOCK`）。
保留 `_TRANSPORT_FAILURE` sentinel 和 `_PROVIDER_COOLDOWN_SECS` 常量（移至 registry 内部）。

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/fetcher/chain.py` | ~30 | 删除 4 个全局变量，改用 `_get_registry()` 委托 |
| 修改 | `src/test/unit/fetcher/test_chain.py` | ~20 | 直接操作 `_PROVIDER_SKIP` → `_chain_registry()._providers` |
| 修改 | `src/test/unit/fetcher/test_chain_edge.py` | ~20 | 同上 |

### chain.py 改前 vs 改后对照

**改前（L52-L62）：**
```python
_PROVIDER_CONSECUTIVE_FAILURES: dict[str, int] = {}
_PROVIDER_SKIP: set[str] = set()
_PROVIDER_SKIP_TIME: dict[str, float] = {}
_PROVIDER_SKIP_THRESHOLD = 3
_PROVIDER_COOLDOWN_SECS = 300
_PROVIDER_LOCK = threading.Lock()
```

**改后：**
```python
from src.python.provider_registry import get_registry as _get_registry
```

**改前 `reset_provider_skip()`：**
```python
def reset_provider_skip() -> None:
    with _PROVIDER_LOCK:
        _PROVIDER_CONSECUTIVE_FAILURES.clear()
        _PROVIDER_SKIP.clear()
        _PROVIDER_SKIP_TIME.clear()
```

**改后：**
```python
def reset_provider_skip() -> None:
    _get_registry().reset()
```

**改前 `is_provider_chain_broken(data_type)`：**
```python
def is_provider_chain_broken(data_type: str) -> bool:
    chain = _get_chain(data_type)
    if not chain: return True
    with _PROVIDER_LOCK:
        return all(p in _PROVIDER_SKIP for p in chain)
```

**改后：**
```python
def is_provider_chain_broken(data_type: str) -> bool:
    chain = _get_chain(data_type)
    if not chain: return True
    registry = _get_registry()
    for p in chain:
        registry.register_provider(p, tier=2, timeout=10.0)
    return registry.is_chain_broken(chain)
```

**改前 `_fetch_with_fallback` 熔断检查部分（L179-L227）：** 约 50 行的锁操作 + 计数 + 冷却判断 + 日志

**改后：**
```python
registry = _get_registry()
for provider_name in chain:
    registry.register_provider(provider_name, tier=2, timeout=10.0)

for provider_name in chain:
    if registry.is_circuit_broken(provider_name):
        logger.debug("[%s] %s 已被熔断，跳过", data_type, provider_name)
        continue

    # ... _try_provider_fetch 调用（不变）...

    if result is not None and result is not _TRANSPORT_FAILURE:
        registry.record_success(provider_name)
        # ... 缓存 + return ...
    if result is _TRANSPORT_FAILURE:
        registry.record_failure(provider_name, "transport")
    # 代码级空结果（None）不计入熔断
```

### 测试改动

**`test_chain.py` 中需要改动的测试（3 个）：**

| 测试 | 原代码 | 新代码 |
|:-----|:-------|:-------|
| `test_chain_skip_skipped_provider` (L446) | `_PROVIDER_SKIP.update(["p1","p2"])` | `r = _chain_registry(); r.register_provider("p1",2,None,10); r.register_provider("p2",2,None,10); r._providers["p1"].is_skipped=True; r._providers["p2"].is_skipped=True; r._providers["p1"].consecutive_failures=3; r._providers["p2"].consecutive_failures=3; r._providers["p1"].last_failure_time=time.time(); r._providers["p2"].last_failure_time=time.time()` |
| `test_is_provider_chain_broken` (L455) | `_PROVIDER_SKIP.add("p1")` | 同上模式 |
| `test_cooldown_probe_recovery` (L478) | `_PROVIDER_SKIP.add("p1")` | 同上 + mock time.time |

**`test_chain_edge.py` 中需要改动的测试（4 个）：**
同样模式：`_PROVIDER_SKIP` → `r._providers["p1"].is_skipped = True`，`_PROVIDER_SKIP_TIME` → `r._providers["p1"].last_failure_time`

### 边界条件

| 条件 | 预期行为 |
|:-----|:---------|
| `_try_provider_fetch` 返回 `_TRANSPORT_FAILURE` sentinel | registry.record_failure("transport") 计入熔断计数 |
| `_try_provider_fetch` 返回 `None`（代码级空结果） | 不调用 registry.record_failure，不计入熔断 |
| 首次启动，chain.py 某 provider 未注册 | register_provider 幂等注册，默认 tier=2/timeout=10 |
| `is_provider_chain_broken` 传入空 chain | 返回 True（无可用 provider）|
| registry 全局重置被外部调用影响 chain | 需要确保 `reset()` 只在此处通过 `reset_provider_skip()` 调用 |

### 验收标准

- [ ] `git grep "_PROVIDER_CONSECUTIVE_FAILURES\|_PROVIDER_SKIP\|_PROVIDER_SKIP_TIME\|_PROVIDER_LOCK" src/python/fetcher/chain.py` 结果为零
- [ ] `is_provider_chain_broken("price")` 行为与旧版完全一致：全链熔断→True，有可用→False
- [ ] `_fetch_with_fallback` 中 transport 异常熔断规则不变（3 次→跳过→300s→试探）
- [ ] `reset_provider_skip()` 行为一致（registry.reset() 清空所有状态）
- [ ] `pytest src/test/unit/fetcher/ -k "chain" -v` 全通过（含 13 个 edge 测试）
- [ ] `pytest src/test/scenario/resilience/` 全通过（S7 网络中断降级）
- [ ] `python scripts/test_runner.py --mode regression` 通过

### 风险与回退

**风险**：测试中直接操作 `_providers` 时可能漏注册（`ProviderNotFound` → 测试失败）。
**回退**：恢复 chain.py 的 4 个全局变量 + 旧逻辑，测试文件 revert。代价 ~20min。

---

## 第 3 轮：会话级缓存统一（合并 3 份 _ext_memo）

### 做什么

将 3 份独立的 `_ext_memo` 模块级字典统一到 DataSourceRegistry 的 session_cache：
- `fund_style_analysis.py`（L35）— domain=`"extended"`
- `eastmoney_industry.py`（L56）— domain=`"industry"`
- `eastmoney_industry_rest.py`（L37）— domain=`"industry_rest"`

结束"同一股票跨模块重复 HTTP 请求"的问题。

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/report/fund_style_analysis.py` | ~15 | `_ext_memo` → `get_registry().session_cache_get/set("extended", code)` |
| 修改 | `src/python/providers/eastmoney_industry.py` | ~15 | `_ext_memo` → registry |
| 修改 | `src/python/providers/eastmoney_industry_rest.py` | ~10 | `_ext_memo` → registry |
| 修改 | `src/test/unit/report/test_fund_style_analysis.py` | ~10 | `_fsa_module._ext_memo.clear()` → `get_registry().session_cache_clear("extended")` |
| 修改 | `src/test/unit/providers/test_eastmoney_industry.py` | ~10 | `_ext_memo_clear()` → `get_registry().session_cache_clear("industry")` |
| 修改 | `src/test/unit/fetcher/test_fetcher_industry.py` | ~5 | 同上 |
| 修改 | `src/test/conftest.py` | ~10 | 新增 autouse fixture 自动清理 registry |

### 各文件具体改动

**`fund_style_analysis.py` 改动：**

```python
# 删除 L35：
# _ext_memo: dict[str, dict | None] = {}

# 所有读取 _ext_memo 的地方改为：
from src.python.provider_registry import get_registry as _get_registry
_registry = _get_registry()

# 读取（原 _ext_memo.get(code)）→
ext_data = _registry.session_cache_get("extended", code)

# 写入（原 _ext_memo[code] = data）→
_registry.session_cache_set("extended", code, data, source="push2")
```

具体位置：
- L305：`_push2_extended` 填充 `_ext_memo` → `_registry.session_cache_set("extended", code, ext_data, source="push2")`
- L370：`_ext_memo.update(results)` → 循环 `_registry.session_cache_set("extended", c, data, source="tencent")`
- L415-421：预取循环中 `code in _ext_memo` → `_registry.session_cache_get("extended", code) is not None`
- L440：`ext_data = _ext_memo.get(code)` → `_registry.session_cache_get("extended", code)`

**`eastmoney_industry.py` 改动：**

```python
# 删除 L56-61：
# _ext_memo: dict[...] = {}
# def _ext_memo_clear() -> None:
#     _ext_memo.clear()

# 读取（L180-181）: if code in _ext_memo: return _ext_memo[code]
# 改为：
from src.python.provider_registry import get_registry as _get_registry
_reg = _get_registry()
cached = _reg.session_cache_get("industry", code)
if cached is not None: return cached

# 写入（L185: _ext_memo[code] = None, 198: _ext_memo[code] = result）
# 改为：
_reg.session_cache_set("industry", code, None, source="push2")
_reg.session_cache_set("industry", code, result, source="push2")
```

**`eastmoney_industry_rest.py` 改动：** 同上，domain=`"industry_rest"`

**`conftest.py` 新增 autouse fixture：**

```python
# 在文件末尾或已有 fixture 区域新增
@pytest.fixture(autouse=True)
def _auto_reset_provider_registry():
    """每个测试执行后自动清理 DataSourceRegistry 状态，防止跨测试污染。"""
    yield
    from src.python.provider_registry import get_registry
    get_registry().reset()
```

### 测试改动详情

**`test_fund_style_analysis.py`：**

```python
# 删除 L33:
# import src.python.report.fund_style_analysis as _fsa_module

# L199: _fsa_module._ext_memo.clear() → 全部删除（由 conftest 自动处理）
# L303: _fsa_module._ext_memo[code] = val → get_registry().session_cache_set("extended", code, val)
# L310-311: _fsa_module._ext_memo 断言 → get_registry().session_cache_get("extended", code)
# L337-338: setUp 中 _fsa_module._ext_memo.clear() → 删除

# 导入修改
from src.python.provider_registry import get_registry as _get_registry_in_test
```

**`test_eastmoney_industry.py`：**

```python
# 所有 _ext_memo_clear() 调用 → 删除（conftest 自动处理）
```

### 验收标准

- [ ] `git grep "_ext_memo" src/python/` 结果为零
- [ ] `git grep "_ext_memo_clear" src/` 结果为零
- [ ] `conftest.py` 的 autouse fixture 存在且清理 registry
- [ ] `pytest src/test/unit/report/test_fund_style_analysis.py -v` 全通过
- [ ] `pytest src/test/unit/providers/test_eastmoney_industry.py -v` 全通过
- [ ] `pytest src/test/unit/report/` 全通过（conftest fixture 不会破坏任何测试）
- [ ] `python scripts/test_runner.py --mode regression` 通过
- [ ] 手动验证：mock push2 后 `session_cache_get("extended","600519")` 可在 `fund_style_analysis` 和 `eastmoney_industry` 间共享数据

### 技术债务登记

**暂不处理**：`fetch_market_data`（price.py）的缓存走的是 `cache.py` 文件缓存，未纳入 session cache。这不是 bug，是不同粒度的缓存（session vs file）。后续可考虑让 `fetch_market_data` 成功返回时也写入 session cache，但这不是本轮范围。

### 风险与回退

**风险**：测试隔离机制从"手动 clear"变为"autouse fixture"，如果 conftest 清理过晚（yield 位置不对）可能导致跨测试污染。需要确认 `yield` 在 fixture 中处于"测试执行后"位置。
**验证方式**：编写一个"脏读测试"：
```python
def test_first_writes_to_cache():
    get_registry().session_cache_set("extended", "600519", {"pe": 25})
def test_second_should_not_see_it():
    assert get_registry().session_cache_get("extended", "600519") is None  # 隔离 OK
```
**回退**：恢复 3 份 `_ext_memo` 全局变量 + 手动清理调用，删除 conftest 的 autouse fixture。代价 ~1h。

---

## 第 4 轮：市场时段感知策略选择集成

### 做什么

在第 1 轮已建立的 `get_effective_strategy()` 基础上，将策略选择逻辑集成到实际的数据获取入口中。核心改动：
1. `market_value.py` 的 `_generate_details` 在 `fetch_market_data` 前检查策略
2. 非交易时段且代码为 A 股 → CACHE_ONLY（不发起 HTTP，直接从文件缓存读）

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/report/market_value.py` | ~25 | `_generate_details` 集成策略选择 |
| 新建 | `src/test/unit/report/test_market_value_strategy_edge.py` | ~150 | 策略选择 8 个 edge 测试 |

### `_generate_details` 改动

```python
def _generate_details(holdings: list[Holding], today_str: str) -> list[DetailRow]:
    """获取所有持仓的行情数据并生成明细行（感知市场时段）。"""
    details: list[DetailRow] = []
    today_str = today_str or datetime.now().strftime("%Y-%m-%d")

    from src.python.provider_registry import get_registry as _get_registry
    registry = _get_registry()

    # 分类统计
    stock_holdings: list[Holding] = []
    fund_holdings: list[Holding] = []
    for h in holdings:
        code = h.code.strip()
        if is_a_share_code(code) or is_hk_stock_code(code):
            stock_holdings.append(h)
        elif is_qdii_extended(h.name):
            fund_holdings.append(h)  # QDII 走 LIVE_FETCH
        else:
            fund_holdings.append(h)  # 场外基金

    # A 股（含港股）非交易时段 → CACHE_ONLY
    if stock_holdings:
        strategy = registry.get_effective_strategy(
            "a_share" if any(is_a_share_code(h.code.strip()) for h in stock_holdings) else "hk_stock")
    else:
        strategy = FetchStrategy.LIVE_FETCH

    # CACHE_ONLY 策略：尽最大努力读缓存，不发起 HTTP
    if strategy == FetchStrategy.CACHE_ONLY:
        logger.info("非交易时段，A 股行情从缓存读取（CACHE_ONLY 策略）")
        for h in stock_holdings:
            mkt = _fetch_from_cache_only(h.code)  # ← 新增辅助函数
            details.append(_compute_detail_row(h, mkt))
        # 场外基金和 QDII 仍走正常路径
        if fund_holdings:
            details.extend(_generate_details_http(fund_holdings, today_str))
        return details

    # LIVE_FETCH 策略：正常 HTTP 获取（原逻辑）
    future_map = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for h in holdings:
            future = executor.submit(fetch_market_data, h.code, h.name)
            future_map[future] = h
        for future in as_completed(future_map):
            h = future_map[future]
            try:
                mkt = future.result()
            except Exception:
                logger.warning("获取行情异常: %s (%s)", h.name, h.code, exc_info=True)
                mkt = None
            details.append(_compute_detail_row(h, mkt))

    # ... 原有失败/成功计数统计（不变）...
    return details
```

**新增辅助函数 `_fetch_from_cache_only`：**

```python
def _fetch_from_cache_only(code: str) -> dict | None:
    """非交易时段从文件缓存读取行情，不发起 HTTP。

    已缓存 → 返回缓存数据（即使 TTL 过期，盘后只有缓存可用）
    未缓存 → 返回 None（后续走 DetailRow 占位路径）
    """
    from src.python import cache as _cache
    from src.python.fetcher.price import _price_cache_key
    key = _price_cache_key(code)
    ttl = 86400 * 7  # 最大容忍 7 天过期缓存
    data = _cache.get(key, ttl)
    if data is not None:
        logger.debug("盘后缓存命中: %s (TTL=%ds)", code, ttl)
    else:
        logger.debug("盘后缓存未命中: %s", code)
    return data
```

### 测试用例规格（8 个 edge 测试）

新建 `src/test/unit/report/test_market_value_strategy_edge.py`（`@pytest.mark.edge`）。

| # | 测试函数 | mock/准备 | 验证断言 |
|:-:|:---------|:----------|:---------|
| 1 | `test_market_open_a_share_http` | `is_market_open` → True, mock `fetch_market_data` | `fetch_market_data` 被调用（HTTP）|
| 2 | `test_market_closed_a_share_cache_only` | `is_market_open` → False, mock `cache.get` → 有缓存 | `fetch_market_data` 未被调用，DetailRow 数据来自缓存 |
| 3 | `test_market_closed_no_cache_fallback` | `is_market_open` → False, mock `cache.get` → None | `fetch_market_data` 未调用（禁止 HTTP），DetailRow price=0 |
| 4 | `test_qdii_always_http_regardless_market` | `is_market_open` → False, QDII holding | `fetch_market_data` 被调用（HTTP）|
| 5 | `test_hk_stock_always_http` | `is_market_open` → False, HK stock code | `fetch_market_data` 被调用 |
| 6 | `test_mixed_holdings_strategy` | 同时有 A 股+QDII，非交易时段 | A 股走缓存，QDII 走 HTTP |
| 7 | `test_cache_only_no_write_through` | `is_market_open` → False | 所有 HTTP 调用次数为 0（日志验证）|
| 8 | `test_cache_only_with_stale_cache` | `is_market_open` → False, 7 天前的缓存 | 正常读回，不更新 |

### 验收标准

- [ ] 交易时段：`_generate_details` 走原 HTTP 路径（`fetch_market_data` 被调用）
- [ ] 非交易时段 A 股：零 HTTP 请求，数据来自缓存（`fetch_market_data` 未被调用）
- [ ] 非交易时段无缓存 A 股：零 HTTP 请求，DetailRow 全 0（"暂无行情"占位）
- [ ] QDII/港股：不受 A 股时段限制，始终 HTTP
- [ ] 混合持仓：A 股走缓存 + QDII 走 HTTP，互不影响
- [ ] 8 个 edge 测试全部通过
- [ ] 所有现有测试通过（不破坏 market_value 的原有 50+ 个测试）

### 技术债务登记

**收市后验证（`_price_cache_fresh`）与策略选择器功能重叠**：
- 策略选择器是"预防式"的：非交易时段就不试了
- `_price_cache_fresh` 是"补丁式"的：走完 HTTP 发现数据过时再刷
- 两者共存期间不冲突：策略优先，`_price_cache_fresh` 作为双保险只在 LIVE_FETCH 路径下生效

### 风险与回退

**风险**：CACHE_ONLY 策略下如果缓存也没有，用户看到全零数据可能困惑。但这是合理的——非交易时段确实没有新价格。报告中已有"暂无行情"占位文字。
**回退**：恢复 `_generate_details` 原实现（`git checkout`），新代码作为 `_generate_details_v2` 保留。代价 ~10min。

---

## 第 5 轮：全局超时 + PhaseTimeout

### 做什么

为整个 data fetch 阶段设置全局超时，避免任一数据源卡死导致报告生成冻结。

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/provider_registry.py` | ~60 | 新增 `PhaseTimeout` 上下文管理器 |
| 修改 | `src/python/report/excel_generator.py` | ~30 | `_resolve_market_data` 包裹超时 |
| 修改 | `src/python/handlers_report.py` | ~20 | 报告生成全程包裹超时 |
| 新建 | `src/test/unit/core/test_phase_timeout.py` | ~100 | 超时 8 个测试 |

### PhaseTimeout 设计

```python
# 在 provider_registry.py 中新增

import signal
from contextlib import contextmanager
from threading import Timer

# Windows 兼容：signal.SIGALRM 不可用，用 threading.Timer
_phase_timer: threading.Timer | None = None
_phase_expired = False
_phase_timeout_lock = threading.Lock()


@contextmanager
def phase_timeout(seconds: float, phase_name: str = "data_fetch"):
    """数据获取阶段全局超时。

    超时后已获取的数据保留，未完成的以占位处理。
    超时不影响正在运行的 HTTP 线程（Python 无法 kill 线程），
    但结果被丢弃。

    Args:
        seconds: 超时秒数
        phase_name: 阶段名称（日志用）
    """
    global _phase_timer, _phase_expired

    start = time.time()
    _phase_expired = False

    def _expire():
        global _phase_expired
        with _phase_timeout_lock:
            _phase_expired = True
        logger.warning("[phase_timeout] %s 超时（%.0fs），继续使用已获取数据", phase_name, seconds)

    timer = Timer(seconds, _expire)
    timer.daemon = True
    timer.start()
    _phase_timer = timer

    try:
        yield _PhaseTimeoutContext(start, seconds)
    finally:
        timer.cancel()
        with _phase_timeout_lock:
            _phase_expired = False
        _phase_timer = None


class _PhaseTimeoutContext:
    """超时上下文，供调用方检查状态。"""

    def __init__(self, start: float, total: float):
        self._start = start
        self._total = total

    @property
    def expired(self) -> bool:
        with _phase_timeout_lock:
            return _phase_expired

    @property
    def elapsed(self) -> float:
        return time.time() - self._start

    @property
    def remaining(self) -> float:
        return max(0.0, self._total - self.elapsed)

    def check(self) -> None:
        """检查超时，超时时抛出 TimeoutError。"""
        if self.expired:
            raise TimeoutError(f"数据获取阶段超时（{self._total:.0f}s）")


# 在 DataSourceRegistry 类中新增
def check_phase_timeout(self) -> bool:
    """检查当前阶段是否已超时。"""
    return _phase_expired
```

### `excel_generator.py` 改动

```python
def _resolve_market_data(...):
    from src.python.provider_registry import phase_timeout

    with phase_timeout(120, "market_data"):
        if mvs is None:
            ...
        else:
            grand_mv, grand_cost, grand_profit, today_profit, details = mvs(
                ws2, holdings, today_str, details)
    
    # 超时后记录状态
    if _PhaseTimeoutContext.expired:  # 伪代码，实际需要通过上下文检查
        prog.add_warning("市场数据获取超时，部分数据可能不可用")
```

### 测试用例规格（8 个）

| # | 测试 | mock | 断言 |
|:-:|:-----|:------|:-----|
| 1 | `test_no_timeout_normal` | 快速 mock（< 0.1s） | 不触发超时，正常返回 |
| 2 | `test_timeout_triggers` | sleep 0.3s + timeout=0.1s | `expired == True` |
| 3 | `test_remaining_positive` | timeout=10s，检查 0.1s 后 remaining | `remaining ≈ 9.9` |
| 4 | `test_elapsed_non_zero` | timeout=10s | `elapsed > 0` |
| 5 | `test_cancel_on_exit` | 短时间内完成 | 退出后 `expired == False`（timer 已 cancel）|
| 6 | `test_nested_timeout` | 两层 phase_timeout 嵌套 | 外层超时覆盖内层 |
| 7 | `test_check_raises_on_expired` | timeout=0.05s, sleep 0.1s | `check()` 抛出 TimeoutError |
| 8 | `test_check_noop_on_normal` | 正常执行 | `check()` 不抛出 |

### 风险与回退

**风险**：`threading.Timer` 无法 kill Python 线程，超时后仍在运行的 HTTP 请求会消耗少量带宽。这是 Python 线程模型的限制，非我们设计能解决。
**回退**：移除 `phase_timeout` 上下文管理器及其调用，恢复无超时原始行为。代价 ~15min。

---

## 第 6 轮：_generate_details 完整集成 + price.py 对接

### 做什么

让整个 price 数据获取路径完整使用 DataSourceRegistry 的策略+熔断+缓存。本轮重构是整个方案中改动最集中的一环，需将 `fetch_market_data` 也挂接到 registry 上，确保 price 链路的熔断决策与其他模块一致。

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/fetcher/price.py` | ~20 | `fetch_market_data` 写入 session cache + 注册 provider |
| 修改 | `src/python/report/market_value.py` | ~30 | `_generate_details` 完整使用 registry |
| 修改 | `src/test/unit/fetcher/test_fetcher_price.py` | ~15 | 适配新接口 |

### `fetch_market_data` 改动

```python
def fetch_market_data(code: str, expected_name: str = "") -> dict[str, Any] | None:
    # ... 原有代码开头 ...

    # 写入 registry session cache（成功时才写）
    result = _fetch_with_fallback(...)  # 原逻辑

    if result is not None:
        from src.python.provider_registry import get_registry
        get_registry().session_cache_set("price", code, result, source="api")

    # ... 原有收市后验证逻辑 ...
    return result
```

### 验收标准

- [ ] `fetch_market_data` 成功后自动写入 registry session cache（`domain="price"`）
- [ ] `_generate_details` 中的 `fetch_market_data` 成功/失败均通过 registry 记录
- [ ] `pytest src/test/unit/report/test_market_value.py -v` 全通过
- [ ] `pytest src/test/unit/fetcher/test_fetcher_price.py -v` 全通过
- [ ] `python scripts/test_runner.py --mode regression` 通过

### 风险与回退

**风险**：`fetch_market_data` 被多处调用（`_generate_details` 中的 ThreadPoolExecutor + 单条调用），session cache 写入不影响原有行为，风险低。
**回退**：恢复 `fetch_market_data` 原实现。代价 ~5min。

---

## 第 7 轮：熔断器完全统一（消除 _tencent_failures）

### 做什么

消除 `fund_style_analysis.py` 中最后一个独立熔断器 `_tencent_failures`。
原有逻辑：`tencent_extended` 连续失败 2 次后跳过（无冷却期，永久跳过）。
新逻辑：通过 `registry.is_circuit_broken("tencent")` 统一管理（3 次/300s 冷却，冷却后自动试探恢复）。

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/report/fund_style_analysis.py` | ~20 | 删除 `_tencent_failures` + `global`，改用 registry |
| 修改 | `src/test/unit/report/test_fund_style_analysis.py` | ~5 | 删除 `_tencent_failures` 相关 mock |

### `fund_style_analysis.py` 改动

```python
# 删除：
# _tencent_failures = 0
# _TENCENT_SKIP_THRESHOLD = 2

# 删除 classify_fund_style 函数中的：
# global _tencent_failures

# 批处理前的熔断检查（L423）：
# if _need_tencent and _tencent_failures < _TENCENT_SKIP_THRESHOLD:
# 改为：
if _need_tencent:
    registry = _get_registry()
    registry.register_provider("tencent", tier=3, timeout=10.0, fallback="code_estimate")
    if not registry.is_circuit_broken("tencent"):
        _batch_tencent_extended(_need_tencent)
    else:
        logger.info("Tencent 扩展行情已熔断，跳过批量回退")
```

### 验收标准

- [ ] `git grep "_tencent_failures\|_TENCENT_SKIP_THRESHOLD" src/python/` 结果为零
- [ ] `global _tencent_failures` 从 `fund_style_analysis.py` 中移除
- [ ] push2 和 tencent 的熔断阈值统一为 3 次/300s
- [ ] `pytest src/test/unit/report/test_fund_style_analysis.py -v` 全通过（12 个测试）
- [ ] `python scripts/test_runner.py --mode regression` 通过

### 风险登记

阈值从 2 次（永久跳过）变为 3 次（300s 冷却自动恢复），理论上降低了熔断敏感性（多容忍 1 次失败），但增加了冷却后自动恢复的能力。行为变化是良性的。

### 回退方案

恢复 `_tencent_failures` 全局变量 + global 声明 + 旧预取逻辑。代价 ~20min。

---

## 第 8 轮：降级审计日志 + 报告数据源状态页签

### 做什么

在前 7 轮基础上建立：
1. 自动化的测试隔离（conftest 的 autouse fixture 已完成）
2. 降级决策的可审计输出
3. 日志降噪（熔断期间不逐条刷 warning）

### 精确文件清单

| 操作 | 文件 | 行数 | 内容 |
|:----:|:-----|:----:|:-----|
| 修改 | `src/python/provider_registry.py` | ~15 | `record_failure` 熔断期间日志从 warning 降级为 debug |
| 修改 | `src/python/report/excel_generator.py` | ~25 | 报告末尾新增"数据源状态"页签 |
| 修改 | `src/python/report/html_writer.py` | ~20 | HTML 报告新增数据源状态摘要 |
| 修改 | `src/python/tmpl/report_template.html` | ~20 | CSS + 条件渲染块 |
| 新建 | `src/test/unit/report/test_registry_audit.py` | ~80 | 审计日志相关测试 |
| 修改 | `docs-stm/managements/technical.md` | ~30 | 同步更新架构文档 |

### 审计报告数据流

```
report 生成结束时 → registry.generate_status_report()
    ↓
dict:
  tencent: {available: True, consecutive_failures: 0, circuit_broken: False, ...}
  eastmoney: {available: False, circuit_broken: True, cooldown_remaining: 120, ...}
    ↓
excel_generator.py: 追加"数据源状态"页签
html_writer.py: 在报告底部条件渲染
```

### 日志降噪细则

| 当前行为 | 熔断期间行为 | 恢复后行为 |
|:---------|:-------------|:-----------|
| `logger.warning("Tencent 扩展数据获取失败")` × N 条 | `logger.debug("...跳过(熔断)...")` × N 条 | `logger.info("...冷却期满...")` × 1 条 |
| 每条失败都打 warning | 只在第一条熔断触发时打 warning | 不在每个熔断循环中重复打 |
| 汇总日志在 `_generate_details` 中已有 | 保持 | 保持 |

### 验收标准

- [ ] 熔断期间的重复失败日志自动降级为 debug（只打一次 warning）
- [ ] 冷却恢复时打 info 日志
- [ ] Excel 报告末尾出现"数据源状态"页签（或 data_status foot），列出每个 provider 的可用状态
- [ ] HTML 报告底部有条件渲染的数据源状态摘要
- [ ] `pytest src/test/unit/report/` 全通过
- [ ] `python scripts/test_runner.py --mode regression` 通过
- [ ] `python scripts/test_runner.py --mode verify` 通过

---

## 重构代价总览

| 轮次 | 范围 | 新增 | 修改 | 涉及测试文件 | 风险 |
|:----:|:-----|:----:|:----:|:-----------:|:----:|
| 1 | provider_registry.py 纯新增 | ~250 | 0 | 1 新文件 | 低 |
| 2 | chain.py 熔断器替换 | 0 | ~30 | 2 | 中 |
| 3 | 3 份 _ext_memo 合并 | 0 | ~40 | 4+conftest | 中高 |
| 4 | 市场时段感知策略 | ~150 | ~25 | 1 新文件 | 中 |
| 5 | 全局超时 PhaseTimeout | ~100 | ~50 | 1 新文件 | 中 |
| 6 | _generate_details 集成 | 0 | ~50 | 1 | 中 |
| 7 | _tencent_failures 清除 | 0 | ~20 | 1 | 高 |
| 8 | 审计日志 + 降噪 | ~80 | ~80 | 1 新文件 | 低 |
| **合计** | | **~580** | **~295** | **~13** | |

### 执行顺序依赖

```
1 → 2 → 3 → 4 → 6 → 7 → 8
         ↓
         5 (可与 4/6 并行)
```

- 1 → 2（先建基础设施，再替换 chain.py）
- 2 → 6（chain.py 熔断统一后再集成 fetch_market_data）
- 4 → 6（策略选择器先于 _generate_details 集成）
- 3 不依赖 1/2，可并行；5 不依赖其他
- 8 是最后的收尾轮

---

## 关于"为什么之前这么差"的自我批评

1. **非交易时段从没测试过**：所有测试都在"交易时段"假设下编写，午夜跑报告是盲区
2. **熔断设计只考虑了"正常运行时挂一个 API"，没考虑"所有 API 都不可用应快速降级"**
3. **\`_ext_memo\` 的碎片化不是因为需要 3 份缓存，而是因为 3 个模块分属不同迭代加入**：
   - `fund_style_analysis._ext_memo` — D-8 早期加入
   - `eastmoney_industry._ext_memo` — D-8b R-167 加入（本应合并但没做）
   - `eastmoney_industry_rest._ext_memo` — 同上
4. **全局超时被忽略了**：每个模块都假设"API 要么快速返回，要么快速超时"，没考虑"API 全挂了但每个都要等 15s 超时"
5. **降级不是补丁**：以上 4 个问题叠加，导致用户在非交易时段按 L → 每个 API 等 15s 超时 → 熔断 → 回退 → 再试另一个 → 2h+ 耗完

**核心教训**：数据降级不是"正常路径的补丁"，是和主路径同等重要的设计维度。如果一开始就设非交易时段的测试，所有问题会在第一个版本暴露。

---

## 架构合规复盘（基于 technical.md C1-C13 设计约束）

> 以下复盘审视角从 **5 个独立维度** 对照 `technical.md` §设计约束（C1~C13），逐轮检查计划是否合规、有无遗漏约束、以及计划本身是否可以优化。

### 第 1 轮：架构约束遵从严审（C1-C13）

| 约束 | 要求 | 方案是否遵守 | 发现 |
|:----:|:-----|:----------:|:------|
| C1 | 代码类型判定中心化（code_utils） | ⚠️ 部分 | Round 4 的 `_generate_details` 中 `is_a_share_code()` / `is_hk_stock_code()` / `is_qdii_extended()` 确实来自 code_utils ✅；但 Round 4 在 `_generate_details` 中**重新实现了**分类逻辑（尽管用了 code_utils 原语），与已有的 `classify_holdings()` 重复。需要改用 `classify_holdings` 来避免 C1 原则被架空 |
| C2 | 缓存统一管理（cache.py） | ✅ | 新增 `_fetch_from_cache_only` 使用 `cache.get()` ✅；registry 的 `session_cache` 是进程级内存缓存（非久化），不受 C2 管辖 |
| C3 | 缓存原子写入 | ✅ | 新增代码不涉及文件写入，registry session cache 是内存操作 |
| C4 | 会话级 API 复用缓存（_ext_memo 模式） | ⚠️ **有冲突需更新约束** | 方案是**用 registry session cache 取代** 3 份 `_ext_memo`。技术方向上正确（集中化优于分散化），但 C4 原文明确写 `_ext_memo: dict` 并引用 `fund_style_analysis.py`。做完后**必须同步更新 C4**，改为：`DataSourceRegistry.session_cache` 优先推荐，模块级 `_ext_memo` 为备选方案 |
| C5 | HTTP 客户端统一（http_client.py） | ✅ | 不引入新 HTTP 调用 |
| C6 | Provider Chain 必经 | ✅ ⚠️ | CACHE_ONLY 策略直接读缓存（不走 Provider），这不违反 C6——C6 说的是"获取数据必须过 chain.py"，缓存读取不是获取新数据。但需确保 LIVE_FETCH 路径始终走 `_fetch_with_fallback()` |
| C7 | 报告序号注册表驱动 | ❌ **遗漏** | Round 8 新增"数据源状态"页签/状态摘要，这本质是新增报告模块/页签。C7 要求所有报告模块序号和显示名必须在 `registry.py` 注册表驱动。方案未提及注册到 `registry.py` 的步骤。**必须在 Round 8 中补上** |
| C8 | 日志统一（logger invest） | ✅ | 所有日志使用 `logging.getLogger("invest")` |
| C9 | LLM 模块注册 | N/A | 不影响 |
| C10 | 新闻召回策略 | N/A | 不影响 |
| C11 | 测试标记强制 | ❌ **遗漏** | 方案提到了 `@pytest.mark.edge`，但未指定其他新测试文件的模块级 marker。新增 4 个测试文件各需对应 marker（如 `unit_core`、`unit_report`、`unit_providers`），且需要在 `conftest.py` 的 `pytest_configure` 中注册 |
| C12 | 边缘测试文件隔离 | ✅ | `test_market_value_strategy_edge.py` 命名 ✅ (`_edge.py`) |
| C13 | 测试敏感路径隔离 | ✅ | 不修改 config/holdings |

**C7 修正在**：Round 8 需要：
1. 在 `registry.py` 的 `_REPORT_SECTION_DEFAULT` 中新增 `"data_source_status"` 条目
2. 在 `excel_generator.py` 中注册 `section_order` 传递
3. 在 HTML 模板中通过 `section_visible("data_source_status")` 控制显示

**C4 修正**：完成后需将 `technical.md` 中 C4 的 "`_ext_memo: dict`" 改为 "`DataSourceRegistry.session_cache`"。

### 第 2 轮：运行时风险评估（代码级失效分析）

**Risk A：`_generate_details` 中分类逻辑与 `classify_holdings` 重复 → 数据丢失**

Round 4 的代码用 `is_a_share_code()` 和 `is_hk_stock_code()` 直接对代码前缀分组，而 `classify_holdings` 的优先级是：`QDII 名称 → 场外账户 → ETF → 场内股票 → 国内场外`。

问题是：A 股代码前缀和场外基金代码可能重叠（如 `002943` 既是股票代码也是场外基金）。
- `_generate_details` 中 `is_a_share_code("002943")` → True → 分入 stock_holdings → CACHE_ONLY
- 但 `classify_holdings` 中因为账户是 "基金账户" → 分入 国内场外 → LIVE_FETCH

两种路径产生不同结果。用 `classify_holdings` 可以消除此差异。

**严重度：高**。修复：Round 4 直接使用 `classify_holdings` 的返回结果，**不在 `_generate_details` 中重复实现分类**。

**Risk B：CACHE_ONLY 策略读到的缓存可能与实际交易日不同步**

场景：
1. 用户周五收盘后运行 L → LIVE_FETCH 获取周五收盘价 → 写入文件缓存（price_date=周五）
2. 用户周一早上开盘前运行 E → CACHE_ONLY 从缓存读周五数据 → DetailRow 显示"今日行情"但实际是 3 天前的

当前 `_price_cache_fresh` 在 price.py 中会在 LIVE_FETCH 路径下校验 price_date。但 CACHE_ONLY 绕过了 `fetch_market_data`，因此也绕过了 `_price_cache_fresh`。

**严重度：中**。修复：`_fetch_from_cache_only` 需要校验缓存中的 `price_date`，如果不是当天则标记"盘后缓存"或返回 None。

```python
def _fetch_from_cache_only(code: str) -> dict | None:
    registry = get_registry()
    cached = registry.session_cache_get("price", code)
    if cached is not None: return cached
    from src.python import cache as _cache
    from src.python.fetcher.price import _price_cache_key
    key = _price_cache_key(code)
    data = _cache.get(key, 86400 * 7)
    if data is not None:
        price_date = data.get("price_date", "")
        if price_date != datetime.now().strftime("%Y-%m-%d"):
            logger.debug("盘后缓存日期 %s 不是今天，仍返回（非交易时段无新价）", price_date)
            data["_cache_date_mismatch"] = True  # 标记，供详情行显示
    return data
```

**Risk C：Round 2 测试改动在 Round 3 conftest fixture 生效前有隔离断层**

Round 2 修改了 `test_chain.py` 和 `test_chain_edge.py`，使其通过 registry 操作熔断状态。但 registry 的 autouse 清理 fixture（conftest.py）要到 Round 3 才加入。

在 Round 2 ↔ Round 3 的窗口期内，**registry 的 `_providers` 状态跨测试污染**——一个测试设置熔断状态后，后续测试可能误判。

**严重度：高**。修复：将 conftest fixture **提前到 Round 1 就加入**（注册表建好 → 就要隔离）。

**Risk D：PhaseTimeout global 变量不支持嵌套调用**

`_phase_expired` 是全局变量。如果 `_resolve_market_data` 包裹了一个 `phase_timeout(120)`，其间又调用 `_fetch_with_fallback` 内部的什么逻辑也用了 `phase_timeout`（虽然目前没有，但以后可能加），内层的超时触发会修改全局 `_phase_expired`，让外层误以为超时了。

**严重度：中**。修复：禁止嵌套（`raise RuntimeError`），或改用 stack。

### 第 3 轮：设计方案深度优化

**优化 1：策略选择器应该感知熔断状态（不仅感知市场时段）**

当前 `get_effective_strategy` 只检查 `market_open` 和 `code_type`。但在交易时段如果全部 provider 都已熔断，LIVE_FETCH 必然失败（且需要等待 15s 超时）。

改进：
```python
def get_effective_strategy(self, code_type: str,
                           chain: list[str] | None = None,
                           market_open: bool | None = None) -> FetchStrategy:
    if code_type in ("qdii", "hk_stock"):
        return FetchStrategy.LIVE_FETCH
    if market_open is None:
        from src.python.market_hours import is_market_open
        try: market_open = is_market_open()
        except Exception: market_open = False
    if not market_open:
        return FetchStrategy.CACHE_ONLY
    # 熔断状态感知：链已全熔断 → 降级到 CACHE_ONLY 而非白白等超时
    if chain and self.is_chain_broken(chain):
        logger.info("策略降级: %s 链已熔断，LIVE_FETCH → CACHE_ONLY", chain)
        return FetchStrategy.CACHE_ONLY
    return FetchStrategy.LIVE_FETCH
```

这修复了原始问题 2.0 的深层场景：**"交易时段所有 API 都不可用时仍然无脑 HTTP 等超时"**。

**优化 2：`_fetch_from_cache_only` 应该位于 registry 层而非 market_value 层**

当前方案将 `_fetch_from_cache_only` 放在 `market_value.py` 中作为 module-level 函数。但如果其他模块（如 category.py 或 summary.py）也需要非交易时段的缓存读取，就需要重复实现。

改进：将 `_fetch_from_cache_only` 搬到 `provider_registry.py` 中：
```python
# 在 DataSourceRegistry 中新增
def fetch_cached_only(self, code: str, cache_domain: str,
                       cache_key_fn: Callable[[str], str] | None = None) -> Any | None:
    """仅从缓存读取（不发起 HTTP），session_cache → file_cache 两级 fallback。"""
    # 1. session cache
    result = self.session_cache_get(cache_domain, code)
    if result is not None: return result
    # 2. file cache
    if cache_key_fn:
        key = cache_key_fn(code)
        from src.python import cache as _cache
        data = _cache.get(key, max_age=86400 * 7)
        if data is not None:
            self.session_cache_set(cache_domain, code, data, source="file")
            return data
    return None
```

但这引入 `cache_key_fn` 耦合。考虑简单性，保留 `_fetch_from_cache_only` 在 `market_value.py` 但通过调用 registry 的 session_cache 作为第一级。

**优化 3：registry 应提供 `fetch_or_cached` 统一入口**

减少调用方的策略判断代码：
```python
def fetch_or_cached(self, code: str, code_type: str,
                    fetch_fn: Callable[[str], Any],
                    chain: list[str] | None = None,
                    cache_domain: str = "price",
                    cache_key_fn: Callable[[str], str] | None = None) -> Any:
    """策略感知的数据获取：根据策略决定走 HTTP 还是缓存。"""
    strategy = self.get_effective_strategy(code_type, chain)
    if strategy == FetchStrategy.CACHE_ONLY:
        return self.fetch_cached_only(code, cache_domain, cache_key_fn)
    # LIVE_FETCH
    result = fetch_fn(code)
    if result is not None:
        self.session_cache_set(cache_domain, code, result)
    return result
```

这样 `_generate_details` 的策略选择变成了：
```python
for h in holdings:
    mkt = registry.fetch_or_cached(
        h.code, "a_share", fetch_market_data,
        chain=["tencent", "eastmoney"], cache_domain="price")
    details.append(_compute_detail_row(h, mkt))
```

**优化 4：Chain 定义集中化**

当前 `_DEFAULT_CHAINS` 在 `chain.py` 中，但 `register_provider` 分散在：
- `_fetch_with_fallback`（chain.py L189+）
- `is_provider_chain_broken`（chain.py L73+）
- `classify_fund_style`（fund_style_analysis.py L423+）

没有统一入口。建议在 registry 中增加 `register_default_chains()`：
```python
def register_default_chains(self) -> None:
    chains = {
        "price": [("tencent", 2, 10.0), ("eastmoney", 2, 15.0)],
        "fund_rank": [("tiantian", 3, 20.0)],
        "fund_hold": [("tiantian", 3, 20.0)],
        "industry": [("eastmoney_industry", 3, 10.0), ("eastmoney_industry_rest", 3, 10.0)],
    }
    for data_type, provider_list in chains.items():
        for name, tier, timeout in provider_list:
            self.register_provider(name, tier, None, timeout)
        self._chains[data_type] = [name for name, _, _ in provider_list]
```

此函数在 `chain.py` 模块加载时调用一次，消除分散注册。

### 第 4 轮：执行顺序与测试策略再优化

**问题 1：conftest fixture 引入过早导致模拟问题**

Round 1 的 conftest autouse fixture 会在每个测试后 reset registry。但 Round 1 本身只新增 2 个文件，现有测试不认识 registry——这意味着现有测试的 setUp 中如果有 mock registry 状态的操作，在 fixture reset 后被清零。

好在现有测试在 Round 1 时完全不引用 registry（registry 是新文件）。所以 fixture 在 Round 1 加入后**仅影响 2 个新测试文件**，不影响现有测试。✅

**问题 2：Round 2 测试改动的隔离断层确认**

在 Round 2 完成、Round 3 开始前：
- registry 存在 ✅（Round 1 已建）
- conftest fixture 存在 ✅（Round 1 已加，因为建议 fixture 提前）
- `test_chain.py` 中的 3 个测试改用 registry 操作 ✅
- 测试间的 registry 状态由 conftest fixture 自动清理 ✅

所以如果 fixture 在 Round 1 加，断层问题不存在。**关键修复**：conftest fixture 不等到 Round 3，跟着 Round 1 走。

**问题 3：test marker 注册策略**

| 测试文件 | 源轮次 | 需要 marker | 是否 _edge |
|:---------|:------|:-----------|:----------|
| `test_provider_registry.py` | Round 1 | `@pytest.mark.unit_core` | 否 |
| `test_phase_timeout.py` | Round 1（合并后） | `@pytest.mark.unit_core` | 否 |
| `test_market_value_strategy_edge.py` | Round 4 | `@pytest.mark.edge` + `@pytest.mark.unit_report` | **是** |
| `test_registry_audit.py` | Round 8 | `@pytest.mark.unit_report` | 否 |

C11 要求 `pytestmark` 模块级变量 + 新 marker 注册到 `conftest.py:pytest_configure`。

**问题 4：5 步执行计划的最终版本**

综合第 3 轮的优化方案，进一步优化：

| 步 | 轮次 | 新增 | 修改 | 风险 | 交付价值 |
|:--:|:----|:----:|:----:|:----:|:---------|
| **A** | DataFrameRegistry + PhaseTimeout + `register_default_chains()` + chain 定义集中化 + conftest fixture + test markers | ~360 | ~15 (chain.py + conftest.py) | 低 | 基础设施完整，chain.py 首次获得预热注册机制 |
| **B** | 策略选择器集成（`get_effective_strategy` 加入熔断感知）+ `_generate_details` 改用 `classify_holdings` + `fetch_or_cached` | ~170 | ~40 | **中** | ✅ 用户可感知：非交易时段报告速度暴涨 |
| **C** | chain.py 熔断替换 + 行为等价性测试 + chain registry 验证 | 0 | ~45 | 中 | 熔断行为统一，消除 `_PROVIDER_SKIP` 等 4 个全局变量 |
| **D** | 3 份 _ext_memo + _tencent_failures 统一清除 + 更新 C4 约束文档 | 0 | ~55 | 中 | 消除模块级全局变量，统一缓存路径 |
| **E** | `_generate_details` 集成 + 审计报告 + C7 "数据源状态"注册到 registry.py + 更新 technical.md | ~80 | ~120 | 低 | 数据源可视化 + 架构文档同步 |
| **合计** | | **~610** | **~265** | | **第 B 步即产生可测量收益** |

### 第 5 轮：技术债务取舍分析

**可接受债务（不修复）：**
1. **`_fetch_with_fallback` 的 80 行复杂度** — 稳定无 bug，重构的边际收益低
2. **PhaseTimeout daemon Timer 线程残留** — 重量极轻，不影响 shutdown
3. **session_cache + file_cache 双缓存** — 各司其职（快 vs 持久），桥接逻辑已够
4. **provider timeout 注册值硬编码** — timeout 当前未被用于实际控制（只有熔断计数用），可后续再加

**不可接受债务（必须修复）：**
1. ⚠️ **C7 注册表遗漏** — "数据源状态"直接写进 Excel/HTML 而不走 registry → 将来改排序/重命名时遗漏。**每引入一个新页签都必须先注册**
2. ⚠️ **C4 约束过时** — 完成 _ext_memo → registry 迁移后，technical.md 中的约束仍引用 `_ext_memo` 模式，新开发者会困惑
3. ⚠️ **Round 4 分类逻辑不信任 `classify_holdings`** — 如果 `_generate_details` 自己分类而 `classify_holdings` 被更新但未同步，两者不一致 → 数据丢失

**建议积极处理的债务：**
1. ✅ **第 A 步中集中 chain 定义**— `register_default_chains()` 消灭分散注册，代价仅 ~20 行，一次搞定
2. ✅ **第 B 步中 `fetch_or_cached` 统一入口** — 减少调用方策略判断代码，集中测试

---

## 最终优化方案（5 步，融入所有复盘发现）

下列 5 步方案吸收了全部 5 轮复盘结论：

### 第 A 步：基础设施（原 1+5 + C4/C11 前置修补）

- 新建 `provider_registry.py`（含 DataSourceRegistry + PhaseTimeout + `register_default_chains`）
- 新增 conftest autouse 清理 fixture（scope=function）
- 新增 2 个测试文件（`test_provider_registry.py` + `test_phase_timeout.py`），注 `@pytest.mark.unit_core`
- conftest.py 注册 `unit_core` marker
- **关键设计变化**：
  - 锁 `_provider_lock` + `_cache_lock` 双锁（单锁 → 双锁）
  - 淘汰策略 O(1) 弹出（非 O(n log n) 排序）
  - `get_effective_strategy` 新增 `chain` 参数（熔断感知）
  - `register_default_chains()` 集中定义所有 chain
  - 禁止 PhaseTimeout 嵌套（`raise RuntimeError`）

### 第 B 步：策略选择器（原 4 优化版）

- `_generate_details` 重构：使用 `classify_holdings` 分类，通过 `fetch_or_cached` 获取数据
- 策略选择器引入**熔断感知**：全链熔断时自动降级 CACHE_ONLY
- `_fetch_from_cache_only` 从 market_value 层移至 registry 层作为 `fetch_cached_only`
- 新建 `test_market_value_strategy_edge.py`（`@pytest.mark.edge` + `@pytest.mark.unit_report`）
- **验收标准扩展**：
  - 交易时段、provider 全熔断 → CACHE_ONLY（非简单 LIVE_FETCH）
  - `_fetch_from_cache_only` 可验证缓存日期与当天是否匹配

### 第 C 步：chain.py 替换（原 2 + 验证）

- 删除 `_PROVIDER_SKIP` / `_SKIP_TIME` / `_CONSECUTIVE_FAILURES` / `_LOCK` 4 个全局变量
- `_fetch_with_fallback` 熔断逻辑委托 registry
- `reset_provider_skip()` 委托 `registry.reset()`
- `is_provider_chain_broken()` 委托 `registry.is_chain_broken()`
- 前置：写**行为等价性测试**验证 old-path-new-path 一致

### 第 D 步：状态统一（原 3+7 + C4 更新）

- 3 份 `_ext_memo` → registry session_cache
- `_tencent_failures` → registry circuit breaker
- conftest fixture 已提前加入，无需额外测试改动
- **更新 `technical.md` C4**：`_ext_memo: dict` → `DataSourceRegistry.session_cache`

### 第 E 步：集成 + 审计（原 6+8 + C7 修复）

- `fetch_market_data` 写入 session cache
- `_generate_details` 通过 registry 记录成功/失败
- 新增"数据源状态"页签 + HTML 底部摘要
- **必须**在 `registry.py` 注册 `"data_source_status"` 模块（C7 合规）
- `generate_status_report()` 在报告生成结束时调用
- 日志降噪：熔断期间重复失败从 warning 降 debug
- 更新 `technical.md` 同步架构文档

5 步共 **~610 新增 + ~265 修改**，比原 8 轮减少 3 次切换成本，第 B 步即可交付用户可感知收益。
