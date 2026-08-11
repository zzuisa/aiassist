import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentTurnRetry from '@/components/agent/AgentTurnRetry.vue'

describe('AgentTurnRetry', () => {
  it('shows stalled guidance and emits retry', async () => {
    const wrapper = mount(AgentTurnRetry, { props: { turns: [{ id: 'turn-1', conversation_id: 'conv', status: 'stalled', route_kind: 'task', current_step: '处理已停滞', agent_task_id: null, error_message: '处理长时间没有进展，可以安全重试。', created_at: '2026-08-11T00:00:00Z', finished_at: '2026-08-11T00:01:00Z' }] } })
    expect(wrapper.text()).toContain('可以安全重试')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toEqual([['turn-1']])
  })
})
