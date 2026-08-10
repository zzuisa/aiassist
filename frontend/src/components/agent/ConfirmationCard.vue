<script setup lang="ts">
import { computed } from 'vue'
import type { ConfirmationDecision, PendingWrite } from '@/api/agent'

const props = defineProps<{
  confirmation: PendingWrite
  deciding: boolean
}>()

defineEmits<{
  decide: [decision: ConfirmationDecision]
}>()

const previewText = computed(() => JSON.stringify(props.confirmation.preview, null, 2))
const previewSummary = computed(() => {
  const summary = props.confirmation.preview.summary
  return typeof summary === 'string'
    ? summary
    : `${props.confirmation.operation_type} ${props.confirmation.target_type}`
})

function decisionLabel(decision: PendingWrite['decision']): string {
  return {
    pending: '等待你的决定',
    approved: '已批准',
    rejected: '已拒绝',
    expired: '已过期',
  }[decision]
}
</script>

<template>
  <article
    class="confirmation-card"
    :class="{ 'high-risk': confirmation.high_risk }"
    aria-label="待确认写操作"
  >
    <header>
      <div>
        <strong>写入前确认</strong>
        <p>{{ previewSummary }}</p>
      </div>
      <span class="decision">{{ decisionLabel(confirmation.decision) }}</span>
    </header>

    <dl>
      <div>
        <dt>影响范围</dt>
        <dd>预计影响 {{ confirmation.affected_count }} 项</dd>
      </div>
      <div>
        <dt>风险级别</dt>
        <dd>{{ confirmation.high_risk ? '高风险操作' : '常规写操作' }}</dd>
      </div>
      <div>
        <dt>回滚能力</dt>
        <dd>{{ confirmation.reversible ? '支持回滚' : '不支持自动回滚' }}</dd>
      </div>
    </dl>

    <details>
      <summary>查看变更预览</summary>
      <pre>{{ previewText }}</pre>
    </details>

    <p
      v-if="confirmation.high_risk && confirmation.decision === 'pending'"
      class="risk-note"
      role="alert"
    >
      这是删除、覆盖或批量修改类高风险操作，必须在这里再次确认。
    </p>

    <div
      v-if="confirmation.decision === 'pending'"
      class="actions"
    >
      <button
        type="button"
        class="secondary"
        data-action="reject"
        :disabled="deciding"
        @click="$emit('decide', 'reject')"
      >
        拒绝写入
      </button>
      <button
        type="button"
        data-action="approve"
        :disabled="deciding"
        @click="$emit('decide', 'approve')"
      >
        {{ deciding ? '正在处理…' : '批准并写入' }}
      </button>
    </div>
  </article>
</template>

<style scoped>
.confirmation-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}
.confirmation-card.high-risk {
  border-color: var(--status-overdue);
}
header,
.actions {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}
header p,
dd {
  margin: var(--space-1) 0 0;
}
.decision,
dt {
  color: var(--color-text-muted);
  font-size: 0.875rem;
}
dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--space-2);
  margin: 0;
}
dl > div {
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
}
pre {
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.risk-note {
  color: var(--status-overdue);
}
.actions {
  justify-content: flex-end;
}
</style>
