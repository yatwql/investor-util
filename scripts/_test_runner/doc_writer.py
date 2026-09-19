"""test-coverage.md 的机器环境表与模式计数表自动更新。"""

from __future__ import annotations

import os

from _test_runner.paths import _PROJECT_ROOT
from _test_runner.machine_info import _duration_mode_cells, _env_value, _format_approx_duration
from _checklib import extract_table_region as _extract_table_region, replace_table_region as _replace_table_region
from typing import Callable


_DOC_ENV_TABLE_MARKERS = ("<!-- env-table:start -->", "<!-- env-table:end -->")


_DOC_DURATION_TABLE_MARKERS = ("<!-- duration-table:start -->", "<!-- duration-table:end -->")


_DOC_MODE_COUNT_MARKERS = ("<!-- mode-count-table:start -->", "<!-- mode-count-table:end -->")


_DOC_COVERAGE_PATH = os.path.join(_PROJECT_ROOT, "docs-stm", "managements", "test-coverage.md")


def _find_machine_column(header_row: list[str], hostname: str) -> int | None:
    """在表头 token 网格中查找含 `{hostname}（` 的列序号（第 1 列为序号 1）。

    header_row 为按 `|` 拆分后的 token 列表（行首/行尾 token 为空串）。
    旧慢笔记本等非本机列因主机名不匹配而天然豁免。
    """
    marker = hostname + "（"
    for idx in range(1, len(header_row) - 1):
        if marker in header_row[idx].strip():
            return idx
    return None


def _new_separator_cell(last_sep: str) -> str:
    """由既有数据列分隔标记推断新增列对齐样式（居中 :---: 或左对齐 :---）。"""
    return ":---:" if last_sep.rstrip().endswith(":") else ":---"


def _update_machine_table(
    table_lines: list[str],
    header_cell: str,
    row_value: Callable[[str], str | None],
) -> list[str]:
    """更新或新增当前主机名列（其余单元格字节原样保留）。

    Args:
        table_lines: 两 marker 之间的表格行（含表头/分隔行/数据行）
        header_cell: 主机名列表头文本 `{hostname}（{date} 实测）`
        row_value: 数据行第一列 label → 该主机列值；返回 None 保留原值不更新

    Returns:
        更新后的表格行列表

    Raises:
        ValueError: 区域首行不是表格行
    """
    if not table_lines or not table_lines[0].lstrip().startswith("|"):
        raise ValueError("表区域首行不是 `|` 开头的表格行")
    grid = [line.split("|") for line in table_lines]

    hostname = header_cell.split("（", 1)[0]
    col = _find_machine_column(grid[0], hostname)
    new_col = col is None
    if new_col:
        col = len(grid[0]) - 1  # 行尾空 token 前插入新列

    if new_col:
        grid[0].insert(col, f" {header_cell} ")  # 新列：插入以保留行尾空 token
    else:
        grid[0][col] = f" {header_cell} "  # 更新（含日期刷新）

    if new_col and len(grid) >= 2:  # 分隔行：新增列补对齐标记
        grid[1].insert(col, _new_separator_cell(grid[1][-2]))

    for tokens in grid[2:]:  # 数据行：按行 label 取值
        label = tokens[1].strip()
        value = row_value(label)
        if new_col:
            tokens.insert(col, f" {value} " if value is not None else " ")
        elif value is not None:
            tokens[col] = f" {value} "  # 缺失（None）→ 保留原单元格

    return ["|".join(tokens) for tokens in grid]


