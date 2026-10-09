# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.6]**（2026-10-07）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.7-dev] - 开发中（未发布）

- **功能/规则**：**三项章节类实验转正入报告章节与增强组**——`holding_change_review` / `whatif_trade_cost` / `event_window_impact` 按「移出实验组、目标组按功能形态选（章节/页签类→报告章节与增强组，默认关）」单批迁入 `GROUP_REPORT`（章节类形态同构，分批反而拉长面板编号抖动窗口；声明位不动 → 转正三项落报告块块首 29-31、既有报告项 32-41 不位移）；启用记录已积累（三项各 4 次，最近 2026-10-09）且产物经报告浏览器实测；注册表现状 **34 项 = 实验 5 / 常规 16 / 报告 13**，TUI 面板编号重推导（实验 8-12 / 常规 13-28 / 报告 29-41），`--experiment` 取值域与报告自述、启用统计随实验组身份自动移除；同步 features.py 注释、requirements §11.5 计数与 R-WIF-13/R-HCR 措辞、developer-guide 转正判据首例注记、technical §1.8.11 白名单口径（51 键）、三份手册与 how-to-config/【P】说明/【how-to-start】面板组名/folders 行注、test_config_edit 死常量清理；测试同步（分组断言改报告组 + config 访问器同源不变式改写），定向 1069 项通过 | plan-83

- **测试/工程质量**：**报告与 Web 浏览器验证方法成文入档 + 自动化实测**——新增 `docs/plan/report-browser-verification.md`（六项拆分：可自动化子项 headless Chromium 148 + Node 22 CDP 一键复跑，①②2.4③3.1⑤报告⑥ 实测全部通过/记录，④微信真机留人工步骤 + §5 复验清单）与 `docs/plan/web-browser-verification.md`（五类 37 断言 33 过/2 不过/2 人工 + smoke-web 11/11，全程 0 次真实 POST /api/runs）；rf-113 状态→仅余 ④ 微信真机（+ Safari/Ctrl+P 抽验），rf-257 状态→①②⑤过/③部分/④ 375px 不过（根因入 rf-644）；同批登记 rf-644（Web 375px 横向滚动：radio 路径文案不可断行 + select 溢出视口 + whatif 文件输入内在宽）、rf-645（调试页 375px 溢出 + afterprint 恢复不精确，均不影响报告产物）、rf-646（事件窗缺需求条目） | rf-113

- **功能/规则**：**bg=2 梯度泛词否决表**——`_GENERIC_TOKENS = {ai, etf, cm, gb, ce, pcb}` 不作专名证据（锚点 7.8 万对量化：靠这些词过闸的 bg2 合并 104/209 为跨主体误合并主力；`CPI/PPI/IPO/AMD` 类真发布会/公司缩写保留，长度一刀切因误伤半数真合并而弃用）；单源原语 `proper_noun_tokens`/`has_proper_noun_token` 供生产条件与校准展示面同源引用，词表入规则指纹自动分时代；校准复跑 bg2 209→146、cross_skip +63 精确互补、其余分支零扰动；回归 5 项 + dedup 相邻 120 项全绿 | rf-643

- **分析/记录**：**新闻去重阈值校准判读（2026-10-09）**——锚点 7.8 万唯一标题对达校准节奏（跨源 17,486 / 同源 54,407）；判读：`_CROSS_BG2_RATIO` 0.375 不降（114 含专名候选抽读 10 条仅 1 条真漏判，误合并静默丢稿代价不对称）、cross bg=3 边界 775 条不抬阈值（样本两可留档观察，误合并样例优先扩模板词/方向对）、锚点体积 26.8/34MB 挂观察（79%，需归档/封顶机制）；附带发现 bg2 存量泛短词误合并（etf/gdp 过闸）待量化收紧 | rf-642

