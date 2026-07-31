import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/blogQueries', () => ({
  articlesApi: { list: vi.fn(), search: vi.fn(), timeline: vi.fn() },
}))
vi.mock('@/api/blogTaxonomy', () => ({
  taxonomyApi: { list: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { articlesApi } from '@/api/blogQueries'
import { taxonomyApi } from '@/api/blogTaxonomy'
import PostListPage from '@/modules/posts/PostListPage.vue'
import TimelinePage from '@/modules/posts/TimelinePage.vue'

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(articlesApi.list).mockResolvedValue({
    items: [], next_cursor: null, total: 0, counts_by_status: {},
  } as never)
  vi.mocked(articlesApi.search).mockResolvedValue({
    query: 'CrashLoopBackOff',
    items: [{
      id: 'p1', title: '故障复盘', summary: '摘要', content_class: 'technical',
      category_id: 'c1', category: '技术复盘', tags: ['Kubernetes'],
      content_status: 'completed', status: 'draft', matched_fields: ['markdown', 'tags'],
      highlight: '…CrashLoopBackOff…', occurred_at: null, updated_at: '2025-04-12T10:00:00Z',
    }], next_cursor: null, total: 1,
  } as never)
  vi.mocked(taxonomyApi.list).mockResolvedValue([{
    id: 'c1', kind: 'category', name: '技术复盘', description: null, parent_id: null,
    aliases: [], color: null, enabled: true, stop_word: false, usage_count: 1,
  }] as never)
  vi.mocked(articlesApi.timeline).mockResolvedValue({
    items: [{
      id: 'p1', title: '年度复盘', summary: '时间轴摘要', content_class: 'technical',
      category_id: 'c1', status: 'draft', content_status: 'completed',
      time: '2025-04-12T10:00:00Z', time_basis: 'occurred_at',
    }], next_cursor: null, total: 1, time_basis: 'occurred_at_or_created_at',
  } as never)
})

describe('TimelinePage', () => {
  it('groups posts by month and labels the time basis', async () => {
    const wrapper = mount(TimelinePage)
    await flushPromises()

    expect(wrapper.find('.timeline-group').attributes('aria-label')).toBe('2025 年 4 月')
    expect(wrapper.find('time').text()).toContain('发生时间')
    expect(wrapper.find('.meta').text()).toContain('技术复盘')
  })

  it('passes year and category filters to the timeline query', async () => {
    const wrapper = mount(TimelinePage)
    await flushPromises()

    await wrapper.find('input[aria-label="按年份筛选"]').setValue('2025')
    await wrapper.find('select[aria-label="按分类筛选"]').setValue('c1')
    await flushPromises()

    expect(articlesApi.timeline).toHaveBeenLastCalledWith(expect.objectContaining({
      year: 2025,
      category_id: 'c1',
      cursor: 0,
    }))
  })

  it('allows a month group to be collapsed and expanded accessibly', async () => {
    const wrapper = mount(TimelinePage)
    await flushPromises()
    const toggle = wrapper.find('.group-toggle')

    expect(toggle.attributes('aria-expanded')).toBe('true')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.timeline-list').exists()).toBe(false)
    await toggle.trigger('click')
    expect(wrapper.find('.timeline-list').exists()).toBe(true)
  })
})

describe('PostListPage deep search', () => {
  it('uses deep search and renders matched fields plus a safe text snippet', async () => {
    const wrapper = mount(PostListPage)
    await flushPromises()

    await wrapper.find('input[aria-label="搜索文章"]').setValue('CrashLoopBackOff')
    await flushPromises()

    expect(articlesApi.search).toHaveBeenLastCalledWith(
      'CrashLoopBackOff',
      expect.objectContaining({ category_id: undefined }),
      0,
    )
    expect(wrapper.find('.search-result').text()).toContain('匹配：正文、标签')
    expect(wrapper.find('.search-highlight').text()).toContain('CrashLoopBackOff')
    expect(wrapper.find('.filter-chip').text()).toContain('关键词：CrashLoopBackOff')
  })

  it('clears an applied search chip and returns to the regular list', async () => {
    const wrapper = mount(PostListPage)
    await flushPromises()
    const searchInput = wrapper.find('input[aria-label="搜索文章"]')
    await searchInput.setValue('CrashLoopBackOff')
    await flushPromises()

    await wrapper.find('.filter-chip button').trigger('click')
    await flushPromises()

    expect((searchInput.element as HTMLInputElement).value).toBe('')
    expect(articlesApi.list).toHaveBeenCalledTimes(2)
  })
})
