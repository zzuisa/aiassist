// Shared blog-job display helpers (spec 005, US3, T079).
//
// The backend derives a presentation-only `display_status` for blog jobs; this
// maps it (and the generic status fallback) to a Chinese label + a semantic tone
// used for badges in the Job list/detail views. Nothing here is persisted.
import type { AsyncJob } from '@/api/types'

export type Tone = 'queued' | 'processing' | 'review' | 'done' | 'failed' | 'neutral'

const DISPLAY_LABELS: Record<string, { label: string; tone: Tone }> = {
  ai_queued: { label: '排队中', tone: 'queued' },
  ai_processing: { label: '优化中', tone: 'processing' },
  ai_review: { label: '待审核', tone: 'review' },
  capturing: { label: '抓取中', tone: 'processing' },
  parsing: { label: '解析中', tone: 'processing' },
  aggregating: { label: '统计中', tone: 'processing' },
  failed: { label: '失败', tone: 'failed' },
  cancelled: { label: '已取消', tone: 'neutral' },
  completed: { label: '已完成', tone: 'done' },
}

const STATUS_FALLBACK: Record<string, { label: string; tone: Tone }> = {
  pending: { label: '等待中', tone: 'queued' },
  queued: { label: '排队中', tone: 'queued' },
  processing: { label: '处理中', tone: 'processing' },
  waiting_user: { label: '待审核', tone: 'review' },
  completed: { label: '已完成', tone: 'done' },
  failed: { label: '失败', tone: 'failed' },
  cancelled: { label: '已取消', tone: 'neutral' },
}

export function jobDisplay(job: Pick<AsyncJob, 'status' | 'display_status'>): {
  label: string
  tone: Tone
} {
  if (job.display_status && DISPLAY_LABELS[job.display_status]) {
    return DISPLAY_LABELS[job.display_status]
  }
  return STATUS_FALLBACK[job.status] ?? { label: job.status, tone: 'neutral' }
}

const TYPE_LABELS: Record<string, string> = {
  'blog.capture': '内容采集',
  'blog.parse': '内容解析',
  'blog.generate': 'AI 优化',
  'blog.optimize': 'AI 优化',
  'blog.wordcloud': '词云统计',
}

export function jobTypeLabel(jobType: string): string {
  return TYPE_LABELS[jobType] ?? jobType
}
