# 多 LLM Provider 链式服务 — 迭代计划

> 文档版本：v1.0
> 状态：待实现
> 关联设计：[llm-multi-provider-design.md](llm-multi-provider-design.md)
> 目标版本：v0.7.0

---

## 1. 概述

为 LLM 服务层增加多 Provider 链式支持，允许同时配置多个 LLM 服务商（Claude / OpenAI / Gemini / DeepSeek），按优先级/权重/成本策略分发请求，实现高可用和成本优化。

### 1.1 核心架构决策

**现有 `call_llm()` 为唯一的 provider chain 入口，策略引擎为新增中间层，不改变调用方接口。**

```
改动前:
  generators → call_llm() → call_single_provider() → httpx

改动后:
  generators → call_llm() → StrategyEngine → ProviderChain → call_single_provider() → httpx
                                    ↓
                              config/_core.py get_llm_config()
                                    ↓
                              llm_providers.json v1 (providers[] + strategy)
                                    |
                        (config.json 移除 llm_key_file 字段)
```

### 1.2 四阶段划分

| 阶段 | 内容 | 进度要求 |
|:-----|:------|:---------|
| **S1：数据模型 + Config**（3 轮） | `llm_providers.json` 格式解析、配置分离、`get_llm_config()` 扩展 | 单测全绿，config.json 兼容 |
| **S2：策略引擎 + Priority**（2 轮） | `strategy.py` 模块、priority 策略实现、chain 集成到 `call_llm()` | 链式回退单测通过 |
| **S3：Weighted + Cost 策略**（2 轮） | weighted 随机分发、cost_first 排序、fallback_only | 三策略单测通过 |
| **S4：每模块路由 + TUI + 文档**（2 轮） | `llm_preferred_providers`、v1→v2 迁移脚本、用户手册更新 | 回归全绿 + 文档完稿 |

---

## 2. 9 轮迭代总览

```
S1 ██░░░░░░░░░░░░░░░   v2 数据模型 + _parse_llm_key_v2 + 向后兼容
S2 ████░░░░░░░░░░░░░   get_llm_config() 扩展 _provider_list + 配置校验
S3 ██████░░░░░░░░░░░   strategy.py 框架 + priority 策略 + call_llm() chain
S4 ████████░░░░░░░░░   Weighted 策略：加权随机排序 + 失败重选
S5 ██████████░░░░░░░   Cost First 策略：按定价排序 + fallback_only
S6 ████████████░░░░░   每模块路由：llm_preferred_providers 解析 + 注入 chain
S7 ██████████████░░░   TUI 配置界面（菜单 P/S 扩展）
S8 ████████████████░   单测覆盖全部 + 集成测试
S9 █████████████████   文档 + regression 最终验证
```

---

## 3. S1~S9 逐轮详情

---

### S1：llm_providers.json 数据模型 + 解析函数

**目标**：定义 `llm_key.json` v2 格式及解析逻辑，v1 格式自动转换。

#### 设计要点

- **新增配置项** `data/config/llm_providers.json`：
  - `config.json` 中移除 `llm_key_file` 字段
  - `_default_config` 中 `llm_key_file` 改为不设置（或默认 None）
  - 读取时优先查找 `llm_providers.json`，不存在时尝试旧 `llm_key.json` 作兜底
- **`config/_core.py`** 新增 `_parse_llm_providers(config: dict) -> list[dict]`
- 检测 `config.get("version")`：
  - `== 1` → 直接返回 `config["providers"]`（做字段补齐）
  - 缺失 → 视为空配置
- 新增 `_PROVIDER_CONFIG_FIELDS = {"name", "provider", "api_key", "model", "endpoint", "priority", "weight", "timeout", "max_retries"}`
- 新增 `_validate_provider_entry(entry, index)` 校验每个 Entry 的必填字段
- 新增 `_PROVIDER_REQUIRED_FIELDS = {"name", "provider", "api_key"}`

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/config/_core.py` | **修改** — 新增 `_parse_llm_providers()`、`_validate_provider_entry()`；`get_llm_config()` 读取 `llm_providers.json` |
| `src/python/config/_config_defaults.py` | **修改** — 移除 `llm_key_file` 默认值 |
| `data/config/llm_providers.json` | **新建** — 用户手动创建 |

#### 测试新增

- `test_config_llm_multi.py::TestParseLlmProviders`
  - `test_v1_format_parsed_correctly` — v1 标准格式解析
  - `test_missing_provider_field` — 缺失必填字段报 WARNING
  
    - `test_config_json_no_llm_key_file` — config.json 中无 llm_key_file 字段

#### 验收标准

- [ ] v1 格式正确解析为 `_provider_list`
- [ ] `config.json` 无 `llm_key_file` 时读取 `llm_providers.json`
- [ ] `"name"` 缺失时自动生成（`provider_0`、`provider_1`）
- [ ] 必填字段缺失记录 WARNING
- [ ] 原有 `provider`/`api_key`/`model`/`endpoint` 键仍存在

---

### S2：get_llm_config() 扩展 + 策略配置

**目标**：`get_llm_config()` 返回 `_provider_list`、`_strategy`、`_preferred_providers`。

#### 设计要点

- 在 `get_llm_config()` 的 merged 阶段插入 provider list 解析
- 从 `llm_providers.json` 读取 `llm_strategy` 和 `llm_preferred_providers`（策略与配置同源）
- 将解析结果注入 merged dict：
  ```python
  merged["_provider_list"] = _parse_llm_key_v2(key_config)
  merged["_strategy"] = base_settings.get("llm_strategy", "priority")
  merged["_preferred_providers"] = base_settings.get("llm_preferred_providers", {})
  ```
- 校验策略值：`llm_strategy` 必须在 `{"priority", "weighted", "cost_first", "fallback_only"}` 中
- 校验 `_preferred_providers` 中的值是否存在于 `_provider_list` 的 name 中

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/config/_core.py` | **修改** — `get_llm_config()` + 校验 |

