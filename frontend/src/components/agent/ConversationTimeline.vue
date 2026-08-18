<script setup lang="ts">
import { messageText, type AgentMessage } from '@/api/agentConversations'
import ClarificationCard from './ClarificationCard.vue'
import ConversationMessage from './ConversationMessage.vue'
import ToolActivityCard from './ToolActivityCard.vue'
import AgentPlanCard from './AgentPlanCard.vue'
import type { AgentPlan } from '@/api/agentPlans'

type TimelineMessage = AgentMessage & { pending?: boolean }
withDefaults(defineProps<{
  messages: TimelineMessage[]
  plans?: AgentPlan[]
  retryingPlanId?: string | null
}>(), { plans: () => [], retryingPlanId: null })
const emit = defineEmits<{ retryPlan: [planId: string] }>()
</script>
<template>
  <div class="timeline">
    <template
      v-for="message in messages"
      :key="message.id"
    >
      <ClarificationCard
        v-if="message.kind === 'clarification'"
        :question="messageText(message)"
      />
      <template v-else>
        <ConversationMessage :message="message" />
        <ToolActivityCard
          v-if="message.kind === 'result' && message.content.task_status === 'waiting_confirmation'"
          label="已生成预览"
          status="确认前不会写入"
        />
      </template>
      <AgentPlanCard
        v-for="plan in plans.filter((item) => item.user_message_id === message.id)"
        :key="plan.plan_id"
        :plan="plan"
        :retrying="retryingPlanId === plan.plan_id"
        @retry="emit('retryPlan', $event)"
      />
    </template>
  </div>
</template>
<style scoped>.timeline { display: grid; gap: var(--space-2); }</style>
