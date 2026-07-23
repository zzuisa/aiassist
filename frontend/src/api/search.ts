import { api } from '@/api/client'

export interface SearchResultItem {
  entity: { type: string; id: string }
  title: string
  category?: string | null
  tags: string[]
  summary?: string | null
  thumbnail_asset_id?: string | null
  highlights: string[]
}

export interface SearchGroup {
  type: string
  items: SearchResultItem[]
}

export interface SearchResponse {
  query: string
  groups: SearchGroup[]
  index_pending_count: number
}

export const searchApi = {
  search: (q: string, types?: string) =>
    api.get<SearchResponse>('/search', types ? { q, types } : { q }),
}

export const TYPE_LABELS: Record<string, string> = {
  task: '任务',
  habit: '习惯',
  capture: '收藏',
  post: '博客',
}
