# A5 迭代计划：测试运行时可扩展性优化

创建日期：2026-07-04
状态：待评审

---

## 1. 问题陈述

### 1.1 当前状态

| 测试模式 | 项数 | 耗时 | 用途 |
|:---------|:----:|:----:|:------|
| `smoke` | 24 | ~2s | 开发快速验证 |
| `regression` | 222 | ~32s | 提交前门禁（P0） |
| `verify` | 839 | **~12min** | 合并前门禁（P1） |
| `unit` | 1998 | **~25min** | 全量单元测试 |
| `all` | 2244 | **~26min** | 发布前门禁（P2） |

### 1.2 瓶颈定位

按标记分组的测试分布：

| 标记 | 项数 | 估算耗时 | 说明 |
|:-----|:----:|:--------:|:-----|
| `unit_report` | 672 | ~9min | 报告生成（最重） |
| `unit_llm` | 337 | ~1min | LLM 模块（纯 mock，约 4-6s） |
| `unit_core` | 307 | ~4min | 核心基础设施 |
| `unit_news` | 177 | ~90s | 新闻模块 |
| `unit_providers` | 167 | ~5min | 数据源提供商 |
| `unit_fetcher` | 146 | ~4min | 数据获取调度 |
| `unit_ui` | 143 | ~60s | TUI 交互 |
| `unit_config` | 56 | ~20s | 配置管理 |
| `scenario` | 222 | ~32s | 业务场景（快速） |
| `unit` **合计** | **1998** | **~25min** | |

### 1.3 根因分析

1. **顺序单线程执行** — `pytest` 默认单进程单线程，无法利用多核 CPU（本机 8 核）
2. **超大测试文件导致颗粒度不均** — `test_market_value.py`（1918 行）、`test_llm.py`（2040 行）各含数百项测试，即使多线程也无法拆分
3. **verify 模式覆盖过宽** — 839 项包含 `unit_core` + `unit_providers` + `unit_fetcher`，其中 provider 和 fetcher 涉及大量 mock HTTP 调用
4. **全量报告写入测试串行** — `unit_report` 672 项中包含大量 `openpyxl` 工作簿写入（I/O 密集型），单线程下拖累明显

---

## 2. 需求分析

### 2.1 用户需求（开发者视角）

| 角色 | 操作 | 当前体验 | 目标体验 |
|:-----|:-----|:---------|:---------|
| 开发者 | 提交前 `--mode regression` | ~32s ✅ | 保持 < 60s |
| 开发者 | 合并前 `--mode verify` | ~12min ❌ | < **3min** |
| 开发者 | 发布前 `--mode all` | ~26min ❌ | < **8min** |
| 开发者 | 修改 report 模块后快速验证 | 无快速模式 | 新增 `--mode report` < 60s |
| 开发者 | 本地开发反复运行 | 盲目跑全量 | 增量测试仅运行受影响项 |

### 2.2 非功能需求

| 维度 | 要求 |
|:-----|:------|
| 正确性 | 并行/增量方案不遗漏测试、不误报通过 |
| 兼容性 | 现有 MODES 定义、test_runner.py CLI、CI 调用不变 |
| 可维护性 | 新增依赖（如 pytest-xdist）需评估维护成本 |
| 可靠性 | 并行方案下测试隔离（mock 不共享状态） |

### 2.3 约束条件

- 测试代码全部为 mock 测试（无需真实 API），理论上无共享资源冲突
- 保留对 Windows 环境的兼容性（pytest-xdist 在 Windows 上工作正常）
- 不降低现有测试覆盖率

---

## 3. 详细设计

### 3.1 方案总览：四管齐下

