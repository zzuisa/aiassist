import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmationCard from '@/components/agent/ConfirmationCard.vue'
import type { PendingWrite } from '@/api/agent'

function pendingWrite(overrides: Partial<PendingWrite> = {}): PendingWrite {
  return {
    confirmation_id: 'confirm-1',
    operation_type: 'update',
    target_type: 'post',
    targets: [{ id: 'post-1', version: 3 }, { id: 'post-2', version: 2 }],
    preview: {
      summary: '把已生成的标签、关键词与摘要写入目标文章',
      changes: [{ post_id: 'post-1', tags: ['Agent'], keywords: ['确认流'] }],
    },
    affected_count: 2,
    reversible: true,
    high_risk: true,
    decision: 'pending',
    decided_at: null,
    created_at: '2026-08-09T12:00:00Z',
    ...overrides,
  }
}

describe('Agent ConfirmationCard', () => {
  it('shows impact, risk, rollback information and preview', () => {
    const wrapper = mount(ConfirmationCard, {
      props: { confirmation: pendingWrite(), deciding: false },
    })

    expect(wrapper.text()).toContain('预计影响 2 项')
    expect(wrapper.text()).toContain('高风险操作')
    expect(wrapper.text()).toContain('支持回滚')
    expect(wrapper.text()).toContain('确认流')
  })

  it('only emits structured decisions from explicit buttons', async () => {
    const wrapper = mount(ConfirmationCard, {
      props: { confirmation: pendingWrite(), deciding: false },
    })

    await wrapper.get('[data-action="approve"]').trigger('click')
    await wrapper.get('[data-action="reject"]').trigger('click')

    expect(wrapper.emitted('decide')).toEqual([['approve'], ['reject']])
  })

  it('disables decisions after completion', () => {
    const wrapper = mount(ConfirmationCard, {
      props: {
        confirmation: pendingWrite({ decision: 'approved' }),
        deciding: false,
      },
    })

    expect(wrapper.find('[data-action="approve"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已批准')
  })
})
