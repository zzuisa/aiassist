<script setup lang="ts">
import { computed, ref } from 'vue'
import { calendarApi, type SchedulePreview } from '@/api/calendar'

const props = defineProps<{ preview: SchedulePreview }>()
const emit = defineEmits<{ (e: 'applied'): void; (e: 'close'): void }>()

// Only selectable (non-fixed, non-stale) suggestions can be checked.
const selected = ref<Set<string>>(new Set())
const applying = ref(false)
const feedback = ref<string>('')

const selectable = computed(() => props.preview.suggestions.filter((s) => s.selectable))

function toggle(id: string): void {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
  selected.value = new Set(selected.value)
}

function selectAll(): void {
  selected.value = new Set(selectable.value.map((s) => s.suggestion_id))
}

async function apply(): Promise<void> {
  if (selected.value.size === 0 || applying.value) return
  applying.value = true
  feedback.value = ''
  try {
    const result = await calendarApi.applyPreview(props.preview.id, [...selected.value])
    if (result.rejected.length > 0) {
      const stale = result.rejected.some((r) => r.code === 'version_conflict')
      feedback.value = stale
        ? '部分建议已过期，请重新生成预览。'
        : `${result.applied.length} 项已应用，${result.rejected.length} 项被拒绝。`
    }
    emit('applied')
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <aside
    class="drawer"
    role="dialog"
    aria-label="日程调整预览"
  >
    <header>
      <h2>日程调整预览</h2>
      <button
        class="close"
        aria-label="关闭"
        @click="emit('close')"
      >
        ✕
      </button>
    </header>
    <p
      v-if="preview.explanation"
      class="explain"
    >
      {{ preview.explanation }}
    </p>

    <ul class="suggestions">
      <li
        v-for="s in preview.suggestions"
        :key="s.suggestion_id"
        class="suggestion"
        :class="{ locked: !s.selectable }"
      >
        <label>
          <input
            type="checkbox"
            :disabled="!s.selectable"
            :checked="selected.has(s.suggestion_id)"
            @change="toggle(s.suggestion_id)"
          >
          <span class="reason">{{ s.reason }}</span>
        </label>
        <div class="times">
          <span class="old">{{ s.old_start ?? '未排期' }}</span>
          <span aria-hidden="true">→</span>
          <span class="new">{{ s.new_start ?? '未排期' }}</span>
        </div>
        <span
          v-if="!s.selectable"
          class="badge"
        >固定 / 不可调整</span>
      </li>
    </ul>

    <p
      v-if="feedback"
      class="feedback"
      role="status"
    >
      {{ feedback }}
    </p>

    <footer>
      <button
        type="button"
        @click="selectAll"
      >
        全选可调整项
      </button>
      <button
        type="button"
        class="primary"
        :disabled="selected.size === 0 || applying"
        @click="apply"
      >
        {{ applying ? '应用中…' : `应用所选 (${selected.size})` }}
      </button>
    </footer>
  </aside>
</template>

<style scoped>
.drawer {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-surface);
  border-left: 1px solid var(--color-border);
  max-width: 420px;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.close {
  border: none;
  background: transparent;
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  cursor: pointer;
  color: var(--color-text);
}
.suggestions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.suggestion {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--status-ai);
  border-radius: var(--radius-md);
}
.suggestion.locked {
  border-left-color: var(--status-muted);
  opacity: 0.75;
}
.times {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  display: flex;
  gap: var(--space-2);
}
.badge {
  font-size: 0.7rem;
  color: var(--status-muted);
}
footer {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}
button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
button.primary {
  background: var(--status-ai);
  color: white;
  border: none;
}
button:disabled {
  opacity: 0.5;
}
.feedback {
  color: var(--status-due-soon);
}
</style>
