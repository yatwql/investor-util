# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.8-dev
> **编号源**：`rf-next = 470`（新增问题取此编号，完成后更新为 +1；已用最大 rf-469，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> `src/test/conftest.py` 曾达 872 行（超硬上限），已于 2026-09-26 拆分至 672 行 + 新模块 225 行（详见「已解决问题」rf-448）。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 704 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-09-26 实测 704，较 2026-09-10 的 666 增长 38——plan-50 财报域槽位/plan-57 等注册项增补） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 578 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-09-26 实测 578，较登记值 564 增长 14） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 605 | 维持现状（仍在 500-800 区间内聚；2026-09-26 实测 605，较登记值 542 增长 63，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 621 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-09-26 实测 621，较 2026-09-10 的 544 增长 77——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 556 | 维持现状（render 函数属同一渲染域；2026-09-26 实测 556，较 2026-09-10 的 521 增长 35） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 551 | **已跨入 500-800 可选优化区间**（2026-09-26 实测 551，较 2026-09-10 的 405 增长 146——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-86** | `cache/operations.py` | 633 | 500-800 可选优化区间（2026-09-26 实测 633，与 2026-09-10 持平） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 574 | **已跨入 500-800 可选优化区间**（2026-09-26 实测 574，较 2026-09-10 的 427 增长 147——持仓基本面合并页签等增补）；暂维持现状 | 页签编排可进一步下沉到独立 writer（后续择机） |


#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

#### P2C — 文档与配置口径（2026-09-24）

> 无待处理项（`rf-420` 已修复，见「已解决问题」区）。
## 已解决问题

### 已解决待归档（v0.11.8-dev）

> 暂无（v0.11.7 批次 rf-457 ~ rf-460 已随发布归档至 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)）

| # | 问题 | 修复 |
|---|------|------|
| **rf-461** | **provider 层把传输级失败降级成返回值，使链路的重试/熔断/文案全部失效**（用户贴日志报「备用也不好用」）：`providers/datasink.py::_request` 把**网络异常**（`_ssl.c:1012: The handshake operation timed out`）与「代码级空结果」一律 `return None`（docstring 还写明「不计熔断」），而链路的传输级判据**只认异常**（`chain._try_provider_fetch` 捕获异常 → `TRANSPORT_FAILURE`；返回值哨兵无判据分支）——实测后果：① **同源重试不触发**（`retry_if_result=lambda r: r is TRANSPORT_FAILURE` 永不命中）；② **熔断与可用性统计不计**（`record_failure` 仅在 TRANSPORT_FAILURE 路径）→ 主源持续不可用也不熔断，每篇文档白等 20s 超时且刷屏；③ **诊断文案误导**（SSL 握手超时报成「返回空」，本次排查即被误导）；④ datasink **连连接级重试都没有**（cninfo/tencent/eastmoney_industry 均有）——一次握手被丢即整篇丢失，而 cninfo 注释已实测「首个连接常被丢弃，重试即成功」。同源缺陷还有 `hithink._request`、`_utils.run_with_timeout`（akshare 路径） | ① `datasink._request` / `hithink._request` 抽出 `_get_with_transient_retry`：**每次尝试前**取限速许可 + `core/retry` 统一原语连接级重试（镜像 cninfo：3 次、线性 1s/2s），重试耗尽后**上抛**，代码级结果（401/403/404/非 200/非 JSON/业务 code≠0）仍返回 None 不计熔断；② 直连调用点补护栏（不因上抛中断报告）：`financial_report._fetch_index` → 转巨潮备源、`_fetch_sections` → 返回 None 回退偏好名直取、`financial_indicator.fetch_indicator_series` / `fetch_hithink_indicator_series` → 转下一兜底；③ `_utils.run_with_timeout` 新增 `raise_on_failure`（默认 False 维持既有 None 契约；链路消费方 `akshare_financial` 开启上抛）；④ 回归 +9 例（datasink/hithink：重试耗尽上抛且断言尝试次数与退避序列、首次握手失败重试即成功、非瞬时异常不重试；`run_with_timeout` 两种模式；`akshare_financial` 上抛且断言 `raise_on_failure=True`；编排层三处护栏）；⑤ 文档口径修正（`technical.md` §2.2.1 新增「传输级必须上抛」契约 + datasink 降级段落、`datasource-reliability.md` datasink/hithink 降级与重试条目、`requirements.md` R-DATA-07 补两类失败分界） |

