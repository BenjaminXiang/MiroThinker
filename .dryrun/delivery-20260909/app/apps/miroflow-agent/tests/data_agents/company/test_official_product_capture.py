from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from src.data_agents.company.official_product_capture import (
    CompanyApplicationScenarioCandidate,
    CompanyProductCandidate,
    OfficialSitePage,
    classify_official_capture_failure,
    common_official_material_urls,
    extract_official_source_materials,
    extract_products_from_html,
    needs_javascript_rendering,
    select_candidate_material_urls,
    select_sitemap_material_urls,
    select_candidate_urls,
    upsert_company_application_scenario,
    upsert_company_product,
)


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _CaptureConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "RETURNING product_id" in sql:
            return _Result({"product_id": "PROD-1"})
        if "RETURNING scenario_id" in sql:
            return _Result({"scenario_id": "SCEN-1"})
        return _Result()


def test_select_candidate_urls_stays_on_official_host_and_respects_limit():
    html = """
    <html><body>
      <a href="/products">产品中心</a>
      <a href="https://example.com/solutions/ai">解决方案</a>
      <a href="https://external.example/products">外部产品</a>
      <a href="/about">关于我们</a>
    </body></html>
    """

    urls = select_candidate_urls(
        base_url="https://example.com",
        html=html,
        max_urls=2,
    )

    assert urls == [
        "https://example.com/products",
        "https://example.com/solutions/ai",
    ]


def test_select_candidate_material_urls_covers_core_official_sections():
    html = """
    <html><body>
      <a href="/about">关于我们</a>
      <a href="/products">产品中心</a>
      <a href="/services">服务</a>
      <a href="/solutions/ai">解决方案</a>
      <a href="/cases">客户案例</a>
      <a href="/customers">客户</a>
      <a href="/news">新闻动态</a>
      <a href="/careers">加入我们</a>
      <a href="https://external.example/news">外部新闻</a>
    </body></html>
    """

    urls = select_candidate_material_urls(
        base_url="https://example.com",
        html=html,
        max_urls=10,
    )

    assert urls == [
        "https://example.com/about",
        "https://example.com/products",
        "https://example.com/services",
        "https://example.com/solutions/ai",
        "https://example.com/cases",
        "https://example.com/customers",
        "https://example.com/news",
    ]


def test_select_sitemap_material_urls_filters_same_host_business_pages():
    sitemap_xml = """
    <urlset>
      <url><loc>https://example.com/about</loc></url>
      <url><loc>https://example.com/product/vision-platform</loc></url>
      <url><loc>https://example.com/cases/manufacturing</loc></url>
      <url><loc>https://example.com/careers</loc></url>
      <url><loc>https://external.example.com/products</loc></url>
    </urlset>
    """

    urls = select_sitemap_material_urls(
        base_url="https://example.com",
        sitemap_xml=sitemap_xml,
        max_urls=10,
    )

    assert urls == [
        "https://example.com/about",
        "https://example.com/product/vision-platform",
        "https://example.com/cases/manufacturing",
    ]


def test_common_official_material_urls_builds_bounded_same_host_paths():
    urls = common_official_material_urls(
        base_url="https://example.com/root/index.html",
        max_urls=5,
    )

    assert urls == [
        "https://example.com/about",
        "https://example.com/about-us",
        "https://example.com/company",
        "https://example.com/products",
        "https://example.com/product",
    ]


def test_needs_javascript_rendering_detects_spa_shell_and_short_pages():
    spa_html = """
    <html><body>
      <div id="app">We're sorry but 扬奇智能 doesn't work properly without JavaScript enabled.</div>
      <script src="/assets/app.js"></script>
    </body></html>
    """

    assert needs_javascript_rendering(spa_html) is True
    assert needs_javascript_rendering("<html><body><div id='root'></div></body></html>") is True
    assert (
        needs_javascript_rendering(
            "<html><body><p>示例科技专注工业视觉检测平台，服务产线质检客户，"
            "提供缺陷识别、质量追溯和智能制造解决方案。</p></body></html>"
        )
        is False
    )


