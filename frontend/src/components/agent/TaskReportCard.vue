<script setup lang="ts">
import type { AgentTaskReport } from '@/api/agentPlans'

defineProps<{ report: AgentTaskReport }>()
</script>

<template>
  <details class="task-report">
    <summary>
      Markdown 任务报告
      <small>
        匹配 {{ report.totals.matched ?? 0 }} · 写入 {{ report.totals.applied ?? 0 }} ·
        验证 {{ report.totals.verified ?? 0 }}
      </small>
    </summary>
    <pre>{{ report.markdown }}</pre>
  </details>
</template>

<style scoped>
.task-report {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
summary {
  cursor: pointer;
  font-weight: 600;
}
small {
  display: block;
  margin-top: var(--space-1);
  color: var(--color-text-muted);
  font-weight: 400;
}
pre {
  max-height: 24rem;
  margin: var(--space-3) 0 0;
  padding: var(--space-3);
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--color-background);
  border-radius: var(--radius-sm);
  font: inherit;
  line-height: 1.6;
}
</style>
