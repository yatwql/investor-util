# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.13-dev
> **编号源**：`rf-next = 276`（新增问题取此编号，完成后更新为 +1；已用最大 rf-275，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
| **rf-75** | `core/registry.py` | 665 | 维持现状（中央注册表被 56 文件引用，数据表内聚） | 报告章节/缓存TTL/LLM模块/数据模块 4 个注册职责（不拆） |
| **rf-78** | `fetcher/batch.py` | 564 | 维持现状（BatchDispatcher 本身内聚，复核确认不拆） | BatchDispatcher 本身内聚，可维持现状（不拆） |
| **rf-79** | `core/code_utils.py` | 542 | 维持现状（500-800 区间内聚文件） | 可考虑将 `estimate_market_cap_by_prefix()` 等非核心判定函数移出（不拆） |
| **rf-80** | `report/data_status.py` | 536 | 维持现状（DegradationTracker 单类，内部职责内聚） | DegradationTracker 单类偏大（不拆） |
| **rf-81** | `report/html_renderers.py` | 526 | 维持现状（render 函数属同一渲染域，拆分收益有限） | 所有 HTML render 函数揉合一体（不拆） |
| **rf-85** | `fetcher/fund.py` | 401 | 未超限（<500，维持现状） | 排名/持仓/基准三职责可拆分为子模块 |
| **rf-86** | `cache/operations.py` | 635 | 500-800 可选优化区间（2026-08-05 实测 635，较登记值 472 增长 163，跨过 500 线，关注后续增长） | 数据结构定义/基金刷新/公共缓存/持仓缓存/缓存清理 5 个职责 |
| **rf-89** | `report/excel_generator.py` | 423 | 未超限（<500，维持现状；2026-08-05 实测 423，较登记值 477 下降，重构后缩减） | Excel 编排器 |

#### P2B — Web 模式遗留技术债（2026-08-06）

