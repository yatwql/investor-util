# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.8]**（2026-09-29）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.9-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

---

### 缺陷修复：同类排名的数据版本一致性（rf-477）

**背景**（用户报）：040046（华安纳斯达克100ETF联接 QDII A）与 016055（博时纳斯达克100ETF
发起式联接 QDII A人民币）同为纳指100联接，报告里却一个「253 只里排」、一个「362 只里排」，
看似不同类。

**排查结论**：排名完全来自天天基金 `pingzhongdata/{code}.js`（本项目不做同类圈定）：
`Data_rateInSimilarType` 末位 → rank/total，`Data_rateInSimilarPersent` → 百分位。实测数据证明
**两者本属同一同类池**——两只基金各自的 `sc`（同类池规模）序列逐期几乎完全相同，最新均为
`sc=362`，而报告里的 `253` 实为 **2024-02-18** 那一期的值（两只基金的序列都含该期：
040046 `49/253`、016055 `81/253`）。即：不是分类不同，而是**取到了上游数据版本滞后的快照**，
且报告无任何提示（读到 `155/253` 时内部还自洽：155/253 = 61.26% = 1 − 38.74%）。

**变更**（三项）：
- `providers/tiantian_ranking.py::_parse_rank_entry`：
  ① **同期性校验**——两侧末位日期不一致时以**较新者**为准、较旧项置 `--` 并告警；
     「无日期」不当作不同期（旧格式/精简载荷的未知期次不应白丢数据）；
  ② **同类池跳变防护**（新 `_warn_on_peer_pool_shrink`）——`sc` 相对上期回落 > 10% 即告警；
  ③ 新增 `data_date` 字段与 `_sample_date`（含 «2000-01-01 起» 的合理性下限，防旧格式序号
     如 `[[1, 6.25]]` 被误解为 1970-01-01）；
- `report/fund_performance.py::_format_rank`：**排名后附注数据日期**（`231/362（09-28）`），
  使排名与其他数据一样可追溯；
- `report/fund_candidate.py`：候选基金比较表改为复用同一格式化器（消除重复实现，口径一致）。

**验证**：回归 +9（同期保留/两向不同期取新/无日期不误判/同类池回落告警/正常增长不告警/
日期附注与不可解析日期回退）；实测载荷复验 040046 → `231/362`、016055 → `174/362`（both `sc=362`，
均附 `09-28`）；`unit/report + providers + fetcher` 2965 passed。

### 缺陷修复：provider 失败原因载体的残值串味（rf-476，CI 3.11 暴露）

**背景**：GitHub CI 的 `test (3.11)` job 在本次提交后持续失败（3.12/3.13 均绿），失败断言为
`assert 'HTTP 500' == ''` @ `test_reason_is_thread_local`。诊断方式：将 P0 失败详情输出为
GitHub annotation（annotation 免授权可读，不必下载日志），定位到具体断言。

**根因**（真产品缺陷，非测试问题）：provider 自陈失败原因的线程本地载体
（`providers/_utils._last_reason`）**只在 provider 返回 `None` 时被链路消费**
（`fetcher/chain._try_provider_fetch`）。但 `datasink`/`cninfo` 的用例直接调取数函数、
只看返回值而不消费原因 → 写入的 `HTTP 500` 残留在该 xdist worker 的主线程槽位，
污染同 worker 中**下一个**读该载体的用例。仅 3.11 暴露是因为各版本测试分布/顺序不同，
使「写入方」与「读取方」恰好落到同一 worker（本机 3.11/3.13 均不可稳定重现）。

**变更**：
- `providers/_utils.py`：新增 `clear_last_reason()`（生产前清除，与消费方 `take_last_reason` 分工）；
- `fetcher/chain.py::_try_provider_fetch`：**每次尝试 provider 之前**先 `clear_last_reason()`，
  使「本次读到的原因」不可能是上次未经消费的残值；
- `src/test/conftest.py`：新增 autouse fixture `_auto_reset_last_reason`（与 `_auto_reset_provider_registry`
  同习语——模块级可变状态每用例前复位，使用例不依赖执行顺序/worker 分配）；
- `test_provider_utils.py`：+2 回归（链级残值不串入诊断 / 测试间不串味）。

**验证**：两处修复均验证为 load-bearing（分别移除后对应用例即失败）；`test_provider_utils` 8 passed、
chain+datasink+cninfo 120 passed；本地 Python 3.11（`uv` 与 `pip` 两套独立环境）`dev-verify`
3376 passed 连续 3 次稳定。

