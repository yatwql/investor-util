# 自我审查问题记录归档 — v0.10.x

> 归档时间：2026-08-06；2026-08-16 二次合并 review-findings.md 已解决项（rf-248 ~ rf-275，v0.10.10 ~ v0.10.13 已发布版本）；2026-08-17 四次合并（rf-282 ~ rf-287，v0.10.14-dev）；2026-08-29 发布 v0.10.15 合并（rf-288 ~ rf-294）；2026-09-10 发布 v0.10.16 合并（rf-295 ~ rf-304）；2026-09-10 发布 v0.10.17 合并（rf-297、rf-303、rf-305 ~ rf-321）
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.10.1 ~ v0.10.13（2026-08-04 ~ 2026-08-14，已发布；v0.10.0 无独立 changelog 段，已发布记录自 v0.10.1 起）+ v0.10.14-dev 批次（2026-08-16 ~ 2026-08-17，未发布、按用户要求提前归档）+ v0.10.15 批次（2026-08-17 ~ 2026-08-29，已发布）+ v0.10.16 批次（2026-08-29 ~ 2026-09-10，已发布）+ v0.10.17 批次（2026-09-10，已发布）
> 归档内容：本迭代已修复的 rf 记录（rf-204 ~ rf-321）摘要行 + 修复方案 + 变更记录；v0.10.14-dev 已解决项（rf-276 ~ rf-287）按用户要求提前归档于 v0.10.14 章节，v0.10.15 已解决项（rf-288 ~ rf-294）随发布归档于 v0.10.15 章节，v0.10.16 已解决项（rf-295 ~ rf-304）随发布归档于 v0.10.16 章节，v0.10.17 已解决项（rf-297、rf-303、rf-305 ~ rf-321）随发布归档于 v0.10.17 章节，未完成待办项保留在原文件 review-findings.md

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

### v0.10.16（2026-09-10）

> 发布 v0.10.16 时整体归档已解决项（rf-295 ~ rf-304；rf-297 与 rf-303 仍在待办区）。变更详情见 changelog.md [0.10.16] 对应条目。

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-295 | 持仓体检「数据质量」维度降级事件恒空（`_submit_llm_future` 未传 `degradation_events`）——报告自身数据降级披露口径自相矛盾 | `report/_llm_news.py` 在提交线程池前于主线程取一次 `DegradationTracker.get_log()` 快照随参传入 `generate_all_llm`（该参数早已存在，仅调用点漏传；主线程读取避免与工作线程并发写入交错）；回归测试 `TestSubmitLlmFutureDegradationEvents` 3 项（快照非空透传/空降级仍传空列表/不影响 metrics 等既有传参） | `changelog.md` [0.10.16] |
| rf-296 | 品种代码笔误无自动纠正通道（2026-09-09 实盘穿透深度复现 561910→161910 易位一位幻觉；唯一近邻 + 组合权重 10.2% 吻合仍仅告警） | `_corrections.py` 新增 `detect_code_corrections`/`apply_code_corrections`（辅助 `_utils._build_stock_weight_map`/`_edit_distance_le_one`）：错码非 持仓/穿透/指数/建议语境 有效集、**唯一**持仓近邻（编辑距离≤1）、后方权重声称与候选真实组合权重容差内吻合 三条件全满足才自动纠正，纳入「已修正明细」并从 ⚠ 剔除；回归测试 `TestCodeTypoAutoCorrection` 8 项（实盘纠正 + 权重不吻合/多近邻歧义/建议语境/穿透代码/指数 边界不误改） | `changelog.md` [0.10.16] |
| rf-298 | `core/signal_ledger.fold_signals` 对**显式传入**的非 dict 元素（`None`/字符串/数字）会抛异常，而 `load_signals` 对同一文件内容是容错的——同一份数据走「文件读入」与「直接传集合」两条路径行为不一致（plan-34 实现期自审发现，写边缘用例时暴露） | `fold_signals` 入口增加 `items = [s for s in raw if isinstance(s, dict)]` 过滤（与 `load_signals` 的容错口径对齐）；回归测试 `test_signal_ledger_edge.py::TestDegenerateRecords::test_fold_ignores_non_dict_entries` | `changelog.md` [0.10.16] |
| rf-299 | `fetcher/chain.py` 熔断跳过分支把**原始 provider id** 写进链路诊断（`p1(已被熔断跳过)`），而同一循环内其余分支写的是展示名（`腾讯财经(连接超时)`）——同一条降级事件因失败类型不同而时好时坏地不可读，恰好违背本项「失败原因可读」的目标（写批量 3 用例时被断言揭出） | 把 `entry = provider_fn_map.get(provider_name)` 提到熔断检查之前，熔断/未注册分支统一改用 `label`（有注册项取展示名，否则回落原始 id）；回归测试 `test_chain_diagnostics.py::TestFetchWithFallbackDiagnostics::test_circuit_broken_provider_recorded` 断言输出为 `腾讯财经(已被熔断跳过)` | `changelog.md` [0.10.16] |
| rf-300 | `cli._handle_doctor` 用裸字面量 `1 if bad_count else 0` 作退出码，未走项目既有的 `_EXIT_SUCCESS/_EXIT_PARTIAL/_EXIT_SEVERE` 常量——脚本无法区分「命令本身失败」（SEVERE=2）与「命令跑完但检查未通过」（PARTIAL=1），且魔法数字散落 | 改为 `return _EXIT_PARTIAL if bad_count else _EXIT_SUCCESS`，docstring 补记该语义区分；测试相应改为断言 `_EXIT_PARTIAL` | `changelog.md` [0.10.16] |
| rf-301 | plan-35 A1/A2 改动遗留 4 处违反代码痕迹纪律的注释/文案：`providers/_utils.py` 与 `providers/akshare_extras.py` 注释叙述历史实现（「原实现的 `float(s)`…」「原实现只拦 NaN」），`test_numeric_guard_regression.py` 出现魔法编号 `F9` 及同类历史叙述——`check-code-traces --ci` 报 HIGH×2 + MAGIC×1，阻断 P0 门禁 | 四处一并改写为陈述当前不变量的语义描述（不提历史实现、不用接口字段名的缩写代号），`check-code-traces --ci` 恢复 [OK] | `changelog.md` [0.10.16] |
| rf-302 | plan-35 文档阶段在 `technical.md` §4.17 正文写入两处任务编号括注（「（自审记录 rf-299）」「（自审记录 rf-300）」）——技术设计文档属实现层文档，不得出现任务代号引用，`check-doc-traces --ci` 报 CODE×2 阻断 P0 门禁 | 两处括注改写为对应的语义描述（展示名一致性的目的、退出码 `PARTIAL` 与 `SEVERE` 的语义区分），任务编号引用仅保留在 `changelog.md` / `plan.md` / `review-findings.md` 三份记账文档中，`check-doc-traces --ci` 恢复 [OK] | `changelog.md` [0.10.16] |
| rf-304 | 接入 `deepseek-flash` 时在代码注释与测试 docstring 中书写厂商标识 `DeepSeek-V4.1-Flash` / `V4.1 Pro`，其「大写字母+数字」形态被 `check-code-traces --ci` 判为魔法编号（MAGIC×8：`core/constants.py`、`llm/api_base.py`、`test_llm_utils.py`×2、`test_llm_api.py`）；同批在 `changelog.md` 写入指向技术设计文档某章的编号式引用，被 `check-doc-traces --ci` 判为 CHAPTER×1——两项同时阻断 P0 门禁 | 代码侧 8 处改写为语义描述「新一代 Flash / 新一代 Pro」（正式模型名 `deepseek-flash` 本身已是语义名，不承载版本代号）；`changelog.md` 改称「定价快照表」（语义章节名，不带章号）。两个 checker 均恢复 [OK] | `changelog.md` [0.10.16] |

