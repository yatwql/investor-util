# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.11.2-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 修复 full 路径 HTML 漏接市场情绪契约（2026-09-18，rf-402）

**背景**（用户反馈）：「同花顺，市场情绪没开启么？我看数据可用性矩阵没提到它」。排查确认**开关与 key 均无问题**（`features.json` 已开 `market_sentiment`、hithink key 就绪、`data/cache/sentiment_*` 本次已由同花顺接口刷新），而是 full 路径的 HTML 端接线遗漏。

**现象**：同一次运行的两份产物自相矛盾——xlsx「15.数据源可用性矩阵」有 `市场情绪 | ✅ 正常 | 同花顺金融数据 ×2`、说明表「✅ 已使用」；HTML 两者皆无（矩阵缺该行、说明表「○ 未使用」），情绪区块也不渲染。

**根因**：`report/_report_generation.py::_generate_report_full` 未取数/未注入 `market_sentiment_data`，且 `_generate_full_html_report` 无该形参、其 `write_html_report` 调用未传参；Excel 侧靠 `report/excel_generator.py` 的「就地兜底」在 **HTML 落盘之后**才触发取数（`logs/app.log`：HTML 20.126 → 情绪取数 20.419/20.799 → Excel 21.032）。矩阵只列**本次取用过的类别**，故取数前生成的 HTML 自然缺行。

**变更**：
- 编排层在写 HTML 之前取数并注入 `pipeline_data`（位置与 both 路径一致：`record_prosperity_diagnosis` 之后、`# ── 6. HTML 报告 ──` 之前），并透传 `prep` 以带出穿透标的（与该路径 Excel 的穿透口径一致）
- `_generate_full_html_report` 新增 `market_sentiment_data` 形参并透传 `write_html_report`（HTML 与 Excel 从此同源同序）
- Excel 就地兜底保留（basic 路径不经编排层；注释「full/both 由编排层注入」自此属实）
- 回归用例 2 例（`test_market_sentiment_wiring.py::TestFullPathInjection`：编排注入 / HTML 生成器透传），已实测对修复前代码两者均失败

**验证**：修复前后各跑一次两例（修复前 `assert None is {...}` / `TypeError: unexpected keyword argument` 失败，修复后通过）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 四个 `--ci` 脚本全 [OK]。

### 文案与实现对齐：市场情绪块的描述口径 + 报告组开关计数（2026-09-19，rf-403、rf-404）

**触发**：用户追问「情绪价值会出现在报告的哪个部分？我没看到」。实测确认区块已正常出现（HTML 行动建议章 ⑦ 号内嵌块 / Excel「7.行动建议」页签），只是当日 0 命中——而两份手册恰好把这种情况写反了，所以先修文档。

**两类文案与实现不符**：
- **位置**：`features.py` 的 `market_sentiment` 开关描述写「**新增独立章**」（初稿形态），实际是行动建议章内嵌块——该偏离在设计文档归档里已记录，只是开关描述未随之更新；它恰是功能开关面板/菜单里展示给用户的文字
- **零命中行为**：`data_source_matrix.py` 说明表、`how-to-config.md`、`datasource.md` 三处写「**无命中时该区块不显示/不渲染**」，而实现是**零命中仍渲染**（标题 + 市场概览 + 「（当日无持仓/穿透标的命中龙虎榜或连板梯队）」+ 口径脚注）——两句话叠加，正好把“功能正常、只是无事件”误读成“没开启”
- **报告组开关计数**（rf-400 同类漏改）：`how-to-use-tui-menu.md`（共 29 项 / 报告组 8 项 + 两处清单漏 `market_sentiment`）、`how-to-config.md`（子模块枚举漏）、`folders.md`（28 项 / 8 项）——实况 **30 项（⚗5 / 常规 16 / 报告组 9）**

**变更**：四处描述口径按实现改正（并把“怎么排查是否已取到数”写进手册：矩阵「市场情绪」行 + 说明表「本次使用」+ `logs/app.log` 的 `[market_sentiment] 命中 N 条`）；四处计数/清单按 `feature_switch_registry` 实况更正并补 `market_sentiment`。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 文档与实现全量核对：4 类共 28 处不一致修订（2026-09-19，rf-405~rf-408）