### 工程修复：消除 `ruff format` 漂移残留（rf-474）

**背景**：CLAUDE.md 声明「`ruff format --check` + `ruff check` 当前均为零告警基线」，但全仓复核发现
`src/test/unit/report/test_market_value_strategy_edge.py` 存在两处格式漂移（`line-length = 120` 下有两行
124 字符的 `session_cache_set(...)` 调用未按 ruff 规范化换行）。因 `.github/workflows/ci.yml` 的 `format`
job 为**非阻塞**（只报告不阻断合并/发布），该漂移长期未被发现。

**变更**：对该文件执行 `ruff format`（仅两处语句换行展开，+4 行）。

**验证**：**AST 等价**（新旧 `ast.dump(ast.parse(...))` 全等）证明行为中性；该文件 8 例边缘用例全过；
`ruff check` 干净；全仓 `ruff format --check src/ scripts/` **736 files 零漂移**；同步 `folders.md` 测试代码行数。

### 工程修复：安全基线的密钥文件范围修正（rf-475）

**背景**：bench 全量采集（`--mode bench`，含 `scenario_security`）暴露 `test_key_file_permissions_unix` 恒失败——该用例把 `data/config/llm_providers.json` 也当密钥文件断言不得 world-readable，而它是**故意跟踪入仓**的配置（`.gitignore` 显式 `!` 放行），git 索引记录 `100644`，任何干净检出的权限都是 `644`。因 `scenario_security` 不在 `dev-verify`/`verify` 模式内，该恒失败长期未被常规门禁发现。

**变更**：
- `src/test/scenario/security/test_security.py`：权限基线收窄为「仅**持有密钥本体**的文件」（类常量 `_SECRET_FILES = ("data/config/llm_key.json",)`），并就地注明为何不含 `llm_providers.json`；
- **新增** `test_providers_config_has_no_inline_secret`：守住「该文件可入库」的真正红线——不得内联 `api_key`、`credentials_ref` 必填（与 `unit_config` 的内联 api_key 硬拒绝同一判据），使「移出权限断言」不以丢失防护为代价；
- 修正类 docstring（原「五项安全基线」→ 明确列出五项基线含本项的两条禁令）。

**验证**：`security` 模式 **10 passed / 0 failed**；反向核对——向 `llm_providers.json` 注入内联 `api_key` 则该用例失败、恢复即通过。

### 数据源稳定性提升：指数历史双备源 + 重试补齐 + 状态补全（plan-58）

**背景**（用户要求）：报告数据源降级表中 `report_datasink_index`、`fin_indicator_akshare_financial`、
`index_history_history_index_sh000300` 与 QDII 价格刷新反复失败，且分红缺状态。

**变更**：
- **历史指数日 K（`index_history_*`）**：`history_index` 链原为 `tencent → sina`，而新浪 `getKLineData`
  端点实测全 404 → 事实单源；且历史链路（`chain._try_providers`）**无链级重试**，provider 又把传输失败
  吞成空列表 → 单次抖动即整链空。① `providers/tencent.py` 抽出 `_fetch_kline_json`（总尝试 3 次、指数退避）
  供股票/指数 K 线共用；② 新增 `providers/eastmoney.py::fetch_index_kline`（push2his 日线，免 key 独立厂商）
  + `providers/hithink.py::fetch_index_kline`（与 `fetch_kline` 同上游，走新增 `to_index_thscode` 指数映射）；
  ③ `history_index` 链槽扩为 `["tencent", "eastmoney", "sina", "hithink"]`。
- **财务指标多期（`fin_indicator_akshare_financial`）**：`fetch_indicator_series` 直连 provider（不经链路），
  链路的传输级重试不覆盖它 → 补一层有界退避重试（`_SERIES_RETRY_POLICY`，重试耗尽仍落同花顺/链路兜底）。
- **财报索引（`report_datasink_index`）**：主源索引异常且巨潮备源无命中时原先**静默** → 补降级登记
  （`_record_index_failure`，仅主源异常时记，预期内空结果不误报）；并如实归属来源——巨潮接管与缓存命中
  均按条目 `source` 字段记 `report_cninfo_index`（`_index_source_of`），类别前缀补 `report_cninfo_`。
