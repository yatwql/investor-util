"""`check-doc-drift` 共享设施 —— 文档路径常量、扫描面与通用解析原语。

被检文档清单、生成物排除规则、表格与区间解析、项目统计口径的公共辅助。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from _checklib import REPO_ROOT, rel


_README = REPO_ROOT / "README.md"


_MANUALS = REPO_ROOT / "docs" / "manuals"


_MANAGEMENTS = REPO_ROOT / "docs" / "managements"


_FOLDERS_MD = _MANAGEMENTS / "folders.md"


_HOW_TO_CONFIG_MD = _MANUALS / "how-to-config.md"


_REPORTS_MD = _MANUALS / "reports-instruction.md"


_TUI_MENU_MD = _MANUALS / "how-to-use-tui-menu.md"


_LLM_TECHNICAL_MD = _MANAGEMENTS / "llm-technical.md"
_RELIABILITY_MD = _MANUALS / "datasource-reliability.md"


_TEST_COVERAGE_MD = _MANAGEMENTS / "test-coverage.md"


_PLAN_MD = _MANAGEMENTS / "plan.md"


_CHANGELOG_MD = _MANAGEMENTS / "changelog.md"


_REVIEW_FINDINGS_MD = _MANAGEMENTS / "review-findings.md"


_HISTORY_DOCS = {_MANAGEMENTS / "changelog.md", _MANAGEMENTS / "review-findings.md"}


_TREE_ROOTS = ("src", "scripts", "docs/managements", "docs/manuals", "docs/plan")


_GENERATED_DIRS = {
    "__pycache__",
    ".eggs",
    "build",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov",
}


_GENERATED_SUFFIXES = (".egg-info", ".dist-info")


_GENERATED_FILES = {".coverage"}


_GENERATED_PREFIXES = ("docs/tmp/",)


def _is_generated(rel: str) -> bool:
    """相对路径是否属构建/缓存产物（`pip install -e` 的 egg-info、构建目录、缓存等）。

    这些由工具链生成、不该出现在目录树里也不该计入统计——CI 上 `pip install -e ".[test]"`
    会在 `src/` 下留下 `*.egg-info/`，若不排除会被误报为「目录树缺条目」。

    **例外**：`test-reports/` 的规范位置是仓库根（不在受检根内），故**不**豁免——受检目录
    （`src/`、`scripts/`、`docs/{managements,manuals,plan}`）下出现 `test-reports/`
    属误落（如入口把项目根算到了 `scripts/`），须由目录树检查报出。
    """
    if rel in _GENERATED_FILES or rel.startswith(_GENERATED_PREFIXES):
        return True
    return any(p in _GENERATED_DIRS or p.endswith(_GENERATED_SUFFIXES) for p in Path(rel).parts)


def _scan_docs() -> dict[Path, str]:
    """返回参与断言扫描的文档集合（README + 手册 + 管理文档，排除历史记录类）。"""
    docs: list[Path] = [_README]
    docs += sorted(_MANUALS.glob("*.md"))
    docs += sorted(_MANAGEMENTS.glob("*.md"))
    return {p: p.read_text(encoding="utf-8") for p in docs if p not in _HISTORY_DOCS}


def _doc_section(text: str, start: str, end: str | None) -> str:
    """取 ``start`` 起、到 ``end``（不含）的区段；起点缺失返回空串。"""
    idx = text.find(start)
    if idx < 0:
        return ""
    if end is None:
        return text[idx:]
    stop = text.find(end, idx + len(start))
    return text[idx:] if stop < 0 else text[idx:stop]


def _split_table_row(line: str) -> list[str] | None:
    """拆分 markdown 表格行 → 去除粗体标记的单元格列表（非表格行返回 None）。"""
    if not line.startswith("|"):
        return None
    cells = [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]
    return cells if len(cells) >= 4 else None


def _first_number(cell: str) -> str | None:
    """取单元格中的首个数字（去千分位），无数字时返回 None（`-` / 空占位）。"""
    m = re.search(r"[\d][\d,]*", cell)
    return m.group(0).replace(",", "") if m else None


def _count(files: list[Path]) -> tuple[int, int]:
    kept = [p for p in files if not _is_generated(rel(p))]
    return len(kept), sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in kept)


def _values_equal(doc_value: str, code_value: object) -> bool:
    """文档字符串 ↔ 代码默认值的等价判定（bool/None/数字/路径/字符串）。"""
    shown = doc_value.strip()
    if isinstance(code_value, bool):
        return shown.lower() in (("true", "开") if code_value else ("false", "关"))
    if code_value is None:
        return shown.lower() in ("null", "none", "无")
    if isinstance(code_value, (int, float)):
        try:
            return float(shown.replace(",", "")) == float(code_value)
        except ValueError:
            return False
    text = str(code_value)
    if shown == text or shown.strip("\"'") == text.strip("\"'"):
        return True
    # 路径类默认值在代码内可能已被解析为绝对路径，文档写相对形式
    return bool(shown) and (text.endswith(shown) or Path(text).name == Path(shown).name)


def _collect_test_count() -> int | None:
    """已收集用例数（与 folders.md 说明同源），见 `_collect_test_snapshot`。"""
    snapshot = _collect_test_snapshot()
    return snapshot.get("_总收集")


#: 测试计数快照磁盘缓存落点（可经环境变量重定向；测试隔离在
#: `src/test/_path_isolation.py::seed_sensitive_path_isolation` 统一改写到 tmp_path）
_SNAPSHOT_CACHE_ENV = "DOC_DRIFT_SNAPSHOT_CACHE"
_SNAPSHOT_CACHE_DEFAULT = REPO_ROOT / "data" / "cache" / "test_coverage_snapshot.json"


def _snapshot_cache_path() -> Path:
    """快照缓存文件路径（环境变量覆盖优先，便于测试隔离不依赖模块实例身份）。"""
    override = os.environ.get(_SNAPSHOT_CACHE_ENV)
    return Path(override) if override else _SNAPSHOT_CACHE_DEFAULT


def _snapshot_signature(
    test_root: Path | None = None,
    extra_files: list[Path] | None = None,
) -> str:
    """测试收集快照的树指纹：`src/test` 全树 + 收集链路依赖文件 + 解释器大版本。

    指纹不变 → 收集结果必然不变（pytest 只收集 `src/test/`，分类逻辑由
    `collect-test-coverage.py` 承载，`pytest.ini`/`pyproject.toml` 影响收集行为），
    可直接复用磁盘快照、免跑 3~4s 的 pytest 收集；任一输入变化（路径+大小+mtime_ns
    粒度）即失效重收集——失效方向永远偏向真收集，宁可多跑不陈旧。
    """
    root = test_root if test_root is not None else REPO_ROOT / "src" / "test"
    extras = (
        extra_files
        if extra_files is not None
        else [
            REPO_ROOT / "pytest.ini",
            REPO_ROOT / "pyproject.toml",
            REPO_ROOT / "scripts" / "collect-test-coverage.py",
        ]
    )
    entries: list[str] = []
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                st = p.stat()
                entries.append(f"tree:{p.relative_to(root).as_posix()}|{st.st_size}|{st.st_mtime_ns}")
    for ep in extras:
        if ep.exists():
            st = ep.stat()
            entries.append(f"extra:{ep}|{st.st_size}|{st.st_mtime_ns}")
    entries.append(f"python{sys.version_info[0]}.{sys.version_info[1]}")
    return hashlib.sha1("\n".join(entries).encode("utf-8")).hexdigest()


def _read_snapshot_state() -> dict:
    """读 v2 按文件计数状态；损坏/旧格式/收集逻辑版本不符一律当空（走全量重建）。"""
    path = _snapshot_cache_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("format") != _SNAPSHOT_FORMAT:
        return {}
    if data.get("logic") != _logic_key():
        return {}
    if not isinstance(data.get("files"), dict):
        return {}
    return data


def _write_snapshot_state(state: dict) -> None:
    """原子写 v2 状态（失败静默降级——缓存只是加速，不是真值）。"""
    path = _snapshot_cache_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


#: 受收集测试文件根 / live 套件目录（`pytest.ini` addopts `-m "not live"` 恒不收集 →
#: live 不入逐文件账本；配置一变共享指纹即失效转全量）
_TEST_ROOT = REPO_ROOT / "src" / "test"
_LIVE_DIR = _TEST_ROOT / "live"
#: 快照缓存结构版本（结构/字段变更需递增，旧格式按空处理）
_SNAPSHOT_FORMAT = 2
#: 影子双算连续一致次数达标后停用影子（纯增量）；不一致立即归零继续守门
_SHADOW_MATCHES_NEEDED = 5


def _file_signature(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _is_test_file(path: Path) -> bool:
    return path.name.startswith("test_") or path.name.endswith("_test.py")


def _current_test_files() -> dict[str, Path]:
    """当前受收集测试文件：{仓库相对 posix 路径: 绝对路径}（排除 live 与缓存目录）。"""
    out: dict[str, Path] = {}
    if not _TEST_ROOT.exists():
        return out
    for p in sorted(_TEST_ROOT.rglob("*.py")):
        if "__pycache__" in p.parts or p == _LIVE_DIR or _LIVE_DIR in p.parents:
            continue
        if _is_test_file(p):
            out[p.relative_to(REPO_ROOT).as_posix()] = p
    return out


def _logic_key() -> str:
    """收集逻辑版本：收集脚本 + 本模块 + 解释器大版本 + pytest 版本，任一变化全量重建。"""
    parts = [f"{sys.version_info[0]}.{sys.version_info[1]}"]
    try:
        parts.append(metadata.version("pytest"))
    except Exception:  # noqa: BLE001 — 元数据缺失只降级为不等，偏向全量
        parts.append("?")
    for src_file in (REPO_ROOT / "scripts" / "collect-test-coverage.py", Path(__file__)):
        try:
            parts.append(hashlib.sha1(src_file.read_bytes()).hexdigest())
        except OSError:
            parts.append("?")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _shared_signature() -> str:
    """共享收集语境指纹：`src/` 非测试文件（含 conftest）+ pytest 配置 + 解释器大版本。

    任一变化（conftest 钩子、参数化数据源、业务代码、配置）→ 每文件计数整体不可信，
    整树全量重收集——失效方向永远偏向真收集，宁可多跑不陈旧。
    """
    entries: list[str] = []
    src_root = REPO_ROOT / "src"
    if src_root.exists():
        for p in sorted(src_root.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            if (_TEST_ROOT in p.parents or p.parent == _TEST_ROOT) and _is_test_file(p):
                continue  # 测试文件单独按文件比对，不进共享指纹
            st = p.stat()
            entries.append(f"{p.relative_to(REPO_ROOT).as_posix()}|{st.st_size}|{st.st_mtime_ns}")
    for ep in (REPO_ROOT / "pytest.ini", REPO_ROOT / "pyproject.toml"):
        if ep.exists():
            st = ep.stat()
            entries.append(f"extra:{ep.as_posix()}|{st.st_size}|{st.st_mtime_ns}")
    entries.append(f"python{sys.version_info[0]}.{sys.version_info[1]}")
    return hashlib.sha1("\n".join(entries).encode("utf-8")).hexdigest()


def _parse_collect_stdout(stdout: str) -> tuple[dict[str, int], dict[str, int]]:
    """收集脚本输出 → (聚合快照含 ``_总收集``, 逐文件计数)。"""
    snapshot: dict[str, int] = {}
    per_file: dict[str, int] = {}
    total = re.search(r"总收集:\s*(\d+)\s*项", stdout)
    if total:
        snapshot["_总收集"] = int(total.group(1))
    for line in stdout.splitlines():
        pm = re.match(r"^(\S+\.py)\t(\d+)$", line)
        if pm:
            per_file[pm.group(1)] = int(pm.group(2))
            continue
        m = re.match(r"^([\w一-鿿][^:]*?):\s*(\d+)$", line.strip())
        if m:
            snapshot[m.group(1).strip()] = int(m.group(2))
    return snapshot, per_file


def _run_collect(file_args: list[str]) -> tuple[dict[str, int], dict[str, int]] | None:
    """跑收集脚本（``file_args``=限定文件，空 = 整树）。失败/空输出/非零退出 → None。"""
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "collect-test-coverage.py"), *file_args],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",  # 显式编码（cp936 Windows/locale 假设 + EncodingWarning 严格档）
        errors="replace",  # 子进程若因环境写出非 UTF-8 字节，降级替换而非在 reader 线程抛 UnicodeDecodeError
        text=True,
    )
    stdout = proc.stdout or ""
    if proc.returncode not in (0, 5) or not stdout.strip():
        # 非零退出 = 收集出错（exit=4 时输出含未过滤错数）→ 拒收，不回写
        return None
    return _parse_collect_stdout(stdout)


def _shadow_active(cache: dict) -> bool:
    """影子双算开关：环境变量强制 1/0，否则未达一致次数前保持开启。"""
    env = os.environ.get("DOC_DRIFT_SNAPSHOT_SHADOW")
    if env == "1":
        return True
    if env == "0":
        return False
    try:
        return int(cache.get("shadow_ok", 0)) < _SHADOW_MATCHES_NEEDED
    except (TypeError, ValueError):
        return True


def _collect_test_snapshot(full_buckets: bool = False) -> dict[str, int]:
    """`collect-test-coverage.py` 快照 → ``{标记/名称: 数量}``（含 ``_总收集``）。

    **按文件增量（质量前提：只省「输入字节未变」的重复）**：
      - 共享语境（conftest / pytest 配置 / 业务代码 / 收集逻辑）未变且测试文件无增删改
        → 逐文件计数直接求和，零子进程；
      - 仅测试文件变更 → 只对变更文件重收集（单次子进程），未变文件复用缓存计数；
      - 共享语境变化 / 缓存缺失损坏 / 子进程异常 → 整树全量收集（保守回退）。
    **影子双算**：增量与全量同时跑、以全量为准逐项比对，连续
    ``_SHADOW_MATCHES_NEEDED`` 次一致才停用影子（``DOC_DRIFT_SNAPSHOT_SHADOW=1/0``
    强制开/关）；不一致立即 stderr 告警并归零继续守门。**失败不回写**：子进程
    无输出/非零退出不更新缓存，下次仍真收集。``full_buckets=True``
    （`--with-test-count` 核对计数表）要求完整分组快照：状态干净且 full 块指纹
    有效才复用，否则真全量；全量失败返回空（调用方跳过计数表核对，不给残缺桶）。
    """
    logic = _logic_key()
    shared = _shared_signature()
    cache = _read_snapshot_state()
    files = _current_test_files()
    sigs = {rel: _file_signature(p) for rel, p in files.items()}
    store: dict[str, dict] = cache.get("files") if cache else {}
    shared_ok = bool(cache) and cache.get("shared") == shared
    if not shared_ok:
        store = {}
    changed = [rel for rel in sigs if store.get(rel, {}).get("sig") != sigs[rel]]
    full_block = cache.get("full") if isinstance(cache.get("full"), dict) else None
    block_valid = isinstance(full_block, dict) and full_block.get("signature") == _snapshot_signature()

    # ── 快路径：共享未变且无测试文件改动（仅删除时按现存文件求和并回写剔除）──
    if shared_ok and not changed:
        if set(store) != set(sigs):
            store = {rel: store[rel] for rel in sigs}
            _write_snapshot_state({**cache, "files": store})
        total = sum(int(store[rel].get("total", 0)) for rel in sigs)
        if not full_buckets:
            return {"_总收集": total}
        if block_valid:
            try:
                return {str(k): int(v) for k, v in full_block["snapshot"].items()}
            except (TypeError, ValueError, KeyError):
                pass  # full 块损坏 → 落到下方全量
        # 块指纹失效/损坏 → 全量重取分组桶

    # ── 需要真收集：变更文件先增量，影子/full_buckets/增量不可用时叠加全量 ──
    incremental_possible = shared_ok and bool(changed)
    inc: tuple[dict[str, int], dict[str, int]] | None = _run_collect(changed) if incremental_possible else None
    if inc is not None and any(rel not in inc[1] for rel in changed):
        inc = None  # 逐文件输出缺变更文件 → 增量不可信，回退全量
    shadow = _shadow_active(cache)
    need_full = not incremental_possible or inc is None or full_buckets or shadow
    full: tuple[dict[str, int], dict[str, int]] | None = _run_collect([]) if need_full else None

    if inc is None and full is None:
        return {}  # 全部失败：不回写，下次仍真收集

    # 增量口径（影子比对用）：变更取增量、未变沿用缓存（删除自动剔除）
    inc_files: dict[str, dict] | None = None
    if inc is not None:
        inc_per = inc[1]
        inc_files = {
            rel: (
                {"sig": sigs[rel], "total": int(inc_per[rel])}
                if rel in inc_per
                else {"sig": sigs[rel], "total": int(store.get(rel, {}).get("total", 0))}
            )
            for rel in files
        }
    inc_total = sum(int(v["total"]) for v in inc_files.values()) if inc_files is not None else None

    prev_ok = 0
    try:
        prev_ok = int(cache.get("shadow_ok", 0)) if cache else 0
    except (TypeError, ValueError):
        prev_ok = 0
    shadow_ok = prev_ok

    if full is not None:
        snapshot, per_file_full = full
        # 权威状态以全量为准
        new_files = {rel: {"sig": sigs[rel], "total": int(per_file_full.get(rel, 0))} for rel in files}
        if shadow and inc_files is not None:
            full_total = snapshot.get("_总收集")
            per_file_ok = all(int(inc_files[rel]["total"]) == int(per_file_full.get(rel, 0)) for rel in changed)
            if full_total == inc_total and per_file_ok:
                shadow_ok = prev_ok + 1
            else:
                print(
                    f"[!] 收集增量与全量比对不一致（增量 {inc_total} / 全量 {full_total}），已回退全量并保持影子双算",
                    file=sys.stderr,
                )
                shadow_ok = 0
        _write_snapshot_state(
            {
                "format": _SNAPSHOT_FORMAT,
                "logic": logic,
                "shared": shared,
                "files": new_files,
                "full": {"signature": _snapshot_signature(), "snapshot": snapshot},
                "shadow_ok": shadow_ok,
            }
        )
        result = snapshot
    else:
        # 仅增量成功（全量未跑或失败）：以增量回写，full 块保留旧值（指纹自会失效）
        new_files = inc_files  # 上方已保证 inc 非 None
        _write_snapshot_state(
            {
                "format": _SNAPSHOT_FORMAT,
                "logic": logic,
                "shared": shared,
                "files": new_files,
                "full": cache.get("full"),
                "shadow_ok": prev_ok,
            }
        )
        result = {"_总收集": inc_total}

    if full_buckets and full is None:
        return {}  # 分组桶必须来自成功全量：残缺桶会误报计数表
    return result
