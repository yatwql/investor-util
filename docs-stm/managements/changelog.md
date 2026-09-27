# 变更日志

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

> **最近发布 [0.11.6]**（2026-09-26）——已发布版本段随发布移入 [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md)；本文件只保留当前开发版本段与归档索引。

---

## [0.11.7-dev] - 开发中（未发布）

> 本轮开发开始后逐条追加变更记录；发布时本段头改为 `## [x.y.z] - YYYY-MM-DD`。

### 缺陷修复：`requirements.txt` 加 UTF-8 BOM（中文 Windows 上装依赖中断，rf-457）

**现象**（另一台 Windows 机实测报障）：`launch.ps1` 走到「正在安装依赖 ...」后抛 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xac in position 225: illegal multibyte sequence`（栈顶 `pip/_internal/utils/encoding.py::auto_decode`），虚拟环境依赖装不上、启动中断。

**根因**：plan-50 给 `requirements.txt` 的 `pdfplumber` / `Pillow` 两行追加中文注释，文件保持 UTF-8 **无 BOM**；中文 Windows 的 locale 是 cp936，pip ≤24.x 的解码次序为「BOM → PEP263 cookie → locale 编码」，前两档均无 → 回退 cp936 解码 UTF-8 字节 → `0xac` 非法。本机 Linux 与 CI 同为 UTF-8 locale，pip ≥25 起更已默认 UTF-8（新版连该模块都已移除），故该缺陷只在「旧 pip + 非 UTF-8 locale」组合上暴露，P0 门禁全绿拦不住。

**变更**：
- `requirements.txt`：加 UTF-8 BOM（`EF BB BF`）——pip 任意版本的 `BOMS` 判定优先于 locale 回退；实测 pip 25.1.1 `_decode_req_file` 与 pip 24.3.1 `auto_decode`（强制 cp936）均正常解析、BOM 不污染首行、中文注释保留
- `.editorconfig`：新增 `[requirements.txt] charset = utf-8-bom`（默认 `[*] charset = utf-8` 会让编辑器保存时剥掉 BOM，必须显式覆盖）
- `CLAUDE.md`：编码/BOM 约定补 `requirements.txt` 条目与成因
- 回归用例 +3（`test_script_encoding.py::TestRequirementsFileEncoding`）：非 ASCII 内容必须带 BOM；复刻 pip ≤24 解码次序并在强制 cp936 下断言与 UTF-8 直读一致（**去 BOM 即复现 `'gbk' codec can't decode byte 0xac`**，已验证）；BOM 仅允许作文件头
- `folders.md`：`.editorconfig` 与 `test_script_encoding.py` 两处说明同步

**验证**：回归用例双向验证（去 BOM → `TestRequirementsFileEncoding` 两条用例复现 `'gbk' codec can't decode byte 0xac`；带 BOM → 全绿）；真实旧 pip 端到端：`pip==24.3.1` 在 `LC_ALL=C` 下 `pip install --dry-run -r requirements.txt` 带 BOM 正常解析、去 BOM 即 `UnicodeDecodeError`；`dev-verify` 3309 passed / 0 failed；7 个 `--ci` 守护脚本全 `[OK]`。

**用户侧**：那台机器下次 `launch.ps1` 会因 `requirements.txt` 的 SHA256 变化而重跑 `pip install`，BOM 生效后即可装上；若其他旧 venv 仍报同类错，可先 `python -m pip install -U pip`，或临时 `$env:PYTHONUTF8=1` 应急。

### 系统性护栏：非 UTF-8 locale / 隐式编码门禁（rf-458）

**背景**（用户质问「两个系统的基本要求不是会覆盖的吗」）：上面的缺陷暴露的不是单点疏漏，而是**测试面盲区**——本机与 CI 全部跑在 UTF-8 locale 上（CI 三个 job 均为 `ubuntu-latest`，无 Windows runner），而该缺陷只在「旧 pip + 非 UTF-8 locale（cp936）」组合下出现；UTF-8 locale 下 pip 的最后一档回退恰好就是 UTF-8，因此 3309 条 `dev-verify` 全绿也拦不住。顺这条线排查出同源暴露面：生产代码 1 处（`report/excel_writer.py` 输出目录可写性探针）、测试代码 8 文件 24 处未显式 `encoding=` 的文本 I/O（`open`/`write_text`/`subprocess.run(text=True)`）。

