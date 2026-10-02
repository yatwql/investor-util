# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.11]**（2026-10-02）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.12-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### Windows 可移植性与测试失败修复

- **Web 上传目录项目根误算（rf-534）**：`src/python/web/upload.py` 用 `__file__` 向上 3 层手工推算项目根，落点为 `src/python/web/upload.py` 时只得 `src/`，上传文件被误存进 `src/data/holdings/uploads/` 幽灵目录（本机实测残留 `*.xlsx`，并被 `check-doc-drift` 报为目录树缺条目）。改用 `constants.PROJECT_ROOT`（标记文件查找、不依赖目录深度）作单一来源；新增回归用例 `test_upload_dir_rooted_at_repo_data` 钉桩「落点不在 `src/` 内」。

- **check-doc-drift 在 Windows 的三处失效（rf-535~537）**：(a) `_checklib.rel()` 返回 `\\`，与 `folders.md` 目录树的 `/` 拼接、文档内文件引用全线失配 → Windows 下把 1,600+ 真实文件全报「目录树缺条目」，改 `.as_posix()` 归一；(b) `collect-test-coverage.py` 中文分组名按 cp936 GBK 写出，消费方 `_doc_drift/_shared.py::_collect_test_snapshot` 按 UTF-8 解码 → reader 线程 `UnicodeDecodeError` → `proc.stdout` 为 None → `re.search(..., None)` 抛 `TypeError` 使 `--sync` 堆栈退出，双侧修复：子进程入口 `sys.stdout.reconfigure(encoding="utf-8")`，消费方补 `errors="replace"` + stdout 空值降级为空快照（新增 4 例回归）；(c) 同步刷新 `folders.md` 统计数字快照。

- **测试用例的 Windows 可移植性修复（rf-538）**：13 例失败全部为断言不可移植（非生产缺陷）——POSIX 权限位断言（`os.chmod`/`st_mode` 在 Windows 无意义，5 例加 `skipif(os.name == "nt")`）、`os.geteuid` 仅 POSIX（1 例跳过）、`asyncio.ProactorEventLoop` 启动用 `socket.socketpair()`（内部退化为回环 `connect`）被网络守卫误阻（守卫加回环豁免：`127.0.0.0/8`、`::1`、`localhost` 放行，外网仍阻断；已加 sanity 验证）、`/tmp` 与 `/` 分隔符硬编码（改 `Path` 结构断言 / `is_relative_to(PROJECT_ROOT)`）、`endswith("a/b")` 反斜杠失配（改 `Path(path).parts[-2:]`）。

- **`test_real_repo_sync_idempotent` 在 xdist 下的假失败修复（rf-538 后续）**：该用例经由 `_sync()` 触发嵌套全量 `pytest --collect-only`，在 xdist 并行套件运行中被资源争用采到不完整集合（实测 7964 vs 完整 8173），幂等断言假红。改为从 `folders.md`「测试用例」行注入登记用例数（`test_count=` 参数本就为测试暴露），真实 `_stats_actual()` 照常实测——同步逻辑的真实仓库幂等性照旧被覆盖，不再有嵌套收集脆弱性。附带将 `TestRel` 断言随 `rel()` 语义更新（POSIX 分隔符契约），并补一条 POSIX 分隔符钉桩用例。

### 文档治理与脚本收编

- **rf-521 归档确认**：六个报告层/core 文件直连 providers 已零（改经 fetcher 网关 `fetch_with_fallback`/`report_adapters` 薄透传，commit 2e53f813），守卫 rc=0 佐证；主表行迁入 v0.11.x 归档「v0.11.11 批次」。

- **check-code-traces 拆包（rf-533）**：1,016 行破 800 硬上限的唯一脚本，按「模式表/扫描/守卫」拆为 `scripts/_traces_code/` 六模块包，入口只留 CLI（185 行）与原面 re-export；`_traces_common.py` 并入包内 `exemptions.py` 并删兼容壳（测试改指向子模块）；check-task-numbering / check-test-markers / check-doc-traces 三脚本迁移 `_checklib` 契约（补 `-v`、统一输出与退出码，17 处 sys.path 样板文本统一）。scripts 单测 428 例全通。

- **已修复 rf 记录批量归档（发布后治理）**：review-findings.md 裁剪为纯待处理集——P2E 表 rf-522~527 六行已修复行与游离的 rf-532 行、P2C 的 rf-520 摘要引言原文迁入 [`archived_review-findings.0.11.x.md`](../archive/v0.11.x/archived_review-findings.0.11.x.md) 新增「v0.11.11 批次」段（rf-474 明细此前批次已在档）；归档头涵盖版本补 v0.11.11。主文件现仅存待处理项：P1 人工验证 rf-113/rf-114、P2A 八长文件复核行、P2B rf-257 用户复验、P2E rf-521 与 rf-528~531 五项。

- **rf-528（渲染期模块级可变状态并发保护）**：`web/handlers.py` 的 `_history_cache`/`_health_cache`（5s/60s 进程内缓存）在 `app.run(threaded=True)` 下读写无并发保护。处置：新增线程锁保护两缓存读写段（计算在锁外，同时 miss 可重复计算、单机单用户低风险）。测试：`test_handlers.py::TestShortCacheConcurrency` 4 例（命中跳过重载 / TTL 重算 / `?fresh=1` 绕过 / 8 线程并发写安全）。

- **rf-529（HHI 计算收敛唯一原语）**：`whatif._compute_hhi`（成本口径）与 `portfolio_evolution._compute_hhi`（权重口径）重复实现 Σ权重²，`metrics_risk.hhi` 原语闲置。处置：两处均收敛为 `metrics_risk.hhi` 唯一原语薄委托（预归一权重幂等；退化语义一致）。测试：`test_stale_cache_helper.py::TestHHIConvergence` 3 例。

- **rf-530（print 输出边界确认）**：`doctor.py` 本体零 print（CLI 输出走 `format_doctor_report` 结构化整块，唯一消费面单 print），`TuiProgressReporter` 属交互式进度合法豁免。处置：doctor.py 模块 docstring 显式声明「输出边界：CLI-only 交互豁免面」锁定依据，不改输出路径。

- **rf-531（过期缓存回写统一降级助手）**：`fetch_us_indices` 过期缓存段裸 `cache_set` 未盖语义版本。处置：`fetcher/chain.py` 新增 `write_stale_with_version`（来源标记 + `_payload_ver` 语义版本戳 + 回写）与准入判据 `payload_version_current`，`fetch_us_indices` 改调助手。测试：`test_stale_cache_helper.py::TestStaleCacheWriteHelper` 3 例。

- **rf-539（probe 统一入口 + 幻觉率采样拆包）**：新增 `scripts/probe.py`（registry 分发统一入口）+ `scripts/probes/`（`__init__` 注册表 / csi / push2，target 实现 PROBE_TARGET/build_parser/run 契约面，新探针登记即用）；旧入口两脚本保留为薄委托垫片（旧命令用法不变），`csi` 状态改「因子分析已实施 → 周期性复核」。`llm-hallucination-sampler.py` 634 行拆为入口薄 CLI（239 行）+ `scripts/_halluc_sampler/`（holdings/llm_call/fact_check/report），顺带修复三处随 fact_checker 拆包失效的坏 import（工具此前已静默坏掉）。测试：`test_probe_entry.py` 8 例。

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.11（2026-09-15 ~ 2026-10-02）
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
