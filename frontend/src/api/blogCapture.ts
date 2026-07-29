// Blog capture API client (spec 005, US1, T040).
//
// Wraps the durable capture endpoints and maps typed errors so dialogs can show
// actionable messages (e.g. an unsafe URL vs. a transient failure). All calls go
// through the shared `api` wrapper (same-origin cookies + CSRF).

import { ApiError, api } from '@/api/client'

export type DetectedFormat =
  | 'plain'
  | 'markdown'
  | 'html'
  | 'rich'
  | 'url'
  | 'code'
  | 'image'
  | 'mixed'

export type UrlUsage =
  | 'bookmark'
  | 'summary_note'
  | 'reading_note'
  | 'technical_material'
  | 'travel_material'
  | 'personal_article'
  | 'triage'

export interface CapturePost {
  id: string
  title: string
  markdown: string
  content_status: string
  content_class: string
  content_type_id: string | null
  language: string
  version: number
  created_at: string
  updated_at: string
}

export interface CaptureSource {
  id: string
  post_id: string | null
  source_type: string
  status: string
  detected_format: string | null
  original_url: string | null
  original_title: string | null
  original_text: string | null
  normalized_markdown: string | null
  user_note: string | null
  metadata: Record<string, unknown>
  has_snapshot: boolean
  attempt_count: number
  captured_at: string | null
  error: { code: string; message: string; retryable: boolean } | null
}

export interface CaptureJob {
  id: string
  job_type: string
  status: string
  display_status?: string
  progress: number
  [key: string]: unknown
}

export interface CaptureResult {
  post: CapturePost
  source: CaptureSource
  job: CaptureJob | null
  warnings: string[]
}

export interface BlankCaptureBody {
  title?: string
  content_class?: string
  content_type_id?: string | null
  language?: string
}

export interface ClipboardCaptureBody {
  raw_content: string
  detected_format: DetectedFormat
  normalized_markdown?: string | null
  content_class?: string
  content_type_id?: string | null
  ai_enabled?: boolean
  skill_id?: string | null
  save_as_defaults?: boolean
}

export interface UrlCaptureBody {
  url: string
  note?: string | null
  usage?: UrlUsage
  content_class?: string
  content_type_id?: string | null
  ai_enabled?: boolean
  skill_id?: string | null
  save_as_defaults?: boolean
}

export interface QuickCaptureBody {
  content: string
  content_class?: string
  ai_enabled?: boolean
  save_and_continue?: boolean
}

// Stable, user-facing categories derived from backend Problem `code`s so dialogs
// can branch without matching on free-text messages.
export type CaptureErrorKind =
  | 'unsafe_url'
  | 'invalid_format'
  | 'too_large'
  | 'not_retryable'
  | 'conflict'
  | 'unknown'

const UNSAFE_URL_CODES = new Set([
  'scheme_not_allowed',
  'credentials_in_url',
  'no_host',
  'ip_not_public',
  'dns_failure',
])

export function classifyCaptureError(err: unknown): CaptureErrorKind {
  if (!(err instanceof ApiError)) return 'unknown'
  const code = err.code
  if (UNSAFE_URL_CODES.has(code)) return 'unsafe_url'
  if (code === 'invalid_detected_format' || err.status === 422) return 'invalid_format'
  if (err.status === 413 || code === 'response_too_large') return 'too_large'
  if (code === 'source_not_retryable' || code === 'not_url_source') return 'not_retryable'
  if (err.status === 409) return 'conflict'
  return 'unknown'
}

export const blogCaptureApi = {
  blank: (body: BlankCaptureBody) =>
    api.post<CaptureResult>('/posts/captures/blank', body),
  clipboard: (body: ClipboardCaptureBody) =>
    api.post<CaptureResult>('/posts/captures/clipboard', body),
  url: (body: UrlCaptureBody) => api.post<CaptureResult>('/posts/captures/url', body),
  quick: (body: QuickCaptureBody) =>
    api.post<CaptureResult>('/posts/captures/quick', body),
  getSource: (sourceId: string) => api.get<CaptureSource>(`/post-sources/${sourceId}`),
  retrySource: (sourceId: string) =>
    api.post<CaptureJob>(`/post-sources/${sourceId}/retry`),
  snapshotAccess: (sourceId: string) =>
    api.get<{ url: string; expires_at: string | null }>(
      `/post-sources/${sourceId}/snapshot-access`,
    ),
}