- **工程质量/工具**：**测试计数轻量回写开关**——`collect-test-coverage.py` 新增 `--update-docs`：按本次快照回写 `test-coverage.md` 计数行（反引号标记行 + 已映射标签加粗行，比对域与 `check-doc-drift` 计数核对**同构**、复用其行匹配原语，写后必过 `--with-test-count`）与 `folders.md`「测试用例」行；只改数字保粗体/千分位/后缀、幂等、收集非 0/5 跳过回写；快照单源 `_build_snapshot()`（与输出分节同出一份，同名键覆盖次序对齐子进程 stdout 解析）。实施收尾刷计数不再需要整跑 bench（流程纪律维持 bench 仅发布刷新/换机）；文档触点 developer-guide ×4、CLAUDE 发布刷新句、folders 目录树同步；回归 7 项 | rf-641

- **兼容/守护**：**Windows 钩子日志回放乱码修复**——pre-commit 十守护经 `run_bg` 重定向落盘，中文 Windows 上 Python 按 locale ANSI（cp936）编码，UTF-8 终端回放成乱码（前台直打正常、回放段落乱码的分界与 `WriteConsoleW` vs 文件落盘吻合）；修复 = 钩子 `export PYTHONUTF8=1` + `scripts/_checklib.py` 导入时把非 UTF-8 的真实 stdout/stderr 收敛到 UTF-8（已 UTF-8 / `StringIO` 桩零改写），守护详情在 Windows 可读；回归 4 项 | rf-640

- **工程质量/守护**：**单文件行数红线体系三域定档（主程序/脚本/测试）**——`check-file-length` 检查域扩到 `scripts/` 递归全集（警戒 400 / 红线 1000，含包内子模块），主程序硬上限 800 → 1000（警告 500 维持），测试 800/1200 维持；阈值与警戒区收敛为 `_LIMIT_BY_KIND` / `_WARN_BY_KIND` / `_HINT_BY_KIND` 三域单源。域内最大单文件 `factor_zoo_eval.py`（1595 行）按「评测核心 / 阶段编排 / 判定书」拆为 `scripts/_factor_zoo/` 包（catalog/probe/metrics/stages/report 五模块 342/228/562/410/135 行，入口仅留 CLI 与原面 re-export，既有 40 项测试零改动），CLI 冒烟（`--help` + catalog 阶段落盘）通过；边界/三域收集/脚本警戒区新增 4 项用例。决策与理由记入 technical.md 约束 C28「大文件红线体系（主程序/脚本/测试）」，developer-guide 阈值表/门禁注记/脚本表、CLAUDE 守护描述与 review-findings P3 口径同步 | plan-113

- **工程质量/缺陷**：**计数核对守卫功能域表静默跳过修复**——`--with-test-count` 只识别反引号标记行，`test-coverage.md` 功能域表的中文加粗标签行不匹配即被「未收录名」静默跳过，实测该表 4 行过期（报告生成 / LLM 智能分析 / 配置管理 / 核心基础设施）长期无人核对；修复：标签↔标记映射与 `collect-test-coverage` 功能域聚合**单一来源**（collect 侧同对象引用防双处漂移）、功能域章内**未登记标签**与映射集**缺行**一律报出（章外加粗行不属核对域）、「端到端业务场景」聚合行显式别名映射父标记、功能域行标签与单源对齐；同批刷新该表 11 行过期计数与测试用例总数；回归 7 项（缺行反查按映射集动态遍历、不写死条数） | rf-639

- **测试/缺陷**：**类作用域 fixture 模块级化**——设计 token 契约测试的两个类作用域 fixture 以实例方法形式定义在测试类内，全量套件稳定输出 2 条 pytest 弃用告警（后续 pytest 版本移除该形式），提升到模块级（作用域保持 class、仍按类复用）后 `-W error` 下 7 项全绿；全仓类作用域 fixture 仅此一处 | rf-638

