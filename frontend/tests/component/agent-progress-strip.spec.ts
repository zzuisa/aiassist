import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentProgressStrip from '@/components/agent/AgentProgressStrip.vue'
import type { Turn } from '@/api/agentConversations'
import type { AgentPlan } from '@/api/agentPlans'

const turn: Turn = {
  id: 'turn-1',
  conversation_id: 'conversation-1',
  status: 'routing',
  route_kind: null,
  current_step: '正在理解请求',
  agent_task_id: null,
  error_message: null,
  created_at: '2026-08-21T00:00:00Z',
  finished_at: null,
}

const plan: AgentPlan = {
  schema_version: 'agent-plan-view.v1',
  plan_id: 'plan-1',
  turn_id: 'turn-1',
  task_id: 'task-1',
  user_message_id: 'message-1',
  objective: '查询并补充博客标签',
  status: 'running',
  phase: 'executing',
  version: 2,
  counts: { total: 3, completed: 1, failed: 0, skipped: 0 },
  elapsed_ms: 1000,
  result_summary: null,
  error: null,
  steps: [
    {
      step_id: 'step-1', step_key: 'search', position: 1, title: '搜索博客',
      responsibility: '搜索', agent: { key: 'mcp', name: 'MCP' }, tool_name: 'blog-search',
      operation_type: 'query', depends_on: [], status: 'success', progress: null,
      attempt_count: 1, stage_label: '步骤完成', result_summary: '8 篇', error: null,
      started_at: null, finished_at: null, duration_ms: null,
    },
    {
      step_id: 'step-2', step_key: 'analyze', position: 2, title: '分析缺失标签文章',
      responsibility: '分析', agent: { key: 'llm', name: 'LLM' }, tool_name: 'analyze',
      operation_type: 'analyze', depends_on: ['search'], status: 'running',
      progress: { current: 3, total: 8, stage_label: '正在分析' }, attempt_count: 1,
      stage_label: '正在分析', result_summary: null, error: null, started_at: null,
      finished_at: null, duration_ms: null,
    },
    {
      step_id: 'step-3', step_key: 'verify', position: 3, title: '回读验证',
      responsibility: '验证', agent: { key: 'verify', name: '验证' }, tool_name: 'verify',
      operation_type: 'query', depends_on: ['analyze'], status: 'pending', progress: null,
      attempt_count: 0, stage_label: '等待依赖', result_summary: null, error: null,
      started_at: null, finished_at: null, duration_ms: null,
    },
  ],
  created_at: '2026-08-21T00:00:00Z',
  finished_at: null,
}

describe('AgentProgressStrip', () => {
  it('shows thinking immediately while routing before a plan exists', () => {
    const wrapper = mount(AgentProgressStrip, { props: { plan: null, turn } })
    expect(wrapper.text()).toContain('正在思考')
    expect(wrapper.text()).toContain('正在理解请求')
  })

  it('prioritizes the immediate sending state over an older plan', () => {
    const wrapper = mount(AgentProgressStrip, { props: { plan, turn, sending: true } })
    expect(wrapper.text()).toContain('正在接收任务')
    expect(wrapper.text()).toContain('正在建立任务上下文')
  })

  it('shows a marquee roadmap and granular current-step progress for a complex plan', () => {
    const wrapper = mount(AgentProgressStrip, { props: { plan, turn } })
    expect(wrapper.find('.marquee').exists()).toBe(true)
    expect(wrapper.find('.marquee').text()).toContain('回读验证')
    expect(wrapper.text()).toContain('分析缺失标签文章 · 正在分析')
    expect(wrapper.text()).toContain('本步骤 3/8')
    expect(wrapper.get('progress').attributes('value')).toBe('3')
    expect(wrapper.get('progress').attributes('max')).toBe('8')
  })
})