**变更**：
- **CI 新增阻塞 job `portability`**（两道探针，均可在任意平台本地复现，不依赖 Windows runner 或安装 GB18030）：① 固定 `pip==24.3.1` + `LC_ALL=C`/`PYTHONCOERCECLOCALE=0`/`PYTHONUTF8=0` 真实 `pip install --dry-run --no-deps -r requirements.txt`——本地已双向验证（带 BOM 正常解析、去掉 BOM 即复现 `UnicodeDecodeError`）；② `PYTHONWARNDEFAULTENCODING=1` 跑 `src/test/unit` 全量（PEP 597 隐式编码严格档）
- **`pytest.ini`**：新增 `filterwarnings = error::EncodingWarning` + `openpyxl.worksheet._writer` 豁免（上游 `NamedTemporaryFile(mode='w+')` 未传 encoding；写/读共用同一 codec、zip 条目仍为 UTF-8，实测无用户可见影响——刻意豁免与 ruff 豁免同风格，就地显式声明）
- **修复**：`report/excel_writer.py` 可写性探针改二进制模式（`open(..., "ab")`）；测试 8 文件 24 处补 `encoding="utf-8"`（含 2 处 `subprocess.run(text=True)`），全部由严格档跑绿
- **文档**：`CLAUDE.md` 编码纪律从「Windows 脚本」泛化为按消费方表达（非 ASCII + 被 locale 回退型工具读取 ⇒ 必须 BOM）并禁止隐式编码；`developer-guide.md` 新增「编码/locale 自检」段（含**为何不用 Windows runner**——en-US/cp1252 单字节只乱码不报错；**为何不跑全套件换 locale**——POSIX `fsencoding=ascii` 下中文文件名会失败，属探测伪影）；`testplan.md` §6.4 新增第 17 项门禁；`folders.md` 同步 `pytest.ini` 说明

**探测方法纠偏（留证）**：`LC_ALL=C` 全套件初跑报 47 处失败，逐条定位后确认其中 18 处为 POSIX `fsencoding=ascii` 无法编码中文**文件名**的伪影（cp936 Windows 侧正常），另有 31 处来自 openpyxl 内部 tempfile 的上游隐式编码——最终采用「精确模拟消费方」的两道探针，而非「换整套 locale」的粗探针。

**验证**：严格档单元套件 7597 passed / 0 failed（修复前 78 failed）；`dev-verify` 3309 passed / 0 failed；7 个 `--ci` 守护脚本全 `[OK]`；`ruff check` + `ruff format --check` 零告警。

### CI 首次运行暴露的既存测试隔离缺陷（rf-459）

**现象**：新增 `portability` job 首轮（e083c1cc）与第二轮（b61a7a5f）均在「隐式编码严格档」步失败（其余 5 个 job 与旧 pip 探针均绿），而本机同命令全绿。借助新增的 workflow annotation 机制从 checks API 取到失败用例（日志端点需授权）：`test_cli_edge.py::TestCliEdge::test_no_input_in_report_path`（`generate_report` 未被调用）与 `test_cli.py::TestHandleWhatif::test_effective_date_passthrough`（`assert 2 == 0`）。

**根因（与编码无关，为既存隔离泄漏被新 job 翻出）**：
- **mock 打错调用点**：前者的 `patch("...cli._cli_read_holdings")` 与实际被调用的 `_cli_read_holdings_with_flows` 不是同一个函数；后者只 stub 了目标持仓的 `read_holdings`，基准持仓走未 stub 的 `_cli_read_holdings`。二者双双静默回退到**真实文件读取**，仅当开发机存在 `data/holdings/个人投资持仓信息.xlsx` 时才「恰好绿」——把该目录临时移走后**不带严格档也失败**（已实测），干净 clone 下日志即 `cli.py:323 持仓文件不存在`
- **CI 选择口径缺席**：`dev-verify` 的 marker 表达式为 `(unit_core or unit_providers or unit_fetcher or unit_analysis or unit_scripts or unit_web) and not (edge or data)`，`verify` 亦不含 `unit_cli` → 这两条在 CI 上**从未运行过**；新 job 无过滤跑完整 `src/test/unit`，首次在清洁树上暴露

**变更**：两条用例改为 patch 真实调用点（`_cli_read_holdings_with_flows` 返回 `(holdings, [], [])`；whatif 用例补 `_cli_read_holdings` stub）并就地注释该陷阱；`ci.yml` 的严格档步骤对调至 pip 降级之前，并在失败时输出 `::error::` workflow annotation（annotations 可免授权从 checks API 读取，无日志权限也能定位）。

