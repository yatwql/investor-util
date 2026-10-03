# akshare 集成：profit_forecast + sector_fund_flow

## Context

用户要求将两个 akshare API 集成到投资分析工具中：
1. **`stock_profit_forecast_em()`** — 机构盈利预测（全量 ~2764 只股票，含 2025~2028 预测 EPS、研报数、机构评级）
2. **`stock_sector_fund_flow_rank()`** — 行业资金流向排名（含主力净流入、涨跌幅）

集成位置：
- Profit Forecast → 模块 4（穿透TOP10 新增"预测EPS"列）+ 模块 5（基金业绩新增"机构关注"列）
- Sector Flow → 模块 7（全球政经局势 LLM Prompt 注入行业资金流向数据）

## 变更清单

### 1. 新增 `src/providers/akshare_extras.py`

遵循 `akshare_news.py` 模式，两个函数各自独立：

**`get_profit_forecast() -> dict[str, dict]`**
- 调用 `ak.stock_profit_forecast_em()` 全量获取
- 转为 `{code: {name, reports, eps_2025e, eps_2026e, buy_rating, ...}}`
- 自管理文件缓存 `profit_forecast_all` 24h TTL
- 降级：异常/空 → 返回 `{}`

**`get_sector_fund_flow() -> list[dict]`**
- 调用 `ak.stock_sector_fund_flow_rank(indicator='今日', sector_type='行业资金流')`
- 提取 `[{name, change_pct, main_net_inflow}, ...]` 前 10 条
- 用 ThreadPoolExecutor + timeout 防挂起
- 自管理文件缓存 `sector_flow` 15min TTL
- 降级：异常/空 → 返回 `[]`

### 2. 修改 `src/cache.py`

- `_CACHE_TTL_DEFAULTS` 添加 `"profit_forecast": CACHE_DAILY, "sector_flow": 900`
- `prefix_type_map` 添加对应映射

### 3. 修改 `src/config.py`

- `_DEFAULT_CONFIG["cache_ttl"]` 添加 `profit_forecast` / `sector_flow`

### 4. 修改 `src/report/penetration.py`（模块 4）

- `_NCOLS`: 8 → 9
- `_HEADERS`: 新增 `"预测EPS(2025E)"`
- `write_penetration_sheet()` 开头：调用 `get_profit_forecast()` 
- 渲染循环：对每项 top10 的 codes 遍历，找匹配代码 → 查 EPS → 格式 `"¥XX.XX"`；无匹配 → `"--"`
- 降级：若返回 `{}`，全列显示 `"--"`
- `_num_formats()`: 对应列格式 `""`

### 5. 修改 `src/report/fund_performance.py`（模块 5）

- `_NCOLS`: 11 → 12  
- `_HEADERS`: 新增 `"机构覆盖"`
- `write_fund_performance_sheet()` 开头：调用 `get_profit_forecast()`
- 渲染循环：用基金 code 查 forecast dict → 有匹配则 `"研报N家 EPS¥XX.XX"`；无则 `"--"`
- `_write_empty_row()`: 追加 `"--"` 占位列

### 6. 修改 `src/llm_client.py`（模块 7）

**`_build_macro_prompt()`**:
- 新增参数 `sector_flow: list[dict] | None = None`
- 有数据时在 prompt 追加 `【行业资金流向】` 区块（前 5 个行业主力净流入）

**`generate_global_macro()`**:
- 新增参数 `sector_flow`
- 加入缓存指纹（`_compute_fingerprint` 增加 sector_flow）
- 传递给 `_build_macro_prompt()`

**`generate_all_llm()`**:
- 新增参数 `sector_flow`
- `_run_macro()` 内传递给 `generate_global_macro()`

### 7. 修改 `src/report/html_writer.py`

- LLM 生成分支（~line 322）：调用 `get_sector_fund_flow()`，传入 `generate_all_llm()`

### 8. 修改 `src/tui_handlers.py`

- `_cmd_generate_full()`（菜单 L）：调用 `get_sector_fund_flow()`，传入 LLM 生成路径

### 9. 测试

- **`src/test_akshare_extras.py`**（新）：mock DataFrame，测试成功/空/异常三种场景 × 2 个函数
- **`src/test_penetration.py`**：追加新列存在性断言  
- **`src/test_fund_performance.py`**：追加新列存在性断言
- **`test_llm_client.py::TestBuildMacroPrompt`**：新增 `test_with_sector_flow`

## 验证

```bash
pytest src/  # 全量通过
```
