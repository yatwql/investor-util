# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.1-dev
> **编号源**：`rf-next = 371`（新增问题取此编号，完成后更新为 +1；已用最大 rf-370，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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

### 已解决待归档（v0.10.20-dev）

均为发布 v0.10.19 后的自查整改：rf-354 为「多币种换算」这一从未实现的能力在文档与测试中被当作已验证项（rf-350 遗留项的收尾）；rf-355/rf-356 为脚本约定类——`scripts/*.ps1` 的 BOM+CRLF 约定、`scripts/*.sh` 可执行位入索引，两者此前均无任何校验环节；rf-357 为用户报障的缓存遮蔽缺陷（fix 只改代码未让旧载荷失效，TTL 内旧条目使修复在另一台机器完全失效）；rf-358~rf-362 为过去 96 小时实现的技术债与文档漂移审计整改（死代码/单一事实来源/配置形态、DataSinking 接入后的过时描述、用户文档计数与 testplan/technical 覆盖缺口）。

| # | 问题（违反的约束用语义描述） | 处置 |
|---|------|------|
| **rf-354** | **「多币种换算」口径与实现不符**：`faq.md` 称「港股通和非 A 股品种的汇率换算由数据源接口自动处理」；`testplan.md` 的 T8 场景列「美元份额币种转换」、T19 场景为「汇率中间价故障」、数据正确性验证表列「多币种转换正确：美元份额 × 汇率中间价 = 人民币市值 ✅」；测试侧 `test_data_integrity.py` 的第 4 项与 `TestMultiCurrencyConversion`、`test_market_value.py::TestCurrencyConversion` 亦按「汇率换算」命名。而全仓**无任何汇率取数或换算**（`get_currency_by_code` 只做币种分类、`fx_exposure.py` 只按币种汇总市值，QDII/场外基金净值本身即以人民币计值），T19 描述的场景不可能发生——文档把从未实现的能力写成了已验证项 | 按实现改写（不新增汇率功能）：`faq.md` 明确「程序不做汇率换算」并说明币种敞口只做分类与占比、情景分析的汇率情景为假设 ±5%；`testplan.md` T8 删「美元份额币种转换」、T19 改为真实且已覆盖的「场外品种净值日期非 T 日」场景、数据正确性表该行改为「非人民币计价品种市值核算（价格 × 份额，不做汇率折算）」；两个测试类更名为 `TestForeignDenominatedMarketValue` 并改述 docstring（断言不变）。变更详情见 changelog [0.10.20-dev] |
| **rf-355** | **`scripts/*.ps1` 的 BOM+CRLF 约定只写在文档里，无实现校验**：`cli.ps1` 与 `launch.ps1` 为 UTF-8 with BOM 但**通体 LF**，与 `.editorconfig` 的 `[*.ps1] end_of_line = crlf` 及 CLAUDE.md 的「BOM + CRLF」约定不符（新写的 `llm.ps1` 反而合规）；仓库无任何校验环节，偏离只能靠人眼发现 | 两个文件行尾归一为 CRLF（保留 BOM）；新增 `src/test/unit/scripts/test_script_encoding.py` 回归守护——逐文件断言 `scripts/*.ps1` 以 BOM 开头且不含裸 LF（缺 BOM 时 Windows PowerShell 5.1 会按 GBK 误读中文注释而解析崩溃） |
| **rf-356** | **`scripts/*.sh` 的可执行位未记入 git 索引**：仓库 `core.fileMode = false`，工作区权限不被跟踪，`cli.sh` / `launch.sh` / `llm.sh` 在索引中均为 `100644`——新克隆的仓库里 `./scripts/llm.sh` 报 permission denied，而 `how-to-use-cli-mode.md` / `developer-guide.md` / changelog 均按可执行方式调用/声称「置可执行位」 | `git update-index --chmod=+x` 将三个 `.sh` 的索引权限置为 `100755`（`llm.sh` 工作区权限同时由 777 归为 755）；新增回归用例断言索引权限为 `100755` 且工作区可执行（非 git 工作区/Windows 自动跳过） |
| **rf-357** | **「改变载荷语义」的修复被 TTL 内的旧缓存遮蔽**（用户报障：QDII 联接穿透修复在另一台机器完全失效）：`d02e32e0` 把联接基金的取数改为三跳阶梯 + 目标 ETF 穿透，但未让修复前写下的 `fund_hold_*` 条目失效——旧条目无 `feeder_target_code`，新代码无从穿透，旧载荷「有持仓 + 早期报告期」（`2023-09-30` / `2022-12-08`）直接撞上时效闸门被记为持仓不可用；`hold` TTL 为 7 天，旧条目过期前修复被全程遮蔽（提交当时仅以「需 `--clear-cache`」提醒，依赖用户手动，属真实缺口） | 给 `fund_hold_*` 载荷盖语义版本 `hold_schema`（`_stamp_hold_schema`），读取侧以 `_is_current_hold_payload` 为准入判据、版本不符即视为未命中重取；`fetch_with_fallback` 新增 `cache_validate` 参数（覆盖新鲜命中与过期降级），批量预检回调 `_hold_cache_check` 同判据（命中会跳过任务，判据须同挂在此接缝）；回归用例 8 例（chain 3 + fund 5） |
| **rf-358** | **新增即死代码 + 配置形态与语义不符**：`providers/datasink.py` 的 `fetch_report_sections()`（章节清单接口）、`quota_remaining()`（剩余配额）有定义、有单测却无任何生产消费者；`datasink.sections` 声明为列表但装配层只取 `sections[0]`，多章节配置被静默忽略 | 删除两个死函数及其单测（配额计数改由 `_read_quota` 断言）；`fetch_symbol_report` 改为按 `sections` 顺序逐章节取正文（每节独立缓存）并拼接，装配层传全部章节；补 3 例（顺序拼接/跳过缺失/全缺失返回 None） |
| **rf-359** | **同一清单/数字写两份（单一事实来源违背）**：`report/data_source_matrix._SOURCE_CATALOG[*].prefixes` 与 `_SOURCE_CATEGORIES[*].prefixes` 各写一份（日后加类别必漂移）；`_DATASINK_PLAN_BILLING` 硬编码「3 请求/秒、8,191 篇/日」，与 `providers.datasink._PLAN_LIMITS` 的 `(3, 8191)` 重复（套餐额度调整后报告说明表与真实限速不一致） | 前缀改为从 `_CATEGORY_PREFIXES`（由 `_SOURCE_CATEGORIES` 派生）取；计费文案改由 provider 新增的 `billing_description(plan)` 生成（数字同源 `_PLAN_LIMITS`），删除 `_DATASINK_PLAN_BILLING` 与目录里的重复数字；`note` 只留「免费 key 需自备」 |
| **rf-360** | **「全部数据源免费、声明表为空」描述在 DataSinking 接入后普遍过时**：`core/datasource_credential.py` 模块 docstring 与「声明即数据」注释、`config/features.py` 开关注释与描述、`core/doctor.py` / `core/check_sources.py` 回退文案、`technical.md` §2.7（标题仍写「实验：默认关」+ 正文「生产实现为空表/就绪矩阵报均无需凭据」+「凭据只从环境变量读取」）、`requirements.md` §5.8（R-CRD-01/02/03/06/07）、`how-to-config.md`（开关表行 + S 面板说明）——均与「首个需 key 源已接入、凭据走通用密钥文件」矛盾 | 全部按实现改写（中性/准确措辞）：代码注释与文案改为「未声明免凭据、需凭据的源主动跳过」；technical §2.7 标题改「常规开关默认开」、正文补 DataSinking 密钥文件与节名；requirements R-CRD-01/02/03/06/07 补 `key_file`/`key_field`/`key_section` 与密钥文件解析顺序；how-to-config 两处同步；同步更新受影响的 3 个测试断言文案 |
| **rf-361** | **用户文档计数漂移**：`README.md` 三处「最多 19 个条件页签」（registry 已 20 项、新章节启用后最多 20），且无新章节/新数据源任何提及 | README 改 20，补「财报摘要（可选）」分组与 DataSinking key 说明（`data_key.json` 的 `datasink` 节 / `DATASINK_API_KEY`） |
| **rf-362** | **testplan / technical 覆盖缺口**：`testplan.md` §4 回归清单无财报取数路径条目（同期联接穿透/cassette 均有）；`technical.md` 无 §4.x 叙述章节给「持仓个股财报摘要」 | testplan §4 增 P1 行（指向 test_datasink/test_financial_report/test_financial_report_digest/test_datasource_credential，含隔离防线）；technical 增 §4.19 章节（定位/鉴权/取数链路/限速配额/降级合规/缓存/数据源说明表） |
| **rf-363** | **任务编号纪律存在测试侧豁免漏洞**：`check-code-traces.py` 的 `TEST_META_EXCLUDE` 含「回归…整行豁免」与「rf-N 修复」两条，导致 `src/test/` 注释/docstring 中的任务编号（如 `# rf-232 回归：…`、docstring `（回归：rf-306）`、`（rf-204 回归场景）`）被放行——与「任务代号只属内部计划表、不扩散到实现层」冲突；共 7 处残留 | 收紧为「任务编号硬禁止，先于整行豁免判定」：`scan_file` 在 `_is_excluded` 之前用 `_TASK_ID_RE` 检出 rf-/plan-/R- 编号即报 CODE；删除 `TEST_META_EXCLUDE` 的 `rf-…修复` 条；清理 7 处测试注释/docstring 的编号（保留回归语义）；检查器测试同步（新增测试文件/源码注释硬检出 2 例、改写 rf 豁免断言 1 例）；CLAUDE.md 补注 |
| **rf-364** | **plan-42 新增章节未同步 integration 三方一致性契约测试**：`test_report_chapter_consistency.py` 的「全开」镜像（`_excel_visible` / `_html_visible_keys` / 两个 all-enabled 用例）未带新章节 `financial_report_digest` 的 board/data 参数，导致 Excel 少一页签、HTML 该章节不可见——`--mode all` / `all_no_unit` 各有 2 例失败；该套件为 `integration` 标记、不在 dev-verify 门禁内，故此前未暴露（由 `--mode bench` 全量跑出） | 为镜像补 `financial_report` 开关与 `financial_report_digest_data` 数据参数，「全开」场景显式启用；`--mode all` 复跑 6982 passed / 0 failed |
| **rf-365** | **测试用例审计：无效/死/冗余/目录语义不符用例**（全仓 333 文件 / 6,991 例，AST+收集扫描）：① 6 例「名实不符」无效用例——名字承诺断言却无任何断言（`test_cache_core::test_set_write_error_logged`、`test_llm_api_base::TestLogTokenUsage`、`test_handlers_cache::TestCmdCleanupCache` 2 例、`test_html_report_structure_edge::test_nav_links_count_in_source` 把 `re.findall` 结果赋给 `_` 丢弃）；② 1 例空体死用例（`test_market_value::test_today_profit_in_price_update_status` 仅 `pass`）；③ 1 组冗余——`test_llm_utils` 与 `test_llm_api_base` 各有一个 `TestLogTokenUsage` 测同一函数；④ 1 处目录语义不符——`unit/report/test_classification_utils.py` 测 `core.code_utils` 却标 `unit_report`。另 18 例「不抛异常/no-op」弱断言经审为有意，保留 | 补断言：`test_set_write_error_logged` 断言告警含「无法创建临时文件」；`test_llm_api_base::TestLogTokenUsage` 用 `assertLogs/assertNoLogs` 断言输入/输出/缓存命中内容并补 empty 分支；`test_handlers_cache` 断言 `cleanup_cache` 以 `TuiProgressReporter` 调用一次且 `press_any_key` 调用；`test_html_report_structure_edge` 改为断言 2 处导航锚点模板存在。删除空体死用例；删除 `test_llm_utils::TestLogTokenUsage` 冗余类（覆盖并入 api_base）。`git mv` 分类测试至 `unit/core/test_code_utils_classification.py` 并改标 `unit_core`。新增回归守护 `test_test_quality_regression.py`（静态禁止空测试体）。`--mode bench` 复跑 30,459 通过 / 0 失败 |
| **rf-366** | **章节合并施工单把「数据源类别」误判为「注册表 type 允许集合」**：`section-consolidation-iteration.md` 的下游影响清单（§3.2）要求「`config/_validation.py` 已知类型集合删旧增新」——该集合实为 `_KNOWN_PROVIDER_TYPES`（数据源类别 id：price/fund_rank/fund_hold/industry/financial_report/financial_indicator），与注册表章节 `type` 无关；照此实施会误改数据源校验白名单，而真正的注册表 type 约束（两侧 `board_flags` 显式登记）反而无人守 | 实施期更正 §3.2 该行（标注作废 + 说明真实约束）；新增正面守卫 `unit/report/test_section_type_flag_consistency.py`（注册表 type ↔ 两侧 board_flags 键一致 + 无残留废弃 type + 写入器模块键装配一致）；同步 §6.6b 守卫表实施标记。变更详情见 changelog [0.11.1-dev] |
| **rf-367** | **合并章 `data_flag_any` 在 Excel 侧被悲观判定吞掉页签**：`extend` 可见性模型新增多契约 OR 后，`should_create_sheet` 对 `data_flag_any` 取「未登记即未就绪」的**悲观**口径；而 `excel_generator` 构造 `data_availability` 时只登记 news/llm/两份财报契约，导致合并章 `position_structure` 的两契约（`position_relationship_data`/`concentration_data`）恒未登记 → **Excel 页签恒不创建**（HTML 侧因 `overlap_matrix`/`concentration_analysis` 直传而正常）。由 integration `test_report_chapter_consistency`（两侧可见集合一致性）捕获，dev-verify/单测均不覆盖 | `excel_generator` 按与 HTML 同口径登记两契约 flag（基金深度分析开启时下游恒计算，故视为就绪；关闭时由 board 层隐藏）；集成测试镜像同步补 flag；`test_section_visibility` 增合并章 OR 三例（仅关系就绪/仅集中度就绪/两者皆无）。变更详情见 changelog [0.11.1-dev] |
| **rf-368** | **章节合并的 board 层参数链比施工单预估更长（漏改即运行期 TypeError）**：④-1b 预计 `enable_financial_report_digest` 需改「`html_writer`/`excel_generator`/`_report_generation` 三处调用链」，实际 `_report_generation.py` 内另有 2 处包装函数签名与 2 处调用点（含 full 路径组装处共 5 处），首次改动后 `--mode verify` 立刻报 `unexpected keyword argument`；另 `technical.md` 功能语义命名表残留 `financial_indicator_sheet` 僵尸条目，由 `check-semantic-index` 的「表内 slug 无代码引用」判据捕获 | 参数链按 `grep -rn` 全量清单一次性改净（含两处包装函数与 full 路径调用点）；语义命名表把 `financial_indicator_sheet` 替换为 `fundamental_snapshot_sheet` 并新增 `fundamental_snapshot` 合并章行；两处均由既有守卫捕获（集成/verify + `--ci` 语义索引），无需新增守卫。变更详情见 changelog [0.11.1-dev] |
| **rf-369** | **章节合并四批后管理/用户文档出现顺序与内容漂移**（逐份核对发现，共 6 类）：① `requirements.md` §6.3 漏 `fundamental_snapshot` 行且 `llm_usage` 编号滞留 16；§6.4 编号重复（两个 6.4.5）且缺 持仓基本面 小节 → 已补行、§6.4 重排为 1..18（17 个报告章节 + 成本流水子模块），经理变更块降为章内子标题；② `how-to-config.md` 表头「15 个模块」与缺 `fundamental_snapshot` 行、`llm_usage` 编号错位，示例 JSON 仍用已删键（`fund_manager`/`position_relationship`/`fund_concentration`），「19 项/18 项」计数陈旧；③ `reports-instruction.md` 类型分组表编号错位（基金业绩 3→4、数据源 14→15、LLM 用量 16→17）、基金深度分析「共 4 个」→2、基金评价表重复的「持仓集中度」行、菜单索引与「19 个页签」陈旧；④ `folders.md` HTML 模板行仍列两个旧 partial、目录树残留三个已删模块行、缺 `test_section_visibility.py` 与合并 partial、统计快照陈旧；⑤ `technical.md` 三处「19 个模块」、注册表示例用已删条目、基金深度块图与小节标题未随合并更新、TOC 条目未随 §4.19 改题；⑥ 用户文档 `README/faq/how-to-use-*`/`datasource*` 的页签计数、示例 JSON、管理菜单 `[P]`/`[S]` 归属与章归属表述陈旧 | 逐份按注册表现状整改（章节表编号与顺序对齐 17 条注册表；示例键全部替换为现存键；计数/清单以实测或注册表为准）；`test-coverage.md` 按 `collect-test-coverage.py` 实测刷新模式/子标记/跨类计数；补 `testplan.md` §4「报告章节合并」回归行；`folders.md` 统计与目录树按实测刷新。变更详情见 changelog [0.11.1-dev] |
| **rf-370** | **过去 96 小时（plan-42~45）实现的技术债审计**（7 类）：① **语义索引正向校验空转**——`check-semantic-index.py` 仍校验 `_config_defaults.py` 的 `report_submodules` 字典，但该机制已随 plan-44 移除 → 该项恒为空集、**新增开关可绕过「功能语义命名表」登记而不被发现**；② 该失效掩盖了 **12 个功能开关未登记语义表**（`llm_debate_procon`/`llm_debate_qa_concentration`/`llm_debate_conditional`/7 个 `metrics_*`/`enable_interactive_charts`/`datasource_adapter`）；③ **data 层可用性字典双份实现**——`excel_generator` 内联构造、integration 一致性测试手写镜像，plan-45 每批都要改两处（rf-367 即此类漂移）；④ 死代码/死认知——`html_writer_nav` 的 `manager_data` data_flag 随章节移除后已无消费方、`registry` docstring 示例仍用已删条目 `fund_manager`；⑤ 配置面旧名残留——Web 面 surface 键 `submodules`（含前端 `main.js` 手写 `CONFIG_LABELS.submodules` 字典，且漏列两个开关）沿用旧机制命名，与「键即功能开关名」不一致；⑥ **测试用例陈旧/失效断言**——`test_excel_report_structure` 夹具仍用已删章节键与旧序号、`test_config` 的「重复序号」用例改用已删键后实际测的是「未知键」路径（断言通过但测的不是目标行为）、`test_orchestrator`/`test_excel_market_data` 等注释仍指向 `report_submodules.*`、plan-45 新增用例含一条**恒真断言**（先按值过滤再断言不存在）；⑦ **配置与模板漂移**——`data/config/config.json` 缺 `holdings_start_date`（模板已含），属 plan-43 引入后未重生成 | **处置**：①把正向校验改挂**功能开关注册表**（`features.py::feature_switch_registry`，AST 解析；脚本 docstring/verbose/摘要与单测同步），②按新校验补齐 12 行语义表，③把字典构造下沉为 `excel_sheet_factory.build_data_availability()`（生成器与集成镜像同源，新增 5 例口径守卫），④删死 flag + 修 docstring 示例，⑤Web 面键改名 `report_switches`（服务端 surface + 前端渲染同步，删前端陈旧字典），⑥夹具/注释/断言按现状改正（恒真断言改为「占位文案存在 + 无集中度数据行」正向断言），⑦按当前模板重生成 `config.json`（补 `holdings_start_date`，其余键值保持仓库现值，校验 0 问题）。变更详情见 changelog [0.11.1-dev] |

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.19-dev（2026-08-04 ~ 2026-09-12，rf-204 ~ rf-353）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