> **已评估未改（登记待办）**：`providers/cninfo.py::_with_transient_retry` 重试耗尽后仍 `return None`——同样是「传输级降级成返回值」，但其直连调用点有多处（`financial_report._backup_candidates` / `_fetch_index` 备源分支 / `check_sources` 探针），改动面比 datasink 大；且它已有连接级重试（本轮的可靠性收益已拿到），故本轮不动，待专项处理时连同上述调用点一次性加护栏。

| **rf-462** | **连接级重试未区分「快速失败」与「挂起」，把失败等待放大 3 倍**（用户报「现在运行测试，怎么那么久了」）：rf-461 引入的连接级重试只按「是否瞬时异常」判据重试，未区分两类传输失败——**快速失败**（连接被拒/重置/DNS 立即失败，重试有效）与**挂起**（等到超时，重试只会线性放大等待）。实测（不可路由地址 + 2s 预算）：挂起型单请求 6.0s / 3 次尝试，按真实 20s 预算即 63s（+3s 退避），链路再同源重试 1 次 ≈ 83s；巨潮（cninfo）更早就有 3 次盲重试（63s/请求，既有问题）。实测确认**非取数路径不受影响**：单元套件 101s / `verify,regression` 31.3s（与改动前 30.5s 持平），变慢的是「主机不可达时的失败路径」。 | ① `providers/_utils.py` 新增共享判据 `build_transient_retry_judge(elapsed, timeout)` + `HANG_ELAPSED_RATIO = 0.5`：瞬时异常**且**本次尝试耗时 < 超时预算一半 → 可重试；否则判「主机不可达」不再重试，并记 WARNING「连接挂起 Ns（≥超时预算一半），判定主机不可达，不再重试」；② `datasink` / `hithink` / `cninfo` 三处连接级重试改用该判据（口径统一，判据单源）；③ 回归 +3 例（假时钟模拟挂起耗时：断言仅 1 次尝试、**无退避等待**（sleep 被换成 `pytest.fail`）、留下「连接挂起」日志）；④ 文档：`technical.md` §2.2.1 新增「挂起型不重试」条目，`datasource-reliability.md` datasink/hithink/cninfo 与 `datasource.md` 同步，`faq.md` 日志问答补「挂起即不再重试」解释。**效果**：挂起型单请求 63s → 20s（一次超时），且计入熔断 → 连续 3 次后本会话跳过，整轮报告不再逐篇白等 |
| **rf-463** | **CI「安装依赖」步偶发失败（3.12 单独挂掉）**：`test (3.12)` job 在 `pip install -e ".[test]"` 步失败而测试步未执行（同 run 内 3.11/3.13 装成功；上一提交 a1e0908d 的 3.12 为全绿，本次未改任何依赖声明）。查明根因面：akshare 在 Linux 上的依赖 **`py-mini-racer>=0.6.0` 与 `jsonpath` 均无 wheel、只有 sdist**（前者需源码编译 V8），该步是全流水线最脆弱、耗时最长的一环，下载/编译抖动即整 job 失败；此外 GitHub Actions 日志端点需授权，免授权仅能拿到「exit code 1」，定位只能靠复现（本轮即因 API 限流受阻） | ① 四个 job 的安装步统一加下载重试与更长超时（`--retries 5 --timeout 60`，pip 自升级同步）；② 定位手段仍靠之前引入的 annotation 机制（失败用例可免授权读取）——安装步失败则只能靠重跑确认偶发；③ 若后续再现，备选方案：为 CI 预置 wheels 缓存或把重依赖改为可选安装（另行评估） |
| **rf-464** | **LLM 关闭时「LLM API 用量」章仍渲染，且无序号、被排到最前**（用户报「章节数由 17 降至 12 章；llm api 用量还没有序号了，又摆在最前面」）：`report_template.html` 的 `sec-llm_usage` 容器**漏加可见性守卫**（其余 4 个 LLM 章由 `section_visible("global_macro")` 统一包住），`both`/`basic`（LLM 关闭）下该章照样输出；此时它不在 `_compute_section_visibility` 的 `visible_numbers` 中，`section_numbers['llm_usage']` 为 Jinja Undefined → 标题渲染成「、LLM API 用量」（序号空）；容器 `.container{display:flex;flex-direction:column}` 靠 `style="order:N"` 排序，空值输出为非法的 `order: ;` 被忽略 → `order` 回退 0 → 排到所有 `order:1..N` 之前。L 模式下该章有数据（编号 17、末位），故长期未暴露。**注**：用户同期确认 17→12 章是「用 CLI 包装脚本默认 `both`（不含 LLM）」所致，脚本默认**保持 both 不变**，非缺陷 | ① `report_template.html` 给 `sec-llm_usage` 补 `{% if section_visible("llm_usage") %} … {% endif %}` 守卫，LLM 关闭时整章不渲染（与其余 LLM 章一致）；② 回归 +2 例（`test_html_report_structure.py`：不可见时 `soup.find(id="sec-llm_usage")` 为 None 且页面不出现 `order: ;`；可见时正常渲染且 `order` 为末位序号），并把 `test_all_invisible` 改写为「只渲染 4 个 always 章容器」的结构断言；③ `folders.md` 统计表行数同步 |
| **rf-465** | **场景测试 fixture 的时间炸弹：硬编码绝对日期 + 停更判定用真实今天**（`dev-verify` 暴露的 1 个既有失败 `test_pipeline_style_factor_regression.py::TestComputeFactorExposureData::test_contract_available_with_full_data`）：`_klines()` 默认 `start="2026-03-01"`（末根 K 线 2026-05-29），而 `compute_factor_exposure_data` 的停更判定用 `datetime.now()`（当日 2026-09-29），阈值 86 交易日；离线桩（`offline_external_sources`）将交易日历置空 → `count_trading_days_elapsed` 回退「仅排周末」近似计数 = 87 > 86 → 三个因子全被判停更剔除 → 有效因子不足 → `available=False`。**非网络/数据源问题**（外网均 mock，`fetch_index_history` 走合成 K 线）。真实交易日历口径为 85，仅差 1 个交易日，即该用例本就随时间必然变红 | ① `_klines` 改以 `end: date \| None = None` 锚定「今天」（`last = end or date.today()`，向前推 `n-1` 天），合成 K 线始终新鲜；② 回归 +1 例 `TestMockKlinesFreshness::test_klines_anchored_to_today_and_not_stale`（断言末根日期 == 今天 且 距今天数 ≤ 停更阈值）；③ 数据快照同步：`folders.md` 测试代码行数 + 用例数 7,938→7,941，`test-coverage.md` `scenario_basic` 152→153、报告生成/`unit_report` 1,983→1,985 |
| **rf-466** | **00 重叠区场外基金被当 A 股取数：价格缓存串味致报告显示错误价格**（用户报「002943 你拿到了 28.98，官方净值应 4.7727」）：`002943` 既是深市股票「宇晶股份」也是场外基金「广发多因子灵活配置混合」（实测 `fund_hold_002943` 的 98 个成分股含该代码）。① `fund_style_classify._prefetch_extended_data → _tencent_extended` 取基金成分股扩展数据时调 `fetch_market_data(code)` **未传 expected_name** → 名称消歧被跳过 → 判 `price_stock` → 把宇晶股份 28.98 写进**路由无关的共享缓存键** `price_{code}`；② 用户持仓该基金收盘后走 CACHE_ONLY 只读缓存 → 读到 28.98。同源缺陷遍布「按持仓过滤 A 股」的各域路由（历史 K 线、分红、行业关键词、估值分位、风格扩展数据）——均只按代码前缀判定，绕过已有的 `is_otc_fund_by_name`。**非代码回归**（窗口内相关文件零改动），系潜伏缺陷被数据触发（09-26 前 push2 返回市值/PE 未触发腾讯降级，09-28 push2 对 002943 只回行业、pe/mcap 全 null 触发降级） | ① `core/code_utils.py` 新增 `is_a_share_stock(name, code)`（`is_a_share_code` 且非场外基金），作「持仓按 A 股处理」唯一判据（代码类型判定中心化）；② `price._price_cache_key(code, data_type)` 按路由分域（`price_stock_{code}` / `price_fund_otc_{code}`）+ 新增 `resolve_price_route`；`fetch_market_data` 首跳与降级分别用各自键，`fetch_market_data_cached` 会话域改按路由；③ 历史 K 线（`portfolio_history`、`_report_factor_metrics`）、分红（`category`、`html_builders`、`cache/operations`）、行业关键词（`news_correlation`）、估值分位（`orchestrator`）、风格扩展数据（`fund_style_classify`）、资产构成图兜底（`chart_data_builder`）改用 `is_a_share_stock`；④ 回归 +8 例；⑤ 文档：`technical.md` §2.4.1 路由/缓存分域 + §6.5 原语清单 + 附录 C 键名、`how-to-config.md`、`tui/handlers_cache.py` |
| **rf-467** | **rf-466 同源残留：两处仍按代码前缀判 A 股**（rf-466 收尾时登记）：① `fund_style_classify._get_industry_avg_pe` 按 `is_a_share_code` 过滤基金成分股代码 → FOF 成分含 `00` 重叠区场外基金时会取到同代码股票行业/PE；② `fetcher/industry.py::batch_fetch_industry_data` 内部只按代码前缀过滤，且 `cache/operations` 的 `_refresh_industry_cache` / `_refresh_dividend_cache` 直接把用户全部持仓代码传入（含场外基金 002943）→ `cache --update position` 会把基金当股票取行业/分红 | ① `_get_industry_avg_pe(codes, names_by_code=None)` 支持名称判定，`classify_fund_style` 传入 `{code: name}`；② `cache/operations._refresh_industry_cache` / `_refresh_dividend_cache` 改用 `is_a_share_stock(h.name, h.code)` 预过滤（`batch_fetch_industry_data` 内部的代码前缀过滤仅作防御）；③ 回归 +4 例（行业平均 PE 名称过滤 + 新建 `test_cache_refresh_routing.py` 三例） |
| **rf-468** | **过去 24 小时实现的技术债审计（rf-461/462/466/467 引入）**：① **连接级重试脚手架三份复制**——`datasink._get_with_transient_retry` / `hithink._get_with_transient_retry` / `cninfo._with_transient_retry` 各自复制了策略常量 `_CONNECT_RETRY_POLICY`、耗时统计、挂起判据+警告、重试日志、限速许可前钩子（rf-462 只统一了判据 `build_transient_retry_judge`，脚手架仍三份）；② **`batch_fetch_industry_data(names_by_code=…)` 无生产调用方**（rf-467 新增、仅测试引用，属未用 API）；③ `report/market_value.py` 跨模块引用私有 `_price_cache_key`（rf-466 引入） | ① `providers/_utils.py` 新增 `CONNECT_RETRY_POLICY` + `with_connect_retry(request_fn, timeout, log_tag, label, before_attempt)`，datasink/hithink/cninfo 改用共享脚手架（cninfo 保留「直连降级为 None」契约于调用点）；② 移除 `batch_fetch_industry_data` 的 `names_by_code` 参数（调用方预过滤 + 网关前缀防御）；③ `fetcher/price.py` 新增公开 `price_cache_key(code, expected_name)`，`market_value` 改用公开入口；④ 回归 +1 例（公开 `price_cache_key` 路由解析），provider 测试改为 patch `providers/_utils.time` / `_utils.CONNECT_RETRY_POLICY` |
| **rf-469** | **本地 dev-verify（P0）绿、GitHub CI 红**（用户报「github ci 报错」）：① rf-466 把价格缓存/会话域改为按路由分域后，**4 条 `edge` 用例**仍按旧路由无关会话域 `"price"` 预填缓存（`get_registry().session_cache_set("price", "561910", …)`），CACHE_ONLY 读 `price_stock` 域落空 → 降级 live → 4 例失败；而 dev-verify（P0）**不含 `edge` 标记**，本地不复现，只有 CI `portability` job（跑全量 `src/test/unit`）暴露。② rf-466/467/468 编辑的 4 个文件未跑 `ruff format`，CI `format` job 报「Would reformat」 | ① `test_market_value_strategy_edge.py` 改用公开 `resolve_price_route(...)` 解析会话域（4 处，不硬编码路由名）；② `ruff format` 4 个源文件（`cache/operations.py` / `fetcher/price.py` / `report/fund_style_classify.py` / `tui/handlers_cache.py`）；③ `folders.md` 行数快照同步。**教训**：改动报告层缓存键/会话域后，本地须跑「全量 unit（含 edge）」而非仅 dev-verify（P0 不含 edge） |

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — rf-380 ~ rf-456（v0.11.0 ~ v0.11.6 批次：v0.11.1~v0.11.3 于 2026-09-18 / 2026-09-24 并入，v0.11.4~v0.11.6 批次（rf-428 ~ rf-456）于 2026-09-26 并入）
- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.20（2026-08-04 ~ 2026-09-15）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