**验证**：本机（有真实 `data/holdings/`）与临时移走该目录后均全绿；清洁树（`git archive HEAD` + 修复后的两份测试，无 `data/holdings/`）严格档整轮单元套件仅剩 `folders.md` 统计自洽项（同步后消失）。**副产物**：`portability` job 自此实际承担「清洁树 + 全量单元（含 `unit_cli` / `edge`）」的隔离回归。

### 文档核对：FAQ/自检段/描述同步（rf-460）

**背景**（用户要求核对管理文档与用户文档）：rf-457~rf-459 三批变更落地后，逐份比对 10 份管理文档 + 11 份用户文档 + `CLAUDE.md`，发现 4 处未同步：

**变更**：
- `faq.md`「启动与安装」新增问答：中文 Windows 装依赖报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xac ...`（根因：旧版 `requirements.txt` 中文注释无 BOM + pip ≤24.x + cp936）——三档解法（首选 `git pull` 拉 BOM 修复版 / `pip install -U pip` 升 ≥25 / 临时 `$env:PYTHONUTF8=1`）+ 预防说明（CI `portability` 门禁）
- `developer-guide.md`「编码/locale 自检」补 PEP 668 注意：①号命令在系统级管理解释器上会被拒，本机复现请装进临时 venv 或追加 `--break-system-packages`（`--dry-run` 无实际安装风险）
- `test-coverage.md`：`unit_scripts` 标记描述补「编码与 locale 自检（requirements.txt BOM 约定 + 复刻旧 pip 解码次序 + PEP 597 严格档豁免）」
- `folders.md`：目录树 `ci.yml` 描述补「P0/P1/P2 三级门禁 + guards/portability/format 三个独立 job」

**核对无偏差项**（顺带确认）：CI job 计数表述（`guards`/`portability`/`format` 三处一致）、版本一致性 13/13、pytest.ini 引用、`requirements.txt` BOM 引用口径、review-findings 编号源与待办/已解决分区、dev-verify 验证记录。

---

## 归档

- [`archived_changelog.0.11.x.md`](../archive/v0.11.x/archived_changelog.0.11.x.md) — v0.11.0 ~ v0.11.6（2026-09-15 ~ 2026-09-26）
- [`archived_changelog.0.10.x.md`](../archive/v0.10.x/archived_changelog.0.10.x.md) — v0.10.1 ~ v0.10.19（2026-08-04 ~ 2026-09-13）
- [`archived_changelog.0.9.x.md`](../archive/v0.9.x/archived_changelog.0.9.x.md) — v0.9.0 ~ v0.9.12（2026-07-30 ~ 2026-08-03）
- [`archived_changelog.0.8.x.md`](../archive/v0.8.x/archived_changelog.0.8.x.md) — v0.8.0 ~ v0.8.11（2026-07-21 ~ 2026-07-30）
- [`archived_changelog.0.7.x.md`](../archive/v0.7.x/archived_changelog.0.7.x.md) — v0.7.0 ~ v0.7.9（2026-07-18 ~ 2026-07-21）
- [`archived_changelog.0.6.x.md`](../archive/v0.6.x/archived_changelog.0.6.x.md) — v0.6.0 ~ v0.6.10（2026-07-15 ~ 2026-07-18）
- [`archived_changelog.0.5.x.md`](../archive/v0.5.x/archived_changelog.0.5.x.md) — v0.5.0 ~ v0.5.12（2026-07-14 ~ 2026-07-15）
- [`archived_changelog.0.4.x.md`](../archive/v0.4.x/archived_changelog.0.4.x.md) — v0.4.0 ~ v0.4.5（2026-07-12 ~ 2026-07-14）
- [`archived_changelog.0.3.x.md`](../archive/v0.3.x/archived_changelog.0.3.x.md) — v0.3.0 ~ v0.3.10（2026-07-08 ~ 2026-07-12）
- [`archived_changelog.0.2.x.md`](../archive/v0.2.x/archived_changelog.0.2.x.md) — v0.2.0 ~ v0.2.91（2026-06-27 ~ 2026-07-08）
- [`archived_changelog.0.1.x.md`](../archive/v0.1.x/archived_changelog.0.1.x.md) — 早期版本记录
