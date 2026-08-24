<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  activeCount: number
  unreadCount: number
  reconnecting: boolean
}>()

const emit = defineEmits<{
  search: [query: string]
  openNotifications: []
  openTasks: []
}>()

const query = ref('')

function submitSearch(): void {
  const value = query.value.trim()
  if (value) emit('search', value)
}
</script>

<template>
  <header class="topbar">
    <RouterLink
      class="brand"
      to="/today"
      aria-label="AI Assist 首页"
    >
      <span aria-hidden="true">AI</span>
      <b>AI Assist<small>PERSONAL OS</small></b>
    </RouterLink>

    <nav
      class="app-switch"
      aria-label="应用切换"
    >
      <a href="https://roguelife.de/interview/">Interview</a>
      <RouterLink
        to="/today"
        class="active"
        aria-current="page"
      >
        AI Assist
      </RouterLink>
    </nav>

    <div class="header-actions">
      <form
        class="search"
        role="search"
        @submit.prevent="submitSearch"
      >
        <span aria-hidden="true">⌕</span>
        <label
          for="global-search"
          class="sr-only"
        >搜索 AI Assist</label>
        <input
          id="global-search"
          v-model="query"
          type="search"
          placeholder="搜索任务、文章、记录…"
        >
      </form>

      <div
        v-if="reconnecting || activeCount"
        class="job-status"
        role="status"
      >
        <span class="job-status__dot" />
        {{ reconnecting ? '正在重新连接…' : `${activeCount} 个任务运行中` }}
      </div>

      <button
        type="button"
        class="header-button"
        aria-label="通知"
        @click="emit('openNotifications')"
      >
        <span aria-hidden="true">◉</span>
        <span
          v-if="unreadCount > 0"
          class="badge"
        >{{ unreadCount }}</span>
      </button>
      <button
        type="button"
        class="header-button"
        aria-label="后台任务中心"
        @click="emit('openTasks')"
      >
        <span aria-hidden="true">▤</span>
        <span
          v-if="activeCount > 0"
          class="badge"
        >{{ activeCount }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky;
  z-index: 40;
  top: 0;
  display: flex;
  align-items: center;
  height: var(--header-height);
  gap: var(--space-8);
  padding: var(--safe-top) var(--space-8) 0;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-header-glass);
  backdrop-filter: blur(15px);
}

.brand {
  display: flex;
  align-items: center;
  min-width: 190px;
  gap: 0.7rem;
  color: var(--color-text);
  text-decoration: none;
}

.brand > span {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 50%;
  background: var(--color-primary);
  color: var(--color-accent-soft);
  font-weight: 800;
}

.brand b {
  line-height: 1;
}

.brand small {
  display: block;
  margin-top: 0.35rem;
  color: var(--color-text-muted);
  font-size: 0.58rem;
  letter-spacing: 0.16em;
}

.app-switch {
  display: flex;
  padding: 3px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
}

.app-switch a {
  padding: 0.45rem 0.75rem;
  border-radius: var(--radius-pill);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  text-decoration: none;
}

.app-switch a.active {
  background: var(--color-primary);
  color: white;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin-left: auto;
}

.search {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0.55rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: white;
}

.search:focus-within {
  border-color: var(--color-accent);
  box-shadow: var(--shadow-focus-soft);
}

.search input {
  width: 230px;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
}

.job-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  white-space: nowrap;
}

.job-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-running);
  box-shadow: var(--shadow-running);
}

.header-button {
  position: relative;
  display: grid;
  flex: none;
  width: var(--tap-target);
  height: var(--tap-target);
  padding: 0;
  place-items: center;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  background: var(--color-surface);
  cursor: pointer;
}

.header-button:hover {
  border-color: var(--color-accent);
  background: var(--color-surface-2);
}

.badge {
  position: absolute;
  top: -2px;
  right: -2px;
  display: grid;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  place-items: center;
  border: 2px solid var(--color-bg);
  border-radius: var(--radius-pill);
  background: var(--status-urgent);
  color: white;
  font-size: 0.6rem;
}

@media (max-width: 1050px) {
  .app-switch,
  .job-status {
    display: none;
  }
}

@media (max-width: 700px) {
  .topbar {
    align-content: center;
    flex-wrap: wrap;
    height: auto;
    min-height: 70px;
    gap: 0.7rem;
    padding: calc(var(--safe-top) + 0.7rem) 1rem 0.7rem;
  }

  .brand {
    min-width: 0;
    margin-right: auto;
  }

  .header-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    order: 2;
    width: 100%;
  }

  .search input {
    width: 100%;
  }
}
</style>
