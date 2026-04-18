"""Data quality configuration and rule modules.

`threshold_config.py` holds numerical thresholds referenced by verification
pipelines. Rule modules (future `rules/R00X_*.py`) implement individual
quality checks per plan 005 §6.7.
"""

from .threshold_config import (
    AUTHOR_NAME_MATCH_VERIFY_THRESHOLD,
    COMPANY_MERGE_AUTO_REASONS,
    EVENT_CONFIDENCE_FLOOR_BY_TIER,
    INSTITUTION_CONSISTENCY_VERIFY_THRESHOLD,
    PROFESSOR_PAPER_LINK_PROMOTION,
    TOPIC_CONSISTENCY_VERIFY_THRESHOLD,
)

__all__ = [
    "AUTHOR_NAME_MATCH_VERIFY_THRESHOLD",
    "COMPANY_MERGE_AUTO_REASONS",
    "EVENT_CONFIDENCE_FLOOR_BY_TIER",
    "INSTITUTION_CONSISTENCY_VERIFY_THRESHOLD",
    "PROFESSOR_PAPER_LINK_PROMOTION",
    "TOPIC_CONSISTENCY_VERIFY_THRESHOLD",
]
