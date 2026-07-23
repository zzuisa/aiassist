import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import LiveVoiceInput from '@/modules/voice/LiveVoiceInput.vue'
import { isSpeechSupported } from '@/modules/voice/useSpeechRecognition'
import * as voiceApi from '@/api/voice'

// Minimal fake SpeechRecognition to drive the real-time flow deterministically.
class FakeRecognition {
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((e: unknown) => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  start(): void {
    // Emit an interim then a final result.
    this.onresult?.({
      resultIndex: 0,
      results: [{ 0: { transcript: '明天下午三点' }, isFinal: false }],
    })
    this.onresult?.({
      resultIndex: 0,
      results: [{ 0: { transcript: '明天下午三点提醒我联系房东' }, isFinal: true }],
    })
  }
  stop(): void {
    this.onend?.()
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition
  delete (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition
})

describe('LiveVoiceInput (real-time recognition)', () => {
  it('detects support from the browser API', () => {
    expect(isSpeechSupported()).toBe(false)
    ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = FakeRecognition
    expect(isSpeechSupported()).toBe(true)
  })

  it('shows recognized text live and parses it via the backend on stop', async () => {
    ;(window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = FakeRecognition
    const spy = vi.spyOn(voiceApi.voiceApi, 'fromText').mockResolvedValue({
      id: 'v1',
      status: 'waiting_user',
      transcript: '明天下午三点提醒我联系房东',
      candidate: null,
      schema_version: 'voice-task.v1',
      job_id: null,
      error: null,
      created_at: '',
    })

    const wrapper = mount(LiveVoiceInput)
    await wrapper.get('.mic').trigger('click') // start → fake emits results
    expect(wrapper.text()).toContain('明天下午三点提醒我联系房东')

    await wrapper.get('.mic.listening').trigger('click') // stop → parse
    await new Promise((r) => setTimeout(r, 0))
    expect(spy).toHaveBeenCalledWith('明天下午三点提醒我联系房东')
    expect(wrapper.emitted('candidate')).toBeTruthy()
  })

  it('falls back to the recorder when the browser lacks recognition', () => {
    const wrapper = mount(LiveVoiceInput)
    // No SpeechRecognition on window → VoiceRecorder fallback is rendered.
    expect(wrapper.text()).toContain('开始录音')
    expect(wrapper.find('.mic').exists()).toBe(false)
  })
})
