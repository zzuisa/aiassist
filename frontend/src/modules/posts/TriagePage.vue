<script setup lang="ts">
// Triage backlog (spec 005, US6, T123).
//
// Lists items that still need organizing, each tagged with a derived reason
// (quick / failed / stale / draft) and a quick text preview. Reason chips filter
// the list; selecting exactly two items enables an ordered merge that never loses
// their sources.
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { articlesApi, type TriageItem, type TriageReason } from '@/api/blogQueries'
import TriageMergeDialog from '@/modules/posts/TriageMergeDialog.vue'

const router = useRouter()
const items = ref<TriageItem[]>([])
const counts = ref<Record<string, number>>({})
const reason = ref<TriageReason | null>(null)
const selected = ref<string[]>([])
const merging = ref(false)

const REASON_LABEL: Record<TriageReason, string> = {
  quick: '快速记录', failed: '处理失败', stale: '长期搁置', draft: '草稿',
}

const canMerge = computed(() => selected.value.length === 2)
const mergePair = computed(() => {
  if (!canMerge.value) return null
  const [a, b] = selected.value
  const pa = items.value.find((i) => i.id === a)!
  const pb = items.value.find((i) => i.id === b)!
  return { primary: { id: pa.id, title: pa.title }, secondary: { id: pb.id, title: pb.title } }
})

async function load(): Promise<void> {
  const res = await articlesApi.triage(reason.value ?? undefined)
  items.value = res.items
  counts.value = res.counts_by_reason
}

function setReason(r: TriageReason | null): void {
  reason.value = r
  selected.value = []
  void load()
}

function toggle(id: string): void {
  const i = selected.value.indexOf(id)
  if (i >= 0) selected.value.splice(i, 1)
  else if (selected.value.length < 2) selected.value.push(id)
}

function onMerged(postId: string): void {
  merging.value = false
  selected.value = []
  router.push({ name: 'blog-post-editor', params: { id: postId } })
}

onMounted(load)
</script>

<template>
  <section class="triage">
    <header class="head">
      <h1>待整理</h1>
      <RouterLink
        class="back"
        :to="{ name: 'blog' }"
      >
        全部文章
      </RouterLink>
    </header>

    <div class="reasons">
      <button
        type="button"
        class="chip"
        :class="{ active: reason === null }"
        @click="setReason(null)"
      >
        全部
      </button>
      <button
        v-for="(label, r) in REASON_LABEL"
        :key="r"
        type="button"
        class="chip"
        :class="{ active: reason === r }"
        @click="setReason(r as TriageReason)"
      >
        {{ label }} {{ counts[r] ?? 0 }}
      </button>
    </div>

    <div
      v-if="canMerge"
      class="merge-cta"
    >
      已选 2 项
      <button
        type="button"
        class="primary"
        @click="merging = true"
      >
        合并
      </button>
    </div>

    <p
      v-if="items.length === 0"
      class="empty"
    >
      没有待整理的内容。
    </p>

    <ul class="item-list">
      <li
        v-for="it in items"
        :key="it.id"
        class="item"
        :class="{ selected: selected.includes(it.id) }"
      >
        <input
          type="checkbox"
          :checked="selected.includes(it.id)"
          :disabled="!selected.includes(it.id) && selected.length >= 2"
          :aria-label="`选择 ${it.title}`"
          @change="toggle(it.id)"
        >
        <div class="body">
          <RouterLink
            class="title"
            :to="{ name: 'blog-post-editor', params: { id: it.id } }"
          >
            {{ it.title }}
          </RouterLink>
          <span
            class="reason"
            :data-reason="it.reason"
          >{{ REASON_LABEL[it.reason] }}</span>
          <p class="preview">
            {{ it.preview }}
          </p>
        </div>
        <span
          v-if="it.source_count"
          class="src"
        >{{ it.source_count }} 来源</span>
      </li>
    </ul>

    <TriageMergeDialog
      v-if="merging && mergePair"
      :primary="mergePair.primary"
      :secondary="mergePair.secondary"
      @close="merging = false"
      @merged="onMerged"
    />
  </section>
</template>

<style scoped>
.triage {
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
.reasons {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin: var(--space-3) 0;
}
.chip {
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0.25rem 0.7rem;
  background: none;
  cursor: pointer;
  font-size: 0.85rem;
}
.chip.active {
  background: var(--status-normal);
  color: #fff;
  border-color: var(--status-normal);
}
.merge-cta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.empty {
  color: var(--color-text-muted);
}
.item-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  margin-bottom: var(--space-2);
}
.item.selected {
  border-color: var(--status-normal);
}
.body {
  flex: 1;
}
.title {
  font-weight: 600;
  text-decoration: none;
  color: inherit;
  margin-right: var(--space-2);
}
.reason {
  font-size: 0.72rem;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  background: var(--color-surface-muted, #eee);
}
.reason[data-reason='failed'] {
  background: var(--status-danger-soft, #fee2e2);
}
.reason[data-reason='stale'] {
  background: var(--status-warn-soft, #fef3c7);
}
.preview {
  margin: 0.35rem 0 0;
  font-size: 0.85rem;
  color: var(--color-text-muted);
}
.src {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}
.primary {
  min-height: 2rem;
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: #fff;
  cursor: pointer;
}
</style>
