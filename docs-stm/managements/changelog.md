# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.10.20-dev] - 开发中（未发布）

### 修复：QDII 联接穿透被旧缓存遮蔽 — 持仓缓存载荷语义版本（rf-357）（2026-09-14）

- **背景（用户报障）**：另一台机器运行报告仍报 `016055` / `040046` 持仓报告期陈旧（`2023-09-30` / `2022-12-08`）、已按持仓不可用处理、未计入穿透 TOP10。定位于 v0.10.18 的 QDII 联接穿透修复（`d02e32e0`）**只改代码、未让旧缓存失效**：修复前写下的 `fund_hold_*` 条目无 `feeder_target_code`，新代码读到时无法穿透，旧载荷「有持仓 + 早期报告期」直接撞上时效闸门——`hold` TTL 为 7 天，旧条目过期前修复被全程遮蔽（提交当时已注明「需立即见效时 `--clear-cache`」，但该依赖用户手动，属真实缺口）。
- **修复（语义版本 + 读侧准入）**：provider 产出经 `fetcher/fund.py::_stamp_hold_schema` 盖 `hold_schema` 版本字段；读取侧以 `_is_current_hold_payload` 为准入判据，版本不符视为未命中。判据接在**两处**读缓存接缝：① `fetcher/chain.py::fetch_with_fallback` 新增 `cache_validate` 参数（覆盖新鲜命中与过期降级条目，不符即清缓存重取）；② 批量预检回调 `_hold_cache_check`（`execute_with_cache_check` 命中会跳过任务，判据若只挂在链路内则热缓存下失效）。顺带移除 `fetch_fund_holdings_batch` 内冗余的局部 `cache_get`/`get_ttl` 导入（模块顶部已有，局部导入使与 `fetch_with_fallback` 的 `cache_validate` 无法在测试中一致打桩）。
- **效果**：此类「改变载荷含义、不变键结构」的修复从此自失效，不再依赖用户手动清缓存；另一台机器 `git pull` 后首次运行即自动丢弃旧条目并重取。
- **回归测试**：`test_chain.py` 增 3 例（准入判据放行/拒收旧载荷并清缓存重取/拒收旧语义过期降级条目）；`test_fund.py` 增 `TestHoldPayloadSchema` 5 例（盖章、判据准入、旧载荷重取并盖章、当前载荷命中不重取、批量预检拒收旧载荷）。fetcher 两文件 89 passed / 0 failed。
- **文档**：`technical.md` §4.9 补「持仓缓存载荷语义版本」机制、§6.7 语义命名表增 `hold_schema` / `cache_validate` 两行、§8.2 补「缓存载荷语义版本」词条外设计规则；本 changelog 与 `review-findings.md` rf-357。

### 发布后自查整改：多币种换算口径校正 + 脚本约定守护（rf-354 ~ rf-356）（2026-09-13）

- **背景**：发布 v0.10.19 后复盘近 96 小时的实现，发现三处遗留债——一处是 rf-350 明确标记「待用户确认」的能力口径失配，两处是脚本约定只写在文档、无任何校验环节。
- **rf-354 多币种换算口径校正（按实现改写文档与测试，不新增汇率功能）**：`faq.md` 原称「港股通和非 A 股品种的汇率换算由数据源接口自动处理」；`testplan.md` 的 T8 场景列「美元份额币种转换」、T19 场景为「汇率中间价故障」、数据正确性验证表列「多币种转换正确：美元份额 × 汇率中间价 = 人民币市值 ✅」；测试侧 `test_data_integrity.py` 第 4 项与 `TestMultiCurrencyConversion`、`test_market_value.py::TestCurrencyConversion` 亦按汇率换算命名。核对实现：**全仓无任何汇率取数或换算**——`get_currency_by_code` 只做币种分类（5 位纯数字→HKD、QDII/海外基金/美股指数→USD、其余→CNY），`fx_exposure.py` 只按币种汇总市值与占比，`market_value.py` 无汇率分支，QDII/场外基金的净值本身即以人民币计值（相关断言为 100 份 × 2.5 = 250.0），情景分析的「汇率情景」是假设 ±5% 对非人民币占比的估算。处置：四处口径按实现改写（`faq.md` 明确「程序不做汇率换算」并补币种分类规则与港股通换汇成本提示；`testplan.md` T8 删跨境币种换算、T19 改为真实且已覆盖的「场外品种净值日期非 T 日」场景、数据正确性表该行改为「非人民币计价品种市值核算（价格 × 份额，不做汇率折算）」并补 `test_market_value.py` 载体；两个测试类更名为 `TestForeignDenominatedMarketValue`，docstring 改述实现，**断言不变**）。需求 §6.10 只承诺「币种判定 + 市值占比 + 标注 + 注入」，与实现一致，未改。
- **rf-355 `scripts/*.ps1` 行尾归一 + 回归守护**：`cli.ps1`、`launch.ps1` 为 UTF-8 with BOM 但**通体 LF**，与 `.editorconfig` 的 `[*.ps1] end_of_line = crlf` 及 CLAUDE.md 的「BOM + CRLF」约定不符（新写的 `llm.ps1` 反而合规）——两文件行尾归一为 CRLF（BOM 保留）。
- **rf-356 `scripts/*.sh` 可执行位入索引 + 回归守护**：仓库 `core.fileMode = false`，工作区权限不被跟踪，`cli.sh` / `launch.sh` / `llm.sh` 在索引中均为 `100644`——新克隆的仓库里 `./scripts/llm.sh` 报 permission denied，而 CLI 手册 / 开发者指南 / 变更记录均按可执行方式调用（且声称「llm.sh 置可执行位」）。处置：`git update-index --chmod=+x` 将三个 `.sh` 的索引权限置为 `100755`，`llm.sh` 工作区权限由 777 归为 755。
- **回归测试**：新增 `src/test/unit/scripts/test_script_encoding.py`（`unit_scripts` 标记，4 例）——`scripts/*.ps1` 逐文件断言以 BOM 开头且不含裸 LF（无 BOM 时 Windows PowerShell 5.1 按 GBK 误读中文注释而解析崩溃）；`scripts/*.sh` 断言 git 索引权限为 `100755` 且工作区可执行（非 git 工作区 / Windows 自动跳过）。

### 开发版本切换（2026-09-13）

- 发布 v0.10.19 后，按既定流程将 `APP_VERSION` 与全部管理文档版本头切换至 v0.10.20-dev，`check-version-consistency.py` 全链 [OK]。

### 已发布版本变更记录归档（v0.10.19 → archived_changelog）（2026-09-13）

- **归档**：发布 v0.10.19 后，按「已完成即归档」口径将本文件 [0.10.19] 已发布版本变更记录整体迁入 `docs-stm/archive/v0.10.x/archived_changelog.0.10.x.md`（接于 [0.10.18] 之后，保持版本升序）；本文件自此仅保留在开发版本 [0.10.20-dev] 的章节与归档引用。
- **同步**：归档文件头部「涵盖版本」扩至 v0.10.1 ~ v0.10.19、「归档内容」改指开发版本 [0.10.20-dev]；`folders.md` 项目文档/归档统计按实测刷新。
- **口径**：发布版本与开发版本分开存放——已发布版本的完整变更记录只在归档文件，本文件只描述尚未发布的工作。

## 归档

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
