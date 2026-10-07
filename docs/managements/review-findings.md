# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.5-dev
> **编号源**：`rf-next = 616`（新增问题取此编号，完成后更新为 +1；已用最大 rf-615，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> **派生源（2026-10-05 起，人肉快照退役）**：行数与全集以 `scripts/check-file-length.py -v` 输出为真值（该输出列出全部 >500 行主程序文件）；红线（>800 行）由 `check-file-length.py --ci` 自动拦截（豁免路径与本表挂账同步），不再依赖本表人工发现新破线者。本表仅登记需跟踪/决策的文件。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 743 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-10-05 脚本实测 743，较 2026-10-02 的 716 增长 27——plan-50 财报域槽位/plan-57 等注册项增补） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 520 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-10-02 实测 520，回落至登记值附近（rf-522 重试退避原语收编后下降）） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 671 | 维持现状（仍在 500-800 区间内聚；2026-10-02 实测 671，较登记值 542 增长 129，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 621 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-10-02 实测 621，较 2026-09-10 的 544 增长 77——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 556 | 维持现状（render 函数属同一渲染域；2026-10-02 实测 556，较 2026-09-10 的 521 增长 35） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 555 | **已跨入 500-800 可选优化区间**（2026-10-02 实测 555，较 2026-09-10 的 405 增长 150——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-86** | `cache/operations.py` | 740 | 500-800 可选优化区间（2026-10-05 脚本实测 740，较 2026-10-02 的 637 增长 103，临近 800 须关注） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 585 | **已跨入 500-800 可选优化区间**（2026-10-05 脚本实测 585，较 2026-10-02 的 574 增长 11——持仓基本面合并页签等增补）；暂维持现状 | 页签编排可进一步下沉到独立 writer（后续择机） |


### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

### P2C — 测试文件膨胀（阈值：行数 >800 警告 / >1200 红线；测试项 >80 警告 / >120 红线）

> 阈值见 `developer-guide.md`「文件膨胀阈值」表；本表登记已越线或临近越线的测试文件（2026-10-05 实测；全集清单以 `scripts/check-file-length.py -v` 为准，>1200 行红线由 `--ci` 拦截）。

> **当前无挂账项**（贴线跟踪 rf-586 的拆分已完成并转入下方已解决区）。警告级全集（测试 >800 行 / >80 项）以 `scripts/check-file-length.py -v` 为派生源，不做人肉快照；逼近红线（1200 行 / 120 项）时按「被测函数 / 场景类型」拆分为同目录兄弟分片，并同步刷新 `test-coverage.md` / `folders.md` 用例计数。

### P2D — 报告结构与组织优化（Excel × HTML 双端同步）（2026-10-07）

