<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { blogCaptureApi } from '@/api/blogCapture'
import { articlesApi, type ArticleRow, type BlogSearchItem } from '@/api/blogQueries'
import { taxonomyApi, type TaxonomyItem } from '@/api/blogTaxonomy'
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
const searchItems = ref<BlogSearchItem[]>([])

// Combinable filters + search + selection.
const search = ref('')
const classFilter = ref('')
const categoryFilter = ref('')
const aiFilter = ref('')
const cursor = ref(0)
const selected = ref<string[]>([])
const categories = ref<TaxonomyItem[]>([])
const categoryMenuPostId = ref<string | null>(null)
const openActionsId = ref<string | null>(null)
const swipeOffset = ref<Record<string, number>>({})
const undoAction = ref<{
  id: string
  kind: 'status' | 'category'
  value: string | null
} | null>(null)
const swipeState = ref<{
  id: string
  startX: number
  currentX: number
  startY: number
  currentY: number
} | null>(null)
interface TouchLikeEvent {
  touches: ArrayLike<{ clientX: number; clientY: number }>
}

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
const categoryNames = computed(() => new Map(categories.value.map((category) => [category.id, category.name])))
const searchResultById = computed(() => new Map(searchItems.value.map((item) => [item.id, item])))

const activeFilters = computed(() => {
  const filters: Array<{ key: string; label: string; clear: () => void }> = []
  if (search.value.trim()) {
    filters.push({ key: 'search', label: `关键词：${search.value.trim()}`, clear: () => { search.value = '' } })
  }
  if (classFilter.value) {
    filters.push({ key: 'class', label: `类别：${classFilter.value}`, clear: () => { classFilter.value = '' } })
  }
  if (categoryFilter.value) {
    filters.push({ key: 'category', label: `分类：${categoryName(categoryFilter.value)}`, clear: () => { categoryFilter.value = '' } })
  }
  if (aiFilter.value) {
    const label = AI_STATES.find((item) => item.v === aiFilter.value)?.label ?? aiFilter.value
    filters.push({ key: 'ai', label: `AI：${label}`, clear: () => { aiFilter.value = '' } })
  }
  return filters
})

function categoryName(id: string | null): string {
  return id ? categoryNames.value.get(id) ?? '未分类' : '未分类'
}

async function load(): Promise<void> {
  if (search.value.trim()) {
    const res = await articlesApi.search(search.value.trim(), {
      content_class: classFilter.value || undefined,
      category_id: categoryFilter.value || undefined,
      ai_state: aiFilter.value || undefined,
    }, cursor.value)
    searchItems.value = cursor.value > 0 ? [...searchItems.value, ...res.items] : res.items
    posts.value = searchItems.value.map((item) => ({
      id: item.id,
      title: item.title,
      content_status: item.content_status,
      content_class: item.content_class,
      category_id: item.category_id,
      status: item.status,
      ai_state: 'none' as const,
      source_count: 0,
      updated_at: item.updated_at,
      created_at: item.updated_at,
    }))
    total.value = res.total
    nextCursor.value = res.next_cursor
    return
  }
  searchItems.value = []
  const res = await articlesApi.list({
    content_class: classFilter.value || undefined,
    category_id: categoryFilter.value || undefined,
    ai_state: aiFilter.value || undefined,
    cursor: cursor.value,
  })
  posts.value = cursor.value > 0 ? [...posts.value, ...res.items] : res.items
  total.value = res.total
  nextCursor.value = res.next_cursor
}
onMounted(load)
onMounted(async () => {
  try {
    categories.value = await taxonomyApi.list('category', true)
  } catch {
    categories.value = []
  }
})

