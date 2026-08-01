// Blog content-type + revision read/write clients (spec 005, US2, T054).

import { api } from '@/api/client'

export interface ContentType {
  id: string
  content_class: string
  key: string
  name: string
  description: string | null
  field_schema: Record<string, unknown>
  sort_order: number
  enabled: boolean
  schema_version: number
  created_at: string
  updated_at: string
}

export interface ContentTypeWrite {
  content_class: string
  key: string
  name: string
  description?: string | null
  field_schema: Record<string, unknown>
  sort_order?: number
  enabled: boolean
}

export interface PostRevisionSummary {
  id: string
  post_id: string
  source: string
  version: number
  change_summary: string | null
  created_at: string
  applied_at: string | null
}

export const contentTypesApi = {
  list: () => api.get<ContentType[]>('/blog/content-types'),
  create: (body: ContentTypeWrite) => api.post<ContentType>('/blog/content-types', body),
  update: (id: string, body: ContentTypeWrite) =>
    api.patch<ContentType>(`/blog/content-types/${id}`, body),
}

// --- Article management: list / triage / batch / merge (spec 005, US6, T121) ---

export interface ArticleRow {
  id: string
  title: string
  content_status: string
  content_class: string
  category_id: string | null
  status: string
  ai_state: 'none' | 'processing' | 'review' | 'failed' | 'optimized'
  source_count: number
  updated_at: string
  created_at: string
}

export interface ArticleListResult {
  items: ArticleRow[]
  next_cursor: number | null
  total: number
  counts_by_status: Record<string, number>
}

export interface BlogSearchItem {
  id: string
  title: string
  summary: string | null
  content_class: string
  category_id: string | null
  category: string | null
  tags: string[]
  content_status: string
  status: string
  matched_fields: string[]
  highlight: string | null
  occurred_at: string | null
  updated_at: string
}

export interface BlogSearchResult {
  query: string
  items: BlogSearchItem[]
  next_cursor: number | null
  total: number
}

export interface TimelineItem {
  id: string
  title: string
  summary: string | null
  content_class: string
  category_id: string | null
  status: string
  content_status: string
  time: string
  time_basis: 'occurred_at' | 'created_at'
}

export interface TimelineResult {
  items: TimelineItem[]
  next_cursor: number | null
  total: number
  time_basis: 'occurred_at_or_created_at'
}

export interface WordCloudTerm {
  id: string
  term: string
  count: number
}

export interface WordCloudSnapshot {
  id: string
  source_kind: 'tag' | 'keyword'
  filter: Record<string, unknown>
  terms: WordCloudTerm[]
  article_count: number
  status: 'ready' | 'stale' | 'failed'
  generated_at: string | null
  error_code: string | null
}

export interface WordCloudJob {
  id: string
  job_type: string
  status: string
}

export interface WordCloudRequest {
  source_kind: 'tag' | 'keyword'
  filter: Record<string, unknown>
  min_frequency?: number
  max_terms?: number
}

export interface ArticleFilters {
  content_status?: string
  content_class?: string
  category_id?: string
  tag_id?: string
  keyword_id?: string
  status?: string
  ai_state?: string
  search?: string
  include_inactive?: boolean
  sort?: string
  cursor?: number
  limit?: number
}

export type TriageReason = 'quick' | 'failed' | 'stale' | 'draft'

export interface TriageItem {
  id: string
  title: string
  reason: TriageReason
  content_class: string
  content_status: string
  preview: string
  source_count: number
  updated_at: string
}

export interface TriageResult {
  items: TriageItem[]
  counts_by_reason: Record<TriageReason, number>
}

export type BatchOp = 'set_class' | 'set_status' | 'set_category' | 'add_tags' | 'archive' | 'discard'

export interface BatchResult {
  results: Array<{ id: string; ok: boolean; error?: string }>
  succeeded: number
  failed: number
}

export interface MergeBody {
  primary_id: string
  secondary_id: string
  primary_version: number
  order?: 'primary_first' | 'secondary_first'
  title?: string | null
}

function toQuery(f: object): Record<string, string> {
  const q: Record<string, string> = {}
  for (const [k, v] of Object.entries(f)) {
    if (v !== undefined && v !== null && v !== '') q[k] = String(v)
  }
  return q
}

export const articlesApi = {
  list: (filters: ArticleFilters = {}) =>
    api.get<ArticleListResult>('/blog/articles', toQuery(filters)),
  search: (q: string, filters: Omit<ArticleFilters, 'search' | 'cursor'> = {}, cursor = 0) =>
    api.get<BlogSearchResult>('/blog/search', toQuery({ ...filters, q, cursor })),
  timeline: (filters: {
    year?: number
    month?: number
    content_class?: string
    category_id?: string
    cursor?: number
    limit?: number
  } = {}) => api.get<TimelineResult>('/blog/timeline', toQuery(filters)),
  triage: (reason?: TriageReason) =>
    api.get<TriageResult>('/blog/triage', reason ? { reason } : undefined),
  batch: (postIds: string[], op: BatchOp, params: Record<string, unknown> = {}) =>
    api.post<BatchResult>('/blog/articles/batch', { post_ids: postIds, op, params }),
  merge: (body: MergeBody) =>
    api.post<{ id: string; markdown: string; version: number }>('/blog/articles/merge', body),
  export: (id: string) =>
    api.get<{ filename: string; title: string; markdown: string }>(`/blog/articles/${id}/export`),
}

export const wordCloudApi = {
  get: (sourceKind: 'tag' | 'keyword', filter: Record<string, unknown>) =>
    api.get<WordCloudSnapshot | null>('/blog/word-cloud', {
      source_kind: sourceKind,
      filter: JSON.stringify(filter),
    }),
  rebuild: (body: WordCloudRequest) =>
    api.post<{ job: WordCloudJob; previous: WordCloudSnapshot | null }>('/blog/word-cloud', body),
}
