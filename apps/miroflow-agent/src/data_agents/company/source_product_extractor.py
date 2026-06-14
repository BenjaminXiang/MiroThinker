from __future__ import annotations

from dataclasses import replace
import json
import re
from decimal import Decimal
from typing import Any

from .source_material import CompanySourceMaterial
from .official_product_capture import (
    CompanyApplicationScenarioCandidate,
    CompanyProductCandidate,
    upsert_company_application_scenario,
    upsert_company_product,
)

_PRODUCT_NAME_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9_-]{1,32}[\u4e00-\u9fffA-Za-z0-9_-]{0,18}"
    r"(?:平台|系统|设备|产品|服务|解决方案|方案|传感器|芯片|模组|机器人)|"
    r"[\u4e00-\u9fffA-Za-z0-9_-]{2,24}(?:平台|系统|设备|产品|服务|解决方案|方案|传感器|芯片|模组|机器人))"
)
_LEADING_BRAND_RE = re.compile(
    r"(?:^|项目简介[:： ]+|产品服务[:： ]+|产品与服务[:： ]+|业务介绍[:： ]+)"
    r"([A-Za-z][A-Za-z0-9_-]{2,32})"
    r"(?=\s+[^。；;]{0,140}(?:产品|服务|平台|系统|设备|解决方案|辅助诊断|筛查|检测|管理|监护|开发|推出|自研|专注))"
)
_PRODUCT_SECTION_MARKERS = (
    "产品服务",
    "产品与服务",
    "产品",
    "服务",
    "解决方案",
    "项目简介",
    "业务介绍",
    "主营业务",
)
_PRODUCT_HINTS = (
    "产品",
    "服务",
    "平台",
    "系统",
    "设备",
    "解决方案",
    "辅助诊断",
    "筛查",
    "检测",
    "管理",
)
_GENERIC_NAMES = {
    "产品",
    "产品服务",
    "核心产品",
    "服务",
    "平台",
    "系统",
    "解决方案",
    "项目简介",
    "业务介绍",
}
_BAD_NAME_PREFIXES = (
    "产品",
    "服务",
    "核心",
    "主要",
    "面向",
    "提供",
    "拥有",
    "主打",
    "结合",
    "集",
    "销售",
    "技术",
    "支持",
    "应用",
    "生产",
    "基于",
    "曾",
    "双方",
    "已有",
    "旗下",
    "我们",
    "的",
    "同时",
    "器和",
    "相关行业",
    "能",
    "帮助",
    "专业",
    "并在",
    "每开通过",
    "在面对",
    "从而",
    "能够",
    "打造",
    "受益",
    "通过",
    "公司推出",
    "该技术",
)
_BAD_NAME_SUBSTRINGS = (
    "提供",
    "面向",
    "是一家",
    "研发商",
    "提供商",
    "生产商",
    "开发商",
    "技术服务",
    "产品研发",
    "在产品",
    "等自动化",
    "售后",
    "提高产品",
    "服务商",
    "希望通过",
    "共同研发",
    "将赋能",
    "搭载",
    "获得",
    "等五大平台",
    "构建一个开放",
)
_LEGAL_NAME_MARKERS = ("公司", "有限公司")
_GENERIC_ASCII_NAMES = {"AI", "IP", "AR", "VR", "SaaS", "PaaS"}
_LEADING_NAME_NOISE_RE = re.compile(
    r"^(?:提供|自研|自主研发的|推出|包括|拥有|主打产品为|产品有|产品为|产品包括|通过自研)"
)
_LLM_FALLBACK_MAX_TOKENS = 4096


