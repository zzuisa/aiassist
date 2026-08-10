import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MarkdownPreview from '@/modules/posts/MarkdownPreview.vue'

// Source→display fidelity for the MVP supported-block matrix. The preview is the
// deterministic, testable half of the source/rich round-trip; it must render
// every supported block and must never emit raw author HTML.

function render(markdown: string) {
  return mount(MarkdownPreview, { props: { markdown } })
}

describe('MarkdownPreview supported blocks', () => {
  it('renders headings', () => {
    const w = render('# H1\n## H2')
    expect(w.find('h1').text()).toBe('H1')
    expect(w.find('h2').text()).toBe('H2')
    expect(w.find('h1').attributes('data-outline-index')).toBe('0')
    expect(w.find('h2').attributes('data-outline-index')).toBe('1')
  })

  it('exposes outline navigation to the matching preview heading', () => {
    const w = render('# H1\n\n正文\n\n## H2')
    const container = w.find('.md-preview').element as HTMLDivElement
    container.scrollTo = vi.fn()
    ;(w.vm as unknown as { scrollToHeading: (index: number) => void }).scrollToHeading(1)
    expect(container.scrollTo).toHaveBeenCalled()
    expect(w.find('h2').classes()).toContain('outline-target')
  })

  it('renders bold, italic and inline code', () => {
    const w = render('**b** and *i* and `c`')
    expect(w.find('strong').text()).toBe('b')
    expect(w.find('em').text()).toBe('i')
    expect(w.find('code').text()).toBe('c')
  })

  it('renders unordered lists', () => {
    const w = render('- a\n- b')
    expect(w.findAll('li').map((li) => li.text())).toEqual(['a', 'b'])
  })

  it('renders blockquotes', () => {
    const w = render('> quoted')
    expect(w.find('blockquote').text()).toBe('quoted')
  })

  it('renders safe links with rel/target', () => {
    const w = render('[t](https://x.io)')
    const a = w.find('a')
    expect(a.attributes('href')).toBe('https://x.io')
    expect(a.attributes('rel')).toContain('noopener')
  })

  it('renders a fenced code block with a copy button', () => {
    const w = render('```\ncode line\n```')
    expect(w.find('.md-code pre').text()).toContain('code line')
    expect(w.find('.md-copy').exists()).toBe(true)
  })

  it('shows mermaid as read-only labelled source, not rendered', () => {
    const w = render('```mermaid\ngraph TD; A-->B\n```')
    expect(w.find('.md-special figcaption').text()).toContain('Mermaid')
    expect(w.text()).toContain('graph TD')
  })

  it('shows formula blocks as read-only labelled source', () => {
    const w = render('$$\nE=mc^2\n$$')
    expect(w.find('.md-special figcaption').text()).toContain('公式')
    expect(w.text()).toContain('E=mc^2')
  })
})

describe('MarkdownPreview safety', () => {
  it('escapes raw HTML instead of rendering it', () => {
    const w = render('<script>alert(1)</script> and <b>x</b>')
    expect(w.find('script').exists()).toBe(false)
    // The angle brackets survive as text, not as elements.
    expect(w.text()).toContain('<script>')
    expect(w.text()).toContain('<b>x</b>')
  })

  it('does not turn a javascript: link into an anchor', () => {
    const w = render('[x](javascript:alert(1))')
    expect(w.find('a').exists()).toBe(false)
    expect(w.text()).toContain('javascript:alert(1)')
  })
})
