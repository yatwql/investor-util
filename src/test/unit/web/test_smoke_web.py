"""测试：scripts/smoke-web.py 可复跑 Web 冒烟脚本。

对齐「沉淀 Web 冒烟脚本」修复方向：以 pytest 为载体调用脚本的
``run_smoke()``，验证 11 项 HTTP 全链路断言全部通过（含正式-用存量模式、
配置编辑冒烟）。脚本自身走 Flask test_client（进程内、不占端口、不发真实
网络），管线/健康/历史均 mock，无真实 LLM/行情/历史文件依赖。

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
    """run_smoke() 11 项断言全部通过。"""
    mod = _load_script()
    results = mod.run_smoke()

    assert len(results) == 11
    failed = [r for r in results if not r["ok"]]
    assert failed == [], f"Web 冒烟存在失败项: {failed}"


class _FakePollClient:
    """模拟 run 状态机轮询客户端：按给定 status 序列依次返回。"""

    def __init__(self, statuses: list[str]):
        self._statuses = statuses

    def get(self, url):
        class _Resp:
            @staticmethod
            def get_json():
                return {"data": {"status": self._statuses.pop(0)}}

        return _Resp()


def test_smoke_web_poll_run_finished_waits_for_done():
    """_poll_run_finished 轮询至终态：queued→running→done 返回 done（不提前返回）。"""
    mod = _load_script()
    status = mod._poll_run_finished(_FakePollClient(["queued", "running", "done"]), "r1")
    assert status == "done"


def test_smoke_web_poll_run_finished_returns_failed():
    """_poll_run_finished 到 failed 也返回终态 failed。"""
    mod = _load_script()
    status = mod._poll_run_finished(_FakePollClient(["queued", "failed"]), "r1")
    assert status == "failed"


def test_smoke_web_poll_run_finished_never_finishes_returns_last():
    """_poll_run_finished 始终不到终态时返回最后 status（不崩溃）。"""
    mod = _load_script()
    status = mod._poll_run_finished(_FakePollClient(["running", "running"]), "r1", max_iters=2)
    assert status == "running"
