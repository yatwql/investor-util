# R-197 `market_value.py` 计算/写入分离迭代计划 V3

> 创建：2026-07-09 | 更新：2026-07-09 | 状态：**✅ 已完成**
>
> 本版在前版（V2，综合 4 路审查代理 + 10 轮自复盘）基础上，再行 6 轮聚焦复盘，评估风险、收益、技术债务与 C1-C14 设计约束全量合规，并据此产出优化迭代计划。

---

## 1. 动机与目标

`market_value.py` 当前 711 行（全源码第 3 大），混合两重职责：

| 职责 | 函数 | 行数估 | 占比 |
|:----|:-----|:------:|:----:|
| **纯计算** | `_compute_premium`, `DetailRow`, `classify_holdings`, `price_update_status`, `is_market_open`, `is_midday_break`, `_get_trading_calendar`, `_is_trading_day`, `get_last_trading_day`, `get_prev_trading_day`, `_count_trading_days_back`, `_determine_price_type`, `_compute_detail_row`, `_price_cache_key`, `_generate_details` | ~480 | 67% |
| **Excel 写入** | `_detail_to_row_values`, `_num_formats`, `_apply_profit_colors`, `_apply_price_type_colors`, `_write_account_groupings`, `write_market_value_sheet` | ~200 | 28% |
| 辅助 + import + 注释 | 其他 | ~31 | 5% |

### 端状态

```
market_value.py        ~450 行  纯计算（解除 openpyxl/excel_writer/styles 全部依赖）
market_value_sheet.py  ~200 行  Excel 写入（write_market_value_sheet, 着色, 分组小计）
```

依赖方向：
```
market_value.py ← market_value_sheet.py（仅 DetailRow 类型导入）
excel_generator.py → market_value.py + market_value_sheet.py（编排器分别导入计算/写入）
```

### B 系列模式对照（V3 更新）

| 计算模块 | 写入模块 | 计算→写入 跨导入？ | 说明 |
|:---------|:---------|:------------------|:------|
| `fund_concentration.py` | `fund_concentration_sheet.py` | ❌ 无 | 数据由编排器传入 |
| `fund_manager_analysis.py` | `fund_manager_sheet.py` | ❌ 无 | 同上 |
| `fund_overlap.py` | `fund_overlap_sheet.py` | ❌ 无 | 同上 |
| `fund_style_analysis.py` | `fund_style_sheet.py` | ❌ 无 | 同上 |
| `penetration.py` | `penetration_sheet.py` | ✅ 类型导入 | `compute_penetration_top10` 回退 |
| **`market_value.py`** | **`market_value_sheet.py`** | **✅ 仅 `DetailRow` 类型** | 运行时无计算逻辑跨导入 ✅ |

> V2 将 `market_value_sheet` 依赖 `_generate_details`（details=None 回退）与 `penetration` 模式对齐。V3 采纳了"移除 `details=None` 回退，在 `_resolve_market_data` 预计算"的优化建议，使 `market_value_sheet` 只依赖 `DetailRow` 一个类型导入。

---

## 2. 全局设计约束（跨迭代强制执行）

| # | 约束 | 来源 | 说明 |
|:-:|:-----|:-----|:------|
| D1 | 每步门禁：`python scripts/test_runner.py --mode regression` | CLAUDE.md P0 | 通过方得提交 |
| D2 | 目录树同步 | datasource-and-folders.md | 每步新增文件后更新 |
| D3 | 所有测试必须标 marker | C11 technical.md | 新增/修改测试标 `@pytest.mark.unit_report` |
| D4 | 边缘测试文件隔离 | C12 technical.md | edge 标记必须放 `*_edge.py` |
| D5 | C7 注册表链路不变 | technical.md | 不可硬编码报告序号 |
| D6 | 桥接导入必须在文件末尾 | 本计划 | `market_value.py` 中 `from ...sheet import ...` 必须放在所有函数定义之后 |
| D7 | 每步验证循环 import | 本计划 | 每步代码搬迁后执行 `python -c "import src.python.report.market_value; import src.python.report.market_value_sheet"` |
| D8 | 测试敏感路径隔离不变 | C13 technical.md | 不修改 conftest.py 的敏感路径隔离逻辑 |
| D9 | 代码类型判定中心化 | C1 technical.md | 不引入新的 `code.startswith()` 等判断 |
| D10 | 桥接清理零残留 | 本计划 | 终态 `market_value.py` 不应有任何 `from ...sheet import ...` 桥接行 |

---

## 3. 六轮自复盘发现（V2 → V3 优化依据）

### 复盘 1：收益/ROI 评估

| 维度 | 分析 |
|:-----|:------|
| 核心问题 | 11 步迭代 + 15 处 mock 变更 + ~3 天工作量，换什么？ |
| 收益 | `market_value.py` 711→~450 行（-37%）、openpyxl/excel_writer/styles 三组依赖解除、职责单一 |
| 成本 | 11 步操作 + 14 处 mock 路径变更 + ~3 天工作量 |
| ROI 定性 | **中性偏正面**。职责分离的长期维护收益 > 短期操作成本。但迭代可压缩 |
| 建议 | 合并 I-6+I-7 减少 1 步，压缩桥接期 |

### 复盘 2：C1-C14 设计约束深层检查

逐条对全部 14 条约束进行合规检查：

