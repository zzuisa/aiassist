<script setup lang="ts">
import type { AgentResultItemView } from './resultPresentation'

defineProps<{ item: AgentResultItemView }>()
</script>

<template>
  <article
    class="result-item"
    :class="`tone-${item.tone}`"
  >
    <header>
      <span
        v-if="item.status"
        class="status"
      >{{ item.status }}</span>
      <strong>{{ item.title }}</strong>
    </header>
    <p v-if="item.description">
      {{ item.description }}
    </p>
    <div
      v-if="item.category || item.tags.length"
      class="chips"
    >
      <span v-if="item.category">{{ item.category }}</span>
      <span
        v-for="tag in item.tags"
        :key="tag"
      >#{{ tag }}</span>
    </div>
    <dl
      v-if="item.metrics.length"
      class="metrics"
    >
      <template
        v-for="metric in item.metrics"
        :key="metric.label"
      >
        <dt>{{ metric.label }}</dt><dd>{{ metric.value }}</dd>
      </template>
    </dl>
    <footer>
      <RouterLink
        v-if="item.link"
        :to="item.link"
        class="open-link"
      >
        打开查看 <span aria-hidden="true">→</span>
      </RouterLink>
      <details v-if="item.details.length">
        <summary>更多信息</summary>
        <dl>
          <template
            v-for="detail in item.details"
            :key="detail.label"
          >
            <dt>{{ detail.label }}</dt>
            <dd>{{ detail.value }}</dd>
          </template>
        </dl>
      </details>
    </footer>
  </article>
</template>

<style scoped>
.result-item { display: grid; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-border); border-inline-start: 3px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); }
.result-item:hover { border-color: var(--color-primary); }
.tone-success { border-inline-start-color: var(--status-done); }
.tone-warning { border-inline-start-color: var(--status-warning, #b7791f); }
.tone-danger { border-inline-start-color: var(--status-overdue); }
header { display: flex; align-items: center; gap: var(--space-2); }
header strong { min-width: 0; overflow-wrap: anywhere; }
.status { flex: none; padding: .1rem .45rem; border-radius: 999px; background: var(--color-surface-2); color: var(--color-text-muted); font-size: .75rem; }
p { margin: 0; color: var(--color-text-muted); line-height: 1.55; }
.chips { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.chips span { padding: .15rem .5rem; border-radius: 999px; background: var(--color-surface-2); color: var(--color-text-muted); font-size: .8rem; }
footer { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-2); }
.open-link { color: var(--color-primary); font-weight: 600; text-decoration: none; }
details { margin-inline-start: auto; }
summary { cursor: pointer; color: var(--color-text-muted); }
dl { margin: var(--space-2) 0 0; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--space-1) var(--space-2); }
dt { color: var(--color-text-muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.metrics { display: flex; gap: var(--space-3); }
.metrics dd { font-variant-numeric: tabular-nums; font-weight: 600; }
</style>
