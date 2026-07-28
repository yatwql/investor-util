# rf-1 批量并行调度迭代计划

> **对应自审**：`rf-1`
> **技术设计**：参见 [`batch-parallel-design.md`](batch-parallel-design.md)
> **状态**：全部完成（dev-verify 1114 ✅ + edge 478 ✅）

---

## 5. 迭代计划

---

### 迭代 1：BatchDispatcher 骨架+辅助方法

**范围**：创建 `batch.py` 核心类、TPE 基本执行单元、辅助方法
**工期**：0.5 天

#### 技术设计

```python
@dataclass
class BatchResult:
    index: int
    success: bool
    result: Any = None
    error: str | None = None
    skipped: bool = False

    def unwrap(self) -> Any:
        if not self.success:
            raise BatchError(f"任务 {self.index} 失败: {self.error}")
        return self.result

class BatchError(Exception):
    pass

class BatchDispatcher:
    def __init__(self, max_workers: int = 4, thread_name_prefix: str = "batch"):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )

    def execute(self, tasks: list[Callable[[], Any]]) -> list[BatchResult]:
        futures = {self._executor.submit(task): i for i, task in enumerate(tasks)}
        results = [None] * len(tasks)
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = BatchResult(index=idx, success=True, result=future.result())
            except Exception as e:
                results[idx] = BatchResult(index=idx, success=False, error=str(e))
                logger.debug("[batch] 任务 %d 异常: %s", idx, e)
        return results

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    @staticmethod
    def successful(results):
        return [r.result for r in results if r.success]

    @staticmethod
    def failures(results):
        return [(r.index, r.error) for r in results if not r.success and r.error]

    @staticmethod
    def all_successful(results):
        return all(r.success for r in results)

    @staticmethod
    def any_failed(results):
        return any(not r.success for r in results)
```

#### 验收标准

- [ ] `execute([sleep(0.2) * 3])` 总耗时 < 0.3s
- [ ] 返回结果按输入顺序排列
- [ ] 空列表 execute([]) 返回空列表
- [ ] `max_workers=1` 退化为串行
- [ ] `successful` / `failures` / `any_failed` 语义正确
- [ ] 线程名前缀可配置，日志可见 `[batch_price]`

#### 测试范围

- **文件**：`test_batch.py`（新建）
- **耗时**：< 10s

#### 风险

**低**。纯新增文件，不影响现有代码。

---

### 迭代 1.5：线程安全审计

**范围**：验证 BatchDispatcher 涉及的共享对象线程安全性
**工期**：0.2 天

#### 审计清单

| 对象 | 锁机制 | 线程安全？ |
|:-----|:-------|:---------|
| DataSourceRegistry | `_provider_lock`(RLock) + `_cache_lock`(RLock) | ✅ |
| DegradationTracker | `_lock`(Lock) | ✅ |
| cache.get/set | 文件级隔离 | ✅（不同 key 不同文件） |
| get_registry() 单例 | `_singleton_lock` 双检锁 | ✅ |
| get_tracker() 单例 | `_tracker_instance_lock` 双检锁 | ✅ |

#### 验收标准

- [ ] 审计清单全部验证通过
- [ ] `batch.py` 头部注释记录线程安全契约

#### 风险

**中**。审计发现隐患必须在本轮修复，不留到后续迭代。

---

### 迭代 2：缓存优先过滤 + 策略感知预检

**范围**：批前检查缓存 + 可选的策略预检钩子（基于 `DataSourceRegistry.get_effective_strategy()`，当前仅行情数据类型适用）
**工期**：0.35 天

#### 技术设计

缓存检查前置到线程池调度之前；同时引入可选的策略预检钩子 `strategy_hook`，各数据类型可传入自己的提前判定逻辑。**仅行情数据类型传入钩子**（基于 `DataSourceRegistry.get_effective_strategy()` 判断非交易时段走缓存），基金排名/行业不传，退化为普通缓存优先。

