import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CalendarEventPopover from '@/modules/calendar/CalendarEventPopover.vue'
import type { Task } from '@/api/tasks'

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 't1',
    type: 'task',
    title: '和房东开会',
    status: 'todo',
    priority: 0,
    importance: 0,
    is_fixed: false,
    is_ai_adjustable: true,
    is_splittable: false,
    tag_ids: [],
    version: 1,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('CalendarEventPopover (US1)', () => {
  it('shows toggle labels for the current state', () => {
    const w = mount(CalendarEventPopover, {
      props: { task: makeTask({ status: 'completed', importance: 4 }) },
    })
    expect(w.text()).toContain('取消完成')
    expect(w.text()).toContain('取消重要')
  })

  it('deletes only after a confirm tap', async () => {
    const w = mount(CalendarEventPopover, { props: { task: makeTask() } })
    const btn = () => w.findAll('.act').find((b) => b.text().includes('删除'))!
    await btn().trigger('click')
    expect(w.emitted('delete')).toBeFalsy() // first tap only arms it
    expect(btn().text()).toContain('确认删除')
    await btn().trigger('click')
    expect(w.emitted('delete')).toBeTruthy()
  })

  it('emits adjust-time from the popover', async () => {
    const w = mount(CalendarEventPopover, { props: { task: makeTask() } })
    const btn = w.findAll('.act').find((b) => b.text().includes('调整时间'))!
    await btn.trigger('click')
    expect(w.emitted('adjust-time')).toBeTruthy()
  })

  it('emits toggle-complete and toggle-important', async () => {
    const w = mount(CalendarEventPopover, { props: { task: makeTask() } })
    const btns = w.findAll('.act')
    await btns[0].trigger('click')
    await btns[1].trigger('click')
    expect(w.emitted('toggle-complete')).toBeTruthy()
    expect(w.emitted('toggle-important')).toBeTruthy()
  })

  it('surfaces the reminder summary for an important event', () => {
    const w = mount(CalendarEventPopover, {
      props: {
        task: makeTask({ importance: 4, important_reminder: { state: 'scheduled', trigger_at: null } }),
      },
    })
    expect(w.text()).toContain('开始前 4 小时')
  })

  it('warns when an important event has no start time', () => {
    const w = mount(CalendarEventPopover, {
      props: {
        task: makeTask({ importance: 4, important_reminder: { state: 'missing_start', trigger_at: null } }),
      },
    })
    expect(w.text()).toContain('设置开始时间')
  })
})
