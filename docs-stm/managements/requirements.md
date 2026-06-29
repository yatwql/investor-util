# 投资分析报告小工具 — 需求文档

创建日期：2026-06-26
最后更新：2026-06-29
来源：`投资分析应用-需求.txt`

---

## 1. 运行环境与源代码要求

- R-ENV1. 基础源代码基于 Python 编写
- R-ENV2. Windows 11 使用 PowerShell 脚本启动，支持直接调用 Python 源代码或启动 TUI 界面
- R-ENV3. Linux 使用 Bash 脚本启动，支持直接调用 Python 源代码或启动 TUI 界面

---

## 2. TUI 界面

- R-TUI1. 启动后显示标题"投资分析报告生成系统"
- R-TUI2. 显示以下 13 个选项供用户选择：

| 选项 | 功能 | 说明 |
|---|---|---|
| E | 生成基础版Excel分析报告 | 读取持仓信息生成 Excel 报告（必选模块 1-5） |
| N | 生成包含新闻的Excel分析报告 | 生成 Excel 报告 + 财经新闻关联增补页签（模块 6） |
| H | 生成基础版HTML分析报告 | 读取持仓信息生成 HTML 报告，不含 LLM 增补内容（模块 1-6） |
| B | 生成全系列包含新闻的报告(Excel+HTML) | 同时生成 HTML + 含新闻的 Excel 报告，不含 LLM 增补内容（模块 1-6） |
| L | 生成全系列完整版报告(Excel+HTML) | 同时生成 HTML + Excel，含新闻、模块 7-10 LLM 增补内容（模块 1-10） |
| C | 配置持仓信息目录 | 配置持仓文件的存放目录 |
| F | 配置持仓信息文件名 | 配置持仓文件的文件名 |
| R | 配置报告输出目录 | 配置报告文件的输出目录（默认 reports） |
| 1 | 更新基础类缓存 | 主动更新基金业绩/持仓/基准/新闻/盈利预测/行业资金流向/分红缓存（含 news_、llm_news_correlation_、profit_forecast_、sector_flow_、dividend_） |
| 2 | 更新持仓类缓存 | 主动更新价格/指数行情，清除关联 LLM 缓存 |
| 3 | 清理过期缓存文件 | 扫描 data/cache/ 目录，删除已过期的缓存文件 |
| 4 | 查看缓存统计信息 | 显示缓存文件总数/大小/按前缀分类/过期预览 |
| X | 退出 | 退出程序 |

- R-TUI3. E/N/H/B/L 操作流程：
  - 持仓目录下有多个 xlsx 文件时，弹出选择器要求用户选择其中一个
  - 持仓目录不存在或目录下没有 xlsx 文件时，弹出选择器要求配置持仓目录

---

## 3. 持仓文件格式

持仓 xlsx 文件格式固定：

- 每个页签 = 一个账户，页签名即账户名（如"证券账户""支付宝-余利宝账户"）
- 每个页签固定 4 列：名称（str）、代码（str）、持仓份额（float）、每份成本（float）
- 列名固定，不需要用户配置映射

---

## 4. 数据源

| 用途 | 主链路 | 备用链路 |
|---|---|---|
| 场内实时/收盘价 | 腾讯财经 `qt.gtimg.cn` | 东方财富 `push2.eastmoney.com` |
| 场外官方净值 | 东方财富 `fundf.eastmoney.com` | 天天基金 `fundgz.1234567.com.cn` |
| 基金持仓数据 | 天天基金 `fundf10.eastmoney.com` | — |
| 基金业绩排名 | 天天基金 JS 变量解析 | — |
| 财经新闻 | 5 源并行：新浪/东方财富/财联社/华尔街见闻/akshare | — |
| 市场指数（A股） | 腾讯财经 `qt.gtimg.cn` | — |
| 美股指数 | 新浪财经 `hq.sinajs.cn`（JS变量解析） | — |
| 行业分类/概念板块 | 东方财富 `push2.eastmoney.com` | — |