- **测试/缺陷**：**网关展示文案钩子补回归覆盖**——上一条分层修复新增的 `register_circuit_text()` / `circuit_text()` 缺两支覆盖：上游未注册按「正常」降级的缺省分支、展示原语必须经网关取文案的路径（后者无断言则回退成直连上层也测不出），补 3 项并实测「回退即红」；同轮 36 小时技术债核查其余维度全净——窗口 43 提交新增 789 个 def/class 全部落在有测试文件的模块、无新增 TODO/FIXME/抑制标记、测试域脚本加载样板迁移后无死路径常量与残留样板、工作区无临时产物残留；调仓模拟产物无匿名化层为已登记待处理项，主报告相关性矩阵列头真码由边界安全兜底覆盖、不构成泄漏 | rf-637

- **工程质量/缺陷**：**历史痕迹守卫恢复有效扫描**——`check-code-traces` 实现拆包至 `scripts/_traces_code/` 后 `config.REPO_ROOT` 路径深度少算一级（落成 `scripts/`），`SCAN_DIRS` 四个路径全部不存在 → 遍历逐个跳过 → **守卫恒 exit 0 空转**，CI `guards` 档与 pre-commit 十守护连同它空跑多日；同时规则定义字面量（`R11`/`F-1`/`第X章`/`rf-117` 的模式与示例）在拆包后落进 `scripts/_traces_code/`，而 `_is_tool_self()` 只按 `check-*.traces.py` 文件名豁免，规则载体自身成了头号命中源。修复：① `REPO_ROOT` 改按 `parents[2]` 取仓库根（代码内注记层级深度）；② 新增 `RULE_CARRIER_DIRS` 按**目录**跳过规则载体（与文件名无关）；③ 裸版本号模式加 `(?<![\\d.])…(?!\\.\\d)` 逐 token 排除 IPv4 内嵌子串（`127.0.0.1`/`0.0.0.0` 的 `0.0.x` 是地址片段不是版本号，不整行放行、同侧真实版本痕迹照报）；④ `_magic_excludes()` 收录真实领域值（`F10` 基金费率页、`P0~P4` 门禁档位与公式价格符号、`T0` 事件窗口锚定、`S0`/`S1`/`MV0`、`Phase1`/`Phase3`、`E1~E3`/`W1~W2` 样式护栏编号）并修正与门禁领域值冲突的暗号样例；⑤ **分层倒置实质修复（不加豁免）**：`core/system_info.py::circuit_display` 的函数内 lazy import 上层改走 core 网关新增 `register_circuit_text()`/`circuit_text()`（晚绑定回调，展示层不反向 import 上层、不复制上游 URL→域名归一规则，既有 patch 用例仍生效）；⑥ 其余 40 个被改文件为注释/文档串改写（任务编号、约束代号、历史叙述、迭代标记、章节暗号、待办误报、语义暗号），逐文件 **AST 归一化比对**证明代码语义零变动；⑦ 守卫自证回归：扫描目录存在性硬断言 + tmp 种入式样本正/负双探针 + 载体目录跳过而同字面量在扫描域内仍报 + 领域值不误伤且同侧暗号照报 + 统一 CLI 面（`--help` 含 `-v`/`--ci`、`add_common_args` 即 `_checklib` 同一对象）；基线 167 条 → **0**，`--ci` exit 0 | rf-636

- **工程质量/契约**：**check-code-traces 采纳 _checklib 统一 CLI 面**——手写 `-v/--verbose` + `--ci` argparse 换成 `_checklib.add_common_args`，本地 `rel` 改共享 `rel()`（别名 `rel_path`），自身 0/1/2/3 分级退出码语义保留；`check-script-contract.py` 四条规则**全部归零**（原唯一 finding 即本项），`_checklib` 契约 docstring 中 code-traces 分级描述与实现不符一并改正 | plan-114

