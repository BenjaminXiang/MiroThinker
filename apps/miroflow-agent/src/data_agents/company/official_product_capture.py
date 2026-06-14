from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from psycopg.types.json import Jsonb

from .source_material import CompanySourceMaterial

_PRODUCT_URL_HINT_RE = re.compile(
    r"(product|products|solution|solutions|service|services|case|cases|产品|方案|解决方案|服务)",
    re.IGNORECASE,
)
_OFFICIAL_MATERIAL_URL_HINT_RE = re.compile(
    r"(about|company|profile|product|products|solution|solutions|service|services|"
    r"case|cases|customer|customers|client|clients|news|article|blog|"
    r"关于|公司|简介|产品|方案|解决方案|服务|案例|客户|新闻|动态|资讯)",
    re.IGNORECASE,
)
_COMMON_OFFICIAL_MATERIAL_PATHS = (
    "/about",
    "/about-us",
    "/company",
    "/products",
    "/product",
    "/services",
    "/service",
    "/solutions",
    "/solution",
    "/cases",
    "/case",
    "/customers",
    "/customer",
    "/news",
)
_RECRUITING_URL_HINT_RE = re.compile(
    r"(career|careers|job|jobs|join|recruit|hiring|招聘|职位|加入|人才|校招|社招)",
    re.IGNORECASE,
)
_RECRUITING_ONLY_PAGE_RE = re.compile(
    r"(招聘职位|投递简历|职位申请|加入我们|校园招聘|社会招聘|"
    r"job\s+opportunities|career|careers|apply\s+now|send\s+resume)",
    re.IGNORECASE,
)
_NOISE_NAMES = {
    "产品中心",
    "产品",
    "产品介绍",
    "解决方案",
    "方案",
    "服务",
    "Products",
    "Solutions",
}
_NOISE_PRODUCT_NAMES = {
    "get a free quote",
    "javascript",
    "linkedin",
    "lora",
    "paypal",
    "product",
    "products",
    "wechat",
    "wifi",
    "godaddy",
    "namebright",
    "whois",
    "hugedomains",
    "bestbuy",
    "bioscience",
    "home depot",
    "lidar",
    "netrtk",
    "系统定制化能力",
}
_NOISE_TITLE_RE = re.compile(
    r"(follow\s+us|job|opportunit|recruit|career|join\s+us|news|about\s+us|"
    r"free\s+quote|shop\s+online|linkedin|director|engineer|sales|"
    r"bringing\s+robots\s+everywhere|software\s+app\s+template|"
    r"设计|招聘|职位|新闻|关于|产品介绍|产品与服务|软件\s*APP\s*模板|"
    r"预约|好礼|即将|上线|产品中心|爆火|AI工具)",
    re.IGNORECASE,
)
_NOISE_PRODUCT_CONTEXT_RE = re.compile(
    r"(follow\s+us|free\s+quote|shop\s+online|linkedin|预约|好礼|即将|上线|验证码|"
    r"爆火|AI工具|渠道伙伴|大型商超|copyright|all\s+rights\s+reserved|"
    r"advancing\s+a[il]\s+for)",
    re.IGNORECASE,
)
_NOISE_PAGE_RE = re.compile(
    r"(domain\s+is\s+for\s+sale|buy\s+now\s+for\s+\$|start\s+payment\s+plan|"
    r"your\s+web\s+address\s+means\s+everything|hugedomains|"
    r"doesn['’]t\s+work\s+properly\s+without\s+javascript\s+enabled|"
    r"you\s+need\s+to\s+enable\s+javascript\s+to\s+run\s+this\s+app|"
    r"please\s+enable\s+javascript)",
    re.IGNORECASE,
)
_CAPTCHA_OR_BOT_RE = re.compile(
    r"(x-waf-captcha-referer|captcha|bot\s+challenge|security\s+check|"
    r"access\s+denied|访问过于频繁|安全验证|请完成验证)",
    re.IGNORECASE,
)
_JAVASCRIPT_REQUIRED_RE = re.compile(
    r"(without\s+javascript\s+enabled|enable\s+javascript|"
    r"javascript\s+to\s+run\s+this\s+app|please\s+enable\s+javascript|"
    r"需要启用\s*javascript|请启用\s*javascript)",
    re.IGNORECASE,
)
_PRODUCT_TITLE_HINT_RE = re.compile(
    r"(平台|系统|机器人|产品|设备|模块|芯片|传感器|检测|终端|badge|platform|system|"
    r"robot|device|sensor|module|chip|solution)",
    re.IGNORECASE,
)
_CAMELCASE_PRODUCT_RE = re.compile(
    r"\b[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]+)+(?:™|®|â¢)?\b"
)
_TRADEMARK_PRODUCT_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9-]{2,}(?:™|®|â¢)"
)


