<script setup lang="ts">
import { computed } from 'vue'
import { api } from '@/api/client'
import { useJobsStore } from '@/stores/jobs'
import { jobLabel, formatTime, formatDuration } from '@/api/jobs'
import type { AsyncJob } from '@/api/types'

// Global task center: active / waiting / failed sections with business copy,
// a labelled progress bar, start/finish times, and clear failure reasons.
// Progress updates in place — never as repeated toasts.
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
  <transition name="drawer">
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
        <transition-group
          name="job"
          tag="div"
        >
          <div
            v-for="job in active"
            :key="job.id"
            class="job"
          >
            <div class="job-head">
              <span class="name">{{ jobLabel(job) }}</span>
              <span class="pct">{{ job.progress }}%</span>
            </div>
            <span class="step">{{ job.current_step ?? '处理中' }}</span>
            <div
              class="bar"
              role="progressbar"
              :aria-valuenow="job.progress"
            >
              <span :style="{ width: job.progress + '%' }" />
            </div>
            <div class="times">
              <span>开始 {{ formatTime(job.started_at ?? job.created_at) }}</span>
              <span v-if="formatDuration(job.started_at ?? job.created_at)">
                · 已用 {{ formatDuration(job.started_at ?? job.created_at) }}
              </span>
            </div>
          </div>
        </transition-group>
      </section>

      <section
        v-if="waiting.length"
        aria-label="等待确认"
      >
        <h3>等待确认</h3>
        <div
          v-for="job in waiting"
          :key="job.id"
          class="job waiting"
        >
          <div class="job-head">
            <span class="name">{{ jobLabel(job) }}</span>
          </div>
          <span class="step">{{ job.current_step ?? '请确认' }}</span>
        </div>
      </section>

      <section
        v-if="jobs.failedJobs.length"
        aria-label="失败"
      >
        <h3>失败</h3>
        <transition-group
          name="job"
          tag="div"
        >
          <div
            v-for="job in jobs.failedJobs"
            :key="job.id"
            class="job failed"
          >
            <div class="job-head">
              <span class="name">{{ jobLabel(job) }}</span>
              <span class="badge">失败</span>
            </div>
            <span class="reason">{{ job.error?.message ?? '处理失败' }}</span>
            <div class="times">
              <span>开始 {{ formatTime(job.started_at ?? job.created_at) }}</span>
              <span>· 结束 {{ formatTime(job.finished_at ?? job.updated_at) }}</span>
              <span v-if="job.retry_count > 0">· 已重试 {{ job.retry_count }} 次</span>
            </div>
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
        </transition-group>
      </section>

      <p
        v-if="!active.length && !waiting.length && !jobs.failedJobs.length"
        class="empty"
      >
        暂无后台任务。
      </p>
    </aside>
  </transition>
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
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.12);
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
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  transition: box-shadow 0.2s ease;
}
.job:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
}
.job.failed {
  border-left: 4px solid var(--status-urgent);
}
.job.waiting {
  border-left: 4px solid var(--status-ai);
}
.job-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.name {
  font-weight: 600;
}
.pct {
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.step {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.reason {
  color: var(--status-urgent);
  font-size: 0.85rem;
}
.times {
  color: var(--color-text-muted);
  font-size: 0.75rem;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.bar {
  height: 6px;
  background: var(--color-surface-2);
  border-radius: 999px;
  overflow: hidden;
  margin-top: 2px;
}
.bar span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--status-normal), var(--status-ai));
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.badge {
  font-size: 0.7rem;
  color: var(--status-urgent);
}
.actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-top: var(--space-1);
}
.actions button {
  min-height: 32px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  transition: background 0.15s ease;
}
.actions button:hover {
  background: var(--color-surface-2);
}
code {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}
.empty {
  color: var(--color-text-muted);
}

/* Drawer slide-in + job list transitions */
.drawer-enter-active,
.drawer-leave-active {
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.drawer-enter-from,
.drawer-leave-to {
  transform: translateX(100%);
}
.job-enter-active {
  transition: all 0.25s ease;
}
.job-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}
.job-move {
  transition: transform 0.25s ease;
}
@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active,
  .drawer-leave-active,
  .job-enter-active,
  .job-move,
  .bar span {
    transition: none;
  }
}
</style>
