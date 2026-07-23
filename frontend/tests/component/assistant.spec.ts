import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ActionCardView from '@/modules/assistant/ActionCard.vue'
import type { ActionCard } from '@/api/assistant'

function planCard(overrides: Partial<ActionCard> = {}): ActionCard {
  return {
    id: 'plan',
    kind: 'plan',
    title: '今日安排建议',
    body: { reason: '基于当前未完成任务的具体时间建议', fixed_kept: ['f1'] },
    actions: [{ id: 'reschedule:t1', label: '调整「任务一」到下一个空档' }],
    ...overrides,
  }
}

describe('ActionCard', () => {
  it('shows grounded reasoning and explicit action buttons', () => {
    const wrapper = mount(ActionCardView, { props: { card: planCard(), applying: null } })
    expect(wrapper.text()).toContain('基于当前未完成任务')
    expect(wrapper.text()).toContain('调整「任务一」到下一个空档')
  })

  it('surfaces that fixed events are kept', () => {
    const wrapper = mount(ActionCardView, { props: { card: planCard(), applying: null } })
    expect(wrapper.text()).toContain('固定事件保持不变')
  })

  it('only applies when the explicit button is clicked', async () => {
    const wrapper = mount(ActionCardView, { props: { card: planCard(), applying: null } })
    await wrapper.get('.actions button').trigger('click')
    expect(wrapper.emitted('apply')?.[0]).toEqual(['reschedule:t1'])
  })

  it('shows a no-result card honestly with no actions', () => {
    const card = planCard({
      id: 'no_result',
      kind: 'summary',
      title: '未找到相关数据',
      body: { message: '没有找到可操作的记录，请先创建任务。' },
      actions: [],
    })
    const wrapper = mount(ActionCardView, { props: { card, applying: null } })
    expect(wrapper.text()).toContain('没有找到可操作的记录')
    expect(wrapper.text()).toContain('此结果没有可执行的操作')
    expect(wrapper.find('.actions').exists()).toBe(false)
  })

  it('disables the button while its action is applying', () => {
    const wrapper = mount(ActionCardView, {
      props: { card: planCard(), applying: 'reschedule:t1' },
    })
    expect((wrapper.get('.actions button').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('应用中')
  })
})
