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

#### 3.2.2 核心设计

```python
# test_runner.py MODES 新增 parallel 字段
MODES = {
    "unit": {
        "marker": "unit",
        "desc": "全量单元测试",
        "timeout_sec": 600,       # 从 1800 下调（预期 5min）
        "order": 1,
        "parallel": True,         # ✅ 新增
    },
    # ...
}
```

`_build_pytest_args` 逻辑：

```python
if mode_cfg.get("parallel"):
    args.extend(["-n", "auto"])
```

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
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main..."],
        capture_output=True, text=True
    )
    changed = result.stdout.strip().splitlines()

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
        "src/test/": "",  # 测试文件变更 → 运行对应域
    }

    markers = set()
    for f in changed:
        for prefix, marker in FILE_TO_MARKER.items():
            if f.startswith(prefix):
                if marker:
                    markers.add(marker)
                break

    if not markers:
        return None
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

### 3.5 Phase 4：新增快速 verify 子模式

#### 3.5.1 新模式定义

```python
MODES = {
    # ... 现有模式 ...
    "verify_fast": {
        "marker": "scenario or unit_core",
        "desc": "快速合入验证（场景+核心模块 ~529 项，预期 ~2min）",
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

- `verify_fast` 取代 `verify` 作为日常合入验证（核心逻辑不涉及数据源）
- `verify` 保留不变，CI 中作为更严格的提交前检查
- `report` 为 report 模块开发者提供快捷入口

#### 3.5.2 gate 推荐更新

| 门禁 | 当前 | 推荐 |
|:-----|:-----|:-----|
| P0（提交前） | `regression` ~32s | 不变 |
| P1（合并前） | `verify` ~12min | `verify_fast` ~2min（日常）/ `verify` ~3min（并行后，CI）|
| P2（发布前） | `all` ~26min | `all` ~5-8min（并行后）|

---

## 4. 预期收益汇总

| 指标 | Phase 1（并行） | Phase 2（拆分） | Phase 3（增量） | Phase 4（新模式） |
|:-----|:---------------:|:---------------:|:---------------:|:-----------------:|
| `unit` | 25min → **4-6min** | 稳定 4-6min | 增量 10-30s | — |
| `verify` | 12min → **2-3min** | 2-3min | — | 新增 **~2min** |
| `all` | 26min → **5-8min** | 5-8min | — | — |
| 本地开发 | — | — | **git 感知 10s 级** | 新增 report 模式 **~60s** |

---

## 5. 依赖评估

### 5.1 新增依赖

| 包 | 用途 | 安装大小 | 风险 |
|:---|:------|:--------:|:----:|
| `pytest-xdist` | 并行测试执行 | ~200KB | ⚠️ Windows 需 `psutil` 或 `py` |
| `pytest-testmon`（可选） | 增量测试选择 | ~100KB | 低 |

### 5.2 兼容性

- `pytest-xdist 3.x` 支持 `pytest 7+`（当前 8.3.4，兼容）
- `pytest-xdist` 的 `--forked` 选项在 Windows 上受限，使用 `-n auto`（进程池）即可
- Windows 上 `-n` 使用 `spawn` 启动方式，所有测试文件需保证模块级导入安全（已在 `conftest.py` 中内置 import 保护）

---

## 6. 实施步骤（拆细为 16 个原子步）

### 6.1 依赖与基础设施（3 步）

```
Step A1 ──→ Step A2 ──→ Step A3
(pyproject)  (fixture审计)  (test_runner)
```

#### Step A1：添加 pytest-xdist 依赖

| 字段 | 值 |
|:-----|:----|
| **文件** | `pyproject.toml` |
| **操作** | 在 `[project.dependencies]` 或 `[project.optional-dependencies]` 中新增 `pytest-xdist>=3.6` |
| **验证** | `pip install -e .` 后 `pytest src/test/ -n auto --collect-only -q` 不报错 |
| **回滚** | `git revert` 该 commit |

#### Step A2：审计 conftest.py fixture scope

| 字段 | 值 |
|:-----|:----|
| **文件** | `src/test/conftest.py`, `src/test/unit/conftest.py` |
| **操作** | 扫描所有 `@pytest.fixture(scope="session")` 和 `@pytest.fixture(scope="module")`，确认 fixture 产生或修改的对象不跨进程共享。重点关注：缓存临时目录、mock 单例、openpyxl Workbook |
| **验证** | 运行 `pytest src/test/ -n 2 --collect-only` 无 warning。如有 session-scope fixture 要改为 module-scope，逐个改完验证 |
| **预期产出** | fixture scope 审核清单，标记为 safe 的 `✓` 和需要改 scope 的 `Δ` |

#### Step A3：test_runner.py 并行逻辑

| 字段 | 值 |
|:-----|:----|
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) MODES 中 `unit`/`verify`/`all`/`integration` 新增 `"parallel": True`；`smoke`/`regression` 保持 `False` <br>(2) `_build_pytest_args()` 检测 `mode_cfg.get("parallel")` 且 xdist 可用时追加 `-n auto` <br>(3) 新增 `_check_xdist()` 函数检测 xdist 安装，不可用时降级（打印 `[!]` 警告）<br>(4) 收紧超时：`unit` 1800→600, `verify` 1200→300, `all` 2400→600 |
| **验证** | `python test_runner.py --mode unit` 正常运行（有 xdist 时 print 中包含 `-n auto`），无 xdist 时降级不报错 |
| **预期产出** | commit: "feat: test_runner.py 并行模式 — MODES parallel 字段 + -n auto" |

---

### 6.2 文件拆分（6 步，可并行）

```
Step B1 ──→ Step B2 ──→ Step B3
(market_value   (llm_split)   (cache_split)
 _split)