def test_classify_official_capture_failure_uses_normalized_taxonomy():
    cases = [
        ({"website": None}, "no_website"),
        ({"website": "not a url"}, "invalid_url"),
        ({"website": "https://example.com", "error": "DNS lookup failed"}, "dns_failed"),
        ({"website": "https://example.com", "error": "request timeout"}, "timeout"),
        ({"website": "https://example.com", "http_status": 403}, "http_403"),
        ({"website": "https://example.com", "http_status": 429}, "http_429"),
        (
            {
                "website": "https://example.com",
                "html": "<html><body>x-waf-captcha-referer captcha</body></html>",
            },
            "captcha_or_bot_challenge",
        ),
        ({"website": "https://example.com", "robots_disallowed": True}, "robots_disallowed"),
        (
            {
                "website": "https://example.com",
                "html": "<html><body><div id='app'>please enable JavaScript</div></body></html>",
            },
            "js_required",
        ),
        ({"website": "https://example.com", "render_failed": True}, "js_render_failed"),
        ({"website": "https://example.com", "html": "<html><body>短</body></html>"}, "text_too_short"),
        (
            {
                "website": "https://example.com",
                "html": "<html><body>This domain is for sale. Buy now for $1995.</body></html>",
            },
            "noise_page",
        ),
        ({"website": "https://example.com", "identity_mismatch": True}, "identity_mismatch"),
        ({"website": "https://example.com", "no_relevant_pages": True}, "no_relevant_pages"),
        ({"website": "https://example.com", "error": "connection reset"}, "fetch_failed"),
    ]

    for kwargs, expected in cases:
        assert classify_official_capture_failure(**kwargs) == expected


def test_extract_official_source_materials_filters_noise_and_marks_high_trust():
    pages = [
        OfficialSitePage(
            url="https://example.com/about",
            html="<html><head><title>关于示例科技</title></head><body><h1>关于我们</h1><p>示例科技专注工业视觉检测平台，服务产线质检客户。</p></body></html>",
            fetched_at=None,
            acquisition_method="js_render",
        ),
        OfficialSitePage(
            url="https://example.com/careers",
            html="<html><body><h1>招聘职位</h1><p>算法工程师、销售经理、投递简历。</p></body></html>",
            fetched_at=None,
        ),
    ]

    materials = extract_official_source_materials(
        company_id="COMP-1",
        company_name="深圳示例科技有限公司",
        pages=pages,
        max_chars=200,
    )

    assert len(materials) == 1
    material = materials[0]
    assert material.source_tier == "official_site"
    assert material.url == "https://example.com/about"
    assert material.title == "关于示例科技"
    assert "工业视觉检测平台" in material.captured_text
    assert material.trust_reason == "official_company_website"
    assert material.acquisition_method == "js_render"
    assert material.source_judgment_status == "accepted"
    assert material.source_judgment_confidence == Decimal("0.95")
    assert "工业视觉检测平台" in material.evidence_span


def test_extract_products_from_official_html_preserves_evidence_span():
    html = """
    <html><body>
      <section class="product-card">
        <h2>AI ECG Platform</h2>
        <p>面向医院的AI自动诊断心电系统，支持多导联心电图分析。</p>
      </section>
    </body></html>
    """

    products = extract_products_from_html(
        company_id="COMP-1",
        company_name="深圳旭宏医疗科技有限公司",
        page=OfficialSitePage(
            url="https://www.semacare.com/products",
            html=html,
            fetched_at=None,
        ),
    )

    assert len(products) == 1
    product = products[0]
    assert product.company_id == "COMP-1"
    assert product.product_name == "AI ECG Platform"
    assert product.short_description == "面向医院的AI自动诊断心电系统，支持多导联心电图分析。"
    assert product.official_product_url == "https://www.semacare.com/products"
    assert "AI ECG Platform" in product.evidence_span
    assert product.confidence == Decimal("0.75")
    assert product.quality_status == "needs_review"


def test_product_evidence_preserves_source_tier():
    conn = _CaptureConn()
    product = CompanyProductCandidate(
        company_id="COMP-1",
        product_name="AI ECG Platform",
        short_description="面向医院的AI自动诊断心电系统。",
        official_product_url="https://www.semacare.com/products",
        evidence_span="AI ECG Platform 面向医院的AI自动诊断心电系统。",
        confidence=Decimal("0.75"),
    )

    upsert_company_product(
        conn,
        product,
        extractor_version="test",
        source_tier="official_site",
    )

    evidence_calls = [call for call in conn.calls if "company_product_evidence" in call[0]]
    assert evidence_calls
    assert all("source_tier" in sql for sql, _params in evidence_calls)
    assert all("WHERE NOT EXISTS" in sql for sql, _params in evidence_calls)
    assert all("AND source_tier = %s" in sql for sql, _params in evidence_calls)
    assert any("official_site" in params for _sql, params in evidence_calls)


