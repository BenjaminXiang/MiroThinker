from __future__ import annotations

from src.data_agents.professor.publish_helpers import is_official_url


def test_is_official_url_treats_uestc_subdomains_as_official_by_default() -> None:
    assert is_official_url(
        "https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/10364?yxsh=28"
    )
    assert is_official_url("https://www.uestc.edu.cn/")
