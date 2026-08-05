# 自我审查问题记录归档 — v0.10.x

> 归档时间：2026-08-05
> 原始文件：`docs-stm/managements/review-findings.md`
> 涵盖版本：v0.10.1 ~ v0.10.6（2026-08-04 ~ 2026-08-05；v0.10.0 无独立 changelog 段，已发布记录自 v0.10.1 起）
> 归档内容：本迭代已修复的 rf 记录（rf-204 ~ rf-232）摘要行 + 修复方案 + 变更记录

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

## 归档说明

- 本归档涵盖 v0.10.1 ~ v0.10.6 已发布版本的自审修复记录（rf-204~rf-232）；当前待处理项（rf-75~89 文件过长、rf-113/114 交互图表技术债、rf-217 场外渠道限制、rf-229 语义命名表增强）保留在 `docs-stm/managements/review-findings.md`，不随版本归档。
- 已关闭项（rf-117/118/120/121 决策已定，不做）与未修复待办项不在此列。
