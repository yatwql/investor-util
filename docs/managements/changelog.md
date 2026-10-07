# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.12.4]**（2026-10-07）——已发布版本段随发布移入 [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md)；本文件只保留当前开发版本段与归档索引。

---


## [0.12.5-dev] - 开发中（未发布）

- **工程效能**：**任务执行流程耗时优化第一批（质量 × 时间平衡）**落地——① 执行口径统一：P0 门禁文档三处（CLAUDE.md / developer-guide / testplan）收敛为「dev-verify 手动 + 十守护由 pre-commit 钩子唯一执行 + CI guards 恒全量兜底」，本地不再对同一待提交树重复跑守护；② dev-verify 预检精简为 <100ms 任务编号快检（重量守护不入预检）；③ pre-commit 钩子改分域并行：`check-doc-drift --sync` 串行先行回写统计，其余九守护按暂存域（恒跑快集 / doc / py / 测试域）后台并行回放，纯文档提交不跑 file-length、纯代码提交不跑 test-redundancy；④ `check-doc-drift --sync` 测试收集快照缓存（树指纹失效，测试增删照真收集）：pytest 收集 4.1s → 命中 0.6s；⑤ `check-test-redundancy` 按文件事实缓存（size:mtime 签名 + 逻辑版本键，跨文件重复/死用例比对仍全集归并）：冷 3.5s → 1.8s、变更文件增量 0.07s，与旧实现输出对拍逐字一致；全部配回归用例与缓存路径测试隔离；CI 十守护恒全量与守护清单五处同源校验不变 | rf-606 ~ rf-610
- **工程效能**：**任务执行流程耗时优化第二批（质量 × 时间平衡）**落地——`check-doc-drift` 测试收集快照升级 v2 按文件增量：逐文件计数账本，共享语境（conftest/pytest 配置/业务代码）变化整树全量，仅变更文件单文件重收集（0.2s），删除文件按现存账本回减；影子双算连续一致才毕业进纯增量，不一致告警归零继续守门；失败/非零退出拒收不回写。实测 sync 快路径 0.63s、变更文件纯增量 0.87s（旧全量 4.2s）、`--with-test-count` 热 0.52s。配套修复 `collect-test-coverage.py` 无视 pytest 退出码缺陷（收集出错的未过滤错数不得当真值缓存/写进文档统计）；CI 恒全量、守护清单与五处同源校验不变 | rf-611、rf-615
- **工程效能**：**任务执行流程耗时优化第三批（质量 × 时间平衡）** —— dev-verify 双阶段合一：原「核心单元 Phase A + 基础场景 Phase B」两轮 pytest 收敛为单轮并集 marker（用例集合布尔等价全组合枚举对拍 + 合并前后收集数 5752+155=5907 精确一致零重叠；timeout 预算 300s×2 不变；单轮报告 `report.html`，多阶段每阶段一文件防覆盖机制保留；preflight 预检不变），省一整轮收集与 worker 启动：本机 37.6s → 30.1s；并行 high 档实测无增益（wall 持平、CPU×2），默认保持 medium、`--parallel high` 可选 | rf-612
- **工程效能**：**任务执行流程耗时优化第四批（质量 × 时间平衡）** —— ① 三守护结论缓存：`check-doc-traces` / `check-semantic-index` / `check-doc-links` 按「逻辑版本键（脚本+_checklib+解释器大版本）+ 输入面指纹（文件集 + 逐文件 size:mtime_ns）」未变直接回放上次结论（**通过与发现都缓存**，输入同则结论同），--ci 冷/热输出与退出码逐字一致（实测 0.59→0.04s / 0.32→0.035s / 0.10→0.03s），失败/损坏/歧义一律全量重算，缓存目录测试隔离重定向；② 钩子读写分层调度：不读 folders.md 的快集+py 域+测试域守护与 doc-drift 串行段并行启动，读 folders.md 的 version-consistency 与 doc 域守护串行后置（避 --sync 写读竞态）。CI guards 恒全量十守护与五处同源清单不变 | rf-613
- **工程效能**：**任务执行流程耗时优化第五批（质量 × 时间平衡）** —— ① CI guards job 十守护由逐个串行改为 pre-commit 同款后台并行回放（清单/恒全量/五处同源不变，步骤合并为单步但十守护每项照跑；任一失败折叠 FAIL 分组并使 job 红，本地原样提取块复演成功与失败双路径），暖测串行 0.80s → 并行 0.43s，CI 冷环境预期 ~5.1s → ~2s（受最慢单守护冷耗时封顶）；② 移除 4 处 `pip install --upgrade pip` 冷自升级（setup-python 自带版本足够新、无缓存收益）；③ 依赖审计（守护 → 仓内模块传递闭包）确认守护经 src.python 链 import 项目运行时依赖（check-doc-drift → registry/tui_menu → httpx）→ 按质量规则**保留** editable 安装；三档测试分流与守护清单不变 | rf-614
- **报告结构**：**rf-600 仓库 config 报告序号契约修复** —— ① `data/config/config.json` 的 `report_section_order` 移除已废弃键 `event_impact`、补 `schedule_replay`=16：18 键与注册表 19 键（减 `llm_usage`）双向一致且逐键出厂同序，启动校验不再报「未知的模块标识」告警、调仓纪律回放归位注册表默认位 16，章节顺序经 `get_report_section_order()` 单源派生自动双端归位；② `validate_config` 对未知模块标识升级为「计 1 问题 + 从内存配置自动清理」，防残留键扭曲「已配置在前/未配置排尾」合并（文件层漂移仍计问题提示同步、不回写文件）；③ 补契约测试 `TestRepoConfigSectionOrderContract`（绕过测试隔离直读仓库 config，键集双向一致 + 逐键出厂同序）与 `TestReportSectionOrderAutoClean`（计数与清理回归）；④ 同步手册/技术文档「本仓库配置 N 项」镜像表述（how-to-config 模块表 17→19 项、faq 18→19 项、technical 合并流程图与仓库配置镜像段） | rf-600

（本次发布内容见下方归档索引）

## 归档

- [`archived_changelog.0.12.x.md`](../archive/v0.12.x/archived_changelog.0.12.x.md) — v0.12.1 ~ v0.12.4（2026-10-03 ~ 2026-10-07）
- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.12 + v0.12.0（2026-09-15 ~ 2026-10-03）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12)
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
