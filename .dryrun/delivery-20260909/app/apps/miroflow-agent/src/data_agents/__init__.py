"""Shared data-agent contracts, helpers, and provider adapters.

Avoid eager imports so downstream tools can import narrow submodules like
``src.data_agents.storage.sqlite_store`` without pulling in optional runtime deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "CompanyKeyPerson",
    "CompanyRecord",
    "Evidence",
    "PaperRecord",
    "PatentRecord",
    "ProfessorCompanyRole",
    "ProfessorPaperLinkRecord",
    "ProfessorRecord",
    "ReleasedObject",
    "load_domain_cfg",
    "parse_structured_payload",
    "run_structured_task",
    "schema_text_for_model",
]

if TYPE_CHECKING:  # pragma: no cover
    from .contracts import (
        CompanyKeyPerson,
        CompanyRecord,
        Evidence,
        PaperRecord,
        PatentRecord,
        ProfessorCompanyRole,
        ProfessorPaperLinkRecord,
        ProfessorRecord,
        ReleasedObject,
    )
    from .runtime import (
        load_domain_cfg,
        parse_structured_payload,
        run_structured_task,
        schema_text_for_model,
    )


def __getattr__(name: str) -> Any:
    if name in {
        "CompanyKeyPerson",
        "CompanyRecord",
        "Evidence",
        "PaperRecord",
        "PatentRecord",
        "ProfessorCompanyRole",
        "ProfessorPaperLinkRecord",
        "ProfessorRecord",
        "ReleasedObject",
    }:
        from .contracts import (
            CompanyKeyPerson,
            CompanyRecord,
            Evidence,
            PaperRecord,
            PatentRecord,
            ProfessorCompanyRole,
            ProfessorPaperLinkRecord,
            ProfessorRecord,
            ReleasedObject,
        )
        return {
            "CompanyKeyPerson": CompanyKeyPerson,
            "CompanyRecord": CompanyRecord,
            "Evidence": Evidence,
            "PaperRecord": PaperRecord,
            "PatentRecord": PatentRecord,
            "ProfessorCompanyRole": ProfessorCompanyRole,
            "ProfessorPaperLinkRecord": ProfessorPaperLinkRecord,
            "ProfessorRecord": ProfessorRecord,
            "ReleasedObject": ReleasedObject,
        }[name]
    if name in {
        "load_domain_cfg",
        "parse_structured_payload",
        "run_structured_task",
        "schema_text_for_model",
    }:
        from .runtime import (
            load_domain_cfg,
            parse_structured_payload,
            run_structured_task,
            schema_text_for_model,
        )
        return {
            "load_domain_cfg": load_domain_cfg,
            "parse_structured_payload": parse_structured_payload,
            "run_structured_task": run_structured_task,
            "schema_text_for_model": schema_text_for_model,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
