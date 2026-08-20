<script setup lang="ts">
import { computed, ref } from 'vue'
import AgentResultItem from './AgentResultItem.vue'
import type { AgentResultItemView } from './resultPresentation'

const props = defineProps<{
  items: AgentResultItemView[]
  summary?: string | null
}>()

const query = ref('')
const expanded = ref(false)
const filtered = computed(() => {
  const normalized = query.value.trim().toLocaleLowerCase()
  if (!normalized) return props.items
  return props.items.filter((item) => item.searchText.includes(normalized))
})
const visibleItems = computed(() => expanded.value ? filtered.value : filtered.value.slice(0, 6))
</script>

<template>
  <div class="result-list">
    <div class="result-toolbar">
      <p v-if="summary">
        {{ summary }}
      </p>
      <label v-if="items.length > 1">
        <span class="sr-only">筛选处理结果</span>
        <input
          v-model="query"
          type="search"
          placeholder="筛选标题、标签或状态"
        >
      </label>
    </div>
    <div
      v-if="visibleItems.length"
      class="result-grid"
    >
      <AgentResultItem
        v-for="item in visibleItems"
        :key="item.key"
        :item="item"
      />
    </div>
    <p
      v-else
      class="empty"
    >
      没有符合筛选条件的结果。
    </p>
    <button
      v-if="!query && items.length > 6"
      type="button"
      class="toggle"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起结果' : `查看全部 ${items.length} 项` }}
    </button>
  </div>
</template>

<style scoped>
.result-list { display: grid; gap: var(--space-2); }
.result-toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.result-toolbar p { margin: 0; color: var(--color-text-muted); }
input { width: min(16rem, 100%); padding: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background); color: inherit; }
.result-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr)); gap: var(--space-2); }
.toggle { justify-self: center; }
.empty { margin: 0; color: var(--color-text-muted); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
