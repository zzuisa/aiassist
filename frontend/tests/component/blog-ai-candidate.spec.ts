import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'

// Mock the AI client so the dialog never hits the network. Keep the real
// classifier/types export so the component's imports still resolve.
vi.mock('@/api/blogAI', async () => {
  const actual = (await vi.importActual('@/api/blogAI')) as Record<string, unknown>
  return {
    ...actual,
    blogAIApi: {
      optimize: vi.fn(), getRun: vi.fn(), cancelRun: vi.fn(),
      listCandidates: vi.fn(), compareCandidate: vi.fn(), decideCandidate: vi.fn(),
    },
  }
})
const routerPush = vi.fn()
// Neutralise router usage in the pages.
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: { id: 'p1', candidateId: 'c1' } }),
  useRouter: () => ({ push: routerPush }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { blogAIApi } from '@/api/blogAI'
import { api } from '@/api/client'
import OptimizePostDialog from '@/modules/posts/OptimizePostDialog.vue'
import BlogJobsPage from '@/modules/posts/BlogJobsPage.vue'
import BlogJobDetailPage from '@/modules/posts/BlogJobDetailPage.vue'
import CandidateComparePage from '@/modules/posts/CandidateComparePage.vue'
import { jobDisplay, jobTypeLabel } from '@/modules/posts/blogJobStatus'
import { useJobsStore } from '@/stores/jobs'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('OptimizePostDialog', () => {
  it('submits an optimization bound to the current version and emits the job id', async () => {
    vi.mocked(blogAIApi.optimize).mockResolvedValue({ id: 'job-9' } as never)
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 7 } })

    await w.find('.primary').trigger('click')
    await Promise.resolve()

    expect(blogAIApi.optimize).toHaveBeenCalledWith('p1', {
      post_version: 7,
      optimization_type: 'full',
      scope: 'all',
      selected_fields: [],
      skill_id: null,
      model_key: null,
      instruction: null,
    })
    expect(w.emitted('submitted')!.at(-1)).toEqual(['job-9'])
  })

  it('requires and passes selected fields when scope is selected_fields', async () => {
    vi.mocked(blogAIApi.optimize).mockResolvedValue({ id: 'job-1' } as never)
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 2 } })

    // Second select is the scope control.
    await w.findAll('select')[1].setValue('selected_fields')
    // With no fields chosen the submit button is disabled.
    expect((w.find('.primary').element as HTMLButtonElement).disabled).toBe(true)

    await w.find('input[aria-label="指定字段"]').setValue('title, summary')
    await w.find('.primary').trigger('click')
    await Promise.resolve()

    const body = vi.mocked(blogAIApi.optimize).mock.calls[0][1]
    expect(body.scope).toBe('selected_fields')
    expect(body.selected_fields).toEqual(['title', 'summary'])
  })

  it('surfaces a version conflict without emitting', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(blogAIApi.optimize).mockRejectedValue(
      new ApiError({ type: '', title: '', status: 409, code: 'version_conflict' }),
    )
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 1 } })
    await w.find('.primary').trigger('click')
    await Promise.resolve()
    expect(w.find('.opt-error').text()).toContain('文章已被修改')
    expect(w.emitted('submitted')).toBeUndefined()
  })
})

describe('blogJobStatus helper', () => {
  it('maps derived display statuses to tone + label', () => {
    expect(jobDisplay({ status: 'processing', display_status: 'ai_processing' })).toEqual({
      label: '优化中',
      tone: 'processing',
    })
    expect(jobDisplay({ status: 'completed', display_status: 'ai_review' })).toEqual({
      label: '待审核',
      tone: 'review',
    })
  })

  it('falls back to the generic status when no display status is set', () => {
    expect(jobDisplay({ status: 'failed', display_status: null }).tone).toBe('failed')
  })

  it('labels blog job types in business language', () => {
    expect(jobTypeLabel('blog.optimize')).toBe('AI 优化')
  })
})

