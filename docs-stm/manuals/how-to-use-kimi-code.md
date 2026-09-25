# Kimi Code 订阅端点接入范例（随时可启用）

> **本文用途**：把 **Kimi Code 订阅 Key**（`api.kimi.com/coding/`）接入本工具的**可直接照抄的范例**。
> 当前程序使用的是**开放平台按量付费 Key**（`api.moonshot.cn`），与本文的 Key/端点**互不通用**。
> 换 Key 时按本文「启用步骤」改两个文件即可，无需改代码。
>
> ⚠️ **先读风险提示**：Kimi Code 订阅的官方条款明确 **"Don't use Kimi Code for non-interactive automation"**
> （"Kimi Code subscriptions are for personal interactive use only. Using it for non-interactive purposes —
> such as scripted batch execution or data annotation pipelines — goes beyond normal usage."）。
> 本工具的批量报告生成属于**非交互式自动化**，因此：
> - 用 Kimi Code Key 跑本工具**在合规性上是有风险的**，`pacing` 只能降低被风控检出的概率，**不能消除风险**；
> - 违规处置可能是 **403 `You've reached your concurrent request limit`**（风控触发，只能申诉）；
> - **长期稳定跑自动化，建议用开放平台按量付费 Key**（无此条款）；订阅 Key 更适合留给 Claude Code / CLI 等交互式编码场景。

---

## 一、关键差异一览（最容易踩的三个坑）

| 项 | 开放平台（当前在用） | **Kimi Code 订阅** |
|---|---|---|
| Base URL | `https://api.moonshot.cn/anthropic/v1/messages` | **`https://api.kimi.com/coding/v1/messages`** |
| Key 来源 | platform.moonshot.cn 控制台 | **Kimi Code 控制台**（kimi.com/code/console） |
| 模型名 | `kimi-k2.6` / `kimi-k3` | **`kimi-for-coding`**（标准）/ `kimi-for-coding-highspeed`（高速，高等级套餐）/ `k3` |
| 计费 | 按量付费（token 计费） | 会员订阅额度（**不按 token 计费**） |
| 通用性 | 两套 Key **与端点互不通用**——用错会 401 `Invalid Authentication` | 同左 |

> **模型名务必改**：若保留 `kimi-k2.6` 去请求 Code 端点，会得到 `Your model id does not exist, recognized as other:` 类 401。

## 二、启用步骤（改两个文件，不改代码）

### 步骤 1｜`data/config/llm_key.json`（本地密钥文件，**不入库**）

追加一个凭据块（**保留原有的按量付费块**，便于随时切回）：

```jsonc
{
  // …原有 kimi-main / deepseek-main 保持不变…

  // Kimi Code 订阅（Anthropic 兼容端点；模型名与开放平台不同！）
  "kimi-code": {
    "api_key": "sk-替换为 Kimi Code 控制台新建的 Key",
    "model": "kimi-for-coding",
    "endpoint": "https://api.kimi.com/coding/v1/messages"
  }
}
```

### 步骤 2｜`data/config/llm_providers.json`（路由配置，**已入库**，无密钥）

把主 Provider 换成 `kimi-code`，并加上 `pacing` 收紧节流：

```jsonc
{
  "strategy": "priority",
  "preferred_providers": {},
  "providers": [
    {
      "name": "kimi-code",
      "provider": "claude",
      "credentials_ref": "kimi-code",
      "priority": 10,
      "timeout": 120,
      // 订阅制端点：低频串行，降低风控风险（详见 how-to-config-llm.md「端点级节流」）
      "pacing": { "min_interval": 20, "jitter": 0.2, "max_concurrency": 1 }
    },
    {
      "name": "deepseek-main",
      "provider": "claude",
      "credentials_ref": "deepseek-main",
      "priority": 20,
      "timeout": 120
    }
  ]
}
```

