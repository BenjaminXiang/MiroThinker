"""Build one complete Canonical V2 candidate on explicit isolated targets.

The module deliberately keeps the public seam small: callers provide the three
marked targets and boundary adapters, then call ``KnowledgeBuild.build`` once.
All logical composition remains owned here; the injected boundary can only
stage bytes, retain typed values, and materialize/audit the physical index.
"""

from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import secrets
from threading import Condition
from typing import Any, Literal, Protocol, cast

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import (
    Field,
    JsonValue,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from sqlalchemy.engine import make_url

from src.data_agents.contracts import ReleasedObject as HistoricalReleasedObject
from src.data_agents.company.vectorizer import (
    EmbeddingClient as _OpenAIEmbeddingClient,
)
from src.data_agents.providers.local_api_key import load_local_api_key
from src.data_agents.storage.database_target import (
    DatabaseTargetSafetyError,
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)

from .candidate_projection import (
    CandidateProjectionRequest,
    CandidateProjectionResult,
    compose_candidate_projections,
)
from .canonical_decision_engine import (
    DecisionBatchRequest,
    DecisionBatchResult,
    FieldAssertionGroup,
    RecordedAdjudication,
    RelationshipAssertionGroup,
    create_ephemeral_canonical_decision_engine,
    create_recorded_structured_adjudicator,
)
from .canonical_decision_postgres import create_postgres_canonical_decision_store
from .canonical_identity_resolution import (
    CANONICAL_IDENTITY_METHOD_VERSION_V2,
    IdentityResolutionRequest,
    IdentityResolutionResult,
    PERSON_IDENTITY_METHOD_VERSION,
    create_ephemeral_canonical_identity_resolution_engine,
)
from .canonical_identity_postgres import (
    OFFLINE_BUILD_AUTHORITY,
    create_postgres_canonical_identity_store,
)
from .contracts import (
    BuildManifest,
    CandidateRelease,
    CanonicalDatetime,
    CanonicalIdentityState,
    ContractModel,
    DecisionMethod,
    EvidenceArtifact,
    IdentityReference,
    IdentitySpace,
    KnowledgeGap,
    ManifestSection,
    NonEmptyStr,
    ParseStatus,
    PolicyKind,
    PolicyReference,
    ReleaseVerification,
    RelationshipType,
    Sha256,
    SourceAssertion,
    SourceError,
    SourceErrorKind,
    SourceIdentity,
    SourceIdentityState,
    SourceRecord,
    TemporalInstantValue,
    RelationshipAssertion,
    ReleaseState,
)
from .evidence_adapters import HistoricalJsonlAdapter, HistoricalXlsxAdapter
from .domain_catalog import (
    CATALOG_CONTENT_SHA256,
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
)
from .domain_inclusion import (
    ApprovedSourceBatch,
    InclusionBatchRequest,
    InclusionCandidate,
    create_approved_source_scope_manifest,
    create_ephemeral_domain_inclusion_engine,
)
from .domain_projection import (
    DomainProjectionRequest,
    DomainProjectionResult,
    create_ephemeral_domain_projection_builder,
)
from .domain_projection_postgres import create_postgres_domain_projection_store
from .domain_projection_models import NamedReference
from .evidence_landing import (
    AdapterInput,
    EvidenceLandingService,
    IngestEvidenceRequest,
    LandingReceipt,
    ParsedRecordDraft,
    ParserReference,
    RegisterArtifactRequest,
)
from .evidence_landing_postgres import PostgresLandingRepository
from .index_projection import (
    IndexProjectionActualState,
    IndexProjectionBuilder,
    IndexProjectionRequest,
    IndexProjectionResult,
    create_ephemeral_index_projection_builder,
)
from .index_projection_isolated import (
    IsolatedIndexTarget,
    RecordedEmbeddingAdapter,
    audit_isolated_index_snapshot,
    create_isolated_index_projection_builder,
    prepare_isolated_index_target,
)
from .internal_reference_catalog import (
    REFERENCE_CATALOG_CONTENT_SHA256,
    REFERENCE_CATALOG_SCHEMA_VERSION,
    REFERENCE_CATALOG_VERSION,
)
from .internal_reference_projection import (
    InternalReferenceProjectionRequest,
    InternalReferenceProjectionResult,
    ReferenceCatalogIdentity,
    create_ephemeral_internal_reference_projection_builder,
)
from .knowledge_build import (
    BuildCandidateRequest,
    KnowledgeBuild,
    create_ephemeral_knowledge_build,
)
from .knowledge_gap_feedback import (
    GapSignal,
    GapTrigger,
    create_ephemeral_knowledge_gap_feedback,
)
from .knowledge_gap_postgres import create_postgres_knowledge_gap_operations
from .knowledge_read import InstitutionCatalog
from .knowledge_serving_isolated import load_recorded_serving_inputs
from .path_eligibility import (
    PUBLISHED_USER_PATHS,
    PathEligibilityEngine,
    PathEligibilityRequest,
    PathEligibilityResult,
    TypedProjectionInput,
)
from .patent_applicant_linking import (
    CompanyNameEntry,
    build_company_name_index,
    resolve_patent_applicant_links,
)
from .relationship_projection import (
    INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256,
    INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION,
    LEGACY_RELATIONSHIP_REGISTRY_CONTENT_SHA256,
    LEGACY_RELATIONSHIP_REGISTRY_VERSION,
    RelationshipCatalogIdentity,
    RelationshipDecisionInput,
    RelationshipEndpointReference,
    RelationshipProjectionCandidate,
    RelationshipProjectionRequest,
    RelationshipProjectionResult,
    RetainedAssertionReference,
    RetainedEvidenceBinding,
    SourceCanonicalAssignment,
    TypedRelationshipAssertionInput,
    create_ephemeral_relationship_projection,
)
from .relationship_projection_postgres import (
    create_postgres_relationship_projection_store,
)
from .rebuild_write_gate import BackupGateReceipt, require_accepted_backup_gate
from .release_publication import create_ephemeral_release_publication
from .release_publication_isolated import IsolatedReleaseBundle


_ZERO_SHA256 = "0" * 64
_SOURCE_INVENTORY_SHA256 = (
    "83a9e2c82aee4cbe5c02f088ba0fdbf8d15359d87a85bf4ee901b0f58f70fa09"
)
_BACKUP_MANIFEST_SHA256 = (
    "a14c1eab673f8fca2bdbf4d50dfe8e9b33cf077b9314855298d29a16a82e59c8"
)
_RESTORE_VERIFICATION_SHA256 = (
    "98826e8da7ee66af20199c4998f4cdccc9276179119f30cd318f7ce8c0e7d231"
)
_ACCEPTANCE_RECORD_SHA256 = (
    "3155d8908ab560d8d97ed08881f067564f38e23c097e46fe111a056ef739fc5b"
)
_RELEASED_OBJECTS_SOURCE_ID = (
    "inventory:ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0"
)
_RELEASED_OBJECTS_SHA256 = (
    "7637d808559685f1bcf0316cd22cfeac4e50bd0850c53652ec95b3dbb5e43bce"
)
_RELEASED_OBJECTS_MEMBER_SIZE = 20_267_008
_RELEASED_OBJECTS_MEMBER_ID = (
    "accepted-restore:workspace/logs/data_agents/released_objects.db"
)
_RELEASED_OBJECTS_RESTORE_MEMBER_PATH = Path(
    "workspace/logs/data_agents/released_objects.db"
)
_RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH = Path(
    "manifests/inventory/"
    "027-ffe87de3fe5cefe929194235d43fe7bcf09be406976a81cea23efb464d4d34a0.jsonl"
)
_RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256 = (
    "6820786a2e055def2828c82de60f3b90cad9ac5dcc8f1477943a9f46a02777ae"
)
_RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256 = (
    "4c91d1d7dce88e5c9d9924b2c21d6f3111292eb3e5c30a60e688fd40ccf8b594"
)
_ACCEPTED_ORIGINAL_MILVUS_SHA256 = (
    "43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc"
)
_ACCEPTED_ORIGINAL_MILVUS_RECORD_SHA256 = (
    "df3715a0be8560d523ce2abb589bdaf690e0fe07babcad26c03a4da0ad8cbe6b"
)
_RECORDED_DECISION_BUNDLE_SHA256 = (
    "6d7fa297838812bf6e3692bb32ff1133239be692d675ad8be749aeca9c7487b4"
)
_RECORDED_EMBEDDING_BUNDLE_SHA256 = (
    "a5b57005eb48a0692ae946d83c02ce54df0280a8274527f94c29d79d81266200"
)
_RECORDED_EMBEDDING_DIMENSION = 32
_QWEN_EMBEDDING_BUNDLE_SHA256 = (
    "05473fabc8055e9ce3ebca9d846761cab7cb8c89eb51c96607172c402d1f46db"
)
_QWEN_EMBEDDING_DIMENSION = 4096
_ACCEPTED_EMBEDDING_AUTHORITIES = frozenset(
    {
        (_RECORDED_EMBEDDING_BUNDLE_SHA256, _RECORDED_EMBEDDING_DIMENSION),
        (_QWEN_EMBEDDING_BUNDLE_SHA256, _QWEN_EMBEDDING_DIMENSION),
    }
)
_EXPECTED_OBJECT_COUNTS = {
    "company": 1037,
    "paper": 574,
    "patent": 1931,
    "professor": 1439,
    "professor_paper_link": 580,
}
_PUBLIC_DOMAINS = ("company", "paper", "patent", "professor")
# Only name+institution stay hard professor requirements.  The other
# historically required fields degrade to quality signals carrying this
# explicit placeholder so the typed projection contract still validates.
# The placeholder is excluded from identity keys and author-attribution
# signatures because it is not identity evidence.
_PROFESSOR_MISSING_FIELD_FALLBACK = "Not supplied by the historical source."
_PROFESSOR_PROFILE_SUMMARY_FALLBACK = (
    "No dedicated summary was supplied by the historical source."
)
_PROFESSOR_DEGRADABLE_FIELDS = (
    "department",
    "email",
    "homepage",
    "profile_summary",
    "title",
)
# Generic faculty-page section labels observed as extracted professor
# "names" (s12e professor audit: 师资列表×2, 教育经历×2, 师资介绍, 相关教师
# plus conservative equivalents).  They are extraction pollution, not
# people, so they stay hard rejections next to the name+institution check.
_PROFESSOR_POLLUTION_NAME_LABELS = frozenset(
    {
        "师资列表",
        "师资介绍",
        "教育经历",
        "相关教师",
        "教师名录",
        "科研成果",
    }
)
# Anti-scrape reversed emails (s12e professor audit: 41 records).  Historical
# faculty pages obfuscate addresses by reversing the whole string, e.g.
# "moc.liamg@abc" for "abc@gmail.com"; the reversed-TLD label then leads the
# local part.  Decode only when the reversed text verifies as a well-formed
# address on a known public TLD and the raw value does not; otherwise keep
# the raw value and flag it instead of guessing.
_REVERSED_EMAIL_LOCAL_PREFIXES = ("gro.", "moc.", "nc.", "ten.", "ude.", "vog.")
_DECODABLE_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\."
    r"(?:biz|cn|com|edu|gov|info|io|me|net|org)$"
)
_EXPECTED_ALEMBIC_REVISION = "C2_0011"
_OWNER_SCHEMAS = (
    "company",
    "knowledge",
    "landing",
    "ops",
    "paper",
    "patent",
    "professor",
    "publish",
)
_EXPECTED_OWNER_TABLES: frozenset[str] = frozenset(
    """
    company.business_scenario company.capability company.current_projection
    company.financing_event company.key_personnel company.personnel_education
    company.personnel_work_experience company.product company.public_update
    knowledge.canonical_decision knowledge.canonical_decision_assertion
    knowledge.canonical_decision_constraint_outcome
    knowledge.canonical_decision_identity_context knowledge.canonical_identity
    knowledge.canonical_identity_lineage knowledge.canonical_identity_source_membership
    knowledge.current_relationship_projection knowledge.current_source_identity_assignment
    knowledge.decision_batch_temporal_context knowledge.domain_inclusion_decision
    knowledge.domain_inclusion_decision_assertion knowledge.domain_projection_lineage
    knowledge.domain_projection_manifest knowledge.identity_candidate_verdict
    knowledge.identity_decision knowledge.identity_decision_assertion
    knowledge.identity_decision_context knowledge.identity_decision_input
    knowledge.identity_decision_output knowledge.identity_decision_output_source
    knowledge.identity_decision_record knowledge.identity_decision_source_identity
    knowledge.identity_resolution_run knowledge.policy knowledge.relationship_assertion
    knowledge.relationship_decision knowledge.relationship_decision_assertion
    knowledge.relationship_decision_constraint_outcome
    knowledge.relationship_decision_identity_context knowledge.relationship_projection_outcome
    knowledge.relationship_projection_run knowledge.relationship_projection_shared_assertion
    knowledge.relationship_projection_shared_decision knowledge.relationship_type
    knowledge.release knowledge.source_assertion knowledge.source_identity
    knowledge.source_identity_record knowledge.typed_relationship_assertion
    knowledge.typed_relationship_decision knowledge.typed_relationship_decision_assertion
    landing.evidence_artifact landing.ingest_run landing.parser_run landing.source_error
    landing.source_record ops.gap_remediation_transition ops.knowledge_gap paper.author
    paper.current_projection paper.enrichment_provenance paper.full_text paper.funding
    paper.identifier paper.publication paper.reference paper.summary patent.applicant
    patent.current_projection patent.inventor patent.ipc_classification
    patent.patent_milestone patent.technical_summary professor.affiliation_history
    professor.award professor.contact professor.current_projection
    professor.education_history professor.metric_snapshot professor.research_project
    professor.work_history publish.active_release publish.build_manifest
    publish.manifest_section
    """.split()
)
_EXPECTED_LIVE_SCHEMA_CATALOG_COUNTS = {
    "column": 1362,
    "constraint": 1110,
    "index": 166,
    "internal_trigger_summary": 1,
    "relation": 85,
    "routine": 47,
    "schema": 8,
    "server": 1,
    "trigger": 267,
    "view": 1,
}
_EXPECTED_LIVE_SCHEMA_CATALOG_SHA256 = (
    "7605fd00290741478b0cda727b9a6869e731d3a94d0b7bd6ab5ad9b8a59fcdfc"
)
_LIBPQ_CONNECTION_ENVIRONMENT_KEYS = frozenset(
    {
        "PGAPPNAME",
        "PGCHANNELBINDING",
        "PGCLIENTENCODING",
        "PGCONNECT_TIMEOUT",
        "PGDATABASE",
        "PGDATESTYLE",
        "PGGSSDELEGATION",
        "PGGSSENCMODE",
        "PGGSSLIB",
        "PGGEQO",
        "PGHOST",
        "PGHOSTADDR",
        "PGKRBSRVNAME",
        "PGLOADBALANCEHOSTS",
        "PGMAXPROTOCOLVERSION",
        "PGMINPROTOCOLVERSION",
        "PGOPTIONS",
        "PGPASSFILE",
        "PGPASSWORD",
        "PGPORT",
        "PGREQUIREAUTH",
        "PGREQUIREPEER",
        "PGREQUIRESSL",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSSLCERT",
        "PGSSLCERTMODE",
        "PGSSLCOMPRESSION",
        "PGSSLCRL",
        "PGSSLCRLDIR",
        "PGSSLKEY",
        "PGSSLMAXPROTOCOLVERSION",
        "PGSSLMINPROTOCOLVERSION",
        "PGSSLMODE",
        "PGSSLNEGOTIATION",
        "PGSSLROOTCERT",
        "PGSSLSNI",
        "PGTARGETSESSIONATTRS",
        "PGTZ",
        "PGUSER",
    }
)

_LIVE_SCHEMA_CATALOG_SQL = """
WITH owner_schema AS (
    SELECT namespace.oid AS schema_oid, namespace.nspname
    FROM pg_catalog.pg_namespace AS namespace
    WHERE namespace.nspname = ANY(%s::text[])
), catalog AS (
    SELECT
        'server'::text AS object_kind,
        'postgresql-database'::text AS object_identity,
        jsonb_build_object(
            'server_version_num', current_setting('server_version_num')::integer,
            'server_encoding', current_setting('server_encoding'),
            'database_encoding', pg_catalog.pg_encoding_to_char(
                database_value.encoding
            ),
            'collation', database_value.datcollate,
            'ctype', database_value.datctype,
            'locale_provider', database_value.datlocprovider::text,
            'icu_locale', database_value.daticulocale,
            'collation_version', database_value.datcollversion,
            'actual_collation_version',
                pg_catalog.pg_database_collation_actual_version(database_value.oid)
        ) AS definition
    FROM pg_catalog.pg_database AS database_value
    WHERE database_value.datname = current_database()
    UNION ALL
    SELECT
        'schema',
        owner.nspname,
        '{}'::jsonb
    FROM owner_schema AS owner
    UNION ALL
    SELECT
        'relation',
        owner.nspname || '.' || relation.relname,
        jsonb_build_object(
            'relkind', relation.relkind::text,
            'relpersistence', relation.relpersistence::text,
            'row_security', relation.relrowsecurity,
            'force_row_security', relation.relforcerowsecurity,
            'replica_identity', relation.relreplident::text,
            'access_method', access_method.amname,
            'partition_key', CASE
                WHEN relation.relkind = 'p'
                THEN pg_catalog.pg_get_partkeydef(relation.oid)
                ELSE NULL
            END,
            'options', COALESCE(to_jsonb(relation.reloptions), '[]'::jsonb)
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
    LEFT JOIN pg_catalog.pg_am AS access_method
      ON access_method.oid = relation.relam
    WHERE relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
    UNION ALL
    SELECT
        'column',
        owner.nspname || '.' || relation.relname || ':'
            || attribute.attnum::text || ':' || attribute.attname,
        jsonb_build_object(
            'position', attribute.attnum,
            'name', attribute.attname,
            'type', pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
            'not_null', attribute.attnotnull,
            'default', pg_catalog.pg_get_expr(
                default_value.adbin, default_value.adrelid, false
            ),
            'identity', attribute.attidentity::text,
            'generated', attribute.attgenerated::text,
            'storage', attribute.attstorage::text,
            'compression', attribute.attcompression::text,
            'collation', CASE
                WHEN attribute.attcollation = 0 THEN NULL
                ELSE collation_namespace.nspname || '.' || collation_value.collname
            END
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
     AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
    JOIN pg_catalog.pg_attribute AS attribute
      ON attribute.attrelid = relation.oid
     AND attribute.attnum > 0
     AND NOT attribute.attisdropped
    LEFT JOIN pg_catalog.pg_attrdef AS default_value
      ON default_value.adrelid = relation.oid
     AND default_value.adnum = attribute.attnum
    LEFT JOIN pg_catalog.pg_collation AS collation_value
      ON collation_value.oid = attribute.attcollation
    LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
      ON collation_namespace.oid = collation_value.collnamespace
    UNION ALL
    SELECT
        'constraint',
        owner.nspname || '.' || relation.relname || ':' || constraint_value.conname,
        jsonb_build_object(
            'kind', constraint_value.contype::text,
            'deferrable', constraint_value.condeferrable,
            'initially_deferred', constraint_value.condeferred,
            'validated', constraint_value.convalidated,
            'definition', pg_catalog.pg_get_constraintdef(
                constraint_value.oid, false
            )
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
     AND relation.relkind IN ('r', 'p')
    JOIN pg_catalog.pg_constraint AS constraint_value
      ON constraint_value.conrelid = relation.oid
    UNION ALL
    SELECT
        'index',
        owner.nspname || '.' || table_value.relname || ':' || index_value.relname,
        jsonb_build_object(
            'unique', index_metadata.indisunique,
            'primary', index_metadata.indisprimary,
            'exclusion', index_metadata.indisexclusion,
            'valid', index_metadata.indisvalid,
            'ready', index_metadata.indisready,
            'live', index_metadata.indislive,
            'clustered', index_metadata.indisclustered,
            'check_xmin', index_metadata.indcheckxmin,
            'replica_identity', index_metadata.indisreplident,
            'definition', pg_catalog.pg_get_indexdef(
                index_metadata.indexrelid, 0, false
            )
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS table_value
      ON table_value.relnamespace = owner.schema_oid
     AND table_value.relkind IN ('r', 'p')
    JOIN pg_catalog.pg_index AS index_metadata
      ON index_metadata.indrelid = table_value.oid
    JOIN pg_catalog.pg_class AS index_value
      ON index_value.oid = index_metadata.indexrelid
    UNION ALL
    SELECT
        'trigger',
        owner.nspname || '.' || relation.relname || ':' || trigger_value.tgname,
        jsonb_build_object(
            'enabled', trigger_value.tgenabled::text,
            'deferrable', trigger_value.tgdeferrable,
            'initially_deferred', trigger_value.tginitdeferred,
            'definition', pg_catalog.pg_get_triggerdef(trigger_value.oid, false)
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
     AND relation.relkind IN ('r', 'p')
    JOIN pg_catalog.pg_trigger AS trigger_value
      ON trigger_value.tgrelid = relation.oid
     AND NOT trigger_value.tgisinternal
    UNION ALL
    SELECT
        'internal_trigger_summary',
        'owner-schemas',
        jsonb_build_object(
            'count', count(*),
            'origin_count', count(*) FILTER (WHERE trigger_value.tgenabled = 'O'),
            'disabled_count', count(*) FILTER (WHERE trigger_value.tgenabled = 'D'),
            'replica_count', count(*) FILTER (WHERE trigger_value.tgenabled = 'R'),
            'always_count', count(*) FILTER (WHERE trigger_value.tgenabled = 'A')
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
     AND relation.relkind IN ('r', 'p')
    JOIN pg_catalog.pg_trigger AS trigger_value
      ON trigger_value.tgrelid = relation.oid
     AND trigger_value.tgisinternal
    UNION ALL
    SELECT
        'routine',
        owner.nspname || '.' || routine.proname || '('
            || pg_catalog.pg_get_function_identity_arguments(routine.oid) || ')',
        jsonb_build_object(
            'result', pg_catalog.pg_get_function_result(routine.oid),
            'language', language.lanname,
            'kind', routine.prokind::text,
            'volatility', routine.provolatile::text,
            'parallel', routine.proparallel::text,
            'strict', routine.proisstrict,
            'security_definer', routine.prosecdef,
            'leakproof', routine.proleakproof,
            'configuration', COALESCE(to_jsonb(routine.proconfig), '[]'::jsonb),
            'definition', pg_catalog.pg_get_functiondef(routine.oid)
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_proc AS routine
      ON routine.pronamespace = owner.schema_oid
    JOIN pg_catalog.pg_language AS language
      ON language.oid = routine.prolang
    UNION ALL
    SELECT
        'type',
        owner.nspname || '.' || type_value.typname,
        jsonb_build_object(
            'kind', type_value.typtype::text,
            'base_type', CASE
                WHEN type_value.typbasetype = 0 THEN NULL
                ELSE pg_catalog.format_type(
                    type_value.typbasetype, type_value.typtypmod
                )
            END,
            'not_null', type_value.typnotnull,
            'default', type_value.typdefault,
            'enum_labels', COALESCE((
                SELECT jsonb_agg(enum_value.enumlabel ORDER BY enum_value.enumsortorder)
                FROM pg_catalog.pg_enum AS enum_value
                WHERE enum_value.enumtypid = type_value.oid
            ), '[]'::jsonb),
            'constraints', COALESCE((
                SELECT jsonb_agg(
                    pg_catalog.pg_get_constraintdef(type_constraint.oid, false)
                    ORDER BY type_constraint.conname
                )
                FROM pg_catalog.pg_constraint AS type_constraint
                WHERE type_constraint.contypid = type_value.oid
            ), '[]'::jsonb)
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_type AS type_value
      ON type_value.typnamespace = owner.schema_oid
    WHERE type_value.typtype IN ('d', 'e')
       OR (type_value.typtype = 'c' AND type_value.typrelid = 0)
    UNION ALL
    SELECT
        'policy',
        owner.nspname || '.' || relation.relname || ':' || policy.polname,
        jsonb_build_object(
            'permissive', policy.polpermissive,
            'roles', to_jsonb(policy.polroles),
            'command', policy.polcmd::text,
            'using', pg_catalog.pg_get_expr(policy.polqual, policy.polrelid, false),
            'check', pg_catalog.pg_get_expr(
                policy.polwithcheck, policy.polrelid, false
            )
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
     AND relation.relkind IN ('r', 'p')
    JOIN pg_catalog.pg_policy AS policy
      ON policy.polrelid = relation.oid
    UNION ALL
    SELECT
        'rule',
        owner.nspname || '.' || relation.relname || ':' || rule.rulename,
        jsonb_build_object(
            'enabled', rule.ev_enabled::text,
            'definition', pg_catalog.pg_get_ruledef(rule.oid, false)
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = owner.schema_oid
    JOIN pg_catalog.pg_rewrite AS rule
      ON rule.ev_class = relation.oid
     AND rule.rulename <> '_RETURN'
    UNION ALL
    SELECT
        'view',
        owner.nspname || '.' || view_value.relname,
        jsonb_build_object(
            'options', COALESCE(to_jsonb(view_value.reloptions), '[]'::jsonb),
            'definition', pg_catalog.pg_get_viewdef(view_value.oid, false)
        )
    FROM owner_schema AS owner
    JOIN pg_catalog.pg_class AS view_value
      ON view_value.relnamespace = owner.schema_oid
     AND view_value.relkind = 'v'
)
SELECT object_kind, object_identity, definition
FROM catalog
ORDER BY object_kind, object_identity
"""


class IsolatedKnowledgeBuildError(RuntimeError):
    """The isolated candidate could not reach a verified success envelope."""


class IsolatedKnowledgeBuildSafetyError(IsolatedKnowledgeBuildError):
    """An input or target failed the pre-effect isolation gate."""


class SourceBuildManifestError(IsolatedKnowledgeBuildSafetyError):
    """The source-build manifest is not the exact accepted source authority."""


