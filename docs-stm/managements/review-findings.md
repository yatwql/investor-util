# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.18-dev
> **编号源**：`rf-next = 350`（新增问题取此编号，完成后更新为 +1；已用最大 rf-349，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

#### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）



| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 666 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-09-10 实测 666，较登记值 665 增长 1） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 542 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 544 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-09-10 实测 544，较登记值 536 增长 8，数值归一防线纳入后仍处 500-800 区间） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 521 | 维持现状（render 函数属同一渲染域，拆分收益有限；2026-09-10 实测 521，较登记值 526 下降 5） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 405 | 未超限（<500，维持现状；2026-09-10 实测 405，较登记值 401 增长 4） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 633 | 500-800 可选优化区间（2026-08-05 实测 635，较登记值 472 增长 163，跨过 500 线；2026-09-10 实测 633，较上次下降 2，关注后续增长） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 427 | 未超限（<500，维持现状；2026-08-05 实测 423，较登记值 477 下降，重构后缩减；2026-09-10 实测 427，较上次增长 4，决策登记载体纳入后仍处 500 线以下） | Excel 编排器 |

#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui.md` 验收标准），完成后回填 changelog、本表移至已修复。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

## 已解决问题

### 已解决待归档（v0.10.18-dev）

> 全局架构约束逐条自检（C 表 24 项）发现并修复的违规项，详情见 `changelog.md` [0.10.18-dev] 对应条目。约束语义见 `technical.md` §架构设计约束。
>
> 非架构约束违规：rf-336/rf-337 为同轮 lint 基线收敛过程中发现（工具链基线、测试完整性），rf-338 为实验功能三通道核查时发现的开关声明即死，rf-339 为用户在实际运行日志中发现的持仓报告期陈旧（四年前快照被当期采信），rf-340 为实验功能三通道核查时发现的配置面板边框错位，rf-341/rf-343/rf-344 为用户就「报告是否应体现已开实验功能」提问后顺藤核查发现的报告期标注缺口、清单兜底落点缺失与候选比较两列恒空（其中 rf-344 为 rf-341 修复过程中撞见的潜伏缺陷），rf-342 为同一轮核查发现的报告未自述生成条件，rf-345 为用户就同一话题追问「系统自检为何不能作为缺省功能」后复查发现的自述假阳性与归类口径问题。

