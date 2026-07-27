import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import QuickPlanReview from '@/modules/today/QuickPlanReview.vue'
import * as planApi from '@/api/plan'

function stubAnalyze(over: Partial<planApi.PlanResult> = {}) {
  vi.spyOn(planApi.planApi, 'analyze').mockResolvedValue({
    tasks: [
      {
        title: '喝咖啡',
        content_type: 'task',
        description: null,
        local_date: '2026-07-28',
        local_time: '09:00:00',
        timezone: 'Europe/Berlin',
        duration_minutes: 30,
        priority: 1,
        important: false,
        reminder: null,
        recurring: false,
        recurrence_rule: null,
        original_text: '喝咖啡',
      },
    ],
    questions: ['你一般几点起床？'],
    summary: '已安排 1 件事',
    error: null,
    ...over,
  })
}

describe('QuickPlanReview', () => {
  it('shows the analyzed plan and a clarifying question', async () => {
    stubAnalyze()
    const w = mount(QuickPlanReview, { props: { text: '明天上午喝咖啡' } })
    await flushPromises()
    expect(w.text()).toContain('喝咖啡')
    expect(w.text()).toContain('已安排 1 件事')
    expect(w.text()).toContain('几点起床')
  })

  it('commits the plan on save', async () => {
    stubAnalyze()
    const commit = vi.spyOn(planApi.planApi, 'commit').mockResolvedValue({ created: [] })
    const w = mount(QuickPlanReview, { props: { text: '明天上午喝咖啡' } })
    await flushPromises()
    await w.get('button.primary').trigger('click')
    await flushPromises()
    expect(commit).toHaveBeenCalled()
    expect(w.emitted('saved')).toBeTruthy()
  })

  it('always offers a raw-save escape hatch', async () => {
    stubAnalyze({ tasks: [], questions: [], summary: '', error: 'timeout' })
    const w = mount(QuickPlanReview, { props: { text: '随便记一条' } })
    await flushPromises()
    const raw = w.findAll('button').find((b) => b.text().includes('直接存为待办'))!
    await raw.trigger('click')
    expect(w.emitted('save-raw')?.[0]).toEqual(['随便记一条'])
  })
})
