const BASE = "";

export interface DomainStats {
  name: string;
  count: number;
  quality: Record<string, number>;
  last_updated: string | null;
}

export interface DashboardResponse {
  domains: DomainStats[];
}

export interface PaginatedResponse<T = Record<string, unknown>> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReleasedObject {
  id: string;
  object_type: string;
  display_name: string;
  core_facts: Record<string, unknown>;
  summary_fields: Record<string, unknown>;
  evidence: Evidence[];
  last_updated: string;
  quality_status: string;
}

export interface Evidence {
  source_type: string;
  source_url: string | null;
  source_file: string | null;
  fetched_at: string;
  snippet: string | null;
  confidence: number | null;
}

export interface RelatedResponse {
  papers: ReleasedObject[];
  patents: ReleasedObject[];
  companies: ReleasedObject[];
}

export interface FilterOptionsResponse {
  options: string[];
}

export interface BatchQualityResponse {
  updated: number;
}

export interface BatchDeleteResponse {
  deleted: number;
}

export interface UploadResponse {
  imported: number;
  skipped: number;
  total_in_store: number;
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, init);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`API error: ${resp.status} ${resp.statusText} ${body}`);
  }
  return resp.json() as Promise<T>;
}

// --- Read ---

export function fetchDashboard(): Promise<DashboardResponse> {
  return fetchJSON("/api/dashboard");
}

export function fetchDomainList(
  domain: string,
  params: {
    q?: string;
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: "asc" | "desc";
    filters?: Record<string, string>;
  } = {}
): Promise<PaginatedResponse<ReleasedObject>> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.sort_by) qs.set("sort_by", params.sort_by);
  if (params.sort_order) qs.set("sort_order", params.sort_order);
  if (params.filters && Object.keys(params.filters).length > 0) {
    qs.set("filters", JSON.stringify(params.filters));
  }
  const query = qs.toString();
  return fetchJSON(`/api/${domain}${query ? `?${query}` : ""}`);
}

export function fetchDomainObject(
  domain: string,
  id: string
): Promise<ReleasedObject> {
  return fetchJSON(`/api/${domain}/${id}`);
}

export function fetchFilterOptions(
  domain: string,
  field: string
): Promise<FilterOptionsResponse> {
  return fetchJSON(`/api/${domain}/filters/${field}`);
}

export function fetchRelated(
  domain: string,
  id: string
): Promise<RelatedResponse> {
  return fetchJSON(`/api/${domain}/${id}/related`);
}

// --- Mutations ---

export function updateRecord(
  domain: string,
  id: string,
  body: {
    core_facts?: Record<string, unknown>;
    summary_fields?: Record<string, unknown>;
    quality_status?: string;
  }
): Promise<ReleasedObject> {
  return fetchJSON(`/api/${domain}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteRecord(domain: string, id: string): Promise<void> {
  return fetch(`${BASE}/api/${domain}/${id}`, { method: "DELETE" }).then(
    (resp) => {
      if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
    }
  );
}

export function batchUpdateQuality(
  ids: string[],
  quality_status: string
): Promise<BatchQualityResponse> {
  return fetchJSON("/api/batch/quality", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, quality_status }),
  });
}

export function batchDelete(ids: string[]): Promise<BatchDeleteResponse> {
  return fetchJSON("/api/batch/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
}

export function uploadFile(
  domain: "company" | "patent",
  file: File
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return fetchJSON(`/api/upload/${domain}`, {
    method: "POST",
    body: form,
  });
}

// --- Chat ---

export interface ChatCitation {
  type: "professor" | "paper" | "patent" | "company";
  id: string;
  label: string;
  url: string | null;
}

export interface ChatResponse {
  query: string;
  query_type: string;
  answer_text: string;
  citations: ChatCitation[];
  structured_payload: Record<string, unknown>;
  answer_style: "template" | "llm_synthesized";
  citation_map: Record<string, string>;
}

export function sendChatMessage(query: string): Promise<ChatResponse> {
  return fetchJSON("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

export function exportDomain(
  domain: string,
  format: "csv" | "xlsx" = "csv",
  ids?: string[]
): void {
  const qs = new URLSearchParams({ format });
  if (ids && ids.length > 0) qs.set("ids", ids.join(","));
  window.open(`${BASE}/api/export/${domain}?${qs.toString()}`);
}
