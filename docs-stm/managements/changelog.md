# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.6-dev] - 2026-08-05

### 开发中（未发布）

### 测试模式耗时标注更新（换机实测 + 机型依赖说明）

- **动机**：测试环境从旧慢笔记本换到当前开发机（Linux x86_64，Intel i5-13500H，12 核 16 线程，46GiB 内存；pytest-xdist worker=8 = medium 50% 核数）后，各测试模式实际耗时大幅下降（如 `all` ~10min → ~21s、`scenario` ~6min → ~18s、`scenario_extreme` ~1min 45s → ~2s），test-coverage.md「典型耗时」列与 test_runner.py 模式描述中的时间标注已严重过时。
- **实测**：2026-08-05 顺序运行除 `live`（opt-in 运维套件，不入门禁）外全部 14 个模式记录 pytest 总耗时——unit ~15s / standard ~16s / scenario ~18s / regression ~17s / dev-verify ~20s / verify ~10s / integration ~14s / edge ~13s / data ~2s / all ~21s / all_no_unit ~10s / smoke ~2s / report ~11s / scenario_extreme ~2s。
- **更新**：`scripts/test_runner.py` MODES 描述 4 处时间估算（dev-verify ~2.5min→~20s、scenario_basic 阶段 ~100s→~10s、smoke ~15s→~2s 且项数 24→26、scenario_extreme ~1min→~2s）并标注「12 核 16 线程并行实测」；`test-coverage.md` 模式表「典型耗时」列全部刷新为实测值，并加注说明**耗时与硬件/操作系统/并行度强相关**（早期标注源自慢笔记本环境，仅作相对量级参考）；同步刷新 `scripts-reference.md`「--mode 对照」表与 `how-to-test-my-code.md` 门禁/流水线/模式说明中的全部耗时标注，并在 test-coverage.md / scripts-reference.md / how-to-test-my-code.md 三份文档补充统计所用硬件配置（i5-13500H 12 核 16 线程 / 46GiB 内存 / worker=8）。
- **门禁**：各模式实测全部通过；改动仅涉及描述字符串与文档，不影响测试逻辑。

### test_runner 机器信息采集与耗时对照表（跨机器采集工具链）

- **动机**：耗时受硬件/操作系统/并行度三因素影响，既有文档已注明「强相关」但需换机采集时才能填表；为在不同电脑（如旧笔记本）上复现采集并回填对照表，需要脚本自动收集环境属性与各模式耗时并输出可直接粘贴的 Markdown 表格。
- **新增 `--mode bench` 聚合别名**：一键顺序运行 14 个对照表模式（`_MODE_TABLE_ORDER` 除 `live` 外的全部模式，`live` 为 opt-in 运维套件不入门禁），结果去重保序；非 bench 模式原样透传。`--machine-info` 输出环境属性表 + 各模式耗时对照表。
- **新增机器信息采集（跨平台容错）**：`_collect_machine_info` 采集 14 项属性——操作系统/系统版本/架构/主机名/CPU 型号/物理核数/逻辑线程/内存/磁盘类型/文件系统/Python 版本/并行级别/worker 数/采集日期。Linux 读 `/proc/cpuinfo`（按 physical id+core id 去重统计物理核）、`/proc/meminfo`、`/proc/mounts` + `/sys/block/*/queue/rotational`（区分 NVMe/SSD/HDD）；macOS 走 `sysctl`；Windows 走 `ctypes.GlobalMemoryStatusEx`。全部读取均 try/except 容错回退 `未知`，不影响 bench 运行；bench 中途 Ctrl+C 先打印已采集部分再退出（`KeyboardInterrupt` 保护，慢机器不丢数据）。
- **耗时表格渲染**：`_render_duration_table` 按对照表固定顺序输出 `--mode | 覆盖项数 | 耗时` 三列，`verify,regression` 合并一行，耗时取整至秒（下限 1s），超时与不在对照表内的模式跳过。`_render_env_table` 输出 14 行环境属性表。输出即为文档表格格式，可直接粘贴进 test-coverage.md。
- **文档同步**：test-coverage.md 新增「采集环境属性」表（当前开发机实测值 + 旧笔记本待补）+「各模式耗时对照」表（实测 vs 早期标注）+ 跨机器采集说明（`--mode bench --machine-info`）；scripts-reference.md 补充 bench/machine-info 用法；folders.md 目录树与项目统计同步（测试代码 283 文件 / 79,122 行、测试用例 4,998 个）。
- **测试**：新增 `src/test/unit/scripts/test_test_runner_machine_info.py` 17 项（机器信息字段完整性/并行级别映射/Linux 回退不崩溃/bench 展开去重排除 live/耗时表格排序与组合行/环境表未知占位），pytestmark `unit` + `unit_scripts`。
- **门禁**：dev-verify 1723 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 修复：事实校验误将止盈/减仓目标比例修正为收益率（rf-230）

