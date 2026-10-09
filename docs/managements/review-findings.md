# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.7-dev
> **编号源**：`rf-next = 642`（新增问题取此编号，完成后更新为 +1；已用最大 rf-641，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题


### P1 — 高优先：不做的风险高（尽快执行）

> 入选标准：默认开启功能与用户渠道未经完整验证，遗漏即放行线上缺陷。

| # | 问题 | 修复方向 |
|---|------|----------|

| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

### P2 — 中优先：价值明确、成本可控（下批排期）

> 入选标准：修复路径清晰、成本可控；rf-114 须待 rf-113 人工验证完成后执行。

| # | 问题 | 修复方向 |
|---|------|----------|

| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |
| **rf-635** | 调仓模拟产物无匿名化层——`whatif_writer` 生成的 HTML（明细对比/变更明细/可行性/成本面板）直接用真名真码渲染，既无字段层 `apply_report_anonymization`，也无产物清扫（名称/代码均裸奔），与主报告的匿名化契约不一致；主报告已把代码面收在渲染点与清扫层，whatif 模板预留了 `anon_code` 渲染点但未接映射 | 按主报告同一分层接入：装配边注入 `apply_report_anonymization` → 渲染点/`anon_code` 映射 + 名称清扫 → 产物输出；离线场景补 whatif 产物端到端真名/真码断言 |

### P3 — 持续监控：文件过长登记表（>500 行观察，脚本域 >400 即入观察 / **>1000 行为硬上限必须拆分**（主程序与脚本）；按距红线余量升序）

> **派生源（2026-10-05 起，人肉快照退役）**：行数与全集以 `scripts/check-file-length.py -v` 输出为真值（该输出列出全部 >500 行主程序、>400 行脚本、>800 行测试文件）；红线（主程序/脚本 >1000 行、测试 >1200 行）由 `check-file-length.py --ci` 自动拦截（豁免路径与本表挂账同步），不再依赖本表人工发现新破线者。本表仅登记需跟踪/决策的文件，**触发式处理**：未逼近红线不排期，逼近时按本表拆分建议执行。
> **红线体系调整（2026-10-09）**：主程序硬上限 800 → **1000**（警告 500 不变）；`scripts/` 首次纳入检查域（警告 >400 / 红线 >1000）；测试 800/1200 不变。调整决策与理由见 `docs/managements/technical.md`「大文件红线体系（主程序/脚本/测试）」决策记录；域内最大单文件 `scripts/factor_zoo_eval.py`（1595 行）同批按「评测核心 / 阶段编排 / 判定书」拆为 `_factor_zoo/` 包，红线内最大脚本为 `release.py`（841，距红线 159）。
> **测试文件口径**：阈值见 `developer-guide.md`「文件膨胀阈值」表（行数 >800 警告 / >1200 红线；测试项 >80 警告 / >120 红线），**当前无挂账项**（贴线跟踪 rf-586 的拆分已完成并转入下方已解决区）；警告级全集以 `scripts/check-file-length.py -v` 为派生源，不做人肉快照；逼近红线（1200 行 / 120 项）时按「被测函数 / 场景类型」拆分为同目录兄弟分片，并同步刷新 `test-coverage.md` / `folders.md` 用例计数。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|

