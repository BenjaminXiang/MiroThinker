from __future__ import annotations

import json
from pathlib import Path

from src.data_agents.company.models import CompanyImportRecord

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_company_official_product_capture.py"
)


def _import_cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_company_official_product_capture", _SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_products_for_record_fetches_bounded_official_pages():
    cli = _import_cli()
    fetched: list[str] = []
    html_by_url = {
        "https://example.com": "<a href='/products'>产品中心</a>",
        "https://example.com/products": (
            "<section class='product-card'>"
            "<h2>工业视觉平台</h2>"
            "<p>面向产线质检的AI视觉检测产品。</p>"
            "</section>"
        ),
    }

    def fetch_html(url: str) -> str | None:
        fetched.append(url)
        return html_by_url.get(url)

    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    products = cli._capture_products_for_record(
        record,
        fetch_html=fetch_html,
        max_pages=2,
    )

    assert fetched == ["https://example.com", "https://example.com/products"]
    assert len(products) == 1
    assert products[0].product_name == "工业视觉平台"


def test_capture_official_materials_for_record_fetches_core_sections():
    cli = _import_cli()
    fetched: list[str] = []
    html_by_url = {
        "https://example.com": (
            "<p>示例科技官网展示工业视觉检测平台、解决方案和客户案例。</p>"
            "<a href='/about'>关于我们</a>"
            "<a href='/products'>产品中心</a>"
            "<a href='/solutions'>解决方案</a>"
            "<a href='/news'>新闻动态</a>"
        ),
        "https://example.com/about": "<title>关于示例科技</title><p>示例科技长期专注工业视觉检测平台研发，服务产线质检客户。</p>",
        "https://example.com/products": "<title>产品中心</title><p>工业视觉平台服务产线质检，提供缺陷识别和质量追溯能力。</p>",
        "https://example.com/solutions": "<title>解决方案</title><p>面向制造客户的质检方案，覆盖电子、汽车零部件等场景。</p>",
    }

    def fetch_html(url: str) -> str | None:
        fetched.append(url)
        return html_by_url.get(url)

    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    materials = cli._capture_official_materials_for_record(
        record,
        company_id="COMP-1",
        fetch_html=fetch_html,
        max_pages=3,
    )

    assert fetched == [
        "https://example.com",
        "https://example.com/about",
        "https://example.com/products",
    ]
    assert [material.source_tier for material in materials] == [
        "official_site",
        "official_site",
        "official_site",
    ]
    assert [material.url for material in materials] == [
        "https://example.com",
        "https://example.com/about",
        "https://example.com/products",
    ]


def test_capture_official_materials_uses_sitemap_when_navigation_has_no_links():
    cli = _import_cli()
    fetched: list[str] = []
    html_by_url = {
        "https://example.com": "<html><body><p>示例科技官网。</p></body></html>",
        "https://example.com/sitemap.xml": """
          <urlset>
            <url><loc>https://example.com/products/vision</loc></url>
            <url><loc>https://external.example.com/products</loc></url>
          </urlset>
        """,
        "https://example.com/products/vision": (
            "<title>工业视觉平台</title>"
            "<p>示例科技工业视觉平台服务产线质检，提供缺陷识别能力。</p>"
        ),
    }

    def fetch_html(url: str):
        fetched.append(url)
        return html_by_url.get(url)

    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    result = cli._capture_official_materials_with_diagnostics_for_record(
        record,
        company_id="COMP-1",
        fetch_html=fetch_html,
        max_pages=2,
    )

    assert fetched == [
        "https://example.com",
        "https://example.com/sitemap.xml",
        "https://example.com/products/vision",
    ]
    assert result.failure_reason is None
    assert [material.url for material in result.materials] == [
        "https://example.com/products/vision",
    ]
    assert any(
        attempt["acquisition_method"] == "sitemap"
        and attempt["url"] == "https://example.com/sitemap.xml"
        for attempt in result.attempts
    )


def test_capture_official_materials_records_http_status_and_robots_failures():
    cli = _import_cli()
    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    blocked = cli._capture_official_materials_with_diagnostics_for_record(
        record,
        company_id="COMP-1",
        fetch_html=lambda _url: cli.OfficialFetchResult(
            html="<html><body>Forbidden</body></html>",
            http_status=403,
            content_type="text/html",
        ),
        max_pages=2,
    )
    robots = cli._capture_official_materials_with_diagnostics_for_record(
        record,
        company_id="COMP-1",
        fetch_html=lambda _url: cli.OfficialFetchResult(
            html=None,
            robots_disallowed=True,
        ),
        max_pages=2,
    )

    assert blocked.failure_reason == "http_403"
    assert blocked.attempts[0]["http_status"] == 403
    assert blocked.attempts[0]["failure_reason"] == "http_403"
    assert robots.failure_reason == "robots_disallowed"
    assert robots.attempts[0]["robots_disallowed"] is True