- **缺陷**：智囊团深度复盘等 LLM 调仓建议写「建议止盈约30-40%持仓」「止盈约20-30%」，其中 30%/40% 是止盈/减仓**目标比例**（相对当前持仓），非收益率。事实校验因句子含「利润/盈利」触发收益语境，且 `_REBALANCE_TARGET_KEYWORDS` 只覆盖「降至/减仓至」等"至"字式、漏掉「止盈约/减仓约」等"约"字式 → 比例值走全局最近邻被误修正为 601398 实际收益率 70.2%，报告被篡改为「止盈约30-70.2%」「止盈约20-70.2%」，建议语义失真（真实报告复现 + 单测逐字复现修正明细）。
- **根因**：① 语境识别缺失——止盈/减仓目标比例无词表、无邻近窗口检测；② `apply_numerical_corrections` 用 `re.sub` 全局替换（无 `count`），一处修正连带替换 HTML 中所有同值数字。
- **修复**：① `llm/fact_checker/_constants.py` 新增 `_TRIM_TARGET_KEYWORDS`、`_context.py` 新增 `_is_trim_target_context`（match 前 15 字符窗口）、`_numerical.py` `_evaluate_percent_value` 开头拦截；② `llm/fact_checker/_corrections.py` 的 `re.sub` 加 `count=1`。
- **测试**：`test_fact_checker.py` 新增 `TestTrimTargetContext`（真实复现句 30-40%/20-30% 不误修正、单句「止盈约30%」「减仓约20%」、加仓/止损/清仓同义表达、run_fact_check 整链路内容不被篡改、真实收益率 5.0% 仍被校验）+ `TestApplyCorrectionSingleReplace`（同值异义只替换一处）。test_fact_checker 103 passed。

### 修复：What-if 测试断言硬编码 POSIX 路径致 Windows 失败（rf-231）

- **缺陷**：`test_handlers_whatif.py::TestSelectCandidateFile` 三处断言硬编码 POSIX 风格路径，在 Windows 上失败：① `test_only_base_choose_copy_template` / `test_only_base_invalid_choice_then_copy_template` 期望 `dummy_dir/base-调仓后模板.xlsx`（正斜杠），而 `_copy_base_as_template` 用 `os.path.join` 拼接在 Windows 下为 `dummy_dir\base-调仓后模板.xlsx`；② `test_only_base_manual_input_valid` 期望返回 `/tmp/after.xlsx`，但 `_manual_input_path` 对输入做 `os.path.abspath` 后 Windows 下为 `D:\tmp\after.xlsx`。dev-verify 1559 passed / 3 failed，均落此三例。
- **根因**：测试断言直接使用硬编码路径字符串，未随平台路径分隔符/归一化规则自适应。
- **修复**：期望值改用平台无关构造——复制模板路径用 `os.path.join("dummy_dir", "base-调仓后模板.xlsx")`，手动输入返回用 `os.path.abspath("/tmp/after.xlsx")`（与被测代码归一化口径一致）；测试文件补充 `import os`。
- **测试**：test_handlers_whatif.py 16 passed（含原失败三例）。

### 修复：test_runner --update-docs 写入器跨盘符 relpath 崩溃（rf-232）

