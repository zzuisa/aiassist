<script setup lang="ts">
// Version timeline + compare + restore + copy (spec 005, US4, T094).
//
// The revision chain is immutable: restoring never rewrites history, it appends
// a new `restore` revision. Pick any two revisions to see a body + field diff.
// "Create copy" forks the current article into a new independent draft.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { postsApi, type RevisionCompare, type RevisionSummary } from '@/api/posts'

const route = useRoute()
const router = useRouter()
const postId = computed(() => route.params.id as string)

const revisions = ref<RevisionSummary[]>([])
const fromId = ref<string | null>(null)
const toId = ref<string | null>(null)
const compare = ref<RevisionCompare | null>(null)
const busy = ref(false)
const error = ref('')
const version = ref(1)

const sourceLabel: Record<string, string> = {
  user: '手动编辑', user_edit: '手动编辑', ai: 'AI 草稿', ai_candidate: 'AI 候选',
  ai_applied: '应用 AI', capture: '采集', restore: '恢复', merge: '合并', import: '导入',
}

const canCompare = computed(() => fromId.value && toId.value && fromId.value !== toId.value)

async function load(): Promise<void> {
  revisions.value = await postsApi.listRevisions(postId.value)
  const post = await postsApi.get(postId.value)
  version.value = post.version
  if (revisions.value.length >= 2) {
    toId.value = revisions.value[0].id
    fromId.value = revisions.value[1].id
  }
}

async function runCompare(): Promise<void> {
  if (!canCompare.value) return
  busy.value = true
  error.value = ''
  try {
    compare.value = await postsApi.compareRevisions(postId.value, fromId.value!, toId.value!)
  } catch {
    error.value = '对比失败。'
  } finally {
    busy.value = false
  }
}

async function restore(revisionId: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const post = await postsApi.restoreRevision(postId.value, revisionId, version.value)
    version.value = post.version
    await load()
  } catch {
    error.value = '恢复失败，请刷新后重试。'
  } finally {
    busy.value = false
  }
}

async function createCopy(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const post = await postsApi.get(postId.value)
    const copy = await postsApi.create(`${post.title}（副本）`, post.markdown)
    router.push({ name: 'blog-post-editor', params: { id: copy.id } })
  } finally {
    busy.value = false
  }
}

const changedFields = computed(() =>
  compare.value ? Object.keys(compare.value.field_diff) : [],
)

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="versions">
    <header class="head">
      <h1>版本历史</h1>
      <div class="head-actions">
        <button
          type="button"
          class="ghost"
          :disabled="busy"
          @click="createCopy"
        >
          创建副本
        </button>
        <RouterLink
          class="back"
          :to="{ name: 'blog-post-editor', params: { id: postId } }"
        >
          返回编辑
        </RouterLink>
      </div>
    </header>

    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>

    <ul class="timeline">
      <li
        v-for="r in revisions"
        :key="r.id"
        class="rev-row"
      >
        <label class="pick">
          <input
            type="radio"
            name="from"
            :value="r.id"
            :checked="fromId === r.id"
            aria-label="对比起点"
            @change="fromId = r.id"
          >
          <span class="pick-label">起</span>
        </label>
        <label class="pick">
          <input
            type="radio"
            name="to"
            :value="r.id"
            :checked="toId === r.id"
            aria-label="对比终点"
            @change="toId = r.id"
          >
          <span class="pick-label">终</span>
        </label>
        <span class="rev-source">{{ sourceLabel[r.source] ?? r.source }}</span>
        <span class="rev-time">{{ r.created_at }}</span>
        <span
          v-if="r.applied_at"
          class="applied"
        >已应用</span>
        <button
          type="button"
          class="ghost small"
          :disabled="busy"
          @click="restore(r.id)"
        >
          恢复到此版本
        </button>
      </li>
    </ul>

    <div class="compare-bar">
      <button
        type="button"
        class="primary"
        :disabled="!canCompare || busy"
        @click="runCompare"
      >
        对比所选版本
      </button>
    </div>

    <section
      v-if="compare"
      class="compare-result"
    >
      <h2>变化字段：{{ changedFields.length }}</h2>
      <ul class="changed">
        <li
          v-for="f in changedFields"
          :key="f"
        >
          {{ f }}
        </li>
      </ul>
      <pre
        v-if="compare.body_diff.changed"
        class="body"
      >{{ compare.body_diff.unified_diff }}</pre>
      <p
        v-else
        class="nochange"
      >
        正文无变化。
      </p>
    </section>
  </section>
</template>

<style scoped>
.versions {
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
.head-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.back {
  color: var(--color-text-muted);
  text-decoration: none;
}
.err {
  color: var(--status-danger, #dc2626);
}
.timeline {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0;
}
.rev-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.pick {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.rev-source {
  font-weight: 600;
}
.rev-time {
  color: var(--color-text-muted);
  font-size: 0.85rem;
  flex: 1;
}
.applied {
  font-size: 0.75rem;
  color: var(--status-done, #16a34a);
}
.compare-result h2 {
  font-size: 1rem;
}
.changed {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  list-style: none;
  padding: 0;
}
.changed li {
  background: var(--color-surface-muted, #eee);
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
  font-size: 0.8rem;
}
.body {
  overflow-x: auto;
  font-size: 0.8rem;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.nochange {
  color: var(--color-text-muted);
}
.primary,
.ghost {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.ghost.small {
  min-height: 2rem;
  font-size: 0.85rem;
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
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
