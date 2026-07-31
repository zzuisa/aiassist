<script setup lang="ts">
// Sanitized Markdown preview (spec 005, US2, T057).
//
// Dependency-free and XSS-safe: all raw HTML in the source is escaped before any
// Markdown structure is applied, so no author or pasted markup can inject nodes.
// Fenced code gets a copy button; Mermaid and ECharts blocks are rendered with
// a local, strict visual renderer and retain an expandable source view.
import { computed, ref } from 'vue'
import VisualBlock from '@/modules/posts/VisualBlock.vue'

const props = defineProps<{ markdown: string }>()

interface Block {
  kind: 'html' | 'code' | 'mermaid' | 'visual-plan' | 'echarts' | 'formula'
  content: string
  lang?: string
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function inline(s: string): string {
  // Operates on already-escaped text; only introduces our own safe tags.
  const safeImageSource = (src: string): boolean =>
    /^https?:\/\//.test(src) || /^\/api\/v1\/posts\/[0-9a-f-]+\/visual-assets\/[0-9a-f-]+\.png$/i.test(src)
  return s
    .replace(/`([^`]+)`/g, (_m, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, (_m, c) => `<strong>${c}</strong>`)
    .replace(/(^|[^*])\*([^*]+)\*/g, (_m, p, c) => `${p}<em>${c}</em>`)
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_m, alt, src) =>
      safeImageSource(src) ? `<img alt="${alt}" src="${src}">` : escapeHtml(`![${alt}](${src})`),
    )
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, txt, href) =>
      /^https?:\/\//.test(href)
        ? `<a href="${href}" rel="noopener noreferrer nofollow" target="_blank">${txt}</a>`
        : escapeHtml(`[${txt}](${href})`),
    )
}

function renderMarkdownBlock(src: string, headingIndex: { value: number }): string {
  const lines = src.split('\n')
  const html: string[] = []
  let inList = false
  const closeList = (): void => {
    if (inList) {
      html.push('</ul>')
      inList = false
    }
  }
  for (const raw of lines) {
    const line = raw
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      closeList()
      const level = h[1].length
      html.push(
        `<h${level} data-outline-index="${headingIndex.value}">${inline(h[2])}</h${level}>`,
      )
      headingIndex.value += 1
      continue
    }
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) {
        html.push('<ul>')
        inList = true
      }
      html.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ''))}</li>`)
      continue
    }
    // Text reaching here is already HTML-escaped, so a blockquote's ">" marker
    // appears as "&gt;".
    if (/^\s*(&gt;|>)\s?/.test(line)) {
      closeList()
      html.push(`<blockquote>${inline(line.replace(/^\s*(&gt;|>)\s?/, ''))}</blockquote>`)
      continue
    }
    if (line.trim() === '') {
      closeList()
      continue
    }
    closeList()
    html.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  return html.join('\n')
}

const blocks = computed<Block[]>(() => {
  const source = props.markdown
  const out: Block[] = []
  const headingIndex = { value: 0 }
  const fence = /```([\w-]+)?\n([\s\S]*?)```/g
  let lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = fence.exec(source)) !== null) {
    if (m.index > lastIndex) {
      out.push({
        kind: 'html',
        content: renderMarkdownBlock(escapeHtml(source.slice(lastIndex, m.index)), headingIndex),
      })
    }
    const lang = (m[1] || '').toLowerCase()
    // Code/visual blocks are rendered through text nodes or strict renderers;
    // escaping their source here would corrupt JSON and Mermaid syntax.
    const code = m[2].replace(/\n$/, '')
    out.push({
      kind:
        lang === 'mermaid'
          ? 'mermaid'
          : lang === 'visual-plan'
            ? 'visual-plan'
            : lang === 'echarts'
              ? 'echarts'
              : 'code',
      content: code,
      lang,
    })
    lastIndex = fence.lastIndex
  }
  let tail = escapeHtml(source.slice(lastIndex))
  // Read-only formula blocks ($$ … $$) are surfaced as labelled source.
  const formula = /\$\$([\s\S]*?)\$\$/g
  const tailOut: Block[] = []
  let fLast = 0
  let fm: RegExpExecArray | null
  while ((fm = formula.exec(tail)) !== null) {
    if (fm.index > fLast)
      tailOut.push({
        kind: 'html',
        content: renderMarkdownBlock(tail.slice(fLast, fm.index), headingIndex),
      })
    tailOut.push({ kind: 'formula', content: fm[1].trim() })
    fLast = formula.lastIndex
  }
  if (fLast < tail.length)
    tailOut.push({ kind: 'html', content: renderMarkdownBlock(tail.slice(fLast), headingIndex) })
  return [...out, ...tailOut]
})

