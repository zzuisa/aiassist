<script setup lang="ts">
// Candidate compare + apply (spec 005, US4, T093).
//
// Risk-first three-way review: conflicts (user and AI both changed a field to
// different values) are surfaced at the top and are never applied unless the
// user explicitly ticks them. The user picks exactly which fields to apply; the
// body is applied only when its checkbox is on, so a user's post-generation body
// edits are never silently overwritten. A final impact line states precisely
// what will change before the apply is sent under the current version lock.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  blogAIApi,
  classifyOptimizeError,
  type CandidateCompare,
  type FieldStatus,
} from '@/api/blogAI'
import BodyChangeReview from '@/modules/posts/BodyChangeReview.vue'

const route = useRoute()
const router = useRouter()
const postId = computed(() => route.params.id as string)
const candidateId = computed(() => route.params.candidateId as string)

const data = ref<CandidateCompare | null>(null)
const selected = ref<Set<string>>(new Set())
const busy = ref(false)
const error = ref('')

const STATUS_LABEL: Record<FieldStatus, string> = {
  unchanged: '未变化',
  user_only: '你已修改',
  ai_only: 'AI 建议',
  agreed: '一致',
  conflict: '冲突',
}
const STATUS_TONE: Record<FieldStatus, string> = {
  unchanged: 'neutral',
  user_only: 'user',
  ai_only: 'ai',
  agreed: 'done',
  conflict: 'conflict',
}

// Conflicts first, then AI-only, then the rest — risk-first ordering.
const RANK: Record<FieldStatus, number> = {
  conflict: 0,
  ai_only: 1,
  agreed: 2,
  user_only: 3,
  unchanged: 4,
}

const fields = computed(() => {
  const fd = data.value?.field_diff ?? {}
  return Object.entries(fd)
    .map(([path, entry]) => ({ path, ...entry }))
    .sort((a, b) => RANK[a.status] - RANK[b.status] || a.path.localeCompare(b.path))
})

const metadataFields = computed(() => fields.value.filter((field) => field.path !== 'markdown'))

const bodyEntry = computed(() =>
  fields.value.find((f) => f.path === 'markdown') ?? null,
)
const bodyCurrent = computed(() =>
  typeof bodyEntry.value?.current === 'string' ? bodyEntry.value.current : undefined,
)
const bodyCandidate = computed(() =>
  typeof bodyEntry.value?.candidate === 'string' ? bodyEntry.value.candidate : undefined,
)
const hasConflict = computed(() => fields.value.some((f) => f.status === 'conflict'))
const selectedCount = computed(() => selected.value.size)
const changedFieldCount = computed(() => fields.value.filter((field) => field.status !== 'unchanged').length)
const aiChangeCount = computed(() =>
  fields.value.filter((field) => field.status === 'ai_only' || field.status === 'agreed').length,
)
const conflictCount = computed(() => fields.value.filter((field) => field.status === 'conflict').length)

const FIELD_LABEL: Record<string, string> = {
  title: '标题',
  subtitle: '副标题',
  summary: '摘要',
  markdown: '正文',
  category_id: '分类',
  language: '语言',
  occurred_at: '发生时间',
}
const FIELD_HINT: Record<string, string> = {
  title: '文章在列表和阅读页显示的名称',
  summary: '帮助读者快速了解文章内容的简介',
  category_id: '文章所属的内容分类',
}

function fieldLabel(path: string): string {
  if (FIELD_LABEL[path]) return FIELD_LABEL[path]
  if (path.startsWith('structured_data.')) return `结构化信息 · ${path.slice('structured_data.'.length)}`
  return path
}

function fieldHint(path: string): string | undefined {
  return FIELD_HINT[path]
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '（空）'
  return typeof v === 'string' ? v : JSON.stringify(v, null, 2)
}

