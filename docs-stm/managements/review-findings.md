# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.10.17-dev
> **编号源**：`rf-next = 321`（新增问题取此编号，完成后更新为 +1；已用最大 rf-320，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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

#### P2D — LLM 缓存指纹同源与覆盖问题（2026-09-10 plan-31 实现期自审发现）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-308** | `health_check` 缓存指纹**覆盖不足（欠敏感）**——与已修复的 rf-305 同类：`degradation_events`（降级事件日志）经 `_build_data_quality_detail_block()` 渲染成【数据质量详细状态】段**进入 `health_check` 提示词**，却不进入其指纹。后果与 rf-305 同形但更严重：**报告可能在陈述与当前事实相反的数据健康结论**——10:00 数据源故障时生成并缓存「连接失败: xxx(N次)」，14:00 故障恢复后重新出报告，持仓未变故键未变 → 预检命中旧键 → 显示「连接失败」而实际一切正常，不报错、用户无从察觉。`llm-technical.md` §7.1/§13 曾明确记「health_check 缓存指纹不含提示词内容，故该修复在下次缓存未命中时自然生效」——该取舍在「提示词内容覆盖」纪律成立前作出 | 纳入 `ModuleFingerprintInputs`（哈希**已渲染**的数据质量块，与 rf-305 同法——一次渲染、两侧共享同一实例）。**须先量化的成本项**：降级事件集在一日内随数据源抖动而变，纳入后 source 抖动期间 `health_check` 会随事件集变化反复 miss（TTL 24h 下的重算成本）；须确认真实运行中事件集变更频率，若过高则改用「降级**有无**+ 触发降级计数」等稳定摘要而非整块哈希。**改动前须先补覆盖性断言测试**（降级块内容变化 → 指纹随之变化）。登记待定：属行为变更，需与用户确认取舍 |
#### P2E — DeepSeek 旧模型名定价口径待确认（2026-09-10 接入 `deepseek-flash` 时自审发现）

| # | 问题 | 修复方向 |
|---|------|----------|
| **rf-303** | 接入 V4.1-Flash 正式名时核对 `MODEL_PRICING` 的 DeepSeek 条目，发现两处既有口径未经官方确认：① **`deepseek-reasoner` 无定价条目**——该模型名目前仍被 DeepSeek 端点接受，但 `estimate_cost()` 对其返回 `"-"`，费用页签显示为空；② **`deepseek-chat` 单价来源存疑**——本表按 V3（1.50/4.50/0.05）单独定价，而 DeepSeek 文档称 `deepseek-chat` 与 `deepseek-reasoner` 分别是 V4-Flash 的「非思考 / 思考模式」别名（若属实，二者应随 flash 系列走 09-10 降价后的 1.00/4.00/0.02，且 `deepseek-reasoner` 应有条目） | 以 DeepSeek 官方文档确认两个模型名的**当前语义与单价归属**后再定：若确为 v4-flash 别名，则为 `deepseek-reasoner` 增加条目并核对 `deepseek-chat` 单价（须同步 `[0.10.16]` 起 flash 系列降价口径）；若 `deepseek-chat` 已固化为独立 V3 端点则维持现值并补注释说明。**改动前须先补「模型名 → 单价」断言测试**，避免误改导致费用估算偏移。低优先级：项目配置、文档示例与测试均未使用这两个模型名 |

## 已解决问题

### 已解决待归档（v0.10.17-dev）

