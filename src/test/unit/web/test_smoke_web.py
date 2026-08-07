"""测试：scripts/smoke-web.py 可复跑 Web 冒烟脚本。

对齐「沉淀 Web 冒烟脚本」修复方向：以 pytest 为载体调用脚本的
``run_smoke()``，验证 10 项 HTTP 全链路断言全部通过（含正式-用存量模式冒烟）。
脚本自身走 Flask test_client（进程内、不占端口、不发真实网络），
管线/健康/历史均 mock，无真实 LLM/行情/历史文件依赖。

隔离：
  - 脚本内部将 output_dir / 上传目录重定向到临时目录并 try/finally 还原
  - conftest 的 _isolate_sensitive_paths / _auto_reset_run_manager 提供
    兜底隔离，本用例不触发真实数据读写
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]  # investor-util 仓库根目录
_SCRIPT = _REPO_ROOT / "scripts" / "smoke-web.py"

pytestmark = [pytest.mark.unit, pytest.mark.unit_web]


def _load_script():
    """按文件名加载 scripts/ 下的脚本（规避 import 路径限制）。"""
    mod_name = _SCRIPT.stem.replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_smoke_web_run_smoke_all_pass():
    """run_smoke() 10 项断言全部通过。"""
    mod = _load_script()
    results = mod.run_smoke()

    assert len(results) == 10
    failed = [r for r in results if not r["ok"]]
    assert failed == [], f"Web 冒烟存在失败项: {failed}"
