"""live 真实网络验证套件（opt-in）。

用途：在需要排查「数据源是否真的可达 / API 是否漂移」时，手工运行
`python scripts/test-runner.py --mode live`（或 `pytest -m live`）验证真实
数据源/LLM API 连通性与返回结构。

设计约束（与门禁测试严格隔离）：
- 全部带 @pytest.mark.live，conftest 默认跳过（`-m not live` addopts + autouse skip），
  不进入 dev-verify / verify / all 等任何门禁
- 断言只校验「结构」（字段存在、类型、非空），不校验具体数值，容忍行情波动
- 不含 LLM 真实调用（防费用），LLM 连通性由运行时健康检查覆盖
"""
