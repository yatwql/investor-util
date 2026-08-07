"""正式持仓更新失败/回滚语义（holdings_update.py 异常场景）。

覆盖：
  - backup 失败（目标目录不可写）→ 抛错，不继续 promote，旧文件完好
  - promote（copy）失败 → 旧正式文件未动，.bak 保留原文件（可恢复）
  - 半写态中间文件（.tmp）在失败路径被清理

边缘场景按纪律放入 *_edge.py（`@pytest.mark.edge` + `*_edge.py` 文件隔离）。
"""

from __future__ import annotations

import os
import shutil

import pytest
from unittest.mock import patch

from src.python.web.holdings_update import promote_upload_to_holdings

pytestmark = [pytest.mark.unit, pytest.mark.unit_web, pytest.mark.edge]


def _write(path, content):
    path = os.fspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_backup_failure_aborts_promote(tmp_path, monkeypatch):
    """backup 失败（备份目标不可写）→ 抛错，正式文件与 .bak 均完好（不继续 promote）。"""
    formal = _write(tmp_path / "holdings" / "持仓.xlsx", "旧持仓")
    temp = _write(tmp_path / "uploads" / "uuid.xlsx", "新上传")

    # 备份目标目录设为只读（backup 的 mkstemp/os.replace 失败）
    os.chmod(os.path.dirname(formal), 0o500)
    try:
        with pytest.raises(OSError):
            promote_upload_to_holdings(temp, formal)
    finally:
        os.chmod(os.path.dirname(formal), 0o755)

    # 正式文件未被覆盖
    assert open(formal, encoding="utf-8").read() == "旧持仓"


def test_promote_copy_failure_keeps_old_and_bak(tmp_path, monkeypatch):
    """promote（copy）失败 → 旧正式文件未动，.bak 保留原文件（可恢复）。"""
    formal = _write(tmp_path / "holdings" / "持仓.xlsx", "旧持仓")
    temp = _write(tmp_path / "uploads" / "uuid.xlsx", "新上传")

    # 原子写先 copy 到 .tmp 再 os.replace——copy2 目标恒为 .tmp。按调用次数触发：
    # 第 1 次 copy2 = 备份（放行，先落 .bak）；第 2 次 = promote 的 copy2（失败）
    real_copy2 = shutil.copy2
    calls = {"n": 0}

    def _flaky_copy2(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_copy2(src, dst)

    with patch("src.python.web.holdings_update.shutil.copy2", side_effect=_flaky_copy2):
        with pytest.raises(OSError):
            promote_upload_to_holdings(temp, formal)

    # 旧正式文件未动
    assert open(formal, encoding="utf-8").read() == "旧持仓"
    # .bak 保留旧文件（备份已完成），可手动恢复
    assert open(formal + ".bak", encoding="utf-8").read() == "旧持仓"
    # 无 .tmp 中间文件残留（失败路径清理）
    leftovers = [n for n in os.listdir(os.path.dirname(formal)) if n.endswith(".tmp")]
    assert leftovers == []


def test_temp_missing_raises(tmp_path):
    """临时文件不存在 → 抛错，旧正式文件不变。"""
    formal = _write(tmp_path / "holdings" / "持仓.xlsx", "旧持仓")
    missing_temp = str(tmp_path / "uploads" / "不存在.xlsx")
    with pytest.raises(OSError):
        promote_upload_to_holdings(missing_temp, formal)
    assert open(formal, encoding="utf-8").read() == "旧持仓"