| **rf-626** | `llm/prompts_core.py`、`llm/generators.py`、`report/html_writer.py`、`analysis/rebalance.py` | 350 / 444 / 783 / 751 | **临界带（≥950 行）四文件登记项**；`prompts_core`/`generators` 主体已按域下沉完成（800/787 → 350/444：failure_reasons / prompts_data_blocks / prompts_review / generators_singletons 四新模块承载，两文件保留门面 re-export、消费方导入面不变，仅 4 处测试 patch 按「测试指向持有子模块」纪律改指新域）；2026-10-09 实测 `html_writer`(783)/`rebalance`(751)，距 1000 红线余量 217/249，已出临界带 | `html_writer`/`rebalance` 由 `-v` 月度复核、逼近 980 行启动拆分（方法沿用本次：域下沉 + 门面 re-export + 测试 patch 改指持有子模块） |
| **rf-86** | `cache/operations.py` | 740 | 500-1000 可选优化区间（2026-10-05 脚本实测 740，较 2026-10-02 的 637 增长 103，增长偏快，`-v` 按月复核） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-79** | `core/code_utils.py` | 671 | 维持现状（仍在 500-1000 区间内聚；2026-10-02 实测 671，较登记值 542 增长 129，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-89** | `report/excel_generator.py` | 642 | **500-1000 可选优化区间，增长偏快**（2026-10-09 实测 642，较 2026-10-05 的 585 增长 57——持仓基本面合并页签等增补）；暂维持现状，`-v` 按月复核 | 页签编排可进一步下沉到独立 writer（后续择机） |
| **rf-80** | `report/data_status.py` | 622 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-10-09 实测 622，较 2026-09-10 的 544 增长 78——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 577 | 维持现状（render 函数属同一渲染域；2026-10-09 实测 577，较 2026-09-10 的 521 增长 56） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 555 | **已跨入 500-1000 可选优化区间**（2026-10-02 实测 555，较 2026-09-10 的 405 增长 150——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-78** | `fetcher/batch.py` | 520 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-10-02 实测 520，回落至登记值附近（rf-522 重试退避原语收编后下降）） | BatchDispatcher 本身内聚，可维持现状（不拆） |

## 已解决问题

- rf-641 已修复（2026-10-09，计数回写效率自查，当批修复）：测试计数刷新缺轻量回写入口——`check-doc-drift --with-test-count` 只读核对不落盘，实施收尾刷一次计数被迫整跑 `bench --update-docs`（14 模式、分钟级）；已定流程纪律 bench 只在发布刷新/换机跑，两者之间计数行长期无人回写。新增 `collect-test-coverage.py --update-docs`：按本次收集快照回写 `test-coverage.md` 计数行（反引号标记行 + 能映射到标记的加粗标签行，比对域与 `check_test_coverage_counts` **同构**、行匹配/标签映射复用 check-doc-drift 原语）与 `folders.md` 项目统计表「测试用例」行；只改计数数字（粗体/千分位/` 个` 后缀原样保留），一致零变更幂等；收集退出非 0/5 跳过回写并告警，错数不落盘；快照单源 `_build_snapshot()`（输出分节与快照同出一份，`edge/data/smoke/scenario_extreme` 同名键覆盖次序与子进程 `_parse_collect_stdout` 逐行后写同义，重叠四处谓词与裸标记判定已实测同值）。子标记清单提升为模块常量 `UNIT_SUBS`/`SCEN_SUBS`/`CROSS_SUBS`（输出与回写同一来源）。回归 7 项：保形改写（粗体/别名 `all`/聚合行/章外同标签行/folders 后缀）、非计数行跳过（未入快照键/无计数格/未映射标签）、写后过 `check_test_coverage_counts` 反漂移断言、幂等二轮零变更、CLI 摘要、收集失败跳过且不碰文件、空收集放行回写
- rf-640 已修复（2026-10-09，Windows 钩子回放乱码自查，当批修复）：pre-commit 十守护经 `run_bg` 把 stdout 重定向到日志文件，中文 Windows 上 Python 按 locale ANSI（cp936/GBK）落盘，`cat` 回放到 UTF-8 终端即成乱码（GBK `CE B4`=「未」被读作 `δ`；前台直打走控制台 `WriteConsoleW` 正常——与「前台正常、回放段落乱码」的分界完全吻合），纯显示问题、退出码与判定不受影响，但守护详情在 Windows 上不可读。修复三点：① 钩子 `set -e` 后 `export PYTHONUTF8=1`（UTF-8 模式统一按 UTF-8 写日志，Linux/CI 本就是 UTF-8、行为不变）；② `scripts/_checklib.py` 导入时 `_force_utf8_stdio()` 把**非 UTF-8 的真实 stdout/stderr**收敛到 UTF-8（`_force_utf8_stream`：已 UTF-8 不动、`StringIO` 等测试输出桩跳过），模块 docstring「无副作用原语」例外清单同步为两项；③ 回归 4 项：cp936 文本流收敛、已 UTF-8 零改写、非 TextIOWrapper 跳过、`_force_utf8_stdio` 对当前 stdio 生效