- **缺陷**：`test_runner.py::_update_test_coverage_doc_file` 打印路径用 `os.path.relpath(_DOC_COVERAGE_PATH, _PROJECT_ROOT)`，Windows 下两路径跨盘符时 relpath 抛 `ValueError: path is on mount 'C:', start on mount 'D:'` 致进程崩溃。`unit` 模式 1 failed（`test_test_runner_doc_writer.py::TestDocFileAndArgs::test_update_doc_file_writes_only_when_changed`，traceback 落 929 行 print）——该测试将 `_DOC_COVERAGE_PATH` monkeypatch 到 C: 临时目录而项目在 D:。
- **根因**：仅用于展示的相对路径换算未处理 Windows 跨盘符（不同驱动器间不存在相对路径），relpath 抛 ValueError。
- **修复**：新增 `_display_path(path, start)` 辅助函数——relpath 抛 ValueError 时降级返回绝对路径；`_update_test_coverage_doc_file` 两处打印（925/929 行）改用该函数。
- **测试**：新增回归测试 `TestDocFileAndArgs::test_display_path_cross_drive_fallback`（Windows 构造跨盘符路径断言返回绝对路径不崩溃，POSIX 断言正常相对路径，平台无关）。test_test_runner_doc_writer.py 23 passed（原失败用例通过）。

### test_runner 环境耗时对照文档自动更新（`--update-docs`）

- **动机**：上一轮 `--mode bench --machine-info` 输出的环境属性表 + 耗时对照表需**手工粘贴**进 test-coverage.md，且脚本 stdout 表格与文档表格列结构不一致（脚本环境表 13 行/OS 与系统版本合并，文档 14 行分列）。用户希望跑完自动更新文档，无需手工编辑。
- **方向（用户已定）**：① 并排表格·按主机名增列——新机器自动追加一列（表头 `{hostname}（{采集日期} 实测）`），同机再次运行原地覆盖刷新日期；历史参考列（旧慢笔记本）永不被触碰；② 显式 `--update-docs` 标志（隐含 `--machine-info`），默认永不写文档。
- **文档标记锚点**：test-coverage.md 两张表各包一对 HTML 注释标记（`<!-- env-table:start/end -->`、`<!-- duration-table:start/end -->`），写入器按标记定位替换区域，标记区外文本逐字节不变；表头预改为 `dragonball（2026-08-05 实测）`（主机名子串匹配列，同机首跑即命中原地刷新，不产生孤儿列）。
- **写入器（纯函数 + IO 封装）**：`_update_test_coverage_doc(doc_text, machine_info, results) -> str` 无副作用解析→替换；`_update_test_coverage_doc_file` 仅内容变化才写盘（缺标记/异常打印 `[ERR]` 返回，绝不破坏既有文档）。表编辑用「token 网格」按 `|` 切分逐格增/改，未改动列字节原样保留；新列分隔标记由最后数据列推断（环境表左对齐 `:---` / 耗时表居中 `:---:`）。
- **环境表统一 14 行**：新增 `_ENV_ATTR_LABELS` + `_env_value(label, info)` 作为 stdout 渲染与文档写入的单一事实源（操作系统/系统版本分列），修复脚本与文档列结构不一致。
- **耗时单元格**：`_duration_mode_cells` 按 `_MODE_TABLE_ORDER` 聚合 `~{N}s`（≥60s 显示 `~{M}min`，对齐文档旧列风格），组合行 `verify,regression` = 顺序耗时之和；超时/未测模式单元格留空（None 保留原值不清空）；Ctrl+C 中断时已跑完模式照常回填。
- **测试**：新增 `src/test/unit/scripts/test_test_runner_doc_writer.py` 22 项（环境表同名列刷新/新列追加/未知行保留、耗时表同列更新/新列留空/组合行格式、标记缺失抛 ValueError、round-trip 幂等、区外文本不变、结构异常防护（标记间夹非表格行/缺分隔行抛错）、替换块反斜杠不触发 re 模板解析、仅内容变化才写盘、非 ValueError 异常降级 [ERR]、`--update-docs` 隐含 `--machine-info`），pytestmark `unit` + `unit_scripts`；既有 `test_test_runner_machine_info.py` 环境表 14 行断言同步。
- **文档**：how-to-test-my-code.md 新增「跨机器耗时采集与环境耗时对照」（`bench` + `--machine-info` / `--update-docs`）小节；folders.md 文档统计行随 changelog/manuals 增补刷新（用户文档 5,689 / 项目文档 41,957 / managements 7,102）。
- **门禁**：dev-verify + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全通过。

## [0.10.5] - 2026-08-05

### plan.md 已完成事项整体归档至 archived_plan.0.10.x.md