def persist_synthesized_products_and_scenarios(
    conn: Any,
    *,
    products: list[CompanyProductCandidate],
    scenarios: list[CompanyApplicationScenarioCandidate],
    source_materials: list[CompanySourceMaterial],
    extractor_version: str = "source_product_extractor.v2",
) -> dict[str, int]:
    material_by_url = {
        _normalize_material_url(material.url): material for material in source_materials
    }
    products_inserted = 0
    scenarios_inserted = 0
    for product in products:
        material = material_by_url.get(_normalize_material_url(product.official_product_url))
        source_tier = _material_tier(material, fallback_url=product.official_product_url)
        gated = replace(
            product,
            quality_status=_product_quality_status(product, material),
        )
        upsert_company_product(
            conn,
            gated,
            extractor_version=extractor_version,
            source_tier=source_tier,
        )
        products_inserted += 1
    for scenario in scenarios:
        material = material_by_url.get(_normalize_material_url(scenario.source_url))
        source_tier = _material_tier(material, fallback_url=scenario.source_url)
        gated = replace(
            scenario,
            quality_status=_scenario_quality_status(scenario, material),
        )
        upsert_company_application_scenario(
            conn,
            gated,
            extractor_version=extractor_version,
            source_tier=source_tier,
        )
        scenarios_inserted += 1
    return {
        "products_inserted": products_inserted,
        "scenarios_inserted": scenarios_inserted,
    }


def _normalize_material_url(value: str | None) -> str:
    return (value or "").strip()


def _product_quality_status(
    product: CompanyProductCandidate,
    material: CompanySourceMaterial | None,
) -> str:
    tier = _material_tier(material, fallback_url=product.official_product_url)
    if tier == "xlsx" and _product_has_explicit_trusted_baseline(product):
        return "ready"
    if tier in {"xlsx", "official", "official_site"} and _product_has_business_fields(product):
        return "ready"
    if (
        tier == "generic_web"
        and _product_has_business_fields(product)
        and product.confidence >= Decimal("0.85")
        and _strong_generic_judgment(material)
    ):
        return "ready"
    return "needs_review"


def _product_has_explicit_trusted_baseline(product: CompanyProductCandidate) -> bool:
    return bool(
        product.product_name
        and product.short_description
        and product.evidence_span
        and product.confidence >= Decimal("0.65")
    )


def _scenario_quality_status(
    scenario: CompanyApplicationScenarioCandidate,
    material: CompanySourceMaterial | None,
) -> str:
    tier = _material_tier(material, fallback_url=scenario.source_url)
    explicit = bool(
        scenario.scenario_name
        and scenario.evidence_span
        and (scenario.description or scenario.target_customer)
    )
    if tier in {"xlsx", "official", "official_site"} and explicit:
        return "ready"
    if (
        tier == "generic_web"
        and explicit
        and scenario.confidence >= Decimal("0.85")
        and _strong_generic_judgment(material)
    ):
        return "ready"
    return "needs_review"


def _material_tier(material: CompanySourceMaterial | None, *, fallback_url: str) -> str:
    if material is not None:
        return material.source_tier.strip().lower()
    if fallback_url.startswith("xlsx://"):
        return "xlsx"
    return ""


def _strong_generic_judgment(material: CompanySourceMaterial | None) -> bool:
    if material is None:
        return False
    if material.source_judgment_status != "accepted":
        return False
    if material.source_judgment_confidence is not None:
        return material.source_judgment_confidence >= Decimal("0.90")
    reason = (material.trust_reason or "").lower()
    return "strong" in reason and "fact" in reason


