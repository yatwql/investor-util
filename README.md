# 投资分析报告生成系统

个人投资者辅助工具：读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.2.33

---

## 功能特性

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 腾讯财经（场内实时价）、东方财富（场外基金净值）等多源备线
- **智能缓存** — API 响应按指定频率缓存，减少网络请求，支持手动刷新和缓存管理
- **Excel 报告** — 10 个功能页签：投资分析汇总、市值核算明细表、分类汇总表、资产穿透TOP10、基金业绩分析、财经新闻热点与持仓关联分析、全球政经局势（LLM）、智囊团深度复盘（LLM）、持仓体检报告（LLM）、穿透深度分析（LLM）
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、新闻关联，全部页面顺序展示）
- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 + 华尔街见闻 + akshare（财新网/CCTV）5 源并行获取，去重后与持仓关键词关联
- **行业/概念关键词** — 自动获取东方财富三级行业分类和概念板块，扩展新闻匹配关键词
- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek API，结果按策略缓存（全球政经局势/穿透深度分析 24h / 智囊团深度复盘/持仓体检报告 2h / 财经新闻热点与持仓关联分析 1h），持仓变更时主动失效
- **机构盈利预测** — 调用 akshare 获取全量股票的研报覆盖、预测 EPS、机构评级，穿透 TOP10 与基金业绩页签同步显示
- **分红历史分析** — 个股历年分红自动汇总，计算年均股息率（分类汇总 + 穿透 TOP10 双列展示）
- **行业资金流向** — LLM 宏观分析注入实时行业资金流向数据（主力净流入/涨跌幅），辅助判断板块轮动
- **基金业绩评价** — 同类排名百分位 + 超额收益修正，自动标注优秀/良好/稳定/偏差
- **TUI 智能摘要** — LLM 分析报告生成后终端直接展示核心观点（全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析），无需打开文件即可快速了解 LLM 输出重点

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

> **💡 外部虚拟环境管理：** 设置环境变量 `VENV_PATH` 可将 `.venv` 放在项目目录外部，
> 方便多个项目共享或集中管理虚拟环境：
> ```bash
> # Windows PowerShell
> $env:VENV_PATH = "D:\shared\venvs\investor-util"
> .\scripts\launch.ps1
>
> # Linux
> VENV_PATH=/opt/venvs/investor-util ./scripts/launch.sh
> ```
> 首次运行自动创建并链接，再次运行直接复用。

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
python src/python/main.py
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
    [H] 生成包含新闻的HTML分析报告
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

| 菜单 | 核心报告 | 财经新闻 | 全球政经局势（LLM） | 智囊团深度复盘（LLM） | 持仓体检报告（LLM） | 穿透深度分析（LLM） |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **E** | ✅ | — | — | — | — | — |
| **N** | ✅ | ✅ | — | — | — | — |
| **H** | ✅ | ✅ | — | — | — | — |
| **B** | ✅ | ✅ | — | — | — | — |
| **L** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

缓存管理：
| 菜单 | 功能 |
|------|------|
| `[1]` | 清除并重新获取基金业绩、持仓明细、基准、行业分类、新闻、LLM新闻关联（含逐条缓存）、盈利预测、行业资金流向、分红 |
| `[2]` | 清除并重新获取价格/指数行情，**附带清除 LLM 缓存**（智囊团深度复盘、全球政经局势、持仓体检报告、穿透深度分析） |
| `[3]` | 按 TTL 扫描删除已过期的缓存文件 |
| `[4]` | 查看缓存统计信息（仅浏览，不删除） |

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
    "eastmoney": true,
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
    "llm_news_correlation": 3600,
    "industry": 604800,
    "benchmark": 2592000,
    "llm_global_macro": 86400,
    "llm_expert_review": 7200,
    "llm_health_check": 7200,
    "llm_penetration_deep": 86400,
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
| `preferred_provider` | `{}` | 各数据类型的首选提供商覆写 | 手动编辑 |
| `user_fund_benchmarks` | `{}` | 自定义基金业绩基准覆盖（键=基金代码，值=基准代码） | 手动编辑 |
| `cache_ttl.*` | 见下方 | 各缓存类型有效期（秒） | 手动编辑 |
| `llm_key_file` | `data/config/llm_key.json` | LLM 密钥文件路径（4 个必填字段 + 4 个可选回退字段） | 手动编辑 |
| `llm_settings_file` | `data/config/llm_settings.json` | LLM 非敏感配置文件路径 | 手动编辑 |

### news_sources 可调字段

| 子字段 | 默认 | 说明 |
|--------|------|------|
| `sina` | `true` | 新浪财经（财经要闻/国内/国际，正常工作） |
| `eastmoney` | `true` | 东方财富（np-weblist 快讯接口，req_trace 参数，稳定可用） |
| `cls` | `false` | 财联社（API 要求签名鉴权，匿名请求不可用） |
| `wallstreetcn` | `true` | 华尔街见闻（全球财经直播流，JSON API，无需鉴权，推荐开启） |
| `akshare` | `true` | akshare（财新网要闻 + CCTV 财经新闻，开源封装，推荐开启） |

> **用法：** 将值改为 `true` 或 `false` 即可启用/禁用对应新闻源。

### preferred_provider 可调字段

`preferred_provider` 用于手动指定某类数据的首选提供商，将其提到 Provider Chain 第一位。不配置时全部走默认优先级，一个源失败后自动递补备用。

适用场景：某网络环境下特定数据源更稳定、或因 IP 限制某数据源不可用。

