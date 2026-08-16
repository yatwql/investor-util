"""结构化日志读取单元测试 — 日志可视化（CLI/TUI/Web 三端共享核心层）。

覆盖 `core/log_reader.py`：
  - parse_log — 时间戳分条 / 多行续行归并 / 装饰性横幅标记 / 孤儿行丢弃 / 空文本
  - read_log — 级别阈值过滤 / 时间前缀过滤 / limit 截尾 / 无效级别 / 缺失文件
  - tail_log — 末 N 行 / 行数不足 / 空文件 / 缺失文件
  - default_log_path — 与 logger._LOG_FILE 一致

运行：
  python -m pytest src/test/unit/core/test_log_reader.py -v
"""

from __future__ import annotations

import os

import pytest

from src.python.core.log_reader import (
    LOG_LEVELS,
    LogEntry,
    default_log_path,
    parse_log,
    read_log,
    tail_log,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core]

# 与 core/logger.py::_LOG_FORMAT 一致的样例日志文本
_SAMPLE = """\
2026-08-16 10:00:00,123 [INFO] 应用启动
2026-08-16 10:00:01,456 [ERROR] 读取行情失败
  详细堆栈第一行
  详细堆栈第二行
2026-08-16 10:00:02,789 [WARNING] 数据源响应偏慢
"""

_BANNER = """\
2026-08-16 10:00:03,000 [ERROR] ================================================
2026-08-16 10:00:03,001 [ERROR]   ⚗ 实验性功能已开启！
2026-08-16 10:00:03,002 [ERROR] ================================================
"""


def _write_log(tmp_path, text: str, name: str = "app.log") -> str:
    """将样例文本写入临时日志文件，返回路径。"""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestParseLog:
    """parse_log 解析行为。"""

    def test_basic_records(self):
        """时间戳起始行解析为独立记录。"""
        entries = parse_log(_SAMPLE)
        assert len(entries) == 3
        assert entries[0].time == "2026-08-16 10:00:00,123"
        assert entries[0].level == "INFO"
        assert entries[0].message == "应用启动"
        assert entries[1].level == "ERROR"
        assert entries[2].level == "WARNING"

    def test_continuation_lines_merged(self):
        """多行 traceback 续行归并到上一条记录的 body。"""
        entries = parse_log(_SAMPLE)
        error_entry = entries[1]
        assert error_entry.body == "读取行情失败\n  详细堆栈第一行\n  详细堆栈第二行"
        # 首行消息不变
        assert error_entry.message == "读取行情失败"

    def test_decorative_banner_marked(self):
        """纯分隔线与 ⚗ 提示横幅标记为装饰性。"""
        entries = parse_log(_BANNER)
        assert len(entries) == 3
        assert all(e.is_decorative for e in entries)
        assert all(e.level == "ERROR" for e in entries)

    def test_orphan_head_lines_dropped(self):
        """首条记录前的孤儿行（tail 边界不完整记录头）丢弃。"""
        text = " 残留堆栈行（无时间戳头）\n" + _SAMPLE
        entries = parse_log(text)
        assert len(entries) == 3
        assert entries[0].message == "应用启动"

    def test_empty_text(self):
        """空文本返回空列表。"""
        assert parse_log("") == []

    def test_non_decorative_error_not_marked(self):
        """普通 ERROR 消息不标记为装饰性。"""
        entries = parse_log(_SAMPLE)
        assert entries[1].is_decorative is False

    def test_to_dict_roundtrip(self):
        """to_dict 输出可 JSON 序列化字段。"""
        entry = parse_log(_SAMPLE)[0]
        data = entry.to_dict()
        assert data == {
            "time": "2026-08-16 10:00:00,123",
            "level": "INFO",
            "message": "应用启动",
            "body": "应用启动",
            "is_decorative": False,
        }