def extract_products_from_source_text(
    *,
    company_id: str,
    company_name: str,
    source_url: str,
    title: str,
    body_text: str | None,
) -> list[CompanyProductCandidate]:
    text = _normalize_text(body_text)
    if not text:
        return []

    source_section = _productish_section(text)
    if source_section is None:
        return []

    products: list[CompanyProductCandidate] = []
    seen: set[str] = set()
    for match in _LEADING_BRAND_RE.finditer(source_section):
        _append_product_candidate(
            products,
            seen,
            company_id=company_id,
            company_name=company_name,
            source_url=source_url,
            source_section=source_section,
            start=match.start(1),
            end=match.end(1),
            raw_name=match.group(1),
        )
    for match in _PRODUCT_NAME_RE.finditer(source_section):
        if not _has_local_product_signal(
            source_section,
            match.start(),
            match.end(),
            match.group(1),
        ):
            continue
        _append_product_candidate(
            products,
            seen,
            company_id=company_id,
            company_name=company_name,
            source_url=source_url,
            source_section=source_section,
            start=match.start(),
            end=match.end(),
            raw_name=match.group(1),
        )

    ascii_named_products = [
        product for product in products if re.search(r"[A-Za-z]", product.product_name)
    ]
    if ascii_named_products:
        return ascii_named_products[:5]

    fallback_name = _fallback_project_name(title, company_name=company_name)
    if fallback_name:
        return [
            CompanyProductCandidate(
                company_id=company_id,
                product_name=fallback_name,
                short_description=_trim_description(source_section),
                official_product_url=source_url,
                evidence_span=_trim_evidence(source_section),
                confidence=Decimal("0.65"),
                quality_status="needs_review",
                **_structured_product_fields(source_section),
            )
        ]
    return products[:5]


def extract_application_scenarios_from_source_text(
    *,
    company_id: str,
    company_name: str,
    source_url: str,
    title: str,
    body_text: str | None,
) -> list[CompanyApplicationScenarioCandidate]:
    text = _normalize_text(body_text)
    if not text:
        return []
    source_section = _productish_section(text)
    if source_section is None:
        return []

    products = extract_products_from_source_text(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=body_text,
    )
    related_product_name = products[0].product_name if products else None
    scenarios = _application_scenarios(source_section)
    results: list[CompanyApplicationScenarioCandidate] = []
    for scenario_name in scenarios:
        results.append(
            CompanyApplicationScenarioCandidate(
                company_id=company_id,
                scenario_name=scenario_name,
                description=_trim_description(_scenario_description(source_section)),
                source_url=source_url,
                evidence_span=_trim_evidence(source_section),
                confidence=Decimal("0.65"),
                quality_status="needs_review",
                scenario_category=_scenario_category(scenario_name, source_section),
                target_customer=_target_customer(source_section),
                related_product_name=related_product_name,
            )
        )
    return results


def synthesize_products_and_scenarios_from_xlsx(
    *,
    company_id: str,
    company_name: str,
    project_name: str | None = None,
    industry: str | None = None,
    description: str | None = None,
    business: str | None = None,
    product_intro: str | None = None,
    product_features: str | None = None,
    application_scenarios_raw: str | None = None,
    team_raw: str | None = None,
    llm_client: Any | None = None,
    llm_model: str = "",
    extra_body: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[CompanyProductCandidate], list[CompanyApplicationScenarioCandidate]]:
    """Synthesize products/scenarios from trusted XLSX business text."""
    source_text = _xlsx_source_text(
        project_name=project_name,
        industry=industry,
        description=description,
        business=business,
        product_intro=product_intro,
        product_features=product_features,
        application_scenarios_raw=application_scenarios_raw,
        team_raw=team_raw,
    )
    if not source_text:
        if diagnostics is not None:
            diagnostics["synthesis_skipped"] = "no_source_text"
        return [], []

    source_url = f"xlsx://company/{company_id}"
    title = project_name or company_name
    products = extract_products_from_source_text(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=source_text,
    )
    scenarios = extract_application_scenarios_from_source_text(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=source_text,
    )

    if llm_client is None:
        return products, _merge_product_application_scenarios(
            products,
            scenarios,
            source_url=source_url,
        )
    if products and scenarios and all(_product_has_business_fields(product) for product in products):
        return products, _merge_product_application_scenarios(
            products,
            scenarios,
            source_url=source_url,
        )

    llm_products, llm_scenarios = extract_products_and_scenarios_with_llm_fallback(
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        title=title,
        body_text=source_text,
        existing_products=[],
        existing_scenarios=[],
        llm_client=llm_client,
        llm_model=llm_model,
        extra_body=extra_body,
        diagnostics=diagnostics,
    )
    final_products = llm_products or products
    final_scenarios = llm_scenarios or scenarios
    return final_products, _merge_product_application_scenarios(
        final_products,
        final_scenarios,
        source_url=source_url,
    )


