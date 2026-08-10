<script setup lang="ts">
// Human-readable body review. The unified diff remains useful as a durable
// contract, but it is deliberately transformed into plain-language change
// cards and rendered previews for people reviewing an article.
import { computed, ref } from 'vue'
import type { BodyDiffHunk } from '@/api/blogAI'
import MarkdownPreview from '@/modules/posts/MarkdownPreview.vue'

const props = defineProps<{
  currentMarkdown?: string
  candidateMarkdown?: string
  unifiedDiff: string
  hunks?: BodyDiffHunk[]
  changed: boolean
}>()

interface ChangeGroup {
  removed: string[]
  added: string[]
}

function parseUnifiedChanges(diff: string): ChangeGroup[] {
  const groups: ChangeGroup[] = []
  let removed: string[] = []
  let added: string[] = []

  const flush = (): void => {
    if (removed.length || added.length) {
      groups.push({ removed, added })
      removed = []
      added = []
    }
  }

  for (const line of diff.split('\n')) {
    if (line.startsWith('--- ') || line.startsWith('+++ ') || line.startsWith('@@')) continue
    if (line.startsWith('-')) {
      removed.push(line.slice(1))
    } else if (line.startsWith('+')) {
      added.push(line.slice(1))
    } else {
      flush()
    }
  }
  flush()
  return groups
}

function parseChanges(hunks: BodyDiffHunk[] | undefined, diff: string): ChangeGroup[] {
  if (hunks?.length) {
    return hunks.map((hunk) => ({
      removed: hunk.old_lines,
      added: hunk.new_lines,
    }))
  }
  return parseUnifiedChanges(diff)
}

const changes = computed(() => parseChanges(props.hunks, props.unifiedDiff))
const view = ref<'changes' | 'preview'>('changes')
const hasPreview = computed(
  () => typeof props.currentMarkdown === 'string' && typeof props.candidateMarkdown === 'string',
)
const removedLines = computed(() => changes.value.reduce((total, change) => total + change.removed.length, 0))
const addedLines = computed(() => changes.value.reduce((total, change) => total + change.added.length, 0))
</script>

<template>
  <section
    class="body-review"
    aria-labelledby="body-review-title"
  >
    <div class="body-review__summary">
      <div>
        <p class="body-review__eyebrow">
          正文变化
        </p>
        <h2 id="body-review-title">
          {{ changed ? `AI 建议了 ${changes.length || 1} 处调整` : '正文没有变化' }}
        </h2>
        <p class="body-review__explain">
          先看阅读效果，再决定是否应用。当前文章不会因为查看而改变。
        </p>
      </div>
      <div
        v-if="changed"
        class="body-review__counts"
        aria-label="正文变化统计"
      >
        <span><strong>{{ removedLines }}</strong> 处原文</span>
        <span><strong>{{ addedLines }}</strong> 处建议</span>
      </div>
    </div>

    <div
      v-if="changed"
      class="body-review__switch"
      role="tablist"
      aria-label="正文查看方式"
    >
      <button
        type="button"
        role="tab"
        :aria-selected="view === 'changes'"
        :class="{ active: view === 'changes' }"
        @click="view = 'changes'"
      >
        具体改了什么
      </button>
      <button
        v-if="hasPreview"
        type="button"
        role="tab"
        :aria-selected="view === 'preview'"
        :class="{ active: view === 'preview' }"
        @click="view = 'preview'"
      >
        文章阅读效果
      </button>
    </div>

    <div
      v-if="changed && view === 'changes'"
      class="change-list"
    >
      <article
        v-for="(change, index) in changes"
        :key="index"
        class="change-card"
      >
        <div class="change-card__title">
          <span class="change-card__number">{{ index + 1 }}</span>
          <strong>第 {{ index + 1 }} 处调整</strong>
        </div>
        <div class="change-card__columns">
          <div class="change-pane change-pane--removed">
            <span class="change-pane__label">当前文章</span>
            <p
              v-for="(line, lineIndex) in change.removed"
              :key="`removed-${lineIndex}`"
            >
              {{ line || '（空行）' }}
            </p>
            <p
              v-if="!change.removed.length"
              class="change-pane__empty"
            >
              这里是新增内容
            </p>
          </div>
          <div
            class="change-arrow"
            aria-hidden="true"
          >
            →
          </div>
          <div class="change-pane change-pane--added">
            <span class="change-pane__label">AI 建议</span>
            <p
              v-for="(line, lineIndex) in change.added"
              :key="`added-${lineIndex}`"
            >
              {{ line || '（空行）' }}
            </p>
            <p
              v-if="!change.added.length"
              class="change-pane__empty"
            >
              这里的内容将被移除
            </p>
          </div>
        </div>
      </article>
      <p
        v-if="!changes.length"
        class="body-review__fallback"
      >
        这次正文有变化，但服务没有提供可拆分的段落信息。
        <template v-if="hasPreview">
          请切换到“文章阅读效果”查看整体结果。
        </template>
      </p>
    </div>

    <div
      v-else-if="changed && view === 'preview' && hasPreview"
      class="preview-grid"
    >
      <article class="preview-card">
        <header>当前文章 <span>不会被修改</span></header>
        <div class="preview-card__body">
          <MarkdownPreview :markdown="currentMarkdown!" />
        </div>
      </article>
      <article class="preview-card preview-card--candidate">
        <header>AI 建议 <span>应用后效果</span></header>
        <div class="preview-card__body">
          <MarkdownPreview :markdown="candidateMarkdown!" />
        </div>
      </article>
    </div>

    <p
      v-else
      class="body-review__unchanged"
    >
      当前正文将保持不变。
    </p>
  </section>
