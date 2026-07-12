# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [Unreleased]

### Fixed

- **分红 API akshare 1.18.64 签名兼容**：`stock_history_dividend()` 新版不接受参数且返回全量聚合数据（列名从"每股股利"改为"年均股息"），改为一次拉取全量后按代码过滤，移除旧版逐股并发请求逻辑。
- **Tencent API 超时/网络错误自动重试**：`fetch_price()` 对 `TimeoutException`/`RequestError` 自动重试一次后再放弃，降低备用链路的偶发超时影响。
- **日志噪音压缩**：移除 `fetcher/chain.py` 和 `report/market_value.py` 中与 `cache.py` 重复的"缓存命中"DEBUG 日志。
- **TUI 主循环标题丢失**：`_print_header()` 从主循环前移至循环内调用，确保生成报告/刷新缓存等操作返回后，软件名称和版本号仍然显示在屏幕顶部。
- **测试文档 `--lf` 错误示例**：`how-to-test-my-code.md` 中原示例 `test_runner.py -- --lf` 实际因 argparse 不支持 `--` 透传而报错。改为直接调 `pytest -m` 复现标记表达式后组合 `--lf`，并补充 `test_runner.py` 与 `--lf` 的分工说明。

### Changed

- **缓存引擎 Strangler Fig 重构完成**：667 行的单体 `cache.py` 拆分为 `cache/` 子包（9 个文件 + services 子包），职责解耦为路径/IO/存取/TTL/统计/清理/组管理/持仓跟踪。过渡文件 `_legacy.py` 已删除。对外 API 保持完全兼容，`from cache import get/set/clear` 等不变。
- **T4 stale_days 配置收紧：14→7 天**：盈利预测/分红/风格等补充数据级不再容忍 2 周旧缓存。`config.json`、`data_status.py` 默认值、`how-to-config.md`、`requirements.md` 同步更新。

> **v0.3.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.3.x.md](../archive/archived_changelog.0.3.x.md)。
> 涵盖 v0.3.0 ~ v0.3.8（2026-07-08 ~ 2026-07-12）共 6 个版本。
>
> **v0.2.x 版本变更记录已归档**：详见 [docs-stm/archive/archived_changelog.0.2.x.md](../archive/archived_changelog.0.2.x.md)。
> 涵盖 v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）共 47 个版本。
>
> **v0.1.x 早期版本记录已归档**：详见 [docs-stm/archive/archived_changelog.0.1.x.md](../archive/archived_changelog.0.1.x.md)。
