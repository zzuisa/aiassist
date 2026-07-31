import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref, type Ref } from 'vue'

// Mock the API modules the editor pieces depend on.
vi.mock('@/api/blogQueries', () => ({
  contentTypesApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: 'ct1', content_class: 'technical', key: 'tut', name: '教程',
        description: null, field_schema: {}, sort_order: 0, enabled: true,
        schema_version: 1, created_at: '', updated_at: '',
      },
    ]),
  },
}))
vi.mock('@/api/posts', async () => {
  const actual = (await vi.importActual('@/api/posts')) as Record<string, unknown>
  return { ...actual, postsApi: { patch: vi.fn(), get: vi.fn() } }
})

import { postsApi, type Post } from '@/api/posts'
import { usePostAutosave } from '@/modules/posts/usePostAutosave'
import MarkdownSourceEditor from '@/modules/posts/MarkdownSourceEditor.vue'
import PostPropertySidebar from '@/modules/posts/PostPropertySidebar.vue'
import { editorModeFromApi, editorModeToApi } from '@/modules/posts/editorMode'

function fakePost(over: Partial<Post> = {}): Post {
  return {
    id: 'p1', title: 't', subtitle: null, summary: null, markdown: 'body',
    status: 'draft', slug: null, content_status: 'draft', content_class: 'technical',
    content_type_id: null, category_id: null, tag_ids: [], keyword_ids: [],
    language: 'zh-CN', editor_mode: 'source', occurred_at: null, location: null,
    project: null, structured_data: {}, source_summary: [], ai_summary: null,
    version: 3, current_revision_id: null, created_at: '', updated_at: '',
    published_at: null, ...over,
  }
}

beforeEach(() => vi.clearAllMocks())

describe('editor mode mapping', () => {
  it('maps API modes without sending the unsupported source value', () => {
    expect(editorModeFromApi('rich')).toBe('rich')
    expect(editorModeFromApi('markdown')).toBe('source')
    expect(editorModeToApi('source')).toBe('markdown')
    expect(editorModeToApi('split')).toBe('split')
  })
})

describe('MarkdownSourceEditor', () => {
  it('emits the edited value', async () => {
    const w = mount(MarkdownSourceEditor, { props: { modelValue: 'a' } })
    await w.find('textarea').setValue('a b')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['a b'])
  })

  it('exposes chapter navigation that moves the caret and scrolls', () => {
    const markdown = '# 第一章\n正文\n## 第二章\n内容'
    const w = mount(MarkdownSourceEditor, { props: { modelValue: markdown } })
    const textarea = w.find('textarea').element
    textarea.scrollTo = vi.fn()
    const offset = markdown.indexOf('## 第二章')
    ;(w.vm as unknown as { scrollToPosition: (line: number, offset: number) => void })
      .scrollToPosition(3, offset)
    expect(textarea.selectionStart).toBe(offset)
    expect(textarea.scrollTo).toHaveBeenCalled()
  })
})

describe('PostPropertySidebar', () => {
  it('emits a content_class patch and resets content_type', async () => {
    const w = mount(PostPropertySidebar, { props: { post: fakePost() } })
    const select = w.findAll('select')[0]
    await select.setValue('life')
    const patches = w.emitted('patch')! as Array<[Record<string, unknown>]>
    expect(patches.at(-1)![0]).toEqual({ content_class: 'life', content_type_id: null })
  })

  it('emits a status patch', async () => {
    const w = mount(PostPropertySidebar, { props: { post: fakePost() } })
    const statusSelect = w.findAll('select')[2]
    await statusSelect.setValue('completed')
    const patches = w.emitted('patch')! as Array<[Record<string, unknown>]>
    expect(patches.at(-1)![0]).toEqual({ content_status: 'completed' })
  })
})

// Harness component so the composable runs inside a real setup() scope.
function mountAutosave(post: Ref<Post | null>) {
  const api = {} as ReturnType<typeof usePostAutosave>
  const Comp = defineComponent({
    setup() {
      Object.assign(api, usePostAutosave(post))
      return () => h('div')
    },
  })
  const wrapper = mount(Comp)
  return { api, wrapper }
}

describe('usePostAutosave', () => {
  it('transitions dirty→saving→saved and clears sent fields', async () => {
    vi.useFakeTimers()
    const post = ref<Post | null>(fakePost())
    vi.mocked(postsApi.patch).mockResolvedValue(fakePost({ version: 4, markdown: 'x' }))
    const { api } = mountAutosave(post)

    api.update({ markdown: 'x' })
    expect(api.state.value).toBe('dirty')
    expect(api.isDirty()).toBe(true)

    await vi.advanceTimersByTimeAsync(1300)
    expect(postsApi.patch).toHaveBeenCalledWith('p1', { markdown: 'x' }, 3)
    expect(api.state.value).toBe('saved')
    expect(api.isDirty()).toBe(false)
    vi.useRealTimers()
  })

  it('enters conflict state on a 409 and keeps the pending edit', async () => {
    const { ApiError } = await import('@/api/client')
    const post = ref<Post | null>(fakePost())
    vi.mocked(postsApi.patch).mockRejectedValue(
      new ApiError({ type: '', title: '', status: 409, code: 'version_conflict' }),
    )
    const { api } = mountAutosave(post)
    api.update({ title: 'new' })
    const ok = await api.save()
    expect(ok).toBe(false)
    expect(api.state.value).toBe('conflict')
    expect(api.isDirty()).toBe(true) // edit is never lost
  })
})
