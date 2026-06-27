# 投资分析报告生成系统

个人投资者辅助工具：读取 Excel 持仓信息，对接中国金融数据源获取实时行情，生成 **Excel / HTML** 格式的投资分析报告。

> 当前版本：0.2.6

---

## 功能特性

- **TUI 菜单操作** — 方向键导航 + 字母快捷键，交互友好
- **多账户支持** — Excel 每页工作表为一个独立账户，自动识别
- **实时行情获取** — 腾讯财经（场内实时价）、东方财富（场外基金净值）等多源备线
- **智能缓存** — API 响应按指定频率缓存，减少网络请求，支持手动刷新和缓存管理
- **Excel 报告** — 8 个功能页签：汇总、市值核算、分类汇总、资产穿透 TOP10、基金业绩分析、财经新闻热点、全球政经局势（LLM）、智囊团深度复盘（LLM）
- **HTML 报告** — 单页完整渲染（响应式 CSS、盈亏着色、新闻关联）
- **多源财经新闻** — 新浪财经 + 东方财富 + 财联社 3 源并行获取，去重后与持仓关键词关联
- **LLM 智能分析** — 支持 Claude / OpenAI / DeepSeek API，双模块并行调用，结果缓存 24 小时
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

### 示例数据

`data/holdings/` 目录下附带示例文件 `个人投资持仓信息.xlsx`，包含 4 个账户：
- **证券账户** — 场内股票/ETF
- **支付宝-基金投资账户** — 场外基金
- **微信-基金投资账户** — 债券基金
- **银行-基金投资账户** — QDII 基金

---

## 菜单操作

```
  > [E] 生成 EXCEL 分析报告（模块 1-5）
    [N] 生成包含新闻的 EXCEL 分析报告（模块 1-6）
    [H] 生成基础的 HTML 分析报告（模块 1-6）
    [B] 生成全系列包含新闻的报告（Excel + HTML）
    [L] 生成全系列完整版报告（含 LLM 模块 7-8）
    [C] 配置持仓信息目录
    [F] 配置持仓信息文件名
    [R] 配置报告输出目录
    [1] 更新基础缓存信息
    [2] 更新持仓相关缓存信息
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
  "preferred_provider": {},
  "cache_ttl": {
    "price": 86400,
    "index": 86400,
    "rank": 86400,
    "hold": 604800,
    "news": 86400,
    "benchmark": 2592000
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
| `preferred_provider` | `{}` | 优选数据源（预留字段） | 手动编辑 |
| `cache_ttl.*` | 见下方 | 各缓存类型有效期（秒） | 手动编辑 |

### cache_ttl 可调参数

| 子字段 | 默认 | 说明 |
|--------|------|------|
| `price` | 86400（24h） | 股票/基金最新价缓存 |
| `index` | 86400（24h） | 市场指数行情缓存 |
| `rank` | 86400（24h） | 基金同类排名+区间收益率 |
| `hold` | 604800（7天） | 基金前10大持仓明细 |
| `news` | 86400（24h） | 财经新闻缓存 |
| `benchmark` | 2592000（30天） | 业绩比较基准对照表 |

> **调整建议：** 盘中频繁刷新可将 `price` 改为 `3600`（1小时）；持仓变动少可将 `hold` 改为 `2592000`（30天）。

---

## LLM 配置指引

模块 7（全球政经局势）和模块 8（智囊团深度复盘）需调用外部 LLM API。API Key 独立存储于 `data/config/llm.json`，避免误提交到版本控制。

### 快速配置

1. 编辑 `data/config/llm.json`
2. 填入 provider 和 api_key
3. 启动程序，菜单选 **L** 生成完整版报告

```json
{
  "provider": "claude",
  "api_key": "sk-ant-xxxxxxxxxxxxx",
  "model": "claude-sonnet-4-6",
  "endpoint": "https://api.anthropic.com/v1/messages",
  "max_tokens": 2500,
  "system_prompt_macro": "你是一位资深宏观经济学家...",
  "system_prompt_expert": "你是投资智囊团召集人..."
}
```

### 字段全表

| 字段 | 必填 | 说明 |
|------|:----:|------|
| `provider` | ✅ | `"claude"`（Anthropic Messages API）或 `"openai"`（OpenAI Chat Completions） |
| `api_key` | ✅ | API 密钥，妥善保管勿提交 Git |
| `model` | — | 模型名称，留空使用 provider 默认值 |
| `endpoint` | — | API 端点 URL，留空使用官方端点 |
| `max_tokens` | — | 输出 token 上限（默认 2500） |
| `system_prompt_macro` | — | 模块 7 自定义系统提示词，留空使用内置默认值 |
| `system_prompt_expert` | — | 模块 8 自定义系统提示词，留空使用内置默认值 |

### 支持的 provider 及配置示例

<details>
<summary><b>Claude（Anthropic 官方）</b></summary>

```json
{
  "provider": "claude",
  "api_key": "sk-ant-your-key",
  "model": "claude-sonnet-4-6",
  "endpoint": "https://api.anthropic.com/v1/messages",
  "max_tokens": 2500
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
  "endpoint": "https://api.openai.com/v1/chat/completions",
  "max_tokens": 2500
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
  "endpoint": "https://api.deepseek.com/anthropic/v1/messages",
  "max_tokens": 8192
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
  "endpoint": "https://api.deepseek.com/v1/chat/completions",
  "max_tokens": 2500
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
  "endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
  "max_tokens": 2500
}
```

获取方式：火山引擎方舟控制台 → 推理接入点 → 创建接入点。
</details>

### token 消耗参考

| 模块 | 输入 token | 输出 token | 单次费用参考 |
|------|-----------|-----------|-------------|
| 模块 7（全球政经） | ~300-800 | ~300-600 | ~$0.005-0.015 |
| 模块 8（智囊团） | ~800-2500 | ~1500-2500 | ~$0.02-0.05 |
| 两者合计（菜单 L） | — | — | ~$0.03-0.06/次 |

- 仅菜单 **L** 触发 LLM 调用，E / N / H / B 不会
- LLM 结果缓存 24 小时，同一天反复按 L 不会重复扣费
- 菜单 L 已内置 `force=True`，每次强制刷新 LLM 内容

### 不配置 LLM 时的行为

`llm.json` 缺失或 key 为空时，程序不崩溃，其他功能正常。对应报告页签显示占位提示：
```
本节内容待生成 — 请配置 LLM API Key（data/config/llm.json）
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
| A 股指数 | 腾讯财经 `qt.gtimg.cn` | — |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS 变量解析） | — |

