# 缓存引擎拆分迭代计划（借鉴 R-206 模式）

创建日期：2026-07-11

## 1. 现状分析

### 1.1 当前结构

`src/python/cache.py` — 667 行，混合 7 类职责：

| 职责组 | 行数 | 核心函数 | 调用方数量 |
|:-------|:----:|:---------|:---------:|
| **路径/常量** | 20 | `_cache_path()`, `get_cache_dir()` | 3 |
| **文件 IO** | 70 | `_read_cache_data()`, `_write_atomic()` | 4 |
| **核心存取** | 130 | `get()`, `set()`, `clear()` | ~20 模块 |
| **命中率统计** | 35 | `get_cache_hit_rate()`, `reset_cache_stats()` | 3 |
| **TTL / 缓存年龄** | 100 | `get_ttl()`, `get_cache_age()`, `get_cache_age_by_data_type()` | ~10 模块 |
| **过期清理** | 80 | `cleanup_expired()`, `_process_cache_file()` | 2 |
| **组管理** | 70 | `clear_by_prefix()`, `clear_by_group()` | 2 |
| **持仓跟踪** | 140 | `compute_holdings_fingerprint()`, `check_and_refresh_caches()`, 等 5 函数 | 1 |
| **目录统计** | 40 | `get_cache_stats()` | 1 |

### 1.2 问题

- **内聚性低**：持仓跟踪（业务逻辑）与文件 IO（基础设施）同处一文件，前者因"依赖 cache 存数据"而被归入，概念上不属于缓存引擎
- **测试膨胀**：`test_cache.py` 1413 行，对应上述所有职责，定位特定功能测试时需跨文件搜索
- **模块责任不清**：开发者新增缓存功能时没有明确的位置归属，倾向于追加到现有文件尾部

### 1.3 设计约束（来自 technical.md）

| # | 约束 | 对本计划的影响 |
|:---|:-----|:-------------|
| C2 | **缓存统一管理** — 所有持久化缓存必须通过 `get()`/`set()` 读写 | ⚠️ 需在 I-07 中从 `__all__` 移除内部接口（`_cache_path`、`_read_cache_data`、`_write_atomic`），防止外部模块绕过 get/set 直接操作文件系统 |
| C3 | **原子写入** — 必须 `tempfile.mkstemp` + `os.replace` | `_write_atomic` 所在模块不被破坏即可 |
| C8 | **日志统一** — `logger = logging.getLogger("invest")` | 各子模块复用 |
| C11 | **测试标记强制** — 新增/修改测试用例必须标注 pytest marker | I-01 mock 路径迁移如涉及新增临时测试方法（如测试兼容性 patch），必须添加对应 marker |
| C13 | **测试敏感路径隔离** — 不得修改用户真实配置/缓存文件 | 🔴 `conftest.py:109` 的 `monkeypatch.setattr("src.python.cache._CACHE_DIR", ...)` 在 I-01 后静默失效（`_CACHE_DIR` 移至 `_paths.py`），必须修复 |
| C14 | 渲染期数据不可写入模块级全局变量 | 不涉及 |

### 1.4 R-206 模式回顾

`excel_generator.py`（原 ~1800 行）拆分时采用的模式：

```
迭代模式：I-01 baseline capture → I-N 逐模块提取 → I-07 收尾
核心策略：Strangler Fig — 创建新文件、移入代码、原文件 re-export 保持兼容
每轮产出：1 个子模块文件 + __init__.py 更新 + 回归测试验证
风险控制：每轮独立可回退，回归全部通过后才进入下一轮
```

## 2. 目标架构

```
src/python/
├── cache/                   # 缓存引擎子包（新建）
│   ├── __init__.py           # 公共 API re-export（保持 from cache import get 兼容）
│   ├── _paths.py             # 路径 & 常量（_CACHE_DIR, _cache_path, get_cache_dir）
│   ├── _io.py                # 文件读写（_read_cache_data, _write_atomic）
│   ├── _store.py             # 核心存取（get, set, clear + _cache_lock）
│   ├── _stats.py             # 命中率 & 目录统计（get_cache_hit_rate, reset_cache_stats, get_cache_stats）
│   ├── _ttl.py               # TTL 解析（get_ttl, get_cache_age, get_cache_age_by_data_type）
│   ├── _cleanup.py           # 过期清理（cleanup_expired, _process_cache_file）
│   ├── _groups.py            # 组管理（clear_by_prefix, clear_by_group）
│   └── _groups.py            # 组管理（clear_by_prefix, clear_by_group）
├── services/                # 业务服务层（新建）
│   ├── __init__.py           # 子包标记（空文件）
│   └── holdings_tracker.py   # 持仓跟踪（check_and_refresh_caches 等 5 函数，经 cache/__init__.py re-export）
```

### 2.1 模块依赖关系

```
对外 public API（__init__.py 统一 re-export）
    │
    ├── _store.py  ─────────────→  _io.py, _paths.py
    ├── _cleanup.py ───────────→  _io.py, _paths.py, _ttl.py
    ├── _groups.py ─────────────→  _store.py, _paths.py, registry
    ├── _stats.py ──────────────→  _paths.py（get_cache_stats 需要读目录）
    ├── _ttl.py ────────────────→  config（lazy）, registry, market_hours, _paths.py, _io.py
    │
    ├── services/holdings_tracker →  cache._store, cache._paths, cache._groups
    │    （业务层，不属 cache/ 包，经 __init__.py re-export）
    │
    ├── _io.py ─────────────────→  _paths.py
    └── _paths.py ──────────────→  constants（PROJECT_ROOT）
```

### 2.2 锁定方案说明

以下设计决策在首轮即锁定，后续迭代不可变更：

| 决策 | 选择 | 理由 |
|:-----|:-----|:------|
| 子模块命名前缀 `_` | `_store.py`, `_ttl.py`... | 明确标记为内部模块，IDE 补全不优先展示 |
| 过渡文件命名 | `_legacy.py`（I-01 由 `cache.py` 重命名而来） | 保持 git blame 历史，I-07 删除 |
| `__init__.py` re-export | **显式** `from ._module import name` 而非 `from ._legacy import *` | `import *` 漏掉 `_` 前缀私有名（如 `_cache_lock`），显式导入可审计 |
| 全局状态集中 | `_cache_lock` 放 `_store.py` | 所有需要锁的函数通过导入同一变量共享 |
| stats 全局变量 | `_cache_hits` / `_cache_misses` 放 `_stats.py` | `_store.py` 中调 `_stats._record_hit()` |
| `__init__.py` 导入策略 | 采用 **eager import**（全量直接导入）；仅当 import 基准退化超过 1.2x 时切换为 `__getattr__` 延迟加载 | `__getattr__` 方案虽可节省 ~8-12ms 首轮导入，但增加认知复杂度（`_LAZY_MODULES` 映射 + 自定义 `__dir__`），对 TUI 应用无实际影响 |
| `CACHE_DAILY` 引用 | `_ttl.py` 从 `constants` 导入 | 保持 TTL 默认值来源中心化 |
| 提取顺序 | `_stats.py`（I-02）**先于** `_store.py`（I-03） | 避免 `_store.py` 导入 `_legacy.py` 形成循环依赖 |
| commit message 前缀 | 每轮 commit message 格式 `[cache/I-N] 标题`，标注"requires I-M" | 保证 git log 可追溯提取顺序，防止 cherry-pick 或误操作打乱依赖 |
| `from __future__ import annotations` | **仅**使用了联合类型语法（`str | None`、`int | float` 等）的子模块文件在头部添加 | 联合类型语法在 Python 3.9 下必须配合此导入才能正常工作；无需联合类型语法的模块（如 `_paths.py` 仅含 `-> str` 注解）可省略，减少模块编译阶段 AST 变换开销 |

### 2.3 运行时性能考量

#### 2.3.1 导入性能

拆分后 `cache/` 子包在首次 `from src.python.cache import ...` 时需加载 9 个文件（1 个 `__init__.py` + 8 子模块，`_protocol.py` 因 YAGNI 已从计划中淘汰），而原 monolithic `cache.py` 仅加载 1 个文件。Python 的模块缓存机制（`sys.modules`）保证重复导入仅做 O(1) 字典查找，无额外开销。关键在于**首轮导入**耗时。

**实际影响**：首轮启动时间增加约 5-15ms（取决于磁盘 I/O 和 Python 版本）。对 TUI 应用（菜单循环模式）无显著影响，因为缓存模块在报告生成前仅加载一次。测试场景下 `pytest --collect-only` 的收集时间可能增加 20-50ms，对 CI 门禁影响甚微。

**优化措施**：
1. `__init__.py` 中采用 eager import（全量直接导入），简化维护复杂度；如果实际 import 耗时退化超过 1.2x，再切换为模块级 `__getattr__` 延迟加载低频模块（`_cleanup`、`_groups`）
2. I-07 验收时手动运行 `timeit` 确认 import 耗时退化在可接受范围（阈值 1.2x）

#### 2.3.2 函数调用性能

所有跨子模块调用均通过直接函数引用（`from ._submodule import func`），Python 在模块初始化时将名字绑定到同一函数对象：
- `get()` 热路径中调用 `_cache_path`、`_read_cache_data`、`_record_cache_hit` → 均为跨模块导入的直接函数引用，无 wrapper/proxy 层
- `from cache import get` 与 `from cache._store import get` 返回同一函数对象（`id(get)` 相同），无 re-export 间接跳转

**结论**：热路径函数调用开销与 monolithic 版本完全一致，无可测差异（纳秒级偏差可忽略）。

#### 2.3.3 锁竞争

`_cache_lock` 仍是同一个 `threading.Lock()` 对象，跨模块导入不影响锁语义：
- `_store.py` 定义并持有锁
- `_groups.py` / `_cleanup.py` 通过 `from ._store import _cache_lock` 获取同一实例；`services/holdings_tracker.py` 通过 `set`/`clear` 间接使用锁，无需直接引用
- 所有锁的获取/释放均在同一锁对象上，无锁顺序问题，无新的死锁风险

#### 2.3.4 `__init__.py` 加载事项

`__init__.py` 本身体积极小（约 30 行 import 语句 + `__all__`），其执行时间主要由 `from ._xxx import ...` 触发的子模块编译/执行时间决定。eager vs lazy 加载策略的差异见 2.3.1 节。

### 2.4 未来可扩展性缺口

本次拆分以"保持语义不变"为首要原则，未对架构做超前抽象。以下为识别到的未来可扩展性缺口及对应的未来处理策略（均经成本/收益审查判定为当前 YAGNI，不纳入本轮计划）。

