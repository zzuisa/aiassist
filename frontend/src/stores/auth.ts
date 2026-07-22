import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, ApiError, setCsrfToken } from '@/api/client'
import type { LoginResponse, User } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  async function login(email: string, password: string): Promise<void> {
    const resp = await api.post<LoginResponse>('/auth/login', { email, password })
    setCsrfToken(resp.csrf_token)
    user.value = resp.user
  }

  async function fetchMe(): Promise<void> {
    try {
      user.value = await api.get<User>('/auth/me')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        user.value = null
      } else {
        throw err
      }
    } finally {
      initialized.value = true
    }
  }

  async function logout(): Promise<void> {
    try {
      await api.post('/auth/logout')
    } finally {
      user.value = null
      setCsrfToken(null)
    }
  }

  return { user, initialized, loading, login, fetchMe, logout }
})
