# 自我审查问题记录归档 — v0.10.x

> 归档时间：2026-08-06；2026-08-16 二次合并 review-findings.md 已解决项（rf-248 ~ rf-275，v0.10.10 ~ v0.10.13 已发布版本）；2026-08-17 四次合并（rf-282 ~ rf-287，v0.10.14-dev）；2026-08-29 发布 v0.10.15 合并（rf-288 ~ rf-294）
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.10.1 ~ v0.10.13（2026-08-04 ~ 2026-08-14，已发布；v0.10.0 无独立 changelog 段，已发布记录自 v0.10.1 起）+ v0.10.14-dev 批次（2026-08-16 ~ 2026-08-17，未发布、按用户要求提前归档）+ v0.10.15 批次（2026-08-17 ~ 2026-08-29，已发布）
> 归档内容：本迭代已修复的 rf 记录（rf-204 ~ rf-294）摘要行 + 修复方案 + 变更记录；v0.10.14-dev 已解决项（rf-276 ~ rf-287）按用户要求提前归档于 v0.10.14 章节，v0.10.15 已解决项（rf-288 ~ rf-294）随发布归档于 v0.10.15 章节，未完成待办项保留在原文件 review-findings.md

---

## 已修复问题

### v0.10.4（2026-08-05）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-226 | `_evaluate_percent_value` 对「组合级收益 + 个股级收益同句段」误配：组合累计收益 10.0% 被整句主体定位误路由到数值最近的个股（招商银行 8.2%），报假阳性（HEAD 基线已复现） | 新增组合级语境检测 `_is_portfolio_level_context`（`_PORTFOLIO_KEYWORDS` 词表，match 前 15 字符窗口），在主体定位前判定组合级收益并归到组合总收益率 | `changelog.md` v0.10.4 |

### v0.10.3（2026-08-05）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-223 | 批量暗号替换脚本（/tmp/clean_ciphers.py，本次会话一次性工具）`[ \t]{2,}` 折叠整行空白，破坏 9 个 Python 文件前导缩进（report 4 个 + test 5 个，IndentationError） | 按 HEAD 逐行映射恢复前导空白（行数 1:1 已验），全仓 git diff 范围内 `compile()` 通过 | `changelog.md` v0.10.3 |
| rf-224 | 批量暗号替换脚本误处理：截断需求 ID `R-LLM-DB-QA-CONCENTRATION-03/04`（test_debate_prompts.py）、删除 `I2.` 段头序号（_config_defaults.py / how-to-config.md）、产生空头 `── ──` | 需求 ID 恢复完整并纳入 DASHTASK 豁免（requirements.md 表格定义的合法需求交叉引用，非任务编号）；交易纪律段头改纯语义「交易纪律配置」（`I2` 属配置索引暗号，两处同步） | `changelog.md` v0.10.3 |
| rf-225 | 语义清理将模块级 `_C19_KEYS` 重命名为 `__KEYS`，双下划线在类内触发 Python 名称混淆（NameError：`test_correlation.py` 2 例 + `test_pipeline_factor_exposure.py` 1 例） | 改语义名 `_CONTRACT_KEYS`（单下划线 + 语义名，符合命名纪律），3 处引用同步；P0 门禁 dev-verify 复跑 1649 全过 | `changelog.md` v0.10.3 |
| rf-220 | check-code-traces 缺迭代轮次检测 + 测试层残留轮次引用（`test_html_writer.py`「对应轮13 验收标准」等） | 测试层轮次注释改语义描述；check-code-traces.py 新增 ROUND 模式（`第 N 轮`/`N 轮`/`轮N`）+ 计数/运行时豁免（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/轮换、第 N 轮循环），退出码归入任务编号类（exit 2） | `changelog.md` v0.10.3 |
| rf-221 | 迭代轮次检测缺口：check-doc-traces 完全无「第 N 轮/经 N 轮/N 轮/轮 N」检测；check-code-traces ROUND 只匹配「轮N」紧贴形式，漏检空格分隔「轮 12」「轮 7」等旧注释（4 处） | check-doc-traces 镜像 ROUND 模式（含空格「轮 N」）+ 计数/运行时豁免（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/轮换/轮番/轮涨/轮跌、第 N 轮循环），ROUND 不进 trace-exempt 文档扫描（changelog/plan/review-findings/plan 目录豁免）；check-code-traces ROUND 放宽为「轮\s*N」；清理 4 处空格分隔旧注释（industry_beta/excel_fund_deep_analysis/orchestrator/test_return_attribution）；新增 TestDocRoundDetection 4 例 | `changelog.md` v0.10.3 |
| rf-222 | 契约改名叙述漏检：注释残留「原 factor_exposure 契约迁移为主键」等历史契约改名痕迹（7 处 src 注释 + 1 处 scenario 测试），两检查脚本只覆盖「原+固定名词 / 迁移自 / 迁移到新X」，漏掉「原+标识符+迁移为/为主键」形状 | 7 处 src 注释 + 1 处 scenario 测试改纯语义描述（style_factor_data 主键）；check-code-traces/check-doc-traces 同步补 HIGH 模式「原 X…迁移/改称/并入」（ASCII 标识符 + 契约/dict/数据契约 限定词，中文后续「原始数据迁移」不误伤）；新增代码/文档各 1 例回归测试 | `changelog.md` v0.10.3 |
| rf-219 | 测试层残留章节数字引用 + check-code-traces 缺章节编号检测（测试 fixture 硬编码陈旧章节序号、docstring/注释残留「N 章」暗号等） | 测试层全部改为纯语义章节描述 + 陈旧 fixture 编号对齐当前 registry；check-code-traces.py 镜像 CHAPTER 模式 + 计数豁免（共 N 章等不误报），退出码归入 exit 2 | `changelog.md` v0.10.3 |
| rf-218 | 源码/注释残留章节数字引用（`报告第 N 页`、`N 章「X」`），部分因合并重排已陈旧 | 全部改为纯语义章节描述，不依赖章节数字；合并章模块 docstring 改用当前章节语义名 | `changelog.md` v0.10.3 |

