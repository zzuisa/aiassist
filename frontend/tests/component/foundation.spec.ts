import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useJobsStore } from '@/stores/jobs'
import { useAuthStore } from '@/stores/auth'
import { setCsrfToken, getCsrfToken } from '@/api/client'

beforeEach(() => {
  setActivePinia(createPinia())
  setCsrfToken(null)
})

describe('jobs store — SSE event handling', () => {
  it('applies a job event and exposes it as active', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({
      job_id: 'j1',
      job_version: 2,
      job_type: 'capture.analyze',
      status: 'processing',
      progress: 40,
    })
    expect(jobs.activeJobs).toHaveLength(1)
    expect(jobs.activeJobs[0].progress).toBe(40)
  })

  it('deduplicates by job_version (ignores stale/duplicate)', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({ job_id: 'j1', job_version: 3, status: 'processing', progress: 60 })
    jobs.applyJobEvent({ job_id: 'j1', job_version: 2, status: 'processing', progress: 10 })
    jobs.applyJobEvent({ job_id: 'j1', job_version: 3, status: 'processing', progress: 10 })
    expect(jobs.activeJobs[0].progress).toBe(60)
  })

  it('moves a job out of active when it completes', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({ job_id: 'j1', job_version: 1, status: 'processing', progress: 50 })
    jobs.applyJobEvent({ job_id: 'j1', job_version: 2, status: 'completed', progress: 100 })
    expect(jobs.activeJobs).toHaveLength(0)
  })

  it('counts unread notifications', () => {
    const jobs = useJobsStore()
    jobs.applyNotification({ notification_id: 'n1', type: 'task_due', title: 'x', created_at: '' })
    jobs.applyNotification({ notification_id: 'n2', type: 'task_due', title: 'y', created_at: '' })
    expect(jobs.unreadCount).toBe(2)
  })

  it('clear() resets jobs and notifications', () => {
    const jobs = useJobsStore()
    jobs.applyJobEvent({ job_id: 'j1', job_version: 1, status: 'processing', progress: 1 })
    jobs.applyNotification({ notification_id: 'n1', type: 't', title: 'x', created_at: '' })
    jobs.clear()
    expect(jobs.activeJobs).toHaveLength(0)
    expect(jobs.unreadCount).toBe(0)
  })
})

describe('auth store', () => {
  it('logout clears the user and CSRF token', async () => {
    const auth = useAuthStore()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    setCsrfToken('abc')
    // Seed a user directly.
    auth.$patch({ user: { id: '1', email: 'a@b.c', display_name: 'A', timezone: 'UTC', locale: 'zh-CN' } })
    await auth.logout()
    expect(auth.user).toBeNull()
    expect(getCsrfToken()).toBeNull()
    vi.unstubAllGlobals()
  })

  it('fetchMe sets initialized even on 401', async () => {
    const auth = useAuthStore()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 401, title: 'x', type: 'about:blank' }), {
        status: 401,
        headers: { 'content-type': 'application/problem+json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await auth.fetchMe()
    expect(auth.initialized).toBe(true)
    expect(auth.user).toBeNull()
    vi.unstubAllGlobals()
  })
})
