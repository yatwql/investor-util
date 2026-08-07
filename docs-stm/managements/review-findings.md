# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.12-dev
> **编号源**：`rf-next = 268`（新增问题取此编号，完成后更新为 +1；已用最大 rf-267，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
| **rf-257** | plan-8 Web 模式浏览器真机人工验收未做：冒烟测试为脚本化 HTTP 验证（9/9 过：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离），但未在真实浏览器（Chrome/Edge 90+）人工走查——main.js/style.css 渲染、上传表单 UX、进度事件可视化、375px 响应式、按钮态 | 用户浏览器人工走查（对照 `plan-web-ui.md` 验收标准），完成后回填 changelog、本表移至已修复 |
| **rf-261** | Web 上传持仓跑 full/both 会**污染共享快照目录** `data/history/snapshots/`：上传文件本身已隔离（`web/upload.py` uuid 落盘 `data/holdings/uploads/` + TTL/用完即删），但 full/both 生成时 `capture_snapshot`（`report/_snapshot.py`）基于**本次上传的临时持仓**调 `save()` 持久化快照到**三渠道共享**目录 → TUI/CLI 后续报告的「快照差异/组合演进」会拿 web 测试持仓的历史快照参与对比（`portfolio_evolution` 读 `load_latest`）。`data/cache/`（行情缓存）与 `data/state/`（熔断/降级/性能历史）共享属**架构刻意**（数据降级治理体系全局一致），非缺口；basic 路径明确不落快照（`orchestrator.py` 注释） | **方案已确认（2026-08-07 探讨收敛）**：`data/cache`/`data/state` 保持共享不动（按证券代码/机器键控，非持仓身份数据，隔离反而破坏缓存复用与数据降级治理——伪需求）。按**使用意图**分两模式：① **临时试算（web 默认）**：上传保持 uuid 临时态，快照写入独立子目录 `data/history/snapshots/web/`（`history_snapshot.save/load` 增 namespace 子目录支持），TUI/CLI 读主目录自然排除 web 试算快照，组合演进/快照差异不受污染；② **正式更新（共享，显式选择）**：两种输入——上传覆盖 `data/holdings/{holdings_filename}`（先备份旧文件），或**不上传直接用存量持仓文件**（web 成为完整报告生成入口，符合"最少输入"定位）；快照入共享主目录，演进/对比真实生效。实现要点：`capture_snapshot` 增试算/正式判定（web 默认试算），`history_snapshot` 支持 namespace 子目录，web `_handle_create_run` 增模式参数（trial/formal + use-existing）。**待实现（登记 plan-25）** |
---

## 已修复（摘要）

