<script setup lang="ts">
// Post property sidebar (spec 005, US2, T058).
//
// Edits the organisation fields that live beside the body: content class and
// type, status, occurrence time, location and project. Taxonomy relations
// (category/tags/keywords) and Skill selection are surfaced read-only here —
// their management endpoints arrive in later stories — while source summary,
// version and AI status are shown for context. Every change emits a PostPatch.
import { onMounted, ref } from 'vue'
import type { Post, PostPatch } from '@/api/posts'
import { contentTypesApi, type ContentType } from '@/api/blogQueries'

const props = defineProps<{ post: Post }>()
const emit = defineEmits<{ (e: 'patch', patch: PostPatch): void }>()

const CONTENT_CLASSES = [
  'technical', 'project', 'learning', 'life', 'travel',
  'diary', 'essay', 'bookmark', 'media', 'item', 'quick',
]
const USER_STATUSES = [
  { value: 'triage', label: '待整理' },
  { value: 'draft', label: '草稿' },
  { value: 'completed', label: '完成' },
  { value: 'archived', label: '归档' },
  { value: 'discarded', label: '弃用' },
]

const contentTypes = ref<ContentType[]>([])
onMounted(async () => {
  try {
    contentTypes.value = (await contentTypesApi.list()).filter((c) => c.enabled)
  } catch {
    contentTypes.value = []
  }
})

function typesForClass(): ContentType[] {
  return contentTypes.value.filter((c) => c.content_class === props.post.content_class)
}

function toDateInput(iso: string | null): string {
  return iso ? iso.slice(0, 10) : ''
}
</script>

<template>
  <aside class="sidebar">
    <section>
      <label class="fld">
        <span>内容类别</span>
        <select
          :value="post.content_class"
          @change="emit('patch', { content_class: ($event.target as HTMLSelectElement).value, content_type_id: null })"
        >
          <option
            v-for="c in CONTENT_CLASSES"
            :key="c"
            :value="c"
          >
            {{ c }}
          </option>
        </select>
      </label>

      <label class="fld">
        <span>内容类型</span>
        <select
          :value="post.content_type_id ?? ''"
          @change="emit('patch', { content_type_id: ($event.target as HTMLSelectElement).value || null })"
        >
          <option value="">
            （未指定）
          </option>
          <option
            v-for="t in typesForClass()"
            :key="t.id"
            :value="t.id"
          >
            {{ t.name }}
          </option>
        </select>
      </label>

      <label class="fld">
        <span>状态</span>
        <select
          :value="post.content_status"
          @change="emit('patch', { content_status: ($event.target as HTMLSelectElement).value })"
        >
          <option
            v-for="s in USER_STATUSES"
            :key="s.value"
            :value="s.value"
          >
            {{ s.label }}
          </option>
        </select>
      </label>
    </section>

    <section>
      <label class="fld">
        <span>发生时间</span>
        <input
          type="date"
          :value="toDateInput(post.occurred_at)"
          @change="emit('patch', { occurred_at: ($event.target as HTMLInputElement).value ? new Date(($event.target as HTMLInputElement).value).toISOString() : null })"
        >
      </label>
      <label class="fld">
        <span>地点</span>
        <input
          :value="post.location ?? ''"
          placeholder="可选"
          @change="emit('patch', { location: ($event.target as HTMLInputElement).value || null })"
        >
      </label>
      <label class="fld">
        <span>项目</span>
        <input
          :value="post.project ?? ''"
          placeholder="可选"
          @change="emit('patch', { project: ($event.target as HTMLInputElement).value || null })"
        >
      </label>
    </section>

    <section class="readonly">
      <h3>组织与关联</h3>
      <p>分类 / 标签 / 关键词管理将在后续版本开放。</p>
      <ul class="meta">
        <li>标签：{{ post.tag_ids.length }}</li>
        <li>关键词：{{ post.keyword_ids.length }}</li>
        <li>版本：v{{ post.version }}</li>
        <li v-if="post.ai_summary">
          AI 优化：{{ post.ai_summary.optimization_count }} 次
        </li>
      </ul>
    </section>

    <section
      v-if="post.source_summary.length"
      class="readonly"
    >
      <h3>来源</h3>
      <ul class="meta">
        <li
          v-for="s in post.source_summary"
          :key="s.id"
        >
          <span class="badge">{{ s.source_type }}</span>
          <span :data-status="s.status">{{ s.status }}</span>
          <a
            v-if="s.original_url"
            :href="s.original_url"
            target="_blank"
            rel="noopener noreferrer nofollow"
          >链接</a>
        </li>
      </ul>
    </section>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
  border-left: 1px solid var(--color-border);
  overflow-y: auto;
  min-width: 240px;
}
.fld {
  display: block;
  margin-bottom: var(--space-2);
}
.fld > span {
  display: block;
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin-bottom: 0.2rem;
}
.fld select,
.fld input {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font: inherit;
}
.readonly h3 {
  font-size: 0.85rem;
  margin: 0 0 var(--space-2);
}
.readonly p {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-2);
}
.meta {
  list-style: none;
  padding: 0;
  margin: 0;
  font-size: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.meta li {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.badge {
  font-size: 0.7rem;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background: var(--color-accent-soft, #eef2ff);
  color: var(--color-accent, #4f46e5);
}
</style>
