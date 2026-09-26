# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.5]**（2026-09-26）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.6-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### CI 补齐守护 job + 门禁数字与注释痕迹整改（2026-09-26，rf-444、rf-445、rf-446）

**起因**：核对「git hook 包含哪些任务 / 守护包含哪些脚本」时发现三处不一致——门禁表数字少于实际、CI 未跑守护脚本、以及本地扫描循环漏跑 `check-code-traces`（导致本会话写入的 7 处任务编号引用/历史叙述一直未被拦下）。

**变更**：
- **CI 补全（`.github/workflows/ci.yml`）**：新增 **`guards` job（阻塞型）** 逐个 step 跑 7 个 `--ci` 守护脚本（`check-code-traces` / `check-doc-traces` / `check-task-numbering` / `check-semantic-index` / `check-doc-drift` / `check-test-redundancy` / `check-requirement-trace`）；`format` job（仍为非阻塞 `continue-on-error`）补 `ruff check` 步骤；`test` job 与三档分流规则不变（并在文件头注释补「P2 → verify,regression」的准确模式名与新增 job 说明）
- **注释痕迹整改**：7 处改写为语义化描述——`core/check_sources.py`、`src/test/conftest.py`、`test_check_sources.py`、`test_report_backup_source.py`、`test_html_template.py`、`scripts/_doc_drift/_format.py`；`check-code-traces --ci` 恢复“未发现历史变更痕迹，注释干净”
- **文档同步**：开发者指南三级门禁表「4 个 check 脚本」→「**7 个**」并新增「**CI 同步执行**」段（分流/矩阵/两 job 职责与阻塞性）；编号保障表新增 `CI guards job` 行（“四层→五层”）；`CLAUDE.md` 的 CI 条目改为描述实际流水线（三档测试矩阵 + `guards` 阻塞 job + `format` 非阻塞 job）

**验证**：`check-code-traces` 由 7 处 finding 回落为 0；7 个 `--ci` 脚本 + `ruff check` + `ruff format --check` 全部 exit 0（本地等价演练 CI `guards`/`format` job 命令）；`ci.yml` YAML 解析通过（jobs: test / format / guards）。

### 清理无效 pre-push 桩 + 补 `--off` 提示（2026-09-26，rf-447）

**结论（先验证后动手）**：`.git/hooks/` 下三个 `pre-push` / `pre-push(1)` / `pre-push(1)(1)` 确实是**无效残留**，两层独立原因：
- **路径旁路**：`core.hooksPath = .githooks`（仅仓库本地 `.git/config`）——`git hook run pre-push` 在 `.git/hooks/pre-push` 存在的情况下报 `error: cannot find a hook named pre-push`，证明 Git 根本不查 `.git/hooks/`；
- **权限拦截**：三者均为 mode 644（非可执行）——`git -c core.hooksPath=.git/hooks hook run pre-push` 直接给 `hint: … ignored because it's not set as executable.`；
- 内容为 17 字节 `#!/bin/sh` + `exit 0`（无逻辑），mtime 相隔 3 秒，属云同步冲突副本；`git ls-files .git/hooks/` 为 0（不跟踪、不跨机器），全仓无脚本/文档引用。

**变更**：
- 删除三个本地残留（原件备份至 `/tmp/pre-push.bak` 以便回滚）——删除后可消除「回退默认路径时 Git 每次 push 的 not-executable 警告噪音」；
- `.githooks/install-hooks.sh` 的 `--off` 分支增两行说明：Git 回退到 `.git/hooks` 后本脚本**不会**在其中安装任何 hook，该目录内容也不随仓库同步（避免误以为回退默认路径会启用某些校验）。

**验证**：`sh -n` 语法通过；`--off` → `hooksPath` 未设置，再启用 → `.githooks`（往返正确）；启用态下 `git hook run pre-push` 仍为 not found（即确实不存在 pre-push 校验）、`git hook run pre-commit` exit 0。

---

### rf-453、rf-454：重试/退避与间隔节流收敛为唯一原语（2026-09-26）

