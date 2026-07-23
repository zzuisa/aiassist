import { api } from '@/api/client'

export interface DependencyState {
  configured: boolean
  state: 'ready' | 'degraded' | 'unconfigured'
  provider_key?: string | null
}

export interface UserSettings {
  user: {
    id: string
    email: string
    display_name: string
    timezone: string
    locale: string
    notification_preferences: Record<string, unknown>
  }
  notification_preferences: {
    in_app_enabled: boolean
    email_enabled: boolean
    critical_email_enabled: boolean
    quiet_hours_start: string | null
    quiet_hours_end: string | null
  }
  dependencies: {
    mail: DependencyState
    llm: DependencyState
    speech: DependencyState
    storage: DependencyState
  }
}

export const settingsApi = {
  get: () => api.get<UserSettings>('/settings'),
  patch: (body: Record<string, unknown>) => api.patch<UserSettings>('/settings', body),
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post<void>('/settings/password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
}