- rf-639 已修复（2026-10-09，文档计数核对诊断发现，当批修复）：`check-doc-drift --with-test-count` 的计数核对只识别反引号标记行，`test-coverage.md` 功能域表的中文加粗标签行因不匹配以「未收录名」**静默跳过**，实测该表 4 行过期（报告生成 / LLM 智能分析 / 配置管理 / 核心基础设施）无人核对。修复五点：① 标签↔标记映射与 collect 功能域聚合**单一来源**（`_test_runner.modes.UNIT_DOMAIN_LABELS`，collect 侧同对象引用防双处定义漂移）；② 功能域章内（`## 功能域对应测试源`）出现**未登记标签**或映射集**缺行**一律报 finding，章外加粗行不属核对域（既有用例不受影响）；③ 表内「端到端业务场景」聚合行经显式别名映射 scenario 父标记；④ 功能域行标签与单源对齐（「CLI 命令行模式」→「CLI 命令行」），完整性反查按**标记覆盖度**判定、对标签措辞免疫；⑤ 同批刷新该表 11 行过期计数与 `folders` 测试用例总数。回归 7 项：映射匹配/不匹配、章内外边界、未登记报出、缺行反查（按映射集动态遍历不写死条数）、collect 同对象断言

- rf-638 已修复（2026-10-09，全量测试收尾发现，当批修复）：`test_design_tokens.py::TestSharedRoleParity` 的两个类作用域 fixture（`report_defs`/`web_defs`）以实例方法形式定义在测试类内，全量套件稳定输出 2 条 pytest 弃用告警（类作用域 fixture 用实例方法定义，实例属性对测试方法不可见；后续 pytest 版本移除该形式）——已把两个 fixture 提升到模块级（作用域保持 class，仍按类复用、不重复读模板与样式表），`-W error::pytest.PytestRemovedIn10Warning` 下 7 项全绿；全仓类作用域 fixture 仅此一处，无同类遗留

- rf-637 已修复（2026-10-09，36 小时技术债核查发现，当批修复）：上一条分层修复引入的 core 网关展示文案钩子（`register_circuit_text()` / `circuit_text()`）缺两支回归覆盖——上游未注册时按「正常」降级的缺省分支、以及展示原语必须经网关取文案的路径（后者无断言则回退成直连上层也测不出）。补 3 项：缺省降级、注册后按注册判定出文案、`system_info.circuit_display` 必须读到注册替换的结果（**回退直连上层即红**，已实测验证）。同轮核查其余维度全净：窗口 43 提交新增 789 个 def/class 全部落在有测试文件的模块（模块+符号双重无覆盖 0 项）、无新增 TODO/FIXME/抑制标记、测试域脚本加载样板迁移后无死路径常量与残留样板（先前命中为计数器双重扣除误报，逐项核实均为在用）、工作区无临时产物残留；调仓模拟产物无匿名化层属已登记待处理项（非新增），主报告相关性矩阵列头真码由 `mask_code_text` 边界安全兜底覆盖（独立代码 token 命中、金额与 JSON 数值子串跳过），故渲染点未加过滤器不构成泄漏

