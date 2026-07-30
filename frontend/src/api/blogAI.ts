// Blog AI optimization API client (spec 005, US3, T077).
//
// Wraps the async optimization endpoints. Submitting an optimization is bound to
// the current revision and returns the Job (202); the AI never mutates the live
// article — it produces an unapplied candidate reviewed later (US4). All calls go
// through the shared `api` wrapper (same-origin cookies + CSRF).

import { ApiError, api } from '@/api/client'
import type { AsyncJob } from '@/api/types'

// Mirrors OptimizeBody.optimization_type (backend schemas.py).
export type OptimizationType =
  | 'full'
  | 'language'
  | 'structure'
  | 'metadata'
  | 'check'
  | 'reoptimize'

// Mirrors OptimizeBody.scope.
export type OptimizationScope = 'all' | 'body' | 'metadata' | 'selected_fields'

export interface OptimizeBody {
  post_version: number
  optimization_type: OptimizationType
  scope?: OptimizationScope
  selected_fields?: string[]
  skill_id?: string | null
  model_key?: string | null
  instruction?: string | null
  request_nonce?: string | null
}

// Mirrors ai_router._run_out.
export interface AIRun {
  id: string
  post_id: string
  job_id: string
  optimization_type: OptimizationType
  content_class: string
  skill_version_id: string
  model_key: string
  ai_schema_version: string
  input_hash: string
  outcome: string | null
  candidate_id: string | null
  validation_summary: Record<string, unknown> | null
  created_at: string
  completed_at: string | null
}

// Stable, user-facing categories derived from backend Problem `code`s so the
// dialog can branch without matching on free-text messages.
export type OptimizeErrorKind =
  | 'version_conflict'
  | 'skill_unresolved'
  | 'not_found'
  | 'invalid_request'
  | 'unknown'

export function classifyOptimizeError(err: unknown): OptimizeErrorKind {
  if (!(err instanceof ApiError)) return 'unknown'
  if (err.status === 409 || err.code === 'version_conflict') return 'version_conflict'
  if (err.code === 'skill_unresolved' || err.code === 'skill_incomplete')
    return 'skill_unresolved'
  if (err.status === 404) return 'not_found'
  if (err.status === 422) return 'invalid_request'
  return 'unknown'
}

// --- Candidate review + decision (spec 005, US4, T091) ---

export type FieldStatus =
  | 'unchanged'
  | 'user_only'
  | 'ai_only'
  | 'agreed'
  | 'conflict'

export interface FieldDiffEntry {
  base: unknown
  current: unknown
  candidate: unknown
  status: FieldStatus
}

export interface CandidateSummary {
  id: string
  post_id: string
  ai_run_id: string
  base_revision_id: string
  candidate_revision_id: string
  status: 'pending' | 'merge_required' | 'applied' | 'rejected' | 'copied'
  field_diff: Record<string, { from: unknown; to: unknown; classification: string }>
  validation: Record<string, unknown>
  applied_revision_id: string | null
  created_at: string
  reviewed_at: string | null
}

export interface CandidateCompare {
  candidate: CandidateSummary
  post_version: number
  field_diff: Record<string, FieldDiffEntry>
  body_diff: {
    from_label: string
    to_label: string
    unified_diff: string
    changed: boolean
  }
  conflicts: string[]
  validation: Record<string, unknown>
}

export type DecisionAction =
  | 'apply_all'
  | 'apply_body'
  | 'apply_metadata'
  | 'apply_fields'
  | 'keep_current'
  | 'reject'
  | 'copy'

export interface DecisionBody {
  post_version: number
  action: DecisionAction
  selected_fields?: string[]
}

export interface DecisionResult {
  candidate: CandidateSummary
  decision_id: string
  post_version: number
  result_revision_id: string | null
}

export const blogAIApi = {
  // Submit an optimization bound to the current revision; returns the Job (202).
  // A duplicate (identical still-active request) returns the existing Job.
  optimize: (postId: string, body: OptimizeBody) =>
    api.post<AsyncJob>(`/posts/${postId}/optimize`, body),
  getRun: (runId: string) => api.get<AIRun>(`/blog/ai/runs/${runId}`),
  cancelRun: (runId: string) => api.post<AsyncJob>(`/blog/ai/runs/${runId}/cancel`),
  listCandidates: (postId: string) =>
    api.get<CandidateSummary[]>(`/posts/${postId}/candidates`),
  compareCandidate: (candidateId: string) =>
    api.get<CandidateCompare>(`/blog/ai/candidates/${candidateId}`),
  decideCandidate: (candidateId: string, body: DecisionBody) =>
    api.post<DecisionResult>(`/blog/ai/candidates/${candidateId}/decide`, body),
}
