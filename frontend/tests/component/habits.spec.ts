import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import HabitCard from '@/modules/habits/HabitCard.vue'
import SkipSheet from '@/modules/habits/SkipSheet.vue'
import HabitHeatmap from '@/modules/habits/HabitHeatmap.vue'
import type { Habit, HabitStats } from '@/api/habits'

beforeEach(() => {
  vi.useRealTimers()
})

function makeHabit(overrides: Partial<Habit> = {}): Habit {
  return {
    id: 'h1',
    name: '喝水',
    recurrence_rule: 'FREQ=DAILY',
    priority: 0,
    auto_create_task: true,
    is_ai_adjustable: true,
    status: 'active',
    version: 1,
    ...overrides,
  }
}

describe('HabitCard', () => {
  it('emits checkin on one-tap', async () => {
    const wrapper = mount(HabitCard, { props: { habit: makeHabit(), log: null } })
    await wrapper.get('.checkin').trigger('click')
    expect(wrapper.emitted('checkin')?.[0]?.[0]).toBe('h1')
  })

  it('shows completed status and disables checkin when done', () => {
    const wrapper = mount(HabitCard, {
      props: {
        habit: makeHabit(),
        log: { id: 'l', habit_id: 'h1', local_date: '2026-07-27', status: 'completed' },
      },
    })
    expect(wrapper.text()).toContain('已完成')
    expect((wrapper.get('.checkin').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('timer emits checkin with elapsed seconds when stopped', async () => {
    vi.useFakeTimers()
    const wrapper = mount(HabitCard, { props: { habit: makeHabit(), log: null } })
    await wrapper.get('.timer').trigger('click') // start
    vi.advanceTimersByTime(3000)
    await wrapper.get('.timer').trigger('click') // stop
    const emitted = wrapper.emitted('checkin')
    expect(emitted?.[0]?.[1]).toBe(3)
    vi.useRealTimers()
  })
})

describe('SkipSheet', () => {
  it('emits the selected reason and note', async () => {
    const wrapper = mount(SkipSheet, { props: { habitName: '喝水' } })
    await wrapper.get('textarea').setValue('太忙')
    await wrapper.get('button.primary').trigger('click')
    const emitted = wrapper.emitted('confirm')
    expect(emitted?.[0]?.[0]).toBe('too_tired')
    expect(emitted?.[0]?.[1]).toBe('太忙')
  })
})

describe('HabitHeatmap', () => {
  it('renders streak and completion rate', () => {
    const stats: HabitStats = {
      streak: 5,
      completion_rate: 0.8,
      total_logs: 10,
      completed_logs: 8,
      heatmap: {},
    }
    const wrapper = mount(HabitHeatmap, { props: { stats } })
    expect(wrapper.text()).toContain('连续 5 天')
    expect(wrapper.text()).toContain('80%')
  })
})