| 约束 | 是否受影响 | 详情 |
|:-----|:---------|:------|
| **C1 代码类型判定中心化** | ✅ 合规 | D9 已涵盖，`is_qdii_extended` 来自 `code_utils` |
| **C2 缓存统一管理** | ❌ 不涉及 | 无缓存逻辑变更 |
| **C3 缓存原子写入** | ❌ 不涉及 | 无文件写入 |
| **C4 会话级 API 复用** | 🟡 已识别 | `_generate_details` 未使用 `session_cache` → TD-3 已记录但缺少 C4 引用 |
| **C5 HTTP 客户端统一** | ❌ 不涉及 | 无新 HTTP 调用 |
| **C6 Provider Chain 必经** | 🟡 已识别 | `_generate_details` 使用 `get_registry().get_effective_strategy()` → TD-3 需补充 C6 引用 |
| **C7 报告序号不可硬编码** | ✅ 合规 | 使用 `get_report_sheet_name('market_value')` |
| **C8 日志统一** | ✅ 合规 | 无新 logger |
| **C9 LLM 模块注册** | ❌ 不涉及 | |
| **C10 新闻召回策略** | ❌ 不涉及 | |
| **C11 测试标记强制** | ✅ 合规 | D3 已涵盖 |
| **C12 边缘测试文件隔离** | ✅ 合规 | D4 已涵盖；搬迁后写入测试无 `@pytest.mark.edge` |
| **C13 测试敏感路径隔离** | ✅ 合规 | D8 已涵盖 |
| **C14 渲染期全局变量** | ❌ 不涉及 | |

**关键发现**：TD-3 描述仅说"混合计算编排"，未注明违反的约束编号（C4、C6）。V3 已更新 TD-3 补充约束引用。

### 复盘 3：实施风险再评估

| 风险 | 严重度 | V2 缓解 | V3 优化 |
|:-----|:------:|:--------|:--------|
| **桥接期双态文件** | 🟡 | 无明确说明 | **合并 I-6+I-7**，桥接期从 6 步缩至 5 步 |
| **Mock 路径手动操作精度** | 🔴 | §7 对照表 | §7 对照表 + **新增批量替换指南**（`sed` 模式） |
| **`_import_report_modules` 拆分遗漏** | 🟡 | FMEA 已标记 | 保持 |
| **`test_excel_generator.py line 294` 断言脆性** | 🟡 | 标记为已知 | **新增验证点**：确认 `"market_value" in e.lower()` 对新错误消息仍然有效 |

### 复盘 4：模块内部一致性审核

| 问题 | V2 状态 | V3 修正 |
|:-----|:-------|:--------|
| **§4 总览图 `I-7 ❗MOCK 改12处`** | 实际只改了 9 处（3 处是 I-6 改的），§4 写 12 处有误→**合并后 I-6 改 12 处**，所以 §4 数字正确但描述需更新 | 合并后统称为`I-6 ❗MOCK 改12处` |
| **§7 合计 `15 处`** | 实际 14 处（3+9+2）。V2 §7 多算 1 处 | **修正为 14 处**（合并步 12 处 + I-7 2 处） |
| **终态 `market_value.py` 行数 `~475`** | 仅算了 openpyxl 清理（-15 行），忽略了 excel_writer/styles 清理（额外 -15 行） | **修正为 ~450 行** |
| **I-9 import 清理范围** | 仅说 openpyxl | **扩展为 openpyxl + excel_writer + styles 三组 import** |

### 复盘 5：替代方案评估

比较四种方案：

| 维度 | A（V2 方案） | B（超大合并） | C（纯 B 系列） | **D/E（混合推荐）** |
|:-----|:-----------:|:-----------:|:-------------:|:-----------------:|
| 迭代数 | 11 | 8 | 12 | **10** |
| Mock 变更 | 14 处 | 14 处 | 14 处 | **14 处** |
| 循环 import 风险 | 🟡 有 | 🟡 有 | ✅ 零 | **✅ 零** |
| 桥接残留 | 6 条 | 6 条 | 0 条 | **0 条** ✅ |
| B 系列对齐 | ❌ penetration | ❌ | ✅ 完全 | **✅ 完全** |
| `_resolve_market_data`改造 | 无 | 无 | 需改 | **需改（~20 行）** |
| `_generate_details` 导入 `_import_report_modules` | 无 | 无 | 需加 | **需加（~3 行）** |

**V3 采用方案 E**：移除 `details=None` 回退（对齐 B 系列）+ 合并 I-6+I-7（压缩迭代）。虽然增加了 I-3 的 `_resolve_market_data` 改造工作，但换来循环 import 风险归零 + 桥接残留归零 + B 系列完全对齐的净收益。

### 复盘 6：终态可维护性评估

**终态检查**：

1. **新功能该放哪个文件？** → 计算逻辑 `market_value.py`，Excel 格式 `market_value_sheet.py` ✅ **清晰**
2. **修改 `market_value_sheet.py` 时如何找测试？** → 当前所有写入测试仍在 `test_market_value.py`，但 I-9（V3 的 I-9）强制测试重组 → ✅ **已规划**
3. **`DetailRow` 类型依赖是否需要跨模块？** → `market_value_sheet` 只需 `from src.python.report.market_value import DetailRow` 一个类型导入 ✅ **可控**
4. **新人能否快速上手？** → 需理解"编排器预计算 → 传入 sheet 写入器"的模式。与 B 系列其他 4 模块一致 ✅

---

## 4. 执行顺序总览

