/**
 * API client.
 *
 * Two credentials exist and they are not interchangeable:
 *  - a bearer token for a signed-in account;
 *  - an anonymous capability token, per analysis, which is the only way an
 *    unauthenticated visitor can retrieve their own result.
 *
 * Anonymous tokens are kept in localStorage keyed by analysis id. If the user clears
 * storage they genuinely lose access — there is no server-side recovery, which is the
 * price of not requiring an account. The UI says so at the point it matters.
 */

import type {
  AnalysisCreated,
  AnalysisDetail,
  AnalysisOptions,
  AnalysisStatusResponse,
  AnalysisSummary,
  ApiError,
  SearchHit,
  UploadResult,
  User,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const API = `${API_BASE}/api/v1`;

const ACCESS_TOKEN_KEY = "starcode.access_token";
const REFRESH_TOKEN_KEY = "starcode.refresh_token";
const ANON_TOKEN_PREFIX = "starcode.anon.";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly body: ApiError;

  constructor(status: number, body: ApiError) {
    super(body.detail || body.error || `Request failed with status ${status}`);
    this.name = "ApiRequestError";
    this.status = status;
    this.body = body;
  }

  /** Field-level messages, for rendering next to inputs rather than as a banner. */
  get fieldErrors(): Record<string, string[]> {
    return this.body.field_errors ?? {};
  }

  get isRateLimit(): boolean {
    return this.status === 429;
  }

  get isAuth(): boolean {
    return this.status === 401;
  }
}

// ---- token storage --------------------------------------------------------------

const isBrowser = () => typeof window !== "undefined";

export function getAccessToken(): string | null {
  return isBrowser() ? window.localStorage.getItem(ACCESS_TOKEN_KEY) : null;
}

export function setTokens(access: string, refresh: string): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, access);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens(): void {
  if (!isBrowser()) return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function storeAnonymousToken(analysisId: string, token: string): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(`${ANON_TOKEN_PREFIX}${analysisId}`, token);
}

export function getAnonymousToken(analysisId: string): string | null {
  return isBrowser()
    ? window.localStorage.getItem(`${ANON_TOKEN_PREFIX}${analysisId}`)
    : null;
}

/** Anonymous analyses this browser knows about, newest first. */
export function listAnonymousAnalyses(): string[] {
  if (!isBrowser()) return [];
  const ids: string[] = [];
  for (let i = 0; i < window.localStorage.length; i += 1) {
    const key = window.localStorage.key(i);
    if (key?.startsWith(ANON_TOKEN_PREFIX)) {
      ids.push(key.slice(ANON_TOKEN_PREFIX.length));
    }
  }
  return ids;
}

// ---- core request ---------------------------------------------------------------

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  analysisToken?: string | null;
  /** Skip the Authorization header even when a token exists. */
  anonymous?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, analysisToken, anonymous, headers, ...rest } = options;

  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string> | undefined),
  };

  if (body !== undefined && !(body instanceof FormData)) {
    finalHeaders["Content-Type"] = "application/json";
  }

  const accessToken = anonymous ? null : getAccessToken();
  if (accessToken) finalHeaders.Authorization = `Bearer ${accessToken}`;
  if (analysisToken) finalHeaders["X-Analysis-Token"] = analysisToken;

  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      ...rest,
      headers: finalHeaders,
      body:
        body === undefined
          ? undefined
          : body instanceof FormData
            ? body
            : JSON.stringify(body),
    });
  } catch {
    // A network failure and an API error need different messages: one is "check your
    // connection", the other is "the server said no".
    throw new ApiRequestError(0, {
      error: "network_error",
      detail:
        "Could not reach the server. Check your connection, and that the API is running.",
    });
  }

  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) {
      throw new ApiRequestError(response.status, {
        error: "unexpected_response",
        detail: `The server returned ${response.status}.`,
      });
    }
    return (await response.text()) as T;
  }

  const payload = await response.json();
  if (!response.ok) throw new ApiRequestError(response.status, payload as ApiError);
  return payload as T;
}

// ---- analyses -------------------------------------------------------------------

export interface AnalyzeInput {
  text?: string;
  url?: string;
  document_id?: string;
  upload_id?: string;
  title?: string;
  options?: AnalysisOptions;
}

export async function createAnalysis(input: AnalyzeInput): Promise<AnalysisCreated> {
  const created = await request<AnalysisCreated>("/analyses", {
    method: "POST",
    body: input,
  });
  if (created.anonymous_token) {
    storeAnonymousToken(created.id, created.anonymous_token);
  }
  return created;
}