@dataclass(frozen=True, slots=True)
class OfficialSitePage:
    url: str
    html: str
    fetched_at: datetime | None
    acquisition_method: str | None = None


@dataclass(frozen=True, slots=True)
class CompanyProductCandidate:
    company_id: str
    product_name: str
    short_description: str | None
    official_product_url: str
    evidence_span: str
    confidence: Decimal
    quality_status: str = "needs_review"
    product_category: str | None = None
    target_customers: tuple[str, ...] = ()
    application_scenarios: tuple[str, ...] = ()
    technical_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_customers",
            _clean_sequence(self.target_customers),
        )
        object.__setattr__(
            self,
            "application_scenarios",
            _clean_sequence(self.application_scenarios),
        )
        object.__setattr__(
            self,
            "technical_tags",
            _clean_sequence(self.technical_tags),
        )


@dataclass(frozen=True, slots=True)
class CompanyApplicationScenarioCandidate:
    company_id: str
    scenario_name: str
    description: str | None
    source_url: str
    evidence_span: str
    confidence: Decimal
    quality_status: str = "needs_review"
    scenario_category: str | None = None
    target_customer: str | None = None
    related_product_name: str | None = None
    related_product_id: str | None = None


def select_candidate_urls(*, base_url: str, html: str, max_urls: int = 8) -> list[str]:
    base_host = _host(base_url)
    if not base_host:
        return []

    soup = BeautifulSoup(html or "", "lxml")
    selected: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = _normalize_url(urljoin(base_url, str(anchor.get("href"))))
        if not absolute_url or absolute_url in seen:
            continue
        if _host(absolute_url) != base_host:
            continue
        label = anchor.get_text(" ", strip=True)
        if not _PRODUCT_URL_HINT_RE.search(f"{absolute_url} {label}"):
            continue
        seen.add(absolute_url)
        selected.append(absolute_url)
        if len(selected) >= max_urls:
            break
    return selected


def select_candidate_material_urls(
    *,
    base_url: str,
    html: str,
    max_urls: int = 12,
) -> list[str]:
    base_host = _host(base_url)
    if not base_host:
        return []

    soup = BeautifulSoup(html or "", "lxml")
    selected: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = _normalize_url(urljoin(base_url, str(anchor.get("href"))))
        if not absolute_url or absolute_url in seen:
            continue
        if _host(absolute_url) != base_host:
            continue
        label = anchor.get_text(" ", strip=True)
        combined = f"{absolute_url} {label}"
        if _RECRUITING_URL_HINT_RE.search(combined):
            continue
        if not _OFFICIAL_MATERIAL_URL_HINT_RE.search(combined):
            continue
        seen.add(absolute_url)
        selected.append(absolute_url)
        if len(selected) >= max_urls:
            break
    return selected


def select_sitemap_material_urls(
    *,
    base_url: str,
    sitemap_xml: str,
    max_urls: int = 12,
) -> list[str]:
    base_host = _host(base_url)
    if not base_host:
        return []

    soup = BeautifulSoup(sitemap_xml or "", "xml")
    selected: list[str] = []
    seen: set[str] = set()
    for loc in soup.find_all("loc"):
        absolute_url = _normalize_url(str(loc.get_text("", strip=True)))
        if not absolute_url or absolute_url in seen:
            continue
        if _host(absolute_url) != base_host:
            continue
        if _RECRUITING_URL_HINT_RE.search(absolute_url):
            continue
        if not _OFFICIAL_MATERIAL_URL_HINT_RE.search(absolute_url):
            continue
        seen.add(absolute_url)
        selected.append(absolute_url)
        if len(selected) >= max_urls:
            break
    return selected


