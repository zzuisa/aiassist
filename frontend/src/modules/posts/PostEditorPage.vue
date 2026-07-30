<script setup lang="ts">
// Editor shell (spec 005, US2, T059).
//
// Hosts the canonical Markdown through three modes — source / rich / split — plus
// a read-only preview, with focus and fullscreen affordances and a document
// outline. Switching from rich→source (or vice-versa) after edits shows a
// one-time conversion-risk confirmation because the rich editor re-serializes
// Markdown. All saving is delegated to usePostAutosave; the body is one source
// of truth shared by every mode.
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { postsApi, type Post, type PostPatch } from '@/api/posts'
import { usePostAutosave } from '@/modules/posts/usePostAutosave'
import MarkdownSourceEditor from '@/modules/posts/MarkdownSourceEditor.vue'
import RichMarkdownEditor from '@/modules/posts/RichMarkdownEditor.vue'
import MarkdownPreview from '@/modules/posts/MarkdownPreview.vue'
import PostPropertySidebar from '@/modules/posts/PostPropertySidebar.vue'
import OptimizePostDialog from '@/modules/posts/OptimizePostDialog.vue'
import { blogAIApi } from '@/api/blogAI'

type Mode = 'source' | 'rich' | 'split' | 'preview'

const route = useRoute()
const router = useRouter()
const post = ref<Post | null>(null)
const markdown = ref('')
const title = ref('')
const mode = ref<Mode>('source')
const focus = ref(false)
const fullscreen = ref(false)
const publishing = ref(false)
const optimizing = ref(false)

const autosave = usePostAutosave(post)

// Open the AI optimize dialog only after any pending edit is persisted, so the
// run binds to the revision the user is actually looking at.
async function openOptimize(): Promise<void> {
  if (!post.value) return
  if (autosave.isDirty()) {
    const ok = await autosave.save()
    if (!ok) return
  }
  optimizing.value = true
}

function onOptimizeSubmitted(jobId: string): void {
  optimizing.value = false
  router.push({ name: 'blog-jobs', query: { focus: jobId } })
}

// A candidate awaits review when the server marks the article `ai_review`.
const reviewPending = computed(() => post.value?.content_status === 'ai_review')

async function goReview(): Promise<void> {
  if (!post.value) return
  const candidates = await blogAIApi.listCandidates(post.value.id)
  const pending = candidates.find((c) => c.status === 'pending' || c.status === 'merge_required')
  if (pending) {
    router.push({
      name: 'blog-candidate-compare',
      params: { id: post.value.id, candidateId: pending.id },
    })
  }
}

async function load(): Promise<void> {
  const id = route.params.id as string
  const p = await postsApi.get(id)
  post.value = p
  markdown.value = p.markdown
  title.value = p.title
  mode.value = (p.editor_mode as Mode) || 'source'
  if (mode.value === 'preview') mode.value = 'source'
}
onMounted(load)

// Keep the local body in sync when the server copy is replaced (e.g. reload).
watch(post, (p) => {
  if (p && p.markdown !== markdown.value && !autosave.isDirty()) markdown.value = p.markdown
})

function onBody(v: string): void {
  markdown.value = v
  autosave.update({ markdown: v })
}
function onTitle(e: Event): void {
  const v = (e.target as HTMLInputElement).value
  title.value = v
  autosave.update({ title: v })
}
function onPatch(patch: PostPatch): void {
  autosave.update(patch)
}

// Conversion-risk confirmation when moving between rich and source after edits.
const RICHY = new Set<Mode>(['rich', 'split'])
function switchMode(next: Mode): void {
  const crossing = RICHY.has(mode.value) !== RICHY.has(next)
  if (crossing && autosave.isDirty()) {
    const ok = window.confirm(
      '切换编辑模式会以富文本重新生成 Markdown，可能规整部分格式。是否继续？',
    )
    if (!ok) return
  }
  mode.value = next
  if (post.value && next !== 'preview' && next !== post.value.editor_mode) {
    autosave.update({ editor_mode: next })
  }
}

