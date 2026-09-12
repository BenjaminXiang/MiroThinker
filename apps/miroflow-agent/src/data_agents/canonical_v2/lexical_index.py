"""Derived lexical index for the canonical-v2 serving read path.

retrieval-v2 Step 1 (OpenSpec: `retrieval-v2-derived-index-and-fusion`):
the release's lookup documents are segmented once (jieba `cut_for_search`
with a domain dictionary built from the entity name forms) into a persisted
SQLite FTS5 artifact written OUTSIDE the sealed pack, and the lexical lane
queries that index with field-tiered BM25 instead of scanning every document
with substring matching.

Artifact layout:

    <out_dir>/lexical.sqlite3   FTS5 columns name/tags/body + doc_map + segment_dict
    <out_dir>/manifest.json     schema, release id, pack stat + sha256, dictionary
                                sha256, document count, build time

Fail-closed: `LexicalIndex.open` refuses an artifact whose release id, schema
version or pack fingerprint differs from the caller's expectation; a missing
artifact returns None so the caller keeps the previous lane unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

LEXICAL_INDEX_SCHEMA_VERSION = "canonical-v2-lexical-index-v1"
INDEX_FILENAME = "lexical.sqlite3"
MANIFEST_FILENAME = "manifest.json"
# Field-tiered BM25: display names above tags above body text (design.md
# "Field contract"). FTS5 bm25() returns negative scores; lower is better.
COLUMN_WEIGHTS = (8.0, 4.0, 1.0)

# Field contract (design.md §Field contract): only these keys feed the index.
# Hash/decision/lineage fields are never read, so they can never tokenize in.
_NAME_KEYS = ("name", "normalized_name", "title", "canonical_name_zh")
_TAG_KEYS = ("industry", "venue")
_LIST_TAG_KEYS = (
    "aliases",
    "industry_tags",
    "tech_tags",
    "products",
    "applicants",
    "inventors",
    "authors",
)
_BODY_KEYS = (
    "profile_summary",
    "product_description",
    "technology_route_summary",
    "summary_text",
    "team_description",
)


class LexicalIndexIntegrityError(ValueError):
    """Artifact missing/mismatched where the caller required a bound index."""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _names(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                out.append(item.strip())
            elif isinstance(item, dict):
                out.append(_text(item.get("name")))
    elif isinstance(value, dict):
        out.append(_text(value.get("name")))
    elif isinstance(value, str):
        out.append(value.strip())
    return [item for item in out if item]


def document_columns(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the (name, tags, body) column texts for one lookup payload."""
    name_parts = [_text(payload.get(key)) for key in _NAME_KEYS]
    tag_parts: list[str] = []
    for key in _LIST_TAG_KEYS:
        tag_parts.extend(_names(payload.get(key)))
    for key in _TAG_KEYS:
        tag_parts.extend(_names(payload.get(key)))
    body_parts: list[str] = []
    for key in _BODY_KEYS:
        body_parts.append(_text(payload.get(key)))
    supplementary = payload.get("_supplementary")
    if isinstance(supplementary, dict):
        for value in supplementary.values():
            if isinstance(value, str):
                body_parts.append(value.strip())
            elif isinstance(value, list):
                body_parts.extend(
                    item.strip() for item in value if isinstance(item, str)
                )
    return (
        " ".join(part for part in name_parts if part),
        " ".join(part for part in tag_parts if part),
        " ".join(part for part in body_parts if part),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_fingerprint(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns, stat.st_ino)


class Segmenter:
    """Deterministic jieba `cut_for_search` segmentation with a domain dict.

    An isolated `jieba.Tokenizer` instance is used so loading the domain
    dictionary never mutates the process-wide jieba state (tests and the
    serving process can hold different dictionaries side by side).
    """

    def __init__(self, words: Iterable[str] = ()) -> None:
        import jieba  # local import: only build/query paths pay it

        tokenizer = jieba.Tokenizer()
        tokenizer.initialize()
        added = 0
        for word in dict.fromkeys(words):
            candidate = word.strip()
            if len(candidate) < 2:
                continue
            tokenizer.add_word(candidate)
            added += 1
        self._tokenizer = tokenizer
        self.word_count = added

    def tokens(self, text: str) -> tuple[str, ...]:
        return tuple(
            token for token in self._tokenizer.cut_for_search(text) if token.strip()
        )

    def __call__(self, text: str) -> str:
        return " ".join(self.tokens(text))

    def match_expression(self, text: str) -> str:
        """FTS5 OR expression: tokens OR-joined, each as a quoted phrase."""
        tokens = tuple(dict.fromkeys(self.tokens(text)))
        if not tokens:
            return ""
        quoted = ('"' + token.replace('"', '""') + '"' for token in tokens)
        return " OR ".join(quoted)

    def phrase_expression(self, text: str) -> str:
        """FTS5 phrase expression: quoted tokens joined by a space.

        FTS5's own tokenizer treats a raw quoted CJK run as ONE token, so a
        phrase must be built from the already-segmented tokens ("储能" "电池"
        means the two tokens adjacent) — the build/query symmetry rule,
        measured 2026-09-12: 储能电池 0 → 114 hits once built this way.
        """
        tokens = tuple(self.tokens(text))
        if not tokens:
            return ""
        return " ".join('"' + token.replace('"', '""') + '"' for token in tokens)


@dataclass(frozen=True)
class LexicalIndexManifest:
    schema_version: str
    release_id: str
    pack_lookup_sha256: str
    pack_lookup_size: int
    pack_lookup_mtime_ns: int
    dictionary_sha256: str
    document_count: int
    built_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "release_id": self.release_id,
                "pack_lookup_sha256": self.pack_lookup_sha256,
                "pack_lookup_size": self.pack_lookup_size,
                "pack_lookup_mtime_ns": self.pack_lookup_mtime_ns,
                "dictionary_sha256": self.dictionary_sha256,
                "document_count": self.document_count,
                "built_at": self.built_at,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> "LexicalIndexManifest":
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise LexicalIndexIntegrityError(
                "lexical index manifest is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise LexicalIndexIntegrityError("lexical index manifest is not an object")
        try:
            return cls(
                schema_version=str(payload["schema_version"]),
                release_id=str(payload["release_id"]),
                pack_lookup_sha256=str(payload["pack_lookup_sha256"]),
                pack_lookup_size=int(payload["pack_lookup_size"]),
                pack_lookup_mtime_ns=int(payload["pack_lookup_mtime_ns"]),
                dictionary_sha256=str(payload["dictionary_sha256"]),
                document_count=int(payload["document_count"]),
                built_at=str(payload["built_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LexicalIndexIntegrityError(
                "lexical index manifest is missing required fields"
            ) from exc


def _document_payload(document_json: str) -> tuple[str, str, str, str] | None:
    """(document_id, canonical_object_id, domain, lookup_content) or None."""
    try:
        document = json.loads(document_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    document_id = document.get("document_id")
    canonical_id = document.get("canonical_object_id")
    domain = document.get("domain")
    content = document.get("lookup_content")
    if not (
        isinstance(document_id, str)
        and isinstance(canonical_id, str)
        and isinstance(domain, str)
        and isinstance(content, str)
    ):
        return None
    return document_id, canonical_id, domain, content


def build_lexical_index(
    *,
    lookup_sqlite: Path,
    out_dir: Path,
    release_id: str,
    dictionary_words: Iterable[str],
    built_at: str,
    segmenter: Segmenter | None = None,
    force: bool = False,
) -> Path:
    """Build (or reuse) the derived index. Returns the artifact directory."""
    manifest_path = out_dir / MANIFEST_FILENAME
    index_path = out_dir / INDEX_FILENAME
    fingerprint = _stat_fingerprint(lookup_sqlite)
    if not force and manifest_path.is_file() and index_path.is_file():
        existing = LexicalIndexManifest.from_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            existing.schema_version == LEXICAL_INDEX_SCHEMA_VERSION
            and existing.release_id == release_id
            and (existing.pack_lookup_size, existing.pack_lookup_mtime_ns)
            == (fingerprint[0], fingerprint[1])
        ):
            return out_dir

    words = tuple(
        dict.fromkeys(
            word.strip()
            for word in dictionary_words
            if word.strip() and len(word.strip()) >= 2
        )
    )
    dictionary_sha256 = hashlib.sha256(
        "\n".join(sorted(words)).encode("utf-8")
    ).hexdigest()
    active_segmenter = segmenter or Segmenter(words)
    if active_segmenter.word_count != len(words):
        raise LexicalIndexIntegrityError(
            "segmenter dictionary does not match the requested words"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    staging = out_dir / f"{INDEX_FILENAME}.staging"
    staging.unlink(missing_ok=True)
    connection = sqlite3.connect(str(staging))
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE doc_fts USING fts5("
            "name, tags, body, tokenize='unicode61')"
        )
        connection.execute(
            "CREATE TABLE doc_map("
            "rowid INTEGER PRIMARY KEY, document_id TEXT, "
            "canonical_object_id TEXT, domain TEXT)"
        )
        connection.execute("CREATE TABLE segment_dict(word TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO segment_dict(word) VALUES (?)",
            ((word,) for word in sorted(words)),
        )
        source = sqlite3.connect(f"file:{lookup_sqlite}?mode=ro", uri=True)
        try:
            rows = source.execute("SELECT document_json FROM lookup_document")
            document_count = 0
            for (document_json,) in rows:
                parsed = _document_payload(document_json)
                if parsed is None:
                    continue
                document_id, canonical_id, domain, content = parsed
                try:
                    payload = json.loads(content)
                except (TypeError, ValueError):
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                name, tags, body = document_columns(payload)
                cursor = connection.execute(
                    "INSERT INTO doc_fts(name, tags, body) VALUES (?, ?, ?)",
                    (
                        active_segmenter(name)[:20000],
                        active_segmenter(tags)[:20000],
                        active_segmenter(body)[:40000],
                    ),
                )
                connection.execute(
                    "INSERT INTO doc_map(rowid, document_id, canonical_object_id, domain) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        int(cursor.lastrowid),
                        document_id,
                        canonical_id,
                        domain,
                    ),
                )
                document_count += 1
        finally:
            source.close()
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()
    staging.replace(index_path)

    pack_sha256 = sha256_file(lookup_sqlite)
    manifest = LexicalIndexManifest(
        schema_version=LEXICAL_INDEX_SCHEMA_VERSION,
        release_id=release_id,
        pack_lookup_sha256=pack_sha256,
        pack_lookup_size=fingerprint[0],
        pack_lookup_mtime_ns=fingerprint[1],
        dictionary_sha256=dictionary_sha256,
        document_count=document_count,
        built_at=built_at,
    )
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    return out_dir


class LexicalIndex:
    """Read-only handle over one derived lexical artifact."""

    def __init__(
        self,
        *,
        connection: sqlite3.Connection,
        manifest: LexicalIndexManifest,
        segmenter: Segmenter,
    ) -> None:
        self._connection = connection
        self._manifest = manifest
        self._segmenter = segmenter

    @property
    def manifest(self) -> LexicalIndexManifest:
        return self._manifest

    @classmethod
    def open(
        cls,
        artifact_dir: Path,
        *,
        expected_release_id: str,
        lookup_sqlite: Path | None = None,
        expected_pack_lookup_sha256: str | None = None,
    ) -> "LexicalIndex | None":
        manifest_path = artifact_dir / MANIFEST_FILENAME
        index_path = artifact_dir / INDEX_FILENAME
        if not manifest_path.is_file() or not index_path.is_file():
            return None
        manifest = LexicalIndexManifest.from_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if manifest.schema_version != LEXICAL_INDEX_SCHEMA_VERSION:
            raise LexicalIndexIntegrityError("lexical index schema version differs")
        if manifest.release_id != expected_release_id:
            raise LexicalIndexIntegrityError(
                "lexical index release id differs from the active release"
            )
        if lookup_sqlite is not None:
            size, mtime_ns, _inode = _stat_fingerprint(lookup_sqlite)
            if (size, mtime_ns) != (
                manifest.pack_lookup_size,
                manifest.pack_lookup_mtime_ns,
            ):
                raise LexicalIndexIntegrityError(
                    "lexical index is bound to a different lookup pack file"
                )
        if expected_pack_lookup_sha256 is not None:
            if manifest.pack_lookup_sha256 != expected_pack_lookup_sha256:
                raise LexicalIndexIntegrityError(
                    "lexical index pack sha256 differs from the expected release"
                )

        connection = sqlite3.connect(
            f"file:{index_path}?mode=ro", uri=True, check_same_thread=False
        )
        words = tuple(
            row[0] for row in connection.execute("SELECT word FROM segment_dict")
        )
        if words:
            dictionary_sha256 = hashlib.sha256(
                "\n".join(sorted(words)).encode("utf-8")
            ).hexdigest()
            if dictionary_sha256 != manifest.dictionary_sha256:
                connection.close()
                raise LexicalIndexIntegrityError(
                    "lexical index dictionary differs from its manifest"
                )
        return cls(
            connection=connection,
            manifest=manifest,
            segmenter=Segmenter(words),
        )

    def search(
        self,
        query_text: str,
        *,
        domains: Sequence[str] = (),
        limit: int,
        mode: str = "phrase",
    ) -> tuple[tuple[str, float], ...]:
        """Ranked (document_id, bm25_score) pairs; lower score is better.

        mode="phrase" requires the query's segmented tokens to be adjacent
        (the precision pass: 激光设备 must not surface for 激光雷达);
        mode="or" is the recall pass (a ranked sample of any token).
        """
        if limit <= 0:
            return ()
        expression = (
            self._segmenter.phrase_expression(query_text)
            if mode == "phrase"
            else self._segmenter.match_expression(query_text)
        )
        if not expression:
            return ()
        sql = (
            "SELECT m.document_id, bm25(doc_fts, 8.0, 4.0, 1.0) AS score "
            "FROM doc_fts JOIN doc_map m ON m.rowid = doc_fts.rowid "
            "WHERE doc_fts MATCH ?"
        )
        parameters: list[Any] = [expression]
        if domains:
            placeholders = ",".join("?" for _ in domains)
            sql += f" AND m.domain IN ({placeholders})"
            parameters.extend(domains)
        sql += " ORDER BY score, m.document_id LIMIT ?"
        parameters.append(limit)
        return tuple(
            (str(document_id), float(score))
            for document_id, score in self._connection.execute(sql, parameters)
        )


_OPEN_LOCK = threading.Lock()
_OPEN_CACHE: dict[tuple[str, str], LexicalIndex | None] = {}


def open_lexical_index(
    *,
    artifact_root: Path,
    release_id: str,
    lookup_sqlite: Path,
) -> LexicalIndex | None:
    """Process-wide cached open; None when no artifact exists for release.

    Only successful opens are cached: a missing or rejected artifact must not
    pin the process to the fallback lane for its whole lifetime (an operator
    rebuilding the index should not also have to restart the service).
    """
    key = (str(artifact_root), release_id)
    with _OPEN_LOCK:
        if key in _OPEN_CACHE:
            return _OPEN_CACHE[key]
        artifact_dir = artifact_root / release_id
        index = LexicalIndex.open(
            artifact_dir,
            expected_release_id=release_id,
            lookup_sqlite=lookup_sqlite,
        )
        if index is not None:
            _OPEN_CACHE[key] = index
        return index