```
┌─────────────────────────────────────────────────────────────────┐
│  A5 测试运行时可扩展性优化                                      │
├─────────────────────────────────────────────────────────────────┤
│  Phase 1: 并行执行（pytest-xdist）          预期：3x-6x 加速   │
│  Phase 2: 超大测试文件拆分                   预期：提升并行度   │
│  Phase 3: 增量测试（git-aware）             预期：本地 10s 级  │
│  Phase 4: 新的快速 verify 子模式            预期：2-3min       │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3.2 Phase 1：并行执行（pytest-xdist）

#### 3.2.1 变更说明

引入 `pytest-xdist` 实现 CPU 级并行，`test_runner.py` 为指定 mode 启用 `-n auto`（自动使用所有 CPU 核心）。
需要注意 `-n auto` 检测的是**逻辑核数**（超线程下翻倍），对于 openpyxl I/O-bound 测试，16 worker 争抢 IO 反而比 8 worker 慢。因此 `parallel: True` 实际使用 `max(1, cpu_count // 2)`。

#### 3.2.2 核心设计

```python
# test_runner.py MODES 新增 parallel 字段
MODES = {
    "unit": {
        "marker": "unit",
        "desc": "全量单元测试",
        "timeout_sec": 720,       # 从 1800 下调（预期 5min + 20% buffer）
        "order": 1,
        "parallel": True,         # ✅ 新增（True = max(1, cpu_count//2), 也可指定进程数如 4）
    },
    # ...
}
```

`_build_pytest_args` 逻辑：

```python
parallel = mode_cfg.get("parallel", False)
if parallel:
    if parallel is True:
        workers = max(1, os.cpu_count() // 2)  # 超线程减半，防 IO 争抢
    else:
        workers = str(parallel)
    args.extend(["-n", str(workers)])
```

> ⚠️ **为什么不是 `-n auto` 直接翻倍？**
> 测试以 `openpyxl` I/O-bound 写入为主，逻辑核数翻倍（16 worker）会导致 IO 争抢加剧、切换成本上升。
> 实测经验：`cpu_count // 2`（物理核数）在 I/O-bound 工作负载下吞吐最优。
> 如遇 IO 争抢降速，可手动指定 `parallel: 4` 进一步压减。

#### 3.2.3 预期加速

| 模式 | 当前 | 8 核预期 | 加速比 |
|:-----|:----:|:--------:|:------:|
| unit | 25min | **4-6min** | 4-6x |
| verify | 12min | **2-3min** | 4-6x |
| all | 26min | **5-8min** | 3-5x |

#### 3.2.4 隔离性验证

- ✅ 所有 LLM 测试使用 mock，无真实 API 调用
- ✅ 报告测试使用 `openpyxl` `Workbook()`（线程安全，各写各的文件）
- ✅ 缓存测试使用独立临时目录
- ⚠️ `conftest.py` 中的模块级 fixture 需审核作用域（`session` → `module`）
- ⚠️ 文件系统测试（`test_filesystem_edge.py`）操作真实文件，需避免并发冲突
- ⚠️ openpyxl 测试需确认使用 `tmp_path`（pytest 内置，进程隔离），而非固定路径

#### 3.2.5 回退机制

```python
try:
    import xdist  # noqa: F401
    HAS_XDIST = True
except ImportError:
    HAS_XDIST = False
    # 无 xdist 时 fallback 到单线程
```

#### 3.2.6 变更文件

| 文件 | 变更 |
|:-----|:------|
| `scripts/test_runner.py` | MODES 新增 `parallel` 字段；`_build_pytest_args` 处理 `-n auto`；检测 xdist 安装 |
| `pyproject.toml` | 新增 `pytest-xdist` 到可选依赖 |
| `src/test/conftest.py` | 审核 fixture scope，确保并行安全 |
| `docs-stm/managements/test-coverage.md` | 更新耗时预期 |

---

### 3.3 Phase 2：超大测试文件拆分

#### 3.3.1 拆分目标

拆分最大的测试文件以提升并行颗粒度：

| 源文件 | 行数 | 拆分方案 | 目标文件数 |
|:-------|:----:|:---------|:---------:|
| `test_market_value.py` | 1918 | 按函数域拆分为 `_classify` / `_details` / `_sheet_writer` | 3 |
| `test_llm.py` | 2040 | 按模块拆分为 `_api` / `_session` / `_generators` / `_fingerprint` | 4 |
| `test_cache.py` | 1361 | 拆分为 `_core` / `_edge` / `_ttl` / `_concurrency` | 3 |
| **`test_html_template.py`** | **438** | 新增文件独立存放；B 系列 4 个页签的渲染测试写入此文件（不新增文件） | **1（不拆分，仅作为跨迭代共存热点标记）**|
| `test_fund_performance.py` | 975 | 暂不拆分（排名+评级逻辑高度耦合） | 1 |
| `test_summary.py` | 892 | 暂不拆分 | 1 |

#### 3.3.2 拆分原则

1. 拆分为 `test_<module>_<domain>.py` 模式，如 `test_market_value_classify.py`
2. 每个子文件独立生效，保留原有 `@pytest.mark` 标记
3. `__init__.py` 不变
4. 共享 fixture 迁移到测试类内部或提升到 `conftest.py`
5. 拆分后确保 `pytest src/test/ -m "unit_report"` 仍能收集到所有测试

#### 3.3.3 变更文件

| 文件 | 变更类型 |
|:-----|:---------|
| `src/test/unit/report/test_market_value_classify.py` | 新增（原文件 ~600 行剥离）|
| `src/test/unit/report/test_market_value_details.py` | 新增（原文件 ~700 行剥离）|
| `src/test/unit/report/test_market_value_sheet.py` | 新增（原文件 ~500 行剥离）|
| `src/test/unit/report/test_market_value.py` | 保留骨架 + 公共 fixture（~118 行）|
| `src/test/unit/llm/test_llm_api.py` | 新增 |
| `src/test/unit/llm/test_llm_session.py` | 新增 |
| `src/test/unit/llm/test_llm_generators.py` | 新增 |
| `src/test/unit/llm/test_llm_fingerprint.py` | 新增 |
| `src/test/unit/llm/test_llm.py` | 保留骨架 |
| `src/test/unit/core/test_cache_core.py` | 新增 |
| `src/test/unit/core/test_cache_edge.py` | 新增 |
| `src/test/unit/core/test_cache_ttl.py` | 新增 |
| `src/test/unit/core/test_cache_concurrency.py` | 新增 |
| `src/test/unit/core/test_cache.py` | 保留骨架 |

#### 3.3.4 标记继承

所有拆分后的子文件继承父文件标记（`unit_report` / `unit_llm` / `unit_core`），无需新增标记。

---

### 3.4 Phase 3：增量测试（git-aware）

#### 3.4.1 方案选择

对比三种方案：

| 方案 | 原理 | 优点 | 缺点 |
|:-----|:-----|:-----|:------|
| **A) pytest-testmon** | 基于覆盖率数据自动检测受影响的测试 | 零配置、精确 | 需初始种子运行，依赖 .testmon 数据文件 |
| **B) pytest-incremental** | 基于文件修改时间 + import 图 | 无额外依赖 | 准确度不如 testmon |
| **C) 自定义 git diff → marker** | git diff 识别变更文件，映射到 marker | 透明可控 | 需维护映射表 |

**推荐：方案 C（自定义 git-aware）为主，方案 A（testmon）为备选**

#### 3.4.2 自定义 git-aware 设计

```python
# scripts/test_runner.py 新增 --changed 参数

def _get_changed_marker() -> str | None:
    """从 git diff 推断应运行的测试标记。

    Returns:
        pytest -m 表达式字符串，无变更时返回 None
    """
    # 选择基准分支：origin/main → main → HEAD~1
    for branch in ["origin/main", "main", "HEAD~1"]:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            break
    else:
        return None  # 无法确定基准分支，跳过增量

    result = subprocess.run(
        ["git", "diff", "--name-only", f"{branch}..."],
        capture_output=True, text=True
    )
    changed = result.stdout.strip().splitlines()
    if not changed or (len(changed) == 1 and changed[0] == ""):
        return None

    # 文件 → 标记映射
    FILE_TO_MARKER = {
        "src/python/providers/": "unit_providers or unit_fetcher",
        "src/python/fetcher/": "unit_fetcher",
        "src/python/report/": "unit_report",
        "src/python/llm/": "unit_llm",
        "src/python/cache.py": "unit_core",
        "src/python/models.py": "unit_core",
        "src/python/reader.py": "unit_core",
        "src/python/config.py": "unit_config",
        "src/python/tui": "unit_ui",
        "src/test/": "__TEST_ONLY__",  # 仅测试文件变更 → 运行对应域
        "src/python/": "__SOURCE__",   # 兜底：源文件变更未匹配 → 跑 unit
    }

    markers = set()
    has_unmatched_source = False

    for f in changed:
        matched = False
        for prefix, marker in FILE_TO_MARKER.items():
            if f.startswith(prefix):
                if marker == "__TEST_ONLY__":
                    pass  # 仅测试变更，由调用方决定模式
                elif marker == "__SOURCE__":
                    has_unmatched_source = True
                else:
                    markers.add(marker)
                matched = True
                break
        if not matched and f.startswith("src/"):
            has_unmatched_source = True

    if not markers and has_unmatched_source:
        return "unit"          # 兜底：无法映射的源文件变更 → 跑全量 unit
    if not markers:
        return None            # 仅 docs/data 等无关文件变更
    if has_unmatched_source:
        markers.add("unit")    # 有映射匹配 + 未识别源文件 → unit 兜底确保不漏
    return " or ".join(sorted(markers))
```

