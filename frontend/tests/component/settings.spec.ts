import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DependencyBadge from '@/modules/settings/DependencyBadge.vue'
import type { DependencyState } from '@/api/settings'

describe('DependencyBadge', () => {
  it('shows configured state without exposing secrets', () => {
    const state: DependencyState = { configured: true, state: 'ready', provider_key: 'openai' }
    const wrapper = mount(DependencyBadge, { props: { label: 'AI 模型', state } })
    expect(wrapper.text()).toContain('已配置')
    expect(wrapper.text()).toContain('openai') // logical route only, not a key
  })

  it('shows unconfigured state', () => {
    const state: DependencyState = { configured: false, state: 'unconfigured', provider_key: null }
    const wrapper = mount(DependencyBadge, { props: { label: '邮件', state } })
    expect(wrapper.text()).toContain('未配置')
  })

  it('shows degraded state', () => {
    const state: DependencyState = { configured: true, state: 'degraded', provider_key: null }
    const wrapper = mount(DependencyBadge, { props: { label: '邮件', state } })
    expect(wrapper.text()).toContain('降级')
  })
})