各步之间无依赖，可并行执行，但建议顺序执行以便逐项验证。
```

#### Step B1：拆 test_market_value.py（1918 行 → 1+3 文件）

| 字段 | 值 |
|:-----|:----|
| **源文件** | `src/test/unit/report/test_market_value.py` |
| **目标** | `test_market_value.py`（骨架 ~118 行）+ `test_market_value_classify.py`（分类逻辑） + `test_market_value_details.py`（明细行生成） + `test_market_value_sheet.py`（页签写入 + Excel 格式） |
| **操作** | (1) 识别可独立测试的函数域（按文件顶部 docstring 中的组）<br>(2) 每个子文件自包含 import，共享 fixture 提升到新 `conftest.py` 或放入测试类<br>(3) 源文件保留公共 fixture + import，删减为骨架 |
| **验证** | `pytest src/test/ -m "unit_report" --collect-only -q` 收集数 = 原 672 项；`python test_runner.py --mode report` 全部通过 |
| **预期产出** | commit: "refactor: 拆分 test_market_value.py 为 4 文件 — classify/details/sheet" |

#### Step B2：拆 test_llm.py（2040 行 → 1+4 文件）

| 字段 | 值 |
|:-----|:----|
| **源文件** | `src/test/unit/llm/test_llm.py` |
| **目标** | `test_llm.py`（骨架）+ `test_llm_api.py`（API 路由/请求）+ `test_llm_session.py`（会话管理）+ `test_llm_generators.py`（生成器）+ `test_llm_fingerprint.py`（指纹） |
| **验证** | `pytest src/test/ -m "unit_llm" --collect-only -q` 收集数 = 原 337 项；`pytest src/test/ -m "unit_llm" -q` 全部通过 |
| **预期产出** | commit: "refactor: 拆分 test_llm.py 为 5 文件 — api/session/generators/fingerprint" |

#### Step B3：拆 test_cache.py（1361 行 → 1+4 文件）

| 字段 | 值 |
|:-----|:----|
| **源文件** | `src/test/unit/core/test_cache.py` |
| **目标** | `test_cache.py`（骨架）+ `test_cache_core.py`（核心读写逻辑）+ `test_cache_edge.py`（边界条件）+ `test_cache_ttl.py`（TTL/过期）+ `test_cache_concurrency.py`（并发安全） |
| **验证** | `pytest src/test/ -m "unit_core" --collect-only -q` 收集数 = 原 307 项；`pytest src/test/ -m "unit_core" -q` 全部通过 |
| **预期产出** | commit: "refactor: 拆分 test_cache.py 为 5 文件 — core/edge/ttl/concurrency" |

#### Step B4：验证单元测试收集总数一致

| 字段 | 值 |
|:-----|:----|
| **操作** | (1) 运行 `pytest src/test/ --collect-only -q -m "unit"` 统计总数 <br>(2) 与拆分前的基线对比（1998 项）<br>(3) 逐个标记核对：`unit_report`/`unit_llm`/`unit_core` |
| **验证** | 收集数 = 1998 (每个标记与原基线一致) |
| **预期产出** | 收集数一致确认（如有偏差，回溯到具体拆分步骤修正） |

#### Step B5：运行全量单元测试确认无回归

| 字段 | 值 |
|:-----|:----|
| **操作** | `python test_runner.py --mode unit` |
| **验证** | 全部通过（允许因计时波动的少量 flaky，但数量 < 拆分前） |
| **预期产出** | 基准耗时记录：`unit` 模式在并行下的首次耗时 |

#### Step B6：运行回归测试确认场景无影响

| 字段 | 值 |
|:-----|:----|
| **操作** | `python test_runner.py --mode regression` |
| **验证** | 0 failed（场景测试不受文件拆分影响，但确保 import 路径无错） |
| **预期产出** | 回归确认 |

---

### 6.3 增量测试（4 步）

```
Step C1 ──→ Step C2 ──→ Step C3 ──→ Step C4
(mapping表)  (CLI参数)   (映射测试)   (testmon可选)
```

#### Step C1：实现 `_get_changed_marker()` 映射函数

| 字段 | 值 |
|:-----|:----|
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) 在文件顶部新增 `import subprocess`（如不存在）<br>(2) 实现 `_get_changed_marker(branch="origin/main") → str | None`<br>(3) 通过 `git diff --name-only {branch}...HEAD` 获取变更文件列表<br>(4) 遍历 `FILE_TO_MARKER` 映射表，合并匹配的 marker<br>(5) 无变更时返回 `None` |
| **验证** | (1) 无变更时返回 `None`<br>(2) 修改 `src/python/report/` 下文件后，返回 `"unit_report"` <br>(3) 同时修改 `src/python/providers/` + `src/python/tui_menu.py`，返回 `"unit_providers or unit_fetcher or unit_ui"` |
| **预期产出** | commit: "feat: test_runner.py 新增 _get_changed_marker() 增量测试映射" |

#### Step C2：`--changed` CLI 参数集成

| 字段 | 值 |
|:-----|:----|
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) `parse_args()` 新增 `--changed` 可选参数（`store_true`）<br>(2) `main()` 中：`--changed` 指定时，调用 `_get_changed_marker()`，若返回 marker 则运行对应模式；无变更时打印 "无变更文件，跳过"<br>(3) `--changed` 可与 `--mode` 叠加，`--changed` 优先级更高 |
| **验证** | (1) `python test_runner.py --changed` → 根据当前 diff 运行对应模式<br>(2) clean working tree 下 `--changed` → 跳过 |
| **预期产出** | commit: "feat: test_runner.py --changed 参数 — git-aware 增量测试"  |

#### Step C3：为 `_get_changed_marker()` 编写单元测试

| 字段 | 值 |
|:-----|:----|
| **文件** | `src/test/unit/test_test_runner.py`（新文件） |
| **操作** | (1) mock `subprocess.run` 返回可控的 git diff 输出<br>(2) 覆盖场景：无变更、单文件变更、多域变更、测试文件变更、docs-only 变更<br>(3) 标记 `@pytest.mark.unit_core` |
| **验证** | `pytest src/test/ -m "unit_core" -k "test_runner"` 全部通过 |
| **预期产出** | commit: "test: 为 _get_changed_marker 添加 5 项单元测试" |

#### Step C4（可选）：pytest-testmon 集成

| 字段 | 值 |
|:-----|:----|
| **操作** | (1) `pip install pytest-testmon` <br>(2) 种子运行：`pytest src/test/ --testmon` <br>(3) 验证增量：修改一个测试文件后，`pytest src/test/ --testmon` 仅运行受影响项 |
| **验证** | 增量运行项数 < 全量运行项数，且漏报率为 0 |
| **预期产出** | testmon 增量验证确认 |

---

### 6.4 新增快速子模式（3 步）

```
Step D1 ──→ Step D2 ──→ Step D3
(verify_fast)  (report模式)  (门禁文档同步)
```

#### Step D1：新增 `verify_fast` 模式

| 字段 | 值 |
|:-----|:----|
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) MODES 中 `"verify"` 之后插入 `"verify_fast"` 条目：marker=`"scenario or unit_core"`，parallel=`True`，timeout=`300`<br>(2) order 设为 5（紧接 verify 之后） |
| **验证** | `python test_runner.py --mode verify_fast` 运行成功，耗时预期 ~2min |
| **预期产出** | commit: "feat: test_runner 新增 verify_fast 模式（场景+核心~529项）" |

#### Step D2：新增 `report` 模式

| 字段 | 值 |
|:-----|:----|
| **文件** | `scripts/test_runner.py` |
| **操作** | (1) MODES 末尾插入 `"report"` 条目：marker=`"unit_report"`，parallel=`True`，timeout=`180`<br>(2) order 设为 11 |
| **验证** | `python test_runner.py --mode report` 运行成功，耗时预期 ~60s |
| **预期产出** | commit: "feat: test_runner 新增 report 模式（unit_report ~672项）" |

#### Step D3：门禁文档同步

| 字段 | 值 |
|:-----|:----|
| **文件** | `CLAUDE.md`, `docs-stm/managements/test-coverage.md` |
| **操作** | (1) CLAUDE.md 提交前门禁说明更新为使用 `verify_fast` 作为日常 P1 门禁<br>(2) test-coverage.md 新增 `verify_fast`/`report` 行 |
| **验证** | 阅读确认一致 |
| **预期产出** | commit: "docs: 同步 verify_fast/report 模式到门禁文档" |

---

### 6.5 最终验证（1 步）

#### Step E：全量回归 + 基线记录

| 字段 | 值 |
|:-----|:----|
| **操作** | (1) `python test_runner.py --mode all` — 全量并行回归<br>(2) `python test_runner.py --mode verify_fast` — 记录新基线<br>(3) `python test_runner.py --mode report` — 记录新基线<br>(4) 将耗时数据填入 test-coverage.md |
| **验证** | (1) `all` 0 failed，耗时 < 8min（当前 26min 基线）<br>(2) `verify_fast` 耗时 < 3min<br>(3) `report` 耗时 < 90s |
| **预期产出** | commit: "docs: A5 迭代完成 — 测试耗时基线更新" |

---

### 实施步骤总览

```
Week 1                          Week 2
┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│  A1  │  A2  │  A3  │  B1  │  B2  │  B3  │  C1  │  C2  │
│  dep │scope │并行  │拆分MV│拆分LLM│拆分  │映射  │CLI   │
│      │审计  │逻辑  │      │      │Cache │      │      │
├──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤
│  C3  │  C4  │  D1  │  D2  │  D3  │ B4~6 │  E   │      │
│映射UT│test- │verify│report│文档  │验证  │全量  │      │
│      │mon   │_fast │      │同步  │回归  │基线  │      │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
        ↑第一阶段目标:     ↑第二阶段目标:     ↑第三阶段目标:
         verify_fast       unit 并行跑通     全量回归
         跑通(~2min)       (~5min)           (<8min 基线)
