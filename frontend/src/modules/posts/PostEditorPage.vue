<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { postsApi, type Post } from '@/api/posts'
import { ApiError } from '@/api/client'

const route = useRoute()
const post = ref<Post | null>(null)
const title = ref('')
const markdown = ref('')
const saving = ref(false)
const conflict = ref(false)
const publishing = ref(false)
const tab = ref<'edit' | 'preview'>('edit')

async function load(): Promise<void> {
  const id = route.params.id as string
  post.value = await postsApi.get(id)
  title.value = post.value.title
  markdown.value = post.value.markdown
}

onMounted(load)

let autosaveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleAutosave(): void {
  if (autosaveTimer) clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(save, 1500)
}

async function save(): Promise<void> {
  if (!post.value || saving.value) return
  saving.value = true
  conflict.value = false
  try {
    post.value = await postsApi.save(post.value.id, title.value, markdown.value, post.value.version)
  } catch (err) {
    if (err instanceof ApiError && err.code === 'version_conflict') conflict.value = true
  } finally {
    saving.value = false
  }
}

async function togglePublish(): Promise<void> {
  if (!post.value) return
  publishing.value = true
  try {
    post.value = await postsApi.publish(
      post.value.id,
      post.value.status !== 'published',
      post.value.version,
    )
  } finally {
    publishing.value = false
  }
}
</script>

<template>
  <main
    v-if="post"
    class="editor"
  >
    <header class="head">
      <input
        v-model="title"
        class="title"
        aria-label="标题"
        @input="scheduleAutosave"
      >
      <div class="status">
        <span>{{ post.status === 'published' ? '已发布' : '草稿' }}</span>
        <button
          type="button"
          :disabled="publishing"
          @click="togglePublish"
        >
          {{ post.status === 'published' ? '取消发布' : '发布' }}
        </button>
      </div>
    </header>

    <p
      v-if="conflict"
      class="conflict"
      role="alert"
    >
      文章已被其他修改更新，请刷新后重试。
    </p>

    <nav class="tabs">
      <button
        :class="{ active: tab === 'edit' }"
        @click="tab = 'edit'"
      >
        编辑
      </button>
      <button
        :class="{ active: tab === 'preview' }"
        @click="tab = 'preview'"
      >
        预览
      </button>
      <span
        v-if="saving"
        class="saving"
      >保存中…</span>
    </nav>

    <textarea
      v-if="tab === 'edit'"
      v-model="markdown"
      class="body"
      aria-label="正文"
      @input="scheduleAutosave"
    />
    <pre
      v-else
      class="preview"
    >{{ markdown }}</pre>
  </main>
</template>

<style scoped>
.editor {
  padding: var(--space-4);
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
}
.title {
  flex: 1;
  font-size: 1.2rem;
  border: none;
  border-bottom: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text);
  padding: var(--space-2) 0;
}
.status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.status button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
.conflict {
  color: var(--status-urgent);
}
.tabs {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.tabs button {
  min-height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.tabs button.active {
  background: var(--color-surface-2);
}
.saving {
  color: var(--color-text-muted);
  font-size: 0.8rem;
}
.body,
.preview {
  min-height: 320px;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: ui-monospace, monospace;
  white-space: pre-wrap;
}
</style>
