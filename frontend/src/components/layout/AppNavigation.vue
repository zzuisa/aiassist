<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

export interface NavigationItem {
  to: RouteLocationRaw
  path: string
  label: string
  icon: string
}

defineProps<{
  items: NavigationItem[]
  activePath: string
  activeCount: number
  open: boolean
}>()

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <div
    class="mobile-nav-backdrop"
    :class="{ visible: open }"
    aria-hidden="true"
    @click="emit('close')"
  />
  <aside
    id="primary-navigation"
    class="sidebar"
    :class="{ open }"
    aria-label="主导航"
  >
    <p class="nav-label">
      PERSONAL OPERATING SYSTEM
    </p>
    <nav class="side-nav">
      <RouterLink
        v-for="item in items"
        :key="item.path"
        :to="item.to"
        class="nav-item"
        :class="{ active: activePath === item.path || activePath.startsWith(`${item.path}/`) }"
        :data-nav-icon="item.icon"
        :title="item.label"
        @click="emit('close')"
      >
        <span aria-hidden="true">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>

    <section class="side-progress">
      <span>正在运行</span>
      <strong>{{ activeCount }}</strong>
      <small>后台任务</small>
      <button
        type="button"
        @click="$emit('close')"
      >
        保持专注，任务会在后台继续 →
      </button>
    </section>
  </aside>
</template>

<style scoped>
.mobile-nav-backdrop {
  display: none;
}

.sidebar {
  position: sticky;
  top: var(--header-height);
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-height));
  padding: var(--space-8) var(--space-6);
  border-right: 1px solid var(--color-border);
}

.nav-label {
  margin: 0 0 var(--space-4);
  color: var(--color-accent);
  font-size: var(--text-xs);
  font-weight: 800;
  letter-spacing: var(--tracking-label);
}

.side-nav {
  display: grid;
  gap: var(--space-1);
}

.nav-item {
  display: flex;
  align-items: center;
  min-height: var(--tap-target);
  gap: var(--space-3);
  padding: 0.65rem 1rem;
  border-left: 3px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-body);
  text-decoration: none;
  transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.nav-item > span:first-child {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  font-weight: 800;
}

.nav-item:hover {
  background: rgba(232, 238, 227, 0.55);
  color: var(--color-primary);
}

.nav-item.active {
  border-left-color: var(--color-accent);
  background: #e8ebdf;
  color: var(--color-primary);
  font-weight: 700;
}

.side-progress {
  margin-top: auto;
  padding: 1.2rem;
  border-radius: var(--radius-lg);
  background: var(--color-primary);
  color: white;
}

.side-progress span,
.side-progress small {
  display: block;
  color: #c7d8d2;
  font-size: 0.75rem;
}

.side-progress strong {
  display: block;
  margin: 0.2rem 0;
  color: var(--color-accent-soft);
  font: 700 2.5rem var(--font-serif);
}

.side-progress button {
  padding: 0.7rem 0 0;
  border: 0;
  background: transparent;
  color: var(--color-accent-soft);
  font-weight: 700;
  text-align: left;
  cursor: pointer;
}

@media (max-width: 1050px) {
  .mobile-nav-backdrop {
    position: fixed;
    z-index: 49;
    inset: 0;
    display: block;
    background: rgba(10, 25, 21, 0.38);
    opacity: 0;
    pointer-events: none;
    backdrop-filter: blur(0);
    transition: opacity 0.3s ease, backdrop-filter 0.3s ease;
  }

  .mobile-nav-backdrop.visible {
    opacity: 1;
    pointer-events: auto;
    backdrop-filter: blur(7px);
  }

  .sidebar {
    position: fixed;
    z-index: 50;
    top: auto;
    right: 1rem;
    bottom: calc(6.1rem + var(--safe-bottom));
    left: auto;
    width: min(340px, calc(100vw - 2rem));
    height: auto;
    max-height: calc(100dvh - 8rem - var(--safe-bottom));
    overflow: auto;
    overscroll-behavior: contain;
    padding: 1rem;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 26px;
    background: linear-gradient(150deg, rgba(23, 61, 51, 0.98), rgba(16, 39, 33, 0.97));
    box-shadow: 0 28px 80px rgba(5, 23, 18, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.12);
    opacity: 0;
    pointer-events: none;
    transform: translateY(28px) scale(0.9) rotate(2deg);
    transform-origin: bottom right;
    transition: opacity 0.22s ease, transform 0.42s cubic-bezier(0.2, 1.25, 0.32, 1);
  }

  .sidebar.open {
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0) scale(1) rotate(0);
  }

  .nav-label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0.2rem 0.4rem 0.8rem;
    color: #a7c4bb;
  }

  .nav-label::after {
    content: 'JUMP MENU';
    padding: 0.25rem 0.45rem;
    border: 1px solid rgba(217, 238, 159, 0.3);
    border-radius: var(--radius-pill);
    color: var(--color-accent-soft);
    font-size: 0.56rem;
  }

  .side-nav {
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.35rem;
  }

  .nav-item {
    display: grid;
    grid-template-rows: 24px auto;
    min-width: 0;
    min-height: 49px;
    gap: 0.18rem;
    padding: 0.38rem 0.18rem;
    place-items: center;
    border: 0;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.045);
    color: #d8e5e1;
    font-size: 0.54rem;
    line-height: 1;
    white-space: nowrap;
  }

  .nav-item:hover,
  .nav-item:focus-visible {
    background: rgba(255, 255, 255, 0.1);
    color: white;
    transform: translateY(-1px);
  }

  .nav-item.active {
    border: 0;
    background: var(--color-accent-soft);
    color: var(--color-primary);
    box-shadow: 0 8px 22px rgba(217, 238, 159, 0.15);
  }

  .side-progress {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    margin-top: 0.65rem;
    padding: 0.85rem 1rem;
    background: rgba(0, 0, 0, 0.16);
  }

  .side-progress strong {
    grid-row: 1 / 3;
    grid-column: 2;
    font-size: 2rem;
  }

  .side-progress button {
    grid-column: 1 / -1;
  }
}

@media (max-width: 700px) {
  .sidebar {
    right: 0.75rem;
    bottom: calc(5.75rem + var(--safe-bottom));
    width: calc(100vw - 1.5rem);
    max-height: calc(100dvh - 7rem - var(--safe-bottom));
    border-radius: 22px;
  }
}
</style>