| 子字段 | 默认 | 可选值 | 说明 |
|--------|:----:|--------|------|
| `price` | — | `tencent`, `eastmoney` | 股票/ETF 实时收盘价首选源 |
| `index` | — | `tencent`, `sina` | A 股指数首选源 |
| `us_index` | — | `sina` | 美股指数首选源 |
| `fund_rank` | — | `tiantian` | 基金业绩排名首选源 |
| `fund_hold` | — | `tiantian` | 基金持仓穿透首选源 |

示例 — 将行情首选从腾讯改为东方财富：

```json
{
  "preferred_provider": {
    "price": "eastmoney"
  }
}
```

> `preferred_provider` 为空对象 `{}` 时全部使用默认优先级。

### user_fund_benchmarks 自定义基准

`user_fund_benchmarks` 用于覆盖部分基金的业绩比较基准。代码内置了主流宽基/行业指数（沪深 300、中证 500、纳斯达克 100 等），遇到不在内置库中的基金时，可通过此字段手动指定。

格式：`{"基金代码": "基准代码"}`，键值均为六位基金代码（字符串或数字均可）。

```json
{
  "user_fund_benchmarks": {
    "000001": "000300",
    "005827": "399001",
    "110011": "000300"
  }
}
```

> 内置基准库实时自动补充，`user_fund_benchmarks` 仅在置信度不足时作为兜底。空对象 `{}` 表示不添加自定义覆盖。

### cache_ttl 可调参数

| 键名 | 文件名模式 | 默认 TTL | 指纹来源 | 说明 |
|------|-----------|:--------:|----------|------|
| `price` | `price_{code}.json` | 24h | — | 股票/基金最新价、昨收 |
| `index` | `index_{code}.json` | 24h | — | 市场指数行情 |
| `rank` | `fund_perf_{code}.json` | 24h | — | 基金同类排名+区间收益率 |
| `hold` | `fund_hold_{code}.json` | 7 天 | — | 基金前 10 持仓明细 |
| `industry` | `industry_{code}.json` | 7 天 | — | 行业分类/概念板块 |
| `benchmark` | `fund_benchmarks.json` | 30 天 | — | 业绩比较基准对照表 |
| `news` | `news_{md5}.json` | 15 分钟 | 新闻源参数 + 关键词 | 多源新闻聚合结果 |
| `llm_global_macro` | `llm_global_macro_{fingerprint}.json` | 24h | A股/美股指数 + 持仓汇总 | 全球政经局势 LLM 分析 |
| `llm_expert_review` | `llm_expert_review_{fingerprint}.json` | 2h | 持仓汇总 + 分类计数 + 穿透 TOP10 + 持仓明细 | 智囊团深度复盘 LLM 分析 |
| `llm_health_check` | `llm_health_check_{fingerprint}.json` | 2h | 持仓明细（排除行情波动） | 持仓体检报告 LLM 分析 |
| `llm_penetration_deep` | `llm_penetration_deep_{fingerprint}.json` | 24h | 持仓明细（排除行情波动） | 穿透深度分析 LLM 分析 |
| `llm_news_correlation` | `llm_news_item_{hash}.json`（逐条） | 1h | 标题前 80 字 + 持仓指纹 | LLM 新闻关联分析 |
| `profit_forecast` | `profit_forecast_{fingerprint}.json` | 24h | A股+美股指数 | 机构盈利预测全量数据 |
| `sector_flow` | `sector_flow_{fingerprint}.json` | 15 分钟 | A股+美股指数 | 行业资金流向排名 |
| `dividend` | `dividend_{fingerprint}.json` | 30 天 | 持仓+穿透 A 股代码列表 | 股票历史分红汇总 |

> **指纹驱动失效：** 文件名中的 `{fingerprint}` 是输入数据的 MD5 哈希。持仓/指数数据变化时指纹自动改变，原缓存失效，无需手动清除。
> 
> **TTL 兜底：** 即使指纹未变，缓存文件仍有 TTL 兜底到期自动刷新，防止数据"永久有效"。
> 
> **调整建议：** 盘中频繁刷新可将 `price` 改为 `3600`（1小时）；持仓变动少可将 `hold` 改为 `2592000`（30天）。

---

## LLM 配置指引

全球政经局势、智囊团深度复盘、持仓体检报告、穿透深度分析、以及可选的 LLM 新闻关联分析均需调用外部 LLM API。

LLM 配置拆分为两个独立文件（v0.2.15+），分工明确：

| 文件 | 内容 | 用途 |
|------|------|------|
| `data/config/llm_key.json` | 4 个必填 + 4 个可选回退字段 | API 调用渠道（必填：provider / api_key / model / endpoint；可选：fallback_provider / fallback_api_key / fallback_endpoint / fallback_model） |
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

> `llm_key.json` 仅保留必填字段（provider / api_key / model / endpoint）和可选回退字段（fallback_provider / fallback_api_key / fallback_endpoint / fallback_model，见下方说明），其余所有参数移至 `llm_settings.json`。