- **QDII / 场外净值价格刷新（`price_fund_otc_*_refresh`）**：`_price_cache_fresh` 按「最近交易日」判定，
  而场外 / QDII 官方净值合法为 T-1 → 永远被判跨日残留、反复清缓存重取。改为新鲜度阈值**按路由分域**
  （场外取前一交易日，场内仍取最近交易日）；**`report/market_value.py` 的 CACHE_ONLY 缓存校验同步传入路由**
  （该处为同一函数的第二个调用点，早于本次改动即存在，首轮遗漏会在 `edge` 模式下抛 `TypeError`）。
- **分红数据状态**：刷新原先只在控制台打印 → `report/category.py` 补类别级取用/失败登记
  （`dividend_data`，失败原因读 `akshare_extras._DIVIDEND_FAILURE`；「本无分红」这类预期内空结果不登记），
  类别前缀补 `dividend_`，与行业分类 / 盈利预测同口径。
- 回归 +30 例：`test_eastmoney.py`（`_index_secid` 映射 + 解析/增量）、新增
  `test_eastmoney_index_edge.py`（6 例边缘：无法映射/结构异常/重试耗尽/5xx 不重试）、`test_hithink.py`
  （`to_index_thscode` + `fetch_index_kline`）、`test_tencent.py`（K 线重试）、`test_financial_indicator.py`
  （多期重试/耗尽兜底）、`test_financial_report.py`（来源归属 + 静默失败登记 + 矩阵可见）、
  `test_category.py`（分红状态四分支）、`test_fetcher_price.py`（场外 T-1 新鲜度 + 路由分域）。
- `src/test/_network_guard.py::apply_offline_stubs` 同步将新增 provider 级重试策略退避置 0（离线用例零等待）。
- 文档同步：`requirements.md`（R-HST-07）、`technical.md`（架构约束链槽 + 数据源表 + 功能语义命名表
  补 `fetch_index_kline` / `to_index_thscode`）、`datasource.md` / `datasource-reliability.md`
  （指数链槽 / 东方财富指数 K 线 / 净值新鲜度口径 / 分红状态）、`developer-guide.md`（离线退避口径）、
  `folders.md`（目录树 + 统计表）、本变更日志。

### 交互优化：新增 [D] 配置目录信息子菜单（rf-471）

**背景**（用户要求）：持仓目录 / 持仓文件名 / 报告输出目录三个同属「路径配置」的入口平铺在主菜单占 3 个键位，而 `[D]` 已被系统自检占用，语义冲突。

**变更**：
- `tui_menu.MENU_ITEMS`：三项合并为 `[D] 配置目录信息`（20 → 18 项）；系统自检键 `D` → `T`（`FEATURE_GATED_ITEMS` 同步，仍受 `doctor_check` 门控）
- `handlers_config._cmd_config_dir_info()`：独立子菜单循环（`[C]` 持仓目录 / `[F]` 持仓文件名 / `[O]` 报告输出目录 / `[B]` 返回主菜单）——大小写归一、无效输入重提示、EOF/Ctrl+C 安全返回；子项在调用时取模块全局（便于打桩）
- 回归 +7 例（子菜单分发/大小写/返回/无效输入/EOF + 菜单键集与路由 D→`_cmd_config_dir_info`、T→`_cmd_run_doctor`）
- 文档同步：how-to-use-tui-menu / how-to-start / faq / how-to-config / how-to-config-llm / how-to-use-web-mode / how-to-use-cli-mode / requirements（R-TUI-02 18 项 + §3.2 菜单表 + R-DIAG-05）/ technical（§1.6.3 菜单体系）/ testplan / test-coverage / folders；代码内提示串（`handlers_log` docstring、`features.doctor_check` 说明）同步

### 文档：README 核心亮点与功能特性重梳（v0.11.x 全部特性）

**背景**（用户要求）：README 的亮点表与功能特性章节停留在较早版本，未覆盖 v0.11.x 落地的能力。

**变更**（`README.md` 全文重写，207 → 221 行）：
- 核心亮点表：7 条重排为「一次持仓三种用法 / 全量报告双格式 / 穿透到真实持仓 / 量化风控成体系 / 真正把 LLM 用成智囊团 / 数据可信度可追溯 / 决策闭环 / 调仓 What-if」
- 功能特性重分组：报告与行情 / 新闻与数据增强 / LLM 分析 / 投资分析与风控 / 基金评价 / 持仓基本面 / 调仓 What-if / 运维与可观测性 / 隐私与安全
- 补齐此前缺失：市场情绪、估值分位、市场温度、交易纪律、流动性、尾部风险、候选基金比较、财务指标与财报摘要、信号预消化、确定性信号沉淀、决策跨期反思闭环、正反辩论/条件推理/集中度问答、景气度框架诊断、系统自检、日志可视化、阶段计时、凭据不落产物、00 重叠区按名称消歧、ETF 联接穿透
- 修正过期内容：图表数与页签分组口径、「17 章」章节编号表述、技术设计文档描述去约束代号