```
I-1 ─→ I-2 ─→ I-3 ─→ I-4 ─→ I-5 ─→ I-6 ─→ I-7 ─→ I-8 ─→ I-9 ─→ I-10
分析    覆盖    骨架    格式    着色    全搬迁   try/    import  文档+   全量
       加固    +预算   函数    函数    6函数    except  清理+   测试    回归
              改造           SAFE   SAFE   12MOCK  拆分    重组    同步
```

> V2 步数：11 步（I-1 ~ I-11）
> V3 步数：**10 步**（I-1 ~ I-10）
> 关键变化：I-6 合并原 V2 的 I-6+I-7，I-7 拆分 + I-8 import 清理 + I-9 测试重组合并为原 V2 的 I-8+I-9+重新排序

---

## 5. 迭代详情

### I-1：函数清单 + 调用者映射

**纯分析，不动代码。**

| 项 | 内容 |
|:---|:------|
| 操作 | 读取 `market_value.py` 每个函数 → 列出签名、行号范围、分类（计算/写入）、依赖（import 了什么模块）、被谁调用 |
| 输出 | 调用者地图表格、两份清单：计算函数集 / 写入函数集 |
| 风险 | ★☆☆☆☆ — 纯文档操作 |
| 恢复 | 删除文档，< 1min |

**验收标准**：
- [ ] 每个函数标记了"计算"或"写入"
- [ ] 写入函数集清单确认：`_detail_to_row_values`, `_num_formats`, `_apply_profit_colors`, `_apply_price_type_colors`, `_write_account_groupings`, `write_market_value_sheet`
- [ ] 所有调用者列出完整路径（含 test 文件中 mock 路径）

---

### I-2：测试覆盖加固

**为写入函数补测，确保迁移后行为不变。**

| 项 | 内容 |
|:---|:------|
| 范围 | 写入函数当前缺失的边界覆盖： |
| | `_write_account_groupings`：单账户路径（`mock_sub.call_count == 1`）、特殊字符账户名、`acc_cost == 0` 分支 |
| | `write_market_value_sheet`：全零行情分支（line 679-685 红色警告行+合并单元格） |
| | `_apply_profit_colors`：空范围、Integer 类型的 `rate_cell.value` |
| 目标 | 每个写入函数至少覆盖 3 个显著边缘场景 |
| 风险 | ★★☆☆☆ — 新增测试可能暴露潜藏 bug，但不会破坏生产代码 |
| 恢复 | `git checkout src/test/` |

**验收标准**：
- [ ] `_apply_profit_colors` 覆盖空范围、None 值、int 类型 rate 值
- [ ] `_write_account_groupings` 覆盖单账户/多账户/空账户/特殊字符账户名
- [ ] `write_market_value_sheet` 覆盖全零行情路径
- [ ] 所有新增测试标记 `@pytest.mark.unit_report`
- [ ] `regression` 门禁通过

---

### I-3：`market_value_sheet.py` 骨架 + `_resolve_market_data` 预计算改造

**关键变化（相对 V2）**：此步不再仅仅创建骨架，同时做 `_resolve_market_data` 改造，使 `market_value_sheet` 在后续步骤中无需 `_generate_details` 跨导入。

| 项 | 内容 |
|:---|:------|
| 操作 1 | 创建 `market_value_sheet.py`，写入模块级 docstring + import（仅从 `market_value` 导入 `DetailRow` 类型）+ 写入函数空壳 |
| 操作 2 | **`_import_report_modules`**（`excel_generator.py`）：在 block A 中注册 `_generate_details` 到 modules dict，使其在 `_resolve_market_data` 中可用 |
| 操作 3 | **`_resolve_market_data`**（`excel_generator.py` line 138-186）：改造 `else` 分支（`details is None` 时），用 `gen_details(holdings)` 预计算 details，然后传入 `mvs()`。**移除 `write_market_value_sheet` 中 `details=None` 回退的依赖** |
| 操作 4 | `market_value.py` 末尾加桥接：`from src.python.report.market_value_sheet import write_market_value_sheet` |
| 关键规则 | **桥接导入必须放在文件末尾**（所有函数定义之后） |
| 验证 | `python -c "from src.python.report.market_value import write_market_value_sheet; from src.python.report.market_value_sheet import write_market_value_sheet"` |
| 风险 | ★★☆☆☆ — `_resolve_market_data` 改造影响报告生成逻辑，需确认回归通过 |
| 恢复 | 回滚 `excel_generator.py` + 删除 `market_value_sheet.py` |

**关于 `_resolve_market_data` 改造的技术细节**：

```python
# 改造前（V2）：
elif details is not None:
    ...
    mvs(ws2, holdings, details=details)
else:
    ...
    total_mv, ... = mvs(ws2, holdings)  # write_market_value_sheet 内部调用 _generate_details

# 改造后（V3）：
# 注册：在 _import_report_modules block A 中增加 _generate_details
# 使用：gen_details = modules.get("_generate_details")
# else 分支改为：
else:
    details = gen_details(holdings) if gen_details else []
    total_mv = sum(d.market_value for d in details)
    ...
    mvs(ws2, holdings, details=details)
    # mvs 不再需要 details=None 回退
```

同时：`write_market_value_sheet` 签名中的 `details: list[DetailRow] | None = None` **暂时保留**（删除默认值在 I-6 搬迁时进行），当前通过 `if details is None` 检查在新的预计算路径下永不触发。