#### 验收标准

- [ ] v2 配置的 `_provider_list` 可通过 `get_llm_config().get("_provider_list")` 获取
- [ ] `_strategy` 默认值为 `"priority"`（来自 `llm_providers.json` 顶层）
- [ ] `_preferred_providers` 默认值为 `{}`（来自 `llm_providers.json` 顶层）
- [ ] 策略值非法时记 WARNING 并回退到 `"priority"`
- [ ] 偏好值不匹配时记 WARNING 并忽略该偏好

---

### S3：strategy.py + Priority 策略 + call_llm() Chain

**目标**：新增 `strategy.py` 模块，实现 priority 策略，`call_llm()` 集成 provider chain。

#### 设计要点

- **新建** `src/python/llm/strategy.py`，定义：
  ```python
  def resolve_provider_chain(
      provider_list: list[dict],
      strategy: str,
      module_key: str = "",
      preferred: dict[str, str] | None = None,
  ) -> list[dict]:
      """返回按策略排序的 provider 尝试列表。"""
  ```
- **priority 实现**：`sorted(provider_list, key=lambda p: p["priority"])` + 按 `module_key` 移动偏好 provider 到首位
- **`call_llm()` 重构**：
  ```python
  def call_llm(...):
      provider_list = llm_config.get("_provider_list", [])
      strategy = llm_config.get("_strategy", "priority")
      preferred = llm_config.get("_preferred_providers", {})
      module_key = _infer_module_key(config_field)  # "max_tokens_global_macro" → "global_macro"
      chain = resolve_provider_chain(provider_list, strategy, module_key, preferred)
      for entry in chain:
          result, usage = call_single_provider(
              entry["provider"], ..., entry["api_key"], entry["model"], entry["endpoint"],
              timeout=entry.get("timeout", 60), max_retries=entry.get("max_retries", 2),
              ...
          )
          if result is not None:
              return result, usage
      return (None, None)
  ```
- **`call_single_provider()` 扩展**：接受 `timeout` 参数覆写默认值（当前是 `llm_config` 全局值）
- **失败原因追踪扩展到 provider 级别**：`_last_llm_failure_reason` 增加 provider name 前缀

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **新建** — `resolve_provider_chain()` |
| `src/python/llm/api.py` | **修改** — `call_llm()` chain 循环 + `call_single_provider()` timeout 参数 |
| `src/python/llm/api_base.py` | **修改** — 失败原因记录带上 provider name |

#### 验收标准

- [ ] `resolve_provider_chain()` 按 priority 升序返回列表
- [ ] 有 preferred 时该 provider 排到首位
- [ ] preferred 不存在时 WARNING 且不影响排序
- [ ] `call_llm()` 按 chain 依次尝试，成功即返回
- [ ] 所有 provider 失败后返回 `(None, None)`
- [ ] 日志中能区分是哪个 provider 的失败

---

### S4：Weighted 策略

**目标**：实现加权随机分发策略。

#### 设计要点

- `resolve_provider_chain()` 中 `strategy == "weighted"` 时：
  1. 复制 provider_list
  2. 按 weight 比例随机排序（Fisher-Yates 加权变体）
  3. 返回排序后的列表（外层 `call_llm()` 的 for 循环天然实现"失败后换下一个"）
- 权重算法：`random.choices(providers, weights=[p["weight"] for p in providers], k=len(providers))` + 去重保持唯一
- 失败重选：当 chain 中某 provider 失败时，`call_llm()` 循环到下一个——weighted 的核心是"每次调用独立随机"，而非"固定排列"

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **修改** — `resolve_provider_chain()` weighted 分支 |

#### 验收标准

- [ ] 多次调用 `resolve_provider_chain(..., strategy="weighted")` 返回的顺序不同
- [ ] 权重为 0 的 provider 不被选中
- [ ] 所有 weight 为 0 时回退到 priority 模式
- [ ] 失败后按剩余 provider 重选（不是再随机全部）