def _canonical_sha256(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class _DuplicateJsonKeyError(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"duplicate JSON object key: {key!r}")


def _load_unique_json_object(raw: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise _DuplicateJsonKeyError(key)
            value[key] = item
        return value

    def reject_nonfinite(value: str) -> Any:
        raise ValueError(f"non-finite JSON number is not accepted: {value}")

    parsed = json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_constant=reject_nonfinite,
    )
    if not isinstance(parsed, dict):
        raise ValueError("released_objects payload_json must be an object")
    return parsed


def _schema_catalog_sha256(rows: tuple[Mapping[str, Any], ...]) -> str:
    normalized: list[dict[str, JsonValue]] = []
    identities: set[tuple[str, str]] = set()
    for row in rows:
        if set(row) != {"object_kind", "object_identity", "definition"}:
            raise ValueError("live schema catalog row shape differs")
        object_kind = row["object_kind"]
        object_identity = row["object_identity"]
        definition = row["definition"]
        if (
            not isinstance(object_kind, str)
            or not object_kind
            or not isinstance(object_identity, str)
            or not object_identity
        ):
            raise ValueError("live schema catalog identity is invalid")
        identity = (object_kind, object_identity)
        if identity in identities:
            raise ValueError("live schema catalog identities must be unique")
        identities.add(identity)
        normalized.append(
            {
                "object_kind": object_kind,
                "object_identity": object_identity,
                "definition": cast(JsonValue, definition),
            }
        )
    normalized.sort(key=lambda item: (item["object_kind"], item["object_identity"]))
    return _canonical_sha256(cast(JsonValue, normalized))


def _live_schema_catalog_sha256(connection: Any) -> str:
    rows = tuple(
        cast(Mapping[str, Any], row)
        for row in connection.execute(
            _LIVE_SCHEMA_CATALOG_SQL,
            (list(_OWNER_SCHEMAS),),
        ).fetchall()
    )
    counts = dict(sorted(Counter(str(row["object_kind"]) for row in rows).items()))
    if counts != _EXPECTED_LIVE_SCHEMA_CATALOG_COUNTS:
        raise ValueError(
            "candidate database live schema object counts differ: "
            f"expected={_EXPECTED_LIVE_SCHEMA_CATALOG_COUNTS}, observed={counts}"
        )
    return _schema_catalog_sha256(rows)


_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE = {
    "company": (
        "core_facts.aliases",
        "core_facts.industry",
        "core_facts.key_personnel",
        "core_facts.name",
        "core_facts.normalized_name",
        "core_facts.website",
        "summary_fields.profile_summary",
        "summary_fields.technology_route_summary",
    ),
    "paper": (
        "core_facts.arxiv_id",
        "core_facts.authors",
        "core_facts.doi",
        "core_facts.pdf_path",
        "core_facts.title",
        "core_facts.venue",
        "core_facts.year",
        "summary_fields.summary_text",
    ),
    "patent": (
        "core_facts.applicants",
        "core_facts.company_ids",
        "core_facts.filing_date",
        "core_facts.inventors",
        "core_facts.patent_number",
        "core_facts.publication_date",
        "core_facts.title",
        "summary_fields.summary_text",
    ),
    "professor": (
        "core_facts.canonical_name_zh",
        "core_facts.company_roles",
        "core_facts.department",
        "core_facts.email",
        "core_facts.homepage",
        "core_facts.institution",
        "core_facts.name",
        "core_facts.paper_summary",
        "core_facts.patent_ids",
        "core_facts.patent_summary",
        "core_facts.research_directions",
        "core_facts.title",
        "summary_fields.profile_summary",
    ),
    "professor_paper_link": (
        "core_facts.paper_id",
        "core_facts.professor_id",
    ),
}
_RELEASED_OBJECTS_MAPPER_POLICY = cast(
    JsonValue,
    {
        "schema_version": "canonical-v2-released-objects-mapper-policy-v2",
        "policy_version": "canonical-v2-released-objects-mapper-v2",
        "allowed_fields_by_object_type": {
            object_type: list(paths)
            for object_type, paths in _ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE.items()
        },
        "expected_row_counts": _EXPECTED_OBJECT_COUNTS,
        "product_capability": "answer_scoped_only",
        "public_domains": list(_PUBLIC_DOMAINS),
    },
)
_RELEASED_OBJECTS_MAPPER_POLICY_SHA256 = _canonical_sha256(
    _RELEASED_OBJECTS_MAPPER_POLICY
)


def _model_sha256(value: ContractModel) -> str:
    return _canonical_sha256(
        cast(JsonValue, value.model_dump(mode="json", exclude={"content_sha256"}))
    )


class _ContentAddressedModel(ContractModel):
    content_sha256: Sha256 = _ZERO_SHA256

    @model_validator(mode="after")
    def bind_content_sha256(self, info: ValidationInfo) -> _ContentAddressedModel:
        if info.context and info.context.get("external_content_addressed"):
            if (
                "content_sha256" not in self.model_fields_set
                or self.content_sha256 == _ZERO_SHA256
            ):
                raise ValueError(
                    "external content-addressed values require an explicit nonzero hash"
                )
        expected = _model_sha256(self)
        if self.content_sha256 == _ZERO_SHA256:
            object.__setattr__(self, "content_sha256", expected)
        elif self.content_sha256 != expected:
            raise ValueError("content_sha256 must bind the complete normalized value")
        return self


class SourceDisposition(str, Enum):
    evidence_input = "evidence_input"
    requirements_only = "requirements_only"
    acceptance_only = "acceptance_only"
    protection_only = "protection_only"
    registered_unprojected = "registered_unprojected"
    unrecoverable = "unrecoverable"


class SourceBuildMember(ContractModel):
    member_id: NonEmptyStr
    source_batch_id: NonEmptyStr
    source_kind: NonEmptyStr
    content_path: Path
    restore_member_path: Path | None = None
    backup_member_manifest_path: Path | None = None
    backup_member_manifest_sha256: Sha256 | None = None
    source_member_manifest_sha256: Sha256 | None = None
    byte_size: int = Field(ge=0)
    content_sha256: Sha256
    parser: ParserReference
    observed_at: CanonicalDatetime
    parent_source_id: NonEmptyStr

    @field_validator("content_sha256")
    @classmethod
    def require_nonzero_content_sha256(cls, value: str) -> str:
        if value == _ZERO_SHA256:
            raise ValueError("source member content hash must be nonzero")
        return value


class SourceBuildEntry(ContractModel):
    source_id: NonEmptyStr
    disposition: SourceDisposition
    source_family: NonEmptyStr
    members: tuple[SourceBuildMember, ...]
    approval_reference: NonEmptyStr | None
    gap_id: NonEmptyStr | None
    rationale: NonEmptyStr


@dataclass(frozen=True, slots=True)
class _SupplementalSourceAuthority:
    filename: str
    byte_size: int
    content_sha256: str
    # S12B backup lineage is null only for authorities admitted after the
    # Accepted S2B checkpoint (the s12f professor backfill); the r7 fixed
    # sources all carry their exact historical backup identity.
    backup_manifest_filename: str | None
    backup_manifest_sha256: str | None
    source_member_manifest_sha256: str | None
    source_kind: str
    source_batch_id: str
    parser_name: str
    parser_options: dict[str, JsonValue]

    @property
    def restore_member_path(self) -> Path:
        return Path("workspace/docs/source_backfills") / self.filename

    @property
    def member_id(self) -> str:
        return f"accepted-restore:{self.restore_member_path}"

    @property
    def backup_member_manifest_path(self) -> Path | None:
        if self.backup_manifest_filename is None:
            return None
        return Path("manifests/inventory") / self.backup_manifest_filename


# S12F professor backfill authority.  The s12e professor audit demoted 882
# professors to explicit placeholder fields; the 16-record priority batch
# backfills the worst gaps (department/email/title) from official institution
# pages.  The payload was produced after the Accepted S2B checkpoint, so it
# reuses the still-registered-but-unprojected professor-metrics inventory slot
# and carries no historical backup lineage.
_PROFESSOR_BACKFILL_SOURCE_ID = (
    "inventory:8c3084c6d7364e43089903d8bd60c182534aa199eb7c04e6721291ad0b358e99"
)
_PROFESSOR_BACKFILL_BATCH_ID = "s12e-professor-backfill-v1"

_SUPPLEMENTAL_SOURCE_AUTHORITIES = {
    "inventory:f8fea06321bd45af4c88c9654497a8c504defbf56c5eaee1d758e26248ea2bae": (
        _SupplementalSourceAuthority(
            filename="company_knowledge_fields.jsonl",
            byte_size=3609,
            content_sha256=(
                "954ad91b06d767550fef38700cae8fc854f68b1856bcb22824525c1cce384c5b"
            ),
            backup_manifest_filename=(
                "008-f8fea06321bd45af4c88c9654497a8c504defbf56c5eaee1d758e26248ea2bae.jsonl"
            ),
            backup_manifest_sha256=(
                "0f9665ac38877818aadbaa936ec0964c43d04486091eea62579af1bb95a2ac9a"
            ),
            source_member_manifest_sha256=(
                "d55fb7578a48fa2d379125e624520b9e54c782f34f2795b31923499671f7c8d7"
            ),
            source_kind="historical_jsonl",
            source_batch_id="s12c-r7-company-knowledge-v1",
            parser_name="historical_jsonl",
            parser_options={},
        )
    ),
    "inventory:4384044cb138f62be89edc0f9457065d00f08ce44d8dd9d06e0caefc555c3eef": (
        _SupplementalSourceAuthority(
            filename="paper_exact_identifier_backfills.jsonl",
            byte_size=1619,
            content_sha256=(
                "beb47502842916d8a37cadc06fe356b45b1111f8c4456852e50549fe3651c004"
            ),
            backup_manifest_filename=(
                "009-4384044cb138f62be89edc0f9457065d00f08ce44d8dd9d06e0caefc555c3eef.jsonl"
            ),
            backup_manifest_sha256=(
                "5408445fc4d706ab180b9c86f3e1b42f1e3a0632f21d7034d8dec07d5645fcbb"
            ),
            source_member_manifest_sha256=(
                "338b825e6cffeadb9813ed1e87ce1db89019760dd8eb38f8fa6c2eda4f53d33d"
            ),
            source_kind="historical_jsonl",
            source_batch_id="s12c-r7-paper-identifiers-v1",
            parser_name="historical_jsonl",
            parser_options={},
        )
    ),
    "inventory:1a987406c94c0f1e7b69e0272d8f06582f7f1fe2668f3cfbdd0e48780eed3026": (
        _SupplementalSourceAuthority(
            filename="professor_company_roles.jsonl",
            byte_size=579,
            content_sha256=(
                "8b3ffd1a8d4a9f5fda7ec760fc241b25de9417a2477d8ec51dbdb588de2e7e02"
            ),
            backup_manifest_filename=(
                "012-1a987406c94c0f1e7b69e0272d8f06582f7f1fe2668f3cfbdd0e48780eed3026.jsonl"
            ),
            backup_manifest_sha256=(
                "a701f6e6cd879738923c2c0bb104cb75114f6fec1dae753dde71a87fe4562107"
            ),
            source_member_manifest_sha256=(
                "acfcb07613a840a923310a42690d3e9a08a6cb955330548628c10b4216883550"
            ),
            source_kind="historical_jsonl",
            source_batch_id="s12c-r7-professor-company-roles-v1",
            parser_name="historical_jsonl",
            parser_options={},
        )
    ),
    "inventory:b84a6eac6bc59c9b9431b94ae8735bcda813b3186c28455719ac3bd6718d41ae": (
        _SupplementalSourceAuthority(
            filename="company_workbook_critical_supplement.xlsx",
            byte_size=6924,
            content_sha256=(
                "cdefadb03a4a804690d8ee9fe708a53c71f9a7b7ca858be0b8911dc767193790"
            ),
            backup_manifest_filename=(
                "014-b84a6eac6bc59c9b9431b94ae8735bcda813b3186c28455719ac3bd6718d41ae.jsonl"
            ),
            backup_manifest_sha256=(
                "0ec89486e7fe05ddc7cc2862d2472b4c2f0ae3893c3c02de67c77c24205900ee"
            ),
            source_member_manifest_sha256=(
                "575ccd1b8e2bc0bdb22d0902fe311933fce242d3e761e701e942b1f3f6d8b02b"
            ),
            source_kind="historical_xlsx",
            source_batch_id="s12c-r7-company-workbook-supplement-v1",
            parser_name="historical_xlsx",
            parser_options={"sheet": "sheet1", "header_row": 2},
        )
    ),
    "inventory:b9a8975b2d147348ef47cbd08ad12c6e550c6012ecc29e2979a4db76e3b3c4a0": (
        _SupplementalSourceAuthority(
            filename="patent_exact_identifier_supplement.xlsx",
            byte_size=5447,
            content_sha256=(
                "9780b96ac6a97b5086a3acfc2324391c8611b8163515614661d3131d1ec94b5a"
            ),
            backup_manifest_filename=(
                "015-b9a8975b2d147348ef47cbd08ad12c6e550c6012ecc29e2979a4db76e3b3c4a0.jsonl"
            ),
            backup_manifest_sha256=(
                "1e6d9b8d6099f0be5ad89f511537530bec488c517ada36ec1fcba63e32c9bb24"
            ),
            source_member_manifest_sha256=(
                "0348cdb61e437f7cc547a27e1beeeca5141ea4fa502c195194406713a8808adc"
            ),
            source_kind="historical_xlsx",
            source_batch_id="s12c-r7-patent-identifiers-v1",
            parser_name="historical_xlsx",
            parser_options={"sheet": "Sheet1"},
        )
    ),
    _PROFESSOR_BACKFILL_SOURCE_ID: (
        _SupplementalSourceAuthority(
            filename="professor_backfill_batch.jsonl",
            byte_size=33352,
            content_sha256=(
                "06b44c047a618ba9e9e90404bf4ecf57ce4e007b9164f9e226ed8085ad9832ab"
            ),
            # Admitted at s12f, after the Accepted S2B checkpoint: the payload
            # has no historical backup lineage, so the backup-member identity
            # stays explicitly null instead of borrowing another source's.
            backup_manifest_filename=None,
            backup_manifest_sha256=None,
            source_member_manifest_sha256=None,
            source_kind="historical_jsonl",
            source_batch_id=_PROFESSOR_BACKFILL_BATCH_ID,
            parser_name="historical_jsonl",
            parser_options={},
        )
    ),
}
_SUPPLEMENTAL_SOURCE_IDS = frozenset(_SUPPLEMENTAL_SOURCE_AUTHORITIES)
_SUPPLEMENTAL_SOURCE_PURPOSES = {
    "inventory:f8fea06321bd45af4c88c9654497a8c504defbf56c5eaee1d758e26248ea2bae": "company_knowledge",
    "inventory:4384044cb138f62be89edc0f9457065d00f08ce44d8dd9d06e0caefc555c3eef": "paper_identifier",
    "inventory:1a987406c94c0f1e7b69e0272d8f06582f7f1fe2668f3cfbdd0e48780eed3026": "professor_company_role",
    "inventory:b84a6eac6bc59c9b9431b94ae8735bcda813b3186c28455719ac3bd6718d41ae": "company_workbook",
    "inventory:b9a8975b2d147348ef47cbd08ad12c6e550c6012ecc29e2979a4db76e3b3c4a0": "patent_identifier",
    _PROFESSOR_BACKFILL_SOURCE_ID: "professor_backfill",
}


_SOURCE_IDS_BY_DISPOSITION: dict[SourceDisposition, frozenset[str]] = {
    SourceDisposition.requirements_only: frozenset(
        {
            "inventory:531d3cb88f7c5605d5c3fe2d8c4e6564106c71cf3d278f23b3eea6daad08d145",
            "inventory:5b0c06ada31be18bfb8ce8704c3e1a7cf04346f243756b451e5d37b414328d2f",
            "inventory:5b17380f2b046730ccda68910ee8dec2af10319093d7b86734780f6a19f4c847",
            "inventory:619924e69182f9fffe9bef24455d50ebee787fabe9fb92b74e413a5e7a46544c",
            "inventory:7bbd1e8e41e98162add1fbb385443061ac91b8a8fd7e0da3fa9a2a6a5dac47ee",
            "inventory:bfd2f9771e12452101507f8e0d10b2243f7f1807e96905ed35c327c430f349b6",
            "inventory:c037008730833b28b5e9fb200a4ed9078d8571382b1250d36795d6ca18456e6b",
        }
    ),
    SourceDisposition.acceptance_only: frozenset(
        {
            "inventory:03cdece09485247f5a036871021e770a9b3b35c25a515fb0314655589f5d9c44",
            "inventory:43c44a4cb584803b79fcd4760461af7dcd68304ac163d961a83643067e5227d8",
            "inventory:55c969432f588015934396a66874ea6b533d431aa3b521a61f5681c4f2f886a2",
            "inventory:9d70d6f276e39cd177079766739fbce58723ef79435cf502eedd798207f5c720",
            "inventory:c72421b11813abe836836545eb8925076e5e3c09b975a9a11387b7fef6e8bde4",
            "inventory:d26dd2f6d1e9a24699d642b68760c03df65b13e07edc5335868d5923eab43189",
            "inventory:e425f399185195b5e1c187db87869032e000e9c7e17b29353b61bce1b6ce025f",
        }
    ),
    SourceDisposition.evidence_input: frozenset({_RELEASED_OBJECTS_SOURCE_ID}),
    SourceDisposition.protection_only: frozenset(
        {
            "forensic_recovery_tree",
            "inventory:1a873f91cf59065877e3b21a5b5a046c3c7705b128d9ae8c9db31c23588e439f",
            "inventory:5880891dd3b3c04f1f8e9b29c308dd9be12b233a3165338bf992c17f3aa848a8",
            "inventory:65c4a289550957659155a00799158dd615be14005eb8f35afc778cfa3943accd",
            "original_postgresql_volume",
        }
    ),
    SourceDisposition.registered_unprojected: frozenset(
        {
            "inventory:11c9847d8bb362984a35e54c25d6f3f01f74b6209245d359e40f7dbd98738829",
            "inventory:1a987406c94c0f1e7b69e0272d8f06582f7f1fe2668f3cfbdd0e48780eed3026",
            "inventory:20be9e411f58e2d8a13f82ff094c5424074ba95bf6668177f64edc2396463d07",
            "inventory:27e2129243e993646d1e976814f26fd42590dd6c02639577c1ce6cdf36329ce7",
            "inventory:2d237edecb0f22c141c270f0c9147e3c5a18824025d155f607bb58ef79acc1bb",
            "inventory:306888219094fdee6713d1d21bf2716d8fd1326efaf5a7a4875c08ce3cbc58f5",
            "inventory:3371136d61fe041eb7e7ba087d9ddc37843330b4d39187b355310ba50599d1d2",
            "inventory:3bf673d8c10db3fc95558037794443a0b8f4a3994d5ae36ac7c85191440f1cd6",
            "inventory:4384044cb138f62be89edc0f9457065d00f08ce44d8dd9d06e0caefc555c3eef",
            "inventory:573305265d755bf3d85fb60e5e3d33e588838f7d71075d663f5f1b6836bf3ff7",
            "inventory:5e1ba9daab456914060f8df8b826a57006cb6ae8486ac816f7b1721186c17c73",
            "inventory:5eed796459843f74ecaebf4f0f8b20fd4570d2a343a442f9ddcbe0f26362d6ab",
            "inventory:603b9b33d7e8f3581d670659002768778ec06914a1f1586a0742619024038083",
            "inventory:6533126e9f7b14a478e8fc098541258d9b075ce70de16288b43dcf9abed59cc1",
            "inventory:6cf786f09478810a09cffe194d96e046a4d3e28a465c4418d8be2a13a126e5f7",
            "inventory:7a323115d06360192111c84e2a4da324146948d18c3189751885f6b95ac6d255",
            "inventory:82e601426705c3ab7ea24b9b9736975fc8f22128e077aa279075e19558309ee3",
            "inventory:8c3084c6d7364e43089903d8bd60c182534aa199eb7c04e6721291ad0b358e99",
            "inventory:909ada3e637a0220acc7d7a6335d3743045762e5c720e6120141c79ae5b0d8f8",
            "inventory:98a87f5fea987e586f33ead0914b848d4acd9e03a3312eaa5a8eb01f7c8765f5",
            "inventory:aa84883ccf6e8034b9ebe6d03fa91d6b265f4abd1f096ceb13d219d38a1a6435",
            "inventory:b2fd4e9bcf4238424785571f65e94161f07f9631a5b589ace749397527ac35ad",
            "inventory:b84a6eac6bc59c9b9431b94ae8735bcda813b3186c28455719ac3bd6718d41ae",
            "inventory:b9a8975b2d147348ef47cbd08ad12c6e550c6012ecc29e2979a4db76e3b3c4a0",
            "inventory:bdb272f5232f7d7bdb9df3e6341f8be4235c57bcc7f11917cb628b216a7367b5",
            "inventory:c2199ac16504af74d0e8a0a00c7e9fea5cf79c65c9de9631ceaa81a3ad0347d2",
            "inventory:d0306b9ab385b64379e437978a971e1d4a8abecee0de0863e0cdb53163b1028d",
            "inventory:dc465266f3a71f9c820cba8cf83f860feb053f6da5bfef79ec02283e9f5ee673",
            "inventory:eb4faa13a8f4c00f703b2fb014ecc5eb671cb29b3dd20e0836afb9b1024bf8a0",
            "inventory:f8fea06321bd45af4c88c9654497a8c504defbf56c5eaee1d758e26248ea2bae",
        }
    ),
    SourceDisposition.unrecoverable: frozenset(),
}


class SourceBuildManifest(_ContentAddressedModel):
    schema_version: Literal[
        "canonical-v2-source-build-manifest-v1",
        "canonical-v2-source-build-manifest-v2",
    ]
    source_inventory_sha256: Sha256
    backup_manifest_sha256: Sha256
    restore_verification_sha256: Sha256
    acceptance_record_sha256: Sha256
    released_objects_mapper_policy_version: Literal[
        "canonical-v2-released-objects-mapper-v2"
    ]
    released_objects_mapper_policy_sha256: Sha256
    released_objects_expected_row_counts: dict[NonEmptyStr, int]
    restore_root: Path
    approved_recollection_root: Path | None
    inventory_entries: tuple[SourceBuildEntry, ...]
    targeted_recollection_entries: tuple[SourceBuildEntry, ...] = ()

    @model_validator(mode="after")
    def validate_source_authority(self) -> SourceBuildManifest:
        expected_gate = (
            _SOURCE_INVENTORY_SHA256,
            _BACKUP_MANIFEST_SHA256,
            _RESTORE_VERIFICATION_SHA256,
            _ACCEPTANCE_RECORD_SHA256,
        )
        supplied_gate = (
            self.source_inventory_sha256,
            self.backup_manifest_sha256,
            self.restore_verification_sha256,
            self.acceptance_record_sha256,
        )
        if supplied_gate != expected_gate:
            raise ValueError("manifest accepted-gate hashes differ")
        if (
            self.released_objects_mapper_policy_sha256
            != _RELEASED_OBJECTS_MAPPER_POLICY_SHA256
            or self.released_objects_expected_row_counts != _EXPECTED_OBJECT_COUNTS
        ):
            raise ValueError("released_objects mapper policy/count authority differs")
        if not self.restore_root.is_absolute() or (
            self.approved_recollection_root is not None
            and not self.approved_recollection_root.is_absolute()
        ):
            raise ValueError("source roots must be absolute")
        if (
            self.approved_recollection_root is not None
            or self.targeted_recollection_entries
        ):
            raise ValueError(
                "Task 12.1 has no approved targeted-recollection authority"
            )

        inventory_keys = tuple(item.source_id for item in self.inventory_entries)
        if inventory_keys != tuple(sorted(set(inventory_keys))):
            raise ValueError("inventory source IDs must be sorted and unique")
        expected_ids = frozenset().union(*_SOURCE_IDS_BY_DISPOSITION.values())
        if len(self.inventory_entries) != 50 or set(inventory_keys) != expected_ids:
            raise ValueError("inventory must exactly cover the 50 accepted sources")
        expected_by_disposition = dict(_SOURCE_IDS_BY_DISPOSITION)
        if self.schema_version == "canonical-v2-source-build-manifest-v2":
            expected_by_disposition[SourceDisposition.evidence_input] = frozenset(
                {*expected_by_disposition[SourceDisposition.evidence_input], *_SUPPLEMENTAL_SOURCE_IDS}
            )
            expected_by_disposition[SourceDisposition.registered_unprojected] = (
                expected_by_disposition[SourceDisposition.registered_unprojected]
                - _SUPPLEMENTAL_SOURCE_IDS
            )
        for disposition, source_ids in expected_by_disposition.items():
            actual = {
                item.source_id
                for item in self.inventory_entries
                if item.disposition is disposition
            }
            if actual != source_ids:
                raise ValueError(
                    f"exact {disposition.value} source disposition differs"
                )

        all_entries = (*self.inventory_entries, *self.targeted_recollection_entries)
        source_ids = tuple(item.source_id for item in all_entries)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique across both collections")
        member_ids = tuple(
            member.member_id for item in all_entries for member in item.members
        )
        batch_ids = tuple(
            member.source_batch_id for item in all_entries for member in item.members
        )
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("source member IDs must be unique")
        if len(batch_ids) != len(set(batch_ids)):
            raise ValueError("source batch IDs must be unique")

        non_evidence = {
            SourceDisposition.requirements_only,
            SourceDisposition.acceptance_only,
            SourceDisposition.protection_only,
            SourceDisposition.registered_unprojected,
        }
        for entry in all_entries:
            if entry.disposition in non_evidence and entry.members:
                raise ValueError(
                    "non-evidence dispositions cannot carry readable members"
                )
            if (
                entry.disposition is SourceDisposition.evidence_input
                and not entry.members
            ):
                raise ValueError("evidence input requires an immutable member")
            if (
                entry.disposition is SourceDisposition.unrecoverable
                and entry.gap_id is None
            ):
                raise ValueError("unrecoverable source requires a typed gap identity")
            if (
                entry.disposition is not SourceDisposition.unrecoverable
                and entry.gap_id
            ):
                raise ValueError(
                    "only unrecoverable sources carry a manifest gap identity"
                )
            for member in entry.members:
                if member.parent_source_id != entry.source_id:
                    raise ValueError("source member parent identity is cross-wired")

        accepted_entry = next(
            item
            for item in self.inventory_entries
            if item.source_id == _RELEASED_OBJECTS_SOURCE_ID
        )
        if len(accepted_entry.members) != 1:
            raise ValueError("released_objects evidence requires one exact member")
        member = accepted_entry.members[0]
        if (
            member.member_id != _RELEASED_OBJECTS_MEMBER_ID
            or member.source_kind != "released_objects_sqlite"
            or member.byte_size != _RELEASED_OBJECTS_MEMBER_SIZE
            or member.content_sha256 != _RELEASED_OBJECTS_SHA256
            or member.restore_member_path != _RELEASED_OBJECTS_RESTORE_MEMBER_PATH
            or member.backup_member_manifest_path
            != _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH
            or member.backup_member_manifest_sha256
            != _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
            or member.source_member_manifest_sha256
            != _RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256
            or member.parser.parser_name != "released_objects_sqlite"
            or member.parser.parser_version != "canonical-v2-s12a-full-table-v1"
            or member.parser.schema_version != "released-objects-v1"
            or member.parser.options.get("table") != "released_objects"
            or member.parser.options.get("order") != "primary_key"
            or member.parser.options.get("limit") is not None
            or not _lexically_below(member.content_path, self.restore_root)
            or member.content_path
            != self.restore_root / _RELEASED_OBJECTS_RESTORE_MEMBER_PATH
        ):
            raise ValueError("released_objects member differs from accepted authority")

        if self.schema_version == "canonical-v2-source-build-manifest-v2":
            entries_by_id = {entry.source_id: entry for entry in self.inventory_entries}
            for source_id, authority in _SUPPLEMENTAL_SOURCE_AUTHORITIES.items():
                entry = entries_by_id[source_id]
                if len(entry.members) != 1:
                    raise ValueError("supplemental evidence requires one exact member")
                supplemental = entry.members[0]
                if (
                    supplemental.member_id != authority.member_id
                    or supplemental.source_batch_id != authority.source_batch_id
                    or supplemental.source_kind != authority.source_kind
                    or supplemental.byte_size != authority.byte_size
                    or supplemental.content_sha256 != authority.content_sha256
                    or supplemental.restore_member_path != authority.restore_member_path
                    or supplemental.backup_member_manifest_path
                    != authority.backup_member_manifest_path
                    or supplemental.backup_member_manifest_sha256
                    != authority.backup_manifest_sha256
                    or supplemental.source_member_manifest_sha256
                    != authority.source_member_manifest_sha256
                    or supplemental.parser.parser_name != authority.parser_name
                    or supplemental.parser.parser_version != "v1"
                    or supplemental.parser.schema_version
                    not in {
                        "historical-jsonl-record-v1",
                        "historical-xlsx-record-v1",
                    }
                    or supplemental.parser.options != authority.parser_options
                    or supplemental.parent_source_id != source_id
                    or supplemental.content_path
                    != self.restore_root / authority.restore_member_path
                    or not _lexically_below(supplemental.content_path, self.restore_root)
                ):
                    raise ValueError(
                        "supplemental member differs from fixed accepted authority"
                    )

        return self


def _lexically_below(path: Path, root: Path) -> bool:
    if not path.is_absolute() or not root.is_absolute() or path == root:
        return False
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalized_absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("safety-sensitive paths must be absolute")
    return Path(os.path.abspath(os.fspath(path)))


def _paths_overlap(left: Path, right: Path) -> bool:
    normalized_left = _normalized_absolute_path(left)
    normalized_right = _normalized_absolute_path(right)
    return (
        normalized_left == normalized_right
        or normalized_left.is_relative_to(normalized_right)
        or normalized_right.is_relative_to(normalized_left)
    )


_NETWORK_FILESYSTEM_TYPES = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "davfs",
        "fuse.rclone",
        "fuse.sshfs",
        "glusterfs",
        "lustre",
        "nfs",
        "nfs4",
        "smb3",
        "sshfs",
    }
)


def _filesystem_type_for_path(path: Path) -> str:
    if str(path).startswith("//"):
        return "unc"
    existing = path
    while not existing.exists():
        parent = existing.parent
        if parent == existing:
            raise ValueError("target filesystem identity is unavailable")
        existing = parent
    resolved = existing.resolve(strict=True)
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("target filesystem identity is unavailable") from exc
    matches: list[tuple[int, str]] = []
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
            mount_text = (
                fields[4]
                .replace(r"\040", " ")
                .replace(r"\011", "\t")
                .replace(r"\012", "\n")
                .replace(r"\134", "\\")
            )
            mount_point = Path(mount_text)
            filesystem_type = fields[separator + 1].casefold()
        except (IndexError, ValueError):
            continue
        if resolved == mount_point or mount_point in resolved.parents:
            matches.append((len(mount_point.parts), filesystem_type))
    if not matches:
        raise ValueError("target filesystem identity is unavailable")
    return max(matches)[1]


def _require_local_filesystem_path(path: Path) -> None:
    filesystem_type = _filesystem_type_for_path(path)
    if filesystem_type == "unc" or filesystem_type in _NETWORK_FILESYSTEM_TYPES:
        raise ValueError(
            f"candidate target is on a forbidden network filesystem: {filesystem_type}"
        )