**验收标准**：
- [ ] `market_value_sheet.py` 可被导入无报错
- [ ] `from market_value import write_market_value_sheet` 桥接生效
- [ ] `_import_report_modules` 注册了 `_generate_details`
- [ ] `_resolve_market_data` 改造后调用 `gen_details()` 预计算，不依赖 `write_market_value_sheet` 内部回退
- [ ] 循环 import 验证命令通过
- [ ] `regression` 门禁通过

---

### I-4：搬迁 `_detail_to_row_values` + `_num_formats`（SAFE ✅）

**纯函数搬迁，无 mock 路径断裂风险（桥接保持）。**

| 项 | 内容 |
|:---|:------|
| 操作 | 将 `_detail_to_row_values()` 和 `_num_formats()` 复制到 `market_value_sheet.py`，`market_value.py` 末尾加桥接 |
| Mock 影响 | `@patch("market_value._detail_to_row_values")` → 桥接保持 `market_value` 命名空间绑定 → **mock 继续工作 ✅** |
| 循环 import | `market_value_sheet` 此时仅导入 `DetailRow`（在 `market_value.py` 顶部定义）→ 无环 ✅ |
| 风险 | ★★☆☆☆ |
| 恢复 | 删除桥接行 + 从 sheet 文件删除函数 |

**验收标准**：
- [ ] `test_market_value.py::TestDetailToRowValues` 通过
- [ ] `test_market_value.py::TestNumFormats` 通过
- [ ] `test_integration_scenarios.py` 通过
- [ ] `regression` 门禁通过

---

### I-5：搬迁 `_apply_profit_colors` + `_apply_price_type_colors`（SAFE ✅）

**纯函数搬迁，无 mock 路径断裂风险（桥接保持）。**

| 项 | 内容 |
|:---|:------|
| 操作 | 复制到 `market_value_sheet.py`，`market_value.py` 末尾加桥接 |
| Mock 影响 | `@patch("market_value._apply_profit_colors")` → 桥接保持 → **mock 继续工作 ✅** |
| 依赖 | `openpyxl.styles.Font` + `styles.profit_font` + `code_utils.is_qdii_extended` → `market_value_sheet.py` 需自行 import |
| 风险 | ★★☆☆☆ |
| 恢复 | 删除桥接 + 从 sheet 文件删除函数 |

**验收标准**：
- [ ] `test_market_value.py::TestApplyProfitColors` 通过
- [ ] `test_market_value.py::TestApplyPriceTypeColors` 通过
- [ ] `test_security_edge.py` 通过
- [ ] `regression` 门禁通过

---

### I-6：搬迁全部 4 个剩余写入函数（BREAKING ❌ — 12 mock 路径一次性变更）

**将 V2 的 I-6（分组小计）+ I-7（主函数）合并为一步。这是本计划最大单步。**

| 项 | 内容 |
|:---|:------|
| 搬迁函数 | `_write_account_groupings`、`write_market_value_sheet` |
| 操作 | 将两个函数复制到 `market_value_sheet.py`，保留 `market_value.py` 桥接 |
| 签名变更 | `write_market_value_sheet` 中 `details: list[DetailRow] \| None = None` → **`details: list[DetailRow]`**（必选参数，因 I-3 已改造调用者）|
| **12 处 mock 路径** | `test_market_value.py::TestWriteMarketValueSheet` 全部变更（I-6 完成前全部使用 `market_value.*` → 完成后全部使用 `market_value_sheet.*`） |

**Mock 路径对照表**：

```python
# 变更前（market_value.*）→ 变更后（market_value_sheet.*）
@patch("src.python.report.market_value.write_data_row")
    → "src.python.report.market_value_sheet.write_data_row"
@patch("src.python.report.market_value.write_subtotal_row")
    → "src.python.report.market_value_sheet.write_subtotal_row"
@patch("src.python.report.market_value.write_total_row")
    → "src.python.report.market_value_sheet.write_total_row"
@patch("src.python.report.market_value.write_header_row")
    → "src.python.report.market_value_sheet.write_header_row"
@patch("src.python.report.market_value.write_title_row")
    → "src.python.report.market_value_sheet.write_title_row"
@patch("src.python.report.market_value._apply_profit_colors")
    → "src.python.report.market_value_sheet._apply_profit_colors"
@patch("src.python.report.market_value._apply_price_type_colors")
    → "src.python.report.market_value_sheet._apply_price_type_colors"
@patch("src.python.report.market_value.freeze_header")
    → "src.python.report.market_value_sheet.freeze_header"
@patch("src.python.report.market_value.auto_width")
    → "src.python.report.market_value_sheet.auto_width"
@patch("src.python.report.market_value._generate_details")
    → "src.python.report.market_value_sheet._generate_details"
@patch("src.python.report.market_value._detail_to_row_values")
    → "src.python.report.market_value_sheet._detail_to_row_values"
@patch("src.python.report.market_value._num_formats")
    → "src.python.report.market_value_sheet._num_formats"
```

**批量替换技巧**：
```bash
# 在 test_market_value.py::TestWriteMarketValueSheet 范围内执行
# 将 market_value.xxx → market_value_sheet.xxx（注意不要替换模块级 import）
sed -i '/class TestWriteMarketValueSheet/,/^class /s/market_value\./market_value_sheet\./g' test_market_value.py
```

**循环 import**：`market_value.py` 末尾导入 `market_value_sheet` → `market_value_sheet` 导入 `DetailRow`（在 `market_value.py` 顶部 `dataclass` 定义）→ `market_value` 定义完成后再执行文件末尾桥接 → **单向无环 ✅**

