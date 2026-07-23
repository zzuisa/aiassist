<script setup lang="ts">
import { computed } from 'vue'
import type { ProvenancedValue } from '@/api/captures'

// Displays a field value with a clear "你填写 / AI 建议" source distinction and,
// for AI values, a confidence label. Editing always writes the user value.
const props = defineProps<{ label: string; field: ProvenancedValue | undefined }>()
defineEmits<{ (e: 'accept', value: string): void }>()

const isAi = computed(() => props.field?.source === 'ai')
const confidencePct = computed(() =>
  props.field?.confidence != null ? Math.round(props.field.confidence * 100) : null,
)
</script>

<template>
  <div class="prov-field">
    <span class="label">{{ label }}</span>
    <template v-if="field">
      <span class="value">{{ field.value }}</span>
      <span
        v-if="isAi"
        class="source ai"
      >
        AI 建议<template v-if="confidencePct !== null"> · {{ confidencePct }}%</template>
      </span>
      <span
        v-else
        class="source user"
      >你填写</span>
      <button
        v-if="isAi"
        type="button"
        class="accept"
        @click="$emit('accept', field.value)"
      >
        采用
      </button>
    </template>
    <span
      v-else
      class="empty"
    >未填写</span>
  </div>
</template>

<style scoped>
.prov-field {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  flex-wrap: wrap;
}
.label {
  min-width: 72px;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.value {
  font-weight: 500;
}
.source {
  font-size: 0.7rem;
  padding: 1px 6px;
  border-radius: 999px;
}
.source.ai {
  background: color-mix(in srgb, var(--status-ai) 18%, transparent);
  color: var(--status-ai);
}
.source.user {
  background: color-mix(in srgb, var(--status-normal) 18%, transparent);
  color: var(--status-normal);
}
.empty {
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.accept {
  min-height: 28px;
  padding: 0 var(--space-2);
  border: 1px solid var(--status-ai);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--status-ai);
  cursor: pointer;
  font-size: 0.75rem;
}
</style>
