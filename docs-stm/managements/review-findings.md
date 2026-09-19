# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.2-dev
> **编号源**：`rf-next = 414`（新增问题取此编号，完成后更新为 +1；已用最大 rf-413，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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

#### P2C — LLM Thinking 预算与 max_tokens 约束（2026-09-16）

> 处理「思考耗尽 max_tokens」日志时发现；本次修复只做 +50% 上调上限，未改动此逻辑。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-379** | `llm/api.py::_resolve_thinking_budget` 兜底方向可疑：配置的 `thinking_budget_{module}` 小于 `max_tokens + 1024` 时被判「不足」并**提升到 `max_tokens + 4096`** → 实际发送 `budget_tokens > max_tokens`。但 Anthropic 官方约束是 `budget_tokens < max_tokens`（Gemini 2.5 亦要求 thinkingBudget 小于 maxOutputTokens），方向相反 → Claude/Gemini 原生模型 + 开启 thinking 时可能被 API 拒绝（日志表现：「Claude API 响应格式异常」后关闭 thinking 重试）。手册 `how-to-config-llm.md`「thinking_budget 与 max_tokens 的关系」将该方向写为「API 硬约束须 ≥ max_tokens + 1024」，同样待核实 | ① 查证 Anthropic / Gemini 真实约束并构造复现（两者是否都要求 budget < max_tokens）；② 若方向确认写反，改为「budget 上限 = max_tokens − 正文余量（如 −2048 或 −20%）」；③ 同步更新手册与 `llm-technical.md`；④ 补 payload 级回归测试（Claude / Gemini 两条路径各一） |

## 已解决问题

### 已解决待归档（v0.11.2-dev）