| 缺口 | 当前状态 | 未来变更成本 | 建议补救 | 对应迭代 |
|:-----|:---------|:-----------|:---------|:--------|
| **存储后端抽象** | `_io.py` 接口暴露 `fpath`/`fd`/`tmp_path`/`final_path` 等文件系统细节；`_store.py` 直接调用文件系统特定函数 | 替换 Redis/S3 需修改 `_store.py` + `_io.py` + `_paths.py` | 当实际需要替换后端时，定义 `StorageBackend` Protocol 并实现 `FileStorageBackend` 类 | 已淘汰（YAGNI） |
| **缓存格式版本化** | `{"_ts": ..., "_data": ...}` 无版本字段；`_read_cache_data` 无格式检测 | 更换 envelope 结构时无法区分新旧格式 | 当实际需要变更格式时，在 payload 中增加 `_version` 字段并实现兼容性校验 | 已淘汰（YAGNI） |
| **TTL 接口扩展性** | `get_ttl(data_type)` 仅接受数据类型，不支持逐 key 或自适应 TTL | 增加滑动窗口 TTL 需修改 `_store.py`（get 热路径）和 `_ttl.py`（接口和实现） | ~~将 `get_ttl` 接口扩展为 `get_ttl(data_type, key=None, context=None)`~~ → **YAGNI 淘汰**：无当前需求，接口扩展留到实际需要时按真实场景设计 | 已淘汰 |
| **异步兼容路径** | `threading.Lock` + 同步文件 I/O；无 asyncio 路径 | 整体切换 async 需改造 `_io.py` + `_store.py` + 所有 `from cache import` 的外部模块 | 当前拆分不阻塞异步化，但需注意 `_cache_lock` 在 `_store.py` 中的类型（`threading.Lock`）后续需切换为 `asyncio.Lock` | 非本轮范围 |

## 3. 迭代路线图（优化版：14 轮 → 7 轮）

**成本/收益优化说明**：以下为经过成本/收益收敛审查后的精简路线图，相比原 14 轮方案削减 50% 迭代数，节省约 44% 工时。合并原则：(1) 无依赖关系的叶子模块提取合并到同一迭代（I-01 中同时提取路径+IO）；(2) 相互独立的业务模块合并到同一迭代（I-05 同时提取清理+组管理）；(3) 纯文档类收尾工作合并到同一迭代（I-07 包含删除 _legacy + 全量文档同步 + 开发者指引）。已淘汰的 5 项迭代（测试拆分、import 基准、存储后端抽象、缓存版本化、TTL 接口扩展）附 YAGNI 理由，见末尾「已淘汰的迭代」。

### 【已完成】 I-01: 建包 + 路径/常量 + 文件 IO

**目标**：建立 `cache/` 子包目录结构，同时提取无依赖的路径常量和文件读写逻辑，一次完成三个叶子模块的创建。

**合并依据**：
- `_paths.py`（原 `cache.py` 中 20 行）和 `_io.py`（70 行）均为叶子模块，仅依赖 `constants` 和标准库
- `_paths` 被 `_io` 使用，但二者可同时创建（彼此不构成循环依赖）
- 合并节省两个完整迭代周期（~16min），零额外风险

**0. mock 路径预审计**（I-01 前置步骤，执行前必检）：
    在修改任何文件之前，先生成当前代码库中所有 cache patch 路径的完整清单，与下文迁移表对照，确保无遗漏：
    ```bash
    grep -rn 'patch.*\.cache\.\|monkeypatch.*\.cache\.' src/test/ --include="*.py" \
      | grep -oP 'src\.python\.cache[\._]\w+' | sort -u > docs-stm/tmp/cache-patch-paths.txt
    ```
    输出文件为 `docs-stm/tmp/cache-patch-paths.txt`，与"测试 mock 路径迁移"节的 5 类迁移表逐行对照。
    **确认全部覆盖且无遗漏后再执行后续步骤**。

**重要背景（Python 限制，必须一次完成）**：
Python 3 不允许同名的 `.py` 模块文件和包目录在同一个目录中共存。
若同时存在 `src/python/cache.py`（模块）和 `src/python/cache/`（目录），
`import src.python.cache` 会解析为**包**而非模块，`cache.py` 的内容被完全屏蔽，
通过正常导入路径**不可访问**。因此本步骤必须一次性完成重命名 + 建包，
不能分两步走（先建 `cache/` 空目录、后续再迁移）。

**改动**：
1. `git mv src/python/cache.py src/python/cache/_legacy.py`
   — 重命名原文件，`blame` 历史保持完整
2. 创建 `src/python/cache/__init__.py`，**显式** re-export 所有需要保持兼容的 name：
   ```python
   """缓存引擎子包。"""
   from ._legacy import (
       # ── 公共 API ──
       get, set, clear,
       get_cache_hit_rate, reset_cache_stats, get_cache_stats,
       get_ttl, get_cache_age, get_cache_age_by_data_type,
       cleanup_expired,
       clear_by_prefix, clear_by_group,
       check_and_refresh_caches, compute_holdings_fingerprint, compute_holdings_codes,
       get_cache_dir,
       # ── 公共常量（保持 from cache import CACHE_DAILY 兼容）──
       CACHE_DAILY,
       # ── 内部接口（被子模块或外部引用）──
       _cache_lock, _cache_path, _CACHE_DIR, _GZIP_THRESHOLD, _GZIP_SUFFIX,
       _read_cache_data, _write_atomic,
       _record_cache_hit, _record_cache_miss,
   )

   __all__ = [
       "get", "set", "clear",
       "get_cache_hit_rate", "reset_cache_stats", "get_cache_stats",
       "get_ttl", "get_cache_age", "get_cache_age_by_data_type",
       "cleanup_expired",
       "clear_by_prefix", "clear_by_group",
       "check_and_refresh_caches", "compute_holdings_fingerprint", "compute_holdings_codes",
       "get_cache_dir",
       # ── 公共常量（test_cache.py 有 3 处 from cache import CACHE_DAILY）──
       "CACHE_DAILY",
       # ── 内部接口（外部消费者不应依赖，但已有测试使用）──
       "_cache_lock", "_cache_path",
   ]
   ```
3. 创建 `src/python/cache/_paths.py`，移入（20 行）：
   - `_CACHE_DIR`, `_GZIP_THRESHOLD`, `_GZIP_SUFFIX`（模块级常量）
   - `_cache_path(key)` — 路径构造函数
   - `get_cache_dir()` — 公开路径查询
4. 创建 `src/python/cache/_io.py`，移入（70 行）：
   - `_read_cache_data(fpath, key, dry_run=False)` — 读取并解析单个缓存文件
   - `_write_atomic(fd, tmp_path, final_path, path, json_str, raw_bytes, use_gzip)` — 原子写入
5. 更新 `_legacy.py`：删除上述 7 项定义，新增 `from ._paths import ...` 和 `from ._io import ...`
6. **清理 `__pycache__` 残留字节码**：
   `git mv` 后 `src/python/__pycache__/` 下可能残留旧 `cache.py` 模块的字节码缓存
   （`cache.cpython-*.pyc`）。虽然 Python 在新包导入时不会使用此文件（路径不匹配，
   新包在 `cache/__pycache__/` 下生成新字节码），但为保险执行清理：
   ```bash
   find src/python/ -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
   ```

7. **前置安全验证**（mock 路径迁移前必检）：

   - **验证 registry 模块级 cache 导入安全**：确保 I-03 `_store.py` 和 I-05 `_cleanup.py`/`_groups.py` 在模块级导入 registry 函数时不会触发循环导入：
     ```bash
     grep -n "^from.*cache import\|^import.*cache" src/python/registry.py || echo "OK: registry 无模块级 cache 导入"
     ```
     如果输出非空（registry 在模块级导入了 cache），则 cleanup/groups 对 registry 的导入必须改为函数内 lazy import。

   - **修复 conftest.py 缓存路径隔离夹具（C13 约束）**：`_isolate_sensitive_paths` autouse fixture（`conftest.py:109`）使用 `monkeypatch.setattr("src.python.cache._CACHE_DIR", ...)`。I-01 后 `_CACHE_DIR` 移至 `_paths.py`，此 patch 仅改 `__init__._CACHE_DIR`，不涉及 `_paths._CACHE_DIR` 和 `_legacy._CACHE_DIR`，所有测试无声写入真实 `data/cache/`。**必须改为双路径 patch**：
     ```python
     # 替换 conftest.py _isolate_sensitive_paths 中的 monkeypatch.setattr 行：
     
     # I-01~I-07: 直接 patch 定义源 _paths._CACHE_DIR（长期有效）
     monkeypatch.setattr(
         "src.python.cache._paths._CACHE_DIR",
         str(tmp_path / "data/cache"),
     )
     # I-01~I-06 兼容期: _legacy 在模块加载时 from ._paths import _CACHE_DIR
     # 做了本地绑定，即使 _paths._CACHE_DIR 已改，_legacy._CACHE_DIR 仍指向旧值
     try:
         monkeypatch.setattr(
             "src.python.cache._legacy._CACHE_DIR",
             str(tmp_path / "data/cache"),
         )
     except AttributeError:
         pass  # I-07 后 _legacy 已删除，忽略即可
     ```

**为什么不直接用 `from ._legacy import *`？**
- `cache.py` 没有定义 `__all__`，默认 `import *` 只导入非 `_` 开头的公开名，
  会漏掉 `_cache_lock`、`_cache_path` 等私有名。显式导入更安全、可审计。
- `__all__` 同时作为公共 API 文档清单。

**子模块命名前缀约定**：使用单下划线 `_` 前缀（如 `_paths.py`），
明确标记为内部模块，IDE 代码补全不优先展示。此约定在 I-01 即锁定，
后续迭代不可变更。

### 跨分支兼容性与合并冲突风险

Python 3 不允许同名 `.py` 模块文件和包目录在 `sys.path` 同一入口中共存。
当两个 git 分支分别持有旧结构（`cache.py` 模块）和新结构（`cache/` 子包）时，
合并会产生 **树冲突**——Git 无法自动判定 `cache.py` 的删除与 `cache/` 目录的
新增是同一重构的两个面。

**具体场景**：
- 分支 A 基于 dev 在拆分前创建，持有 `src/python/cache.py`
- 分支 B（或 dev 本身）已完成 I-01，持有 `src/python/cache/` 子包 + `_legacy.py`
- 将分支 A 合入 dev 时，Git 看到 `cache.py` 在 A 中"修改"、在 dev 中"删除并替换为目录"
  → 树冲突，`cache.py` 和 `cache/` 同时出现 → Python import 完全失效

**缓解措施**：
1. **拆分期间统一在 dev 分支完成**，所有 cache 拆分提交（I-01 ~ I-07）仅在 dev 上累积，
   其他功能分支**暂时避免接触 `src/python/cache.py` / `cache/`**。
2. **I-07 前冻结非拆分分支**的缓存相关修改。确需修改的，优先在 dev 完成 I-01 后再建分支。
3. **如已发生合并冲突**，手动修复步骤：
   ```bash
   # 1. 接受新结构，丢弃旧模块
   git rm src/python/cache.py              # 如果还存在
   git checkout --theirs src/python/cache/  # 接受 branch 的 cache/ 子包
   # 2. 验证导入
   python -c "from src.python.cache import get; print('OK')"
   # 3. 运行回归
   pytest src/test/ -m "unit_core or scenario or scenario_basic" --collect-only
   ```
4. **在 I-07 之前，禁止将拆分中的 cache/ 子包 cherry-pick 到其他分支**。
   即使 `__init__.py` re-export 保持兼容，`cache/` 目录的出现会屏蔽
   旧分支上可能存在的 `cache.py` 模块，造成无声导入失败。

**测试 mock 路径迁移（I-01 前置/并行步骤）**：

`src.python.cache` 从模块变为包后，所有不在 `__init__.py` re-export 列表中的名字将从包命名空间中消失，导致以下测试 mock 路径失效。**须在 I-01 提交前完成迁移，否则 `pytest` 回归会大面积报错。**