const outline = computed(() =>
  markdown.value
    .split('\n')
    .map((l) => /^(#{1,6})\s+(.*)$/.exec(l))
    .filter((m): m is RegExpExecArray => m !== null)
    .map((m) => ({ level: m[1].length, text: m[2].trim() })),
)

const saveLabel = computed(() => {
  switch (autosave.state.value) {
    case 'saving':
      return '保存中…'
    case 'saved':
      return '已保存'
    case 'dirty':
      return '待保存'
    case 'conflict':
      return '有冲突'
    case 'error':
      return '保存失败'
    default:
      return ''
  }
})

async function togglePublish(): Promise<void> {
  if (!post.value) return
  publishing.value = true
  try {
    await autosave.save()
    post.value = await postsApi.publish(
      post.value.id,
      post.value.status !== 'published',
      post.value.version,
    )
  } finally {
    publishing.value = false
  }
}

// Navigation guard: never leave with unsaved changes silently.
onBeforeRouteLeave(async () => {
  if (!autosave.isDirty()) return true
  const saved = await autosave.save()
  if (saved) return true
  return window.confirm('有未保存的更改，确定离开吗？')
})
</script>

<template>
  <main
    v-if="post"
    class="editor"
    :class="{ 'editor--fullscreen': fullscreen, 'editor--focus': focus }"
  >
    <header class="head">
      <input
        class="title"
        aria-label="标题"
        :value="title"
        @input="onTitle"
      >
      <div class="actions">
        <span
          class="save-state"
          :data-state="autosave.state.value"
        >{{ saveLabel }}</span>
        <button
          v-if="reviewPending"
          type="button"
          class="review-btn"
          @click="goReview"
        >
          待审核 AI 优化
        </button>
        <RouterLink
          class="versions-link"
          :to="{ name: 'blog-post-versions', params: { id: post.id } }"
        >
          版本
        </RouterLink>
        <button
          type="button"
          class="optimize-btn"
          :disabled="optimizing"
          @click="openOptimize"
        >
          AI 优化
        </button>
        <button
          type="button"
          :disabled="publishing"
          @click="togglePublish"
        >
          {{ post.status === 'published' ? '取消发布' : '发布' }}
        </button>
      </div>
    </header>

    <OptimizePostDialog
      v-if="optimizing && post"
      :post-id="post.id"
      :post-version="post.version"
      @close="optimizing = false"
      @submitted="onOptimizeSubmitted"
    />

    <div
      v-if="autosave.state.value === 'conflict'"
      class="conflict"
      role="alert"
    >
      {{ autosave.errorMessage.value }}
      <button
        type="button"
        @click="autosave.reload()"
      >
        重新载入
      </button>
    </div>

    <nav class="toolbar">
      <div class="modes">
        <button
          v-for="m in (['source', 'rich', 'split', 'preview'] as Mode[])"
          :key="m"
          type="button"
          :class="{ active: mode === m }"
          @click="switchMode(m)"
        >
          {{ { source: '源码', rich: '富文本', split: '分栏', preview: '预览' }[m] }}
        </button>
      </div>
      <div class="view-toggles">
        <button
          type="button"
          :class="{ active: focus }"
          @click="focus = !focus"
        >
          专注
        </button>
        <button
          type="button"
          :class="{ active: fullscreen }"
          @click="fullscreen = !fullscreen"
        >
          全屏
        </button>
      </div>
    </nav>

    <div class="workbench">
      <nav
        v-if="!focus && outline.length"
        class="outline"
      >
        <p class="outline__title">
          大纲
        </p>
        <ul>
          <li
            v-for="(h, i) in outline"
            :key="i"
            :style="{ paddingLeft: `${(h.level - 1) * 0.75}rem` }"
          >
            {{ h.text }}
          </li>
        </ul>
      </nav>

      <div class="pane">
        <MarkdownSourceEditor
          v-if="mode === 'source'"
          :model-value="markdown"
          @update:model-value="onBody"
        />
        <RichMarkdownEditor
          v-else-if="mode === 'rich'"
          :model-value="markdown"
          @update:model-value="onBody"
        />
        <MarkdownPreview
          v-else-if="mode === 'preview'"
          :markdown="markdown"
        />
        <div
          v-else
          class="split"
        >
          <MarkdownSourceEditor
            :model-value="markdown"
            @update:model-value="onBody"
          />
          <MarkdownPreview :markdown="markdown" />
        </div>
      </div>

      <PostPropertySidebar
        v-if="!focus"
        :post="post"
        @patch="onPatch"
      />
    </div>
  </main>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.editor--fullscreen {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: var(--color-surface, #fff);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}
.title {
  flex: 1;
  font-size: 1.2rem;
  border: none;
  background: transparent;
  color: var(--color-text);
  padding: var(--space-2) 0;
}
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.actions button {
  min-height: var(--tap-target);
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-sm);
  background: var(--status-normal);
  color: #fff;
  cursor: pointer;
}
.save-state {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}
.save-state[data-state='conflict'],
.save-state[data-state='error'] {
  color: var(--status-danger, #dc2626);
}
.conflict {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: var(--space-2) var(--space-4);
  background: var(--status-danger-soft, #fef2f2);
  color: var(--status-danger, #dc2626);
}
.toolbar {
  display: flex;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}
.modes,
.view-toggles {
  display: flex;
  gap: var(--space-2);
}
.toolbar button {
  min-height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.toolbar button.active {
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #4f46e5);
  border-color: var(--color-accent, #4f46e5);
}
.workbench {
  display: flex;
  flex: 1;
  min-height: 0;
}
.outline {
  width: 180px;
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  padding: var(--space-3);
}
.outline__title {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-2);
}
.outline ul {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 0.85rem;
}
.outline li {
  padding: 0.15rem 0;
  cursor: default;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pane {
  flex: 1;
  min-width: 0;
  display: flex;
}
.pane > * {
  flex: 1;
  min-width: 0;
}
.split {
  display: flex;
  width: 100%;
}
.split > * {
  flex: 1;
  min-width: 0;
  border-right: 1px solid var(--color-border);
}
@media (max-width: 720px) {
  .workbench {
    flex-direction: column;
  }
  .outline {
    width: auto;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
  }
  .split {
    flex-direction: column;
  }
}
</style>
