"""Initial `source_domain_tier_registry` seeds — 3 tier simplification per plan 005 §11.3.

Three tiers only:
  - official : edu.cn / gov.cn wildcards and companies' canonical website host.
               Single-source verify allowed for institution profile / patent registry.
  - trusted  : 权威/知名媒体. Can back news_item as primary source; needs ≥2 sources
               to promote to a company_signal_event.
  - unknown  : default for all others. Candidate-only evidence.

Runtime matching rules (implemented in `resolve_tier(host) -> str`):
  1. exact host match    -> tier directly
  2. wildcard suffix     -> tier (e.g. host ends with '.edu.cn' -> official)
  3. otherwise           -> 'unknown'

Companies' canonical website hosts are registered dynamically from
`company.website_host` in Phase 1; they are NOT hard-coded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TierName = Literal["official", "trusted", "unknown"]


@dataclass(frozen=True)
class DomainTierSeed:
    domain: str
    tier: TierName
    tier_reason: str
    is_official_for_scope: str | None = None


# ---------------------------------------------------------------------
# tier=official
# ---------------------------------------------------------------------
_OFFICIAL_WILDCARDS: list[DomainTierSeed] = [
    DomainTierSeed(
        ".edu.cn",
        "official",
        "教育部注册高校域名",
        "official_for_institution_profile",
    ),
    DomainTierSeed(
        ".gov.cn",
        "official",
        "政府部门域名",
        "official_for_government_statement",
    ),
    DomainTierSeed(
        ".ac.cn",
        "official",
        "中国科学院 / 学术机构域名",
        "official_for_institution_profile",
    ),
]

_OFFICIAL_EXPLICIT: list[DomainTierSeed] = [
    DomainTierSeed(
        "miit.gov.cn", "official", "工信部", "official_for_government_statement"
    ),
    DomainTierSeed(
        "sipo.gov.cn",
        "official",
        "国家知识产权局",
        "official_for_patent_registry",
    ),
    DomainTierSeed(
        "cnipa.gov.cn",
        "official",
        "国家知识产权局（新域名）",
        "official_for_patent_registry",
    ),
    DomainTierSeed(
        "credit.szmqs.gov.cn",
        "official",
        "深圳市市场监管局 / 信用公示",
        "official_for_company_registry",
    ),
    DomainTierSeed(
        "gsxt.gov.cn",
        "official",
        "国家企业信用信息公示系统",
        "official_for_company_registry",
    ),
]

# ---------------------------------------------------------------------
# tier=trusted（权威/知名媒体；r2 保守起步，不按细分类别切）
# ---------------------------------------------------------------------
_TRUSTED: list[DomainTierSeed] = [
    # 国家级通讯社/权威媒体
    DomainTierSeed("xinhuanet.com", "trusted", "新华社", None),
    DomainTierSeed("people.com.cn", "trusted", "人民网", None),
    DomainTierSeed("cctv.com", "trusted", "央视网", None),
    DomainTierSeed("chinadaily.com.cn", "trusted", "中国日报", None),
    # 财经
    DomainTierSeed("caijing.com.cn", "trusted", "财经网", None),
    DomainTierSeed("21jingji.com", "trusted", "21 世纪经济报道", None),
    DomainTierSeed("yicai.com", "trusted", "第一财经", None),
    DomainTierSeed("caixin.com", "trusted", "财新", None),
    DomainTierSeed("stcn.com", "trusted", "证券时报网", None),
    DomainTierSeed("cnstock.com", "trusted", "中国证券网", None),
    # 科技/创投媒体
    DomainTierSeed("36kr.com", "trusted", "36Kr", None),
    DomainTierSeed("tmtpost.com", "trusted", "钛媒体", None),
    DomainTierSeed("leiphone.com", "trusted", "雷锋网", None),
    DomainTierSeed("geekpark.net", "trusted", "极客公园", None),
    DomainTierSeed("pingwest.com", "trusted", "品玩", None),
    DomainTierSeed("sohu.com/tech", "trusted", "搜狐科技", None),
    DomainTierSeed("technode.com", "trusted", "TechNode", None),
    # 学术发现辅助
    DomainTierSeed("openalex.org", "trusted", "OpenAlex", None),
    DomainTierSeed("semanticscholar.org", "trusted", "Semantic Scholar", None),
    DomainTierSeed("crossref.org", "trusted", "CrossRef", None),
    DomainTierSeed("orcid.org", "trusted", "ORCID", None),
]


DOMAIN_TIER_SEEDS: list[DomainTierSeed] = [
    *_OFFICIAL_WILDCARDS,
    *_OFFICIAL_EXPLICIT,
    *_TRUSTED,
]


def resolve_tier(host: str, company_hosts: set[str] | None = None) -> TierName:
    """Resolve a URL host to its tier.

    Order of resolution:
      1. If `company_hosts` is given and `host` is in that set -> official
         (company's own website counts as official source for its own facts).
      2. Exact match against DOMAIN_TIER_SEEDS.domain (without leading '.').
      3. Wildcard suffix match against seeds whose `domain` starts with '.'.
      4. Default 'unknown'.
    """
    if not host:
        return "unknown"
    host = host.lower().strip()
    if company_hosts and host in company_hosts:
        return "official"

    for seed in DOMAIN_TIER_SEEDS:
        if not seed.domain.startswith("."):
            if host == seed.domain:
                return seed.tier

    for seed in DOMAIN_TIER_SEEDS:
        if seed.domain.startswith("."):
            if host.endswith(seed.domain):
                return seed.tier

    return "unknown"


def as_upsert_rows() -> list[dict[str, str | None]]:
    return [
        {
            "domain": s.domain,
            "tier": s.tier,
            "tier_reason": s.tier_reason,
            "is_official_for_scope": s.is_official_for_scope,
        }
        for s in DOMAIN_TIER_SEEDS
    ]