| 旧 patch 路径（I-01 后失效） | 替换路径 | 文件 | 涉及测试数 |
|:----------------------------|:---------|:-----|:---------:|
| `src.python.cache.time.time` | `time.time` | `test_cache.py`, `test_cache_edge.py` | ~40 |
| `src.python.cache.os.remove` | `os.remove` | `test_cache.py` | 3 |
| `src.python.cache.tempfile.mkstemp` | `tempfile.mkstemp` | `test_cache.py` | 2 |
| `src.python.cache.os.replace` | `os.replace` | `test_cache.py` | 1 |
| `src.python.cache._is_market_open` | `src.python.market_hours.is_market_open` | `test_cache.py`, `test_cache_edge.py`, `test_datetime_scenarios.py` | ~16 |
| `src.python.cache._CACHE_DIR` | `src.python.cache._paths._CACHE_DIR` + conftest 双路径 patch（见上节"修复 conftest.py"） | `test_cache.py`, `test_cache_edge.py`, `test_filesystem_edge.py`, `test_security_edge.py`, `test_datetime_scenarios.py`, `conftest.py` | ~8 + 1(conftest) |

**迁移原则**：
1. **标准库名称**（`time`, `os`, `tempfile`）：直接改为全局 patch 路径。测试已通过 `_CACHE_DIR` 隔离到临时目录，全局 patch `time.time` 不影响其他模块。
2. **私有导入别名**（`_is_market_open`）：改为对**原定义模块**打补丁 `src.python.market_hours.is_market_open`，此路径在所有迭代中均有效（`_ttl.py` 中的 `from market_hours import is_market_open as _is_market_open` 是引用同一函数对象）。
3. **`_CACHE_DIR`（模块级常量引用）**：**必须**在 I-01 中迁移（与路径提取同时完成）。因为 `from ._paths import _CACHE_DIR` 创建的是子模块本地引用，
   `patch("src.python.cache._CACHE_DIR")` 仅修改 `__init__._CACHE_DIR` 而不影响 `_paths._CACHE_DIR`，
   遗留函数查找的仍是原始值。改为 `patch("src.python.cache._paths._CACHE_DIR")` 直接对定义模块打补丁（此路径从 I-01 到 I-07 均有效）。

**注意**：替换后可能因 patch 目标的变化导致部分测试行为差异（例如全局 `time.time` patch 会影响测试中其他模块的 `time.time` 调用）。对于测试中调用了 `time.sleep`、`time.time` 等函数的场景，建议在测试执行窗口内通过 `importlib.reload()` 或函数内 `import` 确保加载顺序正确。如有冲突，可改为对具体子模块打补丁（如 `patch("src.python.cache._legacy.time.time")` 在 I-01~I-09 短期兼容）。确认全部迁移完毕且回归通过后再进入下一步。

**风险**：**高**（更新为实际评估）。原计划标注 I-01 风险为"中"，但实际约 60 个测试 mock 路径需同时迁移，遗漏任一都会导致回归失败：
1. 替换后运行 `pytest src/test/ -m "unit_core" --collect-only` 确认收集项数未减少
2. 再运行完整 `pytest src/test/ -m "unit_core or scenario or scenario_basic"` 全通过
3. 兼容方案：如有冲突测试，可临时补丁到 `src.python.cache._legacy.X` 路径（I-01~I-07 期内有效 — I-07 删除 `_legacy.py` 后此路径失效，必须在此之前切换为永久路径）

**验收**：
- `from src.python.cache import get, set, get_ttl` 均正常工作
- `from src.python.cache import _cache_lock, _cache_path` 也正常工作
- `python -c "from src.python.cache import get; assert get('_nonexistent_z6_test_key_') is None; print('smoke OK')"` — 功能冒烟测试（验证 import + 核心函数可执行）
- `pytest src/test/ -m "unit_core or scenario or scenario_basic"` 全通过
- `grep -n "src\.python\.cache\._CACHE_DIR\|src\.python\.cache\._cache_path" src/test/conftest.py` — 确认 C13 隔离夹具无残留旧路径

**文档管理**：
- `changelog.md`：在 `[Unreleased]` → `### Changed` 追加 `cache/ 子包拆分: I-01 建包 + _legacy.py 过渡（原 cache.py→cache/_legacy.py，__init__.py 显式 re-export）`
- `review-findings.md`：如有测试 mock 路径迁移发现（如 I-01 风险中列出的 ~60 处 mock 路径），记录为"待处理"条目
- 本文档：迭代标题旁标注 `【已完成】`，并在"## 4. 风险矩阵"中勾选对应风险为已验证
- commit message 格式：`[cache/I-01] 建包 + 路径/常量 + 文件 IO (requires I-02)` — 方便 git log 追溯依赖顺序

**回退**：
- `git revert <commit>` 一步还原：删除 `cache/` 目录，恢复 `src/python/cache.py`
- 或者手动：`git mv cache/_legacy.py cache.py` 后 `git rm -r cache/`

---

### 【已完成】 I-02: 提取命中率统计 → `_stats.py`（先于 `_store.py` 提取）

**目标**：将缓存命中率追踪和目录统计独立。**必须先于 I-05（store 提取）完成**，
因为 `_store.py` 的 `get()` 需要调用 `_record_cache_hit/miss`，如果 `_stats.py` 尚未存在，
`_store.py` 只能从 `_legacy.py` 导入，形成**循环依赖**（_legacy ← _store 双向引用）。

**移入 `_stats.py`**：
- `_cache_stats_lock`（模块级 threading.Lock）
- `_cache_hits: int`（模块级全局变量）
- `_cache_misses: int`（模块级全局变量）
- `_record_cache_hit()`
- `_record_cache_miss()`
- `get_cache_hit_rate()` — 公开 API
- `reset_cache_stats()` — 公开 API
- `get_cache_stats()` — 目录级统计（依赖 `_paths.py`）

**`_cache_stats_lock 去留判断`**（执行提取前必须确认）：
原始 `cache.py` 中 `_cache_hits += 1` 和 `_cache_misses += 1` 是模块级 int 的原子自增（CPython GIL 保护，单字节码操作），**无需独立锁**。在提取前通过以下方式确认：
```bash
grep -n "_cache_hits\|_cache_misses" src/python/cache.py | head -10
```
- 如果原始代码中所有 stats 变量修改均**无** `_cache_lock` 保护（靠 GIL 隐含安全）：则 `_cache_stats_lock` 是冗余的，I-02 中取消创建，改为注释说明"GIL 保护 int 原子自增，无锁"
- 如果原始代码用 `_cache_lock` 保护了 stats 变量（预计不会，因为 `get()` 热路径中已有 `_cache_lock`，不可能在内层再次加 `_cache_lock` 保护同一个 int 自增）：则 I-02 时从 `_legacy` 导入 `_cache_lock`（因 I-03 尚未提取 `_store`），并在 I-03 完成后 PR 中切换到 `from ._store import _cache_lock`

**`_stats.py` 新增导入**：
- `from ._paths import _CACHE_DIR`（`get_cache_stats` 需要缓存目录路径）
- `import threading, os, logging`
- `logger = logging.getLogger("invest")`

**`_legacy.py` 变更**：
- 删除 `_cache_stats_lock`, `_cache_hits`, `_cache_misses`, 上述 4 函数
- 新增 `from ._stats import get_cache_hit_rate, reset_cache_stats, get_cache_stats, _record_cache_hit, _record_cache_miss`

**风险**：低。统计函数为纯只读/写入，无业务逻辑变化。
注意后续 I-05 的 `_store.py` 导入 `_record_cache_hit/miss` 时从 `_stats` 导入，而非从 `_legacy`。

**测试观察**：`_cache_hits`/`_cache_misses` 是模块级全局变量（非持久化状态），测试中仅通过 `get_cache_hit_rate()` / `reset_cache_stats()` 间接访问，无直接 `patch` 引用。
`get_cache_stats()` 的测试依赖 `_CACHE_DIR` patch（已在 I-01 处理），无需额外变更。

**验收**：
- `from src.python.cache import get_cache_hit_rate, reset_cache_stats, get_cache_stats` 正常
- 多次 get/set 后命中率 > 0
- `get_cache_stats()` 正确返回文件数量和大小
- `python -c "from src.python.cache import get_cache_hit_rate; print('import OK')"` — 冒烟测试
- 回归测试全通过

**文档管理**：
- `changelog.md`：追加 `I-02 提取 _stats.py（缓存命中率统计 / 目录统计，先于 _store 提取以避免循环依赖）`
- `review-findings.md`：如发现 `_cache_stats_lock` 导入路径变更影响测试，记录"待处理"

**回退**：`git revert <commit>` — `_stats.py` 被删除，`_legacy.py` 恢复统计函数定义。

---

### 【已完成】 I-03: 提取核心存取 → `_store.py`

**目标**：将 `get()` / `set()` / `clear()` 三个最核心的公开 API 移至 `_store.py`，这是最关键的迭代——影响所有调用方。

**前提**：I-04（_stats.py）必须已经完成，因为 `get()` 中调用 `_record_cache_hit/miss`，
`_store.py` 直接导入 `_stats` 模块，避免与 `_legacy.py` 形成循环依赖。

**移入 `_store.py`**：
- `_cache_lock`（模块级 threading.Lock）
- `get(key, max_age_seconds)` — 读取缓存
- `set(key, data)` — 写入缓存
- `clear(key)` — 删除单个缓存

**`_store.py` 新增导入**：
- `from ._paths import _cache_path, _GZIP_THRESHOLD, _GZIP_SUFFIX`（路径构造 + gzip 阈值与后缀）
- `from ._io import _read_cache_data, _write_atomic`（文件读写）
- `from ._stats import _record_cache_hit, _record_cache_miss`（命中率记录，I-04 已就绪）
- `time`, `logging`, `json`, `gzip`, `tempfile`, `os`, `contextlib`（与原来一致）
- `logger = logging.getLogger("invest")`

**`_legacy.py` 变更**：
- 删除 `_cache_lock`, `get()`, `set()`, `clear()`
- 新增 `from ._store import _cache_lock, get, set, clear`

**消除循环依赖确认**（执行前必检）：
- `_store.py` → `_paths.py` ✓（叶子模块，仅依赖 constants）
- `_store.py` → `_io.py` ✓（需 `paths` 先就绪，I-03 已就绪）
- `_store.py` → `_stats.py` ✓（需 stats 先就绪，I-04 已就绪）
- `_legacy.py` → `_store.py` ✓（单向依赖，_store 不回溯引用 _legacy）
- 不存在任何双向 import 链

**风险**：中。这是最大的一次移动（~130 行），影响 ~20 个调用方。风险在于：
1. `set()` 中重试逻辑复杂（FileNotFoundError → 重建目录 → 重试写入）
2. `get()` 中 gz/非 gz 双路径回退
3. `_cache_lock` 被 `clear_by_prefix()`, `cleanup_expired()` 等引用

**缓解措施**：
- `_cache_lock` 仍然从 `_store.py` 导出，其他模块 `from ._store import _cache_lock`
- 移动后手动检查 get/set 的 6 条逻辑分支路径正确性
- 运行完整 unit_core + scenario_basic 回归