| 其他 mock | `test_excel_generator.py` 中的 `market_value.write_market_value_sheet` → **暂不更新**（桥接保持）|
| 风险 | ★★★★☆ — 12 处 mock 路径 + 函数体搬迁 + 签名变更，需逐一确认 |
| 恢复 | 恢复桥接 + 恢复原函数 + 回滚 mock 路径 |

**I-6 后 `market_value.py` 内容**：
全部计算函数 + 6 条桥接行（I-4/I-5/I-6 的 `from ...sheet import ...`）+ **已无 `_generate_details` 跨导入需求**（`details=None` 回退已移除，但 `_generate_details` 仍在 `market_value.py` 中供其他模块导入）

**验收标准**：
- [ ] `test_market_value.py::TestWriteMarketValueSheet` 全部通过（12 处 mock 路径已更新 ✅）
- [ ] `test_excel_generator.py` 全部通过（桥接保持，mock 暂不更新 ✅）
- [ ] `test_scenario_holdings_quality.py` 场景测试通过（桥接保持 ✅）
- [ ] `write_market_value_sheet` 签名 `details` 已为必选参数
- [ ] `python -c "import src.python.report.market_value; import src.python.report.market_value_sheet"` ✅
- [ ] `regression` 门禁通过

---

### I-7：拆分 `_import_report_modules` try/except + 更新外部导入（BREAKING ❌ — 2 mock 路径变更）

**核心操作：消除 V2 中发现的混合 try/except 风险。**

| 项 | 内容 |
|:---|:------|
| 操作 1 | 拆分 `_import_report_modules` 中的 try/except（line 55-75）为两个独立块：<br>**块 A**（计算 — 从 `market_value` 导入）：`classify_holdings`, `get_last_trading_day`, `price_update_status`, `_generate_details`<br>**块 B**（写入 — 从 `market_value_sheet` 导入）：`write_market_value_sheet` |
| 操作 2 | 更新 `test_excel_generator.py` mock 路径（2 处）：<br>`"src.python.report.market_value.write_market_value_sheet"` → `"src.python.report.market_value_sheet.write_market_value_sheet"` |
| 操作 3 | 更新 `test_scenario_holdings_quality.py` line 382：`mv.write_market_value_sheet(...)` → `mvs.write_market_value_sheet(...)` |
| 操作 4 | 更新 `test_excel_generator.py` line 294 断言：`"market_value" in e.lower() or "行情市值" in e` → 新错误消息中 `"market_value_sheet"` 包含 `"market_value"` 子串，断言自然兼容，但**建议改为** `"market_value_sheet" in e.lower() or "行情市值" in e` 精确匹配 |
| 验证 | `grep -rn 'write_market_value_sheet' src/ --include='*.py'` 确认所有引用路径正确 |
| 风险 | ★★★☆☆ — mock 路径变更 + try/except 拆分 |
| 恢复 | 回滚 `excel_generator.py` + 回滚测试文件 |

**验收标准**：
- [ ] `_import_report_modules` 拆分为两个独立 try/except 块
- [ ] 块 A 错误消息：`"行情市值计算模块缺失 (market_value)"`
- [ ] 块 B 错误消息：`"行情市值写入模块缺失 (market_value_sheet)"`
- [ ] `test_excel_generator.py` 全部通过（mock 路径已更新 ✅）
- [ ] `test_scenario_holdings_quality.py` 全部通过
- [ ] `regression` 门禁通过

---

### I-8：清理 `market_value.py` 的 import + `__pycache__` + 测试重组

**移除了写入函数后，`market_value.py` 不再需要三组导入。**

| 项 | 内容 |
|:---|:------|
| 操作 1 | 删除 `openpyxl` 导入（`Font` + `Worksheet`，仅写入函数使用） |
| 操作 2 | 删除 `excel_writer` 导入（`auto_width`, `freeze_header`, `write_data_row`, `write_header_row`, `write_subtotal_row`, `write_title_row`, `write_total_row`，全部仅写入函数使用）|
| 操作 3 | 删除 `styles` 导入（`BLUE_FONT`, `FMT_MONEY`, `FMT_PERCENT`, `FMT_PRICE`, `FMT_SHARES`, `profit_font`，全部仅写入函数使用）|
| 操作 4 | `__pycache__` 清理：`find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null` |
| 操作 5 | **测试重组（强制）**：创建 `test_market_value_sheet.py`，将写入测试从 `test_market_value.py` 搬迁：<br>— `TestDetailToRowValues`<br>— `TestNumFormats`<br>— `TestApplyProfitColors`<br>— `TestApplyPriceTypeColors`<br>— `TestWriteMarketValueSheet`<br>搬迁后 `test_market_value.py` 保留计算函数测试，`test_market_value_sheet.py` 专注写入测试 |
| 验证 | `grep openpyxl\|excel_writer\|styles` in `market_value.py` → 0 |
| 风险 | ★★★☆☆ — 测试搬迁可能遗漏 marker |
| 恢复 | `git checkout src/python/report/market_value.py src/test/` |

**终态 `market_value.py` 导入行**（约 15 import，仅计算所需）：

```python
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.python import cache
from src.python.code_utils import (...)
from src.python.fetcher.price import fetch_market_data
from src.python.market_hours import is_market_open as _mh_is_market_open
from src.python.market_hours import is_midday_break as _mh_is_midday_break
from src.python.models import Holding
from src.python.provider_registry import FetchStrategy, get_registry
from src.python.registry import get_report_sheet_name
# 注意：不再有 openpyxl / excel_writer / styles
```