### v0.10.17（2026-09-10）

> 发布 v0.10.17 时整体归档已解决项（rf-297、rf-303、rf-305 ~ rf-321）。变更详情见 changelog.md [0.10.17] 对应条目。

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-297 | 预检侧与写侧各自拼接同一模块的缓存指纹，已双向漂移（预检侧计入组合风险信号而写侧未计入；写侧计入辩论增强后缀而预检侧未计入）→ 三个模块的读写键永不相等，预检恒不命中、每次报告全量派发 LLM | 抽取 `llm/module_fingerprint.py` 作为模块缓存指纹的**唯一事实来源**，写侧与预检侧改为调用同一构建函数（后缀判定收敛进函数内部），`history_data` 两侧一致计入；该同源要求同时写入技术设计文档的架构设计约束表。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-303 | 接入 `deepseek-flash` 正式名时核对 `MODEL_PRICING` 的 DeepSeek 条目，发现两处既有口径未经官方确认：① `deepseek-reasoner` 无定价条目——`estimate_cost()` 对其返回 `"-"`，费用页签显示为空；② `deepseek-chat` 按 V3（1.50/4.50/0.05）单独定价，而 DeepSeek 文档称二者分别是 V4-Flash 的「非思考 / 思考模式」别名（若属实应随 flash 系列走降价后的 1.00/4.00/0.02） | 官方资料核实后**原假设修正**：两个模型名**不是**「端点仍接受但未定价」，而是已于 2026-07-24 停用，故条目口径按其真实语义（flash 系列别名）而非 V3 定价。`deepseek-chat` 单价由 1.50/4.50/0.05（高峰 3.00/9.00/0.10）改为与 flash 系列一致的 1.00/4.00/0.02（高峰 2.00/8.00/0.04），并新增 `deepseek-reasoner` 同价条目；**条目保留而非删除**——报告与性能页签在渲染时用本表估算历史记录（模型名 + token 数）的费用，删条目会让停用前产生的调用一律显示 `"-"`。按条目标注的前置要求**先补「模型名 → 单价」断言测试**再改：新增 3 例（两个别名闲时/高峰两段与 `deepseek-flash` 同价且非 `"-"`、缓存命中价 0.02 不回落为 input 价、两条目均在 `PRICING_MERGED`），锁定后即便将来误改单价也会立刻转红。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-305 | LLM 模块缓存指纹**覆盖不足（欠敏感）**——与「读写不同源」属不同类别：`competitive_context`（`_build_competitive_context_block` 生成的业绩基准与竞品对比块）与 `metrics`（量化指标）**参与提示词构造，却不进入任何模块指纹**。当持仓未变、但基准指数或竞品行情变动使对比块内容变化时，指纹不变 → 预检命中旧键 → 运行期直接复用旧内容，**提示词与缓存键脱钩**。两侧一致缺失（写侧与预检侧同缺 `competitive_context`/`metrics`），因此不产生恒 miss，而是**恒命中过期内容**，用户感知弱。辩论三键（白脸/黑脸/综合）的基础指纹此前经本地自拼 `build_llm_fingerprint` 构造，同样不含二者 | 先按 rf 要求**量化后决定纳入**：全部对市场敏感的模块本已按 `total_mv`/`total_profit`/`total_today_profit` 换键，而对比块正是由这些已被键控的量派生的 ⇒ 边际额外失效≈0；真正新增的失效维度恰是本缺陷的目标（指数动而持仓未动、`comparison_indices` 配置变更、指标重算），且 TTL（expert_review 2h / global_macro 24h）封顶额外成本。实现上确立两条结构性保证：**① 覆盖以「提示词是否真的含该段」为准**（`competitive_context`/`metrics` 只进提示词确实包含它们的模块——`health_check`/`penetration_deep` 的提示词不含这两段，刻意不并入以免纯成本失效）；**② 一次渲染、两侧共享同一实例**（`generate_all_llm()` 渲染一次后同时交给预检侧与写侧；哈希「已渲染文本」而非其输入 dict，使「提示词变 ⇒ 键必变」由构造保证，将来改渲染函数不会悄悄脱钩）。辩论三键由本地自拼收敛为 `debate_procon_fingerprint()`，口径同以辩论提示词实际段落为准（含对比块/指标，**不含** `history_data`/`pipeline_data` 与教训/信号/决策头后缀——辩论提示词无这些段，并入会让三次昂贵调用每份报告必 miss）。新增覆盖性断言测试（「进了提示词必须进键」+「未进提示词的模块不得被并入」+ 预检侧同源 + 辩论口径），并新增「同一实例」断言（`assertIs`）。已验证两处变异转红（摘掉 `expert_review` 的对比块/指标 → 3 例失败；预检侧传空块 → 实例断言失败）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-306 | 命令行实验开关 `--experiment` 对早期返回命令（`doctor` / `check-sources`）**完全无效**：这些命令在 `init_config()` 之前分派（配置损坏时仍须可用，属有意设计），而应用命令行开关的调用在其后才执行，故参数被静默忽略——`doctor` 会报告「实验开关关闭」而用户明明指定了该开关，据此判断实验功能状态即得相反答案 | 早返回分支内改为「先读 features.json 覆写、再叠加命令行增量」（与配置初始化顺序一致，避免被覆写值回冲），抽出 `_prepare_early_exit_experiments()` 承载该顺序；新增 4 例回归测试（含「不传开关保持默认」对照组与「覆写先于命令行」顺序守卫），已验证去掉修复后 3 例转红。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-307 | **`python -m src.python.cli` 的退出码恒为 0**：`cli/__main__.py` 只调 `main()` 而丢弃其返回值（`cli.py` 自身作为脚本直跑时才 `sys.exit(main())`，两条入口行为不一致）。退出码是本项目命令对外契约的一部分——`doctor` 用 1/2 表达「部分失败/严重」、`cassettes --verify` 用 2 表达「解析失败」、`report`/`cache`/`whatif` 亦然——而 `scripts/cli.sh`、`scripts/cli.ps1`、cron、CI 全部经 `python -m src.python.cli` 调用，故失败对外一律表现为成功，脚本化调用无法据此判断成败（在 plan-37 自测 `cassettes --verify` 时被实证：损坏 cassette 已打印 `[ERR]`，进程仍返回 0） | 抽出 `run_cli()`（`cli.py`）承载「执行 `main()` → 退出码/异常 → `SystemExit` + 应用边界日志」的全部逻辑，`cli.py` 直跑分支与 `__main__.py` 共用，两条入口行为归一；新增 6 例回归测试（`run_cli` 的码传递/KBI→130/异常→2/边界日志 + `runpy` 以 `__main__` 身份执行真实入口断言退出码为 7），已验证还原旧 `__main__.py` 后入口用例转红（实测退出码 0 ≠ 7）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-308 | `health_check` 缓存指纹**覆盖不足（欠敏感）**——与 rf-305 同类：`degradation_events`（降级事件日志）经 `_build_data_quality_detail_block()` 渲染成【数据质量详细状态】段**进入 `health_check` 提示词**，却不进入其指纹。后果比 rf-305 更重：不是复用一段偏旧的分析，而是**报告陈述与此刻事实相反的数据健康结论**——源故障期间生成并缓存「连接失败: xxx(N次)」，源恢复后重出报告、持仓未变故键未变 → 预检命中旧键 → 报告仍称该源连接失败，不报错、用户无从察觉 | 先核查挂起理由的成本前提（三条均不成立：事件集是**本进程内**的降级日志、该块已是聚合结果、本模块指纹本就含 `total_today_profit` —— 边际额外失效接近零），再按 rf-305 同法纳入：`generate_all_llm()` 渲染**一次**，同一实例同时交给预检侧（`ModuleFingerprintInputs.data_quality_text`）与写侧（`generate_health_check(data_quality_text=...)`），指纹哈希**已渲染文本**；提示词构建函数不再接收原始事件（改收已渲染文本）。该块**只进 `health_check`** 指纹（其余模块提示词不含该段）。新增 3 组覆盖性断言 + 「一次渲染 / 同一实例」用例，已验证两处变异转红。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-309 | `check-sources` 结果行的**符号与统计口径不一致**：统计分支判 `"timeout" in message or "超时" in message` 两种措辞，符号分支只判 `"timeout"`。而本文件自身产生的预算超时行消息是 `超时（预算 15s）`（无 "timeout" 子串），于是该行**被计入 `warn_count` 却渲染成 `_ERR`（红色错误）**——同一行自相矛盾（汇总行说「⚠️ 1」、行首说「❌」）——计数是对的（退出码仍为告警级 1），**渲染是错的**，用户据此以为源故障要排查，而实际只是本次探测超预算。在 plan-38 改造该分支（新增凭据跳过态）时发现 | 把措辞判定提为单一变量 `timed_out = "timeout" in msg.lower() or "超时" in msg`，统计与符号两处共用，口径归一；新增 2 例回归测试（预算超时行渲染为 `_WARN` 且汇总计入告警、退出码 1；真实失败仍渲染 `_ERR` 且退出码 2，防修复过度放宽），已验证把符号分支退回旧判据后首例转红（实测行首为 ❌）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-310 | 报告管线实验挂载点的**守护语义被复制四份**：决策结算/登记、LLM 决策注入、模块质量横幅、确定性信号沉淀四个挂载点各自内联 `try/except Exception` + `reporter.warn` + `logger.exception`，告警文案与日志标签逐处重写（改一处必漏三处，与缓存指纹「读写两份拼接」同一病根）；且 `report/_report_generation.py` 因这四个内联块**越过 800 行硬上限**（实测 817 行）；挂载点本身**零直接测试覆盖**——内联在管线函数中只能靠驱动整条报告管线覆盖，开关判定与数据注入此前无任何直接断言 | 抽出 `report/_experimental_seams.py`：四个挂载点收敛为四个函数，共用一份 `_guarded()` 守护（异常 → 一条告警 + 一条异常日志 + 兜底值，绝不外抛），被调子模块在挂载点内**按需导入**（开关关闭时不付导入成本，导入期异常落入同一守护）；`_report_generation.py` 降至 736 行回到上限内，且只按序调用挂载点。**挂载点工序顺序契约**（结算先于 LLM 拉取 / 质量横幅晚于决策登记 / 信号沉淀晚于 LLM 生成）与其理由写入模块 docstring，该机制同时登记为架构设计约束表的挂载点集中约束行。新增 `src/test/unit/report/test_experimental_seams.py` 16 例（开关关 → 无副作用 / 开关开 → 按契约向 `pipeline_data` 注入 / 下游异常 → 只告警不外抛且返回输入原对象 / 缺下游符号 → 安全降级 / 被调子模块确为按需导入），含 AST 断言「四个挂载点的调用顺序固定」与「除进度上报器外无 report 子模块被提前导入」。已验证四个方向变异各自转红（去掉开关判定 / 收窄守护范围 / 改横幅兜底值 / 交换调用顺序）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-311 | 体检（`doctor`）的目录写入探针**落到用户真实目录**：探针以 `output_dir`、`data/cache/`、`logs/` 为目标写入再删除 `.doctor_write_probe` 以验证「目录存在且可写」，但目标列表在函数内直接取自配置，**无任何可替换的注入点**——测试运行体检时探针作用于用户的真实 `reports/`/`data/cache/`/`logs/`（实测真实报告目录出现 `.doctor_write_probe` 残留），违反「测试不得修改用户数据」的敏感路径隔离纪律 | 把探针目标提为**单一可替换来源** `_probe_targets()`（返回值即探针实际作用的目录列表），`conftest.py` 增加 session 级 fixture 将 `_probe_targets` 重定向到临时目录。已验证端到端生效：体检运行中探针解析到 `pytest` 临时目录，真实 `reports/`/`data/cache/`/`logs/` 无 `.doctor_write_probe` 残留。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-312 | **代码注释与实现漂移**三处：① `config/features.py` 的注册表注释把 CLI 侧描述为可用 `--experiment` / `--no-experiment` 双向覆写，而 **`--no-experiment` 参数并不存在**（`cli.py` 只有只开不关的 `--experiment <名\|all>`）——读者据此寻找一个不存在的关闭开关；② `log_experimental_features()` 的 docstring 称「在 main() 中调用（TUI/CLI 均在 `init_config()` 之后调用此函数）」，而实际唯一调用点是报告入口 `report/orchestrator.generate_report`（TUI/CLI/Web 三入口均经该点统一触发）；③ `tui/tui.py` 的 `default_menu_key` 合法键注释列表漏掉 `D`（系统自检，受 `doctor_check` 开关门控），据此配置 `default_menu_key` 的用户无法判断 `D` 是否可用 | 三处按代码现状改写：注册表注释改为「CLI 侧经 `--experiment <名\|all>` 增量启用（仅当前进程、不写盘，只开不关——关闭仍走配置/面板）」；`log_experimental_features()` docstring 改为点名唯一调用点并说明三入口经报告入口统一提示（「本次报告受哪些实验功能影响」正是需要看到该信息的时刻）；`tui.py` 键列表补 `D` 并注明其受开关门控、关闭时该项被裁剪后按键查找会回落到首项。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-313 | 管理文档与用户文档相对代码现状的**成片漂移**（实验性功能三批实施后未同步）：实验开关计数写作 33 而实际 35；TUI 试验功能面板编号写作「6-14」而实际到 6-16（`datasource_adapter`/`datasource_credential_ready` 未上文档）；`testplan.md` 与 `developer-guide.md` 的 unit 子标记清单均含**并不存在的** `unit_config_edge` 且漏 `unit_web`，`developer-guide.md` 的模式表还把 `dev-verify`/`verify` 的标记表达式漏写成不含 `unit_web`；十余处 shell 示例使用裸 `python`/`pytest`（违反项目虚拟环境解释器纪律）；`doctor`/`view-logs`/`cassettes` 三个 CLI 子命令未进 developer-guide 的脚本/子命令一览；架构设计约束表停在旧编号，近 72 小时落地的三条机制（报告管线实验挂载点集中、实验开关注册表唯一事实来源、凭据值不落日志与产物）**无对应约束行**，`CLAUDE.md` 的约束条数说明与之同步失准 | 逐项对照代码核实后更新：`technical.md`（实验开关计数与注册表来源、`_FEATURE_FLAGS_DEFAULT` 计数、功能语义命名表补 19 行、**新增三条约束行**并同步放开双检查脚本的约束代号匹配范围与 `CLAUDE.md` 的条数说明）、`requirements.md`、`testplan.md` 与 `developer-guide.md`（unit 子标记清单按 `conftest.py` 实况重列、模式表达式与脚本 `MODES` 逐字对齐、补齐虚拟环境解释器、新增非有限数值测试要求行、跨类标记补数据质量/回放/联网三类、补 `doctor`/`view-logs`/`cassettes` 行与两节子命令说明）、`folders.md`（新增实验挂载点条目 + 统计快照）、`test-coverage.md`（模式/子标记/功能域计数按实时收集结果刷新）、用户文档五篇（开关计数与面板编号、`features.json` 键表、实验功能行、快速开始措辞）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-314 | **已停用模型名在代码与文档中被当成受支持模型**（2026-09-10 接入 `deepseek-flash` 时只补新名、未审旧名语义所致）：`llm/api_base.py` 的 `_THINKING_SUPPORTED_PREFIXES` / `_THINKING_EFFORT_MODEL_PREFIXES` 直接把 `deepseek-chat` 列为受支持模型而无任何说明，读者据名单会认为该名当前可用；`docs-stm/manuals/how-to-config-llm.md` 的模型单价表把 `deepseek-chat` 标为「DeepSeek V3（功能受限）」并只列 V3 单价，且**整表漏登**正式模型名 `deepseek-flash`——用户按表选型会配到一个已下线两个月、且从未是独立 V3 端点的名字；`llm-technical.md` 附录 B 单价表同样缺 `deepseek-reasoner` 行 | 经 DeepSeek 官方资料核实：`deepseek-chat` / `deepseek-reasoner` 只是 flash 系列**非思考 / 思考模式的兼容别名**（不是独立 V3 模型），已于 **2026-07-24 23:59（北京时间）停用**，端点不再接受。据此三处按同一口径改写：**保留**两份推理族/支持名单中的 `deepseek-chat`（存量配置与第三方兼容端点仍可能发出该名，命中名单才能照旧施加「显式禁用思考」安全网，删掉反而让这类请求落入默认思考模式占满 `max_tokens`），但补注释写明其为已停用别名与保留理由；用户手册单价表以 `deepseek-flash` 取代原先的 `deepseek-chat` 行，并新增一行合并说明两个已停用别名的语义、下线日期与「条目仅保留供历史计费」；`llm-technical.md` 附录 B 补 `deepseek-reasoner` 行、两条别名行标注为已停用别名、峰谷模型清单同步补该名。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-315 | `core/jsonl_store.py::append_jsonl_atomic` 存在**潜伏的 `UnboundLocalError` 与无法区分的成败**：`tempfile.mkstemp()` 与随后的写入/`os.replace()` 包在**同一个 `try`** 内，而 `except` 分支引用的 `tmp_path` 由 `mkstemp` 赋值——`mkstemp` 自身抛 `OSError` 时该名字尚未绑定，清理分支反而抛出 `UnboundLocalError` 掩盖真实错误；同时函数签名返回 `None`、失败只记日志不返回，调用方无从得知写盘是否成功（rf-316 的乐观返回即由此诱发） | `mkstemp` 拆为独立 `try` 并返回 `False`；写入/替换段保持原清理逻辑（失败时删除临时文件、记异常日志、返回 `False`）；函数签名由 `-> None` 改为 `-> bool`，docstring 增加 `Returns:` 说明「失败只记日志不抛出，但**成功/失败必须如实上报**」。新增 3 例回归测试（成功返回 `True`；替换失败返回 `False` 且原文件内容不变；创建临时文件失败返回 `False` 而非抛 `UnboundLocalError`），已验证还原旧实现后第三例转红。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-316 | `core/signal_ledger.py::append_signals` 在**落盘失败时仍返回去重后的 `fresh` 列表**——调用方据此统计「本次入账 N 条」并渲染绿色成功行，而账本零新增（磁盘满 / 无写权限时静默失效）。与 rf-315 同属「写失败被乐观吞掉」一类：确定性信号账本是报告结论的事实来源，账本与实际入账不一致会让「统计只算实时记录」的口径失真 | 落盘结果**向上传递**：`append_signals` 收下 `append_jsonl_atomic` 的布尔结果，失败时返回空列表（并在 docstring 写明「落盘失败同样返回空列表」），使调用方的计数与账本内容同源。新增 2 例回归测试（写盘失败时入账数为 0、`append_signal` 失败时返回 `None`）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-317 | **美股指数历史日线链路整链为死分支**（自数据源适配改造起潜伏）：`fetcher/chain.py::_call_history_provider` 只按 `chain_name` 分派「A 股指数 / 基金净值 / 股票行情」三类取数函数，`history_index_us` 落入 `else` 分支——该分支从不调用任何 provider，按无实现者处理并落到末尾「未知函数」告警。后果是 **`fetch_index_kline('gb_*')` 恒返回空**，用户看到的是「美股指数历史数据缺失」而非任何配置错误，且告警文案（「未知函数」）指向的是内部符号名，与真实原因（该链路未接函数）不符，排查方向被带偏 | `_call_history_provider` 补 `history_index_us` 分派（与 `history_index` 共用 `fetch_index_kline`），并在命中 provider 无该实现时给出可读原因；`fn_name` 映射表同步补齐（该表供「函数名未实现」告警定位用）。链路注释写明现实约束：实际取数通常由腾讯承担（新浪侧虽有 `fetch_index_kline` 实现，但其 `getKLineData` 端点对全部代码返回 404/空——归因校正见 rf-321），且腾讯 K 线接口对 `gb_*` 代码支持有限——**该链可能整链取空，空结果按正常降级记录、不视作配置错误**。新增 `test_call_history_provider_dispatches_us_index` 回归用例（断言确实调到腾讯 `fetch_index_kline`、不再产生「未知函数」告警），已验证还原分派前该用例转红。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-318 | `health_check` 提示词构建的「未提供数据质量详情」判据用 `is None`，而模块指纹侧同参判据是 `data_quality_text or ""`——**同一实例在两个消费点被判成不同状态**。传空串时：指纹侧把它折叠成「无」并入哈希，提示词侧却认为「已提供」而渲染出一个空的数据质量段。当前调用方（`generate_all_llm()` 一次渲染两侧共享）恰好只传非空串或 `None`，缺陷不显现，但该函数是公开入口、判据分叉属结构性隐患（rf-308 建立「一次渲染两侧共享」纪律时遗留的口径不一致） | 提示词侧判据改为 `not data_quality_text`，与指纹侧折叠口径一致；docstring 写明「未提供」含 `None` 与空串两种，并说明为何必须用 `not` 而非 `is None`。新增参数化回归用例（`None` 与 `""` 渲染出**逐字相同**的提示词），并新增「数据质量文本与指纹同源」断言（同一实例渲染结果与哈希输入一致）。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-319 | `report/_experimental_seams.py` 的模块 docstring **只说明了「按需导入」这一种导入方式**，未记录真正的分界契约——`core` 账本模块（`decision_ledger` / `signal_ledger`）是**顶层导入**（`is_active()` 开关判定本身要落在它们上，且二者只依赖 stdlib + 同层 core，不构成启动负担），而 report 子模块才是挂载点内按需导入。读者按 docstring 的唯一口径理解，会以为模块内出现任何 `src.python.*` 顶层导入都是违规，或反过来把新增的顶层导入当成无害 | docstring 改为显式区分**两类导入**并按「开关关闭时是否值得付出成本」给出判据；该分界由 `test_experimental_seams` 的接线守卫逐项锁定（顶层项目导入集合必须恰为两个 core 模块 + `report.progress` 接口），使文字描述与可执行断言同源。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-320 | 管理文档与用户文档相对代码现状的**第二批成片漂移**（plan-36~38 三条实验机制落地后未复核到的部分）：`doctor` 的自检分组在四处仍写作「五组 / 六组」（`technical.md` 概览表与 §4.17.3、`requirements.md` §3.6、`plan.md` 的 plan-35 完成态），实际已是七组（环境/配置/目录/功能开关/数据源适配/数据源凭据/数据源）；`technical.md` §5.1 称 `llm/` 包「共 34 个子模块」而实测 35（26 个顶层模块 + `fact_checker/` 子包 9 模块），且 `llm-technical.md` §2.1 模块表**漏登** `_hallucination_filter.py`；`developer-guide.md` 脚本一览写「支持 14 种 `--mode`」而 `scripts/test-runner.py::MODES` 实为 17 个键，模式对照表还把 `all_no_unit` 的等效表达式写成 `not unit`（实为 `not unit and not live`）并漏掉 `perf`/`security`/`live` 三个定向模式；`test-coverage.md` 的模式计数/单元子标记/功能域/跨类四张子表停在旧快照（`unit` 6274→6283、`all` 6583→6595、`unit_web` 213→215、`unit_core` 1126→1131、`unit_llm` 933→935、`llm` 跨类 736→738 等）；`folders.md` 目录树缺 `src/test/unit/report/test_experimental_seams.py` 条目、统计表六项数据过期。用户文档侧：`how-to-start.md` 指向**并不存在**的 `scripts-reference.md`（死链）、`how-to-config.md` 的 TUI 菜单键列表漏 `D`/`P`/`I`/`A`/`S`/`R`/`V`/`H`/`F`/`X` 等且未标注门控、`how-to-use-cli-mode.md` 把 `doctor --timeout` 描述成单次请求超时（实为**整轮网络检查**的耗时预算）、`faq.md` 的日志行号引用整体偏移、`datasource.md` / `datasource-reliability.md` / `requirements.md` R-HST-07 / `technical.md` 链路图仍称美股指数历史链路由新浪承担（新浪无指数 K 线实现） | 逐项对照代码核实后更新：`technical.md`（自检分组改七组并注明由 `GROUP_ORDER` 锁定、LLM 子模块计数 34→35 并计入 `_hallucination_filter.py`）、`llm-technical.md`（§2.1 模块表补 `_hallucination_filter.py` 行）、`requirements.md`（§3.6 分组枚举）、`plan.md`（plan-35 完成态的分组枚举，避免同一特性在计划表与设计文档给出相反的分组数）、`developer-guide.md`（`--mode` 计数 14→17、`all_no_unit` 表达式与 `MODES` 逐字对齐、模式对照表补 `perf`/`security`/`live` 三行）、`test-coverage.md`（四张子表按 `scripts/collect-test-coverage.py` 实时收集结果刷新）、`folders.md`（目录树补条目 + 统计表按实测刷新）；用户文档五篇按上列问题逐一改写。变更详情见 changelog.md [0.10.17] 对应条目 | `changelog.md` [0.10.17] |
| rf-321 | **美股指数历史链路的「谁真正发请求」归因写错**：`fetcher/chain.py` 的两处注释与五份文档（`datasource.md`、`datasource-reliability.md`、`faq.md`、`requirements.md` R-HST-07、`technical.md` 链路图）均称「新浪未实现 `fetch_index_kline`、探测到即跳过，实际发请求的只有腾讯」。实为 `providers/sina_kline.py` **实现了** `fetch_index_kline` 并经 `providers/sina.py` 重导出，`chain.py` 的 `getattr(mod, "fetch_index_kline", None)` 对新浪命中非 None，链上会**真实向新浪发出请求**；「跳过」的真实原因是该源 `getKLineData` 端点对所有代码返回 404/空（`sina_kline.py` 自述「保留此实现作为代码级备用」），不是缺实现。同批核对另发现两处数据源描述失真：`datasource.md` 基金持仓行主链路主机写成 `fundf10.eastmoney.com`（实为 `fund.eastmoney.com/{code}.html`，`fundf10` 是季报 API 回退）且漏登该回退链路；`datasource-reliability.md` §3.8 称指数 K 线 `datalen` 上限 3650（provider 侧实为 2000，3650 是取数层钳位） | 按代码现状改写归因并统一六处措辞：「新浪侧实现存在，但其 `getKLineData` 端点对全部代码返回 404/空，实际取数通常由腾讯承担」；基金持仓行改为「`fund.eastmoney.com/{code}.html`（HTML 解析）→ `fundf10.eastmoney.com` 季报 API（回溯 4 个季度）」；`datalen` 钳位按实况分列（股票 5~365、指数 5~2000，并注明取数层另按 5~3650 钳位后传入）。同时按实现校正三处口径：失败路径「重试（最多 3 次）」（链路逐 provider 单次调用、无请求级重试，3 是熔断阈值）、K 线字段「含涨跌幅/换手率」（实为开高低收 + 成交量）、`price_fund_otc` 回退条件「JSONP 解析失败」（实含超时/请求错误/无净值记录）。链路分派逻辑本身无需改动 | `changelog.md` [0.10.17] |