**测试 mock 路径验证**：
I-05 后 `get()`/`set()`/`clear()` 所在的 `_store.py` 具备独立的 `import time`、`import os`、`import tempfile`。
如果 I-01 阶段已将 mock 路径改为全局 `patch("time.time")` / `patch("os.remove")` / `patch("tempfile.mkstemp")`，
则此迭代无需调整——全局 patch 对 `_store.py` 的 `time`/`os`/`tempfile` 同样生效。
如果有未迁移的残留 mock 路径（如 `patch("src.python.cache._legacy.time.time")`），此迭代**必须**修复，
因为 `_legacy.py` 不再包含 `get`/`set`/`clear` 且不再 `import time` 用于缓存操作，
`_legacy.time.time` 因 `_legacy` 中无 import 而不可访问（或指向无关的时间调用）。
验证方式：运行 `pytest src/test/ -m "unit_core" -k "TestCacheGet or TestCacheSet or TestCacheClear"` 确认全部通过。

**验收**：
- `from src.python.cache import get, set, clear` 正常
- `get()` 缓存命中/过期/不存在三种状态正确
- `set()` 普通 / gzip / 重试三种路径正确
- `clear()` 删除 .json 和 .json.gz 均正确
- `python -c "from src.python.cache import get; print('import OK')"` — 冒烟测试
- 回归测试全通过

**文档管理**：
- `changelog.md`：追加 `I-03 提取 _store.py（get/set/clear 核心存取，最关键的迭代——影响所有 ~20 个调用方）`
- `review-findings.md`：如发现残留 `_legacy.time.time` mock 路径未迁移或 `_GZIP_THRESHOLD`/`_GZIP_SUFFIX` 遗漏导入，立即记录

**回退**：`git revert <commit>` — `_store.py` 被删除，`_legacy.py` 恢复 get/set/clear/_cache_lock 定义。

---

### 【已完成】 I-04: 提取 TTL → `_ttl.py`

**目标**：将 TTL 查询逻辑独立。

**移入 `_ttl.py`**：
- `get_ttl(data_type)` — 交易时段感知 TTL 解析（含 market_hour_aware 逻辑）
- `get_cache_age(key)` — 按键名查缓存年龄
- `get_cache_age_by_data_type(data_type, identifier)` — 按数据类型查缓存年龄（含 profit_forecast 特殊处理）

**`_ttl.py` 新增导入**：
- `from ._paths import _cache_path, _GZIP_SUFFIX`（get_cache_age 的路径构造 + gzip 后缀）
- `from ._io import _read_cache_data`（get_cache_age 读取文件）
- `from src.python.market_hours import is_market_open as _is_market_open`（market_hour_aware 判断）
- `from src.python.registry import get_cache_ttl_defaults`（TTL 默认值）
- `get_registry` 由 `get_cache_age_by_data_type` 在函数内 lazy import（避免循环依赖）
- `from src.python.constants import CACHE_DAILY`（兜底默认 TTL）
- `from src.python.config import get_config`（lazy，在 get_ttl 函数内导入）
- `import logging, time`
- `logger = logging.getLogger("invest")`

**缓存年龄与 TTL 的去留判断**：`get_cache_age()` 的功能本质是"读取缓存文件并提取时间戳"，与 `get_ttl()` 的"根据数据类型查 TTL"在概念上属于同一关注点（缓存时间的查询），故放在同一模块。

**`_legacy.py` 变更**：
- 删除 `get_ttl()`, `get_cache_age()`, `get_cache_age_by_data_type()`
- 新增 `from ._ttl import get_ttl, get_cache_age, get_cache_age_by_data_type`

**风险**：低。纯查询函数，无状态修改。注意 `get_ttl()` 内部 lazy 导入 `config` 的逻辑保持不变。

**测试 mock 路径注意点**：
`_ttl.py` 中 `get_ttl` 使用 `from src.python.market_hours import is_market_open as _is_market_open` 创建了新的模块级别名。
如果 I-01 阶段已将测试中的 `patch("src.python.cache._is_market_open")` 迁移为 `patch("src.python.market_hours.is_market_open")`，
则此迭代无需额外测试变更。如果 I-01 采取了临时兼容方案（如 `patch("src.python.cache._legacy._is_market_open")`），
则此迭代**必须**将其更新为 `patch("src.python.market_hours.is_market_open")`，
因为 `_legacy.py` 不再导入 `_is_market_open`（已移至 `_ttl.py`），`cache._legacy._is_market_open` 不再存在。
验证方式：运行 `pytest src/test/ -m "unit_core" -k "TTL or ttl or get_ttl"` 确认全部通过。

**验收**：
- `from src.python.cache import get_ttl, get_cache_age` 正常
- get_ttl 在盘中/盘后返回正确的 TTL
- get_cache_age_by_data_type 的 profit_forecast 特殊处理仍然有效
- `python -c "from src.python.cache import get_ttl; print('import OK')"` — 冒烟测试
- 回归测试全通过

**文档管理**：
- `changelog.md`：追加 `I-04 提取 _ttl.py（get_ttl/get_cache_age/get_cache_age_by_data_type + 交易时段感知 TTL）`
- `review-findings.md`：如发现 `_is_market_open` mock 路径兼容问题（I-01 临时方案到期失效），记录并修复

**回退**：`git revert <commit>` — `_ttl.py` 被删除，`_legacy.py` 恢复 3 函数定义。

---

### 【已完成】 I-05: 提取过期清理 + 组管理 → `_cleanup.py` + `_groups.py`

**目标**：将过期清理逻辑和缓存分组管理同时提取为独立模块。

**合并依据**：
- `_cleanup.py`（80 行）和 `_groups.py`（70 行）均依赖 `_store`、`_paths` 且互不依赖
- 二者可并行提取（不同模块，无交叉引用）
- 合并节省一个完整迭代周期（~16min），零额外风险

**移入 `_cleanup.py`**：
- `_process_cache_file(fname, dry_run, prefix_type_map, exact_map)` — 单文件过期判断
- `cleanup_expired(dry_run=False)` — 全目录扫描清理

**移入 `_groups.py`**：
- `clear_by_prefix(key_prefix)` — 按前缀批量清除
- `clear_by_group(group_name)` — 按 registry 分组清除

**新增导入**（`_cleanup.py`）：
- `from ._paths import _CACHE_DIR, _GZIP_SUFFIX`
- `from ._io import _read_cache_data`
- `from ._store import _cache_lock`
- `from ._ttl import get_ttl`
- `from src.python.registry import get_prefix_type_map, get_exact_type_map`
- `import os, logging, time`

**新增导入**（`_groups.py`）：
- `from ._paths import _CACHE_DIR, _cache_path`
- `from ._store import clear, _cache_lock`
- `from src.python.registry import get_registry`
- `import os, logging`

**`_legacy.py` 变更**：
- 删除 `_process_cache_file()`, `cleanup_expired()`
- 删除 `clear_by_prefix()`, `clear_by_group()`
- 新增 `from ._cleanup import cleanup_expired`
- 新增 `from ._groups import clear_by_prefix, clear_by_group`

**风险**：低。两个模块均直接调用下层模块函数，无状态共享或循环依赖风险。

**验收**：
- `from src.python.cache import cleanup_expired` 正常
- `from src.python.cache import clear_by_prefix, clear_by_group` 正常
- 过期文件在 `cleanup_expired()` 后正确删除
- `clear_by_prefix("fund_perf_")` 正确删除匹配文件
- `python -c "from src.python.cache import cleanup_expired, clear_by_prefix; print('import OK')"` — 冒烟测试
- 回归测试全通过

**文档管理**：
- `changelog.md`：追加 `I-05 提取 _cleanup.py + _groups.py（过期清理 + 组管理，合并迭代）`
- `review-findings.md`：如 `_cache_lock` 导入路径不一致导致锁失效，紧急记录

**回退**：`git revert <commit>` — `_cleanup.py` 和 `_groups.py` 被删除，`_legacy.py` 恢复 4 函数定义。

---

### 【已完成】 I-06: 提取持仓跟踪 → `src/python/services/holdings_tracker.py`

**目标**：将持仓指纹检测逻辑独立，**直接放入正确的架构层次（`services/` 目录）**，`cache/` 包保持纯基础设施职责。

**新增 `src/python/services/` 目录**：
- `__init__.py` — 子包标记（空文件）

**移入 `services/holdings_tracker.py`**：
- `compute_holdings_fingerprint(holdings)` — 持仓指纹计算
- `compute_holdings_codes(holdings)` — 代码集合提取
- `_read_holdings_tracking(tracking_key)` — 读取上次跟踪数据
- `_clear_holdings_related_caches()` — 清除关联缓存
- `check_and_refresh_caches(holdings)` — 主入口（被 `handlers_report.py` 调用）

**`holdings_tracker.py` 新增导入**：
- `from src.python.cache._paths import _cache_path`（读取跟踪文件路径）
- `from src.python.cache._store import set, clear`（写入跟踪数据 + 清除基准缓存）
- `from src.python.cache._groups import clear_by_prefix`（清除 industry_* 缓存）
- `hashlib`, `json`, `logging`, `os`, `builtins`（标准库）
- `logger = logging.getLogger("invest")`

**`cache/__init__.py` 变更**（确保调用方完全透明）：
- 新增 `from src.python.services.holdings_tracker import check_and_refresh_caches, compute_holdings_fingerprint, compute_holdings_codes`
- 这三个函数加入 `__all__` 列表

**`_legacy.py` 变更**：
- 删除 `compute_holdings_fingerprint()`, `compute_holdings_codes()`, `_read_holdings_tracking()`, `_clear_holdings_related_caches()`, `check_and_refresh_caches()`
- 新增 `from src.python.services.holdings_tracker import check_and_refresh_caches, compute_holdings_fingerprint, compute_holdings_codes`

**架构决策理由**：
- 持仓跟踪是**业务逻辑**（持仓变更检测），而非缓存基础设施。将其放入 `cache/` 包会混合架构层次
- 调用方 `tui_handlers.py` 通过 `from src.python.cache import check_and_refresh_caches` 使用，`cache/__init__.py` 的 re-export 确保**调用方零改动**
- `services/` 目录目前仅此一个模块，后续可容纳更多业务服务模块
- **不做技术债推迟**——一步到位放在正确位置

**风险**：低。纯业务逻辑移动，无循环依赖。`holdings_tracker.py` 仅依赖 `cache._paths`, `cache._store`, `cache._groups`（均为下层模块）。

**验收**：
- `from src.python.cache import check_and_refresh_caches, compute_holdings_fingerprint` 正常（re-export 生效）
- `from src.python.services.holdings_tracker import check_and_refresh_caches` 正常（直接导入也生效）
- 指纹相同 → 返回 `[]` 不变
- 指纹变更且代码无新增 → 清除关联缓存，返回 `[]` 不变
- 指纹变更且代码有新增 → 返回新增代码列表
- `python -c "from src.python.cache import check_and_refresh_caches; print('import OK')"` — 冒烟测试
- 回归测试全通过

**文档管理**：
- `changelog.md`：追加 `I-06 提取 services/holdings_tracker.py（持仓指纹检测 check_and_refresh_caches / compute_holdings_fingerprint 等 5 函数，直接放入 services/ 目录，cache re-export 保持兼容）`
- `review-findings.md`：记录 `services/` 目录创建，无需后续迁移

**回退**：`git revert <commit>` — `services/holdings_tracker.py` 和 `services/__init__.py` 被删除，`cache/__init__.py` 和 `_legacy.py` 恢复 re-export。

---

### 【已完成】 I-07: 删除 `_legacy.py` + 全量文档同步 + 开发者指引