### v0.10.1（2026-08-04）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-204 | 版本一致性检查全文 contains 会漏检头部版本行未同步（正文偶然版本号掩盖） | 管理文档改用「文档版本：」头部行精确匹配；`--fix` 自动修正头部版本行 | `changelog.md` v0.10.1 |
| rf-205 | 事实校验把非收益率百分比（胜率/评分权重/相对基准跑输跑赢）误修正为持仓收益率，且亏损品种修正丢失负号（518880 -8.86% 输出 +8.9%） | `_evaluate_percent_value` 补胜率/权重/相对基准近邻语境跳过；修正输出改带符号收益率保留盈亏方向 | `changelog.md` v0.10.1 |
| rf-206 | 版本一致性回归测试硬编码正斜杠路径，Windows 下 `relative_to` 返回反斜杠导致永不匹配、dev-verify 必失败 | 构造 CHECKS 类型字典时把 `relative_to` 结果分隔符规范化为 `/` | `changelog.md` v0.10.1 |
| rf-207 | 数值校验策略 1 全局最近邻忽略句中明确品种代码：句中已写明确主体（「建设银行收益率 3.2%」）、数值接近无关品种容差内（与 240012 差 0.96≤1.0）即误判通过，漏检与主体 601939 的 1.33 超差 | `_evaluate_percent_value` 将主体解析提前到策略 1 前：句中有明确持仓主体（代码/名称）时按该主体实际收益率校验（容差内通过、超差报错），无主体或主体无收益率数据时回退全局最近邻 | `changelog.md` v0.10.1 |
| rf-208 | 门禁只扫注释且 CODE 仅 `(?:rf\|plan\|R)-\d+`，抓不住系列代号（`b_series`/`G系列`/`F4`/`B6`），也不扫代码标识符 | check-code-traces 注释 CODE 补 `[A-Za-z]系列`/单字母`_series`；新增标识符扫描维度（`.py` ast、`.js` 正则）捕获大写裸字母+数字/单字母`_series`/`系列`/嵌入 `rf/plan`+数字；IDENT 类等同 CODE 退出码 2；check-doc-traces 同步补系列模式 | `changelog.md` v0.10.1 |
| rf-209 | 交易纪律代码审查（轮5）HIGH：both 报告路径组装 `action_data` 时 `profit_rate` 传小数值，纪律引擎按百分数阈值比较 → 止盈/止损纪律永不触发 | both 路径将 `profit_rate` 换算为百分数（`×100`，同 full 路径 orchestrator 口径），并补回归测试断言 | `changelog.md` 轮5 |
| rf-210 | 交易纪律代码审查（轮5）MEDIUM：组合回撤纪律依赖 `portfolio_peak_mv`，当前管线未注入（历史峰值数据待 plan-20 历史增强接入） | 回撤纪律已实现并测试；管线注入属历史增强范围，changelog 标注「回撤数据接线说明」，组合级信号不参与单品静默期（与再平衡 category/summary 约定一致）已文档化 | `changelog.md` 轮5 |
| rf-211 | 交易纪律代码审查（轮5）MEDIUM：`discipline` 配置校验缺语义约束，止损线误配为正数时与止盈线冲突 | 补充符号校验：止盈线须正数、止损线须负数（符号约束自动保证止盈线 > 止损线，杜绝同品种同时触发） | `changelog.md` 轮5 |
| rf-212 | 交易纪律代码审查（轮5）LOW：`action_advisor.py` 注释含任务代号「轮6/轮7」 | 改为语义描述「调仓建议（可行化清单）与收益归因（贡献占比）为后续增强能力」 | `changelog.md` 轮5 |
| rf-213 | 交易纪律代码审查（轮5）LOW：回撤线配置为正值（10）时规则文本显示「回撤线 10%」有歧义 | 统一按负值展示「回撤线 -10%」（`-abs(drawdown_pct)` 后格式化） | `changelog.md` 轮5 |
| rf-214 | 调仓建议代码审查 MEDIUM：00 前缀债券型基金（名称含"债券"无细分词，如 `000311 景顺长城景颐双利债券A`）误判为 A 股 → 100 份取整 + 印花税，漏计赎回费 | `_OTC_FUND_NAME_KW` 补「债券/指数/股票」关键词（仅 00 前缀分支生效，A 股股票名不含这些词，无副作用），回归测试断言整数份 + 赎回费 | `changelog.md` 轮6 |
| rf-215 | 调仓建议代码审查 LOW：`estimate_fee` 的 `operation` 参数未被使用，未来买入调用会静默按卖出口径计费 | 增加卖出方向守卫（未知操作抛 ValueError），杜绝静默误计费，参数保留供后续买卖方向区分 | `changelog.md` 轮6 |
| rf-216 | 调仓建议代码审查 LOW：持仓名称缺失（None）时 `is_otc_fund_by_name` 抛 TypeError 中断整条清单 | `_round_to_lot`/`estimate_fee` 名称归一化为空串后参与判定，防御性降级（00 前缀按 A 股口径） | `changelog.md` 轮6 |

