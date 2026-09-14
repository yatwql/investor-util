# DataSinking 持仓个股财报摘要 — 设计文档

> 文档类型：中间设计文件（实现落地后随迭代归档）
> 数据源：DataSinking（全文本财报，中国 / 日本 / 韩国 / 台湾）
> 状态：设计完成，待实施

---

## 1. 背景与数据源事实

DataSinking 提供**全文本财报 Markdown**，来源为各市场官方披露平台（cninfo / DART / EDINET / MOPS）。它不提供行情、净值或基金持仓，与现有数据源互补：现有链路覆盖「价格与持仓」，本渠道覆盖「公司经营层叙事与财务口径原文」。

**已核实的接口事实**（来源：官方 docs / OpenAPI 规范 / pricing 页）：

| 项 | 值 |
|---|---|
| 基础地址 | `https://api.datasink.ing` |
| 鉴权 | `?apikey=` query 参数（FMP 风格） |
| 免费 key 领取 | `POST /free-key`（提交邮箱） |
| 符号格式 | FMP 风格：`600519.SS` / `000001.SZ` / `830799.BJ` / `7203.T` / `005930.KS` / `2330.TW` |
| 文种 | `annual` / `semiannual` / `q1` / `q3` / `amendment` |
| 列表 | `GET /documents?symbol=&doc_type=&order=&size=&page=&with_content=1` |
| 单篇 | `GET /documents/{id}` |
| 单章节 | `GET /documents/{id}?section=<章节标题>`（fuzzy title match） |
| 章节清单 | `GET /documents/{id}/sections` |
| 批量 | `POST /documents/batch`（**免费 plan 不可用**） |
| 免费额度 | 3 请求/秒；8,191 篇/日/键（另有全局共享池） |
| 付费额度 | 31 请求/秒；131,071 篇/日（Yearly） |

**合规约束**：返回对象含 `source` 字段（披露平台归属），官方要求再分发时保留出处。报告输出须带来源标注。

**免费档的隐含约束**：批量端点对免费档关闭，因此逐篇取数是免费档的**唯一**路径——这决定了限速必须在**单条调用层**兜住，而不能只依赖批量调度器。

---

## 2. 已定决策

| 决策点 | 结论 |
|---|---|
| 数据用途 | 新增报告章节「持仓个股财报摘要」 |
| 覆盖市场 | 仅 A 股（SSE / SZSE / BSE），按沪深京代码前缀识别 |
| 凭据存放 | 单独密钥文件（仿 LLM 密钥文件的本地私有文件惯例） |
| 限速策略 | 计划感知（按 plan 取每秒上限）+ 日配额护栏 |

---

## 3. 语义命名索引（新增标识符）

命名纪律：下列英文标识符即代码名；中文名即文档/UI 描述。任务编号不进入实现层。

| 语义 slug | 中文名（文档/UI） | 归入 | 说明 |
|:--|:--|:--|:--|
| `financial_report` | 财报全文 | 数据域 | 新数据域标识 |
| `datasink` | DataSinking 财报 | 数据源 | provider 名 / 链路名 / 限速键 / 凭据 source_id |
| `financial_report_digest` | 持仓个股财报摘要 | 报告章节 | 章节 key 与 `report_submodules` 键 |
| `data_key_file` | 数据源密钥文件路径 | 配置 | 顶层路径键，默认 `data/config/data_key.json`；通用文件以 provider（source_id）为节 |
| `datasink_plan` | DataSinking 套餐 | 配置 | `free` / `yearly` |
| `datasink_requests_per_second` | 每秒请求上限 | 配置 | 由套餐给出默认值，可覆盖 |
| `datasink_daily_quota` | 每日文档配额 | 配置 | 日请求计数护栏阈值 |
| `datasink_sections` | 财报取用章节 | 配置 | 章节标题列表（fuzzy 匹配） |
| `datasink_max_chars` | 单股摘要字符上限 | 配置 | 报告内摘要截断长度 |
| `DataSinkReportAdapter` | DataSinking 财报适配器 | 适配器 | 三段式契约实现 |
| `FinancialReportFields` | 财报标准字段记录 | 契约 | 数据域标准字段 |

