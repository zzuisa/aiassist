<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { settingsApi, type UserSettings } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import DependencyBadge from '@/modules/settings/DependencyBadge.vue'
import { ApiError } from '@/api/client'

const auth = useAuthStore()
const settings = ref<UserSettings | null>(null)
const displayName = ref('')
const timezone = ref('')
const saved = ref('')

// Common IANA timezones for the selector; the backend validates the full set.
const timezones = [
  'Europe/Berlin',
  'Asia/Shanghai',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
]

async function load(): Promise<void> {
  settings.value = await settingsApi.get()
  displayName.value = settings.value.user.display_name
  timezone.value = settings.value.user.timezone
}

onMounted(load)

async function save(): Promise<void> {
  saved.value = ''
  settings.value = await settingsApi.patch({
    display_name: displayName.value,
    timezone: timezone.value,
  })
  saved.value = '已保存'
}

// Password change
const currentPw = ref('')
const newPw = ref('')
const pwMsg = ref('')

async function changePassword(): Promise<void> {
  pwMsg.value = ''
  try {
    await settingsApi.changePassword(currentPw.value, newPw.value)
    pwMsg.value = '密码已更新，其他会话已退出。'
    currentPw.value = ''
    newPw.value = ''
  } catch (err) {
    pwMsg.value = err instanceof ApiError ? '当前密码不正确或新密码太短。' : '修改失败。'
  }
}

async function onLogout(): Promise<void> {
  await auth.logout()
  window.location.assign('/login')
}
</script>

<template>
  <section
    v-if="settings"
    class="settings"
  >
    <h1>设置</h1>

    <fieldset>
      <legend>账户</legend>
      <label>
        <span>邮箱</span>
        <input
          :value="settings.user.email"
          disabled
          aria-label="邮箱"
        >
      </label>
      <label>
        <span>昵称</span>
        <input
          v-model="displayName"
          aria-label="昵称"
        >
      </label>
      <label>
        <span>时区</span>
        <select
          v-model="timezone"
          aria-label="时区"
        >
          <option
            v-for="tz in timezones"
            :key="tz"
            :value="tz"
          >{{ tz }}</option>
        </select>
      </label>
      <button
        type="button"
        class="primary"
        @click="save"
      >
        保存
      </button>
      <span
        v-if="saved"
        class="ok"
      >{{ saved }}</span>
    </fieldset>

    <fieldset>
      <legend>依赖状态</legend>
      <DependencyBadge
        label="邮件"
        :state="settings.dependencies.mail"
      />
      <DependencyBadge
        label="AI 模型"
        :state="settings.dependencies.llm"
      />
      <DependencyBadge
        label="语音"
        :state="settings.dependencies.speech"
      />
      <DependencyBadge
        label="存储"
        :state="settings.dependencies.storage"
      />
    </fieldset>

    <fieldset>
      <legend>修改密码</legend>
      <label>
        <span>当前密码</span>
        <input
          v-model="currentPw"
          type="password"
          aria-label="当前密码"
        >
      </label>
      <label>
        <span>新密码</span>
        <input
          v-model="newPw"
          type="password"
          aria-label="新密码"
        >
      </label>
      <button
        type="button"
        @click="changePassword"
      >
        更新密码
      </button>
      <span
        v-if="pwMsg"
        class="msg"
      >{{ pwMsg }}</span>
    </fieldset>

    <button
      type="button"
      class="logout"
      @click="onLogout"
    >
      退出登录
    </button>
  </section>
</template>

<style scoped>
.settings {
  padding: var(--space-4);
  max-width: 560px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
fieldset {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
legend {
  padding: 0 var(--space-2);
  color: var(--color-text-muted);
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
input,
select {
  min-height: var(--tap-target);
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
}
button {
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
button.primary {
  background: var(--status-normal);
  color: white;
  border: none;
}
button.logout {
  color: var(--status-urgent);
}
.ok,
.msg {
  color: var(--status-done);
  font-size: 0.85rem;
}
</style>
