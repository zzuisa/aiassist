<script setup lang="ts">
import { RouterView } from 'vue-router'

// Only routes that resolve today are listed. Later user stories add triage,
// skills, taxonomy and settings child routes and extend this list.
const navItems = [{ to: '/blog', label: '文章', exact: true }]
</script>

<template>
  <div class="blog-module">
    <nav class="blog-nav">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="blog-nav__link"
        :class="{ 'blog-nav__link--exact': item.exact }"
        active-class="blog-nav__link--active"
        :exact-active-class="item.exact ? 'blog-nav__link--active' : undefined"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
    <section class="blog-content">
      <RouterView />
    </section>
  </div>
</template>

<style scoped>
.blog-module {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.blog-nav {
  display: flex;
  gap: 0.25rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  overflow-x: auto;
}

.blog-nav__link {
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  color: var(--color-text-muted, #6b7280);
  text-decoration: none;
  white-space: nowrap;
  font-size: 0.9rem;
}

.blog-nav__link--active {
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #4f46e5);
  font-weight: 600;
}

.blog-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