---

## 4. 架构落点（文件级）

复用既有「数据源适配契约」与「凭据就绪」两套机制，不新造获取路径。

| 文件 | 改动 |
|:--|:--|
| `src/python/providers/datasink.py` | **新增**。HTTP 取数三函数（列表 / 单篇 / 章节清单）；符号映射；错误分类（401 key 无效、429 限速、404 无该文档）；请求前限速与配额检查；模块内 `register_credential_spec(...)` 声明凭据 |
| `src/python/schemas/datasource_fields.py` | 新增 `DOMAIN_FINANCIAL_REPORT` 与 `FinancialReportFields`（`id` / `symbol` / `exchange` / `stock_code` / `stock_name` / `doc_type` / `report_period` / `title` / `word_count` / `announcement_time` / `content` / `source` / `source_api`），登记 `DOMAIN_RECORDS` |
| `src/python/fetcher/source_adapter.py` | 新增 `DataSinkReportAdapter`（声明 `aliases` / `defaults`），登记 `ADAPTER_REGISTRY`；契约自检自动覆盖 |
| `src/python/fetcher/chain.py` | 新增默认链 `financial_report: ["datasink"]`；provider 映射；复用缓存键、熔断、降级 |
| `src/python/fetcher/financial_report.py` | **新增**。域编排：持仓/穿透 → A 股符号集合 → 逐股取「最新年报优先、半年报兜底」→ 按章节取正文 → 返回摘要数据 |
| `src/python/core/datasource_credential.py` | `CredentialSpec` 增加 `key_file` / `key_field`；就绪判定支持「密钥文件或环境变量」；就绪矩阵报告来源类型（仍不含凭据值） |
| `src/python/config/_config_defaults.py` | 新增 `datasink` 段、`data_key_file` 路径键、`report_submodules.financial_report_digest`（默认关）、`batch.datasink_workers`、缓存 TTL 默认值 |
| `src/python/core/registry.py` | `DataModuleDef`（`report_datasink_` 前缀缓存）；`_REPORT_SECTION_DEFAULT` 与 `_REPORT_SHEET_NAMES` 增加章节 |
| `src/python/report/financial_report_digest.py` | **新增**。章节数据装配（表行、来源标注、失败清单） |
| `src/python/report/data_source_matrix.py` | 新增数据源类别「财报全文」 |
| `src/python/report/orchestrator.py`（及相关渲染器） | 章节接线：数据装配 → Excel 页签 → HTML 区块 |
| `src/python/fetcher/batch.py` | 限速器构建注入 `datasink` 间隔（由 `datasink_requests_per_second` 派生） |

---

## 5. 数据流

```
持仓 Excel + 穿透结果
        │  提取 A 股 6 位代码（60/68→.SS，00/30→.SZ，8/4→.BJ）
        ▼
符号集合（去重、排序）
        │  逐股：
        │    1) GET /documents?symbol=&doc_type=annual&order=desc&size=1   （元数据）
        │       无年报 → doc_type=semiannual 兜底
        │    2) 取到 id 后 GET /documents/{id}?section=<章节>
        ▼
标准字段记录（FinancialReportFields，经适配器归一）
        │  截断至 datasink_max_chars
        ▼
报告章节「持仓个股财报摘要」
   ├─ Excel 页签
   └─ HTML 区块
```

**失败降级**：缺凭据 → 链路主动跳过（可读指引）；单股无财报 → 该行标注「无覆盖」；限速/配额 → 停止后续请求并标注；单篇失败 → 该股标注失败原因，不中断整章。

---

## 6. 密钥文件与凭据就绪

**文件**：`data/config/data_key.json`（通用数据源密钥文件，被 `.gitignore` 的 `data/` 规则覆盖，不入库）

```json
{
  "datasink": {
    "api_key": "ds_xxxxxxxx"
  }
}
```

以 provider（`source_id`）为节；一个文件容纳多个数据源的 key，文件内容自述「哪个 key 属于哪个数据源」。