**目标**：删除过渡性的 `_legacy.py`（原名 `cache.py`），`__init__.py` 改为直接从子模块导入，同时完成全量文档审计和开发者指引更新。

**合并依据**：
- I-10（删除 _legacy）、I-12（文档同步）、I-13（开发者指引）均为收尾性事务，无执行顺序依赖
- 一次完成减少两次独立提交流程，节省 ~40min
- 文档审计必须在删除 _legacy 后执行（缓存路径引用已变更），天然适合同一迭代

**变更**：
1. `git rm src/python/cache/_legacy.py`
2. 更新 `src/python/cache/__init__.py` 为直连导入：

   **首选方案（eager import，推荐）** — 全量直接导入，避免 `__getattr__` 复杂度。注意：`__all__` 中不暴露文件系统级内部接口（`_cache_path`、`_read_cache_data`、`_write_atomic`），以对齐 C2 约束。测试文件如需这些接口，改为 `from src.python.cache._paths import _cache_path` / `from src.python.cache._io import _read_cache_data`：
   ```python
   """缓存引擎子包。"""
   from ._store import get, set, clear, _cache_lock
   from ._stats import get_cache_hit_rate, reset_cache_stats, get_cache_stats
   from ._ttl import get_ttl, get_cache_age, get_cache_age_by_data_type
   from ._cleanup import cleanup_expired
   from ._groups import clear_by_prefix, clear_by_group
   # 持仓跟踪位于 services/ 目录（业务层），通过 cache 包 re-export 保持兼容
   from src.python.services.holdings_tracker import check_and_refresh_caches, \
       compute_holdings_fingerprint, compute_holdings_codes
   from ._paths import get_cache_dir, _CACHE_DIR
   # ── 公共常量（保持 from cache import CACHE_DAILY 兼容）──
   from src.python.constants import CACHE_DAILY

   __all__ = [
       # ── 公共 API ──
       "get", "set", "clear",
       "get_cache_hit_rate", "reset_cache_stats", "get_cache_stats",
       "get_ttl", "get_cache_age", "get_cache_age_by_data_type",
       "cleanup_expired",
       "clear_by_prefix", "clear_by_group",
       "check_and_refresh_caches", "compute_holdings_fingerprint", "compute_holdings_codes",
       "get_cache_dir",
       # ── 公共常量（test_cache.py 有 3 处 from cache import CACHE_DAILY）──
       "CACHE_DAILY",
       # ── 内部接口（测试文件直接导入，必须保留）──
       "_cache_lock",
   ]
   ```

   **备选方案（__getattr__ 延迟加载）** — 如果 import 耗时基准显示退化超过 1.2x，切换为 `__getattr__` 延迟加载 `_cleanup`/`_groups`。当前代码库中 `get()`/`set()` 热路径与 `cleanup_expired()`/`clear_by_group()` 低频操作分离明确，但 eager 方案更简单易维护，推荐优先使用。

3. **`_legacy.py` 空壳验证**（删除前必检）：
   - `grep -n "^def \|^class " src/python/cache/_legacy.py` — 确认无残余函数/类定义
   - 如有残余：返回对应迭代完成提取，不得携带函数定义直接删除
   - 验证通过后再执行 grep 三重检查

4. **私有函数导入验证**（删除前必检）：
   - `grep -rn "from src\.python\.cache import.*_record_cache" src/` — 确认无外部代码导入 `_record_cache_hit/miss`（当前已知：无；如有则需加入 `__init__.py` 的 re-export 和 `__all__`）
   - `grep -rn "from src\.python\.cache import.*_GZIP" src/` — 确认无外部代码导入 `_GZIP_THRESHOLD`/`_GZIP_SUFFIX`（当前已知：无；如有则需加入 `__init__.py`）

4b. **`__all__` 精简（必选，对齐 C2 约束）**：
    从最终 `__init__.py` 的 `__all__` 中移除 `_cache_path`、`_read_cache_data`、`_write_atomic` 三个内部接口——这些接口暴露了底层文件系统操作，允许外部模块绕过 `get()`/`set()` 直接读写缓存文件，违反 C2 约束。
    ```bash
    # 检查这三个私有接口在当前测试代码中的引用情况（共 13 处，4 文件）
    grep -rn "from src\.python\.cache import.*_cache_path\|_read_cache_data\|_write_atomic" src/ --include="*.py" | grep -v ".pyc"
    # 精确分布:
    #   test_cache.py           → _cache_path       × 4
    #   test_cache_edge.py      → _read_cache_data  × 1
    #   test_filesystem_edge.py → _cache_path       × 4
    #   test_security_edge.py   → _cache_path       × 3
    #   test_security_edge.py   → _write_atomic     × 1
    # 合计 13 处 import 引用，分布在 4 个测试文件
    ```
    将每个引用迁移为直接导入目标子模块（如 `from src.python.cache._paths import _cache_path` / `from src.python.cache._io import _read_cache_data`），然后从 `__init__.py` 的 `__all__` 和 import 语句中移除这些接口。注意：移除后需再次运行全量回归验证。

5. **grep 三重检查**（执行后必检）：
   - `grep -rn "_legacy" src/test/` — 确认无测试 mock 路径引用 `cache._legacy`
   - `grep -rn "_legacy" src/python/` — 确认无 src 代码引用
   - `grep -rn "cache\._legacy\|cache\._legacy" . --include="*.py" --exclude-dir=.venv` — 广义搜索

6. **全量文档同步（6 份文件审计）**：
   - `docs-stm/manuals/datasource-and-folders.md`：目录树 `cache.py` → `cache/` 子包 8 行 + 新增 `services/` 目录和 `services/holdings_tracker.py`
   - `docs-stm/managements/technical.md`：更新 11 处 `cache.py` → `cache/` 引用（架构图、目录树、C2 约束、依赖图等），新增 `services/` 目录和 `services/holdings_tracker.py` 引用
   - `docs-stm/manuals/how-to-config.md`：L352 `cache.py:clear_by_group()` → `cache:clear_by_group()`
   - `docs-stm/manuals/how-to-use-registry.md`：L92/93/151 三处引用更新
   - `docs-stm/managements/changelog.md`：追加变更记录
   - `docs-stm/managements/review-findings.md`：追加审查标识
   - 更新后运行 `grep -rn "src/python/cache\.py" docs-stm/ --include="*.md"` 确认零残留

7. **开发者指引**：在 `technical.md` 缓存设计章节末尾新增「子模块导航」小节：

   ```markdown
   ### 子模块导航（cache/ 拆分后）

   `src/python/cache/` 子包模块职责边界：

   | 子模块 | 职责 | 新增函数放这里 |
   |:-------|:-----|:--------------|
   | `_paths.py` | 缓存路径常量 + 路径构造函数 | 涉及缓存目录/路径/后缀的新常量或路径函数 |
   | `_io.py` | 原子文件读写（tempfile+os.replace） | 新的文件序列化/反序列化格式 |
   | `_store.py` | get/set/clear + _cache_lock | 核心存取逻辑变更；锁机制扩展 |
   | `_stats.py` | 命中率统计 + 目录统计 | 新增指标或统计查询 API |
   | `_ttl.py` | TTL 查询 + 缓存年龄（交易时段感知） | 新增数据类型 TTL 规则 |
   | `_cleanup.py` | 过期清理 + 单文件过期判断 | 清理策略变更（如 LRU/LFU） |
   | `_groups.py` | 前缀/分组批量清除 | 新的批量清除策略 |
   | *`services/holdings_tracker.py`* | 持仓指纹跟踪（业务层，不属 cache/） | 持仓变更检测逻辑 |

   **添加新缓存函数的通用规则**：
   1. 定位职责：上述 7 个 cache/ 子模块 + services/ 哪个最接近？放入对应模块
   2. 业务逻辑（如持仓跟踪）→ `services/` 目录，不放入 cache/ 包
   4. 热路径函数 → 高频核心模块（_store/_stats/_ttl/_paths/_io）
   5. 低频操作（菜单命令触发的清理/分组）→ 低频模块（_cleanup/_groups）
   6. 不可确认归属 → 暂放 `_store.py`
   7. 所有新增函数必须 `logger = logging.getLogger("invest")`（C8 约束）
   6. 所有新增函数必须是线程安全的（使用 `_cache_lock`）
   ```

**风险**：中。可能影响导入路径：
1. `_legacy.py` 中可能残留了未被提取的函数或变量
2. 某些测试 mock 路径 `src.python.cache._legacy.X` 需要更新
3. 私有函数（如 `_record_cache_hit/miss`、`_GZIP_THRESHOLD`）未被 `__init__.py` 导入，若被外部代码直接引用则不可访问
4. 文档引用遗漏

**缓解措施**：
- 删除前运行 `pytest --collect-only` 确认所有测试仍能收集
- `_legacy.py` 空壳验证 + grep 三重检查确认无残留
- 导入顺序核验：`__init__.py` 的 import 语句顺序必须遵守依赖 DAG

**验收**：
- `from src.python.cache import X` 对所有原始调用方正常工作
- `_legacy.py` 已删除，`cache/` 包共有 8 个文件（`__init__.py` + 7 子模块）；`services/holdings_tracker.py` 已独立于 `services/` 目录
- 回归测试全通过
- `grep -rn "src/python/cache\.py" docs-stm/ --include="*.md"` 零残留
- `python -c "
from src.python.cache import get, set, clear, get_ttl, cleanup_expired, clear_by_prefix, check_and_refresh_caches;
assert get('_e2e_z6_key_') is None;           # 读取不存在key
set('_e2e_z6_key_', {'test': 42});            # 写入
assert get('_e2e_z6_key_') == {'test': 42};   # 读取确认
clear('_e2e_z6_key_');                        # 删除
assert get('_e2e_z6_key_') is None;           # 确认已删除
print('E2E smoke OK')
"` — 全链路 E2E 冒烟测试（import + set/get/clear 业务语义完整验证）

**成本节省**：删除 _legacy（~20min）+ 全量文档同步（~10min）+ 开发者指引（~5min）= 35min → 合并后 ~25min（-29%）

---

### 已淘汰的迭代（附理由）

以下迭代经成本/收益审查后确认淘汰，不纳入执行计划。

#### ~~测试文件拆分（原 I-11）~~（淘汰）

**原内容**：将 1413 行的 `test_cache.py` 按子模块拆分为 9 个测试文件。

**淘汰理由**：
- **维护负担增加而非减少**：9 个测试文件意味着开发者需在 9 个文件间跳转定位测试，比在一个文件中搜索更困难
- **无行为收益**：测试的运行方式、覆盖率、可读性在拆分前后无实质变化——`pytest` 的 marker 分组已提供足够的关注点隔离
- **mock 路径维护成本**：拆分的测试文件各自需要独立的 `setUp`/`patch` 路径，增加了重复样板代码
- **`test_cache_edge.py` 审计成本**：需逐条用例审计归属，新增整合测试确保跨模块交互不漏测，投入产出比低
- **行数虚高**：1413 行中包含大量 fixture 和辅助方法（`CacheTestBase`、`_write_cache`、`_write_gz_cache`），提取共享基类后各文件实际仅 ~100-250 行，已足够可维护
- **已有更好的替代方案**：`pytest -k` 表达式（如 `pytest -k "TestCacheGet or TestCacheSet"`）可精准定位特定功能测试，无需文件拆分