> **可选 — 跨 Provider 自动回退**：可在 `llm_key.json` 中额外配置 `fallback_provider`、`fallback_api_key`、`fallback_endpoint`、`fallback_model`。当主 provider 连续请求失败（网络超时、429 限流、服务端错误）后，自动切换到回退 provider 重试。适用于高可用场景，如主用 DeepSeek（低成本）、回退到 Anthropic Claude（高稳定性）：
> ```json
> {
>   "provider": "claude",
>   "api_key": "sk-ant-xxxxxxxxxxxxx",
>   "model": "claude-sonnet-4-6",
>   "endpoint": "https://api.anthropic.com/v1/messages",
>   "fallback_provider": "openai",
>   "fallback_api_key": "sk-your-fallback-key",
>   "fallback_endpoint": "https://api.openai.com/v1/chat/completions",
>   "fallback_model": "gpt-4o-mini"
> }
> ```

**Step 2**（可选，使用默认值即可跳过）：编辑 `data/config/llm_settings.json`，根据偏好微调参数。配置项按业务模块分组排列：

```json
{
  "max_retries": 2,
  "enabled_llm_news_correlation": false,

  "system_prompt_global_macro": null,
  "model_global_macro": null,
  "temperature_global_macro": 0.3,
  "max_tokens_global_macro": 1024,
  "timeout_global_macro": 60,
  "cache_enabled_global_macro": true,
  "output_brief_global_macro": false,
  "thinking_enabled_global_macro": false,
  "thinking_budget_global_macro": 4000,
  "reasoning_effort_global_macro": "high",

  "system_prompt_expert_review": null,
  "model_expert_review": null,
  "temperature_expert_review": 0.8,
  "max_tokens_expert_review": 8192,
  "timeout_expert_review": 120,
  "cache_enabled_expert_review": true,
  "output_brief_expert_review": false,
  "thinking_enabled_expert_review": true,
  "thinking_budget_expert_review": 16000,
  "reasoning_effort_expert_review": "high",

  "system_prompt_health_check": null,
  "model_health_check": null,
  "temperature_health_check": 0.5,
  "max_tokens_health_check": 4096,
  "timeout_health_check": 120,
  "cache_enabled_health_check": true,
  "output_brief_health_check": false,
  "thinking_enabled_health_check": true,
  "thinking_budget_health_check": 12000,
  "reasoning_effort_health_check": "high",

  "system_prompt_penetration_deep": null,
  "model_penetration_deep": null,
  "temperature_penetration_deep": 0.4,
  "max_tokens_penetration_deep": 4096,
  "timeout_penetration_deep": 90,
  "cache_enabled_penetration_deep": true,
  "output_brief_penetration_deep": false,
  "thinking_enabled_penetration_deep": false,
  "thinking_budget_penetration_deep": 8000,
  "reasoning_effort_penetration_deep": "high",

  "system_prompt_news_correlation": null,
  "model_news_correlation": null,
  "temperature_news_correlation": 0.1,
  "max_tokens_news_correlation": 2000,
  "timeout_news_correlation": 60,
  "cache_enabled_news_correlation": true,
  "thinking_enabled_news_correlation": false,
  "thinking_budget_news_correlation": 4000,
  "reasoning_effort_news_correlation": "high"
}
```

> **注意**：
> - `system_prompt_*` 字段已默认同步代码内置提示词，可直接编辑覆盖。
> - `pricing` 段可省略（代码内置默认定价：货币 CNY，DeepSeek-V4-Flash 输入 1 元/M、输出 2 元/M、缓存命中 0.02 元/M）。仅需自定义覆盖时才在 `llm_settings.json` 中添加 `pricing` 段，例如：
>
> ```json
> "pricing": {
>   "currency": "CNY",
>   "deepseek-v4-flash": {"input": 1, "output": 2, "input_cache_hit": 0.02},
>   "deepseek-v4-pro": {"input": 3, "output": 6, "input_cache_hit": 0.025}
> }
> ```
>
> 文件中的 `pricing` 优先级高于代码内置默认值。只写需要覆盖的模型即可，其余模型自动使用代码默认值。
> 各模块角色定位及对应配置参数：

| 模块 | 配置参数 | 角色 | 核心指令摘要 |
|------|----------|------|-------------|
| 全球政经局势 | `system_prompt_global_macro` | 资深宏观经济学家 | 500 字分析主要经济体政策走向、地缘风险、持仓影响 |
| 智囊团深度复盘 | `system_prompt_expert_review` | 投资智囊团召集人 | 三阶段：Phase 1 召集令 → Phase 2 圆桌辩论 → Phase 3 定音锤。净值滞后品种（标注"净值:YYYY-MM-DD"）不得讨论本日盈亏；QDII 基金（标注"(QDII滞后1日)"）底层定价天然滞后一交易日 |
| 持仓体检报告 | `system_prompt_health_check` | 组合体检分析师 | 四维度评分（风险/流动性/收益/成本），综合评级+改进建议 |
| 穿透深度分析 | `system_prompt_penetration_deep` | 穿透分析专家 | 行业集中度、品种集中度、国别/币种暴露分析 |
| 财经新闻热点与持仓关联分析 | `system_prompt_news_correlation` | 资深金融分析师 | 逐条分析新闻关联性，输出 JSON（高/中/低/无关+原因） |

> 代码内置完整提示词定义在 `src/python/llm_client.py` 中，变量名分别为 `_SYSTEM_GLOBAL_MACRO`、`_SYSTEM_EXPERT_REVIEW`、`_SYSTEM_HEALTH_CHECK`、`_SYSTEM_PENETRATION_DEEP`、`_SYSTEM_NEWS_CORRELATION`。
> 将配置项设为 `null` 即回退使用这些内置 prompt，方便升级时自动获取更新。

**Step 3**：启动程序，菜单选 **L** 生成包含 LLM 分析的完整版报告。

### 推荐参数值及说明