def common_official_material_urls(*, base_url: str, max_urls: int = 12) -> list[str]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return []
    root = f"{parsed.scheme}://{parsed.netloc}"
    urls: list[str] = []
    for path in _COMMON_OFFICIAL_MATERIAL_PATHS:
        absolute_url = _normalize_url(urljoin(root, path))
        if not absolute_url:
            continue
        urls.append(absolute_url)
        if len(urls) >= max_urls:
            break
    return urls


def needs_javascript_rendering(html: str | None, *, min_text_chars: int = 30) -> bool:
    if html is None:
        return False
    text, _title = _official_page_text_and_title(html)
    if _JAVASCRIPT_REQUIRED_RE.search(html):
        return True
    if len(text) < min_text_chars and re.search(
        r"<(?:div|main)[^>]+id=[\"']?(app|root|__next)[\"']?",
        html,
        re.IGNORECASE,
    ):
        return True
    return False


def classify_official_capture_failure(
    *,
    website: str | None,
    html: str | None = None,
    http_status: int | None = None,
    error: str | None = None,
    robots_disallowed: bool = False,
    render_failed: bool = False,
    identity_mismatch: bool = False,
    no_relevant_pages: bool = False,
) -> str | None:
    if not website:
        return "no_website"
    if _normalize_url(website) is None:
        return "invalid_url"
    if robots_disallowed:
        return "robots_disallowed"
    if http_status == 403:
        return "http_403"
    if http_status == 429:
        return "http_429"
    if error:
        normalized_error = error.lower()
        if "dns" in normalized_error or "name resolution" in normalized_error:
            return "dns_failed"
        if "timeout" in normalized_error or "timed out" in normalized_error:
            return "timeout"
        return "fetch_failed"
    if html and _CAPTCHA_OR_BOT_RE.search(html):
        return "captcha_or_bot_challenge"
    if render_failed:
        return "js_render_failed"
    if html and needs_javascript_rendering(html):
        return "js_required"
    if html and _looks_like_noise_page(_official_page_text_and_title(html)[0]):
        return "noise_page"
    if html is not None:
        text, _title = _official_page_text_and_title(html)
        if len(text) < 20:
            return "text_too_short"
    if identity_mismatch:
        return "identity_mismatch"
    if no_relevant_pages:
        return "no_relevant_pages"
    if html is None:
        return "fetch_failed"
    return None


def extract_official_source_materials(
    *,
    company_id: str,
    company_name: str,
    pages: list[OfficialSitePage],
    max_chars: int = 5000,
) -> list[CompanySourceMaterial]:
    materials: list[CompanySourceMaterial] = []
    for page in pages:
        text, title = _official_page_text_and_title(page.html)
        if not text:
            continue
        if _looks_like_noise_page(text):
            continue
        if _is_recruiting_only_page(page.url, text):
            continue
        captured_text = text[:max_chars].strip()
        if len(captured_text) < 20:
            continue
        source_id = _official_source_id(company_id=company_id, url=page.url)
        materials.append(
            CompanySourceMaterial(
                source_id=source_id,
                source_tier="official_site",
                url=page.url,
                title=title,
                captured_text=captured_text,
                captured_at=page.fetched_at,
                trust_reason="official_company_website",
                source_judgment_status="accepted",
                source_judgment_confidence=Decimal("0.95"),
                source_judgment_evidence_span=_trim_evidence(captured_text),
                acquisition_method=page.acquisition_method or "static",
                evidence_span=_trim_evidence(captured_text),
            )
        )
    return materials


