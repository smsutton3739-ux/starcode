/**
 * Types mirroring the backend API.
 *
 * `ClaimType` is the load-bearing one: the backend enforces it, and every surface in
 * this app renders a claim through its declared type rather than by guessing from
 * content. That is what keeps a conjecture from ever looking like a finding.
 */

export type ClaimType =
  | "source_text"
  | "verified_history"
  | "astronomical_calculation"
  | "astronomical_dating_candidate"
  | "textual_analysis"
  | "traditional_interpretation"
  | "scholarly_interpretation"
  | "ai_hypothesis"
  | "uncertain";

export type AnalysisStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";

export interface ClaimPresentation {
  label: string;
  short: string;
  description: string;
  tone: string;
}

export interface Citation {
  id?: string;
  citation_text: string;
  title?: string | null;
  authors: string[];
  publication?: string | null;
  year?: number | null;
  url?: string | null;
  doi?: string | null;
  locator?: string | null;
  reference_kind: string;
  reliability?: string | null;
  /** False for model-supplied references. Rendered as "unverified" and never counted as evidence. */
  verified: boolean;
}

export interface Claim {
  /** Absent for claims embedded in a stored report, which are serialised before the
   *  database row exists. Present on everything returned by the analyses API. */
  id?: string;
  section: string;
  claim_type: ClaimType;
  statement: string;
  reasoning?: string | null;
  confidence: number;
  confidence_basis?: string | null;
  produced_by: string;
  engine?: string | null;
  algorithm_reference?: string | null;
  quoted_text?: string | null;
  text_span_start?: number | null;
  text_span_end?: number | null;
  ordering: number;
  payload: Record<string, unknown>;
  references?: Citation[];
  presentation?: ClaimPresentation | null;
  /** True when the reader's tier withholds this claim's content. The type, section,
   *  confidence and citations are still present — only the readable fields are
   *  replaced — so the UI can show what is being withheld rather than hiding it. */
  locked?: boolean;
}

export interface Entity {
  id: string;
  entity_type: string;
  name: string;
  canonical_name?: string | null;
  aliases: unknown[];
  description?: string | null;
  /** How sure we are the text refers to this at all. */
  extraction_confidence: number;
  /** How sure we are *which* referent it is — a genuinely different question. */
  identification_confidence?: number | null;
  mention_count: number;
  mentions: Array<{ surface: string; start: number; end: number }>;
  earliest_year?: number | null;
  latest_year?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  attributes: Record<string, unknown>;
}

export interface TimelineEvent {
  year: number;
  year_end?: number | null;
  label: string;
  description: string;
  kind: string;
  certainty: string;
  confidence: number;
  note?: string | null;
}

export interface ReportSection {
  key: string;
  title: string;
  claims: Claim[];
  claim_count: number;
  data?: Record<string, unknown>;
  is_empty: boolean;
  empty_reason?: string | null;
  narrative?: string;
  claim_type_breakdown: Record<string, number>;
}

export interface ConfidenceSummary {
  overall: number | null;
  band: string;
  by_type: Record<string, { count: number; mean_confidence: number; label: string }>;
  evidence_claim_count: number;
  hypothesis_claim_count?: number;
  total_claim_count: number;
  rationale: string;
}

export interface TraceStep {
  step: number;
  agent: string;
  status: string;
  reasoning: string;
  claims_produced: number;
  entities_produced: number;
  duration_ms?: number | null;
  attempts: number;
  provider?: string | null;
  model?: string | null;
  error?: string | null;
}

export interface Report {
  id: string;
  version: number;
  executive_summary: string;
  sections: ReportSection[];
  timeline: TimelineEvent[];
  confidence_summary: ConfidenceSummary;
  further_reading: Array<{ title: string; citation: string; why: string; source: string }>;
  reasoning_trace: TraceStep[];
  word_count: number;
  generator_version: string;
}

export interface AnalysisDocument {
  id: string;
  title?: string | null;
  source_kind: string;
  source_url?: string | null;
  char_count: number;
  word_count: number;
  detected_language?: string | null;
  ocr_applied: boolean;
  ocr_confidence?: number | null;
  extraction_metadata: Record<string, unknown>;
  created_at: string;
}

export interface AnalysisSummary {
  id: string;
  title: string;
  status: AnalysisStatus;
  progress: number;
  current_stage?: string | null;
  detected_language?: string | null;
  overall_confidence?: number | null;
  is_favorite: boolean;
  created_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  failed_stages: string[];
  tags: string[];
}

