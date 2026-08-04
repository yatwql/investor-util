# 个人投资分析报告生成小助手 - 自我审查问题记录
> 文档版本：0.10.4-dev
> **编号源**：`rf-next = 226`（新增问题取此编号，完成后更新为 +1；已用最大 rf-225，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复 |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器 |

> 已关闭项（决策已定，archive 可查）：rf-117 A6 键盘可达性（不做 MVP）、rf-118 相关性矩阵 Heatmap（已用 HTML 表格渲染）、rf-120 S5 CSP（不做）、rf-121 报告体积（R21 接受自包含代价）

#### P2D — 调仓建议可行化层数据模型限制（待后续增强接入）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-217** | 调仓建议可行化层（审查发现）：1 前缀场外持有基金（LOF/开放式指数基金，如 `161725 招商中证白酒指数A`、`110022 易方达消费行业`）无法区分场内/场外持仓渠道，当前默认按场内基金处理（100 份取整 + 仅计佣金）；场外持有会漏计赎回费且份额取整过粗 | 需持仓明细携带场内/场外渠道上下文（属后续增强，不在当前契约内）；当前默认场内口径已在模块 docstring 与 changelog 文档化，费用为估算性质 |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）



| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 653 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 537 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 534 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 472 | 未超限（<500，维持现状） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 477 | 未超限（<500，维持现状） | Excel 编排器 |

#### P2B — 文档与实现不符（低优先级，增量改进）

| # | 问题 | 修复方向 |
|---|------|----------|

### P3 — 测试覆盖缺口（建议补齐）

| # | 位置 | 问题 |
|---|------|------|

---

## 已修复（摘要）