- **工程质量**：**收集计数谓词与模式注册表单源化**——`_test_runner/modes.py` 新增 `mode_marker_expr()`（顶层 `marker` 缺省时回落到首阶段 marker）与 `compile_marker_expr()`（复用 pytest 自身的 `-m` 表达式求值器，把表达式编译成「对 marker 名集合」的谓词，空表达式恒真）；`collect-test-coverage.py` 删掉 15 项手写 lambda 字典与「双处定义——marker 变更必须同步本字典」的纯人肉纪律注释，改为按 `MODES` 键集现场编译（`all` 已由「总收集: N」表达、`live` 被默认收集宇宙排除，两项显式豁免并在脚本内注记理由，模式增删自动跟随），同步删掉只服务旧字典的 `_sel`；表达式语义由真值表参数化用例与注册表回读用例锁死，计数与 `-m` 实跑同源（对拍：`unit`/`not unit and not live`/`unit_scripts`/`scenario` 谓词计数与 `pytest -m` 收集数逐项相等） | plan-112

- **工程质量/重构**：**测试域脚本加载样板收敛为共享实现**——新增 `src/test/_script_loader.py`（`load_script(name, module_name=None)`：按文件名/子路径加载 `scripts/` 下脚本，模块名缺省由文件名派生、可显式覆盖，每次调用重新执行返回新实例，注册进 `sys.modules` 保住 `@dataclass` 按 `cls.__module__` 回查），33 个测试文件的 4 种自建样板（模块级 `_load_script(name)` / 无参固定脚本 / 路径+模块名两参 / `_load_checklib`·`_load_release_module`·`_load_modes`·`_load_runner` 自定义名）全部迁移，顺带清 38 处失效路径常量与 importlib 导入，净 −362 行；样板唯一性由 `test_script_loader.py` 机检（除 loader 外不得再出现动态加载样板、不得再定义同名本地加载器），新测试强制复用共享 loader | plan-111

- **工程质量/契约**：**scripts 顶层脚本契约机检上线（观察期）**——新增 `check-script-contract.py` 四条规则：退出码 docstring 声明 ⊆ `_checklib.report` 返回值域 {0,2}（白名单：code-traces 0/1/2/3、doc-traces/svg/version-consistency 的 1=HIGH/环境缺失/事实源不可读）、`check-*` 须统一 `add_common_args`（-v/--ci）、文本 I/O 显式 encoding（内建 open 非二进制模式 / Path.read_text·write_text / subprocess text=True，AST 全口径）、顶层脚本须被 `src/test/` 测试按文件名引用（一次性探测工具豁免）；同批把 `check-version-consistency` 手写 argv 解析改 argparse + `add_common_args`（补 `-v`）；当前唯一 finding 为 `check-code-traces` CLI 面（plan-114 收口后归零）；测试 39 项 | plan-110

- **工程质量/缺陷**：**测试标记清单改由 conftest 派生**——`check-test-markers` 的 `KNOWN_MARKERS` 由手写 42 项改为 `registered_markers()` 对 `src/test/conftest.py` 的 `addinivalue_line("markers", …)` 做 AST 提取（多行调用与相邻字面量拼接天然处理），conftest 新增/删除标记自动跟随；已实测真实漂移：`cassette` 早已注册却不在手写清单内（43 vs 42），裸属性写法会被误判「未注册」；`EXPECTED_DIR_MARKERS` 补齐 5 个含测试却无期望的目录（`unit/cache`·`unit/startup`·`unit/web`·`scenario/perf`·`scenario/security`，原静默不查）并加目录结构绑定注释，`src/test/unit/conftest.py` 的 `_DIR_TO_MARKER` 同步补齐 cache/scripts/startup；docstring 删去「已移除的标记（如 integration）」与现状矛盾的表述；回归 = 27 项，含期望表↔目录、提示表↔期望表的结构性双向绑定断言 | rf-633