### v0.10.7（2026-08-05）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-233 | `test_circuit_breaker_wrapper.py` 的 `test_default_path_under_state_dir` 用硬编码正斜杠子串 `data/state/metrics_breaker.json` 对实际路径做 `in` 匹配——Linux 下 `tmp_path` 为正斜杠路径恰好命中，Windows 下为反斜杠路径断言落空（Windows dev-verify 单点失败） | 断言前将实际路径分隔符统一规范化为 `/`（`path.replace(os.sep, "/")`）再匹配，正向/负向两条断言同时修正；源码（`os.path.join`）与 conftest 隔离（`tmp_path / ...`）本就 OS 感知，无需改动。test_circuit_breaker_wrapper.py 10 项全通过 | `changelog.md` v0.10.7 |
| rf-229 | 语义命名索引「功能语义命名表」仅为记录性活索引、无正面校验——新增 `report_submodules.*` 开关键可绕过登记、功能删除后表行可残留僵尸条目（预演审计实证：`cost_lots` 未登记、`dividend_flow`/`holding_diagnosis` 为僵尸条目）、合并章 sheet key 无人核实 | 新增 `scripts/check-semantic-index.py` 正面校验（正向 `report_submodules` 键登记 / 反向僵尸条目 / 合并章 sheet key 存在性，tokenize 剔除注释，退出码 0/2）；表存量修正（`cost_lots` 补登记、僵尸条目移除、表体包裹 `<!-- semantic-index:start/end -->` 标记）；纪律升级为架构设计约束的「约束外参照」并接入 P0/P2 门禁 | `changelog.md` v0.10.7 |
| rf-217 | 调仓建议可行化层（`analysis/rebalance_advisor`）仅凭代码前缀 + 名称关键词判定证券类型，场外持有基金（LOF/开放式指数基金，如 `161725 招商中证白酒指数A`、`110022 易方达消费行业`）的 16/11 开头代码命中场内基金前缀被误当场内处理（100 份取整 + 仅计佣金），漏计赎回费且份额取整过粗 | `holdings_details` 契约新增 `channel` 字段（报告层按账户关键词 `is_offsite_fund` 判定填充），`_round_to_lot`/`estimate_fee` 按渠道计算（场外整数份 + 赎回费；非场外回退既有证券类型判定）；显式 `channel` 优先、无渠道回退代码判定保持向后兼容 | `changelog.md` v0.10.7 |

