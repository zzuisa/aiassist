<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { articlesApi, type TimelineItem } from '@/api/blogQueries'
import { taxonomyApi, type TaxonomyItem } from '@/api/blogTaxonomy'

const router = useRouter()
const items = ref<TimelineItem[]>([])
const categories = ref<TaxonomyItem[]>([])
const query = ref('')
const year = ref('')
const month = ref('')
const classFilter = ref('')
const categoryFilter = ref('')
const cursor = ref(0)
const total = ref(0)
const nextCursor = ref<number | null>(null)
const loading = ref(false)
const error = ref('')
const collapsedGroups = ref<Set<string>>(new Set())

const CONTENT_CLASSES = [
  ['technical', '技术'], ['project', '项目'], ['learning', '学习'], ['life', '生活'],
  ['travel', '旅行'], ['diary', '日记'], ['essay', '随笔'], ['quick', '快速记录'],
]

const categoryNames = computed(() => new Map(categories.value.map((category) => [category.id, category.name])))

const filteredItems = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return items.value
  return items.value.filter((item) => (
    (item.title + ' ' + (item.summary ?? '')).toLocaleLowerCase().includes(keyword)
  ))
})

const groupedItems = computed(() => {
  const groups = new Map<string, TimelineItem[]>()
  for (const item of filteredItems.value) {
    const key = item.time.slice(0, 7)
    const current = groups.get(key) ?? []
    current.push(item)
    groups.set(key, current)
  }
  return [...groups.entries()]
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await articlesApi.timeline({
      year: year.value ? Number(year.value) : undefined,
      month: month.value ? Number(month.value) : undefined,
      content_class: classFilter.value || undefined,
      category_id: categoryFilter.value || undefined,
      cursor: cursor.value,
    })
    items.value = cursor.value > 0 ? [...items.value, ...result.items] : result.items
    total.value = result.total
    nextCursor.value = result.next_cursor
  } catch {
    error.value = '时间轴暂时无法加载，请稍后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    categories.value = await taxonomyApi.list('category', true)
  } catch {
    categories.value = []
  }
  await load()
})

watch([year, month, classFilter, categoryFilter], () => {
  cursor.value = 0
  void load()
})

function openPost(id: string): void {
  void router.push('/blog/' + id)
}

function formatGroup(key: string): string {
  const [groupYear, groupMonth] = key.split('-')
  return groupYear + ' 年 ' + Number(groupMonth) + ' 月'
}