- **测试/缺陷**：**四个零测脚本补齐直接单测**——`check-svg`（字符档位/锚点包围盒/最小面积容器归属/越界·贴边·重叠·越画布四类 finding/同列底部提示/`geom` 退出码 0·2）、`check-test-markers`（AST 三来源提取/`_get_relative_dir`/八类判定分支）、`perf-view`（均值极值降级/阶段跨记录合并/分组过滤·截尾·排序/趋势报告结构与过滤参数）、`collect-test-coverage`（收集退出码 0/4/5 原样传递与插件记录清空、`_target_files` 目录展开与 live 套件排除、模式与子标记计数、`main()` 出口 0/5 正常·非零原样 `sys.exit`）共 87 项；同批修复 `check-svg._text_box` 缺 x/y 时直接崩溃（rect 有 try/except 而 text 无，防御不对称 → 补同口径跳过）与 `perf-view` 明细时间列 `[-16:]` 截掉年份首位（`2026-01-01 10:00:00` → `6-01-01 10:00:00`）→ 改 `[:16]`；回归验证 = 摘防御 3 红 / 回退时间列 2 红 | rf-632

- **工具/缺陷**：**性能基准报告三处缺陷修复**——测试时间随运行时刻动态生成（`_test_time_text`）；持仓规模文案按实际样本派生（新增 `PerfSample` + 账户口径 `_sample_of`，概述/表格/结论三处同源出数，港股不再被按代码位数误计为基金），股票样本池扩到 50 支使 `_PHASE3_STOCK_COUNT` 被覆盖、`[:N]` 静默截断消失；LLM mock patch 目标改为包属性 `src.python.llm.generate_all_llm`（与 `_llm_news` 函数内 import 读取点一致）+ 返回值对齐 `generate_all_llm` 8 元组契约（经核查 both 路径 `enable_llm=False`、原 patch 本就无效）；回归测试 18 项（摘除修复后 16 项红） | rf-631

- **工程效能/缺陷**：**scripts 退出码 docstring 契约族补正**——`check-test-markers` 声明「0/1」而实现走 `_checklib.report()` 实为 0/2；`check-file-length` / `check-style-guardrails` / `check-version-consistency` 缺「退出码」声明节（后者 usage 还错写「不一致退出 1」）；`check-requirement-trace` 的 0/2 同行不成节；CLAUDE「scripts 共享设施与契约」段未涵盖 `check-doc-traces` 的 1=HIGH 分级——逐处补正，并把分级退出码特例（code-traces / doc-traces / svg / version-consistency 事实源不可读）写进契约段与 plan-110 白名单；防再犯由 plan-110 机检承接 | rf-630

- **报告安全/缺陷**：**持仓匿名化代码面改在渲染点掩码**——HTML 自由文本清扫剥离代码（原实现把真码并入整份 HTML 子串替换，与「数字串全局替换有金额误伤风险、刻意不在 HTML 自由文本换代码」的前提相悳，实测 `1600519.00` 会被改成 `1000XXX.00` 破坏金额与 JSON 数值；summary 模式映射不含代码，明细以外章节真码裸奔）；新增 `build_code_display_map` / `mask_holding_code` / `code_masking_enabled` / `mask_code_text`（**边界安全**精确键替换，相邻非数字/小数点/冒号才认作独立代码 token）与模板 `anon_code` pass_context 过滤器，9 份 partial 代码列在渲染点键控折叠（列表型 codes 逐项 map），演进图表 `top_holdings` 代码在数据层折叠，LLM 提示词组装点折叠且代码白名单块改写为「真码一律不写」反幻觉约束；数值面评估：派生章节数值为公开市场/财报数据、保留原值，仓位面已由明细层 full 千位模糊 / summary 大类聚合覆盖；回归 = 产物级 HTML 真码断言 + 匿名化映射/边界安全替换/过滤器/图表数据层/提示词五组单测，手册 §L 改写 | rf-628