- **动机**：`plan.md` 承载当前迭代待办 + 已完成项详细记录，v0.10.x 已发布事项（plan-17~24）详细段落随迭代推进持续累积，活跃文档过重。按「已完成历史版本计划已归档，此处仅跟踪当前迭代中的工作」原则，将已发布（v0.10.1/v0.10.3/v0.10.4）的已完成事项记录整体迁入归档索引，`plan.md` 回归轻量「未完成项 + 归档引用」结构。
- **迁移内容**（`plan.md` → `docs-stm/archive/v0.10.x/archived_plan.0.10.x.md`）：P0 发布门禁两条（v0.10.3/v0.10.4）、推荐实施顺序 ①~⑧ 表格、P1~P3 已完成项详细段落（plan-17~24 每项轮次/验收/门禁记录）。
- **归档文档结构**：设计文档索引（investment-features + task-code-traces-gate）+ v0.10.x 已完成项摘要表 + P0 发布门禁 + 推荐实施顺序 + P1~P3 详细段落（原相对链接改指本目录内 `investment-features/` 兄弟路径）。
- **plan.md 精简**：概述改为指向归档（含设计文档索引 + 完成项摘要表 + 推荐实施顺序 + 发布门禁记录）；当前迭代待办仅保留 P4 实验功能（plan-8/plan-10，未完成）；归档列表保持。
- **状态变更**：`plan.md` 中已完成项状态由「当前迭代待办」转为「已归档」；`plan-next` 编号源不变（已用最大 plan-24，归档不回收）。

### 新增 opt-in live 真实网络验证套件（不入门禁）

- **动机**：既有测试体系全 mock（网络依赖由运行时回退/熔断治理，非门禁），无法直接排查「数据源是否真的可达 / API 是否漂移」。新增 `live` 套件作为独立运维验证通道，与门禁严格隔离。
- **基建**：`src/test/live/` 14 项真实联网测试（行情：A 股/ETF/场外基金/中美指数；新闻：东方财富/财联社/新浪/华尔街见闻；基金：历史净值/排名/基准；akshare 交易日历）。三层机制保证**平时完全不运行**：① `pytest.ini` `addopts = -m "not live"` 收集期排除；② conftest `_skip_live_unless_requested` autouse fixture 默认 skip；③ test_runner 门禁模式不引用。验证：全量收集 4981/4995（14 deselected，即 live 被排除）。
- **断言原则**：只校验返回「结构」（字段存在、类型、非空），不校验具体数值，容忍真实行情波动；不含 LLM 真实调用（防费用）。`_block_external_network` 阻断 fixture 放行 live 项（显式 `--run-live`/`-m live` 时）。
- **触发方式**：`python scripts/test_runner.py --mode live`（新增 MODES 条目，order 14）或 `pytest --run-live -m live`。
- **文档同步**：how-to-test-my-code.md（②专项验证代码块 + 新增 live 小节 + 报告目录树）、testplan.md（测试环境网络行标注 live opt-in）。
- **门禁**：dev-verify 1706 passed + 3 check 全 [OK]。

### 功能语义命名表抽取为活索引（technical.md §6.7）

- **动机**：CLAUDE.md「语义化命名」条目原引用归档文档（`docs-stm/archive/v0.10.x/investment-features/plan-investment-features.md` §2.0）作功能语义命名表，归档后引用路径不稳定、可追溯性差。共性语义命名表应入管理文档作为**活索引**，各轮设计文档中的原始表降级为历史快照。
- **抽取**：`technical.md` 新增 `### 6.7 功能语义命名表`——纪律说明（代码标识符=文档中文描述、先定语义名再设计、任务代号不入实现层）+ 14 行核心功能语义命名表（candidate_compare/valuation_percentile/market_temperature/rebalance_advice/trade_discipline/return_attribution/fund_flow/dividend_flow/industry_beta/crisis_annotation/tail_risk/snapshot_diff/data_quality/holding_diagnosis）+ 合并章 key 说明（position_relationship/portfolio_history_drawdown/style_factor）+ registry.number 重排说明（1~19）；同时更新技术文档目录 TOC 添加 6.7。
- **引用改向**：CLAUDE.md「语义化命名」条目引用改指 `docs-stm/managements/technical.md` §6.7（活索引）；归档 `plan-investment-features.md` §2.0 原始表保留为历史快照不追溯修改。
- **门禁**：check-code-traces.py 不引用归档表格（抽取无冲突），3 check 脚本 `--ci` 待最终全量验证。

### 消除测试用例运行时外部网络依赖（全局 socket 阻断防线）