**验收标准**：
- [ ] `market_value.py` 无 `openpyxl` / `excel_writer` / `styles` 导入
- [ ] `test_market_value_sheet.py` 创建成功，写入测试已搬迁
- [ ] 搬迁的测试类均有 `pytestmark` 和正确 marker（`@pytest.mark.unit_report`）
- [ ] `test_market_value.py` 无写入测试残留
- [ ] `regression` 门禁通过

---

### I-9：文档同步（强制）

| 项 | 内容 |
|:---|:------|
| 同步文件 | `datasource-and-folders.md` — 目录树加 `market_value_sheet.py` + 更新 `market_value.py` 描述 |
| | `technical.md` — **必须**更新模块依赖关系图（`excel_generator` 从 `market_value_sheet` 导入写入函数 + `market_value.py` 角色更新）+ `report/` 目录列表 + `market_value.py` 的 market_hours 消费方描述（line 907）|
| | `review-findings.md` — R-197 标记 ✅，摘要保留 |
| | `changelog.md` — 记录全部变更（含 `_resolve_market_data` 改造、三组 import 清理、测试重组）|
| 风险 | ★☆☆☆☆ |

**验收标准**：
- [ ] `datasource-and-folders.md` 目录树包含 `market_value_sheet.py`，`market_value.py` 描述改为"市值核算计算引擎"
- [ ] `technical.md` 模块依赖关系图已更新（**强制**）
- [ ] `technical.md` 中 market_hours 消费方描述引用行号已更新（如适用）
- [ ] `review-findings.md` R-197 已标记 ✅
- [ ] `changelog.md` 已完成记录

---

### I-10：全量回归验证

| 项 | 内容 |
|:---|:------|
| 操作 | `python scripts/test_runner.py --mode regression`（P0 门禁）<br>`python scripts/test_runner.py --mode verify`（P1 门禁）<br>`python scripts/test_runner.py --mode edge`<br>`python scripts/test_runner.py --mode data` |
| 验证要点 | 14 处 mock 路径全部正确、`_import_report_modules` 拆分后 ImportError 处理正确、无 `ImportError`、无模块未找到 |
| 风险 | ★★☆☆☆ |
| 恢复 | 按步回退 |

**验收标准**：
- [ ] `regression`（269 项）全部通过
- [ ] `verify`（1049 项）全部通过
- [ ] `edge`（316 项）全部通过
- [ ] `data`（69 项）全部通过
- [ ] 未引入新 warning

---

## 6. 端状态依赖关系图

```
# 计算路径（market_value.py）
excel_generator.py ──→ market_value.py
    ├── classify_holdings()
    ├── get_last_trading_day()
    ├── price_update_status()
    └── _generate_details()          # 新增注册（用于 _resolve_market_data 预计算）

html_renderers.py ──→ market_value.py
    ├── DetailRow
    ├── _generate_details()
    ├── classify_holdings()
    ├── get_last_trading_day()
    └── price_update_status()

handlers_report.py ──→ market_value.py
    ├── _generate_details()
    └── classify_holdings()

# 写入路径（market_value_sheet.py 新增 — 仅有类型依赖）
excel_generator.py ──→ market_value_sheet.py
    └── write_market_value_sheet()

market_value_sheet.py ──→ market_value.py
    └── DetailRow (类型仅——通过 from __future__ import annotations 运行时零开销)

# HTML 路径（不受影响 ✅）
html_writer.py ──→ market_value.py
    └── get_last_trading_day()

summary.py ──→ market_value.py
    └── get_last_trading_day()

category.py ──→ market_value.py
    └── DetailRow

fund_performance.py ──→ market_value.py
    └── DetailRow

penetration.py/penetration_sheet.py ──→ market_value.py
    └── DetailRow
```

**循环 import 分析（终态）**：

```
market_value.py 加载:
  1. 定义 DetailRow (dataclass)
  2. 定义 _compute_premium, classify_holdings, ... 
  3. 定义 _generate_details（最后定义的计算函数）
  4. 无桥接导入（已清理）
  → 加载完成 ✅

market_value_sheet.py 加载:
  1. from __future__ import annotations
  2. from src.python.report.market_value import DetailRow
     → Python 已加载 market_value.py（模块完全就绪）→ 成功 ✅
  → 加载完成 ✅
```

**零环 ✅**

---

## 7. Mock 路径变更全集（V3 修正版）

> 总变更数：**14 处**（V2 误算为 15 处，实际为 12 + 2 = 14）。

| 函数组 | 迭代步 | Mock 路径变更 | 影响文件 | 变更数 |
|:-------|:------:|:--------------|:--------|:------:|
| `_write_account_groupings` + `write_market_value_sheet` | **I-6** (合并步) | `market_value.*` → `market_value_sheet.*`（12 条 `@patch` 装饰器）| `test_market_value.py` | 12 |
| `write_market_value_sheet`（外部） | **I-7** | `market_value.write_market_value_sheet` → `market_value_sheet.write_market_value_sheet` | `test_excel_generator.py` | 2 |
| **合计** | | | **2 个测试文件** | **14** |

**不需要变更的 mock 路径**（这些函数留在 `market_value.py` 中，mock 继续工作）：

