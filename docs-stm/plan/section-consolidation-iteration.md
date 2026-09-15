# 报告章节整合实施层（迭代施工单）

> 文档类型：中间设计文件（实施层）——与设计层 [`section-consolidation-design.md`](section-consolidation-design.md) 配套
> 分工：设计层定「合并什么、为什么、新语义名、架构约束对照」；**本文件是施工单**——逐批列出改动文件、
> 命名统一动作、测试同步清单与量化验收标准，实施时按批次勾选并逐批提交
> 状态：批次①已实施；批次②③④待实施

## 1. 命名统一总表（唯一施工依据）

| 旧名（全部删除，不留 alias） | 新语义名 | 新显示名 |
|:--|:--|:--|
| `market_value` + `category` | **`holdings_detail`** | 持仓明细与分类 |
| `position_relationship` + `fund_concentration` | **`position_structure`** | 持仓结构与集中度 |
| `financial_indicator` + `financial_report_digest` | **`fundamental_snapshot`** | 持仓基本面 |
| （`fund_manager` 并入） | `fund_performance`（键/显示名语义未变） | 基金业绩分析 |

**契约层不改名**：`position_relationship_data` / `concentration_data` / `manager_data` /
`financial_indicator_data` / `financial_report_digest_data` 全部保留（契约描述数据内容而非章节）。

## 2. 接缝地图（实施前已核实，含精确位置）

