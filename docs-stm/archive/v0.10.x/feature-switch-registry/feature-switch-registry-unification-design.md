# 功能开关注册表统一 — 设计

> 状态：**已实现**（2026-09-11，批次①转正 + 批次②注册表统一均已落地；计划项 plan-39、自审记录 rf-346）
> 文档版本：0.10.18-dev
> 相关约束：`technical.md` 架构设计约束「功能开关注册表唯一事实来源」（本设计修订该条口径——适用范围扩至全部开关、登记点改指 `feature_switch_registry`，已同步落文）
> 涉及模块：`config/features.py`（注册点）、`tui/handlers_config.py`、`web/config_edit.py` + `src/static/web/main.js`、`cli/cli.py`
> 已归档。原始路径：`docs-stm/plan/feature-switch-registry-design.md` → `docs-stm/archive/v0.10.x/feature-switch-registry/`

---

## 1. 问题：三件事被拧在一个容器里

`features.py` 的 `EXPERIMENTAL_FEATURES` 目前同时承担三件互不相干的事：

| 承担的事 | 实际语义 | 消费方 |
|:--|:--|:--|
| **面板可见性** | 这 10 项在 TUI 菜单 `[S]` 与 Web 配置面板可切换 | TUI / Web 面板渲染 |
| **默认关** | 实验项出厂关闭（`_FEATURE_FLAGS_DEFAULT` 里逐项写 `False`） | `get_feature_defaults()` |
| **是否进产物自述** | 开启后报告页脚/Excel 要自述生成条件 | `enabled_experimental_features()` |

三件事耦合的直接后果，在 `doctor_check` 转正时已经显现：**「转正」（默认值改 `True` + 移出实验注册表）会连带摘掉可见性**——该开关自此在 TUI 菜单 `[S]`、Web 配置面板、CLI `--experiment` 三处全部消失，唯一关闭途径是手改 `features.json`。同类现象的另一半更早就存在：`metrics_*`（7 项）与 `enable_interactive_charts` 从来不在任何界面通道内，同样只能手改 JSON。

于是用户看到的是：**19 项同质的「功能开关」，一半能在界面里改，一半不能；而「能不能在界面改」取决于它是不是被标为实验项**——两者本无逻辑关系。

## 2. 目标与非目标

**目标**

1. 「面板可见性」「默认值」「是否进产物自述」三件事各自有明确归属，互不牵连（转正不再丢可见性）。
2. 全部 19 项功能开关都有三面可控入口：TUI 面板、Web 配置面板、CLI（本次运行）。
3. `datasource_adapter` 转正为默认开启（内部接缝不应占用用户开关且默认关）。
4. 注册表仍是唯一登记点，渠道层与文档清单一律由它派生（该约束的意图不变、覆盖面由实验开关扩到全部开关）。

**非目标**

- 不改 `features.json` 文件格式（仍是「只存覆写子集」的扁平 JSON）。
- 不引入「每数据域/每模块」的细粒度开关，不新增任何功能开关（本次为零新增开关的纯结构变更 + 一项默认值变更）。
- 不改 `--experiment` 的既有语义（实验组、只开不关、不写盘）。

## 3. 设计：注册表是唯一登记点，分组是属性

### 3.1 单条声明

```python
@dataclass(frozen=True)
class FeatureSwitchDef:
    label: str           # 显示名（TUI 行名 / Web 标签，服务端同源下发）
    desc: str            # 一句话说明（CLI 报错提示 / 文档 / doctor 上屏）
    group: str           # 分组：决定面板分块与是否属「实验」
    default: bool        # 出厂默认值
    affects_report: bool # 开启后报告产物内容是否可能不同
```

`feature_switch_registry: dict[str, FeatureSwitchDef]` 登记**全部 19 项**，按分组与默认值分块排列、顺序即面板顺序。

### 3.2 分组语义（两个分组，由「默认值 + 生命周期」定义）

