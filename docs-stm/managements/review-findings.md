# 个人投资分析报告生成小助手 - 自我审查问题记录

创建日期：2026-06-26
最后更新：2026-07-01（v0.2.53 — 全量场景审计完成 + 第二波代码级深度审计，R-084 P0 崩溃已修复并归档至 changelog）

---

## 审查记录（摘要）

| 日期 | 范围 | 状态 |
|------|------|:----:|
| 2026-06-26 ~ 2026-07-01 | 全量需求/架构/代码/测试审计（P1~P2） | ✅ 已完成 |
| 2026-07-01 | P3 代码现代化：旧式 typing / `__future__` / `.format()` / pyproject.toml | ✅ 已完成 |
| 2026-07-01 | 全量场景审计：网络/数据质量/并发/节假日/零成本/首次运行/LLM 等 edge case | ✅ 已完成 |
| 2026-07-01 | 第二波代码级深度审计：逐行排查 12 个核心模块，发现 18 个新问题（P0 CRASH × 7、P1 WRONG DATA/HANG × 5、P2 × 6） | ✅ 已完成 |

---

## 待办区

---
### R-085: `main.py` 类型标注 `callable` 为内置函数非泛型
- **状态**：◐ 待处理
- **风险**：P2 — 当前因 `from __future__ import annotations` 不会崩溃，但移除该 import 后会抛 `TypeError`
- **位置**：`src/python/main.py:96`
- **建议**：改为 `dict[str, Callable]` 并补上 `from collections.abc import Callable`

---
### R-086: 旧式 `Optional[...]`/`Dict[...]`/`List[...]` 残留
- **状态**：◐ 待处理
- **风险**：P3 — 不崩溃，破坏编码一致性
- **涉及文件**：`llm/api.py`、`providers/news_aggregator.py`、`report/html_builders.py`、`report/html_writer.py`、`report/news_correlation.py`、`report/excel_writer.py`、`report/category.py`、`tui_menu.py` 共 23 处
- **建议**：5 分钟批量统一替换为内置泛型

---
### R-087: `plan.md` 已完成项未归档（文档膨胀）
- **状态**：◐ 待处理
- **风险**：P3 — 不影响运行，但 J 阶段 15 行函数治理表格全部 ✅ 仍占用篇幅
- **位置**：`docs-stm/managements/plan.md`
- **建议**：移至 `archived_plan.md`

---
### R-088: `news_aggregator.py` 含未导入的 `Optional` 引用
- **状态**：◐ 待处理
- **风险**：P3 — `from __future__ import annotations` 下正常工作，移除后会 NameError
- **位置**：`src/python/providers/news_aggregator.py:62`
- **建议**：补上 `Optional` import 或改用 `| None` 风格

---
### R-089: `__pycache__` 残留 .pyc 与 .py 不对应可能致缓存不一致
- **状态**：◐ 待处理
- **风险**：P3 — 可能加载过期字节码
- **建议**：执行 `find . -path '*/__pycache__/*' -delete`

---
### R-090: `data/config/` 文件含 `//` 注释，纯 `json.load()` 会崩溃
- **状态**：◐ 已知设计
- **风险**：P2 — 程序使用 `_strip_json_comments()` 预处理后解析，正常运行。但若配置代码改为直接 `json.load()` 风险暴露
- **位置**：`src/python/config.py` `_strip_json_comments()`
- **建议**：保持现有方案，代码注释标注"勿改用裸 json.load()"

---

## 场景审计 — 全量 edge case 排查（2026-07-01 新增）

以下结果来自系统性场景分析（网络/数据质量/并发/节假日/首次运行/LLM/报表输出/用户输入等维度），逐一判断程序是否崩溃、是否产生错误或不充分的结果。

---

### R-101: 东方财富备用链路 `yesterday_nav=0.0` 导致 `today_profit` 虚高

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成错误数据（数值虚高）**
- **场景**：网络异常时，主 API（`api.fund.eastmoney.com/f10/lsjz`）超时/失败，触发 `_fallback_fundf10()` 备用链路。该函数将 `yesterday_nav` 硬编码为 `0.0`（行 153）。当备用 HTML 页面返回的净值日期恰好等于今日交易日时（收盘后场景），`today_profit = (nav - 0.0) × shares = nav × shares`，即**整只基金持仓市值被报告为"今日盈亏"**
- **触发条件**：①东方财富主 API 不可用；②报告在交易日收盘后生成（今日净值已发布）；③持仓含场外基金
- **根因**：`src/python/providers/eastmoney.py:153` 注释称"置零避免 today_profit=0 误判"，但 `yesterday_nav=0` 才是误判源。备用链路获取不到前日净值时**不应设置 `today_profit` 为有意义的非零值**
- **修复建议**：
  - 方案 A：备用链路 `yesterday_nav = nav`（保守回退，假设当日净值无变化 → `today_profit = 0.0`）
  - 方案 B：在 `_compute_detail_row` 中对 `source_api="eastmoney"` 且 `nav_date == trading_day` 但 `yesterday_close == 0.0` 时跳过 today_profit 计算（置 0）
- **收益**：消除场外基金今日盈亏的虚假高位报告。用户不会被"今天涨了几十万"的幻象误导

---

### R-102: QDII 检测仅依赖名称关键词（`"QDII" in name.upper()`），遗漏无显式 QDII 标签的 QDII 基金

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成错误数据（QDII 被当作普通基金处理）**
- **根因**：QDII 检测在 `market_value.py:_is_qdii()`（行 59-60）和 `penetration.py:classify_penetration()`（行 88-89）中使用完全相同的纯名称匹配。部分跟踪海外指数的基金名称中不包含 "QDII" 字样
- **影响维度**：
  1. `price_update_status()`：不接受 T-1 净值日期 → 标记为"未更新"（实际上 QDII 因时差 T-1 正常）
  2. `classify_penetration()`：误分类为主动权益基金或债券基金 → 穿透深度分析方向错误
