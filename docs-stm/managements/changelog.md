# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.14-dev] - 开发中（未发布）

### 死参数/遗留文件清理：html 渲染签名瘦身 + 遗留重复文件删除 + warm_cache 移除（2026-08-16）

三项自审独立跟踪项（rf-282/283/284，源自 rf-272 全仓 ARG001 死参数处置后遗留）一并收尾：

- **rf-282 渲染器签名瘦身**：`html_renderers._render_llm_content_section` 上下文参数从 15 个删至 2 个（`enable_llm`/`llm_content`）。函数职责仅为解包预生成的 4 元组 + 开关判定；其余 13 参（force_llm/a_indices/us_indices/总额/持仓/穿透/板块资金流等）均由编排层预置或由下游直接读取，属死参数。同步重构 `html_writer.py` 调用点。
- **rf-283 遗留重复文件删除**：`report/_pipeline.py`（25KB，标注「遗留重复文件」）确认为死代码副本——零生产引用，活代码在 `report/_llm_news.py`。删除文件（`git rm`），`test_pipeline_utils.py` 测试迁移至活模块 `_llm_news.py`（`_collect_llm_future_result`/`_collect_news_future_result`/`_report_llm_module_results`），防双份漂移。
- **rf-284 warm_cache 移除**：`orchestrator.generate_report.warm_cache` 参数声明但函数体内从未使用，唯一传入方是 CLI `--warm` 标志（web/TUI 不消费；TUI 新资产预热走独立 `check_and_warm_for_new_assets` 机制）。删除 `--warm` 标志 + `warm_cache` 参数 + 测试中 6 处引用同步清理。
- **验证**：`test_pipeline_utils.py` 6 例通过；report+cli 全量单元测试 1596 例通过。
- **自审登记**：review-findings.md 三项（rf-282/283/284）由 P3 待办区转「已解决」区。

### extract-test-failures.py 修复：pytest-html 报告解析崩溃（2026-08-16）

- **缺陷（rf-281）**：`_find_json_blob` 用手工花括号扫描器提取 `data-jsonblob`，假设 JSON 引号以反斜杠转义；但 pytest-html 将 JSON 内引号编码为 HTML 实体 `&#34;`，扫描器从不进入字符串态，日志内嵌 HTML 的 `}` 在 depth==0 时提前截断 → `json.loads` 报 `JSONDecodeError: Extra data`，**全绿报告也崩溃**，导致依赖此工具的失败用例提取流程不可用。
- **修复**：改为按属性值整体截取——`data-jsonblob=` 起始引号到下一个裸引号之间即为完整 JSON（blob 内引号均为实体编码，不会出现裸引号提前终止属性），取回后统一解码 `&#34;/&gt;/&lt;/&amp;`。
- **回归测试**：新增 `src/test/unit/scripts/test_extract_test_failures.py` 4 例——实体引号 blob 完整提取且 JSON 可解析 / 日志内嵌花括号不干扰 / 无 data-jsonblob 返回 None / 属性无结束引号返回 None 不崩溃。已验证全绿报告 `--summary` 汇总正常、失败报告与 `--json` 输出均正常。
- **测试统计同步**：按 `scripts/collect-test-coverage.py` 实时收集快照（总 5474）同步 `test-coverage.md`（模式总计 `all` 5461→5474、`unit`→5165、`verify`→3433、`dev-verify`→2019、`standard`→4487；unit 子标记 `unit_llm` 754→760、`unit_news` 188→191、`unit_scripts` 190→194；跨类 `llm` 609→615，其中 llm/news 增量来自 e777ca5f/4c4e156b 新增用例）与 `folders.md`（测试代码 306→307 文件、86,228→86,536 行；测试用例 5,461→5,474 个）。
- **自审登记**：review-findings.md 新增 rf-281 已解决条目。

### dedup 校准脚本路径修复 + 基于最新数据重校准（2026-08-16）

