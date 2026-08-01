<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Task } from '@/api/tasks'

const props = defineProps<{ task: Task; busy?: boolean }>()
const emit = defineEmits<{
  (e: 'toggle-complete'): void
  (e: 'toggle-important'): void
  (e: 'adjust-time'): void
  (e: 'add-note'): void
  (e: 'delete'): void
  (e: 'close'): void
}>()

// Two-step delete so a tap can't destroy an event by accident (HCD).
const confirmingDelete = ref(false)
function onDelete(): void {
  if (confirmingDelete.value) emit('delete')
  else confirmingDelete.value = true
}

const done = computed(() => props.task.status === 'completed')
const important = computed(() => props.task.importance > 0)

// User-facing reminder status derived on the backend (FR-009).
const reminderText = computed(() => {
  const r = props.task.important_reminder
  if (!r) return ''
  switch (r.state) {
    case 'scheduled':
      return '⏰ 将于开始前 4 小时发送邮件提醒'
    case 'sending':
      return '📧 邮件发送中…'
    case 'sent':
      return '✅ 邮件已送达'
    case 'failed':
      return '⚠️ 邮件发送失败'
    case 'unconfigured':
      return '⚠️ 邮箱未配置，邮件未发送'
    case 'missing_start':
      return 'ℹ️ 设置开始时间后才能安排 4 小时提醒'
    default:
      return ''
  }
})
</script>

<template>
  <div
    class="popover"
    role="dialog"
    aria-label="事件操作"
    @click.stop
  >
    <div class="head">
      <strong class="title">{{ task.title }}</strong>
      <button
        class="x"
        aria-label="关闭"
        @click="emit('close')"
      >
        ✕
      </button>
    </div>

    <div class="actions">
      <button
        type="button"
        class="act"
        :class="{ on: done }"
        :disabled="busy"
        :aria-pressed="done"
        @click="emit('toggle-complete')"
      >
        {{ done ? '✅ 取消完成' : '○ 标为已完成' }}
      </button>
      <button
        type="button"
        class="act"
        :class="{ on: important }"
        :disabled="busy"
        :aria-pressed="important"
        @click="emit('toggle-important')"
      >
        {{ important ? '⭐ 取消重要' : '☆ 设为重要' }}
      </button>
      <button
        type="button"
        class="act"
        :disabled="busy"
        @click="emit('adjust-time')"
      >
        🕐 调整时间
      </button>
      <button
        type="button"
        class="act"
        :disabled="busy"
        @click="emit('add-note')"
      >
        {{ task.has_note ? '📝 查看备注' : '📝 添加备注' }}
      </button>
      <button
        type="button"
        class="act danger"
        :class="{ confirming: confirmingDelete }"
        :disabled="busy"
        @click="onDelete"
      >
        {{ confirmingDelete ? '⚠️ 确认删除？' : '🗑 删除' }}
      </button>
    </div>

    <p
      v-if="important && reminderText"
      class="reminder"
      role="status"
    >
      {{ reminderText }}
    </p>
  </div>
</template>

<style scoped>
.popover {
  position: absolute;
  z-index: 40;
  width: min(260px, 90vw);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}
.title {
  font-size: 0.95rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.x {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--color-text-muted);
  min-width: 32px;
  min-height: 32px;
}
.actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.act {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  text-align: left;
  transition:
    background 0.15s ease,
    transform 0.1s ease;
}
.act:active {
  transform: scale(0.98);
}
.act:hover:not(:disabled) {
  background: var(--color-surface-2);
}
.act.on {
  border-color: var(--status-ai);
}
.act:disabled {
  opacity: 0.6;
  cursor: default;
}
.act.danger {
  color: var(--status-urgent);
}
.act.danger.confirming {
  background: color-mix(in srgb, var(--status-urgent) 14%, transparent);
  border-color: var(--status-urgent);
  font-weight: 600;
}
.reminder {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}
</style>
