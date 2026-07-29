<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { postsApi, type Post } from '@/api/posts'
import { blogCaptureApi } from '@/api/blogCapture'
import PostCreateDialog from '@/modules/posts/PostCreateDialog.vue'
import ClipboardCreateDialog from '@/modules/posts/ClipboardCreateDialog.vue'
import UrlCreateDialog from '@/modules/posts/UrlCreateDialog.vue'
import QuickCaptureDialog from '@/modules/posts/QuickCaptureDialog.vue'

const router = useRouter()
const posts = ref<Post[]>([])
const toast = ref('')

// Which dialog is open. 'picker' is the source-selection entry dialog.
type DialogKind = 'picker' | 'clipboard' | 'url' | 'quick' | null
const dialog = ref<DialogKind>(null)
const urlSeed = ref('')

async function load(): Promise<void> {
  posts.value = await postsApi.list()
}
onMounted(load)

function openEditor(postId: string): void {
  void router.push(`/blog/${postId}`)
}

async function onSelectSource(kind: 'blank' | 'clipboard' | 'url' | 'quick'): Promise<void> {
  if (kind === 'blank') {
    // Blank content is created directly and opens in the editor.
    dialog.value = null
    const res = await blogCaptureApi.blank({ title: '未命名文章' })
    openEditor(res.post.id)
    return
  }
  dialog.value = kind
}

function onCreated(postId: string): void {
  dialog.value = null
  openEditor(postId)
}

function onSaved(): void {
  toast.value = '已保存到「待整理」'
  void load()
  window.setTimeout(() => (toast.value = ''), 2500)
}

function switchToUrl(url: string): void {
  urlSeed.value = url
  dialog.value = 'url'
}
</script>

<template>
  <main class="posts">
    <header class="head">
      <h1>博客</h1>
      <button
        type="button"
        class="new-btn"
        @click="dialog = 'picker'"
      >
        新建内容
      </button>
    </header>

    <ul>
      <li
        v-for="p in posts"
        :key="p.id"
        @click="openEditor(p.id)"
      >
        <span class="title">{{ p.title }}</span>
        <span
          class="status"
          :data-status="p.status"
        >
          {{ p.status === 'published' ? '已发布' : '草稿' }}
        </span>
      </li>
    </ul>
    <p
      v-if="posts.length === 0"
      class="muted"
    >
      还没有文章。
    </p>

    <p
      v-if="toast"
      class="toast"
      role="status"
    >
      {{ toast }}
    </p>

    <PostCreateDialog
      v-if="dialog === 'picker'"
      @close="dialog = null"
      @select="onSelectSource"
    />
    <ClipboardCreateDialog
      v-else-if="dialog === 'clipboard'"
      @close="dialog = null"
      @created="onCreated"
      @saved="onSaved"
      @switch-url="switchToUrl"
    />
    <UrlCreateDialog
      v-else-if="dialog === 'url'"
      :initial-url="urlSeed"
      @close="dialog = null"
      @created="onCreated"
      @saved="onSaved"
    />
    <QuickCaptureDialog
      v-else-if="dialog === 'quick'"
      @close="dialog = null"
      @created="onCreated"
      @saved="onSaved"
    />
  </main>
</template>

<style scoped>
.posts {
  padding: var(--space-4);
  max-width: 760px;
  margin: 0 auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.new-btn {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: white;
  cursor: pointer;
}
ul {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
}
li {
  display: flex;
  justify-content: space-between;
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  cursor: pointer;
}
.status[data-status='published'] {
  color: var(--status-done);
}
.muted {
  color: var(--color-text-muted);
}
.toast {
  position: fixed;
  bottom: var(--space-4);
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-text, #111827);
  color: #fff;
  padding: var(--space-2) var(--space-4);
  border-radius: 999px;
  font-size: 0.9rem;
}
</style>