> **实际调用路径**：`get_effective_strategy()` 是 `provider_registry.py:DataSourceRegistry` 的实例方法（非 `market_value.py` 的模块函数）。行情端在 `_compute_details()` 中通过 `registry.get_effective_strategy(code_type, chain, market_open)` 判断策略。batch 层通过闭包封装此调用。

```python
from src.python.provider_registry import FetchStrategy, get_registry


def get_strategy_hook(code_type: str, chain: list[str] | None = None) -> Callable[[], str] | None:
    """工厂函数：构造策略预检闭包，仅在传入数据类型有策略定义时生效。
    
    当前仅 price_stock/price_index 等行情数据类型有 CACHE_ONLY 策略，
    基金排名/行业/持仓传 None。
    """
    registry = get_registry()
    def _hook() -> str:
        strategy = registry.get_effective_strategy(code_type, chain)
        return strategy.value  # "cache" 或 "live"
    return _hook


class BatchDispatcher:
    def execute_with_cache_check(
        self,
        items: list[tuple[str, Callable]],
        cache_check_fn: Callable[[str], Any],
        *,
        strategy_hook: Callable[[], str] | None = None,
    ) -> list[BatchResult]:
        """缓存优先执行（双层缓存：批前预检 + fetch_with_fallback 内部保底）。

        Args:
            strategy_hook: 可选策略预检，返回 "cache" 时全量走缓存。
                          通过 get_strategy_hook() 工厂函数构造。
                          不传则退化为普通缓存优先。
        """
        if strategy_hook is not None:
            try:
                strategy = strategy_hook()
                if strategy == FetchStrategy.CACHE_ONLY.value:
                    logger.info("[batch] 策略预检=CACHE_ONLY，全量走缓存")
                    return [BatchResult(
                        index=i, success=cache_check_fn(cache_id) is not None,
                        result=cache_check_fn(cache_id),
                    ) for i, (cache_id, _) in enumerate(items)]
            except Exception:
                logger.warning("[batch] 策略预检异常，回退正常执行", exc_info=True)

        results = [None] * len(items)
        pending = []
        for i, (cache_id, task) in enumerate(items):
            cached_value = cache_check_fn(cache_id)
            if cached_value is not None:
                results[i] = BatchResult(index=i, success=True, result=cached_value)
                logger.debug("[batch] 缓存命中: %s", cache_id)
            else:
                pending.append((i, task))

        if pending:
            p_results = self.execute([task for _, task in pending])
            for p_idx, p_r in zip([i for i, _ in pending], p_results):
                results[p_idx] = p_r
        return results
```

> **设计说明**：`strategy_hook` 是可选闭包，只有传入的数据类型才执行策略预检。行情端在 `_compute_details()` 中通过 `get_strategy_hook("a_share")` 构造闭包传入，非交易时段零 HTTP。基金排名/行业不传此钩子，退化为普通缓存优先——它们的更新周期（日/低频）已由 TTL 管理，无需另外的策略层。

#### 验收标准

- [ ] 5 资产 3 缓存命中 → 仅 2 执行线程
- [ ] 传入 `strategy_hook` 且策略=CACHE_ONLY → 0 次 HTTP，全量从缓存返回
- [ ] 策略预检抛异常 → 回退到正常执行（fail-open）
- [ ] 不传 `strategy_hook` → 行为与原有缓存优先完全一致（无策略开销）
- [ ] cache_check_fn 抛异常 → 回退到执行（fail-open）

#### 测试范围

- **文件**：`test_batch.py`（扩展）
- **耗时**：< 10s

---

### 迭代 3：熔断器感知+限速控制+重试接口（含 TD-5）

**范围**：熔断预检 + RateLimiter + 通用重试（`retry_failed` 改为实例方法消除 TD-5）
**工期**：0.5 天

#### 技术设计

**链查询**：走 `DataSourceRegistry.get_chain()` 而非暴露 `chain._get_chain()`。