> 各新闻源的完整端点格式见 [README.md](../README.md#数据源一览)。

---

## 5. 缓存策略

缓存统一存放在 `data/cache/` 目录，采用 JSON 格式，由 `src/python/cache.py` 提供泛用键值对存储接口。缓存分为三个层级，各有不同的生命周期和刷新策略。

### 5.1 缓存文件清单及命名规则

#### 合并缓存文件（菜单手动生成 + 自动管理）

| 文件名 | 使用目的 | 有效期限 | 刷新方式 |
|---|---|---|---|
| `fund_benchmarks.json` | 业绩比较基准对照表——每只基金的比较基准名称 | 30 天 | 自动 + [1] 刷新；持仓变更时自动清除 |
| `holdings_tracking.json` | 持仓指纹跟踪——MD5 指纹 + 代码集合，用于变更检测 | 永久，随持仓更新 | 每次检测持仓变化后自动更新 |

#### 单条缓存文件（引擎自动管理）

命名规则：`{类型前缀}_{证券代码}.json` 或 `{类型前缀}_{特征值}.json`

| 文件名模式 | 使用目的 | 默认 TTL |
|---|---|---|
| `price_{code}.json` | **单只股票/基金的最新价、昨收盘、净值日期**。fetcher 自动读写，需区分场内/场外取价链路。文件如 `price_600900.json` | 24 小时 |
| `index_{code}.json` | **A股/美股市场指数行情**（指数名称、最新价、涨跌幅）。文件如 `index_sh000001.json` | 24 小时 |
| `fund_perf_{code}.json` | **单只基金同类排名和区间收益率**（近3月/近6月/近1年），含同类排名百分位、超额收益评分。文件如 `fund_perf_000961.json` | 24 小时 |
| `fund_hold_{code}.json` | **单只基金的前10大持仓明细**（名称、代码、持仓比例），用于穿透分析和板块分类。文件如 `fund_hold_012325.json` | 7 天 |
| `industry_{code}.json` | **单只证券的行业分类和概念板块归属**（三级行业名称 + 概念板块列表），用于新闻关键词富化和穿透板块补充。文件如 `industry_600900.json` | 7 天 |
| `llm_global_macro_{fingerprint}.json` | **全球政经局势 LLM 分析结果**。文件名含指数行情 + 持仓汇总的 MD5 指纹；指数或持仓变化时原缓存自动失效 | 24 小时（可配置） |
| `llm_expert_review_{fingerprint}.json` | **智囊团深度复盘 LLM 分析结果**。文件名含持仓汇总+分类+穿透+持仓明细（名称/代码/成本）的 MD5 指纹，剔除单品行情波动字段（change_pct/实时价）；持仓品种或成本变化时原缓存自动失效，单纯行情波动不影响 | 2 小时（可配置） |
| `llm_health_check_{fingerprint}.json` | **持仓体检报告 LLM 分析结果**。同智囊团指纹策略，排除行情波动字段。四维度打分+改进建议 | 2 小时（可配置） |
| `llm_penetration_deep_{fingerprint}.json` | **穿透深度分析 LLM 分析结果**。行业集中度+品种集中度+国别/币种暴露，排除行情波动字段 | 24 小时（可配置） |
| `news_{md5}.json` | **多源新闻聚合结果**。5 源（新浪/东方财富/财联社/华尔街见闻/akshare）并行获取后去重、关键词关联、排序。文件名含输入参数 MD5 指纹，参数变化时自动失效 | 15 分钟（可配置） |
| `llm_news_correlation_{fingerprint}.json` | **LLM 新闻关联分析结果**。对关键词匹配后的新闻逐条做 LLM 关联度判定（高/中/低/无关），文件名含输入参数 MD5 指纹，参数变化时自动失效 | 1 小时（可配置） |
| `llm_news_item_{fingerprint}.json` | **LLM 新闻逐条缓存**。每篇新闻文章的独立 LLM 关联分析结果（关联度+情绪+分析），指纹基于标题前 80 字+持仓指纹，新文章仅新增文件的缓存缺失 | 1 小时（可配置，与 llm_news_correlation 同 TTL） |
| `profit_forecast_{fingerprint}.json` | **机构盈利预测全量数据**。调用 akshare 获取所有股票的研报覆盖、预测 EPS、机构评级。文件名含指数 MD5 指纹，指数变化时自动失效 | 24 小时（可配置） |
| `sector_flow_{fingerprint}.json` | **行业资金流向排名**。今日行业资金流向（主力净流入/涨跌幅等）。文件名含指数 MD5 指纹，指数变化时自动失效 | 15 分钟（可配置） |
| `dividend_{fingerprint}.json` | **股票历史分红数据**。持仓及穿透 TOP10 A 股代码的历年分红汇总。文件名含代码列表 MD5 指纹，持仓/穿透变化时自动失效 | 30 天（可配置） |

### 5.2 指纹驱动失效机制

以下缓存文件在文件名中**内嵌 MD5 指纹**。当指纹的输入源数据发生变化时，下次读取时的缓存键与已有文件不匹配，等效于"缓存未命中"，自动使用新数据。**无需手动清除缓存即可刷新。**

#### 指纹类型总览

| 指纹类型 | 指纹来源 | 用途 | 所在缓存文件 |
|---------|---------|------|------------|
| **指数指纹** | A股指数 + 美股指数（`_compute_index_fingerprint`） | 市场指数变化时失效 | `profit_forecast_{fingerprint}`、`sector_flow_{fingerprint}` |
| **代码列表指纹** | 持仓+穿透 A 股代码排序后的 MD5（`_compute_dividend_fingerprint`） | 持仓/穿透品种变化时失效 | `dividend_{fingerprint}` |
| **输入参数指纹** | 新闻源参数 + 关键词的 MD5（`_compute_fingerprint`） | 新闻参数或持仓变化时失效 | `news_{md5}` |
| **输入数据指纹** | 指数+持仓汇总/持仓结构等（`_compute_fingerprint` / `_expert_fingerprint` / `_health_check_fingerprint` / `_penetration_deep_fingerprint`） | 指数波动/持仓变化时失效 | `llm_global_macro_{fingerprint}`、`llm_expert_review_{fingerprint}`、`llm_news_correlation_{fingerprint}`、`llm_health_check_{fingerprint}`、`llm_penetration_deep_{fingerprint}` |

#### 各指纹的详细构成

- **指数指纹**：`json.dumps([a_indices, us_indices])` → MD5 前 12 位。A 股 5 大指数 + 美股 3 大指数任一变化 → 指纹改变 → profit_forecast/sector_flow 缓存自动失效
- **代码列表指纹**：`json.dumps(sorted(set(codes)))` → MD5 前 12 位。持仓文件新增/移除了 A 股代码、或穿透 TOP10 发生变化 → 指纹改变 → dividend 缓存自动失效
- **全球政经局势指纹**：A 股/美股指数行情 + 持仓汇总（总市值/总成本/总盈亏/分类）→ `_compute_fingerprint()` 生成
- **智囊团深度复盘指纹**：持仓汇总（总市值/总成本/总盈亏/本日盈亏）+ 分类计数 + 穿透 TOP10 + 持仓明细（名称/代码/成本），剔除单品行情波动字段（market_value/profit/change_pct），仅品种/份额/成本变化才会失效
- **持仓体检报告指纹**：同智囊团策略，排除行情波动字段 → `_health_check_fingerprint()` 生成
- **穿透深度分析指纹**：同智囊团策略，排除行情波动字段 → `_penetration_deep_fingerprint()` 生成
- **LLM 新闻关联分析指纹**：关键词 + 持仓汇总 → `_compute_fingerprint()` 生成
- **新闻聚合指纹**：新闻源参数 + 关键词集合 → `hashlib.md5` 生成，`{md5}` 为完整 32 位指纹

**TTL 兜底：** 即使指纹未变（源数据无变化），缓存文件仍有 TTL 到期自动刷新，防止数据"永久有效"。

**无指纹（固定键名）的缓存：** `price_{code}`、`index_{code}`、`fund_perf_{code}`、`fund_hold_{code}`、`industry_{code}`、`fund_benchmarks`、`holdings_tracking` — 纯 TTL 管理。`holdings_tracking` 内部存了指纹用于变更检测，但键名本身固定。`llm_*`（通用 LLM 缓存兜底）也无指纹，仅在其他 LLM 类型未匹配时生效。

### 5.3 主动失效链路（自动触发）

以下场景会**自动**触发相关缓存失效，无需用户进入菜单：

1. **持仓文件发生变更**（新增品种/清仓/修改份额）：
   - `check_and_refresh_caches()` 检测到 MD5 指纹变化
   - 自动清除关联的 `fund_benchmarks.json` 和 `industry_*` 缓存
   - 新增资产的 `price_*`、`fund_perf_*`、`fund_hold_*`、`industry_*` 自动预热（避免首次取价延迟）
   - 更新 `holdings_tracking.json` 中的指纹和代码集合
2. **LLM 缓存指纹失效**：
   - 全球政经局势：指数行情或持仓汇总数据变化后，指纹与旧缓存不匹配
   - 智囊团深度复盘：持仓品种/份额/成本变化后指纹自动失效；单品行情波动（价格/涨跌幅）不影响
   - 下次生成 L 菜单时自然使用新数据
3. **菜单 [2] 主动清除**：
   - 同时清除 `llm_expert_review_*`（智囊团）和 `llm_global_macro_*`（全球政经）缓存
   - 确保下次 L 菜单强制使用最新数据

### 5.4 TTL 常量对照表

| 类别 | 数据类型键 | 默认 TTL | 对应缓存文件 | 指纹 |
|---|---|---|---|---|
| 价格行情 | `price` | 86400 秒（24 小时） | `price_{code}.json` | — |
| 市场指数 | `index` | 86400 秒（24 小时） | `index_{code}.json` | — |
| 基金业绩 | `rank` | 86400 秒（24 小时） | `fund_perf_{code}.json` | — |
| 持仓数据 | `hold` | 604800 秒（7 天） | `fund_hold_{code}.json` | — |
| 行业分类 | `industry` | 604800 秒（7 天） | `industry_{code}.json` | — |
| 新闻聚合 | `news` | 900 秒（15 分钟） | `news_{md5}.json` | 输入参数指纹 |
| 新闻 LLM 关联分析 | `llm_news_correlation` | 3600 秒（1 小时） | `llm_news_correlation_{fingerprint}.json` | 输入数据指纹 |
| LLM 全局（通用） | `llm` | 86400 秒（24 小时） | `llm_*` | —（兜底） |
| 全球政经局势（LLM） | `llm_global_macro` | 86400 秒（24 小时） | `llm_global_macro_{fingerprint}.json` | 指数+持仓指纹 |
| 智囊团深度复盘（LLM） | `llm_expert_review` | 7200 秒（2 小时） | `llm_expert_review_{fingerprint}.json` | 持仓结构指纹 |
| 持仓体检报告（LLM） | `llm_health_check` | 7200 秒（2 小时） | `llm_health_check_{fingerprint}.json` | 持仓结构指纹 |
| 穿透深度分析（LLM） | `llm_penetration_deep` | 86400 秒（24 小时） | `llm_penetration_deep_{fingerprint}.json` | 持仓结构指纹 |
| 基准数据 | `benchmark` | 2592000 秒（30 天） | `fund_benchmarks.json` | — |
| 机构盈利预测 | `profit_forecast` | 86400 秒（24 小时） | `profit_forecast_{fingerprint}.json` | 指数指纹 |
| 行业资金流向 | `sector_flow` | 900 秒（15 分钟） | `sector_flow_{fingerprint}.json` | 指数指纹 |
| 股票历史分红 | `dividend` | 2592000 秒（30 天） | `dividend_{fingerprint}.json` | 代码列表指纹 |

**TTL 优先级链（按优先级从高到低）：**
1. `config.json` 中的 `cache_ttl.<data_type>`
2. 代码内置默认值（如上表）

### 5.5 手动刷新

| 菜单 | 功能 | 清除范围 |
|---|---|---|
| `[1] 更新基础类缓存` | 主动刷新基金业绩排名、持仓明细、业绩基准、行业分类、新闻、新闻 LLM 关联分析、盈利预测、行业资金流向、分红数据 | `fund_perf_*`、`fund_hold_*`、`fund_benchmarks.json`、`industry_*`、`news_*`、`llm_news_correlation_*`、`llm_news_item_*`、`profit_forecast_*`、`sector_flow_*`、`dividend_*` |
| `[2] 更新持仓类缓存` | 主动刷新价格/指数行情，并清除关联 LLM 缓存 | `price_*`、`index_*`、`llm_expert_review_*`、`llm_global_macro_*`、`llm_health_check_*`、`llm_penetration_deep_*` |
| `[3] 清理过期缓存文件` | 扫描全目录，按文件名前缀匹配各自 TTL，删除过期文件 | 全部过期缓存 |
| `[4] 查看缓存统计信息` | 显示缓存总数/总大小/按前缀分类统计 | 只读不删 |

### 5.6 降级规则

缓存过期但 API 请求失败时使用最近 **7 天内**的过期缓存数据；缓存文件损坏时自动删除并触发重新获取。详细降级设计见 [plan.md](plan.md)。

---

## 6. 输出文件要求

### 6.1 文件命名

| 类型 | 最新文件 | 存档文件 |
|---|---|---|
| Excel | `个人投资分析报告.xlsx` | `个人投资分析报告-<YYYYMMDD>-<HHmmss>.xlsx` |
| HTML | `个人投资分析报告.html` | `个人投资分析报告-<YYYYMMDD>-<HHmmss>.html` |

最新文件存放到 `output_dir` 根目录（默认为 `reports/`，可通过菜单 R 或 `data/config/config.json` 中的 `output_dir` 字段配置），存档文件存放到 `{output_dir}/<YYYYMMDD>/` 子目录。

### 6.2 输出内容

#### 模块 1：汇总（Excel + HTML）

显示当前日期和时间、所属交易日、当日 A 股指数、美股指数、总市值、总成本、总盈亏、本日盈亏。

#### 模块 2：核算市值（Excel + HTML）

15 列明细表：

| # | 列名 | 说明 |
|---|---|---|
| 1 | 账户 | 证券/支付宝/微信/谱蓝 |
| 2 | 名称 | 资产全称 |
| 3 | 代码 | 6 位代码 |
| 4 | 最新价 | 当前价格/净值 |
| 5 | 净值日期 | 具体日期如 2026-06-23 |
| 6 | 昨日价 | 前一日收盘价/净值 |
| 7 | 取价方式 | 场内实时价/场内收盘价/官方净值(T)/官方净值(T-1) |
| 8 | 溢价率 | 对 QDII 基金显示 |
| 9 | 份额 | 持仓数量 |
| 10 | 市值 | 价格 × 份额 |
| 11 | 成本 | 成本价 × 份额 |
| 12 | 盈亏 | 累计盈亏（市值 - 成本） |
| 13 | 收益率 | 累计收益率 |
| 14 | 本日盈亏 | 仅场内品种计算，场外非当日更新标 0 |
| 15 | 取价渠道 | 腾讯财经/天天基金网 |

分账户小计在该账户所属资产下立即显示，总计在最后。盈亏正数红色，负数绿色。

**取价方式蓝色标识规则：** 当取价方式表明价格数据时效性高/可靠时，该字段字体以蓝色（`#0066CC`）标识：
- 场内产品取价方式为 `场内收盘价(T)`（净值日期 == 所属交易日）→ 蓝色
- 国内场外基金取价方式为 `官方净值(T)`（净值日期 == 所属交易日）→ 蓝色
- QDII 基金取价方式为 `官方净值(T-1)`（净值日期 == 前一交易日）→ 蓝色
- Excel 和 HTML 两端的报告格式均适用此规则

**本日盈亏计算逻辑：**
- 场内（交易时段）：(实时价 - 昨收盘) × 份额
- 场内（非交易时段）：(收盘价 - 昨收盘) × 份额
- 国内场外：净值日期 == 当天 → (当日净值 - 前日净值) × 份额；否则 0
- QDII：净值日期 == T-1 → (当日净值 - 前日净值) × 份额；否则 0

#### 模块 3：分类汇总（Excel + HTML）

按资产属性 + 按投资分类进行分组汇总。10 列明细：资产属性 | 投资分类 | 名称 | 代码 | 市值 | 成本 | 盈亏 | 收益率 | 本日盈亏 | 年均股息率（持仓 A 股的年均股息/最新价 × 100%）。

#### 模块 4：资产穿透 TOP10（Excel + HTML）

所有基金拆分为前 10 大持仓成分股：
- 债券基金 → 具体债券品种
- QDII → 具体美股（季报数据）
- 主动权益基金 → 前 10 大持仓
- ETF → 前 10 大成分股/黄金现货
- 场外指数联接 → 前 10 大成分股

合并直接持有股票，相同资产合并市值，排序取 TOP10。
10 列明细：排名 | 名称 | 代码 | 穿透市值 | 占比 | 板块 | **概念** | **预测EPS(2025E)** | **年均股息率** | 来源明细。
底部标注未计入 TOP10 的市值金额和无法获取穿透数据的基金明细（名称+代码）。

**板块分类增强（v0.2.11+）：** 在关键词映射分类基础上，额外调用东方财富 push2 API 获取三级行业分类，作为板块列的补充数据源。当 API 返回的行业数据可用时，优先使用 API 数据覆盖板块列。覆盖静态关键词映射的局限，提高新/偏门股票的板块识别率。

#### 模块 5：基金业绩分析（Excel + HTML）

12 列表格：基金 | 代码 | 类型 | 近3月 | 近6月 | 近12月 | 持仓累计盈亏(¥) | 持仓收益率 | 业绩基准 | 业绩评价 | 同类排名 | 机构覆盖（研报家数 + 预测 EPS）

- **类型**：使用穿透分类逻辑自动标注（场内ETF / 场外主动型基金 / 场外指数基金 / 场外QDII基金 / 场外债券基金）
- **累计盈亏(¥)**：持仓累计盈亏 = 市值 − 成本（来自估值明细）
- **收益率**：累计收益率 = 盈亏 / 成本（来自估值明细）

**业绩评价标签标准（三层计算逻辑）：**

**第 1 层：基础评级** — 基于同类排名百分位，数据来源于天天基金 API（`Data_rateInSimilarPersent`）：

| 排名百分位 | 基础标签 |
|---|---|
| ≤ 20%（前 1/5） | 优秀 |
| 20% ~ 30% | 良好 |
| 30% ~ 50% | 稳定 |
| > 50%（后 1/2） | 偏差 |

API 无百分位数据时降级使用排名/总数折算百分位。

**第 2 层：超额收益修正** — 基于 `Data_performanceEvaluation` 中的超额收益评分：

| 超额收益评分 | 修正规则 |
|---|---|
| ≥ 80 | 基础评级上调一级（如 良好 → 优秀） |
| 40 ~ 80 | 不调整，维持基础评级 |
| < 40 | 基础评级下调一级（如 稳定 → 偏差） |

**第 3 层：显示文本** — 标签转换为带说明的字符串：

| 最终标签 | 显示文本 | Excel/HTML标色 |
|---|---|---|
| 优秀 | "优秀 持续跑赢基准，超额收益显著" | 红色 (#CC0000) |
| 良好 | "良好 稳定跑赢基准，组合管理得当" | 默认 |
| 稳定 | "稳定 收益率稳健，波动控制良好" | 蓝色 (#0066CC) |
| 偏差 | "偏差 近期表现欠佳，需关注持仓变化" | 绿色 (#009900) |

**同类排名**：格式为"排名/总数"，如"23/156"。排名和总数来源于 API 返回的 `Data_rateInSimilarType` 最近一期数据。

#### 模块 6：财经新闻热点与持仓关联分析（Excel + HTML）

分析财经新闻热点，与持仓名称/代码及穿透TOP10底层资产进行关键词匹配，输出 TOP N 新闻（N 通过 `data/config/config.json` 中的 `news_top_count` 配置，默认 100）。

关键词来源：
- 直接持仓的名称（清理基金后缀后的中文关键词）和代码
- 穿透 TOP10 底层资产的名称和代码（需先计算穿透数据）
- 东方财富三级行业名称和概念板块名称（自动从 API 获取，用于扩展关键词匹配范围）

新闻来源（5 个财经源并行获取、去重后排序）：
1. **新浪财经** — `feed.mix.sina.com.cn`（财经要闻/国内财经/国际财经 3 分类）
2. **东方财富** — `np-weblist.eastmoney.com/comm/web/getFastNewsList`（快讯接口 JSON）
3. **财联社** — `www.cls.cn/v1/roll/get_roll_list`（7x24 实时财经快讯）
4. **华尔街见闻** — `api-one.wallstcn.com/apiv1/content/lives`（全球财经直播流，无需鉴权）
5. **akshare** — 封装财新网 `stock_news_main_cx()` 和 CCTV `news_cctv()`，开源库自动适配底层 API

关联规则：对每条新闻的 title + intro 与关键词全集做子串匹配，按匹配到的关键词数量降序排列，去重后输出 TOP N。

**关键词富化（v0.2.10+）：** 关联关键词列支持富化显示 —— 自动识别每个关键词的来源类型：
- **持仓**（`长江电力(600900)`）— 匹配到直接持仓的名称或代码
- **穿透**（`腾讯控股[穿透]`）— 匹配到穿透 TOP10 底层资产
- **概念**（`CPO光模块[概念]`）— 匹配到东方财富行业分类或概念板块名称
- **行业**（`电力`）— 匹配持仓/穿透/概念之外的新闻热词

富化后关键词按 持仓→穿透→概念→行业 顺序排列，在 Excel 中以格式化字符串显示，在 HTML 中以不同颜色标签区分（持仓→蓝色、穿透→紫色、概念→橙色、行业→灰色）。

**LLM 关联分析（可选，v0.2.9+）：** `data/config/llm_settings.json` 中 `enabled_llm_news_correlation` 为 `true` 时自动开启，对关键词匹配后的新闻逐条进行二次关联判定：每条新闻获得 LLM 生成的关联度（高/中/低/无关）并附加原因分析。分析结果写入 "LLM 关联分析" 列（仅在有分析数据时显示列头）。

**Excel 格式优化（v0.2.10+）：** 新闻标题列宽 40、摘要列宽 50，启用文本换行 + 左对齐，长文本自动换行适应内容。

- **Excel**：通过菜单 N/B/L 生成增补页签（财经新闻热点表）
- **HTML**：自动渲染在报告第 6 节（来源标注为"新浪财经"/"东方财富"/"财联社"/"华尔街见闻"/"akshare"）

##### 模块 7：全球政经局势（Excel + HTML，分阶段实现 — LLM 增补项目）

在有 LLM 支持下的增补内容。
- **Phase 1（Iter 3.3）**：模板占位文本输出，预留接口
- **Phase 2（Iter 3.4）**：LLM 基于市场数据和持仓结构生成宏观分析（HTML ✅ 已实现，Excel ✅ 已实现）
- **Excel**：通过菜单 L 生成增补页签 ✅
- **HTML**：通过菜单 L 渲染在报告第 7 节 ✅

#### 模块 8：智囊团深度复盘（Excel + HTML，分阶段实现 — LLM 增补项目）

在有 LLM 支持下的增补内容。
- **Phase 1（Iter 3.3）**：模板占位文本输出，预留接口
- **Phase 2（Iter 3.4）**：LLM 基于持仓明细和盈亏数据生成优化建议和风险预警（HTML ✅ 已实现，Excel ✅ 已实现）
- **Excel**：通过菜单 L 生成增补页签 ✅
- **HTML**：通过菜单 L 渲染在报告第 8 节 ✅

#### 模块 9：持仓体检报告（Excel + HTML — LLM 增补项目，v0.2.29+）

在有 LLM 支持下的增补内容。从风险分散度、流动性、收益合理性、成本结构四个维度
对投资组合进行量化打分（每项满分 100）并给出改进建议。

- **Excel**：通过菜单 L 生成「9.持仓体检报告」页签 ✅
- **HTML**：通过菜单 L 渲染在报告第 9 节 ✅

**生成逻辑：** `generate_health_check()` 复用现有持仓数据（市值核算明细 + 穿透 TOP10 +
分类计数），缓存策略同智囊团（2 小时 TTL，指纹排除行情波动字段）。每个维度独立评分，
最终输出综合评分和评级（优/良/中/差）及 3-5 条具体可操作建议。

**配置项：** `llm_settings.json` 中 `model_health_check` / `temperature_health_check`（默认 0.5）/
`max_tokens_health_check`（默认 4096）/ `thinking_enabled_health_check`（默认 true）/
`thinking_budget_health_check`（默认 12000）

#### 模块 10：穿透深度分析（Excel + HTML — LLM 增补项目，v0.2.30+）

在有 LLM 支持下的增补内容。从行业集中度、国别/币种暴露角度对投资组合进行深度分析。

- **行业集中度仪表盘**：基于现有穿透 + 行业分类数据，计算占净值比重最大的前 N 行业，
  当某行业占比 > 30% 时标注集中度风险
- **国别/币种暴露**：QDII/港股通/美股/A 股按币种分类，计算外汇风险敞口百分比，
  输出分散化建议
- **Excel**：通过菜单 L 生成「10.穿透深度分析」页签 ✅
- **HTML**：通过菜单 L 渲染在报告第 10 节 ✅

**生成逻辑：** `generate_penetration_deep_analysis()` 复用穿透 TOP10 + 行业分类数据，
计算行业集中度和国别/币种暴露度。缓存策略 24 小时 TTL，指纹排除行情波动字段。
每个维度输出分析和建议。

**配置项：** `llm_settings.json` 中 `model_penetration_deep` / `temperature_penetration_deep`（默认 0.5）/
`max_tokens_penetration_deep`（默认 4096）/ `thinking_enabled_penetration_deep`（默认 false）/
`thinking_budget_penetration_deep`（默认 12000）

---

## 7. LLM 智能分析

详见 [plan.md](plan.md)「关键技术决策」和「当前配置架构」章节。

用户配置指南详见根目录 [README.md](../README.md)「LLM 配置指引」章节。

**逐章节模型路由（v0.2.17+）：** 支持对全球政经局势、智囊团深度复盘、新闻关联分析、持仓体检报告、穿透深度分析五个 LLM 章节分别指定不同的模型。通过 `data/config/llm_settings.json` 中的 `model_global_macro`、`model_expert_review`、`model_news_correlation`、`model_health_check`、`model_penetration_deep` 字段设置，为 `null` 时统一使用 `llm_key.json` 中的默认 `model`。详见 README.md「逐章节模型路由」小节。

**Extended Thinking（v0.2.22+，Anthropic 专属）：** `_call_claude()` 支持注入 Anthropic Messages API 的 `thinking` 参数，让 ≥ Claude Sonnet 4 的模型在回答前进行深度推理。通过 `llm_settings.json` 中 `thinking_enabled_{模块}` 和 `thinking_budget_{模块}` 配置开关和预算。`thinking_budget_{模块}` 与对应的 `max_tokens_{模块}` 的关系：
- `thinking_budget_{模块}` 控制内部思考过程的 token 预算（不可见）
- `max_tokens_{模块}` 控制最终输出文本的最大 token 数（如 `max_tokens_expert_review=8192`）
- API 强制约束：`thinking_budget_{模块}` ≥ `max_tokens_{模块} + 1024`，未满足时代码自动补足
- 开启后 `temperature` 自动忽略（API 不支持并存）
- 推荐仅在智囊团深度复盘开启，详见 README.md「Extended Thinking」章节

---

## 8. 页面/页签布局

- Excel 格式：每个模块独立一个页签
- HTML 格式：所有模块在同一页面中按顺序排列
