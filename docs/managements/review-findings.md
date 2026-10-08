# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.7-dev
> **编号源**：`rf-next = 634`（新增问题取此编号，完成后更新为 +1；已用最大 rf-633，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

> **迁出说明（2026-10-07）**：原「改进机会盘点」18 项（新功能/体验改进，非缺陷）已全部迁至 `plan.md`（plan-85 ~ plan-102，随其优先级分档管理），归档放弃清单过滤说明随迁入；本区仅保留缺陷、技术债与监控类条目，编号回收调整为 `rf-next = 627`（文件过长临界登记取 rf-626）。

> **优先级分档（2026-10-07 重排）**：**P1 高优先**（不做的风险高，尽快执行）→ **P2 中优先**（价值明确、成本可控，下批排期）→ **P3 持续监控**（文件过长触发式登记，非排期项，按距红线余量升序）。rf 编号是历史标识，分档不改号。

> **技术债来源**：rf-113 / rf-114 源自 plan-1 交互图表遗留技术债（2026-08-02 登记；代码与自动化测试已落地，余**未实测/计划内延后**项）；rf-257 源自 plan-8 Web 模式遗留技术债（2026-08-06 登记；三阶段已实现并提交，余文档核对/自审发现的代码与验证遗留项）。

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
| **rf-628** | 持仓匿名化剩余衍生面——full 模式 HTML 各章节代码列与交互图表标签（自由文本数字全局替换有金额误伤风险，刻意未清扫）、LLM 提示词持仓块代码字段（字段层为键控链路保留真值所致）、summary 模式明细以外章节的单只数值与演进快照/财报摘要/估值分位等派生章节数据集内部真值（名称面已由产物清扫全覆盖，数值/代码面未覆盖） | 按面在渲染点做结构化掩码：HTML 代码列在模板/渲染器输出点换显示值、派生章节数据契约增加展示值字段、提示词组装点对代码做结构化替换；数值面按分享场景评估是否需聚合/模糊后注入 |
| **rf-630** | scripts 退出码 docstring 契约族不齐——check-test-markers 声明「0/1」而实现走 `_checklib.report()` 实为 0/2（与 rf-629 同类实错）；check-file-length / check-style-guardrails / check-version-consistency 缺「退出码」声明节；check-requirement-trace 的 0/2 同行不成节；CLAUDE「scripts 共享设施与契约」段未涵盖 check-doc-traces 的 1=HIGH 语义 | 逐脚本补正 docstring（0/2 为基线，特例注明码义）；CLAUDE 契约段补 doc-traces 分级说明；防再犯由 plan-110 机检承接 |
| **rf-631** | perf-report.py 三处缺陷——① 报告硬编码「测试时间 2026-07-20」不随运行更新 ② Phase3「50 品种」实为 27（`_STOCKS` 仅 24 支，`[:50]` 截断）、Phase1「20 品种」实为 23（20 股 + 3 基金），文案与实际不符 ③ `generate_all_llm` patch 到 `src.python.llm.generators_orchestrator` 子模块，而调用点 `_llm_news` 为函数内 `from src.python.llm import generate_all_llm` 读包属性——patch 不生效，Phase2 实跑会真调 LLM（费用/稳定性风险） | ① 动态 `datetime.now()` ② 按 `len(holdings)` 实际出文案或扩充样本池到 50 ③ patch 改 `src.python.llm.generate_all_llm`（包属性，与函数内 import 解析点一致）；补 `_generate_holdings`/`_verdict`/报告文案单测 |
| **rf-632** | scripts 无测试/弱测试欠账——check-svg.py（307 行，字符宽度估算/容器归属/重叠判定纯函数零测）、check-test-markers.py（224 行，AST 提取/目录期望/未注册判定零测）、perf-view.py（199 行，分组聚合/趋势报告零测）、collect-test-coverage.py（`_collect` 退出码传递、`_target_files` 展开、modes 计数无直接单测，仅被 drift crosscheck 间接覆盖）；附带 check-svg `_text_box` 对缺 x/y 的 `<text>` 无防护（rect 有 try/except 而 text 无，防御不对称） | 按「纯函数优先」补测试：geom 字符宽度/容器归属/重叠判定、marker AST 提取与判定矩阵、trend 分组与空数据、collect 退出码白名单（0/5 过、非零拒收）与 modes 计数；`_text_box` 补缺失属性默认或跳过 |
| **rf-633** | check-test-markers 双源与自相矛盾——KNOWN_MARKERS 手写 42 项与 conftest `addinivalue_line` 注册集人肉同步（当前双向零漂移，但 conftest 新增标记后本脚本不知情即误判「未注册」）、EXPECTED_DIR_MARKERS 目录期望表同理；docstring「已移除的标记（如 integration）」与 KNOWN_MARKERS 实际包含 integration 家族矛盾（DEPRECATED_MARKERS 为空集） | KNOWN 从 conftest 动态提取（AST 解析 addinivalue_line），EXPECTED 与目录结构绑定注释；docstring 按现状改写（integration 现为注册标记，已移除清单以 DEPRECATED 为准） |

