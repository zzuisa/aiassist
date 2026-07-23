import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import type { AsyncJob, NotificationItem } from '@/api/types'

// Global jobs/notifications store fed by a single EventSource per tab. Events are
// deduplicated by id and applied only when job_version is newer (see sse.md).
export const useJobsStore = defineStore('jobs', () => {
  const jobs = ref<Map<string, AsyncJob>>(new Map())
  const jobVersions = ref<Map<string, number>>(new Map())
  const notifications = ref<NotificationItem[]>([])
  const connected = ref(false)
  const reconnecting = ref(false)
  let source: EventSource | null = null
  let lastEventId = ''

  const activeJobs = computed(() =>
    [...jobs.value.values()].filter((j) =>
      ['pending', 'queued', 'processing', 'waiting_user'].includes(j.status),
    ),
  )
  const failedJobs = computed(() =>
    [...jobs.value.values()].filter((j) => j.status === 'failed'),
  )
  const unreadCount = computed(
    () => notifications.value.filter((n) => n.status === 'unread').length,
  )

  function applyJobEvent(data: Record<string, unknown>): void {
    const id = data.job_id as string
    const version = (data.job_version as number) ?? 0
    if (!id) return
    const known = jobVersions.value.get(id) ?? -1
    if (version <= known) return // duplicate or stale
    jobVersions.value.set(id, version)
    const existing = jobs.value.get(id)
    jobs.value.set(id, {
      ...(existing ?? ({} as AsyncJob)),
      id,
      job_type: (data.job_type as string) ?? existing?.job_type ?? '',
      status: data.status as AsyncJob['status'],
      progress: (data.progress as number) ?? existing?.progress ?? 0,
      current_step: (data.current_step as string) ?? null,
      error: (data.error as AsyncJob['error']) ?? existing?.error ?? null,
      retry_count: (data.retry_count as number) ?? existing?.retry_count ?? 0,
      priority: existing?.priority ?? 0,
      trace_id: (data.trace_id as string) ?? existing?.trace_id ?? null,
      created_at: (data.created_at as string) ?? existing?.created_at ?? (data.updated_at as string),
      started_at: (data.started_at as string) ?? existing?.started_at ?? null,
      updated_at: (data.updated_at as string) ?? existing?.updated_at ?? '',
      finished_at: (data.finished_at as string) ?? existing?.finished_at ?? null,
      entity: (data.entity as AsyncJob['entity']) ?? existing?.entity ?? null,
    })
  }

  function applySnapshot(data: Record<string, unknown>): void {
    const snapshotJobs = (data.jobs as Array<Record<string, unknown>>) ?? []
    for (const j of snapshotJobs) {
      applyJobEvent(j)
    }
  }

  function applyNotification(data: Record<string, unknown>): void {
    notifications.value.unshift({
      id: data.notification_id as string,
      type: data.type as string,
      title: data.title as string,
      body: (data.body as string) ?? '',
      status: 'unread',
      entity: (data.entity as NotificationItem['entity']) ?? null,
      created_at: data.created_at as string,
    })
  }

  async function refreshFromRest(): Promise<void> {
    const list = await api.get<AsyncJob[]>('/jobs')
    for (const j of list) {
      jobVersions.value.set(j.id, -1)
      applyJobEvent({ ...j, job_id: j.id, job_version: 1 })
    }
  }

  function connect(): void {
    if (source) return
    source = new EventSource('/api/v1/events/jobs', { withCredentials: true })
    source.addEventListener('open', () => {
      connected.value = true
      reconnecting.value = false
    })
    source.addEventListener('jobs.snapshot', (e) => {
      lastEventId = (e as MessageEvent).lastEventId || lastEventId
      applySnapshot(JSON.parse((e as MessageEvent).data))
    })
    for (const name of ['job.updated', 'job.waiting_user', 'job.completed', 'job.failed', 'job.cancelled']) {
      source.addEventListener(name, (e) => {
        lastEventId = (e as MessageEvent).lastEventId || lastEventId
        applyJobEvent(JSON.parse((e as MessageEvent).data))
      })
    }
    source.addEventListener('notification.created', (e) => {
      lastEventId = (e as MessageEvent).lastEventId || lastEventId
      applyNotification(JSON.parse((e as MessageEvent).data))
    })
    source.addEventListener('error', () => {
      connected.value = false
      reconnecting.value = true
      // EventSource reconnects automatically with Last-Event-ID.
    })
  }

  function disconnect(): void {
    source?.close()
    source = null
    connected.value = false
  }

  function clear(): void {
    disconnect()
    jobs.value.clear()
    jobVersions.value.clear()
    notifications.value = []
    lastEventId = ''
  }

  return {
    jobs,
    notifications,
    connected,
    reconnecting,
    activeJobs,
    failedJobs,
    unreadCount,
    applyJobEvent,
    applySnapshot,
    applyNotification,
    refreshFromRest,
    connect,
    disconnect,
    clear,
  }
})