### v0.10.6（2026-08-05）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-232 | `test_runner.py::_update_test_coverage_doc_file` 打印路径用 `os.path.relpath(_DOC_COVERAGE_PATH, _PROJECT_ROOT)`，Windows 下两路径跨盘符（测试将 `_DOC_COVERAGE_PATH` monkeypatch 到 C: 临时目录，项目在 D:）时 relpath 抛 `ValueError: path is on mount 'C:', start on mount 'D:'`，`unit` 模式 1 failed（`test_update_doc_file_writes_only_when_changed`）。已用单用例复现，traceback 落 929 行 print | 新增 `_display_path(path, start)`：relpath 抛 ValueError 时降级返回绝对路径；替换 925/929 两处 relpath；新增回归测试 `test_display_path_cross_drive_fallback`（Windows 断言降级绝对路径，POSIX 断言正常相对路径，平台无关）。test_test_runner_doc_writer.py 23 passed | `changelog.md` v0.10.6 |
| rf-231 | `test_handlers_whatif.py::TestSelectCandidateFile` 三处断言硬编码 POSIX 风格路径，Windows 下 dev-verify 失败：① `test_only_base_choose_copy_template`/`test_only_base_invalid_choice_then_copy_template` 期望 `dummy_dir/base-调仓后模板.xlsx`（正斜杠），而 `_copy_base_as_template` 用 `os.path.join` 拼接（Windows `\`）；② `test_only_base_manual_input_valid` 期望返回 `/tmp/after.xlsx`，但 `_manual_input_path` 对输入做 `os.path.abspath`（Windows `D:\tmp\after.xlsx`） | 断言改平台无关：模板路径用 `os.path.join("dummy_dir", "base-调仓后模板.xlsx")`，手动输入返回用 `os.path.abspath("/tmp/after.xlsx")`；测试文件补 `import os`。test_handlers_whatif.py 16 passed | `changelog.md` v0.10.6 |
| rf-230 | 事实校验自动修正将 LLM 调仓建议的止盈/减仓目标比例（「建议止盈约30-40%持仓」「止盈约20-30%」）误当作收益率，修正为最近邻品种收益率（601398 实际 70.2%）——报告原文被篡改为「止盈约30-70.2%」「止盈约20-70.2%」，建议语义失真。根因：① 语境识别缺失——`_REBALANCE_TARGET_KEYWORDS` 仅覆盖「降至/减仓至」等"至"字式，漏掉「止盈约/减仓约」等"约"字式；句子含「利润/盈利」触发收益语境后，比例值走全局最近邻被误修正；② `apply_numerical_corrections` 用 `re.sub` 无 `count` 限制，一处修正连带替换 HTML 中所有同值出现处 | ① `fact_checker/_constants.py` 新增 `_TRIM_TARGET_KEYWORDS`（止盈/减仓/加仓/止损/清仓/调仓等）+ `_context.py` 新增 `_is_trim_target_context`（match 前 15 字符邻近窗口）+ `_numerical.py` `_evaluate_percent_value` 开头拦截（与胜率/权重等非收益率语境同级）；② `_corrections.py` 的 `re.sub` 加 `count=1` 只替换判定处。新增回归测试 `TestTrimTargetContext`（真实复现句 30-40%/20-30% 不误修正 + 真实收益率仍校验）+ `TestApplyCorrectionSingleReplace`（同值异义只替换一处） | `changelog.md` v0.10.6 |

### v0.10.5（2026-08-05）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-228 | TUI 菜单「2」更新行情缓存时进程崩溃 `[FATAL:partition_address_space.cc(243)] Check failed: !IsConfigurablePoolInitialized()`。根因：菜单 2 的并行价格抓取（ThreadPoolExecutor 4 workers）中，每个价格的新鲜度校验 `_price_cache_fresh` → `get_last_trading_day()` → `_get_trading_calendar()` → `akshare.tool_trade_date_hist_sina()`，akshare 内部用 `py_mini_racer`(V8) 解密新浪接口且每次调用都重新初始化 V8；多线程并发首次初始化 V8 触发 partition_address_space FATAL，**直接 abort 整个进程**（try/except 无法捕获）。已在 tmp 探针脚本复现（4 线程并发 → EXIT 3 崩溃；加锁串行化 → 全成功） | `_get_trading_calendar()` 缓存未命中分支用模块级锁 `_TRADING_CALENDAR_AKSHARE_LOCK` 串行化 + 双重检查（避免锁等待后重复拉取）。V8 顺序初始化安全。新增回归测试 `TestTradingCalendarConcurrency`：4 线程并发调用 `_get_trading_calendar()` 注入 fake akshare，断言回调最大并发深度 = 1。**连带优化**：测试文件 `test_market_value.py` 多个测试类裸调用 `is_market_open`（东方财富 push2 API 真实 HTTP）与 `_is_trading_day`（akshare 交易日历）致单用例 2~6s，统一补 setUp mock 隔离网络 | `changelog.md` v0.10.5 |
| rf-227 | `test_cli_integration.py` 三处 CLI 测试 patch 目标陈旧（41df26a 根文件归子包重构后残留包级 re-export 路径 `src.python.cli._cli_read_holdings`，拦截不到 `cli.py` 内部调用）：`test_cli_cache_config_respected` 直接读取真实持仓文件失败（`/test/holdings/test.xlsx` 不存在 → mock 被调用 0 次断言失败），另两例靠默认持仓文件恰好存在而侥幸通过 | 三处 patch 目标统一修正到 `src.python.cli.cli._cli_read_holdings(_with_flows)`；report 路径两例改用 `_cli_read_holdings_with_flows` 返回 `(mock_holdings, [], [])`（与 `_handle_report` 实际调用一致），彻底脱离真实持仓文件依赖。全量 all 5026 passed、CLI 单测 56 passed | `changelog.md` v0.10.5 |

### v0.10.9（2026-08-06）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-239 | 事实校验两处误修正：`_locate_subject_code` 名称分支起点距离平局（建设银行/工商银行距 anchor 均 8）误路由把 601939 正确 171.23% 改写为 601398 的 70.2%；止损警戒阈值「回调20%的警戒区域」被当收益率误修正为 -11.8% | 名称分支改用最近边距离 `min(abs(idx-anchor), abs(idx+len(name)-anchor))`；`_is_trim_target_context` 增警戒词宽窗口检测。新增 6 个回归测试，修复前均失败，修复后 fact_checker 单文件 109 通过 | `changelog.md` v0.10.9 |
| rf-240 | 测试污染真实快照目录：`test_corrupt_snapshot_file_skipped` 用 `from src.python.core.constants import HISTORY_SNAPSHOT_DIR` 在 import 时拷贝旧值，绕过 conftest 隔离，把损坏文件写入真实 `data/history/snapshots/` | 改用 `import src.python.core.constants as core_constants` 模块属性访问，使隔离生效；edge 测试 6 passed，真实快照目录无新增残留 | `changelog.md` v0.10.9 |
| rf-241 | 数据质量仪表盘「品种覆盖/可信度」区块渲染崩溃：`position_status.items`/`data_freshness.items` 在 Jinja2 命中 dict 内置 `items` 方法（bound method）而非契约键 → `TypeError: 'builtin_function_or_method' object is not iterable` | guard 与循环改用 `.get("items")`（与生产代码一致），空 items 正确显示降级占位；新增 `TestHtmlDataQualityBlocks` 4 用例，修复前 `_render_template` 抛 TypeError | `changelog.md` v0.10.9 |
| rf-242 | 报告生成骨架测试污染真实 reports 目录：`test_generate_report_skeleton` 用 `config={}` 真实调用，`output_dir` fallback 到相对路径 `"reports"` → 解析到真实 reports 目录，空持仓跨整天累积 37 个残留文件 | 传入 `output_dir=tempfile.TemporaryDirectory()` 隔离；conftest 新增 `_isolate_report_output_dir` autouse 防线把真实落盘入口透明重定向到 tmp；回归测试恢复 `config={}` 真实调用并以 `reports/` 文件快照断言无新增作永久守护 | `changelog.md` v0.10.9 |
| rf-243 | Excel 正文标题序号未跟随 `report_section_order` 配置：页签栏 tab 名用可见连续序号（行动建议=10），正文标题用注册表默认序号（行动建议=17），两者不一致 | create_sheets 创建页签时就地标记 `visible_number`；registry 新增 `get_report_section_number_from_order`；7 个深度页签写入函数新增 `section_order` 参数并透传。**后经 rf-244 设计调整收敛**：正文标题统一为纯中文名，同步机制全部撤除 | `changelog.md` v0.10.9 |
| rf-244 | 设计调整（rf-243 方案收敛）：序号只在 Excel 页签栏与 HTML 章节标题出现，Excel 正文标题统一为纯中文名 | 撤除 rf-243 正文标题序号同步机制（`get_report_section_number_from_order`/`visible_number` 标记/`section_order` 透传），正文不依赖序号，调整配置/隐藏章节不错位；test_correlation_sheet 正文标题断言同步更新 | `changelog.md` v0.10.9 |
| rf-245 | 历史走势关闭时仅剩误导性「尾部风险：无历史 bars」警告：`fetch_history=False` 静默跳过，用户无法判断是配置关闭所致 | ① fetch 关闭时 `reporter.warn`+`logger.warning` 醒目提示「组合历史走势获取已跳过（history off）」及占位后果；② CLI `--history` 默认改为跟随 `config.history.fetch_mode`（默认 auto），未显式传参时由 `generate_report` 回退到配置层 | `changelog.md` v0.10.9 |
| rf-246 | cli.ps1 文件头注释声称 "UTF-8 with BOM" 实际无 BOM，Windows PowerShell 5.1 对无 BOM 的 UTF-8 中文按 ANSI/GBK 误读注释解析崩溃（跨机器复现） | 补回 BOM（`EF BB BF`，UTF-8+CRLF），PowerShell Parser 验证通过；CLAUDE.md 技术要点新增编码/BOM 约束、新增 `.editorconfig`（`[*.ps1] charset = utf-8-bom`）供跨机器自动遵守 | `changelog.md` v0.10.9 |
| rf-247 | 报告子模块三个提示/缺省缺口：① `candidate_compare` 开启但无候选配置时静默跳过；② `cost_lots` 开启但无流水时 HTML 盈亏汇总区静默消失；③ `data_quality` 缺省 `false` | ① HTML 模板外层守卫改 `{% if candidate_data %}` + `available` 分支渲染「未配置候选基金」占位、Excel 新增 `_write_candidate_unavailable_block`；② 补「成本流水子模块已开启，但未录入交易/分红流水…」empty-note 提示；③ `data_quality` 缺省 `false`→`true` + `is_enable_data_quality` 兜底改缺省 true | `changelog.md` v0.10.9 |

### v0.10.8（2026-08-06）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-234 | `report/_report_generation.py`（1018）超过 800 行硬性上限 | facade 聚合门面拆分：后台健康检查→`_report_health.py`、轻量行情/注入/校验→`_report_helpers.py`、全量指标装配→`_full_risk_metrics.py`、图表数据集→`_chart_dataset_factory.py`；门面保留 both/full 双路径编排并 re-export 全部符号（拆分后 686 行），mock patch 接线零改动 | `changelog.md` v0.10.8 |
| rf-235 | `report/html_writer.py`（934）超过 800 行硬性上限 | facade 聚合门面拆分：章节可见性/目录导航→`html_writer_nav.py`、数据契约展示映射→`html_writer_display.py`、JS 资产复制→`html_writer_assets.py`；门面保留 `write_html_report`/`_render_template` 并 re-export 符号（拆分后 660 行） | `changelog.md` v0.10.8 |
| rf-236 | `analysis/metrics.py`（880）超过 800 行硬性上限 | facade 聚合门面拆分：收益类指标→`metrics_returns.py`、风险类指标→`metrics_risk.py`；门面保留 `compute_all_metrics` 聚合入口 + `__all__` + 常量并 re-export 符号（拆分后 225 行），子模块维持 analysis 层单向依赖约束 | `changelog.md` v0.10.8 |
| rf-237 | `report/orchestrator.py`（822）超过 800 行硬性上限 | facade 聚合门面拆分：风格因子/行业 Beta 计算族→`_report_factor_metrics.py`、市场温度/持仓相关性→`_report_aux_metrics.py`；门面保留 `generate_report`/`prepare_report_data`/`compute_valuation_data`/`_fetch_valuation_for_code` 并 re-export 符号（拆分后 442 行），mock patch 接线零改动 | `changelog.md` v0.10.8 |
| rf-238 | `llm/generators_orchestrator.py`（808）超过 800 行硬性上限 | facade 聚合门面拆分：新闻关联责任单元（模块级结果缓存/闭包/安全直调）→`_llm_news_correlation.py`；门面保留缓存预检/worker 分发/主编排入口并 re-export 符号（拆分后 698 行），mock patch 接线零改动 | `changelog.md` v0.10.8 |

### v0.10.10（2026-08-06）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-248 | test-chart.html 动态注入 chart 脚本未设 `s.async=false` → 注入循环补 `s.async=false` 对齐报告模板 defer 语义 | `changelog.md` v0.10.10 |
| rf-249 | 折线/雷达图 tooltip 悬停无法触发（`pointRadius:0` + `intersect:true`）→ `lineOptions`/radar 补 `interaction`；调试页自检时序 800ms 误报 → onload 触发；offline 文案修正 | `changelog.md` v0.10.10 |
| rf-250 | 调试页自检用 `canvas._chart` 判定接管（v4 无此句柄恒假）→ 改官方 API `Chart.getChart(canvas)` | `changelog.md` v0.10.10 |
| rf-251 | chart-init 守卫不拦截空数组致 empty 场景 TypeError → 6 处守卫补 `!ds.labels.length` + `!ds.datasets.length` 显式跳过 | `changelog.md` v0.10.10 |
| rf-252 | Web 上传预检伪装 zip 致 `KeyError` 逃逸 → `_prevalidate` 任意异常统一转 UPLOAD_BAD_FILE + edge 测试 | `changelog.md` v0.10.10 |
| rf-253 | `RunManager._trim_runs` 仅 submit 时调用致注册表超限 → worker finally 分支补 `_trim_runs()` 持锁清理 | `changelog.md` v0.10.10 |
| rf-254 | `_build_artifacts` 对 failed/严重失败仍返回产物按钮 → 空列表（无产物即无按钮）+ 四用例回归 | `changelog.md` v0.10.10 plan-8 阶段2 |
| rf-255 | `check-doc-traces.py` 裸版本号模式误判 IP → `_line_exempt()` 增 IPv4 整行豁免 + 双用例回归 | `changelog.md` v0.10.10 plan-8 阶段3 |
| rf-256 | `output_dir` 锁文件检测未实现 → server 启动原子抢占写锁 + 占用警告 + 11 用例 | `changelog.md` v0.10.10 |

### v0.10.11（2026-08-06）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-258 | Web 前端无自动化测试 → 沉淀 `scripts/smoke-web.py` 可复跑脚本（test_client 全链路 9/9）+ test_smoke_web.py 载体 | `changelog.md` v0.10.11 |
| rf-259 | HTML 报告非自包含（外链 Chart.js 下载后空白）→ `_inline_js_assets` 内嵌 8 资产，报告单文件自包含 + 6 用例 | `changelog.md` v0.10.11 |
| rf-260 | Web 状态区缺系统信息 → `_build_system_info`（版本/IP/LLM 状态）+ 状态区卡片 + 7 用例 | `changelog.md` v0.10.11 |
| rf-262 | `how-to-config.md` §M 功能开关表未列全 → 逐项补全 27 个 key + 计数修正 + faq 补充 | `changelog.md` v0.10.11 |
| rf-263 | `run_health_checks` 的 `max_timeout` 死参数 → daemon 线程 + 整体耗时预算，预算耗尽返回部分结果 + 回归用例 | `changelog.md` v0.10.11 |

### v0.10.12（2026-08-07）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-261 | Web 上传跑 full/both 污染共享快照目录 `data/history/snapshots/` → **试算/正式双模式**：web 默认试算（快照入 `snapshots/web/` namespace 子目录），正式更新显式选择（上传覆盖或直接用存量） | `changelog.md` v0.10.12 plan-25 |
| rf-264 | Web 首页系统信息卡缺 TUI 首页摘要对齐字段 → 增补配置摘要字段 + 6 用例 | `changelog.md` v0.10.12 |
| rf-265 | 应用名称硬编码散落 → `constants.py` 新增 `APP_NAME` 单一来源，TUI/Web/HTML/Excel 各入口统一强调名称与版本 + 4 处测试 | `changelog.md` v0.10.12 |
| rf-266 | `src/static/README.md` 资产说明滞后（仅图表 bundle）→ 重写为三类资产总览（图表/web/tmpl），原内容保留子节 | `changelog.md` v0.10.12 plan-27 |
| rf-267 | `smoke-web.py` 改写 `_DEFAULT_CONFIG` 不还原污染默认值 → `run_smoke` finally 统一还原 + 失效缓存；web+config 同进程 282 全绿 | `changelog.md` v0.10.12 plan-26 |
| rf-268 | 三模式文档体系建立后相关文档未同步（folders 重复/统计滞后、README 链接、CLAUDE.md 顺序）→ 去重 + 刷新 + 链接统一 | `changelog.md` v0.10.12 plan-28 |
| rf-269 | 提交 `3026ffa7`（README/CLAUDE.md 索引统一）未登记 changelog → 补登记独立条目 | `changelog.md` v0.10.12 plan-28 |

### v0.10.13（2026-08-14）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-270 | folders.md 目录树描述过时 + 树形符号错误 → ①② 计数修正（9→11、25→26）、③④ `└──`→`├──` | `changelog.md` v0.10.13 |
| rf-271 | `analysis/scenario.py` 两个死参数删除（`portfolio_volatility`/`annual_volatility`，Lo 常数近似不消费）+ docstring 诚实化，`vol_*`/CI 输出字段保留 | `changelog.md` v0.10.13 |
| rf-272 | 全仓 43 处 ARG001 未用函数参数全数处置：删参 21（含 40+ 调用点/测试同步）+ 契约保留 7 加 `# noqa: ARG001` + 独立项 3 单列跟踪 | `changelog.md` v0.10.13 |
| rf-273 | 全量测试进程退出 Logging error 噪声 → `core/logger.py` 新增 `_ClosedStreamSilentHandler`（closed file 静默降级，其余照常报告）+ `test_logger.py` 4 用例回归 | `changelog.md` v0.10.13 |
| rf-274 | Web 前端静态资产 404（阻断级）→ `app.py` 显式 `static_url_path="/static"` + `test_web_static_serving.py` 3 用例 + `smoke-web.py` 资产断言升级 200 | `changelog.md` v0.10.13 |
| rf-275 | main.js 旧浏览器兼容：`AbortSignal.timeout` 缺失同步抛 TypeError → 兼容兜底（AbortController+setTimeout）+ init 三加载器 `safeRun` 隔离 | `changelog.md` v0.10.13 |