export function getAnalysisStatus(id: string): Promise<AnalysisStatusResponse> {
  return request<AnalysisStatusResponse>(`/analyses/${id}/status`, {
    analysisToken: getAnonymousToken(id),
  });
}

export function getAnalysis(id: string, token?: string | null): Promise<AnalysisDetail> {
  return request<AnalysisDetail>(`/analyses/${id}`, {
    analysisToken: token ?? getAnonymousToken(id),
  });
}

export function getTrace(id: string, token?: string | null): Promise<unknown> {
  return request(`/analyses/${id}/trace`, {
    analysisToken: token ?? getAnonymousToken(id),
  });
}

export function listAnalyses(params: {
  limit?: number;
  offset?: number;
  status?: string;
  favorites_only?: boolean;
  tag?: string;
  q?: string;
} = {}): Promise<{ items: AnalysisSummary[]; total: number; limit: number; offset: number }> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const suffix = query.toString() ? `?${query}` : "";
  return request(`/analyses${suffix}`);
}

export function updateAnalysis(
  id: string,
  patch: { title?: string; is_favorite?: boolean; tags?: string[] },
): Promise<AnalysisSummary> {
  return request(`/analyses/${id}`, { method: "PATCH", body: patch });
}

export function deleteAnalysis(id: string): Promise<{ message: string }> {
  return request(`/analyses/${id}`, { method: "DELETE" });
}

export function rerunAnalysis(id: string): Promise<AnalysisCreated> {
  return request(`/analyses/${id}/rerun`, { method: "POST" });
}

/**
 * Poll until the analysis finishes.
 *
 * The interval backs off: early stages are fast and the user is watching, later ones
 * are slower and they have probably looked away. Polling stops on a terminal status,
 * never on a timer, so a slow analysis is not abandoned half-finished.
 */
export async function pollAnalysis(
  id: string,
  onProgress?: (status: AnalysisStatusResponse) => void,
  options: { signal?: AbortSignal; maxWaitMs?: number } = {},
): Promise<AnalysisStatusResponse> {
  const { signal, maxWaitMs = 10 * 60 * 1000 } = options;
  const started = Date.now();
  let delay = 400;

  for (;;) {
    if (signal?.aborted) throw new DOMException("Polling aborted", "AbortError");

    const status = await getAnalysisStatus(id);
    onProgress?.(status);

    if (["completed", "partial", "failed", "cancelled"].includes(status.status)) {
      return status;
    }
    if (Date.now() - started > maxWaitMs) {
      throw new ApiRequestError(0, {
        error: "timeout",
        detail:
          "The analysis is taking unusually long. It is still running on the server — reload this page later to check.",
      });
    }

    await new Promise((resolve) => setTimeout(resolve, delay));
    delay = Math.min(delay * 1.3, 3000);
  }
}

// ---- uploads --------------------------------------------------------------------

export function uploadFile(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResult>("/uploads", { method: "POST", body: form });
}

export function ingestUrl(url: string): Promise<{
  document_id: string;
  title?: string | null;
  extracted_characters: number;
  preview: string;
  warnings: string[];
}> {
  return request("/uploads/url", { method: "POST", body: { url } });
}

export function uploadLimits(): Promise<{
  max_upload_bytes: number;
  max_upload_mb: number;
  max_text_characters: number;
  accepted_mime_types: string[];
  accepted_extensions: string[];
  notes: string[];
}> {
  return request("/uploads/limits");
}

// ---- exports --------------------------------------------------------------------

export function exportUrl(id: string, format: string): string {
  return `${API}/analyses/${id}/export/${format}`;
}

/**
 * Download an export.
 *
 * Fetched rather than linked because the request needs an Authorization or
 * X-Analysis-Token header, which a plain anchor cannot send.
 */
