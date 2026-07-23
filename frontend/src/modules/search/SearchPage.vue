<script setup lang="ts">
import { ref, watch } from 'vue'
import { searchApi, TYPE_LABELS, type SearchResponse } from '@/api/search'
import SearchResults from '@/modules/search/SearchResults.vue'

const query = ref('')
const typeFilter = ref<string>('')
const results = ref<SearchResponse | null>(null)
const loading = ref(false)

const typeOptions = ['', ...Object.keys(TYPE_LABELS)]

let debounce: ReturnType<typeof setTimeout> | null = null

async function run(): Promise<void> {
  if (!query.value.trim()) {
    results.value = null
    return
  }
  loading.value = true
  try {
    results.value = await searchApi.search(query.value.trim(), typeFilter.value || undefined)
  } finally {
    loading.value = false
  }
}

watch([query, typeFilter], () => {
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(run, 250)
})

function reset(): void {
  query.value = ''
  typeFilter.value = ''
  results.value = null
}
</script>

<template>
  <main class="search">
    <div class="bar">
      <input
        v-model="query"
        type="search"
        placeholder="搜索任务、习惯、收藏、博客…"
        aria-label="搜索"
        @keydown.enter="run"
      >
      <select
        v-model="typeFilter"
        aria-label="按类型筛选"
      >
        <option
          v-for="t in typeOptions"
          :key="t"
          :value="t"
        >
          {{ t ? TYPE_LABELS[t] : '全部类型' }}
        </option>
      </select>
      <button
        type="button"
        @click="reset"
      >
        清除
      </button>
    </div>

    <SearchResults
      :results="results"
      :loading="loading"
      :pending-hint="(results?.index_pending_count ?? 0) > 0"
    />
  </main>
</template>

<style scoped>
.search {
  padding: var(--space-4);
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.bar {
  display: flex;
  gap: var(--space-2);
  position: sticky;
  top: 0;
}
input {
  flex: 1;
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
select,
button {
  min-height: var(--tap-target);
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
</style>