| # | 问题（违反的约束用语义描述） | 处置 |
|---|------|------|
| **rf-322** | 原子写入分散：分析静默开关、熔断器包装、配置核心/特性开关、JSONL 存储、Provider 注册表、新闻去重、数据状态、历史快照各自实现「临时文件 + 替换」，失败回滚与残留清理口径不一 | 新增唯一原语 `core/atomic_write.py`，上述调用方全部经该原语写入 |
| **rf-323** | 持仓跟踪缓存读取绕过 `cache.py` 统一 API，自行拼路径读文件，TTL/命名口径与缓存管理层脱节 | 读取回归 `cache` API，按前缀匹配 TTL |
| **rf-324** | 基金风格分类自建估值取数路径，绕过 fetcher 网关直连 provider | 经 `fetcher/industry.py::fetch_valuation_fields` 取数 |
| **rf-325** | 报告编排器直连 provider 取行情，跳过 Provider Chain（熔断器不激活、fallback 断路） | 经 `fetch_with_fallback()` 走 Chain 路由 |
| **rf-326** | Excel 页签显示名在写入层硬编码中文字面量，与中央注册表两处清单各自漂移 | 显示名收敛到 `core/registry.py` 的 `_REPORT_SHEET_NAMES`，写入层经 `get_report_sheet_name()` 取用 |
| **rf-327** | 内联 `api_key` 与 provider 级凭据分离冲突时仅告警放行（凭据可能被误用），且校验收紧过程中 `model` 透传丢失 | 冲突收紧为硬拒绝并给出修正指引；补齐 `model` 透传 |
| **rf-328** | `pipeline_data` 键三方漂移：挂载点写入未登记键、台账有注册全仓无消费者的死键 | 键集、类型断言表、`technical.md` 附录 H 三处对齐，死键移除，补契约测试锁定单向不变式 |
| **rf-329** | 新闻关联模块在编排器留有注册分支，但无任何调用方按该分支调度，误导后续维护者推断并发行为 | 移除该注册分支，调用关系如实反映报告侧直调入口 |
| **rf-330** | LLM 模块显示名在配置默认值中另建副本，与中央注册表两处清单漂移 | 显示名回归 `core/registry.py` 中央注册表 |
| **rf-331** | 缓存指纹未覆盖提示词实际承载的 `pipeline_data` 派生段（环比差异、数据质量降级）；辩论综合键只哈希提示词模板文本而非白脸/黑脸完整正文，提示词开关变化不使键失效 | 指纹补齐两段承载文本（两侧共享同一构建器）；新增综合键构造函数，覆盖两段完整正文 |
| **rf-332** | `analysis` 包导出的股息率取值函数全仓无调用方（死码） | 删除函数及其再导出 |
| **rf-333** | 匿名化与图表数据构建各自维护「代码前缀是否合法」判定表，代码前缀知识散落 | 判定回归 `core/code_utils.py` 中心化函数 |
| **rf-334** | 汇率敞口按代码逐个发起 push2 请求，同一代码在多账户重复请求 | 会话复用 + 按代码去重，单次会话内只取一次 |
| **rf-335** | 汇率敞口「其他币种」汇总行引用未定义名，非主要币种敞口存在时崩溃 | 修正该行取值来源，补回归测试 |
| **rf-336** | 全仓 ruff lint 基线 324 项告警 + 176 个文件待格式化，且 `select` 未显式声明——默认规则集随 ruff 版本升级静默漂移，无感知 | 收敛至零告警：`ruff check --fix` 自动修复 216 项，手工收敛歧义变量名 / `lambda` 赋值 / 单行多语句 / `type()` 比较 / `\d` 转义告警；`ruff format` 176 个文件。`pyproject.toml` 显式声明 `select`、`extend-exclude`（归档目录冻结）与 `per-file-ignores`（E402 入口 `sys.path` 注入 + 子模块 re-export 块；F821 延迟导入 + 引号注解误报） |
| **rf-337** | lint 基线中有两项实为**缺陷而非风格**：`test_market_value` 的 `TestIsQdii` 内两条用例同名 `test_empty_string`（`is_qdii_by_name("")` 与 `is_etf_by_name("")`），后者覆盖前者致前一条**从未执行**；`test_config_atomic` 的 `_config_cache = None` 只是本地重绑定、未清模块级缓存，与注释意图不符 | 后者重命名为 `test_etf_empty_string`（用例恢复执行，全量计数 +1）；`_config_cache = None` 改用 `_clear_config_cache()`；`_report_generation`（重复导入 `build_action_data`）与 `test_generate_all_llm`（模块级 generators 导入块全无使用）按死码移除 |
| **rf-338** | `features.json` 宣传的 35 项功能开关中 **16 项声明即死**——全仓无任何代码读取其取值（LLM 模块启停、基金深度分析、新闻源、历史走势、匿名化总开关、缓存日清理），这些能力实际由 `config.json` / `llm_settings.json` 各自的键控制；`how-to-config.md` §M 等三处文档仍按生效开关介绍，用户照文档配置后无任何效果 | 移除 16 项陈旧开关——能力各归其主且多数已在 TUI/Web 面板上屏，无能力损失；文档 §M 由 35 项收敛至 19 项并指明各能力现归属何处；补回归测试逐项守住「注册表每一项都须有消费者」，无消费者键在加载时合并为一条 WARNING 上屏 |
| **rf-339** | 基金持仓的**报告期取回后无人校验、无人上屏**：`fetch_fund_holdings` / `fetch_quarterly_holdings` 返回的 `date`（报告期）在全仓**无任何消费者**，各调用方一律只取 `["holdings"]`，仅 provider 内部两行日志读过它。而 `fetch_quarterly_holdings` 在最近 4 个完整季度均无数据时会回退到**不带年份的默认请求**（该路径本意是「部分基金仅有早期报告」），可返回数年前的陈旧报告期——实测 040046 回退后取回 **2022-12-08** 的 10 条持仓，被 `penetration.py` 与当期报告期持仓**同权合并**进穿透 TOP10（`ratio` 直接乘以当前市值分摊），报告读者无从分辨这一格是四年前的仓位 | 新增时效判定模块 `report/holdings_freshness.py`（口径：报告期之后已走完的完整季度数，阈值 2 个完整季度，兼顾 QDII 披露滞后）；穿透层对判定陈旧的基金走既有「持仓不可用」路径——全值计入未穿透、不折进 TOP10，并以 WARNING 记录基金/报告期/已过季度数；`summary` 增补 `stale_funds` / `stale_fund_details` / `report_periods`，Excel 穿透页签与 HTML 报告同步上屏「各基金持仓报告期」与「报告期陈旧被剔除的基金（含距今季度数）」。报告期缺失或无法解析时不判陈旧（属数据缺失，仍走原路径）。补时效口径单元测试、穿透闸门回归测试（去掉闸门即失败）与页签备注写入测试；测试夹具的报告期改由 `recent_holdings_period()` 相对当天生成，消除写死日期随时间推移被闸门误判的时间炸弹 |
| **rf-340** | TUI 配置面板的盒线边框按**码点数**（`len()`）手写空格补白，中文/全角字符占 2 列却只算 1；同一面板的上下边框、分隔线与内容行又各写各的补白数，四处口径互不相同。实测单个面板的盒线行出现 **7 种行宽**（47~67 列），右边框参差不齐；中文名一长即撑破边框（如报告可选章节面板第 6 行 65 列 vs 边框 44 列） | 新增排版助手 `tui/text_layout.py`：`display_width()` 按东亚宽度计列并剥离 ANSI 颜色序列（`len()` 对着色行会把转义字符也算进去），`render_panel()` 按整块面板最长行统一定宽，四边对齐由构造保证；`handlers_config.py` 五个配置面板（LLM 分析章节 / 对比指数池 / 报告可选章节 / 报告增强子模块 / 持仓匿名化）全部改走该入口，名称列按最长显示名对齐。补单元测试（宽度口径 + 等宽不变式）与面板级回归测试（逐个面板驱动渲染后断言盒线行等宽）；报告层 `report/progress.py` 的模块耗时排行同属此形态，另行处理 |
| **rf-341** | 其余持仓消费者仍未标注报告期：穿透表已上屏报告期并对陈旧快照设闸门（rf-339），但 `fund_concentration.py`（持仓集中度）、`excel_fund_deep_analysis.py` / `html_renderers.py`（基金深度分析）、`position_overlap.py`（重合度矩阵）、`fund_candidate.py`（候选比较）仍只取 `["holdings"]`，同样会把数年前的快照按现行持仓呈现——集中度模块还会拿它与上一次快照算环比，得出与当期配置无关的「变化」 | 报告期接入四处消费者，按模块语义分层处置：**重合度**（按市值加权，陈旧权重失真）剔除陈旧基金并在 Excel/HTML 两侧标注剔除清单；**集中度/风格/候选比较**（比例与分类为主）保留并标注报告期——统一措辞 `fund_period_label()`（名称 + 报告期 + 已过完整季度数），Excel 与 HTML 同源；集中度页签新增「报告期」列，报告期未推进时环比标「无对比意义」而非报 0（本次与上期读的是同一份报告），且快照条目原样沿用、不刷新 `check_date` 伪装成新观察；快照增记 `period` 供下轮判别。报告期陈旧被剔除/保留之处均留 WARNING 与产物标注（删除数据必须留痕）。补口径单元测试与两产物回归测试 |
| **rf-342** | **实验性功能的开启状态在报告产物上不可见**：11 项实验开关会改变报告内容（辩论三项改变 expert_review 形态、决策跨期反思闭环新增行动章「历史决策复盘」区块、模块级质量分级追加内容质量横幅，而信号预消化/决策头结构化/确定性信号沉淀只改内部路径、完全不留痕），但报告本身不说明自己是在哪些非默认开关下生成的。唯一全局提示 `log_experimental_features()` 只活在控制台——报告一旦导出流转，读者无从判断「历史决策复盘」区块是常驻功能还是本机实验开关的产物，也无从判断某处内容质量提示究竟是内容问题还是开关所致；现有痕迹零散（辩论三项共用同一个「🧪 实验模式」标签、质量横幅不标来源开关），缺的正是可复现性的前提——产物须自述其生成条件 | 报告两处产物各落一行实验功能清单：HTML 页脚（紧邻既有「🧪 辩论模式已启用」行）与 Excel 用量页签（说明行之后，不受会话用量早退影响）。清单只列**显示名**、取自 `EXPERIMENTAL_FEATURES` 注册表（与 TUI 菜单 S / Web 面板 / 日志横幅同源，注册表仍是唯一清单来源），经新增的 `enabled_experimental_features()` 统一取数；零开关时两处均不出现，既有输出与既有测试不受影响。补单元测试（清单顺序与显示名取注册表 / 仅实验开关入列）、页签写入测试（含无会话用量时仍在）与页脚渲染测试（含漏传上下文不出现空壳行） |

