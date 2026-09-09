"""Reassess quality_status for all records based on field completeness rules.

Rules:
- Professor:
  - ready: institution + (department OR title) + email + research_directions
  - needs_review: institution + email (but missing dept/title/research)
  - low_confidence: missing institution or email

- Paper:
  - Chinese-titled papers → needs_review (lower quality signal)
  - No venue → needs_review
  - No DOI + no venue → low_confidence

- Company:
  - ready: industry + profile_summary (both always present)
  - needs_review: no website

- Patent: all have required fields → keep as ready
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Ensure repo root on path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "apps" / "miroflow-agent"))

from src.data_agents.contracts import ReleasedObject
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore


def _has(obj: ReleasedObject, field: str) -> bool:
    val = obj.core_facts.get(field)
    if val is None or val == "" or val == []:
        return False
    return True


def _is_chinese_title(name: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", name))


def assess_professor(obj: ReleasedObject) -> str:
    has_inst = _has(obj, "institution")
    has_email = _has(obj, "email")
    has_dept = _has(obj, "department")
    has_title = _has(obj, "title")
    has_research = _has(obj, "research_directions")

    if not has_inst or not has_email:
        return "low_confidence"
    if has_dept and has_research:
        return "ready"
    return "needs_review"


def assess_paper(obj: ReleasedObject) -> str:
    has_venue = _has(obj, "venue")
    has_doi = _has(obj, "doi")
    is_chinese = _is_chinese_title(obj.display_name)

    if not has_venue and not has_doi:
        return "low_confidence"
    if is_chinese:
        return "needs_review"
    if not has_venue:
        return "needs_review"
    return "ready"


def assess_company(obj: ReleasedObject) -> str:
    has_website = _has(obj, "website")
    if not has_website:
        return "needs_review"
    return "ready"


def assess_patent(obj: ReleasedObject) -> str:
    return "ready"


ASSESSORS = {
    "professor": assess_professor,
    "paper": assess_paper,
    "company": assess_company,
    "patent": assess_patent,
}


def main() -> None:
    db_path = _REPO_ROOT / "logs" / "data_agents" / "released_objects.db"
    store = SqliteReleasedObjectStore(db_path)

    for domain, assess_fn in ASSESSORS.items():
        objects = store._load_domain_objects(domain)
        stats = {"ready": 0, "needs_review": 0, "low_confidence": 0}
        changed = 0

        for obj in objects:
            new_status = assess_fn(obj)
            stats[new_status] += 1

            if obj.quality_status != new_status:
                patched = obj.model_copy(update={"quality_status": new_status})
                store.update_object(patched)
                changed += 1

        print(f"\n{domain} ({len(objects)} total, {changed} changed):")
        for status, count in stats.items():
            print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