def _require_no_symlink_ancestors(path: Path) -> None:
    normalized = _normalized_absolute_path(path)
    for ancestor in (normalized, *normalized.parents):
        try:
            metadata = ancestor.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError("candidate target ancestry is not inspectable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("candidate target ancestry contains a symlink")


def _require_unlinked_regular_source(path: Path) -> os.stat_result:
    if not path.is_absolute():
        raise ValueError("accepted source lineage requires an absolute path")
    _require_no_symlink_ancestors(path)
    try:
        source = path.lstat()
    except OSError as exc:
        raise ValueError("accepted source lineage is missing") from exc
    if not stat.S_ISREG(source.st_mode):
        raise ValueError("accepted source lineage is not a regular file")
    if source.st_nlink != 1:
        raise ValueError("accepted source lineage cannot be a hard link")
    return source


def _read_stable_unlinked_regular_file(path: Path) -> bytes:
    inspected = _require_unlinked_regular_source(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        inspected_identity = (
            inspected.st_dev,
            inspected.st_ino,
            inspected.st_size,
            inspected.st_mtime_ns,
        )
        opened_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or opened_identity != inspected_identity
        ):
            raise ValueError("accepted source changed before its first read")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(fd)
        if (
            after.st_nlink != 1
            or (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
            != opened_identity
        ):
            raise ValueError("accepted source changed during its exact read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load_exact_json_document(path: Path, *, expected_sha256: str) -> dict[str, Any]:
    raw = _read_stable_unlinked_regular_file(path)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("accepted control document content identity differs")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("accepted control document must be an object")
    return cast(dict[str, Any], value)


def _verify_accepted_control_files_safe(gate_root: Path) -> None:
    controls = {
        gate_root / "s2/source-inventory.json": _SOURCE_INVENTORY_SHA256,
        gate_root / "s2b/backup-manifest.json": _BACKUP_MANIFEST_SHA256,
        gate_root / "s2b/restore-verification.json": _RESTORE_VERIFICATION_SHA256,
        gate_root / "s2b/acceptance-record.json": _ACCEPTANCE_RECORD_SHA256,
    }
    for path, expected_sha256 in controls.items():
        if (
            hashlib.sha256(_read_stable_unlinked_regular_file(path)).hexdigest()
            != expected_sha256
        ):
            raise ValueError("accepted control document content identity differs")


@dataclass(frozen=True, slots=True)
class _AcceptedImmutablePaths:
    backup_root: Path
    restore_root: Path
    evidence_root: Path
    original_milvus_path: Path


def _derive_accepted_immutable_paths(
    *, gate_root: Path, expected_sha256: str
) -> _AcceptedImmutablePaths:
    inventory = _load_exact_json_document(
        gate_root / "s2/source-inventory.json",
        expected_sha256=_SOURCE_INVENTORY_SHA256,
    )
    backup = _load_exact_json_document(
        gate_root / "s2b/backup-manifest.json",
        expected_sha256=_BACKUP_MANIFEST_SHA256,
    )
    source_rows = inventory.get("sources")
    evidence_root_raw = inventory.get("evidence_root")
    if not isinstance(source_rows, list) or not isinstance(evidence_root_raw, str):
        raise ValueError("accepted source inventory shape differs")
    matches = [
        row
        for row in source_rows
        if isinstance(row, dict)
        and row.get("kind") == "milvus_lite_original"
        and row.get("path") == "apps/miroflow-agent/milvus.db"
        and row.get("sha256") == expected_sha256
        and row.get("access_mode") == "hash_only_never_opened"
    ]
    if len(matches) != 1:
        raise ValueError(
            "accepted source inventory has no exact original Milvus identity"
        )
    evidence_root = _normalized_absolute_path(Path(evidence_root_raw))
    source_id = "inventory:" + _canonical_sha256(cast(JsonValue, matches[0]))
    backup_sources = backup.get("sources")
    backup_match = (
        [
            row
            for row in backup_sources
            if isinstance(row, dict) and row.get("source_id") == source_id
        ]
        if isinstance(backup_sources, list)
        else []
    )
    backup_root_raw = backup.get("backup_root")
    restore_root_raw = backup.get("restore_root")
    if (
        backup.get("source_inventory_sha256") != _SOURCE_INVENTORY_SHA256
        or not isinstance(backup_root_raw, str)
        or not isinstance(restore_root_raw, str)
        or not isinstance(backup.get("pre_copy_source_invariants"), dict)
        or backup["pre_copy_source_invariants"].get("original_milvus_sha256")
        != expected_sha256
        or len(backup_match) != 1
        or backup_match[0].get("source_root") != str(evidence_root)
    ):
        raise ValueError(
            "accepted backup manifest cross-wires original Milvus identity"
        )
    backup_root = _normalized_absolute_path(Path(backup_root_raw))
    restore_root = _normalized_absolute_path(Path(restore_root_raw))
    return _AcceptedImmutablePaths(
        backup_root=backup_root,
        restore_root=restore_root,
        evidence_root=evidence_root,
        original_milvus_path=evidence_root / "apps/miroflow-agent/milvus.db",
    )


def _derive_accepted_original_milvus_path(
    *, gate_root: Path, expected_sha256: str
) -> Path:
    return _derive_accepted_immutable_paths(
        gate_root=gate_root,
        expected_sha256=expected_sha256,
    ).original_milvus_path


class CandidateStagingMarker(ContractModel):
    schema_version: Literal["canonical-v2-candidate-staging-marker-v1"]
    run_id: NonEmptyStr
    candidate_release_id: NonEmptyStr
    source_manifest_sha256: Sha256


class CandidateStagingTarget(ContractModel):
    root: Path
    marker: CandidateStagingMarker

    @field_validator("root")
    @classmethod
    def require_absolute_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("candidate staging root must be absolute")
        return value


class CompleteCandidateTargetConfig(ContractModel):
    database: DestructiveDatabaseTarget
    index: IsolatedIndexTarget
    staging: CandidateStagingTarget


class CompleteCandidateConsumerHandoff(_ContentAddressedModel):
    schema_version: Literal["canonical-v2-complete-candidate-handoff-v1"]
    candidate: CandidateRelease
    release_bundle: IsolatedReleaseBundle
    index_projection_request: IndexProjectionRequest
    institution_catalog: InstitutionCatalog
    release_verification: ReleaseVerification

    @model_validator(mode="after")
    def validate_artifact_graph(self) -> CompleteCandidateConsumerHandoff:
        release_ids = {
            self.candidate.release_id,
            self.release_bundle.manifest.release_id,
            self.release_bundle.index_result.release_id,
            self.release_bundle.index_target.release_id,
            self.index_projection_request.candidate_projection_request.release_id,
            self.index_projection_request.candidate_projection_result.release_id,
            self.institution_catalog.release_id,
            self.release_verification.candidate_release_id,
        }
        if len(release_ids) != 1:
            raise ValueError("consumer handoff artifacts do not share one release")
        if (
            self.release_bundle.manifest.manifest_sha256
            != self.candidate.manifest_sha256
            or self.release_verification.manifest_sha256
            != self.candidate.manifest_sha256
        ):
            raise ValueError("consumer handoff artifacts do not share one manifest")
        manifest = self.release_bundle.manifest
        expected_object_counts = {
            section.section_id.removeprefix("objects:"): section.record_count
            for section in manifest.object_sets
        }
        if (
            self.candidate.state is not ReleaseState.candidate
            or self.candidate.run_id != manifest.build_run_id
            or self.candidate.source_batch_ids != manifest.source_batch_ids
            or self.candidate.parser_versions != manifest.parser_versions
            or self.candidate.policy_versions != manifest.policy_versions
            or self.candidate.model_versions != manifest.model_versions
            or self.candidate.object_counts != expected_object_counts
            or self.candidate.relationship_count
            != manifest.relationship_set.record_count
        ):
            raise ValueError(
                "consumer handoff candidate differs from its exact build manifest"
            )
        try:
            replayed_index = create_ephemeral_index_projection_builder().build(
                self.index_projection_request
            )
        except Exception as exc:
            raise ValueError(
                "consumer handoff index request cannot be replayed exactly"
            ) from exc
        if replayed_index != self.release_bundle.index_result:
            raise ValueError(
                "consumer handoff index request is cross-wired from its release bundle"
            )
        if (
            self.institution_catalog.catalog_id
            != f"institution-catalog:{self.candidate.release_id}"
            or self.institution_catalog.catalog_version
            != "canonical-v2-s12a-retained-v1"
            or self.institution_catalog.entries
        ):
            raise ValueError(
                "consumer handoff institution catalog differs from retained S12A authority"
            )
        publication = create_ephemeral_release_publication(
            candidate_manifests={
                self.candidate.release_id: self.release_bundle.manifest
            },
            actual_index_projections={
                self.candidate.release_id: (
                    self.release_bundle.index_result.actual_index_projections
                )
            },
            expected_index_points={
                self.candidate.release_id: self.release_bundle.index_result.points
            },
            actual_index_points={
                self.candidate.release_id: self.release_bundle.index_result.points
            },
            active_release_state={
                "canonical_release_id": "s12a-absent-active",
                "published_projection_release_id": "s12a-absent-active",
                "index_release_id": "s12a-absent-active",
            },
            verification_store={},
            discrepancy_store={},
            publication_history=[],
            clock=lambda: self.release_verification.verified_at,
        )
        if publication.verify(self.candidate.release_id) != self.release_verification:
            raise ValueError(
                "consumer handoff verification differs from exact index parity replay"
            )
        return self


class CompleteCandidateBuildReceipt(_ContentAddressedModel):
    schema_version: Literal["canonical-v2-complete-candidate-receipt-v1"]
    candidate: CandidateRelease
    consumer_handoff_sha256: Sha256
    source_manifest_sha256: Sha256
    gate_hashes: dict[NonEmptyStr, Sha256]
    landing_receipt_hashes: tuple[Sha256, ...]
    gap_hashes: tuple[Sha256, ...]
    authority_sha256: Sha256
    candidate_projection_sha256: Sha256
    relationship_projection_sha256: Sha256
    database_registry_sha256: Sha256
    index_result_sha256: Sha256
    physical_index_snapshot_sha256: Sha256
    release_verification: ReleaseVerification
    active_release_before_sha256: Sha256
    active_release_after_sha256: Sha256
    accepted_original_milvus_record_sha256: Sha256
    accepted_original_milvus_sha256: Sha256
    recorded_decision_bundle_sha256: Sha256
    recorded_embedding_bundle_sha256: Sha256
    recorded_embedding_dimension: int = Field(ge=8, le=4096)
    built_at: CanonicalDatetime

    @model_validator(mode="after")
    def validate_frozen_authority(self) -> CompleteCandidateBuildReceipt:
        absent_active_sha256 = _canonical_sha256(cast(JsonValue, None))
        if (
            self.candidate.state is not ReleaseState.candidate
            or self.active_release_before_sha256 != absent_active_sha256
            or self.active_release_after_sha256 != absent_active_sha256
        ):
            raise ValueError(
                "S12A receipt requires one candidate and absent active state"
            )
        if self.gate_hashes != {
            "acceptance_record": _ACCEPTANCE_RECORD_SHA256,
            "backup_manifest": _BACKUP_MANIFEST_SHA256,
            "restore_verification": _RESTORE_VERIFICATION_SHA256,
            "source_inventory": _SOURCE_INVENTORY_SHA256,
        }:
            raise ValueError("S12A receipt gate hashes differ from Accepted authority")
        if (
            self.accepted_original_milvus_sha256 != _ACCEPTED_ORIGINAL_MILVUS_SHA256
            or self.accepted_original_milvus_record_sha256
            != _ACCEPTED_ORIGINAL_MILVUS_RECORD_SHA256
            or self.recorded_decision_bundle_sha256 != _RECORDED_DECISION_BUNDLE_SHA256
            or (
                self.recorded_embedding_bundle_sha256,
                self.recorded_embedding_dimension,
            )
            not in _ACCEPTED_EMBEDDING_AUTHORITIES
        ):
            raise ValueError(
                "Candidate receipt offline authority differs from frozen inputs"
            )
        return self


class CompleteCandidateBuildEnvelope(_ContentAddressedModel):
    schema_version: Literal["canonical-v2-complete-candidate-envelope-v1"]
    receipt: CompleteCandidateBuildReceipt
    consumer_handoff: CompleteCandidateConsumerHandoff

    @model_validator(mode="after")
    def validate_cross_binding(self) -> CompleteCandidateBuildEnvelope:
        if self.receipt.consumer_handoff_sha256 != self.consumer_handoff.content_sha256:
            raise ValueError("receipt does not bind the exact consumer handoff")
        if self.receipt.candidate != self.consumer_handoff.candidate:
            raise ValueError("receipt and handoff candidate differ")
        if (
            self.receipt.release_verification
            != self.consumer_handoff.release_verification
        ):
            raise ValueError("receipt and handoff verification differ")
        if (
            self.receipt.candidate_projection_sha256
            != self.consumer_handoff.index_projection_request.candidate_projection_result.content_sha256
            or self.receipt.index_result_sha256
            != self.consumer_handoff.release_bundle.index_result.content_sha256
            or self.receipt.relationship_projection_sha256
            != self.consumer_handoff.release_bundle.manifest.relationship_set.content_sha256
        ):
            raise ValueError("receipt does not bind the exact handoff projection graph")
        return self


class _CandidateRegistrySnapshot(_ContentAddressedModel):
    release_row: dict[NonEmptyStr, JsonValue]
    manifest_row: dict[NonEmptyStr, JsonValue]
    section_rows: tuple[dict[NonEmptyStr, JsonValue], ...]
    seeded_policies: tuple[PolicyReference, ...]


@dataclass(frozen=True, slots=True)
class _RecordedGap:
    signal: GapSignal
    result: KnowledgeGap


@dataclass(frozen=True, slots=True)
class _SelectedFieldAudit:
    domain: str
    selected: dict[str, JsonValue]
    disallowed_paths: tuple[str, ...]
    invalid_allowed_paths: tuple[str, ...]
    quality_signals: tuple[str, ...] = ()
    defaulted_fields: frozenset[str] = frozenset()
    signaled_fields: frozenset[str] = frozenset()

    @property
    def affected_paths(self) -> tuple[str, ...]:
        return tuple(sorted({*self.disallowed_paths, *self.invalid_allowed_paths}))

    @property
    def projectable(self) -> bool:
        return not self.invalid_allowed_paths


@dataclass(frozen=True, slots=True)
class _PayloadSchemaAudit:
    disallowed_paths: tuple[str, ...]
    invalid_allowed_paths: tuple[str, ...]

    @property
    def affected_paths(self) -> tuple[str, ...]:
        return tuple(sorted({*self.disallowed_paths, *self.invalid_allowed_paths}))


@dataclass(frozen=True, slots=True)
class _LandingReadback:
    receipt: LandingReceipt
    records: tuple[SourceRecord, ...]
    artifact: EvidenceArtifact


@dataclass(frozen=True, slots=True)
class _StagedSource:
    path: Path
    source_id: str
    member_id: str
    source_batch_id: str
    content_sha256: str
    byte_size: int


class _Boundary(Protocol):
    def verify_accepted_control_files_safe(self, *, gate_root: Path) -> None: ...
    def resolve_accepted_immutable_paths(
        self, *, gate_root: Path, expected_sha256: str
    ) -> _AcceptedImmutablePaths: ...
    def resolve_accepted_original_milvus_path(
        self, *, gate_root: Path, expected_sha256: str
    ) -> Path: ...
    def verify_accepted_gate(self, *, gate_root: Path) -> Any: ...
    def validate_fresh_targets(
        self, *, target_config: CompleteCandidateTargetConfig
    ) -> None: ...
    def prepare_fresh_targets(
        self, *, target_config: CompleteCandidateTargetConfig
    ) -> None: ...
    def stage_verified_member(
        self,
        *,
        entry: SourceBuildEntry,
        member: SourceBuildMember,
        destination: Path,
    ) -> Any: ...
    def land_released_objects(
        self,
        *,
        entry: SourceBuildEntry,
        member: SourceBuildMember,
        staged_member: Any,
        run_id: str,
        observed_at: datetime,
    ) -> _LandingReadback: ...
    def persist_candidate_registry_and_identity_policy(
        self,
        *,
        candidate: CandidateRelease,
        manifest: BuildManifest,
        sections: tuple[ManifestSection, ...],
        policies: tuple[PolicyReference, ...],
        relationship_types: tuple[RelationshipType, ...],
    ) -> _CandidateRegistrySnapshot: ...
    def read_candidate_registry(
        self,
        *,
        release_id: str,
        policies: tuple[PolicyReference, ...],
    ) -> _CandidateRegistrySnapshot: ...
    def persist_identity_resolution(
        self,
        *,
        request: IdentityResolutionRequest,
        result: IdentityResolutionResult,
    ) -> IdentityResolutionResult: ...
    def persist_decision_batch(
        self, *, result: DecisionBatchResult
    ) -> DecisionBatchResult: ...
    def persist_domain_projection(
        self, *, result: DomainProjectionResult
    ) -> DomainProjectionResult: ...
    def persist_relationship_projection(
        self,
        *,
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> RelationshipProjectionResult: ...
    def persist_gap(
        self, *, signal: GapSignal, expected: KnowledgeGap
    ) -> KnowledgeGap: ...
    def materialize_index(
        self,
        *,
        request: IndexProjectionRequest,
        points: tuple[Any, ...],
        lookup_documents: tuple[Any, ...],
        expected_index_projections: tuple[Any, ...],
        expected_lookup_projections: tuple[Any, ...],
    ) -> IndexProjectionActualState: ...
    def audit_index(self, *, target: IsolatedIndexTarget) -> Any: ...
    def read_active_release(self) -> Mapping[str, str] | None: ...


class _EnvelopeSink(Protocol):
    def validate_fresh(
        self,
        *,
        required_destination: Path,
        protected_paths: tuple[Path, ...],
    ) -> None: ...
    def write_and_readback(
        self, envelope: CompleteCandidateBuildEnvelope
    ) -> CompleteCandidateBuildEnvelope: ...


class _DecisionAdapter(Protocol):
    @property
    def authority_sha256(self) -> str: ...

    def adjudicate(self, request: Any, /) -> Any: ...


class _EmbeddingAdapter(Protocol):
    model_id: str
    dimension: int
    authority_sha256: str

    def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class _BoundaryIndexMaterializer:
    def __init__(self, boundary: _Boundary) -> None:
        self._boundary = boundary

    @property
    def last_receipt(self) -> None:
        return None

    def materialize(
        self,
        *,
        request: IndexProjectionRequest,
        points: tuple[Any, ...],
        lookup_documents: tuple[Any, ...],
        expected_index_projections: tuple[Any, ...],
        expected_lookup_projections: tuple[Any, ...],
    ) -> IndexProjectionActualState:
        return self._boundary.materialize_index(
            request=request,
            points=points,
            lookup_documents=lookup_documents,
            expected_index_projections=expected_index_projections,
            expected_lookup_projections=expected_lookup_projections,
        )


@dataclass(frozen=True)
class _ParsedReleasedObject:
    source_id: str
    source_batch_id: str
    record: SourceRecord
    artifact: EvidenceArtifact
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _TypedRelationshipSeed:
    seed_id: str
    relationship_type_id: str
    source_object_id: str
    source_domain: str
    target_object_id: str
    target_domain: str
    role_id: str
    role_owner: Literal["source", "target"]
    evidence_kind: str
    requested_paths: tuple[str, ...]
    catalog_scenario_id: str
    evidence_metadata: dict[str, JsonValue]
    source_row: _ParsedReleasedObject


@dataclass(frozen=True)
class _MappedAuthority:
    identity_request: IdentityResolutionRequest
    identity_result: IdentityResolutionResult
    decision_result: DecisionBatchResult
    domain_request: DomainProjectionRequest
    domain_result: DomainProjectionResult
    internal_request: InternalReferenceProjectionRequest
    internal_result: InternalReferenceProjectionResult
    candidate_request: CandidateProjectionRequest
    candidate_result: CandidateProjectionResult
    relationship_request: RelationshipProjectionRequest
    relationship_result: RelationshipProjectionResult
    eligibility_requests: tuple[PathEligibilityRequest, ...]
    eligibility_results: tuple[PathEligibilityResult, ...]
    index_request: IndexProjectionRequest
    pure_index_result: IndexProjectionResult
    gaps: tuple[_RecordedGap, ...]


def _policy(
    *,
    kind: PolicyKind,
    version: str,
    effective_at: datetime,
) -> PolicyReference:
    return PolicyReference(
        policy_id=f"canonical-v2-s12a-{kind.value}",
        policy_version=version,
        policy_kind=kind,
        content_sha256=_canonical_sha256(
            cast(JsonValue, {"kind": kind.value, "version": version})
        ),
        effective_at=effective_at,
    )


def _source_record(
    *,
    row: dict[str, Any],
    source_batch_id: str,
    member: SourceBuildMember,
    parsed_at: datetime,
) -> SourceRecord:
    row_id = row.get("id")
    object_type = row.get("object_type")
    display_name = row.get("display_name")
    payload_json = row.get("payload_json")
    valid_shape = all(
        isinstance(value, str) and bool(value.strip())
        for value in (row_id, object_type, display_name, payload_json)
    )
    parse_status = ParseStatus.parsed
    errors: tuple[SourceError, ...] = ()
    error_code = "released_objects_malformed_json"
    error_detail = "malformed JSON or an incomplete scalar envelope"
    if valid_shape:
        try:
            _load_unique_json_object(cast(str, payload_json))
        except _DuplicateJsonKeyError as exc:
            valid_shape = False
            error_code = "released_objects_duplicate_json_key"
            error_detail = str(exc)
        except (TypeError, ValueError, RecursionError):
            valid_shape = False
    if not valid_shape:
        parse_status = ParseStatus.quarantined
        errors = (
            SourceError(
                error_code=error_code,
                error_kind=SourceErrorKind.parse_error,
                message=(f"released_objects row {row_id!r} contains {error_detail}"),
                field_path="payload_json",
                recoverable=True,
            ),
        )
    safe_payload = cast(
        dict[NonEmptyStr, JsonValue],
        json.loads(json.dumps(row, ensure_ascii=False, allow_nan=False)),
    )
    artifact_id = "artifact:sha256:" + _canonical_sha256(
        cast(
            JsonValue,
            {
                "member_id": member.member_id,
                "content_sha256": member.content_sha256,
            },
        )
    )
    return SourceRecord(
        record_id=(
            f"released-object:{source_batch_id}:"
            f"{row_id if isinstance(row_id, str) and row_id else _canonical_sha256(safe_payload)}"
        ),
        artifact_id=artifact_id,
        source_batch_id=source_batch_id,
        record_locator=(
            f"released_objects:{row_id}"
            if isinstance(row_id, str) and row_id
            else "released_objects:unidentified"
        ),
        parser_name=member.parser.parser_name,
        parser_version=member.parser.parser_version,
        schema_version=member.parser.schema_version,
        parse_run_id=f"landing:{source_batch_id}",
        parse_status=parse_status,
        payload=safe_payload,
        errors=errors,
        parsed_at=parsed_at,
    )


def _gap(
    *,
    release_id: str,
    run_id: str,
    record: SourceRecord,
    domain: str,
    reason: str,
    affected_paths: tuple[str, ...] = (),
    now: datetime,
) -> _RecordedGap:
    specific_paths = tuple(sorted({path for path in affected_paths if path.strip()}))
    if not specific_paths:
        raise ValueError(
            "typed candidate gap requires at least one specific affected path"
        )
    seed = _canonical_sha256(
        cast(
            JsonValue,
            {
                "release_id": release_id,
                "run_id": run_id,
                "record_id": record.record_id,
                "reason": reason,
            },
        )
    )
    affected_domain = domain if domain in _PUBLIC_DOMAINS else "cross_domain"
    signal = GapSignal(
        signal_id=f"gap-signal:sha256:{seed}",
        trigger=GapTrigger.insufficient_evidence,
        release_id=release_id,
        affected_domains=(affected_domain,),
        affected_paths=(
            "offline_candidate_build",
            *specific_paths,
        ),
        telemetry_key=f"s12a:{run_id}:{seed}",
        observed_symptom=reason,
        evidence_ids=(record.record_id,),
        observed_at=now,
    )
    result = create_ephemeral_knowledge_gap_feedback(clock=lambda: now).record(signal)
    return _RecordedGap(signal=signal, result=result)


def _present_projection_paths(
    core: dict[str, Any], summary: dict[str, Any]
) -> set[str]:
    return {
        *(f"core_facts.{field}" for field in core),
        *(f"summary_fields.{field}" for field in summary),
    }


def _pydantic_location_path(location: tuple[Any, ...]) -> str:
    path = ""
    for part in location:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path


def _named_reference_audit(
    value: Any,
    *,
    path: str,
) -> tuple[JsonValue, tuple[str, ...], tuple[str, ...]]:
    if isinstance(value, str) and value.strip():
        name = value.strip()
        reference = NamedReference(
            reference_id=f"source-reference:{hashlib.sha256(name.casefold().encode('utf-8')).hexdigest()}",
            name=name,
        )
        return cast(JsonValue, reference.model_dump(mode="json")), (), ()
    if not isinstance(value, dict):
        return cast(JsonValue, value), (), (path,)
    allowed_keys = {"reference_id", "name"}
    disallowed = tuple(
        sorted(f"{path}.{key}" for key in value if key not in allowed_keys)
    )
    sanitized = {key: value[key] for key in allowed_keys if key in value}
    try:
        reference = NamedReference.model_validate(sanitized)
    except ValidationError as exc:
        invalid = tuple(
            sorted(
                {
                    f"{path}.{nested}"
                    if (nested := _pydantic_location_path(tuple(error["loc"])))
                    else path
                    for error in exc.errors()
                }
            )
        )
        return cast(JsonValue, sanitized), disallowed, invalid
    return (
        cast(JsonValue, reference.model_dump(mode="json")),
        disallowed,
        (),
    )


def _source_named_members(
    value: Any,
    *,
    path: str,
    order_field: str,
) -> tuple[list[dict[str, JsonValue]], tuple[str, ...]]:
    if not isinstance(value, list):
        return [], (path,)
    normalized: list[dict[str, JsonValue]] = []
    invalid: set[str] = set()
    for index, member in enumerate(value):
        name = member if isinstance(member, str) else None
        if isinstance(member, dict):
            name = member.get("name")
        if not isinstance(name, str) or not name.strip():
            invalid.add(f"{path}[{index}]")
            continue
        normalized.append(
            {
                "name": name.strip(),
                order_field: index,
            }
        )
    return normalized, tuple(sorted(invalid))


def _source_company_key_personnel(
    value: Any,
    *,
    path: str,
) -> tuple[list[dict[str, JsonValue]], tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, list):
        return [], (), (path,)
    normalized: list[dict[str, JsonValue]] = []
    disallowed: set[str] = set()
    invalid: set[str] = set()
    allowed_member_keys = {"description", "name", "role"}
    for index, member in enumerate(value):
        member_path = f"{path}[{index}]"
        if not isinstance(member, dict):
            invalid.add(member_path)
            continue
        disallowed.update(
            f"{member_path}.{key}"
            for key in member
            if key not in allowed_member_keys
        )
        name = member.get("name")
        role = member.get("role")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(role, str)
            or not role.strip()
        ):
            invalid.add(member_path)
            continue
        entry: dict[str, JsonValue] = {"name": name.strip(), "role": role.strip()}
        description = member.get("description")
        if description is not None:
            if not isinstance(description, str) or not description.strip():
                invalid.add(f"{member_path}.description")
                continue
            entry["description"] = description.strip()
        normalized.append(entry)
    return normalized, tuple(sorted(disallowed)), tuple(sorted(invalid))


def _source_named_references(
    value: Any,
    *,
    path: str,
) -> tuple[list[dict[str, JsonValue]], tuple[str, ...]]:
    if not isinstance(value, list):
        return [], (path,)
    normalized: list[dict[str, JsonValue]] = []
    invalid: set[str] = set()
    for index, member in enumerate(value):
        reference, _, member_invalid = _named_reference_audit(
            member,
            path=f"{path}[{index}]",
        )
        if member_invalid:
            invalid.update(member_invalid)
            continue
        if not isinstance(reference, dict):
            invalid.add(f"{path}[{index}]")
            continue
        normalized.append(cast(dict[str, JsonValue], reference))
    return normalized, tuple(sorted(invalid))


def _source_string_list(value: Any, *, path: str) -> tuple[list[str], tuple[str, ...]]:
    if not isinstance(value, list):
        return [], (path,)
    invalid = tuple(
        f"{path}[{index}]"
        for index, member in enumerate(value)
        if not isinstance(member, str) or not member.strip()
    )
    if invalid:
        return [], invalid
    return [cast(str, member).strip() for member in value], ()


def _source_iso_date_string(
    value: Any, *, path: str
) -> tuple[str | None, tuple[str, ...]]:
    if not isinstance(value, str) or not value.strip():
        return None, (path,)
    candidate = value.strip()
    try:
        Date.fromisoformat(candidate)
    except ValueError:
        return None, (path,)
    return candidate, ()


def _decode_reversed_professor_email(email: str) -> tuple[str, str | None]:
    local_part, separator, _domain = email.partition("@")
    if not separator or not local_part.casefold().startswith(
        _REVERSED_EMAIL_LOCAL_PREFIXES
    ):
        return email, None
    if _DECODABLE_EMAIL_PATTERN.match(email):
        # Already a plausible normal address; never reverse real mailboxes.
        return email, None
    candidate = email[::-1]
    if _DECODABLE_EMAIL_PATTERN.match(candidate):
        return candidate, "decoded_reversed_email"
    return email, "reversed_email_undecodable"


def _selected_fields(payload: dict[str, Any]) -> _SelectedFieldAudit:
    domain = payload.get("object_type")
    core = payload.get("core_facts")
    summary = payload.get("summary_fields")
    if (
        domain not in _PUBLIC_DOMAINS
        or not isinstance(core, dict)
        or not isinstance(summary, dict)
    ):
        raise ValueError("unsupported object type or missing typed facts")
    domain = cast(str, domain)
    allowed_paths = set(_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE[domain])
    disallowed_paths = _present_projection_paths(core, summary) - allowed_paths
    values: dict[str, Any]
    source_path_by_field: dict[str, str]
    invalid_allowed_paths: set[str] = set()
    quality_signals: list[str] = []
    defaulted_fields: set[str] = set()
    signaled_fields: set[str] = set()
    if domain == "company":
        values = {
            "name": core.get("name"),
            "normalized_name": core.get("normalized_name"),
            "profile_summary": summary.get("profile_summary"),
            "technology_route_summary": summary.get("technology_route_summary"),
        }
        source_path_by_field = {
            "name": "core_facts.name",
            "normalized_name": "core_facts.normalized_name",
            "profile_summary": "summary_fields.profile_summary",
            "technology_route_summary": ("summary_fields.technology_route_summary"),
        }
        # Optional source-present fields that the historical whitelist
        # silently dropped (s12e company audit): project them only when the
        # payload actually carries them, so absence stays gap-free.
        aliases_value = core.get("aliases")
        if aliases_value is not None:
            aliases, invalid_aliases = _source_string_list(
                aliases_value, path="core_facts.aliases"
            )
            if aliases:
                values["aliases"] = aliases
                source_path_by_field["aliases"] = "core_facts.aliases"
            invalid_allowed_paths.update(invalid_aliases)
        if core.get("industry") is not None:
            values["industry"] = core.get("industry")
            source_path_by_field["industry"] = "core_facts.industry"
        if core.get("website") is not None:
            values["website"] = core.get("website")
            source_path_by_field["website"] = "core_facts.website"
        key_personnel_value = core.get("key_personnel")
        if key_personnel_value is not None:
            (
                key_personnel,
                key_personnel_disallowed,
                key_personnel_invalid,
            ) = _source_company_key_personnel(
                key_personnel_value, path="core_facts.key_personnel"
            )
            if key_personnel:
                values["key_personnel"] = key_personnel
                source_path_by_field["key_personnel"] = "core_facts.key_personnel"
            disallowed_paths.update(key_personnel_disallowed)
            invalid_allowed_paths.update(key_personnel_invalid)
    elif domain == "paper":
        authors, invalid_authors = _source_named_members(
            core.get("authors"),
            path="core_facts.authors",
            order_field="author_order",
        )
        values = {
            "authors": authors,
            "arxiv_id": core.get("arxiv_id"),
            "doi": core.get("doi"),
            "pdf_path": core.get("pdf_path"),
            "summary_text": summary.get("summary_text"),
            "title": core.get("title"),
            "venue": core.get("venue"),
            "year": core.get("year"),
        }
        # Optional identifiers/summary project only when the source carries
        # them (s12e paper audit); explicit nulls stay gap-free.
        for optional_field in ("arxiv_id", "doi", "pdf_path", "summary_text"):
            if values[optional_field] is None:
                values.pop(optional_field)
        source_path_by_field = {
            field: (
                "summary_fields.summary_text"
                if field == "summary_text"
                else f"core_facts.{field}"
            )
            for field in values
        }
        invalid_allowed_paths.update(invalid_authors)
    elif domain == "patent":
        applicants, invalid_applicants = _source_named_members(
            core.get("applicants"),
            path="core_facts.applicants",
            order_field="applicant_order",
        )
        inventors, invalid_inventors = _source_named_members(
            core.get("inventors"),
            path="core_facts.inventors",
            order_field="inventor_order",
        )
        _, invalid_company_ids = _source_string_list(
            core.get("company_ids", []), path="core_facts.company_ids"
        )
        values = {
            "applicants": applicants,
            "inventors": inventors,
            "patent_number": core.get("patent_number"),
            "summary_text": summary.get("summary_text"),
            "title": core.get("title"),
        }
        # Optional lifecycle dates project only when the source carries a
        # valid ISO calendar date (s12e patent audit); malformed dates stay
        # hard rejections so typed Date projections never fail at build time.
        for date_field in ("filing_date", "publication_date"):
            raw_date = core.get(date_field)
            if raw_date is None:
                continue
            parsed_date, invalid_date = _source_iso_date_string(
                raw_date, path=f"core_facts.{date_field}"
            )
            if parsed_date is not None:
                values[date_field] = parsed_date
            invalid_allowed_paths.update(invalid_date)
        source_path_by_field = {
            field: (
                "summary_fields.summary_text"
                if field == "summary_text"
                else f"core_facts.{field}"
            )
            for field in values
        }
        invalid_allowed_paths.update(
            (*invalid_applicants, *invalid_inventors, *invalid_company_ids)
        )
    else:
        research_directions, invalid_research_directions = _source_named_references(
            core.get("research_directions"),
            path="core_facts.research_directions",
        )
        patent_ids, invalid_patent_ids = _source_string_list(
            core.get("patent_ids"), path="core_facts.patent_ids"
        )
        profile_summary = summary.get("profile_summary")
        fallback_summary = _PROFESSOR_PROFILE_SUMMARY_FALLBACK
        values = {
            "name": core.get("name") or core.get("canonical_name_zh"),
            "canonical_name_zh": core.get("canonical_name_zh") or core.get("name"),
            "department": core.get("department"),
            "email": core.get("email"),
            "homepage": core.get("homepage"),
            "institution": core.get("institution"),
            "paper_summary": core.get("paper_summary") or fallback_summary,
            "patent_ids": patent_ids,
            "patent_summary": core.get("patent_summary") or fallback_summary,
            "profile_summary": profile_summary,
            "research_directions": research_directions,
            "title": core.get("title"),
        }
        source_path_by_field = {
            field: (
                "summary_fields.profile_summary"
                if field == "profile_summary"
                else f"core_facts.{field}"
            )
            for field in values
        }
        # Section-label pollution (see _PROFESSOR_POLLUTION_NAME_LABELS) is a
        # hard rejection, not a quality signal: admitting it would surface
        # generic page columns as people in answers.
        resolved_name = values["name"]
        if (
            isinstance(resolved_name, str)
            and resolved_name.strip() in _PROFESSOR_POLLUTION_NAME_LABELS
        ):
            invalid_allowed_paths.add("core_facts.name")
        # Reversed anti-scrape emails decode deterministically at selection
        # time so projections and identity keys carry the real address.
        email_value = values["email"]
        if isinstance(email_value, str) and email_value.strip():
            decoded_email, email_signal = _decode_reversed_professor_email(
                email_value
            )
            values["email"] = decoded_email
            if email_signal is not None:
                quality_signals.append(email_signal)
                signaled_fields.add("email")
        # Only name+institution stay hard requirements; the other historically
        # required fields degrade to quality signals with explicit fallbacks.
        for field in _PROFESSOR_DEGRADABLE_FIELDS:
            value = values[field]
            if isinstance(value, str) and value.strip():
                continue
            if value is not None and not isinstance(value, str):
                # Malformed values (bad container/reference shapes) stay hard
                # rejections via the audits below.
                continue
            values[field] = (
                fallback_summary
                if field == "profile_summary"
                else _PROFESSOR_MISSING_FIELD_FALLBACK
            )
            quality_signals.append(f"missing_{field}")
            defaulted_fields.add(field)
        company_roles = core.get("company_roles")
        if not isinstance(company_roles, list) or any(
            not isinstance(role, dict)
            or not isinstance(role.get("company_name"), str)
            or not role["company_name"].strip()
            or not isinstance(role.get("role"), str)
            or not role["role"].strip()
            for role in company_roles
        ):
            invalid_allowed_paths.add("core_facts.company_roles")
        invalid_allowed_paths.update(
            (*invalid_patent_ids, *invalid_research_directions)
        )
    scalar_values = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "authors",
            "applicants",
            "company_ids",
            "inventors",
            "company_roles",
            "patent_ids",
            "research_directions",
            "venue",
            "department",
            "year",
            "aliases",
            "industry",
            "key_personnel",
        }
    }
    invalid_allowed_paths.update(
        source_path_by_field[field]
        for field, value in scalar_values.items()
        if not isinstance(value, str) or not value.strip()
    )
    if domain == "company" and "industry" in values:
        industry, nested_disallowed, nested_invalid = _named_reference_audit(
            values["industry"],
            path="core_facts.industry",
        )
        values["industry"] = industry
        disallowed_paths.update(nested_disallowed)
        invalid_allowed_paths.update(nested_invalid)
    if domain == "paper":
        venue, nested_disallowed, nested_invalid = _named_reference_audit(
            values["venue"],
            path="core_facts.venue",
        )
        values["venue"] = venue
        disallowed_paths.update(nested_disallowed)
        invalid_allowed_paths.update(nested_invalid)
        if (
            not isinstance(values["year"], int)
            or isinstance(values["year"], bool)
            or not 1000 <= values["year"] <= 9999
        ):
            invalid_allowed_paths.add("core_facts.year")
    if domain == "professor":
        department, nested_disallowed, nested_invalid = _named_reference_audit(
            values["department"],
            path="core_facts.department",
        )
        values["department"] = department
        disallowed_paths.update(nested_disallowed)
        invalid_allowed_paths.update(nested_invalid)
    return _SelectedFieldAudit(
        domain=domain,
        selected=cast(dict[str, JsonValue], values),
        disallowed_paths=tuple(sorted(disallowed_paths)),
        invalid_allowed_paths=tuple(sorted(invalid_allowed_paths)),
        quality_signals=tuple(sorted(quality_signals)),
        defaulted_fields=frozenset(defaulted_fields),
        signaled_fields=frozenset(signaled_fields),
    )


def _quality_signal_source_path(field: str) -> str:
    if field == "profile_summary":
        return "summary_fields.profile_summary"
    return f"core_facts.{field}"


def _structural_payload_affected_paths(payload: dict[str, Any]) -> tuple[str, ...]:
    object_type = payload.get("object_type")
    core = payload.get("core_facts")
    summary = payload.get("summary_fields")
    affected = {
        path
        for path, value in (("core_facts", core), ("summary_fields", summary))
        if not isinstance(value, dict)
    }
    present_paths = _present_projection_paths(
        core if isinstance(core, dict) else {},
        summary if isinstance(summary, dict) else {},
    )
    allowed_paths = set(_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE.get(str(object_type), ()))
    affected.update(present_paths - allowed_paths)
    if (
        object_type in _PUBLIC_DOMAINS
        and isinstance(core, dict)
        and isinstance(summary, dict)
    ):
        affected.update(_selected_fields(payload).affected_paths)
    elif object_type == "professor_paper_link":
        for endpoint in ("professor_id", "paper_id"):
            endpoint_value = core.get(endpoint) if isinstance(core, dict) else None
            if not isinstance(endpoint_value, str) or not endpoint_value.strip():
                affected.add(f"core_facts.{endpoint}")
    elif object_type not in (*_PUBLIC_DOMAINS, "professor_paper_link"):
        affected.add("object_type")
    return tuple(sorted(affected))


def _parse_aware_not_future(value: Any, *, as_of: datetime) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed > as_of:
        return None
    return parsed


def _metadata_invalid_paths(
    payload: dict[str, Any], *, as_of: datetime
) -> tuple[str, ...]:
    invalid: set[str] = set()
    if (
        not isinstance(payload.get("display_name"), str)
        or not payload["display_name"].strip()
    ):
        invalid.add("display_name")
    if (
        not isinstance(payload.get("quality_status"), str)
        or not payload["quality_status"].strip()
    ):
        invalid.add("quality_status")
    if _parse_aware_not_future(payload.get("last_updated"), as_of=as_of) is None:
        invalid.add("last_updated")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        invalid.add("evidence")
    else:
        for index, item in enumerate(evidence):
            prefix = f"evidence[{index}]"
            if not isinstance(item, dict):
                invalid.add(prefix)
                continue
            if (
                not isinstance(item.get("source_type"), str)
                or not item["source_type"].strip()
            ):
                invalid.add(f"{prefix}.source_type")
            source_url = item.get("source_url")
            source_file = item.get("source_file")
            if not (
                isinstance(source_url, str)
                and source_url.strip()
                or isinstance(source_file, str)
                and source_file.strip()
            ):
                invalid.add(f"{prefix}.locator")
            if _parse_aware_not_future(item.get("fetched_at"), as_of=as_of) is None:
                invalid.add(f"{prefix}.fetched_at")
    return tuple(sorted(invalid))


def _payload_schema_audit(
    payload: dict[str, Any], *, as_of: datetime
) -> _PayloadSchemaAudit:
    disallowed: set[str] = set()
    invalid = set(_metadata_invalid_paths(payload, as_of=as_of))
    try:
        HistoricalReleasedObject.model_validate(payload)
    except ValidationError as exc:
        for error in exc.errors():
            location = tuple(error["loc"])
            path = _pydantic_location_path(location)
            if (
                error["type"] == "value_error"
                and len(location) == 2
                and location[0] == "evidence"
                and isinstance(location[1], int)
                and "source_url or source_file" in str(error.get("msg", ""))
            ):
                path = f"evidence[{location[1]}].locator"
            if not path:
                path = "payload_json"
            if error["type"] == "extra_forbidden":
                disallowed.add(path)
            else:
                invalid.add(path)
    return _PayloadSchemaAudit(
        disallowed_paths=tuple(sorted(disallowed)),
        invalid_allowed_paths=tuple(sorted(invalid)),
    )


def _observed_at(payload: dict[str, Any], as_of: datetime) -> datetime:
    raw = payload.get("last_updated")
    parsed = _parse_aware_not_future(raw, as_of=as_of)
    if parsed is None:
        raise ValueError("last_updated is not a timezone-aware non-future timestamp")
    return parsed


def _shared_relationship_assertion(
    *,
    request: BuildCandidateRequest,
    item: _ParsedReleasedObject,
    professor_id: str,
    paper_id: str,
    now: datetime,
) -> RelationshipAssertion:
    link_id = cast(str, item.payload["id"])
    retained_id = f"retained:{link_id}"
    return RelationshipAssertion(
        assertion_id=f"relationship-assertion:{link_id}",
        relationship_type_id="professor_attributed_to_paper",
        relationship_type_version="canonical-v2-relationship-v1",
        source_record_id=item.record.record_id,
        source_endpoint=IdentityReference(
            identity_id=f"source-released-object:{professor_id}",
            identity_space=IdentitySpace.source,
            entity_type="professor",
        ),
        target_endpoint=IdentityReference(
            identity_id=f"source-released-object:{paper_id}",
            identity_space=IdentitySpace.source,
            entity_type="paper",
        ),
        attributes={
            "candidate_id": f"candidate:{link_id}",
            "evidence_refs": [retained_id],
            "evidence_metadata": {
                "attribution_basis": [
                    "explicit_accepted_professor_endpoint",
                    "explicit_accepted_paper_endpoint",
                ],
                "source_object_id": link_id,
            },
            "role_bindings": {},
        },
        observed_at=_observed_at(item.payload, now),
        assertion_run_id=f"relationships:{request.run_id}",
    )


def _identity_lookup_key(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    return normalized or None


def _professor_email_lookup_key(selected: Mapping[str, JsonValue]) -> str | None:
    email = selected.get("email")
    if email == _PROFESSOR_MISSING_FIELD_FALLBACK:
        # A defaulted placeholder email carries no attribution evidence.
        return None
    return _identity_lookup_key(email)


def _released_object_identity_keys(
    *,
    object_id: str,
    domain: str,
    selected: Mapping[str, JsonValue],
    payload: Mapping[str, Any],
) -> dict[str, str]:
    keys = {"historical_source_id": object_id}
    core = payload.get("core_facts")
    core = core if isinstance(core, dict) else {}

    def retain(key: str, value: Any) -> None:
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            normalized = str(value).strip()
            if normalized:
                keys[key] = normalized

    if domain == "professor":
        for key, field_name in (
            ("name_key", "name"),
            ("institution_key", "institution"),
            ("department_key", "department"),
            ("email_key", "email"),
            ("homepage_key", "homepage"),
        ):
            value = selected.get(field_name)
            if value == _PROFESSOR_MISSING_FIELD_FALLBACK:
                # Defaulted placeholders are not identity evidence; emitting
                # them would auto-merge unrelated same-name professors.
                continue
            retain(key, value)
    elif domain == "company":
        retain("name_key", selected.get("normalized_name") or selected.get("name"))
    elif domain == "paper":
        retain("title_key", selected.get("title"))
        retain("doi", core.get("doi"))
        retain("publication_year", selected.get("year"))
        authors = selected.get("authors")
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            retain("first_author_key", authors[0].get("name"))
    elif domain == "patent":
        retain("title_key", selected.get("title"))
        retain("publication_number", selected.get("patent_number"))
        applicants = selected.get("applicants")
        if (
            isinstance(applicants, list)
            and applicants
            and isinstance(applicants[0], dict)
        ):
            retain("applicant_key", applicants[0].get("name"))
        retain("filing_date", core.get("filing_date"))
    return keys


@dataclass(frozen=True, slots=True)
class _SupplementalMatchIndexes:
    company_ids_by_name: Mapping[str, frozenset[str]]
    professor_ids_by_name: Mapping[str, frozenset[str]]
    professor_object_ids: frozenset[str]
    paper_ids_by_doi: Mapping[str, frozenset[str]]
    paper_ids_by_title: Mapping[str, frozenset[str]]
    patent_ids_by_number: Mapping[str, frozenset[str]]


def _supplemental_match_indexes(
    *,
    selected_by_object: Mapping[str, Mapping[str, JsonValue]],
    row_by_object: Mapping[str, _ParsedReleasedObject],
) -> _SupplementalMatchIndexes:
    mutable: dict[str, defaultdict[str, set[str]]] = {
        key: defaultdict(set)
        for key in (
            "company",
            "professor",
            "paper_doi",
            "paper_title",
            "patent_number",
        )
    }
    professor_object_ids: set[str] = set()
    for object_id, selected in selected_by_object.items():
        row = row_by_object[object_id]
        domain = row.payload.get("object_type")
        if domain == "company":
            for value in (selected.get("name"), selected.get("normalized_name")):
                if (key := _identity_lookup_key(value)) is not None:
                    mutable["company"][key].add(object_id)
        elif domain == "professor":
            professor_object_ids.add(object_id)
            if (key := _identity_lookup_key(selected.get("name"))) is not None:
                mutable["professor"][key].add(object_id)
        elif domain == "paper":
            core = row.payload.get("core_facts")
            doi = core.get("doi") if isinstance(core, dict) else None
            if (key := _identity_lookup_key(doi)) is not None:
                mutable["paper_doi"][key].add(object_id)
            if (key := _identity_lookup_key(selected.get("title"))) is not None:
                mutable["paper_title"][key].add(object_id)
        elif domain == "patent":
            if (key := _identity_lookup_key(selected.get("patent_number"))) is not None:
                mutable["patent_number"][key].add(object_id)

    def freeze(name: str) -> dict[str, frozenset[str]]:
        return {
            key: frozenset(value) for key, value in sorted(mutable[name].items())
        }

    return _SupplementalMatchIndexes(
        company_ids_by_name=freeze("company"),
        professor_ids_by_name=freeze("professor"),
        professor_object_ids=frozenset(professor_object_ids),
        paper_ids_by_doi=freeze("paper_doi"),
        paper_ids_by_title=freeze("paper_title"),
        patent_ids_by_number=freeze("patent_number"),
    )


def _supplemental_record_object_ids(
    *,
    item: _ParsedReleasedObject,
    indexes: _SupplementalMatchIndexes,
) -> tuple[str, ...]:
    purpose = _SUPPLEMENTAL_SOURCE_PURPOSES[item.source_id]
    payload = item.payload
    if purpose in {"company_knowledge", "company_workbook"}:
        name = payload.get(
            "company_name" if purpose == "company_knowledge" else "公司名称"
        )
        key = _identity_lookup_key(name)
        matches = indexes.company_ids_by_name.get(key or "", frozenset())
    elif purpose == "paper_identifier":
        doi_key = _identity_lookup_key(payload.get("doi"))
        title_key = _identity_lookup_key(payload.get("title"))
        matches = indexes.paper_ids_by_doi.get(doi_key or "", frozenset())
        if not matches:
            matches = indexes.paper_ids_by_title.get(title_key or "", frozenset())
    elif purpose == "patent_identifier":
        number_key = _identity_lookup_key(payload.get("公开（公告）号"))
        matches = indexes.patent_ids_by_number.get(number_key or "", frozenset())
    elif purpose == "professor_backfill":
        professor_id = payload.get("professor_id")
        matches = (
            frozenset({professor_id})
            if isinstance(professor_id, str)
            and professor_id in indexes.professor_object_ids
            else frozenset()
        )
    else:
        professor_key = _identity_lookup_key(payload.get("professor_name"))
        company_key = _identity_lookup_key(payload.get("company_name"))
        professor_matches = indexes.professor_ids_by_name.get(
            professor_key or "", frozenset()
        )
        company_matches = indexes.company_ids_by_name.get(
            company_key or "", frozenset()
        )
        matches = (
            frozenset({*professor_matches, *company_matches})
            if professor_matches and company_matches
            else frozenset()
        )
    return tuple(sorted(matches))


# Professor backfill merges only the fields the historical-source gate can
# demote to explicit placeholders.  Every other researched value (English
# name variants, aliases) is outside the professor projection contract and is
# counted as unsupported instead of widening the projection by stealth.
_PROFESSOR_BACKFILL_MERGE_FIELDS = frozenset(_PROFESSOR_DEGRADABLE_FIELDS)


@dataclass(frozen=True, slots=True)
class _ProfessorBackfillMergeStats:
    records_seen: int = 0
    records_merged: int = 0
    records_unmatched: int = 0
    fields_merged: int = 0
    fields_kept_existing: int = 0
    fields_unsupported: int = 0
    fields_invalid: int = 0


def _professor_projection_field_missing(
    selected: Mapping[str, JsonValue], field: str
) -> bool:
    """A field is mergeable only while the projection carries no real value.

    The gate's synthetic placeholders are not evidence, so they count as
    missing; any other value is historical truth the backfill must keep.
    """
    value = selected.get(field)
    if value is None:
        return True
    if field == "department" and isinstance(value, dict):
        name = value.get("name")
        return (
            not isinstance(name, str)
            or not name.strip()
            or name == _PROFESSOR_MISSING_FIELD_FALLBACK
        )
    if isinstance(value, str):
        if not value.strip():
            return True
        if value == _PROFESSOR_MISSING_FIELD_FALLBACK:
            return True
        return field == "profile_summary" and value == (
            _PROFESSOR_PROFILE_SUMMARY_FALLBACK
        )
    return False


def _professor_backfill_projection_value(field: str, value: Any) -> JsonValue | None:
    """Convert a researched value into the exact projection shape, or None."""
    if field == "department":
        if not isinstance(value, str) or not value.strip():
            return None
        reference, _, invalid = _named_reference_audit(
            value, path=f"fields.{field}.value"
        )
        if invalid or not isinstance(reference, dict):
            return None
        return reference
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip()
    if field == "email":
        # Consistent with selection-time handling: decode only verifiably
        # reversed anti-scrape addresses, never rewrite real mailboxes.
        cleaned, _ = _decode_reversed_professor_email(cleaned)
    return cleaned


def _professor_backfill_field_provenance(
    spec: Any, *, now: datetime
) -> datetime | None:
    """The merged assertion is admissible only with complete provenance."""
    if not isinstance(spec, dict):
        return None
    for key in ("source_url", "evidence_quote", "method"):
        value = spec.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
    return _parse_aware_not_future(spec.get("observed_at"), as_of=now)


def _merge_professor_backfill_rows(
    *,
    request: BuildCandidateRequest,
    rows: tuple[_ParsedReleasedObject, ...],
    selected_by_object: dict[str, dict[str, JsonValue]],
    domain_by_object: Mapping[str, str],
    field_assertions: list[SourceAssertion],
    gaps: list[_RecordedGap],
    now: datetime,
) -> tuple[list[SourceAssertion], _ProfessorBackfillMergeStats]:
    """Merge professor backfill records into the retained projections.

    Conservative semantics: a backfilled value replaces the gate's synthetic
    placeholder assertion for the same field (same assertion id, single
    evidence per group), carries the backfill record as its source and the
    researched observed_at as its evidence time, and never touches a field
    that already carries a real historical value.  Records that do not
    resolve to exactly one retained professor are skipped and counted.
    """
    stats = {"records_seen": 0, "records_merged": 0, "records_unmatched": 0,
             "fields_merged": 0, "fields_kept_existing": 0,
             "fields_unsupported": 0, "fields_invalid": 0}
    assertion_index = {
        assertion.assertion_id: index
        for index, assertion in enumerate(field_assertions)
    }
    merged = list(field_assertions)
    for item in rows:
        if _SUPPLEMENTAL_SOURCE_PURPOSES.get(item.source_id) != "professor_backfill":
            continue
        stats["records_seen"] += 1
        payload = item.payload
        professor_id = payload.get("professor_id")
        selected = (
            selected_by_object.get(professor_id)
            if isinstance(professor_id, str)
            else None
        )
        if selected is None or domain_by_object.get(professor_id or "") != "professor":
            # The supplemental lineage loop already records the unmatched gap.
            stats["records_unmatched"] += 1
            continue
        raw_name = payload.get("professor_name")
        if (
            isinstance(raw_name, str)
            and raw_name.strip()
            and _identity_lookup_key(raw_name)
            != _identity_lookup_key(selected.get("name"))
        ):
            stats["records_unmatched"] += 1
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain="professor",
                    reason=(
                        f"professor backfill record {professor_id!r} name does "
                        "not match the retained professor"
                    ),
                    affected_paths=("professor_name",),
                    now=now,
                )
            )
            continue
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            stats["records_unmatched"] += 1
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain="professor",
                    reason=(
                        f"professor backfill record {professor_id!r} lacks "
                        "typed field payloads"
                    ),
                    affected_paths=("fields",),
                    now=now,
                )
            )
            continue
        merged_here = 0
        skipped_paths: list[str] = []
        for field_name in sorted(fields):
            field_path = f"fields.{field_name}"
            if field_name not in _PROFESSOR_BACKFILL_MERGE_FIELDS:
                stats["fields_unsupported"] += 1
                skipped_paths.append(field_path)
                continue
            spec = fields[field_name]
            observed_at = _professor_backfill_field_provenance(spec, now=now)
            value = (
                _professor_backfill_projection_value(field_name, spec.get("value"))
                if observed_at is not None and isinstance(spec, dict)
                else None
            )
            if observed_at is None or value is None:
                stats["fields_invalid"] += 1
                skipped_paths.append(field_path)
                continue
            if not _professor_projection_field_missing(selected, field_name):
                stats["fields_kept_existing"] += 1
                continue
            selected[field_name] = value
            assertion_id = f"assertion:{professor_id}:{field_name}"
            backfilled = SourceAssertion(
                assertion_id=assertion_id,
                source_record_id=item.record.record_id,
                source_identity_id=f"source-released-object:{professor_id}",
                subject_entity_type="professor",
                field_path=field_name,
                value=value,
                observed_at=observed_at,
                assertion_run_id=f"assertions:{request.run_id}",
            )
            prior = assertion_index.get(assertion_id)
            if prior is None:
                assertion_index[assertion_id] = len(merged)
                merged.append(backfilled)
            else:
                merged[prior] = backfilled
            stats["fields_merged"] += 1
            merged_here += 1
        if merged_here:
            stats["records_merged"] += 1
        if skipped_paths:
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain="professor",
                    reason=(
                        f"professor backfill record {professor_id!r} carries "
                        "fields the professor projection cannot admit"
                    ),
                    affected_paths=tuple(sorted(skipped_paths)),
                    now=now,
                )
            )
    return merged, _ProfessorBackfillMergeStats(**stats)


