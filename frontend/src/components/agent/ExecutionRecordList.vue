<script setup lang="ts">
import type { ExecutionRecord } from '@/api/agent'

defineProps<{
  records: ExecutionRecord[]
}>()

function statusLabel(status: ExecutionRecord['status']): string {
  return {
    success: '成功',
    failed: '失败',
    skipped: '已跳过',
  }[status]
}

function durationLabel(durationMs: number | null): string {
  if (durationMs === null) return '耗时未知'
  if (durationMs < 1000) return `${durationMs} ms`
  return `${(durationMs / 1000).toFixed(1)} s`
}
</script>

<template>
  <section
    v-if="records.length"
    class="execution-records"
    aria-label="执行记录"
  >
    <h2>执行记录</h2>
    <ol>
      <li
        v-for="record in records"
        :key="record.step_id"
        :class="`status-${record.status}`"
      >
        <header>
          <strong>{{ record.step_label }}</strong>
          <span>{{ statusLabel(record.status) }}</span>
        </header>
        <p>
          {{ record.agent_name }} · {{ record.tool_name }} · {{ durationLabel(record.duration_ms) }}
        </p>
        <p v-if="record.result_summary">
          {{ record.result_summary }}
        </p>
        <p
          v-if="record.error_reason"
          class="error"
        >
          {{ record.error_reason }}
        </p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.execution-records,
ol {
  display: grid;
  gap: var(--space-3);
}
h2 {
  margin: 0;
}
ol {
  margin: 0;
  padding-left: var(--space-5);
}
li {
  padding: var(--space-3);
  border-left: 3px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
li.status-success {
  border-left-color: var(--status-done);
}
li.status-failed {
  border-left-color: var(--status-urgent);
}
header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
}
p {
  margin: var(--space-1) 0 0;
  color: var(--color-text-muted);
}
.error {
  color: var(--status-urgent);
}
</style>