---

### 缺陷修复：巨潮备源三处取数缺陷（rf-472）

**现象**（用户贴日志问「所以其实是拿不到信息的么？」）：报告里大量 `[financial_report] 全链路失败（无过期缓存可用）`，夹杂 `[cninfo] 连接挂起 40.0s… 判定主机不可达`。

**排查结论（实测）**：
- **主源 DataSinking 完全正常**：直连官方 API 实测 `GET /documents` **HTTP 200**（`total: 626044`）、`/documents/{id}/sections` **HTTP 200**；日志里的「返回空」是**正常业务结果**——那几份季报确实没有「管理层讨论与分析」章节
- **备源巨潮确实连不上**：`www/static.cninfo.com.cn` DNS 解析正常但 **TCP 握手超时**（对照：东财/新浪/datasink 全秒连）——属本机网络路径阻断，非服务下线

**三处缺陷**：
1. `_get_bytes` 与元数据接口共用 `_TIMEOUT = 20.0`，而公告 PDF 是完整年报原文（几十 MB）→ 慢链路下必然「挂起 → 失败」，**从未下成功过**，每次白等一个超时预算
2. `cninfo` 是**直连调用（不经 Provider Chain）**，无会话级熔断 → 主机不可达时同一轮报告里**每篇文档都重新发起、重新白等**（实测 601939 连试 4 次共 160s）
3. provider 返回 `None` 时链路只记笼统的「返回空」，无法区分「源故障」与「该文档确实没这一节」——本次排查即被误导

**变更**：
- `cninfo`：新增独立 `_PDF_TIMEOUT = 60.0`，公告 PDF 用它；新增「主机本会话不可达」短路（`_mark_host_unreachable` / `_is_host_unreachable`，挂起型失败后标记主机，后续请求不发 HTTP 直接失败；非超时失败不标记以免误伤）
- `providers/_utils`：新增**按线程隔离、消费即清**的失败原因载体 `set_last_reason` / `take_last_reason`
- `chain._try_provider_fetch`：provider 返回 `None` 时读取该原因并**替换笼统的「返回空」**，同时进 `FailureDiagnostics`（→ 报告数据源矩阵）
- `datasink` / `cninfo`：各失败分支逐条自陈原因（无凭据 / 凭据为空 / 配额用尽 / 401-403 / 429 / 404 探测（区分「无该章节」与「章节清单未解析」）/ 非 200 / 非 JSON / orgId 未解析 / 主机不可达 / 连接超时）
- 回归 +14 例；文档：`technical.md` §2.2.1、`datasource-reliability.md`、`testplan.md`

**效果**：慢链路下年报 PDF 能真正下下来；主机不可达时由 N × 超时降为 1 次；日志/矩阵如实区分「源故障」与「该文档无该章节」。

---

### 界面优化：新闻表手机窄屏改卡片式堆叠（rf-473）

**现象**（用户用手机打开 HTML 报告）：财经新闻热点与持仓关联分析表里，摘要、关联关键词、LLM 关联分析挤在一起，有些地方错位，容易错过信息。

**根因**：该表 7 列（含 LLM 关联分析列）并沿用全局 `table { min-width: 600px }`，手机（≤768px）横向压缩后各列互相挤压换行、列边界难辨，三块相关字段黏连。

**变更**：
- 新闻表加 `.news-table` 类作窄屏规则作用域
- `@media (max-width: 768px)`：**改为卡片式堆叠**——隐去表头、每行一张卡片；单元格转块级，`td[data-label]::before { content: attr(data-label) }` 生成字段名前缀；序号与可点击标题作卡片头（不显示字段名前缀）；取消 `min-width`
- 模板补 `news-table` / `news-seq` / `news-title` 类与各字段 `data-label`
- 回归 +5 例（类名作用域、逐字段 data-label 齐备、窄屏隐表头与堆叠规则、取消 min-width、卡片头规则）
- 文档：`reports-instruction.md` 补「新闻表窄屏卡片布局」说明

**效果**：手机上一屏一条新闻，各字段带名字段名各占一行，不再错位；宽屏表格形态不变。

---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.8（2026-09-15 ~ 2026-09-29）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