| 字段 | 推荐值 | 说明 |
|------|:------:|------|
| `temperature_global_macro` | **0.3** | 全球政经局势需稳定、事实性输出。低温（<0.5）减少幻觉，确保分析可信；高温（>0.7）易发散编造数据。风险：>0.5 可能编造不存在的经济指标或政策事件 |
| `temperature_expert_review` | **0.8** | 智囊团复盘需要多元视角和创造性碰撞。高温（>0.7）鼓励专家输出差异化观点，避免千篇一律。风险：<0.4 专家观点雷同，失去圆桌辩论意义 |
| `temperature_news_correlation` | **0.1** | 新闻关联分析要求严格的结构化 JSON 输出。极低温（<0.2）保证格式稳定，杜绝 JSON 解析失败。风险：>0.3 JSON 解析失败率显著上升，影响报告渲染 |
| `temperature_health_check` | **0.5** | 持仓体检需要平衡稳定性和判断力。中等温度（0.5）在保持事实准确的同时保留适度判断空间 |
| `temperature_penetration_deep` | **0.4** | 穿透深度分析需稳定的事实性输出（行业占比和币种分布），中等低温平衡准确性和保守性 |
| `timeout_global_macro` | **60s** | 宏观分析输入简短，60 秒内大部分 API 能完成 |
| `timeout_expert_review` | **120s** | 智囊团输入量大（含全部持仓明细），需更长的生成时间 |
| `timeout_news_correlation` | **60s** | 新闻分析逐条处理，单次调用数据量不大 |
| `timeout_health_check` | **120s** | 持仓体检输入中等，120 秒确保完整评分输出 |
| `timeout_penetration_deep` | **90s** | 穿透分析输入中等，90 秒确保完整输出 |
| `max_retries` | **2** | 遇到 429（限流）或 503（服务不可用）时最多重试 2 次 |
| `max_tokens_global_macro` | **1024** | 宏观分析输出 ≈ 300-600 tokens，1024 留有充足富余 |
| `max_tokens_expert_review` | **8192** | 智囊团三阶段输出可达 2000+ tokens，8192 保障完整输出 |
| `max_tokens_news_correlation` | **2000** | 新闻 JSON 数组输出，2000 足以覆盖 30+ 条新闻 |
| `max_tokens_health_check` | **4096** | 体检报告四个维度评分+建议，4096 保障完整输出 |
| `max_tokens_penetration_deep` | **4096** | 穿透深度分析行业集中度+币种暴露，4096 保障完整输出（此前 2048 易截断） |
| `model_global_macro` | **null** | `null` 时使用 `llm_key.json` 的默认 model；填入模型名（如 `"claude-sonnet-4-6"`）单独指定全球政经局势用模型 |
| `model_expert_review` | **null** | `null` 时使用默认 model；填入模型名单独指定智囊团深度复盘用模型（如需更大输出量可换 `"claude-opus-4-8"`） |
| `model_news_correlation` | **null** | `null` 时使用默认 model；填入模型名单独指定新闻关联分析用模型（批量任务可选轻量模型如 `"claude-haiku-4-5"` 降低成本） |
| `model_health_check` | **null** | `null` 时使用默认 model；填入模型名单独指定持仓体检用模型，推荐保持 `null` |
| `model_penetration_deep` | **null** | `null` 时使用默认 model；填入模型名单独指定穿透深度分析用模型，推荐保持 `null` |
| `cache_enabled_global_macro` | **true** | 宏观分析 24 小时内市场格局不会剧变，开启缓存节省费用（指数指纹驱动失效） |
| `cache_enabled_expert_review` | **true** | 智囊团 2 小时内观点有效，开启缓存避免重复扣费 |
| `cache_enabled_news_correlation` | **true** | 同批次新闻的 LLM 分析结果可复用，1 小时缓存 |
| `cache_enabled_health_check` | **true** | 持仓体检 2 小时内有效，开启缓存节省费用 |
| `cache_enabled_penetration_deep` | **true** | 穿透分析 24 小时内行业结构不会剧变，开启缓存 |
| `output_brief_global_macro` | **false** | 关闭时输出完整分析（~500字）；开启后精简至 ≤200 字，适合快速预览 |
| `output_brief_expert_review` | **false** | 关闭时输出完整三阶段复盘；开启后精简至 ≤300 字 |
| `output_brief_health_check` | **false** | 关闭时输出完整分析（四维度评分+建议）；开启后精简至 ≤300 字 |
| `output_brief_penetration_deep` | **false** | 关闭时输出完整分析（行业集中度+币种暴露）；开启后精简至 ≤300 字 |

> **注意**：`news_correlation` 模块无 `output_brief` 配置项。该模块输出严格 JSON 格式供程序解析，精简会破坏 JSON 结构，故不支持精简模式。