**配置键**：顶层 `data_key_file`，默认 `data/config/data_key.json`；与 `llm_key_file` 同为路径型键，经配置层 `_absolutize_paths()` 转绝对路径。

**就绪判定**（扩展既有机制，保持「值永不落日志 / 报告 / 缓存」纪律）：

```
就绪 = 密钥文件存在且 api_key 非空白
    或 环境变量 DATASINK_API_KEY 非空白（覆盖文件，便于 CI / 临时切换）
```

- `CredentialSpec` 增加 `key_file`（路径）与 `key_field`（字段名，默认 `api_key`）。
- `missing_credential()` / `credential_readiness()` 读取来源并报告「来源类型（密钥文件 / 环境变量）」与是否就绪，**不含凭据值**。
- 链路 `fetch_with_fallback` 在发起请求前主动跳过未就绪的源，并给出申请地址；不把配置级问题计入熔断计数。

---

## 7. 限速与配额（计划感知 + 日配额护栏）

### 7.1 每秒限速

复用既有 per-provider `RateLimiter`（线程安全、按 provider 独立锁），间隔由套餐派生：

```
间隔秒 = 1 / datasink_requests_per_second
free   → 3 req/s → 0.333s
yearly → 31 req/s → 0.032s
```

**接入点**：`providers/datasink.py` 在**每次 HTTP 请求前**调用 `get_rate_limiter().acquire("datasink")`。此点必须落在 provider 层——免费档无批量端点、必然逐篇调用，若只在批量调度器层限速，单条与并发路径会绕过。

构建期由 `datasink_requests_per_second` 计算并注入限速器的 `datasink` 项；用户显式在 `batch_rate_limit.datasink` 写值时可覆盖（高级用法）。

### 7.2 日配额护栏

请求计数持久化到 `data/state/datasink_quota.json`：

```json
{ "date": "2026-09-14", "count": 37 }
```

- 每次请求前：日期变更则归零；`count >= datasink_daily_quota` 时**停止**后续请求并告警（不发起必然失败或被计费超限的调用）。
- 该文件须加入测试隔离的敏感路径重定向（防止测试污染真实计数）。
- 超配额按「可恢复的跳过」处理，不作为传输级失败计入熔断。

### 7.3 并发

`batch.datasink_workers` 默认 3（免费档批量上限 ≤3；付费可调高）。章节装配走批量调度器，但限速仍在 provider 层逐请求生效。

---

## 8. 配置 Schema

```json
{
  "data_key_file": "data/config/data_key.json",
  "datasink": {
    "plan": "free",
    "requests_per_second": 3,
    "daily_quota": 8191,
    "sections": ["管理层讨论与分析"],
    "max_chars": 2000,
    "doc_types": ["annual", "semiannual"]
  },
  "batch": { "datasink_workers": 3 },
  "report_submodules": { "financial_report_digest": false }
}
```

`plan` 为 `free` 时 `requests_per_second` / `daily_quota` 取免费档默认；`yearly` 时取付费档默认。用户可显式覆盖任一值。

---

## 9. 报告章节设计

**页签名**：持仓个股财报摘要（由 `_REPORT_SHEET_NAMES` 注册表驱动，不硬编码字面量）

**可见性**：`report_submodules.financial_report_digest` 默认关；开启后仅当有数据时渲染（数据驱动型章节）。

**表列**：

| 列 | 内容 |
|:--|:--|
| 名称 / 代码 | 持仓或穿透标的 |
| 报告期 | `report_period` |
| 文种 | 年报 / 半年报（中文映射） |
| 标题 | 公告标题 |
| 披露日 | `announcement_time` 转日期 |
| 摘要 | 取用章节正文，按 `datasink_max_chars` 截断 |
| 来源 | `source` 字段（披露平台归属，合规必需） |
| 原文链接 | `adjunct_url` |

**无覆盖/失败**：单股一行标注原因（无财报 / 缺凭据 / 限速 / 配额耗尽 / 取数失败），不静默消失。

---

