from dataclasses import dataclass, field
from pathlib import Path

from .discovery import FetchHtml, discover_professor_seeds
from .models import DiscoveredProfessorSeed
from .parser import parse_roster_seed_markdown


class SeedDocumentValidationError(ValueError):
    """Raised when the roster seed document cannot produce usable seed URLs."""


@dataclass(frozen=True, slots=True)
class ProfessorRosterValidationReport:
    document_name: str
    seed_source_count: int
    unique_seed_source_count: int
    duplicate_seed_urls: list[str]
    missing_institution_count: int
    discovered_professor_count: int = 0
    unique_professor_identity_count: int = 0
    duplicate_professor_identities: list[str] = field(default_factory=list)
    failed_fetch_urls: list[str] = field(default_factory=list)
    unresolved_seed_source_count: int = 0
    unresolved_seed_sources: list[str] = field(default_factory=list)

    def to_text_lines(self) -> list[str]:
        lines = [
            f"Seed document: {self.document_name}",
            f"Seed URLs: {self.seed_source_count}",
            f"Unique seed URLs: {self.unique_seed_source_count}",
            f"Missing institution context: {self.missing_institution_count}",
            f"Discovered professors: {self.discovered_professor_count}",
            f"Unique professor identities: {self.unique_professor_identity_count}",
        ]
        if self.duplicate_seed_urls:
            lines.append(f"Duplicate seed URLs: {len(self.duplicate_seed_urls)}")
            for url in self.duplicate_seed_urls:
                lines.append(f"  - {url}")
        else:
            lines.append("Duplicate seed URLs: 0")
        if self.duplicate_professor_identities:
            lines.append(
                f"Duplicate professor identities: {len(self.duplicate_professor_identities)}"
            )
            for identity in self.duplicate_professor_identities:
                lines.append(f"  - {identity}")
        else:
            lines.append("Duplicate professor identities: 0")
        if self.failed_fetch_urls:
            lines.append(f"Failed fetch URLs: {len(self.failed_fetch_urls)}")
            for url in self.failed_fetch_urls:
                lines.append(f"  - {url}")
        else:
            lines.append("Failed fetch URLs: 0")
        if self.unresolved_seed_sources:
            lines.append(f"Unresolved seed sources: {self.unresolved_seed_source_count}")
            for source in self.unresolved_seed_sources:
                lines.append(f"  - {source}")
        else:
            lines.append("Unresolved seed sources: 0")
        return lines


def validate_roster_seed_document(
    markdown_text: str,
    document_name: str = "seed.md",
) -> ProfessorRosterValidationReport:
    seeds = parse_roster_seed_markdown(markdown_text)
    if not seeds:
        raise SeedDocumentValidationError(
            f"Seed document '{document_name}' contains no roster URLs."
        )

    counts: dict[str, int] = {}
    for seed in seeds:
        counts[seed.roster_url] = counts.get(seed.roster_url, 0) + 1
    duplicate_seed_urls = sorted(url for url, count in counts.items() if count > 1)

    missing_institution_count = sum(
        1 for seed in seeds if not seed.institution or not seed.institution.strip()
    )

    return ProfessorRosterValidationReport(
        document_name=document_name,
        seed_source_count=len(seeds),
        unique_seed_source_count=len(counts),
        duplicate_seed_urls=duplicate_seed_urls,
        missing_institution_count=missing_institution_count,
    )


def validate_roster_seed_file(path: Path) -> ProfessorRosterValidationReport:
    markdown_text = path.read_text(encoding="utf-8")
    return validate_roster_seed_document(markdown_text, document_name=str(path))


def validate_roster_discovery_document(
    markdown_text: str,
    document_name: str = "seed.md",
    fetch_html: FetchHtml | None = None,
) -> ProfessorRosterValidationReport:
    seeds = parse_roster_seed_markdown(markdown_text)
    if not seeds:
        raise SeedDocumentValidationError(
            f"Seed document '{document_name}' contains no roster URLs."
        )

    seed_url_counts = _count_seed_urls(markdown_text)
    duplicate_seed_urls = sorted(
        url for url, count in seed_url_counts.items() if count > 1
    )
    missing_institution_count = sum(
        1 for seed in seeds if not seed.institution or not seed.institution.strip()
    )
    discovery = discover_professor_seeds(seeds=seeds, fetch_html=fetch_html)
    discovered = discovery.professors

    identity_counts = _count_professor_identities(discovered)
    duplicate_professor_identities = sorted(
        identity for identity, count in identity_counts.items() if count > 1
    )
    unresolved_seed_sources = sorted(
        (
            f"{status.seed_url}|{status.institution}|{status.department or ''}|{status.reason}"
            for status in discovery.source_statuses
            if status.status == "unresolved"
        )
    )

    return ProfessorRosterValidationReport(
        document_name=document_name,
        seed_source_count=len(seeds),
        unique_seed_source_count=len(seed_url_counts),
        duplicate_seed_urls=duplicate_seed_urls,
        missing_institution_count=missing_institution_count,
        discovered_professor_count=len(discovered),
        unique_professor_identity_count=len(identity_counts),
        duplicate_professor_identities=duplicate_professor_identities,
        failed_fetch_urls=discovery.failed_fetch_urls,
        unresolved_seed_source_count=len(unresolved_seed_sources),
        unresolved_seed_sources=unresolved_seed_sources,
    )


def validate_roster_discovery_file(
    path: Path,
    fetch_html: FetchHtml | None = None,
) -> ProfessorRosterValidationReport:
    markdown_text = path.read_text(encoding="utf-8")
    return validate_roster_discovery_document(
        markdown_text=markdown_text,
        document_name=str(path),
        fetch_html=fetch_html,
    )
def _count_seed_urls(markdown_text: str) -> dict[str, int]:
    seeds = parse_roster_seed_markdown(markdown_text)
    counts: dict[str, int] = {}
    for seed in seeds:
        counts[seed.roster_url] = counts.get(seed.roster_url, 0) + 1
    return counts


def _count_professor_identities(
    discovered: list[DiscoveredProfessorSeed],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in discovered:
        key = f"{item.name}|{item.institution}|{item.department or ''}"
        counts[key] = counts.get(key, 0) + 1
    return counts