function toggle(path: string): void {
  const next = new Set(selected.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  selected.value = next
}

async function load(): Promise<void> {
  try {
    data.value = await blogAIApi.compareCandidate(candidateId.value)
    // Pre-select the safe, non-conflicting AI changes.
    const pre = new Set<string>()
    for (const f of fields.value) {
      if (f.status === 'ai_only' || f.status === 'agreed') pre.add(f.path)
    }
    selected.value = pre
  } catch (e) {
    error.value = '无法加载候选对比。'
    throw e
  }
}

async function decide(
  action: 'apply_all' | 'apply_fields' | 'keep_current' | 'reject' | 'copy',
): Promise<void> {
  if (!data.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await blogAIApi.decideCandidate(candidateId.value, {
      post_version: data.value.post_version,
      action,
      selected_fields: action === 'apply_fields' ? [...selected.value] : [],
    })
    // Back to the editor to review the applied result (or the untouched draft).
    router.push({
      name: 'blog-post-editor',
      params: { id: res.candidate.post_id || postId.value },
    })
  } catch (e) {
    const kind = classifyOptimizeError(e)
    error.value =
      kind === 'version_conflict'
        ? '文章已被修改，请返回重新加载后再决定。'
        : '操作失败，请稍后重试。'
    busy.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="compare">
    <header class="head">
      <div>
        <p class="eyebrow">
          AI 优化候选 · 请确认后应用
        </p>
        <h1>审核 AI 优化</h1>
        <p class="intro">
          先看正文的阅读效果，再选择要采纳的内容。当前文章不会自动改变。
        </p>
      </div>
      <RouterLink
        class="back"
        :to="{ name: 'blog-post-editor', params: { id: postId } }"
      >
        返回编辑
      </RouterLink>
    </header>

    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>

    <template v-if="data">
      <section
        class="review-summary"
        aria-label="优化结果摘要"
      >
        <div class="summary-item">
          <strong>{{ changedFieldCount }}</strong>
          <span>个字段有变化</span>
        </div>
        <div class="summary-item summary-item--ai">
          <strong>{{ aiChangeCount }}</strong>
          <span>项 AI 建议</span>
        </div>
        <div
          class="summary-item"
          :class="{ 'summary-item--conflict': conflictCount > 0 }"
        >
          <strong>{{ conflictCount }}</strong>
          <span>{{ conflictCount ? '项需要你判断' : '无冲突' }}</span>
        </div>
      </section>

      <p
        v-if="hasConflict"
        class="conflict-banner"
        role="alert"
      >
        ⚠ 有字段你和 AI 都做了修改（冲突）。勾选后将以 AI 版本覆盖你的修改。
      </p>

      <section
        v-if="bodyEntry"
        class="body-section"
      >
        <div class="section-heading">
          <label class="field-head body-select">
            <input
              type="checkbox"
              :checked="selected.has('markdown')"
              aria-label="应用正文"
              @change="toggle('markdown')"
            >
            <span>
              <strong>正文</strong>
              <small>选择后，AI 建议会替换当前正文</small>
            </span>
          </label>
          <span
            class="badge"
            :data-tone="STATUS_TONE[bodyEntry.status]"
          >{{ STATUS_LABEL[bodyEntry.status] }}</span>
        </div>
        <BodyChangeReview
          :current-markdown="bodyCurrent"
          :candidate-markdown="bodyCandidate"
          :unified-diff="data.body_diff.unified_diff"
          :hunks="data.body_diff.hunks"
          :changed="data.body_diff.changed"
        />
      </section>

      <section
        v-if="metadataFields.length"
        class="metadata-section"
      >
        <div class="section-title">
          <div>
            <h2>其他内容变化</h2>
            <p>逐项选择要采纳的标题、摘要和结构化信息。</p>
          </div>
        </div>
        <ul class="field-list">
          <li
            v-for="f in metadataFields"
            :key="f.path"
            class="field-row"
            :data-status="f.status"
          >
            <label class="field-head">
              <input
                type="checkbox"
                :checked="selected.has(f.path)"
                :aria-label="`应用 ${f.path}`"
                @change="toggle(f.path)"
              >
              <span class="field-copy">
                <strong>{{ fieldLabel(f.path) }}</strong>
                <small v-if="fieldHint(f.path)">{{ fieldHint(f.path) }}</small>
              </span>
              <span
                class="badge"
                :data-tone="STATUS_TONE[f.status]"
              >{{ STATUS_LABEL[f.status] }}</span>
            </label>
            <div
              class="values"
            >
              <div class="value-card value-card--current">
                <span>当前文章</span>
                <p>{{ fmt(f.current) }}</p>
              </div>
              <span
                class="arrow"
                aria-hidden="true"
              >→</span>
              <div class="value-card value-card--candidate">
                <span>AI 建议</span>
                <p>{{ fmt(f.candidate) }}</p>
              </div>
            </div>
          </li>
        </ul>
      </section>

      <p class="impact">
        将应用 <strong>{{ selectedCount }}</strong> 个字段。未勾选的字段保持你当前的内容不变。
      </p>

      <div class="actions">
        <button
          type="button"
          class="primary"
          :disabled="busy || selectedCount === 0"
          @click="decide('apply_fields')"
        >
          应用所选（{{ selectedCount }}）
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="busy"
          @click="decide('apply_all')"
        >
          全部采纳
        </button>
        <button
          type="button"
          class="ghost"
          :disabled="busy"
          @click="decide('copy')"
        >
          另存为副本
        </button>
        <button
          type="button"
          class="ghost danger"
          :disabled="busy"
          @click="decide('reject')"
        >
          放弃这次优化
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.compare {
  padding: var(--space-4);
  max-width: 960px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-4);
}
.head h1 {
  margin: 0;
  font-size: 1.35rem;
}
.eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--status-ai);
  font-size: 0.8rem;
  font-weight: 700;
}
.intro {
  max-width: 620px;
  margin: var(--space-2) 0 0;
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
.back {
  flex-shrink: 0;
  color: var(--color-text-muted);
  text-decoration: none;
}
.err {
  color: var(--status-danger, #dc2626);
}
.conflict-banner {
  margin: var(--space-3) 0;
  background: var(--status-danger-soft, #fee2e2);
  color: var(--status-danger, #b91c1c);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
}
.review-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
  margin: var(--space-4) 0;
}
.summary-item {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 0.82rem;
}
.summary-item strong {
  color: var(--color-text);
  font-size: 1.35rem;
}
.summary-item--ai {
  border-color: color-mix(in srgb, var(--status-ai) 32%, var(--color-border));
}
.summary-item--ai strong {
  color: var(--status-ai);
}
.summary-item--conflict {
  border-color: color-mix(in srgb, var(--status-urgent) 45%, var(--color-border));
}
.summary-item--conflict strong {
  color: var(--status-urgent);
}
.body-section,
.metadata-section {
  margin-top: var(--space-4);
}
.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.body-select {
  align-items: flex-start;
}
.body-select span {
  display: grid;
  gap: 2px;
}
.body-select small,
.field-copy small {
  color: var(--color-text-muted);
  font-size: 0.78rem;
  font-weight: 400;
}
.section-title {
  margin-bottom: var(--space-2);
}
.section-title h2 {
  margin: 0;
  font-size: 1rem;
}
.section-title p {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.field-list {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0;
}
.field-row {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  margin-bottom: var(--space-2);
}
.field-row[data-status='conflict'] {
  border-color: var(--status-danger, #dc2626);
}
.field-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.field-copy {
  display: grid;
  flex: 1;
  gap: 2px;
  min-width: 0;
}
.field-copy strong {
  font-size: 0.92rem;
}
.field-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.values {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: stretch;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.value-card {
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: 0.88rem;
}
.value-card > span {
  display: block;
  margin-bottom: var(--space-1);
  color: var(--color-text-muted);
  font-size: 0.75rem;
  font-weight: 700;
}
.value-card p {
  margin: 0;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.value-card--current {
  background: color-mix(in srgb, var(--status-urgent) 7%, var(--color-surface));
  border-left: 3px solid var(--status-urgent);
}
.value-card--candidate {
  background: color-mix(in srgb, var(--status-ai) 7%, var(--color-surface));
  border-left: 3px solid var(--status-ai);
}
.arrow {
  display: grid;
  place-items: center;
  color: var(--color-text-muted);
}
.badge {
  font-size: 0.75rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--color-surface-muted, #eee);
}
.badge[data-tone='conflict'] {
  background: var(--status-danger-soft, #fee2e2);
}
.badge[data-tone='ai'] {
  background: var(--status-info-soft, #dbeafe);
}
.badge[data-tone='user'] {
  background: var(--status-warn-soft, #fef3c7);
}
.badge[data-tone='done'] {
  background: var(--status-done-soft, #dcfce7);
}
.impact {
  margin: var(--space-3) 0;
}
.actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.primary {
  border: none;
  background: var(--status-normal);
  color: #fff;
}
.ghost {
  border: 1px solid var(--color-border);
  background: none;
  color: inherit;
}
.ghost.danger {
  color: var(--status-danger, #dc2626);
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
@media (max-width: 680px) {
  .compare {
    padding: var(--space-3);
  }
  .head {
    display: block;
  }
  .back {
    display: inline-block;
    margin-top: var(--space-2);
  }
  .review-summary {
    grid-template-columns: 1fr;
  }
  .values {
    grid-template-columns: 1fr;
  }
  .arrow {
    transform: rotate(90deg);
  }
}
</style>
