import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/aiConfig', () => ({
  aiConfigApi: {
    list: vi.fn(),
    get: vi.fn(),
    createPrompt: vi.fn(),
    createSkill: vi.fn(),
    activate: vi.fn(),
    dryRun: vi.fn(),
    listBindings: vi.fn(),
  },
}))

import { aiConfigApi } from '@/api/aiConfig'
import AIConfigPage from '@/modules/settings/AIConfigPage.vue'

const moduleDetail = {
  key: 'conversation_route',
  title: '对话 Agent 路由',
  baseline_instruction: '根据语义选择一个工具。',
  allowed_tool_keys: ['posts.list_recent'],
  active_prompt_version_id: null,
  active_skill_version_id: null,
  safety_boundary: '权限和确认由平台强制执行。',
  prompt_versions: [],
  skill_versions: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(aiConfigApi.list).mockResolvedValue([moduleDetail])
  vi.mocked(aiConfigApi.get).mockResolvedValue(moduleDetail)
  vi.mocked(aiConfigApi.activate).mockResolvedValue(undefined)
  vi.mocked(aiConfigApi.listBindings).mockResolvedValue([])
})

describe('AI configuration centre', () => {
  it('creates and activates a versioned article-query skill', async () => {
    vi.mocked(aiConfigApi.createSkill).mockResolvedValue({
      id: 'skill-v1',
      version_number: 1,
      name: '文章查询',
      instruction: '使用默认参数',
      parameter_defaults: { 'posts.list_recent': { limit: 10 } },
      created_at: '2026-08-15T00:00:00Z',
    })
    const wrapper = mount(AIConfigPage)
    await flushPromises()

    const save = wrapper.findAll('fieldset')[1].find('button')
    await save.trigger('click')
    await flushPromises()

    expect(aiConfigApi.createSkill).toHaveBeenCalledWith(
      'conversation_route',
      expect.objectContaining({
        parameter_defaults: { 'posts.list_recent': { limit: 10 } },
      }),
    )
    expect(aiConfigApi.activate).toHaveBeenCalledWith('conversation_route', {
      prompt_version_id: null,
      skill_version_id: 'skill-v1',
    })
  })

  it('shows a non-writing dry-run result', async () => {
    vi.mocked(aiConfigApi.dryRun).mockResolvedValue({
      module_key: 'conversation_route',
      status: 'routed',
      selected_tool: 'posts.list_recent',
      arguments: { limit: 10 },
      message: '未执行工具。',
    })
    const wrapper = mount(AIConfigPage)
    await flushPromises()

    const run = wrapper.findAll('button').find((button) => button.text() === '运行测试')
    await run!.trigger('click')
    await flushPromises()

    expect(aiConfigApi.dryRun).toHaveBeenCalledWith('conversation_route', '查一下最近文章')
    expect(wrapper.find('pre').text()).toContain('posts.list_recent')
  })
})
