// Blog taxonomy client. Categories are the primary structured organization
// surface; tags and keywords remain separate concepts and can be added later.
import { api } from '@/api/client'

export interface TaxonomyItem {
  id: string
  kind: 'category' | 'tag' | 'keyword'
  name: string
  description: string | null
  parent_id: string | null
  aliases: string[]
  color: string | null
  enabled: boolean
  stop_word: boolean
  usage_count: number
}

export interface TaxonomyCreate {
  name: string
  description?: string | null
  parent_id?: string | null
  aliases?: string[]
  color?: string | null
  enabled?: boolean
  stop_word?: boolean
}

export interface TaxonomyJob {
  id: string
  job_type: string
  status: string
  progress: number
}

export const taxonomyApi = {
  list: (kind: TaxonomyItem['kind'], enabled?: boolean) =>
    api.get<TaxonomyItem[]>(`/blog/taxonomy/${kind}`, enabled === undefined ? undefined : { enabled }),
  create: (kind: TaxonomyItem['kind'], body: TaxonomyCreate) =>
    api.post<TaxonomyItem>(`/blog/taxonomy/${kind}`, body),
  update: (kind: TaxonomyItem['kind'], id: string, body: Partial<TaxonomyCreate>) =>
    api.patch<TaxonomyItem>(`/blog/taxonomy/${kind}/${id}`, body),
  merge: (kind: TaxonomyItem['kind'], sourceId: string, targetId: string) =>
    api.post<TaxonomyItem | TaxonomyJob>(`/blog/taxonomy/${kind}/merge`, {
      source_id: sourceId, target_id: targetId,
    }),
  recomputeKeywords: () => api.post<TaxonomyJob>('/blog/taxonomy/keyword/recompute'),
}
