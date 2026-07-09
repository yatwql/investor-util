# R-198: LLM 模块两巨头横向拆分 — 技术设计与迭代计划

创建日期：2026-07-09
更新日期：2026-07-09（第 2 轮复盘：R1→导入路径全集+迭代压缩+R2 约束修正；16→15 轮）
状态：实施中（2026-07-09 启动 I-01）

> **复盘记录：**
> - Round 1: 修复 `_last_llm_failure_reason` 循环导入风险、新增未来约定、强化验证步骤、新增 2 轮迭代（Thinking 路由 + 导入基线）

---

## 目录

1. [问题陈述](#1-问题陈述)
2. [现状分析](#2-现状分析)
3. [设计目标](#3-设计目标)
4. [拆分方案](#4-拆分方案)
5. [技术设计](#5-技术设计)
6. [设计债务（已知接受）](#6-设计债务已知接受)
7. [未来新增 LLM 模块的文件放置约定](#7-未来新增-llm-模块的文件放置约定)
8. [风险与缓解](#8-风险与缓解)
9. [设计约束遵守清单](#9-设计约束遵守清单)
10. [迭代计划](#10-迭代计划)

---

## 1. 问题陈述

`generators.py`（750 行，第 2 大源文件）和 `api.py`（702 行，第 4 大源文件）同时承担多重职责，随 LLM 模块持续新增功能持续膨胀。

**现状问题：**

| 文件 | 行数 | 当前职责数 | 包含的独立逻辑域 |
|:-----|:----:|:----------:|:----------------|
| `generators.py` | 750 | 3 | ① 4 个 LLM 单体生成函数 ② 新闻 LLM 关联分析 ③ 批量编排（generate_all_llm） |
| `api.py` | 702 | 2 | ① Provider 调用路由（Claude/OpenAI/多 provider） ② 共享重试/截断/响应处理基础设施 |

**膨胀趋势：**
- 如新增"环比分析"等 LLM 模块，generators.py 将在单体函数列表继续膨胀
- 如新增第三方 LLM provider（如 DeepSeek 原生 API），api.py 的 Provider 路由将继续膨胀
- 现有结构破坏了**高内聚、低耦合**原则：单个文件内混合了属于不同抽象层次的代码

---

## 2. 现状分析

### 2.1 generators.py 现有职责

```
generators.py (750行)
│
├─ 模块入口 (L1-L76)          导入、常量、__all__
├─ 4个单体生成函数 (L78-L224)   generate_global_macro, generate_expert_review,
│                               generate_health_check, generate_penetration_deep
│                               (~158行，29+41+41+47)
├─ 新闻关联分析 (L232-L489)    enhance_news_correlation + 6个辅助函数
│                               (~262行)
│   ├─ _apply_llm_news_correlation     JSON解析与映射
│   ├─ _select_top_news                按关键词排序选取TOP N
│   ├─ _build_news_hooks               批量处理钩子构建
│   ├─ _map_llm_results                TOP索引→原始索引映射
│   ├─ _merge_llm_analysis             分析结果合并回news_data
│   └─ _finalize_news_token_usage      Token用量统计与记录
│
└─ 批量编排 (L492-L750)         generate_all_llm + 3个辅助函数
                                (~258行)
    ├─ _compute_module_cache_info   预计算指纹/缓存键/TTL
    ├─ _precheck_one_cache          单模块缓存预检
    ├─ _precheck_all_modules        全模块状态预检
    ├─ _dispatch_llm_workers        线程池任务分发
    └─ generate_all_llm             公共入口（6参→8元组映射）
```

### 2.2 api.py 现有职责

```
api.py (702行)
│
├─ 失败追踪 (L43-L56)            _last_llm_failure_reason + 存取函数 (~14行)
├─ 常量与配置 (L60-L112)          超时/重试/截断/缓存行/Thinking模型前缀 (~52行)
├─ 检测函数 (L115-L168)           截断检测(Claude/OpenAI)、Thinking兼容性 (~54行)
├─ 内容提取 (L171-L219)           _extract_content/_extract_model_from_cached (~48行)
├─ 工具函数 (L222-L267)           Token日志/重试次数/sanitize endpoint (~46行)
├─ 响应处理 (L269-L305)           熔断检查/成功响应处理 (~36行)
├─ 重试骨架 (L307-L431)           _attempt_api_call/_is_retry_available/
│                                  _call_llm_with_retry (~124行)
├─ Provider路由 (L434-L536)       _call_single_provider/_call_llm (~102行)
├─ Extended Thinking (L539-L581)   _configure_extended_thinking (~42行)
├─ Claude实现 (L584-L644)         _call_claude (~60行)
└─ OpenAI实现 (L647-L702)         _call_openai (~55行)
```

### 2.3 依赖关系图谱

```
当前依赖（简化）:
  __init__.py
    ├─ generators.py → api.py, skeleton.py, fingerprint.py, prompts.py, pricing.py, session.py
    ├─ prompts.py
    └─ session.py

  skeleton.py → api.py, fingerprint.py, markdown.py, pricing.py, prompts.py, session.py, cache.py, config.py

  report/*.py → llm (__init__.py), prompts

外部消费者                                   访问对象                         途经
────────────────────────────────────────────────────────────────────────
handlers_report.py, html_renderers.py        generate_all_llm               __init__.py
news_correlation.py, html_renderers.py       enhance_news_correlation       __init__.py
excel_generator.py                            FAIL_REASON_*                  __init__.py
test_llm.py                                   _apply_llm_news_correlation   generators.py
test_generators.py                            _precheck_one_cache           generators.py
test_api.py                                   _call_claude/_call_llm        api.py
test_api_edge.py                              _attempt_api_call             api.py
test_llm_scenarios.py                         generate_all_llm              generators.py
```

### 2.4 拆分后依赖关系（目标状态）

```
拆分后结构:
  
  generators.py          → 仅保留 4 个单体生成函数(thin wrapper) + 导入/__all__
  generators_news.py     → 新闻LLM关联分析
  generators_orchestrator.py → 批量编排 (调用 generators.py 的 4 个函数)
  
  api.py                 → Provider 路由 + Extended Thinking + 实现
  api_base.py            → 共享基础设施 (常量/重试截断/内容提取/失败追踪)

  目标依赖方向（无环，import 顺序从左到右）:
  api_base.py ─── 被所有其他模块依赖 (最底层)
      ↑
  api.py ───────── 依赖 api_base.py
      ↑
  skeleton.py ──── 依赖 api.py, api_base.py
      ↑
  generators.py ── 依赖 skeleton.py, api_base.py
      ↑
  generators_news.py ─ 依赖 skeleton.py, api_base.py
      ↑
  generators_orchestrator.py ─ 依赖 generators.py, skeleton.py, api_base.py
      ↑
  __init__.py ─── 依赖 generators_orchestrator.py, generators_news.py, ...
  
  关键单向约束:
  - api_base.py    不依赖任何 llm 内部模块
  - api.py         不依赖 skeleton.py 或任何 generators_*.py
  - skeleton.py    不依赖 generators_*.py
  - generators_*.py 不直接依赖 api.py (但通过 skeleton.py 间接依赖 api.py 的 _call_llm)
  - generators.py  不依赖 generators_orchestrator.py 或 generators_news.py

  ⚠️ 间接依赖说明:
  "generators_*.py 不依赖 api.py" 指不直接 import api.py，但由于 generators_*.py import skeleton.py，
  而 skeleton.py import api.py 的 `_call_llm` 和 `_clear_last_llm_failure`，
  实际运行时存在间接依赖。这是可接受的——api.py 的 Provider 调用本就是所有 LLM 模块的基础服务，
  间接依赖链 skeleton→api→api_base 是干净的"基础设施→Provider路由→实现"三层栈。
  ```
  
  **循环 import 分析（终态）**：
  
  ```
  全加载顺序（无环 ✅）:
    1. api_base.py     — 无 llm 内部依赖（最底层）
    2. api.py          ← api_base.py
    3. skeleton.py     ← api_base.py + api.py
    4. generators.py   ← api_base.py + skeleton.py
    5. generators_news.py ← api_base.py + skeleton.py  
    6. generators_orchestrator.py ← generators.py + api_base.py + skeleton.py
    7. __init__.py     ← generators_orchestrator.py + generators_news.py + ...
    → 7 个模块加载顺序线性，无环 ✅
  ```
```

---

## 3. 设计目标

| 维度 | 目标 | 衡量标准 |
|:-----|:-----|:---------|
| **可维护性** | 每个文件聚焦单一职责 | generators.py < 300 行，api.py < 300 行 |
| **可测试性** | 各模块可独立测试 | 各模块有独立测试文件，UT 覆盖核心逻辑 |
| **渐进扩展** | 新增 LLM 模块不加剧膨胀 | 新 LLM 模块 = 新增 `generators_xxx.py` + 注册，不对已有文件增行 |
| **向后兼容** | 已有消费者无缝过渡 | 所有外部 import 路径在过渡期保持可用 |
| **无行为变更** | 纯结构性重构 | 全部测试（场景/单元/集成）通过，无功能回退 |
| **无循环依赖** | 模块间依赖为有向无环图 | `python -c "import src.python.llm"` 成功，无 ImportError |
| **导入性能** | 导入时间不显著增加 | 拆分后 `time python -c "import src.python.llm"` ≈ 拆分前 ±20% |

---

## 4. 拆分方案

### 4.1 generators.py → 3 文件方案

采用**横向（by 职责）**拆分，非纵向（by provider）：

| 新文件 | 迁出部分 | 迁移代码行数 | 目标大小 |
|:-------|:---------|:-----------:|:--------:|
| `generators_news.py` | 新闻关联分析（_apply_llm_news_correlation ~ enhance_news_correlation） | ~262 行 | ~270 行 |
| `generators_orchestrator.py` | 批量编排（_compute_module_cache_info ~ generate_all_llm） | ~258 行 | ~280 行 |
| `generators.py`（保留） | 4 个单体生成函数 + 导入/__all__ | 原 750→~230 行 | ~230 行 |

**选择理由：**
- 3 个逻辑域在 generators.py 中已有清晰的分隔线（`══════` 注释），物理拆分自然
- 新闻关联分析有独立的缓存策略（逐条缓存 + 分批并行 + JSON 解析），与标准模块差异大
- 批量编排使用了 ThreadPoolExecutor 和 HTTP 连接池，与单体生成函数属于不同抽象层次
- 新闻关联分析未来可能独立于 LLM 模块运行，单独文件有利于独立演化

### 4.2 api.py → 2 文件方案

采用**纵向（by 抽象层次）**拆分：

| 新文件 | 迁出部分 | 迁移代码行数 | 目标大小 |
|:-------|:---------|:-----------:|:--------:|
| `api_base.py` | 共享基础设施（常量+检测+内容提取+失败追踪+重试骨架） | ~486 行 | ~500 行 |
| `api.py`（保留） | Provider 路由 + Thinking 注入 + 实现（_call_llm ~ _call_openai） | 原 702→~216 行 | ~220 行 |

**设计要点：**
- **`_last_llm_failure_reason` 随 `_call_llm_with_retry` 迁入 api_base.py**（而非留在 api.py）——解决循环导入风险
- `_configure_extended_thinking` 留在 api.py（与 `_call_claude` 同属 Provider 实现层）
- 基础设施被 skeleton.py 和 generators.py 直接使用，拆出后外部不再依赖 api.py
- 后续新增 LLM provider（如 DeepSeek 原生 API）只需在 api.py 扩展路由
- 不按 provider 拆分的原因是 Claude/OpenAI 实现代码太少（~60+55 行），单独文件收益有限

### 4.3 命名与版本

| 旧路径 | 新路径 | 过渡策略 |
|:-------|:-------|:---------|
| `llm/generators.py` | 不变（瘦身） | 迁出代码 + 加 re-export → 移除 |
| — | `llm/generators_news.py` | 新增 |
| — | `llm/generators_orchestrator.py` | 新增 |
| `llm/api.py` | 不变（瘦身） | 迁出代码 + 加 re-export → 移除 |
| — | `llm/api_base.py` | 新增 |

---

## 5. 技术设计

### 5.1 api_base.py 接口设计

```python
"""LLM API 基础模块 — 共享的常量、检测函数、失败追踪与重试骨架。"""

# ── 常量 ──
_LLM_TIMEOUT: float = 120.0
_RETRY_DELAYS: list[float] = [1.0, 3.0, 5.0, 10.0, 15.0]
_TRUNCATION_MARKER: str = "【⚠ 输出已被截断"
_AUTO_INCREASE_FACTOR: float = 1.5
# _CONTENT_FILTER_RECOVERY（留在 api.py，仅 _call_llm 使用 — 见修正记录）
_CACHE_LINE_HTML: str = ...
_THINKING_SUPPORTED_PREFIXES: tuple = ...
_THINKING_EFFORT_MODEL_PREFIXES: tuple = ...

# ── 失败追踪（从 api.py 迁入，解决 R1 循环导入风险） ──
_last_llm_failure_reason: str | None = None
_clear_last_llm_failure() -> None
_get_last_llm_failure() -> str | None

# ── 工具函数 ──
_cache_line_model_tpl(model: str) -> str
_supports_extended_thinking(model: str) -> bool
_is_effort_model(model: str) -> bool
_truncation_warning(config_field: str) -> str
_check_claude_truncation(data: dict, max_tokens: int, label: str, config_field: str) -> bool
_check_openai_truncation(data: dict, max_tokens: int, label: str, config_field: str) -> bool
_extract_content(data: dict) -> str | None
_extract_model_from_cached(html: str) -> str
_log_token_usage(provider: str, usage: dict | None, label: str, model_name: str) -> None
_get_retry_max(llm_config: dict) -> int
_sanitize_endpoint(endpoint: str) -> str

# ── 重试骨架 ──
_check_circuit_breaker(url: str, label: str) -> bool
_process_success_response(data, extract_fn, check_truncation_fn, max_tokens, 
                          config_field, provider, model_name, label, url) -> tuple
_attempt_api_call(client, url, headers, payload, timeout) -> tuple
_is_retry_available(label: str, attempt: int, max_retries: int, detail: str, url: str) -> bool
_call_llm_with_retry(label, client, url, headers, payload, timeout, max_retries,
                      max_tokens, config_field, extract_fn, check_truncation_fn,
                      provider, model_name) -> tuple[str | None, dict | None]
```

**依赖关系：** `api_base.py` 不反向依赖任何 `llm` 子模块。仅依赖：
- `circuit_breaker.py`（`_check_circuit_breaker/attempt_api_call` 中用）
- `pricing.py`（`_log_token_usage` 中费用估算）
- `session.py`（`_process_success_response` 中 `_track_session_usage`）

**更新后的依赖流向：**
```
# 之前（有环风险）:
api_base.py → ? 无法访问 _last_llm_failure_reason

# 之后（无环）:
api_base.py (owns _last_llm_failure_reason)
    ↑ 提供所有基础设施
api.py (imports from api_base.py: _last_llm_failure_reason, _call_llm_with_retry, ...)
    ↑
skeleton.py (imports from api_base.py + api.py)
```

### 5.2 generators_news.py 接口设计

```python
"""LLM 新闻关联分析模块 — LLM 增强的新闻与持仓关联分析。"""

# ── 全部 7 个符号（从 generators.py 迁出） ──
_apply_llm_news_correlation(news_batch, llm_response) -> list[tuple[str, str, str]]
_select_top_news(news_data, top_n) -> tuple[list[dict], dict[int, int]]
_build_news_hooks(top_news, holdings, penetrated_assets, industry_data, llm_config) -> tuple
_map_llm_results(results_map, top_to_original) -> dict[int, tuple]
_merge_llm_analysis(news_data, analysis_by_orig_idx) -> tuple[list[dict], int]
_finalize_news_token_usage(...) -> dict
enhance_news_correlation(news_data, holdings, ...) -> tuple[list[dict], bool, dict]
```

**依赖：** `skeleton.py`（`_generate_llm_module`），`api_base.py`（仅缓存行常量），`fingerprint.py`，`prompts.py`，`pricing.py`，`session.py`

**设计要点：**
- 不含 `generate_all_llm` 和 4 个单体生成函数的任何代码
- `enhance_news_correlation` 作为唯一公共 API（通过 `__init__.py` 暴露）
- 内部 6 个辅助函数保持私有（`_` 前缀），但不禁止在测试中直接测试

### 5.3 generators_orchestrator.py 接口设计

```python
"""LLM 批量编排模块 — 并行生成全部 LLM 模块内容。"""

# ── 公开 API ──
generate_all_llm(a_indices, us_indices, total_mv, ...) -> tuple

# ── 内部函数（从 generators.py 迁出） ──
_LLM_CLIENT_SETTINGS: dict
_compute_module_cache_info(...) -> dict[str, dict]
_precheck_one_cache(cache_info, llm_config, module_key) -> tuple
_precheck_all_modules(llm_config, cache_info, force) -> dict[str, dict]
_dispatch_llm_workers(needs, llm_config, ...) -> dict[str, dict]
```

**依赖：** `generators.py`（4 个单体函数），`skeleton.py`（`_is_llm_module_enabled`），`api_base.py`（`_CACHE_LINE_HTML`, `_LLM_TIMEOUT`），`fingerprint.py`，`prompts.py`，`session.py`，`cache.py`，`config.py`，`registry.py`

**设计要点：**
- 单向依赖：orchestrator → generators（调用 4 个单体函数），不可反向
- `_LLM_CLIENT_SETTINGS` 随 `_dispatch_llm_workers` 迁入（唯一使用者）
- 不创建新的公共 API（`generate_all_llm` 已通过 `__init__.py` 暴露）

### 5.4 过渡期 re-export 策略

"先加法、后减法"三阶段过渡原则：

```
Phase 1（加法）:  新文件 a.py = 复制代码 + 旧文件 b.py re-export → runs 🔴(从旧路通)
Phase 2（迁移）:   消费者改走新路径 + 每次更新后跑受影响测试 → runs 🟢(两条路通)
Phase 3（减法）:   确认无消费者走旧路 + 移除 b.py re-export → runs 🟢(仅新路径)

┌───────┐     ┌──────────┐     ┌───────┐
│ Phase 1├────→│ Phase 2  ├────→│ Phase 3│
│ 加法   │     │ 迁移      │     │ 减法   │
│ (re-  │     │ (旧路→新路)│     │ (移除  │
│  export)│     │          │     │  旧代码)│
└───────┘     └──────────┘     └───────┘
```

每个完整的"加→移→删"周期 = 3 轮迭代（基线轮除外）。

### 5.5 `__init__.py` 导出更新

拆分后 `__init__.py` 的公共 API 保持完全一致：

```python
# __init__.py（最终状态 — Iteration 12 后）
from src.python.llm.generators_orchestrator import generate_all_llm  # noqa: F401
from src.python.llm.generators_news import enhance_news_correlation  # noqa: F401
from src.python.llm.prompts import (  # noqa: F401
    FAIL_REASON_API_ERROR, FAIL_REASON_CIRCUIT_OPEN, FAIL_REASON_DISABLED,
    FAIL_REASON_NETWORK_ERROR, FAIL_REASON_NOT_CONFIGURED, FAIL_REASON_TIMEOUT,
)
from src.python.llm.session import format_session_usage, get_session_usage  # noqa: F401
```

外部消费者（handlers_report.py, report/*.py）的 `from src.python.llm import xxx` 全程不受影响。

### 5.6 测试策略与测试文件映射

**⚠️ 测试类迁移原则（TD-7）：** 新增测试文件时**必须同时从 `test_llm.py` 迁出对应测试类**，不得仅写新测试。
迁移方法：`git mv` + 更新 import 路径（`git mv` 保留 git 历史）。

| 新模块 | 现有测试（应迁移出 test_llm.py 的类） | 新增测试文件 | 测试重点（必测路径） |
|:-------|:---------|:------------|:--------------------|
| `api_base.py` | test_api.py(部分) + test_llm.py(部分) | `test_api_base.py`, `test_api_base_edge.py` | 重试边界(0/1/N次), 截断检测Claude/OpenAI, 空内容提取, content_filter安抚, _call_llm_with_retry熔断→重试→成功 |
| `generators_news.py` | test_llm.py(部分) | `test_generators_news.py`, `test_generators_news_edge.py` | JSON解析成功/失败/部分缺失, 全缓存/部分缓存/无缓存, markdown代码块剥离, 空news_data |
| `generators_orchestrator.py` | test_generators.py(部分) | `test_generators_orch.py`, `test_generators_orch_edge.py` | 指纹预计算全模块, 全缓存跳过dispatch, 线程异常传播, llm_max_concurrency=1, h2降级路径 |
| `api.py`（瘦身后） | test_api.py | 更新 import | Provider路由覆盖(fallback), Thinking注入正确性 |
| `generators.py`（瘦身后） | test_generators.py | 更新 import | 4个单体函数调用骨架(无需mock API, feign cache hit) |

**新增文件命名规范：**
- 常规测试：`test_api_base.py`, `test_generators_news.py`, `test_generators_orch.py`
- 边缘测试：`test_api_base_edge.py`, `test_generators_news_edge.py`, `test_generators_orch_edge.py`
- `orchestrator` 缩写为 `orch`（避免文件名超长）

### 5.10 覆盖矩阵验证

每个迭代步完成后，使用下列矩阵验证测试覆盖完整性：

| 模块 | 必须覆盖的路径 | 对应 Iteration | 验证命令 |
|:-----|:--------------|:--------------:|:---------|
| `api_base.py` | `_call_llm_with_retry`: 熔断→None, 首次成功, 重试后成功, 耗尽→None; `_extract_content`: 列表/字符串/think block/空/error; `_check_*_truncation`: max_tokens/end_turn/异常; `_attempt_api_call`: 200/429/503/Timeout/JSONError; `_last_llm_failure_reason`: 正常/清除/跨模块读; `_supports_extended_thinking`: 支持/不支持/空 | I-04 | `pytest src/test/unit/llm/test_api_base*.py -v` |
| `generators_news.py` | `enhance_news_correlation`: 空news/全缓存/全未缓存/部分缓存; `_apply_llm_news_correlation`: 正常JSON/md代码块/index缺失/非数组/JSONError; `_select_top_news`: 空/全无关键词/正常排序; `_merge_llm_analysis`: 全富化/部分/无 | I-06 | `pytest src/test/unit/llm/test_generators_news*.py -v` |
| `generators_orch.py` | `generate_all_llm`: llm_config=None/全cached/混合; `_precheck_one_cache`: 命中/未命中/disabled; `_dispatch_llm_workers`: 全需生成/全cached/部分异常; `_compute_module_cache_info`: 4模块key正确; 线程异常传播; concurrency=1 | I-09 | `pytest src/test/unit/llm/test_generators_orch*.py -v` |
| `api.py`(瘦身后) | `_call_llm`: provider路由/fallback; `_call_claude`: thinking注入; `_call_openai`: 正常调用 | I-11 | `pytest src/test/unit/llm/test_api*.py -v` |
| `generators.py`(瘦身后) | 4个单体函数调用骨架(不mock API, feign cache hit) | I-10 | `pytest src/test/unit/llm/test_generators.py -v` |

### 5.7 每个新文件的 `__all__`

```python
# api_base.py
__all__ = [
    "_last_llm_failure_reason",
    "_clear_last_llm_failure", "_get_last_llm_failure",
    "_LLM_TIMEOUT", "_RETRY_DELAYS", "_TRUNCATION_MARKER", "_AUTO_INCREASE_FACTOR",
    "_CACHE_LINE_HTML", "_cache_line_model_tpl",
    "_MODEL_LINE_RE", "_THINKING_SUPPORTED_PREFIXES", "_THINKING_EFFORT_MODEL_PREFIXES",
    "_supports_extended_thinking", "_is_effort_model", "_truncation_warning",
    "_check_claude_truncation", "_check_openai_truncation", "_extract_content",
    "_extract_model_from_cached", "_log_token_usage", "_get_retry_max", "_sanitize_endpoint",
    "_check_circuit_breaker", "_process_success_response", "_attempt_api_call",
    "_is_retry_available", "_call_llm_with_retry",
]

# generators_news.py
__all__ = [
    "_apply_llm_news_correlation", "_select_top_news", "_build_news_hooks",
    "_map_llm_results", "_merge_llm_analysis", "_finalize_news_token_usage",
    "enhance_news_correlation",
]

# generators_orchestrator.py
__all__ = [
    "_LLM_CLIENT_SETTINGS",
    "_compute_module_cache_info", "_precheck_one_cache", "_precheck_all_modules",
    "_dispatch_llm_workers", "generate_all_llm",
]
```

### 5.8 `skeleton.py` import 迁移计划

最终状态：

```python
# skeleton.py — 最终状态的 import
# ── 从 api_base.py 导入基础设施 + 失败追踪 ──
from src.python.llm.api_base import (
    _AUTO_INCREASE_FACTOR, _CACHE_LINE_HTML, _LLM_TIMEOUT, _TRUNCATION_MARKER,
    _cache_line_model_tpl, _extract_model_from_cached, _get_last_llm_failure,
)

# ── 从 api.py 导入 Provider 调用 ──
from src.python.llm.api import (
    _call_llm, _clear_last_llm_failure,
)
```

`generators.py` 的最终 import：

```python
# generators.py — 最终状态的 import
from src.python.llm.api_base import (
    _CACHE_LINE_HTML, _LLM_TIMEOUT, _cache_line_model_tpl, _extract_model_from_cached,
    _log_token_usage,
)
```

### 5.9 跨模块可变状态清单（核实安全）

| 模块变量 | 定义位置 | 读写来源 | 拆分后变化 | 线程安全？ |
|:---------|:---------|:---------|:-----------|:----------|
| `_session_usage` | `session.py` | api.py→api_base.py → session.py | 不变（锁保护） | ✅ 有 `_session_lock` |
| `_LLM_MODULE_FAILURE` | `prompts.py` | skeleton.py + generators.py + orchestrator.py + 报告模块 | 增加 generators_news.py 写 | ⚠️ 无锁，但单次会话内串行或按模块写 |
| `_last_llm_failure_reason` | **api.py → 迁至 api_base.py** | api.py(删) + api_base.py + skeleton.py | 迁入 api_base.py，消除循环依赖 | ✅ 被重试逻辑串行访问 |
| `_circuit_failures/_circuit_open_until` | `circuit_breaker.py` | api_base.py | 不变 | ✅ 有 `_circuit_lock` |

**`_LLM_MODULE_FAILURE` 设计债务说明：** 该字典无显式锁保护，但实践中仅被串行写入（每个模块在生成完成时写入一次），不会在同一个会话中发生同一 key 的并发写。拆分增加了写入模块数量（+1），但不改变并发模式。此为已知接受的债务。

---

## 6. 设计债务（已知接受）

本拆分引入的或保留的已知技术债务，在拆分完成后持续有效：

| # | 债务 | 严重度 | 原因 | 何时应修复 |
|:-:|:-----|:------:|:-----|:----------|
| TD-1 | **`_LLM_MODULE_FAILURE` 无锁** | 🟡 中 | 多模块写入同一 dict，但不并发。拆分后新增 generators_news.py 写入，并发模式不变 | 如果未来批处理模式改为真并行写多个 key |
| TD-7 | **`test_llm.py` 97K 单体测试文件 — 拆分后 10 个测试类应迁移但计划未覆盖** | 🟡 中 | test_llm.py 含 29 个测试类/2039 行。拆分后 5 个 api_base 类 + 5 个 generators_news 类应迁出而未迁，导致 import 变更达 ~43 处且需反复更新 test_llm.py import。单文件 97K 降低可维护性。 | I-04 时将 `TestSupportsExtendedThinking/TestIsEffortModel/TestLogTokenUsage/TestExtractContent/TestCheckTruncation` 移至 `test_api_base.py`；I-06 时将 `TestBuildNewsSummary/TestApplyLLMAnalysis/TestBatchNewsAnalysis/TestEnhanceNewsCorrelation/TestEnhanceNewsCorrelationUsesLlmConfig/TestEnhanceNewsCorrelationGranularCache` 移至 `test_generators_news.py`。目标：test_llm.py ≤ 1500 行 || TD-6 | **`skeleton.py` 持续膨胀风险（491 行，接近警戒线）** | 🟡 中 | R-198 后 skeleton.py 成为所有 generators_*.py 的枢纽模块（接口最密集），任一新 LLM 模块都需在 skeleton.py 注册。491 行且仍在增长，无拆分计划 | 当 skeleton.py ≥ 600 行时，启动拆分计划：① 将 `_generate_llm_module` 调用链抽为 `skeleton_registry.py` ② `_handle_truncation`/`_handle_cache_hit` 等工具函数抽到 `api_base.py` 或独立 `utils.py` ③ 将 Thinking 兼容性检查移至 `api.py` 或独立判断模块。监控：每 100 行检查一次行数增长趋势 |

| TD-2 | **`api_base.py` 依赖 `pricing.py` 和 `session.py`** | 🟢 低 | 基础设施模块不应知道费用估算细节，但 `_log_token_usage` 需要 `_estimate_cost` | 如果 `_log_token_usage` 重构为纯日志函数 |
| TD-3 | **`generators.py` 仍需要 `httpx` import** | 🟢 低 | 仅为函数签名中的类型标注 `http_client: httpx.Client \| None` | Python 3.10+ 可改用 `from __future__ import annotations` |
| TD-4 | **`generators_news.py` 与 `generators.py` 共享几乎相同的 import 集** | 🟢 低 | 两个文件都 import skeleton.py / fingerint / prompts 等，存在重复 | 如果抽取出公共的 import helper |
| TD-5 | **`_LLM_CLIENT_SETTINGS` 和 `_dispatch_llm_workers` 中的 h2 降级逻辑** | 🟡 中→🔴 C5 违规 | httpx HTTP/2 fallback 违背 C5（HTTP 客户端统一），拆分前仅在 generators.py 违规，拆分后扩散至 generators.py + generators_orchestrator.py 两文件 | **待办：在 plan.md 中创建 R-XYZ 任务 `http_client.py 统一化`**，将 `_dispatch_llm_workers` 的 httpx.Client 替换为统一客户端。关闭条件：① `grep -rn "httpx.Client(" src/python/llm/ --include="*.py" | grep -v test` 返回 0；② 所有引用 _dispatch_llm_workers 的测试通过；③ 导入性能退化 < 5% |

---

## 7. 未来新增 LLM 模块的文件放置约定

为防止拆分完成后 generators.py 再次膨胀，明确约定：

### 7.1 新增 LLM 分析模块的流程

```
新增 LLM 模块时:
  1. 该模块是否已有对应的 generators_xxx.py?
     → 是: 追加到对应文件
     → 否: 继续判断
  2. 该模块是否属于"单体生成"模式（单次调用 LLM → 返回 HTML）？
     → 是: 追加到 generators.py
     → 否: 继续判断
  3. 新增 generators_{功能}.py，遵循以下约定:
     - 文件命名: generators_{功能}.py（全小写+下划线）
     - __all__ 必须包含所有私有+公共符号
     - 公共 API 通过 __init__.py 注册
     - 在 registry.py 注册 settings_suffix
     - 在 skeleton.py 的 _generate_llm_module 调用链中注册
```

**新增 generators_xxx 的完整注册模板（以"环比分析"为例）：**

```python
# 1. src/python/registry.py — 新增 DataModuleDef
DataModuleDef(
    name="环比分析",
    data_type="llm_mom_analysis",
    cache_ttl=3600,
    settings_suffix="mom_analysis",          # ★ 与 module_key 一致
)

# 2. src/python/llm/generators_mom.py — 新增模块文件（自动派生 llm.mom_analysis key）
from src.python.llm.skeleton import _generate_llm_module, _MN
from src.python.llm.prompts import _SYSTEM_MOM_ANALYSIS as _sys_prompt
from src.python.llm.fingerprint import _build_llm_fingerprint

def generate_mom_analysis(...) -> tuple[str | None, bool]:
    return _generate_llm_module(
        llm_config, "mom_analysis",             # module_key = settings_suffix
        fingerprint_fn=_build_llm_fingerprint,
        system_prompt_default=_sys_prompt,
        # 选择模式：省略 batch_preparer → 标准模式（单次调用）
    )

# 3. src/python/llm/__init__.py — 导出公共 API
from src.python.llm.generators_mom import generate_mom_analysis  # noqa: F401
```

**模式选择指南：**
- **标准模式**（无 `batch_preparer`）：模块内容为单次 LLM 调用的 HTML 输出 → 函数放入 generators.py 或新增 generators_xxx.py
- **批量模式**（有 `batch_preparer`）：模块需要对多条输入逐条/分批调用 LLM（如 news_correlation）→ **必须** 新建 generators_xxx.py

### 7.2 文件大小门禁

| 文件 | 警戒线 | 拆分线 |
|:-----|:------:|:------:|
| `generators.py` | 250 行 | **300 行**（超过需拆分） |
| `generators_news.py` | 300 行 | **400 行**（超过需拆分） |
| `generators_orchestrator.py` | 300 行 | **400 行**（超过需拆分） |
| `api.py` | 250 行 | **300 行**（超过需拆分） |
| `api_base.py` | 500 行 | **600 行**（超过需拆分） |

### 7.3 新增 provider 的约定

新增 LLM provider（如 DeepSeek 原生 API）时：
1. 在 `api.py` 中新增 `_call_{provider}()` 函数
2. 在 `_call_single_provider()` 中新增路由分支
3. 在 `_call_llm()` 的 content_filter 代码中增加 provider 检查
4. 不在 `api_base.py` 中添加任何 provider 特定代码
5. 如新增 provider 使用新模型前缀（新 thinking/effort 前缀），同步更新 `api_base.py` 中的 `_THINKING_SUPPORTED_PREFIXES` 和 `_THINKING_EFFORT_MODEL_PREFIXES`
6. 如新增 provider 的 API 格式不同（非 messages 格式、流式响应等），在 `_call_single_provider` 中新增路由分支
7. 验证新增 provider 后 `_supports_extended_thinking()` 和 `_is_effort_model()` 的正确性

**新增 Provider 后的验证清单：**
```bash
# 验证 thinking 前缀支持
python -c "from src.python.llm.api_base import _supports_extended_thinking; assert _supports_extended_thinking('deepseek-v4-xxx'); print('[OK]')"
# 验证 effort 模型前缀
python -c "from src.python.llm.api_base import _is_effort_model; assert _is_effort_model('deepseek-v4-xxx'); print('[OK]')"
# 验证 provider 路由
python -c "from src.python.llm.api import _call_single_provider; print('[OK]')"
```

---

## 8. 风险与缓解

### 8.1 风险矩阵

| # | 风险 | 概率 | 影响 | 缓解措施 |
|:-:|:-----|:----:|:----:|:---------|
| R1 | **循环导入**：`api_base.py` 反向 import api.py，或 generators 新模块间交叉引用 | **中** | **高** | ① 严格单向依赖（见 §2.4 目标依赖图）② `_last_llm_failure_reason` 迁入 api_base.py（消除最大环风险）③ 每次迭代后运行 `python -c "import src.python.llm"` 全模块导入验证 |
| R2 | **测试遗留**：旧测试从旧路径 import 但旧文件 re-export 不全导致符号丢失 | **中** | **中** | ① 利用 `__all__` 清单对比两侧导出完整性 ② 每次迭代后跑完整 UT 集 ③ re-export 阶段使用 `# noqa: F401` |
| R3 | **merge 冲突**：拆分期间并行开发修改了 generators.py/api.py 的对应行 | **低** | **高** | ① 协调避免并行大型重构 ② 拆分周期短（预期 2-3 天）③ 每轮迭代独立 commit |
| R4 | **`__init__.py` 导出遗漏**：外部消费者通过 `from src.python.llm import xxx` 但新模块未加入 `__init__.py` | **低** | **高** | ① 在 `__init__.py` 添加新模块的公共 API 导出 ② 使用 `grep -rn "from src.python.llm import"` 检查所有外部消费者 |
| R5 | **线程安全**：拆分后模块级状态被多个线程意外共享 | **低** | **中** | ① 跨模块可变状态清单（§5.9）逐一核查 ② 新闻关联分析的 token 统计函数锁机制保留不变 |
| R6 | **`_LLM_CLIENT_SETTINGS` 跨模块引用**：该 dict 定义在 generators.py 中，仅 `_dispatch_llm_workers` 使用 | **中** | **低** | 随 `_dispatch_llm_workers` 迁移至 `generators_orchestrator.py` |
| R7 | **`_last_llm_failure_reason` 重复定义**：迁移时旧 api.py 中的定义未正确删除 | **中** | **中** | Phase 3（减法）时双重确认：grep 旧定义已移除 + 新导入路径正确 |
| R8 | **ruff/F401 误报**：re-export 行被 linter 标记为未使用 | **低** | **低** | re-export 统一加 `# noqa: F401` 注释；对 `generators.py` 中残留 import 做减法时运行 `ruff check` |

### 8.2 依赖环检测

每次 re-export 变更后运行：

```bash
# 基础验证
python -c "import src.python.llm"
echo "[OK] 无循环导入"

# 完整验证（全部子模块）
python -c "
import src.python.llm.api_base
import src.python.llm.api
import src.python.llm.generators_news
import src.python.llm.generators_orchestrator
import src.python.llm.generators
import src.python.llm.skeleton
import src.python.llm
print('[OK] 全部 LLM 子模块可独立导入')
"
```

### 8.3 回退策略

每轮迭代都有明确的回退点：

```
失败场景                          → 修复方式
──────────────────────────────────────────────────
Iteration N Phase 1 (re-export)  追加遗漏符号即可修复
Iteration N Phase 2 (consumer)   该消费者回退到旧路径（2 步内修复）
Iteration N Phase 3 (remove)     恢复被删除的行（git checkout）
整个拆分不可控                    git reset --hard 上一轮 commit
```

**关键：每轮迭代完成后必须 git commit，确保每次都有明确的可回退版本。**

---

## 9. 设计约束遵守清单

technical.md 的设计约束（C1~C14）中与本拆分相关的检查：

| # | 约束 | 检查项 | 状态 | 验证方式 |
|:-:|:-----|:-------|:----:|:---------|
| C5 | HTTP 客户端统一 | `_dispatch_llm_workers` 使用 `httpx.Client(Limits(...))` 和 h2 降级已存在。**拆分后从 1 文件扩散到 2 文件**（generators.py 残留 + generators_orchestrator.py 新增），C5 违规扩大化 | 🔴 继承扩散 | 拆分不新增 `httpx.Client()` 调用实例，但违规范围扩大。TD-5 需升级 🟡 跟随全局 http_client.py 统一化 |
| C8 | 日志统一 | 所有新文件使用 `logger = logging.getLogger("invest")` | ✅ 强制 | grep 'getLogger' 检查 |
| C9 | LLM 模块注册 | generators_news/orchestrator 的公共 API 已在 `__init__.py` 注册。`settings_suffix`（registry.py）不受拆分影响 | ✅ 强制 | `__init__.py` 最终状态含并检查 |
| C11 | 测试标记强制 | 新测试文件标注 `@pytest.mark.unit_llm`，边缘文件标注 `@pytest.mark.edge` | ✅ 强制 | conftest 自动校验 |
| C12 | 边缘测试文件隔离 | `test_*_edge.py` 命名强制 | ✅ 强制 | conftest 自动校验 |
| C13 | 测试敏感路径隔离 | 不涉及 data/config 写入 | ✅ 无影响 | — |
| C14 | 渲染期数据不写入模块级全局变量 | 不涉及 Jinja2 渲染 | ✅ 无影响 | — |
| **C4-note** | 虽不直接约束，但拆分后的各模块应确保单次会话内的 LLM API 调用次数不被拆分影响 | 相同缓存/批处理逻辑 | ✅ 已验证 | `generate_all_llm` 调用次数逻辑不变 |

**需要部分检查的约束（原标注为"不涉及"但实际需关注）：**
- C2（缓存统一管理）→ ⚠️ 拆分后缓存指纹/键/TTL 计算分散在 `fingerprint.py` + `generators_orchestrator.py` 两个文件，增加了追踪难度
- C4（API 复用缓存）→ ⚠️ `_dispatch_llm_workers` 使用了独立 `httpx.Client(Limits(...))` 连接池，虽不走 Provider Chain，但多了一个自定义 HTTP 客户端实例
- C5（HTTP 客户端统一）→ 🔴 TD-5 已承认违规，拆分后扩大化至 2 个文件

**不需要检查的约束：**
- C1（代码类型判定中心化）→ 不涉及资产类型判定
- C3（缓存原子写入）→ 通过 skeleton.py → cache.py 间接遵守
- C6/C7/C10 → 不相关

---

## 10. 迭代计划

共 **14 轮**迭代，每轮可独立 commit、独立验证、独立回退。
（相比初版 14 轮，新增 1 轮：Thinking 路由独立迁移。导入基线验证降级为全量回归的子检查项；原 Iteration 11+12 合并为 1 轮。）

> ⚠️ **分支策略**：所有 14 轮迭代**必须在独立特性分支**（如 `refactor/r198-llm-split`）上完成，
> 不得直接在 `dev` 分支提交。原因：① 14 个原子 commit 在 `dev` 上会与其他开发 commit 交织，
> 导致批量回退（`git revert HEAD~N`）不可用；② 特性分支允许 PR review，合并时 squash 为一个
> 完整提交到 `dev`；③ 分支隔离确保拆分失败时可删除分支而不影响 `dev` 稳定性。
> 创建命令：`git checkout -b refactor/r198-llm-split dev`

> > **PR 审查要求**：每 3-4 轮迭代后向 `dev` 发起一次 squash merge PR，审查清单：
> 1. `__all__` 两侧逐符号核对（§11 对照表）
> 2. 所有 `@patch` mock 路径已更新到新模块命名空间（§11.3）
> 3. `[导·反证]` 旧路径已切断（ImportError 验证通过）
> 4. ruff 无 F401/F811 误报
> 5. 无未迁移的 test_llm.py 测试类（TD-7 检查）
> 6. 通过的测试门禁：regression + 单元测试
> 7. `wc -l src/python/llm/*.py` 行数变化对比
> 
### 符号说明

```
[测] pytest src/test/unit/llm/         运行 LLM 单元测试
[全] python scripts/test_runner.py --mode regression  运行回归测试
[导] python -c "import src.python.llm"  验证导入无环
[基] wc -l ...src/python/llm/*.py      行数基线测量
[时] time python -c "import src.python.llm" 2>&1 | grep real  导入时间测量
[鲁] ruff check src/python/llm/         linter 检查
```

---

### 迭代 1/14：基线测量与测试就绪

**目标：** 建立可量化的基线，创建新测试文件骨架。

**任务清单：**

1. [ ] 测量基线行数：
   ```bash
   wc -l src/python/llm/generators.py src/python/llm/api.py src/python/llm/skeleton.py
   ```
2. [ ] 记录 generators.py 中 3 个职责域的准确行号范围（用 `# ═══════` 分隔线定位）
3. [ ] 记录 api.py 中 2 个职责域的准确行号范围
4. [ ] 测量导入时间基线：
   ```bash
   hyperfine -w 3 'python -c "import src.python.llm"' --export-csv /dev/null
   # 或用 time 命令: time python -c "import src.python.llm" 2>&1
   ```
5. [ ] 运行完整单元测试确认基线：
   ```bash
   pytest src/test/unit/llm/ -v --tb=short 2>&1 | tail -20
   ```
6. [ ] 运行场景测试确认基线：
   ```bash
   pytest src/test/scenario/llm/ -v --tb=short 2>&1 | tail -20
   ```
7. [ ] 创建 6 个新测试文件骨架（仅 import 占位 + 1 条无操作跳过测试）：
   - `test_api_base.py` / `test_api_base_edge.py`
   - `test_generators_news.py` / `test_generators_news_edge.py`
   - `test_generators_orch.py` / `test_generators_orch_edge.py`
8. [ ] 记录基线到 `docs-stm/managements/test-coverage.md`

**验收标准：**
- [ ] 6 个新测试文件已存在（import 测试+1 条 placeholder test，全部标 `pytest.mark.skip`）
- [ ] 所有现有测试均通过（0 failure, 0 error）
- [ ] 行数和导入时间基线已记录到文档
- [ ] 回退点：**git commit** `r198-iter01-baseline`

---

### 迭代 2/14：创建 api_base.py（常量 + 工具 + 重试骨架 + 失败追踪）

**目标：** 一次性创建完整的 api_base.py（不再分 2 步迁出），迁入所有基础设施、失败追踪和重试骨架。

**要点：** 迭代 2 和 3 合并的原因——常量、工具函数和重试骨架之间无自然隔离边界，一起迁出可减少一次 re-export 过渡周期。

**任务清单：**

1. [ ] 创建 `src/python/llm/api_base.py`
2. [ ] 从 api.py **复制**以下内容（保留完整签名和注释）：

   **常量区：**
   - `_LLM_TIMEOUT` ~ `_CACHE_LINE_HTML`（L60-L111）
   
   **失败追踪（** 关键：迁入 api_base.py 解决循环依赖 **）：**
   - `_last_llm_failure_reason` 变量
   - `_clear_last_llm_failure()` / `_get_last_llm_failure()`（L43-L56）
   
   **工具函数：**
   - `_cache_line_model_tpl` / `_MODEL_LINE_RE`
   - `_THINKING_SUPPORTED_PREFIXES` ~ `_is_effort_model`
   - `_truncation_warning` / `_check_claude_truncation` / `_check_openai_truncation`
   - `_extract_content` / `_extract_model_from_cached`
   - `_log_token_usage` / `_get_retry_max` / `_sanitize_endpoint`
   
   **重试骨架（保留 mutual exclusion 检查）：**
   - `_check_circuit_breaker`
   - `_process_success_response`
   - `_attempt_api_call`
   - `_is_retry_available`
   - `_call_llm_with_retry`
3. [ ] 在 api_base.py 编写完整的 `__all__`
4. [ ] 在 api.py 顶部添加完整的 re-export：
   ```python
   from src.python.llm.api_base import (  # noqa: F401 — re-exported for backward compat
       _last_llm_failure_reason, _clear_last_llm_failure, _get_last_llm_failure,
       _LLM_TIMEOUT, _RETRY_DELAYS, _TRUNCATION_MARKER, _AUTO_INCREASE_FACTOR,
       _CACHE_LINE_HTML, _cache_line_model_tpl,
       _MODEL_LINE_RE, _THINKING_SUPPORTED_PREFIXES, _THINKING_EFFORT_MODEL_PREFIXES,
       _supports_extended_thinking, _is_effort_model, _truncation_warning,
       _check_claude_truncation, _check_openai_truncation, _extract_content,
       _extract_model_from_cached, _log_token_usage, _get_retry_max, _sanitize_endpoint,
       _check_circuit_breaker, _process_success_response, _attempt_api_call,
       _is_retry_available, _call_llm_with_retry,
   )
   ```
5. [ ] 确认 api_base.py **不** import 任何 `src.python.llm` 其他模块（禁止反向依赖）
6. [ ] **同步更新 Mock 路径** — `_call_llm_with_retry` 迁入 api_base.py 后 `@patch("api._cb_is_open")` 等 mock 失效，使用 SS 11.3 sed 命令同一步批量替换

**验证：**
- [ ] `[导] python -c "from src.python.llm.api_base import _call_llm_with_retry, _last_llm_failure_reason"`
- [ ] `[导] python -c "from src.python.llm.api import _call_llm_with_retry, _last_llm_failure_reason"`（通过 re-export）
- [ ] `[导] python -c "import src.python.llm; print([m for m in src.python.llm.api_base.__dict__ if not m.startswith('_')])"`
- [ ] `[基] wc -l src/python/llm/api_base.py`（预期 ~500 行）
- [ ] `[基] wc -l src/python/llm/api.py`（预期 ~216 行）
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[测] pytest src/test/unit/llm/test_api.py -v --tb=short`（re-export 应保证通过）
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -v --tb=short`
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] api_base.py 包含完整的常量、工具函数、失败追踪、重试骨架
- [ ] api.py 通过 re-export 保持完全向后兼容
- [ ] api_base.py 无循环导入
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter02-api-base-created`

**风险 R1：** 低（纯加法 + 单向依赖）。

---

### 迭代 3/14：更新 skeleton.py + generators.py — 指向 api_base

**目标：** 将 skeleton.py 和 generators.py 中导入 api.py 的基础设施符号改为从 api_base.py 导入。

**任务清单：**

1. [ ] 更新 `skeleton.py` 的 import 路径（将原来从 api.py 导入的基础设施改为从 api_base.py 导入，保留 Provider 调用的导入）：
   ```python
   # ── 更新前 ──
   from src.python.llm.api import (
       _AUTO_INCREASE_FACTOR, _CACHE_LINE_HTML, _LLM_TIMEOUT, _TRUNCATION_MARKER,
       _cache_line_model_tpl, _call_llm, _clear_last_llm_failure,
       _extract_model_from_cached, _get_last_llm_failure,
   )
   
   # ── 更新后 ──
   from src.python.llm.api_base import (
       _AUTO_INCREASE_FACTOR, _CACHE_LINE_HTML, _LLM_TIMEOUT, _TRUNCATION_MARKER,
       _cache_line_model_tpl, _extract_model_from_cached, _get_last_llm_failure,
   )
   from src.python.llm.api import (
       _call_llm, _clear_last_llm_failure,
   )
   ```
2. [ ] 更新 `generators.py` 的 import 路径：
   ```python
   # ── 更新前 ──
   from src.python.llm.api import (
       _CACHE_LINE_HTML, _LLM_TIMEOUT, _cache_line_model_tpl,
       _extract_model_from_cached, _log_token_usage,
   )
   
   # ── 更新后 ──
   from src.python.llm.api_base import (
       _CACHE_LINE_HTML, _LLM_TIMEOUT, _cache_line_model_tpl,
       _extract_model_from_cached, _log_token_usage,
   )
   ```

**验证：**
- [ ] `[导] from src.python.llm.skeleton import _handle_truncation, _generate_llm_content`
- [ ] `[导] from src.python.llm.generators import generate_global_macro`
- [ ] `[导] python -c "import src.python.llm"`（全模块导入验证）
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[测] pytest src/test/unit/llm/test_skeleton.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_generators.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -v --tb=short`
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] skeleton.py 从 api_base.py 导入基础设施，从 api.py 导入 Provider 调用
- [ ] generators.py 从 api_base.py 导入基础设施
- [ ] 无循环导入
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter03-skeleton-import-updated`

**风险 R1：** ⚠️ 中（分成两条 import 语句可能遗漏符号，对比 `__all__` 清单逐条核对）。

---

### 迭代 4/14：编写 api_base.py 测试 + 迁移测试 import

**目标：** 为 api_base.py 编写单元测试，将测试文件中的基础设施 import 迁移到 api_base。

**任务清单：**

1. [ ] 为 `test_api_base.py` 编写实际测试（覆盖边界路径）：
   - `_extract_content`: 
     - 正常 content 列表 → 返回拼接文本
     - content 为字符串 → 直接返回
     - content 含 thinking block → 忽略 non-text block
     - content 为空列表 → 返回空字符串
     - data 含 error → 返回 None
     - data 为 None → 返回 None
   - `_check_claude_truncation` / `_check_openai_truncation`:
     - stop_reason="max_tokens" → 返回 True
     - stop_reason="end_turn" → 返回 False
     - 异常 data 格式 → 返回 False
   - `_attempt_api_call`:
     - 成功 → ("success", data)
     - 429 → ("retryable", 429)
     - 503 → ("retryable", 503)
     - httpx.TimeoutException → ("retryable", None)
     - httpx.HTTPError → ("retryable", host)
     - JSON 解析失败 → ("fatal", errmsg)
   - `_is_retry_available`:
     - attempt < max_retries → True（验证延迟）
     - attempt >= max_retries → False
   - `_sanitize_endpoint`: 各种 URL 格式
   - `_get_retry_max`: 正常/缺失/非法配置
   - `_call_llm_with_retry`:
     - 熔断 → (None, None)
     - 首次成功 → (content, usage)
     - 首次失败重试后成功 → (content, usage)
     - 全部重试耗尽 → (None, None)
     - 响应解析失败 → (None, None)
   - `_supports_extended_thinking`: 支持模型/不支持模型/空字符串
   - `_is_effort_model`: DeepSeek 前缀/Claude 前缀
2. [ ] 为 `test_api_base_edge.py` 编写边缘测试：
   - `_check_circuit_breaker`: 不同 URL 的熔断状态查询
   - `_process_success_response`: 
     - 空内容返回 → 标记 content_filter 路径
     - 截断标记 → 追加截断警告
     - usage 缺失 → 不报错
3. [ ] 更新 `test_api.py`（L20-36）：将导入的符号分为 `api_base` + `api` 两组
4. [ ] 更新 `test_llm.py`（L30-64）：将基础设施类导入指向 `api_base`
5. [ ] 更新 `test_log_sanitize.py`、`test_security_edge.py`、`test_api_edge.py` 的 import
6. [ ] 确认 `test_api.py` 不再从 api.py 导入 `_extract_content`、`_call_llm_with_retry` 等基础设施符号

**验证：**
- [ ] `[测] pytest src/test/unit/llm/test_api_base.py -v --tb=short`（>=15 条测试）
- [ ] `[测] pytest src/test/unit/llm/test_api_base_edge.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_api.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_api_edge.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -v --tb=short`
- [ ] `[全] python scripts/test_runner.py --mode regression`
- [ ] `[鲁] ruff check src/python/llm/api_base.py`
- [ ] `[测] pytest src/test/unit/ui/test_log_sanitize.py -v --tb=short`（非 llm 测试文件验证）
- [ ] `[测] pytest src/test/unit/security/test_security_edge.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_api_edge.py -v --tb=short`

**验收标准：**
- [ ] `test_api_base.py` 覆盖 >= 70% api_base.py 的函数
- [ ] `test_api_base_edge.py` 覆盖 >= 5个边缘场景
- [ ] 测试文件不再从 api.py 导入基础设施符号（可 grep `from src.python.llm.api import` 确认仅路由类符号）
- [ ] ruff 无错误
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter04-api-base-tests`

---

### 迭代 5/14：创建 generators_news.py（全部 7 个函数）

**目标：** 创建 generators_news.py，一次性迁入全部 7 个新闻相关函数 + re-export。

**任务清单：**

1. [ ] 创建 `src/python/llm/generators_news.py`
2. [ ] 从 generators.py **复制**以下内容（保留完整签名+注释+日志）：
   - `_apply_llm_news_correlation`
   - `_select_top_news`
   - `_build_news_hooks`
   - `_map_llm_results`
   - `_merge_llm_analysis`
   - `_finalize_news_token_usage`
   - `enhance_news_correlation`
3. [ ] 确保 generators_news.py 的 import 完整（需要导入 skeleton.py 的 `_generate_llm_module` 等）
4. [ ] 在 generators_news.py 编写 `__all__`
5. [ ] 在 generators.py 添加 re-export：
   ```python
   from src.python.llm.generators_news import (  # noqa: F401
       _apply_llm_news_correlation, _select_top_news, _build_news_hooks,
       _map_llm_results, _merge_llm_analysis, _finalize_news_token_usage,
       enhance_news_correlation,
   )
   ```
6. [ ] 从 generators.py 的 `__all__` 中**保留** `enhance_news_correlation` 和新闻辅助函数（Phase 2 移除）

**验证：**
- [ ] `[导] from src.python.llm.generators_news import enhance_news_correlation`
- [ ] `[导] from src.python.llm.generators import enhance_news_correlation`（通过 re-export）
- [ ] `[导] from src.python.llm import enhance_news_correlation`（通过 __init__.py → generators → re-export）
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -k "news" -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py::test_enhance_news_correlation -v`（如有）
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] generators_news.py 包含全部 7 个函数
- [ ] generators.py re-export 完整（`__all__` 两侧对比一致）
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter05-generators-news-created`

**风险 R1：** 低（纯加法 + generators.py import generators_news.py，单向依赖无环）。

---

### 迭代 6/14：迁移 generators_news 消费者 + 移除 re-export

**目标：** 将外部消费者的 import 指向 generators_news，移除 generators.py 的 re-export。

**任务清单：**

1. [ ] 确认 `report/*.py` 通过 `__init__.py` 间接引用，不需改动：
   - `news_correlation.py: from src.python.llm import enhance_news_correlation` → 保持
   - `html_renderers.py: from src.python.llm import ...` → 保持
2. [ ] 更新测试文件中的**直接 import**：
   - `test_generators.py`（L25）：
     ```python
     # 更新前: from src.python.llm.generators import _apply_llm_news_correlation
     # 更新后: from src.python.llm.generators_news import _apply_llm_news_correlation
     ```
   - `test_llm.py` 中所有 `from src.python.llm.generators import _apply_llm_news_correlation` 引用
3. [ ] **移除** generators.py 中新闻相关的 re-export
4. [ ] 从 generators.py 的 `__all__` 中移除 `enhance_news_correlation` 和 6 个新闻辅助函数
5. [ ] **验证旧路径已不可用**：
   ```bash
   # 应返回 ImportError
   python -c "from src.python.llm.generators import enhance_news_correlation" 2>&1 | grep -q ImportError
   ```
6. [ ] 为 `test_generators_news.py` 编写测试（深度覆盖）：
   - `_select_top_news`: 空列表、全部无关键词、正常排序
   - `_apply_llm_news_correlation`: 正常 JSON、含 markdown 代码块、idx 部分缺失、idx 超出范围、非数组响应、JSONDecodeError
   - `_map_llm_results`: 满映射、部分映射、边界索引
   - `_merge_llm_analysis`: 全部富化、部分富化、无富化、空 news_data
   - `_finalize_news_token_usage`: 有用量/无用量/all_cached
   - `enhance_news_correlation`: 空 news_data、全部缓存命中、全部未缓存
7. [ ] 为 `test_generators_news_edge.py` 编写边缘测试：
   - JSON 解析返回数组含无效字段
   - `_build_news_hooks` 中 llm_config 参数为 None
   - 全部新闻被 LLM 判定为"无关"的情况
   - LLM 返回内容为空（安抚重试失败）

**验证：**
- [ ] `[测] pytest src/test/unit/llm/test_generators_news*.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_generators.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -k "news" -v --tb=short`
- [ ] `[导·反证] python -c "from src.python.llm.generators import _apply_llm_news_correlation" 2>&1 | grep -q ImportError`
- [ ] `[导] from src.python.llm.generators_news import enhance_news_correlation`
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] generators.py 不再包含任何新闻代码，也不再 re-export
- [ ] 旧 import 路径返回 ImportError（反证验证通过）
- [ ] generators_news.py 有独立测试 >= 12 条用例
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter06-news-consumers-migrated`

**风险 R2：** ⚠️ 中（多个测试文件需逐一更新 import，用 grep 定位所有匹配行）。

---

### 迭代 7/14：创建 generators_orchestrator.py（precheck 函数）

**目标：** 创建 generators_orchestrator.py，迁入 3 个预处理函数。

**任务清单：**

1. [ ] 创建 `src/python/llm/generators_orchestrator.py`
2. [ ] 从 generators.py **复制**以下内容：
   - `_compute_module_cache_info`
   - `_precheck_one_cache`
   - `_precheck_all_modules`
3. [ ] 确保 generators_orchestrator.py 包含这些函数所需的全部 import
4. [ ] 在 generators_orchestrator.py 编写 `__all__`（包含以上 3 个符号）
5. [ ] 在 generators.py 添加 re-export：
   ```python
   from src.python.llm.generators_orchestrator import (  # noqa: F401
       _compute_module_cache_info, _precheck_one_cache, _precheck_all_modules,
   )
   ```

**验证：**
- [ ] `[导] from src.python.llm.generators_orchestrator import _precheck_one_cache`
- [ ] `[导] from src.python.llm.generators import _precheck_one_cache`（通过 re-export）
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[测] pytest src/test/unit/llm/test_generators.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -k "precheck" -v --tb=short`

**验收标准：**
- [ ] generators_orchestrator.py 包含 3 个预处理函数
- [ ] generators.py re-export 正常
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter07-orch-precheck`

---

### 迭代 8/14：迁入 dispatch_llm_workers + generate_all_llm

**目标：** 将 `_dispatch_llm_workers` 和 `generate_all_llm`（含 `_LLM_CLIENT_SETTINGS`）迁入 orchestrator。

**任务清单：**

1. [ ] 从 generators.py **复制**到 generators_orchestrator.py：
   - `_LLM_CLIENT_SETTINGS`（dict 常量）
   - `_dispatch_llm_workers`（包括闭包 `_make_runner`、`_MODULE_FNS`）
   - `generate_all_llm`
2. [ ] 确保 generators_orchestrator.py 可导入 generators.py 中的 4 个单体函数：
   ```python
   from src.python.llm.generators import (
       generate_global_macro, generate_expert_review,
       generate_health_check, generate_penetration_deep_analysis,
   )
   ```
   ⚠️ 单向依赖：orchestrator → generators（不可反向）。
3. [ ] 在 generators.py 添加 re-export：
   ```python
   from src.python.llm.generators_orchestrator import (  # noqa: F401
       _dispatch_llm_workers, generate_all_llm,
   )
   ```
4. [ ] 更新 generators.py 的 `__all__` 保留 `_dispatch_llm_workers`, `generate_all_llm`

**验证：**
- [ ] `[导] from src.python.llm.generators_orchestrator import generate_all_llm`
- [ ] `[导] from src.python.llm.generators import generate_all_llm`（通过 re-export）
- [ ] `[导] from src.python.llm import generate_all_llm`（通过 __init__ → generators → re-export）
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[测] pytest src/test/unit/llm/test_llm.py -k "generate_all" -v --tb=short`
- [ ] `[测] pytest src/test/scenario/llm/test_llm_scenarios.py -k "generate_all" -v --tb=short`
- [ ] `[全] python scripts/test_runner.py --mode regression`
- [ ] `[导·循环检查] python -c "import sys; del sys.modules['src.python.llm']; from src.python.llm.generators import generate_global_macro; from src.python.llm.generators_orchestrator import generate_all_llm; print('[OK] 独立导入无环')"`

**验收标准：**
- [ ] generators_orchestrator.py 完整包含全部 5 个符号
- [ ] 单向依赖成立：orchestrator → generators（不可反向）
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter08-orch-dispatch`

**风险 R1：** ⚠️ ⚠️ 中高（必须确保 orchestrator import generators 但 generators 不反向 import orchestrator。`generate_all_llm` 的 `__init__.py` → generators → re-export → orchestrator 链在 Iteration 9 才切断）。

---

### 迭代 9/14：迁移 orchestrator 消费者 + 测试编写

**目标：** 切断 `__init__.py`→generators→orchestrator 中间跳转，直链 `__init__`→orchestrator。

**任务清单：**

1. [ ] 更新 `__init__.py`：
   ```python
   # 更新前: from src.python.llm.generators import generate_all_llm
   # 更新后:
   from src.python.llm.generators_orchestrator import generate_all_llm  # noqa: F401
   ```
2. [ ] 更新 `__init__.py` 中 generators 模块的 import 保持仅新闻相关：
   ```python
   # generators 不再提供 generate_all_llm
   # 如果 generators 还有被 __init__ 直接使用的公开符号，保留
   # 但 generate_all_llm 已迁移到 orchestrator
   ```
3. [ ] 更新测试文件 import：
   - `test_llm_scenarios.py`（L1108, L1184）：指向 orchestrator
   - `test_generators.py`（L138-244）：按函数归属分到 orchestrator 或 generators
4. [ ] 移除 generators.py 中 orchestrator 的 re-export
5. [ ] 从 generators.py 的 `__all__` 中移除属于 orchestrator 的条目：
   - `_LLM_CLIENT_SETTINGS`
   - `_compute_module_cache_info`
   - `_precheck_one_cache`
   - `_precheck_all_modules`
   - `_dispatch_llm_workers`
   - `generate_all_llm`
6. [ ] **反证验证**旧路径不可用：
   ```bash
   python -c "from src.python.llm.generators import generate_all_llm" 2>&1 | grep -q ImportError && echo "[OK] 已切断"
   ```
7. [ ] 为 `test_generators_orch.py` 编写测试：
   - `_compute_module_cache_info`: 4 个模块指纹/缓存键/TTL/thinking 键正确
   - `_precheck_one_cache`: cache 命中→(content,True)/未命中→(None,False)/disabled 分支
   - `_precheck_all_modules`: 混合 enabled/disabled 状态
   - `_dispatch_llm_workers`: 全部需生成/全部缓存/none 需要/部分异常
   - `generate_all_llm`: llm_config=None→全 None/全缓存命中→全 cached/混合模式
8. [ ] 为 `test_generators_orch_edge.py` 编写边缘测试：
   - 线程异常传播（`as_completed` 后 `future.result()` 抛出）
   - 全部模块已禁用
   - `llm_max_concurrency=1`（单线程串行）
   - `_make_runner` 中的 `import h2` 降级路径
   - `_MODULE_FNS` 全部 4 个模块函数被调用

**验证：**
- [ ] `[测] pytest src/test/unit/llm/test_generators_orch*.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_generators.py -v --tb=short`
- [ ] `[测] pytest src/test/scenario/llm/test_llm_scenarios.py -v --tb=short`
- [ ] `[导·反证] python -c "from src.python.llm.generators import generate_all_llm" 2>&1 | grep ImportError`
- [ ] `[导] from src.python.llm.generators_orchestrator import generate_all_llm`
- [ ] `[导] from src.python.llm import generate_all_llm`（通过 __init__ 直链）
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] generators.py 不再 re-export 任何 orchestrator 符号
- [ ] `__init__.py` 的 generate_all_llm 来源为 generators_orchestrator（直接）
- [ ] 旧 import 路径返回 ImportError（反证通过）
- [ ] generators_orch.py 有独立测试 >= 12 条用例
- [ ] 回退点：**git commit** `r198-iter09-orch-consumers`

**风险 R2：** ⚠️ 中（`__init__.py` 和测试文件 import 较多，但 grep 可精确定位）。

---

### 迭代 10/14：清理 generators.py — 最终瘦身

**目标：** 确认 generators.py 仅包含 4 个单体生成函数、必要导入和 `__all__`。

**任务清单：**

1. [ ] 验证 generators.py 的当前内容：
   - 是否还有新闻代码残留？→ 清理
   - 是否还有编排代码残留？→ 清理
   - 是否还有仅为 orchestrator 服务的 import？→ 清理
2. [ ] 从 generators.py 中移除不再需要的 import：
   - `concurrent.futures.Future, ThreadPoolExecutor, as_completed`（仅 orchestrator 需要）
   - `httpx`（检查是否仍需类型标注）
   - 检查 `_MN = get_llm_module_name` 是否需要保留（是，多函数使用）
   - 检查 `_label_map` 相关引用
3. [ ] 确认 generators.py 的 import 列表最小化：
   ```python
   from src.python.llm.api_base import (
       _CACHE_LINE_HTML, _LLM_TIMEOUT, _cache_line_model_tpl, _extract_model_from_cached,
       _log_token_usage,
   )
   from src.python.llm.fingerprint import (_build_llm_fingerprint, _compute_fingerprint, _get_cache_ttl_llm)
   from src.python.llm.prompts import (
       _CACHE_PREFIX_LLM, _LLM_MODULE_FAILURE,
       _SYSTEM_EXPERT_REVIEW, _SYSTEM_GLOBAL_MACRO, _SYSTEM_HEALTH_CHECK, _SYSTEM_PENETRATION_DEEP,
       FAIL_REASON_DISABLED,
       _build_expert_review_prompt, ..., _build_penetration_deep_prompt,
   )
   from src.python.llm.session import _record_per_module
   from src.python.llm.skeleton import (_generate_llm_content, _generate_llm_module, _is_llm_module_enabled)
   from src.python.registry import get_llm_module_name
   ```
4. [ ] 测量最终行数：`wc -l src/python/llm/generators.py`
5. [ ] 运行 linter 确认无 F401 等误报：
   ```bash
   ruff check src/python/llm/generators.py
   ```
6. [ ] 确保 generators.py 的 `__all__` 仅含下列符号：
   ```python
   __all__ = [
       "_is_llm_module_enabled", "_generate_llm_content",
       "generate_global_macro", "generate_expert_review",
       "generate_health_check", "generate_penetration_deep_analysis",
   ]
   ```


> **注**：generators.py 的 `__all__` 包含 `_is_llm_module_enabled` 和 `_generate_llm_content` 两个来自 skeleton.py 的 re-export 符号。
> 这意味着 generators.py 不仅是 4 个单体函数的容器，还充当 skeleton 符号的转发出口。
> 拆分后 generators.py 的外部消费者如果使用这两个符号，仍可从 generators 导入。
> 这是当前 `__init__.py` 依赖 generators.py 而非直连 skeleton.py 的副作用，< 300 行限制下可接受。

**验证：**
- [ ] `[导] python -c "import src.python.llm.generators; print(hasattr(src.python.llm.generators, 'generate_global_macro'))"`
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[导·反证] python -c "import src.python.llm.generators; print(hasattr(src.python.llm.generators, 'enhance_news_correlation'))"`（应为 False）
- [ ] `[基] wc -l src/python/llm/generators.py`（目标 < 300）
- [ ] `[鲁] ruff check src/python/llm/generators.py`
- [ ] `[测] pytest src/test/unit/llm/test_generators.py -v --tb=short`
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] generators.py < 300 行（目标 ~220 行）
- [ ] 4 个单体生成函数正常工作
- [ ] 所有测试通过
- [ ] ruff 无错误
- [ ] 回退点：**git commit** `r198-iter10-generators-slim`

---

### 迭代 11/14：清理 api.py + skeleton 最终态验证（合并原 Iteration 11+12）

**目标：** 确认 api.py 仅包含 Provider 路由 + Thinking 注入 + 实现，移除所有 re-export；同时确认 skeleton.py 完整迁离 api.py 依赖。

**任务清单：**

1. [ ] 验证 api.py 中已无重试/截断/内容提取等基础设施代码
2. [ ] 确认 `_configure_extended_thinking` 留在 api.py（与 `_call_claude` 同属 Provider 实现层）
3. [ ] 从 api.py 移除 api_base 的全部 re-export
4. [ ] 确认 api.py 的 `__all__` 仅包含 Provider 路由相关：
   ```python
   __all__ = [
       "_call_single_provider", "_call_llm", "_call_claude", "_call_openai",
       "_configure_extended_thinking",
   ]
   ```
5. [ ] 最终确认 skeleton.py 的 import 状态：
   ```python
   from src.python.llm.api_base import (
       _AUTO_INCREASE_FACTOR, _CACHE_LINE_HTML, _LLM_TIMEOUT, _TRUNCATION_MARKER,
       _cache_line_model_tpl, _extract_model_from_cached, _get_last_llm_failure,
   )
   from src.python.llm.api import (
       _call_llm, _clear_last_llm_failure,
   )
   ```
6. [ ] 确认 generators.py 的 import 状态（已从 api_base 导入）
7. [ ] 确认 generators_news.py 的 import 状态（无 api.py 依赖）
8. [ ] 测量最终行数：`wc -l src/python/llm/api.py`（目标 < 300 行）
9. [ ] **反证验证**旧路径不可用：
   ```bash
   python -c "from src.python.llm.api import _extract_content" 2>&1 | grep -q ImportError && echo "[OK] 已切断"
   # 更精确的反证：
   python -c "import src.python.llm.api; assert '_last_llm_failure_reason' not in src.python.llm.api.__dict__; print('[OK] api.py 无 _last_llm_failure_reason')"
   ```
10. [ ] 运行完整依赖检查：
    ```bash
    grep -rn "from src.python.llm.api_base import" --include="*.py" | grep -v test | grep -v __pycache__
    # 预期: api.py, skeleton.py, generators.py, generators_news.py, generators_orchestrator.py
    ```
11. [ ] 补充 `test_api_base.py` 中对 `_last_llm_failure_reason` 的测试
12. [ ] 运行 ruff 检查：
    ```bash
    ruff check src/python/llm/api.py src/python/llm/api_base.py
    ```

**验证：**
- [ ] `[导] from src.python.llm.api import _call_llm, _call_claude`（正常）
- [ ] `[导] from src.python.llm.api_base import _call_llm_with_retry, _last_llm_failure_reason`（正常）
- [ ] `[导·反证] from src.python.llm.api import _extract_content 2>&1 | grep ImportError`
- [ ] `[导] 全模块导入验证通过`（使用 §11 验证脚本）
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[基] wc -l src/python/llm/api.py`（目标 < 300 行）
- [ ] `[鲁] ruff check src/python/llm/api.py src/python/llm/api_base.py`
- [ ] `[测] pytest src/test/unit/llm/test_api.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_api_edge.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/test_api_base.py -v --tb=short`
- [ ] `[测] pytest src/test/unit/llm/ -v --tb=short`
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] api.py < 300 行（目标 ~220 行）
- [ ] api.py 不 re-export api_base 的任何符号
- [ ] skeleton.py 仅从 api.py 导入 `_call_llm` 和 `_clear_last_llm_failure`
- [ ] 5 个 LLM 子模块组合无循环依赖
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter11-api-skeleton-final`

---

### 迭代 12/14：__init__.py 最终化

**目标：** 确认 `__init__.py` 的公共 API 完整、路径最优、无中间跳转。

**任务清单：**

1. [ ] 最终化 `__init__.py`：
   ```python
   from src.python.llm.generators_orchestrator import generate_all_llm  # noqa: F401
   from src.python.llm.generators_news import enhance_news_correlation  # noqa: F401
   from src.python.llm.prompts import (  # noqa: F401
       FAIL_REASON_API_ERROR, FAIL_REASON_CIRCUIT_OPEN, FAIL_REASON_DISABLED,
       FAIL_REASON_NETWORK_ERROR, FAIL_REASON_NOT_CONFIGURED, FAIL_REASON_TIMEOUT,
   )
   from src.python.llm.session import format_session_usage, get_session_usage  # noqa: F401
   ```
2. [ ] 验证外部消费者路径正常：
   ```python
   python -c "
   from src.python.llm import generate_all_llm, enhance_news_correlation
   from src.python.llm import format_session_usage, get_session_usage
   from src.python.llm import FAIL_REASON_API_ERROR, FAIL_REASON_DISABLED
   print('[OK] 全部公共 API 可用')
   "
   ```
3. [ ] grep 外部消费者列表，确认全部使用 `from src.python.llm import` 语法：
   ```bash
   grep -rn "from src.python.llm import" --include="*.py" src/python/report/ src/python/handlers_*.py | grep -v __pycache__
   ```

**验证：**
- [ ] `[导] 公共 API 验证通过`
- [ ] `[时] time python -c "import src.python.llm" 2>&1 | grep real`
- [ ] `[测] pytest src/test/unit/report/ -v --tb=short -k "llm"`（报告模块 LLM 使用）
- [ ] `[全] python scripts/test_runner.py --mode regression`

**验收标准：**
- [ ] `__init__.py` 直接引用 generators_orchestrator 和 generators_news（无 generators.py 中间跳转）
- [ ] 所有报告模块的 `from src.python.llm import xxx` 正常工作
- [ ] 所有测试通过
- [ ] 回退点：**git commit** `r198-iter12-init-final`

---

### 迭代 13/14：全量回归 + 导入基准检查（含原 Iteration 14/16 导入基准）

**目标：** 运行全量测试、修复标记遗漏、验证导入性能、确认门禁通过。

**任务清单：**

1. [ ] 运行全量模式门禁：
   ```bash
   python scripts/test_runner.py --mode all
   ```
2. [ ] 修复测试失败（如有）：
   - import 路径错误 → 修正
   - 标记遗漏 → 检查新文件是否标注 `pytestmark`
   - 其他存量问题
3. [ ] 运行 conftest.py 的标记检查（确保新文件无 PytestWarning）
4. [ ] 检查 generators.py 外部消费者：
   ```bash
   grep -rn "from src.python.llm.generators import" --include="*.py" | grep -v test | grep -v __pycache__
   ```
   预期结果：仅自身 import 和 `__init__.py`（且仅保留单体函数符号）
5. [ ] 检查 api.py 基础设施类外部消费者：
   ```bash
   grep -rn "from src.python.llm.api import _call_llm_with_retry\|from src.python.llm.api import _extract_content\|from src.python.llm.api import _last_llm" --include="*.py" | grep -v test | grep -v __pycache__
   ```
   预期结果：0 条（均已迁至 api_base）
6. [ ] **导入性能基准对比（原 Iteration 14/16 降级）**：
   ```bash
   python -X importtime -c "import src.python.llm.api_base" 2>&1 | tail -5
   python -X importtime -c "import src.python.llm.api" 2>&1 | tail -5
   python -X importtime -c "import src.python.llm.generators_news" 2>&1 | tail -5
   python -X importtime -c "import src.python.llm.generators_orchestrator" 2>&1 | tail -5
   python -X importtime -c "import src.python.llm.generators" 2>&1 | tail -5
   python -X importtime -c "import src.python.llm.skeleton" 2>&1 | tail -5
   python -X importtime -c "import src.python.llm" 2>&1 | tail -5
   ```
7. [ ] 与迭代 1 的基线对比：退化应 < 20%。如有明显退化，分析原因并优化
8. [ ] 最终全量测试验证：
   ```bash
   python scripts/test_runner.py --mode all
   ```
9. [ ] 最终导入验证：
   ```bash
   python -c "import src.python.llm; print('[OK] R-198 拆分完成')"
   ```

**验证：**
- [ ] `[全] python scripts/test_runner.py --mode all`（完整 3 模式：scenario + regression + verify）
- [ ] `[全·端到端] pytest src/test/scenario/ -v --tb=short -k "report_generation or full_pipeline"`（端到端生产链路：handlers_report → __init__ → orchestrator → generators → skeleton → api → api_base）
- [ ] `[全·运行时快照] python -c "import sys, time; t=time.time(); import src.python.llm; print(f'[OK] 全模块导入: {time.time()-t:.3f}s')"`（记录运行时基线）
- [ ] `[基] 导入时间与基线对比在 ±20% 内`
- [ ] `[鲁] ruff check src/python/llm/`
- [ ] `[鲁] ruff check src/test/unit/llm/`（新测试文件规范）

**验收标准：**
- [ ] `--mode all` 全量测试通过
- [ ] 无标记遗漏警告
- [ ] generators.py 和 api.py 无外部消费者仍依赖旧符号
- [ ] 全 LLM 包导入时间未显著增加（退化 < 20%）
- [ ] ruff 无错误
- [ ] 回退点：**git commit** `r198-iter13-full-regression`

---

### 迭代 14/14：文档更新 + R-198 关闭

**目标：** 更新项目管理文档、技术文档、目录结构、review-findings。该步骤不修改代码，仅更新文档。

**任务清单：**

1. [ ] 更新 `docs-stm/manuals/datasource-and-folders.md`：
   - 在 `src/python/llm/` 目录树下新增：
     ```
     ├── api_base.py                 — LLM API 共享基础设施（常量/重试/截断/内容提取/失败追踪）
     ├── generators_news.py          — LLM 新闻关联分析
     ├── generators_orchestrator.py  — LLM 批量编排（generate_all_llm）
     ```
   - 更新 api.py 描述为"Provider 路由 + Thinking 注入 + 实现"
   - 更新 generators.py 描述为"4 个单体生成函数（global_macro / expert_review / health_check / penetration_deep）"
   - **验证**：`grep -c "api_base.py\|generators_news.py\|generators_orchestrator.py" docs-stm/manuals/datasource-and-folders.md` ≥ 3
2. [ ] 更新 `docs-stm/managements/changelog.md`：
   - 标题：R-198 LLM 模块两巨头横向拆分
   - 方案：generators.py → 3 文件（+ generators_news.py / generators_orchestrator.py）
   - 方案：api.py → 2 文件（+ api_base.py）
   - 行数变化：generators.py 750→~220, api.py 702→~220
   - 新增测试文件：6 个
   - 新增设计约束：门槛行数（见 §7.2 文件大小门禁）
   - **已知遗留项**：TD-5（C5 违规扩散至 2 文件），标记为待跟随 http_client.py 统一化修复
   - **复盘记录**：10 轮自复盘优化（16→14 轮迭代、导入路径全集、约束表修正、FMEA、度量总表）
3. [ ] 更新 `docs-stm/managements/review-findings.md`：
   - 将 R-198 从 "🟡 中优先级 → 待修复" 移至 "✅ 近期已修复"
   - 摘要行：`R-198 LLM 两巨头拆分: generators.py 750→~220行 + news/orchestrator; api.py 702→~220行 + base; 复盘: 16→14轮`
   - **验证**：`grep "R-198" docs-stm/managements/review-findings.md | grep "✅"` 返回非空
4. [ ] 更新 `docs-stm/managements/technical.md`：
   - 「LLM 客户端技术要点」子模块表格新增 3 行：
     - `api_base.py` — 共享基础设施
     - `generators_news.py` — 新闻关联分析
     - `generators_orchestrator.py` — 批量编排
   - 模块间依赖关系图 LLM 部分刷新
   - 在 `## 设计约束` 部分增加 C9 副条款引用文件行数门禁
   - 在 TD 表中新增 TD-5 描述 C5 违规扩散（llm/ → 2 文件）
   - **验证**：`grep -c "api_base\|generators_news\|generators_orchestrator" docs-stm/managements/technical.md` ≥ 3
5. [ ] 更新 `docs-stm/managements/test-coverage.md`：
   - 添加 6 个新测试文件及其覆盖率数据
   - 更新 LLM 模块整体覆盖率
6. [ ] 更新 `docs-stm/managements/plan.md`（标记 R-198 完成）
7. [ ] 更新 `CLAUDE.md` — 同步「技术要点」节中 llm/ 模块列表、行数阈值、新增测试文件路径
7. [ ] 最终全量测试验证：
   ```bash
   python scripts/test_runner.py --mode all
   ```
8. [ ] 最终导入验证 + 检查无遗留的 api.py 基础设施符号：
   ```bash
   python -c "import src.python.llm; print('[OK] R-198 拆分完成')"
   # 确认无基础设施符号残留 api.py
   python -c "import src.python.llm.api; assert not hasattr(src.python.llm.api, '_last_llm_failure_reason'); assert not hasattr(src.python.llm.api, '_extract_content'); assert not hasattr(src.python.llm.api, '_call_llm_with_retry'); print('[OK] api.py 无基础设施残留')"
   # 确认 generators.py 无新闻/编排残留
   python -c "import src.python.llm.generators; assert not hasattr(src.python.llm.generators, 'enhance_news_correlation'); assert not hasattr(src.python.llm.generators, 'generate_all_llm'); print('[OK] generators.py 无新闻/编排残留')"
   ```

**验收标准：**
- [ ] datasource-and-folders.md 已同步新文件结构
- [ ] changelog.md 已记录 R-198 完成（含遗留 TD-5 备注）
- [ ] review-findings.md 中 R-198 已移入"近期已修复"
- [ ] technical.md 已更新模块描述和依赖图 + TD-5 记录
- [ ] test-coverage.md 已更新
- [ ] 全量测试通过
- [ ] 回退点：**git commit** `r198-iter14-docs-done`（最终回退点）

---

## 11. 导入/Mock 路径变更全集

> 总变更数：**~43 处**（分散在 ~8 个测试文件），相比 R-197（14 处 mock 变更）增加了 3 倍，手动操作风险更高，**必须使用批量替换命令**。

### 变更全集对照表

| 函数/符号组 | 迁移方向 | 影响文件 | 变更数 |
|:------------|:---------|:--------|:------:|
| `_last_llm_failure_reason`, `_clear_last_llm_failure`, `_get_last_llm_failure` | api.py → api_base.py | 6 测试文件 | 3 |
| `_LLM_TIMEOUT`, `_RETRY_DELAYS`, `_TRUNCATION_MARKER`, `_AUTO_INCREASE_FACTOR`, `_CACHE_LINE_HTML` | api.py → api_base.py | 3 测试文件 | 5 | ⚠ 注：`_CONTENT_FILTER_RECOVERY` 留在 api.py
| `_check_claude_truncation`, `_check_openai_truncation` | api.py → api_base.py | 2 测试文件 | 2 |
| `_extract_content`, `_extract_model_from_cached` | api.py → api_base.py | 3 测试文件 | 2 |
| `_log_token_usage`, `_get_retry_max`, `_sanitize_endpoint` | api.py → api_base.py | 4 测试文件 | 3 |
| `_check_circuit_breaker`, `_process_success_response`, `_attempt_api_call`, `_is_retry_available`, `_call_llm_with_retry` | api.py → api_base.py | 3 测试文件 | 5 |
| `_apply_llm_news_correlation`（所有 ~13 处） | generators.py → generators_news.py | test_llm.py, test_generators.py | 13 |
| `enhance_news_correlation`, `_select_top_news`, `_build_news_hooks`, `_map_llm_results`, `_merge_llm_analysis`, `_finalize_news_token_usage` | generators.py → generators_news.py | test_llm.py, test_generators.py | 6 |
| `_compute_module_cache_info`, `_precheck_one_cache`, `_precheck_all_modules` | generators.py → generators_orchestrator.py | test_generators.py, test_llm.py | 3 |
| `_dispatch_llm_workers`, `generate_all_llm` | generators.py → generators_orchestrator.py | test_llm_scenarios.py, test_generators.py | 2 |
| **合计** | **8 个来源文件 → 5 个目标文件** | **~8 个测试文件** | **~43** |

### 批量替换指南

各迭代步执行时，使用以下命令批量替换：

```bash
# === Iteration 4（测试 import 迁移：api.py → api_base.py）===
# 在 test_llm.py 中替换基础设施符号
sed -i 's/from src\.python\.llm\.api import \((.*_extract_content.*\|.*_last_llm_failure.*\|.*_check.*truncation.*\|.*_call_llm_with_retry.*\|.*_attempt_api_call.*\|.*_process_success.*\|.*_log_token_usage.*\|.*_sanitize_endpoint.*\|.*_get_retry_max.*\|.*_CONTENT_FILTER.*\|.*_CACHE_LINE_HTML.*\|.*_AUTO_INCREASE.*\|.*_TRUNCATION_MARKER.*\|.*_LLM_TIMEOUT.*\|.*_RETRY_DELAYS.*\|.*_is_retry.*\|.*_extract_model.*)\)/from src.python.llm.api_base import \1/g' test_llm.py

# 在 test_log_sanitize.py 中替换
sed -i 's/from src\.python\.llm\.api import/from src.python.llm.api_base import/g' test_log_sanitize.py

# 在 test_security_edge.py 中替换
sed -i 's/from src\.python\.llm\.api import _sanitize_endpoint/from src.python.llm.api_base import _sanitize_endpoint/g' test_security_edge.py

# 验证替换结果（应返回 0 匹配）
grep -rn "from src.python.llm.api import.*_extract_content\|from src.python.llm.api import.*_call_llm_with_retry\|from src.python.llm.api import.*_last_llm" src/test/ --include="*.py"
# 期望输出：0 匹配 ✅

# === Iteration 6（新闻函数迁移：generators.py → generators_news.py）===
# 在 test_llm.py 中替换新闻相关 import
sed -i 's/from src\.python\.llm\.generators import _apply_llm_news_correlation/from src.python.llm.generators_news import _apply_llm_news_correlation/g' test_llm.py

# 在 test_generators.py 中替换新闻相关 import
sed -i 's/from src\.python\.llm\.generators import _apply_llm_news_correlation/from src.python.llm.generators_news import _apply_llm_news_correlation/g' test_generators.py

# 验证：grep 应返回 0 条 generators 中引用 _apply_llm_news_correlation
grep -n "generators.*_apply_llm_news_correlation" src/test/ --include="*.py"
# 期望输出：0 匹配 ✅

# === Iteration 9（编排函数迁移：generators.py → generators_orchestrator.py）===
# 在 test_llm_scenarios.py 中替换
sed -i 's/from src\.python\.llm\.generators import generate_all_llm/from src.python.llm.generators_orchestrator import generate_all_llm/g' test_llm_scenarios.py

# 在 test_generators.py 中替换编排相关
sed -i 's/from src\.python\.llm\.generators import _precheck_one_cache/from src.python.llm.generators_orchestrator import _precheck_one_cache/g' test_generators.py
sed -i 's/from src\.python\.llm\.generators import _compute_module_cache_info/from src.python.llm.generators_orchestrator import _compute_module_cache_info/g' test_generators.py
sed -i 's/from src\.python\.llm\.generators import _LLM_CLIENT_SETTINGS/from src.python.llm.generators_orchestrator import _LLM_CLIENT_SETTINGS/g' test_generators.py

# 验证：grep 应返回 0 条 generators 中引用 orchestration 符号
grep -n "generators.*generate_all_llm\|generators.*_precheck_\|generators.*_dispatch_\|generators.*_LLM_CLIENT_SETTINGS\|generators.*_compute_module_cache" src/test/ --include="*.py"
# 期望输出：0 匹配 ✅
```

### 11.3 Mock 路径变更全集（⚠️ 前 10 轮复盘未覆盖 — 关键盲区）

> **核心问题**：Python `@patch`/`mock.patch` 按**模块命名空间**替换符号，而 re-export 不转发命名空间修改。
> 当函数从 `a.py` 迁到 `b.py`，但测试仍 `@patch("a._fn")` 时，被测试函数（现在在 `b.py` 中定义）
> 从 `b` 的命名空间查找符号，`a` 上的 patch 无效。**mock 路径必须在代码迁移的同一步（Phase 1）更新**，
> 不能等到 Phase 2 消费者迁移。

| Mock 目标 | 旧路径 | 新路径 | 影响文件 | 数量 | 断裂迭代 |
|:----------|:-------|:-------|:--------|:----:|:--------:|
| `_cb_is_open` | `api._cb_is_open` | `api_base._cb_is_open` | test_api.py | 5 | ❗**I-02** |
| `_cb_record_success` | `api._cb_record_success` | `api_base._cb_record_success` | test_api.py | 5 | ❗**I-02** |
| `_cb_record_failure` | `api._cb_record_failure` | `api_base._cb_record_failure` | test_api.py | 4 | ❗**I-02** |
| `_log_token_usage` | `api._log_token_usage` | `api_base._log_token_usage` | test_api.py | 2 | ❗**I-02** |
| `_track_session_usage` | `api._track_session_usage` | `api_base._track_session_usage` | test_api.py | 2 | ❗**I-02** |
| `ThreadPoolExecutor` | `generators.ThreadPoolExecutor` | `generators_orchestrator.ThreadPoolExecutor` | test_llm.py, test_llm_scenarios.py | 4 | I-07 |
| `httpx.Client` | `generators.httpx.Client` | `generators_orchestrator.httpx.Client` | test_llm.py, test_llm_scenarios.py | 4 | I-07 |
| `_attempt_api_call` | `api._attempt_api_call` | `api_base._attempt_api_call` | test_log_sanitize.py | 1 | ❗**I-02** |
| **合计** | — | — | 4 个文件 | **27** | — |

**不受影响的 Mock 路径（函数仍留在原模块，namespace 绑定不变）：**

| Mock 目标 | 所在模块 | 说明 |
|:----------|:---------|:-----|
| `generators.generate_global_macro` / `_expert_review` / `_health_check` / `_penetration_deep` | `generators.py` | 4 个单体函数保留 |
| `generators._is_llm_module_enabled` | `generators.py` | 从 skeleton.py 导入的绑定保留 |
| `generators.cache_get` | `generators.py` | 直接使用不变 |
| `generators.get_llm_config` | `generators.py` | 直接使用不变 |
| `api._call_llm` | `api.py` | 保留 |
| `api._call_claude` / `api._call_openai` | `api.py` | 保留 |
| `api._call_single_provider` | `api.py` | 保留 |
| `api._call_llm_with_retry` | `api.py` / `api_base.py` | api.py 从 api_base 导入后 **api._call_llm_with_retry** 仍存在（api.py 内部需要） |

#### Mock 路径批量替换命令

```bash
# === I-02 强制同步更新（与 api_base.py 创建同一步，不可延迟！） ===
# test_api.py: _cb_is_open
sed -i 's/from src\.python\.circuit_breaker import _cb_is_open//' test_api.py  # 不移除 import
# 替换 mock 目标路径
sed -i 's/patch("src\.python\.llm\.api\._cb_is_open"/patch("src.python.llm.api_base._cb_is_open"/g' test_api.py
sed -i 's/patch("src\.python\.llm\.api\._cb_record_success"/patch("src.python.llm.api_base._cb_record_success"/g' test_api.py
sed -i 's/patch("src\.python\.llm\.api\._cb_record_failure"/patch("src.python.llm.api_base._cb_record_failure"/g' test_api.py
sed -i 's/patch("src\.python\.llm\.api\._log_token_usage"/patch("src.python.llm.api_base._log_token_usage"/g' test_api.py
sed -i 's/patch("src\.python\.llm\.api\._track_session_usage"/patch("src.python.llm.api_base._track_session_usage"/g' test_api.py

# test_log_sanitize.py: _attempt_api_call
sed -i 's/patch("src\.python\.llm\.api\._attempt_api_call"/patch("src.python.llm.api_base._attempt_api_call"/g' test_log_sanitize.py

# === I-07 同步更新（创建 orchestrator 时） ===
# test_llm.py: ThreadPoolExecutor + httpx.Client
sed -i 's/patch("src\.python\.llm\.generators\.ThreadPoolExecutor"/patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor"/g' test_llm.py
sed -i 's/patch("src\.python\.llm\.generators\.httpx\.Client"/patch("src.python.llm.generators_orchestrator.httpx.Client"/g' test_llm.py

# test_llm_scenarios.py: ThreadPoolExecutor + httpx.Client
sed -i 's/patch("src\.python\.llm\.generators\.ThreadPoolExecutor"/patch("src.python.llm.generators_orchestrator.ThreadPoolExecutor"/g' test_llm_scenarios.py
sed -i 's/patch("src\.python\.llm\.generators\.httpx\.Client"/patch("src.python.llm.generators_orchestrator.httpx.Client"/g' test_llm_scenarios.py

# 验证：应返回 0 匹配
grep -rn 'patch("src\.python\.llm\.api\._cb_\|patch("src\.python\.llm\.api\._log_token_\|patch("src\.python\.llm\.api\._track_\|patch("src\.python\.llm\.api\._attempt_api' src/test/ --include="*.py"
grep -rn 'patch("src\.python\.llm\.generators\.ThreadPoolExecutor\|patch("src\.python\.llm\.generators\.httpx' src/test/ --include="*.py"
# 期望：0 匹配 ✅
```

#### 迭代计划中 Mock 路径需要同步更新的位置

| 迭代 | 代码变更 | 需同步的 Mock 路径 | 验证 |
|:----:|:---------|:-------------------|:-----|
| I-02 | 创建 api_base.py | `api._cb_*` → `api_base._cb_*`, `api._log_token_usage` → `api_base._log_token_usage` | `pytest test_api.py` 全部通过 |
| I-07 | 创建 generators_orch.py | `generators.ThreadPoolExecutor` → `generators_orch.ThreadPoolExecutor` | `pytest test_llm.py -k "generate_all"` 通过 |
| I-08 | 迁入 dispatch | `generators.httpx.Client` → `generators_orch.httpx.Client` | `pytest test_llm_scenarios.py -k "generate_all"` 通过 |

---

### 验证清单（每个迁移迭代步后执行）

```bash
# Phase 1（加法后）：验证旧路径仍然可用
python -c "from src.python.llm.generators import generate_all_llm; print('[OK] 旧路径仍可用')"

# Phase 2（迁移后）：验证新路径可用 + 旧路径仍可用
python -c "from src.python.llm.generators_orchestrator import generate_all_llm; print('[OK] 新路径')"
python -c "from src.python.llm.generators import generate_all_llm; print('[OK] 旧路径仍可用')"

# Phase 3（减法后）：反证验证旧路径已切断
python -c "from src.python.llm.generators import generate_all_llm" 2>&1 | grep -q ImportError && echo "[OK] 旧路径已切断 ✅"
python -c "from src.python.llm.generators_orchestrator import generate_all_llm; print('[OK] 仅新路径可用 ✅')"

# 完整导入验证
python -c "
import src.python.llm.api_base;
import src.python.llm.api;
import src.python.llm.generators_news;
import src.python.llm.generators_orchestrator;
import src.python.llm.generators;
import src.python.llm.skeleton;
import src.python.llm;
from src.python.llm import generate_all_llm, enhance_news_correlation;
print('[OK] 全模块导入验证通过')
"
```

---

## 12. FMEA 汇总

| 迭代 | 失败场景 | 根因 | 检测 | 严重 | 概率 | 恢复 |
|:----:|:---------|:-----|:-----|:----:|:----:|:-----|
| 2 | `api_base.py` 反向 import `api.py` 造成循环导入 | `_last_llm_failure_reason` 留在 api.py 未迁出 | `python -c "import src.python.llm"` 失败 | **高** | **低** | 设计已迁出 → 低概率 |
| 3 | skeleton.py 遗漏从 `api_base` 导入的符号 | import 更新时遗漏 `__all__` 中的某个基础设施符号 | `test_skeleton.py` 失败 | **高** | **低** | 补漏符号 |
| 4 | `test_api.py` 从 api.py 导入的旧符号未全部迁移 | 手动更新 import 遗漏 | regression 失败：`AttributeError` | **中** | **中** | grep 验证 + 逐步修复 |
| 5 | `generators_news.py` 缺少 `skeleton.py` 的 `_generate_llm_module` 依赖 | 复制函数时 import 不完整 | regression 失败：`NameError` | **中** | **低** | 补全 import |
| 6 | **测试文件~16 处 `_apply_llm_news_correlation` import 遗漏 1 处** | 手动更新遗漏 | regression 失败 | **高** | **中** | 使用 §11.2 sed 批量替换 |
| 7 | `generators_orchestrator.py` 首次导入时报错 | 未注册到 `__init__.py` 或自身 import 不完整 | `python -c "import src.python.llm"` 失败 | **高** | **低** | 补全 import + 注册 |
| 8 | **`generators.py` ↔ `generators_orchestrator.py` 双向 re-export 环** | 过渡期 generators.py re-export orchestrator，orchestrator import generators | 循环导入 | **高** | **低** | 单向约束确保不反向 import |
| 9 | **~12 处编排函数 import 遗漏** | 手动更新遗漏 | regression 失败 | **中** | **中** | 使用 §11.2 sed 批量替换 |
| 10 | generators.py 清理后残留未使用的 import 被 ruff 标记 F401 | 删代码未同步删 import | ruff 检查失败 | **低** | **低** | 删除未使用 import |
| 11 | `api.py` 移除 re-export 后 `test_log_sanitize.py` 等非 llm 测试断裂 | 遗忘更新非 llm 测试文件的 import | regression 失败 | **中** | **中** | grep 全项目修复 |
| 11 | skeleton.py 的 import 路径遗漏 `_call_llm` 或 `_clear_last_llm_failure` | 从 api.py 导入的符号被误移到 api_base | `test_skeleton.py` 失败 | **中** | **低** | 修正 skeleton.py import |
| 12 | `__init__.py` 最终化后 `from src.python.llm import generate_all_llm` 断裂 | `__init__.py` 从 generators 改引 orchestrator 路径错误 | 外部消费者报 ImportError | **高** | **低** | 修正 `__init__.py` 路径 |
| 13 | 导入性能退化超过 20% | 文件数 9→12 增加 33% 导致冷启动变慢 | 导入基准检查 | **低** | **低** | 延迟导入 heavy 模块 |
| 13 | 全量测试通过但 review-findings.md 标记遗漏 | 文档更新时遗忘 | 人工检查 | **低** | **低** | 补充更新 |
| 14 | changelog.md 中 C5 违规扩散 TD 遗漏记录 | 文档更新时遗忘 | 人工检查 | **低** | **低** | 补充更新 |
| **新模块** | **新增 generators_xxx 时遗漏 registry/skeleton/__init__ 注册** | 文档未提供注册模板，开发者遗漏注册步骤 | 新增模块首次调用失败（KeyError / ModuleNotFoundError） | **中** | **中** | 使用 §7.1 注册模板逐一核对 |
| 全期 | **Re-export 双重命名空间 — 可变状态不同步** | Phase 1→2 过渡期 `_LLM_CLIENT_SETTINGS` 等可变 dict 同时存在于新旧模块命名空间；代码写一个、读另一个时值不同 | 随机行为（llm 客户端配置意外不同步） | **高** | **低** | Phase 1 后立即标记过渡期 dict 为 `_FORBIDDEN_WRITE` 或加读-写一致性检查 |
| 全期 | **并行开发冲突** | 拆分期间另一开发者修改 generators.py/api.py 中的函数；git merge 成功但原函数已移至新文件，改的"空气" | 代码变更无声丢失 | **中** | **低** | 拆分期间在特性分支上开发，禁止其他任务同时改动 generators.py/api.py |
| I-08→I-09 | **`__init__.py` 中间态传递 — 错误定位误导** | `__init__.py` → generators(re-export orchestrator) → orchestrator；如 orchestrator 有语法错误，回溯指向 generators.py（非根因） | 调试时间增加 2× | **中** | **低** | 过渡期禁止 generators.py 的 re-export 指向尚未经过独立测试的新模块 |

---

## 13. 回滚策略

### 提交约定

每个迭代 1 个原子 commit，message 前缀 `R-198 I-N:`：

```
R-198 I-01: 基线测量与测试就绪
R-198 I-02: 创建 api_base.py（常量+工具+重试骨架+失败追踪）
R-198 I-03: 更新 skeleton.py + generators.py - 指向 api_base
R-198 I-04: 编写 api_base.py 测试 + 迁移测试 import
R-198 I-05: 创建 generators_news.py（全部7个函数）
R-198 I-06: 迁移 generators_news 消费者 + 移除 re-export
R-198 I-07: 创建 generators_orchestrator.py（precheck 函数）
R-198 I-08: 迁入 dispatch_llm_workers + generate_all_llm
R-198 I-09: 迁移 orchestrator 消费者 + 测试编写
R-198 I-10: 清理 generators.py - 最终瘦身
R-198 I-11: 清理 api.py + skeleton 最终态验证
R-198 I-12: __init__.py 最终化
R-198 I-13: 全量回归 + 导入基准检查
R-198 I-14: 文档更新 + R-198 关闭
```

> ⚠️ **分支上下文警告**：以上 14 个 commit 在特性分支 `refactor/r198-llm-split` 上提交。
> 合并到 `dev` 后，这 14 个 commit 会 squash 为 1 个 merge commit。
> **不要在合并后尝试基于单个 R-198 commit hash 回退**——合并 squash 会丢失原始 commit 哈希。
> 在 `dev` 上回退 R-198 的正确操作：`git revert <merge-commit-hash>`。
> 如需中间态回退，在特性分支上操作：`git revert <r198-specific-commit-hash>`。

### 回滚操作

| 场景 | 操作 | 耗时 |
|:-----|:-----|:----:|
| 某一步 regression 失败 | `git checkout .` 放弃该步所有变更 | < 30s |
| 中间步骤发现上游问题 | `git revert <commit-hash>` — 按序回退 | < 1min |
| 全部拆分完成后发现回归 | `git revert HEAD~14..HEAD` — 批量回退 14 个 commit | < 2min |
| 冲突处理 | `git revert --no-commit HEAD~14..HEAD` 逐确认 | < 3min |

### 注意事项

- 批量回退使用 `git revert HEAD~N..HEAD`（范围语法，非单 commit）
- `git revert` 产生新 commit，适合共享分支
- `git reset --soft HEAD~N` 保留工作区文件，`--hard` 丢弃全部
- 如果某一步的 re-export 阶段出现问题，优先补漏符号而不是整步回退（Phase 2 问题修复成本最低）

---

## 14. 累积度量总表

| 迭代 | generators.py | api.py | 新增文件 | 测试改动 | import 变更 | 门禁 | 累计风险 |
|:----:|:-------------:|:------:|:---------|:--------:|:-----------:|:----:|:--------:|
| I-01 | 750 行（不变） | 702 行（不变） | 6 测试骨架 | +6 文件占位 | 0 | 无 | ★☆☆☆☆ |
| I-02 | 750 行（+re-export） | 702 行（+re-export） | +`api_base.py` ~500 行 | 0 | 0 | regression | ★★☆☆☆ |
| I-03 | 750 行（↑import） | 702 行（不变） | — | 0 | 2 文件（skeleton + generators） | regression | ★★☆☆☆ |
| I-04 | 750 行（不变） | 702 行（不变） | — | +test_api_base.py +test_api_base_edge.py | ~15 处（测试 import 迁移） | regression | ★★★☆☆ |
| I-05 | 750 行（+re-export） | 702 行（不变） | +`generators_news.py` ~270 行 | 0 | 0 | regression | ★★☆☆☆ |
| I-06 | ~488 行（-re-export） | 702 行（不变） | — | +test_generators_news.py +test_generators_news_edge.py | **~16 处**❗ | regression | ★★★★☆ |
| I-07 | ~488 行（+re-export） | 702 行（不变） | +`generators_orch.py` ~280 行 | 0 | 0 | regression | ★★☆☆☆ |
| I-08 | ~488 行（+re-export） | 702 行（不变） | — | 0 | 0 | regression | ★★☆☆☆ |
| I-09 | ~220 行（-re-export） | 702 行（不变） | — | +test_generators_orch.py +test_generators_orch_edge.py | **~12 处**❗ | regression | ★★★★☆ |
| I-10 | **~230 行（瘦身）** | 702 行（不变） | — | 0 | 0 | regression | ★★☆☆☆ |
| I-11 | ~220 行（不变） | **~220 行（瘦身）** | — | — | 少量（反证验证） | regression | ★★★☆☆ |
| I-12 | 不变 | 不变 | — | — | 0 | regression | ★☆☆☆☆ |
| I-13 | 不变 | 不变 | — | — | 0 | **verify** | ★★☆☆☆ |
| I-14 | 不变 | 不变 | — | 文档更新 | 0 | 无 | ★☆☆☆☆ |
| **终态** | **~230 行** | **~220 行** | **+5 新模块文件 + 6 新测试文件** | **+6 新测试文件，~43 处 import 变更** | **~43 处** | — | — |

### import 路径变更计数明细

| 变更批次 | 迭代 | 变更来源 | 变更数量 | 累计 |
|:--------|:----:|:---------|:--------:|:----:|
| 测试 import → api_base | I-04 | api.py → api_base.py | ~15 | 15 |
| 新闻 import → generators_news | I-06 | generators.py → generators_news.py | ~16 | 31 |
| 编排 import → orchestrator | I-09 | generators.py → generators_orch.py | ~12 | 43 |

---

### import 路径变更计数明细

| 变更批次 | 迭代 | 变更来源 | 变更数量 | 累计 |
|:--------|:----:|:---------|:--------:|:----:|
| 测试 import → api_base | I-04 | api.py → api_base.py | ~15 | 15 |
| 新闻 import → generators_news | I-06 | generators.py → generators_news.py | ~16 | 31 |
| 编排 import → orchestrator | I-09 | generators.py → generators_orch.py | ~12 | 43 |

---

## 15. 外部消费者迁移检查表

以下表格列出了所有可能受 import 路径变更影响的外部文件（测试文件除外），供每个迁移迭代步后对照检查。

| # | 文件 | 当前 import | 目标（终态） | 影响迭代 |
|:-:|:-----|:------------|:------------|:--------:|
| 1 | `handlers_report.py` | `from src.python.llm import FAIL_REASON_DISABLED` | 不变（通过 `__init__.py`） | 无 |
| 2 | `handlers_report.py` | `from src.python.llm.prompts import _LLM_MODULE_FAILURE` | 不变 | 无 |
| 3 | `handlers_report.py` | `from src.python.llm import generate_all_llm` | 不变（`__init__.py` 路径会变但 API 不变） | I-09/I-12 |
| 4 | `report/html_renderers.py` | `from src.python.llm import generate_all_llm` | 不变（同上） | I-09 |
| 5 | `report/html_renderers.py` | `from src.python.llm import format_session_usage, get_session_usage` | 不变 | 无 |
| 6 | `report/html_renderers.py` | `from src.python.llm import FAIL_REASON_DISABLED as _` | 不变 | 无 |
| 7 | `report/html_renderers.py` | `from src.python.llm.prompts import _LLM_MODULE_FAILURE` | 不变 | 无 |
| 8 | `report/news_correlation.py` | `from src.python.llm import enhance_news_correlation` | 不变（`__init__.py` 路径会变但 API 不变） | I-05 |
| 9 | `report/llm_content.py` | `from src.python.llm import (...)` | 不变 | 无 |
| 10 | `report/llm_content.py` | `from src.python.llm.prompts import _LLM_MODULE_FAILURE` | 不变 | 无 |
| 11 | `report/excel_generator.py` | `from src.python.llm import (...)` | 不变 | 无 |
| 12 | `report/excel_generator.py` | `from src.python.llm.prompts import _LLM_MODULE_FAILURE` | 不变 | 无 |
| 13 | `report/summary.py` | `from src.python.llm.pricing import _CURRENCY_SYMBOLS, _PRICING_CURRENCY` | 不变 | 无 |
| 14 | `handlers_config.py` | `from src.python.llm.pricing import _reload_pricing` | 不变 | 无 |

> 结论：所有 14 个外部消费者均通过 `__init__.py` 或 `prompts.py`/`pricing.py` 间接访问 LLM 模块，**无需直接修改任何外部消费者代码**。import 变更仅在测试文件和 `__init__.py` 内部。

### 非 LLM 测试文件迁移清单

以下文件在 `llm/` 之外，需要特别关注 import 迁移：

| # | 文件 | 当前 import | 目标 import | 影响迭代 | 替换命令 |
|:-:|:-----|:------------|:------------|:--------:|:---------|
| 1 | `test_log_sanitize.py` | `from src.python.llm.api import _sanitize_endpoint` | `from src.python.llm.api_base import _sanitize_endpoint` | I-04 | 替换 api→api_base |
| 2 | `test_log_sanitize.py` | `from src.python.llm.api import _call_llm` | 保持不变（`_call_llm` 仍在 api.py） | I-11 | 不变 |
| 3 | `test_log_sanitize.py` | `from src.python.llm.api import _call_llm_with_retry as _retry` | `from src.python.llm.api_base import _call_llm_with_retry as _retry` | I-04 | 替换 api→api_base |
| 4 | `test_log_sanitize.py` | `from src.python.llm.api import _call_claude` | 保持不变（仍在 api.py） | 无 | 不变 |
| 5 | `test_security_edge.py` | `from src.python.llm.api import _sanitize_endpoint` | `from src.python.llm.api_base import _sanitize_endpoint` | I-04 | 替换 api→api_base |
| 6 | `test_api_edge.py` | `from src.python.llm.api import _call_llm` | 保持不变（仍在 api.py） | 无 | 不变 |
| 7 | `test_api_edge.py` | `from src.python.llm.api import _attempt_api_call` | `from src.python.llm.api_base import _attempt_api_call` | I-04 | 替换 api→api_base |
| 8 | `test_integration.py` | `from src.python.llm.skeleton import _handle_cache_hit` | 保持不变 | 无 | 不变 |

--

## 附录

### A. 14 轮最终版与初版 14 轮映射

（第 2 轮复盘优化：原 R1 后扩展为 16 轮的方案经 2 轮复盘压缩回 14 轮，策略不同——合并了 2 轮，降级 1 轮，重排了 2 轮。）

| 新版(14轮) | 初版(14轮) | 差异说明 |
|:----------:|:--------:|:---------|
| 1 | 1 | 基线 + 导入时间测量 |
| 2 | 2+3 | **合并** → api_base 一次性迁出（省去 re-export 过渡周期） |
| 3 | 3 | skeleton/generators import 更新 |
| 4 | 4 | 测试编写 |
| 5 | 5+6 | **合并** → generators_news 一次性迁出全部 7 个函数 |
| 6 | 7 | 消费者迁移 + 测试 |
| 7 | 8 | orchestrator precheck 迁出 |
| 8 | 9 | orchestrator dispatch 迁出 |
| 9 | 10 | 消费者迁移 + 测试 |
| 10 | 11 | generators.py 瘦身 |
| 11 | — | **新增 + 合并** → api.py 瘦身 + skeleton 最终态验证（替代"先瘦身再验证"的 2 步） |
| 12 | 13 | `__init__.py` 最终化 |
| 13 | 14+15 | **合并 + 降级** → 全量回归 + 导入基准子检查（导入基准不再独立成轮） |
| 14 | 16 | 文档更新 + R-198 关闭 |

### B. 最终文件预期大小

| 文件 | 原大小 | 目标大小 | 职责 |
|:-----|:------:|:--------:|:-----|
| `api_base.py` | — | ~500 行 | 共享基础设施（常量/重试/截断/内容提取/失败追踪） |
| `api.py` | 702 行 | ~220 行 | Provider 路由 + Extended Thinking + 实现 |
| `generators.py` | 750 行 | ~220 行 | 4 个单体生成函数 |
| `generators_news.py` | — | ~270 行 | 新闻关联分析 |
| `generators_orchestrator.py` | — | ~280 行 | 批量编排 |

### C. 测试覆盖率目标

| 新模块 | 分支覆盖目标 | 行覆盖目标 | 最低测试计数 |
|:-------|:----------:|:---------:|:----------:|
| `api_base.py` | ≥ 75% | ≥ 80% | ≥ 20 条（含边缘） |
| `generators_news.py` | ≥ 70% | ≥ 80% | ≥ 12 条（含边缘） |
| `generators_orchestrator.py` | ≥ 70% | ≥ 80% | ≥ 12 条（含边缘） |
| `api.py`（瘦身后） | ≥ 80% | ≥ 85% | 更新 import |
| `generators.py`（瘦身后） | ≥ 80% | ≥ 85% | 更新 import |

### D. 各迭代文件变更摘要

| 迭代 | gen.py | gen_news | gen_orch | api.py | api_base | __init__ | 测试变更 |
|:----:|:------:|:--------:|:--------:|:------:|:--------:|:--------:|:---------|
| 1 | — | — | — | — | — | — | 6 骨架 |
| 2 | — | — | — | +re-export | 创建(500) | — | — |
| 3 | ↑import | — | — | — | — | — | — |
| 4 | — | — | — | — | — | — | test_api_base |
| 5 | +re-export | 创建(270) | — | — | — | — | — |
| 6 | -re-export | — | — | — | — | — | test_gen_news |
| 7 | +re-export | — | 创建(280) | — | — | — | — |
| 8 | +re-export | — | ↑内容 | — | — | — | — |
| 9 | -re-export | — | — | — | — | ↑来源 | test_gen_orch |
| 10 | 瘦身(220) | — | — | — | — | — | — |
| 11 | — | — | — | -re-export + 瘦身(220) | — | — | skeleton vérif |
| 12 | — | — | — | — | — | 最终化 | — |
| 13 | — | — | — | — | — | — | 全量回归 + 导入基准 |
| 14 | — | — | — | — | — | — | 文档更新 |
