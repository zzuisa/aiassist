<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'

function loadStoredSettings(): { min_frequency?: number; max_terms?: number } {
  try {
    return JSON.parse(window.localStorage.getItem('aiassist:word-cloud-settings') || '{}') as {
      min_frequency?: number
      max_terms?: number
    }
  } catch {
    return {}
  }
}
const stored = loadStoredSettings()
const minFrequency = ref(stored.min_frequency ?? 2)
const maxTerms = ref(stored.max_terms ?? 100)
const saved = ref(false)
function save(): void {
  window.localStorage.setItem('aiassist:word-cloud-settings', JSON.stringify({
    min_frequency: minFrequency.value, max_terms: maxTerms.value,
  }))
  saved.value = true
}
</script>

<template>
  <main class="settings">
    <h1>博客设置</h1>
    <section>
      <h2>词云</h2>
      <p>设置只会用于下一次手动重建；不会在保存文章时自动运行。</p>
      <label>最低出现频次<input
        v-model.number="minFrequency"
        type="number"
        min="1"
        max="100000"
      ></label>
      <label>最多展示词数<input
        v-model.number="maxTerms"
        type="number"
        min="1"
        max="500"
      ></label>
      <div class="actions">
        <button @click="save">
          保存词云设置
        </button><RouterLink to="/blog/word-cloud">
          前往词云并手动重建
        </RouterLink>
      </div>
      <p
        v-if="saved"
        role="status"
      >
        设置已保存
      </p>
    </section>
  </main>
</template>

<style scoped>
.settings{max-width:760px;margin:auto;padding:var(--space-4)}section{padding:var(--space-4);border:1px solid var(--color-border);border-radius:var(--radius-lg)}label{display:grid;gap:var(--space-1);margin:var(--space-3) 0}input,button{min-height:var(--tap-target);padding:0 var(--space-2)}.actions{display:flex;align-items:center;gap:var(--space-3);flex-wrap:wrap}
</style>
