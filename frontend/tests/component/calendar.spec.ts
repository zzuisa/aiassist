import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SchedulePreviewDrawer from '@/modules/calendar/SchedulePreviewDrawer.vue'
import { persistReschedule } from '@/modules/calendar/useReschedule'
import { ApiError } from '@/api/client'
import type { SchedulePreview, ScheduleSuggestion } from '@/api/calendar'
import * as calendarApi from '@/api/calendar'
import type { Task } from '@/api/tasks'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

function suggestion(overrides: Partial<ScheduleSuggestion> = {}): ScheduleSuggestion {
  return {
    suggestion_id: 's1',
    task_id: 't1',
    task_version: 1,
    recommendation: 'move',
    old_start: '2026-07-27T10:00:00Z',
    old_end: '2026-07-27T11:00:00Z',
    new_start: '2026-07-27T12:00:00Z',
    new_end: '2026-07-27T13:00:00Z',
    reason: '与其他任务冲突',
    conflicting_task_ids: ['t2'],
    selectable: true,
    ...overrides,
  }
}

function preview(suggestions: ScheduleSuggestion[]): SchedulePreview {
  return {
    id: 'p1',
    status: 'ready',
    suggestions,
    explanation: '基于冲突的建议',
    expires_at: '2026-07-27T12:00:00Z',
  }
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 't1',
    type: 'task',
    title: 'A',
    status: 'todo',
    priority: 0,
    importance: 0,
    is_fixed: false,
    is_ai_adjustable: true,
    is_splittable: false,
    tag_ids: [],
    version: 3,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('SchedulePreviewDrawer', () => {
  it('disables fixed/non-selectable suggestions', () => {
    const wrapper = mount(SchedulePreviewDrawer, {
      props: { preview: preview([suggestion({ selectable: false, recommendation: 'keep' })]) },
    })
    const checkbox = wrapper.get('input[type=checkbox]')
    expect((checkbox.element as HTMLInputElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('固定 / 不可调整')
  })

  it('applies only selected suggestions', async () => {
    const spy = vi
      .spyOn(calendarApi.calendarApi, 'applyPreview')
      .mockResolvedValue({ applied: ['s1'], rejected: [], activity_id: 'a' })
    const wrapper = mount(SchedulePreviewDrawer, { props: { preview: preview([suggestion()]) } })
    await wrapper.get('input[type=checkbox]').setValue(true)
    await wrapper.get('button.primary').trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(spy).toHaveBeenCalledWith('p1', ['s1'])
    expect(wrapper.emitted('applied')).toBeTruthy()
  })

  it('shows stale feedback when a suggestion is rejected as version_conflict', async () => {
    vi.spyOn(calendarApi.calendarApi, 'applyPreview').mockResolvedValue({
      applied: [],
      rejected: [{ suggestion_id: 's1', code: 'version_conflict', detail: 'stale' }],
      activity_id: 'a',
    })
    const wrapper = mount(SchedulePreviewDrawer, { props: { preview: preview([suggestion()]) } })
    await wrapper.get('input[type=checkbox]').setValue(true)
    await wrapper.get('button.primary').trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('已过期')
  })
})

describe('persistReschedule (drag/resize revert)', () => {
  it('returns ok on success', async () => {
    vi.spyOn(calendarApi.calendarApi, 'reschedule').mockResolvedValue(makeTask({ version: 4 }))
    const outcome = await persistReschedule(makeTask(), '2026-07-27T12:00:00Z', null)
    expect(outcome.ok).toBe(true)
    expect(outcome.task?.version).toBe(4)
  })

  it('reports version_conflict so the caller can revert', async () => {
    vi.spyOn(calendarApi.calendarApi, 'reschedule').mockRejectedValue(
      new ApiError({ type: '', title: '', status: 409, code: 'version_conflict' }),
    )
    const outcome = await persistReschedule(makeTask(), '2026-07-27T12:00:00Z', null)
    expect(outcome.ok).toBe(false)
    expect(outcome.reason).toBe('version_conflict')
  })

  it('reports fixed_event rejection', async () => {
    vi.spyOn(calendarApi.calendarApi, 'reschedule').mockRejectedValue(
      new ApiError({ type: '', title: '', status: 422, code: 'fixed_event' }),
    )
    const outcome = await persistReschedule(makeTask(), '2026-07-27T12:00:00Z', null)
    expect(outcome.reason).toBe('fixed_event')
  })
})
