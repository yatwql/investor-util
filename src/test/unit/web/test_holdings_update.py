"""正式持仓更新单元测试（holdings_update.py 正常路径）。

覆盖：
  - backup_holdings_file：首次无旧文件返回 None；有旧文件生成 .bak 单槽轮转
  - promote_upload_to_holdings：提升后正式文件内容=临时文件；先备份旧文件
  - 原子写：任一环节不出现半写态（mkstemp + os.replace）

失败/回滚语义（不可写目录等异常场景）见 test_holdings_update_edge.py。
"""

from __future__ import annotations

import os

import pytest

from src.python.web.holdings_update import backup_holdings_file, promote_upload_to_holdings

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _write(path, content):
    path = os.fspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_backup_missing_file_returns_none(tmp_path):
    """正式文件不存在 → 返回 None（首次正式更新无需备份）。"""
    assert backup_holdings_file(str(tmp_path / "不存在.xlsx")) is None
    # 无 .bak 残留
    assert not os.path.exists(str(tmp_path / "不存在.xlsx.bak"))


def test_backup_creates_bak_single_slot(tmp_path):
    """有旧文件 → 生成 {path}.bak，内容一致；二次备份单槽轮转覆盖。"""
    formal = _write(tmp_path / "holdings" / "持仓.xlsx", "v1")
    bak = backup_holdings_file(formal)
    assert bak == formal + ".bak"
    assert open(bak, encoding="utf-8").read() == "v1"

    # 单槽轮转：第二次备份覆盖 .bak，不保留多版本
    _write(formal, "v2")
    backup_holdings_file(formal)
    assert open(bak, encoding="utf-8").read() == "v2"


def test_promote_updates_formal_and_backs_up(tmp_path):
    """提升后正式文件=临时文件；旧正式文件备份为 .bak。"""
    formal = _write(tmp_path / "holdings" / "持仓.xlsx", "旧持仓")
    temp = _write(tmp_path / "uploads" / "uuid.xlsx", "新上传持仓")

    ret = promote_upload_to_holdings(temp, formal)
    assert ret == formal
    assert open(formal, encoding="utf-8").read() == "新上传持仓"
    # 旧正式文件备份保留
    assert open(formal + ".bak", encoding="utf-8").read() == "旧持仓"
    # 临时文件原样保留（copy 非 move，调用方负责清理）
    assert os.path.isfile(temp)


def test_promote_first_time_no_bak(tmp_path):
    """首次正式更新（无旧文件）：提升成功且无 .bak。"""
    formal = str(tmp_path / "holdings" / "持仓.xlsx")
    temp = _write(tmp_path / "uploads" / "uuid.xlsx", "首次持仓")

    promote_upload_to_holdings(temp, formal)
    assert open(formal, encoding="utf-8").read() == "首次持仓"
    assert not os.path.exists(formal + ".bak")


def test_promote_atomic_no_partial_state(tmp_path):
    """提升为原子写：正式文件最终要么旧内容要么新内容，无半写态中间文件残留。"""
    formal = _write(tmp_path / "holdings" / "持仓.xlsx", "旧")
    temp = _write(tmp_path / "uploads" / "uuid.xlsx", "新")
    promote_upload_to_holdings(temp, formal)
    # 目录下不应残留 .holdings-*.tmp 中间文件
    leftover = [n for n in os.listdir(os.path.dirname(formal)) if n.endswith(".tmp")]
    assert leftover == []
    assert open(formal, encoding="utf-8").read() == "新"