def test_application_scenario_evidence_preserves_source_tier():
    conn = _CaptureConn()
    scenario = CompanyApplicationScenarioCandidate(
        company_id="COMP-1",
        scenario_name="临床心电诊断",
        description="医院使用平台进行心电辅助诊断。",
        source_url="xlsx://company/COMP-1",
        evidence_span="面向医院提供AI心电辅助诊断。",
        confidence=Decimal("0.80"),
        target_customer="医院",
    )

    upsert_company_application_scenario(
        conn,
        scenario,
        extractor_version="test",
        source_tier="xlsx",
    )

    evidence_calls = [
        call for call in conn.calls if "company_application_scenario_evidence" in call[0]
    ]
    assert evidence_calls
    assert all("source_tier" in sql for sql, _params in evidence_calls)
    assert all("WHERE NOT EXISTS" in sql for sql, _params in evidence_calls)
    assert all("AND source_tier = %s" in sql for sql, _params in evidence_calls)
    assert any("xlsx" in params for _sql, params in evidence_calls)


def test_extract_products_rejects_navigation_and_recruiting_false_positives():
    html = """
    <html><body>
      <section>
        <h2>Follow Us</h2>
        <p>SHENZHEN SEMACARE MEDICAL TECHNOLOGY CO., LTD Follow Us After two years of hard work, MetaCor™ will come to the market soon.</p>
      </section>
      <section>
        <h2>Semacare 2019-2020 Job Opportunities</h2>
        <p>Director of Sales Android development engineer Algorithm engineer</p>
      </section>
      <section>
        <h2>Design</h2>
        <p>We put more PARAMETERS in every MILLIMETER.</p>
      </section>
    </body></html>
    """

    products = extract_products_from_html(
        company_id="COMP-1",
        company_name="深圳旭宏医疗科技有限公司",
        page=OfficialSitePage(
            url="https://www.semacare.com/",
            html=html,
            fetched_at=None,
        ),
    )

    assert [product.product_name for product in products] == ["MetaCor™"]
    assert products[0].short_description.startswith("After two years")
    assert "market soon" in products[0].short_description


def test_extract_products_rejects_domain_sale_and_javascript_placeholder_pages():
    domain_sale_html = """
    <html><body>
      <h1>BobbinControl.com</h1>
      <p>This domain is for sale: $1,995</p>
      <section><h2>PayPal</h2><p>Additionally, you may checkout with PayPal or Escrow.</p></section>
      <section><h2>GoDaddy</h2><p>You can transfer this domain to GoDaddy.</p></section>
    </body></html>
    """
    javascript_html = """
    <html><body>
      <div id="app">We're sorry but 扬奇智能 doesn't work properly without JavaScript enabled.</div>
      <section><h2>JavaScript</h2><p>You need to enable JavaScript to run this app.</p></section>
    </body></html>
    """

    assert (
        extract_products_from_html(
            company_id="COMP-1",
            company_name="梭芯智能",
            page=OfficialSitePage(
                url="https://www.bobbincontrol.com/",
                html=domain_sale_html,
                fetched_at=None,
            ),
        )
        == []
    )
    assert (
        extract_products_from_html(
            company_id="COMP-2",
            company_name="扬奇智能",
            page=OfficialSitePage(
                url="https://www.jancsitech.net/",
                html=javascript_html,
                fetched_at=None,
            ),
        )
        == []
    )