---

### S5：Cost First + Fallback Only 策略

**目标**：实现成本优先排序和仅回退模式。

#### 设计要点

- **Cost First 实现**：
  1. 从 `pricing.py` 的 `PRICING_MERGED` 获取各模型定价
  2. 对每个 provider 估算 `cost_score = input_price + output_price`（取均值）
  3. 按 `cost_score` 升序排列 chain
  4. 定价表中找不到的模型排在末尾（视为高价）
- **Fallback Only 实现**：
  1. 与 priority 相同，但**首次调用仅取第一个**
  2. 失败后锁住该失败的 provider name，后续调用跳过它
  3. 本策略下 `call_llm()` 需要感知"当前会话中哪些 provider 已降级"

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **修改** — `resolve_provider_chain()` cost_first / fallback_only 分支 |
| `src/python/llm/api.py` | **修改** — fallback_only 会话级降级状态 |

#### 验收标准

- [ ] cost_first 按定价升序排列（最便宜优先）
- [ ] 未知模型排在最后
- [ ] fallback_only 首次只尝试 priority=1 的 provider
- [ ] fallback_only 失败后正常回退到下一个

---

### S6：每模块 Provider 路由

**目标**：在 `llm_settings.json` 中按模块指定偏好 provider。

#### 设计要点

- `_preferred_providers` 已在 S2 中解析
- 策略引擎中"模块键"的推导：
  - `call_llm()` 的 `config_field` 如 `"max_tokens_global_macro"` → 提取后缀 `"global_macro"`
  - `call_llm()` 的 `config_field` 如 `"max_tokens"` → 无模块名，忽略偏好
- 偏好优先级：模块级偏好 > 全局策略 > 默认 priority

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/llm/strategy.py` | **修改** — `_infer_module_key()` + 偏好注入 chain |
| `src/python/llm/api.py` | **修改** — 传递 `config_field` 到 `resolve_provider_chain()` |

#### 验收标准

- [ ] `global_macro` 配置 `gemini-pro` 时，该模块 chain 以 `gemini-pro` 开头
- [ ] 偏好 provider 失败后正常回退
- [ ] 不存在的偏好 provider 记 WARNING 并忽略
- [ ] 无匹配模块偏好的调用使用全局策略

---

### S7：迁移工具 + TUI 配置

**目标**：提供 v1→v2 迁移脚本和 TUI 菜单中的多 provider 配置项。

#### 设计要点

- **TUI 配置扩展**：
  - `handlers_config.py` 新增 `_cmd_config_llm_providers()` 菜单项
  - 在菜单中注册新快捷键（如 `M`）
  - 交互：显示当前 provider 列表，支持添加/编辑/删除/调整优先级

#### 涉及文件

| 文件 | 操作 |
|:-----|:------|
| `src/python/handlers_config.py` | **修改** — 新增 `_cmd_config_llm_providers()` |
| `src/python/tui_menu.py` | **修改** — 注册新菜单项 |
| `src/python/main.py` | **修改** — `_bind_callbacks()` 注册回调 |

#### 验收标准

- [ ] TUI 菜单能显示多 provider 列表
- [ ] 支持添加/编辑/删除 provider

---

### S8：测试覆盖

**目标**：全面覆盖多 provider 场景的单元测试和集成测试。

#### 测试清单

- `test_config_llm_multi.py`（S1+S2 测试巩固）
  - v1 解析、字段校验、策略值校验、偏好校验、配置分离验证
- `test_strategy.py`（S3~S6 策略测试）
  - priority 排序
  - weighted 随机分布
  - cost_first 定价排序
  - fallback_only 行为
  - 模块偏好注入
- `test_api_multi.py`（S3 chain 集成测试）
  - 正常 chain：首 provider 成功
  - 链式回退：首失败、次成功
  - 全部失败
  - 混合失败原因（网络错误 + 格式异常）
  - timeout 覆写参数传递

#### 验收标准

- [ ] 所有策略分支覆盖 >= 80%
- [ ] 边界场景覆盖：空列表、空权重、未知策略值
- [ ] 集成测试覆盖首成功/首失败回退/全部失败

---

### S9：文档 + Regression 最终验证

**目标**：用户手册更新 + 全量回归。

#### 文档清单

- `docs-stm/managements/technical.md` — 追加 C17 架构约束
- `docs-stm/manuals/how-to-config-llm.md` — 多 provider 配置指南（含 `llm_providers.json` 格式说明）
- `docs-stm/manuals/how-to-config.md` — 更新配置项说明（移除 `llm_key_file`）
- `docs-stm/manuals/faq.md` — 常见问题更新
- `docs-stm/managements/changelog.md` — 变更记录

#### 验收标准

- [ ] `python scripts/test_runner.py --mode regression` 全绿
- [ ] `python scripts/test_runner.py --mode verify` 全绿
- [ ] 文档评审通过