def _professor_author_aliases(selected: Mapping[str, JsonValue]) -> frozenset[str]:
    aliases = {
        key
        for value in (selected.get("name"),)
        if (key := _identity_lookup_key(value)) is not None
    }
    email = selected.get("email")
    if isinstance(email, str) and "@" in email:
        parts = tuple(
            part
            for part in re.split(r"[^0-9a-zA-Z]+", email.split("@", maxsplit=1)[0])
            if part
        )
        if parts:
            aliases.add("".join(parts).casefold())
        if len(parts) == 2:
            aliases.add("".join(reversed(parts)).casefold())
    return frozenset(aliases)


def _derived_professor_paper_links(
    *,
    source_identities: Mapping[str, SourceIdentity],
    selected_by_object: Mapping[str, Mapping[str, JsonValue]],
    domain_by_object: Mapping[str, str],
    row_by_object: Mapping[str, _ParsedReleasedObject],
    explicitly_anchored_paper_ids: frozenset[str],
    now: datetime,
) -> tuple[_ParsedReleasedObject, ...]:
    professor_ids_by_alias: defaultdict[str, set[str]] = defaultdict(set)
    for object_id, domain in domain_by_object.items():
        if domain != "professor":
            continue
        for alias in _professor_author_aliases(selected_by_object[object_id]):
            professor_ids_by_alias[alias].add(object_id)

    derived: list[_ParsedReleasedObject] = []
    for paper_id, domain in sorted(domain_by_object.items()):
        if domain != "paper" or paper_id in explicitly_anchored_paper_ids:
            continue
        authors = selected_by_object[paper_id].get("authors")
        if not isinstance(authors, list):
            continue
        candidate_ids = {
            professor_id
            for author in authors
            if isinstance(author, dict)
            and (alias := _identity_lookup_key(author.get("name"))) is not None
            for professor_id in professor_ids_by_alias.get(alias, set())
        }
        if not candidate_ids:
            continue
        identity_signatures = {
            (
                _professor_email_lookup_key(selected_by_object[professor_id]),
                _identity_lookup_key(
                    selected_by_object[professor_id].get("institution")
                ),
            )
            for professor_id in candidate_ids
        }
        if len(candidate_ids) > 1 and (
            len(identity_signatures) != 1
            or any(None in signature for signature in identity_signatures)
        ):
            continue
        professor_id = max(
            candidate_ids,
            key=lambda value: (_observed_at(row_by_object[value].payload, now), value),
        )
        paper_row = row_by_object[paper_id]
        link_digest = _canonical_sha256(
            cast(JsonValue, {"paper_id": paper_id, "professor_id": professor_id})
        )
        derived.append(
            _ParsedReleasedObject(
                source_id=paper_row.source_id,
                source_batch_id=paper_row.source_batch_id,
                record=paper_row.record,
                artifact=paper_row.artifact,
                payload={
                    "id": f"derived-professor-paper-link:{link_digest}",
                    "object_type": "professor_paper_link",
                    "display_name": (
                        f"Derived author attribution: {professor_id} -> {paper_id}"
                    ),
                    "core_facts": {
                        "professor_id": professor_id,
                        "paper_id": paper_id,
                    },
                    "summary_fields": {},
                    "evidence": paper_row.payload.get("evidence", []),
                    "last_updated": paper_row.payload.get("last_updated"),
                    "quality_status": paper_row.payload.get("quality_status", "ready"),
                },
            )
        )
    return tuple(derived)


def _bind_snapshot_intervals(
    *,
    assertions: tuple[SourceAssertion, ...],
    canonical_by_source: Mapping[str, str],
) -> tuple[SourceAssertion, ...]:
    grouped: defaultdict[tuple[str, str], list[SourceAssertion]] = defaultdict(list)
    for assertion in assertions:
        grouped[
            (canonical_by_source[assertion.source_identity_id], assertion.field_path)
        ].append(assertion)
    normalized: list[SourceAssertion] = []
    for group in grouped.values():
        observed_times = tuple(sorted({item.observed_at for item in group}))
        if len(group) == 1 or len(observed_times) == 1:
            normalized.extend(group)
            continue
        next_time = {
            observed_at: observed_times[index + 1]
            for index, observed_at in enumerate(observed_times[:-1])
        }
        for assertion in group:
            normalized.append(
                SourceAssertion.model_validate(
                    {
                        **assertion.model_dump(mode="python"),
                        "valid_from": TemporalInstantValue(
                            value=assertion.observed_at
                        ),
                        "valid_to": (
                            TemporalInstantValue(value=next_time[assertion.observed_at])
                            if assertion.observed_at in next_time
                            else None
                        ),
                    }
                )
            )
    return tuple(sorted(normalized, key=lambda item: item.assertion_id))


def _representative_object_ids(
    *,
    identity_result: IdentityResolutionResult,
    row_by_object: Mapping[str, _ParsedReleasedObject],
) -> dict[str, str]:
    source_by_id = {
        source.source_identity_id: source for source in identity_result.source_identities
    }
    representatives: dict[str, str] = {}
    for identity in identity_result.current_canonical_identities:
        object_ids = tuple(
            source_by_id[source_id].source_key
            for source_id in identity.source_identity_ids
        )
        representatives[identity.canonical_identity_id] = max(
            object_ids,
            key=lambda object_id: (
                _observed_at(row_by_object[object_id].payload, identity_result.as_of),
                object_id,
            ),
        )
    return representatives