- **审计方法**：临时 socket 阻断插件全局替换建连入口（socket.socket 用类替换保留 ssl 继承、socket.create_connection / getaddrinfo 函数替换），扫描全部测试套件——凡触发真实网络连接的用例立即失败暴露。unit 套件 + scenario/integration 共扫描出 **5 处**未 mock 的真实网络依赖。
- **修复 5 处未 mock 网络调用**：
  - `test_fetcher.py::TestFetchFundBenchmark`（2 例）：`fetch_fund_benchmark` 三层策略（API 解析→内置知识库→配置覆盖）先走 API 解析层联网；mock `_fetch_benchmark_from_api` → None 改走内置基准库，用例改用内置库真实代码 561910。
  - `test_data_integrity.py::test_a_index_value_ranges` / `test_cache_consistency.py::test_index_cache_shared_across_modules`：mock 指数数据只覆盖 5/1 个，而 `_A_INDICES` 共 7 个 → 缺失项触发新浪备用链路联网；补 patch `_fetch_indices_from_sina` → {} 阻断 fallback。
  - `test_orchestrator.py::test_generate_report_skeleton`：骨架 basic 路径真实生成 Excel，依赖交易日历（akshare 联网）+ A 股/美股指数 + 后台数据源健康检查（全量 HTTP 连通性探测）；补 mock `_get_trading_calendar` / `fetch_indices` / `fetch_us_indices` / `_spawn_health_checks` / `_collect_health_checks`。
- **全局防线**：`conftest.py` 新增 `_block_external_network` autouse fixture——测试运行时全局阻断 socket 建连，任何未 mock 的网络调用（数据源 API / LLM API / akshare / 健康检查）立即抛 RuntimeError 使测试失败，从机制上杜绝测试运行时外部网络依赖。已 mock HTTP 层（httpx.Client / requests / provider / `_fetch_*`）的测试不创建真实 socket，不受影响；真实建连仅发生在「应 mock 却未 mock」时。
- **验证**：unit 4660 passed + 12 skipped、scenario+integration 309 passed + 76 subtests、dev-verify 1706 passed / 0 failed，均无外部网络依赖。

### 文档全面核对与修复（folders.md 统计刷新 + 用户/管理文档一致性审计）

- **folders.md 统计与目录树核对**：项目统计表核对至当前实时状态（主程序 222 文件/55,247 行、HTML 4 文件/3,761 行、辅助脚本 16 文件/5,581 行、源代码合计 242 文件/64,589 行、测试代码 276 文件/78,332 行、测试用例 4,980 个）；目录树层级符号对齐（`├──`/`└──` 一致性）与文件补录；报告章节图表初始化描述「6 张」→「9 张（6 核心 + 3 演进；单图异常隔离 + degraded 虚线）」。
- **管理文档一致性核对**：technical.md 12 处修复——缓存层线程池唯一宿主表述、线程池表由 2 池补全为 9 池（orch_prep/orch_factor/orch_factor_idx/orch_ind/orch_ind_idx/orch_val/orch_corr/orch_llm_news/orch_health，含用途与 max_workers）、基金深度分析模块数 5→4、相关性区块数据契约引用改指附录 H 且架构约束注册引用改指 §8.3、STATUS_MESSAGES「23 条」→「24 条」、llm/ 子模块「36 个」→「32 个」、`module_{标识}`→`{参数}_{标识}` 命名约定、portfolio_evolution number=16、action number=17；requirements.md 8 处——降级引用统一「technical.md §1.4.5」、调仓建议/收益归因由「框架子块」更新为「已实现（无数据写『待生成』）」；testplan.md——场景规格表头补齐 D1-D3、无人工门禁表述更新、unit_config_edge 预留说明；llm-technical.md——批处理并行度「最多 3 批并行」表述、附录 B 定价表补 claude-sonnet-4-8/claude-opus-4-6 具名模型 + 6 个前缀回退键脚注；test-coverage.md——分组标题层级统一、场景覆盖项数/文件数/基准指数覆盖表述刷新；README.md——Chart.js 图表数 6→9。
- **用户手册一致性核对**：how-to-test-my-code.md 场景编号 S1-S34→S1-S33（S34 基准指数对比为合法规格项、由单元测试覆盖，testplan.md 规格表保留 S34）；reports-instruction.md / faq.md / how-to-config.md / datasource*.md / how-to-menu.md 等章节序号、目录锚点、模型名、数据源清单核对至最新状态。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]，dev-verify 1706 passed / 0 failed。