def test_capture_official_materials_with_diagnostics_uses_rendered_spa_content():
    cli = _import_cli()
    fetched: list[str] = []
    rendered: list[str] = []
    html_by_url = {
        "https://example.com": (
            "<html><body><div id='app'>please enable JavaScript</div>"
            "<script src='/app.js'></script></body></html>"
        ),
    }

    def fetch_html(url: str) -> str | None:
        fetched.append(url)
        return html_by_url.get(url)

    def render_html(url: str) -> str | None:
        rendered.append(url)
        return (
            "<html><head><title>示例科技</title></head><body>"
            "<p>示例科技专注工业视觉检测平台，服务产线质检客户。</p>"
            "<a href='/products'>产品中心</a>"
            "</body></html>"
        )

    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    result = cli._capture_official_materials_with_diagnostics_for_record(
        record,
        company_id="COMP-1",
        fetch_html=fetch_html,
        render_html=render_html,
        max_pages=2,
    )

    assert fetched == ["https://example.com", "https://example.com/products"]
    assert rendered == ["https://example.com"]
    assert result.failure_reason is None
    assert result.materials[0].url == "https://example.com"
    assert result.attempts[0]["failure_reason"] == "js_required"
    assert result.attempts[1]["acquisition_method"] == "js_render"
    assert result.attempts[1]["status"] == "accepted"


