<script setup lang="ts">
import { ref } from 'vue'

// Quick text capture. On failure the input is preserved (US1: never lose input).
// The handler may be async; a prop lets us await it directly (emit does not
// surface the listener's returned promise).
const props = defineProps<{ onCreate?: (title: string) => Promise<void> | void }>()

const title = ref('')
const saving = ref(false)
const failed = ref(false)

async function submit(): Promise<void> {
  const value = title.value.trim()
  if (!value || saving.value) return
  saving.value = true
  failed.value = false
  try {
    await props.onCreate?.(value)
    title.value = '' // clear only on success
  } catch {
    failed.value = true // keep the text for retry
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form
    class="quick"
    @submit.prevent="submit"
  >
    <input
      v-model="title"
      type="text"
      placeholder="快速添加任务…"
      aria-label="快速添加任务"
      :disabled="saving"
    >
    <button
      type="submit"
      :disabled="saving || !title.trim()"
    >
      {{ saving ? '保存中' : '添加' }}
    </button>
    <p
      v-if="failed"
      class="failed"
      role="alert"
    >
      保存失败，内容已保留，请重试。
    </p>
  </form>
</template>

<style scoped>
.quick {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
input {
  flex: 1;
  min-height: var(--tap-target);
  min-width: 0;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
button {
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
.failed {
  flex-basis: 100%;
  color: var(--status-urgent);
  margin: var(--space-2) 0 0;
}
</style>
