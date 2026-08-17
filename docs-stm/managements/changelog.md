# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.15-dev] - 开发中（未发布）

### 开发版本切换（2026-08-17）

- 发布 v0.10.14 后，APP_VERSION 与全部管理文档版本头切换至 v0.10.15-dev。待办：rf-288（test-runner `all_no_unit` marker 补 `and not live`，修复后 bench `--update-docs` 回填稳定不反复）。

### scripts/ 命名统一与清理（2026-08-17）

- **脚本重命名 kebab-case**：7 个 snake_case 脚本统一为 kebab-case（`git mv` 保留历史）——`test_runner.py`→`test-runner.py`、`perf_report.py`→`perf-report.py`、`perf_view.py`→`perf-view.py`、`llm_hallucination_sampler.py`→`llm-hallucination-sampler.py`、`svg_geom_check.py`→`check-svg-geom.py`、`svg_pixel_check.py`→`check-svg-pixel.py`、`svg_text_overflow_check.py`→`check-svg-text-overflow.py`。同步更新脚本自引用、`src/` 注释、live/unit 测试、CI、CLAUDE.md/README/用户手册/管理文档全部引用；测试文件 `test_test_runner_*.py` 按约定不重命名。
- **developer-guide 补 `probe-push2.py`**：速查表 + 诊断类章节补齐东方财富 push2 连通性探测条目（含 curl 对照判读）。
- **删除低价值脚本**：`diagnose_gemini_proxy.py`（硬编码代理 IP `10.22.207.29:10037` 的单机排查临时产物）+ `reproduce_factcheck_corrections.py`（一次性事实校验修正复现，docstring 自认"不属于仓库交付物"，功能已被 rf-289 回归测试 `TestDescriptiveTailMatch` 正式覆盖）。同步移除 developer-guide 速查表行 + 章节、folders.md 目录树行，辅助脚本统计 23→21 / 7,394→7,165。

### dedup 跨源误合并率修复（rf-290）（2026-08-17）

- **问题**：42560 条锚点分层随机采样人工判定，跨源合并区（cross_merge bg3/bg≥4/cross_merge_bg2/cross_safe 共 4180 条）约 70-80% 为误合并，每条误合并即报告丢失一条独立新闻：① `_STOP_BIGRAMS` 未覆盖财报/回购/指数/预警/地震等模板词，不同公司同类新闻天然共享 3-6 bigram（"美的集团累计回购A股股份" vs "中远海控累计回购A股股份" bg=5 误合并）；② 英文占位符统一 `_tk_` 使任意英文 token（msci/vn）共享相似度虚高 ratio；③ 候选区门槛 0.30 过低，跨源方向对立报道（"暂缓加息" vs "将加息"）也被合并；④ bg=2 梯度（ratio≥0.40）误合并率 ~85%（英伟达 Vera Rubin vs 英伟达投资）；⑤ 安全区 0.50 直接合并在 0.50-0.60 段误合并 ~40-50%（行云科技 vs 亿田智能 共享"算力服务合同"骨架 ratio 0.542）。
- **修复**（`src/python/providers/news_dedup.py`）：
  - `_STOP_BIGRAMS` 扩至 ~280 个模板词（财报/回购/指数/预警/地震/评级/货币单位/通用业务词），提取中文 bigram 前整体掩码替换为占位符（`_mask_stop`），消除模板词贡献并杜绝"累计|回购"跨词边界 bigram（计回）泄漏
  - 英文占位符按长度分桶（`_tk2_`/`_tk4_`/`_tk6_`），不同长度英文词不再共享相似度
  - 跨源候选区门槛 0.30→0.35；bg=2 梯度改为 ratio≥0.375 且共享 bigram 含英数/数字 token（CPI/PPI、荣耀IPO、SpaceX 类专名真重复），纯中文公司名共享不触发
  - 安全区分级：ratio≥0.65 且专名 bg≥1 直接合并；0.50~0.65 需专名 bg≥2（防不同公司同模板 ratio 0.7+ 误合并）
  - 新增跨源方向对立词对检测（上涨/下跌、加息/降息等分属两标题且共享实体 → 不合并，记录 cross_opposite）
  - `_normalize_title` 保留空格防英文 token 粘连（"Blackwell AI"→blackwellai）+ 剥离"N级"（地震级数）+ 孤立年份数字不作专名 token
  - ratio 双向取 max 消除 SequenceMatcher 贪心匹配方向不对称（含多英文占位块时 ratio(a,b)≠ratio(b,a) 差异可达 0.18）
