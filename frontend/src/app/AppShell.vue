<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useJobsStore } from '@/stores/jobs'
import TaskCenterDrawer from '@/components/jobs/TaskCenterDrawer.vue'
import NotificationCenter from '@/components/notifications/NotificationCenter.vue'
import { releasesApi, type ReleaseEntry } from '@/api/releases'
import ReleaseUpdateDialog from '@/modules/releases/ReleaseUpdateDialog.vue'

// Responsive shell: left sidebar on wide screens, bottom nav on mobile. Opens a
// single global EventSource for job/notification updates.
const jobs = useJobsStore()
const route = useRoute()
const taskCenterOpen = ref(false)
const notifOpen = ref(false)
const currentRelease = ref<ReleaseEntry | null>(null)
const updateNoticeOpen = ref(false)

const primaryNav = [
  { to: '/today', label: '今日', icon: '📅' },
  { to: '/calendar', label: '日历', icon: '🗓️' },
  { to: '/habits', label: '习惯', icon: '🔁' },
  { to: '/captures', label: '收藏', icon: '📷' },
  { to: '/search', label: '搜索', icon: '🔍' },
  { to: '/posts', label: '博客', icon: '✍️' },
  { to: '/assistant', label: 'AI 助手', icon: '🤖' },
  { to: '/agent', label: '自助 Agent', icon: '🧩' },
  { to: '/settings', label: '设置', icon: '⚙️' },
]

const activeCount = computed(() => jobs.activeJobs.length)

onMounted(() => {
  jobs.connect()
  void loadReleaseNotice()
})
onBeforeUnmount(() => {
  jobs.disconnect()
})

async function loadReleaseNotice(): Promise<void> {
  try {
    const history = await releasesApi.history()
    const latest = history.releases[0]
    if (!latest) return
    currentRelease.value = latest
    const lastSeen = window.localStorage.getItem('aiassist:last-seen-release')
    if (lastSeen !== latest.id) updateNoticeOpen.value = true
  } catch {
    // Release metadata is informational and must never block the application shell.
  }
}

function acknowledgeRelease(): void {
  if (currentRelease.value) {
    window.localStorage.setItem('aiassist:last-seen-release', currentRelease.value.id)
  }
  updateNoticeOpen.value = false
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        AI Assist
      </div>
      <nav>
        <RouterLink
          v-for="item in primaryNav"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: route.path === item.to }"
        >
          <span aria-hidden="true">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <main class="content">
      <header class="topbar">
        <div
          class="status"
          role="status"
        >
          <span
            v-if="jobs.reconnecting"
            class="reconnecting"
          >正在重新连接…</span>
          <span v-else-if="activeCount > 0">{{ activeCount }} 个后台任务</span>
        </div>
        <div class="topbar-actions">
          <button
            type="button"
            class="icon-btn"
            aria-label="通知"
            @click="notifOpen = true"
          >
            🔔
            <span
              v-if="jobs.unreadCount > 0"
              class="badge"
            >{{ jobs.unreadCount }}</span>
          </button>
          <button
            type="button"
            class="icon-btn"
            aria-label="后台任务中心"
            @click="taskCenterOpen = true"
          >
            📋
            <span
              v-if="activeCount > 0"
              class="badge"
            >{{ activeCount }}</span>
          </button>
        </div>
      </header>
      <RouterView v-slot="{ Component }">
        <transition
          name="page"
          mode="out-in"
        >
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>

    <TaskCenterDrawer
      :open="taskCenterOpen"
      @close="taskCenterOpen = false"
    />
    <NotificationCenter
      :open="notifOpen"
      @close="notifOpen = false"
    />

    <ReleaseUpdateDialog
      v-if="updateNoticeOpen && currentRelease"
      :release="currentRelease"
      @close="acknowledgeRelease"
    />

    <nav
      class="bottom-nav"
      aria-label="主导航"
    >
      <RouterLink
        v-for="item in primaryNav"
        :key="item.to"
        :to="item.to"
        class="bottom-item"
        :class="{ active: route.path === item.to }"
      >
        <span aria-hidden="true">{{ item.icon }}</span>
        <span class="label">{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}
.sidebar {
  border-right: 1px solid var(--color-border);
  padding: var(--space-4);
  padding-top: calc(var(--safe-top) + var(--space-4));
}
.brand {
  font-weight: 700;
  font-size: 1.1rem;
  margin-bottom: var(--space-6);
}
.nav-item,
.bottom-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  text-decoration: none;
}
.nav-item.active,
.bottom-item.active {
  background: var(--color-surface-2);
  color: var(--status-normal);
}
.content {
  min-width: 0;
}
.topbar {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-4);
  padding-top: var(--safe-top);
}
.topbar-actions {
  display: flex;
  gap: var(--space-2);
}
.icon-btn {
  position: relative;
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 1.1rem;
}
.badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--status-urgent);
  color: white;
  font-size: 0.65rem;
  display: grid;
  place-items: center;
}
.reconnecting {
  color: var(--status-due-soon);
}
.bottom-nav {
  display: none;
}

@media (max-width: 720px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    display: none;
  }
  .bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 100;
    display: flex;
    justify-content: space-around;
    align-items: stretch;
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
    padding: var(--space-2) var(--space-2) var(--safe-bottom);
    box-shadow: 0 -4px 16px rgba(15, 23, 42, 0.08);
    isolation: isolate;
  }
  .bottom-item {
    flex: 1 1 0;
    min-width: 0;
    justify-content: center;
    flex-direction: column;
    gap: 2px;
    font-size: 0.75rem;
    padding: 0 var(--space-1);
    white-space: nowrap;
  }
  .content {
    padding-bottom: calc(var(--tap-target) + var(--space-4) + var(--safe-bottom));
  }
}
</style>