| 分组常量 | 面板标题 | 语义 | 成员（19 项） |
|:--|:--|:--|:--|
| `GROUP_EXPERIMENTAL` | ⚗ 实验性功能（默认关闭） | 改变产物、需真实数据验证后择机转正 | 辩论 3 + 决策反思 + 信号预消化 + 模块质量分级 + 决策头结构化 + 确定性信号沉淀 + 数据源凭据就绪（9） |
| `GROUP_STANDARD` | 常规开关（默认开启） | 默认开、用户可关的常驻开关 | 量化指标 7 + 交互图表 + 系统自检 + 数据源适配契约（10） |

分组不是「优先级」也不是「新旧」，而是**生命周期的当前状态**：实验组是「默认关、待验证」，常规组是「默认开、可关」。**转正 = 把一条声明从实验组改到常规组并把 `default` 改 `True`**——一个字段的改动，面板可见性由此自动延续（不再有「转正即消失」）。

### 3.3 三个事实的归属

| 事实 | 唯一归属 | 派生方式 |
|:--|:--|:--|
| 开关是否存在 / 显示名 / 说明 / 分组 / 默认值 / 产物影响 | `feature_switch_registry` | 直接读取 |
| 出厂默认值字典 | 注册表 | `_FEATURE_FLAGS_DEFAULT = {k: d.default for k, d in feature_switch_registry.items()}`（保留旧名作**派生投影**，`get_feature_defaults()` 与文档引用不变） |
| 运行时取值 | `FEATURE_FLAGS`（注册表默认值 + `features.json` 覆写 + 命令行增量） | 不变 |
| 实验清单 | 注册表 | `switches_in_group(GROUP_EXPERIMENTAL)`（`EXPERIMENTAL_FEATURES` 作为「容器」的概念消失，改为分组属性） |
| 产物自述清单 | 注册表 | `enabled_experimental_features()` = 实验组 ∧ `affects_report` ∧ 已启用 |

**为什么 `affects_report` 仍留在每条声明上**：实验组用它过滤产物自述；常规组用它标注「关掉这一项会改变报告内容」——`metrics_sharpe` 关掉即少一个指标、`enable_interactive_charts` 关掉即回退静态渲染并把 HTML 从单文件自包含变为依赖同目录 JS；而系统自检是只读诊断，关掉只影响入口显隐。这条差异正是用户改动前需要知道的，故两个分组都消费该字段。

### 3.4 查询与解析助手（全部收敛在 `features.py`）

| 助手 | 用途 |
|:--|:--|
| `switches_in_group(group)` | 面板渲染与实验清单（顺序 = 注册表顺序） |
| `resolve_experiment_flags(names)` / `describe_experiment_flags()` | `--experiment` 取值解析与报错提示（取值域 = 实验组，语义不变） |
| `resolve_switch_values(pairs)` / `describe_switches()`（新增） | `--feature NAME=VALUE` 取值解析与报错提示（取值域 = 全注册表） |
| `enabled_experimental_features()` / `log_experimental_features()` | 产物自述与控制台横幅（语义不变） |

**渠道层不得再有任何开关清单字面量**——TUI 面板、Web 白名单与标签、CLI 取值域与提示、doctor 的功能开关组，全部经上表助手取数。

## 4. 架构约束遵从

| 约束（按语义称名，见技术设计文档约束表） | 本设计的处置 |
|:--|:--|
| **功能开关注册表唯一事实来源** | **修订口径**：由「实验功能的枚举/显示名/说明/默认值来自 `EXPERIMENTAL_FEATURES` / `_FEATURE_FLAGS_DEFAULT`」扩展为「**全部功能开关**的枚举/显示名/说明/分组/默认值/产物影响来自 `feature_switch_registry`」；适用范围由「实验开关」扩到「全部可切换开关」，**禁止渠道层另写清单**的禁令不变、覆盖面扩大。修订后 TUI 面板、Web 白名单与标签、CLI 取值校验与提示、用户/管理文档清单仍一律派生自唯一注册点 |
| **缓存与覆写原子写入** | 不受影响：`save_feature_overrides()` 仍委托 `core/atomic_write.write_json_atomic` |
| **测试标记 / edge 文件隔离 / 敏感路径隔离** | 新增用例一律带 marker；`features.json` 路径已由 `_isolate_sensitive_paths` 重定向到 `tmp_path`；`_auto_reset_feature_flags` 每测重置注册表取值 |
| 语义命名纪律 | 新增标识符用语义名（`feature_switch_registry` / `switch_group_*` / `switches_in_group` / `--feature`），并在 `technical.md` §6.7 功能语义命名表登记；不使用任何任务代号 |
| 文档纪律 | 手册与管理文档只描述「当前是什么」；本设计的迁移过程仅记于 `plan.md` / `review-findings.md` / `changelog.md`（豁免文档）与本文件（`docs-stm/plan/` 豁免扫描） |

