import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentResultList from '@/components/agent/AgentResultList.vue'
import { presentAgentResult } from '@/components/agent/resultPresentation'

describe('friendly Agent results', () => {
  it('unwraps an MCP structured result into searchable, interactive article items', async () => {
    const presented = presentAgentResult({
      structured_content: {
        query: '情感',
        total: 2,
        items: [
          {
            id: '10000000-0000-4000-8000-000000000001',
            title: '情感与边界',
            highlight: '<mark>情感</mark>并不等于依赖',
            category: '随笔',
            tags: ['情感', '成长'],
            status: 'private',
          },
          {
            id: '20000000-0000-4000-8000-000000000002',
            title: '理解关系',
            tags: ['关系'],
            status: 'draft',
          },
        ],
      },
    })
    const wrapper = mount(AgentResultList, {
      props: presented,
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    expect(wrapper.text()).toContain('“情感”共找到 2 项')
    expect(wrapper.text()).toContain('情感与边界')
    expect(wrapper.text()).not.toContain('{"')
    expect(wrapper.findAll('.result-item')).toHaveLength(2)

    await wrapper.get('input[type="search"]').setValue('关系')
    expect(wrapper.findAll('.result-item')).toHaveLength(1)
    expect(wrapper.text()).toContain('理解关系')
  })

  it('turns taxonomy records into named items with readable metrics', () => {
    const presented = presentAgentResult({
      kind: 'tag',
      total: 1,
      tags: [{ id: 'tag-1', name: '情感', usage_count: 8 }],
    })
    expect(presented.items[0]?.title).toBe('情感')
    expect(presented.items[0]?.metrics).toEqual([{ label: '使用次数', value: '8' }])
  })
})