| # | 问题（违反的约束用语义描述） | 处置 |
|---|------|------|
| **rf-402** | **full 路径 HTML 漏接市场情绪契约 → 同一次运行两端产物自相矛盾**（用户问询「同花顺，市场情绪没开启么？我看数据可用性矩阵没提到它」曝光）：`_generate_report_full` 未注入 `market_sentiment_data`，且 `_generate_full_html_report` 无该形参、其 `write_html_report` 调用未传参——HTML 侧因此（a）行动建议章情绪区块不渲染（b）「数据源可用性矩阵」缺「市场情绪」行（矩阵只列本次取用过的类别，非源清单）（c）说明表记「○ 未使用」；而 Excel 侧靠 `excel_generator` 就地兜底在 HTML 落盘**之后**才取数 → 同一份运行里 xlsx 有「同花顺金融数据 ×2」行、HTML 没有（实测 2026-09-18 21:54；`logs/app.log` 三行时间戳 HTML 20.126 → 情绪取数 20.419/20.799 → Excel 21.032）。开关与凭据本无问题（`features.json` 已开 `market_sentiment`、hithink key 已就绪），属接线遗漏而非功能未开启 | 编排层在写 HTML 之前取数并注入 `pipeline_data`（与 both 路径同位：`record_prosperity_diagnosis` 之后、`# ── 6. HTML 报告 ──` 之前，透传 `prep` 以带出穿透标的），`_generate_full_html_report` 新增形参并透传 `write_html_report`；回归用例 2 例（编排注入 / HTML 生成器透传，已验证对修复前代码两者均失败）；Excel 就地兜底保留（basic 路径不经编排层） |
| **rf-403** | **市场情绪块的三处描述与实现不符**（用户追问「情绪价值会出现在报告哪个部分？我没看到」时发现）：“位置”写错——`features.py` 开关描述写「**新增独立章**」，实际是行动建议章内嵌块（归档设计文档已记该偏离：初稿「独立章节」→ 实现「章内区块」）；“空命中行为”写反——`data_source_matrix.py` 说明表、`how-to-config.md`、`datasource.md` 三处写「**无命中时该区块不显示/不渲染**」，而实现是**零命中仍渲染**（HTML `action_section.html` / Excel `action_sheet.py` 均写 `reason or "当日无命中事件"` + 市场概览，并有专测锁定）。两句叠加使用户把“区块正常但零命中”误判为功能未开启/未接入 | 四处按实现改正：开关描述改为「行动建议章内嵌块「市场情绪与持仓热点」…（零命中时写市场概览与说明行）」；三处空命中口径改为「零命中时写市场概览与「当日无持仓/穿透标的命中」说明行（区块仍渲染，便于区分「无事件」与「取数失败」）」，并将排查路径（矩阵「市场情绪」行 / 说明表「本次使用」/ `[market_sentiment] 命中 N 条`）写入手册 |
| **rf-404** | **报告组开关计数与清单在 4 处漏数**（rf-400 同类漏改，本次文案核对时发现）：`how-to-use-tui-menu.md` 仍写「功能开关共 29 项（⚗5 / 常规 16 / 报告组 8）」、「报告组 8 项」且清单漏 `market_sentiment`（两处列举）、`how-to-config.md` 报告子模块枚举漏 `market_sentiment`、`folders.md` 仍写「features.py 28 项声明…报告组 8 项」——实况为 **30 项（5/16/9）** | 四处按注册表实况更正（29→30、8→9）并在三份清单中补 `market_sentiment`（按注册表顺序置于 `financial_report_digest` 与 `financial_indicator` 之间）；核对方式：以 `feature_switch_registry` 按 `GROUP_ORDER` 重算分组计数与成员顺序逐项比对 |
| **rf-405** | **统计快照过期（12 处，用户要求全量核对时发现）**：`test-coverage.md` 的 unit 7,213 / standard 6,198 / all 7,530 / report 1,964 / unit 父标记 7,213 / unit_report 1,964 / 功能域「报告生成」1,964 与实测各差 2（本次 rf-402 新增 2 例回归用例未回填）；`folders.md` 的主程序行数 74,191、测试代码行数 114,036、测试用例 7,530、managements 行数 10,090、项目文档行数 53,808 同样未随代码/文档变动刷新（代码行数口径项还需联动「源代码合计」） | 12 处按实测更新（测试计数 +2；行数按当前工作区重算，合计行同步）；口径命令：`scripts/collect-test-coverage.py` + 行数统计重算 |
| **rf-406** | **目录树漏登 9 个文件**（违反「目录结构同步」约定）：`fetcher/financial_indicator.py`、`scenario/basic/test_scenario_prosperity_framework.py`、`unit/analysis/test_financial_statement_derive.py`、`unit/analysis/test_market_sentiment.py`、`unit/fetcher/test_financial_indicator_hithink.py`、`unit/fetcher/test_quote_adapter_hithink.py`、`unit/report/test_market_sentiment.py`、`unit/report/test_market_sentiment_wiring.py`、`unit/scripts/test_test_runner_reports.py`——新增时未同步 `folders.md`（鲸鱼效应：反向检查无幽灵条目、10 份手册/管理文档其它目录一致） | 9 个文件按所属子包位置补入目录树，每个附简短职责说明（说明取自文件 docstring）；补后重核：实际有而树内缺 0、树内有而磁盘无 0 |
| **rf-407** | **TUI `[S]` 面板编号表整体过期**：实验块只列 6~9（缺 ⚗ 景气度框架诊断，实况已转实验组后共 5 项）；常规块编号 10~25 未随实验组扩容后移（实况 11~26）；报告块完全未编号（实况 27~35）；`how-to-use-tui-menu.md` 的「系统自检（第 23 项）」引用随之失准（实况第 24 项）；`how-to-use-web-mode.md` 的实验性功能清单同样只列 4 项、标 `[S]` 实验块（6-9）。根源：编号由 `handlers_config.py` 从分组与注册表顺序**派生**（设计上就为非硬编码），而文档抄的是旧快照 | 编号表按实况重编（实验 6-10 / 常规 11-26 / 报告 27-35）并补景气度框架诊断行；报告块改为带序号枚举（便于以后与面板逐项对得上）；两处位置引用改为第 24 项；web-mode 清单补项并改（6-10）。面板编号口径：LLM 模块（辩论三模块被 `filter_menu_llm_modules` 隐藏）1-5 → 实验组 → 常规组 → 报告组连续编号 |
| **rf-408** | **三处零星数值/表述与实况不符**：① `requirements.md` R-OUT-05/R-OUT-07 仍写「页签编号 1~19」「默认顺序（19 项）」，而章节注册表实况为 17 个报告章节（`how-to-config.md` / `technical.md` 已写 17，仅这两处漏改）；② `technical.md` 功能语义命名表的 `market_temperature` 行写「（默认关）」而注册表默认 `True`；③ `testplan.md` 写「配置面板 8 块可编辑项（白名单 7 组…）」——白名单是 45 个扁平键无分组，7 是 `/api/config/edit` 的可编辑面数（`technical.md` 已准确表述） | 三处按实况改正（19→17；默认关→默认开；改为「7 个可编辑面，功能开关面拆成「实验性功能」「常规开关」两块」）；同轮核对中另两类报警经核实为误报（`market_temperature_data` 契约名被前缀匹配、`how-to-config.md` 中非开关表被当成开关表），未改 |
| **rf-409** | **章节数/开关默认值两处漏网**（把审计脚本常驻化时由脚本自身报出）：① `technical.md` 章节渲染流程末尾仍写「返回 result（19 项，key/number/type/data_flag）」，实况 17 项——上轮手工核对只覆盖了「页签编号 1~N」「默认顺序（N 项）」两种写法，漏了「返回 result（N 项）」；② 同文档 `market_temperature_data` 契约段写「功能开关 `market_temperature` 默认关」，实况默认开（`how-to-config.md` 已写 true）——上轮扫到的这条因同行有 `market_temperature_data` 而被整行误判为「前缀匹配误报」放过（误报过滤粒度过粗：应逐 token 判定而非逐行） | 两处按实况改正（19→17；默认关→默认开）；并把四类断言（章节表/章节数量/开关表与分组计数/开关默认值）连同目录树与项目统计表做成脚本 `scripts/check-doc-drift.py`，纳入 P0/P2 门禁与 dev-verify preflight，不再依赖人工穷举写法 |
| **rf-410** | **CI 因构建产物误报全红**（提交后 GitHub Actions `test` job 在 3.11/3.12/3.13 全部失败）：CI 的 P0 步骤在 `pip install -e ".[test]"` 之后执行，而 editable 安装会在 `src/` 下生成 `*.egg-info/`（`*.egg-info` 本就在 .gitignore 中）；一致性检查把工作区所有文件都当作「应被 folders.md 登记」，于是对生成物报「目录树缺条目」→ dev-verify preflight 失败。**本地验证漏了安装态差异**——只用「干净克隆 + 现有 venv」复现，未模拟 CI 的 editable 安装 | 新增产物判定 `_is_generated()`（`__pycache__`/`.eggs`/`build`/`dist`/`.pytest_cache`/`.ruff_cache`/`.mypy_cache`/`htmlcov`/`test-reports`/`*.egg-info`/`*.dist-info`/`.coverage` + `docs-stm/tmp/` 前缀），目录树与项目统计两条路径统一排除；回归用例 +11（判定表 + 含产物的合成仓库用例）；本地以 `mkdir src/investor_util.egg-info` 复现该误报、修复后不再触发 |
| **rf-411** | **测试集存在可清理的冗余与若干「名实不符」用例**（用户问询「有没有冗余的测试用例，无效的测试用例」后全量静态审计 7,245 个用例）：① 20 组完全重复用例（同体同参数同装饰器）——其中 14 组同一被测对象同一断言、6 组是不同 provider 解析器的并行覆盖（后者应保留）；② 6 个**自证用例**（`test_cache_edge.py` 的 `get_ttl` 系列：`@patch("src.python.cache.get_ttl")` 把被测函数本身 mock 掉，再断言自己设的 `return_value`，断言恒真）；③ 若干**名实不符**用例（`test_default_true` 实际设了 `SSL_VERIFY=true` 而非默认值、`test_none_content` 传的是 `""`、`test_midday_145959_still_midday` 的时间由 patch 决定而与名字无关、`test_capture_snapshot_holding_mapping` 名字声称验字段映射却只断言返回 None）；④ 16 个**无断言**用例（仅「调用不抛异常」，未断言任何可观测结果）。**无死用例、无同名覆盖、无 Test 类 __init__**（既有 `test_test_quality_regression` 空体守护有效） | ① 跨文件重复删其一（metrics/metrics_edge、config/financial_indicator、decision_header/prompts_structured_header、llm_analysis 两个类），同文件重复合并（`test_html_builders_edge` 的价格变体 4→1 用 `subTest`、`test_market_hours` 09:30 重复删一、`test_news_sources` 字母 token 重复删一、`test_cache_edge` 午休/收盘合并为一条）；② 自证用例改写为真实断言（patch 依赖 `_is_market_open`/`get_config`、断言真 `get_ttl` 返回值：短 TTL / 静态 TTL / 默认回退 / 告警下限）；③ 名实不符改为真跑名字声称的场景（`getenv` 走 default 分支、真传 `None`、映射用例改为断言传给 `save()` 快照的字段映射）；④ 16 处补真实断言（stdout 静默、错误列表记录、删除尝试次数、缓存文件不存在、`assert_not_called`、剩余超时 > 0、产出 xlsx 存在等）；⑤ 新增常驻检查 `scripts/check-test-redundancy.py`（四类：死用例/无断言/完全重复/自证用例，含辅助方法断言解析与「不可解析 self 间接调用跳过比对」的误报守卫）+ 24 例单测，纳入 P0/P2 门禁与 dev-verify preflight。审计结论与处置口径已回用户 |
| **rf-412** | **`scripts/` 存在性能、重复与契约三类可优化空间**（用户问询「scripts 目录下的脚本有没有可优化的空间」后审计 23 个脚本）：**性能**——`check-semantic-index.py` 对每个 slug 重读并重 tokenize 全部 `.py`（116 slug × ~88 文件 ≈ **10,176 次全文件 tokenize**，cProfile 显示占其 95% 耗时，实测 7.15s）；`check-code-traces.py` 对 89 个模式逐行 逐一匹配（3.8 万注释行 × 89 ≈ 345 万次 regex，实测 4.53s）；**重复**——`check-code-traces.py`(1009 行) 与 `check-doc-traces.py`(586 行) 有 4 个函数逐字节相同（`_chapter_excludes`/`_is_chapter_excluded`/`_round_excludes`/`_is_round_excluded`，漂移风险）；14 份 argparse、12 份 `REPO_ROOT`、9 份 `--ci` 分支、17 份 `[OK]` 输出、4 份 marker/表格区间解析、2 份 `_rel`（各自一份样板）；**契约**——`check-version-consistency.py` 无 `--ci`；`check-task-numbering.py`/`check-test-markers.py` 有 finding 却退 1（非 2）；三个 `check-svg-*.py` 无退出码（永不失败，无法作为门禁）；**结构**——`test-runner.py` 1,600 行混 6 类职责；**死代码** 2 处（`calibrate-dedup-threshold._ratio_band`、`check-version-consistency._check_exact`） | ① **性能**：semantic-index 改为「每文件 tokenize 一次 + 全 slug 复用」（7.15s → **0.25s**，≈29×）；code-traces 加编译缓存 + 89 模式并集预筛（4.53s → **3.32s**，−27%）；② **共享模块**：新增 `scripts/_checklib.py`（统一 `-v/--ci` 与 `report()` 退出码契约、`rel()`、文档标记与表格区间解析）与 `scripts/_traces_common.py`（两个 trace 脚本共享排除模式，原面 re-export 保持测试可用），各脚本改为复用；③ **契约统一**：`check-version-consistency.py` 补 `--ci`（只报失败、退出 2）、`check-task-numbering.py`/`check-test-markers.py` 违规退 2、`check-svg-*.py` 三合一为 `check-svg.py`（子命令 geom/pixel/text-overflow + `--ci` + 退出码）；④ **拆包**：`test-runner.py` 1,600 → 246 行入口 + `scripts/_test_runner/` 七个模块（paths/modes/pytest_env/machine_info/doc_writer/report_html/runner，均 <350 行），入口原面 re-export 49 个符号；⑤ 清理 2 处死代码；新增 `src/test/unit/scripts/test_checklib.py`（38 例）覆盖共享设施；受影响测试的 monkeypatch 改指向持有状态的子模块（`report_html._LATEST_DIR` 等）；⑥ 合并后 `geom` 暴露的 4 处「文本贴边」（右余量 1~4px）按加宽卡片修复：`architecture.svg` 左侧渠道列 +10px / 中间双列卡片 +8px，`llm-chain.svg` 四 Provider 卡片 +10px，三张 SVG 现均通过且卡片内文本右余量 ≥10px |
| **rf-413** | **`check-svg-pixel.py` / `check-svg-text-overflow.py` 依赖 Pillow 但未在依赖清单声明**：两脚本顶层 `from PIL import Image`，而 `pyproject.toml`/`requirements.txt` 均无 Pillow——本地 venv 恰好装了（12.3.0，疑为其它包传递依赖），干净环境（CI 的 `pip install -e ".[test]"`）下两脚本必 `ModuleNotFoundError`（即「像素审查」在 CI 环境从未可用） | 合并为 `check-svg.py` 后改为**按需导入** + 可读指引（`pip install -e '.[svg]'`）与退出码 1；`pyproject.toml` 新增可选依赖组 `svg = ["Pillow>=10"]`，`requirements.txt` 同步 `Pillow>=10`；`developer-guide.md` 注明几何审查免依赖、像素子命令需 Pillow |

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)  — rf-380 ~ rf-401（v0.11.0 ~ v0.11.1 批次，2026-09-18 并入）
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
