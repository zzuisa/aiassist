<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { wordCloudApi, type WordCloudSnapshot, type WordCloudTerm } from '@/api/blogQueries'
import { blogSettingsApi } from '@/api/blogSettings'
import { taxonomyApi, type TaxonomyItem } from '@/api/blogTaxonomy'
import WordCloudView from './WordCloudView.vue'

const router = useRouter()
const sourceKind = ref<'tag' | 'keyword'>('keyword')
const year = ref('')
const contentClass = ref('')
const categoryId = ref('')
const minFrequency = ref(2)
const maxTerms = ref(100)
const snapshot = ref<WordCloudSnapshot | null>(null)
const categories = ref<TaxonomyItem[]>([])
const loading = ref(false)
const message = ref('')
const filters = () => ({
  ...(year.value ? { year: Number(year.value) } : {}),
  ...(contentClass.value ? { content_class: contentClass.value } : {}),
  ...(categoryId.value ? { category_id: categoryId.value } : {}),
})
async function load(): Promise<void> {
  loading.value = true
  try { snapshot.value = await wordCloudApi.get(sourceKind.value, filters()) } finally { loading.value = false }
}
async function rebuild(): Promise<void> {
  const result = await wordCloudApi.rebuild({
    source_kind: sourceKind.value, filter: filters(),
    min_frequency: minFrequency.value, max_terms: maxTerms.value,
  })
  snapshot.value = result.previous
  message.value = '词云重建已提交，可在任务中心查看进度。'
}
function openTerm(term: WordCloudTerm): void {
  void router.push({ name: 'blog', query: { [sourceKind.value === 'tag' ? 'tag_id' : 'keyword_id']: term.id } })
}
watch([sourceKind, year, contentClass, categoryId], () => void load())
onMounted(async () => {
  const taxonomyRequest = taxonomyApi.list('category', true)
    .then((items) => { categories.value = items })
    .catch(() => { categories.value = [] })
  const settingsRequest = blogSettingsApi.get()
    .then((settings) => {
      minFrequency.value = settings.word_cloud.min_term_count
      maxTerms.value = settings.word_cloud.max_terms
    })
    .catch(() => undefined)
  await Promise.all([taxonomyRequest, settingsRequest, load()])
})
</script>

<template>
  <main class="word-cloud-page">
    <header>
      <div>
        <p class="eyebrow">
          内容发现
        </p><h1>词云</h1>
      </div><button
        class="primary"
        @click="rebuild"
      >
        立即重建
      </button>
    </header>
    <section
      class="controls"
      aria-label="词云筛选"
    >
      <label>来源<select
        v-model="sourceKind"
        aria-label="词云来源"
      ><option value="keyword">关键词</option><option value="tag">标签</option></select></label>
      <label>年份<input
        v-model="year"
        aria-label="词云年份"
        type="number"
        min="1970"
        max="2200"
      ></label>
      <label>类别<select
        v-model="contentClass"
        aria-label="词云内容类别"
      ><option value="">全部</option><option value="technical">technical</option><option value="essay">essay</option></select></label>
      <label>分类<select
        v-model="categoryId"
        aria-label="词云分类"
      ><option value="">全部</option><option
        v-for="category in categories"
        :key="category.id"
        :value="category.id"
      >{{ category.name }}</option></select></label>
      <label>最低频次<input
        v-model.number="minFrequency"
        aria-label="最低频次"
        type="number"
        min="1"
      ></label>
      <label>最多词数<input
        v-model.number="maxTerms"
        aria-label="最多词数"
        type="number"
        min="1"
        max="500"
      ></label>
    </section>
    <p
      v-if="message"
      role="status"
    >
      {{ message }}
    </p>
    <p
      v-if="loading"
      role="status"
    >
      正在加载词云…
    </p>
    <template v-else-if="snapshot">
      <p
        v-if="snapshot.status !== 'ready'"
        class="stale"
        role="alert"
      >
        重建未完成，当前展示上次有效结果。
      </p>
      <p class="meta">
        覆盖 {{ snapshot.article_count }} 篇文章 · {{ snapshot.generated_at ? new Date(snapshot.generated_at).toLocaleString() : '尚未生成' }}
      </p>
      <WordCloudView
        v-if="snapshot.terms.length"
        :terms="snapshot.terms"
        @select="openTerm"
      />
      <p
        v-else
        class="empty"
      >
        当前筛选下没有达到频次要求的词。
      </p>
    </template>
    <p
      v-else
      class="empty"
    >
      尚无词云快照，请点击“立即重建”。
    </p>
  </main>
</template>

<style scoped>
.word-cloud-page{max-width:980px;margin:auto;padding:var(--space-4)}header,.controls{display:flex;gap:var(--space-3);justify-content:space-between;align-items:end;flex-wrap:wrap}.controls{margin:var(--space-4) 0;padding:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-lg)}label{display:grid;gap:var(--space-1);font-size:.8rem}select,input,button{min-height:var(--tap-target);padding:0 var(--space-2)}.primary{background:var(--status-normal);color:#fff;border:0;border-radius:var(--radius-sm)}.eyebrow,.meta,.empty{color:var(--color-text-muted)}h1,.eyebrow{margin:0}.stale{color:var(--status-urgent)}
</style>