### 修复 akshare 交易日历并发 V8 崩溃（rf-228）

- **问题**：TUI 菜单「2」更新行情缓存时进程崩溃，`[FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized()`（abort 整个进程，try/except 无法捕获）。根因链：菜单 2 并行价格抓取（ThreadPoolExecutor 4 workers）→ 每价格新鲜度校验 `_price_cache_fresh` → `get_last_trading_day()` → `_get_trading_calendar()` → `akshare.tool_trade_date_hist_sina()`（新浪交易日历）。akshare 该函数内部用 `py_mini_racer`(V8) 解密、**每次调用都新建 V8 实例**；多线程并发首次初始化 V8 触发 `partition_address_space` FATAL。已在 tmp 探针脚本复现（4 线程并发 → EXIT 3 崩溃；加锁串行化 → 全成功）。
- **修复**：`market_value.py::_get_trading_calendar()` 缓存未命中分支用模块级锁 `_TRADING_CALENDAR_AKSHARE_LOCK` 串行化 + **双重检查**（锁等待后重新读缓存，避免重复拉取）。V8 顺序初始化安全。不影响单线程正常路径。
- **回归测试**：`test_market_value.py` 新增 `TestTradingCalendarConcurrency`——4 线程并发调 `_get_trading_calendar()`，注入 fake akshare（`patch.dict(sys.modules)`）统计回调最大并发深度，断言**串行化不变量 max_active == 1**。全 mock 无真实 V8/网络调用。
- **连带优化**：审计发现 `test_market_value.py` 多个测试类裸调用 `is_market_open`（东方财富 push2 API 真实 HTTP，timeout 5s）与 `_is_trading_day`（akshare 交易日历网络）导致单用例 2~6s。为 `TestPriceUpdateStatus`/`TestDeterminePriceType`/`TestGenerateDetails`/`TestPremiumPlaceholder`/`TestTodayProfitEastMoneyNonTDay`/`TestTodayProfitTencentAlways`/`TestTodayProfitEdgeCases`/`TestPremiumInWriteSheet`/`TestCurrencyConversion`/`TestTodayProfitOffMarket` 统一补 setUp mock（`is_market_open`/`is_midday_break`/`_is_trading_day`），消除用例内网络依赖。用例 call 时间从 2~6s 降至 0.01~0.08s（剩余启动开销为环境 Python 解释器慢，与测试无关）。

### HTML 报告目录 LLM 章节标记（橙色加粗 + 🧠 图标）

- **功能**：HTML 报告两处导航（左侧目录 `.toc-sidebar` + 窄屏顶部横向 `.section-nav`）中，由 LLM 生成/支持的章节标题改为**橙色加粗**并在标题旁显示 **🧠 图标**。dark mode 下橙色复用双定义变量 `--orange-text`（浅色 `#E65100` / 深色 `#ff8a50`），天然适配。
- **标记范围**：与「LLM」导航组同源派生——`html_writer.py` 新增常量 `_LLM_SUPPORTED_SECTIONS`，从 `_SECTION_NAV_GROUP_MAP` 的 `"llm"` 组推导（单一数据源防漂移，覆盖新闻关联 + LLM 文本分析系列 + API 用量），经 render() context 传入模板（渲染期数据经 context 传递约束）。
- **实现**：模板目录/横向导航链接按章节 LLM 支持位加 `toc-llm` class 与 `span.toc-llm-icon`（`aria-hidden="true"`）；CSS 新增 `.toc-list a.toc-llm` / `.section-nav a.toc-llm`（橙色加粗）与 `.toc-list a.toc-llm.active`（active 态保持橙色，特异性高于既有 active 规则）；打印样式已隐藏两导航，无需处理。
- **测试**：`test_html_report_structure.py` 新增 7 例（常量与「LLM」组一致性、目录/横向导航标记与未标记断言、分组 dict 携带 `llm_supported`、CSS 规则存在、颜色变量双定义复用），并更新 2 例既有测试（剔除 🧠 图标后比对导航文字一致性 / LLM 目录文案前缀+图标断言）。report 套件单测全绿（1482 passed）。

### 迭代计划归档（plan-17~24 收官，2026-08-05）

