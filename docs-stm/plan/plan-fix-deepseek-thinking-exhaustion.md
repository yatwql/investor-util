# 修复 DeepSeek Extended Thinking 思考耗尽 max_tokens 预算（rf-122）

> **状态**：rf-122 已实现并修复（竞态 + 配置缓解，v0.9.x 已发布，修复记录见 `archived_review-findings.0.9.x.md`）。设计文档保留在 `docs-stm/plan/` 供历史参考，待 release 后随版本段归档。

## Context

用户运行报告生成时，DeepSeek 主链路（`deepseek-main` claude/anthropic-compat，模型 `deepseek-v4-flash`）反复触发：

```
LLM 输出思考部分耗尽 max_tokens 预算，未生成最终文本
Claude API 响应格式异常
provider deepseek-main 失败（api_error），切换下一 provider
模型 gemini-2.0-flash 不支持 Extended Thinking，已自动降级跳过
```

日志中 **expert_review / health_check** 两个模块各失败一次（thinking 开启），全球政经局势（thinking 关闭）成功。

### 根因

- DeepSeek V4 为**强制推理模型**，Anthropic 兼容端点上 `max_tokens` 是 **thinking + 正文的共享预算**（官方文档：thinking 消耗同一输出预算，理论上限 384K，实际 131K+）。
- 当前 `expert_review` / `health_check`：`thinking_enabled=true` + `max_tokens=8192` + `reasoning_effort=medium`。复杂持仓输入下 medium 思考即耗尽 8192 → 响应仅含 thinking block、无正文 → `api_base._extract_content` 走 `stop_reason=="max_tokens"` 分支返回 None → `_process_success_response` 记失败 → 直接切 provider。
- rf-98 只把 max_tokens 从 4096 抬到 8192 + effort 降 medium，对当前更复杂的输入仍不够（8192 是 thinking+正文合算，正文被挤光）。
- 配置内自带矛盾：`thinking_budget_expert_review=16000` / `thinking_budget_health_check=12000`（操作者预期思考可到 16k/12k），但 `max_tokens` 只有 8192，且对 DeepSeek effort 模型 budget 字段被忽略——真正生效的只有 max_tokens。
- 降级链 gemini-2.0-flash 不在 thinking 支持名单（仅 `gemini-2.5-`/`gemini-3.5-`），且实测链路不稳定，模块内容有丢失风险。

### 修复策略（双层）

1. **配置抬升 max_tokens**（保质量：一次调用内完成思考+正文）
2. **代码安全网**（兜底：thinking 仍耗尽时自动关闭 thinking 重试一次，保证有正文）

## 改动清单

### 1. 配置：抬升 thinking 开启模块的 `max_tokens`

- `max_tokens_expert_review`: 8192 → **20000**（= thinking_budget 16000 + 正文余量 ~4k）
- `max_tokens_health_check`: 8192 → **16000**（= thinking_budget 12000 + 正文余量 ~4k）
- 生效文件（两处必须同步）：
  - `data/config/llm_settings.json`（git 跟踪，用户运行实际生效）
  - `src/python/config/_llm_defaults.py`（`_DEFAULT_LLM_SETTINGS`，新装模板）
- 安全性：DeepSeek V4 max output 上限 384K（实际 131K+），20000 无 400 风险；config 无 max_tokens 范围校验（doc 中 "1024~8192" 仅为描述性，非硬约束）。
- 不动的模块：`global_macro`/`penetration_deep`/`news_correlation` 均 `thinking_enabled=false`，无思考耗尽问题，维持现值。

### 2. 代码安全网：thinking 耗尽后自动重试（关闭 thinking）

**`src/python/llm/api_base.py`**
- 新增模块级标志 `_last_thinking_exhausted: bool`（仿既有 `_last_llm_failure_reason` 模式）+ 存取函数 `_get_last_thinking_exhausted()` / `clear_last_thinking_exhausted()`，加入 `__all__`。
- `_extract_content` 开头先 `_last_thinking_exhausted = False` 复位；在 `stop_reason=="max_tokens"` 且无 text 分支置 `True`（其余分支自然为 False）。