```python
# provider_registry.py
class DataSourceRegistry:
    def get_chain(self, data_type: str) -> list[str]:
        return list(self._chains.get(data_type, []))
```

**RateLimiter**（Provider 级别请求间隔）：

```python
class RateLimiter:
    def __init__(self, config: dict | None = None):
        self._limits: dict[str, float] = {}
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()
        self._load_config(config or {})

    def acquire(self, provider: str) -> None:
        interval = self._limits.get(provider, 0.0)
        if interval <= 0:
            return
        with self._lock:
            last = self._last_call.get(provider, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < interval:
                time.sleep(interval - elapsed)
            self._last_call[provider] = time.monotonic()
```

**熔断预检 + 重试（TD-5 修复）**：

```python
class BatchDispatcher:
    def execute_with_chain_precheck(
        self, items: list[tuple[str, Callable]], data_type: str,
    ) -> list[BatchResult]:
        """批前预检 Provider Chain 状态。"""
        if not self._registry:
            return self.execute([task for _, task in items])
        chain = self._registry.get_chain(data_type)
        if not chain or self._registry.is_chain_broken(chain):
            logger.warning("[batch:%s] 全链熔断，跳过 %d 个", data_type, len(items))
            return [BatchResult(i, False, skipped=True, error=f"全链熔断:{data_type}")
                    for i in range(len(items))]

    def retry_failed(
        self,
        results: list[BatchResult],
        task_factory: Callable[[int], Callable],
        max_retries: int = 1,
        delay: float = 0.8,
        jitter: float = 0.4,
    ) -> list[BatchResult]:
        """对失败任务重试（复用主 executor，避免 TD-5 线程泄漏）。"""
        import random, time

        failed_indices = [r.index for r in results if not r.success and not r.skipped]
        if not failed_indices:
            return results

        actual_delay = delay + random.uniform(0, jitter)
        logger.info("[batch] 重试 %d 个失败任务（%.1fs 后）", len(failed_indices), actual_delay)
        time.sleep(actual_delay)

        retry_tasks = [task_factory(idx) for idx in failed_indices]
        retry_results = self.execute(retry_tasks)  # ← 复用主 executor，不新建

        for orig_idx, rr in zip(failed_indices, retry_results):
            if rr.success:
                results[orig_idx] = rr
        return results
```

#### 验收标准

- [ ] 全链熔断 → 全部 skipped，0 次 HTTP
- [ ] `registry.get_chain("price_stock")` 返回 `["tencent", "sina"]`
- [ ] RateLimiter：同一 provider 间隔保证
- [ ] **TD-5 修复确认**：`retry_failed` 后 `executor._threads` 数量不增长
- [ ] `retry_failed` 无失败任务时无等待立即返回

#### 测试范围

- **文件**：`test_batch.py`（扩展）+ `test_provider_registry.py`
- **耗时**：< 20s

---

### 迭代 4：降级追踪聚合（含 TD-7）

**范围**：批量执行后多资产降级聚合（`record_aggregated`），含 ratio+severity 防止恶化掩盖（TD-7）
**工期**：0.35 天

#### 技术设计

TD-7 修复：聚合记录增加 `ratio` 和 `severity`，下游消费方可区分小故障与大故障。

```python
@dataclass
class DegradationEvent:
    source_key: str
    tier: str
    success: bool
    failure_type: str
    degraded: bool
    count: int
    effective_threshold: int
    timestamp: float
    detail: dict | None = None  # 新增（可选，向后兼容）


class DegradationTracker:
    def record_aggregated(
        self,
        source_key: str,
        tier: str,
        *,
        failed_count: int,
        total_count: int,
        codes: list[str],
        message: str,
    ) -> None:
        """记录一条聚合降级记录（多条失败压缩为单条）。
        
        TD-7：通过 ratio + severity 区分小故障（3/15）和大故障（15/15）。
        """
        ratio = failed_count / total_count if total_count > 0 else 0.0
        severity = "high" if ratio >= 0.5 else "low"
        
        with self._lock:
            self._events.append(DegradationEvent(
                source_key=source_key,
                tier=tier,
                success=False,
                failure_type="aggregated",
                degraded=True,
                count=failed_count,
                effective_threshold=1,
                timestamp=time.time(),
                detail={
                    "failed_count": failed_count,
                    "total_count": total_count,
                    "ratio": round(ratio, 2),
                    "severity": severity,
                    "message": message,
                },
            ))
            self._persist_dirty = True
```