> 已归档历史修复记录见 [归档档案](#归档档案)。以下仅保留近期未归档条目。

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| **rf-223** | 批量暗号替换脚本（/tmp/clean_ciphers.py，本次会话一次性工具）`[ \t]{2,}` 折叠整行空白，破坏 9 个 Python 文件前导缩进（report 4 个 + test 5 个，IndentationError） | 按 HEAD 逐行映射恢复前导空白（行数 1:1 已验），全仓 git diff 范围内 `compile()` 通过 | changelog v0.10.3 |
| **rf-224** | 批量暗号替换脚本误处理：截断需求 ID `R-LLM-DB-QA-CONCENTRATION-03/04`（test_debate_prompts.py）、删除 `I2.` 段头序号（_config_defaults.py / how-to-config.md）、产生空头 `── ──` | 需求 ID 恢复完整并纳入 DASHTASK 豁免（requirements.md 表格定义的合法需求交叉引用，非任务编号）；交易纪律段头改纯语义「交易纪律配置」（`I2` 属配置索引暗号，两处同步） | changelog v0.10.3 |
| **rf-225** | 语义清理将模块级 `_C19_KEYS` 重命名为 `__KEYS`，双下划线在类内触发 Python 名称混淆（NameError：`test_correlation.py` 2 例 + `test_pipeline_factor_exposure.py` 1 例） | 改语义名 `_CONTRACT_KEYS`（单下划线 + 语义名，符合命名纪律），3 处引用同步；P0 门禁 dev-verify 复跑 1649 全过 | changelog v0.10.3 |
| **rf-220** | check-code-traces 缺迭代轮次检测 + 测试层残留轮次引用（`test_html_writer.py`「对应轮13 验收标准」等） | 测试层轮次注释改语义描述；check-code-traces.py 新增 ROUND 模式（`第 N 轮`/`N 轮`/`轮N`）+ 计数/运行时豁免（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/轮换、第 N 轮循环），退出码归入任务编号类（exit 2） | changelog v0.10.3 |
| **rf-221** | 迭代轮次检测缺口：check-doc-traces 完全无「第 N 轮/经 N 轮/N 轮/轮 N」检测；check-code-traces ROUND 只匹配「轮N」紧贴形式，漏检空格分隔「轮 12」「轮 7」等旧注释（4 处） | check-doc-traces 镜像 ROUND 模式（含空格「轮 N」）+ 计数/运行时豁免（共 N 轮、计划分 N 轮、N 轮每轮、轮询、轮动/轮换/轮番/轮涨/轮跌、第 N 轮循环），ROUND 不进 trace-exempt 文档扫描（changelog/plan/review-findings/plan 目录豁免）；check-code-traces ROUND 放宽为「轮\s*N」；清理 4 处空格分隔旧注释（industry_beta/excel_fund_deep_analysis/orchestrator/test_return_attribution）；新增 TestDocRoundDetection 4 例 | changelog v0.10.3 |
| **rf-222** | 契约改名叙述漏检：注释残留「原 factor_exposure 契约迁移为主键」等历史契约改名痕迹（7 处 src 注释 + 1 处 scenario 测试），两检查脚本只覆盖「原+固定名词 / 迁移自 / 迁移到新X」，漏掉「原+标识符+迁移为/为主键」形状 | 7 处 src 注释 + 1 处 scenario 测试改纯语义描述（style_factor_data 主键）；check-code-traces/check-doc-traces 同步补 HIGH 模式「原 X…迁移/改称/并入」（ASCII 标识符 + 契约/dict/数据契约 限定词，中文后续「原始数据迁移」不误伤）；新增代码/文档各 1 例回归测试 | changelog v0.10.3 |
| **rf-219** | 测试层残留章节数字引用 + check-code-traces 缺章节编号检测（测试 fixture 硬编码陈旧章节序号、docstring/注释残留「N 章」暗号等） | 测试层全部改为纯语义章节描述 + 陈旧 fixture 编号对齐当前 registry；check-code-traces.py 镜像 CHAPTER 模式 + 计数豁免（共 N 章等不误报），退出码归入 exit 2 | changelog v0.10.3 |
| **rf-218** | 源码/注释残留章节数字引用（`报告第 N 页`、`N 章「X」`），部分因合并重排已陈旧 | 全部改为纯语义章节描述，不依赖章节数字；合并章模块 docstring 改用当前章节语义名 | changelog v0.10.3 |
| **rf-207** | 数值校验策略 1 全局最近邻忽略句中明确品种代码：句中已写明确主体（「建设银行收益率 3.2%」）、数值接近无关品种容差内（与 240012 差 0.96≤1.0）即误判通过，漏检与主体 601939 的 1.33 超差 | `_evaluate_percent_value` 将主体解析提前到策略 1 前：句中有明确持仓主体（代码/名称）时按该主体实际收益率校验（容差内通过、超差报错），无主体或主体无收益率数据时回退全局最近邻 | changelog v0.10.1 |
| **rf-208** | 门禁只扫注释且 CODE 仅 `(?:rf\|plan\|R)-\d+`，抓不住系列代号（`b_series`/`G系列`/`F4`/`B6`），也不扫代码标识符 | check-code-traces 注释 CODE 补 `[A-Za-z]系列`/单字母`_series`；新增标识符扫描维度（`.py` ast、`.js` 正则）捕获大写裸字母+数字/单字母`_series`/`系列`/嵌入 `rf/plan`+数字；IDENT 类等同 CODE 退出码 2；check-doc-traces 同步补系列模式 | changelog v0.10.1 |
| **rf-205** | 事实校验把非收益率百分比（胜率/评分权重/相对基准跑输跑赢）误修正为持仓收益率，且亏损品种修正丢失负号（518880 -8.86% 输出 +8.9%） | `_evaluate_percent_value` 补胜率/权重/相对基准近邻语境跳过；修正输出改带符号收益率保留盈亏方向 | changelog v0.10.1 |
| **rf-206** | 版本一致性回归测试硬编码正斜杠路径，Windows 下 `relative_to` 返回反斜杠导致永不匹配、dev-verify 必失败 | 构造 CHECKS 类型字典时把 `relative_to` 结果分隔符规范化为 `/` | changelog v0.10.1 |
| **rf-214** | 调仓建议代码审查 MEDIUM：00 前缀债券型基金（名称含"债券"无细分词，如 `000311 景顺长城景颐双利债券A`）误判为 A 股 → 100 份取整 + 印花税，漏计赎回费 | `_OTC_FUND_NAME_KW` 补「债券/指数/股票」关键词（仅 00 前缀分支生效，A 股股票名不含这些词，无副作用），回归测试断言整数份 + 赎回费 | changelog 轮6 |
| **rf-215** | 调仓建议代码审查 LOW：`estimate_fee` 的 `operation` 参数未被使用，未来买入调用会静默按卖出口径计费 | 增加卖出方向守卫（未知操作抛 ValueError），杜绝静默误计费，参数保留供后续买卖方向区分 | changelog 轮6 |
| **rf-216** | 调仓建议代码审查 LOW：持仓名称缺失（None）时 `is_otc_fund_by_name` 抛 TypeError 中断整条清单 | `_round_to_lot`/`estimate_fee` 名称归一化为空串后参与判定，防御性降级（00 前缀按 A 股口径） | changelog 轮6 |
| **rf-213** | 交易纪律代码审查（轮5）LOW：回撤线配置为正值（10）时规则文本显示「回撤线 10%」有歧义 | 统一按负值展示「回撤线 -10%」（`-abs(drawdown_pct)` 后格式化） | changelog 轮5 |
| **rf-212** | 交易纪律代码审查（轮5）LOW：`action_advisor.py` 注释含任务代号「轮6/轮7」 | 改为语义描述「调仓建议（可行化清单）与收益归因（贡献占比）为后续增强能力」 | changelog 轮5 |
| **rf-211** | 交易纪律代码审查（轮5）MEDIUM：`discipline` 配置校验缺语义约束，止损线误配为正数时与止盈线冲突 | 补充符号校验：止盈线须正数、止损线须负数（符号约束自动保证止盈线 > 止损线，杜绝同品种同时触发） | changelog 轮5 |
| **rf-210** | 交易纪律代码审查（轮5）MEDIUM：组合回撤纪律依赖 `portfolio_peak_mv`，当前管线未注入（历史峰值数据待 plan-20 历史增强接入） | 回撤纪律已实现并测试；管线注入属历史增强范围，changelog 标注「回撤数据接线说明」，组合级信号不参与单品静默期（与再平衡 category/summary 约定一致）已文档化 | changelog 轮5 |
| **rf-209** | 交易纪律代码审查（轮5）HIGH：both 报告路径组装 `action_data` 时 `profit_rate` 传小数值，纪律引擎按百分数阈值比较 → 止盈/止损纪律永不触发 | both 路径将 `profit_rate` 换算为百分数（`×100`，同 full 路径 orchestrator 口径），并补回归测试断言 | changelog 轮5 |
| **rf-204** | 版本一致性检查全文 contains 会漏检头部版本行未同步（正文偶然版本号掩盖） | 管理文档改用「文档版本：」头部行精确匹配；`--fix` 自动修正头部版本行 | changelog v0.10.1 |


---

## 归档

### 归档档案

- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