| # | 问题摘要 | 解决方式 |
|---|----------|----------|
| **rf-310** | 报告管线实验挂载点的**守护语义被复制四份**：决策结算/登记、LLM 决策注入、模块质量横幅、确定性信号沉淀四个挂载点各自内联 `try/except Exception` + `reporter.warn` + `logger.exception`，告警文案与日志标签逐处重写（改一处必漏三处，与缓存指纹「读写两份拼接」同一病根）；且 `report/_report_generation.py` 因这四个内联块**越过 800 行硬上限**（实测 817 行）；挂载点本身**零直接测试覆盖**——内联在管线函数中只能靠驱动整条报告管线覆盖，开关判定与数据注入此前无任何直接断言 | 抽出 `report/_experimental_seams.py`：四个挂载点收敛为四个函数，共用一份 `_guarded()` 守护（异常 → 一条告警 + 一条异常日志 + 兜底值，绝不外抛），被调子模块在挂载点内**按需导入**（开关关闭时不付导入成本，导入期异常落入同一守护）；`_report_generation.py` 降至 736 行回到上限内，且只按序调用挂载点。**挂载点工序顺序契约**（结算先于 LLM 拉取 / 质量横幅晚于决策登记 / 信号沉淀晚于 LLM 生成）与其理由写入模块 docstring，该机制同时登记为架构设计约束表的挂载点集中约束行。新增 `src/test/unit/report/test_experimental_seams.py` 16 例（开关关 → 无副作用 / 开关开 → 按契约向 `pipeline_data` 注入 / 下游异常 → 只告警不外抛且返回输入原对象 / 缺下游符号 → 安全降级 / 被调子模块确为按需导入），含 AST 断言「四个挂载点的调用顺序固定」与「除进度上报器外无 report 子模块被提前导入」。已验证四个方向变异各自转红（去掉开关判定 / 收窄守护范围 / 改横幅兜底值 / 交换调用顺序）。变更详情见 changelog.md [0.10.17-dev] 对应条目 |
| **rf-311** | 体检（`doctor`）的目录写入探针**落到用户真实目录**：探针以 `output_dir`、`data/cache/`、`logs/` 为目标写入再删除 `.doctor_write_probe` 以验证「目录存在且可写」，但目标列表在函数内直接取自配置，**无任何可替换的注入点**——测试运行体检时探针作用于用户的真实 `reports/`/`data/cache/`/`logs/`（实测真实报告目录出现 `.doctor_write_probe` 残留），违反「测试不得修改用户数据」的敏感路径隔离纪律 | 把探针目标提为**单一可替换来源** `_probe_targets()`（返回值即探针实际作用的目录列表），`conftest.py` 增加 session 级 fixture 将 `_probe_targets` 重定向到临时目录。已验证端到端生效：体检运行中探针解析到 `pytest` 临时目录，真实 `reports/`/`data/cache/`/`logs/` 无 `.doctor_write_probe` 残留。变更详情见 changelog.md [0.10.17-dev] 对应条目 |
| **rf-309** | `check-sources` 结果行的**符号与统计口径不一致**：统计分支判 `"timeout" in message or "超时" in message` 两种措辞，符号分支只判 `"timeout"`。而本文件自身产生的预算超时行消息是 `超时（预算 15s）`（无 "timeout" 子串），于是该行**被计入 `warn_count` 却渲染成 `_ERR`（红色错误）**——同一行自相矛盾（汇总行说「⚠️ 1」、行首说「❌」）——计数是对的（退出码仍为告警级 1），**渲染是错的**，用户据此以为源故障要排查，而实际只是本次探测超预算。在 plan-38 改造该分支（新增凭据跳过态）时发现 | 把措辞判定提为单一变量 `timed_out = "timeout" in msg.lower() or "超时" in msg`，统计与符号两处共用，口径归一；新增 2 例回归测试（预算超时行渲染为 `_WARN` 且汇总计入告警、退出码 1；真实失败仍渲染 `_ERR` 且退出码 2，防修复过度放宽），已验证把符号分支退回旧判据后首例转红（实测行首为 ❌）。变更详情见 changelog.md [0.10.17-dev] 对应条目 |
| **rf-305** | LLM 模块缓存指纹**覆盖不足（欠敏感）**——与「读写不同源」属不同类别：`competitive_context`（`_build_competitive_context_block` 生成的业绩基准与竞品对比块）与 `metrics`（量化指标）**参与提示词构造，却不进入任何模块指纹**。当持仓未变、但基准指数或竞品行情变动使对比块内容变化时，指纹不变 → 预检命中旧键 → 运行期直接复用旧内容，**提示词与缓存键脱钩**。两侧一致缺失（写侧与预检侧同缺 `competitive_context`/`metrics`），因此不产生恒 miss，而是**恒命中过期内容**，用户感知弱。辩论三键（白脸/黑脸/综合）的基础指纹此前经本地自拼 `build_llm_fingerprint` 构造，同样不含二者 | 先按 rf 要求**量化后决定纳入**：全部对市场敏感的模块本已按 `total_mv`/`total_profit`/`total_today_profit` 换键，而对比块正是由这些已被键控的量派生的 ⇒ 边际额外失效≈0；真正新增的失效维度恰是本缺陷的目标（指数动而持仓未动、`comparison_indices` 配置变更、指标重算），且 TTL（expert_review 2h / global_macro 24h）封顶额外成本。实现上确立两条结构性保证：**① 覆盖以「提示词是否真的含该段」为准**（`competitive_context`/`metrics` 只进提示词确实包含它们的模块——`health_check`/`penetration_deep` 的提示词不含这两段，刻意不并入以免纯成本失效）；**② 一次渲染、两侧共享同一实例**（`generate_all_llm()` 渲染一次后同时交给预检侧与写侧；哈希「已渲染文本」而非其输入 dict，使「提示词变 ⇒ 键必变」由构造保证，将来改渲染函数不会悄悄脱钩）。辩论三键由本地自拼收敛为 `debate_procon_fingerprint()`，口径同以辩论提示词实际段落为准（含对比块/指标，**不含** `history_data`/`pipeline_data` 与教训/信号/决策头后缀——辩论提示词无这些段，并入会让三次昂贵调用每份报告必 miss）。新增覆盖性断言测试（「进了提示词必须进键」+「未进提示词的模块不得被并入」+ 预检侧同源 + 辩论口径），并新增「同一实例」断言（`assertIs`）。已验证两处变异转红（摘掉 `expert_review` 的对比块/指标 → 3 例失败；预检侧传空块 → 实例断言失败）。变更详情见 changelog.md [0.10.17-dev] 对应条目 |
| **rf-306** | 命令行实验开关 `--experiment` 对早期返回命令（`doctor` / `check-sources`）**完全无效**：这些命令在 `init_config()` 之前分派（配置损坏时仍须可用，属有意设计），而应用命令行开关的调用在其后才执行，故参数被静默忽略——`doctor` 会报告「实验开关关闭」而用户明明指定了该开关，据此判断实验功能状态即得相反答案 | 早返回分支内改为「先读 features.json 覆写、再叠加命令行增量」（与配置初始化顺序一致，避免被覆写值回冲），抽出 `_prepare_early_exit_experiments()` 承载该顺序；新增 4 例回归测试（含「不传开关保持默认」对照组与「覆写先于命令行」顺序守卫），已验证去掉修复后 3 例转红。变更详情见 changelog.md [0.10.17-dev] 对应条目 |
| **rf-307** | **`python -m src.python.cli` 的退出码恒为 0**：`cli/__main__.py` 只调 `main()` 而丢弃其返回值（`cli.py` 自身作为脚本直跑时才 `sys.exit(main())`，两条入口行为不一致）。退出码是本项目命令对外契约的一部分——`doctor` 用 1/2 表达「部分失败/严重」、`cassettes --verify` 用 2 表达「解析失败」、`report`/`cache`/`whatif` 亦然——而 `scripts/cli.sh`、`scripts/cli.ps1`、cron、CI 全部经 `python -m src.python.cli` 调用，故失败对外一律表现为成功，脚本化调用无法据此判断成败（在 plan-37 自测 `cassettes --verify` 时被实证：损坏 cassette 已打印 `[ERR]`，进程仍返回 0） | 抽出 `run_cli()`（`cli.py`）承载「执行 `main()` → 退出码/异常 → `SystemExit` + 应用边界日志」的全部逻辑，`cli.py` 直跑分支与 `__main__.py` 共用，两条入口行为归一；新增 6 例回归测试（`run_cli` 的码传递/KBI→130/异常→2/边界日志 + `runpy` 以 `__main__` 身份执行真实入口断言退出码为 7），已验证还原旧 `__main__.py` 后入口用例转红（实测退出码 0 ≠ 7）。变更详情见 changelog.md [0.10.17-dev] 对应条目 |
| **rf-297** | 预检侧与写侧各自拼接同一模块的缓存指纹，已双向漂移（预检侧计入组合风险信号而写侧未计入；写侧计入辩论增强后缀而预检侧未计入）→ 三个模块的读写键永不相等，预检恒不命中、每次报告全量派发 LLM | 抽取 `llm/module_fingerprint.py` 作为模块缓存指纹的**唯一事实来源**，写侧与预检侧改为调用同一构建函数（后缀判定收敛进函数内部），`history_data` 两侧一致计入；该同源要求同时写入技术设计文档的架构设计约束表。变更详情见 changelog.md [0.10.17-dev] 对应条目 |

