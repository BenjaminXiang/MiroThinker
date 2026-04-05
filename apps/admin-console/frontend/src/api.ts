const BASE = "";

export interface DomainStats {
  name: string;
  count: number;
  quality: Record<string, number>;
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

async function fetchJSON<T>(url: string): Promise<T> {
  const resp = await fetch(`${BASE}${url}`);
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

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
  } = {}
): Promise<PaginatedResponse<ReleasedObject>> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.sort_by) qs.set("sort_by", params.sort_by);
  if (params.sort_order) qs.set("sort_order", params.sort_order);
  const query = qs.toString();
  return fetchJSON(`/api/${domain}${query ? `?${query}` : ""}`);
}

export function fetchDomainObject(
  domain: string,
  id: string
): Promise<ReleasedObject> {
  return fetchJSON(`/api/${domain}/${id}`);
}