| **rf-343** | 实验功能清单在 Excel 侧只落在「LLM API 用量」页签，而该页签只在 LLM 章节开启时生成（`report/excel_llm_usage.py` 在 `not include_llm` 时直接返回）。因此 LLM 分析整章关闭时 Excel 产物上不出现清单，而 `signal_ledger` / `datasource_adapter` / `decision_reflection` 等**非 LLM 实验开关**此刻仍可能开启——这批开关不依赖 LLM 章节，其在 Excel 产物上遂完全无痕。HTML 页脚不受影响（页脚始终存在） | 汇总页签页脚补兜底落点：LLM 用量页签缺席**或为空**（用量数据/模块明细缺失导致写入早退）时写入清单——空页签这条是核查中发现的额外缺口，不止「页签不存在」一种无痕形态；已落在用量页签时不重复写（同一事实说两遍会被当成两处来源）。措辞收敛到 `report/experimental_notice.py` 单一来源（`enabled_notice_line()`），HTML 页脚与 Excel 两处落点共用，并补跨产物措辞一致性测试防漂移。同步 `how-to-config.md` §M 的告知说明，补页脚写入单元测试与全链路回归测试（`include_llm=False` 时清单仍须上屏且全文只出现一次） |
| **rf-345** | **报告产物的生成条件自述出现假阳性开关**：`enabled_experimental_features()` 遍历整个 `EXPERIMENTAL_FEATURES` 注册表，凡启用即列入 HTML 页脚 / Excel 清单——而系统自检（`doctor_check`）只门控 TUI 菜单 `[D]` 与 Web 卡片两个入口的可见性，**不改报告任何字节**。一个只影响入口显隐的开关出现在「本报告在哪些实验功能下生成」的清单里，读者会推断内容受其影响（rf-342 引入该自述时，注册表尚无「只影响入口」类成员，故当时口径无懈可击——缺陷随注册表成员变化而出现）。同一处还暴露归类问题：系统自检是只读诊断（不改产物、不写文件、联网检查每次显式确认），却被按「新增能力默认关」的发布惯例归为实验项默认关——默认关的实际代价是让**环境出故障的那批用户恰好看不到它**，而开启对默认输出零代价 | 两处一并处置。① **自述准入口径显式化**：注册表条目类型由 `(显示名, 说明)` 二元组扩为 `(显示名, 说明, 是否改变报告产物)` 三元组，`enabled_experimental_features()` 按第三位过滤——新增实验项时必须书面回答「能否改变报告产物」，答否者不进自述；同时更新三处解包点（`_match_experiment` / `describe_experiment_flags` / TUI 与 Web 面板清单生成）与 `core/doctor.py` 的解包。② **系统自检转正为默认开启**：移出 `EXPERIMENTAL_FEATURES`（不再上实验面板、不再进产物自述），`_FEATURE_FLAGS_DEFAULT` 保留同名键并改默认 `True`；TUI `FEATURE_GATED_ITEMS` 与 Web `system_info["doctor_enabled"]` 门控**保留**——转正不等于不可关，`features.json` 置 `false` 仍可隐藏两个入口；CLI `doctor` 子命令本就先于 `init_config` 分派、始终不受开关约束。管理文档与用户手册同步（`requirements.md` §3.6/R-DIAG-05~07、`technical.md` §4.17.3 三面上屏表、`folders.md`、`how-to-config.md` §M、`how-to-use-tui-menu.md` 实验面板编号 6~16→6~15、`how-to-use-web-mode.md`、`faq.md`、`developer-guide.md`），并补「实验性」准入与转正判据（只读诊断类能力应默认开启）。测试：新增三元组声明完整性、只影响入口的合成项被排除、`doctor_check` 开启时自述为空三例，及默认值/非实验项/开关仍可关三例；TUI 与 Web 各补「默认配置下入口可见」用例（原有用例均 `patch` 覆盖取值，测不出默认值本身）。移除随转正失效的 `⚗ 实验性` 标签与其 CSS 规则 |
| **rf-344** | 候选基金比较子表的**「风格」与「与持仓重合度」两列在取数成功时恒为空**：`fetch_fund_holdings_cached()` 返回 `{"name", "holdings", "date"}` 字典，而 `fund_candidate.py` 把它**整体**当作持仓列表传给下游（`classify_fund_style` 与 `compute_overlap_matrix` 都期望 `[{name, code, ratio}, ...]`），在字典上迭代键名（字符串）即抛 `AttributeError`；两处各被自身的 `try/except Exception` 吞成 `logger.debug`，于是两列恒为 `--`。既有单测全部 mock 掉 `compute_overlap_matrix`，真实入参形状无人校验，缺陷长期潜伏（rf-341 修复过程中撞见） | 取 `fh["holdings"]` 后再传下游，既有基金持仓基准与候选持仓两侧口径统一为持仓列表；既有基金侧同时按报告期时效剔除陈旧者并标注；补**不 mock 计算引擎**的回归测试（喂真实形状的字典，断言风格与重合度两列被填出） |
| **rf-346** | **功能开关的「面板可见性」被绑在「是否实验项」上**：`EXPERIMENTAL_FEATURES` 同时承担三件互不相干的事——决定面板可见性、决定默认关、决定是否进产物自述，于是「转正」（默认值改 `True` + 移出实验注册表）会**连带摘掉可见性**：`doctor_check` 转正后 TUI 菜单 `[S]` / Web 配置面板 / CLI `--experiment` 三处全部消失，关闭途径只剩手改 `features.json`；反方向同样成立——`metrics_*`（7 项）与 `enable_interactive_charts` 从来不在任何界面通道内，用户要关闭某项指标只能手写 JSON。用户看到的是 19 项同质开关，其中一半能改、一半不能，而「能不能改」取决于它是否被标为实验项，两者本无逻辑关系 | 注册表统一（合并 `EXPERIMENTAL_FEATURES` 与 `_FEATURE_FLAGS_DEFAULT` 为单条声明 `feature_switch_registry`：显示名/说明/分组/默认值/产物影响五字段，"面板可见性"由**分组属性**表达而非「是否实验项」）；转正 = 改一个字段，可见性自动延续。三渠道入口一律由注册表派生：TUI 面板分「实验性功能（默认关）」与「常规开关（默认开）」两块、Web 配置面板同构并下发标签与「影响报告」标记、CLI 新增 `--feature NAME=VALUE`（双向、仅本次运行、不写盘）。同时把 `datasource_adapter` 转正为默认开启（内部接缝，开关两态下报告产物逐源等价，不该占一个默认关的用户开关；见 developer-guide「内部接缝类开关也应转正」）。设计文档 `docs-stm/plan/feature-switch-registry-design.md`；计划项 plan-39 |