export interface AnalysisDetail extends AnalysisSummary {
  document?: AnalysisDocument | null;
  confidence_rationale?: string | null;
  source_identification: Record<string, unknown>;
  translation_applied: boolean;
  options: Record<string, unknown>;
  error_message?: string | null;
  token_usage: Record<string, unknown>;
  claims: Claim[];
  entities: Entity[];
  report?: Report | null;
  agent_runs: Array<{
    id: string;
    agent_name: string;
    sequence: number;
    status: string;
    provider?: string | null;
    model?: string | null;
    reasoning_summary?: string | null;
    error_message?: string | null;
    duration_ms?: number | null;
  }>;
}

export interface AnalysisCreated {
  id: string;
  status: AnalysisStatus;
  progress: number;
  poll_url: string;
  anonymous_token: string | null;
  message: string;
}

export interface AnalysisStatusResponse {
  id: string;
  status: AnalysisStatus;
  progress: number;
  current_stage?: string | null;
  stage_label?: string | null;
  error_message?: string | null;
  failed_stages: string[];
}

/**
 * Which pipeline an analysis runs.
 *
 * `analyze` is the ordinary report and the default everywhere. The rest run an
 * astronomical dating search: `date` is the free one (five per account, ever), and the
 * other three are paid.
 */
export type AnalysisMode =
  | "analyze"
  | "date"
  | "rectification"
  | "eschatological"
  | "historicizing";

export const PAID_DATING_MODES: AnalysisMode[] = [
  "rectification",
  "eschatological",
  "historicizing",
];

export interface AnalysisOptions {
  output_language?: string;
  include_traditional_interpretations?: boolean;
  include_alternative_interpretations?: boolean;
  include_astronomical_correlation?: boolean;
  astronomical_search_window_years?: number;
  maya_correlation?: number;
  detail_level?: "standard" | "brief" | "exhaustive";
  mode?: AnalysisMode;
  /**
   * Astronomical year numbers bounding a dating search — year 0 is 1 BCE, matching the
   * engine. A narrowing option only: the server clamps to the plan's limit, so asking
   * for more produces a smaller search rather than an error. Send both or neither.
   */
  date_range_start?: number | null;
  date_range_end?: number | null;
}

/** What is left of an account's astronomical dating allowance. */
export interface DatingQuota {
  used: number;
  /** null for an account with no limit — the UI shows nothing rather than "n of ∞". */
  limit: number | null;
  remaining: number | null;
  unlimited: boolean;
  paid_modes_available: boolean;
}

/** One criterion, checked against one candidate date. */
export interface CriterionOutcome {
  criterion: string;
  matched: boolean;
  strength: number;
  detail: string;
  /** False when no engine can decide it either way — listed, never scored. */
  searchable: boolean;
  evidence: Record<string, unknown>;
}

/**
 * The payload a dating-candidate claim carries.
 *
 * The matched and unmatched lists are required by the backend contract, not a
 * convention: a proposed date with no misses shown cannot be argued with, and a
 * candidate that cannot be argued with is worthless.
 */
export interface DateCandidatePayload {
  year: number;
  month: number;
  day: number;
  hour_ut: number | null;
  gregorian_label: string;
  fit: number;
  anchor: string;
  recurrences: number;
  engine: string;
  uncertainty_note: string;
  notes: string[];
  matched_criteria: CriterionOutcome[];
  unmatched_criteria: CriterionOutcome[];
  mode?: AnalysisMode;
  framework?: string;
}

export interface ApiError {
  error: string;
  detail?: string;
  request_id?: string;
  field_errors?: Record<string, string[]>;
}

export interface UploadResult {
  upload: { id: string; original_filename: string; byte_size: number; status: string };
  document_id: string;
  extracted_characters: number;
  ocr_applied: boolean;
  ocr_confidence?: number | null;
  warnings: string[];
  preview: string;
}

export interface SearchHit {
  kind: string;
  id: string;
  title: string;
  snippet: string;
  score: number;
  match_strength?: string | null;
  citation?: string | null;
  url?: string | null;
  created_at?: string | null;
}

export interface User {
  id: string;
  email: string;
  display_name?: string | null;
  avatar_url?: string | null;
  role: string;
  is_active: boolean;
  analyses_count: number;
  created_at: string;
}

/** ---- Billing ------------------------------------------------------------------ */

export type Tier = "free" | "paid" | "byok";

export interface BillingStatus {
  tier: Tier;
  /** Stripe's own status string, passed through rather than re-encoded. */
  subscription_status: string | null;
  has_subscription: boolean;
  can_manage: boolean;
  billing_enabled: boolean;
  unlocks_interpretation: boolean;
  byok_key_last4: string | null;
}
