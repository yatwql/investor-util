# 投资分析报告生成系统

个人投资者辅助工具：读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.2.18

---

## 功能特性

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 腾讯财经（场内实时价）、东方财富（场外基金净值）等多源备线
- **智能缓存** — API 响应按指定频率缓存，减少网络请求，支持手动刷新和缓存管理
- **Excel 报告** — 8 个功能页签：汇总、市值核算、分类汇总、资产穿透 TOP10、基金业绩分析、财经新闻热点、全球政经局势（LLM）、智囊团深度复盘（LLM）
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、新闻关联）
- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 + 华尔街见闻 + akshare（财新网/CCTV）5 源并行获取，去重后与持仓关键词关联
- **行业/概念关键词** — 自动获取东方财富三级行业分类和概念板块，扩展新闻匹配关键词
- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek API，结果按策略缓存（宏观 24h / 智囊团 2h），持仓变更时主动失效
- **机构盈利预测** — 调用 akshare 获取全量股票的研报覆盖、预测 EPS、机构评级，穿透 TOP10 与基金业绩页签同步显示
- **分红历史分析** — 个股历年分红自动汇总，计算年均股息率（分类汇总 + 穿透 TOP10 双列展示）
- **行业资金流向** — LLM 宏观分析注入实时行业资金流向数据（主力净流入/涨跌幅），辅助判断板块轮动
- **基金业绩评价** — 同类排名百分位 + 超额收益修正，自动标注优秀/良好/稳定/偏差
- **TUI 智能摘要** — LLM 分析报告生成后终端直接展示核心观点，无需打开文件

---

## 快速开始

### 方式一：启动脚本（推荐）

```bash
# Windows PowerShell
.\scripts\launch.ps1

# Linux
./scripts/launch.sh
```

启动脚本自动完成：Python 检测 → 虚拟环境创建 → 依赖安装 → 目录创建 → 运行主程序。

### 方式二：手动运行

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
# Windows:
.venv\Scripts\Activate.ps1
# Linux:
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动
python src/main.py
```

---

## 持仓文件格式

支持 `.xlsx` 格式，每页工作表为一个独立账户（页签名即账户名）：

| 列名 | 类型 | 说明 | 示例 |
|------|------|------|------|
| 名称 | 文本 | 股票/基金名称 | 长江电力 |
| 代码 | 文本 | 证券代码 | 600900 |
| 持仓份额 | 数值 | 持有股数/份额 | 800 |
| 每份成本 | 数值 | 单位成本价 | 17.65 |

**格式要求：**
- 列名必须完全匹配 **名称、代码、持仓份额、每份成本**
- 每份成本 > 0，持仓份额 > 0
- 暂无数据的行留空即可，程序自动跳过
- 最新价和昨收盘价由程序自动从 API 获取，无需填入表格

### 持仓数据处理流程

每次执行 **任何菜单命令**（E / N / H / B / L）时：

1. **读取 Excel** — 程序调用 `openpyxl` 重新打开持仓文件，解析每页工作表中的持仓明细
2. **内存中转** — 读取后的持仓数据仅以 Python 对象形式驻留在本次操作的内存中，操作完成后即释放
3. **不落盘缓存** — 持仓原始数据**不会**写入 `data/cache/`，也不存储到任何数据库文件
4. **缓存的是 API 响应** — `data/cache/` 中缓存的是外部数据源返回的价格行情、行业分类、基金业绩、新闻、LLM 分析结果，而非持仓本身

**这意味着：你每次更新 `个人投资持仓信息.xlsx` 后，程序总能读到最新数据**，无需手动刷新或同步。

当持仓文件新增了代码（如新买了一只股票），程序会自动触发该代码的行情预热缓存（`_check_and_warm_for_new_assets`），首次使用时可能稍慢，后续操作即复用缓存。

> 提示：如果需要同时维护多份不同的持仓方案，可在 `holdings_dir` 目录下放置多个 `.xlsx` 文件，程序会列出所有文件供选择。

### 示例数据
- **证券账户** — 场内股票/ETF
- **支付宝-基金投资账户** — 场外基金
- **微信-基金投资账户** — 债券基金
- **银行-基金投资账户** — QDII 基金

---

## 菜单操作

```
  > [E] 生成基础版Excel分析报告
    [N] 生成包含新闻的Excel分析报告
    [H] 生成基础版HTML分析报告
    [B] 生成全系列包含新闻的报告(Excel+HTML)
    [L] 生成全系列完整版报告(Excel+HTML)
    [C] 配置持仓信息目录
    [F] 配置持仓信息文件名
    [R] 配置报告输出目录
    [1] 更新基础类缓存
    [2] 更新持仓类缓存
    [3] 清理过期缓存文件
    [4] 查看缓存统计信息
    [X] 退出