export async function downloadExport(id: string, format: string): Promise<void> {
  const headers: Record<string, string> = {};
  const accessToken = getAccessToken();
  const anonToken = getAnonymousToken(id);
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (anonToken) headers["X-Analysis-Token"] = anonToken;

  const response = await fetch(exportUrl(id, format), { headers });
  if (!response.ok) {
    let detail = `Export failed (${response.status}).`;
    try {
      detail = ((await response.json()) as ApiError).detail ?? detail;
    } catch {
      /* the body was not JSON; keep the status message */
    }
    throw new ApiRequestError(response.status, { error: "export_failed", detail });
  }

  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const filename = match?.[1]
    ? decodeURIComponent(match[1])
    : `analysis.${format === "markdown" ? "md" : format}`;

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

// ---- search ---------------------------------------------------------------------

export function search(params: {
  query: string;
  mode?: "semantic" | "keyword" | "hybrid";
  scope?: "analyses" | "corpus" | "all";
  limit?: number;
}): Promise<{ query: string; total: number; hits: SearchHit[]; note?: string | null }> {
  return request("/search", { method: "POST", body: params });
}

// ---- auth -----------------------------------------------------------------------

export async function login(email: string, password: string): Promise<User> {
  const tokens = await request<{ access_token: string; refresh_token: string }>(
    "/auth/login",
    { method: "POST", body: { email, password }, anonymous: true },
  );
  setTokens(tokens.access_token, tokens.refresh_token);
  return getCurrentUser();
}

export async function register(
  email: string,
  password: string,
  displayName?: string,
): Promise<User> {
  const tokens = await request<{ access_token: string; refresh_token: string }>(
    "/auth/register",
    {
      method: "POST",
      body: { email, password, display_name: displayName },
      anonymous: true,
    },
  );
  setTokens(tokens.access_token, tokens.refresh_token);
  return getCurrentUser();
}

export function getCurrentUser(): Promise<User> {
  return request<User>("/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await request("/auth/logout", { method: "POST" });
  } catch {
    // Signing out locally must succeed even if the server call does not.
  }
  clearTokens();
}

/** What sign-in methods this deployment offers. Read it rather than assuming. */
export function authCapabilities(): Promise<{
  password_registration_enabled: boolean;
  anonymous_analysis_enabled: boolean;
  note: string | null;
  providers: Array<{ name: string; configured: boolean; authorize_url: string }>;
}> {
  return request("/auth/oauth/providers", { anonymous: true });
}

export function oauthUrl(provider: string): string {
  return `${API}/auth/oauth/${provider}/authorize`;
}

// ---- reference data --------------------------------------------------------------

export function skyOnDate(params: {
  year: number;
  month?: number;
  day?: number;
  hour_ut?: number;
}): Promise<Record<string, unknown>> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  );
  return request(`/astronomy/sky?${query}`, { anonymous: true });
}

export function eclipsesInRange(
  startYear: number,
  endYear: number,
  kind: "both" | "solar" | "lunar" = "both",
): Promise<{ count: number; events: Array<Record<string, unknown>> }> {
  return request(
    `/astronomy/eclipses?start_year=${startYear}&end_year=${endYear}&kind=${kind}`,
    { anonymous: true },
  );
}

export function convertCalendar(params: {
  system: string;
  year: number;
  month?: number;
  day?: number;
}): Promise<Record<string, unknown>> {
  const query = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  );
  return request(`/calendars/convert?${query}`, { anonymous: true });
}

export function listCalendars(): Promise<{ calendars: Array<Record<string, unknown>> }> {
  return request("/calendars", { anonymous: true });
}

export function claimTypeVocabulary(): Promise<{
  claim_types: Array<Record<string, unknown>>;
  rule: string;
}> {
  return request("/corpus/claim-types", { anonymous: true });
}

export function pipelineInfo(): Promise<{
  agents: Array<Record<string, unknown>>;
  provider: { provider: string; model: string; is_offline: boolean; note: string };
}> {
  return request("/corpus/pipeline", { anonymous: true });
}

export function corpusSources(): Promise<{
  total: number;
  disclosure: string;
  sources: Array<Record<string, unknown>>;
}> {
  return request("/corpus/sources", { anonymous: true });
}

// ---- library ---------------------------------------------------------------------

export function dashboard(): Promise<Record<string, unknown>> {
  return request("/dashboard");
}

export function listCollections(): Promise<Array<Record<string, unknown>>> {
  return request("/collections");
}

export function createCollection(name: string, description?: string): Promise<Record<string, unknown>> {
  return request("/collections", { method: "POST", body: { name, description } });
}

export function createShare(
  id: string,
  expiresInDays?: number,
): Promise<{ id: string; url: string; token: string | null }> {
  return request(`/analyses/${id}/share`, {
    method: "POST",
    body: { expires_in_days: expiresInDays ?? null, allow_export: true },
  });
}

export function health(): Promise<Record<string, unknown>> {
  return request("/health", { anonymous: true });
}