**如果未来需要拆分**：当 test_cache.py 超过 2000 行或某子模块测试超过 400 行时重新评估。届时优先提取 `CacheTestBase` 共享基类和 fixture 辅助函数，而非盲目拆分所有子模块测试。

#### ~~import 性能基准测试脚本（原 I-14）~~（淘汰）

**原内容**：创建一次性 `cache_import_benchmark.py` 脚本测量 import 耗时。

**淘汰理由**：
- **一次性脚本，无持续价值**：基准测试仅在重组前后有意义，后续版本迭代中退化可能性极低
- **8-12ms 的 import 差异对 TUI 应用无实际影响**：首轮导入在菜单显示前完成，后续重复导入为 O(1) `sys.modules` 查找
- **I-07 验收中已包含 import 验证**：`pytest --collect-only` 和回归测试已隐含验证模块可加载性
- **如需验证**：手动运行 `python -c "import timeit; print(min(timeit.repeat('from src.python.cache import get', number=500, repeat=5)))"` 即可，无需脚本化

#### ~~存储后端抽象接口（原 I-15）~~（淘汰 — YAGNI）

**原内容**：定义 `StorageBackend` Protocol + 将 `_io.py` 改造为 `FileStorageBackend` 类 + `_store.py` 改为依赖注入。

**淘汰理由**（YAGNI — "You Aren't Gonna Need It"）：
- **无实际替换需求**：当前代码库无任何替换文件系统缓存为 Redis/S3 的计划或需求。此抽象仅针对"可能有一天"的假设场景
- **引入额外复杂度**：
  - `_store.py` 从直接调用 `_read_cache_data(fpath, ...)` 改为 `self._backend.read(key)` — 增加间接层
  - `__init__.py` 需创建全局单例 `_backend = FileStorageBackend()` + `_store = CacheStore(_backend)` — 增加启动代码
  - 新增 1 个模块（`_protocol.py`）和 3 处修改（`_io.py`→`_file_io.py`, `_store.py`, `__init__.py`）
- **抽象若错误则成本更高**：没有第二个实现来验证 Protocol 设计的合理性，提取的接口很可能不符合未来实际需求
- **收益远低于成本**：~25min 编码 + ~10min 测试 = 35min 投入，产出 0 个用户可见功能
- **未来重构成本低**：移除代码经拆分后更加模块化，当真正需要替换后端时，提取 Protocol 的成本不会比现在更高

**替代方案**：保持 `_io.py` 的简单函数接口。如需替换后端，届时定义 Protocol 并实现即可（成本与现在相当，但接口基于真实需求）。

#### ~~缓存格式版本化（原 I-16）~~（淘汰 — YAGNI）

**原内容**：在缓存文件 envelope 中增加 `_version` 字段 + 版本兼容性校验 + 演进式自动迁移。

**淘汰理由**（YAGNI）：
- **无版本化需求**：当前 `{"_ts": ..., "_data": ...}` 格式自项目创建以来从未变更，无任何计划表明需要变更
- **破坏性副作用**：添加 `_version` 字段后，所有现有缓存（`_version = 0`）在首次读取时会被判定为"版本不兼容"并自动删除，导致用户所有缓存数据在升级后立即清空，相当于强制全量缓存失效
- **增加额外测试负担**：需为版本兼容性编写测试用例覆盖：新写/旧读、旧写/新读、版本号越界等组合
- **当需要变更时的成本很低**：添加版本字段 + 校验逻辑是约 10 行的修改，不需要提前预留
- **"演进式迁移"实为"破坏式迁移"**：计划中 `version < MIN_COMPAT_VERSION` 时直接 `os.remove`，会删除所有无版本字段的现有缓存。如果用户有大量未过期的 `profit_forecast` 等大文件，首次读取时全部删除并重新拉取，造成性能抖动

**替代方案**：当实际需要更改缓存格式时，添加版本字段并进行迁移。届时可以设计平滑迁移策略（如读取时兼容旧格式 + 写入时自动升级），而非立即删除。

#### ~~TTL 接口扩展（原计划 I-04 含）~~（淘汰 — YAGNI）

**原内容**：在 I-04 提取 `_ttl.py` 时，将 `get_ttl(data_type)` 接口扩展为 `get_ttl(data_type, key=None, context=None)`，为未来的逐 key TTL 和滑动窗口 TTL 预留入参。

**淘汰理由**（YAGNI）：
- **无当前使用场景**：当前 ~20 个调用方均只传 `data_type` 一个参数，没有任何模块需要逐 key TTL 或滑动窗口 TTL
- **预留接口可能错误**：没有真实用例时，`context` 参数的类型（`Any`）和语义（`dict`? `str`? `TypedDict`?）只能猜测，未来实际需求很可能不匹配
- **增加不必要的测试负担**：扩展后的接口需要测试 3 种参数组合（`(data_type)` / `(data_type, key)` / `(data_type, key, context)`），而纯提取只需测试原有行为
- **参考 StorageBackend 和缓存版本化**：与已淘汰的 I-15、I-16 同属"为未来预留"的预先抽象，当前保持接口精简

**替代方案**：保持 `get_ttl(data_type)` 纯提取。当未来出现需要逐 key TTL 的真实场景时，按实际需求重新设计接口。届时 `_ttl.py` 已独立成模块，修改范围可控。

---

## 4. 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 | 涉及迭代 |
|:-----|:----:|:----:|:---------|:--------|
| **模块/包命名冲突**：`cache/` 包与 `cache.py` 文件同名，Python 屏蔽模块导致循环导入 | **高** | **高** | I-01 一次性 `git mv cache.py → cache/_legacy.py`，不共存 | I-01 |
| **循环依赖（registry）**：cache 子模块导入 registry，registry 导入 cache | 低 | 高 | `get_ttl`/`get_cache_age_by_data_type` 等函数内 lazy import；registry 已验证不导入 cache | I-04, I-05 |
| **循环依赖（_store ↔ _legacy）**：`_store.py` 需 `_record_cache_hit/miss` 若从 `_legacy` 导入，而 `_legacy` 又导入 `_store`，形成双向循环 | 中 | 高 | `_stats.py` **先于** `_store.py` 提取（I-02 → I-03 顺序），`_store.py` 从 `_stats` 而非 `_legacy` 导入 | I-02, I-03 |
| **lock 状态不一致**：多个子模块共享 `_cache_lock` 但导入路径不同 | 低 | 中 | `_cache_lock` 从 `_store` 集中导出，其他模块 `from ._store import _cache_lock` | I-03, I-05 |
| **标准库 mock 路径失效**：`patch("src.python.cache.time.time")` 等约 45 处因 `cache.py`→`cache/` 包转换后 `time` 不再是包属性而不可访问 | **高** | **高** | I-01 执行前先更新所有此类 mock 路径：标准库改用 `patch("time.time")`/`patch("os.remove")`/`patch("tempfile.mkstemp")` 全局补丁（测试已隔离临时目录）；详见 I-01「测试 mock 路径迁移」子步骤 | I-01 |
| **私有引用 mock 路径失效**：`patch("src.python.cache._is_market_open")` 约 20 处因 `_is_market_open` 未被 `__init__.py` re-export 而不可访问，且 I-04 后 `get_ttl` 移至 `_ttl.py`，`_is_market_open` 的存在位置也随之变更 | **高** | **中** | 改用 `patch("src.python.market_hours.is_market_open")` 直接为目标模块打补丁 | I-01, I-04 |
| **文件残留**：`_legacy.py` 在 I-07 删除时可能残留未提取函数 | 低 | 中 | 执行「`_legacy.py` 空壳验证」(`grep -n "^def \|^class " _legacy.py`) 确认无残余函数/类定义后方可删除；`pytest --collect-only` 验证 | I-07 |
| **文件名冲突**：`_store` 等模块名与第三方库重名 | 低 | 低 | 使用 `_` 前缀缩小作用域 | 全局 |
| **缺少 `_paths` 导入**：`_store.py` 和 `_ttl.py` 直接使用 `_GZIP_THRESHOLD`/`_GZIP_SUFFIX`，但计划中对应迭代的 import 列表未列出这两个常量 | **高** | **中** | I-03/I-04 步骤中手动补充 `from ._paths import _GZIP_THRESHOLD, _GZIP_SUFFIX`；提取后即刻运行 `pytest` 验证 | I-03, I-04 |
| **缺少 `from __future__ import annotations`**：各子模块的函数签名使用联合类型语法如 `dict[str, int | float]` / `str | None`，未加该导入时 Python 3.9 会引发 `TypeError` | 中 | 高 | 每个子模块提取后即刻运行 `python -c "from src.python.cache._xxx import func"` 验证模块可加载 | I-01 ~ I-06 全局 |
| **子包导入级联性能退化**：8 个子模块在 `__init__.py` 中全部 eager import 时，首轮导入需编译 8 个文件（vs 原 1 个），可能增加 5-15ms 启动耗时 | 低 | 低 | `__init__.py` 使用 eager import（简单可维护），如需延迟加载再切换为 `__getattr__` 方案；实际影响对 TUI 应用可忽略 | I-07 |
| **迭代漏测**：某迭代漏回归，问题叠加到后续迭代才发现 | 中 | 中 | 每轮强制 `--mode regression` 验证，I-03/I-06 额外加 `unit_core` | 全局 |
| **跨分支合并冲突**：两个 git 分支分别持有 `cache.py`（旧）和 `cache/`（新），合并产生树冲突，Python import 完全失效 | **高** | **高** | 拆分期间统一在 dev 分支完成；合并冲突时手动接受 `cache/` 子包并 `git rm cache.py` | I-01 |
| **部分迁移状态检查**：中间提交（如 I-01~I-03 已提交但 I-04 未完成）被他人 checkout 后，`_legacy.py` 中 get_ttl 等功能仍在，但新模块开发（如 I-05 `_cleanup.py` 依赖 `_ttl`）会因 `_ttl.py` 不存在而失败 | 低 | **高** | 每轮迭代必须是**完整可工作的**：`__init__.py` 和 `_legacy.py` 的 re-export 链完整 | I-01 ~ I-07 |
| **`__pycache__` 残留字节码**：`git mv cache.py → cache/_legacy.py` 后旧字节码被意外使用 | 低 | 中 | I-01 执行 `find ... -name "__pycache__" -exec rm -rf` 清理；`git clean -fdX` 防遗漏 | I-01 |
| **`CACHE_DAILY` 公共常量未 re-export**：`test_cache.py` 中 3 处使用 `from src.python.cache import CACHE_DAILY`，但各版 `__init__.py` 均未导入此常量 | **高** | **高** | I-01 `__init__.py` 中追加 `CACHE_DAILY` 导入和 `__all__` 条目；I-07 改用 `from src.python.constants import CACHE_DAILY` | I-01, I-07 |
| **`_CACHE_DIR` 模块引用语义变更后测试 patch 静默失效**：路径提取后 `from ._paths import _CACHE_DIR` 创建本地引用，`patch("src.python.cache._CACHE_DIR")` 仅修改 `__init__._CACHE_DIR` | **高** | **高** | I-01 中将测试中所有 `patch("src.python.cache._CACHE_DIR", ...)` 迁移为 `patch("src.python.cache._paths._CACHE_DIR", ...)` | I-01 |
| **`_read_cache_data`/`_write_atomic` I-07 后不可访问**：`test_cache_edge.py:235` 和 `test_security_edge.py:259` 从 `src.python.cache` 导入这两个私有函数 | 中 | 中 | I-07 `__init__.py` 添加 `from ._io import _read_cache_data, _write_atomic` | I-07 |
| **`_record_cache_hit/miss` I-07 后不可访问**：`_store.py` 通过 `from ._stats import` 使用这两个函数，但 I-07 `__init__.py` 未 re-export | 低 | 中 | 经 grep 确认（`grep -rn "from src\.python\.cache import.*_record_cache" src/`），无外部代码直接导入 `_record_cache_hit/miss`，无需加入 `__init__.py`；I-07 执行前再次 grep 确认 | I-07 |
| **`__dir__` 不完整（如启用 __getattr__ 延迟加载）**：`dir(cache)` 缺失低频操作名，影响 IDE 自动补全 | 低 | 低 | `__dir__` 实现返回 `sorted(set(__all__) | {标准模块属性集合})` | I-07 |
| **`get_ttl(data_type)` 接口过窄**：仅接受数据类型名，不支持逐 key TTL、滑动窗口 TTL 或自适应 TTL | 低 | 低 | ~~I-04 提取时将接口扩展为 `get_ttl(data_type, key=None, context=None)`~~ → **YAGNI 淘汰**（见"已淘汰的迭代"中 TTL 接口扩展条目），保持原有接口纯提取 | I-04（已取消扩展） |
| **循环依赖验证不足**：I-05 `_cleanup.py`/`_groups.py` 在模块级 eager import registry 函数（`get_prefix_type_map`/`get_registry`），若 registry 在模块级导入了 cache 则会死锁 | 中 | **高** | I-01 中新增 `grep` 验证步骤确认 `registry.py` 无模块级 cache 导入；如有则 cleanup/groups 改为 lazy import | I-01, I-05 |
| **conftest 隔离夹具无声失效**：`_isolate_sensitive_paths` autouse fixture 若使用 `patch("src.python.cache._CACHE_DIR")`，I-01 后仅改 `__init__._CACHE_DIR` 而 `_paths._CACHE_DIR` 不受影响，测试写入真实缓存目录 | **高** | **高** | I-01 中增加 `grep` 检查 conftest.py 的 cache 路径 patch 方式，并修正为 `_paths._CACHE_DIR` | I-01 |
| **`_cache_stats_lock` 冗余风险**：I-02 创建一个独立的 `_cache_stats_lock`，但原始代码中 `_cache_hits += 1` 是 GIL 保护下的 int 原子自增，无锁即可安全操作 | 低 | 低 | I-02 中先 grep 确认原始代码中 stats 变量是否有 `_cache_lock` 保护，若无则撤销创建独立锁 | I-02 |
| **异步化路径未规划**：`threading.Lock` + 同步文件 I/O 无 asyncio 路径 | 低 | 低 | 当前拆分不阻塞异步化；注意 `_cache_lock` 紧耦合 `threading` 模块 | I-03 |