```

| 操作 | 说明 |
|------|------|
| **↑ ↓** | 方向键上下移动选择项 |
| **Enter** | 确认执行当前选中项 |
| **字母/数字键** | 快捷键直达功能 |
| **Ctrl+C** | 退出程序 |

### 报告内容对照

| 菜单 | 模块 1-5 核心报告 | 模块 6 财经新闻 | 模块 7 全球政经（LLM） | 模块 8 智囊团（LLM） |
|------|:---:|:---:|:---:|:---:|
| **E** | ✅ | — | — | — |
| **N** | ✅ | ✅ | — | — |
| **H** | ✅ | ✅ | — | — |
| **B** | ✅ | ✅ | — | — |
| **L** | ✅ | ✅ | ✅ | ✅ |

---

## 配置指南

主配置文件 `data/config/config.json`，程序首次启动时自动创建。

```json
{
  "holdings_dir": "data/holdings",
  "holdings_filename": "个人投资持仓信息.xlsx",
  "output_dir": "reports",
  "news_top_count": 100,
  "news_sources": {
    "sina": true,
    "eastmoney": false,
    "cls": false,
    "wallstreetcn": true,
    "akshare": true
  },
  "preferred_provider": {},
  "llm_key_file": "data/config/llm_key.json",
  "llm_settings_file": "data/config/llm_settings.json",
  "cache_ttl": {
    "price": 86400,
    "index": 86400,
    "rank": 86400,
    "hold": 604800,
    "news": 900,
    "news_corr": 3600,
    "industry": 604800,
    "benchmark": 2592000,
    "llm": 86400,
    "llm_macro": 86400,
    "llm_expert": 7200,
    "profit_forecast": 86400,
    "sector_flow": 900,
    "dividend": 2592000
  }
}
```

### 字段说明

| 字段 | 默认值 | 说明 | TUI 修改 |
|------|--------|------|----------|
| `holdings_dir` | `data/holdings` | 持仓 xlsx 文件所在目录 | 菜单 `C` |
| `holdings_filename` | `个人投资持仓信息.xlsx` | 要读取的持仓文件名 | 菜单 `F` |
| `output_dir` | `reports` | 报告输出目录（最新版+按日期存档） | 菜单 `R` |
| `news_top_count` | `100` | 财经新闻关联分析输出条目上限 | 手动编辑 |
| `news_sources` | 见下方 | 各新闻数据源启停开关 | 手动编辑 |
| `preferred_provider` | `{}` | 优选数据源（预留字段） | 手动编辑 |
| `cache_ttl.*` | 见下方 | 各缓存类型有效期（秒） | 手动编辑 |
| `llm_key_file` | `data/config/llm_key.json` | LLM 密钥文件路径（4 个敏感字段） | 手动编辑 |
| `llm_settings_file` | `data/config/llm_settings.json` | LLM 非敏感配置文件路径 | 手动编辑 |

### news_sources 可调字段

| 子字段 | 默认 | 说明 |
|--------|------|------|
| `sina` | `true` | 新浪财经（财经要闻/国内/国际，正常工作） |
| `eastmoney` | `false` | 东方财富（2026 年 6 月起 API 返回 302 跳转，匿名请求不可用） |
| `cls` | `false` | 财联社（API 要求签名鉴权，匿名请求不可用） |
| `wallstreetcn` | `true` | 华尔街见闻（全球财经直播流，JSON API，无需鉴权，推荐开启） |
| `akshare` | `true` | akshare（财新网要闻 + CCTV 财经新闻，开源封装，推荐开启） |

> **用法：** 当某个新闻源恢复可用时，将其值改为 `true` 即可启用。

### cache_ttl 可调参数

| 子字段 | 默认 | 指纹 | 说明 |
|--------|------|:----:|------|
| `price` | 86400（24h） | — | 股票/基金最新价缓存 |
| `index` | 86400（24h） | — | 市场指数行情缓存 |
| `rank` | 86400（24h） | — | 基金同类排名+区间收益率 |
| `hold` | 604800（7天） | — | 基金前10大持仓明细 |
| `news` | 900（15分钟） | 输入参数指纹 | 多源新闻聚合结果缓存，避免重复 HTTP 获取 |
| `news_corr` | 3600（1小时） | 输入数据指纹 | LLM 新闻关联分析缓存 |
| `llm` | 86400（24h） | —（兜底） | LLM 通用缓存兜底（其他 LLM 类型未匹配时生效） |
| `llm_macro` | 86400（24小时） | 指数+持仓指纹 | 全球政经局势 LLM 分析 |
| `llm_expert` | 7200（2小时） | 持仓结构指纹 | 智囊团深度复盘 LLM 分析 |
| `industry` | 604800（7天） | — | 行业分类/概念板块缓存 |
| `benchmark` | 2592000（30天） | — | 业绩比较基准对照表 |
| `profit_forecast` | 86400（24小时） | 指数指纹 | 机构盈利预测 |
| `sector_flow` | 900（15分钟） | 指数指纹 | 行业资金流向排名 |
| `dividend` | 2592000（30天） | 代码列表指纹 | 股票历史分红 |

> **调整建议：** 盘中频繁刷新可将 `price` 改为 `3600`（1小时）；持仓变动少可将 `hold` 改为 `2592000`（30天）。

---

## LLM 配置指引

模块 7（全球政经局势）、模块 8（智囊团深度复盘）、以及可选的 LLM 新闻关联分析均需调用外部 LLM API。

LLM 配置拆分为两个独立文件（v0.2.15+），分工明确：

| 文件 | 内容 | 用途 |
|------|------|------|
| `data/config/llm_key.json` | 4 个敏感字段 | API 调用渠道（provider / api_key / model / endpoint） |
| `data/config/llm_settings.json` | 所有非敏感配置 | 参数调优（temperature、timeout、cache、system_prompt 等） |

> **为什么拆分？** `llm_key.json` 包含 API Key，可加入 `.gitignore` 避免误提交；
> `llm_settings.json` 不含密钥，可安全纳入版本控制，方便团队共享调优参数。

### 快速配置

**Step 1**：编辑 `data/config/llm_key.json`，填入 provider 和 api_key：

```json
{
  "provider": "claude",
  "api_key": "sk-ant-xxxxxxxxxxxxx",
  "model": "claude-sonnet-4-6",
  "endpoint": "https://api.anthropic.com/v1/messages"
}
```

> `llm_key.json` 仅保留以上 4 个字段，其余所有参数移至 `llm_settings.json`。

**Step 2**（可选，使用默认值即可跳过）：编辑 `data/config/llm_settings.json`，根据偏好微调参数：

```json
{
  "max_retries": 2,
  "temperature_macro": 0.3,
  "temperature_expert": 0.8,
  "temperature_news_correlation": 0.1,
  "timeout_macro": 60,
  "timeout_expert": 120,
  "timeout_news_correlation": 60,
  "cache_enabled_macro": true,
  "cache_enabled_expert": true,
  "cache_enabled_news": true,
  "output_brief_macro": false,
  "output_brief_expert": false,
  "max_tokens_macro": 800,
  "max_tokens_expert": 8192,
  "max_tokens_news_correlation": 2000,
  "cache_ttl_macro": 86400,
  "cache_ttl_expert": 7200,
  "cache_ttl_news_correlation": 3600,
  "system_prompt_macro": null,
  "system_prompt_expert": null,
  "system_prompt_news_correlation": null,
  "llm_news_analysis": false
}
```

**Step 3**：启动程序，菜单选 **L** 生成包含 LLM 分析的完整版报告。

---

### 推荐参数值及说明

| 字段 | 推荐值 | 说明 |
|------|:------:|------|
| `temperature_macro` | **0.3** | 全球政经局势需稳定、事实性输出。低温（<0.5）减少幻觉，确保分析可信；高温（>0.7）易发散编造数据 |
| `temperature_expert` | **0.8** | 智囊团复盘需要多元视角和创造性碰撞。高温（>0.7）鼓励专家输出差异化观点，避免千篇一律 |
| `temperature_news_correlation` | **0.1** | 新闻关联分析要求严格的结构化 JSON 输出。极低温（<0.2）保证格式稳定，杜绝 JSON 解析失败 |
| `timeout_macro` | **60s** | 宏观分析输入简短，60 秒内大部分 API 能完成 |
| `timeout_expert` | **120s** | 智囊团输入量大（含全部持仓明细），需更长的生成时间 |
| `timeout_news_correlation` | **60s** | 新闻分析逐条处理，单次调用数据量不大 |
| `max_retries` | **2** | 遇到 429（限流）或 503（服务不可用）时最多重试 2 次 |
| `max_tokens_macro` | **800** | 宏观分析输出 ≈ 300-600 tokens，800 留有富余 |
| `max_tokens_expert` | **8192** | 智囊团三阶段输出可达 2000+ tokens，8192 保障完整输出 |
| `max_tokens_news_correlation` | **2000** | 新闻 JSON 数组输出，2000 足以覆盖 30+ 条新闻 |
| `cache_enabled_macro` | **true** | 宏观分析 24 小时内市场格局不会剧变，开启缓存节省费用（指数指纹驱动失效） |
| `cache_enabled_expert` | **true** | 智囊团 2 小时内观点有效，开启缓存避免重复扣费 |
| `cache_enabled_news` | **true** | 同批次新闻的 LLM 分析结果可复用，1 小时缓存 |
| `cache_ttl_macro` | **86400（24h）** | 24 小时内指数/持仓不变时复用上次分析结果（指数指纹驱动失效） |
| `cache_ttl_expert` | **7200（2h）** | 2 小时内持仓价格变化不大时复用 |
| `cache_ttl_news_correlation` | **3600（1h）** | 1 小时内同批新闻分析结果有效 |
| `output_brief_macro` | **false** | 关闭时输出完整分析（~500字）；开启后精简至 ≤200 字，适合快速预览 |
| `output_brief_expert` | **false** | 关闭时输出完整三阶段复盘；开启后精简至 ≤300 字 |
| `system_prompt_macro` | **null** | `null` 时使用代码内置默认 prompt；填入自定义文本可覆盖分析风格 |
| `system_prompt_expert` | **null** | `null` 时使用代码内置默认 prompt；填入自定义文本可覆盖专家角色设定 |
| `system_prompt_news_correlation` | **null** | `null` 时使用代码内置默认 prompt；填入自定义文本可覆盖新闻关联判定规则 |
| `llm_news_analysis` | **false** | 默认关闭 LLM 新闻关联分析；开启后每条新闻报道 LLM 判定关联度，增加费用但提高准确率 |

#### temperature 推荐理由详解

| 模块 | 推荐值 | 为什么低/高 | 风险提示 |
|------|:------:|-------------|----------|
| global_macro | 0.3 | 宏观分析是事实性任务：引用真实指数数据、判断经济走向。低温度让输出更聚焦、减少编造虚假经济数据的风险 | >0.5 → 可能编造不存在的经济指标或政策事件 |
| expert_review | 0.8 | 专家复盘是创造性任务：需要五位专家从不同立场碰撞观点。高温度让输出更多样化、避免所有专家意见趋同 | <0.4 → 专家观点雷同，失去"圆桌辩论"意义 |
| news_correlation | 0.1 | 新闻关联是结构化任务：输出严格 JSON 格式。极低温保证格式稳定性，避免 JSON 字段缺失或格式错误 | >0.3 → JSON 解析失败率显著上升，影响报告渲染 |

---

### 字段总表

#### llm_key.json（敏感字段 — 4 个）

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `provider` | ✅ | `"claude"`（Anthropic Messages API 兼容）或 `"openai"`（OpenAI Chat Completions 兼容） |
| `api_key` | ✅ | API 密钥，妥善保管勿提交 Git |
| `model` | — | 模型名称，留空使用 provider 默认值 |
| `endpoint` | — | API 端点 URL，留空使用官方端点 |

#### llm_settings.json（非敏感字段 — 全部可选）

| 字段 | 默认值 | 说明 |
|------|:------:|------|
| `max_retries` | `2` | API 调用失败最大重试次数 |
| `temperature_macro` | `0.3` | 全球政经局势生成温度（0-1），低值 → 稳定可靠，高值 → 创意发散 |
| `temperature_expert` | `0.8` | 智囊团深度复盘生成温度（0-1），建议高值鼓励观点多样性 |
| `temperature_news_correlation` | `0.1` | LLM 新闻关联分析温度（0-1），建议低值保证 JSON 格式稳定性 |
| `timeout_macro` | `60` | 全球政经局势 API 超时秒数 |
| `timeout_expert` | `120` | 智囊团深度复盘 API 超时秒数（输入量大，需更长时间） |
| `timeout_news_correlation` | `60` | LLM 新闻关联分析 API 超时秒数 |
| `cache_enabled_macro` | `true` | 全球政经局势是否启用缓存 |
| `cache_enabled_expert` | `true` | 智囊团深度复盘是否启用缓存 |
| `cache_enabled_news` | `true` | LLM 新闻关联分析是否启用缓存 |
| `output_brief_macro` | `false` | `true` 时输出 ≤200 字精简版宏观分析 |
| `output_brief_expert` | `false` | `true` 时输出 ≤300 字精简版专家复盘 |
| `max_tokens_macro` | `800` | 全球政经局势输出 token 上限 |
| `max_tokens_expert` | `8192` | 智囊团深度复盘输出 token 上限 |
| `max_tokens_news_correlation` | `2000` | LLM 新闻关联分析输出 token 上限 |
| `cache_ttl_macro` | `86400` | 全球政经局势缓存时间（秒，24 小时，指数指纹驱动失效） |
| `cache_ttl_expert` | `7200` | 智囊团深度复盘缓存时间（秒，2 小时） |
| `cache_ttl_news_correlation` | `3600` | LLM 新闻关联分析缓存时间（秒，1 小时） |
| `system_prompt_macro` | `null` | 自定义宏观分析系统提示词，`null` 回退内置默认值 |
| `system_prompt_expert` | `null` | 自定义智囊团系统提示词，`null` 回退内置默认值 |
| `system_prompt_news_correlation` | `null` | 自定义新闻关联系统提示词，`null` 回退内置默认值 |
| `llm_news_analysis` | `false` | 是否启用 LLM 新闻二次关联分析 |

---

### 支持的 provider 及配置示例

所有示例配置写入 `data/config/llm_key.json`，非敏感参数（max_tokens / cache_ttl 等）仍在 `llm_settings.json` 中管理。

<details>
<summary><b>Claude（Anthropic 官方）</b></summary>

```json
{
  "provider": "claude",
  "api_key": "sk-ant-your-key",
  "model": "claude-sonnet-4-6",
  "endpoint": "https://api.anthropic.com/v1/messages"
}
```

可用模型：`claude-sonnet-4-6`（推荐）、`claude-haiku-4-5-20251001`（高性价比）、`claude-opus-4-8`（强推理）、`claude-fable-5`（最新）
</details>

<details>
<summary><b>OpenAI</b></summary>

```json
{
  "provider": "openai",
  "api_key": "sk-your-key",
  "model": "gpt-4o",
  "endpoint": "https://api.openai.com/v1/chat/completions"
}
```

可用模型：`gpt-4o`（推荐）、`gpt-4o-mini`（轻量）、`o3-mini`（推理）
</details>

<details>
<summary><b>DeepSeek（Anthropic 兼容端点 — 推荐）</b></summary>

DeepSeek 官方提供 Anthropic API 兼容端点，`provider` 设为 `"claude"` 即可调用。

```json
{
  "provider": "claude",
  "api_key": "sk-your-deepseek-key",
  "model": "DeepSeek-V4-Flash",
  "endpoint": "https://api.deepseek.com/anthropic/v1/messages"
}
```

- API Key 使用 DeepSeek 官方 Key（带 `sk-` 前缀）
- 模型：`DeepSeek-V4-Flash`（推荐）、`deepseek-v4-pro`、`deepseek-chat`（V3，即将废弃）
- 官方文档：https://api-docs.deepseek.com/guides/anthropic_api
</details>

<details>
<summary><b>DeepSeek（OpenAI 兼容格式）</b></summary>

```json
{
  "provider": "openai",
  "api_key": "sk-your-deepseek-key",
  "model": "deepseek-chat",
  "endpoint": "https://api.deepseek.com/v1/chat/completions"
}
```
</details>

<details>
<summary><b>火山引擎（豆包）</b></summary>

```json
{
  "provider": "openai",
  "api_key": "your-volcengine-key",
  "model": "doubao-pro-32k",
  "endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
}
```

获取方式：火山引擎方舟控制台 → 推理接入点 → 创建接入点。
</details>

---

### token 消耗参考

| 模块 | 输入 token | 输出 token | 单次费用参考 |
|------|-----------|-----------|-------------|
| 模块 7（全球政经） | ~300-800 | ~300-600 | ~$0.005-0.015 |
| 模块 8（智囊团） | ~800-2500 | ~1500-2500 | ~$0.02-0.05 |
| 两者合计（菜单 L） | — | — | ~$0.03-0.06/次 |

- 仅菜单 **L** 触发 LLM 调用，E / N / H / B 不会
- LLM 结果默认缓存 24 小时（全球政经）/ 2 小时（智囊团），缓存有效期内反复按 L 不会重复扣费
- 持仓或指数数据变更时，关联的 LLM 缓存自动失效；也可通过菜单 [2] 更新持仓缓存主动清除 LLM 缓存
- 缓存时间可在 `data/config/llm_settings.json` 中通过 `cache_ttl_macro` / `cache_ttl_expert` / `cache_ttl_news_correlation` 自定义

### 不配置 LLM 时的行为

`llm_key.json` 缺失或 key 为空时，程序不崩溃，其他功能正常。对应报告页签显示占位提示：
```
本节内容待生成 — 请配置 LLM API Key（data/config/llm_key.json）
```

---

## 数据源一览

| 用途 | 主链路 | 备用链路 |
|------|--------|----------|
| 场内实时/收盘价 | 腾讯财经 `qt.gtimg.cn` | 东方财富 `push2.eastmoney.com` |
| 场外基金净值 | 东方财富 `fundf.eastmoney.com` | 天天基金 `fundgz.1234567.com.cn` |
| 基金业绩排名 | 天天基金 `pingzhongdata/{code}.js`（JS 变量解析） | — |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 财经新闻（源1） | 新浪财经 `feed.mix.sina.com.cn` | — |
| 财经新闻（源2） | 东方财富 `push-api-html.eastmoney.com` | — |
| 财经新闻（源3） | 财联社 `www.cls.cn/v1/roll/get_roll_list` | — |
| 财经新闻（源4） | 华尔街见闻 `api-one.wallstcn.com/apiv1/content/lives` | — |
| 财经新闻（源5） | akshare 封装：财新网 `stock_news_main_cx()` + CCTV `news_cctv()` | — |
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | — |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析） | — |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com`（三级行业分类 + 概念板块归属） | — |
| 机构盈利预测 | akshare `stock_profit_forecast_em()` 全量获取 | — |
| 行业资金流向 | akshare `stock_sector_fund_flow_rank()` 今日排名 | — |
| 股票历史分红 | akshare `stock_history_dividend()` 逐股获取 | — |

