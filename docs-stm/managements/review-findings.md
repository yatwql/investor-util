# 投资复盘助手 - 自我审查问题记录
> 文档版本：0.11.7-dev
> **编号源**：`rf-next = 460`（新增问题取此编号，完成后更新为 +1；已用最大 rf-459，递增保证唯一，归档不回收。若与历史归档冲突，运行 `scripts/check-task-numbering.py` 校验）

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
## 已解决问题

### 已解决待归档（v0.11.7-dev）

| **rf-458** | **「本机/CI 只有 UTF-8 locale」使 locale 回退类缺陷结构性不可见**（用户质问「两个系统的基本要求不是会覆盖的吗」）：rf-457 那条缺陷在仓库测试面上**无法暴露**——本机 `locale.getpreferredencoding()=UTF-8`、CI 三个 job 全为 `ubuntu-latest`（矩阵仅 Python 3.11/3.12/3.13，无 Windows、无非 UTF-8 locale），而 UTF-8 locale 下 pip 的最后一档回退恰好就是 UTF-8，故 3309 条 `dev-verify` 全绿也拦不住。同源暴露面：生产代码 `src/python/report/excel_writer.py` 输出目录可写性探针 `open(..., "a")` 与 8 个测试文件 24 处 `open(..., "w")` / `write_text()` / `subprocess.run(text=True)` 未显式 `encoding=`（cp936 上静默写 GBK / 直接报错） | ① CI 新增阻塞 job `portability`：固定 `pip==24.3.1`（最后一版按「BOM → PEP263 cookie → locale 编码」解码）+ `LC_ALL=C`/`PYTHONCOERCECLOCALE=0`/`PYTHONUTF8=0` 真实解析 `requirements.txt`（本地已双向验证：带 BOM 正常、去 BOM 即复现报错），并在 `PYTHONWARNDEFAULTENCODING=1` 下跑 `src/test/unit` 全量；② `pytest.ini` 置 `filterwarnings = error::EncodingWarning` + `openpyxl.worksheet._writer` 上游豁免（该模块内部 `NamedTemporaryFile(mode='w+')` 无 encoding；写/读共用同一 codec、zip 条目仍为 UTF-8，实测无用户可见影响）；③ 生产 1 处改为二进制可写性探针（`open(..., "ab")`），测试 8 文件 24 处补 `encoding="utf-8"`（含 2 处 `subprocess.run(..., text=True)`）；④ 文档：`CLAUDE.md` 编码纪律从「Windows 脚本」泛化为按消费方表达（非 ASCII + 被 locale 回退型工具读 ⇒ 必须 BOM）并禁止隐式编码，`developer-guide.md` 新增「编码/locale 自检」段（含不采用 Windows runner 与 GB18030 全套件探针的理由），`testplan.md` §6.4 新增第 17 项门禁，`folders.md` 同步 `pytest.ini` 说明 |

> **探测方法纠偏（留证）**：`LC_ALL=C` 全套件初跑报 47 处失败，逐条定位后确认其中 18 处为 POSIX `fsencoding=ascii` 无法编码中文**文件名**的伪影（cp936 Windows 侧正常），另有 31 处来自 openpyxl 内部 tempfile——最终改用「精确模拟消费方」的两道探针，而非「换整套 locale 跑全套件」。

| **rf-459** | **CI 首次运行暴露的既存测试隔离泄漏 + CI 选择口径遗漏**（用户报「github ci 报错」）：新增 `portability` job 的严格档在清洁树上失败，含两条*与编码无关*的用例——`test_cli_edge.py::TestCliEdge::test_no_input_in_report_path` 与 `test_cli.py::TestHandleWhatif::test_effective_date_passthrough`。根因两重：**① mock 打错调用点** —— 前者 patch `_cli_read_holdings`，而 `_handle_report` 实际调 `_cli_read_holdings_with_flows`；后者只 stub 目标持仓的 `read_holdings`，未 stub 基准持仓的 `_cli_read_holdings` → 二者双双静默回退到**真实文件读取**，只在开发机存在 `data/holdings/个人投资持仓信息.xlsx` 时「恰好绿」（实测：将 `data/holdings/` 移走后**不带严格档也红**；干净 clone 下日志即 `cli.py:323 持仓文件不存在`）；**② CI 选择口径缺席** —— `dev-verify` 的 marker 表达式为 `(unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts or unit_web) and not (edge or data)`、`verify` 亦不含 `unit_cli`，故这两条在 CI 上**从未运行过**，新 job 无过滤跑完整 `src/test/unit` 时首次暴露 | ① 两条用例改为 patch 真实调用点（`_cli_read_holdings_with_flows` 返回 `(holdings, [], [])`；whatif 用例补 `_cli_read_holdings` stub），并在原位置以注释说明「只 patch 另一个名字会静默回退到真实文件」；② 验证：`data/holdings/` 临时移走后上述用例仍全绿（已恢复现场）；③ 收益：`portability` job 从此实际承担「**清洁树 + 全量单元（含 `unit_cli` / `edge`）**」的隔离回归——CI 选择口径的空白由它兜住（是否需要把 `unit_cli` 正式并入 P0/P1 模式选择另议） |

| # | 问题 | 修复 |
|---|------|------|
| **rf-457** | **`requirements.txt` 含中文注释但无 UTF-8 BOM → 中文 Windows 上装依赖中断**（另一台 Windows 机实测报障）：plan-50 给 `requirements.txt` 的 `pdfplumber` / `Pillow` 两行追加中文注释，而文件仍为 UTF-8 **无 BOM**；中文 Windows 的 locale 是 cp936，该机 venv 的 pip ≤24.x 按「BOM → PEP263 cookie → locale 编码」次序解码，前两档均无 → 回退 cp936 解码 UTF-8 字节，`launch.ps1` 「正在安装依赖 ...」瞬间抛 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xac in position 225`，依赖装不上、启动中断。本机 Linux 与 CI 均为 UTF-8 locale，pip ≥25 起更已默认 UTF-8（新版连 `auto_decode` 模块都已移除），故该缺陷只在「旧 pip + 非 UTF-8 locale」组合上暴露，全绿门禁拦不住 | ① `requirements.txt` 加 UTF-8 BOM（`EF BB BF`）——pip 任意版本的 `BOMS` 判定优先于 locale 回退；实测 pip 25.1.1 `_decode_req_file` 与 pip 24.3.1 `auto_decode`（强制 cp936）均正常解析、BOM 不污染首行、中文注释保留；② `.editorconfig` 新增 `[requirements.txt] charset = utf-8-bom`（默认 `[*] charset = utf-8` 会让编辑器保存时剥掉 BOM，必须显式覆盖）；③ `CLAUDE.md` 编码/BOM 约定补该条与成因；④ 回归用例 +3（`src/test/unit/scripts/test_script_encoding.py::TestRequirementsFileEncoding`）：非 ASCII 内容必须带 BOM、复刻 pip ≤24 解码次序并在强制 cp936 下断言与 UTF-8 直读一致（**去 BOM 即复现 `'gbk' codec can't decode byte 0xac`**，已验证）、BOM 仅允许作文件头；⑤ `folders.md` 的 `.editorconfig` 与 `test_script_encoding.py` 两处说明同步 |

### 归档档案

- [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) — rf-380 ~ rf-456（v0.11.0 ~ v0.11.6 批次：v0.11.1~v0.11.3 于 2026-09-18 / 2026-09-24 并入，v0.11.4~v0.11.6 批次（rf-428 ~ rf-456）于 2026-09-26 并入）
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