function toggleGroup(key: string): void {
  const next = new Set(collapsedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedGroups.value = next
}
</script>

<template>
  <main class="timeline-page">
    <header class="timeline-head">
      <div>
        <p class="eyebrow">
          博客回顾
        </p>
        <h1>时间轴</h1>
        <p class="muted">
          按文章发生时间回顾；没有发生时间时使用创建时间，并明确标记。
        </p>
      </div>
      <span class="count">共 {{ total }} 篇</span>
    </header>

    <div class="filters">
      <input
        v-model="query"
        type="search"
        placeholder="在当前时间轴中查找"
        aria-label="时间轴内搜索"
      >
      <input
        v-model="year"
        type="number"
        min="1970"
        max="2200"
        placeholder="年份"
        aria-label="按年份筛选"
      >
      <select
        v-model="month"
        aria-label="按月份筛选"
      >
        <option value="">
          全部月份
        </option>
        <option
          v-for="m in 12"
          :key="m"
          :value="String(m)"
        >
          {{ m }} 月
        </option>
      </select>
      <select
        v-model="classFilter"
        aria-label="按大类筛选"
      >
        <option value="">
          全部大类
        </option>
        <option
          v-for="entry in CONTENT_CLASSES"
          :key="entry[0]"
          :value="entry[0]"
        >
          {{ entry[1] }}
        </option>
      </select>
      <select
        v-model="categoryFilter"
        aria-label="按分类筛选"
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
    </div>

    <p
      v-if="error"
      class="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-else-if="loading && !items.length"
      class="muted"
    >
      正在加载时间轴…
    </p>
    <p
      v-else-if="!groupedItems.length"
      class="empty"
    >
      暂无符合条件的文章。
    </p>

    <section
      v-for="[group, groupItems] in groupedItems"
      :key="group"
      class="timeline-group"
      :aria-label="formatGroup(group)"
    >
      <h2>
        <button
          type="button"
          class="group-toggle"
          :aria-expanded="!collapsedGroups.has(group)"
          :aria-controls="`timeline-${group}`"
          @click="toggleGroup(group)"
        >
          <span aria-hidden="true">{{ collapsedGroups.has(group) ? '＋' : '－' }}</span>
          {{ formatGroup(group) }}
          <small>（{{ groupItems.length }}）</small>
        </button>
      </h2>
      <ol
        v-if="!collapsedGroups.has(group)"
        :id="`timeline-${group}`"
        class="timeline-list"
      >
        <li
          v-for="item in groupItems"
          :key="item.id"
          class="timeline-item"
        >
          <span
            class="timeline-dot"
            aria-hidden="true"
          />
          <div class="timeline-card">
            <time :datetime="item.time">
              {{ item.time.slice(0, 10) }} · {{ item.time_basis === 'occurred_at' ? '发生' : '创建' }}时间
            </time>
            <button
              type="button"
              class="title"
              @click="openPost(item.id)"
            >
              {{ item.title }}
            </button>
            <p
              v-if="item.summary"
              class="summary"
            >
              {{ item.summary }}
            </p>
            <span class="meta">
              {{ categoryNames.get(item.category_id ?? '') ?? '未分类' }} · {{ item.content_status }}
            </span>
          </div>
        </li>
      </ol>
    </section>

    <button
      v-if="nextCursor !== null"
      type="button"
      class="load-more"
      :disabled="loading"
      @click="cursor = nextCursor ?? 0; void load()"
    >
      {{ loading ? '加载中…' : '加载更多' }}
    </button>
  </main>
</template>

<style scoped>
.timeline-page { max-width: 860px; margin: 0 auto; padding: var(--space-4); }
.timeline-head { display: flex; justify-content: space-between; gap: var(--space-3); align-items: flex-start; }
.eyebrow { margin: 0 0 var(--space-1); color: var(--status-normal); font-size: 0.78rem; font-weight: 700; }
h1, h2, p { margin-top: 0; }
h1 { margin-bottom: var(--space-1); }
.muted, .empty, .count, .meta { color: var(--color-text-muted); }
.count { white-space: nowrap; font-size: 0.85rem; }
.filters { display: flex; gap: var(--space-2); flex-wrap: wrap; margin: var(--space-4) 0; }
.filters input, .filters select, .load-more {
  min-height: var(--tap-target); padding: 0 var(--space-3); border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); background: var(--color-surface); color: inherit; font: inherit;
}
.filters input[type='search'] { flex: 1 1 220px; }
.timeline-group { margin: var(--space-6) 0; }
.timeline-group h2 { font-size: 1rem; }
.group-toggle {
  display: inline-flex; align-items: center; gap: var(--space-1); border: 0; padding: 0;
  background: transparent; color: inherit; font: inherit; font-weight: 700; cursor: pointer;
}
.group-toggle small { color: var(--color-text-muted); font-size: 0.8em; font-weight: 400; }
.timeline-list { list-style: none; margin: 0; padding: 0 0 0 var(--space-4); border-left: 2px solid var(--color-border); }
.timeline-item { position: relative; padding: 0 0 var(--space-3) var(--space-3); }
.timeline-dot {
  position: absolute; left: -7px; top: var(--space-2); width: 12px; height: 12px; border-radius: 50%;
  background: var(--status-normal); border: 2px solid var(--color-surface); box-shadow: 0 0 0 1px var(--status-normal);
}
.timeline-card {
  display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-3);
  border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface);
}
time, .meta { font-size: 0.78rem; }
.title { border: 0; padding: 0; background: none; color: inherit; font: inherit; font-weight: 700; text-align: left; cursor: pointer; }
.summary { margin-bottom: 0; color: var(--color-text-muted); font-size: 0.9rem; }
.load-more { cursor: pointer; }
.error { color: var(--status-urgent); }
@media (max-width: 680px) {
  .timeline-page { padding: var(--space-3); }
  .timeline-head { flex-direction: column; }
  .filters { flex-wrap: nowrap; overflow-x: auto; padding-bottom: 2px; }
  .filters input, .filters select { flex: 0 0 auto; }
}
</style>