```

### 每步可独立 commit + 验证

| 步骤 | 可独立 commit? | 验证方法 | 失败回退 |
|:-----|:--------------:|:---------|:---------|
| A1 | ✅ | pip install 成功 | git revert |
| A2 | ✅ | pytest -n 2 无 warning | git revert |
| A3 | ✅ | unit 并行跑通 | git revert |
| B1 | ✅ | unit_report 收集数一致 | git revert |
| B2 | ✅ | unit_llm 收集数一致 | git revert |
| B3 | ✅ | unit_core 收集数一致 | git revert |
| B4 | ✅ | 全标记收集数 = 1998 | 回溯 B1~B3 |
| B5 | ✅ | unit 0 failed | 回溯 B1~B3 |
| B6 | ✅ | regression 0 failed | git revert |
| C1 | ✅ | 函数逻辑正确 | git revert |
| C2 | ✅ | --changed 生效 | git revert |
| C3 | ✅ | 单元测试通过 | git revert |
| C4 | ❌(可选) | 增量运行漏报率=0 | 跳过 |
| D1 | ✅ | verify_fast ~2min | git revert |
| D2 | ✅ | report ~60s | git revert |
| D3 | ✅ | 文档一致 | git revert |
| E | ✅ | all < 8min | 记录偏差基线 |

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| pytest-xdist 下测试状态泄漏（共享 fixture） | 中 | 高 | 审核 fixture scope；`--forked` 隔离进程 |
| 拆分测试文件导致标记遗漏 | 低 | 中 | 收集前后计数对比；`check-test-markers.py` 验证 |
| pytest-xdist Windows 兼容问题 | 低 | 中 | `-n auto` 进程池模式已验证兼容；保留 `--strict` 回退 |
| git diff → marker 映射漏测 | 中 | 中 | 映射表 + 兜底运行 `unit` 模式；testmon 作为备选 |
| 并行测试输出混乱 | 高 | 低 | `pytest-xdist` 自动聚合输出；每个工作进程输出流独立 |