---

## 缓存文件指引

所有缓存文件存放于 `data/cache/` 目录，JSON 格式，自动管理过期时间。

### 单条缓存（引擎自动管理）

| 文件名模式 | 用途 | 有效期 |
|-----------|------|--------|
| `price_{code}.json` | 单只股票/基金最新价、昨收、净值日期 | 24h |
| `index_{code}.json` | A 股/美股指数行情 | 24h |
| `fund_perf_{code}.json` | 基金同类排名+区间收益率 | 24h |
| `fund_hold_{code}.json` | 基金前 10 持仓明细 | 7 天 |
| `news_*.json` | 财经新闻数据（多源去重合并） | 24h |
| `llm_*` | LLM 分析结果缓存 | 24h |

### 合并缓存（菜单手动触发）

| 文件名 | 用途 | 触发方式 |
|--------|------|----------|
| `fund_benchmarks.json` | 业绩比较基准对照表 | 菜单 [1] |
| `portfolio_latest.json` | 持仓主数据快照 | 菜单 [2] |
| `penetration_cache.json` | 资产穿透 TOP10 计算结果 | 菜单 [2] |
| `holdings_tracking.json` | 持仓指纹跟踪（变更检测） | 自动 |

### 缓存管理菜单

| 菜单 | 功能 |
|------|------|
| `[1] 更新基础缓存` | 刷新基金业绩排名、持仓、基准 |
| `[2] 更新持仓相关缓存` | 清空价格缓存、重新获取行情和穿透数据 |
| `[3] 清理过期缓存文件` | 删除超过各自 TTL 的缓存 |
| `[4] 查看缓存统计信息` | 显示缓存总数/大小/按前缀分类 |

### 降级规则

缓存过期但 API 请求失败时，返回最近 7 天内的过期缓存数据而非报错。缓存文件损坏时自动删除并触发重新获取。

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
│   ├── test_*.py                 # 单元测试（14 个模块，491 项）
│   ├── providers/                # API 供应商
│   │   ├── tencent.py            # 腾讯财经（实时价、指数）
│   │   ├── eastmoney.py          # 东方财富（基金净值）
│   │   ├── tiantian.py           # 天天基金（业绩排名、持仓）
│   │   ├── sina.py               # 新浪财经（美股指数）
│   │   ├── sina_news.py          # 新浪财经（新闻）
│   │   ├── eastmoney_news.py     # 东方财富（新闻）
│   │   ├── cls_news.py           # 财联社（新闻）
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
│   └── config/                   # 配置文件（config.json, llm.json）
├── reports/                      # 生成报告（最新版+按日期存档）
├── logs/                         # 程序日志（app.log）
├── docs-stm/                     # 项目管理文档
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
| 2 | **市值核算** | 15 列明细：账户、名称、代码、最新价、净值日期、昨日价、取价方式、溢价率、份额、市值、成本、盈亏、收益率、本日盈亏、取价渠道。分账户小计+总计 |
| 3 | **分类汇总** | 按资产属性（股票/ETF/基金）和投资分类（沪市/深市/指数/债券等）分组统计市值和盈亏 |
| 4 | **资产穿透 TOP10** | 7 列明细：排名、名称、代码、穿透市值、占比、板块、来源明细。基金拆解为底层标的合并排序，底部标注无法获取穿透数据的基金 |
| 5 | **基金业绩分析** | 11 列：基金、代码、类型、近3月/6月/12月收益率、累计盈亏(¥)、持仓收益率、业绩基准、业绩评价、同类排名。业绩标色：优秀→红、稳定→蓝、偏差→绿 |
| 6 | **财经新闻热点**（菜单 N/B/L） | 3 源新闻与持仓关键词匹配结果，含标题、来源、时间、关联度 |
| 7 | **全球政经局势**（菜单 L） | LLM 基于指数行情和持仓结构生成的宏观分析 |
| 8 | **智囊团深度复盘**（菜单 L） | LLM 三阶段圆桌会议：召集令→辩论→定音锤，含调仓建议和风险预警 |

### HTML 报告

单页渲染以上全部模块（模块 1-8），响应式 CSS 自适应桌面/移动端。额外特性：
- 盈亏正数红色、负数绿色着色
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
A: 菜单 `L` 已内置强制刷新逻辑，每次生成都会重新调用 LLM 并更新缓存。

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