def _update_mode_count_table(table_lines: list[str], results: list[dict]) -> list[str]:
    """更新「模式对应测试量」表：覆盖项数=实测执行数，典型耗时=实测耗时。

    未实测/超时模式保留原值；表结构与行集不做增删（模式增删走人工维护）。

    Args:
        table_lines: 两 marker 之间的表格行（含表头/分隔行/数据行）
        results: 各模式运行结果列表

    Returns:
        更新后的表格行列表

    Raises:
        ValueError: 区域首行不是表格行
    """
    if not table_lines or not table_lines[0].lstrip().startswith("|"):
        raise ValueError("表区域首行不是 `|` 开头的表格行")
    by_mode = {r.get("mode", ""): r for r in results if not r.get("timed_out")}
    grid = [line.split("|") for line in table_lines]
    for tokens in grid[2:]:  # 跳过表头与分隔行
        mode = tokens[1].strip().strip("`")
        res = by_mode.get(mode)
        if res is None:
            continue
        cnt = res.get("passed", 0) + res.get("failed", 0) + res.get("skipped", 0) + res.get("errors", 0)
        tokens[2] = f" **{cnt}** "
        tokens[3] = f" {_format_approx_duration(res.get('duration', 0.0) or 0.0)} "
    return ["|".join(tokens) for tokens in grid]


def _update_test_coverage_doc(doc_text: str, machine_info: dict, results: list[dict]) -> str:
    """更新 test-coverage.md「模式对应测试量」表 + 两张「环境耗时对照」表（纯函数，不落盘）。

    Args:
        doc_text: test-coverage.md 全文
        machine_info: _collect_machine_info 结果
        results: 各模式运行结果列表

    Returns:
        更新后的全文；marker 缺失/结构异常时抛 ValueError，绝不擅自改写

    Raises:
        ValueError: 表区域标记缺失或表格结构异常
    """
    hostname = machine_info.get("hostname") or "未知主机"
    date = machine_info.get("date") or ""
    header_cell = f"{hostname}（{date} 实测）"

    env_lines = _extract_table_region(doc_text, _DOC_ENV_TABLE_MARKERS)
    env_updated = _update_machine_table(env_lines, header_cell, lambda label: _env_value(label, machine_info))
    doc_text = _replace_table_region(doc_text, _DOC_ENV_TABLE_MARKERS, env_updated)

    duration_cells = _duration_mode_cells(results)
    dur_lines = _extract_table_region(doc_text, _DOC_DURATION_TABLE_MARKERS)
    dur_updated = _update_machine_table(
        dur_lines,
        header_cell,
        # 数据更新时间行按本机采集日期填充；其余行按模式实测耗时（未测留空）
        lambda label: date if label == "数据更新时间" else duration_cells.get(label.strip("`")),
    )
    doc_text = _replace_table_region(doc_text, _DOC_DURATION_TABLE_MARKERS, dur_updated)

    count_lines = _extract_table_region(doc_text, _DOC_MODE_COUNT_MARKERS)
    count_updated = _update_mode_count_table(count_lines, results)
    doc_text = _replace_table_region(doc_text, _DOC_MODE_COUNT_MARKERS, count_updated)

    return doc_text


def _display_path(path: str, start: str) -> str:
    """返回相对 start 的展示路径；Windows 跨盘符时 relpath 抛 ValueError，
    降级返回绝对路径，避免仅用于打印的路径换算崩溃（测试重定向文档路径到
    其他驱动器时会触发）。"""
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return os.path.abspath(path)


def _update_test_coverage_doc_file(machine_info: dict, results: list[dict]) -> None:
    """将本机环境与实测耗时写入 test-coverage.md（仅内容变化时落盘）。

    文档缺标记/结构异常时打印 [ERR] 并返回，绝不破坏既有文档。
    """
    if not os.path.exists(_DOC_COVERAGE_PATH):
        print(f"  [ERR] 未找到 {_DOC_COVERAGE_PATH}，无法更新环境耗时对照")
        return
    with open(_DOC_COVERAGE_PATH, encoding="utf-8") as f:
        original = f.read()
    try:
        updated = _update_test_coverage_doc(original, machine_info, results)
    except Exception as exc:  # 结构异常一律降级 [ERR]，绝不破坏既有文档
        print(f"  [ERR] 未更新环境耗时对照：{exc}")
        return
    if updated == original:
        print(f"  [..] {_display_path(_DOC_COVERAGE_PATH, _PROJECT_ROOT)} 内容未变化，跳过写入")
        return
    with open(_DOC_COVERAGE_PATH, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"  [OK] 已更新 {_display_path(_DOC_COVERAGE_PATH, _PROJECT_ROOT)}（模式对应测试量 + 环境耗时对照）")