- rf-636 已修复（2026-10-09，历史痕迹守卫空转失效，当批修复）：`check-code-traces` 的实现拆包至 `scripts/_traces_code/` 后，`config.REPO_ROOT` 路径深度少算一级（落成 `scripts/`），`SCAN_DIRS` 四个路径全部不存在 → 遍历逐个跳过 → **守卫恒 exit 0 空转**，CI `guards` 档与 pre-commit 十守护连同它空跑多日；同时拆包把规则定义字面量（`R11`/`F-1`/`第X章`/`rf-117` 的模式与示例）搬入 `scripts/_traces_code/`，`_is_tool_self()` 只按 `check-*.traces.py` 文件名豁免，规则载体自身成为头号命中源。修复七项：① `REPO_ROOT = parents[2]`（代码内注记层级深度）；② 新增 `RULE_CARRIER_DIRS = {"_traces_code"}` 按**目录**跳过规则载体（与文件名无关，后续拆包子目录自动覆盖）；③ 裸版本号模式加 `(?<![\\d.])…(?!\\.\\d)` 逐 token 排除 IPv4 内嵌子串（`127.0.0.1`/`0.0.0.0` 的 `0.0.x` 是地址片段而非版本号；不采用整行放行，同侧真实版本痕迹照报）；④ `_magic_excludes()` 收录真实领域值（`F10` 基金费率页、`P0~P4` 门禁档位与公式价格符号、`T0` 事件窗口锚定、`S0`/`S1`/`MV0`、`Phase1`/`Phase3`、`E1~E3`/`W1~W2` 样式护栏编号），并同步修正 `test_magic_number_letter_digit_flagged` 的样例（`P1 优先级` → `K9 优先级`：原样例与门禁档位领域值直接冲突，其余 7 个暗号样例不变）；⑤ **分层倒置实质修复（不加豁免）**：`core/system_info.py::circuit_display` 函数内 lazy import `llm.circuit_breaker` 改走 core 网关新增的 `register_circuit_text()`/`circuit_text()`（晚绑定回调：展示层不反向 import 上层、也不复制上游 URL→域名归一规则；既有三处 patch `get_circuit_status` 的用例经晚绑定仍生效）；⑥ 其余 40 个被改文件为注释/文档串改写（任务编号、约束代号、历史叙述、迭代标记、章节暗号、待办误报、语义暗号），逐文件经 **AST 归一化比对**证明仅注释/文档串变化、代码语义零变动；⑦ 守卫自证回归：扫描目录存在性硬断言、tmp 种入式样本正/负双探针（种入必报、干净必过）、载体目录跳过而同字面量落在扫描域内仍报、领域值不误伤且同侧暗号照报、统一 CLI 面（`--help` 含 `-v`/`--ci`、`add_common_args` 即 `_checklib` 同一对象）。改前基线 167 条 → 改后 **0**，`--ci` exit 0；防再犯由扫描域自证用例与种入探针承接

- rf-633 已修复（2026-10-08，check-test-markers 双源与自相矛盾，当批修复）：① `KNOWN_MARKERS` 由手写 42 项改为 `registered_markers()` 从 `src/test/conftest.py` 的 `addinivalue_line("markers", …)` **AST 派生**（多行调用与相邻字符串字面量拼接由 `ast` 天然处理，只认 `markers` 分组、忽略 `*args`），conftest 新增/删除标记自动跟随——**已实测到真实漂移**：`cassette` 早已在 conftest 注册却不在手写清单内（43 vs 42），`@pytest.mark.cassette(...)` 一旦写成裸属性即被误判「未注册」；② `EXPECTED_DIR_MARKERS` 补齐目录结构缺口（新增 `unit/cache`→unit_core、`unit/startup`→unit_ui、`unit/web`→unit_web、`scenario/perf`、`scenario/security`——原表有 5 个含测试文件的目录无期望、静默不查），表头补「目录结构绑定」注释；`src/test/unit/conftest.py` 的 `_DIR_TO_MARKER` 运行时提示表同步补齐 cache/scripts/startup（原缺 3 项，漏标报错文案会落到「unit_<未知模块>」）；③ 模块 docstring 通过标准按现状改写：删去「已移除的标记（如 integration）」这一与 `integration` 实为现行注册标记的矛盾表述，并把「scenario/ 下每个测试类」纠正为目录级期望；回归 = `src/test/unit/scripts/test_check_test_markers.py` 27 项，含三组**结构性**双向绑定断言（期望表键全部是真实目录 / 有测试的 `unit/*`·`scenario/*` 目录全部有期望 / `_DIR_TO_MARKER` 键集 ≡ 期望表 `unit/*` 键集，均不写死条数），标记清单等式断言在手写清单下即红（42≠43）