- **回归测试**：`test_news_sources.py` 新增 `TestDedupFalseMergeGuard` 9 例（同名不同事件/不同公司回购/不同地震/不同公司业绩快报/目标价骨架/算力合同骨架/不同指数/方向对立/同源不同公司）+ `TestDedupTokenGradientMerge` 3 例；锚点采样 13/13 误合并案例全部修复为保留，真重复 7/11 保持合并（4 条表述差异大按宁漏勿错原则接受漏判，如段永平减持澄清、欧元区CPI、南向资金、野村财报）。`unit/news` 44 用例全绿。
- **校准脚本同步**：`scripts/calibrate-dedup-threshold.py` 阈值常量（0.35/0.375/0.65/0.50）与"当前阈值规则"摘要更新。

### 事实校验描述性尾名匹配修复（rf-289）（2026-08-17）

- **问题**：2026-08-17 报告「事实校验自动修正 3.92%→36.3%（022365实际收益率36.3%）」——LLM 正确写出的"电池主题ETF（收益率-3.92%）"（561910 招商中证电池主题ETF 实际 -3.92%）被自动修正为 **-36.3%**。根因：`_locate_subject_code` 无法解析省略基金公司前缀的描述性缩写（"电池主题ETF"→561910），回退同句最近邻把 3.92 误路由到 022365（永赢科技智选混合C，实际 +36.29%），修正逻辑保留负号 → 报告出现 -36.3%，正确数据被改错。
- **修复**：`src/python/llm/fact_checker/_utils.py` 新增 `_match_descriptive_tail` 描述性尾名匹配——逐持仓取核心名后缀（≥3 汉字）+ 产品后缀（ETF/股票A/混合C 等）拼完整候选，命中句中候选按 (距锚点距离, 候选长度) 择优，接入 `_locate_subject_code` 兜底（产品后缀将候选锚定为产品名，避免"科技""指数"等泛词误路由）。修复后"电池主题ETF（收益率-3.92%）"归因 561910 且 3.92 在容差内通过、不再误修正。
- **回归测试**：`test_fact_checker.py` 新增 `TestDescriptiveTailMatch` 5 项（报告场景不误修正 / 错误值经尾名匹配修正且保留盈亏方向 / `_locate_subject_code` 直测 / 泛词不误路由 / `run_fact_check` 整链路）；全 LLM 单测 764 通过 + code/doc/task-numbering/semantic-index 四检查全绿。

## [0.10.14] - 2026-08-17

### 版本发布 v0.10.14（2026-08-17）

- **发布流程**：P2 发布门禁通过（`test-runner --mode verify,regression` 3710 通过 0 失败 + code/doc/task-numbering/semantic-index 四检查全绿 + 发布手动验证 `--mode perf,security` 14 通过）；版本号全链一致化至 v0.10.14（constants.py / pyproject.toml / README / 10 份管理文档）；发布数据文档刷新（test-coverage.md / folders.md / datasource 文档核对）。
- **test-coverage.md `all_no_unit` 修正（rf-288 登记）**：发布前刷新发现模式对应测试量表 `all_no_unit` 被 bench 回填为 323（含 opt-in live 套件），而 `all`(5533) = `unit`(5224) + `all_no_unit`(309) 数学自洽证明 309 为正确口径——`test-runner.py` MODES `all_no_unit: "not unit"` 覆盖 pytest.ini `addopts = -m "not live"`，使 14 项 live 真实网络套件卷入。已按 collect-test-coverage.py 口径将表值修正为 309，并登记 rf-288 待修复（marker 补 `and not live`）。

