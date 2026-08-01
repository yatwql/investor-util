# src/static/ — 前端静态资产

Chart.js 交互式图表的前端资产（引擎 + 自有 JS + 独立调试页）统一存放于此目录。
报告生成时由 `html_writer.py` 通过 `shutil.copy2` 复制到报告输出目录（与 HTML 同目录），
模板以**相对路径**引用，报告完全离线自包含（R21 纯本地 bundle 决策）。

## 文件清单

| 文件 | 职责 | 体积 |
|:-----|:-----|:----:|
| `chart.min.js` | **Chart.js v4 引擎**（UMD 构建，第三方库） | ~205KB |
| `chart-print.js` | 打印降级（§4.5）：beforeprint 快照 `<img>` / afterprint 恢复 | <5KB |
| `chart-config.js` | 全局配置：配色（CSS 变量驱动）/ 动画关闭（P2）/ DPR 限制（P4） | <5KB |
| `chart-init.js` | 6 张图表初始化（O1 异常隔离 + `typeof Chart` 守卫） | <10KB |
| `test-chart.html` | **独立调试页**（TD8）：6 图渲染/交互/降级场景验证（S2 升级验证载体） | <20KB |

## 版本记录

| 日期 | Chart.js 版本 | 说明 |
|:-----|:-------------|:-----|
| 2026-08-01 | v4.4.3 | 初始引入（plan-1 Iter 1）。来源：jsdelivr `chart.js@4.4.3/dist/chart.umd.min.js` |

## 升级 Chart.js

1. 从官方/镜像下载新版 `chart.umd.min.js`，替换本文件（重命名为 `chart.min.js`）
2. **无需 SRI**（R21）：本地文件来自自身可信下载源，`file://` 下部分浏览器不校验 integrity
3. 升级后在 **`test-chart.html`** 验证 6 图渲染 + 交互 + 4 场景（正常/降级/空数据/离线）——打开调试页即可自检，替代完整报告生成
4. 通过后补做 Iter 7 全链路手动验证（真实报告打印 + 微信/离线场景）
5. 更新本文件「版本记录」表

## 安全

- 引擎从官方/镜像下载**一次**后入库 git 跟踪，无外部域名加载（R10 已闭环）
- 如需额外防护，可对本文件计算 SHA-256 记录于此
