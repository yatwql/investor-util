"""CLI 命令行入口 — python -m src.python.cli。

与 ``python src/python/cli/cli.py`` 共用 ``run_cli()``：两条入口行为一致，
尤其是**退出码必须传给 shell**（脚本化调用依赖它判断成败）。
"""

from src.python.cli.cli import run_cli

if __name__ == "__main__":
    run_cli()
