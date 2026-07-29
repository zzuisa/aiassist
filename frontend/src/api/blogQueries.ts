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
