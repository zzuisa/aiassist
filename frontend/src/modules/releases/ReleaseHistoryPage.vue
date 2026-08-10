<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { releasesApi, type ReleaseEntry } from '@/api/releases'

const releases = ref<ReleaseEntry[]>([])
const loading = ref(true)
const error = ref('')

const currentRelease = computed(() => releases.value[0] ?? null)

onMounted(async () => {
  try {
    releases.value = (await releasesApi.history()).releases
  } catch {
    error.value = '更新记录暂时无法加载。'
  } finally {
    loading.value = false
  }
})

function statusLabel(release: ReleaseEntry): string {
  if (release === currentRelease.value) return '当前运行'
  if (release.deployment_status === 'verified') return '历史版本'
  if (release.deployment_status === 'deploying') return '部署中'
  return '部署失败'
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString()
}
</script>

<template>
  <main class="release-history">
    <header class="history-head">
      <div>
        <p class="eyebrow">
          系统更新
        </p>
        <h1>更新历史</h1>
        <p class="muted">
          查看每次部署的变更内容、Git 推送状态和当前运行版本。
        </p>
      </div>
      <span
        v-if="currentRelease"
        class="current-badge"
      >当前 {{ currentRelease.version }}</span>
    </header>

    <p
      v-if="loading"
      class="muted"
    >
      正在加载更新记录…
    </p>
    <p
      v-else-if="error"
      class="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-else-if="!releases.length"
      class="empty"
    >
      暂无更新记录。
    </p>

    <ol
      v-else
      class="release-list"
    >
      <li
        v-for="release in releases"
        :key="release.id"
        class="release-card"
        :class="{ current: release === currentRelease }"
      >
        <div class="release-card-head">
          <div>
            <h2>{{ release.version }}</h2>
            <p class="message">
              {{ release.message }}
            </p>
          </div>
          <span class="status-badge">{{ statusLabel(release) }}</span>
        </div>
        <div class="status-grid">
          <span>提交 <code>{{ release.commit_short }}</code></span>
          <span>推送 {{ release.git_pushed ? '已完成' : '未完成' }}</span>
          <span>部署 {{ release.deployment_status === 'verified' ? '已验证' : release.deployment_status }}</span>
          <span>{{ formatDate(release.deployed_at) }}</span>
        </div>
        <ul class="changes">
          <li
            v-for="change in release.changes"
            :key="change"
          >
            {{ change }}
          </li>
        </ul>
        <details v-if="release.changed_files.length">
          <summary>查看变更文件（{{ release.changed_files.length }}）</summary>
          <ul class="files">
            <li
              v-for="file in release.changed_files"
              :key="file"
            >
              <code>{{ file }}</code>
            </li>
          </ul>
        </details>
      </li>
    </ol>
  </main>
</template>

<style scoped>
.release-history { max-width: 860px; margin: 0 auto; padding: var(--space-4); }
.history-head { display: flex; justify-content: space-between; gap: var(--space-4); align-items: flex-start; margin-bottom: var(--space-5); }
.eyebrow { margin: 0 0 var(--space-1); color: var(--status-normal); font-size: 0.8rem; font-weight: 700; }
h1, h2, p { margin-top: 0; }
h1 { margin-bottom: var(--space-1); }
.muted, .empty, .status-grid, .message { color: var(--color-text-muted); }
.current-badge, .status-badge { display: inline-flex; align-items: center; min-height: 28px; padding: 0 var(--space-2); border-radius: 999px; background: var(--color-surface-2); color: var(--status-normal); font-size: 0.8rem; white-space: nowrap; }
.release-list { display: grid; gap: var(--space-3); list-style: none; padding: 0; margin: 0; }
.release-card { padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); }
.release-card.current { border-color: var(--status-normal); box-shadow: 0 0 0 2px color-mix(in srgb, var(--status-normal) 16%, transparent); }
.release-card-head { display: flex; justify-content: space-between; gap: var(--space-3); align-items: flex-start; }
.release-card h2 { margin-bottom: var(--space-1); font-size: 1.05rem; }
.message { margin-bottom: 0; }
.status-grid { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); margin: var(--space-3) 0; font-size: 0.8rem; }
.changes { margin: 0 0 var(--space-3); padding-left: 1.25rem; line-height: 1.6; }
summary { cursor: pointer; color: var(--status-normal); font-size: 0.85rem; }
.files { max-height: 220px; overflow: auto; margin-bottom: 0; padding-left: 1.25rem; }
.files code { color: var(--color-text-muted); font-size: 0.78rem; word-break: break-all; }
.error { color: var(--status-urgent); }
@media (max-width: 560px) { .history-head { flex-direction: column; } .release-card-head { flex-direction: column; } }
</style>