def test_extract_products_rejects_testimonial_cta_footer_and_generic_section_noise():
    html = """
    <html><body>
      <section>
        <h2>AndreaGaleazzi</h2>
        <p>Italy CGO800S Italian Andrea Galeazzi @AndreaGaleazzi "E la bicicletta perfetta per l'uso urbano."</p>
      </section>
      <section>
        <h2>GET A FREE QUOTE</h2>
        <p>Submit your request today and get a free solution plan and quote within 24 hours.</p>
      </section>
      <footer>
        <h2>LinkedIn</h2>
        <p>Tel: +86 755 8966 6210 LinkedIn Shop Online Smart Home Total Solution.</p>
      </footer>
      <section>
        <h2>产品介绍</h2>
        <p>产品介绍 国际领先的数据智能技术创新应用，打造新型智能数据库 BigInsights。</p>
      </section>
      <section>
        <h2>AI ECG Platform</h2>
        <p>面向医院的AI自动诊断心电系统，支持多导联心电图分析。</p>
      </section>
    </body></html>
    """

    products = extract_products_from_html(
        company_id="COMP-1",
        company_name="深圳旭宏医疗科技有限公司",
        page=OfficialSitePage(
            url="https://www.semacare.com/products",
            html=html,
            fetched_at=None,
        ),
    )

    assert [product.product_name for product in products] == ["AI ECG Platform"]


def test_extract_products_rejects_protocol_social_app_and_generic_products_heading_noise():
    html = """
    <html><body>
      <section>
        <h2>PRODUCTS</h2>
        <p>产品展示 反谐振空芯光纤-1310 可应用于通信领域。</p>
      </section>
      <section>
        <h2>WiFi</h2>
        <p>NB-IoT, LoRa, WiFi protocols are optional.</p>
      </section>
      <section>
        <h2>WeChat</h2>
        <p>Alarm receiving methods include SMS, WeChat and platform notification.</p>
      </section>
      <section>
        <h2>LoRa</h2>
        <p>SMART INDUSTRY communication supports LoRa communication.</p>
      </section>
      <section>
        <h2>AI ECG Platform</h2>
        <p>面向医院的AI自动诊断心电系统，支持多导联心电图分析。</p>
      </section>
    </body></html>
    """

    products = extract_products_from_html(
        company_id="COMP-1",
        company_name="深圳旭宏医疗科技有限公司",
        page=OfficialSitePage(
            url="https://www.semacare.com/products",
            html=html,
            fetched_at=None,
        ),
    )

    assert [product.product_name for product in products] == ["AI ECG Platform"]


def test_extract_products_rejects_marketing_channel_article_and_external_tool_noise():
    html = """
    <html><body>
      <section>
        <h2>预约即享 专属定制 好礼！OasisX即将全面上线各大平台。</h2>
        <p>获取验证码 立即预约</p>
      </section>
      <section>
        <h2>软件 APP 模板</h2>
        <p>产品中心 光通信产品线 通用类产品 硅光控制产品。</p>
      </section>
      <section>
        <h2>Bringing robots everywhere, for everyone</h2>
        <p>机器人与具身智能</p>
      </section>
      <section>
        <h2>产品与服务</h2>
        <p>BioFord™️ 一站式生物科学研究平台 AI 大模型和算法开发服务。</p>
      </section>
      <section>
        <h2>华力创产品</h2>
        <p>产品中心 力及力矩传感器产品 智能末端执行器 视-触觉融合解决方案。</p>
      </section>
      <section>
        <h2>BestBuy</h2>
        <p>已开拓沃尔玛、BestBuy、Home Depot等大型商超渠道伙伴。</p>
      </section>
      <section>
        <h2>OpenClaw</h2>
        <p>当然，这里说的不是海鲜，而是一款突然爆火的AI工具 OpenClaw。</p>
      </section>
      <section>
        <h2>EmbodiFlow</h2>
        <p>数据标注管理平台 EmbodiFlow 面向具身智能的数据标注与管理平台，并可一键导出 LeRobot 等可训练格式。</p>
      </section>
      <section>
        <h2>LivingAI</h2>
        <p>Copyright © 2026 LivingAI All Rights Reserved.</p>
      </section>
      <section>
        <h2>BioScience</h2>
        <p>以 AI 科技探索生命之谜 Advancing AI for BioScience</p>
      </section>
    </body></html>
    """

    products = extract_products_from_html(
        company_id="COMP-1",
        company_name="艾欧智能（深圳）",
        page=OfficialSitePage(
            url="https://io-ai.tech/",
            html=html,
            fetched_at=None,
        ),
    )

    assert [product.product_name for product in products] == ["BioFord™", "EmbodiFlow"]


