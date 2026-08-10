import { api } from '@/api/client'

export interface PostSourceSummary {
  id: string
  source_type: string
  status: string
  original_url?: string | null
  original_title?: string | null
  captured_at?: string | null
}

export interface PostAiSummary {
  display_status: string | null
  optimization_count: number
  first_optimized_at?: string | null
  last_optimized_at?: string | null
  latest_job_id?: string | null
  pending_candidate_id?: string | null
}

export interface Post {
  id: string
  title: string
  subtitle: string | null
  summary: string | null
  markdown: string
  status: 'draft' | 'private' | 'published'
  slug: string | null
  content_status: string
  content_class: string
  content_type_id: string | null
  category_id: string | null
  tag_ids: string[]
  keyword_ids: string[]
  language: string
  editor_mode: string
  occurred_at: string | null
  location: string | null
  project: string | null
  structured_data: Record<string, unknown>
  source_summary: PostSourceSummary[]
  ai_summary: PostAiSummary | null
  version: number
  current_revision_id: string | null
  created_at: string
  updated_at: string
  published_at: string | null
}

// Every field a PATCH may carry (all optional; version is added at call time).
export interface PostPatch {
  title?: string
  subtitle?: string | null
  summary?: string | null
  markdown?: string
  content_status?: string
  content_class?: string
  content_type_id?: string | null
  category_id?: string | null
  tag_ids?: string[]
  keyword_ids?: string[]
  language?: string
  editor_mode?: string
  occurred_at?: string | null
  location?: string | null
  project?: string | null
  structured_data?: Record<string, unknown>
}

export interface RevisionDiff {
  base_revision_id: string
  candidate_revision_id: string
  unified_diff: string
}

export interface RevisionSummary {
  id: string
  post_id: string
  source: string
  version: number
  change_summary: string | null
  created_at: string
  applied_at: string | null
}

// Structured body diff (spec 005, US4) — mirrors diffing.body_diff.
export interface BodyDiff {
  from_label: string
  to_label: string
  unified_diff: string
  hunks: Array<{
    op: 'replace' | 'delete' | 'insert'
    old_start: number
    old_lines: string[]
    new_start: number
    new_lines: string[]
  }>
  changed: boolean
}

export interface RevisionCompare {
  from_revision_id: string
  to_revision_id: string
  body_diff: BodyDiff
  field_diff: Record<string, { base: unknown; current: unknown; candidate: unknown; status: string }>
}

export const postsApi = {
  list: () => api.get<Post[]>('/posts'),
  get: (id: string) => api.get<Post>(`/posts/${id}`),
  create: (title: string, markdown: string, sourceRefs: Array<{ type: string; id: string }> = []) =>
    api.post<Post>('/posts', { title, markdown, source_refs: sourceRefs }),
  patch: (id: string, patch: PostPatch, version: number) =>
    api.patch<Post>(`/posts/${id}`, { ...patch, version }),
  save: (id: string, title: string, markdown: string, version: number) =>
    api.patch<Post>(`/posts/${id}`, { title, markdown, version }),
  generate: (id: string, scenario: string, instruction?: string) =>
    api.post(`/posts/${id}/generate`, { scenario, instruction }),
  diff: (id: string, revisionId: string) =>
    api.get<RevisionDiff>(`/posts/${id}/revisions/${revisionId}/diff`),
  applyRevision: (id: string, revisionId: string) =>
    api.post<Post>(`/posts/${id}/revisions/${revisionId}/apply`),
  publish: (id: string, published: boolean, version: number) =>
    api.post<Post>(`/posts/${id}/publish`, { published, version }),
  remove: (id: string) => api.del<void>(`/posts/${id}`),
  // Version timeline + compare + restore (spec 005, US4, T091).
  listRevisions: (id: string) =>
    api.get<RevisionSummary[]>(`/posts/${id}/revisions`),
  compareRevisions: (id: string, fromRevision: string, toRevision: string) =>
    api.get<RevisionCompare>(
      `/posts/${id}/revisions/compare`,
      { from_revision: fromRevision, to_revision: toRevision },
    ),
  restoreRevision: (id: string, revisionId: string, version: number) =>
    api.post<Post>(`/posts/${id}/revisions/${revisionId}/restore`, { version }),
}
