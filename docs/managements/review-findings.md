# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.9-dev
> **编号源**：`rf-next = 658`（新增问题取此编号，完成后更新为 +1；已用最大 rf-657，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题


### P1 — 高优先：不做的风险高（尽快执行）

> 入选标准：默认开启功能与用户渠道未经完整验证，遗漏即放行线上缺陷。

| # | 问题 | 修复方向 |
|---|------|----------|

| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **验证方法与实测结论已成文 [`docs/plan/report-browser-verification.md`](../plan/report-browser-verification.md)**（六项拆分可自动化/人工 + §1.1 复跑命令 + §5 复验清单；勾选清单留存 [`docs/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`](../archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md)）——历史：2026-08-06 另机人工 ① 全过 / ② 2.1~2.3 过（期间修复 rf-248/249/251）；**2026-10-09 本机 headless Chromium 148 + Node 22 CDP 自动化实测**（不生成报告、仅打开既有产物；脚本与证据在 git 忽略的 `docs/tmp/rf113/`，重跑即建）：① `?s=ok` 6/6 badge + console 0 error 过；② 2.4 过（真实报告 beforeprint 插入 10 张 2x 快照 → afterprint 0 残留 + 几何 0px 偏差 + 真实 hover tooltip 恢复 2→2）；③ 3.1 过（静态 5 类外链 grep 全 0 + `--host-resolver-rules=MAP * ~NOTFOUND` 断 DNS 打开 10/10 图渲染、外域请求 0、console 0）；⑤ 报告产物 375px 过（`scrollWidth==clientWidth==375`、轴标签 45° 不重叠、表格容器内滚动）；⑥ 实测完成（注入 `getContext→null`：0/10 初始化 + 图表区空白 + 41 张明细表格兜底可读，rf-249 口径复核成立）。**待人工（不可自动化）**：④ 微信真机（步骤与判定标准见该文档 §2④：4.1 链接访问必过，4.2 file:// / 4.3 兜底任一过即 ④ 通过）+ ① Safari / ② 真实 `Ctrl+P` 分页抽验（均不阻塞）。附带发现 → rf-645（调试页 375px 溢出 + afterprint 内联 display 恢复不精确；两项均已修复 2026-10-09）。④ 完成后回填 changelog、本表移至已修复（rf-114 随之解锁） |
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复。**验证方法与实测结论已成文 [`docs/plan/web-browser-verification.md`](../plan/web-browser-verification.md)**（五类拆分可自动化/人工 + §1.1 启动/收尾命令 + §5 复验清单；勾选清单留存 [`docs/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`](../archive/v0.10.x/web-ui/web-ui-verification-checklist.md)）——**2026-10-09 本机 headless Chromium 148 CDP 自动化实测 37 项断言：33 过 / 2 不过 / 2 人工**（全程 0 次真实 `POST /api/runs`——浏览器侧 Network 捕获与服务端日志双侧为 0；`scripts/smoke-web.py` 11/11；脚本与证据在 git 忽略的 `docs/tmp/rf257/`，重跑即建）：① 渲染过（`style.css` 171 条规则生效、7 卡齐、`main.js`/`style.css` 均 200、Console 0 error，**rf-274 回归闭合**）；② 上传表单过（`accept=.xlsx` + 合法/伪装/空文件三路径中文文案 + 拖拽 class/样式 + 键盘可达；2.5/2.6 为合成事件口径）；③ 部分（初始 hidden + aria 进度条 + 显隐逻辑过，真实进度以 smoke-web 事件流为已有证据，完整观察待人工跑一次 basic）；④ **375px 不过**（`scrollWidth 421>375` 横向滚动、`select#report-type` 超视口 29px——根因「正式更新」radio 文案内绝对持仓路径无断词机会 → **rf-644**（已修复 2026-10-09））；⑤ 按钮态过（初始 disabled/启用条件/disabled 视觉/真实鼠标 hover 4/4 + `forcePseudoState` 兜底；5.3 提交即禁用留人工）。复跑：`.venv/bin/python scripts/smoke-web.py` + `node docs/tmp/rf257/cdp-check.mjs`；收尾必做 kill 服务/浏览器 + 清空 `data/holdings/uploads/`。**余人工项**：③ 真实 basic/full 进度观察、④ 4.5 结果区按钮、⑤ 5.3、② 2.5/2.6 真实拖拽与 Tab/Enter 抽验；rf-644 已修复，按该文档 §5 复验清单回填 |