**动因**：审计发现「退避算式与瞬时判据在 6 处各自实现」，且通用「按名间隔」原语错住数据层模块、被 LLM 层与 providers 反向依赖（层次倒置）。两类问题都属「实现未收敛」（对齐既有「实现收敛到唯一原语」的先例，如原子写入），故以**新增架构约束 + 新公共原语 + 逐处迁移**处理。

**代码变更**：
- **新增 `src/python/core/retry.py`**（rf-453）：`RetryPolicy`（attempts + 固定/线性/指数算式 + jitter + max_backoff，含 attempts<1 / 未知算式 / base=0 不等待等边界钳制）、`is_transient_exception`（传输级瞬时判据唯一定义）、`retry_transient`（**异常触发**与**结果哨兵触发**两类条件、`on_retry` 回调保留各源日志文案、`sleep` 可注入）
- **6 处迁移（行为等价）**：Provider Chain 同源重试（哨兵 `TRANSPORT_FAILURE`，策略 attempts=2 / 指数 / 0.6 / ×2 / jitter 0.2；保留 `_TRANSIENT_RETRY_BACKOFF` 以兼容既有测试与离线桩置 0）、巨潮连接级重试（3 次线性 1s/2s）、DataSinking 429 退避、东财 push2（retries+1 指数 0.5 / ×2 / jitter 0.3）、腾讯行情（2 次固定、无等待）、akshare 超时（attempts=1+retries / 固定 1s / `retry_on` 恒真以保持原「一律重试」语义）
- **原语下沉（rf-454）**：`RateLimiter` 由 `fetcher/batch.py` 迁至 **`src/python/core/throttle.py`**（唯一实现），新增 `interval_delay(interval, jitter_ratio)` 作为**抖动算式唯一来源**（`acquire_interval` 返回实际等待秒数）；`fetcher/batch.py` 改为从 core 引入（既有 import 路径仍指向同一类）；`llm/pacing.py` 与 `providers/{datasink,hithink,cninfo}` 依赖改指 core.throttle；pacing 只保留声明解析 + 在途并发上限
- **顺带**：修 `eastmoney_industry` docstring 与实际不符的「默认 3 次」（常量为 1）；26 处测试补丁由「patch provider 的 httpx 引用」改指统一 HTTP 出口 `core.http_client.httpx.Client`（对齐 patch 调用点原则）

**架构与需求层同步**：technical.md 新增「重试与退避唯一原语」与「间隔节流唯一原语」两条架构约束（§8.5，含违反后果与适用范围），§2.2.1 补「口径单一来源」说明、§6.7 命名表补 `retry` / `throttle` 行、附录 A 目录树补两模块；CLAUDE.md 的约束编号范围同步扩展；requirements.md 新增 **R-DATA-07（重试与节流口径统一）** 并在 testplan.md 映射表补载体；llm-technical §4.2.1 更新间隔原语归属；用户文档 `datasource-reliability.md` §3.9 补「重试（备源巨潮）」与 429 退避口径

**测试**：新增 `test_retry.py`（15 例）与 `test_throttle.py`（13 例，含**归属断言**：数据层再导出同一类、pacing 不再依赖 fetcher、providers 依赖 core）；迁移后全量非 live 套件 0 失败（行为等价）；收集数 7,885 → **7,913**。

**另记（未修复）**：同类「失败→重试」实现在 LLM 调用链上仍存一处——`llm/api_base.py::call_llm_with_retry` 自带循环与手工调优的显式退避表，语义与取数路径不同（含内容级/配额级分类），已登记为待处理项并在约束适用范围中如实交代，不并入本轮迁移。

### rf-456：原语收敛后的文档口径核对（2026-09-26）

对管理文档与用户文档做了一轮「序号 + 内容时效性」核对（标题编号序列、目录锚点有效性按 GitHub slug 规则复验、计数声明与代码实况逐项对照），修 4 处偏差：

