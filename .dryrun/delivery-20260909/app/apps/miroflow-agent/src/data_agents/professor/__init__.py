"""Professor roster and profile extraction utilities."""

from .discovery import (
    DiscoveryLimits,
    DiscoverySourceStatus,
    FetchHtml,
    ProfessorSeedDiscoveryResult,
    discover_professor_seeds,
    fetch_html_with_fallback,
    get_registered_domain,
)
from .models import DiscoveredProfessorSeed, ExtractedProfessorProfile, ProfessorRosterSeed
from .parser import parse_roster_seed_markdown
from .profile import extract_professor_profile
from .roster import extract_roster_entries, extract_roster_page_links
from .validator import (
    ProfessorRosterValidationReport,
    SeedDocumentValidationError,
    validate_roster_discovery_document,
    validate_roster_discovery_file,
    validate_roster_seed_document,
    validate_roster_seed_file,
)

__all__ = [
    "DiscoveredProfessorSeed",
    "DiscoveryLimits",
    "DiscoverySourceStatus",
    "ExtractedProfessorProfile",
    "FetchHtml",
    "ProfessorRosterSeed",
    "ProfessorRosterValidationReport",
    "ProfessorSeedDiscoveryResult",
    "discover_professor_seeds",
    "extract_professor_profile",
    "extract_roster_page_links",
    "SeedDocumentValidationError",
    "extract_roster_entries",
    "fetch_html_with_fallback",
    "get_registered_domain",
    "parse_roster_seed_markdown",
    "validate_roster_discovery_document",
    "validate_roster_discovery_file",
    "validate_roster_seed_document",
    "validate_roster_seed_file",
]
