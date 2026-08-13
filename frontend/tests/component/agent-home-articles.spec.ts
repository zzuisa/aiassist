import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ArticleResultCard from '@/components/agent/ArticleResultCard.vue'
import ConversationPanel from '@/components/agent/ConversationPanel.vue'

describe('Agent fresh landing and article results', () => {
  it('guides a new conversation without mentioning historical messages', () => {
    const wrapper = mount(ConversationPanel, {
      props: { messages: [], loading: false, sending: false, error: '' },
    })

    expect(wrapper.get('[role="log"]').text()).toContain('开始一次新对话')
    expect(wrapper.text()).not.toContain('加载会话')
  })

  it('renders an article result as one accessible navigation card', () => {
    const wrapper = mount(ArticleResultCard, {
      props: {
        article: {
          id: 'post-1', title: '可打开的文章', link: '/blog/post-1/view',
          category: '技术', tags: ['Agent'], published_at: null, updated_at: null, status: 'private',
        },
      },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    expect(wrapper.text()).toContain('可打开的文章')
    expect(wrapper.text()).toContain('打开查看')
    expect(wrapper.attributes('aria-label')).toBe('查看文章：可打开的文章')
  })
})