| 字段 | 推荐值 | 说明 |
|------|:------:|------|
| `system_prompt_*` | （已同步） | 已默认同步代码内置 prompt，可直接编辑修改。设为 `null` 回退使用代码默认值。各模块角色定位见下方说明 |
| `thinking_enabled_global_macro` | `false` | 全球政经启用 Extended Thinking（不建议——输出短，不值得）。**Claude / DeepSeek 均兼容** |
| `thinking_enabled_expert_review` | `true` ⭐ | **默认已开启**。智囊团深度复盘启用 Extended Thinking。**Claude / DeepSeek 均兼容** |
| `thinking_enabled_news_correlation` | `false` | 新闻关联启用 Extended Thinking（不建议——JSON 格式任务不需要深度推理）。**Claude / DeepSeek 均兼容** |
| `thinking_enabled_health_check` | `true` | 持仓体检启用 Extended Thinking（建议——评分+建议需深度推理）。**Claude / DeepSeek 均兼容** |
| `thinking_enabled_penetration_deep` | `false` | 穿透分析启用 Extended Thinking（不建议——结构化输出不需要深度推理） |
| `thinking_budget_global_macro` | 4000 | **仅 Claude** 政经 thinking token 预算。自动兜底 `max_tokens + 4096` |
| `thinking_budget_expert_review` | 16000 | **仅 Claude** 智囊团 thinking token 预算。`max_tokens_expert_review=8192`，16000 留充足余量 |
| `thinking_budget_news_correlation` | 4000 | **仅 Claude** 新闻关联 thinking token 预算。实际被关闭时该值不生效 |
| `thinking_budget_health_check` | 12000 | **仅 Claude** 体检 thinking token 预算。`max_tokens_health_check=4096`，12000 留充足余量 |
| `thinking_budget_penetration_deep` | 8000 | **仅 Claude** 穿透 thinking token 预算。`max_tokens_penetration_deep=4096`，8000 留充足余量 |
| `reasoning_effort_global_macro` | `"high"` | **仅 DeepSeek** 思考深度：`"high"`（标准）或 `"max"`（极致） |
| `reasoning_effort_expert_review` | `"high"` | **仅 DeepSeek** 思考深度，推荐 `"max"` 以充分发挥 V4 推理能力 |
| `reasoning_effort_news_correlation` | `"high"` | **仅 DeepSeek** 思考深度，建议保持 `"high"` |
| `reasoning_effort_health_check` | `"high"` | **仅 DeepSeek** 思考深度，推荐 `"max"` 以增强评分判断 |
| `reasoning_effort_penetration_deep` | `"high"` | **仅 DeepSeek** 思考深度，建议保持 `"high"` |
| `enabled_llm_news_correlation` | **false** | 默认关闭 LLM 新闻关联分析；开启后每条新闻报道 LLM 判定关联度，增加费用但提高准确率 |
| `pricing` | （内置） | 模型 Token 定价表，格式 `{"model_name": {"input": X, "output": Y, "input_cache_hit": Z}}`（每百万 Token，货币由 `pricing.currency` 决定）。`input` = 标准输入（缓存未命中），`input_cache_hit` = 缓存命中输入（可选，缺失时等于 `input` 即无折扣），`currency` = 货币标识（`"CNY"` / `"USD"`，默认 `"CNY"`）。代码内置默认定价以人民币计价，`llm_settings.json` 中的 `pricing` 段优先级更高，可覆盖或新增模型。例如 DeepSeek-V4-Flash：输入 1 元/M、输出 2 元/M、缓存命中 0.02 元/M。用于 `_estimate_cost()` 生成格式化费用估算字符串供报告展示 |

#### Prompt Caching（Anthropic 专属）

> 仅 `provider: "claude"` 时生效，OpenAI 提供商不适用。

代码在 `_call_claude()` 中自动启用 Anthropic Messages API 的 [Prompt Caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) 功能。system prompt 以数组格式发送并标注 `cache_control: ephemeral`：

- **生效条件**：同一 system prompt 在 **5 分钟内**重复使用
- **场景**：新闻关联分析批量处理时最有价值——5 分钟内多次调用共享缓存，**输入 token 扣费减少约 50%**
- **效果**：费用按 `cache_creation_tokens`（写入缓存）× 1.25 + `cache_read_tokens`（命中缓存）× 0.1 计价，远低于全价输入 token
- **无感使用**：不需要任何配置项，调用 Claude API 时自动启用

---

#### Extended Thinking

> **Claude**（provider: `"claude"`）：模型 ≥ `claude-sonnet-4` 时生效，用 `thinking.budget_tokens` 控制思考 token 预算。
>
> **DeepSeek**（provider: `"claude"` + endpoint `api.deepseek.com/anthropic`）：模型 `deepseek-v4-*` / `deepseek-chat` 时生效，用 `output_config.effort` 控制思考深度（`"high"` / `"max"`）。

**[Extended Thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)** 让模型在回答前进行深度推理，大幅提升复杂分析的深度和逻辑严谨性。代价是输出 token 大幅增加（约 2~4 倍），费用相应上升。

##### 配置方式

在 `llm_settings.json` 中设置（示例为 DeepSeek 全面开启智囊团深度推理）：

```json
{
  "thinking_enabled_expert_review": true,
  "reasoning_effort_expert_review": "max"
}
```

或使用 Claude 模型：

```json
{
  "thinking_enabled_expert_review": true,
  "thinking_budget_expert_review": 16000
}
```


##### 模型差异详解

| 维度 | Anthropic Claude | DeepSeek V4+ |
|------|------------------|-------------|
| 控制参数 | `thinking.budget_tokens`（token 数量预算） | `output_config.effort`（"high"/"max" 定性控制） |
| 互斥参数 | temperature | temperature |
| 兼容端点 | `api.anthropic.com` | `api.deepseek.com/anthropic`（Anthropic 兼容端点） |
| 推荐场景 | 预算可控，适合所有模型 | `max` 深度推荐仅用于智囊团；宏观/新闻保持 `high` |
| 降级策略 | 模型不支持时自动跳过，记录 WARNING | 模型不支持时自动跳过，记录 WARNING |