- **LLM/缺陷**：**串行后置模块 http_client 缺省兜底**——`run_holding_change_review` / `run_self_review` 全链不注入 http_client，None 直达 provider 层 `assert client is not None` 秒败且被 `call_llm` per-provider `except` 吞成「provider 异常」整链连环失败（实测四 provider 各 ~2ms、归因整章静默丢失）；修复收敛在多链与 legacy 唯一汇聚点 `call_single_provider`：None 且 provider 受支持时经 `core.http_client.make_http_client` 自建一次性客户端、`with` 用后关闭（守 HTTP 客户端统一工厂约束）；回归测试 9 项（漏斗 7 + 端到端 2，摘除修复后 7 项全红） | rf-634

- **报告呈现**：**报告空状态与降级呈现统一**——占位样式归并三档族（章节 `empty-section` / 单元 `empty-note` / 图表 `chart-empty-note`）：原 `placeholder-note` 同义修饰类并入 `empty-note` 基底（20 处双类清零，两模板定义合并）；文案二元口径落地（合法空「暂无+具体对象」——summary 指数占位双端改「暂无指数数据」、降级空「数据不可用：<原因>」——数据源状态行×2 与历史图空态加标准前缀，与 data_freshness 词根同源）；豁免表（哨兵值/拼接缀/条件说明句）入档；状态→观感映射与空态中性分工约束入 DESIGN Data States 节（含 20 partial 核对结论）；脆窗 print 断言改括号平衡解析；契约测试 11 项 | plan-109

- **工程效能**：**设计护栏机检上线（观察期）**——`scripts/check-style-guardrails.py`（复用 `_checklib` 契约，`-v/--ci`、退出 0/2）：E 级判 finding（护栏 3 强调色越权——品牌蓝 hex 集从 `:root` 强调系 token 动态提取、护栏 5 明暗同步——dark 覆盖变量根缺、Colors「同名对齐」段双面 token 表↔实现双向对表）；W 级观察统计不判 finding（护栏 1 裸色值 129 处 / 护栏 2 圆角档外 7 处，`-v` 明细供分诊）；清理遗留 3 处品牌蓝 hover 字面量与工作台 `--radius:12px` 出档值（104 残留，收敛 8px）；测试 14 项；**观察期未入钩子与 CI**，稳定后评估入域；DESIGN 护栏节/圆角档同步落地标注 | plan-108

- **报告呈现**：**响应式断点与触控契约落地（移动阅读一等场景）**——三面（主报告/What-if/Web 工作台）断点收敛四档族（旧 899/900/375 残值零；toc 侧栏边界归 1024/1023 配对）；宽表首列冻结（sticky + 斑马/hover 底色同步 + 打印归位）；触控目标 ≥44px（≤768 触屏档强制含表单控件；折叠组头/目录/主题/回顶浮动钮全局 44）；iOS `text-size-adjust` 防字号放大；What-if 补 768 触控/480 紧凑两档；契约测试 12 项（断点⊆DESIGN 档族/旧值零残留/冻结与打印归位/触控尺寸，print 块括号平衡解析）；whatif 关态 golden 基线随样式合法刷新 | plan-107
- **报告呈现**：**阅读版式与数字排版升级**——两模板（主报告 + What-if）201 处字号字面量收敛为 8 档字阶 token（`--fs-h1/kpi/h2/h3/body/table/table-sm/footnote`，图标 >24px 豁免）+ 3 档行高 token；表格全局 `tabular-nums` + th/td 行高档 + body 行高 1.7；正文行长控制（`.section p` 78ch，宽表/图表保持章节横滚）；章节节奏归档（section-title/block-title 阶外值入档）；WCAG AA 亮色修值（muted `#888`→`#6b6b6b`、faint `#999`→`#6e6e6e`、loss `#009900`→`#007a00`，两模板同步；暗色全套已达标）；What-if 模板补品牌蓝/字体栈 token 化（三面统一）；契约测试 18 项（字阶就位/游离字号零残留/数字排版/78ch/亮暗对比度动态计算），whatif 关态 golden 基线随样式合法刷新 | plan-106

