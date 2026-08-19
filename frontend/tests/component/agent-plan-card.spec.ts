import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentPlanCard from '@/components/agent/AgentPlanCard.vue'
import type { AgentPlan } from '@/api/agentPlans'

function plan(status: AgentPlan['status'], version = 1): AgentPlan {
  return {
    schema_version: 'agent-plan-view.v1',
    plan_id: 'plan-1',
    turn_id: 'turn-1',
    task_id: 'task-1',
    user_message_id: 'message-1',
    objective: '查询并分析文章',
    status,
    version,
    counts: { total: 2, completed: status === 'success' ? 2 : 0, failed: 0, skipped: 0 },
    elapsed_ms: status === 'success' ? 1200 : null,
    result_summary: status === 'success' ? '处理完成' : null,
    error: null,
    steps: [
      {
        step_id: 'step-1',
        step_key: 'step_query',
        position: 1,
        title: '查询文章',
        responsibility: '取得文章范围',
        agent: { key: 'article-query-agent', name: '文章查询 Agent' },
        tool_name: 'posts.list_recent',
        operation_type: 'query',
        depends_on: [],
        status: status === 'success' ? 'success' : 'running',
        progress: null,
        attempt_count: 1,
        stage_label: '正在查询',
        result_summary: null,
        error: null,
        started_at: '2026-08-18T00:00:00Z',
        finished_at: status === 'success' ? '2026-08-18T00:00:01Z' : null,
        duration_ms: status === 'success' ? 1000 : null,
      },
    ],
    created_at: '2026-08-18T00:00:00Z',
    finished_at: status === 'success' ? '2026-08-18T00:00:01Z' : null,
  }
}

describe('AgentPlanCard', () => {
  it('shows a compact active summary and keeps details collapsed by default', async () => {
    const wrapper = mount(AgentPlanCard, { props: { plan: plan('running') } })
    expect(wrapper.find('.plan-details').exists()).toBe(false)
    expect(wrapper.text()).toContain('执行中')

    await wrapper.get('.plan-summary').trigger('click')
    expect(wrapper.find('.plan-details').exists()).toBe(true)
  })

  it('preserves a manual expansion across later terminal snapshots', async () => {
    const wrapper = mount(AgentPlanCard, { props: { plan: plan('success') } })
    await wrapper.get('.plan-summary').trigger('click')
    expect(wrapper.find('.plan-details').exists()).toBe(true)

    await wrapper.setProps({ plan: plan('success', 2) })
    expect(wrapper.find('.plan-details').exists()).toBe(true)
  })
})
