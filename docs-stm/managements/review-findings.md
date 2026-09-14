# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.20-dev
> **编号源**：`rf-next = 364`（新增问题取此编号，完成后更新为 +1；已用最大 rf-363，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