### P2 — 中优先：价值明确、成本可控（下批排期）

> 入选标准：修复路径清晰、成本可控；rf-114 须待 rf-113 人工验证完成后执行。

| # | 问题 | 修复方向 |
|---|------|----------|

| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |


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

- rf-657 已修复（2026-10-10，管理文档核对）：**`folders.md` 版本演进对照「当前开发版」列过时**——该列为滚动读数，仍停留在 2026-10-09 发布日快照（主程序 344 文件 / 90,627 行、测试 506 / 146,728、`def test_` 行数 9,346），与同文件「项目统计」（345 / 91,291、508 / 147,773、收集 9,882）及实测不一致，口径附注同过时（严格口径 9,293、pytest 收集 9,784 / 9,804、行数比 146,728 / 90,627）。修复：按表内复现方法以 2026-10-10 工作区重跑第三列全部读数（11 行 + 增长比 + 列头日期）与附注三读数；前两列固定快照不动。

- rf-656 已修复（2026-10-10，管理文档核对）：**LLM 用户手册落后于 429 实现口径且有缺登记**——rf-647 / rf-653 已把 429 归 `quota` 终态（首试即 600s 长冷却熔断、零退避重试，503 才按 `max_retries` 退避），`llm-technical.md` / `requirements.md` / `technical.md` / `developer-guide.md` 已同步，但用户手册漏改：`how-to-config-llm.md` 4 处（失败分类与重试、`max_retries` 键说明、状态码表 429/503 合并行、高峰 429 无害提示行）与 `faq.md` 429 Q&A 仍写「429 按 max_retries 退避重试」；同文件另缺登三处：全局键清单缺 `llm_full_fail_retry_delay`（rf-653 已入已知键集，「全部配置项」声明下不可检索）、`{module}` 后缀清单缺 `self_review` / `holding_change`、`enabled_llm` 三处 JSON 示例缺同两键；`how-to-config.md` 的 cache_ttl 表缺 `llm_holding_change`（`data_registry` 已登记 2h）。修复：按实现与 llm-technical 口径改写 / 补齐上述各处。

- rf-655 已修复（2026-10-10，用户报告持仓体检报告事实校验 3 条提示 + 2 处自动误修正）：**事实校验器四类语境缺口**——① **回放/回测语境未豁免**：调仓纪律回放面板的模拟指标（规则A/买入持有 的区间收益、最大回撤、夏普）与持仓实际收益率不同源，句中无 6 位代码时被全局最近邻兜底归因到无关品种并自动「修正」（实盘：回放句「区间收益 -5.35% 优于买入持有 -7.16%」的 -7.16% 被改为 096001 的 9.2%，把正确数据改错且与回放面板自相矛盾）；② **回撤紧邻窗口被远端收益词击穿**：`_is_drawdown_context` 的「前 15 字符有收益词则非回撤」排除逻辑在「收益 -5.35%、最大回撤 10.28%」中把 10.28 判为收益语境；③ **历史（已清仓）代码未纳入有效集**：LLM 提示词含【环比变化】清仓行与统一附录【持仓变动复盘】块，引用已清仓代码（如 159222）属合法历史语境，却被品种存在性校验误报「不在当前持仓中」；④ **近并列排名无差距注记**：市值差仅 0.05% 的两只品种排名随快照时点翻转，告警未提示该脆弱性。修复：① `_constants._REPLAY_KEYWORDS` + `_context._is_replay_context`（整句判定，回放/回测/买入持有/What-if/as-if），在 `check_numerical_consistency` 主循环整句跳过；② `_is_drawdown_context` 增紧邻优先（match 前 ≤8 字符内回撤词直接判回撤，优先于远端收益词排除）；③ `generators_orchestrator.extract_historical_codes` 从 `pipeline_data["diff"]`（removed/added）与 `holding_change_data.events` 动态提取历史代码并入 `extra_valid_codes`（四模块均生效，穿透代码仍仅限三模块）；④ `_ranking._near_tie_note` 在市值差 <1% 时于告警文案尾附加差距注记（不改变严重级别）。回归 16 项（`test_fact_checker_replay_context.py`）。