## 归档说明

- 本归档涵盖 v0.10.1 ~ v0.10.13 已发布版本的自审修复记录（rf-204~rf-275）、v0.10.14-dev 已解决项（rf-276~rf-287）与 v0.10.15 已解决项（rf-288~rf-294）；当前待处理项（rf-75~89 文件过长、rf-113/114 交互图表技术债、rf-257 Web 真机验收）保留在 `docs-stm/managements/review-findings.md`，不随版本归档。
- **二次合并（2026-08-16）**：`docs-stm/managements/review-findings.md`「已解决问题」区 v0.10.10 ~ v0.10.13 已发布版本修复项（rf-248~rf-275）整体迁入本文件对应版本章节。对应 plan.md P4 已完成项（plan-8/25/26/27/28）迁入 `archived_plan.0.10.x.md`、changelog [0.10.9]~[0.10.13] 迁入 `archived_changelog.0.10.x.md`。
- **三次合并（2026-08-16，dev 批次提前归档）**：按用户要求，仍处 0.10.14-dev 的已解决项（rf-276~rf-281）一并迁入本文件新增 v0.10.14 章节；原 review-findings.md 已解决区清空。后续新增已解决项先登记 review-findings.md，待 v0.10.14 发布后按惯例归档。
- **四次合并（2026-08-17，dev 批次提前归档）**：按用户要求，续归 v0.10.14-dev 已解决项（rf-282~rf-287）——死参数/遗留文件清理（rf-282/283/284，源自 rf-272 衍生独立项）、smoke-web 竞态修复（rf-285）、bench 菜单键集缺陷（rf-286）、测试标记体系漂移（rf-287）。原 review-findings.md 已解决区再次清空；待办项（含 rf-113/114 交互图表技术债）继续保留在原文件。
- **五次合并（2026-08-29，发布归档）**：发布 v0.10.15 时，将 v0.10.15-dev 已解决项（rf-288~rf-294）整体迁入本文件新增 v0.10.15 章节——all_no_unit live 卷入修复（rf-288）、事实校验主体归因三处修复（rf-291/292/293，描述性尾名匹配 rf-289）、dedup 跨源误合并率修复（rf-290）与收盘术语同义归一（rf-294）。原 review-findings.md 已解决区清空，仅保留待办区与归档引用。
- **六次合并（2026-09-10，发布归档）**：发布 v0.10.16 时，将 v0.10.16-dev 已解决项（rf-295 ~ rf-304）整体迁入本文件新增 v0.10.16 章节——持仓体检降级事件漏传修复（rf-295）、品种代码笔误自动纠正（rf-296）、信号账本 `fold_signals` 容错口径不一致（rf-298）、链路熔断分支展示名不一致（rf-299）、`doctor` 退出码常量（rf-300）、代码/文档痕迹纪律四处整改（rf-301/302/304）。原 review-findings.md 已解决区清空，仅保留待办区与归档引用。
- **七次合并（2026-09-10，发布归档）**：发布 v0.10.17 时，将 v0.10.17-dev 已解决项（rf-297、rf-303、rf-305 ~ rf-321）整体迁入本文件新增 v0.10.17 章节——模块缓存指纹读写同源与覆盖补齐（rf-297/rf-305/rf-308，含预检侧与写侧一次渲染共享）、报告管线实验挂载点抽取公共守护（rf-310）、体检目录写入探针测试隔离（rf-311）、已停用模型名定价与支持名单口径校正（rf-303/rf-314）、JSONL 原子写入与信号账本落盘结果如实上报（rf-315/rf-316）、美股指数历史链路分派补齐（rf-317）、数据质量详情「未提供」判据归一（rf-318）、命令行实验开关对早返回命令失效（rf-306）、__main__ 入口退出码恒 0（rf-307）、check-sources 超时行符号与统计口径不一致（rf-309）、代码注释与文档成片漂移校正（rf-312/rf-313/rf-319/rf-320）、数据源文档归因与实现口径校正（rf-321）。原 review-findings.md 已解决区清空，仅保留待办区与归档引用。
- 已关闭项（rf-117/118/120/121 决策已定，不做）与未修复待办项不在此列。
