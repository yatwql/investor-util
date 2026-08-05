# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.7-dev] - 开发中（未发布）

### 语义命名索引双向校验（check-semantic-index.py + 功能语义命名表存量修正 + 架构约束参照）

- **动机**：「功能语义命名表」（技术设计文档中「代码标识符 = 文档中文描述」的唯一现状基准）此前是「记录性活索引」而非自动约束——`check-code-traces.py` 只做负面禁止（禁任务代号/魔法编号），**不校验正面一致性**：新增 `report_submodules.*` 开关键可绕过登记、功能删除后表行可残留僵尸条目、合并章 sheet key 无人核实。预演审计实证漂移：`cost_lots` 未登记（表内成本流水此前由 `fund_flow`/`dividend_flow` 覆盖）、`dividend_flow`/`holding_diagnosis` 为僵尸条目。
- **存量修正（技术设计文档）**：表与代码对齐——`cost_lots` 补登记（`report_submodules.cost_lots`，默认关）、移除僵尸条目 `dividend_flow`/`holding_diagnosis`（并入说明注明其并入归属）、合并章 sheet key 三枚（`position_relationship`/`portfolio_history_drawdown`/`style_factor`）核实均存在于 `registry._REPORT_SECTION_DEFAULT`；表体包裹 `<!-- semantic-index:start/end -->` HTML 标记供脚本定位（与 check-version-consistency / test_runner 文档写入器同款标记习语）。
- **新增 `check-semantic-index.py`**（独立脚本，正面校验，与 check-code-traces 负面禁止互补）：正向——`_config_defaults.py` 中 `report_submodules` 各键须在「功能语义命名表」中登记（表外键报错）；反向——表中每个语义 slug 在 `src/python` 至少一处非注释代码引用（防僵尸条目，tokenize 剔除注释）；合并章——注声明 sheet key 须在 registry 中存在。退出码 0/2，`--ci` 只输出违规。
- **纪律升级为架构约束参照**：技术设计文档「架构设计约束」章节开头新增「约束外参照（语义命名纪律）」——除该章节编号约束外，语义命名纪律以「功能语义命名表」为唯一现状基准、由双脚本强制；表所在章节的纪律行同步指向该参照。**不新增约束编号**：语义命名纪律以「约束外参照」形式并入，避免扩充约束编号集合，从而无需波及 check-code-traces 的约束代号边界匹配与其边界测试。
- **门禁接入**：CLAUDE.md 提交前（P0）/发布前（P2）门禁、testplan.md 回归门禁清单增补 `check-semantic-index.py --ci`；scripts-reference.md 一览表 + 详细章节、folders.md 目录树与统计同步。
- **测试**：`test_check_semantic_index.py` 24 项（标记区间提取/表行解析/合并章 key 解析/权威源 ast/注释剔除/反向存在性/run_checks 三向/真实仓库冒烟），全部通过；新增脚本自身通过 check-code-traces --ci 自检。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering / check-semantic-index `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 文档内容修正（菜单 P 章节组 / enable_action 配置入口 / 场内场外识别描述 / 注册表使用说明）

- **菜单 P 章节组修正**：`faq.md` 菜单 P 可配置章节组由「三个」修正为「四个」（基金深度分析/市场新闻/历史走势/组合演进），并补充「组合演进」对应 `enable_portfolio_evolution` 开关；`how-to-config.md` 同步修正——`enable_action` 无菜单入口（需手动编辑 `config.json`），菜单 P 仅配置其余 4 个章节组可见性。
- **场内/场外识别描述修正**：`reports-instruction.md` 移除「F 开头标记场外基金」的错误描述，改为程序自动识别规则（账户渠道/名称关键词/代码前缀三要素联合判定，QDII 单独分类，识别结果以取价方式列颜色区分），与实际 `market_value.py` 分类逻辑一致。
- **注册表使用说明修正（`how-to-use-registry.md`）**：① 注册表结构表移除已并入「持仓关系矩阵」的缓存模块 `fund_overlap`（`_MODULE_REGISTRY` 中已删除），TTL 由「24h~7d」修正为「24h」；②「无需手动维护的派生产出」误称报表页签标题/Excel 标签随 `_MODULE_REGISTRY` 自动派生——实际由独立 `_REPORT_SECTION_DEFAULT` 注册表驱动，改为说明注释；③「计算模块注册表」交叉引用去掉裸 `§` 符号，改文字指引；④ 计算模块表 `量化指标` 名称对齐代码 `量化指标计算`。**同步清理**：`how-to-config.md` 缓存 TTL 表移除同源失效行 `fund_overlap`（模块已删除）。
- **测试**：纯文档修正，无代码变更。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 调仓建议可行化层区分场内/场外渠道

- **动机**：调仓建议可行化层（`analysis/rebalance_advisor`）此前仅凭代码前缀 + 名称关键词判定证券类型，场外持有基金（LOF/开放式指数基金，如 `161725 招商中证白酒指数A`、`110022 易方达消费行业`）的 16/11 开头代码命中场内基金前缀，被误当场内处理（100 份取整 + 仅计佣金），漏计赎回费且份额取整过粗。
- **持仓明细携带渠道上下文**：`holdings_details` 契约（`orchestrator.prepare_report_data` 与 `_report_generation` both 路径 `_both_action_holdings_details`）新增 `channel` 字段，按账户关键词 `is_offsite_fund(account)` 判定填充（`"场外"`/`"场内"`）；`getattr` 兼容缺 `account` 的 detail 对象（测试 fixture 简化版）。
- **可行化层按渠道消费**：`_round_to_lot`/`estimate_fee` 新增 `channel` 参数——`channel="场外"` 强制整数份取整 + 计收赎回费；非场外回退既有证券类型判定（A 股印花税 / 场内基金仅佣金 / 100 份取整），避免用单一渠道覆盖 A 股印花税等差异化费率。显式 `channel` 优先，其次按 `account` 关键词判定，两者皆无保持向后兼容。候选构造（再平衡/纪律）携带渠道到可行化层。
- **测试**：`test_rebalance_advisor.py` 新增渠道感知 10 项（场外 LOF/开放式基金整数份 + 赎回费、场内 ETF 100 份 + 仅佣金、A 股渠道仍计印花税、显式 channel 优先于 account、账户关键词回退、无渠道回退代码判定）；`test_orchestrator.py` 新增契约 channel 字段 2 项（场内/场外账户各一）+ both 路径 channel 接线 1 项。
- **门禁**：dev-verify 1820 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 再平衡信号配置化阈值 + 静默期 + 回撤纪律峰值注入 + 日收益口径统一（第四批）

- **再平衡信号配置化阈值 + 静默期**：`analysis/simple_rebalance` 的再平衡阈值与静默期由硬编码改为配置化参数（`threshold`/`silence_days`/`silence_file`），与纪律层共用 `_silence.py` 静默机制；智囊团深度复盘「行动摘要」的 LLM 段**豁免静默期**（`prompts_core` 以 `silence_days=0` 调用），保证每次复盘完整呈现超限信号、不被静默窗口抑制；新增回归验证 LLM 段不写共享静默文件。
- **回撤纪律管线注入组合历史峰值市值**：组合级回撤纪律此前在生产路径**从未激活**——`build_action_data` 的两处调用（`orchestrator.prepare_report_data`、`_report_generation` both 路径）均未传 `portfolio_peak_mv`，而峰值只能从 `history_data.bars` 计算且晚于 action_data 构建。修复：新增 `metrics.compute_portfolio_peak_mv(bars)` 计算历史峰值；both 路径将 action_data 构建移至「3. 历史走势」之后并注入峰值；full 路径在 `_prepare_full_risk_metrics` 后重建 action_data 并覆盖 prep/pipeline_data；新增 `persist_silence` 参数使 `prepare_report_data` 的中间占位构建不读写纪律静默文件，保证峰值就绪后的最终构建为管线中纪律静默的唯一写入方（单品信号不被占位构建抢占静默而误抑制）。
- **日收益口径统一**：`metrics.compute_daily_returns` 成为 tail_risk 与组合走势表共用的单一口径源（prev 与 curr 市值均 >0 才计入，跳过缺失/占位/清仓的伪 -100% 单日）；`tail_risk` 与 `portfolio_history` 均委托之，VaR/最大单日跌幅/年化波动率与走势表日收益完全一致。
- **测试**：新增组合峰值市值计算 4 项、`persist_silence=False` 不读写静默文件 1 项、both/full 路径峰值注入接线 3 项（含历史走势关闭时峰值取 None 的降级路径）。
- **门禁**：dev-verify 1810 passed + check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]。

### 统一熔断网关 + 指标熔断状态文件落盘位置修正 + 菜单 [1] 基础缓存刷新补齐

- **统一熔断网关（三路聚合）**：`CircuitBreakerGateway` 将数据源熔断（DataSourceRegistry）、LLM 端点熔断、指标熔断（IndicatorBreaker）三路状态聚合到统一查询入口——`gateway.get("data_source"/"indicator"/"llm")`、`gateway.summary()`，并新增模块级 `get_indicator_breaker_status()`/`get_all_breaker_status()` 包装函数。`technical.md` §2.2「统一熔断网关」段落同步更新为三路聚合描述。
- **指标熔断状态文件落盘位置修正**：指标熔断器持久化文件从 `data/cache/metrics_breaker.json` 调整至 `data/state/metrics_breaker.json`（运行时状态目录），旧路径文件在首次加载时自动改写至新位置并删除旧文件，避免被缓存清理误扫。`technical.md` §2.2 持久化列与 `datasource-reliability.md` §4.1 同步更新。
- **菜单 [1] 更新基础类缓存补齐**：新增三项刷新——财经新闻（持仓关键词聚合预热 `news_` 缓存）、基金经理（逐基金刷新 `fund_manager_` 缓存）、基金风格扩展（A 股扩展数据预取到 registry 会话缓存）；同时补齐有基金路径此前缺失的行业分类、分红刷新。纯股票组合路径同样刷新新闻与风格扩展。`how-to-menu.md` 菜单 [1] 说明同步更新。
- **测试**：新增统一熔断网关 12 项、指标熔断持久化路径 3 项、菜单 [1] 扩展缓存刷新 19 项（新闻/基金经理/风格扩展 helper + 并行编排 + update_basic_cache 两分支接线 + 显示三行输出）。
- **门禁**：check-code-traces / check-doc-traces / check-task-numbering `--ci` 全 [OK]；提交前跑 dev-verify 全量验证。

### 基金业绩评级类型差异化阈值接线

- **动机**：`tiantian_ranking` 已定义四组类型差异化评级阈值（默认/债券/指数/QDII）与类型提示参数，但 `fetch_fund_rankings` 调用评级计算时未传类型，导致债券型/QDII 的宽松阈值与指数型的严格阈值**从未生效**，所有基金均按主动权益默认阈值评级。
- **接线**：新增 `_fund_type_hint_from_name(name)`——按基金名称推导阈值类型键（优先级：QDII/隐式海外 → 债券型 → 指数/ETF/联接 → 默认，与穿透分类 `classify_penetration` 一致）；`fetch_fund_rankings` 从 JS `fS_name` 提取名称后推导类型，透传至 `_calc_rating_from_entry`，并在返回结构 `type` 字段回填类型键（此前恒为 `""`）。调用链（fetcher 包装、报告、缓存刷新、候选比较）零签名变更。
- **行为影响**：债券型/QDII 在 10~15% 百分位区间由「良好」升至「优秀」，指数型在 25~30% 区间由「良好」降为「稳定」，评级与「类型」列展示的基金分类口径一致。
- **文档**：`requirements.md` §6.4.5 基金业绩分析补充类型差异化评级阈值表。
- **测试**：`test_tiantian.py` 新增类型推导 9 项 + `fetch_fund_rankings` 接线 6 项（mock `_request_pingzhong_data`，覆盖债券/指数/QDII/主动权益四类阈值生效与无排名数据回退）。
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