**调用方使用方式**：

```python
tracker = get_tracker()
tracker.record_aggregated(
    "batch_fund_rank", "T2",
    failed_count=3, total_count=10,
    codes=["000001", "000002", "000003"],
    message="3/10 个基金排名数据不可用",
)
```

#### 文件变更

| 文件 | 操作 |
|:-----|:-----|
| `src/python/report/data_status.py` | 修改 — DegradationEvent.detail、record_aggregated |
| `src/test/unit/report/test_data_status.py` | 修改 — 聚合+ratio+severity 测试 |

#### 验收标准

- [ ] `record_aggregated(failed_count=3, total_count=15)` → `detail.ratio=0.2, severity="low"`
- [ ] `record_aggregated(failed_count=15, total_count=15)` → `detail.ratio=1.0, severity="high"`
- [ ] 0 个资产失败调用方不调用 record_aggregated
- [ ] 现有 `DegradationEvent` 无 `detail` 时完全向后兼容

#### 测试范围

- **文件**：`test_data_status.py`
- **耗时**：< 10s

---

### 迭代 5：fund.py + penetration.py 批量集成

**范围**：`fund.py` 新增批量方法 + `penetration.py` 的基金持仓获取切换为批量
**工期**：0.8 天

#### 技术设计

```python
# fetcher/fund.py 新增
def fetch_fund_rankings_batch(
    fund_codes: list[str],
    dispatcher: BatchDispatcher | None = None,
) -> dict[str, dict]:
    """批量获取基金排名数据。"""
    own = dispatcher is None
    if dispatcher is None:
        dispatcher = BatchDispatcher(max_workers=3, thread_name_prefix="batch_fund_rank")
    items = [(code, partial(fetch_fund_rankings, code=code)) for code in fund_codes]
    results = dispatcher.execute_with_cache_check(
        items,
        cache_check_fn=lambda code: cache_get(f"fund_perf_{code}", get_ttl("rank", f"fund_perf_{code}")),
    )
    rank_map = {}
    for code, r in zip(fund_codes, results):
        if r.success and r.result:
            rank_map[code] = r.result
    if own:
        dispatcher.shutdown()
    return rank_map


def fetch_fund_holdings_batch(
    fund_codes: list[str],
    dispatcher: BatchDispatcher | None = None,
) -> dict[str, dict]:
    """批量获取基金持仓数据。"""
    own = dispatcher is None
    if dispatcher is None:
        dispatcher = BatchDispatcher(max_workers=3, thread_name_prefix="batch_fund_hold")
    items = [(code, partial(fetch_fund_holdings_cached, code=code)) for code in fund_codes]
    results = dispatcher.execute_with_cache_check(...)
    hold_map = {}
    for code, r in zip(fund_codes, results):
        if r.success and r.result:
            hold_map[code] = r.result
    if own:
        dispatcher.shutdown()
    return hold_map
```

**penetration.py 集成**：`_merge_fund_layer()` 中的串行 `fetch_fund_holdings(fund.code)` 改为：

```python
def _merge_fund_layer(funds, detail_map):
    merged = {}
    fund_codes = [f.code for f in funds]
    holdings_batch = fetch_fund_holdings_batch(fund_codes)
    for fund in funds:
        holdings_data = holdings_batch.get(fund.code)
        # ... 原有处理逻辑不变
```

#### 验收标准

