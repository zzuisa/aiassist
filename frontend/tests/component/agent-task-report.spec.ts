import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import TaskReportCard from '@/components/agent/TaskReportCard.vue'
import type { AgentTaskReport } from '@/api/agentPlans'

const report: AgentTaskReport = {
  schema_version: 'task-report.v1',
  report_id: '00000000-0000-0000-0000-000000000001',
  plan_id: '00000000-0000-0000-0000-000000000002',
  revision: 1,
  source_digest: 'a'.repeat(64),
  objective: '处理情感博客标签',
  executed_steps: [],
  totals: { matched: 8, applied: 3, verified: 3 },
  verified_changes: [],
  conflicts: [],
  failures: [],
  skipped: [],
  unprocessed: [],
  next_actions: [],
  results: [],
  markdown: '# 处理情感博客标签\n\n匹配：8\n',
  report_digest: 'b'.repeat(64),
  generation_method: 'deterministic',
  generated_at: '2026-08-20T00:00:00Z',
}

describe('TaskReportCard', () => {
  it('keeps the full Markdown compact and available on demand', async () => {
    const wrapper = mount(TaskReportCard, { props: { report } })

    expect(wrapper.text()).toContain('匹配 8')
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('pre').text()).toContain('# 处理情感博客标签')
  })
})
