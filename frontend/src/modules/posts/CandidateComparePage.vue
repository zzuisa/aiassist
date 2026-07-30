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
import RevisionDiff from '@/modules/posts/RevisionDiff.vue'

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

const bodyEntry = computed(() =>
  fields.value.find((f) => f.path === 'markdown') ?? null,
)
const hasConflict = computed(() => fields.value.some((f) => f.status === 'conflict'))
const selectedCount = computed(() => selected.value.size)

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '（空）'
  return typeof v === 'string' ? v : JSON.stringify(v)
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
      <h1>审核 AI 优化</h1>
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
      <p
        v-if="hasConflict"
        class="conflict-banner"
        role="alert"
      >
        ⚠ 有字段你和 AI 都做了修改（冲突）。勾选后将以 AI 版本覆盖你的修改。
      </p>

      <ul class="field-list">
        <li
          v-for="f in fields"
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
            <span class="field-name">{{ f.path }}</span>
            <span
              class="badge"
              :data-tone="STATUS_TONE[f.status]"
            >{{ STATUS_LABEL[f.status] }}</span>
          </label>
          <div
            v-if="f.path !== 'markdown'"
            class="values"
          >
            <span class="from">当前：{{ fmt(f.current) }}</span>
            <span class="arrow">→</span>
            <span class="to">AI：{{ fmt(f.candidate) }}</span>
          </div>
        </li>
      </ul>

      <section
        v-if="bodyEntry && data.body_diff.changed"
        class="body-diff"
      >
        <h2>正文改动（当前 → AI）</h2>
        <RevisionDiff
          :unified-diff="data.body_diff.unified_diff"
          hide-actions
        />
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
          全部应用
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
          放弃候选
        </button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.compare {
  padding: var(--space-4);
  max-width: 820px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.head h1 {
  font-size: 1.2rem;
  margin: 0;
}
.back {
  color: var(--color-text-muted);
  text-decoration: none;
}
.err {
  color: var(--status-danger, #dc2626);
}
.conflict-banner {
  background: var(--status-danger-soft, #fee2e2);
  color: var(--status-danger, #b91c1c);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
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
.field-name {
  font-weight: 600;
  flex: 1;
}
.values {
  margin-top: 0.35rem;
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  font-size: 0.9rem;
  color: var(--color-text-muted);
}
.arrow {
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
.body-diff h2 {
  font-size: 1rem;
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
</style>