- **rf-456①**：`technical.md` §5.1 LLM 子模块计数 35 → **36**（27 顶层 + `fact_checker/` 9；`pacing.py` 加入后未同步）
- **rf-456②**：LLM 重试退避的命名与实现不符——实现为手工调优递增表 `[1.0, 3.0, 5.0, 10.0, 15.0]`，文档与代码注释均称「指数退避」；`llm-technical` §6.2 标题与正文、`api_base._RETRY_DELAYS` 注释改为「递增退避表（非等比）」
- **rf-456③**：`developer-guide` live 覆盖「共 14 项」→「**14 个用例**（行情 5 / 新闻 4 / 基金 3 / 交易日历 2）」，与实测用例数一致（`ls src/test/live` 逐文件计数）
- **rf-456④**：本文件新增的架构原语小节（P3）层级与顺序错误（四级标题、落在 P1 表尾）→ 改为三级标题并移至 P2C 之后

核对结论：其余「共 N 个模块」类声明（报告章节模块数、TUI 页签数、数据源探针数、STATUS_MESSAGES 24 条、熔断退避阶梯等）经代码实况逐项复核**均一致**；标题编号序列无重复/断号；目录锚点 0 失配。用户文档本轮仅确认无新增偏差，未作改动。

### 36 小时实现技术债审计（2026-09-26，rf-448、rf-449、rf-450、rf-451、rf-452）

**范围**：过去 36 小时 12 个提交——v0.11.4 / v0.11.5 两次发布、plan-57 端点级节流、财报域备源链路修复、测试外部网络隔离、文档门禁槽位级校验、健康检查覆盖财报域、CI `guards` job、hooks 清理。

**已修 5 项**：
- **rf-448（突破硬上限）**：`src/test/conftest.py` 872 行 > 800 硬上限 → 两个 autouse 隔离 fixture 的**实现体**外移到新模块 `src/test/_path_isolation.py`（225 行：`seed_sensitive_path_isolation` + `apply_report_output_isolation` + 专用常量），conftest 保留 fixture 本体/装饰器/文档串（**pytest 发现语义不变**），降至 **672 行**；全量非 live 套件 0 失败（行为等价）
- **rf-449（台账失真）**：「文件过长」（P2A）8 行登记值全部过期 → 逐行按 2026-09-26 实测刷新（`registry.py` 666→**704**、`batch.py` 564→**578**、`code_utils.py` 542→**605**、`data_status.py` 544→**621**、`html_renderers.py` 521→**556**、`cache/operations.py` 633 持平），并把**已跨 500 线**的 `fund.py`（405→**551**）与 `excel_generator.py`（427→**574**）状态更新为「已跨入 500-800 可选优化区间」
- **rf-450（脆弱点）**：`check_chain_table` 硬编码 `cells[3]` 取槽位列 → **按表头文本定位**（`_chain_id_column_index()` 返回列下标 + 表头列数）；缺表头、行内单元格数少于表头分别给出可读 finding。验证：临时把 provider id 列调到第 2 列后门禁仍 0 finding；新增回归测试 `test_column_reorder_still_parsed`
- **rf-451（桩清单完备性）**：离线桩的 4 个目标新增存在性断言（`TestOfflineStubTargets`），上游重命名/搬迁不再只靠「用到该 fixture 时才炸」
- **rf-452（配额未提示）**：`check-sources` 的 DataSinking 探针每次消耗 1 次源配额，已在 `datasource-reliability.md` §5.2 补「配额提示」（并注明巨潮探针无凭据、无配额）

**待处理 2 项（登记于「当前待处理问题」P3，建议单独立项）**：
- **rf-453**：重试/退避实现散落 5 处且口径不一（chain 同源瞬时 / cninfo 连接级 / datasink 429 / eastmoney_industry / tencent；既有 `providers/_utils.run_with_timeout` 仅覆盖 akshare）→ 建议抽 `core/retry.py` 统一原语并按源逐个迁移
- **rf-454（观察项）**：`llm/pacing.py` 与 `fetcher/batch.RateLimiter` 在「最小间隔 + 等待 + jitter」上部分重叠（作用域不同：LLM 端点级 vs 数据源请求），暂不抽象合并以免过度设计

**验证**：`ruff check` / `ruff format --check` 干净；7 个 `--ci` 门禁 + `--mode dev-verify`（3,271 通过）全绿；非 live 全量 **7,871 通过 / 0 失败**；测试收集数 7,885。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.5（2026-09-15 ~ 2026-09-26）
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