- rf-632 已修复（2026-10-08，scripts 测试欠账，当批修复）：四个零测脚本补齐**纯函数优先**的直接单测，共 87 项。① `check-svg.py`：字符宽度七档位与 bold 档、三种 `text-anchor` 包围盒展开与字号默认、`_parse_svg` 坏元素跳过（**`_text_box` 补 try/except，与 rect 防御对称**，缺 x/y 或 x 非数值不再中断整轮审查）、`_parent_rect` 最小面积容器/横向不相交/无包含三态、`geom_findings` 四类 finding（越界/贴边/文本重叠/无容器越画布）与干净路径、`geom_notes` 同列底部提示不入退出码、`geom` 子命令 0/2/文件缺失 2；② `check-test-markers.py`：AST 三来源提取（模块级 pytestmark / 类与方法装饰器 / 无标记与语法错误降级 / 相似属性名不误判）、`_get_relative_dir` 嵌套与根层、`check_file` 八分支（未注册/已移除/edge 文件缺 edge 与合规/目录期望未达与达成/未登记目录不误报/verbose 干净路径）；③ `perf-view.py`：`_mean`/`_min_max` 空输入降级、`_merge_phase_stats` 跨记录合并与阶段名排序与坏 `phases` 忽略、`_group_records` 类型过滤/截尾/组内按时间排序/组键排序/缺字段缺省键、`build_trend_report` 空数据文案/头部计数同源/分组与阶段表/明细截 5/过滤参数生效；④ `collect-test-coverage.py`：`_collect` 对 pytest 退出码 0/4/5 原样传递与 CLI 参数·插件注入·输出静默、`CollectPlugin` 记录与重收集清空、`_target_files` 目录展开·文件透传·不存在目标·排序·**live 套件排除**、`_sel` 三态、`main()` 出口 0/5 正常返回 与 1/4 原样 `sys.exit`、模式/子标记/跨类计数与注入记录同源；**同批修复两处**：`_text_box` 防御不对称（见上）、`perf-view.py` 明细时间列 `[-16:]` 把年份首位截掉（`2026-01-01 10:00:00` → `6-01-01 10:00:00`，与注释口径也不符）改 `[:16]`（日期+时:分）；回归验证 = 摘除 `_text_box` 防御后 3 项红、回退 `[-16:]` 后 2 项红

- rf-631 已修复（2026-10-08，perf-report 三处缺陷，当批修复）：① 报告「测试时间」由硬编码日期改为 `_test_time_text()` 按运行时刻动态生成；② 规模文案全部按实际样本派生——新增 `PerfSample(holdings/stocks/funds)` 与 `_sample_of()`（**按账户口径**分列，港股非 6 位代码不再被按位数误计为基金），`write_perf_report(timings, phase1, phase3)` 签名带入两阶段实际规模，概述/表格/结论三处文案同源出数；同时股票样本池 `SAMPLE_STOCKS` 扩到 50 支（`_PHASE3_STOCK_COUNT=50` 由样本池覆盖，`[:50]` 静默截断消失），常量改名去掉误导数字（`_PHASE1_STOCK_COUNT`）；③ LLM mock patch 目标由 `generators_orchestrator` 子模块属性改为包属性 `src.python.llm.generate_all_llm`（与 `_llm_news._submit_llm_future` 函数内 `from src.python.llm import generate_all_llm` 的读取点一致），mock 返回值同步改为与 `generate_all_llm` 契约同构的 8 元组（4 模块内容 + 4 缓存标志）——**核查修正**：`_generate_report_both` 路径 `enable_llm=False` 硬编码、并不调用 LLM，故原 patch 属无效死补丁（无实际费用风险），改对目标后成为该路径未来接入 LLM 时的有效防线；回归 = `src/test/unit/scripts/test_perf_report.py` 18 项（样本规模/池覆盖上限/账户口径分类/`_verdict` 边界/测试时间随运行更新/规模文案随样本变化/patch 目标与读取点一致/mock 值经真实收集器解析），摘除修复后 16 项红

- rf-630 已修复（2026-10-08，scripts 核查同批发现的退出码 docstring 契约族不齐，当批修复）：`check-test-markers.py` 声明「0/1」而实现走 `_checklib.report()` 实为 0/2（与 rf-629 同类实错）→ 改 0/2；`check-file-length.py` / `check-style-guardrails.py` / `check-version-consistency.py` 缺「退出码」声明节 → 补齐（两例 0/2；后者同时把 usage 里「不一致退出 1」的错述改为 2，并如实声明 1=事实源不可读与 `--ci` 用法）；`check-requirement-trace.py` 的 0/2 同行不成节 → 分行列举；CLAUDE「scripts 共享设施与契约」段 → 补全分级退出码特例（`check-code-traces` 1=HIGH/2=硬禁止引用/3=仅 LOW、`check-doc-traces` 1=HIGH/2=仅 LOW、`check-svg` 1=环境缺失）；防再犯由 plan-110 机检承接，其白名单同步登记 `check-version-consistency` 的 1

