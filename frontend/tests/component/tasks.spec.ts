import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import QuickTaskInput from '@/modules/tasks/QuickTaskInput.vue'
import TaskCard from '@/modules/tasks/TaskCard.vue'
import type { Task } from '@/api/tasks'

beforeEach(() => {
  setActivePinia(createPinia())
})

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 't1',
    type: 'task',
    title: '买菜',
    status: 'todo',
    priority: 2,
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

describe('QuickTaskInput', () => {
  it('clears the input after a successful create', async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(QuickTaskInput, { attrs: { onCreate } })
    const input = wrapper.get('input')
    await input.setValue('喝水')
    await wrapper.get('form').trigger('submit')
    await new Promise((r) => setTimeout(r, 0))
    expect(onCreate).toHaveBeenCalledWith('喝水')
    expect((input.element as HTMLInputElement).value).toBe('')
  })

  it('retains the input and shows an error when create fails', async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(QuickTaskInput, { attrs: { onCreate } })
    const input = wrapper.get('input')
    await input.setValue('重要任务')
    await wrapper.get('form').trigger('submit')
    await new Promise((r) => setTimeout(r, 0))
    expect((input.element as HTMLInputElement).value).toBe('重要任务')
    expect(wrapper.text()).toContain('保存失败')
  })

  it('does not submit blank titles', async () => {
    const onCreate = vi.fn()
    const wrapper = mount(QuickTaskInput, { attrs: { onCreate } })
    await wrapper.get('input').setValue('   ')
    await wrapper.get('form').trigger('submit')
    expect(onCreate).not.toHaveBeenCalled()
  })
})

describe('TaskCard', () => {
  it('shows a text status label (not color alone)', () => {
    const wrapper = mount(TaskCard, { props: { task: makeTask({ status: 'in_progress' }) } })
    expect(wrapper.text()).toContain('进行中')
  })

  it('marks fixed tasks with a fixed label', () => {
    const wrapper = mount(TaskCard, {
      props: { task: makeTask({ is_fixed: true, is_ai_adjustable: false }) },
    })
    expect(wrapper.text()).toContain('固定')
  })

  it('emits complete when the check button is clicked', async () => {
    const task = makeTask()
    const wrapper = mount(TaskCard, { props: { task } })
    await wrapper.get('.check').trigger('click')
    expect(wrapper.emitted('complete')?.[0]).toEqual([task])
  })
})
