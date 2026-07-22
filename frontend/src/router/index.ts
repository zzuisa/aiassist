import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// Business routes are added incrementally per user story. Route guards that
// enforce authentication are wired in Phase 2 (T027).
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/today',
  },
  {
    path: '/today',
    name: 'today',
    component: () => import('@/modules/today/TodayPage.vue'),
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})
