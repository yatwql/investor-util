"""测试：check-style-guardrails.py — 设计护栏机检（DESIGN.md 护栏样式面）。

覆盖：
  - E1 强调色越权：品牌蓝字面量命中 / token 定义行与 JS fallback 串豁免 / 注释豁免
    / 品牌蓝集从 :root 强调系 token 动态提取（注入合成定义即生效）
  - E2 明暗同步：dark 覆盖变量根缺命中 / 根齐通过
  - E3 双面 token 对表：表共名缺定义命中 / 两面同名颜色变量未登记命中 / 一致通过
  - W1/W2 观察语义：裸色值与圆角档外**不进 findings**（只进 observations）
  - 真实仓库冒烟：E 级零 finding + observations 键齐备 + --ci 退出 0（结构断言）
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from src.test._script_loader import load_script

pytestmark = [
    pytest.mark.unit,
    pytest.mark.unit_scripts,
    pytest.mark.usefixtures("offline_external_sources"),
]

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def guard():
    return load_script("check-style-guardrails.py")


_MINIMAL_DESIGN = """## Colors — 语义角色表

| 角色族 | 角色 | 报告侧实现 | 工作台侧实现 | 备注 |
|---|---|---|---|---|
| 强调 | 品牌蓝 | `--primary` | `--primary` | 单强调色 |

## Typography — 字阶表
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestEmphasisColor:
    """E1 强调色越权（护栏 3）。"""

    def test_brand_hex_outside_definition_is_finding(self, guard, tmp_path):
        f = _write(tmp_path, "a.html", ":root { --primary: #2E75B6; }\n.btn { background: #2E75B6; }\n")
        findings, _ = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert any("强调色越权" in x for x in findings)

    def test_definition_js_comment_exempt(self, guard, tmp_path):
        f = _write(
            tmp_path,
            "b.html",
            ":root { --primary: #2E75B6; }\n"
            "/* .x { color: #2E75B6 } */\n"
            "const c = '#2E75B6';\n"
            ".y { color: var(--primary); }\n",
        )
        findings, _ = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert not any("强调色越权" in x for x in findings)

    def test_brand_set_derived_from_root_token(self, guard, tmp_path):
        """品牌集动态提取：:root 里新强调 token 的 hex 立即进白名单检查域。"""
        f = _write(tmp_path, "c.html", ":root { --primary: #123456; }\n.z { outline: #123456; }\n")
        findings, _ = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert any("#123456" in x for x in findings)


class TestDarkSync:
    """E2 明暗同步（护栏 5）。"""

    def test_dark_var_missing_root_is_finding(self, guard, tmp_path):
        f = _write(tmp_path, "d.html", ':root { --ok: #0a0; }\n[data-theme="dark"] { --ghost: #fff; }\n')
        findings, _ = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert any("--ghost" in x and "缺定义" in x for x in findings)

    def test_dark_vars_present_in_root_pass(self, guard, tmp_path):
        f = _write(tmp_path, "e.html", ':root { --ok: #0a0; }\n[data-theme="dark"] { --ok: #6b6; }\n')
        findings, _ = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert not any("缺定义" in x for x in findings)


class TestTokenAlignment:
    """E3 双面 token 对表（Colors「同名对齐」段）。"""

    def test_table_shared_token_missing_on_side_is_finding(self, guard, tmp_path):
        design = _MINIMAL_DESIGN  # 表共名 --primary
        rep = _write(tmp_path, "report_template.html", ":root { --primary: #2E75B6; }\n")
        web = _write(tmp_path, "style.css", ":root { --accent: #0f0; }\n")
        findings, _ = guard.run_checks(files=[rep, web], design_text=design)
        assert any("--primary" in x and "共名" in x for x in findings)

    def test_shared_color_not_registered_in_table_is_finding(self, guard, tmp_path):
        """两面同名颜色变量（表外新 token）→ 未登记命中。"""
        rep = _write(tmp_path, "report_template.html", ":root { --brand-new: #123456; }\n")
        web = _write(tmp_path, "style.css", ":root { --brand-new: #654321; }\n")
        findings, _ = guard.run_checks(files=[rep, web], design_text=_MINIMAL_DESIGN)
        assert any("--brand-new" in x and "未在 Colors 表登记" in x for x in findings)

    def test_aligned_pair_passes(self, guard, tmp_path):
        rep = _write(tmp_path, "report_template.html", ":root { --primary: #2E75B6; }\n")
        web = _write(tmp_path, "style.css", ":root { --primary: #1f6fb2; }\n")
        findings, _ = guard.run_checks(files=[rep, web], design_text=_MINIMAL_DESIGN)
        assert findings == []


class TestObservations:
    """W 级观察语义：统计但不判 finding。"""

    def test_raw_color_only_observed(self, guard, tmp_path):
        f = _write(tmp_path, "f.html", ":root { --ok: #0a0; }\n.a { box-shadow: 0 1px 2px rgba(0,0,0,0.1); }\n")
        findings, obs = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert findings == []
        assert obs["raw_colors"], "裸色值应进观察统计"

    def test_out_of_tier_radius_only_observed(self, guard, tmp_path):
        f = _write(tmp_path, "g.html", ":root { --ok: #0a0; }\n.b { border-radius: 3px; }\n")
        findings, obs = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert findings == []
        assert any("3px" in x for x in obs["radius"]), "档外圆角应进观察统计"

    def test_tier_radius_not_observed(self, guard, tmp_path):
        f = _write(
            tmp_path,
            "h.html",
            ':root { --ok: #0a0; }\n.c { border-radius: 8px; }\n[data-theme="dark"] { --ok: #0a0; }\n',
        )
        _, obs = guard.run_checks(files=[f], design_text=_MINIMAL_DESIGN)
        assert not any("8px" in x for x in obs["radius"])


class TestRealRepoSmoke:
    """真实仓库冒烟：E 级零 finding（观察期口径）+ CLI 退出 0。"""

    def test_e_level_clean(self, guard):
        findings, obs = guard.run_checks()
        assert findings == [], f"E 级应零 finding: {findings[:3]}"
        assert set(obs) == {"raw_colors", "radius"}

    def test_radius_tiers_match_design(self, guard):
        """圆角档位与 DESIGN.md Layout「圆角档」同源（4/6/8 明文 + 999 药丸）。"""
        design = (_REPO_ROOT / "DESIGN.md").read_text(encoding="utf-8")
        for tier in ("4px", "6px", "8px"):
            assert tier in design, f"DESIGN Layout 应含圆角档 {tier}"
        assert guard.RADIUS_TIERS >= {4, 6, 8, 999}

    def test_ci_exit_zero(self):
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "check-style-guardrails.py"), "--ci"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert proc.returncode == 0, f"--ci 应退出 0（观察期 E 级零 finding）: {proc.stdout}{proc.stderr}"
