# 变更日志归档 — v0.1.x

> 从 `docs-stm/managements/changelog.md` 迁移的早期版本记录。
> 当前活跃变更日志见 [changelog.md](../managements/changelog.md)。

---

## [0.1.0] - 2026-06-26

### Added
- 项目初始化，创建目录骨架
- 需求文档 `docs-stm/managements/requirements.md`
- 实现计划 `docs-stm/managements/plan.md`
- 质量标准与测试计划 `docs-stm/managements/testplan.md`
- 自我审查问题记录 `docs-stm/managements/review-findings.md`
- 本变更日志 `docs-stm/managements/changelog.md`
- 管理文档统一移至 `docs-stm/managements/` 目录
- 软件使用说明 `docs-stm/README.md`
- 代码配置文件 `CLAUDE.md`
- 示例持仓数据 `data/holdings/个人投资持仓信息.xlsx`

### Iter 1.1 — 项目骨架 + 配置管理 ✅ 已完成
- Python 包标记 `src/__init__.py`
- 配置管理模块 `src/config.py`（读写 `data/cache/config.json`，JSON 损坏容错）
- 日志模块 `src/logger.py`（控制台 + 文件双输出，防重复 handler）
- 依赖清单 `requirements.txt`（openpyxl, httpx）
- Windows 启动脚本 `scripts/launch.ps1`（自动 venv + pip install + 目录创建）
- Linux 启动脚本 `scripts/launch.sh`（同上）

### Iter 1.2 — 持仓读取 + TUI 菜单 ✅ 已完成
- 持仓数据结构 `src/models.py`（Holding dataclass）
- xlsx 解析器 `src/reader.py`（多工作表、表头校验、空行跳过）
- TUI 主菜单 `src/main.py`（6 选项 input() 循环，文件选择，配置管理）
- 键盘输入模块 `src/tui.py`（跨平台 msvcrt/termios 封装）
- 主菜单增强：方向键 ↑↓ 导航 + Enter 确认 + 默认选中第一项 + Ctrl+C 退出
- 修复 Windows 终端 GBK 编码兼容性问题（emoji/¥ → ASCII 替代）
- 修复 `scripts/launch.ps1` 路径问题（`Set-Location $projectRoot`）

### Bug Fixes (代码审查后修复)
- **reader.py**: try/finally 保护 workbook 资源释放；try/except 捕获 xlsx 损坏异常；精确行号追踪错误位置；份额/成本缺失时警告并跳过行；修复 `cell.value or ""` 吞掉数值 0 的问题
- **tui.py**: Linux 上 Ctrl+C 正确返回 KEY_CTRL_C；ESC 序列读取增加 150ms 超时（防单按 ESC 阻塞）；Windows 兼容 `\x00` 扩展键前缀
- **main.py**: 全部 `input()` 调用增加 EOFError 保护；入口处 `os.chdir(_project_root)` 保障相对路径；`_config_cache` 减少重复文件 I/O；顶层 KeyboardInterrupt 兜底退出

### Iter 1.3 — 数据源接入 + 缓存管理 ✅ 已完成
- 泛用 JSON 缓存模块 `src/cache.py`（get/set/clear，按秒过期，7 个缓存文件频率常量）
- 腾讯财经 API 封装 `src/providers/tencent.py`（`qt.gtimg.cn`，自动加 sh/sz 前缀，~ 分隔符解析）
- 东方财富 API 封装 `src/providers/eastmoney.py`（`api.fund.eastmoney.com` 获取净值，天天基金 fundf10 备用链路）
- 数据获取路由 `src/fetcher.py`（代码前缀自动识别股票/基金，先读缓存再调 API，缓存失败静默降级）
- API 联调验证：股票(600900=26.65)、ETF(159222=1.132)、场外基金(011506=2.1717)、QDII(017730=4.9361)、债券(012325=1.1351)

### Iter 1.4 — 汇总 + 市值核算 + Excel 输出 ✅ 已完成
- 样式常量 `src/report/styles.py`（正数红色/负数绿色字体，表头/小计/总计填充色，数字格式）
- Excel 输出引擎 `src/report/excel_writer.py`（标题行/表头行/数据行/小计/总计，列宽自适应，冻结首行，双路径保存最新+存档）
- 汇总模块 `src/report/summary.py`（统计时间、总市值/成本/盈亏/收益率/本日盈亏）
- 市值核算模块 `src/report/market_value.py`（15 列明细表，分账户小计+总计，盈亏红绿着色）
- 修正 `tencent.py` `_add_prefix` 缺失 5xxxxx ETF 前缀（561910/518880 等 ETF 正确取价）
- 重构 `fetcher.py`：先尝试腾讯财经（所有代码）→ 失败回退东方财富净值（消除前缀猜测依赖）
- `main.py` E 选项接入真实 Excel 生成（读持仓 → 取行情 → 写市值核算 → 写汇总 → 保存 reports/）
- 首次生成验证：15 条持仓，2 个页签，总市值 51.8 万，总盈亏 +24.5 万

### 配置更新
- 配置文件路径从 `data/cache/config.json` 迁移至 `data/config/config.json`
- 启动脚本（launch.ps1 / launch.sh）增加 `data/config/` 目录创建
- README 同步更新配置路径说明