> 触发：2026-10-07 报告结构专项自审（章节注册表单源 / 导航分组 / 双端一致性契约 / 模板组织四路核查）。均为未修复项；凡涉及结构与组织的改动，修复时须 Excel 与 HTML 两端同步考虑，不得单端落地。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-601** | HTML 目录导航元数据是 HTML 端私有硬编码，与注册表并列为第二事实源：`html_writer_nav.py` 的 `_NAV_GROUP_LABELS`（基础信息/基金深度分析/行动建议/历史/LLM/附录 六组）、`_SECTION_NAV_GROUP_MAP`（章→组映射）、`_LLM_SUPPORTED_SECTIONS`（🧠 标记集合）三张表都不在 `_REPORT_SECTION_DEFAULT` 里——新增章节须两处注册，漏配时静默回退「基础信息」组不报错；且 LLM 口径存在三套并行集合（注册表 `type=llm`、🧠 集合、`LLM_MODULE_GATED_SECTIONS`），边界各异（如 `news_correlation` 有 🧠 但 type=news、`llm_usage` 属附录组但带 🧠）；Excel 端完全拿不到分组信息（rf-602 的前置依赖） | 注册表条目增 `nav_group` 字段（🧠 标记并入或由注册表字段派生），HTML 三张表改为注册表派生或删除；补「注册表键集 ⊆ 分组映射键集」防漂移测试，现有散点断言（`test_financial_indicator` / `test_schedule_replay_wiring` 等处直接 import 私有常量比对）收口迁移；入库时一并评审分组归属是否符合阅读流（如「持仓基本面」现归附录组、与基金深度分析组仅隔数据源矩阵一章） |
| **rf-602** | Excel 端导航能力与 HTML 三件套不对等：HTML 有左侧 TOC 分组目录、顶部横向章节导航、每章「回到顶部」链接；Excel 三者皆无——全库无 `tabColor` 页签颜色（六组分组在 Excel 端零体现）、汇总页无章节清单、各页签无「返回汇总」跳转，最多 19 个页签只能靠底部标签栏线性翻找 | 依赖 rf-601 分组同源后双端落地：① 页签 `tabColor` 按 `nav_group` 上色（六组六色，与 HTML 目录分组一眼对应）；② 汇总页顶部加「章节导航」区（Excel 内部超链接指向各页签，按可见章节动态生成，与 HTML TOC 对应）；③ 各页签标题行下加「返回汇总」链接（与 HTML「回到顶部」对应）；补双端导航一致性测试（TOC 分组 ↔ 页签颜色、可见章节集 ↔ 导航链接集） |
| **rf-603** | 章节显示名三处（实为四条路径）维护：① 注册表 `_REPORT_SECTION_DEFAULT[].name`——Excel 页签标签 `f"{n}.{name}"` 与 HTML 导航由此取；② `_REPORT_SHEET_NAMES` 14 键子集——Excel 章内 A1 标题行走 `get_report_sheet_name()`，LLM 章另走 `get_llm_module_name()` 第四条路径；③ 模板正文硬编码中文标题 14 处（`{{ section_numbers['summary'] }}、投资分析汇总` 只动态了序号）+ 5 个 partial 内同款硬编码。现有测试（`test_sheet_names_match_section_names`、导航↔section-title 一致、section-title 格式）能把漂移打红，但一次改名需手工同步 3-4 处，测试只能事后报错、改名过程没有单一真值 | 模板与 partials 标题改为 context 注入动态章名（渲染层从注册表一次性构造 `section_names`，模板写 `{{ section_names[key] }}`），改名收敛为注册表单点变更；`_REPORT_SHEET_NAMES` 降级为注册表派生视图或删除（LLM 章仍走 `get_llm_module_name`，差集显式声明）；既有三处一致性测试改为断言派生关系，防漂移强度不降 |
| **rf-604** | `src/static/tmpl/report_template.html` 3131 行单文件：报告章节中仅 5 个拆到 partials（action/evolution/holding_change/schedule_replay/fundamental_snapshot，另有新闻章内 event_impact 区块 partial），其余 14 个章节仍内联（基础信息、基金深度、LLM 分析、历史主章、附录各组），CSS/JS/正文/导航同文件；且 `check-file-length.py` 只扫 `*.py`，模板体量无任何红线监控——归档 rf-198 已开章节级 partial 拆分先例（当时 2570→2410 行），现已回涨至 3131（+721） | 按 TOC 六组继续章节级 partial 拆分（沿用 `partials/*_section.html` 命名与 `with context` 透传约定），输出零变化由 `test_html_report_structure*` 系列结构测试护航；同步 `folders.md` 目录树与行数快照；可选：`check-file-length.py` 增列 `.html` 模板观察名单（仅 `-v` 提示，不设红线，豁免与观察项显式声明） |
| **rf-605** | 双端一致性契约只覆盖「名称 + 顺序 + 集合」（`test_report_chapter_consistency`），**章内区块级**内容无契约：风格与因子 4 区块、持仓结构 3 区块、组合历史 2 区块、持仓基本面 2 区块、行动建议 4 区块等的区块清单只存在于 `technical.md` 文字描述——某端增/删/漏区块（Excel 少写一节、HTML 多渲染一块）无机检，两端内容不对等不会被任何测试发现 | 建立「章节-区块矩阵」双端契约：区块清单以数据契约/渲染注册为真值（或注册表条目增 `blocks` 字段），测试断言 Excel 写入区块与 HTML 渲染区块集合双向一致；至少先在 `technical.md` 固化矩阵表，并由 `check-doc-drift` 抽查区块计数（与既有「统计表核对」机制合流），后续再升级为代码级契约 |

