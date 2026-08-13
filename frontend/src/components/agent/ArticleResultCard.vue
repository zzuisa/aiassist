<script setup lang="ts">
import type { AgentArticleResult } from '@/api/agent'

defineProps<{ article: AgentArticleResult }>()
</script>

<template>
  <RouterLink
    class="article-result-card"
    :to="article.link"
    :aria-label="`查看文章：${article.title}`"
  >
    <span class="eyebrow">文章</span>
    <strong>{{ article.title }}</strong>
    <span
      v-if="article.category || article.tags.length"
      class="meta"
    >
      <span v-if="article.category">{{ article.category }}</span>
      <span
        v-for="tag in article.tags"
        :key="tag"
      >#{{ tag }}</span>
    </span>
    <span class="action">打开查看 <span aria-hidden="true">→</span></span>
  </RouterLink>
</template>

<style scoped>
.article-result-card {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: inherit;
  text-decoration: none;
  background: var(--color-surface);
}
.article-result-card:hover,
.article-result-card:focus-visible { border-color: var(--color-primary); }
.eyebrow, .meta { color: var(--color-text-muted); font-size: .875rem; }
.meta { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.action { color: var(--color-primary); font-weight: 600; }
</style>
