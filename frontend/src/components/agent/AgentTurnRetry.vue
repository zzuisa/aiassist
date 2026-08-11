<script setup lang="ts">
import type { Turn } from '@/api/agentConversations'
defineProps<{ turns: Turn[]; retrying?: boolean }>()
defineEmits<{ retry: [turnId: string] }>()
</script>
<template>
  <section
    v-if="turns.length"
    aria-label="未完成的消息"
  >
    <article
      v-for="turn in turns"
      :key="turn.id"
    >
      <p>{{ turn.error_message ?? '处理没有完成，你可以安全重试。' }}</p>
      <button
        type="button"
        :disabled="retrying"
        @click="$emit('retry', turn.id)"
      >
        {{ retrying ? '正在重试…' : '重试这条消息' }}
      </button>
    </article>
  </section>
</template>