> plan-8 三阶段已实现并提交（含 changelog 阶段 1/2/3 条目），以下为文档核对/自审发现的代码与验证遗留项。

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui.md` 验收标准），完成后回填 changelog、本表移至已修复。**2026-08-08 另机 Firefox 153 走查**：首次走查即发现阻断级缺陷 rf-274（`/static/main.js` 404 → JS/CSS 未加载，前端整页失效），已修复；其余 UX 项（渲染/上传/进度可视化/375px/按钮态）待用户在修复后版本上复验后回填 |

## 已解决问题（变更详情见 changelog.md 对应条目）

> 2026-08-07 全面核对：以下各项均已修复并在 changelog.md 相应版本段登记（rf-261 为 plan-25 实现、rf-272 为 ARG001 死参数全数处置，完成时均处于待处理段，本次核对后移入本区）。

| # | 摘要 | 变更记录 |
|---|------|----------|
| rf-248 | test-chart.html 动态注入 chart 脚本未设 `s.async=false` → 注入循环补 `s.async=false` 对齐报告模板 defer 语义 | `changelog.md` [0.10.10-dev] |
| rf-249 | 折线/雷达图 tooltip 悬停无法触发（`pointRadius:0` + `intersect:true`）→ `lineOptions`/radar 补 `interaction`；调试页自检时序 800ms 误报 → onload 触发；offline 文案修正 | `changelog.md` [0.10.10-dev] |
| rf-250 | 调试页自检用 `canvas._chart` 判定接管（v4 无此句柄恒假）→ 改官方 API `Chart.getChart(canvas)` | `changelog.md` [0.10.10-dev] |
| rf-251 | chart-init 守卫不拦截空数组致 empty 场景 TypeError → 6 处守卫补 `!ds.labels.length` + `!ds.datasets.length` 显式跳过 | `changelog.md` [0.10.10-dev] |
| rf-252 | Web 上传预检伪装 zip 致 `KeyError` 逃逸 → `_prevalidate` 任意异常统一转 UPLOAD_BAD_FILE + edge 测试 | `changelog.md` [0.10.10-dev] |
| rf-253 | `RunManager._trim_runs` 仅 submit 时调用致注册表超限 → worker finally 分支补 `_trim_runs()` 持锁清理 | `changelog.md` [0.10.10-dev] |
| rf-254 | `_build_artifacts` 对 failed/严重失败仍返回产物按钮 → 空列表（无产物即无按钮）+ 四用例回归 | `changelog.md` [0.10.10-dev] plan-8 阶段2 |
| rf-255 | `check-doc-traces.py` 裸版本号模式误判 IP → `_line_exempt()` 增 IPv4 整行豁免 + 双用例回归 | `changelog.md` [0.10.10-dev] plan-8 阶段3 |
| rf-256 | `output_dir` 锁文件检测未实现 → server 启动原子抢占写锁 + 占用警告 + 11 用例 | `changelog.md` [0.10.10-dev] |
| rf-258 | Web 前端无自动化测试 → 沉淀 `scripts/smoke-web.py` 可复跑脚本（test_client 全链路 9/9）+ test_smoke_web.py 载体 | `changelog.md` [0.10.11] |
| rf-259 | HTML 报告非自包含（外链 Chart.js 下载后空白）→ `_inline_js_assets` 内嵌 8 资产，报告单文件自包含 + 6 用例 | `changelog.md` [0.10.11] |
| rf-260 | Web 状态区缺系统信息 → `_build_system_info`（版本/IP/LLM 状态）+ 状态区卡片 + 7 用例 | `changelog.md` [0.10.11] |
| rf-262 | `how-to-config.md` §M 功能开关表未列全 → 逐项补全 27 个 key + 计数修正 + faq 补充 | `changelog.md` [0.10.11] |
| rf-263 | `run_health_checks` 的 `max_timeout` 死参数 → daemon 线程 + 整体耗时预算，预算耗尽返回部分结果 + 回归用例 | `changelog.md` [0.10.11] |
| rf-264 | Web 首页系统信息卡缺 TUI 首页摘要对齐字段 → 增补配置摘要字段 + 6 用例 | `changelog.md` [0.10.12-dev] |
| rf-265 | 应用名称硬编码散落 → `constants.py` 新增 `APP_NAME` 单一来源，TUI/Web/HTML/Excel 各入口统一强调名称与版本 + 4 处测试 | `changelog.md` [0.10.12-dev] |
| rf-266 | `src/static/README.md` 资产说明滞后（仅图表 bundle）→ 重写为三类资产总览（图表/web/tmpl），原内容保留子节 | `changelog.md` [0.10.12-dev] plan-27 |
| rf-267 | `smoke-web.py` 改写 `_DEFAULT_CONFIG` 不还原污染默认值 → `run_smoke` finally 统一还原 + 失效缓存；web+config 同进程 282 全绿 | `changelog.md` [0.10.12-dev] plan-26 |
| rf-268 | 三模式文档体系建立后相关文档未同步（folders 重复/统计滞后、README 链接、CLAUDE.md 顺序）→ 去重 + 刷新 + 链接统一 | `changelog.md` [0.10.12-dev] plan-28 |
| rf-269 | 提交 `3026ffa7`（README/CLAUDE.md 索引统一）未登记 changelog → 补登记独立条目 | `changelog.md` [0.10.12-dev] plan-28 |
| rf-270 | folders.md 目录树描述过时 + 树形符号错误 → ①② 计数修正（9→11、25→26）、③④ `└──`→`├──` | `changelog.md` [0.10.13-dev] |
| rf-261 | Web 上传跑 full/both 污染共享快照目录 `data/history/snapshots/` → **试算/正式双模式**：web 默认试算（快照入 `snapshots/web/` namespace 子目录），正式更新显式选择（上传覆盖或直接用存量） | `changelog.md` [0.10.12] plan-25 |
| rf-272 | 全仓 **43 处 ARG001 未用函数参数**全数处置：① 删参 21 处（含 40+ 调用点/测试同步）② 契约保留 7 处加 `# noqa: ARG001`（sina_kline start_from、is_enable_llm config、_compute_ncols 3×、check_liquidity total_mv）③ 独立项 3 项不纳入本轮（见下） | `changelog.md` [0.10.13-dev] |
| rf-271 | `analysis/scenario.py` 两个死参数——① `scenario_analysis()` 的 `portfolio_volatility`（docstring 承诺 ±1σ/±2σ 波动率区间但从未消费，调用方已传 `annualized_volatility` 被吞）；② `sharpe_ci_propagation()` 的 `annual_volatility`（Lo(2002) 常数近似不消费）。**深入评估（2026-08-07）**：死的不止参数——`vol_*`/`ci_*` 输出字段全仓零消费（LLM 唯一消费方 `_build_scenario_block` 只读点估计），`sharpe_ci_propagation` 无生产调用；设计承诺（P4-03）的 CI 区间从未进入 prompt。**处置（方向 2：删除）**：删 2 参数 + 2 生产调用点（_full_risk_metrics/_pipeline）+ 8 处测试调用点（7 处单元位置传参 + e2e_perf 关键字传参）+ docstring/模块 docstring 诚实化（修正「年化波动率 CI → 夏普 CI」为实际「Lo 常数近似」）；`vol_*`/CI 输出字段保留为结构化输出。 | `changelog.md` [0.10.13-dev] |
| rf-273 | 全量测试（mode all）进程退出阶段出现 `--- Logging error ---` 噪声：`tui.py` 模块级 `atexit.register(log_app_boundary, "关闭", ...)` 在 pytest 关闭 sys.stderr 后执行，console `StreamHandler` emit 抛 `ValueError: I/O operation on closed file`，logging 默认 `handleError` 打印噪声（无害但污染输出）。**修复**：`core/logger.py` 新增 `_ClosedStreamSilentHandler`（`StreamHandler` 子类，`handleError` 仅对 "closed file" 竞态静默降级，其余日志错误照常报告），`setup_logger` 控制台 handler 换用；新增 `test_logger.py` 4 用例回归。 | `changelog.md` [0.10.13-dev] |
| rf-274 | Web 前端静态资产 404（阻断级）：Flask 未显式指定 `static_url_path` 时按 `static_folder` basename 推导（`src/static/web/` → `/web/*`），index.html 引用的 `/static/main.js`、`/static/style.css` 全 404 → JS/CSS 未加载，前端整页失效（配置面板空白、健康区卡静态"正在检测"、生成按钮灰色）。plan-27 前端资产移入 `src/static/` 时引入，移动后未在真实浏览器验证。**修复**：`app.py` 显式 `static_url_path="/static"`；新增 `test_web_static_serving.py` 3 用例（静态路由固定 /static + index 全部资产 200 + main.js 可访问）回归；连带补强：`smoke-web.py` 页面渲染检查升级为实际请求全部 `/static/*` 资产断言 200（原仅查引用串存在，同类 404 会漏过冒烟）。 | `changelog.md` [0.10.13-dev] |
| rf-275 | main.js 旧浏览器兼容隐患（排查 rf-274 时发现）：`AbortSignal.timeout`（Chrome 103+/Safari 16+ 起才有）缺失时 `fetch(url, {signal: AbortSignal.timeout(...)})` 构造参数**同步抛 TypeError** → init 在 loadHealth 处中断，后续 loadHistory/loadConfigEdit 全部静默不执行（同 rf-274 症状但不同根因）。**修复**：main.js 顶部补 `AbortSignal.timeout` 兼容兜底（AbortController+setTimeout，无 AbortController 则退化 undefined 信号）+ init 三加载器改 `safeRun` 隔离（任一初始化异常只渲染对应面板错误，不连带中断其余）。 | `changelog.md` [0.10.13-dev] |

> **独立项（rf-272 处置衍生，单列跟踪）**：`html_renderers._render_llm_content_section` 13 参渲染器上下文（删除需重构 html_writer.py 调用点，单列「签名瘦身」）；`report/_pipeline.py` 遗留重复文件（已标注不承载活代码，单列清理项）；`orchestrator.generate_report.warm_cache`（CLI `--warm` 标志去留待决策，已无实际消费路径）。

> v0.10.8/v0.10.9 发布时已修复项（rf-234~rf-247）已整体迁入 [归档档案](#归档档案) 的 `archived_review-findings.0.10.x.md`。

## 归档

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.8（2026-08-04 ~ 2026-08-06，rf-204~rf-247）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
