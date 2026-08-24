<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useJobsStore } from '@/stores/jobs'
import TaskCenterDrawer from '@/components/jobs/TaskCenterDrawer.vue'
import NotificationCenter from '@/components/notifications/NotificationCenter.vue'
import { releasesApi, type ReleaseEntry } from '@/api/releases'
import ReleaseUpdateDialog from '@/modules/releases/ReleaseUpdateDialog.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppNavigation, { type NavigationItem } from '@/components/layout/AppNavigation.vue'
import { SHELL_COMPACT_MEDIA_QUERY, useMediaQuery } from '@/composables/useMediaQuery'

const jobs = useJobsStore()
const route = useRoute()
const router = useRouter()
const taskCenterOpen = ref(false)
const notifOpen = ref(false)
const navigationOpen = ref(false)
const navigationToggle = ref<HTMLButtonElement | null>(null)
const compactNavigation = useMediaQuery(SHELL_COMPACT_MEDIA_QUERY)
const currentRelease = ref<ReleaseEntry | null>(null)
const updateNoticeOpen = ref(false)

const primaryNav: NavigationItem[] = [
  { to: '/today', path: '/today', label: '今日', icon: '⌂' },
  { to: '/calendar', path: '/calendar', label: '日历', icon: '◫' },
  { to: '/habits', path: '/habits', label: '习惯', icon: '↻' },
  { to: '/captures', path: '/captures', label: '收藏', icon: '◇' },
  { to: '/search', path: '/search', label: '搜索', icon: '⌕' },
  { to: '/blog', path: '/blog', label: '博客', icon: '文' },
  { to: '/assistant', path: '/assistant', label: '助手', icon: '✦' },
  { to: '/agent', path: '/agent', label: 'Agent', icon: '◎' },
  { to: '/settings', path: '/settings', label: '设置', icon: '⚙' },
]

const activeCount = computed(() => jobs.activeJobs.length)

watch(() => route.fullPath, () => {
  navigationOpen.value = false
})

watch([navigationOpen, compactNavigation], ([open, compact], [wasOpen]) => {
  document.body.classList.toggle('mobile-nav-open', open && compact)
  if (wasOpen && !open && compact) void nextTick(() => navigationToggle.value?.focus())
})

onMounted(() => {
  jobs.connect()
  window.addEventListener('keydown', onKeydown)
  void loadReleaseNotice()
})

onBeforeUnmount(() => {
  jobs.disconnect()
  window.removeEventListener('keydown', onKeydown)
  document.body.classList.remove('mobile-nav-open')
})

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') navigationOpen.value = false
}

async function search(query: string): Promise<void> {
  await router.push({ path: '/search', query: { q: query } })
}

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
    <AppHeader
      :active-count="activeCount"
      :unread-count="jobs.unreadCount"
      :reconnecting="jobs.reconnecting"
      @search="search"
      @open-notifications="notifOpen = true"
      @open-tasks="taskCenterOpen = true"
    />

    <div class="app-shell">
      <AppNavigation
        :items="primaryNav"
        :active-path="route.path"
        :active-count="activeCount"
        :open="navigationOpen"
        :compact="compactNavigation"
        @close="navigationOpen = false"
      />

      <div class="content">
        <RouterView v-slot="{ Component }">
          <transition
            name="page"
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </RouterView>
      </div>
    </div>

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

    <button
      ref="navigationToggle"
      type="button"
      class="mobile-nav-toggle"
      :class="{ active: navigationOpen }"
      :aria-expanded="navigationOpen"
      aria-controls="primary-navigation"
      :aria-label="navigationOpen ? '关闭主导航' : '打开主导航'"
      @click="navigationOpen = !navigationOpen"
    >
      <span
        class="mobile-nav-icon"
        aria-hidden="true"
      ><i /><i /><i /><i /></span>
    </button>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
}

.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  max-width: var(--layout-max);
  margin: auto;
}

.content {
  min-width: 0;
}

.mobile-nav-toggle {
  display: none;
}

@media (max-width: 1050px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .mobile-nav-toggle {
    position: fixed;
    z-index: 51;
    right: 1.15rem;
    bottom: calc(1.15rem + var(--safe-bottom));
    display: grid;
    width: 64px;
    height: 64px;
    padding: 0;
    place-items: center;
    border: 1px solid var(--color-nav-border);
    border-radius: 50%;
    background: linear-gradient(145deg, var(--color-accent), var(--color-primary));
    color: var(--color-accent-soft);
    box-shadow: var(--shadow-nav-toggle);
    cursor: pointer;
    transition: transform 0.35s cubic-bezier(0.2, 1.4, 0.35, 1), box-shadow 0.25s ease;
  }

  .mobile-nav-toggle:hover,
  .mobile-nav-toggle:focus-visible {
    outline: 0;
    transform: translateY(-3px) scale(1.04);
    box-shadow: var(--shadow-nav-toggle-hover);
  }

  .mobile-nav-toggle.active {
    transform: rotate(45deg);
    background: var(--gradient-nav-toggle-active);
  }

  .mobile-nav-icon {
    display: grid;
    grid-template-columns: repeat(2, 7px);
    grid-template-rows: repeat(2, 7px);
    gap: 5px;
    transition: transform 0.45s cubic-bezier(0.2, 1.35, 0.3, 1);
  }

  .mobile-nav-icon i {
    display: block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: var(--shadow-nav-icon);
  }

  .mobile-nav-toggle.active .mobile-nav-icon {
    transform: rotate(45deg) scale(0.92);
  }
}

@media (max-width: 700px) {
  .mobile-nav-toggle {
    right: 1rem;
    bottom: calc(1rem + var(--safe-bottom));
    width: 58px;
    height: 58px;
  }
}
</style>