| # | 问题 | 修复方案 | 变更记录 |
|---|------|----------|----------|
| rf-248 | test-chart.html 调试页动态注入 chart 脚本未设 `s.async=false`（注释「非 async 动态注入按序执行」实为错误认知），动态 script 默认 async=true 无序执行，chart-init.js 先于 chart.min.js/chart-common.js 执行触发守卫静默 return，全场景 0/6 图未初始化、无 tooltip（用户 2026-08-06 实测 ok/degraded/empty 三场景复现） | 注入循环补 `s.async=false` 对齐报告模板 defer 语义；生产模板（report_template/whatif_template）用静态 defer 不受影响 | `changelog.md` [0.10.10-dev] |
| rf-249 | 折线图（净值趋势/最大回撤/演进图 + whatif 回测线图）`pointRadius:0` 且默认 `interaction.intersect:true` → 数据点命中区域≈0，悬停无法触发 tooltip；雷达图 `pointRadius:3` 命中区域小同样难触发（用户 2026-08-06 ok 场景实测：环形图+两柱状图有 tooltip、折线+雷达无）。另：test-chart.html 自检 800ms 早于脚本加载完成误报 0/6；offline 文案「canvas 保留 fallback 文本」为误解（现代浏览器不渲染 `<canvas>` fallback 文本，引擎缺失时图表区域空白，真实报告回退明细表格） | ① chart-common.js `lineOptions` 补 `interaction:{mode:'index',intersect:false}`（悬停任意处显示最近 x 点全数据集值）；② chart-init.js radar 补 `interaction:{mode:'nearest',intersect:false}`；③ test-chart.html 自检改 chart-init.js onload 触发 + 3s 兜底；④ offline 文案与 iter7 清单/review-findings 断言修正为实测行为 | `changelog.md` [0.10.10-dev] |
| rf-250 | test-chart.html 自检用 `canvas._chart` 判定图是否被 Chart.js 接管——v4 该内部句柄不存在（canvas 上挂 `_chartjs` 管理事件监听，`_chart` 是数据集/元素内部引用），判定恒为假；rf-249 修复后图真实渲染、tooltip 可用，但自检仍误报「0/6 图已初始化」（用户 2026-08-06 ok/degraded 场景实测） | 自检判定改官方 API `Chart.getChart(canvas)`（v4 构造内部亦用 `Chart.getChart(canvas)` 查已有图表，与 chart-print/chart-export 用同一 API） | `changelog.md` [0.10.10-dev] |
| rf-251 | chart-init.js 6 个核心图 init 守卫 `!ds.labels`/`!ds.datasets` 不拦截空数组（空数组 truthy），empty 场景（`labels:[]`+`datasets:[]`）下 `ds.datasets[0]` 为 undefined、抛 TypeError，依赖外层 try/catch 降级（图不渲染、console warn 噪声），而非显式空数据跳过 | 6 处守卫统一补 `!ds.labels.length` + `!ds.datasets.length`，空数据优雅 return（对齐生产模板 `{% if labels %}` 空值语义 §4.12，不再依赖异常降级） | `changelog.md` [0.10.10-dev] |
| rf-252 | Web 上传预检（`_prevalidate`）调用 `get_xlsx_info` 未兜底：普通 zip 改 `.xlsx` 扩展名伪装（PK 魔数通过）时 openpyxl 抛 `KeyError`（archive 缺 `[Content_Types].xml`），`get_xlsx_info` 仅捕获 FileNotFoundError/BadZipFile/InvalidFileException/OSError，KeyError 逃逸 → `save_upload` 抛非 UploadError → handler 未捕获 → 500（而非设计预期的 400 UPLOAD_BAD_FILE） | `_prevalidate` 包裹 `get_xlsx_info` 调用，任意异常统一转 UPLOAD_BAD_FILE（防伪装 zip 造成 500）；新增 edge 测试 `test_plain_zip_disguised_as_xlsx` 回归 | `changelog.md` [0.10.10-dev] |
| rf-253 | `RunManager._trim_runs` 仅在 `submit` 时调用：run 由 worker 线程逐条变为 done，批量提交时多数 run 尚未完成，submit 循环结束时 trim 无法清理后续完成的 run → run 注册表超出 `_RUN_KEEP`（测试实测 25 > 20） | worker `_work_loop` 的 finally 分支补 `_trim_runs()`（持锁），run 完成即触发保留上限清理；`test_retention_trim_oldest` 调整等待语义回归 | `changelog.md` [0.10.10-dev] |
| rf-254 | 阶段2 自审：`_build_artifacts` 对 **failed 状态与严重失败（exit_code 2）仍返回产物按钮**——报告未生成时产物文件不存在，前端点击下载/预览只会 404，属错误路径未收敛 | `_build_artifacts` 对 `status == "failed"` 或 `exit_code == 2` 返回空列表（无产物即无按钮）；`TestArtifactsExitCode` 四用例回归（severe/failed 空、partial/success 保留） | `changelog.md` [0.10.10-dev] plan-8 阶段2 |
| rf-255 | 阶段3 自审：`check-doc-traces.py` 裸版本号模式（`0.x.x`，无 v 前缀）把 Web 用户文档正文的 **IP 地址** 误判为版本号——`127.0.0.1:8000` 命中子串 `0.0.1`、`--host 0.0.0.0` 命中子串 `0.0.0`，5 处 Web 文档（how-to-start 方式四 / faq Web 问答）被误报，检查无法通过 | `_line_exempt()` 增加 IPv4 地址（含端口）整行豁免模式 `\b(?:\d{1,3}\.){3}\d{1,3}\b(?::\d{1,5})?`（与既有「当前状态/运行时语义」豁免同性质，仅豁免 IPv4 形态，不削弱裸版本号检出）；`test_ip_address_exempted` + `test_bare_version_still_flagged` 双用例回归 | `changelog.md` [0.10.10-dev] plan-8 阶段3 |
| rf-256 | `output_dir` 锁文件检测未实现：设计文档（`docs-stm/archive/v0.10.x/web-ui/plan-web-ui-implementation.md` 单 worker 串行队列一节）规定「server 启动时检测 `output_dir` 锁文件有占用则警告」，防止多进程共享输出目录互相覆盖产物（web 与 TUI/CLI 并行、或不同端口双 web 实例）；实现仅做端口占用检测（bind 探测），未做输出目录占用检测 | `web/server.py` 启动时对 output_dir 原子抢占写锁 `.investor_output.lock`（`O_CREAT|O_EXCL` 防多进程竞态），锁已被其他入口持有则警告「该输出目录可能正被其他入口占用，产物可能互相覆盖」，持有至进程退出 finally 释放；新增 `src/test/unit/web/test_server.py` 11 用例回归 | `changelog.md` [0.10.10-dev] |
| rf-258 | Web 前端 main.js（状态机/轮询节流/按钮态）无自动化测试，仅后端 Python 单测覆盖（`src/test/unit/web/`，unit_web 标记 64 用例）；冒烟脚本为临时脚本已删除，未沉淀为可复跑脚本 | 前端零 node 工具链约束 → 不引入 Playwright，沉淀 `scripts/smoke-web.py` 可复跑冒烟脚本（Flask test_client 进程内 HTTP 全链路 9/9 断言：页面渲染/健康检查/上传校验/运行 202/进度事件/完成态/产物下载/历史记录/产物目录隔离；管线/健康/历史全 mock，output_dir 与上传目录临时隔离）；新增 `src/test/unit/web/test_smoke_web.py` 载体（unit_web 标记，自动纳入 dev-verify/verify 门禁）；脚本可独立运行 `.venv/bin/python scripts/smoke-web.py` | `changelog.md` [0.10.11] |
| rf-259 | HTML 报告非自包含：报告 HTML 外链 8 个 Chart.js 资产，下载/移动（Web 下载到其他目录、单发移动端）后 JS 找不到 → 资产穿透 TOP10 等图表空白（无头 Chrome 实测 canvas 停默认 500×320，仅 HTML 与 JS 同目录才渲染；用户 `reports/` 正常、Web 下载后空白） | `html_writer_assets.py` 新增 `_inline_js_assets`（内嵌保存前读取 8 个资产 → 移除 head 外链标签 → 按 bundle 依赖序追加行内 `<script>` 到 `</body>` 前，复刻 defer 时序），`html_writer.py`/`whatif_writer.py` 保存前调用 → 报告 HTML 单文件完全自包含；`_copy_js_assets` 保留兜底；新增 `TestInlineJsAssets` 6 用例（unit_report 标记） | `changelog.md` [0.10.11] |
| rf-260 | Web 状态区缺系统信息：TUI 状态面板显示程序版本号/LLM 是否开启（含 endpoint、熔断、模型路由）/本机 IP，Web 模式仅 TUI 有，页面运行状态区无对应展示（用户要求 Web 与 TUI 对齐） | `web/handlers.py` 新增 `_build_system_info`（版本 `APP_VERSION` + 本机 IP `_get_machine_ip` + LLM 状态：flat 单 provider 展示 provider/model/endpoint 简化主机名/熔断/模型路由，credentials_ref 多链展示策略/provider 清单/模块偏好，未配置显示「未配置」，读取异常兜底）；`index.html` 状态区新增「系统信息」卡片（status-grid 改三列）；`style.css` 补 `.status-grid-3` 等样式；新增 `TestSystemInfo` 7 用例（unit_web 标记） | `changelog.md` [0.10.11] |
| rf-262 | `how-to-config.md` §M 功能开关表未列全 27 项 Feature Flag：`llm_*`/`fund_deep_analysis_*`/`news_*`/`metrics_*` 只写通配符未列具体 key；`fund_deep_analysis_*` 计数误写 4 项（实际 2 项）与总数 27 自相矛盾；结尾指引「完整清单以 features.json 注释为准」错误（features.json 唯一不支持注释） | §M 表格补全为逐项列出全部 27 个 key（含默认值+说明，与 `features.py::_FEATURE_FLAGS_DEFAULT` 一致）；修正 `fund_deep_analysis` 计数；删除错误指引改指向源码；faq.md 报告理解新增「HTML 单文件自包含」重点问答 + 修正故障排查过时说法 | `changelog.md` [0.10.11] |
| rf-263 | `run_health_checks` 的 `max_timeout` 是**死参数**：原实现用 `ThreadPoolExecutor` + `as_completed`，线程并行执行、主流程等待全部完成，`max_timeout` 从未真正限制整体耗时——慢速/挂起的数据源会拖住整个健康检查（Web 健康接口需在前端 15s abort 前返回，若超时会 504） | 改为 daemon 线程 + 整体耗时预算：`deadline = perf_counter() + max_timeout`，逐线程 `join(timeout=剩余预算)`，预算耗尽即返回已收集的部分结果，未完成项标记「超时（预算 Ns）」；持锁原子追加 + 竞态兜底（同 name 保留真实结果弃超时占位）；`max_timeout` 成为真正的整体耗时上限；新增 `src/test/unit/core/test_check_sources.py` 回归用例 | `changelog.md` [0.10.11] |
| rf-264 | Web 首页系统信息卡缺 TUI 首页摘要对齐字段：`show_config()` 展示 持仓目录/持仓文件/输出目录/新闻抓取上限/状态（文件是否就绪）/持仓匿名化/隐私声明，Web 首页仅展示 程序版本/本机 IP/LLM（用户要求首页显示 软件版本号/状态/新闻抓取上限/LLM配置信息/模型/策略 等，参考 TUI 首页摘要） | `web/handlers.py` `_build_system_info` 增补配置摘要字段（`get_config()` 读取 holdings_dir/holdings_filename/output_dir/news_top_count、`os.path.exists` 判定 holdings_ready、features.anonymization.mode 中文映射、`get_flag("_privacy_notice_shown")`），配置读取异常按默认值兜底；`index.html` 系统信息卡片补对应行 + `style.css` `.system-status-ok/err` 状态色；`TestSystemInfo` 新增 6 用例（web 目录 89 用例全绿 + smoke 9/9） | `changelog.md` [0.10.12-dev] |
| rf-265 | 应用名称「投资复盘助手」硬编码散落（TUI 首页 tui_menu.py 写死、cli.py/server.py 描述用「生成工具」）、未作为单一来源常量；各入口（TUI 首页/启动日志/Web 首页/HTML 报告首页/Excel 首页）未统一强调应用名称 + 版本号（用户要求固化到 constants.py，报告强调由本应用及版本生成） | `core/constants.py` 新增 `APP_NAME` 单一来源常量；启动日志 `log_app_boundary` 改为「应用启动 \| {APP_NAME} v{APP_VERSION} \| …」；TUI 首页 `print_header` 引用 `APP_NAME`；Web 首页 `_handle_index` 传 `app_name` + index.html 顶部 `<h1>`/副标题强调名称与版本；主报告模板 report_template.html 头部加「由 {app_name} v{app_version} 生成」+ 页脚改「由 {app_name} v{app_version} 生成 · 个人投资分析报告」；whatif 报告模板页脚同加；Excel summary 页签 `_write_basic_info` 增「生成工具」行（`APP_NAME v{APP_VERSION}`）；新增/补强测试 4 处 | `changelog.md` [0.10.12-dev] |
| rf-266 | `src/static/README.md` 资产说明仍仅覆盖图表 bundle（Chart.js 文件清单 + 升级指引），未涵盖 plan-27 归入的 `web/`（Web UI 前端）与 `tmpl/`（报告模板）——目录语义扩大为三类资产后文档说明滞后 | `src/static/README.md` 重写为三类资产总览（图表 bundle 报告生成时复制 / web 前端 Flask `template_folder`+`static_folder` 加载 / 报告模板 `report/html_jinja_env` 加载），原图表文件清单/版本/升级/安全保留为子节 | `changelog.md` [0.10.12-dev] plan-27 |
| rf-267 | `smoke-web.py` `_build_client` 直接改写 `_config_defaults._DEFAULT_CONFIG`（holdings_dir/holdings_filename/output_dir）且运行后不还原，污染模块级默认值——web 套件先跑后，后续 config 测试读到被改写的默认值，致 7 个 config 用例顺序失败（test_corrupted_json/empty_file/missing_file/partial_config_merge/init_creates_default/init_template_writes_relative/set_preserves_other_keys） | `run_smoke` finally 统一还原 `_DEFAULT_CONFIG` 快照 + `_CONFIG_FILE` + `invalidate_config_cache()`；web+config 同进程 282 测试全绿（修复前 7 失败），config 单独 102 passed | `changelog.md` [0.10.12-dev] plan-26 |

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