### v0.10.14（2026-08-16，dev 批次提前归档）

> 用户要求：v0.10.14 仍处 dev（0.10.14-dev）时即归档本批次已解决项（rf-276 ~ rf-287），便于原文件聚焦待办。变更详情见 changelog.md [0.10.14-dev] 对应条目。

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-276 | v0.10.1+ 改动文档一致性全量审计（203 提交）→ A 类事实错误 / B 类用户文档缺口 / C 类管理文档三档问题 | A/B/C 三档全量修复：README 默认值、6 测试文件同步、reports-instruction 成本流水章节、需求/技术/测试文档补充（详见 changelog [0.10.14-dev]） | `changelog.md` [0.10.14-dev] |
| rf-277 | fact_checker 条件阈值误修正：穿透深度分析「收益率超过 200% 后可考虑部分止盈」的 200% 是止盈目标阈值，被误判为 600900 实际收益率修正为 59.2%（把正确文本改错） | 新增 `_CONDITION_TRIGGER_KEYWORDS` 触发词 + 后置调仓动作词双条件联合判定 | `changelog.md` [0.10.14-dev] |
| rf-278 | fact_checker 简称匹配漏检：「华安纳指+180.5%」（040046 实际 130.61%）因简称无法匹配全名、回退最近邻 180.5 恰命中 601939 真实值而漏检 | `_NAME_ALIAS_MAP` 简称归一化 + `_extract_core_name` 核心名前缀匹配 | `changelog.md` [0.10.14-dev] |
| rf-279 | dedup 校准脚本读取路径与写入路径不一致：`calibrate-dedup-threshold.py` 默认读 `data/cache/dedup_anchors.jsonl`（7-29 旧文件），而 `news_dedup.py` 自 commit `4e95d595`（2026-07-30）起写入 `data/calibration/dedup_anchors.jsonl`，脚本从未同步 → 校准建议基于过时快照 | 脚本默认路径改为 `data/calibration/`；基于最新 109018 条数据重校准——bg=2 ratio≥0.35 候选 523 条真实重复率仅约 25%，维持现阈值 | `changelog.md` [0.10.14-dev] |
| rf-280 | dedup 锚点文件重复计数：`dedup_anchors.jsonl` append-only，同一对 (source,title) 多轮运行重复追加（实测 61.6% 为重复），使校准数字失真（cross_skip bg=0 279→13800 虚增） | ① `_flush_anchors` 写入层去重——`_WRITTEN_ANCHOR_KEYS` 进程级集合 + `_load_written_keys` 惰性加载，跨轮只写新 key；② 校准脚本 `load_anchors` 统计层按 (source,title) 对去重，处理存量污染；③ conftest 隔离锚点路径 + 重置锚点单例。去重后校准锚点 109018→41761 | `changelog.md` [0.10.14-dev] |
| rf-281 | extract-test-failures.py 解析 pytest-html 报告崩溃：`_find_json_blob` 手工花括号扫描器假设 JSON 引号以反斜杠转义，但 pytest-html 将引号编码为 `&#34;` 实体 → 扫描器从不进入字符串态、日志内嵌 `}` 提前截断，`json.loads` 报 `Extra data`（全绿报告也崩溃，依赖此工具的失败用例提取流程不可用） | 按 `data-jsonblob` 属性起始引号到下一裸引号整体截取（blob 内引号均为实体编码，不会裸引号提前终止）+ 统一解码实体。新增 4 例回归测试（实体引号提取/日志内嵌花括号/无 blob/缺失结束引号） | `changelog.md` [0.10.14-dev] |
| rf-282 | `html_renderers._render_llm_content_section` 渲染器上下文参数过多（15 参） | 签名瘦身至 2 参（`enable_llm`/`llm_content`），删 13 死参并重构 `html_writer.py` 调用点 | `changelog.md` [0.10.14-dev] |
| rf-283 | `report/_pipeline.py` 遗留重复文件（已标注不承载活代码） | 确认无活引用后删除（`git rm`），测试迁移至活模块 `_llm_news.py` | `changelog.md` [0.10.14-dev] |
| rf-284 | `orchestrator.generate_report.warm_cache`（CLI `--warm` 标志）已无实际消费路径 | 删除 `--warm` 标志 + `warm_cache` 参数（含测试引用同步清理） | `changelog.md` [0.10.14-dev] |
| rf-285 | `smoke-web.py` 正式-用存量 run 提交后未轮询终态 → 后台 worker 线程仍写临时产物目录，`TemporaryDirectory` 清理撞并发写报 `OSError: Directory not empty`（CI 并行调度下偶发） | 抽 `_poll_run_finished(client, run_id)` 轮询 helper，正式-用存量 run 与进度事件检查统一轮询至终态（done/failed）后退出；断言语义不变，仅消除竞态窗口；回归测试新增 3 例，本地 8 次连跑稳定 | `changelog.md` [0.10.14-dev] |
| rf-286 | `test_menu_key_coverage` 菜单键集断言未同步日志可视化新增键——`MENU_ITEMS` 自加 `[V]`/`[H]` 后为 19 键，断言仍为旧 17 键，`integration`/`all_no_unit`/`all` 模式必失败（integration 不在 P0 门禁内，`--mode bench` 全量跑才暴露） | `test_tui_routing.py` 期望集补 `V`/`H`（回归断言直接验证缺失键），集成/全量模式复跑通过 | `changelog.md` [0.10.14-dev] |
| rf-287 | `check-test-markers.py` 标记合规检查的 `KNOWN_MARKERS` 与 `conftest._KNOWN_MARKERS` 漂移——缺 `unit_web`/`integration_cli`/`live` 三个实际在用的标记，导致脚本误报 17 处「未注册标记」、退出码 1（非门禁脚本，漂移未被日常门禁暴露） | 按 conftest 对齐 `check-test-markers.py` 全集（补 `unit_web`/`integration_cli`/`live` 三缺），277 文件 0 违规恢复通过；同步在 conftest 与 check-test-markers 移除死注册 `unit_config_edge`（0 用例） | `changelog.md` [0.10.14-dev] |