def _map_public_authority(
    *,
    request: BuildCandidateRequest,
    rows: tuple[_ParsedReleasedObject, ...],
    initial_gaps: tuple[_RecordedGap, ...],
    decision_adapter: _DecisionAdapter,
    now: datetime,
) -> tuple[
    IdentityResolutionRequest,
    IdentityResolutionResult,
    DecisionBatchResult,
    DomainProjectionRequest,
    DomainProjectionResult,
    tuple[_ParsedReleasedObject, ...],
    tuple[_RecordedGap, ...],
]:
    source_rows = rows
    rows = tuple(
        item
        for item in source_rows
        if item.source_id == _RELEASED_OBJECTS_SOURCE_ID
    )
    supplemental_rows = tuple(
        item for item in source_rows if item.source_id in _SUPPLEMENTAL_SOURCE_IDS
    )
    field_policy = _policy(
        kind=PolicyKind.field_selection,
        version="canonical-v2-s12a-single-evidence-v1",
        effective_at=now - timedelta(days=1),
    )
    inclusion_policies = tuple(
        PolicyReference(
            policy_id=f"canonical-v2-{domain}-inclusion",
            policy_version=f"{domain}-inclusion-v1",
            policy_kind=PolicyKind.inclusion,
            content_sha256=_canonical_sha256(
                cast(
                    JsonValue,
                    {
                        "domain": domain,
                        "policy_version": f"{domain}-inclusion-v1",
                    },
                )
            ),
            effective_at=now - timedelta(days=1),
        )
        for domain in _PUBLIC_DOMAINS
    )
    identity_policy = _policy(
        kind=PolicyKind.identity,
        version=CANONICAL_IDENTITY_METHOD_VERSION_V2,
        effective_at=now - timedelta(days=1),
    )
    relationship_policy = _policy(
        kind=PolicyKind.relationship,
        version="professor-paper-attribution-deterministic-v1",
        effective_at=now - timedelta(days=1),
    )
    source_identities: dict[str, SourceIdentity] = {}
    identity_assertions: list[SourceAssertion] = []
    field_assertions: list[SourceAssertion] = []
    selected_by_object: dict[str, dict[str, JsonValue]] = {}
    domain_by_object: dict[str, str] = {}
    row_by_object: dict[str, _ParsedReleasedObject] = {}
    links: list[_ParsedReleasedObject] = []
    payload_audit_by_record: dict[str, _PayloadSchemaAudit] = {}
    gaps = list(initial_gaps)
    object_id_counts = Counter(
        object_id
        for item in rows
        if isinstance((object_id := item.payload.get("id")), str) and object_id
    )
    duplicate_object_ids = {
        object_id for object_id, count in object_id_counts.items() if count > 1
    }

    for item in rows:
        payload = item.payload
        object_id = payload.get("id")
        object_type = payload.get("object_type")
        outer_id = item.record.payload.get("id")
        outer_type = item.record.payload.get("object_type")
        display_name = payload.get("display_name")
        outer_display_name = item.record.payload.get("display_name")
        payload_audit = _payload_schema_audit(payload, as_of=now)
        payload_audit_by_record[item.record.record_id] = payload_audit
        early_structural_paths = _structural_payload_affected_paths(payload)
        identity_type_paths = tuple(
            sorted(
                {
                    *(
                        ("id", "payload_json.id")
                        if not isinstance(object_id, str)
                        or not object_id.strip()
                        or object_id != outer_id
                        else ()
                    ),
                    *(
                        ("object_type", "payload_json.object_type")
                        if object_type != outer_type
                        else ()
                    ),
                    *(
                        ("display_name", "payload_json.display_name")
                        if not isinstance(display_name, str)
                        or not display_name.strip()
                        or display_name != outer_display_name
                        else ()
                    ),
                }
            )
        )
        if (
            not isinstance(object_id, str)
            or not object_id.strip()
            or object_id != outer_id
            or object_type != outer_type
            or not isinstance(display_name, str)
            or not display_name.strip()
            or display_name != outer_display_name
        ):
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain=str(object_type or "cross_domain"),
                    reason=(
                        f"released_objects row {outer_id!r} has cross-wired "
                        "identity/type/display"
                    ),
                    affected_paths=tuple(
                        sorted(
                            {
                                *identity_type_paths,
                                *payload_audit.affected_paths,
                                *early_structural_paths,
                            }
                        )
                    ),
                    now=now,
                )
            )
            continue
        if object_id in duplicate_object_ids:
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain=str(object_type),
                    reason=(
                        f"released_objects row {object_id!r} has a duplicate "
                        "object identity across admitted batches"
                    ),
                    affected_paths=tuple(
                        sorted(
                            {
                                "identity.object_id",
                                *payload_audit.affected_paths,
                                *early_structural_paths,
                            }
                        )
                    ),
                    now=now,
                )
            )
            continue
        if object_type == "professor_paper_link":
            links.append(item)
            continue
        core = payload.get("core_facts")
        summary = payload.get("summary_fields")
        invalid_container_paths = tuple(
            path
            for path, value in (("core_facts", core), ("summary_fields", summary))
            if not isinstance(value, dict)
        )
        if object_type not in _PUBLIC_DOMAINS or invalid_container_paths:
            present_paths = _present_projection_paths(
                core if isinstance(core, dict) else {},
                summary if isinstance(summary, dict) else {},
            )
            allowed_paths = set(
                _ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE.get(str(object_type), ())
            )
            structural_paths = {
                *invalid_container_paths,
                *(present_paths - allowed_paths),
            }
            tolerant_field_audit: _SelectedFieldAudit | None = None
            if object_type in _PUBLIC_DOMAINS:
                tolerant_payload = {
                    **payload,
                    "core_facts": core if isinstance(core, dict) else {},
                    "summary_fields": summary if isinstance(summary, dict) else {},
                }
                tolerant_field_audit = _selected_fields(tolerant_payload)
                structural_paths.update(tolerant_field_audit.affected_paths)
            if object_type not in _PUBLIC_DOMAINS:
                structural_paths.add("object_type")
            affected_paths = tuple(
                sorted({*payload_audit.affected_paths, *structural_paths})
            )
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain=str(object_type),
                    reason=(
                        f"released_objects row {object_id}: structural audit "
                        + json.dumps(
                            {
                                "invalid_container_paths": list(
                                    invalid_container_paths
                                ),
                                "disallowed_payload_paths": list(
                                    payload_audit.disallowed_paths
                                ),
                                "invalid_metadata_paths": list(
                                    payload_audit.invalid_allowed_paths
                                ),
                                "structural_paths": sorted(structural_paths),
                                "invalid_allowed_paths": list(
                                    tolerant_field_audit.invalid_allowed_paths
                                    if tolerant_field_audit is not None
                                    else ()
                                ),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    ),
                    affected_paths=affected_paths,
                    now=now,
                )
            )
            continue
        field_audit = _selected_fields(payload)
        affected_paths = tuple(
            sorted(
                {
                    *field_audit.affected_paths,
                    *payload_audit.affected_paths,
                    *(
                        _quality_signal_source_path(field)
                        for field in (
                            *field_audit.defaulted_fields,
                            *field_audit.signaled_fields,
                        )
                    ),
                }
            )
        )
        if affected_paths or field_audit.quality_signals:
            audit_payload = {
                "disallowed_paths": sorted(
                    {
                        *field_audit.disallowed_paths,
                        *payload_audit.disallowed_paths,
                    }
                ),
                "invalid_allowed_paths": list(field_audit.invalid_allowed_paths),
                "invalid_metadata_paths": list(payload_audit.invalid_allowed_paths),
                "quality_signals": list(field_audit.quality_signals),
            }
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain=str(object_type),
                    reason=(
                        f"released_objects row {object_id}: field audit "
                        + json.dumps(
                            audit_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    ),
                    affected_paths=affected_paths,
                    now=now,
                )
            )
        if not field_audit.projectable or payload_audit.invalid_allowed_paths:
            continue
        domain = field_audit.domain
        selected = field_audit.selected

        source_identity_id = f"source-released-object:{object_id}"
        observed_at = _observed_at(payload, now)
        display_name = payload.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = object_id
        normalized_keys = _released_object_identity_keys(
            object_id=object_id,
            domain=domain,
            selected=selected,
            payload=payload,
        )
        source_identities[object_id] = SourceIdentity(
            source_identity_id=source_identity_id,
            source_system="accepted-restored-released-objects",
            source_key=object_id,
            entity_type=domain,
            source_record_ids=(item.record.record_id,),
            normalized_keys=normalized_keys,
            first_observed_at=observed_at,
            last_observed_at=observed_at,
            state=SourceIdentityState.active,
        )
        identity_assertions.extend(
            SourceAssertion(
                assertion_id=f"identity-assertion:{object_id}:{key}",
                source_record_id=item.record.record_id,
                source_identity_id=source_identity_id,
                subject_entity_type=domain,
                field_path=f"identity.{key}",
                value=value,
                observed_at=observed_at,
                assertion_run_id=f"identity-assertions:{request.run_id}",
            )
            for key, value in sorted(normalized_keys.items())
        )
        selected_by_object[object_id] = selected
        domain_by_object[object_id] = domain
        row_by_object[object_id] = item
        for field_path, value in sorted(selected.items()):
            assertion_id = f"assertion:{object_id}:{field_path}"
            field_assertions.append(
                SourceAssertion(
                    assertion_id=assertion_id,
                    source_record_id=item.record.record_id,
                    source_identity_id=source_identity_id,
                    subject_entity_type=domain,
                    field_path=field_path,
                    value=value,
                    observed_at=observed_at,
                    assertion_run_id=f"assertions:{request.run_id}",
                )
            )

    supplemental_domains_by_batch: defaultdict[str, set[str]] = defaultdict(set)
    supplemental_indexes = _supplemental_match_indexes(
        selected_by_object=selected_by_object,
        row_by_object=row_by_object,
    )
    for item in supplemental_rows:
        matched_object_ids = _supplemental_record_object_ids(
            item=item,
            indexes=supplemental_indexes,
        )
        if not matched_object_ids:
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain="cross_domain",
                    reason="fixed supplemental record has no exact retained object match",
                    affected_paths=("supporting_source.object_match",),
                    now=now,
                )
            )
            continue
        for matched_object_id in matched_object_ids:
            source = source_identities[matched_object_id]
            source_identities[matched_object_id] = source.model_copy(
                update={
                    "source_record_ids": tuple(
                        sorted({*source.source_record_ids, item.record.record_id})
                    )
                },
                deep=True,
            )
            supplemental_domains_by_batch[item.source_batch_id].add(
                domain_by_object[matched_object_id]
            )

    # Relationship evidence is part of the exact source-identity record lineage.
    valid_links: list[_ParsedReleasedObject] = []
    for item in links:
        core = item.payload.get("core_facts")
        summary = item.payload.get("summary_fields")
        payload_audit = payload_audit_by_record[item.record.record_id]
        if not isinstance(core, dict) or not isinstance(summary, dict):
            invalid_container_paths = tuple(
                path
                for path, value in (
                    ("core_facts", core),
                    ("summary_fields", summary),
                )
                if not isinstance(value, dict)
            )
            present_paths = _present_projection_paths(
                core if isinstance(core, dict) else {},
                summary if isinstance(summary, dict) else {},
            )
            disallowed_paths = tuple(
                sorted(
                    present_paths
                    - set(_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE["professor_paper_link"])
                )
            )
            invalid_endpoint_paths = tuple(
                path
                for path, endpoint, expected_domain in (
                    (
                        "core_facts.professor_id",
                        core.get("professor_id") if isinstance(core, dict) else None,
                        "professor",
                    ),
                    (
                        "core_facts.paper_id",
                        core.get("paper_id") if isinstance(core, dict) else None,
                        "paper",
                    ),
                )
                if not isinstance(endpoint, str)
                or domain_by_object.get(endpoint) != expected_domain
            )
            affected_paths = tuple(
                sorted(
                    {
                        *payload_audit.affected_paths,
                        *invalid_container_paths,
                        *disallowed_paths,
                        *invalid_endpoint_paths,
                    }
                )
            )
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain="cross_domain",
                    reason=(
                        f"relationship row {item.payload.get('id')!r} lacks "
                        "explicit typed endpoint facts"
                    ),
                    affected_paths=affected_paths,
                    now=now,
                )
            )
            continue
        disallowed_paths = tuple(
            sorted(
                _present_projection_paths(core, summary)
                - set(_ALLOWED_FIELD_PATHS_BY_OBJECT_TYPE["professor_paper_link"])
            )
        )
        invalid_endpoint_paths = tuple(
            path
            for path, endpoint, expected_domain in (
                ("core_facts.professor_id", core.get("professor_id"), "professor"),
                ("core_facts.paper_id", core.get("paper_id"), "paper"),
            )
            if not isinstance(endpoint, str)
            or domain_by_object.get(endpoint) != expected_domain
        )
        affected_paths = tuple(
            sorted(
                {
                    *payload_audit.affected_paths,
                    *disallowed_paths,
                    *invalid_endpoint_paths,
                }
            )
        )
        if affected_paths:
            audit_payload = {
                "disallowed_paths": list(disallowed_paths),
                "invalid_endpoint_paths": list(invalid_endpoint_paths),
                "disallowed_payload_paths": list(payload_audit.disallowed_paths),
                "invalid_metadata_paths": list(payload_audit.invalid_allowed_paths),
            }
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=item.record,
                    domain="cross_domain",
                    reason=(
                        f"relationship row {item.payload.get('id')!r}: field audit "
                        + json.dumps(
                            audit_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    ),
                    affected_paths=affected_paths,
                    now=now,
                )
            )
        if invalid_endpoint_paths or payload_audit.invalid_allowed_paths:
            continue
        for endpoint, expected_domain in (
            (core.get("professor_id"), "professor"),
            (core.get("paper_id"), "paper"),
        ):
            assert isinstance(endpoint, str)
            assert domain_by_object[endpoint] == expected_domain
            source = source_identities[endpoint]
            source_identities[endpoint] = source.model_copy(
                update={
                    "source_record_ids": tuple(
                        sorted({*source.source_record_ids, item.record.record_id})
                    )
                },
                deep=True,
            )
        valid_links.append(item)
    links = valid_links

    derived_links = _derived_professor_paper_links(
        source_identities=source_identities,
        selected_by_object=selected_by_object,
        domain_by_object=domain_by_object,
        row_by_object=row_by_object,
        explicitly_anchored_paper_ids=frozenset(
            cast(str, cast(dict[str, Any], item.payload["core_facts"])["paper_id"])
            for item in links
        ),
        now=now,
    )
    for item in derived_links:
        core = cast(dict[str, Any], item.payload["core_facts"])
        for endpoint in (
            cast(str, core["professor_id"]),
            cast(str, core["paper_id"]),
        ):
            source = source_identities[endpoint]
            source_identities[endpoint] = source.model_copy(
                update={
                    "source_record_ids": tuple(
                        sorted({*source.source_record_ids, item.record.record_id})
                    )
                },
                deep=True,
            )
    links.extend(derived_links)

    anchor_by_paper: dict[str, tuple[str, _ParsedReleasedObject]] = {}
    for item in sorted(links, key=lambda value: cast(str, value.payload["id"])):
        core = cast(dict[str, Any], item.payload["core_facts"])
        paper_id = cast(str, core["paper_id"])
        professor_id = cast(str, core["professor_id"])
        anchor_by_paper.setdefault(paper_id, (professor_id, item))
    unanchored_paper_ids = tuple(
        sorted(
            object_id
            for object_id, domain in domain_by_object.items()
            if domain == "paper" and object_id not in anchor_by_paper
        )
    )
    for paper_id in unanchored_paper_ids:
        item = row_by_object[paper_id]
        gaps.append(
            _gap(
                release_id=request.candidate_release_id,
                run_id=request.run_id,
                record=item.record,
                domain="paper",
                reason=(
                    f"released_objects row {paper_id}: no valid Professor "
                    "relationship supplies discovery.professor_anchor_identity_id"
                ),
                affected_paths=("discovery.professor_anchor_identity_id",),
                now=now,
            )
        )
        source_identities.pop(paper_id)
        selected_by_object.pop(paper_id)
        domain_by_object.pop(paper_id)
        row_by_object.pop(paper_id)
    if unanchored_paper_ids:
        removed_source_ids = {
            f"source-released-object:{paper_id}" for paper_id in unanchored_paper_ids
        }
        identity_assertions = [
            assertion
            for assertion in identity_assertions
            if assertion.source_identity_id not in removed_source_ids
        ]
        field_assertions = [
            assertion
            for assertion in field_assertions
            if assertion.source_identity_id not in removed_source_ids
        ]

    # Professor backfill merges after derived attribution so backfilled emails
    # never create new author-attribution aliases; it only fills projection
    # fields the gate demoted to placeholders.
    field_assertions, _backfill_merge_stats = _merge_professor_backfill_rows(
        request=request,
        rows=supplemental_rows,
        selected_by_object=selected_by_object,
        domain_by_object=domain_by_object,
        field_assertions=field_assertions,
        gaps=gaps,
        now=now,
    )

    source_identity_values = tuple(
        sorted(source_identities.values(), key=lambda item: item.source_identity_id)
    )
    identity_request = IdentityResolutionRequest(
        release_id=request.candidate_release_id,
        decision_run_id=request.run_id,
        identity_method_version=CANONICAL_IDENTITY_METHOD_VERSION_V2,
        as_of=now,
        policy=identity_policy,
        source_identities=source_identity_values,
        identity_assertions=tuple(
            sorted(identity_assertions, key=lambda item: item.assertion_id)
        ),
    )
    identity_result = create_ephemeral_canonical_identity_resolution_engine().resolve(
        identity_request
    )
    if len(identity_result.source_identity_assignments) != len(source_identity_values):
        raise IsolatedKnowledgeBuildError(
            "explicit historical source identities did not resolve completely"
        )
    canonical_by_source = {
        assignment.source_identity_id: assignment.canonical_identity_id
        for assignment in identity_result.source_identity_assignments
    }

    patent_ids_by_reference: defaultdict[str, set[str]] = defaultdict(set)
    for object_id, domain in domain_by_object.items():
        if domain != "patent":
            continue
        canonical_id = canonical_by_source[f"source-released-object:{object_id}"]
        references = {object_id, canonical_id}
        patent_number = selected_by_object[object_id].get("patent_number")
        if isinstance(patent_number, str) and patent_number.strip():
            references.add(patent_number)
        for reference in references:
            patent_ids_by_reference[reference.strip().casefold()].add(canonical_id)

    normalized_field_assertions: list[SourceAssertion] = []
    for assertion in field_assertions:
        if not (
            assertion.subject_entity_type == "professor"
            and assertion.field_path == "patent_ids"
        ):
            normalized_field_assertions.append(assertion)
            continue
        raw_references = assertion.value
        if not isinstance(raw_references, list):
            raise IsolatedKnowledgeBuildError(
                "validated Professor patent references lost their list shape"
            )
        resolved: set[str] = set()
        unresolved: list[tuple[int, str]] = []
        for index, reference in enumerate(raw_references):
            if not isinstance(reference, str):
                raise IsolatedKnowledgeBuildError(
                    "validated Professor patent reference is not a string"
                )
            matches = patent_ids_by_reference.get(reference.strip().casefold(), set())
            if len(matches) == 1:
                resolved.update(matches)
            else:
                unresolved.append((index, reference))
        normalized_field_assertions.append(
            SourceAssertion.model_validate(
                {
                    **assertion.model_dump(mode="python"),
                    "value": sorted(resolved),
                }
            )
        )
        if unresolved:
            professor_object_id = assertion.source_identity_id.removeprefix(
                "source-released-object:"
            )
            professor_row = row_by_object.get(professor_object_id)
            if professor_row is None:
                raise IsolatedKnowledgeBuildError(
                    "Professor patent reference has no retained source row"
                )
            gaps.append(
                _gap(
                    release_id=request.candidate_release_id,
                    run_id=request.run_id,
                    record=professor_row.record,
                    domain="professor",
                    reason=(
                        "Professor patent references have no unique active "
                        "Candidate Patent: "
                        + json.dumps(
                            [reference for _, reference in unresolved],
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    ),
                    affected_paths=tuple(
                        f"core_facts.patent_ids[{index}]"
                        for index, _ in unresolved
                    ),
                    now=now,
                )
            )
    field_assertions = normalized_field_assertions

    for paper_id, (professor_id, item) in sorted(anchor_by_paper.items()):
        field_assertions.append(
            SourceAssertion(
                assertion_id=f"assertion:{paper_id}:discovery.professor_anchor_identity_id",
                source_record_id=item.record.record_id,
                source_identity_id=f"source-released-object:{paper_id}",
                subject_entity_type="paper",
                field_path="discovery.professor_anchor_identity_id",
                value=canonical_by_source[f"source-released-object:{professor_id}"],
                observed_at=_observed_at(item.payload, now),
                assertion_run_id=f"assertions:{request.run_id}",
            )
        )

    field_assertions = list(
        _bind_snapshot_intervals(
            assertions=tuple(field_assertions),
            canonical_by_source=canonical_by_source,
        )
    )
    assertions_by_subject_path: defaultdict[
        tuple[str, str], list[SourceAssertion]
    ] = defaultdict(list)
    for assertion in field_assertions:
        assertions_by_subject_path[
            (canonical_by_source[assertion.source_identity_id], assertion.field_path)
        ].append(assertion)
    field_groups = tuple(
        FieldAssertionGroup(
            canonical_identity_id=canonical_identity_id,
            field_path=field_path,
            assertions=tuple(
                sorted(assertions, key=lambda item: item.assertion_id)
            ),
            policy=field_policy,
        )
        for (canonical_identity_id, field_path), assertions in sorted(
            assertions_by_subject_path.items()
        )
    )
    relationship_groups: list[RelationshipAssertionGroup] = []
    for item in links:
        link_id = cast(str, item.payload["id"])
        core = cast(dict[str, Any], item.payload["core_facts"])
        professor_id = cast(str, core["professor_id"])
        paper_id = cast(str, core["paper_id"])
        assertion = _shared_relationship_assertion(
            request=request,
            item=item,
            professor_id=professor_id,
            paper_id=paper_id,
            now=now,
        )
        relationship_groups.append(
            RelationshipAssertionGroup(
                canonical_relationship_id=f"relationship:{link_id}",
                relationship_type_id="professor_attributed_to_paper",
                relationship_type_version="canonical-v2-relationship-v1",
                source_canonical_identity_id=canonical_by_source[
                    f"source-released-object:{professor_id}"
                ],
                target_canonical_identity_id=canonical_by_source[
                    f"source-released-object:{paper_id}"
                ],
                assertions=(assertion,),
                policy=relationship_policy,
            )
        )
    decision_request = DecisionBatchRequest(
        release_id=request.candidate_release_id,
        decision_run_id=request.run_id,
        decision_method_version="canonical-decision-v1",
        as_of=now,
        source_identities=identity_result.source_identities,
        canonical_identities=identity_result.current_canonical_identities,
        field_groups=field_groups,
        relationship_groups=tuple(relationship_groups),
    )
    decision_result = create_ephemeral_canonical_decision_engine(
        adjudicator=cast(Any, decision_adapter)
    ).decide(decision_request)

    assertion_ids_by_canonical: dict[str, list[str]] = defaultdict(list)
    for assertion in decision_result.field_assertions:
        assertion_ids_by_canonical[
            canonical_by_source[assertion.source_identity_id]
        ].append(assertion.assertion_id)
    source_identity_by_id = {
        item.source_identity_id: item for item in identity_result.source_identities
    }
    object_id_by_canonical = _representative_object_ids(
        identity_result=identity_result,
        row_by_object=row_by_object,
    )
    artifacts_by_id: dict[str, EvidenceArtifact] = {}
    for item in source_rows:
        existing = artifacts_by_id.setdefault(item.artifact.artifact_id, item.artifact)
        if existing != item.artifact:
            raise IsolatedKnowledgeBuildError(
                "landing artifact identity has conflicting retained content"
            )
    scope_by_domain = {
        "company": "company_skeleton",
        "paper": "paper_roster_discovery",
        "patent": "patent_export",
        "professor": "professor_seed",
    }
    approved_batch_keys = {
        (
            cast(str, item.payload["object_type"]),
            item.source_batch_id,
            item.artifact.artifact_id,
        )
        for item in rows
        if item.payload.get("object_type") in _PUBLIC_DOMAINS
    }
    for item in supplemental_rows:
        for domain in supplemental_domains_by_batch[item.source_batch_id]:
            approved_batch_keys.add(
                (domain, item.source_batch_id, item.artifact.artifact_id)
            )
    approved_manifest = create_approved_source_scope_manifest(
        manifest_version="canonical-v2-s12a-approved-source-scope-v1",
        approved_batches=tuple(
            ApprovedSourceBatch(
                domain=cast(Any, domain),
                scope_kind=cast(Any, scope_by_domain[domain]),
                source_batch_id=source_batch_id,
                artifact_id=artifact_id,
                artifact_content_sha256=artifacts_by_id[artifact_id].content_sha256,
            )
            for domain, source_batch_id, artifact_id in sorted(approved_batch_keys)
        ),
        created_at=now,
    )
    candidates = tuple(
        InclusionCandidate(
            canonical_identity_id=identity.canonical_identity_id,
            domain=cast(Any, identity.entity_type),
            source_identity_ids=identity.source_identity_ids,
            source_record_ids=tuple(
                sorted(
                    {
                        record_id
                        for source_identity_id in identity.source_identity_ids
                        for record_id in source_identity_by_id[
                            source_identity_id
                        ].source_record_ids
                    }
                )
            ),
            supporting_assertion_ids=tuple(
                sorted(assertion_ids_by_canonical[identity.canonical_identity_id])
            ),
            evidence_lane="offline_landing",
            professor_anchor_identity_id=(
                canonical_by_source[
                    f"source-released-object:{anchor_by_paper[object_id_by_canonical[identity.canonical_identity_id]][0]}"
                ]
                if identity.entity_type == "paper"
                else None
            ),
        )
        for identity in identity_result.current_canonical_identities
    )
    inclusion_result = create_ephemeral_domain_inclusion_engine().evaluate(
        InclusionBatchRequest(
            release_id=request.candidate_release_id,
            decision_run_id=request.run_id,
            evaluated_at=now,
            policies=inclusion_policies,
            approved_source_scope_manifest=approved_manifest,
            canonical_identities=identity_result.current_canonical_identities,
            source_identities=identity_result.source_identities,
            evidence_artifacts=tuple(
                sorted(artifacts_by_id.values(), key=lambda item: item.artifact_id)
            ),
            source_records=tuple(
                sorted(
                    (item.record for item in source_rows),
                    key=lambda item: item.record_id,
                )
            ),
            source_assertions=decision_result.field_assertions,
            candidates=candidates,
        )
    )
    domain_request = DomainProjectionRequest(
        release_id=request.candidate_release_id,
        build_run_id=request.run_id,
        as_of=now,
        projection_version="domain-projection-v1",
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        catalog_version=CATALOG_VERSION,
        catalog_content_sha256=CATALOG_CONTENT_SHA256,
        canonical_identities=identity_result.current_canonical_identities,
        source_identity_assignments=identity_result.source_identity_assignments,
        source_assertions=decision_result.field_assertions,
        canonical_decisions=decision_result.canonical_decisions,
        current_fields=tuple(
            item
            for item in decision_result.current_fields
            if item.field_path != "discovery.professor_anchor_identity_id"
        ),
        inclusion_result=inclusion_result,
    )
    domain_result = create_ephemeral_domain_projection_builder().project(domain_request)
    expected_projection_counts = {
        domain: sum(
            identity.entity_type == domain
            for identity in identity_result.current_canonical_identities
        )
        for domain in _PUBLIC_DOMAINS
    }
    if domain_result.counts_by_domain != expected_projection_counts:
        raise IsolatedKnowledgeBuildError(
            "public-domain projections differ from the valid mapped row authority"
        )
    return (
        identity_request,
        identity_result,
        decision_result,
        domain_request,
        domain_result,
        tuple(sorted(links, key=lambda item: cast(str, item.payload["id"]))),
        tuple(sorted(gaps, key=lambda item: item.result.gap_id)),
    )


def _internal_candidate_authority(
    *,
    request: BuildCandidateRequest,
    domain_request: DomainProjectionRequest,
    domain_result: DomainProjectionResult,
    now: datetime,
) -> tuple[
    InternalReferenceProjectionRequest,
    InternalReferenceProjectionResult,
    CandidateProjectionRequest,
    CandidateProjectionResult,
]:
    identity_policy = _policy(
        kind=PolicyKind.identity,
        version=PERSON_IDENTITY_METHOD_VERSION,
        effective_at=now - timedelta(days=1),
    )
    person_request = IdentityResolutionRequest(
        release_id=request.candidate_release_id,
        decision_run_id=f"{request.run_id}:person",
        identity_method_version=PERSON_IDENTITY_METHOD_VERSION,
        as_of=now,
        policy=identity_policy,
        source_identities=(),
        identity_assertions=(),
    )
    person_result: IdentityResolutionResult = (
        create_ephemeral_canonical_identity_resolution_engine().resolve(person_request)
    )
    internal_request = InternalReferenceProjectionRequest(
        release_id=request.candidate_release_id,
        build_run_id=request.run_id,
        as_of=now,
        projection_version="internal-reference-v1",
        reference_catalog_identity=ReferenceCatalogIdentity(
            schema_version=REFERENCE_CATALOG_SCHEMA_VERSION,
            catalog_version=REFERENCE_CATALOG_VERSION,
            content_sha256=REFERENCE_CATALOG_CONTENT_SHA256,
        ),
        public_domain_projection_request=domain_request,
        public_domain_projection_result=domain_result,
        person_identity_resolution_request=person_request,
        person_identity_resolution_result=person_result,
        person_evidence_locators=(),
    )
    internal_result = create_ephemeral_internal_reference_projection_builder().project(
        internal_request
    )
    if any(
        (
            internal_result.person_projections,
            internal_result.technology_concept_projections,
            internal_result.technology_route_projections,
        )
    ):
        raise IsolatedKnowledgeBuildError(
            "unmapped internal references cannot become candidate projections"
        )
    candidate_request = CandidateProjectionRequest(
        release_id=request.candidate_release_id,
        build_run_id=request.run_id,
        as_of=now,
        internal_reference_projection_request=internal_request,
        internal_reference_projection_result=internal_result,
    )
    candidate_result = compose_candidate_projections(candidate_request)
    return internal_request, internal_result, candidate_request, candidate_result


def _source_name_key(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    return normalized or None


def _professor_company_role_id(value: Any) -> str | None:
    key = _source_name_key(value)
    if key in {"发起人", "创始人", "联合创始人", "founder", "cofounder"}:
        return "founder"
    if key in {"顾问", "adviser", "advisor"}:
        return "adviser"
    if key in {"投资人", "投资者", "investor"}:
        return "investor"
    if key in {"员工", "雇员", "employee"}:
        return "employee"
    if key in {"合作人", "合作方", "cooperator"}:
        return "cooperator"
    return None


def _typed_relationship_seeds(
    *,
    source_rows: tuple[_ParsedReleasedObject, ...],
    canonical_by_source: Mapping[str, str],
    canonical_domains: Mapping[str, str],
) -> tuple[_TypedRelationshipSeed, ...]:
    rows_by_object = {
        cast(str, row.payload["id"]): row
        for row in source_rows
        if isinstance(row.payload.get("id"), str)
    }
    company_ids_by_name: dict[str, set[str]] = defaultdict(set)
    professor_ids_by_name: dict[str, set[str]] = defaultdict(set)
    company_name_entries: list[CompanyNameEntry] = []
    for object_id, row in rows_by_object.items():
        canonical_id = canonical_by_source.get(f"source-released-object:{object_id}")
        domain = canonical_domains.get(canonical_id or "")
        if canonical_id is None or domain not in {"company", "professor"}:
            continue
        core = row.payload.get("core_facts")
        if not isinstance(core, dict):
            continue
        if domain == "company":
            for value in (core.get("name"), core.get("normalized_name")):
                if (key := _source_name_key(value)) is not None:
                    company_ids_by_name[key].add(object_id)
            entry_names = tuple(
                value.strip()
                for value in (core.get("name"), core.get("normalized_name"))
                if isinstance(value, str) and value.strip()
            )
            if entry_names:
                company_name_entries.append(
                    CompanyNameEntry(
                        object_id=object_id,
                        canonical_identity_id=canonical_id,
                        names=entry_names,
                    )
                )
        elif (key := _source_name_key(core.get("name"))) is not None:
            professor_ids_by_name[key].add(object_id)
    applicant_link_index = build_company_name_index(company_name_entries)

    seeds: list[_TypedRelationshipSeed] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_seed(
        *,
        relationship_type_id: str,
        source_object_id: str,
        source_domain: str,
        target_object_id: str,
        target_domain: str,
        role_id: str,
        role_owner: Literal["source", "target"],
        evidence_kind: str,
        requested_paths: tuple[str, ...],
        catalog_scenario_id: str,
        evidence_metadata: dict[str, JsonValue],
        source_row: _ParsedReleasedObject,
    ) -> None:
        identity = (
            relationship_type_id,
            canonical_by_source.get(
                f"source-released-object:{source_object_id}", source_object_id
            ),
            canonical_by_source.get(
                f"source-released-object:{target_object_id}", target_object_id
            ),
            role_id,
        )
        if identity in seen:
            return
        seen.add(identity)
        digest = _canonical_sha256(cast(JsonValue, list(identity)))
        seeds.append(
            _TypedRelationshipSeed(
                seed_id=digest,
                relationship_type_id=relationship_type_id,
                source_object_id=source_object_id,
                source_domain=source_domain,
                target_object_id=target_object_id,
                target_domain=target_domain,
                role_id=role_id,
                role_owner=role_owner,
                evidence_kind=evidence_kind,
                requested_paths=requested_paths,
                catalog_scenario_id=catalog_scenario_id,
                evidence_metadata=evidence_metadata,
                source_row=source_row,
            )
        )

    for row in sorted(source_rows, key=lambda item: item.record.record_id):
        if (
            _SUPPLEMENTAL_SOURCE_PURPOSES.get(row.source_id)
            != "professor_company_role"
        ):
            continue
        professor_key = _source_name_key(row.payload.get("professor_name"))
        company_key = _source_name_key(row.payload.get("company_name"))
        role_id = _professor_company_role_id(row.payload.get("role"))
        professor_ids = professor_ids_by_name.get(professor_key or "", set())
        company_ids = company_ids_by_name.get(company_key or "", set())
        professor_canonical_ids = {
            canonical_by_source[f"source-released-object:{object_id}"]
            for object_id in professor_ids
        }
        company_canonical_ids = {
            canonical_by_source[f"source-released-object:{object_id}"]
            for object_id in company_ids
        }
        if (
            role_id is None
            or len(professor_canonical_ids) != 1
            or len(company_canonical_ids) != 1
        ):
            continue
        add_seed(
            relationship_type_id="professor_company_role",
            source_object_id=max(professor_ids),
            source_domain="professor",
            target_object_id=max(company_ids),
            target_domain="company",
            role_id=role_id,
            role_owner="source",
            evidence_kind="professor_company_role_assertion",
            requested_paths=("company_to_professor", "professor_to_company"),
            catalog_scenario_id="catalog_scenario.professor_company_role",
            evidence_metadata={
                "source_field": "professor_company_roles.role",
                "source_role": cast(str, row.payload["role"]),
            },
            source_row=row,
        )

    for object_id, row in sorted(rows_by_object.items()):
        source_canonical_id = canonical_by_source.get(
            f"source-released-object:{object_id}"
        )
        source_domain = canonical_domains.get(source_canonical_id or "")
        core = row.payload.get("core_facts")
        if source_domain == "professor" and isinstance(core, dict):
            roles = core.get("company_roles")
            if isinstance(roles, list):
                for index, role in enumerate(roles):
                    if not isinstance(role, dict):
                        continue
                    company_key = _source_name_key(role.get("company_name"))
                    role_id = _professor_company_role_id(role.get("role"))
                    company_ids = (
                        company_ids_by_name.get(company_key, set())
                        if company_key is not None
                        else set()
                    )
                    if role_id is None or len(company_ids) != 1:
                        continue
                    add_seed(
                        relationship_type_id="professor_company_role",
                        source_object_id=object_id,
                        source_domain="professor",
                        target_object_id=next(iter(company_ids)),
                        target_domain="company",
                        role_id=role_id,
                        role_owner="source",
                        evidence_kind="professor_company_role_assertion",
                        requested_paths=(
                            "company_to_professor",
                            "professor_to_company",
                        ),
                        catalog_scenario_id=(
                            "catalog_scenario.professor_company_role"
                        ),
                        evidence_metadata={
                            "source_field": f"core_facts.company_roles[{index}]",
                            "source_role": cast(str, role["role"]),
                        },
                        source_row=row,
                    )
        if source_domain == "patent" and isinstance(core, dict):
            target_object_ids = core.get("company_ids")
            if not isinstance(target_object_ids, list):
                target_object_ids = []
            for index, target_object_id in enumerate(target_object_ids):
                if not isinstance(target_object_id, str):
                    continue
                target_canonical_id = canonical_by_source.get(
                    f"source-released-object:{target_object_id}"
                )
                if canonical_domains.get(target_canonical_id or "") != "company":
                    continue
                add_seed(
                    relationship_type_id="patent_has_applicant",
                    source_object_id=object_id,
                    source_domain="patent",
                    target_object_id=target_object_id,
                    target_domain="company",
                    role_id="applicant",
                    role_owner="target",
                    evidence_kind="patent_applicant_assertion",
                    requested_paths=("company_to_patent", "patent_to_company"),
                    catalog_scenario_id="catalog_scenario.patent_has_applicant",
                    evidence_metadata={
                        "source_field": f"core_facts.company_ids[{index}]",
                    },
                    source_row=row,
                )
            if not target_object_ids:
                # No upstream company ids: resolve applicant names against
                # released companies (unique-match only; ambiguous abstains).
                applicant_names = core.get("applicants")
                if isinstance(applicant_names, list):
                    for applicant_index, resolution in enumerate(
                        resolve_patent_applicant_links(
                            applicant_names=applicant_names,
                            index=applicant_link_index,
                        )
                    ):
                        if (
                            resolution.status != "accepted"
                            or resolution.company_object_id is None
                        ):
                            continue
                        add_seed(
                            relationship_type_id="patent_has_applicant",
                            source_object_id=object_id,
                            source_domain="patent",
                            target_object_id=resolution.company_object_id,
                            target_domain="company",
                            role_id="applicant",
                            role_owner="target",
                            evidence_kind="patent_applicant_assertion",
                            requested_paths=("company_to_patent", "patent_to_company"),
                            catalog_scenario_id="catalog_scenario.patent_has_applicant",
                            evidence_metadata={
                                "source_field": f"core_facts.applicants[{applicant_index}]",
                                "match_kind": resolution.match_kind,
                                "matched_company_name": resolution.matched_company_name,
                            },
                            source_row=row,
                        )
    return tuple(sorted(seeds, key=lambda item: item.seed_id))


def _relationship_authority(
    *,
    request: BuildCandidateRequest,
    identity_result: IdentityResolutionResult,
    decision_result: DecisionBatchResult,
    domain_result: DomainProjectionResult,
    internal_request: InternalReferenceProjectionRequest,
    internal_result: InternalReferenceProjectionResult,
    links: tuple[_ParsedReleasedObject, ...],
    now: datetime,
    source_rows: tuple[_ParsedReleasedObject, ...] = (),
) -> tuple[RelationshipProjectionRequest, RelationshipProjectionResult]:
    has_internal_references = any(
        (
            internal_result.person_projections,
            internal_result.technology_concept_projections,
            internal_result.technology_route_projections,
        )
    )
    canonical_ids = {
        projection.canonical_identity_id: projection.entity_type
        for projection in domain_result.projections
    }
    relationship_policy = _policy(
        kind=PolicyKind.relationship,
        version="professor-paper-attribution-deterministic-v1",
        effective_at=now - timedelta(days=1),
    )
    candidates: list[RelationshipProjectionCandidate] = []
    assertions: list[RelationshipAssertion] = []
    retained: list[RetainedAssertionReference] = []
    decisions: list[RelationshipDecisionInput] = []
    typed_assertions: list[TypedRelationshipAssertionInput] = []
    source_record_refs: dict[str, set[str]] = defaultdict(set)
    source_types: dict[str, str] = {}
    source_to_canonical: dict[str, str] = {}
    canonical_by_source = {
        assignment.source_identity_id: assignment.canonical_identity_id
        for assignment in identity_result.source_identity_assignments
    }
    decisions_by_relationship = {
        decision.canonical_relationship_id: decision
        for decision in decision_result.relationship_decisions
    }
    typed_seeds = _typed_relationship_seeds(
        source_rows=source_rows,
        canonical_by_source=canonical_by_source,
        canonical_domains=canonical_ids,
    )

    for item in links:
        payload = item.payload
        link_id = cast(str, payload["id"])
        core = payload.get("core_facts")
        if not isinstance(core, dict):
            raise IsolatedKnowledgeBuildError(
                f"relationship row {link_id} lacks explicit endpoint facts"
            )
        historical_professor_id = core.get("professor_id")
        historical_paper_id = core.get("paper_id")
        if not isinstance(historical_professor_id, str) or not isinstance(
            historical_paper_id, str
        ):
            raise IsolatedKnowledgeBuildError(
                f"relationship row {link_id} has malformed endpoint identities"
            )
        professor_source_id = f"source-released-object:{historical_professor_id}"
        paper_source_id = f"source-released-object:{historical_paper_id}"
        professor_id = canonical_by_source.get(professor_source_id)
        paper_id = canonical_by_source.get(paper_source_id)
        if (
            professor_id is None
            or paper_id is None
            or canonical_ids.get(professor_id) != "professor"
            or canonical_ids.get(paper_id) != "paper"
        ):
            raise IsolatedKnowledgeBuildError(
                f"relationship row {link_id} has missing or cross-release endpoints"
            )
        source_record_refs[professor_source_id].add(item.record.record_id)
        source_record_refs[paper_source_id].add(item.record.record_id)
        source_types[professor_source_id] = "professor"
        source_types[paper_source_id] = "paper"
        source_to_canonical[professor_source_id] = professor_id
        source_to_canonical[paper_source_id] = paper_id

        source_endpoint = RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type="professor",
            stable_reference=f"canonical:professor:{professor_id}",
            canonical_identity_id=professor_id,
        )
        target_endpoint = RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type="paper",
            stable_reference=f"canonical:paper:{paper_id}",
            canonical_identity_id=paper_id,
        )
        retained_id = f"retained:{link_id}"
        relationship_assertion_id = f"relationship-assertion:{link_id}"
        decision_input_id = f"relationship-decision-input:{link_id}"
        canonical_relationship_id = f"relationship:{link_id}"
        candidate_id = f"candidate:{link_id}"
        evidence_metadata: dict[str, JsonValue] = {
            "attribution_basis": [
                "explicit_accepted_professor_endpoint",
                "explicit_accepted_paper_endpoint",
            ],
            "source_object_id": link_id,
        }
        binding = RetainedEvidenceBinding(
            evidence_kind="professor_page_or_identity_attribution_assertion",
            assertion_refs=(retained_id,),
            artifact_refs=(),
        )
        observed_at = _observed_at(payload, now)
        candidates.append(
            RelationshipProjectionCandidate(
                candidate_id=candidate_id,
                relationship_type_id="professor_attributed_to_paper",
                relationship_type_version="canonical-v2-relationship-v1",
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                role_bindings={},
                evidence_metadata=evidence_metadata,
                requested_paths=("paper_to_professor", "professor_to_paper"),
                catalog_scenario_id="catalog_scenario.professor_attributed_to_paper",
                observed_at=observed_at,
                evidence_bindings=(binding,),
                assertion_input_id=relationship_assertion_id,
                assertion_input_kind="shared_source_relationship_assertion",
                decision_input_id=decision_input_id,
            )
        )
        retained.append(
            RetainedAssertionReference(
                reference_id=retained_id,
                assertion_id=relationship_assertion_id,
                source_record_ref=item.record.record_id,
                artifact_refs=(),
            )
        )
        assertion = _shared_relationship_assertion(
            request=request,
            item=item,
            professor_id=historical_professor_id,
            paper_id=historical_paper_id,
            now=now,
        )
        assertions.append(assertion)
        durable_decision = decisions_by_relationship.get(canonical_relationship_id)
        if durable_decision is None:
            raise IsolatedKnowledgeBuildError(
                f"relationship row {link_id} lacks its Accepted decision result"
            )
        decisions.append(
            RelationshipDecisionInput(
                decision_input_id=decision_input_id,
                decision_id=durable_decision.decision_id,
                canonical_relationship_id=canonical_relationship_id,
                state=durable_decision.state.value,
                candidate_assertion_ids=durable_decision.candidate_assertion_ids,
                selected_assertion_ids=durable_decision.selected_assertion_ids,
                conflicting_assertion_ids=(durable_decision.conflicting_assertion_ids),
                role_bindings=durable_decision.role_bindings,
                selected_evidence_refs=(retained_id,),
                policy=durable_decision.policy,
                method=durable_decision.method,
                method_version=durable_decision.method_version,
                confidence=durable_decision.confidence,
                rationale=durable_decision.rationale,
                supersedes_decision_id=durable_decision.supersedes_decision_id,
            )
        )

    for seed in typed_seeds:
        source_identity_id = f"source-released-object:{seed.source_object_id}"
        target_identity_id = f"source-released-object:{seed.target_object_id}"
        source_id = canonical_by_source[source_identity_id]
        target_id = canonical_by_source[target_identity_id]
        for endpoint_identity_id, endpoint_type, endpoint_canonical_id in (
            (source_identity_id, seed.source_domain, source_id),
            (target_identity_id, seed.target_domain, target_id),
        ):
            source_record_refs[endpoint_identity_id].add(
                seed.source_row.record.record_id
            )
            source_types[endpoint_identity_id] = endpoint_type
            source_to_canonical[endpoint_identity_id] = endpoint_canonical_id
        source_endpoint = RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type=seed.source_domain,
            stable_reference=f"canonical:{seed.source_domain}:{source_id}",
            canonical_identity_id=source_id,
        )
        target_endpoint = RelationshipEndpointReference(
            reference_kind="canonical_identity",
            endpoint_type=seed.target_domain,
            stable_reference=f"canonical:{seed.target_domain}:{target_id}",
            canonical_identity_id=target_id,
        )
        candidate_id = f"candidate:source-relationship:{seed.seed_id}"
        assertion_id = f"typed-relationship-assertion:{seed.seed_id}"
        retained_id = f"retained:source-relationship:{seed.seed_id}"
        decision_input_id = f"relationship-decision-input:{seed.seed_id}"
        canonical_relationship_id = f"relationship:source:{seed.seed_id}"
        owner = source_endpoint if seed.role_owner == "source" else target_endpoint
        role_bindings = {seed.role_id: owner.stable_reference}
        binding = RetainedEvidenceBinding(
            evidence_kind=seed.evidence_kind,
            assertion_refs=(retained_id,),
            artifact_refs=(),
        )
        observed_at = (
            seed.source_row.record.parsed_at
            if seed.source_row.source_id in _SUPPLEMENTAL_SOURCE_IDS
            else _observed_at(seed.source_row.payload, now)
        )
        candidates.append(
            RelationshipProjectionCandidate(
                candidate_id=candidate_id,
                relationship_type_id=seed.relationship_type_id,
                relationship_type_version="canonical-v2-relationship-v1",
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                role_bindings=role_bindings,
                evidence_metadata=seed.evidence_metadata,
                requested_paths=seed.requested_paths,
                catalog_scenario_id=seed.catalog_scenario_id,
                observed_at=observed_at,
                evidence_bindings=(binding,),
                assertion_input_id=assertion_id,
                assertion_input_kind="typed_relationship_assertion",
                decision_input_id=decision_input_id,
            )
        )
        retained.append(
            RetainedAssertionReference(
                reference_id=retained_id,
                assertion_id=assertion_id,
                source_record_ref=seed.source_row.record.record_id,
                artifact_refs=(),
            )
        )
        typed_assertions.append(
            TypedRelationshipAssertionInput(
                assertion_id=assertion_id,
                relationship_type_id=seed.relationship_type_id,
                relationship_type_version="canonical-v2-relationship-v1",
                source_record_ref=seed.source_row.record.record_id,
                source_endpoint=source_endpoint,
                target_endpoint=target_endpoint,
                attributes={
                    "candidate_id": candidate_id,
                    "evidence_metadata": seed.evidence_metadata,
                    "role_bindings": cast(JsonValue, role_bindings),
                },
                evidence_bindings=(binding,),
                observed_at=observed_at,
                assertion_run_id=f"relationships:{request.run_id}",
            )
        )
        decisions.append(
            RelationshipDecisionInput(
                decision_input_id=decision_input_id,
                decision_id=f"relationship-decision:sha256:{seed.seed_id}",
                canonical_relationship_id=canonical_relationship_id,
                state="accepted",
                candidate_assertion_ids=(assertion_id,),
                selected_assertion_ids=(assertion_id,),
                conflicting_assertion_ids=(),
                role_bindings=role_bindings,
                selected_evidence_refs=(retained_id,),
                policy=relationship_policy,
                method=DecisionMethod.deterministic,
                method_version="source-relationship-deterministic-v1",
                confidence=1.0,
                rationale="Explicit source relationship endpoints and supported role.",
            )
        )

    assignments = tuple(
        SourceCanonicalAssignment(
            assignment_id=f"relationship-assignment:{source_identity_id}",
            source_identity_id=source_identity_id,
            canonical_identity_id=source_to_canonical[source_identity_id],
            entity_type=source_types[source_identity_id],
            source_record_refs=tuple(sorted(record_ids)),
        )
        for source_identity_id, record_ids in sorted(source_record_refs.items())
    )
    bind_internal_graph = bool(links or typed_seeds or has_internal_references)
    relationship_request = RelationshipProjectionRequest(
        catalog=RelationshipCatalogIdentity(
            schema_version=CATALOG_SCHEMA_VERSION,
            catalog_version=CATALOG_VERSION,
            content_sha256=CATALOG_CONTENT_SHA256,
        ),
        relationship_registry_version=(
            INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
            if bind_internal_graph
            else LEGACY_RELATIONSHIP_REGISTRY_VERSION
        ),
        relationship_registry_content_sha256=(
            INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_CONTENT_SHA256
            if bind_internal_graph
            else LEGACY_RELATIONSHIP_REGISTRY_CONTENT_SHA256
        ),
        release_id=request.candidate_release_id,
        projection_run_id=request.run_id,
        as_of=now,
        decision_policy=relationship_policy,
        domain_projections=domain_result.projections,
        internal_reference_projection_request=(
            internal_request if bind_internal_graph else None
        ),
        internal_reference_projection_result=(
            internal_result if bind_internal_graph else None
        ),
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        relationship_assertions=tuple(
            sorted(assertions, key=lambda item: item.assertion_id)
        ),
        typed_relationship_assertions=tuple(
            sorted(typed_assertions, key=lambda item: item.assertion_id)
        ),
        source_canonical_assignments=assignments,
        decision_inputs=tuple(
            sorted(decisions, key=lambda item: item.decision_input_id)
        ),
        retained_assertions=tuple(sorted(retained, key=lambda item: item.reference_id)),
        retained_artifacts=(),
    )
    relationship_result = create_ephemeral_relationship_projection().project(
        relationship_request
    )
    if len(relationship_result.current_relationships) != len(links) + len(typed_seeds) or any(
        not item.admitted for item in relationship_result.candidate_outcomes
    ):
        raise IsolatedKnowledgeBuildError(
            "explicit source relationship projection is incomplete"
        )
    return relationship_request, relationship_result


