<script setup lang="ts">
import { ref } from 'vue'
import { assistantApi, INTENTS, type AssistantRun } from '@/api/assistant'
import ActionCardView from '@/modules/assistant/ActionCard.vue'
import { ApiError } from '@/api/client'

const run = ref<AssistantRun | null>(null)
const loading = ref(false)
const applying = ref<string | null>(null)
const feedback = ref('')

async function launch(intent: string): Promise<void> {
  loading.value = true
  feedback.value = ''
  try {
    run.value = await assistantApi.run(intent)
  } finally {
    loading.value = false
  }
}

async function apply(actionId: string): Promise<void> {
  if (!run.value) return
  applying.value = actionId
  feedback.value = ''
  try {
    await assistantApi.action(run.value.id, actionId)
    feedback.value = '已应用所选操作。'
    // Refresh the run so applied state is reflected.
    run.value = await assistantApi.get(run.value.id)
  } catch (err) {
    feedback.value =
      err instanceof ApiError && err.code === 'fixed_event'
        ? '该项为固定事件或已过期，未做更改。'
        : '应用失败，请重试。'
  } finally {
    applying.value = null
  }
}
</script>

<template>
  <main class="assistant">
    <h1>AI 助手</h1>

    <nav
      class="intents"
      aria-label="意图入口"
    >
      <button
        v-for="intent in INTENTS"
        :key="intent.value"
        type="button"
        @click="launch(intent.value)"
      >
        {{ intent.label }}
      </button>
    </nav>

    <p
      v-if="loading"
      class="muted"
      role="status"
    >
      分析中…
    </p>
    <p
      v-if="feedback"
      class="feedback"
      role="status"
    >
      {{ feedback }}
    </p>

    <section
      v-if="run"
      class="results"
      aria-label="结构化结果"
    >
      <ActionCardView
        v-for="card in run.cards"
        :key="card.id"
        :card="card"
        :applying="applying"
        @apply="apply"
      />
      <p
        v-if="run.grounded_refs.length"
        class="grounded"
      >
        基于 {{ run.grounded_refs.length }} 条真实记录
      </p>
    </section>
  </main>
</template>

<style scoped>
.assistant {
  padding: var(--space-4);
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.intents {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.intents button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.results {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.muted,
.grounded {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.feedback {
  color: var(--status-due-soon);
}
</style>
