import type { AsyncJob } from '@/api/types'

// Business-language names for job types (FR-094: no queue/executor jargon).
const JOB_LABELS: Record<string, string> = {
  'voice.transcribe': '语音识别',
  'capture.process': '图片处理',
  'capture.analyze': '图片分析',
  'image.process': '图片处理',
  'blog.generate': '博客生成',
  'schedule.preview': '日程调整预览',
  'assistant.plan_today': '安排今天',
  'assistant.adjust_week': '调整本周',
  'assistant.summarize_day': '总结今天',
  search: '搜索索引',
}

export function jobLabel(job: Pick<AsyncJob, 'job_type'>): string {
  if (JOB_LABELS[job.job_type]) return JOB_LABELS[job.job_type]
  // Fallback: prefix before the dot, humanized.
  const prefix = job.job_type.split('.')[0]
  return (
    {
      voice: '语音',
      capture: '收藏',
      image: '图片',
      blog: '博客',
      schedule: '日程',
      assistant: 'AI 助手',
      search: '搜索',
      llm: 'AI',
    }[prefix] ?? '后台任务'
  )
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

export function formatDuration(start?: string | null, end?: string | null): string {
  if (!start) return ''
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return ''
  const secs = Math.round((e - s) / 1000)
  if (secs < 60) return `${secs} 秒`
  return `${Math.floor(secs / 60)} 分 ${secs % 60} 秒`
}