> **备选 Provider 建议保留**：一旦 Code 端点返回 403（配额/风控），程序会自动降级到 `deepseek-main`，
> 报告不会因为端点被限流而空白。

### 步骤 3｜验证

```bash
# 配置合法性自检（不发起 LLM 调用）
.venv/bin/python -m src.python.cli doctor --offline

# 跑一次含 LLM 的报告，观察日志中的 provider 尝试与节流是否生效
.venv/bin/python -m src.python.cli report --type full
# 日志应出现：尝试 provider: kimi-code(claude/kimi-for-coding) [https://api.kimi.com/coding/v1/messages]
# 若已声明 pacing，相邻两次 API 请求的日志时间戳间隔应 ≥ min_interval
```

## 三、`pacing` 参数怎么调（订阅端点推荐值）

| 参数 | 推荐值 | 说明 |
|---|:---:|---|
| `min_interval` | `20` | 两次请求最小间隔（秒）。按「每次报告约 9 次调用」估算，串行 + 20s 间隔 ≈ 3 分钟额外等待，换来最低频次 |
| `jitter` | `0.2` | 间隔随机抖动 ±20%，避免固定节奏的机器特征 |
| `max_concurrency` | `1` | 该端点**在途**请求上限 1（配合 `llm_max_concurrency` 全局 3，只有本端点被串行化） |

**想更保守**：`min_interval` 提到 `30~60`，并把 `llm_settings.json` 的 `llm_max_concurrency` 降到 `1~2`
（全局串行，整份报告只用 1 条请求在途）。

**想恢复放开**：删掉 `pacing` 段即可 —— 无 `pacing` 声明的端点**零约束**，行为与未引入节流时完全一致。
这也适用于把主 Provider 换回按量付费端点（`api.moonshot.cn` 有明确的分级 RPM/TPM，可放心并发）。

## 四、换 Key 后仍会看到的两处「无害提示」

| 现象 | 原因 | 是否需要处理 |
|---|---|---|
| 报告「LLM 用量」页签的费用显示 **`-`** | `kimi-for-coding` 不在内置计价表中，而订阅制**本来就不按 token 计费**，费用无意义 | 可不处理（`-` 即"未计价"，非错误）。若想显示估算值，见附录 |
| 首次请求可能较慢 | 订阅端点在高峰时段（工作日 14:00–17:00）偶发 `429 The engine is currently overloaded`（服务端容量，与本账号无关） | 程序会按 `max_retries` 重试；避开高峰更稳 |

## 五、与「403 配额/风控」的交互（重要）

程序对端点状态码的处理**已按订阅端点语义区分**：

| 状态码 | 含义 | 程序行为 |
|---|---|---|
| **403** | 配额/风控拒绝（5 小时窗口用尽、并发上限、月度额度） | **不重试**，直接降级到下一 Provider；报告显示「LLM 端点配额/风控限制已触发」 |
| **429 / 503** | 瞬时限流 / 服务端过载 | 按 `llm_settings.json` 的 `max_retries`（默认 2）退避重试 |
| **401** | Key 或 Base URL 不匹配（两套系统混用） | 认证失败，不重试；检查步骤 1/2 的端点与 Key 是否配套 |

> 403 **不重试**是刻意设计：配额窗口按时间滚动（非瞬时故障），重试无益且高频重试会加剧风控画像。

---

## 附录：让费用页签显示估算值（可选）

订阅额度不按 token 计费，费用页签显示 `-` 属正常。若仍希望有参考值，可把官方公布的单 token 价
（若有）或你的「等效单价」写入 `data/config/llm_settings.json` 的 `pricing` 段：

```jsonc
{
  "pricing": {
    "kimi-for-coding": { "input": 6.5, "output": 27.0, "input_cache_hit": 1.10 }
  }
}
```

> 这只是**显示用**的估算，不产生任何实际计费；号码随意填会导致报告数字失真，建议仅在确有官方单价时填写。
