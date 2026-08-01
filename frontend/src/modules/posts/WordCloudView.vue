<script setup lang="ts">
import { computed } from 'vue'
import type { WordCloudTerm } from '@/api/blogQueries'

const props = defineProps<{ terms: WordCloudTerm[] }>()
const emit = defineEmits<{ select: [term: WordCloudTerm] }>()
const maximum = computed(() => Math.max(1, ...props.terms.map((term) => term.count)))
function size(count: number): string {
  return `${0.85 + (count / maximum.value) * 1.35}rem`
}
</script>

<template>
  <ul
    class="cloud"
    aria-label="文章词云"
  >
    <li
      v-for="term in terms"
      :key="term.id"
    >
      <button
        :style="{ fontSize: size(term.count) }"
        :aria-label="`${term.term}，出现于 ${term.count} 篇文章`"
        @click="emit('select', term)"
      >
        {{ term.term }} <small>{{ term.count }}</small>
      </button>
    </li>
  </ul>
</template>

<style scoped>
.cloud{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:var(--space-3);min-height:240px;max-width:760px;margin:auto;padding:var(--space-4);list-style:none}.cloud button{min-height:var(--tap-target);max-width:14rem;border:0;background:transparent;color:var(--status-ai);cursor:pointer;overflow:hidden;text-overflow:ellipsis}.cloud small{font-size:.65em;color:var(--color-text-muted)}
</style>
