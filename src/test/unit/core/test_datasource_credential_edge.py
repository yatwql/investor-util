"""数据源凭据声明与就绪判定的边缘/异常场景测试。

覆盖：空声明表、声明缺 env_var、环境变量全空白、重复注册、未知源查询、
就绪矩阵在声明被清空后的回落——均为「声明写错」而非「源不可达」的场景，
机制必须安然降级而不是抛异常（体检与健康检查复用它，不能因声明错误而崩）。

运行：
  pytest src/test/unit/core/test_datasource_credential_edge.py -v
"""

from __future__ import annotations

import pytest

from src.python.core.datasource_credential import (
    CREDENTIAL_SPECS,
    CredentialSpec,
    credential_hint,
    credential_readiness,
    missing_credential,
    register_credential_spec,
    reset_credential_specs,
)

pytestmark = [pytest.mark.unit, pytest.mark.unit_core, pytest.mark.edge]


class TestDeclarationEdges:
    """声明侧边界：空表 / 缺变量名 / 重复登记 / 清空。"""

    def test_lookup_on_empty_registry(self):
        """空声明表查询任何源都返回 None（无需凭据），不抛异常。"""
        assert CREDENTIAL_SPECS == {}
        assert missing_credential("anything") is None
        assert credential_readiness() == []

    def test_spec_without_env_var_is_reported_missing(self):
        """声明缺 env_var（空串）→ 判定为缺失而非崩溃。

        空变量名在 os.environ 中必然取不到值，故恒判缺失；这属**声明写错**，
        但机制须安全降级——把问题显式暴露成「缺少凭据」比抛 KeyError 有用。
        """
        register_credential_spec(CredentialSpec("broken", "声明有误的源", ""))
        assert missing_credential("broken") is not None

    def test_reset_clears_registry(self, monkeypatch):
        """清空后回到生产初始状态（全部免费源）。"""
        monkeypatch.setenv("EDGE_KEY", "v")
        register_credential_spec(CredentialSpec("e1", "边缘源一", "EDGE_KEY"))
        register_credential_spec(CredentialSpec("e2", "边缘源二", "EDGE_KEY"))
        assert len(CREDENTIAL_SPECS) == 2

        reset_credential_specs()
        assert CREDENTIAL_SPECS == {}
        assert credential_readiness() == []

    def test_duplicate_registration_keeps_one_row(self, monkeypatch):
        """同一源重复登记只留一行（矩阵不出现重复行）。"""
        monkeypatch.delenv("DUP_KEY", raising=False)
        register_credential_spec(CredentialSpec("dup", "旧", "DUP_KEY"))
        register_credential_spec(CredentialSpec("dup", "新", "DUP_KEY"))
        rows = credential_readiness()
        assert len(rows) == 1
        assert rows[0]["display_name"] == "新"


class TestEnvironmentEdges:
    """环境变量侧边界：Unicode 空白 / 仅换行 / 正常值。"""

    @pytest.mark.parametrize("value", ["", " ", "\t", "\n", " \t\n "])
    def test_all_whitespace_variants_are_missing(self, monkeypatch, value):
        """各类空白字符组成的值一律视为未配置。"""
        monkeypatch.setenv("WS_KEY", value)
        register_credential_spec(CredentialSpec("ws", "空白源", "WS_KEY"))
        assert missing_credential("ws") is not None
        assert credential_readiness()[0]["ready"] is False

    def test_value_with_surrounding_space_is_ready(self, monkeypatch):
        """值两侧有空格但内容非空 → 就绪（只判空，不做 trim 后改写）。"""
        monkeypatch.setenv("TRIM_KEY", " abc ")
        register_credential_spec(CredentialSpec("trim", "带空格源", "TRIM_KEY"))
        assert missing_credential("trim") is None


class TestHintEdges:
    """指引措辞边界：地址与备注取舍。"""

    def test_hint_with_note_only(self):
        """只有备注无地址 → 备注照样上屏，不出现「申请地址」空占位。"""
        hint = credential_hint(CredentialSpec("n", "仅备注源", "N_KEY", note="免费额度 100 次/日"))
        assert "申请地址" not in hint
        assert "免费额度 100 次/日" in hint

    def test_hint_never_raises_on_empty_display_name(self):
        """显示名为空也不抛异常（措辞退化但不崩）。"""
        assert "N_KEY" in credential_hint(CredentialSpec("n", "", "N_KEY"))