def _xlsx_source_text(
    *,
    project_name: str | None,
    industry: str | None,
    description: str | None,
    business: str | None,
    product_intro: str | None,
    product_features: str | None,
    application_scenarios_raw: str | None,
    team_raw: str | None,
) -> str:
    business_parts = [
        ("项目名称", project_name),
        ("简介", description),
        ("业务", business),
        ("产品简介", product_intro),
        ("产品特点", product_features),
        ("应用场景", application_scenarios_raw),
        ("团队", team_raw),
    ]
    if not any(_normalize_text(value) for _label, value in business_parts[1:]):
        return ""

    parts = []
    if _normalize_text(industry):
        parts.append(f"行业: {_normalize_text(industry)}")
    for label, value in business_parts:
        text = _normalize_text(value)
        if text:
            parts.append(f"{label}: {text}")
    return "\n".join(parts)


def _product_has_business_fields(product: CompanyProductCandidate) -> bool:
    return bool(
        product.product_name
        and product.short_description
        and product.product_category
        and product.technical_tags
        and product.target_customers
        and product.application_scenarios
    )


def extract_products_and_scenarios_with_llm_fallback(
    *,
    company_id: str,
    company_name: str,
    source_url: str,
    title: str,
    body_text: str | None,
    existing_products: list[CompanyProductCandidate],
    existing_scenarios: list[CompanyApplicationScenarioCandidate],
    llm_client: Any,
    llm_model: str,
    extra_body: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[CompanyProductCandidate], list[CompanyApplicationScenarioCandidate]]:
    """Use an LLM only as a fallback when deterministic extraction misses."""
    text = _normalize_text(body_text)
    if not text or existing_products or existing_scenarios:
        return existing_products, existing_scenarios

    prompt = "\n".join(
        [
            "Extract company products and application scenarios from the source text.",
            "Use only the provided text. Do not invent missing fields.",
            "Treat products broadly: named products, services, solutions, platforms, technical systems, or core technology offerings may all be product candidates when the text explicitly presents them as something the company provides.",
            "If there is no branded product name, derive a concise offering name from the described service/solution/technology, but never use the company name alone as a product.",
            "Extract application scenarios from explicit use cases, customer problems, deployment domains, or industry contexts in the text.",
            "Return empty arrays only when the text has no source-grounded product, service, solution, platform, or application-scenario facts.",
            "Return strict JSON with keys products and scenarios.",
            "Product schema: product_name, short_description, product_category, target_customers, application_scenarios, technical_tags, evidence_span, confidence.",
            "Scenario schema: scenario_name, description, scenario_category, target_customer, related_product_name, evidence_span, confidence.",
            "",
            f"Company: {company_name}",
            f"Title: {title}",
            f"Source URL: {source_url}",
            "Source text:",
            text[:3500],
        ]
    )
    try:
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You extract source-grounded company product facts and output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=_LLM_FALLBACK_MAX_TOKENS,
            extra_body=extra_body or {},
        )
    except Exception as exc:  # noqa: BLE001
        if diagnostics is not None:
            diagnostics["llm_fallback_model"] = llm_model
            diagnostics["llm_fallback_error"] = str(exc)
        return existing_products, existing_scenarios

    choice = response.choices[0]
    raw_text = (choice.message.content or "").strip()
    payload = _extract_json_object(raw_text)
    if not isinstance(payload, dict):
        if diagnostics is not None:
            diagnostics["llm_fallback_model"] = llm_model
            diagnostics["llm_fallback_error"] = "json_parse_failed"
            diagnostics["llm_fallback_finish_reason"] = getattr(
                choice,
                "finish_reason",
                None,
            )
            diagnostics["llm_fallback_raw_length"] = len(raw_text)
            diagnostics["llm_fallback_raw_prefix"] = raw_text[:200]
        return existing_products, existing_scenarios

    products = _coerce_llm_products(
        payload.get("products"),
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        source_text=text,
    )
    scenarios = _coerce_llm_scenarios(
        payload.get("scenarios"),
        company_id=company_id,
        source_url=source_url,
        source_text=text,
        product_names={product.product_name for product in products},
    )
    scenarios = _merge_product_application_scenarios(
        products,
        scenarios,
        source_url=source_url,
    )
    if diagnostics is not None:
        diagnostics["llm_fallback_model"] = llm_model
        diagnostics["llm_products"] = len(products)
        diagnostics["llm_scenarios"] = len(scenarios)
    return products, scenarios