### docs-stm/tmp 有价值脚本迁移至 scripts/ + 归档（2026-08-17）

- **有复用价值脚本迁入 `scripts/`**（此前在 git 忽略的临时区，无法留存/共享）：`reproduce_factcheck_corrections.py`（事实校验自动修正复现脚本）+ `check-svg-geom.py`/`check-svg-pixel.py`/`check-svg-text-overflow.py`（README SVG 架构图检查三件套，未来改架构图可复用）。4 脚本语法验证通过，`reproduce_factcheck_corrections.py` 的 `sys.path`（`../..`）在 scripts/ 下仍正确解析项目根。**后续（v0.10.15-dev）重新评估后判定其一次性排查属性，已删除**（见 changelog 当前版本「scripts/ 命名统一与清理」条目）。
- **dedup 校准分析报告迁入归档区**：`cross_merge_bg2_review.md`/`dedup-calibration-report.md`/`dedup-review.md` → `docs-stm/archive/v0.10.x/dedup-calibration/`（rf-279/280 校准结论的依据与逐条样本，原 tmp 位置 git 忽略无法追溯）。
- **清理低价值临时产物**：一次性迁移/清理脚本（migrate_*/clean_*）、被正式工具取代的 _extract_fails/_parse_report、覆盖历史快照（coverage-*.txt）、可再生产物（rf113 报告副本 + svg 渲染 png/jpg）、`__pycache__` 全数删除；docs-stm/tmp 现为空目录（git 忽略）。
- **文档同步**：folders.md 目录树 scripts/ 补 4 脚本 + archive/ 补 dedup-calibration/，统计刷新（辅助脚本 19→23 / 7,106→7,394；archive 106→109 / 37,373→37,689；项目文档 45,933→46,249）。

### 自审记录四次合并：已解决项迁入归档（2026-08-17）

