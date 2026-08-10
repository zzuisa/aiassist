<script setup lang="ts">
// New-content entry dialog (US1, T041): pick a source — blank / clipboard / URL /
// quick — with a one-line summary of what each does. Selecting a source emits the
// choice; the parent opens the matching specialized dialog (or creates a blank
// draft directly).
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', kind: 'blank' | 'clipboard' | 'url' | 'quick'): void
}>()
import CaptureModal from '@/modules/posts/CaptureModal.vue'

const sources = [
  { kind: 'blank', icon: '📄', label: '空白文章', desc: '从零开始写一篇文章' },
  { kind: 'clipboard', icon: '📋', label: '从剪贴板', desc: '保存剪贴板原文，稍后整理' },
  { kind: 'url', icon: '🔗', label: '从网址', desc: '保存链接并后台抓取正文' },
  { kind: 'quick', icon: '⚡', label: '快速记录', desc: '随手记一笔，先存再说' },
] as const
</script>

<template>
  <CaptureModal
    title="新建内容"
    @close="emit('close')"
  >
    <ul class="source-list">
      <li
        v-for="s in sources"
        :key="s.kind"
      >
        <button
          type="button"
          class="source"
          @click="emit('select', s.kind)"
        >
          <span class="source__icon">{{ s.icon }}</span>
          <span class="source__text">
            <span class="source__label">{{ s.label }}</span>
            <span class="source__desc">{{ s.desc }}</span>
          </span>
        </button>
      </li>
    </ul>
  </CaptureModal>
</template>

<style scoped>
.source-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.source {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: none;
  cursor: pointer;
  text-align: left;
}
.source:hover {
  border-color: var(--color-accent, #4f46e5);
  background: var(--color-accent-soft, #eef2ff);
}
.source__icon {
  font-size: 1.5rem;
}
.source__text {
  display: flex;
  flex-direction: column;
}
.source__label {
  font-weight: 600;
}
.source__desc {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}
</style>
