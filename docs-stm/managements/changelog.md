# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.9.12] - 2026-08-03

### Feat

- **`history.lookback_days` 取数窗口配置，修复历史回撤分析数据不足** — 新增 `history.lookback_days`（默认 90，下限绑定回撤分析 MIN_SPAN=60、上限 365，超范围在配置校验时告警）控制组合历史走势取数窗口。修复 plan-2/3/9 引入回撤分析 60 交易日门槛（MIN_SPAN）后主报告取数窗口仍固定 30 天导致的矛盾——回撤分析章节结构性判定"有效交易日不足 60 天"。取数窗口配置在 `_snapshot.py fetch_history_data` 边界读取并透传 `get_combined_timeseries(days=...)`，`PortfolioHistoryCalculator` 保持无状态默认 30 不变（调仓 What-if 回测按生效日独立计算窗口，不受影响）

### Fix

- **事实校验器误修正修复（rf-160/161/162，回归测试 8 项）** — 真实报告三处误修正，根因与修复：
  - **rf-160 个股收益率 profit_rate 单位错配** — `orchestrator` 构建 `holdings_details` 时 `profit_rate` 沿用小数（1.8712=187.12%），与百分数契约（LLM prompt 按 `profit/cost*100`）不一致，导致报告"建设银行今日下跌 3.41%"等数值被误修正为 1.9%（小数误读、偏差恰在容差内）。修复：orchestrator 源头 `×100` 为百分单位，`_build_stock_rate_map` 契约对齐百分数，prompt 三处收益率格式化同步补 `×100`
  - **rf-161 单日涨跌语境缺失** — "今日下跌 3.41%"被按收益率维度校验。修复：新增 `_is_daily_change_context`（今日/昨日/单日 + 上涨/下跌关键词窗口），单日涨跌按持仓主体 `change_pct` 校验，无持仓主体（如指数）时跳过不修正
  - **rf-162 表格行内排名声称归因误判** — 调仓表行"…040046…为第一重仓，与 016055 高度同质"，声称词后 8 字的比较对象 016055 抢位误归因到 016055 → 误报。修复：`_claimed_code` 优先行内声称词前代码（品种名列），无则回退行内就近/整句
  - 附带：自动修正明细渲染语义 reason（如"601939实际收益率187.1%"）替代原截断句段，用户可直接看懂修正的是哪个数字的含义
  - 回归测试 `test_fact_checker.py::TestRegressionProfitRateUnitAndDailyChange` / `TestRegressionTableRowRankAttribution`（8 项，覆盖单位契约/单日涨跌匹配与错配/无主体跳过/整链路不修正/表格归因正误两侧）

### Refactor

- **默认 config.json 模板注释补齐（首次生成即可见）** — 此前 `_get_default_config_template()` 对 history / performance_evaluation / rebalance / anonymization 等段用 `json.dumps` 整体序列化，`_DEFAULT_CONFIG` 中的 `#` 行尾注释全部丢弃，首次运行生成的 config.json 模板仅分组注释无字段说明。现改为手工构建模板（对齐 `batch` 段先例），将 `fetch_mode`、`lookback_days`、`risk_free_rate`、`comparison_indices`、`excess_threshold_up/down`、`rebalance` 六键、`redemption_limits`、`anonymization.mode` 的行尾注释写入模板；`data/config/config.json` 同步注释（已存在配置不重写，仅注释展示）
- **plan 迭代设计文档归档清理** — ① `plan-11-dark-mode-plan.md` 归档至 `archive/v0.9.x/html-dark-mode/`（原 `archive/v0.9.x/dark-mode/` 目录更名 `html-dark-mode/`）；② `plan-whatif-backtest.md` 归档至 `archive/v0.9.x/whatif-backtest/`；③ `plan-advanced-analysis.md` 归档至 `archive/v0.9.x/abandoned-design/` 并更名 `plan-4-brinson-attribution-abandoned.md`（记录放弃设计决策依据——除已放弃的 plan-4 Brinson 归因外均已实现）；④ `plan-engineering.md` 删除（任务均已实现）。外部引用同步（plan.md / plan-web-ui.md / folders.md 目录树与统计）
- **因子暴露分析设计沉淀至正式文档** — `technical.md` §4.8 因子暴露分析新增「候选因子代理指数」表（6 个 CSI 指数 + probe 实测状态）与「数据新鲜度判定标准」（threshold/stale 双维度 + 5f/3f/infeasible 分级）；`probe-csi-factor-indices.py` 与 `whatif.py` 注释/文档字符串由 archive 路径改引正式文档（technical.md §4.8 / §4.13）
- **check-doc-traces.py 打磨（文档痕迹检查收口）** — 明确两条核心规则：① 文档正文不得带历史痕迹与历史变更（changelog / plan / review-findings 例外），只反映最新状态；② 除上述三例外文档外，管理/用户文档正文不得引用归档文件（folders.md 目录树可引用 archive 目录及文件名）。归档引用模式收紧——运行时产物归档描述（"归档至 `YYYYMMDD/` 日期子目录"、"归档到 `reports/`"等）豁免；工具说明豁免加固（含"不得/禁止"前缀）；`scripts-reference.md` 同步说明
- **check-code-traces.py / check-doc-traces.py 自我进化（痕迹检查能力补强）** — ① 补强高频时序历史叙述模式 ~13 条（之前/此前/以前/曾经/原始/历史实现/旧逻辑/由旧 XX 改造/迁移到新/重构前/替代旧/曾考虑/后来改为 等），并配套 EXCLUDE 豁免合法运行时描述（历史数据/历史序列/当前版本/此前已配置/之前缓存过/以前端 等）；"迁移到新/至"组合补强（原模式漏检"迁移到新模块"）。② 工具自身豁免由硬编码文件名改为 `_is_tool_self()` 模式识别（`check-*.traces.py` 重命名/新增同类工具不失效）。③ code 侧新增"工具说明行元描述豁免"（与 doc 侧 `检查…历史痕迹` 豁免对齐），防止补强模式误伤规则描述类注释。④ 新增 `src/test/unit/scripts/test_trace_check_scripts.py`（32 项）固化检测/豁免行为；注册 `unit_scripts` marker（conftest.py / check-test-markers.py / collect-test-coverage.py 同步），并纳入 `test_runner.py` dev-verify/verify 门禁
- **check-code-traces.py 门禁打磨（回归场景元描述豁免 + 多行 docstring 提取修复）** — ① 新增「测试回归场景元描述豁免」`TEST_META_EXCLUDE`（**仅 `src/test/` 文件生效**）：回归测试 docstring/注释描述"旧实现/修复前做错什么、修复后如何"（如"旧实现把 3.41/4.43 修正成 1.9"、分隔注释"rf-159 批次修复"）属测试元数据而非源码历史痕迹残留，豁免不报；非测试文件（test_file=False）检出能力不受影响——同样的"旧实现"叙述在源码侧仍被检出。② 修复 `_is_triple_quote_line` 多行 docstring 关闭行识别缺陷：docstring 内容最后一行为 `…内容"""`（不以三引号开头）时 `in_docstring` 状态不翻转、泄漏到后续代码行（assert 被误当 docstring 提取导致误报）；现补「仅关闭」识别分支（`endswith('"""')`）。③ `test_trace_check_scripts.py` 由 32 项扩至 39 项（TestTestFileMetaExemption 4 项 + TestCommentExtraction 3 项，覆盖豁免生效/非测试文件不豁免/关闭行识别/状态不泄漏）

---

## 归档

- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.11（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