- **涉及位置**：`src/python/report/market_value.py:59-60`、`src/python/report/penetration.py:88-89`
- **修复建议**：
  - 方案 A：在 `config.json` 新增 `qdii_codes` 列表，用户可手动标记 QDII 代码
  - 方案 B：建立内置 QDII 代码知识库（更新成本高，但准确）
  - 方案 C：增加第二重检测——如果基金跟踪境外指数（从基准名称判断），也标记为 QDII
- **收益**：QDII 基金在报告中正确标记为 QDII，获取正确的价格更新状态和穿透分析

---

### R-103: 零成本持仓 `profit_rate` 显示为 0%（数学误导）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成误导数据（收益率错误）**
- **场景**：持仓允许零成本（v0.2.16 设计），`_compute_detail_row()` 行 403：`profit_rate = profit / cost if cost > 0 else 0.0`。当 `cost=0` 且 `profit>0` 时，收益率应为无穷大或 N/A，而非 0%
- **位置**：`src/python/report/market_value.py:403`
- **修复建议**：
  - `cost == 0` 时 `profit_rate` 设为 `None` 并在 Excel/HTML 渲染为 "--"
  - 或显示 "∞"（但 Excel 单元格不支持）
- **收益**：零成本持仓的正确收益率呈现。用户不会误以为"这持仓没赚钱"

---

### R-104: 交易日历 akshare 失败时回退到纯周度判断，中国长假期间严重偏差

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成错误数据（交易日判断错误、取价方式和盈亏计算偏差）**
- **场景**：`_is_trading_day()`（`market_value.py:203-219`）使用 akshare 交易日历。若 akshare 不可用（网络/import 失败），回退到 `date.weekday() < 5`（周六日排除）。中国股市有独特的**调休安排**（如春节、国庆前后可能存在"周六开市、周日休市"或"工作日休市"）
- **影响**：
  1. `get_last_trading_day()` 返回错误日期 → `_determine_price_type()` 标签错误
  2. `price_update_status()` 判断偏差
  3. `today_profit` 计算偏差（`nav_date == trading_day` 条件错误）
- **涉及位置**：`src/python/report/market_value.py:174-248`
- **修复建议**：
  - 无 100% 完美替代方案。建议 akshare 失败时在日志中打出 **WARNING 级别告警**（当前是 INFO）
  - 可内置一个简化的中国法定节假日排除表（硬编码已知的调休模式，精确到 2026~2027）
  - 或缓存 akshare 结果到独立文件，即使网络波动也能使用上次成功获取的日历
- **收益**：节假日附近生成的报告具有正确的交易日判断、取价标签和盈亏计算

---

### R-105: 新闻情绪聚合中 `\d{6}` 正则从 `matched_keywords` 提取代码，可能误匹配非持仓代码

- **状态**：◐ 待处理
- **风险等级**：**P1 — 情绪聚合归因到错误的持仓品种**
- **场景**：`early_warning.py:226` 使用 `re.search(r"(\d{6})", kw)` 在 `matched_keywords` 中提取所有 6 位数字序列作为持仓代码。但 `matched_keywords` 可能包含日期（202601）、数字、或与持仓无关的 6 位代码
- **影响**：新闻情绪利好/利空被错误地归因到无关的持仓品种上
- **位置**：`src/python/report/early_warning.py:224-228`
- **修复建议**：对提取到的 6 位数字，仅在 `code_to_name` 查找表中存在时才归因（已有行 231 `code_to_name.get(code, code)` 兜底返回 code 本身，建议改为 `if code not in code_to_name: continue`）
- **收益**：情绪聚合只归因到真实持仓，避免噪音

---

### R-106: Excel 页签名无特殊字符/长度校验

