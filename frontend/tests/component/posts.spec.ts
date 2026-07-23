import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RevisionDiff from '@/modules/posts/RevisionDiff.vue'

const SAMPLE_DIFF = `--- current
+++ candidate
@@ -1,2 +1,2 @@
 line1
-line2
+line2 changed
`

describe('RevisionDiff', () => {
  it('colors added and removed lines', () => {
    const wrapper = mount(RevisionDiff, { props: { unifiedDiff: SAMPLE_DIFF } })
    expect(wrapper.find('.line.add').exists()).toBe(true)
    expect(wrapper.find('.line.remove').exists()).toBe(true)
    expect(wrapper.find('.line.meta').exists()).toBe(true)
  })

  it('emits apply/ignore/regenerate explicitly (AI never auto-applies)', async () => {
    const wrapper = mount(RevisionDiff, { props: { unifiedDiff: SAMPLE_DIFF } })
    await wrapper.get('.apply').trigger('click')
    expect(wrapper.emitted('apply')).toBeTruthy()
    const buttons = wrapper.findAll('button')
    await buttons.find((b) => b.text() === '忽略')!.trigger('click')
    expect(wrapper.emitted('ignore')).toBeTruthy()
    await buttons.find((b) => b.text() === '重新生成')!.trigger('click')
    expect(wrapper.emitted('regenerate')).toBeTruthy()
  })

  it('shows the changed content in the diff', () => {
    const wrapper = mount(RevisionDiff, { props: { unifiedDiff: SAMPLE_DIFF } })
    expect(wrapper.text()).toContain('line2 changed')
  })
})
