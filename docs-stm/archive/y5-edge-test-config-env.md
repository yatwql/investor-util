# Y5 实施计划 — 配置/环境纵深（~10 项 edge 测试）

## Context

Y5 来自 plan.md § [P2-2] Y 迭代（Edge Case 纵深覆盖增补），是 Y 系列的五个子方向之一（Y1-Y6）。本计划实现 Y5 的 8 项配置/环境 edge 测试，覆盖 BOM 头 JSON、0 字节配置文件、CRLF vs LF、api_key 空格、代理冲突、缺失嵌套键、多实例并发、终端无颜色。

---

## 实施项

### 1. BOM 头 JSON（1~2 项）

**问题：** 所有 JSON 读取使用 `encoding="utf-8"`，Windows 编辑器保存的 UTF-8 BOM（`﻿`）会导致 `json.JSONDecodeError`。

**受影响位置：**
- `config.py:96` — `get_config()` 读取 config.json
- `config.py:615` — `get_llm_config()` 读取 llm_settings.json
- `config.py:644` — `get_llm_config()` 读取 llm_key.json
- `cache.py:105` — `_read_cache_data()`
- `handlers_config.py:27` — `_read_llm_settings()`

**修复方案：** 在所有 JSON 读取处将 `encoding="utf-8"` 改为 `encoding="utf-8-sig"`，使 Python 自动跳过 BOM（如果存在）。`utf-8-sig` 兼容无 BOM 的文件。

> ⚠ 但需注意：`cache.py` 的 `_read_cache_data()` 也处理 gzip 文件（`gzip.open(fpath, "rt", encoding="utf-8")` 第 112 行）。gzip 文件不应加 BOM。仅影响普通 JSON 读取路径。

**测试：** 在每个修改后的读取路径验证 BOM 文件能正常解析。

### 2. 0 字节配置文件（已有覆盖，补充 1 项）

**现状：** `get_config()` 和 `get_llm_config()` 已处理空文件（`json.JSONDecodeError` 返回默认值）。`test_config.py` 有 `test_empty_file_returns_defaults`。

**补充：** 确认 `llm_key.json` 空文件导致 `get_llm_config()` 返回 `None` 的行为（影响：LLM 功能降级为"未配置"）。

### 3. CRLF vs LF（无需修复，通过 Python 文本模式自动转换）

**现状：** Python 3 `open()` 文本模式自动转换 `\r\n` → `\n`。`_strip_json_comments()` 的 `\n` 检查安全。

**测试：** 1 项验证 CRLF 行尾的 `llm_settings.json` 能被正确解析（含注释剥离）。

### 4. API Key 空格（1 项修复 + 1 项测试）

**问题：** `llm/api.py:482` 从 `llm_config.get("api_key", "")` 获取的 api_key 未做 `.strip()`。如果 `llm_key.json` 中有 `"api_key": " sk-ant-xxx "`（含空格），所有 LLM API 调用会因认证失败。

**修复方案：** 在 `config.py` 的 `get_llm_config()` 中，读取 `api_key` 后做 `.strip()`，或统一在 `config.py:657` 处处理：

```python
api_key = (llm_key_config or {}).get("api_key", "")
if api_key:
    api_key = api_key.strip()
```

或者在 `config.py` 的 `validate_config()` 中增加校验逻辑。

**测试：** 验证带空格的 api_key 被正确 trim 后再用于 API 调用。

### 5. 代理冲突（不修复 — 仅测试，1 项）

**问题：** 无显式代理支持。`http_client.py` 的 `make_http_client()` 不接收 `proxies` 参数。`httpx` 靠 `trust_env=True`（默认）从环境变量 `HTTP_PROXY`/`HTTPS_PROXY` 读取。

**决定：** 本次迭代**不新增代理配置功能**（属于 feature 而非 edge 修复）。仅编写 1 项测试验证 `HTTP_PROXY` 环境变量被 `httpx.Client` 隐式尊重（mock 级别的行为验证），或验证代码在代理不可用时不会崩溃。

### 6. 缺失嵌套键（已有防护，补充 1 项）

**现状：** 所有配置读取都用 `.get()`，无 `KeyError` 风险。`tui_menu.py:108` 的 `llm_config["provider"]` 有前面的 `.get("provider")` 守卫。

**测试：** 验证 `llm_settings.json` 缺失 `pricing`、`system_prompt` 等嵌套键时，`get_llm_config()` 仍返回有效配置。

### 7. 多实例并发（已有测试，补充 1 项）

**现状：** `test_config_atomic_edge.py` 已有 `test_concurrent_set_config_thread_safe`（10 线程并发写入）。

**补充测试：** 验证 `config.json` 缺失时，双进程同时调用 `init_config()` 不崩溃（模拟首次运行 + 缓存预热并发）。

### 8. 终端无颜色（修复 + 1~2 项测试）

**问题：** `tui_menu.py` 和 `handlers_config.py` 使用 ANSI 转义码着色但无 TTY 检测。输出重定向到文件时产生乱码。

**修复方案：**
- 在 `tui_menu.py` 增加 `_supports_color()` 函数，检查 `NO_COLOR` 环境变量和 `sys.stdout.isatty()`
- 当不支持颜色时禁用 ANSI 转义码，或使用 `colorama.init(strip=not sys.stdout.isatty())`
- 或者使用 `colorama.Style`/`Fore` 替代手写 `\033[...`，利用 colorama 的自动 strip

**测试：** 验证 `stdout` 模拟为非 TTY 时，输出不含 `\033` 转义序列。

---

## 修改文件清单

### 生产代码
| 文件 | 修改内容 |
|------|----------|
| `src/python/config.py:96,615,644` | JSON 读取 `utf-8` → `utf-8-sig`（BOM 兼容） |
| `src/python/cache.py:105` | 普通 JSON 读取 `utf-8` → `utf-8-sig`（gzip 路径不变） |
| `src/python/handlers_config.py:27` | JSON 读取 `utf-8` → `utf-8-sig` |
| `src/python/config.py` | `get_llm_config()` 中 api_key 加 `.strip()` |
| `src/python/tui_menu.py` | 增加 TTY/NO_COLOR 检测，禁用非 TTY 输出 ANSI |

### 测试文件
| 文件 | 测试内容 |
|------|----------|
| `src/test/unit/config/test_config_atomic_edge.py` | 新增 Y5 测试类：BOM JSON、CRLF JSON、api_key 空格、缺失嵌套键、并发 init_config、TTY 颜色 |
| `src/test/unit/core/test_cache_edge.py` | 新增 BOM 缓存文件读取测试 |

---

## 验证

1. `pytest src/test/ -m "edge" -v` — 全部 edge 测试通过
2. `pytest src/test/unit/config/ -v` — config 测试全部通过
3. `python -m pytest src/test/ --collect-only -q | tail -3` — 总计数不减少
4. 手动验证：用含 BOM 的 `config.json` 启动程序，菜单正常显示
5. 手动验证：`python main.py > output.txt` 输出不含 ANSI 转义
