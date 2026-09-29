# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.9-dev
> **编号源**：`rf-next = 477`（新增问题取此编号，完成后更新为 +1；已用最大 rf-476，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

---

## 当前待处理问题

### P1 — plan-1 交互图表遗留技术债（2026-08-02）

> plan-1 代码与自动化测试已落地，以下为**未实测/计划内延后**项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-113** | plan-1 **Iter 7 全链路浏览器人工验证 6 项全程未实测**（设计文档验收标准 2/3/4/6 标 ⏳）：① 6 图 Chrome/Edge 90+ 真实渲染+交互（Firefox 90+/Safari 14+ 抽验，R17）② 打印 2x DPI 快照 + 浅色强制 + 不跨页 ③ 离线验证（删除/改名 chart.min.js → `typeof Chart` 守卫应跳过、无 JS 报错、回退 Canvas/表格）④ 微信内置浏览器链接 + file:// 两种打开方式实测（R22）⑤ 移动端 375px 图表不溢出（A4）⑥ 禁用 Canvas 后 6 图区域显示 fallback 文本而非空白（A1） | **载体已备齐（2026-08-03）**：①③⑤ 用 `src/static/test-chart.html` 调试页自检（TD8 rf-112 载体；本次修复 rf-159 回归——注入列表补 `chart-common.js`，否则 0/6 全跳过）；②④⑥ 用完整报告（菜单 L/B，`enable_interactive_charts` 默认开）。**勾选清单**：`docs-stm/archive/v0.9.x/chartjs-upgrade/iter7-verification-checklist.md`（已更新至 7 JS 资产 + chart-common.js 依赖说明 + 回撤图数据 span≥60 交易日才渲染的说明），用户另机手工勾选完成后回填 changelog、本表移至已修复。**验证进度（2026-08-06 另机）**：① 全过（ok/degraded 6/6 图渲染 + tooltip、empty 4/6 渲染 + 2 占位、offline 守卫生效，Windows Chrome+Firefox；期间修复 rf-248/249/251）；② 2.1~2.3 过（2x DPI 清晰/浅色主题/不跨页），2.4 afterprint 待补验；③ 3.2~3.4 过（引擎缺失守卫：无 JS 报错、chart-config/chart-init 静默跳过；现代浏览器不渲染 `<canvas>` fallback 文本，图表区域空白，真实报告回退明细表格，见 rf-249 修正）；待补验：② 2.4、③ 3.1（断网渲染）、④ 微信、⑤ 375px、⑥ 禁用 Canvas |
| **rf-114** | TD3/TD-L1：双渲染路径共存——模板保留 Canvas `drawSimpleChart()`（265 行内联 JS）+ Chart.js 渲染器，Flag OFF 时旧路径仍活 | plan-1 稳定 2 版本后（v0.10.0，阶段 2→3 切换，判定标准见 upgrade.md §4.15）删除 `drawSimpleChart()` + Canvas 回退分支 + Feature Flag 条件分支，Chart.js 成唯一渲染器。**2026-08-05 决策：先完成 rf-113 人工验证（确认 Chart.js 真机渲染可靠）后再执行删除** |

### P2A — 文件过长（>500 行，可选优化；**>800 行为硬上限必须拆分**）

> `src/test/conftest.py` 曾达 872 行（超硬上限），已于 2026-09-26 拆分至 672 行 + 新模块 225 行（详见「已解决问题」rf-448）。

| # | 文件 | 行数 | 状态 | 拆分建议 |
|---|------|------|------|----------|
| **rf-75** | `core/registry.py` | 704 | 维持现状（中央注册表被 56 文件引用，数据表内聚；2026-09-26 实测 704，较 2026-09-10 的 666 增长 38——plan-50 财报域槽位/plan-57 等注册项增补） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 578 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆；2026-09-26 实测 578，较登记值 564 增长 14） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 605 | 维持现状（仍在 500-800 区间内聚；2026-09-26 实测 605，较登记值 542 增长 63，主要为符号映射/判定函数增补） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 621 | 维持现状（DegradationTracker 单类，内部职责内聚；2026-09-26 实测 621，较 2026-09-10 的 544 增长 77——provider 归属登记与失败原因可读化增补） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 556 | 维持现状（render 函数属同一渲染域；2026-09-26 实测 556，较 2026-09-10 的 521 增长 35） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 551 | **已跨入 500-800 可选优化区间**（2026-09-26 实测 551，较 2026-09-10 的 405 增长 146——同花顺官方源备源、基准多源判定等增补）；暂维持现状，若再增则按职责拆分 | 排名/持仓/基准三职责可拆分为子模块（后续择机） |
| **rf-86** | `cache/operations.py` | 633 | 500-800 可选优化区间（2026-09-26 实测 633，与 2026-09-10 持平） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 574 | **已跨入 500-800 可选优化区间**（2026-09-26 实测 574，较 2026-09-10 的 427 增长 147——持仓基本面合并页签等增补）；暂维持现状 | 页签编排可进一步下沉到独立 writer（后续择机） |