def extract_products_from_html(
    *,
    company_id: str,
    company_name: str,
    page: OfficialSitePage,
) -> list[CompanyProductCandidate]:
    soup = BeautifulSoup(page.html or "", "lxml")
    page_text = _normalize_text(soup.get_text(" ", strip=True)) or ""
    if _looks_like_noise_page(page_text):
        return []
    cards = _candidate_nodes(soup)
    products: list[CompanyProductCandidate] = []
    seen: set[str] = set()
    for node in cards:
        title = _extract_title(node)
        if title in _NOISE_NAMES:
            continue
        for product in _extract_named_products_from_node(
            company_id=company_id,
            page_url=page.url,
            node_text=node.get_text(" ", strip=True),
        ):
            if _product_name_key(product.product_name) in seen:
                continue
            seen.add(_product_name_key(product.product_name))
            products.append(product)

        description = _extract_description(node, title=title)
        if not title or title in _NOISE_NAMES:
            continue
        if company_name and title in company_name:
            continue
        if not description:
            continue
        if not _looks_like_product_title(title, description):
            continue
        key = _product_name_key(title)
        if key in seen:
            continue
        seen.add(key)
        evidence_span = _trim_evidence(node.get_text(" ", strip=True))
        if title not in evidence_span:
            evidence_span = _trim_evidence(f"{title} {description}")
        products.append(
            CompanyProductCandidate(
                company_id=company_id,
                product_name=title,
                short_description=description,
                official_product_url=page.url,
                evidence_span=evidence_span,
                confidence=Decimal("0.75"),
                quality_status="needs_review",
            )
        )
    return products


def _extract_named_products_from_node(
    *,
    company_id: str,
    page_url: str,
    node_text: str,
) -> list[CompanyProductCandidate]:
    text = _normalize_text(node_text)
    if not text:
        return []
    products: list[CompanyProductCandidate] = []
    seen: set[str] = set()
    for pattern in (_TRADEMARK_PRODUCT_RE, _CAMELCASE_PRODUCT_RE):
        for match in pattern.finditer(text):
            product_name = _normalize_product_name(match.group(0))
            key = _product_name_key(product_name) if product_name else None
            if not product_name or key in seen:
                continue
            if _is_noise_product_name(product_name):
                continue
            seen.add(key)
            sentence = _sentence_around(text, match.start(), match.end())
            if _looks_like_noise_product_context(product_name, sentence):
                continue
            products.append(
                CompanyProductCandidate(
                    company_id=company_id,
                    product_name=product_name,
                    short_description=_trim_description(sentence),
                    official_product_url=page_url,
                    evidence_span=_trim_evidence(sentence),
                    confidence=Decimal("0.75"),
                    quality_status="needs_review",
                )
            )
    return products


def _looks_like_product_title(title: str, description: str) -> bool:
    combined = f"{title} {description}"
    if _is_noise_product_name(title):
        return False
    if _looks_like_noise_product_context(title, combined):
        return False
    if _NOISE_TITLE_RE.search(combined):
        return False
    if _PRODUCT_TITLE_HINT_RE.search(title):
        return True
    if _TRADEMARK_PRODUCT_RE.search(title) or _CAMELCASE_PRODUCT_RE.search(title):
        return True
    if re.search(r"\b[A-Z]{2,}\b", title) and _PRODUCT_TITLE_HINT_RE.search(combined):
        return True
    return False


def _looks_like_noise_page(text: str) -> bool:
    return bool(_NOISE_PAGE_RE.search(text or ""))


def _is_recruiting_only_page(url: str, text: str) -> bool:
    combined = f"{url} {text}"
    if not _RECRUITING_ONLY_PAGE_RE.search(combined):
        return False
    product_or_company_signal = re.search(
        r"(产品|方案|解决方案|客户|案例|平台|系统|服务|融资|公司简介|关于我们)",
        text or "",
        re.IGNORECASE,
    )
    return product_or_company_signal is None


def _is_noise_product_name(value: str) -> bool:
    key = _product_name_key(value)
    if key in _NOISE_PRODUCT_NAMES:
        return True
    if key.endswith(".com") and "." in key:
        return True
    return bool(_NOISE_TITLE_RE.search(value))


def _looks_like_noise_product_context(product_name: str, text: str) -> bool:
    compact = re.sub(r"\s+", "", product_name or "")
    if _NOISE_PRODUCT_CONTEXT_RE.search(text or ""):
        return True
    if compact and re.search(
        rf"导出\s*{re.escape(product_name)}\s*等可训练格式",
        text or "",
        re.IGNORECASE,
    ):
        return True
    if compact and re.search(rf"@{re.escape(compact)}\b", text or "", re.IGNORECASE):
        return True
    return False


def _normalize_product_name(value: str) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.replace("â¢", "™")


def _product_name_key(value: str) -> str:
    return value.replace("™", "").replace("®", "").casefold()


