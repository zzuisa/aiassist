<script setup lang="ts">
import { ref } from 'vue'
import type { SkipReason } from '@/api/habits'

defineProps<{ habitName: string }>()
const emit = defineEmits<{ (e: 'confirm', reason: SkipReason, note: string): void; (e: 'cancel'): void }>()

const reasons: Array<{ value: SkipReason; label: string }> = [
  { value: 'no_time', label: '没时间' },
  { value: 'too_tired', label: '太累' },
  { value: 'forgot', label: '忘记了' },
  { value: 'unrealistic_plan', label: '计划不现实' },
  { value: 'not_suitable', label: '不合适' },
  { value: 'other', label: '其他' },
]
const reason = ref<SkipReason>('too_tired')
const note = ref('')
</script>

<template>
  <div
    class="sheet"
    role="dialog"
    :aria-label="`跳过 ${habitName}`"
  >
    <h3>为什么跳过？</h3>
    <fieldset>
      <label
        v-for="r in reasons"
        :key="r.value"
      >
        <input
          v-model="reason"
          type="radio"
          :value="r.value"
          name="skip-reason"
        >
        <span>{{ r.label }}</span>
      </label>
    </fieldset>
    <textarea
      v-model="note"
      placeholder="补充说明（可选）"
      rows="2"
    />
    <div class="actions">
      <button
        type="button"
        @click="emit('cancel')"
      >
        取消
      </button>
      <button
        type="button"
        class="primary"
        @click="emit('confirm', reason, note)"
      >
        确认跳过
      </button>
    </div>
  </div>
</template>

<style scoped>
.sheet {
  padding: var(--space-4);
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
fieldset {
  border: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
}
label {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  min-height: var(--tap-target);
}
textarea {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2);
  background: var(--color-bg);
  color: var(--color-text);
}
.actions {
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
  background: var(--status-normal);
  color: white;
  border: none;
}
</style>