### 已解决待归档（v0.10.16-dev）

v0.10.16 已解决记录（rf-295 ~ rf-304）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.16 章节（变更详情见 changelog.md [0.10.16] 对应条目）。

### 已解决待归档（v0.10.15-dev）

v0.10.15 已解决记录（rf-288 ~ rf-294）已随发布整体迁入 [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) v0.10.15 章节（变更详情见 changelog.md [0.10.15] 对应条目）。

### 归档档案

- [`archived_review-findings.0.10.x.md`](../archive/v0.10.x/archived_review-findings.0.10.x.md) — v0.10.1 ~ v0.10.16（2026-08-04 ~ 2026-09-10，rf-204 ~ rf-304）
- [`archived_review-findings.0.9.x.md`](../archive/v0.9.x/archived_review-findings.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_review-findings.0.8.x.md`](../archive/v0.8.x/archived_review-findings.0.8.x.md) — 0.8.0 ~ 0.8.10（2026-07-21 ~ 2026-07-30）
- [`archived_review-findings.0.7.x.md`](../archive/v0.7.x/archived_review-findings.0.7.x.md) 
- [`archived_review-findings.0.6.x.md`](../archive/v0.6.x/archived_review-findings.0.6.x.md)
- [`archived_review-findings.0.5.x.md`](../archive/v0.5.x/archived_review-findings.0.5.x.md)
- [`archived_review-findings.0.4.x.md`](../archive/v0.4.x/archived_review-findings.0.4.x.md)
- [`archived_review-findings.0.3.x.md`](../archive/v0.3.x/archived_review-findings.0.3.x.md)
- [`archived_review-findings.0.2.x.md`](../archive/v0.2.x/archived_review-findings.0.2.x.md)
- [`archived_review-findings.0.1.x.md`](../archive/v0.1.x/archived_review-findings.0.1.x.md)
