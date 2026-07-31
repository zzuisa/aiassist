<script setup lang="ts">
import { RouterLink } from 'vue-router'
import type { ReleaseEntry } from '@/api/releases'

defineProps<{
  release: ReleaseEntry
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <div
    class="release-backdrop"
    role="presentation"
    @click.self="emit('close')"
  >
    <section
      class="release-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="release-dialog-title"
    >
      <button
        type="button"
        class="release-close"
        aria-label="关闭更新公告"
        @click="emit('close')"
      >
        ×
      </button>
      <p class="eyebrow">
        AI Assist 已更新
      </p>
      <h2 id="release-dialog-title">
        本次更新内容
      </h2>
      <p class="release-version">
        {{ release.version }} · {{ release.message }}
      </p>
      <ul class="release-changes">
        <li
          v-for="change in release.changes"
          :key="change"
        >
          {{ change }}
        </li>
      </ul>
      <div class="release-meta">
        <span>版本 {{ release.commit_short }}</span>
        <span>{{ new Date(release.deployed_at).toLocaleString() }}</span>
      </div>
      <div class="release-actions">
        <RouterLink
          class="primary"
          to="/settings/updates"
          @click="emit('close')"
        >
          查看更新历史
        </RouterLink>
        <button
          type="button"
          class="secondary"
          @click="emit('close')"
        >
          稍后查看
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.release-backdrop {
  position: fixed;
  inset: 0;
  z-index: 300;
  display: grid;
  place-items: center;
  padding: var(--space-4);
  background: rgba(15, 23, 42, 0.46);
}
.release-dialog {
  position: relative;
  width: min(100%, 520px);
  max-height: min(680px, 90vh);
  overflow: auto;
  padding: var(--space-6);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  color: var(--color-text);
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.25);
}
.release-close {
  position: absolute;
  top: var(--space-3);
  right: var(--space-3);
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  border: 0;
  background: transparent;
  color: var(--color-text-muted);
  font-size: 1.5rem;
  cursor: pointer;
}
.eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--status-normal);
  font-size: 0.8rem;
  font-weight: 700;
}
h2 { margin: 0 0 var(--space-2); }
.release-version { color: var(--color-text-muted); }
.release-changes {
  margin: var(--space-4) 0;
  padding-left: 1.25rem;
  line-height: 1.7;
}
.release-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
.release-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-5);
}
.release-actions a,
.release-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: var(--tap-target);
  padding: 0 var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}
.release-actions .primary {
  border-color: var(--status-normal);
  background: var(--status-normal);
  color: white;
}
.release-actions .secondary {
  background: var(--color-surface);
  color: inherit;
}
</style>