def _extract_json_object(raw_text: str) -> Any:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _coerce_llm_products(
    values: Any,
    *,
    company_id: str,
    company_name: str,
    source_url: str,
    source_text: str,
) -> list[CompanyProductCandidate]:
    if not isinstance(values, list):
        return []
    products: list[CompanyProductCandidate] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        name = _clean_name(str(value.get("product_name") or ""))
        if not _valid_product_name(name, company_name=company_name, allow_company_alias=True):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        evidence = _llm_evidence_span(value, source_text)
        products.append(
            CompanyProductCandidate(
                company_id=company_id,
                product_name=name,
                short_description=_trim_description(
                    str(value.get("short_description") or evidence)
                ),
                official_product_url=source_url,
                evidence_span=_trim_evidence(evidence),
                confidence=_llm_confidence(value.get("confidence")),
                quality_status="needs_review",
                product_category=_optional_str(value.get("product_category")),
                target_customers=tuple(_string_list(value.get("target_customers"))),
                application_scenarios=tuple(
                    _string_list(value.get("application_scenarios"))
                ),
                technical_tags=tuple(_string_list(value.get("technical_tags"))),
            )
        )
    return products[:5]


def _coerce_llm_scenarios(
    values: Any,
    *,
    company_id: str,
    source_url: str,
    source_text: str,
    product_names: set[str],
) -> list[CompanyApplicationScenarioCandidate]:
    if not isinstance(values, list):
        return []
    scenarios: list[CompanyApplicationScenarioCandidate] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            continue
        name = _clean_name(str(value.get("scenario_name") or ""))
        if not name or name in seen or len(name) > 40:
            continue
        seen.add(name)
        related = _optional_str(value.get("related_product_name"))
        if related and related not in product_names:
            related = None
        evidence = _llm_evidence_span(value, source_text)
        scenarios.append(
            CompanyApplicationScenarioCandidate(
                company_id=company_id,
                scenario_name=name,
                description=_optional_str(value.get("description")),
                source_url=source_url,
                evidence_span=_trim_evidence(evidence),
                confidence=_llm_confidence(value.get("confidence")),
                quality_status="needs_review",
                scenario_category=_optional_str(value.get("scenario_category")),
                target_customer=_optional_str(value.get("target_customer")),
                related_product_name=related,
            )
        )
    return scenarios[:8]


def _merge_product_application_scenarios(
    products: list[CompanyProductCandidate],
    scenarios: list[CompanyApplicationScenarioCandidate],
    *,
    source_url: str,
) -> list[CompanyApplicationScenarioCandidate]:
    merged = list(scenarios)
    seen = {scenario.scenario_name for scenario in merged}
    for product in products:
        target_customer = (
            product.target_customers[0] if len(product.target_customers) == 1 else None
        )
        for raw_name in product.application_scenarios:
            name = _clean_name(str(raw_name or ""))
            if not name or name in seen or len(name) > 40:
                continue
            seen.add(name)
            merged.append(
                CompanyApplicationScenarioCandidate(
                    company_id=product.company_id,
                    scenario_name=name,
                    description=_trim_description(
                        f"{product.product_name}用于{name}。"
                    ),
                    source_url=source_url,
                    evidence_span=product.evidence_span,
                    confidence=product.confidence,
                    quality_status="needs_review",
                    scenario_category=product.product_category,
                    target_customer=target_customer,
                    related_product_name=product.product_name,
                )
            )
            if len(merged) >= 8:
                return merged
    return merged