def _sentence_around(text: str, start: int, end: int) -> str:
    left_candidates = [text.rfind(mark, 0, start) for mark in ("。", ".", "；", ";", "\n")]
    left = max(left_candidates)
    right_candidates = [
        position
        for position in (text.find(mark, end) for mark in ("。", ".", "；", ";", "\n"))
        if position != -1
    ]
    right = min(right_candidates) if right_candidates else min(len(text), end + 180)
    sentence = text[left + 1 : right + 1].strip()
    sentence = _trim_leading_navigation_noise(
        sentence,
        product_offset=max(0, start - left - 1),
    )
    return sentence or text[max(0, start - 80) : min(len(text), end + 160)].strip()


def _trim_leading_navigation_noise(sentence: str, *, product_offset: int) -> str:
    prefixes = ("Follow Us", "HOME", "ABOUT US", "NEWS", "JOIN US")
    for prefix in prefixes:
        index = sentence.lower().find(prefix.lower())
        if index == -1 or index > product_offset:
            continue
        trimmed = sentence[index + len(prefix) :].strip(" ,，:：")
        if trimmed:
            return trimmed
    return sentence


def upsert_company_product(
    conn: Any,
    product: CompanyProductCandidate,
    *,
    extractor_version: str = "official_product_capture.v1",
    source_tier: str | None = None,
) -> str:
    product_id = _product_id(product.company_id, product.product_name)
    evidence_source_tier = _evidence_source_tier(
        source_tier,
        source_url=product.official_product_url,
    )
    row = conn.execute(
        """
        INSERT INTO company_product (
            product_id, company_id, canonical_name, short_description,
            official_product_url, product_category, target_customers,
            application_scenarios, technical_tags, quality_status, confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id, canonical_name) DO UPDATE
        SET short_description = COALESCE(EXCLUDED.short_description, company_product.short_description),
            official_product_url = COALESCE(EXCLUDED.official_product_url, company_product.official_product_url),
            product_category = COALESCE(EXCLUDED.product_category, company_product.product_category),
            target_customers = CASE
                WHEN EXCLUDED.target_customers = '[]'::jsonb THEN company_product.target_customers
                ELSE EXCLUDED.target_customers
            END,
            application_scenarios = CASE
                WHEN EXCLUDED.application_scenarios = '[]'::jsonb THEN company_product.application_scenarios
                ELSE EXCLUDED.application_scenarios
            END,
            technical_tags = CASE
                WHEN EXCLUDED.technical_tags = '[]'::jsonb THEN company_product.technical_tags
                ELSE EXCLUDED.technical_tags
            END,
            quality_status = CASE
                WHEN company_product.quality_status = 'ready'
                     AND EXCLUDED.quality_status != 'ready'
                    THEN company_product.quality_status
                ELSE EXCLUDED.quality_status
            END,
            confidence = GREATEST(company_product.confidence, EXCLUDED.confidence),
            last_refreshed_at = now(),
            updated_at = now()
        RETURNING product_id
        """,
        (
            product_id,
            product.company_id,
            product.product_name,
            product.short_description,
            product.official_product_url,
            product.product_category,
            Jsonb(list(product.target_customers)),
            Jsonb(list(product.application_scenarios)),
            Jsonb(list(product.technical_tags)),
            product.quality_status,
            product.confidence,
        ),
    ).fetchone()
    stored_product_id = str(row["product_id"] if row else product_id)
    _insert_product_evidence(
        conn,
        product_id=stored_product_id,
        field_name="short_description",
        source_url=product.official_product_url,
        evidence_span=product.evidence_span,
        confidence=product.confidence,
        extractor_version=extractor_version,
        source_tier=evidence_source_tier,
    )
    for field_name, values in (
        ("product_category", [product.product_category] if product.product_category else []),
        ("target_customers", list(product.target_customers)),
        ("application_scenarios", list(product.application_scenarios)),
        ("technical_tags", list(product.technical_tags)),
    ):
        if values:
            _insert_product_evidence(
                conn,
                product_id=stored_product_id,
                field_name=field_name,
                source_url=product.official_product_url,
                evidence_span=product.evidence_span,
                confidence=product.confidence,
                extractor_version=extractor_version,
                source_tier=evidence_source_tier,
            )
    return stored_product_id