- **路径不一致（rf-279）**：`scripts/calibrate-dedup-threshold.py` 默认读取 `data/cache/dedup_anchors.jsonl`，而 `src/python/providers/news_dedup.py` 自 commit `4e95d595`（2026-07-30）起将锚点写入 `data/calibration/dedup_anchors.jsonl`，脚本从未同步 → 校准报告基于 7-29 旧快照（119654 条），与当前去重行为脱节。修复：脚本默认 `--file` 路径改为 `data/calibration/dedup_anchors.jsonl`，与代码写入路径一致。
- **重校准结论（基于最新 109018 条锚点）**：
  - cross_skip 总量 20785 条，但 87% 为 bg=0/1（无实体重叠的安全跳过）；真实漏判候选 bg≥2 有 2239 条，与旧数据（2154）持平，未恶化。
  - **维持现阈值**：bg=2 ratio≥0.35 的 523 条候选抽样人工审查，真实重复率仅约 25%（多为"关税退款""A股白酒领涨""原油上涨"等，其余为不同公司回购/财报/目标价误判候选）。降到 0.35 会误合并约 390 条不同事件，不值得。当前 bg=2 ratio≥0.40 梯度补偿已捕获 196 条高置信重复。
  - 跨源 bigram≥4（4753 条）与同源 bigram≥4 阈值安全；跨源 bigram=3 边界 2418 条中仅 354 条 ratio≥0.40，降阈值需求不大。
  - 可选优化（非本次必改）：bg≤1 ratio≥0.40 虚高噪声从 82→1468 条（+18x），是共享日期/事件名/财经关键词导致的 SequenceMatcher 比率虚高，可进一步改进归一化。
- **自审登记**：review-findings.md 新增 rf-279 已解决条目。

### dedup 锚点重复计数修复：写入层 + 统计层双重去重（2026-08-16）

重校准中发现锚点文件同一对 (source,title) 多轮运行重复追加（实测 61.6% 为重复记录，同一对最多重复 63 次），导致校准报告绝对数字严重失真（cross_skip bg=0 从真实 279 虚增至 13800）。修复为写入层 + 统计层双重去重：

- **写入层去重（`news_dedup.py`）**：新增进程级 `_WRITTEN_ANCHOR_KEYS` 已写 key 集合 + `_load_written_keys()` 惰性加载（首次 flush 前读一次现有文件，~110k 行/35MB 一次性成本），`_flush_anchors` 写入前按 `_anchor_key`（source 对 + 标题对，顺序无关）比对，只写新 key、写后入集合 → 跨会话、跨轮次拦截重复，无需每次读全文件。
- **统计层去重（`calibrate-dedup-threshold.py`）**：`load_anchors` 按 (source_a, source_b, title_a, title_b) 顺序无关 key 去重，处理存量污染文件 → 校准锚点 109018→41761 条。
- **测试隔离**：conftest 增加 `_ANCHOR_PATH` 路径重定向（`_isolate_sensitive_paths`）+ `_auto_reset_anchor_state` autouse fixture 重置锚点单例；`test_news_sources.py` 新增 `TestFlushAnchorsDedup` 3 例（同对跨轮只写一次 / 不同对正常追加 / key 集合缓存生效）。
- **自审登记**：review-findings.md 新增 rf-280 已解决条目。

### fact_checker 校验层修复：条件阈值误修正 + 持仓简称匹配漏检（2026-08-16）

排查 601939「130.61%」/600900「200%」两处报告数值时定位到 fact_checker 两处缺陷，均已修复并配回归测试：

- **条件阈值误修正（rf-277）**：穿透深度分析原文「收益率超过 200% 后可考虑部分止盈」中的 200% 是**止盈目标阈值**（非对 600900 当前收益率的陈述），旧逻辑因"止盈"位于数值之后较远处（超出 `_TRIM_TARGET_KEYWORDS` 的 [-15,+5] 邻近窗口）未命中止盈语境，误将 200% 归因到最近名称"长江电力(600900)"并修正为 59.2%——把正确文本改错。修复：`_constants.py` 新增 `_CONDITION_TRIGGER_KEYWORDS`（超过/达到/突破/接近/降至等），`_context._is_trim_target_context` 增加「触发词（前 12 字符）+ 后置调仓动作词（后 25 字符）」双条件联合判定；仅有触发词无动作词（如"收益率超过200%，风险很大"）仍按收益率校验，不过度跳过。
- **持仓简称匹配漏检（rf-278）**：辩论综合原文「华安纳指+180.5%、建设银行+180.55%」——华安纳指（040046）实际收益率 130.61%，LLM 反向串位写成 180.5%；旧逻辑 `_locate_subject_code` 仅按持仓全名匹配，"华安纳指"匹配不到"华安纳斯达克100ETF联接基金A" → 主体定位失败回退全局最近邻，180.5 恰命中 601939 真实值 180.55 → 误判通过、反向串位漏检。修复：`_constants.py` 新增 `_NAME_ALIAS_MAP` 简称归一化表（纳指→纳斯达克、建行→建设银行等），`_utils._locate_subject_code` 增加归一化后按持仓名称核心名（`_extract_core_name`，首个 ASCII 字母/数字前汉字部分）前缀匹配，归因到实际品种。
- **回归测试**：`test_fact_checker.py` 新增 `TestTrimTargetContext` 2 例（条件阈值不误修正 + 无动作词仍校验）+ 新增 `TestNameAliasNormalized` 4 例（华安纳指错误值修正/正确值通过/建行简称不误伤/run_fact_check 整链路）；全量 115 例通过。
- **自审登记**：review-findings.md 新增 rf-277 / rf-278 已解决条目。