def _release_bundle_relationship_authority(
    request: RelationshipProjectionRequest,
    result: RelationshipProjectionResult,
) -> tuple[
    RelationshipProjectionRequest | None,
    RelationshipProjectionResult | None,
]:
    has_relationship_records = any(
        (
            request.candidates,
            request.relationship_assertions,
            request.typed_relationship_assertions,
            result.retained_relationship_assertions,
            result.typed_relationship_assertions,
            result.relationship_decisions,
            result.typed_relationship_decisions,
            result.candidate_outcomes,
            result.current_relationships,
        )
    )
    if not has_relationship_records:
        return None, None
    if (
        request.internal_reference_projection_request is None
        or request.internal_reference_projection_result is None
        or request.relationship_registry_version
        != INTERNAL_REFERENCE_RELATIONSHIP_REGISTRY_VERSION
    ):
        raise IsolatedKnowledgeBuildError(
            "nonzero public-only relationship authority cannot enter the "
            "Accepted isolated release bundle"
        )
    return request, result


def _index_authority(
    *,
    request: BuildCandidateRequest,
    candidate_request: CandidateProjectionRequest,
    candidate_result: CandidateProjectionResult,
    now: datetime,
) -> tuple[
    tuple[PathEligibilityRequest, ...],
    tuple[PathEligibilityResult, ...],
    IndexProjectionRequest,
    IndexProjectionResult,
]:
    domain_result = candidate_request.internal_reference_projection_request.public_domain_projection_result
    inclusions = {
        item.subject_identity_id: item for item in domain_result.inclusion_decisions
    }
    path_version = request.policy_versions["path_eligibility"]
    path_policy = _policy(
        kind=PolicyKind.path_eligibility,
        version=path_version,
        effective_at=now - timedelta(days=1),
    )
    path_requests: list[PathEligibilityRequest] = []
    path_results: list[PathEligibilityResult] = []
    for projection in domain_result.projections:
        field_assertion_ids = {
            lineage.field_path: lineage.supporting_assertion_ids
            for lineage in projection.field_lineage
        }
        typed_projection = TypedProjectionInput(
            projection_id=(
                f"typed:{projection.entity_type}:{projection.canonical_identity_id}"
            ),
            canonical_identity_id=projection.canonical_identity_id,
            domain=projection.entity_type,
            release_id=projection.release_id,
            canonical_identity_state=CanonicalIdentityState.active,
            domain_identity_status=(
                "confirmed" if projection.entity_type == "paper" else None
            ),
            usable_field_paths=tuple(sorted(field_assertion_ids)),
            field_assertion_ids=field_assertion_ids,
            quality_signals=(),
        )
        path_request = PathEligibilityRequest(
            release_id=request.candidate_release_id,
            policy=path_policy,
            projection=typed_projection,
            inclusion_decision=inclusions[projection.canonical_identity_id],
            relationship_decisions=(),
            published_paths=PUBLISHED_USER_PATHS,
            evaluated_at=now,
        )
        path_result = PathEligibilityEngine().evaluate(path_request)
        path_requests.append(path_request)
        path_results.append(path_result)
    request_values = tuple(path_requests)
    result_values = tuple(path_results)
    index_request = IndexProjectionRequest(
        candidate_projection_request=candidate_request,
        candidate_projection_result=candidate_result,
        public_path_eligibility_requests=request_values,
        public_path_eligibility_results=result_values,
        index_projection_version="canonical-v2-index-projection-v1",
        vector_schema_version="canonical-v2-vector-schema-v1",
        embedding_model=request.model_versions["embedding"],
        internal_auxiliary_policy_version="internal-evidence-anchor-v1",
        build_mode="full",
    )
    pure_result = create_ephemeral_index_projection_builder().build(index_request)
    return request_values, result_values, index_request, pure_result


def _manifest_sections(
    *,
    request: BuildCandidateRequest,
    decision: DecisionBatchResult,
    candidate_result: CandidateProjectionResult,
    internal_result: InternalReferenceProjectionResult,
    relationship_result: RelationshipProjectionResult,
    eligibility_results: tuple[PathEligibilityResult, ...],
) -> tuple[
    ManifestSection,
    tuple[ManifestSection, ...],
    ManifestSection,
    tuple[ManifestSection, ...],
]:
    decision_section = ManifestSection(
        section_id="decisions",
        release_id=request.candidate_release_id,
        version="canonical-v2-s12a-authority-v1",
        record_count=(
            len(decision.canonical_decisions) + len(decision.relationship_decisions)
        ),
        content_sha256=decision.content_sha256,
    )
    published_by_domain = {
        item.domain: item
        for item in candidate_result.published_projections
        if item.domain is not None
    }
    object_sections = tuple(
        ManifestSection(
            section_id=f"objects:{domain}",
            release_id=request.candidate_release_id,
            version=candidate_result.public_domain_projection_version,
            record_count=published_by_domain[domain].record_count,
            content_sha256=published_by_domain[domain].content_sha256,
        )
        for domain in _PUBLIC_DOMAINS
    )
    relationship_section = ManifestSection(
        section_id="relationships",
        release_id=request.candidate_release_id,
        version=relationship_result.projection_schema_version,
        record_count=len(relationship_result.current_relationships),
        content_sha256=relationship_result.content_sha256,
    )
    internal_section = ManifestSection(
        section_id="eligibility:internal-reference",
        release_id=request.candidate_release_id,
        version=internal_result.projection_version,
        record_count=(
            len(internal_result.person_projections)
            + len(internal_result.technology_concept_projections)
            + len(internal_result.technology_route_projections)
        ),
        content_sha256=internal_result.content_sha256,
    )
    path_sections = tuple(
        ManifestSection(
            section_id=f"eligibility:{item.subject_identity_id}",
            release_id=request.candidate_release_id,
            version=request.policy_versions["path_eligibility"],
            record_count=len(item.decisions),
            content_sha256=item.content_sha256,
        )
        for item in eligibility_results
    )
    return (
        decision_section,
        object_sections,
        relationship_section,
        (internal_section, *path_sections),
    )


def _section_kind(section_id: str) -> str:
    if section_id == "decisions":
        return "decision_set"
    if section_id.startswith("objects:"):
        return "object_set"
    if section_id == "relationships":
        return "relationship_set"
    if section_id.startswith("eligibility:"):
        return "eligibility_set"
    raise IsolatedKnowledgeBuildError(f"unknown manifest section kind: {section_id}")


def _candidate_registry_snapshot(
    *,
    candidate: CandidateRelease,
    manifest: BuildManifest,
    sections: tuple[ManifestSection, ...],
    policies: tuple[PolicyReference, ...],
) -> _CandidateRegistrySnapshot:
    return _CandidateRegistrySnapshot(
        release_row=cast(
            dict[NonEmptyStr, JsonValue],
            {
                "release_id": candidate.release_id,
                "build_run_id": candidate.run_id,
                "state": candidate.state.value,
                "manifest_sha256": candidate.manifest_sha256,
                "previous_release_id": None,
                "created_at": manifest.created_at.isoformat(),
            },
        ),
        manifest_row=cast(
            dict[NonEmptyStr, JsonValue],
            {
                "release_id": manifest.release_id,
                "manifest_version": manifest.manifest_version,
                "build_run_id": manifest.build_run_id,
                "source_batch_ids": list(manifest.source_batch_ids),
                "source_batches_sha256": manifest.source_batches_sha256,
                "parser_versions": dict(manifest.parser_versions),
                "policy_versions": dict(manifest.policy_versions),
                "model_versions": dict(manifest.model_versions),
                "manifest_sha256": manifest.manifest_sha256,
                "created_at": manifest.created_at.isoformat(),
            },
        ),
        section_rows=tuple(
            cast(
                dict[NonEmptyStr, JsonValue],
                {
                    "release_id": section.release_id,
                    "section_id": section.section_id,
                    "section_kind": _section_kind(section.section_id),
                    "version": section.version,
                    "record_count": section.record_count,
                    "content_sha256": section.content_sha256,
                },
            )
            for section in sorted(sections, key=lambda item: item.section_id)
        ),
        seeded_policies=tuple(
            sorted(policies, key=lambda item: (item.policy_id, item.policy_version))
        ),
    )


class _ReleasedObjectsSqliteAdapter:
    parser_name = "released_objects_sqlite"

    def validate_source(self, value: AdapterInput) -> None:
        if (
            value.source_kind != "released_objects_sqlite"
            or value.parser.parser_version != "canonical-v2-s12a-full-table-v1"
            or value.parser.options.get("table") != "released_objects"
            or value.parser.options.get("order") != "primary_key"
            or value.parser.options.get("limit") is not None
        ):
            raise ValueError("released_objects parser identity is not Accepted")
        path = Path(value.source_locator)
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError(
                "released_objects staged source is not a safe regular file"
            )

    def parse(self, value: AdapterInput) -> tuple[ParsedRecordDraft, ...]:
        # SQLite WAL-header snapshots cannot be deserialized reliably. Open a
        # private exact-byte copy, then serialize the opened handle before any
        # table query so a pathname replacement cannot cross-wire retained rows.
        content = value.content
        if (
            len(content) < 100
            or content[:16] != b"SQLite format 3\x00"
            or content[18] not in (1, 2)
            or content[19] not in (1, 2)
        ):
            raise ValueError("released_objects SQLite header is invalid")
        source_path = Path(value.source_locator)
        snapshot_path = source_path.with_name(
            f".{source_path.name}.parse.{secrets.token_hex(16)}.sqlite"
        )
        snapshot_fd = -1
        snapshot_identity: tuple[int, int] | None = None
        try:
            snapshot_fd = os.open(
                snapshot_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o400,
            )
            snapshot_stat = os.fstat(snapshot_fd)
            snapshot_identity = (snapshot_stat.st_dev, snapshot_stat.st_ino)
            view = memoryview(content)
            while view:
                written = os.write(snapshot_fd, view)
                view = view[written:]
            os.fsync(snapshot_fd)
            os.close(snapshot_fd)
            snapshot_fd = -1
            uri = f"{snapshot_path.as_uri()}?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA query_only = ON")
                if connection.execute("PRAGMA query_only").fetchone() != (1,):
                    raise ValueError("released_objects SQLite is not query-only")
                opened_content = connection.serialize()
                if opened_content != content:
                    raise ValueError(
                        "opened released_objects SQLite bytes differ from accepted input"
                    )
                del opened_content
                try:
                    schema = tuple(
                        (
                            str(row[1]),
                            str(row[2]).upper(),
                            int(row[3]),
                            row[4],
                            int(row[5]),
                            int(row[6]),
                        )
                        for row in connection.execute(
                            "PRAGMA table_xinfo(released_objects)"
                        )
                    )
                    primary_keys = tuple(item for item in schema if item[4] > 0)
                    if len(primary_keys) != 1 or primary_keys[0][1:] != (
                        "TEXT",
                        0,
                        None,
                        1,
                        0,
                    ):
                        raise ValueError(
                            "released_objects SQLite schema/primary key drifted"
                        )
                    primary_key = primary_keys[0][0]
                    expected_columns = {
                        primary_key: ("TEXT", 0, None, 1, 0),
                        "object_type": ("TEXT", 1, None, 0, 0),
                        "display_name": ("TEXT", 1, None, 0, 0),
                        "payload_json": ("TEXT", 1, None, 0, 0),
                    }
                    if {
                        name: (
                            column_type,
                            not_null,
                            default_value,
                            primary_key_order,
                            hidden,
                        )
                        for (
                            name,
                            column_type,
                            not_null,
                            default_value,
                            primary_key_order,
                            hidden,
                        ) in schema
                    } != expected_columns:
                        raise ValueError(
                            "released_objects SQLite schema/primary key drifted"
                        )
                    table_rows = tuple(
                        row
                        for row in connection.execute("PRAGMA table_list")
                        if row[1] == "released_objects"
                    )
                    if len(table_rows) != 1 or tuple(table_rows[0][:6]) != (
                        "main",
                        "released_objects",
                        "table",
                        4,
                        0,
                        0,
                    ):
                        raise ValueError(
                            "released_objects SQLite table mode/schema drifted"
                        )
                    primary_indexes = tuple(
                        row
                        for row in connection.execute(
                            "PRAGMA index_list(released_objects)"
                        )
                        if int(row[2]) == 1 and row[3] == "pk" and int(row[4]) == 0
                    )
                    if len(primary_indexes) != 1:
                        raise ValueError(
                            "released_objects SQLite primary-key index drifted"
                        )
                    primary_index_name = str(primary_indexes[0][1])
                    quoted_primary_index = (
                        '"' + primary_index_name.replace('"', '""') + '"'
                    )
                    primary_index_columns = tuple(
                        row
                        for row in connection.execute(
                            f"PRAGMA index_xinfo({quoted_primary_index})"
                        )
                        if int(row[5]) == 1
                    )
                    if len(primary_index_columns) != 1 or (
                        str(primary_index_columns[0][2]),
                        int(primary_index_columns[0][3]),
                        str(primary_index_columns[0][4]),
                    ) != (primary_key, 0, "BINARY"):
                        raise ValueError(
                            "released_objects SQLite primary-key semantics drifted"
                        )
                    quoted_primary_key = '"' + primary_key.replace('"', '""') + '"'
                    rows = connection.execute(
                        f'SELECT {quoted_primary_key}, "object_type", "display_name", '
                        f'"payload_json" FROM "released_objects" '
                        f"ORDER BY {quoted_primary_key}"
                    ).fetchall()
                    if connection.serialize() != content:
                        raise ValueError(
                            "released_objects SQLite bytes changed during parsing"
                        )
                finally:
                    connection.rollback()
        finally:
            if snapshot_fd >= 0:
                os.close(snapshot_fd)
            try:
                current = snapshot_path.lstat()
                if (
                    snapshot_identity is not None
                    and (current.st_dev, current.st_ino) == snapshot_identity
                ):
                    snapshot_path.unlink()
            except FileNotFoundError:
                pass
        drafts: list[ParsedRecordDraft] = []
        for row_id, object_type, display_name, payload_json in rows:
            payload = cast(
                dict[NonEmptyStr, JsonValue],
                {
                    "id": row_id,
                    "object_type": object_type,
                    "display_name": display_name,
                    "payload_json": payload_json,
                },
            )
            error_code = "released_objects_malformed_json"
            error_message = "released_objects row has malformed JSON or scalar shape"
            try:
                _load_unique_json_object(payload_json)
                valid = (
                    isinstance(row_id, str)
                    and bool(row_id)
                    and isinstance(object_type, str)
                    and bool(object_type)
                    and isinstance(display_name, str)
                    and bool(display_name)
                )
            except _DuplicateJsonKeyError as exc:
                valid = False
                error_code = "released_objects_duplicate_json_key"
                error_message = str(exc)
            except (TypeError, ValueError, RecursionError):
                valid = False
            errors = ()
            if not valid:
                errors = (
                    SourceError(
                        error_code=error_code,
                        error_kind=SourceErrorKind.parse_error,
                        message=error_message,
                        field_path="payload_json",
                        recoverable=True,
                    ),
                )
            drafts.append(
                ParsedRecordDraft(
                    record_locator=f"released_objects:{row_id}",
                    parse_status=(
                        ParseStatus.parsed if valid else ParseStatus.quarantined
                    ),
                    payload=payload,
                    errors=errors,
                )
            )
        return tuple(drafts)


@dataclass(frozen=True, slots=True)
class _PhysicalIndexAudit:
    points: tuple[Any, ...]
    lookup_documents: tuple[Any, ...]
    index_projections: tuple[Any, ...]
    lookup_projections: tuple[Any, ...]
    content_sha256: str


