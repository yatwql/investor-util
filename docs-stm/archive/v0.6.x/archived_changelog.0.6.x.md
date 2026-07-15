# 变更日志归档 — v0.6.x

> 归档时间：2026-07-15
> 原始文件：docs-stm/managements/changelog.md
> 涵盖版本：v0.6.0（2026-07-15）共 1 个版本

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.6.0] - 2026-07-15

### Fixed

- **管理文档清理**：补齐版本头（llm-technical.md、review-findings.md、test-coverage.md、folders.md），plan.md 移除字母跳跃历史注释，review-findings.md P3 重新连续编号（P3-2~P3-9→P3-1~P3-5），changelog.md 去重
- **faq.md 行号偏差**：`logger.py` 控制台级别修改行号 48→82（实际代码行）
- **how-to-test-my-code.md 历史注脚**：移除"基于 v0.5.7 版本撰写"过时说明

### Docs

- **文档版本号统一升至 v0.6.0**：constants.py、pyproject.toml、README.md、7 份管理文档、how-to-test-my-code.md
