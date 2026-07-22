from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import hashlib
from importlib import util
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field


JsonObject = dict[str, Any]
SHA256_PATTERN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
SOURCE_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:COMP|PROF|PAPER|PAT|PROF-PAPER-LINK)-[A-Z0-9]+(?![A-Za-z0-9])"
)
RAW_ENUM_PATTERN = re.compile(
    r"\b(?:professor_attributed_to_paper|company_has_patent|professor_authored_paper)\b"
)
_DOMAINS = ("company", "paper", "patent", "professor")
_RELATION_TYPES = frozenset({"company_has_patent", "professor_authored_paper"})
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_STATIC_DIR = _REPO_ROOT / "apps" / "admin-console" / "backend" / "static"


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    entity_id_hint: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _derived_id(kind: str, seed: str) -> str:
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"cv2-{kind}-{suffix}"


def _plain_row(row: Any) -> JsonObject:
    if isinstance(row, Mapping):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    values: JsonObject = {}
    for field in (
        "source_id",
        "id",
        "object_type",
        "display_name",
        "payload_json_sha256",
        "projectable_payload",
    ):
        if hasattr(row, field):
            values[field] = getattr(row, field)
    return values


def _nested(row: Mapping[str, Any], key: str) -> JsonObject:
    value = row.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "" and value != []:
            return value
    return default


