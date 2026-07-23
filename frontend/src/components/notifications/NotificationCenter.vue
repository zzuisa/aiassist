<script setup lang="ts">
import { api } from '@/api/client'
import { useJobsStore } from '@/stores/jobs'
import type { NotificationItem } from '@/api/types'

defineProps<{ open: boolean }>()
defineEmits<{ (e: 'close'): void }>()

const jobs = useJobsStore()

async function markRead(n: NotificationItem): Promise<void> {
  await api.post(`/notifications/${n.id}/read`)
  n.status = 'read'
}
</script>

<template>
  <aside
    v-if="open"
    class="notif-center"
    role="dialog"
    aria-label="通知"
  >
    <header>
      <h2>通知</h2>
      <button
        class="close"
        aria-label="关闭"
        @click="$emit('close')"
      >
        ✕
      </button>
    </header>
    <p
      v-if="jobs.notifications.length === 0"
      class="empty"
    >
      暂无通知。
    </p>
    <ul>
      <li
        v-for="n in jobs.notifications"
        :key="n.id"
        :class="{ unread: n.status === 'unread' }"
      >
        <div class="body">
          <span class="title">{{ n.title }}</span>
          <span class="text">{{ n.body }}</span>
        </div>
        <button
          v-if="n.status === 'unread'"
          type="button"
          @click="markRead(n)"
        >
          已读
        </button>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.notif-center {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: min(360px, 100%);
  background: var(--color-surface);
  border-left: 1px solid var(--color-border);
  padding: var(--space-4);
  overflow-y: auto;
  z-index: 30;
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
ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
li {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}
li.unread {
  border-left: 3px solid var(--status-normal);
}
.body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.text {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}
button {
  min-height: 32px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.empty {
  color: var(--color-text-muted);
}
</style>