## 5. 收益分析

### 5.1 直接收益

| 指标 | 拆分前 | 拆分后 | 改善 |
|:-----|:------:|:------:|:----:|
| `cache.py` / `cache/` 单文件 | 667 行 | 子包 8 文件，各 ~30-130 行 | 单文件 -92% |
| 单文件最大责任数 | 7 类 | 1 类 | -85% |
| `test_cache.py` 行数 | 1413 | 1413（未拆分，见淘汰理由） | 0%（可维护性不变） |
| 新增功能定位成本 | 需阅读 667 行找追加位置 | 按职责定位到子模块 | 显著降低 |
| 模块边界清晰度 | 模糊（"更多归入 cache"） | 明确（_io / _store / _ttl 等） | 显著提升 |

### 5.2 间接收益

- **代码评审简化**：评审者只需关注相关子模块，不需要翻阅整个 667 行文件
- **持仓跟踪已有正确归属**：`services/holdings_tracker.py` 已在 I-06 一步到位放在业务层，不影响其余代码
- **测试编写简化**：针对 `_ttl` 的测试不需要 mock 整个 cache 系统
- **未来可替换存储后端**：如需替换 S3/Redis，在 `_io.py` 和 `_store.py` 之间提取 `StorageBackend` Protocol 即可（当前 YAGNI，见淘汰理由）

### 5.3 优化后成本估算

| 迭代 | 对应原计划 | 预估编码时间 | 预估测试时间 | 总工时 |
|:-----|:----------|:-----------:|:-----------:|:-----:|
| I-01 | I-01~I-03 合并 | 12min（git mv + 显式 __init__.py + 创建 _paths.py + _io.py + 更新 _legacy + conftest 双 patch） | **40min**（迁移 ~60 处测试 mock 路径 + conftest 双 patch + 回归） | **52min** |
| I-02 | I-04（原） | 5min（stats 提取，纯移动无新依赖） | 3min（回归） | 8min |
| I-03 | I-05（原） | 15min（store 提取 + 循环依赖检查） | **10min**（验证残留 mock 路径 + unit_core） | **25min** |
| I-04 | I-06（原） | 3min（ttl 纯提取，取消 YAGNI 接口扩展） | 3min（回归） | **6min** |
| I-05 | I-07~I-08 合并 | 8min（同时创建 _cleanup.py + _groups.py） | 4min（回归） | 12min |
| I-06 | I-09（原） | 15min（holdings 提取 + services/ 目录 + re-export） | 3min（回归） | 18min |
| I-07 | I-10~I-12~I-13 合并 | 15min（git rm _legacy + __init__.py 重写 + 全量文档审计 6 份 + 开发者指引） | **13min**（_legacy 空壳验证 + 私有函数导入验证 + grep 三重检查 + 文档引用验证 + full regression） | **28min** |
| **合计** | **14 轮→7 轮** | **~71min**（−4min: I-04 取消 YAGNI 接口扩展 +5min: I-06 services/ 目录） | **~76min**（+10min: I-01 mock 迁移预算从严 + conftest 双 patch） | **~147min**（+15min） |

**节约对比**（原计划 vs 优化后）：

| 维度 | 原计划（14 轮） | 优化后（7 轮） | 节省 |
|:-----|:--------------:|:-------------:|:----:|
| 迭代数 | 14 | 7 | **50%** |
| 编码时间 | ~125min | ~71min | **43%** |
| 测试时间 | ~98min | ~76min | **22%** |
| 总工时 | ~223min | ~147min | **34%** |
| 风险缓冲 | ~105min | ~65min | **38%** |
| **总预估** | **~5.5-6.5h** | **~3.5-4h** | **~34%** |

**风险缓冲**：~65min（I-01 mock 迁移从严预算 40min + 回归 + conftest 双 patch；I-03/I-04 各迭代可能遇到遗留补丁路径需要修复；I-07 删除 _legacy + 文档审计 + __all__ 清理可能遗漏引用）

## 6. 与 C2 / C13 约束的兼容性

### C2 — 缓存统一管理

C2 约束要求"所有持久化缓存必须通过 `cache.py` 的 `get()`/`set()` 读写，不得直接操作 `data/cache/` 文件系统"。

拆分后：
- 原有的 `from src.python.cache import get, set` 在所有调用方中**无需改动**
- 新增模块仍然通过 `from src.python.cache import get, set` 使用缓存
- `cache/` 包的 `__init__.py` 统一 re-export

**I-07 的 `__all__` 精简（必选步骤）** 进一步强化 C2：从 `__init__.py` 的 `__all__` 中移除 `_cache_path`、`_read_cache_data`、`_write_atomic` 三个内部接口，防止外部模块绕过 `get()`/`set()` 直接操作文件系统。测试文件如需使用这些接口，改为 `from src.python.cache._paths import _cache_path` / `from src.python.cache._io import _read_cache_data` 显式导入子模块。

### C13 — 测试敏感路径隔离

`conftest.py:109` 的 `monkeypatch.setattr("src.python.cache._CACHE_DIR", ...)` 在 I-01 后因 `_CACHE_DIR` 移至 `_paths.py` 而静默失效。**已在 I-01 中修复为双路径 patch**（`_paths._CACHE_DIR` + `_legacy._CACHE_DIR` try/except 兼容），确保测试全周期不污染真实 `data/cache/`。

## 7. 不在此次计划中的事项

| 事项 | 原因 |
|:-----|:------|
| **替换为 S3/Redis 后端 + StorageBackend 抽象** | 经成本/收益审查判定为 YAGNI，当前无替换需求；如未来需要，提取 `StorageBackend` Protocol 即可（详见已淘汰的迭代 ~~I-15~~） |
| **缓存格式版本化** | 经成本/收益审查判定为 YAGNI，当前格式稳定；如未来需要变更 envelope 结构时同步添加（详见已淘汰的迭代 ~~I-16~~） |
| **测试文件拆分（I-11）** | 经成本/收益审查判定为低收益事项，1413 行测试文件的维护负担低于 9 文件拆分（详见已淘汰的迭代 ~~I-11~~） |
| **import 性能基准脚本（I-14）** | 一次性脚本无持续价值，手动验证即可（详见已淘汰的迭代 ~~I-14~~） |
| **保持 `_legacy.py` 完整可删除条件** | `_legacy.py` 在 I-07 删除，前提是所有函数已提取至子模块 |

---

## 8. 逐轮评估

以下对 I-01 ~ I-07 每轮迭代进行独立评估，涵盖风险等级、核心风险、收益、验收标准、设计约束对齐和技术债务影响。

### 【已完成】 I-01: 建包 + 路径/常量 + 文件 IO

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🔴 **高** — 全计划中风险最高的一轮 |
| **核心风险** | ① 模块/包命名冲突：`cache.py` + `cache/` 不可共存，必须一步 `git mv` 完成；② ~60 处 mock 路径批量迁移，遗漏任一都导致回归失败；③ **C13 隔离夹具失效**：`conftest.py:109` 的 `monkeypatch.setattr("src.python.cache._CACHE_DIR", ...)` 在 I-01 后因 `_CACHE_DIR` 移至 `_paths.py` 而仅改 `__init__._CACHE_DIR`，不涉及 `_paths._CACHE_DIR`，测试无声写入真实 `data/cache/`。**I-01 已包含双 path 修复方案** |
| **直接收益** | 建立整个拆分的目录骨架（`cache/` 子包 + `_paths.py` + `_io.py` + `__init__.py` + `_legacy.py` 过渡）。无此轮则后续 6 轮无从谈起 |
| **验收标准** | ✅ 功能冒烟 `get('_nonexistent_') is None`、`pytest unit_core+scenario` 全通过、C13 `grep` 零残留 |
| **约束对齐** | C2(回退为`from ._legacy import` 保持 `from cache import get` 可用)、C3(`_io.py` 保留 `tempfile.mkstemp` + `os.replace`)、C8(各子模块 `logger = logging.getLogger("invest")`)、C11(迁移中新增测试方法必须加 pytest marker)、**C13(conftest 双 path patch 修复)**
| **新增债务** | **D-transition**: `_legacy.py` 过渡文件存在（I-07 清偿）。I-01~I-06 期间代码分散于 `_store`/`_cleanup`/`_ttl` 等 + `_legacy` 中，但通过 `__init__.py` re-export 对调用方透明 |
| **工时** | 编码 12min + 测试 **40min**（mock 迁移从严预算）→ **52min** |

---