def _psycopg_dsn(database_url: str) -> str:
    return (
        make_url(database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def _verify_accepted_released_objects_lineage(
    *,
    gate_root: Path,
    entry: SourceBuildEntry,
    member: SourceBuildMember,
) -> None:
    if entry.source_id != _RELEASED_OBJECTS_SOURCE_ID:
        return
    require_accepted_backup_gate(gate_root)
    backup_path = gate_root / "s2b" / "backup-manifest.json"
    backup_bytes = _read_stable_unlinked_regular_file(backup_path)
    if hashlib.sha256(backup_bytes).hexdigest() != _BACKUP_MANIFEST_SHA256:
        raise ValueError("accepted source lineage backup manifest changed")
    try:
        backup = json.loads(backup_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("accepted source lineage backup manifest is invalid") from exc
    sources = backup.get("sources") if isinstance(backup, dict) else None
    records = (
        [
            item
            for item in sources
            if isinstance(item, dict)
            and item.get("source_id") == _RELEASED_OBJECTS_SOURCE_ID
        ]
        if isinstance(sources, list)
        else []
    )
    if len(records) != 1:
        raise ValueError("accepted source lineage record is missing or ambiguous")
    record = records[0]
    backup_root_raw = backup.get("backup_root")
    restore_root_raw = backup.get("restore_root")
    if not isinstance(backup_root_raw, str) or not isinstance(restore_root_raw, str):
        raise ValueError("accepted source lineage roots are missing")
    backup_root = Path(backup_root_raw)
    restore_root = Path(restore_root_raw)
    expected_content_path = restore_root / _RELEASED_OBJECTS_RESTORE_MEMBER_PATH
    if (
        member.content_path != expected_content_path
        or member.restore_member_path != _RELEASED_OBJECTS_RESTORE_MEMBER_PATH
        or member.backup_member_manifest_path
        != _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH
        or member.backup_member_manifest_sha256
        != _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
        or member.source_member_manifest_sha256
        != _RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256
        or record.get("backup_member_manifest_path")
        != str(_RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH)
        or record.get("backup_member_manifest_sha256")
        != _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
        or record.get("source_member_manifest_sha256")
        != _RELEASED_OBJECTS_SOURCE_MEMBER_MANIFEST_SHA256
        or record.get("source_bytes") != _RELEASED_OBJECTS_MEMBER_SIZE
    ):
        raise ValueError("accepted source lineage identity differs")
    member_manifest_path = backup_root / _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_PATH
    _require_unlinked_regular_source(member_manifest_path)
    member_manifest_bytes = _read_stable_unlinked_regular_file(member_manifest_path)
    if (
        hashlib.sha256(member_manifest_bytes).hexdigest()
        != _RELEASED_OBJECTS_BACKUP_MEMBER_MANIFEST_SHA256
    ):
        raise ValueError("accepted source lineage member manifest changed")
    lines = member_manifest_bytes.splitlines()
    if len(lines) != 1:
        raise ValueError("accepted source lineage member manifest is not singular")
    try:
        manifest_record = json.loads(lines[0])
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("accepted source lineage member record is invalid") from exc
    expected_relative_path = "logs/data_agents/released_objects.db"
    if not isinstance(manifest_record, dict) or (
        manifest_record.get("namespace") != "workspace"
        or manifest_record.get("relative_path") != expected_relative_path
        or manifest_record.get("source_bytes") != _RELEASED_OBJECTS_MEMBER_SIZE
        or manifest_record.get("backup_bytes") != _RELEASED_OBJECTS_MEMBER_SIZE
        or manifest_record.get("source_sha256") != _RELEASED_OBJECTS_SHA256
        or manifest_record.get("backup_sha256") != _RELEASED_OBJECTS_SHA256
        or manifest_record.get("copy_independent") is not True
    ):
        raise ValueError("accepted source lineage member record differs")
    source_manifest_line = (
        f"{expected_relative_path}|{_RELEASED_OBJECTS_MEMBER_SIZE}|"
        f"{_RELEASED_OBJECTS_SHA256}\n"
    ).encode("utf-8")
    if (
        hashlib.sha256(source_manifest_line).hexdigest()
        != member.source_member_manifest_sha256
    ):
        raise ValueError("accepted source lineage source manifest differs")


def _prepared_index_root_is_fresh(target: IsolatedIndexTarget) -> bool:
    root = target.root
    if not root.is_absolute() or root.is_symlink():
        return False
    if not root.exists():
        return True
    if not root.is_dir():
        return False
    marker_path = root / ".canonical-v2-isolated-index-target.json"
    try:
        _require_no_symlink_ancestors(marker_path)
        entries = tuple(sorted(item.name for item in root.iterdir()))
        marker_stat = marker_path.lstat()
        marker_bytes = marker_path.read_bytes()
        marker = json.loads(marker_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    expected = {
        "schema_version": "canonical-v2-isolated-index-target-v1",
        "root": str(root),
        "target_id": target.target_id,
        "release_id": target.release_id,
        "target_kind": "isolated-candidate",
        "forbidden_milvus_paths": [str(path) for path in target.forbidden_milvus_paths],
    }
    return (
        entries == (marker_path.name,)
        and marker_path.is_file()
        and not marker_path.is_symlink()
        and marker_stat.st_nlink == 1
        and hashlib.sha256(marker_bytes).hexdigest() == target.marker_sha256
        and marker == expected
    )


def _load_recorded_bundle(
    path: Path,
    *,
    schema_version: str,
    exact_keys: frozenset[str],
) -> dict[str, Any]:
    _require_unlinked_regular_source(path)
    try:
        document = json.loads(_read_stable_unlinked_regular_file(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("recorded offline bundle is unreadable or invalid") from exc
    if not isinstance(document, dict) or set(document) != exact_keys:
        raise ValueError("recorded offline bundle schema differs")
    if document.get("schema_version") != schema_version:
        raise ValueError("recorded offline bundle version differs")
    declared = document.get("content_sha256")
    payload = {key: value for key, value in document.items() if key != "content_sha256"}
    if not isinstance(declared, str) or declared != _canonical_sha256(
        cast(JsonValue, payload)
    ):
        raise ValueError("recorded offline bundle content hash differs")
    return document


@dataclass(frozen=True, slots=True)
class _BoundDecisionAdapter:
    delegate: Any
    authority_sha256: str

    def adjudicate(self, request: Any, /) -> Any:
        return self.delegate.adjudicate(request)


class _BoundEmbeddingAdapter(RecordedEmbeddingAdapter):
    authority_sha256: Sha256


@dataclass(slots=True)
class _OpenAICompatibleEmbeddingAdapter:
    model_id: str
    dimension: int
    authority_sha256: str
    base_url: str
    batch_size: int
    max_workers: int
    timeout_seconds: int
    _cache: OrderedDict[str, tuple[float, ...]] = field(
        default_factory=OrderedDict,
        init=False,
        repr=False,
    )
    _inflight_texts: set[str] = field(default_factory=set, init=False, repr=False)
    _condition: Condition = field(default_factory=Condition, init=False, repr=False)

    _MAX_CACHE_ENTRIES = 16_384

    def embed_batch(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()

        while True:
            with self._condition:
                missing = tuple(
                    dict.fromkeys(text for text in texts if text not in self._cache)
                )
                if not missing:
                    return tuple(self._cache[text] for text in texts)
                if any(text in self._inflight_texts for text in missing):
                    self._condition.wait()
                    continue
                self._inflight_texts.update(missing)
                break

        try:
            vectors = self._embed_uncached(missing)
        except Exception:
            with self._condition:
                self._inflight_texts.difference_update(missing)
                self._condition.notify_all()
            raise

        with self._condition:
            for text, vector in zip(missing, vectors, strict=True):
                self._cache[text] = vector
            protected = set(texts)
            for text in tuple(self._cache):
                if len(self._cache) <= self._MAX_CACHE_ENTRIES:
                    break
                if text not in protected:
                    del self._cache[text]
            self._inflight_texts.difference_update(missing)
            self._condition.notify_all()
            return tuple(self._cache[text] for text in texts)

    def _embed_uncached(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        api_key = load_local_api_key()
        if not api_key:
            raise ValueError("release embedding credential is unavailable")
        batches = tuple(
            texts[offset : offset + self.batch_size]
            for offset in range(0, len(texts), self.batch_size)
        )

        def embed_one(batch: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            client = _OpenAIEmbeddingClient(
                base_url=self.base_url,
                api_key=api_key,
                timeout=float(self.timeout_seconds),
            )
            raw_vectors = client.embed_batch(list(batch), model=self.model_id)
            if len(raw_vectors) != len(batch):
                raise ValueError("release embedding provider returned a different row count")
            vectors: list[tuple[float, ...]] = []
            for raw_vector in raw_vectors:
                vector = tuple(float(value) for value in raw_vector)
                if (
                    len(vector) != self.dimension
                    or not all(math.isfinite(value) for value in vector)
                    or not any(value != 0.0 for value in vector)
                ):
                    raise ValueError("release embedding provider returned an invalid vector")
                vectors.append(vector)
            return tuple(vectors)

        with ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(batches))
        ) as executor:
            parts = tuple(executor.map(embed_one, batches))
        return tuple(vector for part in parts for vector in part)


def load_recorded_decision_adapter(path: Path) -> _DecisionAdapter:
    """Load exact offline adjudication bytes without provider fallback."""

    document = _load_recorded_bundle(
        path,
        schema_version="canonical-v2-recorded-decision-bundle-v1",
        exact_keys=frozenset(
            {
                "schema_version",
                "provider",
                "model",
                "prompt_version",
                "output_schema_version",
                "responses",
                "content_sha256",
            }
        ),
    )
    if document["content_sha256"] != _RECORDED_DECISION_BUNDLE_SHA256:
        raise ValueError("recorded decision bundle differs from frozen S12A authority")
    responses_raw = document["responses"]
    if not isinstance(responses_raw, list):
        raise ValueError("recorded decision bundle responses must be a list")
    responses: list[RecordedAdjudication] = []
    response_keys = {
        "input_evidence_ids",
        "input_evidence_sha256",
        "raw_output",
        "expected_output_sha256",
    }
    for raw in responses_raw:
        if not isinstance(raw, dict) or set(raw) != response_keys:
            raise ValueError("recorded decision response schema differs")
        raw_output = raw["raw_output"]
        if not isinstance(raw_output, str):
            raise ValueError("recorded decision raw output must be exact UTF-8 text")
        responses.append(
            RecordedAdjudication(
                input_evidence_ids=tuple(raw["input_evidence_ids"]),
                input_evidence_sha256=raw["input_evidence_sha256"],
                raw_output=raw_output.encode("utf-8"),
                expected_output_sha256=raw["expected_output_sha256"],
            )
        )
    return _BoundDecisionAdapter(
        delegate=create_recorded_structured_adjudicator(
            provider=cast(str, document["provider"]),
            model=cast(str, document["model"]),
            prompt_version=cast(str, document["prompt_version"]),
            schema_version=cast(str, document["output_schema_version"]),
            responses=tuple(responses),
        ),
        authority_sha256=cast(str, document["content_sha256"]),
    )


def load_recorded_embedding_adapter(path: Path) -> _EmbeddingAdapter:
    """Load the Accepted deterministic local embedding configuration."""

    document = _load_recorded_bundle(
        path,
        schema_version="canonical-v2-recorded-embedding-bundle-v1",
        exact_keys=frozenset(
            {
                "schema_version",
                "model_id",
                "dimension",
                "algorithm",
                "content_sha256",
            }
        ),
    )
    if (
        document["algorithm"] != "canonical-v2-token-hash-l2-v1"
        or document["content_sha256"] != _RECORDED_EMBEDDING_BUNDLE_SHA256
        or document["dimension"] != _RECORDED_EMBEDDING_DIMENSION
    ):
        raise ValueError("recorded embedding bundle differs from frozen S12A authority")
    return _BoundEmbeddingAdapter(
        model_id=document["model_id"],
        dimension=document["dimension"],
        authority_sha256=cast(str, document["content_sha256"]),
    )


def load_content_addressed_embedding_adapter(path: Path) -> _EmbeddingAdapter:
    """Load one frozen build/serving embedding authority without retaining secrets."""

    _require_unlinked_regular_source(path)
    try:
        raw = json.loads(_read_stable_unlinked_regular_file(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("content-addressed embedding bundle is unreadable") from exc
    if not isinstance(raw, dict):
        raise ValueError("content-addressed embedding bundle schema differs")
    if raw.get("schema_version") == "canonical-v2-recorded-embedding-bundle-v1":
        return load_recorded_embedding_adapter(path)

    document = _load_recorded_bundle(
        path,
        schema_version="canonical-v2-openai-compatible-embedding-bundle-v1",
        exact_keys=frozenset(
            {
                "schema_version",
                "provider",
                "model_id",
                "dimension",
                "base_url",
                "api_key_source",
                "batch_size",
                "max_workers",
                "timeout_seconds",
                "content_sha256",
            }
        ),
    )
    expected = {
        "schema_version": "canonical-v2-openai-compatible-embedding-bundle-v1",
        "provider": "openai-compatible",
        "model_id": "Qwen/Qwen3-Embedding-8B",
        "dimension": _QWEN_EMBEDDING_DIMENSION,
        "base_url": "http://100.64.0.27:18005/v1",
        "api_key_source": "local_api_key",
        "batch_size": 32,
        "max_workers": 32,
        "timeout_seconds": 180,
        "content_sha256": _QWEN_EMBEDDING_BUNDLE_SHA256,
    }
    if document != expected:
        raise ValueError("release embedding bundle differs from frozen authority")
    return _OpenAICompatibleEmbeddingAdapter(
        model_id=cast(str, document["model_id"]),
        dimension=cast(int, document["dimension"]),
        authority_sha256=cast(str, document["content_sha256"]),
        base_url=cast(str, document["base_url"]),
        batch_size=cast(int, document["batch_size"]),
        max_workers=cast(int, document["max_workers"]),
        timeout_seconds=cast(int, document["timeout_seconds"]),
    )


@dataclass(frozen=True, slots=True)
class _ExplicitDatabaseTargetConfig:
    target: DestructiveDatabaseTarget

    def get_main_option(self, name: str, default: str | None = None) -> str | None:
        values = {
            "sqlalchemy.url": self.target.url,
            "miroflow.expected_database": self.target.expected_database,
            "miroflow.target_kind": self.target.target_kind,
        }
        return values.get(name, default)


def _resolve_explicit_database_target(
    target: DestructiveDatabaseTarget,
) -> DestructiveDatabaseTarget:
    try:
        resolved = resolve_destructive_database_target(
            _ExplicitDatabaseTargetConfig(target),
            {},
        )
        parsed = make_url(resolved.url)
        if parsed.query:
            raise DatabaseTargetSafetyError(
                "The complete candidate database URL cannot contain caller-owned "
                "libpq query parameters."
            )
        inherited_libpq = sorted(
            key for key in _LIBPQ_CONNECTION_ENVIRONMENT_KEYS if key in os.environ
        )
        if inherited_libpq:
            raise DatabaseTargetSafetyError(
                "The complete candidate database cannot inherit libpq environment "
                f"configuration: {inherited_libpq}"
            )
        try:
            address = ipaddress.ip_address(parsed.host or "")
        except ValueError as exc:
            raise DatabaseTargetSafetyError(
                "The complete candidate database endpoint must be an explicit "
                "numeric loopback address."
            ) from exc
        if not address.is_loopback:
            raise DatabaseTargetSafetyError(
                "The complete candidate database endpoint must be local loopback."
            )
        if parsed.port is None or not parsed.username:
            raise DatabaseTargetSafetyError(
                "The complete candidate database URL requires an explicit port and user."
            )
        safe_url = parsed.update_query_dict(
            {
                "application_name": "canonical-v2-s12a",
                "client_encoding": "UTF8",
                "hostaddr": str(address),
                "options": (
                    "-csession_replication_role=origin\t-ctimezone=UTC"
                    "\t-cgeqo=on\t-cDateStyle=ISO,YMD"
                    "\t-csearch_path=pg_catalog,public"
                ),
                "sslmode": "disable",
                "target_session_attrs": "read-write",
            }
        ).render_as_string(hide_password=False)
        return DestructiveDatabaseTarget(
            url=safe_url,
            expected_database=resolved.expected_database,
            target_kind=resolved.target_kind,
        )
    except DatabaseTargetSafetyError as exc:
        raise IsolatedKnowledgeBuildSafetyError(
            "explicit local database target failed the Accepted safety resolver"
        ) from exc


class _RealBoundary:
    """Accepted local adapters for one explicit disposable candidate target."""

    def __init__(
        self,
        *,
        targets: CompleteCandidateTargetConfig,
        backup_gate_root: Path,
        embedding_adapter: _EmbeddingAdapter,
        clock: Callable[[], datetime],
    ) -> None:
        self._targets = targets
        self._gate_root = backup_gate_root.resolve(strict=False)
        self._embedding_adapter = embedding_adapter
        self._clock = clock
        self._dsn = _psycopg_dsn(targets.database.url)
        repository = PostgresLandingRepository(
            target=targets.database,
            backup_gate_root=self._gate_root,
        )
        self._landing = EvidenceLandingService(
            repository=repository,
            adapters=(
                _ReleasedObjectsSqliteAdapter(),
                HistoricalJsonlAdapter(),
                HistoricalXlsxAdapter(),
            ),
        )

    def resolve_accepted_original_milvus_path(
        self, *, gate_root: Path, expected_sha256: str
    ) -> Path:
        if gate_root.resolve(strict=False) != self._gate_root:
            raise ValueError("backup gate root changed after composition")
        return _derive_accepted_original_milvus_path(
            gate_root=self._gate_root,
            expected_sha256=expected_sha256,
        )

    def verify_accepted_control_files_safe(self, *, gate_root: Path) -> None:
        if gate_root.resolve(strict=False) != self._gate_root:
            raise ValueError("backup gate root changed after composition")
        _verify_accepted_control_files_safe(self._gate_root)

    def resolve_accepted_immutable_paths(
        self, *, gate_root: Path, expected_sha256: str
    ) -> _AcceptedImmutablePaths:
        if gate_root.resolve(strict=False) != self._gate_root:
            raise ValueError("backup gate root changed after composition")
        return _derive_accepted_immutable_paths(
            gate_root=self._gate_root,
            expected_sha256=expected_sha256,
        )

    def verify_accepted_gate(self, *, gate_root: Path) -> BackupGateReceipt:
        if gate_root.resolve(strict=False) != self._gate_root:
            raise ValueError("backup gate root changed after composition")
        return require_accepted_backup_gate(self._gate_root)

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        connection = cast(
            psycopg.Connection[dict[str, Any]],
            psycopg.connect(
                self._dsn,
                autocommit=False,
                row_factory=cast(Any, dict_row),
            ),
        )
        try:
            row = connection.execute(
                "SELECT pg_catalog.current_database() AS database, "
                "pg_catalog.shobj_description(oid, 'pg_database') AS marker "
                "FROM pg_catalog.pg_database "
                "WHERE datname = pg_catalog.current_database()"
            ).fetchone()
            if row is None:
                raise ValueError("candidate database identity is unavailable")
            self._targets.database.verify_database_identity(
                actual_database=row["database"], database_marker=row["marker"]
            )
            session = connection.execute(
                "SELECT pg_catalog.current_setting('session_replication_role') "
                "AS replication_role, "
                "pg_catalog.current_setting('client_encoding') AS client_encoding, "
                "pg_catalog.current_setting('TimeZone') AS timezone, "
                "pg_catalog.current_setting('geqo') AS geqo, "
                "pg_catalog.current_setting('DateStyle') AS date_style, "
                "pg_catalog.current_setting('search_path') AS search_path, "
                "pg_catalog.current_setting('transaction_read_only') "
                "AS transaction_read_only"
            ).fetchone()
            if session != {
                "replication_role": "origin",
                "client_encoding": "UTF8",
                "timezone": "UTC",
                "geqo": "on",
                "date_style": "ISO, YMD",
                "search_path": "pg_catalog,public",
                "transaction_read_only": "off",
            }:
                raise ValueError("candidate database session safety settings differ")
        except Exception:
            connection.close()
            raise
        return connection

    def validate_fresh_targets(
        self, *, target_config: CompleteCandidateTargetConfig
    ) -> None:
        if target_config != self._targets:
            raise ValueError("candidate target configuration changed")
        if self._targets.index.root.exists():
            if not _prepared_index_root_is_fresh(self._targets.index):
                raise ValueError("isolated index target is not fresh marker-only state")
        elif not self._targets.index.root.parent.is_dir():
            raise ValueError("isolated index parent must already exist")
        staging = self._targets.staging.root
        _require_no_symlink_ancestors(staging)
        _require_local_filesystem_path(self._targets.index.root)
        _require_local_filesystem_path(staging)
        protected_paths = (
            self._gate_root,
            self._targets.index.root,
            *self._targets.index.forbidden_milvus_paths,
        )
        if any(_paths_overlap(staging, path) for path in protected_paths):
            raise ValueError("candidate staging overlaps a protected target")
        if staging.exists() or not staging.parent.is_dir():
            raise ValueError("candidate staging target is not fresh")
        self._assert_fresh_database()

    def _assert_fresh_database(self) -> None:
        with self._connect() as connection:
            revisions = connection.execute(
                "SELECT version_num FROM public.canonical_v2_alembic_version "
                "ORDER BY version_num"
            ).fetchall()
            observed_revisions = tuple(str(row["version_num"]) for row in revisions)
            if observed_revisions != (_EXPECTED_ALEMBIC_REVISION,):
                raise ValueError(
                    "candidate database migration revision differs from the live single head"
                )
            relations = connection.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type='BASE TABLE' AND table_schema = ANY(%s) "
                "ORDER BY table_schema, table_name",
                (list(_OWNER_SCHEMAS),),
            ).fetchall()
            observed_tables = {
                f"{relation['table_schema']}.{relation['table_name']}"
                for relation in relations
            }
            if observed_tables != _EXPECTED_OWNER_TABLES:
                missing = sorted(_EXPECTED_OWNER_TABLES - observed_tables)
                extra = sorted(observed_tables - _EXPECTED_OWNER_TABLES)
                raise ValueError(
                    "candidate database owner schema inventory differs: "
                    f"missing={missing}, extra={extra}"
                )
            observed_schema_sha256 = _live_schema_catalog_sha256(connection)
            if observed_schema_sha256 != _EXPECTED_LIVE_SCHEMA_CATALOG_SHA256:
                raise ValueError(
                    "candidate database live schema fingerprint differs: "
                    f"expected={_EXPECTED_LIVE_SCHEMA_CATALOG_SHA256}, "
                    f"observed={observed_schema_sha256}"
                )
            nonempty: list[str] = []
            for relation in relations:
                schema = str(relation["table_schema"])
                table = str(relation["table_name"])
                row = connection.execute(
                    sql.SQL("SELECT EXISTS (SELECT 1 FROM {}.{}) AS has_rows").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                ).fetchone()
                if row is None or bool(row["has_rows"]):
                    nonempty.append(f"{schema}.{table}")
            connection.rollback()
        if nonempty:
            raise ValueError("candidate database is not fresh: " + ", ".join(nonempty))

    def prepare_fresh_targets(
        self, *, target_config: CompleteCandidateTargetConfig
    ) -> None:
        self.validate_fresh_targets(target_config=target_config)
        if self._targets.index.root.exists():
            prepared = self._targets.index
        else:
            prepared = prepare_isolated_index_target(
                root=self._targets.index.root,
                target_id=self._targets.index.target_id,
                release_id=self._targets.index.release_id,
                backup_gate_root=self._gate_root,
                forbidden_milvus_paths=self._targets.index.forbidden_milvus_paths,
            )
        if prepared != self._targets.index:
            raise ValueError("isolated index marker identity differs")
        staging = self._targets.staging.root
        os.mkdir(staging, mode=0o700)
        staging_stat = staging.lstat()
        marker_path = staging / ".canonical-v2-staging.json"
        marker_bytes = (
            self._targets.staging.marker.model_dump_json().encode("utf-8") + b"\n"
        )
        fd = -1
        marker_identity: tuple[int, int] | None = None
        try:
            fd = os.open(
                marker_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            marker_stat = os.fstat(fd)
            marker_identity = (marker_stat.st_dev, marker_stat.st_ino)
            os.write(fd, marker_bytes)
            os.fsync(fd)
            os.close(fd)
            fd = -1
            dir_fd = os.open(staging, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            marker_readback = _read_stable_unlinked_regular_file(marker_path)
            try:
                typed_marker = CandidateStagingMarker.model_validate_json(
                    marker_readback
                )
            except ValidationError as exc:
                raise ValueError(
                    "candidate staging marker readback is invalid"
                ) from exc
            if (
                marker_readback != marker_bytes
                or typed_marker != self._targets.staging.marker
            ):
                raise ValueError("candidate staging marker readback differs")
        except Exception:
            if marker_identity is not None:
                try:
                    current_marker = marker_path.lstat()
                    if (
                        current_marker.st_dev,
                        current_marker.st_ino,
                    ) == marker_identity:
                        marker_path.unlink()
                except FileNotFoundError:
                    pass
            try:
                current_staging = staging.lstat()
                if (current_staging.st_dev, current_staging.st_ino) == (
                    staging_stat.st_dev,
                    staging_stat.st_ino,
                ) and not any(staging.iterdir()):
                    staging.rmdir()
            except FileNotFoundError:
                pass
            raise
        finally:
            if fd >= 0:
                os.close(fd)

    def stage_verified_member(
        self,
        *,
        entry: SourceBuildEntry,
        member: SourceBuildMember,
        destination: Path,
    ) -> _StagedSource:
        if entry.disposition is not SourceDisposition.evidence_input:
            raise ValueError("only evidence input may enter staging")
        inspected = _require_unlinked_regular_source(member.content_path)
        _verify_accepted_released_objects_lineage(
            gate_root=self._gate_root,
            entry=entry,
            member=member,
        )
        source_fd = os.open(
            member.content_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        destination_fd = -1
        destination_identity: tuple[int, int] | None = None
        try:
            before = os.fstat(source_fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or (before.st_dev, before.st_ino)
                != (inspected.st_dev, inspected.st_ino)
            ):
                raise ValueError("accepted source member changed before its first read")
            destination_fd = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            created = os.fstat(destination_fd)
            destination_identity = (created.st_dev, created.st_ino)
            digest = hashlib.sha256()
            byte_size = 0
            while chunk := os.read(source_fd, 1024 * 1024):
                digest.update(chunk)
                byte_size += len(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_fd, view)
                    view = view[written:]
            os.fsync(destination_fd)
            after = os.fstat(source_fd)
            staged = os.fstat(destination_fd)
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                or after.st_nlink != 1
                or (staged.st_dev, staged.st_ino) == (before.st_dev, before.st_ino)
                or byte_size != member.byte_size
                or digest.hexdigest() != member.content_sha256
            ):
                raise ValueError("accepted source changed or staged identity differs")
        except Exception:
            if destination_identity is not None:
                try:
                    current = destination.lstat()
                    if (current.st_dev, current.st_ino) == destination_identity:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise
        finally:
            os.close(source_fd)
            if destination_fd >= 0:
                os.close(destination_fd)
        return _StagedSource(
            path=destination,
            source_id=entry.source_id,
            member_id=member.member_id,
            source_batch_id=member.source_batch_id,
            content_sha256=member.content_sha256,
            byte_size=member.byte_size,
        )

    def land_released_objects(
        self,
        *,
        entry: SourceBuildEntry,
        member: SourceBuildMember,
        staged_member: Any,
        run_id: str,
        observed_at: datetime,
    ) -> _LandingReadback:
        if not isinstance(staged_member, _StagedSource):
            raise TypeError("real landing requires one verified staged source")
        content = _read_stable_unlinked_regular_file(staged_member.path)
        if hashlib.sha256(content).hexdigest() != member.content_sha256:
            raise ValueError("staged source hash changed before landing")
        parent = self._landing.register_artifact(
            RegisterArtifactRequest(
                run_id=f"{run_id}:accepted-restore-parent",
                source_kind="verified_restore_copy",
                source_locator=str(member.content_path),
                content_path=staged_member.path,
                observed_at=observed_at,
                expected_content_sha256=member.content_sha256,
                expected_byte_size=member.byte_size,
            )
        )
        receipt = self._landing.ingest(
            IngestEvidenceRequest(
                run_id=run_id,
                source_batch_id=member.source_batch_id,
                source_kind=member.source_kind,
                source_locator=str(staged_member.path),
                content=content,
                observed_at=observed_at,
                expected_content_sha256=member.content_sha256,
                parser=member.parser,
                parent_artifact_id=parent.artifact_id,
                parent_content_sha256=parent.content_sha256,
            )
        )
        if (
            receipt.parent_artifact_id != parent.artifact_id
            or receipt.parent_content_sha256 != parent.content_sha256
        ):
            raise ValueError("landing receipt lost accepted restore parent lineage")
        artifact = EvidenceArtifact(
            artifact_id=receipt.artifact_id,
            source_kind=member.source_kind,
            source_locator=str(staged_member.path),
            content_sha256=member.content_sha256,
            byte_size=member.byte_size,
            acquired_at=observed_at,
            run_id=run_id,
            parent_artifact_id=parent.artifact_id,
            parent_content_sha256=parent.content_sha256,
        )
        return _LandingReadback(
            receipt=receipt,
            records=self._landing.stream(member.source_batch_id),
            artifact=artifact,
        )

    def persist_candidate_registry_and_identity_policy(
        self,
        *,
        candidate: CandidateRelease,
        manifest: BuildManifest,
        sections: tuple[ManifestSection, ...],
        policies: tuple[PolicyReference, ...],
        relationship_types: tuple[RelationshipType, ...],
    ) -> _CandidateRegistrySnapshot:
        relationship_store = create_postgres_relationship_projection_store(
            database_url=self._targets.database.url,
            expected_database=self._targets.database.expected_database,
            target_kind=self._targets.database.target_kind,
            backup_gate_root=self._gate_root,
        )
        installed_types = relationship_store.install_types(relationship_types)
        if installed_types != tuple(
            sorted(
                relationship_types,
                key=lambda item: (item.relationship_type_id, item.version),
            )
        ):
            raise ValueError("relationship type catalog exact readback differs")
        expected = _candidate_registry_snapshot(
            candidate=candidate,
            manifest=manifest,
            sections=sections,
            policies=policies,
        )
        require_accepted_backup_gate(self._gate_root)
        with self._connect() as connection:
            try:
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (candidate.release_id,),
                )
                connection.execute(
                    "INSERT INTO knowledge.release (release_id, build_run_id, state, "
                    "manifest_sha256, previous_release_id, created_at) VALUES "
                    "(%s, %s, %s, %s, NULL, %s) ON CONFLICT DO NOTHING",
                    (
                        candidate.release_id,
                        candidate.run_id,
                        candidate.state.value,
                        candidate.manifest_sha256,
                        manifest.created_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO publish.build_manifest (release_id, manifest_version, "
                    "build_run_id, source_batch_ids, source_batches_sha256, parser_versions, "
                    "policy_versions, model_versions, manifest_sha256, created_at) VALUES "
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (
                        manifest.release_id,
                        manifest.manifest_version,
                        manifest.build_run_id,
                        Jsonb(list(manifest.source_batch_ids)),
                        manifest.source_batches_sha256,
                        Jsonb(dict(manifest.parser_versions)),
                        Jsonb(dict(manifest.policy_versions)),
                        Jsonb(dict(manifest.model_versions)),
                        manifest.manifest_sha256,
                        manifest.created_at,
                    ),
                )
                for section in sorted(sections, key=lambda item: item.section_id):
                    connection.execute(
                        "INSERT INTO publish.manifest_section (release_id, section_id, "
                        "section_kind, version, record_count, content_sha256) VALUES "
                        "(%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                        (
                            section.release_id,
                            section.section_id,
                            _section_kind(section.section_id),
                            section.version,
                            section.record_count,
                            section.content_sha256,
                        ),
                    )
                for policy in policies:
                    connection.execute(
                        "INSERT INTO knowledge.policy (policy_id, policy_version, policy_kind, "
                        "content_sha256, effective_at) VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT DO NOTHING",
                        (
                            policy.policy_id,
                            policy.policy_version,
                            policy.policy_kind.value,
                            policy.content_sha256,
                            policy.effective_at,
                        ),
                    )
                release_row = connection.execute(
                    "SELECT release_id, build_run_id, state, manifest_sha256, "
                    "previous_release_id, created_at FROM knowledge.release WHERE release_id=%s",
                    (candidate.release_id,),
                ).fetchone()
                manifest_row = connection.execute(
                    "SELECT release_id, manifest_version, build_run_id, source_batch_ids, "
                    "source_batches_sha256, parser_versions, policy_versions, model_versions, "
                    "manifest_sha256, created_at FROM publish.build_manifest WHERE release_id=%s",
                    (candidate.release_id,),
                ).fetchone()
                section_rows = connection.execute(
                    "SELECT release_id, section_id, section_kind, version, record_count, "
                    "content_sha256 FROM publish.manifest_section WHERE release_id=%s "
                    "ORDER BY section_id",
                    (candidate.release_id,),
                ).fetchall()
                policy_rows = tuple(
                    connection.execute(
                        "SELECT policy_id, policy_version, policy_kind, content_sha256, "
                        "effective_at FROM knowledge.policy WHERE policy_id=%s "
                        "AND policy_version=%s",
                        (policy.policy_id, policy.policy_version),
                    ).fetchone()
                    for policy in policies
                )
                if (
                    release_row is None
                    or manifest_row is None
                    or any(row is None for row in policy_rows)
                ):
                    raise ValueError(
                        "candidate registry durable readback is incomplete"
                    )
                actual = _CandidateRegistrySnapshot(
                    release_row=cast(
                        dict[NonEmptyStr, JsonValue],
                        {
                            **release_row,
                            "created_at": release_row["created_at"].isoformat(),
                        },
                    ),
                    manifest_row=cast(
                        dict[NonEmptyStr, JsonValue],
                        {
                            **manifest_row,
                            "created_at": manifest_row["created_at"].isoformat(),
                        },
                    ),
                    section_rows=tuple(
                        cast(dict[NonEmptyStr, JsonValue], row) for row in section_rows
                    ),
                    seeded_policies=tuple(
                        PolicyReference.model_validate(row)
                        for row in policy_rows
                        if row is not None
                    ),
                )
                if actual != expected:
                    raise ValueError(
                        "candidate registry exact durable replay conflicts"
                    )
                connection.commit()
                return actual
            except Exception:
                connection.rollback()
                raise

    def read_candidate_registry(
        self,
        *,
        release_id: str,
        policies: tuple[PolicyReference, ...],
    ) -> _CandidateRegistrySnapshot:
        require_accepted_backup_gate(self._gate_root)
        with self._connect() as connection:
            release_row = connection.execute(
                "SELECT release_id, build_run_id, state, manifest_sha256, "
                "previous_release_id, created_at FROM knowledge.release WHERE release_id=%s",
                (release_id,),
            ).fetchone()
            manifest_row = connection.execute(
                "SELECT release_id, manifest_version, build_run_id, source_batch_ids, "
                "source_batches_sha256, parser_versions, policy_versions, model_versions, "
                "manifest_sha256, created_at FROM publish.build_manifest WHERE release_id=%s",
                (release_id,),
            ).fetchone()
            section_rows = connection.execute(
                "SELECT release_id, section_id, section_kind, version, record_count, "
                "content_sha256 FROM publish.manifest_section WHERE release_id=%s "
                "ORDER BY section_id",
                (release_id,),
            ).fetchall()
            policy_rows = tuple(
                connection.execute(
                    "SELECT policy_id, policy_version, policy_kind, content_sha256, "
                    "effective_at FROM knowledge.policy WHERE policy_id=%s "
                    "AND policy_version=%s",
                    (policy.policy_id, policy.policy_version),
                ).fetchone()
                for policy in policies
            )
            connection.rollback()
        if (
            release_row is None
            or manifest_row is None
            or any(row is None for row in policy_rows)
        ):
            raise ValueError("candidate registry final durable readback is incomplete")
        return _CandidateRegistrySnapshot(
            release_row=cast(
                dict[NonEmptyStr, JsonValue],
                {
                    **release_row,
                    "created_at": release_row["created_at"].isoformat(),
                },
            ),
            manifest_row=cast(
                dict[NonEmptyStr, JsonValue],
                {
                    **manifest_row,
                    "created_at": manifest_row["created_at"].isoformat(),
                },
            ),
            section_rows=tuple(
                cast(dict[NonEmptyStr, JsonValue], row) for row in section_rows
            ),
            seeded_policies=tuple(
                PolicyReference.model_validate(row)
                for row in policy_rows
                if row is not None
            ),
        )

    def persist_identity_resolution(
        self, *, request: IdentityResolutionRequest, result: IdentityResolutionResult
    ) -> IdentityResolutionResult:
        store = create_postgres_canonical_identity_store(
            database_url=self._targets.database.url,
            expected_database=self._targets.database.expected_database,
            target_kind=self._targets.database.target_kind,
            backup_gate_root=self._gate_root,
            build_authority=OFFLINE_BUILD_AUTHORITY,
        )
        return store.persist(request, result)

    def persist_decision_batch(
        self, *, result: DecisionBatchResult
    ) -> DecisionBatchResult:
        return create_postgres_canonical_decision_store(
            database_url=self._targets.database.url,
            expected_database=self._targets.database.expected_database,
            target_kind=self._targets.database.target_kind,
            backup_gate_root=self._gate_root,
        ).persist(result)

    def persist_domain_projection(
        self, *, result: DomainProjectionResult
    ) -> DomainProjectionResult:
        store = create_postgres_domain_projection_store(
            database_url=self._targets.database.url,
            expected_database=self._targets.database.expected_database,
            target_kind=self._targets.database.target_kind,
            backup_gate_root=self._gate_root,
        )
        store.persist(result)
        return store.load(result.release_id)

    def persist_relationship_projection(
        self,
        *,
        request: RelationshipProjectionRequest,
        result: RelationshipProjectionResult,
    ) -> RelationshipProjectionResult:
        return create_postgres_relationship_projection_store(
            database_url=self._targets.database.url,
            expected_database=self._targets.database.expected_database,
            target_kind=self._targets.database.target_kind,
            backup_gate_root=self._gate_root,
        ).persist(request, result)

    def persist_gap(self, *, signal: GapSignal, expected: KnowledgeGap) -> KnowledgeGap:
        if (
            expected.created_at != signal.observed_at
            or expected.updated_at != signal.observed_at
        ):
            raise ValueError("expected gap time differs from its recorded signal")
        actual = create_postgres_knowledge_gap_operations(
            database_url=self._targets.database.url,
            expected_database=self._targets.database.expected_database,
            target_kind=self._targets.database.target_kind,
            backup_gate_root=self._gate_root,
            clock=lambda: signal.observed_at,
        ).record(signal)
        if actual != expected:
            raise ValueError("durable gap differs from the exact Accepted owner result")
        return actual

    def materialize_index(
        self,
        *,
        request: IndexProjectionRequest,
        points: tuple[Any, ...],
        lookup_documents: tuple[Any, ...],
        expected_index_projections: tuple[Any, ...],
        expected_lookup_projections: tuple[Any, ...],
    ) -> IndexProjectionActualState:
        result = create_isolated_index_projection_builder(
            target=self._targets.index,
            backup_gate_root=self._gate_root,
            embedding_adapter=self._embedding_adapter,
            clock=self._clock,
        ).build(request)
        if (
            result.points != points
            or result.lookup_documents != lookup_documents
            or result.expected_index_projections != expected_index_projections
            or result.expected_lookup_projections != expected_lookup_projections
        ):
            raise ValueError("Accepted physical index builder input/output differs")
        return IndexProjectionActualState(
            index_projections=result.actual_index_projections,
            lookup_projections=result.actual_lookup_projections,
        )

    def audit_index(self, *, target: IsolatedIndexTarget) -> _PhysicalIndexAudit:
        if target != self._targets.index:
            raise ValueError("index audit target changed")
        snapshot = audit_isolated_index_snapshot(
            target, embedding_adapter=self._embedding_adapter
        )
        index_projections = snapshot.receipt.index_projections
        lookup_projections = snapshot.receipt.lookup_projections
        content_sha256 = _canonical_sha256(
            cast(
                JsonValue,
                {
                    "points": [
                        item.model_dump(mode="json") for item in snapshot.points
                    ],
                    "lookup_documents": [
                        item.model_dump(mode="json")
                        for item in snapshot.lookup_documents
                    ],
                    "index_projections": [
                        item.model_dump(mode="json") for item in index_projections
                    ],
                    "lookup_projections": [
                        item.model_dump(mode="json") for item in lookup_projections
                    ],
                },
            )
        )
        return _PhysicalIndexAudit(
            points=snapshot.points,
            lookup_documents=snapshot.lookup_documents,
            index_projections=index_projections,
            lookup_projections=lookup_projections,
            content_sha256=content_sha256,
        )

    def read_active_release(self) -> Mapping[str, str] | None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT release_id, canonical_release_id, "
                "published_projection_release_id, index_release_id "
                "FROM publish.active_release WHERE singleton=TRUE"
            ).fetchall()
            connection.rollback()
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("active release state is ambiguous")
        row = rows[0]
        values = (
            row["release_id"],
            row["canonical_release_id"],
            row["published_projection_release_id"],
            row["index_release_id"],
        )
        if len(set(values)) != 1:
            raise ValueError("active release state is cross-wired")
        return {
            "canonical_release_id": row["canonical_release_id"],
            "published_projection_release_id": row["published_projection_release_id"],
            "index_release_id": row["index_release_id"],
        }


class FileCompleteCandidateEnvelopeSink:
    """Crash-safe single-file sink for a complete typed candidate envelope."""

    def __init__(self, destination: Path) -> None:
        if not destination.is_absolute():
            raise ValueError("complete candidate envelope path must be absolute")
        self._destination = destination

    def validate_fresh(
        self,
        *,
        required_destination: Path,
        protected_paths: tuple[Path, ...],
    ) -> None:
        destination = _normalized_absolute_path(self._destination)
        if destination != _normalized_absolute_path(required_destination):
            raise ValueError(
                "complete candidate envelope must use the fixed candidate evidence path"
            )
        _require_no_symlink_ancestors(destination.parent)
        if not destination.parent.is_dir():
            raise ValueError("complete candidate envelope parent must already exist")
        if destination.exists() or destination.is_symlink():
            raise ValueError(
                "complete candidate envelope destination must have fresh ownership"
            )
        if any(_paths_overlap(destination, path) for path in protected_paths):
            raise ValueError(
                "complete candidate envelope overlaps an immutable input or target"
            )

    def write_and_readback(
        self, envelope: CompleteCandidateBuildEnvelope
    ) -> CompleteCandidateBuildEnvelope:
        destination = self._destination
        parent = destination.parent
        _require_no_symlink_ancestors(parent)
        if not parent.is_dir():
            raise ValueError("complete candidate envelope destination is unsafe")
        if destination.exists() or destination.is_symlink():
            raise ValueError(
                "complete candidate envelope destination must have fresh ownership"
            )
        temporary = parent / f".{destination.name}.{secrets.token_hex(12)}.tmp"
        published_identity: tuple[int, int] | None = None
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            payload = envelope.model_dump_json(indent=2).encode("utf-8") + b"\n"
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
            os.close(fd)
            fd = -1
            temporary_stat = temporary.lstat()
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise ValueError(
                    "complete candidate envelope destination requires fresh ownership"
                ) from exc
            published_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
            temporary.unlink()
            dir_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            read_fd = os.open(destination, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                chunks: list[bytes] = []
                while chunk := os.read(read_fd, 1024 * 1024):
                    chunks.append(chunk)
            finally:
                os.close(read_fd)
            return CompleteCandidateBuildEnvelope.model_validate_json(
                b"".join(chunks),
                context={"external_content_addressed": True},
            )
        except Exception:
            if published_identity is not None:
                try:
                    destination_stat = destination.lstat()
                    if (destination_stat.st_dev, destination_stat.st_ino) == (
                        published_identity
                    ):
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise
        finally:
            if fd >= 0:
                os.close(fd)
            temporary.unlink(missing_ok=True)


class _IsolatedKnowledgeBuild(KnowledgeBuild):
    def __init__(
        self,
        *,
        target_config: CompleteCandidateTargetConfig,
        accepted_backup_gate_root: Path,
        source_manifest_path: Path,
        accepted_original_milvus_sha256: str,
        accepted_original_milvus_record_sha256: str,
        decision_adapter: _DecisionAdapter,
        embedding_adapter: _EmbeddingAdapter,
        boundary: _Boundary,
        envelope_sink: _EnvelopeSink,
        clock: Callable[[], datetime],
    ) -> None:
        self._targets = target_config
        self._gate_root = accepted_backup_gate_root
        self._source_manifest_path = source_manifest_path
        self._accepted_original_milvus_sha256 = accepted_original_milvus_sha256
        self._accepted_original_milvus_record_sha256 = (
            accepted_original_milvus_record_sha256
        )
        self._decision_adapter = decision_adapter
        self._embedding_adapter = embedding_adapter
        self._boundary = boundary
        self._envelope_sink = envelope_sink
        self._clock = clock
        self._used = False

    def _load_manifest(self) -> SourceBuildManifest:
        try:
            raw = _read_stable_unlinked_regular_file(self._source_manifest_path)
            manifest = SourceBuildManifest.model_validate_json(
                raw,
                context={"external_content_addressed": True},
            )
        except (OSError, UnicodeError, ValidationError, ValueError) as exc:
            raise SourceBuildManifestError(
                "source-build manifest failed exact accepted-authority validation"
            ) from exc
        if manifest.schema_version != "canonical-v2-source-build-manifest-v2":
            # A v1 manifest validates as a legal accepted-gate build without
            # the supplemental source authority, so a caller could downgrade
            # the manifest and silently drop every supplemental source
            # (professor backfill included).  The build entry accepts only v2.
            raise SourceBuildManifestError(
                "source-build manifest must be canonical-v2 "
                "(canonical-v2-source-build-manifest-v2); v1 manifests are "
                "not accepted"
            )
        return manifest

    def _preflight(
        self, request: BuildCandidateRequest
    ) -> tuple[SourceBuildManifest, Any]:
        if self._used:
            raise IsolatedKnowledgeBuildSafetyError(
                "one isolated builder and physical target set is single-use"
            )
        manifest = self._load_manifest()
        try:
            self._boundary.verify_accepted_control_files_safe(gate_root=self._gate_root)
            immutable = self._boundary.resolve_accepted_immutable_paths(
                gate_root=self._gate_root,
                expected_sha256=self._accepted_original_milvus_sha256,
            )
            accepted_original_milvus_path = (
                self._boundary.resolve_accepted_original_milvus_path(
                    gate_root=self._gate_root,
                    expected_sha256=self._accepted_original_milvus_sha256,
                )
            )
        except Exception as exc:
            raise IsolatedKnowledgeBuildSafetyError(
                "accepted original Milvus path identity cannot be derived"
            ) from exc
        marker = self._targets.staging.marker
        expected_database = "miroflow_" + request.candidate_release_id.replace("-", "_")
        if (
            marker.run_id != request.run_id
            or marker.candidate_release_id != request.candidate_release_id
            or marker.source_manifest_sha256 != manifest.content_sha256
            or self._targets.index.release_id != request.candidate_release_id
            or self._targets.database.target_kind != "disposable"
            or self._targets.database.expected_database != expected_database
            or self._targets.index.forbidden_milvus_paths
            != (accepted_original_milvus_path,)
            or immutable.original_milvus_path != accepted_original_milvus_path
            or immutable.restore_root != manifest.restore_root
        ):
            raise IsolatedKnowledgeBuildSafetyError(
                "request and explicit isolated target identities differ"
            )
        index_root = self._targets.index.root
        staging_root = self._targets.staging.root
        try:
            _require_no_symlink_ancestors(index_root)
            _require_no_symlink_ancestors(staging_root)
        except ValueError as exc:
            raise IsolatedKnowledgeBuildSafetyError(
                "index or staging target ancestry is unsafe"
            ) from exc
        immutable_paths = [
            self._gate_root,
            self._source_manifest_path,
            immutable.backup_root,
            immutable.restore_root,
            immutable.evidence_root,
            manifest.restore_root,
            *self._targets.index.forbidden_milvus_paths,
            *(
                (manifest.approved_recollection_root,)
                if manifest.approved_recollection_root is not None
                else ()
            ),
            *(
                member.content_path
                for entry in (
                    *manifest.inventory_entries,
                    *manifest.targeted_recollection_entries,
                )
                for member in entry.members
            ),
        ]
        protected_paths = [index_root, *immutable_paths]
        # The envelope is itself run evidence beneath evidence_root. Protect the
        # accepted immutable descendants and concrete inputs, not that broad parent.
        envelope_protected_paths = (
            self._gate_root / "s2",
            self._gate_root / "s2b",
            self._source_manifest_path,
            immutable.backup_root,
            manifest.restore_root,
            index_root,
            staging_root,
            *self._targets.index.forbidden_milvus_paths,
            *(
                (manifest.approved_recollection_root,)
                if manifest.approved_recollection_root is not None
                else ()
            ),
            *(
                member.content_path
                for entry in (
                    *manifest.inventory_entries,
                    *manifest.targeted_recollection_entries,
                )
                for member in entry.members
            ),
        )
        try:
            if request.candidate_release_id.startswith("candidate-s12c-"):
                evidence_slice = "s12c"
            elif request.candidate_release_id.startswith("candidate-s12b-"):
                evidence_slice = "s12b"
            else:
                evidence_slice = "s12a"
            self._envelope_sink.validate_fresh(
                required_destination=(
                    self._gate_root
                    / evidence_slice
                    / "complete-candidate-build-envelope.json"
                ),
                protected_paths=envelope_protected_paths,
            )
        except Exception as exc:
            raise IsolatedKnowledgeBuildSafetyError(
                "complete candidate envelope target failed preflight"
            ) from exc
        if (
            not staging_root.is_absolute()
            or index_root == staging_root
            or any(_paths_overlap(staging_root, path) for path in protected_paths)
            or any(_paths_overlap(index_root, path) for path in immutable_paths)
            or not _prepared_index_root_is_fresh(self._targets.index)
            or staging_root.exists()
        ):
            raise IsolatedKnowledgeBuildSafetyError(
                "index and staging roots must be distinct fresh non-symlink targets"
            )
        evidence_entries = tuple(
            item
            for item in (
                *manifest.inventory_entries,
                *manifest.targeted_recollection_entries,
            )
            if item.disposition is SourceDisposition.evidence_input
        )
        manifest_batches = tuple(
            sorted(
                member.source_batch_id
                for item in evidence_entries
                for member in item.members
            )
        )
        if manifest_batches != request.source_batch_ids:
            raise SourceBuildManifestError(
                "request source batches differ from the source-build manifest"
            )
        admitted_parser_versions: dict[str, str] = {}
        for entry in evidence_entries:
            for member in entry.members:
                parser_name = member.parser.parser_name
                parser_version = member.parser.parser_version
                prior = admitted_parser_versions.setdefault(parser_name, parser_version)
                if prior != parser_version:
                    raise SourceBuildManifestError(
                        "admitted members require conflicting parser versions"
                    )
        admitted_policy_versions = {
            "path_eligibility": "path-eligibility-v1",
            "released_objects_mapper": "canonical-v2-released-objects-mapper-v2",
        }
        admitted_model_versions = {"embedding": self._embedding_adapter.model_id}
        if (
            dict(request.parser_versions) != admitted_parser_versions
            or dict(request.policy_versions) != admitted_policy_versions
            or dict(request.model_versions) != admitted_model_versions
        ):
            raise SourceBuildManifestError(
                "request versions differ from the exact admitted build authority"
            )
        try:
            self._boundary.validate_fresh_targets(target_config=self._targets)
            gate = self._boundary.verify_accepted_gate(gate_root=self._gate_root)
        except Exception as exc:
            raise IsolatedKnowledgeBuildSafetyError(
                "isolated target or accepted backup gate validation failed"
            ) from exc
        gate_values = (
            getattr(gate, "source_inventory_sha256", None),
            getattr(gate, "backup_manifest_sha256", None),
            getattr(gate, "restore_verification_sha256", None),
            getattr(gate, "acceptance_record_sha256", None),
        )
        manifest_values = (
            manifest.source_inventory_sha256,
            manifest.backup_manifest_sha256,
            manifest.restore_verification_sha256,
            manifest.acceptance_record_sha256,
        )
        if gate_values != manifest_values:
            raise SourceBuildManifestError(
                "live accepted gate differs from the bound source manifest"
            )
        try:
            self._boundary.prepare_fresh_targets(target_config=self._targets)
        except Exception as exc:
            raise IsolatedKnowledgeBuildSafetyError(
                "isolated targets failed collision-safe preparation"
            ) from exc
        self._used = True
        return manifest, gate

    def _stage_and_land(
        self,
        *,
        request: BuildCandidateRequest,
        manifest: SourceBuildManifest,
        now: datetime,
    ) -> tuple[
        tuple[_ParsedReleasedObject, ...],
        tuple[_RecordedGap, ...],
        tuple[str, ...],
    ]:
        parsed_rows: list[_ParsedReleasedObject] = []
        gaps: list[_RecordedGap] = []
        landing_hashes: list[str] = []
        entries = (
            *manifest.inventory_entries,
            *manifest.targeted_recollection_entries,
        )
        for entry in entries:
            if entry.disposition is not SourceDisposition.evidence_input:
                continue
            for member in entry.members:
                destination = self._targets.staging.root / (
                    hashlib.sha256(member.member_id.encode("utf-8")).hexdigest()
                    + ".source"
                )
                try:
                    staged = self._boundary.stage_verified_member(
                        entry=entry,
                        member=member,
                        destination=destination,
                    )
                    landing = self._boundary.land_released_objects(
                        entry=entry,
                        member=member,
                        staged_member=staged,
                        run_id=f"landing:{request.run_id}:{member.member_id}",
                        observed_at=now,
                    )
                except Exception as exc:
                    raise IsolatedKnowledgeBuildError(
                        f"verified source staging/landing failed for {entry.source_id}"
                    ) from exc
                retained = landing.records
                if landing.receipt.source_batch_id != member.source_batch_id or (
                    landing.receipt.record_count != len(retained)
                ):
                    raise IsolatedKnowledgeBuildError(
                        "landing receipt/readback differs"
                    )
                landing_hashes.append(
                    _canonical_sha256(
                        cast(JsonValue, landing.receipt.model_dump(mode="json"))
                    )
                )
                if entry.source_id == _RELEASED_OBJECTS_SOURCE_ID:
                    counts = Counter(
                        cast(str, item.payload.get("object_type")) for item in retained
                    )
                    if len(retained) != 5561 or counts != _EXPECTED_OBJECT_COUNTS:
                        raise IsolatedKnowledgeBuildError(
                            "full released_objects row/type counts differ from accepted authority"
                        )
                for record in retained:
                    domain = str(record.payload.get("object_type") or "cross_domain")
                    if record.parse_status is not ParseStatus.parsed:
                        if entry.source_id in _SUPPLEMENTAL_SOURCE_IDS:
                            raise IsolatedKnowledgeBuildError(
                                "fixed supplemental source did not parse completely"
                            )
                        parse_error_paths = tuple(
                            sorted(
                                {
                                    error.field_path or "parse_status"
                                    for error in record.errors
                                }
                            )
                        ) or ("parse_status",)
                        gaps.append(
                            _gap(
                                release_id=request.candidate_release_id,
                                run_id=request.run_id,
                                record=record,
                                domain=domain,
                                reason=(
                                    f"released_objects row {record.payload.get('id')!r} "
                                    "is quarantined because payload_json is malformed"
                                ),
                                affected_paths=parse_error_paths,
                                now=now,
                            )
                        )
                        continue
                    if entry.source_id == _RELEASED_OBJECTS_SOURCE_ID:
                        raw_json = record.payload.get("payload_json")
                        try:
                            payload = _load_unique_json_object(cast(str, raw_json))
                        except (TypeError, ValueError, RecursionError) as exc:
                            raise IsolatedKnowledgeBuildError(
                                "parsed landing record cannot replay payload_json"
                            ) from exc
                    else:
                        payload = dict(record.payload)
                    parsed_rows.append(
                        _ParsedReleasedObject(
                            source_id=entry.source_id,
                            source_batch_id=member.source_batch_id,
                            record=record,
                            artifact=landing.artifact,
                            payload=cast(dict[str, Any], payload),
                        )
                    )
        return (
            tuple(parsed_rows),
            tuple(sorted(gaps, key=lambda item: item.result.gap_id)),
            tuple(sorted(landing_hashes)),
        )

    def _logical_graph(
        self,
        *,
        request: BuildCandidateRequest,
        rows: tuple[_ParsedReleasedObject, ...],
        initial_gaps: tuple[_RecordedGap, ...],
        now: datetime,
    ) -> _MappedAuthority:
        (
            identity_request,
            identity_result,
            decision_result,
            domain_request,
            domain_result,
            links,
            gaps,
        ) = _map_public_authority(
            request=request,
            rows=rows,
            initial_gaps=initial_gaps,
            decision_adapter=self._decision_adapter,
            now=now,
        )
        (
            internal_request,
            internal_result,
            candidate_request,
            candidate_result,
        ) = _internal_candidate_authority(
            request=request,
            domain_request=domain_request,
            domain_result=domain_result,
            now=now,
        )
        relationship_request, relationship_result = _relationship_authority(
            request=request,
            identity_result=identity_result,
            decision_result=decision_result,
            domain_result=domain_result,
            internal_request=internal_request,
            internal_result=internal_result,
            links=links,
            now=now,
            source_rows=rows,
        )
        (
            eligibility_requests,
            eligibility_results,
            index_request,
            pure_index_result,
        ) = _index_authority(
            request=request,
            candidate_request=candidate_request,
            candidate_result=candidate_result,
            now=now,
        )
        return _MappedAuthority(
            identity_request=identity_request,
            identity_result=identity_result,
            decision_result=decision_result,
            domain_request=domain_request,
            domain_result=domain_result,
            internal_request=internal_request,
            internal_result=internal_result,
            candidate_request=candidate_request,
            candidate_result=candidate_result,
            relationship_request=relationship_request,
            relationship_result=relationship_result,
            eligibility_requests=eligibility_requests,
            eligibility_results=eligibility_results,
            index_request=index_request,
            pure_index_result=pure_index_result,
            gaps=gaps,
        )

    def _retain_candidate(
        self,
        *,
        request: BuildCandidateRequest,
        graph: _MappedAuthority,
        now: datetime,
    ) -> tuple[
        CandidateRelease,
        BuildManifest,
        tuple[ManifestSection, ...],
        tuple[PolicyReference, ...],
        _CandidateRegistrySnapshot,
    ]:
        decision_set, object_sets, relationship_set, eligibility_sets = (
            _manifest_sections(
                request=request,
                decision=graph.decision_result,
                candidate_result=graph.candidate_result,
                internal_result=graph.internal_result,
                relationship_result=graph.relationship_result,
                eligibility_results=graph.eligibility_results,
            )
        )
        candidate_store: dict[str, CandidateRelease] = {}
        manifest_store: dict[str, BuildManifest] = {}
        failure_store: dict[str, Any] = {}

        def materialize(_: BuildCandidateRequest) -> object:
            return {
                "decision_set": decision_set,
                "object_sets": object_sets,
                "relationship_set": relationship_set,
                "eligibility_sets": eligibility_sets,
                "published_projections": graph.candidate_result.published_projections,
                "expected_index_projections": (
                    graph.pure_index_result.expected_index_projections
                ),
            }

        logical_builder = create_ephemeral_knowledge_build(
            materialize=materialize,
            candidate_store=candidate_store,
            manifest_store=manifest_store,
            failure_store=failure_store,
            active_release_state={},
            clock=lambda: now,
        )
        try:
            candidate = logical_builder.build(request)
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                "immutable candidate manifest construction failed"
            ) from exc
        manifest = manifest_store[request.candidate_release_id]
        sections = (decision_set, *object_sets, relationship_set, *eligibility_sets)
        policy_by_id = {
            (policy.policy_id, policy.policy_version): policy
            for policy in (
                graph.identity_request.policy,
                *(
                    decision.policy
                    for decision in (
                        *graph.decision_result.canonical_decisions,
                        *graph.decision_result.relationship_decisions,
                    )
                ),
            )
        }
        policies = tuple(
            sorted(
                policy_by_id.values(),
                key=lambda item: (item.policy_id, item.policy_version),
            )
        )
        expected_registry = _candidate_registry_snapshot(
            candidate=candidate,
            manifest=manifest,
            sections=sections,
            policies=policies,
        )
        try:
            readback = self._boundary.persist_candidate_registry_and_identity_policy(
                candidate=candidate,
                manifest=manifest,
                sections=sections,
                policies=policies,
                relationship_types=graph.relationship_result.relationship_types,
            )
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                "candidate registry insert/readback failed"
            ) from exc
        if readback != expected_registry:
            raise IsolatedKnowledgeBuildError(
                "candidate registry readback differs from immutable candidate"
            )
        return candidate, manifest, sections, policies, readback

    def _persist_owners(self, graph: _MappedAuthority) -> None:
        operations: tuple[tuple[str, Callable[[], Any], Any], ...] = (
            (
                "identity",
                lambda: self._boundary.persist_identity_resolution(
                    request=graph.identity_request,
                    result=graph.identity_result,
                ),
                graph.identity_result,
            ),
            (
                "decision",
                lambda: self._boundary.persist_decision_batch(
                    result=graph.decision_result
                ),
                graph.decision_result,
            ),
            (
                "domain",
                lambda: self._boundary.persist_domain_projection(
                    result=graph.domain_result
                ),
                graph.domain_result,
            ),
            (
                "relationship",
                lambda: self._boundary.persist_relationship_projection(
                    request=graph.relationship_request,
                    result=graph.relationship_result,
                ),
                graph.relationship_result,
            ),
        )
        for store_name, persist, expected in operations:
            for _ in range(2):
                try:
                    readback = persist()
                except Exception as exc:
                    raise IsolatedKnowledgeBuildError(
                        f"typed store conflict while persisting {store_name}: {exc}"
                    ) from exc
                if readback != expected:
                    raise IsolatedKnowledgeBuildError(
                        f"typed store conflict on {store_name} exact replay"
                    )
        for gap in graph.gaps:
            try:
                readback = self._boundary.persist_gap(
                    signal=gap.signal,
                    expected=gap.result,
                )
            except Exception as exc:
                raise IsolatedKnowledgeBuildError(
                    f"typed gap persistence conflict: {exc}"
                ) from exc
            if readback != gap.result:
                raise IsolatedKnowledgeBuildError(
                    "typed gap readback differs from retained evidence"
                )

    def _materialize_verify_and_emit(
        self,
        *,
        request: BuildCandidateRequest,
        manifest: SourceBuildManifest,
        gate: Any,
        landing_hashes: tuple[str, ...],
        graph: _MappedAuthority,
        candidate: CandidateRelease,
        build_manifest: BuildManifest,
        registry_policies: tuple[PolicyReference, ...],
        registry_snapshot: _CandidateRegistrySnapshot,
        active_before: Mapping[str, str] | None,
        now: datetime,
    ) -> CandidateRelease:
        try:
            physical_builder = IndexProjectionBuilder(
                materializer=_BoundaryIndexMaterializer(self._boundary)
            )
            index_result = physical_builder.build(graph.index_request)
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                f"physical index materialization/parity failed: {exc}"
            ) from exc
        try:
            audit = self._boundary.audit_index(target=self._targets.index)
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                f"physical index audit failed: {exc}"
            ) from exc
        if (
            tuple(getattr(audit, "points", ())) != index_result.points
            or tuple(getattr(audit, "lookup_documents", ()))
            != index_result.lookup_documents
            or tuple(getattr(audit, "index_projections", ()))
            != index_result.actual_index_projections
            or tuple(getattr(audit, "lookup_projections", ()))
            != index_result.actual_lookup_projections
        ):
            raise IsolatedKnowledgeBuildError(
                "independent physical index inventory differs from the candidate"
            )
        physical_sha256 = getattr(audit, "content_sha256", None)
        if not isinstance(physical_sha256, str) or len(physical_sha256) != 64:
            raise IsolatedKnowledgeBuildError(
                "physical index audit did not return a content identity"
            )

        verification_store: dict[str, ReleaseVerification] = {}
        synthetic_absent_active = {
            "canonical_release_id": "s12a-absent-active",
            "published_projection_release_id": "s12a-absent-active",
            "index_release_id": "s12a-absent-active",
        }
        publication = create_ephemeral_release_publication(
            candidate_manifests={candidate.release_id: build_manifest},
            actual_index_projections={
                candidate.release_id: tuple(getattr(audit, "index_projections"))
            },
            expected_index_points={candidate.release_id: index_result.points},
            actual_index_points={candidate.release_id: tuple(getattr(audit, "points"))},
            active_release_state=synthetic_absent_active,
            verification_store=verification_store,
            discrepancy_store={},
            publication_history=[],
            clock=lambda: now,
        )
        verification = publication.verify(candidate.release_id)
        if (
            not verification.accepted
            or not verification.canonical_index_parity
            or any(
                (
                    verification.missing_points,
                    verification.extra_points,
                    verification.stale_points,
                    verification.cross_release_points,
                )
            )
        ):
            raise IsolatedKnowledgeBuildError(
                "Accepted ReleasePublication verification rejected physical parity"
            )
        active_after_raw = self._boundary.read_active_release()
        active_after = None if active_after_raw is None else dict(active_after_raw)
        frozen_before = None if active_before is None else dict(active_before)
        if active_after != frozen_before:
            raise IsolatedKnowledgeBuildError(
                "candidate construction changed the active release pointer"
            )
        try:
            final_registry = self._boundary.read_candidate_registry(
                release_id=candidate.release_id,
                policies=registry_policies,
            )
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                f"candidate registry final durable readback failed: {exc}"
            ) from exc
        if final_registry != registry_snapshot:
            raise IsolatedKnowledgeBuildError(
                "candidate registry final durable readback differs from initial retention"
            )

        bundle_relationship_request, bundle_relationship_result = (
            _release_bundle_relationship_authority(
                graph.relationship_request,
                graph.relationship_result,
            )
        )
        release_bundle = IsolatedReleaseBundle(
            manifest=build_manifest,
            index_result=index_result,
            index_target=self._targets.index,
            relationship_projection_request=bundle_relationship_request,
            relationship_projection_result=bundle_relationship_result,
        )
        institution_catalog = InstitutionCatalog(
            catalog_id=f"institution-catalog:{candidate.release_id}",
            catalog_version="canonical-v2-s12a-retained-v1",
            release_id=candidate.release_id,
            entries=(),
        )
        handoff = CompleteCandidateConsumerHandoff(
            schema_version="canonical-v2-complete-candidate-handoff-v1",
            candidate=candidate,
            release_bundle=release_bundle,
            index_projection_request=graph.index_request,
            institution_catalog=institution_catalog,
            release_verification=verification,
        )
        authority_sha256 = _canonical_sha256(
            cast(
                JsonValue,
                {
                    "identity": graph.identity_result.content_sha256,
                    "decision": graph.decision_result.content_sha256,
                    "domain": graph.domain_result.content_sha256,
                    "internal_reference": graph.internal_result.content_sha256,
                    "relationship": graph.relationship_result.content_sha256,
                },
            )
        )
        gap_hashes = tuple(
            sorted(
                _canonical_sha256(cast(JsonValue, gap.result.model_dump(mode="json")))
                for gap in graph.gaps
            )
        )
        receipt = CompleteCandidateBuildReceipt(
            schema_version="canonical-v2-complete-candidate-receipt-v1",
            candidate=candidate,
            consumer_handoff_sha256=handoff.content_sha256,
            source_manifest_sha256=manifest.content_sha256,
            gate_hashes={
                "acceptance_record": manifest.acceptance_record_sha256,
                "backup_manifest": manifest.backup_manifest_sha256,
                "restore_verification": manifest.restore_verification_sha256,
                "source_inventory": manifest.source_inventory_sha256,
            },
            landing_receipt_hashes=landing_hashes,
            gap_hashes=gap_hashes,
            authority_sha256=authority_sha256,
            candidate_projection_sha256=graph.candidate_result.content_sha256,
            relationship_projection_sha256=(graph.relationship_result.content_sha256),
            database_registry_sha256=registry_snapshot.content_sha256,
            index_result_sha256=index_result.content_sha256,
            physical_index_snapshot_sha256=physical_sha256,
            release_verification=verification,
            active_release_before_sha256=_canonical_sha256(
                cast(JsonValue, frozen_before)
            ),
            active_release_after_sha256=_canonical_sha256(
                cast(JsonValue, active_after)
            ),
            accepted_original_milvus_record_sha256=(
                self._accepted_original_milvus_record_sha256
            ),
            accepted_original_milvus_sha256=self._accepted_original_milvus_sha256,
            recorded_decision_bundle_sha256=(self._decision_adapter.authority_sha256),
            recorded_embedding_bundle_sha256=(self._embedding_adapter.authority_sha256),
            recorded_embedding_dimension=self._embedding_adapter.dimension,
            built_at=now,
        )
        envelope = CompleteCandidateBuildEnvelope(
            schema_version="canonical-v2-complete-candidate-envelope-v1",
            receipt=receipt,
            consumer_handoff=handoff,
        )
        try:
            readback = self._envelope_sink.write_and_readback(envelope)
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                f"single-envelope atomic write/readback failed: {exc}"
            ) from exc
        if readback != envelope or readback.consumer_handoff.candidate != candidate:
            raise IsolatedKnowledgeBuildError(
                "single-envelope readback differs from the verified candidate"
            )
        return readback.consumer_handoff.candidate

    def build(self, request: BuildCandidateRequest) -> CandidateRelease:
        manifest, gate = self._preflight(request)
        now = self._clock()
        active_raw = self._boundary.read_active_release()
        active_before = None if active_raw is None else dict(active_raw)
        if active_before is not None:
            raise IsolatedKnowledgeBuildSafetyError(
                "isolated candidate database acquired an active release before staging"
            )
        rows, initial_gaps, landing_hashes = self._stage_and_land(
            request=request,
            manifest=manifest,
            now=now,
        )
        try:
            graph = self._logical_graph(
                request=request,
                rows=rows,
                initial_gaps=initial_gaps,
                now=now,
            )
        except IsolatedKnowledgeBuildError:
            raise
        except Exception as exc:
            raise IsolatedKnowledgeBuildError(
                f"accepted owner composition failed: {exc}"
            ) from exc
        (
            candidate,
            build_manifest,
            _,
            registry_policies,
            registry_snapshot,
        ) = self._retain_candidate(
            request=request,
            graph=graph,
            now=now,
        )
        self._persist_owners(graph)
        return self._materialize_verify_and_emit(
            request=request,
            manifest=manifest,
            gate=gate,
            landing_hashes=landing_hashes,
            graph=graph,
            candidate=candidate,
            build_manifest=build_manifest,
            registry_policies=registry_policies,
            registry_snapshot=registry_snapshot,
            active_before=active_before,
            now=now,
        )


def create_isolated_knowledge_build(
    *,
    target_config: CompleteCandidateTargetConfig,
    accepted_backup_gate_root: Path,
    source_manifest_path: Path,
    accepted_original_milvus_sha256: str,
    accepted_original_milvus_record_sha256: str,
    decision_adapter: _DecisionAdapter,
    embedding_adapter: _EmbeddingAdapter,
    boundary: _Boundary | None = None,
    envelope_sink: _EnvelopeSink,
    clock: Callable[[], datetime],
) -> KnowledgeBuild:
    """Compose the single-use complete isolated candidate builder."""

    resolved_target_config = target_config.model_copy(
        update={
            "database": _resolve_explicit_database_target(target_config.database),
        }
    )

    if (
        accepted_original_milvus_sha256 != _ACCEPTED_ORIGINAL_MILVUS_SHA256
        or accepted_original_milvus_record_sha256
        != _ACCEPTED_ORIGINAL_MILVUS_RECORD_SHA256
        or decision_adapter.authority_sha256 != _RECORDED_DECISION_BUNDLE_SHA256
        or (embedding_adapter.authority_sha256, embedding_adapter.dimension)
        not in _ACCEPTED_EMBEDDING_AUTHORITIES
    ):
        raise IsolatedKnowledgeBuildSafetyError(
            "Accepted original-Milvus or content-addressed offline authority is invalid"
        )
    selected_boundary = boundary or _RealBoundary(
        targets=resolved_target_config,
        backup_gate_root=accepted_backup_gate_root,
        embedding_adapter=embedding_adapter,
        clock=clock,
    )

    return _IsolatedKnowledgeBuild(
        target_config=resolved_target_config,
        accepted_backup_gate_root=accepted_backup_gate_root,
        source_manifest_path=source_manifest_path,
        accepted_original_milvus_sha256=accepted_original_milvus_sha256,
        accepted_original_milvus_record_sha256=(accepted_original_milvus_record_sha256),
        decision_adapter=decision_adapter,
        embedding_adapter=embedding_adapter,
        boundary=selected_boundary,
        envelope_sink=envelope_sink,
        clock=clock,
    )


__all__ = [
    "BuildCandidateRequest",
    "CandidateRelease",
    "CandidateStagingMarker",
    "CandidateStagingTarget",
    "CompleteCandidateBuildEnvelope",
    "CompleteCandidateBuildReceipt",
    "CompleteCandidateConsumerHandoff",
    "CompleteCandidateTargetConfig",
    "DestructiveDatabaseTarget",
    "FileCompleteCandidateEnvelopeSink",
    "IndexProjectionActualState",
    "IsolatedIndexTarget",
    "IsolatedKnowledgeBuildError",
    "IsolatedKnowledgeBuildSafetyError",
    "KnowledgeBuild",
    "SourceBuildEntry",
    "SourceBuildManifest",
    "SourceBuildManifestError",
    "SourceBuildMember",
    "SourceDisposition",
    "create_isolated_knowledge_build",
    "load_recorded_decision_adapter",
    "load_content_addressed_embedding_adapter",
    "load_recorded_embedding_adapter",
    "load_recorded_serving_inputs",
]