**`src/python/llm/_api_claude.py::call_claude`**
- 从 `api_base` 导入 `_get_last_thinking_exhausted` / `clear_last_thinking_exhausted`。
- 把 `call_llm_with_retry(...)` 收进本地 `_do_call()` 闭包（避免重试时重复大段参数）。
- 记录 `thinking_was_enabled = "thinking" in payload`（`configure_extended_thinking` 之后判定）。
- 首次调用返回 `(None, None)` 且 `thinking_was_enabled` 且 `_get_last_thinking_exhausted()` → 记 WARNING → `payload.pop("thinking", None)`、若 `temperature is not None` 则恢复 `payload["temperature"]`、`clear_last_thinking_exhausted()` → 再 `_do_call()` 一次，返回其结果。
- 不满足条件则返回首次结果（行为与现状一致）。

> 设计说明：仅在"成功 HTTP 但空正文且根因=思考耗尽"时重试一次，不掩盖真实 API 错误；`_cb_record_failure` 在重试成功后由 `_cb_record_success` 抵消；provider 链看不到这次失败（在 `call_claude` 内部消化）。

### 3. 回归测试（`src/test/unit/llm/test_llm_api.py`，`TestCallClaudeThinkingDegradation` 类新增）

- `test_thinking_exhausted_retries_without_thinking`：`mock call_llm_with_retry`，`side_effect=[(None, None), ("recovered", {...})]`；patch `_api_claude._get_last_thinking_exhausted` 为 `side_effect=[True, False]`；`temperature=0.3`。断言：调用 2 次；第一次 payload 含 `thinking`、第二次不含；第二次恢复 `temperature=0.3`；返回 `"recovered"`。
- `test_thinking_exhausted_flag_false_no_retry`：flag 恒 False，`side_effect=[(None, None)]` → 仅调用 1 次。
- `test_no_thinking_enabled_no_retry`：`thinking_enabled=false`（payload 无 thinking）→ 即使 flag True 也不重试，调用 1 次。

### 4. 文档同步

- `docs-stm/manuals/how-to-config-llm.md`
  - 示例 JSON：`max_tokens_expert_review` 8192→20000、`max_tokens_health_check` 8192→16000（约 393/407 行）
  - 模块参数表（约 510-511 行）：max_tokens 同步
  - 参数范围表（约 298 行 "1024~8192"）：改为 "1024~20000（模块差异）"
  - DeepSeek V4 调参段（约 577-579 行）：补充"思考耗尽时抬 max_tokens（思考+正文共享预算）"，并说明代码已加"关闭 thinking 自动重试一次"兜底
- `docs-stm/managements/llm-technical.md`：默认 max_tokens 表（约 182-184 行）同步
- `docs-stm/managements/changelog.md`：0.9.5-dev 段补 Fix / Test 条目（根因 + 双层修复）
- `docs-stm/managements/review-findings.md`：新增 `rf-122`（P1 待处理）记录本缺陷，修复验证后移至已修复表

> 无新增文件 → `folders.md` 不需改；不改版本号 → 不需 `check-version-consistency.py`。

## 验证

1. 新增测试 + 既有 ExtendedThinking 测试不回归：
   `.venv/bin/python -m pytest src/test/unit/llm/test_llm_api.py -v --tb=short`
2. 相关 API 层测试：`.venv/bin/python -m pytest src/test/unit/llm/ -v --tb=short`
3. P0 门禁：`.venv/bin/python scripts/test_runner.py --mode dev-verify`
4. 历史痕迹：`.venv/bin/python scripts/check-history-traces.py --ci`
5. 用户实测：重新生成报告，确认 DeepSeek 主链路 expert_review / health_check 不再出现"思考部分耗尽"→ 切 provider；正文正常产出