- rf-652 已修复（2026-10-10，用户报告盘后「价格更新状态 8/13」长期缺数）：**场外净值缓存新鲜度门禁对国内场外误用 QDII 的 T-1 阈值**——`_OTC_NAV_ROUTES`（`price_fund_otc`）把国内场外与 QDII 一律按前一交易日判新鲜，而国内场外 T 日当晚即披露净值、盘后应已达 T；实测数据源（东财）已返回 T（10-09），缓存仍停在 T-1（10-08）被门禁放行，报告口径（`price_update_status` 国内场外仅认 T）与缓存口径不一致 → 5 只国内场外长期计为未更新。修复：`_price_cache_fresh` 增 `name` 形参并按 `is_qdii_extended` 细分（QDII 保留 T-1、国内场外要求 T），两处调用点传入持仓名（`fetcher/price.py` 强刷路径 `expected_name`、`report/market_value.py` CACHE_ONLY 路径 `h.name`）。回归 4 项（QDII T-1 新鲜 / 国内场外 T-1 过时 / 国内场外 T 新鲜 / 端到端强刷并验证持仓名转发）；`unit/fetcher` + `unit/report` 3076 项全绿。

- rf-653 已处置（2026-10-10，过去 72h 实现技术债核查：BASE=`424f25b5^..HEAD`，78 提交）：三项修复——① **LLM 429 行为变更后文档未同步**：rf-647 把 429 由「可重试」改判 `quota` 终态（首试即 600s 长冷却熔断、零退避重试），但 `llm-technical.md`（§4.2 与 403 的配合 / §6.1「四层容错」/ §6.2 重试表 / §6.3 失败原因表）、`requirements.md`（R-LLM-10 + `max_retries` 说明）、`technical.md`（LLM 降级 + C26）、`developer-guide.md`（测试载体描述）仍写 429 重试——按实现改写，并把 429 长冷却与「全链延迟重试（`llm_full_fail_retry_delay`）」补入容错层次与失败原因表；② **`llm_full_fail_retry_delay` 未登记为已知键**：`skeleton._execute_llm_with_finalize` 直接读取该键，但 `_DEFAULT_LLM_SETTINGS` 与 `get_known_llm_settings_keys()` 均无——用户在 `llm_settings.json` 设置会被判「未知配置项…请删除」，与消费端读取矛盾；补入默认集/模板/已知键集，并加结构回归（默认集 ⊆ 已知键集 + 设置该键不产生未知键告警）；③ **`_factor_zoo` 包内根路径三处重复计算**：`catalog/metrics/stages` 各自 `Path(__file__).resolve().parents[2]`（rf-636 同类「拆包后层级算错静默失效」风险），收敛为包 `__init__.py` 的 `PROJECT_ROOT` 单一来源。

- rf-654 已修复（2026-10-10，量化指标开关合并（plan-115）实施中自查）：**熔断器 `_ff_was_off` 标记只读不写**——`_check_feature_flag` 的「Feature Flag 打开时自动重置断路器状态」分支依赖 `_ff_was_off`，但全仓无任何写入点，该契约从未生效；关闭期到来前的残留失败计数会跨开关周期累计，开关刚打开即可能误触发断路。修复：关闭期为已有状态写入标记（解熔路径保持原语义），开回时清零残留；并补 6 项熔断 FF 联动用例（关闭不计失败 / 开启正常计数断路 / 关闭自动解熔 / 开回清残留 / 映射外指标不受约束 / 关闭时不执行计算——此前该联动零覆盖）。

### 归档档案

- [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md) — v0.12.1 ~ v0.12.8 批次（2026-10-03 ~ 2026-10-09）
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