### P3 — 持续监控：文件过长登记表（>500 行观察 / **>800 行为硬上限必须拆分**；按距红线余量升序）

> **派生源（2026-10-05 起，人肉快照退役）**：行数与全集以 `scripts/check-file-length.py -v` 输出为真值（该输出列出全部 >500 行主程序文件）；红线（>800 行）由 `check-file-length.py --ci` 自动拦截（豁免路径与本表挂账同步），不再依赖本表人工发现新破线者。本表仅登记需跟踪/决策的文件，**触发式处理**：未逼近红线不排期，逼近时按本表拆分建议执行。
> **测试文件口径**：阈值见 `developer-guide.md`「文件膨胀阈值」表（行数 >800 警告 / >1200 红线；测试项 >80 警告 / >120 红线），**当前无挂账项**（贴线跟踪 rf-586 的拆分已完成并转入下方已解决区）；警告级全集以 `scripts/check-file-length.py -v` 为派生源，不做人肉快照；逼近红线（1200 行 / 120 项）时按「被测函数 / 场景类型」拆分为同目录兄弟分片，并同步刷新 `test-coverage.md` / `folders.md` 用例计数。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|

| **rf-626** | `llm/prompts_core.py`、`llm/generators.py`、`report/html_writer.py`、`analysis/rebalance.py` | 350 / 444 / 754 / 751 | **临界带（≥750 行）四文件登记项**；`prompts_core`/`generators` 主体已按域下沉完成（800/787 → 350/444：failure_reasons / prompts_data_blocks / prompts_review / generators_singletons 四新模块承载，两文件保留门面 re-export、消费方导入面不变，仅 4 处测试 patch 按「测试指向持有子模块」纪律改指新域）；余 `html_writer`(754)/`rebalance`(751) 在带内 | `html_writer`/`rebalance` 由 `-v` 月度复核、逼近 780 行启动拆分（方法沿用本次：域下沉 + 门面 re-export + 测试 patch 改指持有子模块） |
| **rf-86** | `cache/operations.py` | 740 | 500-800 可选优化区间（2026-10-05 脚本实测 740，较 2026-10-02 的 637 增长 103，临近 800 须关注） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-79** | `core/code_utils.py` | 671 | 维持现状（仍在 500-800 区间内聚；2026-10-02 实测 671，较登记值 542 增长 129，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-89** | `report/excel_generator.py` | 632 | **500-800 可选优化区间，增长偏快**（2026-10-07 实测 632，较 2026-10-05 的 585 增长 47——持仓基本面合并页签等增补）；暂维持现状，`-v` 按月复核 | 页签编排可进一步下沉到独立 writer（后续择机） |
| **rf-80** | `report/data_status.py` | 621 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-10-02 实测 621，较 2026-09-10 的 544 增长 77——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 556 | 维持现状（render 函数属同一渲染域；2026-10-02 实测 556，较 2026-09-10 的 521 增长 35） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 555 | **已跨入 500-800 可选优化区间**（2026-10-02 实测 555，较 2026-09-10 的 405 增长 150——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-78** | `fetcher/batch.py` | 520 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-10-02 实测 520，回落至登记值附近（rf-522 重试退避原语收编后下降）） | BatchDispatcher 本身内聚，可维持现状（不拆） |

## 已解决问题

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