def test_cli_dry_run_report_includes_official_capture_failures(monkeypatch, tmp_path):
    cli = _import_cli()
    output = tmp_path / "official-report.json"
    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    class _ImportResult:
        records = [record]

    monkeypatch.setattr(cli, "import_company_xlsx", lambda *_a, **_kw: _ImportResult())
    monkeypatch.setattr(cli, "_fetch_html", lambda *_a, **_kw: None)

    exit_code = cli.main(
        [
            "--dry-run",
            "--limit",
            "1",
            "--max-pages",
            "2",
            "--sleep-seconds",
            "0",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["official_pages_captured"] == 0
    assert report["official_capture_failures"] == [
        {
            "company_id": "COMP-示例科技",
            "company_name": "深圳示例科技有限公司",
            "website": "https://example.com",
            "failure_reason": "fetch_failed",
        }
    ]


def test_parse_args_accepts_dry_run_and_limit():
    cli = _import_cli()

    args = cli._parse_args(
        [
            "--dry-run",
            "--limit",
            "3",
            "--max-pages",
            "2",
            "--company-id",
            "COMP-1",
            "--enable-js-render",
            "--disable-sitemap-discovery",
            "--disable-common-path-discovery",
        ]
    )

    assert args.dry_run is True
    assert args.limit == 3
    assert args.max_pages == 2
    assert args.company_id == ["COMP-1"]
    assert args.enable_js_render is True
    assert args.disable_sitemap_discovery is True
    assert args.disable_common_path_discovery is True


def test_load_company_records_from_database_uses_canonical_company_ids():
    cli = _import_cli()

    class _Result:
        def fetchall(self):
            return [
                {
                    "company_id": "COMP-1",
                    "canonical_name": "深圳示例科技有限公司",
                    "normalized_name": "示例科技",
                    "industry": "人工智能",
                    "website": "https://example.com",
                }
            ]

    class _Conn:
        def __init__(self):
            self.calls = []

        def execute(self, query, params=None):
            self.calls.append((query, params))
            return _Result()

    conn = _Conn()

    records = cli._load_company_records_from_database(
        conn,
        company_ids=("COMP-1",),
        limit=10,
    )

    assert len(records) == 1
    record = records[0]
    assert record.company_id == "COMP-1"
    assert record.record.name == "深圳示例科技有限公司"
    assert record.record.website == "https://example.com"
    assert "company_id IN (%s)" in conn.calls[0][0]


def test_rewrite_products_with_canonical_company_id():
    cli = _import_cli()
    products = [
        cli.CompanyProductCandidate(
            company_id="COMP-示例科技",
            product_name="工业视觉平台",
            short_description="面向产线质检。",
            official_product_url="https://example.com/products",
            evidence_span="工业视觉平台 面向产线质检。",
            confidence="0.75",
        )
    ]

    rewritten = cli._rewrite_products_with_company_id(products, "COMP-CANONICAL")

    assert rewritten[0].company_id == "COMP-CANONICAL"
    assert rewritten[0].product_name == "工业视觉平台"


def test_cli_dry_run_report_includes_official_source_materials(monkeypatch, tmp_path):
    cli = _import_cli()
    output = tmp_path / "official-report.json"
    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    class _ImportResult:
        records = [record]

    html_by_url = {
        "https://example.com": (
            "<p>示例科技官网展示工业视觉检测平台、解决方案和客户案例。</p>"
            "<a href='/about'>关于我们</a>"
        ),
        "https://example.com/about": (
            "<title>关于示例科技</title>"
            "<p>示例科技长期专注工业视觉检测平台研发，服务产线质检客户。</p>"
        ),
    }

    monkeypatch.setattr(cli, "import_company_xlsx", lambda *_a, **_kw: _ImportResult())
    monkeypatch.setattr(
        cli,
        "_fetch_html",
        lambda url, **_kwargs: html_by_url.get(url),
    )

    exit_code = cli.main(
        [
            "--dry-run",
            "--limit",
            "1",
            "--max-pages",
            "2",
            "--sleep-seconds",
            "0",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["official_pages_captured"] == 2
    assert [item["source_tier"] for item in report["source_materials"]] == [
        "official_site",
        "official_site",
    ]
    assert report["source_materials"][0]["acquisition_method"] == "static"
    assert report["source_materials"][0]["source_judgment_status"] == "accepted"
    assert report["source_materials"][0]["source_judgment_confidence"] == "0.95"
    assert "工业视觉检测平台" in report["source_materials"][0]["evidence_span"]


def test_cli_dry_run_extracts_products_from_diagnostic_sitemap_pages(
    monkeypatch,
    tmp_path,
):
    cli = _import_cli()
    output = tmp_path / "official-report.json"
    record = CompanyImportRecord(
        name="深圳示例科技有限公司",
        normalized_name="示例科技",
        industry="人工智能",
        website="https://example.com",
    )

    class _ImportResult:
        records = [record]

    html_by_url = {
        "https://example.com": "<html><body><p>示例科技官网。</p></body></html>",
        "https://example.com/sitemap.xml": """
          <urlset>
            <url><loc>https://example.com/products/vision</loc></url>
          </urlset>
        """,
        "https://example.com/products/vision": (
            "<section class='product-card'>"
            "<h2>工业视觉平台</h2>"
            "<p>面向产线质检的AI视觉检测产品。</p>"
            "</section>"
        ),
    }

    monkeypatch.setattr(cli, "import_company_xlsx", lambda *_a, **_kw: _ImportResult())
    monkeypatch.setattr(
        cli,
        "_fetch_html",
        lambda url, **_kwargs: html_by_url.get(url),
    )

    exit_code = cli.main(
        [
            "--dry-run",
            "--limit",
            "1",
            "--max-pages",
            "2",
            "--sleep-seconds",
            "0",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["official_pages_captured"] == 1
    assert report["products_extracted"] == 1
    assert report["items"][0]["product_name"] == "工业视觉平台"
    assert report["items"][0]["official_product_url"] == (
        "https://example.com/products/vision"
    )


def test_cli_dry_run_with_company_id_does_not_persist_products(monkeypatch, tmp_path):
    cli = _import_cli()
    output = tmp_path / "official-report.json"

    class _Result:
        def fetchall(self):
            return [
                {
                    "company_id": "COMP-1",
                    "canonical_name": "深圳示例科技有限公司",
                    "normalized_name": "示例科技",
                    "industry": "人工智能",
                    "website": "https://example.com",
                }
            ]

    class _Conn:
        def __init__(self):
            self.closed = False
            self.commits = 0

        def execute(self, _query, _params=None):
            return _Result()

        def commit(self):
            self.commits += 1

        def close(self):
            self.closed = True

    conn = _Conn()
    html_by_url = {
        "https://example.com": (
            "<section class='product-card'>"
            "<h2>工业视觉平台</h2>"
            "<p>面向产线质检的AI视觉检测产品。</p>"
            "</section>"
        )
    }

    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(cli.psycopg, "connect", lambda *_args, **_kwargs: conn)
    monkeypatch.setattr(
        cli,
        "_fetch_html",
        lambda url, **_kwargs: html_by_url.get(url),
    )

    def fail_persist(*_args, **_kwargs):
        raise AssertionError("dry-run must not persist official products")

    monkeypatch.setattr(cli, "upsert_company_product", fail_persist)

    exit_code = cli.main(
        [
            "--dry-run",
            "--company-id",
            "COMP-1",
            "--max-pages",
            "1",
            "--sleep-seconds",
            "0",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dry_run"] is True
    assert report["products_extracted"] == 1
    assert report["products_inserted"] == 0
    assert conn.commits == 0
    assert conn.closed is True