| Mock 路径 | 函数 | 受影响测试文件数 |
|:----------|:-----|:---------------:|
| `market_value.get_last_trading_day` | `get_last_trading_day` | 15+ |
| `market_value.is_market_open` | `is_market_open` | 5+ |
| `market_value.is_midday_break` | `is_midday_break` | 2+ |
| `market_value._compute_detail_row` | `_compute_detail_row` | 20+ |
| `market_value._get_trading_calendar` | `_get_trading_calendar` | 5+ |
| `market_value._is_trading_day` | `_is_trading_day` | 3+ |
| `market_value.get_prev_trading_day` | `get_prev_trading_day` | 5+ |
| `market_value._count_trading_days_back` | `_count_trading_days_back` | 2+ |
| `market_value._determine_price_type` | `_determine_price_type` | 3+ |
| `market_value.price_update_status` | `price_update_status` | 5+ |
| `market_value.classify_holdings` | `classify_holdings` | 3+ |
| `market_value.datetime` | `datetime`（mock） | 10+ |
| `market_value.cache.*` | `cache.get/set/get_ttl` | 2+ |
| `market_value._FUND_PREMIUM_PLACEHOLDER` | 常量 | 2+ |

### 批量替换操作指南

```bash
# I-6 执行时，在 test_market_value.py 的 TestWriteMarketValueSheet 范围内替换：
# 定位范围：line 1320 ~ line 1510（或 class 起止行）
sed -i '/class TestWriteMarketValueSheet/,/^class /s/\.market_value\./.market_value_sheet./g' test_market_value.py

# 验证替换结果：
grep -n 'market_value\.\(write_\|_apply_\|freeze_\|auto_\|_generate_\|_detail_\|_num_\)' test_market_value.py
# 期望输出：零匹配

grep -n 'market_value_sheet\.\(write_\|_apply_\|freeze_\|auto_\|_generate_\|_detail_\|_num_\)' test_market_value.py
# 期望输出：12 匹配
```

---

## 8. 累积度量总表（V3）

| 迭代 | `market_value.py` | 文件变更 | 测试改动 | Mock 变更 | 门禁 | 累计风险 |
|:----:|:-----------------:|:---------|:--------:|:---------:|:----:|:--------:|
| I-1 | 711 行（不变） | — | 0 | 0 | 无 | ★☆☆☆☆ |
| I-2 | 711 行（不变） | test 文件 +~30 行 | +30 行测试 | 0 | regression | ★★☆☆☆ |
| I-3 | 711 行（+桥接） | +`market_value_sheet.py` ~10 行 + `excel_generator.py` ~20 行 | 0 | 0 | regression | ★★☆☆☆ |
| I-4 | ~680 行（-2 函数） | sheet ~+50 行 | 0 | 0 | regression | ★★☆☆☆ |
| I-5 | ~650 行（-2 函数） | sheet ~+90 行 | 0 | 0 | regression | ★★☆☆☆ |
| **I-6** | **~490 行（-2 函数）** | **sheet ~+220 行** | **~30 行** | **12 处**❗ | regression | **★★★★☆** |
| I-7 | ~490 行（不变） | excel_generator + 2 测试 | ~10 行 | 2 处❗ | regression | ★★★☆☆ |
| I-8 | **~450 行（-~40 行 import）** | +`test_market_value_sheet.py` | 搬迁 ~200 行测试 | 0 | regression | ★★★☆☆ |
| I-9 | 不变 | 4 份文档 | 0 | 0 | 无 | ★☆☆☆☆ |
| I-10 | 不变 | — | 0 | 0 | **verify** | ★★☆☆☆ |
| **终态** | **~450 行** | **+2 文件**（sheet + test_sheet） | **+30/-0 行 + 搬迁 ~200 行** | **14 处** | — | — |

> 对比 V2：终态 `market_value.py` 从 ~475 行降至 **~450 行**（多清理 excel_writer+styles 两组 import），迭代从 11 步降至 **10 步**，新增 `test_market_value_sheet.py` 一个测试文件。

---

## 9. FMEA 汇总（V3）

| 迭代 | 失败场景 | 根因 | 检测 | 严重 | 概率 | 恢复 |
|:----:|:---------|:-----|:-----|:----:|:----:|:-----|
| I-2 | 新增测试暴露了现有 bug | 现有代码潜藏分支条件缺失 | 测试失败 | 中 | 低 | 修复 bug |
| I-3 | `_resolve_market_data` 改造后预计算 details 与 `write_market_value_sheet` 内部分歧 | 算法不一致 | regression 验证 | 高 | 低 | 调式 |
| I-6 | **12 处 mock 路径遗漏 1 处未更新** | 手动更新遗漏 | regression 失败 | **高** | **中** | `git checkout` 该步 |
| I-6 | **`_generate_details` 路径在 `market_value_sheet` 命名空间未定义** | `write_market_value_sheet` 搬迁后调用 `_generate_details()` 但 sheet 未导入 | `AttributeError` | **高** | **低** | `market_value_sheet` 补导入 `_generate_details`（注意此步已移除 details=None 回退 → 不应触发此路径） |
| I-7 | `_import_report_modules` 拆分后 ImportError 处理不一致 | try/except 拆分错误 | regression | 中 | 低 | 调整异常处理 |
| I-7 | **`test_excel_generator.py` line 294 `"market_value" in e.lower()` 断言** | 错误消息变为 `"market_value_sheet"`，子串匹配仍生效但脆性 | 不失败（子串匹配） | 低 | 低 | 建议主动更新为精确匹配 |
| I-8 | 测试搬迁遗漏 `pytestmark` | 新文件缺 marker | pytest 收集期警告 | 中 | 中 | 补标 |
| I-8 | 测试搬迁后 `test_market_value.py` 残余写入测试 | 搬迁遗漏 | regression 重复计数 | 低 | 中 | 确认删除 |
| I-9 | `technical.md` 关系图和 market_hours 行号更新遗漏 | 遗忘 | 文档不一致 | 低 | 低 | 后续补更 |

