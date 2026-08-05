# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.7-dev] - 开发中（未发布）

### 统一熔断网关 + 指标熔断状态文件落盘位置修正 + 菜单 [1] 基础缓存刷新补齐

- **统一熔断网关（三路聚合）**：`CircuitBreakerGateway` 将数据源熔断（DataSourceRegistry）、LLM 端点熔断、指标熔断（IndicatorBreaker）三路状态聚合到统一查询入口——`gateway.get("data_source"/"indicator"/"llm")`、`gateway.summary()`，并新增模块级 `get_indicator_breaker_status()`/`get_all_breaker_status()` 包装函数。`technical.md` §2.2「统一熔断网关」段落同步更新为三路聚合描述。
- **指标熔断状态文件落盘位置修正**：指标熔断器持久化文件从 `data/cache/metrics_breaker.json` 调整至 `data/state/metrics_breaker.json`（运行时状态目录），旧路径文件在首次加载时自动改写至新位置并删除旧文件，避免被缓存清理误扫。`technical.md` §2.2 持久化列与 `datasource-reliability.md` §4.1 同步更新。
- **菜单 [1] 更新基础类缓存补齐**：新增三项刷新——财经新闻（持仓关键词聚合预热 `news_` 缓存）、基金经理（逐基金刷新 `fund_manager_` 缓存）、基金风格扩展（A 股扩展数据预取到 registry 会话缓存）；同时补齐有基金路径此前缺失的行业分类、分红刷新。纯股票组合路径同样刷新新闻与风格扩展。`how-to-menu.md` 菜单 [1] 说明同步更新。
- **测试**：新增统一熔断网关 12 项、指标熔断持久化路径 3 项、菜单 [1] 扩展缓存刷新 19 项（新闻/基金经理/风格扩展 helper + 并行编排 + update_basic_cache 两分支接线 + 显示三行输出）。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

---

## [0.10.6] - 2026-08-05

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

### test-coverage 耗时对照表新增「数据更新时间」行（按设备列回填采集日期）

- **动机**：环境耗时对照表此前只有逐模式耗时单元格，表头括号里的实测日期（如 `dragonball（2026-08-05 实测）`）无法在表体一行内直观看清**每列数据的更新时间**；多台设备各自回填后难以一眼确认某列时效。
- **更新**：`test_runner.py` `--update-docs` 写入器在耗时对照表末尾追加「数据更新时间」行——本机匹配列按采集日期回填，其余列保留原值不清空（旧慢笔记本列保持 `—`）；test-coverage.md 耗时对照表补入该行（dragonball / stallman-NB1 为 2026-08-05 实测，旧慢笔记本为早期标注 `—`），与「采集环境属性」表「采集日期」行口径一致。
- **测试**：`test_test_runner_doc_writer.py` 新增 `test_duration_update_time_row_matches_machine_date`（换机采集日期不同 → 数据更新时间行随本机列更新），并在既有同列更新/新列追加两例断言数据更新时间行回填；test-coverage.md 计数同步刷新（unit 4721 / standard 4114 / verify 3065 / dev-verify 1747 / all 5030 / unit_scripts 162 / unit_llm 736）。
- **门禁**：dev-verify 1747 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### test-coverage 环境耗时对照表移除「旧慢笔记本」列

- **变更**：test-coverage.md 两张表（采集环境属性 / 各模式耗时对照）删除「旧慢笔记本（早期标注）」列，仅保留 dragonball 与 stallman-NB1 两台已实测机器列（均 2026-08-05 采集）；正文随列删除同步修正——对照说明改为「两台已实测机器」、跨机器采集注去除「旧机器标注列不受影响」、两机差距注按 dragonball vs stallman-NB1 重述（多数模式约 10~20 倍）并补充 stallman-NB1 worker=4。
- **验证**：`--update-docs` 写入器对 2 列表格 round-trip 正常（不重写历史列、不引入列宽异常）；check-doc-traces / check-task-numbering / check-code-traces `--ci` 全 [OK]，doc_writer + machine_info 测试 41 passed。

### README 开发者参考补充跨机器测试耗时采集说明

- **更新**：README.md「如何测试我的代码」行描述补「跨机器耗时采集与环境耗时对照」，开发者参考表后新增注——`python scripts/test_runner.py --mode bench --update-docs`（隐含 `--machine-info`）一键采集本机 14 项环境属性并自动回填 test-coverage.md 环境耗时对照表（按主机名匹配/新增列，显式传入才写文档），与 how-to-test-my-code.md / scripts-reference.md 口径一致。
- **门禁**：check-version-consistency 13 项 [OK] + 3 check 脚本 `--ci` 全通过。

### 历史记录归档（review-findings + changelog，v0.10.5 已发布记录迁入归档）

- **changelog 归档**：`docs-stm/managements/changelog.md` 中 v0.10.5 已发布版本段整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（涵盖版本更新为 v0.10.1 ~ v0.10.5）；`changelog.md` 保留 v0.10.6 发布段 + 归档列表（v0.10.x 链接更新）。
- **review-findings 归档**：`docs-stm/managements/review-findings.md` 已修复摘要中 v0.10.5/v0.10.6 已修复 rf 记录迁入 `docs-stm/archive/v0.10.x/archived_review-findings.0.10.x.md`。
- **门禁**：3 check 脚本（check-code-traces / check-doc-traces / check-task-numbering）`--ci` 全 [OK]；版本号全链一致 v0.10.6。
## 归档

- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.5（2026-08-04 ~ 2026-08-05）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