#### 3.4.3 testmon 备选方案

```bash
# 种子运行（首次）
pytest src/test/ --testmon

# 后续增量运行（仅受影响的测试）
pytest src/test/ --testmon -m "not edge"
```

#### 3.4.4 变更文件

| 文件 | 变更 |
|:-----|:------|
| `scripts/test_runner.py` | 新增 `_get_changed_marker()`；`main()` 处理 `--changed` 参数 |
| `pyproject.toml` | 可选新增 `pytest-testmon` |

---

### 3.5 Phase 4：新增快速 verify 子模式（条件执行）

> **前置依赖**：Phase 1（并行）+ Phase 2（拆分）完成后，实测 `verify` 模式耗时仍 > 3min 才实施。
> 若 Phase 1+2 后 `verify` 已达标（预计 < 3min），则 `verify_fast` 冗余跳过，仅实施 `report` 模式。

#### 3.5.1 新模式定义（按需启用）

```python
MODES = {
    # ... 现有模式 ...
    "verify_fast": {
        "marker": "unit_core or unit_llm or unit_config",
        "desc": "快速合入验证（核心+LLM+配置 ~700 项，预期 ~2min）",
        "timeout_sec": 300,
        "order": 5,
        "parallel": True,
    },
    "report": {
        "marker": "unit_report",
        "desc": "仅报告模块测试（672 项，开发期快速验证报告变更）",
        "timeout_sec": 180,
        "order": 11,
        "parallel": True,
    },
}
```

- `verify_fast` **仅当 Phase 1+2 后 `verify` 仍 > 3min 才启用**，否则砍掉减少模式认知负担
- `verify_fast` 的 marker 为 `unit_core or unit_llm or unit_config`（纯单元），不混入 `scenario`
- `verify` 保留不变，CI 中作为更严格的提交前检查
- `report` 模式无条件启用，为 report 模块开发者提供快捷入口

#### 3.5.2 gate 推荐更新（按 Phase 1+2 后实测结果决策）

| 门禁 | 当前 | 推荐（Phase 1+2 后） |
|:-----|:-----|:---------------------|
| P0（提交前） | `regression` ~32s | 不变 |
| P1（合并前） | `verify` ~12min | `verify` ~3min（并行后）或 `verify_fast` ~2min（如果保留）|
| P2（发布前） | `all` ~26min | `all` ~5-8min（并行后）|

---

## 4. 预期收益汇总

| 指标 | Phase 1（并行） | Phase 2（拆分） | Phase 3（增量） | Phase 4（新模式）† |
|:-----|:---------------:|:---------------:|:---------------:|:-----------------:|
| `unit` | 25min → **4-6min** | 稳定 4-6min | 增量 10-30s | — |
| `verify` | 12min → **2-3min** | 2-3min | — | †**~2min** |
| `all` | 26min → **5-8min** | 5-8min | — | — |
| 本地开发 | — | — | **git 感知 10s 级** | 新增 report 模式 **~60s** |

† `verify_fast` **有条件启用**：Phase 1+2 完成后实测 `verify` > 3min 才实施；否则跳过。
   `report` 模式无条件启用。

---

## 4.5 Phase 目标与回退

每个 Phase 必须有明确的成功标准和回退路径，在进入下一 Phase 前确认。

### Phase 1：并行执行（pytest-xdist）

| 维度 | 内容 |
|:-----|:------|
| **目标** | `verify` 模式从 12min 降至 **< 3min**；`unit` 模式从 25min 降至 **< 6min**；`all` 降至 **< 8min** |
| **成功标志** | `test_runner.py --mode unit` 0 failed，耗时 < 720s；日志明确输出 `-n auto` |
| **失败回退** | 卸载 `pytest-xdist` 即完全恢复单线程；`_check_xdist()` 检测不到时自动降级，零代码变更 |
| **进入下一 Phase 前提** | Phase 1 目标达成 |

### Phase 2：超大测试文件拆分

| 维度 | 内容 |
|:-----|:------|
| **目标** | 3 个大文件（1918+2040+1361 行）拆为 13 个子文件，拆分后 `pytest src/test/ --collect-only -q -m "unit"` 收集数 = **1998**（与拆分前一致）|
| **成功标志** | 每个子标记 `unit_report`(672)/`unit_llm`(337)/`unit_core`(307) 收集数分别等于拆分前；`python test_runner.py --mode unit` 0 failed |
| **失败回退** | 任一子文件收集数不匹配 → 删除该子文件，恢复原始文件；全标记汇总不匹配 → `git revert` 整个拆分 commit |
| **进入下一 Phase 前提** | Phase 2 目标达成 |

### Phase 3：增量测试（git-aware）

| 维度 | 内容 |
|:-----|:------|
| **目标** | `test_runner.py --changed` 根据 git diff 自动推导 marker 并运行对应测试；修改 `report/` → 运行 `unit_report`；修改 `providers/` → 运行 `unit_providers or unit_fetcher`；无变更 → 跳过 |
| **成功标志** | (1) `--changed` 映射准确率 100%（测试覆盖 5 种 diff 场景）<br>(2) 增量运行项数 **< 全量 50%** |
| **失败回退** | `--changed` 映射错误 → 不使用 `--changed` 参数即恢复全量运行；`_get_changed_marker()` 输出 None 时自然回退到指定模式 |
| **进入下一 Phase 前提** | C1~C3 步骤全部通过 |

### Phase 4：新增快速子模式（条件执行）

| 维度 | 内容 |
|:-----|:------|
| **前置条件** | Phase 1+2 完成后，实测 `verify` 仍 > 3min 才启；否则仅实施 `report` 模式 |
| **目标** | `verify_fast` 模式 **< 3min**，`report` 模式 **< 90s** |
| **成功标志** | `python test_runner.py --mode verify_fast` 0 failed，耗时 < 180s；`python test_runner.py --mode report` 0 failed，耗时 < 90s |
| **失败回退** | 新模式不达预期 → 保留原有模式，文档注明"beta 阶段"；完全不可用 → `git revert` 该步骤 commit，旧模式不受影响 |
| **进入下一 Phase 前提** | Phase 4 目标达成 |

### 全迭代最终目标

`verify_fast` < 3min（P1 门禁），`smoke` < 5s，`all` < 8min（P2 门禁）