### P2E — 任务执行流程耗时优化（质量 × 时间平衡）（2026-10-07）

> 触发：2026-10-07 用户反馈「每次运行任务比以前长很多」并怀疑冗余调用。实测基准（dragonball，12C16T，本轮采集）：十守护串行合计 **5.1s**（其中 `check-test-redundancy` AST 全量解析 446 个测试文件 **3.47s，占 68%**）；`check-doc-drift --sync` **4.0s**（内含 pytest 收集 9157 项 **3.4s**）；`collect-test-coverage` 单跑 3.4s；dev-verify preflight 3 守护 ≈3.9s + 测试本机 ~33s（test-coverage.md 环境耗时表）。变重时间线：pre-commit 在 2026-10-03 前仅条件触发 3 项守护，10-03 改为八守护全量（dfad7090）、10-03 增 doc-links、10-06 增 file-length，09-19 增 test-redundancy 与 dev-verify preflight——两周内多层叠加，与「比以前慢」的主观感受吻合。**优化总原则：本地降频不降级——CI guards job 恒全量兜底，任何本地分级/缓存都必须与 CI 全量成对设计**。

| # | 问题 | 修复方向 |
|---|------|----------|

## 已解决问题

- rf-600 已修复（2026-10-07）：仓库 config `report_section_order` 与章节注册表失同步 —— config 移除废弃键 `event_impact`、补 `schedule_replay`=16（18 键与注册表 19 键减 `llm_usage` 双向一致、逐键出厂同序），`validate_config` 未知模块标识升级为计 1 问题 + 内存自动清理，契约测试 `TestRepoConfigSectionOrderContract` 绕过测试隔离直读仓库 config 兜底键集漂移 + `TestReportSectionOrderAutoClean` 锁定清理，并同步 how-to-config/faq/technical「本仓库配置 N 项」镜像表述
- rf-606 已修复（2026-10-07）：同一待提交树守护重复执行 —— dev-verify 预检精简为 <100ms 任务编号快检，pre-commit 为本地守护唯一执行点、CI guards 全量兜底；回归用例 `test_test_runner_modes.py` 3 项锁定预检内容
- rf-607 已修复（2026-10-07）：P0 门禁文档三处口径矛盾 —— CLAUDE.md / developer-guide / testplan 统一为「dev-verify 手动 + 十守护由 pre-commit 钩子自动执行 + CI 恒全量兜底」，守护清单五处同源校验保持不变
- rf-608 已修复（2026-10-07）：`check-doc-drift --sync` 无条件 pytest 收集 —— 测试树指纹磁盘缓存（`DOC_DRIFT_SNAPSHOT_CACHE` 测试隔离重定向），收集冷 4.1s → 命中 0.6s；回归用例 `test_check_doc_drift_crosscheck.py` 6 项（命中免收集 / 失效重算回写 / 损坏降级 / 树指纹敏感 / 同树确定性 / 隔离生效）
- rf-609 已修复（2026-10-07）：pre-commit 十守护无条件串行 —— `check-doc-drift` 串行先行（--sync 回写）+ 其余九守护按暂存域后台并行回放，纯文档/纯代码提交不跑无关守护，CI 恒全量与同源清单校验不变
- rf-610 已修复（2026-10-07）：`check-test-redundancy` 随测试规模线性变重 —— 按文件事实缓存（size:mtime 签名 + 逻辑版本键 + 跨文件重复/死用例比对仍全集归并），冷 3.5s → 1.8s、变更文件增量 0.07s、命中 0.06s，与旧实现输出对拍逐字一致；回归用例 `TestFactsCache` 5 项
- rf-611 已修复（2026-10-07）：`check-doc-drift` 测试收集快照全树指纹重复全量 —— v2 按文件增量状态（逐文件计数账本 + 共享语境指纹变化整树全量兑底 + 影子双算连续 5 次一致才毕业进纯增量 + 失败/非零退出拒收不回写），实测 sync 快路径 0.63s、变更文件纯增量 0.87s（单文件收集 0.2s，旧全量 4.2s）、`--with-test-count` 热 0.52s（冷 3.5s 保守重算）；影子窗口内双算 ≈4.3s 与旧全量同级不回退；回归用例 `test_check_doc_drift_crosscheck.py` 重写 `TestSnapshotCountCache` 15 项 + `TestCollectTestSnapshot` 7 项
- rf-615 已修复（2026-10-07，随 rf-611 同批自查发现）：`collect-test-coverage.py` 无视 `pytest.main()` 退出码 —— 收集期校验出错（exit=4：conftest 标记纪律校验中断钩子链使 `-m not live` 过滤未执行，实测 20 个 live 项混入、总数虚增）时输出未过滤错数，会被当真值缓存并写进文档统计（rf-608 上线路径与发布数据刷新同受影响）；改为传递退出码、消费方按 rc∈{0,5} 拒收且不回写状态；回归用例 `test_nonzero_exit_rejected` / `test_no_tests_collected_exit_accepted`
- rf-612 已修复（2026-10-07）：dev-verify 双阶段重复的收集与 worker 启动 —— 两阶段合一为单轮并集 marker（布尔等价全组合枚举对拍 + 合并前后收集数 5752+155=5907 精确一致零重叠，timeout 预算 300s×2 不变，单轮报告 `report.html`，多阶段逐文件防覆盖机制保留），实测本机 37.6s → 30.1s；high 档实测无增益（31.2s、CPU×2），默认保持 medium、`--parallel high` 档可选；回归用例 `TestDevVerifySinglePhaseMerge` 3 项
- rf-613 已修复（2026-10-07）：三守护暖路径全量重扫 + 钩子串行空等 —— ① 结论缓存（`_checklib.conclusion_cache_*`：逻辑版本键 + 输入面指纹 + 原子写失败静默 + 仅 --ci 加载），--ci 冷/热输出与退出码逐字一致实测 0.59→0.043s / 0.32→0.035s / 0.10→0.031s；② 钩子读写分层：不读 folders.md 的快集+py/test 域先行与 doc-drift 并行，读 folders.md 的 version-consistency+doc 域串行后置；回归用例 `test_check_conclusion_cache.py` 10 项（三守护冷热对拍 ×3 + 输入/逻辑/结构失配矩阵 + 通过与发现双缓存 + 隔离）
- rf-614 已修复（2026-10-07）：CI guards 十守护串行 + 每 job pip 自升级 —— ① guards job 改单步后台并行回放（YAML 语法校验通过；本地原样提取块复演：成功 rc=0 十守护全回放，注入失败 rc=1 折叠 [FAIL] 分组且其余九守护照跑），暖测 0.80→0.43s、CI 冷预期 ~5.1s→~2s（test-redundancy 冷 ~1.8s 封顶，原目标 1.5s 略乐观、以实际下限为准）；② 4 处 `--upgrade pip` 移除；③ 依赖审计（十守护→仓内模块传递闭包 69 文件）确认守护经 src.python 链 import httpx 等运行时依赖 → 按 rf 规则保留 editable 安装；五处同源对拍 13 项绿

> **本迭代已修复记录（rf-579 ~ rf-599 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>


> **本迭代已修复记录（rf-568、rf-571 ~ rf-578 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>

> **本迭代已修复记录（rf-563 ~ rf-570 批次）已随发布迁移至** [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)；主文件只留未修复项与迁移索引。
>
>
> **迁移说明**：已完成批次摘要（rf-557 ~ rf-562）已于 v0.12.1 发布（2026-10-03）随档迁入 [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md)，本文件只保留未完成项与归档索引；更早批次（rf-541、rf-542 ~ rf-556）见 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)。

### 归档档案

- [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md) — v0.12.1 ~ v0.12.4 批次（2026-10-03 ~ 2026-10-07）
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
