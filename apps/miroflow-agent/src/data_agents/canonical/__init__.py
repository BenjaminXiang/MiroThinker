"""Pydantic contracts for the new canonical graph (plan 005).

Split per-domain to keep the modules readable. The legacy single-file
`data_agents/contracts.py` stays intact for the duration of the Phase 3-5
double-write window; new code imports from here.
"""

from .company import (
    Company,
    CompanyFact,
    CompanyNewsItem,
    CompanySignalEvent,
    CompanySnapshot,
    CompanyTeamMember,
)
from .common import (
    EntityMergeAction,
    EvidenceKind,
    IdentityStatus,
    LinkStatus,
    PaperAuthorMatch,
    QualityStatus,
    RunKind,
    RunStatus,
    SeedKind,
)
from .paper import Paper, Patent, ProfessorPaperLink
from .professor import Professor, ProfessorAffiliation, ProfessorFact
from .relations import (
    CompanyPatentLink,
    ProfessorCompanyRole,
    ProfessorPatentLink,
)
from .source import ImportBatch, PipelineRun, SeedRegistry, SourcePage, SourceRowLineage

__all__ = [
    # company
    "Company",
    "CompanyFact",
    "CompanyNewsItem",
    "CompanySignalEvent",
    "CompanySnapshot",
    "CompanyTeamMember",
    # common
    "EntityMergeAction",
    "EvidenceKind",
    "IdentityStatus",
    "LinkStatus",
    "PaperAuthorMatch",
    "QualityStatus",
    "RunKind",
    "RunStatus",
    "SeedKind",
    # paper / patent
    "Paper",
    "Patent",
    "ProfessorPaperLink",
    # professor
    "Professor",
    "ProfessorAffiliation",
    "ProfessorFact",
    # cross-domain relations
    "CompanyPatentLink",
    "ProfessorCompanyRole",
    "ProfessorPatentLink",
    # source
    "ImportBatch",
    "PipelineRun",
    "SeedRegistry",
    "SourcePage",
    "SourceRowLineage",
]
