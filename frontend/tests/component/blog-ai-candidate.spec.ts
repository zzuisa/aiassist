import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

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
vi.mock('@/api/blogSkills', () => ({
  blogSkillsApi: { list: vi.fn().mockResolvedValue([]) },
}))
vi.mock('@/api/settings', () => ({
  settingsApi: { get: vi.fn() },
}))
const routerPush = vi.fn()
// Neutralise router usage in the pages.
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: { id: 'p1', candidateId: 'c1' } }),
  useRouter: () => ({ push: routerPush }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { blogAIApi } from '@/api/blogAI'
import { api } from '@/api/client'
import { settingsApi } from '@/api/settings'
import OptimizePostDialog from '@/modules/posts/OptimizePostDialog.vue'
import BlogJobsPage from '@/modules/posts/BlogJobsPage.vue'
import BlogJobDetailPage from '@/modules/posts/BlogJobDetailPage.vue'
import CandidateComparePage from '@/modules/posts/CandidateComparePage.vue'
import { jobDisplay, jobTypeLabel } from '@/modules/posts/blogJobStatus'
import { useJobsStore } from '@/stores/jobs'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.mocked(settingsApi.get).mockResolvedValue({
    ai_optimization: {
      default_provider: 'radio',
      version: 1,
      providers: [],
    },
  } as never)
})

describe('OptimizePostDialog', () => {
  it('submits an optimization bound to the current version and emits the job', async () => {
    const submittedJob = { id: 'job-9', status: 'queued' }
    vi.mocked(blogAIApi.optimize).mockResolvedValue(submittedJob as never)
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 7 } })

    await flushPromises()
    await w.find('.primary').trigger('click')
    await Promise.resolve()

    expect(blogAIApi.optimize).toHaveBeenCalledWith('p1', {
      post_version: 7,
      optimization_type: 'language',
      scope: 'body',
      selected_fields: [],
      skill_id: null,
      provider_key: 'radio',
      model_key: null,
      instruction: null,
    })
    expect(w.emitted('submitted')!.at(-1)).toEqual([submittedJob])
  })

  it('requires and passes selected fields when scope is selected_fields', async () => {
    vi.mocked(blogAIApi.optimize).mockResolvedValue({ id: 'job-1' } as never)
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 2 } })

    await flushPromises()
    await w.find('select[aria-label="AI 优化服务"]').setValue('aiassist')
    await w.find('select[aria-label="范围"]').setValue('selected_fields')
    // With no fields chosen the submit button is disabled.
    expect((w.find('.primary').element as HTMLButtonElement).disabled).toBe(true)

    await w.find('input[aria-label="指定字段"]').setValue('title, summary')
    await w.find('.primary').trigger('click')
    await Promise.resolve()

    const body = vi.mocked(blogAIApi.optimize).mock.calls[0][1]
    expect(body.scope).toBe('selected_fields')
    expect(body.selected_fields).toEqual(['title', 'summary'])
    expect(body.provider_key).toBe('aiassist')
  })

  it('loads AI Assist as the user configured default', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue({
      ai_optimization: {
        default_provider: 'aiassist',
        version: 2,
        providers: [],
      },
    } as never)
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 3 } })
    await flushPromises()
    expect((w.find('select[aria-label="AI 优化服务"]').element as HTMLSelectElement).value)
      .toBe('aiassist')
    expect(w.text()).toContain('高级选项')
  })

  it('surfaces a version conflict without emitting', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(blogAIApi.optimize).mockRejectedValue(
      new ApiError({ type: '', title: '', status: 409, code: 'version_conflict' }),
    )
    const w = mount(OptimizePostDialog, { props: { postId: 'p1', postVersion: 1 } })
    await flushPromises()
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
      current_step: 'Radio 正在生成优化内容',
      result: { context: { post_title: '并行优化文章', provider_key: 'radio' } },
    })
    store.applyJobEvent({
      job_id: 't1', job_version: 1, job_type: 'voice.transcribe', status: 'processing',
      progress: 10, created_at: '2026-01-02',
    })

    const w = mount(BlogJobsPage)
    await Promise.resolve()

    expect(w.text()).toContain('AI 优化')
    expect(w.text()).toContain('优化中')
    expect(w.text()).toContain('并行优化文章')
    expect(w.text()).toContain('Radio')
    expect(w.text()).toContain('1 个进行中')
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

  it('shows a human-readable body review instead of only a code diff', async () => {
    vi.mocked(blogAIApi.compareCandidate).mockResolvedValue(compareFixture() as never)
    const w = mount(CandidateComparePage)
    await Promise.resolve()
    await Promise.resolve()

    expect(w.find('.body-review').text()).toContain('具体改了什么')
    expect(w.find('.change-pane--removed').text()).toContain('b')
    expect(w.find('.change-pane--added').text()).toContain('AI正文')

    await w.findAll('[role="tab"]')[1].trigger('click')
    expect(w.find('.preview-card--candidate').text()).toContain('AI正文')
    expect(w.find('.preview-card').text()).toContain('不会被修改')
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
