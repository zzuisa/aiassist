<script setup lang="ts">
// Read-only article view (spec 005, US2, T061).
//
// Renders the user's canonical content and, separately and clearly labelled, the
// captured original source(s). Keeping the two regions distinct means an AI- or
// user-authored article is never confused with the raw material it came from.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { postsApi, type Post } from '@/api/posts'
import { blogCaptureApi, type CaptureSource } from '@/api/blogCapture'
import { blogAIApi } from '@/api/blogAI'
import MarkdownPreview from '@/modules/posts/MarkdownPreview.vue'

const route = useRoute()
const router = useRouter()
const post = ref<Post | null>(null)
const sources = ref<CaptureSource[]>([])
const showSource = ref(false)

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
  post.value = await postsApi.get(id)
}
onMounted(load)

// Archive/discard keep the article recoverable (status-only) and never break a
// published slug — publishing must be undone first, which the confirmation notes.
async function archiveArticle(mode: 'archive' | 'discard'): Promise<void> {
  if (!post.value) return
  if (post.value.status === 'published') {
    window.alert('已发布的文章请先取消发布再归档/丢弃。')
    return
  }
  const verb = mode === 'archive' ? '归档' : '丢弃'
  if (!window.confirm(`确定要${verb}这篇文章吗？此操作可恢复。`)) return
  const { articlesApi } = await import('@/api/blogQueries')
  await articlesApi.batch([post.value.id], mode)
  router.push({ name: 'blog' })
}

async function loadSources(): Promise<void> {
  showSource.value = !showSource.value
  if (showSource.value && post.value && sources.value.length === 0) {
    const loaded: CaptureSource[] = []
    for (const s of post.value.source_summary) {
      try {
        loaded.push(await blogCaptureApi.getSource(s.id))
      } catch {
        /* skip unreadable source */
      }
    }
    sources.value = loaded
  }
}
</script>

<template>
  <main
    v-if="post"
    class="view"
  >
    <div
      v-if="reviewPending"
      class="review-banner"
    >
      <span>有一份 AI 优化候选待审核。</span>
      <button
        type="button"
        @click="goReview"
      >
        去审核
      </button>
    </div>
    <header class="head">
      <h1>{{ post.title }}</h1>
      <p
        v-if="post.subtitle"
        class="subtitle"
      >
        {{ post.subtitle }}
      </p>
      <div class="head-actions">
        <button
          type="button"
          class="edit"
          @click="router.push(`/blog/${post.id}`)"
        >
          编辑
        </button>
        <button
          type="button"
          class="ghost"
          @click="archiveArticle('archive')"
        >
          归档
        </button>
        <button
          type="button"
          class="ghost danger"
          @click="archiveArticle('discard')"
        >
          丢弃
        </button>
      </div>
    </header>

    <p
      v-if="post.summary"
      class="summary"
    >
      {{ post.summary }}
    </p>

    <!-- User / AI content region -->
    <section class="content">
      <MarkdownPreview :markdown="post.markdown" />
    </section>

    <!-- Original source region, kept visually separate -->
    <section
      v-if="post.source_summary.length"
      class="sources"
    >
      <button
        type="button"
        class="sources__toggle"
        @click="loadSources"
      >
        {{ showSource ? '隐藏原始来源' : `查看原始来源 (${post.source_summary.length})` }}
      </button>
      <div
        v-if="showSource"
        class="sources__body"
      >
        <article
          v-for="s in sources"
          :key="s.id"
          class="source-card"
        >
          <div class="source-card__meta">
            <span class="badge">{{ s.source_type }}</span>
            <a
              v-if="s.original_url"
              :href="s.original_url"
              target="_blank"
              rel="noopener noreferrer nofollow"
            >{{ s.original_title || s.original_url }}</a>
          </div>
          <MarkdownPreview
            v-if="s.normalized_markdown"
            :markdown="s.normalized_markdown"
          />
          <pre
            v-else-if="s.original_text"
            class="raw"
          >{{ s.original_text }}</pre>
          <p
            v-else
            class="muted"
          >
            该来源尚未抽取正文。
          </p>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.view {
  max-width: 820px;
  margin: 0 auto;
  padding: var(--space-4);
}
.head {
  position: relative;
}
.head h1 {
  margin: 0;
}
.subtitle {
  color: var(--color-text-muted);
  margin: 0.25rem 0 0;
}
.head-actions {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  gap: var(--space-2);
}
.edit,
.ghost {
  min-height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  cursor: pointer;
}
.ghost.danger {
  color: var(--status-danger, #dc2626);
}
.summary {
  font-style: italic;
  color: var(--color-text-muted);
  border-left: 3px solid var(--color-border);
  padding-left: var(--space-3);
}
.content {
  margin-top: var(--space-4);
}
.sources {
  margin-top: var(--space-4);
  border-top: 2px dashed var(--color-border);
  padding-top: var(--space-3);
}
.sources__toggle {
  border: none;
  background: none;
  color: var(--color-accent, #4f46e5);
  cursor: pointer;
  font-size: 0.9rem;
}
.source-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
  margin-top: var(--space-3);
  background: var(--color-surface-muted, #f8fafc);
}
.source-card__meta {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-2);
}
.badge {
  font-size: 0.7rem;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #4f46e5);
}
.raw {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.9rem;
}
.muted {
  color: var(--color-text-muted);
}
</style>