---

## 5. 依赖评估

### 5.1 新增依赖

| 包 | 用途 | 安装大小 | 风险 |
|:---|:------|:--------:|:----:|
| `pytest-xdist` | 并行测试执行 | ~200KB | ⚠️ Windows 需 `psutil` 或 `py` |
| `pytest-rerunfailures` | flaky 测试重试（`test_cache_concurrency` 使用）| ~50KB | 低 |

### 5.2 兼容性

- `pytest-xdist 3.x` 支持 `pytest 7+`（当前 8.3.4，兼容）
- `pytest-xdist` 的 `--forked` 选项在 Windows 上受限，使用 `-n auto`（进程池）即可
- Windows 上 `-n` 使用 `spawn` 启动方式，所有测试文件需保证模块级导入安全（已在 `conftest.py` 中内置 import 保护）

---

## 6. 实施步骤（拆细为 17 个原子步）

### 6.1 依赖与基础设施（7 步）

```
Step A0 ──→ Step A1 ──→ Step A2 ──→ Step A2a ──→ Step A3 ──→ Step A3b ──→ Step A3c
(基线录制)  (pyproject)  (fixture审计)  (检查点)    (test_runner)  (单线程确认)  (加速比门)
                                          │
                                     Δ ≤ 5 OK? ──→ ⛔ 暂停/改道
```

#### Step A0：录制变更前基线

| 字段 | 值 |
|:-----|:----|
| **目标** | 实测各模式耗时精确基线（warmup + 去 3 次取中位数），写入 test-coverage.md |
| **文件** | `docs-stm/managements/test-coverage.md` |
| **操作** | (1) **先跑 1 次 warmup**（`python test_runner.py --mode unit`），结果不计入，仅预热文件系统缓存 <br>(2) 再正式跑 `python test_runner.py --mode smoke` / `regression` / `verify` / `unit` / `all` 各 3 次 <br>(3) 去 3 次取中位数记录到 test-coverage.md <br>(4) 标记为"A5 优化前基线"，注明 warmup 后的中位数 |
| **验证** | test-coverage.md 基线数据完整，各模式耗时 ±10% 内合理 |
| **预期产出** | commit: "docs: 录制 A5 优化前测试耗时基线" |
| **回滚** | `git revert` 该 commit；原始耗时在 git 历史中完好 |

#### Step A1：添加 pytest-xdist 依赖

| 字段 | 值 |
|:-----|:----|
| **目标** | `pyproject.toml` 声明 pytest-xdist 依赖，安装后 `pytest -n auto` 可用 |
| **文件** | `pyproject.toml` |
| **操作** | 在 `[project.dependencies]` 或 `[project.optional-dependencies]` 中新增 `pytest-xdist>=3.6` |
| **验证** | `pip install -e .` 后 `pytest src/test/ -n auto --collect-only -q` 不报错 |
| **回滚** | `git revert` 该 commit |

#### Step A2：审计 conftest.py fixture scope + tmpdir

| 字段 | 值 |
|:-----|:----|
| **目标** | 确认所有 session/module scope fixture 在 xdist 多进程下安全，不安全项限期整改 |
| **文件** | `src/test/conftest.py`, `src/test/unit/conftest.py` |
| **操作** | (1) 扫描所有 `@pytest.fixture(scope="session")` 和 `@pytest.fixture(scope="module")`，确认 fixture 产生或修改的对象不跨进程共享。
> **注意**：xdist 的 `-n auto` 模式下每个 worker 进程独立运行自己的 session/module fixture，scope="session" 的 fixture 不会被跨 worker 共享复用，而是在每个 worker 中各执行一次。这意味着：
> - 如果有 session fixture 创建临时目录，不同 worker 通过硬编码路径隐式依赖 → 竞态
> - 所有涉及文件系统的 fixture **必须** 使用 `tmp_path`（每个 worker 各自独立的临时目录）
> - fixture 不得依赖 worker 间共享状态（全局变量、固定文件名）

(2) 重点检查：缓存临时目录、mock 单例、openpyxl Workbook、固定路径写入（强制改用 `tmp_path`）<br>(3) 运行 `pytest src/test/ -n 2` 收集 warning，逐个改完验证 |
| **验证** | `pytest src/test/ -n 2 --collect-only` 无 warning；`pytest src/test/ -n 2` 0 failed |
| **预期产出** | fixture scope 审核清单，标记为 safe 的 `✓` 和需要改 scope 的 `Δ` |
| **回滚** | 修改的 fixture scope 可逐条 `git revert`；审核清单本身无副作用 |

#### Step A2a（新增）：Fixture 不兼容检查点（提前退出门）

> **背景**：如果 session/module scope fixture 不兼容问题过多，强行推进 Phase 1 可能引入大量耗时重构。
> 本步骤提供明确的退出点，避免沉没成本。

| 字段 | 值 |
|:-----|:----|
| **目标** | 根据 A2 审核结果决策：是否继续推进 Phase 1 并行化 |
| **操作** | (1) 统计 A2 审核清单中标记为 `Δ`（需改 scope）的问题数量<br>(2) **Δ ≤ 5** → ✅ 继续 A3 并行逻辑<br>(3) **Δ > 5** → ⛔ 暂停，输出评估报告：逐一列出需重构的 fixture、预期工作量、推荐方案（彻底重构 / 不完全依赖并行 / 跳过 Phase 1 直接到 Phase 3 增量测试）<br>(4) 决策结果写入 `docs-stm/plan/notes/a5-fixture-gate.md` |
| **验证** | 决策记录明确（继续/暂停/改道），fixture 评估报告完整 |
| **预期产出** | commit: "docs: A5 A2a 检查点 — fixture 不兼容 {Δ} 项，决策{继续|暂停|改道}" |
| **回滚** | 文档仅作记录，无代码影响；可在重构后重新进入 A3 |

#### Step A3：test_runner.py 并行逻辑