---

## 10. 滚回策略

### 提交约定

每个迭代 1 个原子 commit，message 前缀 `R-197 I-N:`：

```
R-197 I-1: 函数清单 + 调用者映射
R-197 I-2: 测试覆盖加固
R-197 I-3: 创建 market_value_sheet.py + _resolve_market_data 预计算改造
R-197 I-4: 搬迁 _detail_to_row_values + _num_formats
R-197 I-5: 搬迁 _apply_profit_colors + _apply_price_type_colors
R-197 I-6: 搬迁 _write_account_groupings + write_market_value_sheet (12 mock)
R-197 I-7: 拆分 _import_report_modules try/except + 外部导入更新 (2 mock)
R-197 I-8: 清理 market_value.py imports + 测试重组
R-197 I-9: 文档同步
R-197 I-10: 全量回归验证
```

### 回滚操作

| 场景 | 操作 | 耗时 |
|:-----|:-----|:----:|
| 某一步 regression 失败 | `git checkout .` 放弃该步所有变更 | < 30s |
| 中间步骤发现上游问题 | `git revert <commit-hash>` — 按序回退 | < 1min |
| 全部拆分完成后发现回归 | `git revert HEAD~10..HEAD` — 批量回退 10 个 commit | < 2min |
| 冲突处理 | `git revert --no-commit HEAD~10..HEAD` 逐确认 | < 3min |

### 注意事项

- 批量回退使用 `git revert HEAD~N..HEAD`（范围语法，非单 commit）
- `git revert` 产生新 commit，适合共享分支
- `git reset --soft HEAD~N` 保留工作区文件，`--hard` 丢弃全部

---

## 11. 已识别的技术债务

| # | 债务 | 模块 | 严重度 | 说明 |
|:-:|:-----|:-----|:------:|:-----|
| TD-1 | **测试去重：`test_market_value_edge.py` 与 `test_market_value.py` 6 类重复** | test/ | 🟢 | 前科债务，合计 6 个完整重复类 ~460 行。非 R-197 核心范围，待单独处理 |
| TD-2 | `test_market_value.py:TestIsQdii` 测试 `code_utils` 而非 `market_value` | test/ | 🟢 | 委派测试重复，增加脆性 |
| TD-3 | **`_generate_details` 违反 C4/C6：混合计算编排与数据转换，未使用 `session_cache`，未全程通过 Provider Chain** | `market_value.py` | 🟡 | 分拆后仍在计算模块。混合职责（注册表交互 + HTTP 编排 + 数据转换）。违反约束 **C4**（会话级复用）和 **C6**（Provider Chain 必经）。属下一轮重构主题 |
| TD-4 | `premium` 字段已升级为真实计算（v0.3.4），但测试中仍有大量"premium=--"占位符断言 | test/ | 🟢 | 测试速度与真实行为的不匹配 |
| TD-5 | **残留桥接清理（已消除 ✅）** | — | — | V3 采用方案 E 移除 `details=None` 回退后，`market_value.py` 终态零桥接。此 TD 已不复存在 |
| TD-6 | **`_generate_details` 跨模块私有调用**：`html_renderers.py` 和 `handlers_report.py` 跨模块调用私有函数 | 多个 | 🟢 | 架构边界模糊，本次不处理 |

---

## 附录 A：V2 → V3 关键优化

| 优化项 | V2 | V3 | 来源 |
|:-------|:---|:---|:------|
| 迭代数 | 11 步（I-1 ~ I-11） | **10 步（I-1 ~ I-10）** | 复盘 1 ROI + 复盘 5 替代方案 |
| `details=None` 回退 | 保留（penetration 模式） | **移除（B 系列对齐）** | 复盘 5 方案 D/E |
| `_resolve_market_data` | 不变 | **改造为预计算 details** | 复盘 5 |
| I-6+I-7 | 分离两步 | **合并为一步（12 mock）** | 复盘 1 + 复盘 3 |
| Mock 计数 | §4 图 I-7 改 12 处（应 9 处），§7 合计 15 处（应 14 处） | **修正：I-6 改 12 处，合计 14 处** | 复盘 4 一致性审查 |
| I-9 import 清理 | 仅 openpyxl（~15 行） | **openpyxl + excel_writer + styles（~40 行）** | 复盘 2 C1-C14 检查 |
| 终态行数 | ~475 行 | **~450 行** | 复盘 4 |
| TD-3 约束引用 | 无 | **增加 C4/C6 约束编号** | 复盘 2 C1-C14 检查 |
| 测试重组 I-11 | 可选、未排序 | **强制、在 I-8 执行** | 复盘 6 可维护性 |
| 批量替换指南 | 无 | **新增 `sed` 指令** | 复盘 3 实施风险 |
| 桥接残留 TD-5 | 6 条待清理 | **已消除 ✅** | 复盘 5 |
| 循环 import 风险 | 🟡 有（`_generate_details` 跨导入） | **✅ 零环** | 复盘 5 |
