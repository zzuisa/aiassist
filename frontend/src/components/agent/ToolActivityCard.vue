<script setup lang="ts">
defineProps<{ label: string; status: string }>()
</script>
<template>
  <aside
    class="tool-activity"
    role="status"
  >
    <strong>{{ label }}</strong><span>{{ status }}</span>
  </aside>
</template>
<style scoped>.tool-activity { display: flex; justify-content: space-between; gap: var(--space-2); padding: var(--space-2); color: var(--color-text-muted); }</style>
