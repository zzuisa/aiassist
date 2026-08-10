import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('@/api/blogTaxonomy', () => ({
  taxonomyApi: { list: vi.fn(), create: vi.fn() },
}))
vi.mock('vue-router', () => ({
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { taxonomyApi } from '@/api/blogTaxonomy'
import TaxonomyPage from '@/modules/posts/TaxonomyPage.vue'

const fixture = [
  {
    id: 'root', kind: 'category', name: '技术', description: null, parent_id: null,
    aliases: [], color: null, enabled: true, stop_word: false, usage_count: 2,
  },
  {
    id: 'child', kind: 'category', name: '故障复盘', description: null, parent_id: 'root',
    aliases: [], color: null, enabled: true, stop_word: false, usage_count: 1,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(taxonomyApi.list).mockResolvedValue(fixture as never)
})

describe('TaxonomyPage', () => {
  it('renders a bounded category tree with usage counts', async () => {
    const w = mount(TaxonomyPage)
    await flushPromises()

    expect(w.find('.tree').text()).toContain('技术')
    expect(w.find('.tree').text()).toContain('故障复盘')
    expect(w.find('.tree').text()).toContain('2 篇')
    expect(w.text()).toContain('最多 3 层')
  })

  it('creates a category under the selected parent', async () => {
    vi.mocked(taxonomyApi.create).mockResolvedValue(fixture[1] as never)
    const w = mount(TaxonomyPage)
    await flushPromises()

    await w.find('.card-head .primary').trigger('click')
    await w.find('input[aria-label="分类名称"]').setValue('移动端')
    await w.find('select[aria-label="父分类"]').setValue('root')
    await w.find('.drawer .primary').trigger('click')
    await flushPromises()

    expect(taxonomyApi.create).toHaveBeenCalledWith('category', expect.objectContaining({
      name: '移动端', parent_id: 'root',
    }))
    expect(w.find('.message--saved').text()).toContain('分类已保存')
  })
})
