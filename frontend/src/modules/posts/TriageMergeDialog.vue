<script setup lang="ts">
// Ordered merge dialog (spec 005, US6, T124).
//
// Merges two triage items in a chosen order into the primary. The secondary's
// sources are preserved on the merged article and the secondary is kept as a
// recoverable discarded record — so nothing is lost. The user picks the order and
// an optional merged title, and sees a preview of the concatenation order.
import { computed, ref } from 'vue'
import { articlesApi } from '@/api/blogQueries'
import { postsApi } from '@/api/posts'
import CaptureModal from '@/modules/posts/CaptureModal.vue'

const props = defineProps<{
  primary: { id: string; title: string }
  secondary: { id: string; title: string }
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'merged', postId: string): void }>()

const order = ref<'primary_first' | 'secondary_first'>('primary_first')
const title = ref(props.primary.title)
const busy = ref(false)
const error = ref('')

const orderedTitles = computed(() =>
  order.value === 'primary_first'
    ? [props.primary.title, props.secondary.title]
    : [props.secondary.title, props.primary.title],
)

async function merge(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const primary = await postsApi.get(props.primary.id)
    const res = await articlesApi.merge({
      primary_id: props.primary.id,
      secondary_id: props.secondary.id,
      primary_version: primary.version,
      order: order.value,
      title: title.value.trim() || null,
    })
    emit('merged', res.id)
  } catch {
    error.value = '合并失败，请刷新后重试。'
    busy.value = false
  }
}
</script>

<template>
  <CaptureModal
    title="合并两条记录"
    :busy="busy"
    @close="emit('close')"
  >
    <p class="hint">
      合并会把两条内容按顺序拼接到主记录，并保留两者的来源；被合并方将标记为「已丢弃」，仍可恢复。
    </p>

    <label class="field">
      <span>顺序</span>
      <select
        v-model="order"
        aria-label="顺序"
        :disabled="busy"
      >
        <option value="primary_first">
          主记录在前
        </option>
        <option value="secondary_first">
          副记录在前
        </option>
      </select>
    </label>

    <div class="preview">
      <span
        v-for="(t, i) in orderedTitles"
        :key="i"
        class="chip"
      >{{ i + 1 }}. {{ t }}</span>
    </div>

    <label class="field">
      <span>合并后标题</span>
      <input
        v-model="title"
        aria-label="合并后标题"
        :disabled="busy"
      >
    </label>

    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>

    <template #footer>
      <button
        type="button"
        class="ghost"
        :disabled="busy"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        type="button"
        class="primary"
        :disabled="busy"
        @click="merge"
      >
        {{ busy ? '合并中…' : '合并' }}
      </button>
    </template>
  </CaptureModal>
</template>

<style scoped>
.hint {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-3);
}
.field {
  display: block;
  margin-bottom: var(--space-3);
}
.field > span {
  display: block;
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: 0.2rem;
}
.field input,
.field select {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.preview {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}
.chip {
  background: var(--color-surface-muted, #eee);
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  font-size: 0.85rem;
}
.err {
  color: var(--status-danger, #dc2626);
  margin: 0;
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
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
