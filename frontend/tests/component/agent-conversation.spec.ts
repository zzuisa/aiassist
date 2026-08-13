import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConversationPanel, {
  type ConversationPanelMessage,
} from '@/components/agent/ConversationPanel.vue'

function message(overrides: Partial<ConversationPanelMessage> = {}): ConversationPanelMessage {
  return {
    id: 'msg-1',
    role: 'user',
    kind: 'text',
    content: { text: 'hi' },
    turn_id: null,
    created_at: '2026-08-10T12:00:00Z',
    ...overrides,
  }
}

describe('Agent ConversationPanel', () => {
  it('shows an empty-state guide when there is no history and nothing is loading', () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: false, error: '' },
    })

    expect(wrapper.text()).toContain('开始一次新对话')
  })

  it('shows a loading state instead of the empty guide while history loads', () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: true, sending: false, error: '' },
    })

    expect(wrapper.find('[role="status"]').text()).toContain('正在加载会话')
    expect(wrapper.text()).not.toContain('开始一次新对话')
  })

  it('shows an error banner when an error is present', () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: false, error: '消息发送失败，请重试。' },
    })

    expect(wrapper.find('[role="alert"]').text()).toBe('消息发送失败，请重试。')
  })

  it('renders an optimistic pending user message', () => {
    const wrapper = mount(ConversationPanel, {
      props: {
        messages: [message({ pending: true })],
        loading: false,
        sending: true,
        error: '',
      },
    })

    const bubble = wrapper.find('.message.role-user')
    expect(bubble.text()).toContain('hi')
    expect(bubble.text()).toContain('发送中…')
    expect(bubble.classes()).toContain('pending')
  })

  it('renders an assistant text reply', () => {
    const wrapper = mount(ConversationPanel, {
      props: {
        messages: [
          message({ id: 'u-1', role: 'user', content: { text: '你好' } }),
          message({
            id: 'a-1',
            role: 'assistant',
            content: { text: '你好！我可以帮你查询、分析你的内容和日程。' },
          }),
        ],
        loading: false,
        sending: false,
        error: '',
      },
    })

    const assistantBubble = wrapper.find('.message.role-assistant')
    expect(assistantBubble.exists()).toBe(true)
    expect(assistantBubble.text()).toContain('你好！我可以帮你查询')
  })

  it('renders clarification and pending-confirmation guidance', () => {
    const wrapper = mount(ConversationPanel, {
      props: {
        messages: [
          message({ id: 'clarify', role: 'assistant', kind: 'clarification', content: { text: '需要处理哪几篇？' } }),
          message({ id: 'result', role: 'assistant', kind: 'result', content: { text: '已生成预览', task_status: 'waiting_confirmation' } }),
        ],
        loading: false,
        sending: false,
        error: '',
      },
    })
    expect(wrapper.text()).toContain('需要你补充信息后才能继续')
    expect(wrapper.text()).toContain('确认前不会写入')
  })

  it('submits the draft on Enter and clears the input', async () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: false, error: '' },
    })

    const textarea = wrapper.get('textarea')
    await textarea.setValue('hi')
    await textarea.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('send')).toEqual([['hi']])
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('does not submit on Shift+Enter, allowing a newline instead', async () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: false, error: '' },
    })

    const textarea = wrapper.get('textarea')
    await textarea.setValue('hi')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })

    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('does not submit an empty or whitespace-only draft', async () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: false, error: '' },
    })

    const textarea = wrapper.get('textarea')
    await textarea.setValue('   ')
    await textarea.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('disables the composer while a send is already in flight', () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: true, error: '' },
    })

    expect((wrapper.get('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    expect((wrapper.get('button[type="submit"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
  })
})