---

## 缓存文件指引

所有缓存文件存放于 `data/cache/` 目录，JSON 格式，自动管理过期时间。详细缓存机制（TTL 表、指纹构成、覆盖矩阵、降级规则）见 [需求文档 — 缓存策略](docs-stm/managements/requirements.md#6-缓存策略)。

### 缓存文件清单

| 文件名模式 | 用途 | 默认 TTL |
|-----------|------|:--------:|
| `price_{code}.json` | 股票/基金最新价、昨收 | 24h |
| `index_{code}.json` | 市场指数行情 | 24h |
| `fund_perf_{code}.json` | 基金同类排名+区间收益率 | 24h |
| `fund_hold_{code}.json` | 基金前 10 持仓明细 | 7 天 |
| `industry_{code}.json` | 行业分类/概念板块 | 7 天 |
| `fund_benchmarks.json` | 业绩比较基准对照表 | 30 天 |
| `news_{md5}.json` | 多源新闻聚合结果 | 15 分钟 |
| `llm_global_macro_{fingerprint}.json` | 全球政经局势 LLM 分析 | 24h |
| `llm_expert_review_{fingerprint}.json` | 智囊团深度复盘 LLM 分析 | 2h |
| `llm_news_corr_{fingerprint}.json` | LLM 新闻关联分析 | 1h |
| `profit_forecast_{fingerprint}.json` | 机构盈利预测全量数据 | 24h |
| `sector_flow_{fingerprint}.json` | 行业资金流向排名 | 15 分钟 |
| `dividend_{fingerprint}.json` | 股票历史分红汇总 | 30 天 |

**LLM 缓存指纹：** 文件名中的 `{fingerprint}` 是输入数据的 MD5 哈希前 12 位。持仓/指数数据变化时指纹自动改变，原缓存失效。

### 指纹驱动失效机制

以下缓存文件的文件名中**内嵌 MD5 指纹**，输入源数据变化时指纹自动改变 → 缓存键不匹配 → 等效于"缓存未命中" → 自动使用新数据。**无需手动清除。**

| 缓存文件 | 指纹来源 | 指纹数据变更时自动失效 |
|---------|---------|:---:|
| `news_{md5}.json` | 新闻源参数 + 关键词 | 持仓/穿透变化 |
| `llm_global_macro_{fingerprint}.json` | A股/美股指数 + 持仓汇总（总市值/总成本/总盈亏/分类） | 指数波动 / 持仓变化 |
| `llm_expert_review_{fingerprint}.json` | 持仓汇总 + 分类计数 + 穿透 TOP10 + 持仓明细（剔除行情波动字段） | 品种/份额/成本变化 |
| `llm_news_corr_{fingerprint}.json` | 关键词 + 持仓汇总 | 持仓变化 |
| `profit_forecast_{fingerprint}.json` | **A股+美股指数**（`_compute_index_fingerprint`） | 指数行情变化 |
| `sector_flow_{fingerprint}.json` | **A股+美股指数**（`_compute_index_fingerprint`） | 指数行情变化 |
| `dividend_{fingerprint}.json` | **持仓+穿透 A 股代码列表**（`_compute_dividend_fingerprint`） | 持仓/穿透品种变化 |

**TTL 兜底：** 即使指纹未变（源数据无变化），缓存文件仍有 TTL 兜底到期自动刷新，防止数据"永久有效"。

**无指纹（固定键名）的缓存：** `price_{code}`、`index_{code}`、`fund_perf_{code}`、`fund_hold_{code}`、`industry_{code}`、`fund_benchmarks`、`holdings_tracking` — 这些缓存的键名固定，纯 TTL 管理。`holdings_tracking` 内部存了指纹用于变更检测，但键名本身固定。

### TUI 缓存管理

| 菜单 | 功能 |
|------|------|
| `[1]` | 刷新基金业绩、持仓明细、基准、行业分类、新闻、盈利预测、行业资金流向、分红缓存 |
| `[2]` | 刷新价格/指数行情，**并清除 LLM 缓存** |
| `[3]` | 删除已过期的缓存文件 |
| `[4]` | 查看缓存统计（只读） |

---

## 目录结构

```
investor-util/
├── src/                          # 源代码
│   ├── main.py                   # TUI 入口 + 菜单循环
│   ├── config.py                 # 配置读写
│   ├── cache.py                  # 缓存引擎
│   ├── fetcher.py                # 数据获取调度
│   ├── reader.py                 # 持仓 Excel 解析
│   ├── llm_client.py             # LLM 集成（Claude/OpenAI/DeepSeek）
│   ├── models.py                 # 数据模型（Holding dataclass）
│   ├── logger.py                 # 日志模块
│   ├── tui.py                    # 键盘输入封装
│   ├── test_*.py                 # 单元测试（18 个模块）
│   ├── providers/                # API 供应商
│   │   ├── tencent.py            # 腾讯财经（实时价、指数）
│   │   ├── eastmoney.py          # 东方财富（基金净值）
│   │   ├── eastmoney_industry.py # 东方财富（行业分类/概念板块）
│   │   ├── tiantian.py           # 天天基金（业绩排名、持仓）
│   │   ├── sina.py               # 新浪财经（美股指数）
│   │   ├── sina_news.py          # 新浪财经（新闻）
│   │   ├── eastmoney_news.py     # 东方财富（新闻）
│   │   ├── cls_news.py           # 财联社（新闻）
│   │   ├── wallstreetcn_news.py  # 华尔街见闻（新闻）
│   │   ├── akshare_extras.py     # akshare 扩展（盈利预测/资金流向/分红）
│   │   ├── akshare_news.py       # akshare 聚合（财新网/CCTV）
│   │   └── news_aggregator.py    # 多源新闻聚合器
│   └── report/                   # 报告生成
│       ├── excel_writer.py       # Excel 工作簿管理
│       ├── styles.py             # 样式常量
│       ├── summary.py            # 模块 1：汇总
│       ├── market_value.py       # 模块 2：市值核算
│       ├── category.py           # 模块 3：分类汇总
│       ├── penetration.py        # 模块 4：资产穿透 TOP10
│       ├── fund_performance.py   # 模块 5：基金业绩分析
│       ├── news_correlation.py   # 模块 6：财经新闻关联
│       ├── llm_content.py        # 模块 7+8：LLM 内容
│       └── html_writer.py        # HTML 报告引擎
├── data/
│   ├── holdings/                 # 持仓 xlsx 文件
│   ├── cache/                    # API 响应缓存
│   └── config/                   # 配置文件（config.json, llm_key.json, llm_settings.json）
├── reports/                      # 生成报告（最新版+按日期存档）
├── logs/                         # 程序日志（app.log）
├── docs-stm/                     # 项目管理文档
│   ├── plan/                     # 计划/设计文件
│   ├── tmp/                      # 临时/过程文件
│   └── managements/
│       ├── plan.md               # 实现计划
│       ├── requirements.md       # 需求文档
│       ├── testplan.md           # 测试计划
│       ├── changelog.md          # 变更日志
│       └── review-findings.md    # 自审记录
├── scripts/
│   ├── launch.ps1                # Windows 启动脚本
│   └── launch.sh                 # Linux 启动脚本
├── CLAUDE.md                     # Claude Code 指引
├── README.md                     # 本文件
└── requirements.txt
```

---

## 报告文件结构

### Excel 报告

| # | 页签 | 内容说明 |
|:--|------|----------|
| 1 | **汇总** | 当前时间、交易日、A 股/美股指数行情、总市值/成本/盈亏/本日盈亏、各账户小计、更新状态 |
| 2 | **市值核算** | 15 列明细：账户、名称、代码、最新价、净值日期、昨日价、取价方式、溢价率、份额、市值、成本、盈亏、收益率、本日盈亏、取价渠道。取价方式蓝色标识（场内收盘价(T)→蓝、官方净值(T)→蓝、QDII 官方净值(T-1)→蓝），分账户小计+总计 |
| 3 | **分类汇总** | 10 列：资产属性、投资分类、名称、代码、市值、成本、盈亏、收益率、本日盈亏、年均股息率。按资产属性和投资分类分组统计 |
| 4 | **资产穿透 TOP10** | 10 列：排名、名称、代码、穿透市值、占比、板块、概念、预测EPS(2025E)、年均股息率、来源明细。基金拆解为底层标的合并排序，底部标注无法获取穿透数据的基金 |
| 5 | **基金业绩分析** | 12 列：基金、代码、类型、近3月/6月/12月收益率、累计盈亏(¥)、持仓收益率、业绩基准、业绩评价、同类排名、机构覆盖（研报家数+预测EPS）。业绩标色：优秀→红、稳定→蓝、偏差→绿 |
| 6 | **财经新闻热点**（菜单 N/B/L） | 5 源新闻与持仓关键词匹配结果，含标题、来源、时间、关联度。关联关键词按来源富化显示（持仓→蓝色、穿透→紫色、概念→橙色、行业→灰色），可选 LLM 二次关联分析 |
| 7 | **全球政经局势**（菜单 L） | LLM 基于指数行情和持仓结构生成的宏观分析 |
| 8 | **智囊团深度复盘**（菜单 L） | LLM 三阶段圆桌会议：召集令→辩论→定音锤，含调仓建议和风险预警 |

### HTML 报告

单页渲染以上全部模块（模块 1-8），响应式 CSS 自适应桌面/移动端。额外特性：
- 盈亏正数红色、负数绿色着色
- 取价方式蓝色标识（与 Excel 端规则一致）
- 新闻来源可点击跳转
- 基金业绩评价带颜色标签
- 页脚标注生成时间和版本号
- LLM 内容为条件渲染（仅菜单 L 时显示）

---

## 基金业绩评价标准

基金业绩分析（模块 5）采用 **三层计算逻辑**，数据来源于天天基金 API：

### 第 1 层：基础评级

基于同类排名百分位（`Data_rateInSimilarPersent`）：

| 排名百分位 | 基础标签 |
|:-----------|:---------|
| ≤ 20%（前 1/5） | **优秀** |
| 20% ~ 30% | **良好** |
| 30% ~ 50% | **稳定** |
| > 50%（后 1/2） | **偏差** |

> API 无百分位数据时降级使用排名/总数折算百分位。

### 第 2 层：超额收益修正

基于 `Data_performanceEvaluation` 中的超额收益评分调整评级：

| 超额收益评分 | 修正规则 |
|:-------------|:---------|
| ≥ 80 | 基础评级**上调一级**（如 良好 → 优秀） |
| 40 ~ 80 | 维持基础评级不变 |
| < 40 | 基础评级**下调一级**（如 稳定 → 偏差） |

### 第 3 层：显示与标色

| 最终标签 | Excel / HTML 标色 | 显示文本 |
|:---------|:------------------|:---------|
| **优秀** | 红色 `#CC0000` | 持续跑赢基准，超额收益显著 |
| **良好** | 默认 | 稳定跑赢基准，组合管理得当 |
| **稳定** | 蓝色 `#0066CC` | 收益率稳健，波动控制良好 |
| **偏差** | 绿色 `#009900` | 近期表现欠佳，需关注持仓变化 |

---

## 常见问题

**Q: 启动后菜单显示乱码？**
A: 请使用支持 UTF-8 的终端（Windows Terminal 或 VS Code 终端），或运行 `chcp 65001` 切换代码页。

**Q: 提示"文件未找到"？**
A: 菜单 `C` 配置正确的持仓目录，或菜单 `F` 选择正确的文件名。

**Q: 如何强制刷新 LLM 内容？**
A: 菜单 `L` 会先检查缓存，缓存过期（默认宏观 24h/智囊团 2h）或持仓/指数数据变更时才重新调用 LLM。如需强制刷新，先执行菜单 `[2]` 更新持仓缓存即可清除关联 LLM 缓存。

**Q: 报告数据感觉不完整？**
A: 先试菜单 `[1]` 更新基础缓存，再试 `[2]` 更新持仓缓存，最后重试生成报告。

**Q: 后续如何升级？**
A: 拉取最新代码后，重新运行启动脚本即可自动更新依赖。

**Q: 能否不配置 LLM 使用程序？**
A: 可以。菜单 E / N / H / B 全部不依赖 LLM，仅菜单 L 需要 LLM 配置。

---

## 相关文档

| 文档 | 说明 |
|------|------|
| [实现计划](docs-stm/managements/plan.md) | 迭代计划、技术决策 |
| [需求文档](docs-stm/managements/requirements.md) | 完整需求定义 |
| [测试计划](docs-stm/managements/testplan.md) | 质量控制标准 |
| [变更日志](docs-stm/managements/changelog.md) | 版本更新记录 |
| [自审记录](docs-stm/managements/review-findings.md) | 代码审查问题跟踪 |
| [CLAUDE.md](CLAUDE.md) | AI 编程助手指引 |