const copied = ref<number | null>(null)
const preview = ref<HTMLDivElement | null>(null)

function scrollToHeading(index: number): void {
  const container = preview.value
  const heading = container?.querySelector<HTMLElement>(`[data-outline-index="${index}"]`)
  if (!container || !heading) return
  const top = heading.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
  container.scrollTo({ top: Math.max(0, top - 16), behavior: 'smooth' })
  heading.classList.add('outline-target')
  window.setTimeout(() => heading.classList.remove('outline-target'), 1400)
}

defineExpose({ scrollToHeading })
async function copy(text: string, i: number): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = i
    setTimeout(() => (copied.value = null), 1500)
  } catch {
    /* clipboard unavailable — ignore */
  }
}
</script>

<template>
  <div ref="preview" class="md-preview">
    <template
      v-for="(b, i) in blocks"
      :key="i"
    >
      <!-- eslint-disable vue/no-v-html -- b.content is fully HTML-escaped in renderMarkdownBlock before any tags are added, so it cannot inject markup -->
      <div
        v-if="b.kind === 'html'"
        class="md-body"
        v-html="b.content"
      />
      <!-- eslint-enable vue/no-v-html -->
      <VisualBlock
        v-else-if="b.kind === 'mermaid'"
        kind="mermaid"
        :source="b.content"
        caption="流程图（Mermaid）"
      />
      <VisualBlock
        v-else-if="b.kind === 'visual-plan'"
        kind="visual-plan"
        :source="b.content"
        caption="文章要点图"
      />
      <VisualBlock
        v-else-if="b.kind === 'echarts'"
        kind="echarts"
        :source="b.content"
        caption="数据图表"
      />
      <figure
        v-else-if="b.kind === 'formula'"
        class="md-special"
      >
        <figcaption>公式（只读）</figcaption>
        <pre>{{ b.content }}</pre>
      </figure>
      <div
        v-else
        class="md-code"
      >
        <button
          type="button"
          class="md-copy"
          @click="copy(b.content, i)"
        >
          {{ copied === i ? '已复制' : '复制' }}
        </button>
        <pre><code>{{ b.content }}</code></pre>
      </div>
    </template>
  </div>
</template>

<style scoped>
.md-preview {
  padding: var(--space-4);
  overflow-y: auto;
  line-height: 1.7;
}
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3) {
  margin: 1em 0 0.5em;
}
.md-body :deep(.outline-target) {
  border-radius: var(--radius-sm);
  background: var(--color-accent-soft, #eef2ff);
  transition: background 0.25s ease;
}
.md-body :deep(a) {
  color: var(--color-accent, #4f46e5);
}
.md-body :deep(code) {
  background: var(--color-surface-muted, #f1f5f9);
  padding: 0.1em 0.3em;
  border-radius: 4px;
}
.md-body :deep(img) {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1rem auto;
  border: 1px solid var(--color-border, #e2e8f0);
  border-radius: var(--radius-md, 10px);
}
.md-code {
  position: relative;
  margin: var(--space-3) 0;
}
.md-code pre,
.md-special pre {
  background: var(--color-surface-muted, #0f172a);
  color: var(--color-code-text, #e2e8f0);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: 0;
}
.md-copy {
  position: absolute;
  top: 6px;
  right: 6px;
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  border: none;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  cursor: pointer;
}
.md-special {
  margin: var(--space-3) 0;
}
.md-special figcaption {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin-bottom: 0.25rem;
}
</style>
