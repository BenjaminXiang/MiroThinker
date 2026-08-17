const BASE = "";

export interface DomainStats {
  name: string;
  count: number;
  quality: Record<string, number>;
  last_updated: string | null;
}

export interface DashboardResponse {
  domains: DomainStats[];
  ops: DashboardOps;
}

export interface PipelineStageSummary {
  stage: string;
  total: number;
  running: number;
  succeeded: number;
  partial: number;
  failed: number;
  latest_run_id: string | null;
  latest_domain: string | null;
  latest_started_at: string | null;
  latest_finished_at: string | null;
}

export interface PipelineFailureSample {
  run_id: string;
  run_kind: string;
  domain: string | null;
  status: string;
  items_processed: number | null;
  items_failed: number | null;
  error_summary: Record<string, unknown> | null;
  started_at: string;
  finished_at: string | null;
}

export interface PipelineIssueSample {
  issue_id: string;
  domain: string | null;
  issue_type: string | null;
  severity: string;
  description: string;
  task_id: string | null;
  source_rows: number[];
  recommended_action: string | null;
  reported_at: string;
}

export interface PipelineAction {
  action: string;
  label: string;
  run_id: string | null;
  domain: string | null;
  reason: string;
}

export interface DashboardOps {
  generated_at: string;
  active_runs: number;
  recent_failed_runs: number;
  open_issue_count: number;
  stages: PipelineStageSummary[];
  failure_samples: PipelineFailureSample[];
  issue_samples: PipelineIssueSample[];
  actions: PipelineAction[];
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
  task_id: string;
  source_page_id: string;
  dry_run: boolean;
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

export function fetchAdminProfessorDetail(id: string): Promise<unknown> {
  return fetchJSON(`/api/admin/professor/${id}`);
}

export function markAdminProfessor(
  id: string,
  body: { action: "confirm_ready" | "send_to_review" | "flag_recrawl"; note?: string }
): Promise<unknown> {
  return fetchJSON(`/api/admin/professor/${id}/mark`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  file: File,
  params: { dryRun?: boolean } = {}
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const qs = new URLSearchParams();
  if (params.dryRun) qs.set("dry_run", "true");
  const query = qs.toString();
  return fetchJSON(`/api/upload/${domain}${query ? `?${query}` : ""}`, {
    method: "POST",
    body: form,
  });
}

// --- Pipeline runs ---

export interface PipelineRunSourcePage {
  page_id: string;
  url: string;
  title: string | null;
  clean_text_path: string | null;
  fetched_at: string | null;
}

export interface PipelineRun {
  run_id: string;
  run_kind: string;
  status: string;
  run_scope: Record<string, unknown>;
  triggered_by: string | null;
  started_at: string;
  finished_at: string | null;
  items_processed: number | null;
  items_failed: number | null;
  error_summary: Record<string, unknown> | null;
}

export interface PipelineRunDetail extends PipelineRun {
  source_pages: PipelineRunSourcePage[];
}

export interface PipelineRunListResponse {
  items: PipelineRun[];
  total: number;
}

export interface PipelineRunActionResponse {
  task_id: string;
  status: string;
  domain: string;
  parent_run_id: string;
}

export function fetchPipelineRuns(params: {
  domain?: string;
  triggered_by?: string;
  status?: string;
  limit?: number;
} = {}): Promise<PipelineRunListResponse> {
  const qs = new URLSearchParams();
  if (params.domain) qs.set("domain", params.domain);
  if (params.triggered_by) qs.set("triggered_by", params.triggered_by);
  if (params.status) qs.set("status", params.status);
  if (params.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return fetchJSON(`/api/pipeline/runs${query ? `?${query}` : ""}`);
}

export function fetchPipelineRun(runId: string): Promise<PipelineRunDetail> {
  return fetchJSON(`/api/pipeline/runs/${runId}`);
}

export function triggerMilvusBackfill(
  runId: string,
  params: { dryRun?: boolean } = {}
): Promise<PipelineRunActionResponse> {
  const qs = new URLSearchParams();
  if (params.dryRun) qs.set("dry_run", "true");
  const query = qs.toString();
  return fetchJSON(
    `/api/pipeline/runs/${runId}/milvus-backfill${query ? `?${query}` : ""}`,
    { method: "POST" }
  );
}

export function triggerRetrievalValidation(
  runId: string
): Promise<PipelineRunActionResponse> {
  return fetchJSON(`/api/pipeline/runs/${runId}/retrieval-validation`, {
    method: "POST",
  });
}

// --- Pipeline issues ---

export interface PipelineIssue {
  issue_id: string;
  professor_id: string | null;
  link_id: string | null;
  institution: string | null;
  stage: string;
  severity: string;
  description: string;
  evidence_snapshot: Record<string, unknown> | null;
  reported_by: string | null;
  reported_at: string;
  resolved: boolean;
  resolved_at: string | null;
  resolution_notes: string | null;
  resolution_round: string | null;
  domain: string | null;
  issue_type: string | null;
  task_id: string | null;
  source_rows: number[];
  recommended_action: string | null;
  chat_feedback: ChatFeedbackIssueContext | null;
}

export interface PipelineIssueListResponse {
  items: PipelineIssue[];
  total: number;
  page: number;
  page_size: number;
}

export interface SourceRowCell {
  column_index: number;
  column_letter: string;
  header: string | null;
  value: string | null;
}

export interface SourceRowPreview {
  row_number: number;
  cells: SourceRowCell[];
}

export interface PipelineIssueSourceRowsResponse {
  issue_id: string;
  task_id: string | null;
  domain: string | null;
  upload_path: string | null;
  sheet_name: string | null;
  header_row_number: number | null;
  rows: SourceRowPreview[];
  warning: string | null;
}

export interface ChatFeedbackIssueContext {
  session_id: string | null;
  query: string | null;
  query_type: string | null;
  answer_text: string | null;
  answer_style: string | null;
  feedback_type: string | null;
  note: string | null;
  citations: ChatCitation[];
  citation_map: Record<string, unknown>;
  structured_payload: Record<string, unknown>;
}

export function fetchPipelineIssues(params: {
  stage?: string;
  severity?: string;
  resolved?: boolean;
  reported_by?: string;
  professor_id?: string;
  task_id?: string;
  domain?: string;
  issue_type?: string;
  q?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<PipelineIssueListResponse> {
  const qs = new URLSearchParams();
  if (params.stage) qs.set("stage", params.stage);
  if (params.severity) qs.set("severity", params.severity);
  if (params.resolved !== undefined) qs.set("resolved", String(params.resolved));
  if (params.reported_by) qs.set("reported_by", params.reported_by);
  if (params.professor_id) qs.set("professor_id", params.professor_id);
  if (params.task_id) qs.set("task_id", params.task_id);
  if (params.domain) qs.set("domain", params.domain);
  if (params.issue_type) qs.set("issue_type", params.issue_type);
  if (params.q) qs.set("q", params.q);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const query = qs.toString();
  return fetchJSON(`/api/pipeline-issues${query ? `?${query}` : ""}`);
}

export function fetchPipelineIssueSourceRows(
  issueId: string
): Promise<PipelineIssueSourceRowsResponse> {
  return fetchJSON(`/api/pipeline-issues/${issueId}/source-rows`);
}

export function updatePipelineIssue(
  issueId: string,
  body: {
    resolved: boolean;
    resolution_notes?: string;
    resolution_round?: string;
  }
): Promise<PipelineIssue> {
  return fetchJSON(`/api/pipeline-issues/${issueId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// --- Chat ---

export interface ChatCitation {
  type: "professor" | "paper" | "patent" | "company";
  id: string;
  label: string;
  url: string | null;
}

export interface ChatCandidateOption {
  id: string;
  domain: "professor" | "paper" | "patent" | "company";
  label: string;
  hint: string;
}

export interface ChatClarification {
  prompt: string;
  options: ChatCandidateOption[];
  default_id: string;
  omitted: number;
}

export interface ChatResponse {
  query: string;
  query_type: string;
  answer_text: string;
  citations: ChatCitation[];
  evidence: Record<string, unknown>[];
  clarification: ChatClarification | null;
  structured_payload: Record<string, unknown>;
  answer_style: "template" | "llm_synthesized";
  citation_map: Record<string, string>;
  suggested_followups: string[];
}

export interface ChatFeedbackResponse {
  issue_id: string;
  status: "filed";
  reported_at: string | null;
}

export interface ChatSessionResetResponse {
  session_id: string;
}

export function sendChatMessage(
  query: string,
  params: { entityIdHint?: string } = {}
): Promise<ChatResponse> {
  const body: { query: string; entity_id_hint?: string } = { query };
  if (params.entityIdHint) body.entity_id_hint = params.entityIdHint;
  return fetchJSON("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function resetChatSession(): Promise<ChatSessionResetResponse> {
  return fetchJSON("/api/chat/session/reset", {
    method: "POST",
  });
}

export function reportChatFeedback(
  response: ChatResponse,
  params: {
    feedbackType?: string;
    note?: string;
  } = {}
): Promise<ChatFeedbackResponse> {
  return fetchJSON("/api/chat/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: response.query,
      query_type: response.query_type,
      answer_text: response.answer_text,
      answer_style: response.answer_style,
      citations: response.citations ?? [],
      citation_map: response.citation_map ?? {},
      structured_payload: response.structured_payload ?? {},
      feedback_type: params.feedbackType ?? "incorrect_answer",
      note: params.note,
    }),
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

// --- Seeds (prof-seed-admin-console) ---

export type SeedLastRunStatus =
  | "success"
  | "failure"
  | "in_progress"
  | "never_run"
  | "adapter_missing";

export interface Seed {
  id: number;
  school: string;
  department: string | null;
  seed_url: string;
  last_run_at: string | null;
  last_run_status: SeedLastRunStatus;
  created_at: string;
  updated_at: string;
}

export interface SeedPayload {
  school: string;
  department: string | null;
  seed_url: string;
}

export interface SeedTriggerResponse {
  run_id: string;
  seed_id: number;
  status: "in_progress";
}

export function fetchSeeds(): Promise<Seed[]> {
  return fetchJSON("/api/seeds");
}

export function createSeed(payload: SeedPayload): Promise<Seed> {
  return fetchJSON("/api/seeds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateSeed(id: number, payload: SeedPayload): Promise<Seed> {
  return fetchJSON(`/api/seeds/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteSeed(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/api/seeds/${id}`, { method: "DELETE" });
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`API error: ${resp.status} ${resp.statusText} ${body}`);
  }
}

export function triggerSeed(id: number): Promise<SeedTriggerResponse> {
  return fetchJSON(`/api/seeds/${id}/trigger`, { method: "POST" });
}