def test_upsert_company_product_writes_product_and_evidence_rows():
    conn = MagicMock()
    product_cursor = MagicMock()
    product_cursor.fetchone.return_value = {"product_id": "PROD-123456789abc"}
    conn.execute.return_value = product_cursor
    product = extract_products_from_html(
        company_id="COMP-1",
        company_name="深圳旭宏医疗科技有限公司",
        page=OfficialSitePage(
            url="https://www.semacare.com/products",
            html="<h2>AI ECG Platform</h2><p>AI自动诊断心电系统。</p>",
            fetched_at=None,
        ),
    )[0]

    product_id = upsert_company_product(conn, product)

    assert product_id == "PROD-123456789abc"
    sqls = [call.args[0] for call in conn.execute.call_args_list]
    assert any("INSERT INTO company_product" in sql for sql in sqls)
    assert any("product_category" in sql for sql in sqls)
    assert any("target_customers" in sql for sql in sqls)
    assert any("application_scenarios" in sql for sql in sqls)
    assert any("technical_tags" in sql for sql in sqls)
    assert any("INSERT INTO company_product_evidence" in sql for sql in sqls)


def test_upsert_company_product_does_not_downgrade_ready_status():
    conn = MagicMock()
    product_cursor = MagicMock()
    product_cursor.fetchone.return_value = {"product_id": "PROD-123456789abc"}
    conn.execute.return_value = product_cursor
    product = CompanyProductCandidate(
        company_id="COMP-1",
        product_name="Semacare",
        short_description="AI心电智能筛查服务。",
        official_product_url="https://example.com/news",
        evidence_span="Semacare AI心电智能筛查服务。",
        confidence=Decimal("0.65"),
        quality_status="needs_review",
    )

    upsert_company_product(conn, product, source_tier="generic_web")

    product_sql = conn.execute.call_args_list[0].args[0]
    assert "company_product.quality_status = 'ready'" in product_sql
    assert "THEN company_product.quality_status" in product_sql
    assert "ELSE EXCLUDED.quality_status" in product_sql


def test_upsert_company_application_scenario_writes_scenario_and_evidence_rows():
    conn = MagicMock()
    scenario_cursor = MagicMock()
    scenario_cursor.fetchone.return_value = {"scenario_id": "SCEN-123456789abc"}
    conn.execute.return_value = scenario_cursor
    scenario = CompanyApplicationScenarioCandidate(
        company_id="COMP-1",
        scenario_name="远程心电诊断",
        description="支持临床和远程心电诊断及监护。",
        source_url="https://pitchhub.36kr.com/project/1",
        evidence_span="Semacare 支持临床和远程心电诊断及监护。",
        confidence=Decimal("0.65"),
        scenario_category="医疗诊断",
        target_customer="医院/临床机构",
        related_product_name="Semacare",
    )

    scenario_id = upsert_company_application_scenario(conn, scenario)

    assert scenario_id == "SCEN-123456789abc"
    sqls = [call.args[0] for call in conn.execute.call_args_list]
    assert any("INSERT INTO company_application_scenario" in sql for sql in sqls)
    assert any("related_product_id" in sql for sql in sqls)
    assert any("INSERT INTO company_application_scenario_evidence" in sql for sql in sqls)


def test_upsert_company_application_scenario_does_not_downgrade_ready_status():
    conn = MagicMock()
    scenario_cursor = MagicMock()
    scenario_cursor.fetchone.return_value = {"scenario_id": "SCEN-123456789abc"}
    conn.execute.return_value = scenario_cursor
    scenario = CompanyApplicationScenarioCandidate(
        company_id="COMP-1",
        scenario_name="远程心电诊断",
        description="支持临床和远程心电诊断及监护。",
        source_url="https://example.com/news",
        evidence_span="Semacare 支持临床和远程心电诊断及监护。",
        confidence=Decimal("0.65"),
        quality_status="needs_review",
        related_product_name="Semacare",
    )

    upsert_company_application_scenario(conn, scenario, source_tier="generic_web")

    scenario_sql = conn.execute.call_args_list[0].args[0]
    assert "company_application_scenario.quality_status = 'ready'" in scenario_sql
    assert "THEN company_application_scenario.quality_status" in scenario_sql
    assert "ELSE EXCLUDED.quality_status" in scenario_sql