describe('BlogJobsPage', () => {
  it('lists only blog jobs with live status, newest first', async () => {
    const store = useJobsStore()
    vi.spyOn(store, 'connect').mockImplementation(() => {})
    vi.spyOn(store, 'refreshFromRest').mockResolvedValue()
    store.applyJobEvent({
      job_id: 'b1', job_version: 1, job_type: 'blog.optimize', status: 'processing',
      progress: 30, scope: 'blog', display_status: 'ai_processing', created_at: '2026-01-01',
    })
    store.applyJobEvent({
      job_id: 't1', job_version: 1, job_type: 'voice.transcribe', status: 'processing',
      progress: 10, created_at: '2026-01-02',
    })

    const w = mount(BlogJobsPage)
    await Promise.resolve()

    expect(w.text()).toContain('AI 优化')
    expect(w.text()).toContain('优化中')
    expect(w.text()).not.toContain('voice.transcribe')
  })

  it('shows an empty state when there are no blog jobs', () => {
    const store = useJobsStore()
    vi.spyOn(store, 'connect').mockImplementation(() => {})
    vi.spyOn(store, 'refreshFromRest').mockResolvedValue()
    const w = mount(BlogJobsPage)
    expect(w.find('.empty').exists()).toBe(true)
  })
})

describe('BlogJobDetailPage', () => {
  it('offers retry only for a retryable failed job', async () => {
    const store = useJobsStore()
    vi.spyOn(store, 'connect').mockImplementation(() => {})
    store.applyJobEvent({
      job_id: 'p1', job_version: 1, job_type: 'blog.optimize', status: 'failed',
      progress: 50, scope: 'blog', display_status: 'failed',
      error: { code: 'TIMEOUT', message: '稍后可重试', retryable: true },
    })
    vi.spyOn(api, 'get').mockResolvedValue(store.getJob('p1') as never)

    const w = mount(BlogJobDetailPage)
    await Promise.resolve()

    expect(w.text()).toContain('失败')
    expect(w.text()).toContain('稍后可重试')
    expect(w.find('.primary').text()).toContain('重试')
  })
})

function compareFixture() {
  return {
    candidate: { id: 'c1', post_id: 'p1', status: 'pending' },
    post_version: 3,
    field_diff: {
      summary: { base: 'b', current: 'b', candidate: 'AI摘要', status: 'ai_only' },
      title: { base: 'b', current: '用户标题', candidate: 'AI标题', status: 'conflict' },
      markdown: { base: 'b', current: 'b', candidate: 'AI正文', status: 'ai_only' },
    },
    body_diff: {
      from_label: 'current', to_label: 'candidate',
      unified_diff: '--- current\n+++ candidate\n-b\n+AI正文', changed: true,
    },
    conflicts: ['title'],
    validation: {},
  }
}

describe('CandidateComparePage', () => {
  it('orders conflicts first, warns, and pre-selects only safe AI changes', async () => {
    vi.mocked(blogAIApi.compareCandidate).mockResolvedValue(compareFixture() as never)
    const w = mount(CandidateComparePage)
    await Promise.resolve()
    await Promise.resolve()

    // Risk-first: the conflict field renders before the ai_only fields.
    const rows = w.findAll('.field-row')
    expect(rows[0].attributes('data-status')).toBe('conflict')
    expect(w.find('.conflict-banner').exists()).toBe(true)
    // Conflicting field is NOT pre-selected; the two ai_only fields are.
    expect(w.find('.impact strong').text()).toBe('2')
  })

  it('applies only the selected fields under the current version', async () => {
    vi.mocked(blogAIApi.compareCandidate).mockResolvedValue(compareFixture() as never)
    vi.mocked(blogAIApi.decideCandidate).mockResolvedValue(
      { candidate: { post_id: 'p1' }, decision_id: 'd1', post_version: 4, result_revision_id: 'r1' } as never,
    )
    const w = mount(CandidateComparePage)
    await Promise.resolve()
    await Promise.resolve()

    await w.find('.primary').trigger('click')
    await Promise.resolve()

    const [candId, body] = vi.mocked(blogAIApi.decideCandidate).mock.calls[0]
    expect(candId).toBe('c1')
    expect(body.post_version).toBe(3)
    expect(body.action).toBe('apply_fields')
    expect(new Set(body.selected_fields)).toEqual(new Set(['summary', 'markdown']))
    expect(routerPush).toHaveBeenCalled()
  })

  it('rejects the candidate without selecting fields', async () => {
    vi.mocked(blogAIApi.compareCandidate).mockResolvedValue(compareFixture() as never)
    vi.mocked(blogAIApi.decideCandidate).mockResolvedValue(
      { candidate: { post_id: 'p1' }, decision_id: 'd1', post_version: 3, result_revision_id: null } as never,
    )
    const w = mount(CandidateComparePage)
    await Promise.resolve()
    await Promise.resolve()

    await w.find('.ghost.danger').trigger('click')
    await Promise.resolve()

    expect(vi.mocked(blogAIApi.decideCandidate).mock.calls[0][1].action).toBe('reject')
  })
})