- **归档**：`plan-investment-features.md`（设计层）+ `plan-investment-iteration.md`（实施层，21 轮）由 `docs-stm/plan/` 移入 `docs-stm/archive/v0.10.x/investment-features/`；`plan-task-code-traces-gate.md`（rf-208 门禁增强设计）移入 `docs-stm/archive/v0.10.x/task-code-traces-gate/`。新增 `docs-stm/archive/v0.10.x/archived_plan.0.10.x.md` 归档索引（已完成项表 plan-17~24 + 设计文档索引 + 归档说明），沿用 v0.9.x `archived_plan.*.md` 格式。
- **引用同步**：plan.md 概述/推荐实施顺序/已完成章节链接改指归档索引与归档路径，归档区新增 `archived_plan.0.10.x.md` 条目；folders.md 目录树 `plan/` 仅保留未完成项（plan-web-ui*/plan-web-ui-implementation*），新增 `archive/v0.10.x/` 子树；CLAUDE.md 语义化命名条目中功能语义命名表示例路径改指归档文档。`docs-stm/plan/` 现仅存 plan-8/plan-10（P4 实验功能）设计文档。
- **门禁**：3 check 脚本 `--ci` 全 [OK]（check-task-numbering exit 0，归档编号与历史归档无冲突）。

### changelog 主题标题层级统一（v0.10.3 起 `####` → `###`）

- 修正 v0.10.3/v0.10.4/v0.10.5-dev 各版本主题标题层级漂移：开发节引入 `### 开发中（未发布）` 占位后主题误用四级 `####`，转正式节时未同步升回。现统一为三级 `###`，与 v0.10.0~0.10.2 及 v0.9 分类层级（`###`）对齐。v0.9.x 归档保持原格式不追溯。

### CLI 集成测试 patch 目标修正（rf-227）

- **问题**：`test_cli_integration.py` 三处 CLI 测试 patch 目标陈旧——41df26a「根文件归子包」重构后残留包级 re-export 路径 `src.python.cli._cli_read_holdings`，拦截不到 `cli.py` 模块内部同名引用。`test_cli_cache_config_respected` 因此走到真实持仓读取（`/test/holdings/test.xlsx` 不存在）→ mock 调用 0 次断言失败；另两例（`test_cli_report_config_respected`/`test_handle_report_return_exit_code`）靠 `data/holdings/` 默认持仓文件恰好存在而侥幸通过。
- **修复**：三处 patch 目标统一修正到 `src.python.cli.cli._cli_read_holdings(_with_flows)`；report 路径两例改用 `_cli_read_holdings_with_flows` 返回 `(mock_holdings, [], [])`（与 `_handle_report` 实际调用路径一致），彻底脱离真实持仓文件依赖，测试隔离达标。
- **验证**：全量 `test_runner.py --mode all` 5026 passed / 0 failed / 12 skipped；CLI 单测 `test_cli.py`+`test_cli_edge.py` 56 passed 无回归。

### 历史记录归档（review-findings + changelog，v0.10.x 已发布记录迁入归档）

- **review-findings 归档**：`docs-stm/managements/review-findings.md` 已修复表中 v0.10.1/v0.10.3/v0.10.4 的已修复条目（rf-204~rf-226，dev 版 rf-227/rf-228 除外）整体迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md`，按版本分组（v0.10.1：rf-204~216；v0.10.3：rf-218~225；v0.10.4：rf-226）保留「问题 / 修复方案 / 变更记录」完整记录；`review-findings.md` 已修复表仅保留 dev 版未归档条目（rf-227/rf-228），归档档案段新增 v0.10.x 链接；P3 段末尾 rf-226 补齐注释随迁移删除（信息在归档中）。
- **changelog 归档**：`docs-stm/managements/changelog.md` 中 v0.10.1~v0.10.4 四个已发布版本段整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（v0.10.0 无独立 changelog 段，不单独归档）；`changelog.md` 保留 v0.10.5-dev 开发段 + 归档列表（新增 v0.10.x 链接）。
- **目录同步**：`folders.md` 目录树 `archive/v0.10.x/` 补 `archived_changelog.0.10.x.md` / `archived_review-findings.0.10.x.md` 两行（与 v0.9.x 段三文件并列结构对齐）。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]；全量测试 `test_runner.py --mode all` 4969 passed / 0 failed / 12 skipped；版本号全链一致 v0.10.5。

---

## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.4（2026-08-04 ~ 2026-08-05）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