- rf-628 已修复（2026-10-08，匿名化剩余衍生面自查，当批修复）：**代码面改为渲染点结构化掩码，HTML 自由文本清扫剥离代码**——原实现把「真码→000XXX」并入 `build_report_alias_map` 后对整份 HTML 做子串替换，与代码注释/登记前提（数字串全局替换有金额误伤风险、刻意不在 HTML 自由文本换代码）相悳，实测会把 `1600519.00` 改成 `1000XXX.00`（破坏金额与 JSON 数值），而 summary 模式因映射根本不含代码、明细以外章节真码完全裸奔；修复 = ① `build_report_alias_map(..., include_codes=False)` 专供 HTML 名称清扫（Excel 字符串单元格清扫保持含代码）；② 匿名化层新增 `build_code_display_map`（真码→显示掩码，键控精确、指数基准码天然不在内）、`mask_holding_code` / `code_masking_enabled`（提示词单点折叠）、`mask_code_text`（**边界安全**替换：相邻非数字/小数点/冒号才认作独立代码 token，命中 `<td>600519</td>` 而跳过 `1600519.00`）；③ 模板新增 `anon_code` pass_context 过滤器，各章节代码列在渲染点按 `anon_code_map` 键控折叠（明细/持仓汇总/穿透/持仓结构/基本面/基金业绩/风格因子/演进/数据源状态/行动建议 9 份 partial，列表型 codes 用 `map("anon_code")` 逐项折叠）；④ 演进图表 `top_holdings` 代码在**数据层**折叠（JSON 负载模板过滤器够不到）；⑤ LLM 提示词组装点折叠（明细行/TOP3/数据速查表/穿透/新闻持仓摘要/自审摘要/行动建议/持仓变动差异），代码白名单块在折叠模式改写为「真码一律不写」反幻觉约束（避免全列 000XXX 自相矛盾），无代码明细时跳过「共 0 个」退化块；**数值面评估结论**：派生章节（财报摘要/估值分位/风格因子/基金业绩）数值全部是公开市场与财报数据、与持仓身份仓位无关，保留原值以维持指标口径可复核；仓位面已由明细层覆盖（full 千位模糊 / summary 大类聚合）；调仓模拟产物无匿名化层超出本次范围，另立 rf-635；回归 = 产物级 HTML 真码断言（full/summary，摘除渲染点与清扫后 summary 立即红）+ 匿名化映射/边界安全替换/渲染点过滤器/图表数据层/提示词五组单测，手册 §L 按实现口径改写

- rf-634 已修复（2026-10-08，线上持仓变动复盘归因静默丢失自查，当批修复）：**串行后置模块以 `http_client=None` 直达 provider 层**——`run_holding_change_review`（含孪生 `run_self_review`）经 `generate_llm_module` 全链不注入客户端，而客户端装配只在分发层 `_llm_dispatch._execute` 为并行 worker 做；None 触发 `_api_claude/_api_openai/_api_gemini` 的 `assert client is not None` 秒败，AssertionError 又被 `call_llm` 多链循环的 per-provider `except Exception` 吞成「provider 异常，切换下一 provider」——日志实测四 provider 各 ~2ms 内连环失败（2026-10-07/10-08 两次），归因整章静默丢失（plan-76 落地后从未成功过）；修复 = 在多链与 legacy 两路的唯一汇聚点 `call_single_provider` 收口：`http_client is None` 且 provider 受支持时经 `core.http_client.make_http_client`（HTTP 客户端统一工厂约束）自建一次性客户端、`with` 调用后关闭；回归 = 漏斗层 7 项（三 provider 兜底建/关客户端、调用方自备客户端透传不代关、未知 provider 不建、多链 `http_client=None` 贯通、链上每 entry 各建独立客户端）+ 端到端 2 项（归因全链跑通且 provider 收到已关闭真实客户端 / provider 拒绝时返回 False 并登记原因），**摘除修复后 7 项全红**验证回归有效性