- **review-findings.md 已解决区清空**：v0.10.14 已解决项（rf-282 ~ rf-287）随四次合并整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md` v0.10.14 章节（延续 dev 批次提前归档惯例，三次合并 rf-276~281 先例）。原文件仅保留归档引用 + 待办区（rf-75~89 文件过长、rf-113/114 交互图表技术债、rf-257 Web 真机验收）。
- **对应迭代计划状态**：rf-282~287 均为维护性修复（rf-272 衍生死参/遗留清理 + smoke-web CI 竞态 + bench 菜单键集 + 测试标记体系漂移），非 plan-* 迭代项，plan.md 无变更。
- **变更记录**：各 rf 修复详情已在 [0.10.14] 各条目（死参数/遗留清理、Web 冒烟竞态、bench 回写、perf/security 定向 mode）；归档文件「归档说明」补四次合并记录。

### 补 perf/security 定向 mode + 测试标记体系清理（2026-08-17）

- **新增 `--mode perf` / `--mode security`**：`scenario_perf`（端到端性能基准，5 项）与 `scenario_security`（安全基线，9 项）此前仅有 `collect-test-coverage.py` 能计数、`test-runner.py` 无对应定向 mode（只能靠裸 `-m` 或 `all` 触发）。现补齐定向 mode（`--help` 可见、可进标准 HTML 报告管线），并同步 `collect-test-coverage.py` 模式对应测试量枚举。二者仍为「独立标记、不入门禁、不进 bench」，按既定设计保留手动/发布前运行；testplan.md §6.3 P2 门禁追加**发布手动验证**项：`--mode perf,security`。
- **清理死注册 `unit_config_edge`**：conftest 的 `_KNOWN_MARKERS` + `pytest_configure` 注册了它但全仓 0 用例（config 的 edge 测试已归入 `unit_config`+`edge`）。移除两处注册，无行为影响。
- **顺带修复 rf-287**：`check-test-markers.py` 标记合规检查的 `KNOWN_MARKERS` 与 conftest 漂移——缺 `unit_web`/`integration_cli`/`live` 三个实际在用的标记，误报 17 处「未注册标记」、退出码 1（非门禁脚本，日常门禁未暴露）。按 conftest 对齐后 277 文件 0 违规恢复通过。
- **验证**：check-test-markers 0 违规；collect-test-coverage 输出 perf:5 / security:9；`--mode perf,security` 实跑通过（见下节）。

### bench --update-docs 同步回写模式对应测试量 + 顺带修复菜单键集缺陷（2026-08-16）

- **功能**：`--mode bench --update-docs` 在更新环境耗时对照两表（采集环境属性 + 各模式耗时）之外，同步回写「模式对应测试量」表——覆盖项数 = pytest 实测执行计数（passed+failed+skipped+errors，含参数化展开），典型耗时 = 本机实测约值；未实测/超时模式保留原值。此前该表为 `collect-test-coverage.py` 静态快照，需人工回填易过期（实测由静态 5218/5527 刷新至 5224/5533）。
- **实现**：`test-runner.py` 新增 `_DOC_MODE_COUNT_MARKERS` 标记对 + `_update_mode_count_table()` 纯函数，接入 `_update_test_coverage_doc`；test-coverage.md「模式对应测试量」表套标记并修正注释（原「不含参数化展开」表述与实际 collect 口径不符——collect 计数含参数化展开）。行覆盖率仍走独立 `--coverage` 参数，不并入 bench（插桩会拖慢实测且分段覆盖会重复计数）。
- **顺带修复 rf-286**：bench 全量跑暴露 `test_menu_key_coverage` 菜单键集断言未同步日志可视化新增键——`MENU_ITEMS` 自加 `[V]`/`[H]` 后 19 键，断言仍为旧 17 键，`integration`/`all_no_unit`/`all` 模式必失败（integration 不在 P0 门禁内，全量跑才暴露）。修复：期望集补 `V`/`H`，集成/全量模式复跑通过。
- **验证**：dev-verify 2056 通过；bench 全量 5533 项仅 rf-286 1 例失败（修复前），修复后 integration 281 / all_no_unit 323 / all 5533 全绿；doc_writer 单测新增 3 例模式计数表覆盖，44 例通过。

### Web 冒烟脚本竞态修复 + CI 格式门禁修复（2026-08-16）

GitHub Actions 上报两项失败，均已修复：

- **smoke-web.py 竞态（TemporaryDirectory `Directory not empty`）**：`test_smoke_web_run_smoke_all_pass` 偶发失败——`_check_formal_use_existing` 提交第二个 run（正式-用存量，202）后不轮询终态，`run_smoke()` 立即退出临时目录上下文；run 由后台 worker 线程（`web_run`，daemon）异步执行，退出时仍在写 `output/个人投资分析报告.xlsx`，`TemporaryDirectory` 清理撞上并发写（`OSError: Directory not empty`）。CI 并行调度（worker=2）放大竞态窗口，本地偶发、CI 高频。
  **修复**：抽 `_poll_run_finished(client, run_id)` 轮询 helper，正式-用存量 run 提交后同样轮询至终态（done/failed），`_check_progress_events` 复用；断言语义不变（仍验证 202 + run_id），仅消除竞态窗口。回归测试新增 3 例（轮询至 done / failed / 永不到终态返回最后 status），本地 8 次连跑稳定。
- **ruff format 11 文件格式不一致**：CI `ruff format --check src/python/ scripts/` 报 11 个历史文件需格式化——`scripts/` 6 个（calibrate-dedup-threshold / check-code-traces / check-semantic-index / check-version-consistency / install-claude-hook / probe-push2）+ `src/python/` 5 个（llm/fact_checker/_constants、_utils、llm/strategy、report/category、schemas/history）。均为纯格式调整（frozenset 折叠、多行参数合并等），无逻辑变更；修复后 `ruff format --check src/python/ scripts/` 全 263 文件通过。
- **验证**：dev-verify 2053 通过（含 smoke-web 回归新增 3 例），0 失败。

### 日志可视化三端实现：CLI + TUI + Web（2026-08-16）

实现 plan-10「日志可视化」（P4 实验功能）：三端均提供结构化日志查看，数据源健康历史接线展示。核心解析/聚合逻辑全部集中在核心层，CLI/TUI/Web 仅做薄展示。

- **核心层 `core/log_reader.py`（新）**：三端共享的日志读取模块——`parse_log`（按时间戳切分记录，续行/traceback 归并，装饰性横幅识别 `is_decorative`）、`tail_log`（从文件尾部反向分块读取，64KB chunk，>100MB 大日志不卡顿）、`read_log`（级别阈值过滤 / since-until 时间前缀过滤，无效级别抛 ValueError）。日志路径惰性引用 `logger._LOG_FILE`，不硬编码。`LogEntry` 不可变 dataclass，`to_dict()` 供 Web JSON 序列化。
- **核心层 `core/perf.py`**：新增 `summarize_health_history(limit=10)`——聚合 `data/state/datasource_health.jsonl` 为最近 N 次运行摘要（含 ok/total、失败源清单），接线此前零调用者的 `load_health_history`。
- **CLI**：新增 `view-logs` 子命令（`--level`/`--lines`/`--since`/`--until`），在 `init_config` 之前分派——配置损坏时仍可查日志诊断；输出每条 `time [LEVEL] message`，多行 body 缩进展示。
- **TUI**：菜单新增「V 查看最近运行日志（可按级别筛选）」「H 查看数据源健康历史（近期检查记录）」两项（17→19 项）；`handlers_log.py` 按级别筛选、ERROR 红/WARNING 黄着色（NO_COLOR/TTY 检测自动降级为无着色）、traceback 折叠为「⤷ 堆栈详情 +N 行」。
- **Web**：后端新增 `GET /api/logs`（级别校验→400 / lines clamp [1,5000] / since-until 透传 / 读取失败→500）与 `GET /api/health/history`；前端「⑦ 日志查看」卡手动加载（不自动轮询，对齐设计文档「自动刷新高 IO → 手动刷新」），`<details>` 原生折叠 + 级别配色，全程 `textContent`（XSS 纪律）。
- **回归测试**：新增 `test_log_reader.py` 21 例 + `test_handlers_log.py` 10 例 + `test_tui_menu.py` 更新（V/H 项）+ `test_cli.py` 扩展 10 例 + `test_handlers.py` 扩展 10 例，全部标注 pytest marker、隔离不触真实数据路径。
- **文档同步**：
  - technical.md §6.7 语义命名表新增 `log_reader`/`view_logs`/`health_history` 3 行；§1.7/1.8 三端结构（CLI 子命令 4→5、TUI 菜单 17→19、Web 路由 + `/api/logs` + `/api/health/history`）与 §6.3/6.4 已同步。
  - requirements.md 新增 §3.5「日志可视化（诊断）」R-DIAG-01~03（CLI view-logs / TUI V+H / Web ⑦ 日志卡 + API）；§3.2 菜单表新增「诊断」组（[V]/[H]）；R-TUI-02 菜单数 17→19。
  - 三渠道用户手册：CLI 手册新增 §7 `view-logs` 子命令章节（参数表+示例）并重编号 7-13、§9 速查表加行；TUI 手册主菜单总览加 [V]/[H] + 新增「诊断类」详解；Web 手册首页 6→7 卡片区 + 新增 §6 日志查看区；how-to-start/faq/README 子命令清单加 view-logs、定时任务引用 §11→§12。
  - folders.md 目录树 + 统计刷新；plan.md plan-10 归档至 `archive/v0.10.x/log-visualization/`。
  - **顺带修复 rf-284 文档同步缺口**：CLI 手册残留的 `--warm` 标志说明（参数表/示例/缓存预热章节）已删除——rf-284 删除代码后用户文档未跟上，现与 `cli.py` 一致。
- **已确认覆盖不改代码**：「报告尾部数据源状态表」已由 `data_source_matrix`（registry.py section 18）在 HTML+Excel 双端渲染，与设计意图吻合。

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
