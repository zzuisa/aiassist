<script setup lang="ts">
withDefaults(defineProps<{
  as?: string
  elevated?: boolean
}>(), {
  as: 'section',
  elevated: false,
})
</script>

<template>
  <component
    :is="as"
    class="base-card"
    :class="{ 'base-card--elevated': elevated }"
  >
    <slot />
  </component>
</template>

<style scoped>
.base-card {
  min-width: 0;
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.base-card--elevated {
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-elevated);
}

@media (max-width: 700px) {
  .base-card {
    padding: var(--space-4);
  }
}
</style>
