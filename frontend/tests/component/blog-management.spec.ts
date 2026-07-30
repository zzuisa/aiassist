import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/blogQueries', async () => {
  const actual = (await vi.importActual('@/api/blogQueries')) as Record<string, unknown>
  return {
    ...actual,
    articlesApi: {
      list: vi.fn(), triage: vi.fn(), batch: vi.fn(), merge: vi.fn(), export: vi.fn(),
    },
  }
})
vi.mock('@/api/posts', async () => {
  const actual = (await vi.importActual('@/api/posts')) as Record<string, unknown>
  return { ...actual, postsApi: { get: vi.fn(), list: vi.fn() } }
})
const routerPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: routerPush }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { articlesApi } from '@/api/blogQueries'
import { postsApi } from '@/api/posts'
import PostBatchActionBar from '@/modules/posts/PostBatchActionBar.vue'
import TriagePage from '@/modules/posts/TriagePage.vue'
import TriageMergeDialog from '@/modules/posts/TriageMergeDialog.vue'

beforeEach(() => vi.clearAllMocks())

describe('PostBatchActionBar', () => {
  it('runs a batch op and reports partial failure', async () => {
    vi.mocked(articlesApi.batch).mockResolvedValue({
      results: [{ id: 'a', ok: true }, { id: 'b', ok: false, error: 'not_found' }],
      succeeded: 1, failed: 1,
    })
    const w = mount(PostBatchActionBar, { props: { selectedIds: ['a', 'b'] } })
    expect(w.text()).toContain('已选 2 项')

    await w.find('.primary').trigger('click')
    await Promise.resolve()

    expect(articlesApi.batch).toHaveBeenCalledWith(['a', 'b'], 'set_class', { content_class: 'technical' })
    expect(w.find('.summary').text()).toContain('成功 1 项，失败 1 项')
    expect(w.find('.fail-detail').exists()).toBe(true)
  })

  it('switches op to archive without a class param', async () => {
    vi.mocked(articlesApi.batch).mockResolvedValue({ results: [{ id: 'a', ok: true }], succeeded: 1, failed: 0 })
    const w = mount(PostBatchActionBar, { props: { selectedIds: ['a'] } })
    await w.findAll('select')[0].setValue('archive')
    await w.find('.primary').trigger('click')
    await Promise.resolve()
    expect(articlesApi.batch).toHaveBeenCalledWith(['a'], 'archive', {})
  })
})

describe('TriagePage', () => {
  const triageFixture = {
    items: [
      { id: 'q', title: '快记', reason: 'quick', content_class: 'quick', content_status: 'draft', preview: 'p', source_count: 0, updated_at: '' },
      { id: 'f', title: '失败项', reason: 'failed', content_class: 'essay', content_status: 'pending_parse', preview: 'p', source_count: 1, updated_at: '' },
    ],
    counts_by_reason: { quick: 1, failed: 1, stale: 0, draft: 0 },
  }

  it('renders items with reasons and enables merge on two selections', async () => {
    vi.mocked(articlesApi.triage).mockResolvedValue(triageFixture as never)
    const w = mount(TriagePage)
    await flushPromises()

    expect(w.text()).toContain('快记')
    expect(w.text()).toContain('失败项')
    expect(w.find('.merge-cta').exists()).toBe(false)

    const boxes = w.findAll('.item input[type="checkbox"]')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    expect(w.find('.merge-cta').exists()).toBe(true)
  })

  it('filters by reason chip', async () => {
    vi.mocked(articlesApi.triage).mockResolvedValue(triageFixture as never)
    const w = mount(TriagePage)
    await flushPromises()

    vi.mocked(articlesApi.triage).mockResolvedValue({
      items: [triageFixture.items[0]], counts_by_reason: triageFixture.counts_by_reason,
    } as never)
    // The 快速记录 chip is the second chip (after 全部).
    await w.findAll('.chip')[1].trigger('click')
    await flushPromises()
    expect(articlesApi.triage).toHaveBeenLastCalledWith('quick')
  })
})

describe('TriageMergeDialog', () => {
  it('merges in the chosen order under the primary version', async () => {
    vi.mocked(postsApi.get).mockResolvedValue({ id: 'p', version: 5 } as never)
    vi.mocked(articlesApi.merge).mockResolvedValue({ id: 'p', markdown: '', version: 6 })
    const w = mount(TriageMergeDialog, {
      props: { primary: { id: 'p', title: '主' }, secondary: { id: 's', title: '副' } },
    })
    await w.findAll('select')[0].setValue('secondary_first')
    await w.find('.primary').trigger('click')
    await Promise.resolve(); await Promise.resolve()

    expect(articlesApi.merge).toHaveBeenCalledWith(expect.objectContaining({
      primary_id: 'p', secondary_id: 's', primary_version: 5, order: 'secondary_first',
    }))
    expect(w.emitted('merged')!.at(-1)).toEqual(['p'])
  })
})