- **状态**：◐ 待处理
- **风险等级**：**P2 — 特定条件下 Excel 生成崩溃**
- **场景**：openpyxl 限制 sheet name ≤ 31 字符，不允许字符 `[]:*?/\`。报告页签名使用 `get_report_sheet_name()` 返回的模块名，若用户自定义名称过长或含特殊字符，`ws.title = "..."` 抛出 ValueError
- **位置**：多处 `ws.title = ...`（`market_value.py:593`、`penetration_sheet.py`、`summary.py` 等）
- **触发概率**：低（默认名称均在安全范围内，仅当用户自定义配置时可能触发）
- **修复建议**：在设置 `ws.title` 前做长度截断和特殊字符替换
- **收益**：消除偶发崩溃，即使自定义名称也能正常生成

---

### R-107: 熔断器仅内存有效，程序重启后重置

- **状态**：◐ 待处理
- **风险等级**：P2 — 次优用户体验
- **场景**：`circuit_breaker.py` 用模块级字典存储状态。若 API 持续不可用，每次程序重启都触发完整的 5 次重试链（最长等待 34 秒）后熔断器才再次打开
- **位置**：`src/python/llm/circuit_breaker.py`
- **收益**：若熔断器状态持久化，重启后直接跳过重试，节省等待时间
- **建议**：将熔断器状态持久化（使用 cache 写文件），设置较短的 expiry（如 5 分钟）

---

### R-108: `_benchmark_locks` 字典无限增长

- **状态**：◐ 待处理
- **风险等级**：P2 — 微小内存泄漏
- **场景**：`fetcher/fund.py` 的 `_get_benchmark_lock()` 为每个新基金代码创建一个 `threading.Lock`，存入字典后从不清理。长期运行且覆盖大量基金代码时，字典持续增长
- **位置**：`src/python/fetcher/fund.py:169-177`
- **修复建议**：使用 `functools.lru_cache` 替代手动字典管理，或定期清理不活跃的锁
- **收益**：消除微小的内存泄漏风险

---

### R-109: 大型持仓集下 HTML 报告文件过大

- **状态**：◐ 待处理
- **风险等级**：P2 — 次优用户体验
- **场景**：单页 HTML 嵌入全部内容（LLM 生成章节、新闻数据、市值核算、穿透数据）。50+ 持仓 + LLM 分析时文件轻易超过 10~20MB，浏览器加载缓慢
- **位置**：`src/python/report/html_writer.py:194-211`（模板渲染 + 全部数据一次性传入）
- **修复建议**：
  - 方案 A：新闻数据按需折叠（可展开），默认只显示前 20 条
  - 方案 B：LLM 内容作为独立 HTML 片段，通过 iframe 或脚本懒加载
  - 方案 C：压缩 HTML（移除多余空格/缩进）
- **收益**：改善大报告的可浏览性

---

### R-110: 多模块共享 `_timing_records` 全局列表非线程安全

- **状态**：◐ 待处理
- **风险等级**：P2 — 线程安全
- **场景**：`progress.py:16` 的 `_timing_records` 是模块级列表。多个 `_Timer` 上下文管理器在不同线程中并发写入时可能丢失记录或出现竞态。`html_writer.py` 和 `excel_generator.py` 共享此列表
- **位置**：`src/python/report/progress.py:16-17`
- **修复建议**：加 `threading.Lock` 保护 `_timing_records.append()`，或改用 `queue.Queue`
- **收益**：消除极端并发场景下耗时统计丢失的风险

---

### R-111: `cache.get()` 不创建 `data/cache/` 目录

- **状态**：◐ 待处理
- **风险等级**：P3 — 良性
- **场景**：`cache.py` 的 `get()` 不确保缓存目录存在，目录不存在时直接返回 None。`set()` 会创建目录，所以首次写缓存后就不再有问题。但在极端场景（外部删除缓存目录后立即触发读）下可能产生空缓存的效果
- **修复建议**：`get()` 入口处确保目录存在（最小成本加一个 `os.makedirs` 调用）
- **收益**：消除一个极其边缘的场景

---

### R-112: `classify_holdings` 与 `classify_penetration` 分类逻辑不一致

- **状态**：◐ 待处理
- **风险等级**：P3 — 用户可见的不一致
- **场景**：`market_value.py:classify_holdings()` 和 `penetration.py:classify_penetration()` 有不同的分类优先级逻辑和关键词判断。同一持仓可能在市值核算页和穿透分析页被分为不同类型
- **具体差异**：
  - market_value: 账户名优先 → 场外账户中的 ETF 代码也被归为"国内场外"
  - penetration: 名称特征优先 → ETF 名称/5xxx 代码先判断，再判断账户
- **收益**：统一分类逻辑后，用户不会在不同报告页签中看到同一持仓的不同标签
- **修复建议**：抽取公共分类函数，两处引用同一份逻辑

---

## 第二波深度代码审计 — 代码级 crash/wrong-data 排查（2026-07-01 新增）

以下结果来自对重点模块源代码的逐行审计，聚焦「真的会出问题」导向的崩溃（CRASH）、错误数据（WRONG DATA）和永久阻塞（HANG）场景。

---

### R-113: tiantian.py 正则 `re.search(r"<title>(.*?)\(|（")` 在全宽括号下崩溃（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序崩溃**
- **场景**：`_extract_fund_meta()` 使用正则 `re.search(r"<title>(.*?)\(|（", html)` 提取基金名称。正则有两个分支：`\(`（半宽括号）含捕获组，`（`（全宽括号）不含捕获组。当匹配到第二个分支时，`group(1)` 返回 `None` → `.strip()` 抛出 `AttributeError`
- **根因**：`src/python/providers/tiantian.py:130-132` — 全宽括号 `（` 前未加捕获组
- **触发条件**：持仓中含名称 HTML `<title>` 使用全宽括号的基金（中文基金名称广泛使用全宽括号，如"易方达蓝筹精选混合（110011）"）
- **修复建议**：
  - 方法 A：`title_match = re.search(r"<title>(.*?)\(|（(.*?)）", html)` 后判断哪个 group 非 None
  - 方法 B：使用 `re.search(r"<title>([^<]+?)\(|（", html)` 确保 group(1) 始终非空
- **收益**：消除 `fetch_fund_holdings()` 对特定中文基金名称的崩溃，这类基金数量可观

---

### R-114: tui.py Linux 路径 `sys.stdin.fileno()` 和 `termios.tcgetattr(fd)` 在 stdin 关闭时崩溃（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序崩溃**
- **场景**：`_get_key_linux()` 在行 69-70 调用 `sys.stdin.fileno()` 和 `termios.tcgetattr(fd)`，这两行**位于 try 块之外**。当 stdin 被重定向/关闭时（如 `echo "" | python main.py`、容器内无 TTY、CI 环境），`fileno()` 抛出 `ValueError` 或 `OSError`
- **位置**：`src/python/tui.py:69-70`
- **修复建议**：
  - 将行 69-70 移入 try 块
  - 或在入口处检查 `sys.stdin.isatty()`，非 TTY 时直接返回 KEY_UNKNOWN
- **收益**：在 CI/容器/管道环境下不会因键盘输入初始化崩溃

---

### R-115: tui.py Linux 路径 `sys.stdin.read(2)` 在 ESC 后仅收到 1 个字节时永久阻塞（HANG）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序永久阻塞**
- **场景**：行 85-90：按 ESC 键后读取剩余 2 字节。`select.select` 仅检查第一个字节是否就绪，当只有 1 个字节跟随 ESC 时（网络延迟、串口乱序、API 层截断），`sys.stdin.read(2)` 永久阻塞（无超时参数）
- **位置**：`src/python/tui.py:85-90`
- **修复建议**：
  - `read(2)` 前加二次 `select.select` 检查
  - 或逐字节读取（`read(1)` × 2 次，每次带 0.1s 超时）
  - 或使用 `select.select` 替代裸 read
- **收益**：消除终端输入在极端网络/串口条件下的永久挂起

---

### R-116: tui_menu.py `config["holdings_dir"]` 裸键访问导致 KeyError（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序崩溃**
- **场景**：`_show_config()` 行 87 使用 `config["holdings_dir"]` 裸键访问（非 `.get()`）。当 `_config_cache` 为空 dict、或 `_refresh_config()` 返回的配置缺少 `holdings_dir` 键时，抛出 `KeyError`
- **位置**：`src/python/tui_menu.py:87`
- **修复建议**：改为 `config.get("holdings_dir", "")`，与行 90-91 的 `.get()` 风格一致
- **收益**：消除配置异常时菜单显示的崩溃

---

### R-117: tui_menu.py `endpoint.split("/")[2]` 在 endpoint 无 scheme 时 IndexError（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序崩溃**
- **场景**：`_show_llm_config_status()` 行 111 使用 `endpoint.split("/")[2]` 提取端点域名。当 endpoint 为 `"api.openai.com"`（无 scheme、无路径）时，`split("/")` 返回长度为 1 的列表，`[2]` 抛出 `IndexError`
- **位置**：`src/python/tui_menu.py:111`
- **修复建议**：
  - 使用 `urllib.parse.urlparse(endpoint).hostname` 解析
  - 或先检查 `len(parts) > 2` 再索引
- **收益**：消除 LLM 配置为短端点格式时的菜单崩溃

---

### R-118: reader.py `list_xlsx_files()` 文件删除竞争导致 FileNotFoundError（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 程序崩溃（低概率）**
- **场景**：`list_xlsx_files()` 行 35 `files.sort(key=os.path.getmtime, reverse=True)` 在排序键中调用 `os.path.getmtime`。在 `os.listdir`（行 30-34）和排序之间，若其他进程/用户删除了 xlsx 文件，`os.path.getmtime` 抛出 `FileNotFoundError`
- **位置**：`src/python/reader.py:35`
- **修复建议**：
  - 改用 `sorted()` 配合 try/except 保护的 key 函数，跳过已删除文件
  - 或先 `os.path.exists()` 检查再排序
- **收益**：消除文件系统竞争条件的偶发崩溃

---

### R-119: industry.py `batch_fetch_industry_data()` `future.result()` 无异常防护，单次失败杀死整个批次（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序崩溃**
- **场景**：`batch_fetch_industry_data()` 行 90-91 在 `as_completed` 循环中对 `future.result()` **无 try/except**。任意一个 `fetch_industry_data` 工作线程抛出未处理异常（网络超时、API 解析失败等），异常在 `result()` 调用时重新抛出，整个批量获取崩溃
- **位置**：`src/python/fetcher/industry.py:90-91`
- **修复建议**：在 `future.result()` 外包裹 `try/except Exception`，异常时 `logger.warning` 并 `continue`
- **影响链**：`batch_fetch_industry_data` 被 `news_correlation.py:270` 调用 → 新闻关联分析的行业关键词扩展也会崩溃
- **收益**：单只股票行业数据获取失败不会影响其他股票的数据

---

### R-120: tencent.py `_add_prefix()` 静默丢弃 2/4/8/9 开头的股票代码（WRONG DATA）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成错误数据**
- **场景**：`_add_prefix()` 行 46-50 仅为 `5/6`（sh）和 `0/1/3`（sz）开头的代码添加交易所前缀。`2`（B 股/创业板 B）、`4`（三板）、`8`（北交所/新三板精选层）、`9`（B 股）开头的代码不加前缀返回原值。腾讯行情 API 要求 sh/sz 前缀，无前缀的代码返回空/错误数据，导致价格 = 0.0
- **位置**：`src/python/providers/tencent.py:41-50`
- **修复建议**：添加 `2/4/8/9` 前缀映射，或至少记录 WARNING 日志
- **收益**：B 股/三板/北交所持股在行情获取中不再静默丢失

---

### R-121: sina.py 硬编码 `var hq_str_` 前缀 + `price>0` 过滤导致指数数据静默丢失（WRONG DATA）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成错误数据**
- **场景**：两个问题叠加：
  1. 行 123 `code = var_part.replace("var hq_str_", "").strip()` 硬编码前缀，若新浪 API 格式变更（如改为 JSON），所有指数代码无法提取，全部指数数据静默丢失（无日志告警）
  2. 行 128 `parsed["price"] > 0` 过滤在休市期间（价格=0）排除所有指数，与"API 返回空"无法区分
- **位置**：`src/python/providers/sina.py:123-128`
- **修复建议**：
  - 格式校验：检查 `var_part` 是否以 `"var hq_str_"` 开头，否则记录 WARNING
  - 休市期间允许 price=0 但保留其他字段（yesterday_close/change_pct）
- **收益**：指数格式变更时能日志告警而非静默丢失；休市期间指数数据仍可用

---

### R-122: akshare_extras `_run_with_timeout()` 未能实际超时——`ThreadPoolExecutor` shutdown 等待工作线程完成（HANG）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 永久阻塞（无实效超时）**
- **场景**：`_run_with_timeout()`（行 121-134）使用 `with ThreadPoolExecutor(max_workers=1) as pool:` 上下文管理器。`with` 块退出时调用 `shutdown(wait=True)`，等待工作线程**完成**。当 `fut.result(timeout=15)` 抛出 `TimeoutError` 后，`fut.cancel()` 对**已在运行**的线程无效（返回 False），然后 `with` 阻塞等待该线程完成——超时形同虚设
- **位置**：`src/python/providers/akshare_extras.py:121-134`
- **影响范围**：所有通过 `_run_with_timeout` 调用的 akshare 函数（`get_profit_forecast()`、`get_sector_fund_flow()`）
- **修复建议**：
  - 方案 A：不使用上下文管理器，改为 `pool.shutdown(wait=False)`
  - 方案 B：提交任务后 `fut.result(timeout=T)`，超时后直接 `return None`，让工作线程成为孤儿线程（可接受，max_workers=1 仅此一个）
  - 方案 C：使用 `multiprocessing` 实现真正超时（成本高）
- **收益**：akshare API 永久挂起时不再连带阻塞整个程序

---

### R-123: `_fetch_all_dividends()` 无超时，单个挂起工作线程阻塞整个并发池（HANG）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 永久阻塞**
- **场景**：`_fetch_all_dividends()`（行 344-372）使用 `ThreadPoolExecutor(max_workers=5)`，在 `as_completed` 循环中调用 `future.result()` **无 timeout** 参数。若某只股票的分红 API 永久挂起，该 future 永不返回，整个 `as_completed` 循环阻塞，所有其他股票的分红数据也被拖住
- **位置**：`src/python/providers/akshare_extras.py:362-365`
- **修复建议**：`future.result(timeout=30)` + `except TimeoutError: continue`
- **收益**：单只股票 API 挂起不影响其他股票的分红数据获取

---

### R-124: akshare_extras `_safe_float()` NaN 穿透 → `json.dumps(allow_nan=True)` 输出非法 JSON（WRONG DATA）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 生成非法缓存文件（跨模块数据质量）**
- **场景**：`_safe_float()`（行 429-437）对 `float(numpy.nan)` 返回 `nan`（合法 Python float）。这些值进入 `result` dict 后通过 `cache_set()` → `json.dumps(payload, ...)`（默认 `allow_nan=True`）序列化。`json.dumps` 将 NaN 输出为原始 `NaN` token，该 token **不符合 JSON 规范**（RFC 4626）
- **影响范围**：
  - 当前 `json.load` 默认接受 NaN，同一程序读写无问题
  - 但：①其他 JSON 解析器（前端 JS fetch、其他语言工具）直接崩溃；②若未来 `json.load` 默认行为变更，读缓存也崩溃
  - 影响所有 akshare 缓存：`profit_forecast_*.json`、`sector_flow_*.json`、`dividend_*.json`
- **位置**：跨模块：`akshare_extras.py` → `cache.py:209`
- **修复建议**：
  - 方法 A：`_safe_float` 中 `if math.isnan(v): return None`
  - 方法 B：全局改为 `json.dumps(..., allow_nan=False)` + 修复所有 NaN 数据源
  - 方法 C：自定义 JSONEncoder 替换 NaN 为 null
- **收益**：缓存文件符合 JSON 规范，可被任意 JSON 解析器读取

---

### R-125: akshare_extras `_MEMO_CACHE` 无界字典 → 内存泄漏

- **状态**：◐ 待处理
- **风险等级**：P2 — 内存管理
- **场景**：`_MEMO_CACHE`（行 34）是模块级 dict，每次 `memo_set` 追加条目但无任何清理/淘汰机制。长期运行的会话中（特别是切换多个持仓文件、多次刷新缓存），条目持续累积，可能消耗可观内存
- **位置**：`src/python/providers/akshare_extras.py:34`
- **修复建议**：
  - 使用 `functools.lru_cache(maxsize=128)` 替代手动 dict + 锁
  - 或 `memo_set` 时检查条目数 > 阈值时淘汰最旧的
- **收益**：消除长时间运行的内存消耗增长

---

### R-126: tiantian.py `html[2000:5000]` 硬切片可能错过报告日期

- **状态**：◐ 待处理
- **风险等级**：P2 — 偶发数据丢失
- **场景**：`_extract_fund_meta()` 行 134 从 `html[2000:5000]` 中搜索日期。此切片的假设（日期在前 2000~5000 字符内）对大多数标准基金页面成立。但部分基金页面（含大量 CSS/JS 嵌入、长基金名称、或 QDII/ETF 页面模板不同）可能将报告日期置于切片范围之外
- **位置**：`src/python/providers/tiantian.py:134`
- **修复建议**：移除硬切片，在全文中搜索日期。若担心性能，使用 `re.search(r"(\d{4}-\d{2}-\d{2})", html)` 不带切片即可，正则引擎从索引 0 开始不会扫描整个 500KB HTML
- **收益**：消除报告日期因页面结构差异而静默丢失的情况

---

### R-127: tiantian.py `json.loads('"' + raw_content + '"')` JS 转义序列导致季度持仓解析失败

- **状态**：◐ 待处理
- **风险等级**：P2 — QDII/联接基金持仓数据丢失
- **场景**：行 217 将季报 API 的 JS 字符串用 `json.loads('"' + raw_content + '"')` 解析。若 `raw_content` 含 JS 转义序列（`\"`、`\\`、`\n`、`\x` 等），JSON 解析失败，`json.JSONDecodeError` 被捕获后返回 None。部分 QDII/联接基金的主页面无持仓表格，必须通过季度 API 获取，这导致这些基金的持仓数据全部丢失
- **位置**：`src/python/providers/tiantian.py:216-220`
- **当前处理**：已有 `try/except json.JSONDecodeError`，不会崩溃但会丢数据
- **修复建议**：解析前处理 JS 转义序列，或使用专门反序列化工具（如 `re.sub(r'\\(["\\/bfnrt]|u[0-9a-fA-F]{4})', ...)` 将 JS 转义转换为 JSON 转义）
- **收益**：QDII/联接基金的季度持仓数据不再因 API 响应的 JS 转义而丢失

---

### R-128: reader.py 数据行 `row[1]~row[3]` 在短行上 IndexError 崩溃（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P1 — 程序崩溃（低概率）**
- **场景**：`_parse_workbook()` 行 129-136 通过 `row[0]`~`row[3]` 索引访问每行数据。openpyxl `values_only=True` 对工作表完整矩形区域返回固定长度元组（包含 None），但对某些特殊格式的 Excel（数据区域不连续、仅 A 列有内容的工作表），行长度可能小于 4。此时 `row[3]` 抛出 `IndexError`
- **位置**：`src/python/reader.py:129-136`
- **当前防护**：行 127 `all(cell is None for cell in row)` 已跳过全空行，但无法保护短行
- **修复建议**：访问前检查 `len(row) >= 4`，不满足时 `logger.warning` 并跳过该行
- **收益**：边缘格式的 Excel 文件中不完整数据行不会导致整个持仓读取失败

---

### R-129: generators.py/skeleton.py 多线程并发写入 `_LLM_MODULE_FAILURE` 无显式锁（线程安全）

- **状态**：◐ 待处理
- **风险等级**：P2 — 线程安全
- **场景**：`_LLM_MODULE_FAILURE` dict 从以下路径并发写入：
  - 主线程：`_precheck_all_modules()`（generators.py:565）→ 禁用模块写入 `FAIL_REASON_DISABLED`
  - 工作线程：`_generate_llm_content()`（skeleton.py:231）→ 失败模块写入 `FAIL_REASON_API_ERROR`
  - 工作线程：`_finalize_and_cache()`（skeleton.py:117）→ 空内容写入 `FAIL_REASON_API_ERROR`
  - `_generate_llm_module()`（skeleton.py:302, 309）→ 未配置/禁用写入
- **风险**：CPython GIL 保护 dict `__setitem__` 原子性，不同键写入安全。但若将来实现自定义 `__setitem__` 或改为并发读-改-写模式（如 `_LLM_MODULE_FAILURE.setdefault(key, val)`），则存在数据竞争
- **位置**：`generators.py:565`, `skeleton.py:117/231/302/309`
- **修复建议**：添加 `threading.Lock` 保护写入，或使用 `collections.defaultdict` 显式声明线程使用模式。成本很小，消除未来重构风险
- **收益**：显式线程安全，消除对 GIL 的隐式依赖

---

### R-130: Windows `msvcrt.getch()` 仅在 `except KeyboardInterrupt` 捕获中断（CRASH）

- **状态**：◐ 待处理
- **风险等级**：**P0 — 程序崩溃**
- **场景**：`_get_key_windows()` 行 43 使用 `msvcrt.getch()`，外层 try 仅捕获 `KeyboardInterrupt`。但 `msvcrt.getch()` 在特定条件下（如 stdin 被重定向、`chcp` 代码页不匹配、控制台缓冲区损坏）可能抛出 `ValueError` 或 `OSError`，这些异常未被捕获，导致崩溃
- **位置**：`src/python/tui.py:42-45`
- **修复建议**：`except (KeyboardInterrupt, ValueError, OSError)`
- **收益**：Windows 终端异常状态下按任意键不再崩溃

---

## 全部发现汇总

| 编号 | 风险等级 | 分类 | 问题 | 状态 |
|:----:|:-------:|------|------|:----:|
| R-113 | **P0 崩溃** | **CRASH** | tiantian.py 全宽括号 `（` → `group(1)=None` → `.strip()` AttributeError | ◐ 待处理 |
| R-114 | **P0 崩溃** | **CRASH** | tui.py Linux `sys.stdin.fileno()` 在 stdin 关闭时未保护 → ValueError | ◐ 待处理 |
| R-115 | **P0 崩溃** | **HANG** | tui.py Linux `read(2)` 无超时，ESC 序列不完整时永久阻塞 | ◐ 待处理 |
| R-116 | **P0 崩溃** | **CRASH** | tui_menu.py `config["holdings_dir"]` 裸键访问 → KeyError | ◐ 待处理 |
| R-117 | **P0 崩溃** | **CRASH** | tui_menu.py `endpoint.split("/")[2]` → 无 scheme 时 IndexError | ◐ 待处理 |
| R-119 | **P0 崩溃** | **CRASH** | industry.py `future.result()` 无 try/except → 单次异常杀死整个批量 | ◐ 待处理 |
| R-130 | **P0 崩溃** | **CRASH** | Windows `msvcrt.getch()` 未捕获 ValueError/OSError | ◐ 待处理 |
| R-101 | **P1 错误数据** | **数据质量** | 东方财富备用链路 `yesterday_nav=0.0` → `today_profit` 虚高 | ◐ 待处理 |
| R-102 | **P1 错误数据** | **数据质量** | QDII 纯名称检测，遗漏无 QDII 标签的 QDII 基金 | ◐ 待处理 |
| R-103 | **P1 误导数据** | **数据质量** | 零成本持仓 `profit_rate=0%`（应为 N/A 或 ∞） | ◐ 待处理 |
| R-104 | **P1 错误数据** | **数据质量** | 交易日历 akshare 回退→周末判断，中国长假期间严重偏差 | ◐ 待处理 |
| R-105 | **P1 错误数据** | **数据质量** | `matched_keywords` 6 位数字提取可能误匹配非持仓代码 | ◐ 待处理 |
| R-120 | **P1 错误数据** | **数据质量** | tencent.py `_add_prefix` 丢弃 2/4/8/9 开头代码 → 价格静默 = 0 | ◐ 待处理 |
| R-121 | **P1 错误数据** | **数据质量** | sina.py 硬编码 `var hq_str_` + price>0 过滤 → 指数静默丢失 | ◐ 待处理 |
| R-124 | **P1 错误数据** | **数据质量** | NaN → `json.dumps(allow_nan=True)` 输出非法 JSON，跨模块影响 | ◐ 待处理 |
| R-118 | **P1 崩溃** | **CRASH** | reader.py `getmtime` 文件删除竞争 → FileNotFoundError（低概率） | ◐ 待处理 |
| R-128 | **P1 崩溃** | **CRASH** | reader.py 数据行 `row[3]` 在短行上 IndexError（低概率） | ◐ 待处理 |
| R-122 | **P1 永久阻塞** | **HANG** | akshare_extras `_run_with_timeout` ThreadPoolExecutor shutdown 等待，超时形同虚设 | ◐ 待处理 |
| R-123 | **P1 永久阻塞** | **HANG** | `_fetch_all_dividends` `future.result()` 无 timeout → 单线程挂死全池 | ◐ 待处理 |
| R-106 | P2 中等 | 输入校验 | Excel 页签名无长度/特殊字符校验 | ◐ 待处理 |
| R-107 | P2 中等 | 用户体验 | 熔断器仅内存有效，重启后重置（每次重试链最长 34s） | ◐ 待处理 |
| R-108 | P2 中等 | 内存管理 | `_benchmark_locks` 字典无限增长 | ◐ 待处理 |
| R-109 | P2 中等 | 用户体验 | 大型持仓集 HTML 报告文件过大（可超 10~20MB） | ◐ 待处理 |
| R-110 | P2 中等 | 线程安全 | `_timing_records` 全局列表未加锁，并发写入竞态 | ◐ 待处理 |
| R-125 | P2 中等 | 内存管理 | akshare_extras `_MEMO_CACHE` 无界字典 → 内存泄漏 | ◐ 待处理 |
| R-126 | P2 中等 | 数据质量 | tiantian.py `html[2000:5000]` 硬切片可能错过报告日期 | ◐ 待处理 |
| R-127 | P2 中等 | 数据质量 | tiantian.py JS 转义序列致季度持仓解析失败（QDII 数据丢失） | ◐ 待处理 |
| R-129 | P2 中等 | 线程安全 | generators/skeleton 多线程写入 `_LLM_MODULE_FAILURE` 依赖 GIL | ◐ 待处理 |
| R-085 | P2 中等 | 类型安全 | `main.py:96` `callable` 作泛型标注 | ◐ 待处理 |
| R-090 | P2 中等 | 设计风险 | 配置文件的 `//` JSON 注释依赖特定解析路径 | ◐ 已记录 |
| R-111 | P3 低 | 健壮性 | `cache.get()` 不创建 `data/cache/` 目录 | ◐ 待处理 |
| R-112 | P3 低 | 代码治理 | `classify_holdings` 与 `classify_penetration` 分类逻辑不一致 | ◐ 待处理 |
| R-086 | P3 低 | 代码治理 | `Optional`/`Dict`/`List` 旧式泛型残留（8 文件 23 处） | ◐ 待处理 |
| R-087 | P3 低 | 文档管理 | `plan.md` 已完成函数表格未归档 | ◐ 待处理 |
| R-088 | P3 低 | 导入守卫 | `news_aggregator.py` 未导入的 `Optional` 引用 | ◐ 待处理 |
| R-089 | P3 低 | 构建清理 | `__pycache__` 可能含 stub .pyc | ◐ 待处理 |

---

## 场景覆盖验证矩阵

以下矩阵逐一记录场景分析结果，标注程序是否崩溃（CRASH）、是否产生错误数据（WRONG DATA）、是否无法满足用户需求（FAIL TO MEET NEED）：

| 场景维度 | 子场景 | 程序表现 | 风险项 |
|---------|--------|---------|:------:|
| **空场景** | 无持仓文件 | 友好提示→返回主菜单 | ✅ 正常 |
| | 持仓文件空（0 行） | 提示"未读取到有效持仓" | ✅ 正常 |
| | 持仓份额全部为零 | 明细显示 0 市值/0 盈亏 | ⚠️ R-103 |
| | 无配置文件 | 默认值合并，自动创建 | ✅ 正常 |
| **网络故障** | 全部 API 不可用 | 所有 price=0.0，report 生成但全零，有告警 | ✅ 正常 |
| | 部分 API 不可用 | 失败项=0.0，成功项正常 | ✅ 正常 |
| | 东方财富主API超时→备用链路 | **备用链路 yesterday_nav=0.0** | **🔴 R-101** |
| | 腾讯主API失败→东方财富回退 | 正常降级 | ✅ 正常 |
| | akshare 不可用（节假日） | **交易日历回退→周末判断错误** | **🔴 R-104** |
| **数据质量** | API 返回空/不完整 JSON | 捕获异常 → 降级/回退 | ✅ 正常 |
| | API 返回 429/503 | 重试→最终降级 | ✅ 正常 |
| | Malformed JSONP | JSONDecodeError → 回退备用链路 | ✅ 正常 |
| | QDII 基金名称不含 "QDII" | **误分类为普通基金** | **🔴 R-102** |
| | `matched_keywords` 含非代码 6 位数字 | **情绪归因到错误持仓** | **🔴 R-105** |
| **并发** | 多线程并行更新同一缓存 | 最后写入胜出，偶有旧数据 | ⚠️ 可接受 |
| | 多 Timer 并发写 `_timing_records` | **竞态，记录可能丢失** | **🟡 R-110** |
| | 多线程熔断器状态访问 | 带锁，安全 | ✅ 正常 |
| **节假日/非交易时间** | 春节/国庆闭市 | 信号量显示正常 | ⚠️ R-104 |
| | 中午休市（11:30-13:00） | 正确 → "场内午市收盘(T)" | ✅ 正常 |
| | 盘前（<9:30） | 正确 → 退回上一交易日 | ✅ 正常 |
| | 调休工作日/休息日 | **akshare 失败时判断错误** | **🔴 R-104** |
| **首次运行** | 无 `data/cache/` | `set()` 自动创建，`get()` 返回 None | ⚠️ R-111 |
| | 无 `logs/` | `setup_logger()` 自动创建 | ✅ 正常 |
| | 无 akshare | 函数内 import 失败→捕获→降级 | ✅ 正常 |
| | 无 LLM key | 显示"LLM 未配置"→跳过 | ✅ 正常 |
| | 无持仓目录 | 提示"未找到 xlsx 文件" | ✅ 正常 |
| **LLM 故障** | API Key 过期 | 认证失败→重试→fallback→输出降级 | ✅ 正常 |
| | 内容过滤触发（空返回） | 检测→安抚重试→成功/降级 | ✅ 正常 |
| | 输出截断（max_tokens） | 检测→日志→内容追加警告 | ✅ 正常 |
| | API 持续不可用→熔断器打开 | 下次请求立即跳过 | ⚠️ R-107 重启重置 |
| **报表输出** | 磁盘满 | OSError→try/except 捕获→友好提示 | ✅ 正常 |
| | 权限不足 | PermissionError→`_print_error_with_hint` | ✅ 正常 |
| | 模板文件缺失 | Jinja2 TemplateNotFound→被外层捕获 | ✅ 正常 |
| | 自定义名称含特殊字符 | **Excel ws.title 设置可能崩溃** | **🟡 R-106** |
| | 50+ 持仓大型报告 | **HTML 单页可达 10-20MB** | **🟡 R-109** |
| **用户输入** | Ctrl+C | KeyboardInterrupt→干净退出 | ✅ 正常 |
| | 快速连按菜单键 | `_busy` 标志防重入 | ✅ 正常 |
| | 无效菜单选择 | `_index_by_key` 返回 None→忽略 | ✅ 正常 |
| | 终端 resize | TUI 输出错位但不崩溃 | ✅ 正常 |
| **缓存异常** | 缓存 JSON 损坏 | 自动删除→从 API 重新获取 | ✅ 正常 |
| | `.json` + `.json.gz` 同时存在 | `_write_atomic` 清理旧格式 | ✅ 正常 |
| | 缓存 TTL 交易时段切换 | `get_ttl()` 正确感知交易时段 | ✅ 正常 |
| **代码崩溃** | tiantian HTML 标题含全宽 `（` | **`group(1).strip()` → AttributeError** | **🔴 R-113** |
| | Linux 终端 stdin 重定向 | **`sys.stdin.fileno()` 未保护 → ValueError** | **🔴 R-114** |
| | ESC 键后仅 1 字节跟随 | **`sys.stdin.read(2)` 永久阻塞** | **🔴 R-115** |
| | 配置缺少 `holdings_dir` 键 | **`config["holdings_dir"]` KeyError** | **🔴 R-116** |
| | LLM endpoint 无 scheme 路径 | **`endpoint.split("/")[2]` IndexError** | **🔴 R-117** |
| | 持仓文件在扫描中被删除 | **`os.path.getmtime` FileNotFoundError** | **🟡 R-118** |
| | 行业数据批量获取中单次异常 | **`future.result()` 无 try → 整个批次崩溃** | **🔴 R-119** |
| | 腾讯行情代码前缀 2/4/8/9 | **`_add_prefix` 不处理 → 价格=0** | **🔴 R-120** |
| | 新浪指数 API 格式变化 | **`var hq_str_` 硬编码 → 全部指数丢失** | **🔴 R-121** |
| | akshare 超时形同虚设 | **`_run_with_timeout` shutdown 等 worker 完成** | **🔴 R-122** |
| | 分红 API 单线挂起 | **`future.result()` 无 timeout 阻塞全池** | **🔴 R-123** |
| | NaN 值序列化为非法 JSON | **`json.dumps(allow_nan=True)` 输出 `NaN` token** | **🔴 R-124** |
| | `_MEMO_CACHE` 只增不减 | **无界字典，长期运行内存泄漏** | **🟡 R-125** |
| | 基金页面结构短于 2000 字符 | **`html[2000:5000]` 硬切片错过报告日期** | **🟡 R-126** |
| | 季度 API JS 转义序列 | **`json.loads` 失败 → QDII 持仓数据丢失** | **🟡 R-127** |
| | Excel 数据行不足 4 列 | **`row[3]` IndexError** | **🟡 R-128** |
| | LLM 失败字典并发写入 | **`_LLM_MODULE_FAILURE` 依赖 GIL 隐式保护** | **🟡 R-129** |
| | Windows 终端的 getch 异常 | **未捕获 ValueError/OSError → 崩溃** | **🔴 R-130** |

---

## 结论

### 代码级结论

代码库在正常路径（行情正常、网络正常、配置完整）下运行稳健。1535 测试通过，异常处理覆盖全面，业务降级路径（网络故障/数据异常/首次运行）均已覆盖。

**但第二波深度代码审计发现了 7 个 P0 崩溃点**，在特定异常条件下直接导致程序崩溃或永久阻塞：

| P0 问题 | 触发条件 | 影响 |
|:--------|---------|:----:|
| R-113 tiantian.py 全宽括号 | 持仓基金 HTML 标题含 `（` | `fetch_fund_holdings()` 崩溃 |
| R-114 tui.py stdin 未保护 | Linux 非 TTY 环境（CI/管道） | 启动即崩溃 |
| R-115 tui.py read(2) 阻塞 | ESC 序列不完整 | TUI 永久挂起 |
| R-116 tui_menu.py 裸键访问 | 配置异常 | 菜单显示崩溃 |
| R-117 tui_menu.py split 越界 | 短 endpoint 格式 | LLM 配置显示崩溃 |
| R-119 industry.py 传播异常 | 网络波动 | 整个行业数据批量崩溃 |
| R-130 Windows getch 未防护 | 终端异常 | Windows 键盘输入崩溃 |

**P1 数据质量和阻塞问题**（8 项）：tencent 代码前缀遗漏导致 B 股/北交所价格丢失；sina 硬编码解析导致指数格式变化后全部丢失；akshare 超时形同虚设导致永久阻塞；NaN 序列化输出非法 JSON 跨模块影响；reader 文件竞争和数据行短行崩溃。

### 推荐的行动优先级

**第一阶段（P0 崩溃修复 — 高收益低风险）：**
1. **R-116**（`config["holdings_dir"]` → `.get()`）：1 行改动，消除最易触发的入口崩溃
2. **R-117**（`endpoint.split("/")[2]` → 安全解析）：1 行改动，消除 LLM 配置显示崩溃
3. **R-114**（tui.py stdin 保护）：约 3 行改动，消除 Linux 非 TTY 崩溃
4. **R-130**（Windows getch 异常捕获）：1 行改动，消除 Windows 异常崩溃
5. **R-119**（industry.py 加 try/except）：约 5 行改动，消除批量数据崩溃

**第二阶段（P0 特定条件崩溃 — 中收益中风险）：**
6. **R-113**（tiantian.py 全宽括号正则修复）：约 3 行改动，消除中文基金名称崩溃
7. **R-115**（tui.py read(2) 超时）：约 5 行改动，消除 ESC 序列挂起

**第三阶段（P1 数据质量和阻塞 — 中高收益）：**
8. **R-120**（tencent.py 补全 2/4/8/9 前缀）：B 股/北交所价格恢复
9. **R-122**（`_run_with_timeout` 实际超时）：消除 akshare 挂起拖死主程序
10. **R-124**（NaN → None）：缓存文件 JSON 合规
11. **R-123**（分红 API 超时）：消除分红获取挂起
12. **R-121**（sina.py 格式校验告警）：指数格式变化时非静默丢失

**第四阶段（P1 场景问题和 P2 质量改进）：**
13. **R-101**（today_profit 虚高修复）
14. **R-103**（零成本收益率 → N/A）
15. **R-125**（`_MEMO_CACHE` 添加 LRU 淘汰）

**其余 P2~P3 项**（R-102/R-104/R-105/R-106/R-107/R-108/R-109/R-110/R-126/R-127/R-129/R-085/R-086/R-087/R-088/R-089/R-090/R-111/R-112）：可在后续迭代中按需处理，无紧急风险。
