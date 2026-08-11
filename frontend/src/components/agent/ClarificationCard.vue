<script setup lang="ts">
defineProps<{ question: string }>()
</script>
<template>
  <aside
    class="clarification"
    role="note"
  >
    <strong>需要你补充信息后才能继续</strong><p>{{ question }}</p>
  </aside>
</template>
<style scoped>.clarification { padding: var(--space-3); border-inline-start: 3px solid var(--color-primary); background: var(--color-surface); }</style>
