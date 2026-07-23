<script setup lang="ts">
import { computed } from 'vue'
import { api } from '@/api/client'
import { useJobsStore } from '@/stores/jobs'
import type { AsyncJob } from '@/api/types'

// Global task center: active / waiting / failed sections with business copy and
// retry/cancel actions. Progress updates in place — never as repeated toasts.
defineProps<{ open: boolean }>()
defineEmits<{ (e: 'close'): void }>()

const jobs = useJobsStore()

const waiting = computed(() =>
  [...jobs.jobs.values()].filter((j) => j.status === 'waiting_user'),
)
const active = computed(() =>
  jobs.activeJobs.filter((j) => j.status !== 'waiting_user'),
)

async function retry(job: AsyncJob): Promise<void> {
  await api.post(`/jobs/${job.id}/retry`)
}
async function cancel(job: AsyncJob): Promise<void> {
  await api.post(`/jobs/${job.id}/cancel`)
}
</script>

<template>
  <aside
    v-if="open"
    class="task-center"
    role="dialog"
    aria-label="后台任务中心"
  >
    <header>
      <h2>后台任务</h2>
      <button
        class="close"
        aria-label="关闭"
        @click="$emit('close')"
      >
        ✕
      </button>
    </header>

    <p
      v-if="jobs.reconnecting"
      class="reconnect"
      role="status"
    >
      正在重新连接…
    </p>

    <section
      v-if="active.length"
      aria-label="进行中"
    >
      <h3>进行中</h3>
      <div
        v-for="job in active"
        :key="job.id"
        class="job"
      >
        <span class="step">{{ job.current_step ?? '处理中' }}</span>
        <div class="bar">
          <span :style="{ width: job.progress + '%' }" />
        </div>
      </div>
    </section>

    <section
      v-if="waiting.length"
      aria-label="等待确认"
    >
      <h3>等待确认</h3>
      <div
        v-for="job in waiting"
        :key="job.id"
        class="job"
      >
        <span class="step">{{ job.current_step ?? '请确认' }}</span>
      </div>
    </section>

    <section
      v-if="jobs.failedJobs.length"
      aria-label="失败"
    >
      <h3>失败</h3>
      <div
        v-for="job in jobs.failedJobs"
        :key="job.id"
        class="job failed"
      >
        <span class="step">{{ job.error?.message ?? '处理失败' }}</span>
        <div class="actions">
          <button
            v-if="job.error?.retryable"
            type="button"
            @click="retry(job)"
          >
            重试
          </button>
          <button
            type="button"
            @click="cancel(job)"
          >
            取消
          </button>
          <details v-if="job.trace_id">
            <summary>诊断</summary>
            <code>{{ job.trace_id }}</code>
          </details>
        </div>
      </div>
    </section>

    <p
      v-if="!active.length && !waiting.length && !jobs.failedJobs.length"
      class="empty"
    >
      暂无后台任务。
    </p>
  </aside>
</template>

<style scoped>
.task-center {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: min(380px, 100%);
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
.reconnect {
  color: var(--status-due-soon);
}
h3 {
  font-size: 0.9rem;
  margin: var(--space-3) 0 var(--space-2);
}
.job {
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
}
.job.failed {
  border-left: 4px solid var(--status-urgent);
}
.bar {
  height: 6px;
  background: var(--color-surface-2);
  border-radius: 999px;
  overflow: hidden;
  margin-top: var(--space-2);
}
.bar span {
  display: block;
  height: 100%;
  background: var(--status-normal);
}
.actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-2);
}
.actions button {
  min-height: 32px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
code {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}
.empty {
  color: var(--color-text-muted);
}
</style>