// Re-query when a filter changes (reset to first page).
watch([search, classFilter, categoryFilter, aiFilter], () => {
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

function closeRowActions(id: string): void {
  swipeOffset.value[id] = 0
  if (openActionsId.value === id) openActionsId.value = null
  if (categoryMenuPostId.value === id) categoryMenuPostId.value = null
}

function onTouchStart(id: string, event: TouchLikeEvent): void {
  const point = event.touches[0]
  if (!point) return
  swipeState.value = {
    id,
    startX: point.clientX,
    currentX: point.clientX,
    startY: point.clientY,
    currentY: point.clientY,
  }
}

function onTouchMove(id: string, event: TouchLikeEvent): void {
  const state = swipeState.value
  const point = event.touches[0]
  if (!state || state.id !== id || !point) return
  state.currentX = point.clientX
  state.currentY = point.clientY
  const delta = point.clientX - state.startX
  const verticalDelta = point.clientY - state.startY
  if (Math.abs(verticalDelta) >= Math.abs(delta)) {
    swipeOffset.value[id] = 0
    return
  }
  if (Math.abs(delta) < 8) return
  // Keep vertical page scrolling natural; horizontal movement is bounded so a
  // row never disappears from the viewport.
  swipeOffset.value[id] = Math.max(-168, Math.min(168, delta))
}

function onTouchEnd(id: string): void {
  const state = swipeState.value
  if (!state || state.id !== id) return
  const delta = state.currentX - state.startX
  swipeOffset.value[id] = Math.abs(delta) >= 72 ? (delta > 0 ? 152 : -152) : 0
  swipeState.value = null
}

function openMore(id: string): void {
  const next = openActionsId.value === id ? null : id
  openActionsId.value = next
  categoryMenuPostId.value = null
  swipeOffset.value[id] = 0
}

function openCategoryMenu(id: string): void {
  categoryMenuPostId.value = categoryMenuPostId.value === id ? null : id
  openActionsId.value = null
}

async function runRowAction(id: string, op: 'archive' | 'discard'): Promise<void> {
  if (op === 'discard' && !window.confirm('确定丢弃这篇文章吗？此操作可恢复。')) return
  const post = posts.value.find((item) => item.id === id)
  try {
    await articlesApi.batch([id], op, {})
    toast.value = op === 'archive' ? '文章已归档' : '文章已丢弃'
    undoAction.value = { id, kind: 'status', value: post?.content_status ?? 'draft' }
    closeRowActions(id)
    await load()
  } catch {
    toast.value = '操作失败，请稍后重试。'
  }
  window.setTimeout(() => (toast.value = ''), 2500)
}

async function setCategory(postId: string, categoryId: string | null): Promise<void> {
  const post = posts.value.find((item) => item.id === postId)
  try {
    await articlesApi.batch([postId], 'set_category', { category_id: categoryId })
    toast.value = categoryId ? `已归类到「${categoryName(categoryId)}」` : '已移除分类'
    undoAction.value = { id: postId, kind: 'category', value: post?.category_id ?? null }
    closeRowActions(postId)
    await load()
  } catch {
    toast.value = '分类保存失败，请稍后重试。'
  }
  window.setTimeout(() => (toast.value = ''), 2500)
}

async function undoLastAction(): Promise<void> {
  const action = undoAction.value
  if (!action) return
  try {
    if (action.kind === 'status') {
      await articlesApi.batch([action.id], 'set_status', { content_status: action.value })
    } else {
      await articlesApi.batch([action.id], 'set_category', { category_id: action.value })
    }
    toast.value = '已撤销上一步操作'
    undoAction.value = null
    await load()
  } catch {
    toast.value = '撤销失败，请稍后重试。'
  }
  window.setTimeout(() => (toast.value = ''), 2500)
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
        placeholder="搜索标题、正文、来源、分类或结构化字段…"
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
        v-model="categoryFilter"
        aria-label="按结构化分类筛选"
      >
        <option value="">
          全部分类
        </option>
        <option
          v-for="category in categories"
          :key="category.id"
          :value="category.id"
        >
          {{ category.name }}
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

    <div
      v-if="activeFilters.length > 0"
      class="active-filters"
      aria-label="已应用筛选"
    >
      <span class="active-filters-label">已筛选：</span>
      <span
        v-for="filter in activeFilters"
        :key="filter.key"
        class="filter-chip"
      >
        {{ filter.label }}
        <button
          type="button"
          :aria-label="`清除${filter.label}`"
          @click="filter.clear"
        >
          ×
        </button>
      </span>
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

    <ul class="post-list">
      <li
        v-for="p in posts"
        :key="p.id"
        class="post-row"
        :class="{ 'post-row--swiped-left': swipeOffset[p.id] === -152, 'post-row--swiped-right': swipeOffset[p.id] === 152 }"
        @touchstart="onTouchStart(p.id, $event)"
        @touchmove="onTouchMove(p.id, $event)"
        @touchend="onTouchEnd(p.id)"
      >
        <div
          class="swipe-actions swipe-actions--right"
          aria-hidden="true"
        >
          <button
            type="button"
            class="swipe-action swipe-action--category"
            @click.stop="openCategoryMenu(p.id)"
          >
            归类
          </button>
        </div>
        <div
          class="swipe-actions swipe-actions--left"
          aria-hidden="true"
        >
          <button
            type="button"
            class="swipe-action swipe-action--archive"
            @click.stop="runRowAction(p.id, 'archive')"
          >
            归档
          </button>
          <button
            type="button"
            class="swipe-action swipe-action--discard"
            @click.stop="runRowAction(p.id, 'discard')"
          >
            丢弃
          </button>
        </div>
        <div
          class="row-content"
          :style="{ transform: `translateX(${swipeOffset[p.id] ?? 0}px)` }"
        >
          <input
            type="checkbox"
            :checked="selected.includes(p.id)"
            :aria-label="`选择 ${p.title}`"
            @change="toggleOne(p.id)"
          >
          <button
            type="button"
            class="title"
            @click="openEditor(p.id)"
          >
            {{ p.title }}
          </button>
          <div class="row-meta">
            <span class="category-chip">{{ categoryName(p.category_id) }}</span>
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
            >{{ p.status === 'published' ? '已发布' : '草稿' }}</span>
          </div>
          <div
            v-if="searchResultById.get(p.id)"
            class="search-result"
          >
            <span>匹配：{{ searchResultById.get(p.id)?.matched_fields.map((field) => field === 'markdown' ? '正文' : field === 'structured_data' ? '结构化字段' : field === 'source' ? '来源' : field === 'tags' ? '标签' : field === 'category' ? '分类' : field).join('、') }}</span>
            <span
              v-if="searchResultById.get(p.id)?.highlight"
              class="search-highlight"
            >{{ searchResultById.get(p.id)?.highlight }}</span>
          </div>
          <button
            type="button"
            class="more-btn"
            :aria-expanded="openActionsId === p.id"
            :aria-label="`更多操作：${p.title}`"
            @click.stop="openMore(p.id)"
          >
            ⋯
          </button>
        </div>
        <div
          v-if="openActionsId === p.id"
          class="accessible-actions"
        >
          <button
            type="button"
            @click="openCategoryMenu(p.id)"
          >
            归类
          </button>
          <button
            type="button"
            @click="runRowAction(p.id, 'archive')"
          >
            归档
          </button>
          <button
            type="button"
            class="danger"
            @click="runRowAction(p.id, 'discard')"
          >
            丢弃
          </button>
        </div>
        <div
          v-if="categoryMenuPostId === p.id"
          class="category-menu"
          role="dialog"
          aria-label="选择文章分类"
        >
          <strong>选择主分类</strong>
          <button
            type="button"
            @click="setCategory(p.id, null)"
          >
            未分类
          </button>
          <button
            v-for="category in categories"
            :key="category.id"
            type="button"
            @click="setCategory(p.id, category.id)"
          >
            {{ category.name }}
          </button>
        </div>
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

    <div
      v-if="toast"
      class="toast"
      role="status"
    >
      <span>{{ toast }}</span>
      <button
        v-if="undoAction"
        type="button"
        class="toast-undo"
        @click="undoLastAction"
      >
        撤销
      </button>
    </div>

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
.active-filters {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin: calc(var(--space-2) * -1) 0 var(--space-3);
  color: var(--color-text-muted);
  font-size: 0.85rem;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  max-width: 100%;
  padding: 0.2rem 0.45rem;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-surface);
}
.filter-chip button {
  min-width: 1.25rem;
  min-height: 1.25rem;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  cursor: pointer;
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
.post-row {
  position: relative;
  min-height: 76px;
  overflow: hidden;
  isolation: isolate;
}
.row-content {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  position: relative;
  z-index: 1;
  transition: transform 0.18s ease;
  will-change: transform;
}
.search-result {
  flex-basis: 100%;
  display: grid;
  gap: 0.15rem;
  padding-left: 1.65rem;
  color: var(--color-text-muted);
  font-size: 0.78rem;
}
.search-highlight {
  overflow: hidden;
  color: var(--color-text);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-content .title {
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  flex: 1;
  min-width: 0;
  padding: 0;
}
.row-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}
.category-chip {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #4f46e5);
  font-size: 0.72rem;
}
.more-btn {
  min-width: var(--tap-target);
  min-height: var(--tap-target);
  border: 0;
  background: none;
  color: var(--color-text-muted);
  font-size: 1.35rem;
  cursor: pointer;
}
.swipe-actions {
  position: absolute;
  inset-block: 0;
  display: none;
  z-index: 0;
  align-items: stretch;
  gap: 2px;
  pointer-events: none;
}
.swipe-actions--right {
  inset-inline-start: 0;
}
.swipe-actions--left {
  inset-inline-end: 0;
}
.swipe-action {
  min-width: var(--mobile-row-action-width);
  padding: 0 var(--space-2);
  border: 0;
  color: #fff;
  font: inherit;
  cursor: pointer;
}
.swipe-action--category {
  background: var(--status-ai);
}
.swipe-action--archive {
  background: var(--status-normal);
}
.swipe-action--discard {
  background: var(--status-urgent);
}
.accessible-actions,
.category-menu {
  position: relative;
  z-index: 2;
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-top: 0;
}
.accessible-actions button,
.category-menu button {
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: inherit;
  cursor: pointer;
}
.accessible-actions .danger {
  color: var(--status-urgent);
}
.category-menu strong {
  width: 100%;
  font-size: 0.82rem;
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
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.toast-undo {
  border: 0;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.16);
  color: inherit;
  min-height: 32px;
  padding: 0 var(--space-2);
  cursor: pointer;
}
@media (max-width: 680px) {
  .posts {
    padding: var(--space-3);
  }
  .head {
    align-items: flex-start;
  }
  .head h1 {
    font-size: 1.25rem;
  }
  .head-actions {
    flex-shrink: 0;
  }
  .filters {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 2px;
  }
  .filters .search {
    min-width: 190px;
  }
  .filters select {
    flex: 0 0 auto;
    min-height: var(--tap-target);
  }
  .post-row {
    margin-bottom: var(--space-2);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
  }
  .swipe-actions {
    display: flex;
  }
  .post-row--swiped-right .swipe-actions--right,
  .post-row--swiped-left .swipe-actions--left {
    pointer-events: auto;
  }
  .row-content {
    border: 0;
    border-radius: 0;
    min-height: 76px;
  }
  .row-content .title {
    align-self: flex-start;
    padding-top: var(--space-1);
  }
  .row-meta {
    position: absolute;
    left: 52px;
    right: 52px;
    bottom: var(--space-2);
    justify-content: flex-start;
    flex-wrap: nowrap;
    overflow: hidden;
  }
  .status,
  .src-chip,
  .review-chip {
    white-space: nowrap;
  }
  .more-btn {
    align-self: flex-start;
  }
}
</style>
