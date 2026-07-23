import { api } from '@/api/client'

export interface Post {
  id: string
  title: string
  markdown: string
  status: 'draft' | 'private' | 'published'
  slug: string | null
  version: number
  current_revision_id: string | null
  created_at: string
  published_at: string | null
}

export interface RevisionDiff {
  base_revision_id: string
  candidate_revision_id: string
  unified_diff: string
}

export const postsApi = {
  list: () => api.get<Post[]>('/posts'),
  get: (id: string) => api.get<Post>(`/posts/${id}`),
  create: (title: string, markdown: string, sourceRefs: Array<{ type: string; id: string }> = []) =>
    api.post<Post>('/posts', { title, markdown, source_refs: sourceRefs }),
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
}
