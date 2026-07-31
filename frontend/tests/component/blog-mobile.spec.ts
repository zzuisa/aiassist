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
vi.mock('@/api/blogTaxonomy', () => ({
  taxonomyApi: { list: vi.fn(), create: vi.fn() },
}))
vi.mock('@/api/blogCapture', () => ({
  blogCaptureApi: { blank: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { articlesApi } from '@/api/blogQueries'
import { taxonomyApi } from '@/api/blogTaxonomy'
import PostListPage from '@/modules/posts/PostListPage.vue'

const listFixture = {
  items: [{
    id: 'p1', title: '移动端文章', content_status: 'draft', content_class: 'technical',
    category_id: 'c1', status: 'draft', ai_state: 'none', source_count: 0,
    updated_at: '', created_at: '',
  }],
  next_cursor: null, total: 1, counts_by_status: { draft: 1 },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(articlesApi.list).mockResolvedValue(listFixture as never)
  vi.mocked(articlesApi.batch).mockResolvedValue({
    results: [{ id: 'p1', ok: true }], succeeded: 1, failed: 0,
  })
  vi.mocked(taxonomyApi.list).mockResolvedValue([{
    id: 'c1', kind: 'category', name: '技术复盘', description: null, parent_id: null,
    aliases: [], color: null, enabled: true, stop_word: false, usage_count: 1,
  }] as never)
})

describe('PostListPage mobile actions', () => {
  it('shows category first and exposes the accessible fallback menu', async () => {
    const w = mount(PostListPage)
    await flushPromises()

    expect(w.find('.category-chip').text()).toBe('技术复盘')
    await w.find('.more-btn').trigger('click')
    expect(w.find('.accessible-actions').text()).toContain('归类')
    expect(w.find('.accessible-actions').text()).toContain('归档')
  })

  it('opens right-side category action only after the swipe threshold', async () => {
    const w = mount(PostListPage)
    await flushPromises()
    const row = w.find('.post-row')

    await row.trigger('touchstart', { touches: [{ clientX: 200, clientY: 120 }] })
    await row.trigger('touchmove', { touches: [{ clientX: 240, clientY: 120 }] })
    await row.trigger('touchend')
    expect((w.find('.row-content').element as HTMLElement).style.transform).toContain('0px')

    await row.trigger('touchstart', { touches: [{ clientX: 200, clientY: 120 }] })
    await row.trigger('touchmove', { touches: [{ clientX: 300, clientY: 120 }] })
    await row.trigger('touchend')
    expect((w.find('.row-content').element as HTMLElement).style.transform).toContain('152px')

    await w.find('.swipe-actions--right button').trigger('click')
    expect(w.find('.category-menu').exists()).toBe(true)
    await w.find('.category-menu button:nth-of-type(2)').trigger('click')
    expect(articlesApi.batch).toHaveBeenCalledWith(['p1'], 'set_category', { category_id: 'c1' })

    await row.trigger('touchstart', { touches: [{ clientX: 200, clientY: 120 }] })
    await row.trigger('touchmove', { touches: [{ clientX: 204, clientY: 220 }] })
    await row.trigger('touchend')
    expect((w.find('.row-content').element as HTMLElement).style.transform).toContain('0px')
  })

  it('offers a real undo action after a reversible row operation', async () => {
    const w = mount(PostListPage)
    await flushPromises()
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    await w.find('.more-btn').trigger('click')
    await w.find('.accessible-actions .danger').trigger('click')
    await flushPromises()

    expect(w.find('.toast').text()).toContain('撤销')
    await w.find('.toast-undo').trigger('click')
    expect(articlesApi.batch).toHaveBeenLastCalledWith(['p1'], 'set_status', { content_status: 'draft' })
  })
})
