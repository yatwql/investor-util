# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.12.8-dev
> **编号源**：`rf-next = 652`（新增问题取此编号，完成后更新为 +1；已用最大 rf-651，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
| **rf-651** | **`test_check_doc_drift_crosscheck.py` 两用例在 dev-verify 全量并行下偶发红**：`TestRealRepoSmoke::test_current_repo_consistent` 与 `TestProjectStatsSync::test_real_repo_sync_idempotent` 读写**真实仓库** `folders.md`（sync 类测试会回写统计），与并发 worker 相互踩踏——连续两轮 dev-verify 复现同样两例失败，单跑 68/68 绿、单独 `--sync` 报「统计表数字与实测一致，无需回写」（佐证数据本身一致，纯并发时序问题） | **待处理**（二选一，下批排期）：① 注册串行 marker（`conftest.py` 注册 + `test-runner` 分档）令两用例独占跑；② 改为临时仓库快照读写，不再触碰真实 `folders.md`——消除门禁判读噪声与假红 |


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

- rf-644 已修复（2026-10-09，Web 375px 横向滚动根因）：`style.css` 三层钳制——`.radio-label span` 路径文案 `overflow-wrap:anywhere`（min-content 369→断词级；break-word 不参与 min-content 计算故无效）+ `.generate-form > *` 行线宽按列封顶（机制性根因：flex 行线宽取 fit-content 不受列宽封顶）+ select/file input `min-width:0; max-width:100%`；生成与调仓页签同类路径文案同规则覆盖。真机复验（headless CDP）：375px 断言 35/0/2（修前 4.1 scrollWidth=421、4.3 select 超视口不过）、五页签×十二视口扫描 60/60、新旧 CSS A/B scroll 404→375 / select 363→293，桌面 1280 无回归；回归用例 `test_web_responsive.py` 5 项。favicon 404 已补（`src/static/web/favicon.svg` + `index.html` link 声明，2026-10-09，回归断言 `test_favicon_declared_and_served`）；320px status 按钮溢出经 A/B 证实 pre-existing 不在本条范围。rf-257 ④ 复验解锁（余项仍待人工）。
- rf-645 已修复（2026-10-09，rf-113 自动化实测附带发现两处）：① 调试页 `test-chart.html` grid 列下限改 `minmax(min(420px,100%),1fr)`，375px 不再自身溢出（报告产物本就无溢出，清单 5.1 载体仍为报告 HTML）；② `chart-print.js` beforeprint 记录各 canvas 原内联 display、afterprint 按记录还原（未记录回退 `block`、周期末清空记录），替代置空串导致 computed display 由 block 漂移为 inline。资产单源确认（`html_writer_assets.py` 相对路径引用，无内联副本）；回归用例 `test_feature_interactive.py` 4 项。
- rf-646 已修复（2026-10-09，需求登记补齐）：`requirements.md` §6.16 事件窗量化对照 + `R-EW-01..06` 六条需求行（纯计算口径/契约与降级/编排只读/开关可见性/双端单源/LLM 附录，先读实现后如实登记）；`testplan.md` §2.1 补 6 行载体映射（段首统计同步实测 38 域/310 条）；`check-requirement-trace` `_COVERED_DOMAINS`/`_ALL_DOMAINS` 纳入 R-EW——守护 38/38 域全量双向一致，后续新增需求行不再漏报。
- rf-647 已修复（2026-10-09，LLM provider 链路：429 长冷却 + 全挂延迟重试；**同日追加补完**）：① `circuit_breaker._cb_record_failure` 增加 `cooldown`/`force` 参数，`api_base` 对 429 立即长冷却熔断（`_RATE_LIMIT_RECOVERY=600, force=True`）；**补完**：429 归入 `quota` 终态（`_attempt_api_call` 返回 `("quota", 429)`）**首试即熔断、零退避重试**——撞限首波代价 10~35s→<1s（503/超时保留重试语义不变）；② `skeleton._execute_llm_with_finalize` 失败后按原因分流：瞬时类（network/timeout/api_error）延迟 `llm_full_fail_retry_delay`（默认 30s，配 0 关等待）整链重试 1 次，配额/熔断终态不重试；③ 配套运维：kimi 双端点 `pacing.min_interval` 1s→5s（`llm_providers.json`，改前备份 `.bak-20261009`，opencode-go 不动），降低 RPM 撞限频率。回归用例：`test_circuit_breaker_recovery.py` force/cooldown 2 项、`test_llm_api_retry_errors.py` 429 首试熔断/单次请求/失败原因 3 项改写 + 非 429 默认冷却 1 项、`test_llm_api_attempt.py` 底层 kind 断言、`test_skeleton.py` 重试 3 项。运维观察项：kimi 系双端点配额与全挂时段网络环境，现有 WARNING 日志已可观测。
- rf-648 已修复（2026-10-09，财报链路 source_hint 命名空间碰撞；根因经真实网络探测确认）：13 次 HTTP 探测两源全 200 健康（0.11~3.09s，无 401/403）排除网络/反爬/报告期假设——DataSinking 索引条目自带自由文本 `source="巨潮资讯网 (cninfo)"`（描述爬取出处），`_attempt_candidates` 直传 `source_hint` 后 `DataSinkReportAdapter`/`CninfoReportAdapter` 双双判异源**静默拒服务**（0ms、零 HTTP、不写 reason，日志只剩「返回空（返回空）」），主源整条 7 天 `datasink 成功`=0，靠巨潮备源+缓存兜底（标的层 6/6 轮全成）；口径纠偏：259 = 6 轮链路级失败（44×5+39），当轮 A 股标的仅 8 只。修复：① `financial_report` 新增 `_candidate_source` 来源归一（仅精确 `cninfo` 字面量判备源，自由文本/缺省归主源——使用点归一使旧缓存同样受益）+ `_index_source_of` 同规则精确匹配（主源索引不再错记备源名下）；② `_fetch_sections` 传 source，备源候选跳过主源 sections 探测（每轮 10 次 404 与历史 20~27s 挂起的次生根因）；③ 全文阶 `_fetch_document` 补传 source/meta（每轮 1 次跨源 404）；④ 两适配器异源拒服务写 `last_reason` + DEBUG 日志（隔离不再伪装成源返回空）。回归用例：`test_financial_report.py::TestSourceNormalization` 6 项 + `test_report_backup_source.py::TestAdapterRefusalReason` 2 项；13 处旧签名 lambda 适配 source 参数。验收（运行时观察）：下轮生成 `datasink 成功` 出现、`全链路失败` 归零。
- rf-649 已修复（2026-10-09，横幅日志级别）：`features.log_experimental_features` 全部 `logger.error` → `logger.info`（含 `====` 装饰线与全部 `⚗` 子项行），docstring 同步改为级别语义说明——横幅是生成条件提示非错误；72h 窗口 68 条 ERROR 中 65 条为该横幅的历史污染消除，错误统计恢复信号意义；醒目由 log_reader 装饰横幅标记与报告产物实验标注承担。回归用例 `test_features.py::TestBannerLogLevel`（横幅行全 INFO、零 ERROR，开关状态 finally 恢复）。
- rf-650 已修复（2026-10-09，东财反爬节流 + 穿透写入降级防御）：① `eastmoney_industry` push2 每次请求前 `random.uniform(0.05, 0.2)` 随机间隔（`_PUSH2_THROTTLE`），防批量同速连续请求触发服务端反爬断连（25 次 Server disconnected 均为同速批量场景）；测试侧 autouse fixture 屏蔽真睡，专项用例断言节流档位与 sleep 调用；② `penetration_sheet.write_penetration_sheet` 空数据分支改 `result.get("top10")`——直接覆盖 KeyError 成因路径（降级占位空 dict 传入；`_build_penetration_result` 单出口恒带 top10 键反证 compute 正常不缺键），空数据优雅走「暂无穿透数据」分支而非整表写入失败；edge 用例 `test_penetration_sheet_edge.py` 回归。成因未单点定位到唯一路径，防御覆盖全部已知路径；若后续观测到「暂无数据」占比异常另立条目。


### 归档档案

- [`archived_review-findings.0.12.x.md`](../archive/v0.12.x/archived_review-findings.0.12.x.md) — v0.12.1 ~ v0.12.7 批次（2026-10-03 ~ 2026-10-09）
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