### v0.10.15（2026-08-29）

> 发布 v0.10.15 时整体归档已解决项（rf-288 ~ rf-294）。变更详情见 changelog.md [0.10.15] 对应条目。

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-288 | `test-runner.py` MODES `all_no_unit` 用 `-m "not unit"` 构建 pytest 参数会**覆盖** `pytest.ini` 的 `addopts = -m "not live"`，使 opt-in 的 live 真实网络套件（14 项）卷入 `--mode all_no_unit`/bench 计数 | `scripts/test-runner.py` MODES `all_no_unit` marker 改为 `not unit and not live`，与「live 不入门禁」语义对齐；修复后 `--mode all_no_unit` 收集 309，bench `--update-docs` 回填稳定不反复 | `changelog.md` [0.10.15] |
| rf-289 | 事实校验 `_locate_subject_code` 无法解析省略基金公司前缀的描述性缩写（"电池主题ETF"→561910），回退同句最近邻误路由，把正确 -3.92% 误修正为 -36.3% | `_utils.py` 新增 `_match_descriptive_tail` 描述性尾名匹配（≥3 汉字核心后缀 + 产品后缀，按距锚点距离择优），接入 `_locate_subject_code` 兜底；回归测试 `TestDescriptiveTailMatch` 5 项 | `changelog.md` [0.10.15] |
| rf-290 | dedup 跨源误合并率高（42560 锚点分层采样 ~70-80% 误合并：不同事件共享模板词天然 3-6 bigram，英文统一占位符虚高 ratio，bg=2 梯度与安全区直接合并误判多） | `news_dedup.py`：`_STOP_BIGRAMS` 扩至 ~280 模板词 + 提取前整体掩码；英文占位符按长度分桶；候选区门槛 0.35；bg=2 梯度 0.375 且含英数 token；安全区分级；跨源方向对立检测；`_normalize_title` 保留空格 + 剥离 N级；ratio 双向取 max。回归测试 `TestDedupFalseMergeGuard` 9 例 + `TestDedupTokenGradientMerge` 3 例 | `changelog.md` [0.10.15] |
| rf-291 | 事实校验 `_locate_subject_code` 短尾候选未覆盖「核心名+数字代号」缩略（"华安纳斯达克100"→040046），智囊团深度复盘 130.61% 被误归同句最近邻 601939 | `_utils.py` `_leading_token` 改为仅取前导数字串（"100ETF联接基金A"→"100"）生成「核心名+数字代号」短尾候选，接入 `_match_descriptive_tail`；回归测试 `TestSubjectAttributionMulti::test_thinktank_partial_name_short_tail` | `changelog.md` [0.10.15] |
| rf-292 | 组合单日/当日收益（"今日组合 +0.21%"）无语境保护，回退全局最近邻把当日收益误修正为数值最接近的品种收益率 | `_context.py` 新增 `_is_portfolio_daily_change_context`（前 18 字符时间词 + 紧邻"组合"标记判定），`_numerical.py` 组合级累计收益语境之后跳过；回归测试 `TestSubjectAttributionMulti::test_portfolio_daily_return_not_corrected` | `changelog.md` [0.10.15] |
| rf-293 | 事实校验 `_evaluate_percent_value` 单代码钉扎：句中恰含 1 个持仓代码时把所有百分比钉扎到该代码，与智囊团复盘相反 | `_locate_subject_code` 重构为「紧邻优先 + 代码/全名最近兜底」统一归因（代码/全名/简称/尾名四级，紧邻优先；无紧邻时句内代码/全名最近兜底）；回归测试 `TestSubjectAttributionMulti` 4 项 | `changelog.md` [0.10.15] |
| rf-294 | dedup 跨源收盘/午评同日收评簇漏判（“港股收评…” vs “8月18日港股收盘…”仅共享“恒指涨”2 bigram 被 cross_skip，校准 11847 条 skip 中发现 ~40 条真重复） | `news_dedup.py` `_normalize_title` 收盘术语同义归一：`收盘→收评`、`午评→收评`（只增不减，不破坏既有合并）；归一后收评簇 overlap 2→4、ratio≈0.54≥0.50 进入安全区合并。回归测试 `TestDedupByTitle::test_cross_source_roundup_closing_terminology_synonym_merged*` 2 例 | `changelog.md` [0.10.15] |

