"""上传安全边缘场景测试（安全边缘，放 *_edge.py）。

与 test_upload.py 互补：本文件聚焦极端/异常变体——zip-bomb（注入 fake
预检，避免真实解压 OOM）、伪装 xlsx 的普通 zip、行数超限、恰好/超限大小
边界、反斜杠与编码路径穿越、空流。全部通过 ``get_xlsx_info``/``read_holdings``
注入点 fake，不触发真实解压/不落盘敏感数据。
"""

from __future__ import annotations

import io
import os
import zipfile

import pytest

import src.python.web.upload as upload
from src.python.web.upload import (
    UPLOAD_BAD_FILE,
    UPLOAD_TOO_MANY_ROWS,
    UploadError,
    save_upload,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_web, pytest.mark.edge]


def _fake_info(**overrides) -> dict:
    """标准可用的 fake get_xlsx_info 返回值（部分覆盖）。"""
    base = {"sheet_names": ["账户一"], "accounts": 1, "total_rows": 1}
    base.update(overrides)
    return base


def _valid_xlsx_bytes() -> bytes:
    """最小合法 xlsx 字节（PK 魔数 + 可解析内容，经注入 fake 预检）。"""
    import io as _io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "账户一"
    ws.append(["名称", "代码", "持仓份额", "每份成本"])
    ws.append(["测试基金", "000001", 1000, 1.0])
    buf = _io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestZipBombAndDisguise:
    """zip-bomb / 伪装扩展名（PK 魔数通过但内容异常）。"""

    def test_zip_bomb_row_limit_rejected(self):
        """zip-bomb 变体：注入超行数 info → 行数上限拒绝（不真实解压）。"""
        with pytest.raises(UploadError) as exc:
            save_upload(
                io.BytesIO(_valid_xlsx_bytes()),
                "炸弹.xlsx",
                get_xlsx_info=lambda _p: _fake_info(total_rows=upload._MAX_ROWS + 1),
                read_holdings=lambda _p: [],
            )
        assert exc.value.error_code == UPLOAD_TOO_MANY_ROWS

    def test_plain_zip_disguised_as_xlsx(self):
        """普通 zip 伪装 .xlsx：PK 魔数通过，但预检读取失败 → BAD_FILE。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("not_xlsx.txt", "plain zip, not an excel workbook")
        with pytest.raises(UploadError) as exc:
            save_upload(io.BytesIO(buf.getvalue()), "伪装.zip.xlsx")
        assert exc.value.error_code == UPLOAD_BAD_FILE

    def test_bad_magic_still_rejected(self):
        """非 PK 魔数伪装（即使扩展名 .xlsx）→ BAD_FILE。"""
        with pytest.raises(UploadError) as exc:
            save_upload(io.BytesIO(b"RAR!..." + b"\x00" * 32), "伪装.xlsx")
        assert exc.value.error_code == UPLOAD_BAD_FILE


class TestSizeBoundaries:
    """大小边界：恰好上限通过流校验，超上限拒绝。"""

    def test_exact_max_bytes_passes_stream_check(self):
        """恰好 _MAX_BYTES：读流校验通过（不抛 TOO_LARGE），后续预检另论。"""
        # PK 头 + 填充到恰好上限
        payload = _valid_xlsx_bytes()
        assert len(payload) < upload._MAX_BYTES
        padded = payload + b"\x00" * (upload._MAX_BYTES - len(payload))
        data = upload._read_and_validate_stream(io.BytesIO(padded))
        assert len(data) == upload._MAX_BYTES

    def test_over_max_rejected_before_prevalidate(self):
        """超上限：读流即拒（即使内容本可解析）。"""
        payload = _valid_xlsx_bytes()
        oversized = payload + b"\x00" * (upload._MAX_BYTES - len(payload) + 1)
        with pytest.raises(UploadError) as exc:
            save_upload(io.BytesIO(oversized), "超大.xlsx")
        assert exc.value.error_code == "UPLOAD_TOO_LARGE"


class TestPathTraversalVariants:
    """路径穿越变体：反斜杠 / 绝对路径 / 编码段均不逃逸。"""

    @pytest.mark.parametrize(
        "evil",
        [
            r"..\..\..\Windows\system32\evil.xlsx",  # Windows 反斜杠穿越
            "/etc/passwd.xlsx",  # 绝对路径
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd.xlsx",  # URL 编码点段
            "..%5c..%5c..%5csecret.xlsx",  # 编码反斜杠
            "a" * 300 + ".xlsx",  # 超长文件名（系统安全限制）
        ],
    )
    def test_evil_filenames_never_escape(self, evil):
        """恶意文件名：扩展名校验通过但落盘为 uuid 名，不逃逸上传目录。"""
        result = save_upload(
            io.BytesIO(_valid_xlsx_bytes()),
            evil,
            get_xlsx_info=lambda _p: _fake_info(),
            read_holdings=lambda _p: [_p],  # 返回非空即可
        )
        path = upload.resolve_file(result["file_id"])
        assert path is not None
        root = os.path.realpath(upload._UPLOAD_DIR)
        real = os.path.realpath(path)
        assert real.startswith(root)
        # 落盘名 = uuid.xlsx，不含任何穿越段/原始名
        assert "/" not in os.path.basename(path)
        assert "\\" not in os.path.basename(path)
        assert "evil" not in os.path.basename(path)


class TestMalformedInputs:
    """空流 / 预检失败注入等输入异常。"""

    def test_empty_stream_rejected(self):
        """空流（0 字节）：PK 魔数校验失败 → BAD_FILE。"""
        with pytest.raises(UploadError) as exc:
            save_upload(io.BytesIO(b""), "空.xlsx")
        assert exc.value.error_code == UPLOAD_BAD_FILE

    def test_prevalidate_error_propagates_bad_file(self):
        """注入 get_xlsx_info 返回 error → 预检报 BAD_FILE（文件不可读）。"""
        with pytest.raises(UploadError) as exc:
            save_upload(
                io.BytesIO(_valid_xlsx_bytes()),
                "坏文件.xlsx",
                get_xlsx_info=lambda _p: {"error": "corrupt"},
                read_holdings=lambda _p: [],
            )
        assert exc.value.error_code == UPLOAD_BAD_FILE

    def test_failed_prevalidate_cleans_tmp_file(self):
        """预检失败：落盘的临时文件被清理（不留残余）。"""
        before = set(os.listdir(upload._UPLOAD_DIR)) if os.path.isdir(upload._UPLOAD_DIR) else set()
        with pytest.raises(UploadError):
            save_upload(
                io.BytesIO(_valid_xlsx_bytes()),
                "预检失败.xlsx",
                get_xlsx_info=lambda _p: {"error": "corrupt"},
                read_holdings=lambda _p: [],
            )
        after = set(os.listdir(upload._UPLOAD_DIR)) if os.path.isdir(upload._UPLOAD_DIR) else set()
        assert after == before
