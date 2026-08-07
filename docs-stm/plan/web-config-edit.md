# Web 模式配置编辑：完整镜像 TUI 可编辑配置全集 —— 实现设计

> 文档版本：0.10.12-dev（计划层中间文件，非发布文档）
> 关联：plan.md plan-26 · 已确认方案基线（2026-08-07 探讨收敛）
> 状态：**设计定稿，待实现**
> 本文件为「中间计划文件」，实现完成并验证后归档至 `docs-stm/archive/` 对应版本目录。

---

## 1. 结论摘要

用户需求：Web 模式下可以像 TUI 一样修改部分配置项，可编辑项的选择与 TUI **完全一致**。

已确认决策（不推翻，本文档据此细化）：
- **① 先写设计文档**（本文件即交付物）。
- **② 完整镜像 TUI**：Web 配置编辑覆盖 TUI 可编辑配置项的全集，选项与 TUI 完全一致。
- **③ 加 .bak**：Web 写共享 `config.json` 前先备份为 `config.json.bak`。

**实现设计核心决策**：

| 决策点 | 结论 | 一句话理由 |
|:--|:--|:--|
| 编辑范围 | 7 组全集逐项镜像 TUI（自由路径 / 章节开关 / 子模块开关 / 匿名化枚举 / 对比指数池 / LLM 开关 / 辩论实验开关） | 已确认决策 ②，选项与 TUI 完全一致 |
| 新模块 | `web/config_edit.py`（语义名）：白名单 + 读取面板 + 应用单次编辑 + 写前备份 | 配置编辑职责内聚，与 `web/upload.py`/`web/holdings_update.py` 并列 |
| 路由 | `GET/POST /api/config/edit`：GET 返回面板全量可编辑面，POST 应用单次编辑 | 一个资源两个方法，读/写职责清晰 |
| 校验 | 模块级白名单 `config_edit_whitelist`（点分键 → 类型/枚举 → 目标文件 → 写入原语） | `set_config` 无值类型/模式校验，Web 端必须自建白名单 + 值校验（安全事实） |
| 写入分派 | 按目标文件精确匹配 TUI：config.json→`set_config`（嵌套 dict 读合并后整块写）；llm_settings.json→共享 `write_llm_settings`；features.json→`save_feature_overrides` | 与 TUI 编辑路径逐条等价（附录 A 逐项核对源码） |
| 安全守卫 | POST（副作用操作）复用 `_is_same_origin()`，失败 403 BAD_PARAM | Web 无内建认证/无 CSRF，写操作必须同源校验（对齐 `_handle_create_run`） |
| 备份 | 写 config.json 前 `config_backup_file` 单槽轮转 `.bak`（mkstemp + `os.replace` 原子写） | 已确认决策 ③；llm_settings.json / features.json 同为共享文件，复用同 helper 保持一致性 |
| anonymization 键 | Web 编辑写**顶层** `anonymization.mode`（复用 `set_anonymization_mode`）；同步修正两个状态面板读路径到顶层 | TUI 菜单 A 写顶层；两个状态面板误读 `features.anonymization.mode`（该键不存在，恒显示 off）——对齐读=写 |
| 前端 | `index.html` 新增「配置编辑」面板 + `main.js` 加载/渲染/保存/刷新，控件选项与 TUI 完全一致 | 完整镜像；error_code 驱动错误分支，不前端硬编码映射 |
| 语义命名 | `config_edit` / `config_edit_whitelist` / `config_backup` | 语义名即代码名；实现时登记 technical.md 语义表 |

**关键设计事实（已核源码，见附录 A）**：
- TUI 可编辑项实际落在 **3 个共享文件**：`config.json`（路径/章节/子模块/匿名化/对比指数池）、`llm_settings.json`（`enabled_llm`）、`features.json`（辩论实验标志）。
- `set_config`（`config/_core.py:177`）只做**顶层单键 patch**（保留注释），不做值校验；嵌套 dict（`report_submodules`/`comparison_indices`/`anonymization`）由调用方**读合并后整块写**。
- `_PATH_CONFIG_KEYS` 含 `holdings_dir`/`output_dir`（写盘时自动反绝对化），`holdings_filename` 是纯文件名不在其中。
- `anonymization` 为顶层键（默认 `{"mode":"off"}`）；`get/set_anonymization_mode`（`config/anonymizer.py:332/349`）读写**顶层**；但 `tui_menu.py:137` 与 `web/handlers.py:256` 两个状态面板读 `features.anonymization.mode`（默认配置无此键 → 恒 "off"）。

---

## 2. 需求与范围

### 2.1 完整镜像 TUI：7 组可编辑项全集

| # | 组 | TUI 入口 | 配置项（点分键） | 类型/选项 | 写入文件 |
|:--|:--|:--|:--|:--|:--|
| 1 | 自由文本路径 | 菜单 C/F/O | `holdings_dir` / `holdings_filename` / `output_dir` | str（自由文本） | config.json |
| 2 | 报告章节开关 | 菜单 P 1~5 | `enable_fund_deep_analysis` / `enable_news` / `enable_history` / `enable_portfolio_evolution` / `enable_action` | bool | config.json |
| 3 | 报告增强子模块开关 | 菜单 P 6 | `report_submodules.data_quality` / `industry_beta` / `candidate_compare` / `cost_lots` / `valuation_percentile` / `market_temperature` | bool | config.json |
| 4 | 持仓匿名化枚举 | 菜单 A | `anonymization.mode` | enum：`off` / `code_display` / `full_anonymous` / `summary` | config.json |
| 5 | 对比指数池 | 菜单 I | `comparison_indices`（dict：code→名称） | 增 / 删 / 重置为默认 | config.json |
| 6 | LLM 分析章节开关 | 菜单 S | `enabled_llm.global_macro` / `expert_review` / `health_check` / `penetration_deep` / `news_correlation` | bool | llm_settings.json |
| 7 | 辩论实验功能开关 | 菜单 S 6~8 | `llm_debate_procon` / `llm_debate_conditional` / `llm_debate_qa_concentration` | bool | features.json |