def _insert_product_evidence(
    conn: Any,
    *,
    product_id: str,
    field_name: str,
    source_url: str,
    evidence_span: str,
    confidence: Decimal,
    extractor_version: str,
    source_tier: str,
) -> None:
    conn.execute(
        """
        INSERT INTO company_product_evidence (
            product_id, field_name, source_url, evidence_span,
            confidence, extractor_version, source_tier
        )
        SELECT %s, %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1
              FROM company_product_evidence
             WHERE product_id = %s
               AND field_name = %s
               AND source_url = %s
               AND evidence_span = %s
               AND source_tier = %s
        )
        """,
        (
            product_id,
            field_name,
            source_url,
            evidence_span,
            confidence,
            extractor_version,
            source_tier,
            product_id,
            field_name,
            source_url,
            evidence_span,
            source_tier,
        ),
    )


def upsert_company_application_scenario(
    conn: Any,
    scenario: CompanyApplicationScenarioCandidate,
    *,
    extractor_version: str = "source_product_extractor.v1",
    source_tier: str | None = None,
) -> str:
    evidence_source_tier = _evidence_source_tier(
        source_tier,
        source_url=scenario.source_url,
    )
    related_product_id = scenario.related_product_id
    if not related_product_id and scenario.related_product_name:
        related_product_id = _product_id(scenario.company_id, scenario.related_product_name)
    scenario_id = _scenario_id(scenario.company_id, scenario.scenario_name)
    row = conn.execute(
        """
        INSERT INTO company_application_scenario (
            scenario_id, company_id, related_product_id, scenario_name,
            scenario_category, description, target_customer, source_url,
            quality_status, confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id, scenario_name) DO UPDATE
        SET related_product_id = COALESCE(
                EXCLUDED.related_product_id,
                company_application_scenario.related_product_id
            ),
            scenario_category = COALESCE(
                EXCLUDED.scenario_category,
                company_application_scenario.scenario_category
            ),
            description = COALESCE(
                EXCLUDED.description,
                company_application_scenario.description
            ),
            target_customer = COALESCE(
                EXCLUDED.target_customer,
                company_application_scenario.target_customer
            ),
            source_url = COALESCE(EXCLUDED.source_url, company_application_scenario.source_url),
            quality_status = CASE
                WHEN company_application_scenario.quality_status = 'ready'
                     AND EXCLUDED.quality_status != 'ready'
                    THEN company_application_scenario.quality_status
                ELSE EXCLUDED.quality_status
            END,
            confidence = GREATEST(company_application_scenario.confidence, EXCLUDED.confidence),
            last_refreshed_at = now(),
            updated_at = now()
        RETURNING scenario_id
        """,
        (
            scenario_id,
            scenario.company_id,
            related_product_id,
            scenario.scenario_name,
            scenario.scenario_category,
            scenario.description,
            scenario.target_customer,
            scenario.source_url,
            scenario.quality_status,
            scenario.confidence,
        ),
    ).fetchone()
    stored_scenario_id = str(row["scenario_id"] if row else scenario_id)
    conn.execute(
        """
        INSERT INTO company_application_scenario_evidence (
            scenario_id, field_name, source_url, evidence_span,
            confidence, extractor_version, source_tier
        )
        SELECT %s, %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1
              FROM company_application_scenario_evidence
             WHERE scenario_id = %s
               AND field_name = %s
               AND source_url = %s
               AND evidence_span = %s
               AND source_tier = %s
        )
        """,
        (
            stored_scenario_id,
            "scenario_name",
            scenario.source_url,
            scenario.evidence_span,
            scenario.confidence,
            extractor_version,
            evidence_source_tier,
            stored_scenario_id,
            "scenario_name",
            scenario.source_url,
            scenario.evidence_span,
            evidence_source_tier,
        ),
    )
    return stored_scenario_id


def _evidence_source_tier(source_tier: str | None, *, source_url: str) -> str:
    explicit = (source_tier or "").strip().lower()
    if explicit:
        return explicit
    normalized_url = (source_url or "").strip().lower()
    host = (urlparse(normalized_url).hostname or "").lower()
    if normalized_url.startswith("xlsx://"):
        return "xlsx"
    if host == "data.iyiou.com":
        return "yiou"
    if host == "pitchhub.36kr.com":
        return "pitchhub_36kr"
    if normalized_url.startswith(("http://", "https://")):
        return "official_site"
    return "unknown"


