<script setup lang="ts">
import { computed } from 'vue'
import type { AgentTaskReport } from '@/api/agentPlans'
import AgentResultList from './AgentResultList.vue'
import { presentReportResults } from './resultPresentation'

const props = defineProps<{ report: AgentTaskReport }>()
const presented = computed(() => presentReportResults(props.report))
</script>

<template>
  <section
    class="task-report"
    aria-labelledby="task-report-heading"
  >
    <header>
      <strong id="task-report-heading">任务结果</strong>
      <small>
        匹配 {{ report.totals.matched ?? 0 }} · 写入 {{ report.totals.applied ?? 0 }} ·
        验证 {{ report.totals.verified ?? 0 }}
      </small>
    </header>
    <AgentResultList
      v-if="presented.items.length"
      :items="presented.items"
      :summary="presented.summary"
    />
    <details class="markdown-report">
      <summary>查看 Markdown 完整报告</summary>
      <pre>{{ report.markdown }}</pre>
    </details>
  </section>
</template>

<style scoped>
.task-report {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
.markdown-report summary {
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
.markdown-report { border-top: 1px solid var(--color-border); padding-top: var(--space-2); }
</style>
