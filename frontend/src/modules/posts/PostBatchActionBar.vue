<script setup lang="ts">
// Batch action bar (spec 005, US6, T125).
//
// Appears when one or more articles are selected. Runs an itemized batch op and
// reports per-item success/failure — a single failure never blocks the rest, so
// partial results are surfaced explicitly rather than as an all-or-nothing error.
import { computed, ref } from 'vue'
import { articlesApi, type BatchOp } from '@/api/blogQueries'

const props = defineProps<{ selectedIds: string[] }>()
const emit = defineEmits<{ (e: 'done'): void; (e: 'clear'): void }>()

const CONTENT_CLASSES = ['technical', 'life', 'learning', 'travel', 'diary', 'essay', 'quick']

const op = ref<BatchOp>('set_class')
const contentClass = ref('technical')
const busy = ref(false)
const summary = ref('')
const failures = ref<Array<{ id: string; error?: string }>>([])

const count = computed(() => props.selectedIds.length)

async function run(): Promise<void> {
  if (busy.value || count.value === 0) return
  busy.value = true
  summary.value = ''
  failures.value = []
  try {
    const params = op.value === 'set_class' ? { content_class: contentClass.value } : {}
    const res = await articlesApi.batch(props.selectedIds, op.value, params)
    summary.value = `成功 ${res.succeeded} 项，失败 ${res.failed} 项`
    failures.value = res.results.filter((r) => !r.ok).map((r) => ({ id: r.id, error: r.error }))
    emit('done')
  } catch {
    summary.value = '批量操作失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    class="batch-bar"
    role="region"
    aria-label="批量操作"
  >
    <span class="count">已选 {{ count }} 项</span>
    <select
      v-model="op"
      aria-label="批量操作类型"
      :disabled="busy"
    >
      <option value="set_class">
        设为类别
      </option>
      <option value="archive">
        归档
      </option>
      <option value="discard">
        丢弃
      </option>
    </select>
    <select
      v-if="op === 'set_class'"
      v-model="contentClass"
      aria-label="目标类别"
      :disabled="busy"
    >
      <option
        v-for="c in CONTENT_CLASSES"
        :key="c"
        :value="c"
      >
        {{ c }}
      </option>
    </select>
    <button
      type="button"
      class="primary"
      :disabled="busy || count === 0"
      @click="run"
    >
      {{ busy ? '执行中…' : '执行' }}
    </button>
    <button
      type="button"
      class="ghost"
      :disabled="busy"
      @click="emit('clear')"
    >
      取消选择
    </button>

    <p
      v-if="summary"
      class="summary"
    >
      {{ summary }}
      <span
        v-if="failures.length"
        class="fail-detail"
      >（{{ failures.length }} 项失败）</span>
    </p>
  </div>
</template>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-muted, #f5f5f5);
  margin-bottom: var(--space-3);
}
.count {
  font-weight: 600;
}
select {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.summary {
  width: 100%;
  margin: 0;
  font-size: 0.85rem;
  color: var(--color-text-muted);
}
.fail-detail {
  color: var(--status-danger, #dc2626);
}
.primary,
.ghost {
  min-height: 2rem;
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
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
