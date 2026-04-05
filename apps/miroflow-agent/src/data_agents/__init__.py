"""Shared data-agent contracts, helpers, and provider adapters."""

from .contracts import (
    CompanyKeyPerson,
    CompanyRecord,
    Evidence,
    PaperRecord,
    PatentRecord,
    ProfessorCompanyRole,
    ProfessorRecord,
    ReleasedObject,
)
from .runtime import (
    load_domain_cfg,
    parse_structured_payload,
    run_structured_task,
    schema_text_for_model,
)

__all__ = [
    "CompanyKeyPerson",
    "CompanyRecord",
    "Evidence",
    "PaperRecord",
    "PatentRecord",
    "ProfessorCompanyRole",
    "ProfessorRecord",
    "ReleasedObject",
    "load_domain_cfg",
    "parse_structured_payload",
    "run_structured_task",
    "schema_text_for_model",
]
