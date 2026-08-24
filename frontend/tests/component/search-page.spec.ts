import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type * as SearchApiModule from '@/api/search'

const { search, route } = vi.hoisted(() => ({
  search: vi.fn(),
  route: { query: { q: '情感文章' } },
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
}))

vi.mock('@/api/search', async (importOriginal) => {
  const original = await importOriginal<typeof SearchApiModule>()
  return {
    ...original,
    searchApi: { search },
  }
})

import SearchPage from '@/modules/search/SearchPage.vue'

describe('SearchPage route query integration', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    search.mockReset()
    search.mockResolvedValue({ query: '情感文章', groups: [], index_pending_count: 0 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('hydrates the page search and runs it from the global header q parameter', async () => {
    const wrapper = mount(SearchPage)

    expect(wrapper.get<HTMLInputElement>('input[type="search"]').element.value).toBe('情感文章')
    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()

    expect(search).toHaveBeenCalledWith('情感文章', undefined)
  })
})