- **设计体系**：**工作台暗色主题与组件状态矩阵补齐**——`style.css` 新增 `[data-theme="dark"]` 暗色变量块（与报告暗色世界同值；品牌蓝不调）+ 组件亮色硬底暗色适配（上传区/正式选项/警示条）；`index.html` 样式表前防闪脚本 + 导航条右侧主题切换钮；`main.js` 主题模块与报告 theme.js **同键共享**（investor-theme-dark，偏好跨页一致）；组件六态矩阵落地（全局 focus-visible 兜底、按钮 aria-busy 进行中态闭环提交→生成结束、字段错误态、空态 `.empty-note` 与报告同名同义、链接态）；4 处空态挂点归类；静态断言测试 10 项（存储键与报告 theme.js 动态对表），手册 §2 补主题切换说明 | plan-105

- **设计体系**：**双面设计 token 同名对齐**——跨面共享角色（surface/ink/border/状态/强调/焦点/字体栈）在 HTML 报告与 Web 工作台两面 `:root` 同名定义（对表验收 `test_design_tokens`）：报告侧新增 `--primary/--primary-hover/--focus/--font-stack` 并将 14 处模板 + 9 处 partial 品牌蓝裸值 token 化（Chart 域定义与 JS fallback 豁免）、`--status-ok/warn/info` 改名 `--ok/warn/info`、body 字体栈变量化；工作台侧 `--color-*` 104 处引用切角色名，旧名保留一版 `var()` 兼容映射；同名跨面值按各自明暗世界取值（验名不验值）；DESIGN.md Colors 表同步终态 | plan-104

- **报告呈现/隐私**：**持仓匿名化接入报告管线**——`anonymization.mode` 三档（code_display/full_anonymous/summary）落地：字段层 `report/_report_helpers.apply_report_anonymization` 在明细三处物化点（prepare 装配 / Excel basic 内部生成 / HTML 内部生成，off 恒等零开销）成对匿名明细字典与 DetailRow（同一代号映射；full 数值千位模糊且盈亏/收益率由模糊值派生保持行内恒等、代码保留真值供再平衡静默/决策账本/申购状态等键控链路）+ 明细渲染层（summary 账户组内大类折叠、full 代码列 000XXX）+ 产物清扫（HTML 名称文本 / Excel 字符串单元格 `mask_workbook_text`，只动字符串不动数值防数字子串误伤）+ LLM 同源（约束块与新闻关键词标签按映射掩码）；修 `_anonymize_detail_entry` full 盈亏输出字符串致下游合计/格式化崩溃缺陷；安全场景升级产物端到端断言（3 模式 × HTML/Excel 无样例真名）+ 管线接线单测 18 项；手册 §L 按实现口径改写，剩余衍生面登记 rf-628 | rf-627

- **工程效能**：**中央注册表按注册职责域拆分**——`core/registry.py`（785 行临界，余 15 行）下沉 `core/data_registry.py`（数据模块/缓存 TTL/LLM 设置键派生，441 行）+ `core/report_section_registry.py`（报告章节/导航分组/页签名称派生，335 行），`registry.py` 收敛为 62 行门面（computation/section_block 单入口再导出保留，导入面与测试 patch 面不变）；两域零跨域引用、`__all__` 声明契约互不相交；`check-semantic-index` 章节 AST 解析改指持有子模块；门面同一性+域契约测试 3 项 | rf-75

- **工程效能**：**临界文件按域拆分**——`llm/prompts_core.py`（800→350）按职责下沉三子模块（`failure_reasons` 失败原因常量 / `prompts_data_blocks` 上下文数据块与格式化辅助 / `prompts_review` 自审与持仓复盘提示词），`llm/generators.py`（787→444）按生成器域下沉 `generators_singletons`（单例四生成函数）；两文件保留门面 re-export（消费方导入面不变），仅 4 处测试 patch 按「测试指向持有子模块」纪律改指新域；llm-technical/folders 同步 + 门面同一性回归测试 4 项 | rf-626