| 字段 | 值 |
|:-----|:----|
| **目标** | `unit`/`verify`/`all` 模式自动启用并行，xdist 不可用时无缝降级单线程；支持 `parallel: True`（auto）和 `parallel: 4`（显式指定进程数）|
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) MODES 中 `unit`/`verify`/`all`/`integration` 新增 `"parallel": True`；`smoke`/`regression` 保持 `False` <br>(2) `_build_pytest_args()` 处理 `parallel`：True → `max(1, os.cpu_count() // 2)`（超线程减半防 IO 争抢），int → `-n <N>` <br>(3) 新增 `_check_xdist()` 函数检测 xdist 安装，不可用时降级（打印 `[!]` 警告）<br>(4) 收紧超时：`unit` 1800→720（+20% buffer）, `verify` 1200→360, `all` 2400→720 |
| **验证** | `python test_runner.py --mode unit` 正常运行（有 xdist 时日志含 `-n N`，N = max(1, cpu_count//2)），无 xdist 时降级不报错 |
| **预期产出** | commit: "feat: test_runner.py 并行模式 — MODES parallel 字段 + cpu_count//2" |

#### Step A3b（新增）：单线程对比确认（并行无误报）

> **背景**：xdist 并行可能通过隐式数据依赖掩盖测试失败（测试 A 写→测试 B 读，并行下 B 先于 A 执行读到脏数据"通过"）。
> 本步骤确保并行结果与单线程一致，消除误报风险。

| 字段 | 值 |
|:-----|:----|
| **目标** | `unit` 模式在并行（`-n auto`）和单线程（`-n 0`）下各跑一次，结果完全一致 |
| **操作** | (1) `python test_runner.py --mode unit`（并行）收集 failed 列表 F1<br>(2) `python test_runner.py --mode unit --no-parallel`（强制单线程）收集 failed 列表 F2<br>(3) 比较 F1 和 F2：F1 有而 F2 无 → 误报（并行掩盖）；F1 无而 F2 有 → 漏测（并行错误跳过）<br>(4) 差异为 0 才进入下一 Phase，否则逐个调查 |
| **验证** | F1 = F2（空集或完全一致）|
| **预期产出** | 并行/单线程对比报告（写入 test-coverage.md 或日志）|
| **回滚** | 出现差异 → 定位到具体 fixture 或测试文件修复；无法修复 → 回到 A3 前的单线程模式 |

`--no-parallel` 实现方式：`_build_pytest_args` 检测 `--no-parallel` 时设置 `parallel=False`，追加 `-n 0`。

#### Step A3c（新增）：加速比检测门（决定是否进入 Phase 2 拆分）

> **背景**：如果测试以 I/O（openpyxl 写入）为主而非 CPU，xdist 并行加速可能不足 2.5x。
> 此时先 profiling 再决定是否拆分文件，避免无效拆分增加维护成本。

| 字段 | 值 |
|:-----|:----|
| **目标** | 实测 `verify` 并行加速比，≥ 2.5x（从 12min 降至 ≤ 5min）才进入 Phase 2 文件拆分 |
| **操作** | (1) 从 A0 基线读取 `verify` 耗时 T_baseline（约 12min）<br>(2) `python test_runner.py --mode verify` 记录耗时 T_parallel<br>(3) 计算加速比 R = T_baseline / T_parallel<br>(4) **R ≥ 2.5** → ✅ 进入 Phase 2 文件拆分<br>(5) **R < 2.5** → ⛔ 暂停，运行 `python -m cProfile -s time -m pytest src/test/ -m "unit_report" -n auto -q` 分析瓶颈；输出 profiling 报告到 `docs-stm/plan/notes/a5-profile-report.md`；根据报告决策：瓶颈在 CPU（继续拆分）或 IO（优化写入模式而非拆分）|
| **验证** | 决策记录明确（继续拆分/暂停分析），结果写入 A5 决策日志 |
| **预期产出** | commit: "docs: A5 加速比检测 — verify R={R:.1f}x，进入{'拆分' if ok else '分析'}" |
| **回滚** | 决策记录仅在文档中；如误判可重新运行检测后调整 |

---

### 6.2 文件拆分（6 步，可并行）

```
Step B1 ──→ Step B2 ──→ Step B3
(market_value   (llm_split)   (cache_split)
 _split)

各步之间无依赖，可并行执行（利用 git worktree 或分支实现，节省 ~4 人天），
但建议顺序执行以便逐项验证和回滚。
```

#### Step B1：拆 test_market_value.py（1918 行 → 1+3 文件）

| 字段 | 值 |
|:-----|:----|
| **目标** | `test_market_value.py` 拆为 4 文件后，`unit_report` 收集数仍为 672 项，且 `python test_runner.py --mode report` 全部通过 |
| **源文件** | `src/test/unit/report/test_market_value.py` |
| **拆后文件** | `test_market_value.py`（骨架 ~118 行）+ `test_market_value_classify.py`（分类逻辑） + `test_market_value_details.py`（明细行生成） + `test_market_value_sheet.py`（页签写入 + Excel 格式） |
| **操作** | (1) 识别可独立测试的函数域（按文件顶部 docstring 中的组）<br>(2) 每个子文件自包含 import，共享 fixture 提升到新 `conftest.py` 或放入测试类<br>(3) 源文件保留公共 fixture + import，删减为骨架 |
| **验证** | `pytest src/test/ -m "unit_report" --collect-only -q` 收集数 = 原 672 项；`python test_runner.py --mode report` 全部通过 |
| **预期产出** | commit: "refactor: 拆分 test_market_value.py 为 4 文件 — classify/details/sheet" |
| **回滚** | `git revert` 该 commit；或删除 3 个子文件，恢复原始 test_market_value.py |

#### Step B2：拆 test_llm.py（2040 行 → 1+4 文件）

| 字段 | 值 |
|:-----|:----|
| **目标** | `test_llm.py` 拆为 5 文件后，`unit_llm` 收集数仍为 337 项，且全量运行 0 failed |
| **源文件** | `src/test/unit/llm/test_llm.py` |
| **拆后文件** | `test_llm.py`（骨架）+ `test_llm_api.py`（API 路由/请求）+ `test_llm_session.py`（会话管理）+ `test_llm_generators.py`（生成器）+ `test_llm_fingerprint.py`（指纹） |
| **验证** | `pytest src/test/ -m "unit_llm" --collect-only -q` 收集数 = 原 337 项；`pytest src/test/ -m "unit_llm" -q` 全部通过 |
| **预期产出** | commit: "refactor: 拆分 test_llm.py 为 5 文件 — api/session/generators/fingerprint" |
| **回滚** | `git revert` 该 commit；或删除 4 个子文件，恢复原始 test_llm.py |

#### Step B3：拆 test_cache.py（1361 行 → 1+4 文件）

| 字段 | 值 |
|:-----|:----|
| **目标** | `test_cache.py` 拆为 5 文件后，`unit_core` 收集数仍为 307 项，且全量运行 0 failed |
| **源文件** | `src/test/unit/core/test_cache.py` |
| **拆后文件** | `test_cache.py`（骨架）+ `test_cache_core.py`（核心读写逻辑）+ `test_cache_edge.py`（边界条件）+ `test_cache_ttl.py`（TTL/过期）+ `test_cache_concurrency.py`（并发安全） |
| **注意** | `test_cache_concurrency.py` 包含 `time.sleep` + assertion 时序敏感测试，在 xdist 多进程争抢下可能 flaky。拆分后：(1) 给该文件添加 `@pytest.mark.serial` 标记，或在 `test_runner.py` 中对该文件特例 `-n 0` 单进程执行；(2) 同时添加 `@pytest.mark.flaky(reruns=2)` 重试机制（需 `pytest-rerunfailures`），应对机器负载波动导致的偶尔超时 |
| **验证** | `pytest src/test/ -m "unit_core" --collect-only -q` 收集数 = 原 307 项；`pytest src/test/ -m "unit_core" -q` 全部通过 |
| **预期产出** | commit: "refactor: 拆分 test_cache.py 为 5 文件 — core/edge/ttl/concurrency" |
| **回滚** | `git revert` 该 commit；或删除 4 个子文件，恢复原始 test_cache.py |

#### Step B4：验证单元测试收集总数一致

> **注意**：如果 A5 实施期间有其他迭代（如 B 系列）新增了测试，全量总数会 > 1998。
> 因此 B4 不做绝对数硬编码断言，而是做 **相对比较**：拆分后的子标记收集数之和 = 拆分前的父标记收集数。

| 字段 | 值 |
|:-----|:----|
| **目标** | 拆分后各子标记收集数之和 = 拆分前父标记数，无漏无双计；标记值精确继承无丢失 |
| **操作** | (1) 从 A0 基线和 `docs-stm/managements/test-coverage.md` 读取拆分前各标记收集数<br>(2) 运行 `pytest src/test/ --collect-only -q` 获取全量<br>(3) 核对 `unit_report` 拆分后子文件收集数之和 = 拆分前父标记数<br>(4) 核对 `unit_llm`、`unit_core` 同理<br>(5) ⚠️ **标记值精确比对**：运行 `pytest src/test/ --co -q --markers --tb=no 2>&1 | grep -E "^\s+" > /tmp/markers_pre.txt`（拆分前已保存）+ 拆后同样输出，用 `diff /tmp/markers_pre.txt /tmp/markers_post.txt` 确保标记字符串完全继承（无丢失、无新增、无拼写错误）|
| **验证** | `Σ(test_market_value_*)` 原来 `test_market_value` 标记数；`Σ(test_llm_*)` = 原来 `test_llm` 标记数；`Σ(test_cache_*)` = 原来 `test_cache` 标记数；标记值 diff 输出为空 |
| **预期产出** | 收集数一致确认（如有偏差，回溯到具体拆分步骤修正） |
| **回滚** | 任一标记收集数不匹配 → 回退对应 B1/B2/B3 的拆分 |

#### Step B5：运行全量单元测试确认无回归

| 字段 | 值 |
|:-----|:----|
| **目标** | `unit` 模式 0 failed，耗时 < Phase 1 预期（< 6min） |
| **操作** | `python test_runner.py --mode unit` |
| **验证** | 全部通过（允许因计时波动的少量 flaky，但数量 < 拆分前） |
| **预期产出** | 基准耗时记录：`unit` 模式在并行下的首次耗时 |
| **回滚** | 有 failed 项 → 根据失败追踪到 B1/B2/B3 对应的子文件修正；大量 flaky → 回退最近拆分 commit |

#### Step B6：运行回归测试确认场景无影响

| 字段 | 值 |
|:-----|:----|
| **目标** | `regression` 模式 0 failed（场景测试不受文件拆分影响） |
| **操作** | `python test_runner.py --mode regression` |
| **验证** | 0 failed（场景测试不受文件拆分影响，但确保 import 路径无错） |
| **预期产出** | 回归确认 |
| **回滚** | 场景测试 failed → 检查拆分文件的 import 路径错误，修正后重跑；如为 import 循环依赖 → git revert B1/B2/B3 |

---

### 6.3 增量测试（4 步）

```
Step X  ──→ Step C1 ──→ Step C2 ──→ Step C3
(决策门)    (映射表)     (CLI参数)    (映射测试)
```

#### Step X（新增）：决策门 — 实测 verify 耗时决定 D1 去留

> **背景**：D1（`verify_fast` 模式）的启用在 Phase 1+2 完成后才能合理决策。
> 本步骤将决策点从 D1 的条件标注中显式抽出，
> 避免开发者在实施 Phase 3（增量）和 Phase 4（子模式）间来回斟酌。

| 字段 | 值 |
|:-----|:----|
| **目标** | 实测 Phase 1+2 后的 `verify` 耗时，明确 D1（`verify_fast` 是否实施）|
| **操作** | (1) `python test_runner.py --mode verify` 记录耗时 T<br>(2) T ≤ 180s（3min）→ **跳过 D1**，D1 步骤标记为「不实施 — Phase 1+2 已达标」<br>(3) T > 180s → **实施 D1**，继续 C1→C2→C3→D1→D2→D3→E<br>(4) 决策结果写入 `docs-stm/managements/test-coverage.md` 的 A5 决策日志 |
| **验证** | 决策记录明确（跳过/实施），后续步骤按决策路径执行 |
| **预期产出** | commit: "docs: A5 决策门 — verify 耗时 T={T}s，D1 按需实施" |
| **回滚** | 决策记录仅在文档中，无代码影响；可在 D1 实施后重新决策 |

#### Step C1：实现 `_get_changed_marker()` 映射函数

| 字段 | 值 |
|:-----|:----|
| **目标** | 函数正确识别 git diff 中的变更文件，映射为对应 pytest marker 表达式；未识别源文件兜底 `"unit"`；无变更返回 None |
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) 在文件顶部新增 `import subprocess`（如不存在）<br>(2) 实现 `_get_changed_marker(branch="origin/main") → str | None`<br>(3) 基准分支 fallback 链：`origin/main → main → HEAD~1`<br>(4) 通过 `git diff --name-only {branch}...HEAD` 获取分支差异变更列表<br>(5) ⚠️ **追加 dirty 文件**：通过 `git diff --name-only HEAD` 获取未提交的 dirty 文件列表，与分支差异合并去重。防止开发者改了代码还没 commit 时 `--changed` 误判为"无变更"<br>(6) 遍历合并后的 `FILE_TO_MARKER` 映射表，合并匹配的 marker<br>(7) 未匹配的 `src/` 文件 → 兜底 `"unit"` 确保不漏测；**同时输出 `[!] 未识别变更文件：xxx，建议更新 FILE_TO_MARKER 映射表` 警告**，让开发者知悉覆盖缺口<br>(8) 仅 docs/data 变更 → 返回 None 跳过<br>(9) `src/test/` 变更标记为哨兵值（不自动追加，由调用方根据测试文件决定模式）|
| **验证** | (1) 无变更时返回 `None`<br>(2) 修改 `src/python/report/` 下文件后，返回 `"unit_report"` <br>(3) 同时修改 `src/python/providers/` + `src/python/tui_menu.py`，返回 `"unit_providers or unit_fetcher or unit_ui"` <br>(4) 修改未映射源文件（如 `src/python/constants.py`）→ 兜底返回 `"unit"` <br>(5) 仅修改 docs/ 文件 → 返回 `None`<br>(6) 🔴 **dirty 文件验证**：修改 `src/python/report/fund_overlap.py` 但不 commit，运行 `--changed` 仍返回 `"unit_report"` |
| **预期产出** | commit: "feat: test_runner.py 新增 _get_changed_marker() 增量测试映射" |