**隐藏项（镜像 TUI 语义，不显示但可解释）**：LLM 辩论三模块 `debate_pro`/`debate_con`/`debate_synthesis` 在注册表保留（缓存 TTL/前缀清理仍依赖），TUI 菜单与状态面板均不展示；Web 面板同样不展示，仅以说明文字注明「辩论输出由下方三个实验开关控制」。Web 面板需同步展示该说明（与 TUI 菜单 S 的分隔线注释一致）。

**范围边界**：
- 仅覆盖上表 7 组。TUI 中**不可编辑**的配置项（如 `news_top_count`、`cache_ttl`、`history`、`rebalance` 等）**不在** Web 面板范围——「完整镜像 TUI」的边界是「TUI 能编辑的，Web 都能编辑；TUI 不能编辑的，Web 也不编辑」。
- 不新增任何配置键，不改变 TUI/CLI 行为（除附录 A.3 记录的状态面板匿名化读路径修正——该修正仅影响展示口径，不改变报告行为）。

### 2.2 一致性口径

「选项与 TUI 完全一致」的判定标准：**同一配置项的取值集合、写入目标文件、写入语义**三者与 TUI 编辑路径逐条等价。附录 A 给出源码级对照。

---

## 3. 后端方案

### 3.1 新模块 `src/python/web/config_edit.py`（语义名，职责内聚）

```python
"""Web 配置编辑 — 完整镜像 TUI 可编辑配置全集。

- config_edit_whitelist：可编辑配置项白名单（点分键 → 类型/选项 → 目标文件 → 写入原语）。
  唯一事实来源；`set_config` 不做值校验，Web 端必须自建白名单 + 值校验。
- get_config_edit_surface：读取面板全量可编辑面（GET /api/config/edit）。
- apply_config_edit：应用单次编辑（POST /api/config/edit），按目标文件分派写入。
- config_backup_file：写共享配置文件前的单槽 `.bak` 备份（mkstemp + os.replace 原子写）。
"""

def get_config_edit_surface() -> dict: ...
def apply_config_edit(payload: dict) -> dict: ...
def config_backup_file(path: str) -> str | None: ...
```

### 3.2 路由注册（`web/handlers.py` `create_handlers`）

```python
app.add_url_rule(
    "/api/config/edit",
    "config_edit",
    lambda: _handle_config_edit(),
    methods=["GET", "POST"],
)
```

- `GET` → `get_config_edit_surface()`，只读，无同源校验（与既有只读端点一致）。
- `POST` → 先 `_is_same_origin()`（失败 403 BAD_PARAM），再 `apply_config_edit(payload)`。

### 3.3 白名单 `config_edit_whitelist`（键 → 类型/选项 → 目标文件 → 写入原语）

| 点分键 | 类型/选项 | 目标文件 | 写入原语（精确语义匹配 TUI） |
|:--|:--|:--|:--|
| `holdings_dir` | str | config.json | `set_config(key, value)` |
| `holdings_filename` | str | config.json | `set_config(key, value)` |
| `output_dir` | str | config.json | `set_config(key, value)` |
| `enable_fund_deep_analysis` | bool | config.json | `set_config(key, value)` |
| `enable_news` | bool | config.json | `set_config(key, value)` |
| `enable_history` | bool | config.json | `set_config(key, value)` |
| `enable_portfolio_evolution` | bool | config.json | `set_config(key, value)` |
| `enable_action` | bool | config.json | `set_config(key, value)` |
| `report_submodules.data_quality` | bool | config.json | 读合并 → `set_config("report_submodules", 整块)` |
| `report_submodules.industry_beta` | bool | config.json | 同上 |
| `report_submodules.candidate_compare` | bool | config.json | 同上 |
| `report_submodules.cost_lots` | bool | config.json | 同上 |
| `report_submodules.valuation_percentile` | bool | config.json | 同上 |
| `report_submodules.market_temperature` | bool | config.json | 同上 |
| `anonymization.mode` | enum：`off`/`code_display`/`full_anonymous`/`summary` | config.json | `set_anonymization_mode(value)` |
| `enabled_llm.global_macro` | bool | llm_settings.json | 读合并 → `write_llm_settings` |
| `enabled_llm.expert_review` | bool | llm_settings.json | 同上 |
| `enabled_llm.health_check` | bool | llm_settings.json | 同上 |
| `enabled_llm.penetration_deep` | bool | llm_settings.json | 同上 |
| `enabled_llm.news_correlation` | bool | llm_settings.json | 同上 |
| `llm_debate_procon` | bool | features.json | `save_feature_overrides({key: value})` |
| `llm_debate_conditional` | bool | features.json | 同上 |
| `llm_debate_qa_concentration` | bool | features.json | 同上 |
| `comparison_indices` | action：`add`/`remove`/`reset` | config.json | 读合并 → `set_config("comparison_indices", 整块)` |

