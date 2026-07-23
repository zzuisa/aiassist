import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchResults from '@/modules/search/SearchResults.vue'
import type { SearchResponse } from '@/api/search'

function response(overrides: Partial<SearchResponse> = {}): SearchResponse {
  return {
    query: '房东',
    groups: [
      {
        type: 'task',
        items: [
          {
            entity: { type: 'task', id: 't1' },
            title: '联系房东',
            tags: [],
            highlights: ['联系<mark>房东</mark>'],
          },
        ],
      },
      {
        type: 'capture',
        items: [
          {
            entity: { type: 'capture', id: 'c1' },
            title: '房东合同',
            tags: [],
            highlights: [],
          },
        ],
      },
    ],
    index_pending_count: 0,
    ...overrides,
  }
}

describe('SearchResults', () => {
  it('renders results grouped by type with labels', () => {
    const wrapper = mount(SearchResults, {
      props: { results: response(), loading: false, pendingHint: false },
    })
    expect(wrapper.text()).toContain('任务 (1)')
    expect(wrapper.text()).toContain('收藏 (1)')
    expect(wrapper.text()).toContain('联系房东')
  })

  it('renders <mark> highlight markup safely', () => {
    const wrapper = mount(SearchResults, {
      props: { results: response(), loading: false, pendingHint: false },
    })
    expect(wrapper.find('mark').exists()).toBe(true)
    expect(wrapper.find('mark').text()).toBe('房东')
  })

  it('shows an actionable empty state', () => {
    const wrapper = mount(SearchResults, {
      props: {
        results: { query: 'x', groups: [], index_pending_count: 0 },
        loading: false,
        pendingHint: false,
      },
    })
    expect(wrapper.text()).toContain('未找到匹配结果')
  })

  it('shows a pending-index hint when derived index lags', () => {
    const wrapper = mount(SearchResults, {
      props: { results: response(), loading: false, pendingHint: true },
    })
    expect(wrapper.text()).toContain('索引')
  })

  it('shows a loading state', () => {
    const wrapper = mount(SearchResults, {
      props: { results: null, loading: true, pendingHint: false },
    })
    expect(wrapper.text()).toContain('搜索中')
  })
})