#### Step C2：`--changed` CLI 参数集成

| 字段 | 值 |
|:-----|:----|
| **目标** | `test_runner.py --changed` 根据当前 git diff 自动选择测试模式，clean tree 时跳过 |
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) `parse_args()` 新增 `--changed` 可选参数（`store_true`）<br>(2) `main()` 中：`--changed` 指定时，调用 `_get_changed_marker()`，若返回 marker 则运行对应模式；无变更时打印 "无变更文件，跳过"<br>(3) **⚠️ 交互语义**：`--changed` 和 `--mode` 互斥，同时指定时报错并提示"请选择其一：`--changed` 增量模式 或 `--mode <name>` 指定模式"。<br>&nbsp;&nbsp;&nbsp;理由：`--changed --mode verify` 混合语义会产生"用户以为跑 verify，实际只跑 changed 子集"的危险幻觉。<br>(4) Tab 补全和 help 文本注明二者互斥 |
| **验证** | (1) `python test_runner.py --changed` → 根据当前 diff + dirty 运行对应模式<br>(2) 无变更（committed + dirty 均为空）→ 跳过<br>(3) 改了文件未 commit → 仍检测到<br>(4) `--changed --mode verify` → 报错并提示互斥 |
| **预期产出** | commit: "feat: test_runner.py --changed 参数 — git-aware 增量测试"  |

