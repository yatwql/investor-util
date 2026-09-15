# 报告章节整合设计（章节整合第二轮）

> 文档类型：中间设计文件（实现落地后随迭代归档）
> 关联：`core/registry.py` 报告模块注册表、`report/excel_sheet_factory.py` 与
> `report/html_writer_nav.py` 两层可见性模型、`technical.md` §8 架构设计约束
> 状态：设计完成，待实施（批次①~④）

## 1. 背景与目标

报告模块注册表当前有 **21 个条目**（含 LLM 用量），其中若干条目语义同族、体量很薄或
本就是另一条目的子视图。本次整合按**语义家族**归并，把注册表条目数压到 **17**，
并**重生成配置模板与 `config.json`**（按用户决定：不考虑配置兼容）。

**非目标**：不改数据获取层与 LLM 调用编排；不合并「全球政经局势 / 智囊团深度复盘 /
持仓体检报告 / 穿透深度分析」四个 LLM 条目（模块键、提示词、缓存指纹、三渠道上屏与
用量映射成本远高于收益）；不合并「组合历史走势与回撤 / 组合演进」（两者的顶层开关
`enable_history` 与 `enable_portfolio_evolution` 分属不同 type 的 board 层门禁，
合并需要改动两层可见性模型语义，单独评估）。

## 2. 现状事实（实施依据，均经代码核实）

| 事实 | 数据 |
|:--|:--|
| 注册表条目 | 21（`_REPORT_SECTION_DEFAULT`），其中 16 个有 Excel 页签名（`_REPORT_SHEET_NAMES`） |
| pipeline_data 契约键 | 18（`_PIPELINE_DATA_KNOWN_KEYS`，须与附录 H 同步） |
| HTML 渲染分布 | 主模板内联 9 个 `section_visible(...)` 章节 + 4 个 partial（action / evolution / financial_indicator / financial_report） |
| 各条目体量（Excel 表头列数） | 财务指标 19、市值核算明细 15、持仓集中度 11、资产穿透 10、财报摘要 9、基金经理变更 8、风格与因子 8、持仓关系矩阵 6 |
| 用户 `report_section_order` | 18 个 pin（1~18）；**未知键被静默忽略**（实测：`{"ghost_section":3}` 不影响输出） |
| 可见性模型 | 两层：board 层按 `type` 查 `board_flags`；data 层按 `data_flag` 查 `data_flags`/`data_availability`；两者 AND |

## 3. 合并方案（四项，均**保留吸收方主键**）

保留主键的目的：既有 `report_section_order` pin、`report_submodules` 开关名与测试引用
**不需要迁移**；被吸收条目的键从注册表移除（其 pin 变成无害空操作）。

| # | 合并 | 保留键 / 新显示名 | 区块构成 | 门禁策略 |
|:--|:--|:--|:--|:--|
| M1 | 市值核算明细 + 持仓分类 → **持仓明细与分类** | `market_value` / 「持仓明细与分类」 | 区块①15 列市值明细 + 分账户小计；区块②分类汇总表 | 两者均为 `always`（无 board 开关），data_flag 均空 → 合并后仍 `always`，零门禁变化 |
| M2 | 持仓关系矩阵 + 持仓集中度 → **持仓结构与集中度** | `position_relationship` / 「持仓结构与集中度」 | 区块①重合度 + 相关性矩阵；区块②TOP-N 占比 + HHI + 三级预警 | 两者同 `type=fund_deep_analysis`（同一 board 开关）；data_flag 取 OR（见 §5） |
| M3 | 财报摘要 → **持仓基本面** 的区块 | `financial_indicator` / 「持仓基本面」 | 区块①财务指标表（19 列）；区块②财报章节摘要（9 列） | 两者同属功能开关 `GROUP_REPORT` 且同受数据底座门禁；**两个功能开关各控一块**（保留独立关闭杠杆，区块级判定见 §5） |
| M4 | 基金经理变更 → **基金业绩分析** 的区块 | `fund_performance` / 「基金业绩分析」 | 区块①主业绩表（含候选比较子表）；区块②基金经理变更（8 列） | 被吸收项 `type=fund_deep_analysis`（board 开关 `enable_fund_deep_analysis`）→ 区块级判定；**先例**：`report_submodules.candidate_compare` 已是本条目内的可选子表 |

合并后注册表（17 项，编号重排，`llm_usage` 仍强制末位）：
投资分析汇总 / 持仓明细与分类 / 资产穿透TOP10 / 基金业绩分析 / 持仓结构与集中度 /
风格与因子分析 / 行动建议 / 财经新闻热点与持仓关联分析 / 全球政经局势 /
智囊团深度复盘 / 持仓体检报告 / 穿透深度分析 / 组合历史走势与回撤 / 组合演进 /
数据源可用性矩阵 / 持仓基本面 / LLM API 用量。

## 4. 架构约束对照