### 【已完成】 I-02: 提取命中率统计 → `_stats.py`

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🟢 **低** — 35 行纯移动，零业务逻辑变化 |
| **核心风险** | `_cache_stats_lock` 是否冗余？原始代码中 `_cache_hits += 1` 是 CPython GIL 保护的单字节码 int 原子自增，无需独立锁。I-02 执行前 `grep` 确认后应撤销创建独立锁，改为注释"GIL 保护 int 原子自增" |
| **直接收益** | **必须先于 I-03 完成**，否则 `_store.py` 若从 `_legacy` 导入 `_record_cache_hit/miss` 会形成 `_store ↔ _legacy` 双向循环依赖 |
| **验收标准** | ✅ `import get_cache_hit_rate` 正常、多次 get/set 后命中率 >0、`get_cache_stats()` 正确返回文件数量和大小、导入冒烟、回归全通过 |
| **约束对齐** | C8(`logger = logging.getLogger("invest")`)、C2(统计接口通过 `__init__.py` re-export) |
| **新增债务** | 无（35 行微模块，提取即完结） |
| **工时** | 5min + 3min = **8min** |

---

### 【已完成】 I-03: 提取核心存取 → `_store.py`

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🟡 **中** — 7 轮中最关键的提取（130 行），影响 ~20 个调用方 |
| **核心风险** | ① `set()` 三路径：正常写入 / FileNotFoundError → `os.makedirs` 重试 / PermissionError 降级；② `get()` 双路径：gzip 文件与非 gzip 文件透明回退；③ `_cache_lock` 从此路由到 `_store` 导出，后续 `_groups`/`_cleanup` 均 `from ._store import _cache_lock`（`services/holdings_tracker.py` 通过 `set`/`clear` 间接使用，无需直接引用）；④ 如果 I-01 有残留的 `_legacy.time.time` mock 路径未迁完，此轮必须一并清理（因为 `_legacy` 不再 `import time` 用于缓存操作）|
| **直接收益** | 核心 get/set/clear 从 667 行单体脱离，热路径代码独立可维护。影响面最大（~20 调用方），但 re-export 保证调用方零改动 |
| **验收标准** | ✅ `from cache import get` 正常、get 三种状态(命中/过期/不存在)、set 三路径(普通/gzip/重试)、clear 双后缀(json/json.gz)、导入冒烟、回归全通过 |
| **约束对齐** | C2(保留 `from cache import get/set/clear`，调用方完全透明)、C3(原子写入继承自 `_io.py`)、C8(`invest` logger) |
| **新增债务** | **D-lock**: `_cache_lock` 集中于 `_store.py`，其他子模块共享同一锁实例。I-07 前由 `_legacy` 中转，I-07 后直连 `_store` |
| **工时** | 15min + 10min = **25min** |

---

### 【已完成】 I-04: 提取 TTL → `_ttl.py`

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🟢 **低** — 纯查询函数，无状态修改 |
| **核心风险** | ① `get_ttl()` 内部 lazy import `from src.python.config import get_config`（防循环依赖）— 移动后必须保持函数内导入；② 如果 I-01 采取了临时 mock 方案 `patch("cache._legacy._is_market_open")`，此轮**必须**改为 `patch("src.python.market_hours.is_market_open")`（`_legacy` 不再导入 `_is_market_open`） |
| **直接收益** | TTL 逻辑从核心文件分离，I-05 的 `cleanup_expired()` 依赖 `get_ttl()` |
| **验收标准** | ✅ `from cache import get_ttl` 正常、盘中/盘后 TTL 正确、`profit_forecast` 特殊处理保留、导入冒烟、回归全通过 |
| **约束对齐** | C8(`invest` logger)、C2(get_ttl 仍从 `cache` 导出) |
| **新增债务** | 无（接口扩展已 YAGNI 淘汰，纯提取无附加改动） |
| **工时** | 3min + 3min = **6min**（原 10min，取消接口扩展后精简） |

---

### 【已完成】 I-05: 提取过期清理 + 组管理 → `_cleanup.py` + `_groups.py`

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🟡 **中** — 核心风险已预防，执行风险低 |
| **核心风险** | **循环导入风险**：`_cleanup.py` 在**模块级** eager import `get_prefix_type_map`/`get_exact_type_map`，`_groups.py` 在模块级 import `get_registry`。若 `registry.py` 有任何模块级 `from src.python.cache import ...` 则加载时死锁。已在 I-01 中增加 `grep "^from.*cache import\|^import.*cache" src/python/registry.py` 验证步骤 |
| **直接收益** | 2 个模块合并提取，~150 行清理/分组代码从单体移出 |
| **验收标准** | ✅ `from cache import cleanup_expired, clear_by_prefix` 正常、过期文件正确删除、`clear_by_prefix("fund_perf_")` 正确匹配、导入冒烟、回归全通过 |
| **约束对齐** | C8(`invest` logger)、C2(清理/分组函数通过 `cache` 包导出) |
| **新增债务** | 无（纯功能提取） |
| **工时** | 8min + 4min = **12min** |

---

### 【已完成】 I-06: 提取持仓跟踪 → `src/python/services/holdings_tracker.py`

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🟢 **低** — 纯业务逻辑移动，仅依赖下层模块，无循环依赖 |
| **核心风险** | **架构边界治理**：持仓跟踪（指纹计算/变更检测）是业务语义而非缓存基础设施。**直接在 I-06 将其放入正确的架构层次**（`services/` 目录而非 `cache/` 包），`cache/__init__.py` 增加 re-export 确保调用方 `from cache import check_and_refresh_caches` 完全透明。消除全部架构债务，不做技术债推迟 |
| **直接收益** | 业务逻辑一步到位放在正确层次。`services/holdings_tracker.py` 内 5 个函数（`compute_holdings_fingerprint`、`compute_holdings_codes`、`_read_holdings_tracking`、`_clear_holdings_related_caches`、`check_and_refresh_caches`）结构清晰。`cache/` 包保持纯基础设施职责 |
| **验收标准** | ✅ `from cache import check_and_refresh_caches` 正常、指纹相同 → `[]`、指纹变更代码未增 → `[]`（清除关联缓存）、指纹变更代码有增 → `[新代码]`、导入冒烟、回归全通过 |
| **约束对齐** | C8(`invest` logger)、C2(通过 `cache.set/clear` 存取跟踪数据) |
| **新增债务** | **无** — 持仓跟踪直接放在正确的 `services/` 目录，无需后续迁移 |
| **工时** | 15min（+5min 建 services/ 目录 + 调整 import）+ 3min = **18min** |

---

### 【已完成】 I-07: 删除 `_legacy.py` + 全量文档同步 + 开发者指引

| 维度 | 评估 |
|:-----|:------|
| **风险等级** | 🟡 **中** — 主要是遗漏风险（残余函数/测试 mock 路径/文档引用） |
| **核心风险** | ① `_legacy.py` 空壳验证——`grep "^def \|^class "` 确认零残余函数后方可删除；② grep 三重检查（test/src.py/docs.md）零残留；③ **`__all__` 精简（C2 约束对齐，必选）**：从 `__init__.py` 的 `__all__` 中移除 `_cache_path`/`_read_cache_data`/`_write_atomic`，测试文件改为直接导入子模块；④ 6 份文档逐行审计，`grep "src/python/cache\\.py" docs-stm/` 零残留 |
| **直接收益** | 💎 清偿全部过渡期债务（D-transition、D-lock）。最终架构：9 文件子包（`__init__.py` + 8 子模块），C2 强约束生效。开发者指引明确后续新增函数的 6 条归属规则 |
| **验收标准** | ✅ `from cache import X` 对所有原始调用方 OK、`_legacy.py` 已删除、全回归通过、`grep` 零残留、**E2E 冒烟**（`set('_e2e_', {42}) → get → clear → get(None)` 完整业务语义验证） |
| **约束对齐** | **C2(`__all__` 清理必选)**、C3(原子写入由 `_io.py` 保障)、C8(日志统一)、C13(conftest 隔离已由 I-01 修复)、C11(文档提示 marker 合规) |
| **清偿债务** | ✅ D-transition(`_legacy.py` 删除)、D-lock(`_cache_lock` 直连 `_store`)、D-holdings-location(开发者指引明确"留待后续") |
| **工时** | 15min + 13min = **28min** |

---

### 8.1 逐轮评估汇总

| 迭代 | 风险 | 工时 | 功能冒烟 | C2对齐 | C8/C11/C13 | 新增债务 |
|:----|:----:|:----:|:--------:|:------:|:----------:|:---------|
| I-01 | 🔴 高 | 52min | ✅ import+functional | ✅ (回退兼容) | C13🔴→✅ | D-transition |
| I-02 | 🟢 低 | 8min | ✅ import | ✅ | C8✅ | 无 |
| I-03 | 🟡 中 | 25min | ✅ import | ✅ | C8✅ | D-lock |
| I-04 | 🟢 低 | 6min | ✅ import | ✅ | C8✅ | 无 |
| I-05 | 🟡 中 | 12min | ✅ import | ✅ | C8✅ | 无 |
| I-06 | 🟢 低 | 18min | ✅ import | ✅ | C8✅ | 无 |
| I-07 | 🟡 中 | 28min | ✅ **E2E set/get/clear** | **C2🔴→✅** | C13✅ | **清偿全部** |
| **合计** | 2🔴3🟡2🟢 | **147min** | 7/7 | I-07 修复 | **全部对齐** | **2项→I-07清偿** |

### 8.2 设计约束全表

| # | 约束 | 涉及迭代 | 状态 |
|:--|:-----|:--------|:----:|
| C1 | 代码类型判定中心化 | 无 | ✅ N/A |
| C2 | **缓存统一管理 get/set** | I-03(保持透明)；**I-07(`__all__` 强制清理)** | 🔴→✅ **I-07 约束生效** |
| C3 | 原子写入 mkstemp+os.replace | I-01(移至 `_io.py`) | ✅ |
| C4 | 会话级 API 复用缓存 | 无 | ✅ N/A |
| C5 | HTTP 客户端统一 | 无 | ✅ N/A |
| C6 | Provider Chain 必经 | 无 | ✅ N/A |
| C7 | 报告序号不可硬编码 | 无 | ✅ N/A |
| C8 | **日志统一 `invest`** | I-01~I-07 全部 | ✅ 每轮显式标注 |
| C9 | LLM 模块注册 | 无 | ✅ N/A |
| C10 | 新闻召回策略 | 无 | ✅ N/A |
| C11 | **测试标记强制** | I-01(mock 迁移注意新增方法加 marker) | ⚠️ 验收已标注 |
| C12 | **边缘测试文件隔离** | I-07(`__all__` 清理注意 edge 文件导入) | ✅ 已标注 |
| C13 | **测试敏感路径隔离** | **I-01(conftest 双 path patch)** | 🔴→✅ **已修复** |
| C14 | 渲染期数据不可模块级全局变量 | 无 | ✅ N/A |

### 8.3 技术债务时间线

```
I-01: 产生 D-transition（_legacy.py 存在期 I-01~I-06）
I-03: 产生 D-lock（_cache_lock 路由锁定期 I-03~I-07）
I-06: （无新增债务 — 持仓跟踪直接放入 services/ 目录，架构层次正确）
I-07: 清偿 D-transition（删除 _legacy.py）
      清偿 D-lock（__init__.py 直连 _store）
```