#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui-implementation.md` §10 三阶段验收标准 + §6.5/§6.6 样式/响应式）。**勾选清单已备齐（2026-09-20）**：`docs-stm/archive/v0.10.x/web-ui/web-ui-verification-checklist.md`（从实际 `index.html` 七卡结构 + `how-to-use-web-mode.md` 手册导出 ①~⑤ 五类 UX 项，含逐步操作步骤与判定标准）。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

#### P2C — 文档与配置口径（2026-09-24）

> 无待处理项（`rf-420` 已修复，见「已解决问题」区）。

#### P2D — 工程卫生（2026-09-29）

> 无待处理项（`rf-474` 已修复，见「已解决问题」区）。

## 已解决问题

### 已解决待归档（v0.11.9-dev）

> 暂无（v0.11.8 批次 rf-461 ~ rf-470 已随发布归档至 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md)）
| **rf-476** | **GitHub CI `test (3.11)` P0 持续失败（3.12/3.13 均绿）**：失败断言 `assert 'HTTP 500' == ''` @ `test_reason_is_thread_local`（「子线程的原因不得泄漏到主线程」）。根因是「provider 失败原因载体」（`providers/_utils._last_reason`，线程本地）**只在 provider 返回 `None` 时被链路消费**——`datasink`/`cninfo` 的用例直接调取数函数只看返回值（不消费原因），写入的 `HTTP 500` 便残留在该 worker 主线程槽位，污染同 worker 中**下一个**读载体的用例。属**真产品缺陷**（残值会串到无关诊断），非测试问题；仅 3.11 暴露是因为各版本 test 分布/顺序不同使两个用例落到同一 worker（本机 3.11/3.13 均不可稳定重现） | **已完成**：① 产品侧——`_utils` 新增 `clear_last_reason()`，`fetcher/chain._try_provider_fetch` 在**每次尝试 provider 之前**先清（保证「本次原因」不可能混入上次残值）；② 测试侧——conftest 新增 autouse fixture `_auto_reset_last_reason`（与 `_auto_reset_provider_registry` 同习语，每用例前复位线程本地载体）；③ 回归 +2（链级残值不串、测试间不串）。**双修复均经验证为 load-bearing**：移除任一修复，对应用例即失败。验证：`test_provider_utils` 8 passed、chain+datasink+cninfo 120 passed；本地 3.11（uv + pip 两套环境）dev-verify 3376 passed ×3 次稳定 |
| **rf-474** | **`ruff format` 漂移残留（`format` CI job 非阻塞故长期未暴露）**：`src/test/unit/report/test_market_value_strategy_edge.py` 有两行 124 字符（超 `line-length = 120`）的 `session_cache_set(...)` 调用未按 ruff 规范化换行，与 CLAUDE.md 「lint/格式为零告警基线」的声明不符 | **已完成**：对该文件执行 `ruff format`（两处语句换行展开，+4 行）；**AST 等价校验证实行为中性**（新旧 `ast.dump` 全等）；`ruff check` 干净、8 例边缘用例全过；同步 `folders.md` 测试代码行数。全仓复校 `ruff format --check src/ scripts/` **736 files 零漂移** |
| **rf-475** | **安全基线用例恒失败（`scenario_security` 不在常规门禁内，bench 全量采集才暴露）**：`test_key_file_permissions_unix` 断言 `data/config/llm_key.json` 与 `data/config/llm_providers.json` 均不得 world-readable，但后者是 **git 跟踪文件**（`git ls-files -s` 记录 `100644`）——任何干净检出的权限都是 `644`，断言必然不成立（实测 mode=644、mtime 2026-09-27，与功能改动无关） | **已完成**：权限基线收窄为「仅**持有密钥本体**的文件」——新增类常量 `_SECRET_FILES = ("data/config/llm_key.json",)` 并注明为何不含 `llm_providers.json`（它只存 `credentials_ref` 指针，真凭据在未跟踪的 `llm_key.json`，且 `.gitignore` 对它显式 `!` 放行入库）；**补** `test_providers_config_has_no_inline_secret` 守住该文件可入库的真正红线（不得内联 `api_key`、`credentials_ref` 必填，与 `unit_config` 同一判据）；修正类 docstring 的基线清单。验证：`security` 模式 **10 passed / 0 failed**；反向核对——向其注入内联 `api_key` 则该用例失败、恢复即通过（非自证） |
| **rf-471** | **TUI 主菜单目录配置入口分散 + 与系统自检争用 `[D]`**（用户要求「增加 [D] 配置目录信息，把 [C]/[F]/[O] 变成其二级选项」）：持仓目录 / 持仓文件名 / 报告输出目录三个同属「路径配置」的入口平铺在主菜单（占 3 个键位），而系统自检占用 `[D]`，二者语义冲突 | ① `tui_menu.MENU_ITEMS`：三项合并为 `[D] 配置目录信息`（20 → 18 项），系统自检键 `D` → `T`（`FEATURE_GATED_ITEMS` 同步）；② `handlers_config._cmd_config_dir_info()`：独立子菜单循环（`[C]`/`[F]`/`[O]` + `[B]` 返回，大小写归一、无效输入重提示、EOF/Ctrl+C 安全返回），子项在调用时取 `handlers_config` 模块全局（可打桩）；③ `tui.py` 回调绑定与 `default_menu_key` 注释同步；④ 回归 +7 例（子菜单分发/大小写/返回/无效输入/EOF，菜单键集与路由 D→`_cmd_config_dir_info`、T→`_cmd_run_doctor`）；⑤ 文档同步：how-to-use-tui-menu / how-to-start / faq / how-to-config(-llm) / how-to-use-web-mode / how-to-use-cli-mode / requirements（R-TUI-02 18 项 + §3.2 菜单表 + R-DIAG-05）/ technical（菜单体系表）/ testplan / test-coverage / folders；代码内提示串（`handlers_log` docstring、`features.doctor_check` 说明）同步 |
| **rf-472** | **巨潮备源（cninfo）的三处取数缺陷：PDF 用元数据超时、不可达主机反复白等、失败原因丢失**（用户贴日志问「所以其实是拿不到信息的么？」）：① `_get_bytes` 与元数据接口共用 `_TIMEOUT = 20.0`，而公告 PDF 是完整年报原文（几十 MB）→ 慢链路下必然「挂起 → 不重试 → 失败」，**从未下成功过**，每次白等一个超时预算；② `cninfo` 是**直连调用（不经 Provider Chain）**，没有会话级熔断——主机不可达时同一轮报告里**每篇文档都重新发起请求、重新白等**（实测 601939 连试 4 次共 160s）；③ provider 返回 `None` 时链路只记笼统的「返回空」，无法区分「源故障」（要排查网络/凭据）与「该文档确实没这一节」（正常业务结果）——本次排查即被误导，实际 DataSinking 主源**完全正常**（直连实测 HTTP 200、626044 篇索引、章节清单可取），是「该季报没有管理层讨论与分析」+ 备源网络不可达共同造成 | ① `cninfo` 新增独立 `_PDF_TIMEOUT = 60.0`，`_get_bytes` 用它（慢链路下年报能真正下下来）；② 新增「主机本会话不可达」短路 `_mark_host_unreachable` / `_is_host_unreachable`（挂起型失败后标记主机，后续请求不发 HTTP 直接失败，把 N × 超时降为 1 次；非超时失败不标记，避免误伤真实可达的主机；`reset_cninfo_unreachable` 支持手动/测试重置）；③ `providers/_utils` 新增**按线程隔离、消费即清**的失败原因载体 `set_last_reason` / `take_last_reason`，`chain._try_provider_fetch` 在 provider 返回 `None` 时读取并**替换笼统的「返回空」**（同时进 `FailureDiagnostics` → 报告数据源矩阵）；`datasink._request` 与 `cninfo` 各分支（无凭据/凭据为空/配额用尽/401-403/429/404 探测/非 200/非 JSON/orgId 未解析/主机不可达/连接超时）逐条自陈原因；④ 回归 +14 例（cninfo PDF 超时预算与会话短路 6、datasink 自陈原因 4、chain 原因透传 2、共享载体线程隔离与消费即清 5）；⑤ 文档：`technical.md` §2.2.1（自陈原因契约 + cninfo 额外护栏）、`datasource-reliability.md`（PDF 超时 / 会话短路 / 可达性取决于本机网络路径）、`testplan.md` R-DATA-07 载体 |
| **rf-473** | **HTML 报告新闻表在手机窄屏下字段错位、信息易错过**（用户报「财经新闻热点与持仓关联分析里，摘要、关联关键词、LLM 关联分析挤在一起，有些地方错位」）：该表 7 列（有 LLM 分析时）且沿用全局 `table { min-width: 600px }`，手机上横向压缩后各列内容互相挤压换行、列边界肉眼难辨，「摘要 / 关联关键词 / LLM 关联分析」三块黏连在一起 | ① 新闻表加 `.news-table` 类作窄屏规则作用域；② `@media (max-width: 768px)` 下**改为卡片式堆叠**——隐去表头、每行化为一张卡片，单元格转块级并用 `td[data-label]::before { content: attr(data-label) }` 生成字段名，序号与标题作卡片头（不显示字段名前缀）、取消 `min-width`；③ 模板补 `news-table` / `news-seq` / `news-title` 类与各字段 `data-label`；④ 回归 +5 例（类名作用域、逐字段 data-label 齐备、窄屏隐表头与堆叠规则、取消 min-width、卡片头规则）；⑤ 文档：`reports-instruction.md` 补「新闻表窄屏卡片布局」说明 |

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — rf-380 ~ rf-470（v0.11.0 ~ v0.11.8 批次：v0.11.1~v0.11.3 于 2026-09-18 / 2026-09-24 并入，v0.11.4~v0.11.6 批次（rf-428 ~ rf-456）于 2026-09-26 并入，v0.11.7 批次（rf-457 ~ rf-460）于 2026-09-27 并入，v0.11.8 批次（rf-461 ~ rf-470）于 2026-09-29 并入）
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