def _llm_evidence_span(value: dict[str, Any], source_text: str) -> str:
    evidence = str(value.get("evidence_span") or "").strip()
    if evidence and evidence in source_text:
        return evidence
    return evidence or source_text[:240]


def _llm_confidence(value: Any) -> Decimal:
    try:
        confidence = Decimal(str(value))
    except Exception:
        return Decimal("0.55")
    if confidence <= 0:
        return Decimal("0.55")
    if confidence > 1:
        return Decimal("1.00")
    return confidence.quantize(Decimal("0.01"))


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return _dedupe([str(item) for item in value if str(item or "").strip()])


def _append_product_candidate(
    products: list[CompanyProductCandidate],
    seen: set[str],
    *,
    company_id: str,
    company_name: str,
    source_url: str,
    source_section: str,
    start: int,
    end: int,
    raw_name: str | None,
) -> None:
    name = _clean_name(raw_name)
    if not _valid_product_name(name, company_name=company_name):
        return
    key = name.casefold()
    if key in seen:
        return
    seen.add(key)
    evidence = _sentence_around(source_section, start, end)
    products.append(
        CompanyProductCandidate(
            company_id=company_id,
            product_name=name,
            short_description=_trim_description(evidence),
            official_product_url=source_url,
            evidence_span=_trim_evidence(evidence),
            confidence=Decimal("0.65"),
            quality_status="needs_review",
            **_structured_product_fields(evidence),
        )
    )


def _structured_product_fields(text: str) -> dict[str, object]:
    return {
        "product_category": _product_category(text),
        "target_customers": tuple(
            customer for customer in (_target_customer(text),) if customer
        ),
        "application_scenarios": tuple(_application_scenarios(text)),
        "technical_tags": tuple(_technical_tags(text)),
    }


def _product_category(text: str) -> str | None:
    if "心电" in text and ("诊断" in text or "监护" in text):
        return "心电诊断系统"
    if "机器人" in text and "巡检" in text:
        return "机器人巡检平台"
    if "机器视觉" in text:
        return "机器视觉系统"
    if "传感器" in text:
        return "传感器"
    return None


def _target_customer(text: str) -> str | None:
    if "医院" in text or "临床" in text:
        return "医院/临床机构"
    if "工厂" in text:
        return "工厂"
    if "企业" in text:
        return "企业客户"
    return None


def _application_scenarios(text: str) -> list[str]:
    scenarios: list[str] = []
    if "心电" in text and "诊断" in text:
        if "临床" in text:
            scenarios.append("临床心电诊断")
        if "远程" in text:
            scenarios.append("远程心电诊断")
    if "心电" in text and "监护" in text:
        scenarios.append("心电监护")
    if "机器人" in text and "巡检" in text:
        scenarios.append("机器人巡检")
    if "设备监测" in text or ("设备" in text and "监测" in text):
        scenarios.append("设备监测")
    if "机器视觉" in text and "检测" in text:
        scenarios.append("机器视觉检测")
    return _dedupe(scenarios)


def _technical_tags(text: str) -> list[str]:
    tags: list[str] = []
    normalized = text.replace(" ", "")
    if "AI" in text and "诊断" in text:
        tags.append("AI自动诊断")
    if "心电" in text:
        tags.append("心电系统")
    if "机器人" in text:
        tags.append("机器人")
    if "机器视觉" in text:
        tags.append("机器视觉")
    if "3D激光" in text:
        tags.append("3D激光")
    if "自动诊断" in normalized and "AI自动诊断" not in tags:
        tags.append("自动诊断")
    return _dedupe(tags)


def _scenario_category(scenario_name: str, text: str) -> str | None:
    if any(term in scenario_name for term in ("心电", "诊断", "监护")):
        return "医疗诊断"
    if any(term in scenario_name for term in ("巡检", "设备监测", "机器视觉")):
        return "工业运维"
    if "医疗" in text:
        return "医疗健康"
    return None


