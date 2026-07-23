import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import VoiceConfirmDrawer from '@/modules/voice/VoiceConfirmDrawer.vue'
import * as voiceApi from '@/api/voice'
import type { VoiceCandidate } from '@/api/voice'

beforeEach(() => {
  vi.restoreAllMocks()
})

function candidate(overrides: Partial<VoiceCandidate> = {}): VoiceCandidate {
  return {
    title: '联系房东',
    content_type: 'reminder',
    description: null,
    local_date: '2026-07-24',
    local_time: '15:00:00',
    timezone: 'Europe/Berlin',
    duration_minutes: 20,
    priority: 3,
    important: true,
    reminder: { channel: 'in_app', offset_minutes: 30 },
    recurring: false,
    recurrence_rule: null,
    original_text: '明天下午三点提醒我联系房东',
    ...overrides,
  }
}

describe('VoiceConfirmDrawer', () => {
  it('shows the AI-parsed values as editable and labels them as AI guesses', () => {
    const wrapper = mount(VoiceConfirmDrawer, {
      props: { recordId: 'v1', candidate: candidate() },
    })
    const title = wrapper.get('input[aria-label=标题]')
    expect((title.element as HTMLInputElement).value).toBe('联系房东')
    expect(wrapper.text()).toContain('AI 推测')
    expect(wrapper.text()).toContain('确认后才会创建正式记录')
  })

  it('submits the edited candidate on confirm', async () => {
    const spy = vi
      .spyOn(voiceApi.voiceApi, 'confirm')
      .mockResolvedValue({ entity_type: 'reminder', entity_id: 'task-1' })
    const wrapper = mount(VoiceConfirmDrawer, {
      props: { recordId: 'v1', candidate: candidate() },
    })
    await wrapper.get('input[aria-label=标题]').setValue('联系房东（改）')
    await wrapper.get('button.primary').trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(spy).toHaveBeenCalledWith('v1', expect.objectContaining({ title: '联系房东（改）' }))
    expect(wrapper.emitted('confirmed')?.[0]).toEqual(['reminder', 'task-1'])
  })

  it('emits discard without creating anything', async () => {
    const spy = vi.spyOn(voiceApi.voiceApi, 'confirm')
    const wrapper = mount(VoiceConfirmDrawer, {
      props: { recordId: 'v1', candidate: candidate() },
    })
    await wrapper.get('footer button:not(.primary)').trigger('click')
    expect(wrapper.emitted('discard')).toBeTruthy()
    expect(spy).not.toHaveBeenCalled()
  })
})
