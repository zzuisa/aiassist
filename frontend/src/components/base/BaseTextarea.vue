<script setup lang="ts">
defineOptions({ inheritAttrs: false })

const model = defineModel<string>({ required: true })
defineProps<{ label?: string }>()
</script>

<template>
  <label class="base-textarea">
    <span
      v-if="label"
      class="base-textarea__label"
    >{{ label }}</span>
    <textarea
      v-model="model"
      v-bind="$attrs"
    />
  </label>
</template>

<style scoped>
.base-textarea {
  display: grid;
  min-width: 0;
  gap: var(--space-1);
}

.base-textarea__label {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: 700;
}

textarea {
  width: 100%;
  min-height: var(--tap-target);
  padding: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--color-text);
  line-height: 1.55;
  resize: vertical;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

textarea:hover:not(:disabled) {
  border-color: var(--color-border-strong);
}

textarea:focus-visible {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus);
}

textarea:disabled {
  background: var(--color-surface-muted);
  opacity: 0.65;
}
</style>