class TestTailLog:
    """tail_log 尾部反向分块读取。"""

    def test_last_n_lines(self, tmp_path):
        """返回文件末尾 N 行。"""
        lines = [f"2026-08-16 10:00:0{i},000 [INFO] 第{i}条" for i in range(5)]
        path = _write_log(tmp_path, "\n".join(lines) + "\n")
        text = tail_log(path, limit=3)
        assert text.splitlines() == lines[-3:]

    def test_fewer_than_limit(self, tmp_path):
        """行数不足 limit 时返回全部行。"""
        lines = ["a", "b"]
        path = _write_log(tmp_path, "\n".join(lines) + "\n")
        assert tail_log(path, limit=5000).splitlines() == lines

    def test_empty_file(self, tmp_path):
        """空文件返回空字符串。"""
        path = _write_log(tmp_path, "")
        assert tail_log(path, limit=10) == ""

    def test_missing_file(self, tmp_path):
        """缺失文件返回空字符串。"""
        assert tail_log(str(tmp_path / "nope.log"), limit=10) == ""

    def test_utf8_multi_byte(self, tmp_path):
        """UTF-8 中文内容可完整读取。"""
        path = _write_log(tmp_path, "2026-08-16 10:00:00,000 [INFO] 中文消息\n")
        text = tail_log(path, limit=10)
        assert "中文消息" in text


class TestReadLog:
    """read_log 读取 + 过滤。"""

    def test_read_injected_path(self, tmp_path):
        """注入路径读取，返回按时间升序的条目。"""
        path = _write_log(tmp_path, _SAMPLE)
        entries = read_log(path=path)
        assert [e.level for e in entries] == ["INFO", "ERROR", "WARNING"]

    def test_level_threshold(self, tmp_path):
        """级别阈值过滤（ERROR 含 ERROR+CRITICAL）。"""
        path = _write_log(tmp_path, _SAMPLE)
        entries = read_log(path=path, level="ERROR")
        assert [e.level for e in entries] == ["ERROR"]
        entries = read_log(path=path, level="WARNING")
        assert [e.level for e in entries] == ["ERROR", "WARNING"]

    def test_level_threshold_decorative_excluded_by_level(self, tmp_path):
        """装饰性 ERROR 横幅仍受级别过滤约束。"""
        path = _write_log(tmp_path, _BANNER)
        # 默认全量读取时装饰性横幅计入条目
        assert len(read_log(path=path)) == 3
        # 级别过滤只看 levelname，不受 is_decorative 影响
        assert all(e.level == "ERROR" for e in read_log(path=path, level="ERROR"))

    def test_limit_truncates_tail(self, tmp_path):
        """limit 限制读取的物理行数（保留尾部）。"""
        lines = [f"2026-08-16 10:00:0{i},000 [INFO] 第{i}条" for i in range(10)]
        path = _write_log(tmp_path, "\n".join(lines) + "\n")
        entries = read_log(path=path, limit=3)
        assert len(entries) == 3
        assert entries[-1].message == "第9条"

    def test_since_until_filter(self, tmp_path):
        """时间前缀过滤（since 起点、until 终点含边界）。"""
        text = """\
2026-08-16 10:00:00,000 [INFO] 早
2026-08-16 12:00:00,000 [INFO] 午
2026-08-17 10:00:00,000 [INFO] 次日
"""
        path = _write_log(tmp_path, text)
        entries = read_log(path=path, since="2026-08-16 12")
        assert [e.message for e in entries] == ["午", "次日"]
        entries = read_log(path=path, until="2026-08-16")
        assert [e.message for e in entries] == ["早", "午"]

    def test_invalid_level_raises_value_error(self, tmp_path):
        """无效级别抛 ValueError。"""
        path = _write_log(tmp_path, _SAMPLE)
        with pytest.raises(ValueError, match="无效日志级别"):
            read_log(path=path, level="VERBOSE")

    def test_missing_file_returns_empty(self, tmp_path):
        """缺失文件返回空列表。"""
        assert read_log(path=str(tmp_path / "nope.log")) == []

    def test_default_path_matches_logger(self):
        """default_log_path 与 logger._LOG_FILE 一致（惰性引用）。"""
        from src.python.core.logger import _LOG_FILE

        assert default_log_path() == _LOG_FILE

    def test_log_levels_contains_standard(self):
        """LOG_LEVELS 覆盖标准 logging 级别。"""
        assert set(LOG_LEVELS) == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