**触发**：用户要求「核对管理文档和用户文档，比对程序和配置文件，查看有没有不一致的地方，要修订」。

**核对口径**：以注册表（`feature_switch_registry` / 章节注册表 `_REPORT_SECTION_DEFAULT` / 数据模块缓存注册表）、`data/config/config.json` + `_DEFAULT_CONFIG`、文件系统、`pytest --collect-only`（`scripts/collect-test-coverage.py`）为事实源，逐条比对 11 份用户文档（README + manuals 10）+ 10 份管理文档。审计脚本（`docs-stm/tmp/audit_phase{1..7}.py`，gitignore）按「提取代码侧事实 → 反向扫文档断言」两面跑。

**修订四类**：
- **统计快照过期（rf-405，12 处）**：`test-coverage.md` 的 unit/standard/all/report/unit 父标记/unit_report/功能域「报告生成」与实测差 2（rf-402 新增的回归用例未回填）；`folders.md` 的主程序与测试代码行数、测试用例数、managements/项目文档行数未随代码与文档变动刷新（含「源代码合计」联动）
- **目录树漏登 9 个文件（rf-406）**：`folders.md` 未随新增文件同步（`fetcher/financial_indicator.py` + 8 个测试文件）→ 按所属子包位置补条目并附职责说明（取自各文件 docstring）；补后重核「实际有而树内缺 0 / 树内有而磁盘无 0」
- **TUI `[S]` 面板编号表与分组实况脱节（rf-407）**：实验块只列 4 项（缺 ⚗ 景气度框架诊断）、常规块 10-25 未随实验组扩容后移、报告块未编号、三处「第 23 项」位置引用失准、`how-to-use-web-mode.md` 实验清单缺项——而编号本是 `handlers_config.py` 从分组与注册表顺序**派生**（设计上非硬编码）→ 按实况重编（实验 6-10 / 常规 11-26 / 报告 27-35）
- **零星数值/表述（rf-408，3 处）**：`requirements.md` 页签编号 1~19 与默认顺序 19 项（实况 17 个报告章节）；`technical.md` 功能语义命名表中 `market_temperature` 标为默认关（实况默认开）；`testplan.md` 「白名单 7 组」→「7 个可编辑面（功能开关面拆两块）」

**核对为一致（未改）**：30 项开关分组计数与清单、报告章节表（17 项）与 Excel sheet 名、13 份版本头（`check-version-consistency`）、`how-to-config.md` 标量默认值表与 `_DEFAULT_CONFIG`、缓存 TTL 表与 LLM 默认 `max_tokens`/`timeout`、CLI 7 个子命令、`providers/` 与数据源清单路由、测试标记与 conftest；另有 2 类扫描报警经核实为误报（`market_temperature_data` 契约名被前缀匹配、`how-to-config.md` 中非开关表被当成开关表），未改。

