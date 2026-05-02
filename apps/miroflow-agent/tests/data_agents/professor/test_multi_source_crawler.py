from __future__ import annotations

import pytest

from src.data_agents.professor.multi_source_crawler import follow_supplementary_links


def test_follows_group_website_anchor():
    main_html = """
    <html><body>
      <a href="/group/index.html">Group Website</a>
    </body></html>
    """
    pages = {
        "https://faculty.example.edu/group/index.html": (
            "<html><body><main>Robotics group research on tactile sensing.</main></body></html>"
        )
    }

    segments = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        fetch_html_fn=lambda url, _timeout: pages[url],
    )

    assert len(segments) == 1
    assert "Robotics group research" in segments[0]
    assert "https://faculty.example.edu/group/index.html" in segments[0]


def test_follows_cv_pdf_link():
    main_html = """
    <html><body>
      <a href="/files/zhang-cv.pdf">CV PDF</a>
    </body></html>
    """

    segments = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        fetch_pdf_fn=lambda url, _timeout: f"Parsed PDF from {url}",
    )

    assert segments == [
        "Source: https://faculty.example.edu/files/zhang-cv.pdf\n"
        "Parsed PDF from https://faculty.example.edu/files/zhang-cv.pdf"
    ]


def test_respects_2_hop_depth_limit():
    main_html = '<a href="/lab/">Lab</a>'
    pages = {
        "https://faculty.example.edu/lab/": """
            <html><body>
              <p>Lab overview text.</p>
              <a href="/lab/people/zhang.html">张三</a>
            </body></html>
        """,
        "https://faculty.example.edu/lab/people/zhang.html": (
            "<html><body>Professor Zhang detailed group bio.</body></html>"
        ),
    }

    one_hop = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        professor_name="张三",
        max_hops=1,
        fetch_html_fn=lambda url, _timeout: pages[url],
    )
    two_hop = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        professor_name="张三",
        max_hops=2,
        fetch_html_fn=lambda url, _timeout: pages[url],
    )

    assert len(one_hop) == 1
    assert len(two_hop) == 2
    assert "Professor Zhang detailed group bio" in two_hop[1]


def test_skips_external_unrelated_domains():
    main_html = """
    <html><body>
      <a href="https://news.example.com/page.html">External news</a>
      <a href="https://scholar.google.com/profile">Scholar</a>
    </body></html>
    """
    fetched: list[str] = []

    segments = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        fetch_html_fn=lambda url, _timeout: fetched.append(url) or "",
    )

    assert segments == []
    assert fetched == []


def test_handles_pdf_parse_error_gracefully():
    main_html = '<a href="/files/resume.pdf">个人简历</a>'

    def _boom(_url: str, _timeout: float) -> str:
        raise RuntimeError("encrypted pdf")

    segments = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        fetch_pdf_fn=_boom,
    )

    assert segments == []


def test_caps_raw_text_segments():
    main_html = '<a href="/group/">Group Website</a>'
    segments = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        raw_text_cap=50,
        fetch_html_fn=lambda _url, _timeout: (
            "<html><body>" + "A" * 200 + "</body></html>"
        ),
    )

    assert len("".join(segments)) == 50


@pytest.mark.parametrize(
    ("anchor", "href"),
    [
        ("Group Website", "https://faculty.example.edu/group/"),
        ("课题组", "https://faculty.example.edu/team/"),
        ("Lab", "https://faculty.example.edu/lab/"),
    ],
)
def test_group_lab_anchor_variants(anchor: str, href: str):
    main_html = f'<a href="{href}">{anchor}</a>'
    segments = follow_supplementary_links(
        main_html,
        "https://faculty.example.edu/prof.html",
        fetch_html_fn=lambda _url, _timeout: "<html><body>Group text.</body></html>",
    )

    assert segments
