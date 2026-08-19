<script setup lang="ts">
import { computed } from 'vue'
import { useAgentStore } from '@/stores/agent'

const props = defineProps<{ taskId?: string }>()
const store = useAgentStore()
const ACTIVE_STATUSES = ['pending', 'running', 'waiting_confirmation']
const visibleAgents = computed(() =>
  props.taskId
    ? store.forTask(props.taskId).filter((agent) => ACTIVE_STATUSES.includes(agent.status))
    : store.activeAgents,
)

function statusLabel(status: string): string {
  return {
    pending: '等待开始',
    running: '运行中',
    waiting_confirmation: '等待确认',
    success: '已完成',
    partial_success: '部分完成',
    failed: '失败',
    skipped: '已跳过',
  }[status] ?? status
}
</script>

<template>
  <section
    v-if="visibleAgents.length"
    class="agent-status-panel"
    aria-label="Agent 运行状态"
  >
    <article
      v-for="agent in visibleAgents"
      :key="agent.agent_id"
      class="agent-card"
    >
      <header>
        <strong>{{ agent.agent_name }}</strong>
        <span class="status">{{ statusLabel(agent.status) }}</span>
      </header>
      <p>{{ agent.responsibility }}</p>
      <p><b>当前任务：</b>{{ agent.current_task }}</p>
      <p v-if="agent.current_tool">
        <b>当前工具：</b>{{ agent.current_tool }}
      </p>
      <progress
        v-if="agent.progress"
        :value="agent.progress.current"
        :max="agent.progress.total"
      />
      <small v-if="agent.progress?.stage_label">{{ agent.progress.stage_label }}</small>
      <p
        v-if="agent.error_message"
        class="error"
      >
        {{ agent.error_message }}
      </p>
    </article>
  </section>
</template>

<style scoped>
.agent-status-panel {
  display: grid;
  gap: var(--space-2);
}
.agent-card {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
}
.status {
  color: var(--color-text-muted);
}
progress {
  width: 100%;
}
.error {
  color: var(--status-overdue);
}
</style>
