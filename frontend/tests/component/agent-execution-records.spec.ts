import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ExecutionRecordList from '@/components/agent/ExecutionRecordList.vue'

describe('ExecutionRecordList', () => {
  it('keeps execution details collapsed until requested', async () => {
    const wrapper = mount(ExecutionRecordList, {
      props: {
        records: [{
          step_id: 'step-1',
          agent_id: 'agent-1',
          agent_name: '文章查询 Agent',
          step_label: '查询文章',
          tool_name: 'posts.list_recent',
          operation_type: 'query',
          params_digest: {},
          result_summary: '找到了 10 篇文章',
          status: 'success',
          error_reason: null,
          started_at: '2026-08-19T00:00:00Z',
          finished_at: '2026-08-19T00:00:01Z',
          duration_ms: 1000,
        }],
      },
    })

    const details = wrapper.get('details')
    expect(details.attributes('open')).toBeUndefined()
    expect(details.get('summary').text()).toBe('执行记录（1）')

    await details.get('summary').trigger('click')
    expect((details.element as HTMLDetailsElement).open).toBe(true)
    expect(wrapper.text()).toContain('找到了 10 篇文章')
  })
})
