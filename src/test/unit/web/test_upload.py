"""上传安全模块单元测试（upload.py）。

覆盖：正常 xlsx 通过 / 非 xlsx 拒绝 / 超 10MB 拒绝 / 路径穿越文件名净化 /
非 PK 魔数拒绝 / 落盘后清理 / TTL 过期失效。
"""

from __future__ import annotations

import os
from io import BytesIO

import pytest
from openpyxl import Workbook

import src.python.web.upload as upload
from src.python.web.upload import (
    UPLOAD_BAD_FILE,
    UPLOAD_TOO_LARGE,
    UploadError,
    cleanup_all,
    discard_file,
    resolve_file,
    save_upload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _make_holdings_xlsx() -> bytes:
    """构造标准四列最小持仓 xlsx 字节流。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "账户一"
    ws.append(["名称", "代码", "持仓份额", "每份成本"])
    ws.append(["测试基金", "000001", 1000, 1.0])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _assert_under_upload_dir(path: str) -> None:
    """断言落盘路径位于上传临时目录内（防路径穿越逃逸）。"""
    root = os.path.realpath(upload._UPLOAD_DIR)
    assert os.path.realpath(path).startswith(root + os.sep) or os.path.realpath(path).startswith(root)


class TestSaveUpload:
    """正常/非法上传校验。"""

    def test_valid_xlsx_passes_and_registers(self):
        """正常 xlsx 通过：返回 file_id，注册可解析，落盘为 uuid 名。"""
        result = save_upload(BytesIO(_make_holdings_xlsx()), "个人投资持仓信息.xlsx")
        assert result["file_id"]
        assert result["count"] == 1
        assert result["sheets"] == ["账户一"]

        path = resolve_file(result["file_id"])
        assert path is not None
        _assert_under_upload_dir(path)
        # 服务端重命名：丢弃原始中文名，改用 uuid 名（内容即身份）
        assert "个人投资" not in os.path.basename(path)
        assert path.endswith(".xlsx")

    def test_reject_wrong_extension(self):
        """非 .xlsx 扩展名拒绝（.xls/.txt/宏文件等）。"""
        with pytest.raises(UploadError) as exc:
            save_upload(BytesIO(_make_holdings_xlsx()), "持仓.xls")
        assert exc.value.error_code == UPLOAD_BAD_FILE

    def test_reject_missing_filename(self):
        """未提供文件名拒绝。"""
        with pytest.raises(UploadError) as exc:
            save_upload(BytesIO(_make_holdings_xlsx()), None)
        assert exc.value.error_code == UPLOAD_BAD_FILE

    def test_reject_non_pk_magic(self):
        """非 PK zip 魔数拒绝（改扩展名伪装：内容不是 xlsx）。"""
        bogus = b"NOTAZIPFILE" + b"\x00" * 64
        with pytest.raises(UploadError) as exc:
            save_upload(BytesIO(bogus), "伪装.xlsx")
        assert exc.value.error_code == UPLOAD_BAD_FILE

    def test_reject_too_large(self):
        """超过 10MB 上限拒绝（读流计数）。"""
        oversized = b"PK\x03\x04" + b"\x00" * (upload._MAX_BYTES + 1)
        with pytest.raises(UploadError) as exc:
            save_upload(BytesIO(oversized), "超大.xlsx")
        assert exc.value.error_code == UPLOAD_TOO_LARGE

    def test_filename_sanitization_path_traversal(self):
        """路径穿越文件名净化：.. / 绝对路径不逃逸，落盘仍在上传目录。"""
        data = _make_holdings_xlsx()
        for evil in ("../../etc/passwd.xlsx", "/etc/evil.xlsx", r"..\..\evil.xlsx"):
            result = save_upload(BytesIO(data), evil)
            path = resolve_file(result["file_id"])
            assert path is not None
            _assert_under_upload_dir(path)
            # 原始恶意名被丢弃，落盘文件名不包含路径分隔符
            assert "/" not in os.path.basename(path)
            assert "\\" not in os.path.basename(path)
            assert "evil" not in os.path.basename(path)

    def test_reject_empty_holdings(self):
        """空持仓/无有效账户拒绝（内容预检：表头不符 sheet 被跳过）。"""
        wb = Workbook()
        ws = wb.active
        ws.title = "空账户"
        ws.append(["名称", "代码", "持仓份额", "每份成本"])  # 只有表头无数据
        buf = BytesIO()
        wb.save(buf)
        from src.python.web.upload import UPLOAD_EMPTY

        with pytest.raises(UploadError) as exc:
            save_upload(BytesIO(buf.getvalue()), "空持仓.xlsx")
        assert exc.value.error_code == UPLOAD_EMPTY


class TestFileLifecycle:
    """file_id 注册/过期/清理生命周期。"""

    def test_discard_removes_file_and_unregisters(self):
        """生成任务结束 discard_file：文件删除 + file_id 失效。"""
        result = save_upload(BytesIO(_make_holdings_xlsx()), "持仓.xlsx")
        file_id = result["file_id"]
        path = resolve_file(file_id)
        assert path is not None and os.path.isfile(path)

        discard_file(file_id)
        assert resolve_file(file_id) is None
        assert not os.path.exists(path)

    def test_expired_ttl_cleans_file(self, monkeypatch):
        """TTL 过期：resolve_file 自动清理（惰性过期）。"""
        monkeypatch.setattr(upload, "_FILE_TTL", -1)  # 强制所有记录视为过期
        result = save_upload(BytesIO(_make_holdings_xlsx()), "持仓.xlsx")
        file_id = result["file_id"]
        path = upload._file_registry[file_id][0]

        assert resolve_file(file_id) is None
        assert not os.path.exists(path)

    def test_cleanup_all_removes_residuals(self):
        """cleanup_all：清空注册表并删除全部残留文件（启动兜底）。"""
        r1 = save_upload(BytesIO(_make_holdings_xlsx()), "a.xlsx")
        r2 = save_upload(BytesIO(_make_holdings_xlsx()), "b.xlsx")
        p1 = upload._file_registry[r1["file_id"]][0]

        count = cleanup_all()
        assert count >= 2
        assert resolve_file(r1["file_id"]) is None
        assert resolve_file(r2["file_id"]) is None
        assert not os.path.exists(p1)