def _scenario_description(text: str) -> str:
    return re.sub(r"^(项目简介|产品服务|产品与服务|业务介绍)[:： ]*", "", text).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _productish_section(text: str) -> str | None:
    if not any(hint in text for hint in _PRODUCT_HINTS):
        return None
    marker_positions = [
        position
        for marker in _PRODUCT_SECTION_MARKERS
        if (position := text.find(marker)) >= 0
    ]
    if not marker_positions:
        return text[:800] if len(text) <= 800 else None
    start = min(marker_positions)
    return text[start : start + 800].strip()


def _fallback_project_name(title: str, *, company_name: str) -> str | None:
    raw_name = title or ""
    for separator in ("|", "_", " - ", " | "):
        raw_name = raw_name.split(separator, 1)[0]
    name = _clean_name(raw_name)
    if _looks_like_company_alias(name, company_name=company_name):
        return None
    if not (re.search(r"[A-Za-z]", name) or _has_product_marker(name)):
        return None
    if not _valid_product_name(name, company_name=company_name):
        return None
    return name


def _valid_product_name(
    name: str | None, *, company_name: str, allow_company_alias: bool = False
) -> bool:
    if not name or name in _GENERIC_NAMES:
        return False
    if name in _GENERIC_ASCII_NAMES:
        return False
    if any(marker in name for marker in _LEGAL_NAME_MARKERS):
        return False
    if name.startswith(_BAD_NAME_PREFIXES):
        return False
    if any(term in name for term in _BAD_NAME_SUBSTRINGS):
        return False
    if len(name) > 40:
        return False
    if not allow_company_alias and (name in company_name or company_name in name):
        return False
    return True


def _has_local_product_signal(
    text: str,
    start: int,
    end: int,
    raw_name: str | None,
) -> bool:
    raw_text = (raw_name or "").strip()
    if _LEADING_NAME_NOISE_RE.match(raw_text):
        return True
    name = _clean_name(raw_name)
    if re.search(r"[A-Za-z]", name):
        return True
    left = text[max(0, start - 24) : start]
    if left.endswith(("“", "\"", "'", "《", "「", "『")):
        return True
    if end < len(text) and text[end : end + 1] in {"”", "\"", "'", "》", "」", "』"}:
        return True
    left_tail = left[-12:]
    return bool(
        re.search(
            r"(产品有|产品为|产品包括|主打产品为|自主研发的|自研|推出|提供|包括|拥有)[，、:： ]*$",
            left_tail,
        )
    )


def _looks_like_company_alias(name: str | None, *, company_name: str) -> bool:
    if not name:
        return False
    if name in company_name or company_name in name:
        return True
    return any(marker in name for marker in _LEGAL_NAME_MARKERS)


def _has_product_marker(name: str) -> bool:
    return bool(
        re.search(
            r"(平台|系统|设备|产品|服务|解决方案|方案|传感器|芯片|模组|机器人|"
            r"platform|system|device|sensor|module|chip|solution)",
            name,
            re.IGNORECASE,
        )
    )


def _clean_name(value: str | None) -> str:
    text = (value or "").strip(" \t\r\n，,。.;；:：\"'“”‘’（）()[]【】")
    text = _LEADING_NAME_NOISE_RE.sub("", text)
    return text.strip(" \t\r\n，,。.;；:：\"'“”‘’（）()[]【】")


def _sentence_around(text: str, start: int, end: int) -> str:
    left_candidates = [text.rfind(mark, 0, start) for mark in ("。", ".", "；", ";", "\n")]
    left = max(left_candidates)
    right_candidates = [
        position
        for position in (text.find(mark, end) for mark in ("。", ".", "；", ";", "\n"))
        if position != -1
    ]
    right = min(right_candidates) if right_candidates else min(len(text), end + 180)
    return text[left + 1 : right + 1].strip() or text[max(0, start - 80) : right].strip()


def _normalize_text(value: str | None) -> str:
    text = (value or "").replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def _trim_description(value: str) -> str:
    text = value.strip()
    if len(text) <= 220:
        return text
    return text[:220].rstrip("，。；; ") + "。"


def _trim_evidence(value: str) -> str:
    return value.strip()[:400]
