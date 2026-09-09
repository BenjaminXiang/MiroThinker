from __future__ import annotations

import httpx

from src.data_agents.paper.homepage_http import fetch_homepage_html


def test_fetch_with_injected_client_follows_redirect_to_final_homepage_content() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url == "https://faculty.hitsz.edu.cn/hedaojing":
            return httpx.Response(
                301,
                headers={"Location": "https://homepage.hit.edu.cn/hedaojing"},
                request=request,
            )
        if url == "https://homepage.hit.edu.cn/hedaojing":
            return httpx.Response(
                200,
                text="<html><title>何道敬 - 哈尔滨工业大学教师个人主页</title></html>",
                request=request,
            )
        raise AssertionError(f"unexpected request: {url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    html = fetch_homepage_html(
        "https://faculty.hitsz.edu.cn/hedaojing",
        http_client=client,
    )

    assert requests == [
        "https://faculty.hitsz.edu.cn/hedaojing",
        "https://homepage.hit.edu.cn/hedaojing",
    ]
    assert "何道敬 - 哈尔滨工业大学教师个人主页" in html
