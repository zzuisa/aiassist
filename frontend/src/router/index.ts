import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/modules/auth/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/app/AppShell.vue'),
    children: [
      { path: '', redirect: '/today' },
      { path: 'today', name: 'today', component: () => import('@/modules/today/TodayPage.vue') },
      {
        path: 'calendar',
        name: 'calendar',
        component: () => import('@/modules/calendar/CalendarPage.vue'),
      },
      {
        path: 'habits',
        name: 'habits',
        component: () => import('@/modules/habits/HabitsPage.vue'),
      },
      {
        path: 'captures',
        name: 'captures',
        component: () => import('@/modules/captures/CapturePage.vue'),
      },
      {
        path: 'search',
        name: 'search',
        component: () => import('@/modules/search/SearchPage.vue'),
      },
      {
        path: 'posts',
        name: 'posts',
        component: () => import('@/modules/posts/PostListPage.vue'),
      },
      {
        path: 'posts/:id',
        name: 'post-editor',
        component: () => import('@/modules/posts/PostEditorPage.vue'),
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/modules/settings/SettingsPage.vue'),
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.initialized) {
    await auth.fetchMe()
  }
  if (!to.meta.public && !auth.user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.user) {
    return { name: 'today' }
  }
  return true
})