| 接缝 | 位置 |
|:--|:--|
| 注册表条目（顺序/显示名/type/data_flag/**data_flag_any**） | `core/registry.py::_REPORT_SECTION_DEFAULT`（521 行起；字段契约注释见其上方） |
| 页签名表 | `core/registry.py::_REPORT_SHEET_NAMES`（378 行起）+ `get_report_sheet_name()` |
| 可见性判定（Excel 侧） | `report/excel_sheet_factory.py::should_create_sheet`（含 `data_flag_any` OR 支持） |
| 可见性判定（HTML 侧） | `report/html_writer_nav.py::_compute_section_visibility` + `_SECTION_NAV_GROUP_MAP`（导航分组） |
| Excel 分派点 | `market_value`→`excel_generator.py:297`；`category`→`excel_content_sheets.py:58`；`fund_performance`→`excel_content_sheets.py:80`；`fund_manager`/`position_relationship`/`fund_concentration`→`excel_fund_deep_analysis.py:107/129/185`；`financial_report_digest`→`excel_generator.py:396`；`financial_indicator`→`excel_generator.py:407` |
| 页签写入器 | `report/market_value_sheet.py::write_market_value_sheet`(232) / `report/category.py::write_category_sheet`(271) / `report/position_relationship_sheet.py` / `report/fund_concentration_sheet.py` / `report/fund_manager_sheet.py` / `report/financial_indicator_sheet.py` / `report/financial_report_sheet.py` |
| HTML 锚点 | `report_template.html`：`sec-market_value`(1102) / `sec-category`(1183) / `sec-fund_performance`(1393) / `sec-fund_manager`(1499) / `sec-position_relationship`(1563) / `sec-fund_concentration`(1811)；`partials/financial_indicator_section.html` / `partials/financial_report_section.html` |
| 契约写入点 | 经理/集中度/关系数据由编排层组装后写入 `pipeline_data`（`manager_data` / `concentration_data` / `position_relationship_data`） |

## 3. 批次①（已实施，留档）

可见性模型扩展：注册表可选字段 `data_flag_any`（多契约 OR，悲观判定）+ Excel/HTML 两侧支持 +
`src/test/unit/report/test_section_visibility.py`（12 例）。**零条目变更、行为零变化**。

## 4. 批次② 施工单：`holdings_detail`（持仓明细与分类）

**前置**：无（两个来源条目均 `always`、无契约键）。

| 步骤 | 动作 |
|:--|:--|
| ②-1 注册表 | 删除 `market_value` 与 `category` 两个条目；新增 `holdings_detail`「持仓明细与分类」（`type=always`、`data_flag=None`，置于原 position 1/2 的顺序位） |
| ②-2 页签名表 | 删除两条，新增 `"holdings_detail": "持仓明细与分类"` |
| ②-3 Excel 写入器 | 新建 `report/holdings_detail_sheet.py::write_holdings_detail_sheet(ws, ...)`（吸收两表：区块①市值明细 15 列 + 分账户小计；区块②分类汇总）；删除 `report/market_value_sheet.py`、`report/category.py` |
| ②-4 Excel 分派 | `excel_generator.py` 与 `excel_content_sheets.py` 的 `sheets["market_value"]/["category"]` 三处改为 `sheets["holdings_detail"]` 一次调用 |
| ②-5 HTML | `report_template.html` 两个 `div.section` 合并为一个 `sec-holdings_detail`（`section_numbers['holdings_detail']`、标题「持仓明细与分类」，内含两区块小节标题）；删除旧锚点 |
| ②-6 命名统一检查 | `grep -rn "market_value\|sec-category" src/ docs-stm/` 仅允许命中历史 changelog / 归档 / `pipeline_data` 契约（如无则应为零）；`category` 作为普通词（分类）不误删——按标识符边界检索 |
| ②-7 测试同步 | `test_registry`（条目数 21→20、类型集合）、`test_html_report_structure(_edge)`（章节容器数、锚点）、`test_report_chapter_consistency`（双端一致性夹具）、`test_scenario_section_order`、`test_excel_report_structure`、`test_category*.py`/`test_market_value_sheet.py` → 合并为 `test_holdings_detail_sheet.py` |
| ②-8 文档同步 | `reports-instruction`（对照表/章节分组/可见性表）、`technical` §6.7 语义表与 §4.x 叙述、`how-to-config`（若涉及）、`folders` 树与统计、`changelog` |
| 验收 | 条目数 20；Excel 页签减少 1 个且内容等同（两表逐格比对用例）；HTML 章节减少 1 个；`--mode dev-verify` 全绿 |

## 5. 批次③ 施工单：`position_structure`（持仓结构与集中度）

| 步骤 | 动作 |
|:--|:--|
| ③-1 注册表 | 合并为 `position_structure`「持仓结构与集中度」（`type=fund_deep_analysis`，**`data_flag_any=("position_relationship_data","concentration_data")`**，`data_flag=None`） |
| ③-2 页签名表 | `"position_structure": "持仓结构与集中度"` |
| ③-3 Excel | 新建 `report/position_structure_sheet.py::write_position_structure_sheet`（吸收关系矩阵 + 集中度两张表）；删除 `position_relationship_sheet.py`、`fund_concentration_sheet.py` |
| ③-4 分派 | `excel_fund_deep_analysis.py:129/185` 两处合并为一次 `sheets.get("position_structure")` |
| ③-5 HTML | 两个 `div.section`（1563/1811）合并为 `sec-position_structure`；导航分组映射保持 `fund_deep` |
| ③-6 测试 | 增加**OR 可见性用例**：仅有 `position_relationship_data` 时页签/章节可见；两者皆无时隐藏；**两契约写入点不动** |
| 验收 | 条目数 19；OR 语义用例通过；两区块内容等同（逐表比对） |

## 6. 批次④ 施工单：`fundamental_snapshot` + 经理变更并入基金业绩

| 步骤 | 动作 |
|:--|:--|
| ④-1 注册表 | 合并为 `fundamental_snapshot`「持仓基本面」（`type=financial_indicator` 语义化为 `type=fundamental_snapshot`；`data_flag_any=("financial_indicator_data","financial_report_digest_data")`）；`fund_performance` 条目不变 |
| ④-2 页签名表 | `"fundamental_snapshot": "持仓基本面"`；`fund_performance` 名称不变 |
| ④-3 Excel | 新建 `report/fundamental_snapshot_sheet.py::write_fundamental_snapshot_sheet`（区块①指标表 19 列 / 区块②摘要 9 列）；删除 `financial_indicator_sheet.py`、`financial_report_sheet.py`；经理变更区块并入 `fund_performance` 写入器（删除 `fund_manager_sheet.py`） |
| ④-4 HTML | 新建 `partials/fundamental_snapshot_section.html`（两区块，**区块级开关**：区块②需 `is_feature_enabled("financial_report_digest")` 且契约就绪）；删除两个旧 partial；`report_template.html` 的 `sec-fund_manager`(1499) 区块删除并并入 `sec-fund_performance`(1393)（区块级门禁 `is_enable_fund_deep_analysis()`） |
| ④-5 配置 | `_get_default_config_template()` 与 `data/config/config.json` **重生成**（新条目顺序/名称；`report_section_order` 按新条目） |
| ④-6 开关 | `features.py::GROUP_REPORT` 保留 `financial_indicator` 与 `financial_report_digest` 两个功能开关（各控一块）；`fundamental_snapshot` 章节级门禁 = 数据底座就绪（沿用既有 `datasink_feature_ready`） |
| ④-7 测试 | 区块级门禁用例两条（摘要区块随开关关闭消失 / 经理区块随 `enable_fund_deep_analysis=false` 消失且主业绩表保留）；条目数 18；配置模板重生成后的一致性用例 |
| 验收 | 条目数 18；`--mode verify,regression` + 四个 `--ci` + 版本一致性 + ruff 全绿 |

## 7. 收尾（每批之后 + 全部完成后）

- 每批：`--mode dev-verify` + 四个 `--ci` + `ruff check`/`format` + `check-version-consistency`；命名统一 grep 检查；`folders`/`test-coverage` 统计刷新。
- 全部完成后：`--mode verify,regression`；`reports-instruction` 三处目录/可见性表与 `technical` §6.7/附录 H 复核；`changelog` 汇总一条迭代记录。
- **不做**：不做配置兼容迁移；不引入契约层改名；不合并 LLM 相关条目（见设计层非目标）。

## 8. 风险与回退

| 风险 | 缓解 |
|:--|:--|
| 合并后内容遗漏（少搬一张表/一个区块） | 每批以「合并前双端产物」为基准做逐表比对用例（列标题 + 行数 + 关键值） |
| 可见性 OR 语义误判导致空章节 | 悲观判定（未登记视为未就绪）+ 批次③ 专项用例 |
| 区块级门禁漏判导致关闭后仍渲染 | 批次④ 两条专项用例 + 模板侧 `section_visible`/开关双判定 |
| 命名残留（旧键/旧锚点/旧 partial） | 每批强制 grep 检查（仅允许历史 changelog 与归档命中） |
| 中途需要回退 | 每批一次提交，可单独 `git revert`；批次①（模型）与条目变更解耦 |
