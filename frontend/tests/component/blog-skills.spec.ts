import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('@/api/blogSkills', async () => {
  const actual = (await vi.importActual('@/api/blogSkills')) as Record<string, unknown>
  return {
    ...actual,
    blogSkillsApi: {
      list: vi.fn(), get: vi.fn(), create: vi.fn(), updateMeta: vi.fn(),
      setEnabled: vi.fn(), copy: vi.fn(), remove: vi.fn(),
      listVersions: vi.fn(), addVersion: vi.fn(), restoreVersion: vi.fn(),
      recentRuns: vi.fn(), listDefaults: vi.fn(), setDefault: vi.fn(), removeDefault: vi.fn(),
    },
  }
})
const routerPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { skillId: 's1' }, query: {} }),
  useRouter: () => ({ push: routerPush }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' },
}))

import { blogSkillsApi, type Skill, type SkillConfig, type SkillVersion } from '@/api/blogSkills'
import SkillListPage from '@/modules/posts/SkillListPage.vue'
import SkillEditorPage from '@/modules/posts/SkillEditorPage.vue'
import SkillVersionsPage from '@/modules/posts/SkillVersionsPage.vue'

function fakeSkill(over: Partial<Skill> = {}): Skill {
  return {
    id: 's1', name: '默认优化', description: null, enabled: true,
    current_version: { id: 'v1', skill_id: 's1', version_number: 2, schema_version: 'blog-skill-config.v1',
      recommended_model: null, max_content_chars: 200000, long_content_strategy: 'reject',
      change_summary: null, created_at: '' },
    current_version_complete: true, default_scopes: [], created_at: '', updated_at: '', ...over,
  }
}

function cfg(): SkillConfig {
  return {
    schema_version: 'blog-skill-config.v1', applicable_content_classes: ['essay'],
    applicable_content_type_ids: [], processing_goal: 'g', content_rules: [], title_rules: [],
    summary_rules: [], body_structure: [], taxonomy_rules: [], keyword_rules: [],
    prohibitions: ['p'], field_policies: { title: 'suggest_only' }, output_fields: ['title'],
    output_schema: 'blog-optimization.v1', validation_rules: [], recommended_model: null,
    max_content_chars: 200000, long_content_strategy: 'reject',
  }
}

beforeEach(() => vi.clearAllMocks())

describe('SkillListPage', () => {
  it('filters by query and shows state + default badges', async () => {
    vi.mocked(blogSkillsApi.list).mockResolvedValue([
      fakeSkill({ id: 'a', name: '技术优化', default_scopes: [{ scope_type: 'global', scope_key: '*' }] }),
      fakeSkill({ id: 'b', name: '生活随笔', enabled: false, current_version_complete: false }),
    ])
    const w = mount(SkillListPage)
    await Promise.resolve()
    await Promise.resolve()

    expect(w.text()).toContain('技术优化')
    expect(w.text()).toContain('默认 global:*')
    expect(w.text()).toContain('停用')
    expect(w.text()).toContain('未完成')

    await w.find('.search').setValue('技术')
    expect(w.text()).toContain('技术优化')
    expect(w.text()).not.toContain('生活随笔')
  })

  it('confirms before disabling a skill that backs a default', async () => {
    vi.mocked(blogSkillsApi.list).mockResolvedValue([
      fakeSkill({ default_scopes: [{ scope_type: 'global', scope_key: '*' }] }),
    ])
    vi.mocked(blogSkillsApi.setEnabled).mockResolvedValue(fakeSkill({ enabled: false }))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const w = mount(SkillListPage)
    await Promise.resolve(); await Promise.resolve()

    // The disable button is the last action button.
    await w.findAll('button').at(-1)!.trigger('click')
    expect(confirm).toHaveBeenCalled()
    expect(blogSkillsApi.setEnabled).not.toHaveBeenCalled() // cancelled
    confirm.mockRestore()
  })
})

describe('SkillEditorPage', () => {
  it('loads the current version config into the form', async () => {
    vi.mocked(blogSkillsApi.get).mockResolvedValue(
      fakeSkill({ current_version: { ...fakeSkill().current_version!, config: { ...cfg(), processing_goal: '提升清晰度' } } }) as never,
    )
    const w = mount(SkillEditorPage)
    await Promise.resolve(); await Promise.resolve()
    expect((w.find('input[aria-label="名称"]').element as HTMLInputElement).value).toBe('默认优化')
    expect((w.find('textarea[aria-label="处理目标"]').element as HTMLTextAreaElement).value).toBe('提升清晰度')
  })

  it('blocks saving above the content-size safety ceiling', async () => {
    vi.mocked(blogSkillsApi.get).mockResolvedValue(
      fakeSkill({ current_version: { ...fakeSkill().current_version!, config: cfg() } }) as never,
    )
    const w = mount(SkillEditorPage)
    await Promise.resolve(); await Promise.resolve()

    await w.find('input[aria-label="内容上限"]').setValue(999999)
    await w.find('.primary').trigger('click')
    expect(w.find('.err').text()).toContain('安全上限')
    expect(blogSkillsApi.addVersion).not.toHaveBeenCalled()
  })

  it('saves an edit as a new version', async () => {
    vi.mocked(blogSkillsApi.get).mockResolvedValue(
      fakeSkill({ current_version: { ...fakeSkill().current_version!, config: cfg() } }) as never,
    )
    vi.mocked(blogSkillsApi.updateMeta).mockResolvedValue(fakeSkill())
    vi.mocked(blogSkillsApi.addVersion).mockResolvedValue({} as never)
    const w = mount(SkillEditorPage)
    await Promise.resolve(); await Promise.resolve()

    await w.find('.primary').trigger('click')
    await Promise.resolve()
    expect(blogSkillsApi.addVersion).toHaveBeenCalledWith('s1', expect.objectContaining({
      config: expect.objectContaining({ schema_version: 'blog-skill-config.v1' }),
    }))
  })
})

describe('SkillVersionsPage', () => {
  it('renders the immutable timeline and restores a version', async () => {
    const versions: SkillVersion[] = [
      { id: 'v2', skill_id: 's1', version_number: 2, schema_version: 'blog-skill-config.v1',
        recommended_model: null, max_content_chars: 200000, long_content_strategy: 'reject',
        change_summary: '改进', created_at: '', config: { ...cfg(), processing_goal: 'v2' } },
      { id: 'v1', skill_id: 's1', version_number: 1, schema_version: 'blog-skill-config.v1',
        recommended_model: null, max_content_chars: 200000, long_content_strategy: 'reject',
        change_summary: '初始', created_at: '', config: { ...cfg(), processing_goal: 'v1' } },
    ]
    vi.mocked(blogSkillsApi.listVersions).mockResolvedValue(versions)
    vi.mocked(blogSkillsApi.restoreVersion).mockResolvedValue(versions[0])
    const w = mount(SkillVersionsPage)
    await Promise.resolve(); await Promise.resolve()

    expect(w.text()).toContain('v2')
    expect(w.text()).toContain('v1')
    // Compare table marks processing_goal as changed between the two versions.
    expect(w.find('tr.changed').exists()).toBe(true)

    await w.findAll('button').at(-1)!.trigger('click')
    expect(blogSkillsApi.restoreVersion).toHaveBeenCalledWith('s1', 'v1')
  })
})
