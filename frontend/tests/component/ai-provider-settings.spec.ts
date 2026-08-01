import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/settings', () => ({
  settingsApi: {
    get: vi.fn(),
    patch: vi.fn(),
    changePassword: vi.fn(),
    getMemory: vi.fn().mockResolvedValue({ items: [] }),
    putMemory: vi.fn(),
  },
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ logout: vi.fn() }),
}))

import { settingsApi, type UserSettings } from '@/api/settings'
import SettingsPage from '@/modules/settings/SettingsPage.vue'

const baseSettings: UserSettings = {
  user: {
    id: 'u1',
    email: 'owner@example.test',
    display_name: 'Owner',
    timezone: 'Europe/Berlin',
    locale: 'zh-CN',
    notification_preferences: {},
  },
  notification_preferences: {
    in_app_enabled: true,
    email_enabled: false,
    critical_email_enabled: true,
    quiet_hours_start: null,
    quiet_hours_end: null,
  },
  dependencies: {
    mail: { configured: false, state: 'unconfigured' },
    llm: { configured: true, state: 'ready', provider_key: 'openai' },
    radio: { configured: true, state: 'ready', provider_key: 'radio' },
    speech: { configured: false, state: 'unconfigured' },
    storage: { configured: true, state: 'ready' },
  },
  ai_optimization: {
    default_provider: 'radio',
    version: 1,
    providers: [
      {
        key: 'radio',
        label: 'Radio（Gemini 轻量正文优化）',
        configured: true,
        state: 'ready',
      },
      {
        key: 'aiassist',
        label: 'AI Assist（完整优化）',
        configured: true,
        state: 'ready',
      },
    ],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(settingsApi.get).mockResolvedValue(structuredClone(baseSettings))
  vi.mocked(settingsApi.patch).mockResolvedValue({
    ...structuredClone(baseSettings),
    ai_optimization: {
      ...baseSettings.ai_optimization,
      default_provider: 'aiassist',
    },
  })
})

describe('article AI provider settings', () => {
  it('defaults to Radio and persists an AI Assist selection', async () => {
    const wrapper = mount(SettingsPage, {
      global: {
        stubs: {
          DependencyBadge: { template: '<div />' },
          MemorySettings: { template: '<div />' },
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    await flushPromises()

    const select = wrapper.find('select[aria-label="默认 AI 优化服务"]')
    expect((select.element as HTMLSelectElement).value).toBe('radio')
    await select.setValue('aiassist')
    const saveButton = wrapper
      .findAll('button')
      .find((button) => button.text() === '保存默认优化服务')
    await saveButton!.trigger('click')
    await flushPromises()

    expect(settingsApi.patch).toHaveBeenCalledWith({
      display_name: 'Owner',
      timezone: 'Europe/Berlin',
      ai_optimization: { default_provider: 'aiassist' },
    })
  })
})