**校验规则**（`apply_config_edit` 内集中实现）：
- 未知点分键 → 400 `BAD_PARAM`（不落盘）。
- str 值：必须为非空 str（拒绝纯空白）；`holdings_dir`/`output_dir` 允许绝对路径，写盘时由 `set_config` 自动反绝对化（对齐 `_PATH_CONFIG_KEYS`）；`holdings_filename` 为纯文件名，**拒绝含路径分隔符**（`/`/`\`）——防止用户填「子目录/持仓.xlsx」破坏文件定位。
- bool 值：必须为 `bool`（拒绝 `0`/`1`/`"true"` 字符串——`set_config` 不校验，这里强制）。
- enum：必须命中选项集合（`off`/`code_display`/`full_anonymous`/`summary`），否则 400。
- `comparison_indices`：
  - `add`：`code` 非空且长度 ≥ 3（对齐 `_validate_comparison_indices`：键长 < 3 告警）、`name` 非空 str；`code` 拒绝含 `..`/`/`/`\`（防脏数据污染，非路径向量）。
  - `remove`：`code` 必须已在当前池中，否则 400（对齐 TUI 空池/不存在分支的友好提示）。
  - `reset`：覆盖为默认池 `{"sh000300":"沪深300","sh000905":"中证500","sh000012":"中证全债"}`（对齐 TUI `_DEFAULT_CONFIG.get("comparison_indices")`）。
- `enabled_llm.*` 隐藏键（`debate_pro`/`debate_con`/`debate_synthesis`）**不在白名单**——请求命中即 400，镜像 TUI 隐藏语义。

### 3.4 写入分派语义（对齐 TUI 的精确匹配）

| 目标文件 | 写入方式 | 与 TUI 的等价点 |
|:--|:--|:--|
| config.json 顶层标量 | `set_config(key, value)` | `_edit_single_config`（菜单 C/F/O）与 `_cmd_config_report_boards`（菜单 P 1~5）同用 `set_config` |
| config.json 嵌套 dict | 先 `get_config()` 取当前 dict → 合并单键 → `set_config(顶层键, 整块 dict)` | `_cmd_config_report_submodules`（菜单 P 6）`submodules[key] = not curr; set_config("report_submodules", submodules)`；`_add/_remove/_reset_comparison_index`（菜单 I）同构 |
| config.json 匿名化 | `set_anonymization_mode(value)` | `_cmd_config_anonymization_mode`（菜单 A）同用；写顶层 `anonymization` dict |
| llm_settings.json | 读原始文本（含注释）→ `_update_json_raw_text` 字段级替换 → 原子写 → `get_llm_config()` 刷新 | `_write_llm_settings`（菜单 S）逐字等价——抽取为共享 `write_llm_settings`（见 3.5） |
| features.json | `save_feature_overrides({key: value}, merge=True)` | `_cmd_config_llm_modules` 辩论分支（菜单 S 6~8）同用 |

### 3.5 llm_settings 写入共享化（层间解耦）

当前 `_write_llm_settings(settings, path)` 位于 `src/python/tui/handlers_config.py:56`。Web 层**不得 import TUI 模块**（分层错误），设计将其抽取为 config 层共享函数：

- 在**现有** `src/python/config/_llm_settings.py` 新增公开函数 `write_llm_settings(settings: dict, path: str) -> None`（该文件已存在，含 `get_llm_settings_path`/`get_llm_config` 等，新增本函数与既有职责内聚）：保留注释（`_update_json_raw_text`）、mkstemp + `os.replace` 原子写、写完 `get_llm_config()` 刷新。
- `src/python/tui/handlers_config.py` 的 `_write_llm_settings` 改为**委托**共享函数（或 TUI 调用点直接改调共享函数），行为零变化。
- 测试：既有 TUI 注释保留用例迁移到 config 层测试，TUI 侧保留委托用例。

### 3.6 同源守卫与错误信封

- `POST /api/config/edit` 复制 `_handle_create_run` 的守卫位置（副作用操作）：
  `if not _is_same_origin(): return _err("BAD_PARAM", "同源校验失败，拒绝提交"), 403`。
- 统一信封（复用 `_ok`/`_err`）：成功 `{"ok":true,"data":...}`；错误 `{"ok":false,"error_code":...,"error":中文}`。
- `error_code` 值：

| error_code | HTTP | 触发 |
|:--|:--|:--|
| `BAD_PARAM` | 400 | 未知键 / 类型不符 / 枚举不符 / comparison action 非法（code 缺失、code 不在池、code 含非法字符等） |
| `BAD_PARAM` | 403 | 同源校验失败（对齐 `_handle_create_run`） |
| `CONFIG_WRITE_FAILED` | 500 | `set_config`/`write_llm_settings`/`save_feature_overrides` 抛异常（详情记日志，前端文案不泄露内部细节） |

### 3.7 anonymization 键不一致处理（决策）

**现状不一致**：`config/anonymizer.py` 读写**顶层** `anonymization.mode`（默认键在 `_config_defaults.py:123`）；但 `tui/tui_menu.py:137` 与 `web/handlers.py:256` 两个状态面板读 `features.anonymization.mode`——该键在默认配置中不存在，面板恒显示「关闭」。

**决策**：
- Web 编辑端点**写顶层** `anonymization.mode`（复用 `set_anonymization_mode`），与 TUI 菜单 A 完全一致；「完整镜像 TUI」以 TUI 的实际编辑路径（顶层）为准。
- 随本功能同步修正两个状态面板读路径为顶层（`web/handlers.py:_build_system_info` 改用 `get_anonymization_mode()`；`tui/tui_menu.py:_show_privacy_and_security_status` 同改）。理由：Web 配置面板保存后要能**读回真实生效值**，而读路径若仍指向不存在的键，面板回显与保存值必然漂移；两处修改各为 1~2 行，风险低，直接服务本功能正确性。
- 测试影响：`src/test/unit/web/test_handlers.py` `TestSystemInfo` 断言需从「fixtures 注入 `features.anonymization.mode`」改为「注入顶层 `anonymization.mode`」；`tui` 侧既有状态面板测试同步调整。

---

## 4. 备份：写共享配置前 `.bak`（单槽轮转）

已确认决策 ③ 的范围是 `config.json`；本设计将其扩展为三个共享配置文件统一策略（`config.json` / `llm_settings.json` / `features.json`），理由：三者为同一性质（git 跟踪、用户可编辑、写入失败/误改有恢复需求），同一 helper 低边际成本。

**`config_backup_file(path: str) -> str | None`**（`web/config_edit.py`）：
- 文件不存在 → 返回 `None`（首次写入无需备份）。
- 存在 → 复制为 `{path}.bak`（单槽轮转：第二次写覆盖上一版 `.bak`）。
- 原子性（架构约束 原子写入）：一律 mkstemp 到同目录 → `os.replace` 到 `.bak`，无半写态（复用 `web/holdings_update.py:_atomic_copy` 同型实现；`_atomic_copy` 当前为私有，可提为 web 层共享 helper 或在本模块内复制等价实现——实施时二选一，倾向提取共享）。
- 失败语义：备份失败 → 抛错中止本次配置写入（目标目录不可写时不写半截配置）。
- 恢复路径：用户手动把 `{path}.bak` 改回 `{path}`；`how-to-config.md` / `faq.md` 说明。
- **调用时机**：`apply_config_edit` 内、按目标文件分派写入前调用。config.json 写一次、llm_settings.json 写一次、features.json 写一次——每次独立备份各自文件。
- 注意：`set_config` 本身已用 mkstemp + `os.replace` 保证 config.json 无半写态；`.bak` 是**逻辑备份**（可回滚上一版），与原子写是两个层面，不冲突。

---

## 5. 前端方案

### 5.1 页面结构（`src/static/web/index.html`；前端资源随并行重构已从 `src/python/web/{templates,static}/` 迁至 `src/static/web/`）

新增「配置编辑」card（放在「生成区」之后、「进度区」之前），标题「③ 配置编辑（与 TUI 菜单一致）」——现有 ①②③④⑤ 编号顺延调整为 ①上传 ②生成 ③配置编辑 ④进度 ⑤结果 ⑥状态区。面板分组（对齐 TUI 7 组）：

| 分组 | 控件 | 选项 |
|:--|:--|:--|
| 1 路径与文件 | 3 个文本输入 + 各自「保存」 | `holdings_dir` / `holdings_filename` / `output_dir` |
| 2 报告章节 | 5 个 checkbox | 基金深度分析 / 市场新闻 / 组合历史走势+回撤 / 组合演进 / 行动建议 |
| 3 报告增强子模块 | 6 个 checkbox | 数据质量仪表盘 / 行业Beta子表 / 候选基金比较子表 / 成本流水 / 估值分位 / 市场温度 |
| 4 持仓匿名化 | 4 个 radio（或 select） | off / code_display / full_anonymous / summary（中文描述与 TUI 菜单 A 完全一致） |
| 5 对比指数池 | 列表 + 添加表单（code+名称）+ 每项删除按钮 + 重置按钮 | code (名称) 逐行展示；空池显示「空池（仅显示沪深300）」 |
| 6 LLM 分析章节 | 5 个 checkbox | 全球政经局势 / 智囊团深度复盘 / 持仓体检报告 / 穿透深度分析 / 新闻关联分析；隐藏项说明文字（辩论三模块不展示） |
| 7 辩论实验功能 | 3 个 checkbox | 辩论-正反辩论 / 辩论-条件推理 / 辩论-集中度问答（标 ⚗ 实验性，与 TUI 一致） |

- 面板顶部：说明条「配置修改立即写入共享配置文件（config.json / llm_settings.json / features.json），写前自动备份 .bak；TUI / CLI 下次读取即生效」。
- 面板底部：「重新加载」按钮（重新 GET 全量面，丢弃未保存改动）。

### 5.2 交互（`src/static/web/main.js`）

- 页面加载时 `loadConfigEdit()` 调 `GET /api/config/edit`，按返回分组渲染；渲染一律 `textContent`/DOM API（XSS 防护纪律，禁止 innerHTML）。
- 保存：**即改即存**（已确认，非二选一）——每个控件改动即提交 `POST /api/config/edit`（`{key, value}` 或 `{key, action, code?, name?}`），与 TUI「改一项存一项」的即时保存语义完全一致。提交期间该控件禁用，成功后回读该项最新值；失败恢复为改动前值并显示错误。
- 失败反馈：`error_code` 驱动——`BAD_PARAM`（400）→ 该分组错误区显示服务端中文文案；`BAD_PARAM`（403）同源失败 → 面板顶部警示「同源校验失败，请刷新页面重试」；`CONFIG_WRITE_FAILED` → 面板错误区 + 提示查看日志。中文文案一律直显服务端，不前端硬编码映射（对齐既有 error_code 约定）。
- `comparison_indices`：添加成功后本地追加行；删除成功后移除行；重置后整组重渲染。
- a11y：checkbox/radio 用原生 label 包裹（键盘可达）；分组 `role="group"`/`aria-labelledby`；错误区 `role="alert"` `aria-live="polite"`；375px 下分组纵向堆叠（沿用现有响应式规则）。

### 5.3 样式（`src/static/web/style.css`）

复用既有 `field-check` / `field-block` / `status-text` / `btn` 体系；新增配置分组卡片内联样式（分组标题、开关行、错误区红色语义色）。

---

## 6. 数据契约

### 6.1 `GET /api/config/edit` → 200

```json
{
  "ok": true,
  "data": {
    "paths": {
      "holdings_dir": "/abs/path/data/holdings",
      "holdings_filename": "个人投资持仓信息.xlsx",
      "output_dir": "/abs/path/reports"
    },
    "sections": {
      "enable_fund_deep_analysis": true,
      "enable_news": true,
      "enable_history": true,
      "enable_portfolio_evolution": true,
      "enable_action": true
    },
    "submodules": {
      "data_quality": true,
      "industry_beta": false,
      "candidate_compare": false,
      "cost_lots": false,
      "valuation_percentile": false,
      "market_temperature": false
    },
    "anonymization": {
      "mode": "off",
      "options": ["off", "code_display", "full_anonymous", "summary"]
    },
    "comparison_indices": {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"},
    "comparison_indices_defaults": {"sh000300": "沪深300", "sh000905": "中证500", "sh000012": "中证全债"},
    "llm": {
      "enabled_llm": {
        "global_macro": true,
        "expert_review": true,
        "health_check": true,
        "penetration_deep": true,
        "news_correlation": true
      },
      "hidden_modules": ["debate_pro", "debate_con", "debate_synthesis"],
      "debate": {
        "llm_debate_procon": false,
        "llm_debate_conditional": false,
        "llm_debate_qa_concentration": false
      }
    }
  }
}
```

- `comparison_indices_defaults` 供前端「重置」按钮确认文案使用（对齐 TUI 重置为默认预设）。
- `anonymization.options` 供前端渲染枚举选项（单一来源，避免前端硬编码枚举漂移）。

### 6.2 `POST /api/config/edit` → 请求

```json
{"key": "holdings_dir", "value": "/abs/path/data/holdings"}
{"key": "enable_news", "value": false}
{"key": "report_submodules.cost_lots", "value": true}
{"key": "anonymization.mode", "value": "code_display"}
{"key": "enabled_llm.news_correlation", "value": true}
{"key": "llm_debate_conditional", "value": true}
{"key": "comparison_indices", "action": "add", "code": "sh000905", "name": "中证500"}
{"key": "comparison_indices", "action": "remove", "code": "sh000905"}
{"key": "comparison_indices", "action": "reset"}
```

### 6.3 `POST /api/config/edit` → 响应

成功 200：

```json
{"ok": true, "data": {"key": "enable_news", "value": false, "backup": "/abs/path/data/config/config.json.bak"}}
```

- `backup`：本次写前 `.bak` 路径；首次写入（无原文件）为 `null`。供前端「已备份」提示。

错误信封（对齐既有 `_ok`/`_err`）：

```json
{"ok": false, "error_code": "BAD_PARAM", "error": "配置键不在白名单: xxx"}
{"ok": false, "error_code": "BAD_PARAM", "error": "同源校验失败，拒绝提交"}
{"ok": false, "error_code": "CONFIG_WRITE_FAILED", "error": "配置写入失败（详情请查看日志）"}
```

---

## 7. 逐文件改动清单

| 文件 | 改动 |
|:--|:--|
| `src/python/web/config_edit.py` | **新建**：`config_edit_whitelist` 白名单 + `get_config_edit_surface` + `apply_config_edit` + `config_backup_file`（语义名） |
| `src/python/web/handlers.py` | `create_handlers` 注册 `GET/POST /api/config/edit`；新增 `_handle_config_edit`（GET/POST 分派 + POST 同源守卫）；`_build_system_info` 匿名化读路径改顶层 `get_anonymization_mode()` |
| `src/python/config/_llm_settings.py` | **在现有文件新增公开函数** `write_llm_settings(settings, path)`（自 `tui/handlers_config.py:_write_llm_settings` 抽取：注释保留 + 原子写 + `get_llm_config()` 刷新） |
| `src/python/tui/handlers_config.py` | `_write_llm_settings` 改为委托共享 `write_llm_settings`（行为零变化） |
| `src/python/tui/tui_menu.py` | `_show_privacy_and_security_status` 匿名化读路径改顶层（`get_anonymization_mode()`） |
| `src/static/web/index.html`（并行重构后前端资源新位置，原 `src/python/web/templates/`） | 新增「配置编辑」card（7 组控件），编号顺延 |
| `src/static/web/main.js`（原 `src/python/web/static/main.js`） | `loadConfigEdit`/渲染/即改即存/重新加载/error_code 分支（BAD_PARAM/CONFIG_WRITE_FAILED） |
| `src/static/web/style.css`（原 `src/python/web/static/style.css`） | 配置分组样式 |
| `src/test/unit/web/test_config_edit.py` | **新建**：白名单校验、值校验、写入分派、备份、同源守卫、error_code（见 §12） |
| `src/test/unit/web/test_config_edit_edge.py` | **新建**（`@pytest.mark.edge`，`*_edge.py`）：非法键/非法类型/非法枚举/非法 code/超长值等极端输入 |
| `src/test/unit/web/test_handlers.py` | `TestSystemInfo` 匿名化断言改顶层键；新增 `_handle_config_edit` 路由用例 |
| `src/test/unit/web/test_smoke_web.py` | 冒烟扩展：配置面板加载 + 单次保存成功 + 非法键 400（断言数递增） |
| `src/test/unit/tui/test_tui_menu.py`（如存在匿名化状态断言） | 状态面板匿名化读路径断言改顶层 |
| `docs-stm/managements/technical.md` | **实现时**在语义命名表登记 `config_edit`/`config_edit_whitelist`/`config_backup` 行（见 §8 说明） |
| `docs-stm/managements/folders.md` | 目录树登记 `web/config_edit.py` + 测试两文件；统计表同步 |
| `docs-stm/manuals/how-to-config.md` | 新增「Web 模式配置编辑」小节（见 §9） |
| `docs-stm/manuals/faq.md` | 新增 2 条 Q&A（见 §9） |
| `docs-stm/managements/changelog.md` | 新条目（见 §9） |

---

## 8. 语义命名表（本功能拟登记语义 slug）

> 登记时机说明：`check-semantic-index.py --ci` 做**反向校验**——语义表内每个 slug 必须在 `src/python/` 代码中存在引用（防僵尸条目）。本计划为设计阶段（无功能代码），**此时**在 technical.md 登记会挂门禁；故本文档先定语义名（语义名即代码名），**实现阶段随代码落地一并登记**到 technical.md 语义表（对齐 plan-25 先例：`snapshot_namespace` 等行在六阶段落地时登记）。

| 语义 slug | 中文名（文档/UI） | 归入章节 | 决策链环节 | config 开关 |
|:--|:--|:--|:--|:--|
| `config_edit` | Web 配置编辑（覆盖 TUI 可编辑全集） | Web 配置 | 配置编辑 | 无（功能面） |
| `config_edit_whitelist` | 可编辑配置项白名单（键→类型/枚举→目标文件→写入原语） | Web 配置 | 配置编辑 | 无（校验面） |
| `config_backup` | 配置写前备份（`.bak` 单槽轮转） | Web 配置 | 配置编辑 | 无（安全面） |

**实现时标识符约束**（保证反向校验通过）：`scripts/check-semantic-index.py:190` 用**大小写敏感子串匹配** `slug in _code_without_comments(text)` 且剥离注释——docstring 写 slug 无效，必须真实代码标识符含字面量。模块 `web/config_edit.py`、函数 `apply_config_edit`/`get_config_edit_surface` 含 `config_edit` 字面量；白名单定义为模块级**小写** `config_edit_whitelist = {...}`（数据字典，非 UPPER_SNAKE 常量——大写会因大小写敏感匹配不过；此小写数据名是对语义索引的反向校验要求，非普通常量风格，见语义命名纪律）；备份函数命名必须含 `config_backup` 字面量（如 `config_backup_file`）。

---

## 9. 文档清单

- **plan.md**：P4 章节登记 plan-26 条目（含设计文档链接与要点），`plan-next` 26→27。
- **technical.md**：**实现时**在 `<!-- semantic-index:start -->` 区域登记上表 3 行；架构设计约束无新增（原子写入/测试标记强制/边缘测试文件隔离 已覆盖）。
- **folders.md**：目录树登记 `src/python/web/config_edit.py`、`src/test/unit/web/test_config_edit.py`、`test_config_edit_edge.py`，`plan/` 目录登记本设计文档；统计表「项目文档」「plan/」计数同步。
- **how-to-config.md**：新增「Web 模式配置编辑」小节——可编辑项覆盖 TUI 全集（7 组）、修改即写共享文件（config.json / llm_settings.json / features.json）、写前自动备份 `.bak`、TUI/CLI 下次读取即生效（缓存按文件修改时间自动失效）、Web 与 TUI 编辑同一份配置需注意跨进程并发覆盖（web 单 worker 串行，与同时运行的 TUI 属另一进程，`set_config` 的写锁只覆盖本进程——既有风险，文档提示「避免 Web 与 TUI 同时改配置」）。
- **faq.md**：①「在 Web 页面改了配置，会影响到 TUI / CLI 吗？」→ 会，同一份共享配置文件，写前自动备份 `.bak`，TUI/CLI 下次读取即生效；②「Web 改配置改错了怎么办？」→ 用 `.bak` 还原（单槽轮转，仅保留最近一份）。
- **changelog.md**：`[0.10.12-dev]` 新条目（Web 配置编辑覆盖 TUI 全集、写前 `.bak`、状态面板匿名化读路径修正）。

---

## 10. 实施顺序与门禁

### 10.1 实施顺序（依赖驱动）

1. **共享层抽取**：在现有 `config/_llm_settings.py` 新增公开函数 `write_llm_settings`；`tui/handlers_config.py` 改为委托（TUI 行为零变化，既有测试先绿）。
2. **后端核心**：`web/config_edit.py`（白名单 + 面板读取 + 应用编辑 + 备份）→ `handlers.py` 路由注册与同源守卫 → T3/T4/T5/T7。
3. **匿名化读路径修正**：`handlers.py:_build_system_info` 与 `tui_menu.py:_show_privacy_and_security_status` 改顶层读 → 同步 `test_handlers.py` 断言 → T8。
4. **前端**：`index.html` + `main.js` + `style.css` 配置面板 → T6/T9（冒烟扩展）。
5. **测试补齐**：`test_config_edit.py` + `test_config_edit_edge.py` + conftest 隔离（复用 `_isolate_sensitive_paths`，见 §12；llm_settings.json 已由 conftest `_isolate_sensitive_paths` seed 到 tmp——T6 写 llm_settings 不污染真实文件，见附录 A）。
6. **文档与门禁**：plan.md 条目、changelog、how-to-config、faq、folders；**实现完成后**登记 technical.md 语义表 3 行并跑全部门禁。

### 10.2 门禁（P0，提交前必须全绿）

- `.venv/bin/python scripts/test_runner.py --mode dev-verify`（核心单元 + 基础场景快速验证，含新用例）。
- `.venv/bin/python scripts/check-code-traces.py --ci`（本设计全程语义名，无 plan-26 进标识符）。
- `.venv/bin/python scripts/check-doc-traces.py --ci`（docs-stm/plan/ 仅章节编号 + 架构约束代号检查；本设计避免「N 章」数字暗号，报告章节一律用「X」章语义名）。
- `.venv/bin/python scripts/check-task-numbering.py --ci`（plan-26 编号登记后 `plan-next=27` 仍严格大于已用最大）。
- `.venv/bin/python scripts/check-semantic-index.py --ci`（实现后 3 行语义 slug 反向校验通过；设计阶段**不登记**）。
- `.venv/bin/ruff format --check`（非阻塞，可 `ruff format` 自修）。

### 10.3 合入门禁（P1）/ 发布门禁（P2）

合并/发布前补跑 `test_runner.py --mode verify`（P1）与 `verify,regression`（P2），与现有门禁一致，无新增特例。

---

## 11. 风险/技术债

### 11.1 风险登记表

| # | 风险 | 等级 | 缓解 |
|:--|:--|:--|:--|
| R1 | Web 无内建认证 / 无 CSRF token，配置写接口被跨站伪造提交 | 中 | 写操作复用 `_is_same_origin()`（Sec-Fetch-Site + Origin 校验）守卫；残余风险同 `_handle_create_run`（浏览器跨站表单/简单请求无法带 JSON Content-Type，天然受限；`Sec-Fetch-Site` 主流浏览器均携带）。文档明示 Web 模式为本地单人工具，不建议暴露到不可信网络 |
| R2 | `set_config` 不做值类型/模式校验，误写脏数据进 config.json | 高 | `config_edit_whitelist` 白名单强制（键 + 类型 + 枚举 + comparison action 校验），校验失败 400 不落盘；`set_config` 内部仍会拒绝非法 JSON（注释剥离后校验） |
| R3 | 嵌套 dict（`report_submodules`/`comparison_indices`/`anonymization`）读合并时基于过期快照覆盖丢失并发修改 | 低 | 与 TUI 相同模式（读→改→整块写）；web 单 worker 串行，进程内无并发；跨进程（TUI 同时编辑）为既有风险（R5） |
| R4 | 写共享配置前备份失败/写失败导致配置损坏 | 低 | `config_backup_file` 失败即中止；`set_config`/`write_llm_settings`/`save_feature_overrides` 均 mkstemp + `os.replace` 原子写，无半写态；`.bak` 提供单槽回滚 |
| R5 | Web 与 TUI 分属两进程同时编辑同一配置文件 | 中 | `set_config` 的 RLock 只覆盖本进程，跨进程读-改-写覆盖为既有风险（非本功能引入）；文档提示避免并发编辑；`.bak` 缓解误覆盖恢复 |
| R6 | 状态面板匿名化读路径修正影响既有测试/展示 | 低 | 修改仅两处读代码 + 同步测试断言；修正后面板真实反映生效模式（修 bug，非行为变化） |
| R7 | 前端资源位置随并行重构迁移至 `src/static/` | 低 | 迁移已在工作区落地（`src/static/web/` + `src/static/tmpl/`）；本设计改动清单已按新路径更新，前端与后端只经 `GET/POST /api/config/edit` 契约耦合，**位置无关**——后续仅移动文件、不改契约 |
| R8 | comparison_indices 键含非法字符污染指数池 | 低 | 校验 code 长度 ≥ 3 且拒绝 `..`/`/`/`\`；写盘后 `_validate_comparison_indices` 兜底告警 |

### 11.2 技术债登记

| # | 债务 | 影响 | 处置 |
|:--|:--|:--|:--|
| TD1 | `set_config` 无值校验是长期现状，Web 白名单仅覆盖可编辑子集 | 直接编辑 config.json 的用户仍可能写入脏值（仅 WARNING 不阻断） | 接受（`validate_config` 已告警兜底）；Web 面板强制校验是本功能的缓解边界 |
| TD2 | `.bak` 单槽轮转，第二次写丢失上一版备份 | 回滚窗口仅 1 版 | 接受（KISS，与 `holdings_update` 的 `.bak` 策略一致）；文档说明 |
| TD3 | `_atomic_copy`（`web/holdings_update.py`）当前为私有，备份逻辑可能复制实现 | 重复代码 | 实施时评估提取 `web/_atomic_copy.py` 或 config 层共享；本设计倾向提取共享，未定前按复制等价实现（T 测试兜底） |
| TD4 | 状态面板匿名化读路径历史误读（读 `features.anonymization.mode`） | 此前面板恒显示「关闭」 | 随本功能修正（见 §3.7），changelog 记录 |

---

## 12. 测试矩阵（最小充分集）

> 所有新增/修改用例**必须**带 pytest marker；edge 场景入 `*_edge.py`；LLM/网络一律 mock；不触碰真实 `data/config/`（conftest `_isolate_sensitive_paths` autouse 已把 config.json 与缓存重定向到临时目录）。

| # | 测试 | 归属 | 断言要点 |
|:--|:--|:--|:--|
| T1 | 白名单完备：7 组全部点分键均在 `config_edit_whitelist`，且与 TUI 编辑项一一对应 | unit_web | 枚举白名单断言（防新增 TUI 项漏登记） |
| T2 | 隐藏 LLM 键（`enabled_llm.debate_pro/con/synthesis`）不在白名单 → 400 | unit_web | 镜像 TUI 隐藏语义 |
| T3 | `GET /api/config/edit` 返回面板全量（paths/sections/submodules/anonymization/comparison_indices/llm） | unit_web | 分组齐全、值来自 `get_config()`/llm_settings/features |
| T4 | 标量写：`holdings_dir`/`enable_news`/`anonymization.mode` 分别走 `set_config`/`set_anonymization_mode` | unit_web | 写后 `get_config()` 读回正确；config.json 内容含新值 |
| T5 | 嵌套 dict 写：`report_submodules.cost_lots` / `comparison_indices` 增/删/重置 读合并后整块写 | unit_web | 其余子键/指数保留；重置=默认池 |
| T6 | llm_settings 写：`enabled_llm.news_correlation` 走 `write_llm_settings`（注释保留、原子写、刷新缓存） | unit_web | 文件注释不丢；`get_llm_config()` 读到新值 |
| T7 | features 写：`llm_debate_conditional` 走 `save_feature_overrides` | unit_web | features.json 含覆写；运行时 `is_feature_enabled` 为真 |
| T8 | 匿名化读路径修正：`_build_system_info`/`_show_privacy_and_security_status` 读顶层 `anonymization.mode` | unit_web + unit_config | 顶层 mode=code_display → 面板显示「代码显示」 |
| T9 | 校验与守卫：未知键 400、类型不符 400、枚举不符 400、comparison code 非法 400、非 same-origin 403、`CONFIG_WRITE_FAILED` 500 | unit_web | error_code/HTTP 状态精确 |
| T10 | 备份：写 config.json 前生成 `config.json.bak`（内容=旧值）；首次无原文件 → backup=null | unit_web | `.bak` 内容断言；单槽轮转覆盖 |
| T11 | 极端输入：空串/纯空白 str、`0`/`1`/`"true"` 伪 bool、非法枚举、含 `../` code、超长 name | unit_web_edge（`test_config_edit_edge.py`） | 全部 400 不落盘 |
| T12 | 冒烟扩展：配置面板加载 + 单次保存成功 + 非法键 400 | unit_web（`test_smoke_web.py`） | 断言数递增，保持可复跑 |

---

## 13. 预估工作量

| 阶段 | 子项 | 预估 |
|:--|:--|:--|
| 共享层抽取 | `write_llm_settings` 抽取 + TUI 委托 + 测试迁移 | 0.25d |
| 后端 | `web/config_edit.py` + 路由/守卫 + 备份 + 匿名化读路径修正 + 测试 | 0.75d |
| 前端 | 配置面板 + main.js + 样式 + 冒烟扩展 | 0.5d |
| 文档与门禁 | plan/changelog/how-to-config/faq/folders + 语义表登记 + 扫描 | 0.5d |
| **合计** | | **2d**（对齐 plan-25） |

---

## 附录 A：TUI 编辑链路逐项核对（源码级）

| 组 | TUI handler（`src/python/tui/handlers_config.py`） | 写入调用 | Web 等价原语 |
|:--|:--|:--|:--|
| 1 路径 | `_cmd_config_dir`(140) / `_cmd_config_filename`(145) / `_cmd_config_output_dir`(150) → `_edit_single_config`(98) | `set_config(key, new_val)` | `set_config` |
| 2 章节 | `_cmd_config_report_boards`(356) 分支 1~5 | `set_config(key, not curr)` | `set_config` |
| 3 子模块 | `_cmd_config_report_submodules`(429) | `submodules=dict(config.get("report_submodules") or {}); submodules[key]=not curr; set_config("report_submodules", submodules)` | 读合并 → `set_config` |
| 4 匿名化 | `_cmd_config_anonymization_mode`(537) | `set_anonymization_mode(new_mode)`（写顶层 `anonymization` dict，`anonymizer.py:349`） | `set_anonymization_mode` |
| 5 指数池 | `_cmd_config_comparison_indices`(245) / `_add_comparison_index`(295) / `_remove_comparison_index`(324) | `set_config("comparison_indices", new_indices)`；重置 `set_config("comparison_indices", dict(_DEFAULT_CONFIG["comparison_indices"]))` | 读合并 → `set_config` |
| 6 LLM 开关 | `_cmd_config_llm_modules`(155) llm 分支 | `enabled_map[key]=new_val; settings["enabled_llm"]=enabled_map; _write_llm_settings(settings, settings_path)`（`_write_llm_settings`@56） | `write_llm_settings`（共享化后） |
| 7 辩论 | `_cmd_config_llm_modules`(155) debate 分支 | `set_feature_enabled(key, new_val); save_feature_overrides({key: new_val})` | `save_feature_overrides` |

关键核对结论：
- `set_config`（`config/_core.py:177`）顶层单键 patch，保留注释；`_patch_config_key`（`_json_patch.py:292`）是注释保留补丁机制。Web 写 config.json 复用 `set_config` 即与 TUI 完全等价。
- `_PATH_CONFIG_KEYS = {holdings_dir, output_dir, llm_key_file, llm_settings_file, llm_providers_file}`（`_validation.py:47`）——`holdings_filename` 为纯文件名不在其中；`set_config` 写盘时对路径键自动反绝对化（`_patch_value_for_write`@144）。
- `save_feature_overrides`（`config/features.py:206`）merge 覆写 + 原子写 + 运行时状态同步——Web 直接复用。
- 默认指数池（`_config_defaults.py:87`）：`{"sh000300":"沪深300","sh000905":"中证500","sh000012":"中证全债"}`。
- 默认子模块（`_config_defaults.py:48`）：`data_quality:True`，其余 5 项 `False`。
- `enabled_llm` 结构来自 llm_settings.json（`_llm_settings.py:32` `_REPORT_LLM_MODULES` 4 项 + `news_correlation`），TUI 经 `filter_menu_llm_modules`（`tui_menu.py:66`）隐藏 `debate_pro/con/synthesis`（`LLM_MENU_HIDDEN_KEYS`@63）。

---

## 附录 B：遗留风险与推荐下一步

- **遗留风险**：R1（Web 无认证，仅同源守卫）是唯一「中」级安全项——以「同源校验 + 本地单人工具定位 + 文档明示不暴露不可信网络」三重缓解；R5（Web/TUI 跨进程并发编辑）为既有风险，文档提示。
- **推荐下一步**：① 按 §10.1 顺序实施，先落共享层抽取（独立可验证）；② 实施期间同步登记 review-findings 新发现；③ 实现完成后登记 technical.md 语义表 3 行，并跑 §10.2 全部门禁；④ 前端资源位置迁移（并行讨论中）落定后，本功能前端文件随迁但契约不变。