### LLM 定价支持 DeepSeek 峰谷定价 + 时段可配置（2026-08-15）

- **定价更新**：`MODEL_PRICING` 中 `deepseek-v4-flash` / `deepseek-v4-pro` / `deepseek-chat` 三模型按 DeepSeek 官方 2026-08-17 峰谷定价更新——base（闲时）价 + 新增 `peak` 高峰价子段（闲时价 ×2）。如 flash：输入 ¥1.5/输出 ¥4.5/缓存命中 ¥0.05，高峰 ¥3/¥9/¥0.10。
- **峰谷时段**：新增 `PRICING_PEAK_PERIODS` / `PRICING_IDLE_PERIODS` / `PRICING_TIMEZONE` 常量（默认高峰北京时间 09:00–12:00、14:00–18:00，闲时为其外全部时间），`estimate_cost()` 新增 `at_time` 参数按时段计费（缺省当前时间、按定价时区换算，naive 视为已在定价时区便于测试）。
- **配置可覆盖**：`llm_settings.json → pricing` 段新增 `timezone` / `peak_periods` / `idle_periods` 三个非模型键，时段与时区可自定义；模型条目可携带 `peak` 子段覆盖高峰价。`reload_pricing()` 就地更新时段列表，保持对象身份稳定。
- **回归测试**：`TestPricing` 新增 6 例峰谷用例（高峰/闲时价差、边界闭区间、无 peak 模型不受时段影响、缓存命中按 peak 费率、默认时段、自定义时段+模型价格覆盖）。
- **文档同步**：`how-to-config-llm.md` 定价表与 Token 消耗参考按新价更新 + 峰谷说明；`llm-technical.md` §10 新增峰谷定价小节、附录 B 定价表更新。

### v0.10.1+ 改动文档一致性审计修复（2026-08-15）

- **A 类事实错误**：README `enable_action` 默认值修正（默认开、菜单 P 可切换，原误述为默认关）；folders.md 统计与目录树同步 6 个新测试文件（`test_llm_settings`、`test_history_snapshot_namespace{,_edge}`、`test_snapshot_namespace_consumers`、`test_holdings_update{,_edge}`）；reports-instruction 浮盈/已实现盈亏文案修正。
- **B 类用户文档缺口**：reports-instruction 补完整「成本流水分析」章节（开关 `report_submodules.cost_lots`、交易/分红流水表头、XIRR/成本分档/分红累计输出、快照近似模式文案）+ HTML TOC 加 LLM 标记说明；how-to-use-web-mode 补数据源健康代理诊断提示与产物写锁检测说明；datasource 补行业名归一化说明（剥离申万 Ⅰ~Ⅳ 后缀）；how-to-config `history.fetch_mode=off` 行补警告行为说明；how-to-start 持仓文件格式补可选流水页签块引用；faq 已实现盈亏答案引用 XIRR/cost_lots。
- **C 类管理文档**：requirements 新增 R-ENV-05（CLI 包装脚本 cli.sh/cli.ps1）、R-WEB-09（Web 试算隔离）、§6.4.20 成本流水（R-CFL-01~04）、增强 R-OUT-07（report_section_order 细节）；technical 新增 §1.7.6 便捷入口包装脚本、语义命名表补 `report_section_order`/`generators_news` 行；test-coverage 测试计数快照刷新至实时值（`all` 5,455→5,461）。
- **自审登记**：review-findings.md 新增 rf-276 已解决条目。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.13（2026-08-04 ~ 2026-08-14）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