## 归档说明

- 本归档涵盖 v0.10.1 ~ v0.10.13 已发布版本的自审修复记录（rf-204~rf-275）、v0.10.14-dev 已解决项（rf-276~rf-287）与 v0.10.15 已解决项（rf-288~rf-294）；当前待处理项（rf-75~89 文件过长、rf-113/114 交互图表技术债、rf-257 Web 真机验收）保留在 `docs-stm/managements/review-findings.md`，不随版本归档。
- **二次合并（2026-08-16）**：`docs-stm/managements/review-findings.md`「已解决问题」区 v0.10.10 ~ v0.10.13 已发布版本修复项（rf-248~rf-275）整体迁入本文件对应版本章节。对应 plan.md P4 已完成项（plan-8/25/26/27/28）迁入 `archived_plan.0.10.x.md`、changelog [0.10.9]~[0.10.13] 迁入 `archived_changelog.0.10.x.md`。
- **三次合并（2026-08-16，dev 批次提前归档）**：按用户要求，仍处 0.10.14-dev 的已解决项（rf-276~rf-281）一并迁入本文件新增 v0.10.14 章节；原 review-findings.md 已解决区清空。后续新增已解决项先登记 review-findings.md，待 v0.10.14 发布后按惯例归档。
- **四次合并（2026-08-17，dev 批次提前归档）**：按用户要求，续归 v0.10.14-dev 已解决项（rf-282~rf-287）——死参数/遗留文件清理（rf-282/283/284，源自 rf-272 衍生独立项）、smoke-web 竞态修复（rf-285）、bench 菜单键集缺陷（rf-286）、测试标记体系漂移（rf-287）。原 review-findings.md 已解决区再次清空；待办项（含 rf-113/114 交互图表技术债）继续保留在原文件。
- **五次合并（2026-08-29，发布归档）**：发布 v0.10.15 时，将 v0.10.15-dev 已解决项（rf-288~rf-294）整体迁入本文件新增 v0.10.15 章节——all_no_unit live 卷入修复（rf-288）、事实校验主体归因三处修复（rf-291/292/293，描述性尾名匹配 rf-289）、dedup 跨源误合并率修复（rf-290）与收盘术语同义归一（rf-294）。原 review-findings.md 已解决区清空，仅保留待办区与归档引用。
- 已关闭项（rf-117/118/120/121 决策已定，不做）与未修复待办项不在此列。