## 5. 三渠道接入点与数据契约

| 渠道 | 接入点 | 契约 |
|:--|:--|:--|
| TUI | `tui/handlers_config.py::_cmd_config_llm_modules` | 面板分三块：标准 LLM 模块（`llm_settings.json`）→ 实验组 → 常规组；编号按「标准模块数 + 注册表序号」连续分配，**常规块追加在实验块之后**（既有编号不位移）；行名 `pad_right(label, name_column)` 维持矩形对齐；切换写 `set_feature_enabled` + `save_feature_overrides`（两个分组同一路径） |
| Web | `web/config_edit.py` 白名单第 7 组 + `get_config_edit_surface()`；`src/static/web/main.js::renderConfigEdit` | 白名单第 7 组改为对全注册表推导（键不变、值域扩大）；surface 新增顶层 `features` = `{experimental: {flag: bool}, standard: {flag: bool}, labels: {flag: 显示名}, report_affecting: [flag, ...]}`，标签与「影响报告」标记由服务端同源下发，前端不写字典；写入复用既有 `writer: "features"` 原语（键无关，无需新原语） |
| CLI | `cli/cli.py` 全局参数 | 新增 `--feature NAME=VALUE`（可重复；`VALUE ∈ on/off/true/false/1/0`，大小写不敏感；`NAME` 取全注册表开关名）；**仅本次运行、双向、不写盘**；取值在 argparse `type` 回调即时校验、报错列出可选值。`--experiment NAME` 语义不变（实验组、只开不关、支持 `all`）。两者共用同一应用原语，早返回命令（`doctor` / `check-sources` / `view-logs` / `cassettes`）同样生效，顺序仍为「先加载 `features.json` 覆写、再叠加命令行增量」 |

## 6. 转正机制

**判据（三条同时成立）**：① **安全**——默认开启对未主动选择它的用户不产生不可接受代价（费用 / 耗时 / 误报 / 写入用户数据）；② **确定**——已有真实数据上稳定的证据，单元测试只证明「按设计运行」；③ **可回滚**——开关保留，且关闭路径仍有测试覆盖。

**步骤**：① 声明从实验组分到常规组、`default` 改 `True`（一处改动）；② 关掉后的行为口径写进声明 `desc` 与文档（回退到什么）；③ 补「默认配置下走新路径」与「显式关闭后走回退路径」两向测试；④ 管理文档与手册同步。

**本次转正 `datasource_adapter` 的理由**：它是**内部接缝**而非用户功能——开启与否报告产物逐源等价（`test_quote_adapter_parity.py` 锁定，唯一差异是东财多出 `market_cap`/`pe` 两个 `None` 键，下游一律 `.get()` 读取、语义不变），用户开它没有任何收益，挂在用户面前只会让人误以为「开了有好处」；而默认关的代价是**生产路径从不执行适配器分支**，接入新数据源/新字段的契约得不到实跑覆盖。转正后默认走适配器、既有转换函数保留为回退杠杆（`features.json` 置 `false` 即回退）。

**本次不转正的**：`datasource_credential_ready` 保持实验组，随首个需凭据的数据源接入时一并转正——当前声明表为空，机制虽有合成声明的单元测试，但尚无真实场景（转正后一旦声明非空即会「跳过缺凭据的源」，属会改产物的行为，须有真实数据背书）。

## 7. 实施批次

**批次①：转正 `datasource_adapter`**（小步、独立可验证）

