<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { blogCaptureApi } from '@/api/blogCapture'
import { articlesApi, type ArticleRow } from '@/api/blogQueries'
import PostCreateDialog from '@/modules/posts/PostCreateDialog.vue'
import ClipboardCreateDialog from '@/modules/posts/ClipboardCreateDialog.vue'
import UrlCreateDialog from '@/modules/posts/UrlCreateDialog.vue'
import QuickCaptureDialog from '@/modules/posts/QuickCaptureDialog.vue'
import PostBatchActionBar from '@/modules/posts/PostBatchActionBar.vue'

const router = useRouter()
const posts = ref<ArticleRow[]>([])
const total = ref(0)
const nextCursor = ref<number | null>(null)
const toast = ref('')

// Combinable filters + search + selection.
const search = ref('')
const classFilter = ref('')
const aiFilter = ref('')
const cursor = ref(0)
const selected = ref<string[]>([])

// Which dialog is open. 'picker' is the source-selection entry dialog.
type DialogKind = 'picker' | 'clipboard' | 'url' | 'quick' | null
const dialog = ref<DialogKind>(null)
const urlSeed = ref('')

const CONTENT_CLASSES = ['technical', 'life', 'learning', 'travel', 'diary', 'essay', 'quick']
const AI_STATES: Array<{ v: string; label: string }> = [
  { v: 'review', label: '待审核' }, { v: 'processing', label: '优化中' },
  { v: 'failed', label: '失败' }, { v: 'optimized', label: '已优化' }, { v: 'none', label: '未优化' },
]

const allSelected = computed(() => posts.value.length > 0 && selected.value.length === posts.value.length)

async function load(): Promise<void> {
  const res = await articlesApi.list({
    search: search.value || undefined,
    content_class: classFilter.value || undefined,
    ai_state: aiFilter.value || undefined,
    cursor: cursor.value,
  })
  posts.value = cursor.value > 0 ? [...posts.value, ...res.items] : res.items
  total.value = res.total
  nextCursor.value = res.next_cursor
}
onMounted(load)

// Re-query when a filter changes (reset to first page).
watch([search, classFilter, aiFilter], () => {
  cursor.value = 0
  selected.value = []
  void load()
})

function openEditor(postId: string): void {
  void router.push(`/blog/${postId}`)
}

function toggleOne(id: string): void {
  const i = selected.value.indexOf(id)
  if (i >= 0) selected.value.splice(i, 1)
  else selected.value.push(id)
}
function toggleAll(): void {
  selected.value = allSelected.value ? [] : posts.value.map((p) => p.id)
}
function onBatchDone(): void {
  selected.value = []
  void load()
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
      <div class="head-actions">
        <RouterLink
          class="triage-link"
          :to="{ name: 'blog-triage' }"
        >
          待整理
        </RouterLink>
        <button
          type="button"
          class="new-btn"
          @click="dialog = 'picker'"
        >
          新建内容
        </button>
      </div>
    </header>

    <div class="filters">
      <input
        v-model="search"
        class="search"
        type="search"
        placeholder="搜索标题或正文…"
        aria-label="搜索文章"
      >
      <select
        v-model="classFilter"
        aria-label="按类别筛选"
      >
        <option value="">
          全部类别
        </option>
        <option
          v-for="c in CONTENT_CLASSES"
          :key="c"
          :value="c"
        >
          {{ c }}
        </option>
      </select>
      <select
        v-model="aiFilter"
        aria-label="按 AI 状态筛选"
      >
        <option value="">
          全部 AI 状态
        </option>
        <option
          v-for="a in AI_STATES"
          :key="a.v"
          :value="a.v"
        >
          {{ a.label }}
        </option>
      </select>
    </div>

    <PostBatchActionBar
      v-if="selected.length > 0"
      :selected-ids="selected"
      @done="onBatchDone"
      @clear="selected = []"
    />

    <div
      v-if="posts.length > 0"
      class="select-all"
    >
      <label>
        <input
          type="checkbox"
          :checked="allSelected"
          aria-label="全选"
          @change="toggleAll"
        >
        全选（共 {{ total }} 篇）
      </label>
    </div>

    <ul>
      <li
        v-for="p in posts"
        :key="p.id"
      >
        <input
          type="checkbox"
          :checked="selected.includes(p.id)"
          :aria-label="`选择 ${p.title}`"
          @change="toggleOne(p.id)"
        >
        <span
          class="title"
          @click="openEditor(p.id)"
        >{{ p.title }}</span>
        <span
          v-if="p.content_status === 'ai_review'"
          class="review-chip"
        >待审核</span>
        <span
          v-if="p.source_count"
          class="src-chip"
        >{{ p.source_count }} 来源</span>
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
      没有符合条件的文章。
    </p>
    <button
      v-if="nextCursor !== null"
      type="button"
      class="more"
      @click="cursor = nextCursor ?? 0; load()"
    >
      加载更多
    </button>

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
.head-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}
.triage-link {
  color: var(--color-text-muted);
  text-decoration: none;
  padding: 0 var(--space-2);
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
.filters {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin: var(--space-3) 0;
}
.filters .search {
  flex: 1;
  min-width: 160px;
}
.filters input,
.filters select {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.select-all {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}
ul {
  list-style: none;
  padding: 0;
  margin: var(--space-3) 0 0;
}
li {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
}
li .title {
  cursor: pointer;
  flex: 1;
}
.src-chip {
  font-size: 0.72rem;
  color: var(--color-text-muted);
}
.more {
  min-height: 2.2rem;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: none;
  cursor: pointer;
  margin-top: var(--space-2);
}
.status[data-status='published'] {
  color: var(--status-done);
}
.review-chip {
  font-size: 0.75rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--status-info-soft, #dbeafe);
  color: var(--status-info, #2563eb);
  margin-left: auto;
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