| **rf-347** | **「常规 ETF 页也有相关锚点」这一误判防线的设计理由与实测相反**：设计稿称常规 ETF 主页含「查看相关ETF」锚点属**推荐位**，故须靠名称含「联接」过滤。落地前实测发现两类页面的相关链接**互为反向**——联接基金页标签止于「ETF」指向场内目标 ETF，常规 ETF 页标签为「查看相关ETF**联接**」指向该 ETF 的场外联接基金；且前者是后者的**前缀**，锚点正则 `查看相关ETF` 会一并命中反向链接。原设计只把「名称过滤」当唯一防线（且该过滤由调用方负责），一旦有常规 ETF 的名称含「联接」二字或调用方漏过滤，就会把该 ETF 的底层暴露错认成其联接基金的持仓。附带：测试夹具 `_NORMAL_ETF_HTML` 按设计稿的错误认知构造（在常规 ETF 页写「查看相关ETF」），测的是不存在的页面形态 | 锚点识别加**两重独立区分**并在正则内自证：① 标签须止于「ETF」（负向先行断言 `(?!联)`）；② 目标须为场内代码（`is_exchange_fund_code`，前缀 5/1）。实测 `561910` 的锚点两重各自都能挡下、`016055` 两重都通过。夹具改为真实形态（常规 ETF 页写「查看相关ETF联接」→ 场外 `016019`），补反向链接拒绝用例 2 例；设计文档 §3.3 的错误理由改写为实测结论并附两个方向的对照表 |
| **rf-348** | **报告章节的默认顺序存在两个事实来源，文档随之分叉**：注册表出厂默认（`action`=17、`portfolio_evolution`=16）与仓库 `config.json` 的 `report_section_order`（`action`=10、其余顺延）并存且不同序，于是同一事实在文档中并存两种写法——`requirements.md` §6.3、`how-to-config.md` 排序表、`reports-instruction.md` 页签表按 10 写，`technical.md` 两处契约行与 `reports-instruction.md` 旁注仍按 17 写。两份顺序只要并存，改其一必使另一处的文档悄悄过期（本条的两种写法正由此而来，非笔误）。附带发现：`unit/report/test_excel_report_structure.py` 的表头自称「与 registry.py 对齐」，实为 `create_sheets` 的**输入**数据、序号只在本表内自洽（且刻意省略 `action`/`portfolio_evolution`），照该注释在下次改注册表时会被误当镜像同步——而它本非镜像 | 用户决策「改注册表默认值」：`core/registry.py::_REPORT_SECTION_DEFAULT` 的 `action` 由第 17 位前移至第 10 位（紧随 `style_factor`），其后 `news_correlation`…`portfolio_evolution` 顺延为 11…17，`data_source_status`=18、`llm_usage`=19 不变，双源分叉消除（清空 `report_section_order` 与保留它从此效果相同）。仅改变**出厂默认**（`{}` 配置的用户与全新 clone），本仓库显式配置同一顺序、报告产物逐字节不变。`unit/core/test_registry.py` 两处序号断言同步（evolution 16→17、action 17→10）并订正 docstring；两处测试文件的表头注释改为如实说明；`how-to-config.md` / `reports-instruction.md` / `technical.md` / `config.json` 四处旁注与 `number=` 取值同步 |
| **rf-349** | **「行动建议」的 basic 可见性只存在于文档，未落到实现**：契约一致声明该章为纯算法、`basic/both/full` 均可见（`requirements.md` R-ACT-01、`technical.md` 章节契约、`reports-instruction.md` 页签表与分组说明、`how-to-config.md`、TUI 手册），而 `report/orchestrator.py` 的 basic 分支既未下传 `enable_action`（页签不创建），也无 `pipeline_data` 注入（即便创建也只写「无持仓数据，行动建议无法生成」占位）——菜单 E 的用户永远看不到这一章。三条独立证据指向实现漏而非文档错：注册表中 `action` 条目自身注释即写明「纯算法，basic/both/full 均可见」且 `data_flag=None`；`git log -S enable_action -- orchestrator.py` **零结果**（从未接线而非被移除），且同一分支**确实**下传了同级的 `is_enable_data_quality`/`is_enable_cost_lots`，属不对称省略；全部文档中仅 `reports-instruction.md` 的「按菜单快速索引」B 行一处异说 | basic 分支补传 `enable_action=is_enable_action(config)`；`excel_generator.generate_excel_report` 在行情明细落成后，若开关开启且 `pipeline_data` 未带 `action_data` 则就地构建（both/full 由编排层注入，已注入时原样透传、不重复构建，编排层仍为唯一事实来源）。basic 无历史走势故 `portfolio_peak_mv` 缺省——组合级回撤纪律按「峰值未知」不激活，其余纪律不受影响。持仓明细投影函数由 `_both_action_holdings_details` 更名为 `_action_holdings_details`（basic/both 共用）。补回归测试三例（未注入即构建、已注入不重建、关闭即不建）与 basic 接线守卫（精确 kwargs 断言含 `enable_action=True`）；`reports-instruction.md` 索引行与 `technical.md` 组装口径、附录 H 台账来源列同步 |

### 已解决待归档（v0.10.17-dev）

v0.10.17 已解决记录（rf-297、rf-303、rf-305 ~ rf-321）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.17 章节（变更详情见 changelog.md [0.10.17] 对应条目）。

### 已解决待归档（v0.10.16-dev）

v0.10.16 已解决记录（rf-295 ~ rf-304）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.16 章节（变更详情见 changelog.md [0.10.16] 对应条目）。

### 已解决待归档（v0.10.15-dev）

v0.10.15 已解决记录（rf-288 ~ rf-294）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.15 章节（变更详情见 changelog.md [0.10.15] 对应条目）。

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.17（2026-08-04 ~ 2026-09-10，rf-204 ~ rf-321）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