- [ ] 10 基金排名使用 BatchDispatcher 3 workers，结果与串行 1:1 一致
- [ ] 10 基金持仓使用 BatchDispatcher 3 workers，结果与串行 1:1 一致
- [ ] C6 合规：每基金仍经过 `fetch_with_fallback()`
- [ ] C4 合规：`fetch_fund_holdings_batch` 使用 `fetch_fund_holdings_cached`（含 session_cache）
- [ ] `max_workers` 通过 `batch.fund_workers` 配置可调

#### 测试范围

- **文件**：`test_fund.py`（扩展）+ `test_penetration.py`（扩展）
- **耗时**：< 30s

#### 风险

**中。** penetration.py 在穿透计算中途切换为批量 + 后续再将数据分组，需验证 `_merge_fund_layer` 的 `funds` 顺序与 `holdings_batch` 匹配。

---

### 迭代 6：fund 消费者串行→批量切换（含 TD-8）

**范围**：将两个串行调用 `fetch_fund_rankings()` 的消费者同时改为批量（TD-8）
**工期**：0.4 天

#### 技术设计

**`fund_performance.py:229`（Excel 管线）**：

```python
# 当前（串行）
for idx, fund in enumerate(fund_holdings_sorted, 1):
    rating = _write_one_fund_row(ws, row, fund, detail_map)

# 优化：批量获取打底 + 逐行写入保持原有逻辑
fund_codes = [f.code for f in fund_holdings_sorted]
rank_batch = fetch_fund_rankings_batch(fund_codes)
for fund in fund_holdings_sorted:
    rating = _write_one_fund_row(ws, row, fund, detail_map, prefetched_rank=rank_batch.get(fund.code))
```

**`html_builders.py:130`（HTML 管线）**：

```python
# 当前（串行）
perf_data = fetch_fund_rankings(fund.code)

# 优化：同 type 的 fund 一次性批量获取
```

**设计要点**：`_write_one_fund_row` 签名不改（向后兼容），允许传入可选 `prefetched_rank` 参数。`prefetched_rank=None` 时退化为内部 `fetch_fund_rankings` 调用。

#### 文件变更

| 文件 | 操作 |
|:-----|:-----|
| `src/python/report/fund_performance.py` | 修改 — 循环前一次批量获取 |
| `src/python/report/html_builders.py` | 修改 — 循环前一次批量获取 |
| `src/test/unit/report/test_fund_performance.py` | 修改 — 批量场景 |
| `src/test/unit/report/test_html_builders.py` | 修改 — 批量场景 |

#### 验收标准

- [ ] `fund_performance.py` 中的串行循环改为调用 `fetch_fund_rankings_batch()` 一次 + 遍历 consumer
- [ ] `html_builders.py` 中的串行循环同上
- [ ] 批量结果与串行结果 1:1 一致
- [ ] `_write_one_fund_row` 签名不变（向后兼容）
- [ ] 降级场景：批量部分失败 → 失败基金使用空数据写入（不抛异常）

#### 测试范围

- **文件**：`test_fund_performance.py` + `test_html_builders.py`
- **耗时**：< 25s

#### 风险

**中。** 两处消费者分别属于 Excel 和 HTML 管线，测试需 mock 完整的报告上下文。**特别注意**：`html_builders.py` 在 `build_html_content()` 调用链中，TuiProgressReporter 需 mock。

---

### 迭代 7：industry.py 批量统一重构

**范围**：`batch_fetch_industry_data()` 重构为 BatchDispatcher + 通用 `retry_failed`
**工期**：0.3 天

#### 技术设计

