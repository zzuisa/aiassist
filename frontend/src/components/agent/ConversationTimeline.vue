<script setup lang="ts">
import { messageText, type AgentMessage } from '@/api/agentConversations'
import ClarificationCard from './ClarificationCard.vue'
import ConversationMessage from './ConversationMessage.vue'
import ToolActivityCard from './ToolActivityCard.vue'

type TimelineMessage = AgentMessage & { pending?: boolean }
defineProps<{ messages: TimelineMessage[] }>()
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
    </template>
  </div>
</template>
<style scoped>.timeline { display: grid; gap: var(--space-2); }</style>