def product_to_json(product: CompanyProductCandidate) -> dict[str, Any]:
    return {
        "company_id": product.company_id,
        "product_name": product.product_name,
        "short_description": product.short_description,
        "official_product_url": product.official_product_url,
        "evidence_span": product.evidence_span,
        "confidence": str(product.confidence),
        "quality_status": product.quality_status,
        "product_category": product.product_category,
        "target_customers": list(product.target_customers),
        "application_scenarios": list(product.application_scenarios),
        "technical_tags": list(product.technical_tags),
    }


def application_scenario_to_json(
    scenario: CompanyApplicationScenarioCandidate,
) -> dict[str, Any]:
    return {
        "company_id": scenario.company_id,
        "scenario_name": scenario.scenario_name,
        "description": scenario.description,
        "source_url": scenario.source_url,
        "evidence_span": scenario.evidence_span,
        "confidence": str(scenario.confidence),
        "quality_status": scenario.quality_status,
        "scenario_category": scenario.scenario_category,
        "target_customer": scenario.target_customer,
        "related_product_name": scenario.related_product_name,
        "related_product_id": scenario.related_product_id,
    }


def _scenario_id(company_id: str, scenario_name: str) -> str:
    digest = sha256(f"{company_id}|{scenario_name}".encode("utf-8")).hexdigest()[:12]
    return f"SCEN-{digest}"


def _clean_sequence(values: tuple[str, ...] | list[str] | Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = list(values)
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return tuple(cleaned)


def _candidate_nodes(soup: BeautifulSoup) -> list[Any]:
    nodes: list[Any] = []
    for selector in (
        ".product-card",
        ".product",
        ".products li",
        ".solution-card",
        ".solution",
        "article",
        "section",
    ):
        nodes.extend(soup.select(selector))
    if nodes:
        return nodes
    return list(soup.find_all(["section", "article", "div", "li", "body"], limit=80))


def _extract_title(node: Any) -> str | None:
    title_node = node.find(["h1", "h2", "h3", "h4"])
    if title_node is None:
        title_node = node.find(["strong", "b"])
    if title_node is None:
        return None
    title = _normalize_text(title_node.get_text(" ", strip=True))
    if not title or len(title) > 80:
        return None
    return title


def _extract_description(node: Any, *, title: str | None) -> str | None:
    for paragraph in node.find_all(["p", "li"], limit=8):
        text = _normalize_text(paragraph.get_text(" ", strip=True))
        if not text or text == title or len(text) < 8:
            continue
        return _trim_description(text)
    text = _normalize_text(node.get_text(" ", strip=True))
    if not text or not title or title not in text:
        return None
    remainder = _normalize_text(text.replace(title, " ", 1))
    if not remainder or len(remainder) < 8:
        return None
    return _trim_description(remainder)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.replace("\u3000", " ").replace("â¢", "™").replace("ï¼", "：")
    text = " ".join(text.split()).strip()
    return text or None


def _official_page_text_and_title(html: str | None) -> tuple[str, str | None]:
    soup = BeautifulSoup(html or "", "lxml")
    title = None
    if soup.title is not None:
        title = _normalize_text(soup.title.get_text(" ", strip=True))
    if title is None:
        heading = soup.find(["h1", "h2"])
        if heading is not None:
            title = _normalize_text(heading.get_text(" ", strip=True))
    text = _normalize_text(soup.get_text(" ", strip=True)) or ""
    return text, title


def _trim_description(text: str) -> str:
    if len(text) <= 220:
        return text.strip()
    return text[:220].rstrip("，。；; ") + "。"


def _trim_evidence(text: str) -> str:
    return text[:400].strip()


def _normalize_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    return parsed._replace(fragment="").geturl()


def _host(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host or None


def _product_id(company_id: str, product_name: str) -> str:
    digest = sha256(f"{company_id}|{product_name}".encode("utf-8")).hexdigest()[:12]
    return f"PROD-{digest}"


def _official_source_id(*, company_id: str, url: str) -> str:
    digest = sha256(f"{company_id}|{url}".encode("utf-8")).hexdigest()[:12]
    return f"official:{company_id}:{digest}"