```python
def batch_fetch_industry_data(codes: list[str], max_workers: int = 8) -> dict[str, dict]:
    """批量获取行业数据（统一 BatchDispatcher 实现）。"""
    valid_codes = _validate_and_filter_codes(codes)
    if not valid_codes:
        return {}

    chain_broken = is_provider_chain_broken("industry")
    if chain_broken:
        logger.warning("[industry] 全链熔断，跳过 %d 个代码", len(valid_codes))
        return {}

    dispatcher = BatchDispatcher(max_workers=max_workers, thread_name_prefix="batch_industry")
    items = [(code, partial(fetch_industry_data, code=code)) for code in valid_codes]
    results = dispatcher.execute_with_cache_check(items, cache_check_fn=...)

    results = dispatcher.retry_failed(
        results,
        task_factory=lambda idx: partial(fetch_industry_data, code=valid_codes[idx]),
        delay=_BATCH_RETRY_DELAY, jitter=_BATCH_RETRY_JITTER,
    )

    result_map = {}
    for code, r in zip(valid_codes, results):
        if r.success and r.result:
            result_map[code] = r.result
    dispatcher.shutdown()
    return result_map
```

#### 验收标准

- [x] 返回结果与重构前 1:1 一致（41 tests ✅）
- [x] 缓存优先 + 熔断预检 + 非 A 股过滤 + 重试逻辑全部保留
- [x] 函数签名不变（`batch_fetch_industry_data(codes, max_workers=8)`）

#### 测试范围

- **文件**：`test_industry.py`
- **耗时**：< 20s

#### 风险

**低。** 保留原有全部逻辑，只替换 TPE 底层。

---

### 迭代 8a：池配置与线程上限（含 TD-4）

**范围**：注册管线 Dispatcher 配置，全局线程硬上限
**工期**：0.2 天

#### 技术设计

TD-4 修正：上限 15（已有池不计入 batch 配额）。按实际管线计算：

| 池 | workers | 配置键 |
|:---|:--------|:-------|
| 基金排名/持仓（新增） | 3 | `batch.fund_workers` |
| 行业（新增） | 8 | `batch.industry_workers` |
| **batch 合计上限** | **15** | `batch.max_total_workers` |
| orch_prep（已有） | 2 | 不动 |
| orch_llm_news（已有） | 2 | 不动 |
| cache_ops（已有） | 4 | 不动 |

---

### 迭代 8b：管线集成验证

**范围**：orchestrator 管线使用 BatchDispatcher，多批量同时运行无冲突
**工期**：0.5 天

#### 管线依赖图（实际调用链）

> ⚠️ **校正说明**：原计划误标为"三项可并行"。实际调用链中 penetration 内部基金持仓→行业为**串行**（同属 `compute_penetration_top10()`），基金排名在渲染阶段独立执行。*收益不受影响*——节省的时间叠加而非并发。

```
prepare_report_data()
    ├── 获取持仓
    ├── _generate_details 行情 (已有 TPE 8w，不动)    ~14s
    ├── 指数 orch_prep (已有 TPE 2w，不动)              ~2s
    ├── compute_penetration_top10():                    ~20s
    │   ├── _merge_fund_layer:
    │   │   └── [TPE 3] fund 持仓批量  ──── 等待 3s  ← 迭代5
    │   ├── 股票层处理                   ──── 等待 2s
    │   ├── _enrich_with_industry_api:
    │   │   └── [TPE 8] industry 批量  ──── 等待 8s  ← 迭代7
    │   └── 分类/排序                   ──── 等待 7s
    ├── 组合校准/量化指标                                15s
    └── prepare_report_data() return ─── 此时 ~49s

LLM+新闻 (已有 TPE 2w，并行)                            15s
快照捕获 (prepare_report_data 数据就绪后开始)

──────── 渲染阶段 ────────
Excel 生成:
  └── fund_performance.py:
      └── [TPE 3] fund 排名批量  ──── 等待 3s  ← 迭代6
      └── Excel 渲染 (CPU)                             8s

HTML 生成:
  └── html_builders.py:
      └── [文件缓存命中] fund 排名批量  ──── 等待 1s  ← 迭代6
      └── HTML 渲染 (CPU)                              8s

full 路径合计: ~84s → ~67s (-20%)
```

#### 验收标准

- [x] 全管线运行无死锁/线程泄漏
- [x] `max_total_workers=15` 硬上限生效（配置读取 + 钳位逻辑已验证）
- [x] 管线结束时无残留线程（所有 Dispatcher 均已 shutdown）
- [x] C19 pipeline_data Schema 无损

