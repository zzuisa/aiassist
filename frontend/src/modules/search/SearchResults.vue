<script setup lang="ts">
import { TYPE_LABELS, type SearchResponse } from '@/api/search'

// Highlights arrive as server-escaped strings wrapping matches in <mark>…</mark>.
// We parse them into text/mark segments and render with plain interpolation, so
// there is no v-html and no XSS surface even if the server contract changes.
defineProps<{ results: SearchResponse | null; loading: boolean; pendingHint: boolean }>()

interface Segment {
  text: string
  mark: boolean
}

function toSegments(highlight: string): Segment[] {
  const segments: Segment[] = []
  const regex = /<mark>(.*?)<\/mark>/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = regex.exec(highlight)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ text: decode(highlight.slice(lastIndex, match.index)), mark: false })
    }
    segments.push({ text: decode(match[1]), mark: true })
    lastIndex = regex.lastIndex
  }
  if (lastIndex < highlight.length) {
    segments.push({ text: decode(highlight.slice(lastIndex)), mark: false })
  }
  return segments
}

// Decode the entity-escaping the server applied (safe: output is text, not HTML).
function decode(s: string): string {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
}
</script>

<template>
  <div class="results">
    <p
      v-if="loading"
      class="muted"
    >
      搜索中…
    </p>
    <p
      v-else-if="pendingHint"
      class="pending"
      role="status"
    >
      部分内容仍在建立索引…
    </p>

    <template v-if="results && results.groups.length">
      <section
        v-for="group in results.groups"
        :key="group.type"
        aria-label="搜索结果分组"
      >
        <h3>{{ TYPE_LABELS[group.type] ?? group.type }} ({{ group.items.length }})</h3>
        <ul>
          <li
            v-for="item in group.items"
            :key="item.entity.id"
            class="result"
          >
            <span class="title">{{ item.title }}</span>
            <span
              v-for="(h, i) in item.highlights"
              :key="i"
              class="highlight"
            >
              <template
                v-for="(seg, j) in toSegments(h)"
                :key="j"
              >
                <mark v-if="seg.mark">{{ seg.text }}</mark>
                <template v-else>{{ seg.text }}</template>
              </template>
            </span>
            <span
              v-if="item.category"
              class="cat"
            >{{ item.category }}</span>
          </li>
        </ul>
      </section>
    </template>

    <p
      v-else-if="results && !loading"
      class="empty"
    >
      未找到匹配结果。试试其他关键词或清除筛选。
    </p>
  </div>
</template>

<style scoped>
.results {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
h3 {
  font-size: 0.9rem;
  margin: var(--space-2) 0;
}
ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.result {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.title {
  font-weight: 500;
}
.highlight {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.highlight :deep(mark) {
  background: color-mix(in srgb, var(--status-due-soon) 40%, transparent);
  color: inherit;
}
.cat {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}
.muted,
.empty,
.pending {
  color: var(--color-text-muted);
}
</style>
