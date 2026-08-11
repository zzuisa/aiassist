import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationTimeline from '@/components/agent/ConversationTimeline.vue'

describe('ConversationTimeline', () => {
  it('renders roles, clarification and confirmation-safe activity', () => {
    const wrapper = mount(ConversationTimeline, { props: { messages: [
      { id: 'u', role: 'user', kind: 'text', content: { text: '处理文章' }, turn_id: 't', created_at: '2026-08-11T00:00:00Z' },
      { id: 'c', role: 'assistant', kind: 'clarification', content: { text: '哪几篇？' }, turn_id: 't', created_at: '2026-08-11T00:00:01Z' },
      { id: 'r', role: 'assistant', kind: 'result', content: { text: '已生成', task_status: 'waiting_confirmation' }, turn_id: 't2', created_at: '2026-08-11T00:00:02Z' },
    ] } })
    expect(wrapper.find('.role-user').text()).toContain('处理文章')
    expect(wrapper.text()).toContain('哪几篇？')
    expect(wrapper.text()).toContain('确认前不会写入')
  })
})