</template>

<style scoped>
.body-review {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  overflow: hidden;
}
.body-review__summary {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4);
  background: color-mix(in srgb, var(--status-ai) 5%, var(--color-surface));
}
.body-review__eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--status-ai);
  font-size: 0.8rem;
  font-weight: 700;
}
.body-review h2 {
  margin: 0;
  font-size: 1.08rem;
}
.body-review__explain {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
  font-size: 0.88rem;
}
.body-review__counts {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
  color: var(--color-text-muted);
  font-size: 0.78rem;
  white-space: nowrap;
}
.body-review__counts strong {
  color: var(--color-text);
  font-size: 1rem;
}
.body-review__switch {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-4) 0;
  border-bottom: 1px solid var(--color-border);
}
.body-review__switch button {
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font: inherit;
}
.body-review__switch button.active {
  border-bottom-color: var(--status-ai);
  color: var(--status-ai);
  font-weight: 700;
}
.change-list {
  padding: var(--space-3) var(--space-4) var(--space-4);
}
.change-card {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border);
}
.change-card:last-child {
  border-bottom: 0;
}
.change-card__title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  font-size: 0.88rem;
}
.change-card__number {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--color-surface-2);
  color: var(--color-text-muted);
  font-size: 0.75rem;
}
.change-card__columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: stretch;
  gap: var(--space-2);
}
.change-pane {
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.change-pane--removed {
  background: color-mix(in srgb, var(--status-urgent) 8%, var(--color-surface));
  border-left: 3px solid var(--status-urgent);
}
.change-pane--added {
  background: color-mix(in srgb, var(--status-done) 9%, var(--color-surface));
  border-left: 3px solid var(--status-done);
}
.change-pane__label {
  display: block;
  margin-bottom: var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 700;
}
.change-pane p {
  margin: 0;
}
.change-pane p + p {
  margin-top: var(--space-1);
}
.change-pane__empty {
  color: var(--color-text-muted);
  font-style: italic;
}
.change-arrow {
  display: grid;
  place-items: center;
  color: var(--color-text-muted);
  font-size: 1.1rem;
}
.body-review__fallback,
.body-review__unchanged {
  margin: 0;
  padding: var(--space-4);
  color: var(--color-text-muted);
}
.preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4) var(--space-4);
}
.preview-card {
  min-width: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.preview-card header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-2);
  font-size: 0.85rem;
  font-weight: 700;
}
.preview-card header span {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 400;
}
.preview-card--candidate header {
  background: color-mix(in srgb, var(--status-ai) 10%, var(--color-surface));
}
.preview-card__body {
  height: 360px;
  overflow: auto;
}
.preview-card__body :deep(.md-preview) {
  padding: var(--space-3);
  font-size: 0.9rem;
}
@media (max-width: 680px) {
  .body-review__summary {
    display: block;
  }
  .body-review__counts {
    margin-top: var(--space-3);
  }
  .change-card__columns,
  .preview-grid {
    grid-template-columns: 1fr;
  }
  .change-arrow {
    transform: rotate(90deg);
  }
  .preview-card__body {
    height: 280px;
  }
}
</style>