- rf-624 已修复（2026-10-07，v0.12.6 发布后自查，当批修复）：`scripts/check-version-consistency.py` 的 `_auto_fix_header` docstring 含裸 `\s` 转义 → 非 raw 字符串下每次导入/运行打印 `SyntaxWarning: invalid escape sequence '\s'`（py3.12+），污染终端与 CI stderr（全仓扫描仅此一处）；修复 = docstring 改 raw 前缀（顺带 `[ \t]` 显示由真实 TAB 还原为字面 `\t`）；回归 = 以 `warnings.simplefilter("error", SyntaxWarning)` + `compile()` 锁定脚本可无警告编译（同批自纠：本条回归测试类的 docstring 初版亦含裸 `\s`，由提交前钩子回放段告警捕获，已同步 raw 化）
- rf-625 已修复（2026-10-07，v0.12.6 发布 publish 实战，当批修复）：`release.py publish` 组装 release subject 时未归一 `--title`——title 自带 `release: v… —— ` 前缀时拼出双前缀（v0.12.6 发布提交 `a68f2376` 即 `release: v0.12.6 —— release: v0.12.6 —— …`；tag/历史不可变故保留）；修复 = 新增 `normalize_release_title()` 剥离重复前缀（剥离后为空回退原值）；回归 = 带前缀 title 断言 subject 单前缀 + 纯描述/纯前缀变体不变
- rf-627 已修复（2026-10-08，报告管线接入，当批修复）：字段层 `apply_report_anonymization` 三处物化点接入（prepare 装配 / Excel basic 内部生成 / HTML 内部生成，off 恒等零开销；summary 折叠明细字典、DetailRow 行留渲染层拦截保持合计真值）+ 明细渲染层（summary 账户组内大类折叠、full 代码列 000XXX）+ 产物清扫（HTML 名称文本 / Excel 字符串单元格，代号编号三层同源；数值单元格不动防数字子串误伤）+ LLM 同源（明细字典匿名进提示词，约束块/新闻关键词标签按映射掩码；code 保留真值供再平衡静默/决策账本/申购状态键控链路）；修 `_anonymize_detail_entry` full 盈亏输出字符串致下游合计/格式化崩溃缺陷（改数值千位模糊 + 模糊值派生行内恒等 + 旧键兼容）；安全场景升级 3 模式 × HTML/Excel 产物端到端断言（XML 数字实体反转义）+ 管线接线单测 18 项；手册 §L 按实现口径改写；剩余衍生面登记 rf-628
- rf-629 已修复（2026-10-08，24h 技术债核查，当批修复）：`check-task-numbering.py` docstring 退出码声明「1 — 存在违规」与实现不符（main 走 `_checklib.report()` 实际返回 0/2；hook 版自身 0/1 为独立适配语义无误）——docstring 改「2 — 存在违规」；回归 = docstring 声明码集与 `_checklib.report` 返回值域 `{0, 2}` 一致性断言
- rf-75 已修复（2026-10-07，文件长度红线治理，当批修复）：`core/registry.py` 785 行临界（余 15 行）——按注册职责域下沉 `core/data_registry.py`（数据模块/缓存 TTL/LLM 设置键派生，441 行）+ `core/report_section_registry.py`（报告章节/导航分组/页签名称派生，335 行），`registry.py` 收敛为 62 行门面（computation/section_block 原有单入口再导出保留，导入面/测试 patch 面不变）；两域零跨域引用、`__all__` 声明契约且互不相交；`check-semantic-index` 章节 AST 解析改指持有子模块（`_SECTION_REGISTRY_PY`）；门面同一性+域契约测试 3 项

### 归档档案

- [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md) — v0.12.1 ~ v0.12.6 批次（2026-10-03 ~ 2026-10-07）
- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — v0.11.0 ~ v0.11.11  （2026-09-18 ~ 2026-10-02）
- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.20（2026-08-04 ~ 2026-09-15）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