def _safe_https(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text.startswith("https://") else None


def _public_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = SOURCE_ID_PATTERN.sub("内部标识已省略", text)
    text = SHA256_PATTERN.sub("内部摘要已省略", text)
    text = RAW_ENUM_PATTERN.sub("内部关系类型已省略", text)
    return text


def _public_text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [copy for item in value if (copy := _public_text(item)) is not None]


class PreviewIndex:
    def __init__(self, rows: Iterable[Any], *, release_id: str) -> None:
        self.release_id = release_id
        self.raw_rows = tuple(_plain_row(row) for row in rows)
        if not self.raw_rows:
            raise ValueError("the preview requires selected records")

        self.source_rows: dict[str, JsonObject] = {}
        self.records: dict[str, list[JsonObject]] = {domain: [] for domain in _DOMAINS}
        self.by_public_id: dict[str, JsonObject] = {}
        self.source_to_public_id: dict[str, str] = {}
        self.as_of = ""

        for raw in self.raw_rows:
            source_id = str(raw.get("source_id") or raw.get("id") or "").strip()
            object_type = str(raw.get("object_type") or "").strip()
            display_name = str(raw.get("display_name") or "").strip()
            projected = _nested(raw, "projectable_payload")
            merged = {**raw, **projected}
            merged.setdefault("id", source_id)
            merged.setdefault("object_type", object_type)
            merged.setdefault("display_name", display_name)
            self.source_rows[source_id] = merged
            if object_type not in _DOMAINS:
                continue
            record = self._project_record(merged, source_id, object_type, display_name)
            self.records[object_type].append(record)
            self.by_public_id[record["canonical_identity_id"]] = record
            self.source_to_public_id[source_id] = record["canonical_identity_id"]
            candidate_as_of = str(merged.get("last_updated") or "")
            if candidate_as_of > self.as_of:
                self.as_of = candidate_as_of

        missing = [domain for domain in _DOMAINS if len(self.records[domain]) != 1]
        if missing:
            raise ValueError(
                f"preview needs exactly one selected record per domain: {missing}"
            )
        self.as_of = self.as_of or _now()

    def _project_record(
        self,
        row: Mapping[str, Any],
        source_id: str,
        domain: str,
        display_name: str,
    ) -> JsonObject:
        core = _nested(row, "core_facts")
        summary = _nested(row, "summary_fields")
        public_id = _derived_id(domain, source_id)
        payload_hash = str(row.get("payload_json_sha256") or _digest(row))
        evidence_id = _derived_id("evidence", payload_hash)
        common: JsonObject = {
            "release_id": self.release_id,
            "canonical_identity_id": public_id,
            "decision_id": _derived_id("decision", source_id),
            "assertion_id": _derived_id("assertion", payload_hash),
            "quality_status": str(row.get("quality_status") or "verified_preview"),
            "evidence_ids": [evidence_id],
            "field_lineage": [
                {
                    "field": "display_name",
                    "evidence_id": evidence_id,
                    "release_id": self.release_id,
                }
            ],
            "retrieval_traces": [],
            "limitations": [
                {
                    "code": "preview_selection_only",
                    "message": "当前仅展示只读选择清单中的少量真实数据。",
                }
            ],
            "as_of": str(row.get("last_updated") or "") or None,
        }
        if domain == "company":
            common.update(
                {
                    "name": _public_text(_first(core.get("name"), display_name)),
                    "normalized_name": _public_text(core.get("normalized_name")),
                    "industry": _public_text(core.get("industry")),
                    "geography": _public_text(core.get("geography")),
                    "founded_at": core.get("founded_at"),
                    "website": _safe_https(core.get("website")),
                    "profile_summary": _public_text(
                        _first(
                            summary.get("profile_summary"),
                            summary.get("summary_text"),
                            core.get("profile_summary"),
                        )
                    ),
                    "technology_route_summary": _public_text(
                        _first(
                            summary.get("technology_route_summary"),
                            core.get("technology_route_summary"),
                        )
                    ),
                }
            )
        elif domain == "paper":
            common.update(
                {
                    "title": _public_text(_first(core.get("title"), display_name)),
                    "authors": _public_text_list(core.get("authors")),
                    "venue": _public_text(core.get("venue")),
                    "year": core.get("year"),
                    "citation_count": core.get("citation_count"),
                    "publication_date": core.get("publication_date"),
                    "doi": _public_text(core.get("doi")),
                    "summary": _public_text(
                        _first(summary.get("summary_text"), core.get("abstract"))
                    ),
                }
            )
        elif domain == "patent":
            common.update(
                {
                    "title": _public_text(_first(core.get("title"), display_name)),
                    "patent_number": _public_text(core.get("patent_number")),
                    "patent_type": _public_text(core.get("patent_type")),
                    "filing_date": core.get("filing_date"),
                    "publication_date": core.get("publication_date"),
                    "applicants": _public_text_list(core.get("applicants")),
                    "abstract": _public_text(
                        _first(core.get("abstract"), summary.get("summary_text"))
                    ),
                }
            )
        else:
            common.update(
                {
                    "name": _public_text(_first(core.get("name"), display_name)),
                    "institution": _public_text(core.get("institution")),
                    "department": _public_text(core.get("department")),
                    "title": _public_text(core.get("title")),
                    "homepage": _safe_https(core.get("homepage")),
                    "research_directions": _public_text_list(
                        core.get("research_directions")
                    ),
                    "paper_count": core.get("paper_count"),
                    "h_index": core.get("h_index"),
                    "citation_count": core.get("citation_count"),
                    "profile_summary": _public_text(
                        _first(
                            summary.get("profile_summary"),
                            summary.get("summary_text"),
                        )
                    ),
                }
            )
        return {key: value for key, value in common.items() if value is not None}

    def page(self, domain: str) -> JsonObject:
        self.require_domain(domain)
        items = self.records[domain]
        return {
            "release_id": self.release_id,
            "as_of": self.as_of,
            "domain": domain,
            "total": len(items),
            "items": items,
            "limitations": [],
        }

    def require_domain(self, domain: str) -> None:
        if domain not in _DOMAINS:
            raise HTTPException(status_code=404, detail="unknown domain")

    def detail(self, domain: str, public_id: str) -> JsonObject:
        self.require_domain(domain)
        item = self.by_public_id.get(public_id)
        if item is None or item not in self.records[domain]:
            raise HTTPException(status_code=404, detail="record not found")
        return item

    def related(self, domain: str, public_id: str, relation_type: str) -> JsonObject:
        self.detail(domain, public_id)
        if relation_type not in _RELATION_TYPES:
            raise HTTPException(status_code=400, detail="unsupported relation type")
        targets: list[JsonObject] = []
        if relation_type == "company_has_patent" and domain in {"company", "patent"}:
            target_domain = "patent" if domain == "company" else "company"
            targets = list(self.records[target_domain])
        elif relation_type == "professor_authored_paper" and domain in {
            "professor",
            "paper",
        }:
            target_domain = "paper" if domain == "professor" else "professor"
            targets = list(self.records[target_domain])
        return {
            "release_id": self.release_id,
            "relation_type": relation_type,
            "total": len(targets),
            "items": targets,
            "limitations": [],
        }


def _entity_text(item: Mapping[str, Any]) -> str:
    return str(item.get("name") or item.get("title") or "该条目")


def _local_evidence(item: Mapping[str, Any]) -> JsonObject:
    evidence_id = str((item.get("evidence_ids") or [""])[0])
    return {
        "evidence_id": evidence_id,
        "object_id": item["canonical_identity_id"],
        "domain": "local",
        "lane": "exact",
        "source_nature": "local",
        "source_locator": f"canonical-v2://{quote(str(item['canonical_identity_id']))}",
        "snippet": f"{_entity_text(item)}：当前候选发布版本中的已验证选择记录。",
        "score": 1.0,
        "release_id": item["release_id"],
    }


def _web_evidence(
    query: str, web_provider: Any
) -> tuple[list[JsonObject], list[JsonObject]]:
    if web_provider is None:
        return [], [
            {"code": "web_provider_unavailable", "message": "Web Search 未配置。"}
        ]
    try:
        result = web_provider.search(query)
    except Exception:
        return [], [
            {"code": "web_provider_unavailable", "message": "Web Search 暂时不可用。"}
        ]
    organic = result.get("organic") if isinstance(result, Mapping) else []
    evidence: list[JsonObject] = []
    for rank, raw in enumerate(organic or [], start=1):
        if not isinstance(raw, Mapping):
            continue
        locator = _safe_https(raw.get("link"))
        if locator is None:
            continue
        snapshot = {
            "query": query,
            "rank": rank,
            "title": str(raw.get("title") or "公开网页结果")[:300],
            "source_locator": locator,
            "snippet": str(raw.get("snippet") or "")[:800],
        }
        content = _canonical_json(snapshot)
        digest = hashlib.sha256(content).hexdigest()
        evidence.append(
            {
                "evidence_id": _derived_id("web-evidence", digest),
                "object_id": _derived_id("web-query", query),
                "domain": "web",
                "lane": "web",
                "source_nature": "current_web",
                "source_locator": locator,
                "title": snapshot["title"],
                "snippet": snapshot["snippet"],
                "score": max(0.0, 1.0 - ((rank - 1) * 0.1)),
                "web_snapshot": {
                    "snapshot_id": _derived_id("web-snapshot", digest),
                    "content_sha256": digest,
                    "retrieved_at": _now(),
                    "byte_length": len(content),
                },
            }
        )
        if len(evidence) == 3:
            break
    if not evidence:
        return [], [
            {
                "code": "web_evidence_missing",
                "message": "Web Search 未返回可安全引用的 HTTPS 结果。",
            }
        ]
    return evidence, []


def _answer_for(
    query: str, index: PreviewIndex
) -> tuple[str, str, list[JsonObject], list[str]]:
    company = index.records["company"][0]
    patent = index.records["patent"][0]
    professor = index.records["professor"][0]
    paper = index.records["paper"][0]
    wants_patent = "专利" in query or str(patent.get("title")) in query
    wants_paper = (
        any(token in query for token in ("论文", "成果", "发表"))
        or str(paper.get("title")) in query
    )
    mentions_company = str(company.get("name")) in query
    mentions_professor = str(professor.get("name")) in query

    if wants_patent and mentions_company:
        text = (
            f"{company['name']}是一家{company.get('industry') or '先进制造'}企业。"
            f"当前选择数据中可核验到 1 项关联专利：《{patent['title']}》"
            f"（{patent.get('patent_number') or '专利号未提供'}，公开日 {patent.get('publication_date') or '未提供'}）。"
        )
        return (
            text,
            "relationship",
            [company, patent],
            ["继续查看这项专利的摘要", "查询该企业的公开网页信息"],
        )
    if wants_paper and mentions_professor:
        text = (
            f"{professor['name']}任职于{professor.get('institution') or '机构信息未提供'}，"
            f"当前选择数据中可核验到 1 篇关联论文：《{paper['title']}》"
            f"（{paper.get('venue') or '期刊未提供'}，{paper.get('year') or '年份未提供'}）。"
        )
        return (
            text,
            "relationship",
            [professor, paper],
            ["继续查看论文 DOI 与作者", "查询该教授的公开网页信息"],
        )
    if str(patent.get("title")) in query:
        text = (
            f"《{patent['title']}》是{patent.get('patent_type') or '类型未提供'}专利，"
            f"专利号 {patent.get('patent_number') or '未提供'}，申请日 {patent.get('filing_date') or '未提供'}，"
            f"公开日 {patent.get('publication_date') or '未提供'}。{patent.get('abstract') or ''}"
        )
        return text, "exact", [patent], ["查看其申请企业", "继续检索当前网页证据"]
    if str(paper.get("title")) in query:
        authors = "、".join(str(value) for value in paper.get("authors") or [])
        text = (
            f"《{paper['title']}》发表于 {paper.get('venue') or '未知期刊'}（{paper.get('year') or '年份未提供'}），"
            f"作者包括 {authors or '作者未提供'}，DOI 为 {paper.get('doi') or '未提供'}。"
        )
        return text, "exact", [paper], ["查看关联教授", "继续检索论文当前网页信息"]
    if str(professor.get("name")) in query:
        directions = "、".join(
            str(value) for value in professor.get("research_directions") or []
        )
        text = (
            f"{professor['name']}是{professor.get('institution') or '机构未提供'}"
            f"{professor.get('department') or ''}的{professor.get('title') or '教师'}，"
            f"研究方向包括{directions or '当前记录未提供'}。"
        )
        return (
            text,
            "exact",
            [professor],
            ["查看一篇关联论文", "继续检索该教授的公开网页信息"],
        )
    text = (
        f"{company['name']}属于{company.get('industry') or '行业未提供'}。"
        f"{company.get('profile_summary') or ''} {company.get('technology_route_summary') or ''}"
    ).strip()
    return (
        text,
        "exact",
        [company],
        ["查看该企业的一项专利", "继续检索企业当前网页信息"],
    )


def _chat_response(query: str, index: PreviewIndex, web_provider: Any) -> JsonObject:
    answer, lane, local_items, followups = _answer_for(query, index)
    local_evidence = [_local_evidence(item) for item in local_items]
    web_evidence, limitations = _web_evidence(query, web_provider)
    evidence = [*local_evidence, *web_evidence]
    lanes = [lane, "web"]

    claims = [
        {
            "claim_id": _derived_id("claim", f"{query}:{position}"),
            "text": _entity_text(item),
            "evidence_ids": item.get("evidence_ids") or [],
        }
        for position, item in enumerate(local_items, start=1)
    ]
    evidence_ids = [str(item["evidence_id"]) for item in evidence]
    continuation_offer = None
    if limitations:
        continuation_offer = {
            "reason": limitations[0]["code"],
            "options": [
                {
                    "option_id": "retry_current_web",
                    "operation": "targeted_evidence_search",
                    "label": "稍后重试当前网页检索",
                }
            ],
        }
    citations = [
        {
            "id": item["evidence_id"],
            "type": "当前网页"
            if item["source_nature"] == "current_web"
            else "本地发布证据",
            "label": item.get("title") or item.get("snippet") or "证据",
            **(
                {"url": item["source_locator"]}
                if item["source_nature"] == "current_web"
                else {}
            ),
        }
        for item in evidence
    ]
    return {
        "query": query,
        "query_type": "canonical_v2_relationship"
        if lane == "relationship"
        else "canonical_v2_exact",
        "answer_text": answer,
        "citations": citations,
        "evidence": evidence,
        "clarification": None,
        "structured_payload": {
            "canonical_v2": {
                "release_id": index.release_id,
                "plan_id": _derived_id("plan", query),
                "plan_version": "preview-p1",
                "behavior_class": "knowledge_retrieval",
                "interaction_mode": "single_turn_with_continuation",
                "lanes": lanes,
                "retrieval_traces": [
                    {
                        "lane": lane,
                        "status": "completed",
                        "result_count": len(local_items),
                    },
                    {
                        "lane": "web",
                        "status": "completed" if web_evidence else "limited",
                        "result_count": len(web_evidence),
                    },
                ],
                "evidence_ids": evidence_ids,
                "claims": claims,
                "claim_evidence_mappings": [
                    {
                        "claim_id": claim["claim_id"],
                        "evidence_ids": claim["evidence_ids"],
                    }
                    for claim in claims
                ],
                "limitations": limitations,
                "enumeration_coverage": {
                    "mode": "selected_preview_only",
                    "scope": "manifest-selected records",
                    "complete": False,
                },
                "continuation_offer": continuation_offer,
            }
        },
        "answer_style": "evidence_bound_preview",
        "citation_map": {
            str(index): citation["id"]
            for index, citation in enumerate(citations, start=1)
        },
        "suggested_followups": followups[:3],
    }


def create_preview_app(
    *,
    rows: Iterable[Any],
    release_id: str,
    web_provider: Any = None,
) -> FastAPI:
    index = PreviewIndex(rows, release_id=release_id)
    app = FastAPI(title="Canonical V2 real-data preview", version="preview-p1")
    app.state.preview_index = index
    app.state.web_provider = web_provider

    @app.get("/api/health")
    def health() -> JsonObject:
        return {
            "status": "ok",
            "release_id": index.release_id,
            "preview_mode": True,
            "web_search_configured": bool(getattr(web_provider, "api_key", "")),
        }

    @app.get("/api/canonical-v2/admin/status")
    def status() -> JsonObject:
        return {
            "release_id": index.release_id,
            "as_of": index.as_of,
            "domains": [
                {"domain": domain, "record_count": len(index.records[domain])}
                for domain in _DOMAINS
            ],
            "gap_summary": {"total": 0},
            "preview": {"selected_records": 5, "read_only": True},
        }

    @app.get("/api/canonical-v2/admin/domains/{domain}")
    def domain_page(domain: str) -> JsonObject:
        return index.page(domain)

    @app.get("/api/canonical-v2/admin/domains/{domain}/{public_id}")
    def domain_detail(domain: str, public_id: str) -> JsonObject:
        return index.detail(domain, public_id)

    @app.get("/api/canonical-v2/admin/domains/{domain}/{public_id}/related")
    def domain_related(domain: str, public_id: str, relation_type: str) -> JsonObject:
        return index.related(domain, public_id, relation_type)

    @app.get("/api/canonical-v2/operations/gaps")
    def gaps() -> JsonObject:
        return {"release_id": index.release_id, "total": 0, "items": []}

    @app.get("/api/canonical-v2/operations/gaps/{gap_id}")
    def gap_detail(gap_id: str) -> JsonObject:
        del gap_id
        raise HTTPException(status_code=404, detail="knowledge gap not found")

    @app.post("/api/chat")
    def chat(request: ChatRequest, response: Response) -> JsonObject:
        response.set_cookie(
            "miroflow_chat_session",
            _derived_id("session", request.query + _now()),
            httponly=True,
            samesite="lax",
        )
        return _chat_response(request.query.strip(), index, web_provider)

    @app.post("/api/chat/session/reset")
    def reset_session(response: Response) -> JsonObject:
        response.delete_cookie("miroflow_chat_session")
        return {"status": "reset"}

    @app.get("/browse")
    def browse() -> FileResponse:
        return FileResponse(_STATIC_DIR / "browse.html")

    @app.get("/chat")
    def chat_page() -> FileResponse:
        return FileResponse(_STATIC_DIR / "chat.html")

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/browse")

    @app.get("/static/{asset_path:path}")
    def static_asset(asset_path: str) -> FileResponse:
        target = (_STATIC_DIR / asset_path).resolve()
        if _STATIC_DIR.resolve() not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(target)

    return app


def _load_web_provider() -> Any:
    module_path = (
        _REPO_ROOT
        / "apps"
        / "miroflow-agent"
        / "src"
        / "data_agents"
        / "providers"
        / "web_search.py"
    )
    spec = util.spec_from_file_location("canonical_v2_preview_web_search", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Web Search provider")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.WebSearchProvider(timeout=8.0)


def _load_real_rows(evidence_root: Path, manifest_path: Path) -> tuple[Any, ...]:
    extractor_path = _SCRIPT_DIR / "extract_preview_selection.py"
    spec = util.spec_from_file_location(
        "canonical_v2_preview_selection", extractor_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load preview selection extractor")
    module = util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    extraction = module.extract_preview_selection(
        evidence_root=evidence_root,
        manifest_path=manifest_path,
    )
    records = getattr(extraction, "records", extraction)
    return tuple(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve a read-only Canonical V2 real-data preview"
    )
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release-id", default="preview-p1-real-data-20260721")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18189)
    args = parser.parse_args(argv)

    rows = _load_real_rows(args.evidence_root, args.manifest)
    app = create_preview_app(
        rows=rows,
        release_id=args.release_id,
        web_provider=_load_web_provider(),
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