##### `thinking_budget` 与 `max_tokens_*` 的关系（仅 Claude，必读）

**仅在使用 Claude 模型时 `thinking_budget_{模块}` 有意义。** DeepSeek 使用 `reasoning_effort`（`"high"` / `"max"`）定性控制思考深度，不涉及 token 预算概念。

以下解释针对 Claude 的 `thinking_budget_{模块}` 和 `max_tokens_{模块}`（如 `thinking_budget_expert_review` / `max_tokens_expert_review`）。

| 配置项（llm_settings.json） | 管什么 | expert 默认值 |
|------|--------|:------------:|
| `max_tokens_expert_review` | **最终输出文本**的最大 token 数 | 8192 |
| `thinking_budget_expert_review` | **内部思考过程**分配的 token 预算 | 16000 |

模型先消耗 `thinking_budget` 做内部推理（该部分不可见），再从剩余额度里吐出最终回答（不超过 `max_tokens`）：

```
┌─── thinking_budget_expert_review: 16000 ────────────────┐
│  ┌── 模型内部思考 ──┐  ┌── 最终输出 ──────────┐   │
│  │  ~8000 tokens    │  │  ~3000 tokens (可见)  │   │
│  │  (不可见，不计入  │  │  ≤ max_tokens=8192   │   │
│  │   输出 token)     │  │                      │   │
│  └──────────────────┘  └──────────────────────┘   │
│                   总计 ~11000 tokens（API 按此计价）  │
└───────────────────────────────────────────────────┘
```

**API 硬性约束（仅 Claude）：** `thinking_budget_{模块}` 的值 **必须 ≥ 对应的 `max_tokens_{模块}` + 1024**。实际场景：
- `max_tokens_global_macro=1024` → `thinking_budget_global_macro` 至少 2048（默认 4000 ✅）
- `max_tokens_expert_review=8192` → `thinking_budget_expert_review` 至少 9216（默认 16000 ✅）

> **提示**：开启 Extended Thinking 后，所有 LLM 章节底部统一追加 `| Extended Thinking` 标识，
> 格式为：`模型：{model} | Token 用量：输入 X / 输出 Y = Z | 估算费用：${cost} | Extended Thinking`，
> Excel 与 HTML 报告保持一致。未启用时仅显示模型名、用量和费用。
> - `max_tokens_news_correlation=2000` → `thinking_budget_news_correlation` 至少 3024（默认 4000 ✅）

**代码自动保护：**
- 若 `thinking_budget` 小于 `max_tokens + 1024`，自动补足到 `max_tokens + 4096`。
- 若配置开启但模型不支持（如 `claude-sonnet-3-5`），自动跳过并记录 WARNING。
- DeepSeek V4+ 与 Claude Sonnet 4+ / Opus 4+ 均可自动识别，无需手动适配。

**一句话总结（Claude）：** `max_tokens_{模块}` 管"最终说多少"，`thinking_budget_{模块}` 管"允许想多久"。
**一句话总结（DeepSeek）：** `reasoning_effort_{模块}` 管"想多深"，`"max"` 对应深度分析的极致模式。

##### 效果参考

| 分析模块 | 关闭 thinking（token 用量） | 开启 thinking（token 用量） | 费用倍率 |
|------|:---------------------------:|:---------------------------:|:--------:|
| 智囊团深度复盘 | 输入 ~3000 / 输出 ~2000 | 输入 ~3000 / 输出 ~8000 | ~2.5× |
| 全球政经局势 | 输入 ~1500 / 输出 ~600 | 输入 ~1500 / 输出 ~2500 | ~3× |

---


### 支持的 provider 及配置示例

所有示例配置写入 `data/config/llm_key.json`，非敏感参数（max_tokens 等）仍在 `llm_settings.json` 中管理。缓存 TTL 统一在 `data/config/config.json` → `cache_ttl` 中配置。

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
- 模型：`DeepSeek-V4-Flash`（推荐，当前主版本）、`deepseek-chat`（V3 旧版，功能受限）
- 官方文档：https://api-docs.deepseek.com/guides/anthropic_api
</details>

<details>
<summary><b>DeepSeek（OpenAI 兼容格式）</b></summary>

