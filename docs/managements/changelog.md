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

- **报告结构**：**P2D 报告结构与组织优化批（Excel × HTML 双端同步）落地** —— ① 导航分组同源：注册表条目增 `nav_group`（六组）与 `llm_supported` 字段，HTML 章→组映射/分组标签/🧠 集合全部改为注册表派生（漏配不再静默回退基础信息组），计算注册表拆出 `core/computation_registry.py`（`registry.py` re-export）控住 800 行红线，散点断言收口为 `TestNavGroupRegistry`；② Excel 导航三件套：页签 `tabColor` 六组六色（与 HTML 目录分组同源）、汇总页章节导航超链接区（每 8 列一行、表头与冻结行动态化）、各页签「↩ 返回汇总」链接（标题行尾落点，不挪动既有写入器表头行），`test_excel_navigation.py` 双端导航一致性用例；③ 章节显示名单源化：模板 14 处 + partials 5 处标题改 `{{ section_names[key] }}`（env globals 自注册表一次性构造），`_REPORT_SHEET_NAMES` 降为派生视图（LLM 章差集 `_LLM_SHEET_NAME_KEYS` 显式声明）+ 派生关系测试 + 模板无硬编码标题守卫；④ 模板拆分：`report_template.html` 3131 → 1143 行、14 个章节级 partial 按 TOC 六组拆入（渲染输出与拆分前空白归一逐字一致，结构测试护航），raw 读模板的 4 个测试改读「模板 + partials」拼接源，`_FOLD_KEYS` 补持仓变动/调仓回放两章；⑤ 章节-区块矩阵：`technical.md` §4.22 固化 19 个章节的双端区块清单（HTML 序号标记重算口径 + Excel 子块存在性对账），`check-doc-drift` 新增第 17 项机检（key 双向对注册表/计数重算/清单逐串，守护清单五处同源 scope 同步），组合历史 docstring「两区块」修正为三区块；⑥ 文档审计收尾：管理/用户文档全量核对——「18 个模块」类计数刷新为 19（technical/developer-guide/faq 六处）、`report_section_order` 镜像与 TOC/序号核对、§4.21 折叠载体口径随拆分重写、页签导航与折叠清单补进 reports-instruction、folders 目录树登记 20 个 partial 与新增文件 | rf-601 ~ rf-605
- **报告结构**：**rf-616 章节区块级双端契约** —— ① 真值单源：新建 `core/section_block_registry.py`（`SectionBlockSpec` + `SECTION_BLOCK_SPECS` 19 个章节全量条目：`html`/`excel` 归一化区块名清单 + `partials`/`modules` 提取载体，`registry.py` 顶部 re-export 保持访问面）与 `report/section_block_extraction.py`（HTML 三源：`block-title` 全计 + 带序号加粗 div + `<!-- ── 一、` 框式注释兜底且可见优先；Excel 侧静态解析 `write_block_title` 调用点含参数直通包装位参，动态拼接抛错不静默漏计；两端归一化同口径：去标签/序号头/括号段/【】）；② 双端换装：15 个 Excel 写入器约 44 处区块小节标题由 `write_title_row` 改 `write_block_title` 唯一 API（summary/action 本地包装保版式），组合演进 Excel 端题名对齐 HTML 端（`总市值与总盈亏趋势` 等，双端 5 对 5 对等），历史章危机区间注释对齐可见题名；③ 机检升级：`check-doc-drift` 第 17 项改注册表三向对账（文档行 ↔ 注册表逐列 / 键集双向 / 双端实现提取集合），`recount_html_blocks` 序号重算口径退役，§4.22 口径段改「提取口径」（与 extraction 模块说明同源双写）；④ 矩阵事实纠错：新闻章对照表计数 1→2（双端同级标题）、LLM 四个章节的幻影项「事实校验摘要」撤除（运行时内容内嵌无标题行）、`fundamental_snapshot` 清单补全名、组合演进清单改 5 项对等；⑤ 测试：新增 `test_section_block_contract.py`（键集双向/双端提取对账/双端对等/载体存在/归一化与直通包装/动态拒绝）+ `TestBlockMatrix` 注册表篡改与缺契约用例，evolution/holdings/fund_performance 受影响题名断言与 patch 面同步；顺带用户可见标题去配置键泄漏（`候选基金比较（候选来自 config.comparison_candidates）` → `候选基金比较（比较对象由配置指定）`，两端四处） | rf-616
- **工程效能**：**近 36 小时实现技术债务自查（27 提交 / 247 文件）** —— 新增符号测试引用与行为级覆盖交叉（199 项全命中）、TODO/FIXME/抑制标记扫描、删除符号残留、文件行数派生源与文档登记核对全净；唯一发现 rf-617（`_doc_drift/_tree.py` 矩阵解析 5 处下标抑制改 `cast` 收窄）当批修复；rf-75（注册表行数临界 780/800）为已登记挂账、按既定触发条件后续处理 | rf-617

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
