<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()

async function onLogout(): Promise<void> {
  await auth.logout()
  window.location.assign('/login')
}
</script>

<template>
  <section class="settings">
    <h1>设置</h1>
    <p v-if="auth.user">
      已登录：{{ auth.user.email }}
    </p>
    <button
      type="button"
      @click="onLogout"
    >
      退出登录
    </button>
  </section>
</template>

<style scoped>
.settings {
  padding: var(--space-4);
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
</style>
