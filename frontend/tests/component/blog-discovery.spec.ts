import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/blogQueries', () => ({
  articlesApi: { list: vi.fn(), search: vi.fn(), timeline: vi.fn() },
  wordCloudApi: { get: vi.fn(), rebuild: vi.fn() },
}))
vi.mock('@/api/blogTaxonomy', () => ({
  taxonomyApi: { list: vi.fn() },
}))
const routerPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => ({ query: {} }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { articlesApi, wordCloudApi } from '@/api/blogQueries'
import { taxonomyApi } from '@/api/blogTaxonomy'
import BlogSettingsPage from '@/modules/posts/BlogSettingsPage.vue'
import PostListPage from '@/modules/posts/PostListPage.vue'
import TimelinePage from '@/modules/posts/TimelinePage.vue'
import WordCloudPage from '@/modules/posts/WordCloudPage.vue'

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
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

describe('Word cloud discovery', () => {
  it('renders controls, stale state and non-color frequency cues', async () => {
    vi.mocked(wordCloudApi.get).mockResolvedValue({
      id: 's1', source_kind: 'keyword', filter: {}, article_count: 8,
      status: 'stale', generated_at: '2026-08-01T12:00:00Z', error_code: 'failed',
      terms: [{ id: 'k1', term: '数据库', count: 5 }],
    })
    const wrapper = mount(WordCloudPage)
    await flushPromises()

    expect(wrapper.find('[aria-label="词云筛选"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('上次有效结果')
    expect(wrapper.get('button[aria-label="数据库，出现于 5 篇文章"]').text()).toContain('5')
  })

  it('saves word-cloud defaults without triggering an automatic rebuild', async () => {
    const wrapper = mount(BlogSettingsPage)
    await wrapper.get('input[min="1"][max="100000"]').setValue('3')
    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('设置已保存')
    expect(JSON.parse(window.localStorage.getItem('aiassist:word-cloud-settings') || '{}'))
      .toMatchObject({ min_frequency: 3 })
    expect(wordCloudApi.rebuild).not.toHaveBeenCalled()
  })

  it('shows loading and empty states and submits explicit rebuild controls', async () => {
    let resolveGet: (value: null) => void = () => undefined
    vi.mocked(wordCloudApi.get).mockReturnValue(new Promise((resolve) => { resolveGet = resolve }))
    vi.mocked(wordCloudApi.rebuild).mockResolvedValue({
      job: { id: 'j1', job_type: 'blog.wordcloud', status: 'pending' }, previous: null,
    })
    const wrapper = mount(WordCloudPage)
    await Promise.resolve()
    expect(wrapper.text()).toContain('正在加载词云')
    resolveGet(null)
    await flushPromises()
    expect(wrapper.text()).toContain('尚无词云快照')
    await wrapper.get('input[aria-label="最低频次"]').setValue('3')
    await wrapper.get('.primary').trigger('click')
    await flushPromises()
    expect(wordCloudApi.rebuild).toHaveBeenCalledWith(expect.objectContaining({ min_frequency: 3 }))
  })

  it('navigates canonical terms to a clearable article filter', async () => {
    vi.mocked(wordCloudApi.get).mockResolvedValue({
      id: 's1', source_kind: 'keyword', filter: {}, article_count: 4,
      status: 'ready', generated_at: '2026-08-01T12:00:00Z', error_code: null,
      terms: [{ id: 'keyword-1', term: '后端', count: 4 }],
    })
    const wrapper = mount(WordCloudPage)
    await flushPromises()
    await wrapper.get('button[aria-label="后端，出现于 4 篇文章"]').trigger('click')
    expect(routerPush).toHaveBeenCalledWith({
      name: 'blog', query: { keyword_id: 'keyword-1' },
    })
  })
})
