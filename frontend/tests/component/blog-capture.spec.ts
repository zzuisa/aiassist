import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// Mock the capture API so the dialogs can be exercised without a backend.
vi.mock('@/api/blogCapture', async () => {
  const actual = (await vi.importActual('@/api/blogCapture')) as Record<string, unknown>
  return {
    ...actual,
    blogCaptureApi: {
      blank: vi.fn(),
      clipboard: vi.fn(),
      url: vi.fn(),
      quick: vi.fn(),
      getSource: vi.fn(),
      retrySource: vi.fn(),
      snapshotAccess: vi.fn(),
    },
  }
})

import { blogCaptureApi } from '@/api/blogCapture'
import PostCreateDialog from '@/modules/posts/PostCreateDialog.vue'
import QuickCaptureDialog from '@/modules/posts/QuickCaptureDialog.vue'
import UrlCreateDialog from '@/modules/posts/UrlCreateDialog.vue'

const CAPTURE_RESULT = {
  post: {
    id: 'p1',
    title: 't',
    markdown: 'm',
    content_status: 'triage',
    content_class: 'quick',
    content_type_id: null,
    language: 'zh-CN',
    version: 1,
    created_at: '',
    updated_at: '',
  },
  source: {
    id: 's1',
    post_id: 'p1',
    source_type: 'quick',
    status: 'completed',
    detected_format: 'plain',
    original_url: null,
    original_title: null,
    original_text: 'm',
    normalized_markdown: 'm',
    user_note: null,
    metadata: {},
    has_snapshot: false,
    attempt_count: 0,
    captured_at: '',
    error: null,
  },
  job: null,
  warnings: [],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PostCreateDialog', () => {
  it('offers all four source options and emits the chosen one', async () => {
    const wrapper = mount(PostCreateDialog)
    const labels = wrapper.findAll('.source__label').map((n) => n.text())
    expect(labels).toEqual(['空白文章', '从剪贴板', '从网址', '快速记录'])
    await wrapper.findAll('.source')[3]!.trigger('click')
    expect(wrapper.emitted('select')![0]).toEqual(['quick'])
  })
})

describe('QuickCaptureDialog', () => {
  it('disables save until there is content', async () => {
    const wrapper = mount(QuickCaptureDialog)
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === '保存')!
    expect(saveBtn.attributes('disabled')).toBeDefined()
    await wrapper.find('textarea').setValue('记一笔')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
  })

  it('saves and emits created when "保存并编辑" is used', async () => {
    vi.mocked(blogCaptureApi.quick).mockResolvedValue(CAPTURE_RESULT as never)
    const wrapper = mount(QuickCaptureDialog)
    await wrapper.find('textarea').setValue('记一笔')
    await wrapper.findAll('button').find((b) => b.text() === '保存并编辑')!.trigger('click')
    await Promise.resolve()
    expect(blogCaptureApi.quick).toHaveBeenCalledOnce()
    expect(wrapper.emitted('saved')).toBeTruthy()
    expect(wrapper.emitted('created')![0]).toEqual(['p1'])
  })
})

describe('UrlCreateDialog', () => {
  it('keeps the save button disabled for a non-URL value', async () => {
    const wrapper = mount(UrlCreateDialog)
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === '保存并抓取')!
    expect(saveBtn.attributes('disabled')).toBeDefined()
    await wrapper.find('input[type="url"]').setValue('not a url')
    expect(saveBtn.attributes('disabled')).toBeDefined()
    await wrapper.find('input[type="url"]').setValue('https://example.com/a')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
  })

  it('shows a friendly message when the URL is rejected as unsafe', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(blogCaptureApi.url).mockRejectedValue(
      new ApiError({ type: '', title: '', status: 422, code: 'ip_not_public' }),
    )
    const wrapper = mount(UrlCreateDialog)
    await wrapper.find('input[type="url"]').setValue('http://169.254.169.254/')
    await wrapper.findAll('button').find((b) => b.text() === '保存并抓取')!.trigger('click')
    await Promise.resolve()
    await Promise.resolve()
    expect(wrapper.find('.url-error').text()).toContain('不被允许')
  })

  it('seeds the URL from the initialUrl prop (clipboard hand-off)', () => {
    const wrapper = mount(UrlCreateDialog, { props: { initialUrl: 'https://x.io/a' } })
    expect((wrapper.find('input[type="url"]').element as HTMLInputElement).value).toBe(
      'https://x.io/a',
    )
  })

  it('recognizes a Bilibili URL and submits it through the existing capture API', async () => {
    vi.mocked(blogCaptureApi.url).mockResolvedValue(CAPTURE_RESULT as never)
    const wrapper = mount(UrlCreateDialog)
    await wrapper.find('input[type="url"]').setValue(
      'https://www.bilibili.com/video/BV1abc123',
    )
    const submit = wrapper.findAll('button').find((b) => b.text() === '保存并转写')!
    expect(submit.exists()).toBe(true)
    await submit.trigger('click')
    await Promise.resolve()
    expect(blogCaptureApi.url).toHaveBeenCalledWith(
      expect.objectContaining({ url: 'https://www.bilibili.com/video/BV1abc123' }),
    )
    expect(wrapper.text()).toContain('正在后台处理并转写音视频')
  })

  it('shows the Radio unavailable message instead of a generic import failure', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(blogCaptureApi.url).mockRejectedValue(
      new ApiError({
        type: '', title: '', status: 503, code: 'RADIO_SERVICE_UNAVAILABLE',
      }),
    )
    const wrapper = mount(UrlCreateDialog, { props: { initialUrl: 'https://b23.tv/abc' } })
    await wrapper.findAll('button').find((b) => b.text() === '保存并转写')!.trigger('click')
    await Promise.resolve()
    await Promise.resolve()
    expect(wrapper.find('.url-error').text()).toBe(
      'B站音视频处理服务当前不可用，请稍后重试。',
    )
  })
})
