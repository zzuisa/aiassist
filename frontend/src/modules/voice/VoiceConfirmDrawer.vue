<script setup lang="ts">
import { reactive, ref } from 'vue'
import { voiceApi, type VoiceCandidate } from '@/api/voice'

const props = defineProps<{ recordId: string; candidate: VoiceCandidate }>()
const emit = defineEmits<{
  (e: 'confirmed', entityType: string, entityId: string): void
  (e: 'discard'): void
}>()

// Edit a copy so the user reviews AI-parsed values before any record is created.
const form = reactive<VoiceCandidate>({ ...props.candidate })
const submitting = ref(false)

const contentTypes: Array<{ value: VoiceCandidate['content_type']; label: string }> = [
  { value: 'task', label: '任务' },
  { value: 'reminder', label: '提醒' },
  { value: 'fixed_event', label: '固定事件' },
  { value: 'note', label: '笔记' },
]

async function confirm(): Promise<void> {
  if (submitting.value) return
  submitting.value = true
  try {
    const result = await voiceApi.confirm(props.recordId, { ...form })
    emit('confirmed', result.entity_type, result.entity_id)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <aside
    class="confirm"
    role="dialog"
    aria-label="确认语音结果"
  >
    <h2>确认语音结果</h2>
    <p class="original">
      识别原文：{{ candidate.original_text }}
    </p>

    <label>
      <span>标题</span>
      <input
        v-model="form.title"
        aria-label="标题"
      >
    </label>

    <label>
      <span>类型</span>
      <select
        v-model="form.content_type"
        aria-label="类型"
      >
        <option
          v-for="t in contentTypes"
          :key="t.value"
          :value="t.value"
        >{{ t.label }}</option>
      </select>
    </label>

    <div class="row">
      <label>
        <span>日期</span>
        <input
          v-model="form.local_date"
          type="date"
          aria-label="日期"
        >
      </label>
      <label>
        <span>时间</span>
        <input
          v-model="form.local_time"
          type="time"
          aria-label="时间"
        >
      </label>
    </div>

    <label class="check">
      <input
        v-model="form.important"
        type="checkbox"
      >
      <span>重要</span>
    </label>

    <p class="hint">
      这些是 AI 推测的结果，确认后才会创建正式记录。
    </p>

    <footer>
      <button
        type="button"
        @click="emit('discard')"
      >
        放弃
      </button>
      <button
        type="button"
        class="primary"
        @click="confirm"
      >
        确认创建
      </button>
    </footer>
  </aside>
</template>

<style scoped>
.confirm {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  max-width: 420px;
}
.original {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
label.check {
  flex-direction: row;
  align-items: center;
  gap: var(--space-2);
}
.row {
  display: flex;
  gap: var(--space-3);
}
.row label {
  flex: 1;
}
input,
select {
  min-height: var(--tap-target);
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
  color: var(--color-text);
}
.hint {
  color: var(--status-ai);
  font-size: 0.8rem;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
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
