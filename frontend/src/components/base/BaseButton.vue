<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'text'
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
}>(), {
  variant: 'secondary',
  type: 'button',
  disabled: false,
})
</script>

<template>
  <button
    :type="type"
    class="base-button"
    :class="`base-button--${variant}`"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>

<style scoped>
.base-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: var(--tap-target);
  padding: 0.7rem 1.1rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.base-button:hover:not(:disabled) {
  border-color: var(--color-accent);
  background: var(--color-surface-2);
  transform: translateY(-1px);
}

.base-button--primary {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: white;
}

.base-button--primary:hover:not(:disabled) {
  border-color: var(--color-accent);
  background: var(--color-accent);
}

.base-button--text {
  min-height: auto;
  padding: var(--space-2);
  border-color: transparent;
  background: transparent;
  color: var(--color-accent);
}

.base-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
