import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CaptureCard from '@/modules/captures/CaptureCard.vue'
import ProvenanceField from '@/modules/captures/ProvenanceField.vue'
import type { Capture, ProvenancedValue } from '@/api/captures'

function makeCapture(overrides: Partial<Capture> = {}): Capture {
  return {
    id: 'c1',
    type: 'item',
    private: true,
    fields: { title: { value: '厨房剪刀', source: 'user' } },
    assets: [],
    processing_status: 'ready',
    usage_status: 'unknown',
    version: 1,
    created_at: '',
    ...overrides,
  }
}

describe('CaptureCard', () => {
  it('shows a processing state inline (not a toast)', () => {
    const wrapper = mount(CaptureCard, {
      props: { capture: makeCapture({ processing_status: 'processing' }) },
    })
    expect(wrapper.text()).toContain('处理中')
  })

  it('flags possible duplicates', () => {
    const wrapper = mount(CaptureCard, {
      props: { capture: makeCapture({ possible_duplicate_of: 'c2' }) },
    })
    expect(wrapper.text()).toContain('可能重复')
  })

  it('shows failed state for a failed analysis but still renders the card', () => {
    const wrapper = mount(CaptureCard, {
      props: { capture: makeCapture({ processing_status: 'failed' }) },
    })
    expect(wrapper.text()).toContain('分析失败')
    expect(wrapper.text()).toContain('厨房剪刀')
  })
})

describe('ProvenanceField', () => {
  it('labels a user value as 你填写', () => {
    const field: ProvenancedValue = { value: '我的品牌', source: 'user' }
    const wrapper = mount(ProvenanceField, { props: { label: '品牌', field } })
    expect(wrapper.text()).toContain('你填写')
    expect(wrapper.text()).toContain('我的品牌')
  })

  it('labels an AI value with confidence and offers accept', async () => {
    const field: ProvenancedValue = { value: '不锈钢', source: 'ai', confidence: 0.7 }
    const wrapper = mount(ProvenanceField, { props: { label: '材质', field } })
    expect(wrapper.text()).toContain('AI 建议')
    expect(wrapper.text()).toContain('70%')
    await wrapper.get('.accept').trigger('click')
    expect(wrapper.emitted('accept')?.[0]).toEqual(['不锈钢'])
  })

  it('shows empty state when no value', () => {
    const wrapper = mount(ProvenanceField, { props: { label: '型号', field: undefined } })
    expect(wrapper.text()).toContain('未填写')
  })
})
