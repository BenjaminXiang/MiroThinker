"""Controlled vocabulary and domain-tier seed data.

Used to populate `taxonomy_vocabulary` and `source_domain_tier_registry`
tables. Designed to be re-runnable (idempotent upserts).

See plan docs/plans/2026-04-17-005 §6.7 / §11.2 / §11.3.
"""

from .domain_tier import DOMAIN_TIER_SEEDS, DomainTierSeed
from .seed_data import TAXONOMY_SEEDS, TaxonomySeed

__all__ = [
    "DOMAIN_TIER_SEEDS",
    "DomainTierSeed",
    "TAXONOMY_SEEDS",
    "TaxonomySeed",
]
