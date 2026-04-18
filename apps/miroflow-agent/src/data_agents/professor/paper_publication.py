from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from src.data_agents.contracts import PaperRecord, ProfessorPaperLinkRecord, ReleasedObject
from src.data_agents.evidence import build_evidence
from src.data_agents.normalization import build_stable_id
from src.data_agents.paper.models import DiscoveredPaper
from src.data_agents.paper.release import build_paper_release

from .cross_domain import PaperStagingRecord


@dataclass(frozen=True, slots=True)
class PaperDomainPublicationResult:
    paper_records: list[PaperRecord]
    paper_released_objects: list[ReleasedObject]
    link_records: list[ProfessorPaperLinkRecord]
    link_released_objects: list[ReleasedObject]


def build_paper_domain_publication(
    *,
    staging_records: list[PaperStagingRecord],
    now: datetime,
) -> PaperDomainPublicationResult:
    discovered_papers = [_staging_to_discovered_paper(record) for record in staging_records]
    release_result = build_paper_release(papers=discovered_papers, now=now)
    paper_ids_by_key = {
        _paper_record_identity_key(record): record.id
        for record in release_result.paper_records
    }

    link_records: list[ProfessorPaperLinkRecord] = []
    seen_link_keys: set[str] = set()
    for record in staging_records:
        identity_key = _staging_identity_key(record)
        paper_id = paper_ids_by_key.get(identity_key)
        if not paper_id:
            continue
        link_key = f"{record.anchoring_professor_id}|{paper_id}"
        if link_key in seen_link_keys:
            continue
        seen_link_keys.add(link_key)
        evidence_source_type = _link_evidence_source_type(record.source)
        match_reason = _match_reason(record.source)
        link = ProfessorPaperLinkRecord(
            id=build_stable_id('prof-paper-link', link_key),
            professor_id=record.anchoring_professor_id,
            paper_id=paper_id,
            professor_name=record.anchoring_professor_name,
            paper_title=record.title,
            link_status='verified',
            evidence_source=record.source,
            evidence_url=record.source_url,
            match_reason=match_reason,
            verified_by='pipeline_v3_staging',
            evidence=[
                build_evidence(
                    source_type=evidence_source_type,
                    source_url=record.source_url,
                    fetched_at=now,
                    confidence=0.85,
                )
            ],
            last_updated=now,
            quality_status='ready',
        )
        link_records.append(link)

    return PaperDomainPublicationResult(
        paper_records=release_result.paper_records,
        paper_released_objects=release_result.released_objects,
        link_records=link_records,
        link_released_objects=[record.to_released_object() for record in link_records],
    )


def _staging_to_discovered_paper(record: PaperStagingRecord) -> DiscoveredPaper:
    return DiscoveredPaper(
        paper_id=record.doi or build_stable_id('paper-staging', _staging_identity_key(record)),
        title=record.title,
        year=record.year or 0,
        publication_date=None,
        venue=record.venue,
        doi=record.doi,
        arxiv_id=None,
        abstract=record.abstract,
        authors=tuple(record.authors),
        professor_ids=(record.anchoring_professor_id,),
        citation_count=record.citation_count,
        source_url=record.source_url,
        fields_of_study=tuple(record.keywords),
        enrichment_sources=(record.source,),
    )


def _staging_identity_key(record: PaperStagingRecord) -> str:
    if record.doi:
        return f"doi:{record.doi.strip().lower()}"
    return '|'.join([
        'title',
        re.sub(r"\s+", '', record.title).lower(),
        str(record.year or 0),
        ','.join(sorted(author.strip().lower() for author in record.authors if author.strip())),
    ])


def _paper_record_identity_key(record: PaperRecord) -> str:
    if record.doi:
        return f"doi:{record.doi.strip().lower()}"
    if record.arxiv_id:
        return f"arxiv:{record.arxiv_id.strip().lower()}"
    return '|'.join([
        'title',
        re.sub(r"\s+", '', record.title).lower(),
        str(record.year),
        ','.join(sorted(author.strip().lower() for author in record.authors if author.strip())),
    ])


def _link_evidence_source_type(source: str) -> str:
    lowered = source.strip().lower()
    if lowered == 'official_site' or lowered.startswith('official_linked_'):
        return 'official_site'
    if lowered in {'openalex', 'semantic_scholar', 'crossref', 'orcid', 'google_scholar'}:
        return 'academic_platform'
    return 'public_web'


def _match_reason(source: str) -> str:
    lowered = source.strip().lower()
    if lowered == 'official_site':
        return 'Verified from an official publication list collected during professor enrichment.'
    if lowered.startswith('official_linked_'):
        return 'Verified from an academic profile explicitly linked by the official professor page.'
    return 'Verified from professor-anchored academic paper discovery during professor enrichment.'