#### Step C3：为 `_get_changed_marker()` 编写单元测试

| 字段 | 值 |
|:-----|:----|
| **目标** | 新增 `test_test_runner.py` 覆盖 **8 种** git diff + dirty 场景，映射准确率 100% |
| **文件** | `src/test/unit/test_test_runner.py`（新文件） |
| **操作** | (1) mock `subprocess.run` 返回可控的 git diff + dirty 输出<br>(2) 覆盖场景：无变更、单文件变更、多域变更、测试文件变更、docs-only 变更、**未识别源文件（兜底 unit）**、**基准分支 fallback**、**dirty 文件未 commit 仍被检测**<br>(3) 标记 `@pytest.mark.unit_core` |
| **验证** | `pytest src/test/ -m "unit_core" -k "test_runner"` 全部通过 |
| **预期产出** | commit: "test: 为 _get_changed_marker 添加 7 项单元测试（含兜底）" |

---

### 6.4 新增快速子模式（3 步）

```
Step D1 ──→ Step D2 ──→ Step D3
(verify_fast)  (report模式)  (门禁文档同步)
```

#### Step D1（条件）：新增 `verify_fast` 模式

> **前置条件**：Phase 1+2 完成后，实测 `verify` 仍 > 3min 才实施。否则跳过此步骤。
> 建议在 Step D3 门禁同步前做一次 `python test_runner.py --mode verify` 实测决定。

| 字段 | 值 |
|:-----|:----|
| **目标** | 新增 `verify_fast` 模式（unit_core + unit_llm + unit_config，~700 项），耗时 **< 3min** |
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) MODES 中 `"verify"` 之后插入 `"verify_fast"` 条目：marker=`"unit_core or unit_llm or unit_config"`，parallel=`True`，timeout=`300`<br>(2) order 设为 5（紧接 verify 之后） |
| **验证** | `python test_runner.py --mode verify_fast` 运行成功，耗时预期 ~2min |
| **预期产出** | commit: "feat: test_runner 新增 verify_fast 模式（核心+LLM+配置~700项）" |

#### Step D2：新增 `report` 模式

| 字段 | 值 |
|:-----|:----|
| **目标** | 新增 `report` 模式（unit_report，~672 项），耗时 **< 90s** |
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) MODES 末尾插入 `"report"` 条目：marker=`"unit_report"`，parallel=`True`，timeout=`180`<br>(2) order 设为 11 |
| **验证** | `python test_runner.py --mode report` 运行成功，耗时预期 ~60s |
| **预期产出** | commit: "feat: test_runner 新增 report 模式（unit_report ~672项）" |

#### Step D3：门禁文档同步

| 字段 | 值 |
|:-----|:----|
| **目标** | CLAUDE.md 门禁说明和 test-coverage.md 中的模式列表与最新状态同步 |
| **文件** | `CLAUDE.md`, `docs-stm/managements/test-coverage.md` |
| **操作** | (1) CLAUDE.md 门禁说明更新为：P1 门禁使用 `verify`（约 3min）或 `verify_fast`（如启用，约 2min）<br>(2) test-coverage.md 新增 `verify_fast`（如启用）/`report` 行<br>(3) A0 基线数据对比标注优化效果 |
| **验证** | 阅读确认一致 |
| **预期产出** | commit: "docs: 同步 verify_fast/report 模式到门禁文档及基线数据" |
| **回滚** | `git revert` 该 commit，旧门禁说明在 git 历史中完好 |

---

### 6.5 最终验证（1 步）

#### Step E：全量回归 + 基线记录

| 字段 | 值 |
|:-----|:----|
| **目标** | `all` 模式 0 failed 且耗时 < 8min（当前 26min 基线），全迭代目标达成 |
| **操作** | (1) `python test_runner.py --mode all` — 全量并行回归<br>(2) `python test_runner.py --mode verify_fast` — 记录新基线<br>(3) `python test_runner.py --mode report` — 记录新基线<br>(4) 将耗时数据填入 test-coverage.md |
| **验证** | (1) `all` 0 failed，耗时 < 8min（当前 26min 基线）<br>(2) `verify_fast` 耗时 < 3min<br>(3) `report` 耗时 < 90s |
| **预期产出** | commit: "docs: A5 迭代完成 — 测试耗时基线更新" |
| **回滚** | 基线偏差（如 all 仍 > 10min）→ 记录实际耗时作为新基线，标记 Phase 1 目标未达成原因，后续优化 |