## 10. 缓存

| 缓存键前缀 | 内容 | TTL |
|:--|:--|:--|
| `report_datasink_index_` | 单股报告元数据 | 两周 |
| `report_datasink_doc_` | 单篇章节正文 | 一个月 |

登记到 `core/registry.py` 的 `DataModuleDef`（`cache_groups=("refresh",)`），受菜单缓存命令与 TTL 统一管理。正文体积较大，缓存层已有的 gzip 阈值对其生效。

---

## 11. 错误与降级矩阵

| 场景 | 处理 |
|:--|:--|
| 密钥文件缺失 / 空值 | 链路跳过该源，报告章节标注「未配置 key」+ 申请地址 |
| key 无效（401/403） | 标注凭据无效；不计入熔断（配置级问题） |
| 限速（429） | 退避或停止本批；标注限速 |
| 日配额耗尽 | 停止后续请求；标注配额耗尽与重置日 |
| 单股无财报 | 该行标注「无覆盖」 |
| 网络不可达 | 传输级失败，计入熔断；标注失败原因 |

---

## 12. 测试计划

| 层 | 用例要点 |
|:--|:--|
| provider | 401 / 429 / 404 / 200 分支；符号映射（沪深京前缀）；章节 fuzzy 参数拼装；请求前 `acquire` 被调用 |
| 限速 | 间隔由 `requests_per_second` 派生；并发下同 provider 间隔 ≥ 配置值；日配额归零与耗尽停止 |
| 凭据 | 密钥文件就绪 / 空值视为缺失 / 环境变量覆盖；就绪矩阵不含凭据值；已就绪时不跳过 |
| 适配器 | 三段式契约自检；缺字段按类型注解兜底；`source` 由适配器强制提供 |
| 章节装配 | 沪深京代码过滤与去重；年报优先半年报兜底；截断长度；失败行不消失 |
| 注册与文档 | 章节进 `_REPORT_SECTION_DEFAULT` 与页签表；`report_submodules` 键在语义命名表登记；缓存前缀在注册表 |

测试须覆盖 `@pytest.mark.unit_providers` / `unit_fetcher` / `unit_report` 等对应 marker；密钥文件与日配额状态文件纳入测试隔离。

---

## 13. 非目标（本期不做）

- 批量端点（免费档不可用，付费档另行评估）
- 日 / 韩 / 台市场（本期仅 A 股）
- LLM 二次摘要（本期输出章节原文截断；LLM 摘要后续评估）
- 财报全文入库报告（仅摘要截断 + 原文链接）
- 修正稿（`amendment`）的自动替换逻辑（仅按文种列出）

---

## 14. 实施顺序

1. **凭据与密钥文件**：`CredentialSpec` 扩展 + 配置键 + 就绪矩阵 + 测试
2. **provider 与限速**：`providers/datasink.py` + 计划感知限速 + 日配额护栏 + 测试
3. **契约与链路**：标准字段域 + 适配器 + 链 + 缓存注册 + 测试
4. **章节装配与渲染**：域编排 + 章节 + Excel/HTML + 注册表 + 开关 + 测试
5. **文档与门禁**：datasource 手册 / 配置手册 / 技术设计语义表 / 需求 / 测试计划 / 目录树 / 变更日志；跑提交门禁

---

## 15. 风险

| 风险 | 缓解 |
|:--|:--|
| 免费档 3 req/s 下逐篇取数耗时随持仓数线性增长 | 缓存元数据与正文；仅取配置的单个章节；并发 3 且限速兜底 |
| 官方免费额度随政策调整 | 全部额度与速率走配置，不硬编码；文档标注默认值来源 |
| 章节标题随披露方措辞变化导致 fuzzy 失配 | 配置化章节列表；`/sections` 接口可先探章节标题（后续可加自愈） |
| 财报正文含大段表格，截断后语义不完整 | 默认取「管理层讨论与分析」章节（叙述性强）；截断长度可配 |
| 凭据泄露 | 沿用「只读密钥文件/环境变量、值永不落日志报告缓存」纪律 |
