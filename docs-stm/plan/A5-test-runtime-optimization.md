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

## 6. 实施步骤

### Step A：基础设施准备（1d）

1. 安装 `pytest-xdist`
2. 审核 `conftest.py` 中所有 fixture scope
3. `test_runner.py` 增加 `parallel` 字段 + `-n auto` 逻辑
4. 修改超时时间（并行后预期缩短）
5. 运行 `python test_runner.py --mode unit` 验证并行
6. 记录基线耗时

### Step B：超大测试文件拆分（2d）

1. 拆分 `test_market_value.py` → 3 子文件
2. 拆分 `test_llm.py` → 4 子文件
3. 拆分 `test_cache.py` → 3 子文件
4. 验证拆分后 `unit_report` / `unit_llm` / `unit_core` 标记收集数不变
5. 运行全量测试确认无回归

### Step C：增量测试（1d）

1. `test_runner.py` 新增 `--changed` 参数 + `_get_changed_marker()` 实现
2. 验证 git diff → marker 映射准确度
3. 可选安装 pytest-testmon 作为备选

### Step D：快速 verify 子模式（0.5d）

1. MODES 新增 `verify_fast` 和 `report`
2. 更新 CLAUDE.md 门禁时间说明
3. 更新 test-coverage.md 耗时预期
4. 更新 testplan.md

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| pytest-xdist 下测试状态泄漏（共享 fixture） | 中 | 高 | 审核 fixture scope；`--forked` 隔离进程 |
| 拆分测试文件导致标记遗漏 | 低 | 中 | 收集前后计数对比；`check-test-markers.py` 验证 |
| pytest-xdist Windows 兼容问题 | 低 | 中 | `-n auto` 进程池模式已验证兼容；保留 `--strict` 回退 |
| git diff → marker 映射漏测 | 中 | 中 | 映射表 + 兜底运行 `unit` 模式；testmon 作为备选 |
| 并行测试输出混乱 | 高 | 低 | `pytest-xdist` 自动聚合输出；每个工作进程输出流独立 |