```json
{
  "provider": "openai",
  "api_key": "sk-your-deepseek-key",
  "model": "DeepSeek-V4-Flash",
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

### token 消耗参考（按 DeepSeek-V4-Flash 定价，CNY）

| 模块 | 输入 token | 输出 token | 单次费用参考 |
|------|-----------|-----------|-------------|
| 全球政经局势 | ~300-800 | ~300-600 | ~¥0.001-0.003 |
| 智囊团深度复盘 | ~800-2500 | ~1500-2500 | ~¥0.005-0.02 |
| 持仓体检报告 | ~500-1500 | ~800-1500 | ~¥0.002-0.008 |
| 穿透深度分析 | ~500-1500 | ~800-1500 | ~¥0.002-0.008 |
| 新闻关联 LLM（可选） | ~2000-4000 | ~600-1200 | ~¥0.003-0.01 |
| 五者合计（菜单 L + 新闻 LLM） | — | — | ~¥0.01-0.05/次 |

- 仅菜单 **L** 触发 LLM 调用，E / N / H / B 不会
- LLM 结果默认缓存 24 小时（全球政经局势/穿透深度分析）/ 2 小时（智囊团深度复盘/持仓体检报告）/ 1 小时（财经新闻热点与持仓关联分析），缓存有效期内反复按 L 不会重复扣费
- 持仓或指数数据变更时，关联的 LLM 缓存自动失效；也可通过菜单 [2] 更新持仓缓存主动清除所有 LLM 缓存
- 缓存时间可在 `data/config/config.json` → `cache_ttl` 中通过 `llm_global_macro` / `llm_expert_review` / `llm_health_check` / `llm_penetration_deep` / `llm_news_correlation` 自定义

### 完整模型定价表

代码内置所有支持模型的 Token 定价（货币单位 CNY，每百万 Token），`pricing` 段可自定义覆盖：

| 模型 | 输入 ¥/M | 输出 ¥/M | 缓存命中 ¥/M | 说明 |
|------|:--------:|:--------:|:------------:|------|
| `claude-sonnet-4-6` | 3.00 | 15.00 | 0.30 | Claude 主力模型，推荐日常使用 |
| `claude-sonnet-4-8` | 3.00 | 15.00 | 0.30 | Sonnet 升级版，同价 |
| `claude-haiku-4-5-20251001` | 0.25 | 1.25 | 0.025 | 轻量高性价比，适合新闻关联批量任务 |
| `claude-opus-4-6` | 15.00 | 75.00 | 1.50 | 强推理，适合智囊团等复杂分析 |
| `claude-opus-4-8` | 15.00 | 75.00 | 1.50 | Opus 升级版，同价 |
| `claude-fable-5` | 3.00 | 15.00 | 0.30 | 最新 Claude 模型 |
| `gpt-4o` | 2.50 | 10.00 | 2.50 | OpenAI 主力（缓存无折扣） |
| `gpt-4o-mini` | 0.15 | 0.60 | 0.15 | OpenAI 轻量（缓存无折扣） |
| `deepseek-v4-flash` | 1.00 | 2.00 | 0.02 | ⭐ 高性价比推荐，默认模型 |
| `deepseek-v4-pro` | 3.00 | 6.00 | 0.025 | DeepSeek 增强推理 |
| `deepseek-chat` | 1.00 | 2.00 | 0.02 | DeepSeek V3 旧版 |

> **起算关系**：上述价格为**每百万 Token**单价。单次调用费用 = `(输入 token × 输入单价 + 输出 token × 输出单价) / 1,000,000`。例如：
> - DeepSeek-V4-Flash：输入 3000 tokens × ¥1 + 输出 2000 tokens × ¥2 = ¥0.007/次（含输入约 ¥0.003/次）
> - 缓存命中时输入部分按 `input_cache_hit` 计费，大幅降低成本
>
> **自定义定价**：在 `llm_settings.json` 中添加 `pricing` 段即可覆盖任意模型的定价，未覆盖的模型自动使用上方内置价格。例如添加 `"claude-opus-4-8": {"input": 15, "output": 75}` 或新模型。

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
| 财经新闻（源2） | 东方财富 `np-weblist.eastmoney.com/comm/web/getFastNewsList` | — |
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

## 目录结构

```
investor-util/
├── src/
│   ├── __init__.py
│   ├── python/                   # 源代码
│   │   ├── __init__.py
│   │   ├── main.py               # 入口
│   │   ├── cache.py              # 缓存管理
│   │   ├── config.py             # 配置文件管理
│   │   ├── fetcher.py            # 数据获取路由
│   │   ├── llm_client.py         # LLM 客户端
│   │   ├── logger.py             # 日志模块
│   │   ├── models.py             # 数据模型
│   │   ├── reader.py             # 持仓读取
│   │   ├── tui.py                # TUI 主循环
│   │   ├── tui_menu.py           # 菜单交互
│   │   ├── tui_handlers.py       # 菜单功能执行
│   │   ├── providers/            # 数据源提供商
│   │   │   ├── __init__.py
│   │   │   ├── akshare_extras.py
│   │   │   ├── akshare_news.py
│   │   │   ├── cls_news.py
│   │   │   ├── eastmoney.py
│   │   │   ├── eastmoney_industry.py
│   │   │   ├── eastmoney_news.py
│   │   │   ├── news_aggregator.py
│   │   │   ├── news_correlator.py
│   │   │   ├── news_keywords.py
│   │   │   ├── news_sources.py
│   │   │   ├── sina.py
│   │   │   ├── sina_news.py
│   │   │   ├── tencent.py
│   │   │   ├── tiantian.py
│   │   │   └── wallstreetcn_news.py
│   │   ├── report/               # 报告生成
│   │   │   ├── __init__.py
│   │   │   ├── category.py
│   │   │   ├── excel_writer.py
│   │   │   ├── fund_performance.py
│   │   │   ├── html_writer.py
│   │   │   ├── llm_content.py
│   │   │   ├── market_value.py
│   │   │   ├── news_correlation.py
│   │   │   ├── penetration.py
│   │   │   ├── styles.py
│   │   │   └── summary.py
│   │   └── tmpl/
│   │       └── report_template.html
│   └── test/                     # 测试
│       ├── __init__.py
│       └── test_*.py (23 个)
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
├── README.md                     # 用户文档
└── requirements.txt
```

---

## 报告文件结构

### Excel 报告

| # | 页签 | 内容说明 |
|:--|------|----------|
| 1 | **1.投资分析汇总** | 当前时间、交易日、A 股/美股指数行情、总市值/成本/盈亏/本日盈亏、各账户小计、更新状态 |
| 2 | **2.市值核算明细表** | 15 列明细：账户、名称、代码、最新价、净值日期、昨日价、取价方式、溢价率、份额、市值、成本、盈亏、收益率、本日盈亏、取价渠道。取价方式蓝色标识（场内收盘价(T)→蓝、官方净值(T)→蓝、QDII 官方净值(T-1)→蓝），分账户小计+总计 |
| 3 | **3.分类汇总表** | 10 列：资产属性、投资分类、名称、代码、市值、成本、盈亏、收益率、本日盈亏、年均股息率。按资产属性和投资分类分组统计 |
| 4 | **4.资产穿透TOP10** | 10 列：排名、名称、代码、穿透市值、占比、板块、概念、预测EPS(2025E)、年均股息率、来源明细。基金拆解为底层标的合并排序，底部标注无法获取穿透数据的基金 |
| 5 | **5.基金业绩分析** | 12 列：基金、代码、类型、近3月/6月/12月收益率、累计盈亏(¥)、持仓收益率、业绩基准、业绩评价、同类排名、机构覆盖（研报家数+预测EPS）。业绩标色：优秀→红、稳定→蓝、偏差→绿 |
| 6 | **6.财经新闻热点与持仓关联分析**（菜单 N/B/L） | 5 源新闻与持仓关键词匹配结果，含标题、来源、时间、关联度。关联关键词按来源富化显示（持仓→蓝色、穿透→紫色、概念→橙色、行业→灰色），可选 LLM 二次关联分析 |
| 7 | **7.全球政经局势**（菜单 L） | LLM 基于指数行情和持仓结构生成的宏观分析 |
| 8 | **8.智囊团深度复盘**（菜单 L） | LLM 三阶段圆桌会议：召集令→辩论→定音锤，含调仓建议和风险预警 |
| 9 | **9.持仓体检报告**（菜单 L） | LLM 从风险分散度、流动性、收益合理性、成本结构四维度量化评分并给出改进建议 |
| 10 | **10.穿透深度分析**（菜单 L） | LLM 从行业集中度、国别/币种暴露角度生成深度分析，含行业集中度仪表盘和外汇风险敞口 |

### HTML 报告

单页渲染以上全部 10 个模块，响应式 CSS 自适应桌面/移动端。额外特性：
- 盈亏正数红色、负数绿色着色
- 取价方式蓝色标识（与 Excel 端规则一致）
- 新闻来源可点击跳转
- 基金业绩评价带颜色标签
- 页脚标注生成时间和版本号
- LLM 内容为条件渲染（仅菜单 L 时显示）

---

## 基金业绩评价标准

基金业绩分析采用 **三层计算逻辑**，数据来源于天天基金 API：

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
A: 菜单 `L` 会先检查缓存，缓存过期（默认全球政经局势/穿透深度分析 24h / 智囊团深度复盘/持仓体检报告 2h / 财经新闻热点与持仓关联分析 1h）或持仓/指数数据变更时才重新调用 LLM。如需强制刷新，先执行菜单 `[2]` 更新持仓缓存即可清除关联 LLM 缓存（智囊团深度复盘、全球政经局势、持仓体检报告、穿透深度分析均被清除）。

**Q: 报告数据感觉不完整？**
A: 先试菜单 `[1]` 更新基础缓存，再试 `[2]` 更新持仓缓存，最后重试生成报告。

**Q: 后续如何升级？**
A: 拉取最新代码后，重新运行启动脚本即可自动更新依赖。

**Q: 能否不配置 LLM 使用程序？**
A: 可以。菜单 E / N / H / B 全部不依赖 LLM，仅菜单 L 需要 LLM 配置。

**Q: 如何开启新闻 LLM 关联分析？**
A: 编辑 `data/config/llm_settings.json`，将 `enabled_llm_news_correlation` 设为 `true`，并确保 `llm_key.json` 已配置有效的 API Key。开启后菜单 N / B / L 生成的报告增加"LLM 关联分析"列，每条新闻获得 LLM 判定的关联度（高/中/低/无关）和原因分析。默认关闭以节省费用。

---

## 附录：新增 LLM 分析章节规范

增加新的 LLM 服务章节时，必须同步完成以下步骤：

1. **`llm_settings.json`** — 增加一整套配置键（10 个），命名格式为 `{key}_{module_name}`：
   - 必含：`system_prompt_{module}`、`model_{module}`、`temperature_{module}`、`max_tokens_{module}`、
     `timeout_{module}`、`cache_enabled_{module}`、`output_brief_{module}`、
     `thinking_enabled_{module}`、`thinking_budget_{module}`、`reasoning_effort_{module}`
2. **`llm_client.py`** — 添加 LLM 调用函数，使用 `llm_config.get("{key}_{module}")` 读取对应配置
3. **`llm_content.py`** — 在 `_MODULE_KEY_MAP` 中添加章节名→模块键映射；在 `write_llm_sheets()` 中添加新页签
4. **报告模板** — 在 Excel `tui_handlers.py` 和 HTML `html_writer.py` 中传递新章节的 model/thinking 参数
5. **页脚规范** — 章节内容底部 LLM 提示使用标准格式：
   `模型：{model} | Token 用量：输入 X / 输出 Y = Z | 估算费用：${cost} | Extended Thinking`
6. **缓存 TTL** — 在 `config.json` → `cache_ttl` 中添加 `llm_{module}` 条目，并在 `cache.py` → `prefix_type_map` / `_CACHE_TTL_DEFAULTS` 同步
7. **README** — 文档化新章节的配置项、推荐值、缓存策略

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