- **工程效能/发布**：**版本一致性 `--fix` 不再吞空行 + 消除脚本 SyntaxWarning**——`_auto_fix_header` 行首空白类改同行字符类（原 `\s` 含换行，MULTILINE 下吞掉版本头前空行，developer-guide 受损已恢复），docstring 改 raw 串消除 invalid escape 警告；回归补「空行保留 + 跨行不误判 + 无警告编译」用例 | rf-624
- **工程效能/发布**：**`release.py publish` 归一化 `--title`**——新增 `normalize_release_title()` 剥离 title 自带的 `release: v… —— ` 前缀，防双前缀 subject（v0.12.6 发布提交实测出现，历史不可变，修复防再犯） | rf-625
- **运行体验**：**生成进行中阶段 ETA 预估**——`core/perf` 新增同阶段历史中位数预估 `estimate_stage_eta`（最近 20 次运行同名阶段减已耗时、严格同报告类型筛样本、无样本与读档/计算异常一律静默降级）与阶段状态唯一格式器；`PerfCollector` 可选阶段广播回调（回调异常隔离，basic/both/full 三处管线构造点零调用点改动）；`ProgressReporter.stage_progress` 基类单一实现，CLI verbose / Web / TUI 同源（瞬时阶段不刷屏、历史不足先静默后仅显已耗时） | plan-97
- **运行体验**：**主菜单页头常驻状态仪表盘**——新增 `tui/status_line` 五项本地单源组装（上次报告时间 ← perf 历史末条 / 缓存过期数 ← 与 [4] 同口径统计 / 数据新鲜度 ← 最新价格缓存数据日期与自然日龄 / 降级源数 ← 健康历史末条 fail_count / LLM 状态点 ← llm_status 同源 ●○），逐项异常降级为「—」、整行永不抛、TTL 45s 记忆化随页头重绘零外部调用（新鲜度刻意不取交易日历：日历缓存未命中会走 akshare 触网），`print_header` 标题下常驻一行并附详情菜单指引 | plan-96
- **报告呈现**：**月度收益日历（近 24 个月年 × 月红绿格）**——`analysis/monthly_returns` 按月聚合（月末/上月末−1、首月 inception 基线、截窗保真实上窗基线、胜亏平与最长连亏统计；as-if 现行 + realized 预留的双口径并排结构），`history_data.monthly_returns` 三处返回点单源注入；HTML 端纯表格热力格（正值红/负值绿，无 JS 天然具备无脚本回退）+ Excel 页签第四区块（FMT_PERCENT 小数 + profit_font 红绿字 + 口径统计说明行），区块注册表/矩阵/语义表/需求/手册/faq 目录树同步 | plan-86
- **运行保障**：**生成中断一致性收口**——新增 `report/run_integrity`（`guard_run` 装饰 `generate_report`，ContextVar 线程隔离）：KeyboardInterrupt 安全落点清理未完成临时产物 + 进度通道提示「已写盘/未完成已丢弃/已清理临时文件」明细 + `status=interrupted`（含 `interrupted_stage`）落 perf_history（`save` 幂等一次一录，页头状态行显「（已中断）」不误判成功）+ 健康检查收敛；HTML/Excel 产物改同目录 `.tmp` + `os.replace` 原子落盘（中断不再产生半写文件，遗留预清扫），收口不吞 KI（CLI 退出码 130/菜单「操作已取消」语义不变）；新需求 R-OUT-13 + faq 中断问答改写 | plan-98

（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.6（2026-10-03 ~ 2026-10-07）
- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12 + v0.12.0（2026-09-15 ~ 2026-10-03）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12)
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