#### 测试范围

- **文件**：`test_pipeline_smoke.py`
- **耗时**：< 60s

---

### 迭代 9：性能验证与边缘场景

**范围**：运行性能基准验证 + 边缘场景测试
**工期**：0.5 天

#### 关键指标

| 指标 | 当前 | 目标 |
|:-----|:-----|:-----|
| full 路径总耗时 | ~84s | ≤ 67s |
| 基金排名加持仓获取耗时 | ~18s | ≤ 8s |
| 行业获取耗时 | ~15s | ≤ 10s |
| 串行 IO 占比 | ~39% | ≤ 22% |

#### 边缘场景（test_batch_edge.py，C12 合规）

| # | 场景 | 预期 |
|--|------|------|
| 1 | 空持仓 | 空 dict，0 HTTP |
| 2 | 单持仓 | 结果正确 |
| 3 | 全部缓存命中 | 0 线程池调度 |
| 4 | 全部 Provider 熔断 | 全部 skipped |
| 5 | 混合：缓存+熔断+失败+成功 | 各自对应 |
| 6 | max_workers=1 退化串行 | 结果一致 |
| 7 | 并发安全：重复资产 | C4 去重 |
| 8 | 线程泄漏（TD-5 验证） | 100 次批量后线程数稳定 |
| 9 | 大品种 100 资产 | 不 OOM |
| 10 | 内存释放 | 无循环引用 |

#### 验收标准

- [ ] `perf_view.py` 显示 full 路径 **≤ 67s**（≥20% 提升）—— 需实际运行报告验证（mock 环境无法测 IO 耗时）
- [x] C12：边缘测试在 `test_batch_edge.py`
- [x] C11：标记 `@pytest.mark.edge` + `@pytest.mark.unit_providers`
- [x] `dev-verify` 门禁通过（1114 passed ✅）
- [x] edge 门禁通过（478 passed ✅）

---

### 6.2 迭代依赖关系图

```
迭代 1 (骨架+辅助方法)          0.5d
  ↓
迭代 1.5 (线程安全审计)          0.2d
  ↓
迭代 2 (缓存优先过滤+策略钩子)   0.35d
  ↓
迭代 3 (熔断+限速+重试 TD-5)    0.5d
  ↓
迭代 4 (降级聚合 TD-7)          0.35d
  ↓
迭代 5 (fund+penetration 批量)  0.8d
  ↓
迭代 6 (fund 消费者切换 TD-8)   0.4d
  ↓
迭代 7 (industry 重构)          0.3d
  ↓
迭代 8a (池配置 TD-4)          0.2d
  ↓
迭代 8b (管线集成验证)          0.5d   ← 依赖 5-7 完成
  ↓
迭代 9 (性能验证+边缘)          0.5d   ← 依赖 8b 完成
                              ─────
合计: 9 轮 = 4.10-4.60d
```

### 6.4 测试命令速查

```bash
# 迭代 1-3（batch 核心层）
pytest src/test/unit/fetcher/test_batch.py -v --tb=short

# 迭代 4（降级聚合）
pytest src/test/unit/report/test_data_status.py -v --tb=short

# 迭代 5（fund/penetration 批量）
pytest src/test/unit/fetcher/test_fund.py -v --tb=short
pytest src/test/unit/report/test_penetration.py -v --tb=short

# 迭代 6（fund 消费者切换）
pytest src/test/unit/report/test_fund_performance.py -v --tb=short
pytest src/test/unit/report/test_html_builders.py -v --tb=short

# 迭代 7（industry 重构）
pytest src/test/unit/fetcher/test_industry.py -v --tb=short

# 迭代 8b（管线集成）
pytest src/test/integration/test_pipeline_smoke.py -v --tb=short

# 迭代 9（边缘场景）
pytest src/test/unit/fetcher/test_batch_edge.py -v --tb=short

# 门禁
python scripts/test_runner.py --mode dev-verify
```