| 约束 | 本设计如何满足 |
|:--|:--|
| **注册表驱动**（报告序号与显示名不得硬编码） | 全部改动落在 `core/registry.py` 注册表条目（顺序/显示名/type/data_flag）；Excel 页签名表同步；模板与页签写入器一律经 `section_numbers`/`get_report_sheet_name` 取值，不新增硬编码 |
| **渲染期数据经模板 context 传递**（不写模块级全局） | 合并章的两区块判定仍通过模板 context（`section_visible`）与写入器入参传递；不新增模块级状态 |
| **pipeline_data 契约台账** | **不新增 pipeline_data 键**（否则须登记附录 H）；被吸收条目原有的契约键（`manager_data` / `position_relationship_data` / `concentration_data` / `financial_report_digest_data`）**全部保留**，仅渲染归属改为合并条目 |
| **图表图下说明** | 合并只搬运既有区块，图下说明随区块保留（组合时序类条目不在本次合并范围） |
| **实验挂载点集中** | 不涉及（本次不新增实验功能） |
| **缓存统一入口与原子写入** | 不涉及数据层；`config.json` 重生成仍用既有 `core/atomic_write.py` 原语 |
| ** 数据降级治理（§1.4.5）** | 合并条目的可用性 = 各区块契约的 OR（见 §5）；不可用时仍走既有「占位 / 静默省略」策略，不新增降级路径 |

## 5. 可见性模型的最小扩展（关键设计）

注册表条目新增**可选**字段 `data_flag_any: tuple[str, ...]`，语义为「这些 data_flag 任一
为真则本条目可见」；未声明该字段时行为与现状完全一致（向后兼容）。

- `report/excel_sheet_factory.py::should_create_sheet`：有 `data_flag_any` 时对
  `data_availability` 取 OR；否则沿用单键判定。
- `report/html_writer_nav.py::_compute_section_visibility`：同上（data 层）。
- **区块级门禁**（M3/M4）：合并条目的渲染层按被吸收项的原判定取值——
  - M3 的摘要区块：`is_feature_enabled("financial_report_digest")` 且
    `financial_report_digest_data is not None`；
  - M4 的经理变更区块：`is_enable_fund_deep_analysis()` 且 `manager_data` 可用。
  该模式与既有「基金业绩分析章内的候选比较子表」一致（`candidate_compare` 开关 + 契约）。

设计取舍说明：不采用「合成契约键」（如 `holdings_detail_data`）方案——那会在
pipeline_data 台账里增加**没有真实来源**的键（契约键须有明确的写入与消费模块），
而 `data_flag_any` 把「多契约→单条目可见性」的表达留在注册表内，语义更窄、影响面更小。

## 6. 测试与验证（实施时必须同步）

**会变红的既有断言（预期同步项）**：注册表条目数与类型集合（`test_registry`）、
HTML 章节容器数与导航分组映射（`test_html_report_structure*`）、双端章节一致性夹具
（`test_report_chapter_consistency`：Excel 页签序 == 注册表序）、场景全类型集合
（`test_scenario_section_order`）、页签名映射与页签写入断言（`test_excel_report_structure`、
各 `*_sheet` 单测）、`report_section_order` 场景测试、`folders`/`test-coverage` 统计。

**新增守卫（防回归）**：
1. `data_flag_any` 语义守卫——两个契约只给其一为真时合并条目**可见**、两者皆假时隐藏（M2）；
2. 区块级门禁守卫——M3 摘要区块随 `financial_report_digest` 开关关闭而消失、指标区块不受影响；
   M4 经理区块随 `enable_fund_deep_analysis=false` 消失而主业绩表保留；
3. 「注册表条目数 == 17」显式断言（发布前快照，配套文档核对）；
4. 页签名表与注册表条目一一对应（无孤儿/缺失）。

**验证层级**：`--mode dev-verify`（每批）→ `--mode verify,regression`（收尾）→
四个 `--ci` + `ruff check`/`format` + `check-version-consistency`。

## 7. 配置与文档同步清单

| 项 | 动作 |
|:--|:--|
| `data/config/config.json` | **重生成**（`report_section_order` 按新 17 项重排；不做兼容迁移） |
| `_get_default_config_template()` | 模板同步（19→17 项的注释与示例值） |
| `reports-instruction.md` | 「功能与报告位置对照表」「页面/章节分组」「可见性规则总览」三处按新条目重写；页签序号重排 |
| `technical.md` | 注册表驱动约束的适用范围表述（19→17 项）、附录 H（确认无新增键）、§4.x 各条目叙述的合并说明、§6.7 语义命名表如需新增条目名 |
| `how-to-config.md` | 章节可见性节（B）、功能开关表（M）与菜单对应关系按新条目同步 |
| `datasource(-reliability).md` | 若某数据类别的「消费章节」表述受影响（数据质量/财报/指标）则同步 |
| `folders.md` | 目录树（新增/删除文件：合并后的 sheet 写入器与 partial）+ 统计 |
| `test-coverage.md` | 单元分组与功能域计数（合并后测试文件数变化） |
| `changelog.md` | 每条批次一条记录（含「配置模板重生成、不做兼容」的显式说明） |

## 8. 批次划分与验收

| 批次 | 内容 | 验收 |
|:--|:--|:--|
| ① | 注册表扩展 `data_flag_any` + 两个可见性消费点支持 OR（**无条目变更**，纯模型扩展 + 守卫测试） | 既有行为逐字节不变（全部用例绿）；新增 OR 语义守卫 |
| ② | M1 持仓明细与分类（Excel 写入器合并 + HTML 区块合并 + 配置/文档同步） | 页签数与 HTML 区块数各减一；内容与合并前等价（逐表比对用例） |
| ③ | M2 持仓结构与集中度（含 `data_flag_any` 实战） | 上述 + OR 可见性用例 |
| ④ | M3 持仓基本面 + M4 基金经理变更并入基金业绩（区块级门禁） | 区块随各自开关独立显隐；配置模板重生成后 `--mode verify,regression` 全绿 |

每批一次提交、每批跑门禁；批次①单独提交（模型先行，风险隔离）。