**验证**：`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 2971 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；四个 `--ci` 脚本全 [OK]。

### 新增文档与实现一致性检查脚本（check-doc-drift.py）并纳入门禁（2026-09-19，rf-409）

**背景**：前一条全量核对用的是临时脚本（`docs-stm/tmp/audit_phase*.py`），用户问「是否有价值留存」。结论：值得——这类「文档里写死的事实」属**易漂移断言**，人工穷举写法必定漏检（本次就把「返回 result（N 项）」与「`market_temperature_data` 同行内的开关默认值」漏掉了，见 rf-409），而每次漂移都直接误导读者。故常驻化为门禁脚本。

**新增 `scripts/check-doc-drift.py`（十一项检查，权威源 → 受检文档）**：
- 章节：报告章节表（`reports-instruction.md` ↔ 章节注册表，行数/序号/名称）+ 章节数量断言（`页签编号 1~N` / `默认顺序（N 项` / `返回 result（N 项` / `N 个报告章节`）
- 开关：功能开关表（`how-to-config.md` 三组区段 ↔ 注册表，含表外键与缺项）+ 分组计数断言（三组连写/单组/合计三种写法）+ 默认值断言（`` `flag` `` 后紧随「默认开/关」，不跨到相邻开关、不误匹配 `xxx_data` 形态）
- 默认值：配置标量默认值表（↔ `_DEFAULT_CONFIG`，含 bool/None/数字/路径/引号归一）+ LLM 默认参数表（↔ `_DEFAULT_LLM_SETTINGS` 与缓存 TTL 注册表）
- 结构：TUI `[S]` 面板编号连续性与分组边界（↔ `handlers_config.py` 的派生规则）+ 目录树双向比对（↔ 文件系统）+ 项目统计表（↔ 实测文件数/行数，`--with-test-count` 时再核「测试用例」行）+ 测试覆盖计数表（`test-coverage.md` ↔ collect-test-coverage 快照，同一开关）

**集成**：纳入 P0 提交前门禁与 P2 发布门禁（`CLAUDE.md` / `developer-guide.md` / `testplan.md` §6.3 同步）、`test-runner.py` 的 dev-verify preflight（与编号校验并列，约 1s）；`pyproject.toml` 补 E402 豁免（先注入项目根到 `sys.path`）；`technical.md` 的「约束外参照」新增「文档与实现一致性纪律」条；`folders.md` 目录树与统计表同步。

**测试**：`src/test/unit/scripts/test_check_doc_drift.py`（55 例，`unit_scripts`）——逐项纯函数单测（含误报守卫：相邻开关不串号、`xxx_data` 不误匹配、历史记录类文档豁免）+ 真实仓库冒烟（`run_checks()` 为空）。

**豁免面（设计声明）**：`changelog.md` / `review-findings.md`（如实引用旧数字作为变更记录）与 `docs-stm/archive/**`（版本快照）不参与计数与默认值扫描；结构型默认值（dict/list）与菜单类位置引用（「第 N 项」）不比对（前者文档以「见下节」描述，后者随分组变动属预期）。

**修正**：rf-409 两处（`technical.md` 19→17 项、`market_temperature` 默认关→默认开）；`folders.md` 新增脚本与测试文件树条目与统计刷新。

**验证**：`.venv/bin/python scripts/check-doc-drift.py --ci` → [OK]（`--with-test-count` 连 test-coverage.md 计数一并核对）；`.venv/bin/python scripts/test-runner.py --mode dev-verify` → 3026 passed / 0 failed（较上次 +55，即本脚本的用例数）；`ruff check` + `ruff format --check` 全绿；`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` 全 [OK]。

### 修复一致性检查在 CI 上误报构建产物（2026-09-19，rf-410）

**背景**：提交 `122694d3` 推送后 GitHub Actions 的 `test` job 在 3.11/3.12/3.13 三版本全红（`format` job 通过），失败步骤为新纳入的 P0 门禁（dev-verify）。

**根因**：CI 的 P0 步骤在 `pip install -e ".[test]"` 之后运行，而 editable 安装会在 `src/` 下生成 `*.egg-info/`（该目录本就在 `.gitignore` 中）。一致性检查的目录树/统计比对把工作区所有文件都视为「应被 `folders.md` 登记的源文件」，于是把生成物报成「目录树缺条目」→ preflight 失败。本地未做 editable 安装，故「干净克隆 + 现有 venv」验证无法暴露该差异。

**变更**：新增产物判定 `_is_generated()`——按目录名（`__pycache__` / `.eggs` / `build` / `dist` / `.pytest_cache` / `.ruff_cache` / `.mypy_cache` / `htmlcov` / `test-reports`）、后缀（`*.egg-info` / `*.dist-info`）、文件名（`.coverage`）与路径前缀（`docs-stm/tmp/`）识别构建/缓存产物；目录树比对与项目统计两条路径统一排除。

**回归用例（+11）**：产物判定表（egg-info / pycache / build / dist-info / .coverage / tmp / test-reports 为产物；`core/atomic_write.py`、测试文件不是）+ 含产物的合成仓库用例（构造成员被忽略、真实文件缺条目仍报）。定位于 `TestGeneratedArtifacts`。

**本地复现方式**（供后续同类排查）：在仓库根执行 `mkdir -p src/investor_util.egg-info && echo x > src/investor_util.egg-info/PKG-INFO`，即可复现「目录树缺条目」误报；修复后同一状态下检查通过。

**验证**：`check-doc-drift --ci` → [OK]（`--with-test-count` 连 test-coverage.md 计数一并核对）；`dev-verify` → 3037 passed / 0 failed；`ruff check` + `ruff format --check` 全绿；五个 `--ci` 脚本全 [OK]；统计快照同步刷新（folders.md / test-coverage.md）。

### 测试用例冗余与有效性整备 + 新增 check-test-redundancy.py（2026-09-19，rf-411）

**触发**：用户问询「有没有冗余的测试用例，无效的测试用例」。对 381 个测试文件 / 7,245 个用例做 AST 静态审计（并与 `pytest --collect-only` 节点比对），结论与处置：

**四类问题**：
- **完全重复 20 组**：14 组为同一被测对象同一断言（跨文件或同文件），6 组是不同 provider 解析器（`_safe_float` vs `_parse_float` 等）的**并行覆盖，保留**
- **自证用例 6 个**：`test_cache_edge.py` 的 `get_ttl` 系列把被测函数本身 patch 掉，再断言自己设的 `return_value`——断言恒真、等于没测
- **名实不符 7 例**：`test_default_true`（实际设了 `SSL_VERIFY=true`，默认分支从未被测）、`test_none_content`（传 `""`）、`test_none_returns_low`（传 `[]`）、`test_midday_145959_still_midday`（时间由 patch 决定，与 11:30 用例完全同分支）、`test_afternoon_closed_uses_long_ttl`（与午休同义）、`test_capture_snapshot_first_run`/`holding_mapping`（两者同体同断言，且后者名字声称验字段映射却只断言返回 `None`）
- **无断言 16 个**：仅「调用不抛异常」，未断言任何可观测结果

**负面结论（同样是有效信息）**：**无死用例**（无同名覆盖 / 无非 `Test` 类的 `test_*` / 无 `Test` 类 `__init__`）、**无空测试体**（既有守护生效）、**parametrize 无重复参数集**、20 个 `test/live/*` 是 `pytest.ini` 刻意排除的 opt-in 套件（非死用例）。

**处置**：跨文件重复删其一；同文件重复合并（`test_html_builders_edge` 价格变体 4→1 用 `subTest`、`test_cache_edge` 午休/收盘合并、`test_market_hours` 09:30 重复删一、`test_news_sources` 字母 token 重复删一）；6 个自证用例改为真实断言（patch 依赖、断言真 `get_ttl`）；7 例名实不符改为真跑其声称场景（含 `capture_snapshot` 映射用例改为断言传给 `save()` 的快照字段）；16 处补可观测断言（stdout 静默、错误列表、删除尝试次数、`assert_not_called`、产出文件存在等）。

**新增 `scripts/check-test-redundancy.py`（四类检查 + 误报守卫）**：死用例（不可收集/被覆盖）／无断言（含「断言落在同类辅助方法」的解析）／完全重复（去 docstring 后函数体+参数+装饰器 AST 归一化；**无法解析的 `self.<attr>` 间接调用跳过比对**，避免把并行覆盖误判为重复）／自证用例（patch 被测函数 + `return_value` 断言回原值）。纳入 P0/P2 门禁与 `test-runner.py` 的 dev-verify preflight；`developer-guide.md`（工具表 + 专门章节）、`testplan.md` §6.3、`technical.md`「约束外参照（测试有效性纪律）」、`CLAUDE.md`（P0/P2 + 独立性条目）同步；`folders.md` 目录树与统计刷新。

**验证**：`check-test-redundancy --ci` → [OK]（0 死用例 / 0 无断言 / 0 完全重复 / 0 自证）；`dev-verify` 全绿；`ruff check` + `ruff format --check` 全绿；`check-doc-drift --with-test-count` 连计数一并核对通过。

### scripts/ 优化：性能修复 + 共享模块抽取 + test-runner 拆包（2026-09-19，rf-412 / rf-413）

**触发**：用户问询「scripts 目录下的脚本有没有可优化的空间」。审计 23 个脚本（AST 克隆检测 + 真实计时 + cProfile + 调用方引用统计）。

**① 性能（P0 门禁合计 15.7s → 4.0s）**
- `check-semantic-index.py` **7.15s → 0.25s（≈29×）**：`slug_exists_in_code()` 曾对**每个 slug** 遍历全部 `.py` 并 tokenize 一次（116 slug × ~88 文件 ≈ 10,176 次全文件 tokenize；cProfile 显示 `tokenize` 占其 95% 耗时）。改为 `collect_code_texts()` 每次检查只收集一次、所有 slug 复用
- `check-code-traces.py` **4.53s → 3.32s（−27%）**：89 个模式逐行逐一匹配（3.8 万注释行 × 89 ≈ 345 万次 regex）→ 加模式编译缓存 + **并集预筛**（单次扫描判定该行是否可能命中，未命中即跳过逐一匹配；命中后仍走精确分支，判定结果不变）；标识符模式同样改为预编译

**② 共享模块（消除重复与漂移面）**
- 新增 **`scripts/_checklib.py`**：统一 CLI 契约（`add_common_args()` 的 `-v/--verbose` + `--ci`）、统一输出与退出码（`report()`：通过 0 / 发现 finding 2，`--ci` 仅输出裸描述）、`REPO_ROOT`/`rel()`、文档标记区间与表区域解析（`extract_region`/`replace_region`/`extract_table_region`/`replace_table_region`）
- 新增 **`scripts/_traces_common.py`**：两个历史痕迹检查脚本 4 个逐字节相同的函数（章节计数豁免 / 迭代轮次豁免）收拢一处；两脚本以原面 re-export + `__all__` 暴露同名符号，既有测试与调用方无需改动
- 语义命名索引、文档一致性、测试冗余、版本一致性、编号一致性、测试标记等脚本改为复用 `_checklib`

**③ 契约统一**：`check-version-consistency.py` 补 `--ci`（仅报失败、退出 2）；`check-task-numbering.py` / `check-test-markers.py` 发现违规退出 2（原为 1）；`check-svg-geom/pixel/text-overflow` 三件套合并为 **`check-svg.py`**（子命令 `geom` / `pixel` / `text-overflow`，带 `--ci` 与退出码 0/1/2）

**④ `test-runner.py` 拆包（1,600 → 246 行入口 + 7 模块）**：`scripts/_test_runner/` 按职责拆分 `paths` / `modes` / `pytest_env` / `machine_info` / `doc_writer` / `report_html` / `runner`（最大 345 行）；入口保留 CLI 与主流程并 **原面 re-export 49 个符号**，既有测试与调用方零改动（受影响测试的 monkeypatch 改指向持有状态的子模块，如 `_test_runner.report_html._LATEST_DIR`）

**⑤ 清理**：2 处死代码（`_ratio_band`、`_check_exact`）；新增 `src/test/unit/scripts/test_checklib.py`（38 例）覆盖共享设施与共享排除模式

**⑥ 顺带修正 rf-413**：`check-svg` 的像素子命令依赖 Pillow 但依赖清单未声明（干净环境必 `ModuleNotFoundError`）→ 改为按需导入 + 可读指引 + `[svg]` 可选依赖组（`pyproject.toml` / `requirements.txt` 同步）

**顺带修版式**：`geom` 报出的 4 处「文本贴边」（右余量 1~4px）已通过加宽卡片消除——`architecture.svg` 左侧渠道列 +10px、中间双列卡片统一 +8px，`llm-chain.svg` 四个 Provider 卡片统一 +10px；三张 SVG 现均通过 `geom`（卡片内文本右余量 ≥10px，`capabilities.svg` ≥19px）。矩形底部对齐降为提示项（流程图同列卡片高度本就允许不同）。

**验证**：`check-semantic-index --ci` / `check-code-traces --ci` / `check-doc-drift --ci`（含 `--with-test-count`）/ `check-test-redundancy --ci` 全 [OK]；`dev-verify` 3098 passed / 0 failed；`ruff check` + `format --check` 全绿；统计快照（folders.md / test-coverage.md）同步刷新。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.1（2026-09-15 ~ 2026-09-18）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