---

### 实施步骤总览

```
Week 1                          Week 2
┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│  A0  │  A1  │  A2  │ A2a  │  A3  │ A3b  │ A3c  │ B1~3 │
│基线  │  dep │scope │检查  │并行  │单线  │加速  │拆分  │
│录制  │      │审计  │点    │逻辑  │程确认│比门  │(可并行)│
├──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│ B4~6 │  X   │  C1  │  C2  │  C3  │ [D1] │  D2  │  D3  │
│决策  │映射  │CLI   │映射UT│test- │verify│report│文档  │
│门    │      │      │      │mon   │_fast†│      │同步  │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
        ↑Phase 1 完成            ↑文件拆分完成     ↑增量测试完成   ↑全量回归
         verify 加速比门          B4 收集数确认    —changed        (<8min)
         ≥2.5x 才进拆分
```

### 每步验收卡片

| 步骤 | 目标 | 验证 | 回滚 |
|:-----|:------|:---------|:---------|
| A0 | 录制各模式耗时基线（3 次取中位数） | test-coverage.md 数据完整 | `git revert` A0 commit |
| A1 | pyproject.toml 声明 xdist 依赖 | `pip install -e .` + `pytest -n auto --collect-only` 不报错 | `git revert` A1 commit |
| A2 | 所有 fixture scope + tmpdir 路径确认并行安全 | `pytest -n 2` 0 failed | 逐条 `git revert` |
| A2a | fixture 检查点：Δ ≤ 5 才继续 Phase 1 | 决策记录明确（继续/暂停/改道）| 文档回退无代码影响；暂停后可在重构后重新进入 |
| A3 | `unit`/`verify`/`all` 使用并行；支持 `parallel: N` | 日志含 `-n N`（N = cpu_count//2）；`-n 4` 手动指定有效 | `git revert`；无 xdist 自动降级 |
| A3b | 并行与单线程结果一致 | F1（并行 failed） = F2（单线程 failed）| 有差异时定位 fixture 修复 |
| A3c | verify 加速比 ≥ 2.5x 才进拆分 | 决策记录明确（继续/暂停分析）| 暂停分析时提交 profiling 报告后退回决策 |
| B1 | 拆分后 `unit_report` 收集数 = 672 | `test_runner.py --mode report` 0 failed | `git revert` B1 commit |
| B2 | 拆分后 `unit_llm` 收集数 = 337 | `pytest -m "unit_llm" -q` 全部通过 | `git revert` B2 commit |
| B3 | 拆分后 `unit_core` 收集数 = 307；concurrency 文件标记 serial | `pytest -m "unit_core" -q` 全部通过 | `git revert` B3 commit |
| B4 | 全标记收集数 = 1998 | 逐个标记核对一致 | 回溯 B1~B3 修正 |
| B5 | `unit` 0 failed, < 6min | `test_runner.py --mode unit` 通过 | 追踪到子文件修正 |
| B6 | `regression` 0 failed | `test_runner.py --mode regression` 通过 | 检查 import 或 git revert |
| X | 实测 verify 耗时，决策 D1 去留 | 决策记录明确，后续路径一致 | 文档回退无代码影响 |
| C1 | `_get_changed_marker()` 映射准确 + 兜底 unit | 5 种 diff 场景均返回正确 marker | `git revert` C1 commit |
| C2 | `--changed` 语义完整（无 `--mode` 干扰） | clean tree 跳过；`--changed` + `--mode` 并用时报错提示互斥 | `git revert` C2 commit |
| C3 | 8 项 mock 场景覆盖（含兜底+fallback+dirty） | `pytest -k "test_runner"` 全部通过 | `git revert` C3 commit |
| D1† | `verify_fast` < 3min（条件：Phase1+2 后 verify>3min） | `test_runner.py --mode verify_fast` 通过 | `git revert` D1 commit |
| D2 | `report` < 90s | `test_runner.py --mode report` 通过 | `git revert` D2 commit |
| D3 | 门禁文档 + 基线数据同步 | 阅读一致 | `git revert` D3 commit |
| E | `all` < 8min | 全量 0 failed | 记录实际基线，标注偏差原因 |

† D1 为条件步骤，若 Phase 1+2 后 `verify` 已达标则跳过

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| pytest-xdist 下测试状态泄漏（共享 fixture） | 中 | 高 | 审核 fixture scope；所有 openpyxl 测试确认用 `tmp_path`（Step A2）；明确 xdist 下 session scope fixture 在每个 worker 独立执行，不跨进程共享 |
| xdist 并行误报（隐式数据依赖导致测试"通过"但实际失败）| 高 | 中 | Step A3b 新增单线程对比确认；F1（并行失败列表）= F2（单线程失败列表）才通过 |
| 拆分测试文件导致标记遗漏 | 低 | 中 | 相对比较法 B4（子标记之和 = 父标记数）；`check-test-markers.py` 验证 |
| pytest-xdist Windows 兼容问题 | 低 | 中 | `-n auto` 进程池模式已验证兼容；保留 `--strict` 回退 |
| git diff → marker 映射漏测 | 中 | 中 | 映射表 + 兜底 `"unit"` + 未识别文件警告日志（`[!]`）|
| 并行测试输出混乱 | 高 | 低 | `pytest-xdist` 自动聚合输出；每个工作进程输出流独立 |
| `--changed` 基准分支不存在 | 低 | 中 | fallback 链：`origin/main → main → HEAD~1`（C1）|
| `test_cache_concurrency` 时序测试多负载下 flaky | 低 | 低 | 标记 `@pytest.mark.serial` + `@pytest.mark.flaky(reruns=2)`（B3）|
| `verify_fast` 与 `verify` 效果重叠冗余 | 中 | 低 | Step X 决策门：Phase 1+2 后实测 verify 耗时，>3min 才实施 D1 |
| FILE_TO_MARKER 映射表随项目新文件增长而失效 | 高 | 低 | 未识别 `src/` 文件兜底 `"unit"` + 输出 `[!]` 警告；建议每次新增目录/文件时同步更新映射表 |
| 拆分后 B 系列等并行迭代产生 git 合并冲突 | 中 | 中 | 建议 B 迭代完成后才执行 A5 Phase 2 拆分，或拆分前锁定需拆文件不做其他修改 |