1. `features.py`：从实验注册表移出；`_FEATURE_FLAGS_DEFAULT` 该键改 `True`；注释说明回退路径。
2. 消费点口径复核：`fetcher/price.py::_price_chain_slots()`（开关读取保留，仅默认值变）、`core/doctor.py` 的「数据源适配」组。
3. 测试：默认值 True / 不在实验清单 / 显式置 `false` 仍走既有转换函数（回退杠杆有效）/ 默认配置下链路使用适配器。
4. 文档：`requirements.md`（§5.7 标题、R-ADP-08、§11.5 开关行）、`technical.md`（§2.5 标题、目录项、features.json 矩阵行、语义命名表 `source_adapter`/`quote_adapters`/`adapter_chain_slots` 行的开关口径）、手册四处、`developer-guide.md` 转正判据补第二例。

**批次②：注册表统一 + 三渠道上屏**（结构变更）

1. `features.py`：引入 `FeatureSwitchDef` + `feature_switch_registry`（19 项）+ 分组常量 + 查询/解析助手；`_FEATURE_FLAGS_DEFAULT` 改为派生投影；移除 `EXPERIMENTAL_FEATURES` 容器，改用 `switches_in_group`。
2. TUI 面板增常规块（追加在实验块后）+ 面板标题改为分组中性表述。
3. Web 白名单/surface/main.js 增常规组与标签下发。
4. CLI 增 `--feature NAME=VALUE`。
5. 测试与文档同步（含「功能开关注册表唯一事实来源」约束条文的修订、developer-guide 新增开关检查清单改为「分组归属」两栏）。
6. `plan.md` / `review-findings.md` / `changelog.md` 记录。

## 8. 验证方案

| 层次 | 验证 |
|:--|:--|
| 单元 | 注册表不变量（分组取值合法、每条声明五字段齐备、注册表键集 == 默认值键集）；`switches_in_group` 分组正确；`enabled_experimental_features()` 只含实验组且过滤 `affects_report`；CLI `--feature` 双向解析与未知名报错；`--experiment` 取值域仍为实验组 |
| 渠道 | TUI 面板三块渲染 + 编号锚点（既有 6/9/10 用例不位移）+ 矩形对齐 + 常规开关切换落盘；Web 白名单全集、surface 新键、POST 写 `metrics_hhi`/`doctor_check` 落 `features.json`；CLI 早返回命令应用 `--feature` 与不落盘 |
| 集成 | 默认配置下 `_price_chain_slots()` 使用适配器、报告产物自述不含常规组开关 |
| 门禁 | `test-runner.py --mode dev-verify` + `check-code-traces.py` / `check-doc-traces.py` / `check-task-numbering.py` / `check-semantic-index.py` 四个 `--ci` + `ruff check` / `ruff format --check` |
| 人工 | TUI 菜单 `[S]` 观察三块与编号；Web 配置面板观察「常规开关」块与「影响报告」标记；`--feature doctor_check=off doctor` 与 `--experiment all report --type full` 各跑一次 |

## 9. 风险与取舍

| 风险 | 处置 |
|:--|:--|
| 移除 `EXPERIMENTAL_FEATURES` 会让既有文档/测试中的名称失效 | 全仓替换为 `switches_in_group(GROUP_EXPERIMENTAL)`；约束条文与 developer-guide 同步改写；`_FEATURE_FLAGS_DEFAULT` 保留旧名作派生投影以降低文档改动面 |
| 常规组把 7 项量化指标铺进面板，面板变长 | 分组块内按注册表顺序紧凑排列、行名对齐；面板仍为单一入口，避免为「常规开关」另开菜单项（菜单项数由测试锁定，且分块已能表达语义） |
| CLI 两个参数语义重叠 | `--experiment` 保留为实验组简写（只开），`--feature` 为全域双向；两者共用应用原语，文档用「实验组简写 / 全部开关双向」一句区分 |
| 面板新增行破坏矩形对齐断言 | 所有行一律经 `pad_right(..., name_column)`，列宽取注册表全部显示名 + 标准模块名的最大值 |
