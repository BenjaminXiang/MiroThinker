"""RED-phase tests for M2.4 Unit 5 — homepage HTTP fetcher.

Sync helper that fetches a single prof homepage URL with trust_env=False and
a per-host rate-limit gate (0.5s). Hermetic tests only.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.data_agents.paper.homepage_http import (
    _DEFAULT_HOMEPAGE_TIMEOUT,
    _HOST_FETCH_GATE_SECONDS,
    _reset_host_gate_for_test,
    fetch_homepage_html,
)

# Capture real class references BEFORE any test patch runs (M0.1 learning).
_REAL_HTTPX_CLIENT = httpx.Client
_REAL_HTTPX_RESPONSE = httpx.Response


@pytest.fixture(autouse=True)
def _reset_gate():
    """Each test starts with a clean rate-limit dict."""
    _reset_host_gate_for_test()
    yield
    _reset_host_gate_for_test()


def _mock_response(
    text: str,
    *,
    status: int = 200,
    encoding: str | None = "utf-8",
    url: str | None = None,
):
    resp = MagicMock(spec=_REAL_HTTPX_RESPONSE)
    resp.text = text
    resp.content = text.encode("utf-8")
    resp.status_code = status
    resp.encoding = encoding
    resp.url = url
    if 200 <= status < 300:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status}", request=MagicMock(), response=MagicMock(status_code=status)
        )
    return resp


def _fake_client(response):
    client = MagicMock(spec=_REAL_HTTPX_CLIENT)
    client.get.return_value = response
    client.trust_env = False
    return client


def test_fetch_returns_text_on_200():
    http = _fake_client(_mock_response("<html><body>hi</body></html>"))
    result = fetch_homepage_html("https://example.edu/prof", http_client=http)
    assert "<html>" in result
    assert "hi" in result


def test_fetch_raises_on_404():
    http = _fake_client(_mock_response("", status=404))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_homepage_html("https://example.edu/missing", http_client=http)


def test_fetch_raises_on_500():
    http = _fake_client(_mock_response("server error", status=500))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_homepage_html("https://example.edu/broken", http_client=http)


def test_fetch_uses_response_text_when_encoding_known():
    """If response.encoding is set, use response.text directly."""
    http = _fake_client(_mock_response("UTF-8 body ✓", encoding="utf-8"))
    result = fetch_homepage_html("https://example.edu/p", http_client=http)
    assert "UTF-8 body" in result


def test_fetch_owned_client_uses_trust_env_false_and_follow_redirects():
    with patch("src.data_agents.paper.homepage_http.httpx.Client") as ClientCls:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.return_value = _mock_response("<html></html>")
        ClientCls.return_value = owned
        fetch_homepage_html("https://example.edu/prof")
        _, kwargs = ClientCls.call_args
        assert kwargs.get("trust_env") is False
        assert kwargs.get("follow_redirects") is True
        assert kwargs.get("timeout") == _DEFAULT_HOMEPAGE_TIMEOUT


def test_fetch_owned_client_falls_back_to_proxy_free_curl_on_transport_error():
    with patch("src.data_agents.paper.homepage_http.httpx.Client") as ClientCls, patch(
        "subprocess.run"
    ) as run:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.side_effect = httpx.ConnectError("tls handshake failed")
        ClientCls.return_value = owned
        run.return_value = CompletedProcess(
            args=["curl"], returncode=0, stdout="<html>curl body</html>", stderr=""
        )

        result = fetch_homepage_html("https://mypage.cuhk.edu.cn/academics/wuliang/")

    assert result == "<html>curl body</html>"
    curl_args = run.call_args.args[0]
    curl_env = run.call_args.kwargs["env"]
    assert curl_args[:2] == ["curl", "--silent"]
    assert "--location" in curl_args
    assert "--insecure" not in curl_args
    assert curl_args[-1] == "https://mypage.cuhk.edu.cn/academics/wuliang/"
    assert not {
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "all_proxy",
    }.intersection(curl_env)


def test_fetch_owned_client_does_not_fallback_to_curl_on_http_status_error():
    with patch("src.data_agents.paper.homepage_http.httpx.Client") as ClientCls, patch(
        "subprocess.run"
    ) as run:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.return_value = _mock_response("", status=404)
        ClientCls.return_value = owned

        with pytest.raises(httpx.HTTPStatusError):
            fetch_homepage_html("https://example.edu/missing")

    run.assert_not_called()


def test_fetch_owned_client_falls_back_to_professor_fetch_on_anti_scraping_status():
    with patch("src.data_agents.paper.homepage_http.httpx.Client") as ClientCls, patch(
        "src.data_agents.paper.homepage_http._fetch_homepage_html_with_professor_fallback"
    ) as fallback:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.return_value = _mock_response("precondition failed", status=412)
        ClientCls.return_value = owned
        fallback.return_value = "<html>reader body</html>"

        result = fetch_homepage_html("https://blocked.example.edu/profile?id=1187")

    assert result == "<html>reader body</html>"
    fallback.assert_called_once_with(
        "https://blocked.example.edu/profile?id=1187",
        fallback_exc=owned.get.return_value.raise_for_status.side_effect,
    )


def test_fetch_owned_client_fast_fails_known_unproductive_anti_scraping_page():
    with patch("src.data_agents.paper.homepage_http.httpx.Client") as ClientCls, patch(
        "src.data_agents.paper.homepage_http._fetch_homepage_html_with_professor_fallback"
    ) as fallback:
        owned = MagicMock(spec=_REAL_HTTPX_CLIENT)
        owned.get.return_value = _mock_response("precondition failed", status=412)
        ClientCls.return_value = owned

        with pytest.raises(httpx.HTTPStatusError):
            fetch_homepage_html("https://csse.szu.edu.cn/pages/user/index?id=1187")

    fallback.assert_not_called()


def test_fetch_hit_homepage_appends_dynamic_teacher_body_from_json_wrapped_html():
    static_html = (
        '<html><body><div data-tid="12345" data-version-id="v9">'
        "Static profile</div></body></html>"
    )
    body_html = "<section><h2>Publications</h2><p>Dynamic HIT paper</p></section>"
    http = _fake_client(
        _mock_response(static_html, url="https://homepage.hit.edu.cn/teacher/12345")
    )
    http.post.return_value = _mock_response(json.dumps(body_html))

    result = fetch_homepage_html("https://homepage.hit.edu.cn/teacher/12345", http_client=http)

    assert "Static profile" in result
    assert "Dynamic HIT paper" in result
    http.post.assert_called_once()
    post_url = http.post.call_args.args[0]
    post_kwargs = http.post.call_args.kwargs
    assert post_url == "https://homepage.hit.edu.cn/TeacherHome/teacherBody.do"
    assert post_kwargs["data"] == {"id": "12345", "versionId": "v9"}
    assert "application/x-www-form-urlencoded" in post_kwargs["headers"]["Content-Type"]


def test_fetch_hit_homepage_uses_https_teacher_body_endpoint_for_http_profile():
    static_html = '<html><body><div data-tid="12345">Static</div></body></html>'
    http = _fake_client(
        _mock_response(static_html, url="http://homepage.hit.edu.cn/teacher/12345")
    )
    http.post.return_value = _mock_response("<section>HTTPS dynamic body</section>")

    result = fetch_homepage_html("http://homepage.hit.edu.cn/teacher/12345", http_client=http)

    assert "HTTPS dynamic body" in result
    assert http.post.call_args.args[0] == (
        "https://homepage.hit.edu.cn/TeacherHome/teacherBody.do"
    )


def test_fetch_hit_homepage_uses_final_response_url_host_for_dynamic_body():
    static_html = '<html><body><div data-tid="redirected">Static</div></body></html>'
    http = _fake_client(
        _mock_response(static_html, url="https://homepage.hit.edu.cn/teacher/redirected")
    )
    http.post.return_value = _mock_response("<section>Redirect dynamic body</section>")

    result = fetch_homepage_html("https://example.edu/redirect", http_client=http)

    assert "Redirect dynamic body" in result
    assert http.post.call_args.args[0] == (
        "https://homepage.hit.edu.cn/TeacherHome/teacherBody.do"
    )
    assert http.post.call_args.kwargs["data"] == {"id": "redirected"}


def test_fetch_does_not_post_dynamic_body_for_non_hit_hosts():
    static_html = '<html><body><div data-tid="12345">Static</div></body></html>'
    http = _fake_client(_mock_response(static_html, url="https://example.edu/prof"))

    result = fetch_homepage_html("https://example.edu/prof", http_client=http)

    assert result == static_html
    http.post.assert_not_called()


def test_fetch_does_not_post_dynamic_body_for_hit_pages_without_data_tid():
    static_html = "<html><body>Static HIT profile without dynamic id</body></html>"
    http = _fake_client(
        _mock_response(static_html, url="https://homepage.hit.edu.cn/teacher/no-tid")
    )

    result = fetch_homepage_html("https://homepage.hit.edu.cn/teacher/no-tid", http_client=http)

    assert result == static_html
    http.post.assert_not_called()


def test_fetch_sustech_faculty_js_redirect_stub_refetches_resolved_page():
    stub_html = """
        <html><head><script>
        var url = "tagid=xingxy&iscss=1&snapid=1&orderby=date&lang=zh&go=2";
        window.location.href="/?"+url;
        </script></head></html>
    """
    final_url = (
        "https://faculty.sustech.edu.cn/"
        "?tagid=xingxy&iscss=1&snapid=1&orderby=date&lang=zh&go=2"
    )
    final_html = "<html><body><h1>邢小玉</h1><h2>成果</h2></body></html>"
    http = _fake_client(
        _mock_response(stub_html, url="https://faculty.sustech.edu.cn/xingxy")
    )
    http.get.side_effect = [
        _mock_response(stub_html, url="https://faculty.sustech.edu.cn/xingxy"),
        _mock_response(final_html, url=final_url),
    ]

    result = fetch_homepage_html("http://faculty.sustech.edu.cn/xingxy", http_client=http)

    assert result == final_html
    assert [call.args[0] for call in http.get.call_args_list] == [
        "http://faculty.sustech.edu.cn/xingxy",
        final_url,
    ]


def test_fetch_sustech_faculty_js_redirect_stub_stops_on_self_redirect():
    current_url = (
        "https://faculty.sustech.edu.cn/"
        "?tagid=xingxy&iscss=1&snapid=1&orderby=date&lang=zh&go=2"
    )
    stub_html = """
        <html><head><script>
        var url = "tagid=xingxy&iscss=1&snapid=1&orderby=date&lang=zh&go=2";
        window.location.href="/?"+url;
        </script></head></html>
    """
    http = _fake_client(_mock_response(stub_html, url=current_url))
    http.get.side_effect = [_mock_response(stub_html, url=current_url)]

    result = fetch_homepage_html(current_url, http_client=http)

    assert result == stub_html
    assert [call.args[0] for call in http.get.call_args_list] == [current_url]


def test_fetch_sustech_faculty_js_redirect_stub_requires_exact_host():
    stub_html = """
        <html><head><script>
        var url = "tagid=xingxy&iscss=1&snapid=1&orderby=date&lang=zh&go=2";
        window.location.href="/?"+url;
        </script></head></html>
    """
    suspicious_url = "https://faculty.sustech.edu.cn.evil.example/xingxy"
    http = _fake_client(_mock_response(stub_html, url=suspicious_url))
    http.get.side_effect = [_mock_response(stub_html, url=suspicious_url)]

    result = fetch_homepage_html(suspicious_url, http_client=http)

    assert result == stub_html
    assert [call.args[0] for call in http.get.call_args_list] == [suspicious_url]


def test_fetch_hit_dynamic_body_json_object_without_html_is_ignored():
    static_html = '<html><body><div data-tid="12345">Static HIT profile</div></body></html>'
    http = _fake_client(
        _mock_response(static_html, url="https://homepage.hit.edu.cn/teacher/12345")
    )
    http.post.return_value = _mock_response(json.dumps({"msg": "sql error"}))

    result = fetch_homepage_html("https://homepage.hit.edu.cn/teacher/12345", http_client=http)

    assert result == static_html


def test_fetch_hit_dynamic_body_failure_is_non_fatal(caplog):
    static_html = '<html><body><div data-tid="12345">Static HIT profile</div></body></html>'
    http = _fake_client(
        _mock_response(static_html, url="https://homepage.hit.edu.cn/teacher/12345")
    )
    http.post.side_effect = httpx.ConnectError("dynamic endpoint unavailable")

    with caplog.at_level(logging.WARNING, logger="src.data_agents.paper.homepage_http"):
        result = fetch_homepage_html(
            "https://homepage.hit.edu.cn/teacher/12345",
            http_client=http,
        )

    assert result == static_html
    assert "Failed to fetch HIT dynamic teacher body" in caplog.text


def test_fetch_passes_url_to_get():
    http = _fake_client(_mock_response("<html></html>"))
    fetch_homepage_html("https://example.edu/prof/doe", http_client=http)
    url_arg = http.get.call_args[0][0]
    assert url_arg == "https://example.edu/prof/doe"


# --- per-host rate-limit gate ---


def test_fetch_rate_limits_same_host():
    """Two calls to same host: second waits ≥ 0.5s after first."""
    http = _fake_client(_mock_response("<html></html>"))
    t0 = time.monotonic()
    fetch_homepage_html("https://example.edu/prof/a", http_client=http)
    fetch_homepage_html("https://example.edu/prof/b", http_client=http)
    elapsed = time.monotonic() - t0
    assert elapsed >= _HOST_FETCH_GATE_SECONDS


def test_fetch_does_not_rate_limit_across_different_hosts():
    """Two calls to different hosts should not wait for each other."""
    http = _fake_client(_mock_response("<html></html>"))
    t0 = time.monotonic()
    fetch_homepage_html("https://alpha.edu/prof/a", http_client=http)
    fetch_homepage_html("https://beta.edu/prof/b", http_client=http)
    elapsed = time.monotonic() - t0
    # Both calls should complete well under the 0.5s gate cumulatively.
    assert elapsed < _HOST_FETCH_GATE_SECONDS


def test_fetch_thread_safe_gate():
    """Concurrent callers against same host should serialize via lock."""
    http = _fake_client(_mock_response("<html></html>"))
    errors: list[Exception] = []

    def _call():
        try:
            fetch_homepage_html("https://concurrent.edu/prof", http_client=http)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_call) for _ in range(3)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    elapsed = time.monotonic() - t0
    assert errors == []
    # 3 serialized calls at 0.5s apart = at least 2 * 0.5 = 1.0s elapsed.
    assert elapsed >= _HOST_FETCH_GATE_SECONDS * 2 - 0.05  # small tolerance
