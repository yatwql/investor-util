"""分阶段测试汇总页（`test-reports/latest/index.html`）渲染。"""

from __future__ import annotations

import os

from _test_runner.paths import _LATEST_DIR, _REPORTS_DIR
from _test_runner.modes import MODES
from src.python.core.constants import APP_NAME  # noqa: E402
from datetime import datetime


def _overall_status(results: list[dict]) -> tuple[str, str]:
    """判断总体状态。"""
    all_ok = all(r.get("exit_code", 0) == 0 for r in results)
    if all_ok:
        return "PASS", "全部通过"
    ok_count = sum(1 for r in results if r.get("exit_code", 0) == 0)
    return "PARTIAL", f"{ok_count}/{len(results)} 模式通过"


def _report_links_html(mode: str) -> str:
    """汇总页「报告」列链接：分阶段模式的逐阶段报告全部列出（不再只剩最后跑的那一阶段）。"""
    mode_dir = os.path.join(_LATEST_DIR, mode)
    links: list[str] = []
    if os.path.isfile(os.path.join(mode_dir, "report.html")):
        links.append(f'<a href="{mode}/report.html">📄 查看</a>')
    if os.path.isdir(mode_dir):
        for name in sorted(os.listdir(mode_dir)):
            if name.startswith("report_phase_") and name.endswith(".html"):
                tag = name[len("report_phase_") : -len(".html")]
                links.append(f'<a href="{mode}/{name}">📄 Phase {tag}</a>')
    return " ".join(links) if links else '<span class="dim">无</span>'


def _render_index_html(results: list[dict], coverage: bool, archive_path: str | None) -> str:
    """生成汇总页 HTML。"""
    total_passed = sum(r.get("passed", 0) for r in results)
    total_failed = sum(r.get("failed", 0) for r in results)
    total_skipped = sum(r.get("skipped", 0) for r in results)
    total_errors = sum(r.get("errors", 0) for r in results)
    total_duration = sum(r.get("duration", 0) for r in results)
    overall, status_desc = _overall_status(results)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 各行
    rows_html = ""
    mode_order = {k: v["order"] for k, v in MODES.items()}
    for r in sorted(results, key=lambda x: mode_order.get(x.get("mode", ""), 99)):
        mode = r.get("mode", "")
        ec = r.get("exit_code", -1)
        if ec == 0:
            badge = '<span class="badge badge-pass">PASS</span>'
        elif ec == -1:
            badge = '<span class="badge badge-timeout">超时</span>'
        else:
            badge = f'<span class="badge badge-fail">FAIL ({ec})</span>'

        report_link = _report_links_html(mode)

        rows_html += f"""\
    <tr>
      <td><strong>{mode}</strong></td>
      <td>{r.get("desc", "")}</td>
      <td>{badge}</td>
      <td class="num">{r.get("passed", 0)}</td>
      <td class="num">{r.get("failed", 0)}</td>
      <td class="num">{r.get("skipped", 0)}</td>
      <td class="num">{r.get("errors", 0)}</td>
      <td class="num">{r.get("duration", 0):.1f}s</td>
      <td>{report_link}</td>
    </tr>"""

    overall_badge = f'<span class="badge badge-{overall.lower()}">{overall}</span>'

    # 存档备注
    archive_note = ""
    if archive_path:
        rel_archive = os.path.relpath(archive_path, _REPORTS_DIR)
        archive_note = f'<div class="note archive-note">📦 历史报告已归档: <code>{rel_archive}/</code></div>'

    # 覆盖率备注
    cov_note = ""
    if coverage:
        cov_index = os.path.join(_LATEST_DIR, "coverage", "index.html")
        if os.path.isfile(cov_index):
            cov_note = '<div class="note cov-note">📊 <a href="coverage/index.html">查看行覆盖率报告</a></div>'

    html = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>测试报告汇总 — {now_str}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Microsoft YaHei', 'PingFang SC', sans-serif; margin: 0; padding: 24px; background: #f0f2f5; color: #1a1a2e; }}
  h1 {{ font-size: 1.4em; margin: 0 0 4px; }}
  .meta {{ color: #666; font-size: 0.88em; margin-bottom: 20px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; font-size: 0.92em; }}
  th {{ background: #f7f8fa; font-weight: 600; color: #444; }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 0.82em; font-weight: 600; }}
  .badge-pass {{ background: #d4edda; color: #155724; }}
  .badge-fail {{ background: #f8d7da; color: #721c24; }}
  .badge-partial {{ background: #fff3cd; color: #856404; }}
  .badge-timeout {{ background: #e2e3e5; color: #383d41; }}
  .summary {{ margin-top: 20px; padding: 16px 20px; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-top: 10px; }}
  .summary-item {{ text-align: center; padding: 8px; border-radius: 6px; background: #f8f9fa; }}
  .summary-item .num {{ font-size: 1.3em; font-weight: 700; display: block; }}
  .summary-item .lbl {{ font-size: 0.82em; color: #666; }}
  .note {{ margin-top: 12px; padding: 10px 16px; border-radius: 6px; font-size: 0.9em; }}
  .archive-note {{ background: #e8f4f8; color: #0c5460; }}
  .cov-note {{ background: #e8f4e8; color: #155724; }}
  .dim {{ color: #999; }}
  .footer {{ margin-top: 24px; color: #aaa; font-size: 0.82em; text-align: center; }}
  a {{ color: #0066cc; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>🧪 测试报告汇总</h1>
<p class="meta">生成时间: {now_str} &nbsp;|&nbsp; 总体: {overall_badge} &nbsp;|&nbsp; {status_desc}</p>

<table>
  <thead>
    <tr>
      <th>模式</th>
      <th>说明</th>
      <th>状态</th>
      <th class="num">通过</th>
      <th class="num">失败</th>
      <th class="num">跳过</th>
      <th class="num">错误</th>
      <th class="num">耗时</th>
      <th>报告</th>
    </tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>

<div class="summary">
  <strong>📋 总计</strong>
  <div class="summary-grid">
    <div class="summary-item"><span class="num" style="color:#155724;">{total_passed}</span><span class="lbl">通过</span></div>
    <div class="summary-item"><span class="num" style="color:#721c24;">{total_failed}</span><span class="lbl">失败</span></div>
    <div class="summary-item"><span class="num" style="color:#856404;">{total_skipped}</span><span class="lbl">跳过</span></div>
    <div class="summary-item"><span class="num" style="color:#721c24;">{total_errors}</span><span class="lbl">错误</span></div>
    <div class="summary-item"><span class="num">{total_duration:.1f}s</span><span class="lbl">总耗时</span></div>
  </div>
</div>

{cov_note}
{archive_note}

<div class="footer">
  Generated by test-runner.py · {APP_NAME}
</div>
</body>
</html>"""
    return html
